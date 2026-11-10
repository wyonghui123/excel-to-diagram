# -*- coding: utf-8 -*-
"""销售发票守卫拦截器测试（S8 Wave A）—— 写保护与状态迁移接线。

依据: docs/specs/s8-customer-invoice-wave-a/spec.md §6（守卫 8 条）
夹具: meta/tests/factories/_customer_invoice_helpers.py
"""
import types
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors import (
    customer_invoice_guard_interceptor as guard_interceptor,
)
from meta.core.interceptors.customer_invoice_guard_interceptor import (
    CustomerInvoiceGuardInterceptor,
    state_readonly_fields,
)
from meta.services.customer_invoice_service import (
    EPSILON,
    PERCENT_TAIL_TOLERANCE,
    CustomerInvoiceError,
    CustomerInvoiceService,
)
from meta.tests.factories._customer_invoice_helpers import (
    BILLING_SCHEDULE_ID,
    CURRENCY_ID,
    CUSTOMER_ID,
    DELIVERY_SCHEDULE_ID,
    INVOICE_DATE,
    ORDER_LINE_DELIVERY,
    ORG_ID,
    RETURN_ORDER_LINE_ID,
    RETURN_SHIPMENT_ID,
    RETURN_SHIP_LINE_ID,
    build_conn,
    get_header,
    get_lines,
    make_billing_schedule,
    make_ds,
    make_return_shipment,
    set_schedule_billed,
    set_shipment_line_billed,
    type_id,
)

BASE_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': CUSTOMER_ID,
    'currency_id': CURRENCY_ID,
    'org_id': ORG_ID,
}


def _ctx(conn, object_id, action, params, old_data=None, result=None):
    return types.SimpleNamespace(
        meta_object=types.SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        extra={},
        data_source=make_ds(conn),
        result=result,
    )


def _service(conn):
    return CustomerInvoiceService(make_ds(conn))


def _draft_invoice(conn, *, qty=40):
    return _service(conn).create_manual(dict(
        BASE_HEADER,
        lines=[{'order_line_id': 11, 'qty': qty}]))


def _submitted_invoice(conn, *, qty=40):
    service = _service(conn)
    created = _draft_invoice(conn, qty=qty)
    service.submit(created['id'])
    return created


def _posted_invoice(conn, *, qty=40):
    service = _service(conn)
    created = _draft_invoice(conn, qty=qty)
    service.submit(created['id'])
    service.post(created['id'], posting_date=INVOICE_DATE)
    return created


def _expect(error, rule):
    assert isinstance(error.value, ValidationFailedError)
    assert error.value.details[0]['rule'] == rule
    return error.value


_INTERCEPTOR = CustomerInvoiceGuardInterceptor()


# ---------------------------------------------------------------- 作用域 / 创建

def test_should_execute_limits_to_three_objects_write_actions():
    conn = build_conn()
    for object_id in ('customer_invoice', 'customer_invoice_line',
                      'customer_invoice_schedule'):
        assert _INTERCEPTOR.should_execute(
            _ctx(conn, object_id, 'crud_create', {})) is True
    assert _INTERCEPTOR.should_execute(
        _ctx(conn, 'customer_invoice', 'crud_read', {})) is False
    assert _INTERCEPTOR.should_execute(
        _ctx(conn, 'shipment', 'crud_create', {})) is False


def test_create_fills_number_and_defaults():
    conn = build_conn()
    params = dict(BASE_HEADER, lines=[{'order_line_id': 11, 'qty': 5}])

    _INTERCEPTOR.before_action(
        _ctx(conn, 'customer_invoice', 'crud_create', params))

    assert params['invoice_no'] == 'SINV-202611-00001'
    assert params['status'] == 'draft'
    assert params['document_type_id']
    assert params['gross_amount'] == 0
    assert params['net_amount'] == 0


def test_create_rejects_non_draft_status():
    conn = build_conn()
    params = dict(BASE_HEADER, status='posted')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice', 'crud_create', params))
    _expect(error, 'INVOICE_STATE_INVALID')


