import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks / task_events / task_async_waits）暂无 Factory；
# 按仓库既有惯例（13+ 测试文件同款）走 raw SQL escape hatch，避免用例被 conftest 拦跳。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - BOActionExecutor 三态（B2）
测试 meta.core.bo_action_executor 模块（同步 / 异步补全 / needs_review）

覆盖目标（对齐 §12.1 B2 / §9.1 / §9.2）：
  1. 同步：claimed→in_progress→done（守卫 acceptance_passed）+ outputs 回写
  2. 异步补全：开 A7 等待单、Task 保持 in_progress、返回 async_token
  3. needs_review：in_progress→waiting_approval（守卫 reviewer_configured）
  4. 失败：success=False / handler 抛异常 / 前置条件未满足 → failed + fail_reason
  5. 幂等：A6 键 {run}:{task}:{attempt} 重放不重复执行、返回首次结果
  6. 入口前置：任务不存在 / executor_type 不符 / 状态不可执行
  7. 守卫 fail-closed：acceptance 未通过 → TaskTransitionError + 事务回滚
"""

import json
from datetime import datetime

from meta.core.bo_action_executor import (
    BO_ACTION_EXECUTOR_TYPES,
    BOActionExecutionError,
    BOActionExecutor,
    OUTCOME_ASYNC,
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_NEEDS_REVIEW,
    classify_result,
)
from meta.core.task_state_machine import TaskTransitionError


# ─────────────────────────────────────────────────────────────────────────────
# 夹具
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（A1/A3/A6/A7 四段底座），预置 legacy 表验证不破坏。"""
    from meta.core.datasource import get_data_source
    from meta.core.task_async import ensure_async_tables
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "b2.db"))
    with source.transaction():
        source.execute("CREATE TABLE IF NOT EXISTS b2_legacy (id INTEGER PRIMARY KEY)")
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
        ensure_async_tables(source)
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


def _task(ds, *, task_id="T-1", status="claimed", executor_type="system",
          action_id="demo.sync", inputs=None, attempt=1, run_id="R-1", **cfg):
    executor_config = {"action_id": action_id}
    executor_config.update(cfg)
    cols = ["id", "title", "type", "status", "executor_type", "executor_config",
            "inputs", "attempt", "workflow_run_id", "priority", "created_at", "updated_at"]
    vals = [task_id, "测试任务", "automation", status, executor_type,
            json.dumps(executor_config), json.dumps(inputs or {}),
            attempt, run_id, "P2", _now(), _now()]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _status(ds, task_id):
    return ds.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]


