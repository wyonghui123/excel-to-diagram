# -*- coding: utf-8 -*-
"""采购发票金额（W2 / D-VI-27）——A1-A5

依据: docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §22.2 / §22.3 / §22.13
      docs/superpowers/plans/2026-11-12-vendor-invoice-amount-w2-execution-plan.md

口径: 算术继承 SalesOrderAmountService（R-VI-33），本文件只验证 VI 薄子类的
      含税倒算 / 缺税率拦截 / 供应商总额兜底 / rounding_diff。
"""

from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.sales_order_amount_service import SalesOrderAmountError
from meta.services.vendor_invoice_amount_service import VendorInvoiceAmountService


class _FakeDS:
    """按 SQL 特征片段分流；execute 只记录，不落库。"""

    def __init__(self):
        self.queries = []
        self.executed = []

    def query(self, sql, params=None):
        self.queries.append((sql, params))
        normalized = ' '.join(sql.split())
        if 'FROM vendor_invoice_lines WHERE id' in normalized:
            return [{'id': 5, 'order_id': 7, 'qty': 10, 'unit_price': 100,
                     'price_includes_tax': 0, 'tax_code_id': 3,
                     'tax_rate_percent': None}]
        if 'FROM vendor_invoices WHERE id' in normalized:
            return [{'id': 7, 'document_type_id': 2,
                     'order_date': '2026-11-12', 'currency_id': 1,
                     'supplier_gross_amount': 1130.05}]
        if 'FROM currencies WHERE id' in normalized:
            return [{'decimal_places': 2}]
        if 'FROM type_definitions WHERE id' in normalized:
            return [{'document_category': 'invoice'}]
        if 'FROM tax_rates' in normalized:
            return [{'rate_percent': 13}]
        if 'FROM tax_codes WHERE id' in normalized:
            return [{'rounding': 'round'}]
        if 'FROM vendor_invoice_lines WHERE invoice_id' in normalized:
            return [{'net_amount': 1000.0, 'tax_amount': 130.0,
                     'gross_amount': 1130.0}]
        return []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


def _svc(ds=None):
    return VendorInvoiceAmountService(ds or _FakeDS())


# ------------------------------------------------------------------ A1 / A2 / A4

def test_a1_path_a_net_tax_gross():
    """A1: 不含税 10×100 @13% → 1000 / 130 / 1130。"""
    values = _svc()._line_amounts(
        qty=Decimal('10'), unit_price=Decimal('100'),
        price_includes_tax=0, tax_rate_percent=Decimal('13'),
        tax_rounding='round', decimals=2)
    assert values['net_amount'] == Decimal('1000.00')
    assert values['tax_amount'] == Decimal('130.00')
    assert values['gross_amount'] == Decimal('1130.00')


def test_a2_path_b_back_calculates_from_tax_inclusive_price():
    """A2: 含税 3×113 @13% → 300 / 39 / 339。"""
    values = _svc()._line_amounts(
        qty=Decimal('3'), unit_price=Decimal('113'),
        price_includes_tax=1, tax_rate_percent=Decimal('13'),
        decimals=2)
    assert values['net_amount'] == Decimal('300.00')
    assert values['tax_amount'] == Decimal('39.00')
    assert values['gross_amount'] == Decimal('339.00')


def test_a3_tax_inclusive_line_without_rate_is_rejected():
    """A3: 含税价行缺税率 → VI_TAX_RATE_REQUIRED。"""
    with pytest.raises(SalesOrderAmountError) as exc:
        _svc()._line_amounts(
            qty=Decimal('1'), unit_price=Decimal('113'),
            price_includes_tax=1, tax_rate_percent=None, decimals=2)
    assert exc.value.rule == 'VI_TAX_RATE_REQUIRED'
    assert exc.value.field_name == 'tax_rate_percent'


def test_a4_zero_decimal_currency_keeps_identity():
    """A4: 0 位币种 gross 取整，net + tax 恒等于 gross。"""
    values = _svc()._line_amounts(
        qty=Decimal('1'), unit_price=Decimal('1001.4'),
        price_includes_tax=1, tax_rate_percent=Decimal('13'), decimals=0)
    assert values['gross_amount'] == Decimal('1001')
    assert values['net_amount'] + values['tax_amount'] == Decimal('1001')


# ------------------------------------------------------------------ A5 / 头

def test_a5_supplier_gross_wins_and_rounding_diff_is_revealed():
    """A5: 供应商票面 1130.05 vs 行合计 1130.00 → rounding_diff=0.05。"""
    values = _svc()._header_amounts(
        sum_net=Decimal('1000'), sum_tax=Decimal('130'),
        sum_gross=Decimal('1130'), supplier_gross=Decimal('1130.05'),
        decimals=2)
    assert values['net_amount'] == Decimal('1000.00')
    assert values['tax_amount'] == Decimal('130.00')
    assert values['gross_amount'] == Decimal('1130.05')
    assert values['rounding_diff'] == Decimal('0.05')


def test_header_without_supplier_gross_uses_line_totals():
    values = _svc()._header_amounts(
        sum_net=Decimal('1000'), sum_tax=Decimal('130'),
        sum_gross=Decimal('1130'), supplier_gross=None, decimals=2)
    assert values['gross_amount'] == Decimal('1130.00')
    assert values['rounding_diff'] == Decimal('0.00')


# ------------------------------------------------------------------ 端到端

def test_recompute_line_writes_vi_table_and_snapshot_rate():
    ds = _FakeDS()
    values = _svc(ds).recompute_line(5)
    assert values['net_amount'] == Decimal('1000.00')
    assert values['tax_rate_percent'] == Decimal('13')
    update_sql, params = ds.executed[-1]
    assert 'UPDATE vendor_invoice_lines' in update_sql
    assert all(isinstance(p, float) for p in params[:-1])


def test_recompute_order_writes_gross_and_rounding_diff():
    ds = _FakeDS()
    values = _svc(ds).recompute_order(7)
    assert values['gross_amount'] == Decimal('1130.05')
    assert values['rounding_diff'] == Decimal('0.05')
    update_sql, params = ds.executed[-1]
    assert 'UPDATE vendor_invoices' in update_sql
    assert abs(params[3] - 0.05) < 1e-9