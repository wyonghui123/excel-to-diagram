"""Test archive_change_events.py - T7.1 归档策略

DML 统一走 factories/_raw_sql_bridge（避免 conftest raw-SQL 守卫整体 skip）。
"""
import pytest
import sys
import os
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.tests.factories import _raw_sql_bridge as bridge


CHANGE_EVENT_COLS = """
    object_type TEXT NOT NULL, object_id INTEGER NOT NULL,
    event_type TEXT NOT NULL, changed_fields TEXT, old_values TEXT, new_values TEXT,
    payload TEXT, channels TEXT, status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
    delivered_at TEXT, audit_log_id INTEGER, retention_until TEXT
"""


def _create_change_events_table(cur, table):
    cur.execute("CREATE TABLE {0} (id INTEGER PRIMARY KEY AUTOINCREMENT, {1})".format(
        table, CHANGE_EVENT_COLS))


class TestArchiveChangeEvents:

    @pytest.fixture
    def db_path(self, tmp_path):
        p = str(tmp_path / "test_change_events.db")
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        _create_change_events_table(cur, 'change_events')
        cur.execute("""
            CREATE TABLE change_events_archive (
                id INTEGER PRIMARY KEY,
                archived_at TEXT NOT NULL,
                {0}
            )
        """.format(CHANGE_EVENT_COLS))
        cur.execute("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT, object_id TEXT, action TEXT,
                field_name TEXT, old_value TEXT, new_value TEXT,
                user_id INTEGER, user_name TEXT, ip_address TEXT, user_agent TEXT,
                created_at TEXT, action_kind TEXT, outcome TEXT, error_message TEXT,
                retention_until TEXT, log_category TEXT, log_level TEXT, status TEXT
            )
        """)
        conn.commit()
        conn.close()
        return p

    def _insert_event(self, db_path, retention_until, object_id='1'):
        conn = sqlite3.connect(db_path)
        bridge.insert(
            conn, 'change_events',
            object_type='product', object_id=object_id, event_type='update',
            created_at=datetime.now().isoformat(),
            retention_until=retention_until,
        )
        conn.commit()
        conn.close()

    def test_archives_only_expired(self, db_path):
        """只归档 retention_until < NOW() 的事件"""
        from meta.scripts.archive_change_events import archive_old_change_events
        expired = (datetime.now() - timedelta(days=1)).isoformat()
        future = (datetime.now() + timedelta(days=30)).isoformat()
        self._insert_event(db_path, expired, '1')
        self._insert_event(db_path, expired, '2')
        self._insert_event(db_path, future, '3')
        self._insert_event(db_path, None, '4')  # 无保留期 → 不动

        result = archive_old_change_events(db_path, dry_run=False)
        assert result['archived_count'] == 2
        assert result['error_count'] == 0

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM change_events")
        assert cur.fetchone()[0] == 2  # future + NULL
        cur.execute("SELECT COUNT(*) FROM change_events_archive")
        assert cur.fetchone()[0] == 2
        conn.close()

    def test_dry_run_does_not_modify(self, db_path):
        from meta.scripts.archive_change_events import archive_old_change_events
        expired = (datetime.now() - timedelta(days=1)).isoformat()
        self._insert_event(db_path, expired)

        result = archive_old_change_events(db_path, dry_run=True)
        assert result['would_archive'] == 1

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM change_events")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM change_events_archive")
        assert cur.fetchone()[0] == 0
        conn.close()

    def test_copy_failure_keeps_source_rows(self, db_path):
        """archive 写入失败时，源表记录不得被删除（防丢数据）"""
        from meta.scripts.archive_change_events import archive_old_change_events
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("DROP TABLE change_events_archive")
        cur.execute("CREATE TABLE change_events_archive (id INTEGER PRIMARY KEY, archived_at TEXT NOT NULL)")
        conn.commit()
        conn.close()

        expired = (datetime.now() - timedelta(days=1)).isoformat()
        self._insert_event(db_path, expired, '1')
        self._insert_event(db_path, expired, '2')

        result = archive_old_change_events(db_path, dry_run=False)
        assert result['archived_count'] == 0
        assert result['error_count'] == 2

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM change_events")
        assert cur.fetchone()[0] == 2
        conn.close()

    def test_batch_over_500_archives_all(self, db_path):
        """超过一个批次（500）时不得跳行（keyset 分页）"""
        from meta.scripts.archive_change_events import archive_old_change_events
        expired = (datetime.now() - timedelta(days=1)).isoformat()
        conn = sqlite3.connect(db_path)
        for i in range(600):
            bridge.insert(
                conn, 'change_events',
                object_type='product', object_id=str(i), event_type='update',
                created_at=datetime.now().isoformat(), retention_until=expired,
            )
        conn.commit()
        conn.close()

        result = archive_old_change_events(db_path, dry_run=False)
        assert result['archived_count'] == 600
        assert result['error_count'] == 0

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM change_events_archive")
        assert cur.fetchone()[0] == 600
        conn.close()

    def test_archive_action_logged_to_audit(self, db_path):
        """归档操作自身写 audit（system action）"""
        from meta.scripts.archive_change_events import archive_old_change_events
        expired = (datetime.now() - timedelta(days=1)).isoformat()
        self._insert_event(db_path, expired)

        archive_old_change_events(db_path, dry_run=False)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT action, user_name FROM audit_logs")
        row = cur.fetchone()
        assert row == ('archive_old_events', 'system:cron')
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
