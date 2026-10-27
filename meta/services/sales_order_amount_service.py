# -*- coding: utf-8 -*-
"""销售订单金额 —— W0-R7 / R11 / R12 的计算与快照回写。

依据: meta/schemas/sales_order_line.yaml 头注释「行级口径 ③」
      docs/superpowers/specs/2026-10-24-sales-order-wave0-detailed-plan.md §1.4

口径:
  · 行：net = qty × unit_price + 抬头折扣/附加费分摊额，按订单币种
        decimal_places 四舍五入（R11）；
        tax_base = net；tax = round(tax_base × tax_rate_percent / 100, 精度)；
        gross = net + tax。税率按订单日期从 tax_rates 的生效区间取（R12）。
  · 符号（R3）：订单抬头 order_type.document_category = 'return' 时，
        整行金额乘以 -1；非退货单为正。qty 恒正（R2 由守卫保证）。
  · 抬头（R7）：net/tax/gross 三项 = 该订单所有行的对应项之和。

[D 2026-10-27] 税额舍入方向改为按税码 `tax_code.rounding` 执行（此前一律
  ROUND_HALF_UP，该字段是死字段——配了不生效且静默失效）。精度（位数）仍唯一
  取自币种 `currency.decimal_places`，税码只管方向。
  依据: docs/superpowers/specs/2026-10-27-sales-order-business-type-and-rounding-spec.md
        FR-005 / FR-010

只在行写入（创建 / 更新 / 删除）后调用，属「快照式」回写：下游主数据变动
（税率、物料价）不会触发重算，已确认单据的金额因此保持不变（R9）。

已知边界：与守卫相同，只覆盖 bo_api 写路径。
"""

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional

from meta.core.rounding import is_valid_rounding_mode, resolve_rounding_mode

logger = logging.getLogger(__name__)

DEFAULT_DECIMALS = 2
_ZERO = Decimal('0')


