# -*- coding: utf-8 -*-
"""需求线索服务 —— INV-2 S3 跨单据供应—需求链。

依据:
  docs/specs/inv2-reservation-atp/spec.md §3.4 / §4.3

口径:
  ① 同一 (supply 节点, demand 节点, trace_type) 只允许一条有效 trace；
     重复链接同量幂等，改量按覆盖处理。
  ② 分配量不得超过供应节点 / 需求节点自身数量（可解析时）。
  ③ 与 demand_allocation 边界：本表只写跨单据 trace，不写单据内需求归属。
  ④ unlink 只置 valid_to，不物理删除。
  ⑤ trace_end_demand 迭代追到最终需求节点。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from meta.services.inventory_guard_service import InventoryError

logger = logging.getLogger(__name__)

TRACE_TABLE = 'demand_trace_links'

TRACE_RESERVATION = 'reservation'
TRACE_PEGGING = 'pegging'
TRACE_ALLOCATION = 'allocation'
TRACE_TYPES = (TRACE_RESERVATION, TRACE_PEGGING, TRACE_ALLOCATION)

PEG_HARD = 'hard'
PEG_SOFT = 'soft'

INV_TRACE_QTY_EXCEEDED = 'INV_TRACE_QTY_EXCEEDED'
INV_TRACE_NODE_INVALID = 'INV_TRACE_NODE_INVALID'
INV_TRACE_NOT_FOUND = 'INV_TRACE_NOT_FOUND'

#: 节点类型白名单（供应侧 + 需求侧）
NODE_TYPES = (
    'inventory_balance', 'inventory_transaction',
    'purchase_order_line', 'receipt_line', 'shipment', 'shipment_line',
    'work_order', 'work_order_component', 'transfer_order_line',
    'sales_order', 'sales_order_line', 'project_task', 'forecast',
    'service_order',
)

#: 可解析数量的节点 → (表, 数量列)
NODE_QTY = {
    'sales_order_line': ('sales_order_lines', 'qty'),
    'purchase_order_line': ('purchase_order_lines', 'qty'),
    'receipt_line': ('receipt_lines', 'qty_received'),
    'shipment_line': ('shipment_lines', 'qty'),
    'work_order_component': ('work_order_components', 'qty_required'),
    'transfer_order_line': ('transfer_order_lines', 'qty'),
    'inventory_balance': ('inventory_balances', 'qty_on_hand'),
}


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


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


def _node_key(node: Dict[str, Any]) -> Tuple[str, int, int]:
    node_type = str(node.get('object_type') or node.get('node_type') or '')
    return (node_type, _to_int(node.get('object_id') or node.get('id')),
            _to_int(node.get('line_id')))


class DemandTraceService:
    """供应—需求 trace 的写入、关闭与端到端追溯。"""

    def __init__(self, data_source):
        self.ds = data_source

    def _table_ready(self) -> bool:
        try:
            return bool(self.ds.query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                [TRACE_TABLE]))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 链接
    # ------------------------------------------------------------------
    def link_supply_demand(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """写一条 trace；同三元组同量幂等，改量覆盖。"""
        if not self._table_ready():
            raise InventoryError(
                'INV_SEQUENCE_MISSING', '需求线索表未建立（v205 未迁移）')
        data = dict(payload or {})
        supply = {
            'object_type': data.get('supply_object_type'),
            'object_id': data.get('supply_object_id'),
            'line_id': data.get('supply_line_id'),
        }
        demand = {
            'object_type': data.get('demand_object_type'),
            'object_id': data.get('demand_object_id'),
            'line_id': data.get('demand_line_id'),
        }
        for node in (supply, demand):
            node_type = str(node.get('object_type') or '')
            if node_type not in NODE_TYPES:
                raise InventoryError(
                    INV_TRACE_NODE_INVALID,
                    '未知 trace 节点类型: %s' % node_type,
                    {'node': node})
            if _to_int(node.get('object_id')) <= 0:
                raise InventoryError(
                    INV_TRACE_NODE_INVALID, 'trace 节点缺少对象 ID',
                    {'node': node})

        trace_type = str(data.get('trace_type') or TRACE_ALLOCATION).strip()
        if trace_type not in TRACE_TYPES:
            raise InventoryError(
                INV_TRACE_NODE_INVALID,
                '未知 trace 类型: %s' % trace_type, {'trace_type': trace_type})
        peg_type = str(data.get('peg_type') or PEG_SOFT).strip().lower()
        if peg_type not in (PEG_HARD, PEG_SOFT):
            raise InventoryError(
                INV_TRACE_NODE_INVALID, '钉类型只允许 hard / soft',
                {'peg_type': peg_type})
        qty = _num(data.get('allocated_qty'))
        if qty <= 0:
            raise InventoryError(
                INV_TRACE_QTY_EXCEEDED, 'trace 分配量必须大于 0',
                {'allocated_qty': data.get('allocated_qty')})

        existing = self._find_active(supply, demand, trace_type)
        if existing:
            if abs(_num(existing.get('allocated_qty')) - qty) <= 1e-9:
                return {'link': existing, 'created': False, 'updated': False}
            self._assert_capacity(supply, demand, trace_type,
                                   qty, exclude_id=existing['id'])
            self.ds.execute(
                'UPDATE %s SET allocated_qty = ?, peg_type = ?, remark = ?, '
                'computed_at = ? WHERE id = ?' % TRACE_TABLE,
                [qty, peg_type, data.get('remark'), _now(), existing['id']])
            updated = self._load(existing['id'])
            return {'link': updated, 'created': False, 'updated': True}

        self._assert_capacity(supply, demand, trace_type, qty)
        cursor = self.ds.execute(
            'INSERT INTO %s (supply_object_type, supply_object_id, '
            'supply_line_id, demand_object_type, demand_object_id, '
            'demand_line_id, trace_type, peg_type, allocated_qty, '
            'plan_version, valid_from, valid_to, source_doc_type, '
            'source_doc_id, source_line_id, remark, computed_at, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)'
            % TRACE_TABLE,
            [supply['object_type'], _to_int(supply['object_id']),
             _to_int(supply['line_id']), demand['object_type'],
             _to_int(demand['object_id']), _to_int(demand['line_id']),
             trace_type, peg_type, qty, data.get('plan_version'),
             data.get('valid_from') or _now(), data.get('source_doc_type'),
             _to_int(data.get('source_doc_id')) or None,
             _to_int(data.get('source_line_id')) or None,
             data.get('remark'), _now(), _now()])
        link = self._load(cursor.lastrowid)
        logger.info('[inv2] trace 链接 %s:%s:%s -> %s:%s:%s qty=%s',
                    supply['object_type'], supply['object_id'],
                    supply['line_id'], demand['object_type'],
                    demand['object_id'], demand['line_id'], qty)
        return {'link': link, 'created': True, 'updated': False}

    def unlink(self, link_id: Any, reason: str = '') -> Dict[str, Any]:
        """逻辑关闭 trace（valid_to = now），重复关闭幂等。"""
        row = self._load(link_id)
        if row.get('valid_to'):
            return row
        self.ds.execute(
            'UPDATE %s SET valid_to = ?, remark = ? WHERE id = ?' % TRACE_TABLE,
            [_now(), reason or row.get('remark'), row['id']])
        return self._load(row['id'])

    # ------------------------------------------------------------------
    # 继承与追溯
    # ------------------------------------------------------------------
    def inherit_from_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """从单据行与预留推导 trace：供应节点 = 单据行，需求 = 预留需求节点。

        doc:
          {doc_type, doc_id, lines: [{line_id, qty, source_doc_type,
                                      source_doc_id, source_line_id}]}
        无匹配预留时按来源行直接链接到销售订单行需求。
        """
        data = dict(doc or {})
        doc_type = str(data.get('doc_type') or '')
        doc_id = _to_int(data.get('doc_id'))
        if doc_type not in NODE_TYPES or not doc_id:
            raise InventoryError(
                INV_TRACE_NODE_INVALID, 'inherit 缺少合法单据类型或 ID',
                {'doc_type': doc_type, 'doc_id': doc_id})
        created = 0
        updated = 0
        skipped = 0
        for line in data.get('lines') or []:
            qty = _num(line.get('qty'))
            line_id = _to_int(line.get('line_id'))
            if qty <= 0 or not line_id:
                skipped += 1
                continue
            demand = self._resolve_line_demand(line)
            if not demand:
                skipped += 1
                continue
            payload = {
                'supply_object_type': doc_type,
                'supply_object_id': doc_id,
                'supply_line_id': line_id,
                'demand_object_type': demand['object_type'],
                'demand_object_id': demand['object_id'],
                'demand_line_id': demand['line_id'],
                'trace_type': TRACE_RESERVATION,
                'peg_type': demand.get('peg_type') or PEG_SOFT,
                'allocated_qty': qty,
                'source_doc_type': data.get('source_doc_type')
                or line.get('source_doc_type'),
                'source_doc_id': data.get('source_doc_id')
                or line.get('source_doc_id'),
                'source_line_id': line.get('source_line_id'),
                'remark': data.get('remark'),
            }
            try:
                result = self.link_supply_demand(payload)
            except InventoryError as exc:
                logger.warning('[inv2] trace 继承跳过 %s:%s: %s',
                               doc_type, line_id, exc)
                skipped += 1
                continue
            if result.get('created'):
                created += 1
            elif result.get('updated'):
                updated += 1
            else:
                skipped += 1
        logger.info('[inv2] trace 继承 %s:%s created=%s updated=%s skipped=%s',
                    doc_type, doc_id, created, updated, skipped)
        return {'created': created, 'updated': updated, 'skipped': skipped}

    def trace_end_demand(self, supply_node: Dict[str, Any]) -> Dict[str, Any]:
        """从供应节点迭代追溯到最终需求（需求节点亦可作为下一跳供应）。"""
        if not self._table_ready():
            return {'demands': [], 'hops': 0}
        start = (_node_key({'object_type': supply_node.get('object_type')
                            or supply_node.get('supply_object_type'),
                            'object_id': supply_node.get('object_id')
                            or supply_node.get('supply_object_id'),
                            'line_id': supply_node.get('line_id')
                            or supply_node.get('supply_line_id')}))
        if start[0] not in NODE_TYPES or not start[1]:
            raise InventoryError(
                INV_TRACE_NODE_INVALID, '追溯缺少合法供应节点', {'node': start})

        frontier: List[Tuple[Tuple[str, int, int], float]] = [(start, 0.0)]
        visited: Set[Tuple[str, int, int]] = {start}
        terminals: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
        hops = 0
        while frontier:
            current, inherited = frontier.pop(0)
            links: List[Dict[str, Any]] = self._links_by_supply(current)
            matched = 0
            for link in links:
                matched += 1
                qty = _num(link.get('allocated_qty'))
                amount = (qty if inherited <= 0 else min(inherited, qty))
                demand_key = (str(link.get('demand_object_type')),
                              _to_int(link.get('demand_object_id')),
                              _to_int(link.get('demand_line_id')))
                if demand_key in visited:
                    continue
                if self._is_supply_node(demand_key):
                    visited.add(demand_key)
                    frontier.append((demand_key, amount))
                else:
                    entry = terminals.setdefault(demand_key, {
                        'object_type': demand_key[0],
                        'object_id': demand_key[1],
                        'line_id': demand_key[2],
                        'allocated_qty': 0.0,
                    })
                    entry['allocated_qty'] += amount
            if matched:
                hops += 1
            elif inherited <= 0:
                terminals.setdefault(start, {
                    'object_type': start[0], 'object_id': start[1],
                    'line_id': start[2], 'allocated_qty': inherited})
        return {'demands': list(terminals.values()), 'hops': hops}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _resolve_line_demand(self, line: Dict[str, Any]
                             ) -> Optional[Dict[str, Any]]:
        source_type = str(line.get('source_doc_type') or '').strip()
        source_id = _to_int(line.get('source_doc_id'))
        source_line = _to_int(line.get('source_line_id'))
        if not source_id or not source_line:
            return None
        if self._table_ready() and \
                source_type == 'sales_order':
            rows = self.ds.query(
                'SELECT peg_type, demand_object_type, demand_object_id, '
                'demand_line_id FROM %s WHERE source_doc_type = ? '
                'AND source_doc_id = ? AND source_line_id = ? '
                'AND status IN (?, ?) LIMIT 1' % 'inventory_reservations',
                [source_type, source_id, source_line, 'open',
                 'partially_fulfilled'])
            if rows:
                row = rows[0]
                return {
                    'object_type': row.get('demand_object_type'),
                    'object_id': _to_int(row.get('demand_object_id')),
                    'line_id': _to_int(row.get('demand_line_id')),
                    'peg_type': row.get('peg_type'),
                }
            return {'object_type': 'sales_order_line',
                    'object_id': source_line, 'line_id': source_line,
                    'peg_type': PEG_SOFT}
        if source_type in NODE_TYPES and source_id:
            return {'object_type': source_type, 'object_id': source_id,
                    'line_id': source_line, 'peg_type': PEG_SOFT}
        return None

    def _assert_capacity(self, supply: Dict[str, Any], demand: Dict[str, Any],
                         trace_type: str, qty: float,
                         exclude_id: int = 0) -> None:
        for node, label in ((supply, 'supply'), (demand, 'demand')):
            node_type = str(node.get('object_type') or '')
            node_id = _to_int(node.get('object_id'))
            line_id = _to_int(node.get('line_id'))
            capacity = self._node_qty(node_type, node_id, line_id)
            if capacity is None:
                continue
            used = self._allocated_for(node, trace_type, label, exclude_id)
            if used + qty > capacity + 1e-9:
                raise InventoryError(
                    INV_TRACE_QTY_EXCEEDED,
                    '%s 节点分配量超限' % label,
                    {'node': node, 'capacity': capacity,
                     'allocated': used, 'qty': qty})

    def _node_qty(self, node_type: str, node_id: int,
                  line_id: int) -> Optional[float]:
        mapping = NODE_QTY.get(node_type)
        if not mapping or not node_id:
            return None
        table, column = mapping
        key = line_id or node_id
        try:
            rows = self.ds.query(
                'SELECT %s AS qty FROM %s WHERE id = ?' % (column, table),
                [key])
        except Exception:
            return None
        if not rows:
            return None
        return _num(rows[0].get('qty'))

    def _allocated_for(self, node: Dict[str, Any], trace_type: str,
                       role: str, exclude_id: int = 0) -> float:
        node_type = str(node.get('object_type') or '')
        node_id = _to_int(node.get('object_id'))
        line_id = _to_int(node.get('line_id'))
        if role == 'supply':
            sql = ('SELECT COALESCE(SUM(allocated_qty), 0) AS total FROM %s '
                   'WHERE valid_to IS NULL AND trace_type = ? AND id <> ? '
                   'AND supply_object_type = ? AND supply_object_id = ? '
                   'AND supply_line_id = ?' % TRACE_TABLE)
        else:
            sql = ('SELECT COALESCE(SUM(allocated_qty), 0) AS total FROM %s '
                   'WHERE valid_to IS NULL AND trace_type = ? AND id <> ? '
                   'AND demand_object_type = ? AND demand_object_id = ? '
                   'AND demand_line_id = ?' % TRACE_TABLE)
        rows = self.ds.query(sql,
                             [trace_type, _to_int(exclude_id), node_type,
                              node_id, line_id])
        return _num(rows[0].get('total')) if rows else 0.0

    def _links_by_supply(self,
                         node: Tuple[str, int, int]) -> List[Dict[str, Any]]:
        return self.ds.query(
            'SELECT * FROM %s WHERE valid_to IS NULL '
            'AND supply_object_type = ? AND supply_object_id = ? '
            'AND supply_line_id = ?' % TRACE_TABLE,
            [node[0], node[1], node[2]])

    @staticmethod
    def _is_supply_node(node: Tuple[str, int, int]) -> bool:
        return node[0] in ('purchase_order_line', 'work_order',
                           'work_order_component', 'inventory_balance',
                           'inventory_transaction', 'transfer_order_line',
                           'receipt_line', 'shipment', 'shipment_line')

    def _find_active(self, supply: Dict[str, Any], demand: Dict[str, Any],
                     trace_type: str) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE supply_object_type = ? '
            'AND supply_object_id = ? AND supply_line_id = ? '
            'AND demand_object_type = ? AND demand_object_id = ? '
            'AND demand_line_id = ? AND trace_type = ? AND valid_to IS NULL '
            'LIMIT 1' % TRACE_TABLE,
            [supply['object_type'], _to_int(supply['object_id']),
             _to_int(supply['line_id']), demand['object_type'],
             _to_int(demand['object_id']), _to_int(demand['line_id']),
             trace_type])
        return rows[0] if rows else None

    def _load(self, link_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ?' % TRACE_TABLE,
            [_to_int(link_id)])
        if not rows:
            raise InventoryError(INV_TRACE_NOT_FOUND,
                                 '需求线索不存在: %s' % link_id,
                                 {'link_id': link_id})
        return rows[0]
