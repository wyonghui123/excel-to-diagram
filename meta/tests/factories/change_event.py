"""
ChangeEventFactory (P1-5b 新建)
===============================

变更事件工厂: 用于事件溯源记录的测试

yaml: meta/schemas/change_event.yaml
表名: change_events
required 字段:
- object_type
- object_id
- event_type (create/update/delete/state_change)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class ChangeEventFactory(BaseFactory):
    """变更事件工厂"""

    _OBJECT_TYPE = 'change_event'

    # 标准 event_type
    EVENT_CREATE = 'create'
    EVENT_UPDATE = 'update'
    EVENT_DELETE = 'delete'
    EVENT_STATE_CHANGE = 'state_change'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        return {
            'object_type': 'product',
            'object_id': 1,
            'event_type': cls.EVENT_CREATE,
            'changed_fields': '[]',
            'old_values': None,
            'new_values': '{}',
            'actor_user_id': None,
            'transaction_id': f'txn_{n}',
            'description': f'Change event #{n}',
        }

    @classmethod
    def create_for_object(
        cls, object_type: str, object_id: int, event_type: str = 'create',
        cookie=None, **overrides
    ):
        """创建指定对象的变更事件"""
        return cls.create(
            cookie=cookie,
            object_type=object_type,
            object_id=object_id,
            event_type=event_type, **overrides
        )

    @classmethod
    def create_update(
        cls, object_type: str, object_id: int,
        old_values: dict = None, new_values: dict = None,
        cookie=None, **overrides
    ):
        """创建 update 事件"""
        import json as _json
        return cls.create(
            cookie=cookie,
            object_type=object_type, object_id=object_id,
            event_type=cls.EVENT_UPDATE,
            old_values=_json.dumps(old_values or {}),
            new_values=_json.dumps(new_values or {}),
            changed_fields=_json.dumps(list((new_values or {}).keys())),
            **overrides
        )

    @classmethod
    def create_create(
        cls, object_type: str, object_id: int, values: dict = None,
        cookie=None, **overrides
    ):
        """创建 create 事件"""
        import json as _json
        return cls.create(
            cookie=cookie,
            object_type=object_type, object_id=object_id,
            event_type=cls.EVENT_CREATE,
            new_values=_json.dumps(values or {}), **overrides
        )

    @classmethod
    def create_delete(
        cls, object_type: str, object_id: int, old_values: dict = None,
        cookie=None, **overrides
    ):
        """创建 delete 事件"""
        import json as _json
        return cls.create(
            cookie=cookie,
            object_type=object_type, object_id=object_id,
            event_type=cls.EVENT_DELETE,
            old_values=_json.dumps(old_values or {}),
            new_values=None, **overrides
        )