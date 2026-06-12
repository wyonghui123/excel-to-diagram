import sys
import os
sys.path.insert(0, '.')
from meta.core.datasource import get_data_source

db_path = os.path.join('meta', 'architecture.db')
ds = get_data_source('sqlite', database=db_path)

print('=== permissions schema ===')
for row in ds.execute('PRAGMA table_info(permissions)').fetchall():
    print(' ', row)
print()
print('=== role_permissions schema ===')
for row in ds.execute('PRAGMA table_info(role_permissions)').fetchall():
    print(' ', row)
print()
print('=== role count ===')
print(' ', ds.execute('SELECT COUNT(*) FROM roles').fetchone())
print('=== permission count ===')
print(' ', ds.execute('SELECT COUNT(*) FROM permissions').fetchone())
print('=== role_permissions count ===')
print(' ', ds.execute('SELECT COUNT(*) FROM role_permissions').fetchone())
print('=== audit_logs schema ===')
for row in ds.execute('PRAGMA table_info(audit_logs)').fetchall():
    print(' ', row)

print()
print('=== List role permissions query ===')
try:
    role_ids = [1, 2, 3]
    placeholders = ','.join(['?'] * len(role_ids))
    cursor = ds.execute(
        f"SELECT rp.role_id, p.id, p.code, p.name, p.description, p.is_system "
        f"FROM permissions p JOIN role_permissions rp ON p.id = rp.permission_id "
        f"WHERE rp.role_id IN ({placeholders})",
        role_ids
    )
    rows = cursor.fetchall()
    print(' OK, count:', len(rows))
except Exception as e:
    import traceback
    traceback.print_exc()
