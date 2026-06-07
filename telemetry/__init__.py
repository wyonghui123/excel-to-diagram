"""
telemetry - M14 v3 引擎：OpenTelemetry 简化版

基于实际代码（20 个 .py 拦截器 + Interceptor ABC）：
- 内存 ring buffer（最近 1000 trace）
- 0 依赖 OTLP / Jaeger（仅 Python 标准库）
- 4 Dashboard API 端点
- @trace 装饰器 + trace_class 方法
- wrap_interceptor 包装现有 18 拦截器

公开 API：
- TraceContext / Span / @trace / @trace_class
- TraceStorage / get_storage()
- install_global_tracer(interceptors)
- /api/v1/telemetry/{stats, traces, traces/slow, traces/<id>, configure}

回滚：删除 telemetry/ 目录即可（不修改任何业务代码）
"""
import logging
from .tracing import (
    TraceContext,
    Span,
    trace,
    span,
)
from .storage import (
    TraceStorage,
    get_storage,
    reset_storage,
)
from .decorators import (
    trace_method,
    trace_interceptor,
)
from .integration import (
    wrap_interceptor_before,
    wrap_interceptor_after,
    install_global_tracer,
)
from .api import telemetry_bp

logger = logging.getLogger(__name__)

__all__ = [
    # tracing
    'TraceContext',
    'Span',
    'trace',
    'span',
    # storage
    'TraceStorage',
    'get_storage',
    'reset_storage',
    # decorators
    'trace_method',
    'trace_interceptor',
    # integration
    'wrap_interceptor_before',
    'wrap_interceptor_after',
    'install_global_tracer',
    # api
    'telemetry_bp',
]

__version__ = '1.0.0'
