# -*- coding: utf-8 -*-
"""
[MODULE] permission_cache — Phase 8 三级缓存
[DESCRIPTION] L1 请求级 / L2 角色级 / L3 全局级 缓存, 加速权限决策
[SPEC] spec-permission-system-unification-2026-07-19 §3.13 / §8.8

[设计原则]
  L1 Cache (请求级) — threading.local, 单次请求内缓存
    - TTL: 请求生命周期 (clear_l1() 显式清空)
    - 存储: 用户权限决策结果
    - 命中率: > 90%

  L2 Cache (角色级) — TTLCache, 5 分钟 TTL
    - 存储: 角色的 dimension scope + permission rules
    - 失效: 角色配置变更时 (invalidate(role_id))

  L3 Cache (全局级) — SQLite :memory:, 1 小时 TTL
    - 存储: BO.yaml schema + 全局规则
    - 失效: 配置文件变更时 (invalidate_all())

  PermissionCacheManager — 统一管理 L1+L2+L3 级联查询
    get_or_load(key, loader):
      L1 miss → L2 miss → L3 miss → loader()
      命中层级: L1 (request) > L2 (role) > L3 (global) > loader
"""
import json
import logging
import sqlite3
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# P8-T1: L1 请求级缓存 (threading.local)
# ============================================================================

class L1RequestCache:
    """[P8-T1] 请求级缓存 — 基于 threading.local

    同一请求 (线程) 内不重复计算同一 key 的权限决策.
    线程隔离: 不同线程的 L1 缓存互不影响.
    """

    def __init__(self):
        self._local = threading.local()

    def _get_store(self) -> Dict[Tuple, Any]:
        """获取当前线程的 L1 存储 (懒初始化)"""
        if not hasattr(self._local, 'store'):
            self._local.store = {}
        return self._local.store

    def get(self, key: Tuple) -> Optional[Any]:
        """[P8-T1] 查询 L1, 未命中返回 None"""
        return self._get_store().get(key)

    def put(self, key: Tuple, value: Any) -> None:
        """[P8-T1] 写入 L1"""
        self._get_store()[key] = value

    def get_or_load(
        self,
        key: Tuple,
        loader: Callable[[], Any],
    ) -> Any:
        """[P8-T1] 查询 L1, 未命中则调 loader 加载并写入"""
        store = self._get_store()
        if key in store:
            logger.debug(f'[P8-T1 L1 hit] key={key}')
            return store[key]
        value = loader()
        store[key] = value
        logger.debug(f'[P8-T1 L1 miss→load] key={key}')
        return value

    def clear(self) -> None:
        """[P8-T1] 清空当前线程的 L1 缓存"""
        if hasattr(self._local, 'store'):
            self._local.store.clear()


# ============================================================================
# P8-T2: L2 角色级缓存 (TTLCache, TTL=5min)
# ============================================================================

class L2RoleCache:
    """[P8-T2] 角色级缓存 — TTLCache, 5 分钟 TTL

    key = (role_id, resource_type, action)
    不同 role/resource/action 的 key 互不干扰.
    TTL 过期后自动 miss, 调用 loader 重新加载.
    """

    def __init__(self, ttl_seconds: int = 300):
        """Args:
            ttl_seconds: TTL 秒数 (默认 300 = 5 分钟, Spec §3.13)
        """
        self._ttl = ttl_seconds
        self._store: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def _is_expired(self, timestamp: float) -> bool:
        """检查时间戳是否过期"""
        return (time.time() - timestamp) > self._ttl

    def _purge_expired(self) -> None:
        """清除过期项 (惰性清除)"""
        now = time.time()
        expired_keys = [
            k for k, (ts, _) in self._store.items()
            if (now - ts) > self._ttl
        ]
        for k in expired_keys:
            del self._store[k]

    def get(self, key: Tuple) -> Optional[Any]:
        """[P8-T2] 查询 L2, 未命中或过期返回 None"""
        with self._lock:
            self._purge_expired()
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if self._is_expired(ts):
                del self._store[key]
                return None
            return value

    def put(self, key: Tuple, value: Any) -> None:
        """[P8-T2] 写入 L2"""
        with self._lock:
            self._store[key] = (time.time(), value)

    def get_or_load(
        self,
        key: Tuple,
        loader: Callable[[], Any],
    ) -> Any:
        """[P8-T2] 查询 L2, 未命中或过期则调 loader"""
        with self._lock:
            self._purge_expired()
            entry = self._store.get(key)
            if entry is not None:
                ts, value = entry
                if not self._is_expired(ts):
                    logger.debug(f'[P8-T2 L2 hit] key={key}')
                    return value
                # 过期, 删除
                del self._store[key]
        # 调 loader (锁外, 避免长时间持锁)
        value = loader()
        with self._lock:
            self._store[key] = (time.time(), value)
        logger.debug(f'[P8-T2 L2 miss→load] key={key}')
        return value

    def invalidate(self, role_id: Optional[int] = None) -> int:
        """[P8-T4] 失效指定 role 的 L2 缓存

        Args:
            role_id: 角色 ID. None 表示失效所有.

        Returns:
            被清除的条目数
        """
        with self._lock:
            if role_id is None:
                count = len(self._store)
                self._store.clear()
                return count
            # key 格式: (role_id, resource_type, action, ...)
            keys_to_remove = [
                k for k in self._store
                if len(k) > 0 and k[0] == role_id
            ]
            for k in keys_to_remove:
                del self._store[k]
            return len(keys_to_remove)

    def invalidate_all(self) -> int:
        """[P8-T4] 失效所有 L2 缓存"""
        return self.invalidate(role_id=None)


