# -*- coding: utf-8 -*-
"""通过 BO framework 真实创建用户组，记录实际写入 audit_logs 的所有内容"""
import sys
import os
import sqlite3

sys.path.insert(0, r'D:\filework\excel-to-diagram')

from meta.core.bo_framework import BOFramework
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.datasource import get_data_source

db_path = r'D:\filework\excel-to-diagram\meta\architecture.db'
ds = get_data_source('sqlite', database=db_path)

schema_dir = get_yaml_schema_dir()
register_from_directory(schema_dir)

framework = BOFramework(ds)
from meta.core.interceptors.context_interceptor import ContextInterceptor
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.interceptors.business_log_interceptor import BusinessLogInterceptor

framework.register_interceptor(ContextInterceptor())
framework.register_interceptor(BusinessLogInterceptor())
framework.register_interceptor(PersistenceInterceptor())
framework.register_interceptor(AuditInterceptor())

framework.set_user_context(user_id=1, user_name='admin', ip_address='127.0.0.1')

# Clean any existing test data
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("DELETE FROM audit_logs WHERE trace_id = 'trace_test_create'")
conn.commit()
conn.close()

# Create user_group
import random
code = f'test_audit_{random.randint(100000, 999999)}'
print(f'Creating user_group code={code}')

# Override trace_id to find our records
from meta.core.trace_id import TraceId
TraceId.set('trace_test_create')

result = framework.create('user_group', {
    'code': code,
    'name': f'Audit Test {code}',
    'description': 'Test description',
})
print(f'Result: success={result.success}, data={result.data}')

# Wait for async writes to complete
import time
time.sleep(2)

# Check audit_logs
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
print()
print('=== audit_logs rows with trace_id=trace_test_create ===')
cursor.execute("""
    SELECT id, action, field_name, old_value, new_value, created_at
    FROM audit_logs
    WHERE trace_id = 'trace_test_create'
    ORDER BY id ASC
""")
rows = cursor.fetchall()
print(f'Total rows: {len(rows)}')
for row in rows:
    print(row)
conn.close()
