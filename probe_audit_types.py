"""列出 audit_logs 表中出现过的所有 object_type"""
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("SELECT DISTINCT object_type FROM audit_logs ORDER BY object_type")
for r in cur.fetchall():
    print(f'  {r[0]}')
conn.close()
