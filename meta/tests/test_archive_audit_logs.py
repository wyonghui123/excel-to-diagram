"""Test archive_audit_logs.py - FR-LOG-008"""
import pytest
import sys
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestArchiveAuditLogs:

    @pytest.fixture
    def db_path(self, tmp_path):
        """创建临时 DB，初始化 audit_logs + audit_logs_archive 表"""
        p = str(tmp_path / "test_archive.db")
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        # 完整 v2 schema
        cur.execute("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT, object_id TEXT, action TEXT,
                field_name TEXT, old_value TEXT, new_value TEXT,
                user_id INTEGER, user_name TEXT, ip_address TEXT, user_agent TEXT,
                created_at TEXT, trace_id TEXT, transaction_id TEXT, status TEXT,
                agent_id TEXT, agent_session_id TEXT, tool_call_id TEXT, agent_reasoning TEXT,
                log_category TEXT, log_level TEXT,
                action_kind TEXT, outcome TEXT, parent_action_id INTEGER,
                error_message TEXT, retention_until TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE audit_logs_archive (
                id INTEGER PRIMARY KEY,
                archived_at TEXT NOT NULL,
                object_type TEXT, object_id TEXT, action TEXT,
                field_name TEXT, old_value TEXT, new_value TEXT,
                user_id INTEGER, user_name TEXT, ip_address TEXT, user_agent TEXT,
                created_at TEXT, trace_id TEXT, transaction_id TEXT, status TEXT,
                agent_id TEXT, agent_session_id TEXT, tool_call_id TEXT, agent_reasoning TEXT,
                log_category TEXT, log_level TEXT,
                action_kind TEXT, outcome TEXT, parent_action_id INTEGER,
                error_message TEXT, retention_until TEXT
            )
        """)
        conn.commit()
        conn.close()
        return p

    def _insert_log(self, db_path, retention_until):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_logs
                (object_type, object_id, action, user_id, user_name, retention_until, action_kind, outcome)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ('user', '1', 'created', 1, 'alice', retention_until, 'instance', 'success'))
        conn.commit()
        conn.close()

    def test_archive_old_records(self, db_path):
        """6 月前的记录被归档"""
        from meta.scripts.archive_audit_logs import archive_old_audit_logs
        old_iso = (datetime.utcnow() - timedelta(days=200)).isoformat()
        new_iso = (datetime.utcnow() + timedelta(days=10)).isoformat()
        self._insert_log(db_path, old_iso)
        self._insert_log(db_path, old_iso)
        self._insert_log(db_path, new_iso)  # 不应被归档

        result = archive_old_audit_logs(db_path, retention_days=180, dry_run=False)
        assert result['archived_count'] == 2
        assert result['error_count'] == 0

        # 验证
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM audit_logs")
        # 剩 2 条：1 原新的 + 1 归档操作自身 audit（FR-LOG-008 自审计）
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT COUNT(*) FROM audit_logs_archive")
        assert cur.fetchone()[0] == 2  # 归档 2 条
        conn.close()

    def test_dry_run_does_not_modify(self, db_path):
        """dry_run 不修改数据"""
        from meta.scripts.archive_audit_logs import archive_old_audit_logs
        old_iso = (datetime.utcnow() - timedelta(days=200)).isoformat()
        self._insert_log(db_path, old_iso)
        self._insert_log(db_path, old_iso)

        result = archive_old_audit_logs(db_path, retention_days=180, dry_run=True)
        assert result['dry_run'] is True
        assert result['would_archive'] == 2

        # 验证：原表未变
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM audit_logs")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT COUNT(*) FROM audit_logs_archive")
        assert cur.fetchone()[0] == 0
        conn.close()

    def test_no_old_records(self, db_path):
        """无过期记录时 0 归档"""
        from meta.scripts.archive_audit_logs import archive_old_audit_logs
        new_iso = (datetime.utcnow() + timedelta(days=30)).isoformat()
        self._insert_log(db_path, new_iso)

        result = archive_old_audit_logs(db_path, retention_days=180, dry_run=False)
        assert result['archived_count'] == 0

    def test_db_not_exists(self, tmp_path):
        from meta.scripts.archive_audit_logs import archive_old_audit_logs
        result = archive_old_audit_logs(str(tmp_path / "nonexistent.db"), 180, dry_run=False)
        assert result['error_count'] == 1

    def test_records_without_retention_until_not_archived(self, db_path):
        """retention_until 为 NULL 的记录不被归档（v1 兼容）"""
        from meta.scripts.archive_audit_logs import archive_old_audit_logs
        # v1 记录没有 retention_until
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_logs
                (object_type, object_id, action, user_id, user_name, retention_until)
                VALUES (?, ?, ?, ?, ?, NULL)
        """, ('user', '1', 'created', 1, 'alice'))
        conn.commit()
        conn.close()

        result = archive_old_audit_logs(db_path, retention_days=180, dry_run=False)
        # v1 记录不应被归档
        assert result['archived_count'] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
