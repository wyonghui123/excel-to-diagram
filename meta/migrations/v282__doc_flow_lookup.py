# -*- coding: utf-8 -*-
"""v282 —— 映射三钩子的持久化（M4）。

依据:
  docs/specs/spec-integration-module-2026-11-15.md
    §5.2 映射三钩子 / §6 FR-5 / §11 M4

内容:
  1. `doc_flow_rule` 追加 3 列: condition(TEXT) / transform(JSON) / lookup_ref(JSON)
  2. 新建映射码表 `doc_flow_lookup`（lookup_ref 钩子的数据源）

幂等: 列已存在则跳过；表/索引 IF NOT EXISTS。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v282__doc_flow_lookup'

RULE_TABLE = 'doc_flow_rule'
LOOKUP_TABLE = 'doc_flow_lookup'

NEW_COLUMNS = (
    ('condition', "TEXT NOT NULL DEFAULT ''"),
    ('transform', "TEXT NOT NULL DEFAULT '{}'"),
    ('lookup_ref', "TEXT NOT NULL DEFAULT '{}'"),
)

LOOKUP_DDL = """
CREATE TABLE IF NOT EXISTS doc_flow_lookup (
    lookup_code  TEXT NOT NULL,
    source_value TEXT NOT NULL,
    target_value TEXT,
    description  TEXT NOT NULL DEFAULT '',
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT,
    updated_at   TEXT,
    PRIMARY KEY (lookup_code, source_value)
)
"""

LOOKUP_INDEX_DDL = (
    'CREATE INDEX IF NOT EXISTS idx_doc_flow_lookup_code '
    'ON doc_flow_lookup(lookup_code)'
)


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [table]
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str):
    return [row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)]


def _do_columns(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, RULE_TABLE):
        print('  - [SKIP] 表 %s 不存在，跳过加列' % RULE_TABLE)
        return
    existing = set(_columns(conn, RULE_TABLE))
    for name, ddl in NEW_COLUMNS:
        if name in existing:
            print('  - [OK] 列 %s 已存在' % name)
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (RULE_TABLE, name, ddl))
        print('  - [NEW] 列 %s' % name)


def _do_lookup_table(conn: sqlite3.Connection) -> None:
    conn.execute(LOOKUP_DDL)
    conn.execute(LOOKUP_INDEX_DDL)
    print('  - [OK] 码表 %s 就绪' % LOOKUP_TABLE)


def migrate(db_path, skip_backup=True) -> bool:
    """migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    path = Path(db_path)
    if not path.exists():
        print('[v282] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v282] 开始: 映射三钩子持久化')
        _do_columns(conn)
        _do_lookup_table(conn)
        conn.commit()
        print('[v282] 完成')
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
        print('[v282 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        if not _has_table(conn, LOOKUP_TABLE):
            print('[v282 verify] FAIL: 码表 %s 不存在' % LOOKUP_TABLE)
            return False
        if _has_table(conn, RULE_TABLE):
            existing = set(_columns(conn, RULE_TABLE))
            missing = [n for n, _ in NEW_COLUMNS if n not in existing]
            if missing:
                print('[v282 verify] FAIL: 缺列 %s' % missing)
                return False
        return True
    finally:
        conn.close()