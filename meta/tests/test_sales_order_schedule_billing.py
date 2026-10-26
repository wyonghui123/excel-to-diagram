# -*- coding: utf-8 -*-
"""销售订单计划行 billing 守卫测试（R-SCH-11 ~ R-SCH-15）

依据: meta/schemas/sales_order_schedule.yaml
      docs/superpowers/specs/2026-10-26-sales-order-billing-and-header-discount-spec.md §3.2
"""

import pytest

pytestmark = pytest.mark.unit

from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)


class _FakeDS:
    """按 SQL 特征片段分流，只覆盖计划行守卫用到的查询。"""

    def __init__(self, orders=None, lines=None, schedules=None,
                 billing_sum=0.0, delivery_sum=0.0, raise_on_query=False):
        self.orders = orders or {}
        self.lines = lines or {}
        self.schedules = schedules or {}
        self.billing_sum = billing_sum
        self.delivery_sum = delivery_sum
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError('db down')
        p = list(params or [])

        if 'COALESCE(SUM(billing_percent)' in sql:
            return [{'pct': self.billing_sum}]
        if 'COALESCE(SUM(promised_qty)' in sql:
            return [{'qty': self.delivery_sum}]
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
    # 订单 10 的订单行（草稿）
    100: {'id': 100, 'order_id': 10, 'qty': 10, 'uom_id': 8,
          'plant_location_id': None},
    # 订单 11 的订单行（已提交）
    101: {'id': 101, 'order_id': 11, 'qty': 5, 'uom_id': 8,
          'plant_location_id': 900},
}

SCHEDULES = {
    # 已提交订单下的 billing 计划行（用于非草稿冻结场景）
    300: {'id': 300, 'order_id': 11, 'line_id': 101, 'schedule_no': 20,
          'schedule_kind': 'billing', 'promised_date': '2026-11-30',
          'promised_qty': None, 'billing_percent': 30,
          'plant_location_id': None, 'milestone_code': None,
          'service_visit_no': None, 'status': 'planned'},
}


def _ds(**kwargs):
    return _FakeDS(orders=ORDERS, lines=LINES, schedules=SCHEDULES, **kwargs)


def _billing(**over):
    """草稿订单 10 下的一条合法 billing 计划行。"""
    data = {
        'schedule_no': 20,
        'line_id': 100,
        'order_id': 10,
        'schedule_kind': 'billing',
        'promised_date': '2026-11-30',
        'billing_percent': 30,
        'promised_qty': None,
        'plant_location_id': None,
        'service_visit_no': None,
        'milestone_code': None,
        'status': 'planned',
    }
    data.update(over)
    return data


def _rule(excinfo):
    return excinfo.value.rule


# ---------------- 合法路径 ----------------

def test_billing_create_allowed():
    """billing 已启用：带收款比例与收款日即可创建。"""
    SalesOrderGuardService(_ds()).validate_schedule_write(_billing())


def test_billing_percent_at_upper_bound_allowed():
    """R-SCH-11：100 是合法上界。"""
    SalesOrderGuardService(_ds()).validate_schedule_write(
        _billing(billing_percent=100))


# ---------------- R-SCH-11 比例 ----------------

def test_billing_percent_required():
    """R-SCH-11：收款比例必填。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _billing(billing_percent=None))
    assert _rule(exc) == 'BILLING_PERCENT_REQUIRED'


def test_billing_percent_range():
    """R-SCH-11：0 与 101 都越界。"""
    for bad in (0, 101):
        with pytest.raises(SalesOrderGuardError) as exc:
            SalesOrderGuardService(_ds()).validate_schedule_write(
                _billing(billing_percent=bad))
        assert _rule(exc) == 'BILLING_PERCENT_RANGE'


# ---------------- R-SCH-12 禁止字段 ----------------

def test_billing_plant_location_not_allowed():
    """R-SCH-12：billing 不得填写发货点。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _billing(plant_location_id=900))
    assert _rule(exc) == 'BILLING_FIELD_NOT_ALLOWED'


