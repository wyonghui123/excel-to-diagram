# -*- coding: utf-8 -*-
"""收货单整单红冲测试（spec-receipt-object-model §7）

口径：
  · 红冲 = 新建红字单（document_category='return'）并自动过账；
  · 红字行数量保持正数，净量贡献为负（分配 / 计划行 / 履约三处）；
  · 仅 completion_source='receipt' 的完成可被回退（R-RC-10）；
  · 一张已过账单只允许一张有效红字单（R-RC-REVERSAL）。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.tests.receipt_test_doubles import MemDS, seeded_db

DOC_TYPE_STD = 1
DOC_TYPE_RETURN = 2


def _svc(conn):
    return ReceiptService(MemDS(conn))


def _create(conn, qty=100.0, **line_extra):
    line = {'schedule_id': 1, 'qty_received': qty}
    line.update(line_extra)
    return _svc(conn).create_receipt(
        {'document_type_id': DOC_TYPE_STD, 'receipt_date': '2026-11-01',
         'source_doc_id': 1}, [line])


def _posted(conn, qty=100.0, **line_extra):
    svc = _svc(conn)
    receipt = _create(conn, qty, **line_extra)
    svc.post(receipt['id'])
    return receipt


def _row(conn, table, row_id):
    return MemDS(conn).query(
        'SELECT * FROM %s WHERE id = ?' % table, [row_id])[0]


def test_reverse_creates_red_document_and_negates_facts():
    conn = seeded_db()
    original = _posted(conn)

    result = _svc(conn).reverse(original['id'], remark='质检不合格')

    assert result['status'] == 'reversed'
    assert result['reversal_receipt_no'] == 'RCV-202611-000002'
    assert result['order_ids'] == [1]

    reversed_header = _row(conn, 'receipts', original['id'])
    assert reversed_header['status'] == 'reversed'
    assert reversed_header['reversed_at']

    red = _row(conn, 'receipts', result['reversal_receipt_id'])
    assert red['document_type_id'] == DOC_TYPE_RETURN
    assert red['reversal_of_receipt_id'] == original['id']
    assert red['status'] == 'posted'
    assert red['remark'] == '质检不合格'

    red_lines = MemDS(conn).query(
        'SELECT * FROM receipt_lines WHERE receipt_id = ?',
        [result['reversal_receipt_id']])
    original_line = MemDS(conn).query(
        'SELECT * FROM receipt_lines WHERE receipt_id = ?', [original['id']])[0]
    assert len(red_lines) == 1
    assert red_lines[0]['reversal_of_line_id'] == original_line['id']
    assert red_lines[0]['qty_received'] == pytest.approx(100.0)
    assert red_lines[0]['status'] == 'posted'


def test_reverse_restores_schedule_and_completion_source():
    conn = seeded_db()
    original = _posted(conn)
    schedule = _row(conn, 'purchase_order_schedules', 1)
    assert schedule['status'] == 'completed'
    assert schedule['completion_source'] == 'receipt'

    _svc(conn).reverse(original['id'])

    schedule = _row(conn, 'purchase_order_schedules', 1)
    assert schedule['received_qty'] == pytest.approx(0.0)
    assert schedule['status'] == 'planned'
    assert schedule['completion_source'] is None
    assert schedule['completion_prev_status'] is None


def test_reverse_writes_negative_allocations():
    conn = seeded_db()
    original = _posted(conn)
    _svc(conn).reverse(original['id'])

    rows = MemDS(conn).query(
        "SELECT target_id, qty FROM demand_allocations "
        "WHERE target_bo = 'receipt' ORDER BY id")
    assert [r['qty'] for r in rows] == [pytest.approx(100.0),
                                        pytest.approx(-100.0)]
    assert sum(r['qty'] for r in rows) == pytest.approx(0.0)


def test_reverse_keeps_manual_completion_when_not_from_receipt():
    """R-RC-10：手工 / 短收结案的完成不因红冲回退。"""
    conn = seeded_db(with_po_allocation=False)
    conn.execute(
        "UPDATE purchase_order_schedules SET status = 'confirmed', "
        "completion_source = 'manual', completion_prev_status = 'planned'")
    conn.commit()
    original = _create(conn, qty=10)
    _svc(conn).post(original['id'])
    _svc(conn).reverse(original['id'])

    schedule = _row(conn, 'purchase_order_schedules', 1)
    assert schedule['status'] == 'confirmed'
    assert schedule['completion_source'] == 'manual'


def test_reverse_rejects_draft_receipt():
    conn = seeded_db()
    draft = _create(conn)
    with pytest.raises(ReceiptError) as exc:
        _svc(conn).reverse(draft['id'])
    assert exc.value.rule == 'RC_STATE_INVALID'


def test_reverse_rejects_second_reversal():
    conn = seeded_db()
    original = _posted(conn)
    svc = _svc(conn)
    # 手工塞一张有效的红字单，原单保持 posted ⇒ 命中 RC_REVERSAL_EXISTS
    conn.execute(
        "INSERT INTO receipts (receipt_no, document_type_id, receipt_date, "
        "source_doc_type, source_doc_id, status, reversal_of_receipt_id) "
        "VALUES ('RCV-202611-999999', 2, '2026-11-01', 'purchase_order', 1, "
        "'posted', ?)", [original['id']])
    conn.commit()
    with pytest.raises(ReceiptError) as exc:
        svc.reverse(original['id'])
    assert exc.value.rule == 'RC_REVERSAL_EXISTS'


def test_reverse_rejects_red_document():
    conn = seeded_db()
    original = _posted(conn)
    result = _svc(conn).reverse(original['id'])
    with pytest.raises(ReceiptError) as exc:
        _svc(conn).reverse(result['reversal_receipt_id'])
    assert exc.value.rule == 'RC_REVERSAL_INVALID'


def test_reverse_requires_positive_net_lines():
    conn = seeded_db(with_po_allocation=False)
    original = _posted(conn, qty=10, qty_rejected=10,
                       rejection_reason_code='DMG',
                       rejection_disposition='scrap')
    with pytest.raises(ReceiptError) as exc:
        _svc(conn).reverse(original['id'])
    assert exc.value.rule == 'RC_REVERSAL_INVALID'
    assert exc.value.field_name == 'lines'


def test_reverse_goes_through_reversal_orchestrator(monkeypatch):
    """D3：收货红冲必须经 ReversalOrchestrator（声明式写面 + 红字单创建器）。"""
    from meta.core import reversal_orchestrator

    conn = seeded_db()
    original = _posted(conn)

    seen = []
    real_execute = reversal_orchestrator.execute

    def spy(ds, **kwargs):
        seen.append((kwargs.get('schema_id'), kwargs.get('doc_id')))
        return real_execute(ds, **kwargs)

    monkeypatch.setattr(reversal_orchestrator, 'execute', spy)
    result = _svc(conn).reverse(original['id'])

    assert seen == [('receipt', original['id'])]
    assert result['reversal_receipt_id']


def test_blocking_invoice_lines_counts_normal_minus_red(tmp_path):
    """R-VI-48：收货行被 ap_match 消耗未抵消时命中；红字边抵消后放行。"""
    from meta.tests.factories._vendor_invoice_helpers import (
        RECEIPT_ID, RECEIPT_LINE_ID, insert_edge, insert_invoice, insert_line,
        make_env, seed_receipt_line,
    )

    ds = make_env(tmp_path)
    seed_receipt_line(ds, qty_received=10.0)
    invoice_id = insert_invoice(ds)
    line_one = insert_line(ds, invoice_id, line_no=1)
    line_two = insert_line(ds, invoice_id, line_no=2)
    service = ReceiptService(ds)

    insert_edge(ds, target_line_id=line_one, quantity=10.0)
    assert service._blocking_invoice_lines(RECEIPT_ID) \
        == [str(RECEIPT_LINE_ID)]
    assert service._blocking_invoice_nos([str(RECEIPT_LINE_ID)]) \
        == ['VI-0001']

    insert_edge(ds, target_line_id=line_two, quantity=10.0,
                quantity_sign='red')
    assert service._blocking_invoice_lines(RECEIPT_ID) == []


def test_reverse_blocked_by_vendor_invoice_consumption(monkeypatch):
    """R-VI-48：被采购发票占用的收货单拒绝红冲（错误契约）。"""
    conn = seeded_db()
    original = _posted(conn)
    monkeypatch.setattr(ReceiptService, '_blocking_invoice_lines',
                        lambda self, receipt_id: ['7401'])
    monkeypatch.setattr(ReceiptService, '_blocking_invoice_nos',
                        lambda self, line_ids: ['VI-0001'])

    with pytest.raises(ReceiptError) as exc:
        _svc(conn).reverse(original['id'])

    assert exc.value.rule == 'RC_CONSUMED_BY_VENDOR_INVOICE'
    assert exc.value.field_name == 'receipt_line_id'
    assert 'VI-0001' in exc.value.message
