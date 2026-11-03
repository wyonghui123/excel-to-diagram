# -*- coding: utf-8 -*-
"""G4 工程变更单 API

    GET    /api/v1/engineering-changes                      列表
    GET    /api/v1/engineering-changes/<id>                 详情
    POST   /api/v1/engineering-changes                      创建（draft）
    POST   /api/v1/engineering-changes/diff                 diff 预览（只读）
    POST   /api/v1/engineering-changes/<id>/submit          提交评审
    POST   /api/v1/engineering-changes/<id>/approve         批准
    POST   /api/v1/engineering-changes/<id>/reject          驳回
    POST   /api/v1/engineering-changes/<id>/cancel          取消
    POST   /api/v1/engineering-changes/<id>/apply           应用到生产 BOM
    GET    /api/v1/engineering-changes/<id>/where-used      影响预览（只读）

依据:
  docs/specs/spec-project-g4-engineering-bom-2026-11-03.md §7 / §13

口径:
  · 统一响应契约（ok / error_response），禁止直接 jsonify。
  · 权限：view / create / approve / apply 四码；submit/cancel 归 create，
    reject 归 approve（与 §7 权限表一致）。
  · 所有业务规则在服务层强制；本层只做参数解包、权限与 HTTP 映射。
"""
import logging
from typing import Any, Optional

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.services.auth_middleware import get_current_user, require_permission
from meta.services.engineering_change_service import (
    EngineeringChangeError,
    EngineeringChangeService,
)

logger = logging.getLogger(__name__)

engineering_change_bp = Blueprint(
    'engineering_change', __name__, url_prefix='/api/v1/engineering-changes')

_service: Optional[EngineeringChangeService] = None


def init_service(data_source=None) -> EngineeringChangeService:
    """测试传内存 / 临时数据源；生产懒取 meta 库（路径走 get_meta_db_path）。"""
    global _service
    if data_source is not None:
        _service = EngineeringChangeService(data_source)
    elif _service is None:
        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        data_source = get_data_source('sqlite', database=get_meta_db_path())
        _service = EngineeringChangeService(data_source)
    return _service


def _get_service() -> EngineeringChangeService:
    init_service()
    return _service


def _actor() -> str:
    user = get_current_user() or {}
    return (user.get('username') or user.get('display_name')
            or str(user.get('user_id') or ''))


def _payload() -> dict:
    return request.get_json(silent=True) or {}


def _error(e: EngineeringChangeError):
    status = 400
    if e.rule == 'EC_NOT_FOUND':
        status = 404
    elif e.rule in ('EC_CONFLICT_APPROVED', 'EC_REVISION_DRIFT'):
        status = 409
    details = dict(e.details or {})
    if e.field_name:
        details.setdefault('field', e.field_name)
    return error_response(e.message, code=e.rule, status=status,
                          details=details or None)


def _int_param(name: str) -> Optional[int]:
    raw = request.args.get(name)
    if raw in (None, ''):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@engineering_change_bp.route('', methods=['GET'])
@engineering_change_bp.route('/', methods=['GET'])
@require_permission('engineering_change:engineering_change_view')
def list_engineering_changes():
    service = _get_service()
    page = _int_param('page') or 1
    page_size = _int_param('page_size') or 20
    try:
        result = service.list_changes(
            status=request.args.get('status'),
            item_id=_int_param('item_id'),
            project_id=_int_param('project_id'),
            page=page, page_size=page_size,
        )
    except EngineeringChangeError as e:
        return _error(e)
    except Exception as e:  # noqa: BLE001
        logger.exception('[engineering_change] 列表查询失败')
        return error_response('工程变更单列表查询失败',
                              code='ENGINEERING_CHANGE_LIST_ERROR', status=500,
                              details=str(e))
    return ok(result)


@engineering_change_bp.route('/diff', methods=['POST'])
@require_permission('engineering_change:engineering_change_view')
def diff_engineering_change():
    payload = _payload()
    service = _get_service()
    try:
        result = service.diff_structures(
            payload.get('source_structure_id'),
            payload.get('target_structure_id'),
            payload.get('as_of'),
        )
    except EngineeringChangeError as e:
        return _error(e)
    except Exception as e:  # noqa: BLE001
        logger.exception('[engineering_change] diff 预览失败')
        return error_response('工程 BOM 差异预览失败',
                              code='ENGINEERING_CHANGE_DIFF_ERROR', status=500,
                              details=str(e))
    return ok(result)


