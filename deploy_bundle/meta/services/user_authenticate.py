# -*- coding: utf-8 -*-
"""
BO 业务 Action: user.authenticate
=================================

用户登录认证业务 Action。
作为 v3 BO Action 体系的**首个业务 Action** 实现，演示如何把现有
auth_api.py 的业务逻辑下沉到 BO Action 体系。

**关键特性**:
- 接收 params (username, password) 返回 user info + token
- 内部走完整鉴权链路: rate_limiter → auth_provider → token_service → must_change_password
- 返回结构与现有 auth_api.py login endpoint 兼容
- 业务 Action 后续可被前端 useBoAction() 直接调用, 而无需单独 endpoint

**业务逻辑与 auth_api.py:login() 完全一致**, 仅迁移到 BO Action 命名空间。
"""
import logging
import os
from typing import Any, Dict

from meta.services.auth_provider import LocalAuthProvider
from meta.services.token_service import TokenService
from meta.services.rate_limiter import rate_limiter
from meta.core.datasource import get_data_source

logger = logging.getLogger(__name__)


# 单例: data_source / provider
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


def user_authenticate_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    user.authenticate Action 处理器

    Args:
        params: {'username': str, 'password': str}
        context: {'user_id', 'user_name', 'ip_address', 'permissions'}

    Returns:
        {
            'success': bool,
            'data': {
                'user': {...},
                'must_change_password': bool,
            } | None,
            'message': str,
        }
    """
    username = (params.get('username') or '').strip()
    password = params.get('password', '')

    # 1. 输入校验
    if not username or not password:
        return {
            'success': False,
            'data': None,
            'message': '用户名和密码不能为空',
        }

    # 2. 速率限制
    client_ip = (context or {}).get('ip_address', '')
    is_locked, lockout_msg = rate_limiter.check_rate_limit(client_ip, username)
    if is_locked:
        return {
            'success': False,
            'data': None,
            'message': lockout_msg or '登录尝试过于频繁',
        }

    # 3. 认证
    provider = _get_auth_provider()
    user_info = provider.authenticate({'username': username, 'password': password})

    if not user_info:
        # 记录失败
        is_locked_after, lockout_msg_after = rate_limiter.record_failed_attempt(
            client_ip, username
        )
        return {
            'success': False,
            'data': None,
            'message': (
                lockout_msg_after
                if is_locked_after
                else f'用户名或密码错误 ({lockout_msg_after})'
            ),
        }

    # 4. 成功: 重置速率限制
    rate_limiter.record_successful_attempt(client_ip, username)

    # 5. 创建 token
    token, expires_at = TokenService.create_token(user_info)

    # 6. 查询 must_change_password
    must_change_password = False
    try:
        if _data_source is not None:
            cursor = _data_source.execute(
                "SELECT must_change_password FROM users WHERE id = ?",
                [user_info.user_id],
            )
            row = cursor.fetchone()
            if row:
                # row 可能是 tuple 或 dict
                if isinstance(row, dict):
                    must_change_password = bool(row.get('must_change_password', 0))
                else:
                    must_change_password = bool(row[0])
    except Exception as e:
        logger.warning(f"[user.authenticate] Failed to query must_change_password: {e}")

    # 7. 构造返回 (兼容现有 auth_api.py:login)
    result = {
        'success': True,
        'data': {
            'user': {
                'user_id': user_info.user_id,
                'username': user_info.username,
                'display_name': user_info.display_name,
                'email': getattr(user_info, 'email', ''),
                'roles': user_info.roles,
                'permissions': user_info.permissions,
            },
            'token': token,
            'must_change_password': must_change_password,
        },
        'message': '登录成功',
    }
    logger.info(
        f"[user.authenticate] OK user={username} ip={client_ip} "
        f"roles={len(user_info.roles)} perms={len(user_info.permissions)}"
    )
    return result
