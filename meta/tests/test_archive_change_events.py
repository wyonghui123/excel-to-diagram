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
    status_reason TEXT, idempotency_key TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
    delivered_at TEXT, audit_log_id INTEGER, retention_until TEXT
"""

#: 历史库归档表结构（v228 建表，缺后续新增的 status_reason / idempotency_key）
LEGACY_ARCHIVE_COLS = """
    object_type TEXT NOT NULL, object_id INTEGER NOT NULL,
    event_type TEXT NOT NULL, changed_fields TEXT, old_values TEXT, new_values TEXT,
    payload TEXT, channels TEXT, status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
    delivered_at TEXT, audit_log_id INTEGER, retention_until TEXT
"""


_ARCHIVE_DDL = """
    CREATE TABLE change_events_archive (
        id INTEGER PRIMARY KEY,
        archived_at TEXT NOT NULL,
        {0}
    )
""".format(CHANGE_EVENT_COLS)

_LEGACY_ARCHIVE_DDL = """
    CREATE TABLE change_events_archive (
        id INTEGER PRIMARY KEY,
        archived_at TEXT NOT NULL,
        {0}
    )
""".format(LEGACY_ARCHIVE_COLS)

_INBOX_DDL = """
    CREATE TABLE notification_inbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER, subscription_id INTEGER, user_id INTEGER,
        title TEXT, body TEXT, read_at TEXT, created_at TEXT,
        retention_until TEXT
    )
"""

_DELIVERIES_DDL = """
    CREATE TABLE notification_deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER, subscription_id INTEGER, user_id INTEGER,
        channel TEXT, status TEXT, attempts INTEGER,
        last_error TEXT, next_retry_at TEXT, created_at TEXT
    )
"""

_AUDIT_LOGS_DDL = """
    CREATE TABLE audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_type TEXT, object_id TEXT, action TEXT,
        field_name TEXT, old_value TEXT, new_value TEXT,
        user_id INTEGER, user_name TEXT, ip_address TEXT, user_agent TEXT,
        created_at TEXT, action_kind TEXT, outcome TEXT, error_message TEXT,
        retention_until TEXT, log_category TEXT, log_level TEXT, status TEXT
    )
"""

_BROKEN_ARCHIVE_DDL = (
    "CREATE TABLE change_events_archive (id INTEGER PRIMARY KEY, archived_at TEXT NOT NULL)"
)

#: 用触发器模拟归档表不可写（自愈补列后仍无法插入）
_BROKEN_ARCHIVE_TRIGGER = (
    "CREATE TRIGGER fail_archive_insert BEFORE INSERT ON change_events_archive "
    "BEGIN SELECT RAISE(ABORT, 'simulated archive failure'); END"
)

_DROP_ARCHIVE_SQL = "DROP TABLE change_events_archive"


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
        cur.execute(_ARCHIVE_DDL)
        cur.execute(_INBOX_DDL)
        cur.execute(_DELIVERIES_DDL)
        cur.execute(_AUDIT_LOGS_DDL)
        conn.commit()
        conn.close()
        return p

    def _insert_event(self, db_path, retention_until, object_id='1', **extra):
        conn = sqlite3.connect(db_path)
        bridge.insert(
            conn, 'change_events',
            object_type='product', object_id=object_id, event_type='update',
            created_at=datetime.now().isoformat(),
            retention_until=retention_until,
            **extra,
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
        """archive 写入失败时，源表记录不得被删除（防丢数据）

        归档表结构会先自愈补列，因此用触发器让插入真正失败。
        """
        from meta.scripts.archive_change_events import archive_old_change_events
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(_DROP_ARCHIVE_SQL)
        cur.execute(_BROKEN_ARCHIVE_DDL)
        cur.execute(_BROKEN_ARCHIVE_TRIGGER)
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

    def test_legacy_archive_table_gets_missing_columns(self, db_path):
        """旧库归档表缺 status_reason / idempotency_key 时自动补列且不丢值"""
        from meta.scripts.archive_change_events import archive_old_change_events
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(_DROP_ARCHIVE_SQL)
        cur.execute(_LEGACY_ARCHIVE_DDL)
        conn.commit()
        conn.close()

        expired = (datetime.now() - timedelta(days=1)).isoformat()
        self._insert_event(
            db_path, expired, '1',
            status='failed', status_reason='retry_exhausted',
            idempotency_key='evt-1',
        )

        result = archive_old_change_events(db_path, dry_run=False)
        assert result['archived_count'] == 1
        assert result['error_count'] == 0

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT status_reason, idempotency_key, archived_at "
            "FROM change_events_archive WHERE id=1"
        )
        status_reason, idempotency_key, archived_at = cur.fetchone()
        conn.close()
        assert status_reason == 'retry_exhausted'
        assert idempotency_key == 'evt-1'
        assert archived_at

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

    def test_archives_also_cleans_inbox_and_deliveries(self, db_path):
        """归档过期事件时，同步清理对应收件箱 / 投递行（P1-d A12）"""
        from meta.scripts.archive_change_events import archive_old_change_events
        expired = (datetime.now() - timedelta(days=1)).isoformat()
        future = (datetime.now() + timedelta(days=30)).isoformat()
        self._insert_event(db_path, expired, '1')
        self._insert_event(db_path, expired, '2')
        self._insert_event(db_path, future, '3')

        conn = sqlite3.connect(db_path)
        for event_id in (1, 2, 3):
            bridge.insert(
                conn, 'notification_inbox',
                event_id=event_id, user_id=7, title='t',
                created_at=datetime.now().isoformat(),
                retention_until=expired if event_id < 3 else future,
            )
        for event_id in (1, 2):
            bridge.insert(
                conn, 'notification_deliveries',
                event_id=event_id, user_id=7, channel='in_app',
                status='delivered', attempts=1,
                created_at=datetime.now().isoformat(),
            )
        conn.commit()
        conn.close()

        result = archive_old_change_events(db_path, dry_run=False)
        assert result['archived_count'] == 2
        assert result['inbox_deleted'] == 2
        assert result['deliveries_deleted'] == 2

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notification_inbox")
        assert cur.fetchone()[0] == 1  # 未过期事件的消息保留
        cur.execute("SELECT COUNT(*) FROM notification_deliveries")
        assert cur.fetchone()[0] == 0
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
