# ALLOW_RAW_SQL: 本文件含裸 SQL 构造迁移前后的列 / 种子 / 发票数据，守卫豁免
# -*- coding: utf-8 -*-
"""v244 价格与金额溯源迁移测试 —— 列 / 种子 / 回填 / 权限 / 菜单 / 回滚。

依据: docs/specs/sales-invoice-pricing-spec-2026-11-10.md
      §3 FR-001~FR-006 / §9.3.2 枚举与控制参数 / §9.3.4 迁移设计
夹具: meta/tests/factories/_customer_invoice_helpers.py（build_file）
"""
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v244__customer_invoice_pricing_trace as v244
from meta.tests.factories._customer_invoice_helpers import (
    build_file,
    permission_exists,
    permission_grant_set_codes,
    seed_permission_sets,
    table_columns,
)

NEW_LINE_COLUMNS = {name for name, _ddl in v244.NEW_LINE_COLUMNS}
NEW_HEADER_COLUMNS = {name for name, _ddl in v244.NEW_HEADER_COLUMNS}
NEW_RATE_RECORD_COLUMNS = {name for name, _ddl in v244.NEW_RATE_RECORD_COLUMNS}

ENUM_VALUE_COUNT = sum(len(values) for _t, _n, _d, values in v244.ENUM_SEEDS)

#: 迁移依赖、但业务夹具不建的最小元数据表（真实库由早前迁移创建）
_META_DDL = """
CREATE TABLE IF NOT EXISTS enum_types (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128),
    category VARCHAR(32),
    mutability VARCHAR(16),
    dimension_schema TEXT,
    description TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS enum_values (
    enum_type_id VARCHAR(64),
    code VARCHAR(64),
    name VARCHAR(128),
    name_en VARCHAR(128),
    sort_order INTEGER,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS control_parameter_defs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(64) UNIQUE,
    name VARCHAR(128),
    domain VARCHAR(32),
    value_type VARCHAR(16),
    enum_type_id VARCHAR(64),
    target_bo VARCHAR(64),
    default_value VARCHAR(128),
    status VARCHAR(16) DEFAULT 'active',
    description TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS control_parameter_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    control_parameter_id INTEGER,
    org_id INTEGER,
    document_type_id INTEGER,
    line_type_id INTEGER,
    item_group_id INTEGER,
    specificity_rank INTEGER DEFAULT 0,
    value VARCHAR(128),
    status VARCHAR(16) DEFAULT 'active',
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS rate_records (
    id INTEGER PRIMARY KEY,
    code VARCHAR(64)
);
"""


def _strip_v244_columns(path):
    """移除夹具预置的 v244 列，让 migrate() 真正走 ALTER TABLE 分支。"""
    conn = sqlite3.connect(str(path))
    for table, columns in (('customer_invoice_lines', v244.NEW_LINE_COLUMNS),
                           ('customer_invoices', v244.NEW_HEADER_COLUMNS),
                           ('rate_records', v244.NEW_RATE_RECORD_COLUMNS)):
        existing = {row[1] for row in conn.execute(
            'PRAGMA table_info("%s")' % table)}
        for name, _ddl in columns:
            if name in existing:
                conn.execute('ALTER TABLE %s DROP COLUMN %s' % (table, name))
    conn.commit()
    conn.close()


def _db_file(tmp_path, *, strip=True):
    path = tmp_path / 'app.db'
    conn = build_file(path)
    seed_permission_sets(conn)
    conn.executescript(_META_DDL)
    conn.execute(
        'ALTER TABLE menus ADD COLUMN required_permissions TEXT')
    conn.execute('ALTER TABLE menus ADD COLUMN bo_bindings TEXT')
    conn.execute(
        'INSERT INTO menus (menu_code, menu_name, menu_path, parent_menu, '
        'sort_order, required_permissions, bo_bindings) '
        "VALUES (?, ?, ?, NULL, 10, '[]', ?)",
        [v244.MENU_CODE, '销售发票', '/customer-invoice',
         '[{"bo": "customer_invoice", "include_actions": ["create"]}]'])
    conn.commit()
    conn.close()
    if strip:
        _strip_v244_columns(path)
    return path


def _insert_invoice(path, invoice_no, invoice_date='2026-11-09'):
    conn = sqlite3.connect(str(path))
    conn.execute(
        'INSERT INTO customer_invoices '
        '(invoice_no, document_type_id, document_category, invoice_date, '
        ' customer_account_id, currency_id, org_id) '
        'VALUES (?, (SELECT id FROM type_definitions '
        "          WHERE scope_bo = 'customer_invoice' AND level = 'header' "
        "          AND code = 'SINV'), 'invoice', ?, 900, 1, 10)",
        [invoice_no, invoice_date])
    conn.commit()
    conn.close()


def _count(path, sql, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, list(params)).fetchone()[0]
    finally:
        conn.close()


def _header_row(path, invoice_no):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            'SELECT billing_pricing_mode, pricing_date, rounding_diff '
            'FROM customer_invoices WHERE invoice_no = ?',
            [invoice_no]).fetchone()
    finally:
        conn.close()


