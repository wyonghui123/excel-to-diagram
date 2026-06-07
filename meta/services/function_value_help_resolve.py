# -*- coding: utf-8 -*-
"""
Function (v3.4): function.value_help.resolve
=============================================

SAP CAP function / Palantir Function 模式 —— 读操作 / 查询。
"""
import logging
from typing import Any, Dict

from flask import g

logger = logging.getLogger(__name__)


def function_value_help_resolve_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    function.value_help.resolve Function 处理器 (v3.4 Function 维度)

    Args:
        params: {
            'source_type': 'enum' | 'bo' | 'custom',
            'source_id': str,
            'value': 任意,
            'value_field': str (default 'id'),
            'display_field': str (default 'name'),
            'code_field': str (default 'code'),
        }
    """
    source_type = params.get('source_type')
    source_id = params.get('source_id')
    value = params.get('value')

    if not source_type or not source_id or value is None:
        return {'success': False, 'data': None, 'message': 'source_type/source_id/value 必填'}

    user_info = g.current_user if hasattr(g, 'current_user') else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}

    from meta.core.models import ValueHelpSource
    source = ValueHelpSource(type=source_type)
    if source_type == "enum":
        source.enum_type_id = source_id
        source.apply_target_permissions = False
    elif source_type == "bo":
        source.target_bo = source_id
        source.value_field = params.get('value_field', 'id')
        source.display_field = params.get('display_field', 'name')
        source.code_field = params.get('code_field', 'code')
    elif source_type == "custom":
        source.endpoint = source_id
    else:
        return {'success': False, 'data': None, 'message': f'Unknown source type: {source_type}'}

    try:
        from meta.core.value_help_providers import get_provider
        provider = get_provider(source)
    except ValueError as e:
        return {'success': False, 'data': None, 'message': str(e)}

    user_context = {
        'user_id': user_info.get('user_id'),
        'roles': user_info.get('roles', []),
        'is_admin': 'admin' in user_info.get('roles', []),
    }

    try:
        result = provider.resolve(value, user_context)
        if result is None:
            result = {'value': value, 'display': str(value), 'code': str(value)}
        return {'success': True, 'data': result, 'message': '解析成功'}
    except Exception as e:
        logger.exception(f"[function.value_help.resolve] failed: {e}")
        return {'success': False, 'data': None, 'message': f'解析失败: {e}'}