# ---------------------------------------------------------------- 抬头迁移

def test_draft_to_submitted_delegates_submit_and_tightens_params():
    conn = build_conn()
    created = _draft_invoice(conn)
    params = {'id': created['id'], 'status': 'submitted'}

    _INTERCEPTOR.before_action(
        _ctx(conn, 'customer_invoice', 'crud_update', params))

    assert get_header(conn, created['id'])['status'] == 'submitted'
    assert params == {'id': created['id'], 'status': 'submitted'}


def test_submitted_frozen_field_change_rejected():
    conn = build_conn()
    created = _submitted_invoice(conn)
    params = {'id': created['id'], 'currency_id': CURRENCY_ID + 1}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            conn, 'customer_invoice', 'crud_update', params,
            old_data=get_header(conn, created['id'])))
    _expect(error, 'INVOICE_POSTED_READONLY')


def test_submitted_same_frozen_value_allowed():
    conn = build_conn()
    created = _submitted_invoice(conn)
    params = {'id': created['id'], 'currency_id': CURRENCY_ID,
              'remark': '备注可改'}

    _INTERCEPTOR.before_action(_ctx(
        conn, 'customer_invoice', 'crud_update', params,
        old_data=get_header(conn, created['id'])))
    assert params['remark'] == '备注可改'


def test_submitted_same_month_invoice_date_allowed():
    """AC-7.3：submitted 仍允许同月调整 invoice_date（号码一致性补丁兼容）。"""
    conn = build_conn()
    created = _submitted_invoice(conn)
    params = {'id': created['id'], 'invoice_date': '2026-11-20'}

    _INTERCEPTOR.before_action(_ctx(
        conn, 'customer_invoice', 'crud_update', params,
        old_data=get_header(conn, created['id'])))
    assert params['invoice_date'] == '2026-11-20'


def _yaml_submitted_readonly():
    from meta.core.yaml_loader import (
        get_meta_object,
        get_yaml_schema_dir,
        register_from_directory,
    )

    meta = get_meta_object('customer_invoice')
    if meta is None:
        register_from_directory(get_yaml_schema_dir())
        meta = get_meta_object('customer_invoice')
    return tuple(meta.state_field_policies['submitted'].readonly)


def _changed_value(field, header):
    old = header.get(field)
    if field in ('customer_account_id', 'currency_id', 'org_id',
                 'sales_org_id', 'bill_to_account_id', 'payer_account_id'):
        return (old or 0) + 1
    if field == 'document_type_id':
        return int(old) + 1000
    if field == 'exchange_rate':
        return 2.0
    if field == 'direction':
        return -1 if int(old) == 1 else 1
    return 'CHANGED-%s' % field


def test_yaml_submitted_readonly_matches_interceptor():
    """AC-7.2：YAML 声明的 submitted 只读集合 == 内核实际拦截集合。"""
    conn = build_conn()
    created = _submitted_invoice(conn)
    header = get_header(conn, created['id'])
    declared = _yaml_submitted_readonly()

    # 内核读取的就是同一份 YAML 声明
    assert declared == tuple(state_readonly_fields('submitted'))
    # direction 全状态只读；invoice_date 不在其中（AC-7.3 同月可调）
    assert 'direction' in declared
    assert 'invoice_no' in declared
    assert 'invoice_date' not in declared

    for field in declared:
        params = {'id': created['id'], field: _changed_value(field, header)}
        with pytest.raises(ValidationFailedError) as error:
            _INTERCEPTOR.before_action(_ctx(
                conn, 'customer_invoice', 'crud_update', params,
                old_data=header))
        _expect(error, 'INVOICE_POSTED_READONLY')


def test_frozen_policy_follows_yaml_declaration(monkeypatch):
    """AC-7.1：冻结集合随 YAML 解析结果变化，无需改 Python。"""
    conn = build_conn()
    created = _submitted_invoice(conn)
    header = get_header(conn, created['id'])

    monkeypatch.setattr(
        guard_interceptor, 'state_readonly_fields', lambda state: ('remark',))
    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            conn, 'customer_invoice', 'crud_update',
            {'id': created['id'], 'remark': 'YAML 声明为只读'}, old_data=header))
    _expect(error, 'INVOICE_POSTED_READONLY')


