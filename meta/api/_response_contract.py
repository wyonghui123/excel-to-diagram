# -*- coding: utf-8 -*-
"""
API 响应格式统一契约

解决 v1/v2 响应格式不一致问题：
- v1 列表：可能直接返回数组 {success: true, data: [...]}
- v2 列表：返回分页格式 {success: true, data: {items: [...], total, page, page_size}}

统一契约：
- 单条:  {success: bool, data: {...}, message?: str}
- 列表:  {success: bool, data: {items: [...], total: int, page: int, page_size: int}}
- 错误:  {success: false, message: str, code?: str}

使用示例：

    from meta.api._response_contract import (
        ok, ok_list, ok_message, error_response,
        normalize_list_response
    )

    # 1. 单条响应
    @bp.route('/<int:item_id>')
    def get_item(item_id):
        item = service.get(item_id)
        return ok(item)

    # 2. 列表响应（自动分页格式）
    @bp.route('/')
    def list_items():
        items = service.list()
        return ok_list(items, total=len(items))

    # 3. 带分页参数的列表
    @bp.route('/')
    def list_items():
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        items, total = service.list(page=page, page_size=page_size)
        return ok_list(items, total=total, page=page, page_size=page_size)

    # 4. 带消息的成功响应
    @bp.route('/<int:item_id>', methods=['DELETE'])
    def delete_item(item_id):
        service.delete(item_id)
        return ok_message('删除成功')

    # 5. 错误响应
    @bp.errorhandler(404)
    def not_found(e):
        return error_response('资源不存在', code='NOT_FOUND', status=404)
"""
import logging
import uuid
from typing import Any, List, Optional

from flask import g, jsonify, request

from meta.core.error_codes import ALL_CODES, ERROR_HTTP_STATUS
from meta.core.platform_flags import OFF, STRICT, contract_mode

logger = logging.getLogger(__name__)

# 历史大写错误码 → 统一码表值（兼容期内保留映射）
_LEGACY_CODE_ALIASES = {
    'INTERNAL_ERROR': 'internal_error',
    'UNAUTHORIZED': 'unauthorized',
    'FORBIDDEN': 'forbidden',
    'NOT_FOUND': 'not_found',
    'VALIDATION_ERROR': 'data_invalid',
    'INVALID_QUERY': 'invalid_query',
    'DUPLICATE_ID': 'data_conflict',
    'DUPLICATE_CODE': 'duplicate_code',
    'DUPLICATE_NAME': 'duplicate_name',
    'INVALID_MUTABILITY': 'invalid_mutability',
    'INVALID_CODE_FORMAT': 'invalid_code_format',
    'SYSTEM_ENUM_IMMUTABLE': 'system_enum_immutable',
    'SYSTEM_VALUE_IMMUTABLE': 'system_value_immutable',
    'ENUM_TYPE_LOCKED': 'enum_type_locked',
    'ENUM_VALUE_LOCKED': 'enum_value_locked',
    'HAS_VALUES': 'has_values',
    'CODE_IMMUTABLE': 'code_immutable',
    'ID_IMMUTABLE': 'id_immutable',
    'MISSING_DIMENSION_KEY': 'missing_dimension_key',
    'INVALID_DIMENSION_KEY': 'invalid_dimension_key',
    'INVALID_DIMENSION_VALUE': 'invalid_dimension_value',
    'MUTABILITY_CHANGE_REQUIRES_SUPER_ADMIN': 'mutability_change_requires_super_admin',
    'FILE_TOO_LARGE': 'file_too_large',
    'FILE_GENERATION_FAILED': 'file_generation_failed',
    'DATA_NOT_FOUND': 'data_not_found',
    'DATA_CONFLICT': 'data_conflict',
    'DATA_INVALID': 'data_invalid',
    'DATA_REFERENCED': 'data_referenced',
    'ACTION_NOT_FOUND': 'action_not_found',
    'ACTION_VALIDATION_ERROR': 'action_validation_error',
    'ACTION_HANDLER_ERROR': 'action_handler_error',
    'ACTION_PARAMS_MISSING': 'action_params_missing',
    'ACTION_PERMISSION_DENIED': 'action_permission_denied',
    'STATE_MACHINE_VIOLATION': 'STATE_MACHINE_VIOLATION',
    'DEEP_INSERT_FAILED': 'DEEP_INSERT_FAILED',
    'TRANSACTION_ROLLBACK': 'TRANSACTION_ROLLBACK',
}


def normalize_error_code(code: Optional[str], default: str = 'internal_error') -> str:
    """把历史错误码映射到统一码表；无法识别时回落到 ``default``。"""
    if not code:
        return default
    if code in ALL_CODES:
        return code
    alias = _LEGACY_CODE_ALIASES.get(code)
    if alias:
        return alias
    lowered = code.lower()
    return lowered if lowered in ALL_CODES else default