# ============================================================================
# P8-T3: L3 全局级缓存 (SQLite :memory:)
# ============================================================================

class L3GlobalCache:
    """[P8-T3] 全局级缓存 — SQLite :memory:, 1 小时 TTL

    跨角色共享 schema / 全局规则.
    数据持久在 SQLite :memory: 中 (进程内共享).
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Args:
            ttl_seconds: TTL 秒数 (默认 3600 = 1 小时, Spec §3.13)
        """
        self._ttl = ttl_seconds
        self._conn = sqlite3.connect(':memory:', check_same_thread=False)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        """初始化 cache_entries 表"""
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key_json TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    created_ts REAL NOT NULL
                )
            """)
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_ts ON cache_entries(created_ts)"
            )
            self._conn.commit()

    def _key_to_json(self, key: Tuple) -> str:
        """将 tuple key 转为 JSON 字符串 (用作 SQLite 主键)"""
        return json.dumps(list(key), ensure_ascii=False)

    def get(self, key: Tuple) -> Optional[Any]:
        """[P8-T3] 查询 L3, 未命中或过期返回 None"""
        key_json = self._key_to_json(key)
        with self._lock:
            row = self._conn.execute(
                "SELECT value_json, created_ts FROM cache_entries WHERE key_json = ?",
                (key_json,)
            ).fetchone()
        if row is None:
            return None
        value_json, created_ts = row
        if (time.time() - created_ts) > self._ttl:
            # 过期, 异步删除
            with self._lock:
                self._conn.execute(
                    "DELETE FROM cache_entries WHERE key_json = ?", (key_json,)
                )
                self._conn.commit()
            return None
        return json.loads(value_json)

    def put(self, key: Tuple, value: Any) -> None:
        """[P8-T3] 写入 L3"""
        key_json = self._key_to_json(key)
        value_json = json.dumps(value, ensure_ascii=False, default=str)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache_entries (key_json, value_json, created_ts) "
                "VALUES (?, ?, ?)",
                (key_json, value_json, time.time())
            )
            self._conn.commit()

    def get_or_load(
        self,
        key: Tuple,
        loader: Callable[[], Any],
    ) -> Any:
        """[P8-T3] 查询 L3, 未命中或过期则调 loader"""
        value = self.get(key)
        if value is not None:
            logger.debug(f'[P8-T3 L3 hit] key={key}')
            return value
        value = loader()
        self.put(key, value)
        logger.debug(f'[P8-T3 L3 miss→load] key={key}')
        return value

    def invalidate_all(self) -> int:
        """[P8-T4] 失效所有 L3 缓存"""
        with self._lock:
            cursor = self._conn.execute("SELECT COUNT(*) FROM cache_entries")
            count = cursor.fetchone()[0]
            self._conn.execute("DELETE FROM cache_entries")
            self._conn.commit()
        return count


# ============================================================================
# P8-T1+T2+T3: PermissionCacheManager — 统一管理三级级联缓存
# ============================================================================

class PermissionCacheManager:
    """[P8-T1/T2/T3/T4] 统一管理 L1+L2+L3 级联查询

    级联查询顺序: L1 (request) → L2 (role) → L3 (global) → loader
    任一层命中则直接返回, 不再调下层.

    用法:
        mgr = PermissionCacheManager()
        result = mgr.get_or_load(
            key=(role_id, resource_type, action),
            loader=lambda: expensive_permission_calc()
        )
    """

    def __init__(
        self,
        l1: Optional[L1RequestCache] = None,
        l2: Optional[L2RoleCache] = None,
        l3: Optional[L3GlobalCache] = None,
    ):
        self._l1 = l1 or L1RequestCache()
        self._l2 = l2 or L2RoleCache(ttl_seconds=300)
        self._l3 = l3 or L3GlobalCache(ttl_seconds=3600)

    def get_or_load(
        self,
        key: Tuple,
        loader: Callable[[], Any],
    ) -> Any:
        """级联查询 L1 → L2 → L3 → loader

        命中层级会向上回填:
          L2 命中 → 回填 L1
          L3 命中 → 回填 L1 + L2
          loader  → 回填 L1 + L2 + L3
        """
        # L1
        v = self._l1.get(key)
        if v is not None:
            return v

        # L2
        v = self._l2.get(key)
        if v is not None:
            self._l1.put(key, v)
            return v

        # L3
        v = self._l3.get(key)
        if v is not None:
            self._l1.put(key, v)
            self._l2.put(key, v)
            return v

        # loader
        v = loader()
        self._l1.put(key, v)
        self._l2.put(key, v)
        self._l3.put(key, v)
        return v

    def clear_l1(self) -> None:
        """[P8-T4] 清空 L1 (请求级)"""
        self._l1.clear()

    def invalidate(self, role_id: Optional[int] = None) -> None:
        """[P8-T4] 失效缓存

        Args:
            role_id: 指定角色 ID → L1 清空 + L2 按 role_id 失效 + L3 全清
                     None → 全部失效
        """
        # L1 清空 (请求级缓存与 role_id 无强绑定)
        self._l1.clear()
        # L2 按 role_id 失效
        self._l2.invalidate(role_id=role_id)
        # L3 全清 (全局 schema 变更概率低, 全清更安全)
        self._l3.invalidate_all()

    def invalidate_all(self) -> None:
        """[P8-T4] 失效所有缓存 (L1+L2+L3)"""
        self._l1.clear()
        self._l2.invalidate_all()
        self._l3.invalidate_all()
