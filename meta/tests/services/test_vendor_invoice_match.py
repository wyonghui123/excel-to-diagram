# -*- coding: utf-8 -*-
"""W5 采购发票三单匹配服务单测（spec-vendor-invoice-object-model §12 / §13）。

覆盖 DoD：
  D4  超量 → exception（少开不拦）
  D5  matched → post 写边；exception → post 拒绝；override → post 成功留痕
  D6  贷项红冲后 billing / ap_match 净额归零
"""

import json

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
                           match_mode='gr_based', pricing_mode='po_price',
                           price_includes_tax=0, tax_code_id=None):
    """标准场景：PO 承诺 10 / 收货 10，发票按收货行开票。"""
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id = H.insert_invoice(
        ds, invoice_no=invoice_no, supplier_invoice_no=supplier_invoice_no,
        match_mode=match_mode, pricing_mode=pricing_mode,
        net_amount=net, tax_amount=tax, gross_amount=gross)
    H.insert_line(
        ds, invoice_id, qty=qty, unit_price=unit_price,
        net_amount=net, tax_amount=tax, gross_amount=gross,
        receipt_line_id=H.RECEIPT_LINE_ID,
        price_includes_tax=price_includes_tax, tax_code_id=tax_code_id)
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
    # 量差在容差内（25%）→ 例外而非硬错误；容差外由 A7 用例覆盖
    H.set_param(ds, 'vi_qty_tolerance_receipt', 25)
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
    H.set_param(ds, 'vi_qty_tolerance_order', 20)
    result = service.match(over_id)
    assert result['match_status'] == 'exception'
    assert 'qty_over_order_tolerance' in (result['match_exception_reason'] or '')


def test_service_line_two_way_when_acceptance_not_required(ds, service):
    """方案 C：服务行不要求验收 → 2-way，按计划行余量匹配，不需收货行。"""
    H.seed_purchase_order(ds, promised_qty=10.0, schedule_kind='service',
                          service_acceptance_required=0)
    invoice_id = H.insert_invoice(ds, invoice_no='VI-SVC-1', match_mode='gr_based')
    H.insert_line(ds, invoice_id, qty=10.0, schedule_id=H.SCHEDULE_ID)

    result = service.match(invoice_id)

    assert result['match_status'] == 'matched'
    line = _line(ds, H.get_lines(ds, invoice_id)[0]['id'])
    assert line['match_status'] == 'matched'
    assert line['match_exception_reason'] is None


def test_service_line_requires_acceptance_when_flag_on(ds, service):
    """默认 service_acceptance_required=1 → 3-way：缺验收行按 no_receipt 例外。"""
    H.seed_purchase_order(ds, promised_qty=10.0, schedule_kind='service',
                          service_acceptance_required=1)
    invoice_id = H.insert_invoice(ds, invoice_no='VI-SVC-2', match_mode='gr_based')
    H.insert_line(ds, invoice_id, qty=10.0, schedule_id=H.SCHEDULE_ID)

    result = service.match(invoice_id)

    # 头级聚合把 no_receipt 归入 unmatched，原因保留 VI_NO_RECEIPT
    assert result['match_status'] == 'unmatched'
    assert 'VI_NO_RECEIPT' in (result['match_exception_reason'] or '')
    line = _line(ds, H.get_lines(ds, invoice_id)[0]['id'])
    assert line['match_status'] == 'no_receipt'
    assert 'VI_NO_RECEIPT' in (line['match_exception_reason'] or '')


def test_price_over_tolerance_is_exception(ds, service):
    invoice_id = _ready_receipt_invoice(
        ds, unit_price=11.0, net=110.0, tax=14.3, gross=124.3)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert 'price_over_tolerance' in (result['match_exception_reason'] or '')


def test_qty_over_receipt_without_tolerance_rejected(ds, service):
    """A7：默认零容差 → 超量直接硬错误，不再静默截断。"""
    invoice_id = _ready_receipt_invoice(
        ds, qty=12.0, net=120.0, tax=15.6, gross=135.6)

    with pytest.raises(VendorInvoiceError) as exc:
        service.match(invoice_id)

    assert exc.value.rule == 'VI_QTY_EXCEEDED'
    assert _header(ds, invoice_id)['match_status'] == 'unmatched'


