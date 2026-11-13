# -*- coding: utf-8 -*-
"""W8-P1 采购发票费用行分摊（Spec §22.6.1 / §22.6.2）。

覆盖 7 条硬约束：
  ① 守恒      Σ 物料行 = Σ 费用行
  ② 不动原值  net_amount / 头金额 / rounding_diff 不变
  ③ 费用行不进目标集合，且派生列恒 0
  ④ 取整差额由 plan 落最后一行，不造尾差行
  ⑤ 零基数拒绝（不 0/0）
  ⑥ 重摊旧留痕置 invalid（不物理删除）
  ⑦ 先匹配后分摊
另覆盖借贷混行拒绝、红冲取负、开关关闭静默跳过、submit 接线。
"""

from decimal import Decimal

import pytest

from meta.services.vendor_invoice_charge_allocation_service import (
    ERR_BASE_ZERO,
    ERR_DISABLED,
    ERR_MATCH_REQUIRED,
    ERR_MIXED_SIGN,
    ChargeAllocationError,
    VendorInvoiceChargeAllocationService,
)
from meta.services.vendor_invoice_match_service import VendorInvoiceMatchService
from meta.tests.factories import _vendor_invoice_helpers as H

TAX_CODE_13 = 6601
TAX_CODE_6 = 6602


@pytest.fixture()
def ds(tmp_path):
    env = H.make_env(tmp_path)
    H.seed_type_definitions(env)
    H.seed_currency(env)
    H.seed_allocation_rule(env, code='VI_CHARGE_BY_NET_VALUE', basis='value',
                           rounding='round')
    H.seed_charge_allocation_params(env, enabled=True, rule_code='')
    return env


@pytest.fixture()
def service(ds):
    return VendorInvoiceChargeAllocationService(ds)


# ------------------------------------------------------------------ 辅助

def _line(ds, line_id):
    return ds.query('SELECT * FROM vendor_invoice_lines WHERE id = ?', [line_id])[0]


def _header(ds, invoice_id):
    return ds.query('SELECT * FROM vendor_invoices WHERE id = ?', [invoice_id])[0]


def _amount(row):
    return Decimal(str(row.get('allocated_charge_amount') or 0))


def _traces(ds, invoice_id, status='active'):
    return ds.query(
        'SELECT * FROM allocation_results WHERE document_type = ? '
        ' AND document_id = ? AND status = ? ORDER BY level, sequence',
        ['vendor_invoice', invoice_id, status])


def _invoice(ds, *, invoice_no='VI-ALLOC-1',
             materials=((1, 300.0, 3.0), (2, 100.0, 1.0)),
             charges=((3, H.LINE_TYPE_FREIGHT_ID, 40.0),),
             match_status='matched'):
    """物料行 + 费用行；头金额 = 行合计（费用行单列 net，税额记 0）。"""
    net = sum(m[1] for m in materials) + sum(c[2] for c in charges)
    invoice_id = H.insert_invoice(
        ds, invoice_no=invoice_no, net_amount=net, tax_amount=0.0,
        gross_amount=net)
    material_ids = []
    for line_no, amount, qty in materials:
        material_ids.append(H.insert_line(
            ds, invoice_id, line_no=line_no, qty=qty, unit_price=0.0,
            net_amount=amount, tax_amount=0.0, gross_amount=amount,
            match_status=match_status))
    charge_ids = []
    for line_no, line_type_id, amount in charges:
        charge_ids.append(H.insert_line(
            ds, invoice_id, line_no=line_no, qty=1.0, unit_price=0.0,
            net_amount=amount, tax_amount=0.0, gross_amount=amount,
            line_type_id=line_type_id))
    return invoice_id, material_ids, charge_ids


# ------------------------------------------------------------------ 预演

def test_compute_preview_does_not_persist(ds, service):
    """compute 只算不落库：派生列与留痕表都保持原样。"""
    invoice_id, material_ids, charge_ids = _invoice(ds)

    plan = service.compute(invoice_id)

    assert Decimal(plan['total']) == Decimal('40')
    assert [Decimal(a['allocated_charge_amount'])
            for a in plan['allocations']] == [Decimal('30'), Decimal('10')]
    assert plan['conserved'] is True
    assert plan['charge_line_ids'] == charge_ids
    assert plan['basis_field'] == 'net_amount'
    # 未落库
    assert _traces(ds, invoice_id) == []
    assert [_amount(_line(ds, i)) for i in material_ids + charge_ids] == \
        [Decimal('0')] * 3


# ------------------------------------------------------------------ 落库

