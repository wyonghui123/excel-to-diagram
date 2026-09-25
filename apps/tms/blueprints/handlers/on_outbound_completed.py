# -*- coding: utf-8 -*-
"""[PoC 4] tms 的事件 handler：WMS 出库完成 → 建运单（roadmap §6.14.2）

调用时机（由 `meta/core/event_consumer.py` 的 `consume_event` 驱动）：
    1. 先在**本应用库**写入 consumed_events 去重标记
    2. 再调用本函数建业务数据
    3. 两者在同一事务提交 —— 要么都成，要么都回滚（下轮重试）

因此本函数**不需要自己做幂等**：重复投递会在步骤 1 被唯一键拦下。

约定签名: handle(data_source, payload) -> Any
    data_source: tms **自己的**库（消费方库，非发布方的库）
    payload: 发布契约声明的字段快照（order_no / item_id / quantity /
             warehouse_id / shipped_at）
"""
from __future__ import annotations

from meta.core.action_executor import ActionRegistry
from meta.core.models import registry as bo_registry

BO_ID = "waybill"


def handle(data_source, payload):
    """用平台 ActionRegistry 在本应用库里建运单。"""
    meta_object = bo_registry.get(BO_ID)
    if meta_object is None:
        raise RuntimeError(f"BO '{BO_ID}' 未注册（tms 应用未加载?）")

    order_no = payload.get("order_no")
    if not order_no:
        raise ValueError(f"事件载荷缺少 order_no: {payload}")

    waybill_no = f"WB-{order_no}"
    result = ActionRegistry(data_source).create(meta_object, {
        "waybill_no": waybill_no,
        "order_no": order_no,
        "item_id": payload.get("item_id"),
        "quantity": payload.get("quantity"),
        "warehouse_id": payload.get("warehouse_id"),
        "status": "created",
    })
    if not result.success:
        # 抛出让 consume_event 回滚去重标记 → 事件重试 / 进死信
        raise RuntimeError(f"建运单失败: {result.message}")

    return {"waybill_no": waybill_no, "order_no": order_no,
            "waybill_id": (result.data or {}).get("id")}