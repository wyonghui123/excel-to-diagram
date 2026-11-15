# -*- coding: utf-8 -*-
"""v278 —— 任务定义层通用化（spec-approval-workflow-2026-11-15 §9.4）

依据:
  docs/specs/spec-approval-workflow-2026-11-15.md §9（M5-1）

内容（只加列 + 重建一个唯一索引，零新表）:
  1. `approval_policies.task_type`：定义服务的任务类型（默认 approval）；
  2. `approval_policy_steps.stage_no`：阶段序号（默认 1 = 现有金额分段并行集合）；
  3. `approval_policy_steps.action_type`：approve / auto / notify；
  4. `approval_policy_steps.routing_json`：6 个路由参数 + 取人器参数；
  5. 唯一索引 `uidx_approval_policy_step` 由 (policy_id, step_no)
     改为 (policy_id, stage_no, step_no)（现有数据 stage_no=1，等价）。

边界:
  · 不改表名（D-GT-01），通用性由 `task_type` 表达；
  · `tasks.stage_no` 走元数据（task.yaml）派生，不在本迁移里 ALTER；
  · 所有 DDL 幂等，可重复执行。
"""

import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v278__task_engine_generic'

POLICY_TABLE = 'approval_policies'
STEP_TABLE = 'approval_policy_steps'

#: (表, 列, 列定义)
NEW_COLUMNS = (
    (POLICY_TABLE, 'task_type',
     "VARCHAR(200) NOT NULL DEFAULT 'approval'"),
    (STEP_TABLE, 'stage_no', 'INTEGER NOT NULL DEFAULT 1'),
    (STEP_TABLE, 'action_type',
     "VARCHAR(200) NOT NULL DEFAULT 'approve'"),
    (STEP_TABLE, 'routing_json', 'TEXT'),
)

STEP_INDEXES = (
    ('uidx_approval_policy_step', 'policy_id, stage_no, step_no', True),
    ('idx_approval_step_stage', 'policy_id, stage_no', False),
)


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [table]
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    except sqlite3.DatabaseError:
        return set()
    return {row[1] for row in rows}


def _add_columns(conn: sqlite3.Connection) -> None:
    for table, column, ddl in NEW_COLUMNS:
        if not _has_table(conn, table):
            print('  - [SKIP] 表 %s 不存在' % table)
            continue
        if column in _columns(conn, table):
            print('  - [OK] %s.%s 已存在' % (table, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, ddl))
        print('  - [OK] %s.%s 新增' % (table, column))


def _rebuild_step_index(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, STEP_TABLE):
        return
    conn.execute('DROP INDEX IF EXISTS uidx_approval_policy_step')
    for name, columns, unique in STEP_INDEXES:
        conn.execute('CREATE %sINDEX IF NOT EXISTS %s ON %s (%s)' % (
            'UNIQUE ' if unique else '', name, STEP_TABLE, columns))
    print('  - [OK] 唯一索引 uidx_approval_policy_step '
          '(policy_id, stage_no, step_no) 重建')


def _normalize_rows(conn: sqlite3.Connection) -> None:
    """历史行补默认值（NULL 视为未设置），并保证 routing_json 是合法 JSON。"""
    if not _has_table(conn, STEP_TABLE):
        return
    conn.execute("UPDATE %s SET stage_no = 1 WHERE stage_no IS NULL" % STEP_TABLE)
    conn.execute("UPDATE %s SET action_type = 'approve' "
                 'WHERE action_type IS NULL OR TRIM(action_type) = %s'
                 % (STEP_TABLE, "''"))
    conn.execute("UPDATE %s SET routing_json = '{}' "
                 'WHERE routing_json IS NULL OR TRIM(routing_json) = %s'
                 % (STEP_TABLE, "''"))
    bad = []
    for row in conn.execute(
            'SELECT id, routing_json FROM %s' % STEP_TABLE).fetchall():
        try:
            json.loads(row[1])
        except (TypeError, ValueError):
            bad.append(row[0])
    if bad:
        conn.executemany(
            "UPDATE %s SET routing_json = '{}' WHERE id = ?" % STEP_TABLE,
            [(item,) for item in bad])
        print('  - [FIX] routing_json 非法 JSON 归一 %d 行' % len(bad))


def migrate(db_path, skip_backup=True) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v278] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v278] 开始: 任务定义层通用化')
        conn.execute('BEGIN')
        _add_columns(conn)
        _normalize_rows(conn)
        _rebuild_step_index(conn)
        conn.commit()
        print('[v278] 完成')
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
        print('[v278 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        missing = []
        for table, column, _ddl in NEW_COLUMNS:
            if not _has_table(conn, table):
                continue
            if column not in _columns(conn, table):
                missing.append('%s.%s' % (table, column))
        if missing:
            print('[v278 verify] FAIL: 缺列 %s' % missing)
            return False
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        if 'uidx_approval_policy_step' not in names:
            print('[v278 verify] FAIL: 缺索引 uidx_approval_policy_step')
            return False
        return True
    finally:
        conn.close()