# -*- coding: utf-8 -*-
"""v241 计划期次开票迁移测试 —— 规则 / 索引 / 幂等 / 回滚。

依据: docs/specs/s8-customer-invoice-wave-b/spec.md §6
夹具: meta/tests/factories/_customer_invoice_helpers.py（build_bare_file）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v241__customer_invoice_billing_plan as v241
from meta.tests.factories._customer_invoice_helpers import (
    build_bare_file,
    doc_flow_rule,
    doc_flow_rule_count,
    set_doc_flow_rule_status,
)


def _db_file(tmp_path):
    path = tmp_path / 'app.db'
    conn = build_bare_file(path)
    conn.close()
    return path


def test_upgrade_inserts_plan_doc_flow_rule_and_index(tmp_path):
    path = _db_file(tmp_path)

    assert v241.migrate(path, skip_backup=True) is True
    assert v241.verify(path) is True

    assert doc_flow_rule(path, v241.RULE_ID) == {
        'source_bo': 'sales_order_schedule',
        'target_bo': 'customer_invoice_line',
        'source_qty_field': 'billing_percent',
        'pool': 'billing',
        'status': 'active',
    }


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)

    assert v241.migrate(path, skip_backup=True) is True
    assert v241.migrate(path, skip_backup=True) is True
    assert doc_flow_rule_count(path, v241.RULE_ID) == 1

    # 二次执行把已停用规则恢复 active
    set_doc_flow_rule_status(path, v241.RULE_ID, 'deprecated')
    assert v241.verify(path) is False
    assert v241.migrate(path, skip_backup=True) is True
    assert v241.verify(path) is True


def test_rollback_removes_rule_and_index(tmp_path):
    path = _db_file(tmp_path)
    assert v241.migrate(path, skip_backup=True) is True

    assert v241.rollback(path) is True
    assert doc_flow_rule_count(path, v241.RULE_ID) == 0
    assert v241.verify(path) is False