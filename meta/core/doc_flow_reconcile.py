# -*- coding: utf-8 -*-
"""[单据流 Phase 2] DOC_FLOW 一致性巡检 + 投影重建（S7 最小版，触发式）

契约（doc-flow spec §9.5 S7 / §9.6 Phase 2；roadmap §五 S7）::

    S7 巡检最小版（触发式脚本）→ 验收：对账可发现人为改账
    巡检域（最小版 3 域，2026-10-02 用户拍板"精简 3 域"）:
      ① 结构域    边表缺失 / 边表缺列 / 规范索引缺失（幂等索引须唯一，其余
                  两索引缺失为 warn）/ 消耗视图缺失 / 视图 SQL 漂移
      ② 边域      7 元组幂等键重复 / 同 6 元组异规则 active+normal（R4 双重消耗）/
                  status·quantity_sign·quantity 域值非法
      ③ 视图对账  边表复算 vs 视图查询逐行比对（数值侧双保险；含红字口径）
      ④ 事务互检  库存事务 ↔ 转单边双向核对（ORPHAN_TXN / DANGLING_EDGE）；
                  调整/盘点来源对账（P2 B+ 口径：UNKNOWN_SOURCE_DOC_TYPE /
                  MISSING_SOURCE_DOC / UNEXPECTED_ADJUSTMENT_EDGE）
      ⑤ 跨层对账  计划层 reservation 量 ↔ 执行层出库边量
                  （TRACE_EDGE_QTY_MISMATCH，2026-11-05 阶段 4）

    投影重建（显式触发，CLI --rebuild）：视图**单事务原子替换**（失败回滚，
    旧视图不变）+ 缺失索引/缺列补建；
    **绝不改边数据**（append-only 铁律）；后置自检闭环——SchemaMigrator 对索引
    创建失败吞错（重复键挡唯一索引），必须自检，缺一即 fail-loud 不假成功。

边界（如实声明，不扩范围）:
- **语义侧改账不可检**（无物化快照对照；§14 R3 完整对账依赖快照机制，未来
  落地后纳入）——具体包括: ① 人为删正常边（静默少消耗）；② 手改 quantity
  为另一合法正数；③ 手翻 status active→reversed（合法值；边表定稿 17 列无
  冲销审计位，E6 的 reversed_by 仅记日志，引擎翻转与手工翻转不可区分）；
  ④ 插孤儿边（target 不存在）；⑤ 改 rule_id 为不存在规则。以上需读事实对象
  / 规则表或快照对照，属完全体。
- 2026-10-02 精简 3 域（业务锚/超耗检查仍不做）；2026-11-05 端到端规格
  §3.5 新增④ 库存事务互检: 孤儿事务 ORPHAN_TXN / 悬空边 DANGLING_EDGE。
- 跨实例镜像差异不在本版（Phase 3 未启动，无镜像对象）。
- 不挂定时（E7 触发式；定时巡检属 Phase 4 完全体）。
- 全表扫描：边表起步量级可接受；大表窗口化留完全体。

对应方案: docs/superpowers/specs/2026-09-08-doc-flow-quantity-semantics.md §9.5 / §9.6
          docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §五 S7
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from meta.core.doc_flow_schema import (
    DOC_FLOW_CONSUMED_VIEW, DOC_FLOW_EDGE_TABLE, _build_consumed_view_meta,
    _build_edge_meta, edge_table_exists,
)

logger = logging.getLogger(__name__)

#: 数量浮点比较容差（与 derive 引擎 _QTY_EPSILON 对齐）
_QTY_EPSILON = 1e-9
#: 视图对账相对容差（聚合浮点误差）
_SUM_REL_TOL = 1e-6
#: 幂等唯一索引名（doc_flow_schema.MetaIndex.name）
_IDEM_INDEX = "uq_doc_flow_idem"
#: 每类 finding 明细最多列出的样本数（超出折叠为总数）
_MAX_DETAIL = 20

_STATUS_VALID = ("active", "reversed")
_SIGN_VALID = ("normal", "red")
#: 需与边表核对「有事务无边」的过账来源单据类型（发运 / 收货 / 调拨）
_POSTING_DOC_TYPES = ("shipment", "receipt", "transfer_order")
#: 库存事务来源类型注册表（P2 B+，规格 §4 C 类）：
#:   key = inventory_transactions.source_doc_type
#:   value = (来源单据表名 | None, 是否要求转单边)
#: 过账类（A/B 类）必须写边；调整/盘点/期初（C 类）只保留事实引用，
#: 不进入 DOC_FLOW 转单派生（与 Oracle Fusion「事务来源引用 ≠ 单据派生」一致）。
_SOURCE_DOC_REGISTRY = {
    "shipment": ("shipments", True),
    "receipt": ("receipts", True),
    "transfer_order": ("transfer_orders", True),
    "inventory_adjustment": ("inventory_adjustments", False),
    "inventory_count": ("inventory_counts", False),
    # 期初导入的 source_doc_id 是批次号 CRC32（无来源单据表）
    "opening": (None, False),
    # 库存段转移以事件键为来源（source_doc_type 缺省值）
    "inventory_segment_transfer": (None, False),
}
#: 调整类来源：B+ 明确不接入 DOC_FLOW，出现转单边即契约被破坏
_NON_DOC_FLOW_DOC_TYPES = ("inventory_adjustment", "inventory_count")
#: 边表指向库存事务的目标 BO
_INVENTORY_TXN_BO = "inventory_transaction"
#: 计划层线索表 / 发货行表（跨层对账用）
_TRACE_TABLE = "demand_trace_links"
_SHIPMENT_LINE_TABLE = "shipment_lines"
#: 计划层参与执行量对账的关系与执行边规则
_TRACE_RESERVATION = "reservation"
_SHIPMENT_ISSUE_RULE = "shipment_line_to_issue_txn"


# ─────────────────────────────────────────────────────────────────────────────
# 结果对象
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """一条巡检发现（机器可读 code + severity + 明细）。"""

    code: str
    severity: str          # error / warn
    detail: str


@dataclass
class ReconcileReport:
    """巡检报告（只读快照）。"""

    edge_count: int = 0
    active_count: int = 0
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        # 只有 error 级发现才算不 ok（warn 级如缺性能索引仅提示，不影响退出码）
        return not any(f.severity == "error" for f in self.findings)

    def codes(self) -> List[str]:
        return [f.code for f in self.findings]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_count": self.edge_count,
            "active_count": self.active_count,
            "ok": self.ok,
            "warnings": [f.code for f in self.findings if f.severity == "warn"],
            "findings": [
                {"code": f.code, "severity": f.severity, "detail": f.detail}
                for f in self.findings
            ],
        }


@dataclass
class RebuildResult:
    """投影重建结果（重建 = 写操作，仅动视图与索引）。"""

    view_existed: bool = False       # 重建前视图是否存在
    view_rebuilt: bool = False       # 后置自检：视图存在且达规范形态
    index_restored: bool = False     # 后置自检：唯一幂等索引在位
    ok: bool = False
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "view_existed": self.view_existed,
            "view_rebuilt": self.view_rebuilt,
            "index_restored": self.index_restored,
            "ok": self.ok,
            "error": self.error,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────────────────────

def _canonical_view_sql() -> str:
    """消耗视图的规范 SQL（唯一事实来源 = doc_flow_schema 定义）。"""
    return _build_consumed_view_meta().view_definition


def _norm_sql(sql: str) -> str:
    """SQL 归一化（比较用）：去 IF NOT EXISTS / 折叠空白 / 统一小写。"""
    s = re.sub(r"if\s+not\s+exists", "", sql or "", flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip().rstrip(";").strip()
    return s.lower()


def _stored_view_sql(app_ds) -> Optional[str]:
    """sqlite_master 中该视图的创建语句；视图不存在返回 None。"""
    rows = app_ds.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name=?",
        (DOC_FLOW_CONSUMED_VIEW,),
    ).fetchall()
    if not rows or rows[0][0] is None:
        return None
    return rows[0][0]


def _index_name_exists(app_ds, name: str) -> bool:
    """索引名是否存在（不判唯一性）。"""
    rows = app_ds.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchall()
    return bool(rows)


def _unique_index_ok(app_ds, name: str) -> bool:
    """索引存在**且确实为 UNIQUE**。

    只验名会被"同名普通索引"绕过（DROP 唯一索引后建同名非唯一索引）→ 防重放
    保障实际失效却亮绿灯。故用 PRAGMA index_list 复核 unique 标志。
    """
    try:
        rows = app_ds.execute(
            "PRAGMA index_list('{0}')".format(DOC_FLOW_EDGE_TABLE)
        ).fetchall()
    except Exception:  # noqa: BLE001 - 库不可读视为不满足
        return False
    for r in rows:
        # PRAGMA index_list 列序: (seq, name, unique, origin, partial)
        if len(r) >= 3 and r[1] == name and int(r[2]) == 1:
            return True
    return False


def _expected_edge_columns() -> Tuple[str, ...]:
    """边表规范列（唯一事实来源 = doc_flow_schema 的 MetaObject 定义）。"""
    return tuple(f.db_column or f.id for f in _build_edge_meta().fields)


def _actual_edge_columns(app_ds) -> set:
    """边表实际列（PRAGMA table_info 列序: cid, name, type, ...）。"""
    rows = app_ds.execute(
        "PRAGMA table_info('{0}')".format(DOC_FLOW_EDGE_TABLE)
    ).fetchall()
    return {r[1] for r in rows}


def _missing_edge_columns(app_ds) -> List[str]:
    """相对规范缺失的边表列（空 = 结构齐备）。"""
    actual = _actual_edge_columns(app_ds)
    return [c for c in _expected_edge_columns() if c not in actual]


def _expected_index_names() -> Tuple[str, ...]:
    """边表规范索引名（唯一事实来源 = doc_flow_schema MetaObject.indexes）。"""
    return tuple(ix.name for ix in _build_edge_meta().indexes)


def _missing_schema_indexes(app_ds) -> List[str]:
    """相对规范缺失/失真的索引；唯一幂等索引额外复核 unique 标志。"""
    out: List[str] = []
    for name in _expected_index_names():
        if name == _IDEM_INDEX:
            if not _unique_index_ok(app_ds, name):
                out.append(name)
        elif not _index_name_exists(app_ds, name):
            out.append(name)
    return out


def _expected_view_sql_norm() -> str:
    return _norm_sql(
        "CREATE VIEW {0} AS {1}".format(DOC_FLOW_CONSUMED_VIEW, _canonical_view_sql())
    )


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _sample(lines: List[str]) -> str:
    shown = "; ".join(lines[:_MAX_DETAIL])
    if len(lines) > _MAX_DETAIL:
        shown += " …（共 {0} 项）".format(len(lines))
    return shown


def _compare_view_sums(app_ds) -> List[Tuple[Tuple, float, float]]:
    """视图聚合 vs 边表复算（同一公式两侧独立取数），返回不一致组样本。"""
    view_rows = app_ds.execute(
        "SELECT source_bo, source_id, source_item, pool, consumed_qty FROM {0}".format(
            DOC_FLOW_CONSUMED_VIEW
        )
    ).fetchall()
    edge_rows = app_ds.execute(
        "SELECT source_bo, source_id, source_item, pool, "
        "SUM(CASE WHEN status='active' AND quantity_sign='normal' "
        "         THEN quantity ELSE 0 END) "
        "- SUM(CASE WHEN status='active' AND quantity_sign='red' "
        "         THEN quantity ELSE 0 END) "
        "FROM {0} GROUP BY source_bo, source_id, source_item, pool".format(
            DOC_FLOW_EDGE_TABLE
        )
    ).fetchall()

    vm = {(r[0], r[1], r[2], r[3]): _f(r[4]) for r in view_rows}
    em = {(r[0], r[1], r[2], r[3]): _f(r[4]) for r in edge_rows}

    out: List[Tuple[Tuple, float, float]] = []
    for key in sorted(set(vm) | set(em), key=lambda k: tuple(str(p) for p in k)):
        a, b = vm.get(key, 0.0), em.get(key, 0.0)
        if abs(a - b) > max(_QTY_EPSILON, _SUM_REL_TOL * max(abs(a), abs(b), 1.0)):
            out.append((key, a, b))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ④ 库存事务互检
# ─────────────────────────────────────────────────────────────────────────────

def _table_exists(app_ds, name: str) -> bool:
    try:
        found = app_ds.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,)).fetchall()
    except Exception:  # noqa: BLE001 - 无 sqlite_master 的测试双桩
        return False
    return bool(found)


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _inventory_edge_findings(app_ds, rows) -> List[Finding]:
    """库存事务与转单边双向核对（2026-11-05 端到端规格 §3.5）。

    - ``DANGLING_EDGE``：边 target_bo 指向库存事务，但事务不存在 / ID 非整数；
    - ``ORPHAN_TXN``：发运 / 收货 / 调拨过账事务没有任何边引用（有事务无边）。
      REVERSAL（``reversal_of_transaction_id`` 非 0）不要求边；原边保留
      ``status='reversed'`` 仍算引用，不误报。
    """
    if not _table_exists(app_ds, "inventory_transactions"):
        return []
    try:
        txn_rows = app_ds.execute(
            "SELECT id, source_doc_type, "
            "COALESCE(reversal_of_transaction_id, 0), source_doc_id "
            "FROM inventory_transactions").fetchall()
    except Exception:  # noqa: BLE001 - 半迁移 / 缺列时跳过本域
        return []

    txn_ids = {_int_or_none(r[0]) for r in txn_rows}
    txn_ids.discard(None)

    edge_targets: set = set()
    dangling: List[str] = []
    for r in rows:
        if r[4] != _INVENTORY_TXN_BO:
            continue
        tid = _int_or_none(r[5])
        if tid is None or tid not in txn_ids:
            dangling.append("edge={0} target_id={1!r}".format(r[0], r[5]))
        else:
            edge_targets.add(tid)

    orphan = [
        "txn={0} source_doc_type={1!r}".format(r[0], r[1])
        for r in txn_rows
        if r[1] in _POSTING_DOC_TYPES
        and (_int_or_none(r[2]) or 0) == 0
        and _int_or_none(r[0]) not in edge_targets
    ]

    findings: List[Finding] = []
    if dangling:
        findings.append(Finding(
            "DANGLING_EDGE", "error",
            "边指向不存在的库存事务 {0} 条: {1}".format(
                len(dangling), _sample(dangling))))
    if orphan:
        findings.append(Finding(
            "ORPHAN_TXN", "error",
            "过账事务无对应转单边 {0} 条: {1}".format(
                len(orphan), _sample(orphan))))

    findings.extend(_source_doc_findings(app_ds, txn_rows, rows))
    return findings


def _source_doc_findings(app_ds, txn_rows, edge_rows) -> List[Finding]:
    """调整/盘点来源对账（P2 B+：保留事实引用，不建转单边）。

    三项检查（缺来源表时自动降级）：
    - ``UNKNOWN_SOURCE_DOC_TYPE``（warn）：来源类型不在注册表，防新入口绕开口径；
    - ``MISSING_SOURCE_DOC``（error）：调整/盘点事务的 ``source_doc_id``
      在来源表不存在（删除策略为 restrict，正常不应出现）；
    - ``UNEXPECTED_ADJUSTMENT_EDGE``（warn）：调整类事务被转单边引用，
      违反「不接入 DOC_FLOW」契约（会把调整量带进需求追溯执行层）。
    """
    findings: List[Finding] = []

    unknown = [
        "txn={0} source_doc_type={1!r}".format(r[0], r[1])
        for r in txn_rows
        if r[1] and r[1] not in _SOURCE_DOC_REGISTRY
    ]
    if unknown:
        findings.append(Finding(
            "UNKNOWN_SOURCE_DOC_TYPE", "warn",
            "库存事务来源类型未注册 {0} 条: {1}".format(
                len(unknown), _sample(unknown))))

    missing: List[str] = []
    for doc_type, (table, needs_edge) in _SOURCE_DOC_REGISTRY.items():
        # 过账类来源的存在性由 ORPHAN_TXN/业务外键保障，本项只查 C 类
        if not table or needs_edge or not _table_exists(app_ds, table):
            continue
        by_doc: Dict[int, List[Any]] = {}
        for r in txn_rows:
            if r[1] != doc_type:
                continue
            doc_id = _int_or_none(r[3])
            if doc_id is not None:
                by_doc.setdefault(doc_id, []).append(r[0])
        if not by_doc:
            continue
        placeholders = ",".join("?" * len(by_doc))
        try:
            existing_rows = app_ds.execute(
                "SELECT id FROM {0} WHERE id IN ({1})".format(
                    table, placeholders),
                tuple(sorted(by_doc))).fetchall()
        except Exception:  # noqa: BLE001 - 半迁移 / 列名差异时跳过
            continue
        existing = {_int_or_none(r[0]) for r in existing_rows}
        for doc_id in sorted(set(by_doc) - existing):
            missing.append("{0} 缺失: txn={1} doc_id={2}".format(
                table, "/".join(str(t) for t in by_doc[doc_id]), doc_id))
    if missing:
        findings.append(Finding(
            "MISSING_SOURCE_DOC", "error",
            "调整/盘点事务的来源单据不存在 {0} 条: {1}".format(
                len(missing), _sample(missing))))

    adjustment_txn_ids = {
        _int_or_none(r[0]) for r in txn_rows
        if r[1] in _NON_DOC_FLOW_DOC_TYPES and _int_or_none(r[0]) is not None
    }
    unexpected = [
        "edge={0} target_id={1}".format(r[0], r[5])
        for r in edge_rows
        if r[4] == _INVENTORY_TXN_BO
        and _int_or_none(r[5]) in adjustment_txn_ids
    ]
    if unexpected:
        findings.append(Finding(
            "UNEXPECTED_ADJUSTMENT_EDGE", "warn",
            "调整/盘点事务被转单边引用 {0} 条（B+ 口径应为无边）: {1}".format(
                len(unexpected), _sample(unexpected))))
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ 跨层对账（计划层 reservation ↔ 执行层出库边）
# ─────────────────────────────────────────────────────────────────────────────

def _trace_edge_findings(app_ds) -> List[Finding]:
    """同一 SO 行的计划核销量与执行出库量比对。

    - 计划侧：``demand_trace_links`` 中 ``trace_type='reservation'`` 且
      ``valid_to IS NULL`` 的 ``allocated_qty``，按 ``demand_object_id`` 聚合；
    - 执行侧：``shipment_line_to_issue_txn`` 边，按发货行回查
      ``shipment_lines.order_line_id`` 聚合；
    - 任一侧为空不报（历史缺失不是漂移）；容差同视图对账。
    - 缺 ``demand_trace_links`` / ``shipment_lines`` / 边表时跳过本域。
    """
    if not (_table_exists(app_ds, _TRACE_TABLE)
            and _table_exists(app_ds, _SHIPMENT_LINE_TABLE)
            and _table_exists(app_ds, DOC_FLOW_EDGE_TABLE)):
        return []

    try:
        plan_rows = app_ds.execute(
            "SELECT demand_object_id, SUM(allocated_qty) "
            "FROM {0} "
            "WHERE demand_object_type='sales_order_line' "
            "  AND trace_type=? AND valid_to IS NULL "
            "GROUP BY demand_object_id".format(_TRACE_TABLE),
            (_TRACE_RESERVATION,),
        ).fetchall()
        exec_rows = app_ds.execute(
            "SELECT sl.order_line_id, SUM(e.quantity) "
            "FROM {0} e "
            "JOIN {1} sl ON CAST(sl.id AS TEXT) = e.source_id "
            "WHERE e.rule_id=? AND e.target_bo=? "
            "  AND e.status='active' AND e.quantity_sign='normal' "
            "GROUP BY sl.order_line_id".format(
                DOC_FLOW_EDGE_TABLE, _SHIPMENT_LINE_TABLE),
            (_SHIPMENT_ISSUE_RULE, _INVENTORY_TXN_BO),
        ).fetchall()
    except Exception:  # noqa: BLE001 - 半迁移 / 缺列时跳过本域
        return []

    plan = {}
    for so_line_id, qty in plan_rows:
        key = _int_or_none(so_line_id)
        if key is not None:
            plan[key] = plan.get(key, 0.0) + _f(qty)

    executed = {}
    for so_line_id, qty in exec_rows:
        key = _int_or_none(so_line_id)
        if key is not None:
            executed[key] = executed.get(key, 0.0) + _f(qty)

    mismatch: List[str] = []
    for key in sorted(set(plan) & set(executed)):
        planned, actual = plan[key], executed[key]
        if planned <= 0 or actual <= 0:
            continue
        if abs(planned - actual) > max(
                _QTY_EPSILON, _SUM_REL_TOL * max(abs(planned), abs(actual), 1.0)):
            mismatch.append(
                "sales_order_line={0} plan={1:g} exec={2:g}".format(
                    key, planned, actual))

    if not mismatch:
        return []
    return [Finding(
        "TRACE_EDGE_QTY_MISMATCH", "error",
        "计划核销量与执行出库量不一致 {0} 条: {1}".format(
            len(mismatch), _sample(mismatch)))]


# ─────────────────────────────────────────────────────────────────────────────
# 巡检（只读）
# ─────────────────────────────────────────────────────────────────────────────

def scan(app_ds) -> ReconcileReport:
    """一致性巡检（只读，5 域：结构 / 边域 / 视图 / 库存事务互检 / 跨层对账）。

    Args:
        app_ds: 应用库数据源（边表/视图所在库）

    Returns:
        ReconcileReport（findings 为空即 ok）
    """
    report = ReconcileReport()
    findings: List[Finding] = []

    # ── ① 结构域 ─────────────────────────────────────────────────────────────
    if not edge_table_exists(app_ds):
        findings.append(Finding(
            "EDGE_TABLE_MISSING", "error",
            "边表 {0} 不存在（该库未启用 doc_flow 或表被删）".format(
                DOC_FLOW_EDGE_TABLE),
        ))
        report.findings = findings
        return report

    missing_cols = _missing_edge_columns(app_ds)
    if missing_cols:
        findings.append(Finding(
            "EDGE_TABLE_COLUMNS_MISSING", "error",
            "边表缺列 {0} 个: {1}（结构与规范不符；可用 --rebuild 触发补列）".format(
                len(missing_cols), ", ".join(missing_cols)),
        ))

    missing_idx = _missing_schema_indexes(app_ds)
    if _IDEM_INDEX in missing_idx:
        findings.append(Finding(
            "IDEM_INDEX_MISSING", "error",
            "唯一幂等索引 {0} 缺失或已退化为非唯一（7 元组防重放保障失效；"
            "可用 --rebuild 补建）".format(_IDEM_INDEX),
        ))
    other_idx = [n for n in missing_idx if n != _IDEM_INDEX]
    if other_idx:
        findings.append(Finding(
            "SCHEMA_INDEX_MISSING", "warn",
            "结构索引缺失 {0}: {1}（不影响账本正确性，仅查询性能；"
            "可用 --rebuild 补建）".format(len(other_idx), ", ".join(other_idx)),
        ))

    stored_sql = _stored_view_sql(app_ds)
    view_ok = stored_sql is not None
    if not view_ok:
        findings.append(Finding(
            "VIEW_MISSING", "error",
            "消耗视图 {0} 缺失（可用 --rebuild 重建）".format(DOC_FLOW_CONSUMED_VIEW),
        ))
    elif _norm_sql(stored_sql) != _expected_view_sql_norm():
        findings.append(Finding(
            "VIEW_SQL_DRIFT", "error",
            "视图定义与规范 SQL 不一致（视图被篡改；可用 --rebuild 重建）",
        ))

    # 缺列时不读边表/不做视图对账（SELECT 会因缺列直接抛错）
    if missing_cols:
        report.findings = findings
        return report

    # ── ② 边域（全表扫描） ───────────────────────────────────────────────────
    rows = app_ds.execute(
        "SELECT id, source_bo, source_id, source_item, target_bo, target_id, "
        "target_item, rule_id, quantity, quantity_sign, status "
        "FROM {0}".format(DOC_FLOW_EDGE_TABLE)
    ).fetchall()
    report.edge_count = len(rows)

    invalid_status: List[str] = []
    invalid_sign: List[str] = []
    invalid_qty: List[str] = []
    idem_groups: Dict[Tuple, List[str]] = {}
    pair_groups: Dict[Tuple, List[Tuple[str, str]]] = {}

    for r in rows:
        (eid, s_bo, s_id, s_item, t_bo, t_id, t_item, rule_id,
         qty, sign, status) = r
        if status == "active":
            report.active_count += 1
        if status not in _STATUS_VALID:
            invalid_status.append("edge={0} status={1!r}".format(eid, status))
        if sign not in _SIGN_VALID:
            invalid_sign.append("edge={0} quantity_sign={1!r}".format(eid, sign))
        q = None if qty is None else _f(qty)
        if q is None or q <= _QTY_EPSILON:
            invalid_qty.append("edge={0} quantity={1!r}".format(eid, qty))

        key7 = (s_bo, s_id, s_item, t_bo, t_id, t_item, rule_id)
        idem_groups.setdefault(key7, []).append(eid)

        if status == "active" and sign == "normal":
            key6 = (s_bo, s_id, s_item, t_bo, t_id, t_item)
            pair_groups.setdefault(key6, []).append((eid, rule_id))

    if invalid_status:
        findings.append(Finding(
            "INVALID_STATUS", "error",
            "status 域非法 {0} 条: {1}".format(
                len(invalid_status), _sample(invalid_status)),
        ))
    if invalid_sign:
        findings.append(Finding(
            "INVALID_SIGN", "error",
            "quantity_sign 域非法 {0} 条: {1}".format(
                len(invalid_sign), _sample(invalid_sign)),
        ))
    if invalid_qty:
        findings.append(Finding(
            "INVALID_QUANTITY", "error",
            "quantity 域非法（≤0 或非数值）{0} 条: {1}".format(
                len(invalid_qty), _sample(invalid_qty)),
        ))

    dup_idem = [k for k, v in idem_groups.items() if len(v) > 1]
    if dup_idem:
        lines = [
            "{0}:{1}/{2}→{3}:{4}/{5} rule={6}（{7} 条边）".format(
                k[0], k[1], k[2], k[3], k[4], k[5], k[6], len(idem_groups[k]))
            for k in dup_idem
        ]
        findings.append(Finding(
            "DUPLICATE_IDEM_KEY", "error",
            "7 元组幂等键重复 {0} 组: {1}".format(len(dup_idem), _sample(lines)),
        ))

    dup_pairs = [
        (k, v) for k, v in pair_groups.items()
        if len({rule for _, rule in v}) > 1
    ]
    if dup_pairs:
        lines = []
        for k, v in dup_pairs:
            rules = sorted({rule for _, rule in v})
            lines.append(
                "{0}:{1}/{2}→{3}:{4}/{5}（{6} 条 active normal 边，规则 {7}）".format(
                    k[0], k[1], k[2], k[3], k[4], k[5], len(v), "/".join(rules))
            )
        findings.append(Finding(
            "DUPLICATE_PAIR", "error",
            "同源同目标行经不同规则重复派生 {0} 组（§14 R4 双重消耗风险）: {1}".format(
                len(dup_pairs), _sample(lines)),
        ))

    # ── ④ 库存事务互检（ORPHAN_TXN / DANGLING_EDGE；无事务表时跳过） ───────────
    findings.extend(_inventory_edge_findings(app_ds, rows))

    # ── ⑤ 跨层对账（计划核销 vs 执行出库；缺 trace/shipment_lines 时跳过） ─────
    findings.extend(_trace_edge_findings(app_ds))

    # ── ③ 视图对账（数值侧双保险；视图缺失时跳过） ────────────────────────────
    if view_ok:
        mismatches = _compare_view_sums(app_ds)
        if mismatches:
            lines = [
                "{0}:{1}/{2} pool={3} 视图={4:.6g} 复算={5:.6g}".format(
                    k[0], k[1], k[2], k[3], a, b)
                for k, a, b in mismatches
            ]
            findings.append(Finding(
                "VIEW_SUM_MISMATCH", "error",
                "视图聚合与边表复算不一致 {0} 组: {1}".format(
                    len(mismatches), _sample(lines)),
            ))

    report.findings = findings
    return report


# ─────────────────────────────────────────────────────────────────────────────
# 投影重建（显式触发；写操作）
# ─────────────────────────────────────────────────────────────────────────────

def rebuild_projection(app_ds) -> RebuildResult:
    """按边表重建投影：视图原子替换 + 缺失索引/列补建（幂等可重入）。

    **绝不改边数据**（append-only 铁律）。视图替换在单事务内 DROP+CREATE，
    失败即回滚（旧视图保持不变，不出现"DROP 后建不回"的空窗）。后置自检
    闭环：SchemaMigrator 对索引创建失败吞错（重复键挡唯一索引即静默失败），
    故重建后逐项复核（视图达规范形态 + 规范索引齐全），缺一即 ok=False +
    error（fail-loud，不假成功）。

    Args:
        app_ds: 应用库数据源

    Returns:
        RebuildResult
    """
    from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables

    result = RebuildResult()
    if not edge_table_exists(app_ds):
        result.error = "边表 {0} 不存在，无法重建投影（该库未启用 doc_flow）".format(
            DOC_FLOW_EDGE_TABLE)
        return result

    result.view_existed = _stored_view_sql(app_ds) is not None

    # 原子替换视图：DROP + CREATE 同一事务，任一失败即回滚 → 旧视图保持不变
    # （SchemaMigrator 的视图 CREATE 是 IF NOT EXISTS 且静默吞错，故此处直接
    #   用规范 SQL 建视图，不走 ensure）
    try:
        with app_ds.transaction():
            app_ds.execute("DROP VIEW IF EXISTS {0}".format(DOC_FLOW_CONSUMED_VIEW))
            app_ds.execute("CREATE VIEW {0} AS {1}".format(
                DOC_FLOW_CONSUMED_VIEW, _canonical_view_sql()))
    except Exception as e:  # noqa: BLE001 - 重建失败必须显式回报，不假成功
        result.error = "视图重建失败（已回滚，原视图保持不变）: {0}".format(e)
        return result

    # 同名非唯一索引（被篡改）→ 先摘除，交给 ensure 重建为唯一索引
    # （重复键仍会 fail-loud，见后置自检）
    if (not _unique_index_ok(app_ds, _IDEM_INDEX)
            and _index_name_exists(app_ds, _IDEM_INDEX)):
        app_ds.execute("DROP INDEX IF EXISTS {0}".format(_IDEM_INDEX))
    ensure_doc_flow_edge_tables(app_ds)   # 索引补建 + 缺列补齐（视图已存在则跳过）

    stored = _stored_view_sql(app_ds)
    result.view_rebuilt = (
        stored is not None and _norm_sql(stored) == _expected_view_sql_norm()
    )
    missing_idx = _missing_schema_indexes(app_ds)
    result.index_restored = not missing_idx
    result.ok = result.view_rebuilt and result.index_restored
    if not result.ok:
        if not result.view_rebuilt:
            result.error = "视图重建后未达规范形态（检查库可写性）"
        elif _IDEM_INDEX in missing_idx:
            result.error = (
                "唯一索引 {0} 未恢复——通常因边表存在重复 7 元组"
                "（先清重复再重建；重建不改边数据）".format(_IDEM_INDEX)
            )
        else:
            result.error = "结构索引未恢复: {0}".format(", ".join(missing_idx))
    return result