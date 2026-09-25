# -*- coding: utf-8 -*-
"""[多产品平台] 跨应用事件：幂等消费框架（roadmap §6.14.2 / §6.14.4 ②）

投递语义是 **at-least-once**：进程崩溃、重试、Dispatcher 重启都会让同一事件被投递
多次。因此**消费端幂等是硬要求，不是优化项**（R16）。

实现方式：消费端在自己的库里维护 `consumed_events` 去重表，以
`(consumer_app, event_name, idempotency_key)` 为唯一键。

    with 事务:
        1. INSERT 去重标记   → 唯一冲突 ⇒ 已消费过 ⇒ 直接返回 duplicate
        2. 调 handler 建业务数据
        3. 回写处理结果
    handler 抛异常 ⇒ 事务回滚 ⇒ 去重标记一并回滚 ⇒ 下轮重试可再次消费

这样"标记 + 业务数据"原子提交：不会出现"标记成功但业务数据没建"（漏消费），
也不会出现"业务数据建了两次"（重复消费）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

CONSUMED_TABLE = "consumed_events"

CONSUMED_DDL = f"""
CREATE TABLE IF NOT EXISTS {CONSUMED_TABLE} (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    consumer_app     TEXT NOT NULL,
    event_name       TEXT NOT NULL,
    idempotency_key  TEXT NOT NULL,
    event_id         TEXT NOT NULL DEFAULT '',
    consumed_at      TEXT NOT NULL,
    result           TEXT NOT NULL DEFAULT '',
    UNIQUE (consumer_app, event_name, idempotency_key)
)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_consumed_table(data_source) -> None:
    """建去重表（启动期调用；表位于**消费方自己的库**）。"""
    data_source.execute(CONSUMED_DDL)


def _is_unique_violation(error: Exception) -> bool:
    return "unique" in str(error).lower()


def consume_event(
    data_source,
    consumer_app: str,
    event_name: str,
    idempotency_key: str,
    payload: Dict[str, Any],
    handler: Callable[[Any, Dict[str, Any]], Any],
    event_id: str = "",
) -> Dict[str, Any]:
    """幂等消费一条事件。

    Args:
        data_source: **消费方**的数据源（去重表与业务数据都在这里，同库同事务）
        consumer_app: 消费方应用 id
        event_name: 事件名
        idempotency_key: 去重值（由订阅契约的 `idempotency_key` 字段从 payload 取）
        payload: 事件载荷
        handler: `handle(data_source, payload)`，在本事务内建业务数据
        event_id: 源事件 id（仅记录，便于追溯）

    Returns:
        {"status": "consumed" | "duplicate", "result": ...}

    Raises:
        Exception: handler 的异常原样抛出（标记随事务回滚），交由 Dispatcher
            计入 attempts → 重试 / 死信。
    """
    if not str(idempotency_key):
        raise ValueError(
            f"事件 '{event_name}' 的幂等键为空（订阅契约 idempotency_key 未在 payload 中命中）"
        )

    with data_source.transaction():
        try:
            data_source.execute(
                f"INSERT INTO {CONSUMED_TABLE} (consumer_app, event_name, "
                f"idempotency_key, event_id, consumed_at, result) "
                f"VALUES (?, ?, ?, ?, ?, '')",
                (consumer_app, event_name, str(idempotency_key), event_id, _now_iso()),
            )
        except Exception as e:  # noqa: BLE001 - 唯一冲突即"已消费"，其余原样抛出
            if _is_unique_violation(e):
                logger.info(
                    "[EventConsumer] 重复投递已忽略: %s.%s key=%s",
                    consumer_app, event_name, idempotency_key,
                )
                return {"status": "duplicate", "result": None, "idempotency_key": str(idempotency_key)}
            raise

        result = handler(data_source, payload)

        data_source.execute(
            f"UPDATE {CONSUMED_TABLE} SET result = ? WHERE consumer_app = ? "
            f"AND event_name = ? AND idempotency_key = ?",
            (_serialize(result), consumer_app, event_name, str(idempotency_key)),
        )

    logger.info(
        "[EventConsumer] 已消费: %s.%s key=%s event_id=%s",
        consumer_app, event_name, idempotency_key, event_id,
    )
    return {"status": "consumed", "result": result, "idempotency_key": str(idempotency_key)}


def _serialize(result: Any) -> str:
    try:
        return json.dumps(result, ensure_ascii=False, default=str)[:500]
    except (TypeError, ValueError):
        return str(result)[:500]


def consumed_count(data_source, consumer_app: str, event_name: str = "") -> int:
    """去重表行数（供测试与运维观测）。"""
    if event_name:
        sql = (f"SELECT COUNT(*) FROM {CONSUMED_TABLE} WHERE consumer_app = ? "
               f"AND event_name = ?")
        params: tuple = (consumer_app, event_name)
    else:
        sql = f"SELECT COUNT(*) FROM {CONSUMED_TABLE} WHERE consumer_app = ?"
        params = (consumer_app,)
    rows = data_source.execute(sql, params).fetchone()
    return int(rows[0]) if rows else 0