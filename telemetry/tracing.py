"""
telemetry/tracing.py - M14 v1.0.0 Trace 上下文 + Span 管理

简化版 OpenTelemetry：
- TraceContext: 全局 trace ID（contextvars，线程/异步安全）
- Span: 单个操作段（含 name / start / end / duration / status）
- 0 依赖 OTLP / Jaeger（仅内存存储）

用法：
    from telemetry.tracing import TraceContext, Span

    # 启动 trace
    ctx = TraceContext.start('handle_request')
    span = Span.start('validate')
    # ... 业务逻辑 ...
    span.end(status='ok')
    ctx.end()
"""
import logging
import time
import uuid
import contextvars
import threading
from contextlib import contextmanager
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


# ==================== TraceContext ====================

class TraceContext:
    """Trace 上下文（线程/异步安全）

    字段：
    - trace_id: 32 字符 hex（UUID4）
    - root_span_name: 根 span 名称
    - started_at: 启动时间
    - spans: 当前 trace 下的 span 列表
    """

    _local = contextvars.ContextVar('trace_context', default=None)

    def __init__(self, trace_id: str = None, root_span_name: str = 'root'):
        self.trace_id = trace_id or uuid.uuid4().hex
        self.root_span_name = root_span_name
        self.started_at = time.time()
        self.spans: List['Span'] = []
        self.metadata: Dict[str, Any] = {}

    @classmethod
    def start(cls, name: str = 'root') -> 'TraceContext':
        """启动新 trace"""
        ctx = cls(root_span_name=name)
        cls._local.set(ctx)
        return ctx

    @classmethod
    def current(cls) -> Optional['TraceContext']:
        """获取当前线程/上下文的 TraceContext"""
        return cls._local.get()

    def end(self) -> Dict:
        """结束 trace，返回 trace summary"""
        return {
            'trace_id': self.trace_id,
            'root_span_name': self.root_span_name,
            'duration_ms': (time.time() - self.started_at) * 1000,
            'span_count': len(self.spans),
            'spans': [s.to_dict() for s in self.spans],
        }

    def add_span(self, span: 'Span') -> None:
        """添加 span 到 trace"""
        self.spans.append(span)

    def to_dict(self) -> Dict:
        return self.end()


# ==================== Span ====================

class Span:
    """单个操作段

    字段：
    - name: 名称（如 'PermissionInterceptor.before_action'）
    - trace_id: 所属 trace
    - started_at / ended_at / duration_ms
    - status: ok / error
    - attributes: 自定义标签
    - error: 异常信息（status=error 时）
    """

    def __init__(self, name: str, trace_id: str = None, attributes: Optional[Dict] = None):
        self.name = name
        self.trace_id = trace_id or (TraceContext.current().trace_id if TraceContext.current() else uuid.uuid4().hex)
        self.started_at = time.time()
        self.ended_at: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.status = 'ok'
        self.attributes: Dict[str, Any] = attributes or {}
        self.error: Optional[str] = None

    @classmethod
    def start(cls, name: str, attributes: Optional[Dict] = None) -> 'Span':
        """启动 span（自动附加到当前 TraceContext）"""
        span = cls(name=name, attributes=attributes)
        ctx = TraceContext.current()
        if ctx:
            ctx.add_span(span)
        return span

    def end(self, status: str = 'ok', error: Optional[str] = None, **attributes) -> None:
        """结束 span"""
        self.ended_at = time.time()
        self.duration_ms = (self.ended_at - self.started_at) * 1000
        self.status = status
        if error:
            self.error = error
        self.attributes.update(attributes)

    def set_attribute(self, key: str, value: Any) -> None:
        """设置 attribute"""
        self.attributes[key] = value

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'trace_id': self.trace_id,
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'duration_ms': self.duration_ms,
            'status': self.status,
            'attributes': self.attributes,
            'error': self.error,
        }


# ==================== 便捷 API ====================

@contextmanager
def trace(name: str = 'root', attributes: Optional[Dict] = None):
    """上下文管理器：自动启动/结束 TraceContext

    用法：
        with trace('handle_request') as ctx:
            span = Span.start('validate')
            # ...
            span.end()
        # ctx 自动 end()
    """
    ctx = TraceContext.start(name)
    if attributes:
        ctx.metadata.update(attributes)
    try:
        yield ctx
    except Exception as e:
        ctx.metadata['error'] = str(e)
        raise
    finally:
        # 记录到 storage
        from .storage import get_storage
        get_storage().record(ctx)
        # 重置 context
        TraceContext._local.set(None)


@contextmanager
def span(name: str, attributes: Optional[Dict] = None):
    """上下文管理器：自动启动/结束 Span

    用法：
        with span('PermissionInterceptor') as s:
            # 业务逻辑
            pass
    """
    s = Span.start(name, attributes)
    try:
        yield s
    except Exception as e:
        s.end(status='error', error=str(e))
        raise
    else:
        s.end()
