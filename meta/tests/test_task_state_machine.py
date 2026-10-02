import pytest

pytestmark = pytest.mark.unit

"""
后端测试套件 - 统一任务状态机
测试 meta.core.task_state_machine 模块（A2：11 态迁移表 + 迁移守卫）

覆盖目标（对齐 §12.1 Phase 0 验收「全量迁移表有单测覆盖」）：
  1. 迁移表与 §7.2 spec 一致（18 条，逐条核对）
  2. 11×11 全量组合：声明外的迁移一律拒绝
  3. 终态无出边（dead 除外，可人工重放）
  4. 每个守卫的通过 / 拒绝 / 缺上下文 fail-closed
"""

from meta.core.task_state_machine import (
    GUARDS,
    TERMINAL_STATES,
    TASK_STATES,
    TRANSITION_TABLE,
    TaskTransitionError,
    TransitionContext,
    allowed_transitions,
    assert_transition,
    can_transition,
    evaluate_transition,
    is_terminal,
    require_transition,
    validate_state,
)

# §7.2 mermaid 派生的期望迁移集合（测试侧独立声明，用于与模块实现互校）
EXPECTED_TRANSITIONS = {
    ("pending", "ready"),
    ("pending", "cancelled"),
    ("ready", "claimed"),
    ("ready", "skipped"),
    ("claimed", "in_progress"),
    ("claimed", "ready"),
    ("in_progress", "waiting_approval"),
    ("waiting_approval", "in_progress"),
    ("waiting_approval", "done"),
    ("waiting_approval", "failed"),
    ("in_progress", "blocked"),
    ("blocked", "in_progress"),
    ("in_progress", "done"),
    ("in_progress", "failed"),
    ("in_progress", "cancelled"),
    ("failed", "ready"),
    ("failed", "dead"),
    ("dead", "ready"),
}

EXPECTED_STATES = {
    "pending", "ready", "claimed", "in_progress", "blocked",
    "waiting_approval", "done", "failed", "cancelled", "skipped", "dead",
}


def ctx_for_guard(guard_name):
    """为某守卫构造最小「可通过」上下文（也顺带证明守卫无多余依赖）。"""
    mapping = {
        None: TransitionContext(),
        "deps_satisfied": TransitionContext(deps_satisfied=True),
        "claimable": TransitionContext(actor_in_candidates=True),
        "edge_condition_failed": TransitionContext(edge_condition_satisfied=False),
        "claim_timed_out": TransitionContext(claim_elapsed_seconds=400,
                                             claim_timeout_seconds=300),
        "reviewer_configured": TransitionContext(reviewer_configured=True),
        "review_permission": TransitionContext(actor_has_review_permission=True),
        "approve_authorized": TransitionContext(
            actor_has_review_permission=True, requires_four_eyes=True,
            actor="bob", submitter_id="alice"),
        "acceptance_passed": TransitionContext(acceptance_passed=True),
        "retry_available": TransitionContext(retry_exhausted=False),
        "retry_exhausted": TransitionContext(retry_exhausted=True),
    }
    return mapping[guard_name]


class TestTransitionTable:
    """迁移表与 §7.2 spec 一致性"""

    def test_state_set_matches_spec(self):
        """TC-TSM-001: 状态全集为 11 态"""
        assert TASK_STATES == EXPECTED_STATES
        assert len(TASK_STATES) == 11

    def test_transition_table_matches_spec(self):
        """TC-TSM-002: 迁移表恰为 spec 派生的 18 条"""
        actual = {(r.from_state, r.to_state) for r in TRANSITION_TABLE}
        assert actual == EXPECTED_TRANSITIONS
        assert len(actual) == 18

    def test_no_duplicate_rule(self):
        """TC-TSM-003: 同一 (from,to) 不重复声明"""
        pairs = [(r.from_state, r.to_state) for r in TRANSITION_TABLE]
        assert len(pairs) == len(set(pairs))

    def test_terminal_states(self):
        """TC-TSM-004: 终态 = done/cancelled/skipped"""
        assert TERMINAL_STATES == {"done", "cancelled", "skipped"}

    def test_every_non_terminal_state_has_out_edge(self):
        """TC-TSM-005: 每个非终态至少有一条出边（dead 亦非终态）"""
        for state in TASK_STATES - TERMINAL_STATES:
            assert allowed_transitions(state), f"{state} 无出边"

    def test_terminal_states_have_no_out_edge(self):
        """TC-TSM-006: 终态无出边"""
        for state in TERMINAL_STATES:
            assert allowed_transitions(state) == frozenset()
            assert is_terminal(state) is True

    def test_dead_is_not_terminal(self):
        """TC-TSM-007: dead 可人工重放（dead → ready），不是终态"""
        assert is_terminal("dead") is False
        assert allowed_transitions("dead") == {"ready"}


