# -*- coding: utf-8 -*-
"""采购退货（RTV）验收测试 —— D6 / AC-RP-11 ~ AC-RP-19。

覆盖：退货出库过账、类别一致性、可退量上限、returned_qty 重算、
退货红冲回退、原 PO 不重开、审批维度、序列号出库事件与红冲回退。
"""

import importlib
import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.document_approval_service import DocumentApprovalResolver
from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.services.serial_number_service import SerialNumberService
from meta.tests.receipt_test_doubles import (MemDS, add_order, add_order_line,
                                             add_schedule, seeded_db)

RETURN_PO_TYPE = 3
VENDOR_RETURN_TYPE = 4
RED_RECEIPT_TYPE = 2


def _svc(conn):
    return ReceiptService(MemDS(conn))


def _row(conn, table, row_id):
    return MemDS(conn).query(
        'SELECT * FROM %s WHERE id = ?' % table, [row_id])[0]


def _return_setup(conn, qty=30.0, origin_receipt_id=None, promised_qty=None):
    """在标准种子之上追加一张退货采购单 + 计划行。"""
    add_order(conn, oid=2, order_no='RPO-0001',
              document_type_id=RETURN_PO_TYPE,
              origin_purchase_order_id=1,
              origin_receipt_id=origin_receipt_id,
              return_reason='质量不合格')
    add_order_line(conn, lid=200, oid=2, qty=promised_qty or qty)
    add_schedule(conn, sid=2, oid=2, lid=200,
                 promised_qty=promised_qty or qty, status='confirmed')
    return {
        'document_type_id': VENDOR_RETURN_TYPE,
        'receipt_date': '2026-11-05',
        'source_doc_id': 2,
    }


def _return_receipt(svc, conn, qty=30.0, origin_receipt_id=None, **overrides):
    header = _return_setup(conn, qty=qty, origin_receipt_id=origin_receipt_id)
    header.update(overrides)
    return svc.create_receipt(
        header, [{'schedule_id': 2, 'qty_received': qty}])


# ---------------- AC-RP-11 / 13 / 14 ----------------

def test_return_receipt_posts_outbound_and_updates_returned_qty(monkeypatch):
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _return_receipt(svc, conn, qty=30)

    captured = {}

    def fake_inventory(header, checked, transaction_type, direction='in'):
        captured['txn_type'] = transaction_type
        captured['direction'] = direction
        return {checked[0]['line']['id']: 501}

    def fake_edges(checked, txns, rule_id='receipt_line_to_inventory_txn'):
        captured['rule_id'] = rule_id

    monkeypatch.setattr(svc, '_post_receipt_inventory', fake_inventory)
    monkeypatch.setattr(svc, '_write_receipt_inbound_edges', fake_edges)

    result = svc.post(receipt['id'])

    assert result['status'] == 'posted'
    assert captured['txn_type'] == 'RETURN_TO_VENDOR'
    assert captured['direction'] == 'out'
    assert captured['rule_id'] == 'receipt_line_to_return_out_txn'

    schedule = _row(conn, 'purchase_order_schedules', 2)
    assert schedule['returned_qty'] == pytest.approx(30.0)
    assert schedule['received_qty'] == pytest.approx(0.0)

    allocations = MemDS(conn).query(
        "SELECT * FROM demand_allocations WHERE target_bo = 'receipt'")
    assert allocations == []


def test_return_receipt_with_standard_po_is_rejected():
    conn = seeded_db()
    svc = _svc(conn)
    with pytest.raises(ReceiptError) as exc:
        svc.create_receipt(
            {'document_type_id': VENDOR_RETURN_TYPE,
             'receipt_date': '2026-11-05', 'source_doc_id': 1},
            [{'schedule_id': 1, 'qty_received': 10}])
    assert exc.value.rule == 'RC_CATEGORY_MISMATCH'


def test_return_receipt_rejects_rejected_qty():
    conn = seeded_db()
    svc = _svc(conn)
    header = _return_setup(conn, qty=10)
    receipt = svc.create_receipt(
        header, [{'schedule_id': 2, 'qty_received': 10, 'qty_rejected': 1,
                  'rejection_reason_code': 'DMG',
                  'rejection_disposition': 'return_to_supplier'}])
    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'RC_RETURN_REJECTED_NOT_ALLOWED'


# ---------------- AC-RP-15 ----------------

def test_return_over_original_receipt_limit_is_rejected():
    conn = seeded_db()
    svc = _svc(conn)
    original = svc.create_receipt(
        {'document_type_id': 1, 'receipt_date': '2026-11-01',
         'source_doc_id': 1}, [{'schedule_id': 1, 'qty_received': 10}])
    svc.post(original['id'])

    header = _return_setup(conn, qty=12, origin_receipt_id=original['id'])
    receipt = svc.create_receipt(
        header, [{'schedule_id': 2, 'qty_received': 12}])
    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'RC_RETURN_OVER_LIMIT'


# ---------------- 红字单语义 ----------------

def test_red_receipt_cannot_be_posted_directly():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = svc.create_receipt(
        {'document_type_id': RED_RECEIPT_TYPE, 'receipt_date': '2026-11-05',
         'source_doc_id': 1, 'reversal_of_receipt_id': 1},
        [{'schedule_id': 1, 'qty_received': 10}])
    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'RC_CATEGORY_INVALID'


# ---------------- AC-RP-17 ----------------

