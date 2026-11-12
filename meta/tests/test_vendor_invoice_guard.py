# -*- coding: utf-8 -*-
"""采购发票守卫拦截器测试（W5）—— 状态迁移接线与写保护。

夹具：meta/tests/factories/_vendor_invoice_helpers.py（v252 生产 DDL）。
状态迁移的跨表副作用由 vendor_invoice_match_service 负责，本测试只验证
委托是否发生、入参是否被收紧，因此对 submit / post / cancel 打桩。
"""

import types

import pytest

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.vendor_invoice_guard_interceptor import (
    VendorInvoiceGuardInterceptor,
)
from meta.services.vendor_invoice_match_service import VendorInvoiceMatchService
from meta.tests.factories._vendor_invoice_helpers import (
    make_env,
    insert_invoice,
    insert_line,
)


def _ctx(ds, object_id, action, params, old_data=None, result=None):
    return types.SimpleNamespace(
        meta_object=types.SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        extra={},
        data_source=ds,
        result=result,
    )


def _rule(error):
    assert isinstance(error.value, ValidationFailedError)
    return error.value.details[0]['rule']


_INTERCEPTOR = VendorInvoiceGuardInterceptor()


# ---------------------------------------------------------------- 作用域

def test_should_execute_limits_to_header_and_line_write_actions():
    env = types.SimpleNamespace()
    for object_id in ('vendor_invoice', 'vendor_invoice_line'):
        assert _INTERCEPTOR.should_execute(
            _ctx(env, object_id, 'crud_create', {})) is True
    assert _INTERCEPTOR.should_execute(
        _ctx(env, 'vendor_invoice', 'crud_read', {})) is False
    assert _INTERCEPTOR.should_execute(
        _ctx(env, 'customer_invoice', 'crud_create', {})) is False


# ---------------------------------------------------------------- 抬头写保护

def test_vendor_create_rejects_non_draft_status(tmp_path):
    ds = make_env(tmp_path)
    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(ds, 'vendor_invoice', 'crud_create', {'status': 'posted'}))
    assert _rule(error) == 'VI_STATE_INVALID'


@pytest.mark.parametrize(
    'category', ['credit_memo', 'debit_memo', 'cancellation'])
def test_vendor_create_rejects_manual_adjustment_documents(tmp_path, category):
    ds = make_env(tmp_path)
    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'vendor_invoice', 'crud_create',
            {'document_category': category}))
    assert _rule(error) == 'VI_MANUAL_ADJUSTMENT_FORBIDDEN'


def test_delete_requires_draft(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='submitted')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(
            _ctx(ds, 'vendor_invoice', 'crud_delete', {'id': invoice_id}))
    assert _rule(error) == 'VI_DELETE_FORBIDDEN'


def test_posted_update_is_readonly(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='posted')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'vendor_invoice', 'crud_update',
            {'id': invoice_id, 'remark': 'x'},
            old_data={'status': 'posted'}))
    assert _rule(error) == 'VI_POSTED_READONLY'


def test_posted_reverse_requires_reason(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='posted')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'vendor_invoice', 'crud_update',
            {'id': invoice_id, 'status': 'reversed'},
            old_data={'status': 'posted'}))
    assert _rule(error) == 'VI_REVERSAL_REASON_REQUIRED'


def test_posted_reverse_delegates_service_reverse(tmp_path, monkeypatch):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='posted')
    calls = []

    monkeypatch.setattr(
        VendorInvoiceMatchService, 'reverse',
        lambda self, iid, *, reason: calls.append((iid, reason)) or {
            'invoice_id': iid, 'status': 'reversed',
            'reversal_reason': reason, 'red_invoice_id': 999,
            'red_invoice_no': 'VCM-0001', 'red_line_ids': [1001]})

    params = {'id': invoice_id, 'status': 'reversed', 'reversal_reason': '供应商退回'}
    context = _ctx(ds, 'vendor_invoice', 'crud_update', params,
                   old_data={'status': 'posted'})
    _INTERCEPTOR.before_action(context)

    assert calls == [(invoice_id, '供应商退回')]
    # 只保留状态推进参数（避免二次写入触发 posted 只读校验）
    assert params == {'id': invoice_id, 'status': 'reversed'}
    result = context.extra['vendor_invoice_result']
    assert result['red_invoice_id'] == 999
    assert result['reversal_reason'] == '供应商退回'


