# -*- coding: utf-8 -*-
"""
核心异常定义

定义数据源和事务相关的异常类型。
"""


class ConcurrentModificationError(Exception):
    """并发修改异常 — 乐观锁版本不匹配"""
    pass


class FieldPolicyViolationError(Exception):
    """字段策略违反异常 — FieldPolicy 校验失败

    [R-MM-03 R12] 状态矩阵导致的写入拒绝使用 `field_not_writable_in_state`，
    与普通 `FIELD_NOT_EDITABLE` 区分，便于前端定位「已过账不可改」而非权限不足。
    """

    code = 'FIELD_NOT_EDITABLE'
    status_code = 400

    def __init__(self, message: str = "", code: str = None):
        super().__init__(message)
        if code:
            self.code = code


class ValidationFailedError(Exception):
    """校验失败异常 — 元数据驱动校验或约束校验失败"""

    def __init__(self, message: str = "", details: list = None):
        super().__init__(message)
        self.details = details or []


class StateMachineViolationError(Exception):
    """状态机违规 — 目标状态在当前状态没有声明过的迁移边。"""

    code = 'STATE_MACHINE_VIOLATION'

    def __init__(self, message: str = "", details: list = None):
        super().__init__(message)
        self.details = details or []
