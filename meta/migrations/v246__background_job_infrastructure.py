# -*- coding: utf-8 -*-
"""v246 —— 后台任务基础设施：job_definitions / job_triggers / task_runs。

依据:
  docs/specs/spec-background-job-infrastructure-2026-11-10.md
    §4 数据模型 / §5 状态机 / §9 迁移与播种

内容:
  1. 三张表：`job_definitions`（作业定义）、`job_triggers`（触发器）、
     `task_runs`（执行账本）。
  2. 两个索引：到期扫描 `(enabled, next_run_at)`；租约回收
     `(status, lease_until)`。
  3. 播种 10 条作业定义（8 个运维作业 + platform_tick + workflow_schedule 占位），
     与 `maintenance_scheduler.DEFAULT_JOBS` / `platform_scheduler.PLATFORM_JOBS`
     的 code / cron 逐条对齐。
  4. 播种同名触发器，但一律 `enabled=0`、`next_run_at=NULL`：
     本迁移只建能力，不改变任何现有调度行为（P1 影子比对时手工打开）。

边界:
  · 不迁移 `task_executions` 历史行，不删除 Gen1 队列表；
  · 不写入 `task_events`（执行账本与领域事件双轨，见 spec §3「明确不做」）；
  · 所有 DDL 幂等（IF NOT EXISTS），播种幂等（INSERT OR IGNORE）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v246__background_job_infrastructure'

JOB_TABLE = 'job_definitions'
TRIGGER_TABLE = 'job_triggers'
RUN_TABLE = 'task_runs'

TABLES = (
    (JOB_TABLE, """
CREATE TABLE IF NOT EXISTS job_definitions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    code              TEXT    NOT NULL UNIQUE,
    name              TEXT    NOT NULL,
    description       TEXT,
    executor_type     TEXT    NOT NULL DEFAULT 'python',
    handler           TEXT    NOT NULL,
    params_schema     TEXT,
    default_params    TEXT,
    timeout_seconds   INTEGER NOT NULL DEFAULT 300,
    max_attempts      INTEGER NOT NULL DEFAULT 3,
    backoff_seconds   INTEGER NOT NULL DEFAULT 60,
    concurrency_group TEXT,
    record_mode       TEXT    NOT NULL DEFAULT 'all',
    status            TEXT    NOT NULL DEFAULT 'active',
    created_at        TEXT,
    updated_at        TEXT
)
"""),
    (TRIGGER_TABLE, """
CREATE TABLE IF NOT EXISTS job_triggers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           INTEGER NOT NULL,
    trigger_type     TEXT    NOT NULL DEFAULT 'cron',
    cron_expr        TEXT,
    interval_seconds INTEGER,
    event_name       TEXT,
    params_override  TEXT,
    timezone         TEXT    NOT NULL DEFAULT 'Asia/Shanghai',
    enabled          INTEGER NOT NULL DEFAULT 1,
    next_run_at      REAL,
    last_run_at      REAL,
    created_at       TEXT,
    updated_at       TEXT
)
"""),
    (RUN_TABLE, """
