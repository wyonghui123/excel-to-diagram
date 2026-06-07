# -*- coding: utf-8 -*-
"""
核心异常定义

定义数据源和事务相关的异常类型。
"""


class ConcurrentModificationError(Exception):
    """并发修改异常 — 乐观锁版本不匹配"""
    pass


class FieldPolicyViolationError(Exception):
    """字段策略违反异常 — FieldPolicy 校验失败"""
    pass


class ValidationFailedError(Exception):
    """校验失败异常 — 元数据驱动校验或约束校验失败"""

    def __init__(self, message: str = "", details: list = None):
        super().__init__(message)
        self.details = details or []
