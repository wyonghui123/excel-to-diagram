import time
from typing import Dict, Optional, Tuple


class TokenVersionService:
    """
    Token Version 验证服务 — 轻量级 in-memory 缓存

    性能：
    - 普通请求：内存 dict 查找 O(1)，零 DB 查询
    - 缓存过期（60s）：单次 DB SELECT + 更新缓存
    - 角色变更：立即更新 DB + 缓存
    """

    _instance: Optional['TokenVersionService'] = None
    _version_cache: Dict[int, Tuple[int, float]] = {}
    _cache_ttl: float = 60.0
    _ds = None

    @classmethod
    def get_instance(cls) -> 'TokenVersionService':
        if cls._instance is None:
            cls._instance = TokenVersionService()
        return cls._instance

    def set_data_source(self, ds) -> None:
        self._ds = ds

    def check(self, user_id: int, token_version: int) -> bool:
        if not token_version:
            return True

        now = time.time()
        cached = self._version_cache.get(user_id)
        if cached is not None:
            cached_version, cached_time = cached
            if now - cached_time < self._cache_ttl:
                return cached_version == token_version

        try:
            current = self._get_db_version(user_id)
            self._version_cache[user_id] = (current, now)
            return current == token_version
        except Exception:
            return True

    def bump(self, user_ids) -> None:
        """角色变更时递增 token_version 并更新缓存"""
        if not self._ds:
            return
        ids = user_ids if isinstance(user_ids, list) else [user_ids]
        now = time.time()
        for uid in ids:
            try:
                self._ds.execute(
                    "UPDATE users SET token_version = token_version + 1 WHERE id = ?",
                    [uid]
                )
                current = self._get_db_version(uid)
                self._version_cache[uid] = (current, now)
            except Exception:
                pass

    def _get_db_version(self, user_id: int) -> int:
        # P10 修复: 必须调用 fetchone() 获取真正的 row 对象
        # 之前是 row[0]（cursor 不支持下标），导致异常被 catch
        # 后果：assign_role 等的 token_version 失效机制形同虚设
        cursor = self._ds.execute(
            "SELECT COALESCE(token_version, 0) FROM users WHERE id = ?",
            [user_id]
        )
        row = cursor.fetchone()
        return row[0] if row else 0


token_version_service = TokenVersionService.get_instance()
