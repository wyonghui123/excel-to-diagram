# -*- coding: utf-8 -*-
"""W5 采购发票三单匹配服务单测（spec-vendor-invoice-object-model §12 / §13）。

覆盖 DoD：
  D4  超量 → exception（少开不拦）
  D5  matched → post 写边；exception → post 拒绝；override → post 成功留痕
  D6  贷项红冲后 billing / ap_match 净额归零
"""

import pytest

from meta.services.vendor_invoice_match_service import (
    VendorInvoiceError,
    VendorInvoiceMatchService,
    normalize_supplier_invoice_no,
)
from meta.tests.factories import _vendor_invoice_helpers as H


@pytest.fixture()
def ds(tmp_path):
    return H.make_env(tmp_path)


@pytest.fixture()
def service(ds):
    return VendorInvoiceMatchService(ds, ds)


def _capture_edges(monkeypatch):
    captured = []

    def fake_attach(app_ds, platform_ds, rule_id, source_id, target_id,
                    quantity, **kwargs):
        captured.append({
            'rule_id': rule_id,
            'source_id': source_id,
            'target_id': target_id,
            'quantity': quantity,
            'amount': kwargs.get('amount'),
        })
        return True

    monkeypatch.setattr(
        'meta.services.vendor_invoice_match_service.attach_edge', fake_attach)
    return captured


def _header(ds, invoice_id):
    return ds.query('SELECT * FROM vendor_invoices WHERE id = ?', [invoice_id])[0]


def _line(ds, line_id):
    return ds.query('SELECT * FROM vendor_invoice_lines WHERE id = ?', [line_id])[0]


def _ready_receipt_invoice(ds, *, qty=10.0, unit_price=10.0,
                           net=100.0, tax=13.0, gross=113.0,
                           invoice_no='VI-0001', supplier_invoice_no=None,
                           match_mode='gr_based'):
    """标准场景：PO 承诺 10 / 收货 10，发票按收货行开票。"""
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id = H.insert_invoice(
        ds, invoice_no=invoice_no, supplier_invoice_no=supplier_invoice_no,
        match_mode=match_mode, net_amount=net, tax_amount=tax,
        gross_amount=gross)
    H.insert_line(
        ds, invoice_id, qty=qty, unit_price=unit_price,
        net_amount=net, tax_amount=tax, gross_amount=gross,
        receipt_line_id=H.RECEIPT_LINE_ID)
    return invoice_id


# ------------------------------------------------------------------ 匹配结果

def test_gr_based_matched(ds, service):
    invoice_id = _ready_receipt_invoice(ds)

    result = service.match(invoice_id)

    assert result['match_status'] == 'matched'
    assert _header(ds, invoice_id)['match_status'] == 'matched'
    lines = ds.query(
        'SELECT * FROM vendor_invoice_lines WHERE invoice_id = ?', [invoice_id])
    assert lines[0]['match_status'] == 'matched'
    assert float(lines[0]['qty_over_receipt']) == 0.0


def test_qty_over_receipt_is_exception(ds, service):
    invoice_id = _ready_receipt_invoice(
        ds, qty=12.0, net=120.0, tax=15.6, gross=135.6)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert 'qty_over_receipt_tolerance' in (result['match_exception_reason'] or '')
    with pytest.raises(VendorInvoiceError) as exc:
        service.submit(invoice_id)
    assert exc.value.rule == 'VI_MATCH_EXCEPTION'

    # 未提交成功 → 仍是 draft，post 必须拒绝
    with pytest.raises(VendorInvoiceError) as exc2:
        service.post(invoice_id)
    assert exc2.value.rule == 'VI_STATE_INVALID'


def test_under_invoice_is_allowed(ds, service):
    """少开不拦（D4 后半句）：开 6 / 收 10 → matched。"""
    invoice_id = _ready_receipt_invoice(
        ds, qty=6.0, net=60.0, tax=7.8, gross=67.8)

    result = service.match(invoice_id)

    assert result['match_status'] == 'matched'


