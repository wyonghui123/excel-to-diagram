"""
FilterVariantFactory (Phase 5 新建)
====================================

过滤变体工厂: 用于保存用户的过滤条件组合测试

yaml: meta/schemas/filter_variant.yaml
required 字段 (排除审计自动生成):
- name (display_name)
- object_type
- filters (json)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class FilterVariantFactory(BaseFactory):
    """过滤变体工厂"""

    _OBJECT_TYPE = 'filter_variant'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            # [FIX 2026-07-17 P1] 覆盖 yaml 必填字段
            'name': f'Test Filter {n}_{suffix}',
            'object_type': 'business_object',
            'filters': {
                'status': 'active',
                'created_by': 'system',
            },
            # 业务字段 (使用 yaml default 值)
            'is_shared': False,
            'user_id': None,  # 需配 UserFactory
        }

    @classmethod
    def create_for_user(cls, user_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """创建用户专属变体"""
        return cls.create(cookie=cookie, user_id=user_id, is_shared=False, **overrides)

    @classmethod
    def create_shared(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """创建共享变体"""
        return cls.create(cookie=cookie, is_shared=True, **overrides)

    @classmethod
    def create_for_object_type(
        cls, object_type: str, cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建指定对象类型的过滤变体"""
        return cls.create(cookie=cookie, object_type=object_type, **overrides)