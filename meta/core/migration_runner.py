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

增强历史:
  v1.0: 基础框架 (仅 .sql, 无 checksum/lock/backup/audit)
  v1.1 (P0): 支持 .py + checksum + migration_lock + 超时 + 备份 + 审计日志
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
    checksum VARCHAR(64)
);
"""

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
        logger.info("Migration tracking table + lock table ensured")

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

    def record_migration(self, migration_name: str, checksum: str = None):
        """记录迁移执行"""
        sql = "INSERT INTO schema_migrations (migration_name, checksum) VALUES (?, ?)"
        self.data_source.execute(sql, (migration_name, checksum))
        if not self.data_source.in_transaction:
            self.data_source.commit()
        logger.info("Migration recorded: %s", migration_name)

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

    def execute_sql_file(self, sql_file_path: str) -> bool:
        """
        执行 SQL 文件

        Args:
            sql_file_path: SQL 文件路径

        Returns:
            是否执行成功
        """
        try:
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            statements = self._parse_sql_statements(sql_content)

            for statement in statements:
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    self.data_source.execute(statement)

            if not self.data_source.in_transaction:
                self.data_source.commit()

            logger.info("SQL file executed successfully: %s", sql_file_path)
            return True

        except Exception as e:
            logger.error("Failed to execute SQL file %s: %s", sql_file_path, str(e))
            return False

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
            self.record_migration(migration_name, checksum)
            self._log_audit(migration_name, "SUCCESS",
                            checksum=checksum, elapsed_ms=elapsed_ms)
            return True
        elif success is None:
            # 跳过 (签名不兼容), 不记录, 不算失败
            self._log_audit(migration_name, "SKIPPED",
                            error="incompatible signature", elapsed_ms=elapsed_ms)
            logger.info("Migration %s skipped (incompatible signature)", migration_name)
            return True  # 不阻断后续 migration
        else:
            self._log_audit(migration_name, "FAILED", elapsed_ms=elapsed_ms)
            return False

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
    """CLI 入口: python -m meta.core.migration_runner [--dry-run] [--db-path PATH]"""
    import argparse

    parser = argparse.ArgumentParser(description='Database migration runner')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only list pending migrations, do not execute')
    parser.add_argument('--migrations-dir', default=None,
                        help='Migrations directory (default: meta/migrations/)')
    parser.add_argument('--db-path', default=None,
                        help='SQLite DB path (default: env SQLITE_DB_PATH or meta/architecture.db)')
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

    if args.dry_run:
        runner.ensure_migrations_table()
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
            print("  Would execute: %s (checksum=%s)" % (f, cs_short))
        return 0

    count = runner.run_pending_migrations()
    print("OK: executed %d migrations" % count)
    return 0


if __name__ == '__main__':
    sys.exit(_cli_main())
