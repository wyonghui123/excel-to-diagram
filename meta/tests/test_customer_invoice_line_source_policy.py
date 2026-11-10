# -*- coding: utf-8 -*-
"""销售发票行来源策略测试（S8 Wave D FR-8）。

依据: docs/specs/s8-customer-invoice-wave-d/spec.md §8 AC-8.x
夹具: meta/tests/factories/_customer_invoice_helpers.py（内存库，raw SQL 在工厂内）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import (
    CustomerInvoiceError,
    CustomerInvoiceService,
    _check_line_source_policy,
    _line_source_kind,
)
from meta.tests.factories._customer_invoice_helpers import (
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORG_ID,
    ORDER_LINE_DELIVERY,
    PAYMENT_TERM_ID,
    SHIP_LINE_ID,
    SHIPMENT_ID,
    build_conn,
    make_ds,
)

POLICY = {
    'invoice': ['shipment_line', 'order_line', 'plan', 'manual'],
    'credit_memo': ['invoice_line', 'return_line', 'manual'],
    'debit_memo': ['manual', 'order_line_readonly'],
}


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _posted_invoice(conn):
    service = _service(conn)
    created = service.create_from_shipment(
        {'shipment_id': SHIPMENT_ID, 'invoice_date': INVOICE_DATE})
    service.submit(created['id'])
    service.post(created['id'])
    return service, created['id']


def _expect(error, rule):
    assert isinstance(error.value, CustomerInvoiceError)
    assert error.value.rule == rule


def _yaml_policy():
    from meta.core.yaml_loader import (
        get_meta_object,
        get_yaml_schema_dir,
        register_from_directory,
    )

    meta = get_meta_object('customer_invoice')
    if meta is None:
        register_from_directory(get_yaml_schema_dir())
        meta = get_meta_object('customer_invoice')
    return dict(meta.line_source_policy)


def test_yaml_declares_line_source_policy():
    """AC-8.1/8.2/8.3：策略由 YAML 单一事实源声明。"""
    assert _yaml_policy() == POLICY


# ---------------------------------------------------------------- 分类

def test_line_source_kind_priority():
    policy_line = {'original_invoice_line_id': 3, 'shipment_line_id': 81}
    return_line = {'source_doc_type': 'return_shipment',
                   'original_invoice_line_id': 5}
    plan_line = {'schedule_id': 7}
    order_line = {'order_line_id': ORDER_LINE_DELIVERY}

    assert _line_source_kind(return_line, 'credit_memo') == 'return_line'
    assert _line_source_kind(policy_line, 'credit_memo') == 'invoice_line'
    assert _line_source_kind({'shipment_line_id': 81}, 'invoice') == \
        'shipment_line'
    assert _line_source_kind(plan_line, 'invoice') == 'plan'
    assert _line_source_kind(order_line, 'invoice') == 'order_line'
    assert _line_source_kind(order_line, 'debit_memo') == \
        'order_line_readonly'
    assert _line_source_kind({}, 'invoice') == 'manual'


# ---------------------------------------------------------------- 校验

def test_invoice_accepts_all_declared_sources():
    lines = [
        {'shipment_line_id': 81},
        {'order_line_id': ORDER_LINE_DELIVERY},
        {'schedule_id': 7},
        {'source_doc_type': 'manual'},
    ]

    _check_line_source_policy('invoice', 1, lines, POLICY)


def test_credit_rejects_shipment_line():
    """AC-8.1：贷项行引用发货行 → INVOICE_LINE_SOURCE_POLICY_VIOLATION。"""
    with pytest.raises(CustomerInvoiceError) as error:
        _check_line_source_policy('credit_memo', -1,
                                  [{'shipment_line_id': 81}], POLICY)
    _expect(error, 'INVOICE_LINE_SOURCE_POLICY_VIOLATION')


def test_debit_accepts_order_line_readonly():
    """AC-8.2：借项行引用订单行（只读）与手工行均合法。"""
    _check_line_source_policy(
        'debit_memo', 1,
        [{'order_line_id': ORDER_LINE_DELIVERY}, {'source_doc_type': 'manual'}],
        POLICY)


def test_undeclared_role_fails_closed():
    """AC-8.3：策略已声明但缺少该角色 → 默认拒绝。"""
    with pytest.raises(CustomerInvoiceError) as error:
        _check_line_source_policy('cancellation', 1, [], POLICY)
    _expect(error, 'INVOICE_LINE_SOURCE_POLICY_VIOLATION')


def test_red_letter_mirror_lines_skip_user_policy():
    """红字镜像行（invoice/-1）由内核生成，不受用户行来源策略约束。"""
    _check_line_source_policy('invoice', -1,
                              [{'original_invoice_line_id': 5}], POLICY)


# ---------------------------------------------------------------- 链路

def test_credit_flow_rejects_shipment_source(monkeypatch):
    """创建链路：贷项行被注入发货行引用时拦截。"""
    conn = build_conn()
    service, source_id = _posted_invoice(conn)
    original = service._negate_line

    def inject(line, line_no, **kwargs):
        row = original(line, line_no, **kwargs)
        row['shipment_line_id'] = SHIP_LINE_ID
        row['original_invoice_line_id'] = None
        return row

    monkeypatch.setattr(service, '_negate_line', inject)
    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_invoice(
            {'source_invoice_id': source_id, 'reason': '折让'})
    _expect(error, 'INVOICE_LINE_SOURCE_POLICY_VIOLATION')


def test_debit_flow_rejects_shipment_source():
    """创建链路：借项头角色为 debit_memo，注入发货行引用时拦截。"""
    conn = build_conn()
    service = _service(conn)
    debit = service.create_debit_memo({
        'invoice_date': INVOICE_DATE,
        'customer_account_id': CUSTOMER_ID,
        'currency_id': CURRENCY_ID,
        'org_id': ORG_ID,
        'payment_term_id': PAYMENT_TERM_ID,
        'lines': [{'description': '补差', 'uom_id': 21, 'tax_code_id': 31,
                   'qty': 1, 'unit_price': 10, 'tax_rate': 0.13}],
    })

    with pytest.raises(CustomerInvoiceError) as error:
        service._insert_lines(debit['id'], [{'shipment_line_id': SHIP_LINE_ID}])
    _expect(error, 'INVOICE_LINE_SOURCE_POLICY_VIOLATION')