def test_po_based_uses_promised_minus_returned(ds, service):
    H.seed_purchase_order(ds, promised_qty=10.0, returned_qty=2.0)
    ok_id = H.insert_invoice(ds, invoice_no='VI-PO-1', match_mode='po_based')
    H.insert_line(ds, ok_id, qty=8.0, net_amount=80.0, tax_amount=10.4,
                  gross_amount=90.4, schedule_id=H.SCHEDULE_ID)
    assert service.match(ok_id)['match_status'] == 'matched'

    over_id = H.insert_invoice(ds, invoice_no='VI-PO-2', match_mode='po_based')
    H.insert_line(ds, over_id, qty=9.0, net_amount=90.0, tax_amount=11.7,
                  gross_amount=101.7, schedule_id=H.SCHEDULE_ID)
    result = service.match(over_id)
    assert result['match_status'] == 'exception'
    assert 'qty_over_order_tolerance' in (result['match_exception_reason'] or '')


def test_price_over_tolerance_is_exception(ds, service):
    invoice_id = _ready_receipt_invoice(
        ds, unit_price=11.0, net=110.0, tax=14.3, gross=124.3)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert 'price_over_tolerance' in (result['match_exception_reason'] or '')


# ------------------------------------------------------------- 提交 / 过账

def test_post_writes_ap_match_edge(ds, service, monkeypatch):
    captured = _capture_edges(monkeypatch)
    invoice_id = _ready_receipt_invoice(ds)

    service.submit(invoice_id)
    assert _header(ds, invoice_id)['status'] == 'submitted'

    posted = service.post(invoice_id)
    assert posted['status'] == 'posted'
    assert _header(ds, invoice_id)['status'] == 'posted'
    assert _header(ds, invoice_id)['posting_date']

    ap_edges = [e for e in captured
                if e['rule_id'] == 'receipt_line_to_vendor_invoice_line']
    assert len(ap_edges) == 1
    assert float(ap_edges[0]['quantity']) == 10.0
    assert float(ap_edges[0]['amount']) == 100.0

    # 幂等：重复过账不再写边
    before = len(captured)
    again = service.post(invoice_id)
    assert again.get('already_posted') is True
    assert len(captured) == before


def test_override_then_submit_and_post(ds, service, monkeypatch):
    captured = _capture_edges(monkeypatch)
    invoice_id = _ready_receipt_invoice(
        ds, qty=12.0, net=120.0, tax=15.6, gross=135.6)
    service.match(invoice_id)

    out = service.override_match(invoice_id, reason='超收已与供应商确认')
    assert out['match_status'] == 'overridden'
    assert out['overridden_lines'] == 1

    lines = ds.query(
        'SELECT * FROM vendor_invoice_lines WHERE invoice_id = ?', [invoice_id])
    assert lines[0]['override_reason'] == '超收已与供应商确认'

    service.submit(invoice_id)
    service.post(invoice_id)

    assert _header(ds, invoice_id)['status'] == 'posted'
    # 写边按可用量封顶：min(12, 10) = 10
    ap_edges = [e for e in captured
                if e['rule_id'] == 'receipt_line_to_vendor_invoice_line']
    assert float(ap_edges[0]['quantity']) == 10.0


def test_cancel_draft_and_reject_cancel_posted(ds, service, monkeypatch):
    _capture_edges(monkeypatch)
    invoice_id = _ready_receipt_invoice(ds)
    assert service.cancel(invoice_id)['status'] == 'cancelled'

    posted_id = _ready_receipt_invoice(
        ds, invoice_no='VI-0002', supplier_invoice_no='SI-2')
    service.submit(posted_id)
    service.post(posted_id)
    with pytest.raises(VendorInvoiceError) as exc:
        service.cancel(posted_id)
    assert exc.value.rule == 'VI_STATE_INVALID'


# ----------------------------------------------------------------- 重复发票