CREATE TABLE IF NOT EXISTS task_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key          TEXT    NOT NULL UNIQUE,
    job_id           INTEGER NOT NULL,
    trigger_id       INTEGER,
    task_id          INTEGER,
    status           TEXT    NOT NULL,
    params           TEXT,
    attempt          INTEGER NOT NULL DEFAULT 1,
    max_attempts     INTEGER NOT NULL DEFAULT 3,
    scheduled_for    REAL    NOT NULL,
    claimed_at       REAL,
    started_at       REAL,
    finished_at      REAL,
    lease_until      REAL,
    worker_id        TEXT,
    duration_ms      INTEGER,
    result           TEXT,
    error            TEXT,
    next_retry_at    REAL,
    created_at       TEXT,
    updated_at       TEXT
)
"""),
)

INDEXES = (
    ('ix_job_triggers_due',
     'CREATE INDEX IF NOT EXISTS ix_job_triggers_due '
     'ON job_triggers(enabled, next_run_at)'),
    ('ix_task_runs_status_lease',
     'CREATE INDEX IF NOT EXISTS ix_task_runs_status_lease '
     'ON task_runs(status, lease_until)'),
    ('ix_task_runs_job_time',
     'CREATE INDEX IF NOT EXISTS ix_task_runs_job_time '
     'ON task_runs(job_id, created_at)'),
)

#: 作业定义种子。
#: (code, name, handler, timeout_seconds, max_attempts, backoff_seconds,
#:  record_mode, cron_expr)
#: cron 与 `maintenance_scheduler.DEFAULT_JOBS` / `platform_scheduler.PLATFORM_JOBS`
#: 逐条等值；workflow_schedule 的 cron 由 workflow 定义动态派生，故留空。
JOB_SEEDS = (
    ('db_analyze', '数据库分析', 'db_analyze',
     900, 2, 300, 'all', '0 3 * * *'),
    ('db_vacuum', '数据库整理', 'db_vacuum',
     3600, 1, 0, 'all', '0 4 * * 0'),
    ('db_integrity_check', '数据库完整性检查', 'db_integrity_check',
     1800, 2, 300, 'all', '0 6 * * *'),
    ('db_checkpoint', '数据库检查点', 'db_checkpoint',
     300, 2, 60, 'failure_only', '*/5 * * * *'),
    ('audit_failure_retry', '审计失败重试', 'audit_failure_retry',
     300, 3, 60, 'all', '*/10 * * * *'),
    ('audit_log_cleanup', '审计日志清理', 'audit_log_cleanup',
     600, 2, 300, 'all', '0 2 * * *'),
    ('audit_log_archive', '审计日志归档', 'audit_log_archive',
     1800, 2, 300, 'all', '0 1 * * 0'),
    ('import_queue_processor', '导入队列处理器', 'import_queue_processor',
     300, 3, 30, 'failure_only', '*/2 * * * *'),
    ('platform_tick', '平台心跳', 'platform_tick',
     60, 1, 0, 'failure_only', '* * * * *'),
    ('workflow_schedule', '工作流调度（动态触发器占位）', 'workflow_schedule',
     60, 1, 0, 'failure_only', None),
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


def _do_job_definitions(conn: sqlite3.Connection) -> None:
    """播种作业定义（按 code 幂等）。"""
    for (code, name, handler, timeout, max_attempts, backoff,
         record_mode, _cron) in JOB_SEEDS:
        exists = conn.execute(
            'SELECT 1 FROM %s WHERE code=?' % JOB_TABLE, [code]).fetchone()
        if exists:
            print('  - [SKIP] 作业定义 %s 已存在' % code)
            continue
        conn.execute(
            'INSERT INTO %s (code, name, executor_type, handler, '
            'timeout_seconds, max_attempts, backoff_seconds, record_mode, '
            "status, created_at) VALUES (?, ?, 'python', ?, ?, ?, ?, ?, "
            "'active', datetime('now'))" % JOB_TABLE,
            [code, name, handler, timeout, max_attempts, backoff, record_mode])
        print('  - [NEW] 作业定义 %s' % code)


def _do_triggers(conn: sqlite3.Connection) -> None:
    """播种触发器（一律 enabled=0，不改变现有调度行为）。"""
    for (code, _name, _handler, _timeout, _max_attempts, _backoff,
         _record_mode, cron) in JOB_SEEDS:
        row = conn.execute(
            'SELECT id FROM %s WHERE code=?' % JOB_TABLE, [code]).fetchone()
        if not row:
            print('  - [SKIP] 触发器 %s: 缺作业定义' % code)
            continue
        job_id = row[0]
        exists = conn.execute(
            'SELECT 1 FROM %s WHERE job_id=? AND trigger_type=?' % TRIGGER_TABLE,
            [job_id, 'cron']).fetchone()
        if exists:
            print('  - [SKIP] 触发器 %s 已存在' % code)
            continue
        conn.execute(
            'INSERT INTO %s (job_id, trigger_type, cron_expr, enabled, '
            'next_run_at, created_at) '
            "VALUES (?, 'cron', ?, 0, NULL, datetime('now'))" % TRIGGER_TABLE,
            [job_id, cron])
        print('  - [NEW] 触发器 %s (enabled=0)' % code)


def migrate(db_path, skip_backup=True) -> bool:
    """migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    path = Path(db_path)
    if not path.exists():
        print('[v246] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v246] 开始: 后台任务基础设施')
        _do_tables(conn)
        _do_indexes(conn)
        _do_job_definitions(conn)
        _do_triggers(conn)
        conn.commit()
        print('[v246] 完成')
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
        print('[v246 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        ok = True
        for table, _sql in TABLES:
            if not _table_exists(conn, table):
                print('[v246 verify] FAIL: 缺表 %s' % table)
                ok = False
        for name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v246 verify] FAIL: 缺索引 %s' % name)
                ok = False
        count = conn.execute(
            'SELECT COUNT(*) FROM %s' % JOB_TABLE).fetchone()[0]
        if count < len(JOB_SEEDS):
            print('[v246 verify] FAIL: 作业定义仅 %d 条（期望 >= %d）'
                  % (count, len(JOB_SEEDS)))
            ok = False
        return ok
    finally:
        conn.close()