def test_document_category_is_immutable():
    conn = build_conn()
    created = _draft_invoice(conn)
    old_data = get_header(conn, created['id'])
    assert old_data['document_category'] == 'invoice'

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            conn, 'customer_invoice', 'crud_update',
            {'id': created['id'], 'document_category': 'credit_memo'},
            old_data=old_data))
    _expect(error, 'INVOICE_POSTED_READONLY')

    params = {'id': created['id'], 'document_category': 'invoice',
              'remark': '同值可提交'}
    _INTERCEPTOR.before_action(_ctx(
        conn, 'customer_invoice', 'crud_update', params, old_data=old_data))
    assert params['remark'] == '同值可提交'


def test_number_locks_document_type_change():
    conn = build_conn()
    created = _draft_invoice(conn)
    old_data = get_header(conn, created['id'])
    assert old_data['invoice_no'] == 'SINV-202611-00001'
    debit_memo_type_id = type_id(conn, 'SDN')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            conn, 'customer_invoice', 'crud_update',
            {'id': created['id'], 'document_type_id': debit_memo_type_id},
            old_data=old_data))
    _expect(error, 'INVOICE_NUMBER_TYPE_LOCKED')

    params = {'id': created['id'],
              'document_type_id': old_data['document_type_id']}
    _INTERCEPTOR.before_action(_ctx(
        conn, 'customer_invoice', 'crud_update', params, old_data=old_data))
    assert params['document_type_id'] == old_data['document_type_id']


def test_number_rejects_cross_month_invoice_date_change():
    conn = build_conn()
    draft = _draft_invoice(conn)
    draft_row = get_header(conn, draft['id'])

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            conn, 'customer_invoice', 'crud_update',
            {'id': draft['id'], 'invoice_date': '2026-12-01'},
            old_data=draft_row))
    _expect(error, 'INVOICE_NUMBER_PERIOD_MISMATCH')

    submitted = _submitted_invoice(conn)
    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            conn, 'customer_invoice', 'crud_update',
            {'id': submitted['id'], 'invoice_date': '2026-12-01'},
            old_data=get_header(conn, submitted['id'])))
    _expect(error, 'INVOICE_NUMBER_PERIOD_MISMATCH')


def test_number_allows_same_month_invoice_date_change():
    conn = build_conn()
    draft = _draft_invoice(conn)
    params = {'id': draft['id'], 'invoice_date': '2026-11-20'}

    _INTERCEPTOR.before_action(_ctx(
        conn, 'customer_invoice', 'crud_update', params,
        old_data=get_header(conn, draft['id'])))

    assert params['invoice_date'] == '2026-11-20'


def test_submitted_to_posted_delegates_and_exposes_posting_date():
    conn = build_conn()
    created = _submitted_invoice(conn)
    params = {'id': created['id'], 'status': 'posted',
              'posting_date': INVOICE_DATE}
    context = _ctx(conn, 'customer_invoice', 'crud_update', params,
                   result=types.SimpleNamespace(data={}))

    _INTERCEPTOR.before_action(context)
    _INTERCEPTOR.after_action(context)

    assert get_header(conn, created['id'])['status'] == 'posted'
    assert context.result.data['posting_date'] == INVOICE_DATE
    assert params == {'id': created['id'], 'status': 'posted'}


def test_posted_to_reversed_delegates_reverse():
    conn = build_conn()
    created = _posted_invoice(conn)
    params = {'id': created['id'], 'status': 'reversed',
              'reversal_reason': '客户退货'}
    context = _ctx(conn, 'customer_invoice', 'crud_update', params,
                   result=types.SimpleNamespace(data={}))

    _INTERCEPTOR.before_action(context)
    _INTERCEPTOR.after_action(context)

    assert get_header(conn, created['id'])['status'] == 'reversed'
    assert context.result.data['red_invoice_no'] == 'SRV-202611-00001'
    assert params == {'id': created['id'], 'status': 'reversed'}


