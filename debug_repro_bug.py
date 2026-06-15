"""
Reproduce the user group deletion bug.
"""
import sys
import os
import time
import tempfile

sys.path.insert(0, 'd:/filework/excel-to-diagram')

# Setup
from meta.core.datasource import get_data_source
from meta.core.bo_framework import BOFramework
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.models import registry

# Per-test isolated DB
db_fd, db_path = tempfile.mkstemp(suffix='.db')
os.close(db_fd)
print(f"[init] using test DB: {db_path}")

ds = get_data_source('sqlite', database=db_path)

# Create minimal tables
ds.execute('''CREATE TABLE IF NOT EXISTS user_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    parent_id INTEGER,
    manager_id INTEGER,
    created_at DATETIME,
    updated_at DATETIME,
    created_by INTEGER,
    updated_by INTEGER
)''')
ds.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(200) UNIQUE NOT NULL,
    email VARCHAR(200),
    display_name VARCHAR(200),
    created_at DATETIME
)''')
ds.execute('''CREATE TABLE IF NOT EXISTS user_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    is_manager INTEGER DEFAULT 0,
    joined_at DATETIME
)''')
ds.execute('''CREATE TABLE IF NOT EXISTS group_data_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    permission VARCHAR(50),
    created_at DATETIME
)''')
ds.execute('''CREATE TABLE IF NOT EXISTS group_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    created_at DATETIME
)''')
ds.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_category VARCHAR(200) NOT NULL DEFAULT 'business',
    log_level VARCHAR(200) NOT NULL DEFAULT 'INFO',
    object_type VARCHAR(200) NOT NULL,
    object_id INTEGER NOT NULL,
    parent_object_type VARCHAR(200),
    parent_object_id INTEGER,
    action VARCHAR(200) NOT NULL,
    field_name VARCHAR(200),
    old_value TEXT,
    new_value TEXT,
    user_id INTEGER,
    user_name VARCHAR(200),
    ip_address VARCHAR(200),
    user_agent VARCHAR(200),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    extra_data TEXT,
    trace_id VARCHAR(200),
    transaction_id VARCHAR(200),
    status VARCHAR(200) DEFAULT 'written',
    status_entered_at DATETIME,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    agent_id VARCHAR(200),
    agent_session_id VARCHAR(200),
    tool_call_id VARCHAR(200),
    agent_reasoning TEXT
)''')
ds.commit()

# Register schema
schema_dir = get_yaml_schema_dir()
if schema_dir and not registry._initialized:
    register_from_directory(schema_dir)

fw = BOFramework(data_source=ds)
fw.register_interceptor(PersistenceInterceptor())

# === Scenario A: simple delete ===
print("\n" + "="*60)
print("Scenario A: Delete a simple user group (no children, no members)")
print("="*60)
group_a_id = ds.insert('user_groups', {
    'code': f'BUG_A_{int(time.time())}',
    'name': 'Bug scenario A',
})
print(f"  Created group A id={group_a_id}")

result_a = fw.delete('user_group', group_a_id)
print(f"  Delete result: success={result_a.success}, errors={result_a.errors}, message={getattr(result_a, 'message', None)}")

exists = ds.find_by_id('user_groups', group_a_id)
print(f"  Group exists after delete? {exists is not None}  (expected: False)")

# === Scenario B: delete with child group ===
print("\n" + "="*60)
print("Scenario B: Delete a user group that has a CHILD group (self-referencing parent_id)")
print("="*60)
parent_id = ds.insert('user_groups', {
    'code': f'BUG_B_PARENT_{int(time.time())}',
    'name': 'Bug B parent',
})
child_id = ds.insert('user_groups', {
    'code': f'BUG_B_CHILD_{int(time.time())}',
    'name': 'Bug B child',
    'parent_id': parent_id,
})
print(f"  Created parent id={parent_id}, child id={child_id} (child.parent_id={parent_id})")

result_b = fw.delete('user_group', parent_id)
print(f"  Delete parent result: success={result_b.success}, errors={result_b.errors}, message={getattr(result_b, 'message', None)}")

parent_exists = ds.find_by_id('user_groups', parent_id)
print(f"  Parent exists after delete? {parent_exists is not None}  (expected: False)")

child = ds.find_by_id('user_groups', child_id)
if child is None:
    print(f"  Child also gone (cascade worked)")
elif child.get('parent_id') is None:
    print(f"  Child's parent_id was cleaned to NULL")
else:
    print(f"  !!! BUG !!! Child still exists with stale parent_id={child.get('parent_id')} pointing to non-existent parent {parent_id}")

# === Scenario C: delete with members ===
print("\n" + "="*60)
print("Scenario C: Delete a user group that has MEMBERS (M2M through table)")
print("="*60)
user_id = ds.insert('users', {
    'username': f'bug_user_c_{int(time.time())}',
    'email': 'bugc@test.com',
    'display_name': 'Bug User C',
})
group_c_id = ds.insert('user_groups', {
    'code': f'BUG_C_{int(time.time())}',
    'name': 'Bug scenario C',
})
ds.insert('user_group_members', {
    'group_id': group_c_id,
    'user_id': user_id,
})
print(f"  Created group C id={group_c_id} with member user_id={user_id}")

result_c = fw.delete('user_group', group_c_id)
print(f"  Delete result: success={result_c.success}, errors={result_c.errors}, message={getattr(result_c, 'message', None)}")

group_c_exists = ds.find_by_id('user_groups', group_c_id)
print(f"  Group exists after delete? {group_c_exists is not None}  (expected: False)")

member_count = ds.execute(
    "SELECT COUNT(*) FROM user_group_members WHERE group_id = ?", (group_c_id,)
).fetchone()[0]
print(f"  Members in user_group_members for deleted group: {member_count}  (expected: 0)")

# === Scenario D: delete with group_data_permissions ===
print("\n" + "="*60)
print("Scenario D: Delete a user group that has group_data_permissions")
print("="*60)
group_d_id = ds.insert('user_groups', {
    'code': f'BUG_D_{int(time.time())}',
    'name': 'Bug scenario D',
})
ds.insert('group_data_permissions', {
    'group_id': group_d_id,
    'resource_type': 'business_object',
    'resource_id': 'x',
    'permission': 'read',
})
print(f"  Created group D id={group_d_id} with 1 data permission")

result_d = fw.delete('user_group', group_d_id)
print(f"  Delete result: success={result_d.success}, errors={result_d.errors}, message={getattr(result_d, 'message', None)}")

group_d_exists = ds.find_by_id('user_groups', group_d_id)
print(f"  Group exists after delete? {group_d_exists is not None}  (expected: False)")

perm_count = ds.execute(
    "SELECT COUNT(*) FROM group_data_permissions WHERE group_id = ?", (group_d_id,)
).fetchone()[0]
print(f"  Permissions in group_data_permissions for deleted group: {perm_count}  (expected: 0, BUG if > 0)")

# === Summary ===
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"  A (simple):   success={result_a.success}  removed={exists is None}")
print(f"  B (child FK): success={result_b.success}  parent_removed={parent_exists is None}  child_orphan={child is not None and child.get('parent_id') is not None}")
print(f"  C (members):  success={result_c.success}  group_removed={group_c_exists is None}  orphan_members={member_count}")
print(f"  D (data_perm): success={result_d.success}  group_removed={group_d_exists is None}  orphan_perms={perm_count}")

ds.disconnect()
os.unlink(db_path)
print(f"\n[cleanup] removed {db_path}")
