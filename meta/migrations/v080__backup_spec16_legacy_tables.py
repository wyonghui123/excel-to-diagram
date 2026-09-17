"""
v080 - backup legacy Spec16 role/user_group tables before drop

Background:
  Spec16 Plan D (2026-09-01) renamed roles -> permission_sets, user_groups -> orgs.
  v070 + v077 renamed tables + columns. But 12 legacy tables still exist as dead weight:
    - roles                     (now permission_sets, 353 rows)
    - role_permissions          (now permission_set_permissions, 458 rows)
    - role_menu_permissions     (now permission_set_menu_permissions)
    - role_data_permissions     (already empty in new table)
    - role_dimension_scopes     (now permission_set_dimension_scopes)
    - role_intents              (legacy intents, was never refactored)
    - group_roles               (now org_permission_sets, 22 rows)
    - user_roles                (now user_permission_sets, 353 rows)
    - user_groups               (now orgs, 45 rows)
    - user_group_members        (now org_members, 45 rows)
    - role_menu_permissions_pre_v078_backup (v078 backup table)
    - roles_v1_backup           (v1 backup table)

After this v080 backup, v081 will DROP these 12 tables.

Strategy:
  - backup: rename each legacy table to <table>_pre_v080_backup
  - this preserves the schema + data 1:1 (no data loss)
  - verify: count rows in old vs new table, should match within tolerance
  - downgrade: rename backup tables back to original name

Idempotent:
  - rename_table fails if target exists; check first + skip if already done
  - schema_migrations: INSERT with UNIQUE constraint, catch duplicate
  - verify checks backup table exists for every legacy table
"""
from __future__ import print_function
import sqlite3
import sys
import os

MIGRATION_NAME = 'v080__backup_spec16_legacy_tables'

# Triggers that reference legacy tables - drop them BEFORE renaming legacy tables
# (SQLite ALTER TABLE RENAME fails if any trigger references the renamed table's columns)
LEGACY_TRIGGERS = [
    'cascade_delete_org_from_org_permission_sets',       # ON orgs -> DELETE FROM group_roles
    'cascade_delete_permission_set_from_org_permission_sets',  # ON permission_sets -> DELETE FROM group_roles (also buggy: column name is wrong)
]

# (legacy_table, expected_data_in_new_table_for_sanity)
# If new_table is None, we don't validate (legacy table may have no replacement)
LEGACY_TABLES = [
    ('roles', 'permission_sets'),
    ('role_permissions', 'permission_set_permissions'),
    ('role_menu_permissions', 'permission_set_menu_permissions'),
    ('role_data_permissions', 'permission_set_data_permissions'),
    ('role_dimension_scopes', 'permission_set_dimension_scopes'),
    ('role_intents', None),  # legacy intents table, no direct replacement
    ('group_roles', 'org_permission_sets'),
    ('user_roles', 'user_permission_sets'),
    ('user_groups', 'orgs'),
    ('user_group_members', 'org_members'),
    ('role_menu_permissions_pre_v078_backup', None),  # v078 backup, no replacement
    ('roles_v1_backup', None),  # v1 backup, no replacement
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

    # 0.5 DROP legacy triggers that reference legacy tables
    # (SQLite ALTER TABLE RENAME fails if any trigger references the renamed table's columns)
    triggers_dropped = 0
    for trig in LEGACY_TRIGGERS:
        row = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
            [trig],
        ).fetchone()
        if not row:
            print(f'[{MIGRATION_NAME}] trigger {trig} not found, skip drop')
            continue
        try:
            c.execute(f'DROP TRIGGER {trig}')
            print(f'[{MIGRATION_NAME}] dropped trigger: {trig}')
            triggers_dropped += 1
        except Exception as e:
            print(f'[{MIGRATION_NAME}][FAIL] drop trigger {trig}: {e}')
            c.rollback()
            sys.exit(1)
    c.commit()
    print(f'[{MIGRATION_NAME}] dropped {triggers_dropped} legacy triggers')

    total_backed_up = 0
    skipped = []
    failed = []

    for legacy, new_table in LEGACY_TABLES:
        backup_name = f'{legacy}_pre_v080_backup'

        # check legacy table
        if not _table_exists(c, legacy):
            print(f'[{MIGRATION_NAME}][SKIP] {legacy} does not exist (already dropped)')
            skipped.append(legacy)
            continue

        # check backup already exists (idempotent)
        if _table_exists(c, backup_name):
            print(f'[{MIGRATION_NAME}][SKIP] {backup_name} already exists (already backed up)')
            skipped.append(legacy)
            continue

        # row count sanity
        legacy_rows = _row_count(c, legacy)
        if new_table and _table_exists(c, new_table):
            new_rows = _row_count(c, new_table)
            # new table should have >= legacy (might have more if data was added post-rename)
            if new_rows < legacy_rows:
                print(f'[{MIGRATION_NAME}][WARN] {legacy}({legacy_rows}) > {new_table}({new_rows})')
                print(f'  data may have been added to legacy table after rename')
                # not blocking, just warning

        try:
            # rename to backup (preserves schema + data)
            c.execute(f'ALTER TABLE {legacy} RENAME TO {backup_name}')
            print(f'[{MIGRATION_NAME}] renamed {legacy} -> {backup_name} ({legacy_rows} rows)')
            total_backed_up += 1
        except Exception as e:
            print(f'[{MIGRATION_NAME}][FAIL] rename {legacy}: {e}')
            failed.append(legacy)
            c.rollback()
            sys.exit(1)

    c.commit()

    print()
    print(f'[{MIGRATION_NAME}] === summary ===')
    print(f'  backed up: {total_backed_up} tables')
    print(f'  skipped:   {len(skipped)} tables ({skipped})')
    print(f'  failed:    {len(failed)} tables ({failed})')
    print(f'[{MIGRATION_NAME}] DONE (next step: run v081 to DROP backup tables)')


def verify(db_path):
    """Verify v080: all legacy tables renamed to _pre_v080_backup variants."""
    if not os.path.exists(db_path):
        return False
    conn = sqlite3.connect(db_path)
    try:
        all_ok = True
        for legacy, _ in LEGACY_TABLES:
            backup_name = f'{legacy}_pre_v080_backup'
            # OK if legacy GONE OR backup exists OR legacy didn't exist originally
            legacy_exists = _table_exists(conn, legacy)
            backup_exists = _table_exists(conn, backup_name)
            if legacy_exists and not backup_exists:
                print(f'  [v080 verify] FAIL: {legacy} still exists without backup')
                all_ok = False
            elif backup_exists:
                rows = _row_count(conn, backup_name)
                print(f'  [v080 verify] OK: {backup_name} ({rows} rows)')
        return all_ok
    finally:
        conn.close()


def downgrade(db_path):
    """v080 downgrade: rename backup tables back to original names."""
    conn = sqlite3.connect(db_path)
    try:
        for legacy, _ in LEGACY_TABLES:
            backup_name = f'{legacy}_pre_v080_backup'
            if not _table_exists(conn, backup_name):
                continue
            if _table_exists(conn, legacy):
                print(f'  [v080 downgrade] WARN: {legacy} already exists, skip restore')
                continue
            conn.execute(f'ALTER TABLE {backup_name} RENAME TO {legacy}')
            print(f'  [v080 downgrade] restored {backup_name} -> {legacy}')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'  [v080 downgrade] FAIL: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    print(f'[{MIGRATION_NAME}] running on {db}')
    os.environ['DATABASE_PATH'] = db
    os.environ.setdefault('ENVIRONMENT', 'staging')
    migrate()
    print(f'[{MIGRATION_NAME}] verify: {verify(db)}')