# -*- coding: utf-8 -*-
"""
CDCBus（QE-M7-2026-06-v2）

[M7.1 2026-06-05] CDC 事件总线。

设计：
- 内存 pub/sub（生产可换 Redis Stream）
- 线程安全（threading.RLock）
- 事件缓冲（maxlen 1000/实体）支持 Last-Event-ID 重放
- 订阅句柄用 with 块管理（自动取消订阅）
- 异常隔离（一个订阅者失败不影响其他）
"""
from __future__ import annotations
import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CDCEvent:
    """变更数据捕获事件。"""
    entity_type: str
    action: str  # 'create' / 'update' / 'delete'
    affected_ids: List[int] = field(default_factory=list)
    transaction_id: str = ''
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: f"cdc-{uuid.uuid4().hex[:16]}")
    user_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'entity_type': self.entity_type,
            'action': self.action,
            'affected_ids': self.affected_ids,
            'transaction_id': self.transaction_id,
            'timestamp': self.timestamp,
        }

    def to_sse(self) -> str:
        """SSE 序列化。"""
        data = json.dumps(self.to_dict(), default=str)
        return f"id: {self.event_id}\ndata: {data}\n\n"


class _Subscription:
    """订阅句柄（context manager）。"""

    def __init__(self, bus: 'CDCBus', entity_type: str, callback: Callable):
        self.bus = bus
        self.entity_type = entity_type
        self.callback = callback

    def __enter__(self) -> '_Subscription':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.bus.unsubscribe(self.entity_type, self.callback)
        return False

    def cancel(self) -> None:
        self.bus.unsubscribe(self.entity_type, self.callback)


class CDCBus:
    """CDC 事件总线。"""

    def __init__(self, max_buffer_per_entity: int = 1000):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_buffer: Dict[str, Deque[CDCEvent]] = defaultdict(
            lambda: deque(maxlen=max_buffer_per_entity)
        )
        self._lock = threading.RLock()
        self.published_count = 0
        self.delivered_count = 0
        self.error_count = 0

    def subscribe(
        self,
        entity_type: str,
        callback: Callable[[CDCEvent], None],
        last_event_id: str = '',
    ) -> _Subscription:
        """订阅 entity_type 变更。

        Args:
            entity_type: 实体类型
            callback: 回调函数（接收 CDCEvent）
            last_event_id: 重放起点（事件 ID 字典序比较）

        Returns:
            _Subscription: 订阅句柄
        """
        with self._lock:
            self._subscribers[entity_type].append(callback)
            # 重放历史事件
            if last_event_id:
                for event in list(self._event_buffer[entity_type]):
                    if event.event_id > last_event_id:
                        try:
                            callback(event)
                            self.delivered_count += 1
                        except Exception as e:
                            self.error_count += 1
                            logger.error(
                                f"[CDCBus.M7.1] replay subscriber error: {e}"
                            )
        return _Subscription(self, entity_type, callback)

    def publish(self, event: CDCEvent) -> None:
        """发布事件到所有订阅者。"""
        with self._lock:
            self._event_buffer[event.entity_type].append(event)
            self.published_count += 1
            for cb in self._subscribers.get(event.entity_type, []):
                try:
                    cb(event)
                    self.delivered_count += 1
                except Exception as e:
                    self.error_count += 1
                    logger.error(
                        f"[CDCBus.M7.1] subscriber error: {e}",
                        exc_info=False,
                    )

    def unsubscribe(self, entity_type: str, callback: Callable) -> None:
        with self._lock:
            if entity_type in self._subscribers:
                try:
                    self._subscribers[entity_type].remove(callback)
                except ValueError:
                    pass

    def replay(
        self,
        entity_type: str,
        last_event_id: str = '',
        limit: int = 100,
    ) -> List[CDCEvent]:
        """重放历史事件（无订阅，长期查询用）。"""
        with self._lock:
            events = list(self._event_buffer[entity_type])
            if last_event_id:
                events = [e for e in events if e.event_id > last_event_id]
            return events[:limit]

    def stats(self) -> Dict[str, Any]:
        """DRE 上报。"""
        with self._lock:
            return {
                'subscribed_entities': len([
                    k for k, v in self._subscribers.items() if v
                ]),
                'buffered_entities': len(self._event_buffer),
                'published': self.published_count,
                'delivered': self.delivered_count,
                'errors': self.error_count,
            }


_default_cdc_bus: Optional[CDCBus] = None


def get_cdc_bus() -> CDCBus:
    global _default_cdc_bus
    if _default_cdc_bus is None:
        _default_cdc_bus = CDCBus()
    return _default_cdc_bus
