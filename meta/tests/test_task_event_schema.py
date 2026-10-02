import pytest

pytestmark = pytest.mark.unit

"""
后端测试套件 - 任务事件账 schema（A3）
测试 meta.core.task_event_schema 模块（TASK_EVENT + WORKLOG）

覆盖目标（对齐 §12.1 A3）：
  1. 两表 MetaObject 结构（含 OCED 对象关联列）
  2. 幂等建表 + legacy 不破坏 + 主键
  3. 「每次迁移 = 一条 TASK_EVENT + 一条 WORKLOG」配对不变量
  4. append-only（无 update / delete API）
  5. 非法迁移不落脏事件（借 A2 状态机校验）
"""

import pytest

from meta.core.task_event_schema import (
    EVENT_TYPES,
    TASK_EVENT_TABLE,
    WORKLOG_ENTRY_TYPES,
    WORKLOG_TABLE,
    build_task_event_meta_objects,
    ensure_task_event_tables,
    record_task_event,
    record_transition,
    task_event_tables_exist,
)
from meta.core.task_state_machine import TaskTransitionError


@pytest.fixture()
def ds(tmp_path):
    """独立临时库（不碰 architecture.db），预置一张 legacy 表用于验证不破坏。"""
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "a3.db"))
    with source.transaction():
        source.execute(
            "CREATE TABLE IF NOT EXISTS a3_legacy (id INTEGER PRIMARY KEY, name TEXT)"
        )
    yield source


def _columns(ds, table):
    return [r[1] for r in ds.execute(f"PRAGMA table_info({table})").fetchall()]


def _count(ds, table):
    return ds.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class TestMetaObjects:
    """两表 MetaObject 结构"""

    def test_two_objects_with_expected_table_names(self):
        """TC-TEV-001: 恰两张表 task_events / task_worklogs"""
        objs = build_task_event_meta_objects()
        assert [o.table_name for o in objs] == [TASK_EVENT_TABLE, WORKLOG_TABLE]

    def test_event_type_value_set(self):
        """TC-TEV-002: 事件类型值域 = created/status_changed/hold/release"""
        assert EVENT_TYPES == ("created", "status_changed", "hold", "release")
        assert set(WORKLOG_ENTRY_TYPES) == {
            "transition", "bo_call", "agent_tool", "heartbeat", "note"}

    def test_task_event_has_oced_object_refs(self):
        """TC-TEV-003: TASK_EVENT 携带 OCED 对象关联列（§16.4）"""
        obj = build_task_event_meta_objects()[0]
        cols = {f.db_column for f in obj.fields}
        for required in ("task_id", "workflow_run_id", "doc_ref", "line_refs",
                         "agent_session_id", "trace_id", "actor", "event_type",
                         "from_status", "to_status", "occurred_at"):
            assert required in cols, f"缺列 {required}"

    def test_worklog_has_audit_fields(self):
        """TC-TEV-004: WORKLOG 含 event_id 配对与输入输出哈希"""
        obj = build_task_event_meta_objects()[1]
        cols = {f.db_column for f in obj.fields}
        for required in ("task_id", "event_id", "entry_type", "summary",
                         "inputs_hash", "outputs_hash", "progress_pct", "occurred_at"):
            assert required in cols, f"缺列 {required}"

    def test_indexes_declared(self):
        """TC-TEV-005: 两表索引已声明"""
        ev, wl = build_task_event_meta_objects()
        assert {i.name for i in ev.indexes} == {
            "idx_task_events_task", "idx_task_events_run", "idx_task_events_type",
            "idx_task_events_doc", "idx_task_events_trace"}
        assert {i.name for i in wl.indexes} == {
            "idx_task_worklogs_task", "idx_task_worklogs_run", "idx_task_worklogs_event"}


class TestEnsureTables:
    """幂等建表"""

    def test_creates_both_tables(self, ds):
        """TC-TEV-010: 建表后两表存在"""
        ensure_task_event_tables(ds)
        assert task_event_tables_exist(ds) == {
            TASK_EVENT_TABLE: True, WORKLOG_TABLE: True}

    def test_idempotent_second_run(self, ds):
        """TC-TEV-011: 二次执行幂等，不报错、表仍在"""
        ensure_task_event_tables(ds)
        ensure_task_event_tables(ds)
        assert all(task_event_tables_exist(ds).values())

    def test_legacy_table_unchanged(self, ds):
        """TC-TEV-012: 既有表列不受影响"""
        before = _columns(ds, "a3_legacy")
        ensure_task_event_tables(ds)
        assert _columns(ds, "a3_legacy") == before

    def test_primary_key_on_id(self, ds):
        """TC-TEV-013: 两表主键均为 id"""
        ensure_task_event_tables(ds)
        for table in (TASK_EVENT_TABLE, WORKLOG_TABLE):
            pk = [r[1] for r in ds.execute(f"PRAGMA table_info({table})").fetchall() if r[5]]
            assert pk == ["id"]

    def test_event_has_no_status_column(self, ds):
        """TC-TEV-014: 事件账不改状态列（hold 事件化不改状态列之纪律）"""
        ensure_task_event_tables(ds)
        assert "status" not in _columns(ds, TASK_EVENT_TABLE)


