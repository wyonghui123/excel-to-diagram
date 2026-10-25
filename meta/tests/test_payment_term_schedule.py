# -*- coding: utf-8 -*-
"""付款条件到期日推算测试（基准日口径 / 截止日顺延 / 固定日 / 折扣 / 分期合计）

依据: meta/schemas/payment_term_line.yaml 头注释「到期日计算口径」
"""

import pytest

pytestmark = pytest.mark.unit

from datetime import date

from meta.services.payment_term_guard_service import PaymentTermGuardError
from meta.services.payment_term_schedule_service import (
    add_months,
    compute_discount_date,
    compute_due_date,
    compute_schedule,
    resolve_base_date,
)

NET30 = {'basis_date_rule': 'invoice_date', 'cutoff_day': None}


def _line(seq=1, percentage=100, months=0, fixed=None, days=0,
          discount_percent=None, discount_days=None):
    return {'seq': seq, 'percentage': percentage, 'offset_months': months,
            'fixed_day_of_month': fixed, 'offset_days': days,
            'discount_percent': discount_percent, 'discount_days': discount_days}


# ─────────────────────────────────────────────────────────────────────────────
# 基准日口径
# ─────────────────────────────────────────────────────────────────────────────

class TestBaseDate:
    def test_invoice_date_is_trigger(self):
        assert resolve_base_date(NET30, '2026-03-15') == date(2026, 3, 15)

    def test_month_end_rule(self):
        term = {'basis_date_rule': 'month_end'}
        assert resolve_base_date(term, date(2026, 2, 10)) == date(2026, 2, 28)

    def test_month_end_rule_leap_year(self):
        term = {'basis_date_rule': 'month_end'}
        assert resolve_base_date(term, date(2028, 2, 3)) == date(2028, 2, 29)

    def test_cutoff_rolls_over(self):
        term = {'basis_date_rule': 'invoice_date', 'cutoff_day': 25}
        assert resolve_base_date(term, '2026-03-28') == date(2026, 4, 28)

    def test_cutoff_keeps_same_month_within_day(self):
        term = {'basis_date_rule': 'invoice_date', 'cutoff_day': 25}
        assert resolve_base_date(term, '2026-03-25') == date(2026, 3, 25)

    def test_unknown_rule_rejected(self):
        with pytest.raises(PaymentTermGuardError) as e:
            resolve_base_date({'basis_date_rule': 'ship_date'}, '2026-03-15')
        assert e.value.rule == 'basis_rule_unknown'


# ─────────────────────────────────────────────────────────────────────────────
# 月偏移 / 固定日 / 天偏移
# ─────────────────────────────────────────────────────────────────────────────

class TestDueDate:
    def test_net_30(self):
        assert compute_due_date(date(2026, 3, 15), _line(days=30)) == date(2026, 4, 14)

    def test_add_months_clamps_to_month_end(self):
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_add_months_leap_year(self):
        assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)

    def test_fixed_day_of_month(self):
        line = _line(months=1, fixed=15)
        assert compute_due_date(date(2026, 1, 20), line) == date(2026, 2, 15)

    def test_fixed_day_clamped_to_month_end(self):
        line = _line(months=1, fixed=31)
        assert compute_due_date(date(2026, 1, 10), line) == date(2026, 2, 28)

    def test_month_offset_then_days(self):
        line = _line(months=2, days=10)
        assert compute_due_date(date(2026, 1, 15), line) == date(2026, 3, 25)


# ─────────────────────────────────────────────────────────────────────────────
# 折扣
# ─────────────────────────────────────────────────────────────────────────────

class TestDiscount:
    def test_discount_from_base_ignoring_offsets(self):
        line = _line(months=1, days=0, discount_percent=2, discount_days=10)
        assert compute_discount_date(date(2026, 3, 10), line) == date(2026, 3, 20)
        assert compute_due_date(date(2026, 3, 10), line) == date(2026, 4, 10)

    def test_no_discount_returns_none(self):
        assert compute_discount_date(date(2026, 3, 10), _line()) is None


# ─────────────────────────────────────────────────────────────────────────────
# 整表推算
# ─────────────────────────────────────────────────────────────────────────────

class TestSchedule:
    def test_two_installments_sorted(self):
        lines = [_line(seq=2, percentage=50, days=60),
                 _line(seq=1, percentage=50, days=0)]
        plan = compute_schedule(NET30, lines, '2026-03-10')
        assert [p['seq'] for p in plan] == [1, 2]
        assert [p['due_date'] for p in plan] == [date(2026, 3, 10), date(2026, 5, 9)]
        assert [p['percentage'] for p in plan] == [50.0, 50.0]

    def test_cutoff_applies_to_all_installments(self):
        term = {'basis_date_rule': 'invoice_date', 'cutoff_day': 25}
        plan = compute_schedule(term, [_line(days=30)], '2026-03-28')
        assert plan[0]['due_date'] == date(2026, 5, 28)

    def test_discount_present_in_schedule(self):
        plan = compute_schedule(NET30, [_line(days=30, discount_percent=2,
                                              discount_days=10)], '2026-03-10')
        assert plan[0]['discount_due_date'] == date(2026, 3, 20)
        assert plan[0]['discount_percent'] == 2

    def test_rejects_partial_total(self):
        with pytest.raises(PaymentTermGuardError) as e:
            compute_schedule(NET30, [_line(percentage=60, days=30)], '2026-03-10')
        assert e.value.rule == 'percentage_not_100'

    def test_rejects_no_lines(self):
        with pytest.raises(PaymentTermGuardError) as e:
            compute_schedule(NET30, [], '2026-03-10')
        assert e.value.rule == 'no_lines'
