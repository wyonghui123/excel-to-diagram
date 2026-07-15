#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MigrationRunner P1 增强功能单元测试

测试覆盖:
  P1.1: schema_migrations 6 字段增强 (ALTER ADD COLUMN 自动迁移)
  P1.2: prerequisites() 检查
  P1.3: verify() 调用 (非强制)
  P1.4: rollback() 3 策略 (rollback_func / backup_restore / 拒绝)
  P1.5: rename_migrations_flyway.py (Flyway 命名 + DB UPDATE)
  P1.6: migration_lint.py 8 项检查

运行: python tools/test_migration_runner_p1.py
"""
import os
import sys
import shutil
import tempfile
import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
WORKTREE = SCRIPT_DIR.parent
sys.path.insert(0, str(WORKTREE))

from meta.core.migration_runner import (
    MigrationRunner, P1_COLUMNS, _cli_main
)


class MockDataSource:
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


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


def create_migration_file(dir_path, name, content):
    p = Path(dir_path) / name
    p.write_text(content, encoding="utf-8")
    return p


# =====================================================================
# P1.1: schema_migrations 表 6 字段增强
# =====================================================================

def test_p1_columns_added(result):
    """P1.1: 6 字段自动 ALTER ADD"""
    print("\n[P1.1] schema_migrations 6 字段自动添加")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        db = tmp / "test.db"
        with MockDataSource(db) as ds:
            # P0 schema: 只创建 4 字段
            ds.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_name VARCHAR(255) NOT NULL UNIQUE,
                    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    checksum VARCHAR(64)
                )
            """)
            ds.commit()
            runner = MigrationRunner(ds, str(tmp))
            runner.ensure_migrations_table()  # 触发 _ensure_p1_columns

            # 检查所有 P1 字段已添加
            cur = ds.execute("PRAGMA table_info(schema_migrations)")
            cols = {r["name"] for r in cur.fetchall()}
            expected = {c[0] for c in P1_COLUMNS}
            missing = expected - cols
            if not missing:
                result.ok("6 P1 columns auto-added")
            else:
                result.fail("6 P1 columns auto-added", f"missing={missing}")

        # 二次跑: 幂等
        with MockDataSource(db) as ds:
            runner = MigrationRunner(ds, str(tmp))
            runner.ensure_migrations_table()
            cur = ds.execute("PRAGMA table_info(schema_migrations)")
            cols2 = {r["name"] for r in cur.fetchall()}
            if expected.issubset(cols2):
                result.ok("_ensure_p1_columns idempotent")
            else:
                result.fail("idempotent", f"missing={expected - cols2}")


# =====================================================================
# P1.2: prerequisites 检查
# =====================================================================

def test_prerequisites(result):
    """P1.2: prerequisites() 函数检查"""
    print("\n[P1.2] prerequisites() 检查")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # .py migration 声明 prerequisites
        mig_a = '''
def migrate(db_path, skip_backup=False):
    return True
'''
        mig_b = '''
def prerequisites():
    return ["v001__nonexistent.py"]
def migrate(db_path, skip_backup=False):
    return True
'''
        mig_b_ok = '''
def prerequisites():
    return ["v001__fake.py"]
def migrate(db_path, skip_backup=False):
    return True
'''
        create_migration_file(tmp, "v001__fake.py", mig_a)
        create_migration_file(tmp, "v002__needs_fake.py", mig_b)
        create_migration_file(tmp, "v003__needs_real.py", mig_b_ok)

        db = tmp / "test.db"
        with MockDataSource(db) as ds:
            runner = MigrationRunner(ds, str(tmp))
            runner.ensure_migrations_table()
            # 先记 v001 为已执行
            runner.record_migration("v001__fake.py", "abc123")

            # v002 需要 v001, 但 v001__nonexistent.py 不是 v001__fake.py → should be missing
            ok, missing = runner.check_prerequisites("v002__needs_fake.py")
            if not ok and "v001__nonexistent.py" in missing:
                result.ok("missing prerequisite detected")
            else:
                result.fail("missing prereq", f"got ok={ok} missing={missing}")

            # v003 需要 v001__fake.py, 该文件存在并已记录 → should be OK
            ok, missing = runner.check_prerequisites("v003__needs_real.py")
            if ok and not missing:
                result.ok("satisfied prerequisite")
            else:
                result.fail("satisfied prereq", f"got ok={ok} missing={missing}")

            # 无 prerequisites() 函数的 migration → 默认 OK
            ok, missing = runner.check_prerequisites("v001__fake.py")
            if ok:
                result.ok("no prereqs = OK")
            else:
                result.fail("no prereqs default")


