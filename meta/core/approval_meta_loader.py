# -*- coding: utf-8 -*-
"""审批对象注册元数据加载（Rule Convergence M2 / FR-005）

唯一真源 = 各 BO YAML 顶层 ``approval`` 声明：

    approval:
      table: purchase_orders
      amount_fields: [gross_amount, net_amount, total_amount, amount]

审批策略（门限 / 审批人）仍由 DB ``approval_policy`` 维护，本模块不读 DB。
registry 已加载时读 MetaObject；未加载时直读同名 schema 文件。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

from meta.core import yaml_compat as yaml

logger = logging.getLogger(__name__)

_SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')

#: 旧 ``_AMOUNT_FIELDS`` 的唯一默认副本；对象未声明 amount_fields 时使用
DEFAULT_AMOUNT_FIELDS: Tuple[str, ...] = (
    'gross_amount', 'net_amount', 'total_amount', 'amount')

_cache: Dict[str, Dict[str, Any]] = {}


def _raw_declaration(object_type: str) -> Optional[Dict[str, Any]]:
    from meta.core.models import registry

    meta_obj = registry.get(object_type)
    if meta_obj is not None:
        return dict(getattr(meta_obj, 'approval', None) or {})

    path = os.path.join(_SCHEMA_DIR, '%s.yaml' % object_type)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = yaml.safe_load(handle) or {}
    except Exception as exc:  # noqa: BLE001 - 读取失败按未声明处理
        logger.warning('[approval_meta] 读取 %s 失败: %s', path, exc)
        return None
    return dict(data.get('approval') or {})


def get_approval_meta(object_type: str) -> Dict[str, Any]:
    """返回 ``{'table': str, 'amount_fields': tuple}``；未声明时 table 为空串。"""
    if object_type in _cache:
        return _cache[object_type]

    raw = _raw_declaration(object_type) or {}
    table = str(raw.get('table') or '')
    # 显式 amount_fields: [] 表示该对象不参与金额分段（恒 0.0），
    # 只有完全未声明时才回落到默认优先级。
    if 'amount_fields' in raw:
        amount_fields = raw.get('amount_fields') or []
    else:
        amount_fields = list(DEFAULT_AMOUNT_FIELDS)
    meta = {
        'table': table,
        'amount_fields': tuple(str(item) for item in amount_fields),
    }
    _cache[object_type] = meta
    return meta


def reload() -> None:
    """清空进程内缓存（测试 / 热加载用）。"""
    _cache.clear()
