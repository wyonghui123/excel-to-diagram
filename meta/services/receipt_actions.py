# -*- coding: utf-8 -*-
"""收货单 BO Action（spec-receipt-object-model §13 步骤 7）。

注册于 `meta/services/bo_action_registrations.py`，共 4 个：

  · `receipt.create_from_schedule` —— 由 PO 计划行批量生成草稿收货单
  · `receipt.post`                —— 草稿 → 已过账（§6 六步）
  · `receipt.reverse`             —— 已过账 → 整单红冲（§7）
  · `receipt.cancel`              —— 草稿 → 已取消

口径：
  · 取号必须在事务之外（R-RC-8 / 编号引擎硬约束）⇒ `create_from_schedule`
    与 `reverse` 先取号再开事务；
  · 事务边界由本模块控制（`with service.ds.transaction()`），
    服务层不自行提交，异常即整体回滚。
"""

import logging
from typing import Any, Dict, List, Optional

from meta.services.receipt_service import (
    ReceiptError,
    ReceiptService,
    SCHEDULE_TABLE,
    SOURCE_PURCHASE_ORDER,
)

logger = logging.getLogger(__name__)

#: 收货抬头可透传的字段（其余由 `prepare_header` 推导）
HEADER_KEYS = (
    'document_type_id', 'receipt_date', 'actual_arrival_date',
    'supplier_party_id', 'supplier_delivery_no', 'org_id', 'purchase_org_id',
    'deliver_to_location_id', 'project_id', 'received_by', 'remark',
)

#: 可生成收货行的计划行规格（§5.3 R-RC-1）
SCHEDULE_KINDS = ('delivery', 'service')
PENDING_STATUSES = ('planned', 'confirmed')


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _receipt_id(params: Dict[str, Any]) -> Any:
    return params.get('receipt_id') or params.get('id')


def _ok(data: Any, message: str) -> Dict[str, Any]:
    return {'success': True, 'data': data, 'message': message}


def _fail(message: str, code: str) -> Dict[str, Any]:
    return {'success': False, 'data': None, 'message': message, 'code': code}


def _set_user_context() -> None:
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


def _lines_from_schedules(service: ReceiptService,
                          order_id: Any) -> List[Dict[str, Any]]:
    """未显式给行时，按计划行「承诺量 - 已收净量」自动生成。"""
    rows = service.ds.query(
        'SELECT id, schedule_kind, promised_qty, '
        'COALESCE(received_qty, 0) AS received_qty, '
        "COALESCE(completion_source, '') AS completion_source "
        'FROM %s WHERE order_id = ? AND status IN (%s) ORDER BY id'
        % (SCHEDULE_TABLE, ', '.join(['?'] * len(PENDING_STATUSES))),
        [order_id] + list(PENDING_STATUSES))

    lines: List[Dict[str, Any]] = []
    for row in rows:
        if row.get('schedule_kind') not in SCHEDULE_KINDS:
            continue
        if row.get('completion_source') == 'short_close':
            continue
        if _blank(row.get('promised_qty')):
            continue
        remaining = float(row['promised_qty']) - float(row.get('received_qty') or 0)
        if remaining <= 0:
            continue
        lines.append({'schedule_id': row['id'], 'qty_received': remaining})
    return lines


def _write_schedule_edges(service: ReceiptService, receipt_id: Any) -> None:
    """DOC_FLOW 阶段 2：PO 计划行 → 收货行（attach 模式，失败降级不阻断）。"""
    from meta.core.doc_flow_attach import attach_edge
    rows = service.ds.query(
        'SELECT id, schedule_id, qty_received, uom_id FROM receipt_lines '
        'WHERE receipt_id = ? AND schedule_id IS NOT NULL ORDER BY id',
        [receipt_id])
    for row in rows:
        attach_edge(
            service.ds, service.platform_ds, 'po_schedule_to_receipt_line',
            row['schedule_id'], row['id'],
            float(row.get('qty_received') or 0),
            target_item=str(row.get('id') or ''),
            unit=str(row.get('uom_id') or ''),
            derived_by='receipt_actions')


def create_from_schedule_handler(params: Dict[str, Any],
                                 context=None) -> Dict[str, Any]:
    """BO Action：`receipt.create_from_schedule`（PO 计划行 → 草稿收货单）。"""
    _set_user_context()
    source_id = params.get('source_doc_id') or params.get('purchase_order_id')
    if _blank(source_id):
        return _fail('缺少 source_doc_id（采购订单 id）', 'INVALID_ARGUMENT')

    header = {key: params.get(key) for key in HEADER_KEYS}
    header['source_doc_type'] = SOURCE_PURCHASE_ORDER
    header['source_doc_id'] = source_id

    service = ReceiptService()
    try:
        if _blank(header.get('document_type_id')):
            header['document_type_id'] = service.standard_header_type()['id']
        lines = params.get('lines') or _lines_from_schedules(service, source_id)
        if not lines:
            return _fail('该采购订单没有可收货的计划行', 'NO_RECEIVABLE_SCHEDULE')
        # R-RC-8：取号在开事务之前完成
        prepared, _order, _doc_type = service.prepare_header(header)
        with service.ds.transaction():
            result = service.create_receipt(prepared, lines)
            _write_schedule_edges(service, result['id'])
    except ReceiptError as e:
        return _fail(e.message, e.rule or 'RC_CREATE_FAILED')

    return _ok(result, '已生成收货单 %s' % result.get('receipt_no'))


def post_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`receipt.post`（草稿 → 已过账；幂等）。"""
    _set_user_context()
    receipt_id = _receipt_id(params)
    if _blank(receipt_id):
        return _fail('缺少 receipt_id', 'INVALID_ARGUMENT')
    service = ReceiptService()
    try:
        with service.ds.transaction():
            result = service.post(
                receipt_id, params.get('actual_arrival_date') or None)
    except ReceiptError as e:
        return _fail(e.message, e.rule or 'RC_POST_FAILED')
    return _ok(result, '收货单 %s 已过账' % result.get('id'))


def cancel_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`receipt.cancel`（草稿 → 已取消）。"""
    _set_user_context()
    receipt_id = _receipt_id(params)
    if _blank(receipt_id):
        return _fail('缺少 receipt_id', 'INVALID_ARGUMENT')
    service = ReceiptService()
    try:
        with service.ds.transaction():
            result = service.cancel(receipt_id)
    except ReceiptError as e:
        return _fail(e.message, e.rule or 'RC_CANCEL_FAILED')
    return _ok(result, '收货单 %s 已取消' % result.get('id'))


def reverse_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`receipt.reverse`（已过账 → 整单红冲，新建红字单）。"""
    _set_user_context()
    receipt_id = _receipt_id(params)
    if _blank(receipt_id):
        return _fail('缺少 receipt_id', 'INVALID_ARGUMENT')
    receipt_date = params.get('receipt_date') or None
    service = ReceiptService()
    try:
        # R-RC-8：红字单号必须在开事务前分配
        red_no = service.allocate_reversal_no(receipt_id, receipt_date)
        with service.ds.transaction():
            result = service.reverse(
                receipt_id, receipt_date=receipt_date, receipt_no=red_no,
                remark=params.get('remark'))
    except ReceiptError as e:
        return _fail(e.message, e.rule or 'RC_REVERSE_FAILED')
    return _ok(result, '已生成红字收货单 %s'
               % result.get('reversal_receipt_no'))
