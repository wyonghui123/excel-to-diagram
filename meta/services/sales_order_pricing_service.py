# -*- coding: utf-8 -*-
"""销售订单定价接线 —— 把「定价确定」落到订单行与抬头。

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
      §3.7 订单接线、§3.8 不变量 W1-R1 ~ W1-R8

职责边界:
  解析与取价在 `pricing_determination_service`；本服务只负责订单侧的
  触发判定、字段写回与降级：

    · 行：写 `unit_price` / `price_source` / `price_trace`
    · 抬头：写 `price_list_id` / `pricing_procedure_id` / `pricing_status`
    · 金额：一律交给 `sales_order_amount_service` 重算，本服务不写金额字段

写回口径（§3.7）:
  · 取价成功 → `price_source='rate_table'`，`unit_price` 按币种精度
  · 取价失败 → 保留原单价，只写 `price_trace.reason`（W1-R3 不阻塞保存）
  · 手工价   → `price_source='manual'`，自动取价跳过（W1-R2）
  · 显式重取 → `force=True` 无视 manual 标记，成功后 `price_source` 复位

已知边界：与订单守卫一致，只覆盖 bo_api 写路径与显式重取端点。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from meta.services.pricing_determination_service import (
    PricingDeterminationService,
    _date_key,
)
from meta.services.sales_order_amount_service import SalesOrderAmountService

logger = logging.getLogger(__name__)

ORDER_TABLE = 'sales_orders'
LINE_TABLE = 'sales_order_lines'

STATUS_PENDING = 'pending'
STATUS_DETERMINED = 'determined'
STATUS_MANUAL = 'manual'
STATUS_FAILED = 'failed'

SOURCE_RATE_TABLE = 'rate_table'
SOURCE_MANUAL = 'manual'

_DRAFT = 'draft'
_OPEN_LINE = 'open'


class SalesOrderPricingError(ValueError):
    """订单侧取价被拒（如非草稿状态显式重取）。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _num(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _trace_of(line: Dict[str, Any]) -> Dict[str, Any]:
    raw = line.get('price_trace')
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


class SalesOrderPricingService:
    """订单行的取价写回与抬头定价状态汇总。

    覆写 `_load_line` / `_load_order` / `_lines_for_order` / `_currency_code` /
    `_write_line` / `_write_order` 即可注入测试数据。
    """

    def __init__(self, data_source,
                 determination: Optional[PricingDeterminationService] = None,
                 amount_service: Optional[SalesOrderAmountService] = None):
        self.ds = data_source
        self.det = determination or PricingDeterminationService(data_source)
        self.amount = amount_service or SalesOrderAmountService(data_source)

    # ------------------------------------------------------------------
    # 行级
    # ------------------------------------------------------------------
    def price_line(self, line_id: Any, *, force: bool = False,
                   order: Optional[Dict[str, Any]] = None,
                   resolved: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """对单行取价并写回，返回写入摘要；不满足触发前提时返回 None。"""
        line = self._load_line(line_id)
        if not line:
            return None
        order = order or self._load_order(line.get('order_id'))
        if not order:
            return None

        # W1-R1：自动取价只在草稿态执行
        if str(order.get('status') or '').lower() != _DRAFT:
            return None
        # W1-R2：手工价不被自动覆盖（显式重取 force=True 例外）
        if not force and line.get('price_source') == SOURCE_MANUAL:
            return None
        # 无物料 / 无数量：不取价（由行校验先拦）
        if line.get('item_id') in (None, ''):
            return None
        qty = _num(line.get('qty'))
        if qty is None or qty <= 0:
            return None

        currency = self._currency_code(order.get('currency_id'))
        price_date = _date_key(order.get('price_date')) or _date_key(order.get('order_date'))
        dims = dict(
            sales_org_id=order.get('sales_org_id'),
            order_type_id=order.get('order_type_id'),
            price_date=price_date,
            currency=currency,
        )
        if resolved is None:
            resolved = self.det.resolve(**dims)

        result = self.det.determine_line(
            item_id=line.get('item_id'), qty=qty,
            customer_account_id=order.get('customer_account_id'), **dims,
            document_id=order.get('id'), document_line_id=line_id,
            persist=True,
        )

        values: Dict[str, Any] = {'price_trace': result['trace']}
        if result['pricing_status'] == STATUS_DETERMINED:
            values['unit_price'] = result['unit_price']
            values['price_source'] = SOURCE_RATE_TABLE
        self._write_line(line_id, values)

        self._write_order_snapshot(order.get('id'), resolved)
        return {
            'line_id': line_id,
            'pricing_status': result['pricing_status'],
            'reason': result.get('reason'),
            'unit_price': values.get('unit_price', line.get('unit_price')),
            'price_source': values.get('price_source', line.get('price_source')),
            'price_trace': result['trace'],
        }

    def mark_manual(self, line_id: Any) -> None:
        """用户显式录入单价 → 打上手工价标记，后续自动取价跳过该行。"""
        self._write_line(line_id, {'price_source': SOURCE_MANUAL})

    # ------------------------------------------------------------------
    # 抬头级
    # ------------------------------------------------------------------
    def reprice_order(self, order_id: Any, *, force: bool = False,
                      strict: bool = False) -> Optional[Dict[str, Any]]:
        """重取整单非手工行，并重算金额与抬头定价状态。

        `strict=True` 供显式「重新取价」端点使用：非草稿直接报错；
        自动触发路径用默认值，非草稿静默跳过（W1-R1）。
        """
        order = self._load_order(order_id)
        if not order:
            if strict:
                raise SalesOrderPricingError(
                    f'订单 {order_id} 不存在', field_name='id', rule='order_not_found')
            return None
        if str(order.get('status') or '').lower() != _DRAFT:
            if strict:
                raise SalesOrderPricingError(
                    '订单非草稿状态，不能重新取价',
                    field_name='status', rule='order_not_draft')
            return None

        currency = self._currency_code(order.get('currency_id'))
        price_date = _date_key(order.get('price_date')) or _date_key(order.get('order_date'))
        resolved = self.det.resolve(
            sales_org_id=order.get('sales_org_id'),
            order_type_id=order.get('order_type_id'),
            price_date=price_date,
            currency=currency,
        )

        repriced = 0
        for line in self._lines_for_order(order_id):
            if str(line.get('status') or '').lower() != _OPEN_LINE:
                continue
            got = self.price_line(line.get('id'), force=force, order=order,
                                  resolved=resolved)
            if got:
                repriced += 1
            self.amount.recompute_line(line.get('id'))

        totals = self.amount.recompute_order(order_id) or {}
        status = self.refresh_order_pricing_status(order_id)
        self._write_order_snapshot(order_id, resolved)
        return {
            'order_id': order_id,
            'repriced': repriced,
            'pricing_status': status,
            'net_amount': totals.get('net_amount'),
            'tax_amount': totals.get('tax_amount'),
            'gross_amount': totals.get('gross_amount'),
        }

    def refresh_order_pricing_status(self, order_id: Any) -> Optional[str]:
        """按行结果汇总抬头 `pricing_status`（failed > manual > determined > pending）。"""
        lines = self._lines_for_order(order_id)
        status = self._aggregate_status(lines)
        self._write_order(order_id, {'pricing_status': status})
        return status

    @staticmethod
    def _aggregate_status(lines: List[Dict[str, Any]]) -> str:
        priced = [l for l in lines if l.get('item_id') not in (None, '')]
        if not priced:
            return STATUS_PENDING
        failed = manual = determined = 0
        for line in priced:
            source = line.get('price_source')
            if source == SOURCE_MANUAL:
                manual += 1
                continue
            if _trace_of(line).get('reason'):
                failed += 1
            elif source == SOURCE_RATE_TABLE:
                determined += 1
        if failed:
            return STATUS_FAILED
        if manual:
            return STATUS_MANUAL
        if determined == len(priced):
            return STATUS_DETERMINED
        return STATUS_PENDING

    # ------------------------------------------------------------------
    # 查询 / 写入（可覆写，便于单测注入）
    # ------------------------------------------------------------------
    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, order_id, line_no, item_id, qty, unit_price, '
            'price_source, price_trace, status FROM sales_order_lines WHERE id = ?',
            [line_id])
        return rows[0] if rows else None

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, status, order_type_id, order_date, price_date, currency_id, '
            'sales_org_id, customer_account_id, pricing_status '
            'FROM sales_orders WHERE id = ?', [order_id])
        return rows[0] if rows else None

    def _lines_for_order(self, order_id: Any) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT id, item_id, qty, unit_price, price_source, price_trace, status '
            'FROM sales_order_lines WHERE order_id = ? ORDER BY line_no, id', [order_id])

    def _currency_code(self, currency_id: Any) -> Optional[str]:
        if currency_id in (None, ''):
            return None
        try:
            rows = self.ds.query(
                'SELECT code FROM currencies WHERE id = ?', [currency_id])
        except Exception as e:  # noqa: BLE001 - 查询失败按无币种降级
            logger.warning(f'[sales_order_pricing] 读取币种失败: {e}')
            return None
        return (rows[0].get('code') or '').strip().upper() if rows else None

    def _write_line(self, line_id: Any, values: Dict[str, Any]) -> None:
        sets, params = [], []
        if 'unit_price' in values:
            sets.append('unit_price = ?')
            params.append(values['unit_price'])
        if 'price_source' in values:
            sets.append('price_source = ?')
            params.append(values['price_source'])
        if 'price_trace' in values:
            sets.append('price_trace = ?')
            trace = values['price_trace']
            params.append(trace if isinstance(trace, str)
                          else json.dumps(trace, ensure_ascii=False))
        if not sets:
            return
        sets.append("updated_at = datetime('now')")
        params.append(line_id)
        self.ds.execute(
            f"UPDATE sales_order_lines SET {', '.join(sets)} WHERE id = ?", params)

    def _write_order(self, order_id: Any, values: Dict[str, Any]) -> None:
        if not values:
            return
        sets = [f'{key} = ?' for key in values]
        params = list(values.values())
        sets.append("updated_at = datetime('now')")
        params.append(order_id)
        self.ds.execute(
            f"UPDATE sales_orders SET {', '.join(sets)} WHERE id = ?", params)

    def _write_order_snapshot(self, order_id: Any,
                              resolved: Optional[Dict[str, Any]]) -> None:
        """回写抬头命中的价目表 / 过程快照（未命中则清空）。"""
        table = (resolved or {}).get('rate_table') or {}
        rule = (resolved or {}).get('rule') or {}
        self._write_order(order_id, {
            'price_list_id': table.get('id') if resolved and resolved.get('matched') else None,
            'pricing_procedure_id': (
                rule.get('calc_procedure_id')
                if resolved and resolved.get('matched') else None),
        })
