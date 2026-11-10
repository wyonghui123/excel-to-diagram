# ALLOW_RAW_SQL: 本文件含裸 SQL 构造迁移前后数据与 CHECK 约束校验，守卫豁免
# -*- coding: utf-8 -*-
"""v242 开票完备性迁移测试 —— 5 列 / 权限 / 菜单 / doc_flow / 索引 / 回滚。

依据: docs/specs/s8-customer-invoice-wave-c/spec.md §4
夹具: meta/tests/factories/_customer_invoice_helpers.py（build_file）
"""
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v242__customer_invoice_wave_c as v242
from meta.tests.factories._customer_invoice_helpers import (
    ORDER_LINE_DELIVERY,
    build_file,
    doc_flow_rule,
    doc_flow_rule_count,
    index_names,
    permission_exists,
    permission_grant_set_codes,
    seed_permission_sets,
    set_billing_plan_fields,
    table_columns,
)

NEW_COLUMNS = {name for name, _ddl in v242.NEW_COLUMNS}


def _db_file(tmp_path):
    path = tmp_path / 'app.db'
    conn = build_file(path, with_return_source=False)
    seed_permission_sets(conn)
    conn.close()
    return path


def _insert_line(conn, source_doc_type, line_no=1):
    """最小发票行：只填 NOT NULL 列，来源类型由参数控制。"""
    conn.execute(
        'INSERT INTO customer_invoice_lines (invoice_id, line_no, line_type_id, '
        'source_doc_type, shipment_line_id, description, uom_id, qty, '
        'unit_price, tax_code_id, tax_rate_percent) '
        "VALUES (1, ?, 4, ?, 81, '退货', 21, -5, 10, 31, 13)",
        [line_no, source_doc_type])


def test_upgrade_adds_columns_permission_rule_indexes(tmp_path):
    path = _db_file(tmp_path)

    assert v242.migrate(path, skip_backup=True) is True
    assert v242.verify(path) is True

    assert NEW_COLUMNS <= table_columns(path, 'sales_order_lines')

    assert permission_exists(path, v242.SUBMIT_PERMISSION) is True
    assert permission_grant_set_codes(
        path, v242.SUBMIT_PERMISSION) == {'admin', 'default'}

    assert doc_flow_rule(path, v242.RULE_ID) == {
        'source_bo': 'shipment_line',
        'target_bo': 'customer_invoice_line',
        'source_qty_field': 'qty',
        'pool': 'billing',
        'status': 'active',
    }

    indexes = index_names(path)
    assert 'idx_sol_billing_plan' in indexes
    assert 'idx_cil_original_line' in indexes


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)

    assert v242.migrate(path, skip_backup=True) is True
    assert v242.migrate(path, skip_backup=True) is True

    assert permission_exists(path, v242.SUBMIT_PERMISSION) is True
    assert doc_flow_rule_count(path, v242.RULE_ID) == 1
    assert v242.verify(path) is True


def test_verify_rejects_invalid_values(tmp_path):
    path = _db_file(tmp_path)
    assert v242.migrate(path, skip_backup=True) is True

    set_billing_plan_fields(path, ORDER_LINE_DELIVERY,
                            billing_proration='monthly')
    assert v242.verify(path) is False

    set_billing_plan_fields(path, ORDER_LINE_DELIVERY,
                            billing_proration='daily',
                            billing_period_count=61)
    assert v242.verify(path) is False

    set_billing_plan_fields(path, ORDER_LINE_DELIVERY,
                            billing_period_count=12)
    assert v242.verify(path) is True


def test_rollback_removes_all(tmp_path):
    path = _db_file(tmp_path)
    assert v242.migrate(path, skip_backup=True) is True

    assert v242.rollback(path) is True

    assert not (NEW_COLUMNS & table_columns(path, 'sales_order_lines'))
    assert permission_exists(path, v242.SUBMIT_PERMISSION) is False
    assert doc_flow_rule_count(path, v242.RULE_ID) == 0
    indexes = index_names(path)
    assert 'idx_sol_billing_plan' not in indexes
    assert 'idx_cil_original_line' not in indexes
    assert v242.verify(path) is False

    # 回滚幂等
    assert v242.rollback(path) is True


def test_upgrade_rebuilds_line_table_for_return_shipment_source(tmp_path):
    """v236 的 CHECK 不含 return_shipment：升级重建表并保留既有行。"""
    path = _db_file(tmp_path)

    conn = sqlite3.connect(str(path))
    _insert_line(conn, 'shipment')
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        _insert_line(conn, 'return_shipment')
    conn.rollback()
    conn.close()

    assert v242.migrate(path, skip_backup=True) is True
    assert v242.verify(path) is True

    conn = sqlite3.connect(str(path))
    _insert_line(conn, 'return_shipment', line_no=2)
    conn.commit()
    rows = conn.execute(
        'SELECT source_doc_type FROM customer_invoice_lines ORDER BY id'
    ).fetchall()
    conn.close()
    assert [row[0] for row in rows] == ['shipment', 'return_shipment']