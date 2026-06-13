"""
RelationshipFactory (Phase 4 新建)
====================================

关系工厂: 用于对象间关系/外键测试
"""
from typing import Dict, Any, Optional
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class RelationshipFactory(BaseFactory):
    """关系工厂"""

    _OBJECT_TYPE = 'relationship'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'name': f'Test Relationship {n}_{suffix}',
            'source_type': 'business_object',
            'source_id': None,
            'target_type': 'business_object',
            'target_id': None,
            'type': 'one_to_many',
        }

    @classmethod
    def create_one_to_many(cls, source_id: int, target_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """1对多关系"""
        return cls.create(
            cookie=cookie,
            source_id=source_id,
            target_id=target_id,
            type='one_to_many',
            **overrides
        )

    @classmethod
    def create_many_to_many(cls, source_id: int, target_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """多对多关系"""
        return cls.create(
            cookie=cookie,
            source_id=source_id,
            target_id=target_id,
            type='many_to_many',
            **overrides
        )
