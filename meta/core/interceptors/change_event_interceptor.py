# -*- coding: utf-8 -*-
"""v2 BO 写出口 → 变更事件发布拦截器。

背景：`/api/v2/bo` 是前端实际使用的写入口，但此前完全没有变更事件发布，
只有旧 `ManageService`（`/api/manage`）在发 —— 消息平台因此形同虚设。

与既有拦截器的分工（after 钩子按 priority 降序执行）：
    95 PersistenceInterceptor  —— 真正落盘
    94 OutboxInterceptor       —— 跨应用事件契约入 outbox
    93 BoStatusInterceptor     —— bo.status_changed 保留事件
    92 本类                    —— change_events（站内通知底座）

fail-open：发布失败只记 warning，业务写入照常成功。
"""
from __future__ import annotations

import logging

from meta.core.action_constants import CRUD_CREATE, CRUD_DELETE, CRUD_UPDATE
from meta.core.action_context import ActionContext
from meta.core.change_event_types import CREATED, DELETED, UPDATED
from meta.core.interceptors.base import Interceptor
from meta.core.interceptors.outbox_interceptor import OutboxInterceptor
from meta.core.models import registry

logger = logging.getLogger(__name__)

_ACTION_TO_EVENT = {
    CRUD_CREATE: CREATED,
    CRUD_UPDATE: UPDATED,
    CRUD_DELETE: DELETED,
}


class ChangeEventInterceptor(Interceptor):
    """CRUD 成功后发布变更事件（fail-open）。"""

    @property
    def priority(self) -> int:
        return 92

    def before_action(self, context: ActionContext) -> None:
        pass

    def should_execute(self, context: ActionContext) -> bool:
        if context.action not in _ACTION_TO_EVENT:
            return False
        # 未配置 change_notification 的对象零开销短路
        meta_object = registry.get(context.object_type)
        if not meta_object:
            return False
        ui_config = getattr(meta_object, 'ui_view_config', None)
        config = getattr(ui_config, 'change_notification', None)
        return bool(config and getattr(config, 'enabled', False))

    def after_action(self, context: ActionContext) -> None:
        if not context.result or not getattr(context.result, 'success', False):
            return
        try:
            self._publish(context)
        except Exception as e:  # noqa: BLE001 - fail-open
            logger.warning(
                "[ChangeEventInterceptor] publish failed: object_type=%s object_id=%s action=%s err=%s",
                context.object_type, context.object_id, context.action, e,
            )

    def _publish(self, context: ActionContext) -> None:
        from meta.services.change_notification_service import (
            ChangeEventRequest, ChangeNotificationService,
        )

        event_type = _ACTION_TO_EVENT[context.action]
        object_id = context.object_id
        old_data = None
        new_data = None

        if context.action == CRUD_CREATE:
            data = (context.result.data if context.result else None) or {}
            new_data = dict(data)
            object_id = data.get('id') or data.get('ID') or object_id
        elif context.action == CRUD_UPDATE:
            old_data = dict(context.old_data or {})
            new_data = OutboxInterceptor._load_row(context)
        else:  # CRUD_DELETE
            old_data = dict(context.old_data or {}) or OutboxInterceptor._load_row(context)

        if object_id is None:
            return

        ChangeNotificationService(context.data_source).publish_event(
            ChangeEventRequest(
                object_type=context.object_type,
                object_id=object_id,
                event_type=event_type,
                old_data=old_data,
                new_data=new_data,
            )
        )