import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 检查id=4247和12318的business_objects
print('检查id=4247和12318的business_objects:')
cursor.execute('SELECT id, name, version_id FROM business_objects WHERE id IN (4247, 12318)')
results = cursor.fetchall()
for row in results:
    print(f'  id: {row[0]}, name: {row[1]}, version_id: {row[2]}')

# 检查所有有TEST annotations的business_objects
print('\n有TEST annotations的business_objects及其version_id:')
cursor.execute('''
    SELECT DISTINCT bo.id, bo.name, bo.version_id 
    FROM business_objects bo
    JOIN annotations a ON bo.id = a.target_id
    WHERE a.category = 'TEST' AND a.target_type = 'business_object'
''')
results2 = cursor.fetchall()
for row in results2:
    print(f'  id: {row[0]}, name: {row[1]}, version_id: {row[2]}')

# 检查version_id=1的business_objects总数
print('\nversion_id=1的business_objects总数:')
cursor.execute('SELECT COUNT(*) FROM business_objects WHERE version_id = 1')
print(f'  {cursor.fetchone()[0]}')

# 不带version_id条件的有TEST annotations的business_objects
print('\n不带version_id条件的有TEST annotations的business_objects:')
cursor.execute('''
    SELECT DISTINCT bo.id, bo.name, bo.version_id 
    FROM business_objects bo
    JOIN annotations a ON bo.id = a.target_id
    WHERE a.category = 'TEST' AND a.target_type = 'business_object'
''')
results3 = cursor.fetchall()
for row in results3:
    print(f'  id: {row[0]}, name: {row[1]}, version_id: {row[2]}')

conn.close()
