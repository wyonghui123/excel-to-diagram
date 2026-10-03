# -*- coding: utf-8 -*-
"""[D3 2026-10-03] bo.status_changed 反向事件 —— 单据状态变更 → 跨应用握手通道

职责（§9.7 规范 4 / §12.1 D3）:
- 把「单据状态发生了变化（from→to）」这一语义做成**可复用的原子能力**：
  写前 old_data 与写后行比较 → 变化即经 D1 outbox **同事务**入队
  （`event_outbox.enqueue_event`），跨应用投递、消费端幂等。
- 覆盖 spec 明写的两种路径：任务驱动（B3 生效翻转）与**绕过任务的直接改单 / 导入**
  —— 因为钩子挂在 BO 写入链上，而非任务链上。

保留事件名:
- `BO_STATUS_CHANGED` 是**平台保留名**，由 `BoStatusInterceptor` 专属处理
  （`condition` 只能判写后行字段，表达不了 from→to）。`OutboxInterceptor`
  对该名让位，避免同一写双入队。

分层纪律:
- **不发明第二套通道**：复用 `event_outbox`（outbox + Dispatcher + 契约注册表）。
- **不发明状态**：本模块只**读取** status 字段做比较，不写任何表（入队由 outbox 负责）。
- 对账兜底（§9.7 规范 5）已由 B3 的 `decision_effect.reconcile_effects()` 落地，
  **不在本模块**。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §9.7 规范 4 / §12.1 D3
  先例: meta/core/interceptors/outbox_interceptor.py（写后入队）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional, Tuple

from meta.core.event_outbox import PublisherContract, enqueue_event

logger = logging.getLogger(__name__)

#: 平台保留事件名（§9.7 规范 4；由 BoStatusInterceptor 专属处理）
BO_STATUS_CHANGED = "bo.status_changed"

#: 约定：BO 的状态列名为 `status`（与 apps/warehouse/app.yaml 的
#: `condition: "status == 'shipped'"` 同一约定）
STATUS_FIELD = "status"

FROM_FIELD = "from_status"
TO_FIELD = "to_status"
KEY_FIELD = "event_key"


def detect_status_change(
    old_row: Optional[Dict[str, Any]],
    new_row: Optional[Dict[str, Any]],
    field: str = STATUS_FIELD,
) -> Optional[Tuple[str, str]]:
    """比较写前 / 写后的 `status`；变化返回 `(from, to)`，否则 None（fail-closed）。

    任一侧缺失（None / 无该字段）都不发事件 —— 宁可漏发，不可乱发。
    """
    old = (old_row or {}).get(field)
    new = (new_row or {}).get(field)
    if old is None or new is None:
        return None
    old_text, new_text = str(old), str(new)
    if old_text == new_text:
        return None
    return old_text, new_text


def build_status_payload(
    row: Optional[Dict[str, Any]],
    from_status: str,
    to_status: str,
    payload_fields: Iterable[str],
    event_key: str,
) -> Dict[str, Any]:
    """构造事件载荷：契约声明字段（只带必要字段）+ from/to + event_key。"""
    payload = {name: (row or {}).get(name) for name in payload_fields}
    payload[FROM_FIELD] = from_status
    payload[TO_FIELD] = to_status
    payload[KEY_FIELD] = event_key
    return payload


def enqueue_bo_status_changed(
    data_source,
    contract: PublisherContract,
    *,
    entity_id: Any,
    row: Optional[Dict[str, Any]],
    from_status: str,
    to_status: str,
    transaction_id: str = "",
) -> Optional[str]:
    """把一次状态变更写入 outbox（**同事务**；不自行提交）。

    幂等键口径（D4 最小要件）: `"{entity}:{entity_id}:{from}->{to}"`，
    随载荷 `event_key` 下发，供订阅方在 `app.yaml` 的 `idempotency_key` 引用。

    Returns:
        event_id；同 (event_name, entity_id, transaction_id) 重复时为 None
    """
    event_key = f"{contract.entity}:{entity_id}:{from_status}->{to_status}"
    payload = build_status_payload(
        row, from_status, to_status, contract.payload, event_key)
    return enqueue_event(
        data_source, contract, entity_id, payload, transaction_id)