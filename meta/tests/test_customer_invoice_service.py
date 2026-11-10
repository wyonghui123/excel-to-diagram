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
    PLAN_DOC_FLOW_RULE_ID,
    RETURN_DOC_FLOW_RULE_ID,
    SOURCE_RETURN_SHIPMENT,
    CustomerInvoiceError,
    CustomerInvoiceService,
)
from meta.tests.factories._customer_invoice_helpers import (
    BILLING_SCHEDULE_ID,
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORDER_ID,
    ORDER_LINE_DELIVERY,
    ORDER_LINE_NONE,
    ORDER_LINE_PLAN,
    ORG_ID,
    RETURN_ORDER_LINE_ID,
    RETURN_SHIPMENT_ID,
    RETURN_SHIP_LINE_ID,
    SHIPMENT_ID,
    SHIP_LINE_ID,
    add_allocation,
    build_conn,
    enable_allocation_table,
    fetch_one,
    get_header,
    get_lines,
    get_schedules,
    make_billing_schedule,
    make_ds,
    make_order,
    make_order_line,
    make_return_shipment,
    set_header_amounts,
    set_order_line_billed,
    set_order_line_item,
    set_order_status,
    set_schedule_billed,
    set_schedule_fields,
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
    """Wave B：手工开票不允许按计划期次开票，必须走 create_from_schedule。"""
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER, lines=[{'schedule_id': 72}]))
    _expect(error, 'INVOICE_SOURCE_MISMATCH')


