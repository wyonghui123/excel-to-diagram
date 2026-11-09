# -*- coding: utf-8 -*-
"""销售发票服务测试（S8 Wave A）—— 建单 / 提交 / 过账 / 红冲 / 派生回写。

依据: docs/specs/s8-customer-invoice-wave-a/spec.md §8.1（服务 14 条）
夹具: meta/tests/factories/_customer_invoice_helpers.py（内存库，raw SQL 在工厂内）
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import (
    CREDIT_DOC_FLOW_RULE_ID,
    CustomerInvoiceError,
    CustomerInvoiceService,
)
from meta.tests.factories._customer_invoice_helpers import (
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORDER_ID,
    ORDER_LINE_DELIVERY,
    ORG_ID,
    SHIPMENT_ID,
    SHIP_LINE_ID,
    add_allocation,
    build_conn,
    enable_allocation_table,
    get_header,
    get_lines,
    get_schedules,
    make_ds,
    set_header_amounts,
    set_order_line_billed,
    set_order_line_item,
    set_shipment_line_billed,
    set_shipment_status,
    shipment_billed,
    type_id,
)

BASE_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': CUSTOMER_ID,
    'currency_id': CURRENCY_ID,
    'org_id': ORG_ID,
}


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _from_shipment(conn, **overrides):
    payload = dict(BASE_HEADER, shipment_id=SHIPMENT_ID)
    payload.update(overrides)
    return _service(conn).create_from_shipment(payload)


def _expect(error, rule):
    assert isinstance(error.value, CustomerInvoiceError)
    assert error.value.rule == rule
    return error.value


# ---------------------------------------------------------------- 建单

def test_create_from_shipment_takes_number_and_snapshots_lines():
    conn = build_conn()
    result = _from_shipment(conn)

    assert result['invoice_no'] == 'SINV-202611-00001'
    assert result['status'] == 'draft'
    assert get_header(conn, result['id'])['document_category'] == 'invoice'
    assert result['amounts'] == {'net_amount': 500.0, 'tax_amount': 65.0,
                                 'gross_amount': 565.0}
    lines = get_lines(conn, result['id'])
    assert [line['shipment_line_id'] for line in lines] == [81, 82]
    first = lines[0]
    assert first['source_doc_type'] == 'shipment'
    assert first['order_line_id'] == ORDER_LINE_DELIVERY
    assert first['billing_basis'] == 'quantity'
    assert first['price_source'] == 'order'
    assert Decimal(str(first['qty'])) == Decimal('40')
    assert Decimal(str(first['net_amount'])) == Decimal('400')


def test_validate_line_write_allows_shipment_line_with_redundant_order_line():
    """回归：发货行同时带 shipment_line_id 与冗余 order_line_id 时不应被 XOR 拒绝。"""
    conn = build_conn()
    result = _from_shipment(conn)
    service = _service(conn)
    line = get_lines(conn, result['id'])[0]
    header = get_header(conn, result['id'])

    normalized = service.validate_line_write(
        {'id': line['id'], 'qty': 10}, existing=line, invoice=header)

    assert normalized['shipment_line_id'] == SHIP_LINE_ID
    assert normalized['order_line_id'] == ORDER_LINE_DELIVERY
    assert Decimal(str(normalized['qty'])) == Decimal('10')


def test_line_price_change_requires_reason_and_computes_diff():
    """D13：草稿行改价必须填写原因，差额按 (单价-订单价)×数量 派生。"""
    conn = build_conn()
    result = _from_shipment(conn)
    service = _service(conn)
    line = get_lines(conn, result['id'])[0]
    header = get_header(conn, result['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.validate_line_write(
            {'id': line['id'], 'unit_price': 12},
            existing=line, invoice=header)
    _expect(error, 'INVOICE_PRICE_REASON_REQUIRED')

    normalized = service.validate_line_write(
        {'id': line['id'], 'unit_price': 12,
         'price_change_reason': '客户议价'},
        existing=line, invoice=header)
    assert normalized['price_source'] == 'manual'
    assert normalized['price_change_reason'] == '客户议价'
    assert Decimal(str(normalized['price_diff_amount'])) == Decimal('80')


def test_line_qty_update_keeps_price_override():
    """D13：已改价行只改数量时，保留覆盖价与原因，差额按新数量重算。"""
    conn = build_conn()
    result = _from_shipment(conn)
    service = _service(conn)
    line = get_lines(conn, result['id'])[0]
    header = get_header(conn, result['id'])

    overridden = service.validate_line_write(
        {'id': line['id'], 'unit_price': 12,
         'price_change_reason': '客户议价'},
        existing=line, invoice=header)
    line.update(overridden)

    normalized = service.validate_line_write(
        {'id': line['id'], 'qty': 10}, existing=line, invoice=header)
    assert Decimal(str(normalized['unit_price'])) == Decimal('12')
    assert normalized['price_source'] == 'manual'
    assert normalized['price_change_reason'] == '客户议价'
    assert Decimal(str(normalized['price_diff_amount'])) == Decimal('20')


def test_service_line_allows_empty_item():
    """B4：服务行允许 item_id 为空（description 必填兜底）。"""
    conn = build_conn()
    result = _service(conn).create_manual(dict(
        BASE_HEADER,
        lines=[{'line_type_id': type_id(conn, 'INV_SERVICE'),
                'description': '安装服务', 'uom_id': 21, 'tax_code_id': 31,
                'tax_rate_percent': 6, 'billing_basis': 'amount',
                'net_amount': 800}]))

    line = get_lines(conn, result['id'])[0]
    assert line['item_id'] is None
    assert line['line_type_id'] == type_id(conn, 'INV_SERVICE')
    assert Decimal(str(line['net_amount'])) == Decimal('800')


def test_order_line_requires_item_for_material_line():
    """B4：非手工的物料行必须关联物料。"""
    conn = build_conn()
    set_order_line_item(conn, None)
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER,
            lines=[{'order_line_id': ORDER_LINE_DELIVERY, 'qty': 5}]))
    _expect(error, 'INVOICE_LINE_ITEM_REQUIRED')


def test_discount_line_allows_negative_amount():
    """B4：仅折扣行允许负金额。"""
    conn = build_conn()
    result = _service(conn).create_manual(dict(
        BASE_HEADER,
        lines=[{'line_type_id': type_id(conn, 'INV_DISCOUNT'),
                'description': '年度折扣', 'uom_id': 21, 'tax_code_id': 31,
                'tax_rate_percent': 13, 'billing_basis': 'amount',
                'net_amount': -50}]))

    line = get_lines(conn, result['id'])[0]
    assert Decimal(str(line['net_amount'])) == Decimal('-50')
    assert Decimal(str(line['gross_amount'])) == Decimal('-56.5')
    assert result['amounts']['gross_amount'] == -56.5


def test_discount_line_rejects_non_negative_amount():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER,
            lines=[{'line_type_id': type_id(conn, 'INV_DISCOUNT'),
                    'description': '折扣', 'uom_id': 21, 'tax_code_id': 31,
                    'tax_rate_percent': 13, 'billing_basis': 'amount',
                    'net_amount': 50}]))
    _expect(error, 'INVOICE_LINE_AMOUNT_INVALID')


def test_non_discount_line_rejects_negative_amount():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER,
            lines=[{'description': '负数物料', 'uom_id': 21, 'tax_code_id': 31,
                    'tax_rate_percent': 13, 'billing_basis': 'amount',
                    'net_amount': -50}]))
    _expect(error, 'INVOICE_LINE_AMOUNT_INVALID')


def test_line_type_must_belong_to_customer_invoice():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER,
            lines=[{'line_type_id': type_id(conn, 'SINV'),
                    'description': '错类型', 'uom_id': 21, 'tax_code_id': 31,
                    'tax_rate_percent': 13, 'billing_basis': 'amount',
                    'net_amount': 100}]))
    _expect(error, 'INVOICE_LINE_TYPE_INVALID')


def test_create_from_shipment_partial_qty():
    conn = build_conn()
    result = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 15}])

    lines = get_lines(conn, result['id'])
    assert len(lines) == 1
    assert Decimal(str(lines[0]['qty'])) == Decimal('15')
    assert Decimal(str(lines[0]['gross_amount'])) == Decimal('169.5')
    assert result['amounts']['gross_amount'] == 169.5


def test_create_from_shipment_rejects_qty_over_available():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _from_shipment(
            conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 41}])
    _expect(error, 'INVOICE_QTY_EXCEEDED')


def test_create_from_shipment_requires_shipped_state():
    conn = build_conn()
    set_shipment_status(conn, 'staged')
    with pytest.raises(CustomerInvoiceError) as error:
        _from_shipment(conn)
    _expect(error, 'INVOICE_SHIPMENT_STATE_INVALID')


def test_create_from_shipment_rejects_when_all_billed():
    conn = build_conn()
    set_shipment_line_billed(conn, 40)
    set_shipment_line_billed(conn, 10, line_id=82)
    with pytest.raises(CustomerInvoiceError) as error:
        _from_shipment(conn)
    _expect(error, 'INVOICE_SOURCE_INVALID')


def test_create_manual_amount_line_derives_unit_price():
    conn = build_conn()
    result = _service(conn).create_manual(dict(
        BASE_HEADER,
        lines=[{'description': '咨询服务', 'uom_id': 21, 'tax_code_id': 31,
                'tax_rate_percent': 6, 'billing_basis': 'amount',
                'net_amount': 1000}]))

    line = get_lines(conn, result['id'])[0]
    assert line['source_doc_type'] == 'manual'
    assert line['price_source'] == 'manual'
    assert Decimal(str(line['qty'])) == Decimal('1')
    assert Decimal(str(line['unit_price'])) == Decimal('1000')
    assert Decimal(str(line['tax_amount'])) == Decimal('60')
    assert result['amounts']['gross_amount'] == 1060.0


def test_create_manual_line_requires_tax_code():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER,
            lines=[{'description': '缺税码', 'uom_id': 21,
                    'tax_rate_percent': 6, 'net_amount': 100}]))
    _expect(error, 'INVOICE_SOURCE_INVALID')


def test_create_manual_plan_schedule_fails_closed():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER, lines=[{'schedule_id': 72}]))
    _expect(error, 'INVOICE_RELEVANCE_NOT_SUPPORTED')


def test_order_line_plan_relevance_fails_closed():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER, lines=[{'order_line_id': 12, 'qty': 5}]))
    _expect(error, 'INVOICE_RELEVANCE_NOT_SUPPORTED')


def test_order_line_none_relevance_rejected():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER, lines=[{'order_line_id': 13, 'qty': 5}]))
    _expect(error, 'INVOICE_SOURCE_MISMATCH')


def test_line_source_keys_schedule_is_exclusive():
    conn = build_conn()
    service = _service(conn)
    with pytest.raises(CustomerInvoiceError) as error:
        service.create_manual(dict(
            BASE_HEADER,
            lines=[{'shipment_line_id': SHIP_LINE_ID, 'schedule_id': 999,
                    'qty': 1}]))
    _expect(error, 'INVOICE_LINE_XOR')

    # 发货行允许携带冗余的 order_line_id（与 v231 CHECK 语义一致）
    result = service.create_manual(dict(
        BASE_HEADER,
        lines=[{'shipment_line_id': SHIP_LINE_ID,
                'order_line_id': ORDER_LINE_DELIVERY, 'qty': 1}]))
    line = get_lines(conn, result['id'])[0]
    assert line['shipment_line_id'] == SHIP_LINE_ID
    assert line['order_line_id'] == ORDER_LINE_DELIVERY


def test_manual_order_line_invoice_uses_order_price():
    conn = build_conn()
    result = _service(conn).create_manual(dict(
        BASE_HEADER,
        lines=[{'order_line_id': ORDER_LINE_DELIVERY, 'qty': 30}]))

    line = get_lines(conn, result['id'])[0]
    assert line['source_doc_type'] == 'sales_order'
    assert line['shipment_line_id'] is None
    assert Decimal(str(line['net_amount'])) == Decimal('300')
    assert result['amounts']['gross_amount'] == 339.0


# ---------------------------------------------------------------- 提交 / 过账

def test_submit_requires_lines():
    conn = build_conn()
    service = _service(conn)
    header = service.prepare_header(dict(BASE_HEADER))
    invoice_id = service._insert_header(header)

    with pytest.raises(CustomerInvoiceError) as error:
        service.submit(invoice_id)
    _expect(error, 'INVOICE_SOURCE_INVALID')


def test_submit_rejects_exhausted_source_after_other_invoice_posted():
    conn = build_conn()
    service = _service(conn)
    first = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 40}])
    second = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 10}])

    service.submit(first['id'])
    service.post(first['id'])
    with pytest.raises(CustomerInvoiceError) as error:
        service.submit(second['id'])
    _expect(error, 'INVOICE_QTY_EXCEEDED')


def test_post_writes_progress_schedules_and_order_billing():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    service.submit(result['id'])

    posted = service.post(result['id'], posting_date=INVOICE_DATE)

    assert posted['status'] == 'posted'
    header = get_header(conn, result['id'])
    assert header['status'] == 'posted'
    assert header['posting_date'] == INVOICE_DATE
    shipment_billed = conn.execute(
        'SELECT billed_qty FROM shipment_lines WHERE id = ?',
        [SHIP_LINE_ID]).fetchone()[0]
    assert Decimal(str(shipment_billed)) == Decimal('40')
    order_line = conn.execute(
        'SELECT billed_qty FROM sales_order_lines WHERE id = ?',
        [ORDER_LINE_DELIVERY]).fetchone()
    assert Decimal(str(order_line[0])) == Decimal('50')
    order = conn.execute(
        'SELECT billing_status FROM sales_orders WHERE id = ?',
        [ORDER_ID]).fetchone()
    assert order[0] == 'partial'
    schedules = get_schedules(conn, result['id'])
    assert len(schedules) == 2
    assert Decimal(str(schedules[0]['amount'])) == Decimal('169.5')
    assert Decimal(str(schedules[1]['amount'])) == Decimal('395.5')


def test_post_rejects_second_time():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    service.submit(result['id'])
    service.post(result['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.post(result['id'])
    _expect(error, 'INVOICE_STATE_INVALID')


def test_post_rejects_posting_date_before_invoice_date():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    service.submit(result['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.post(result['id'], posting_date='2026-11-01')
    _expect(error, 'INVOICE_POSTING_DATE_INVALID')


def test_post_defaults_posting_date_to_invoice_date():
    """D19：发票日期与过账日期分离，未传过账日期时取发票日期。"""
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    service.submit(result['id'])

    posted = service.post(result['id'])

    assert posted['posting_date'] == INVOICE_DATE
    assert get_header(conn, result['id'])['posting_date'] == INVOICE_DATE


def test_over_order_amount_does_not_block_posting():
    """D28：不建冻结码，开票金额超过订单行金额也不阻断过账。"""
    conn = build_conn()
    service = _service(conn)
    result = service.create_manual(dict(
        BASE_HEADER,
        lines=[{'order_line_id': ORDER_LINE_DELIVERY, 'qty': 10,
                'unit_price': 200, 'price_change_reason': '溢价开票'}]))
    service.submit(result['id'])

    posted = service.post(result['id'])

    assert posted['status'] == 'posted'
    assert posted['amounts']['gross_amount'] == 2260.0
    assert get_header(conn, result['id'])['status'] == 'posted'


def test_post_rejects_tampered_header_totals():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)
    set_header_amounts(conn, result['id'], gross=999.0)
    service.submit(result['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.post(result['id'])
    _expect(error, 'INVOICE_AMOUNT_MISMATCH')


def test_recompute_order_billing_full_when_all_lines_billed():
    conn = build_conn()
    for line_id, qty in ((11, 100), (12, 50), (13, 5)):
        set_order_line_billed(conn, line_id, qty)

    result = _service(conn).recompute_order_billing(ORDER_ID)

    assert result['billing_status'] == 'full'
    order = conn.execute(
        'SELECT billing_status, billing_derived_at FROM sales_orders '
        'WHERE id = ?', [ORDER_ID]).fetchone()
    assert order[0] == 'full'
    assert order[1]


def test_cancel_draft_then_transitions_rejected():
    conn = build_conn()
    service = _service(conn)
    result = _from_shipment(conn)

    service.cancel(result['id'])
    assert get_header(conn, result['id'])['status'] == 'cancelled'
    with pytest.raises(CustomerInvoiceError) as error:
        service.submit(result['id'])
    _expect(error, 'INVOICE_STATE_INVALID')


# ---------------------------------------------------------------- 红冲

def _posted_invoice(conn):
    service = _service(conn)
    result = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 40}])
    service.submit(result['id'])
    service.post(result['id'])
    return service, result


def test_reverse_creates_red_invoice_and_rolls_back_progress():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    reversed_result = service.reverse(original['id'], '客户退货')

    assert reversed_result['red_invoice_no'] == 'SCR-202611-00001'
    assert reversed_result['status'] == 'reversed'
    assert get_header(conn, original['id'])['status'] == 'reversed'
    red = get_header(conn, reversed_result['red_invoice_id'])
    assert red['status'] == 'posted'
    assert red['document_category'] == 'credit_memo'
    assert get_header(conn, original['id'])['document_category'] == 'invoice'
    assert red['reversal_of_invoice_id'] == original['id']
    assert Decimal(str(red['gross_amount'])) == Decimal('-452')
    red_lines = get_lines(conn, red['id'])
    assert Decimal(str(red_lines[0]['qty'])) == Decimal('-40')
    assert red_lines[0]['original_invoice_line_id']
    assert Decimal(str(conn.execute(
        'SELECT billed_qty FROM shipment_lines WHERE id = ?',
        [SHIP_LINE_ID]).fetchone()[0])) == Decimal('0')
    assert Decimal(str(conn.execute(
        'SELECT billed_qty FROM sales_order_lines WHERE id = ?',
        [ORDER_LINE_DELIVERY]).fetchone()[0])) == Decimal('0')
    assert conn.execute(
        'SELECT billing_status FROM sales_orders WHERE id = ?',
        [ORDER_ID]).fetchone()[0] == 'none'
    cancelled = get_schedules(conn, original['id'])
    assert [row['status'] for row in cancelled] == ['cancelled', 'cancelled']
    assert get_schedules(conn, red['id']) == []


def test_reverse_rejects_second_red_invoice():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    service.reverse(original['id'], '第一次红冲')

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(original['id'], '重复红冲')
    _expect(error, 'INVOICE_REVERSE_EXISTS')


def test_reverse_requires_reason():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(original['id'], '  ')
    _expect(error, 'INVOICE_REVERSE_INVALID')


def test_reverse_blocked_by_active_allocation():
    """R-INV-23：存在 active 核销时禁止红冲。"""
    conn = build_conn()
    service, original = _posted_invoice(conn)
    enable_allocation_table(conn)
    add_allocation(conn, original['id'], 452)

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(original['id'], '有核销不能红冲')
    _expect(error, 'INVOICE_ALLOCATION_EXISTS')


def test_reverse_allows_cancelled_allocation():
    """R-INV-23：核销已取消（status != active）不阻断红冲。"""
    conn = build_conn()
    service, original = _posted_invoice(conn)
    enable_allocation_table(conn)
    add_allocation(conn, original['id'], 452, status='cancelled')

    result = service.reverse(original['id'], '核销已取消')
    assert result['status'] == 'reversed'
    assert get_header(conn, original['id'])['status'] == 'reversed'


# ---------------------------------------------------------------- 独立贷项（B5）

def test_create_credit_from_invoice_copies_negative_lines():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    credit = service.create_credit_from_invoice(
        {'source_invoice_id': original['id'], 'reason': '价格调整'})

    assert credit['invoice_no'] == 'SCR-202611-00001'
    assert credit['status'] == 'draft'
    header = get_header(conn, credit['id'])
    assert header['document_category'] == 'credit_memo'
    assert header['reversal_of_invoice_id'] == original['id']
    assert header['reversal_reason'] == '价格调整'
    assert Decimal(str(header['gross_amount'])) == Decimal('-452')
    assert get_header(conn, original['id'])['status'] == 'posted'

    credit_line = get_lines(conn, credit['id'])[0]
    assert Decimal(str(credit_line['qty'])) == Decimal('-40')
    assert credit_line['original_invoice_line_id'] == get_lines(
        conn, original['id'])[0]['id']
    # 贷项草稿不回写原单进度
    assert Decimal(str(shipment_billed(conn))) == Decimal('40')


def test_create_credit_requires_posted_source():
    conn = build_conn()
    draft = _from_shipment(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_credit_from_invoice(
            {'source_invoice_id': draft['id']})
    _expect(error, 'INVOICE_STATE_INVALID')


def test_create_credit_rejects_second_credit():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    service.create_credit_from_invoice({'source_invoice_id': original['id']})

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_invoice(
            {'source_invoice_id': original['id']})
    _expect(error, 'INVOICE_CREDIT_EXISTS')


def test_create_credit_date_before_posting_rejected():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_invoice(
            {'source_invoice_id': original['id'],
             'invoice_date': '2026-11-08'})
    _expect(error, 'INVOICE_POSTING_DATE_INVALID')


def test_create_credit_selected_lines_only():
    conn = build_conn()
    service = _service(conn)
    created = _from_shipment(conn)
    service.submit(created['id'])
    service.post(created['id'])
    second_line_id = get_lines(conn, created['id'])[1]['id']

    credit = service.create_credit_from_invoice(
        {'source_invoice_id': created['id'], 'line_ids': [second_line_id]})

    credit_lines = get_lines(conn, credit['id'])
    assert len(credit_lines) == 1
    assert credit_lines[0]['original_invoice_line_id'] == second_line_id
    assert Decimal(str(credit_lines[0]['qty'])) == Decimal('-10')


def test_credit_post_rolls_back_billed_progress():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    credit = service.create_credit_from_invoice(
        {'source_invoice_id': original['id']})

    service.submit(credit['id'])
    service.post(credit['id'])

    assert get_header(conn, credit['id'])['status'] == 'posted'
    assert Decimal(str(shipment_billed(conn))) == Decimal('0')
    assert conn.execute(
        'SELECT billed_qty FROM sales_order_lines WHERE id = ?',
        [ORDER_LINE_DELIVERY]).fetchone()[0] == 0


# ---------------------------------------------------------------- doc_flow 反向边（B7）

def _capture_attach_edges(monkeypatch):
    calls = []

    def _fake_attach_edge(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    monkeypatch.setattr('meta.core.doc_flow_attach.attach_edge', _fake_attach_edge)
    return calls


def test_credit_post_writes_reverse_doc_flow_edge(monkeypatch):
    conn = build_conn()
    service, original = _posted_invoice(conn)
    credit = service.create_credit_from_invoice(
        {'source_invoice_id': original['id']})
    original_line_id = get_lines(conn, original['id'])[0]['id']
    credit_line_id = get_lines(conn, credit['id'])[0]['id']
    calls = _capture_attach_edges(monkeypatch)

    service.submit(credit['id'])
    service.post(credit['id'])

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[2] == CREDIT_DOC_FLOW_RULE_ID
    assert args[3] == original_line_id
    assert args[4] == credit_line_id
    assert args[5] == 40.0        # 负行取正
    assert kwargs['amount'] == 400.0
    assert kwargs['derived_by'] == 'customer_invoice_service'


def test_reverse_writes_credit_doc_flow_edge(monkeypatch):
    conn = build_conn()
    service, original = _posted_invoice(conn)
    original_line_id = get_lines(conn, original['id'])[0]['id']
    calls = _capture_attach_edges(monkeypatch)

    result = service.reverse(original['id'], '客户退货')

    assert len(calls) == 1
    args, kwargs = calls[0]
    red_line_id = get_lines(conn, result['red_invoice_id'])[0]['id']
    assert args[2] == CREDIT_DOC_FLOW_RULE_ID
    assert args[3] == original_line_id
    assert args[4] == red_line_id
    assert args[5] == 40.0
    assert kwargs['amount'] == 400.0
