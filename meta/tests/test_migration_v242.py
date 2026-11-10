# -*- coding: utf-8 -*-
"""v242 开票完备性迁移测试 —— 5 列 / 权限 / 菜单 / doc_flow / 索引 / 回滚。

依据: docs/specs/s8-customer-invoice-wave-c/spec.md §4
夹具: meta/tests/factories/_customer_invoice_helpers.py（build_file）
"""
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
    conn = build_file(path)
    seed_permission_sets(conn)
    conn.close()
    return path


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