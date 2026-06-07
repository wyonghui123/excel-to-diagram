"""SSOT migration: updated_at 从物理列改为从 audit_logs 虚拟计算"""
import sqlite3, os, sys

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'architecture.db'))


def run():
    print(f"Database: {DB_PATH}")
    print(f"SQLite version: {sqlite3.sqlite_version}")
    if not os.path.exists(DB_PATH):
        print(f"[X] Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 60)
    print("SSOT Migration: updated_at → audit_logs virtual compute")
    print("=" * 60)

    # ── Phase 1: audit_logs table upgrade ──
    print("\n[Phase 1] audit_logs: add created_at_epoch column...")

    try:
        conn.execute("ALTER TABLE audit_logs ADD COLUMN created_at_epoch BIGINT")
        print("  [OK] created_at_epoch column added")
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower():
            print("  ⏭  column already exists")
        else:
            raise

    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM audit_logs "
        "WHERE created_at_epoch IS NULL AND created_at IS NOT NULL"
    ).fetchone()['cnt']
    print(f"  Rows to backfill: {count}")
    if count > 0:
        conn.execute(
            "UPDATE audit_logs SET created_at_epoch = "
            "(strftime('%s', created_at) * 1000) "
            "WHERE created_at_epoch IS NULL AND created_at IS NOT NULL"
        )
        print(f"  [OK] Backfilled {count} rows")

    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_ssot_updated "
            "ON audit_logs(object_type, object_id, action, created_at_epoch DESC)"
        )
        print("  [OK] idx_audit_ssot_updated created")
    except Exception as e:
        print(f"  [WARNING]  index creation: {e}")

    # ── Phase 2: Drop updated_at from business tables ──
    print("\n[Phase 2] Drop updated_at physical column from business tables...")

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    all_table_names = [t['name'] for t in tables]
    print(f"  Total tables in DB: {len(all_table_names)}")

    candidates = []
    for table_name in all_table_names:
        cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        col_names = [c['name'] for c in cols]
        if 'updated_at' in col_names:
            candidates.append((table_name, col_names))
            print(f"  [SEARCH] {table_name}: columns={col_names}")

    if not candidates:
        print("  (no tables with updated_at column)")
        conn.close()
        return

    print(f"\n  Tables to process: {len(candidates)}")

    sqlite_ver = tuple(int(x) for x in sqlite3.sqlite_version.split('.'))
    supports_drop_column = sqlite_ver >= (3, 35, 0)
    print(f"  SQLite {sqlite3.sqlite_version} → DROP COLUMN {'[OK] supported' if supports_drop_column else '[X] not supported (need >= 3.35.0)'}")

    if supports_drop_column:
        dropped = []
        skipped = []
        for table_name, _ in candidates:
            try:
                indexes = conn.execute(
                    f"SELECT name FROM pragma_index_list('{table_name}') "
                    f"WHERE name LIKE '%updated_at%'"
                ).fetchall()
                for idx in indexes:
                    conn.execute(f"DROP INDEX IF EXISTS {idx['name']}")

                triggers = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    f"AND tbl_name='{table_name}' AND sql LIKE '%updated_at%'"
                ).fetchall()
                for trg in triggers:
                    conn.execute(f"DROP TRIGGER IF EXISTS {trg['name']}")
                    print(f"  [WARNING]  Dropped trigger {trg['name']} on {table_name}")

                conn.execute(f"ALTER TABLE {table_name} DROP COLUMN updated_at")
                dropped.append(table_name)
            except Exception as e:
                skipped.append((table_name, str(e)))

        for t in dropped:
            print(f"  [OK] DROPPED: {t}")
        for t, err in skipped:
            print(f"  [X] SKIPPED: {t} — {err}")

        conn.commit()
        print(f"\n[OK] Phase 2 complete. Dropped: {len(dropped)}, Skipped: {len(skipped)}")
    else:
        print("\n  Using table-rebuild method (SQLite < 3.35.0)...")
        dropped = []
        skipped = []
        for table_name, col_names in candidates:
            other_cols = [c for c in col_names if c != 'updated_at']
            col_list = ', '.join(other_cols)
            try:
                # 2026-06-05 修复：使用 BEGIN IMMEDIATE 防止多进程写冲突
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(f"CREATE TABLE {table_name}_new AS SELECT {col_list} FROM {table_name}")
                conn.execute(f"DROP TABLE {table_name}")
                conn.execute(f"ALTER TABLE {table_name}_new RENAME TO {table_name}")
                conn.execute("COMMIT")
                dropped.append(table_name)
            except Exception as e:
                conn.execute("ROLLBACK")
                skipped.append((table_name, str(e)))

        for t in dropped:
            print(f"  [OK] DROPPED (rebuilt): {t}")
        for t, err in skipped:
            print(f"  [X] SKIPPED: {t} — {err}")

        print(f"\n[OK] Phase 2 complete. Dropped: {len(dropped)}, Skipped: {len(skipped)}")

        if dropped:
            print("\n[WARNING]  WARNING: Tables were rebuilt. Primary keys and auto-increment may have been lost.")
            print("  Recommended: verify table schemas with .schema command.")

    if dropped:
        print(f"   Tables: {', '.join(dropped)}")

    conn.close()


if __name__ == '__main__':
    run()
