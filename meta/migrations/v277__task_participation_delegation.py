# -*- coding: utf-8 -*-
"""v277 —— 任务参与流水 + 委托（spec-approval-workflow-2026-11-15 §8.1）

依据:
  docs/specs/spec-approval-workflow-2026-11-15.md §8.1（M4 P2，任务域通用能力）

内容（只新增两张表，零 ALTER）:
  1. `task_participations`：谁做了什么（角色 + 结果 + 代投票留痕）；
  2. `task_delegations`：委托配置（有效期 + 范围匹配，准入期身份展开）。

边界:
  · 分配真源仍是 `tasks.executor_candidates`，参与流水/委托都**不**参与分配判定；
  · 弱引用不建 FK（历史任务/用户删除不阻塞）；
  · 全部 DDL 走 IF NOT EXISTS，可重复执行。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v277__task_participation_delegation'

PARTICIPATION_TABLE = 'task_participations'
DELEGATION_TABLE = 'task_delegations'

PARTICIPATION_INDEXES = (
    ('idx_participation_task', 'task_id, outcome'),
    ('idx_participation_actor', 'participant, outcome'),
)

DELEGATION_INDEXES = (
    ('uidx_task_delegation',
     'delegator, delegate, scope_type, scope_value, effective_from', True),
    ('idx_task_delegation_delegate', 'delegate, status', False),
    ('idx_task_delegation_delegator', 'delegator, status', False),
)


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [table]
    ).fetchone()
    return bool(row)


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_participations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      VARCHAR(200) NOT NULL,
            participant  VARCHAR(200) NOT NULL,
            role         VARCHAR(32)  NOT NULL DEFAULT 'required',
            outcome      VARCHAR(32)  NOT NULL DEFAULT 'pending',
            comment      TEXT,
            decided_by   VARCHAR(200),
            on_behalf_of VARCHAR(200),
            decided_at   DATETIME,
            created_by   VARCHAR(200),
            created_at   DATETIME,
            updated_at   DATETIME
        )
    """)
    print('  - [OK] 表 %s' % PARTICIPATION_TABLE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_delegations (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            delegator      VARCHAR(200) NOT NULL,
            delegate       VARCHAR(200) NOT NULL,
            scope_type     VARCHAR(32)  NOT NULL DEFAULT 'any',
            scope_value    VARCHAR(200),
            effective_from DATETIME,
            effective_to   DATETIME,
            status         VARCHAR(32)  NOT NULL DEFAULT 'active',
            reason         TEXT,
            created_by     VARCHAR(200),
            created_at     DATETIME,
            updated_at     DATETIME
        )
    """)
    print('  - [OK] 表 %s' % DELEGATION_TABLE)

    for name, columns in PARTICIPATION_INDEXES:
        conn.execute('CREATE INDEX IF NOT EXISTS %s ON %s (%s)'
                     % (name, PARTICIPATION_TABLE, columns))
    for name, columns, unique in DELEGATION_INDEXES:
        ddl = 'CREATE %sINDEX IF NOT EXISTS %s ON %s (%s)' % (
            'UNIQUE ' if unique else '', name, DELEGATION_TABLE, columns)
        conn.execute(ddl)
    print('  - [OK] 索引 %d 个' % (len(PARTICIPATION_INDEXES) + len(DELEGATION_INDEXES)))


def migrate(db_path, skip_backup=True) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v277] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v277] 开始: 任务参与流水 + 委托')
        conn.execute('BEGIN')
        _create_tables(conn)
        conn.commit()
        print('[v277] 完成')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v277 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        missing = [t for t in (PARTICIPATION_TABLE, DELEGATION_TABLE)
                   if not _has_table(conn, t)]
        if missing:
            print('[v277 verify] FAIL: 缺表 %s' % missing)
            return False
        return True
    finally:
        conn.close()