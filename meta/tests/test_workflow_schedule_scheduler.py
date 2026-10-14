# -*- coding: utf-8 -*-
"""Workflow 定时调度器回归 —— schedule 触发从「占位」到「真行为」

背景:
  `trigger_kind='schedule'` 早期只是值域占位：`parse_trigger_expr` 对非 event 直接放行，
  声明了 cron 也永不触发（静默失败）。C 组编排完整补齐这块空挂点，分两半:
    - 定义期（`workflow_trigger`）: schedule 必须声明 JSON `{"cron": "..."}`，发布即校验；
    - 运行期（`WorkflowScheduleScheduler`）: 扫生效版 schedule 定义 → 到点 start_run。

本测试锁定:
  1. 作业集从定义表派生：code=workflow_key、schedule=声明 cron；
  2. 只收 schedule 定义（manual / event / api 不进作业集）；
  3. refresh_jobs 增量：schedule 未变的 code 沿用下次触发时间，变更的重算；
  4. tick 先重派生再到期扫描，到点唤起 Run；
  5. run_now 直达 start_run；未知 code 返回 False；
  6. 单条脏定义（历史空 trigger_expr）跳过，不拖垮整轮派生；
  7. 不落任务域调度表（调度状态在内存）。
"""
import json
from datetime import datetime, timedelta

import pytest

from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_engine import run_progress
from meta.core.workflow_schedule_scheduler import (
    SCHEDULE_HANDLER,
    WorkflowScheduleScheduler,
)
from meta.core.workflow_store import publish_workflow


@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（任务四表 + 事件账两表 + 编排定义表）。"""
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "c6.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
    yield source


def _node(node_id, step):
    return {"node_id": node_id, "step_number": step, "title": f"节点{node_id}",
            "executor_type": "human"}


def _nodes():
    return [_node("n1", 1), _node("n2", 2)]


def _cron_expr(cron):
    return json.dumps({"cron": cron}, ensure_ascii=False)


def _publish_schedule(ds, key, cron, **kw):
    return publish_workflow(
        ds, workflow_key=key, name=kw.pop("name", f"流程{key}"), nodes=_nodes(),
        trigger_kind="schedule", trigger_expr=_cron_expr(cron), **kw)


def _run_count(ds, key):
    return ds.execute(
        "SELECT COUNT(*) FROM workflow_runs WHERE workflow_key = ?", (key,)
    ).fetchone()[0]


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# 1. 作业集派生
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test作业集派生:
    def test_schedule_定义派生为作业(self, ds):
        """[C6-1] code=workflow_key、schedule=声明 cron、handler 占位"""
        _publish_schedule(ds, "wf-morning", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        assert sched.codes() == {"wf-morning"}
        job = sched._jobs[0]
        assert job["schedule"] == "0 3 * * *"
        assert job["handler"] == SCHEDULE_HANDLER
        assert job["workflow_key"] == "wf-morning"
        assert sched.is_registered("wf-morning") is True
        assert sched.is_registered("nope") is False

    def test_非schedule定义不入作业集(self, ds):
        """[C6-2] manual / event / api 定义不进 schedule 作业集"""
        publish_workflow(ds, workflow_key="wf-manual", name="手动",
                         nodes=_nodes(), trigger_kind="manual")
        publish_workflow(ds, workflow_key="wf-api", name="接口",
                         nodes=_nodes(), trigger_kind="api")
        publish_workflow(ds, workflow_key="wf-event", name="事件",
                         nodes=_nodes(), trigger_kind="event",
                         trigger_expr=json.dumps({"event": "e"}))
        _publish_schedule(ds, "wf-time", "*/5 * * * *")
        sched = WorkflowScheduleScheduler(ds)
        assert sched.codes() == {"wf-time"}

    def test_取每个key的最新版(self, ds):
        """[C6-3] 生效版语义：改版后按最新 cron 派生"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        _publish_schedule(ds, "wf-a", "0 9 * * *")
        sched = WorkflowScheduleScheduler(ds)
        assert sched._jobs[0]["schedule"] == "0 9 * * *"

    def test_脏定义跳过不拖垮整轮(self, ds):
        """[C6-6] 历史空 trigger_expr 的 schedule 行 → 跳过并告警"""
        _publish_schedule(ds, "wf-ok", "0 3 * * *")
        with ds.transaction():
            ds.execute(
                "INSERT INTO workflows (id, workflow_key, version, name, "
                "trigger_kind, trigger_expr, edges, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("bad-id", "wf-bad", 1, "脏定义", "schedule", "", None,
                 _now(), _now()),
            )
        sched = WorkflowScheduleScheduler(ds)
        assert sched.codes() == {"wf-ok"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. refresh 增量
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRefresh增量:
    def test_未变更沿用下次触发(self, ds):
        """[C6-4] schedule 未变 → _next_run 原值保留（不因重算漂移）"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        before = sched._next_run["wf-a"]
        assert before is not None
        sched.refresh_jobs()
        assert sched._next_run["wf-a"] == before

    def test_变更后重算下次触发(self, ds):
        """[C6-5] 改版 schedule → 重算下次触发"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        before = sched._next_run["wf-a"]
        _publish_schedule(ds, "wf-a", "0 4 * * *")
        sched.refresh_jobs()
        assert sched._jobs[0]["schedule"] == "0 4 * * *"
        assert sched._next_run["wf-a"] != before


# ─────────────────────────────────────────────────────────────────────────────
# 3. 到期触发
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test到期触发:
    def test_tick_到点唤起Run(self, ds):
        """[C6-7] 下次触发已过 → tick 派生 + 到期扫描 → 唤起 Run"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        assert _run_count(ds, "wf-a") == 0
        # 把下次触发拨到过去（模拟已到期）
        sched._next_run["wf-a"] = datetime.now() - timedelta(minutes=1)
        fired = sched.tick()
        assert fired == ["wf-a"]
        assert _run_count(ds, "wf-a") == 1
        # 触发后下次触发被重排到未来
        assert sched._next_run["wf-a"] > datetime.now()

    def test_tick_未到点不触发(self, ds):
        """[C6-8] 未到期 → 不唤起"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        assert sched.tick() == []
        assert _run_count(ds, "wf-a") == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. run_now
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRunNow:
    def test_run_now_唤起Run(self, ds):
        """[C6-9] run_now 直达 workflow_engine.start_run"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        assert sched.run_now("wf-a") is True
        assert _run_count(ds, "wf-a") == 1
        assert sched._last_result["wf-a"]["trigger_kind"] == "schedule"

    def test_run_now_未知code返回False(self, ds):
        """[C6-10] 非当前派生作业 → False（不误派发）"""
        sched = WorkflowScheduleScheduler(ds)
        assert sched.run_now("wf-unknown") is False

    def test_唤起Run带节点任务(self, ds):
        """[C6-11] 唤起后 Run 内含定义克隆出的任务（进度可派生）"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        sched.run_now("wf-a")
        run_id = sched._last_result["wf-a"]["run_id"]
        progress = run_progress(ds, run_id)
        assert progress["total"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 5. 与任务域解耦
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test不落任务域调度表:
    def test_调度状态只在内存(self, ds):
        """[C6-12] 作业集来自定义表派生，不写 scheduled_tasks"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        # 调度状态全部在内存属性上
        assert sched._jobs and sched._next_run["wf-a"] is not None
        # 作业 code 直接等于定义 key（无中间映射表）
        assert {j["code"] for j in sched._jobs} == {"wf-a"}
