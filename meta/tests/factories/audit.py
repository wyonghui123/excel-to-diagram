"""
AuditLogFactory (Phase 3 新建)
================================

审计日志工厂: 用于审计/日志测试
"""
from typing import Dict, Any, Optional
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class AuditLogFactory(BaseFactory):
    """审计日志工厂"""

    _OBJECT_TYPE = 'audit_log'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(4)
        return {
            'action': 'create',
            'object_type': 'business_object',
            'object_id': None,
            'user_id': None,
            'trace_id': f'trace_{n}_{suffix}',
            'metadata': {'test': True, 'auto': True},
        }

    @classmethod
    def create_for_event(cls, action: str, object_type: str, object_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """为指定事件创建审计日志"""
        return cls.create(
            cookie=cookie,
            action=action,
            object_type=object_type,
            object_id=object_id,
            **overrides
        )

    @classmethod
    def create_for_user(cls, user_id: int, cookie=None, **overrides) -> Dict[str, Any]:
        """为指定用户创建审计日志"""
        return cls.create(cookie=cookie, user_id=user_id, **overrides)
