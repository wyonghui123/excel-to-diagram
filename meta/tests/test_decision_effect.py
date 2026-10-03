import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks / task_events / task_worklogs / task_idempotency）暂无 Factory；
# 按仓库既有惯例走 raw SQL escape hatch，避免用例被 conftest 整文件拦跳。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - 决策-生效分离协议（B3）
测试 meta.core.decision_effect 模块（§9.7 七条规范固化）

覆盖目标（对齐 §12.1 B3 / §9.7）：
  1. 先生效后完成：BO 返回生效回执后任务才 done；无回执 / 失败 / 异常 → 不迁移
  2. 幂等生效：effect_key = {task_id}:{attempt} 注入 BO 上下文 + A6 包裹整次决策
  3. 守卫双向独立：任务侧守卫先于 BO 预校验（无副作用），BO 侧独立
  4. 拒绝同样要生效：reject 同协议、同口径；decision_actions 必须成对配置
  5. 对账兜底：done 无回执 / 回执与现状不一致 / 等待单据无活跃任务
"""

import json
from datetime import datetime, timedelta

from meta.core.decision_effect import (
    DECISIONS,
    DecisionEffectError,
    DecisionEffectProtocol,
    EffectNotAppliedError,
    build_effect_key,
    extract_effect_receipt,
    normalize_decision,
    reconcile_effects,
    resolve_decision_action,
)


# ─────────────────────────────────────────────────────────────────────────────
# 夹具
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（A1/A3/A6 三段底座）。"""
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "b3.db"))
    with source.transaction():
        source.execute("CREATE TABLE IF NOT EXISTS b3_legacy (id INTEGER PRIMARY KEY)")
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
    yield source


@pytest.fixture()
def registry():
    """快照-恢复全局注册表单例，避免污染其他测试。"""
    from meta.core.bo_action_registry import bo_action_registry

    saved = dict(bo_action_registry._actions)
    bo_action_registry.clear()
    yield bo_action_registry
    bo_action_registry._actions.clear()
    bo_action_registry._actions.update(saved)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _approval_task(ds, *, task_id="T-A1", status="waiting_approval", attempt=1,
                   doc_ref="DOC-1", inputs=None, created_by="u-sub",
                   approve_action="demo.approve", reject_action="demo.reject",
                   type_="approval", **cfg):
    """插入一个审批任务（waiting_approval 决策门）。"""
    config = {
        "decision_actions": {"approve": approve_action, "reject": reject_action},
    }
    config.update(cfg)
    cols = ["id", "title", "type", "status", "executor_type", "executor_config",
            "inputs", "attempt", "workflow_run_id", "doc_ref", "created_by",
            "priority", "created_at", "updated_at"]
    vals = [task_id, "审批任务", type_, status, "system", json.dumps(config),
            json.dumps(inputs or {"doc_ref": doc_ref}), attempt, "R-1", doc_ref,
            created_by, "P2", _now(), _now()]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _register(registry, action_id, handler, **kw):
    kw.setdefault("object_type", "*")
    kw.setdefault("category", "business")
    kw.setdefault("input_schema", {"type": "object", "properties": {}})
    registry.register(action_id, handler, description="B3 测试 action", **kw)


def _ok_handler(new_status="approved", calls=None):
    def _h(payload, context):
        if calls is not None:
            calls.append(context)
        return {"success": True, "data": {"new_status": new_status, "doc_ref": "DOC-1"}}

    return _h


def _status(ds, task_id):
    return ds.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]


