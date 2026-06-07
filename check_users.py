import sqlite3, os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta', 'architecture.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT id, username FROM users LIMIT 10")
for row in cursor.fetchall():
    print(f"  user: id={row[0]} username={row[1]}")
conn.close()
