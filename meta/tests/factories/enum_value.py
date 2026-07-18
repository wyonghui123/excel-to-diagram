"""
EnumValueFactory (P1-6a 新建)
==============================

枚举值工厂: 用于枚举类型具体值项的测试

yaml: meta/schemas/enum_value.yaml
表名: enum_values
required 字段:
- enum_type_id
- code
- name
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class EnumValueFactory(BaseFactory):
    """枚举值工厂"""

    _OBJECT_TYPE = 'enum_value'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'enum_type_id': 'test_enum_type',
            'code': f'test_value_{n}_{suffix}',
            'name': f'Test Value {n}',
            'name_en': f'Test Value {n}',
            'dimensions': '{}',
            'sort_order': n * 10,
            'is_active': True,
            'is_system': False,
            'parent_code': None,
            'metadata': '{}',
        }

    @classmethod
    def create_for_enum_type(
        cls, enum_type_id: str, code: str, name: str = None,
        cookie=None, **overrides
    ):
        """为指定枚举类型创建值"""
        if name is None:
            name = f'{enum_type_id}.{code}'
        return cls.create(
            cookie=cookie,
            enum_type_id=enum_type_id, code=code, name=name, **overrides
        )

    @classmethod
    def create_system_value(
        cls, enum_type_id: str, code: str, name: str = None, cookie=None, **overrides
    ):
        """创建系统内置枚举值"""
        return cls.create_for_enum_type(
            enum_type_id, code, name,
            cookie=cookie, is_system=True, **overrides
        )

    @classmethod
    def create_inactive(
        cls, enum_type_id: str, code: str, name: str = None, cookie=None, **overrides
    ):
        """创建已禁用枚举值"""
        return cls.create_for_enum_type(
            enum_type_id, code, name,
            cookie=cookie, is_active=False, **overrides
        )

    @classmethod
    def create_child(
        cls, enum_type_id: str, code: str, parent_code: str,
        name: str = None, cookie=None, **overrides
    ):
        """创建子枚举值 (层级枚举)"""
        if name is None:
            name = f'{parent_code}.{code}'
        return cls.create_for_enum_type(
            enum_type_id, code, name,
            cookie=cookie, parent_code=parent_code, **overrides
        )

    @classmethod
    def create_multi_dim_value(
        cls, enum_type_id: str, code: str, dimensions: dict,
        name: str = None, cookie=None, **overrides
    ):
        """创建多维枚举值"""
        import json as _json
        if name is None:
            name = code
        return cls.create_for_enum_type(
            enum_type_id, code, name,
            cookie=cookie,
            dimensions=_json.dumps(dimensions),
            **overrides
        )