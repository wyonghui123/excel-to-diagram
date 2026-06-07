# -*- coding: utf-8 -*-
"""
Functions (v3.4): function.aggregate.query + function.aggregate.refresh
======================================================================

SAP CAP function / Palantir Function 模式。
"""
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _get_manager():
    """复用 stats_api.py 的 manager 构造模式"""
    from meta.core.aggregate_manager import AggregateManager
    from meta.core.datasource import get_data_source
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )
    ds = get_data_source("sqlite", database=db_path)
    manager = AggregateManager(ds)
    manager.register_all()
    return manager


def function_aggregate_query_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    function.aggregate.query Function 处理器
    """
    aggregate_id = params.get('aggregate_id')
    if not aggregate_id:
        return {'success': False, 'data': None, 'message': 'aggregate_id 必填'}
    filters = params.get('filters')
    order_by = params.get('order_by')
    limit = params.get('limit', 1000)

    try:
        manager = _get_manager()
        results = manager.query(aggregate_id, filters=filters, order_by=order_by, limit=limit)
        return {
            'success': True,
            'data': results,
            'meta': {
                'aggregate_id': aggregate_id,
                'row_count': len(results),
                'freshness': manager.get_freshness(aggregate_id),
            },
            'message': f'查询到 {len(results)} 行',
        }
    except Exception as e:
        logger.exception(f"[function.aggregate.query] failed: {e}")
        return {'success': False, 'data': None, 'message': f'查询失败: {e}'}


def function_aggregate_refresh_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    function.aggregate.refresh Function 处理器 (admin 限定, 实际是写操作)
    """
    aggregate_id = params.get('aggregate_id')
    if not aggregate_id:
        return {'success': False, 'data': None, 'message': 'aggregate_id 必填'}
    force = bool(params.get('force', True))

    try:
        manager = _get_manager()
        row_count = manager.refresh(aggregate_id, force=force)
        return {
            'success': True,
            'data': {
                'aggregate_id': aggregate_id,
                'row_count': row_count,
                'freshness': manager.get_freshness(aggregate_id),
            },
            'message': f'已刷新 {row_count} 行',
        }
    except Exception as e:
        logger.exception(f"[function.aggregate.refresh] failed: {e}")
        return {'success': False, 'data': None, 'message': f'刷新失败: {e}'}
