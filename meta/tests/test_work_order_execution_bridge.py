# -*- coding: utf-8 -*-
"""G13 / P3-2：工序 → tasks 桥接与 line_refs 回填

依据:
  docs/specs/tasks-project-g12-g13-execution-boundary-2026-11-01.md §6.2

【本文件守什么】
  · 只接受 work_order_id；project_task 不直接生成 tasks（§8.2 硬规则 1）。
  · 仅 source_demand_type='project_task' 且项目一致（AC-09）才可桥接。
  · 每条工序一条 task，doc_ref 指工单、line_refs 回填工序 id（D10 方案 A）。
  · 重复调用幂等，不新增任务。
"""
import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.task_schema import ensure_task_tables  # noqa: E402
from meta.services.work_order_execution_service import (  # noqa: E402
    BridgeError,
    create_operation_tasks,
)
from meta.services.work_order_service import (  # noqa: E402
    WorkOrderError,
    WorkOrderService,
)

pytestmark = pytest.mark.unit

_SCHEMA = (
    """CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY,
    work_order_no TEXT,
    status TEXT DEFAULT 'New',
    schedule_id INTEGER,
    coverage_id INTEGER,
    project_id INTEGER,
    source_demand_type TEXT,
    source_demand_id INTEGER,
    resolved_at TEXT,
    updated_at TEXT
);""",
    """CREATE TABLE project_tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    task_no TEXT,
    name TEXT
);""",
    """CREATE TABLE work_order_operations (
    id INTEGER PRIMARY KEY,
    work_order_id INTEGER,
    seq INTEGER,
    operation_name TEXT,
    status TEXT DEFAULT 'pending'
);""",
    """CREATE TABLE service_events (
    id INTEGER PRIMARY KEY,
    work_order_id INTEGER,
    event_type TEXT,
    occurred_at TEXT,
    actor TEXT,
    payload TEXT,
    note TEXT,
    created_at TEXT
);""",
)


def _build(tmp_path):
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "bridge.db"))
    with source.transaction():
        ensure_task_tables(source)
        for statement in _SCHEMA:
            source.execute(statement)
        source.execute(
            """INSERT INTO project_tasks (id, project_id, task_no, name) VALUES
               (11, 7, 'T-01', '任务A'), (12, 8, 'T-02', '任务B')"""
        )
        source.execute(
            """INSERT INTO work_orders
               (id, work_order_no, project_id, source_demand_type, source_demand_id)
               VALUES
               (21, 'WO-01', 7, 'project_task', 11),
               (22, 'WO-02', 8, 'project_task', 11),
               (23, 'WO-03', 7, 'sales_order_line', NULL)"""
        )
        source.execute(
            """INSERT INTO work_order_operations
               (id, work_order_id, seq, operation_name) VALUES
               (31, 21, 1, '上门诊断'), (32, 21, 2, '更换配件'),
               (33, 22, 1, '巡检')"""
        )
    return source


@pytest.fixture()
def ds(tmp_path):
    yield _build(tmp_path)


def _tasks(ds):
    return ds.query("SELECT id, title, doc_ref, line_refs, status FROM tasks")


class TestBridgeGuards:

    def test_工单不存在被拒(self, ds):
        with pytest.raises(BridgeError) as err:
            create_operation_tasks(ds, 99, created_by="owner")
        assert err.value.rule == "WORK_ORDER_NOT_FOUND"
        assert _tasks(ds) == []

    def test_非_project_task_来源被拒(self, ds):
        with pytest.raises(BridgeError) as err:
            create_operation_tasks(ds, 23, created_by="owner")
        assert err.value.rule == "BRIDGE_SOURCE_NOT_PROJECT_TASK"
        assert _tasks(ds) == []

    def test_项目不一致被拒(self, ds):
        with pytest.raises(BridgeError) as err:
            create_operation_tasks(ds, 22, created_by="owner")
        assert err.value.rule == "PROJECT_MISMATCH"
        assert _tasks(ds) == []