def test_price_includes_tax_normalized_before_compare(ds, service):
    """A6：含税价 113 / 13% → 归一为 100，与 PO 价 100 匹配通过。"""
    H.seed_tax_rate(ds, tax_code_id=6601, rate_percent=13.0)
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=100.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-TAX', net_amount=1000.0, tax_amount=130.0,
        gross_amount=1130.0)
    H.insert_line(
        ds, invoice_id, qty=10.0, unit_price=113.0,
        net_amount=1000.0, tax_amount=130.0, gross_amount=1130.0,
        receipt_line_id=H.RECEIPT_LINE_ID,
        price_includes_tax=1, tax_code_id=6601)

    result = service.match(invoice_id)

    assert result['match_status'] == 'matched'
    assert abs(float(result['lines'][0]['price_diff_amount'])) < 1e-6


def test_receipt_price_mode_unsupported(ds, service):
    """A8：收货价模式不支持（Spec §22.8）→ 明确报错而非静默降级。"""
    invoice_id = _ready_receipt_invoice(ds, pricing_mode='receipt_price')

    with pytest.raises(VendorInvoiceError) as exc:
        service.match(invoice_id)

    assert exc.value.rule == 'VI_PRICING_MODE_UNSUPPORTED'


def test_price_includes_tax_without_rate_rejected(ds, service):
    """含税行缺税率（A3 在匹配路径）→ VI_TAX_RATE_REQUIRED 契约错误。"""
    invoice_id = _ready_receipt_invoice(ds, price_includes_tax=1)

    with pytest.raises(VendorInvoiceError) as exc:
        service.match(invoice_id)

    assert exc.value.rule == 'VI_TAX_RATE_REQUIRED'


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
    H.set_param(ds, 'vi_qty_tolerance_receipt', 25)
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
    # 人工放行不截断：按发票全额 12 写边（排队侧已确认）
    ap_edges = [e for e in captured
                if e['rule_id'] == 'receipt_line_to_vendor_invoice_line']
    assert float(ap_edges[0]['quantity']) == 12.0


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


# ------------------------------------------------- 价格来源快照 / 参数解析（W5 遗留）

def test_price_source_snapshot_po_with_trace(ds, service):
    """有 PO 锚 → price_source=po，price_trace 带 po_id / 计划行 / PO 单价。"""
    invoice_id = _ready_receipt_invoice(ds)

    service.match(invoice_id)

    line = ds.query(
        'SELECT * FROM vendor_invoice_lines WHERE invoice_id = ?', [invoice_id])[0]
    assert line['price_source'] == 'po'
    trace = json.loads(line['price_trace'])
    assert trace['po_id'] == H.PO_ID
    assert trace['order_line_id'] == H.PO_LINE_ID
    assert trace['schedule_id'] == H.SCHEDULE_ID
    assert trace['po_unit_price'] == 10.0
    assert trace['price_source'] == 'po'
    assert trace['snapshot_at']


def test_price_source_snapshot_manual_without_anchor(ds, service):
    """无锚点行 → price_source=manual，trace 不含 PO 键。"""
    header = {'id': 1, 'org_id': 1, 'document_type_id': 1}

    line = service._normalize_line_anchors(
        header, {'id': 9, 'line_no': 1, 'item_id': H.ITEM_ID, 'qty': 1.0})

    assert line['price_source'] == 'manual'
    trace = json.loads(line['price_trace'])
    assert 'po_id' not in trace and 'order_line_id' not in trace
    assert trace['price_source'] == 'manual'


def test_price_source_snapshot_keeps_adjustment(ds, service):
    """调整行已落库的 adjustment 来源与轨迹不被重跑匹配覆盖。"""
    header = {'id': 1, 'org_id': 1, 'document_type_id': 1}
    raw_trace = json.dumps({'original_line_id': 7, 'price_source': 'adjustment'})

    line = service._normalize_line_anchors(
        header, {'id': 8, 'line_no': 1, 'price_source': 'adjustment',
                 'price_trace': raw_trace})

    assert line['price_source'] == 'adjustment'
    assert line['price_trace'] == raw_trace


