# -*- coding: utf-8 -*-
"""[单据流 Phase 1] DOC_FLOW 派生引擎（同库同事务闭环）

调用契约（spec 2026-09-29 §6.2）::

    derive(app_ds, platform_ds, rule_id, source_id, source_item=...,
           quantity=..., target_data={...}, derived_by=...)

单事务五步（F5：app_ds 单库，绝不跨库）::

    BEGIN
      1. check   源行存在 + 数量充足性（Σ 校验兜底，见下）
      2. map     默认映射：同名字段直拷（quantity/unit 等）+ target_data 覆盖
      3. create  写目标单行（直写 INSERT——不复用 _do_create，见"实现裁定"）
      4. edge    写边（7 元组 + quantity + rule_id + derived_at/by，status=active）
      5. Σ 校验  active 正向 − active 红字 ≤ 源行数量，违反 → 整体回滚
    COMMIT

实现裁定（对 spec §6.2/§6.3 的落地细化，已记入 spec v1.1）:
- **直写目标行**：_do_create 绑定 ActionExecutor 实例与请求上下文（规则引擎/
  审计 v2/写守卫），且其事务边界（self.ds）与引擎入参 app_ds 未必同库——
  同事务要求下由引擎直写 INSERT；权限校验在入口 Action 层完成，审计由
  边表 derived_at/by + 目标行审计字段承担。
- **两种模式**：
  - create 模式（target_data 不含 id）：新建目标单行 → 一源行可多次部分派生
    （对应 SAP 分批交货，多条边合法）；
  - attach 模式（target_data 含 id）：挂到既有目标单 → 7 元组幂等重放安全
    （同 7 元组重复调用返回既有边、零新增、不报错，spec §6.3）。
- **幂等优先于写**：attach 模式在事务内先查 7 元组，命中即返回——目标行与
  边都不会重复；create 模式目标身份是新生成的，天然无重放。
- **红字分支一次写对**：Σ 公式内建 quantity_sign 分支，Phase 1 恒 normal、
  quantity 必须 > 0（红字/负数是 Phase 2 冲销引擎的专用入口）。
- **池隔离**：Σ 聚合按 rule.pool 过滤（主文档 §3.4 v1.4 多池修订）——
  异池规则的消耗互不串扰。

对应方案: docs/superpowers/specs/2026-09-08-doc-flow-quantity-semantics.md §3 / §6.5
          docs/superpowers/specs/2026-09-29-doc-flow-phase1-spec.md §6
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

#: 浮点比较容差（Σ 校验用，REAL 精度兜底）
_QTY_EPSILON = 1e-9

#: 边表物理表名（统一定义见 doc_flow_schema）
DOC_FLOW_EDGES_TABLE = "doc_flow_edges"


class DocFlowDeriveError(Exception):
    """派生失败（带稳定错误码，供上层 API/测试断言）。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class DeriveResult:
    """derive 执行结果。"""

    edge_id: str
    target_id: Any
    replay: bool          # True = 幂等重放命中既有边（零新增）
    source_qty: float
    consumed_qty: float
    open_qty: float


