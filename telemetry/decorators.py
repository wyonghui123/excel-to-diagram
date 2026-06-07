"""
telemetry/decorators.py - M14 v1.0.0 @trace 装饰器

提供：
- @trace: 自动 trace 函数执行
- @trace_class: 自动 trace 类所有方法
- trace_function: 上下文管理器版本

用法：
    from telemetry.decorators import trace

    @trace('my_function')
    def my_function(x, y):
        return x + y
"""
import functools
import logging
import time
from typing import Optional, Callable

from .tracing import TraceContext, Span

logger = logging.getLogger(__name__)


def trace(name: Optional[str] = None, attributes: Optional[dict] = None):
    """装饰器：自动 trace 函数执行

    Args:
        name: span 名称（默认用函数名）
        attributes: 静态属性

    Returns:
        decorator

    Example:
        @trace('my_function')
        def my_function(x, y):
            return x + y
    """
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 如果当前没有 trace context，自动启动
            ctx = TraceContext.current()
            own_ctx = False
            if ctx is None:
                ctx = TraceContext.start(span_name)
                own_ctx = True

            span = Span.start(span_name, attributes=attributes)
            try:
                result = func(*args, **kwargs)
                span.end(status='ok')
                return result
            except Exception as e:
                span.end(status='error', error=str(e))
                raise
            finally:
                if own_ctx:
                    from .storage import get_storage
                    get_storage().record(ctx)
                    TraceContext._local.set(None)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            ctx = TraceContext.current()
            own_ctx = False
            if ctx is None:
                ctx = TraceContext.start(span_name)
                own_ctx = True

            span = Span.start(span_name, attributes=attributes)
            try:
                result = await func(*args, **kwargs)
                span.end(status='ok')
                return result
            except Exception as e:
                span.end(status='error', error=str(e))
                raise
            finally:
                if own_ctx:
                    from .storage import get_storage
                    get_storage().record(ctx)
                    TraceContext._local.set(None)

        # 根据函数类型返回对应 wrapper
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def trace_method(method: Callable) -> Callable:
    """装饰器：trace 方法（无参数版本，自动用方法名）"""
    return trace(name=method.__name__)(method)


def trace_interceptor(name: Optional[str] = None):
    """装饰器：专门用于拦截器的 trace 装饰器

    自动附加 entity / action attributes
    """
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(self, context, *args, **kwargs):
            ctx = TraceContext.current()
            own_ctx = False
            if ctx is None:
                ctx = TraceContext.start(span_name)
                own_ctx = True

            # 自动从 context 提取 entity / action
            attrs = {
                'interceptor': type(self).__name__,
                'entity': getattr(context, 'object_type', None) or getattr(context, 'entity_name', 'unknown'),
            }
            if hasattr(context, 'action'):
                attrs['action'] = context.action

            span = Span.start(span_name, attributes=attrs)
            try:
                result = func(self, context, *args, **kwargs)
                span.end(status='ok')
                return result
            except Exception as e:
                span.end(status='error', error=str(e))
                raise
            finally:
                if own_ctx:
                    from .storage import get_storage
                    get_storage().record(ctx)
                    TraceContext._local.set(None)

        return wrapper
    return decorator
