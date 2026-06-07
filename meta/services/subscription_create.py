# -*- coding: utf-8 -*-
"""
BO 业务 Action: subscription.create
====================================

创建对象变更通知订阅 (websocket/webhook)。
业务逻辑与 notification_api.py:190-235 (create_subscription) 一致。
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict

from flask import g

logger = logging.getLogger(__name__)


def subscription_create_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    subscription.create Action 处理器

    Args:
        params: {
            'object_type': str (required),
            'event_types': [str] (default ['created','updated','deleted']),
            'channel': 'websocket' | 'webhook' (default 'websocket'),
            'webhook_url': str (webhook 必填),
            'webhook_secret': str (optional),
            'filter_condition': dict (optional),
        }
    """
    # 鉴权: 必须登录
    user_info = g.current_user if hasattr(g, 'current_user') and g.current_user else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}
    user_id = user_info.get('user_id')
    if not user_id:
        return {'success': False, 'data': None, 'message': '用户信息无效'}

    # 校验
    object_type = params.get('object_type')
    if not object_type:
        return {'success': False, 'data': None, 'message': 'object_type 必填'}

    channel = params.get('channel', 'websocket')
    if channel not in ('websocket', 'webhook'):
        return {'success': False, 'data': None, 'message': "channel 必须是 'websocket' 或 'webhook'"}

    if channel == 'webhook' and not params.get('webhook_url'):
        return {'success': False, 'data': None, 'message': 'webhook 模式必须提供 webhook_url'}

    event_types = params.get('event_types', ['created', 'updated', 'deleted'])
    if not isinstance(event_types, list):
        return {'success': False, 'data': None, 'message': 'event_types 必须是数组'}

    filter_condition = params.get('filter_condition', {})

    # 构造订阅
    subscription = {
        'user_id': user_id,
        'object_type': object_type,
        'event_types': json.dumps(event_types) if isinstance(event_types, list) else event_types,
        'channel': channel,
        'webhook_url': params.get('webhook_url', ''),
        'webhook_secret': params.get('webhook_secret', ''),
        'filter_condition': json.dumps(filter_condition) if filter_condition else '{}',
        'enabled': 1,
        'created_at': datetime.now().isoformat(),
    }

    # 写库
    try:
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)
        if not ds:
            return {'success': False, 'data': None, 'message': '数据源未初始化'}
        sub_id = ds.insert('change_subscriptions', subscription)
    except Exception as e:
        logger.exception(f"[subscription.create] insert failed: {e}")
        return {'success': False, 'data': None, 'message': f'创建订阅失败: {e}'}

    subscription['id'] = sub_id

    return {
        'success': True,
        'data': {
            'subscription_id': sub_id,
            'object_type': object_type,
            'channel': channel,
        },
        'message': '订阅创建成功'
    }
