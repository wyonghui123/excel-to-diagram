# -*- coding: utf-8 -*-
"""
Function (v3.4): function.subscription.list
===========================================

SAP CAP function / Palantir Function 模式 —— 读操作 / 查询。
"""
import json
import logging
import os
from typing import Any, Dict

from flask import g

logger = logging.getLogger(__name__)


def function_subscription_list_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    function.subscription.list Function 处理器
    """
    user_info = g.current_user if hasattr(g, 'current_user') else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}
    user_id = user_info.get('user_id')

    object_type = params.get('object_type')

    try:
        from meta.core.datasource import get_data_source
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)

        rows = ds.execute(
            """SELECT id, user_id, object_type, event_types, channel, webhook_url,
                      webhook_secret, filter_condition, enabled, created_at
               FROM change_subscriptions
               WHERE user_id = ? AND (? IS NULL OR object_type = ?)
               ORDER BY created_at DESC""",
            [user_id, object_type, object_type]
        ).fetchall()

        subscriptions = []
        for r in rows:
            sub = dict(r) if hasattr(r, 'keys') else {
                'id': r[0], 'user_id': r[1], 'object_type': r[2],
                'event_types': json.loads(r[3]) if r[3] else [],
                'channel': r[4], 'webhook_url': r[5], 'webhook_secret': r[6],
                'filter_condition': json.loads(r[7]) if r[7] else {},
                'enabled': r[8], 'created_at': r[9],
            }
            subscriptions.append(sub)

        return {
            'success': True,
            'data': subscriptions,
            'message': f'找到 {len(subscriptions)} 个订阅',
        }
    except Exception as e:
        logger.exception(f"[function.subscription.list] failed: {e}")
        return {'success': False, 'data': None, 'message': f'查询失败: {e}'}