def _num(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _consumed_in_pool(app_ds, source_bo: str, source_id: str,
                      source_item: str, pool: str) -> float:
    """指定池内该源行的已消耗量（§3.4 公式：active 正向 − active 红字）。"""
    row = app_ds.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN status='active' AND quantity_sign='normal'
                               THEN quantity ELSE 0 END), 0)
           - COALESCE(SUM(CASE WHEN status='active' AND quantity_sign='red'
                               THEN quantity ELSE 0 END), 0)
           FROM doc_flow_edges
           WHERE source_bo=? AND source_id=? AND source_item=? AND pool=?""",
        (source_bo, str(source_id), source_item, pool),
    ).fetchall()
    return _num(row[0][0]) if row else 0.0


def _find_edge_by_key(app_ds, key: Tuple) -> Optional[str]:
    """按 7 元组幂等键查既有边 ID；不存在返回 None。"""
    (source_bo, source_id, source_item,
     target_bo, target_id, target_item, rule_id) = key
    rows = app_ds.execute(
        """SELECT id FROM doc_flow_edges
           WHERE source_bo=? AND source_id=? AND source_item=?
             AND target_bo=? AND target_id=? AND target_item=? AND rule_id=?""",
        (source_bo, str(source_id), source_item,
         target_bo, str(target_id), target_item, rule_id),
    ).fetchall()
    return rows[0][0] if rows else None


def _find_edge_loose(app_ds, source_bo: str, source_id: Any, source_item: str,
                     target_bo: str, target_id: Any,
                     rule_id: str) -> Optional[Tuple[str, str]]:
    """按 (源, 目标单头, 规则) 宽松键查既有边 → (edge_id, target_item)。

    头行模式下明细行 ID 在幂等预查时刻尚未生成（spec §6.3），故退一格：
    同一源行 + 同一目标单头 + 同一规则 = 已派生过，命中即重放。
    """
    rows = app_ds.execute(
        """SELECT id, target_item FROM doc_flow_edges
           WHERE source_bo=? AND source_id=? AND source_item=?
             AND target_bo=? AND target_id=? AND rule_id=?
           ORDER BY derived_at LIMIT 1""",
        (source_bo, str(source_id), source_item,
         target_bo, str(target_id), rule_id),
    ).fetchall()
    return (rows[0][0], rows[0][1]) if rows else None


def _replay_result(app_ds, rule, source_bo_id: str, source_id: Any,
                   source_item: str, source_qty: float, edge_id: str,
                   target_id: Any) -> "DeriveResult":
    """构造幂等重放结果（零新增：返回既有边 + 当前池消耗口径）。"""
    consumed = _consumed_in_pool(
        app_ds, source_bo_id, source_id, source_item, rule["pool"]
    )
    return DeriveResult(
        edge_id=edge_id, target_id=target_id, replay=True,
        source_qty=source_qty, consumed_qty=consumed,
        open_qty=source_qty - consumed,
    )


def _row_exists(app_ds, table: str, row_id: Any) -> bool:
    rows = app_ds.execute(
        "SELECT 1 FROM {0} WHERE id = ?".format(table), (row_id,)
    ).fetchall()
    return bool(rows)


def _read_source_fields(app_ds, table: str, source_id: Any,
                        field_ids: Tuple[str, ...], meta_obj) -> Dict[str, Any]:
    """读源行指定字段的值（按 db_column 取列，返回 {field_id: value}）。

    刻意显式列名而非 SELECT *：不依赖 cursor row_factory 的返回形态。
    """
    id_field = meta_obj.get_field("id")
    id_col = id_field.db_column if id_field else "id"
    cols, wanted = [], []
    for fid in field_ids:
        f = meta_obj.get_field(fid)
        if f is not None and f.db_column != id_col:
            cols.append(f.db_column)
            wanted.append(fid)
    if not cols:
        return {}
    select_cols = ", ".join([id_col] + cols)
    rows = app_ds.execute(
        "SELECT {0} FROM {1} WHERE {2} = ?".format(select_cols, table, id_col),
        (source_id,),
    ).fetchall()
    if not rows:
        return {}
    return dict(zip(wanted, rows[0][1:]))


def _derive_core(app_ds, rule, source_obj, target_obj, source_id, source_item,
                 qty, target_data, derived_by, now, *,
                 fk_column: Optional[str] = None, fk_value: Any = None,
                 edge_target_bo: Optional[str] = None,
                 edge_target_id: Any = None,
                 exact_idem: bool = True,
                 derive_key: str = "") -> DeriveResult:
    """事务内单行派生核心（**不含事务装饰**——调用方负责事务边界）。

    两种模式（同一份映射/边/Σ 逻辑，差异只在"目标身份从哪来"）：

    - **单表模式**（Phase 1 行为，``exact_idem=True``）：``target_obj`` = 规则
      ``target_bo``；目标身份 = ``target_data['id']``（attach，幂等重放）或新建行；
      edge 目标三元组在函数内确定，幂等按 **7 元组精确匹配**。
    - **头行模式**（Phase 2，``exact_idem=False``）：``target_obj`` = 明细行 BO；
      ``edge_target_bo/id`` = 单头（调用方给定），``fk_column/fk_value`` 写明细行
      归属外键；幂等按 **(源, 单头, 规则) 宽松匹配**——明细行 ID 此刻尚未生成
      （spec §6.3），命中即重放，不重复建行。

    映射优先级链（spec §5.1）：同名字段直拷 → field_map 改名 → target_data
    静态覆盖；目标行数量字段不参与映射链（§5.3，由引擎显式写入派生量）。
    """
    source_table = source_obj.table_name
    target_table = target_obj.table_name
    source_bo_id, target_bo_id = source_obj.id, target_obj.id

    target_qty_field = target_obj.get_field("quantity")
    qty_col = target_qty_field.db_column if target_qty_field else None
    target_field_ids = tuple(
        f.id for f in target_obj.get_persistent_fields() if f.id != "id"
    )
    # 同名直拷候选（数量字段例外——其语义是本次派生量，见模块 docstring）
    copy_field_ids = tuple(
        fid for fid in target_field_ids
        if fid != (target_qty_field.id if target_qty_field else None)
        and source_obj.get_field(fid) is not None
    )
    # field_map 改名对（§5.1 优先级链第 2 环）；两端字段须都存在，数量字段除外
    rename_pairs = []
    for src_fid, tgt_fid in (rule.get("field_map") or {}).items():
        if target_qty_field is not None and tgt_fid == target_qty_field.id:
            continue
        if (source_obj.get_field(src_fid) is not None
                and target_obj.get_field(tgt_fid) is not None):
            rename_pairs.append((src_fid, tgt_fid))

    read_field_ids = tuple(
        set(copy_field_ids) | {rule["source_qty_field"]}
        | {src for src, _ in rename_pairs}
    )

    # ── 1. check：源行存在 + 读数量/映射源 ───────────────────────────────
    source_vals = _read_source_fields(
        app_ds, source_table, source_id, read_field_ids, source_obj,
    )
    if not source_vals and not _row_exists(app_ds, source_table, source_id):
        raise DocFlowDeriveError(
            "SOURCE_ROW_NOT_FOUND",
            f"源行不存在: {source_bo_id}.id={source_id}",
        )
    source_qty = _num(source_vals.get(rule["source_qty_field"]))

    # 数量 > 0（红字/负数是 Phase 3 冲销专用入口；精确充足性由 Σ 校验权威判定）
    if qty <= 0:
        raise DocFlowDeriveError(
            "INVALID_QUANTITY",
            f"派生数量必须 > 0（红字冲销是专用入口），实际: {qty}",
        )

    # ── 2. 目标身份 + 幂等重放预查 ───────────────────────────────────────
    attach_target_id = None
    target_item = ""
    if exact_idem:
        attach_target_id = target_data.get("id")
        target_item = str(target_data.get("item") or "")
        if attach_target_id is not None:
            if not _row_exists(app_ds, target_table, attach_target_id):
                raise DocFlowDeriveError(
                    "TARGET_ROW_NOT_FOUND",
                    f"目标行不存在: {target_bo_id}.id={attach_target_id}",
                )
            existing = _find_edge_by_key(
                app_ds, (source_bo_id, source_id, source_item,
                         target_bo_id, attach_target_id, target_item, rule["rule_id"])
            )
            if existing:
                return _replay_result(app_ds, rule, source_bo_id, source_id,
                                      source_item, source_qty, existing,
                                      attach_target_id)
    else:
        if edge_target_id is None:
            raise DocFlowDeriveError(
                "HEAD_FK_NOT_FOUND", "头行模式缺少单头 ID（edge_target_id）"
            )
        found = _find_edge_loose(
            app_ds, source_bo_id, source_id, source_item,
            edge_target_bo, edge_target_id, rule["rule_id"],
        )
        if found:
            return _replay_result(app_ds, rule, source_bo_id, source_id,
                                  source_item, source_qty, found[0], found[1])

    # ── 3. map + create：直拷 → 改名 → 静态覆盖 → 数量默认 ───────────────
    if exact_idem and attach_target_id is not None:
        target_id = attach_target_id
    else:
        row_data: Dict[str, Any] = {}
        for fid in copy_field_ids:                       # ① 同名字段直拷
            if fid in source_vals:
                row_data[target_obj.get_field(fid).db_column] = source_vals[fid]
        for src_fid, tgt_fid in rename_pairs:            # ② field_map 改名
            if src_fid in source_vals:
                row_data[target_obj.get_field(tgt_fid).db_column] = source_vals[src_fid]
        for fid in target_field_ids:                     # ③ target_data 覆盖
            if fid in target_data:
                row_data[target_obj.get_field(fid).db_column] = target_data[fid]
        if qty_col is not None and qty_col not in row_data:
            row_data[qty_col] = qty                      # 数量默认 = 本次派生量
        if fk_column is not None:                        # 头行模式：归属外键
            row_data[fk_column] = fk_value
        for audit_col in ("created_at", "updated_at"):
            f = target_obj.get_field(audit_col)
            if f is not None and f.db_column not in row_data:
                row_data[f.db_column] = now
        target_id = app_ds.insert(target_table, row_data)
        if target_id is None:
            raise DocFlowDeriveError(
                "CREATE_TARGET_FAILED", f"目标单行写入失败: {target_table}"
            )

    # edge 目标三元组：单表模式 = 目标行本身；头行模式 = 单头 + 行项目
    if edge_target_bo is None:
        ed_bo, ed_id, ed_item = target_bo_id, target_id, target_item
    else:
        ed_bo, ed_id, ed_item = edge_target_bo, edge_target_id, str(target_id)

    # ── 4. 写边（append-only 事实流水，status=active）────────────────────
    edge_id = uuid.uuid4().hex
    try:
        app_ds.insert(DOC_FLOW_EDGES_TABLE, {
            "id": edge_id,
            "source_bo": source_bo_id,
            "source_id": str(source_id),
            "source_item": source_item,
            "target_bo": ed_bo,
            "target_id": str(ed_id),
            "target_item": ed_item,
            "quantity": qty,
            "amount": _num(target_data.get("amount")),
            "currency": str(target_data.get("currency") or ""),
            "unit": str(target_data.get("unit")
                        or source_vals.get("unit") or ""),
            "quantity_sign": "normal",
            "rule_id": rule["rule_id"],
            "derived_at": now,
            "derived_by": derived_by,
            "status": "active",
            "pool": rule["pool"],
            "source_instance_id": "",
            "target_instance_id": "",
            "derive_key": derive_key,
        })
    except Exception as e:  # noqa: BLE001 - 唯一索引冲突 → 幂等重放兜底
        existing = _find_edge_by_key(
            app_ds, (source_bo_id, source_id, source_item,
                     ed_bo, ed_id, ed_item, rule["rule_id"])
        )
        if existing:
            logger.warning("[DocFlow] 7 元组冲突但命中既有边（并发重放）: %s", e)
            return _replay_result(app_ds, rule, source_bo_id, source_id,
                                  source_item, source_qty, existing, target_id)
        raise

    # ── 5. Σ 校验（权威判定；违反 → 异常上抛 → 事务整体回滚）─────────────
    consumed = _consumed_in_pool(
        app_ds, source_bo_id, source_id, source_item, rule["pool"]
    )
    if consumed > source_qty + _QTY_EPSILON:
        raise DocFlowDeriveError(
            "OVER_DERIVE",
            "超额派生被拒（事务已回滚）: 源行 {0}.id={1} 数量={2}, "
            "本次后已消耗={3}, 超出={4}".format(
                source_bo_id, source_id, source_qty, consumed,
                round(consumed - source_qty, 9),
            ),
        )

    return DeriveResult(
        edge_id=edge_id, target_id=target_id, replay=False,
        source_qty=source_qty, consumed_qty=consumed,
        open_qty=source_qty - consumed,
    )


def derive(app_ds, platform_ds, rule_id: str, source_id: Any,
           source_item: str = "", quantity: Optional[float] = None,
           target_data: Optional[Dict[str, Any]] = None,
           derived_by: str = "",
           derive_key: str = "") -> DeriveResult:
    """执行一次派生（同库同事务：目标单行 + 边一起落，一起回滚）。

    Args:
        app_ds: 源/目标/边所在的同一应用库数据源（调用方保证与 BO 同库）
        platform_ds: 平台库数据源（读 doc_flow_rule；规则读取在数据事务之外
            ——规则与业务数据异库，F5 禁止纳入同一事务）
        rule_id: 复制规则 ID（须已注册且 status=active）
        source_id: 源单行记录 ID
        source_item: 源行项目标识（行级 BO 派生留空串即可）
        quantity: 本边消耗量（>0；红字/负数是 Phase 2 冲销专用入口）
        target_data: 目标单数据；含 `id` = attach 模式（挂既有目标单），
            否则 create 模式（新建目标单行，同名字段自动映射 + 此处覆盖）
        derived_by: 派生执行者（写边 derived_by）
        derive_key: 边业务幂等键（Phase 2 冲销引擎锚定用：'count:' 前缀；
            默认空串 = 普通派生）

    Raises:
        DocFlowDeriveError: RULE_NOT_FOUND / RULE_DEPRECATED / BO_NOT_REGISTERED /
            SOURCE_ROW_NOT_FOUND / TARGET_ROW_NOT_FOUND / INVALID_QUANTITY /
            SOURCE_QTY_FIELD_MISSING / OVER_DERIVE
    """
    from meta.core.doc_flow_rule_store import get_rule
    from meta.core.models import registry

    target_data = dict(target_data or {})

    # ── 前置 1：规则（平台库，数据事务之外）──────────────────────────────
    rule = get_rule(platform_ds, rule_id)
    if rule is None:
        raise DocFlowDeriveError("RULE_NOT_FOUND", f"规则不存在: {rule_id}")
    if rule["status"] != "active":
        raise DocFlowDeriveError(
            "RULE_DEPRECATED",
            f"规则 '{rule_id}' 已停用（deprecated 停新不禁旧，历史边不受影响）",
        )

    # ── 前置 2：BO 元数据 ────────────────────────────────────────────────
    source_obj = registry.get(rule["source_bo"])
    target_obj = registry.get(rule["target_bo"])
    missing_bo = [
        bo for bo, obj in ((rule["source_bo"], source_obj),
                           (rule["target_bo"], target_obj)) if obj is None
    ]
    if missing_bo:
        raise DocFlowDeriveError(
            "BO_NOT_REGISTERED", f"BO 未注册: {missing_bo}"
        )
    if source_obj.get_field(rule["source_qty_field"]) is None:
        raise DocFlowDeriveError(
            "SOURCE_QTY_FIELD_MISSING",
            f"源 BO '{source_obj.id}' 缺少数量字段 '{rule['source_qty_field']}'"
            "（规则的 source_qty_field 声明有误）",
        )

    now = datetime.now().isoformat(timespec="seconds")

    with app_ds.transaction():
        return _derive_core(
            app_ds, rule, source_obj, target_obj, source_id, source_item,
            _num(quantity), target_data, derived_by, now, exact_idem=True,
            derive_key=derive_key,
        )
