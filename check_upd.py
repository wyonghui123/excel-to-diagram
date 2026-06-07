import sqlite3, os
conn = sqlite3.connect('meta/architecture.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
print(f"Total tables: {len(tables)}")
count_with_updated = 0
for (t,) in tables:
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    col_names = [c[1] for c in cols]
    has_created = 'created_at' in col_names
    has_updated = 'updated_at' in col_names
    if has_created or has_updated:
        suffix = []
        if has_created: suffix.append('created_at')
        if has_updated: suffix.append('updated_at')
        if has_updated: count_with_updated += 1
        print(f"  {t}: {', '.join(suffix)}")
print(f"\nTables with updated_at: {count_with_updated}")
conn.close()
