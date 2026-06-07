"""
telemetry/integration.py - M14 v1.0.0 拦截器集成 hook

提供：
- InterceptorTracer: 给 18 拦截器添加 trace 能力的工具
- wrap_interceptor: 包装现有拦截器，自动添加 span
- install_global_tracer: 一键启用所有拦截器 trace

回滚：注释掉 wrap_interceptor 调用即可
"""
import logging
import time
from typing import Optional

from .tracing import TraceContext, Span

logger = logging.getLogger(__name__)


def wrap_interceptor_before(interceptor_instance, before_action_func):
    """包装拦截器 before_action，自动添加 span

    Args:
        interceptor_instance: 拦截器实例
        before_action_func: 原始 before_action 函数

    Returns:
        包装后的函数（自动 span + duration 记录）
    """
    interceptor_name = type(interceptor_instance).__name__

    def wrapper(context):
        span = Span.start(
            f'{interceptor_name}.before_action',
            attributes={
                'interceptor': interceptor_name,
                'priority': getattr(interceptor_instance, 'priority', 100),
            },
        )
        try:
            result = before_action_func(context)
            span.end(status='ok')
            return result
        except Exception as e:
            span.end(status='error', error=str(e))
            raise

    return wrapper


def wrap_interceptor_after(interceptor_instance, after_action_func):
    """包装拦截器 after_action，自动添加 span"""
    interceptor_name = type(interceptor_instance).__name__

    def wrapper(context):
        span = Span.start(
            f'{interceptor_name}.after_action',
            attributes={
                'interceptor': interceptor_name,
                'priority': getattr(interceptor_instance, 'priority', 100),
            },
        )
        try:
            result = after_action_func(context)
            span.end(status='ok')
            return result
        except Exception as e:
            span.end(status='error', error=str(e))
            raise

    return wrapper


def install_global_tracer(registry_or_interceptors, auto_record: bool = True):
    """给所有拦截器安装 trace

    Args:
        registry_or_interceptors: 拦截器注册表 / 列表
        auto_record: 是否自动记录到 storage

    用法：
        from meta.core.interceptors import ALL_INTERCEPTORS
        install_global_tracer(ALL_INTERCEPTORS)
    """
    from .storage import get_storage

    if hasattr(registry_or_interceptors, '__iter__'):
        interceptors = list(registry_or_interceptors)
    else:
        interceptors = [registry_or_interceptors]

    wrapped_count = 0
    for interceptor in interceptors:
        if not hasattr(interceptor, 'before_action') or not hasattr(interceptor, 'after_action'):
            continue

        # 包装 before_action
        original_before = interceptor.before_action
        interceptor.before_action = wrap_interceptor_before(interceptor, original_before)

        # 包装 after_action
        original_after = interceptor.after_action
        interceptor.after_action = wrap_interceptor_after(interceptor, original_after)

        wrapped_count += 1
        logger.info(f'[Telemetry] Wrapped {type(interceptor).__name__}')

    logger.info(f'[Telemetry] Global tracer installed: {wrapped_count} interceptors wrapped')
    return wrapped_count
