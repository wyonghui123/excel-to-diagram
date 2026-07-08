# -*- coding: utf-8 -*-
"""
BO Schema Loader — 加载 BO 的 dimension_bindings 声明

【背景 2026-06-04】
Spec v1.3 (data-permission-unified-model) 引入运行时动态展开，
需要从 BO 的 YAML schema 中读取 dimension_bindings 声明，
作为数据权限过滤时"如何应用管理维度"的元数据。

dimension_bindings 格式：
    dimension_bindings:
      - dimension: domain       # 维度名
        field: id               # BO 表中的字段
      - dimension: product
        field: version_id       # 多跳关联
        through: version        # 中间表

缓存策略：LRU 缓存（TTL 5min），避免每次请求都读 YAML。
"""
import os
import time
import yaml
from threading import Lock
from typing import Dict, List, Optional, Any


_DEFAULT_TTL = 300  # 5 minutes


class BoSchemaLoader:
    """BO schema 加载器（带 LRU 缓存）"""

    def __init__(self, schema_dir: Optional[str] = None, ttl: int = _DEFAULT_TTL):
        self._schema_dir = schema_dir or self._default_schema_dir()
        self._ttl = ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_time: Dict[str, float] = {}
        self._lock = Lock()

    @staticmethod
    def _default_schema_dir() -> str:
        """默认 schema 目录：meta/schemas"""
        # __file__ = .../meta/core/bo_schema_loader.py
        # 向上两层 = .../meta
        current = os.path.abspath(__file__)
        for _ in range(2):
            current = os.path.dirname(current)
        return os.path.join(current, 'schemas')

    def get_dimension_bindings(self, bo_id: str) -> List[Dict[str, Any]]:
        """获取 BO 的 dimension_bindings 声明

        Args:
            bo_id: BO 标识符（如 'domain', 'sub_domain'）

        Returns:
            bindings 列表：
                [{'dimension': 'domain', 'field': 'id'}, ...]
        """
        bo_schema = self.get_bo_schema(bo_id)
        if not bo_schema:
            return []
        return bo_schema.get('dimension_bindings', []) or []

    def get_bo_schema(self, bo_id: str) -> Optional[Dict[str, Any]]:
        """获取 BO 的完整 schema（带缓存）

        Args:
            bo_id: BO 标识符

        Returns:
            完整的 BO schema dict，没有则 None
        """
        with self._lock:
            # 缓存命中 + 未过期
            if bo_id in self._cache:
                if time.time() - self._cache_time[bo_id] < self._ttl:
                    return self._cache[bo_id]
                # 过期，删除
                self._cache.pop(bo_id, None)
                self._cache_time.pop(bo_id, None)

        # 缓存未命中或过期，从文件读取
        schema = self._load_from_file(bo_id)
        if schema is not None:
            with self._lock:
                self._cache[bo_id] = schema
                self._cache_time[bo_id] = time.time()
        return schema

    def _load_from_file(self, bo_id: str) -> Optional[Dict[str, Any]]:
        """从 YAML 文件加载 BO schema"""
        yaml_path = os.path.join(self._schema_dir, f'{bo_id}.yaml')
        if not os.path.exists(yaml_path):
            return None
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return None
            return data
        except Exception as e:
            print(f"[BoSchemaLoader] Failed to load {yaml_path}: {e}")
            return None

    def has_owner_id(self, bo_id: str) -> bool:
        """检查 BO 是否声明了 owner_id 字段

        [FIX 2026-06-17] 同时检查:
        1. yaml fields 里有 owner_id 字段
        2. yaml aspects 列表里有 owner_aspect (aspect 会注入 owner_id 字段)
        修复: TEST333 + version 这种没有显式 owner_id 字段但引用 owner_aspect 的 BO,
              之前 has_owner_id 返回 False 导致 owner 例外失效,
              现在能识别出 aspect 注入的 owner_id 字段.
        """
        schema = self.get_bo_schema(bo_id)
        if not schema:
            return False
        for field in schema.get('fields', []) or []:
            fid = field.get('id') if isinstance(field, dict) else getattr(field, 'id', None)
            if fid == 'owner_id':
                return True
        # [FIX 2026-06-17] aspect 注入的字段也算
        aspects = schema.get('aspects', []) or []
        if 'owner_aspect' in aspects:
            return True
        return False

    def has_visibility_field(self, bo_id: str) -> bool:
        """[FIX v1.0.8 2026-06-10] 检查 BO 是否声明了 visibility 字段

        用于 DataPermissionInterceptor 判断是否需要应用 visibility scope 过滤:
        - version 有 visibility 字段 → True (需要应用 visibility scope 保护 draft)
        - product 没有 visibility 字段 → False (跳过 visibility scope, 避免过严)

        [FIX 2026-06-17] 同时检查 aspect 注入 (owner_aspect 包含 visibility 字段)
        """
        schema = self.get_bo_schema(bo_id)
        if not schema:
            return False
        for field in schema.get('fields', []) or []:
            fid = field.get('id') if isinstance(field, dict) else getattr(field, 'id', None)
            if fid == 'visibility':
                return True
        # [FIX 2026-06-17] aspect 注入的字段也算
        aspects = schema.get('aspects', []) or []
        if 'owner_aspect' in aspects:
            return True
        return False

    def get_bo_type(self, bo_id: str) -> str:
        """获取 BO 类型（FR-017 AC-1）

        Args:
            bo_id: BO 标识符

        Returns:
            'entity' | 'service'
            默认 'entity'（向后兼容）
        """
        schema = self.get_bo_schema(bo_id)
        if not schema:
            return 'entity'
        return schema.get('type', 'entity')

    def get_bo_actions(self, bo_id: str) -> List[Dict[str, Any]]:
        """获取 BO 的 actions 列表（FR-017 AC-2）

        Args:
            bo_id: BO 标识符

        Returns:
            actions 列表：
            [{'id': 'business_object_read', 'name': '...', 'action_type': 'read'}, ...]
        """
        schema = self.get_bo_schema(bo_id)
        if not schema:
            return []
        return schema.get('actions', []) or []

    def get_bo_action(
        self, bo_id: str, action_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取 BO 的单个 action（FR-017 AC-2）

        Args:
            bo_id: BO 标识符
            action_id: Action 标识符（如 'business_object_read'）

        Returns:
            action dict，未找到则 None
        """
        actions = self.get_bo_actions(bo_id)
        for a in actions:
            if isinstance(a, dict) and a.get('id') == action_id:
                return a
        return None

    def clear_cache(self, bo_id: Optional[str] = None) -> None:
        """清空缓存（bo_id=None 时清空所有）"""
        with self._lock:
            if bo_id:
                self._cache.pop(bo_id, None)
                self._cache_time.pop(bo_id, None)
            else:
                self._cache.clear()
                self._cache_time.clear()


# 单例
_loader_instance: Optional[BoSchemaLoader] = None
_loader_lock = Lock()


def get_bo_schema_loader() -> BoSchemaLoader:
    """获取全局单例加载器"""
    global _loader_instance
    with _loader_lock:
        if _loader_instance is None:
            _loader_instance = BoSchemaLoader()
        return _loader_instance
