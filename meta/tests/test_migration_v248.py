# ALLOW_RAW_SQL: 本文件含裸 SQL 构造迁移前后数据与 CHECK 约束校验，守卫豁免
# -*- coding: utf-8 -*-
"""v248 服务确认开票迁移测试 —— 规则 / 索引 / 来源 CHECK 重建 / 回滚。

依据: docs/specs/sales-invoice-pricing-spec-2026-11-10.md §11.3.3 缺口①
夹具: meta/tests/factories/_customer_invoice_helpers.py（build_file）
"""
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v248__service_confirmation_invoice as v248
from meta.tests.factories._customer_invoice_helpers import (
    build_file,
    doc_flow_rule,
    doc_flow_rule_count,
    index_names,
)


def _db_file(tmp_path):
    path = tmp_path / 'app.db'
    conn = build_file(path, with_return_source=False)
    conn.close()
    return path


def _insert_shipment_line(conn, line_no=1):
    conn.execute(
        'INSERT INTO customer_invoice_lines (invoice_id, line_no, line_type_id, '
        'source_doc_type, shipment_line_id, description, uom_id, qty, '
        'unit_price, tax_code_id, tax_rate_percent) '
        "VALUES (1, ?, 4, 'shipment', 81, '发货', 21, 10, 10, 31, 13)",
        [line_no])


def _insert_service_line(conn, line_no=1, schedule_id=81):
    conn.execute(
        'INSERT INTO customer_invoice_lines (invoice_id, line_no, line_type_id, '
        'source_doc_type, schedule_id, description, uom_id, qty, '
        'unit_price, tax_code_id, tax_rate_percent) '
        "VALUES (1, ?, 4, 'service_confirmation', ?, '服务', 21, 5, 20, 31, 13)",
        [line_no, schedule_id])


def test_upgrade_writes_rule_index_and_rebuilds_source_check(tmp_path):
    path = _db_file(tmp_path)

    conn = sqlite3.connect(str(path))
    _insert_shipment_line(conn)
    conn.commit()
    # v236/v242 的互斥 CHECK 不允许 service_confirmation 携带 schedule_id
    with pytest.raises(sqlite3.IntegrityError):
        _insert_service_line(conn)
    conn.rollback()
    conn.close()

    assert v248.migrate(path, skip_backup=True) is True
    assert v248.verify(path) is True

    assert doc_flow_rule(path, v248.RULE_ID) == {
        'source_bo': 'sales_order_schedule',
        'target_bo': 'customer_invoice_line',
        'source_qty_field': 'promised_qty',
        'pool': 'billing',
        'status': 'active',
    }
    assert v248.INDEX_NAME in index_names(path)

    conn = sqlite3.connect(str(path))
    _insert_service_line(conn, line_no=2)
    conn.commit()
    rows = conn.execute(
        'SELECT source_doc_type FROM customer_invoice_lines ORDER BY id'
    ).fetchall()
    conn.close()
    assert [row[0] for row in rows] == ['shipment', 'service_confirmation']


def test_migrate_is_idempotent(tmp_path):
    path = _db_file(tmp_path)

    assert v248.migrate(path, skip_backup=True) is True
    assert v248.migrate(path, skip_backup=True) is True

    assert doc_flow_rule_count(path, v248.RULE_ID) == 1
    assert v248.verify(path) is True


def test_verify_rejects_wrong_pool(tmp_path):
    path = _db_file(tmp_path)
    assert v248.migrate(path, skip_backup=True) is True

    conn = sqlite3.connect(str(path))
    conn.execute('UPDATE doc_flow_rule SET pool = ? WHERE rule_id = ?',
                 ['delivery', v248.RULE_ID])
    conn.commit()
    conn.close()

    assert v248.verify(path) is False


def test_rollback_removes_rule_and_index_but_keeps_source_check(tmp_path):
    path = _db_file(tmp_path)
    assert v248.migrate(path, skip_backup=True) is True

    assert v248.rollback(path) is True

    assert doc_flow_rule_count(path, v248.RULE_ID) == 0
    assert v248.INDEX_NAME not in index_names(path)
    assert v248.verify(path) is False

    # 重建后的 CHECK 为超集（不回退），避免已有服务行失去约束兼容
    conn = sqlite3.connect(str(path))
    _insert_service_line(conn)
    conn.commit()
    conn.close()

    # 回滚幂等
    assert v248.rollback(path) is True