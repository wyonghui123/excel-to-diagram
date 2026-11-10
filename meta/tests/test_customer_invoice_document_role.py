# -*- coding: utf-8 -*-
"""销售发票单据身份元数据测试（S8 Wave D FR-2/FR-3/FR-4）。

覆盖：
  · AC-2.x 角色 / 方向由类型元数据派生，未知类型 fail-closed；
  · AC-3.x 头 / 行方向与符号（direction 驱动，`_is_red` 不再读类别）；
  · AC-4.x 红冲读取 `reversal_type_id`，非正向发票拒绝红冲。

夹具: meta/tests/factories/_customer_invoice_helpers.py（内存库，raw SQL 在工厂内）
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import (  # noqa: E402
    CustomerInvoiceError,
    CustomerInvoiceService,
)
from meta.tests.factories._customer_invoice_helpers import (  # noqa: E402
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORG_ID,
    SHIP_LINE_ID,
    SHIPMENT_ID,
    build_conn,
    get_header,
    get_lines,
    get_schedules,
    make_ds,
    set_type_identity,
    type_id,
    type_identity,
)

BASE_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': CUSTOMER_ID,
    'currency_id': CURRENCY_ID,
    'org_id': ORG_ID,
}


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _posted_invoice(conn):
    service = _service(conn)
    result = service.create_from_shipment(
        dict(BASE_HEADER, shipment_id=SHIPMENT_ID,
             lines=[{'shipment_line_id': SHIP_LINE_ID, 'qty': 40}]))
    service.submit(result['id'])
    service.post(result['id'])
    return service, result


def _expect(error, rule):
    assert isinstance(error.value, CustomerInvoiceError)
    assert error.value.rule == rule
    return error.value


# ---------------------------------------------------------------- AC-2 元数据

def test_prepare_header_derives_identity_from_type():
    conn = build_conn()
    header = _service(conn).prepare_header(dict(
        BASE_HEADER, document_type_id=type_id(conn, 'SINV'),
        document_category='credit_memo', direction=-1))

    # 调用方传入的类别 / 方向不生效（元数据单一事实源）
    assert header['document_category'] == 'invoice'
    assert header['direction'] == 1


def test_credit_document_derives_negative_direction():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    credit = service.create_credit_from_invoice(
        {'source_invoice_id': original['id'], 'reason': '折让'})
    header = get_header(conn, credit['id'])

    assert header['document_category'] == 'credit_memo'
    assert header['direction'] == -1
    line = get_lines(conn, credit['id'])[0]
    assert Decimal(str(line['qty'])) < 0
    assert Decimal(str(line['net_amount'])) < 0
    assert Decimal(str(header['gross_amount'])) == sum(
        Decimal(str(item['gross_amount'])) for item in get_lines(conn,
                                                                 credit['id']))


@pytest.mark.parametrize('fields', [
    {'status': 'inactive'},
    {'document_role': 'unknown_role'},
    {'direction': 0},
    {'document_role': None},
])
def test_unknown_identity_fails_closed(fields):
    conn = build_conn()
    set_type_identity(conn, 'SINV', **fields)

    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_from_shipment(
            dict(BASE_HEADER, shipment_id=SHIPMENT_ID))
    _expect(error, 'INVOICE_TYPE_UNKNOWN')


def test_missing_type_fails_closed():
    conn = build_conn()

    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).prepare_header(dict(BASE_HEADER,
                                           document_type_id=9999))
    _expect(error, 'INVOICE_TYPE_UNKNOWN')


# ---------------------------------------------------------------- AC-3 方向

def test_is_red_is_direction_only():
    service = _service(build_conn())

    assert service._is_red({'direction': -1}) is True
    assert service._is_red({'direction': 1}) is False
    # 类别 / 反转指针不再参与判定
    assert service._is_red({'direction': 1,
                            'document_category': 'credit_memo'}) is False
    assert service._is_red({'direction': 1,
                            'reversal_of_invoice_id': 9}) is False


def test_forward_invoice_lines_stay_positive():
    conn = build_conn()
    _, original = _posted_invoice(conn)

    header = get_header(conn, original['id'])
    lines = get_lines(conn, original['id'])
    assert header['direction'] == 1
    assert all(Decimal(str(line['qty'])) > 0 for line in lines)
    assert Decimal(str(header['gross_amount'])) == sum(
        Decimal(str(line['gross_amount'])) for line in lines)


# ---------------------------------------------------------------- AC-4 红冲

def test_reverse_uses_reversal_type_id():
    conn = build_conn()
    service, original = _posted_invoice(conn)

    result = service.reverse(original['id'], '客户退货')
    red = get_header(conn, result['red_invoice_id'])
    srv = type_identity(conn, 'SRV')

    assert result['red_invoice_no'].startswith('SRV-')
    assert red['document_type_id'] == srv['id']
    assert red['document_category'] == srv['document_role'] == 'invoice'
    assert red['direction'] == srv['direction'] == -1
    assert srv['reversal_type_id'] is None
    assert srv['is_default'] == 0
    # 红字单据不生成期次（R-INV-24），行金额全负
    assert get_schedules(conn, red['id']) == []
    assert all(Decimal(str(line['net_amount'])) < 0
               for line in get_lines(conn, red['id']))
    assert red['reversal_of_invoice_id'] == original['id']


def test_reverse_rejects_credit_memo():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    credit = service.create_credit_from_invoice(
        {'source_invoice_id': original['id'], 'reason': '折让'})

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(credit['id'], '二次红冲')
    _expect(error, 'INVOICE_REVERSE_ROLE_UNSUPPORTED')


def test_reverse_rejects_debit_memo():
    conn = build_conn()
    service = _service(conn)
    debit = service.create_manual(dict(
        BASE_HEADER, document_type_id=type_id(conn, 'SDN'),
        lines=[{'line_type_id': type_id(conn, 'INV_SERVICE'),
                'description': '补差', 'uom_id': 21, 'tax_code_id': 31,
                'tax_rate_percent': 6, 'billing_basis': 'amount',
                'net_amount': 10}]))

    assert get_header(conn, debit['id'])['document_category'] == 'debit_memo'
    assert get_header(conn, debit['id'])['direction'] == 1

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(debit['id'], '借项不可红冲')
    _expect(error, 'INVOICE_REVERSE_ROLE_UNSUPPORTED')


def test_reverse_rejects_red_invoice_again():
    conn = build_conn()
    service, original = _posted_invoice(conn)
    red = service.reverse(original['id'], '客户退货')

    with pytest.raises(CustomerInvoiceError) as error:
        service.reverse(red['red_invoice_id'], '红字再红冲')
    _expect(error, 'INVOICE_REVERSE_ROLE_UNSUPPORTED')