def test_upgrade_adds_columns_seeds_and_permissions(tmp_path):
    path = _db_file(tmp_path)

    assert v244.migrate(path, skip_backup=True) is True
    assert v244.verify(path) is True

    assert NEW_LINE_COLUMNS <= table_columns(path, 'customer_invoice_lines')
    assert NEW_HEADER_COLUMNS <= table_columns(path, 'customer_invoices')
    assert NEW_RATE_RECORD_COLUMNS <= table_columns(path, 'rate_records')

    assert _count(path, 'SELECT COUNT(*) FROM enum_types '
                        'WHERE id IN (?, ?)',
                  [seed[0] for seed in v244.ENUM_SEEDS]) == len(v244.ENUM_SEEDS)
    assert _count(path, 'SELECT COUNT(*) FROM enum_values') == ENUM_VALUE_COUNT

    assert _count(path, 'SELECT COUNT(*) FROM control_parameter_defs') == \
        len(v244.PARAM_DEFS)

    # 类型级取值：SINV / SCR / SDN / SRV 各一条，specificity_rank=1
    assert _count(
        path,
        'SELECT COUNT(*) FROM control_parameter_values v '
        'JOIN control_parameter_defs d ON d.id = v.control_parameter_id '
        "WHERE d.code = 'billing_pricing_mode' AND v.specificity_rank = 1 "
        "AND v.value = 'copy_frozen_redetermine_tax'") == \
        len(v244.PRICING_MODE_TYPE_CODES)

    assert permission_exists(path, v244.OVERRIDE_PERMISSION) is True
    assert permission_grant_set_codes(
        path, v244.OVERRIDE_PERMISSION) == {'admin', 'default'}

    # 菜单：required_permissions 追加权限码、bo_bindings 追加动作
    conn = sqlite3.connect(str(path))
    try:
        required, bindings = conn.execute(
            'SELECT required_permissions, bo_bindings FROM menus '
            'WHERE menu_code = ?', [v244.MENU_CODE]).fetchone()
    finally:
        conn.close()
    assert v244.OVERRIDE_PERMISSION in required
    assert v244.OVERRIDE_ACTION in bindings


def test_upgrade_backfills_blank_existing_invoice(tmp_path):
    path = _db_file(tmp_path, strip=False)
    _insert_invoice(path, 'SINV-0001', invoice_date='2026-10-01')

    conn = sqlite3.connect(str(path))
    conn.execute(
        "UPDATE customer_invoices SET billing_pricing_mode = '', "
        "pricing_date = '' WHERE invoice_no = 'SINV-0001'")
    conn.commit()
    conn.close()

    assert v244.migrate(path, skip_backup=True) is True
    assert v244.verify(path) is True

    mode, pricing_date, rounding_diff = _header_row(path, 'SINV-0001')
    assert mode == 'legacy'
    assert pricing_date == '2026-10-01'
    assert rounding_diff == 0


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)

    assert v244.migrate(path, skip_backup=True) is True
    assert v244.migrate(path, skip_backup=True) is True

    assert v244.verify(path) is True
    assert _count(path, 'SELECT COUNT(*) FROM enum_types') == \
        len(v244.ENUM_SEEDS)
    assert _count(path, 'SELECT COUNT(*) FROM enum_values') == ENUM_VALUE_COUNT
    assert _count(path, 'SELECT COUNT(*) FROM control_parameter_defs') == \
        len(v244.PARAM_DEFS)
    assert _count(path, 'SELECT COUNT(*) FROM control_parameter_values') == \
        len(v244.PRICING_MODE_TYPE_CODES)
    assert _count(path, 'SELECT COUNT(*) FROM permissions WHERE code = ?',
                  [v244.OVERRIDE_PERMISSION]) == 1
    assert _count(path, 'SELECT COUNT(*) FROM permission_set_permissions '
                        'WHERE permission_code = ?',
                  [v244.OVERRIDE_PERMISSION]) == 2


def test_verify_rejects_missing_backfill(tmp_path):
    path = _db_file(tmp_path)
    _insert_invoice(path, 'SINV-0002')

    assert v244.migrate(path, skip_backup=True) is True
    assert v244.verify(path) is True

    conn = sqlite3.connect(str(path))
    conn.execute(
        "UPDATE customer_invoices SET billing_pricing_mode = '' "
        "WHERE invoice_no = 'SINV-0002'")
    conn.commit()
    conn.close()
    assert v244.verify(path) is False


def test_rollback_removes_all(tmp_path):
    path = _db_file(tmp_path)
    assert v244.migrate(path, skip_backup=True) is True

    assert v244.rollback(path) is True

    assert not (NEW_LINE_COLUMNS & table_columns(path, 'customer_invoice_lines'))
    assert not (NEW_HEADER_COLUMNS & table_columns(path, 'customer_invoices'))
    assert not (NEW_RATE_RECORD_COLUMNS & table_columns(path, 'rate_records'))
    assert permission_exists(path, v244.OVERRIDE_PERMISSION) is False
    assert _count(path, 'SELECT COUNT(*) FROM permission_set_permissions '
                        'WHERE permission_code = ?',
                  [v244.OVERRIDE_PERMISSION]) == 0
    assert _count(path, 'SELECT COUNT(*) FROM enum_types') == 0
    assert _count(path, 'SELECT COUNT(*) FROM enum_values') == 0
    assert _count(path, 'SELECT COUNT(*) FROM control_parameter_defs') == 0
    assert _count(path, 'SELECT COUNT(*) FROM control_parameter_values') == 0

    conn = sqlite3.connect(str(path))
    try:
        required, bindings = conn.execute(
            'SELECT required_permissions, bo_bindings FROM menus '
            'WHERE menu_code = ?', [v244.MENU_CODE]).fetchone()
    finally:
        conn.close()
    assert v244.OVERRIDE_PERMISSION not in (required or '')
    assert v244.OVERRIDE_ACTION not in (bindings or '')

    assert v244.verify(path) is False

    # 回滚幂等
    assert v244.rollback(path) is True