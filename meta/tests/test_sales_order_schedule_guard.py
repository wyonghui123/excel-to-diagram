# -*- coding: utf-8 -*-
"""销售订单计划行守卫测试（R-SCH-0 ~ R-SCH-10）

依据: meta/schemas/sales_order_schedule.yaml
      docs/superpowers/specs/2026-10-26-sales-order-schedule-line-spec.md §3
"""

import pytest

pytestmark = pytest.mark.unit

from meta.services import sales_order_guard_service as guard_module
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)


class _FakeDS:
    """按 SQL 特征片段分流，只覆盖计划行守卫用到的查询。"""

    def __init__(self, orders=None, lines=None, schedules=None,
                 delivery_sum=0.0, edges=None, raise_on_query=False):
        self.orders = orders or {}
        self.lines = lines or {}
        self.schedules = schedules or {}
        self.delivery_sum = delivery_sum
        self.edges = edges or set()
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError('db down')
        p = list(params or [])

        if 'COALESCE(SUM(promised_qty)' in sql:
            return [{'qty': self.delivery_sum}]
        if 'FROM doc_flow_edges' in sql:
            return [{'ok': 1}] if (p[0], p[1]) in self.edges else []
        if 'FROM sales_order_schedules WHERE id' in sql:
            row = self.schedules.get(p[0])
            return [row] if row else []
        if 'FROM sales_order_lines WHERE id' in sql:
            row = self.lines.get(p[0])
            return [row] if row else []
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        raise AssertionError('unexpected sql: %s' % sql)


ORDERS = {
    10: {'id': 10, 'status': 'draft'},
    11: {'id': 11, 'status': 'submitted'},
}

LINES = {
    # 订单 10 的订单行：数量 10，订单行未指定发货点
    100: {'id': 100, 'order_id': 10, 'qty': 10, 'uom_id': 8,
          'plant_location_id': None},
    # 订单 11 的订单行：数量 5，订单行已指定发货点（默认继承）
    101: {'id': 101, 'order_id': 11, 'qty': 5, 'uom_id': 8,
          'plant_location_id': 900},
    # 订单 10 的另一条订单行：数量 4，订单行已指定发货点
    102: {'id': 102, 'order_id': 10, 'qty': 4, 'uom_id': 8,
          'plant_location_id': 900},
}

SCHEDULES = {
    # 草稿订单下的计划行（可删）
    200: {'id': 200, 'order_id': 10, 'line_id': 100, 'schedule_no': 10,
          'schedule_kind': 'delivery', 'promised_date': '2026-11-01',
          'promised_qty': 1, 'plant_location_id': 900,
          'milestone_code': None, 'service_visit_no': None,
          'status': 'planned'},
    # 已提交订单下的计划行（不可删）
    201: {'id': 201, 'order_id': 11, 'line_id': 101, 'schedule_no': 10,
          'schedule_kind': 'delivery', 'promised_date': '2026-11-01',
          'promised_qty': 1, 'plant_location_id': 900,
          'milestone_code': None, 'service_visit_no': None,
          'status': 'planned'},
}


def _ds(**kwargs):
    return _FakeDS(orders=ORDERS, lines=LINES, schedules=SCHEDULES, **kwargs)


def _create(**over):
    """草稿订单 10 下的一条合法 delivery 计划行。"""
    data = {
        'schedule_no': 10,
        'line_id': 100,
        'order_id': 10,
        'schedule_kind': 'delivery',
        'promised_date': '2026-11-01',
        'promised_qty': 3,
        'plant_location_id': 900,
        'status': 'planned',
    }
    data.update(over)
    return data


def _update(old, **over):
    data = dict(old)
    data.update(over)
    return data


def _rule(excinfo):
    return excinfo.value.rule


# ---------------- 单条规则 ----------------

def test_kind_not_enabled():
    """R-SCH-10：service 已声明但本波未启用。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(schedule_kind='service'))
    assert _rule(exc) == 'SCHEDULE_KIND_NOT_ENABLED'


def test_promised_date_required():
    """R-SCH-1：承诺日期必填。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(promised_date=None))
    assert _rule(exc) == 'SCHEDULE_DATE_REQUIRED'


def test_milestone_code_too_long():
    """R-SCH-6：里程碑码长度上限 64。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(milestone_code='M' * 65))
    assert _rule(exc) == 'MILESTONE_CODE_TOO_LONG'


def test_order_mismatch():
    """R-SCH-0：计划行订单必须与订单行一致。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(order_id=11))
    assert _rule(exc) == 'SCHEDULE_ORDER_MISMATCH'


