# -*- coding: utf-8 -*-
"""
[MODULE] trace_id 全局管理 (v3.18 M.1)
[DESCRIPTION] 每个请求一个 trace_id (UUID 32 char), 跨 subflow/audit/SSE 关联

使用:
  from meta.core.trace_id import TraceId

  TraceId.set('abc123...')  # 入口生成
  tid = TraceId.get()       # 各处取
"""
import uuid
import threading
from typing import Optional

# 线程局部 (跟 Flask g 类似)
_local = threading.local()


class TraceId:
    """[DECORATIVE] v3.18 M.1: trace_id 全局管理"""

    @staticmethod
    def generate() -> str:
        """生成 32 字符 UUID trace_id"""
        return uuid.uuid4().hex[:32]

    @staticmethod
    def get() -> Optional[str]:
        """当前请求的 trace_id"""
        return getattr(_local, 'trace_id', None)

    @staticmethod
    def set(trace_id: str) -> None:
        _local.trace_id = trace_id

    @staticmethod
    def clear() -> None:
        """请求结束清空"""
        if hasattr(_local, 'trace_id'):
            delattr(_local, 'trace_id')

    @staticmethod
    def get_or_generate() -> str:
        """取或生成"""
        tid = TraceId.get()
        if not tid:
            tid = TraceId.generate()
            TraceId.set(tid)
        return tid