class TestStructuralValidation:
    """结构校验：声明内放行、声明外拒绝"""

    def test_all_declared_transitions_allowed(self):
        """TC-TSM-010: 全部声明迁移结构上可通过"""
        for frm, to in EXPECTED_TRANSITIONS:
            assert can_transition(frm, to) is True, f"{frm}→{to} 应放行"
            assert assert_transition(frm, to).to_state == to

    def test_all_undeclared_combinations_rejected(self):
        """TC-TSM-011: 11×11 全量组合中，声明外的一律拒绝"""
        for frm in TASK_STATES:
            for to in TASK_STATES:
                expected = (frm, to) in EXPECTED_TRANSITIONS
                assert can_transition(frm, to) is expected, f"{frm}→{to}"

    def test_assert_transition_raises_on_illegal(self):
        """TC-TSM-012: 非法迁移抛 TaskTransitionError"""
        with pytest.raises(TaskTransitionError) as exc:
            assert_transition("pending", "done")
        assert "非法迁移" in str(exc.value)

    def test_assert_transition_raises_from_terminal(self):
        """TC-TSM-013: 终态出发的迁移一律拒绝"""
        for state in TERMINAL_STATES:
            with pytest.raises(TaskTransitionError):
                assert_transition(state, "ready")

    def test_unknown_state_rejected(self):
        """TC-TSM-014: 未知状态名一律拒绝"""
        for bad in ("", "PENDING", "completed", "started"):
            with pytest.raises(TaskTransitionError):
                validate_state(bad)
            with pytest.raises(TaskTransitionError):
                can_transition(bad, "ready")
            with pytest.raises(TaskTransitionError):
                is_terminal(bad)

    def test_allowed_transitions_returns_frozenset(self):
        """TC-TSM-015: 出边集合为 frozenset"""
        assert isinstance(allowed_transitions("in_progress"), frozenset)
        assert allowed_transitions("in_progress") == {
            "waiting_approval", "blocked", "done", "failed", "cancelled"}


class TestGuards:
    """守卫：通过 / 拒绝 / fail-closed"""

    def test_every_rule_guard_is_registered(self):
        """TC-TSM-020: 迁移表引用的守卫均已注册"""
        for rule in TRANSITION_TABLE:
            if rule.guard is not None:
                assert rule.guard in GUARDS, f"未注册守卫: {rule.guard}"

    def test_every_guard_passes_with_satisfying_ctx(self):
        """TC-TSM-021: 每个守卫在满足上下文时放行"""
        for name, fn in GUARDS.items():
            result = fn(ctx_for_guard(name))
            assert result.ok is True, f"守卫 {name} 应放行：{result.reason}"

    def test_missing_context_fails_closed(self):
        """TC-TSM-022: 缺上下文一律拒绝（fail-closed）"""
        for name, fn in GUARDS.items():
            result = fn(TransitionContext())
            assert result.ok is False, f"守卫 {name} 缺上下文应拒绝"
            assert result.reason

    def test_deps_not_satisfied_rejected(self):
        """TC-TSM-023: 依赖未满足不能 ready"""
        ctx = TransitionContext(deps_satisfied=False)
        assert evaluate_transition("pending", "ready", ctx).ok is False

    def test_claimable_by_candidates_or_policy(self):
        """TC-TSM-024: 候选池命中或分配策略命中，二者其一即可认领"""
        assert evaluate_transition(
            "ready", "claimed", TransitionContext(actor_in_candidates=True)).ok is True
        assert evaluate_transition(
            "ready", "claimed", TransitionContext(assign_policy_hit=True)).ok is True
        assert evaluate_transition("ready", "claimed", TransitionContext(
            actor_in_candidates=False, assign_policy_hit=False)).ok is False

    def test_claim_timeout_recycle(self):
        """TC-TSM-025: claim 超时才可回收"""
        assert evaluate_transition("claimed", "ready", TransitionContext(
            claim_elapsed_seconds=301, claim_timeout_seconds=300)).ok is True
        assert evaluate_transition("claimed", "ready", TransitionContext(
            claim_elapsed_seconds=300, claim_timeout_seconds=300)).ok is False

    def test_edge_condition_failed_skips(self):
        """TC-TSM-026: edge 条件不满足才可 skipped"""
        assert evaluate_transition("ready", "skipped", TransitionContext(
            edge_condition_satisfied=False)).ok is True
        assert evaluate_transition("ready", "skipped", TransitionContext(
            edge_condition_satisfied=True)).ok is False

    def test_acceptance_gate(self):
        """TC-TSM-027: 验收未通过不能 done"""
        assert evaluate_transition("in_progress", "done", TransitionContext(
            acceptance_passed=True)).ok is True
        r = evaluate_transition("in_progress", "done", TransitionContext(
            acceptance_passed=False))
        assert r.ok is False and "验收" in r.reason

    def test_retry_boundary(self):
        """TC-TSM-028: retry 未超限 → ready；超限 → dead"""
        assert evaluate_transition("failed", "ready", TransitionContext(
            retry_exhausted=False)).ok is True
        assert evaluate_transition("failed", "ready", TransitionContext(
            retry_exhausted=True)).ok is False
        assert evaluate_transition("failed", "dead", TransitionContext(
            retry_exhausted=True)).ok is True
        assert evaluate_transition("failed", "dead", TransitionContext(
            retry_exhausted=False)).ok is False

    def test_reviewer_required_to_enter_approval(self):
        """TC-TSM-029: 未配置审核人不能进 waiting_approval"""
        assert evaluate_transition("in_progress", "waiting_approval",
                                   TransitionContext(reviewer_configured=True)).ok is True
        assert evaluate_transition("in_progress", "waiting_approval",
                                   TransitionContext(reviewer_configured=False)).ok is False

    def test_review_permission_gate(self):
        """TC-TSM-030: 无审核权限不能流转 waiting_approval 出边"""
        for to in ("in_progress", "failed"):
            assert evaluate_transition("waiting_approval", to, TransitionContext(
                actor_has_review_permission=False)).ok is False
            assert evaluate_transition("waiting_approval", to, TransitionContext(
                actor_has_review_permission=True)).ok is True

    def test_four_eyes_maker_checker(self):
        """TC-TSM-031: type=approval 审核通过须四眼（审核人 ≠ 提交人）"""
        base = dict(actor_has_review_permission=True, requires_four_eyes=True,
                    submitter_id="alice")
        assert evaluate_transition("waiting_approval", "done",
                                   TransitionContext(actor="bob", **base)).ok is True
        r = evaluate_transition("waiting_approval", "done",
                                TransitionContext(actor="alice", **base))
        assert r.ok is False and "四眼" in r.reason

    def test_four_eyes_not_required_allows_self(self):
        """TC-TSM-032: 非 approval 任务不强制四眼"""
        assert evaluate_transition("waiting_approval", "done", TransitionContext(
            actor_has_review_permission=True, requires_four_eyes=False,
            actor="alice", submitter_id="alice")).ok is True

    def test_unguarded_transition_needs_no_context(self):
        """TC-TSM-033: 无守卫迁移（如 blocked→in_progress）无需上下文"""
        assert evaluate_transition("blocked", "in_progress").ok is True
        assert evaluate_transition("claimed", "in_progress").ok is True
        assert evaluate_transition("dead", "ready").ok is True
        assert evaluate_transition("pending", "cancelled").ok is True


