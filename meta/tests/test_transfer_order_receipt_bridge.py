# -*- coding: utf-8 -*-
"""调拨单 → 收货单桥接测试（spec-transfer-order-object-model §7 / R-TO-8 / R-TO-9）

覆盖：create_from_transfer_order 字段映射与发运余量、post 净收回写、全收自动关闭、
全拒收 net=0、reverse 红冲回退、草稿收货单取消 / 删除不影响调拨单、
ReceiptGuardService 的 TO 来源分支。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.receipt_service import ReceiptError
from meta.tests.transfer_order_test_doubles import (MemDS, release_transfer_order,
                                                    receipt_guard_svc, receipt_svc,
                                                    seeded_db, to_service)

TO_ID = 1
TO_LINE_ID = 100


def _single_line_db(shipped=100.0):
    conn = seeded_db(line_qtys=(100.0,))
    release_transfer_order(conn, TO_ID, {TO_LINE_ID: shipped})
    return conn


def _to_header(conn):
    return MemDS(conn).query(
        'SELECT * FROM transfer_orders WHERE id = ?', [TO_ID])[0]


def _to_line(conn):
    return MemDS(conn).query(
        'SELECT * FROM transfer_order_lines WHERE id = ?', [TO_LINE_ID])[0]


def _receipt_header(conn, receipt_id):
    return MemDS(conn).query(
        'SELECT * FROM receipts WHERE id = ?', [receipt_id])[0]


def _receipt_lines(conn, receipt_id):
    return MemDS(conn).query(
        'SELECT * FROM receipt_lines WHERE receipt_id = ? ORDER BY id',
        [receipt_id])


# ---------------------------------------------------------------------------
# create_from_transfer_order
# ---------------------------------------------------------------------------
def test_create_maps_header_and_only_open_balances():
    conn = seeded_db()
    release_transfer_order(conn, TO_ID, {100: 100.0})
    result = receipt_svc(conn).create_from_transfer_order(TO_ID)

    assert result['status'] == 'draft'
    assert result['line_count'] == 1
    assert result['receipt_no'].startswith('RCV-')

    header = _receipt_header(conn, result['id'])
    assert header['source_doc_type'] == 'transfer_order'
    assert header['source_doc_id'] == TO_ID
    assert header['source_doc_no'] == 'TRF-202611-000001'
    # 收货方法人取调拨单 legal_entity_id；采购专属字段置空
    assert header['org_id'] == 1
    assert header['purchase_org_id'] is None
    assert header['supplier_party_id'] is None
    assert header['deliver_to_location_id'] == 7
    assert header['document_type_id'] == 1

    lines = _receipt_lines(conn, result['id'])
    assert len(lines) == 1
    line = lines[0]
    assert line['source_line_id'] == 100
    assert line['qty_received'] == pytest.approx(100.0)
    assert line['qty_rejected'] == pytest.approx(0.0)
    assert line['schedule_id'] is None
    assert line['order_id'] is None
    assert line['item_id'] == 900
    assert line['uom_id'] == 3


def test_create_rejects_when_no_shipping_balance():
    conn = seeded_db(line_qtys=(100.0,))
    with pytest.raises(ReceiptError) as exc:
        receipt_svc(conn).create_from_transfer_order(TO_ID)
    assert exc.value.rule == 'RC_TRANSFER_NO_BALANCE'
    assert exc.value.field_name == 'lines'


def test_create_rejects_missing_transfer_order():
    conn = seeded_db()
    with pytest.raises(ReceiptError) as exc:
        receipt_svc(conn).create_from_transfer_order(999)
    assert exc.value.rule == 'RC_TRANSFER_NOT_FOUND'


# ---------------------------------------------------------------------------
# post
# ---------------------------------------------------------------------------
def test_post_writes_net_qty_to_transfer_line():
    conn = _single_line_db()
    svc = receipt_svc(conn)
    receipt = svc.create_from_transfer_order(TO_ID)
    # 草稿期下调本次净收量，验证部分收货
    conn.execute('UPDATE receipt_lines SET qty_received = 40 WHERE receipt_id = ?',
                 [receipt['id']])
    result = svc.post(receipt['id'])

    assert result['status'] == 'posted'
    assert result['transfer_order_id'] == TO_ID
    assert result['order_ids'] == []

    line = _to_line(conn)
    assert line['qty_received'] == pytest.approx(40.0)
    header = _to_header(conn)
    assert header['status'] == 'released'
    assert header['fulfillment_status'] == 'partially_received'
    assert _receipt_header(conn, receipt['id'])['status'] == 'posted'


def test_post_full_receipt_auto_closes_transfer_order():
    conn = _single_line_db()
    svc = receipt_svc(conn)
    receipt = svc.create_from_transfer_order(TO_ID)
    svc.post(receipt['id'])

    # TO 来源不要求 vendor 关系（种子库未插 party_relations）
    assert MemDS(conn).query('SELECT id FROM party_relations') == []

    header = _to_header(conn)
    assert header['status'] == 'closed'
    assert header['fulfillment_status'] == 'received'
    line = _to_line(conn)
    assert line['status'] == 'closed'
    assert line['qty_received'] == pytest.approx(100.0)


def test_post_all_rejected_writes_nothing_back():
    conn = _single_line_db()
    svc = receipt_svc(conn)
    receipt = svc.create_from_transfer_order(TO_ID)
    conn.execute(
        "UPDATE receipt_lines SET qty_rejected = qty_received, "
        "rejection_reason_code = 'DMG', rejection_disposition = 'scrap' "
        'WHERE receipt_id = ?', [receipt['id']])

    result = svc.post(receipt['id'])

    assert result['status'] == 'posted'
    line = _to_line(conn)
    assert line['qty_received'] == pytest.approx(0.0)
    header = _to_header(conn)
    assert header['status'] == 'released'
    receipt_line = _receipt_lines(conn, receipt['id'])[0]
    assert receipt_line['status'] == 'posted'
    assert receipt_line['qty_rejected'] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# reverse
# ---------------------------------------------------------------------------
def test_reverse_restores_qty_and_reopens_auto_closed_order():
    conn = _single_line_db()
    svc = receipt_svc(conn)
    receipt = svc.create_from_transfer_order(TO_ID)
    svc.post(receipt['id'])
    assert _to_header(conn)['status'] == 'closed'

    result = svc.reverse(receipt['id'])

    assert result['status'] == 'reversed'
    assert result['transfer_order_id'] == TO_ID
    header = _to_header(conn)
    assert header['status'] == 'released'
    line = _to_line(conn)
    assert line['status'] == 'open'
    assert line['qty_received'] == pytest.approx(0.0)

    red = _receipt_header(conn, result['reversal_receipt_id'])
    assert red['document_type_id'] == 2
    assert red['reversal_of_receipt_id'] == receipt['id']
    assert red['status'] == 'posted'
    assert _receipt_header(conn, receipt['id'])['status'] == 'reversed'


def test_reverse_keeps_manual_close():
    """短收结案后红冲：调拨单保持 closed，不回退。"""
    conn = _single_line_db(shipped=80.0)
    svc = receipt_svc(conn)
    receipt = svc.create_from_transfer_order(TO_ID)
    svc.post(receipt['id'])
    assert _to_header(conn)['fulfillment_status'] == 'partially_received'

    to_service(conn).close(TO_ID)
    assert _to_header(conn)['status'] == 'closed'

    svc.reverse(receipt['id'])

    header = _to_header(conn)
    assert header['status'] == 'closed'
    line = _to_line(conn)
    assert line['status'] == 'closed'
    assert line['qty_received'] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 草稿收货单取消 / 删除
# ---------------------------------------------------------------------------
def test_cancel_and_delete_draft_receipt_do_not_touch_transfer_order():
    conn = _single_line_db()
    svc = receipt_svc(conn)
    receipt = svc.create_from_transfer_order(TO_ID)
    assert _to_line(conn)['qty_received'] == pytest.approx(0.0)

    assert receipt_guard_svc(conn).validate_delete(receipt['id']) is None
    svc.cancel(receipt['id'])

    assert _receipt_header(conn, receipt['id'])['status'] == 'cancelled'
    assert _to_line(conn)['qty_received'] == pytest.approx(0.0)
    assert _to_header(conn)['status'] == 'released'


# ---------------------------------------------------------------------------
# ReceiptGuardService TO 分支
# ---------------------------------------------------------------------------
def test_guard_prepare_create_maps_transfer_header():
    conn = seeded_db()
    header = receipt_guard_svc(conn).prepare_create({
        'source_doc_type': 'transfer_order',
        'source_doc_id': TO_ID,
        'document_type_id': 1,
        'receipt_date': '2026-11-01',
    })

    assert header['source_doc_type'] == 'transfer_order'
    assert header['source_doc_id'] == TO_ID
    assert header['source_doc_no'] == 'TRF-202611-000001'
    assert header['org_id'] == 1
    assert header['purchase_org_id'] is None
    assert header['supplier_party_id'] is None
    assert header['deliver_to_location_id'] == 7
    assert header['receipt_no'].startswith('RCV-')


def test_guard_prepare_create_rejects_standard_with_reversal():
    conn = seeded_db()
    with pytest.raises(ReceiptError) as exc:
        receipt_guard_svc(conn).prepare_create({
            'source_doc_type': 'transfer_order',
            'source_doc_id': TO_ID,
            'document_type_id': 1,
            'receipt_date': '2026-11-01',
            'reversal_of_receipt_id': 99,
        })
    assert exc.value.rule == 'RC_DOC_TYPE_INVALID'
    assert exc.value.field_name == 'reversal_of_receipt_id'


def test_guard_post_keeps_generic_qty_validation():
    conn = _single_line_db()
    svc = receipt_svc(conn)
    receipt = svc.create_from_transfer_order(TO_ID)
    conn.execute('UPDATE receipt_lines SET qty_rejected = 120 WHERE receipt_id = ?',
                 [receipt['id']])

    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'RC_QTY_INVALID'
    assert exc.value.field_name == 'qty_rejected'


def test_guard_post_rejects_closed_transfer_line():
    conn = _single_line_db()
    svc = receipt_svc(conn)
    receipt = svc.create_from_transfer_order(TO_ID)
    conn.execute("UPDATE transfer_order_lines SET status = 'closed' WHERE id = ?",
                 [TO_LINE_ID])

    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'RC_TRANSFER_LINE_CLOSED'
    assert exc.value.field_name == 'source_line_id'
