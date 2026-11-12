# -*- coding: utf-8 -*-
"""v239 销售发票权限补齐 / 菜单分组迁移测试 —— 权限 / 挂载 / 幂等 / 回滚。

依据: docs/specs/research-fusion-billing-deep-dive-2026-11-09.md §7 P2-9
夹具: meta/tests/factories/_customer_invoice_helpers.py（permission file）
"""
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v239__customer_invoice_permissions_menu as v239
from meta.tests.factories._customer_invoice_helpers import build_permission_file

MENU_CODE = 'customer_invoice-list'
PARENT_CODE = 'ar-management'


def _db_file(tmp_path, with_parent=True):
    path = tmp_path / 'app.db'
    rows = [(MENU_CODE, '销售发票管理', '', 99)]
    if with_parent:
        rows.append((PARENT_CODE, '应收管理', '', 10))
    conn = build_permission_file(path, rows)
    conn.close()
    return path


def _rows(path, sql, params=None):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, list(params or ())).fetchall()
    finally:
        conn.close()


def test_adds_permissions_and_attaches_menu(tmp_path):
    path = _db_file(tmp_path)

    assert v239.migrate(path, skip_backup=True) is True
    assert v239.verify(path) is True

    codes = {row[0] for row in _rows(path, 'SELECT code FROM permissions')}
    assert set(v239.PERMISSION_CODES) <= codes

    parent = _rows(
        path, 'SELECT parent_menu FROM menus WHERE menu_code = ?', [MENU_CODE])
    assert parent[0][0] == PARENT_CODE

    granted = _rows(
        path,
        'SELECT COUNT(*) FROM permission_set_permissions '
        'WHERE permission_code IN (?, ?)', list(v239.PERMISSION_CODES))
    assert granted[0][0] == 4


def test_without_parent_menu_keeps_top_level(tmp_path):
    path = _db_file(tmp_path, with_parent=False)

    assert v239.migrate(path, skip_backup=True) is True
    assert v239.verify(path) is True

    parent = _rows(
        path, 'SELECT parent_menu FROM menus WHERE menu_code = ?', [MENU_CODE])
    assert parent[0][0] == ''


def test_inserts_missing_menu_row(tmp_path):
    """全新库：迁移须先补插菜单行（应用启动后 auto_generator 才 INSERT OR IGNORE）。"""
    path = tmp_path / 'app.db'
    conn = build_permission_file(path, [(PARENT_CODE, '应收管理', '', 10)])
    conn.close()
    assert _rows(path, 'SELECT 1 FROM menus WHERE menu_code = ?',
                 [MENU_CODE]) == []

    assert v239.migrate(path, skip_backup=True) is True
    assert v239.verify(path) is True

    row = _rows(
        path,
        'SELECT menu_name, menu_path, parent_menu, sort_order FROM menus '
        'WHERE menu_code = ?', [MENU_CODE])
    assert row
    assert row[0][0] == '销售发票管理'
    assert row[0][1] == '/customer-invoice'
    assert row[0][2] == PARENT_CODE
    assert row[0][3] == v239.MENU_SORT_ORDER


def test_migrate_is_idempotent_and_rollback(tmp_path):
    path = _db_file(tmp_path)

    assert v239.migrate(path, skip_backup=True) is True
    assert v239.migrate(path, skip_backup=True) is True
    assert len(_rows(path, 'SELECT code FROM permissions')) == 7
    assert v239.verify(path) is True

    assert v239.rollback(path) is True
    codes = {row[0] for row in _rows(path, 'SELECT code FROM permissions')}
    assert not (set(v239.PERMISSION_CODES) & codes)
    parent = _rows(
        path, 'SELECT parent_menu FROM menus WHERE menu_code = ?', [MENU_CODE])
    assert parent[0][0] == ''
