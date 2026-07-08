# -*- coding: utf-8 -*-
"""
枚举元数据适配器模块

提供双通道访问模式：
- IEnumProvider: 高速读取通道（缓存优先，无权限检查）
- IEnumAdmin: 安全写入通道（审计+权限+缓存失效）

设计原则：
- 接口隔离：读写分离，职责清晰
- 性能优化：专用缓存层，P99 < 5ms
- 向后兼容：可渐进式迁移现有代码
"""

from .dto import EnumTypeDTO, EnumValueDTO, EnumSelectOption
from .interfaces import IEnumProvider, IEnumAdmin

__all__ = [
    'EnumTypeDTO',
    'EnumValueDTO', 
    'EnumSelectOption',
    'IEnumProvider',
    'IEnumAdmin',
]
