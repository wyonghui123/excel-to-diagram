# -*- coding: utf-8 -*-
"""v231 销售发票迁移测试（S8 Wave A）—— 建表 / 种子 / 回填 / 回滚。

依据: docs/specs/s8-customer-invoice-wave-a/spec.md §8.4（迁移 4 条）
夹具: meta/tests/factories/_customer_invoice_helpers.py（bare file：上游表已建）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v231__customer_invoice as v231
from meta.services.document_number_service import DocumentNumberService
from meta.tests.factories._customer_invoice_helpers import (
    ORDER_LINE_DELIVERY,
    ORDER_LINE_PLAN,
    build_bare_file,
    fetch_all,
    fetch_one,
    make_ds,
)


def _db_file(tmp_path):
    path = tmp_path / 'app.db'
    conn = build_bare_file(path)
    conn.close()
    return path


def test_migrate_creates_tables_indexes_and_verify_passes(tmp_path):
    path = _db_file(tmp_path)

    assert v231.migrate(path, skip_backup=True) is True
    assert v231.verify(path) is True

    import sqlite3
    conn = sqlite3.connect(str(path))
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {'customer_invoices', 'customer_invoice_lines',
                'customer_invoice_schedules'} <= tables
    finally:
        conn.close()


def test_migrate_seeds_types_sequences_and_numbering_works(tmp_path):
    path = _db_file(tmp_path)
    v231.migrate(path, skip_backup=True)

    import sqlite3
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        service = DocumentNumberService(make_ds(conn))
        sinv = fetch_one(
            conn,
            "SELECT id FROM type_definitions WHERE code='SINV' AND level='header'")
        scr = fetch_one(
            conn,
            "SELECT id FROM type_definitions WHERE code='SCR' AND level='header'")
        assert service.allocate_for(
            'customer_invoice',
            {'invoice_date': '2026-11-09',
             'document_type_id': sinv['id']}, required=True) \
            == 'SINV-202611-00001'
        assert service.allocate_for(
            'customer_invoice',
            {'invoice_date': '2026-11-09',
             'document_type_id': scr['id']}, required=True) \
            == 'SCR-202611-00001'
    finally:
        conn.close()


def test_backfill_marks_milestone_with_billing_plan_as_plan(tmp_path):
    path = _db_file(tmp_path)
    v231.migrate(path, skip_backup=True)

    import sqlite3
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = {
            row['id']: row['billing_relevance']
            for row in fetch_all(
                conn, 'SELECT id, billing_relevance FROM sales_order_lines')
        }
        assert rows[ORDER_LINE_DELIVERY] == 'plan'
        assert rows[ORDER_LINE_PLAN] == 'delivery'
    finally:
        conn.close()


def test_migrate_seeds_doc_flow_rule_permissions_and_grants(tmp_path):
    path = _db_file(tmp_path)
    v231.migrate(path, skip_backup=True)

    import sqlite3
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rule = fetch_one(
            conn, 'SELECT * FROM doc_flow_rule WHERE rule_id = ?',
            ['shipment_to_customer_invoice'])
        assert rule['source_bo'] == 'shipment_line'
        assert rule['target_bo'] == 'customer_invoice_line'
        permissions = fetch_all(
            conn, "SELECT code FROM permissions WHERE code LIKE 'customer_invoice:%'")
        assert len(permissions) == 7
        assert {row['code'] for row in permissions} >= {
            'customer_invoice:customer_invoice_print',
            'customer_invoice:customer_invoice_credit_memo',
        }
        granted = fetch_all(
            conn,
            "SELECT permission_code FROM permission_set_permissions "
            "WHERE permission_code LIKE 'customer_invoice:%'")
        assert len(granted) == 14
    finally:
        conn.close()


def test_verify_fails_before_migrate(tmp_path):
    path = _db_file(tmp_path)

    assert v231.verify(path) is False


def test_rollback_removes_invoice_tables(tmp_path):
    path = _db_file(tmp_path)
    v231.migrate(path, skip_backup=True)

    assert v231.rollback(path) is True

    import sqlite3
    conn = sqlite3.connect(str(path))
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert not ({'customer_invoices', 'customer_invoice_lines',
                     'customer_invoice_schedules'} & tables)
    finally:
        conn.close()