def test_mixed_price_source_marks_exception(ds, service):
    """po 与 manual 混用 → 未放通行统一 exception / price_source_inconsistent。"""
    header = {'id': 1, 'document_category': 'invoice'}
    normalized = [
        {'line_no': 1, 'price_source': 'po', 'match_status': 'matched'},
        {'line_no': 2, 'price_source': 'manual', 'match_status': 'matched'},
        {'line_no': 3, 'price_source': 'po', 'match_status': 'overridden',
         'override_reason': '已确认'},
    ]
    results = [
        {'match_status': 'matched', 'match_exception_reason': None},
        {'match_status': 'matched', 'match_exception_reason': None},
        {'match_status': 'overridden', 'match_exception_reason': None},
    ]

    service._validate_price_source_consistency(header, normalized, results)

    assert results[0]['match_status'] == 'exception'
    assert results[0]['match_exception_reason'] == 'price_source_inconsistent'
    assert results[1]['match_status'] == 'exception'
    # 已放通行保留 overridden，不降级
    assert results[2]['match_status'] == 'overridden'


def test_mixed_price_source_skipped_for_adjustment(ds, service):
    header = {'id': 1, 'document_category': 'adjustment'}
    normalized = [{'price_source': 'po'}, {'price_source': 'manual'}]
    results = [{'match_status': 'matched'}, {'match_status': 'matched'}]

    service._validate_price_source_consistency(header, normalized, results)

    assert [r['match_status'] for r in results] == ['matched', 'matched']


def test_resolve_match_pricing_mode_chain(ds, service):
    """头部空快照 → 参数四维解析；缺定义回落 po_price；receipt_price 保留硬错。"""
    blank = {'match_pricing_mode': '', 'org_id': 1, 'document_type_id': 1}
    assert service._resolve_match_pricing_mode(blank) == 'po_price'

    H.seed_pricing_mode_param(ds, 'manual')
    assert service._resolve_match_pricing_mode(blank) == 'manual'

    # 头部已有快照优先，参数不得穿透
    assert service._resolve_match_pricing_mode(
        {'match_pricing_mode': 'po_price'}) == 'po_price'
    # receipt_price 保留给 _match_line 抛 VI_PRICING_MODE_UNSUPPORTED
    assert service._resolve_match_pricing_mode(
        {'match_pricing_mode': 'receipt_price'}) == 'receipt_price'


def test_adjustment_price_trace_keeps_po_keys(ds, service):
    source = {'price_trace': json.dumps(
        {'po_id': 3, 'order_line_id': 4, 'po_unit_price': 10.0,
         'price_source': 'po'})}

    trace = json.loads(
        service._adjustment_price_trace(source, 77))

    assert trace['po_id'] == 3 and trace['po_unit_price'] == 10.0
    assert trace['original_line_id'] == 77
    assert trace['price_source'] == 'adjustment'


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


def test_credit_memo_over_red_rejected(ds, service):
    """贷项红冲总量超可冲减余量 → 硬错误，不静默截断。"""
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
    with pytest.raises(VendorInvoiceError) as exc:
        service.post(credit_id)

    assert exc.value.rule == 'VI_RED_QTY_EXCEEDED'
    red = ds.query(
        "SELECT * FROM doc_flow_edges WHERE quantity_sign = 'red'")
    assert len(red) == 0
    assert H.consumed_qty(ds, 'receipt_line', H.RECEIPT_LINE_ID,
                          'ap_match') == 4.0


def test_credit_memo_partial_red_fifo(ds, service):
    """贷项 3 / 原票已开 4 → 按 FIFO 冲 3，余量 1。"""
    orig_id = H.insert_invoice(ds, invoice_no='VI-ORIG-FIFO',
                               supplier_invoice_no='SI-FIFO-1', status='posted')
    orig_line_id = H.insert_line(ds, orig_id, qty=4.0, match_status='matched')
    H.insert_edge(ds, target_line_id=orig_line_id, quantity=4.0, amount=40.0)

    credit_id = H.insert_invoice(
        ds, invoice_no='VI-CREDIT-FIFO', category='credit_memo', direction=-1,
        supplier_invoice_no='SI-FIFO-2',
        net_amount=-30.0, tax_amount=-3.9, gross_amount=-33.9)
    H.insert_line(ds, credit_id, qty=3.0, net_amount=-30.0, tax_amount=-3.9,
                  gross_amount=-33.9, invoice_line_id=orig_line_id)

    service.submit(credit_id)
    service.post(credit_id)

    red = ds.query(
        "SELECT * FROM doc_flow_edges WHERE quantity_sign = 'red'")
    assert len(red) == 1
    assert float(red[0]['quantity']) == 3.0
    assert H.consumed_qty(ds, 'receipt_line', H.RECEIPT_LINE_ID,
                          'ap_match') == 1.0