def test_posted_reverse_rejects_extra_fields(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='posted')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'vendor_invoice', 'crud_update',
            {'id': invoice_id, 'status': 'reversed',
             'reversal_reason': 'x', 'remark': 'y'},
            old_data={'status': 'posted'}))
    assert _rule(error) == 'VI_POSTED_READONLY'


def test_submitted_content_is_locked(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='submitted')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'vendor_invoice', 'crud_update',
            {'id': invoice_id, 'supplier_invoice_no': 'NEW-1'},
            old_data={'status': 'submitted'}))
    assert _rule(error) == 'VI_POSTED_READONLY'


def test_cancelled_is_terminal(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='cancelled')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'vendor_invoice', 'crud_update',
            {'id': invoice_id, 'status': 'draft'},
            old_data={'status': 'cancelled'}))
    assert _rule(error) == 'VI_POSTED_READONLY'


# ---------------------------------------------------------------- 状态迁移委托

def test_vendor_draft_to_submitted_delegates_submit_and_tightens_params(
        tmp_path, monkeypatch):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='draft')
    calls = []

    monkeypatch.setattr(
        VendorInvoiceMatchService, 'submit',
        lambda self, iid: calls.append(iid) or {
            'invoice_id': iid, 'status': 'submitted',
            'match_status': 'matched', 'match_exception_reason': None})

    params = {'id': invoice_id, 'status': 'submitted', 'remark': '旧值'}
    context = _ctx(ds, 'vendor_invoice', 'crud_update', params,
                   old_data={'status': 'draft'})
    _INTERCEPTOR.before_action(context)

    assert calls == [invoice_id]
    assert params == {'id': invoice_id, 'status': 'submitted'}
    assert context.extra['vendor_invoice_result']['status'] == 'submitted'


def test_submitted_to_posted_delegates_post(tmp_path, monkeypatch):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='submitted')
    calls = []

    monkeypatch.setattr(
        VendorInvoiceMatchService, 'post',
        lambda self, iid: calls.append(iid) or {
            'invoice_id': iid, 'status': 'posted'})

    _INTERCEPTOR.before_action(_ctx(
        ds, 'vendor_invoice', 'crud_update',
        {'id': invoice_id, 'status': 'posted'},
        old_data={'status': 'submitted'}))

    assert calls == [invoice_id]


def test_illegal_transition_is_rejected(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='draft')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'vendor_invoice', 'crud_update',
            {'id': invoice_id, 'status': 'posted'},
            old_data={'status': 'draft'}))
    assert _rule(error) == 'VI_STATE_INVALID'


def test_after_action_merges_service_result(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='submitted')
    context = _ctx(ds, 'vendor_invoice', 'crud_update',
                   {'id': invoice_id, 'status': 'posted'},
                   old_data={'status': 'submitted'},
                   result=types.SimpleNamespace(data={'id': invoice_id}))
    context.extra['vendor_invoice_result'] = {
        'invoice_id': invoice_id, 'status': 'posted',
        'match_status': 'matched', 'match_exception_reason': None,
    }

    _INTERCEPTOR.after_action(context)

    assert context.result.data['status'] == 'posted'
    assert context.result.data['match_status'] == 'matched'


# ---------------------------------------------------------------- 行写保护

def test_line_create_requires_draft_parent(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='posted')

    with pytest.raises(ValidationFailedError) as error:
        _INTERCEPTOR.before_action(_ctx(
            ds, 'vendor_invoice_line', 'crud_create',
            {'invoice_id': invoice_id, 'qty': 1}))
    assert _rule(error) == 'VI_POSTED_READONLY'


def test_line_create_autofills_line_no(tmp_path):
    ds = make_env(tmp_path)
    invoice_id = insert_invoice(ds, status='draft')
    insert_line(ds, invoice_id, line_no=1)

    params = {'invoice_id': invoice_id, 'qty': 2}
    _INTERCEPTOR.before_action(
        _ctx(ds, 'vendor_invoice_line', 'crud_create', params))

    assert params['line_no'] == 2