def test_billing_service_visit_no_not_allowed():
    """R-SCH-12：billing 不得填写服务次数。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _billing(service_visit_no=1))
    assert _rule(exc) == 'BILLING_FIELD_NOT_ALLOWED'


# ---------------- R-SCH-13 合计上限 ----------------

def test_billing_percent_sum_exceeded():
    """R-SCH-13：本行已计划 80 + 本次 30 = 110 > 100。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds(billing_sum=80)).validate_schedule_write(
            _billing(billing_percent=30))
    assert _rule(exc) == 'BILLING_PERCENT_SUM_EXCEEDED'


def test_billing_percent_sum_exactly_100_allowed():
    """R-SCH-13：本行已计划 70 + 本次 30 = 100，允许。"""
    SalesOrderGuardService(_ds(billing_sum=70)).validate_schedule_write(
        _billing(billing_percent=30))


# ---------------- R-SCH-14 收款日 ----------------

def test_billing_date_required():
    """R-SCH-14：billing 的承诺日期（收款日）必填。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _billing(promised_date=None))
    assert _rule(exc) == 'BILLING_DATE_REQUIRED'


# ---------------- R-SCH-15 非草稿冻结 ----------------

def test_billing_percent_locked_after_draft():
    """R-SCH-15：非草稿订单修改收款比例被拒。"""
    old = SCHEDULES[300]
    data = dict(old)
    data['billing_percent'] = 40
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            data, old_data=old, is_create=False)
    assert _rule(exc) == 'BILLING_PERCENT_LOCKED'


def test_billing_date_editable_after_draft():
    """R-SCH-5 收窄：非草稿 billing 仍可改收款日。"""
    old = SCHEDULES[300]
    data = dict(old)
    data['promised_date'] = '2026-12-15'
    SalesOrderGuardService(_ds()).validate_schedule_write(
        data, old_data=old, is_create=False)


# ---------------- R-SCH-2 保持不动 ----------------

def test_billing_qty_not_allowed():
    """R-SCH-2：billing 仍不得携带承诺数量。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds()).validate_schedule_write(
            _billing(promised_qty=3))
    assert _rule(exc) == 'BILLING_QTY_NOT_ALLOWED'


# ---------------- V-A3 三期 60 / 40 / 10 ----------------

def test_billing_percent_sum_60_plus_40_allowed():
    """V-A3：已排 60 + 本次 40 = 100，第二期通过。"""
    SalesOrderGuardService(_ds(billing_sum=60)).validate_schedule_write(
        _billing(billing_percent=40))


def test_billing_percent_sum_60_plus_50_rejected():
    """V-A3：第三期再排 50 会让合计 150 > 100，被拒。"""
    with pytest.raises(SalesOrderGuardError) as exc:
        SalesOrderGuardService(_ds(billing_sum=60)).validate_schedule_write(
            _billing(billing_percent=50))
    assert _rule(exc) == 'BILLING_PERCENT_SUM_EXCEEDED'


# ---------------- V-A1 同一行 delivery + billing + service ----------------

def test_same_line_delivery_billing_enabled_service_still_blocked():
    """V-A1：同一订单行可同时排 delivery 与 billing，service 仍未启用。

    delivery：promised_qty=3（行 qty=10）、显式发货点；
    billing：收款比例 30、收款日；
    service：kind 门控先于服务次数字段校验，直接 SCHEDULE_KIND_NOT_ENABLED。
    """
    guard = SalesOrderGuardService(_ds())
    line_id = 100
    order_id = 10

    delivery = {
        'schedule_no': 20,
        'line_id': line_id,
        'order_id': order_id,
        'schedule_kind': 'delivery',
        'promised_date': '2026-11-30',
        'promised_qty': 3,
        'billing_percent': None,
        'plant_location_id': 900,
        'service_visit_no': None,
        'milestone_code': None,
        'status': 'planned',
    }
    guard.validate_schedule_write(delivery)

    guard.validate_schedule_write(_billing())

    service = {
        'schedule_no': 21,
        'line_id': line_id,
        'order_id': order_id,
        'schedule_kind': 'service',
        'promised_date': '2026-11-30',
        'promised_qty': None,
        'billing_percent': None,
        'plant_location_id': None,
        'service_visit_no': 1,
        'milestone_code': None,
        'status': 'planned',
    }
    with pytest.raises(SalesOrderGuardError) as exc:
        guard.validate_schedule_write(service)
    assert _rule(exc) == 'SCHEDULE_KIND_NOT_ENABLED'
