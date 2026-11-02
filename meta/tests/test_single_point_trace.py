# -*- coding: utf-8 -*-
"""G13 双通道定界：报工口径（P3-3）+ 单点留痕（P3-4）

依据:
  docs/specs/tasks-project-g12-g13-execution-boundary-2026-11-01.md §3 Phase 3

【本文件守什么】
  P3-3 实际工时唯一载体 = `time_entries`（v182）；`work_order_operations` 不落
       actual / reported / 完成数量列。
  P3-4 一次任务动作 = 一条 `tasks` 状态流转 + 一条 `task_events`（另配一条
       WORKLOG）；任务状态迁移不写 `work_order_operations.status`（动作只在 tasks
       一处留痕，工序侧只存参数）。
  P3-1 工序 `status` 是只读投影：通用更新路径跳过该字段，手工推进不落库。
"""
import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json
import logging
import yaml
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.models import registry  # noqa: E402
from meta.core.task_event_schema import (  # noqa: E402
    ensure_task_event_tables,
    record_transition,
)
from meta.core.task_schema import ensure_task_tables  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")
GENERATED_SQL = os.path.join(SCHEMA_DIR, "generated_schema.sql")

pytestmark = pytest.mark.unit

# 工序表禁止出现的「实际工时 / 完成数量」列（口径分裂的典型别名）
FORBIDDEN_OPERATION_COLUMNS = (
    "actual_minutes", "actual_hours", "actual_qty",
    "reported_minutes", "reported_hours", "reported_qty",
    "completed_qty", "qty_done", "hours_actual",
)

_TS = "2026-11-02T09:00:00"


