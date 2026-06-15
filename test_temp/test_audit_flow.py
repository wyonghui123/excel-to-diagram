# -*- coding: utf-8 -*-
"""直接调用 AuditService.log 测试"""
import sys
sys.path.insert(0, r'D:\filework\excel-to-diagram')

from meta.core.datasource import get_data_source
from meta.services.audit_service import AuditService

db_path = r'D:\filework\excel-to-diagram\meta\architecture.db'
ds = get_data_source('sqlite', database=db_path)
svc = AuditService(ds)

print('=== Test 1: AuditService.log with new_data={"id": 999} ===')
svc.log(
    object_type='user_group',
    object_id=999,
    action='CREATE',
    user_id=1,
    user_name='test',
    new_data={'id': 999, 'code': 't1', 'name': 'Test1', 'parent_id': 1, 'manager_id': None, 'description': 'desc'},
    ip_address='127.0.0.1',
)

print('=== Test 2: AuditService.log with new_data={"id": 999} (only id) ===')
svc.log(
    object_type='user_group',
    object_id=999,
    action='CREATE',
    user_id=1,
    user_name='test',
    new_data={'id': 999},
    ip_address='127.0.0.1',
)

print('=== Test 3: AuditService.log with new_data=None ===')
svc.log(
    object_type='user_group',
    object_id=999,
    action='CREATE',
    user_id=1,
    user_name='test',
    new_data=None,
    ip_address='127.0.0.1',
)

# Check what was written
import sqlite3
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
print()
print('=== Recent rows for object_id=999 ===')
cursor.execute("""
    SELECT id, action, field_name, old_value, new_value
    FROM audit_logs
    WHERE object_id='999'
    ORDER BY id DESC LIMIT 10
""")
for row in cursor.fetchall():
    print(row)
conn.close()