def test_duplicate_invoice_requires_override(ds, service, monkeypatch):
    _capture_edges(monkeypatch)
    # 已过账的原始发票（供应商发票号带连字符 / 全角）
    orig_id = _ready_receipt_invoice(
        ds, invoice_no='VI-ORIG', supplier_invoice_no='INV-100')
    service.submit(orig_id)
    service.post(orig_id)

    dup_id = _ready_receipt_invoice(
        ds, invoice_no='VI-DUP', supplier_invoice_no='ｉｎｖ１００')
    service.submit(dup_id)

    with pytest.raises(VendorInvoiceError) as exc:
        service.post(dup_id)
    assert exc.value.rule == 'VI_DUPLICATE'

    out = service.override_duplicate(dup_id, reason='分期结算重复号')
    assert out['duplicate_of'] == orig_id

    service.post(dup_id)
    assert _header(ds, dup_id)['status'] == 'posted'


def test_normalize_supplier_invoice_no():
    assert normalize_supplier_invoice_no('ＩＮＶ－１００') == 'INV100'
    assert normalize_supplier_invoice_no('ＩＮＶ　１００') == 'INV100'
    assert normalize_supplier_invoice_no('inv-100') == 'INV100'
    assert normalize_supplier_invoice_no(' INV 100 ') == 'INV100'


# --------------------------------------------------------------- 红字净额归零

def test_credit_memo_red_ink_nets_to_zero(ds, service):
    # 原发票 + 行 + 一条正常 ap_match 边（绕开 derive，聚焦红冲逻辑）
    orig_id = H.insert_invoice(ds, invoice_no='VI-ORIG-CR',
                               supplier_invoice_no='SI-CR-1', status='posted')
    orig_line_id = H.insert_line(ds, orig_id, qty=10.0, match_status='matched')
    H.insert_edge(ds, target_line_id=orig_line_id, quantity=10.0, amount=100.0)

    assert H.consumed_qty(ds, 'receipt_line', H.RECEIPT_LINE_ID, 'ap_match') == 10.0

    credit_id = H.insert_invoice(
        ds, invoice_no='VI-CREDIT', category='credit_memo', direction=-1,
        supplier_invoice_no='SI-CR-2',
        net_amount=-100.0, tax_amount=-13.0, gross_amount=-113.0)
    H.insert_line(ds, credit_id, qty=10.0, net_amount=-100.0, tax_amount=-13.0,
                  gross_amount=-113.0, invoice_line_id=orig_line_id)

    result = service.submit(credit_id)
    assert result['match_status'] == 'matched'

    service.post(credit_id)
    assert _header(ds, credit_id)['status'] == 'posted'

    red = ds.query(
        "SELECT * FROM doc_flow_edges WHERE quantity_sign = 'red'")
    assert len(red) == 1
    assert float(red[0]['quantity']) == 10.0
    assert H.consumed_qty(ds, 'receipt_line', H.RECEIPT_LINE_ID, 'ap_match') == 0.0


def test_credit_memo_red_quantity_capped_by_original(ds, service):
    orig_id = H.insert_invoice(ds, invoice_no='VI-ORIG-CAP',
                               supplier_invoice_no='SI-CAP-1', status='posted')
    orig_line_id = H.insert_line(ds, orig_id, qty=4.0, match_status='matched')
    H.insert_edge(ds, target_line_id=orig_line_id, quantity=4.0, amount=40.0)

    credit_id = H.insert_invoice(
        ds, invoice_no='VI-CREDIT-CAP', category='credit_memo', direction=-1,
        supplier_invoice_no='SI-CAP-2',
        net_amount=-100.0, tax_amount=-13.0, gross_amount=-113.0)
    H.insert_line(ds, credit_id, qty=10.0, net_amount=-100.0, tax_amount=-13.0,
                  gross_amount=-113.0, invoice_line_id=orig_line_id)

    service.submit(credit_id)
    service.post(credit_id)

    red = ds.query(
        "SELECT * FROM doc_flow_edges WHERE quantity_sign = 'red'")
    assert len(red) == 1
    assert float(red[0]['quantity']) == 4.0
    assert H.consumed_qty(ds, 'receipt_line', H.RECEIPT_LINE_ID, 'ap_match') == 0.0