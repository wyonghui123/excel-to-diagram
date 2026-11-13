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


def _truthy(value: Any) -> bool:
    """轻量布尔判定：兼容 0/1、'0'/'1'、'true'/'false' 与 None。"""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in ('', '0', 'false', 'no', 'n', 'none')
    if isinstance(value, (int, float, Decimal)):
        return value != 0
    return bool(value)


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
        values = self.preview_line(line_id)
        if values is None:
            return None
        self._write_line(line_id, values)
        return values

    def preview_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        """只读重算单行（不落库），返回内核中间值。

        金额回溯 `amount-trace` 与显式重算共用本方法，保证「展示口径 = 落库口径」；
        子类覆写 `_line_amounts` 后自动生效（VI 的路径 B / 直录税额同样覆盖）。
        """
        line = self._load_line(line_id)
        if not line:
            return None
        order = self._load_order(line.get('order_id'))
        if not order:
            return None

        decimals = self._currency_decimals(order.get('currency_id'))
        sign = Decimal('-1') if self._document_category(
            order.get('document_type_id')) == 'return' else Decimal('1')

        qty = _dec(line.get('qty'))
        unit_price = _dec(line.get('unit_price'))

        tax_rate_percent: Optional[Decimal] = None
        tax_rounding: Optional[str] = None
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
            tax_rounding = self._lookup_tax_rounding(tax_code_id)

        amounts = self._line_amounts(
            qty=qty, unit_price=unit_price,
            price_includes_tax=line.get('price_includes_tax'),
            tax_rate_percent=tax_rate_percent, tax_rounding=tax_rounding,
            decimals=decimals, sign=sign,
            # 抬头折扣/附加费分摊额由分摊服务写回，这里只叠加，不改 unit_price
            net_adjustment=(_dec(line.get('header_discount_amount'))
                            + _dec(line.get('header_surcharge_amount'))),
            # 直录税额扩展（Spec §22.2 / R-VI-30）：SO/PO 加载钩子不返回这两项，
            # 默认实现忽略；VI 子类通过 _load_line / _load_order 提供后启用校验。
            tax_mode=line.get('tax_mode') or order.get('tax_mode'),
            declared_tax_amount=(_dec(line.get('tax_amount'))
                                 if line.get('tax_amount') not in (None, '') else None),
            tax_tolerance=order.get('tax_tolerance_abs'))
        values = {
            **amounts,
            'tax_rate_percent': tax_rate_percent,
        }
        return values

    # ---------------- 抬头 ----------------

    def recompute_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        """按行合计回写抬头三项（R7）。"""
        values = self.preview_order(order_id)
        if values is None:
            return None
        self._write_order(order_id, values)
        return values

    def preview_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        """只读汇总抬头（不落库），口径与 `recompute_order` 逐位一致。"""
        order = self._load_order(order_id)
        if not order:
            return None
        decimals = self._currency_decimals(order.get('currency_id'))
        net = tax = gross = _ZERO
        for row in self._sum_lines(order_id):
            net += _dec(row.get('net_amount'))
            tax += _dec(row.get('tax_amount'))
            gross += _dec(row.get('gross_amount'))
        values = self._header_amounts(
            sum_net=net, sum_tax=tax, sum_gross=gross,
            supplier_gross=order.get('supplier_gross_amount'),
            decimals=decimals)
        return values

    # ---------------- 算术钩子（可覆写；默认 = 现行 SO/PO 口径） ----------------
    # [D-VI-27 2026-11-12] 采购发票金额复用本内核：VI 子类只覆写加载 / 写回与
    # 这两个钩子，禁止复制公式或新建平行金额服务（R-VI-33）。

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
        """行金额算术。

        路径 A（默认，不含税价）：`net = R(R(q×p×sign) + 调整额)`；
            `tax = R_tax(net×r/100)`；`gross = net + tax`。
        路径 B（`price_includes_tax` 为真且税率非空，含税价倒算）：
            `gross = R(q×p×sign)`；`net = R(gross/(1+r/100))`；
            `tax = R(gross−net)`。

        `declared_tax_amount / tax_mode / tax_tolerance` 为直录税额扩展点
        （Spec §22.2 规则 2 / R-VI-30）：默认实现不读取，SO/PO 行为逐位不变；
        VI 子类在路径 A 且 `tax_mode='line_direct'` 时校验并采用直录税额。
        """
        gross_price = _round(qty * unit_price * sign, decimals)
        if _truthy(price_includes_tax) and tax_rate_percent is not None:
            divisor = Decimal('1') + tax_rate_percent / Decimal('100')
            net = _round(gross_price / divisor, decimals)
            tax = _round(gross_price - net, decimals)
            return {
                'net_amount': net,
                'tax_base_amount': net,
                'tax_amount': tax,
                'gross_amount': gross_price,
            }

        net = _round(gross_price + net_adjustment, decimals)
        tax = _ZERO
        if tax_rate_percent is not None:
            tax = _round_tax(net * tax_rate_percent / Decimal('100'),
                             decimals, tax_rounding)
        return {
            'net_amount': net,
            'tax_base_amount': net,
            'tax_amount': tax,
            'gross_amount': net + tax,
        }

    def net_unit_price(self, *, unit_price: Any,
                       price_includes_tax: Any = None,
                       tax_rate_percent: Any = None,
                       decimals: int = DEFAULT_DECIMALS) -> Decimal:
        """不含税单价（价格比较唯一口径，Spec §22.2 规则 7）。

        含税价按 1 单位走 `_line_amounts` 路径 B 倒算，保证与行金额逐位一致；
        子类覆写 `_line_amounts` 后自动生效。不含税价原值返回。
        """
        return self._line_amounts(
            qty=Decimal('1'), unit_price=_dec(unit_price),
            price_includes_tax=price_includes_tax,
            tax_rate_percent=(_dec(tax_rate_percent)
                              if tax_rate_percent is not None else None),
            decimals=decimals)['net_amount']

    def _header_amounts(self, *, sum_net: Decimal, sum_tax: Decimal,
                        sum_gross: Decimal, supplier_gross: Any = None,
                        decimals: int = DEFAULT_DECIMALS,
                        rounding_tolerance: Any = None) -> Dict[str, Any]:
        """抬头金额（默认 = Σ 行三项，逐项按币种精度舍入）。

        SO/PO 只回三项；`supplier_gross / rounding_tolerance` 供 VI 子类覆写。
        子类若增加返回键，必须同时覆写 `_write_order`（默认只写三列）。
        """
        return {
            'net_amount': _round(sum_net, decimals),
            'tax_amount': _round(sum_tax, decimals),
            'gross_amount': _round(sum_gross, decimals),
        }

    # ---------------- 查询 / 写入（可覆写，便于单测注入） ----------------

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, order_id, qty, unit_price, tax_code_id, '
            'header_discount_amount, header_surcharge_amount '
            'FROM sales_order_lines WHERE id = ?', [line_id])
        return rows[0] if rows else None

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, document_type_id, order_date, currency_id '
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

    def _document_category(self, document_type_id: Any) -> Optional[str]:
        if document_type_id in (None, ''):
            return None
        try:
            rows = self.ds.query(
                'SELECT document_category FROM type_definitions WHERE id = ?',
                [document_type_id])
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
