# -*- coding: utf-8 -*-
"""v237 销售发票单据类别迁移测试 —— 加列 / 回填 / 幂等 / 回滚。

依据: docs/specs/research-fusion-billing-deep-dive-2026-11-09.md §7
夹具: meta/tests/factories/_customer_invoice_helpers.py（bare file）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v236__customer_invoice as v236
from meta.migrations import v237__customer_invoice_document_category as v237
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
    v236.migrate(path, skip_backup=True)

    # 模拟 v236 之后、v237 之前的旧库
    drop_column(path, 'customer_invoices', 'document_category')
    insert_invoice_without_category(path, 'INV-OLD-1', 'SINV')
    insert_invoice_without_category(path, 'RED-OLD-1', 'SCR')

    assert 'document_category' not in table_columns(path, 'customer_invoices')
    assert v237.migrate(path, skip_backup=True) is True

    assert invoice_categories(path) == {
        'INV-OLD-1': 'invoice', 'RED-OLD-1': 'credit_memo'}
    assert v237.verify(path) is True


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)
    v236.migrate(path, skip_backup=True)

    assert v237.migrate(path, skip_backup=True) is True
    assert v237.migrate(path, skip_backup=True) is True
    assert 'document_category' in table_columns(path, 'customer_invoices')
    assert v237.verify(path) is True


def test_rollback_drops_column(tmp_path):
    path = _db_file(tmp_path)
    v236.migrate(path, skip_backup=True)
    v237.migrate(path, skip_backup=True)

    assert v237.rollback(path) is True
    assert 'document_category' not in table_columns(path, 'customer_invoices')
