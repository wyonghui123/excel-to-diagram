# -*- coding: utf-8 -*-
"""v270 —— `task_runs.progress` 进度列 + `import_cascade` 作业定义播种。

依据:
  docs/specs/spec-unified-async-job-2026-11-14.md
    FR-004（进度上报）/ FR-006（批量导入接账本）/ TR-001（幂等迁移）

内容:
  1. `task_runs` 增加可空 `progress TEXT`（JSON: current/total/percent/stage/message/ts）；
  2. 播种 `import_cascade` 作业定义（manual-only，无触发器）。

边界:
  · DDL 幂等（PRAGMA table_info 判存在后再 ALTER）；
  · 播种幂等（按 code 判存在）；不改任何现有调度行为；
  · 不删除列，回滚只需停止读写 `progress`（spec TR-001）。
"""

import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v270__task_runs_progress'

RUN_TABLE = 'task_runs'
JOB_TABLE = 'job_definitions'

IMPORT_CODE = 'import_cascade'

IMPORT_PARAMS_SCHEMA = {
    'type': 'object',
    'required': ['file_path'],
    'properties': {
        'file_path': {'type': 'string'},
        'conflict_strategy': {'type': 'string'},
        'context': {'type': 'object'},
        'force_override_explicit_mode': {'type': 'boolean'},
        'audit': {'type': 'object'},
    },
}


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    return any(row[1] == column for row in rows)


def _add_progress_column(conn: sqlite3.Connection) -> None:
    if _column_exists(conn, RUN_TABLE, 'progress'):
        print('  - [SKIP] %s.progress 已存在' % RUN_TABLE)
        return
    conn.execute('ALTER TABLE %s ADD COLUMN progress TEXT' % RUN_TABLE)
    print('  - [NEW] %s.progress TEXT' % RUN_TABLE)


def _seed_import_job(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        'SELECT id FROM %s WHERE code=?' % JOB_TABLE, [IMPORT_CODE]).fetchone()
    if exists:
        print('  - [SKIP] 作业定义 %s 已存在' % IMPORT_CODE)
        return
    conn.execute(
        'INSERT INTO %s (code, name, description, executor_type, handler, '
        'params_schema, default_params, timeout_seconds, max_attempts, '
        'backoff_seconds, concurrency_group, record_mode, status, '
        'created_at, updated_at) '
        "VALUES (?, ?, ?, 'python', 'import_cascade', ?, NULL, 3600, 2, 60, "
        "'import', 'all', 'active', datetime('now'), datetime('now'))" % JOB_TABLE,
        [IMPORT_CODE, '批量导入（级联）',
         'Excel 批量导入执行体；由 /import/async 或任务中心发起',
         json.dumps(IMPORT_PARAMS_SCHEMA, ensure_ascii=False)])
    print('  - [NEW] 作业定义 %s' % IMPORT_CODE)


def migrate(db_path, skip_backup=True) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v270] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v270] 开始: task_runs.progress + import_cascade 作业定义')
        conn.execute('BEGIN')
        _add_progress_column(conn)
        _seed_import_job(conn)
        conn.commit()
        print('[v270] 完成')
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
        print('[v270 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        if not _column_exists(conn, RUN_TABLE, 'progress'):
            print('[v270 verify] FAIL: 缺 %s.progress' % RUN_TABLE)
            return False
        row = conn.execute(
            'SELECT handler FROM %s WHERE code=?' % JOB_TABLE,
            [IMPORT_CODE]).fetchone()
        if not row or row[0] != 'import_cascade':
            print('[v270 verify] FAIL: 缺作业定义 %s' % IMPORT_CODE)
            return False
        return True
    finally:
        conn.close()