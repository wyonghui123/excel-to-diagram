# -*- coding: utf-8 -*-
"""交货单守卫拦截器测试（M1-3 / M1-5 / M1-7）—— 纯单元，不连 DB。

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.3 / §10.4
      docs/superpowers/specs/2026-10-29-so-wave3/spec_m1_closeout.md（M1-3/M1-4）

测试策略:
  · 用 types.SimpleNamespace 构造最小上下文（无 object_id property，
    走拦截器的 `_object_id` 兜底读 params['id']）；
  · monkeypatch 替换模块内 ShipmentService / SalesOrderFulfillmentService 为记录调用的假类，
    断言委托方法、入参与回填，不触碰真实库。
"""

import types

import pytest

pytestmark = pytest.mark.unit

import meta.core.interceptors.shipment_guard_interceptor as guard_module
from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.shipment_guard_interceptor import ShipmentGuardInterceptor
from meta.services.shipment_service import ShipmentError

_LINE_COLUMNS = ('schedule_id', 'order_line_id', 'item_id', 'uom_id', 'qty')


def _install(monkeypatch, order_id=None, error=None, recompute_status='partial'):
    """替换两个服务为假类，返回调用记录列表 `[(method, args, kwargs)]`。"""
    calls = []

    class FakeShipmentService:
        def __init__(self, data_source=None):
            self.data_source = data_source

        def _record(self, method, *args, **kwargs):
            calls.append((method, args, kwargs))
            if error is not None:
                raise error

        def release(self, delivery_id):
            self._record('release', delivery_id)
            return {'id': delivery_id, 'status': 'released', 'order_id': order_id}

        def stage(self, delivery_id):
            self._record('stage', delivery_id)
            return {'id': delivery_id, 'status': 'staged'}

        def ship_confirm(self, delivery_id, actual_ship_date=None):
            self._record('ship_confirm', delivery_id,
                         actual_ship_date=actual_ship_date)
            return {'id': delivery_id, 'status': 'shipped',
                    'order_id': order_id, 'line_ids': []}

        def receive(self, delivery_id, signature_ref=None,
                    actual_arrival_date=None):
            self._record('receive', delivery_id,
                         signature_ref=signature_ref,
                         actual_arrival_date=actual_arrival_date)
            return {'id': delivery_id, 'status': 'delivered'}

        def cancel(self, delivery_id):
            self._record('cancel', delivery_id)
            return {'id': delivery_id, 'status': 'cancelled'}

        def assert_deletable(self, delivery_id):
            self._record('assert_deletable', delivery_id)

        def validate_new_line(self, payload):
            self._record('validate_new_line', payload)
            return {'schedule_id': 55, 'order_line_id': 66, 'item_id': 77,
                    'uom_id': 88, 'qty': 9.5}

        def update_line(self, line_id, patch):
            self._record('update_line', line_id, patch)
            return {'schedule_id': 55, 'order_line_id': 66, 'item_id': 77,
                    'uom_id': 88, 'qty': 9.5}

    class FakeFulfillmentService:
        def __init__(self, data_source=None):
            self.data_source = data_source

        def recompute_order(self, order_id):
            calls.append(('recompute_order', (order_id,), {}))
            return recompute_status

    monkeypatch.setattr(guard_module, 'ShipmentService', FakeShipmentService)
    monkeypatch.setattr(guard_module, 'SalesOrderFulfillmentService',
                        FakeFulfillmentService)
    return calls


def _context(action='crud_update', object_id='shipment', params=None,
             old_data=None, result=None, extra=None):
    return types.SimpleNamespace(
        meta_object=types.SimpleNamespace(id=object_id),
        action=action,
        params={} if params is None else params,
        data_source=object(),
        old_data={} if old_data is None else old_data,
        result=result,
        extra={} if extra is None else extra,
    )


def _header_context(target, current, params=None, action='crud_update'):
    payload = {'id': 7, 'status': target}
    payload.update(params or {})
    return _context(action=action, params=payload,
                    old_data={'id': 7, 'status': current})


# ---------------------------------------------------------------- should_execute

def test_should_execute_on_shipment_update():
    interceptor = ShipmentGuardInterceptor()
    context = _context()
    assert interceptor.should_execute(context) is True


def test_should_execute_skips_other_objects():
    interceptor = ShipmentGuardInterceptor()
    context = _context(object_id='sales_order')
    assert interceptor.should_execute(context) is False


def test_should_execute_skips_read_action():
    interceptor = ShipmentGuardInterceptor()
    context = _context(action='crud_read')
    assert interceptor.should_execute(context) is False


def test_priority_is_51():
    assert ShipmentGuardInterceptor().priority == 51


# ---------------------------------------------------------------- 抬头状态迁移

def test_released_delegates_to_release(monkeypatch):
    calls = _install(monkeypatch)
    ShipmentGuardInterceptor().before_action(
        _header_context('released', 'draft'))
    assert calls == [('release', (7,), {})]


