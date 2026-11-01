# -*- coding: utf-8 -*-
"""BO Action: purchase_order.approve / .reject（M3）

依据 `docs/specs/spec-purchase-order-object-model-2026-11-01.md` §6.3：
  · 审批任务决策经 `decision_effect` 按 `executor_config.decision_actions`
    调回本模块的 BO Action；
  · 状态机仍走 YAML 规则（submitted → confirmed / submitted → draft），
    不直改表；approval_status 与本模块同一次 crud_update 落库；
  · 回执 `data.new_status` 是决策-生效协议的任务归位依据（默认键）。

与 M1 审批决策的差异：PO 的 `approval_status` 与 `status` 正交，
approve 时同时写 `approval_status='approved'`，reject 时写 `'rejected'`，
并由守卫 R-PO-12 决定 submitted → confirmed 是否放行。
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

OBJECT_TYPE = 'purchase_order'
TABLE = 'purchase_orders'

_STATUS_SUBMITTED = 'submitted'
_STATUS_CONFIRMED = 'confirmed'
_STATUS_DRAFT = 'draft'
_APPROVAL_APPROVED = 'approved'
_APPROVAL_REJECTED = 'rejected'


def _envelope_error(message: str, code: str = None) -> Dict[str, Any]:
    payload = {'success': False, 'data': None, 'message': message}
    if code:
        payload['code'] = code
    return payload


def _record_id(params: Dict[str, Any]):
    p = params or {}
    record_id = p.get('purchase_order_id')
    if record_id in (None, ''):
        record_id = p.get('id')
    return record_id


def _get_ds():
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return get_data_source('sqlite', database=get_meta_db_path())


def _set_user_context():
    try:
        from flask import request
        from meta.services.auth_middleware import get_current_user
        from meta.core.bo_framework import bo_framework
        current_user = get_current_user()
        bo_framework.set_user_context(
            user_id=current_user.get('user_id'),
            user_name=current_user.get(
                'display_name', current_user.get('username', 'unknown')),
            ip_address=request.remote_addr,
        )
    except Exception:  # noqa: BLE001 - 无请求上下文（任务链路）时跳过审计用户
        pass


def _execute_update(record_id: Any, status: str, approval_status: str):
    """经 BO 框架走 crud_update，让 YAML 状态机与守卫同时生效。"""
    from meta.core.bo_framework import bo_framework
    return bo_framework.execute(OBJECT_TYPE, 'crud_update', {
        'id': record_id,
        'status': status,
        'approval_status': approval_status,
    })


def _decide(params: Dict[str, Any], *, target_status: str,
            approval_status: str, message: str) -> Dict[str, Any]:
    record_id = _record_id(params)
    if record_id in (None, ''):
        return _envelope_error('缺少 purchase_order_id')

    _set_user_context()

    try:
        ds = _get_ds()
        rows = ds.query(
            'SELECT id, status, approval_status FROM {0} WHERE id = ?'.format(TABLE),
            [record_id])
        if not rows:
            return _envelope_error('采购订单不存在: {0}'.format(record_id), 'NOT_FOUND')
        current_status = str(rows[0].get('status') or '')
        if current_status == target_status:
            # 同值 no-op success：重复决策不重复推进，回执仍需 new_status
            return {
                'success': True,
                'data': {
                    'new_status': target_status,
                    'purchase_order_id': record_id,
                    'approval_status': approval_status,
                },
                'message': message,
            }
        if current_status != _STATUS_SUBMITTED:
            return _envelope_error(
                '当前状态 {0} 不允许审批（只接受 submitted）'.format(current_status),
                'INVALID_STATUS',
            )

        result = _execute_update(record_id, target_status, approval_status)
    except Exception as error:  # noqa: BLE001 - 统一转为失败信封
        logger.exception('[document_approval] 采购订单审批决策失败: %s', error)
        return _envelope_error('审批决策失败: {0}'.format(error))

    if not getattr(result, 'success', False):
        return _envelope_error(
            getattr(result, 'message', None) or '审批决策未生效',
            getattr(result, 'error', None),
        )

    # 复核落库结果：框架对未知动作会返回默认 success=True，不能只信返回值
    rows = ds.query(
        'SELECT status, approval_status FROM {0} WHERE id = ?'.format(TABLE),
        [record_id])
    actual_status = rows[0].get('status') if rows else None
    actual_approval = rows[0].get('approval_status') if rows else None
    if str(actual_status) != target_status:
        return _envelope_error(
            '审批决策未生效（单据状态仍为 {0}）'.format(actual_status),
            'EFFECT_NOT_APPLIED',
        )

    return {
        'success': True,
        'data': {
            'new_status': target_status,
            'purchase_order_id': record_id,
            'approval_status': actual_approval or approval_status,
        },
        'message': message,
    }


def purchase_order_approve_handler(params: Dict[str, Any],
                                   context: Dict[str, Any]) -> Dict[str, Any]:
    """采购订单审批通过：submitted → confirmed，approval_status=approved。"""
    return _decide(params, target_status=_STATUS_CONFIRMED,
                   approval_status=_APPROVAL_APPROVED,
                   message='采购订单审批通过')


def purchase_order_reject_handler(params: Dict[str, Any],
                                  context: Dict[str, Any]) -> Dict[str, Any]:
    """采购订单审批驳回：submitted → draft，approval_status=rejected。"""
    return _decide(params, target_status=_STATUS_DRAFT,
                   approval_status=_APPROVAL_REJECTED,
                   message='采购订单已驳回')