@engineering_change_bp.route('/<int:change_id>', methods=['GET'])
@require_permission('engineering_change:engineering_change_view')
def get_engineering_change(change_id):
    service = _get_service()
    try:
        result = service.get_change(change_id)
    except EngineeringChangeError as e:
        return _error(e)
    except Exception as e:  # noqa: BLE001
        logger.exception('[engineering_change] 详情查询失败: id=%s', change_id)
        return error_response('工程变更单详情查询失败',
                              code='ENGINEERING_CHANGE_DETAIL_ERROR', status=500,
                              details=str(e))
    return ok(result)


@engineering_change_bp.route('', methods=['POST'])
@engineering_change_bp.route('/', methods=['POST'])
@require_permission('engineering_change:engineering_change_create')
def create_engineering_change():
    payload = _payload()
    lines = payload.get('lines')
    if lines is not None and not isinstance(lines, list):
        return error_response('lines 必须为数组', code='INVALID_PARAMETER',
                              status=400, details={'field': 'lines'})
    service = _get_service()
    try:
        result = service.create_change(
            change_type=payload.get('change_type'),
            title=payload.get('title'),
            reason=payload.get('reason'),
            effective_date=payload.get('effective_date'),
            project_id=payload.get('project_id'),
            lines=lines or [],
            actor=_actor(),
        )
    except EngineeringChangeError as e:
        return _error(e)
    except Exception as e:  # noqa: BLE001
        logger.exception('[engineering_change] 创建失败')
        return error_response('工程变更单创建失败',
                              code='ENGINEERING_CHANGE_CREATE_ERROR', status=500,
                              details=str(e))
    return ok(result)


@engineering_change_bp.route('/<int:change_id>/submit', methods=['POST'])
@require_permission('engineering_change:engineering_change_create')
def submit_engineering_change(change_id):
    payload = _payload()
    try:
        result = _get_service().submit(change_id, actor=_actor(),
                                       note=payload.get('comment'))
    except EngineeringChangeError as e:
        return _error(e)
    return ok(result)


@engineering_change_bp.route('/<int:change_id>/approve', methods=['POST'])
@require_permission('engineering_change:engineering_change_approve')
def approve_engineering_change(change_id):
    payload = _payload()
    try:
        result = _get_service().approve(change_id, actor=_actor(),
                                        comment=payload.get('comment'))
    except EngineeringChangeError as e:
        return _error(e)
    return ok(result)


@engineering_change_bp.route('/<int:change_id>/reject', methods=['POST'])
@require_permission('engineering_change:engineering_change_approve')
def reject_engineering_change(change_id):
    payload = _payload()
    try:
        result = _get_service().reject(change_id, payload.get('reason'),
                                       actor=_actor())
    except EngineeringChangeError as e:
        return _error(e)
    return ok(result)


@engineering_change_bp.route('/<int:change_id>/cancel', methods=['POST'])
@require_permission('engineering_change:engineering_change_create')
def cancel_engineering_change(change_id):
    payload = _payload()
    try:
        result = _get_service().cancel(change_id, actor=_actor(),
                                       reason=payload.get('reason'))
    except EngineeringChangeError as e:
        return _error(e)
    return ok(result)


@engineering_change_bp.route('/<int:change_id>/apply', methods=['POST'])
@require_permission('engineering_change:engineering_change_apply')
def apply_engineering_change(change_id):
    try:
        result = _get_service().apply(change_id, actor=_actor())
    except EngineeringChangeError as e:
        return _error(e)
    except Exception as e:  # noqa: BLE001
        logger.exception('[engineering_change] 应用失败: id=%s', change_id)
        return error_response('工程变更应用失败',
                              code='ENGINEERING_CHANGE_APPLY_ERROR', status=500,
                              details=str(e))
    return ok(result)


@engineering_change_bp.route('/<int:change_id>/where-used', methods=['GET'])
@require_permission('engineering_change:engineering_change_view')
def where_used_engineering_change(change_id):
    service = _get_service()
    try:
        result = service.where_used(change_id)
    except EngineeringChangeError as e:
        return _error(e)
    except Exception as e:  # noqa: BLE001
        logger.exception('[engineering_change] 影响预览失败: id=%s', change_id)
        return error_response('工程变更影响预览失败',
                              code='ENGINEERING_CHANGE_WHERE_USED_ERROR', status=500,
                              details=str(e))
    return ok(result)