def test_posted_other_field_change_rejected():
    conn = build_conn()
    created = _posted_invoice(conn)
    params = {'id': created['id'], 'remark': '改备注'}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice', 'crud_update', params))
    _expect(error, 'INVOICE_POSTED_READONLY')


def test_terminal_status_rejects_any_update():
    conn = build_conn()
    created = _posted_invoice(conn)
    _service(conn).reverse(created['id'], '退货')
    params = {'id': created['id'], 'remark': '终态改备注'}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice', 'crud_update', params))
    _expect(error, 'INVOICE_POSTED_READONLY')


def test_delete_only_draft():
    conn = build_conn()
    draft = _draft_invoice(conn)
    _INTERCEPTOR.before_action(
        _ctx(conn, 'customer_invoice', 'crud_delete', {'id': draft['id']}))

    submitted = _submitted_invoice(conn)
    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            conn, 'customer_invoice', 'crud_delete', {'id': submitted['id']}))
    _expect(error, 'INVOICE_DELETE_FORBIDDEN')


# ---------------------------------------------------------------- 行写保护

def test_line_create_recalculates_amounts_and_assigns_line_no():
    conn = build_conn()
    draft = _draft_invoice(conn)
    params = {'invoice_id': draft['id'], 'order_line_id': 11, 'qty': 2}

    _INTERCEPTOR.before_action(
        _ctx(conn, 'customer_invoice_line', 'crud_create', params))

    assert params['line_no'] == 2
    assert params['source_doc_type'] == 'sales_order'
    assert params['net_amount'] == 20.0
    assert params['tax_amount'] == 2.6
    assert params['gross_amount'] == 22.6


def test_line_create_on_posted_parent_rejected():
    conn = build_conn()
    posted = _posted_invoice(conn)
    params = {'invoice_id': posted['id'], 'order_line_id': 11, 'qty': 1}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice_line', 'crud_create', params))
    _expect(error, 'INVOICE_POSTED_READONLY')


def test_line_update_recalculates_and_preserves_line_no():
    conn = build_conn()
    draft = _draft_invoice(conn, qty=1)
    line = get_lines(conn, draft['id'])[0]
    params = {'id': line['id'], 'qty': 3}

    _INTERCEPTOR.before_action(
        _ctx(conn, 'customer_invoice_line', 'crud_update', params))

    assert params['line_no'] == 1
    assert params['net_amount'] == 30.0
    assert params['tax_amount'] == 3.9


def test_line_delete_on_submitted_parent_rejected():
    conn = build_conn()
    submitted = _submitted_invoice(conn)
    line = get_lines(conn, submitted['id'])[0]

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            conn, 'customer_invoice_line', 'crud_delete', {'id': line['id']}))
    _expect(error, 'INVOICE_POSTED_READONLY')


def test_line_qty_exceeds_available_rejected():
    conn = build_conn()
    set_shipment_line_billed(conn, 39)
    draft = _draft_invoice(conn)
    params = {'invoice_id': draft['id'],
              'shipment_line_id': 81, 'qty': 5}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice_line', 'crud_create', params))
    _expect(error, 'INVOICE_QTY_EXCEEDED')


# ---------------------------------------------------------------- 注册路径

def test_both_startup_paths_register_customer_invoice_guard():
    import inspect

    import meta.core.app_builder as app_builder
    import meta.server as server

    for module in (server, app_builder):
        source = inspect.getsource(module)
        assert 'CustomerInvoiceGuardInterceptor()' in source


# ---------------------------------------------------------------- 期次只读

@pytest.mark.parametrize('action', ['crud_create', 'crud_update',
                                    'crud_delete'])
def test_schedule_any_write_rejected(action):
    conn = build_conn()
    params = {'invoice_id': 1, 'schedule_no': 1, 'id': 1, 'amount': 1}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice_schedule', action, params))
    _expect(error, 'INVOICE_SCHEDULE_IMMUTABLE')


