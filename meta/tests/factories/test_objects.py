"""
TestObjectsFactory (P1-5d 新建)
================================

测试对象工厂: 用于单元测试和集成测试

yaml: meta/schemas/test_objects.yaml
authorization.check = false (开放访问)
audit.enabled = true (有审计)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class TestObjectsFactory(BaseFactory):
    """测试对象工厂"""

    _OBJECT_TYPE = 'test_objects'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'name': f'test_obj_{n}_{suffix}',
            'description': f'Test object #{n}',
            'value': 0,
            'parent_id': None,
            'tags': '[]',
            'is_active': True,
        }

    @classmethod
    def create_with_name(cls, name: str, cookie=None, **overrides):
        """创建指定名称的测试对象"""
        return cls.create(cookie=cookie, name=name, **overrides)

    @classmethod
    def create_child(cls, parent_id: int, name: str = None, cookie=None, **overrides):
        """创建子测试对象"""
        if name is None:
            n = cls._next_counter()
            name = f'child_obj_{n}'
        return cls.create(
            cookie=cookie, name=name, parent_id=parent_id, **overrides
        )