# -*- coding: utf-8 -*-
"""验证 dissociate 审计日志修复"""
import sys
import os
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.bo_framework import BOFramework
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.interceptors.context_interceptor import ContextInterceptor
from meta.core.datasource import get_data_source
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir

schema_dir = get_yaml_schema_dir()
register_from_directory(schema_dir)

db_path = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')
data_source = get_data_source('sqlite', database=db_path)

# 查询现有的 user_group 和 user
c = data_source.execute("SELECT id, code, name FROM user_groups ORDER BY id DESC LIMIT 3")
groups = c.fetchall()
print('=== 现有用户组 ===')
for row in groups:
    print(f'  {row}')

c = data_source.execute("SELECT id, username FROM users ORDER BY id DESC LIMIT 5")
users = c.fetchall()
print('=== 现有用户 ===')
for row in users:
    print(f'  {row}')

if not groups or not users:
    print('[SKIP] 没有足够的测试数据')
    sys.exit(0)

group_id = groups[0][0]
user_id = users[0][0]
print(f'\n使用 group_id={group_id}, user_id={user_id}')

# 初始化 BOFramework
framework = BOFramework(data_source)
framework.register_interceptor(ContextInterceptor())
framework.register_interceptor(PersistenceInterceptor())
framework.register_interceptor(AuditInterceptor())
framework._data_source = data_source
framework._db_path = db_path
framework.set_user_context(user_id=1, user_name='admin', ip_address='127.0.0.1')

# Step 1: 检查关联是否存在，不存在则创建
c = data_source.execute(
    "SELECT * FROM user_group_members WHERE group_id=? AND user_id=?",
    [group_id, user_id]
)
existing = c.fetchall()
print(f'\n已有关联记录: {existing}')

if not existing:
    print('\n=== Step 1: ASSOCIATE ===')
    result = framework.associate(
        src_type='user_group',
        src_id=group_id,
        tgt_type='user',
        tgt_id=user_id,
        association_name='members'
    )
    print(f'associate result: success={result.success}, message={result.message}')
    time.sleep(0.5)  # 等待审计写入

# Step 2: 查询 ASSOCIATE 审计日志
c = data_source.execute("""
    SELECT id, action, object_type, object_id, field_name, created_at
    FROM audit_logs
    WHERE action='ASSOCIATE' AND object_type='user_group' AND object_id=?
    ORDER BY id DESC LIMIT 5
""", [group_id])
logs = c.fetchall()
print(f'\nASSOCIATE 审计日志: {logs}')

# Step 3: DISSOCIATE
print('\n=== Step 2: DISSOCIATE ===')
result = framework.dissociate(
    src_type='user_group',
    src_id=group_id,
    tgt_type='user',
    tgt_id=user_id,
    association_name='members'
)
print(f'dissociate result: success={result.success}, message={result.message}')
time.sleep(0.5)  # 等待审计写入

# Step 4: 查询 DISSOCIATE 审计日志
c = data_source.execute("""
    SELECT id, action, object_type, object_id, field_name, created_at
    FROM audit_logs
    WHERE action='DISSOCIATE' AND object_type='user_group' AND object_id=?
    ORDER BY id DESC LIMIT 5
""", [group_id])
logs = c.fetchall()
print(f'\nDISSOCIATE 审计日志: {logs}')

# Step 5: 验证
if logs:
    print('\n[OK] DISSOCIATE 审计日志写入成功！')
else:
    print('\n[FAIL] DISSOCIATE 审计日志未找到！')

# 验证关联是否被删除
c = data_source.execute(
    "SELECT * FROM user_group_members WHERE group_id=? AND user_id=?",
    [group_id, user_id]
)
remaining = c.fetchall()
print(f'\nDissociate 后关联表剩余: {remaining}')
