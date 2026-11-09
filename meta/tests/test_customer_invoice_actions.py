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
    assert meta.permission_required == 'customer_invoice:customer_invoice_create'
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
    assert meta.permission_required == 'customer_invoice:customer_invoice_create'
    assert meta.requires_auth is True
    assert meta.idempotent is False