def test_return_receipt_reversal_restores_returned_qty():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _return_receipt(svc, conn, qty=30)
    svc.post(receipt['id'])
    assert _row(conn, 'purchase_order_schedules', 2)['returned_qty'] \
        == pytest.approx(30.0)

    result = svc.reverse(receipt['id'])

    assert result['reversal_receipt_id']
    assert _row(conn, 'purchase_order_schedules', 2)['returned_qty'] \
        == pytest.approx(0.0)
    line = MemDS(conn).query(
        'SELECT * FROM receipt_lines WHERE receipt_id = ?', [receipt['id']])[0]
    assert line['status'] == 'reversed'
    red = _row(conn, 'receipts', result['reversal_receipt_id'])
    assert red['document_type_id'] == RED_RECEIPT_TYPE
    assert red['reversal_of_receipt_id'] == receipt['id']


# ---------------- AC-RP-18 ----------------

def test_return_does_not_reopen_original_order():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _return_receipt(svc, conn, qty=30)
    svc.post(receipt['id'])

    original_order = _row(conn, 'purchase_orders', 1)
    original_schedule = _row(conn, 'purchase_order_schedules', 1)
    assert original_order['status'] == 'confirmed'
    assert original_schedule['received_qty'] == pytest.approx(0.0)
    assert original_schedule['returned_qty'] == pytest.approx(0.0)

    return_order = _row(conn, 'purchase_orders', 2)
    assert return_order['origin_purchase_order_id'] == 1
    assert return_order['return_reason'] == '质量不合格'


# ---------------- AC-RP-16 ----------------

def test_approval_record_exposes_document_category():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _return_receipt(svc, conn, qty=10)
    resolver = DocumentApprovalResolver(MemDS(conn))

    record = resolver._load_record('receipts', receipt['id'])
    assert record['document_category'] == 'return'

    standard = svc.create_receipt(
        {'document_type_id': 1, 'receipt_date': '2026-11-01',
         'source_doc_id': 1}, [{'schedule_id': 1, 'qty_received': 1}])
    assert resolver._load_record('receipts', standard['id'])[
        'document_category'] == 'standard'


# ---------------- AC-RP-19 ----------------

_ITEMS_DDL = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    serial_tracked INTEGER DEFAULT 0,
    require_on_receipt INTEGER DEFAULT 0,
    require_on_issue INTEGER DEFAULT 0
);
"""

_INV_TX_DDL = """
CREATE TABLE inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_event_key TEXT,
    source_line_id INTEGER
);
"""


def _serial_conn():
    migration = importlib.import_module('meta.migrations.v202__serial_number_model')
    return_migration = importlib.import_module(
        'meta.migrations.v227__purchase_return_object')
    conn = seeded_db()
    conn.executescript(_ITEMS_DDL)
    conn.executescript(_INV_TX_DDL)
    for table, ddl in migration.TABLES:
        if table == migration.TX_TABLE:
            # v227 重建后的 CHECK 含 return_to_vendor
            conn.executescript(return_migration.SERIAL_TX_DDL)
            continue
        conn.executescript(ddl)
    conn.execute(
        'INSERT INTO items (id, serial_tracked, require_on_receipt, '
        'require_on_issue) VALUES (900, 1, 1, 1)')
    conn.execute(
        'INSERT INTO serial_numbers (id, item_id, org_id, serial_no, '
        "usage_status, current_location_id, source_type, created_at, updated_at) "
        "VALUES (1, 900, 1, 'SN-1', 'in_stores', 7, 'received', "
        "'2026-11-01 00:00:00', '2026-11-01 00:00:00')")
    conn.commit()
    return conn


def test_return_serial_outbound_event_and_reversal():
    conn = _serial_conn()
    svc = _svc(conn)
    receipt = _return_receipt(svc, conn, qty=1)
    line = MemDS(conn).query(
        'SELECT * FROM receipt_lines WHERE receipt_id = ?', [receipt['id']])[0]
    conn.execute(
        'INSERT INTO document_serial_links (doc_type, doc_id, line_id, '
        "serial_id, direction) VALUES ('receipt', ?, ?, 1, 'out')",
        [receipt['id'], line['id']])
    conn.commit()

    serial_svc = SerialNumberService(MemDS(conn))
    serial_svc.precheck_receipt_return(receipt['id'])
    serial_svc.register_receipt_return(receipt['id'], {line['id']: 501})

    serial = _row(conn, 'serial_numbers', 1)
    assert serial['usage_status'] == 'shipped'
    txn = MemDS(conn).query(
        'SELECT * FROM serial_transactions WHERE serial_id = 1')[0]
    assert txn['txn_type'] == 'return_to_vendor'
    assert txn['inventory_transaction_id'] == 501

    serial_svc.reverse_serial_event(501)
    serial = _row(conn, 'serial_numbers', 1)
    assert serial['usage_status'] == 'in_stores'
    assert serial['current_location_id'] == 7


# ---------------- 规则字段守卫 ----------------

def test_return_rule_qty_fields_exist_in_schema():
    """规则声明的源/目标数量字段必须在对应 BO schema 中真实存在。"""
    import yaml

    migration = importlib.import_module(
        'meta.migrations.v227__purchase_return_object')
    rule = migration.RETURN_RULE
    schema_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')

    def _field_ids(bo):
        path = os.path.join(schema_dir, bo + '.yaml')
        with open(path, encoding='utf-8') as f:
            meta = yaml.safe_load(f)
        return {fld['id'] for fld in meta['fields']}

    assert rule['source_qty_field'] in _field_ids(rule['source_bo'])
    assert rule['target_qty_field'] in _field_ids(rule['target_bo'])
