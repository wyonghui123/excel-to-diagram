# -*- coding: utf-8 -*-
"""[M4-3 2026-11-15] 任务委托 REST 蓝图（任务域通用能力；准入期身份展开）

路由（v1，随 tasks 门控）:
- GET    /api/v1/task-delegations            我的委托配置（admin 可查他人）
- POST   /api/v1/task-delegations            新建委托（delegator 强制 = 当前用户；admin 可代配）
- GET    /api/v1/task-delegations/active     我受托于谁（当前有效）
- PUT    /api/v1/task-delegations/<id>       调整失效时间 / 原因 / 状态
- DELETE /api/v1/task-delegations/<id>       撤销（status='revoked'，保留审计）

权限（spec §8.4 / §8.6）：不新增权限码 —— 登录态 + 本人（delegator）或 admin；
不写 `executor_assignee`、不改任务归属，准入展开在决策层完成。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.core.task_delegation import (
    DelegationError,
    create_delegation,
    get_delegation,
    list_active_for_delegate,
    list_delegations,
    revoke_delegation,
    update_delegation,
)
from meta.services.auth_middleware import get_current_user, is_admin, login_required

logger = logging.getLogger(__name__)

task_delegation_bp = Blueprint('task_delegation', __name__)


def _platform_ds():
    return get_data_source("sqlite", database=get_meta_db_path())


def _actor(user) -> str:
    if not user:
        return ''
    return user.get('user_id') or user.get('username') or ''


def _authorize_row(row: Dict[str, Any], user) -> bool:
    """本人（delegator）或 admin 可改；created_by 不构成权限（admin 代配的配置仍归 delegator）。"""
    return is_admin(user) or str(row.get('delegator') or '') == _actor(user)


def list_delegations_service(*, user, delegator: Optional[str] = None,
                             include_inactive: bool = False,
                             data_source=None) -> Tuple[Dict[str, Any], int]:
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    if not is_admin(user):
        delegator = actor          # 非 admin 只能看自己的委托
    data_source = data_source or _platform_ds()
    try:
        items = list_delegations(
            data_source, delegator=delegator, include_inactive=include_inactive)
    except Exception as e:  # noqa: BLE001
        logger.error('[M4-3] 查询委托失败: %s', e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': {'items': items, 'total': len(items)}}, 200


def create_delegation_service(*, user, body: Optional[Dict[str, Any]] = None,
                              data_source=None) -> Tuple[Dict[str, Any], int]:
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    body = body or {}
    if not isinstance(body, dict):
        return {'success': False, 'message': '请求体必须是 JSON 对象'}, 400

    delegator = str(body.get('delegator') or '').strip() or actor
    if delegator != actor and not is_admin(user):
        return {'success': False, 'message': '只能为自己配置委托（admin 可代配）'}, 403
    delegate = str(body.get('delegate') or '').strip()
    if not delegate:
        return {'success': False, 'message': 'delegate 必填'}, 400

    data_source = data_source or _platform_ds()
    try:
        row = create_delegation(
            data_source, delegator=delegator, delegate=delegate,
            scope_type=body.get('scope_type') or 'any',
            scope_value=body.get('scope_value'),
            effective_from=body.get('effective_from'),
            effective_to=body.get('effective_to'),
            reason=body.get('reason') or '',
            created_by=actor,
        )
    except DelegationError as e:
        return {'success': False, 'message': str(e)}, 400
    except Exception as e:  # noqa: BLE001
        logger.error('[M4-3] 新建委托失败: %s', e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': row}, 200


def update_delegation_service(delegation_id: int, *, user,
                              body: Optional[Dict[str, Any]] = None,
                              data_source=None) -> Tuple[Dict[str, Any], int]:
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    body = body or {}
    if not isinstance(body, dict):
        return {'success': False, 'message': '请求体必须是 JSON 对象'}, 400

    data_source = data_source or _platform_ds()
    row = get_delegation(data_source, int(delegation_id))
    if row is None:
        return {'success': False, 'message': '委托不存在'}, 404
    if not _authorize_row(row, user):
        return {'success': False, 'message': '无权修改该委托'}, 403

    try:
        updated = update_delegation(
            data_source, int(delegation_id),
            status=body.get('status'),
            effective_to=body.get('effective_to', '_keep'),
            reason=body.get('reason'),
        )
    except DelegationError as e:
        return {'success': False, 'message': str(e)}, 400
    except Exception as e:  # noqa: BLE001
        logger.error('[M4-3] 更新委托失败: %s', e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': updated}, 200


def revoke_delegation_service(delegation_id: int, *, user,
                              data_source=None) -> Tuple[Dict[str, Any], int]:
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401

    data_source = data_source or _platform_ds()
    row = get_delegation(data_source, int(delegation_id))
    if row is None:
        return {'success': False, 'message': '委托不存在'}, 404
    if not _authorize_row(row, user):
        return {'success': False, 'message': '无权撤销该委托'}, 403

    try:
        updated = revoke_delegation(data_source, int(delegation_id))
    except DelegationError as e:
        return {'success': False, 'message': str(e)}, 400
    except Exception as e:  # noqa: BLE001
        logger.error('[M4-3] 撤销委托失败: %s', e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': updated}, 200


def active_delegations_service(*, user,
                               data_source=None) -> Tuple[Dict[str, Any], int]:
    """我受托于谁（当前有效；范围匹配由决策层按任务完成）。"""
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    data_source = data_source or _platform_ds()
    items = list_active_for_delegate(data_source, actor)
    return {'success': True, 'data': {'items': items, 'total': len(items)}}, 200


@task_delegation_bp.route('/api/v1/task-delegations', methods=['GET'])
@login_required
def task_delegations_route():
    payload, code = list_delegations_service(
        user=get_current_user(),
        delegator=request.args.get('delegator') or None,
        include_inactive=request.args.get('include_inactive') in ('1', 'true', 'True'),
    )
    return jsonify(payload), code


@task_delegation_bp.route('/api/v1/task-delegations', methods=['POST'])
@login_required
def task_delegation_create_route():
    payload, code = create_delegation_service(
        user=get_current_user(), body=request.get_json(silent=True) or {})
    return jsonify(payload), code


@task_delegation_bp.route('/api/v1/task-delegations/active', methods=['GET'])
@login_required
def task_delegation_active_route():
    payload, code = active_delegations_service(user=get_current_user())
    return jsonify(payload), code


@task_delegation_bp.route('/api/v1/task-delegations/<int:delegation_id>', methods=['PUT'])
@login_required
def task_delegation_update_route(delegation_id: int):
    payload, code = update_delegation_service(
        delegation_id, user=get_current_user(),
        body=request.get_json(silent=True) or {})
    return jsonify(payload), code


@task_delegation_bp.route('/api/v1/task-delegations/<int:delegation_id>', methods=['DELETE'])
@login_required
def task_delegation_revoke_route(delegation_id: int):
    payload, code = revoke_delegation_service(
        delegation_id, user=get_current_user())
    return jsonify(payload), code