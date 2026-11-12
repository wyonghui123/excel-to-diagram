# -*- coding: utf-8 -*-
"""开票计划期次生成测试（S8 Wave C / T37）。

依据: docs/specs/s8-customer-invoice-wave-c/spec.md §6.2
夹具: meta/tests/factories/_billing_plan_helpers.py（内存库，DDL 收口于工厂）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.services.billing_plan_service import (
    BillingPlanError,
    BillingPlanService,
)
from meta.tests.factories._billing_plan_helpers import (
    LINE_DELIVERY,
    LINE_FIXED,
    LINE_MILESTONE,
    LINE_TM,
    ORDER_ID,
    add_line,
    add_schedule,
    build_conn,
    list_schedules,
    make_ds,
)


def _service(conn):
    return BillingPlanService(make_ds(conn))


def test_generate_tm_three_periods():
    conn = build_conn()
    add_line(conn, LINE_TM, method='time_and_material', period_count=3,
             interval=1, anchor='2026-01-15')

    created = _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_TM)
    assert len(rows) == 3
    assert len(created) == 3
    assert [r['schedule_no'] for r in rows] == [1, 2, 3]
    assert [r['schedule_kind'] for r in rows] == ['billing'] * 3
    assert [r['promised_date'] for r in rows] == [
        '2026-01-15', '2026-02-15', '2026-03-15']
    assert rows[0]['billing_percent'] == pytest.approx(33.3333)
    assert rows[1]['billing_percent'] == pytest.approx(33.3333)
    assert rows[2]['billing_percent'] == pytest.approx(33.3334)
    assert sum(r['billing_percent'] for r in rows) == pytest.approx(100.0)
    for row in rows:
        assert row['status'] == 'planned'
        assert row['billing_status'] == 'none'
        assert row['promised_qty'] is None
        assert row['plant_location_id'] is None
        assert row['milestone_code'] is None
        assert row['billed_amount'] == 0


def test_generate_fixed_price_single_period():
    conn = build_conn(confirmed_date='2026-01-10')
    add_line(conn, LINE_FIXED, method='fixed_price')

    _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_FIXED)
    assert len(rows) == 1
    assert rows[0]['billing_percent'] == pytest.approx(100.0)
    # 锚点缺省取订单 confirmed_date
    assert rows[0]['promised_date'] == '2026-01-10'


def test_generate_milestone_skipped():
    conn = build_conn()
    add_line(conn, LINE_MILESTONE, method='milestone')

    assert _service(conn).generate_for_order(ORDER_ID) == []
    assert list_schedules(conn, LINE_MILESTONE) == []


def test_generate_anchor_interval_dates():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, interval=2,
             anchor='2026-01-31')

    _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_TM)
    assert [r['promised_date'] for r in rows] == [
        '2026-01-31', '2026-03-31', '2026-05-31']


def test_generate_lead_days_positive():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, interval=1,
             anchor='2026-01-15', lead_days=5)

    _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_TM)
    assert [r['promised_date'] for r in rows] == [
        '2026-01-20', '2026-02-20', '2026-03-20']


def test_generate_lead_days_negative():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, interval=1,
             anchor='2026-01-15', lead_days=-5)

    _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_TM)
    assert [r['promised_date'] for r in rows] == [
        '2026-01-10', '2026-02-10', '2026-03-10']


def test_generate_daily_proration():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, interval=1,
             anchor='2026-01-01', proration='daily',
             service_start='2026-01-15', service_end='2026-03-15')

    _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_TM)
    # 17 / 28 / 15 天，合计 60 天
    assert rows[0]['billing_percent'] == pytest.approx(28.3333)
    assert rows[1]['billing_percent'] == pytest.approx(46.6667)
    assert rows[2]['billing_percent'] == pytest.approx(25.0)
    assert sum(r['billing_percent'] for r in rows) == pytest.approx(100.0)


def test_generate_daily_without_service_dates_falls_back():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, interval=1,
             anchor='2026-01-15', proration='daily')

    _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_TM)
    assert [round(r['billing_percent'], 4) for r in rows] == [
        33.3333, 33.3333, 33.3334]


def test_generate_daily_zero_overlap_rejected():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, interval=1,
             anchor='2026-01-01', proration='daily',
             service_start='2027-01-01', service_end='2027-02-01')

    with pytest.raises(BillingPlanError) as exc:
        _service(conn).generate_for_order(ORDER_ID)
    assert exc.value.rule == 'ORDER_BILLING_PLAN_INVALID'
    assert list_schedules(conn, LINE_TM) == []


def test_generate_idempotent_existing_schedules():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, interval=1,
             anchor='2026-01-15')
    add_schedule(conn, LINE_TM, schedule_no=1, billing_percent=100.0,
                 promised_date='2026-01-15')

    created = _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_TM)
    assert created == []
    assert len(rows) == 1
    assert rows[0]['billing_percent'] == pytest.approx(100.0)


def test_generate_skips_when_billed_amount_positive():
    conn = build_conn()
    add_line(conn, LINE_TM, period_count=3, interval=1,
             anchor='2026-01-15')
    add_schedule(conn, LINE_TM, schedule_no=1, billing_percent=100.0,
                 billed_amount=400.0, promised_date='2026-01-15')

    created = _service(conn).generate_for_order(ORDER_ID)

    rows = list_schedules(conn, LINE_TM)
    assert created == []
    assert len(rows) == 1
    assert rows[0]['billed_amount'] == pytest.approx(400.0)


def test_generate_returns_empty_without_plan_lines():
    conn = build_conn()
    add_line(conn, LINE_DELIVERY, relevance='delivery')

    assert _service(conn).generate_for_order(ORDER_ID) == []
    assert list_schedules(conn, LINE_DELIVERY) == []