# -*- coding: utf-8 -*-
"""
QueryPlanCache（QE-M4-2026-06-v2）

M4 阶段：SQL 编译缓存。
- 键: (entity_type, filter_signature, ordering_signature)
- 值: dict {'parsed_conditions': List[QueryCondition], 'ts': float}

不在缓存 cursor / 关联子查询 / computed count（动态性强）。
不在缓存 SQL 本身（避免 QueryBuilder 内部状态被破坏）—— 缓存的是
`_apply_meta_driven_filters` 的中间解析结果。

设计原则：
- 零侵入：未命中 → 原路径（call apply + 缓存结果）
- TTL：60s（防 schema 变更后 stale）
- LRU：max 1024 entries
- 线程安全：dict 操作原子性 + 单线程服务场景
"""
from __future__ import annotations
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class QueryPlanCache:
    """SQL 编译缓存（条件解析层）。"""

    def __init__(self, max_size: int = 1024, ttl_seconds: int = 60):
        self._cache: "OrderedDict[Tuple, Dict[str, Any]]" = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _key(self, entity_type: str, filter_signature: str, ordering_signature: str = '') -> tuple:
        return (entity_type, filter_signature, ordering_signature)

    def get(self, entity_type: str, filter_signature: str, ordering_signature: str = '') -> Optional[Dict[str, Any]]:
        """取缓存。命中返回 plan dict；未命中或过期返回 None。"""
        key = self._key(entity_type, filter_signature, ordering_signature)
        if key not in self._cache:
            self.misses += 1
            return None
        entry = self._cache[key]
        if time.time() - entry.get('ts', 0) > self.ttl:
            del self._cache[key]
            self.misses += 1
            return None
        self._cache.move_to_end(key)
        self.hits += 1
        return entry.get('plan')

    def put(
        self,
        entity_type: str,
        filter_signature: str,
        ordering_signature: str,
        plan: Dict[str, Any],
    ) -> None:
        """写缓存。"""
        key = self._key(entity_type, filter_signature, ordering_signature)
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
            self.evictions += 1
        self._cache[key] = {
            'plan': plan,
            'ts': time.time(),
        }

    def invalidate(self, entity_type: Optional[str] = None) -> None:
        """失效缓存。
        - entity_type=None: 清空全部
        - entity_type='user': 只清空 user 实体
        """
        if entity_type is None:
            self._cache.clear()
        else:
            keys_to_del = [k for k in self._cache if k[0] == entity_type]
            for k in keys_to_del:
                del self._cache[k]

    def stats(self) -> Dict[str, Any]:
        """DRE 可观测性。"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total) if total > 0 else 0.0
        return {
            'size': len(self._cache),
            'max_size': self.max_size,
            'ttl_seconds': self.ttl,
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'hit_rate': f'{hit_rate:.2%}',
        }


# 全局默认实例（惰性）
_default_cache: Optional[QueryPlanCache] = None


def get_query_plan_cache() -> QueryPlanCache:
    """获取全局 QueryPlanCache（单例）。"""
    global _default_cache
    if _default_cache is None:
        _default_cache = QueryPlanCache()
    return _default_cache


def signature_filters(filter_params: Dict[str, str]) -> str:
    """生成 filter_params 的稳定签名。"""
    if not filter_params:
        return ''
    items = sorted(filter_params.items())
    return '|'.join(f'{k}={v}' for k, v in items)


def signature_ordering(order_by: str) -> str:
    """生成 ordering 的稳定签名。"""
    return (order_by or '').strip().lower()
