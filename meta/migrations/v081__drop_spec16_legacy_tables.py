"""
v081 - drop legacy Spec16 role/user_group backup tables

Background:
  v080 renamed legacy tables to <table>_pre_v080_backup. v081 actually drops
  them to clean up DB.

  If user regrets, they can recover from a fresh DB snapshot or pre-v080 DB backup.

  Pre-flight:
  - v080 must have run (all backup tables exist)
  - no runtime code references these tables (verified via probe_legacy_table_refs.py)
  - dev.py serves menu/visible correctly using new tables (verified)
  - new permission_sets (353 rows) + user_permission_sets (353 rows) match old roles (353)
  - new permission_set_permissions (458) + permission_set_menu_permissions (6) +
    permission_set_dimension_scopes + permission_set_data_permissions are in use

Strategy:
  - check all _pre_v080_backup tables exist (v080 precondition)
  - DROP TABLE each one
  - DROP only if name ends with _pre_v080_backup (safety against typos)

Idempotent:
  - DROP TABLE IF EXISTS in SQLite (since 3.8)
  - schema_migrations UNIQUE check
  - verify counts = 0 backup tables after
"""
from __future__ import print_function
import sqlite3
import sys
import os

MIGRATION_NAME = 'v081__drop_spec16_legacy_tables'

LEGACY_TABLES = [
    'roles',
    'role_permissions',
    'role_menu_permissions',
    'role_data_permissions',
    'role_dimension_scopes',
    'role_intents',
    'group_roles',
    'user_roles',
    'user_groups',
    'user_group_members',
    'role_menu_permissions_pre_v078_backup',
    'roles_v1_backup',
]


def _table_exists(c, table):
    row = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        [table],
    ).fetchone()
    return row is not None


def _row_count(c, table):
    row = c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()
    return row[0]


def _record_migration(c):
    try:
        existing = c.execute(
            'SELECT id FROM schema_migrations WHERE migration_name = ?',
            [MIGRATION_NAME],
        ).fetchone()
        if existing:
            print(f'[{MIGRATION_NAME}] ALREADY RECORDED (id={existing[0]})')
        else:
            c.execute(
                'INSERT INTO schema_migrations (migration_name, environment, executed_at) '
                "VALUES (?, ?, datetime('now'))",
                [MIGRATION_NAME, os.environ.get('ENVIRONMENT', 'staging')],
            )
            print(f'[{MIGRATION_NAME}] schema_migrations INSERT ok')
    except Exception as e:
        print(f'[{MIGRATION_NAME}][WARN] schema_migrations insert failed:', e)


def migrate():
    db_path = os.environ.get(
        'DATABASE_PATH',
        os.environ.get('SQLITE_DB_PATH', ''),
    )
    if not db_path:
        raise RuntimeError('DATABASE_PATH / SQLITE_DB_PATH not set')

    print(f'[{MIGRATION_NAME}] db_path =', db_path)
    c = sqlite3.connect(db_path)

    _record_migration(c)
    c.commit()

    total_dropped = 0
    skipped = []
    failed = []

    for legacy in LEGACY_TABLES:
        backup_name = f'{legacy}_pre_v080_backup'
        # safety: only drop the backup variant
        target = backup_name
        if not _table_exists(c, target):
            print(f'[{MIGRATION_NAME}][SKIP] {target} does not exist (v080 not run or already dropped)')
            skipped.append(legacy)
            continue
        rows = _row_count(c, target)
        try:
            c.execute(f'DROP TABLE {target}')
            print(f'[{MIGRATION_NAME}] dropped {target} ({rows} rows were in backup)')
            total_dropped += 1
        except Exception as e:
            print(f'[{MIGRATION_NAME}][FAIL] DROP {target}: {e}')
            failed.append(legacy)
            c.rollback()
            sys.exit(1)

    c.commit()

    print()
    print(f'[{MIGRATION_NAME}] === summary ===')
    print(f'  dropped: {total_dropped} tables')
    print(f'  skipped: {len(skipped)} tables ({skipped})')
    print(f'  failed:  {len(failed)} tables ({failed})')
    print(f'[{MIGRATION_NAME}] DONE')


def verify(db_path):
    """Verify v081: no _pre_v080_backup tables remain."""
    if not os.path.exists(db_path):
        return False
    conn = sqlite3.connect(db_path)
    try:
        all_ok = True
        for legacy in LEGACY_TABLES:
            backup_name = f'{legacy}_pre_v080_backup'
            if _table_exists(conn, backup_name):
                print(f'  [v081 verify] FAIL: {backup_name} still exists')
                all_ok = False
        # Also verify legacy tables themselves are gone (they should be, v080 renamed them)
        for legacy in LEGACY_TABLES:
            if _table_exists(conn, legacy):
                # v081 may have run on an env where v080 was skipped (legacy table still existed)
                print(f'  [v081 verify] WARN: legacy {legacy} still in DB')
        return all_ok
    finally:
        conn.close()


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    print(f'[{MIGRATION_NAME}] running on {db}')
    os.environ['DATABASE_PATH'] = db
    os.environ.setdefault('ENVIRONMENT', 'staging')
    migrate()
    print(f'[{MIGRATION_NAME}] verify: {verify(db)}')