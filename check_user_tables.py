from meta.core.datasource import get_data_source
ds = get_data_source("sqlite", database="meta/architecture.db")
cursor = ds.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
user_tables = [t for t in tables if 'user' in t.lower()]
print("Tables with 'user':")
for t in user_tables:
    print(f"  - {t}")

print("\nChecking foreign keys in users table...")
cursor = ds.execute("PRAGMA foreign_key_list('users')")
fks = cursor.fetchall()
print(f"Foreign keys in users: {fks}")

print("\nAll tables that might reference users:")
for t in tables:
    cursor = ds.execute(f"PRAGMA table_info('{t}')")
    cols = [r[1] for r in cursor.fetchall()]
    user_refs = [c for c in cols if 'user' in c.lower()]
    if user_refs:
        print(f"  {t}: {user_refs}")
