"""
permission_set factory (P9 Sunset shim)
======================================

历史背景:
  - spec16 阶段 2 将 ``roles`` 统一改名为 ``permission_sets``
  - 但 factories 子模块历史上保留了 ``role.py`` 文件名, 部分测试仍按
    历史命名 ``from meta.tests.factories.permission_set import RoleFactory``
  - 为保持向后兼容 + 让历史测试可被 collect, 此处提供 P9 Sunset shim

正确做法:
  新代码请使用 ``from meta.tests.factories.role import RoleFactory``

本模块仅做名称重导出, 不引入任何额外行为.
"""
from .role import RoleFactory  # noqa: F401

__all__ = ['RoleFactory']