class TestBridgeCreation:

    def test_按工序创建_tasks_并回填_line_refs(self, ds):
        task_ids = create_operation_tasks(ds, 21, created_by="owner")

        assert len(task_ids) == 2
        rows = ds.query(
            "SELECT id, title, doc_ref, line_refs, status FROM tasks "
            "ORDER BY created_at, id"
        )
        assert len(rows) == 2
        assert [row["title"] for row in rows] == ["上门诊断", "更换配件"]
        assert {row["doc_ref"] for row in rows} == {"work_order:21"}
        assert {row["status"] for row in rows} == {"pending"}
        assert sorted(json.loads(row["line_refs"])[0] for row in rows) == ["31", "32"]

    def test_重复调用幂等(self, ds):
        first = create_operation_tasks(ds, 21, created_by="owner")
        second = create_operation_tasks(ds, 21, created_by="owner")

        assert second == first, "幂等应返回已有 task id"
        assert len(_tasks(ds)) == 2, "重复桥接不得新增任务"

    def test_只给_project_task_不生成任务(self, ds):
        # 11 是 project_task 主键，不是工单 → 硬规则 1：项目任务不直接产任务
        with pytest.raises(BridgeError) as err:
            create_operation_tasks(ds, 11, created_by="owner")
        assert err.value.rule == "WORK_ORDER_NOT_FOUND"
        assert _tasks(ds) == []


def _work_order_status(ds, work_order_id):
    return ds.query(
        "SELECT status FROM work_orders WHERE id = ?", [work_order_id])[0]["status"]


class TestStartWorkOrder:

    def test_project_task_工单开工生成任务(self, ds):
        svc = WorkOrderService(ds)
        result = svc.start_work_order(
            21, now="2026-11-02 09:00:00", actor="tester", created_by="tester")

        assert result["status"] == "In Progress"
        assert len(result["task_ids"]) == 2
        assert _work_order_status(ds, 21) == "In Progress"
        assert len(_tasks(ds)) == 2
        events = ds.query(
            "SELECT event_type FROM service_events WHERE work_order_id = 21")
        assert [e["event_type"] for e in events] == ["start"]

    def test_非_project_task_来源只改状态不建任务(self, ds):
        result = WorkOrderService(ds).start_work_order(23)

        assert result["task_ids"] == []
        assert _work_order_status(ds, 23) == "In Progress"
        assert _tasks(ds) == []

    def test_仅新建工单可开始作业(self, ds):
        svc = WorkOrderService(ds)
        svc.start_work_order(21)

        with pytest.raises(WorkOrderError) as err:
            svc.start_work_order(21)
        assert err.value.rule == "ST_STATE_INVALID"

    def test_桥接失败时状态不变(self, ds):
        ds.execute("DELETE FROM work_order_operations WHERE work_order_id = 21")
        with pytest.raises(BridgeError) as err:
            WorkOrderService(ds).start_work_order(21)

        assert err.value.rule == "OPERATION_NOT_FOUND"
        assert _work_order_status(ds, 21) == "New"
        assert _tasks(ds) == []


class _FakeBlacklist:
    @staticmethod
    def is_blacklisted(token):
        return False


class _FakeTokenService:
    @staticmethod
    def verify_token(token):
        return {'user_id': '1', 'username': 'tester', 'token_version': 0,
                'permissions': ['*']}


AUTH = {'Authorization': 'Bearer test-token', 'Content-Type': 'application/json'}


class TestStartWorkOrderApi:

    def test_端点开工并返回任务(self, monkeypatch, ds):
        from flask import Flask

        import meta.api.work_order_api as wo_api
        import meta.services.auth_middleware as auth_mw

        monkeypatch.setattr(auth_mw, 'token_blacklist_service', _FakeBlacklist())
        monkeypatch.setattr(auth_mw, 'TokenService', _FakeTokenService)
        wo_api.init_service(ds)
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(wo_api.work_order_bp)
        client = app.test_client()
        try:
            resp = client.post('/api/v1/work-orders/21/start',
                               headers=AUTH, json={})
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['success'] is True
            assert body['data']['status'] == 'In Progress'
            assert len(body['data']['task_ids']) == 2

            again = client.post('/api/v1/work-orders/21/start',
                                headers=AUTH, json={})
            assert again.status_code == 400
            assert again.get_json()['code'] == 'ST_STATE_INVALID'
        finally:
            wo_api._service = None

