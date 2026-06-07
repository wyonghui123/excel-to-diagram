# -*- coding: utf-8 -*-
"""
BO 业务 Action: user.change_password
=====================================

用户改密业务 Action。从 auth_api.py:change_password 迁移。
- 校验旧密码
- 写入新密码（hash）
- 清零 must_change_password
"""
import logging
import os
from typing import Any, Dict

from flask import g
from meta.services.auth_provider import LocalAuthProvider
from meta.core.datasource import get_data_source

logger = logging.getLogger(__name__)

_data_source = None
_auth_provider = None


def _get_auth_provider():
    global _data_source, _auth_provider
    if _auth_provider is None:
        if _data_source is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'architecture.db',
            )
            _data_source = get_data_source("sqlite", database=db_path)
        _auth_provider = LocalAuthProvider(_data_source)
    return _auth_provider


def user_change_password_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    user.change_password Action 处理器

    Args:
        params: {
            'old_password': str,
            'new_password': str,
        }
    """
    old_password = params.get('old_password', '')
    new_password = params.get('new_password', '')

    if not old_password or not new_password:
        return {
            'success': False,
            'data': None,
            'message': '旧密码和新密码不能为空',
        }
    if new_password == old_password:
        return {
            'success': False,
            'data': None,
            'message': '新密码不能与旧密码相同',
        }
    if len(new_password) < 6:
        return {
            'success': False,
            'data': None,
            'message': '新密码至少6位',
        }

    # 从 g 拿当前用户
    user_info = g.current_user if hasattr(g, 'current_user') and g.current_user else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}

    user_id = user_info.get('user_id')
    username = user_info.get('username')
    if not user_id or not username:
        return {'success': False, 'data': None, 'message': '用户信息无效'}

    # 1. 校验旧密码
    provider = _get_auth_provider()
    auth_result = provider.authenticate({
        'username': username,
        'password': old_password,
    })
    if not auth_result:
        return {'success': False, 'data': None, 'message': '旧密码错误'}

    # 2. 写新密码
    try:
        # 走 provider 的 password 更新
        # LocalAuthProvider 一般有 update_password 或类似
        # 这里简化为直接 DB 写
        if not hasattr(provider, 'update_password'):
            return {
                'success': False,
                'data': None,
                'message': 'Provider 不支持改密',
            }
        provider.update_password(user_id, new_password)

        # 3. 清零 must_change_password
        if _data_source is not None:
            try:
                _data_source.execute(
                    "UPDATE users SET must_change_password = 0 WHERE id = ?",
                    [user_id],
                )
            except Exception as e:
                logger.warning(f"[user.change_password] clear must_change_password failed: {e}")

    except Exception as e:
        logger.exception(f"[user.change_password] update failed: {e}")
        return {'success': False, 'data': None, 'message': f'改密失败: {e}'}

    return {
        'success': True,
        'data': None,
        'message': '密码修改成功',
    }
