# -*- coding: utf-8 -*-
"""W6 采购发票费用行 + 直录税额（Spec §22.2 / §22.6 / §22.13 A11、A12）。

覆盖：
  A11 运费行 50 @6% + 物料 1000 → net 1050 / tax 133 / gross 1183；
      line_direct 直录税额在容差内通过，超容差 tax_mismatch=True。
  A12 费用行合计 50 vs PO 头附加费 40 → 差 10 > 0 → 头 exception
      VI_FREIGHT_OVER_TOLERANCE；费用行不写 doc_flow 边。
"""

from decimal import Decimal

import pytest

from meta.services.vendor_invoice_amount_service import VendorInvoiceAmountService
from meta.services.vendor_invoice_match_service import (
    RULE_RECEIPT_AP,
    REASON_FREIGHT,
    REASON_TAX,
    VendorInvoiceError,
    VendorInvoiceMatchService,
)
from meta.tests.factories import _vendor_invoice_helpers as H

TAX_CODE_13 = 6601
TAX_CODE_6 = 6602


@pytest.fixture()
def ds(tmp_path):
    env = H.make_env(tmp_path)
    H.seed_type_definitions(env)
    H.seed_charge_params(env)
    H.seed_tax_rate(env, tax_code_id=TAX_CODE_13, rate_percent=13)
    H.seed_tax_rate(env, tax_code_id=TAX_CODE_6, rate_percent=6)
    return env


@pytest.fixture()
def service(ds):
    return VendorInvoiceMatchService(ds, ds)


def _line(ds, line_id):
    return ds.query('SELECT * FROM vendor_invoice_lines WHERE id = ?', [line_id])[0]


def _charge_invoice(ds, *, surcharge_amount=0.0, material_tax=13.0,
                    freight_tax=3.0, freight_qty=1.0, invoice_no='VI-CHG-1',
                    material_unit_price=10.0, material_net=100.0,
                    freight_schedule_id=None):
    """物料行 + 运费行 50；头金额 = 行合计。"""
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=material_unit_price,
                          header_surcharge_amount=surcharge_amount)
    H.seed_receipt_line(ds, qty_received=10.0)
    net = material_net + 50.0
    tax = material_tax + freight_tax
    invoice_id = H.insert_invoice(
        ds, invoice_no=invoice_no, net_amount=net, tax_amount=tax,
        gross_amount=net + tax)
    material_line = H.insert_line(
        ds, invoice_id, line_no=1, qty=10.0, unit_price=material_unit_price,
        net_amount=material_net, tax_amount=material_tax,
        gross_amount=material_net + material_tax,
        receipt_line_id=H.RECEIPT_LINE_ID,
        po_unit_price=material_unit_price, tax_code_id=TAX_CODE_13,
        tax_rate_percent=13)
    freight_line = H.insert_line(
        ds, invoice_id, line_no=2, qty=freight_qty, unit_price=50.0,
        net_amount=50.0, tax_amount=freight_tax,
        gross_amount=50.0 + freight_tax,
        line_type_id=H.LINE_TYPE_FREIGHT_ID, tax_code_id=TAX_CODE_6,
        tax_rate_percent=6, schedule_id=freight_schedule_id)
    return invoice_id, material_line, freight_line


# ------------------------------------------------------------------ A11 金额

def test_a11_charge_line_amounts(ds):
    invoice_id, material_line, freight_line = _charge_invoice(
        ds, material_unit_price=100.0, material_net=1000.0,
        material_tax=130.0)

    svc = VendorInvoiceAmountService(ds)
    svc.recompute_line(material_line)
    svc.recompute_line(freight_line)
    values = svc.recompute_order(invoice_id)

    assert values['net_amount'] == Decimal('1050.00')
    assert values['tax_amount'] == Decimal('133.00')
    assert values['gross_amount'] == Decimal('1183.00')
    assert Decimal(str(_line(ds, material_line)['tax_amount'])) == Decimal('130.00')
    assert Decimal(str(_line(ds, freight_line)['tax_amount'])) == Decimal('3.00')


def test_a11_line_direct_tax_within_tolerance_has_no_mismatch(ds):
    _, material_line, freight_line = _charge_invoice(ds)
    svc = VendorInvoiceAmountService(ds)

    assert svc.recompute_line(material_line)['tax_mismatch'] is False
    assert svc.recompute_line(freight_line)['tax_mismatch'] is False


def test_line_direct_tax_over_tolerance_flags_mismatch(ds):
    _, _, freight_line = _charge_invoice(ds, freight_tax=10.0)
    svc = VendorInvoiceAmountService(ds)

    values = svc.recompute_line(freight_line)

    # 超容差仍采用直录税额（gross = net + tax），由匹配层置 exception
    assert values['tax_mismatch'] is True
    assert values['tax_amount'] == Decimal('10.00')
    assert values['gross_amount'] == Decimal('60.00')


# ------------------------------------------------------------------ 匹配层

def test_line_direct_tax_over_tolerance_is_line_exception(ds, service):
    # R-VI-40 收紧后费用对账不再「target=0 静默通过」，故给出等额附加费目标
    invoice_id, _, freight_line = _charge_invoice(
        ds, surcharge_amount=50.0, freight_tax=10.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert REASON_TAX in (result['match_exception_reason'] or '')
    line = _line(ds, freight_line)
    assert line['match_status'] == 'exception'
    assert line['match_exception_reason'] == REASON_TAX
    with pytest.raises(VendorInvoiceError) as exc:
        service.submit(invoice_id)
    assert exc.value.rule == 'VI_MATCH_EXCEPTION'


def test_a12_freight_over_po_surcharge_is_header_exception(ds, service):
    invoice_id, material_line, freight_line = _charge_invoice(
        ds, surcharge_amount=40.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert result['match_exception_reason'] == REASON_FREIGHT
    # 费用行自身不产生数量 / 价格差异
    line = _line(ds, freight_line)
    assert line['match_status'] == 'matched'
    assert float(line['qty_over_receipt'] or 0) == 0.0
    assert _line(ds, material_line)['match_status'] == 'matched'


def test_a12_charge_line_does_not_write_doc_flow_edges(ds, service):
    invoice_id, material_line, freight_line = _charge_invoice(
        ds, surcharge_amount=50.0)

    result = service.match(invoice_id)
    assert result['match_status'] == 'matched'
    service.submit(invoice_id)
    service.post(invoice_id)

    assert H.count_edges(ds, rule_id=RULE_RECEIPT_AP,
                         target_id=str(freight_line)) == 0
    assert H.count_edges(ds, rule_id=RULE_RECEIPT_AP,
                         target_id=str(material_line)) >= 1


def test_charge_line_cannot_attach_schedule_anchor(ds, service):
    invoice_id, _, _ = _charge_invoice(
        ds, freight_schedule_id=H.SCHEDULE_ID)

    with pytest.raises(VendorInvoiceError) as exc:
        service.match(invoice_id)

    assert exc.value.rule == 'VI_ANCHOR_CONFLICT'