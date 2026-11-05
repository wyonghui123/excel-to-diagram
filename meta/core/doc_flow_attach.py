# -*- coding: utf-8 -*-
"""DOC_FLOW attach 模式写边工具（阶段 2 存量链路共用）

口径:
  · 只挂既有下游单据 / 库存事务，不新建业务行（target_data 必带 id）；
  · 未启用（规则表 / 边表缺失、规则未注册）或派生失败时降级为告警，
    不阻断存量业务链路；
  · 重复调用由派生引擎的 7 元组幂等兜底（同源同目标同规则零新增）。
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _resolve_platform_ds(app_ds, platform_ds=None):
    """平台库优先；未配置时回落应用库（单库部署口径）。"""
    if platform_ds is not None:
        return platform_ds
    try:
        from meta.core.datasource import get_platform_data_source
        return get_platform_data_source() or app_ds
    except Exception:  # noqa: BLE001 - 平台库未配置时按单库处理
        return app_ds


def attach_edge(app_ds, platform_ds, rule_id: str, source_id: Any,
                target_id: Any, quantity: Any, *,
                target_item: str = '', unit: str = '',
                amount: Any = 0, derived_by: str = '') -> bool:
    """以 attach 模式写一条转单事实边。

    Returns:
        True = 边已写入或幂等重放；False = 未启用 / 规则缺失 / 派生失败（已告警）。
    """
    try:
        qty = float(quantity or 0)
    except (TypeError, ValueError):
        logger.warning('[doc_flow_attach] 数量非法，跳过转单边 %s: %r',
                       rule_id, quantity)
        return False
    if qty <= 0 or source_id in (None, '') or target_id in (None, ''):
        return False

    platform_ds = _resolve_platform_ds(app_ds, platform_ds)
    try:
        from meta.core.doc_flow_derive_engine import derive
        from meta.core.doc_flow_rule_store import get_rule
        rule = get_rule(platform_ds, rule_id)
    except Exception as exc:  # noqa: BLE001 - 规则表不可读时保持业务可用
        logger.warning('[doc_flow_attach] 规则表不可读，跳过 %s: %s', rule_id, exc)
        return False
    if rule is None:
        logger.warning('[doc_flow_attach] 规则 %s 未注册，跳过转单边', rule_id)
        return False

    try:
        derive(
            app_ds, platform_ds, rule_id, source_id,
            quantity=qty,
            target_data={
                'id': target_id,
                'item': str(target_item or ''),
                'amount': amount or 0,
                'unit': str(unit or ''),
            },
            derived_by=derived_by,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - 降级不阻断存量链路
        logger.warning('[doc_flow_attach] 派生失败 %s source=%s target=%s: %s',
                       rule_id, source_id, target_id, exc)
        return False


def reverse_edges_by_source(app_ds, rule_id: str, source_bo: str,
                            source_id: Any, *, ref_id: Any,
                            derived_by: str = '') -> int:
    """整体冲销某源行在指定规则下的 active 正向边。

    每条边先写红字边（``quantity_sign='red'``，业务锚 = 红字单 ``ref_id``），
    再把原边置 ``reversed``（级联反转其红字子边，聚合归零）。
    与 ``attach_edge`` 同口径：边表缺失 / 单边冲销失败仅告警，不阻断业务红冲。

    Returns:
        成功冲销的边数；未启用或全部失败时返回 0。
    """
    if source_id in (None, '') or ref_id in (None, ''):
        return 0
    try:
        from meta.core.doc_flow_reversal import red_ink_edge, reverse_edge
    except Exception as exc:  # pragma: no cover - 核心模块缺失时保持业务可用
        logger.warning('[doc_flow_attach] 冲销引擎不可用，跳过 %s: %s',
                       rule_id, exc)
        return 0

    try:
        rows = app_ds.query(
            'SELECT id, quantity FROM doc_flow_edges WHERE rule_id = ? '
            'AND source_bo = ? AND source_id = ? AND status = ? '
            'AND quantity_sign = ?',
            [rule_id, source_bo, str(source_id), 'active', 'normal'])
    except Exception as exc:  # noqa: BLE001 - 边表缺失时不影响红冲
        logger.warning('[doc_flow_attach] 边表不可读，跳过冲销 %s: %s',
                       rule_id, exc)
        return 0

    reversed_count = 0
    for row in rows:
        edge_id = row.get('id')
        try:
            red_ink_edge(
                app_ds, edge_id,
                quantity=float(row.get('quantity') or 0),
                ref_id=str(ref_id), derived_by=derived_by)
            reverse_edge(app_ds, edge_id, reversed_by=derived_by)
            reversed_count += 1
        except Exception as exc:  # noqa: BLE001 - 单边失败不影响其他边与红冲
            logger.warning('[doc_flow_attach] 冲销失败 edge=%s: %s',
                           edge_id, exc)
    return reversed_count
