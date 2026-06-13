"""
trace_id 工具 (Phase 5 v3.18.4+)
=================================

提供 trace_id 端到端追踪:
- 测试创建的每个数据都关联 trace_id
- 跨 subflow/audit/SSE 关联
- 通过 X-Trace-Id header 传递

TBD 依从: test-observability-rules.md M.1
"""
import os
import uuid
import logging
from typing import Optional
from contextvars import ContextVar

logger = logging.getLogger(__name__)


# ============================================================
# ContextVar 存储当前 trace_id (多线程/异步安全)
# ============================================================

_current_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)


def generate_trace_id() -> str:
    """生成新 trace_id (UUID 32 char)"""
    return uuid.uuid4().hex


def get_or_generate_trace_id() -> str:
    """获取当前 trace_id, 无则生成"""
    tid = _current_trace_id.get()
    if not tid:
        tid = generate_trace_id()
        _current_trace_id.set(tid)
    return tid


def set_trace_id(tid: str) -> None:
    """设置当前 trace_id"""
    _current_trace_id.set(tid)


def get_trace_id() -> Optional[str]:
    """获取当前 trace_id"""
    return _current_trace_id.get()


def clear_trace_id() -> None:
    """清除当前 trace_id"""
    _current_trace_id.set(None)


# ============================================================
# 装饰器: 自动注入 trace_id 到测试
# ============================================================

def with_trace_id(func):
    """装饰器: 测试函数自动设置 trace_id"""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tid = generate_trace_id()
        set_trace_id(tid)
        logger.info(f"Test started with trace_id={tid}: {func.__name__}")
        try:
            return func(*args, **kwargs)
        finally:
            logger.info(f"Test ended: trace_id={tid}")
            clear_trace_id()

    return wrapper


# ============================================================
# 与工厂集成
# ============================================================

def add_trace_to_factory_data(data: dict) -> dict:
    """
    给工厂数据加 trace_id 字段
    所有通过 Factory.create() 创建的数据都自动关联
    """
    tid = get_trace_id()
    if tid:
        data['_trace_id'] = tid
        data['_created_by_test'] = True
        data['_created_at_ts'] = __import__('time').time()
    return data