class SalesOrderAmountError(ValueError):
    """金额无法计算（如税码在订单日期无生效税率）。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _dec(value: Any) -> Decimal:
    if value is None or value == '':
        return _ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _ZERO


def _round(value: Decimal, decimals: int) -> Decimal:
    """按币种精度四舍五入（负数对称：-2.5 → -3）。"""
    q = Decimal(1).scaleb(-decimals)
    return value.quantize(q, rounding=ROUND_HALF_UP)


def _round_tax(value: Decimal, decimals: int, mode: Optional[str]) -> Decimal:
    """税额舍入：方向按税码的 `tax_code.rounding`，精度按币种。

    [D 2026-10-27] 此前税额一律 ROUND_HALF_UP（`tax_code.rounding_mode` 是死字段，
    配了不生效且静默失效）。现按税码配置的方向执行：
      none / round → ROUND_HALF_UP（与既有行为逐位一致，零回归）
      ceil        → ROUND_CEILING（部分国家法定要求进位）
      floor       → ROUND_FLOOR
    非法值 → 回落 ROUND_HALF_UP + WARNING（不中断计算，Spec FR-009 / NFR-003）。
    """
    if mode not in (None, '') and not is_valid_rounding_mode(mode):
        logger.warning(
            '[sales_order_amount] tax_code.rounding 非法值 %r，回落为 half-up', mode)
    q = Decimal(1).scaleb(-decimals)
    return value.quantize(q, rounding=resolve_rounding_mode(mode))


def _as_float(value: Any) -> Optional[float]:
    """落库参数：sqlite3 不接受 Decimal，统一转 float（列本身是 REAL）。"""
    return None if value is None else float(value)


class SalesOrderAmountService:
    """行金额计算与抬头汇总回写。

    覆写 `_load_line` / `_load_order` / `_currency_decimals` /
    `_document_category` / `_lookup_rate_percent` / `_write_line` / `_write_order`
    即可注入测试数据（不依赖真实库）。
    """

    def __init__(self, data_source):
        self.ds = data_source

    # ---------------- 行 ----------------

    def recompute_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        """重算单行并落库，返回写入的字段（Decimal 原值）。"""
        line = self._load_line(line_id)
        if not line:
            return None
        order = self._load_order(line.get('order_id'))
        if not order:
            return None

        decimals = self._currency_decimals(order.get('currency_id'))
        sign = Decimal('-1') if self._document_category(
            order.get('order_type_id')) == 'return' else Decimal('1')

        qty = _dec(line.get('qty'))
        unit_price = _dec(line.get('unit_price'))
        base = _round(qty * unit_price * sign, decimals)
        # 抬头折扣/附加费分摊额由分摊服务写回，这里只叠加，不改 unit_price
        net = _round(base
                     + _dec(line.get('header_discount_amount'))
                     + _dec(line.get('header_surcharge_amount')), decimals)

        tax_rate_percent: Optional[Decimal] = None
        tax = _ZERO
        tax_code_id = line.get('tax_code_id')
        if tax_code_id not in (None, ''):
            tax_rate_percent = self._lookup_rate_percent(
                tax_code_id, order.get('order_date'))
            if tax_rate_percent is None:
                raise SalesOrderAmountError(
                    f'税码 {tax_code_id} 在订单日期 {order.get("order_date")} '
                    f'无生效税率，无法计算税额',
                    field_name='tax_code_id', rule='tax_rate_missing')
            # [D 2026-10-27] 税额舍入方向按税码配置执行（此前一律 half-up）。
            tax = _round_tax(net * tax_rate_percent / Decimal('100'), decimals,
                             self._lookup_tax_rounding(tax_code_id))

        gross = net + tax
        values = {
            'net_amount': net,
            'tax_base_amount': net,
            'tax_rate_percent': tax_rate_percent,
            'tax_amount': tax,
            'gross_amount': gross,
        }
        self._write_line(line_id, values)
        return values

    # ---------------- 抬头 ----------------

    def recompute_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        """按行合计回写抬头三项（R7）。"""
        order = self._load_order(order_id)
        if not order:
            return None
        decimals = self._currency_decimals(order.get('currency_id'))
        net = tax = gross = _ZERO
        for row in self._sum_lines(order_id):
            net += _dec(row.get('net_amount'))
            tax += _dec(row.get('tax_amount'))
            gross += _dec(row.get('gross_amount'))
        values = {
            'net_amount': _round(net, decimals),
            'tax_amount': _round(tax, decimals),
            'gross_amount': _round(gross, decimals),
        }
        self._write_order(order_id, values)
        return values

    # ---------------- 查询 / 写入（可覆写，便于单测注入） ----------------

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, order_id, qty, unit_price, tax_code_id, '
            'header_discount_amount, header_surcharge_amount '
            'FROM sales_order_lines WHERE id = ?', [line_id])
        return rows[0] if rows else None

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, order_type_id, order_date, currency_id '
            'FROM sales_orders WHERE id = ?', [order_id])
        return rows[0] if rows else None

    def _sum_lines(self, order_id: Any):
        return self.ds.query(
            'SELECT net_amount, tax_amount, gross_amount FROM sales_order_lines '
            'WHERE order_id = ?', [order_id])

    def _currency_decimals(self, currency_id: Any) -> int:
        if currency_id in (None, ''):
            return DEFAULT_DECIMALS
        try:
            rows = self.ds.query(
                'SELECT decimal_places FROM currencies WHERE id = ?', [currency_id])
        except Exception as e:
            logger.warning(f'[sales_order_amount] 读取币种精度失败: {e}')
            return DEFAULT_DECIMALS
        if not rows:
            return DEFAULT_DECIMALS
        raw = rows[0].get('decimal_places')
        try:
            decimals = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_DECIMALS
        return decimals if 0 <= decimals <= 8 else DEFAULT_DECIMALS

    def _document_category(self, order_type_id: Any) -> Optional[str]:
        if order_type_id in (None, ''):
            return None
        try:
            rows = self.ds.query(
                'SELECT document_category FROM type_definitions WHERE id = ?',
                [order_type_id])
        except Exception as e:
            logger.warning(f'[sales_order_amount] 读取单据类别失败: {e}')
            return None
        return rows[0].get('document_category') if rows else None

    def _lookup_rate_percent(self, tax_code_id: Any,
                             order_date: Any) -> Optional[Decimal]:
        """取 [effective_from, effective_to) 覆盖订单日期的税率。"""
        try:
            rows = self.ds.query(
                'SELECT rate_percent FROM tax_rates '
                'WHERE tax_code_id = ? '
                '  AND effective_from <= ? '
                '  AND (effective_to IS NULL OR effective_to > ?) '
                'ORDER BY effective_from DESC LIMIT 1',
                [tax_code_id, order_date, order_date])
        except Exception as e:
            logger.warning(f'[sales_order_amount] 读取税率失败: {e}')
            return None
        if not rows:
            return None
        return _dec(rows[0].get('rate_percent'))

    def _lookup_tax_rounding(self, tax_code_id: Any) -> Optional[str]:
        """取税码的舍入方式（`tax_code.rounding`）。

        [D 2026-10-27] 补齐该字段的执行消费方（此前是死字段）。
        查不到 / 查失败 → 返回 None，调用方按 half-up 处理（回落默认，不中断）。
        """
        try:
            rows = self.ds.query(
                'SELECT rounding FROM tax_codes WHERE id = ?', [tax_code_id])
        except Exception as e:
            logger.warning(f'[sales_order_amount] 读取税码舍入方式失败: {e}')
            return None
        if not rows:
            return None
        return rows[0].get('rounding')

    def _write_line(self, line_id: Any, values: Dict[str, Any]) -> None:
        self.ds.execute(
            "UPDATE sales_order_lines SET net_amount = ?, tax_base_amount = ?, "
            "tax_rate_percent = ?, tax_amount = ?, gross_amount = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            [_as_float(values['net_amount']), _as_float(values['tax_base_amount']),
             _as_float(values['tax_rate_percent']), _as_float(values['tax_amount']),
             _as_float(values['gross_amount']), line_id])

    def _write_order(self, order_id: Any, values: Dict[str, Any]) -> None:
        self.ds.execute(
            "UPDATE sales_orders SET net_amount = ?, tax_amount = ?, "
            "gross_amount = ?, updated_at = datetime('now') WHERE id = ?",
            [_as_float(values['net_amount']), _as_float(values['tax_amount']),
             _as_float(values['gross_amount']), order_id])
