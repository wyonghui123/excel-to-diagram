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

from dataclasses import dataclass
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
# 迁移表（§7.2 mermaid 18 条 + §9.13.4.2-3 补齐取消出边 4 条 = 22 条；不发明）
# ─────────────────────────────────────────────────────────────────────────────

TRANSITION_TABLE: Tuple[TransitionRule, ...] = (
    TransitionRule("pending", "ready", "引擎调度器", "deps_satisfied",
                   "发 task.ready 事件；进入分配队列"),
    TransitionRule("pending", "cancelled", "创建者/引擎", None, ""),
    TransitionRule("ready", "claimed", "human 抢单 / 引擎自动分派", "claimable",
                   "记 claim 人与时间"),
    TransitionRule("ready", "skipped", "引擎（条件边判定）", "edge_condition_failed",
                   "通知依赖方按 skipped 语义处理"),
    TransitionRule("ready", "cancelled", "创建者/管理员（取消）", None, ""),
    TransitionRule("claimed", "in_progress", "executor", None, "注入 trace span"),
    TransitionRule("claimed", "ready", "引擎（自动回收）", "claim_timed_out",
                   "回收进入队列，通知原认领人"),
    TransitionRule("claimed", "cancelled", "创建者/管理员（取消）", None, ""),
    TransitionRule("in_progress", "waiting_approval", "executor（needs_review / interrupt / 人工提交）",
                   "reviewer_configured", "生成审核子任务（human + type=approval）"),
    TransitionRule("waiting_approval", "in_progress", "审核人（驳回返修）", "review_permission",
                   "审核意见写入 WORKLOG"),
    TransitionRule("waiting_approval", "done", "审核人（通过）", "approve_authorized", ""),
    TransitionRule("waiting_approval", "failed", "审核人（拒绝且不可返修）", "review_permission", ""),
    TransitionRule("waiting_approval", "cancelled", "创建者/管理员（取消）", None, ""),
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
    TransitionRule("failed", "cancelled", "创建者/管理员（取消）", None, ""),
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


def check_meta_object_status_update(meta_obj, old_record, changes) -> None:
    """[G7 2026-11-02] 通用更新路径的状态迁移守卫。

    对象声明 `requires_state_machine: true` 且本次更新要改 `status` 时，
    以库中旧状态为 from、请求新状态为 to 走 `require_transition`
    （结构 + 守卫，守卫 fail-closed）。非法迁移抛 `TaskTransitionError`。
    未改 status / 拿不到旧状态 / 状态未变化时不做校验。
    """
    if not meta_obj.requires_state_machine():
        return
    if not isinstance(changes, dict) or "status" not in changes:
        return
    new_status = changes.get("status")
    old_status = (old_record or {}).get("status") if isinstance(old_record, dict) else None
    if old_status is None or str(old_status) == "":
        return
    if str(old_status) == str(new_status):
        return
    require_transition(str(old_status), str(new_status))


# ─────────────────────────────────────────────────────────────────────────────
# 动作目录（spec §9.13.4.2 / D-AP-17）
# 声明「状态 × 类型 → 可用动作」，REST 只做权限映射，前端只按返回渲染按钮。
# 与迁移表同源：本模块只做结构声明，不查库、不鉴权。
# ─────────────────────────────────────────────────────────────────────────────

#: 非终态（可改派 / 可挂起 / 可取消的执行区间；`dead` 可人工重放故列入）
ACTIVE_STATES: FrozenSet[str] = TASK_STATES - TERMINAL_STATES


@dataclass(frozen=True)
class TaskAction:
    """一个可对任务执行的动作（状态区间 + 端点 + 权限码三合一）。"""

    action: str
    label: str
    endpoint: str        # 「METHOD /path」，`{id}` 由调用方替换
    allowed_from: FrozenSet[str]
    to_state: str = ""   # 目标状态；'' = 不改任务状态（侧通道：改派 / 参与 / 挂起）
    types: Optional[FrozenSet[str]] = None   # None = 不限任务类型
    permission: str = "task.view"
    available: bool = True    # 端点是否已上线（False = 已声明、待实现）
    confirm: bool = False     # 前端是否需要二次确认
    note: str = ""


# 展示顺序 = 详情抽屉按钮顺序（先可推进的，再改派/挂起/撤回/取消）
TASK_ACTIONS: Tuple[TaskAction, ...] = (
    TaskAction("claim", "认领", "POST /api/v1/tasks/{id}/claim",
               frozenset({"ready"}), to_state="claimed",
               permission="task.claim"),
    TaskAction("start", "启动执行", "POST /api/v1/tasks/{id}/start",
               frozenset({"ready", "claimed", "in_progress"}),
               permission="admin"),
    TaskAction("decision", "审批决策", "POST /api/v1/tasks/{id}/decision",
               frozenset({"waiting_approval"}), types=frozenset({"approval"}),
               permission="{bo}:approve", confirm=True,
               note="approve / reject / allow_rework 的目标态由决策协议裁决"),
    TaskAction("participate", "登记参与", "POST /api/v1/tasks/{id}/participate",
               frozenset({"waiting_approval"}), types=frozenset({"approval"}),
               permission="task.view"),
    TaskAction("reassign", "改派", "POST /api/v1/tasks/{id}/assign",
               ACTIVE_STATES, permission="task.assign", confirm=True,
               note="审批任务的服务层附加约束：仅 waiting_approval + 目标非提交人"),
    TaskAction("delegate", "委托", "POST /api/v1/task-delegations",
               ACTIVE_STATES, permission="task.delegate", available=False,
               note="当前仅有委托单端点，任务级委托待补"),
    TaskAction("hold", "挂起", "POST /api/v1/tasks/{id}/hold",
               ACTIVE_STATES, permission="task.hold", confirm=True,
               note="只写 task_events（不改状态列）；body 需 hold_code"),
    TaskAction("resume", "解除挂起", "POST /api/v1/tasks/{id}/resume",
               ACTIVE_STATES, permission="task.hold",
               note="与 hold 严格交替；只写 task_events（不改状态列）"),
    TaskAction("release", "释放认领", "POST /api/v1/tasks/{id}/release",
               frozenset({"claimed"}), to_state="ready",
               permission="task.claim", available=False,
               note="待补（迁移表已含 claimed→ready 回收边）"),
    TaskAction("withdraw", "撤回", "POST /api/v1/tasks/{id}/withdraw",
               frozenset({"waiting_approval"}), types=frozenset({"approval"}),
               permission="owner", confirm=True,
               note="仅提交人且无有效 approve；单据回退（§9.13.4.2 第 4 条）"),
    TaskAction("cancel", "取消", "POST /api/v1/tasks/{id}/cancel",
               frozenset({"pending", "ready", "claimed", "in_progress",
                          "failed", "waiting_approval"}),
               permission="owner_or_admin", confirm=True,
               note="§9.13.4.2 第 3 条：created_by 或 admin；审批撤回走 withdraw"),
)

TASK_ACTION_MAP: Dict[str, TaskAction] = {a.action: a for a in TASK_ACTIONS}


def applicable_actions(state: str, task_type: Optional[str] = None,
                       *, include_unavailable: bool = False
                       ) -> Tuple[TaskAction, ...]:
    """返回某状态（+任务类型）下结构可用的动作。

    只看「状态 × 类型 × 端点是否上线」，**不看用户权限**；权限由 REST 层映射。
    """
    validate_state(state)
    result = []
    for decl in TASK_ACTIONS:
        if state not in decl.allowed_from:
            continue
        if decl.types is not None and str(task_type or "") not in decl.types:
            continue
        if not decl.available and not include_unavailable:
            continue
        result.append(decl)
    return tuple(result)