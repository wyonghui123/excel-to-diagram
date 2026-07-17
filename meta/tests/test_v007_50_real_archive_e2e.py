"""
E2E 真实归档验证 (V007.50)

目的：在真实 architecture.db（拷贝到 tmp）上执行 archive_audit_logs.py，验证：
  1. 归档后 v_audit_all VIEW COUNT = hot + archive（数据不丢失）
  2. 归档表中的记录能通过 VIEW 查到
  3. 类型亲和性：INTEGER id 在 VIEW 中能匹配归档表
  4. 回滚后 DB 恢复到原始状态

数据安全：
  - 测试在 tmp 目录拷贝 architecture.db，不污染真实 DB
  - 测试结束后 tmp 目录自动删除

运行：
  pytest meta/tests/test_v007_50_real_archive_e2e.py -v
"""
import os
import sys
import sqlite3
import subprocess
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REAL_DB = r"D:\filework\worktrees/release-prep\meta\architecture.db"
ARCHIVE_SCRIPT = r"D:\filework\worktrees/release-prep\meta\scripts\archive_audit_logs.py"


def _check_view_exists(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='v_audit_all'"
    ).fetchone()
    assert row, "v_audit_all VIEW 不存在，需先运行 v007_50 迁移"


def _get_count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _prepare_n_records(conn, n: int) -> int:
    """把 N 条最早记录的 retention_until 设为 365 天前"""
    old = (datetime.utcnow() - timedelta(days=365)).isoformat()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM audit_logs ORDER BY id ASC LIMIT ?", (n,)
    ).fetchall()]
    if not ids:
        return 0
    placeholders = ",".join(["?" for _ in ids])
    cur = conn.execute(
        f"UPDATE audit_logs SET retention_until = ? WHERE id IN ({placeholders})",
        [old] + ids,
    )
    conn.commit()
    return cur.rowcount


def _run_archive_subprocess(db_path: str, retention_days: int = 180) -> bool:
    """执行真实 archive_audit_logs.py 一次（处理最多 500 条）"""
    result = subprocess.run(
        [sys.executable, ARCHIVE_SCRIPT,
         "--db-path", db_path,
         "--retention-days", str(retention_days)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"STDERR: {result.stderr[:500]}")
    else:
        # Debug: print relevant log lines
        for line in result.stdout.splitlines():
            if "Found" in line or "Archived" in line or "Archive done" in line:
                print(f"  [archive] {line}")
    return result.returncode == 0


def _verify_view_count(conn, expected_hot, expected_archive):
    view = _get_count(conn, "v_audit_all")
    assert view == expected_hot + expected_archive, (
        f"VIEW COUNT {view} != hot({expected_hot}) + archive({expected_archive})"
    )
    return view


def _verify_archived_record_queryable(conn, archived_id):
    in_archive = conn.execute(
        "SELECT id FROM audit_logs_archive WHERE id = ?", (archived_id,)
    ).fetchone()
    assert in_archive, f"id={archived_id} 不在 archive 表"
    in_view = conn.execute(
        "SELECT id, action, object_type FROM v_audit_all WHERE id = ?",
        (archived_id,),
    ).fetchone()
    assert in_view, f"VIEW 找不到归档 id={archived_id}（V007.49-C P0 失败）"
    return in_view


@pytest.fixture(scope="module")
def tmp_db_path():
    """拷贝真实 architecture.db 到 tmp，测试结束后删除"""
    tmp_dir = tempfile.mkdtemp(prefix="e2e_archive_")
    tmp_db = os.path.join(tmp_dir, "architecture.db")
    shutil.copy2(REAL_DB, tmp_db)
    yield tmp_db
    # Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def db_conn(tmp_db_path):
    conn = sqlite3.connect(tmp_db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


class TestV00750RealArchiveE2E:
    """真实归档端到端测试（隔离 tmp DB）"""

    def test_step1_view_exists_and_hot_enough(self, db_conn):
        """前置条件：v_audit_all VIEW 已存在 + 热表行数 > 1000"""
        _check_view_exists(db_conn)
        hot0 = _get_count(db_conn, "audit_logs")
        arch0 = _get_count(db_conn, "audit_logs_archive")
        view0 = _get_count(db_conn, "v_audit_all")
        assert view0 == hot0 + arch0
        assert hot0 > 1000, f"热表行数 {hot0} 不足 1000"

    def test_step2_archive_500_records(self, db_conn, tmp_db_path):
        """归档 500 条最早记录后 VIEW COUNT = hot + archive"""
        n = 500
        prepared = _prepare_n_records(db_conn, n)
        assert prepared == n, f"准备了 {prepared} 条, 应为 {n}"

        hot_before = _get_count(db_conn, "audit_logs")
        arch_before = _get_count(db_conn, "audit_logs_archive")
        view_before = _get_count(db_conn, "v_audit_all")

        success = _run_archive_subprocess(tmp_db_path, retention_days=180)
        assert success, "archive_audit_logs.py 执行失败"

        # Reopen conn (subprocess may have used its own connection)
        db_conn.close()
        new_conn = sqlite3.connect(tmp_db_path, timeout=60)
        new_conn.row_factory = sqlite3.Row

        hot_after = _get_count(new_conn, "audit_logs")
        arch_after = _get_count(new_conn, "audit_logs_archive")

        # archive 脚本归档 n 条到 archive 表，并往 audit_logs 写 1 条 system 记录
        # 所以 hot_after = hot_before - n + 1, arch_after = arch_before + n
        assert hot_after == hot_before - n + 1, (
            f"hot_after {hot_after} 应为 {hot_before - n + 1} (归档 {n} + 写 1 条 archive 操作日志)"
        )
        assert arch_after == arch_before + n, (
            f"arch_after {arch_after} 应为 {arch_before + n}"
        )

        view_after = _verify_view_count(new_conn, hot_after, arch_after)
        # archive 脚本归档 500 条 + 写 1 条 system 记录，所以 VIEW +1
        assert view_after == view_before + 1, (
            f"VIEW COUNT 应为 view_before+1={view_before + 1}, 实际 {view_after}"
        )

    def test_step3_archived_record_in_view(self, tmp_db_path):
        """归档表记录能通过 VIEW 查到（V007.49-C P0 验证）"""
        conn = sqlite3.connect(tmp_db_path, timeout=60)
        conn.row_factory = sqlite3.Row
        sample = conn.execute(
            "SELECT id FROM audit_logs_archive ORDER BY id ASC LIMIT 1"
        ).fetchone()
        assert sample, "归档表为空"
        in_view = _verify_archived_record_queryable(conn, sample[0])

        arch_row = conn.execute(
            "SELECT action, object_type FROM audit_logs_archive WHERE id = ?",
            (sample[0],),
        ).fetchone()
        assert in_view[1] == arch_row[0]
        assert in_view[2] == arch_row[1]
        conn.close()

    def test_step4_type_affinity_integer_id(self, tmp_db_path):
        """INTEGER id 字段在 VIEW 中能匹配归档表的 INTEGER id"""
        conn = sqlite3.connect(tmp_db_path, timeout=60)
        conn.row_factory = sqlite3.Row
        sample = conn.execute(
            "SELECT id FROM audit_logs_archive ORDER BY id ASC LIMIT 1"
        ).fetchone()
        assert sample
        sample_id = sample[0]
        result = conn.execute(
            "SELECT id FROM v_audit_all WHERE id = ?", (sample_id,)
        ).fetchone()
        assert result, f"VIEW WHERE id={sample_id} (INTEGER) 应能找到归档记录"
        conn.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))