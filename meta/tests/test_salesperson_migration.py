# -*- coding: utf-8 -*-
"""v127 销售员 + 客户销售员分配迁移测试（索引 / 菜单 / 权限 / 幂等 / 回滚）

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §6.6

口径:
  用开发库的表结构（不含数据、不含索引）在临时库重放 migrate —— 既验证
  「表已由 sync_schema 建好时能补索引 + 菜单 + 权限」，也验证复跑只 SKIP、
  有重复组合时拒绝建唯一索引、回滚只删菜单与索引而保留权限码。
  不写真实开发库。
"""
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from meta.migrations.v127__salesperson_and_assignment import (
    ASSIGNMENT_TABLE,
    MENU_CODE,
    PARENT_MENU,
    PERMISSIONS,
    SALESPERSON_TABLE,
    _INDEX_DDL,
    migrate,
    rollback,
    verify,
)
from meta.tests.factories._pricing_w1_helpers import clone_schema, seed_row

REAL_DB = Path(__file__).resolve().parents[1] / 'architecture.db'

TABLES = (SALESPERSON_TABLE, ASSIGNMENT_TABLE,
          'menus', 'permissions', 'menu_permissions')


def _clone(tmp_path: Path) -> Path:
    if not REAL_DB.exists():
        pytest.skip('开发库不存在, 跳过迁移测试')
    dst = tmp_path / 'salesperson.db'
    missing = clone_schema(REAL_DB, dst, TABLES)
    if missing:
        pytest.skip(f'开发库缺表 {missing}, 跳过迁移测试')
    seed_row(dst, 'menus', menu_code=PARENT_MENU, menu_name='主数据')
    return dst


def _index_names(path: Path) -> set:
    conn = sqlite3.connect(str(path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


def _scalar(path: Path, sql: str, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def test_fresh_creates_indexes_menu_and_permissions(tmp_path):
    db = _clone(tmp_path)
    assert not (_index_names(db) & {name for name, _ddl in _INDEX_DDL})

    assert migrate(db) is True

    names = _index_names(db)
    for name, _ddl in _INDEX_DDL:
        assert name in names, f'缺索引 {name}'

    row = _scalar(db, 'SELECT menu_path, parent_menu, show_in_sidebar '
                      'FROM menus WHERE menu_code = ?', (MENU_CODE,))
    assert row == ('/salespersons', PARENT_MENU, 0)
    assert _scalar(db, 'SELECT COUNT(*) FROM menu_permissions '
                       'WHERE menu_code = ?', (MENU_CODE,))[0] == 1
    for code, _name, _resource, _action in PERMISSIONS:
        assert _scalar(db, 'SELECT 1 FROM permissions WHERE code = ?', (code,))
    assert verify(db) is True


def test_rerun_is_idempotent(tmp_path):
    db = _clone(tmp_path)
    assert migrate(db) is True

    before = (
        _scalar(db, 'SELECT COUNT(*) FROM menus WHERE menu_code = ?', (MENU_CODE,))[0],
        _scalar(db, 'SELECT COUNT(*) FROM menu_permissions '
                    'WHERE menu_code = ?', (MENU_CODE,))[0],
        _scalar(db, 'SELECT COUNT(*) FROM permissions')[0],
        len(_index_names(db)),
    )
    assert migrate(db) is True
    after = (
        _scalar(db, 'SELECT COUNT(*) FROM menus WHERE menu_code = ?', (MENU_CODE,))[0],
        _scalar(db, 'SELECT COUNT(*) FROM menu_permissions '
                    'WHERE menu_code = ?', (MENU_CODE,))[0],
        _scalar(db, 'SELECT COUNT(*) FROM permissions')[0],
        len(_index_names(db)),
    )
    assert after == before
    assert verify(db) is True


def test_missing_tables_fails(tmp_path):
    db = tmp_path / 'empty.db'
    sqlite3.connect(str(db)).close()
    assert migrate(db) is False
    assert verify(db) is False


def test_duplicate_assignments_block_indexes(tmp_path):
    db = _clone(tmp_path)
    for _ in range(2):
        seed_row(db, ASSIGNMENT_TABLE, customer_account_id=1, sales_org_id=318,
                 salesperson_id=1, is_primary=0, status='active')

    assert migrate(db) is False
    assert 'uidx_customer_salesperson_assign' not in _index_names(db)


def test_duplicate_primary_blocks_indexes(tmp_path):
    db = _clone(tmp_path)
    seed_row(db, ASSIGNMENT_TABLE, customer_account_id=2, sales_org_id=318,
             salesperson_id=1, is_primary=1, status='active')
    seed_row(db, ASSIGNMENT_TABLE, customer_account_id=2, sales_org_id=318,
             salesperson_id=2, is_primary=1, status='active')

    assert migrate(db) is False
    assert 'uidx_customer_salesperson_primary' not in _index_names(db)


def test_rollback_drops_menu_and_indexes_keeps_permissions(tmp_path):
    db = _clone(tmp_path)
    assert migrate(db) is True

    assert rollback(db) is True
    assert _index_names(db).isdisjoint({name for name, _ddl in _INDEX_DDL})
    assert _scalar(db, 'SELECT 1 FROM menus WHERE menu_code = ?',
                   (MENU_CODE,)) is None
    assert _scalar(db, 'SELECT 1 FROM menu_permissions WHERE menu_code = ?',
                   (MENU_CODE,)) is None
    for code, _name, _resource, _action in PERMISSIONS:
        assert _scalar(db, 'SELECT 1 FROM permissions WHERE code = ?', (code,))
    assert verify(db) is False
