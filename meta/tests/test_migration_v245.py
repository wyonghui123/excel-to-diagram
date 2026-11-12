# ALLOW_RAW_SQL: 本文件含裸 SQL 构造迁移前后的类型 / 发票行数据，守卫豁免
# -*- coding: utf-8 -*-
"""v245 费用行类型迁移测试 —— 种子 / 权限 / 菜单 / 幂等 / 回滚。

依据: docs/specs/sales-invoice-pricing-spec-2026-11-10.md §9.3.4 v245
夹具: meta/tests/factories/_customer_invoice_helpers.py（build_file）
"""
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v245__customer_invoice_fee_line_types as v245
from meta.tests.factories._customer_invoice_helpers import (
    build_file,
    permission_exists,
    permission_grant_set_codes,
    seed_permission_sets,
)


def _db_file(tmp_path):
    path = tmp_path / 'app.db'
    conn = build_file(path)
    seed_permission_sets(conn)
    conn.execute('ALTER TABLE menus ADD COLUMN required_permissions TEXT')
    conn.execute('ALTER TABLE menus ADD COLUMN bo_bindings TEXT')
    conn.execute(
        'INSERT INTO menus (menu_code, menu_name, menu_path, parent_menu, '
        'sort_order, required_permissions, bo_bindings) '
        "VALUES (?, '销售发票', '/customer-invoice', NULL, 10, '[]', ?)",
        [v245.MENU_CODE,
         '[{"bo": "customer_invoice", "include_actions": ["create"]}]'])
    conn.commit()
    conn.close()
    return path


def _type_row(path, code):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            'SELECT id, line_category, delivery_relevant, status '
            'FROM type_definitions WHERE scope_bo = ? AND level = ? AND code = ?',
            [v245.SCOPE_BO, v245.LEVEL, code]).fetchone()
    finally:
        conn.close()


def _count(path, sql, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, list(params)).fetchone()[0]
    finally:
        conn.close()


def _menu_values(path):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            'SELECT required_permissions, bo_bindings FROM menus '
            'WHERE menu_code = ?', [v245.MENU_CODE]).fetchone()
    finally:
        conn.close()


def test_upgrade_seeds_types_permission_and_menu(tmp_path):
    path = _db_file(tmp_path)

    assert v245.migrate(path, skip_backup=True) is True
    assert v245.verify(path) is True

    frt = _type_row(path, 'FRT')
    assert frt is not None
    assert (frt[1], frt[2], frt[3]) == ('freight', 0, 'active')
    msc = _type_row(path, 'MSC')
    assert (msc[1], msc[2], msc[3]) == ('misc', 0, 'active')

    assert permission_exists(path, v245.FEE_PERMISSION) is True
    assert permission_grant_set_codes(
        path, v245.FEE_PERMISSION) == {'admin', 'default'}

    required, bindings = _menu_values(path)
    assert v245.FEE_PERMISSION in required
    assert v245.FEE_ACTION in bindings


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)

    assert v245.migrate(path, skip_backup=True) is True
    assert v245.migrate(path, skip_backup=True) is True

    assert v245.verify(path) is True
    assert _count(
        path, 'SELECT COUNT(*) FROM type_definitions '
              'WHERE scope_bo = ? AND level = ? AND code IN (?, ?)',
        [v245.SCOPE_BO, v245.LEVEL, 'FRT', 'MSC']) == 2
    assert _count(path, 'SELECT COUNT(*) FROM permissions WHERE code = ?',
                  [v245.FEE_PERMISSION]) == 1
    assert _count(path, 'SELECT COUNT(*) FROM permission_set_permissions '
                        'WHERE permission_code = ?',
                  [v245.FEE_PERMISSION]) == 2


def test_verify_rejects_drifted_line_category(tmp_path):
    path = _db_file(tmp_path)
    assert v245.migrate(path, skip_backup=True) is True

    conn = sqlite3.connect(str(path))
    conn.execute(
        "UPDATE type_definitions SET line_category = 'material' "
        "WHERE scope_bo = ? AND level = ? AND code = 'FRT'",
        [v245.SCOPE_BO, v245.LEVEL])
    conn.commit()
    conn.close()

    assert v245.verify(path) is False


def test_rollback_removes_unused_types(tmp_path):
    path = _db_file(tmp_path)
    assert v245.migrate(path, skip_backup=True) is True

    assert v245.rollback(path) is True

    assert _type_row(path, 'FRT') is None
    assert _type_row(path, 'MSC') is None
    assert permission_exists(path, v245.FEE_PERMISSION) is False
    assert _count(path, 'SELECT COUNT(*) FROM permission_set_permissions '
                        'WHERE permission_code = ?',
                  [v245.FEE_PERMISSION]) == 0

    required, bindings = _menu_values(path)
    assert v245.FEE_PERMISSION not in (required or '')
    assert v245.FEE_ACTION not in (bindings or '')

    assert v245.verify(path) is False

    # 回滚幂等
    assert v245.rollback(path) is True


def test_rollback_demotes_referenced_type(tmp_path):
    path = _db_file(tmp_path)
    assert v245.migrate(path, skip_backup=True) is True
    frt_id = _type_row(path, 'FRT')[0]

    conn = sqlite3.connect(str(path))
    conn.execute(
        'INSERT INTO customer_invoice_lines '
        '(invoice_id, line_no, line_type_id, source_doc_type, item_id, '
        ' description, uom_id, qty, unit_price, net_amount, tax_code_id, '
        ' tax_rate_percent, source_doc_id) '
        "VALUES (1, 1, ?, 'manual', NULL, '运费', 1, 1, 0, 0, 1, 0, NULL)",
        [frt_id])
    conn.commit()
    conn.close()

    assert v245.rollback(path) is True

    kept = _type_row(path, 'FRT')
    assert kept is not None
    assert kept[3] == 'inactive'
    assert _type_row(path, 'MSC') is None