# -*- coding: utf-8 -*-
"""W10-1 三单匹配补强（Spec §24.7 测试矩阵 #1 ~ #13）。

覆盖 R-VI-38 ~ R-VI-47：
  源单状态白名单 / 费用对账（多 PO、折扣负值、费用余量、无锚点）/
  UOM 一致性 / 多异常 JSON 数组 / no_receipt 放行 / PO 税额比对 / 容差方向。

#14（默认参数回归 = 既有 25 例 match 测试）由 test_vendor_invoice_match.py 承担。
"""

import pytest

from meta.services.vendor_invoice_match_service import (
    ERR_CHARGE_MULTI_PO,
    ERR_SOURCE_STATUS,
    ERR_UOM,
    REASON_CHARGE_EXHAUSTED,
    REASON_CHARGE_UNANCHORED,
    REASON_FREIGHT,
    REASON_NO_RECEIPT,
    REASON_PO_TAX,
    REASON_PRICE,
    REASON_PRICE_UNDER,
    REASON_QTY_RECEIPT,
    VendorInvoiceError,
    VendorInvoiceMatchService,
    parse_reasons,
)
from meta.tests.factories import _vendor_invoice_helpers as H

PO2_ID = 7002
PO2_LINE_ID = 7102
PO2_SCHEDULE_ID = 7202
PO2_RECEIPT_ID = 7302
PO2_RECEIPT_LINE_ID = 7402


@pytest.fixture()
def ds(tmp_path):
    env = H.make_env(tmp_path)  # 内含 seed_params（零容差基线）
    H.seed_type_definitions(env)
    H.seed_charge_params(env)
    return env


@pytest.fixture()
def service(ds):
    return VendorInvoiceMatchService(ds, ds)


def _goods_charge_invoice(ds, *, invoice_no='VI-GAP-1', match_mode='gr_based',
                          goods_qty=10.0, goods_unit_price=10.0,
                          goods_net=100.0, charge_net=30.0,
                          charge_line_type_id=H.LINE_TYPE_FREIGHT_ID):
    """物料行 + 费用行（费用 qty=1，单价 = 净额），头金额 = 行合计。"""
    net = goods_net + charge_net
    invoice_id = H.insert_invoice(
        ds, invoice_no=invoice_no, match_mode=match_mode,
        net_amount=net, tax_amount=0.0, gross_amount=net)
    goods_line = H.insert_line(
        ds, invoice_id, line_no=1, qty=goods_qty, unit_price=goods_unit_price,
        net_amount=goods_net, tax_amount=0.0, gross_amount=goods_net,
        receipt_line_id=H.RECEIPT_LINE_ID, po_unit_price=goods_unit_price)
    charge_line = H.insert_line(
        ds, invoice_id, line_no=2, qty=1.0, unit_price=charge_net,
        net_amount=charge_net, tax_amount=0.0, gross_amount=charge_net,
        line_type_id=charge_line_type_id)
    return invoice_id, goods_line, charge_line


def _seed_second_po(ds, *, surcharge=0.0):
    H.seed_purchase_order(
        ds, po_id=PO2_ID, order_no='PO-0002', po_line_id=PO2_LINE_ID,
        schedule_id=PO2_SCHEDULE_ID, promised_qty=10.0, unit_price=10.0,
        header_surcharge_amount=surcharge)
    H.seed_receipt_line(
        ds, receipt_id=PO2_RECEIPT_ID, receipt_line_id=PO2_RECEIPT_LINE_ID,
        schedule_id=PO2_SCHEDULE_ID, order_line_id=PO2_LINE_ID, qty_received=10.0)


def _two_po_invoice(ds, *, invoice_no, charge_net):
    net = 200.0 + charge_net
    invoice_id = H.insert_invoice(
        ds, invoice_no=invoice_no, net_amount=net, tax_amount=0.0,
        gross_amount=net)
    H.insert_line(ds, invoice_id, line_no=1, qty=10.0, unit_price=10.0,
                  net_amount=100.0, tax_amount=0.0, gross_amount=100.0,
                  receipt_line_id=H.RECEIPT_LINE_ID, po_unit_price=10.0)
    H.insert_line(ds, invoice_id, line_no=2, qty=10.0, unit_price=10.0,
                  net_amount=100.0, tax_amount=0.0, gross_amount=100.0,
                  receipt_line_id=PO2_RECEIPT_LINE_ID, po_unit_price=10.0)
    H.insert_line(ds, invoice_id, line_no=3, qty=1.0, unit_price=charge_net,
                  net_amount=charge_net, tax_amount=0.0,
                  gross_amount=charge_net,
                  line_type_id=H.LINE_TYPE_FREIGHT_ID)
    return invoice_id


