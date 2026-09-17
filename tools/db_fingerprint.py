#!/usr/bin/env python3
"""db_fingerprint.py - capture/compare SQLite schema + critical data fingerprints.
#
# [P0-5 2026-09-01] B1 fix: delta tool previously only saw file-level SHA256 changes,
# missing DB schema/menu/permission changes that happen via init_*.py scripts.
#
# Usage:
#   python db_fingerprint.py capture <DB_PATH> <OUTPUT_YAML>
#   python db_fingerprint.py diff <OLD_YAML> <NEW_YAML> [--sql-output]
#   python db_fingerprint.py verify <DB_PATH> <EXPECTED_YAML> [--strict]
#
# Examples:
#   python db_fingerprint.py capture meta/architecture.db db_state_localhost.yaml
#   python db_fingerprint.py capture /opt/app/staging/meta/architecture.db db_state_staging.yaml
#   python db_fingerprint.py diff db_state_localhost.yaml db_state_staging.yaml
#
# What gets fingerprinted:
#   1. Tables (CREATE TABLE SQL hash)
#   2. Indexes (CREATE INDEX SQL hash)
#   3. Critical table ROW COUNTS (menus, menu_permissions, role_menu_permissions, permissions, roles)
#   4. CRITICAL TABLE DATA SAMPLES (top N rows by primary key for menus/menu_permissions)
#   5. Migration history (which v### migrations have been applied)
#
# What does NOT get fingerprinted (too much noise):
#   - Audit logs (constantly changing)
#   - Sessions/tokens (volatile)
#   - Timestamps
"""
import sqlite3
import yaml
import hashlib
import sys
import argparse
from pathlib import Path


# Critical tables to fingerprint row counts for (must be tracked for delta detection)
CRITICAL_TABLES = [
    'menus',
    'menu_permissions',
    'role_menu_permissions',
    'permission_sets',
    'permissions',
    'orgs',
    'org_permission_sets',
    'org_functions',
    'users',
    'schema_migrations',
]

# Tables to sample for content fingerprint (top 50 rows by id)
SAMPLE_TABLES = ['menus', 'menu_permissions', 'permission_sets']
SAMPLE_LIMIT = 50


def _table_exists(conn, name):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _table_sql(conn, name):
    """Return the CREATE TABLE SQL (or None if table doesn't exist)."""
    cur = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,))
    row = cur.fetchone()
    return row[0] if row else None


def _all_indexes(conn):
    """Return list of (name, sql) for all indexes."""
    cur = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name")
    return [(r[0], r[1]) for r in cur.fetchall()]


def _row_count(conn, table):
    if not _table_exists(conn, table):
        return -1  # sentinel for missing table
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def _table_sample(conn, table, limit):
    """Return first N rows as list of tuples for content fingerprint.

    For menus/menu_permissions, sample both:
    - Top 50 by id (general state)
    - All rows where parent_menu='user-permission' (critical for spec16 Plan D)
    """
    if not _table_exists(conn, table):
        return None
    try:
        # Try with id column; fallback to rowid
        cur = conn.execute(f"SELECT * FROM {table} ORDER BY id LIMIT {limit}")
        cols = [d[0] for d in cur.description]
        rows = [list(r) for r in cur.fetchall()]

        # For menu-like tables, also sample under user-permission hub
        if table in ('menus', 'menu_permissions') and 'parent_menu' in cols:
            try:
                cur2 = conn.execute(
                    f"SELECT * FROM {table} WHERE parent_menu='user-permission' LIMIT {limit}"
                )
                cols2 = [d[0] for d in cur2.description]
                rows.extend(list(r) for r in cur2.fetchall())
            except Exception:
                pass

        return cols, rows
    except Exception:
        cur = conn.execute(f"SELECT * FROM {table} WHERE rowid IN (SELECT rowid FROM {table} ORDER BY rowid LIMIT {limit})")
        cols = [d[0] for d in cur.description]
        return cols, [list(r) for r in cur.fetchall()]


def _migrations_applied(conn):
    """Return list of applied migration names from schema_migrations."""
    if not _table_exists(conn, 'schema_migrations'):
        return []
    cur = conn.execute("SELECT migration_name FROM schema_migrations ORDER BY id")
    return [r[0] for r in cur.fetchall()]