# ---------------------------------------------------------------- Wave B 计划行

def test_line_create_from_billing_schedule_fills_period_amounts():
    conn = build_conn()
    draft = _draft_invoice(conn)
    params = {'invoice_id': draft['id'],
              'schedule_id': BILLING_SCHEDULE_ID}

    _INTERCEPTOR.before_action(
        _ctx(conn, 'customer_invoice_line', 'crud_create', params))

    assert params['line_no'] == 2
    assert params['source_doc_type'] == 'billing_schedule'
    assert params['billing_basis'] == 'percent'
    assert params['qty'] == 1.0
    assert params['billing_percent'] == 100.0
    assert params['billing_base_amount'] == 1000.0
    assert params['net_amount'] == 1000.0
    assert params['tax_amount'] == 130.0
    assert params['gross_amount'] == 1130.0
    # 三键 XOR：计划行不落冗余 order_line_id
    assert 'order_line_id' not in params


def test_line_create_plan_percent_partial_normalized():
    conn = build_conn()
    draft = _draft_invoice(conn)
    params = {'invoice_id': draft['id'],
              'schedule_id': BILLING_SCHEDULE_ID, 'billing_percent': 30}

    _INTERCEPTOR.before_action(
        _ctx(conn, 'customer_invoice_line', 'crud_create', params))

    assert params['billing_percent'] == 30.0
    assert params['net_amount'] == 300.0
    assert params['tax_amount'] == 39.0
    assert params['gross_amount'] == 339.0


def test_line_create_plan_percent_over_remaining_rejected():
    conn = build_conn()
    set_schedule_billed(conn, 800)
    draft = _draft_invoice(conn)
    params = {'invoice_id': draft['id'],
              'schedule_id': BILLING_SCHEDULE_ID, 'billing_percent': 30}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice_line', 'crud_create', params))
    _expect(error, 'INVOICE_PLAN_PERCENT_INVALID')


def test_line_create_from_non_billing_schedule_rejected():
    conn = build_conn()
    draft = _draft_invoice(conn)
    params = {'invoice_id': draft['id'],
              'schedule_id': DELIVERY_SCHEDULE_ID}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice_line', 'crud_create', params))
    _expect(error, 'INVOICE_PLAN_STATE_INVALID')


def test_line_create_from_schedule_on_delivery_line_rejected():
    conn = build_conn()
    make_billing_schedule(conn, 73, line_id=ORDER_LINE_DELIVERY, percent=50)
    draft = _draft_invoice(conn)
    params = {'invoice_id': draft['id'], 'schedule_id': 73}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice_line', 'crud_create', params))
    _expect(error, 'INVOICE_RELEVANCE_NOT_PLAN')


def test_line_create_from_schedule_on_posted_parent_rejected():
    conn = build_conn()
    posted = _posted_invoice(conn)
    params = {'invoice_id': posted['id'],
              'schedule_id': BILLING_SCHEDULE_ID}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice_line', 'crud_create', params))
    _expect(error, 'INVOICE_POSTED_READONLY')


def test_line_update_plan_source_field_locked():
    conn = build_conn()
    created = _service(conn).create_from_schedule(dict(
        BASE_HEADER, schedule_ids=[BILLING_SCHEDULE_ID]))
    line = get_lines(conn, created['id'])[0]
    make_billing_schedule(conn, 73, percent=40)
    params = {'id': line['id'], 'schedule_id': 73}

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(conn, 'customer_invoice_line', 'crud_update', params))
    _expect(error, 'INVOICE_LINE_SOURCE_LOCKED')


def test_line_update_plan_percent_recalculates_amount():
    conn = build_conn()
    created = _service(conn).create_from_schedule(dict(
        BASE_HEADER, schedule_ids=[BILLING_SCHEDULE_ID]))
    line = get_lines(conn, created['id'])[0]
    params = {'id': line['id'], 'billing_percent': 50}

    _INTERCEPTOR.before_action(
        _ctx(conn, 'customer_invoice_line', 'crud_update', params))

    assert params['billing_percent'] == 50.0
    assert params['net_amount'] == 500.0
    assert params['tax_amount'] == 65.0


