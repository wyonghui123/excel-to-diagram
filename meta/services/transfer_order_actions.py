# -*- coding: utf-8 -*-
"""调拨单 BO Action（spec-transfer-order-object-model §6 / §7）。

注册于 `meta/services/bo_action_registrations.py`，共 5 个：

  · `transfer_order.release` —— 草稿 → 已下达
  · `transfer_order.ship`    —— 已下达 → 累计发货（不建发货单 / 不碰库存）
  · `transfer_order.receive` —— 已下达 → 生成草稿收货单（收货桥接）
  · `transfer_order.cancel`  —— 草稿 / 已下达 → 已取消（未发货才允许）
  · `transfer_order.close`   —— 已下达 → 已关闭（短收结案）

口径：
  · 守卫校验（`TransferOrderGuardService`）与业务写入（`TransferOrderService`）
    都在 `service.ds.transaction()` 内完成，异常即整体回滚；
  · `receive` 生成收货单时取号必须在事务之外（R-RC-8），故由
    `ReceiptService.create_from_transfer_order` 内部先取号、后开事务；
  · 不新增 REST 路由，前端走既有 BO 动作通道。
"""

import logging
from typing import Any, Dict, List

from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.services.transfer_order_guard_service import TransferOrderGuardService
from meta.services.transfer_order_service import TransferOrderError, TransferOrderService

logger = logging.getLogger(__name__)


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _transfer_order_id(params: Dict[str, Any]) -> Any:
    return params.get('transfer_order_id') or params.get('id')


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


def _ship_lines(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines = params.get('lines')
    if lines is None:
        lines = params.get('ship_lines')
    return list(lines or [])


def release_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`transfer_order.release`（draft → released，幂等）。"""
    _set_user_context()
    transfer_order_id = _transfer_order_id(params)
    if _blank(transfer_order_id):
        return _fail('缺少 transfer_order_id', 'INVALID_ARGUMENT')

    service = TransferOrderService()
    guard = TransferOrderGuardService(service.ds)
    try:
        with service.ds.transaction():
            guard.validate_release(transfer_order_id)
            result = service.release(transfer_order_id)
    except TransferOrderError as e:
        return _fail(e.message, e.rule or 'TO_RELEASE_FAILED')

    return _ok(result, '调拨单 %s 已下达' % result.get('id'))


def ship_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`transfer_order.ship`（released 下累加行 `qty_shipped`）。"""
    _set_user_context()
    transfer_order_id = _transfer_order_id(params)
    if _blank(transfer_order_id):
        return _fail('缺少 transfer_order_id', 'INVALID_ARGUMENT')
    lines = _ship_lines(params)
    if not lines:
        return _fail('发货至少需要一行（line_id + qty）', 'INVALID_ARGUMENT')

    service = TransferOrderService()
    guard = TransferOrderGuardService(service.ds)
    try:
        with service.ds.transaction():
            guard.validate_ship(transfer_order_id, lines)
            result = service.ship(transfer_order_id, lines)
    except TransferOrderError as e:
        return _fail(e.message, e.rule or 'TO_SHIP_FAILED')

    return _ok(result, '调拨单 %s 已完成发货' % result.get('id'))


def receive_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`transfer_order.receive`（生成 TO 来源草稿收货单，不直接过账）。"""
    _set_user_context()
    transfer_order_id = _transfer_order_id(params)
    if _blank(transfer_order_id):
        return _fail('缺少 transfer_order_id', 'INVALID_ARGUMENT')
    line_ids = params.get('line_ids') or None

    guard = TransferOrderGuardService(TransferOrderService().ds)
    try:
        guard.validate_receive(transfer_order_id)
    except TransferOrderError as e:
        return _fail(e.message, e.rule or 'TO_RECEIVE_FAILED')

    # R-RC-8：取号在事务之外，事务边界由 create_from_transfer_order 内部控制
    service = ReceiptService()
    try:
        result = service.create_from_transfer_order(
            transfer_order_id, line_ids=line_ids)
    except TransferOrderError as e:
        return _fail(e.message, e.rule or 'TO_RECEIVE_FAILED')
    except ReceiptError as e:
        return _fail(e.message, e.rule or 'RC_TRANSFER_CREATE_FAILED')

    return _ok(result, '已生成收货单 %s' % result.get('receipt_no'))


def cancel_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`transfer_order.cancel`（draft / released → cancelled，幂等）。"""
    _set_user_context()
    transfer_order_id = _transfer_order_id(params)
    if _blank(transfer_order_id):
        return _fail('缺少 transfer_order_id', 'INVALID_ARGUMENT')

    service = TransferOrderService()
    guard = TransferOrderGuardService(service.ds)
    try:
        with service.ds.transaction():
            guard.validate_cancel(transfer_order_id)
            result = service.cancel(transfer_order_id)
    except TransferOrderError as e:
        return _fail(e.message, e.rule or 'TO_CANCEL_FAILED')

    return _ok(result, '调拨单 %s 已取消' % result.get('id'))


def close_handler(params: Dict[str, Any], context=None) -> Dict[str, Any]:
    """BO Action：`transfer_order.close`（released → closed，短收结案，幂等）。"""
    _set_user_context()
    transfer_order_id = _transfer_order_id(params)
    if _blank(transfer_order_id):
        return _fail('缺少 transfer_order_id', 'INVALID_ARGUMENT')

    service = TransferOrderService()
    guard = TransferOrderGuardService(service.ds)
    try:
        with service.ds.transaction():
            guard.validate_close(transfer_order_id)
            result = service.close(transfer_order_id)
    except TransferOrderError as e:
        return _fail(e.message, e.rule or 'TO_CLOSE_FAILED')

    return _ok(result, '调拨单 %s 已关闭' % result.get('id'))
