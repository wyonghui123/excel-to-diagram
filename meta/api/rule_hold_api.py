# -*- coding: utf-8 -*-
"""规则挂起（holds）API —— spec-rule-model §12.4 M7-3。

端点：
    GET  /api/holds?object_type=&record_id=&rule_key=   活动挂起列表（只读）
    POST /api/holds/<hold_id>/release                   按 id 释放挂起

口径：holds 是挂起状态唯一事实源，写入口只有 ``RuleHoldService``；
释放只 UPDATE ``released_by / released_at``，不删行。
"""

import logging
from typing import Any, Optional

from flask import Blueprint, g, request

from meta.api._response_contract import error_response, ok, ok_list
from meta.api.decorators import require_permission
from meta.services.auth_middleware import login_required
from meta.services.rule_hold_service import (
    RuleHoldService,
    get_rule_hold_service,
)

logger = logging.getLogger(__name__)

rule_hold_bp = Blueprint('rule_hold_api', __name__, url_prefix='/api/holds')

HOLD_NOT_FOUND = 'HOLD_NOT_FOUND'
HOLD_NOT_ACTIVE = 'HOLD_NOT_ACTIVE'


def _record_id(value: Optional[str]) -> Any:
    """query 里的 record_id 是字符串；纯数字归一成 int 以匹配列亲和性。"""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _current_user() -> dict:
    return g.get('current_user') or {}


@rule_hold_bp.route('', methods=['GET'])
@login_required
@require_permission('rule_center:read')
def list_holds():
    """活动挂起列表（``released_at IS NULL``）。"""
    object_type = (request.args.get('object_type') or '').strip()
    if not object_type:
        return error_response('缺少 object_type', status=400,
                              error_code='OBJECT_TYPE_REQUIRED')
    try:
        rows = get_rule_hold_service().active_holds(
            object_type,
            _record_id(request.args.get('record_id')),
            (request.args.get('rule_key') or '').strip() or None,
        )
        return ok_list(rows)
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to list rule holds: %s', e)
        return error_response('读取挂起列表失败', status=500)


@rule_hold_bp.route('/<hold_id>/release', methods=['POST'])
@login_required
@require_permission('rule_center:write')
def release_hold(hold_id: str):
    """释放指定挂起行；已释放 / 不存在分别返回 404 / 409。"""
    payload = request.get_json(force=True, silent=True) or {}
    user = _current_user()
    released_by = (payload.get('released_by')
                   or user.get('username') or user.get('user_id'))
    service: RuleHoldService = get_rule_hold_service()
    try:
        row = service.get(hold_id)
        if not row:
            return error_response('挂起记录不存在', status=404,
                                  error_code=HOLD_NOT_FOUND, details={'hold_id': hold_id})
        released = service.release(
            row['object_type'], row['record_id'], row['rule_key'],
            released_by=released_by)
        if not released:
            return error_response('挂起记录已释放', status=409,
                                  error_code=HOLD_NOT_ACTIVE, details={'hold_id': hold_id})
        return ok({'hold_id': hold_id, 'released': int(released),
                   'released_by': released_by})
    except Exception as e:  # noqa: BLE001
        logger.exception('Failed to release rule hold %s: %s', hold_id, e)
        return error_response('释放挂起失败', status=500)