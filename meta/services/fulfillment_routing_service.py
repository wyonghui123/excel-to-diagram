# -*- coding: utf-8 -*-
"""履约路由判定 —— 批次 4a：匹配键 → `workflow_key`（不做通用规则引擎）。

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.18.3
      docs/superpowers/specs/2026-10-29-so-wave3/tasks.md T4.5

口径:
  · 匹配键 = `item_type` / `procurement_type` / `delivery_mode` / `site_id`；
    规则字段为 NULL = 通配（不参与匹配）。
  · 按 `priority ASC, id ASC` 取第一条命中（数字越小越优先，表规则可覆盖种子）。
  · 全部不命中时回落到 `is_default=1` 的规则（未命中走默认）。
  · 无任何 enabled 规则 / 无默认规则可用 → `FulfillmentRoutingError('DEFAULT_ROUTING_MISS')`。
  · `is_field_service` 仅用于补全空白 `delivery_mode`（True → onsite），
    规则表无该列，不参与匹配。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROUTING_RULE_TABLE = 'fulfillment_routing_rules'

WORKFLOW_STOCK = 'wf-fulfill-stock'
WORKFLOW_MTO = 'wf-fulfill-mto'
WORKFLOW_SERVICE = 'wf-fulfill-service'
WORKFLOW_MIXED = 'wf-fulfilled-mixed'

MATCH_KEYS = ('item_type', 'procurement_type', 'delivery_mode', 'site_id')

ROUTING_MISS = 'DEFAULT_ROUTING_MISS'


class FulfillmentRoutingError(ValueError):
    """路由判定失败。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = '',
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule
        self.details = details or {}


def _blank(value: Any) -> bool:
    return value is None or value == ''


class FulfillmentRoutingService:
    """按 `fulfillment_routing_rules` 判定编排模板键。"""

    def __init__(self, data_source):
        self.ds = data_source

    def resolve_workflow_key(self, payload: Optional[Dict[str, Any]] = None,
                             **kwargs: Any) -> Dict[str, Any]:
        """返回 `{'workflow_key', 'rule_id', 'priority', 'matched', 'inputs'}`。"""
        inputs = dict(payload or {})
        inputs.update(kwargs)
        inputs = self._normalize_inputs(inputs)

        rules = self._load_rules()
        if not rules:
            raise FulfillmentRoutingError(
                '未配置任何启用的履约路由规则', rule=ROUTING_MISS,
                details={'inputs': inputs})

        for rule in rules:
            if self._matches(rule, inputs):
                return self._hit(rule, inputs)

        defaults = [rule for rule in rules if bool(rule.get('is_default'))]
        if defaults:
            return self._hit(defaults[0], inputs)

        raise FulfillmentRoutingError(
            '无路由规则命中且无默认规则', rule=ROUTING_MISS,
            details={'inputs': inputs,
                     'rules': [rule.get('workflow_key') for rule in rules]})

    # -------------------------------------------------------------- 内部

    @staticmethod
    def _normalize_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {key: inputs.get(key) for key in MATCH_KEYS}
        if _blank(normalized.get('delivery_mode')) \
                and bool(inputs.get('is_field_service')):
            normalized['delivery_mode'] = 'onsite'
        return normalized

    def _load_rules(self) -> List[Dict[str, Any]]:
        try:
            return self.ds.query(
                'SELECT id, priority, item_type, procurement_type, delivery_mode, '
                'site_id, workflow_key, is_default, enabled, remark FROM %s '
                'WHERE enabled = 1 ORDER BY priority ASC, id ASC'
                % ROUTING_RULE_TABLE)
        except Exception as e:  # 表未就绪 → 视为未配置（触发 MISS）
            logger.warning('[fulfillment_routing] 读取路由规则失败: %s', e)
            return []

    @staticmethod
    def _matches(rule: Dict[str, Any], inputs: Dict[str, Any]) -> bool:
        for key in MATCH_KEYS:
            expected = rule.get(key)
            if _blank(expected):
                continue  # NULL = 通配
            if _blank(inputs.get(key)):
                return False
            if str(expected) != str(inputs.get(key)):
                return False
        return True

    @staticmethod
    def _hit(rule: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'workflow_key': rule.get('workflow_key'),
            'rule_id': rule.get('id'),
            'priority': rule.get('priority'),
            'matched': 'default' if bool(rule.get('is_default')) else 'rule',
            'inputs': inputs,
        }
