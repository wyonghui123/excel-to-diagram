#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MigrationRunner P0 增强功能单元测试

测试覆盖:
  1. checksum 计算 (SHA256)
  2. schema_migrations + migration_lock 表创建
  3. .sql migration 执行 + 记录
  4. .py migration 执行 (兼容签名)
  5. .py migration 跳过 (不兼容签名)
  6. 幂等性 (已执行的跳过)
  7. checksum 不匹配检测
  8. migration_lock 获取/释放
  9. migration_lock 僵尸锁检测
  10. DB 备份 + 保留策略
  11. 审计日志写入

运行方式:
  cd d:/filework/worktrees/release-prep
  python tools/test_migration_runner.py
"""

import os
import sys
import shutil
import tempfile
import sqlite3
import hashlib
import time
from pathlib import Path
from datetime import datetime, timedelta

# 确保 meta 包可导入
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from meta.core.migration_runner import MigrationRunner, MIGRATIONS_TABLE, MIGRATION_LOCK_TABLE


# ----------------------------------------------------------------------
# Mock DataSource (模拟 SQLDataSource 的最小接口)
# ----------------------------------------------------------------------

class MockDataSource:
    """模拟 DataSource, 包装 sqlite3.connect()"""

    def __init__(self, db_path):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._in_transaction = False

    @property
    def in_transaction(self):
        return self._in_transaction

    def execute(self, sql, params=None):
        if params:
            cursor = self._conn.execute(sql, params)
        else:
            cursor = self._conn.execute(sql)
        self._conn.commit()
        return cursor

    def commit(self):
        self._conn.commit()
        self._in_transaction = False

    def rollback(self):
        self._conn.rollback()
        self._in_transaction = False

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # [FIX 2026-07-15] 支持 context manager 协议,
    # 确保异常时也能释放 sqlite3 句柄 (Windows 不释放则临时目录无法清理)
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# ----------------------------------------------------------------------
# 测试辅助
# ----------------------------------------------------------------------

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  [OK] {name}")

    def fail(self, name, reason=""):
        self.failed += 1
        self.errors.append(f"{name}: {reason}")
        print(f"  [FAIL] {name} - {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("Failures:")
            for e in self.errors:
                print(f"  - {e}")
        return 0 if self.failed == 0 else 1


def create_test_migration(dir_path, name, content):
    """创建测试 migration 文件"""
    path = Path(dir_path) / name
    path.write_text(content, encoding='utf-8')
    return path


# ----------------------------------------------------------------------
# 测试用例
# ----------------------------------------------------------------------

def test_checksum(result):
    """1. SHA256 checksum 计算"""
    print("\n[Test 1] Checksum computation (SHA256)")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mig_file = create_test_migration(tmpdir, "v001__test.py", "# test content\nprint('hello')\n")

        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))

        checksum = runner._compute_checksum("v001__test.py")
        # 手动计算对比
        h = hashlib.sha256()
        h.update(mig_file.read_bytes())
        expected = h.hexdigest()

        if checksum == expected:
            result.ok("checksum matches manual SHA256")
        else:
            result.fail("checksum matches", f"got {checksum}, expected {expected}")

        # 不存在的文件
        none_cs = runner._compute_checksum("nonexistent.py")
        if none_cs is None:
            result.ok("checksum None for missing file")
        else:
            result.fail("checksum None for missing", f"got {none_cs}")

        ds.close()


def test_table_creation(result):
    """2. schema_migrations + migration_lock 表创建"""
    print("\n[Test 2] Table creation (schema_migrations + migration_lock)")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))

        runner.ensure_migrations_table()

        # 检查 schema_migrations 表
        tables = ds.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {t[0] for t in tables}

        if "schema_migrations" in table_names:
            result.ok("schema_migrations table created")
        else:
            result.fail("schema_migrations created", f"tables: {table_names}")

        if "migration_lock" in table_names:
            result.ok("migration_lock table created")
        else:
            result.fail("migration_lock created", f"tables: {table_names}")

        ds.close()


def test_sql_migration(result):
    """3. .sql migration 执行 + 记录"""
    print("\n[Test 3] SQL migration execution")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        sql_content = "CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, name TEXT);\n"
        create_test_migration(tmpdir, "v001__create_test.sql", sql_content)

        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))
        runner.ensure_migrations_table()

        # 执行
        success = runner.run_migration("v001__create_test.sql")
        if success:
            result.ok("SQL migration executed successfully")
        else:
            result.fail("SQL migration execution")
            ds.close()
            return

        # 验证表创建
        tables = ds.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'").fetchall()
        if len(tables) == 1:
            result.ok("test_table created by migration")
        else:
            result.fail("test_table created")

        # 验证 schema_migrations 记录
        records = ds.execute("SELECT migration_name, checksum FROM schema_migrations").fetchall()
        if len(records) == 1 and records[0][0] == "v001__create_test.sql":
            result.ok("migration recorded in schema_migrations")
        else:
            result.fail("migration recorded", f"records: {records}")

        if records and records[0][1]:
            result.ok("checksum recorded (non-null)")
        else:
            result.fail("checksum recorded")

        ds.close()


def test_py_migration_compatible(result):
    """4. .py migration 执行 (兼容签名 migrate(db_path, skip_backup))"""
    print("\n[Test 4] Python migration execution (compatible signature)")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        py_content = '''# -*- coding: utf-8 -*-
from pathlib import Path
import sqlite3

def migrate(db_path, skip_backup=False):
    """Test migration: create a test table"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS py_test_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return True
