# -*- coding: utf-8 -*-
"""v232 销售发票单据类别迁移测试 —— 加列 / 回填 / 幂等 / 回滚。

依据: docs/specs/research-fusion-billing-deep-dive-2026-11-09.md §7
夹具: meta/tests/factories/_customer_invoice_helpers.py（bare file）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v231__customer_invoice as v231
from meta.migrations import v232__customer_invoice_document_category as v232
from meta.tests.factories._customer_invoice_helpers import (
    build_bare_file,
    drop_column,
    insert_invoice_without_category,
    invoice_categories,
    table_columns,
)


def _db_file(tmp_path):
    path = tmp_path / 'app.db'
    conn = build_bare_file(path)
    conn.close()
    return path


def test_adds_column_and_backfills_by_type(tmp_path):
    path = _db_file(tmp_path)
    v231.migrate(path, skip_backup=True)

    # 模拟 v231 之后、v232 之前的旧库
    drop_column(path, 'customer_invoices', 'document_category')
    insert_invoice_without_category(path, 'INV-OLD-1', 'SINV')
    insert_invoice_without_category(path, 'RED-OLD-1', 'SCR')

    assert 'document_category' not in table_columns(path, 'customer_invoices')
    assert v232.migrate(path, skip_backup=True) is True

    assert invoice_categories(path) == {
        'INV-OLD-1': 'invoice', 'RED-OLD-1': 'credit_memo'}
    assert v232.verify(path) is True


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)
    v231.migrate(path, skip_backup=True)

    assert v232.migrate(path, skip_backup=True) is True
    assert v232.migrate(path, skip_backup=True) is True
    assert 'document_category' in table_columns(path, 'customer_invoices')
    assert v232.verify(path) is True


def test_rollback_drops_column(tmp_path):
    path = _db_file(tmp_path)
    v231.migrate(path, skip_backup=True)
    v232.migrate(path, skip_backup=True)

    assert v232.rollback(path) is True
    assert 'document_category' not in table_columns(path, 'customer_invoices')
