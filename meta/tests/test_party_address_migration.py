# -*- coding: utf-8 -*-
"""v126 往来单位地址迁移测试（索引 / 幂等 / verify / rollback）

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §5.6

口径:
  用开发库的表结构（不含数据、不含索引）在临时库重放 migrate，验证补齐四条
  索引、复跑只 SKIP、重复组合与同角色多默认时拒绝建索引。不写真实开发库。
"""
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from meta.migrations.v126__party_address import (
    TABLE,
    UNIQUE_INDEX,
    migrate,
    rollback,
    verify,
)
from meta.tests.factories._party_address_helpers import seed_party_address
from meta.tests.factories._pricing_w1_helpers import clone_schema

REAL_DB = Path(__file__).resolve().parents[1] / 'architecture.db'


def _clone(tmp_path: Path) -> Path:
    if not REAL_DB.exists():
        pytest.skip('开发库不存在, 跳过迁移测试')
    dst = tmp_path / 'party_address.db'
    missing = clone_schema(REAL_DB, dst, (TABLE,))
    if missing:
        pytest.skip(f'开发库缺表 {missing}, 跳过迁移测试')
    return dst


def _index_sql(path: Path, name: str = UNIQUE_INDEX):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_fresh_creates_indexes(tmp_path):
    db = _clone(tmp_path)
    assert _index_sql(db) is None

    assert migrate(db) is True
    sql = _index_sql(db)
    assert sql and 'UNIQUE' in sql.upper()
    assert 'PARTY_ID' in sql.upper() and 'ADDRESS_ID' in sql.upper()
    default_sql = _index_sql(db, 'uidx_party_address_default')
    assert default_sql and 'IS_DEFAULT' in default_sql.upper()
    assert verify(db) is True


def test_rerun_is_idempotent(tmp_path):
    db = _clone(tmp_path)
    assert migrate(db) is True
    before = _index_sql(db)

    assert migrate(db) is True
    assert _index_sql(db) == before


def test_missing_table_fails(tmp_path):
    db = tmp_path / 'empty.db'
    sqlite3.connect(str(db)).close()
    assert migrate(db) is False
    assert verify(db) is False


def test_duplicate_triples_block_index(tmp_path):
    db = _clone(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        seed_party_address(conn, party_id=1, address_id=1, role='ship_to')
        seed_party_address(conn, party_id=1, address_id=1, role='ship_to')
    finally:
        conn.close()

    assert migrate(db) is False
    assert _index_sql(db) is None


def test_duplicate_defaults_block_index(tmp_path):
    db = _clone(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        seed_party_address(conn, party_id=1, address_id=1, role='ship_to',
                           is_default=1)
        seed_party_address(conn, party_id=1, address_id=2, role='ship_to',
                           is_default=1)
    finally:
        conn.close()

    assert migrate(db) is False
    assert _index_sql(db) is None


def test_rollback_drops_indexes_only(tmp_path):
    db = _clone(tmp_path)
    assert migrate(db) is True

    assert rollback(db) is True
    assert _index_sql(db) is None

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone()
    finally:
        conn.close()
