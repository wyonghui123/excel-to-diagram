# -*- coding: utf-8 -*-
"""库存预留与 ATP 服务 —— INV-2 S2 预留量唯一事实源。

依据:
  docs/specs/inv2-reservation-atp/spec.md §3.3 / §4.2 / §7

口径:
  ① inventory_reservations 是预留量的唯一事实源；
     inventory_balances.qty_reserved 只是投影，由 rebuild_reserved_qty 回写。
  ② reservation_key 幂等：重复创建返回既有预留，不重复占用。
  ③ 状态机 open → partially_fulfilled → fulfilled / cancelled / closed / expired；
     closed 为终止履行并保留历史，与 cancelled（承诺作废）区分。
  ④ available_on_hand(segment) = 段内 on_hand - 活跃预留未核销量。
  ⑤ hard 钉在目标段扣减且不得超订；soft 允许先预留后补货（MTO 标准）。
  ⑥ 活跃判定含时间派生：valid_to 已过的预留读取时即不计入可用量。
  ⑦ atp(include_inbound=True) 扣减该段已 hard 钉住的未收货未来供应；
     available_on_hand 的含在途分支仍未实现（报 ATP_INBOUND_UNSUPPORTED）。
  ⑧ 工单组件以 work_order_component 为需求节点建 soft 预留；组件是独立
     物料需求，与来源 SO 行（成品）的预留不重复计量。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.services.inventory_document_sequence import next_document_no
from meta.services.inventory_guard_service import InventoryError
from meta.services.stock_segment_service import (
    DEFAULT_SEGMENT, SEGMENT_COLUMNS, StockSegmentService,
)

logger = logging.getLogger(__name__)

RESERVATION_TABLE = 'inventory_reservations'
BAL_TABLE = 'inventory_balances'
SEQUENCE_CODE = 'RSV'
DEFAULT_PATTERN = 'RSV-{DATE:yyyymm}-{SEQ:6}'

STATUS_OPEN = 'open'
STATUS_PARTIALLY_FULFILLED = 'partially_fulfilled'
STATUS_FULFILLED = 'fulfilled'
STATUS_CANCELLED = 'cancelled'
STATUS_CLOSED = 'closed'
STATUS_EXPIRED = 'expired'

ACTIVE_STATUSES = (STATUS_OPEN, STATUS_PARTIALLY_FULFILLED)

PEG_HARD = 'hard'
PEG_SOFT = 'soft'

DEMAND_WORK_ORDER_COMPONENT = 'work_order_component'
WO_SOURCE_TYPE = 'work_order'
WO_COMPONENT_KEY_PREFIX = 'WO-COMP'
#: 工单进入这两个终态后不再需要投料，组件承诺全部释放
WO_COMPONENT_RELEASE_STATUSES = ('Cancelled', 'Closed')

INV_RESERVATION_QTY_EXCEEDED = 'INV_RESERVATION_QTY_EXCEEDED'
INV_RESERVATION_NOT_FOUND = 'INV_RESERVATION_NOT_FOUND'
INV_RESERVATION_STATE_INVALID = 'INV_RESERVATION_STATE_INVALID'
INV_HARD_PEG_CONFLICT = 'INV_HARD_PEG_CONFLICT'
INV_RESERVATION_EXCEEDS_DEMAND = 'INV_RESERVATION_EXCEEDS_DEMAND'
INV_RESERVATION_CLOSED = 'INV_RESERVATION_CLOSED'
INV_RESERVATION_ACTIVE_ON_CLOSE = 'INV_RESERVATION_ACTIVE_ON_CLOSE'
INV_DEMAND_QTY_UNKNOWN = 'INV_DEMAND_QTY_UNKNOWN'
ATP_INBOUND_UNSUPPORTED = 'ATP_INBOUND_UNSUPPORTED'

#: 可解析需求量的节点 → (表, 数量列)。不可解析时告警放行。
DEMAND_QTY_SOURCES = {
    'sales_order_line': ('sales_order_lines', 'qty'),
    DEMAND_WORK_ORDER_COMPONENT: ('work_order_components', 'qty_required'),
}

TRACE_TABLE = 'demand_trace_links'
TRACE_PEGGING = 'pegging'
#: 未收货的未来供应：数量只由 hard pegging 陈述
FUTURE_SUPPLY_TYPES = ('purchase_order_line', 'work_order',
                       'transfer_order_line')


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _to_int(value: Any) -> int:
    if value is None or value == '':
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> float:
    if value is None or value == '':
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class InventoryReservationService:
    """预留创建/释放/核销/过期与按段 ATP。构造函数可注入 data_source。"""

    def __init__(self, data_source, posting_service=None,
                 segment_service=None):
        self.ds = data_source
        self._posting = posting_service
        self._segments = segment_service

    # ------------------------------------------------------------------
    # 内部依赖
    # ------------------------------------------------------------------
    def _posting_service(self):
        if self._posting is not None:
            return self._posting
        from meta.services.inventory_posting_service import (
            InventoryPostingService,
        )
        self._posting = InventoryPostingService(self.ds)
        return self._posting

    def _segment_service(self):
        if self._segments is not None:
            return self._segments
        self._segments = StockSegmentService(self.ds)
        return self._segments

    def _table_ready(self) -> bool:
        try:
            return bool(self.ds.query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                [RESERVATION_TABLE]))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------
    def create_reservation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """创建预留；reservation_key 幂等，重复调用返回既有行。"""
        if not self._table_ready():
            raise InventoryError(
                'INV_SEQUENCE_MISSING', '库存预留表未建立（v205 未迁移）')
        data = dict(payload or {})
        key = str(data.get('reservation_key') or '').strip()
        if not key:
            raise InventoryError('INV_SOURCE_REQUIRED',
                                 '预留缺少 reservation_key 幂等键')
        existing = self._by_key(key)
        if existing:
            logger.info('[inv2] 预留幂等命中 key=%s id=%s',
                        key, existing['id'])
            return {'reservation': existing, 'created': False}

        org_id = _to_int(data.get('org_id'))
        item_id = _to_int(data.get('item_id'))
        uom_id = _to_int(data.get('uom_id')) or self._base_uom(item_id)
        demand_type = str(data.get('demand_object_type') or '').strip()
        demand_id = _to_int(data.get('demand_object_id'))
        if not org_id or not item_id:
            raise InventoryError(
                'INV_ENTRY_INVALID', '预留缺少库存组织或物料',
                {'org_id': org_id, 'item_id': item_id})
        if not uom_id:
            raise InventoryError(
                'INV_UOM_INVALID', '预留缺少单位且物料未维护基本单位',
                {'item_id': item_id})
        if not demand_type or not demand_id:
            raise InventoryError(
                'INV_ENTRY_INVALID', '预留缺少需求节点类型或对象',
                {'demand_object_type': demand_type,
                 'demand_object_id': demand_id})

        qty = _num(data.get('qty_reserved'))
        if qty <= 0:
            raise InventoryError(
                INV_RESERVATION_QTY_EXCEEDED, '预留数量必须大于 0',
                {'qty_reserved': data.get('qty_reserved')})

        segment = self._resolve_segment(data)
        peg_type = str(data.get('peg_type') or PEG_SOFT).strip().lower()
        if peg_type not in (PEG_HARD, PEG_SOFT):
            raise InventoryError(
                'INV_ENTRY_INVALID', '钉类型只允许 hard / soft',
                {'peg_type': peg_type})

        self._assert_demand_capacity(
            demand_type, demand_id,
            _to_int(data.get('demand_line_id')), qty)

        if peg_type == PEG_HARD:
            self._assert_hard_peg(segment, data, qty)

        reservation_no = next_document_no(
            self.ds, SEQUENCE_CODE, default_pattern=DEFAULT_PATTERN)
        with self.ds.transaction():
            cursor = self.ds.execute(
                'INSERT INTO %s (reservation_no, org_id, item_id, uom_id, '
                'demand_object_type, demand_object_id, demand_line_id, '
                'location_id, batch_id, stock_segment_type, project_id, '
                'project_task_id, sales_order_line_id, owner_party_id, '
                'qty_reserved, qty_fulfilled, peg_type, status, valid_from, '
                'valid_to, source_doc_type, source_doc_id, source_line_id, '
                'reservation_key, remark, created_by, created_at, '
                'updated_by, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '
                '?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)' % RESERVATION_TABLE,
                [reservation_no, org_id, item_id, uom_id, demand_type,
                 demand_id, _to_int(data.get('demand_line_id')),
                 _to_int(data.get('location_id')) or None,
                 _to_int(data.get('batch_id')) or None,
                 segment['stock_segment_type'], segment['project_id'],
                 segment['project_task_id'], segment['sales_order_line_id'],
                 segment['owner_party_id'], qty, peg_type, STATUS_OPEN,
                 data.get('valid_from'), data.get('valid_to'),
                 data.get('source_doc_type'),
                 _to_int(data.get('source_doc_id')) or None,
                 _to_int(data.get('source_line_id')) or None,
                 key, data.get('remark'), data.get('created_by'), _now(),
                 data.get('created_by'), _now()])
            reservation_id = cursor.lastrowid
            self._rebuild_projection(org_id)

        row = self._load(reservation_id)
        logger.info('[inv2] 预留创建 id=%s no=%s qty=%s segment=%s peg=%s',
                    reservation_id, reservation_no, qty,
                    segment['stock_segment_type'], peg_type)
        return {'reservation': row, 'created': True}

    def _resolve_segment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        service = self._segment_service()
        if _blank(data.get('stock_segment_type')):
            return service.resolve_segment(data)
        return service.validate_segment({
            'stock_segment_type': data.get('stock_segment_type'),
            'project_id': data.get('project_id'),
            'project_task_id': data.get('project_task_id'),
            'sales_order_line_id': data.get('sales_order_line_id'),
            'owner_party_id': data.get('owner_party_id'),
            'item_id': data.get('item_id'),
            'org_id': data.get('org_id'),
        })

    def _base_uom(self, item_id: int) -> int:
        if not item_id:
            return 0
        try:
            rows = self.ds.query('SELECT base_uom FROM items WHERE id = ?',
                                 [item_id])
        except Exception:
            return 0
        return _to_int(rows[0].get('base_uom')) if rows else 0

    # ------------------------------------------------------------------
    # 状态动作
    # ------------------------------------------------------------------
    def release_reservation(self, reservation_id: int,
                            reason: str = '') -> Dict[str, Any]:
        """释放预留（cancelled）；仅活跃状态可释放。"""
        row = self._load(reservation_id)
        self._assert_not_closed(row, '释放')
        if row['status'] not in ACTIVE_STATUSES:
            raise InventoryError(
                INV_RESERVATION_STATE_INVALID,
                '当前状态不可释放: %s' % row['status'],
                {'reservation_id': reservation_id, 'status': row['status']})
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, remark = ?, updated_at = ? '
                'WHERE id = ?' % RESERVATION_TABLE,
                [STATUS_CANCELLED,
                 reason or row.get('remark'), _now(), reservation_id])
            self._rebuild_projection(row.get('org_id'))
        updated = self._load(reservation_id)
        logger.info('[inv2] 预留释放 id=%s reason=%s', reservation_id, reason)
        return updated

    def close_reservation(self, reservation_id: int,
                          reason: str = '') -> Dict[str, Any]:
        """终止履行并保留历史（closed）；已核销量与链路不变。"""
        row = self._load(reservation_id)
        if row['status'] == STATUS_CLOSED:
            return row
        if row['status'] not in ACTIVE_STATUSES:
            raise InventoryError(
                INV_RESERVATION_STATE_INVALID,
                '当前状态不可关闭: %s' % row['status'],
                {'reservation_id': reservation_id, 'status': row['status']})
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, remark = ?, updated_at = ? '
                'WHERE id = ?' % RESERVATION_TABLE,
                [STATUS_CLOSED, reason or row.get('remark'), _now(),
                 reservation_id])
            self._rebuild_projection(row.get('org_id'))
        updated = self._load(reservation_id)
        logger.info('[inv2] 预留关闭 id=%s reason=%s', reservation_id, reason)
        return updated

    def fulfill_reservation(self, reservation_id: int, qty: Any,
                            tx_id: int = 0) -> Dict[str, Any]:
        """核销预留（部分/全部）；累计不得超过 qty_reserved。"""
        row = self._load(reservation_id)
        self._assert_not_closed(row, '核销')
        if row['status'] not in ACTIVE_STATUSES:
            raise InventoryError(
                INV_RESERVATION_STATE_INVALID,
                '当前状态不可核销: %s' % row['status'],
                {'reservation_id': reservation_id, 'status': row['status']})
        delta = _num(qty)
        if delta <= 0:
            raise InventoryError(
                INV_RESERVATION_QTY_EXCEEDED, '核销数量必须大于 0',
                {'reservation_id': reservation_id, 'qty': qty})
        reserved = _num(row.get('qty_reserved'))
        fulfilled = _num(row.get('qty_fulfilled'))
        if fulfilled + delta > reserved + 1e-9:
            raise InventoryError(
                INV_RESERVATION_QTY_EXCEEDED,
                '核销数量超过预留量',
                {'reservation_id': reservation_id,
                 'qty_reserved': reserved, 'qty_fulfilled': fulfilled,
                 'qty': delta})
        new_fulfilled = fulfilled + delta
        status = (STATUS_FULFILLED if new_fulfilled + 1e-9 >= reserved
                  else STATUS_PARTIALLY_FULFILLED)
        remark = row.get('remark')
        if tx_id:
            suffix = 'tx:%s' % tx_id
            remark = ('%s; %s' % (remark, suffix)).strip('; ')
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET qty_fulfilled = ?, status = ?, remark = ?, '
                'updated_at = ? WHERE id = ?' % RESERVATION_TABLE,
                [new_fulfilled, status, remark, _now(), reservation_id])
            self._rebuild_projection(row.get('org_id'))
        updated = self._load(reservation_id)
        logger.info('[inv2] 预留核销 id=%s qty=%s status=%s',
                    reservation_id, delta, status)
        return updated

    def fulfill_by_demand(self, demand_type: str, demand_id: Any, qty: Any,
                          tx_id: int = 0) -> Dict[str, Any]:
        """按需求节点跨预留核销：依次核销该需求下活跃预留，直至数量用尽。"""
        total = _num(qty)
        if total <= 0 or not self._table_ready():
            return {'fulfilled': 0.0, 'remaining': total, 'reservations': []}
        rows = self.ds.query(
            'SELECT id FROM %s WHERE demand_object_type = ? '
            'AND demand_object_id = ? AND status IN (?, ?) ORDER BY id'
            % RESERVATION_TABLE,
            [demand_type, _to_int(demand_id), STATUS_OPEN,
             STATUS_PARTIALLY_FULFILLED])
        remaining = total
        done: List[Dict[str, Any]] = []
        for row in rows:
            if remaining <= 1e-9:
                break
            current = self._load(row['id'])
            available = (_num(current.get('qty_reserved'))
                         - _num(current.get('qty_fulfilled')))
            if available <= 1e-9:
                continue
            take = min(available, remaining)
            done.append(self.fulfill_reservation(current['id'], take,
                                                 tx_id=tx_id))
            remaining -= take
        return {'fulfilled': total - remaining, 'remaining': remaining,
                'reservations': done}

    def fulfill_work_order_components(self, work_order_id: Any,
                                      completed_qty: Any = None,
                                      tx_id: int = 0) -> Dict[str, Any]:
        """完工收货按累计完工量核销组件承诺（A3 核销链路）。

        目标量 = qty_required × min(1, 累计完工量 / 由结构行反推的工单数量)；
        反推数量 = (qty_required / (1 + scrap_rate) − fixed_qty) / qty_per。
        `completed_qty` 为 None 表示按整单完工处理；`qty_per` 缺失时同样按整单处理。
        只向前核销、不回退：红冲保留成品谱系，组件退回需走独立退料。
        optional 组件不自动核销（是否投料无确定信号），留待释放或关单校验。
        """
        empty = {'fulfilled': 0.0, 'components': 0, 'skipped': 0}
        wo_id = _to_int(work_order_id)
        if wo_id <= 0 or not self._table_ready():
            return empty
        rows = self.ds.query(
            'SELECT id, qty_reserved, qty_fulfilled, demand_object_id '
            'FROM %s WHERE source_doc_type = ? AND source_doc_id = ? '
            'AND demand_object_type = ? AND status IN (?, ?)'
            % RESERVATION_TABLE,
            [WO_SOURCE_TYPE, wo_id, DEMAND_WORK_ORDER_COMPONENT,
             STATUS_OPEN, STATUS_PARTIALLY_FULFILLED])
        if not rows:
            return empty
        components = self._load_component_factors(wo_id)
        completed = None if completed_qty is None else _num(completed_qty)
        total = 0.0
        done = skipped = 0
        for row in rows:
            component = components.get(_to_int(row.get('demand_object_id')))
            target = self._component_fulfill_target(row, component, completed)
            if target is None or target <= 0:
                skipped += 1
                continue
            delta = target - _num(row.get('qty_fulfilled'))
            if delta <= 1e-9:
                continue
            self.fulfill_reservation(_to_int(row.get('id')), delta,
                                     tx_id=tx_id)
            total += delta
            done += 1
        if done:
            logger.info(
                '[inv2] 工单 %s 组件承诺核销 %s 条，合计 %s（累计完工 %s）',
                wo_id, done, total, completed)
        return {'fulfilled': round(total, 4), 'components': done,
                'skipped': skipped}

    def _load_component_factors(self, work_order_id: int) -> Dict[int, Dict]:
        """组件结构用量因子；表/列缺失时返回空（跳过自动核销）。"""
        try:
            rows = self.ds.query(
                'SELECT id, qty_required, qty_per, fixed_qty, scrap_rate, '
                'optional_flag FROM work_order_components '
                'WHERE work_order_id = ?', [work_order_id])
        except Exception as error:  # noqa: BLE001 - 旧库缺列不阻断完工
            logger.warning('[inv2] 读取工单组件因子失败: %s', error)
            return {}
        return {_to_int(row.get('id')): row for row in rows}

    @staticmethod
    def _component_fulfill_target(row: Dict[str, Any],
                                  component: Optional[Dict[str, Any]],
                                  completed: Optional[float]) -> Optional[float]:
        """单个组件承诺的目标核销量；None = 不自动核销。"""
        if not component or bool(component.get('optional_flag')):
            return None
        qty_reserved = _num(row.get('qty_reserved'))
        if completed is None:
            return qty_reserved
        if completed <= 0:
            return 0.0
        qty_required = _num(component.get('qty_required'))
        qty_per = _num(component.get('qty_per'))
        if qty_required <= 0 or qty_per <= 0:
            return qty_reserved
        scrap = max(_num(component.get('scrap_rate')), 0.0)
        fixed = max(_num(component.get('fixed_qty')), 0.0)
        implied_qty = (qty_required / (1 + scrap) - fixed) / qty_per
        if implied_qty <= 0:
            return qty_reserved
        ratio = min(1.0, completed / implied_qty)
        return min(qty_reserved, qty_required * ratio)

    def expire_reservations(self, now: Optional[str] = None) -> int:
        """把已过有效期的活跃预留置为 expired，返回处理行数。"""
        moment = now or _now()
        rows = self.ds.query(
            'SELECT id, org_id FROM %s WHERE status IN (?, ?) '
            'AND valid_to IS NOT NULL AND valid_to < ?' % RESERVATION_TABLE,
            [STATUS_OPEN, STATUS_PARTIALLY_FULFILLED, moment])
        if not rows:
            return 0
        org_ids = sorted({_to_int(row.get('org_id')) for row in rows})
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ? '
                'WHERE status IN (?, ?) AND valid_to IS NOT NULL '
                'AND valid_to < ?' % RESERVATION_TABLE,
                [STATUS_EXPIRED, _now(), STATUS_OPEN,
                 STATUS_PARTIALLY_FULFILLED, moment])
            for org_id in org_ids:
                self._rebuild_projection(org_id)
        logger.info('[inv2] 预留过期处理 %s 条 (now=%s)', len(rows), moment)
        return len(rows)

    # ------------------------------------------------------------------
    # 关单前置校验
    # ------------------------------------------------------------------
    def outstanding_commitments(self, source_doc_type: Any,
                                source_doc_id: Any) -> Dict[str, Any]:
        """来源单据上的未核销承诺（活跃且未过期），供关单前置校验使用。"""
        empty = {'count': 0, 'outstanding': 0.0, 'reservation_ids': []}
        if not str(source_doc_type or '').strip() or not _to_int(source_doc_id):
            return empty
        if not self._table_ready():
            return empty
        rows = self.ds.query(
            'SELECT id, qty_reserved, qty_fulfilled FROM %s '
            'WHERE source_doc_type = ? AND source_doc_id = ? '
            'AND status IN (?, ?) AND (valid_to IS NULL OR valid_to > ?)'
            % RESERVATION_TABLE,
            [str(source_doc_type).strip(), _to_int(source_doc_id),
             STATUS_OPEN, STATUS_PARTIALLY_FULFILLED, _now()])
        count = 0
        outstanding = 0.0
        reservation_ids = []
        for row in rows:
            remaining = _num(row.get('qty_reserved')) \
                - _num(row.get('qty_fulfilled'))
            if remaining <= 0:
                continue
            count += 1
            outstanding += remaining
            reservation_ids.append(_to_int(row.get('id')))
        return {'count': count, 'outstanding': outstanding,
                'reservation_ids': reservation_ids}

    def assert_source_closable(self, source_doc_type: Any,
                               source_doc_id: Any) -> None:
        """关单前置校验：仍有未核销承诺时拒绝关闭，避免静默丢需求。"""
        info = self.outstanding_commitments(source_doc_type, source_doc_id)
        if info['count'] > 0:
            raise InventoryError(
                INV_RESERVATION_ACTIVE_ON_CLOSE,
                '仍有未核销预留，不能关闭；请先核销或释放',
                info)

    # ------------------------------------------------------------------
    # ATP
    # ------------------------------------------------------------------
    def available_on_hand(self, query: Dict[str, Any],
                          include_inbound: bool = False) -> Dict[str, Any]:
        """按段可用量：段内 on_hand - 活跃预留未核销量。

        含在途分支未实现：在途供应由 hard pegging 陈述，只能从 atp() 读取。
        """
        if include_inbound:
            raise InventoryError(
                ATP_INBOUND_UNSUPPORTED,
                '在途供应未接入，include_inbound=true 暂不支持',
                {'include_inbound': include_inbound})
        data = dict(query or {})
        org_id = _to_int(data.get('org_id'))
        item_id = _to_int(data.get('item_id'))
        if not org_id or not item_id:
            raise InventoryError(
                'INV_ENTRY_INVALID', '可用量查询缺少库存组织或物料',
                {'org_id': org_id, 'item_id': item_id})
        segment = self._resolve_segment(data)
        location_id = _to_int(data.get('location_id'))
        batch_id = _to_int(data.get('batch_id'))
        stock_status = data.get('stock_status') or 'unrestricted'

        on_hand = self._sum_on_hand(org_id, item_id, location_id, batch_id,
                                    stock_status, segment)
        reserved = self._sum_active_reservations(
            org_id, item_id, location_id, batch_id, segment)
        return {
            'on_hand': on_hand,
            'reserved': reserved,
            'available_on_hand': on_hand - reserved,
            'shortage': max(0.0, reserved - on_hand),
            'expected_receipts': 0.0,
            'stock_segment_type': segment['stock_segment_type'],
            'project_id': segment['project_id'],
            'project_task_id': segment['project_task_id'],
            'sales_order_line_id': segment['sales_order_line_id'],
            'owner_party_id': segment['owner_party_id'],
            'include_inbound': False,
        }

    def atp(self, query: Dict[str, Any],
            include_inbound: bool = False) -> Dict[str, Any]:
        """简化 ATP（不带日期）：可用量；含在途时再扣未收货 hard pegging。

        v1 expected_receipts 恒为 0；include_inbound=True 只做“已钉住的未来
        供应不再计入可用”的扣减，避免把已被 pegging 占用的在途重复承诺。
        """
        result = self.available_on_hand(query, include_inbound=False)
        data = dict(query or {})
        pegged = 0.0
        if include_inbound:
            pegged = self._sum_inbound_pegged(
                _to_int(data.get('org_id')), _to_int(data.get('item_id')),
                _to_int(data.get('location_id')),
                _to_int(data.get('batch_id')), self._resolve_segment(data))
            result['available_on_hand'] -= pegged
        result['inbound_pegged'] = pegged
        result['include_inbound'] = bool(include_inbound)
        return result

    def _segment_clause(self, segment: Dict[str, Any]):
        sql = ' AND ' + ' AND '.join('%s = ?' % col for col in SEGMENT_COLUMNS)
        params: List[Any] = [segment['stock_segment_type']]
        params.extend(_to_int(segment[col])
                      for col in SEGMENT_COLUMNS[1:])
        return sql, params

    def _sum_on_hand(self, org_id: int, item_id: int, location_id: int,
                     batch_id: int, stock_status: str,
                     segment: Dict[str, Any]) -> float:
        clause, params = self._segment_clause(segment)
        scope_sql, scope_params = self._scope_clause(location_id, batch_id)
        try:
            rows = self.ds.query(
                'SELECT COALESCE(SUM(qty_on_hand), 0) AS total FROM %s '
                'WHERE org_id = ? AND item_id = ? AND stock_status = ? '
                % BAL_TABLE + clause + scope_sql,
                [org_id, item_id, stock_status] + params + scope_params)
        except Exception as exc:
            logger.debug('[inv2] 可用量汇总失败（余额表未建）: %s', exc)
            return 0.0
        return _num(rows[0].get('total')) if rows else 0.0

    def _sum_active_reservations(self, org_id: int, item_id: int,
                                 location_id: int, batch_id: int,
                                 segment: Dict[str, Any]) -> float:
        if not self._table_ready():
            return 0.0
        clause, params = self._segment_clause(segment)
        scope_sql, scope_params = self._scope_clause(location_id, batch_id)
        rows = self.ds.query(
            'SELECT COALESCE(SUM(qty_reserved - qty_fulfilled), 0) AS total '
            'FROM %s WHERE org_id = ? AND item_id = ? AND status IN (?, ?) '
            'AND (valid_to IS NULL OR valid_to > ?) '
            % RESERVATION_TABLE + clause + scope_sql,
            [org_id, item_id, STATUS_OPEN, STATUS_PARTIALLY_FULFILLED, _now()]
            + params + scope_params)
        return _num(rows[0].get('total')) if rows else 0.0

    def _sum_inbound_pegged(self, org_id: int, item_id: int,
                            location_id: int, batch_id: int,
                            segment: Dict[str, Any]) -> float:
        """含在途 ATP 扣减：该段活跃需求上 hard 钉住的未收货未来供应量。

        只统计能以活跃预留定位到需求节点的 pegging；trace 表无段字段，
        故以预留作为段锚点，避免跨段误扣。
        """
        if not org_id or not item_id or not self._table_ready():
            return 0.0
        try:
            exists = self.ds.query(
                "SELECT name FROM sqlite_master WHERE type='table' "
                'AND name=?', [TRACE_TABLE])
        except Exception:
            return 0.0
        if not exists:
            return 0.0
        clause, params = self._segment_clause(segment)
        scope_sql, scope_params = self._scope_clause(location_id, batch_id)
        nodes = self.ds.query(
            'SELECT DISTINCT demand_object_type, demand_object_id, '
            'demand_line_id FROM %s WHERE org_id = ? AND item_id = ? '
            'AND status IN (?, ?) AND (valid_to IS NULL OR valid_to > ?) '
            % RESERVATION_TABLE + clause + scope_sql,
            [org_id, item_id, STATUS_OPEN, STATUS_PARTIALLY_FULFILLED,
             _now()] + params + scope_params)
        if not nodes:
            return 0.0
        placeholders = ', '.join('?' for _ in FUTURE_SUPPLY_TYPES)
        total = 0.0
        for node in nodes:
            rows = self.ds.query(
                'SELECT COALESCE(SUM(allocated_qty), 0) AS total '
                'FROM %s WHERE trace_type = ? AND peg_type = ? '
                'AND (valid_to IS NULL OR valid_to > ?) '
                'AND supply_object_type IN (%s) '
                'AND demand_object_type = ? AND demand_object_id = ? '
                'AND demand_line_id = ?' % (TRACE_TABLE, placeholders),
                [TRACE_PEGGING, PEG_HARD, _now()]
                + list(FUTURE_SUPPLY_TYPES)
                + [node.get('demand_object_type'),
                   _to_int(node.get('demand_object_id')),
                   _to_int(node.get('demand_line_id'))])
            total += _num(rows[0].get('total')) if rows else 0.0
        return total

    def _scope_clause(self, location_id: int, batch_id: int):
        """location/batch 过滤：0 = 不限；预留的 NULL 视为不限定。"""
        sql = ''
        params: List[Any] = []
        if location_id:
            sql += ' AND (location_id IS NULL OR location_id = ?)'
            params.append(location_id)
        if batch_id:
            sql += ' AND (batch_id IS NULL OR batch_id = ?)'
            params.append(batch_id)
        return sql, params

    # ------------------------------------------------------------------
    # 销售订单接入
    # ------------------------------------------------------------------
    def sync_sales_order_line(self, line_id: Any) -> Dict[str, Any]:
        """按销售订单行同步预留（幂等）：可交付行建预留，取消行释放。

        · `so_segment_enabled=1` → `sales_order_line` 段；否则 MTO 标准
          不建段，预留落 `owned` 公共池。
        · `hard_peg_default=1` → hard，否则 soft。
        · 组织取行上的发货库位所属组织，缺省回落抬头财务组织 / 销售组织。
        """
        if not self._table_ready():
            return {'created': False, 'skipped': True,
                    'reason': 'RESERVATION_TABLE_MISSING'}
        line = self._load_sales_order_line(line_id)
        if not line:
            return {'created': False, 'skipped': True,
                    'reason': 'SALES_ORDER_LINE_NOT_FOUND'}
        key = 'SO-LINE-%s' % _to_int(line_id)
        flags = self._segment_service().item_flags(_to_int(line.get('item_id')))
        line_status = str(line.get('status') or '')
        order_status = str(line.get('order_status') or '')
        closed = line_status in (STATUS_CANCELLED, 'closed') \
            or order_status == STATUS_CANCELLED
        if closed or _to_int(line.get('item_id')) <= 0 \
                or _num(line.get('qty')) <= 0:
            released = self.release_by_source(
                'sales_order', _to_int(line.get('order_id')), line_id=line_id,
                reason='销售订单行取消/关闭')
            if flags['so_segment_enabled']:
                self._segment_service().prune_empty_balances({
                    'stock_segment_type': 'sales_order_line',
                    'sales_order_line_id': _to_int(line_id),
                })
            # G15 P2：任务行释放后清理任务段空余额（有项目才可校验段）
            task_id = _to_int(line.get('project_task_id'))
            project_id = _to_int(line.get('project_id'))
            if task_id and project_id:
                self._segment_service().prune_empty_balances({
                    'stock_segment_type': 'project_task',
                    'project_id': project_id,
                    'project_task_id': task_id,
                })
            return {'created': False, 'skipped': True,
                    'released': released, 'reason': 'NOT_RESERVABLE'}

        org_id, location_id = self._resolve_so_org(line)
        if not org_id:
            logger.warning('[inv2] SO 行 %s 无法解析库存组织，跳过预留', line_id)
            return {'created': False, 'skipped': True,
                    'reason': 'ORG_NOT_RESOLVED'}
        segment_ctx = {
            'item_id': _to_int(line.get('item_id')),
            'org_id': org_id,
            'sales_order_line_id': (_to_int(line_id)
                                    if flags['so_segment_enabled'] else 0),
            'so_segment_enabled': flags['so_segment_enabled'],
            # G15 P2：任务行落 project_task 段（任务优先于 SO 行段；
            # SO 段 + 任务组合已在 SO 守卫拒绝，无歧义）。
            'project_id': (_to_int(line.get('project_id'))
                           if _to_int(line.get('project_task_id')) else 0),
            'project_task_id': _to_int(line.get('project_task_id')),
        }
        payload = {
            'reservation_key': key,
            'org_id': org_id,
            'item_id': _to_int(line.get('item_id')),
            'uom_id': _to_int(line.get('uom_id')),
            'location_id': location_id or None,
            'qty_reserved': _num(line.get('qty')),
            'peg_type': PEG_HARD if flags['hard_peg_default'] else PEG_SOFT,
            'demand_object_type': 'sales_order_line',
            'demand_object_id': _to_int(line_id),
            'demand_line_id': _to_int(line_id),
            'source_doc_type': 'sales_order',
            'source_doc_id': _to_int(line.get('order_id')),
            'source_line_id': _to_int(line_id),
            'stock_segment_type': None,
            'created_by': None,
        }
        segment = self._resolve_segment(segment_ctx)
        payload.update(segment)
        return self.sync_reservation(payload)

    # ------------------------------------------------------------------
    # 工单组件接入
    # ------------------------------------------------------------------
    def sync_work_order_components(self, work_order_id: Any) -> Dict[str, Any]:
        """工单组件级 soft 预留：把投料需求计入可用量（A3 最小闭环）。

        · 组件是独立物料需求，与来源 SO 行（成品）预留不重复计量；
        · 一律 soft：不锁死库存，短缺由 ATP shortage 暴露；
        · 段：组件任务 → 任务段，否则 owned；组织：项目 → 销售订单抬头；
        · 幂等键按 structure_line_id 稳定，重展开不会重复承诺；
        · 工单取消/关闭时释放组件承诺；结构行消失的旧承诺一并释放。
        """
        empty = {'created': 0, 'updated': 0, 'released': 0, 'skipped': True}
        if not self._table_ready():
            return dict(empty, reason='RESERVATION_TABLE_MISSING')
        work_order = self._load_work_order(work_order_id)
        if not work_order:
            return dict(empty, reason='WORK_ORDER_NOT_FOUND')
        wo_id = _to_int(work_order.get('id'))
        if str(work_order.get('status') or '') in WO_COMPONENT_RELEASE_STATUSES:
            return {'created': 0, 'updated': 0, 'skipped': False,
                    'released': self.release_by_source(
                        WO_SOURCE_TYPE, wo_id, reason='工单取消/关闭')}
        components = self._load_work_order_components(wo_id)
        org_id = self._resolve_work_order_org(work_order)
        if not org_id:
            logger.warning('[inv2] 工单 %s 无法解析库存组织，跳过组件预留',
                           wo_id)
            return dict(empty, reason='ORG_NOT_RESOLVED')

        project_id = _to_int(work_order.get('project_id'))
        wo_task_id = _to_int(work_order.get('project_task_id'))
        created = updated = skipped = 0
        active_keys = set()
        for component in components:
            component_id = _to_int(component.get('id'))
            item_id = _to_int(component.get('component_item_id'))
            qty = _num(component.get('qty_required'))
            if component_id <= 0 or item_id <= 0 or qty <= 0:
                skipped += 1
                continue
            structure_line_id = _to_int(component.get('structure_line_id')) \
                or component_id
            key = '%s-%s-%s' % (WO_COMPONENT_KEY_PREFIX, wo_id,
                                structure_line_id)
            active_keys.add(key)
            task_id = _to_int(component.get('project_task_id')) or wo_task_id
            segment_ctx = {
                'item_id': item_id,
                'org_id': org_id,
                'project_id': project_id if task_id else 0,
                'project_task_id': task_id,
            }
            try:
                segment = self._resolve_segment(segment_ctx)
            except InventoryError as error:
                logger.warning('[inv2] 工单 %s 组件 %s 段解析失败，跳过: %s',
                               wo_id, component_id, error)
                skipped += 1
                continue
            payload = {
                'reservation_key': key,
                'org_id': org_id,
                'item_id': item_id,
                'uom_id': self._base_uom(item_id),
                'qty_reserved': qty,
                'peg_type': PEG_SOFT,
                'demand_object_type': DEMAND_WORK_ORDER_COMPONENT,
                'demand_object_id': component_id,
                'demand_line_id': component_id,
                'source_doc_type': WO_SOURCE_TYPE,
                'source_doc_id': wo_id,
                'source_line_id': component_id,
            }
            payload.update(segment)
            result = self.sync_reservation(payload)
            if result.get('created'):
                created += 1
            elif result.get('updated'):
                updated += 1
            self._refresh_component_demand(result.get('reservation'), component_id)

        released = self._release_stale_components(wo_id, active_keys)
        return {'created': created, 'updated': updated,
                'released': released, 'skipped': skipped}

    def _refresh_component_demand(self, row: Optional[Dict[str, Any]],
                                  component_id: int) -> None:
        """重展开后组件 id 变化：把承诺重新指向新组件行（键不变，不重复承诺）。"""
        if not row:
            return
        if _to_int(row.get('demand_object_id')) == component_id \
                and _to_int(row.get('demand_line_id')) == component_id:
            return
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET demand_object_id = ?, demand_line_id = ?, '
                'updated_at = ? WHERE id = ?' % RESERVATION_TABLE,
                [component_id, component_id, _now(), row.get('id')])

    def _release_stale_components(self, work_order_id: int,
                                  active_keys: set) -> int:
        """释放结构行已消失的组件承诺（active_keys 之外的旧行）。"""
        rows = self.ds.query(
            'SELECT id, reservation_key FROM %s WHERE source_doc_type = ? '
            'AND source_doc_id = ? AND demand_object_type = ? '
            'AND status IN (?, ?)' % RESERVATION_TABLE,
            [WO_SOURCE_TYPE, work_order_id, DEMAND_WORK_ORDER_COMPONENT,
             STATUS_OPEN, STATUS_PARTIALLY_FULFILLED])
        stale = [row for row in rows
                 if str(row.get('reservation_key') or '') not in active_keys]
        for row in stale:
            self.release_reservation(_to_int(row.get('id')),
                                     reason='工单组件重建后释放旧承诺')
        return len(stale)

    def sync_reservation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """幂等创建 + 数量同步：仅活跃预留允许改量，不得低于已核销量。"""
        result = self.create_reservation(payload)
        if result.get('created'):
            return result
        row = result['reservation']
        if row['status'] not in ACTIVE_STATUSES:
            return {'reservation': row, 'created': False, 'updated': False}
        new_qty = _num(payload.get('qty_reserved'))
        fulfilled = _num(row.get('qty_fulfilled'))
        target = max(new_qty, fulfilled)
        if abs(target - _num(row.get('qty_reserved'))) <= 1e-9:
            return {'reservation': row, 'created': False, 'updated': False}
        if target > _num(row.get('qty_reserved')) \
                and str(row.get('peg_type') or '') == PEG_HARD:
            self._assert_hard_peg(
                {col: row.get(col) for col in SEGMENT_COLUMNS}, payload,
                target - _num(row.get('qty_reserved')))
        status = (STATUS_FULFILLED if fulfilled + 1e-9 >= target
                  else STATUS_PARTIALLY_FULFILLED
                  if fulfilled > 0 else STATUS_OPEN)
        with self.ds.transaction():
            self.ds.execute(
                'UPDATE %s SET qty_reserved = ?, status = ?, updated_at = ? '
                'WHERE id = ?' % RESERVATION_TABLE,
                [target, status, _now(), row['id']])
            self._rebuild_projection(row.get('org_id'))
        updated = self._load(row['id'])
        logger.info('[inv2] 预留同步 id=%s %s -> %s',
                    row['id'], row.get('qty_reserved'), target)
        return {'reservation': updated, 'created': False, 'updated': True}

    def release_by_source(self, doc_type: str, doc_id: Any,
                          line_id: Any = None,
                          reason: str = '') -> int:
        """按来源单据释放其全部活跃预留，返回释放条数。"""
        if not self._table_ready():
            return 0
        sql = ('SELECT id, org_id FROM %s WHERE source_doc_type = ? '
               'AND source_doc_id = ? AND status IN (?, ?)'
               % RESERVATION_TABLE)
        params: List[Any] = [doc_type, _to_int(doc_id),
                             STATUS_OPEN, STATUS_PARTIALLY_FULFILLED]
        if _to_int(line_id):
            sql += ' AND source_line_id = ?'
            params.append(_to_int(line_id))
        rows = self.ds.query(sql, params)
        if not rows:
            return 0
        org_ids = sorted({_to_int(row.get('org_id')) for row in rows})
        ids = [_to_int(row.get('id')) for row in rows]
        with self.ds.transaction():
            placeholders = ', '.join('?' for _ in ids)
            self.ds.execute(
                'UPDATE %s SET status = ?, remark = ?, updated_at = ? '
                'WHERE id IN (%s)' % (RESERVATION_TABLE, placeholders),
                [STATUS_CANCELLED, reason or None, _now()] + ids)
            for org_id in org_ids:
                self._rebuild_projection(org_id)
        logger.info('[inv2] 预留按来源释放 %s:%s line=%s 共 %s 条',
                    doc_type, doc_id, line_id, len(ids))
        return len(ids)

    def _load_sales_order_line(self, line_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                # 整行读取：兼容未加 project_task_id 的旧库 / 测试库
                'SELECT l.*, o.org_id AS header_org_id, '
                'o.status AS order_status '
                'FROM sales_order_lines l '
                'LEFT JOIN sales_orders o ON o.id = l.order_id '
                'WHERE l.id = ?', [_to_int(line_id)])
        except Exception:
            return None
        return rows[0] if rows else None

    def _resolve_so_org(self, line: Dict[str, Any]) -> tuple:
        """返回 (org_id, location_id)；库位组织优先，抬头组织兜底。"""
        location_id = _to_int(line.get('plant_location_id'))
        if location_id:
            try:
                rows = self.ds.query(
                    'SELECT org_id FROM locations WHERE id = ?', [location_id])
            except Exception:
                rows = []
            loc_org = _to_int(rows[0].get('org_id')) if rows else 0
            if loc_org:
                return loc_org, location_id
        return _to_int(line.get('header_org_id')), location_id or 0

    def _load_work_order(self, work_order_id: Any) -> Optional[Dict[str, Any]]:
        if _to_int(work_order_id) <= 0:
            return None
        try:
            rows = self.ds.query('SELECT * FROM work_orders WHERE id = ?',
                                 [_to_int(work_order_id)])
        except Exception:
            return None
        return rows[0] if rows else None

    def _load_work_order_components(self, work_order_id: int):
        try:
            return self.ds.query(
                # 整行读取：兼容未加 structure_line_id 的旧库 / 测试库
                'SELECT * FROM work_order_components WHERE work_order_id = ? '
                'ORDER BY id', [work_order_id])
        except Exception:
            return []

    def _resolve_work_order_org(self, work_order: Dict[str, Any]) -> int:
        """项目组织优先，销售订单抬头组织兜底；都缺失则无法建承诺。"""
        project_id = _to_int(work_order.get('project_id'))
        if project_id:
            org_id = self._query_org('projects', project_id)
            if org_id:
                return org_id
        order_id = _to_int(work_order.get('order_id'))
        if order_id:
            org_id = self._query_org('sales_orders', order_id)
            if org_id:
                return org_id
        return 0

    def _query_org(self, table: str, row_id: int) -> int:
        try:
            rows = self.ds.query('SELECT org_id FROM %s WHERE id = ?' % table,
                                 [row_id])
        except Exception:
            return 0
        return _to_int(rows[0].get('org_id')) if rows else 0

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _rebuild_projection(self, org_id: Any) -> None:
        """回写 qty_reserved 投影；余额表未建（单测子集）时静默跳过。"""
        try:
            if not self.ds.query(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    'AND name=?', [BAL_TABLE]):
                return
            self._posting_service().rebuild_reserved_qty(
                org_id=org_id or None)
        except Exception as exc:  # 投影失败不得影响预留事实写入
            logger.warning('[inv2] qty_reserved 投影回写跳过: %s', exc)

    def _assert_not_closed(self, row: Dict[str, Any], action: str) -> None:
        if row.get('status') == STATUS_CLOSED:
            raise InventoryError(
                INV_RESERVATION_CLOSED,
                '已关闭的预留不可%s' % action,
                {'reservation_id': row.get('id'), 'status': row.get('status')})

    def _assert_demand_capacity(self, demand_type: str, demand_id: int,
                                demand_line_id: int, qty: float) -> None:
        """需求上限守卫：已核销 + 未核销承诺 + 本次量不得超过需求量。"""
        demand_qty = self._demand_qty(demand_type, demand_id, demand_line_id)
        if demand_qty is None:
            logger.warning(
                '[inv2] %s demand=%s:%s line=%s 需求量不可解析，跳过上限守卫',
                INV_DEMAND_QTY_UNKNOWN, demand_type, demand_id, demand_line_id)
            return
        fulfilled, open_qty = self._demand_usage(
            demand_type, demand_id, demand_line_id)
        if fulfilled + open_qty + qty > demand_qty + 1e-9:
            raise InventoryError(
                INV_RESERVATION_EXCEEDS_DEMAND,
                '未核销承诺合计超过需求剩余量',
                {'demand_object_type': demand_type,
                 'demand_object_id': demand_id,
                 'demand_line_id': demand_line_id,
                 'demand_qty': demand_qty,
                 'fulfilled': fulfilled,
                 'open_commitment': open_qty,
                 'qty': qty})

    def _demand_qty(self, demand_type: str, demand_id: int,
                    demand_line_id: int) -> Optional[float]:
        mapping = DEMAND_QTY_SOURCES.get(demand_type)
        if not mapping or not demand_id:
            return None
        table, column = mapping
        key = demand_line_id or demand_id
        try:
            rows = self.ds.query(
                'SELECT %s AS qty FROM %s WHERE id = ?' % (column, table),
                [key])
        except Exception:
            return None
        if not rows:
            return None
        return _num(rows[0].get('qty'))

    def _demand_usage(self, demand_type: str, demand_id: int,
                      demand_line_id: int) -> tuple:
        """返回该需求节点已核销量与活跃未核销承诺量。"""
        if not self._table_ready():
            return 0.0, 0.0
        rows = self.ds.query(
            'SELECT COALESCE(SUM(qty_fulfilled), 0) AS fulfilled, '
            'COALESCE(SUM(CASE WHEN status IN (?, ?) '
            'THEN qty_reserved - qty_fulfilled ELSE 0 END), 0) AS open_qty '
            'FROM %s WHERE demand_object_type = ? AND demand_object_id = ? '
            'AND demand_line_id = ?' % RESERVATION_TABLE,
            [STATUS_OPEN, STATUS_PARTIALLY_FULFILLED, demand_type, demand_id,
             demand_line_id])
        if not rows:
            return 0.0, 0.0
        return _num(rows[0].get('fulfilled')), _num(rows[0].get('open_qty'))

    def _assert_hard_peg(self, segment: Dict[str, Any], data: Dict[str, Any],
                         qty: float) -> None:
        """硬钉不得超订：有存量时，目标段可用量必须覆盖本次预留。

        无存量时允许预占未来入库（MTO/ETO 先预留后收货），
        但仍禁止对同一段硬钉超出现有供应。
        """
        org_id = _to_int(data.get('org_id'))
        item_id = _to_int(data.get('item_id'))
        location_id = _to_int(data.get('location_id'))
        batch_id = _to_int(data.get('batch_id'))
        on_hand = self._sum_on_hand(org_id, item_id, location_id, batch_id,
                                    data.get('stock_status') or 'unrestricted',
                                    segment)
        if on_hand <= 0:
            return
        reserved = self._sum_active_reservations(
            org_id, item_id, location_id, batch_id, segment)
        if qty > on_hand - reserved + 1e-9:
            raise InventoryError(
                INV_HARD_PEG_CONFLICT, '硬钉预留超出目标段可用量',
                {'on_hand': on_hand, 'reserved': reserved, 'qty': qty,
                 'stock_segment_type': segment['stock_segment_type'],
                 'project_task_id': segment['project_task_id'],
                 'sales_order_line_id': segment['sales_order_line_id'],
                 'owner_party_id': segment['owner_party_id']})

    def _by_key(self, key: str) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE reservation_key = ?' % RESERVATION_TABLE,
            [key])
        return rows[0] if rows else None

    def _load(self, reservation_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % RESERVATION_TABLE,
            [_to_int(reservation_id)])
        if not rows:
            raise InventoryError(
                INV_RESERVATION_NOT_FOUND, '库存预留不存在: %s' % reservation_id,
                {'reservation_id': reservation_id})
        return rows[0]
