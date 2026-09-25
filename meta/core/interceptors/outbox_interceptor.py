# -*- coding: utf-8 -*-
"""[多产品平台 §6.14.2] 业务写 → outbox 同事务入队。

这是"事件不丢"的唯一保证（R15）：outbox 行与业务写在**同一个库、同一个事务**里
提交。业务写成功而事件丢失（进程崩溃）在架构上不可能发生 —— 要么两者都提交，
要么两者都回滚。

与 cdc_bus 的分工（§6.14.1 / R17）：内存总线继续服务"页面实时刷新"这类可丢失
场景；跨应用**业务写**只走本拦截器。

零影响：没有任何事件契约（legacy / 应用未声明 events）时，`should_execute`
直接返回 False，业务写路径不增加任何查询。
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from meta.core.action_constants import CRUD_CREATE, CRUD_DELETE, CRUD_UPDATE
from meta.core.action_context import ActionContext
from meta.core.interceptors.base import Interceptor
from meta.core.table_name_validator import validate_table_name

logger = logging.getLogger(__name__)

_WRITE_ACTIONS = (CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE)


class OutboxInterceptor(Interceptor):
    """把命中的发布契约写成 outbox 行（同事务）。

    priority=94 的由来：`_execute_after_interceptors` 按 `reversed(priority)` 执行，
    95（PersistenceInterceptor）先跑完真正的持久化，94 紧随其后拿到写成功的结果；
    而 before_action 阶段本拦截器是空操作，不影响任何前置校验。
    """

    @property
    def priority(self) -> int:
        return 94

    def before_action(self, context: ActionContext) -> None:
        pass

    def should_execute(self, context: ActionContext) -> bool:
        if context.action not in _WRITE_ACTIONS:
            return False
        from meta.core.event_outbox import get_event_contract_registry
        return not get_event_contract_registry().is_empty

    def after_action(self, context: ActionContext) -> None:
        from meta.core.event_outbox import (
            ACTION_TO_TRIGGER, enqueue_event, evaluate_condition,
            get_event_contract_registry,
        )

        registry = get_event_contract_registry()
        if registry.is_empty:
            return
        if context.result is None or not context.result.success:
            return

        trigger = ACTION_TO_TRIGGER.get(context.action)
        if trigger is None:
            return

        from meta.core.app_registry import get_app_id_for_bo

        bo_id = getattr(context.meta_object, "id", "") or ""
        app_id = get_app_id_for_bo(bo_id)
        if not app_id:
            return

        contracts = registry.publishers_for(app_id, bo_id, trigger)
        if not contracts:
            return

        row = self._load_row(context)
        for contract in contracts:
            if contract.condition and not evaluate_condition(contract.condition, row):
                continue
            payload = {name: row.get(name) for name in contract.payload}
            enqueue_event(
                context.data_source, contract, context.object_id, payload,
                context.transaction_id or "",
            )

    @staticmethod
    def _load_row(context: ActionContext) -> Dict[str, Any]:
        """读**写后**的行状态（同一事务内可见）；删除场景回落到 old_data。

        payload 取写后状态是刻意的：契约条件（如 `status == 'shipped'`）判定的
        就是"这次写把对象变成了什么"，而非写之前的值。
        """
        object_id = context.object_id
        if object_id is None:
            return dict(context.params or {})

        table = validate_table_name(context.meta_object.table_name)
        cursor = None
        try:
            cursor = context.data_source.execute(
                f"SELECT * FROM {table} WHERE id = ?", [object_id]
            )
            row = cursor.fetchone()
        except Exception as e:  # noqa: BLE001 - 行不可读（已删除）走 old_data
            logger.debug("[OutboxInterceptor] 读后置行失败（%s）: %s", table, e)
            row = None

        if not row:
            return dict(context.old_data or {})
        if isinstance(row, dict):
            return dict(row)
        columns = [desc[0] for desc in (cursor.description or [])]
        return dict(zip(columns, row))