def _hash_text(text):
    return hashlib.sha256(text.encode('utf-8', errors='replace')).hexdigest()[:16]


def capture(db_path):
    """Capture fingerprint of a SQLite database."""
    if not Path(db_path).exists():
        print(f'[ERROR] DB not found: {db_path}')
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    try:
        # 1. Tables
        tables = {}
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        for (name,) in cur.fetchall():
            sql = _table_sql(conn, name)
            tables[name] = {
                'sql': sql,
                'sql_sha': _hash_text(sql) if sql else None,
            }

        # 2. Indexes
        indexes = {}
        for name, sql in _all_indexes(conn):
            indexes[name] = {
                'sql': sql,
                'sql_sha': _hash_text(sql),
            }

        # 3. Row counts for critical tables
        row_counts = {t: _row_count(conn, t) for t in CRITICAL_TABLES}

        # 4. Sample data for sample tables
        samples = {}
        for t in SAMPLE_TABLES:
            data = _table_sample(conn, t, SAMPLE_LIMIT)
            if data:
                cols, rows = data
                # Convert to hashable form
                samples[t] = {
                    'columns': cols,
                    'row_count': _row_count(conn, t),
                    'rows': rows,
                    'sample_sha': _hash_text(repr([cols] + rows)),
                }

        # 5. Migrations
        migrations = _migrations_applied(conn)

        fingerprint = {
            'db_path': str(db_path),
            'captured_at': __import__('datetime').datetime.now().isoformat(),
            'tables_count': len(tables),
            'indexes_count': len(indexes),
            'tables': tables,
            'indexes': indexes,
            'row_counts': row_counts,
            'samples': samples,
            'migrations': migrations,
            'tables_sha': _hash_text(repr(sorted(tables.keys()))),
            'row_counts_sha': _hash_text(repr(sorted(row_counts.items()))),
        }
        return fingerprint
    finally:
        conn.close()


def diff(old_fp, new_fp):
    """Compare two fingerprints and return structured diff."""
    result = {
        'tables_added': [],
        'tables_dropped': [],
        'tables_changed_sql': [],
        'indexes_added': [],
        'indexes_dropped': [],
        'indexes_changed_sql': [],
        'row_count_changes': {},
        'sample_changes': [],
        'migrations_added': [],
        'migrations_removed': [],
    }

    # Tables
    old_t = set(old_fp.get('tables', {}).keys())
    new_t = set(new_fp.get('tables', {}).keys())
    result['tables_added'] = sorted(new_t - old_t)
    result['tables_dropped'] = sorted(old_t - new_t)
    for name in old_t & new_t:
        if old_fp['tables'][name]['sql_sha'] != new_fp['tables'][name]['sql_sha']:
            result['tables_changed_sql'].append(name)

    # Indexes
    old_i = set(old_fp.get('indexes', {}).keys())
    new_i = set(new_fp.get('indexes', {}).keys())
    result['indexes_added'] = sorted(new_i - old_i)
    result['indexes_dropped'] = sorted(old_i - new_i)
    for name in old_i & new_i:
        if old_fp['indexes'][name]['sql_sha'] != new_fp['indexes'][name]['sql_sha']:
            result['indexes_changed_sql'].append(name)

    # Row counts
    old_rc = old_fp.get('row_counts', {})
    new_rc = new_fp.get('row_counts', {})
    for t in set(old_rc.keys()) | set(new_rc.keys()):
        old_n = old_rc.get(t, -1)
        new_n = new_rc.get(t, -1)
        if old_n != new_n:
            result['row_count_changes'][t] = {'old': old_n, 'new': new_n, 'delta': new_n - old_n}

    # Samples (compare hash)
    old_s = old_fp.get('samples', {})
    new_s = new_fp.get('samples', {})
    for t in set(old_s.keys()) | set(new_s.keys()):
        old_sha = old_s.get(t, {}).get('sample_sha')
        new_sha = new_s.get(t, {}).get('sample_sha')
        if old_sha != new_sha:
            result['sample_changes'].append(t)

    # Migrations
    old_m = set(old_fp.get('migrations', []))
    new_m = set(new_fp.get('migrations', []))
    result['migrations_added'] = sorted(new_m - old_m)
    result['migrations_removed'] = sorted(old_m - new_m)

    return result


