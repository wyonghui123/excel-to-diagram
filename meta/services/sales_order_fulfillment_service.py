# -*- coding: utf-8 -*-
"""销售订单履约状态 —— 计划行 → 订单行 → 订单抬头的派生回写。

依据: docs/superpowers/specs/2026-10-28-sales-order-fulfillment-status-writeback-spec.md v0.6
      §4.2 行派生规则 / §4.3 抬头派生规则 / §4.4 触发点 / §4.5 服务接口 / §4.8 不变式

口径（与 v145 迁移的回填 SQL 逐字同构，保证 INV-5「重算结果 = 现库」）:
  · 行：只看 `schedule_kind = 'delivery'` 的计划行，`cancelled` 视为不存在。
        无 delivery 计划行 → 行类型 `delivery_relevant` 为真则 `not_started`，
        否则 `not_applicable`（事实优先于配置，仅作历史数据兜底）；
        有 completed 且无 planned/confirmed → `fulfilled`；
        有 planned/confirmed 且无 completed → `not_started`；两者都有 → `partial`。
  · 抬头：只看 active 行（`status IN ('open','closed')`）。
        无任何行 → `not_started`；无 active 行 → `voided`；
        active 行全为 `not_applicable` → `not_applicable`；
        无 fulfilled → `not_started`；无 pending → `fulfilled`；否则 `partial`。

约束:
  · INV-1 唯一写入口：本服务是 `fulfillment_status` 的唯一写入方，
    拦截器 / 守卫 / 前端一律不得直接写该字段。
  · INV-2 派生顺序：行先写、抬头后写（`recompute_order` 内部即是此顺序）。
  · 事务边界由调用方控制（与 `SalesOrderAmountService` 同构，本服务不自行开事务）。
  · 幂等：同输入必同输出；只有值变化才落库，避免无谓的 updated_at 抖动。
  · billing / service 计划行不参与履约判定（开票与交付是两个正交事实）。
  · FR-011：每次派生确认都刷新 `fulfillment_derived_at`（UTC），作为巡检判定
    「陈旧数据」的水位；该时间戳刷新不改 `fulfillment_status`，也不动 `updated_at`。

覆写 `_load_*` / `_fetch_*` / `_write_line` / `_write_order` 即可注入测试数据。
"""

import calendar
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LINE_TABLE = 'sales_order_lines'
ORDER_TABLE = 'sales_orders'
SCHEDULE_TABLE = 'sales_order_schedules'
TYPE_TABLE = 'type_definitions'

# 审计水位取数（陈旧判定）：热表 + 冷表合并，IN 列表分片避免 SQLite 变量上限
AUDIT_TABLE = 'audit_logs'
AUDIT_ARCHIVE_TABLE = 'audit_logs_archive'
SQL_PARAM_CHUNK = 500
#: 审计时间与派生时间均取秒精度，留 1 秒容差避免同秒写入被误判为陈旧
STALE_TOLERANCE_SECONDS = 1

LINE_STATUS_CANCELLED = 'cancelled'
SCHEDULE_STATUS_CANCELLED = 'cancelled'
SCHEDULE_STATUS_COMPLETED = 'completed'
SCHEDULE_STATUS_PENDING = ('planned', 'confirmed')

FULFILL_NA = 'not_applicable'
FULFILL_NOT_STARTED = 'not_started'
FULFILL_PARTIAL = 'partial'
FULFILL_DONE = 'fulfilled'
FULFILL_VOIDED = 'voided'


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _chunks(seq: List[Any], size: int):
    for start in range(0, len(seq), size):
        yield seq[start:start + size]


