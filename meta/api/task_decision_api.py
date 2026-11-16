# -*- coding: utf-8 -*-
"""[B3 2026-10-03] 审批决策 REST 蓝图 — 决策-生效分离协议的提交入口（接线点①）

路由（v1）:
- POST /api/v1/tasks/<task_id>/decision   提交一次审批决策（approve / reject）

纪律（§9.7 / §12.1 B3 / Q1）:
- 本路由是决策-生效协议的**唯一**生产调用方：薄适配层只做「权限映射 + body 消毒」，
  协议本体（先 BO 生效、后任务归位、幂等、四眼）全部复用 meta.core.decision_effect。
- 审核权限事实来源（D-AP-06）：admin 短路；其余按 `{doc_ref_type}:approve` 判定，
  单据类型未知（历史任务无 `doc_ref_type`）时 **fail-closed**。
- **禁止**客户端指定 submitter_id / four_eyes / reviewer_permission：四眼基准取自任务
  的 created_by，由服务端裁决，否则可绕过 maker-checker（§9.7 规范 3）。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.7 / §12.1 B3 / §12.1 Q1
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.core.decision_effect import (
    DecisionEffectError, EffectNotAppliedError,
)
from meta.core.permission_gate import user_has_permission
from meta.services.auth_middleware import get_current_user, is_admin, login_required
from meta.services.task_participation import (   # [M4-2 2026-11-15] 参与归并薄层
    ParticipationConflictError, ParticipationNotFoundError,
    ParticipationPermissionError, ParticipationServiceError,
    decide_with_participation,
)

logger = logging.getLogger(__name__)

task_decision_bp = Blueprint('task_decision', __name__)

# 客户端禁传字段（四眼 / 权限事实由服务端裁决，§9.7 规范 3）
_FORBIDDEN_BODY_KEYS = ('submitter_id', 'four_eyes', 'reviewer_permission')


def _actor(user) -> str:
    if not user:
        return ''
    # 统一字符串：user_id 为 int 时与参与流水的 participant（字符串）精确比较会失败，
    # 导致误入 admin 短路分支、多阶段永不推进（live 冒烟发现）。
    return str(user.get('user_id') or user.get('username') or '')


def _task_object_type(data_source, task_id: str) -> str:
    """任务单据对象类型（审批任务在途判重列）；历史任务为空串 ⇒ 权限 fail-closed。"""
    try:
        rows = data_source.query(
            'SELECT doc_ref_type FROM tasks WHERE id = ?', [str(task_id)])
    except Exception as exc:  # noqa: BLE001 - 判权限不阻断决策协议，缺失即视为未知
        logger.warning('[B3] 读取任务 %s 单据类型失败: %s', task_id, exc)
        return ''
    if not rows:
        return ''
    return str(rows[0].get('doc_ref_type') or '')


def _reviewer_permission(user, object_type: str) -> bool:
    """审核权限事实（D-AP-06）：admin 短路，否则校验 `{bo}:approve`。"""
    if not user:
        return False
    if is_admin(user):
        return True
    if not object_type:
        return False
    return user_has_permission(
        user.get('permissions') or [], '%s:approve' % object_type)


def _platform_ds():
    return get_data_source("sqlite", database=get_meta_db_path())


def submit_decision(
    data_source,
    task_id: str,
    *,
    user,
    body: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], int]:
    """可测的决策提交服务：body 消毒 → 权限映射 → 调协议 → 错误映射。

    Returns:
        (payload, http_status)
    """
    body = body or {}
    for key in _FORBIDDEN_BODY_KEYS:
        if key in body:
            return {
                'success': False,
                'message': f'不允许客户端指定 {key}（由服务端裁决，§9.7 规范 3）',
            }, 400

    decision = (body.get('decision') or '').strip()
    comment = body.get('comment') or ''
    allow_rework = bool(body.get('allow_rework', False))

    try:
        outcome = decide_with_participation(
            data_source, str(task_id),
            decision=decision,
            comment=comment,
            actor=_actor(user),
            reviewer_permission=_reviewer_permission(
                user, _task_object_type(data_source, task_id)),
            allow_rework=allow_rework,
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
    except DecisionEffectError as e:
        # 入口/守卫不满足（未调 BO，无副作用）→ 409 冲突（含任务不存在 / 类型不符）
        return {'success': False, 'message': str(e)}, 409
    except EffectNotAppliedError as e:
        # BO 未返回生效回执（未迁移，可重试）→ 502
        return {'success': False, 'message': str(e), 'retryable': True}, 502
    except Exception as e:  # noqa: BLE001 - 兜底，避免裸栈
        logger.error('[B3] 决策提交失败: %s', e)
        return {'success': False, 'message': str(e)}, 500

    return {'success': True, 'data': outcome}, 200


@task_decision_bp.route('/api/v1/tasks/<task_id>/decision', methods=['POST'])
@login_required
def task_decision_submit(task_id: str):
    body = request.get_json(silent=True) or {}
    payload, code = submit_decision(
        _platform_ds(), task_id, user=get_current_user(), body=body,
    )
    return jsonify(payload), code