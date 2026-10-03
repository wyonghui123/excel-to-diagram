import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks 等）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - 写权单通道守卫（B4）
测试 meta.core.task_write_guard（§12.1 B4 / 综合 §6.3 边界三条之二）

覆盖目标：
  1. 任务域自有表 DML 放行
  2. 业务对象表 / 边表 DML 拒绝（fail-closed）
  3. 读（SELECT）不设限
  4. 无作用域时守卫失效（非任务来源的写不归本守卫管）
  5. DML 目标识别（INSERT OR IGNORE / 引号 / 多语句）
  6. 白名单覆盖任务域表常量
"""

from meta.core.task_write_guard import (
    TASK_OWNED_TABLES,
    GuardedDataSource,
    WriteChannelViolation,
    assert_task_write_allowed,
    extract_dml_target,
    task_write_scope,
)


@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（A1/A3/A6/A7 底座；含 Task2 端到端所需账表）。"""
    from meta.core.datasource import get_data_source
    from meta.core.task_async import ensure_async_tables
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "b4.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
        ensure_async_tables(source)
    yield source


# ─────────────────────────────────────────────────────────────────────────────
# DML 目标识别
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractDmlTarget:
    """TC-B4-001~006 DML 目标识别"""

    def test_TC_B4_001_普通写法(self):
        assert extract_dml_target("INSERT INTO tasks (id) VALUES (?)") == "tasks"
        assert extract_dml_target("UPDATE tasks SET status = ? WHERE id = ?") == "tasks"
        assert extract_dml_target("DELETE FROM task_events WHERE id = ?") == "task_events"

    def test_TC_B4_002_insert_or_ignore(self):
        assert extract_dml_target("INSERT OR IGNORE INTO task_idempotency (k) VALUES (?)") \
            == "task_idempotency"
        assert extract_dml_target("INSERT OR REPLACE INTO doc_flow_edges (id) VALUES (?)") \
            == "doc_flow_edges"

    def test_TC_B4_003_引号包裹(self):
        assert extract_dml_target('UPDATE "sales_order" SET status = ?') == "sales_order"
        assert extract_dml_target("[purchase_order] 不用中括号") is None

    def test_TC_B4_004_读语句无目标(self):
        assert extract_dml_target("SELECT * FROM sales_order") is None
        assert extract_dml_target("PRAGMA foreign_keys") is None

    def test_TC_B4_005_多语句逐段检查(self):
        sql = "SELECT 1; UPDATE sales_order SET status = 'x'"
        assert extract_dml_target(sql) == "sales_order"

    def test_TC_B4_006_大小写不敏感(self):
        assert extract_dml_target("update TASKS set x = 1") == "tasks"


# ─────────────────────────────────────────────────────────────────────────────
# 白名单判定
# ─────────────────────────────────────────────────────────────────────────────

class TestAssertAllowed:
    """TC-B4-010~014 白名单判定"""

    def test_TC_B4_010_任务域表放行(self):
        for sql in (
            "INSERT INTO tasks (id) VALUES (?)",
            "UPDATE task_events SET to_status = ?",
            "INSERT OR IGNORE INTO task_idempotency (k) VALUES (?)",
            "UPDATE task_async_waits SET wait_status = 'completed'",
            "DELETE FROM task_worklogs WHERE id = ?",
        ):
            assert_task_write_allowed(sql)      # 不抛即通过

    def test_TC_B4_011_业务对象表拒绝(self):
        with pytest.raises(WriteChannelViolation):
            assert_task_write_allowed("UPDATE sales_order SET status = 'approved'")

    def test_TC_B4_012_边表拒绝(self):
        with pytest.raises(WriteChannelViolation):
            assert_task_write_allowed("INSERT INTO doc_flow_edges (id) VALUES (?)")

    def test_TC_B4_013_读不限(self):
        assert_task_write_allowed("SELECT * FROM sales_order")

    def test_TC_B4_014_违规消息含目标表(self):
        with pytest.raises(WriteChannelViolation) as ei:
            assert_task_write_allowed("UPDATE sales_order SET status = 'x'")
        assert "sales_order" in str(ei.value)


# ─────────────────────────────────────────────────────────────────────────────
# 作用域 + 代理
# ─────────────────────────────────────────────────────────────────────────────

class TestScope:
    """TC-B4-020~025 作用域与代理行为"""

    def test_TC_B4_020_作用域内任务表写放行(self, ds):
        with task_write_scope(ds) as guarded:
            guarded.execute(
                "INSERT INTO tasks (id, title, type, status, executor_type, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("T-1", "t", "automation", "ready", "system", "2026-10-04", "2026-10-04"),
            )
        assert ds.execute("SELECT COUNT(*) FROM tasks").fetchall()[0][0] == 1

    def test_TC_B4_021_作用域内业务表写拒绝(self, ds):
        with pytest.raises(WriteChannelViolation):
            with task_write_scope(ds) as guarded:
                guarded.execute("UPDATE sales_order SET status = 'x'")

    def test_TC_B4_022_读透传(self, ds):
        with task_write_scope(ds) as guarded:
            assert guarded.execute("SELECT COUNT(*) FROM tasks").fetchall()[0][0] == 0
            assert guarded.query("SELECT 1") is not None

    def test_TC_B4_023_作用域外不拦(self, ds):
        # 非任务来源（无作用域）的写不归本守卫管
        ds.execute("CREATE TABLE IF NOT EXISTS free_table (id INTEGER)")
        ds.execute("INSERT INTO free_table (id) VALUES (1)")   # 不抛

    def test_TC_B4_024_代理透传未知属性(self, ds):
        with task_write_scope(ds) as guarded:
            assert isinstance(guarded, GuardedDataSource)
            assert guarded.transaction is not None       # 透传到底层 ds

    def test_TC_B4_025_白名单覆盖任务域表常量(self):
        from meta.core import task_async, task_event_schema, task_idempotency, task_sla
        for name in (
            task_async.WAIT_TABLE, task_async.RECEIPT_TABLE,
            task_event_schema.TASK_EVENT_TABLE, task_event_schema.WORKLOG_TABLE,
            task_idempotency.TABLE, task_sla.SLA_TABLE,
        ):
            assert name in TASK_OWNED_TABLES, name