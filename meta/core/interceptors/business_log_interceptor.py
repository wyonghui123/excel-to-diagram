# -*- coding: utf-8 -*-
"""
业务日志拦截器

在 CRUD 操作后自动记录业务操作日志。
使用 StructuredLogger.log_business() 写入结构化业务日志。

优先级：95（在 AuditInterceptor 之后执行，避免重复记录 CRUD 审计）
"""

import logging
from typing import Dict, Any, Optional

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext
from meta.services.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)


class BusinessLogInterceptor(Interceptor):
    """
    业务日志拦截器
    
    在 CRUD 操作后记录结构化业务日志，包含：
    - 操作类型 (CREATE/UPDATE/DELETE)
    - 对象类型和 ID
    - 操作人信息
    - 变更前后的数据差异
    
    注意：此拦截器与 AuditInterceptor 互补：
    - AuditInterceptor：记录关联操作（associate/dissociate）的审计日志
    - BusinessLogInterceptor：记录所有 CRUD 操作的业务日志（通过 StructuredLogger）
    """

    ACTION_MAP = {
        'crud_create': 'CREATE',
        'crud_update': 'UPDATE',
        'crud_delete': 'DELETE',
    }

    @property
    def priority(self) -> int:
        return 95

    def __init__(self, structured_logger: StructuredLogger = None):
        self._structured_logger = structured_logger or StructuredLogger()

    def before_action(self, context: ActionContext) -> None:
        pass

    def after_action(self, context: ActionContext) -> None:
        """CRUD 操作后记录业务日志"""
        action_name = self.ACTION_MAP.get(context.action)
        if not action_name:
            return

        if not context.result or not context.result.success:
            return

        object_id = context.object_id
        if object_id is None and context.result.data:
            object_id = context.result.data.get('id')

        self._structured_logger.log_business(
            action=action_name,
            object_type=context.object_type,
            object_id=object_id,
            user_id=context.user_id,
            user_name=context.user_name,
            old_data=context.old_data,
            new_data=context.new_data or (context.result.data if context.result else None),
            ip_address=context.ip_address,
            trace_id=context.trace_id,
            transaction_id=context.transaction_id,
        )
