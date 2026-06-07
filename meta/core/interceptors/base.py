# -*- coding: utf-8 -*-
"""
拦截器基类

定义拦截器的抽象接口，所有拦截器都必须继承此类。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext


class Interceptor(ABC):
    """
    拦截器抽象基类
    
    拦截器用于在 BO 操作前后插入横切逻辑，如：
    - 权限检查
    - 数据验证
    - 审计日志
    - 事务控制
    - 锁机制
    
    使用方式：
        class MyInterceptor(Interceptor):
            def before_action(self, context):
                # 前置逻辑
                
            def after_action(self, context):
                # 后置逻辑
    """
    
    @property
    def name(self) -> str:
        """拦截器名称"""
        return self.__class__.__name__
    
    @property
    def priority(self) -> int:
        """
        拦截器优先级
        
        数值越小优先级越高，越先执行。
        默认优先级为 100。
        
        建议优先级：
        - ContextInterceptor: 10
        - LockInterceptor: 20
        - PermissionInterceptor: 30
        - ValidationInterceptor: 40
        - DeterminationInterceptor: 50
        - BusinessRuleInterceptor: 60
        - PersistenceInterceptor: 70
        - AuditInterceptor: 80
        - WorkflowInterceptor: 90
        - EventInterceptor: 100
        """
        return 100
    
    @abstractmethod
    def before_action(self, context: 'ActionContext') -> None:
        """
        动作执行前调用
        
        Args:
            context: 执行上下文，包含元模型、动作、参数等信息
            
        Raises:
            Exception: 如果前置检查失败，可以抛出异常阻止后续执行
        """
        pass
    
    @abstractmethod
    def after_action(self, context: 'ActionContext') -> None:
        """
        动作执行后调用
        
        Args:
            context: 执行上下文，包含执行结果等信息
        """
        pass
    
    def on_error(self, context: 'ActionContext', error: Exception) -> None:
        """
        动作执行出错时调用
        
        默认实现为空，子类可以覆盖以实现错误处理逻辑。
        
        Args:
            context: 执行上下文
            error: 发生的异常
        """
        pass
    
    def should_execute(self, context: 'ActionContext') -> bool:
        """
        判断拦截器是否应该执行
        
        默认始终执行，子类可以覆盖以实现条件执行逻辑。
        
        Args:
            context: 执行上下文
            
        Returns:
            bool: True 表示执行，False 表示跳过
        """
        return True
