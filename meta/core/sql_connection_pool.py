# -*- coding: utf-8 -*-
"""
SQLite 连接池

提供读写分离的连接池，利用 SQLite WAL 模式实现并发读：
- SQLiteConnectionPool: 读写分离连接池
- PooledConnection: 池化连接包装
- ConnectionConfig: 连接池配置
"""

import sqlite3
import threading
import time
import logging
import os
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections import deque

logger = logging.getLogger(__name__)


def _safe_cleanup_wal_shm(db_path: str):
    wal_path = db_path + '-wal'
    shm_path = db_path + '-shm'
    if not os.path.exists(wal_path) and not os.path.exists(shm_path):
        return
    try:
        db_mtime = os.path.getmtime(db_path) if os.path.exists(db_path) else 0
        wal_mtime = os.path.getmtime(wal_path) if os.path.exists(wal_path) else 0
    except OSError:
        return
    if wal_mtime > 0 and wal_mtime < db_mtime:
        for path in (wal_path, shm_path):
            try:
                os.remove(path)
                logger.info("Cleaned orphan file: %s", path)
            except OSError:
                pass


@dataclass
class ConnectionConfig:
    max_readers: int = 20
    idle_timeout: float = 300.0
    max_lifetime: float = 3600.0
    acquire_timeout: float = 30.0
    db_timeout: float = 30.0
    wal_auto_checkpoint: int = 1000


@dataclass
class PooledConnection:
    connection: sqlite3.Connection
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    in_use: bool = False
    usage_count: int = 0
    # [V007.16] 跟踪 connection 健康状态
    # 上次是否报 disk I/O error 或 database is locked
    last_io_error: bool = False
    # 连续错误次数 (用于熔断: 连续 3 次错误强制重建)
    consecutive_errors: int = 0
    # 上次错误信息 (debug 用)
    last_error_msg: str = ""

    def touch(self):
        self.last_used_at = time.time()
        self.usage_count += 1

    def is_expired(self, max_lifetime: float) -> bool:
        return (time.time() - self.created_at) > max_lifetime

    def is_idle_expired(self, idle_timeout: float) -> bool:
        return (not self.in_use) and ((time.time() - self.last_used_at) > idle_timeout)

    def mark_error(self, error_msg: str = ""):
        """[V007.16] 标记 connection 出现错误"""
        self.last_io_error = True
        self.consecutive_errors += 1
        if error_msg:
            self.last_error_msg = error_msg

    def clear_error(self):
        """[V007.16] 清除错误标记 (execute 成功后调)"""
        self.last_io_error = False
        self.consecutive_errors = 0
        self.last_error_msg = ""

    def is_valid(self) -> bool:
        """[V007.16] 检测 connection 是否真的健康

        修复: 之前版本只检查 'closed' / 'cannot operate' 错误,
        导致 disk I/O error / database is locked 都被误判为 valid,
        坏 connection 永久缓存, 反复报 disk I/O error.

        现在: 任何 sqlite3.Error (OperationalError, DatabaseError 等) 都视为 invalid.
        """
        try:
            cursor = self.connection.execute("SELECT 1")
            result = cursor.fetchone()
            if not result or result[0] != 1:
                logger.debug(
                    "[V007.16] is_valid: SELECT 1 returned unexpected result: %s", result
                )
                return False
            return True
        except sqlite3.Error as e:
            # 任何 sqlite3 错误 (包括 disk I/O error, database is locked) 都视为 invalid
            err_str = str(e).lower()
            logger.debug(
                "[V007.16] is_valid: connection INVALID, error: %s", err_str
            )
            # 同步标记 last_io_error, 让 reader() 知道要重建
            self.last_io_error = True
            self.last_error_msg = err_str
            return False
        except Exception as e:
            # 未知错误 (如 ProgrammingError) 也算 invalid
            logger.debug(
                "[V007.16] is_valid: unknown error: %s", str(e)
            )
            return False


