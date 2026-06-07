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

    def touch(self):
        self.last_used_at = time.time()
        self.usage_count += 1

    def is_expired(self, max_lifetime: float) -> bool:
        return (time.time() - self.created_at) > max_lifetime

    def is_idle_expired(self, idle_timeout: float) -> bool:
        return (not self.in_use) and ((time.time() - self.last_used_at) > idle_timeout)

    def is_valid(self) -> bool:
        try:
            self.connection.execute("SELECT 1")
            return True
        except Exception as e:
            err_str = str(e).lower()
            if "closed" in err_str or "cannot operate" in err_str:
                return False
            return True


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
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
            conn.execute(
                "PRAGMA wal_autocheckpoint = {0}".format(
                    self._config.wal_auto_checkpoint
                )
            )
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
        if self._writer_conn:
            self._writer_conn.in_use = False
            self._writer_conn.last_used_at = time.time()

    @contextmanager
    def reader(self, timeout: float = None):
        thread_id = threading.get_ident()
        
        with self._condition:
            if thread_id in self._thread_connections:
                pc = self._thread_connections[thread_id]
                if pc.is_valid():
                    yield pc.connection
                    return
                else:
                    try:
                        pc.connection.close()
                    except Exception:
                        pass
                    del self._thread_connections[thread_id]
                    if pc in self._readers:
                        self._readers.remove(pc)
            
            pc = self._create_pooled_connection()
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
            if pc.is_valid() and not pc.is_expired(self._config.max_lifetime):
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
