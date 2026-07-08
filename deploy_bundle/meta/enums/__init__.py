# -*- coding: utf-8 -*-
"""
系统枚举模块

提供系统级别的枚举定义，包括：
- LogCategory: 日志类型枚举
- LogLevel: 日志级别枚举

这些枚举用于统一日志系统的分类和级别定义。
"""

from .log_category import LogCategory
from .log_level import LogLevel

__all__ = [
    'LogCategory',
    'LogLevel',
]