class SQLiteConnectionPool:
    """读写分离连接池

    架构：
    - 1 个独占写连接（由 WriteQueue 管理）
    - N 个并发读连接（WAL 模式下读不阻塞写）
    - 使用线程本地存储避免多线程竞争

    使用方式：
        pool = SQLiteConnectionPool("/path/to/db.db", ConnectionConfig())
        pool.initialize()

        with pool.acquire_reader() as conn:
            conn.execute("SELECT ...")

        pool.shutdown()
    """

    def __init__(self, db_path: str, config: ConnectionConfig = None):
        self._db_path = db_path
        self._config = config or ConnectionConfig()
        self._readers: List[PooledConnection] = []
        self._available = deque()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._writer_conn: Optional[PooledConnection] = None
        self._initialized = False
        self._shutdown = False
        self._thread_local = threading.local()
        self._thread_connections: Dict[int, PooledConnection] = {}
        # [V007.37 BUG-FIX] PRAGMA journal_mode 幂等保护
        # 背景: yonaa 后端导出 Excel 场景, _create_connection 被频繁调用
        #       每次都执行 "PRAGMA journal_mode=WAL", 但 db 已是 WAL 模式,
        #       重复执行会触发 db 元数据写入 → disk I/O error (V007.37 HANDOFF §3)
        # 修法: db 级幂等标志, 只在首次创建时执行 journal_mode PRAGMA
        #       (其他 PRAGMA 是 per-connection, 不去重)
        self._journal_mode_applied: bool = False
        self._journal_mode_lock = threading.Lock()
        # [V007.38 BUG-FIX] PRAGMA auto_vacuum 幂等保护 (跟 journal_mode 同样原理)
        # auto_vacuum 是 db 持久化设置, 重复执行触发 db 头写 → disk I/O error
        # _create_connection 已引用 _auto_vacuum_applied 但 __init__ 没初始化,
        # 会触发 AttributeError; 这里补上初始化
        self._auto_vacuum_applied: bool = False

        self._stats = {
            "acquire_count": 0,
            "acquire_wait_count": 0,
            "acquire_timeout_count": 0,
            "release_count": 0,
            "create_count": 0,
            "recycle_count": 0,
            "error_count": 0,
            "total_wait_time": 0.0,
        }
        # [V007.38 BUG-FIX] task_scheduler 写后强制 PASSIVE checkpoint
        # 背景: task_scheduler 每 2 分钟写 task_executions, 让 mmap 视图失效,
        #       触发 20 个读连接 mark_error → 雪崩.
        # 修法: 暴露 force_passive_checkpoint 方法, task_scheduler 写后调用
        #       PASSIVE 模式不阻塞读, 但让 WAL 文件 checkpoint, 减少后续视图失效
        self._last_passive_checkpoint = 0.0
        # 线程锁: 保护 _last_passive_checkpoint 节流 + acquire_writer 调用
        # 避免 task_scheduler 后台线程 + Flask 请求线程并发
        self._checkpoint_lock = threading.RLock()
        # [V007.38 BUG-FIX] writer 连接获取锁
        # acquire_writer 之前没有锁, 多线程会同时拿同一个 writer 连接
        self._writer_lock = threading.RLock()

    @property
    def db_path(self) -> str:
        return self._db_path

    @property
    def config(self) -> ConnectionConfig:
        return self._config

    @property
    def active_reader_count(self) -> int:
        with self._lock:
            return sum(1 for pc in self._readers if pc.in_use)

    @property
    def idle_reader_count(self) -> int:
        with self._lock:
            return sum(1 for pc in self._readers if not pc.in_use)

    @property
    def total_reader_count(self) -> int:
        with self._lock:
            return len(self._readers)

    def initialize(self) -> bool:
        if self._initialized:
            return True

        try:
            if self._db_path != ":memory:":
                db_dir = os.path.dirname(self._db_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)
                _safe_cleanup_wal_shm(self._db_path)

            self._writer_conn = PooledConnection(
                connection=self._create_connection()
            )
            for _ in range(min(2, self._config.max_readers)):
                pc = self._create_pooled_connection()
                self._readers.append(pc)
                self._available.append(pc)

            self._initialized = True
            logger.info(
                "Connection pool initialized: db=%s, max_readers=%d",
                self._db_path, self._config.max_readers,
            )
            return True
        except Exception as e:
            logger.error("Connection pool init failed: %s", str(e))
            return False

    def force_passive_checkpoint(self) -> bool:
        """[V007.38] 强制 PASSIVE checkpoint (不阻塞读, 但推 WAL → db)

        Returns:
            True  - 成功执行 checkpoint
            False - 不需要 (距离上次 < 30s) 或失败

        线程安全: 用 _checkpoint_lock 保护节流 + 实际执行的原子性
        避免 task_scheduler 后台线程 + Flask 请求线程同时调
        """
        with self._checkpoint_lock:
            now = time.time()
            # 节流: 30s 内最多一次 (避免过度 checkpoint)
            if now - self._last_passive_checkpoint < 30.0:
                return False
            try:
                pc = self.acquire_writer()
                try:
                    # PASSIVE = 不等待写锁, 不阻塞, 仅推已 commit 的 WAL → db
                    # busy_timeout 30s 保证不被卡死
                    pc.connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    self._last_passive_checkpoint = now
                    logger.debug(
                        "[V007.38] force_passive_checkpoint done at %s",
                        time.strftime('%Y-%m-%d %H:%M:%S')
                    )
                    return True
                finally:
                    self.release_writer()
            except Exception as e:
                logger.warning("[V007.38] force_passive_checkpoint failed: %s", e)
                return False

    def shutdown(self):
        self._shutdown = True
        with self._condition:
            self._condition.notify_all()

        with self._lock:
            for pc in self._readers:
                try:
                    pc.connection.close()
                except Exception:
                    pass
            self._readers.clear()
            self._available.clear()

            if self._writer_conn:
                try:
                    self._writer_conn.connection.close()
                except Exception:
                    pass
                self._writer_conn = None

        self._initialized = False
        logger.info("Connection pool shutdown: db=%s", self._db_path)

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            timeout=self._config.db_timeout,
            isolation_level=None,
        )
        conn.row_factory = None
        if self._db_path != ":memory:":
            # [V007.37 BUG-FIX] PRAGMA journal_mode=WAL 幂等保护
            # db 已是 WAL 模式时, 重复 PRAGMA 触发 db 元数据写入 → disk I/O error
            # 只在首次 _create_connection 调用时执行 (db 级一次性)
            # 其他 PRAGMA (synchronous/foreign_keys/busy_timeout/auto_vacuum/mmap/cache)
            # 是 per-connection 配置, 每次都执行
            with self._journal_mode_lock:
                if not self._journal_mode_applied:
                    conn.execute("PRAGMA journal_mode=WAL")
                    self._journal_mode_applied = True
                # else: 跳过, db 已是 WAL 模式
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys = ON")
            # [V007.20 2026-07-06] busy_timeout: 5000 → 30000 (30s)
            # 背景: yonaa 1w+ annotation import 卡 40% (HANDOFF_V007_20_BUSY_TIMEOUT.md)
            #       WriteQueue 单写线程 + audit_async_queue + async_audit_writer 三条
            #       路径同时写 audit_logs, 撞锁频率高.
            #       busy_timeout=5000 (5s) 不够, 撞锁等不及.
            # 修法: 30s 等待, 让 write_queue retry 接管短撞锁 (< 30s)
            #       WriteQueue._write_loop 也加了 retry + backoff (V007.20 L2)
            conn.execute("PRAGMA busy_timeout = 30000")
            # [V007.38 BUG-FIX] PRAGMA auto_vacuum 幂等保护
            # auto_vacuum 跟 journal_mode 一样是 db 持久化设置, 重复执行触发 db 头写 → disk I/O error
            with self._journal_mode_lock:
                if not self._auto_vacuum_applied:
                    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
                    self._auto_vacuum_applied = True
                # else: 跳过, db 已是 INCREMENTAL 模式
            conn.execute(
                "PRAGMA wal_autocheckpoint = {0}".format(
                    self._config.wal_auto_checkpoint
                )
            )
            # [V007.35 2026-07-07] Windows/Linux 一致性
            # 背景: V007.34 disk I/O 只在 Linux 触发, Windows 不触发.
            #       SQLite 在两者上的默认 mmap_size 和 cache_size 可能不同,
            #       导致并发行为不一致.
            # 修法: 显式设定 mmap_size=256MB, cache_size=-2000 (2MB),
            #       消除平台差异, 让 Windows 开发环境尽量贴近 Linux.
            #
            # [V007.38 BUG-FIX] mmap_size 256MB → 64MB
            # 背景: V007.35 引入 mmap_size=256MB 后, 写操作 (task_scheduler)
            #       会让整个 96MB mmap 视图失效, 触发 20 个读连接全部 mark_error
            #       → 频繁 _create_connection → 重复 PRAGMA journal_mode → disk I/O error
            # 修法: 减小到 64MB (db 96MB 的 67%), 视图失效时重读代价从 96MB → 64MB
            #       减少 mark_error 频度, 缓解雪崩
            conn.execute("PRAGMA mmap_size = 67108864")  # 64MB (was 256MB)
            conn.execute("PRAGMA cache_size = -2000")
        return conn

    def _create_pooled_connection(self) -> PooledConnection:
        conn = self._create_connection()
        self._stats["create_count"] += 1
        return PooledConnection(connection=conn)

    def acquire_reader(self, timeout: float = None) -> PooledConnection:
        timeout = timeout if timeout is not None else self._config.acquire_timeout
        deadline = time.time() + timeout
        wait_start = time.time()

        with self._condition:
            self._stats["acquire_count"] += 1

            while True:
                if self._shutdown:
                    raise RuntimeError("Connection pool is shutdown")

                self._cleanup_idle_expired_unlocked()

                pc = self._try_get_available()
                if pc is not None:
                    pc.in_use = True
                    pc.touch()
                    wait_elapsed = time.time() - wait_start
                    self._stats["total_wait_time"] += wait_elapsed
                    if wait_elapsed > 0.01:
                        self._stats["acquire_wait_count"] += 1
                    return pc

                if len(self._readers) < self._config.max_readers:
                    pc = self._create_pooled_connection()
                    pc.in_use = True
                    pc.touch()
                    self._readers.append(pc)
                    wait_elapsed = time.time() - wait_start
                    self._stats["total_wait_time"] += wait_elapsed
                    return pc

                remaining = deadline - time.time()
                if remaining <= 0:
                    self._stats["acquire_timeout_count"] += 1
                    active = sum(1 for p in self._readers if p.in_use)
                    raise TimeoutError(
                        "Connection pool exhausted: max_readers={0}, active={1}".format(
                            self._config.max_readers, active
                        )
                    )

                self._condition.wait(timeout=min(remaining, 1.0))

    def release_reader(self, pc: PooledConnection):
        with self._condition:
            if pc.in_use:
                pc.in_use = False
                pc.last_used_at = time.time()
                self._stats["release_count"] += 1

                if pc.is_expired(self._config.max_lifetime):
                    self._recycle_connection_unlocked(pc)
                else:
                    self._available.append(pc)

                self._condition.notify()

    def acquire_writer(self) -> PooledConnection:
        # [V007.38 BUG-FIX] 加线程锁
        # 背景: acquire_writer 之前没有锁, 多线程 (WriteQueue 单线程 + force_passive_checkpoint
        #       后台线程) 同时调用会拿同一个 writer 连接, 事务边界破坏 → 不可预测写错误
        # 修法: 加 _writer_lock 保护, 但不要在持锁时做长操作 (PRAGMA checkpoint)
        with self._writer_lock:
            if not self._writer_conn:
                raise RuntimeError("Writer connection not initialized")
            if not self._writer_conn.is_valid():
                logger.warning("Writer connection invalid, reconnecting...")
                try:
                    self._writer_conn.connection.close()
                except Exception:
                    pass
                self._writer_conn = PooledConnection(
                    connection=self._create_connection()
                )
            self._writer_conn.in_use = True
            self._writer_conn.touch()
            return self._writer_conn

    def release_writer(self):
        # [V007.38 BUG-FIX] release_writer 也加锁, 跟 acquire_writer 配对
        with self._writer_lock:
            if self._writer_conn:
                self._writer_conn.in_use = False
                self._writer_conn.last_used_at = time.time()

    @contextmanager
    def reader(self, timeout: float = None):
        thread_id = threading.get_ident()

        with self._condition:
            if thread_id in self._thread_connections:
                pc = self._thread_connections[thread_id]
                # [V007.16] 修复: 不仅检查 is_valid, 还检查 last_io_error 和熔断
                # is_valid() 内部会同步设置 last_io_error, 但保险起见双重检查
                if (pc.is_valid()
                    and not pc.last_io_error
                    and pc.consecutive_errors < 3):
                    yield pc.connection
                    return
                else:
                    # [V007.16] 坏 connection, 关闭 + 移除 + 重建
                    if pc.last_io_error or pc.consecutive_errors >= 3:
                        logger.warning(
                            "[V007.16] reader: rebuilding bad connection "
                            "(last_io_error=%s, consecutive_errors=%d, last_err=%s)",
                            pc.last_io_error, pc.consecutive_errors, pc.last_error_msg
                        )
                    try:
                        pc.connection.close()
                    except Exception:
                        pass
                    del self._thread_connections[thread_id]
                    if pc in self._readers:
                        self._readers.remove(pc)
                    self._stats["recycle_count"] += 1

            pc = self._create_pooled_connection()
            pc.last_io_error = False
            pc.consecutive_errors = 0
            pc.last_error_msg = ""
            self._readers.append(pc)
            self._thread_connections[thread_id] = pc
            yield pc.connection
            return

    @contextmanager
    def writer(self):
        pc = self.acquire_writer()
        try:
            yield pc.connection
        finally:
            self.release_writer()

    def _try_get_available(self) -> Optional[PooledConnection]:
        while self._available:
            pc = self._available.popleft()
            # [V007.16] 修复: 增加 last_io_error + 熔断检查
            if (pc.is_valid()
                and not pc.is_expired(self._config.max_lifetime)
                and not pc.last_io_error
                and pc.consecutive_errors < 3):
                return pc
            else:
                self._recycle_connection_unlocked(pc)
        return None

    def _invalidate_reader(self, pc: PooledConnection):
        """使指定的读连接失效并移除"""
        with self._condition:
            try:
                pc.connection.close()
            except Exception:
                pass
            if pc in self._readers:
                self._readers.remove(pc)
            if pc in self._available:
                try:
                    self._available.remove(pc)
                except Exception:
                    pass
            self._stats["recycle_count"] += 1
            self._condition.notify()

    def _recycle_connection_unlocked(self, pc: PooledConnection):
        try:
            pc.connection.close()
        except Exception:
            pass
        if pc in self._readers:
            self._readers.remove(pc)
        self._stats["recycle_count"] += 1

    def _cleanup_idle_expired_unlocked(self):
        expired = [
            pc for pc in self._readers
            if not pc.in_use and pc.is_idle_expired(self._config.idle_timeout)
        ]
        for pc in expired:
            self._recycle_connection_unlocked(pc)

        min_keep = 1
        idle_not_expired = [
            pc for pc in self._readers
            if not pc.in_use and not pc.is_idle_expired(self._config.idle_timeout)
        ]
        while len(idle_not_expired) > min_keep:
            pc = idle_not_expired.pop()
            self._recycle_connection_unlocked(pc)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            stats = self._stats.copy()
        stats["active_readers"] = self.active_reader_count
        stats["idle_readers"] = self.idle_reader_count
        stats["total_readers"] = self.total_reader_count
        stats["max_readers"] = self._config.max_readers
        if stats["acquire_count"] > 0:
            stats["avg_wait_time_ms"] = (
                stats["total_wait_time"] / stats["acquire_count"] * 1000
            )
        else:
            stats["avg_wait_time_ms"] = 0.0
        return stats

    def health_check(self) -> Dict[str, Any]:
        result = {
            "status": "healthy",
            "checks": {},
        }

        writer_ok = False
        if self._writer_conn and self._writer_conn.is_valid():
            writer_ok = True
        result["checks"]["writer_connection"] = {
            "status": "pass" if writer_ok else "fail",
        }
        if not writer_ok:
            result["status"] = "unhealthy"

        active = self.active_reader_count
        max_r = self._config.max_readers
        pool_ok = active < max_r
        result["checks"]["reader_pool"] = {
            "status": "pass" if pool_ok else "warn",
            "active": active,
            "max": max_r,
            "utilization": "{0:.0%}".format(active / max_r if max_r > 0 else 0),
        }

        if self._db_path != ":memory:" and os.path.exists(self._db_path):
            db_size = os.path.getsize(self._db_path)
            wal_path = self._db_path + "-wal"
            wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
            result["checks"]["database_files"] = {
                "status": "pass",
                "db_size_bytes": db_size,
                "wal_size_bytes": wal_size,
            }

        return result
