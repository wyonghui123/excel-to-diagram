# -*- coding: utf-8 -*-
"""编排只读聚合端点回归 —— 任务管理页「调度」tab 的数据源

本测试锁定:
  1. `/api/v2/workflows/schedules` 把「编排定义 + 触发规则 + 运行实例」三段拼齐；
  2. node_count / cron / cron_label 如实反映定义；
  3. runs 反映该 workflow 最近的 Run（派生状态 + 进度）；
  4. scheduler_registered 反映调度器是否已派生该作业；
  5. `/api/v2/workflows/scheduler/status` 三态：未接线 503 / 暂停 200+paused / 正常 200；
  6. 未接线时 schedules 也 503（不半答）。
"""
import json

import pytest
from flask import Flask

from meta.api.workflow_api import set_workflow_scheduler, workflow_bp
from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_schedule_scheduler import WorkflowScheduleScheduler
from meta.core.workflow_store import publish_workflow


@pytest.fixture(autouse=True)
def _reset_workflow_scheduler():
    set_workflow_scheduler(None)
    yield
    set_workflow_scheduler(None)


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "api.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
    yield source


def _node(node_id, step):
    return {"node_id": node_id, "step_number": step, "title": f"节点{node_id}",
            "executor_type": "human"}


def _publish_schedule(ds, key, cron):
    return publish_workflow(
        ds, workflow_key=key, name=f"流程{key}",
        nodes=[_node("n1", 1), _node("n2", 2)],
        trigger_kind="schedule",
        trigger_expr=json.dumps({"cron": cron}, ensure_ascii=False),
    )


def _client():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(workflow_bp)
    return app.test_client()


# ─────────────────────────────────────────────────────────────────────────────
# 1. schedules 三段聚合
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSchedules聚合:
    def test_三段齐全(self, ds):
        """[C6-API-1] 编排定义 + 触发规则 + 运行实例"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        set_workflow_scheduler(WorkflowScheduleScheduler(ds))
        resp = _client().get('/api/v2/workflows/schedules')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        items = body['data']['items']
        assert len(items) == 1
        item = items[0]
        # 编排定义
        assert item['workflow_key'] == "wf-a"
        assert item['name'] == "流程wf-a"
        assert item['version'] == 1
        assert item['node_count'] == 2
        # 触发规则
        assert item['cron'] == "0 3 * * *"
        assert item['cron_label'] == "每天 03:00"
        assert item['next_run_at'] is not None
        assert item['scheduler_registered'] is True
        # 运行实例（尚无 Run）
        assert item['runs'] == []

    def test_非schedule定义不出现(self, ds):
        """[C6-API-2] 仅列 schedule 定义"""
        publish_workflow(ds, workflow_key="wf-m", name="手动",
                         nodes=[_node("n1", 1)], trigger_kind="manual")
        _publish_schedule(ds, "wf-a", "*/5 * * * *")
        set_workflow_scheduler(WorkflowScheduleScheduler(ds))
        items = _client().get('/api/v2/workflows/schedules').get_json()['data']['items']
        assert [i['workflow_key'] for i in items] == ["wf-a"]

    def test_runs反映最近运行(self, ds):
        """[C6-API-3] 唤起后 runs 带派生状态 + 进度"""
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        sched = WorkflowScheduleScheduler(ds)
        sched.run_now("wf-a")
        set_workflow_scheduler(sched)
        item = _client().get(
            '/api/v2/workflows/schedules').get_json()['data']['items'][0]
        assert len(item['runs']) == 1
        run = item['runs'][0]
        assert run['total'] == 2
        assert run['done'] == 0
        assert run['status'] in ("pending", "in_progress")

    def test_未接线返回503(self, ds):
        """[C6-API-4] 调度器未接线 → 不半答"""
        resp = _client().get('/api/v2/workflows/schedules')
        assert resp.status_code == 503
        assert resp.get_json()['success'] is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. scheduler/status 三态
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class Test调度器状态端点:
    def test_未接线503(self):
        resp = _client().get('/api/v2/workflows/scheduler/status')
        assert resp.status_code == 503

    def test_暂停态200(self):
        set_workflow_scheduler(None, paused=True)
        resp = _client().get('/api/v2/workflows/scheduler/status')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['paused'] is True
        assert data['jobs'] is None

    def test_正常态透传作业状态(self, ds):
        _publish_schedule(ds, "wf-a", "0 3 * * *")
        set_workflow_scheduler(WorkflowScheduleScheduler(ds))
        resp = _client().get('/api/v2/workflows/scheduler/status')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['paused'] is False
        assert set(data['jobs'].keys()) == {"wf-a"}
        assert data['jobs']["wf-a"]['schedule'] == "0 3 * * *"
        assert data['jobs']["wf-a"]['handler_registered'] is True
