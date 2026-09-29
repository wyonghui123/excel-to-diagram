# -*- coding: utf-8 -*-
"""[单据流 Phase 2] DOC_FLOW 批量派生引擎（拆合层：1:n 拆单 / n:1 合并）

调用契约（spec 2026-09-29-doc-flow-phase2-spec.md §6.1）::

    derive_batch(app_ds, platform_ds, rule_id, items,
                 head_overrides=None, derived_by="")

    items: [{"source_id": ..., "source_item": "", "quantity": ...}, ...]
           quantity 缺省 = 源行未结量（源行数量 − 同池已消耗）

统一算法（裁定 B：拆与合共用一份 split_key）::

    事务外（F5：规则与业务数据异库，规则读绝不纳入数据事务）
      0. 读规则 → status=active 校验；声明校验（split_key 字段存在、
         target_line_bo 已注册、明细行 FK 可解析）
    事务内（app_ds 单库，整批一个事务，全成/全败 —— 裁定 §6.3）
      1. 逐项预读源行（分组键 + 源数量），算默认派生量
      2. 分组：
         - 头行模式 + split_key → GROUP BY 分单键值
         - 头行模式 + 无 split_key → 每行自成一组（Phase 1 兼容）
         - 单表模式（target_line_bo 空）→ 逐项独立，无单头
      3. 逐组：建单头（= 首行分单键值 + head_overrides）→ 组内逐行 _derive_core
         （_derive_core 内部做幂等预查 + 建明细行 + 写边 + Σ 校验）
    任一失败 → 异常上抛 → 整批回滚（不留"单据半成品"）

关键裁定:
- **裁定 C**（头行 FK 三级解析）：规则 ``head_fk_field`` > 明细行字段的
  ``semantics.parent_key`` > 命名约定 ``{头BO}_id`` / ``parent_id``；
  三级皆失败 → ``HEAD_FK_NOT_FOUND``（显式报错，不静默）。
- **幂等重放**：``head_overrides`` 含 ``id`` = 挂既有单头（attach）。此时逐行
  走 (源, 单头, 规则) 宽松幂等键，整批重放 → 零新增 + ``skipped_replays`` 计数；
  不含 ``id`` = create 模式（每组建新单头，天然无重放）。
- **不用 DeepInsertEngine**：深插引擎会触发规则引擎/审计/拦截器链，与派生语义
  无关；本引擎在 ``app_ds.transaction()`` 内直写（同 Phase 1 裁定）。

对应方案: docs/superpowers/specs/2026-09-29-doc-flow-phase2-spec.md §5/§6
          docs/superpowers/specs/2026-09-29-doc-flow-phase1-spec.md §6
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from meta.core.doc_flow_derive_engine import (
    DeriveResult, DocFlowDeriveError, _consumed_in_pool, _derive_core, _num,
    _read_source_fields, _row_exists,
)

logger = logging.getLogger(__name__)

#: 头行模式下明细行指向单头的外键命名约定（裁定 C 三级解析的第 ③ 级）
_FK_NAME_CONVENTIONS = ("parent_id",)


@dataclass
class BatchDeriveResult:
    """derive_batch 执行结果（整批一个事务的汇总）。"""

    heads: List[Any] = field(default_factory=list)          # 单头 ID（单表模式 = 目标行 ID）
    total_edges: int = 0                                    # 本批新增边数
    skipped_replays: int = 0                                # 幂等命中的行数
    per_item_open_qty: List[float] = field(default_factory=list)
    results: List[DeriveResult] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 内部：头行 FK 解析 / 单头建行 / 分组
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_head_fk(rule: Dict[str, Any], line_obj, head_obj) -> str:
    """解析明细行指向单头的外键列（裁定 C 三级，返回 db_column）。

    ① 规则显式声明 ``head_fk_field``；② 明细行字段 ``semantics.parent_key``；
    ③ 命名约定 ``{头BO}_id`` / ``parent_id``。三级皆无 → HEAD_FK_NOT_FOUND。
    """
    declared = (rule.get("head_fk_field") or "").strip()
    if declared:
        f = line_obj.get_field(declared)
        if f is None:
            raise DocFlowDeriveError(
                "HEAD_FK_NOT_FOUND",
                f"明细行 BO '{line_obj.id}' 缺少规则声明的外键字段 '{declared}'"
                "（head_fk_field 声明有误）",
            )
        return f.db_column

    for f in line_obj.get_persistent_fields():
        if getattr(f.semantics, "parent_key", False):
            return f.db_column

    for cand in ("{0}_id".format(head_obj.id),) + _FK_NAME_CONVENTIONS:
        f = line_obj.get_field(cand)
        if f is not None:
            return f.db_column

    raise DocFlowDeriveError(
        "HEAD_FK_NOT_FOUND",
        "明细行 BO '{0}' 无法解析指向单头 '{1}' 的外键列："
        "请在规则声明 head_fk_field，或在明细行字段标注 semantics.parent_key，"
        "或使用命名约定 '{1}_id' / 'parent_id'".format(line_obj.id, head_obj.id),
    )


def _read_item_context(app_ds, source_obj, rule, split_key, source_id
                       ) -> Tuple[Tuple, float, Dict[str, Any]]:
    """读一项源行的 (分组键值 tuple, 源行数量, 原始值字典)。"""
    field_ids = tuple(set(split_key) | {rule["source_qty_field"]})
    vals = _read_source_fields(
        app_ds, source_obj.table_name, source_id, field_ids, source_obj
    )
    key = tuple(vals.get(fid) for fid in split_key)
    return key, _num(vals.get(rule["source_qty_field"])), vals


def _group_by_key(prepared: List[tuple]) -> List[Tuple[Tuple, List[tuple]]]:
    """按分单键值分组，保持首次出现顺序（拆单结果稳定、可预期）。"""
    buckets: "OrderedDict[Tuple, List[tuple]]" = OrderedDict()
    for entry in prepared:
        buckets.setdefault(entry[1], []).append(entry)
    return list(buckets.items())


def _create_head(app_ds, head_obj, rule, key, head_overrides, now) -> Any:
    """建单头（同事务直写）：首行分单键值（经 field_map 改名）+ head_overrides。

    分单键字段**自动**进入头映射（spec §5.2），无需在 field_map 重复声明为头字段。
    """
    row_data: Dict[str, Any] = {}
    field_map = rule.get("field_map") or {}
    for idx, src_fid in enumerate(rule.get("split_key") or []):
        tgt_fid = field_map.get(src_fid, src_fid)
        f = head_obj.get_field(tgt_fid)
        if f is not None:
            row_data[f.db_column] = key[idx]
    for fid, value in head_overrides.items():
        if fid == "id":
            continue
        f = head_obj.get_field(fid)
        if f is not None:
            row_data[f.db_column] = value
    for audit_col in ("created_at", "updated_at"):
        f = head_obj.get_field(audit_col)
        if f is not None and f.db_column not in row_data:
            row_data[f.db_column] = now
    head_id = app_ds.insert(head_obj.table_name, row_data)
    if head_id is None:
        raise DocFlowDeriveError(
            "CREATE_TARGET_FAILED", f"单头写入失败: {head_obj.table_name}"
        )
    return head_id


# ─────────────────────────────────────────────────────────────────────────────
# 对外入口
# ─────────────────────────────────────────────────────────────────────────────

def derive_batch(app_ds, platform_ds, rule_id: str, items: List[Dict[str, Any]],
                 head_overrides: Optional[Dict[str, Any]] = None,
                 derived_by: str = "") -> BatchDeriveResult:
    """批量派生（拆/合统一入口；整批一个事务，全成/全败）。

    Args:
        app_ds: 源/目标/边所在的同一应用库数据源（F5 同库前提）
        platform_ds: 平台库数据源（读 doc_flow_rule；事务之外）
        rule_id: 复制规则 ID（须 status=active）
        items: 待派生项列表 ``[{"source_id", "source_item", "quantity"}]``；
            ``quantity`` 缺省 = 源行未结量
        head_overrides: 单头静态覆盖（字段 ID → 值）；
            含 ``id`` = attach 既有单头（幂等重放），不含 = 每组建新单头
        derived_by: 派生执行者（写边 derived_by）

    Returns:
        BatchDeriveResult

    Raises:
        DocFlowDeriveError: BATCH_EMPTY / RULE_NOT_FOUND / RULE_DEPRECATED /
            BO_NOT_REGISTERED / SOURCE_QTY_FIELD_MISSING /
            SPLIT_KEY_FIELD_MISSING / TARGET_LINE_BO_MISSING / HEAD_FK_NOT_FOUND /
            SOURCE_ROW_NOT_FOUND / TARGET_ROW_NOT_FOUND / INVALID_QUANTITY /
            OVER_DERIVE（后四者由 _derive_core 逐行抛出）
    """
    from meta.core.doc_flow_rule_store import get_rule
    from meta.core.models import registry

    if not items:
        raise DocFlowDeriveError("BATCH_EMPTY", "批量派生的 items 为空")

    head_overrides = dict(head_overrides or {})

    # ── 事务外：规则 + BO 元数据 + 声明校验（F5：规则读绝不纳入数据事务）──
    rule = get_rule(platform_ds, rule_id)
    if rule is None:
        raise DocFlowDeriveError("RULE_NOT_FOUND", f"规则不存在: {rule_id}")
    if rule["status"] != "active":
        raise DocFlowDeriveError(
            "RULE_DEPRECATED",
            f"规则 '{rule_id}' 已停用（deprecated 停新不禁旧，历史边不受影响）",
        )

    source_obj = registry.get(rule["source_bo"])
    head_obj = registry.get(rule["target_bo"])
    missing_bo = [
        bo for bo, obj in ((rule["source_bo"], source_obj),
                           (rule["target_bo"], head_obj)) if obj is None
    ]
    if missing_bo:
        raise DocFlowDeriveError("BO_NOT_REGISTERED", f"BO 未注册: {missing_bo}")
    if source_obj.get_field(rule["source_qty_field"]) is None:
        raise DocFlowDeriveError(
            "SOURCE_QTY_FIELD_MISSING",
            f"源 BO '{source_obj.id}' 缺少数量字段 '{rule['source_qty_field']}'",
        )

    split_key = list(rule.get("split_key") or [])
    for fid in split_key:
        if source_obj.get_field(fid) is None:
            raise DocFlowDeriveError(
                "SPLIT_KEY_FIELD_MISSING",
                f"源 BO '{source_obj.id}' 缺少分单键字段 '{fid}'"
                "（规则的 split_key 声明有误）",
            )

    line_bo = (rule.get("target_line_bo") or "").strip()
    two_level = bool(line_bo)
    if two_level:
        line_obj = registry.get(line_bo)
        if line_obj is None:
            raise DocFlowDeriveError(
                "TARGET_LINE_BO_MISSING", f"明细行 BO 未注册: {line_bo}"
            )
        fk_column = _resolve_head_fk(rule, line_obj, head_obj)
    else:
        line_obj, fk_column = head_obj, None

    attach_head_id = head_overrides.get("id")
    now = datetime.now().isoformat(timespec="seconds")

    with app_ds.transaction():
        # ── 1. 逐项预读（分组键 + 源数量），算默认派生量 = 源行未结量 ──────
        prepared = []
        for item in items:
            source_id = item.get("source_id")
            source_item = item.get("source_item", "") or ""
            key, source_qty, _vals = _read_item_context(
                app_ds, source_obj, rule, split_key, source_id
            )
            qty = item.get("quantity")
            if qty is None:
                consumed = _consumed_in_pool(
                    app_ds, source_obj.id, source_id, source_item, rule["pool"]
                )
                qty = source_qty - consumed
            prepared.append((item, key, source_qty, _num(qty)))

        # ── 2. 分组 ───────────────────────────────────────────────────────
        if two_level and split_key:
            groups = _group_by_key(prepared)
        else:
            groups = [(None, [p]) for p in prepared]

        # ── 3. 逐组建单头 → 逐行派生 ──────────────────────────────────────
        heads: List[Any] = []
        results: List[DeriveResult] = []
        for key, group in groups:
            if two_level:
                if attach_head_id is not None:
                    head_id = attach_head_id
                    if not _row_exists(app_ds, head_obj.table_name, head_id):
                        raise DocFlowDeriveError(
                            "TARGET_ROW_NOT_FOUND",
                            f"单头不存在: {head_obj.id}.id={head_id}",
                        )
                else:
                    head_id = _create_head(
                        app_ds, head_obj, rule, key, head_overrides, now
                    )
                if head_id not in heads:
                    heads.append(head_id)
                line_target_data: Dict[str, Any] = {}
            else:
                head_id = None
                line_target_data = dict(head_overrides)

            for item, _key, _sq, qty in group:
                res = _derive_core(
                    app_ds, rule, source_obj, line_obj,
                    item.get("source_id"), item.get("source_item", "") or "",
                    qty, line_target_data, derived_by, now,
                    fk_column=fk_column,
                    fk_value=head_id,
                    edge_target_bo=head_obj.id if two_level else None,
                    edge_target_id=head_id if two_level else None,
                    exact_idem=not two_level,
                )
                if not two_level and res.target_id not in heads:
                    heads.append(res.target_id)
                results.append(res)

        return BatchDeriveResult(
            heads=heads,
            total_edges=sum(1 for r in results if not r.replay),
            skipped_replays=sum(1 for r in results if r.replay),
            per_item_open_qty=[r.open_qty for r in results],
            results=results,
        )