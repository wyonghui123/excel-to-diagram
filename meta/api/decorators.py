# -*- coding: utf-8 -*-
from functools import wraps
from flask import g, request
import logging

from meta.api._response_contract import json_response
from meta.core.permission_gate import declare_permission, evaluate_code

logger = logging.getLogger(__name__)


def require_permission(permission_code):
    """
    API 端点权限校验装饰器

    在 @login_required 之后使用，确保当前用户拥有指定权限。
    无权限时返回 403 Forbidden。

    [FR-005] 判定统一走 meta.core.permission_gate（与 BO 拦截器共用同一解析）。

    Usage:
        @app.route('/api/v1/users')
        @login_required
        @require_permission('user_read')
        def get_users():
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_info = g.get('current_user')
            if not user_info:
                return json_response({
                    'success': False,
                    'error': 'UNAUTHORIZED',
                    'message': '请先登录后再操作'
                }, 401)

            if not evaluate_code(user_info, permission_code):
                logger.warning(
                    f"[require_permission] Denied: user_id={user_info.get('user_id')}, "
                    f"permission={permission_code}, "
                    f"path={request.path}"
                )
                return json_response({
                    'success': False,
                    'error': 'FORBIDDEN',
                    'message': f'Permission denied: {permission_code}'
                }, 403)

            return f(*args, **kwargs)
        return wrapper
    return decorator


__all__ = ['require_permission', 'declare_permission']
