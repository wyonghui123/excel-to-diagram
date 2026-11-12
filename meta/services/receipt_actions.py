# -*- coding: utf-8 -*-
"""收货单 BO Action（spec-receipt-object-model §13 步骤 7）。

注册于 `meta/services/bo_action_registrations.py`，共 5 个：

  · `receipt.create_from_schedule` —— 由 PO 计划行批量生成草稿收货单
  · `receipt.create_vendor_return` —— 由原收货单生成退货采购单 + 退货出库草稿（D6）
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


def create_vendor_return_handler(params: Dict[str, Any],
                                 context=None) -> Dict[str, Any]:
    """BO Action：`receipt.create_vendor_return`（原收货单 → 退货 PO + 退货出库草稿）。"""
    _set_user_context()
    receipt_id = _receipt_id(params)
    if _blank(receipt_id):
        return _fail('缺少 receipt_id', 'INVALID_ARGUMENT')

    from datetime import date as _date
    from meta.core.bo_framework import bo_framework
    from meta.services.document_number_service import DocumentNumberService

    service = ReceiptService()
    header = service.ds.query('SELECT * FROM receipts WHERE id = ?', [receipt_id])
    if not header:
        return _fail('原收货单不存在', 'RECEIPT_NOT_FOUND')
    header = header[0]
    if header.get('status') != 'posted':
        return _fail('只有已过账的收货单可以发起退货', 'RECEIPT_NOT_POSTED')
    if header.get('source_doc_type') != SOURCE_PURCHASE_ORDER:
        return _fail('仅采购订单来源的收货单支持退货', 'RETURN_NOT_SUPPORTED')
    doc_type = service._require_document_type(header.get('document_type_id'))
    if doc_type.get('document_category') != 'standard':
        return _fail('只有标准收货单可以发起退货', 'RETURN_NOT_SUPPORTED')

    source_lines = service.ds.query(
        'SELECT id, schedule_id, item_id, uom_id, order_line_id, '
        'qty_received, qty_rejected FROM receipt_lines '
        'WHERE receipt_id = ? AND status = ? ORDER BY id',
        [receipt_id, 'posted'])
    if not source_lines:
        return _fail('原收货单没有可退货的行', 'NO_RETURNABLE_LINE')

    picked = params.get('lines')
    picked_map = {}
    if picked:
        for spec in picked:
            key = spec.get('receipt_line_id') or spec.get('line_id') \
                or spec.get('schedule_id')
            picked_map[key] = float(spec.get('qty') or 0)
    planned = []
    for line in source_lines:
        net = float(line.get('qty_received') or 0) - float(line.get('qty_rejected') or 0)
        if net <= 0:
            continue
        if picked_map:
            qty = picked_map.get(line['id'], picked_map.get(line.get('schedule_id'), 0))
            qty = min(qty, net)
        else:
            qty = net
        if qty <= 0:
            continue
        planned.append((line, qty))
    if not planned:
        return _fail('未指定有效的退货数量', 'NO_RETURNABLE_LINE')

    return_type = service.ds.query(
        "SELECT id FROM type_definitions WHERE scope_bo = 'purchase_order' "
        "AND level = 'header' AND code = 'RETURN_PO'")
    receipt_type = service.ds.query(
        "SELECT id FROM type_definitions WHERE scope_bo = 'receipt' "
        "AND level = 'header' AND code = 'VENDOR_RETURN'")
    if not return_type or not receipt_type:
        return _fail('缺少 RETURN_PO / VENDOR_RETURN 单据类型种子',
                     'RETURN_TYPE_MISSING')
    return_type_id = return_type[0]['id']
    receipt_type_id = receipt_type[0]['id']

    receipt_date = params.get('receipt_date') or header.get('receipt_date') \
        or _date.today().isoformat()
    source_order = service._load_order(header.get('source_doc_id')) or {}
    order_no = DocumentNumberService(service.ds).allocate_for(
        'purchase_order', {'document_type_id': return_type_id,
                           'order_date': receipt_date})
    receipt_no = service.allocate_receipt_no(receipt_type_id, receipt_date)

    header_data = {
        'order_no': order_no,
        'order_date': receipt_date,
        'document_type_id': return_type_id,
        'supplier_party_id': source_order.get('supplier_party_id'),
        'org_id': source_order.get('org_id'),
        'purchase_org_id': source_order.get('purchase_org_id'),
        'purchase_legal_entity_id': source_order.get('purchase_legal_entity_id'),
        'deliver_to_location_id': source_order.get('deliver_to_location_id'),
        'project_id': source_order.get('project_id'),
        'requested_date': receipt_date,
        'description': '采购退货：%s' % (params.get('return_reason') or ''),
        'origin_purchase_order_id': source_order.get('id'),
        'origin_receipt_id': receipt_id,
        'return_reason': params.get('return_reason'),
    }
    header_data = {k: v for k, v in header_data.items() if v is not None}

    line_type = service.ds.query(
        "SELECT id FROM type_definitions WHERE scope_bo = 'purchase_order' "
        "AND level = 'line' AND code = 'PO_GOODS'")
    line_type_id = line_type[0]['id'] if line_type else None
    created = {'purchase_order_id': None, 'purchase_order_no': order_no,
               'receipt_id': None, 'receipt_no': receipt_no, 'lines': []}
    try:
        with service.ds.transaction():
            order_result = bo_framework.execute(
                'purchase_order', 'crud_create', header_data)
            if not order_result or not order_result.success:
                return _fail('创建退货采购单失败: %s'
                             % getattr(order_result, 'message', '未知错误'),
                             'RETURN_PO_CREATE_FAILED')
            po_id = (order_result.data or {}).get('id')
            created['purchase_order_id'] = po_id
            for seq, (line, qty) in enumerate(planned, start=1):
                line_data = {
                    'order_id': po_id,
                    'line_no': '%04d' % seq,
                    'line_type_id': line_type_id,
                    'item_id': line.get('item_id'),
                    'qty': qty,
                    'uom_id': line.get('uom_id'),
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
                    'requested_date': receipt_date,
                    'deliver_to_location_id': source_order.get(
                        'deliver_to_location_id'),
                }
                line_result = bo_framework.execute(
                    'purchase_order_line', 'crud_create',
                    {k: v for k, v in line_data.items() if v is not None})
                if not line_result or not line_result.success:
                    return _fail('创建退货订单行失败: %s'
                                 % getattr(line_result, 'message', '未知错误'),
                                 'RETURN_PO_LINE_CREATE_FAILED')
                po_line_id = (line_result.data or {}).get('id')
                schedule_result = bo_framework.execute(
                    'purchase_order_schedule', 'crud_create', {
                        'order_id': po_id,
                        'line_id': po_line_id,
                        'schedule_no': '%04d' % seq,
                        'schedule_kind': 'delivery',
                        'promised_date': receipt_date,
                        'promised_qty': qty,
                        'status': 'confirmed',
                        'deliver_to_location_id': source_order.get(
                            'deliver_to_location_id'),
                    })
                if not schedule_result or not schedule_result.success:
                    return _fail('创建退货计划行失败: %s'
                                 % getattr(schedule_result, 'message', '未知错误'),
                                 'RETURN_SCHEDULE_CREATE_FAILED')
                schedule_id = (schedule_result.data or {}).get('id')
                created['lines'].append({
                    'source_receipt_line_id': line['id'],
                    'purchase_order_line_id': po_line_id,
                    'schedule_id': schedule_id,
                    'qty': qty,
                })

            receipt_header = {
                'document_type_id': receipt_type_id,
                'receipt_no': receipt_no,
                'receipt_date': receipt_date,
                'source_doc_type': SOURCE_PURCHASE_ORDER,
                'source_doc_id': po_id,
                'supplier_party_id': source_order.get('supplier_party_id'),
                'org_id': source_order.get('org_id'),
                'purchase_org_id': source_order.get('purchase_org_id'),
                'deliver_to_location_id': source_order.get(
                    'deliver_to_location_id'),
                'project_id': source_order.get('project_id'),
                'return_to': 'supplier',
                'remark': params.get('return_reason'),
            }
            prepared, _order, _doc_type = service.prepare_header(receipt_header)
            result = service.create_receipt(
                prepared,
                [{'schedule_id': item['schedule_id'],
                  'qty_received': item['qty']} for item in created['lines']])
            created['receipt_id'] = result['id']
            _write_schedule_edges(service, result['id'])
    except ReceiptError as exc:
        return _fail(exc.message, exc.rule or 'RETURN_CREATE_FAILED')

    logger.info('[receipt] vendor return receipt=%s → po=%s receipt=%s',
                receipt_id, created['purchase_order_id'], created['receipt_id'])
    return _ok(created, '已生成退货采购单 %s 与退货出库草稿 %s'
               % (order_no, receipt_no))


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
