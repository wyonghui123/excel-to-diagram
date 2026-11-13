# -*- coding: utf-8 -*-
"""采购发票金额 —— W2（D-VI-27：复用统一金额内核的薄子类）。

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §22.1 / §22.2 / §22.3
  docs/superpowers/plans/2026-11-12-vendor-invoice-amount-w2-execution-plan.md

设计（R-VI-33）:
  · 算术全部继承 `SalesOrderAmountService`，本文件**不出现任何公式**。
  · 只覆写加载 / 写回（四张表换成本域两张表）与两个算术钩子：
      _line_amounts   → 含税价倒算路径 B；缺税率时抛 VI_TAX_RATE_REQUIRED
      _header_amounts → 供应商票面总额 + rounding_diff
  · 跨单据复用判据：新增单据金额 = 新增一个只做加载/写回的薄子类。

口径:
  · 行路径 A（不含税价，price_includes_tax=0）：kernel 默认实现。
  · 行路径 B（含税价，price_includes_tax=1）：gross = R(q×p)；
    net = R(gross/(1+r/100))；tax = R(gross−net)。
  · 头：net/tax = Σ 行；gross 取 `supplier_gross_amount`（非空时），
    rounding_diff = R(gross − net − tax)。
  · 精度唯一来自 `currencies.decimal_places`；舍入方向来自 `tax_codes.rounding`。

边界（W2 不做）:
  · 行上 tax_rate_percent 快照优先于税码查询（W6 税模式）；
    本波仍按 tax_code_id → tax_rates 生效区间取税率。
  · 税额直录（line_direct）与容差校验在 W6 接入；本波只提供算术。
"""

from decimal import Decimal
from typing import Any, Dict, Optional

from meta.services.sales_order_amount_service import (
    DEFAULT_DECIMALS,
    _ZERO,
    _as_float,
    _dec,
    _round,
    _round_tax,
    _truthy,
    SalesOrderAmountError,
    SalesOrderAmountService,
)
from meta.services.control_parameter_service import ControlParameterResolver

HEADER_TABLE = 'vendor_invoices'
LINE_TABLE = 'vendor_invoice_lines'

TAX_MODE_LINE_DIRECT = 'line_direct'
TAX_MODE_RATE_CALC = 'rate_calc'
DEFAULT_TAX_TOLERANCE = Decimal('0.01')


