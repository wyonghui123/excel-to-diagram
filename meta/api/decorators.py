# -*- coding: utf-8 -*-
from functools import wraps
from flask import g, jsonify, request
import logging

logger = logging.getLogger(__name__)


def require_permission(permission_code):
    """
    API 端点权限校验装饰器

    在 @login_required 之后使用，确保当前用户拥有指定权限。
    无权限时返回 403 Forbidden。

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
            user_id = g.get('user_id')
            if not user_id:
                return jsonify({
                    'success': False,
                    'error': 'UNAUTHORIZED',
                    'message': 'Authentication required'
                }), 401

            if not _check_permission(user_id, permission_code):
                logger.warning(
                    f"[require_permission] Denied: user_id={user_id}, "
                    f"permission={permission_code}, "
                    f"path={request.path}"
                )
                return jsonify({
                    'success': False,
                    'error': 'FORBIDDEN',
                    'message': f'Permission denied: {permission_code}'
                }), 403

            return f(*args, **kwargs)
        return wrapper
    return decorator


def _check_permission(user_id, permission_code):
    try:
        from meta.services.permission_sync_service import PermissionSyncService
        svc = PermissionSyncService()
        return svc.check_user_permission(user_id, permission_code)
    except Exception as e:
        logger.error(f"[require_permission] Permission check failed: {e}")
        return False
