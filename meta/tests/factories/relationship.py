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
            # [FIX 2026-07-17 v1.1] 覆盖 yaml 必填字段:
            # source_bo_id / target_bo_id / version_id (relationship.yaml required)
            # 注意: yaml 只有 source_bo_id/target_bo_id (无 source_id/target_id/source_type)
            'source_bo_id': None,  # 需配 BO
            'target_bo_id': None,  # 需配 BO
            'version_id': None,  # 由 VersionContextInterceptor 自动解析
            # 业务字段
            'name': f'Test Relationship {n}_{suffix}',
        }

    @classmethod
    def create_one_to_many(cls, source_bo_id: int, target_bo_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """1对多关系"""
        return cls.create(
            cookie=cookie,
            source_bo_id=source_bo_id,
            target_bo_id=target_bo_id,
            **overrides
        )

    @classmethod
    def create_many_to_many(cls, source_bo_id: int, target_bo_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """多对多关系"""
        return cls.create(
            cookie=cookie,
            source_bo_id=source_bo_id,
            target_bo_id=target_bo_id,
            **overrides
        )