def test_staged_delegates_to_stage(monkeypatch):
    calls = _install(monkeypatch)
    ShipmentGuardInterceptor().before_action(
        _header_context('staged', 'released'))
    assert calls == [('stage', (7,), {})]


def test_shipped_delegates_to_ship_confirm(monkeypatch):
    calls = _install(monkeypatch, order_id=42)
    context = _header_context('shipped', 'staged',
                              params={'actual_ship_date': '2026-10-30 10:00:00'})
    ShipmentGuardInterceptor().before_action(context)
    assert calls == [('ship_confirm', (7,),
                      {'actual_ship_date': '2026-10-30 10:00:00'})]
    assert context.extra['shipment_result']['order_id'] == 42
    assert context.extra['shipment_order_id'] == 42


def test_delivered_delegates_to_receive(monkeypatch):
    calls = _install(monkeypatch)
    context = _header_context('delivered', 'shipped',
                              params={'signature_ref': 'SIG-1',
                                      'actual_arrival_date': '2026-10-31 09:00:00'})
    ShipmentGuardInterceptor().before_action(context)
    assert calls == [('receive', (7,),
                      {'signature_ref': 'SIG-1',
                       'actual_arrival_date': '2026-10-31 09:00:00'})]


def test_cancelled_delegates_to_cancel(monkeypatch):
    calls = _install(monkeypatch)
    ShipmentGuardInterceptor().before_action(
        _header_context('cancelled', 'draft'))
    assert calls == [('cancel', (7,), {})]


def test_closed_does_not_delegate(monkeypatch):
    calls = _install(monkeypatch)
    ShipmentGuardInterceptor().before_action(
        _header_context('closed', 'delivered'))
    assert calls == []


def test_unchanged_status_does_not_delegate(monkeypatch):
    calls = _install(monkeypatch)
    ShipmentGuardInterceptor().before_action(
        _header_context('shipped', 'shipped'))
    assert calls == []


def test_blank_status_does_not_delegate(monkeypatch):
    calls = _install(monkeypatch)
    context = _context(params={'id': 7}, old_data={'id': 7, 'status': 'draft'})
    ShipmentGuardInterceptor().before_action(context)
    assert calls == []


def test_delete_asserts_deletable(monkeypatch):
    calls = _install(monkeypatch)
    context = _context(action='crud_delete', params={'id': 7},
                       old_data={'id': 7, 'status': 'shipped'})
    ShipmentGuardInterceptor().before_action(context)
    assert calls == [('assert_deletable', (7,), {})]


def test_service_error_becomes_validation_failed(monkeypatch):
    _install(monkeypatch, error=ShipmentError(
        'x', field_name='status', rule='DN_STATE_INVALID'))
    context = _header_context('shipped', 'staged')
    with pytest.raises(ValidationFailedError) as excinfo:
        ShipmentGuardInterceptor().before_action(context)
    assert excinfo.value.details[0]['rule'] == 'DN_STATE_INVALID'
    assert excinfo.value.details[0]['field_name'] == 'status'


# ---------------------------------------------------------------- 交货行

def test_line_create_validates_and_backfills(monkeypatch):
    calls = _install(monkeypatch)
    params = {'id': 9, 'delivery_id': 5, 'schedule_id': 55, 'qty': 3}
    context = _context(action='crud_create', object_id='shipment_line',
                       params=params)
    ShipmentGuardInterceptor().before_action(context)
    assert calls[0][0] == 'validate_new_line'
    assert [params[key] for key in _LINE_COLUMNS] == [55, 66, 77, 88, 9.5]


def test_line_update_delegates_and_backfills(monkeypatch):
    calls = _install(monkeypatch)
    params = {'id': 9, 'schedule_id': 55, 'qty': 4}
    context = _context(action='crud_update', object_id='shipment_line',
                       params=params)
    ShipmentGuardInterceptor().before_action(context)
    assert calls[0] == ('update_line', (9, params), {})
    assert [params[key] for key in _LINE_COLUMNS] == [55, 66, 77, 88, 9.5]


def test_line_delete_does_nothing(monkeypatch):
    calls = _install(monkeypatch)
    context = _context(action='crud_delete', object_id='shipment_line',
                       params={'id': 9})
    ShipmentGuardInterceptor().before_action(context)
    assert calls == []


# ---------------------------------------------------------------- 履约状态接线

def test_after_action_recomputes_and_merges_status(monkeypatch):
    calls = _install(monkeypatch)
    context = _context(extra={'shipment_order_id': 42},
                       result=types.SimpleNamespace(data={'id': 7}))
    ShipmentGuardInterceptor().after_action(context)
    assert calls == [('recompute_order', (42,), {})]
    assert context.result.data['fulfillment_status'] == 'partial'


def test_after_action_without_order_id_skips_recompute(monkeypatch):
    calls = _install(monkeypatch)
    context = _context(result=types.SimpleNamespace(data={'id': 7}))
    ShipmentGuardInterceptor().after_action(context)
    assert calls == []
