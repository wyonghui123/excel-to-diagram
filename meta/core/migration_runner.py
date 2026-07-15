# -*- coding: utf-8 -*-
"""
数据库迁移运行器 (P0 增强)

提供数据库迁移脚本的执行和管理功能：
- 执行 SQL / Python 迁移脚本
- 记录迁移历史 + SHA256 checksum 验证
- 支持可重复执行（幂等性）
- 审计日志 (logs/migrations.log)
- 多实例并发协调 (migration_lock 表 + heartbeat 僵尸锁检测)
- 执行超时保护 (300s, Unix SIGALRM)
- 自动备份 DB (保留最近 5 个)
- P1: prerequisites + verify() + rollback() + schema_migrations 6 字段增强

增强历史:
  v1.0: 基础框架 (仅 .sql, 无 checksum/lock/backup/audit)
  v1.1 (P0): 支持 .py + checksum + migration_lock + 超时 + 备份 + 审计日志
  v1.2 (P1): schema_migrations 6 字段增强 + prerequisites + verify + rollback + migration status API
"""

import os
import sys
import time
import socket
import shutil
import hashlib
import logging
import importlib.util
import inspect
import threading
from pathlib import Path
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 单个 migration 最大执行时间 (秒)
MIGRATION_TIMEOUT_SECONDS = 300

# migration_lock 僵尸锁检测阈值 (秒)
MIGRATION_LOCK_ZOMBIE_THRESHOLD = 60

# heartbeat 更新间隔 (秒)
MIGRATION_LOCK_HEARTBEAT_INTERVAL = 10

# 备份保留数量
BACKUP_RETENTION = 5

MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name VARCHAR(255) NOT NULL UNIQUE,
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checksum VARCHAR(64),
    executed_by VARCHAR(64),
    execution_time_ms INTEGER,
    backup_path VARCHAR(512),
    status VARCHAR(16) DEFAULT 'SUCCESS',
    error_message TEXT,
    environment VARCHAR(16)
);
"""

# [P1] schema_migrations 表 6 字段增强 - 给历史 DB 补齐时用的 ALTER TABLE ADD COLUMN.
# 如果表已存在但缺字段, ensure_migrations_table() 启动时会逐个 ALTER ADD.
# 注意: SQLite 的 ALTER TABLE ADD COLUMN 在 ROLLBACK 后列仍会保留 (SQLite 限制).
P1_COLUMNS = (
    ("executed_by", "VARCHAR(64)"),
    ("execution_time_ms", "INTEGER"),
    ("backup_path", "VARCHAR(512)"),
    ("status", "VARCHAR(16) DEFAULT 'SUCCESS'"),
    ("error_message", "TEXT"),
    ("environment", "VARCHAR(16)"),
)

MIGRATION_LOCK_TABLE = """
CREATE TABLE IF NOT EXISTS migration_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    locked_by VARCHAR(64),
    locked_at TIMESTAMP,
    heartbeat_at TIMESTAMP
);
"""


class MigrationRunner:
    """数据库迁移运行器"""

    def __init__(self, data_source, migrations_dir: str = None):
        """
        初始化迁移运行器

        Args:
            data_source: 数据源实例
            migrations_dir: 迁移脚本目录路径
        """
        self.data_source = data_source
        self.migrations_dir = migrations_dir or self._get_default_migrations_dir()
        self._heartbeat_timer = None
        self._lock_instance_id = None

    def _get_default_migrations_dir(self) -> str:
        """获取默认迁移目录路径"""
        current_dir = Path(__file__).parent.parent
        migrations_dir = current_dir / "migrations"
        if migrations_dir.exists():
            return str(migrations_dir)
        return str(current_dir / "core" / "migrations")

    # ------------------------------------------------------------------
    # 表初始化
    # ------------------------------------------------------------------

    def ensure_migrations_table(self):
        """确保迁移记录表 + migration_lock 表存在"""
        self.data_source.execute(MIGRATIONS_TABLE)
        if not self.data_source.in_transaction:
            self.data_source.commit()
        self.data_source.execute(MIGRATION_LOCK_TABLE)
        if not self.data_source.in_transaction:
            self.data_source.commit()
        # [P1] schema_migrations 6 字段增强 - 给历史 DB 补齐
        self._ensure_p1_columns()
        logger.info("Migration tracking table + lock table ensured")

    def _ensure_p1_columns(self):
        """[P1] 给历史 schema_migrations 表 ALTER ADD 6 个新字段 (幂等).

        跳过已存在的字段 (检查 sqlite_master 列名).
        """
        try:
            # 读现有列名 (cursor.description 在某些 adapter 上不可用, 用 pragma table_info)
            rows = self.data_source.execute("PRAGMA table_info(schema_migrations)").fetchall()
            existing = {r[1] for r in rows} if rows else set()
            for col_name, col_def in P1_COLUMNS:
                if col_name in existing:
                    continue
                sql = f"ALTER TABLE schema_migrations ADD COLUMN {col_name} {col_def}"
                try:
                    self.data_source.execute(sql)
                    if not self.data_source.in_transaction:
                        self.data_source.commit()
                    logger.info("[P1] Added column schema_migrations.%s", col_name)
                except Exception as e:
                    # ALTER ADD COLUMN 在 ROLLBACK 后列仍保留 (SQLite 限制),
                    # 但 column 已存在时报 'duplicate column name', 此时 OK
                    err_msg = str(e).lower()
                    if 'duplicate' in err_msg or 'already exists' in err_msg:
                        logger.debug("[P1] Column %s already exists (concurrent add?)", col_name)
                    else:
                        logger.warning("[P1] Failed to add column %s: %s", col_name, e)
        except Exception as e:
            logger.warning("[P1] _ensure_p1_columns failed (table may be new): %s", e)

    # ------------------------------------------------------------------
    # 查询 / 记录
    # ------------------------------------------------------------------

    def get_executed_migrations(self) -> List[str]:
        """获取已执行的迁移列表"""
        sql = "SELECT migration_name FROM schema_migrations ORDER BY id"
        cursor = self.data_source.execute(sql)
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []

    def is_migration_executed(self, migration_name: str) -> bool:
        """检查迁移是否已执行"""
        sql = "SELECT 1 FROM schema_migrations WHERE migration_name = ?"
        cursor = self.data_source.execute(sql, (migration_name,))
        return cursor.fetchone() is not None

    def _get_recorded_checksum(self, migration_name: str) -> Optional[str]:
        """获取已记录的 checksum"""
        sql = "SELECT checksum FROM schema_migrations WHERE migration_name = ?"
        cursor = self.data_source.execute(sql, (migration_name,))
        row = cursor.fetchone()
        return row[0] if row else None

    def record_migration(self, migration_name: str, checksum: str = None,
                         executed_by: Optional[str] = None,
                         execution_time_ms: Optional[int] = None,
                         backup_path: Optional[str] = None,
                         status: str = "SUCCESS",
                         error_message: Optional[str] = None,
                         environment: Optional[str] = None):
        """记录迁移执行 (P1: 支持 6 个新字段)

        Args:
            migration_name: 迁移名
            checksum: SHA256 文件 checksum
            executed_by: 执行人/工具 ('deploy.sh' / 'server.py' / 'manual')
            execution_time_ms: 执行耗时毫秒
            backup_path: 备份 DB 文件路径
            status: SUCCESS / FAILED / ROLLED_BACK
            error_message: 失败原因
            environment: staging / prod / dev
        """
        sql = (
            "INSERT INTO schema_migrations "
            "(migration_name, checksum, executed_by, execution_time_ms, "
            " backup_path, status, error_message, environment) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self.data_source.execute(
            sql,
            (migration_name, checksum, executed_by, execution_time_ms,
             backup_path, status, error_message, environment),
        )
        if not self.data_source.in_transaction:
            self.data_source.commit()
        logger.info("Migration recorded: %s (status=%s)", migration_name, status)

    # ------------------------------------------------------------------
    # Checksum (SHA256)
    # ------------------------------------------------------------------

    def _compute_checksum(self, migration_name: str) -> Optional[str]:
        """计算 migration 文件的 SHA256 checksum

        与 tools/backfill_schema_migrations.py 的 compute_checksum 算法保持一致.
        """
        file_path = os.path.join(self.migrations_dir, migration_name)
        if not os.path.exists(file_path):
            return None
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()  # 64 字符十六进制

    # ------------------------------------------------------------------
    # DB 路径 / 备份
    # ------------------------------------------------------------------

    def _get_db_path(self) -> Path:
        """从 data_source 获取 DB 文件路径"""
        # SQLDataSource.connect() 设置 self._db_path
        db_path = getattr(self.data_source, '_db_path', None)
        if db_path:
            return Path(db_path)
        # fallback: 从 migrations_dir 推断 (meta/migrations -> meta/architecture.db)
        return Path(self.migrations_dir).parent / "architecture.db"

    def _backup_db(self) -> bool:
        """备份 DB 到 .bak.YYYYMMDD_HHMMSS, 保留最近 BACKUP_RETENTION 个"""
        db_path = self._get_db_path()
        if not db_path.exists():
            return True  # 新 DB, 无需备份

        # 检查磁盘空间 (至少留 DB 大小 2x)
        db_size = db_path.stat().st_size
        try:
            statvfs = os.statvfs(str(db_path.parent))
            free_space = statvfs.f_bavail * statvfs.f_bsize
            if free_space < db_size * 2:
                logger.error(
                    "Insufficient disk space: free=%dMB, db=%dMB",
                    free_space // 1024 // 1024, db_size // 1024 // 1024
                )
                return False
        except (OSError, AttributeError):
            # Windows: os.statvfs 不可用, 跳过磁盘检查
            logger.debug("statvfs unavailable (Windows?), skipping disk space check")

        bak_path = str(db_path) + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(str(db_path), bak_path)
        logger.info("DB backed up to %s", bak_path)

        # 清理旧备份: 只保留最近 BACKUP_RETENTION 个
        # [FIX 2026-07-15] Python 3.14 起 Path.glob() 不再支持绝对路径模式,
        # 改用文件名前缀 + 相对模式, 然后用前缀过滤掉无关文件
        bak_filename_prefix = Path(str(db_path)).name + ".bak."
        old_baks = [
            p for p in Path(db_path.parent).glob(bak_filename_prefix + "*")
            if p.name.startswith(bak_filename_prefix)
        ]
        old_baks.sort(key=lambda p: p.name)
        if len(old_baks) > BACKUP_RETENTION:
            for old_bak in old_baks[:-BACKUP_RETENTION]:
                old_bak.unlink()
                logger.info("Cleaned old backup: %s", old_bak)

        return True

    # ------------------------------------------------------------------
    # 审计日志
    # ------------------------------------------------------------------

    def _get_audit_log_path(self) -> Path:
        """获取审计日志文件路径 (logs/migrations.log)"""
        db_path = self._get_db_path()
        # db 在 meta/architecture.db, logs 在 项目根/logs/
        logs_dir = db_path.parent.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir / "migrations.log"

    def _log_audit(self, migration_name: str, status: str,
                   checksum: Optional[str] = None, error: Optional[str] = None,
                   elapsed_ms: Optional[int] = None):
        """写审计日志到 logs/migrations.log

        Args:
            migration_name: migration 文件名
            status: SUCCESS / FAILED / SKIPPED
            checksum: SHA256 (成功时)
            error: 错误信息 (失败时)
            elapsed_ms: 执行耗时 (毫秒)
        """
        log_path = self._get_audit_log_path()
        instance_id = f"{socket.gethostname()}-{os.getpid()}"
        env = os.environ.get("MIGRATION_ENV", "unknown")
        timestamp = datetime.now().isoformat()
        cs_short = checksum[:16] + "..." if checksum else "NULL"
        line = (
            f"[{timestamp}] [{env}] [{instance_id}] "
            f"{migration_name} | {status} | checksum={cs_short} | "
            f"elapsed={elapsed_ms}ms"
        )
        if error:
            line += f" | error={error}"
        line += "\n"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.warning("Failed to write audit log: %s", e)

    # ------------------------------------------------------------------
    # Migration Lock (advisory lock + heartbeat)
    # ------------------------------------------------------------------

    def acquire_migration_lock(self, timeout_seconds: int = 60) -> bool:
        """获取 migration 锁. 超时返回 False.

        策略:
        1. INSERT (not REPLACE), 抢锁 - PRIMARY KEY 唯一约束保证互斥
        2. 抢到后启动 heartbeat, 跑完释放
        3. 抢不到: 轮询 heartbeat_at, 如果 > 60s 没更新 → 视为僵尸锁, 强制接管
        """
        self._lock_instance_id = f"{socket.gethostname()}-{os.getpid()}"
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            try:
                self.data_source.execute(
                    "INSERT INTO migration_lock (id, locked_by, locked_at, heartbeat_at) "
                    "VALUES (1, ?, ?, ?)",
                    (self._lock_instance_id,
                     datetime.now().isoformat(),
                     datetime.now().isoformat())
                )
                if not self.data_source.in_transaction:
                    self.data_source.commit()
                logger.info("[MigrationLock] Acquired by %s", self._lock_instance_id)
                self._start_heartbeat()
                return True
            except Exception:
                # INSERT 失败 = 锁已被持有, 检查是否僵尸
                try:
                    if not self.data_source.in_transaction:
                        self.data_source.commit()
                except Exception:
                    pass
                row = None
                try:
                    cursor = self.data_source.execute(
                        "SELECT locked_by, heartbeat_at FROM migration_lock WHERE id = 1"
                    )
                    row = cursor.fetchone()
                except Exception:
                    pass

                if row:
                    locked_by, heartbeat_str = row
                    is_zombie = False
                    try:
                        heartbeat = datetime.fromisoformat(heartbeat_str)
                        if (datetime.now() - heartbeat).total_seconds() > MIGRATION_LOCK_ZOMBIE_THRESHOLD:
                            is_zombie = True
                    except (ValueError, TypeError):
                        is_zombie = True  # 无效 heartbeat, 视为僵尸

                    if is_zombie:
                        logger.warning(
                            "[MigrationLock] Zombie lock by %s (heartbeat=%s), "
                            "force taking over",
                            locked_by, heartbeat_str
                        )
                        try:
                            self.data_source.execute(
                                "DELETE FROM migration_lock WHERE id = 1"
                            )
                            if not self.data_source.in_transaction:
                                self.data_source.commit()
                        except Exception:
                            pass
                        continue  # 重试 INSERT

                time.sleep(2)  # 等 2s 再试

        logger.warning("[MigrationLock] Failed to acquire lock within %ds", timeout_seconds)
        return False

    def _start_heartbeat(self):
        """启动 heartbeat 定时器, 每 10s 更新 heartbeat_at"""
        self._heartbeat_timer = threading.Timer(
            MIGRATION_LOCK_HEARTBEAT_INTERVAL, self._heartbeat_loop
        )
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    def _heartbeat_loop(self):
        """heartbeat 循环 (daemon 线程)"""
        if self._lock_instance_id is None:
            return
        try:
            self.data_source.execute(
                "UPDATE migration_lock SET heartbeat_at = ? WHERE locked_by = ?",
                (datetime.now().isoformat(), self._lock_instance_id)
            )
            if not self.data_source.in_transaction:
                self.data_source.commit()
        except Exception as e:
            logger.warning("[MigrationLock] Heartbeat failed: %s", e)
        # 继续下一轮
        self._heartbeat_timer = threading.Timer(
            MIGRATION_LOCK_HEARTBEAT_INTERVAL, self._heartbeat_loop
        )
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    def _stop_heartbeat(self):
        """停止 heartbeat 定时器"""
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    def release_migration_lock(self):
        """释放锁"""
        self._stop_heartbeat()
        try:
            self.data_source.execute("DELETE FROM migration_lock WHERE id = 1")
            if not self.data_source.in_transaction:
                self.data_source.commit()
            logger.info("[MigrationLock] Released by %s", self._lock_instance_id)
        except Exception as e:
            logger.warning("[MigrationLock] Release failed: %s", e)
        self._lock_instance_id = None

    # ------------------------------------------------------------------
    # 执行超时
    # ------------------------------------------------------------------

    def _execute_with_timeout(self, func, timeout: int = MIGRATION_TIMEOUT_SECONDS):
        """带超时执行 (Unix: SIGALRM; Windows: 仅记录, 不强制)"""
        if os.name == 'posix':
            import signal

            def handler(signum, frame):
                raise TimeoutError(f"Migration exceeded {timeout}s")
            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.alarm(timeout)
            try:
                return func()
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Windows: 不强制超时, 只记录
            start = time.time()
            result = func()
            elapsed = time.time() - start
            if elapsed > timeout:
                logger.warning(
                    "Migration took %.1fs (exceeds %ds soft limit)",
                    elapsed, timeout
                )
            return result

    # ------------------------------------------------------------------
    # SQL 执行
    # ------------------------------------------------------------------

    # 幂等迁移容忍的错误模式 (大小写不敏感子串匹配)
    # 迁移文件多次跑或被部分应用后, 这些错误表示 schema 已经是目标状态
    _IDEMPOTENT_ERRORS = (
        "duplicate column",       # ALTER TABLE ADD COLUMN
        "duplicate column name",  # SQLite 同上
        "already exists",         # CREATE TABLE/INDEX
        "duplicate index name",   # CREATE INDEX
        "index already exists",   # 同上
        "table already exists",   # CREATE TABLE
        "no such column",         # DROP COLUMN 已不存在
        "no such index",          # DROP INDEX 已不存在
    )

    def _is_idempotent_error(self, err_msg: str) -> bool:
        """判断错误是否属于幂等迁移可容忍的"""
        low = err_msg.lower()
        return any(pat in low for pat in self._IDEMPOTENT_ERRORS)

    def execute_sql_file(self, sql_file_path: str) -> bool:
        """
        执行 SQL 文件

        幂等策略: 对于 ALTER TABLE ADD COLUMN / CREATE INDEX 重复错误自动跳过.
        迁移文件应该写成可重复跑的 (IF NOT EXISTS / 重复 ALTER 也兼容),
        这样在 staging/prod 已经手工应用过部分 schema 时也能通过.

        策略:
          1. 优先用 sqlite3.Connection.executescript() 一次性跑全部 (它能处理 trigger 块 BEGIN/END)
          2. 捕获 sqlite3 错, 如果是 idempotent 错误, 重新走分语句模式跳过该语句
          3. 仍然错就 fail

        Args:
            sql_file_path: SQL 文件路径

        Returns:
            是否执行成功
        """
        try:
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            # 尝试 1: 用 executescript 一次性执行 (能处理 trigger BEGIN/END 块)
            try:
                # 获取底层 sqlite3 连接 (绕开 DataSource 包装)
                conn = self._get_raw_sqlite_connection()
                conn.executescript(sql_content)
                conn.commit()
                logger.info("SQL file executed successfully (executescript): %s", sql_file_path)
                return True
            except Exception as script_err:
                err_str = str(script_err)
                if not self._is_idempotent_error(err_str):
                    # 非幂等错误, 整文件失败
                    logger.error("Failed to execute SQL file %s: %s", sql_file_path, err_str[:300])
                    return False
                # idempotent 错: 走分语句模式, 跳过重复列
                logger.info(
                    "executescript hit idempotent error (%s), falling back to per-statement mode",
                    err_str[:200],
                )

            # 尝试 2: 分语句模式 (用于 idempotent 错误容错)
            statements = self._parse_sql_statements(sql_content)

            for statement in statements:
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    try:
                        self.data_source.execute(statement)
                    except Exception as stmt_err:
                        if self._is_idempotent_error(str(stmt_err)):
                            logger.info(
                                "SQL statement skipped (idempotent): %s... err=%s",
                                statement[:60].replace('\n', ' '),
                                str(stmt_err)[:100],
                            )
                            continue
                        raise

            if not self.data_source.in_transaction:
                self.data_source.commit()

            logger.info("SQL file executed successfully (per-statement): %s", sql_file_path)
            return True

        except Exception as e:
            logger.error("Failed to execute SQL file %s: %s", sql_file_path, str(e))
            return False

    def _get_raw_sqlite_connection(self) -> "sqlite3.Connection":
        """获取底层 sqlite3 连接 (用于 executescript 处理 trigger BEGIN/END 块)

        走 DataSource.get_connection() 会返回带事务管理的连接;
        直接读 self.data_source.connection 拿到 sqlite3.Connection
        """
        # 尝试常见属性名
        for attr in ('_conn', 'connection', 'conn', '_connection'):
            obj = getattr(self.data_source, attr, None)
            if obj is not None and hasattr(obj, 'executescript'):
                return obj
        # fallback: 从 datasource 拿 db_path 自己连接
        # 这种情况在生产环境是异常路径, 用临时连接
        import sqlite3
        db_path = getattr(self.data_source, 'database', None) or getattr(self.data_source, 'db_path', None)
        if db_path and os.path.exists(db_path):
            return sqlite3.connect(db_path)
        raise RuntimeError("Cannot get raw sqlite3 connection from DataSource")

    def _parse_sql_statements(self, sql_content: str) -> List[str]:
        """将 SQL 文件内容分割为独立的语句"""
        statements = []
        current_statement = []

        for line in sql_content.split('\n'):
            line = line.strip()

            if line.startswith('--'):
                continue

            current_statement.append(line)

            if line.endswith(';'):
                stmt = '\n'.join(current_statement)
                if stmt.strip():
                    statements.append(stmt)
                current_statement = []

        if current_statement:
            stmt = '\n'.join(current_statement)
            if stmt.strip():
                statements.append(stmt)

        return statements

    # ------------------------------------------------------------------
    # Python migration 执行
    # ------------------------------------------------------------------

    def _execute_py_migration(self, migration_name: str) -> Optional[bool]:
        """执行 .py migration, 统一调用 migrate(db_path, skip_backup)

        Returns:
            True = 成功, False = 失败, None = 跳过 (签名不兼容)
        """
        file_path = os.path.join(self.migrations_dir, migration_name)

        # 动态 import
        module_name = migration_name[:-3]  # 去掉 .py
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error("Failed to load migration %s: %s", migration_name, e)
            return False

        if not hasattr(module, 'migrate'):
            logger.warning(
                "Migration %s has no migrate() function, skipping", migration_name
            )
            return None

        # 检查签名兼容性
        try:
            sig = inspect.signature(module.migrate)
            params = list(sig.parameters.keys())
            # 期望: migrate(db_path, skip_backup=False) 或 migrate(db_path)
            if not params or params[0] not in ('db_path', 'conn', 'database'):
                logger.warning(
                    "Migration %s has incompatible migrate() signature %s, skipping",
                    migration_name, sig
                )
                return None
        except (ValueError, TypeError):
            # 无法检查签名, 尝试调用
            pass

        db_path = self._get_db_path()
        try:
            # runner 已备份, 跳过 migration 内部备份
            result = module.migrate(db_path, skip_backup=True)
            if result is None:
                # 旧签名 migrate() 无返回值, 视为成功
                return True
            return bool(result)
        except TypeError as e:
            # 签名不兼容 (如 migrate() 无参), 跳过
            logger.warning(
                "Migration %s signature incompatible (%s), skipping",
                migration_name, e
            )
            return None
        except Exception as e:
            logger.error(
                "Migration %s raised: %s", migration_name, e, exc_info=True
            )
            return False

    # ------------------------------------------------------------------
    # 单个 migration 执行 (增强: checksum + backup + audit)
    # ------------------------------------------------------------------

    def run_migration(self, migration_name: str) -> bool:
        """
        执行单个迁移

        增强 (P0):
        - checksum 验证 (已执行时对比 checksum)
        - DB 备份 (执行前)
        - 支持 .sql 和 .py
        - 审计日志

        Args:
            migration_name: 迁移名称（文件名）

        Returns:
            是否执行成功 (True = 成功执行或已执行, False = 失败)
        """
        # 1. 幂等检查
        if self.is_migration_executed(migration_name):
            # checksum 验证
            recorded_checksum = self._get_recorded_checksum(migration_name)
            current_checksum = self._compute_checksum(migration_name)
            if recorded_checksum and current_checksum and recorded_checksum != current_checksum:
                logger.error(
                    "Migration %s checksum mismatch! recorded=%s, current=%s",
                    migration_name, recorded_checksum[:16], current_checksum[:16]
                )
                self._log_audit(migration_name, "FAILED",
                                error="checksum mismatch: file was modified after execution")
                return False
            logger.debug("Migration already executed: %s (checksum OK)", migration_name)
            return True

        # 2. 文件存在检查
        file_path = os.path.join(self.migrations_dir, migration_name)
        if not os.path.exists(file_path):
            logger.error("Migration file not found: %s", file_path)
            return False

        # 2.5 [P1] prerequisites 检查 (失败则跳过, 不阻断 - 让运维决定)
        try:
            ok, missing = self.check_prerequisites(migration_name)
            if not ok:
                logger.warning(
                    "[P1] Migration %s prerequisites not met: %s. Skipping.",
                    migration_name, missing,
                )
                self._log_audit(migration_name, "SKIPPED",
                                error=f"prerequisites missing: {missing}")
                return True  # 跳过, 不阻断 (让运维决定)
        except Exception as e:
            logger.debug("[P1] check_prerequisites error: %s", e)

        # 3. 备份 DB
        if not self._backup_db():
            logger.error("Backup failed, abort migration: %s", migration_name)
            self._log_audit(migration_name, "FAILED", error="backup failed")
            return False

        # 4. 执行 (带超时)
        start_time = time.time()
        success = None

        def _do_execute():
            nonlocal success
            if migration_name.endswith('.sql'):
                success = self.execute_sql_file(file_path)
            elif migration_name.endswith('.py'):
                success = self._execute_py_migration(migration_name)
            else:
                logger.warning("Unknown migration type: %s", migration_name)
                success = None

        try:
            self._execute_with_timeout(_do_execute)
        except TimeoutError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error("Migration %s timed out: %s", migration_name, e)
            self._log_audit(migration_name, "FAILED",
                            error=f"timeout: {e}", elapsed_ms=elapsed_ms)
            return False

        elapsed_ms = int((time.time() - start_time) * 1000)

        # 5. 处理结果
        if success is True:
            checksum = self._compute_checksum(migration_name)
            backup_path = self._get_latest_backup_path(migration_name)
            environment = os.environ.get("MIGRATION_ENV", "unknown")
            executed_by = os.environ.get("MIGRATION_EXECUTED_BY", "deploy.sh")

            # [P1] verify() 调用 (推荐, 非强制). 只警告不阻断.
            verify_status = "NOT_IMPLEMENTED"
            try:
                ran, ok, msg = self.verify_migration(migration_name)
                verify_status = "OK" if ok else "FAIL"
                if ran and not ok:
                    logger.warning("[P1] verify() reported problem: %s", msg)
                    verify_status = f"FAIL: {msg}"
            except Exception as e:
                logger.debug("[P1] verify_migration error: %s", e)

            try:
                self.record_migration(
                    migration_name, checksum,
                    executed_by=executed_by,
                    execution_time_ms=elapsed_ms,
                    backup_path=backup_path,
                    status="SUCCESS",
                    environment=environment,
                )
            except Exception as e:
                # [P1] 新字段未生效 (P0 阶段数据库无 P1 列) 时降级到 4 字段
                logger.debug("[P1] record_migration full fields failed (%s), fallback to P0 fields", e)
                self.data_source.execute(
                    "INSERT INTO schema_migrations (migration_name, checksum) VALUES (?, ?)",
                    (migration_name, checksum),
                )
                if not self.data_source.in_transaction:
                    self.data_source.commit()
            self._log_audit(migration_name, "SUCCESS",
                            checksum=checksum, elapsed_ms=elapsed_ms,
                            error=f"verify={verify_status}")
            return True
        elif success is None:
            # 跳过 (签名不兼容), 不记录, 不算失败
            self._log_audit(migration_name, "SKIPPED",
                            error="incompatible signature", elapsed_ms=elapsed_ms)
            logger.info("Migration %s skipped (incompatible signature)", migration_name)
            return True  # 不阻断后续 migration
        else:
            # [P1] 失败时记录 FAILED + error_message
            error_msg = "migration execution returned False"
            try:
                environment = os.environ.get("MIGRATION_ENV", "unknown")
                executed_by = os.environ.get("MIGRATION_EXECUTED_BY", "deploy.sh")
                self.record_migration(
                    migration_name, self._compute_checksum(migration_name),
                    executed_by=executed_by,
                    execution_time_ms=elapsed_ms,
                    status="FAILED",
                    error_message=error_msg,
                    environment=environment,
                )
            except Exception:
                # 降级: 只记 name
                logger.debug("[P1] record FAILED with full fields failed, skipping record")
            self._log_audit(migration_name, "FAILED",
                            error=error_msg, elapsed_ms=elapsed_ms)
            return False

    def _get_latest_backup_path(self, migration_name: str) -> Optional[str]:
        """[P1] 返回当前 migration 关联的最新备份路径 (若有)."""
        try:
            db_path = self._get_db_path()
            baks = sorted(
                [p for p in Path(db_path.parent).glob(Path(str(db_path)).name + ".bak.*")],
                key=lambda p: p.name, reverse=True,
            )
            if baks:
                return str(baks[0])
        except Exception as e:
            logger.debug("[P1] _get_latest_backup_path failed: %s", e)
        return None

    # ------------------------------------------------------------------
    # [P1] prerequisites / verify / rollback
    # ------------------------------------------------------------------

    def _load_migration_module(self, migration_name: str):
        """[P1] 动态 import 一个 .py migration 文件, 返回 module 对象.

        Returns:
            module 对象; 失败返回 None
        """
        if not migration_name.endswith('.py'):
            return None
        file_path = Path(self.migrations_dir) / migration_name
        if not file_path.exists():
            return None
        spec = importlib.util.spec_from_file_location(
            f"_migration_{migration_name.replace('.', '_').replace('/', '_')}",
            str(file_path),
        )
        if spec is None or spec.loader is None:
            return None
        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            logger.debug("[P1] Failed to load module %s: %s", migration_name, e)
            return None

    def check_prerequisites(self, migration_name: str) -> tuple:
        """[P1] 检查 migration 的 prerequisites 是否都已执行.

        Returns:
            (ok: bool, missing: list[str])
        """
        module = self._load_migration_module(migration_name)
        if module is None or not hasattr(module, 'prerequisites'):
            return True, []
        try:
            prereqs = module.prerequisites()
        except Exception as e:
            logger.warning("[P1] prerequisites() raised for %s: %s", migration_name, e)
            return True, []
        missing = []
        for p in prereqs or []:
            if not self.is_migration_executed(p):
                missing.append(p)
        return (len(missing) == 0), missing

    def verify_migration(self, migration_name: str) -> tuple:
        """[P1] 调用 migration 的 verify() 函数 (推荐, 非强制).

        Returns:
            (ran: bool, ok: bool, msg: str)
        """
        module = self._load_migration_module(migration_name)
        if module is None or not hasattr(module, 'verify'):
            return False, True, "verify() not implemented (skip)"
        try:
            db_path = self._get_db_path()
            ok = module.verify(db_path)
            return True, bool(ok), "verify() executed"
        except Exception as e:
            return True, False, f"verify() exception: {e}"

    def rollback_migration(self, migration_name: str,
                           backup_path: Optional[str] = None,
                           force_backup: bool = False) -> bool:
        """[P1] 回滚 migration. 3 策略优先级:
        1. 如果 migration 提供 rollback() 函数 → 调用 (推荐)
        2. 如果 force_backup / backup_path / 表内有 backup_path → 从备份恢复 (危险)
        3. 都没有 → 拒绝, 提示手动处理
        """
        if not self.is_migration_executed(migration_name):
            logger.warning("Migration %s not executed, nothing to rollback", migration_name)
            return True

        # 策略 1: 调用 rollback() 函数
        module = self._load_migration_module(migration_name)
        if module is not None and hasattr(module, 'rollback'):
            logger.info("[Rollback] Strategy 1: Calling %s.rollback()", migration_name)
            try:
                db_path = self._get_db_path()
                ok = module.rollback(db_path)
                if ok:
                    self._mark_rolled_back(migration_name)
                    self._log_audit(migration_name, "ROLLED_BACK",
                                    error=f"strategy=rollback_func backup=None")
                    return True
                logger.warning("[Rollback] rollback() returned False, fallback to backup")
            except Exception as e:
                logger.error("[Rollback] rollback() failed: %s, fallback to backup", e)

        # 策略 2: 从备份恢复
        if not backup_path:
            rows = self.data_source.execute(
                "SELECT backup_path FROM schema_migrations WHERE migration_name = ?",
                (migration_name,),
            ).fetchall()
            if rows and rows[0][0]:
                backup_path = rows[0][0]
        if backup_path and os.path.exists(backup_path):
            if not force_backup:
                logger.error(
                    "[Rollback] backup_path=%s but force_backup=False. "
                    "Refusing to restore (use force_backup=True).",
                    backup_path,
                )
                return False
            logger.warning(
                "[Rollback] Strategy 2: Restoring DB from %s. "
                "WARNING: ALL changes after %s will be lost!",
                backup_path, migration_name,
            )
            db_path = self._get_db_path()
            shutil.copy2(backup_path, str(db_path))
            # 从 schema_migrations 删除该 migration 及之后的所有记录
            try:
                self.data_source.execute(
                    "DELETE FROM schema_migrations WHERE id >= "
                    "(SELECT id FROM schema_migrations WHERE migration_name = ?)",
                    (migration_name,),
                )
                if not self.data_source.in_transaction:
                    self.data_source.commit()
            except Exception as e:
                logger.error("[Rollback] Failed to delete schema_migrations rows: %s", e)
            self._log_audit(migration_name, "ROLLED_BACK_VIA_BACKUP",
                            error=f"backup={backup_path}")
            return True

        # 策略 3: 拒绝
        logger.error(
            "[Rollback] Cannot rollback %s: no rollback() function and no backup_path. "
            "Manual intervention required.", migration_name,
        )
        return False

    def _mark_rolled_back(self, migration_name: str):
        """[P1] 标记 migration 为 ROLLED_BACK (如果 status 列存在)"""
        try:
            rows = self.data_source.execute(
                "PRAGMA table_info(schema_migrations)"
            ).fetchall()
            cols = {r[1] for r in rows} if rows else set()
            if 'status' not in cols:
                return
            self.data_source.execute(
                "UPDATE schema_migrations SET status = 'ROLLED_BACK' WHERE migration_name = ?",
                (migration_name,),
            )
            if not self.data_source.in_transaction:
                self.data_source.commit()
        except Exception as e:
            logger.debug("[P1] _mark_rolled_back failed: %s", e)

    # ------------------------------------------------------------------
    # 批量执行 (增强: .py + .sql 扫描 + migration_lock)
    # ------------------------------------------------------------------

    def run_pending_migrations(self) -> int:
        """
        执行所有待处理的迁移

        增强 (P0):
        - 同时扫描 .sql 和 .py
        - migration_lock 防多实例并发
        - heartbeat 防僵尸锁

        Returns:
            成功执行的迁移数量
        """
        self.ensure_migrations_table()

        if not os.path.exists(self.migrations_dir):
            logger.warning("Migrations directory not found: %s", self.migrations_dir)
            return 0

        # 获取 migration 锁
        if not self.acquire_migration_lock(timeout_seconds=60):
            logger.warning("Failed to acquire migration lock, skipping pending migrations")
            return 0

        try:
            executed_count = 0
            # 同时扫描 .sql 和 .py, 排除下划线开头的测试/工具脚本
            migration_files = sorted([
                f for f in os.listdir(self.migrations_dir)
                if (f.endswith('.sql') or f.endswith('.py'))
                and not f.startswith('_')
            ])

            for migration_file in migration_files:
                try:
                    # [FIX 2026-07-15] 提前过滤已执行的 migration, 避免
                    # run_migration 对已执行的也返回 True 导致 executed_count 误计
                    if self.is_migration_executed(migration_file):
                        # 仍要校验 checksum (检测文件被篡改)
                        recorded_checksum = self._get_recorded_checksum(migration_file)
                        current_checksum = self._compute_checksum(migration_file)
                        if (recorded_checksum and current_checksum
                                and recorded_checksum != current_checksum):
                            logger.error(
                                "Migration %s checksum mismatch! recorded=%s, current=%s",
                                migration_file,
                                recorded_checksum[:16], current_checksum[:16]
                            )
                            self._log_audit(migration_file, "FAILED",
                                            error="checksum mismatch: file was modified after execution")
                        continue
                    if self.run_migration(migration_file):
                        executed_count += 1
                except Exception as e:
                    logger.error(
                        "Unexpected error running migration %s: %s",
                        migration_file, e, exc_info=True
                    )
                    self._log_audit(migration_file, "FAILED", error=str(e))

            logger.info("Executed %d migrations", executed_count)
            return executed_count
        finally:
            self.release_migration_lock()

    def run_change_notification_migration(self) -> bool:
        """
        执行变更通知表迁移

        Returns:
            是否执行成功
        """
        self.ensure_migrations_table()
        migration_name = "add_change_notification_tables.sql"
        return self.run_migration(migration_name)


def init_change_notification_tables(data_source) -> bool:
    """
    初始化变更通知表

    便捷函数，用于在应用启动时初始化变更通知相关的数据库表。

    Args:
        data_source: 数据源实例

    Returns:
        是否初始化成功
    """
    runner = MigrationRunner(data_source)
    return runner.run_change_notification_migration()


def run_all_migrations(data_source, migrations_dir: str = None) -> int:
    """
    执行所有待处理的迁移

    便捷函数，用于在应用启动时执行所有数据库迁移。
    P0 增强: 支持 .py + .sql, migration_lock, checksum, backup, audit log.

    Args:
        data_source: 数据源实例
        migrations_dir: 迁移脚本目录路径

    Returns:
        成功执行的迁移数量
    """
    runner = MigrationRunner(data_source, migrations_dir)
    return runner.run_pending_migrations()


# ----------------------------------------------------------------------
# CLI 入口 (供 deploy.sh PHASE 2.5 调用)
# ----------------------------------------------------------------------

def _cli_main():
    """CLI 入口: python -m meta.core.migration_runner [--dry-run] [--db-path PATH]

    P1 增加: --status / --rollback NAME [--force-backup]
    """
    import argparse

    parser = argparse.ArgumentParser(description='Database migration runner')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only list pending migrations, do not execute')
    parser.add_argument('--migrations-dir', default=None,
                        help='Migrations directory (default: meta/migrations/)')
    parser.add_argument('--db-path', default=None,
                        help='SQLite DB path (default: env SQLITE_DB_PATH or meta/architecture.db)')
    parser.add_argument('--status', action='store_true',
                        help='[P1] List executed migrations with status')
    parser.add_argument('--rollback', metavar='NAME', default=None,
                        help='[P1] Rollback a migration by name')
    parser.add_argument('--force-backup', action='store_true',
                        help='[P1] With --rollback, force restore from backup (DANGEROUS)')
    args = parser.parse_args()

    # 延迟导入, 避免循环依赖
    from meta.core.datasource import get_data_source

    # DB 路径优先级: --db-path > SQLITE_DB_PATH > ARCH_DB_PATH > meta/architecture.db
    if args.db_path:
        db_path = args.db_path
    else:
        db_path = os.environ.get(
            'SQLITE_DB_PATH',
            os.environ.get(
                'ARCH_DB_PATH',
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'architecture.db')
            )
        )
    ds = get_data_source("sqlite", database=db_path)
    runner = MigrationRunner(ds, args.migrations_dir)

    runner.ensure_migrations_table()

    if args.dry_run:
        executed = set(runner.get_executed_migrations())
        if not os.path.exists(runner.migrations_dir):
            print("Migrations directory not found: %s" % runner.migrations_dir)
            return 0

        pending = sorted([
            f for f in os.listdir(runner.migrations_dir)
            if (f.endswith('.sql') or f.endswith('.py'))
            and not f.startswith('_')
            and f not in executed
        ])

        print("=== Migration Dry-Run ===")
        print("Migrations dir: %s" % runner.migrations_dir)
        print("Executed: %d" % len(executed))
        print("Pending: %d" % len(pending))
        print()
        for f in pending:
            checksum = runner._compute_checksum(f)
            cs_short = checksum[:16] + "..." if checksum else "NULL"
            # [P1] 提示 prerequisites
            ok, missing = runner.check_prerequisites(f)
            prereq_str = ("prereqs=OK" if ok else f"prereqs=MISSING[{','.join(missing)}]")
            print("  Would execute: %s (checksum=%s, %s)" % (f, cs_short, prereq_str))
        return 0

    if args.status:
        # [P1] 列出所有 executed + status
        rows = runner.data_source.execute(
            "SELECT migration_name, executed_by, execution_time_ms, status, environment, "
            "executed_at FROM schema_migrations ORDER BY id"
        ).fetchall()
        print("=== Migration Status ===")
        print("Executed: %d" % len(rows))
        print()
        print("%-50s %-12s %-10s %-10s %-16s" % ("name", "status", "time_ms", "env", "executed_at"))
        print("-" * 100)
        for r in rows:
            name, by, ms, st, env, ts = r
            print("%-50s %-12s %-10s %-10s %-16s" % (
                name[:50], (st or "UNKNOWN"), str(ms or "?"), (env or "?"), ts or "?"
            ))
        return 0

    if args.rollback:
        ok = runner.rollback_migration(args.rollback, force_backup=args.force_backup)
        if ok:
            print("Rolled back: %s" % args.rollback)
            return 0
        else:
            print("Rollback FAILED: %s (see logs/migrations.log)" % args.rollback)
            return 1

    count = runner.run_pending_migrations()
    print("OK: executed %d migrations" % count)
    return 0


if __name__ == '__main__':
    sys.exit(_cli_main())
