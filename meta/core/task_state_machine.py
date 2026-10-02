# -*- coding: utf-8 -*-
"""[A2 2026-10-02] 统一任务状态机 — 11 态迁移表 + 迁移守卫（纯逻辑，无持久化）

职责:
- 平台提供**唯一**的 Task 状态机语义（跨应用必须同一套：唯一权威判据，
  §12.1 A2）。定义「谁能从哪个态到哪个态」，其余引擎按此执行。
- 只做「结构 + 守卫」：不做 DB 读写、不发事件、不写 TASK_EVENT、不落迁移日志。
  事件账（每次迁移 = 一条 TASK_EVENT + 一条 WORKLOG）是 A3 的交付物。

分层纪律:
- 状态集合单一事实源：直接引用 `task_schema.TASK_STATUSES`，不另立副本。
- 守卫 **fail-closed**：上下文缺字段 = 拒绝（宁可拦住，不可放行越权）。
- 守卫**不看库**：所有外部事实（deps 状态、候选池、超时秒数……）由调用方
  （引擎 A4/A5）查好后放进 `TransitionContext`——本模块因此可单测、无副作用。

对应方案:
  docs/superpowers/specs/2026-09-07-task-model-design.md §7.2（状态机 / 迁移表）
  §9.7（四眼原则）、§12.1 A2
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, Optional, Tuple

from meta.core.task_schema import TASK_STATUSES

# 状态全集（单一事实源：task_schema）
TASK_STATES: FrozenSet[str] = frozenset(TASK_STATUSES)

# 终态：进入后不再有出边（§7.2 mermaid 中 done / cancelled / skipped 指向 [*]）
# 注意：`dead` 不是终态——`dead --> ready: 人工干预后重放`
TERMINAL_STATES: FrozenSet[str] = frozenset({"done", "cancelled", "skipped"})


class TaskTransitionError(Exception):
    """任务状态迁移非法（结构不合法，或守卫未通过）。"""


@dataclass(frozen=True)
class TransitionRule:
    """一条迁移规则（§7.2 迁移表一行）。"""

    from_state: str
    to_state: str
    trigger: str = ""          # 触发者 / 场景（文档口径）
    guard: Optional[str] = None  # 守卫名（None = 无守卫）
    side_effect: str = ""      # 副作用（文档口径，由引擎实现）


# ─────────────────────────────────────────────────────────────────────────────
# 迁移表（逐条抄 §7.2 mermaid，共 18 条；不发明）
# ─────────────────────────────────────────────────────────────────────────────

TRANSITION_TABLE: Tuple[TransitionRule, ...] = (
    TransitionRule("pending", "ready", "引擎调度器", "deps_satisfied",
                   "发 task.ready 事件；进入分配队列"),
    TransitionRule("pending", "cancelled", "创建者/引擎", None, ""),
    TransitionRule("ready", "claimed", "human 抢单 / 引擎自动分派", "claimable",
                   "记 claim 人与时间"),
    TransitionRule("ready", "skipped", "引擎（条件边判定）", "edge_condition_failed",
                   "通知依赖方按 skipped 语义处理"),
    TransitionRule("claimed", "in_progress", "executor", None, "注入 trace span"),
    TransitionRule("claimed", "ready", "引擎（自动回收）", "claim_timed_out",
                   "回收进入队列，通知原认领人"),
    TransitionRule("in_progress", "waiting_approval", "executor（needs_review / interrupt / 人工提交）",
                   "reviewer_configured", "生成审核子任务（human + type=approval）"),
    TransitionRule("waiting_approval", "in_progress", "审核人（驳回返修）", "review_permission",
                   "审核意见写入 WORKLOG"),
    TransitionRule("waiting_approval", "done", "审核人（通过）", "approve_authorized", ""),
    TransitionRule("waiting_approval", "failed", "审核人（拒绝且不可返修）", "review_permission", ""),
    TransitionRule("in_progress", "blocked", "executor（外部等待/依赖失败）", None, ""),
    TransitionRule("blocked", "in_progress", "引擎（阻塞解除）", None, ""),
    TransitionRule("in_progress", "done", "executor 完成", "acceptance_passed",
                   "outputs 回写；触发下游 deps 重算"),
    TransitionRule("in_progress", "failed", "executor 异常 / timeout / cancel", None,
                   "按 retry_policy 判定：未超限 → ready，超限 → dead"),
    TransitionRule("in_progress", "cancelled", "创建者/引擎（若可中断）", None, ""),
    TransitionRule("failed", "ready", "引擎（retry 未超限，指数退避）", "retry_available", ""),
    TransitionRule("failed", "dead", "引擎（retry 超限）", "retry_exhausted",
                   "死信 + 告警"),
    TransitionRule("dead", "ready", "人工干预后重放", None, ""),
)

# 索引：from → {to...}
TRANSITIONS: Dict[str, FrozenSet[str]] = {}
for _r in TRANSITION_TABLE:
    TRANSITIONS.setdefault(_r.from_state, frozenset())  # type: ignore[arg-type]
    TRANSITIONS[_r.from_state] = TRANSITIONS[_r.from_state] | {_r.to_state}

_RULES_BY_PAIR: Dict[Tuple[str, str], TransitionRule] = {
    (r.from_state, r.to_state): r for r in TRANSITION_TABLE
}


# ─────────────────────────────────────────────────────────────────────────────
# 守卫（fail-closed；上下文由引擎查库后注入）
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GuardResult:
    ok: bool
    reason: str = ""


@dataclass
class TransitionContext:
    """迁移守卫所需的外部事实（由引擎查好后注入；未提供的字段为 None）。

    本类只承载「调用方已知的事实」，不含 DB 句柄——保证守卫是纯函数。
    """

    actor: Optional[str] = None                 # 操作者 id（user_id / agent_id / system）
    actor_kind: Optional[str] = None            # human / agent / system

    deps_satisfied: Optional[bool] = None       # 全部前置 deps 为 done/skipped
    actor_in_candidates: Optional[bool] = None  # 认领人在候选池内
    assign_policy_hit: Optional[bool] = None    # 分配策略命中
    edge_condition_satisfied: Optional[bool] = None  # 上游 edge.when 表达式是否满足
    claim_elapsed_seconds: Optional[float] = None
    claim_timeout_seconds: Optional[float] = None
    reviewer_configured: Optional[bool] = None
    actor_has_review_permission: Optional[bool] = None
    submitter_id: Optional[str] = None          # 提交人（四眼原则比对基准）
    requires_four_eyes: Optional[bool] = None   # type=approval 时为 True（§9.7）
    acceptance_passed: Optional[bool] = None
    retry_exhausted: Optional[bool] = None


def _missing(field_name: str) -> GuardResult:
    return GuardResult(False, f"guard context missing: {field_name}")


def _guard_deps_satisfied(ctx: TransitionContext) -> GuardResult:
    if ctx.deps_satisfied is None:
        return _missing("deps_satisfied")
    return GuardResult(bool(ctx.deps_satisfied),
                       "" if ctx.deps_satisfied else "前置依赖未全部 done/skipped")


def _guard_claimable(ctx: TransitionContext) -> GuardResult:
    if ctx.actor_in_candidates is None and ctx.assign_policy_hit is None:
        return _missing("actor_in_candidates/assign_policy_hit")
    ok = bool(ctx.actor_in_candidates) or bool(ctx.assign_policy_hit)
    return GuardResult(ok, "" if ok else "认领人不在候选池且分配策略未命中")


def _guard_edge_condition_failed(ctx: TransitionContext) -> GuardResult:
    if ctx.edge_condition_satisfied is None:
        return _missing("edge_condition_satisfied")
    ok = not ctx.edge_condition_satisfied
    return GuardResult(ok, "" if ok else "edge 条件满足，不能跳过")


def _guard_claim_timed_out(ctx: TransitionContext) -> GuardResult:
    if ctx.claim_elapsed_seconds is None or ctx.claim_timeout_seconds is None:
        return _missing("claim_elapsed_seconds/claim_timeout_seconds")
    ok = ctx.claim_elapsed_seconds > ctx.claim_timeout_seconds
    return GuardResult(ok, "" if ok else "认领未超时，不能回收")


def _guard_reviewer_configured(ctx: TransitionContext) -> GuardResult:
    if ctx.reviewer_configured is None:
        return _missing("reviewer_configured")
    return GuardResult(bool(ctx.reviewer_configured),
                       "" if ctx.reviewer_configured else "未配置审核人")


def _guard_review_permission(ctx: TransitionContext) -> GuardResult:
    if ctx.actor_has_review_permission is None:
        return _missing("actor_has_review_permission")
    return GuardResult(bool(ctx.actor_has_review_permission),
                       "" if ctx.actor_has_review_permission else "审核权限校验未通过")


def _guard_approve_authorized(ctx: TransitionContext) -> GuardResult:
    """审核通过：审核权限 + 四眼原则（§9.7 type=approval 时审核人 ≠ 提交人）。"""
    perm = _guard_review_permission(ctx)
    if not perm.ok:
        return perm
    if ctx.requires_four_eyes is None:
        return _missing("requires_four_eyes")
    if not ctx.requires_four_eyes:
        return GuardResult(True)
    if ctx.submitter_id is None or ctx.actor is None:
        return _missing("submitter_id/actor")
    ok = ctx.actor != ctx.submitter_id
    return GuardResult(ok, "" if ok else "四眼原则：审核人不得为提交人（maker-checker）")


def _guard_acceptance_passed(ctx: TransitionContext) -> GuardResult:
    if ctx.acceptance_passed is None:
        return _missing("acceptance_passed")
    return GuardResult(bool(ctx.acceptance_passed),
                       "" if ctx.acceptance_passed else "验收未通过（checklist / eval 阈值）")


def _guard_retry_available(ctx: TransitionContext) -> GuardResult:
    if ctx.retry_exhausted is None:
        return _missing("retry_exhausted")
    ok = not ctx.retry_exhausted
    return GuardResult(ok, "" if ok else "重试已超限，应转死信")


def _guard_retry_exhausted(ctx: TransitionContext) -> GuardResult:
    if ctx.retry_exhausted is None:
        return _missing("retry_exhausted")
    return GuardResult(bool(ctx.retry_exhausted),
                       "" if ctx.retry_exhausted else "重试未超限，不能转死信")


GUARDS: Dict[str, Callable[[TransitionContext], GuardResult]] = {
    "deps_satisfied": _guard_deps_satisfied,
    "claimable": _guard_claimable,
    "edge_condition_failed": _guard_edge_condition_failed,
    "claim_timed_out": _guard_claim_timed_out,
    "reviewer_configured": _guard_reviewer_configured,
    "review_permission": _guard_review_permission,
    "approve_authorized": _guard_approve_authorized,
    "acceptance_passed": _guard_acceptance_passed,
    "retry_available": _guard_retry_available,
    "retry_exhausted": _guard_retry_exhausted,
}


# ─────────────────────────────────────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────────────────────────────────────

def validate_state(state: str) -> str:
    """校验状态名合法，返回原值；否则抛 TaskTransitionError。"""
    if state not in TASK_STATES:
        raise TaskTransitionError(f"未知任务状态: {state!r}（合法值见 TASK_STATES）")
    return state


def is_terminal(state: str) -> bool:
    """是否为终态（done / cancelled / skipped）。"""
    validate_state(state)
    return state in TERMINAL_STATES


def allowed_transitions(from_state: str) -> FrozenSet[str]:
    """返回某状态的合法出边集合（空集 = 无出边）。"""
    validate_state(from_state)
    return TRANSITIONS.get(from_state, frozenset())


def can_transition(from_state: str, to_state: str) -> bool:
    """结构校验：该迁移是否在表中（不看守卫）。"""
    return to_state in allowed_transitions(from_state)


def assert_transition(from_state: str, to_state: str) -> TransitionRule:
    """结构校验并返回规则；非法迁移抛 TaskTransitionError（不看守卫）。"""
    validate_state(from_state)
    validate_state(to_state)
    rule = _RULES_BY_PAIR.get((from_state, to_state))
    if rule is None:
        raise TaskTransitionError(
            f"非法迁移: {from_state} → {to_state}"
            f"（合法出边: {sorted(allowed_transitions(from_state)) or '无（终态）'}）"
        )
    return rule


def evaluate_transition(from_state: str, to_state: str,
                        ctx: Optional[TransitionContext] = None) -> GuardResult:
    """结构 + 守卫综合判定；返回 GuardResult（不抛异常，便于上层收集原因）。"""
    try:
        rule = assert_transition(from_state, to_state)
    except TaskTransitionError as e:
        return GuardResult(False, str(e))

    if rule.guard is None:
        return GuardResult(True)

    guard_fn = GUARDS[rule.guard]
    if ctx is None:
        return GuardResult(False, f"guard context missing: {rule.guard}")
    return guard_fn(ctx)


def require_transition(from_state: str, to_state: str,
                       ctx: Optional[TransitionContext] = None) -> TransitionRule:
    """结构 + 守卫综合判定；不通过则抛 TaskTransitionError（引擎调用入口）。"""
    result = evaluate_transition(from_state, to_state, ctx)
    if not result.ok:
        raise TaskTransitionError(
            f"迁移被拒: {from_state} → {to_state}：{result.reason}"
        )
    return assert_transition(from_state, to_state)