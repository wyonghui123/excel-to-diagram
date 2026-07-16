# -*- coding: utf-8 -*-
"""
安全日志拦截器

在安全相关对象（用户/角色/权限/用户组）变更时自动记录安全事件日志。
使用 StructuredLogger.log_security() 写入结构化安全日志。

优先级：96（在 BusinessLogInterceptor 之后执行）
"""

import logging
from typing import Set

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext
from meta.core.action_constants import CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE
from meta.services.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)


class SecurityLogInterceptor(Interceptor):
    """
    安全日志拦截器
    
    仅在安全相关对象变更时触发，记录安全事件：
    - 用户创建/删除
    - 角色创建/删除
    - 权限变更
    - 用户组变更
    
    安全事件使用 WARNING/HIGH 级别，确保在审计日志中可追踪。
    """

    SECURITY_OBJECT_TYPES: Set[str] = {'user', 'role', 'permission', 'user_group'}

    EVENT_MAP = {
        CRUD_CREATE: 'ENTITY_CREATED',
        CRUD_UPDATE: 'ENTITY_MODIFIED',
        CRUD_DELETE: 'ENTITY_DELETED',
    }

    SEVERITY_MAP = {
        CRUD_CREATE: 'INFO',
        CRUD_UPDATE: 'INFO',
        CRUD_DELETE: 'WARNING',
    }

    @property
    def priority(self) -> int:
        return 96

    def __init__(self, structured_logger: StructuredLogger = None):
        self._structured_logger = structured_logger or StructuredLogger()

    def before_action(self, context: ActionContext) -> None:
        pass

    def after_action(self, context: ActionContext) -> None:
        """安全相关对象变更后记录安全日志"""
        if context.object_type not in self.SECURITY_OBJECT_TYPES:
            return

        if not context.result or not context.result.success:
            return

        event_type = self.EVENT_MAP.get(context.action)
        if not event_type:
            return

        severity = self.SEVERITY_MAP.get(context.action, 'INFO')

        if context.object_type == 'permission':
            severity = 'WARNING'
        if context.action == CRUD_DELETE and context.object_type in ('user', 'role'):
            severity = 'ERROR'

        object_id = context.object_id
        details = {}
        if context.old_data:
            details['old_data'] = context.old_data
        if context.new_data:
            details['new_data'] = context.new_data

        self._structured_logger.log_security(
            event_type=event_type,
            severity=severity,
            user_id=context.user_id,
            user_name=context.user_name,
            source_ip=context.ip_address,
            target_user_id=object_id,
            details=details,
            trace_id=context.trace_id,
            transaction_id=context.transaction_id,
        )
