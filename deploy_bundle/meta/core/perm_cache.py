# -*- coding: utf-8 -*-
r"""
Permission Cache — NFR-001 性能优化（缓存层）

【背景 2026-06-04】
Spec v1.4 NFR-001: 权限计算性能优化，对标 SAP DCL Code-to-Data。
- 每次请求都重新计算 role_dimension_scopes + bindings 是浪费
- 引入 LRU/TTL 缓存，避免重复计算
- 缓存 key: (user_id, bo_id, role_ids_hash)
- 缓存 value: List[Condition]

【SAP DCL 对标】
- DCL 是声明式 + 编译时生成
- 我们的缓存是运行时 + 短期缓存
- 折中方案：缓存 5 分钟，过期重算

【v1.4 设计】
- Cache key: (user_id, bo_id, frozenset(role_ids))
- Cache value: List[Condition] (与 _resolve_field 输出相同)
- TTL: 5 分钟（与 BoSchemaLoader 同步）
- 缓存大小: 1000 entries (LRU)
"""
import hashlib
import json
import logging
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PermissionCache:
    """权限结果 LRU 缓存（NFR-001）

    特性：
    - LRU 淘汰（最近最少使用）
    - TTL 过期（默认 300s = 5min）
    - 线程安全（Lock）
    - 容量限制（默认 1000）
    """

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self._max_size = max_size
        self._ttl = ttl
        self._cache: OrderedDict[str, Tuple[List[Dict[str, Any]], float]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(
        user_id: int,
        bo_id: str,
        role_ids: Optional[List[int]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """生成缓存 key"""
        role_part = (
            hashlib.md5(
                json.dumps(sorted(role_ids or []), default=str).encode()
            ).hexdigest()[:8]
        )
        param_part = (
            hashlib.md5(
                json.dumps(parameters or {}, default=str, sort_keys=True).encode()
            ).hexdigest()[:8]
        )
        return f"u{user_id}:b{bo_id}:r{role_part}:p{param_part}"

    def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """获取缓存值（过期或不存在返回 None）"""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            value, expires_at = self._cache[key]
            if time.time() > expires_at:
                # 过期
                del self._cache[key]
                self._misses += 1
                return None
            # LRU：移到末尾
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: List[Dict[str, Any]]) -> None:
        """设置缓存值"""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, time.time() + self._ttl)
            # LRU 淘汰
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (
                self._hits / total if total > 0 else 0.0
            )
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f'{hit_rate:.2%}',
                'ttl': self._ttl,
            }


# 单例
_cache_instance: Optional[PermissionCache] = None
_cache_lock = Lock()


def get_permission_cache() -> PermissionCache:
    """获取全局单例缓存"""
    global _cache_instance
    with _cache_lock:
        if _cache_instance is None:
            _cache_instance = PermissionCache()
        return _cache_instance