class TestEvaluateAndRequire:
    """综合判定入口"""

    def test_every_declared_transition_passes_with_ctx(self):
        """TC-TSM-040: 每条声明迁移在满足上下文的场景下均可通过"""
        for rule in TRANSITION_TABLE:
            ctx = ctx_for_guard(rule.guard)
            result = evaluate_transition(rule.from_state, rule.to_state, ctx)
            assert result.ok is True, \
                f"{rule.from_state}→{rule.to_state}（守卫 {rule.guard}）：{result.reason}"

    def test_evaluate_returns_false_for_illegal(self):
        """TC-TSM-041: 非法迁移返回 ok=False（不抛异常）"""
        result = evaluate_transition("done", "ready", TransitionContext())
        assert result.ok is False
        assert "非法迁移" in result.reason

    def test_evaluate_missing_ctx_for_guarded(self):
        """TC-TSM-042: 有守卫但未传上下文 → 拒绝"""
        result = evaluate_transition("pending", "ready")
        assert result.ok is False
        assert "guard context missing" in result.reason

    def test_require_transition_raises_on_guard_fail(self):
        """TC-TSM-043: require_transition 守卫不过时抛错"""
        with pytest.raises(TaskTransitionError) as exc:
            require_transition("pending", "ready",
                               TransitionContext(deps_satisfied=False))
        assert "迁移被拒" in str(exc.value)

    def test_require_transition_returns_rule_on_success(self):
        """TC-TSM-044: require_transition 通过时返回规则"""
        rule = require_transition("pending", "ready",
                                  TransitionContext(deps_satisfied=True))
        assert rule.from_state == "pending"
        assert rule.to_state == "ready"
        assert rule.guard == "deps_satisfied"

    def test_full_happy_path_closed_loop(self):
        """TC-TSM-045: 一条主链 pending→…→done 全链可通过"""
        steps = [
            ("pending", "ready", TransitionContext(deps_satisfied=True)),
            ("ready", "claimed", TransitionContext(actor_in_candidates=True)),
            ("claimed", "in_progress", TransitionContext()),
            ("in_progress", "waiting_approval", TransitionContext(reviewer_configured=True)),
            ("waiting_approval", "done", TransitionContext(
                actor_has_review_permission=True, requires_four_eyes=True,
                actor="bob", submitter_id="alice")),
        ]
        for frm, to, ctx in steps:
            require_transition(frm, to, ctx)
        assert is_terminal("done") is True