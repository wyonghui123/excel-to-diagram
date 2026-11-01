# -*- coding: utf-8 -*-
"""BO Action: service_request.approve / .reject / requisition.approve / .reject（M1）

依据 docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §2 M1：
「审批复用 tasks(type=approval)」——需求入口不新建审批引擎，提交时由
`DemandEntryService.create_approval_task` 落一条审批任务，任务决策经
`decision_effect` 按 `executor_config.decision_actions` 调回本模块的 BO Action。

口径：
  · 状态迁移只认 `submitted → approved / rejected`，其余状态拒绝并返回失败信封；
  · 已是目标状态 → 同值 no-op success（重复决策不重复推进，回执仍需 new_status）；
  · 回执 `data.new_status` 必须是决策-生效协议的任务归位依据（默认键）；
  · 实际写入走 `bo_framework.execute_action`（YAML 状态机 + 审计链），不直改表。
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

#: object_type → (表名, 通过动作, 驳回动作)
_OBJECTS = {
    'service_request': ('service_requests', 'approve_service_request', 'reject_service_request'),
    'requisition': ('requisitions', 'approve_requisition', 'reject_requisition'),
}

_STATUS_SUBMITTED = 'submitted'
_STATUS_APPROVED = 'approved'
_STATUS_REJECTED = 'rejected'


def _envelope_error(message: str, code: str = None) -> Dict[str, Any]:
    payload = {'success': False, 'data': None, 'message': message}
    if code:
        payload['code'] = code
    return payload


def _record_id(params: Dict[str, Any], object_type: str):
    """任务 inputs 取单据 id：优先 `<object_type>_id`，回退 `id`。"""
    p = params or {}
    record_id = p.get('{0}_id'.format(object_type))
    if record_id in (None, ''):
        record_id = p.get('id')
    return record_id


def _get_ds():
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return get_data_source('sqlite', database=get_meta_db_path())


def _execute_meta_action(object_type: str, action_id: str, record_id: Any):
    """经 BO 框架执行 YAML 状态迁移动作（同一写漏斗，含审计）。"""
    from meta.core.bo_framework import bo_framework
    return bo_framework.execute_action(object_type, action_id, {'id': record_id})


def _set_user_context():
    from flask import request
    from meta.services.auth_middleware import get_current_user
    from meta.core.bo_framework import bo_framework
    current_user = get_current_user()
    bo_framework.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get(
            'display_name', current_user.get('username', 'unknown')
        ),
        ip_address=request.remote_addr,
    )


def _decide(params: Dict[str, Any], context: Dict[str, Any], *,
            object_type: str, target_status: str, message: str) -> Dict[str, Any]:
    if object_type not in _OBJECTS:
        return _envelope_error('不支持的需求入口对象: {0}'.format(object_type))
    table, approve_action, reject_action = _OBJECTS[object_type]
    action_id = approve_action if target_status == _STATUS_APPROVED else reject_action

    record_id = _record_id(params, object_type)
    if record_id in (None, ''):
        return _envelope_error('缺少 {0}_id'.format(object_type))

    try:
        _set_user_context()
    except Exception:  # noqa: BLE001 - 无请求上下文时跳过审计用户
        pass

    try:
        ds = _get_ds()
        rows = ds.query(
            'SELECT id, status FROM {0} WHERE id = ?'.format(table), [record_id])
        if not rows:
            return _envelope_error('单据不存在: {0}'.format(record_id), 'NOT_FOUND')
        current_status = rows[0].get('status')
        if str(current_status) == target_status:
            return {
                'success': True,
                'data': {'new_status': target_status, '{0}_id'.format(object_type): record_id},
                'message': message,
            }
        if str(current_status) != _STATUS_SUBMITTED:
            return _envelope_error(
                '当前状态 {0} 不允许审批（只接受 submitted）'.format(current_status),
                'INVALID_STATUS',
            )

        result = _execute_meta_action(object_type, action_id, record_id)
    except Exception as error:  # noqa: BLE001 - 统一转为失败信封
        logger.exception('[demand_entry] 审批决策失败: %s', error)
        return _envelope_error('审批决策失败: {0}'.format(error))

    if not getattr(result, 'success', False):
        return _envelope_error(
            getattr(result, 'message', None) or '审批决策未生效',
            getattr(result, 'error', None),
        )

    return {
        'success': True,
        'data': {'new_status': target_status, '{0}_id'.format(object_type): record_id},
        'message': message,
    }


def service_request_approve_handler(params: Dict[str, Any],
                                    context: Dict[str, Any]) -> Dict[str, Any]:
    """服务请求审批通过：submitted → approved，回执 new_status=approved。"""
    return _decide(params, context, object_type='service_request',
                   target_status=_STATUS_APPROVED, message='服务请求审批通过')


def service_request_reject_handler(params: Dict[str, Any],
                                   context: Dict[str, Any]) -> Dict[str, Any]:
    """服务请求驳回：submitted → rejected，回执 new_status=rejected。"""
    return _decide(params, context, object_type='service_request',
                   target_status=_STATUS_REJECTED, message='服务请求已驳回')


def requisition_approve_handler(params: Dict[str, Any],
                                context: Dict[str, Any]) -> Dict[str, Any]:
    """采购申请审批通过：submitted → approved，回执 new_status=approved。"""
    return _decide(params, context, object_type='requisition',
                   target_status=_STATUS_APPROVED, message='采购申请审批通过')


def requisition_reject_handler(params: Dict[str, Any],
                               context: Dict[str, Any]) -> Dict[str, Any]:
    """采购申请驳回：submitted → rejected，回执 new_status=rejected。"""
    return _decide(params, context, object_type='requisition',
                   target_status=_STATUS_REJECTED, message='采购申请已驳回')