def test_match_handler_accepts_source_doc_id(ds, service, monkeypatch):
    """详情页业务动作只带 source_doc_id 时，match 等 handler 也能定位发票。"""
    from meta.services import vendor_invoice_actions

    invoice_id = _ready_receipt_invoice(ds)
    monkeypatch.setattr(vendor_invoice_actions, '_service', lambda: service)

    result = vendor_invoice_actions.match_handler({'source_doc_id': invoice_id})

    assert result['success'] is True
    assert result['data']['match_status'] == 'matched'


# ------------------------------------------- W11-2 汇率（R-VI-53） / 退货贷项余量（R-VI-51）

def _seed_return_receipt(ds, *, qty_returned=5.0, unit_price=10.0):
    """退货收货单（scope_bo='receipt' / category='return'）+ PO 行单价。"""
    H.seed_type_definitions(ds)
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=unit_price)
    H.seed_receipt_line(ds, qty_received=-qty_returned,
                        document_type_id=H.RECEIPT_RETURN_TYPE_ID)


def test_base_currency_exchange_rate_normalized_to_one(ds, service):
    invoice_id = _ready_receipt_invoice(ds)
    assert _header(ds, invoice_id)['exchange_rate'] in (None, 0)

    service.submit(invoice_id)

    assert float(_header(ds, invoice_id)['exchange_rate']) == 1.0


@pytest.mark.parametrize('rate', [None, 0])
def test_foreign_currency_requires_positive_exchange_rate(ds, service, rate):
    H.seed_currency(ds, currency_id=2, code='USD', name='美元')
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-USD-1', currency_id=2, exchange_rate=rate)
    H.insert_line(ds, invoice_id, receipt_line_id=H.RECEIPT_LINE_ID)

    with pytest.raises(VendorInvoiceError) as exc:
        service.submit(invoice_id)

    assert exc.value.rule == 'VI_EXCHANGE_RATE_REQUIRED'


def test_return_open_view_nets_posted_credit_lines(ds):
    _seed_return_receipt(ds)
    credit_id = H.insert_invoice(
        ds, invoice_no='VCM-RET-1', category='credit_memo', direction=-1,
        document_type_id=H.RED_TYPE_ID, status='posted',
        net_amount=-20.0, tax_amount=0.0, gross_amount=-20.0)
    H.insert_line(ds, credit_id, qty=2.0, net_amount=-20.0, tax_amount=0.0,
                  gross_amount=-20.0, return_line_id=H.RECEIPT_LINE_ID)

    row = ds.query(
        'SELECT * FROM v_vendor_return_open_amount WHERE return_line_id = ?',
        [H.RECEIPT_LINE_ID])[0]
    assert float(row['qty_returned']) == 5.0
    assert float(row['amount_returned']) == 50.0
    assert float(row['amount_credited']) == 20.0
    assert float(row['amount_open']) == 30.0


def _return_credit_memo(ds, *, invoice_no, net):
    credit_id = H.insert_invoice(
        ds, invoice_no=invoice_no, category='credit_memo', direction=-1,
        document_type_id=H.RED_TYPE_ID,
        net_amount=net, tax_amount=0.0, gross_amount=net)
    H.insert_line(ds, credit_id, qty=abs(net) / 10.0, net_amount=net,
                  tax_amount=0.0, gross_amount=net,
                  return_line_id=H.RECEIPT_LINE_ID)
    return credit_id


def test_return_credit_over_open_amount_rejected(ds, service):
    _seed_return_receipt(ds)
    credit_id = _return_credit_memo(ds, invoice_no='VCM-RET-2', net=-60.0)

    with pytest.raises(VendorInvoiceError) as exc:
        service.submit(credit_id)

    assert exc.value.rule == 'VI_RETURN_EXCEEDED'


def test_return_credit_equal_to_open_amount_not_blocked(ds, service):
    _seed_return_receipt(ds)
    credit_id = _return_credit_memo(ds, invoice_no='VCM-RET-3', net=-50.0)

    try:
        service.submit(credit_id)
    except VendorInvoiceError as exc:
        # 贷项无原票行锚点 → 匹配会报 VI_MATCH_EXCEPTION；但不得被余量拦截
        assert exc.rule != 'VI_RETURN_EXCEEDED'