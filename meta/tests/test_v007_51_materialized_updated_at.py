"""Tests for v007_51 materialized updated_at columns (Phase 2, 2026-07-14)

覆盖场景：
1. 迁移脚本为 3 张表添加物化列 + Backfill
2. 物化列优先：audit_derived_fields 有物化值时跳过 v_audit_all 查询
3. virtual_sort 物化列路径（零 JOIN 开销）
4. enum_api _enrich_updated_at 物化列优先
5. batch_refresh_materialized_updated_at 批量刷新
6. 迁移幂等性
"""
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestV00751MaterializedColumns:
    """v007_51 物化 updated_at 列测试套件"""

    @pytest.fixture
    def db_path(self, tmp_path):
        """创建临时 DB，预设业务表 + audit_logs + v_audit_all VIEW"""
        p = str(tmp_path / "test_materialized.db")
        conn = sqlite3.connect(p)
        cur = conn.cursor()

        # enum_types 表（不含 updated_at，迁移后添加）
        cur.execute("""
            CREATE TABLE enum_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT, name TEXT, category TEXT, created_at TEXT
            )
        """)
        # enum_values 表
        cur.execute("""
            CREATE TABLE enum_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enum_type_id INTEGER, code TEXT, name TEXT, created_at TEXT
            )
        """)
        # users 表
        cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT, email TEXT, status TEXT, created_at TEXT
            )
        """)

        # audit_logs 表（含 v007_50 所需列）
        cur.execute("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT, object_id TEXT, action TEXT,
                field_name TEXT, old_value TEXT, new_value TEXT,
                extra_data TEXT,
                user_id INTEGER, user_name TEXT, ip_address TEXT, user_agent TEXT,
                created_at TEXT, trace_id TEXT, transaction_id TEXT, status TEXT,
                status_entered_at TEXT, retry_count INTEGER, error_message TEXT,
                agent_id TEXT, agent_session_id TEXT, tool_call_id TEXT, agent_reasoning TEXT,
                parent_object_type TEXT, parent_object_id INTEGER,
                log_category TEXT, log_level TEXT,
                action_kind TEXT, outcome TEXT, parent_action_id INTEGER,
                retention_until TEXT, created_at_epoch INTEGER
            )
        """)
        # audit_logs_archive 表
        cur.execute("""
            CREATE TABLE audit_logs_archive (
                id INTEGER PRIMARY KEY,
                archived_at TEXT NOT NULL,
                object_type TEXT, object_id TEXT, action TEXT,
                field_name TEXT, old_value TEXT, new_value TEXT,
                extra_data TEXT,
                user_id INTEGER, user_name TEXT, ip_address TEXT, user_agent TEXT,
                created_at TEXT, trace_id TEXT, transaction_id TEXT, status TEXT,
                status_entered_at TEXT, retry_count INTEGER, error_message TEXT,
                agent_id TEXT, agent_session_id TEXT, tool_call_id TEXT, agent_reasoning TEXT,
                parent_object_type TEXT, parent_object_id INTEGER,
                log_category TEXT, log_level TEXT,
                action_kind TEXT, outcome TEXT, parent_action_id INTEGER,
                retention_until TEXT
            )
        """)

        # 创建 v_audit_all VIEW（Phase 1 的产物）
        cur.execute("""
            CREATE VIEW v_audit_all AS
            SELECT id, object_type, object_id, action, field_name,
                   old_value, new_value, user_id, user_name, created_at,
                   created_at_epoch
            FROM audit_logs
            UNION ALL
            SELECT id, object_type, object_id, action, field_name,
                   old_value, new_value, user_id, user_name, created_at,
                   NULL as created_at_epoch
            FROM audit_logs_archive
        """)

        # 索引
        cur.execute(
            "CREATE INDEX idx_audit_logs_type_action_created "
            "ON audit_logs(object_type, action, created_at)"
        )

        # 插入测试数据
        # enum_types
        cur.execute("INSERT INTO enum_types(code, name, category, created_at) VALUES (?, ?, ?, ?)",
                    ("status", "Status", "system", "2026-01-01T00:00:00"))
        cur.execute("INSERT INTO enum_types(code, name, category, created_at) VALUES (?, ?, ?, ?)",
                    ("priority", "Priority", "system", "2026-02-01T00:00:00"))

        # users
        cur.execute("INSERT INTO users(username, email, status, created_at) VALUES (?, ?, ?, ?)",
                    ("admin", "admin@test.com", "active", "2026-01-01T00:00:00"))
        cur.execute("INSERT INTO users(username, email, status, created_at) VALUES (?, ?, ?, ?)",
                    ("user1", "user1@test.com", "active", "2026-03-01T00:00:00"))

        # audit_logs: UPDATE 记录
        cur.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at, created_at_epoch) "
            "VALUES (?, ?, ?, ?, ?)",
            ("enum_type", "1", "UPDATE", "2026-06-01T10:00:00", 1748772000000),
        )
        cur.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at, created_at_epoch) "
            "VALUES (?, ?, ?, ?, ?)",
            ("user", "1", "UPDATE", "2026-05-01T10:00:00", 1746103200000),
        )

        conn.commit()
        conn.close()
        return p

    def _run_migrate(self, db_path: str) -> bool:
        """运行 v007_51 迁移"""
        from meta.migrations.v007_51_add_updated_at_materialized import migrate
        return migrate(Path(db_path), skip_backup=True)

    # ────────────────────────────────────────────────────────────
    # 场景 1：迁移添加物化列 + Backfill
    # ────────────────────────────────────────────────────────────
    def test_migration_adds_columns_and_backfills(self, db_path):
        """场景 1：迁移后 3 张表都有 updated_at，且值正确回填"""
        assert self._run_migrate(db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # enum_types: id=1 有 UPDATE 审计 → updated_at = 2026-06-01T10:00:00
        row = conn.execute("SELECT updated_at FROM enum_types WHERE id = 1").fetchone()
        assert row["updated_at"] == "2026-06-01T10:00:00", f"enum_type 1 updated_at 应为审计 UPDATE 时间，实际 {row['updated_at']}"

        # enum_types: id=2 无 UPDATE 审计 → fallback 到 created_at
        row = conn.execute("SELECT updated_at FROM enum_types WHERE id = 2").fetchone()
        assert row["updated_at"] == "2026-02-01T00:00:00", f"enum_type 2 应 fallback 到 created_at"

        # users: id=1 有 UPDATE 审计
        row = conn.execute("SELECT updated_at FROM users WHERE id = 1").fetchone()
        assert row["updated_at"] == "2026-05-01T10:00:00"

        # users: id=2 无 UPDATE 审计 → fallback 到 created_at
        row = conn.execute("SELECT updated_at FROM users WHERE id = 2").fetchone()
        assert row["updated_at"] == "2026-03-01T00:00:00"

        conn.close()

    # ────────────────────────────────────────────────────────────
    # 场景 2：迁移幂等性
    # ────────────────────────────────────────────────────────────
    def test_migration_is_idempotent(self, db_path):
        """场景 2：重复执行迁移不报错"""
        assert self._run_migrate(db_path)
        assert self._run_migrate(db_path), "二次迁移应幂等成功"

    # ────────────────────────────────────────────────────────────
    # 场景 3：batch_refresh 批量刷新
    # ────────────────────────────────────────────────────────────
    def test_batch_refresh_updates_materialized_columns(self, db_path):
        """场景 3：审计写入后，batch_refresh 更新物化列"""
        assert self._run_migrate(db_path)

        conn = sqlite3.connect(db_path)

        # 模拟新的 UPDATE 审计日志写入
        conn.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at, created_at_epoch) "
            "VALUES (?, ?, ?, ?, ?)",
            ("enum_type", "2", "UPDATE", "2026-07-14T12:00:00", 1752504000000),
        )
        conn.commit()

        # 物化列还是旧值
        old_val = conn.execute("SELECT updated_at FROM enum_types WHERE id = 2").fetchone()[0]
        assert old_val == "2026-02-01T00:00:00", "刷新前应是 fallback 的 created_at"

        # 执行批量刷新
        from meta.migrations.v007_51_add_updated_at_materialized import batch_refresh_materialized_updated_at
        batch_refresh_materialized_updated_at(conn, [("enum_type", "2")])

        # 物化列应更新
        new_val = conn.execute("SELECT updated_at FROM enum_types WHERE id = 2").fetchone()[0]
        assert new_val == "2026-07-14T12:00:00", f"刷新后应为新审计时间，实际 {new_val}"

        conn.close()

    # ────────────────────────────────────────────────────────────
    # 场景 4：audit_derived_fields 物化列优先
    # ────────────────────────────────────────────────────────────
    def test_enrich_skips_query_when_materialized(self, db_path):
        """场景 4：enrich_audit_virtual_fields 通过 SSOT 读取物化列

        [V007.52 SSOT 重构后] 调用 get_updated_at() 走 SSOT 路径：
        - enum_types 是 audit_callback 策略 → 直接读 enum_types.updated_at
        - 物化列非 NULL → 返回物化值
        - 物化列 NULL → fallback 到 created_at
        """
        assert self._run_migrate(db_path)

        from meta.core.audit_derived_fields import enrich_audit_virtual_fields

        # 用 sqlite3 直连包装（V007.52 后 enrich 通过 SSOT 调用 ds.execute）
        import sqlite3
        class _SimpleDS:
            def __init__(self, path):
                self._conn = sqlite3.connect(path)
                self._conn.row_factory = sqlite3.Row
            def execute(self, sql, params=()):
                return self._conn.execute(sql, params)
        ds = _SimpleDS(db_path)

        # record[0]: 物化列 = 2026-06-01T10:00:00（已 backfill）
        # record[1]: 物化列 NULL（无 UPDATE 审计）→ fallback 到 created_at
        records = [
            {"id": 1, "name": "Status", "created_at": "2026-01-01T00:00:00",
             "updated_at": None},  # V007.52 重置，让函数重新填
            {"id": 2, "name": "Priority", "created_at": "2026-02-01T00:00:00",
             "updated_at": None},
        ]

        result = enrich_audit_virtual_fields(
            ds=ds, object_type="enum_type", records=records
        )

        # record[0]: 物化列有值 → 用物化值（2026-06-01T10:00:00）
        assert result[0]["updated_at"] == "2026-06-01T10:00:00",             f"record[0] 应读物化列，实际 {result[0]['updated_at']}"
        # record[1]: 无 UPDATE 审计 → fallback 到 created_at
        assert result[1]["updated_at"] == "2026-02-01T00:00:00",             f"record[1] 应 fallback 到 created_at，实际 {result[1]['updated_at']}"

    # ────────────────────────────────────────────────────────────
    # 场景 5：virtual_sort 物化列路径
    # ────────────────────────────────────────────────────────────
    def test_virtual_sort_uses_materialized_path(self):
        """场景 5：_build_audit_derived_order_join 返回物化列路径"""
        from meta.services.query.virtual_sort import _build_audit_derived_order_join

        # users 表在 _MATERIALIZED_UPDATED_AT_TABLES 中
        result = _build_audit_derived_order_join(
            table_name="users", obj_type="user",
            sort_field="updated_at", sort_direction="desc",
        )
        assert result is not None
        join_clause, order_alias, sort_dir = result
        assert join_clause == "", f"物化路径 join_clause 应为空，实际: {join_clause}"
        assert "users.updated_at" in order_alias
        assert sort_dir == "desc"

    def test_virtual_sort_falls_back_to_join_for_non_materialized(self):
        """场景 5b：非物化表仍走 LEFT JOIN"""
        from meta.services.query.virtual_sort import _build_audit_derived_order_join

        # products 不在 _MATERIALIZED_UPDATED_AT_TABLES 中
        result = _build_audit_derived_order_join(
            table_name="products", obj_type="product",
            sort_field="updated_at", sort_direction="asc",
        )
        assert result is not None
        join_clause, order_alias, sort_dir = result
        assert "LEFT JOIN" in join_clause, "非物化表应走 LEFT JOIN"
        assert "v_audit_all" in join_clause

    # ────────────────────────────────────────────────────────────
    # 场景 6：enum_api _enrich_updated_at 物化列优先
    # ────────────────────────────────────────────────────────────
    def test_enum_enrich_skips_query_when_materialized(self, db_path):
        """场景 6：_enrich_updated_at 有物化值时跳过 v_audit_all"""
        assert self._run_migrate(db_path)

        # 直接导入 enum_api 的 _enrich_updated_at
        # 用 mock DataSource（不需要真正连接 DB）
        from meta.api import enum_api as enum_mod

        mock_ds = MagicMock()
        enum_mod.init_enum_services(data_source=mock_ds)

        records = [
            {"id": 1, "name": "Status", "created_at": "2026-01-01T00:00:00",
             "updated_at": "2026-06-01T10:00:00"},  # 已有物化值
        ]

        # 调用 _enrich_updated_at
        enum_mod._enrich_updated_at(records, "enum_type")

        # 已有物化值不应被覆盖
        assert records[0]["updated_at"] == "2026-06-01T10:00:00"
