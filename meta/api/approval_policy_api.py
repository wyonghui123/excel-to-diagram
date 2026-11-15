# -*- coding: utf-8 -*-
"""审批策略配置 API（M3 / spec-approval-workflow §4.2）

端点（v1）:
    GET  /api/v1/approval-policies                 策略列表
    GET  /api/v1/approval-policies/options         编辑器下拉项（元数据派生）
    GET  /api/v1/approval-policies/preview         命中试算（只读）
    GET  /api/v1/approval-policies/<id>            策略详情
    POST /api/v1/approval-policies                 新建策略
    PUT  /api/v1/approval-policies/<id>            保存策略（version + 1）

纪律:
- 权限复用规则中心权限码（`rule_center:read` / `rule_center:write`）；
  仓内无 `approval_policy:*` 权限码，不新增第二套权限真源。
- preview 只做入参消毒 + 委托 `DocumentApprovalResolver`，不实现判定逻辑（D-AP-08）。
- 保存失败（校验 / 编码重复）返回 400；不存在返回 404。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok, ok_list
from meta.api.decorators import require_permission
from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.services import approval_policy_admin_service as service
from meta.services.auth_middleware import get_current_user, login_required

logger = logging.getLogger(__name__)

approval_policy_bp = Blueprint('approval_policy', __name__, url_prefix='/api/v1')


def _platform_ds():
    return get_data_source('sqlite', database=get_meta_db_path())


def _actor(user) -> str:
    if not user:
        return ''
    return user.get('user_id') or user.get('username') or ''


def _error(exc: Exception):
    if isinstance(exc, LookupError):
        return error_response(str(exc), error_code='not_found', status=404)
    if isinstance(exc, ValueError):
        return error_response(str(exc), error_code='data_invalid', status=400)
    raise exc


# ----------------------------------------------------------------------
# 列表 / 选项 / 试算
# ----------------------------------------------------------------------
@approval_policy_bp.route('/approval-policies', methods=['GET'])
@login_required
@require_permission('rule_center:read')
def list_policies():
    try:
        page = request.args.get('page', 1, type=int) or 1
        page_size = request.args.get('page_size', 50, type=int) or 50
        page_size = max(1, min(page_size, 200))
        data = service.list_policies(
            _platform_ds(),
            scope_bo=request.args.get('scope_bo') or None,
            status=request.args.get('status') or None,
            keyword=request.args.get('keyword') or None,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return ok_list(data['items'], total=data['total'],
                       page=page, page_size=page_size)
    except Exception as exc:  # noqa: BLE001
        logger.exception('查询审批策略失败: %s', exc)
        return error_response('查询审批策略失败', status=500)


@approval_policy_bp.route('/approval-policies/options', methods=['GET'])
@login_required
@require_permission('rule_center:read')
def policy_options():
    try:
        return ok(service.options())
    except Exception as exc:  # noqa: BLE001
        logger.exception('加载审批策略选项失败: %s', exc)
        return error_response('加载审批策略选项失败', status=500)


@approval_policy_bp.route('/approval-policies/preview', methods=['GET'])
@login_required
@require_permission('rule_center:read')
def preview_policy():
    object_type = (request.args.get('object_type') or '').strip()
    record_id = (request.args.get('record_id') or '').strip()
    trigger_action = (request.args.get('trigger_action') or 'submit').strip()
    if not object_type or not record_id:
        return error_response('object_type / record_id 必填',
                              error_code='data_invalid', status=400)
    try:
        return ok(service.preview(_platform_ds(), object_type, record_id,
                                  trigger_action))
    except Exception as exc:  # noqa: BLE001
        try:
            return _error(exc)
        except Exception:  # noqa: BLE001
            logger.exception('审批策略试算失败: %s', exc)
            return error_response('审批策略试算失败', status=500)


# ----------------------------------------------------------------------
# 详情 / 保存
# ----------------------------------------------------------------------
@approval_policy_bp.route('/approval-policies/<int:policy_id>', methods=['GET'])
@login_required
@require_permission('rule_center:read')
def get_policy(policy_id: int):
    try:
        policy = service.get_policy(_platform_ds(), policy_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception('读取审批策略失败: %s', exc)
        return error_response('读取审批策略失败', status=500)
    if not policy:
        return error_response('审批策略不存在', error_code='not_found', status=404)
    return ok(policy)


@approval_policy_bp.route('/approval-policies', methods=['POST'])
@login_required
@require_permission('rule_center:write')
def create_policy():
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        return ok(service.save_policy(_platform_ds(), payload,
                                      actor=_actor(get_current_user())))
    except Exception as exc:  # noqa: BLE001
        try:
            return _error(exc)
        except Exception:  # noqa: BLE001
            logger.exception('新建审批策略失败: %s', exc)
            return error_response('新建审批策略失败', status=500)


@approval_policy_bp.route('/approval-policies/<int:policy_id>', methods=['PUT'])
@login_required
@require_permission('rule_center:write')
def update_policy(policy_id: int):
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        return ok(service.save_policy(_platform_ds(), payload,
                                      policy_id=policy_id,
                                      actor=_actor(get_current_user())))
    except Exception as exc:  # noqa: BLE001
        try:
            return _error(exc)
        except Exception:  # noqa: BLE001
            logger.exception('保存审批策略失败: %s', exc)
            return error_response('保存审批策略失败', status=500)