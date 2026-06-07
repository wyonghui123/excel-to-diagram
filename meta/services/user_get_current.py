# -*- coding: utf-8 -*-
"""
BO 业务 Action: user.get_current
=================================

获取当前登录用户信息。从 auth_api.py:me 迁移。
- 从 context (g.current_user) 拿当前用户
- 返回统一 user 结构
"""
import logging
from typing import Any, Dict

from flask import g

logger = logging.getLogger(__name__)


def user_get_current_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    user.get_current Action 处理器

    Returns:
        {
            'success': True,
            'data': {
                'user_id': int,
                'username': str,
                'display_name': str,
                'email': str,
                'roles': [...],
                'permissions': [...],
            },
            'message': '',
        }
    """
    user_info = g.current_user if hasattr(g, 'current_user') and g.current_user else None
    if not user_info:
        return {
            'success': False,
            'data': None,
            'message': '未登录',
        }

    return {
        'success': True,
        'data': {
            'user_id': user_info.get('user_id'),
            'username': user_info.get('username'),
            'display_name': user_info.get('display_name') or user_info.get('username', ''),
            'email': user_info.get('email', ''),
            'roles': user_info.get('roles', []),
            'permissions': user_info.get('permissions', []),
        },
        'message': '',
    }
