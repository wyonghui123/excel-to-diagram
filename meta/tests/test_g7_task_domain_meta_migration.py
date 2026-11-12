# -*- coding: utf-8 -*-
"""G7 任务域六表进统一元模型验收测试

覆盖:
  1. 六个 YAML schema 注册进 registry，且 skip_generic_api 生效
     （通用 v1/v2 路由、agent 工具、通用对象元数据入口均不暴露）
  2. v154 provisioning 幂等（第二次不新建表）+ 六表与索引齐全
  3. 六表 DDL 与迁移前代码定义逐列/逐索引等价
  4. 通用更新路径状态机拦截：非法迁移被拒（STATE_MACHINE_VIOLATION / 400），
     合法迁移放行
"""
import sqlite3

import pytest

from meta.core.models import registry
from meta.core.schema_generator import SchemaGenerator
from meta.core.task_event_schema import (
    TASK_EVENT_TABLE,
    WORKLOG_TABLE,
    ensure_task_event_tables,
)
from meta.core.task_schema import (
    TASK_TABLE,
    TASK_TEMPLATE_TABLE,
    WORKFLOW_RUN_TABLE,
    WORKFLOW_TABLE,
    ensure_task_tables,
    get_task_meta_objects,
)

pytestmark = pytest.mark.integration

# 六对象：id → 表名（与代码常量完全一致）
EXPECTED_OBJECTS = {
    "workflow": WORKFLOW_TABLE,
    "task_template": TASK_TEMPLATE_TABLE,
    "workflow_run": WORKFLOW_RUN_TABLE,
    "task": TASK_TABLE,
    "task_event": TASK_EVENT_TABLE,
    "task_worklog": WORKLOG_TABLE,
}

# ---------------------------------------------------------------------------
# 迁移前基线（改动前由代码 MetaObject 经 SchemaGenerator 生成的 DDL，逐行抄录）
# ---------------------------------------------------------------------------