# =====================================================================
# P1.3: verify() 调用
# =====================================================================

def test_verify(result):
    """P1.3: verify() 调用"""
    print("\n[P1.3] verify() 调用")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        mig_ok = '''
def migrate(db_path, skip_backup=False):
    return True
def verify(db_path):
    return True
'''
        mig_fail = '''
def migrate(db_path, skip_backup=False):
    return True
def verify(db_path):
    return False
'''
        mig_novfy = '''
def migrate(db_path, skip_backup=False):
    return True
'''
        create_migration_file(tmp, "v001__with_verify_ok.py", mig_ok)
        create_migration_file(tmp, "v002__with_verify_fail.py", mig_fail)
        create_migration_file(tmp, "v003__no_verify.py", mig_novfy)

        db = tmp / "test.db"
        with MockDataSource(db) as ds:
            runner = MigrationRunner(ds, str(tmp))
            ran, ok, msg = runner.verify_migration("v001__with_verify_ok.py")
            if ran and ok:
                result.ok("verify() returns True → (True, True)")
            else:
                result.fail("verify True", f"ran={ran} ok={ok}")

            ran, ok, msg = runner.verify_migration("v002__with_verify_fail.py")
            if ran and not ok:
                result.ok("verify() returns False → (True, False)")
            else:
                result.fail("verify False", f"ran={ran} ok={ok}")

            ran, ok, msg = runner.verify_migration("v003__no_verify.py")
            if not ran:
                result.ok("no verify() → ran=False skip")
            else:
                result.fail("no verify skip", f"ran={ran}")


# =====================================================================
# P1.4: rollback() 3 策略
# =====================================================================

def test_rollback(result):
    """P1.4: rollback() 3 策略"""
    print("\n[P1.4] rollback() 3 策略")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        db = tmp / "test.db"

        # 策略 1: rollback() 函数
        mig_with_rb = '''
def migrate(db_path, skip_backup=False):
    return True
def rollback(db_path):
    return True
'''
        # 策略 3: 无 rollback 也无 backup → 拒绝
        mig_nor = '''
def migrate(db_path, skip_backup=False):
    return True
'''
        create_migration_file(tmp, "v001__with_rb.py", mig_with_rb)
        create_migration_file(tmp, "v002__no_rb.py", mig_nor)

        with MockDataSource(db) as ds:
            runner = MigrationRunner(ds, str(tmp))
            runner.ensure_migrations_table()
            runner.record_migration("v001__with_rb.py", "cs1",
                                     executed_by="test", status="SUCCESS")
            runner.record_migration("v002__no_rb.py", "cs2",
                                     executed_by="test", status="SUCCESS")

            # 策略 1: 调用 rollback()
            ok = runner.rollback_migration("v001__with_rb.py")
            if ok:
                result.ok("strategy 1: rollback() called")
            else:
                result.fail("strategy 1", "rollback func failed")

            # 策略 3: 没有 rollback 也没有 backup → 拒绝
            ok = runner.rollback_migration("v002__no_rb.py")
            if not ok:
                result.ok("strategy 3: rejected (no rollback, no backup)")
            else:
                result.fail("strategy 3", "should have rejected")

            # 策略 2: force_backup=False 时拒绝, =True 时接受
            # 制造备份文件
            bak_path = str(db) + ".bak.test"
            shutil.copy2(str(db), bak_path)
            ok = runner.rollback_migration("v002__no_rb.py", backup_path=bak_path)
            if not ok:
                result.ok("strategy 2: backup_path refused without force_backup")
            else:
                result.fail("strategy 2 force=False", "should refuse")

            ok = runner.rollback_migration("v002__no_rb.py",
                                            backup_path=bak_path, force_backup=True)
            if ok:
                result.ok("strategy 2: backup restored with force_backup=True")
            else:
                result.fail("strategy 2 force=True", "should accept")

            Path(bak_path).unlink(missing_ok=True)


