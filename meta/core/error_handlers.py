# -*- coding: utf-8 -*-
"""统一错误出口（FR-001 / FR-002 / TR-001）。

生产入口（``meta/server.py``）与测试入口（``meta/core/app_builder.py``）
共用本模块，禁止各自注册 JSON/HTML 双轨错误处理器。

约定：
- 任何 HTTP 错误都返回 JSON：``{success: false, message, code, error_code,
  errors?, details?, request_id}``
- 未捕获异常一律 ``internal_error`` + 500，不向客户端泄露 ``str(e)``；
  ``details``（异常类型 / 堆栈）仅非生产环境输出。
- ``PLATFORM_ERROR_CONTRACT_MODE=off`` 时回滚为旧式
  ``{success: false, error, message, status_code}``。
"""
import logging
import os
import traceback

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

from meta.api._response_contract import error_response
from meta.core.error_codes import ErrorCode, HTTP_TO_ERROR_CODE
from meta.core.message_registry import t
from meta.core.platform_flags import OFF, STRICT, error_contract_mode

logger = logging.getLogger(__name__)


def is_production() -> bool:
    """生产环境判定（与 auth_api 的部署约定一致）。"""
    return (
        os.environ.get('FLASK_ENV', '').lower() in ('production', 'staging')
        or os.environ.get('APP_ENV', '').lower() in ('production', 'staging')
        or os.environ.get('FLASK_PRODUCTION', '').lower() == 'true'
    )


def _http_message(status: int) -> str:
    from meta.core.message_registry import MessageRegistry
    key = 'error.http.{0}'.format(status)
    if key in MessageRegistry.keys():
        return t(key)
    return t('error.system.internal') if status >= 500 else t('error.http.400')


def _error_code_for_status(status: int) -> str:
    code = HTTP_TO_ERROR_CODE.get(status)
    if code:
        return code
    return ErrorCode.INTERNAL_ERROR.value if status >= 500 else ErrorCode.BAD_REQUEST.value


def _alert_scope() -> str:
    """告警聚合维度：优先路由 endpoint，退回请求路径（不含查询串）。"""
    try:
        return request.endpoint or request.path or 'unknown'
    except Exception:
        return 'unknown'


def _request_id() -> str:
    try:
        from flask import g
        return getattr(g, 'trace_id', '') or request.headers.get('X-Request-Id', '')
    except Exception:
        return ''


def _observe_error(status: int, error_code: str) -> None:
    """[FR-010] 错误计数；[FR-009] 5xx 触发告警（聚合在 alert service 内完成）。"""
    try:
        from meta.core.observability import metrics_error_inc
        metrics_error_inc(error_code, _alert_scope())
    except Exception:
        pass
    if status < 500:
        return
    try:
        from meta.core.alert_service import report_alert
        report_alert(
            error_code,
            endpoint=_alert_scope(),
            message='HTTP {0} {1}'.format(status, _alert_scope()),
            trace_id=_request_id(),
        )
    except Exception:
        logger.debug('[error-handler] alert report skipped', exc_info=True)


def _legacy_response(status: int, exc_name: str, message: str):
    return jsonify({
        'success': False,
        'error': exc_name,
        'message': message,
        'status_code': status,
    }), status


def _build_http_exception_response(exc: HTTPException):
    status = exc.code or 500
    error_code = _error_code_for_status(status)
    message = _http_message(status)

    if status >= 500:
        logger.error(
            "[error-handler] %s %s -> %s %s",
            request.method, request.path, status, type(exc).__name__,
            exc_info=exc,
        )
    else:
        logger.info(
            "[error-handler] %s %s -> %s %s",
            request.method, request.path, status, type(exc).__name__,
        )

    _observe_error(status, error_code)

    if error_contract_mode() == OFF:
        return _legacy_response(status, exc.name or 'HTTP_ERROR', message)

    details = None
    if status >= 500 and not is_production() and error_contract_mode() != STRICT:
        details = {'exception': type(exc).__name__, 'description': exc.description}

    return error_response(message, error_code=error_code, status=status, details=details)


def _build_unhandled_response(exc: Exception):
    logger.error(
        "[error-handler] 未捕获异常 %s %s -> %s",
        request.method, request.path, type(exc).__name__,
        exc_info=exc,
    )
    message = t('error.system.internal')
    _observe_error(500, ErrorCode.INTERNAL_ERROR.value)
    if error_contract_mode() == OFF:
        return _legacy_response(500, type(exc).__name__, message)

    details = None
    if not is_production() and error_contract_mode() != STRICT:
        details = {
            'exception': type(exc).__name__,
            'traceback': traceback.format_exc(),
        }
    return error_response(
        message,
        error_code=ErrorCode.INTERNAL_ERROR.value,
        status=500,
        details=details,
    )


def register_error_handlers(app) -> None:
    """为 Flask app 注册统一错误处理器（幂等：重复调用会覆盖旧处理器）。"""

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        return _build_http_exception_response(exc)

    @app.errorhandler(Exception)
    def handle_unhandled_exception(exc):
        if isinstance(exc, HTTPException):
            return _build_http_exception_response(exc)
        return _build_unhandled_response(exc)