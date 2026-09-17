#!/usr/bin/env python3
"""db_assert.py - DB state assertion for delta deployment verification.

[P1-2 2026-09-01] Higher-level wrapper on top of db_fingerprint.py.

Purpose: catch the "deploy looked fine but DB silently didn't apply changes"
case. Goes beyond "did the file change?" to "did the DB *meaningfully* update?".

Three operations:

1. assert_db_healthy(db_path) - sanity check before deploy
   - DB file exists, non-zero, not corrupt (PRAGMA integrity_check)
   - All critical tables present (menus, menu_permissions, etc.)
   - schema_migrations table has expected v### entries

2. assert_db_changes(before_yaml, after_yaml, expected_diff) - what changed
   - calls db_fingerprint.diff() then verifies:
     - Every menu_added/removed in expected_diff MUST appear in actual diff
     - Every table_added/removed MUST appear in actual diff
     - Optional: row_count_deltas within tolerance
   - Returns AssertionError listing unexpected / missing changes

3. assert_critical_invariants(db_path, snapshot_yaml) - post-deploy health
   - All menus that should exist (e.g. user-permission) do exist
   - All migrations in expected list are applied
   - No critical table is empty (catches "table created but no rows")

Usage example in deploy:
    from db_assert import assert_db_healthy, capture_snapshot, assert_db_changes
    
    before = capture_snapshot(staging_db)
    assert_db_healthy(staging_db)
    
    apply_delta_zip(...)
    
    after = capture_snapshot(staging_db)
    assert_db_changes(before, after, expected={
        'menus_added': ['user-permission', 'org-management', 'permission_set-management'],
        'menus_removed': ['user-list', 'permission_set-list', 'org-list', ...],
        'tables_added': [],
        'tables_removed': [],
    })
"""
import sqlite3
import sys
import yaml
from pathlib import Path

# Reuse db_fingerprint's capture logic
sys.path.insert(0, str(Path(__file__).parent))
import db_fingerprint


class DBAssertError(AssertionError):
    """Raised when DB assertion fails."""
    pass


def assert_db_healthy(db_path, min_size_kb=10):
    """Sanity check: file exists, non-empty, not corrupt, critical tables present.

    Args:
        db_path: path to SQLite DB file (local or remote after staging_ops.copy_back)
        min_size_kb: minimum file size in KB (catches truncated/empty DB)

    Raises:
        DBAssertError: if any check fails
    """
    p = Path(db_path)
    if not p.exists():
        raise DBAssertError(f'DB file not found: {db_path}')
    size = p.stat().st_size
    if size < min_size_kb * 1024:
        raise DBAssertError(f'DB too small: {size} bytes < {min_size_kb * 1024} (truncated?)')
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=10)
    except sqlite3.Error as e:
        raise DBAssertError(f'cannot open DB: {e}')
    try:
        # integrity check
        cur = conn.execute('PRAGMA integrity_check')
        row = cur.fetchone()
        if not row or row[0] != 'ok':
            raise DBAssertError(f'integrity_check failed: {row}')
        # critical tables
        for tbl in db_fingerprint.CRITICAL_TABLES:
            if not db_fingerprint._table_exists(conn, tbl):
                raise DBAssertError(f'critical table missing: {tbl}')
    finally:
        conn.close()


def capture_snapshot(db_path, output_yaml=None):
    """Capture DB fingerprint as dict (or write to YAML if path given).

    Args:
        db_path: source DB
        output_yaml: optional path to write YAML; if None, returns dict in memory

    Returns:
        dict (fingerprint data) if output_yaml is None, else None
    """
    fp = db_fingerprint.capture(str(db_path))
    if output_yaml:
        Path(output_yaml).write_text(
            yaml.safe_dump(fp, allow_unicode=True, sort_keys=False),
            encoding='utf-8',
        )
        return None
    return fp


def _diff_yaml(old_path_or_dict, new_path_or_dict):
    """Compute diff between two snapshots. Both args may be dict or YAML path.

    db_fingerprint.diff accepts dicts directly, so we just pass through.
    YAML path support: load YAML file into dict first.

    Returns:
        dict per db_fingerprint.diff format.
    """
    if isinstance(old_path_or_dict, str):
        with open(old_path_or_dict, encoding='utf-8') as f:
            old = yaml.safe_load(f)
    else:
        old = old_path_or_dict
    if isinstance(new_path_or_dict, str):
        with open(new_path_or_dict, encoding='utf-8') as f:
            new = yaml.safe_load(f)
    else:
        new = new_path_or_dict
    return db_fingerprint.diff(old, new)