def verify(db_path, expected_fp):
    """Verify a DB matches a fingerprint. Returns (ok, diff_struct)."""
    actual = capture(db_path)
    d = diff(expected_fp, actual)
    # Filter out trivial changes
    ok = (
        not d['tables_dropped']
        and not d['tables_changed_sql']
        and not d['indexes_dropped']
        and not d['indexes_changed_sql']
    )
    return ok, d


def cmd_capture(args):
    fp = capture(args.db_path)
    out = Path(args.output)
    out.write_text(yaml.dump(fp, default_flow_style=False, sort_keys=False, allow_unicode=True), encoding='utf-8')
    print(f'[OK] captured fingerprint: {out}')
    print(f'  tables: {fp["tables_count"]}, indexes: {fp["indexes_count"]}')
    print(f'  tables_sha: {fp["tables_sha"]}')
    print(f'  row_counts_sha: {fp["row_counts_sha"]}')


def cmd_diff(args):
    old = yaml.safe_load(Path(args.old).read_text(encoding='utf-8'))
    new = yaml.safe_load(Path(args.new).read_text(encoding='utf-8'))
    d = diff(old, new)

    print('=== DB FINGERPRINT DIFF ===')
    print(f'tables_added:    {len(d["tables_added"])} -> {d["tables_added"]}')
    print(f'tables_dropped:  {len(d["tables_dropped"])} -> {d["tables_dropped"]}')
    print(f'tables_changed:  {len(d["tables_changed_sql"])} -> {d["tables_changed_sql"]}')
    print(f'indexes_added:   {len(d["indexes_added"])} -> {d["indexes_added"]}')
    print(f'indexes_dropped: {len(d["indexes_dropped"])} -> {d["indexes_dropped"]}')
    print(f'indexes_changed: {len(d["indexes_changed_sql"])} -> {d["indexes_changed_sql"]}')
    print()
    print('Row count changes (delta = new - old):')
    for t, ch in sorted(d['row_count_changes'].items()):
        print(f'  {t:30s} {ch["old"]:6d} -> {ch["new"]:6d}  (delta={ch["delta"]:+d})')
    print()
    print(f'sample_changes (content drift): {d["sample_changes"]}')
    print(f'migrations_added:    {d["migrations_added"]}')
    print(f'migrations_removed:  {d["migrations_removed"]}')

    if args.sql_output:
        print()
        print('=== SUGGESTED MIGRATION (DDL only, no data) ===')
        for t in d['tables_added']:
            new_sql = new.get('tables', {}).get(t, {}).get('sql', '')
            if new_sql:
                print(f'-- table added: {t}')
                print(new_sql + ';')
        for t in d['tables_changed_sql']:
            print(f'-- table changed (manual review): {t}')
        for idx in d['indexes_added']:
            new_sql = new.get('indexes', {}).get(idx, {}).get('sql', '')
            if new_sql:
                print(f'-- index added: {idx}')
                print(new_sql + ';')


def cmd_verify(args):
    expected = yaml.safe_load(Path(args.expected).read_text(encoding='utf-8'))
    ok, d = verify(args.db_path, expected)
    print(f'verify: {"OK" if ok else "DRIFT DETECTED"}')
    if not ok:
        print(f'  tables_dropped:    {d["tables_dropped"]}')
        print(f'  tables_changed:    {d["tables_changed_sql"]}')
        print(f'  indexes_dropped:   {d["indexes_dropped"]}')
        print(f'  indexes_changed:   {d["indexes_changed_sql"]}')
        print(f'  row_count_changes: {d["row_count_changes"]}')
    sys.exit(0 if ok else 1)


def main():
    parser = argparse.ArgumentParser(description='DB schema/data fingerprint tool')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_cap = sub.add_parser('capture', help='capture DB fingerprint')
    p_cap.add_argument('db_path')
    p_cap.add_argument('output')
    p_cap.set_defaults(func=cmd_capture)

    p_diff = sub.add_parser('diff', help='diff two fingerprints')
    p_diff.add_argument('old')
    p_diff.add_argument('new')
    p_diff.add_argument('--sql-output', action='store_true', help='print suggested migration DDL')
    p_diff.set_defaults(func=cmd_diff)

    p_v = sub.add_parser('verify', help='verify DB matches expected fingerprint')
    p_v.add_argument('db_path')
    p_v.add_argument('expected')
    p_v.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
