# -*- coding: utf-8 -*-
"""镜像行守卫拦截器 —— party_relation 写入前的无序去重校验。

依据: docs/superpowers/specs/2026-10-20-party-relation-role-dictionary-and-mirror-guard.md §4.4

优先级 43（在 ConstraintValidationInterceptor 42 之后、HierarchyValidationInterceptor 45 之前）；
仅对 party_relation 的创建 / 更新生效（should_execute 短路，其余对象 / 动作零开销）。
判定口径见 meta/services/party_relation_guard_service.py。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.party_relation_guard_service import (
    MirrorRowError,
    PartyRelationGuardService,
    SelfRelationError,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

#: 受本守卫约束的对象（仅此对象生效）
GUARDED_OBJECT = 'party_relation'
_GUARDED_ACTIONS = ('crud_create', 'crud_update')


class PartyRelationGuardInterceptor(Interceptor):
    """party_relation 镜像行守卫（P43）。"""

    @property
    def priority(self) -> int:
        return 43

    def should_execute(self, context: 'ActionContext') -> bool:
        """仅拦截 party_relation 的创建 / 更新；其余对象 / 动作零开销短路。"""
        if getattr(context.meta_object, 'id', None) != GUARDED_OBJECT:
            return False
        return context.action in _GUARDED_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        params = dict(context.params or {})
        exclude_id = None
        if context.action == 'crud_update':
            # 更新可能是部分字段：与旧行合并还原「更新后的有效四元组」，
            # 并以自身 id 排除自己（避免原地 update 误伤）。
            merged = dict(context.old_data or {})
            merged.update(params)
            data = merged
            exclude_id = context.object_id
        else:
            data = params

        service = PartyRelationGuardService(context.data_source)
        try:
            service.assert_no_mirror(data, exclude_id=exclude_id)
        except (MirrorRowError, SelfRelationError) as e:
            from meta.core.exceptions import ValidationFailedError

            message = str(e)
            # 自反关系是「我方组织」填错，镜像行是「方向」填反，定位字段不同
            field_name = '我方组织' if isinstance(e, SelfRelationError) else '对手侧'
            rule = 'self_relation' if isinstance(e, SelfRelationError) else 'mirror_row'
            raise ValidationFailedError(
                message=message,
                details=[{
                    'field_name': field_name,
                    'rule': rule,
                    'message': message,
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        pass
