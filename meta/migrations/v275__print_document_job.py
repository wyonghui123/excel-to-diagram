# -*- coding: utf-8 -*-
"""v275 —— 播种 `print_document` 作业定义（批量打印接入统一执行账本）。

依据:
  docs/specs/spec-print-platform-2026-11-15.md §9（批量打印作业）

内容:
  1. 播种 `print_document` 作业定义（manual-only，无触发器）；
  2. 不新增表 / 列，不改变任何现有调度行为。

边界:
  · 播种幂等（按 code 判存在）；
  · `max_attempts=1`：每份打印已独立落 `print_runs`，重试会产生重复归档件；
  · 回滚只需删除该作业定义（无对应 run 时安全）。
"""

import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v275__print_document_job'

JOB_TABLE = 'job_definitions'

JOB_CODE = 'print_document'

PARAMS_SCHEMA = {
    'type': 'object',
    'required': ['bo_code', 'doc_ids'],
    'properties': {
        'bo_code': {'type': 'string'},
        'type_code': {'type': 'string'},
        'doc_ids': {'type': 'array'},
        'template_id': {'type': 'integer'},
        'operator': {'type': 'object'},
        'user': {'type': 'object'},
    },
}


def _seed_job(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        'SELECT id FROM %s WHERE code=?' % JOB_TABLE, [JOB_CODE]).fetchone()
    if exists:
        print('  - [SKIP] 作业定义 %s 已存在' % JOB_CODE)
        return
    conn.execute(
        'INSERT INTO %s (code, name, description, executor_type, handler, '
        'params_schema, default_params, timeout_seconds, max_attempts, '
        'backoff_seconds, concurrency_group, record_mode, status, '
        'created_at, updated_at) '
        "VALUES (?, ?, ?, 'python', 'print_document', ?, NULL, 3600, 1, 60, "
        "'print', 'all', 'active', datetime('now'), datetime('now'))" % JOB_TABLE,
        [JOB_CODE, '批量打印',
         '批量打印执行体；由 /api/print/batch 或任务中心发起',
         json.dumps(PARAMS_SCHEMA, ensure_ascii=False)])
    print('  - [NEW] 作业定义 %s' % JOB_CODE)


def migrate(db_path, skip_backup=True) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v275] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v275] 开始: print_document 作业定义')
        conn.execute('BEGIN')
        _seed_job(conn)
        conn.commit()
        print('[v275] 完成')
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
        print('[v275 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        row = conn.execute(
            'SELECT handler FROM %s WHERE code=?' % JOB_TABLE,
            [JOB_CODE]).fetchone()
        if not row or row[0] != 'print_document':
            print('[v275 verify] FAIL: 缺作业定义 %s' % JOB_CODE)
            return False
        return True
    finally:
        conn.close()