def _norm_id(value: Any) -> Any:
    """审计/业务两侧 id 对齐：能转 int 就转 int，否则保留原值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _utc_epoch(value: Any) -> Optional[int]:
    """`YYYY-MM-DD HH:MM:SS`（UTC）→ epoch 秒；解析失败返回 None。"""
    if not value:
        return None
    text = str(value)[:19].replace('T', ' ')
    try:
        return calendar.timegm(time.strptime(text, '%Y-%m-%d %H:%M:%S'))
    except (TypeError, ValueError):
        return None


def _epoch_text(epoch: int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(epoch))


class SalesOrderFulfillmentService:
    """履约状态派生与回写（行 / 抬头 / 全量 / 取消级联）。"""

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
        if not self._load_order(order_id):
            return None

        lines = self._fetch_line_stats('l.order_id = ?', [order_id])
        computed: List[Dict[str, Any]] = []
        # INV-2：先算全部行、先写行，再算并写抬头
        for row in lines:
            status = self._line_status(row)
            self._write_if_changed_line(row, status)
            computed.append({'status': row.get('status'),
                             'fulfillment_status': status})

        order_status = self._order_status(computed)
        self._write_if_changed_order(order_id, order_status)
        return order_status

    # ---------------- 全量重算 ----------------

    def recompute_all(self, batch_size: int = 500) -> Dict[str, int]:
        """幂等全量重算（INV-5 巡检 / 修复入口）。"""
        size = batch_size if batch_size and batch_size > 0 else 500
        stats = {'orders': 0, 'lines_written': 0, 'orders_written': 0}
        offset = 0
        while True:
            rows = self.ds.query(
                'SELECT id FROM %s ORDER BY id LIMIT ? OFFSET ?' % ORDER_TABLE,
                [size, offset])
            if not rows:
                break
            for row in rows:
                lines = self._fetch_line_stats('l.order_id = ?', [row['id']])
                computed: List[Dict[str, Any]] = []
                for line in lines:
                    status = self._line_status(line)
                    if self._write_if_changed_line(line, status):
                        stats['lines_written'] += 1
                    computed.append({'status': line.get('status'),
                                     'fulfillment_status': status})
                order_status = self._order_status(computed)
                if self._write_if_changed_order(row['id'], order_status):
                    stats['orders_written'] += 1
                stats['orders'] += 1
            offset += len(rows)
        return stats

    # ---------------- 巡检（只读，FR-008） ----------------

    def check_drift(self, order_id: Any = None,
                    batch_size: int = 500) -> Dict[str, Any]:
        """巡检：列出 `fulfillment_status` 与派生值不符的行 / 抬头。

        只读，不写库。`order_id` 为空时全量扫描（按 order 分页以避免一次性载入）。
        返回: {'lines': [...], 'orders': [...], 'stale': {'lines','orders'},
               'scanned': {'orders','lines'}}
        """
        size = batch_size if batch_size and batch_size > 0 else 500
        report: Dict[str, Any] = {
            'lines': [], 'orders': [], 'stale': {'lines': [], 'orders': []},
            'scanned': {'orders': 0, 'lines': 0}}
        line_owner: Dict[Any, Any] = {}

        if not _blank(order_id):
            order_ids: List[Any] = [order_id]
        else:
            order_ids = []
            offset = 0
            while True:
                rows = self.ds.query(
                    'SELECT id FROM %s ORDER BY id LIMIT ? OFFSET ?'
                    % ORDER_TABLE, [size, offset])
                if not rows:
                    break
                order_ids.extend(row['id'] for row in rows)
                offset += len(rows)

        for oid in order_ids:
            lines = self._fetch_line_stats('l.order_id = ?', [oid])
            computed: List[Dict[str, Any]] = []
            for line in lines:
                status = self._line_status(line)
                computed.append({'status': line.get('status'),
                                 'fulfillment_status': status})
                report['scanned']['lines'] += 1
                line_owner[line.get('id')] = line.get('order_id', oid)
                if line.get('fulfillment_status') != status:
                    report['lines'].append({
                        'line_id': line.get('id'),
                        'order_id': line.get('order_id', oid),
                        'stored': line.get('fulfillment_status'),
                        'expected': status,
                    })
            order = self._load_order(oid)
            if not order:
                continue
            report['scanned']['orders'] += 1
            expected = self._order_status(computed)
            if order.get('fulfillment_status') != expected:
                report['orders'].append({
                    'order_id': oid,
                    'stored': order.get('fulfillment_status'),
                    'expected': expected,
                })
        report['stale'] = self._detect_stale(order_ids, line_owner)
        return report

    # ---------------- 取消级联（FR-014） ----------------

    def cascade_cancel(self, order_id: Any) -> Optional[Dict[str, Any]]:
        """订单取消级联：未终态订单行 / delivery 计划行置 cancelled，再派生一次。

        - 订单行：`status <> 'cancelled'` 的全部行（含 closed），
          使 INV-4「voided ⇔ 所有行 cancelled」成立；
        - 计划行：仅 `schedule_kind = 'delivery'` 且 `status IN ('planned','confirmed')`，
          `completed` 保持不动（已发生的交付事实不可改写，验收第 24 项）。
        事务由调用方与订单取消动作打包在一起。
        """
        if _blank(order_id):
            return None
        order = self._load_order(order_id)
        if not order:
            return None

        lines_cancelled = self._count(
            'SELECT COUNT(*) AS n FROM %s WHERE order_id = ? AND status <> ?'
            % LINE_TABLE, [order_id, LINE_STATUS_CANCELLED])
        if lines_cancelled:
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = datetime(\'now\') '
                'WHERE order_id = ? AND status <> ?' % LINE_TABLE,
                [LINE_STATUS_CANCELLED, order_id, LINE_STATUS_CANCELLED])

        schedules_cancelled = self._count(
            'SELECT COUNT(*) AS n FROM %s WHERE order_id = ? '
            'AND schedule_kind = \'delivery\' AND status IN (\'planned\', \'confirmed\')'
            % SCHEDULE_TABLE, [order_id])
        if schedules_cancelled:
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = datetime(\'now\') '
                'WHERE order_id = ? AND schedule_kind = \'delivery\' '
                'AND status IN (\'planned\', \'confirmed\')' % SCHEDULE_TABLE,
                [SCHEDULE_STATUS_CANCELLED, order_id])

        status = self.recompute_order(order_id)
        return {
            'lines_cancelled': lines_cancelled,
            'schedules_cancelled': schedules_cancelled,
            'fulfillment_status': status,
        }

    # ---------------- 派生规则 ----------------

    @staticmethod
    def _line_status(row: Dict[str, Any]) -> str:
        """§4.2：单行履约状态。"""
        if not row.get('active_cnt'):
            return FULFILL_NOT_STARTED if row.get('delivery_relevant', 1) \
                else FULFILL_NA
        if not row.get('done_cnt'):
            return FULFILL_NOT_STARTED
        if not row.get('pending_cnt'):
            return FULFILL_DONE
        return FULFILL_PARTIAL

    @staticmethod
    def _order_status(lines: List[Dict[str, Any]]) -> str:
        """§4.3：抬头履约状态。"""
        if not lines:
            return FULFILL_NOT_STARTED
        active = [x for x in lines if x.get('status') != LINE_STATUS_CANCELLED]
        if not active:
            return FULFILL_VOIDED
        done = sum(1 for x in active
                   if x.get('fulfillment_status') == FULFILL_DONE)
        pending = sum(1 for x in active
                      if x.get('fulfillment_status') in (FULFILL_NOT_STARTED,
                                                         FULFILL_PARTIAL))
        if not done and not pending:
            return FULFILL_NA
        if not done:
            return FULFILL_NOT_STARTED
        if not pending:
            return FULFILL_DONE
        return FULFILL_PARTIAL

    # ---------------- 查询 / 写入（可覆写，便于单测注入） ----------------

    def _load_order(self, order_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, fulfillment_status FROM %s WHERE id = ?' % ORDER_TABLE,
            [order_id])
        return rows[0] if rows else None

    def _fetch_line_stats(self, where: str, params: list) -> List[Dict[str, Any]]:
        """单条 SQL 聚合每行的 delivery 计划行统计（禁止逐行查询）。"""
        sql = (
            'SELECT l.id, l.order_id, l.status, l.fulfillment_status, '
            '       COALESCE(t.delivery_relevant, 1) AS delivery_relevant, '
            '       COALESCE(SUM(CASE WHEN s.status = ? THEN 1 ELSE 0 END), 0) '
            '           AS done_cnt, '
            '       COALESCE(SUM(CASE WHEN s.status IN (?, ?) THEN 1 ELSE 0 END), 0) '
            '           AS pending_cnt, '
            '       COALESCE(SUM(CASE WHEN s.status <> ? THEN 1 ELSE 0 END), 0) '
            '           AS active_cnt '
            'FROM %s l '
            'LEFT JOIN %s t ON t.id = l.line_type_id '
            'LEFT JOIN %s s ON s.line_id = l.id AND s.schedule_kind = \'delivery\' '
            'WHERE %s '
            'GROUP BY l.id, l.order_id, l.status, l.fulfillment_status, '
            '         t.delivery_relevant'
            % (LINE_TABLE, TYPE_TABLE, SCHEDULE_TABLE, where)
        )
        args = [SCHEDULE_STATUS_COMPLETED, SCHEDULE_STATUS_PENDING[0],
                SCHEDULE_STATUS_PENDING[1], SCHEDULE_STATUS_CANCELLED]
        return self.ds.query(sql, args + list(params))

    def _count(self, sql: str, params: list) -> int:
        rows = self.ds.query(sql, params)
        try:
            return int((rows[0] or {}).get('n') or 0) if rows else 0
        except (TypeError, ValueError):
            return 0

    def _write_if_changed_line(self, row: Dict[str, Any], status: str) -> bool:
        """派生值变化才写状态；但无论是否变化都刷新派生确认时间（FR-011）。

        返回值语义 = 「状态值是否发生变化」，用于 `recompute_all` 的落库计数。
        """
        if row.get('fulfillment_status') == status:
            self._touch_derived_at(LINE_TABLE, row['id'])
            return False
        self._write_line(row['id'], status)
        return True

    def _write_if_changed_order(self, order_id: Any, status: str) -> bool:
        order = self._load_order(order_id)
        if order and order.get('fulfillment_status') == status:
            self._touch_derived_at(ORDER_TABLE, order_id)
            return False
        self._write_order(order_id, status)
        return True

    def _write_line(self, line_id: Any, status: str) -> None:
        self.ds.execute(
            'UPDATE %s SET fulfillment_status = ?, '
            'fulfillment_derived_at = datetime(\'now\'), '
            'updated_at = datetime(\'now\') '
            'WHERE id = ?' % LINE_TABLE, [status, line_id])

    def _write_order(self, order_id: Any, status: str) -> None:
        self.ds.execute(
            'UPDATE %s SET fulfillment_status = ?, '
            'fulfillment_derived_at = datetime(\'now\'), '
            'updated_at = datetime(\'now\') '
            'WHERE id = ?' % ORDER_TABLE, [status, order_id])

    def _touch_derived_at(self, table: str, row_id: Any) -> None:
        """只刷新派生确认时间，不改状态值、不动 updated_at（避免无谓的审计抖动）。

        单独一条 UPDATE：不含 `SET fulfillment_status` 字面量，
        不影响 INV-1「唯一写入口」静态扫描。
        """
        self.ds.execute(
            'UPDATE %s SET fulfillment_derived_at = datetime(\'now\') '
            'WHERE id = ?' % table, [row_id])

    # ---------------- 陈旧判定（FR-011，只读） ----------------

    def _audit_ds(self):
        """审计表与业务表可能分库（APP_DB_ROUTING=1），取审计侧数据源。"""
        try:
            from meta.core.datasource import resolve_audit_data_source
            ds = resolve_audit_data_source(self.ds)
            return ds if ds is not None else self.ds
        except Exception as e:  # 路由模块不可用 → 回落业务库
            logger.debug('[fulfillment] 审计数据源解析失败，回落业务库: %s', e)
            return self.ds

    def _derived_at_map(self, table: str, ids: List[Any]) -> Dict[Any, Any]:
        """批量读 `fulfillment_derived_at`；缺列/缺表时返回空（整体降级）。"""
        result: Dict[Any, Any] = {}
        if not ids:
            return result
        keys = [_norm_id(x) for x in ids]
        for chunk in _chunks(keys, SQL_PARAM_CHUNK):
            sql = ('SELECT id, fulfillment_derived_at FROM %s WHERE id IN (%s)'
                   % (table, ','.join(['?'] * len(chunk))))
            try:
                rows = self.ds.query(sql, list(chunk))
            except Exception as e:
                logger.debug('[fulfillment] 读取 %s.fulfillment_derived_at 失败: %s',
                             table, e)
                return {}
            for row in rows or []:
                result[_norm_id(row.get('id'))] = row.get('fulfillment_derived_at')
        return result

    def _audit_watermarks(self, object_type: str, ids: List[Any],
                          parent: bool = False) -> Dict[Any, int]:
        """批量取审计变更水位（epoch 秒，任意 action 的最近一次）。

        `parent=True` 时按 `parent_object_type/parent_object_id` 归属取数
        （订单行 / 计划行的变更挂在订单名下）。热表 + 冷表合并取大。
        """
        if not ids:
            return {}
        id_col = 'parent_object_id' if parent else 'object_id'
        type_col = 'parent_object_type' if parent else 'object_type'
        ds = self._audit_ds()
        result: Dict[Any, int] = {}
        keys = [_norm_id(x) for x in ids]
        for table in (AUDIT_TABLE, AUDIT_ARCHIVE_TABLE):
            for chunk in _chunks(keys, SQL_PARAM_CHUNK):
                sql = (
                    "SELECT {id_col} AS oid, "
                    "MAX(strftime('%s', created_at, 'utc')) AS wm "
                    "FROM {table} WHERE {type_col} = ? AND {id_col} IN ({ph}) "
                    "GROUP BY {id_col}"
                ).format(id_col=id_col, table=table, type_col=type_col,
                         ph=','.join(['?'] * len(chunk)))
                try:
                    rows = ds.query(sql, [object_type] + list(chunk))
                except Exception as e:
                    logger.debug('[fulfillment] 审计水位不可用（%s）: %s', table, e)
                    continue
                for row in rows or []:
                    try:
                        oid = _norm_id(row.get('oid'))
                        wm = int(float(row.get('wm')))
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if wm > result.get(oid, 0):
                        result[oid] = wm
        return result

    def _schedule_ids_by_line(self, line_ids: List[Any]) -> Dict[Any, List[Any]]:
        """delivery 计划行 id 按订单行分组（只读；缺表返回空）。"""
        mapping: Dict[Any, List[Any]] = {}
        keys = [_norm_id(x) for x in line_ids]
        for chunk in _chunks(keys, SQL_PARAM_CHUNK):
            sql = ('SELECT id, line_id FROM %s WHERE line_id IN (%s) '
                   'AND schedule_kind = \'delivery\''
                   % (SCHEDULE_TABLE, ','.join(['?'] * len(chunk))))
            try:
                rows = self.ds.query(sql, list(chunk))
            except Exception as e:
                logger.debug('[fulfillment] 读取 delivery 计划行失败: %s', e)
                return {}
            for row in rows or []:
                mapping.setdefault(_norm_id(row.get('line_id')), []).append(
                    _norm_id(row.get('id')))
        return mapping

    def _detect_stale(self, order_ids: List[Any],
                      line_owner: Dict[Any, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """陈旧判定：审计水位晚于 `fulfillment_derived_at` 即视为陈旧。

        水位 = 该对象及其子对象最近一次审计变更（任意 action）；
        订单取自身 + 其下订单行/计划行，订单行取自身 + 其 delivery 计划行。
        列/表缺失、查询异常一律降级为空 —— 不影响漂移巡检主体。
        """
        stale: Dict[str, List[Dict[str, Any]]] = {'lines': [], 'orders': []}
        oids = [_norm_id(x) for x in order_ids if not _blank(x)]
        if not oids:
            return stale
        try:
            order_derived = self._derived_at_map(ORDER_TABLE, oids)
            order_wm = self._audit_watermarks('sales_order', oids)
            child_wm = self._audit_watermarks('sales_order', oids, parent=True)
        except Exception as e:
            logger.debug('[fulfillment] 订单陈旧判定降级: %s', e)
            return stale

        for oid in oids:
            derived_epoch = _utc_epoch(order_derived.get(oid))
            if derived_epoch is None:
                continue
            wm = max(order_wm.get(oid, 0), child_wm.get(oid, 0))
            if wm > derived_epoch + STALE_TOLERANCE_SECONDS:
                stale['orders'].append({
                    'order_id': oid,
                    'derived_at': order_derived.get(oid),
                    'changed_at': _epoch_text(wm),
                })

        line_ids = [_norm_id(x) for x in line_owner]
        owner = {_norm_id(k): v for k, v in line_owner.items()}
        if not line_ids:
            return stale
        try:
            line_derived = self._derived_at_map(LINE_TABLE, line_ids)
            line_wm = self._audit_watermarks('sales_order_line', line_ids)
            sched_map = self._schedule_ids_by_line(line_ids)
        except Exception as e:
            logger.debug('[fulfillment] 行陈旧判定降级: %s', e)
            return stale

        all_sched_ids = [sid for ids in sched_map.values() for sid in ids]
        sched_wm = self._audit_watermarks(
            'sales_order_schedule', all_sched_ids) if all_sched_ids else {}

        for line_id in line_ids:
            derived_epoch = _utc_epoch(line_derived.get(line_id))
            if derived_epoch is None:
                continue
            wm = line_wm.get(line_id, 0)
            for sid in sched_map.get(line_id, []):
                wm = max(wm, sched_wm.get(sid, 0))
            if wm > derived_epoch + STALE_TOLERANCE_SECONDS:
                stale['lines'].append({
                    'line_id': line_id,
                    'order_id': owner.get(line_id),
                    'derived_at': line_derived.get(line_id),
                    'changed_at': _epoch_text(wm),
                })
        return stale
