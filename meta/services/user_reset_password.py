# -*- coding: utf-8 -*-
"""
BO 业务 Action: user.reset_password
=====================================

管理员重置指定用户密码 (admin 限定, 强制 must_change_password=1)。
业务逻辑与 user_api.py:446-491 (reset_password) 完全一致。
"""
import logging
from typing import Any, Dict

from flask import g

logger = logging.getLogger(__name__)


def user_reset_password_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    user.reset_password Action 处理器

    Args:
        params: {
            'user_id': int,
            'new_password': str (min 6 chars),
        }
        context: { user_id, user_name, ip_address, permissions }
    """
    from meta.services.auth_middleware import get_current_user

    user_id = params.get('user_id')
    new_password = params.get('new_password', '')

    # 校验
    if not user_id:
        return {'success': False, 'data': None, 'message': 'user_id 必填'}
    if not new_password or len(new_password) < 6:
        return {'success': False, 'data': None, 'message': '新密码长度不能少于6位'}

    # 引入 db
    from meta.core.datasource import get_data_source
    import os
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )
    ds = get_data_source("sqlite", database=db_path)
    if not ds:
        return {'success': False, 'data': None, 'message': '数据源未初始化'}

    # 查用户存在
    cursor = ds.execute("SELECT username FROM users WHERE id = ?", [user_id])
    row = cursor.fetchone()
    if not row:
        return {'success': False, 'data': None, 'message': '用户不存在'}

    # 哈希密码 (复用 user_api 的 pbkdf2 实现)
    from meta.api.user_api import _hash_password_pbdkdf2
    password_hash = _hash_password_pbdkdf2(new_password)

    # 写库 (事务)
    try:
        with ds.transaction():
            ds.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                [password_hash, user_id]
            )

        # 写审计 (audit_logs schema: extra_data 不是 new_data)
        operator_id = context.get('user_id')
        operator_name = context.get('user_name') or 'unknown'
        ip_addr = context.get('ip_address', '')
        ds.execute(
            """INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name,
               field_name, extra_data, ip_address, created_at, log_category, log_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'security', 'INFO')""",
            ['user', user_id, 'RESET_PASSWORD', operator_id, operator_name,
             'password_hash', f'reset by {operator_name}', ip_addr]
        )

        return {
            'success': True,
            'data': {
                'user_id': user_id,
                'must_change_password': True,
            },
            'message': '密码重置成功，用户下次登录需修改密码'
        }
    except Exception as e:
        logger.exception(f"[user.reset_password] failed: {e}")
        return {'success': False, 'data': None, 'message': f'重置失败: {e}'}
