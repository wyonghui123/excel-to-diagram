# -*- coding: utf-8 -*-
"""v276 —— 审批域单一事实源收敛（spec-approval-workflow-2026-11-15 §3.2）

依据:
  docs/specs/spec-approval-workflow-2026-11-15.md §3.2（D-AP-04 / D-AP-07）

内容:
  1. `tasks` 新增 `doc_ref_type` / `doc_ref_id`（审批任务单据引用拆列，
     替代把 `doc_ref` 当字符串判定的做法）；
  2. 新增索引 `idx_tasks_approval_ref`（在途判重查询走新列）；
  3. `approval_policies` 新增 `version`（快照记录 `policy_version`，
     策略变更不回溯在途任务）；
  4. 历史在途审批任务按 `inputs` 的 `{bo}_id` 键回填 `doc_ref_type`。

边界:
  · 全部 DDL 走 PRAGMA 判存在，可重复执行；
  · 回填只处理 `doc_ref_type IS NULL` 的 `type='approval'` 行，无法判定对象时保持 NULL
    （下游按 fail-closed 处理，不猜测）。
"""

import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v276__approval_ssot'

TASKS_TABLE = 'tasks'
POLICY_TABLE = 'approval_policies'
INDEX_NAME = 'idx_tasks_approval_ref'

#: tasks.inputs 中的对象主键 → 对象类型（仅当前可审批对象；未知键不猜）
ID_KEY_TO_OBJECT = {
    'purchase_order_id': 'purchase_order',
    'transfer_order_id': 'transfer_order',
    'requisition_id': 'requisition',
    'service_request_id': 'service_request',
}


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    except sqlite3.Error:
        return set()
    return {row[1] for row in rows}


def _add_columns(conn: sqlite3.Connection) -> None:
    task_cols = _columns(conn, TASKS_TABLE)
    for column in ('doc_ref_type', 'doc_ref_id'):
        if column in task_cols:
            print('  - [SKIP] tasks.%s 已存在' % column)
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s VARCHAR(200)'
                     % (TASKS_TABLE, column))
        print('  - [NEW] tasks.%s' % column)

    if 'version' in _columns(conn, POLICY_TABLE):
        print('  - [SKIP] approval_policies.version 已存在')
    else:
        conn.execute('ALTER TABLE %s ADD COLUMN version INTEGER NOT NULL DEFAULT 1'
                     % POLICY_TABLE)
        print('  - [NEW] approval_policies.version')

    conn.execute(
        'CREATE INDEX IF NOT EXISTS %s ON %s (doc_ref_type, doc_ref_id, status)'
        % (INDEX_NAME, TASKS_TABLE))
    print('  - [OK] 索引 %s' % INDEX_NAME)


def _backfill(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, inputs, doc_ref FROM %s "
        'WHERE type = ? AND doc_ref_type IS NULL' % TASKS_TABLE,
        ['approval']).fetchall()
    updated = 0
    for task_id, inputs, doc_ref in rows:
        try:
            payload = json.loads(inputs or '{}')
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        object_type = next(
            (ID_KEY_TO_OBJECT[key] for key in payload if key in ID_KEY_TO_OBJECT),
            None)
        if not object_type:
            continue
        conn.execute(
            'UPDATE %s SET doc_ref_type = ?, doc_ref_id = ? WHERE id = ?'
            % TASKS_TABLE,
            [object_type, str(payload.get('id') or doc_ref or ''), task_id])
        updated += 1
    print('  - [OK] 回填审批任务对象类型 %d 条' % updated)


def migrate(db_path, skip_backup=True) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v276] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v276] 开始: 审批域单一事实源收敛')
        conn.execute('BEGIN')
        _add_columns(conn)
        _backfill(conn)
        conn.commit()
        print('[v276] 完成')
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
        print('[v276 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        task_cols = _columns(conn, TASKS_TABLE)
        missing = {'doc_ref_type', 'doc_ref_id'} - task_cols
        if missing:
            print('[v276 verify] FAIL: tasks 缺列 %s' % sorted(missing))
            return False
        if 'version' not in _columns(conn, POLICY_TABLE):
            print('[v276 verify] FAIL: approval_policies 缺列 version')
            return False
        return True
    finally:
        conn.close()