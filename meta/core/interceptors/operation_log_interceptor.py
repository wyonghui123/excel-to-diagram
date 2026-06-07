# -*- coding: utf-8 -*-
"""
运维操作日志拦截器

在管理员操作时自动记录运维日志。
使用 StructuredLogger.log_operation() 写入结构化运维日志。

优先级：97（在 SecurityLogInterceptor 之后执行）
"""

import logging

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext
from meta.services.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)


class OperationLogInterceptor(Interceptor):
    """
    运维操作日志拦截器
    
    记录所有 CRUD 操作的运维日志，用于系统运维和故障排查：
    - 操作类型和对象
    - 操作来源（IP、用户）
    - 执行耗时
    - 错误信息（如果操作失败）
    
    与 BusinessLogInterceptor 的区别：
    - BusinessLogInterceptor：关注业务语义（谁做了什么）
    - OperationLogInterceptor：关注运维视角（操作耗时、系统状态）
    """

    OPERATION_MAP = {
        'crud_create': 'CREATE_OBJECT',
        'crud_update': 'UPDATE_OBJECT',
        'crud_delete': 'DELETE_OBJECT',
        'crud_read': 'READ_OBJECT',
        'associate': 'ASSOCIATE_OBJECT',
        'dissociate': 'DISSOCIATE_OBJECT',
    }

    @property
    def priority(self) -> int:
        return 97

    def __init__(self, structured_logger: StructuredLogger = None):
        self._structured_logger = structured_logger or StructuredLogger()

    def before_action(self, context: ActionContext) -> None:
        pass

    def after_action(self, context: ActionContext) -> None:
        """操作后记录运维日志"""
        operation = self.OPERATION_MAP.get(context.action)
        if not operation:
            return

        level = 'INFO'
        error_msg = None

        if context.result and not context.result.success:
            level = 'ERROR'
            error_msg = context.result.message or 'Operation failed'

        message = f"{operation} {context.object_type}"
        if context.object_id:
            message += f"#{context.object_id}"

        self._structured_logger.log_operation(
            operation=operation,
            level=level,
            message=message,
            source=context.object_type,
            error=error_msg,
            trace_id=context.trace_id,
            object_type=context.object_type,
            object_id=context.object_id,
            user_id=context.user_id,
            user_name=context.user_name,
            ip_address=context.ip_address,
        )
