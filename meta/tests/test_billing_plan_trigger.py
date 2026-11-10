# -*- coding: utf-8 -*-
"""订单确认触发生成 + sales_order.generate_billing_plan 补跑 Action（T38）。

依据: docs/specs/s8-customer-invoice-wave-c/spec.md §6.2
夹具: meta/tests/factories/_billing_plan_helpers.py
"""
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.core.action_context import ActionResult
from meta.core.bo_action_registry import BoActionRegistry
from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.sales_order_guard_interceptor import (
    SalesOrderGuardInterceptor,
)
from meta.services import billing_plan_actions
from meta.services.billing_plan_service import BillingPlanService
from meta.services.bo_action_registrations import register_all_bo_actions
from meta.tests.factories._billing_plan_helpers import (
    LINE_TM,
    ORDER_ID,
    add_line,
    build_conn,
    list_schedules,
    make_ds,
)

ACTION_ID = 'sales_order.generate_billing_plan'


def _ctx(ds, *, action='crud_update', params=None, old_data=None,
         result_data=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id='sales_order'),
        action=action,
        object_id=ORDER_ID,
        params=params or {},
        old_data=old_data,
        extra={},
        data_source=ds,
        result=ActionResult(success=True, data=result_data or {}),
    )


def test_confirm_triggers_generation():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, anchor='2026-01-15')
    ctx = _ctx(make_ds(conn), params={'status': 'confirmed'},
               old_data={'status': 'draft'})

    SalesOrderGuardInterceptor().after_action(ctx)

    rows = list_schedules(conn, LINE_TM)
    assert len(rows) == 3
    assert ctx.result.data['billing_plan_created'] == [r['id'] for r in rows]


def test_confirm_replay_is_idempotent():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, anchor='2026-01-15')
    interceptor = SalesOrderGuardInterceptor()

    interceptor.after_action(_ctx(make_ds(conn), params={'status': 'confirmed'},
                                  old_data={'status': 'draft'}))
    ctx = _ctx(make_ds(conn), params={'status': 'confirmed'},
               old_data={'status': 'draft'})
    interceptor.after_action(ctx)

    assert len(list_schedules(conn, LINE_TM)) == 3
    assert 'billing_plan_created' not in ctx.result.data


def test_non_confirm_update_skips_generation():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, anchor='2026-01-15')
    ctx = _ctx(make_ds(conn), params={'status': 'closed'},
               old_data={'status': 'confirmed'})

    SalesOrderGuardInterceptor().after_action(ctx)

    assert list_schedules(conn, LINE_TM) == []


def test_confirm_generation_failure_rejects_order():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, anchor='2026-01-01',
             proration='daily', service_start='2027-01-01',
             service_end='2027-02-01')
    ctx = _ctx(make_ds(conn), params={'status': 'confirmed'},
               old_data={'status': 'draft'})

    with pytest.raises(ValidationFailedError) as exc:
        SalesOrderGuardInterceptor().after_action(ctx)
    assert exc.value.details[0]['rule'] == 'ORDER_BILLING_PLAN_INVALID'
    assert list_schedules(conn, LINE_TM) == []


def _bind_service(monkeypatch, conn):
    monkeypatch.setattr(
        billing_plan_actions, '_service',
        lambda: BillingPlanService(make_ds(conn)))


def test_action_generates_and_reports_created(monkeypatch):
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, anchor='2026-01-15')
    _bind_service(monkeypatch, conn)

    result = billing_plan_actions.generate_billing_plan_handler(
        {'order_id': ORDER_ID})

    assert result['success'] is True
    assert result['data']['order_id'] == ORDER_ID
    assert len(result['data']['created']) == 3
    assert result['data']['skipped'] is False
    assert '3' in result['message']


def test_action_is_idempotent(monkeypatch):
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, anchor='2026-01-15')
    _bind_service(monkeypatch, conn)

    billing_plan_actions.generate_billing_plan_handler({'order_id': ORDER_ID})
    result = billing_plan_actions.generate_billing_plan_handler(
        {'order_id': ORDER_ID})

    assert result['success'] is True
    assert result['data']['created'] == []
    assert result['data']['skipped'] is True
    assert len(list_schedules(conn, LINE_TM)) == 3


def test_action_requires_order_id(monkeypatch):
    conn = build_conn()
    _bind_service(monkeypatch, conn)

    result = billing_plan_actions.generate_billing_plan_handler({})

    assert result['success'] is False
    assert result['code'] == 'INVALID_ARGUMENT'


def test_action_rejects_draft_order(monkeypatch):
    conn = build_conn(order_status='draft')
    add_line(conn, LINE_TM, period_count=3)
    _bind_service(monkeypatch, conn)

    result = billing_plan_actions.generate_billing_plan_handler(
        {'order_id': ORDER_ID})

    assert result['success'] is False
    assert result['code'] == 'ORDER_BILLING_PLAN_INVALID'
    assert list_schedules(conn, LINE_TM) == []


def test_action_registered_with_permission():
    registry = BoActionRegistry()
    register_all_bo_actions(registry)

    meta = registry.get(ACTION_ID)
    assert meta is not None
    assert meta.object_type == 'sales_order'
    assert meta.category == 'business'
    assert meta.permission_required == 'sales_order:sales_order_update'
    assert meta.requires_auth is True
    assert meta.idempotent is True