EXPECTED_COLUMNS = {
    "workflow": [
        "id VARCHAR(200) PRIMARY KEY",
        "workflow_key VARCHAR(200) NOT NULL",
        "version INTEGER NOT NULL",
        "name VARCHAR(200) NOT NULL",
        "description TEXT",
        "owner VARCHAR(200)",
        "trigger_kind VARCHAR(200) DEFAULT 'manual'",
        "trigger_expr VARCHAR(200)",
        "edges TEXT",
        "sla TEXT",
        "meta TEXT",
        "created_by VARCHAR(200)",
        "created_at DATETIME",
        "updated_at DATETIME",
    ],
    "task_template": [
        "id VARCHAR(200) PRIMARY KEY",
        "workflow_id VARCHAR(200) NOT NULL",
        "workflow_version INTEGER NOT NULL",
        "node_id VARCHAR(200) NOT NULL",
        "step_number INTEGER",
        "parent_step_number INTEGER",
        "group_name VARCHAR(200)",
        "title VARCHAR(200) NOT NULL",
        "description TEXT",
        "type VARCHAR(200) NOT NULL DEFAULT 'story'",
        "priority VARCHAR(200) DEFAULT 'P2'",
        "executor_type VARCHAR(200) NOT NULL",
        "executor_assignee VARCHAR(200)",
        "executor_candidates TEXT",
        "assign_policy VARCHAR(200) DEFAULT 'direct'",
        "executor_config TEXT",
        "executor_fallback TEXT",
        "claim_timeout_seconds INTEGER DEFAULT 300",
        "timeout_seconds INTEGER",
        "retry_policy TEXT",
        "inputs_schema TEXT",
        "outputs_schema TEXT",
        "acceptance TEXT",
        "sla TEXT",
        "meta TEXT",
        "created_at DATETIME",
        "updated_at DATETIME",
    ],
    "workflow_run": [
        "id VARCHAR(200) PRIMARY KEY",
        "workflow_id VARCHAR(200) NOT NULL",
        "workflow_key VARCHAR(200)",
        "workflow_version INTEGER NOT NULL",
        "name VARCHAR(200)",
        "trigger_kind VARCHAR(200)",
        "definition_snapshot TEXT",
        "variables TEXT",
        "inputs TEXT",
        "outputs TEXT",
        "created_by VARCHAR(200)",
        "created_at DATETIME",
        "started_at DATETIME",
        "finished_at DATETIME",
        "meta TEXT",
        "updated_at DATETIME",
    ],
    "task": [
        "id VARCHAR(200) PRIMARY KEY",
        "code VARCHAR(200)",
        "title VARCHAR(200) NOT NULL",
        "description TEXT",
        "type VARCHAR(200) NOT NULL DEFAULT 'story'",
        "status VARCHAR(200) NOT NULL DEFAULT 'pending'",
        "priority VARCHAR(200) DEFAULT 'P2'",
        "app_id VARCHAR(200)",
        "executor_type VARCHAR(200) NOT NULL",
        "executor_assignee VARCHAR(200)",
        "executor_candidates TEXT",
        "assign_policy VARCHAR(200) DEFAULT 'direct'",
        "executor_config TEXT",
        "executor_fallback TEXT",
        "claim_timeout_seconds INTEGER DEFAULT 300",
        "timeout_seconds INTEGER",
        "retry_policy TEXT",
        "due_at DATETIME",
        "sla TEXT",
        "parent_task_id VARCHAR(200)",
        "workflow_run_id VARCHAR(200)",
        "workflow_node_id VARCHAR(200)",
        "deps TEXT",
        "inputs TEXT",
        "inputs_schema TEXT",
        "outputs TEXT",
        "outputs_schema TEXT",
        "acceptance TEXT",
        "attempt INTEGER DEFAULT 1",
        "trace_id VARCHAR(200)",
        "agent_session_id VARCHAR(200)",
        "doc_ref VARCHAR(200)",
        "line_refs TEXT",
        "created_by VARCHAR(200)",
        "created_at DATETIME",
        "started_at DATETIME",
        "finished_at DATETIME",
        "fail_reason VARCHAR(200)",
        "meta TEXT",
        "updated_at DATETIME",
    ],
    "task_event": [
        "id VARCHAR(200) PRIMARY KEY",
        "task_id VARCHAR(200) NOT NULL",
        "workflow_run_id VARCHAR(200)",
        "event_type VARCHAR(200) NOT NULL DEFAULT 'status_changed'",
        "from_status VARCHAR(200)",
        "to_status VARCHAR(200)",
        "actor VARCHAR(200)",
        "actor_kind VARCHAR(200)",
        "reason VARCHAR(200)",
        "payload TEXT",
        "doc_ref VARCHAR(200)",
        "line_refs TEXT",
        "agent_session_id VARCHAR(200)",
        "trace_id VARCHAR(200)",
        "occurred_at DATETIME NOT NULL",
        "created_at DATETIME",
    ],
    "task_worklog": [
        "id VARCHAR(200) PRIMARY KEY",
        "task_id VARCHAR(200) NOT NULL",
        "workflow_run_id VARCHAR(200)",
        "event_id VARCHAR(200)",
        "entry_type VARCHAR(200) NOT NULL DEFAULT 'transition'",
        "actor VARCHAR(200)",
        "actor_kind VARCHAR(200)",
        "summary VARCHAR(200)",
        "detail TEXT",
        "inputs_hash VARCHAR(200)",
        "outputs_hash VARCHAR(200)",
        "progress_pct INTEGER",
        "doc_ref VARCHAR(200)",
        "trace_id VARCHAR(200)",
        "occurred_at DATETIME NOT NULL",
        "created_at DATETIME",
    ],
}