def test_locked_on_create_after_draft():
    """R-SCH-5：订单离开草稿后禁止新增。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(line_id=101, order_id=11))
    assert _rule(exc) == 'SCHEDULE_LOCKED'


def test_locked_on_update_of_frozen_field():
    """R-SCH-5：非草稿订单只允许改期 / 改量 / 改发货点。"""
    old = SCHEDULES[201]
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _update(old, schedule_no=99), old_data=old, is_create=False)
    assert _rule(exc) == 'SCHEDULE_LOCKED'


def test_update_promised_date_after_draft_allowed():
    """R-SCH-5：非草稿订单仍可改承诺日期。"""
    old = SCHEDULES[201]
    SalesOrderGuardService(_ds()).validate_schedule_write(
        _update(old, promised_date='2026-12-01'), old_data=old,
        is_create=False)


def test_billing_qty_not_allowed(monkeypatch):
    """R-SCH-2：billing 不承诺数量（先放开 kind 门控才能覆盖该分支）。"""
    monkeypatch.setattr(guard_module, 'SCHEDULE_KINDS_ENABLED',
                        ('delivery', 'billing', 'service'))
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(schedule_kind='billing', promised_qty=3))
    assert _rule(exc) == 'BILLING_QTY_NOT_ALLOWED'


def test_delivery_qty_invalid():
    """R-SCH-3：delivery 承诺量必填且 > 0。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(promised_qty=None))
    assert _rule(exc) == 'DELIVERY_QTY_INVALID'


def test_delivery_qty_exceeded():
    """R-SCH-3：同一行 delivery 合计不得超过订单行数量。"""
    ds = _ds(delivery_sum=9)
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(ds).validate_schedule_write(_create())
    assert _rule(exc) == 'DELIVERY_QTY_EXCEEDED'


def test_plant_required():
    """R-SCH-7：订单行与计划行均无发货点时拒绝。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(plant_location_id=None))
    assert _rule(exc) == 'SCHEDULE_PLANT_REQUIRED'


def test_plant_inherited_from_line():
    """R-SCH-7：订单行已指定发货点时，计划行可留空。"""
    SalesOrderGuardService(_ds()).validate_schedule_write(
        _create(line_id=102, order_id=10, plant_location_id=None))


def test_service_visit_no_required(monkeypatch):
    """R-SCH-4：service 计划行必须填写服务次数。"""
    monkeypatch.setattr(guard_module, 'SCHEDULE_KINDS_ENABLED',
                        ('delivery', 'billing', 'service'))
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(schedule_kind='service', promised_qty=None,
                    service_visit_no=None))
    assert _rule(exc) == 'SERVICE_VISIT_NO_REQUIRED'


# ---------------- 删除（R-SCH-8） ----------------

def test_delete_forbidden_when_order_not_draft():
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_delete(201)
    assert _rule(exc) == 'SCHEDULE_DELETE_FORBIDDEN'


def test_delete_forbidden_when_derivation_refs():
    ds = _ds(edges={('sales_order_schedule', '200')})
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(ds).validate_schedule_delete(200)
    assert _rule(exc) == 'SCHEDULE_DELETE_FORBIDDEN'


def test_delete_allowed():
    SalesOrderGuardService(_ds()).validate_schedule_delete(200)


# ---------------- 状态流转（R-SCH-9） ----------------

def test_status_planned_to_confirmed():
    old = SCHEDULES[200]
    SalesOrderGuardService(_ds()).validate_schedule_write(
        _update(old, status='confirmed'), old_data=old, is_create=False)


def test_status_planned_to_completed_invalid():
    """跳过 confirmed 直接完成，非法。"""
    old = SCHEDULES[200]
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _update(old, status='completed'), old_data=old, is_create=False)
    assert _rule(exc) == 'SCHEDULE_STATUS_INVALID'


def test_status_terminal_immutable():
    """completed / cancelled 为终态，不可回退。"""
    old = _update(SCHEDULES[200], status='completed')
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _update(old, status='planned'), old_data=old, is_create=False)
    assert _rule(exc) == 'SCHEDULE_STATUS_INVALID'


def test_status_confirmed_to_cancelled():
    old = _update(SCHEDULES[200], status='confirmed')
    SalesOrderGuardService(_ds()).validate_schedule_write(
        _update(old, status='cancelled'), old_data=old, is_create=False)


def test_status_unknown_value():
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _create(status='unknown'))
    assert _rule(exc) == 'SCHEDULE_STATUS_INVALID'
