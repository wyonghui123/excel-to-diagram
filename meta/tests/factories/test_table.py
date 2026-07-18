"""
TestTableFactory (P1-5d 新建)
==============================

测试表工厂: 用于简单事务测试

yaml: meta/schemas/test_table.yaml
authorization.check = false (开放访问, 仅测试用)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class TestTableFactory(BaseFactory):
    """测试表工厂"""

    _OBJECT_TYPE = 'test_table'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'name': f'test_record_{n}_{suffix}',
            'description': f'Test record #{n}',
            'value': 0,
            'is_active': True,
        }

    @classmethod
    def create_with_value(cls, name: str, value: int, cookie=None, **overrides):
        """创建带 value 的测试记录"""
        return cls.create(cookie=cookie, name=name, value=value, **overrides)

    @classmethod
    def create_inactive(cls, name: str, cookie=None, **overrides):
        """创建非激活测试记录"""
        return cls.create(cookie=cookie, name=name, is_active=False, **overrides)