def test_apply_conserves_and_keeps_source_amounts(ds, service):
    """① + ② + ③：Σ 守恒、原值不动、费用行恒 0。"""
    invoice_id, material_ids, charge_ids = _invoice(ds)

    plan = service.apply(invoice_id)

    assert plan['header_result_id']
    assert [_amount(_line(ds, i)) for i in material_ids] == \
        [Decimal('30'), Decimal('10')]
    assert [_amount(_line(ds, i)) for i in charge_ids] == [Decimal('0')]
    # ① 守恒
    assert sum(_amount(_line(ds, i)) for i in material_ids) == Decimal('40')
    # ② 行净额 / 头金额原样
    assert Decimal(str(_line(ds, charge_ids[0])['net_amount'])) == Decimal('40')
    header = _header(ds, invoice_id)
    assert Decimal(str(header['net_amount'])) == Decimal('440')
    assert Decimal(str(header['rounding_diff'] or 0)) == Decimal('0')


def test_apply_writes_replayable_traces(ds, service):
    """留痕口径：头记总额、行记摊得额，来源 / 规则 / 基数快照齐全。"""
    invoice_id, material_ids, _ = _invoice(ds)

    service.apply(invoice_id)

    rows = _traces(ds, invoice_id)
    assert len(rows) == 3
    header_row = [r for r in rows if r['level'] == 'header'][0]
    assert header_row['parent_id'] == invoice_id
    assert header_row['document_line_id'] is None
    assert Decimal(str(header_row['amount'])) == Decimal('40')
    assert header_row['charge_source'] == 'invoice'
    assert header_row['source_document_type'] == 'vendor_invoice'
    assert header_row['source_document_id'] == invoice_id
    assert header_row['allocation_basis'] == 'value'
    assert header_row['allocation_basis_field'] == 'net_amount'
    assert header_row['currency'] == 'CNY'
    assert header_row['sign'] == '+'

    line_rows = [r for r in rows if r['level'] == 'line']
    assert {r['document_line_id'] for r in line_rows} == set(material_ids)
    assert all(r['parent_id'] == invoice_id for r in line_rows)
    assert sorted(Decimal(str(r['amount'])) for r in line_rows) == \
        [Decimal('10'), Decimal('30')]


def test_reapply_invalidates_old_traces_and_keeps_values(ds, service):
    """⑥ 重摊：旧留痕置 invalid（保留行），派生列按新结果重写。"""
    invoice_id, material_ids, _ = _invoice(ds)

    service.apply(invoice_id)
    service.apply(invoice_id)

    assert len(_traces(ds, invoice_id, 'active')) == 3
    assert len(_traces(ds, invoice_id, 'invalid')) == 3
    assert [_amount(_line(ds, i)) for i in material_ids] == \
        [Decimal('30'), Decimal('10')]


def test_equal_basis_remainder_conserved(ds, service):
    """④ 等权 3 行摊 10：差额 1 个最小单位落首行，Σ 仍精确等于总额。"""
    H.seed_allocation_rule(ds, code='VI_CHARGE_EQUAL', basis='equal',
                           rounding='round')
    H.seed_charge_allocation_params(ds, enabled=True,
                                    rule_code='VI_CHARGE_EQUAL')
    invoice_id, _, _ = _invoice(
        ds, materials=((1, 100.0, 1.0), (2, 100.0, 1.0), (3, 100.0, 1.0)),
        charges=((4, H.LINE_TYPE_FREIGHT_ID, 10.0),))

    plan = service.apply(invoice_id)

    values = [Decimal(a['allocated_charge_amount'])
              for a in plan['allocations']]
    assert sum(values) == Decimal('10')
    assert max(values) - min(values) <= Decimal('0.0001')
    assert values[0] == Decimal('3.3334')


def test_no_charge_lines_writes_zero(ds, service):
    """无费用行：目标行写 0，不产生留痕。"""
    invoice_id, material_ids, _ = _invoice(ds, charges=())

    plan = service.apply(invoice_id)

    assert Decimal(plan['total']) == Decimal('0')
    assert [_amount(_line(ds, i)) for i in material_ids] == [Decimal('0')] * 2
    assert _traces(ds, invoice_id) == []
    assert not plan.get('header_result_id')


# ------------------------------------------------------------------ 拒绝路径

def test_mixed_sign_charge_lines_rejected(ds, service):
    """费用行借贷混行 → 拒绝，且不留下任何部分写入。"""
    invoice_id, material_ids, _ = _invoice(
        ds, charges=((3, H.LINE_TYPE_FREIGHT_ID, 40.0),
                     (4, H.LINE_TYPE_DISCOUNT_ID, -10.0)))

    with pytest.raises(ChargeAllocationError) as exc:
        service.apply(invoice_id)

    assert exc.value.rule == ERR_MIXED_SIGN
    assert _traces(ds, invoice_id) == []
    assert [_amount(_line(ds, i)) for i in material_ids] == [Decimal('0')] * 2