def _load_raw(bo_id):
    with open(os.path.join(SCHEMA_DIR, bo_id + ".yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _table_block(sql, table):
    marker = "CREATE TABLE IF NOT EXISTS %s (" % table
    start = sql.find(marker)
    assert start != -1, "generated_schema.sql 缺少表 %s" % table
    end = sql.find("\n)", start)
    assert end != -1, "generated_schema.sql 中表 %s 未闭合" % table
    return sql[start:end]


def _build(tmp_path):
    """临时库：任务六表中的 tasks / task_events / task_worklogs + 工序骨架表。"""
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "trace.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        source.execute(
            """CREATE TABLE IF NOT EXISTS work_order_operations (
                   id VARCHAR(200) PRIMARY KEY,
                   work_order_id VARCHAR(200),
                   operation_name VARCHAR(200),
                   status VARCHAR(50) NOT NULL DEFAULT 'pending'
               )"""
        )
    return source


def _task(ds, task_id):
    ds.execute(
        """INSERT INTO tasks
           (id, title, type, status, priority, executor_type,
            created_by, created_at, updated_at)
           VALUES (?, ?, 'story', 'pending', 'P2', 'human', 'owner', ?, ?)""",
        (task_id, "测试任务", _TS, _TS),
    )


def _operation(ds, op_id, status="pending"):
    ds.execute(
        """INSERT INTO work_order_operations
           (id, work_order_id, operation_name, status)
           VALUES (?, 'WO-1', '装配', ?)""",
        (op_id, status),
    )


@pytest.fixture()
def ds(tmp_path):
    yield _build(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# P3-3 报工口径：工序不落 actual 列
# ─────────────────────────────────────────────────────────────────────────────

class TestReportingCaliber:
    def test_工序字段无实际工时列(self):
        raw = _load_raw("work_order_operation")
        names = set()
        for field in raw.get("fields") or []:
            names.add(field.get("id") or "")
            names.add(field.get("db_column") or "")
        hit = names.intersection(FORBIDDEN_OPERATION_COLUMNS)
        assert not hit, "工序表出现实际工时列: %s" % sorted(hit)

    def test_工序_DDL_无实际工时列(self):
        with open(GENERATED_SQL, "r", encoding="utf-8") as f:
            sql = f.read()
        block = _table_block(sql, "work_order_operations")
        lowered = block.lower()
        for column in FORBIDDEN_OPERATION_COLUMNS:
            assert column not in lowered, "工序 DDL 出现 %s" % column

    def test_实际工时唯一载体是_time_entries(self):
        with open(GENERATED_SQL, "r", encoding="utf-8") as f:
            sql = f.read()
        # v182 工时表存在，且唯一计数列是 minutes
        block = _table_block(sql, "time_entries")
        assert "minutes INTEGER NOT NULL" in block
        for column in FORBIDDEN_OPERATION_COLUMNS:
            assert column not in block.lower(), "time_entries 出现重复口径 %s" % column

    def test_time_entry_元模型以_minutes_承载实际工时(self):
        raw = _load_raw("time_entry")
        field_ids = {f.get("id") for f in raw.get("fields") or []}
        assert "minutes" in field_ids
        assert not field_ids.intersection(FORBIDDEN_OPERATION_COLUMNS)


# ─────────────────────────────────────────────────────────────────────────────
# P3-4 单点留痕：一次动作一条状态流转 + 一条事件
# ─────────────────────────────────────────────────────────────────────────────

class TestSinglePointTrace:
    def test_一次迁移只产生一条事件与一条_worklog(self, ds):
        _task(ds, "T-TRACE-1")

        event_id, worklog_id = record_transition(
            ds,
            task_id="T-TRACE-1",
            from_status="pending",
            to_status="ready",
            actor="u1",
            actor_kind="human",
            reason="派工",
        )

        events = ds.execute(
            """SELECT id, event_type, from_status, to_status, line_refs
               FROM task_events WHERE task_id = ?""",
            ("T-TRACE-1",),
        ).fetchall()
        assert len(events) == 1, "一次动作应只落一条事件，实际 %d" % len(events)
        assert events[0][1] == "status_changed"
        assert events[0][2] == "pending" and events[0][3] == "ready"
        assert events[0][0] == event_id

        worklogs = ds.execute(
            """SELECT id, entry_type, event_id FROM task_worklogs
               WHERE task_id = ?""",
            ("T-TRACE-1",),
        ).fetchall()
        assert len(worklogs) == 1, "一次迁移应配一条 WORKLOG，实际 %d" % len(worklogs)
        assert worklogs[0][1] == "transition"
        assert worklogs[0][2] == event_id
        assert worklogs[0][0] == worklog_id

    def test_事件与_worklog_一一对应(self, ds):
        _task(ds, "T-TRACE-2")
        for from_status, to_status in (("pending", "ready"), ("ready", "claimed")):
            record_transition(
                ds,
                task_id="T-TRACE-2",
                from_status=from_status,
                to_status=to_status,
                actor="u1",
                actor_kind="human",
            )

        event_ids = {
            row[0] for row in ds.execute(
                """SELECT id FROM task_events
                   WHERE task_id = ? AND event_type = 'status_changed'""",
                ("T-TRACE-2",),
            ).fetchall()
        }
        paired = {
            row[0] for row in ds.execute(
                """SELECT event_id FROM task_worklogs
                   WHERE task_id = ? AND entry_type = 'transition'""",
                ("T-TRACE-2",),
            ).fetchall()
        }
        assert event_ids == paired, "status_changed 事件与 transition WORKLOG 未一一配对"

    def test_任务迁移不写工序状态(self, ds):
        _task(ds, "T-TRACE-3")
        _operation(ds, "OP-1", status="pending")

        record_transition(
            ds,
            task_id="T-TRACE-3",
            from_status="pending",
            to_status="ready",
            actor="u1",
            actor_kind="human",
            line_refs=["OP-1"],
        )

        rows = ds.execute(
            "SELECT status FROM work_order_operations WHERE id = ?", ("OP-1",),
        ).fetchall()
        assert rows and rows[0][0] == "pending", "任务迁移不应改写工序状态（双通道定界）"

        # line_refs 指回工序，动作留痕可从任务侧反查工序
        line_refs = ds.execute(
            "SELECT line_refs FROM task_events WHERE task_id = ?", ("T-TRACE-3",),
        ).fetchall()
        assert json.loads(line_refs[0][0]) == ["OP-1"]


# ─────────────────────────────────────────────────────────────────────────────
# P3-1 工序状态只读投影（P3-4 后半：不可手工推进）
# ─────────────────────────────────────────────────────────────────────────────

def _reload_quietly():
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(SCHEMA_DIR)
    finally:
        logging.disable(logging.NOTSET)


def _status_field():
    meta_obj = registry.get("work_order_operation")
    assert meta_obj is not None, "registry 缺少 work_order_operation"
    for f in meta_obj.fields:
        if f.id == "status":
            return f
    raise AssertionError("work_order_operation 缺少 status 字段")


def _op_status(ds, op_id):
    rows = ds.execute(
        "SELECT status FROM work_order_operations WHERE id = ?", (op_id,),
    ).fetchall()
    return rows[0][0] if rows else None


def _op_name(ds, op_id):
    rows = ds.execute(
        "SELECT operation_name FROM work_order_operations WHERE id = ?", (op_id,),
    ).fetchall()
    return rows[0][0] if rows else None


class TestOperationStatusProjection:
    def test_yaml_声明只读(self):
        raw = _load_raw("work_order_operation")
        status = next(f for f in raw["fields"] if f.get("id") == "status")
        assert status["semantics"]["readonly_always"] is True
        assert status["ui"]["editable"] is False

    def test_registry_携带只读语义(self):
        _reload_quietly()
        assert _status_field().semantics.readonly_always is True

    def test_通用更新不能手工推进状态(self, ds):
        from meta.services.manage_service import ManageService, UpdateRequest

        _operation(ds, "1", status="pending")
        result = ManageService(ds).update(UpdateRequest(
            object_type="work_order_operation",
            id=1,
            data={"status": "completed"},
            skip_audit=True,
        ))

        assert _op_status(ds, "1") == "pending", "工序状态不得经通用更新推进"
        assert result.success is True, (result.error, result.message)

    def test_携带其它字段时状态仍不变(self, ds):
        from meta.services.manage_service import ManageService, UpdateRequest

        _operation(ds, "2", status="pending")
        result = ManageService(ds).update(UpdateRequest(
            object_type="work_order_operation",
            id=2,
            data={"status": "completed", "operation_name": "复检"},
            skip_audit=True,
        ))

        assert result.success is True, (result.error, result.message)
        assert _op_name(ds, "2") == "复检", "可写字段应正常落库"
        assert _op_status(ds, "2") == "pending", "只读状态不得被顺带改写"
