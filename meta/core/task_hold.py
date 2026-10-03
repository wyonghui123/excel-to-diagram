# -*- coding: utf-8 -*-
"""[F1 2026-10-03] 任务 hold / release 事件化 + 当前态派生视图（不改状态列）

职责:
- 平台唯一的「执行侧阻塞」入口（task-model-design §12 F1 / 综合缝合 §6.3）：
  hold / release **只落 TASK_EVENT**（event_type = 'hold' | 'release'），
  **绝不改任何状态列**。行状态（业务事实，单据域写）≠ Task 状态（执行流程事实，
  任务引擎写）≠ hold（执行侧阻塞，本模块写）—— 三者各归其主（综合 §6.3）。
- 当前态由事件账**派生视图** `task_hold_current` 聚合（append-only + 严格交替
  ⇒ 差值派生）；UI 只读视图、不直查事件明细（§12.1 Q3）。
- 巡检：同形态兄弟巡检域 `hold_findings()` + `rebuild_hold_view()`，与 E7
  （doc_flow_reconcile）的 findings / rebuild 契约同形。**不并入 E7** —— E7 的
  scan / rebuild 以「应用库」为单一入参，而 hold 源表 task_events 在**平台库**，
  硬并入会污染 E7 的入参契约（Q3 落地时的显式选择）。

派生口径（不依赖时间戳精度）:
    active_flag = SUM(CASE event_type='hold' THEN 1 ELSE -1 END)
  task_events.id 为 uuid4（无单调性）、occurred_at 可能秒级并列，故「取最新一条」
  不可靠；而入口 API 保证同 (task_id, hold_code) 严格交替（重复 hold / 释放未激活
  均确定性拒绝），差值与最新态等价 —— 且差值 ∉ {0,1} 恰是「交替被破坏」的
  机器可检信号（HOLD_STATE_INCONSISTENT）。

纪律:
- append-only：本模块只 INSERT 事件、不 update / delete；纠正靠 release 再 hold。
- 不改状态列：hold / release 不写 tasks.status / finished_at（测试锁死该回归）。
- 写不自提交：事务由调用方持有（与 A3 `record_task_event` 同口径）。
- hold 原因编码 / 头行 / 履行行三级引用口径属业务域，平台只提供事件化载体
  （`payload.hold_code` + `line_refs`），不解释其语义。

对标: Oracle Fusion `DOO_HOLD_INSTANCES` / `DOO_HOLD_STEP_INSTANCES`
      （HOLD_CODE_ID / ACTIVE_FLAG / PENDING_FLAG；研究 §5.2）

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §12 F1 / §12.1 Q3
  docs/superpowers/specs/2026-10-02-orchestration-task-model-state-machine-synthesis.md §6.3
  docs/superpowers/specs/2026-09-30-oracle-fusion-fulfillment-orchestration-engine-research.md §5.2
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from meta.core.task_event_schema import TASK_EVENT_TABLE, record_task_event
from meta.core.task_schema import TASK_TABLE

# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

#: 派生视图名（UI 只读此视图）
HOLD_VIEW = "task_hold_current"

#: hold 事件类型（append-only 严格交替的一对）
HOLD_EVENT_TYPES: Tuple[str, ...] = ("hold", "release")

#: payload 内 hold 原因编码的键路径（视图分组键；语义归业务域）
HOLD_CODE_PATH = "$.hold_code"

#: 每类 finding 明细最多列出的样本数（超出折叠为总数）
_MAX_DETAIL = 20

_IN_LIST = ", ".join("'{0}'".format(t) for t in HOLD_EVENT_TYPES)


class TaskHoldError(RuntimeError):
    """hold / release 前置校验失败（重复 hold / 释放未激活 / 任务不存在等）。"""


# ─────────────────────────────────────────────────────────────────────────────
# 结果对象（与 E7 doc_flow_reconcile 的 Finding / RebuildResult 同形）
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HoldFinding:
    """一条 hold 巡检发现（机器可读 code + severity + 明细）。"""

    code: str
    severity: str          # error / warn
    detail: str


@dataclass
class HoldReport:
    """hold 巡检报告（只读快照）。"""

    hold_event_count: int = 0
    active_hold_count: int = 0
    findings: List[HoldFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def codes(self) -> List[str]:
        return [f.code for f in self.findings]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hold_event_count": self.hold_event_count,
            "active_hold_count": self.active_hold_count,
            "ok": self.ok,
            "warnings": [f.code for f in self.findings if f.severity == "warn"],
            "findings": [
                {"code": f.code, "severity": f.severity, "detail": f.detail}
                for f in self.findings
            ],
        }


@dataclass
class HoldRebuildResult:
    """派生视图重建结果（重建 = 写操作，仅动视图）。"""

    view_existed: bool = False       # 重建前视图是否存在
    view_rebuilt: bool = False       # 后置自检：视图存在且达规范形态
    ok: bool = False
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "view_existed": self.view_existed,
            "view_rebuilt": self.view_rebuilt,
            "ok": self.ok,
            "error": self.error,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 派生视图（规范 SQL 唯一事实来源）
# ─────────────────────────────────────────────────────────────────────────────

def canonical_hold_view_sql() -> str:
    """hold 当前态派生视图的规范 SQL（无 CREATE 前缀）。"""
    return (
        "SELECT task_id, "
        "json_extract(payload, '{path}') AS hold_code, "
        "SUM(CASE WHEN event_type = 'hold' THEN 1 ELSE -1 END) AS active_flag, "
        "MIN(occurred_at) AS first_hold_at, "
        "MAX(occurred_at) AS last_event_at, "
        "COUNT(*) AS event_count "
        "FROM {table} "
        "WHERE event_type IN ({in_list}) "
        "GROUP BY task_id, json_extract(payload, '{path}')"
    ).format(path=HOLD_CODE_PATH, table=TASK_EVENT_TABLE, in_list=_IN_LIST)


def _norm_sql(sql: str) -> str:
    """SQL 归一化（比较用）：去 IF NOT EXISTS / 折叠空白 / 统一小写。"""
    s = re.sub(r"if\s+not\s+exists", "", sql or "", flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip().rstrip(";").strip()
    return s.lower()


def _expected_view_sql_norm() -> str:
    return _norm_sql(
        "CREATE VIEW {0} AS {1}".format(HOLD_VIEW, canonical_hold_view_sql())
    )


def _stored_view_sql(data_source) -> Optional[str]:
    """sqlite_master 中该视图的创建语句；视图不存在返回 None。"""
    rows = data_source.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name=?", (HOLD_VIEW,)
    ).fetchall()
    if not rows or rows[0][0] is None:
        return None
    return rows[0][0]


def _table_exists(data_source, name: str) -> bool:
    try:
        rows = data_source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchall()
    except Exception:  # noqa: BLE001 - 库不可读视为不存在
        return False
    return bool(rows)


def hold_view_exists(data_source) -> bool:
    """派生视图是否存在（验收 / 巡检用）。"""
    return _stored_view_sql(data_source) is not None


def ensure_hold_view(data_source) -> bool:
    """建派生视图（幂等，启动期调用）。

    视图已存在则不动（漂移由巡检 / rebuild 处理，避免启动期静默覆盖人为改动）。

    Returns:
        True = 本次创建；False = 已存在（跳过）。
    """
    from meta.core.table_name_validator import register_table_name

    register_table_name(HOLD_VIEW)
    if hold_view_exists(data_source):
        return False
    data_source.execute(
        "CREATE VIEW {0} AS {1}".format(HOLD_VIEW, canonical_hold_view_sql())
    )
    return True


def rebuild_hold_view(data_source) -> HoldRebuildResult:
    """原子替换派生视图（显式触发；幂等可重入）。

    DROP + CREATE 在同一事务内，任一失败即回滚（旧视图保持不变，不出现
    「DROP 后建不回」的空窗）；后置自检闭环，未达规范形态即 ok=False + error
    （fail-loud，不假成功）。**绝不改事件数据**（append-only 铁律）。

    Args:
        data_source: 平台库数据源（task_events 所在库）

    Returns:
        HoldRebuildResult
    """
    result = HoldRebuildResult()
    result.view_existed = hold_view_exists(data_source)
    try:
        with data_source.transaction():
            data_source.execute("DROP VIEW IF EXISTS {0}".format(HOLD_VIEW))
            data_source.execute(
                "CREATE VIEW {0} AS {1}".format(HOLD_VIEW, canonical_hold_view_sql())
            )
    except Exception as e:  # noqa: BLE001 - 重建失败必须显式回报，不假成功
        result.error = "hold 派生视图重建失败（已回滚，原视图保持不变）: {0}".format(e)
        return result

    stored = _stored_view_sql(data_source)
    result.view_rebuilt = (
        stored is not None and _norm_sql(stored) == _expected_view_sql_norm()
    )
    result.ok = result.view_rebuilt
    if not result.ok:
        result.error = "hold 派生视图重建后未达规范形态（检查库可写性）"
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 读：当前态（只走派生视图，不直查事件明细）
# ─────────────────────────────────────────────────────────────────────────────

def current_holds(data_source, *, task_id: Optional[str] = None,
                  run_id: Optional[str] = None,
                  active_only: bool = True) -> List[Dict[str, Any]]:
    """当前 hold 态（读派生视图）。

    Args:
        data_source: 平台库数据源
        task_id: 限定任务（None = 全部）
        run_id: 限定 Run（经 tasks.workflow_run_id 关联；None = 全部）
        active_only: 仅返回激活态（active_flag = 1）

    Returns:
        [{task_id, hold_code, active_flag, first_hold_at, last_event_at, event_count}, ...]
    """
    if not hold_view_exists(data_source):
        raise TaskHoldError(
            "派生视图 {0} 不存在（先 ensure_hold_view / rebuild_hold_view；"
            "UI 只读视图，不直查事件明细）".format(HOLD_VIEW)
        )

    sql = ("SELECT v.task_id, v.hold_code, v.active_flag, v.first_hold_at, "
           "v.last_event_at, v.event_count FROM {0} v".format(HOLD_VIEW))
    if run_id:
        sql += " JOIN {0} t ON t.id = v.task_id".format(TASK_TABLE)
    where: List[str] = []
    params: List[Any] = []
    if task_id:
        where.append("v.task_id = ?")
        params.append(task_id)
    if run_id:
        where.append("t.workflow_run_id = ?")
        params.append(run_id)
    if active_only:
        where.append("v.active_flag = 1")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY v.task_id ASC, v.hold_code ASC"

    rows = data_source.execute(sql, tuple(params)).fetchall()
    return [
        {
            "task_id": r[0],
            "hold_code": r[1],
            "active_flag": int(r[2] or 0),
            "first_hold_at": r[3],
            "last_event_at": r[4],
            "event_count": int(r[5] or 0),
        }
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 写：hold / release（只 INSERT 事件，绝不改状态列）
# ─────────────────────────────────────────────────────────────────────────────

def _task_exists(data_source, task_id: str) -> bool:
    rows = data_source.execute(
        "SELECT 1 FROM {0} WHERE id = ?".format(TASK_TABLE), (task_id,)
    ).fetchall()
    return bool(rows)


def _active_flag(data_source, task_id: str, hold_code: str) -> int:
    """同 (task, hold_code) 的 hold−release 差值（不依赖视图，入口即用）。"""
    row = data_source.execute(
        "SELECT COALESCE(SUM(CASE WHEN event_type = 'hold' THEN 1 ELSE -1 END), 0) "
        "FROM {0} WHERE task_id = ? AND event_type IN ({1}) "
        "AND json_extract(payload, '{2}') = ?".format(
            TASK_EVENT_TABLE, _IN_LIST, HOLD_CODE_PATH),
        (task_id, hold_code),
    ).fetchone()
    return int(row[0] or 0)


def hold_task(data_source, task_id: str, *, hold_code: str, reason: str = "",
              actor: str = "", actor_kind: str = "", doc_ref: str = "",
              line_refs: Any = None, agent_session_id: str = "",
              trace_id: str = "", occurred_at: Optional[str] = None) -> str:
    """置 hold（只写一条 TASK_EVENT，**不改状态列**），返回事件 ID。

    前置校验（机器化，保证严格交替）:
      ① 任务存在；② hold_code 非空；③ 同 (task, hold_code) 当前未激活。

    Raises:
        TaskHoldError
    """
    code = (hold_code or "").strip()
    if not code:
        raise TaskHoldError("hold_code 不能为空（hold 原因编码是派生态的分组键）")
    if not _task_exists(data_source, task_id):
        raise TaskHoldError("任务不存在: {0!r}".format(task_id))

    flag = _active_flag(data_source, task_id, code)
    if flag != 0:
        raise TaskHoldError(
            "重复 hold 被拒绝：任务 {0} 的 hold_code={1!r} 当前 active_flag={2}"
            "（同一 hold 未释放前不可再次 hold；严格交替是派生态可聚合的前提）".format(
                task_id, code, flag)
        )

    return record_task_event(
        data_source, task_id=task_id, event_type="hold",
        actor=actor, actor_kind=actor_kind, reason=reason,
        payload={"hold_code": code, "reason": reason},
        doc_ref=doc_ref, line_refs=line_refs,
        agent_session_id=agent_session_id, trace_id=trace_id,
        occurred_at=occurred_at,
    )


def release_task(data_source, task_id: str, *, hold_code: str, reason: str = "",
                 actor: str = "", actor_kind: str = "", doc_ref: str = "",
                 line_refs: Any = None, agent_session_id: str = "",
                 trace_id: str = "", occurred_at: Optional[str] = None) -> str:
    """解除 hold（只写一条 TASK_EVENT，**不改状态列**），返回事件 ID。

    前置校验（机器化，保证严格交替）:
      ① 任务存在；② hold_code 非空；③ 同 (task, hold_code) 当前处于激活态（差值 = 1）。

    Raises:
        TaskHoldError
    """
    code = (hold_code or "").strip()
    if not code:
        raise TaskHoldError("hold_code 不能为空（release 须与 hold 同码配对）")
    if not _task_exists(data_source, task_id):
        raise TaskHoldError("任务不存在: {0!r}".format(task_id))

    flag = _active_flag(data_source, task_id, code)
    if flag != 1:
        raise TaskHoldError(
            "释放未激活 hold 被拒绝：任务 {0} 的 hold_code={1!r} 当前 active_flag={2}"
            "（仅当该 hold 处于激活态（差值 = 1）方可释放）".format(
                task_id, code, flag)
        )

    return record_task_event(
        data_source, task_id=task_id, event_type="release",
        actor=actor, actor_kind=actor_kind, reason=reason,
        payload={"hold_code": code, "reason": reason},
        doc_ref=doc_ref, line_refs=line_refs,
        agent_session_id=agent_session_id, trace_id=trace_id,
        occurred_at=occurred_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 巡检（只读；同形态兄弟巡检域）
# ─────────────────────────────────────────────────────────────────────────────

def _sample(lines: List[str]) -> str:
    shown = "; ".join(lines[:_MAX_DETAIL])
    if len(lines) > _MAX_DETAIL:
        shown += " …（共 {0} 项）".format(len(lines))
    return shown


def hold_findings(data_source) -> HoldReport:
    """hold 一致性巡检（只读）。

    巡检域:
      ① 事件账存在性 / 视图存在性与 SQL 漂移
      ② 交替不变式：同 (task, hold_code) 的 active_flag ∉ {0, 1}
      ③ 归属完整性：hold / release 事件缺 hold_code

    Args:
        data_source: 平台库数据源（task_events 所在库）

    Returns:
        HoldReport（findings 为空即 ok）
    """
    report = HoldReport()
    findings: List[HoldFinding] = []

    if not _table_exists(data_source, TASK_EVENT_TABLE):
        findings.append(HoldFinding(
            "HOLD_EVENT_TABLE_MISSING", "error",
            "事件账 {0} 不存在（该库未启用任务事件账）".format(TASK_EVENT_TABLE),
        ))
        report.findings = findings
        return report

    rows = data_source.execute(
        "SELECT task_id, event_type, json_extract(payload, '{0}'), occurred_at "
        "FROM {1} WHERE event_type IN ({2})".format(
            HOLD_CODE_PATH, TASK_EVENT_TABLE, _IN_LIST)
    ).fetchall()
    report.hold_event_count = len(rows)

    no_code: List[str] = []
    groups: Dict[Tuple[str, str], int] = {}
    for task_id, event_type, code, occurred in rows:
        if not code:
            no_code.append("{0}:{1}@{2}".format(task_id, event_type, occurred))
            continue
        key = (task_id, code)
        groups[key] = groups.get(key, 0) + (1 if event_type == "hold" else -1)

    report.active_hold_count = sum(1 for v in groups.values() if v == 1)

    if no_code:
        findings.append(HoldFinding(
            "HOLD_EVENT_WITHOUT_CODE", "error",
            "hold / release 事件缺 hold_code {0} 条（无法归属派生态；append-only "
            "账不可改，须以新事件纠正）: {1}".format(len(no_code), _sample(no_code)),
        ))

    bad = sorted(
        [(k, v) for k, v in groups.items() if v not in (0, 1)],
        key=lambda kv: (str(kv[0][0]), str(kv[0][1])),
    )
    if bad:
        lines = ["{0}/{1} active_flag={2}".format(k[0], k[1], v) for k, v in bad]
        findings.append(HoldFinding(
            "HOLD_STATE_INCONSISTENT", "error",
            "hold / release 未严格交替 {0} 组（差值 ∉ {{0,1}}；事件账被绕过入口 API "
            "直写或人为误写）: {1}".format(len(bad), _sample(lines)),
        ))

    stored_sql = _stored_view_sql(data_source)
    if stored_sql is None:
        findings.append(HoldFinding(
            "HOLD_VIEW_MISSING", "error",
            "派生视图 {0} 缺失（可用 rebuild_hold_view 重建）".format(HOLD_VIEW),
        ))
    elif _norm_sql(stored_sql) != _expected_view_sql_norm():
        findings.append(HoldFinding(
            "HOLD_VIEW_SQL_DRIFT", "error",
            "派生视图定义与规范 SQL 不一致（视图被篡改；可用 rebuild_hold_view 重建）",
        ))

    report.findings = findings
    return report