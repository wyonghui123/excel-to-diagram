import sqlite3

db_path = 'meta/architecture.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Count all users
cursor.execute("SELECT COUNT(*) FROM users")
count = cursor.fetchone()[0]
print(f"数据库中总用户数: {count}")

# Get min and max IDs
cursor.execute("SELECT MIN(id), MAX(id) FROM users")
min_id, max_id = cursor.fetchone()
print(f"ID范围: {min_id} - {max_id}")

conn.close()
