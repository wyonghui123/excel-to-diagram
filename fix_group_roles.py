import sqlite3, os
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta', 'architecture.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group_roles'")
result = cursor.fetchone()
print(f"group_roles table exists: {result is not None}")
if result is None:
    cursor.execute("""CREATE TABLE IF NOT EXISTS group_roles (
        group_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (group_id, role_id)
    )""")
    conn.commit()
    print("Created group_roles table")
conn.close()
