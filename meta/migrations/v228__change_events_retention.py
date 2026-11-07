# -*- coding: utf-8 -*-
"""v228 - change_events 保留期字段与归档表

背景:
  change_events 是事件溯源与变更通知的事实表，此前永久在线，没有任何清理机制
  （docs/CHANGE_EVENT_RETENTION.md 建议 1 年分层，但未落地）。
  T7.1 归档策略确认：在线 365 天，过期事件搬到 change_events_archive。

范围:
  1. ALTER change_events ADD COLUMN retention_until（保留截止时间）
  2. 回填：retention_until = created_at + 365 天（只填 NULL，可重复执行）
  3. 索引 idx_change_events_retention_until
  4. 新建 change_events_archive（结构同源表 + archived_at）

幂等:
  列存在性守卫 / CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS /
  回填只处理 retention_until IS NULL。
"""

from __future__ import annotations

import os
import sqlite3

MIGRATION_NAME = 'v228__change_events_retention'

TABLE = 'change_events'
ARCHIVE_TABLE = 'change_events_archive'
INDEX_NAME = 'idx_change_events_retention_until'
RETENTION_DAYS = 365

ARCHIVE_DDL = """
CREATE TABLE IF NOT EXISTS change_events_archive (
    id INTEGER PRIMARY KEY,
    archived_at TEXT NOT NULL,
    object_type VARCHAR(100) NOT NULL,
    object_id INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    changed_fields TEXT,
    old_values TEXT,
    new_values TEXT,
    payload TEXT,
    channels TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    delivered_at TIMESTAMP,
    audit_log_id INTEGER,
    retention_until TIMESTAMP
)
"""


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _index_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn, table):
    return {r[1] for r in conn.execute('PRAGMA table_info(%s)' % table).fetchall()}


def migrate(db_path, skip_backup=False):
    print('[v228] change_events 保留期字段与归档表')
    if hasattr(db_path, 'exists') and callable(getattr(db_path, 'exists')):
        exists = db_path.exists()
    else:
        exists = os.path.exists(str(db_path))
    if not exists:
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print('  - [SKIP] 缺表 %s，跳过' % TABLE)
            return False

        if 'retention_until' not in _columns(conn, TABLE):
            conn.execute('ALTER TABLE %s ADD COLUMN retention_until TIMESTAMP' % TABLE)
            print('  - [ALTER] 列 %s.retention_until' % TABLE)
        else:
            print('  - [SKIP] 列 %s.retention_until 已存在' % TABLE)

        if not _index_exists(conn, INDEX_NAME):
            conn.execute(
                'CREATE INDEX %s ON %s(retention_until)' % (INDEX_NAME, TABLE)
            )
            print('  - [INDEX] %s' % INDEX_NAME)
        else:
            print('  - [SKIP] 索引 %s 已存在' % INDEX_NAME)

        cur = conn.execute(
            "UPDATE %s SET retention_until = "
            "strftime('%%Y-%%m-%%dT%%H:%%M:%%S', datetime(created_at, '+%d days')) "
            "WHERE retention_until IS NULL" % (TABLE, RETENTION_DAYS)
        )
        print('  - [BACKFILL] %d 行 retention_until = created_at + %d 天'
              % (cur.rowcount, RETENTION_DAYS))

        conn.execute(ARCHIVE_DDL)
        print('  - [OK] 归档表 %s' % ARCHIVE_TABLE)

        conn.commit()
        print('[v228] 迁移提交完成')
        return True
    except Exception:
        conn.rollback()
        print('[v228] 失败，已回滚')
        raise
    finally:
        conn.close()


def verify(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            return {'ok': False, 'error': 'missing table %s' % TABLE}
        if 'retention_until' not in _columns(conn, TABLE):
            return {'ok': False, 'error': 'missing column %s.retention_until' % TABLE}
        if not _index_exists(conn, INDEX_NAME):
            return {'ok': False, 'error': 'missing index %s' % INDEX_NAME}
        if not _table_exists(conn, ARCHIVE_TABLE):
            return {'ok': False, 'error': 'missing table %s' % ARCHIVE_TABLE}
        null_count = conn.execute(
            'SELECT COUNT(*) FROM %s WHERE retention_until IS NULL' % TABLE
        ).fetchone()[0]
        if null_count:
            return {'ok': False, 'error': '%d rows without retention_until' % null_count}
        return {'ok': True, 'retention_days': RETENTION_DAYS}
    finally:
        conn.close()


def rollback(db_path):
    """回滚：删除索引与归档表；列保留（SQLite DROP COLUMN 需要 3.35+，避免破坏旧库）"""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute('DROP INDEX IF EXISTS %s' % INDEX_NAME)
        conn.execute('DROP TABLE IF EXISTS %s' % ARCHIVE_TABLE)
        conn.commit()
        print('[v228] 回滚完成（retention_until 列保留）')
    finally:
        conn.close()
