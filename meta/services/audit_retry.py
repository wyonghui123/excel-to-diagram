# -*- coding: utf-8 -*-
"""
BO 业务 Action: audit.retry
============================

管理员重试失败的审计日志记录。
直接调用 audit_service.retry_failed_record()。
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def audit_retry_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    audit.retry Action 处理器

    Args:
        params: { 'record_id': int }
    """
    record_id = params.get('record_id')
    if not record_id:
        return {'success': False, 'data': None, 'message': 'record_id 必填'}

    # 引入 audit_service 单例
    try:
        from meta.services.audit_service import AuditService
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)
        if not ds:
            return {'success': False, 'data': None, 'message': '数据源未初始化'}
        audit_service = AuditService(ds)
    except Exception as e:
        logger.exception(f"[audit.retry] init service failed: {e}")
        return {'success': False, 'data': None, 'message': f'服务初始化失败: {e}'}

    result = audit_service.retry_failed_record(record_id)

    if not result.get('success'):
        return {
            'success': False,
            'data': None,
            'message': result.get('message', '重试失败')
        }

    return {
        'success': True,
        'data': {
            'record_id': record_id,
            'new_status': 'written',
        },
        'message': result.get('message', '重试成功')
    }