class VendorInvoiceAmountService(SalesOrderAmountService):
    """采购发票行 / 头金额重算（算术继承 kernel）。"""

    # ---------------- 算术钩子 ----------------

    def _line_amounts(self, *, qty: Decimal, unit_price: Decimal,
                      price_includes_tax: Any = None,
                      tax_rate_percent: Optional[Decimal] = None,
                      tax_rounding: Optional[str] = None,
                      decimals: int = DEFAULT_DECIMALS,
                      sign: Decimal = Decimal('1'),
                      net_adjustment: Decimal = _ZERO,
                      declared_tax_amount: Optional[Decimal] = None,
                      tax_mode: Any = None,
                      tax_tolerance: Any = None) -> Dict[str, Any]:
        """路径 B 前置校验后交给内核；路径 A 在 line_direct 下校验直录税额。

        line_direct（Spec §22.2 规则 2 / R-VI-30）：
          `|tax − R(net×r/100)| ≤ vi_tax_tolerance_abs`；超容差时仍采用直录税额
          （`gross = net + tax`），并返回 `tax_mismatch=True`，由匹配层置
          `exception`（`VI_TAX_MISMATCH`，可 override，Spec §22.12）。
        路径 B 的税额由含税毛额倒算吸收，不参与直录校验。
        """
        if _truthy(price_includes_tax) and tax_rate_percent is None:
            raise SalesOrderAmountError(
                '含税价行必须提供税率（tax_rate_percent 或有效税码）',
                field_name='tax_rate_percent', rule='VI_TAX_RATE_REQUIRED')
        values = super()._line_amounts(
            qty=qty, unit_price=unit_price,
            price_includes_tax=price_includes_tax,
            tax_rate_percent=tax_rate_percent, tax_rounding=tax_rounding,
            decimals=decimals, sign=sign, net_adjustment=net_adjustment,
            declared_tax_amount=declared_tax_amount, tax_mode=tax_mode,
            tax_tolerance=tax_tolerance)
        if (_truthy(price_includes_tax)
                or str(tax_mode or '') != TAX_MODE_LINE_DIRECT
                or declared_tax_amount is None):
            return values

        declared = _round(_dec(declared_tax_amount), decimals)
        values['tax_mismatch'] = False
        if tax_rate_percent is not None:
            expected = _round_tax(
                values['net_amount'] * _dec(tax_rate_percent) / Decimal('100'),
                decimals, tax_rounding)
            tolerance = (_dec(tax_tolerance) if tax_tolerance not in (None, '')
                         else DEFAULT_TAX_TOLERANCE)
            values['tax_mismatch'] = abs(declared - expected) > tolerance
        values['tax_amount'] = declared
        values['gross_amount'] = values['net_amount'] + declared
        return values

    def _header_amounts(self, *, sum_net: Decimal, sum_tax: Decimal,
                        sum_gross: Decimal, supplier_gross: Any = None,
                        decimals: int = DEFAULT_DECIMALS,
                        rounding_tolerance: Any = None) -> Dict[str, Any]:
        """Σ 行 + 供应商票面总额兜底，并给出 rounding_diff。"""
        values = super()._header_amounts(
            sum_net=sum_net, sum_tax=sum_tax, sum_gross=sum_gross,
            supplier_gross=supplier_gross, decimals=decimals,
            rounding_tolerance=rounding_tolerance)
        if supplier_gross not in (None, ''):
            values['gross_amount'] = _round(_dec(supplier_gross), decimals)
        values['rounding_diff'] = _round(
            values['gross_amount'] - values['net_amount'] - values['tax_amount'],
            decimals)
        return values

    # ---------------- 加载 / 写回（只换表） ----------------

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, invoice_id AS order_id, qty, unit_price, '
            'price_includes_tax, tax_code_id, tax_rate_percent, tax_amount '
            'FROM vendor_invoice_lines WHERE id = ?', [line_id])
        return rows[0] if rows else None

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, org_id, document_type_id, invoice_date AS order_date, '
            'currency_id, supplier_gross_amount '
            'FROM vendor_invoices WHERE id = ?', [order_id])
        if not rows:
            return None
        row = dict(rows[0])
        row['tax_mode'], row['tax_tolerance_abs'] = self._resolve_tax_settings(row)
        return row

    def _resolve_tax_settings(self, order: Dict[str, Any]):
        """税模式与直录税额容差（Spec §22.10）：四维解析 → 兜底 line_direct / 0.01。"""
        dims = {
            'org_id': order.get('org_id') or 0,
            'document_type_id': order.get('document_type_id') or 0,
        }
        try:
            resolver = ControlParameterResolver(self.ds)
            mode = str(resolver.resolve('vi_tax_mode', dims) or '').strip()
            tolerance = resolver.resolve('vi_tax_tolerance_abs', dims)
        except Exception:
            return TAX_MODE_LINE_DIRECT, DEFAULT_TAX_TOLERANCE
        if mode not in (TAX_MODE_LINE_DIRECT, TAX_MODE_RATE_CALC):
            mode = TAX_MODE_LINE_DIRECT
        if tolerance in (None, ''):
            tolerance = DEFAULT_TAX_TOLERANCE
        return mode, _dec(tolerance)

    def _sum_lines(self, order_id: Any):
        return self.ds.query(
            'SELECT net_amount, tax_amount, gross_amount FROM '
            'vendor_invoice_lines WHERE invoice_id = ?', [order_id])

    def _write_line(self, line_id: Any, values: Dict[str, Any]) -> None:
        self.ds.execute(
            'UPDATE vendor_invoice_lines SET net_amount = ?, '
            'tax_rate_percent = ?, tax_amount = ?, gross_amount = ?, '
            "updated_at = datetime('now') WHERE id = ?",
            [_as_float(values['net_amount']),
             _as_float(values['tax_rate_percent']),
             _as_float(values['tax_amount']),
             _as_float(values['gross_amount']), line_id])

    def _write_order(self, order_id: Any, values: Dict[str, Any]) -> None:
        self.ds.execute(
            'UPDATE vendor_invoices SET net_amount = ?, tax_amount = ?, '
            "gross_amount = ?, rounding_diff = ?, updated_at = datetime('now') "
            'WHERE id = ?',
            [_as_float(values['net_amount']), _as_float(values['tax_amount']),
             _as_float(values['gross_amount']),
             _as_float(values.get('rounding_diff', _ZERO)), order_id])

    # ---------------- 调整单行（Spec §22.5 T1 / T2 / T3） ----------------

    def compute_adjustment_line(self, header: Dict[str, Any],
                                source: Dict[str, Any], *,
                                qty: Any = None,
                                unit_price: Any = None,
                                net_amount: Any = None,
                                tax_amount: Any = None,
                                direction: str = 'increase') -> Dict[str, Any]:
        """调整行金额（只算不落库）。

        T1 仅给数量：单价沿用源行，按 §22.2 路径 A 重算；
        T2 给单价（`qty` 缺省取源行）/ 组合：按 §22.2 全量重算；
        T3 `qty=0` + `net_amount`：净额直录（可选直录 `tax_amount`）。
        税额一律「新净额 × 原税率」重算（§22.7 G-4），不按源金额比例；
        税率快照缺失时用源行隐含税率（原行税额 / 原行净额）回退。
        decrease：数量存正数幅值、金额带负号。
        """
        sign = Decimal('1') if str(direction) == 'increase' else Decimal('-1')
        decimals = self._currency_decimals(header.get('currency_id'))

        src_qty = abs(_dec(source.get('qty')))
        src_net = abs(_dec(source.get('net_amount')))

        tax_code_id = source.get('tax_code_id')
        rate: Optional[Decimal] = None
        if source.get('tax_rate_percent') not in (None, ''):
            rate = _dec(source.get('tax_rate_percent'))
        if rate is None and tax_code_id not in (None, ''):
            rate = self._lookup_rate_percent(tax_code_id, header.get('invoice_date'))
        # 税率快照与税码都缺失 → 源行隐含税率（原行税额 / 原行净额）
        effective_rate = rate
        if effective_rate is None and src_net > 0:
            effective_rate = (abs(_dec(source.get('tax_amount')))
                              * Decimal('100') / src_net)
        tax_rounding = (self._lookup_tax_rounding(tax_code_id)
                        if tax_code_id not in (None, '') else None)
        tax_mode, tax_tolerance = self._resolve_tax_settings(header)

        if net_amount is not None:
            # T3 / 显式净额：净额直录，数量只作幅值（可为 0）
            out_qty = abs(_dec(qty if qty is not None else 0))
            adjustment = _round(sign * abs(_dec(net_amount)), decimals)
            declared = (_round(sign * abs(_dec(tax_amount)), decimals)
                        if tax_amount is not None else None)
            values = self._line_amounts(
                qty=_ZERO, unit_price=_ZERO, price_includes_tax=0,
                tax_rate_percent=effective_rate, tax_rounding=tax_rounding,
                decimals=decimals, net_adjustment=adjustment,
                declared_tax_amount=declared, tax_mode=tax_mode,
                tax_tolerance=tax_tolerance)
            out_unit_price = (_round(abs(adjustment) / out_qty, decimals)
                              if out_qty > 0 else _ZERO)
            price_includes_tax = 0
        else:
            out_qty = abs(_dec(qty if qty is not None else src_qty))
            if out_qty <= 0:
                raise SalesOrderAmountError(
                    '调整行数量为 0 时必须给出净额', field_name='qty',
                    rule='VI_ADJUSTMENT_EMPTY_LINE')
            out_unit_price = _dec(unit_price if unit_price is not None
                                  else source.get('unit_price'))
            # T1 单价沿用源行 → 路径 A；T2 / 组合沿用源行价格基准（§22.2）
            price_includes_tax = (source.get('price_includes_tax')
                                  if unit_price is not None else 0)
            values = self._line_amounts(
                qty=out_qty, unit_price=out_unit_price,
                price_includes_tax=price_includes_tax,
                tax_rate_percent=effective_rate, tax_rounding=tax_rounding,
                decimals=decimals, sign=sign)

        return {
            'qty': out_qty,
            'unit_price': out_unit_price,
            'price_includes_tax': price_includes_tax,
            'net_amount': values['net_amount'],
            'tax_amount': values['tax_amount'],
            'gross_amount': values['gross_amount'],
            'tax_rate_percent': rate,
        }