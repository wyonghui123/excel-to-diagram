"""
ChangeSubscriptionFactory (P1-5b 新建)
======================================

变更订阅工厂: 用于事件订阅配置的测试

yaml: meta/schemas/change_subscription.yaml
表名: change_subscriptions
required 字段:
- user_id
- object_type
- channel (in_app/email/webhook/sms)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class ChangeSubscriptionFactory(BaseFactory):
    """变更订阅工厂"""

    _OBJECT_TYPE = 'change_subscription'

    # 标准 channel
    CHANNEL_IN_APP = 'in_app'
    CHANNEL_EMAIL = 'email'
    CHANNEL_WEBHOOK = 'webhook'
    CHANNEL_SMS = 'sms'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        return {
            'user_id': None,
            'object_type': 'product',
            'event_types': '["created","updated","deleted"]',
            'channel': cls.CHANNEL_IN_APP,
            'filter_condition': None,
            'webhook_url': None,
            'is_active': True,
            'description': f'Subscription #{n}',
        }

    @classmethod
    def create_for_user(
        cls, user_id: int, object_type: str = 'product', cookie=None, **overrides
    ):
        """为指定用户创建订阅"""
        return cls.create(
            cookie=cookie, user_id=user_id, object_type=object_type, **overrides
        )

    @classmethod
    def create_webhook(
        cls, user_id: int, webhook_url: str, object_type: str = 'product', cookie=None, **overrides
    ):
        """创建 webhook 渠道订阅"""
        return cls.create(
            cookie=cookie, user_id=user_id,
            object_type=object_type,
            channel=cls.CHANNEL_WEBHOOK,
            webhook_url=webhook_url, **overrides
        )

    @classmethod
    def create_email(cls, user_id: int, object_type: str = 'product', cookie=None, **overrides):
        """创建邮件渠道订阅"""
        return cls.create(
            cookie=cookie, user_id=user_id,
            object_type=object_type,
            channel=cls.CHANNEL_EMAIL, **overrides
        )

    @classmethod
    def create_for_object_type(
        cls, user_id: int, object_type: str, event_types: list = None, cookie=None, **overrides
    ):
        """为指定对象类型创建订阅"""
        import json as _json
        events = event_types or ['created', 'updated', 'deleted']
        return cls.create(
            cookie=cookie, user_id=user_id,
            object_type=object_type,
            event_types=_json.dumps(events), **overrides
        )