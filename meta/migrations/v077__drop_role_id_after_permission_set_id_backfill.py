"""
v077 - Drop role_id columns + backfill permission_set_id (spec16 rename completion)

Background:
  v070 renamed `roles` table -> `permission_sets`, `role_permissions` -> `permission_set_permissions`,
  `user_permission_sets` <- `user_roles`. But v070 did NOT rename the column `role_id` inside these tables.
  Later migrations added `permission_set_id` column. Now staging has both columns, with real data in
  `role_id` and `permission_set_id` IS NULL. This migration:

    1. Backfills permission_set_id from role_id where NULL.
    2. Drops the legacy role_id column from these tables (no longer needed).
    3. Records itself in schema_migrations.

Idempotent:
  - backfill: UPDATE WHERE permission_set_id IS NULL AND role_id IS NOT NULL
  - drop column: PRAGMA table_info check + ALTER TABLE DROP COLUMN (sqlite >= 3.35)
  - schema_migrations: INSERT with UNIQUE constraint, catch duplicate

Safe to re-run.
"""
from __future__ import print_function
import sqlite3
import sys
import os

MIGRATION_NAME = 'v077__drop_role_id_after_permission_set_id_backfill'

# Tables to migrate: (table_name, list_of_drop_columns)
TABLES = [
    ('permission_set_dimension_scopes', ['role_id']),
    ('data_permission_rules', ['role_id']),
    ('permission_rules', ['role_id']),
]


def _has_column(c, table, column):
    rows = c.execute('PRAGMA table_info({})'.format(table)).fetchall()
    return any(r[1] == column for r in rows)


def _column_count(c, table):
    rows = c.execute('PRAGMA table_info({})'.format(table)).fetchall()
    return len(rows)


def _null_count(c, table, col):
    row = c.execute(
        'SELECT COUNT(*) FROM {} WHERE {} IS NULL'.format(table, col)
    ).fetchone()
    return row[0]


def migrate():
    db_path = os.environ.get(
        'DATABASE_PATH',
        os.environ.get('SQLITE_DB_PATH', ''),
    )
    if not db_path:
        raise RuntimeError('DATABASE_PATH / SQLITE_DB_PATH not set')

    print('[v077] db_path =', db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row

    # 0. record migration (skip if exists, for idempotency)
    try:
        existing = c.execute(
            'SELECT id FROM schema_migrations WHERE migration_name = ?',
            [MIGRATION_NAME],
        ).fetchone()
        if existing:
            print('[v077] ALREADY RECORDED (id={}), running steps anyway for safety'.format(existing['id']))
        else:
            c.execute(
                'INSERT INTO schema_migrations (migration_name, environment, executed_at) VALUES (?, ?, datetime("now"))',
                [MIGRATION_NAME, os.environ.get('ENVIRONMENT', 'staging')],
            )
            print('[v077] schema_migrations INSERT ok')
    except Exception as e:
        print('[v077][WARN] schema_migrations insert failed (table may not exist):', e)

    for table, drop_cols in TABLES:
        print()
        print('[v077] === table:', table, '===')

        # check existence
        try:
            table_exists = c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                [table],
            ).fetchone()
        except Exception as e:
            print('[v077][SKIP] cannot check existence:', e)
            continue
        if not table_exists:
            print('[v077][SKIP] table does not exist:', table)
            continue

        # 1. backfill permission_set_id from role_id (where NULL)
        if _has_column(c, table, 'permission_set_id') and _has_column(c, table, 'role_id'):
            null_before = _null_count(c, table, 'permission_set_id')
            print('[v077] permission_set_id NULL count before:', null_before)
            cur = c.execute(
                'UPDATE {} SET permission_set_id = role_id '
                'WHERE permission_set_id IS NULL AND role_id IS NOT NULL'.format(table)
            )
            print('[v077] UPDATE backfilled rows:', cur.rowcount)
            null_after = _null_count(c, table, 'permission_set_id')
            print('[v077] permission_set_id NULL count after:', null_after)
            if null_after > 0:
                print('[v077][FAIL] still has NULL permission_set_id after backfill, refusing to DROP role_id')
                c.close()
                sys.exit(1)
        else:
            print('[v077][NOTE] permission_set_id or role_id not both present in', table)

        # 2. drop role_id column(s)
        for col in drop_cols:
            if not _has_column(c, table, col):
                print('[v077][NOTE] column already dropped:', table, col)
                continue
            try:
                c.execute('ALTER TABLE {} DROP COLUMN {}'.format(table, col))
                print('[v077] DROPPED column:', table, col)
            except Exception as e:
                print('[v077][FAIL] DROP COLUMN failed:', table, col, e)
                c.close()
                sys.exit(1)

        # 3. final cols
        cols = [r[1] for r in c.execute('PRAGMA table_info({})'.format(table)).fetchall()]
        print('[v077] final cols:', cols)

    c.commit()
    c.close()
    print()
    print('[v077] DONE')


if __name__ == '__main__':
    migrate()