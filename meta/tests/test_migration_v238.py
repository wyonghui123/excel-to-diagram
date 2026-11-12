# -*- coding: utf-8 -*-
"""v238 发票行改价差额迁移测试 —— 加列 / 回填 / 幂等 / 回滚。

依据: docs/specs/s8-customer-invoice-wave-a/spec.md §13 / D13 价格变更
夹具: meta/tests/factories/_customer_invoice_helpers.py（bare file）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v236__customer_invoice as v236
from meta.migrations import v238__customer_invoice_line_price_diff as v238
from meta.tests.factories._customer_invoice_helpers import (
    build_bare_file,
    drop_column,
    insert_line_without_price_diff,
    line_price_diffs,
    table_columns,
)


def _db_file(tmp_path):
    path = tmp_path / 'app.db'
    conn = build_bare_file(path)
    conn.close()
    return path


def test_adds_column_and_backfills_diff(tmp_path):
    path = _db_file(tmp_path)
    v236.migrate(path, skip_backup=True)

    # 模拟 v236 之后、v238 之前的旧库
    drop_column(path, 'customer_invoice_lines', 'price_diff_amount')
    insert_line_without_price_diff(path, 'INV-OLD-1', 5, 12, 10)
    insert_line_without_price_diff(path, 'INV-OLD-2', 2, 7)

    assert 'price_diff_amount' not in table_columns(
        path, 'customer_invoice_lines')
    assert v238.migrate(path, skip_backup=True) is True

    diffs = line_price_diffs(path)
    assert diffs == [10.0, 0.0]
    assert v238.verify(path) is True


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)
    v236.migrate(path, skip_backup=True)

    assert v238.migrate(path, skip_backup=True) is True
    assert v238.migrate(path, skip_backup=True) is True
    assert 'price_diff_amount' in table_columns(path, 'customer_invoice_lines')
    assert v238.verify(path) is True


def test_rollback_drops_column(tmp_path):
    path = _db_file(tmp_path)
    v236.migrate(path, skip_backup=True)
    v238.migrate(path, skip_backup=True)

    assert v238.rollback(path) is True
    assert 'price_diff_amount' not in table_columns(
        path, 'customer_invoice_lines')
