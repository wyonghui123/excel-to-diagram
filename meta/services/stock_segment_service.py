# -*- coding: utf-8 -*-
"""库存段服务 —— INV-2 S1/S4/S5 的段解析、校验、转移唯一入口。

依据:
  docs/specs/inv2-reservation-atp/spec.md §3.6 / §3.7 / §4.1

口径:
  ① 段类型有限枚举 + 强类型伙伴列，0 哨兵；不建通用 EAV 段表。
  ② 解析优先级：供应商寄售 > 项目任务 > 销售订单行 > 自有。
  ③ 项目段固定任务级；单任务项目由 ensure_root_task 自动建根任务。
  ④ 段不可原地修改，变更只能走 transfer_segment（成对出/入）。
  ⑤ customer_owned 本期一律拒绝（枚举保留、默认禁用）。
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from meta.services.inventory_guard_service import InventoryError

logger = logging.getLogger(__name__)

SEGMENT_OWNED = 'owned'
SEGMENT_PROJECT_TASK = 'project_task'
SEGMENT_SALES_ORDER_LINE = 'sales_order_line'
SEGMENT_SUPPLIER_CONSIGNMENT = 'supplier_consignment'
SEGMENT_CUSTOMER_OWNED = 'customer_owned'

SEGMENT_TYPES = (
    SEGMENT_OWNED,
    SEGMENT_PROJECT_TASK,
    SEGMENT_SALES_ORDER_LINE,
    SEGMENT_SUPPLIER_CONSIGNMENT,
    SEGMENT_CUSTOMER_OWNED,
)

PARTNER_COLUMNS = (
    'project_id', 'project_task_id', 'sales_order_line_id', 'owner_party_id',
)

SEGMENT_COLUMNS = ('stock_segment_type',) + PARTNER_COLUMNS

DEFAULT_SEGMENT: Dict[str, Any] = {
    'stock_segment_type': SEGMENT_OWNED,
    'project_id': 0,
    'project_task_id': 0,
    'sales_order_line_id': 0,
    'owner_party_id': 0,
}

TRANSFER_OUT_TYPE = 'SEG_TRANSFER_OUT'
TRANSFER_IN_TYPE = 'SEG_TRANSFER_IN'

INV_SEGMENT_INVALID = 'INV_SEGMENT_INVALID'
INV_SEGMENT_PARTNER_MISMATCH = 'INV_SEGMENT_PARTNER_MISMATCH'
INV_CROSS_SEGMENT_DENIED = 'INV_CROSS_SEGMENT_DENIED'
INV_SO_SEGMENT_DISABLED = 'INV_SO_SEGMENT_DISABLED'
INV_CONSIGNMENT_OWNER_REQUIRED = 'INV_CONSIGNMENT_OWNER_REQUIRED'


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


class StockSegmentService:
    """段解析/校验/转移。构造函数可注入 data_source 与过账服务（单测替身）。"""

    def __init__(self, data_source, posting_service=None):
        self.ds = data_source
        self._posting = posting_service

    # ------------------------------------------------------------------
    # 元数据读取
    # ------------------------------------------------------------------
    def _table_exists(self, name: str) -> bool:
        try:
            return bool(self.ds.query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                [name]))
        except Exception:
            return False

    def item_flags(self, item_id: int) -> Dict[str, int]:
        flags = {
            'so_segment_enabled': 0,
            'consignment_enabled': 0,
            'hard_peg_default': 0,
            'valuation_relevant': 1,
        }
        if not item_id or not self._table_exists('items'):
            return flags
        try:
            rows = self.ds.query(
                'SELECT so_segment_enabled, consignment_enabled, '
                'hard_peg_default, valuation_relevant FROM items WHERE id = ?',
                [item_id])
        except Exception:
            return flags
        if rows:
            row = rows[0]
            for key in flags:
                if row.get(key) is not None:
                    flags[key] = _to_int(row.get(key))
        return flags

    # ------------------------------------------------------------------
    # 解析与校验
    # ------------------------------------------------------------------
    def resolve_segment(self, doc_ctx: Dict[str, Any]) -> Dict[str, Any]:
        """按 §3.6 解析段；非法组合抛 InventoryError。

        doc_ctx 可显式携带 item 策略覆盖（so_segment_enabled /
        consignment_enabled），便于计划/单据在物料主档缺失时显式声明。
        """
        ctx = dict(doc_ctx or {})
        item_id = _to_int(ctx.get('item_id'))
        flags = self.item_flags(item_id)
        for key in ('so_segment_enabled', 'consignment_enabled'):
            if ctx.get(key) is not None:
                flags[key] = _to_int(ctx.get(key))

        owner = _to_int(ctx.get('owner_party_id'))
        task = _to_int(ctx.get('project_task_id'))
        project = _to_int(ctx.get('project_id'))
        so_line = _to_int(ctx.get('sales_order_line_id'))
        requested = str(ctx.get('stock_segment_type') or '').strip()

        if requested == SEGMENT_CUSTOMER_OWNED:
            raise InventoryError(
                INV_SEGMENT_INVALID,
                '客户所有段本期不启用（customer_owned）',
                {'item_id': item_id})

        if owner:
            if not flags['consignment_enabled']:
                raise InventoryError(
                    INV_SEGMENT_PARTNER_MISMATCH,
                    '物料未开启供应商寄售，不能写入所有权方',
                    {'item_id': item_id, 'owner_party_id': owner})
            if task or so_line:
                raise InventoryError(
                    INV_SEGMENT_INVALID,
                    '寄售段不能同时携带项目任务或销售订单行',
                    {'owner_party_id': owner})
            return {
                'stock_segment_type': SEGMENT_SUPPLIER_CONSIGNMENT,
                'project_id': 0, 'project_task_id': 0,
                'sales_order_line_id': 0, 'owner_party_id': owner,
            }

        if not task and project and ctx.get('ensure_root_task'):
            task = self.ensure_root_task(project)

        if task:
            if not project:
                project = self._project_of_task(task)
            if not project:
                raise InventoryError(
                    INV_SEGMENT_PARTNER_MISMATCH,
                    '项目任务缺少所属项目',
                    {'project_task_id': task})
            if so_line:
                raise InventoryError(
                    INV_SEGMENT_INVALID,
                    '项目任务段不能同时携带销售订单行',
                    {'project_task_id': task, 'sales_order_line_id': so_line})
            segment = {
                'stock_segment_type': SEGMENT_PROJECT_TASK,
                'project_id': project, 'project_task_id': task,
                'sales_order_line_id': 0, 'owner_party_id': 0,
            }
            self._assert_task_belongs(task, project, ctx.get('org_id'))
            return segment

        if so_line:
            if not flags['so_segment_enabled']:
                raise InventoryError(
                    INV_SO_SEGMENT_DISABLED,
                    '物料未开启销售订单专用段',
                    {'item_id': item_id, 'sales_order_line_id': so_line})
            self._assert_so_line_matches(so_line, item_id)
            return {
                'stock_segment_type': SEGMENT_SALES_ORDER_LINE,
                'project_id': 0, 'project_task_id': 0,
                'sales_order_line_id': so_line, 'owner_party_id': 0,
            }

        if project:
            raise InventoryError(
                INV_SEGMENT_PARTNER_MISMATCH,
                '项目归属必须落到具体任务（项目段固定任务级）',
                {'project_id': project})

        return dict(DEFAULT_SEGMENT)

    def validate_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """校验并返回规范化段；非法组合抛 InventoryError。"""
        raw = dict(segment or {})
        seg_type = str(raw.get('stock_segment_type') or SEGMENT_OWNED)
        if seg_type not in SEGMENT_TYPES:
            raise InventoryError(
                INV_SEGMENT_INVALID, '未知库存段类型: %s' % seg_type,
                {'stock_segment_type': seg_type})
        if seg_type == SEGMENT_CUSTOMER_OWNED:
            raise InventoryError(
                INV_SEGMENT_INVALID, '客户所有段本期不启用（customer_owned）',
                {'stock_segment_type': seg_type})

        normalized = {'stock_segment_type': seg_type}
        for col in PARTNER_COLUMNS:
            normalized[col] = _to_int(raw.get(col))

        project = normalized['project_id']
        task = normalized['project_task_id']
        so_line = normalized['sales_order_line_id']
        owner = normalized['owner_party_id']

        if seg_type == SEGMENT_OWNED:
            if project or task or so_line or owner:
                raise InventoryError(
                    INV_SEGMENT_INVALID,
                    '自有段不允许非 0 伙伴列',
                    {'segment': normalized})
        elif seg_type == SEGMENT_PROJECT_TASK:
            if not project or not task:
                raise InventoryError(
                    INV_SEGMENT_PARTNER_MISMATCH,
                    '项目任务段必须同时提供 project_id 与 project_task_id',
                    {'segment': normalized})
            if so_line or owner:
                raise InventoryError(
                    INV_SEGMENT_INVALID,
                    '项目任务段不允许携带销售订单行或所有权方',
                    {'segment': normalized})
            self._assert_task_belongs(task, project, raw.get('org_id'))
        elif seg_type == SEGMENT_SALES_ORDER_LINE:
            if not so_line:
                raise InventoryError(
                    INV_SEGMENT_PARTNER_MISMATCH,
                    '销售订单段必须提供 sales_order_line_id',
                    {'segment': normalized})
            if project or task or owner:
                raise InventoryError(
                    INV_SEGMENT_INVALID,
                    '销售订单段不允许携带项目/任务/所有权方',
                    {'segment': normalized})
            item_id = _to_int(raw.get('item_id'))
            if item_id:
                flags = self.item_flags(item_id)
                if not flags['so_segment_enabled']:
                    raise InventoryError(
                        INV_SO_SEGMENT_DISABLED,
                        '物料未开启销售订单专用段',
                        {'item_id': item_id, 'sales_order_line_id': so_line})
                self._assert_so_line_matches(so_line, item_id)
        else:
            if not owner:
                raise InventoryError(
                    INV_CONSIGNMENT_OWNER_REQUIRED,
                    '供应商寄售段必须提供 owner_party_id',
                    {'segment': normalized})
            if project or task or so_line:
                raise InventoryError(
                    INV_SEGMENT_INVALID,
                    '寄售段不允许携带项目/任务/销售订单行',
                    {'segment': normalized})
            item_id = _to_int(raw.get('item_id'))
            if item_id and not self.item_flags(item_id)['consignment_enabled']:
                raise InventoryError(
                    INV_SEGMENT_INVALID,
                    '物料未开启供应商寄售',
                    {'item_id': item_id,
                     'stock_segment_type': seg_type})
        return normalized

    def segment_key(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """生成余额键/查询键（0 哨兵）。调用前应已 validate。"""
        normalized = self.validate_segment(segment)
        return {col: normalized[col] for col in SEGMENT_COLUMNS}

    # ------------------------------------------------------------------
    # 辅助校验
    # ------------------------------------------------------------------
    def _project_of_task(self, task_id: int) -> int:
        if not task_id or not self._table_exists('project_tasks'):
            return 0
        rows = self.ds.query(
            'SELECT project_id FROM project_tasks WHERE id = ?', [task_id])
        return _to_int(rows[0].get('project_id')) if rows else 0

    def _assert_task_belongs(self, task_id: int, project_id: int,
                             org_id: Any = None) -> None:
        if not self._table_exists('project_tasks'):
            return
        rows = self.ds.query(
            'SELECT project_id FROM project_tasks WHERE id = ?',
            [task_id])
        if not rows:
            raise InventoryError(
                INV_SEGMENT_PARTNER_MISMATCH,
                '项目任务不存在: %s' % task_id,
                {'project_task_id': task_id})
        row = rows[0]
        if _to_int(row.get('project_id')) != _to_int(project_id):
            raise InventoryError(
                INV_SEGMENT_PARTNER_MISMATCH,
                '项目任务 %s 不属于项目 %s' % (task_id, project_id),
                {'project_task_id': task_id, 'project_id': project_id})

    def _assert_so_line_matches(self, line_id: int, item_id: int) -> None:
        if not self._table_exists('sales_order_lines'):
            return
        rows = self.ds.query(
            'SELECT item_id FROM sales_order_lines WHERE id = ?', [line_id])
        if not rows:
            raise InventoryError(
                INV_SEGMENT_PARTNER_MISMATCH,
                '销售订单行不存在: %s' % line_id,
                {'sales_order_line_id': line_id})
        line_item = _to_int(rows[0].get('item_id'))
        if item_id and line_item and line_item != item_id:
            raise InventoryError(
                INV_SEGMENT_PARTNER_MISMATCH,
                '销售订单行 %s 物料与 %s 不一致' % (line_id, item_id),
                {'sales_order_line_id': line_id, 'item_id': item_id})

    def ensure_root_task(self, project_id: int) -> int:
        """单任务项目无任务时自动建根任务（幂等），返回 project_task_id。"""
        project_id = _to_int(project_id)
        if not project_id:
            raise InventoryError(
                INV_SEGMENT_PARTNER_MISMATCH, '缺少 project_id')
        if not self._table_exists('project_tasks'):
            return 0
        rows = self.ds.query(
            'SELECT id FROM project_tasks WHERE project_id = ? '
            'ORDER BY id LIMIT 1', [project_id])
        if rows:
            return _to_int(rows[0].get('id'))
        project = {}
        if self._table_exists('projects'):
            found = self.ds.query(
                'SELECT id, org_id, name FROM projects WHERE id = ?',
                [project_id])
            project = found[0] if found else {}
        task_no = 'ROOT'
        self.ds.execute(
            'INSERT INTO project_tasks '
            '(project_id, task_no, name, task_type, status, parent_task_id) '
            "VALUES (?, ?, ?, 'activity', 'draft', NULL)",
            [project_id, task_no, '根任务'],
        )
        rows = self.ds.query(
            'SELECT id FROM project_tasks WHERE project_id = ? AND task_no = ?',
            [project_id, task_no])
        task_id = _to_int(rows[0].get('id')) if rows else 0
        logger.info('[inv2] 项目 %s 自动建根任务 id=%s', project_id, task_id)
        return task_id

    # ------------------------------------------------------------------
    # 跨段校验与段转移
    # ------------------------------------------------------------------
    def assert_cross_segment_allowed(self, from_seg: Dict[str, Any],
                                     to_seg: Dict[str, Any],
                                     ctx: Optional[Dict[str, Any]] = None) -> None:
        ctx = ctx or {}
        source = self.validate_segment(from_seg)
        target = self.validate_segment(to_seg)
        if source == target:
            return
        if source['stock_segment_type'] == SEGMENT_PROJECT_TASK \
                and target['stock_segment_type'] == SEGMENT_PROJECT_TASK:
            if source['project_id'] != target['project_id'] \
                    and not ctx.get('allow_cross_project'):
                raise InventoryError(
                    INV_CROSS_SEGMENT_DENIED,
                    '禁止跨项目转移库存段',
                    {'from': source, 'to': target})
        if source['stock_segment_type'] == SEGMENT_SALES_ORDER_LINE \
                and target['stock_segment_type'] == SEGMENT_SALES_ORDER_LINE:
            if source['sales_order_line_id'] != target['sales_order_line_id'] \
                    and not ctx.get('allow_cross_sales_order'):
                raise InventoryError(
                    INV_CROSS_SEGMENT_DENIED,
                    '禁止跨销售订单行转移库存段',
                    {'from': source, 'to': target})
        if source['owner_party_id'] != target['owner_party_id'] \
                and not ctx.get('allow_cross_owner'):
            raise InventoryError(
                INV_CROSS_SEGMENT_DENIED,
                '禁止跨所有权方转移库存段',
                {'from': source, 'to': target})

    def _posting_service(self):
        if self._posting is not None:
            return self._posting
        from meta.services.inventory_posting_service import InventoryPostingService
        self._posting = InventoryPostingService(self.ds)
        return self._posting

    def transfer_segment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """段转移：成对出/入分录，数量守恒；禁止普通收发模拟。"""
        from_seg = payload.get('from_segment') or {}
        to_seg = payload.get('to_segment') or {}
        source_seg = self.validate_segment(from_seg)
        target_seg = self.validate_segment(to_seg)
        self.assert_cross_segment_allowed(source_seg, target_seg, payload)

        qty = _num(payload.get('qty'))
        if qty <= 0:
            raise InventoryError(
                'INV_ENTRY_INVALID', '段转移数量必须大于 0',
                {'qty': payload.get('qty')})
        org_id = _to_int(payload.get('org_id'))
        item_id = _to_int(payload.get('item_id'))
        location_id = _to_int(payload.get('location_id'))
        if not org_id or not item_id or not location_id:
            raise InventoryError(
                'INV_ENTRY_INVALID', '段转移缺少组织/物料/库位',
                {'org_id': org_id, 'item_id': item_id,
                 'location_id': location_id})

        event_key = str(payload.get('source_event_key') or '').strip()
        if not event_key:
            raise InventoryError('INV_SOURCE_REQUIRED',
                                 '段转移缺少来源事件键')
        doc_type = payload.get('source_doc_type') or 'inventory_segment_transfer'
        doc_id = payload.get('source_doc_id') or 0
        line_id = _to_int(payload.get('source_line_id')) or 1
        batch_id = _to_int(payload.get('batch_id'))
        stock_status = payload.get('stock_status') or 'unrestricted'
        uom_id = _to_int(payload.get('uom_id')) or item_id
        group_id = payload.get('transfer_group_id') or (
            'SEGT-%s' % uuid.uuid4().hex[:12])
        remark = payload.get('remark') or payload.get('reason') or ''
        txn_date = payload.get('transaction_date') or _now()[:10]

        posting = self._posting_service()
        base = {
            'org_id': org_id, 'location_id': location_id, 'item_id': item_id,
            'uom_id': uom_id, 'batch_id': batch_id,
            'stock_status': stock_status,
            'transaction_date': txn_date, 'created_by': payload.get('created_by'),
        }
        out_entry = dict(base)
        out_entry.update(source_seg)
        out_entry.update({
            'direction': 'out', 'qty': qty, 'base_qty': qty,
            'transaction_type_id': TRANSFER_OUT_TYPE,
            'source_line_id': line_id,
            'remark': ('段转移转出: %s' % remark).strip(),
        })
        in_entry = dict(base)
        in_entry.update(target_seg)
        in_entry.update({
            'direction': 'in', 'qty': qty, 'base_qty': qty,
            'transaction_type_id': TRANSFER_IN_TYPE,
            'source_line_id': line_id + 1,
            'remark': ('段转移转入: %s' % remark).strip(),
        })
        source = {
            'source_doc_type': doc_type,
            'source_doc_id': doc_id,
            'source_event_key': event_key,
            'transaction_date': txn_date,
            'transfer_group_id': group_id,
            'created_by': payload.get('created_by'),
            'remark': remark,
        }
        result = posting.post([out_entry, in_entry], source)
        logger.info('[inv2] 段转移 %s: %s -> %s qty=%s created=%s',
                    group_id, source_seg['stock_segment_type'],
                    target_seg['stock_segment_type'], qty, result['created'])
        return {
            'transfer_group_id': group_id,
            'from_segment': source_seg,
            'to_segment': target_seg,
            'qty': qty,
            'result': result,
        }

    # ------------------------------------------------------------------
    # 生命周期辅助
    # ------------------------------------------------------------------
    def prune_empty_balances(self, segment: Dict[str, Any]) -> int:
        """清理指定段下已无在库/预留的余额投影行，返回删除行数。"""
        seg = self.validate_segment(segment)
        if not self._table_exists('inventory_balances'):
            return 0
        clause = ' AND '.join('%s = ?' % col for col in SEGMENT_COLUMNS)
        params = [seg['stock_segment_type']]
        params.extend(_to_int(seg[col]) for col in SEGMENT_COLUMNS[1:])
        rows = self.ds.query(
            'SELECT id FROM inventory_balances WHERE qty_on_hand = 0 '
            'AND qty_reserved = 0 AND ' + clause, params)
        if not rows:
            return 0
        ids = [row['id'] for row in rows]
        placeholders = ', '.join('?' for _ in ids)
        self.ds.execute(
            'DELETE FROM inventory_balances WHERE id IN (%s)' % placeholders,
            ids)
        logger.info('[inv2] 清理空段余额 %s 条 segment=%s',
                    len(ids), seg['stock_segment_type'])
        return len(ids)

    def consume_consignment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """寄售消耗：供应商所有 → 自有，等价成对段转移 + 计价标记。"""
        from_seg = dict(payload.get('from_segment') or {})
        from_seg.setdefault('stock_segment_type', SEGMENT_SUPPLIER_CONSIGNMENT)
        payload = dict(payload)
        payload['from_segment'] = from_seg
        payload['reason'] = payload.get('reason') or 'CONSIGN_CONSUME'
        payload['allow_cross_owner'] = True
        payload['remark'] = ('寄售消耗/所有权转移 %s'
                             % (payload.get('remark') or '')).strip()
        return self.transfer_segment(payload)

