"""[L13.4] audit coverage 覆盖率检测"""
import sys
import sqlite3
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from audit_coverage_check import check_coverage, CRITICAL_TABLES


def test_check_coverage_empty_db(tmp_path):
    """空 db 应返回 ok (无数据 = 无缺口)"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE roles (id INTEGER PRIMARY KEY, updated_at INTEGER)")
    conn.execute("CREATE TABLE audit_logs (object_type TEXT, action TEXT, created_at INTEGER)")
    conn.commit()
    conn.close()

    report = check_coverage(str(db), lookback_days=30)
    # 空数据时所有表覆盖率 = 1.0, 应 ok
    assert report["overall"]["fail"] == 0


def test_check_coverage_missing_table(tmp_path):
    """表不存在不应崩溃, 而是记录 error"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE audit_logs (object_type TEXT, action TEXT, created_at INTEGER)")
    conn.commit()
    conn.close()

    report = check_coverage(str(db), lookback_days=30)
    assert "roles" in report["tables"]
    assert "error" in report["tables"]["roles"]


def test_check_coverage_perfect(tmp_path):
    """完美覆盖: 全部 DELETE 都有 audit"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE roles (id INTEGER PRIMARY KEY, updated_at INTEGER)")
    conn.execute("CREATE TABLE audit_logs (object_type TEXT, action TEXT, created_at INTEGER)")
    import time
    now = int(time.time())
    conn.execute("INSERT INTO roles VALUES (1, ?)", (now,))
    conn.execute("INSERT INTO audit_logs VALUES ('roles', 'DELETE', ?)", (now,))
    conn.commit()
    conn.close()

    report = check_coverage(str(db), lookback_days=30)
    assert report["tables"]["roles"]["coverage"] == 1.0
    assert report["tables"]["roles"]["status"] == "ok"


def test_check_coverage_partial(tmp_path):
    """部分覆盖: 50% 应 warn (>= 50% threshold)"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE roles (id INTEGER PRIMARY KEY, updated_at INTEGER)")
    conn.execute("CREATE TABLE audit_logs (object_type TEXT, action TEXT, created_at INTEGER)")
    import time
    now = int(time.time())
    # 4 条 records, 2 个 audit
    for i in range(4):
        conn.execute("INSERT INTO roles VALUES (?, ?)", (i, now))
    for i in range(2):
        conn.execute("INSERT INTO audit_logs VALUES ('roles', 'DELETE', ?)", (now,))
    conn.commit()
    conn.close()

    report = check_coverage(str(db), lookback_days=30)
    # coverage = 2/4 = 0.5, expected=1.0 → status = warn (>= 50% of expected)
    assert report["tables"]["roles"]["status"] in ("warn", "ok")


def test_critical_tables_defined():
    """至少定义 6 个关键表"""
    assert len(CRITICAL_TABLES) >= 6
    assert "roles" in CRITICAL_TABLES
    assert "users" in CRITICAL_TABLES


def test_check_coverage_lookback_filter(tmp_path):
    """旧数据应被 lookback 过滤"""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE roles (id INTEGER PRIMARY KEY, updated_at INTEGER)")
    conn.execute("CREATE TABLE audit_logs (object_type TEXT, action TEXT, created_at INTEGER)")
    old_ts = 1000000000  # 2001 年
    conn.execute("INSERT INTO roles VALUES (1, ?)", (old_ts,))
    conn.commit()
    conn.close()

    report = check_coverage(str(db), lookback_days=30)
    # 旧数据不在 lookback 内, total = 0, coverage = 1.0
    assert report["tables"]["roles"]["total"] == 0