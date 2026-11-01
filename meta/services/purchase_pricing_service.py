# -*- coding: utf-8 -*-
"""采购取价服务（M3）。

依据：`docs/specs/spec-purchase-order-object-model-2026-11-01.md` §4.3 / §4.4 / §14 步骤 6B。

解析顺序（Oracle 默认寻源序的落地）：
    本地协议 > 全局协议 > 供应商报价 > 价目表 > 最近采购价(last_po) > 标准成本 > 人工

口径：
  · 协议与报价走 `rate_tables`（`scope_bo='purchase_order'`），阶梯字段
    `qty_from / qty_to / ship_to_location_id`；**同条件多档命中取最低价**。
  · 协议归属由 `purchase_pricing_determinations.agreement_scope ∈ local/global`
    显式表达，不靠排序猜。
  · `last_po` 为**只读派生**：按 `supplier_party_id + item_id` 取最近一张
    `confirmed / closed` PO 的行单价，不落任何新表。
  · `price_break_cumulative` 必须显式配置；仅当同表多档存在歧义时才强制要求，
    避免无阶梯场景被误拦。
  · 命中即写行 `unit_price / price_source / price_trace`，并写头 `price_list_id`；
    无任何来源命中时回落 `manual`（`price_trace` 为空）。
"""

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SOURCE_MANUAL = 'manual'
SOURCE_AGREEMENT = 'agreement'
SOURCE_QUOTATION = 'quotation'
SOURCE_RATE_TABLE = 'rate_table'
SOURCE_LAST_PO = 'last_po'
SOURCE_STANDARD_COST = 'standard_cost'

PRICE_BREAK_PARAM = 'price_break_cumulative'

#: 评定顺序（值越小越优先）
SOURCE_ORDER = (
    SOURCE_AGREEMENT, SOURCE_QUOTATION, SOURCE_RATE_TABLE,
    SOURCE_LAST_PO, SOURCE_STANDARD_COST,
)

_QUOTATION_TYPES = ('quotation', 'quote')
_AGREEMENT_TYPES = ('agreement', 'bpa', 'contract')


