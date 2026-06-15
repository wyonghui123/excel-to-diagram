# -*- coding: utf-8 -*-
"""实际测试 dissociate 是否写审计日志"""
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

# 直接查询现有的 user_group 和 user
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

c = data_source.execute("SELECT * FROM user_group_members ORDER BY id DESC LIMIT 10")
print('=== user_group_members 最近 10 条 ===')
for row in c.fetchall():
    print(f'  {row}')

# 找一对没关联的来测试
print()
print('=== 测试 1: ASSOCIATE 一个 user 到 group ===')

framework = BOFramework(data_source)
framework.register_interceptor(ContextInterceptor())
framework.register_interceptor(PersistenceInterceptor())
framework.register_interceptor(AuditInterceptor())
framework._data_source = data_source
framework._db_path = db_path

framework.set_user_context(user_id=1, user_name='admin', ip_address='127.0.0.1')

# 找一个现有 group 和 user
group_id = groups[0][0] if groups else None
user_id = users[0][0] if users else None

print(f'使用 group_id={group_id}, user_id={user_id}')

# 先查看关联是否存在
c = data_source.execute(
    "SELECT * FROM user_group_members WHERE group_id=? AND user_id=?",
    [group_id, user_id]
)
existing = c.fetchall()
print(f'已有关联记录: {existing}')

# Step 1: ASSOCIATE
result = framework.associate(
    src_type='user_group',
    src_id=group_id,
    tgt_type='user',
    tgt_id=user_id,
    association_name='members'
)
print(f'associate result: success={result.success}, message={result.message}')

# Step 2: 立即查审计日志 (sync 模式下应该立即可见)
c = data_source.execute("""
    SELECT id, action, object_type, object_id, field_name, created_at
    FROM audit_logs
    WHERE object_type='user_group' AND object_id=?
    ORDER BY id DESC LIMIT 5
""", [group_id])
logs = c.fetchall()
print(f'关联后 user_group 审计日志: {logs}')

# Step 3: 等 3 秒再查 (异步模式兜底)
time.sleep(3)
c = data_source.execute("""
    SELECT id, action, object_type, object_id, field_name, created_at
    FROM audit_logs
    WHERE object_type='user_group' AND object_id=?
    ORDER BY id DESC LIMIT 5
""", [group_id])
logs = c.fetchall()
print(f'3秒后 user_group 审计日志: {logs}')

# Step 4: DISSOCIATE
print()
print('=== 测试 2: DISSOCIATE (取消关联) ===')
result = framework.dissociate(
    src_type='user_group',
    src_id=group_id,
    tgt_type='user',
    tgt_id=user_id,
    association_name='members'
)
print(f'dissociate result: success={result.success}, message={result.message}')

# Step 5: 立即查审计日志
c = data_source.execute("""
    SELECT id, action, object_type, object_id, field_name, old_value, new_value, created_at
    FROM audit_logs
    WHERE object_type='user_group' AND object_id=?
    ORDER BY id DESC LIMIT 5
""", [group_id])
logs = c.fetchall()
print(f'取消关联后 user_group 审计日志: {logs}')

# Step 6: 等 3 秒再查 (异步模式兜底)
time.sleep(3)
c = data_source.execute("""
    SELECT id, action, object_type, object_id, field_name, old_value, new_value, created_at
    FROM audit_logs
    WHERE object_type='user_group' AND object_id=?
    ORDER BY id DESC LIMIT 5
""", [group_id])
logs = c.fetchall()
print(f'3秒后 user_group 审计日志: {logs}')

# 验证关联是否真的被删除
c = data_source.execute(
    "SELECT * FROM user_group_members WHERE group_id=? AND user_id=?",
    [group_id, user_id]
)
remaining = c.fetchall()
print(f'Dissociate 后关联表剩余: {remaining}')