def _column(ds, task_id, col):
    return ds.execute(f"SELECT {col} FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]


def _count(ds, table, where="1=1", params=()):
    return ds.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchall()[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 契约口径（§9.7 规范 2 / 7）
# ─────────────────────────────────────────────────────────────────────────────

class TestContract:
    """TC-B3-001~005 键口径 / 决策校验 / 动作映射 / 回执提取"""

    def test_TC_B3_001_生效键口径(self):
        assert build_effect_key("T-1", 2) == "T-1:2"
        assert build_effect_key("T-1") == "T-1:1"

    def test_TC_B3_002_决策值校验(self):
        assert normalize_decision("APPROVE") == "approve"
        assert normalize_decision("reject") == "reject"
        assert DECISIONS == ("approve", "reject")
        with pytest.raises(DecisionEffectError):
            normalize_decision("maybe")

    def test_TC_B3_003_决策动作必须成对(self):
        cfg = {"decision_actions": {"approve": "demo.approve"}}
        assert resolve_decision_action({"decision_actions": {"approve": "a", "reject": "r"}}, "reject") == "r"
        with pytest.raises(DecisionEffectError):
            resolve_decision_action(cfg, "reject")  # 漏配 reject → 机器拦截

    def test_TC_B3_004_回执提取(self):
        receipt = extract_effect_receipt({"success": True, "data": {"new_status": "approved"}})
        assert receipt == {"new_status": "approved"}
        # 无 new_status / data 非对象 / success=False → 视为未生效
        assert extract_effect_receipt({"success": True, "data": {}}) is None
        assert extract_effect_receipt({"success": True, "data": None}) is None
        assert extract_effect_receipt({"success": False, "data": {"new_status": "x"}}) is None

    def test_TC_B3_005_自定义回执键(self):
        assert extract_effect_receipt({"success": True, "data": {"status": "approved"}},
                                      receipt_key="status") == {"status": "approved"}
        assert extract_effect_receipt({"success": True, "data": {"status": "approved"}}) is None


# ─────────────────────────────────────────────────────────────────────────────
# 通过：先生效后完成
# ─────────────────────────────────────────────────────────────────────────────

class TestApprove:
    """TC-B3-010~017 approve 路径"""

    def test_TC_B3_010_先生效后完成(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        _register(registry, "demo.reject", _ok_handler("rejected"))
        tid = _approval_task(ds)

        outcome = DecisionEffectProtocol(registry).decide(
            ds, tid, decision="approve", comment="同意", actor="u-1001",
            reviewer_permission=True, submitter_id="u-sub",
        )

        assert outcome["status"] == "completed"
        assert outcome["task_status"] == "done"
        assert _status(ds, tid) == "done"
        outputs = json.loads(_column(ds, tid, "outputs"))
        assert outputs["decision"] == "approve"
        assert outputs["comment"] == "同意"
        assert outputs["receipt"]["new_status"] == "approved"
        # BO 在迁移之前被调用，且收到决策 / 生效键
        assert len(calls) == 1
        assert calls[0]["decision"] == "approve"
        assert calls[0]["effect_key"] == build_effect_key(tid, 1)
        # A3：waiting_approval→done 一条事件 + 一条工作日志（含审核意见）
        assert _count(ds, "task_events", "task_id = ?", (tid,)) == 1
        assert _count(ds, "task_worklogs", "task_id = ?", (tid,)) == 1
        detail = json.loads(ds.execute(
            "SELECT detail FROM task_worklogs WHERE task_id = ?", (tid,)).fetchall()[0][0])
        assert detail["comment"] == "同意"

    def test_TC_B3_011_无回执不迁移(self, ds, registry):
        _register(registry, "demo.approve", lambda p, c: {"success": True, "data": {}})
        _register(registry, "demo.reject", _ok_handler("rejected"))
        tid = _approval_task(ds)

        with pytest.raises(EffectNotAppliedError):
            DecisionEffectProtocol(registry).decide(
                ds, tid, decision="approve", actor="u-1",
                reviewer_permission=True, submitter_id="u-sub",
            )

        # 绝不出现「任务已完成但单据未生效」；幂等账不被污染（可重试）
        assert _status(ds, tid) == "waiting_approval"
        assert _count(ds, "task_events", "task_id = ?", (tid,)) == 0
        assert _count(ds, "task_idempotency") == 0

    def test_TC_B3_012_生效失败不迁移(self, ds, registry):
        _register(registry, "demo.approve", lambda p, c: {"success": False, "message": "单据状态不允许"})
        _register(registry, "demo.reject", _ok_handler("rejected"))
        tid = _approval_task(ds)

        with pytest.raises(EffectNotAppliedError):
            DecisionEffectProtocol(registry).decide(
                ds, tid, decision="approve", actor="u-1", reviewer_permission=True)

        assert _status(ds, tid) == "waiting_approval"

    def test_TC_B3_013_生效异常不迁移(self, ds, registry):
        def _boom(p, c):
            raise RuntimeError("BO 崩溃")

        _register(registry, "demo.approve", _boom)
        tid = _approval_task(ds)

        with pytest.raises(EffectNotAppliedError):
            DecisionEffectProtocol(registry).decide(
                ds, tid, decision="approve", actor="u-1", reviewer_permission=True)

        assert _status(ds, tid) == "waiting_approval"
        assert _count(ds, "task_events", "task_id = ?", (tid,)) == 0

    def test_TC_B3_014_生效键随尝试递增(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        tid = _approval_task(ds, attempt=3)

        outcome = DecisionEffectProtocol(registry).decide(
            ds, tid, decision="approve", actor="u-1", reviewer_permission=True)

        assert outcome["effect_key"] == f"{tid}:3"
        assert calls[0]["effect_key"] == f"{tid}:3"
        assert calls[0]["attempt"] == 3

    def test_TC_B3_015_守卫不足时不调BO无副作用(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        tid = _approval_task(ds)

        with pytest.raises(DecisionEffectError):
            DecisionEffectProtocol(registry).decide(
                ds, tid, decision="approve", actor="u-1", reviewer_permission=None)

        assert calls == []                      # 任务侧守卫先于 BO
        assert _status(ds, tid) == "waiting_approval"
        assert _count(ds, "task_idempotency") == 0

    def test_TC_B3_016_四眼原则拦截(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        tid = _approval_task(ds, created_by="u-1")

        with pytest.raises(DecisionEffectError):
            DecisionEffectProtocol(registry).decide(
                ds, tid, decision="approve", actor="u-1", reviewer_permission=True)

        assert calls == []
        assert _status(ds, tid) == "waiting_approval"

    def test_TC_B3_017_四眼原则通过(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        tid = _approval_task(ds, created_by="u-sub")

        outcome = DecisionEffectProtocol(registry).decide(
            ds, tid, decision="approve", actor="u-1001", reviewer_permission=True)

        assert outcome["task_status"] == "done"


# ─────────────────────────────────────────────────────────────────────────────
# 拒绝同样要生效（§9.7 规范 7）
# ─────────────────────────────────────────────────────────────────────────────

class TestReject:
    """TC-B3-020~022 reject 路径"""

    def test_TC_B3_020_拒绝同样落到单据(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected", calls=calls))
        tid = _approval_task(ds)

        outcome = DecisionEffectProtocol(registry).decide(
            ds, tid, decision="reject", comment="金额不符", actor="u-1",
            reviewer_permission=True)

        assert calls[0]["decision"] == "reject"
        assert outcome["receipt"]["new_status"] == "rejected"
        assert _status(ds, tid) == "failed"
        assert "rejected" in _column(ds, tid, "fail_reason")

    def test_TC_B3_021_驳回返修不终态(self, ds, registry):
        _register(registry, "demo.reject", _ok_handler("rejected"))
        tid = _approval_task(ds)

        outcome = DecisionEffectProtocol(registry).decide(
            ds, tid, decision="reject", actor="u-1", reviewer_permission=True,
            allow_rework=True)

        assert outcome["task_status"] == "in_progress"
        assert _status(ds, tid) == "in_progress"
        assert _column(ds, tid, "finished_at") is None

    def test_TC_B3_022_漏配拒绝动作被拦(self, ds, registry):
        tid = _approval_task(ds, reject_action=None)

        with pytest.raises(DecisionEffectError):
            DecisionEffectProtocol(registry).decide(
                ds, tid, decision="reject", actor="u-1", reviewer_permission=True)


# ─────────────────────────────────────────────────────────────────────────────
# 幂等重放（§9.7 规范 2）
# ─────────────────────────────────────────────────────────────────────────────

class TestReplay:
    """TC-B3-030~031 重放不重复生效"""

    def test_TC_B3_030_重放不重复调用BO(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        tid = _approval_task(ds)

        first = DecisionEffectProtocol(registry).decide(
            ds, tid, decision="approve", actor="u-1", reviewer_permission=True)
        second = DecisionEffectProtocol(registry).decide(
            ds, tid, decision="approve", actor="u-1", reviewer_permission=True)

        assert first["replayed"] is False
        assert second["replayed"] is True
        assert len(calls) == 1

    def test_TC_B3_031_重放不重复迁移(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        tid = _approval_task(ds)

        DecisionEffectProtocol(registry).decide(
            ds, tid, decision="approve", actor="u-1", reviewer_permission=True)
        DecisionEffectProtocol(registry).decide(
            ds, tid, decision="approve", actor="u-1", reviewer_permission=True)

        assert _status(ds, tid) == "done"
        assert _count(ds, "task_events", "task_id = ?", (tid,)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 对账兜底（§9.7 规范 5）
# ─────────────────────────────────────────────────────────────────────────────

class TestReconcile:
    """TC-B3-040~044 双向漂移扫描"""

    def test_TC_B3_040_done无回执(self, ds, registry):
        tid = _approval_task(ds, status="done")
        ds.execute("UPDATE tasks SET outputs = ? WHERE id = ?", (json.dumps({"decision": "approve"}), tid))

        findings = reconcile_effects(ds)

        assert [f["kind"] for f in findings] == ["done_without_effect"]
        assert findings[0]["task_id"] == tid

    def test_TC_B3_041_回执与现状不一致(self, ds, registry):
        tid = _approval_task(ds, status="done")
        ds.execute("UPDATE tasks SET outputs = ? WHERE id = ?",
                   (json.dumps({"receipt": {"new_status": "approved"}}), tid))

        findings = reconcile_effects(ds, current_statuses={"DOC-1": "rejected"})

        assert [f["kind"] for f in findings] == ["effect_mismatch"]
        assert findings[0]["doc_ref"] == "DOC-1"

    def test_TC_B3_042_等待单据无活跃任务(self, ds, registry):
        since = (datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds")

        findings = reconcile_effects(
            ds, pending_docs=[{"doc_ref": "DOC-9", "since": since}], stale_hours=24)

        assert [f["kind"] for f in findings] == ["pending_without_task"]
        assert findings[0]["doc_ref"] == "DOC-9"

    def test_TC_B3_043_有活跃任务不告警(self, ds, registry):
        _approval_task(ds, task_id="T-ACT", doc_ref="DOC-9", status="waiting_approval")
        since = (datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds")

        findings = reconcile_effects(
            ds, pending_docs=[{"doc_ref": "DOC-9", "since": since}], stale_hours=24)

        assert findings == []

    def test_TC_B3_044_未超时不告警(self, ds, registry):
        since = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")

        findings = reconcile_effects(
            ds, pending_docs=[{"doc_ref": "DOC-9", "since": since}], stale_hours=24)

        assert findings == []

    def test_TC_B3_045_活跃审批任务缺配置(self, ds, registry):
        # 直接插入一个未配置 decision_actions 的活跃审批任务
        tid = _approval_task(ds, task_id="T-NOCFG", status="waiting_approval")
        ds.execute("UPDATE tasks SET executor_config = ? WHERE id = ?", ("{}", tid))

        findings = reconcile_effects(ds)

        assert [f["kind"] for f in findings] == ["approval_without_decision_config"]
        assert findings[0]["task_id"] == tid
        assert "approve" in findings[0]["detail"] and "reject" in findings[0]["detail"]

    def test_TC_B3_046_缺一半配置同样告警(self, ds, registry):
        tid = _approval_task(ds, task_id="T-HALF", status="waiting_approval")
        ds.execute(
            "UPDATE tasks SET executor_config = ? WHERE id = ?",
            (json.dumps({"decision_actions": {"approve": "demo.approve"}}), tid),
        )

        findings = reconcile_effects(ds)

        assert [f["kind"] for f in findings] == ["approval_without_decision_config"]
        assert "reject" in findings[0]["detail"]

    def test_TC_B3_047_终态任务不查配置(self, ds, registry):
        # done（inactive）缺配置不报配置类告警（此处无回执 → 只报 done_without_effect）
        tid = _approval_task(ds, task_id="T-DONE", status="done")
        ds.execute("UPDATE tasks SET executor_config = ?, outputs = ? WHERE id = ?",
                   ("{}", json.dumps({}), tid))

        findings = reconcile_effects(ds)

        assert [f["kind"] for f in findings] == ["done_without_effect"]


# ─────────────────────────────────────────────────────────────────────────────
# 入口前置
# ─────────────────────────────────────────────────────────────────────────────

class TestEntryGuards:
    """TC-B3-050~052 入口前置 fail-closed"""

    def test_TC_B3_050_任务不存在(self, ds, registry):
        with pytest.raises(DecisionEffectError):
            DecisionEffectProtocol(registry).decide(ds, "T-nope", decision="approve")

    def test_TC_B3_051_类型不适用(self, ds, registry):
        tid = _approval_task(ds, type_="automation")
        with pytest.raises(DecisionEffectError):
            DecisionEffectProtocol(registry).decide(ds, tid, decision="approve")

    def test_TC_B3_052_状态不可决策(self, ds, registry):
        tid = _approval_task(ds, status="done")
        with pytest.raises(DecisionEffectError):
            DecisionEffectProtocol(registry).decide(
                ds, tid, decision="approve", actor="u-1", reviewer_permission=True)