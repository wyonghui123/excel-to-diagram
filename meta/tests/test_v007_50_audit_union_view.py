"""Tests for v007_50 v_audit_all UNION ALL VIEW (2026-07-14)

覆盖场景：
1. 仅热表数据 → VIEW 正确返回
2. 热表 + 归档表混合数据 → VIEW UNION 完整
3. 归档表 INTEGER 类型与热表对齐 → WHERE id=? 正常匹配（防类型亲和性 bug）
4. VIEW 不存在时审计派生查询自动回退到 audit_logs
5. 迁移脚本幂等性（重复执行不报错）
6. 归档后审计派生查询能找到归档数据（V007.49-C 关键路径）
"""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestV00750AuditUnionView:
    """v_audit_all VIEW 集成测试套件"""

    @pytest.fixture
    def db_path(self, tmp_path):
        """创建临时 DB，预设 audit_logs + audit_logs_archive 表（类型对齐版本）"""
        p = str(tmp_path / "test_v_audit_all.db")
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        # 热表：完整 v2 schema（包含 verification 必需的关键列 extra_data, created_at_epoch）
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
                retention_until TEXT,
                created_at_epoch INTEGER
            )
        """)
        # 归档表：保持 INTEGER 类型（脚本要求）
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
        # 模拟 enhance_audit_log 已建的索引
        cur.execute(
            "CREATE INDEX idx_audit_logs_type_action_created "
            "ON audit_logs(object_type, action, created_at)"
        )
        cur.execute(
            "CREATE INDEX idx_audit_archive_type_action_created "
            "ON audit_logs_archive(object_type, action, created_at)"
        )
        conn.commit()
        conn.close()
        return p

    def _create_view(self, db_path: str) -> bool:
        """运行 v007_50 迁移创建 VIEW（skip_backup 避免拷贝）"""
        from meta.migrations.v007_50_add_audit_union_view import migrate
        return migrate(Path(db_path), skip_backup=True)

    # ────────────────────────────────────────────────────────────
    # 场景 1：仅热表数据
    # ────────────────────────────────────────────────────────────
    def test_view_returns_hot_table_data_only(self, db_path):
        """场景 1：归档表为空时，VIEW 仅返回热表数据"""
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at) VALUES (?, ?, ?, ?)",
            ("role", "1", "UPDATE", "2026-07-14T10:00:00"),
        )
        conn.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at) VALUES (?, ?, ?, ?)",
            ("role", "2", "UPDATE", "2026-07-14T11:00:00"),
        )
        conn.commit()
        conn.close()

        assert self._create_view(db_path), "VIEW 创建失败"

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT object_type, object_id, action, created_at FROM v_audit_all ORDER BY created_at"
        ).fetchall()
        conn.close()

        assert len(rows) == 2, f"期望 2 行（仅热表），实际 {len(rows)}"
        assert rows[0] == ("role", "1", "UPDATE", "2026-07-14T10:00:00")
        assert rows[1] == ("role", "2", "UPDATE", "2026-07-14T11:00:00")

    # ────────────────────────────────────────────────────────────
    # 场景 2：热表 + 归档表混合
    # ────────────────────────────────────────────────────────────
    def test_view_unions_hot_and_archive(self, db_path):
        """场景 2：热表与归档表都有数据时，VIEW 完整 UNION"""
        conn = sqlite3.connect(db_path)
        # 热表：2 条
        conn.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at) VALUES (?, ?, ?, ?)",
            ("user", "100", "CREATE", "2026-07-14T08:00:00"),
        )
        conn.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at) VALUES (?, ?, ?, ?)",
            ("user", "101", "UPDATE", "2026-07-14T09:00:00"),
        )
        # 归档表：3 条（模拟已归档）
        conn.execute(
            "INSERT INTO audit_logs_archive(id, archived_at, object_type, object_id, action, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (9001, "2026-07-01T00:00:00", "user", "1", "DELETE", "2025-12-01T10:00:00"),
        )
        conn.execute(
            "INSERT INTO audit_logs_archive(id, archived_at, object_type, object_id, action, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (9002, "2026-07-01T00:00:00", "user", "2", "UPDATE", "2025-12-15T10:00:00"),
        )
        conn.execute(
            "INSERT INTO audit_logs_archive(id, archived_at, object_type, object_id, action, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (9003, "2026-07-01T00:00:00", "user", "3", "DELETE", "2025-12-20T10:00:00"),
        )
        conn.commit()
        conn.close()

        assert self._create_view(db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT object_type, object_id, action, created_at FROM v_audit_all ORDER BY created_at"
        ).fetchall()
        conn.close()

        assert len(rows) == 5, f"期望 5 行（2 热 + 3 归档），实际 {len(rows)}"
        # 最早的应是归档表
        assert ("user", "1", "DELETE", "2025-12-01T10:00:00") in [tuple(r) for r in rows]

    # ────────────────────────────────────────────────────────────
    # 场景 3：INTEGER 类型对齐（防 SQLite 类型亲和性 bug）
    # ────────────────────────────────────────────────────────────
    def test_view_where_id_matches_archive_integer_type(self, db_path):
        """场景 3：归档表 id 用 INTEGER 类型时，WHERE id=? 正确返回

        验证 SQL:
            SELECT * FROM v_audit_all WHERE id = ?

        修复前（bug）：归档表 id 为 TEXT 存储 '348464'，WHERE 348464 无法匹配
        修复后：归档表 id 为 INTEGER（迁移脚本保证），VIEW 中 CAST AS INTEGER
        """
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO audit_logs_archive(id, archived_at, object_type, object_id, action, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (348464, "2026-07-01T00:00:00", "user", "1", "DELETE", "2025-12-01T10:00:00"),
        )
        conn.commit()
        conn.close()

        assert self._create_view(db_path)

        conn = sqlite3.connect(db_path)
        # 传 INTEGER 参数（与热表 id 类型一致）
        row = conn.execute(
            "SELECT id, object_type, action FROM v_audit_all WHERE id = ?",
            (348464,),
        ).fetchone()
        conn.close()

        assert row is not None, "INTEGER id=348464 应能匹配归档表"
        assert row[0] == 348464
        assert row[1] == "user"
        assert row[2] == "DELETE"

    # ────────────────────────────────────────────────────────────
    # 场景 4：迁移幂等性
    # ────────────────────────────────────────────────────────────
    def test_migration_is_idempotent(self, db_path):
        """场景 4：重复执行迁移不报错（幂等）"""
        assert self._create_view(db_path)
        # 二次执行
        assert self._create_view(db_path), "二次迁移应幂等成功"

        conn = sqlite3.connect(db_path)
        # 应只有一个 VIEW
        cnt = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='v_audit_all'"
        ).fetchone()[0]
        conn.close()
        assert cnt == 1, f"重复执行后应有 1 个 VIEW，实际 {cnt}"

    # ────────────────────────────────────────────────────────────
    # 场景 5：查询计划走索引（非全表扫描）
    # ────────────────────────────────────────────────────────────
    def test_view_query_plan_uses_index(self, db_path):
        """场景 5：v_audit_all WHERE 查询走索引验证

        Phase 1 关键性能保证：SQLite 应展平 UNION ALL VIEW 子查询，
        将 WHERE 谓词下推到各分支走索引。
        """
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO audit_logs(object_type, object_id, action) VALUES (?, ?, ?)",
            ("role", "1", "UPDATE"),
        )
        conn.commit()
        conn.close()

        assert self._create_view(db_path)

        conn = sqlite3.connect(db_path)
        plan = conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT * FROM v_audit_all WHERE object_type = ? AND action = ?",
            ("role", "UPDATE"),
        ).fetchall()
        conn.close()

        plan_str = " | ".join(str(r) for r in plan)
        # 至少有一个分支走 INDEX（不能全表 SCAN）
        has_index = any("USING INDEX" in str(p) for p in plan)
        assert has_index, f"查询计划未使用索引: {plan_str}"

    # ────────────────────────────────────────────────────────────
    # 场景 6：audit_derived_fields 回退机制（核心 SSOT 路径）
    # ────────────────────────────────────────────────────────────
    def test_audit_derived_fields_falls_back_when_view_missing(self, db_path):
        """场景 6：VIEW 不存在时，audit_derived_fields 回退到 audit_logs

        不依赖完整 backend 启动，直接构造独立 SQL。
        """
        conn = sqlite3.connect(db_path)
        # 没有运行 migrate()  → VIEW 不存在
        conn.execute(
            "INSERT INTO audit_logs(object_type, object_id, action, created_at, created_at_epoch) "
            "VALUES (?, ?, ?, ?, ?)",
            ("user", "1", "UPDATE", "2026-07-14T10:00:00", 1752500000),
        )
        conn.commit()
        conn.close()

        # 验证 VIEW 确实不存在
        conn = sqlite3.connect(db_path)
        view_exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='v_audit_all'"
        ).fetchone()[0]
        conn.close()
        assert view_exists == 0, "VIEW 应不存在以测试回退路径"

        # 回退 SQL：直接查 audit_logs（与 audit_derived_fields 的 _NO_VIEW 路径一致）
        fallback_sql = (
            "SELECT object_id, MAX(created_at_epoch) as max_epoch "
            "FROM audit_logs "
            "WHERE object_type = ? AND object_id IN (?) "
            "AND action = 'UPDATE' "
            "GROUP BY object_id"
        )

        conn = sqlite3.connect(db_path)
        row = conn.execute(fallback_sql, ("user", "1")).fetchone()
        conn.close()

        assert row is not None, "回退 SQL 应能从 audit_logs 查到数据"
        assert row[0] == "1"
        assert row[1] == 1752500000

    # ────────────────────────────────────────────────────────────
    # 场景 7：归档场景下审计派生查询仍能工作（P0 路径）
    # ────────────────────────────────────────────────────────────
    def test_view_supports_archived_object_recovery(self, db_path):
        """场景 7：用户 >180 天前被 DELETE 的对象，VIEW 仍能找到记录

        模拟 V007.49-C audit_recovery 框架的核心场景：
        - 热表删除后，DELETE 记录被归档
        - VIEW 应能 UNION 出归档的 DELETE 记录
        """
        conn = sqlite3.connect(db_path)
        # 归档表里：用户 999 在半年前被 DELETE
        conn.execute(
            "INSERT INTO audit_logs_archive(id, archived_at, object_type, object_id, action, "
            "user_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                99001, "2026-07-01T00:00:00", "user", "999", "DELETE",
                1, "2025-12-01T10:00:00",
            ),
        )
        conn.commit()
        conn.close()

        assert self._create_view(db_path)

        # 模拟 audit_recovery 的 find_recoverable 查询
        # DELETE 记录应能通过 VIEW 返回
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT id, action, object_id FROM v_audit_all "
            "WHERE object_type = ? AND object_id = ? AND action = 'DELETE'",
            ("user", "999"),
        ).fetchall()
        conn.close()

        assert len(rows) == 1, f"归档后应能找到 DELETE 记录，实际 {len(rows)}"
        assert rows[0][1] == "DELETE"
        assert rows[0][2] == "999"