def test_order_line_plan_relevance_fails_closed():
    """Wave B：plan 行只能按计划期次开票，手工按订单量开票直拒。"""
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_manual(dict(
            BASE_HEADER, lines=[{'order_line_id': 12, 'qty': 5}]))
    _expect(error, 'INVOICE_SOURCE_MISMATCH')


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

    # 发货行允许携带冗余的 order_line_id（与 v236 CHECK 语义一致）
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
    # Wave B：plan 行的完成度由其 billing 期次聚合决定
    set_schedule_billed(conn, 1000)

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
    first = service.create_credit_from_invoice(
        {'source_invoice_id': original['id']})
    service.submit(first['id'])
    service.post(first['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_invoice(
            {'source_invoice_id': original['id']})
    _expect(error, 'INVOICE_CREDIT_EXCEEDED')


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


# ---------------------------------------------------------------- C4 部分贷项 / on-account

def _credit(service, invoice_id, **overrides):
    payload = {'source_invoice_id': invoice_id}
    payload.update(overrides)
    return service.create_credit_from_invoice(payload)


def test_credit_partial_qty():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    line_id = get_lines(conn, original['id'])[0]['id']

    credit = _credit(service, original['id'],
                     lines=[{'invoice_line_id': line_id, 'qty': 15}])

    line = get_lines(conn, credit['id'])[0]
    assert Decimal(str(line['qty'])) == Decimal('-15')
    assert Decimal(str(line['net_amount'])) == Decimal('-150')
    assert Decimal(str(line['tax_amount'])) == Decimal('-19.5')
    assert Decimal(str(line['gross_amount'])) == Decimal('-169.5')
    assert Decimal(str(get_header(conn, credit['id'])['gross_amount'])) \
        == Decimal('-169.5')


def test_credit_partial_amount():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    line_id = get_lines(conn, original['id'])[0]['id']

    credit = _credit(service, original['id'],
                     lines=[{'invoice_line_id': line_id, 'amount': 120}])

    line = get_lines(conn, credit['id'])[0]
    assert Decimal(str(line['qty'])) == Decimal('-12')
    assert Decimal(str(line['net_amount'])) == Decimal('-120')
    assert Decimal(str(line['tax_amount'])) == Decimal('-15.6')
    assert Decimal(str(line['unit_price'])) == Decimal('10')


def test_credit_twice_within_limit():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    line_id = get_lines(conn, original['id'])[0]['id']
    first = _credit(service, original['id'],
                    lines=[{'invoice_line_id': line_id, 'qty': 10}])
    service.submit(first['id'])
    service.post(first['id'])

    second = _credit(service, original['id'],
                     lines=[{'invoice_line_id': line_id, 'qty': 20}])

    line = get_lines(conn, second['id'])[0]
    assert Decimal(str(line['qty'])) == Decimal('-20')
    assert Decimal(str(line['net_amount'])) == Decimal('-200')
    # 已过账贷项累计 10，原行剩余 30
    assert Decimal(str(shipment_billed(conn))) == Decimal('30')


def test_credit_exceeds_limit_rejected():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    line_id = get_lines(conn, original['id'])[0]['id']
    first = _credit(service, original['id'],
                    lines=[{'invoice_line_id': line_id, 'qty': 30}])
    service.submit(first['id'])
    service.post(first['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        _credit(service, original['id'],
                lines=[{'invoice_line_id': line_id, 'qty': 11}])
    _expect(error, 'INVOICE_CREDIT_EXCEEDED')


def test_credit_qty_and_amount_both_rejected():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    line_id = get_lines(conn, original['id'])[0]['id']

    with pytest.raises(CustomerInvoiceError) as error:
        _credit(service, original['id'],
                lines=[{'invoice_line_id': line_id, 'qty': 1,
                        'amount': 10}])
    _expect(error, 'INVOICE_CREDIT_AMOUNT_INVALID')


def test_credit_plan_line_percent_conversion():
    conn = build_conn()
    service, original = _posted_plan_invoice(conn)
    line_id = get_lines(conn, original['id'])[0]['id']

    credit = _credit(service, original['id'],
                     lines=[{'invoice_line_id': line_id, 'amount': 300}])

    line = get_lines(conn, credit['id'])[0]
    assert Decimal(str(line['qty'])) == Decimal('-0.3')
    assert Decimal(str(line['net_amount'])) == Decimal('-300')
    # R-INV-24：100% × 300 / 1000 = 30%
    assert Decimal(str(line['billing_percent'])) == Decimal('30')
    assert Decimal(str(line['billing_base_amount'])) == Decimal('300')


def test_credit_on_account_ok():
    conn = build_conn()
    service = _service(conn)

    credit = service.create_credit_on_account(dict(
        BASE_HEADER, reason='年度折让',
        lines=[{'description': '年度返利', 'uom_id': 21, 'tax_code_id': 31,
                'qty': 1, 'unit_price': -100, 'tax_rate_percent': 6}]))

    header = get_header(conn, credit['id'])
    assert header['document_category'] == 'credit_memo'
    assert header['reversal_of_invoice_id'] is None
    assert header['reversal_reason'] == '年度折让'
    assert Decimal(str(header['gross_amount'])) == Decimal('-106')

    line = get_lines(conn, credit['id'])[0]
    assert line['source_doc_type'] == 'manual'
    for key in ('shipment_line_id', 'schedule_id', 'order_line_id',
                'original_invoice_line_id', 'source_line_id',
                'source_doc_id'):
        assert line[key] is None
    assert Decimal(str(line['net_amount'])) == Decimal('-100')
    assert Decimal(str(line['tax_amount'])) == Decimal('-6')
    assert Decimal(str(line['gross_amount'])) == Decimal('-106')


def test_credit_on_account_positive_rejected():
    conn = build_conn()
    service = _service(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_on_account(dict(
            BASE_HEADER,
            lines=[{'description': '错误方向', 'uom_id': 21, 'tax_code_id': 31,
                    'qty': 1, 'unit_price': 100}]))
    _expect(error, 'INVOICE_ON_ACCOUNT_LINE_INVALID')


def test_credit_on_account_missing_customer_rejected():
    conn = build_conn()
    service = _service(conn)
    payload = dict(BASE_HEADER)
    payload.pop('customer_account_id')
    payload['lines'] = [{'description': '返利', 'uom_id': 21, 'tax_code_id': 31,
                         'qty': 1, 'unit_price': -10}]

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_on_account(payload)
    _expect(error, 'INVOICE_SOURCE_INVALID')


def test_is_red_detects_on_account():
    service = _service(build_conn())

    assert service._is_red({'document_category': 'credit_memo',
                           'reversal_of_invoice_id': None}) is True
    assert service._is_red({'document_category': 'invoice',
                           'reversal_of_invoice_id': None}) is False
    assert service._is_red({'document_category': 'invoice',
                           'reversal_of_invoice_id': 9}) is True


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


# ---------------------------------------------------------------- Wave B 计划期次开票

def _from_schedule(conn, **overrides):
    payload = dict(BASE_HEADER, schedule_ids=[BILLING_SCHEDULE_ID])
    payload.update(overrides)
    return _service(conn).create_from_schedule(payload)


def _schedule_row(conn, schedule_id=BILLING_SCHEDULE_ID):
    return fetch_one(
        conn, 'SELECT * FROM sales_order_schedules WHERE id = ?',
        [schedule_id])


def _posted_plan_invoice(conn, **overrides):
    service = _service(conn)
    created = _from_schedule(conn, **overrides)
    service.submit(created['id'])
    service.post(created['id'], posting_date=INVOICE_DATE)
    return service, created


def test_create_from_schedule_defaults_to_full_period():
    conn = build_conn()
    result = _from_schedule(conn)

    assert result['status'] == 'draft'
    assert result['amounts'] == {'net_amount': 1000.0, 'tax_amount': 130.0,
                                 'gross_amount': 1130.0}
    line = get_lines(conn, result['id'])[0]
    assert line['source_doc_type'] == 'billing_schedule'
    assert line['schedule_id'] == BILLING_SCHEDULE_ID
    assert line['order_line_id'] is None
    assert line['billing_basis'] == 'percent'
    assert Decimal(str(line['billing_percent'])) == Decimal('100')
    assert Decimal(str(line['billing_base_amount'])) == Decimal('1000')
    assert Decimal(str(line['qty'])) == Decimal('1')
    assert Decimal(str(line['net_amount'])) == Decimal('1000')


def test_create_from_schedule_keeps_price_diff_zero():
    conn = build_conn()
    result = _from_schedule(conn)

    line = get_lines(conn, result['id'])[0]
    # spec §5.3：plan 不做改价，参考价留空、差额恒 0
    assert line['order_unit_price'] is None
    assert Decimal(str(line['price_diff_amount'])) == Decimal('0')


def test_create_from_schedule_accepts_scalar_schedule_ids():
    conn = build_conn()
    result = _from_schedule(conn, schedule_ids=BILLING_SCHEDULE_ID)

    assert result['amounts']['net_amount'] == 1000.0


def test_create_from_schedule_rejects_duplicate_schedule_over_period():
    conn = build_conn()
    with pytest.raises(CustomerInvoiceError) as error:
        _from_schedule(conn, lines=[
            {'schedule_id': BILLING_SCHEDULE_ID},
            {'schedule_id': BILLING_SCHEDULE_ID},
        ])
    _expect(error, 'INVOICE_PLAN_EXCEEDED')


def test_list_due_schedules_excludes_non_plan_line():
    conn = build_conn()
    make_billing_schedule(conn, 91, percent=50, promised_date='2026-11-15',
                          line_id=ORDER_LINE_DELIVERY)

    result = _service(conn).list_due_schedules(as_of='2026-11-20')

    assert [row['schedule_id'] for row in result['items']] == [
        BILLING_SCHEDULE_ID]


def test_create_from_schedule_merges_multiple_periods():
    conn = build_conn()
    set_schedule_fields(conn, BILLING_SCHEDULE_ID, billing_percent=60)
    make_billing_schedule(conn, 73, percent=40)

    result = _from_schedule(conn, schedule_ids=[BILLING_SCHEDULE_ID, 73])

    lines = get_lines(conn, result['id'])
    assert [line['schedule_id'] for line in lines] == [
        BILLING_SCHEDULE_ID, 73]
    assert result['amounts']['net_amount'] == 1000.0


def test_create_from_schedule_partial_then_remainder_absorbs_tail():
    conn = build_conn()
    service = _service(conn)
    first = _from_schedule(
        conn, lines=[{'schedule_id': BILLING_SCHEDULE_ID,
                      'billing_percent': 30}])
    assert first['amounts']['net_amount'] == 300.0
    service.submit(first['id'])
    service.post(first['id'], posting_date=INVOICE_DATE)

    second = _from_schedule(
        conn, lines=[{'schedule_id': BILLING_SCHEDULE_ID,
                      'billing_percent': 70}])
    assert second['amounts']['net_amount'] == 700.0
    service.submit(second['id'])
    service.post(second['id'], posting_date=INVOICE_DATE)

    schedule = _schedule_row(conn)
    assert Decimal(str(schedule['billed_amount'])) == Decimal('1000')
    assert schedule['billing_status'] == 'full'


def test_create_from_schedule_rejects_over_period_amount():
    conn = build_conn()
    _posted_plan_invoice(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_schedule(conn)
    _expect(error, 'INVOICE_PLAN_EXCEEDED')


def test_create_from_schedule_rejects_percent_over_remaining():
    conn = build_conn()
    service = _service(conn)
    first = _from_schedule(
        conn, lines=[{'schedule_id': BILLING_SCHEDULE_ID,
                      'billing_percent': 30}])
    service.submit(first['id'])
    service.post(first['id'], posting_date=INVOICE_DATE)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_schedule(conn, lines=[{'schedule_id': BILLING_SCHEDULE_ID,
                                     'billing_percent': 80}])
    _expect(error, 'INVOICE_PLAN_PERCENT_INVALID')


def test_create_from_schedule_rejects_non_plan_line():
    conn = build_conn()
    make_billing_schedule(conn, 74, line_id=ORDER_LINE_DELIVERY, percent=50)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_schedule(conn, schedule_ids=[74])
    _expect(error, 'INVOICE_RELEVANCE_NOT_PLAN')


def test_create_from_schedule_rejects_unbillable_period_state():
    conn = build_conn()
    set_schedule_fields(conn, BILLING_SCHEDULE_ID, status='cancelled')

    with pytest.raises(CustomerInvoiceError) as error:
        _from_schedule(conn)
    _expect(error, 'INVOICE_PLAN_STATE_INVALID')


def test_create_from_schedule_rejects_non_billable_order():
    conn = build_conn()
    set_order_status(conn, 'draft')

    with pytest.raises(CustomerInvoiceError) as error:
        _from_schedule(conn)
    _expect(error, 'INVOICE_ORDER_STATE_INVALID')


def test_create_from_schedule_rejects_mixed_orders():
    conn = build_conn()
    make_order(conn, 2)
    make_order_line(conn, 21, order_id=2, relevance='plan', net_amount=500)
    make_billing_schedule(conn, 75, order_id=2, line_id=21, percent=50)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_schedule(conn, schedule_ids=[BILLING_SCHEDULE_ID, 75])
    _expect(error, 'INVOICE_PLAN_ORDER_MISMATCH')


def test_plan_post_writes_schedule_billed_and_doc_flow(monkeypatch):
    conn = build_conn()
    calls = _capture_attach_edges(monkeypatch)
    service, created = _posted_plan_invoice(conn)

    schedule = _schedule_row(conn)
    assert Decimal(str(schedule['billed_amount'])) == Decimal('1000')
    assert schedule['billing_status'] == 'full'
    order = fetch_one(
        conn, 'SELECT billing_status FROM sales_orders WHERE id = ?',
        [ORDER_ID])
    assert order['billing_status'] == 'partial'

    line = get_lines(conn, created['id'])[0]
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[2] == PLAN_DOC_FLOW_RULE_ID
    assert args[3] == BILLING_SCHEDULE_ID
    assert args[4] == line['id']
    assert kwargs['amount'] == 1000.0
    assert kwargs['derived_by'] == 'customer_invoice_service'


def test_plan_post_derives_full_order_with_other_lines():
    conn = build_conn()
    service, _ = _posted_plan_invoice(conn)
    set_order_line_billed(conn, ORDER_LINE_DELIVERY, 100, 1000)
    set_order_line_billed(conn, ORDER_LINE_NONE, 5, 5)

    result = service.recompute_order_billing(ORDER_ID)

    assert result['billing_status'] == 'full'


def test_plan_reverse_rolls_back_schedule_billed():
    conn = build_conn()
    service, created = _posted_plan_invoice(conn)

    result = service.reverse(created['id'], '客户取消')

    schedule = _schedule_row(conn)
    assert Decimal(str(schedule['billed_amount'])) == Decimal('0')
    assert schedule['billing_status'] == 'none'
    assert schedule['status'] == 'planned'
    assert get_header(conn, created['id'])['status'] == 'reversed'
    assert result['red_invoice_no']


def test_plan_red_invoice_keeps_percent_basis_and_negative_amount():
    conn = build_conn()
    service, created = _posted_plan_invoice(conn)

    result = service.reverse(created['id'], '客户取消')

    red_line = get_lines(conn, result['red_invoice_id'])[0]
    assert red_line['billing_basis'] == 'percent'
    assert red_line['schedule_id'] == BILLING_SCHEDULE_ID
    assert Decimal(str(red_line['net_amount'])) == Decimal('-1000')


def test_plan_post_rejects_stale_schedule_after_concurrent_billing():
    conn = build_conn()
    service = _service(conn)
    created = _from_schedule(conn)
    service.submit(created['id'])
    # 模拟提交后另一会话把期次开满：过账时的条件 UPDATE 必须拦下
    set_schedule_billed(conn, 1000)
    conn.commit()

    with pytest.raises(CustomerInvoiceError) as error:
        service.post(created['id'], posting_date=INVOICE_DATE)
    _expect(error, 'INVOICE_PLAN_EXCEEDED')
    assert get_header(conn, created['id'])['status'] == 'submitted'
    assert Decimal(str(_schedule_row(conn)['billed_amount'])) == Decimal('1000')


# ---------------------------------------------------------------- Wave C C3 退货 → 贷项

def _posted_partial_invoice(conn, qty):
    service = _service(conn)
    created = _from_shipment(
        conn, lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': qty}])
    service.submit(created['id'])
    service.post(created['id'])
    return service, created


def test_return_shipment_forward_billing_rejected():
    """R-INV-19：退货发货单禁止正向开票。"""
    conn = build_conn()
    make_return_shipment(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        _from_shipment(conn, shipment_id=RETURN_SHIPMENT_ID)
    _expect(error, 'INVOICE_RETURN_SHIPMENT_NOT_BILLABLE')


def test_return_credit_single_invoice():
    """退货行 → 原订单行 → 已过账发票行，生成负数贷项。"""
    conn = build_conn()
    service, original = _posted_invoice(conn)
    make_return_shipment(conn)

    result = service.create_credit_from_return_shipment(
        {'return_shipment_id': RETURN_SHIPMENT_ID, 'invoice_date': INVOICE_DATE})

    assert result['return_shipment_id'] == RETURN_SHIPMENT_ID
    assert result['source_invoice_id'] == original['id']
    assert result['amounts'] == {'net_amount': -50.0, 'tax_amount': -6.5,
                                 'gross_amount': -56.5}
    header = get_header(conn, result['id'])
    assert header['document_category'] == 'credit_memo'
    assert header['reversal_of_invoice_id'] == original['id']
    assert header['reversal_reason'] == '客户退货'
    lines = get_lines(conn, result['id'])
    assert len(lines) == 1
    assert Decimal(str(lines[0]['qty'])) == Decimal('-5')
    assert Decimal(str(lines[0]['net_amount'])) == Decimal('-50')
    assert lines[0]['original_invoice_line_id'] == get_lines(
        conn, original['id'])[0]['id']


def test_return_credit_fifo_across_two_invoices():
    """D42：多候选默认拒绝歧义，显式 fifo 才按最早发票拆分。"""
    conn = build_conn()
    _posted_partial_invoice(conn, 15)
    service = _service(conn)
    second = _service(conn).create_from_shipment(dict(
        BASE_HEADER, shipment_id=SHIPMENT_ID,
        lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 20}]))
    service.submit(second['id'])
    service.post(second['id'])
    make_return_shipment(conn, lines=[(RETURN_SHIP_LINE_ID,
                                       RETURN_ORDER_LINE_ID, 25.0)])

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_return_shipment(
            {'return_shipment_id': RETURN_SHIPMENT_ID,
             'invoice_date': INVOICE_DATE})
    _expect(error, 'INVOICE_RETURN_ORIGIN_AMBIGUOUS')

    result = service.create_credit_from_return_shipment(
        {'return_shipment_id': RETURN_SHIPMENT_ID,
         'invoice_date': INVOICE_DATE, 'auto_allocate': 'fifo'})

    lines = get_lines(conn, result['id'])
    assert [Decimal(str(line['qty'])) for line in lines] == [
        Decimal('-15'), Decimal('-10')]
    assert len({line['original_invoice_line_id'] for line in lines}) == 2


def test_return_credit_partial_qty():
    """只选部分退货行时，按选中行生成贷项。"""
    conn = build_conn()
    service, _ = _posted_invoice(conn)
    make_return_shipment(conn, lines=[
        (RETURN_SHIP_LINE_ID, RETURN_ORDER_LINE_ID, 5.0),
        (92, 22, 4.0),
    ])

    result = service.create_credit_from_return_shipment(
        {'return_shipment_id': RETURN_SHIPMENT_ID,
         'invoice_date': INVOICE_DATE,
         'return_line_ids': [RETURN_SHIP_LINE_ID]})

    lines = get_lines(conn, result['id'])
    assert len(lines) == 1
    assert lines[0]['source_line_id'] == RETURN_SHIP_LINE_ID
    assert Decimal(str(lines[0]['qty'])) == Decimal('-5')
    assert Decimal(str(shipment_billed(conn))) == Decimal('40')


def test_return_credit_missing_origin_rejected():
    """R-INV-22：找不到已过账原票行时拒绝。"""
    conn = build_conn()
    make_return_shipment(conn)
    service = _service(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_return_shipment(
            {'return_shipment_id': RETURN_SHIPMENT_ID})
    _expect(error, 'INVOICE_RETURN_ORIGIN_MISSING')


def test_return_credit_exceeds_billed_qty_rejected():
    """R-RET-10：退货数量不得大于原行已开票数量。"""
    conn = build_conn()
    _posted_partial_invoice(conn, 15)
    make_return_shipment(conn, lines=[(RETURN_SHIP_LINE_ID,
                                       RETURN_ORDER_LINE_ID, 20.0)])
    service = _service(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_return_shipment(
            {'return_shipment_id': RETURN_SHIPMENT_ID})
    _expect(error, 'INVOICE_CREDIT_EXCEEDED')


def test_return_credit_accumulated_exceeds_rejected():
    """R-RET-10：跨退货单累计退货量不得超过已开票量。"""
    conn = build_conn()
    service, _ = _posted_invoice(conn)
    make_return_shipment(conn, lines=[(RETURN_SHIP_LINE_ID,
                                       RETURN_ORDER_LINE_ID, 30.0)])
    first = service.create_credit_from_return_shipment(
        {'return_shipment_id': RETURN_SHIPMENT_ID, 'invoice_date': INVOICE_DATE})
    service.submit(first['id'])
    service.post(first['id'])

    make_return_shipment(conn, shipment_id=3, return_order_id=3,
                         lines=[(93, 23, 15.0)])
    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_return_shipment(
            {'return_shipment_id': 3})
    _expect(error, 'INVOICE_CREDIT_EXCEEDED')


def test_return_credit_line_keeps_source_keys():
    """红字行来源键：退货发货单 + 退货行 + 原发票行 + 原订单行。"""
    conn = build_conn()
    service, original = _posted_invoice(conn)
    make_return_shipment(conn)

    result = service.create_credit_from_return_shipment(
        {'return_shipment_id': RETURN_SHIPMENT_ID, 'invoice_date': INVOICE_DATE})

    line = get_lines(conn, result['id'])[0]
    assert line['source_doc_type'] == SOURCE_RETURN_SHIPMENT
    assert line['source_doc_id'] == RETURN_SHIPMENT_ID
    assert line['source_line_id'] == RETURN_SHIP_LINE_ID
    assert line['order_line_id'] == ORDER_LINE_DELIVERY
    assert line['original_invoice_line_id'] == get_lines(
        conn, original['id'])[0]['id']
    assert line['billing_basis'] == 'quantity'
    assert line['price_source'] == 'order'


def test_return_credit_writes_two_doc_flow_edges(monkeypatch):
    """过账同时写「原票行 → 贷项行」与「退货发货行 → 贷项行」两条边。"""
    conn = build_conn()
    service, _ = _posted_invoice(conn)
    make_return_shipment(conn)
    created = service.create_credit_from_return_shipment(
        {'return_shipment_id': RETURN_SHIPMENT_ID, 'invoice_date': INVOICE_DATE})
    credit_line_id = get_lines(conn, created['id'])[0]['id']
    calls = _capture_attach_edges(monkeypatch)

    service.submit(created['id'])
    service.post(created['id'])

    assert len(calls) == 2
    credit_args = calls[0][0]
    assert credit_args[2] == CREDIT_DOC_FLOW_RULE_ID
    assert credit_args[4] == credit_line_id
    return_args, return_kwargs = calls[1]
    assert return_args[2] == RETURN_DOC_FLOW_RULE_ID
    assert return_args[3] == RETURN_SHIP_LINE_ID
    assert return_args[4] == credit_line_id
    assert return_args[5] == 5.0
    assert return_kwargs['amount'] == 50.0
    assert return_kwargs['derived_by'] == 'customer_invoice_service'


def test_return_credit_duplicate_return_line_rejected():
    """同一退货行已生成贷项后不得重复提交。"""
    conn = build_conn()
    service, _ = _posted_invoice(conn)
    make_return_shipment(conn)
    created = service.create_credit_from_return_shipment(
        {'return_shipment_id': RETURN_SHIPMENT_ID, 'invoice_date': INVOICE_DATE})
    service.submit(created['id'])
    service.post(created['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_return_shipment(
            {'return_shipment_id': RETURN_SHIPMENT_ID,
             'invoice_date': INVOICE_DATE})
    _expect(error, 'INVOICE_CREDIT_EXCEEDED')
