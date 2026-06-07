import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# Check enum_types table
print('=== enum_types table ===')
try:
    cursor.execute('SELECT COUNT(*) FROM enum_types')
    count = cursor.fetchone()[0]
    print(f'Total records: {count}')

    if count > 0:
        cursor.execute('SELECT id, code, name FROM enum_types LIMIT 5')
        rows = cursor.fetchall()
        print('Sample data:')
        for row in rows:
            print(f'  {row}')
    else:
        print('No data in enum_types table!')
except Exception as e:
    print(f'Error: {e}')

# Check enum_values table
print('\n=== enum_values table ===')
try:
    cursor.execute('SELECT COUNT(*) FROM enum_values')
    count = cursor.fetchone()[0]
    print(f'Total records: {count}')
except Exception as e:
    print(f'Error: {e}')

conn.close()