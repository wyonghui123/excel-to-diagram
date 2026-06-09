# -*- coding: utf-8 -*-
"""
权限检查中间件
"""

from functools import wraps
from flask import request, g, jsonify, make_response, current_app
from meta.services.token_service import TokenService
from meta.services.token_blacklist_service import token_blacklist_service


SELF_SERVICE_WHITELIST = {
    ('POST', '/api/v1/auth/change-password'),
    ('GET', '/api/v1/auth/me'),
    ('PUT', '/api/v1/users/self'),
    ('GET', '/api/v1/users/self'),
    ('GET', '/api/v1/data-permissions/self'),
}


def is_self_service():
    """Check if current request is a self-service operation"""
    return (request.method, request.path) in SELF_SERVICE_WHITELIST


def _extract_token():
    auth_header = request.headers.get('Authorization', '').strip()
    if auth_header and auth_header.lower().startswith('bearer '):
        token = auth_header[7:].strip()
        if token:
            return token
    token = request.cookies.get('auth_token')
    if token:
        return token
    return ''


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()

        if not token:
            return jsonify({'error': '未登录', 'code': 'UNAUTHORIZED'}), 401

        try:
            if token_blacklist_service.is_blacklisted(token):
                return jsonify({'error': 'Token已失效', 'code': 'TOKEN_INVALID'}), 401
        except Exception:
            return jsonify({'error': '认证服务异常', 'code': 'AUTH_SERVICE_ERROR'}), 401

        user_info = TokenService.verify_token(token)
        if not user_info:
            return jsonify({'error': '登录已过期', 'code': 'TOKEN_EXPIRED'}), 401

        from meta.services.token_version_service import token_version_service
        user_id = user_info.get('user_id', 0)
        token_version = user_info.get('token_version', 0)
        if user_id and token_version and not token_version_service.check(user_id, token_version):
            return jsonify({'error': '权限已变更，请重新登录', 'code': 'TOKEN_STALE'}), 401

        g.current_user = user_info

        resp = make_response(f(*args, **kwargs))
        # [TEST-FIX] 在测试环境中不设置 auth_token cookie
        # 避免测试客户端累积 cookie 导致后续"未认证"测试意外通过
        if not current_app.config.get('TESTING'):
            resp.set_cookie(
                'auth_token',
                value=token,
                max_age=86400 * 7,
                httponly=True,
                secure=False,
                samesite='Lax',
                path='/',
            )
        return resp
    return decorated


def require_permission(permission_code: str):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            if is_self_service():
                return f(*args, **kwargs)
            
            user_permissions = g.current_user.get('permissions', [])

            if '*' in user_permissions:
                return f(*args, **kwargs)

            if permission_code not in user_permissions:
                return jsonify({
                    'error': f'需要权限: {permission_code}',
                    'code': 'FORBIDDEN',
                    'required_permission': permission_code
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def require_permission_unified(resource_type: str, action_code: str):
    """
    统一语义的权限检查装饰器
    
    参数：
    - resource_type: 业务对象类型
    - action_code: 服务动作编码
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            if is_self_service():
                return f(*args, **kwargs)
            
            # 构建权限编码
            permission_code = f"{resource_type}:{action_code}"
            
            user_permissions = g.current_user.get('permissions', [])

            # 超级管理员
            if '*' in user_permissions:
                return f(*args, **kwargs)

            # 检查权限
            if permission_code not in user_permissions:
                return jsonify({
                    'error': f'需要权限: {permission_code}',
                    'code': 'FORBIDDEN',
                    'required_permission': permission_code,
                    'resource_type': resource_type,
                    'action_code': action_code
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def get_current_user():
    return getattr(g, 'current_user', None)


def is_admin(user_info=None):
    """
    检查用户是否为超级管理员
    
    判断逻辑（按优先级）：
    1. 用户拥有 '*' 通配权限
    2. 用户任一角色的 is_super_admin 字段为 True
    
    注意：不再硬编码检查角色名称 'admin'，而是通过角色的 is_super_admin 标记判断
    """
    info = user_info or get_current_user()
    if not info:
        return False
    
    if '*' in info.get('permissions', []):
        return True
    
    roles = info.get('roles', [])
    for role in roles:
        if isinstance(role, dict) and role.get('is_super_admin'):
            return True
        elif isinstance(role, str):
            pass
    
    return False
