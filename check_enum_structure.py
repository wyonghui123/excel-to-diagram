import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# Check enum_types table structure
print('=== enum_types table structure ===')
cursor.execute('PRAGMA table_info(enum_types)')
columns = cursor.fetchall()
for col in columns:
    print(f'  {col[1]} ({col[2]})')

# Show sample data with correct columns
print('\n=== Sample data (first 3 rows) ===')
cursor.execute('SELECT * FROM enum_types LIMIT 3')
rows = cursor.fetchall()
col_names = [description[0] for description in cursor.description]
print('Columns:', col_names)
for row in rows:
    print(dict(zip(col_names, row)))

conn.close()