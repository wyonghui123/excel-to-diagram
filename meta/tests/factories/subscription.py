"""
SubscriptionFactory (Phase 1 扩展)
====================================

订阅工厂: 扩展原 SubscriptionFactory, 添加:
- create_for_object
- create_for_event_type
- create_with_webhook

TBD-4 采纳: 唯一性 + 类型化
"""
from typing import Dict, Any, Optional
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class SubscriptionFactory(BaseFactory):
    """订阅工厂 (Phase 1 扩展)"""

    _OBJECT_TYPE = 'subscription'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'name': f'Test Subscription {n}_{suffix}',
            'object_type': 'business_object',
            'event_types': ['create', 'update'],
            'channel': 'webhook',
            'webhook_url': f'https://test.local/webhook/{suffix}',
            'is_active': True,
        }

    @classmethod
    def create_for_object(cls, object_type: str, object_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """为指定对象创建订阅"""
        return cls.create(cookie=cookie, object_type=object_type, object_id=object_id, **overrides)

    @classmethod
    def create_with_event_types(cls, event_types: list, cookie=None, **overrides) -> Dict[str, Any]:
        """创建带指定事件类型的订阅"""
        return cls.create(cookie=cookie, event_types=event_types, **overrides)

    @classmethod
    def create_inactive(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """创建禁用订阅"""
        return cls.create(cookie=cookie, is_active=False, **overrides)
