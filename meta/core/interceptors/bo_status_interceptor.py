# -*- coding: utf-8 -*-
"""[D3 2026-10-03] BO 写入链 → bo.status_changed 反向事件（§9.7 规范 4）。

挂点: BO `crud_update` 写后拦截器 —— 比较写前 `context.old_data.status`
      与写后行 `status`（`BOFramework._load_old_data` 在写前载入 old_data），
      变化即经 `bo_status_event.enqueue_bo_status_changed()` **同事务**入队。

为何独立于 OutboxInterceptor:
    `OutboxInterceptor` 按契约 `condition` 对**写后行**做字段比较
    （如 `status == 'shipped'`），表达不了「状态发生了变化（from→to）」。
    `bo.status_changed` 是需要 from→to 语义的**平台保留事件**，由本类专属处理；
    `OutboxInterceptor` 对该保留名让位，避免同一写双入队。

零影响: 注册表为空 / 无该实体保留契约时 `should_execute` 直接 False。
"""
from __future__ import annotations

import logging
from typing import Any, List

from meta.core.action_constants import CRUD_UPDATE
from meta.core.action_context import ActionContext
from meta.core.bo_status_event import (
    BO_STATUS_CHANGED, STATUS_FIELD, detect_status_change, enqueue_bo_status_changed,
)
from meta.core.event_outbox import get_event_contract_registry
from meta.core.interceptors.base import Interceptor
from meta.core.interceptors.outbox_interceptor import OutboxInterceptor

logger = logging.getLogger(__name__)

_TRIGGER_AFTER_UPDATE = "after_update"


class BoStatusInterceptor(Interceptor):
    """`crud_update` 写后检测 status 变化 → 发 bo.status_changed（同事务）。

    priority=93 的由来：`_execute_after_interceptors` 按 `reversed(priority)` 执行，
    95（PersistenceInterceptor）先完成真正持久化，94（OutboxInterceptor）紧随，
    93（本类）最后 —— 此时写后行可读、写前 old_data 已在 execute() 主路径载入。
    """

    @property
    def priority(self) -> int:
        return 93

    def before_action(self, context: ActionContext) -> None:
        pass

    def _contracts(self, context: ActionContext) -> List[Any]:
        registry = get_event_contract_registry()
        if registry.is_empty:
            return []
        return [
            c for c in registry.publishers
            if c.name == BO_STATUS_CHANGED
            and c.entity == context.object_type
            and c.trigger == _TRIGGER_AFTER_UPDATE
        ]

    def should_execute(self, context: ActionContext) -> bool:
        if context.action != CRUD_UPDATE:
            return False
        return bool(self._contracts(context))

    def after_action(self, context: ActionContext) -> None:
        if context.result is None or not context.result.success:
            return

        row = OutboxInterceptor._load_row(context)
        change = detect_status_change(context.old_data, row, STATUS_FIELD)
        if change is None:
            return
        from_status, to_status = change

        for contract in self._contracts(context):
            enqueue_bo_status_changed(
                context.data_source, contract, entity_id=context.object_id,
                row=row, from_status=from_status, to_status=to_status,
                transaction_id=context.transaction_id or "",
            )