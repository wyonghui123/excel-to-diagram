"""
[Phase 1 / Plan A Task 4.6] v078: drop legacy menus under user-permission hub.

spec16 Plan D (2026-09-01) restructures user-permission hub as multi_object_hub
with 3 independent child menus:
  - user-management          (page_type=object_list, primary_object_type=user)
  - permission-set-management (page_type=object_list, primary_object_type=permission_set)
  - org-management           (page_type=object_list, primary_object_type=org)

But commit bb55767 + init_menu_permissions.py only INSERT new 3 menus, did not
DELETE 6 pre-spec16 legacy menus:
  - user-list             (pre-spec16 user list landing)
  - permission_set-list   (pre-spec16 permission set list landing)
  - org-list              (pre-spec16 org list landing)
  - org_function-list     (pre-spec16 org function list landing)
  - role-list             (pre-spec16 role list landing, before role->permission_set rename)
  - user_group-list       (pre-spec16 user group list landing, before user_group->org rename)

After cleanup (admin role bound):
  user-permission (multi_object_hub, parent=empty)
  |-- user-management
  |-- permission-set-management
  +-- org-management

Applies to: localhost, staging, prod (newly deployed prod runs v070-v077 + v078 sequence)

Conforms to meta/migrations/README.md:
- Filename: v<NNN>__<desc>.py (v078)
- Entry signature: migrate(db_path, skip_backup=False) -> bool
- Idempotent: each row checked via SELECT ... WHERE menu_code IN (...)
- backup-then-delete: legacy rows backed up to menus_pre_v078_backup + menu_permissions_pre_v078_backup,
  deletable from backup tables (30-day rolling cleanup)
- Safety: backup ALWAYS created unless skip_backup=True

Event timeline:
- 2026-09-01: staging deployed spec16 Plan D (worktree fix-spec16-staging-overlap)
- init_menu_permissions.py ran but only INSERTed, did not DELETE legacy
- admin role on staging saw 5 leaf menus (3 new + 2 legacy)
- Direct SQL DELETE on staging cleaned up 6 legacy menus + 2 menu_permissions
  backed up to /tmp/staging_menu_cleanup_*/
- This migration encapsulates the same DELETE logic for prod replay

downgrade: restore from backup tables (only works if backup tables still exist)
"""
import sqlite3
from pathlib import Path

LEGACY_MENUS = [
    'user-list',
    'permission_set-list',
    'org-list',
    'org_function-list',
    'role-list',
    'user_group-list',
]
BACKUP_TABLE = 'menus_pre_v078_backup'
BACKUP_PERMS_TABLE = 'menu_permissions_pre_v078_backup'
ROLE_MENU_PERMS_BACKUP = 'role_menu_permissions_pre_v078_backup'


def _table_exists(conn, name):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _create_backup_table(conn, source, backup):
    """Create backup table from source schema + copy legacy rows.

    Returns True if backup was performed.
    """
    if not _table_exists(conn, source):
        return False
    if _table_exists(conn, backup):
        print(f'  - {backup} already exists (v078 already ran), skip backup')
        return False

    schema_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (source,),
    ).fetchone()
    if not schema_row or not schema_row[0]:
        print(f'  - cannot get schema for {source}, skip')
        return False

    conn.execute(f"CREATE TABLE {backup} AS SELECT * FROM {source} WHERE 0")
    placeholders = ','.join('?' * len(LEGACY_MENUS))
    conn.execute(
        f"INSERT INTO {backup} SELECT * FROM {source} WHERE menu_code IN ({placeholders})",
        LEGACY_MENUS,
    )
    cnt = conn.execute(f"SELECT COUNT(*) FROM {backup}").fetchone()[0]
    print(f'  - backed up {cnt} rows: {source} -> {backup}')
    return True


def _drop_legacy_rows(conn, table):
    placeholders = ','.join('?' * len(LEGACY_MENUS))
    cur = conn.execute(
        f"DELETE FROM {table} WHERE menu_code IN ({placeholders})",
        LEGACY_MENUS,
    )
    return cur.rowcount