'''
        create_test_migration(tmpdir, "v002__py_test.py", py_content)

        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))
        runner.ensure_migrations_table()

        success = runner.run_migration("v002__py_test.py")
        if success:
            result.ok("PY migration executed successfully")
        else:
            result.fail("PY migration execution")
            ds.close()
            return

        # 验证表创建
        tables = ds.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='py_test_table'").fetchall()
        if len(tables) == 1:
            result.ok("py_test_table created by migration")
        else:
            result.fail("py_test_table created")

        # 验证记录
        records = ds.execute("SELECT migration_name FROM schema_migrations WHERE migration_name='v002__py_test.py'").fetchall()
        if len(records) == 1:
            result.ok("PY migration recorded in schema_migrations")
        else:
            result.fail("PY migration recorded")

        ds.close()


def test_py_migration_incompatible(result):
    """5. .py migration 跳过 (不兼容签名)"""
    print("\n[Test 5] Python migration skip (incompatible signature)")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        # 无 migrate() 函数
        py_content_no_migrate = "# no migrate function\ndef main():\n    pass\n"
        create_test_migration(tmpdir, "v003__no_migrate.py", py_content_no_migrate)

        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))
        runner.ensure_migrations_table()

        # 无 migrate() 函数 → 跳过
        ret = runner._execute_py_migration("v003__no_migrate.py")
        if ret is None:
            result.ok("migration without migrate() skipped (None)")
        else:
            result.fail("no migrate() skip", f"got {ret}")

        # 不兼容签名: migrate() 无参
        py_content_no_args = "def migrate():\n    pass\n"
        create_test_migration(tmpdir, "v004__no_args.py", py_content_no_args)
        ret = runner._execute_py_migration("v004__no_args.py")
        if ret is None:
            result.ok("migration with migrate() no-args skipped (None)")
        else:
            result.fail("no-args skip", f"got {ret}")

        ds.close()


def test_idempotency(result):
    """6. 幂等性 (已执行的跳过)"""
    print("\n[Test 6] Idempotency (already executed migrations are skipped)")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        sql_content = "CREATE TABLE IF NOT EXISTS idem_test (id INTEGER);\n"
        create_test_migration(tmpdir, "v005__idem.sql", sql_content)

        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))
        runner.ensure_migrations_table()

        # 第一次执行
        success1 = runner.run_migration("v005__idem.sql")
        if not success1:
            result.fail("first execution")
            ds.close()
            return

        # 第二次执行 (应该跳过, 返回 True)
        success2 = runner.run_migration("v005__idem.sql")
        if success2:
            result.ok("second execution returns True (skipped)")
        else:
            result.fail("second execution skip")

        # 验证只有 1 条记录
        count = ds.execute("SELECT count(*) FROM schema_migrations WHERE migration_name='v005__idem.sql'").fetchone()[0]
        if count == 1:
            result.ok("only 1 record in schema_migrations (no duplicate)")
        else:
            result.fail("no duplicate record", f"count={count}")

        ds.close()


def test_checksum_mismatch(result):
    """7. checksum 不匹配检测"""
    print("\n[Test 7] Checksum mismatch detection")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        sql_content = "CREATE TABLE IF NOT EXISTS cs_test (id INTEGER);\n"
        mig_path = create_test_migration(tmpdir, "v006__cs.sql", sql_content)

        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))
        runner.ensure_migrations_table()

        # 第一次执行
        runner.run_migration("v006__cs.sql")

        # 修改文件内容 (模拟文件被篡改)
        mig_path.write_text("CREATE TABLE IF NOT EXISTS cs_test (id INTEGER, name TEXT);\n", encoding='utf-8')

        # 第二次执行 → 应该检测到 checksum 不匹配, 返回 False
        success = runner.run_migration("v006__cs.sql")
        if not success:
            result.ok("checksum mismatch detected (returned False)")
        else:
            result.fail("checksum mismatch detection", "returned True, expected False")

        ds.close()


def test_migration_lock(result):
    """8. migration_lock 获取/释放"""
    print("\n[Test 8] Migration lock acquire/release")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))
        runner.ensure_migrations_table()

        # 获取锁
        acquired = runner.acquire_migration_lock(timeout_seconds=5)
        if acquired:
            result.ok("lock acquired")
        else:
            result.fail("lock acquire")
            ds.close()
            return

        # 验证锁记录
        row = ds.execute("SELECT locked_by FROM migration_lock WHERE id=1").fetchone()
        if row and row[0]:
            result.ok("lock record exists in migration_lock table")
        else:
            result.fail("lock record exists")

        # 释放锁
        runner.release_migration_lock()

        # 验证锁已删除
        row = ds.execute("SELECT count(*) FROM migration_lock WHERE id=1").fetchone()
        if row[0] == 0:
            result.ok("lock released (record deleted)")
        else:
            result.fail("lock release", f"count={row[0]}")

        ds.close()


def test_zombie_lock(result):
    """9. migration_lock 僵尸锁检测"""
    print("\n[Test 9] Zombie lock detection")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))
        runner.ensure_migrations_table()

        # 手动插入一个僵尸锁 (heartbeat 2 分钟前)
        zombie_time = (datetime.now() - timedelta(seconds=120)).isoformat()
        ds.execute(
            "INSERT INTO migration_lock (id, locked_by, locked_at, heartbeat_at) "
            "VALUES (1, 'zombie-host-999', ?, ?)",
            (zombie_time, zombie_time)
        )
        ds.commit()

        # 尝试获取锁 → 应该检测到僵尸并接管
        acquired = runner.acquire_migration_lock(timeout_seconds=10)
        if acquired:
            result.ok("zombie lock detected and taken over")
        else:
            result.fail("zombie lock takeover")

        # 验证锁属于当前实例
        row = ds.execute("SELECT locked_by FROM migration_lock WHERE id=1").fetchone()
        if row and row[0] != 'zombie-host-999':
            result.ok("lock now held by current instance")
        else:
            result.fail("lock ownership", f"locked_by={row[0] if row else None}")

        runner.release_migration_lock()
        ds.close()


def test_backup(result):
    """10. DB 备份"""
    print("\n[Test 10] DB backup")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        db_path = tmpdir / "test.db"

        # 创建一个有内容的 DB
        ds = MockDataSource(db_path)
        ds.execute("CREATE TABLE test (id INTEGER)")
        ds.execute("INSERT INTO test VALUES (1)")
        ds.commit()
        ds.close()

        # 创建 runner 备份
        ds2 = MockDataSource(db_path)
        runner = MigrationRunner(ds2, str(tmpdir))
        success = runner._backup_db()

        if success:
            result.ok("backup completed successfully")
        else:
            result.fail("backup completion")
            ds2.close()
            return

        # 验证备份文件存在
        backups = list(tmpdir.glob("test.db.bak.*"))
        if len(backups) >= 1:
            result.ok(f"backup file created ({len(backups)} found)")
        else:
            result.fail("backup file created")

        # 验证备份内容正确
        if backups:
            bak_conn = sqlite3.connect(str(backups[0]))
            bak_count = bak_conn.execute("SELECT count(*) FROM test").fetchone()[0]
            bak_conn.close()
            if bak_count == 1:
                result.ok("backup content correct (1 row)")
            else:
                result.fail("backup content", f"expected 1 row, got {bak_count}")

        ds2.close()


def test_audit_log(result):
    """11. 审计日志写入"""
    print("\n[Test 11] Audit log writing")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))
        runner.ensure_migrations_table()

        # 写一条审计日志
        runner._log_audit("v001__test.py", "SUCCESS", checksum="abc123def456", elapsed_ms=150)

        # 验证日志文件
        log_path = runner._get_audit_log_path()
        if log_path.exists():
            content = log_path.read_text(encoding='utf-8')
            if "v001__test.py" in content and "SUCCESS" in content:
                result.ok("audit log contains migration name and status")
            else:
                result.fail("audit log content", f"content: {content[:200]}")
        else:
            result.fail("audit log file exists", str(log_path))

        ds.close()


def test_run_pending_migrations(result):
    """12. run_pending_migrations 完整流程"""
    print("\n[Test 12] run_pending_migrations (full flow)")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 创建 2 个 migration
        create_test_migration(tmpdir, "v001__first.sql",
                              "CREATE TABLE IF NOT EXISTS t1 (id INTEGER);\n")
        create_test_migration(tmpdir, "v002__second.py",
                              "def migrate(db_path, skip_backup=False):\n"
                              "    import sqlite3\n"
                              "    conn = sqlite3.connect(str(db_path))\n"
                              "    conn.execute('CREATE TABLE IF NOT EXISTS t2 (id INTEGER)')\n"
                              "    conn.commit()\n"
                              "    conn.close()\n"
                              "    return True\n")

        ds = MockDataSource(tmpdir / "test.db")
        runner = MigrationRunner(ds, str(tmpdir))

        count = runner.run_pending_migrations()

        if count >= 2:
            result.ok(f"run_pending_migrations executed {count} migrations")
        else:
            result.fail("run_pending_migrations count", f"got {count}, expected >= 2")

        # 验证表都创建了
        tables = {t[0] for t in ds.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "t1" in tables and "t2" in tables:
            result.ok("both tables created")
        else:
            result.fail("tables created", f"tables: {tables}")

        # 验证 schema_migrations 记录
        records = ds.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        if records >= 2:
            result.ok(f"schema_migrations has {records} records")
        else:
            result.fail("schema_migrations records", f"got {records}, expected >= 2")

        # 第二次运行 (应该 0 个 pending)
        count2 = runner.run_pending_migrations()
        if count2 == 0:
            result.ok("second run finds 0 pending (idempotent)")
        else:
            result.fail("second run idempotent", f"got {count2} pending")

        ds.close()


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------

def main():
    print("=" * 60)
    print("MigrationRunner P0 Enhancement - Unit Tests")
    print("=" * 60)

    result = TestResult()

    tests = [
        test_checksum,
        test_table_creation,
        test_sql_migration,
        test_py_migration_compatible,
        test_py_migration_incompatible,
        test_idempotency,
        test_checksum_mismatch,
        test_migration_lock,
        test_zombie_lock,
        test_backup,
        test_audit_log,
        test_run_pending_migrations,
    ]

    for test_func in tests:
        try:
            test_func(result)
        except Exception as e:
            result.fail(test_func.__name__, f"Exception: {e}")
            import traceback
            traceback.print_exc()

    return result.summary()


if __name__ == '__main__':
    sys.exit(main())
