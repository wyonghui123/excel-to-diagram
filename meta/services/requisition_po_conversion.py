# -*- coding: utf-8 -*-
"""需求转采购订单（M3，spec §14 步 23）

口径：
  · 只从「已审批」采购申请转单：`requisitions.status='approved'` + 行 `status='open'`；
  · 可分批转：同一需求行的 active 分配合计不得超过该行 `qty`（超出即拒绝，不静默截断）；
  · `demand_allocation` 是追溯锚点：`demand_bo='requisition'` → `target_bo='purchase_order'`；
  · 所有写动作走 BO 框架（取号 / 守卫 / 金额回写 / 审计全不绕过），
    外层 `bo_framework.transaction()` 保证「PO 头 + 行 + 分配」原子落库；
  · 不改需求行状态：是否整行转完由用户手工关闭（M1 出口判据的 close 动作）。

入口：BO Action `purchase_order.create_from_requisition`
（注册于 `meta/services/bo_action_registrations.py`）。
"""

import logging
from typing import Any, Dict, List, Optional

from meta.core.doc_flow_attach import attach_edge

logger = logging.getLogger(__name__)

OBJECT_TYPE = 'purchase_order'
PO_TABLE = 'purchase_orders'
PO_LINE_TABLE = 'purchase_order_lines'
REQUISITION_TABLE = 'requisitions'
REQUISITION_LINE_TABLE = 'requisition_lines'
ALLOCATION_TABLE = 'demand_allocations'

DEFAULT_HEADER_TYPE_CODE = 'PO_STD'
# requisition_line.line_type → purchase_order_line 行类型编码（v177 种子）
LINE_TYPE_CODE_BY_REQUISITION_TYPE = {
    'goods': 'PO_GOODS',
    'service': 'PO_SERVICE',
}

_REQUISITION_APPROVED = 'approved'
_REQUISITION_LINE_OPEN = 'open'
_ALLOCATION_ACTIVE = 'active'


class ConversionError(Exception):
    """转单失败（message 直接回给调用方，code 用于区分原因）。"""

    def __init__(self, message: str, code: str = 'CONVERSION_FAILED'):
        super().__init__(message)
        self.message = message
        self.code = code


