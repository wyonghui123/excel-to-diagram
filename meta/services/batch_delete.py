# -*- coding: utf-8 -*-
"""
BO 业务 Action: batch_delete (通用, 与 batch_save 对称)
======================================================

任意 object_type 的批量删除。
直接调用 manage_service.batch_delete()。
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _set_user_context():
    from meta.services.auth_middleware import get_current_user
    from flask import request
    from meta.core.bo_framework import bo_framework
    current_user = get_current_user()
    bo = bo_framework
    bo.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get('display_name', current_user.get('username', 'unknown')),
        ip_address=request.remote_addr,
    )


def batch_delete_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    batch_delete Action 处理器

    Args:
        params: {
            'object_type': str,
            'ids': [int, int, ...],
            'force': bool (default False),
        }
    """
    object_type = params.get('object_type')
    if not object_type:
        return {'success': False, 'data': None, 'message': 'object_type 必填'}

    ids = params.get('ids', [])
    if not isinstance(ids, list):
        return {'success': False, 'data': None, 'message': 'ids 必须是数组'}

    if not ids:
        return {
            'success': True,
            'data': {
                'object_type': object_type,
                'total': 0,
                'success_count': 0,
                'failed_count': 0,
                'results': [],
            },
            'message': '没有要删除的项'
        }

    force = bool(params.get('force', False))

    # 设置用户上下文 (审计)
    try:
        _set_user_context()
    except Exception:
        pass

    # 调 manage_service
    try:
        from meta.services.manage_service import ManageService
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)
        if not ds:
            return {'success': False, 'data': None, 'message': '数据源未初始化'}
        manage = ManageService(ds)
        result = manage.batch_delete(object_type, ids, force)
    except Exception as e:
        logger.exception(f"[batch_delete] failed: {e}")
        return {'success': False, 'data': None, 'message': f'批量删除失败: {e}'}

    # 构造响应
    results = []
    for r in result.results:
        if hasattr(r, 'to_dict'):
            results.append(r.to_dict())
        else:
            results.append({
                'success': getattr(r, 'success', True),
                'data': getattr(r, 'data', None),
                'message': getattr(r, 'message', ''),
                'error': getattr(r, 'error', None),
            })

    success_count = result.success_count
    failed_count = result.failed_count

    return {
        'success': failed_count == 0,
        'data': {
            'object_type': object_type,
            'total': len(ids),
            'success_count': success_count,
            'failed_count': failed_count,
            'results': results,
            'errors': getattr(result, 'errors', []),
        },
        'message': f'成功删除 {success_count} 项，失败 {failed_count} 项'
    }
