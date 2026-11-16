# -*- coding: utf-8 -*-
"""[A8 2026-10-02] 统一收件箱 REST 蓝图 — 跨应用待办聚合 + 平台心跳入口

路由（v1）:
- GET  /api/v1/task-inbox          统一收件箱（entries + counts，按登录人过滤）
- GET  /api/v1/task-inbox/counts   分区角标（全量口径）
- POST /api/v1/platform/tick       平台心跳（派工 / 回收 / 告警；限管理员）
- POST /api/v1/tasks/<task_id>/start  启动一个任务（executor 适配层统一入口；限管理员）
- GET  /api/v1/tasks               全量任务列表（管理员；非管理员仅按 doc_ref_* 查询并按行级可见性收敛）
- GET  /api/v1/tasks/<task_id>     任务详情（行级可见性 fail-closed）
- GET  /api/v1/tasks/<task_id>/events  任务活动流（同可见性闸门）
- POST /api/v1/tasks/<task_id>/claim   认领任务（候选池抢单；actor 取登录态）
- GET  /api/v1/tasks/<task_id>/actions 可用动作（状态 × 类型 × 权限，只读）
- POST /api/v1/tasks/<task_id>/cancel  取消任务（created_by / admin；无单据副作用）
- POST /api/v1/tasks/<task_id>/hold    挂起（只写 TASK_EVENT，不改状态列）
- POST /api/v1/tasks/<task_id>/resume  解除挂起（与 hold 严格交替）
- POST /api/v1/tasks/<task_id>/withdraw 提交人撤回审批（单据回退 + 任务取消）

纪律（§12.1 A8 / Q1）:
- 行级可见性过滤是硬项：actor 一律取登录态（user_id 优先，退 username），
  不信任客户端传参；actor 为空时 core 层 fail-closed 返回空。
- 角色→应用授权映射（role_apps + actor_roles）暂无权威用户系统数据源，
  **不臆造权限表**：REST v1 先开 分配者/候选/创建者 三条通道，其余走 core 参数
  （TODO：用户/角色系统接入后在此填充）。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.4 / §12.1 A8 /
  §12.1「五」Q1
"""
from __future__ import annotations

import logging

from flask import Blueprint, request

from meta.api._response_contract import error_response, json_response, ok
from meta.core.query_spec import parse_query_spec

from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.core.permission_gate import user_has_permission
from meta.core.task_assignment import (
    AssignmentError, claim_task, is_candidate,
)
from meta.core.task_control import (
    TaskControlError, TaskNotFoundError, cancel_task,
)
from meta.core.task_event_schema import list_task_events
from meta.core.task_hold import TaskHoldError, hold_task, release_task
from meta.core.task_inbox import DEFAULT_LIMIT, inbox_counts, inbox_query, task_detail
from meta.core.task_query import list_tasks
from meta.core.task_state_machine import (
    TASK_ACTION_MAP, TaskTransitionError, applicable_actions,
)
from meta.core.task_withdraw import (
    TaskWithdrawError, TaskWithdrawPermissionError, withdraw_task,
)
from meta.core.task_tick import platform_tick
from meta.core.task_executor_adapter import ExecutorAdapterError, start_task
from meta.services.auth_middleware import (
    get_current_user, is_admin, login_required,
)

logger = logging.getLogger(__name__)

task_inbox_bp = Blueprint('task_inbox', __name__)

# 单页上限（防止拉全表；与 bo_api 的 MAX_USER_PAGE_SIZE 同思路）
MAX_LIMIT = 200


def _platform_ds():
    """平台库数据源（V007.24 缓存安全，可每请求调用）。"""
    return get_data_source("sqlite", database=get_meta_db_path())


def _actor(user) -> str:
    """当前用户 id（惯例：user_id 优先，缺省退 username；统一转字符串）。"""
    if not user:
        return None
    return str(user.get('user_id') or user.get('username') or '') or None


@task_inbox_bp.route('/api/v1/task-inbox', methods=['GET'])
@login_required
def task_inbox_list():
    actor = _actor(get_current_user())
    bucket = request.args.get('bucket') or None
    app_id = request.args.get('app_id') or None
    limit_raw = request.args.get('limit', type=int)
    limit = DEFAULT_LIMIT if limit_raw is None else max(1, min(MAX_LIMIT, limit_raw))

    try:
        result = inbox_query(_platform_ds(), actor=actor, app_id=app_id,
                             bucket=bucket, limit=limit)
    except ValueError as e:
        return error_response(str(e), status=400)
    except Exception as e:
        logger.error("[A8] 收件箱查询失败: %s", e)
        return error_response(str(e), status=500)
    return ok(result)


