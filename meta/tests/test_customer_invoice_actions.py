# -*- coding: utf-8 -*-
"""销售发票 BO Action 测试（S8 Wave A / B2）。

依据: docs/specs/s8-customer-invoice-wave-a/spec.md §13.6
夹具: meta/tests/factories/_customer_invoice_helpers.py（内存库，raw SQL 在工厂内）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.core.bo_action_registry import BoActionRegistry
from meta.services import customer_invoice_actions
from meta.services.bo_action_registrations import register_all_bo_actions
from meta.services.customer_invoice_service import CustomerInvoiceService
from meta.tests.factories._customer_invoice_helpers import (
    BILLING_SCHEDULE_ID,
    INVOICE_DATE,
    ORDER_ID,
    SHIPMENT_ID,
    build_conn,
    fetch_one,
    get_header,
    get_lines,
    make_ds,
    set_shipment_status,
)

ACTION_ID = 'customer_invoice.create_from_shipment'
CREDIT_ACTION_ID = 'customer_invoice.create_credit_from_invoice'


def _bind_service(monkeypatch, conn):
    monkeypatch.setattr(
        customer_invoice_actions, '_service',
        lambda: CustomerInvoiceService(make_ds(conn)))


def _invoice_count(conn):
    return fetch_one(
        conn, 'SELECT COUNT(*) AS n FROM customer_invoices')['n']


def test_create_from_shipment_handler_creates_draft(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.create_from_shipment_handler(
        {'shipment_id': SHIPMENT_ID})

    assert result['success'] is True
    assert result['data']['status'] == 'draft'
    assert result['data']['invoice_no'].startswith('SINV-')
    assert result['data']['shipment_id'] == SHIPMENT_ID
    header = get_header(conn, result['data']['id'])
    assert header['document_category'] == 'invoice'
    assert len(get_lines(conn, result['data']['id'])) == 2
    assert result['data']['amounts']['gross_amount'] == 565.0
    assert 'SINV-' in result['message']


def test_create_from_shipment_handler_requires_shipment_id(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.create_from_shipment_handler({})

    assert result['success'] is False
    assert result['code'] == 'INVALID_ARGUMENT'
    assert _invoice_count(conn) == 0


def test_create_from_shipment_handler_rejects_unshipped(monkeypatch):
    conn = build_conn()
    set_shipment_status(conn, 'draft')
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.create_from_shipment_handler(
        {'shipment_id': SHIPMENT_ID})

    assert result['success'] is False
    assert result['code'] == 'INVOICE_SHIPMENT_STATE_INVALID'
    assert _invoice_count(conn) == 0


def test_action_is_registered_with_permission():
    registry = BoActionRegistry()
    register_all_bo_actions(registry)

    meta = registry.get(ACTION_ID)
    assert meta is not None
    assert meta.object_type == 'customer_invoice'
    assert meta.category == 'business'
    assert meta.permission_required == 'customer_invoice:create'
    assert meta.requires_auth is True
    assert meta.idempotent is False


# ---------------------------------------------------------------- B5 独立贷项

def _posted_invoice(conn):
    service = CustomerInvoiceService(make_ds(conn))
    created = service.create_from_shipment(
        {'shipment_id': SHIPMENT_ID, 'invoice_date': '2026-11-09'})
    service.submit(created['id'])
    service.post(created['id'])
    return created['id']


def test_create_credit_handler_creates_draft(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    source_id = _posted_invoice(conn)

    result = customer_invoice_actions.create_credit_from_invoice_handler(
        {'source_doc_id': source_id, 'reason': '价格调整'})

    assert result['success'] is True
    assert result['data']['status'] == 'draft'
    assert result['data']['invoice_no'].startswith('SCR-')
    header = get_header(conn, result['data']['id'])
    assert header['document_category'] == 'credit_memo'
    assert header['reversal_of_invoice_id'] == source_id
    assert header['reversal_reason'] == '价格调整'
    assert result['data']['amounts']['gross_amount'] == -565.0
    assert 'SCR-' in result['message']


def test_create_credit_handler_requires_source(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.create_credit_from_invoice_handler({})

    assert result['success'] is False
    assert result['code'] == 'INVALID_ARGUMENT'
    assert _invoice_count(conn) == 0


def test_credit_action_is_registered_with_permission():
    registry = BoActionRegistry()
    register_all_bo_actions(registry)

    meta = registry.get(CREDIT_ACTION_ID)
    assert meta is not None
    assert meta.object_type == 'customer_invoice'
    assert meta.category == 'business'
    assert meta.permission_required == (
        'customer_invoice:credit_memo')
    assert meta.requires_auth is True
    assert meta.idempotent is False


# ---------------------------------------------------------------- C4 on-account 贷项

ON_ACCOUNT_ACTION_ID = 'customer_invoice.create_credit_on_account'

ON_ACCOUNT_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': 900,
    'currency_id': 1,
    'org_id': 10,
}


def test_create_credit_on_account_handler_creates_draft(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.create_credit_on_account_handler(dict(
        ON_ACCOUNT_HEADER, reason='年度折让',
        lines=[{'description': '年度返利', 'uom_id': 21, 'tax_code_id': 31,
                'qty': 1, 'unit_price': -100, 'tax_rate_percent': 6}]))

    assert result['success'] is True
    assert result['data']['status'] == 'draft'
    assert result['data']['invoice_no'].startswith('SCR-')
    header = get_header(conn, result['data']['id'])
    assert header['document_category'] == 'credit_memo'
    assert header['reversal_of_invoice_id'] is None
    line = get_lines(conn, result['data']['id'])[0]
    assert line['source_doc_type'] == 'manual'
    assert result['data']['amounts']['gross_amount'] == -106.0


def test_create_credit_on_account_handler_requires_lines(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.create_credit_on_account_handler(
        dict(ON_ACCOUNT_HEADER, lines=[]))

    assert result['success'] is False
    assert result['code'] == 'INVALID_ARGUMENT'
    assert _invoice_count(conn) == 0


def test_on_account_action_is_registered_with_permission():
    registry = BoActionRegistry()
    register_all_bo_actions(registry)

    meta = registry.get(ON_ACCOUNT_ACTION_ID)
    assert meta is not None
    assert meta.object_type == 'customer_invoice'
    assert meta.category == 'business'
    assert meta.permission_required == (
        'customer_invoice:credit_memo')
    assert meta.requires_auth is True
    assert meta.idempotent is False


# ---------------------------------------------------------------- Wave B 计划期次

PLAN_ACTION_ID = 'customer_invoice.create_from_schedule'
DUE_ACTION_ID = 'customer_invoice.list_due_schedules'


def test_create_from_schedule_handler_creates_draft(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.create_from_schedule_handler(
        {'schedule_ids': [BILLING_SCHEDULE_ID], 'invoice_date': INVOICE_DATE})

    assert result['success'] is True
    assert result['data']['status'] == 'draft'
    assert result['data']['invoice_no'].startswith('SINV-')
    assert result['data']['order_id'] == ORDER_ID
    line = get_lines(conn, result['data']['id'])[0]
    assert line['source_doc_type'] == 'billing_schedule'
    assert line['schedule_id'] == BILLING_SCHEDULE_ID
    assert result['data']['amounts']['gross_amount'] == 1130.0
    assert 'SINV-' in result['message']


def test_create_from_schedule_handler_requires_schedule(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.create_from_schedule_handler({})

    assert result['success'] is False
    assert result['code'] == 'INVALID_ARGUMENT'
    assert _invoice_count(conn) == 0


def test_list_due_schedules_handler_returns_due_items(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.list_due_schedules_handler(
        {'as_of': '2026-11-20'})

    assert result['success'] is True
    assert result['data']['total'] == 1
    item = result['data']['items'][0]
    assert item['schedule_id'] == BILLING_SCHEDULE_ID
    assert item['line_no'] == 12
    assert item['period_amount'] == 1000.0
    assert item['remaining_amount'] == 1000.0
    assert '1 条' in result['message']


def test_list_due_schedules_handler_empty_before_promised_date(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = customer_invoice_actions.list_due_schedules_handler(
        {'as_of': '2026-11-01'})

    assert result['success'] is True
    assert result['data']['total'] == 0
    assert result['data']['items'] == []


def test_plan_actions_registered_with_permission():
    registry = BoActionRegistry()
    register_all_bo_actions(registry)

    create_meta = registry.get(PLAN_ACTION_ID)
    assert create_meta is not None
    assert create_meta.object_type == 'customer_invoice'
    assert create_meta.category == 'business'
    assert create_meta.permission_required == (
        'customer_invoice:create')
    assert create_meta.idempotent is False

    due_meta = registry.get(DUE_ACTION_ID)
    assert due_meta is not None
    assert due_meta.object_type == 'customer_invoice'
    assert due_meta.category == 'query'
    assert due_meta.permission_required == (
        'customer_invoice:read')
    assert due_meta.requires_auth is True
    assert due_meta.idempotent is True


# ---------------------------------------------------------------- Wave C 单据动作

SUBMIT_ACTION_ID = 'customer_invoice.submit'
POST_ACTION_ID = 'customer_invoice.post'
REVERSE_ACTION_ID = 'customer_invoice.reverse'


def _draft_invoice(conn):
    service = CustomerInvoiceService(make_ds(conn))
    created = service.create_from_shipment(
        {'shipment_id': SHIPMENT_ID, 'invoice_date': '2026-11-09'})
    return created['id']


def _submitted_invoice(conn):
    invoice_id = _draft_invoice(conn)
    CustomerInvoiceService(make_ds(conn)).submit(invoice_id)
    return invoice_id


def _posted_invoice_vc(conn):
    invoice_id = _submitted_invoice(conn)
    CustomerInvoiceService(make_ds(conn)).post(invoice_id)
    return invoice_id


def _red_count(conn, invoice_id):
    return fetch_one(
        conn,
        'SELECT COUNT(*) AS n FROM customer_invoices '
        'WHERE reversal_of_invoice_id = ?', [invoice_id])['n']


def test_action_submit_ok(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _draft_invoice(conn)

    result = customer_invoice_actions.submit_handler({'invoice_id': invoice_id})

    assert result['success'] is True
    assert result['data']['status'] == 'submitted'
    assert result['data']['invoice_no'].startswith('SINV-')
    assert get_header(conn, invoice_id)['status'] == 'submitted'


def test_action_submit_idempotent(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _submitted_invoice(conn)

    first = customer_invoice_actions.submit_handler(
        {'source_doc_id': invoice_id})
    second = customer_invoice_actions.submit_handler(
        {'source_doc_id': invoice_id})

    assert first['success'] is True
    assert second['success'] is True
    assert first['data']['status'] == second['data']['status'] == 'submitted'
    assert '已提交' in second['message']
    assert get_header(conn, invoice_id)['status'] == 'submitted'


def test_action_submit_invalid_state(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _draft_invoice(conn)
    CustomerInvoiceService(make_ds(conn)).cancel(invoice_id)

    result = customer_invoice_actions.submit_handler({'invoice_id': invoice_id})

    assert result['success'] is False
    assert result['code'] == 'INVOICE_STATE_INVALID'
    assert get_header(conn, invoice_id)['status'] == 'cancelled'


def test_action_post_ok(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _submitted_invoice(conn)

    result = customer_invoice_actions.post_handler({'invoice_id': invoice_id})

    assert result['success'] is True
    assert result['data']['status'] == 'posted'
    assert result['data']['posting_date']
    assert get_header(conn, invoice_id)['status'] == 'posted'


def test_action_post_idempotent(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _posted_invoice_vc(conn)

    result = customer_invoice_actions.post_handler({'invoice_id': invoice_id})

    assert result['success'] is True
    assert result['data']['status'] == 'posted'
    assert '已过账' in result['message']


def test_action_post_from_draft_rejected(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _draft_invoice(conn)

    result = customer_invoice_actions.post_handler({'invoice_id': invoice_id})

    assert result['success'] is False
    assert result['code'] == 'INVOICE_STATE_INVALID'
    assert get_header(conn, invoice_id)['status'] == 'draft'


def test_action_reverse_ok(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _posted_invoice_vc(conn)

    result = customer_invoice_actions.reverse_handler({
        'invoice_id': invoice_id,
        'reason': '客户退货',
        'reversal_date': '2026-11-10',
    })

    assert result['success'] is True
    assert result['data']['status'] == 'reversed'
    assert result['data']['original_invoice_id'] == invoice_id
    assert result['data']['red_invoice_no'].startswith('SRV-')
    assert _red_count(conn, invoice_id) == 1


def test_action_reverse_idempotent(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _posted_invoice_vc(conn)

    first = customer_invoice_actions.reverse_handler(
        {'invoice_id': invoice_id, 'reason': '客户退货'})
    second = customer_invoice_actions.reverse_handler(
        {'invoice_id': invoice_id, 'reason': '客户退货'})

    assert first['success'] is True
    assert second['success'] is True
    assert first['data']['red_invoice_id'] == second['data']['red_invoice_id']
    assert '已红冲' in second['message']
    assert _red_count(conn, invoice_id) == 1


def test_action_reverse_requires_reason(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)
    invoice_id = _posted_invoice_vc(conn)

    result = customer_invoice_actions.reverse_handler({'invoice_id': invoice_id})

    assert result['success'] is False
    assert result['code'] == 'INVOICE_REVERSE_INVALID'
    assert _red_count(conn, invoice_id) == 0


def test_action_register_submit_post_reverse():
    registry = BoActionRegistry()
    register_all_bo_actions(registry)

    expectations = (
        (SUBMIT_ACTION_ID, 'customer_invoice:submit'),
        (POST_ACTION_ID, 'customer_invoice:post'),
        (REVERSE_ACTION_ID, 'customer_invoice:reverse'),
    )
    for action_id, permission in expectations:
        meta = registry.get(action_id)
        assert meta is not None, action_id
        assert meta.object_type == 'customer_invoice'
        assert meta.category == 'business'
        assert meta.permission_required == permission
        assert meta.requires_auth is True
        assert meta.idempotent is True