def test_zero_basis_rejected(ds, service):
    """⑤ 零基数：不产生 0/0，直接拒绝。"""
    invoice_id, _, _ = _invoice(
        ds, materials=((1, 0.0, 10.0), (2, 0.0, 10.0)),
        charges=((3, H.LINE_TYPE_FREIGHT_ID, 40.0),))

    with pytest.raises(ChargeAllocationError) as exc:
        service.apply(invoice_id)

    assert exc.value.rule == ERR_BASE_ZERO


def test_match_required_before_apply(ds, service):
    """⑦ 先匹配后分摊：物料行未匹配通过不得分摊。"""
    invoice_id, _, _ = _invoice(ds, match_status='unmatched')

    with pytest.raises(ChargeAllocationError) as exc:
        service.apply(invoice_id)

    assert exc.value.rule == ERR_MATCH_REQUIRED


def test_switch_off_skips_apply_and_compute_raises(ds, service):
    """开关关闭：提交链路静默跳过；显式预演时报 DISABLED。"""
    H.seed_charge_allocation_params(ds, enabled=False)
    invoice_id, material_ids, _ = _invoice(ds)

    assert service.apply(invoice_id) is None
    assert _traces(ds, invoice_id) == []
    assert [_amount(_line(ds, i)) for i in material_ids] == [Decimal('0')] * 2

    with pytest.raises(ChargeAllocationError) as exc:
        service.compute(invoice_id)
    assert exc.value.rule == ERR_DISABLED


# ------------------------------------------------------------------ 红冲

def test_credit_memo_negative_charge_allocates_negative(ds, service):
    """红冲 / 贷项：负数费用行按原比例取负，留痕 sign 为 '-'。"""
    invoice_id, material_ids, _ = _invoice(
        ds, charges=((3, H.LINE_TYPE_DISCOUNT_ID, -40.0),))

    plan = service.apply(invoice_id)

    assert Decimal(plan['total']) == Decimal('-40')
    assert [_amount(_line(ds, i)) for i in material_ids] == \
        [Decimal('-30'), Decimal('-10')]
    assert sum(_amount(_line(ds, i)) for i in material_ids) == Decimal('-40')
    rows = _traces(ds, invoice_id)
    assert {r['sign'] for r in rows} == {'-'}


# ------------------------------------------------------------------ submit 接线

def _submittable_invoice(ds, *, invoice_no='VI-SUB-1'):
    """一物料行（收货 10）+ 一运费行 50；PO 头附加费同为 50。"""
    H.seed_charge_params(ds)
    H.seed_tax_rate(ds, tax_code_id=TAX_CODE_13, rate_percent=13)
    H.seed_tax_rate(ds, tax_code_id=TAX_CODE_6, rate_percent=6)
    H.seed_purchase_order(ds, promised_qty=10.0, unit_price=10.0,
                          header_surcharge_amount=50.0)
    H.seed_receipt_line(ds, qty_received=10.0)
    invoice_id = H.insert_invoice(
        ds, invoice_no=invoice_no, net_amount=150.0, tax_amount=16.0,
        gross_amount=166.0)
    material_id = H.insert_line(
        ds, invoice_id, line_no=1, qty=10.0, unit_price=10.0,
        net_amount=100.0, tax_amount=13.0, gross_amount=113.0,
        receipt_line_id=H.RECEIPT_LINE_ID, po_unit_price=10.0,
        tax_code_id=TAX_CODE_13, tax_rate_percent=13)
    freight_id = H.insert_line(
        ds, invoice_id, line_no=2, qty=1.0, unit_price=50.0,
        net_amount=50.0, tax_amount=3.0, gross_amount=53.0,
        line_type_id=H.LINE_TYPE_FREIGHT_ID, tax_code_id=TAX_CODE_6,
        tax_rate_percent=6)
    return invoice_id, material_id, freight_id


def test_submit_allocates_when_enabled(ds):
    invoice_id, material_id, freight_id = _submittable_invoice(ds)

    out = VendorInvoiceMatchService(ds, ds).submit(invoice_id)

    assert out['status'] == 'submitted'
    assert _amount(_line(ds, material_id)) == Decimal('50')
    assert _amount(_line(ds, freight_id)) == Decimal('0')
    assert len(_traces(ds, invoice_id)) == 2


def test_submit_skips_allocation_when_disabled(ds):
    H.seed_charge_allocation_params(ds, enabled=False)
    invoice_id, material_id, freight_id = _submittable_invoice(ds)

    out = VendorInvoiceMatchService(ds, ds).submit(invoice_id)

    assert out['status'] == 'submitted'
    assert _amount(_line(ds, material_id)) == Decimal('0')
    assert _amount(_line(ds, freight_id)) == Decimal('0')
    assert _traces(ds, invoice_id) == []