# -*- coding: utf-8 -*-
"""[M4-2 2026-11-15] 参与（加签）/ 参与进度 REST 蓝图

路由（v1，随 tasks 门控）:
- POST /api/v1/tasks/<task_id>/participate      加签（可 require_all 转会签）
- GET  /api/v1/tasks/<task_id>/participations   参与人进度

权限（spec §8.6）：不新增权限码，登录态 + 任务级准入（与 claim 端点同构）；
决策端点的 `{bo}:approve` 附加校验仍在 task_decision_api。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.core.task_inbox import task_detail
from meta.services.auth_middleware import get_current_user, is_admin, login_required
from meta.services.task_participation import (
    ParticipationConflictError,
    ParticipationNotFoundError,
    ParticipationPermissionError,
    ParticipationServiceError,
    participate,
    participations_view,
)

logger = logging.getLogger(__name__)

task_participation_bp = Blueprint('task_participation', __name__)


def _platform_ds():
    return get_data_source("sqlite", database=get_meta_db_path())


def _actor(user) -> str:
    if not user:
        return ''
    return user.get('user_id') or user.get('username') or ''


def task_participate_service(task_id: str, *, user,
                             body: Optional[Dict[str, Any]] = None,
                             data_source=None) -> Tuple[Dict[str, Any], int]:
    """可测的加签服务。Returns: (payload, http_status)"""
    body = body or {}
    data_source = data_source or _platform_ds()
    try:
        payload = participate(
            data_source, str(task_id),
            actor=_actor(user),
            participant=body.get('participant'),
            comment=body.get('comment') or '',
            require_all=bool(body.get('require_all', False)),
            admin=is_admin(user),
        )
    except ParticipationPermissionError as e:
        return {'success': False, 'message': str(e)}, 403
    except ParticipationNotFoundError as e:
        return {'success': False, 'message': str(e)}, 404
    except ParticipationConflictError as e:
        return {'success': False, 'message': str(e)}, 409
    except ParticipationServiceError as e:
        return {'success': False, 'message': str(e)}, 400
    except Exception as e:  # noqa: BLE001 - 兜底，避免裸栈
        logger.error('[M4-2] 加签失败: %s', e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': payload}, 200


def task_participations_service(task_id: str, *, user,
                                data_source=None) -> Tuple[Dict[str, Any], int]:
    """可测的参与进度服务（任务可见者）。Returns: (payload, http_status)"""
    if not _actor(user):
        return {'success': False, 'message': '未登录'}, 401
    data_source = data_source or _platform_ds()
    try:
        visible = task_detail(data_source, str(task_id), actor=_actor(user))
        if visible is None and not is_admin(user):
            return {'success': False, 'message': '任务不存在或无权查看'}, 404
        payload = participations_view(data_source, str(task_id))
    except ParticipationNotFoundError as e:
        return {'success': False, 'message': str(e)}, 404
    except Exception as e:  # noqa: BLE001
        logger.error('[M4-2] 读取参与进度失败: %s', e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': payload}, 200


@task_participation_bp.route('/api/v1/tasks/<task_id>/participate', methods=['POST'])
@login_required
def task_participate_route(task_id: str):
    body = request.get_json(silent=True) or {}
    payload, code = task_participate_service(
        task_id, user=get_current_user(), body=body)
    return jsonify(payload), code


@task_participation_bp.route('/api/v1/tasks/<task_id>/participations', methods=['GET'])
@login_required
def task_participations_route(task_id: str):
    payload, code = task_participations_service(
        task_id, user=get_current_user())
    return jsonify(payload), code