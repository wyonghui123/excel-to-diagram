# -*- coding: utf-8 -*-
"""
请求链路追踪服务

为每个请求生成唯一的 traceId，支持：
- 请求入口自动生成 traceId
- 从 X-Request-Id / X-Trace-Id header 继承（跨服务调用）
- 在日志和响应中自动携带
"""

import uuid
import logging
from flask import request, g

TRACE_ID_HEADER = 'X-Request-Id'


def get_trace_id() -> str:
    try:
        return getattr(g, 'trace_id', None)
    except RuntimeError:
        return None


def get_or_create_trace_id() -> str:
    trace_id = request.headers.get(TRACE_ID_HEADER) or request.headers.get('X-Trace-Id')
    if trace_id:
        return trace_id
    return str(uuid.uuid4())


class TraceIdLogFilter(logging.Filter):
    def filter(self, record):
        trace_id = get_trace_id()
        if trace_id:
            record.trace_id = trace_id
        else:
            record.trace_id = '-'
        return True


def setup_trace_log_filter():
    trace_filter = TraceIdLogFilter()
    for handler in logging.root.handlers:
        if trace_filter not in handler.filters:
            handler.addFilter(trace_filter)
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger) and not logger.propagate:
            if trace_filter not in logger.filters:
                logger.addFilter(trace_filter)