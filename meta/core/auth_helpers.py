# -*- coding: utf-8 -*-
r"""
Auth Helpers — 简化的认证辅助函数

【背景 2026-06-04】
P2 E2E 测试发现：overlap_api.py 引用 is_authenticated()，
但 auth_helpers.py 不存在，导致所有 overlap 端点 500。

实施：基于 Flask session 的简化认证检查
"""
from flask import session


def is_authenticated() -> bool:
    """检查当前用户是否已登录

    Returns:
        bool: True 表示已登录
    """
    # 检查 session 是否有 user_id 或 user info
    if session.get('user_id'):
        return True
    if session.get('user'):
        return True
    if session.get('logged_in'):
        return True
    return False


def get_current_user_id() -> int:
    """获取当前登录用户 ID

    Returns:
        int: 用户 ID，未登录返回 0
    """
    return session.get('user_id', 0)


def require_auth(f):
    """装饰器：要求登录"""
    from functools import wraps
    from flask import jsonify
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            return jsonify({'success': False, 'error': '未登录'}), 401
        return f(*args, **kwargs)
    return wrapper
