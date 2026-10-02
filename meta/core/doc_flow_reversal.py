# -*- coding: utf-8 -*-
"""[单据流 Phase 2] DOC_FLOW 冲销引擎三档（契约 = 数量语义主文档 §7）

三档模式（§7.1，SAP VBFA 对照见 §7.7）::

    A 全冲销   reverse_edge:  原边 status: active → reversed（边不删，视图不计）
    B 部分冲销 counter_edge:  反向新边（原边 target → 新退货单），quantity=退货量
    C 数量调整 red_ink_edge:  同方向红字新边，quantity_sign='red'（视图按 sign 减）

共同纪律:
- 单事务 + fail-closed；重复调用 = 幂等重放（零新增 / 零状态变更）
- **业务权威锚机器强制**（§7 + task-model 边界铁律 3）：B/C 必填 ref_id
  （退货单 / 红字单 ID），锚写入边 derive_key（'count:' / 'red:' 前缀），
  E7 对账可据此回查"哪张业务单据退货/调整了哪条边"
- **红字边身份**：rule_id 追加 ``#red:{红字单id}`` 锚定后缀——绕开 7 元组
  唯一键 uq_doc_flow_idem 的契约冲突（同源同目标同规则物理插不进第二行）。
  后缀使 7 元组本身即红字边业务身份：同单重放天然幂等、异单多笔调整
  天然支持。注意：**勿按 rule_id 相等性回查规则注册表**（注册表只有基名，
  后缀仅为边身份的一部分）。
- 聚合口径 = SUM(active normal) − SUM(active red)（§7.6），reversed 不计；
  A 档反转时**级联反转其 active 红字子边**（否则"0 − 红字"聚合为负）
- A 档 reversed_by 仅记日志：边表定稿 17 列无冲销审计位，权威锚 = 业务红字单

对应方案: docs/superpowers/specs/2026-09-08-doc-flow-quantity-semantics.md §7
          docs/superpowers/specs/2026-09-07-task-model-design.md §12.1（E6）
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.doc_flow_derive_engine import (
    DOC_FLOW_EDGES_TABLE, DocFlowDeriveError, _QTY_EPSILON, _find_edge_by_key,
    _num, derive,
)

logger = logging.getLogger(__name__)


@dataclass
class ReversalResult:
    """冲销操作结果（三档统一返回形态）。

    edge_id: A=被反转的原边；B/C=新建的反向边 / 红字边
    kind: 'reversed' / 'counter' / 'red_ink'
    replay: True = 幂等重放（零新增 / 零状态变更）
    cascaded_edges: A 档级联反转的红字子边 ID 列表
    """

    edge_id: str
    kind: str
    replay: bool = False
    cascaded_edges: List[str] = field(default_factory=list)


def _red_prefix(orig_edge_id: str) -> str:
    """红字锚前缀（derive_key = 前缀 + 红字单 ID）。"""
    return "red:{0}:".format(orig_edge_id)


def _counter_prefix(orig_edge_id: str) -> str:
    """反向边锚前缀（derive_key = 前缀 + 退货单 ID）。"""
    return "count:{0}:".format(orig_edge_id)


def _read_edge(app_ds, edge_id: str) -> Dict[str, Any]:
    """读边行；不存在 → EDGE_NOT_FOUND（fail-closed）。"""
    cols = ("id", "source_bo", "source_id", "source_item",
            "target_bo", "target_id", "target_item", "quantity",
            "quantity_sign", "rule_id", "status", "pool", "unit",
            "currency", "derive_key")
    rows = app_ds.execute(
        "SELECT {0} FROM doc_flow_edges WHERE id=?".format(", ".join(cols)),
        (edge_id,),
    ).fetchall()
    if not rows:
        raise DocFlowDeriveError(
            "EDGE_NOT_FOUND", "边不存在: {0}".format(edge_id)
        )
    return dict(zip(cols, rows[0]))


def _find_edge_by_derive_key(app_ds, derive_key: str) -> Optional[str]:
    rows = app_ds.execute(
        "SELECT id FROM doc_flow_edges WHERE derive_key=?", (derive_key,),
    ).fetchall()
    return rows[0][0] if rows else None


def _active_sum_by_prefix(app_ds, prefix: str, sign: str) -> float:
    """锚定前缀（derive_key）的 active 边数量合计（B/C 档上限守卫用）。"""
    rows = app_ds.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM doc_flow_edges"
        " WHERE quantity_sign=? AND status='active' AND substr(derive_key, 1, ?)=?",
        (sign, len(prefix), prefix),
    ).fetchall()
    return _num(rows[0][0]) if rows else 0.0


def reverse_edge(app_ds, edge_id: str, *,
                 reversed_by: str = "") -> ReversalResult:
    """A 档：全冲销——原边 status active → reversed（边保留，视图不计）。

    级联：该边名下（derive_key 'red:' 前缀锚定）的 active 红字子边在同一
    事务内一并置 reversed——防止"原边 0 − 红字"的负聚合（§7.6）。

    幂等：已 reversed 的边重复调用 → replay=True（零变更）。

    Args:
        edge_id: 目标边 ID（任何 active 边；红字边也可反转 = 撤销误调整）
        reversed_by: 执行者（仅记日志；权威锚 = 业务红字单，见模块 docstring）
    """
    with app_ds.transaction():
        edge = _read_edge(app_ds, edge_id)
        if edge["status"] == "reversed":
            return ReversalResult(edge_id=edge_id, kind="reversed", replay=True)
        if edge["status"] != "active":
            raise DocFlowDeriveError(
                "EDGE_STATUS_UNKNOWN",
                "边状态异常（拒绝翻转）: {0} status={1}".format(
                    edge_id, edge["status"]),
            )

        cascaded: List[str] = []
        prefix = _red_prefix(edge_id)
        children = app_ds.execute(
            "SELECT id FROM doc_flow_edges"
            " WHERE quantity_sign='red' AND status='active'"
            " AND substr(derive_key, 1, ?)=?",
            (len(prefix), prefix),
        ).fetchall()
        for (child_id,) in children:
            cursor = app_ds.execute(
                "UPDATE doc_flow_edges SET status='reversed'"
                " WHERE id=? AND status='active'",
                (child_id,),
            )
            if cursor.rowcount != 1:
                raise DocFlowDeriveError(
                    "REVERSE_ROWCOUNT_MISMATCH",
                    "级联反转未命中唯一行: {0}".format(child_id),
                )
            cascaded.append(child_id)

        cursor = app_ds.execute(
            "UPDATE doc_flow_edges SET status='reversed'"
            " WHERE id=? AND status='active'",
            (edge_id,),
        )
        if cursor.rowcount != 1:
            raise DocFlowDeriveError(
                "REVERSE_ROWCOUNT_MISMATCH",
                "反转未命中唯一行: {0}".format(edge_id),
            )
        if reversed_by:
            logger.info("[DocFlow] 边 %s 被 %s 反转（级联红字 %d 条）",
                        edge_id, reversed_by, len(cascaded))
        return ReversalResult(edge_id=edge_id, kind="reversed",
                              replay=False, cascaded_edges=cascaded)


def red_ink_edge(app_ds, orig_edge_id: str, *, quantity: float, ref_id: str,
                 derived_by: str = "") -> ReversalResult:
    """C 档：数量调整——同方向红字新边（quantity_sign='red'，status=active）。

    参数:
        quantity: 调整量（>0；聚合按 −quantity 计，§7.4）
        ref_id: 红字单 ID（必填，业务权威锚；同 ref 重放 = 幂等）
    守卫:
        原边须 active 且 quantity_sign='normal'（RED_ORIG_NOT_ACTIVE_NORMAL）；
        Σ(本原边 active 红字) + 本次 ≤ 原边 quantity（RED_OVER_ORIGINAL）。
    """
    qty = _num(quantity)
    if not ref_id:
        raise DocFlowDeriveError(
            "REF_ID_REQUIRED",
            "红字边必须携带红字单 ID（ref_id，业务权威锚）",
        )
    if qty <= 0:
        raise DocFlowDeriveError(
            "INVALID_QUANTITY",
            "红字数量必须 > 0（同方向新增请走 derive），实际: {0}".format(quantity),
        )

    now = datetime.now().isoformat(timespec="seconds")
    with app_ds.transaction():
        orig = _read_edge(app_ds, orig_edge_id)

        # 幂等身份 = 7 元组（rule_id 含 #red:{ref} 锚定后缀）
        red_rule_id = "{0}#red:{1}".format(orig["rule_id"], ref_id)
        key = (orig["source_bo"], orig["source_id"], orig["source_item"],
               orig["target_bo"], orig["target_id"], orig["target_item"],
               red_rule_id)
        existing = _find_edge_by_key(app_ds, key)
        if existing:
            return ReversalResult(edge_id=existing, kind="red_ink", replay=True)

        if orig["status"] != "active" or orig["quantity_sign"] != "normal":
            raise DocFlowDeriveError(
                "RED_ORIG_NOT_ACTIVE_NORMAL",
                "红字仅可挂 active 正向边: {0} status={1} sign={2}".format(
                    orig_edge_id, orig["status"], orig["quantity_sign"]),
            )
        orig_qty = _num(orig["quantity"])
        red_total = _active_sum_by_prefix(
            app_ds, _red_prefix(orig_edge_id), "red"
        )
        if red_total + qty > orig_qty + _QTY_EPSILON:
            raise DocFlowDeriveError(
                "RED_OVER_ORIGINAL",
                "红字合计不得超过原边数量: 原边={0}, 已有红字={1}, 本次={2}".format(
                    orig_qty, red_total, qty),
            )

        edge_id = uuid.uuid4().hex
        try:
            app_ds.insert(DOC_FLOW_EDGES_TABLE, {
                "id": edge_id,
                "source_bo": orig["source_bo"],
                "source_id": str(orig["source_id"]),
                "source_item": orig["source_item"],
                "target_bo": orig["target_bo"],
                "target_id": str(orig["target_id"]),
                "target_item": orig["target_item"],
                "quantity": qty,
                "amount": 0,
                "currency": str(orig["currency"] or ""),
                "unit": str(orig["unit"] or ""),
                "quantity_sign": "red",
                "rule_id": red_rule_id,
                "derived_at": now,
                "derived_by": derived_by,
                "status": "active",
                "pool": orig["pool"],
                "source_instance_id": "",
                "target_instance_id": "",
                "derive_key": _red_prefix(orig_edge_id) + ref_id,
            })
        except Exception as e:  # noqa: BLE001 - 唯一索引冲突 → 幂等重放兜底
            existing = _find_edge_by_key(app_ds, key)
            if existing:
                logger.warning("[DocFlow] 红字边冲突但命中既有边（并发重放）: %s", e)
                return ReversalResult(edge_id=existing, kind="red_ink",
                                      replay=True)
            raise
        return ReversalResult(edge_id=edge_id, kind="red_ink", replay=False)


def counter_edge(app_ds, platform_ds, orig_edge_id: str, *,
                 return_rule_id: str, quantity: float, ref_id: str,
                 target_data: Optional[Dict[str, Any]] = None,
                 derived_by: str = "") -> ReversalResult:
    """B 档：部分冲销——以原边 target 三元组为源，走既有 derive 建反向边。

    退货单等目标单据由目标映射链正常落库（create/attach 语义同 derive）；
    "退货不冲订单行"（§7.3）：新边从交货侧起算，正向聚合 ≠ 回冲原边。

    参数:
        return_rule_id: 回流规则（source_bo 必须 = 原边 target_bo）
        quantity: 退货量（>0）
        ref_id: 退货单 ID（必填，业务权威锚；同 ref 重放 = 幂等）
    守卫:
        原边须 active 且 quantity_sign='normal'（COUNTER_ORIG_NOT_ACTIVE）；
        规则源 BO 错配 → COUNTER_RULE_MISMATCH；
        Σ(本原边 active 退货) + 本次 ≤ 原边 quantity（COUNTER_OVER_RETURN）；
        derive 自身的 Σ 校验（退货池 ≤ 交货行数量）照常生效。
    """
    qty = _num(quantity)
    if not ref_id:
        raise DocFlowDeriveError(
            "REF_ID_REQUIRED",
            "反向边必须携带退货单 ID（ref_id，业务权威锚）",
        )
    if qty <= 0:
        raise DocFlowDeriveError(
            "INVALID_QUANTITY",
            "退货数量必须 > 0（正向新增请走 derive），实际: {0}".format(quantity),
        )

    from meta.core.doc_flow_rule_store import get_rule
    rule = get_rule(platform_ds, return_rule_id)
    if rule is None:
        raise DocFlowDeriveError(
            "RULE_NOT_FOUND", "规则不存在: {0}".format(return_rule_id)
        )

    orig = _read_edge(app_ds, orig_edge_id)

    # 幂等：同退货单（ref）已落边 → 重放，不再校验后续守卫
    derive_key = _counter_prefix(orig_edge_id) + ref_id
    existing = _find_edge_by_derive_key(app_ds, derive_key)
    if existing:
        return ReversalResult(edge_id=existing, kind="counter", replay=True)

    if orig["status"] != "active" or orig["quantity_sign"] != "normal":
        raise DocFlowDeriveError(
            "COUNTER_ORIG_NOT_ACTIVE",
            "反向边仅可挂 active 正向边: {0} status={1} sign={2}".format(
                orig_edge_id, orig["status"], orig["quantity_sign"]),
        )
    if rule["source_bo"] != orig["target_bo"]:
        raise DocFlowDeriveError(
            "COUNTER_RULE_MISMATCH",
            "回流规则源 BO 必须等于原边目标 BO: 规则={0} 原边目标={1}".format(
                rule["source_bo"], orig["target_bo"]),
        )
    returned = _active_sum_by_prefix(
        app_ds, _counter_prefix(orig_edge_id), "normal"
    )
    if returned + qty > _num(orig["quantity"]) + _QTY_EPSILON:
        raise DocFlowDeriveError(
            "COUNTER_OVER_RETURN",
            "退货合计不得超过原边数量: 原边={0}, 已退={1}, 本次={2}".format(
                _num(orig["quantity"]), returned, qty),
        )

    result = derive(
        app_ds, platform_ds, return_rule_id,
        source_id=orig["target_id"], source_item=str(orig["target_item"] or ""),
        quantity=qty, target_data=dict(target_data or {}),
        derived_by=derived_by, derive_key=derive_key,
    )
    return ReversalResult(edge_id=result.edge_id, kind="counter",
                          replay=result.replay)