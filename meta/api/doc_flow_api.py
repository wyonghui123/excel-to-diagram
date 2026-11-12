# -*- coding: utf-8 -*-
"""单据流服务 HTTP API（/api/v2/doc-flow）。

五个只做「参数翻译 + 错误映射」的端点：
  GET  /rules    规则清单（含 display_fields / 目标模式）
  GET  /sources  上游实例 + 已生成 + 未结量（分页）
  POST /derive   按上游行生成本次下游数量（批量）
  GET  /edges    边追溯（源侧或目标侧二选一）
  GET  /trace    头→行展开后的上下游追溯（id 可传单据头或行）

视图体与装饰器分离：`_xxx_view()` 是纯函数（测试直接调用），
`xxx()` 只负责套 `@login_required`。
"""

import logging
from typing import Any, Dict, Tuple

from flask import Blueprint, request

from meta.services.auth_middleware import (
    check_generic_read_permission,
    login_required,
)
from meta.services.doc_flow_service import (
    DocFlowServiceError,
    get_doc_flow_service,
)
from meta.services.trace_service import get_trace_id

logger = logging.getLogger(__name__)

doc_flow_bp = Blueprint('doc_flow', __name__, url_prefix='/api/v2/doc-flow')

_EDGE_ARGS = ('source_bo', 'source_id', 'source_item', 'target_bo', 'target_id')


def _ok(data: Any, message: str = '') -> Tuple[Dict[str, Any], int]:
    """统一返回 `(payload, status)`，与 `_fail` 同形，便于视图直接作为路由返回值。"""
    return {'success': True, 'data': data, 'message': message}, 200


def _fail(code: str, message: str, status: int = 400) -> Tuple[Dict[str, Any], int]:
    return {'success': False, 'data': None,
            'message': message, 'code': code}, status


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _filters_from_args() -> Dict[str, Any]:
    """把 `filter_<field>=<value>` 折叠成 dict，值域由服务层白名单裁决。"""
    filters: Dict[str, Any] = {}
    for key, value in request.args.items():
        if key.startswith('filter_') and value != '':
            filters[key[len('filter_'):]] = value
    return filters


def _forbidden(bo: Any) -> Any:
    """对象读权限判定：放行返回 None，拒绝返回 `(payload, 403)`。"""
    object_id = (bo or '').strip() if isinstance(bo, str) else ''
    if not object_id:
        return None
    decision = check_generic_read_permission(object_id)
    if decision is None:
        return None
    return _fail('DOC_FLOW_FORBIDDEN',
                 '无权访问对象: {0}'.format(object_id), 403)


# ----------------------------------------------------------------------
# 视图体（无装饰器，便于单元测试）
# ----------------------------------------------------------------------
def _rules_view() -> Tuple[Dict[str, Any], int]:
    service = get_doc_flow_service()
    data = service.list_rules(
        source_bo=request.args.get('source_bo') or None,
        target_bo=request.args.get('target_bo') or None)
    return _ok(data)


def _sources_view() -> Any:
    service = get_doc_flow_service()
    rule_id = request.args.get('rule_id') or ''
    if not rule_id:
        return _fail('DOC_FLOW_RULE_INVALID', '缺少 rule_id', 400)
    try:
        data = service.list_sources(
            rule_id,
            filters=_filters_from_args(),
            include_zero_open=(request.args.get('include_zero_open') or '')
            .lower() in ('1', 'true', 'yes'),
            page=_as_int(request.args.get('page'), 1),
            page_size=_as_int(request.args.get('page_size'), 20),
            source_item=request.args.get('source_item') or '')
    except DocFlowServiceError as error:
        return _fail(error.code, error.message, error.status)
    return _ok(data)


def _derive_view() -> Any:
    service = get_doc_flow_service()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return _fail('DOC_FLOW_QTY_INVALID', '请求体必须是 JSON 对象', 400)
    if not payload.get('rule_id'):
        return _fail('DOC_FLOW_QTY_INVALID', '缺少 rule_id', 400)
    try:
        data = service.derive(payload, derived_by='doc_flow_api',
                              trace_id=get_trace_id() or '')
    except DocFlowServiceError as error:
        return _fail(error.code, error.message, error.status)
    return _ok(data, '已生成 {0} 条下游边'.format(data.get('total_edges', 0)))


def _edges_view() -> Any:
    service = get_doc_flow_service()
    kwargs = {key: request.args.get(key) for key in _EDGE_ARGS
              if request.args.get(key) not in (None, '')}
    if not kwargs:
        return _fail('DOC_FLOW_EDGE_FILTER_REQUIRED',
                     '至少提供一个追溯条件（source_bo+source_id 或 target_bo+target_id）',
                     400)
    for key in ('source_bo', 'target_bo'):
        denied = _forbidden(kwargs.get(key))
        if denied is not None:
            return denied
    try:
        data = service.list_edges(**kwargs)
    except DocFlowServiceError as error:
        return _fail(error.code, error.message, error.status)
    return _ok(data)


def _trace_view() -> Any:
    """头→行展开追溯：`bo` + `id`（id 可传单据头或行）。"""
    service = get_doc_flow_service()
    bo = (request.args.get('bo') or '').strip()
    record_id = (request.args.get('id') or '').strip()
    if not bo or not record_id:
        return _fail('DOC_FLOW_TRACE_ARGS_REQUIRED', '缺少 bo 或 id', 400)
    denied = _forbidden(bo)
    if denied is not None:
        return denied
    try:
        data = service.trace_records(bo, record_id)
    except DocFlowServiceError as error:
        return _fail(error.code, error.message, error.status)
    return _ok(data)


# ----------------------------------------------------------------------
# 路由壳
# ----------------------------------------------------------------------
@doc_flow_bp.route('/rules', methods=['GET'])
@login_required
def list_rules_route():
    return _rules_view()


@doc_flow_bp.route('/sources', methods=['GET'])
@login_required
def list_sources_route():
    return _sources_view()


@doc_flow_bp.route('/derive', methods=['POST'])
@login_required
def derive_route():
    return _derive_view()


@doc_flow_bp.route('/edges', methods=['GET'])
@login_required
def list_edges_route():
    return _edges_view()


@doc_flow_bp.route('/trace', methods=['GET'])
@login_required
def trace_route():
    return _trace_view()