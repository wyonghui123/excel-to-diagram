# -*- coding: utf-8 -*-
"""审批对象注册元数据加载（Rule Convergence M2 / FR-005 / SSOT v0.3）

唯一真源 = 各 BO YAML 顶层 ``approval`` 声明：

    approval:
      table: purchase_orders
      amount_fields: [gross_amount, net_amount, total_amount, amount]
      title_prefix: 采购订单审批          # 可选，默认 "{name}审批"
      title_field: order_no              # 可选，默认空 ⇒ 标题用记录 id
      id_key: purchase_order_id          # 可选，默认 "{bo}_id"
      app_id: procurement                # 可选，默认空串
      decision_actions:                  # 可选，默认派生 {bo}.approve / {bo}.reject
        approve: purchase_order.approve
        reject: purchase_order.reject

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

#: 决策动作键（与 decision_effect.DECISIONS 同口径，必须成对）
_DECISION_KEYS: Tuple[str, ...] = ('approve', 'reject')

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


def _object_name(object_type: str) -> str:
    from meta.core.models import registry

    meta_obj = registry.get(object_type)
    return str(getattr(meta_obj, 'name', '') or object_type)


def _decision_actions(object_type: str,
                      raw: Dict[str, Any]) -> Dict[str, str]:
    """决策动作：显式声明优先，否则按 ``{bo}.approve`` / ``{bo}.reject`` 派生。

    存在性校验不在此处做——注册表装配顺序在启动期不稳定，误判会把可审批对象
    整体降级为不可审批；动作缺失由决策执行期的硬错误兜底（fail-closed 同效）。
    """
    declared = raw.get('decision_actions')
    if isinstance(declared, dict) and declared:
        actions = {key: str(declared.get(key) or '') for key in _DECISION_KEYS}
        if not all(actions.values()):
            logger.warning(
                '[approval_meta] %s: decision_actions 必须成对声明 approve/reject，'
                '按不可审批处理', object_type)
            return {}
        return actions
    return {key: '%s.%s' % (object_type, key) for key in _DECISION_KEYS}


def get_approval_meta(object_type: str) -> Dict[str, Any]:
    """返回审批元数据；未声明 ``approval.table`` 时 table 为空串（不可审批）。"""
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
        'title_prefix': str(raw.get('title_prefix')
                            or '%s审批' % _object_name(object_type)),
        'title_field': str(raw.get('title_field') or ''),
        'id_key': str(raw.get('id_key') or '%s_id' % object_type),
        'app_id': str(raw.get('app_id') or ''),
        'decision_actions': _decision_actions(object_type, raw),
    }
    _cache[object_type] = meta
    return meta


def reload() -> None:
    """清空进程内缓存（测试 / 热加载用）。"""
    _cache.clear()