class RequisitionToPoService:
    """采购申请 → 采购订单（部分 / 全部数量）。"""

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
    def convert(self, requisition_id: int, header: Dict[str, Any],
                lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """把一张已审批申请（可指定行与数量）转成一张采购订单。

        Args:
            requisition_id: 采购申请头 id
            header: 订单头字段（`supplier_party_id` 必填；`purchase_org_id` /
                `org_id` / `currency_id` / `document_type_id` 可空，按申请默认值推导）
            lines: `[{'requisition_line_id': int, 'qty': float}]`；为空 = 全部开放行的剩余量

        Returns:
            `{'purchase_order_id', 'order_no', 'lines': [...], 'allocations': [...]}`

        Raises:
            ConversionError: 申请不存在 / 未审批 / 行不可用 / 数量越界 / BO 写失败
        """
        requisition = self._load_requisition(requisition_id)
        if str(requisition.get('status') or '') != _REQUISITION_APPROVED:
            raise ConversionError(
                '采购申请 %s 当前状态 %s，只有 approved 才能转单'
                % (requisition.get('requisition_no'), requisition.get('status')),
                'REQUISITION_NOT_APPROVED')

        picked = self._resolve_lines(requisition_id, lines)
        if not picked:
            raise ConversionError('没有可转单的需求行（开放行剩余数量均为 0）',
                                  'NO_CONVERTIBLE_LINES')

        header_data = self._build_header(requisition, header)
        line_type_ids = self._line_type_ids(picked)

        result = {'purchase_order_id': None, 'lines': [], 'allocations': []}
        with self.framework.transaction():
            order_result = self.framework.execute(OBJECT_TYPE, 'crud_create', header_data)
            if not order_result or not order_result.success:
                raise ConversionError(
                    '创建采购订单失败: %s' % getattr(order_result, 'message', '未知错误'),
                    'PURCHASE_ORDER_CREATE_FAILED')
            po_id = self._created_id(order_result)
            result['purchase_order_id'] = po_id
            # 取号在 `_build_header` 完成；框架回执不一定回传 order_no，取入参兜底
            result['order_no'] = ((order_result.data or {}).get('order_no')
                                  or header_data.get('order_no'))

            for seq, row in enumerate(picked, start=1):
                line_data = self._build_line(po_id, seq, row, line_type_ids)
                line_result = self.framework.execute(
                    'purchase_order_line', 'crud_create', line_data)
                if not line_result or not line_result.success:
                    raise ConversionError(
                        '创建订单行失败（需求行 %s）: %s'
                        % (row.get('line_no'), getattr(line_result, 'message', '未知错误')),
                        'PURCHASE_ORDER_LINE_CREATE_FAILED')
                po_line_id = self._created_id(line_result)

                alloc_data = self._build_allocation(
                    requisition_id, po_id, po_line_id, row,
                    extra=row.get('convert_extra') or {})
                alloc_result = self.framework.execute(
                    'demand_allocation', 'crud_create', alloc_data)
                if not alloc_result or not alloc_result.success:
                    raise ConversionError(
                        '写需求分配失败（需求行 %s）: %s'
                        % (row.get('line_no'), getattr(alloc_result, 'message', '未知错误')),
                        'DEMAND_ALLOCATION_CREATE_FAILED')
                result['lines'].append({
                    'requisition_line_id': row['id'],
                    'purchase_order_line_id': po_line_id,
                    'qty': alloc_data['qty'],
                })
                result['allocations'].append(self._created_id(alloc_result))

                # DOC_FLOW 阶段 2：需求行 → 采购订单行（attach 既有目标行）
                attach_edge(
                    self.ds, self.platform_ds, 'requisition_line_to_po_line',
                    row['id'], po_line_id, alloc_data['qty'],
                    unit=str(row.get('uom_id') or ''),
                    derived_by='requisition_po_conversion')

        logger.info('[RequisitionToPo] %s → %s，%d 行',
                    requisition.get('requisition_no'), result.get('order_no'),
                    len(result['lines']))
        return result

    # ------------------------------------------------------------------ 读
    def _load_requisition(self, requisition_id: int) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT id, requisition_no, status, requester_org_id, deliver_to_org_id, '
            'deliver_to_location_id, need_date, description FROM %s WHERE id = ?'
            % REQUISITION_TABLE, [requisition_id])
        if not rows:
            raise ConversionError('采购申请不存在: %s' % requisition_id,
                                  'REQUISITION_NOT_FOUND')
        return rows[0]

    def _resolve_lines(self, requisition_id: int,
                       lines: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, line_no, line_type, item_id, description, qty, uom_id, '
            'need_date, deliver_to_location_id, cost_center_id, status '
            'FROM %s WHERE requisition_id = ? ORDER BY line_no, id'
            % REQUISITION_LINE_TABLE, [requisition_id])

        remaining = {r['id']: self._remaining_qty(r['id'], r['qty']) for r in rows}
        requested = {}
        for item in (lines or []):
            line_id = item.get('requisition_line_id')
            if line_id is None:
                raise ConversionError('lines 缺少 requisition_line_id', 'INVALID_ARGUMENT')
            requested[line_id] = item

        picked = []
        for row in rows:
            if requested and row['id'] not in requested:
                continue
            if str(row.get('status') or '') != _REQUISITION_LINE_OPEN:
                if requested:
                    raise ConversionError(
                        '需求行 %s 状态 %s 不可转单'
                        % (row.get('line_no'), row.get('status')),
                        'REQUISITION_LINE_NOT_OPEN')
                continue
            avail = remaining.get(row['id'], 0)
            spec_qty = requested.get(row['id'], {}).get('qty')
            qty = avail if spec_qty in (None, '') else float(spec_qty)
            if qty <= 0:
                if requested:
                    raise ConversionError(
                        '需求行 %s 指定数量 %s 非法' % (row.get('line_no'), qty),
                        'INVALID_QTY')
                continue
            if qty > avail:
                raise ConversionError(
                    '需求行 %s 剩余可转 %s，请求 %s 超量'
                    % (row.get('line_no'), avail, qty),
                    'QTY_EXCEEDS_REMAINING')
            row['convert_qty'] = qty
            row['convert_extra'] = requested.get(row['id']) or {}
            picked.append(row)

        missing = set(requested) - {r['id'] for r in picked}
        if missing:
            raise ConversionError('需求行不属于该申请或不可转单: %s' % sorted(missing),
                                  'REQUISITION_LINE_NOT_FOUND')
        return picked

    def _remaining_qty(self, requisition_line_id: int, line_qty: Any) -> float:
        rows = self.ds.query(
            'SELECT COALESCE(SUM(qty), 0) AS allocated FROM %s '
            "WHERE demand_bo = 'requisition' AND demand_line_id = ? AND status = ?"
            % ALLOCATION_TABLE, [requisition_line_id, _ALLOCATION_ACTIVE])
        allocated = float(rows[0].get('allocated') or 0) if rows else 0.0
        return float(line_qty or 0) - allocated

    def _line_type_ids(self, picked: List[Dict[str, Any]]) -> Dict[str, Any]:
        codes = {LINE_TYPE_CODE_BY_REQUISITION_TYPE.get(
            str(r.get('line_type') or 'goods'), 'PO_GOODS') for r in picked}
        rows = self.ds.query(
            "SELECT code, id FROM type_definitions WHERE scope_bo = 'purchase_order' "
            "AND level = 'line' AND code IN (%s)" % ','.join(['?'] * len(codes)),
            sorted(codes))
        mapping = {r['code']: r['id'] for r in rows}
        missing = codes - set(mapping)
        if missing:
            raise ConversionError('缺少行类型种子: %s' % sorted(missing), 'LINE_TYPE_MISSING')
        return mapping

    def _default_header_type_id(self) -> Any:
        rows = self.ds.query(
            "SELECT id FROM type_definitions WHERE scope_bo = 'purchase_order' "
            "AND level = 'header' AND code = ?", [DEFAULT_HEADER_TYPE_CODE])
        if not rows:
            raise ConversionError('缺少单据类型种子 %s' % DEFAULT_HEADER_TYPE_CODE,
                                  'HEADER_TYPE_MISSING')
        return rows[0]['id']

    def _allocate_order_no(self, document_type_id: Any, order_date: Any) -> Any:
        """按单据类型指向的序列取号（spec U12）。

        BO Action 路径不经 `bo_api.create_bo`，故 `_allocate_document_no`
        不会执行；取号须在此完成，且必须早于外层事务（序列引擎要求独立事务，
        嵌入调用方事务会退化为「锁持有到 COMMIT + 回滚把号一并回滚」）。
        """
        if document_type_id in (None, '') or order_date in (None, ''):
            return None
        rows = self.ds.query(
            'SELECT number_sequence_id FROM type_definitions WHERE id = ?',
            [document_type_id])
        sequence_id = rows[0].get('number_sequence_id') if rows else None
        if sequence_id in (None, ''):
            return None
        configs = self.ds.query(
            'SELECT code, pattern, scope_fields, date_field, start_value, on_exhaust '
            'FROM number_sequences WHERE id = ?', [sequence_id])
        if not configs:
            return None
        from meta.core.number_sequence_engine import NumberSequenceEngine
        return NumberSequenceEngine(self.ds).allocate(
            dict(configs[0]), {}, {'order_date': order_date})

    # ------------------------------------------------------------------ 组装
    def _build_header(self, requisition: Dict[str, Any],
                      header: Dict[str, Any]) -> Dict[str, Any]:
        if not header.get('supplier_party_id'):
            raise ConversionError('缺少 supplier_party_id（M3 供应商须人工指定）',
                                  'INVALID_ARGUMENT')
        data = {
            'order_date': header.get('order_date') or requisition.get('need_date')
            or _today(),
            'supplier_party_id': header.get('supplier_party_id'),
            'document_type_id': header.get('document_type_id')
            or self._default_header_type_id(),
            'purchase_org_id': header.get('purchase_org_id')
            or requisition.get('requester_org_id'),
            'org_id': header.get('org_id') or requisition.get('deliver_to_org_id')
            or requisition.get('requester_org_id'),
            'currency_id': header.get('currency_id'),
            'deliver_to_location_id': header.get('deliver_to_location_id')
            or requisition.get('deliver_to_location_id'),
            'requested_date': header.get('requested_date') or requisition.get('need_date'),
            'description': header.get('description') or requisition.get('description'),
            'supplier_reference_no': header.get('supplier_reference_no'),
        }
        if not data['purchase_org_id'] or not data['org_id']:
            raise ConversionError('无法推导 purchase_org_id / org_id，请在 header 指定',
                                  'INVALID_ARGUMENT')
        if not data['currency_id']:
            raise ConversionError('缺少 currency_id', 'INVALID_ARGUMENT')
        # 取号必须在开事务之前（见 `_allocate_order_no` 文档）
        order_no = header.get('order_no') or self._allocate_order_no(
            data['document_type_id'], data['order_date'])
        if order_no:
            data['order_no'] = order_no
        return {k: v for k, v in data.items() if v is not None}

    def _build_line(self, po_id: Any, seq: int, row: Dict[str, Any],
                    line_type_ids: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'order_id': po_id,
            'line_no': '%04d' % seq,
            'line_type_id': line_type_ids[LINE_TYPE_CODE_BY_REQUISITION_TYPE.get(
                str(row.get('line_type') or 'goods'), 'PO_GOODS')],
            'item_id': row.get('item_id'),
            'description': row.get('description') or '',
            'qty': row['convert_qty'],
            'uom_id': row.get('uom_id'),
            # 金额四项与税由拦截器按单价回写；转单时单价待定 ⇒ 0
            'unit_price': 0,
            'net_amount': 0,
            'header_discount_amount': 0,
            'header_surcharge_amount': 0,
            'tax_base_amount': 0,
            'tax_amount': 0,
            'tax_recoverable': True,
            'non_recoverable_tax_amount': 0,
            'gross_amount': 0,
            'component_issue_required': False,
            'service_acceptance_required': False,
            'requested_date': row.get('need_date'),
            'deliver_to_location_id': row.get('deliver_to_location_id'),
        }

    def _build_allocation(self, requisition_id: Any, po_id: Any, po_line_id: Any,
                          row: Dict[str, Any],
                          extra: Dict[str, Any]) -> Dict[str, Any]:
        data = {
            'demand_bo': 'requisition',
            'demand_id': requisition_id,
            'demand_line_id': row['id'],
            'demand_line_no': row.get('line_no'),
            'demand_need_date': row.get('need_date'),
            'target_bo': 'purchase_order',
            'target_id': po_id,
            'target_line_id': po_line_id,
            'qty': row['convert_qty'],
            'uom_id': row.get('uom_id'),
            'cost_center_id': row.get('cost_center_id'),
            'project_id': extra.get('project_id'),
            'project_task_id': extra.get('project_task_id'),
            # 记账口径默认存货；费用 / 资产口径必须由调用方补齐科目字段（守卫校验）
            'charge_basis': extra.get('charge_basis') or 'inventory',
            'expense_account_code': extra.get('expense_account_code'),
            'asset_category_code': extra.get('asset_category_code'),
            'status': _ALLOCATION_ACTIVE,
        }
        return {k: v for k, v in data.items() if v is not None}

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def _created_id(result) -> Any:
        data = getattr(result, 'data', None) or {}
        new_id = data.get('id') if isinstance(data, dict) else None
        if new_id is None:
            raise ConversionError('BO 框架未回传新记录 id', 'CREATE_RESULT_MISSING_ID')
        return new_id


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


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


def create_from_requisition_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action 入口：`purchase_order.create_from_requisition`。"""
    _set_user_context()

    requisition_id = params.get('requisition_id') or params.get('source_requisition_id')
    if requisition_id in (None, ''):
        return {'success': False, 'data': None,
                'message': '缺少 requisition_id', 'code': 'INVALID_ARGUMENT'}
    header = {
        key: params.get(key)
        for key in ('supplier_party_id', 'document_type_id', 'purchase_org_id',
                    'org_id', 'currency_id', 'order_date', 'requested_date',
                    'deliver_to_location_id', 'description', 'supplier_reference_no')
    }
    lines = params.get('lines') or None
    try:
        result = RequisitionToPoService().convert(int(requisition_id), header, lines)
    except ConversionError as e:
        return {'success': False, 'data': None, 'message': e.message, 'code': e.code}
    return {
        'success': True,
        'data': result,
        'message': '已转为采购订单 %s' % result.get('order_no'),
    }