class ResponseContractViolation(ValueError):
    """严格模式（PLATFORM_STRICT_CONTRACT=strict）下的响应契约违规。"""


def _contract_guard(violated: bool, message: str) -> None:
    """统一响应的契约守卫（NFR-005）。

    - strict：抛 `ResponseContractViolation`（强制）
    - shadow：仅记 debug 日志，行为不变（默认）
    - off：不动作
    """
    if not violated:
        return
    mode = contract_mode()
    if mode == STRICT:
        raise ResponseContractViolation(message)
    if mode == OFF:
        return
    logger.debug("[response-contract] %s", message)


def ok(data: Any, message: Optional[str] = None):
    """
    单条数据成功响应

    格式：{success: true, data: {...}, message?: str}
    """
    _contract_guard(
        isinstance(data, (list, tuple)),
        f"ok() 只能返回单条对象，列表请用 ok_list()（实际: {type(data).__name__}）",
    )
    response = {'success': True, 'data': data}
    if message:
        response['message'] = message
    return jsonify(response)


def ok_list(
    items: List[Any],
    total: Optional[int] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
):
    """
    列表成功响应（统一分页格式）

    格式：{success: true, data: {items: [...], total, page, page_size}}

    参数：
    - items: 列表数据
    - total: 总数（默认为 items 长度）
    - page: 当前页码（默认从 request.args 读取）
    - page_size: 每页大小（默认从 request.args 读取）
    """
    if total is None:
        total = len(items)
    if page is None:
        page = request.args.get('page', 1, type=int)
    if page_size is None:
        page_size = request.args.get('page_size', 20, type=int)

    return jsonify({
        'success': True,
        'data': {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
        }
    })


def ok_message(message: str, data: Optional[Any] = None):
    """
    仅消息的成功响应（用于 DELETE/PUT 等无返回数据的操作）

    格式：{success: true, message: str, data?: any}
    """
    response = {'success': True, 'message': message}
    if data is not None:
        response['data'] = data
    return jsonify(response)


def _current_request_id() -> str:
    """取当前请求 trace_id；无上下文时回退生成，保证响应必带 request_id。"""
    try:
        from meta.services.trace_service import get_trace_id

        trace_id = get_trace_id()
    except Exception as exc:  # intentionally-ignored: 无请求上下文时回退 uuid
        logger.debug("[response-contract] trace_id 不可用: %s", exc)
        trace_id = None
    if not trace_id:
        trace_id = getattr(g, 'trace_id', None)
    return trace_id or uuid.uuid4().hex


def error_response(
    message: str,
    code: Optional[str] = None,
    status: Optional[int] = None,
    details: Optional[Any] = None,
    error_code: Optional[str] = None,
    errors: Optional[Any] = None,
):
    """
    错误响应（唯一错误出口，FR-001）

    格式：{success: false, message: str, code: str, error_code: str,
           errors?: any, details?: any, request_id: str}

    - `code` 为历史字段；`error_code` 为统一契约字段，两者同值输出。
    - `status` 缺省时按 error_codes.ERROR_HTTP_STATUS 推导，未知码回落 400。
    - `errors` 为字段级错误数组（ValidationDetail.to_dict() 结构）。
    - `details` 由调用方决定内容；技术细节（堆栈等）仅在非生产环境传入。
    """
    final_code = error_code or code
    if status is None:
        status = ERROR_HTTP_STATUS.get(final_code, 400) if final_code else 400

    response = {
        'success': False,
        'message': message,
        'request_id': _current_request_id(),
    }
    if final_code:
        response['code'] = final_code
        response['error_code'] = final_code
    if details:
        response['details'] = details
    if errors is not None:
        response['errors'] = errors
    return jsonify(response), status


def json_response(payload: Any, status: int = 200):
    """
    兼容既有非标准 payload 的唯一出口（FR-001）。

    仅用于无法无损映射到 ok / ok_list / ok_message / error_response 的
    历史响应结构（如扁平列表、额外字段、`error` 键等）。payload 原样输出，
    不做任何字段增删，保证迁移前后响应体完全一致。

    新增代码不得使用本函数；应收敛到标准助手函数。

    NFR-005：`PLATFORM_STRICT_CONTRACT=strict` 时本函数直接失败（逃生口关闭）。
    """
    _contract_guard(
        True,
        "json_response 是非标准 payload 出口（FR-001），新增代码不得使用",
    )
    return jsonify(payload), status


def normalize_list_response(items: List[Any], total: Optional[int] = None):
    """
    将旧式列表响应包装为统一格式（向后兼容）

    用于逐步迁移旧端点：
    - 旧：{success: true, data: [...]}
    - 新：{success: true, data: {items: [...], total, page, page_size}}

    迁移完成后可直接用 ok_list() 替代。
    """
    return ok_list(items, total=total)
