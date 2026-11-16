# -*- coding: utf-8 -*-
"""v280 —— 订阅改引用连接：`change_subscriptions.connection_id`。

依据:
  docs/specs/spec-integration-module-2026-11-15.md
    §4 数据模型 / §6 FR-1 / §6 FR-3

内容:
  1. `change_subscriptions` 加列 `connection_id`（弱引用 `integration_connection.id`，
     不建 FK，沿用 v246 `task_runs` 的弱引用风格），加索引。
  2. 回填：按 `webhook_url = integration_connection.endpoint AND
     channel_type='webhook'` 把 v279 已生成的连接挂回订阅；
     `webhook_url` / `webhook_secret` 保留只读兼容，不删除。

边界:
  · 不改 `change_subscriptions` 的 channel 枚举 / 唯一键；
  · ALTER 前用 PRAGMA table_info 守卫，回填一律 `WHERE connection_id IS NULL`，可重复执行。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v280__subscription_connection_ref'

SUBSCRIPTION_TABLE = 'change_subscriptions'
CONNECTION_TABLE = 'integration_connection'

NEW_COLUMNS = (
    ('connection_id', 'INTEGER REFERENCES integration_connection(id)'),
)

INDEXES = (
    ('idx_change_subscriptions_connection_id',
     'CREATE INDEX IF NOT EXISTS idx_change_subscriptions_connection_id '
     'ON change_subscriptions(connection_id)'),
)


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [table]
    ).fetchone()
    return bool(row)


def _has_index(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name = ?", [name]
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    except sqlite3.DatabaseError:
        return set()
    return {row[1] for row in rows}


def _do_columns(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, SUBSCRIPTION_TABLE):
        print('  - [SKIP] 表 %s 不存在，跳过加列' % SUBSCRIPTION_TABLE)
        return
    existing = _columns(conn, SUBSCRIPTION_TABLE)
    for column, ddl in NEW_COLUMNS:
        if column in existing:
            print('  - [OK] %s.%s 已存在' % (SUBSCRIPTION_TABLE, column))
            continue
        conn.execute(
            'ALTER TABLE %s ADD COLUMN %s %s' % (SUBSCRIPTION_TABLE, column, ddl))
        print('  - [NEW] %s.%s' % (SUBSCRIPTION_TABLE, column))


def _do_indexes(conn: sqlite3.Connection) -> None:
    if 'connection_id' not in _columns(conn, SUBSCRIPTION_TABLE):
        print('  - [SKIP] 缺列 connection_id，跳过索引')
        return
    for name, sql in INDEXES:
        if _has_index(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
            continue
        conn.execute(sql)
        print('  - [NEW] 索引 %s' % name)


def _backfill(conn: sqlite3.Connection) -> None:
    """webhook_url → connection_id（按端点匹配，只补空值）。"""
    if not _has_table(conn, CONNECTION_TABLE):
        print('  - [SKIP] 表 %s 不存在，跳过回填' % CONNECTION_TABLE)
        return
    if 'connection_id' not in _columns(conn, SUBSCRIPTION_TABLE):
        print('  - [SKIP] 缺列 connection_id，跳过回填')
        return
    cur = conn.execute(
        'UPDATE %s SET connection_id = ('
        '  SELECT c.id FROM %s c WHERE c.channel_type = \'webhook\' '
        '  AND c.endpoint = %s.webhook_url LIMIT 1'
        ') WHERE connection_id IS NULL '
        "AND webhook_url IS NOT NULL AND TRIM(webhook_url) <> '' "
        'AND EXISTS (SELECT 1 FROM %s c WHERE c.channel_type = \'webhook\' '
        'AND c.endpoint = %s.webhook_url)'
        % (SUBSCRIPTION_TABLE, CONNECTION_TABLE, SUBSCRIPTION_TABLE,
           CONNECTION_TABLE, SUBSCRIPTION_TABLE))
    print('  - [OK] connection_id 回填 %d 行' % (cur.rowcount or 0))


def migrate(db_path, skip_backup=True) -> bool:
    """migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    path = Path(db_path)
    if not path.exists():
        print('[v280] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v280] 开始: 订阅改引用连接')
        _do_columns(conn)
        _do_indexes(conn)
        _backfill(conn)
        conn.commit()
        print('[v280] 完成')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


#: 部分历史迁移以 `upgrade()` 命名；保留别名便于手工调用。
upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v280 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        ok = True
        columns = _columns(conn, SUBSCRIPTION_TABLE)
        for column, _ddl in NEW_COLUMNS:
            if column not in columns:
                print('[v280 verify] FAIL: 缺列 %s.%s'
                      % (SUBSCRIPTION_TABLE, column))
                ok = False
        for name, _sql in INDEXES:
            if not _has_index(conn, name):
                print('[v280 verify] FAIL: 缺索引 %s' % name)
                ok = False
        return ok
    finally:
        conn.close()