class PurchasePricingError(ValueError):
    """采购取价失败（配置歧义 / 阶梯参数缺失等）。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _num(value: Any) -> Optional[float]:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_key(value: Any) -> Optional[str]:
    if _blank(value):
        return None
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m-%d')
    text = str(value).strip()
    return text[:10] if text else None


def _loads(value: Any, default):
    if _blank(value):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class PurchasePricingService:
    """采购行取价与整单重取。覆写 `_load_order/_load_line/_write_*` 可注入测试数据。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def price_line(self, line_id: Any, *, force: bool = False,
                   order: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """对单行取价并写回；不满足触发前提时返回 None。"""
        line = self._load_line(line_id)
        if not line:
            return None
        order = order or self._load_order(line.get('order_id'))
        if not order:
            return None
        if str(order.get('status') or '').lower() != 'draft':
            return None
        if not force and str(line.get('price_source') or '') == SOURCE_MANUAL:
            return None
        if _blank(line.get('item_id')):
            return None
        qty = _num(line.get('qty'))
        if qty is None or qty <= 0:
            return None

        item_id = line.get('item_id')
        price_date = _date_key(order.get('price_date')) or _date_key(order.get('order_date'))
        location_id = line.get('deliver_to_location_id') or order.get('deliver_to_location_id')
        currency = self._currency_code(order.get('currency_id'))
        trace: Dict[str, Any] = {
            'inputs': {
                'item_id': item_id,
                'qty': qty,
                'supplier_party_id': order.get('supplier_party_id'),
                'purchase_org_id': order.get('purchase_org_id'),
                'document_type_id': order.get('document_type_id'),
                'price_date': price_date,
                'deliver_to_location_id': location_id,
                'currency': currency,
            },
            'skipped': [],
        }

        hit = self._resolve(order, line, qty, price_date, location_id, currency, trace)
        if hit is None:
            # R-PO-18：无来源命中 → 只允许 manual 且无 trace
            self._write_line(line_id, {
                'price_source': SOURCE_MANUAL, 'price_trace': None})
            return {
                'line_id': line_id,
                'price_source': SOURCE_MANUAL,
                'unit_price': line.get('unit_price'),
                'price_trace': None,
                'trace': trace,
            }

        values = {
            'unit_price': hit['unit_price'],
            'price_source': hit['price_source'],
            'price_trace': json.dumps(trace, ensure_ascii=False),
        }
        self._write_line(line_id, values)
        if hit.get('rate_table_id') not in (None, ''):
            self._write_order(order.get('id'), {'price_list_id': hit['rate_table_id']})
        return {
            'line_id': line_id,
            'price_source': hit['price_source'],
            'unit_price': hit['unit_price'],
            'price_trace': trace,
        }

    def reprice_order(self, order_id: Any, *, force: bool = False,
                      strict: bool = False) -> Optional[Dict[str, Any]]:
        """重取整单非手工行；`strict=True` 时非草稿直接报错。"""
        order = self._load_order(order_id)
        if not order:
            return None
        if str(order.get('status') or '').lower() != 'draft':
            if strict:
                raise PurchasePricingError(
                    '仅草稿态采购订单允许重新取价',
                    field_name='status', rule='order_not_draft')
            return None
        counts: Dict[str, int] = {}
        for row in self._lines_for_order(order_id):
            result = self.price_line(row.get('id'), force=force, order=order)
            if not result:
                continue
            source = result.get('price_source') or 'none'
            counts[source] = counts.get(source, 0) + 1
        return {'order_id': order_id, 'counts': counts}

    def mark_manual(self, line_id: Any) -> None:
        """人工录入单价 → 打标，后续自动取价跳过该行。"""
        self._write_line(line_id, {'price_source': SOURCE_MANUAL})

    # ------------------------------------------------------------------
    # 来源解析
    # ------------------------------------------------------------------
    def _resolve(self, order: Dict[str, Any], line: Dict[str, Any], qty: float,
                 price_date: Optional[str], location_id: Any, currency: Optional[str],
                 trace: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        item_id = line.get('item_id')
        for scope in ('local', 'global'):
            hit = self._resolve_agreement(
                order, item_id, qty, price_date, location_id, currency, scope, trace)
            if hit:
                return hit
        for source, table_filter in (
                (SOURCE_QUOTATION, self._quotation_tables),
                (SOURCE_RATE_TABLE, self._price_list_tables)):
            hit = self._resolve_from_tables(
                order, table_filter, source, item_id, qty, price_date,
                location_id, currency, trace)
            if hit:
                return hit
        hit = self._resolve_last_po(order, item_id, currency, trace)
        if hit:
            return hit
        trace['result'] = {'source': None, 'reason': 'no_source_matched'}
        return None

    def _resolve_agreement(self, order, item_id, qty, price_date, location_id,
                           currency, scope, trace) -> Optional[Dict[str, Any]]:
        rows = self._query(
            "SELECT id, code, seq, rate_table_id, purchase_org_id, document_type_id, "
            "       supplier_party_id, base_date_from, base_date_to "
            "  FROM purchase_pricing_determinations "
            " WHERE status = 'active' AND agreement_scope = ? "
            "   AND (base_date_from IS NULL OR base_date_from <= ?) "
            "   AND (base_date_to IS NULL OR base_date_to >= ?) "
            " ORDER BY (supplier_party_id IS NOT NULL) DESC, "
            "          (purchase_org_id IS NOT NULL) DESC, seq ASC, id ASC",
            [scope, price_date, price_date])
        if not rows:
            return None

        def _matches(row, key, value):
            target = row.get(key)
            return target in (None, '') or (value not in (None, '') and target == value)

        for row in rows:
            if not _matches(row, 'purchase_org_id', order.get('purchase_org_id')):
                continue
            if not _matches(row, 'document_type_id', order.get('document_type_id')):
                continue
            if not _matches(row, 'supplier_party_id', order.get('supplier_party_id')):
                continue
            hit = self._pick_from_table(
                row.get('rate_table_id'), SOURCE_AGREEMENT, item_id, qty, price_date,
                location_id, currency, trace)
            if hit:
                hit['agreement_scope'] = scope
                hit['determination_id'] = row.get('id')
                trace['result'] = {
                    'source': SOURCE_AGREEMENT, 'scope': scope,
                    'determination_id': row.get('id'), 'code': row.get('code'),
                    'rate_table_id': row.get('rate_table_id'),
                }
                return hit
            trace['skipped'].append({
                'source': SOURCE_AGREEMENT, 'scope': scope,
                'determination_id': row.get('id'),
                'reason': 'rate_table_no_match'})
        return None

    def _resolve_from_tables(self, order, table_filter, source, item_id, qty,
                             price_date, location_id, currency, trace) -> Optional[Dict[str, Any]]:
        tables = table_filter(order)
        for table in tables:
            hit = self._pick_from_table(
                table.get('id'), source, item_id, qty, price_date,
                location_id, currency, trace)
            if hit:
                trace['result'] = {
                    'source': source, 'rate_table_id': table.get('id'),
                    'code': table.get('code')}
                return hit
            trace['skipped'].append({
                'source': source, 'rate_table_id': table.get('id'),
                'reason': 'rate_table_no_match'})
        return None

    def _quotation_tables(self, order) -> List[Dict[str, Any]]:
        return self._scoped_tables(order, _QUOTATION_TYPES)

    def _price_list_tables(self, order) -> List[Dict[str, Any]]:
        return self._scoped_tables(order, None)

    def _scoped_tables(self, order, types: Optional[tuple]) -> List[Dict[str, Any]]:
        sql = ("SELECT id, code, name, type, currency, owner_org_id "
               "  FROM rate_tables WHERE status = 'approved' "
               "   AND COALESCE(scope_bo, 'sales_order') = 'purchase_order'")
        params: List[Any] = []
        if types:
            sql += " AND COALESCE(type, 'standard') IN ({0})".format(
                ', '.join('?' * len(types)))
            params.extend(types)
        else:
            # 价目表 = 非协议 / 非报价的 approved 采购表
            placeholders = ', '.join('?' * (len(_QUOTATION_TYPES) + len(_AGREEMENT_TYPES)))
            sql += " AND COALESCE(type, 'standard') NOT IN ({0})".format(placeholders)
            params.extend(list(_QUOTATION_TYPES) + list(_AGREEMENT_TYPES))
        sql += " ORDER BY (owner_org_id IS NOT NULL) DESC, updated_at DESC, id DESC"
        rows = self._query(sql, params)
        org_id = order.get('purchase_org_id')
        matched = [r for r in rows if r.get('owner_org_id') in (None, '') or r.get('owner_org_id') == org_id]
        return matched

    def _pick_from_table(self, rate_table_id, source, item_id, qty, price_date,
                         location_id, currency, trace) -> Optional[Dict[str, Any]]:
        if rate_table_id in (None, ''):
            return None
        records = self._query(
            "SELECT id, code, keys, rate, rate_qty, currency, priority, "
            "       qty_from, qty_to, ship_to_location_id, valid_from, valid_to "
            "  FROM rate_records "
            " WHERE rate_table_id = ? AND status = 'active' "
            " ORDER BY priority ASC, id ASC", [rate_table_id])
        candidates = []
        for rec in records:
            if not self._record_matches(rec, item_id, currency, price_date,
                                        location_id, trace, source):
                continue
            candidates.append(rec)
        if not candidates:
            return None

        banded = [r for r in candidates if r.get('qty_from') not in (None, '')]
        plain = [r for r in candidates if r.get('qty_from') in (None, '')]
        chosen = None
        if banded:
            matched = self._filter_by_band(banded, qty, source, rate_table_id, trace)
            if matched:
                chosen = self._lowest_price(matched)
        if chosen is None and plain:
            chosen = self._lowest_price(plain)
        if chosen is None:
            return None

        rate_qty = _num(chosen.get('rate_qty')) or 1.0
        unit_price = _num(chosen.get('rate'))
        if unit_price is None:
            return None
        unit_price = unit_price / rate_qty if rate_qty else unit_price
        return {
            'price_source': source,
            'unit_price': round(unit_price, 6),
            'rate_table_id': rate_table_id,
            'rate_record_id': chosen.get('id'),
            'qty_break': {'from': chosen.get('qty_from'), 'to': chosen.get('qty_to')},
        }

    def _record_matches(self, rec, item_id, currency, price_date, location_id,
                        trace, source) -> bool:
        keys = _loads(rec.get('keys'), {})
        if not isinstance(keys, dict):
            return False
        for key, value in keys.items():
            if key in ('item_id', 'item', 'product_id'):
                if value not in (None, '') and str(value) != str(item_id):
                    return False
            elif key in ('supplier_party_id', 'party_id'):
                trace.setdefault('record_keys', {})[key] = value
            # 其余维度键（组织 / 客户等）在采购侧不做收窄，交给上层规则
        rec_currency = str(rec.get('currency') or '').strip().upper()
        if rec_currency and currency and rec_currency != str(currency).upper():
            return False
        valid_from = _date_key(rec.get('valid_from'))
        valid_to = _date_key(rec.get('valid_to'))
        if valid_from and price_date and valid_from > price_date:
            return False
        if valid_to and price_date and valid_to <= price_date:
            return False
        rec_location = rec.get('ship_to_location_id')
        if rec_location not in (None, '') and location_id not in (None, ''):
            if rec_location != location_id:
                return False
        elif rec_location not in (None, '') and _blank(location_id):
            return False
        return True

    def _filter_by_band(self, banded, qty, source, rate_table_id, trace) -> List[Dict[str, Any]]:
        """按 `price_break_cumulative` 选档：false=本次数量，true=累计数量。"""
        cumulative = self._price_break_cumulative()
        if cumulative is None:
            # 是否真的存在「多档同时覆盖本次数量」的歧义
            ambiguous = self._ambiguous_bands(banded, qty)
            if ambiguous:
                raise PurchasePricingError(
                    '价格阶梯存在多档命中，必须显式配置控制参数 '
                    'price_break_cumulative（true=累计数量 / false=本次数量）',
                    field_name='price_break_cumulative',
                    rule='price_break_cumulative_missing')
            cumulative = False
        if cumulative:
            qty = self._cumulative_qty(trace, qty)
        trace['qty_for_break'] = qty
        trace['price_break_cumulative'] = bool(cumulative)
        matched = []
        for rec in banded:
            lower = _num(rec.get('qty_from'))
            upper = _num(rec.get('qty_to'))
            if lower is not None and qty < lower:
                continue
            if upper is not None and qty > upper:
                continue
            matched.append(rec)
        return matched

    @staticmethod
    def _ambiguous_bands(banded, qty) -> bool:
        covering = 0
        for rec in banded:
            lower = _num(rec.get('qty_from'))
            upper = _num(rec.get('qty_to'))
            if lower is not None and qty < lower:
                continue
            if upper is not None and qty > upper:
                continue
            covering += 1
        return covering > 1

    def _price_break_cumulative(self) -> Optional[bool]:
        try:
            from meta.services.control_parameter_service import ControlParameterResolver
            value = ControlParameterResolver(self.ds).resolve(PRICE_BREAK_PARAM, {})
        except Exception as e:  # 参数表缺失 → 视为未配置
            logger.warning('[purchase_pricing] 读取 %s 失败: %s', PRICE_BREAK_PARAM, e)
            return None
        if value is None or isinstance(value, str):
            if isinstance(value, str) and value.strip().lower() in ('true', '1', 'yes'):
                return True
            if isinstance(value, str) and value.strip().lower() in ('false', '0', 'no'):
                return False
            return None
        return bool(value)

    def _cumulative_qty(self, trace, qty) -> float:
        inputs = trace.get('inputs') or {}
        try:
            rows = self._query(
                "SELECT COALESCE(SUM(l.qty), 0) AS total "
                "  FROM purchase_order_lines l "
                "  JOIN purchase_orders o ON o.id = l.order_id "
                " WHERE l.item_id = ? AND o.supplier_party_id = ? "
                "   AND o.status IN ('confirmed', 'closed') "
                "   AND l.status IN ('open', 'closed')",
                [inputs.get('item_id'), inputs.get('supplier_party_id')])
        except Exception as e:
            logger.warning('[purchase_pricing] 累计数量查询失败: %s', e)
            return qty
        total = _num(rows[0].get('total')) if rows else 0.0
        return (total or 0.0) + qty

    @staticmethod
    def _lowest_price(records) -> Optional[Dict[str, Any]]:
        best = None
        best_price = None
        for rec in records:
            rate = _num(rec.get('rate'))
            if rate is None:
                continue
            rate_qty = _num(rec.get('rate_qty')) or 1.0
            price = rate / rate_qty if rate_qty else rate
            if best_price is None or price < best_price:
                best, best_price = rec, price
        return best

    def _resolve_last_po(self, order, item_id, currency, trace) -> Optional[Dict[str, Any]]:
        rows = self._query(
            "SELECT l.id AS line_id, l.unit_price, l.price_source, "
            "       o.id AS order_id, o.order_no, o.confirmed_date, o.order_date "
            "  FROM purchase_order_lines l "
            "  JOIN purchase_orders o ON o.id = l.order_id "
            " WHERE l.item_id = ? AND o.supplier_party_id = ? "
            "   AND o.status IN ('confirmed', 'closed') "
            "   AND l.status IN ('open', 'closed') "
            "   AND o.id <> ? AND l.unit_price IS NOT NULL "
            " ORDER BY COALESCE(o.confirmed_date, o.order_date) DESC, l.id DESC "
            " LIMIT 1",
            [item_id, order.get('supplier_party_id'), order.get('id') or 0])
        if not rows:
            return None
        price = _num(rows[0].get('unit_price'))
        if price is None:
            return None
        trace['result'] = {
            'source': SOURCE_LAST_PO,
            'order_id': rows[0].get('order_id'),
            'order_no': rows[0].get('order_no'),
            'line_id': rows[0].get('line_id'),
        }
        return {
            'price_source': SOURCE_LAST_PO,
            'unit_price': price,
            'rate_table_id': None,
            'order_id': rows[0].get('order_id'),
        }

    # ------------------------------------------------------------------
    # 查询 / 写入（可覆写，便于单测注入）
    # ------------------------------------------------------------------
    def _query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        return self.ds.query(sql, params or [])

    def _load_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        rows = self._query(
            'SELECT id, order_id, item_id, qty, uom_id, unit_price, price_source, '
            '       deliver_to_location_id '
            'FROM purchase_order_lines WHERE id = ?', [line_id])
        return rows[0] if rows else None

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self._query(
            'SELECT id, order_no, status, order_date, price_date, currency_id, '
            '       supplier_party_id, purchase_org_id, document_type_id, '
            '       deliver_to_location_id '
            'FROM purchase_orders WHERE id = ?', [order_id])
        return rows[0] if rows else None

    def _lines_for_order(self, order_id: Any) -> List[Dict[str, Any]]:
        return self._query(
            'SELECT id, price_source FROM purchase_order_lines '
            'WHERE order_id = ? AND status <> ?', [order_id, 'cancelled'])

    def _currency_code(self, currency_id: Any) -> Optional[str]:
        if currency_id in (None, ''):
            return None
        rows = self._query(
            'SELECT code FROM currencies WHERE id = ?', [currency_id])
        return str(rows[0].get('code')).strip() if rows and rows[0].get('code') else None

    def _write_line(self, line_id: Any, values: Dict[str, Any]) -> None:
        if not values:
            return
        columns = ', '.join('{0} = ?'.format(k) for k in values)
        self.ds.execute(
            'UPDATE purchase_order_lines SET {0} WHERE id = ?'.format(columns),
            list(values.values()) + [line_id])

    def _write_order(self, order_id: Any, values: Dict[str, Any]) -> None:
        if not values or order_id in (None, ''):
            return
        columns = ', '.join('{0} = ?'.format(k) for k in values)
        self.ds.execute(
            'UPDATE purchase_orders SET {0} WHERE id = ?'.format(columns),
            list(values.values()) + [order_id])
