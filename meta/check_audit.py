import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'architecture.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== Latest audit logs ===")
cursor.execute("""
    SELECT id, object_type, object_id, action, field_name, user_id, user_name, created_at
    FROM audit_logs 
    ORDER BY id DESC 
    LIMIT 10
""")
rows = cursor.fetchall()
for row in rows:
    print(f"  id={row[0]}, object_type={row[1]}, object_id={row[2]}, action={row[3]}")
    print(f"    field={row[4]}, user_id={row[5]}, user_name={row[6]}, time={row[7]}")

conn.close()
