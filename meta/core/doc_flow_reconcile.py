# -*- coding: utf-8 -*-
"""[单据流 Phase 2] DOC_FLOW 一致性巡检 + 投影重建（S7 最小版，触发式）

契约（doc-flow spec §9.5 S7 / §9.6 Phase 2；roadmap §五 S7）::

    S7 巡检最小版（触发式脚本）→ 验收：对账可发现人为改账
    巡检域（最小版 3 域，2026-10-02 用户拍板"精简 3 域"）:
      ① 结构域    边表缺失 / 唯一幂等索引缺失 / 消耗视图缺失 / 视图 SQL 漂移
      ② 边域      7 元组幂等键重复 / 同 6 元组异规则 active+normal（R4 双重消耗）/
                  status·quantity_sign·quantity 域值非法
      ③ 视图对账  边表复算 vs 视图查询逐行比对（数值侧双保险；含红字口径）

    投影重建（显式触发，CLI --rebuild）：视图 DROP + 规范重建 + 缺失索引补建；
    **绝不改边数据**（append-only 铁律）；后置自检闭环——SchemaMigrator 对索引
    创建失败吞错（重复键挡唯一索引），必须自检，缺一即 fail-loud 不假成功。

边界（如实声明，不扩范围）:
- **语义侧改账不可检**（无物化快照对照；§14 R3 完整对账依赖快照机制，未来
  落地后纳入）——具体包括: ① 人为删正常边（静默少消耗）；② 手改 quantity
  为另一合法正数；③ 手翻 status active→reversed（合法值；边表定稿 17 列无
  冲销审计位，E6 的 reversed_by 仅记日志，引擎翻转与手工翻转不可区分）；
  ④ 插孤儿边（target 不存在）；⑤ 改 rule_id 为不存在规则。以上需读事实对象
  / 规则表或快照对照，属完全体。
- 本版不做业务锚/孤儿边/超耗检查（2026-10-02 用户拍板精简 3 域）。
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
    edge_table_exists,
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
        return not self.findings

    def codes(self) -> List[str]:
        return [f.code for f in self.findings]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_count": self.edge_count,
            "active_count": self.active_count,
            "ok": self.ok,
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
# 巡检（只读）
# ─────────────────────────────────────────────────────────────────────────────

def scan(app_ds) -> ReconcileReport:
    """一致性巡检（只读，3 域）。

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

    if not _unique_index_ok(app_ds, _IDEM_INDEX):
        findings.append(Finding(
            "IDEM_INDEX_MISSING", "error",
            "唯一幂等索引 {0} 缺失或已退化为非唯一（7 元组防重放保障失效；"
            "可用 --rebuild 补建）".format(_IDEM_INDEX),
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
    """按边表重建投影：视图 DROP + 规范重建 + 缺失索引补建（幂等可重入）。

    **绝不改边数据**（append-only 铁律）。后置自检闭环：SchemaMigrator 对
    索引/视图创建失败均吞错（重复键挡唯一索引即静默失败），故重建后逐项
    复核，缺一即 ok=False + error（fail-loud，不假成功）。

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
    app_ds.execute("DROP VIEW IF EXISTS {0}".format(DOC_FLOW_CONSUMED_VIEW))
    # 同名非唯一索引（被篡改）会挡住 ensure 的 CREATE INDEX IF NOT EXISTS ——
    # 先摘除，交给 ensure 重建为唯一索引（重复键仍会 fail-loud，见后置自检）
    if (not _unique_index_ok(app_ds, _IDEM_INDEX)
            and _index_name_exists(app_ds, _IDEM_INDEX)):
        app_ds.execute("DROP INDEX IF EXISTS {0}".format(_IDEM_INDEX))
    ensure_doc_flow_edge_tables(app_ds)   # 视图 IF NOT EXISTS 建回 + 索引补建

    stored = _stored_view_sql(app_ds)
    result.view_rebuilt = (
        stored is not None and _norm_sql(stored) == _expected_view_sql_norm()
    )
    result.index_restored = _unique_index_ok(app_ds, _IDEM_INDEX)
    result.ok = result.view_rebuilt and result.index_restored
    if not result.ok:
        if not result.view_rebuilt:
            result.error = "视图重建后未达规范形态（检查库可写性）"
        else:
            result.error = (
                "唯一索引 {0} 未恢复——通常因边表存在重复 7 元组"
                "（先清重复再重建；重建不改边数据）".format(_IDEM_INDEX)
            )
    return result