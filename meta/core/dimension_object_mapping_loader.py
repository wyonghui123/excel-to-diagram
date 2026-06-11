# -*- coding: utf-8 -*-
"""
Dimension Object Mapping Loader — 加载管理维度 → BO 字段映射配置

【背景 2026-06-10】
原 dimension_scope_engine.py 中 RESOURCE_TABLE_MAP / PARENT_FIELD_MAP 硬编码在 Python 代码里，
无法支持"通用维度"(region/department 等) 以及动态扩展。

本 loader 从 meta/schemas/dimension_object_mapping.yaml 加载映射配置，
提供统一查询接口:
  - get_applies_to(dimension_code) → 该维度适用于哪些 BO/字段
  - get_dimension_type(dimension_code) → business | generic
  - get_value_table(dimension_code) → 通用维度的值表
  - get_combination_policy() → scope_combination (AND/OR), owner_always_visible

缓存策略: LRU + TTL (5min)，避免每次请求都读 YAML。
fallback: 加载失败时返回空配置, DimensionScopeEngine 会 fallback 到硬编码 MAP.
"""
import os
import time
import yaml
import logging
from threading import Lock
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300  # 5 minutes


class DimensionObjectMappingLoader:
    """管理维度 ↔ BO 字段映射加载器（带 LRU 缓存）"""

    def __init__(self, schema_dir: Optional[str] = None, ttl: int = _DEFAULT_TTL):
        self._schema_dir = schema_dir or self._default_schema_dir()
        self._ttl = ttl
        self._config: Optional[Dict[str, Any]] = None
        self._config_time: float = 0
        self._lock = Lock()
        self._load_failed = False  # 标记加载失败, 避免重复尝试

    @staticmethod
    def _default_schema_dir() -> str:
        """默认 schema 目录: meta/schemas"""
        current = os.path.abspath(__file__)
        for _ in range(2):
            current = os.path.dirname(current)
        return os.path.join(current, 'schemas')

    def _load_config(self) -> Optional[Dict[str, Any]]:
        """从 YAML 加载映射配置（带缓存）"""
        now = time.time()
        with self._lock:
            if self._config is not None and (now - self._config_time) < self._ttl:
                return self._config

            yaml_path = os.path.join(self._schema_dir, 'dimension_object_mapping.yaml')
            if not os.path.exists(yaml_path):
                logger.warning(
                    f'[DimensionObjectMappingLoader] config not found: {yaml_path}'
                )
                self._load_failed = True
                return None

            try:
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    raw = yaml.safe_load(f) or {}
                self._config = {
                    'mappings': self._index_mappings(
                        raw.get('dimension_object_mappings', [])
                    ),
                    'priority': raw.get('dimension_priority', {}),
                    'combination_policy': raw.get('combination_policy', {
                        'scope_combination': 'AND',
                        'owner_always_visible': True,
                    }),
                }
                self._config_time = now
                self._load_failed = False
                logger.info(
                    f'[DimensionObjectMappingLoader] loaded '
                    f'{len(self._config["mappings"])} dimension mappings'
                )
                return self._config
            except Exception as e:
                logger.error(
                    f'[DimensionObjectMappingLoader] load failed: {e}',
                    exc_info=True,
                )
                self._load_failed = True
                return None

    @staticmethod
    def _index_mappings(
        mappings_list: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """把 mappings list 转成 {dimension_code: mapping} dict"""
        result = {}
        for m in mappings_list:
            code = m.get('dimension_code')
            if not code:
                continue
            result[code] = m
        return result

    # ────────────────────────────────────────
    # 查询接口
    # ────────────────────────────────────────

    def is_loaded(self) -> bool:
        """检查配置是否成功加载"""
        return self._load_config() is not None

    def get_mapping(self, dimension_code: str) -> Optional[Dict[str, Any]]:
        """获取某个维度的完整映射配置"""
        cfg = self._load_config()
        if not cfg:
            return None
        return cfg['mappings'].get(dimension_code)

    def get_dimension_type(self, dimension_code: str) -> Optional[str]:
        """获取维度类型: business | generic | None (未知维度)"""
        m = self.get_mapping(dimension_code)
        if not m:
            return None
        return m.get('dimension_type')

    def get_applies_to(self, dimension_code: str) -> List[Dict[str, Any]]:
        """获取该维度适用于哪些 BO 的哪些字段

        Returns:
            list of {bo, field, filter_type} dicts
        """
        m = self.get_mapping(dimension_code)
        if not m:
            return []
        return m.get('applies_to', [])

    def get_value_table(self, dimension_code: str) -> Optional[str]:
        """获取通用维度的值表名（generic 类型才有）"""
        m = self.get_mapping(dimension_code)
        if not m:
            return None
        return m.get('value_table')

    def get_value_field(self, dimension_code: str) -> str:
        """获取维度值表的 ID 字段，默认 'id'"""
        m = self.get_mapping(dimension_code)
        if not m:
            return 'id'
        return m.get('value_field', 'id')

    def get_priority(self, dimension_code: str) -> int:
        """获取维度优先级（数值越小越高）"""
        cfg = self._load_config()
        if not cfg:
            return 100  # 未知维度最低优先级
        return cfg.get('priority', {}).get(dimension_code, 100)

    def get_combination_policy(self) -> Dict[str, Any]:
        """获取维度与 visibility/owner 的组合策略"""
        cfg = self._load_config()
        if not cfg:
            # 默认: AND 组合 + owner 例外
            return {'scope_combination': 'AND', 'owner_always_visible': True}
        return cfg.get('combination_policy', {
            'scope_combination': 'AND',
            'owner_always_visible': True,
        })

    def get_field_for_bo(
        self, dimension_code: str, bo_id: str
    ) -> Optional[Dict[str, Any]]:
        """查询某个 BO 是否承载了该维度

        Args:
            dimension_code: 维度标识
            bo_id: 业务对象标识

        Returns:
            {bo, field, filter_type} 或 None (该 BO 不承载该维度)
        """
        for entry in self.get_applies_to(dimension_code):
            if entry.get('bo') == bo_id:
                return entry
        return None

    def reload(self) -> None:
        """强制重载配置（用于运行时 reload）"""
        with self._lock:
            self._config = None
            self._config_time = 0
            self._load_failed = False


# ────────────────────────────────────────
# 单例模式
# ────────────────────────────────────────

_loader_instance: Optional[DimensionObjectMappingLoader] = None


def get_dimension_object_mapping_loader() -> DimensionObjectMappingLoader:
    """获取全局单例"""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = DimensionObjectMappingLoader()
    return _loader_instance