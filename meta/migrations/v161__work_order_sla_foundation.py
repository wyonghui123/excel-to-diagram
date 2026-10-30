# -*- coding: utf-8 -*-
"""[v161] 服务工单 / SLA 地基（6 张表）

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/spec.md
  §10.5 对象模型 / §10.8 迁移 / §10.15 作业层统一契约

设计:
  · 6 张表由 work_order.yaml / work_order_operation.yaml / sla_coverage.yaml /
    sla_coverage_rule.yaml / sla_milestone.yaml / service_event.yaml 声明，
    `sync_schema` 生成；本迁移只做「断言 + 兜底 CREATE + 兜底索引」。
  · `sla_coverage_rules` 的 (coverage_id, severity, channel) 唯一索引在 SQLite
    对 channel=NULL 不生效，保存时的歧义校验由 work_order_service 兜底。
  · `service_events` 只追加（append-only），本迁移不建状态迁移约束。

幂等:
  表 / 索引先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删索引 + 删表（先子表后父表）。
"""
import sqlite3
import sys
from pathlib import Path

WORK_ORDERS_TABLE = 'work_orders'
OPERATIONS_TABLE = 'work_order_operations'
COVERAGES_TABLE = 'sla_coverages'
COVERAGE_RULES_TABLE = 'sla_coverage_rules'
MILESTONES_TABLE = 'sla_milestones'
EVENTS_TABLE = 'service_events'

WORK_ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS work_orders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_no        TEXT NOT NULL,
    order_type           TEXT NOT NULL DEFAULT 'service',
    schedule_id          INTEGER NOT NULL,
    order_id             INTEGER NOT NULL,
    order_line_id        INTEGER NOT NULL,
    customer_account_id  INTEGER NULL,
    severity             TEXT NOT NULL,
    channel              TEXT NULL,
    status               TEXT NOT NULL DEFAULT 'New',
    coverage_id          INTEGER NULL,
    asset_ref            TEXT NULL,
    opened_at            TEXT NULL,
    first_response_at    TEXT NULL,
    resolved_at          TEXT NULL,
    closed_at            TEXT NULL,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

OPERATIONS_DDL = """
CREATE TABLE IF NOT EXISTS work_order_operations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id  INTEGER NOT NULL,
    seq            INTEGER NOT NULL,
    work_center_id INTEGER NULL,
    operation_name TEXT NOT NULL,
    setup_minutes  REAL NULL,
    run_minutes    REAL NULL,
    required_skill TEXT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

COVERAGES_DDL = """
CREATE TABLE IF NOT EXISTS sla_coverages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    org_id      INTEGER NULL,
    calendar_id INTEGER NULL,
    start_date  TEXT NULL,
    end_date    TEXT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

