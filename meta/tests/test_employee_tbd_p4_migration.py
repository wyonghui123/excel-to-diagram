# -*- coding: utf-8 -*-
"""v189 员工 TBD 收口迁移测试（加列 / 换唯一索引 / 幂等 / 回滚）

依据: docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md §FR-015 / §10

口径:
  ① `employees.supplier_party_id` 增列（可空，TBD-10 派遣供应商）；
  ② 工号唯一索引从 `(employee_no) WHERE active` 换成
     `(org_id, employee_no) WHERE active`（TBD-12 法人雇主语义）；
  ③ 复跑只 SKIP；回滚恢复旧索引、保留列 stub。
  播种经 factories，本文件不含裸 SQL DML。
"""
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from meta.migrations.v189__employee_tbd_p4 import (  # noqa: E402
    EMPLOYEES_TABLE,
    NEW_COLUMN,
    NEW_INDEX,
    OLD_INDEX,
    OLD_INDEX_SQL,
    migrate,
    rollback,
    verify,
)
from meta.tests.factories._pricing_p2_helpers import seed_row  # noqa: E402

# v185 时期（v189 之前）的 employees 结构：无 supplier_party_id
EMPLOYEE_DDL = """
CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_no TEXT NOT NULL,
    name TEXT NOT NULL,
    person_profile_id INTEGER NOT NULL,
    user_id INTEGER,
    org_id INTEGER NOT NULL,
    location_id INTEGER,
    position TEXT,
    job_grade TEXT,
    employment_type TEXT NOT NULL DEFAULT 'full_time',
    status TEXT NOT NULL DEFAULT 'active',
    hire_date TEXT NOT NULL,
    termination_date TEXT,
    manager_employee_id INTEGER,
    created_at TEXT,
    updated_at TEXT
)
"""


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / 'employee_tbd_p4.db'
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(EMPLOYEE_DDL)
        conn.execute(OLD_INDEX_SQL)
        conn.commit()
    finally:
        conn.close()
    return path


def _columns(path: Path) -> dict:
    conn = sqlite3.connect(str(path))
    try:
        return {row[1]: row for row in conn.execute(
            'PRAGMA table_info({0})'.format(EMPLOYEES_TABLE))}
    finally:
        conn.close()


def _index_names(path: Path) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


def _index_sql(path: Path, name: str):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_migrate_adds_nullable_column_and_swaps_index(db):
    assert migrate(db) is True

    column = NEW_COLUMN[0]
    info = _columns(db)
    assert column in info, '缺列 {0}'.format(column)
    assert info[column][3] == 0, '{0} 应可空'.format(column)

    names = _index_names(db)
    assert OLD_INDEX not in names
    assert NEW_INDEX in names
    sql = (_index_sql(db, NEW_INDEX) or '').lower()
    assert 'unique' in sql and 'where' in sql
    assert 'org_id' in sql and 'employee_no' in sql
    assert "'active'" in sql
    assert verify(db) is True


def test_index_enforced_per_legal_employer(db):
    assert migrate(db) is True
    conn = sqlite3.connect(str(db))
    try:
        seed_row(conn, EMPLOYEES_TABLE, employee_no='E1', name='甲',
                 person_profile_id=1, org_id=1, status='active',
                 hire_date='2026-01-01')
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            seed_row(conn, EMPLOYEES_TABLE, employee_no='E1', name='乙',
                     person_profile_id=2, org_id=1, status='active',
                     hire_date='2026-02-01')
        conn.rollback()
        # 跨法人可复用同一工号
        seed_row(conn, EMPLOYEES_TABLE, employee_no='E1', name='丙',
                 person_profile_id=3, org_id=2, status='active',
                 hire_date='2026-03-01')
        conn.commit()
    finally:
        conn.close()
    assert verify(db) is True


def test_rerun_is_idempotent(db):
    assert migrate(db) is True
    before = (len(_columns(db)), _index_names(db))
    assert migrate(db) is True
    assert (len(_columns(db)), _index_names(db)) == before
    assert verify(db) is True


def test_rollback_restores_old_index_and_keeps_column_stub(db):
    assert migrate(db) is True
    assert rollback(db) is True

    names = _index_names(db)
    assert NEW_INDEX not in names
    assert OLD_INDEX in names
    # 列保留为 stub（不 DROP COLUMN）
    assert NEW_COLUMN[0] in _columns(db)
    assert verify(db) is False
