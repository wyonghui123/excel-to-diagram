# -*- coding: utf-8 -*-
"""验证 OperationLogInterceptor 禁用效果 - 直接导入模块绕过 YAML Loader 输出"""
import sys
import os
import sqlite3
import warnings
import logging

# 抑制 YAML Loader 输出
logging.disable(logging.CRITICAL)
warnings.filterwarnings('ignore')

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# 重定向 stdout 到文件，避免 IDE 显示 YAML 输出
import io
sys.stdout = io.StringIO()

from meta.core.datasource import get_data_source
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
register_from_directory(get_yaml_schema_dir())
ds = get_data_source('sqlite', database='meta/architecture.db')

# 恢复 stdout
sys.stdout = sys.__stdout__

from meta.core.bo_framework import BOFramework
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.interceptors.context_interceptor import ContextInterceptor
from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor

framework = BOFramework(ds)
framework.register_interceptor(ContextInterceptor())
framework.register_interceptor(PersistenceInterceptor())
framework.register_interceptor(AuditInterceptor())
framework.register_interceptor(OperationLogInterceptor())
framework._data_source = ds
framework.set_user_context(user_id=1, user_name='admin', ip_address='127.0.0.1')

conn = sqlite3.connect('meta/architecture.db')
c = conn.cursor()
c.execute('SELECT MAX(id) FROM audit_logs')
before_id = c.fetchone()[0]
print(f'[BEFORE] max audit_log id = {before_id}', flush=True)

# 触发 CRUD 操作
result = framework.create(
    object_type='product',
    data={
        'code': f'TEST_{os.urandom(4).hex().upper()}',
        'name': 'Test Product Audit Verify',
        'description': 'Verify audit log after disable',
        'is_active': True
    }
)
created_id = result.data.get('id') if result.data else None
print(f'CREATE id = {created_id}, success = {result.success}', flush=True)

result = framework.update(
    object_type='product',
    id=created_id,
    data={'name': 'Updated Test Product'}
)
print(f'UPDATE success = {result.success}', flush=True)

result = framework.delete(object_type='product', id=created_id)
print(f'DELETE success = {result.success}', flush=True)

# 检查新的审计日志
c.execute(f'SELECT id, action, object_type, field_name, created_at FROM audit_logs WHERE id > {before_id} ORDER BY id ASC')
new_logs = c.fetchall()
print(f'\n=== 新产生的审计日志 ({len(new_logs)} 条) ===', flush=True)
for log in new_logs:
    print(f'  {log}', flush=True)

# 验证: 不应包含 CREATE_OBJECT/READ_OBJECT/UPDATE_OBJECT/DELETE_OBJECT
ops_logs = [log for log in new_logs if log[1] in ('CREATE_OBJECT','READ_OBJECT','UPDATE_OBJECT','DELETE_OBJECT')]
print(f'\n=== OperationLog 类型日志: {len(ops_logs)} 条 ===', flush=True)
if ops_logs:
    print('[FAIL] 仍有 OperationLog 类型日志！', flush=True)
    for log in ops_logs:
        print(f'  {log}', flush=True)
else:
    print('[OK] 没有 OperationLog 类型日志，禁用成功！', flush=True)

# 验证: 业务审计日志正常产生（CREATE/UPDATE/DELETE）
biz_logs = [log for log in new_logs if log[1] in ('CREATE','UPDATE','DELETE')]
print(f'\n=== 业务审计日志: {len(biz_logs)} 条 ===', flush=True)
if biz_logs:
    print('[OK] 业务审计日志正常产生', flush=True)
else:
    print('[FAIL] 业务审计日志缺失！', flush=True)

conn.close()