def _migrate_impl(db_path):
    if not db_path.exists():
        print(f'[v078] DB not found: {db_path}')
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print(f'[v078] step 1: backup legacy menus -> {BACKUP_TABLE}')
        _create_backup_table(conn, 'menus', BACKUP_TABLE)

        print(f'[v078] step 2: backup legacy menu_permissions -> {BACKUP_PERMS_TABLE}')
        _create_backup_table(conn, 'menu_permissions', BACKUP_PERMS_TABLE)

        backed_up_rmp = False
        if _table_exists(conn, 'role_menu_permissions'):
            print(f'[v078] step 2.5: backup role_menu_permissions -> {ROLE_MENU_PERMS_BACKUP}')
            backed_up_rmp = _create_backup_table(conn, 'role_menu_permissions', ROLE_MENU_PERMS_BACKUP)
            if backed_up_rmp:
                deleted = _drop_legacy_rows(conn, 'role_menu_permissions')
                print(f'  - deleted {deleted} rows from role_menu_permissions')

        deleted_menus = _drop_legacy_rows(conn, 'menus')
        deleted_perms = _drop_legacy_rows(conn, 'menu_permissions')
        print(f'[v078] deleted: menus={deleted_menus}, menu_permissions={deleted_perms}')

        if deleted_menus == 0 and deleted_perms == 0:
            print('[v078] nothing to delete (already clean or no legacy menus)')

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v078] migrate failed: {e}')
        raise
    finally:
        conn.close()


def verify(db_path):
    """Verify v078: no legacy menus remain in menus or menu_permissions."""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ','.join('?' * len(LEGACY_MENUS))
        for table in ('menus', 'menu_permissions'):
            if not _table_exists(conn, table):
                continue
            cur = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE menu_code IN ({placeholders})",
                LEGACY_MENUS,
            )
            cnt = cur.fetchone()[0]
            if cnt > 0:
                print(f'  [v078 verify] {table} still has {cnt} legacy rows')
                return False
        return True
    finally:
        conn.close()


def downgrade(db_path, skip_backup=False):
    """v078 downgrade: restore legacy menus from backup tables."""
    if not db_path.exists():
        print(f'[v078] DB not found: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for source, backup in (('menus', BACKUP_TABLE), ('menu_permissions', BACKUP_PERMS_TABLE)):
            if not _table_exists(conn, backup):
                print(f'  [v078 downgrade] {backup} missing, cannot restore {source}')
                continue
            cnt = conn.execute(f"SELECT COUNT(*) FROM {backup}").fetchone()[0]
            if cnt == 0:
                continue
            conn.execute(f"INSERT INTO {source} SELECT * FROM {backup}")
            print(f'  [v078 downgrade] restored {cnt} rows from {backup} into {source}')
        if _table_exists(conn, ROLE_MENU_PERMS_BACKUP) and _table_exists(conn, 'role_menu_permissions'):
            cnt = conn.execute(f"SELECT COUNT(*) FROM {ROLE_MENU_PERMS_BACKUP}").fetchone()[0]
            conn.execute(f"INSERT OR IGNORE INTO role_menu_permissions SELECT * FROM {ROLE_MENU_PERMS_BACKUP}")
            print(f'  [v078 downgrade] restored {cnt} rows from {ROLE_MENU_PERMS_BACKUP}')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v078] downgrade failed: {e}')
        raise
    finally:
        conn.close()


def migrate(db_path, skip_backup=False):
    """v078: drop legacy menus under user-permission hub (spec16 Plan D cleanup).

    Args:
        db_path: SQLite database path
        skip_backup: skip backup table creation (default False - safer)

    Returns:
        True if migration succeeded or already applied (idempotent).
    """
    if skip_backup:
        print('[v078] WARNING: skip_backup=True, no rollback possible')
        conn = sqlite3.connect(str(db_path))
        try:
            _drop_legacy_rows(conn, 'menus')
            _drop_legacy_rows(conn, 'menu_permissions')
            if _table_exists(conn, 'role_menu_permissions'):
                _drop_legacy_rows(conn, 'role_menu_permissions')
            conn.commit()
            return True
        finally:
            conn.close()
    return _migrate_impl(db_path)


if __name__ == '__main__':
    import sys
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('meta/architecture.db')
    print(f'[v078] running on {db}')
    success = migrate(db)
    print(f'[v078] success={success}, verify={verify(db)}')