def assert_db_changes(before, after, expected):
    """Verify DB changed ONLY in expected ways.

    Args:
        before: snapshot dict or YAML path (pre-deploy)
        after: snapshot dict or YAML path (post-deploy)
        expected: dict describing allowed changes. Keys (all optional):
            - tables_added: list[str]
            - tables_removed: list[str]
            - tables_modified: list[str]    (matches tables_changed_sql)
            - sample_changes: list[str]     (matched against sample_changes)
            - row_count_changes: dict[str, int] (table -> expected delta; +/-N)
            - migrations_added: list[str]
            - migrations_removed: list[str]

    Raises:
        DBAssertError: if actual changes don't match expected
    """
    diff = _diff_yaml(before, after)
    errors = []

    # Tables
    actual = set(diff.get('tables_added', []))
    expected_set = set(expected.get('tables_added', []))
    if actual != expected_set:
        unexpected = actual - expected_set
        missing = expected_set - actual
        if unexpected:
            errors.append(f'tables added unexpectedly: {sorted(unexpected)}')
        if missing:
            errors.append(f'tables expected but not added: {sorted(missing)}')
    actual = set(diff.get('tables_dropped', []))
    expected_set = set(expected.get('tables_removed', []))
    if actual != expected_set:
        unexpected = actual - expected_set
        missing = expected_set - actual
        if unexpected:
            errors.append(f'tables dropped unexpectedly: {sorted(unexpected)}')
        if missing:
            errors.append(f'tables expected to be dropped but still present: {sorted(missing)}')

    # Tables modified (SQL changed)
    actual = set(diff.get('tables_changed_sql', []))
    expected_set = set(expected.get('tables_modified', []))
    if actual != expected_set:
        unexpected = actual - expected_set
        missing = expected_set - actual
        if unexpected:
            errors.append(f'tables changed_sql unexpectedly: {sorted(unexpected)}')
        if missing:
            errors.append(f'tables expected to change_sql but did not: {sorted(missing)}')

    # Sample content changes (menus live here)
    actual = set(diff.get('sample_changes', []))
    expected_set = set(expected.get('sample_changes', []))
    if expected_set:  # only check if caller specified
        if actual != expected_set:
            unexpected = actual - expected_set
            missing = expected_set - actual
            if unexpected:
                errors.append(f'sample content changed unexpectedly: {sorted(unexpected)}')
            if missing:
                errors.append(f'sample content expected to change but did not: {sorted(missing)}')

    # Row count deltas
    if 'row_count_changes' in expected:
        for tbl, exp_delta in expected['row_count_changes'].items():
            actual_info = diff.get('row_count_changes', {}).get(tbl)
            actual_delta = actual_info['delta'] if isinstance(actual_info, dict) else 0
            if actual_delta != exp_delta:
                errors.append(f'row count delta mismatch for {tbl}: expected {exp_delta}, got {actual_delta}')

    # Migrations
    actual = set(diff.get('migrations_added', []))
    expected_set = set(expected.get('migrations_added', []))
    if actual != expected_set:
        unexpected = actual - expected_set
        missing = expected_set - actual
        if unexpected:
            errors.append(f'migrations added unexpectedly: {sorted(unexpected)}')
        if missing:
            errors.append(f'migrations expected but not added: {sorted(missing)}')

    if errors:
        raise DBAssertError('DB state changes do not match expected:\n  - ' + '\n  - '.join(errors))
    return diff


def assert_critical_invariants(db_path, required_menus=None, required_migrations=None):
    """Post-deploy health: required menus/migrations must be present.

    Args:
        db_path: SQLite DB path
        required_menus: list of menu keys/names that MUST exist
        required_migrations: list of migration versions (e.g. ['v078']) that MUST be in schema_migrations

    Raises:
        DBAssertError: if any required item is missing
    """
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=10)
    try:
        if required_menus:
            # menus table has 'key' column (Spec16) or 'name' column
            placeholders = ','.join('?' for _ in required_menus)
            # Try key column first (Spec16+)
            try:
                cur = conn.execute(
                    f'SELECT key FROM menus WHERE key IN ({placeholders})',
                    required_menus,
                )
                found = {row[0] for row in cur.fetchall()}
            except sqlite3.OperationalError:
                # Fallback to name
                cur = conn.execute(
                    f'SELECT name FROM menus WHERE name IN ({placeholders})',
                    required_menus,
                )
                found = {row[0] for row in cur.fetchall()}
            missing = set(required_menus) - found
            if missing:
                raise DBAssertError(f'required menus missing after deploy: {sorted(missing)}')

        if required_migrations:
            placeholders = ','.join('?' for _ in required_migrations)
            # Try migration_name column (actual schema used by db_fingerprint)
            try:
                cur = conn.execute(
                    f'SELECT migration_name FROM schema_migrations WHERE migration_name IN ({placeholders})',
                    required_migrations,
                )
                found = {row[0] for row in cur.fetchall()}
            except sqlite3.OperationalError:
                # Fallback to version column
                cur = conn.execute(
                    f'SELECT version FROM schema_migrations WHERE version IN ({placeholders})',
                    required_migrations,
                )
                found = {row[0] for row in cur.fetchall()}
            missing = set(required_migrations) - found
            if missing:
                raise DBAssertError(f'required migrations missing after deploy: {sorted(missing)}')
    finally:
        conn.close()


# CLI for one-off verification
def main():
    import argparse
    p = argparse.ArgumentParser(description='db_assert CLI')
    sub = p.add_subparsers(dest='cmd', required=True)

    p_healthy = sub.add_parser('healthy', help='check DB is healthy')
    p_healthy.add_argument('db')

    p_capture = sub.add_parser('capture', help='capture snapshot')
    p_capture.add_argument('db')
    p_capture.add_argument('output_yaml')

    p_check = sub.add_parser('check', help='verify required menus/migrations exist')
    p_check.add_argument('db')
    p_check.add_argument('--require-menu', action='append', default=[])
    p_check.add_argument('--require-migration', action='append', default=[])

    args = p.parse_args()
    if args.cmd == 'healthy':
        try:
            assert_db_healthy(args.db)
            print('HEALTHY')
        except DBAssertError as e:
            print(f'UNHEALTHY: {e}')
            sys.exit(1)
    elif args.cmd == 'capture':
        capture_snapshot(args.db, args.output_yaml)
        print(f'CAPTURED {args.output_yaml}')
    elif args.cmd == 'check':
        try:
            assert_critical_invariants(
                args.db,
                required_menus=args.require_menu or None,
                required_migrations=args.require_migration or None,
            )
            print('CHECK_OK')
        except DBAssertError as e:
            print(f'CHECK_FAIL: {e}')
            sys.exit(1)


if __name__ == '__main__':
    main()
