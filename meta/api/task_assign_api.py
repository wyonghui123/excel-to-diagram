# -*- coding: utf-8 -*-
"""[M4-1 2026-11-15] 任务改派 REST 蓝图（任务域通用能力；审批是第一消费者）

路由（v1）:
- POST /api/v1/tasks/<task_id>/assign   改派执行人（actor 取登录态；不改状态）

口径（spec §8.2 / §8.6）:
- 不新增权限码：同 claim 端点——登录态 + 任务级准入（执行人/候选池/有效受托人/admin）。
- 审批任务附加：目标必须具备 `{bo}:approve`（或 `*` 通配）且不是提交人；
  目标权限由服务端按 `to_user` 查权限，不信任客户端声明。
- 错误语义：未登录 401；缺参 400；任务不存在 404；无准入 403；前置不满足 409。
"""
from __future__ import annotations

import logging

from flask import Blueprint, request

from meta.api._response_contract import json_response
from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.core.task_assignment import (
    AssignmentError, AssignmentPermissionError, TaskNotFoundError, reassign_task,
)
from meta.services.auth_middleware import get_current_user, is_admin, login_required

logger = logging.getLogger(__name__)

task_assign_bp = Blueprint('task_assign', __name__)


def _platform_ds():
    return get_data_source("sqlite", database=get_meta_db_path())


def _actor(user) -> str:
    if not user:
        return ""
    return user.get('user_id') or user.get('username') or ""


def _target_review_permitted(data_source, to_user, object_type) -> bool:
    """目标用户是否具备 `{object_type}:approve`（含 `*` 通配）。

    非数字 id 无法映射到权限表 ⇒ fail-closed（审批任务不允许改派给非法主体）。
    """
    if not object_type or not str(to_user or "").isdigit():
        return False
    try:
        from meta.services.permission_service import PermissionService
        return bool(PermissionService(data_source).has_permission(
            int(to_user), f"{object_type}:approve"))
    except Exception:  # noqa: BLE001 - 权限表异常按无权限处理
        logger.warning("[M4-1] 目标审批权限查询失败，按无权限处理", exc_info=True)
        return False


def task_reassign_service(task_id: str, *, user, body: dict):
    """改派任务执行人。Returns: (payload, http_status)"""
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    if not isinstance(body, dict):
        return {'success': False, 'message': '请求体必须是 JSON 对象'}, 400
    to_user = str(body.get('to_user') or '').strip()
    reason = str(body.get('reason') or '').strip()
    if not to_user:
        return {'success': False, 'message': 'to_user 必填'}, 400
    if not reason:
        return {'success': False, 'message': 'reason 必填（改派必须留痕）'}, 400

    ds = _platform_ds()
    try:
        from meta.core.task_inbox import task_detail
        task = task_detail(ds, str(task_id), actor=actor)
        if task is None:
            return {'success': False, 'message': '任务不存在或无权查看'}, 404
        target_permitted = None
        if task.get('type') == 'approval':
            target_permitted = _target_review_permitted(
                ds, to_user, task.get('doc_ref_type'))
            if to_user == task.get('created_by'):
                return {'success': False, 'message': '改派目标不能是提交人（四眼约束）'}, 409

        outcome = reassign_task(
            ds, str(task_id), to_user=to_user, actor=actor, reason=reason,
            admin=is_admin(user), target_permitted=target_permitted,
        )
    except TaskNotFoundError as e:
        return {'success': False, 'message': str(e)}, 404
    except AssignmentPermissionError as e:
        return {'success': False, 'message': str(e)}, 403
    except AssignmentError as e:
        return {'success': False, 'message': str(e)}, 409
    except Exception as e:  # noqa: BLE001
        logger.error("[M4-1] 任务改派失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': outcome}, 200


@task_assign_bp.route('/api/v1/tasks/<task_id>/assign', methods=['POST'])
@login_required
def task_assign_route(task_id: str):
    payload, code = task_reassign_service(
        task_id, user=get_current_user(), body=request.get_json(silent=True) or {})
    return json_response(payload, code)