# ---------------------------------------------------------------- 费用对账
# #1 折扣负值参与目标：50 + (-20) = 30
def test_charge_total_matches_surcharge_plus_discount(ds, service):
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0,
                          header_surcharge_amount=50.0,
                          header_discount_amount=-20.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id, _, _ = _goods_charge_invoice(ds, charge_net=30.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'matched'
    assert result['match_exception_reason'] is None


# #2 费用合计与目标偏差超容差 → 头级 VI_FREIGHT_OVER_TOLERANCE
def test_charge_total_over_target_is_header_exception(ds, service):
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0,
                          header_surcharge_amount=50.0,
                          header_discount_amount=-20.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id, _, _ = _goods_charge_invoice(ds, charge_net=50.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert result['match_exception_reason'] == REASON_FREIGHT


# #3 多 PO 且任一 PO 头费用非 0 → 硬错（需拆票）
def test_multi_po_charge_line_rejected_when_any_header_fee(ds, service):
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0,
                          header_surcharge_amount=50.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    _seed_second_po(ds)
    invoice_id = _two_po_invoice(ds, invoice_no='VI-GAP-3', charge_net=30.0)

    with pytest.raises(VendorInvoiceError) as exc:
        service.match(invoice_id)

    assert exc.value.rule == ERR_CHARGE_MULTI_PO


# #4 多 PO 但各头费用全 0 且费用合计 0 → 放行
def test_multi_po_charge_line_ok_when_all_header_fees_zero(ds, service):
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    _seed_second_po(ds)
    invoice_id = _two_po_invoice(ds, invoice_no='VI-GAP-4', charge_net=0.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'matched'
    assert result['match_exception_reason'] is None


# #5 纯费用发票（无 PO 锚点）→ 行例外 VI_CHARGE_UNANCHORED
def test_pure_charge_invoice_without_po_is_exception(ds, service):
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-GAP-5', net_amount=100.0, tax_amount=0.0,
        gross_amount=100.0)
    H.insert_line(ds, invoice_id, qty=1.0, unit_price=100.0,
                  net_amount=100.0, tax_amount=0.0, gross_amount=100.0,
                  line_type_id=H.LINE_TYPE_FREIGHT_ID)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert result['match_exception_reason'] == REASON_CHARGE_UNANCHORED
    line = H.get_lines(ds, invoice_id)[0]
    assert line['match_status'] == 'exception'
    assert line['match_exception_reason'] == REASON_CHARGE_UNANCHORED


# #6 同一 PO 第二张发票重复报销同额附加费 → VI_CHARGE_EXHAUSTED
def test_second_invoice_repeating_charge_is_exhausted(ds, service):
    H.seed_purchase_order(ds, promised_qty=20.0, unit_price=10.0,
                          header_surcharge_amount=50.0)
    H.seed_receipt_line(ds, qty_received=20.0)
    first_id, _, _ = _goods_charge_invoice(
        ds, invoice_no='VI-GAP-6A', charge_net=50.0)
    service.submit(first_id)
    service.post(first_id)

    second_id, _, _ = _goods_charge_invoice(
        ds, invoice_no='VI-GAP-6B', charge_net=50.0)
    result = service.match(second_id)

    assert result['match_status'] == 'exception'
    assert REASON_CHARGE_EXHAUSTED in parse_reasons(
        result['match_exception_reason'])


# ---------------------------------------------------------------- 源单状态
# #7 PO closed 仍有余量 → VI_SOURCE_STATUS_INVALID
def test_closed_po_rejected(ds, service):
    H.seed_purchase_order(ds, status='closed')
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-GAP-7', match_mode='po_based', net_amount=100.0,
        tax_amount=0.0, gross_amount=100.0)
    H.insert_line(ds, invoice_id, qty=10.0, unit_price=10.0,
                  net_amount=100.0, tax_amount=0.0, gross_amount=100.0,
                  schedule_id=H.SCHEDULE_ID, po_unit_price=10.0)

    with pytest.raises(VendorInvoiceError) as exc:
        service.match(invoice_id)

    assert exc.value.rule == ERR_SOURCE_STATUS


# #8 收货单 draft 作为 3-way 锚点 → VI_SOURCE_STATUS_INVALID
def test_draft_receipt_rejected(ds, service):
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0)
    H.seed_receipt_line(ds, qty_received=10.0, receipt_status='draft')
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-GAP-8', net_amount=100.0, tax_amount=0.0,
        gross_amount=100.0)
    H.insert_line(ds, invoice_id, qty=10.0, unit_price=10.0,
                  net_amount=100.0, tax_amount=0.0, gross_amount=100.0,
                  receipt_line_id=H.RECEIPT_LINE_ID, po_unit_price=10.0)

    with pytest.raises(VendorInvoiceError) as exc:
        service.match(invoice_id)

    assert exc.value.rule == ERR_SOURCE_STATUS


