# -*- coding: utf-8 -*-
"""
上下文拦截器

设置用户上下文信息（用户ID、用户名、IP地址、追踪ID等）。
"""

import logging
from flask import g, request

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


class ContextInterceptor(Interceptor):
    """
    上下文拦截器
    
    设置用户上下文信息，包括：
    - 用户ID
    - 用户名
    - IP地址
    - 追踪ID
    
    优先级：10（最先执行）
    """
    
    @property
    def priority(self) -> int:
        return 10
    
    def before_action(self, context: ActionContext) -> None:
        """动作执行前：设置用户上下文"""
        try:
            if not context.user_id:
                context.user_id = getattr(g, 'user_id', None)
            if not context.user_name:
                context.user_name = getattr(g, 'username', None)
            if not context.ip_address:
                context.ip_address = request.remote_addr if request else None
        except Exception:
            pass
    
    def after_action(self, context: ActionContext) -> None:
        """动作执行后：不需要处理"""
        pass
