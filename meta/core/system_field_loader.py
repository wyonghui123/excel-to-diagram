# -*- coding: utf-8 -*-
"""系统字段清单读取入口（SSOT 访问器）。

[Rule Convergence M1 2026-11-07] 系统字段此前硬编码在
`meta/services/field_policy_engine.py::FieldPolicyEngine.SYSTEM_FIELDS`。
现改为读取 `meta/schemas/shared_properties.yaml#system_fields`。

fail-safe：声明缺失或解析失败时回落到迁移前的 14 项并告警，
避免启动期因声明问题导致字段策略全部失效。
"""

import logging
import os
from typing import FrozenSet

from meta.core import yaml_compat as yaml

logger = logging.getLogger(__name__)

_SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
_YAML_PATH = os.path.join(_SCHEMA_DIR, 'shared_properties.yaml')

# 迁移前基线（fail-safe 兜底，不是业务真源）
_FALLBACK_SYSTEM_FIELDS = frozenset({
    'created_at', 'updated_at', 'created_by', 'updated_by',
    'created_date', 'updated_date', 'created_user', 'updated_user',
    'is_system', 'system_flag', 'readonly',
    'id', '_id', 'tenant_id',
})

_cache = None


def get_system_fields() -> FrozenSet[str]:
    """返回系统字段集合（小写），进程内缓存。"""
    global _cache
    if _cache is not None:
        return _cache

    declared = None
    if os.path.exists(_YAML_PATH):
        try:
            with open(_YAML_PATH, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            values = data.get('system_fields')
            if isinstance(values, list) and values:
                declared = frozenset(str(v).lower() for v in values)
        except Exception as error:
            logger.warning(
                '[system_field_loader] shared_properties.yaml 解析失败: %s', error)

    if declared is None:
        logger.warning(
            '[system_field_loader] 未找到 system_fields 声明，回落 14 项基线')
        declared = _FALLBACK_SYSTEM_FIELDS

    _cache = declared
    return _cache


def reload() -> None:
    """清除进程内缓存（测试 / 热加载用）。"""
    global _cache
    _cache = None