# =====================================================================
# P1.5: rename_migrations_flyway.py
# =====================================================================

def test_rename_migration(result):
    """P1.5: migration 重命名"""
    print("\n[P1.5] rename_migrations_flyway.py")
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        db = tmp / "test.db"
        mig_dir = tmp / "migrations"
        mig_dir.mkdir()

        # 复制 4 个源文件
        src_dir = WORKTREE / "meta" / "migrations"
        for old_name in [
            "add_change_notification_tables.sql",
            "enhance_audit_log_v2.py",
            "v007_50_add_audit_union_view.py",
            "v007_51_add_updated_at_materialized.py",
        ]:
            shutil.copy2(src_dir / old_name, mig_dir / old_name)

        # 初始化 DB: 只 migrate_system_admin + 4 个 rename 源已执行
        with MockDataSource(db) as ds:
            ds.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_name VARCHAR(255) NOT NULL UNIQUE,
                    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    checksum VARCHAR(64)
                )
            """)
            ds.commit()
            for old_name in [
                "add_change_notification_tables.sql",
                "enhance_audit_log_v2.py",
                "v007_50_add_audit_union_view.py",
                "v007_51_add_updated_at_materialized.py",
            ]:
                ds.execute(
                    "INSERT INTO schema_migrations (migration_name, checksum) VALUES (?, ?)",
                    (old_name, "fake_cs_" + old_name),
                )
            ds.commit()

        # 跑 rename --dry-run
        script = WORKTREE / "tools" / "rename_migrations_flyway.py"
        rc = subprocess.run(
            [sys.executable, str(script),
             "--db-path", str(db), "--migrations-dir", str(mig_dir), "--dry-run"],
            capture_output=True, text=True,
        )
        if rc.returncode == 0:
            result.ok("rename --dry-run exit 0")
        else:
            result.fail("rename dry-run", f"rc={rc.returncode}")

        # 真正执行
        rc = subprocess.run(
            [sys.executable, str(script),
             "--db-path", str(db), "--migrations-dir", str(mig_dir)],
            capture_output=True, text=True,
        )
        if rc.returncode == 0:
            result.ok("rename apply exit 0")
        else:
            result.fail("rename apply", f"rc={rc.returncode} stderr={rc.stderr[:200]}")

        # 验证新文件存在
        for new_name in [
            "v003__add_change_notification_tables.sql",
            "v004__enhance_audit_log_v2.py",
            "v005__add_audit_union_view.py",
            "v006__add_updated_at_materialized.py",
        ]:
            if (mig_dir / new_name).exists():
                result.ok(f"created {new_name}")
            else:
                result.fail(f"create {new_name}")

        # 验证 DB 已 UPDATE
        with MockDataSource(db) as ds:
            cur = ds.execute("SELECT migration_name FROM schema_migrations ORDER BY id")
            names = [r[0] for r in cur.fetchall()]
            has_new = any("v003__" in n or "v004__" in n or "v005__" in n or "v006__" in n for n in names)
            has_old = any("enhance_audit_log_v2" == n or "v007_50" in n for n in names)
            if has_new and not has_old:
                result.ok("DB UPDATE old->new name")
            else:
                result.fail("DB UPDATE", f"names={names}")


# =====================================================================
# P1.6: migration_lint.py 8 项
# =====================================================================

def test_lint(result):
    """P1.6: migration_lint.py"""
    print("\n[P1.6] migration_lint.py 8 项检查")
    import subprocess
    # 对生产 migrations/ 跑 lint
    # 注意: 生产 migrations/ 含未 Flyway 命名的旧文件 (P1 之后会重命名),
    # 因此 L1 FAIL 是预期. 此测只验证 lint 工具能跑通 (不崩).
    script = WORKTREE / "tools" / "migration_lint.py"
    rc = subprocess.run(
        [sys.executable, str(script),
         "--migrations-dir", str(WORKTREE / "meta" / "migrations")],
        capture_output=True, text=True,
    )
    # rc in (0, 1, 2) 都接受 (WARN/FAIL 但不崩)
    if rc.returncode in (0, 1, 2):
        result.ok(f"lint runs without crash (rc={rc.returncode})")
    else:
        result.fail("lint crash", f"rc={rc.returncode} stderr={rc.stderr[:200]}")

    # 检查 SUMMARY 行存在
    if "Summary:" in rc.stdout:
        result.ok("lint output has Summary line")
    else:
        result.fail("lint Summary", "missing")

    # 构造恶意 migration 测 FAIL
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_dir = Path(tmpdir)
        # L1 FAIL: 命名规范
        (bad_dir / "badname.py").write_text("def migrate():\n  pass\n")
        # L5 FAIL: 无 [ALLOW_DESTRUCTIVE] 的 DROP
        (bad_dir / "v001__destructive.py").write_text(
            '"""d"""\nDROP TABLE foo\ndef migrate(db_path, skip_backup=False): return True\n'
        )
        rc = subprocess.run(
            [sys.executable, str(script), "--migrations-dir", str(bad_dir)],
            capture_output=True, text=True,
        )
        if rc.returncode == 1:
            result.ok("lint detects FAIL (rc=1)")
        else:
            result.fail("lint detect FAIL", f"rc={rc.returncode}")

        if "L1 naming" in rc.stdout:
            result.ok("L1 naming failure detected")
        else:
            result.fail("L1 detect", "L1 not in output")

        if "L5 destructive" in rc.stdout:
            result.ok("L5 destructive failure detected")
        else:
            result.fail("L5 detect", "L5 not in output")


# =====================================================================
# P1.7: monitor_migrations.py
# =====================================================================

def test_monitor(result):
    """P1.7: monitor_migrations.py"""
    print("\n[P1.7] monitor_migrations.py 健康监控")
    import subprocess
    script = WORKTREE / "tools" / "monitor_migrations.py"

    # 用真实 DB 跑
    real_db = WORKTREE / "meta" / "architecture.db"
    if not real_db.exists():
        result.fail("monitor smoke", "real DB not found")
        return

    rc = subprocess.run(
        [sys.executable, str(script), "--db-path", str(real_db)],
        capture_output=True, text=True,
    )
    output = rc.stdout
    if "schema_migrations" in output:
        result.ok("monitor reports schema_migrations")
    else:
        result.fail("monitor report", "no schema_migrations mentioned")

    if "RESULT" in output:
        result.ok("monitor has RESULT line")
    else:
        result.fail("monitor RESULT", "missing RESULT")

    # check_schema_migrations_health 单元测
    from tools.monitor_migrations import check_schema_migrations_health
    health = check_schema_migrations_health(real_db)
    if "stats" in health:
        result.ok("check_schema_migrations_health returns stats")
    else:
        result.fail("check_schema_migrations_health")


def main():
    print("=" * 60)
    print("MigrationRunner P1 增强功能单元测试")
    print("=" * 60)
    result = TestResult()

    # 跑所有测试
    test_p1_columns_added(result)
    test_prerequisites(result)
    test_verify(result)
    test_rollback(result)
    test_rename_migration(result)
    test_lint(result)
    test_monitor(result)

    return result.summary()


if __name__ == "__main__":
    sys.exit(main())
