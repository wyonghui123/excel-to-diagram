# -*- coding: utf-8 -*-
"""
BO 业务 Action: user.update_profile
====================================

用户更新个人信息业务 Action。
从 user_api.py:update_current_user_profile (行 248-273) 迁移。

业务逻辑:
- 接收 allowed_fields: display_name, email, locale, timezone, date_style, time_style, hour_cycle
- 走 BOFramework.update('user', user_id, update_data) 走完整 18 拦截器链
- 自动审计/权限校验/通知
"""
import logging
from typing import Any, Dict

from flask import g, request

logger = logging.getLogger(__name__)


def _get_bo_framework():
    """复用 user_api.py 中的 BOFramework 单例"""
    from meta.core.bo_framework import bo_framework
    return bo_framework


def _set_user_context():
    """设置用户上下文 (BOFramework 拦截器需要)"""
    from meta.services.auth_middleware import get_current_user
    current_user = get_current_user()
    bo = _get_bo_framework()
    bo.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get('display_name', current_user.get('username', 'unknown')),
        ip_address=request.remote_addr,
    )


def user_update_profile_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    user.update_profile Action 处理器

    Args:
        params: {
            'display_name': str (optional),
            'email': str (optional),
            'locale': str (optional),
            'timezone': str (optional),
            'date_style': str (optional),
            'time_style': str (optional),
            'hour_cycle': str (optional),
        }

    Returns:
        {
            'success': True,
            'data': {'updated': [字段列表]},
            'message': '个人信息更新成功',
        }
    """
    # 鉴权
    user_info = g.current_user if hasattr(g, 'current_user') and g.current_user else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}

    user_id = user_info.get('user_id')
    if not user_id:
        return {'success': False, 'data': None, 'message': '用户信息无效'}

    # 白名单过滤
    allowed_fields = [
        'display_name', 'email',
        'locale', 'timezone', 'date_style', 'time_style', 'hour_cycle',
    ]
    update_data = {k: v for k, v in params.items() if k in allowed_fields}

    if not update_data:
        return {'success': False, 'data': None, 'message': '没有可更新的字段'}

    # 简单校验
    if 'email' in update_data:
        email = update_data['email']
        if email and '@' not in email:
            return {'success': False, 'data': None, 'message': '邮箱格式不正确'}

    # 设置上下文并调用 BO
    try:
        _set_user_context()
        bo = _get_bo_framework()
        result = bo.update('user', user_id, update_data)

        if not result.success:
            return {
                'success': False,
                'data': None,
                'message': result.message or '更新失败',
            }

        return {
            'success': True,
            'data': {
                'updated': list(update_data.keys()),
                'user_id': user_id,
            },
            'message': '个人信息更新成功',
        }
    except Exception as e:
        logger.exception(f"[user.update_profile] failed: {e}")
        return {'success': False, 'data': None, 'message': f'更新失败: {e}'}
