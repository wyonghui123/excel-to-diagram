# -*- coding: utf-8 -*-
"""采购订单履约状态 —— 到货计划行 / 收货量 → 订单行 → 订单抬头的派生回写。

依据:
  docs/specs/spec-purchase-order-object-model-2026-11-01.md §3（头字段 36/37）
      / §4（行字段 27/28）/ §10.4（计划行状态机）
  docs/specs/spec-receipt-object-model-2026-11-01.md §6 步 4 / §8.1

口径:
  · 行：只看未作废的计划行（`delivery` 与 `service` 都算；`service` 收货即验收，
    对应 R-RC-14）。已收量取计划行 `received_qty` 缓存之和；
    `received_total >= 行 qty`，或计划行全部 `completed` 且无 `planned/confirmed`
    （短收结案），行即 `received`。
    无有效计划行时：非交付相关行（`delivery_relevant=0`，如服务 / 费用 / 文本）
    视为 `closed`，不参与履约，避免整单被卡在 `open`；交付相关行仍为 `open`。
    `status='cancelled'` 的行一律 `closed`，不参与抬头聚合。
  · 抬头：只看 active 行（`status <> 'cancelled'`）。
    无行 → `open`；无 active 行 → `closed`；
    active 行全 `received / closed` → `received`（抬头自身 `status='closed'` 时为 `closed`）；
    有任一 `received` 或 `partially_received` → `partially_received`；否则 `open`。

约束:
  · INV-1 唯一写入口：本服务是采购订单 `fulfillment_status` 的唯一写入方，
    收货服务、拦截器、前端一律不得直接写该字段。
  · INV-2 派生顺序：行先写、抬头后写（`recompute_order` 内部即此顺序）。
  · 事务边界由调用方控制（与 `SalesOrderFulfillmentService` 同构，本服务不自行开事务）。
  · 幂等：同输入必同输出；状态值变化才写状态，无变化只刷新 `fulfillment_derived_at`
    （作为巡检「陈旧数据」的水位），不动 `updated_at`。

覆写 `_load_order` / `_fetch_line_stats` / `_write_line` / `_write_order`
即可注入测试数据。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ORDER_TABLE = 'purchase_orders'
LINE_TABLE = 'purchase_order_lines'
SCHEDULE_TABLE = 'purchase_order_schedules'
TYPE_TABLE = 'type_definitions'

LINE_STATUS_CANCELLED = 'cancelled'
ORDER_STATUS_CLOSED = 'closed'
SCHEDULE_STATUS_CANCELLED = 'cancelled'
SCHEDULE_STATUS_COMPLETED = 'completed'
SCHEDULE_STATUS_PENDING = ('planned', 'confirmed')

FULFILL_OPEN = 'open'
FULFILL_PARTIAL = 'partially_received'
FULFILL_DONE = 'received'
FULFILL_CLOSED = 'closed'


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class PurchaseOrderFulfillmentService:
    """采购订单履约状态派生与回写（行 / 抬头 / 全量）。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------------- 行 ----------------

    def recompute_line(self, line_id: Any) -> Optional[str]:
        """重算单行并落库，返回新状态；行不存在返回 None。"""
        if _blank(line_id):
            return None
        rows = self._fetch_line_stats('l.id = ?', [line_id])
        if not rows:
            return None
        row = rows[0]
        status = self._line_status(row)
        self._write_if_changed_line(row, status)
        return status

    # ---------------- 抬头（含所有行） ----------------

    def recompute_order(self, order_id: Any) -> Optional[str]:
        """重算该订单所有行 + 抬头，返回抬头新状态；订单不存在返回 None。"""
        if _blank(order_id):
            return None
        order = self._load_order(order_id)
        if not order:
            return None

        lines = self._fetch_line_stats('l.order_id = ?', [order_id])
        computed: List[Dict[str, Any]] = []
        # INV-2：先算全部行、先写行，再算并写抬头
        for row in lines:
            status = self._line_status(row)
            self._write_if_changed_line(row, status)
            computed.append({'status': row.get('status'),
                             'fulfillment_status': status})

        order_status = self._order_status(
            computed, order.get('status') == ORDER_STATUS_CLOSED)
        self._write_if_changed_order(order, order_status)
        return order_status

    # ---------------- 全量重算 ----------------

    def recompute_all(self, batch_size: int = 500) -> Dict[str, int]:
        """幂等全量重算（巡检 / 修复入口）。"""
        size = batch_size if batch_size and batch_size > 0 else 500
        stats = {'orders': 0, 'lines_written': 0, 'orders_written': 0}
        offset = 0
        while True:
            rows = self.ds.query(
                'SELECT id, status, fulfillment_status FROM %s '
                'ORDER BY id LIMIT ? OFFSET ?' % ORDER_TABLE, [size, offset])
            if not rows:
                break
            for order in rows:
                lines = self._fetch_line_stats('l.order_id = ?', [order['id']])
                computed: List[Dict[str, Any]] = []
                for line in lines:
                    status = self._line_status(line)
                    if self._write_if_changed_line(line, status):
                        stats['lines_written'] += 1
                    computed.append({'status': line.get('status'),
                                     'fulfillment_status': status})
                order_status = self._order_status(
                    computed, order.get('status') == ORDER_STATUS_CLOSED)
                if self._write_if_changed_order(order, order_status):
                    stats['orders_written'] += 1
                stats['orders'] += 1
            offset += len(rows)
        return stats

    # ---------------- 派生规则 ----------------

    @staticmethod
    def _line_status(row: Dict[str, Any]) -> str:
        """单行履约状态（见模块 docstring 口径）。"""
        if row.get('status') == LINE_STATUS_CANCELLED:
            return FULFILL_CLOSED
        if not row.get('active_cnt'):
            return FULFILL_OPEN if row.get('delivery_relevant', 1) else FULFILL_CLOSED

        line_qty = _num(row.get('qty'))
        received_total = _num(row.get('received_total'))
        if line_qty > 0 and received_total >= line_qty:
            return FULFILL_DONE
        if row.get('done_cnt') and not row.get('pending_cnt'):
            return FULFILL_DONE
        if row.get('received_any') or row.get('done_cnt'):
            return FULFILL_PARTIAL
        return FULFILL_OPEN

    @staticmethod
    def _order_status(lines: List[Dict[str, Any]], order_closed: bool = False) -> str:
        """抬头履约状态（见模块 docstring 口径）。"""
        if not lines:
            return FULFILL_OPEN
        active = [x for x in lines if x.get('status') != LINE_STATUS_CANCELLED]
        if not active:
            return FULFILL_CLOSED
        done = sum(1 for x in active
                   if x.get('fulfillment_status') in (FULFILL_DONE, FULFILL_CLOSED))
        if done == len(active):
            return FULFILL_CLOSED if order_closed else FULFILL_DONE
        if done:
            return FULFILL_PARTIAL
        partial = sum(1 for x in active
                      if x.get('fulfillment_status') == FULFILL_PARTIAL)
        return FULFILL_PARTIAL if partial else FULFILL_OPEN

    # ---------------- 查询 / 写入（可覆写，便于单测注入） ----------------

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, status, fulfillment_status FROM %s WHERE id = ?'
            % ORDER_TABLE, [order_id])
        return rows[0] if rows else None

    def _fetch_line_stats(self, where: str, params: list) -> List[Dict[str, Any]]:
        """单条 SQL 聚合每行的计划行统计（禁止逐行查询）。"""
        sql = (
            'SELECT l.id, l.order_id, l.status, l.fulfillment_status, l.qty, '
            '       COALESCE(t.delivery_relevant, 1) AS delivery_relevant, '
            '       COALESCE(SUM(CASE WHEN s.status = ? THEN 1 ELSE 0 END), 0) '
            '           AS done_cnt, '
            '       COALESCE(SUM(CASE WHEN s.status IN (?, ?) THEN 1 ELSE 0 END), 0) '
            '           AS pending_cnt, '
            '       COALESCE(SUM(CASE WHEN s.status <> ? THEN 1 ELSE 0 END), 0) '
            '           AS active_cnt, '
            '       COALESCE(SUM(CASE WHEN s.status <> ? '
            '                    THEN COALESCE(s.received_qty, 0) ELSE 0 END), 0) '
            '           AS received_total, '
            '       COALESCE(MAX(CASE WHEN s.status <> ? '
            '                    AND COALESCE(s.received_qty, 0) > 0 '
            '                    THEN 1 ELSE 0 END), 0) AS received_any '
            'FROM %s l '
            'LEFT JOIN %s t ON t.id = l.line_type_id '
            'LEFT JOIN %s s ON s.line_id = l.id '
            'WHERE %s '
            'GROUP BY l.id, l.order_id, l.status, l.fulfillment_status, l.qty, '
            '         t.delivery_relevant'
            % (LINE_TABLE, TYPE_TABLE, SCHEDULE_TABLE, where)
        )
        args = [SCHEDULE_STATUS_COMPLETED, SCHEDULE_STATUS_PENDING[0],
                SCHEDULE_STATUS_PENDING[1], SCHEDULE_STATUS_CANCELLED,
                SCHEDULE_STATUS_CANCELLED, SCHEDULE_STATUS_CANCELLED]
        return self.ds.query(sql, args + list(params))

    def _write_if_changed_line(self, row: Dict[str, Any], status: str) -> bool:
        """派生值变化才写状态；无变化只刷新派生确认时间。"""
        if row.get('fulfillment_status') == status:
            self._touch_derived_at(LINE_TABLE, row['id'])
            return False
        self._write_line(row['id'], status)
        return True

    def _write_if_changed_order(self, order: Dict[str, Any], status: str) -> bool:
        if order.get('fulfillment_status') == status:
            self._touch_derived_at(ORDER_TABLE, order['id'])
            return False
        self._write_order(order['id'], status)
        return True

    def _write_line(self, line_id: Any, status: str) -> None:
        self.ds.execute(
            'UPDATE %s SET fulfillment_status = ?, '
            "fulfillment_derived_at = datetime('now'), "
            "updated_at = datetime('now') "
            'WHERE id = ?' % LINE_TABLE, [status, line_id])

    def _write_order(self, order_id: Any, status: str) -> None:
        self.ds.execute(
            'UPDATE %s SET fulfillment_status = ?, '
            "fulfillment_derived_at = datetime('now'), "
            "updated_at = datetime('now') "
            'WHERE id = ?' % ORDER_TABLE, [status, order_id])

    def _touch_derived_at(self, table: str, row_id: Any) -> None:
        """只刷新派生确认时间，不改状态值、不动 updated_at。"""
        self.ds.execute(
            'UPDATE %s SET fulfillment_derived_at = datetime(\'now\') '
            'WHERE id = ?' % table, [row_id])