COVERAGE_RULES_DDL = """
CREATE TABLE IF NOT EXISTS sla_coverage_rules (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    coverage_id               INTEGER NOT NULL,
    severity                  TEXT NOT NULL,
    channel                   TEXT NULL,
    first_response_minutes    INTEGER NOT NULL,
    first_response_warn_minutes INTEGER NULL,
    resolution_minutes        INTEGER NOT NULL,
    resolution_warn_minutes   INTEGER NULL,
    seq                       INTEGER NOT NULL DEFAULT 1,
    created_at                TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

MILESTONES_DDL = """
CREATE TABLE IF NOT EXISTS sla_milestones (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id        INTEGER NOT NULL,
    milestone_type       TEXT NOT NULL,
    state                TEXT NOT NULL DEFAULT 'Pending',
    due_at               TEXT NULL,
    warn_at              TEXT NULL,
    started_at           TEXT NULL,
    paused_total_minutes INTEGER NOT NULL DEFAULT 0,
    completed_at         TEXT NULL,
    warned_at            TEXT NULL,
    breached_at          TEXT NULL,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS service_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL,
    event_type    TEXT NOT NULL,
    occurred_at   TEXT NOT NULL,
    actor         TEXT NULL,
    payload       TEXT NULL,
    note          TEXT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

TABLES = (
    (WORK_ORDERS_TABLE, WORK_ORDERS_DDL),
    (OPERATIONS_TABLE, OPERATIONS_DDL),
    (COVERAGES_TABLE, COVERAGES_DDL),
    (COVERAGE_RULES_TABLE, COVERAGE_RULES_DDL),
    (MILESTONES_TABLE, MILESTONES_DDL),
    (EVENTS_TABLE, EVENTS_DDL),
)

INDEXES = (
    ('uq_work_order_no',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uq_work_order_no '
     f'ON {WORK_ORDERS_TABLE}(work_order_no)'),
    ('idx_work_order_schedule',
     f'CREATE INDEX IF NOT EXISTS idx_work_order_schedule '
     f'ON {WORK_ORDERS_TABLE}(schedule_id)'),
    ('idx_work_order_status',
     f'CREATE INDEX IF NOT EXISTS idx_work_order_status '
     f'ON {WORK_ORDERS_TABLE}(status)'),
    ('idx_work_order_operation_work_order',
     f'CREATE INDEX IF NOT EXISTS idx_work_order_operation_work_order '
     f'ON {OPERATIONS_TABLE}(work_order_id)'),
    ('uq_work_order_operation_seq',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uq_work_order_operation_seq '
     f'ON {OPERATIONS_TABLE}(work_order_id, seq)'),
    ('idx_sla_coverage_org',
     f'CREATE INDEX IF NOT EXISTS idx_sla_coverage_org '
     f'ON {COVERAGES_TABLE}(org_id)'),
    ('idx_sla_coverage_active',
     f'CREATE INDEX IF NOT EXISTS idx_sla_coverage_active '
     f'ON {COVERAGES_TABLE}(active)'),
    ('idx_sla_coverage_rule_coverage',
     f'CREATE INDEX IF NOT EXISTS idx_sla_coverage_rule_coverage '
     f'ON {COVERAGE_RULES_TABLE}(coverage_id)'),
    ('uq_sla_coverage_rule',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uq_sla_coverage_rule '
     f'ON {COVERAGE_RULES_TABLE}(coverage_id, severity, channel)'),
    ('idx_sla_milestone_work_order',
     f'CREATE INDEX IF NOT EXISTS idx_sla_milestone_work_order '
     f'ON {MILESTONES_TABLE}(work_order_id)'),
    ('uq_sla_milestone',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uq_sla_milestone '
     f'ON {MILESTONES_TABLE}(work_order_id, milestone_type)'),
    ('idx_service_event_work_order',
     f'CREATE INDEX IF NOT EXISTS idx_service_event_work_order '
     f'ON {EVENTS_TABLE}(work_order_id, occurred_at)'),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v161] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v161] 开始: 服务工单 / SLA 地基')

        for name, ddl in TABLES:
            if _table_exists(conn, name):
                print(f'  - [SKIP] 表 {name} 已存在')
            else:
                conn.execute(ddl)
                print(f'  - [CREATE] 表 {name}')

        for name, sql in INDEXES:
            if _index_exists(conn, name):
                print(f'  - [SKIP] 索引 {name} 已存在')
            else:
                conn.execute(sql)
                print(f'  - [ADD] 索引 {name}')

        conn.commit()
        print('[v161] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v161] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v161 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_columns = {
            WORK_ORDERS_TABLE: (
                'work_order_no', 'order_type', 'schedule_id', 'order_id',
                'order_line_id', 'severity', 'channel', 'status', 'coverage_id',
                'asset_ref', 'opened_at', 'first_response_at', 'resolved_at',
                'closed_at'),
            OPERATIONS_TABLE: (
                'work_order_id', 'seq', 'work_center_id', 'operation_name',
                'setup_minutes', 'run_minutes', 'required_skill', 'status'),
            COVERAGES_TABLE: (
                'name', 'org_id', 'calendar_id', 'start_date', 'end_date', 'active'),
            COVERAGE_RULES_TABLE: (
                'coverage_id', 'severity', 'channel', 'first_response_minutes',
                'first_response_warn_minutes', 'resolution_minutes',
                'resolution_warn_minutes', 'seq'),
            MILESTONES_TABLE: (
                'work_order_id', 'milestone_type', 'state', 'due_at', 'warn_at',
                'started_at', 'paused_total_minutes', 'completed_at', 'warned_at',
                'breached_at'),
            EVENTS_TABLE: (
                'work_order_id', 'event_type', 'occurred_at', 'actor', 'payload',
                'note'),
        }

        for table, columns in required_columns.items():
            if not _table_exists(conn, table):
                print('[v161 verify] FAIL: 缺表 %s' % table)
                ok = False
                continue
            have = _columns(conn, table)
            for col in columns:
                if col not in have:
                    print('[v161 verify] FAIL: 缺列 %s.%s' % (table, col))
                    ok = False

        for name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v161 verify] FAIL: 缺索引 %s' % name)
                ok = False

        print('[v161 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v161 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')
            else:
                print(f'  - [SKIP] 索引 {name} 不存在')

        # 先删子表，再删父表（语义上的父子关系）
        for table in (EVENTS_TABLE, MILESTONES_TABLE, COVERAGE_RULES_TABLE,
                      COVERAGES_TABLE, OPERATIONS_TABLE, WORK_ORDERS_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')
            else:
                print(f'  - [SKIP] 表 {table} 不存在')

        conn.commit()
        print('[v161 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v161 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)