def _column(ds, task_id, col):
    return ds.execute(f"SELECT {col} FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]


def _count(ds, table, where="1=1", params=()):
    return ds.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchall()[0][0]


def _register(registry, action_id, handler, **kw):
    kw.setdefault("object_type", "*")
    kw.setdefault("category", "business")
    kw.setdefault("input_schema", {"type": "object", "properties": {}})
    registry.register(action_id, handler, description="B2 测试 action", **kw)


# ─────────────────────────────────────────────────────────────────────────────
# 结果归一化
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyResult:
    """TC-B2-001~004 三态归一"""

    def test_TC_B2_001_信封默认完成(self):
        assert classify_result({"success": True, "data": 1}) == OUTCOME_COMPLETED

    def test_TC_B2_002_needs_review(self):
        assert classify_result({"status": "needs_review", "payload": {}}) == OUTCOME_NEEDS_REVIEW

    def test_TC_B2_003_异步三种信号(self):
        assert classify_result({"status": "async"}) == OUTCOME_ASYNC
        assert classify_result({"async": True}) == OUTCOME_ASYNC
        assert classify_result({"async_token": "tk"}) == OUTCOME_ASYNC

    def test_TC_B2_004_success_false为失败(self):
        assert classify_result({"success": False, "message": "boom"}) == OUTCOME_FAILED


# ─────────────────────────────────────────────────────────────────────────────
# 三态归位
# ─────────────────────────────────────────────────────────────────────────────

class TestThreeStates:
    """TC-B2-010~024 同步 / 异步 / needs_review / 失败"""

    def test_TC_B2_010_同步完成回写outputs与事件账(self, ds, registry):
        _register(registry, "demo.sync", lambda p, c: {"success": True, "data": {"n": 1}})
        tid = _task(ds, action_id="demo.sync")

        outcome = BOActionExecutor(registry).start(ds, tid, run_as="svc")

        assert outcome["status"] == OUTCOME_COMPLETED
        assert outcome["task_status"] == "done"
        assert _status(ds, tid) == "done"
        assert json.loads(_column(ds, tid, "outputs")) == {"n": 1}
        # A3：claimed→in_progress + in_progress→done，各一条事件 + 一条工作日志
        assert _count(ds, "task_events", "task_id = ?", (tid,)) == 2
        assert _count(ds, "task_worklogs", "task_id = ?", (tid,)) == 2
        # A6：幂等账落一条
        assert _count(ds, "task_idempotency") == 1

    def test_TC_B2_011_异步补全保持in_progress(self, ds, registry):
        _register(registry, "demo.async", lambda p, c: {"status": "async"})
        tid = _task(ds, action_id="demo.async")

        outcome = BOActionExecutor(registry).start(ds, tid)

        assert outcome["status"] == OUTCOME_ASYNC
        assert outcome["task_status"] == "in_progress"
        assert outcome["async_token"]
        assert _status(ds, tid) == "in_progress"
        # A7：开单 1 张，且未完成
        assert _count(ds, "task_async_waits") == 1
        assert _count(ds, "task_async_waits", "wait_status = 'waiting'") == 1

    def test_TC_B2_012_needs_review转waiting_approval(self, ds, registry):
        _register(registry, "demo.review",
                  lambda p, c: {"status": "needs_review", "payload": {"diff": 1}})
        tid = _task(ds, action_id="demo.review")

        outcome = BOActionExecutor(registry).start(ds, tid)

        assert outcome["status"] == OUTCOME_NEEDS_REVIEW
        assert outcome["task_status"] == "waiting_approval"
        assert _status(ds, tid) == "waiting_approval"
        assert json.loads(_column(ds, tid, "outputs")) == {"diff": 1}

    def test_TC_B2_013_success_false归位failed(self, ds, registry):
        _register(registry, "demo.bad", lambda p, c: {"success": False, "message": "业务拒绝"})
        tid = _task(ds, action_id="demo.bad")

        outcome = BOActionExecutor(registry).start(ds, tid)

        assert outcome["status"] == OUTCOME_FAILED
        assert _status(ds, tid) == "failed"
        assert _column(ds, tid, "fail_reason") == "业务拒绝"

    def test_TC_B2_014_handler抛异常归位failed(self, ds, registry):
        def _boom(p, c):
            raise RuntimeError("handler 崩溃")

        _register(registry, "demo.raise", _boom)
        tid = _task(ds, action_id="demo.raise")

        outcome = BOActionExecutor(registry).start(ds, tid)

        assert outcome["status"] == OUTCOME_FAILED
        assert _status(ds, tid) == "failed"
        assert "handler 崩溃" in _column(ds, tid, "fail_reason")

    def test_TC_B2_015_前置条件未满足归位failed(self, ds, registry):
        """B1 前置条件在 call() 内拦截 → executor 视为失败"""
        _register(registry, "demo.pre", lambda p, c: {"success": True},
                  preconditions=[{"kind": "input_present", "field": "object_type"}])
        tid = _task(ds, action_id="demo.pre", inputs={})

        outcome = BOActionExecutor(registry).start(ds, tid)

        assert outcome["status"] == OUTCOME_FAILED
        assert "前置条件" in outcome["message"]

    def test_TC_B2_016_未知action归位failed(self, ds, registry):
        tid = _task(ds, action_id="demo.missing")

        outcome = BOActionExecutor(registry).start(ds, tid)

        assert outcome["status"] == OUTCOME_FAILED
        assert "Unknown action" in _column(ds, tid, "fail_reason")

    def test_TC_B2_017_needs_review未配置审核人归位failed(self, ds, registry):
        _register(registry, "demo.review2",
                  lambda p, c: {"status": "needs_review", "payload": {}})
        tid = _task(ds, action_id="demo.review2")

        outcome = BOActionExecutor(registry).start(ds, tid, reviewer_configured=False)

        assert outcome["status"] == OUTCOME_FAILED
        assert _status(ds, tid) == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# 幂等重放
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotency:
    """TC-B2-030~032 A6 幂等键包裹整尝试"""

    def test_TC_B2_030_重放不重复执行(self, ds, registry):
        calls = []
        _register(registry, "demo.count",
                  lambda p, c: calls.append(1) or {"success": True, "data": len(calls)})
        tid = _task(ds, action_id="demo.count")

        first = BOActionExecutor(registry).start(ds, tid)
        second = BOActionExecutor(registry).start(ds, tid)

        assert first["replayed"] is False
        assert second["replayed"] is True
        assert len(calls) == 1
        assert second["outputs"] == first["outputs"] == 1

    def test_TC_B2_031_幂等键口径(self, ds, registry):
        _register(registry, "demo.sync", lambda p, c: {"success": True})
        tid = _task(ds, action_id="demo.sync", run_id="R-9", attempt=3)

        outcome = BOActionExecutor(registry).start(ds, tid)

        assert outcome["idem_key"] == "R-9:%s:3" % tid

    def test_TC_B2_032_异步重放不再开单(self, ds, registry):
        _register(registry, "demo.async", lambda p, c: {"status": "async"})
        tid = _task(ds, action_id="demo.async")

        BOActionExecutor(registry).start(ds, tid)
        second = BOActionExecutor(registry).start(ds, tid)

        assert second["replayed"] is True
        assert _count(ds, "task_async_waits") == 1


# ─────────────────────────────────────────────────────────────────────────────
# 入口前置与守卫
# ─────────────────────────────────────────────────────────────────────────────

class TestEntryGuards:
    """TC-B2-040~044 入口前置 + 守卫 fail-closed"""

    def test_TC_B2_040_任务不存在(self, ds, registry):
        with pytest.raises(BOActionExecutionError):
            BOActionExecutor(registry).start(ds, "T-nope")

    def test_TC_B2_041_executor类型不符(self, ds, registry):
        tid = _task(ds, executor_type="human")
        with pytest.raises(BOActionExecutionError):
            BOActionExecutor(registry).start(ds, tid)

    def test_TC_B2_042_缺少action_id(self, ds, registry):
        tid = _task(ds, action_id="")
        with pytest.raises(BOActionExecutionError):
            BOActionExecutor(registry).start(ds, tid)

    def test_TC_B2_043_状态不可执行(self, ds, registry):
        tid = _task(ds, status="done")
        with pytest.raises(BOActionExecutionError):
            BOActionExecutor(registry).start(ds, tid)

    def test_TC_B2_044_验收守卫fail_closed并回滚(self, ds, registry):
        _register(registry, "demo.sync", lambda p, c: {"success": True})
        tid = _task(ds, action_id="demo.sync")

        with pytest.raises(TaskTransitionError):
            BOActionExecutor(registry).start(ds, tid, acceptance_passed=False)

        # 事务回滚：状态未推进，事件账与幂等账不落脏数据
        assert _status(ds, tid) == "claimed"
        assert _count(ds, "task_events", "task_id = ?", (tid,)) == 0
        assert _count(ds, "task_idempotency") == 0

    def test_TC_B2_045_执行域常量(self):
        assert BO_ACTION_EXECUTOR_TYPES == ("system", "cron")