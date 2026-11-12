# -*- coding: utf-8 -*-
"""v247 —— 后台作业：`bo_action` 桥接作业播种 + params_schema 补齐。

依据:
  docs/specs/spec-background-job-infrastructure-2026-11-10.md
    §7.3 bo_action 桥接 / §7.2 参数白名单

内容:
  1. 为 v246 播种的运维作业补显式空 schema
     `{"type":"object","additionalProperties":false}`（spec §7.2 要求）；
  2. 播种 `inspection_daily` 示例定义（`handler='bo_action'`，`status='disabled'`）
     与同名 cron 触发器（`enabled=0`）—— 只建能力，不改变现网调度。

边界:
  · 幂等：schema 只更新 NULL 行，定义用 INSERT OR IGNORE；
  · 不启用任何触发器，不写 `task_runs`。
"""

import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v247__job_bo_action_seed'

JOB_TABLE = 'job_definitions'
TRIGGER_TABLE = 'job_triggers'

EMPTY_SCHEMA = json.dumps({'type': 'object', 'additionalProperties': False})

INSPECTION_CODE = 'inspection_daily'

INSPECTION_SCHEMA = {
    'type': 'object',
    'required': ['action_id'],
    'additionalProperties': False,
    'properties': {
        'action_id': {'type': 'string', 'const': 'inspection.run'},
        'payload': {'type': 'object'},
        'permissions': {'type': 'array'},
    },
}

INSPECTION_DEFAULT_PARAMS = {
    'action_id': 'inspection.run',
    'payload': {},
    'permissions': ['*'],
}


def _backfill_schemas(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        'UPDATE %s SET params_schema=?, updated_at=datetime(\'now\') '
        'WHERE params_schema IS NULL OR params_schema=\'\'' % JOB_TABLE,
        [EMPTY_SCHEMA])
    print('  - [SCHEMA] 补齐 %d 条作业定义的 params_schema' % cur.rowcount)


def _seed_inspection(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        'SELECT id FROM %s WHERE code=?' % JOB_TABLE,
        [INSPECTION_CODE]).fetchone()
    if exists:
        print('  - [SKIP] 作业定义 %s 已存在' % INSPECTION_CODE)
        job_id = exists[0]
    else:
        conn.execute(
            'INSERT INTO %s (code, name, description, executor_type, handler, '
            'params_schema, default_params, timeout_seconds, max_attempts, '
            'backoff_seconds, record_mode, status, created_at, updated_at) '
            "VALUES (?, ?, ?, 'python', 'bo_action', ?, ?, 120, 2, 60, "
            "'all', 'disabled', datetime('now'), datetime('now'))" % JOB_TABLE,
            [INSPECTION_CODE, '库存巡检（示例）',
             '经 bo_action 桥接调用 business action；默认禁用，验收时手工启用',
             json.dumps(INSPECTION_SCHEMA, ensure_ascii=False),
             json.dumps(INSPECTION_DEFAULT_PARAMS, ensure_ascii=False)])
        job_id = conn.execute(
            'SELECT id FROM %s WHERE code=?' % JOB_TABLE,
            [INSPECTION_CODE]).fetchone()[0]
        print('  - [NEW] 作业定义 %s (status=disabled)' % INSPECTION_CODE)

    trigger = conn.execute(
        'SELECT 1 FROM %s WHERE job_id=? AND trigger_type=?' % TRIGGER_TABLE,
        [job_id, 'cron']).fetchone()
    if trigger:
        print('  - [SKIP] 触发器 %s 已存在' % INSPECTION_CODE)
        return
    conn.execute(
        'INSERT INTO %s (job_id, trigger_type, cron_expr, enabled, '
        'next_run_at, created_at) '
        "VALUES (?, 'cron', '0 4 * * *', 0, NULL, datetime('now'))"
        % TRIGGER_TABLE, [job_id])
    print('  - [NEW] 触发器 %s (enabled=0)' % INSPECTION_CODE)


def migrate(db_path, skip_backup=True) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v247] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v247] 开始: bo_action 作业播种')
        conn.execute('BEGIN')
        _backfill_schemas(conn)
        _seed_inspection(conn)
        conn.commit()
        print('[v247] 完成')
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
        print('[v247 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        row = conn.execute(
            'SELECT handler, status FROM %s WHERE code=?' % JOB_TABLE,
            [INSPECTION_CODE]).fetchone()
        if not row:
            print('[v247 verify] FAIL: 缺作业定义 %s' % INSPECTION_CODE)
            return False
        if row[0] != 'bo_action':
            print('[v247 verify] FAIL: %s handler=%r' % (INSPECTION_CODE, row[0]))
            return False
        return True
    finally:
        conn.close()