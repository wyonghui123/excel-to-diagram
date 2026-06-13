"""
WebhookFactory (Phase 4 业务特定)
===================================

Webhook 工厂: 用于订阅/通知测试
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class WebhookFactory(BaseFactory):
    """Webhook 工厂"""

    _OBJECT_TYPE = 'webhook'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'url': f'https://test.local/webhook/{suffix}',
            'events': ['create', 'update'],
            'is_active': True,
            'secret': f'secret_{suffix}',
        }

    @classmethod
    def create_disabled(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """创建禁用 webhook"""
        return cls.create(cookie=cookie, is_active=False, **overrides)