# ---------------------------------------------------------------- Wave C 守卫（T41）

def _expect_ci(error, rule):
    assert isinstance(error.value, CustomerInvoiceError)
    assert error.value.rule == rule
    return error.value


def _on_account_credit(conn):
    return _service(conn).create_credit_on_account(dict(
        BASE_HEADER,
        lines=[{'description': '年度返利', 'uom_id': 21, 'tax_code_id': 31,
                'qty': 1, 'unit_price': -100, 'tax_rate_percent': 6}]))


def test_guard_return_shipment_not_billable():
    """R-INV-19：退货发货单禁止正向开票。"""
    conn = build_conn()
    make_return_shipment(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        _service(conn).create_from_shipment(
            dict(BASE_HEADER, shipment_id=RETURN_SHIPMENT_ID))
    _expect_ci(error, 'INVOICE_RETURN_SHIPMENT_NOT_BILLABLE')


def test_guard_credit_line_keys_locked():
    """R-INV-21：贷项行来源键生成后不可改。"""
    conn = build_conn()
    service = _service(conn)
    credit = _on_account_credit(conn)
    line = get_lines(conn, credit['id'])[0]
    header = get_header(conn, credit['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.validate_line_write(
            {'id': line['id'], 'shipment_line_id': 81},
            existing=line, invoice=header)
    _expect_ci(error, 'INVOICE_CREDIT_LINE_LOCKED')

    with pytest.raises(CustomerInvoiceError) as error:
        service.validate_line_write(
            {'id': line['id'], 'source_line_id': 91},
            existing=line, invoice=header)
    _expect_ci(error, 'INVOICE_CREDIT_LINE_LOCKED')


def test_guard_on_account_no_line_keys():
    """R-INV-21：贷项建行必须无来源行键（on-account）。"""
    conn = build_conn()
    service = _service(conn)
    credit = _on_account_credit(conn)
    header = get_header(conn, credit['id'])

    with pytest.raises(CustomerInvoiceError) as error:
        service.validate_line_write(
            {'description': '带来源键', 'uom_id': 21, 'tax_code_id': 31,
             'qty': 1, 'unit_price': -10, 'shipment_line_id': 81},
            invoice=header)
    _expect_ci(error, 'INVOICE_CREDIT_LINE_LOCKED')


def test_guard_return_qty_not_exceed_billed():
    """R-RET-10：退货数量不得超过原行已开票数量。"""
    conn = build_conn()
    _posted_invoice(conn, qty=15)
    make_return_shipment(conn, lines=[(RETURN_SHIP_LINE_ID,
                                       RETURN_ORDER_LINE_ID, 20.0)])
    service = _service(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_return_shipment(
            {'return_shipment_id': RETURN_SHIPMENT_ID})
    _expect_ci(error, 'INVOICE_CREDIT_EXCEEDED')


def test_guard_credit_amount_within_limit():
    """R-INV-20：贷项金额不得超过原行剩余可贷额度。"""
    conn = build_conn()
    service = _service(conn)
    original = _posted_invoice(conn)
    line_id = get_lines(conn, original['id'])[0]['id']

    with pytest.raises(CustomerInvoiceError) as error:
        service.create_credit_from_invoice({
            'source_invoice_id': original['id'],
            'lines': [{'invoice_line_id': line_id, 'amount': 500}]})
    _expect_ci(error, 'INVOICE_CREDIT_EXCEEDED')


def test_guard_tolerances_not_interchangeable():
    """EPSILON（元，4 位）与 PERCENT_TAIL_TOLERANCE（%，2 位）口径分离。"""
    assert EPSILON == Decimal('0.0001')
    assert PERCENT_TAIL_TOLERANCE == Decimal('0.01')
    assert EPSILON.as_tuple().exponent == -4
    assert PERCENT_TAIL_TOLERANCE.as_tuple().exponent == -2
