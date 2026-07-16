# -*- coding: utf-8 -*-
"""
LRU + TTL Cache - 内部缓存原语 (FR-002)

替代 EnrichmentEngine._name_cache / _record_cache 的无界 Dict
支持：
- 容量上限（LRU 淘汰）
- TTL 自动失效
- 命中率统计（暴露给 Prometheus / /diagnostics）
- 可关闭（META_ENRICHMENT_CACHE_DISABLED=1）
"""
import os
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Optional


class LRUTTLCache:
    """LRU + TTL 缓存

    线程安全：使用 Lock 保护内部状态。
    内存安全：超过 max_size 自动 LRU 淘汰。
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: int = 300):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = Lock()

        # 统计指标（FR-002 NFR-003.1）
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值；过期或不存在返回 None。"""
        with self._lock:
            if key not in self._data:
                self.misses += 1
                return None
            value, expire_at = self._data[key]
            if time.time() > expire_at:
                del self._data[key]
                self.expirations += 1
                self.misses += 1
                return None
            self._data.move_to_end(key)  # LRU
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        """设置缓存值。"""
        with self._lock:
            expire_at = time.time() + self._ttl
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (value, expire_at)
            if len(self._data) > self._max_size:
                self._data.popitem(last=False)  # evict LRU
                self.evictions += 1

    def clear(self) -> None:
        """清空缓存（用于写操作时显式失效）。"""
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        """返回命中统计（给 /diagnostics 端点用）。"""
        with self._lock:
            total = self.hits + self.misses
            # 计算内部 entries 总数（向后兼容 dict 风格）
            inner_entries = 0
            for v, _ in self._data.values():
                if isinstance(v, dict):
                    inner_entries += len(v)
            return {
                "size": len(self._data),
                "max_size": self._max_size,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "expirations": self.expirations,
                "hit_rate": round(self.hits / total, 4) if total > 0 else 0,
                "inner_entries": inner_entries,
            }


# 全局开关：紧急情况可禁用缓存（META_ENRICHMENT_CACHE_DISABLED=1）
def is_cache_disabled() -> bool:
    return os.environ.get("META_ENRICHMENT_CACHE_DISABLED", "0") == "1"
