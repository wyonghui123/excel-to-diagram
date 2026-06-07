import sqlite3
conn = sqlite3.connect('meta/architecture.db')

# Check permission_rules table structure
cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='permission_rules'")
result = cursor.fetchone()
if result:
    print('permission_rules table structure:')
    print(result[0])
    print()

# Check sample data
cursor = conn.execute("SELECT * FROM permission_rules LIMIT 3")
rows = cursor.fetchall()
if rows:
    print('Sample permission_rules data:')
    for row in rows:
        print(row)
else:
    print('No permission_rules data found')

conn.close()
