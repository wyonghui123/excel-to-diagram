"""
AnnotationFactory (Phase 3 新建)
==================================

注释工厂: 用于批注/标签/备注测试
"""
from typing import Dict, Any, Optional
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class AnnotationFactory(BaseFactory):
    """注释工厂"""

    _OBJECT_TYPE = 'annotation'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'text': f'Test annotation {n} {suffix}',
            'object_type': 'business_object',
            'object_id': None,  # 需配 BO
            'author_id': None,  # 需配 user
            'tags': ['test', 'auto-generated'],
        }

    @classmethod
    def create_for_object(cls, object_type: str, object_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """为指定对象创建注释"""
        return cls.create(cookie=cookie, object_type=object_type, object_id=object_id, **overrides)

    @classmethod
    def create_with_tag(cls, tag: str, cookie=None, **overrides) -> Dict[str, Any]:
        """创建带指定 tag 的注释"""
        return cls.create(cookie=cookie, tags=[tag], **overrides)