EXPECTED_INDEXES = {
    "workflow": [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_key_version ON workflows(workflow_key, version)",
        "CREATE INDEX IF NOT EXISTS idx_workflow_key ON workflows(workflow_key)",
    ],
    "task_template": [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_task_template_node ON task_templates(workflow_id, workflow_version, node_id)",
        "CREATE INDEX IF NOT EXISTS idx_task_template_wf ON task_templates(workflow_id, workflow_version)",
    ],
    "workflow_run": [
        "CREATE INDEX IF NOT EXISTS idx_run_workflow ON workflow_runs(workflow_id)",
        "CREATE INDEX IF NOT EXISTS idx_run_key ON workflow_runs(workflow_key)",
    ],
    "task": [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_code ON tasks(code)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_inbox ON tasks(app_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(executor_type, executor_assignee, status)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(workflow_run_id)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_doc ON tasks(doc_ref)",
    ],
    "task_event": [
        "CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, occurred_at)",
        "CREATE INDEX IF NOT EXISTS idx_task_events_run ON task_events(workflow_run_id)",
        "CREATE INDEX IF NOT EXISTS idx_task_events_type ON task_events(event_type, occurred_at)",
        "CREATE INDEX IF NOT EXISTS idx_task_events_doc ON task_events(doc_ref)",
        "CREATE INDEX IF NOT EXISTS idx_task_events_trace ON task_events(trace_id)",
    ],
    "task_worklog": [
        "CREATE INDEX IF NOT EXISTS idx_task_worklogs_task ON task_worklogs(task_id, occurred_at)",
        "CREATE INDEX IF NOT EXISTS idx_task_worklogs_run ON task_worklogs(workflow_run_id)",
        "CREATE INDEX IF NOT EXISTS idx_task_worklogs_event ON task_worklogs(event_id)",
    ],
}


def _get_object(obj_id):
    obj = registry.get(obj_id)
    assert obj is not None, f"registry 缺少 {obj_id}"
    return obj


def _table_from_ddl(sql):
    lines = sql.strip().splitlines()
    assert lines[0].startswith("CREATE TABLE IF NOT EXISTS "), lines[0]
    assert lines[-1].strip() == ")", lines[-1]
    return [line.strip().rstrip(",") for line in lines[1:-1]]


# ---------------------------------------------------------------------------
# 1. YAML 加载 + skip_generic_api 生效
# ---------------------------------------------------------------------------

class TestYamlRegisteredObjects:

    def test_six_objects_registered_with_expected_tables(self):
        objs = get_task_meta_objects()
        assert [o.id for o in objs] == list(EXPECTED_OBJECTS)
        for obj_id, table in EXPECTED_OBJECTS.items():
            obj = _get_object(obj_id)
            assert obj.table_name == table
            assert obj.persistent is True
            assert obj.skip_generic_api is True, f"{obj_id} 必须关闭通用 API"

    def test_task_requires_state_machine(self):
        task = _get_object("task")
        assert task.requires_state_machine() is True
        # 其余五表无状态机
        for obj_id in EXPECTED_OBJECTS:
            if obj_id != "task":
                assert _get_object(obj_id).requires_state_machine() is False

    def test_no_generic_crud_actions(self):
        for obj_id in EXPECTED_OBJECTS:
            action_ids = {a.id for a in (_get_object(obj_id).actions or [])}
            assert not action_ids.intersection(
                {"crud_create", "crud_read", "crud_update", "crud_delete", "crud_list"}
            ), f"{obj_id} 不应有通用 CRUD actions"
            assert not action_ids.intersection(
                {f"{obj_id}_create", f"{obj_id}_read", f"{obj_id}_update",
                 f"{obj_id}_delete", f"{obj_id}_list"}
            ), f"{obj_id} 不应有对象级 CRUD actions"

    def test_generic_v1_meta_entry_hidden(self):
        """GET /api/v1/meta/objects 不暴露六个平台机制对象。"""
        from flask import Flask
        from meta.api.meta_api import meta_bp

        app = Flask(__name__)
        app.register_blueprint(meta_bp)
        client = app.test_client()
        resp = client.get("/api/v1/meta/objects")
        assert resp.status_code == 200
        exposed = {item["id"] for item in resp.get_json()["data"]}
        assert not exposed.intersection(EXPECTED_OBJECTS)

    def test_agent_tools_hidden(self):
        """GET /api/v1/agent/tools 不为六个对象生成任何工具。"""
        from flask import Flask
        from meta.api.agent_api import agent_bp

        app = Flask(__name__)
        app.register_blueprint(agent_bp)
        client = app.test_client()
        resp = client.get("/api/v1/agent/tools")
        assert resp.status_code == 200
        names = {tool["name"] for tool in resp.get_json()["data"]}
        for obj_id in EXPECTED_OBJECTS:
            generic = {
                f"{verb}_{obj_id}"
                for verb in ("list", "get", "create", "update", "delete")
            }
            assert not names.intersection(generic), obj_id

    def test_generic_v1_crud_route_rejected(self):
        """GET /api/v1/<object_type> 对六个对象返回 404 GENERIC_API_DISABLED。"""
        from flask import Flask
        from meta.api.manage_api import manage_bp

        app = Flask(__name__)
        app.register_blueprint(manage_bp)
        client = app.test_client()
        for obj_id in EXPECTED_OBJECTS:
            resp = client.get(f"/api/v1/{obj_id}")
            assert resp.status_code == 404, obj_id
            body = resp.get_json()
            assert body["error_code"] == "GENERIC_API_DISABLED", obj_id

    def test_generic_v2_bo_route_rejected(self):
        """GET /api/v2/bo/<object_type> 对六个对象返回 404 GENERIC_API_DISABLED。"""
        from flask import Flask
        from meta.api.bo_api import bo_bp

        app = Flask(__name__)
        app.register_blueprint(bo_bp)
        client = app.test_client()
        for obj_id in EXPECTED_OBJECTS:
            resp = client.get(f"/api/v2/bo/{obj_id}")
            assert resp.status_code == 404, obj_id
            body = resp.get_json()
            assert body["error_code"] == "GENERIC_API_DISABLED", obj_id


# ---------------------------------------------------------------------------
# 2. v154 provisioning 幂等 + 六表/索引存在
# ---------------------------------------------------------------------------

def _sqlite_tables_and_indexes(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        indexes = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        columns = {}
        for table in EXPECTED_OBJECTS.values():
            columns[table] = [
                row[1] for row in conn.execute(
                    'PRAGMA table_info("{0}")'.format(table)
                ).fetchall()
            ]
        return tables, indexes, columns
    finally:
        conn.close()


class TestV154Provisioning:

    def test_migrate_idempotent_tables_and_indexes(self, tmp_path):
        from meta.migrations.v154__provision_task_domain_tables import migrate, verify

        db_path = tmp_path / "v154_g7.db"
        sqlite3.connect(str(db_path)).close()

        assert migrate(db_path) is True
        assert verify(db_path) is True

        tables, indexes, columns = _sqlite_tables_and_indexes(db_path)
        assert set(EXPECTED_OBJECTS.values()).issubset(tables)
        expected_index_names = {
            "uq_workflow_key_version", "idx_workflow_key",
            "uq_task_template_node", "idx_task_template_wf",
            "idx_run_workflow", "idx_run_key",
            "uq_tasks_code", "idx_tasks_status", "idx_tasks_inbox",
            "idx_tasks_assignee", "idx_tasks_run", "idx_tasks_parent",
            "idx_tasks_doc",
            "idx_task_events_task", "idx_task_events_run", "idx_task_events_type",
            "idx_task_events_doc", "idx_task_events_trace",
            "idx_task_worklogs_task", "idx_task_worklogs_run",
            "idx_task_worklogs_event",
        }
        assert expected_index_names.issubset(indexes)
        for table, expected in EXPECTED_COLUMNS.items():
            actual = columns[EXPECTED_OBJECTS[table]]
            assert actual == [line.split(" ")[0] for line in expected]

        # 第二次执行：不新建表（幂等），列结构不变
        before = {t: len(cols) for t, cols in columns.items()}
        assert migrate(db_path) is True
        assert verify(db_path) is True
        _, _, columns_after = _sqlite_tables_and_indexes(db_path)
        assert {t: len(cols) for t, cols in columns_after.items()} == before

    def test_ensure_task_tables_returns_sql_and_idempotent(self, tmp_path):
        from meta.core.datasource import get_data_source

        ds = get_data_source("sqlite", database=str(tmp_path / "ensure_g7.db"))
        first = ensure_task_tables(ds)
        assert any(sql.strip().upper().startswith("CREATE TABLE") for sql in first)
        second = ensure_task_tables(ds)
        assert not any(sql.strip().upper().startswith("CREATE TABLE") for sql in second)

        event_first = ensure_task_event_tables(ds)
        assert any(sql.strip().upper().startswith("CREATE TABLE") for sql in event_first)
        event_second = ensure_task_event_tables(ds)
        assert not any(sql.strip().upper().startswith("CREATE TABLE")
                       for sql in event_second)


# ---------------------------------------------------------------------------
# 3. DDL 逐列 / 逐索引等价
# ---------------------------------------------------------------------------

class TestDdlEquivalence:

    def test_create_table_columns_match_baseline(self):
        generator = SchemaGenerator("sqlite")
        for obj_id, expected in EXPECTED_COLUMNS.items():
            obj = _get_object(obj_id)
            actual = _table_from_ddl(generator.generate_create_table(obj))
            assert actual == expected, f"{obj_id} 列定义与迁移前不等价"

    def test_create_indexes_match_baseline(self):
        generator = SchemaGenerator("sqlite")
        for obj_id, expected in EXPECTED_INDEXES.items():
            obj = _get_object(obj_id)
            assert generator.generate_create_index(obj) == expected, \
                f"{obj_id} 索引定义与迁移前不等价"


# ---------------------------------------------------------------------------
# 4. 通用更新路径状态机拦截
# ---------------------------------------------------------------------------

@pytest.fixture()
def task_ds(tmp_path):
    """独立临时库：只建任务域六表，避免碰 architecture.db。"""
    from meta.core.datasource import get_data_source

    ds = get_data_source("sqlite", database=str(tmp_path / "g7_state_machine.db"))
    ensure_task_tables(ds)
    ensure_task_event_tables(ds)
    ds.insert("tasks", {
        "id": "g7-sm-1",
        "title": "G7 状态机拦截",
        "executor_type": "system",
        "status": "pending",
    })
    yield ds
    ds.disconnect()


def _task_status(ds, task_id="g7-sm-1"):
    record = ds.find_by_id("tasks", task_id)
    return record.get("status") if record else None


class _GenericTaskRegistry:
    """为状态机放行用例提供带通用 crud_update 的 task 探针对象。

    真实 task 对象 skip_generic_api=True（不生成通用 action），直接走
    ManageService 会在守卫之后报 ACTION_NOT_FOUND。本用例把对象浅替为
    “补回通用 actions 的 task 副本”，以便验证合法迁移确实能穿过守卫落到执行器。
    """

    def __init__(self, probe):
        self._probe = probe

    def get(self, object_id):
        if object_id == "task":
            return self._probe
        return registry.get(object_id)

    def list_objects(self):
        return registry.list_objects()


@pytest.fixture()
def task_probe(task_ds, monkeypatch):
    import copy
    from meta.core.yaml_loader import ensure_crud_actions

    probe = copy.deepcopy(registry.get("task"))
    probe.skip_generic_api = False
    probe = ensure_crud_actions(probe)
    monkeypatch.setattr(
        "meta.services.manage_service.registry", _GenericTaskRegistry(probe)
    )
    return task_ds


class TestStateMachineGuard:

    def test_illegal_transition_rejected_with_400(self, task_probe):
        from meta.services.manage_service import ManageService, UpdateRequest

        result = ManageService(task_probe).update(
            UpdateRequest(
                object_type="task", id="g7-sm-1",
                data={"status": "done"}, skip_audit=True,
            )
        )
        assert result.success is False
        assert result.error == "STATE_MACHINE_VIOLATION"
        assert result.status_code == 400
        assert _task_status(task_probe) == "pending", "非法迁移不得落库"

    def test_legal_transition_allowed(self, task_probe):
        from meta.services.manage_service import ManageService, UpdateRequest

        result = ManageService(task_probe).update(
            UpdateRequest(
                object_type="task", id="g7-sm-1",
                data={"status": "cancelled"}, skip_audit=True,
            )
        )
        assert result.success is True, (result.error, result.message, result.errors)
        assert _task_status(task_probe) == "cancelled"

    def test_guarded_transition_fails_closed(self, task_probe):
        """有守卫的迁移在通用路径无上下文 ⇒ 拒绝（fail-closed）。"""
        from meta.services.manage_service import ManageService, UpdateRequest

        result = ManageService(task_probe).update(
            UpdateRequest(
                object_type="task", id="g7-sm-1",
                data={"status": "ready"}, skip_audit=True,
            )
        )
        assert result.success is False
        assert result.error == "STATE_MACHINE_VIOLATION"
        assert _task_status(task_probe) == "pending"

    def test_non_status_update_not_blocked(self, task_probe):
        """不改 status 的普通字段更新不受状态机影响。"""
        from meta.services.manage_service import ManageService, UpdateRequest

        result = ManageService(task_probe).update(
            UpdateRequest(
                object_type="task", id="g7-sm-1",
                data={"title": "新标题"}, skip_audit=True,
            )
        )
        assert result.success is True, (result.error, result.message, result.errors)
