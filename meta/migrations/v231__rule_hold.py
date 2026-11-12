# -*- coding: utf-8 -*-
"""v231: 规则挂起表 holds（spec-rule-model §10.4 A 纯派生方案）。

口径:
  · holds 是「是否被挂起」的唯一事实源，单据侧不落 hold_state 冗余列。
  · 释放 = UPDATE released_by / released_at，不删行（历史可追溯）。
  · 两个部分索引都带 ``released_at IS NULL``；查询必须重复该谓词才能命中。
  · DDL 与 meta/schemas/rule_hold.yaml 对齐（生产由启动期 schema 同步建表，
    本迁移供存量库手动执行与测试替身复用）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v231__rule_hold'

TABLE = 'holds'

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type VARCHAR(200) NOT NULL,
    record_id INTEGER NOT NULL,
    rule_key VARCHAR(200) NOT NULL,
    code VARCHAR(200),
    reason VARCHAR(200),
    applied_by VARCHAR(200),
    applied_at DATETIME NOT NULL,
    released_by VARCHAR(200),
    released_at DATETIME
)
"""

TABLES = ((TABLE, CREATE_TABLE),)

INDEXES = (
    ('idx_holds_active',
     'CREATE INDEX IF NOT EXISTS idx_holds_active '
     'ON holds(object_type, record_id) WHERE released_at IS NULL'),
    ('uq_holds_active',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_holds_active '
     'ON holds(object_type, record_id, rule_key) WHERE released_at IS NULL'),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        [name]).fetchone() is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        [name]).fetchone() is not None


def _do_tables(conn: sqlite3.Connection) -> None:
    for table, sql in TABLES:
        if _table_exists(conn, table):
            print('  - [SKIP] 表 %s 已存在' % table)
            continue
        conn.execute(sql)
        print('  - [NEW] 表 %s' % table)


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, sql in INDEXES:
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
            continue
        conn.execute(sql)
        print('  - [NEW] 索引 %s' % name)


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v231] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v231] 开始: 规则挂起 holds')
        _do_tables(conn)
        _do_indexes(conn)
        conn.commit()
        print('[v231] 迁移提交完成')
        return True
    except Exception as exc:
        conn.rollback()
        print('[v231] 失败: %s' % exc)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v231 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, TABLE):
            print('[v231 verify] FAIL: 缺表 %s' % TABLE)
            ok = False
        for name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v231 verify] FAIL: 缺索引 %s' % name)
                ok = False
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _sql in INDEXES:
            conn.execute('DROP INDEX IF EXISTS %s' % name)
        conn.execute('DROP TABLE IF EXISTS %s' % TABLE)
        conn.commit()
        return True
    finally:
        conn.close()