# ---------------------------------------------------------------- UOM / 多异常
# #9 发票行 uom ≠ 源单 uom → VI_UOM_MISMATCH
def test_uom_mismatch_rejected(ds, service):
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0,
                          uom_id=H.UOM_ID)
    H.seed_receipt_line(ds, qty_received=10.0, uom_id=H.UOM_ID)
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-GAP-9', net_amount=100.0, tax_amount=0.0,
        gross_amount=100.0)
    H.insert_line(ds, invoice_id, qty=10.0, unit_price=10.0,
                  net_amount=100.0, tax_amount=0.0, gross_amount=100.0,
                  receipt_line_id=H.RECEIPT_LINE_ID, po_unit_price=10.0,
                  uom_id=H.UOM_ID + 1)

    with pytest.raises(VendorInvoiceError) as exc:
        service.match(invoice_id)

    assert exc.value.rule == ERR_UOM


# #10 一行同时超量（容差内）+ 超价 → reason 为 2 元 JSON 数组
def test_line_with_price_and_qty_over_reports_both_reasons(ds, service):
    H.set_param(ds, 'vi_qty_tolerance_receipt', '10')
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-GAP-10', net_amount=115.5, tax_amount=0.0,
        gross_amount=115.5)
    H.insert_line(ds, invoice_id, qty=10.5, unit_price=11.0,
                  net_amount=115.5, tax_amount=0.0, gross_amount=115.5,
                  receipt_line_id=H.RECEIPT_LINE_ID, po_unit_price=10.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert result['match_exception_reason'].startswith('[')
    assert parse_reasons(result['match_exception_reason']) == [
        REASON_QTY_RECEIPT, REASON_PRICE]


# ---------------------------------------------------------------- no_receipt
# #11 gr_based 行无收货锚点 → no_receipt，override 后可提交并过账
def test_gr_based_line_without_receipt_can_override_and_post(ds, service):
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0)
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-GAP-11', net_amount=100.0, tax_amount=0.0,
        gross_amount=100.0)
    H.insert_line(ds, invoice_id, qty=10.0, unit_price=10.0,
                  net_amount=100.0, tax_amount=0.0, gross_amount=100.0,
                  po_unit_price=10.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'unmatched'
    assert result['match_exception_reason'] == REASON_NO_RECEIPT
    line = H.get_lines(ds, invoice_id)[0]
    assert line['match_status'] == 'no_receipt'
    assert line['match_exception_reason'] == REASON_NO_RECEIPT

    service.override_match(invoice_id, reason='先开票后收货')
    service.submit(invoice_id)
    out = service.post(invoice_id)

    assert out['status'] == 'posted'


# ---------------------------------------------------------------- 税额 / 容差方向
# #12 vi_po_tax_compare=true 且行税额偏离 PO 税率重算值 → VI_PO_TAX_MISMATCH
def test_po_tax_compare_flags_mismatch(ds, service):
    H.set_param(ds, 'vi_po_tax_compare', 'true')
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0,
                          tax_rate_percent=13)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-GAP-12', net_amount=100.0, tax_amount=5.0,
        gross_amount=105.0)
    H.insert_line(ds, invoice_id, qty=10.0, unit_price=10.0,
                  net_amount=100.0, tax_amount=5.0, gross_amount=105.0,
                  receipt_line_id=H.RECEIPT_LINE_ID, po_unit_price=10.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert result['match_exception_reason'] == REASON_PO_TAX


# #13 tolerance_direction='both' 时单价低于 PO 价超容差 → price_under_tolerance
def test_price_below_po_with_both_direction_is_exception(ds, service):
    H.set_param_direction(ds, 'vi_price_tolerance', 'both')
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id = H.insert_invoice(
        ds, invoice_no='VI-GAP-13', net_amount=90.0, tax_amount=11.7,
        gross_amount=101.7)
    H.insert_line(ds, invoice_id, qty=10.0, unit_price=9.0,
                  net_amount=90.0, tax_amount=11.7, gross_amount=101.7,
                  receipt_line_id=H.RECEIPT_LINE_ID, po_unit_price=10.0)

    result = service.match(invoice_id)

    assert result['match_status'] == 'exception'
    assert result['match_exception_reason'] == REASON_PRICE_UNDER