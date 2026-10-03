# -*- coding: utf-8 -*-
"""[A8 2026-10-02] 统一收件箱 REST 蓝图 — 跨应用待办聚合 + 平台心跳入口

路由（v1）:
- GET  /api/v1/task-inbox          统一收件箱（entries + counts，按登录人过滤）
- GET  /api/v1/task-inbox/counts   分区角标（全量口径）
- POST /api/v1/platform/tick       平台心跳（派工 / 回收 / 告警；限管理员）
- POST /api/v1/tasks/<task_id>/start  启动一个任务（executor 适配层统一入口；限管理员）

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

from flask import Blueprint, jsonify, request

from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.core.task_inbox import DEFAULT_LIMIT, inbox_counts, inbox_query
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
    """当前用户 id（惯例：user_id 优先，缺省退 username）。"""
    if not user:
        return None
    return user.get('user_id') or user.get('username')


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
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error("[A8] 收件箱查询失败: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'data': result})


@task_inbox_bp.route('/api/v1/task-inbox/counts', methods=['GET'])
@login_required
def task_inbox_count():
    actor = _actor(get_current_user())
    app_id = request.args.get('app_id') or None

    try:
        counts = inbox_counts(_platform_ds(), actor=actor, app_id=app_id)
    except Exception as e:
        logger.error("[A8] 收件箱角标失败: %s", e)
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'data': counts})


@task_inbox_bp.route('/api/v1/platform/tick', methods=['POST'])
@login_required
def platform_tick_route():
    """平台心跳：派工 / 回收 / 告警 / 决策-生效对账（cron 或管理员手动触发）。"""
    user = get_current_user()
    if not is_admin(user):
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

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
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'data': result})


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
        # 任务不存在 / 未知类型 / 载体未实现（agent）→ 409 冲突（无副作用）
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
    return jsonify(payload), code