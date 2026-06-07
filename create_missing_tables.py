import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta', 'architecture.db')
if not os.path.exists(db_path):
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'architecture.db')

print(f"Using database: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
existing = set(r[0] for r in cursor.fetchall())
print(f"Existing tables: {existing}")

tables_to_create = [
    """CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        is_system INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT DEFAULT '',
        display_name TEXT DEFAULT '',
        email TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS user_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS user_roles (
        user_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, role_id)
    )""",
    """CREATE TABLE IF NOT EXISTS user_group_members (
        user_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        is_manager INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, group_id)
    )""",
    """CREATE TABLE IF NOT EXISTS role_permissions (
        role_id INTEGER NOT NULL,
        permission_id INTEGER NOT NULL,
        PRIMARY KEY (role_id, permission_id)
    )""",
    """CREATE TABLE IF NOT EXISTS group_roles (
        group_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (group_id, role_id)
    )""",
    """CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        category TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]

for sql in tables_to_create:
    table_name = sql.split('EXISTS ')[1].split(' ')[0]
    try:
        cursor.execute(sql)
        if table_name not in existing:
            print(f"Created: {table_name}")
        else:
            print(f"Already exists: {table_name}")
    except Exception as e:
        print(f"Error creating {table_name}: {e}")

conn.commit()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cursor.fetchall()]
print(f"\nAll tables: {tables}")

conn.close()