class TestRecordTaskEvent:
    """单事件写入"""

    def test_record_created_event(self, ds):
        """TC-TEV-020: created 事件落账，字段一致"""
        ensure_task_event_tables(ds)
        with ds.transaction():
            eid = record_task_event(
                ds, task_id="t1", event_type="created", to_status="pending",
                actor="alice", actor_kind="human", doc_ref="SO-001",
                payload={"src": "manual"}, trace_id="tr-1")

        row = ds.execute(
            "SELECT task_id, event_type, to_status, actor, actor_kind, doc_ref, "
            "payload, trace_id FROM task_events WHERE id=?", (eid,)).fetchone()
        assert row[0] == "t1"
        assert row[1] == "created"
        assert row[2] == "pending"
        assert row[3] == "alice"
        assert row[4] == "human"
        assert row[5] == "SO-001"
        assert '"src"' in row[6]
        assert row[7] == "tr-1"

    def test_invalid_event_type_rejected(self, ds):
        """TC-TEV-021: 未知事件类型抛 ValueError"""
        ensure_task_event_tables(ds)
        with pytest.raises(ValueError):
            with ds.transaction():
                record_task_event(ds, task_id="t1", event_type="bogus")

    def test_hold_and_release_do_not_set_status(self, ds):
        """TC-TEV-022: hold / release 事件不填状态列（Q3 事件化）"""
        ensure_task_event_tables(ds)
        with ds.transaction():
            record_task_event(ds, task_id="t1", event_type="hold",
                              line_refs=[{"line_no": 10}], reason="等料")
            record_task_event(ds, task_id="t1", event_type="release", reason="料齐")
        rows = ds.execute(
            "SELECT event_type, from_status, to_status FROM task_events "
            "WHERE task_id='t1' ORDER BY created_at").fetchall()
        assert [r[0] for r in rows] == ["hold", "release"]
        assert all(r[1] is None and r[2] is None for r in rows)


class TestRecordTransition:
    """配对不变量：一事件 + 一 WORKLOG"""

    def test_writes_one_event_and_one_worklog(self, ds):
        """TC-TEV-030: 每次迁移恰写 1 事件 + 1 WORKLOG，且 worklog.event_id 指回事件"""
        ensure_task_event_tables(ds)
        with ds.transaction():
            event_id, worklog_id = record_transition(
                ds, task_id="t1", from_status="pending", to_status="ready",
                actor="scheduler", actor_kind="system", reason="依赖满足")

        assert _count(ds, TASK_EVENT_TABLE) == 1
        assert _count(ds, WORKLOG_TABLE) == 1

        ev = ds.execute(
            "SELECT event_type, from_status, to_status, actor FROM task_events "
            "WHERE id=?", (event_id,)).fetchone()
        assert ev == ("status_changed", "pending", "ready", "scheduler")

        wl = ds.execute(
            "SELECT event_id, entry_type, summary, actor_kind FROM task_worklogs "
            "WHERE id=?", (worklog_id,)).fetchone()
        assert wl[0] == event_id
        assert wl[1] == "transition"
        assert wl[2] == "pending → ready"
        assert wl[3] == "system"

    def test_multiple_transitions_pairwise(self, ds):
        """TC-TEV-031: N 次迁移 = N 事件 + N WORKLOG（一一配对）"""
        ensure_task_event_tables(ds)
        chain = [("pending", "ready"), ("ready", "claimed"), ("claimed", "in_progress")]
        with ds.transaction():
            for frm, to in chain:
                record_transition(ds, task_id="t1", from_status=frm, to_status=to)

        assert _count(ds, TASK_EVENT_TABLE) == 3
        assert _count(ds, WORKLOG_TABLE) == 3

    def test_illegal_transition_rejected_and_not_recorded(self, ds):
        """TC-TEV-032: 非法迁移抛错且不落脏事件"""
        ensure_task_event_tables(ds)
        before = _count(ds, TASK_EVENT_TABLE)
        with pytest.raises(TaskTransitionError):
            with ds.transaction():
                record_transition(ds, task_id="t1", from_status="pending", to_status="done")
        assert _count(ds, TASK_EVENT_TABLE) == before


class TestAppendOnly:
    """append-only 纪律"""

    def test_no_update_or_delete_api(self):
        """TC-TEV-040: 模块不暴露 update / delete 写 API"""
        import meta.core.task_event_schema as mod

        public = [n for n in dir(mod) if not n.startswith("_")]
        forbidden = [n for n in public
                     if any(k in n.lower() for k in ("update", "delete", "remove"))]
        assert forbidden == [], f"事件账不应暴露可变 API：{forbidden}"