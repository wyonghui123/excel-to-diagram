# -*- coding: utf-8 -*-
"""
BO 业务 Action: user.logout
============================

用户登出业务 Action。从现有 auth_api.py:logout 迁移。
- 提取 token（Cookie 或 Bearer）
- 加入 token_blacklist
"""
import logging
from typing import Any, Dict
from datetime import datetime

from meta.services.token_service import TokenService
from meta.services.token_blacklist_service import token_blacklist_service

logger = logging.getLogger(__name__)


def _extract_token_from_context(context: Dict[str, Any]) -> str:
    """从请求 context 提取 token (Cookie 或 Bearer)"""
    # 优先从 g 拿 (login_required 装饰器已 set)
    from flask import g, request
    # 兜底: 直接从 request 拿
    token = request.cookies.get('auth_token') if request else None
    if token:
        return token
    auth_header = request.headers.get('Authorization', '') if request else ''
    if auth_header.lower().startswith('bearer '):
        return auth_header[7:].strip()
    return ''


def user_logout_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    user.logout Action 处理器

    Returns:
        {'success': True, 'data': None, 'message': '登出成功'}
    """
    token = _extract_token_from_context(context)
    if token:
        try:
            payload = TokenService.extract_payload_without_verification(token)
            if payload and 'exp' in payload:
                expires_at = datetime.utcfromtimestamp(payload['exp'])
                token_blacklist_service.add_to_blacklist(token, expires_at)
        except Exception as e:
            logger.warning(f"[user.logout] blacklist failed: {e}")
    return {
        'success': True,
        'data': None,
        'message': '登出成功',
    }
