# -*- coding: utf-8 -*-
"""收货单服务测试（spec-receipt-object-model §5.1 / §5.3 / §6）

覆盖：R-RC-0 来源校验、R-RC-1 计划行挂载、R-RC-3 数量、R-RC-4 拒收完整性、
R-RC-5 超收原子拒绝、R-RC-6 过账不可改、R-RC-10 完工来源、R-RC-13 删除守卫。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.tests.receipt_test_doubles import (MemDS, add_order, add_schedule,
                                             seeded_db)

DOC_TYPE_STD = 1


def _svc(conn):
    return ReceiptService(MemDS(conn))


def _header(**extra):
    header = {'document_type_id': DOC_TYPE_STD, 'receipt_date': '2026-11-01',
              'source_doc_id': 1}
    header.update(extra)
    return header


def _create(svc, qty=100.0, schedule_id=1, header=None, **line_extra):
    line = {'schedule_id': schedule_id, 'qty_received': qty}
    line.update(line_extra)
    return svc.create_receipt(_header(**(header or {})), [line])


def _row(conn, table, row_id):
    return MemDS(conn).query(
        'SELECT * FROM %s WHERE id = ?' % table, [row_id])[0]


# ---------------- 创建 ----------------

def test_create_applies_defaults_and_allocates_number():
    conn = seeded_db()
    result = _create(_svc(conn))

    assert result['receipt_no'] == 'RCV-202611-000001'
    assert result['status'] == 'draft'
    header = _row(conn, 'receipts', result['id'])
    assert header['source_doc_type'] == 'purchase_order'
    assert header['source_doc_no'] == 'PO-0001'
    assert header['supplier_party_id'] == 500
    assert header['org_id'] == 1
    assert header['deliver_to_location_id'] == 7

    line = MemDS(conn).query(
        'SELECT * FROM receipt_lines WHERE receipt_id = ?', [result['id']])[0]
    assert line['line_no'] == '1'
    assert line['order_id'] == 1
    assert line['order_line_id'] == 100
    assert line['item_id'] == 900
    assert line['uom_id'] == 3
    assert line['status'] == 'draft'


def test_create_rejects_schedule_of_another_order():
    conn = seeded_db()
    add_order(conn, oid=2, order_no='PO-0002')
    add_schedule(conn, sid=2, oid=2)
    with pytest.raises(ReceiptError) as exc:
        _create(_svc(conn), schedule_id=2)
    assert exc.value.rule == 'RC_SCHEDULE_INVALID'
    assert exc.value.field_name == 'schedule_id'


def test_create_rejects_non_delivery_schedule_kind():
    conn = seeded_db()
    conn.execute("UPDATE purchase_order_schedules SET schedule_kind = 'billing'")
    with pytest.raises(ReceiptError) as exc:
        _create(_svc(conn))
    assert exc.value.rule == 'RC_SCHEDULE_INVALID'


def test_create_rejects_invalid_qty():
    conn = seeded_db()
    svc = _svc(conn)
    with pytest.raises(ReceiptError) as exc:
        _create(svc, qty=0)
    assert exc.value.rule == 'RC_QTY_INVALID'
    with pytest.raises(ReceiptError) as exc:
        _create(svc, qty=10, qty_rejected=11, rejection_reason_code='DMG',
                rejection_disposition='scrap')
    assert exc.value.rule == 'RC_QTY_INVALID'


def test_create_rejects_incomplete_rejection():
    conn = seeded_db()
    with pytest.raises(ReceiptError) as exc:
        _create(_svc(conn), qty=10, qty_rejected=2)
    assert exc.value.rule == 'RC_REJECTION_INCOMPLETE'
    assert exc.value.field_name == 'rejection_reason_code'

    with pytest.raises(ReceiptError) as exc:
        _create(_svc(conn), qty=10, qty_rejected=2, rejection_reason_code='DMG',
                rejection_disposition='unknown')
    assert exc.value.rule == 'RC_REJECTION_INCOMPLETE'


# ---------------- 过账 ----------------

def test_post_writes_schedule_and_derives_fulfillment():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _create(svc, qty=100)
    result = svc.post(receipt['id'])

    assert result['status'] == 'posted'
    assert result['idempotent'] is False
    assert result['order_ids'] == [1]
    assert _row(conn, 'receipts', receipt['id'])['status'] == 'posted'
    line = MemDS(conn).query(
        'SELECT * FROM receipt_lines WHERE receipt_id = ?', [receipt['id']])[0]
    assert line['status'] == 'posted'

    schedule = _row(conn, 'purchase_order_schedules', 1)
    assert schedule['received_qty'] == pytest.approx(100.0)
    assert schedule['status'] == 'completed'
    assert schedule['completion_source'] == 'receipt'
    assert schedule['completion_prev_status'] == 'planned'

    # 履约派生唯一写入口（INV-1）：本服务不直写，只调用 recompute_order
    order = _row(conn, 'purchase_orders', 1)
    assert order['fulfillment_status'] != 'not_started'
    assert order['fulfillment_derived_at']

    # 需求分配：target_bo='receipt' 且合计等于净收
    allocations = MemDS(conn).query(
        "SELECT * FROM demand_allocations WHERE target_bo = 'receipt'")
    assert len(allocations) == 1
    assert allocations[0]['qty'] == pytest.approx(100.0)


def test_post_separates_rejected_qty_from_net():
    """R-RC-18：净收与拒收独立缓存，不混算。"""
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _create(svc, qty=50, qty_rejected=5,
                      rejection_reason_code='DMG',
                      rejection_disposition='return_to_supplier')
    svc.post(receipt['id'])

    schedule = _row(conn, 'purchase_order_schedules', 1)
    assert schedule['received_qty'] == pytest.approx(45.0)
    assert schedule['rejected_qty'] == pytest.approx(5.0)
    assert schedule['status'] == 'planned'


def test_post_is_idempotent():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _create(svc)
    svc.post(receipt['id'])
    again = svc.post(receipt['id'])
    assert again['idempotent'] is True
    assert _row(conn, 'purchase_order_schedules', 1)['received_qty'] \
        == pytest.approx(100.0)


def test_post_rejects_over_receipt():
    """R-RC-5：条件 UPDATE 原子累加，超承诺量即拒绝（无 PO 分配时不走分配校验）。"""
    conn = seeded_db(with_po_allocation=False)
    svc = _svc(conn)
    svc.post(_create(svc, qty=60)['id'])
    second = _create(svc, qty=50)
    with pytest.raises(ReceiptError) as exc:
        svc.post(second['id'])
    assert exc.value.rule == 'RC_OVER_RECEIPT'
    assert exc.value.field_name == 'qty_received'
    assert _row(conn, 'purchase_order_schedules', 1)['received_qty'] \
        == pytest.approx(60.0)


def test_post_respects_over_receipt_tolerance():
    conn = seeded_db(percent=10)
    svc = _svc(conn)
    receipt = _create(svc, qty=110)
    svc.post(receipt['id'])
    schedule = _row(conn, 'purchase_order_schedules', 1)
    assert schedule['received_qty'] == pytest.approx(110.0)
    assert schedule['status'] == 'completed'


def test_post_rejects_short_closed_schedule():
    conn = seeded_db()
    conn.execute(
        "UPDATE purchase_order_schedules SET completion_source = 'short_close', "
        "status = 'cancelled'")
    with pytest.raises(ReceiptError) as exc:
        _create(_svc(conn))
    assert exc.value.rule == 'RC_SCHEDULE_CLOSED'


def test_post_requires_lines():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = svc.create_receipt(_header(), [])
    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'RC_EMPTY'


# ---------------- 取消 / 删除守卫 ----------------

def test_cancel_draft_is_idempotent():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _create(svc)
    result = svc.cancel(receipt['id'])
    assert result['status'] == 'cancelled'
    assert _row(conn, 'receipts', receipt['id'])['status'] == 'cancelled'
    again = svc.cancel(receipt['id'])
    assert again['idempotent'] is True


def test_cancel_posted_receipt_rejected():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _create(svc)
    svc.post(receipt['id'])
    with pytest.raises(ReceiptError) as exc:
        svc.cancel(receipt['id'])
    assert exc.value.rule == 'RC_STATE_INVALID'


def test_posted_document_and_line_are_undeletable():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _create(svc)
    svc.post(receipt['id'])
    with pytest.raises(ReceiptError) as exc:
        svc.assert_deletable(receipt['id'])
    assert exc.value.rule == 'RC_POSTED_IMMUTABLE'

    line = MemDS(conn).query(
        'SELECT id FROM receipt_lines WHERE receipt_id = ?', [receipt['id']])[0]
    with pytest.raises(ReceiptError) as exc:
        svc.assert_line_deletable(line['id'])
    assert exc.value.rule == 'RC_POSTED_IMMUTABLE'


def test_update_line_after_post_rejected():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _create(svc)
    svc.post(receipt['id'])
    line = MemDS(conn).query(
        'SELECT id FROM receipt_lines WHERE receipt_id = ?', [receipt['id']])[0]
    with pytest.raises(ReceiptError) as exc:
        svc.update_line(line['id'], {'qty_received': 5})
    assert exc.value.rule == 'RC_POSTED_IMMUTABLE'


def test_validate_new_line_blocked_on_posted_header():
    conn = seeded_db()
    svc = _svc(conn)
    receipt = _create(svc)
    svc.post(receipt['id'])
    with pytest.raises(ReceiptError) as exc:
        svc.validate_new_line(
            {'schedule_id': 1, 'qty_received': 1}, receipt['id'])
    assert exc.value.rule == 'RC_POSTED_IMMUTABLE'


def test_create_rejects_unsupported_source_type():
    conn = seeded_db()
    with pytest.raises(ReceiptError) as exc:
        _svc(conn).create_receipt(
            _header(source_doc_type='transfer_order'), [])
    assert exc.value.rule == 'RC_SOURCE_UNSUPPORTED'
