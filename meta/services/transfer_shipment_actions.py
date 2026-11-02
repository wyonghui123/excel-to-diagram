# -*- coding: utf-8 -*-
"""调拨发货单 BO Action（TBD-3 独立发货单）。

注册于 `meta/services/bo_action_registrations.py`，共 3 个：

  · `transfer_shipment.create` —— 建草稿发货单（取号 + 行校验，不动已发量）
  · `transfer_shipment.post`   —— 草稿 → 已过账（调 TO ship 累加已发量）
  · `transfer_shipment.cancel` —— 草稿 → 已取消

口径:
  · 业务写入（`TransferShipmentService`）在 `ds.transaction()` 内完成，
    异常即整体回滚；`post` 内 ship 失败时发货单保持 draft。
  · 不新增 REST 路由，前端走既有 BO 动作通道。
"""

import logging
from typing import Any, Dict, List

from meta.services.transfer_order_service import TransferOrderError
from meta.services.transfer_shipment_service import (
    TransferShipmentError,
    TransferShipmentService,
)

logger = logging.getLogger(__name__)


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _shipment_id(params: Dict[str, Any]) -> Any:
    return params.get('shipment_id') or params.get('transfer_shipment_id') \
        or params.get('id')


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


def _create_lines(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines = params.get('lines')
    if lines is None:
        lines = params.get('shipment_lines')
    return list(lines or [])


def create_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`transfer_shipment.create`（建草稿发货单）。"""
    _set_user_context()
    transfer_order_id = params.get('transfer_order_id')
    if _blank(transfer_order_id):
        return _fail('缺少 transfer_order_id', 'INVALID_ARGUMENT')
    lines = _create_lines(params)
    if not lines:
        return _fail('发货单至少需要一行（transfer_order_line_id + qty）',
                     'INVALID_ARGUMENT')

    service = TransferShipmentService()
    try:
        result = service.create(
            transfer_order_id,
            params.get('ship_date'),
            lines,
            carrier_name=params.get('carrier_name'),
            waybill_no=params.get('waybill_no'),
            remark=params.get('remark'),
        )
    except TransferShipmentError as e:
        return _fail(e.message, e.rule or 'TRS_CREATE_FAILED')

    return _ok(result, '已生成发货单 %s' % result.get('shipment_no'))


def post_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`transfer_shipment.post`（draft → posted）。"""
    _set_user_context()
    shipment_id = _shipment_id(params)
    if _blank(shipment_id):
        return _fail('缺少 shipment_id', 'INVALID_ARGUMENT')

    service = TransferShipmentService()
    try:
        result = service.post(shipment_id)
    except TransferShipmentError as e:
        return _fail(e.message, e.rule or 'TRS_POST_FAILED')
    except TransferOrderError as e:
        return _fail(e.message, e.rule or 'TRS_POST_FAILED')

    return _ok(result, '发货单 %s 已过账' % result.get('shipment_no'))


def cancel_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`transfer_shipment.cancel`（draft → cancelled）。"""
    _set_user_context()
    shipment_id = _shipment_id(params)
    if _blank(shipment_id):
        return _fail('缺少 shipment_id', 'INVALID_ARGUMENT')

    service = TransferShipmentService()
    try:
        result = service.cancel(shipment_id)
    except TransferShipmentError as e:
        return _fail(e.message, e.rule or 'TRS_CANCEL_FAILED')

    return _ok(result, '发货单 %s 已取消' % result.get('shipment_no'))