@task_inbox_bp.route('/api/v1/task-inbox/counts', methods=['GET'])
@login_required
def task_inbox_count():
    actor = _actor(get_current_user())
    app_id = request.args.get('app_id') or None

    try:
        counts = inbox_counts(_platform_ds(), actor=actor, app_id=app_id)
    except Exception as e:
        logger.error("[A8] 收件箱角标失败: %s", e)
        return error_response(str(e), status=500)
    return ok(counts)


@task_inbox_bp.route('/api/v1/platform/tick', methods=['POST'])
@login_required
def platform_tick_route():
    """平台心跳：派工 / 回收 / 告警 / 决策-生效对账（cron 或管理员手动触发）。"""
    user = get_current_user()
    if not is_admin(user):
        return error_response('需要管理员权限', status=403)

    body = request.get_json(silent=True) or {}
    try:
        result = platform_tick(
            _platform_ds(),
            dispatch=bool(body.get('dispatch', True)),
            reclaim=bool(body.get('reclaim', True)),
            escalate=bool(body.get('escalate', True)),
            reconcile=bool(body.get('reconcile', True)),
        )
    except Exception as e:
        logger.error("[A5] 平台心跳失败: %s", e)
        return error_response(str(e), status=500)
    return ok(result)


def start_task_service(task_id: str, *, user, registry=None):
    """启动一个任务（A5 适配层统一入口）；可测服务函数。

    Returns:
        (payload, http_status)
    """
    if not is_admin(user):
        return {'success': False, 'message': '需要管理员权限'}, 403
    try:
        outcome = start_task(_platform_ds(), str(task_id),
                             run_as='system', registry=registry)
    except ExecutorAdapterError as e:
        # 任务不存在 / 未知类型 → 409 冲突（无副作用）
        return {'success': False, 'message': str(e)}, 409
    except Exception as e:
        logger.error("[A5] 任务启动失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': outcome}, 200


@task_inbox_bp.route('/api/v1/tasks/<task_id>/start', methods=['POST'])
@login_required
def task_start_route(task_id: str):
    """启动任务：executor 适配层统一入口（run-as 由服务端裁决，不接受客户端身份）。"""
    payload, code = start_task_service(task_id, user=get_current_user())
    return json_response(payload, code)


# ─────────────────────────────────────────────────────────────────────────────
# P1 读/写薄路径（详情 / 活动流 / 认领 / 监控列表）
# ─────────────────────────────────────────────────────────────────────────────

def _visible_or_404(task_id, user):
    """按登录态取可见任务；不可见 / 不存在统一 404（不泄露存在性）。"""
    actor = _actor(user)
    task = task_detail(_platform_ds(), str(task_id), actor=actor)
    return task


def task_detail_service(task_id: str, *, user):
    """任务详情（actor 可见性 fail-closed）。Returns: (payload, http_status)"""
    try:
        task = _visible_or_404(task_id, user)
    except Exception as e:
        logger.error("[P1] 任务详情失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    if task is None:
        return {'success': False, 'message': '任务不存在或无权查看'}, 404
    return {'success': True, 'data': task}, 200


def task_events_service(task_id: str, *, user, limit: int = 200):
    """任务活动流（actor 可见性 fail-closed）。Returns: (payload, http_status)"""
    try:
        task = _visible_or_404(task_id, user)
        if task is None:
            return {'success': False, 'message': '任务不存在或无权查看'}, 404
        events = list_task_events(_platform_ds(), str(task_id), limit=limit)
    except ValueError as e:
        return {'success': False, 'message': str(e)}, 400
    except Exception as e:
        logger.error("[P1] 任务活动流失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': events}, 200


def task_claim_service(task_id: str, *, user):
    """认领任务（actor 取登录态，不接受客户端身份）。Returns: (payload, http_status)"""
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    try:
        outcome = claim_task(_platform_ds(), str(task_id), actor,
                             actor_kind="human")
    except AssignmentError as e:
        # 非候选池 / 非 ready / 策略不可抢单 → 409（无副作用）
        return {'success': False, 'message': str(e)}, 409
    except Exception as e:
        logger.error("[P1] 任务认领失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': outcome}, 200


def _action_allowed(decl, task, *, user, actor) -> bool:
    """动作权限码 → 事实判定（D-AP-06 同口径：admin 短路，未知事实 fail-closed）。"""
    code = decl.permission
    if code == "admin":
        return is_admin(user)
    if code == "owner":
        return bool(actor) and str(actor) == str(task.get('created_by') or "")
    if code == "owner_or_admin":
        # cancel：created_by 或 admin（§9.13.4.2 第 3 条）；withdraw 仍严格 owner
        return is_admin(user) or (
            bool(actor) and str(actor) == str(task.get('created_by') or ""))
    if code == "{bo}:approve":
        if is_admin(user):
            return True
        bo = str(task.get('doc_ref_type') or "")
        return bool(bo) and user_has_permission(
            (user or {}).get('permissions') or [], '%s:approve' % bo)
    if code == "task.claim":
        return is_candidate(task, str(actor)) if actor else False
    if code == "task.view":
        return True   # 可见性已由 task_detail 把关
    # task.assign / task.delegate / task.hold：执行人 / 候选池 / 管理员
    if is_admin(user):
        return True
    if not actor:
        return False
    return str(actor) == str(task.get('executor_assignee') or "") \
        or is_candidate(task, str(actor))


def task_actions_service(task_id: str, *, user):
    """任务可用动作（状态 × 类型 × 权限；只读，零副作用）。Returns: (payload, http_status)

    动作目录真源在 `task_state_machine.TASK_ACTIONS`（D-AP-17），本层只做权限映射：
    前端不再硬编码「什么状态显示什么按钮」，也不再自行推断权限。
    """
    actor = _actor(user)
    try:
        task = _visible_or_404(task_id, user)
    except Exception as e:
        logger.error("[P1] 任务动作失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    if task is None:
        return {'success': False, 'message': '任务不存在或无权查看'}, 404

    actions = [
        {
            'action': decl.action,
            'label': decl.label,
            'endpoint': decl.endpoint.replace('{id}', str(task_id)),
            'to_state': decl.to_state,
            'permission': decl.permission,
            'confirm': decl.confirm,
        }
        for decl in applicable_actions(task.get('status'), task.get('type'))
        if _action_allowed(decl, task, user=user, actor=actor)
    ]
    return {'success': True, 'data': {
        'task_id': str(task_id),
        'status': task.get('status') or '',
        'type': task.get('type') or '',
        'actions': actions,
    }}, 200


def task_cancel_service(task_id: str, *, user, reason: str = ""):
    """取消任务（created_by / admin；无单据副作用）。Returns: (payload, http_status)"""
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    try:
        task = _visible_or_404(task_id, user)
    except Exception as e:
        logger.error("[P1] 任务取消失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    if task is None:
        return {'success': False, 'message': '任务不存在或无权查看'}, 404

    decl = TASK_ACTION_MAP['cancel']
    if not _action_allowed(decl, task, user=user, actor=actor):
        return {'success': False, 'message': '无权取消该任务'}, 403
    if task.get('status') not in decl.allowed_from:
        return {'success': False, 'message':
                '当前状态不可取消：%s' % (task.get('status') or '')}, 409

    try:
        outcome = cancel_task(_platform_ds(), str(task_id), actor=actor,
                              actor_kind="human", reason=reason)
    except TaskNotFoundError as e:
        return {'success': False, 'message': str(e)}, 404
    except (TaskControlError, TaskTransitionError) as e:
        return {'success': False, 'message': str(e)}, 409
    except Exception as e:
        logger.error("[P1] 任务取消失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': outcome}, 200


def task_hold_service(task_id: str, *, user, hold_code: str, reason: str = ""):
    """挂起任务（只写 TASK_EVENT，不改状态列）。Returns: (payload, http_status)"""
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    if not hold_code:
        return {'success': False, 'message': 'hold_code 不能为空'}, 400
    try:
        task = _visible_or_404(task_id, user)
    except Exception as e:
        logger.error("[P1] 任务挂起失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    if task is None:
        return {'success': False, 'message': '任务不存在或无权查看'}, 404

    decl = TASK_ACTION_MAP['hold']
    if not _action_allowed(decl, task, user=user, actor=actor):
        return {'success': False, 'message': '无权挂起该任务'}, 403
    if task.get('status') not in decl.allowed_from:
        return {'success': False, 'message':
                '任务已终态，不能挂起：%s' % (task.get('status') or '')}, 409

    try:
        event_id = hold_task(_platform_ds(), str(task_id), hold_code=hold_code,
                             reason=reason, actor=actor, actor_kind="human")
    except TaskHoldError as e:
        return {'success': False, 'message': str(e)}, 409
    except Exception as e:
        logger.error("[P1] 任务挂起失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': {
        'task_id': str(task_id), 'hold_code': hold_code,
        'event_id': event_id, 'status': task.get('status') or '',
    }}, 200


def task_resume_service(task_id: str, *, user, hold_code: str, reason: str = ""):
    """解除挂起（与 hold 严格交替；只写 TASK_EVENT）。Returns: (payload, http_status)"""
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    if not hold_code:
        return {'success': False, 'message': 'hold_code 不能为空'}, 400
    try:
        task = _visible_or_404(task_id, user)
    except Exception as e:
        logger.error("[P1] 解除挂起失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    if task is None:
        return {'success': False, 'message': '任务不存在或无权查看'}, 404

    decl = TASK_ACTION_MAP['resume']
    if not _action_allowed(decl, task, user=user, actor=actor):
        return {'success': False, 'message': '无权解除挂起'}, 403
    if task.get('status') not in decl.allowed_from:
        return {'success': False, 'message':
                '任务已终态，不能解除挂起：%s' % (task.get('status') or '')}, 409

    try:
        event_id = release_task(_platform_ds(), str(task_id), hold_code=hold_code,
                                reason=reason, actor=actor, actor_kind="human")
    except TaskHoldError as e:
        return {'success': False, 'message': str(e)}, 409
    except Exception as e:
        logger.error("[P1] 解除挂起失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': {
        'task_id': str(task_id), 'hold_code': hold_code,
        'event_id': event_id, 'status': task.get('status') or '',
    }}, 200


def task_withdraw_service(task_id: str, *, user, reason: str = ""):
    """提交人撤回审批（单据回退 + 任务取消）。Returns: (payload, http_status)"""
    actor = _actor(user)
    if not actor:
        return {'success': False, 'message': '未登录'}, 401
    try:
        task = _visible_or_404(task_id, user)
    except Exception as e:
        logger.error("[P1] 审批撤回失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    if task is None:
        return {'success': False, 'message': '任务不存在或无权查看'}, 404

    decl = TASK_ACTION_MAP['withdraw']
    if not _action_allowed(decl, task, user=user, actor=actor):
        return {'success': False, 'message': '仅提交人可撤回审批'}, 403
    if task.get('type') != 'approval':
        return {'success': False, 'message': '非审批任务不能撤回（请使用 cancel）'}, 409
    if task.get('status') not in decl.allowed_from:
        return {'success': False, 'message':
                '当前状态不可撤回：%s' % (task.get('status') or '')}, 409

    try:
        outcome = withdraw_task(_platform_ds(), str(task_id), actor=actor,
                                actor_kind="human", reason=reason)
    except TaskWithdrawPermissionError as e:
        return {'success': False, 'message': str(e)}, 403
    except TaskNotFoundError as e:
        return {'success': False, 'message': str(e)}, 404
    except (TaskControlError, TaskWithdrawError, TaskTransitionError) as e:
        return {'success': False, 'message': str(e)}, 409
    except Exception as e:
        logger.error("[P1] 审批撤回失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': outcome}, 200


def task_monitor_service(*, user, status=None, type=None, app_id=None,
                         executor_type=None, page=1, page_size=50,
                         doc_ref_type=None, doc_ref_id=None):
    """全量任务列表（运维监控）。

    - 管理员：全量口径（原行为不变）。
    - 非管理员：仅允许按单据引用查询（必须同时提供 `doc_ref_type` + `doc_ref_id`），
      并按行级可见性收敛（口径同 `task_detail`；管理员不是可见性后门）。

    Returns: (payload, http_status)
    """
    if not is_admin(user):
        if not (doc_ref_type and doc_ref_id):
            return {'success': False,
                    'message': '非管理员仅支持按单据查询（需同时提供 doc_ref_type 与 doc_ref_id）'}, 403
        actor = _actor(user)
        if not actor:
            return {'success': False, 'message': '未登录'}, 401
        try:
            data = list_tasks(_platform_ds(), status=status, type=type,
                              app_id=app_id, executor_type=executor_type,
                              doc_ref_type=doc_ref_type, doc_ref_id=doc_ref_id,
                              actor=actor, page=page, page_size=page_size)
        except ValueError as e:
            return {'success': False, 'message': str(e)}, 400
        except Exception as e:
            logger.error("[P1] 单据审批任务查询失败: %s", e)
            return {'success': False, 'message': str(e)}, 500
        return {'success': True, 'data': data}, 200

    try:
        data = list_tasks(_platform_ds(), status=status, type=type, app_id=app_id,
                          executor_type=executor_type, doc_ref_type=doc_ref_type,
                          doc_ref_id=doc_ref_id, page=page, page_size=page_size)
    except ValueError as e:
        return {'success': False, 'message': str(e)}, 400
    except Exception as e:
        logger.error("[P1] 监控列表失败: %s", e)
        return {'success': False, 'message': str(e)}, 500
    return {'success': True, 'data': data}, 200


@task_inbox_bp.route('/api/v1/tasks', methods=['GET'])
@login_required
def task_monitor_route():
    spec = parse_query_spec(request.args, default_page_size=50)
    payload, code = task_monitor_service(
        user=get_current_user(),
        status=request.args.get('status') or None,
        type=request.args.get('type') or None,
        app_id=request.args.get('app_id') or None,
        executor_type=request.args.get('executor_type') or None,
        doc_ref_type=request.args.get('doc_ref_type') or None,
        doc_ref_id=request.args.get('doc_ref_id') or None,
        page=spec.page,
        page_size=spec.page_size,
    )
    return json_response(payload, code)


@task_inbox_bp.route('/api/v1/tasks/<task_id>', methods=['GET'])
@login_required
def task_detail_route(task_id: str):
    payload, code = task_detail_service(task_id, user=get_current_user())
    return json_response(payload, code)


@task_inbox_bp.route('/api/v1/tasks/<task_id>/events', methods=['GET'])
@login_required
def task_events_route(task_id: str):
    payload, code = task_events_service(
        task_id, user=get_current_user(),
        limit=request.args.get('limit', default=200, type=int))
    return json_response(payload, code)


@task_inbox_bp.route('/api/v1/tasks/<task_id>/claim', methods=['POST'])
@login_required
def task_claim_route(task_id: str):
    payload, code = task_claim_service(task_id, user=get_current_user())
    return json_response(payload, code)


@task_inbox_bp.route('/api/v1/tasks/<task_id>/actions', methods=['GET'])
@login_required
def task_actions_route(task_id: str):
    payload, code = task_actions_service(task_id, user=get_current_user())
    return json_response(payload, code)


@task_inbox_bp.route('/api/v1/tasks/<task_id>/cancel', methods=['POST'])
@login_required
def task_cancel_route(task_id: str):
    body = request.get_json(silent=True) or {}
    payload, code = task_cancel_service(
        task_id, user=get_current_user(), reason=str(body.get('reason') or ''))
    return json_response(payload, code)


@task_inbox_bp.route('/api/v1/tasks/<task_id>/hold', methods=['POST'])
@login_required
def task_hold_route(task_id: str):
    body = request.get_json(silent=True) or {}
    payload, code = task_hold_service(
        task_id, user=get_current_user(),
        hold_code=str(body.get('hold_code') or ''),
        reason=str(body.get('reason') or ''))
    return json_response(payload, code)


@task_inbox_bp.route('/api/v1/tasks/<task_id>/resume', methods=['POST'])
@login_required
def task_resume_route(task_id: str):
    body = request.get_json(silent=True) or {}
    payload, code = task_resume_service(
        task_id, user=get_current_user(),
        hold_code=str(body.get('hold_code') or ''),
        reason=str(body.get('reason') or ''))
    return json_response(payload, code)


@task_inbox_bp.route('/api/v1/tasks/<task_id>/withdraw', methods=['POST'])
@login_required
def task_withdraw_route(task_id: str):
    body = request.get_json(silent=True) or {}
    payload, code = task_withdraw_service(
        task_id, user=get_current_user(), reason=str(body.get('reason') or ''))
    return json_response(payload, code)