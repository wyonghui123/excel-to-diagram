import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks 等）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - Executor 适配层（A5）
测试 meta.core.task_executor_adapter.start_task（§7.1 原则1 / §7.5 适配矩阵 / §12.1 A5）

覆盖目标：
  1. system / cron → 委托 BOActionExecutor（B2 三态）
  2. human → awaiting_human，零写库（status 不变）
  3. webhook → awaiting_async，零写库
  4. agent → fail-closed（未实现，§9.3）
  5. 未知类型 / 任务不存在 → fail-closed
  6. 适配矩阵覆盖 §7.5 全枚举；停等信号判定
"""

import json
from datetime import datetime

from meta.core.task_executor_adapter import (
    ADAPTER_CARRIERS,
    EXECUTOR_TYPES,
    OUTCOME_AWAITING_HUMAN,
    PAUSE_OUTCOMES,
    ExecutorAdapterError,
    is_pause,
    start_task,
)
from meta.core.bo_action_executor import OUTCOME_ASYNC, OUTCOME_COMPLETED


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_async import ensure_async_tables
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "a5.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
        ensure_async_tables(source)
    yield source


@pytest.fixture()
def registry():
    from meta.core.bo_action_registry import bo_action_registry

    saved = dict(bo_action_registry._actions)
    bo_action_registry.clear()
    yield bo_action_registry
    bo_action_registry._actions.clear()
    bo_action_registry._actions.update(saved)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _task(ds, *, task_id="T-1", executor_type="system", status="claimed",
          action_id="demo.sync"):
    config = {"action_id": action_id}
    cols = ["id", "title", "type", "status", "executor_type", "executor_config",
            "inputs", "attempt", "workflow_run_id", "priority", "created_at", "updated_at"]
    vals = [task_id, "测试任务", "automation", status, executor_type,
            json.dumps(config), json.dumps({}), 1, "R-1", "P2", _now(), _now()]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _status(ds, task_id):
    return ds.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]


def _register(registry, action_id, handler):
    registry.register(action_id, handler, description="A5 测试 action",
                      object_type="*", category="business",
                      input_schema={"type": "object", "properties": {}})


# ─────────────────────────────────────────────────────────────────────────────
# 适配矩阵
# ─────────────────────────────────────────────────────────────────────────────

class TestMatrix:
    """TC-A5-001~003 声明式矩阵完整性"""

    def test_TC_A5_001_矩阵覆盖全枚举(self):
        assert EXECUTOR_TYPES == ("human", "agent", "cron", "system", "webhook")
        assert set(ADAPTER_CARRIERS) == set(EXECUTOR_TYPES)

    def test_TC_A5_002_仅agent未实现(self):
        assert ADAPTER_CARRIERS["agent"] is None
        for t in ("human", "system", "cron", "webhook"):
            assert ADAPTER_CARRIERS[t], t

    def test_TC_A5_003_停等信号判定(self):
        assert OUTCOME_AWAITING_HUMAN in PAUSE_OUTCOMES
        assert OUTCOME_ASYNC in PAUSE_OUTCOMES
        assert is_pause(OUTCOME_AWAITING_HUMAN) is True
        assert is_pause(OUTCOME_COMPLETED) is False


# ─────────────────────────────────────────────────────────────────────────────
# 派发
# ─────────────────────────────────────────────────────────────────────────────

class TestDispatch:
    """TC-A5-010~017 各 executor 派发"""

    def test_TC_A5_010_system委托BOActionExecutor(self, ds, registry):
        _register(registry, "demo.sync", lambda p, c: {"success": True, "data": {"n": 1}})
        tid = _task(ds, executor_type="system", action_id="demo.sync")

        outcome = start_task(ds, tid, registry=registry)

        assert outcome["status"] == OUTCOME_COMPLETED
        assert outcome["task_status"] == "done"
        assert outcome["executor_type"] == "system"
        assert _status(ds, tid) == "done"

    def test_TC_A5_011_cron同system通道(self, ds, registry):
        _register(registry, "demo.sync", lambda p, c: {"success": True})
        tid = _task(ds, executor_type="cron", action_id="demo.sync")

        outcome = start_task(ds, tid, registry=registry)

        assert outcome["status"] == OUTCOME_COMPLETED
        assert outcome["executor_type"] == "cron"

    def test_TC_A5_012_human停等且零写库(self, ds, registry):
        tid = _task(ds, executor_type="human", status="ready", action_id="")

        outcome = start_task(ds, tid, registry=registry)

        assert outcome["status"] == OUTCOME_AWAITING_HUMAN
        assert outcome["task_status"] == "ready"       # 未发明状态
        assert _status(ds, tid) == "ready"             # 零写库

    def test_TC_A5_013_webhook停等且零写库(self, ds, registry):
        tid = _task(ds, executor_type="webhook", status="ready", action_id="")

        outcome = start_task(ds, tid, registry=registry)

        assert outcome["status"] == OUTCOME_ASYNC
        assert outcome["task_status"] == "ready"
        assert _status(ds, tid) == "ready"

    def test_TC_A5_014_agent未实现fail_closed(self, ds, registry):
        tid = _task(ds, executor_type="agent", status="ready", action_id="")

        with pytest.raises(ExecutorAdapterError) as ei:
            start_task(ds, tid, registry=registry)

        assert "agent" in str(ei.value)
        assert _status(ds, tid) == "ready"

    def test_TC_A5_015_未知类型fail_closed(self, ds, registry):
        tid = _task(ds, executor_type="robot", status="ready", action_id="")

        with pytest.raises(ExecutorAdapterError):
            start_task(ds, tid, registry=registry)

    def test_TC_A5_016_任务不存在fail_closed(self, ds, registry):
        with pytest.raises(ExecutorAdapterError):
            start_task(ds, "T-nope", registry=registry)

    def test_TC_A5_017_system异常经B2归位failed(self, ds, registry):
        _register(registry, "demo.bad", lambda p, c: {"success": False, "message": "业务拒绝"})
        tid = _task(ds, executor_type="system", action_id="demo.bad")

        outcome = start_task(ds, tid, registry=registry)

        assert outcome["status"] == "failed"
        assert _status(ds, tid) == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# REST 服务函数（不经 Flask 全栈）
# ─────────────────────────────────────────────────────────────────────────────

def test_TC_A5_020_服务函数返回适配结果(ds, registry, monkeypatch):
    import meta.api.task_inbox_api as api

    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _register(registry, "demo.sync", lambda p, c: {"success": True})
    tid = _task(ds, executor_type="system", action_id="demo.sync")

    payload, code = api.start_task_service(
        tid, user={"user_id": "u-admin", "permissions": ["*"]}, registry=registry)

    assert code == 200
    assert payload["success"] is True
    assert payload["data"]["status"] == OUTCOME_COMPLETED


def test_TC_A5_021_服务函数非管理员被拒(ds, registry, monkeypatch):
    import meta.api.task_inbox_api as api

    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    tid = _task(ds, executor_type="human", status="ready", action_id="")

    payload, code = api.start_task_service(
        tid, user={"user_id": "u-plain", "permissions": []}, registry=registry)

    assert code == 403
    assert _status(ds, tid) == "ready"


def test_TC_A5_022_服务函数未实现类型映射409(ds, registry, monkeypatch):
    import meta.api.task_inbox_api as api

    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    tid = _task(ds, executor_type="agent", status="ready", action_id="")

    payload, code = api.start_task_service(
        tid, user={"user_id": "u-admin", "permissions": ["*"]}, registry=registry)

    assert code == 409
    assert payload["success"] is False
    assert "agent" in payload["message"]