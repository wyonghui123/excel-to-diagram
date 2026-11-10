# -*- coding: utf-8 -*-
"""v240 贷项反向 doc_flow 规则迁移测试 —— 插规则 / 幂等 / 回滚。

依据: docs/specs/s8-customer-invoice-wave-a/spec.md §18
夹具: meta/tests/factories/_customer_invoice_helpers.py（build_bare_file）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v240__customer_invoice_credit_doc_flow as v240
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


def test_upgrade_inserts_credit_doc_flow_rule(tmp_path):
    path = _db_file(tmp_path)

    assert v240.migrate(path, skip_backup=True) is True
    assert v240.verify(path) is True

    assert doc_flow_rule(path, v240.RULE_ID) == {
        'source_bo': 'customer_invoice_line',
        'target_bo': 'customer_invoice_line',
        'source_qty_field': 'qty',
        'pool': 'billing',
        'status': 'active',
    }


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)

    assert v240.migrate(path, skip_backup=True) is True
    assert v240.migrate(path, skip_backup=True) is True
    assert doc_flow_rule_count(path, v240.RULE_ID) == 1

    # 二次执行把已停用规则恢复 active
    set_doc_flow_rule_status(path, v240.RULE_ID, 'deprecated')
    assert v240.verify(path) is False
    assert v240.migrate(path, skip_backup=True) is True
    assert v240.verify(path) is True


def test_rollback_removes_rule(tmp_path):
    path = _db_file(tmp_path)
    assert v240.migrate(path, skip_backup=True) is True

    assert v240.rollback(path) is True
    assert doc_flow_rule_count(path, v240.RULE_ID) == 0
    assert v240.verify(path) is False
