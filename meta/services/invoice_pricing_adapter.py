# -*- coding: utf-8 -*-
"""销售发票定价模式适配器 —— 控制参数解析 + 复制策略（对标 SAP 复制控制）。

依据:
  docs/specs/sales-invoice-pricing-spec-2026-11-10.md §3 FR-005
  §9.3.2（枚举与控制参数）/ NFR-005（禁止服务内写模式字面量分支）

三层一致:
  · 枚举字典 `enum_types.billing_pricing_mode` —— 值域真源
  · 控制参数 `control_parameter_def/values` —— 配置真源（类型级 / 组织级）
  · `customer_invoices.billing_pricing_mode` —— 建单快照（只读）

本模块是「配置 → 快照」的唯一解析入口：业务服务不得自行比较模式字符串，
只调用 `resolve_billing_pricing_mode()` 取码、`resolve_copy_strategy()` 取动作。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PARAM_DEF_TABLE = 'control_parameter_defs'
PARAM_VALUE_TABLE = 'control_parameter_values'
PARAM_CODE = 'billing_pricing_mode'

#: 平台默认（与 v244 控制参数 default_value 一致）
DEFAULT_MODE = 'copy_frozen_redetermine_tax'
#: 历史发票回填值（is_system，不可手工选择）
LEGACY_MODE = 'legacy'

#: 模式 → 复制策略；键集合必须与枚举 `billing_pricing_mode` 值域一致
COPY_STRATEGIES = {
    'copy_frozen': {
        'sap_control': 'D', 'copy_net': True, 'copy_tax': True,
        'reprice': 'none', 'scale_update': False,
    },
    'copy_scale_update': {
        'sap_control': 'A', 'copy_net': True, 'copy_tax': True,
        'reprice': 'none', 'scale_update': True,
    },
    'copy_reprice_all': {
        'sap_control': 'B', 'copy_net': False, 'copy_tax': False,
        'reprice': 'all', 'scale_update': False,
    },
    'copy_manual_reprice_rest': {
        'sap_control': 'C', 'copy_net': False, 'copy_tax': False,
        'reprice': 'except_manual', 'scale_update': False,
    },
    'copy_frozen_redetermine_tax': {
        'sap_control': 'G', 'copy_net': True, 'copy_tax': False,
        'reprice': 'none', 'scale_update': False,
    },
    'legacy': {
        'sap_control': None, 'copy_net': True, 'copy_tax': True,
        'reprice': 'none', 'scale_update': False,
    },
}


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _table_exists(ds, table: str) -> bool:
    try:
        return bool(ds.table_exists(table))
    except Exception as exc:  # 数据源不带 table_exists 时按缺失处理
        logger.debug('[invoice_pricing] 检查表 %s 失败: %s', table, exc)
        return False


def _query(ds, sql: str, params: list) -> list:
    try:
        return list(ds.query(sql, params) or [])
    except Exception as exc:
        logger.debug('[invoice_pricing] 查询失败（按未配置处理）: %s', exc)
        return []


def resolve_billing_pricing_mode(ds, document_type_id: Any = None,
                                 org_id: Any = None,
                                 default: Optional[str] = None) -> str:
    """解析建单时使用的定价模式码。

    优先级（高 → 低）：
      1. 组织 + 发票类型（`specificity_rank` 越大越优先）
      2. 仅组织
      3. 仅发票类型（v244 为 SINV/SCR/SDN/SRV 播种，rank=1）
      4. 仅 `specificity_rank=0` 的全局取值
      5. 控制参数 `default_value`
      6. 平台默认 `DEFAULT_MODE`

    未配置 / 元数据表缺失 / 取值不在值域内 → 回落，不抛错（FR-005 验收）。
    """
    fallback = _clean(default) or DEFAULT_MODE
    if not _table_exists(ds, PARAM_DEF_TABLE):
        return fallback

    rows = _query(
        ds,
        'SELECT id, default_value FROM %s WHERE code = ? AND status = ?'
        % PARAM_DEF_TABLE, [PARAM_CODE, 'active'])
    if not rows:
        return fallback
    param_id = rows[0].get('id')
    fallback = _clean(rows[0].get('default_value')) or fallback

    if not _table_exists(ds, PARAM_VALUE_TABLE):
        return fallback

    values = _query(
        ds,
        'SELECT org_id, document_type_id, specificity_rank, value '
        'FROM %s WHERE control_parameter_id = ? AND status = ?'
        % PARAM_VALUE_TABLE, [param_id, 'active'])

    best_value, best_score = None, -1
    for row in values:
        row_org = row.get('org_id')
        row_type = row.get('document_type_id')
        # 组织级取值只对同一组织生效；无组织上下文时不命中组织级配置
        if row_org is not None and (
                org_id is None or str(row_org) != str(org_id)):
            continue
        if row_type is not None and str(row_type) != str(document_type_id or ''):
            continue
        value = _clean(row.get('value'))
        if value not in COPY_STRATEGIES:
            logger.warning('[invoice_pricing] 忽略未知定价模式取值 %s', value)
            continue
        score = int(row.get('specificity_rank') or 0) * 10
        if row_org is not None:
            score += 2
        if row_type is not None:
            score += 1
        if score > best_score:
            best_value, best_score = value, score
    return best_value or fallback


def validate_pricing_mode(mode: Any) -> str:
    """校验并存快照：未知取值回落平台默认（防止脏配置写入单据）。"""
    value = _clean(mode)
    if not value or value not in COPY_STRATEGIES:
        if value:
            logger.warning('[invoice_pricing] 非法定价模式快照 %s，回落默认', value)
        return DEFAULT_MODE
    return value


def resolve_copy_strategy(mode: Any) -> Dict[str, Any]:
    """返回模式的复制动作描述（只读副本，调用方不得改写常量）。"""
    value = _clean(mode)
    strategy = COPY_STRATEGIES.get(value)
    if strategy is None:
        logger.warning('[invoice_pricing] 未知定价模式 %s，按默认策略处理', value)
        strategy = COPY_STRATEGIES[DEFAULT_MODE]
    return dict(strategy)