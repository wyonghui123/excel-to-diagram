# -*- coding: utf-8 -*-
"""需求分配 → 调拨单（TBD-4）

口径:
  · 只消费 `demand_allocations.status='active'` 的分配记录；
  · 分配 `target_bo` 为空 / `inventory`（尚未落执行载体）或 `transfer_order`
    但尚无 `target_id`（已登记待转）时，按分配数量整笔转换；
  · 已指向其他单据（`purchase_order` / `receipt` / `work_order` /
    `sales_order`）或已落到某张调拨单的分配视为已消耗，拒绝重复转换；
  · 物料 / 单位 / 行号取需求行（本波支持 `demand_bo='requisition'`）；
  · 行按「物料 + 单位」聚合，行类型走 `LineTypeResolver(scope_bo='transfer_order')`
    按物料组确定，未命中回落头类型 `default_type_id`；
  · 取号在事务外（`TransferOrderService.allocate_transfer_order_no`），
    头 / 行 / 分配回写在同一 `bo_framework.transaction()` 内原子完成；
  · 不写库存台账 / 可用量 / 在途表。

入口：BO Action `transfer_order.create_from_allocation`
（注册于 `meta/services/bo_action_registrations.py`）。
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from meta.core.doc_flow_attach import attach_edge

logger = logging.getLogger(__name__)

OBJECT_TYPE = 'transfer_order'
LINE_OBJECT_TYPE = 'transfer_order_line'
HEADER_TABLE = 'transfer_orders'
ALLOCATION_TABLE = 'demand_allocations'
REQUISITION_LINE_TABLE = 'requisition_lines'
ITEM_TABLE = 'items'
TYPE_TABLE = 'type_definitions'

DEFAULT_HEADER_TYPE_CODE = 'TRF_STD'
HEADER_SCOPE_BO = 'transfer_order'

_ALLOCATION_ACTIVE = 'active'
_ALLOCATION_REVERSED = 'reversed'
#: 尚未落到具体执行载体的 target_bo（可整笔转换）
_UNASSIGNED_TARGET_BOS = (None, '', 'inventory', 'transfer_order')
#: 已落到其他执行载体 ⇒ 需求已被消耗
_PEGGED_TARGET_BOS = ('purchase_order', 'receipt', 'work_order', 'sales_order')


class ConversionError(Exception):
    """转单失败（message 直接回给调用方，code 用于区分原因）。"""

    def __init__(self, message: str, code: str = 'CONVERSION_FAILED'):
        super().__init__(message)
        self.message = message
        self.code = code


class TransferOrderFromAllocationService:
    """需求分配 → 调拨单（草稿）。"""

    def __init__(self, data_source=None, framework=None, platform_data_source=None):
        self._ds = data_source
        self._framework = framework
        self._platform_ds = platform_data_source

    # ------------------------------------------------------------------ 依赖
    @property
    def ds(self):
        if self._ds is None:
            from meta.core.datasource import get_data_source
            from meta.core.db_path import get_meta_db_path
            self._ds = get_data_source('sqlite', database=get_meta_db_path())
        return self._ds

    @property
    def platform_ds(self):
        """平台库（doc_flow_rule）；未配置时回落应用库（单库部署）。"""
        if self._platform_ds is None:
            try:
                from meta.core.datasource import get_platform_data_source
                self._platform_ds = get_platform_data_source() or self.ds
            except Exception:  # noqa: BLE001 - 未配置平台库
                self._platform_ds = self.ds
        return self._platform_ds

    @property
    def framework(self):
        if self._framework is None:
            from meta.core.bo_framework import bo_framework
            self._framework = bo_framework
        return self._framework

    # ------------------------------------------------------------------ 转换
    def create_from_allocation(
            self, allocation_ids: List[Any], from_org_id: Any, to_org_id: Any,
            transfer_date: Any, document_type_id: Any = None,
            project_id: Any = None, remark: Any = None,
            from_location_id: Any = None, to_location_id: Any = None
    ) -> Dict[str, Any]:
        """把需求分配记录转成一张草稿调拨单。

        Args:
            allocation_ids: `demand_allocations.id` 列表（可跨需求行）
            from_org_id / to_org_id: 调出 / 调入库存组织
            transfer_date: 调拨日期（取号日期段基准）
            document_type_id: 缺省解析 `scope_bo='transfer_order'` +
                `level='header'` + `code='TRF_STD'`
            project_id / remark / from_location_id / to_location_id: 头可选字段

        Returns:
            `{'transfer_order_id', 'transfer_order_no', 'lines': [...],
               'allocations': [...]}`

        Raises:
            ConversionError: 分配不可消费 / 超量 / 组织法人非法 / BO 写失败
        """
        ids = _normalize_ids(allocation_ids)
        if not ids:
            raise ConversionError('缺少 allocation_ids', 'INVALID_ARGUMENT')
        if _blank(from_org_id) or _blank(to_org_id) or _blank(transfer_date):
            raise ConversionError(
                '缺少 from_org_id / to_org_id / transfer_date',
                'INVALID_ARGUMENT')

        allocations = self._load_allocations(ids)
        picked = self._resolve_allocations(allocations)
        if not picked:
            raise ConversionError('没有可转换的需求分配', 'NO_CONVERTIBLE_ALLOCATIONS')

        header_data = self._build_header(
            from_org_id, to_org_id, transfer_date, document_type_id,
            project_id, remark, from_location_id, to_location_id)
        line_groups, demand_lines = self._resolve_lines(picked)
        line_type_ids = self._line_type_ids(
            header_data['document_type_id'], line_groups)

        result = {'transfer_order_id': None, 'transfer_order_no': None,
                  'lines': [], 'allocations': []}
        with self.framework.transaction():
            header_result = self.framework.execute(
                OBJECT_TYPE, 'crud_create', header_data)
            if not header_result or not header_result.success:
                raise ConversionError(
                    '创建调拨单失败: %s'
                    % getattr(header_result, 'message', '未知错误'),
                    'TRANSFER_ORDER_CREATE_FAILED')
            to_id = self._created_id(header_result)
            result['transfer_order_id'] = to_id
            result['transfer_order_no'] = (
                (header_result.data or {}).get('transfer_order_no')
                or header_data.get('transfer_order_no'))

            for seq, group in enumerate(line_groups, start=1):
                line_data = self._build_line(to_id, seq, group, line_type_ids)
                line_result = self.framework.execute(
                    LINE_OBJECT_TYPE, 'crud_create', line_data)
                if not line_result or not line_result.success:
                    raise ConversionError(
                        '创建调拨行失败（物料 %s）: %s'
                        % (group['item_id'],
                           getattr(line_result, 'message', '未知错误')),
                        'TRANSFER_ORDER_LINE_CREATE_FAILED')
                line_id = self._created_id(line_result)
                result['lines'].append({
                    'item_id': group['item_id'],
                    'uom_id': group['uom_id'],
                    'transfer_order_line_id': line_id,
                    'qty': float(group['qty']),
                    'allocation_ids': list(group['allocation_ids']),
                })

            self._write_back(picked, demand_lines, to_id, result['lines'])
            result['allocations'] = [row['id'] for row in picked]

        logger.info('[TransferOrderFromAllocation] %d 笔分配 → %s，%d 行',
                    len(picked), result.get('transfer_order_no'),
                    len(result['lines']))
        return result

    # ------------------------------------------------------------------ 读
    def _load_allocations(self, allocation_ids: List[int]) -> List[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, demand_bo, demand_id, demand_line_id, demand_line_no, '
            'qty, uom_id, cost_center_id, target_bo, target_id, target_line_id, '
            'status FROM %s WHERE id IN (%s)'
            % (ALLOCATION_TABLE, ','.join(['?'] * len(allocation_ids))),
            allocation_ids)
        found = {row['id'] for row in rows}
        missing = [i for i in allocation_ids if i not in found]
        if missing:
            raise ConversionError('需求分配不存在: %s' % missing,
                                  'ALLOCATION_NOT_FOUND')
        return rows

    def _resolve_allocations(
            self, allocations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        picked = []
        for row in allocations:
            status = str(row.get('status') or '').strip().lower()
            if status != _ALLOCATION_ACTIVE:
                raise ConversionError(
                    '需求分配 %s 状态 %s 不可转换'
                    % (row.get('id'), row.get('status') or status),
                    'ALLOCATION_NOT_ACTIVE')
            target_bo = str(row.get('target_bo') or '').strip().lower() or None
            if target_bo in _PEGGED_TARGET_BOS:
                raise ConversionError(
                    '需求分配 %s 已指向 %s，不能重复转调拨单'
                    % (row.get('id'), target_bo),
                    'ALLOCATION_ALREADY_PEGGED')
            if target_bo not in _UNASSIGNED_TARGET_BOS:
                raise ConversionError(
                    '需求分配 %s 的执行对象 %s 不可转换为调拨单'
                    % (row.get('id'), target_bo),
                    'ALLOCATION_TARGET_INVALID')
            if target_bo == 'transfer_order' and not _empty_target(
                    row.get('target_id')):
                raise ConversionError(
                    '需求分配 %s 已生成调拨单（target_id=%s）'
                    % (row.get('id'), row.get('target_id')),
                    'ALLOCATION_ALREADY_CONVERTED')
            qty = _dec(row.get('qty'))
            if qty <= 0:
                raise ConversionError(
                    '需求分配 %s 数量必须大于 0' % row.get('id'),
                    'INVALID_QTY')
            row['convert_qty'] = qty
            picked.append(row)
        return picked

    def _load_demand_lines(
            self, allocations: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
        unsupported = sorted({
            str(row.get('demand_bo') or '') for row in allocations
            if str(row.get('demand_bo') or '') != 'requisition'})
        if unsupported:
            raise ConversionError(
                '本波只支持 requisition 需求行的转调拨: %s' % unsupported,
                'DEMAND_BO_UNSUPPORTED')
        line_ids = sorted({row['demand_line_id'] for row in allocations})
        rows = self.ds.query(
            'SELECT id, line_no, item_id, qty, uom_id, need_date, '
            'cost_center_id, status FROM %s WHERE id IN (%s)'
            % (REQUISITION_LINE_TABLE, ','.join(['?'] * len(line_ids))),
            line_ids)
        by_id = {row['id']: row for row in rows}
        missing = [i for i in line_ids if i not in by_id]
        if missing:
            raise ConversionError('需求行不存在: %s' % missing,
                                  'DEMAND_LINE_NOT_FOUND')
        return by_id

    def _resolve_lines(self, allocations: List[Dict[str, Any]]) -> Any:
        demand_lines = self._load_demand_lines(allocations)
        groups: Dict[Any, Dict[str, Any]] = {}
        for allocation in allocations:
            demand_line = demand_lines.get(allocation['demand_line_id'])
            item_id = demand_line.get('item_id')
            uom_id = allocation.get('uom_id') or demand_line.get('uom_id')
            if _blank(item_id) or _blank(uom_id):
                raise ConversionError(
                    '需求行 %s 缺少物料 / 单位，无法转调拨单'
                    % (allocation.get('demand_line_id')),
                    'DEMAND_LINE_ITEM_MISSING')
            if allocation['convert_qty'] > _dec(demand_line.get('qty')):
                raise ConversionError(
                    '需求行 %s 计划数量 %s，分配 %s 超量'
                    % (demand_line.get('line_no'), demand_line.get('qty'),
                       allocation['convert_qty']),
                    'QTY_EXCEEDS_DEMAND')
            key = (str(item_id), str(uom_id))
            group = groups.setdefault(key, {
                'item_id': item_id,
                'uom_id': uom_id,
                'qty': Decimal('0'),
                'allocation_ids': [],
                'allocation_qtys': [],
            })
            group['qty'] += allocation['convert_qty']
            group['allocation_ids'].append(allocation['id'])
            group['allocation_qtys'].append(allocation['convert_qty'])
        return list(groups.values()), demand_lines

    def _line_type_ids(self, document_type_id: Any,
                       groups: List[Dict[str, Any]]) -> Dict[Any, Any]:
        default_type_id = self._default_line_type_id(document_type_id)
        item_group_ids = self._item_group_ids(
            [group['item_id'] for group in groups])
        from meta.services.line_type_service import LineTypeResolver
        resolver = LineTypeResolver(self.ds, scope_bo=HEADER_SCOPE_BO)
        result = {}
        for group in groups:
            resolved = resolver.resolve(
                document_type_id,
                item_group_ids.get(str(group['item_id'])))
            line_type_id = resolved.get('line_type_id') or default_type_id
            if line_type_id in (None, ''):
                raise ConversionError(
                    '物料 %s 未配置可用的调拨行类型' % group['item_id'],
                    'LINE_TYPE_MISSING')
            result[(str(group['item_id']), str(group['uom_id']))] = line_type_id
        return result

    def _default_line_type_id(self, document_type_id: Any) -> Any:
        rows = self.ds.query(
            'SELECT default_type_id FROM %s WHERE id = ?' % TYPE_TABLE,
            [document_type_id])
        if not rows:
            raise ConversionError('调拨单类型 %s 不存在' % document_type_id,
                                  'HEADER_TYPE_MISSING')
        return rows[0].get('default_type_id')

    def _item_group_ids(self, item_ids: List[Any]) -> Dict[Any, Any]:
        ids = sorted({item_id for item_id in item_ids}, key=str)
        rows = self.ds.query(
            'SELECT id, item_group_id FROM %s WHERE id IN (%s)'
            % (ITEM_TABLE, ','.join(['?'] * len(ids))),
            ids)
        return {str(row['id']): row.get('item_group_id') for row in rows}

    # ------------------------------------------------------------------ 组装
    def _build_header(self, from_org_id: Any, to_org_id: Any,
                      transfer_date: Any, document_type_id: Any,
                      project_id: Any, remark: Any,
                      from_location_id: Any, to_location_id: Any) -> Dict[str, Any]:
        type_id = document_type_id or self._default_header_type_id()
        legal_entity_id = self._resolve_legal_entity(from_org_id, to_org_id)
        transfer_order_no = self._allocate_no(type_id, transfer_date)
        data = {
            'transfer_order_no': transfer_order_no,
            'document_type_id': type_id,
            'transfer_date': transfer_date,
            'status': 'draft',
            'from_org_id': from_org_id,
            'to_org_id': to_org_id,
            'legal_entity_id': legal_entity_id,
            'from_location_id': from_location_id,
            'to_location_id': to_location_id,
            'project_id': project_id,
            'remark': remark,
        }
        return {k: v for k, v in data.items() if v is not None}

    def _default_header_type_id(self) -> Any:
        rows = self.ds.query(
            'SELECT id FROM %s WHERE scope_bo = ? AND level = ? AND code = ? '
            "AND status = 'active'" % TYPE_TABLE,
            [HEADER_SCOPE_BO, 'header', DEFAULT_HEADER_TYPE_CODE])
        if not rows:
            raise ConversionError(
                '缺少单据类型种子 %s' % DEFAULT_HEADER_TYPE_CODE,
                'HEADER_TYPE_MISSING')
        return rows[0]['id']

    def _resolve_legal_entity(self, from_org_id: Any, to_org_id: Any) -> Any:
        """复用调拨守卫的组织上溯口径，不重写法人解析。"""
        from meta.services.transfer_order_guard_service import (
            TransferOrderGuardService)
        from meta.services.transfer_order_service import TransferOrderError
        try:
            return TransferOrderGuardService(self.ds).resolve_legal_entity(
                from_org_id, to_org_id)
        except TransferOrderError as error:
            raise ConversionError(error.message, error.rule
                                  or 'TO_LEGAL_ENTITY_UNRESOLVED')

    def _allocate_no(self, document_type_id: Any, transfer_date: Any) -> str:
        """取号必须在开事务之前（序列引擎要求独立事务）。"""
        from meta.services.transfer_order_service import (
            TransferOrderError, TransferOrderService)
        try:
            return TransferOrderService(self.ds).allocate_transfer_order_no(
                document_type_id, transfer_date)
        except TransferOrderError as error:
            raise ConversionError(error.message, error.rule
                                  or 'TO_NUMBER_REQUIRED')

    def _build_line(self, to_id: Any, seq: int, group: Dict[str, Any],
                    line_type_ids: Dict[Any, Any]) -> Dict[str, Any]:
        key = (str(group['item_id']), str(group['uom_id']))
        return {
            'transfer_order_id': to_id,
            # 调拨行号按 10 / 20 / 30 递增（spec §3.2）
            'line_no': seq * 10,
            'line_type_id': line_type_ids[key],
            'item_id': group['item_id'],
            'uom_id': group['uom_id'],
            'qty': float(group['qty']),
            'qty_shipped': 0,
            'qty_received': 0,
            'status': 'open',
        }

    # ------------------------------------------------------------------ 回写
    def _write_back(self, allocations: List[Dict[str, Any]],
                    demand_lines: Dict[Any, Dict[str, Any]],
                    to_id: Any, created_lines: List[Dict[str, Any]]) -> None:
        """分配行改指调拨单：target_bo / target_id / target_line_id / qty。"""
        line_by_key = {
            (str(line['item_id']), str(line['uom_id'])):
                line['transfer_order_line_id']
            for line in created_lines
        }
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for row in allocations:
            demand_line = demand_lines.get(row['demand_line_id']) or {}
            uom_id = row.get('uom_id') or demand_line.get('uom_id')
            line_id = line_by_key.get(
                (str(demand_line.get('item_id')), str(uom_id)))
            if line_id is None:
                raise ConversionError(
                    '需求分配 %s 未匹配到调拨行' % row.get('id'),
                    'TARGET_LINE_NOT_FOUND')
            self.ds.execute(
                'UPDATE %s SET target_bo = ?, target_id = ?, '
                'target_line_id = ?, qty = ?, status = ?, updated_at = ? '
                'WHERE id = ?' % ALLOCATION_TABLE,
                ['transfer_order', to_id, line_id,
                 float(row['convert_qty']), _ALLOCATION_ACTIVE, now,
                 row['id']])
            # DOC_FLOW 阶段 2：需求分配 → 调拨行（attach 模式，失败降级不阻断）
            attach_edge(
                self.ds, self.platform_ds, 'allocation_to_transfer_line',
                row['id'], line_id, float(row['convert_qty']),
                target_item=str(line_id), unit=str(uom_id or ''),
                derived_by='transfer_order_from_allocation')

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def _created_id(result) -> Any:
        data = getattr(result, 'data', None) or {}
        new_id = data.get('id') if isinstance(data, dict) else None
        if new_id is None:
            raise ConversionError('BO 框架未回传新记录 id',
                                  'CREATE_RESULT_MISSING_ID')
        return new_id


def _normalize_ids(allocation_ids: Any) -> List[int]:
    if allocation_ids in (None, ''):
        return []
    if not isinstance(allocation_ids, (list, tuple, set)):
        allocation_ids = [allocation_ids]
    ids = []
    for value in allocation_ids:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            raise ConversionError('allocation_ids 含非法 id: %r' % value,
                                  'INVALID_ARGUMENT')
    return ids


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _empty_target(value: Any) -> bool:
    return _blank(value) or str(value).strip() in ('0',)


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ConversionError('数量必须是数字: %r' % value, 'INVALID_QTY')


# ---------------------------------------------------------------------- action
def _set_user_context():
    """把当前请求用户塞进 BO 框架上下文（审计 / 权限拦截器依赖）。"""
    try:
        from flask import request
        from meta.services.auth_middleware import get_current_user
        from meta.core.bo_framework import bo_framework
        current_user = get_current_user()
        if not current_user:
            return
        bo_framework.set_user_context(
            user_id=current_user.get('user_id'),
            user_name=current_user.get('display_name') or current_user.get(
                'username', 'unknown'),
            ip_address=request.remote_addr,
        )
    except Exception:  # noqa: BLE001 - 无请求上下文（任务链路）时跳过审计用户
        pass


def create_from_allocation_handler(params: Dict[str, Any],
                                   context=None) -> Dict[str, Any]:
    """BO Action 入口：`transfer_order.create_from_allocation`。"""
    _set_user_context()

    allocation_ids = params.get('allocation_ids') or params.get(
        'demand_allocation_ids')
    if not allocation_ids:
        return {'success': False, 'data': None,
                'message': '缺少 allocation_ids', 'code': 'INVALID_ARGUMENT'}
    try:
        result = TransferOrderFromAllocationService().create_from_allocation(
            allocation_ids,
            params.get('from_org_id'),
            params.get('to_org_id'),
            params.get('transfer_date'),
            document_type_id=params.get('document_type_id'),
            project_id=params.get('project_id'),
            remark=params.get('remark'),
            from_location_id=params.get('from_location_id'),
            to_location_id=params.get('to_location_id'),
        )
    except ConversionError as error:
        return {'success': False, 'data': None,
                'message': error.message, 'code': error.code}
    return {
        'success': True,
        'data': result,
        'message': '已生成调拨单 %s' % result.get('transfer_order_no'),
    }
