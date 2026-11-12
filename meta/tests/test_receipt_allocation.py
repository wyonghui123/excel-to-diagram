# -*- coding: utf-8 -*-
"""收货需求分配测试（spec-receipt-object-model §6.1 / §6.2）

口径：
  · 标准单按 PO 分配剩余量占比拆分，余数归尾行（保证合计 == 净收）；
  · PO 分配与收货分配分段计数，不相加（§6.2）；
  · 无 PO 分配时跳过而不拦截（人工建单场景）。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.tests.receipt_test_doubles import (MemDS, add_po_allocation,
                                             seeded_db)

DOC_TYPE_STD = 1


def _svc(conn):
    return ReceiptService(MemDS(conn))


def _create_and_post(conn, qty):
    svc = _svc(conn)
    receipt = svc.create_receipt(
        {'document_type_id': DOC_TYPE_STD, 'receipt_date': '2026-11-01',
         'source_doc_id': 1},
        [{'schedule_id': 1, 'qty_received': qty}])
    svc.post(receipt['id'])
    return receipt


def _receipt_allocations(conn, receipt_id):
    return MemDS(conn).query(
        "SELECT demand_line_id, qty FROM demand_allocations "
        "WHERE target_bo = 'receipt' AND target_id = ? ORDER BY id", [receipt_id])


def test_split_by_remaining_ratio():
    conn = seeded_db(with_po_allocation=False, promised_qty=100)
    add_po_allocation(conn, demand_line_id=1, qty=60)
    add_po_allocation(conn, demand_line_id=2, qty=40)
    conn.commit()

    receipt = _create_and_post(conn, 50)
    rows = _receipt_allocations(conn, receipt['id'])
    assert [r['qty'] for r in rows] == [pytest.approx(30.0),
                                        pytest.approx(20.0)]
    assert sum(r['qty'] for r in rows) == pytest.approx(50.0)


def test_last_line_takes_remainder():
    conn = seeded_db(with_po_allocation=False, promised_qty=10)
    add_po_allocation(conn, demand_line_id=1, qty=1)
    add_po_allocation(conn, demand_line_id=2, qty=2)
    conn.commit()

    receipt = _create_and_post(conn, 1)
    rows = _receipt_allocations(conn, receipt['id'])
    assert [r['qty'] for r in rows] == [pytest.approx(0.3333),
                                        pytest.approx(0.6667)]
    assert sum(r['qty'] for r in rows) == pytest.approx(1.0)


def test_po_allocation_and_receipt_allocation_are_separate():
    """§6.2：PO 分配行不被收货分配覆盖 / 相加。"""
    conn = seeded_db(with_po_allocation=False)
    add_po_allocation(conn, demand_line_id=1, qty=100)
    conn.commit()

    receipt = _create_and_post(conn, 100)
    po_rows = MemDS(conn).query(
        "SELECT qty FROM demand_allocations WHERE target_bo = 'purchase_order'")
    receipt_rows = _receipt_allocations(conn, receipt['id'])
    assert [r['qty'] for r in po_rows] == [pytest.approx(100.0)]
    assert [r['qty'] for r in receipt_rows] == [pytest.approx(100.0)]


def test_exhausted_allocation_rejected():
    conn = seeded_db(with_po_allocation=False, promised_qty=200)
    add_po_allocation(conn, demand_line_id=1, qty=100)
    conn.commit()

    _create_and_post(conn, 100)
    svc = _svc(conn)
    second = svc.create_receipt(
        {'document_type_id': DOC_TYPE_STD, 'receipt_date': '2026-11-01',
         'source_doc_id': 1},
        [{'schedule_id': 1, 'qty_received': 50}])
    with pytest.raises(ReceiptError) as exc:
        svc.post(second['id'])
    assert exc.value.rule == 'RC_ALLOC_EXHAUSTED'
    assert exc.value.field_name == 'schedule_id'


def test_allocation_over_remaining_rejected():
    conn = seeded_db(with_po_allocation=False, promised_qty=200)
    add_po_allocation(conn, demand_line_id=1, qty=100)
    conn.commit()

    svc = _svc(conn)
    receipt = svc.create_receipt(
        {'document_type_id': DOC_TYPE_STD, 'receipt_date': '2026-11-01',
         'source_doc_id': 1},
        [{'schedule_id': 1, 'qty_received': 150}])
    with pytest.raises(ReceiptError) as exc:
        svc.post(receipt['id'])
    assert exc.value.rule == 'RC_ALLOC_OVER'
    assert exc.value.field_name == 'qty_received'


def test_no_po_allocation_skips_but_posts():
    conn = seeded_db(with_po_allocation=False)
    receipt = _create_and_post(conn, 100)
    assert _receipt_allocations(conn, receipt['id']) == []
    assert MemDS(conn).query(
        'SELECT status FROM receipts WHERE id = ?', [receipt['id']])[0][
        'status'] == 'posted'
