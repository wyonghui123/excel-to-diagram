# -*- coding: utf-8 -*-
"""v271 —— 播种 `export_cascade` 作业定义（异步导出接入统一执行账本）。

依据:
  docs/specs/spec-unified-async-job-2026-11-14.md
    FR-001（唯一执行账本）/ FR-007（状态接口兼容 + 开关回退）/ TR-001（幂等迁移）

内容:
  1. 播种 `export_cascade` 作业定义（manual-only，无触发器）；
  2. 不新增表 / 列，不改变任何现有调度行为。

边界:
  · 播种幂等（按 code 判存在）；
  · `max_attempts=1`：导出每次生成新文件，重试会产生重复产物；
  · 回滚只需删除该作业定义（无对应 run 时安全）。
"""

import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v271__export_cascade_job'

JOB_TABLE = 'job_definitions'

EXPORT_CODE = 'export_cascade'

EXPORT_PARAMS_SCHEMA = {
    'type': 'object',
    'required': ['object_type'],
    'properties': {
        'object_type': {'type': 'string'},
        'scope': {'type': 'string'},
        'selected_types': {'type': 'array'},
        'filters': {'type': 'object'},
        'sort_by': {'type': 'string'},
        'sort_order': {'type': 'string'},
        'options': {'type': 'object'},
        'user': {'type': 'object'},
    },
}


def _seed_export_job(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        'SELECT id FROM %s WHERE code=?' % JOB_TABLE, [EXPORT_CODE]).fetchone()
    if exists:
        print('  - [SKIP] 作业定义 %s 已存在' % EXPORT_CODE)
        return
    conn.execute(
        'INSERT INTO %s (code, name, description, executor_type, handler, '
        'params_schema, default_params, timeout_seconds, max_attempts, '
        'backoff_seconds, concurrency_group, record_mode, status, '
        'created_at, updated_at) '
        "VALUES (?, ?, ?, 'python', 'export_cascade', ?, NULL, 3600, 1, 60, "
        "'export', 'all', 'active', datetime('now'), datetime('now'))" % JOB_TABLE,
        [EXPORT_CODE, '批量导出（级联）',
         'Excel 批量导出执行体；由 /export/async 或任务中心发起',
         json.dumps(EXPORT_PARAMS_SCHEMA, ensure_ascii=False)])
    print('  - [NEW] 作业定义 %s' % EXPORT_CODE)


def migrate(db_path, skip_backup=True) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v271] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v271] 开始: export_cascade 作业定义')
        conn.execute('BEGIN')
        _seed_export_job(conn)
        conn.commit()
        print('[v271] 完成')
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
        print('[v271 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        row = conn.execute(
            'SELECT handler FROM %s WHERE code=?' % JOB_TABLE,
            [EXPORT_CODE]).fetchone()
        if not row or row[0] != 'export_cascade':
            print('[v271 verify] FAIL: 缺作业定义 %s' % EXPORT_CODE)
            return False
        return True
    finally:
        conn.close()