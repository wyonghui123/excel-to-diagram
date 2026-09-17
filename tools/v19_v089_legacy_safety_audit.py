"""[v089 safety] 验证 legacy role_permissions 427 行历史数据是否已迁移到新表"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from tools.staging_round import (
    remote_exec, _build_remote_py_helper, use_prod_gateway,
)

INLINE = '''
import sqlite3
DB_PATH = "%(db_path)s"
conn = sqlite3.connect(DB_PATH, timeout=30)
cur = conn.cursor()

# 1. role_permissions 行数
n_legacy = cur.execute('SELECT COUNT(*) FROM role_permissions').fetchone()[0]
print(f"role_permissions legacy 行数: {n_legacy}")

# 2. permission_set_permissions 行数
n_new = cur.execute('SELECT COUNT(*) FROM permission_set_permissions').fetchone()[0]
print(f"permission_set_permissions 新表行数: {n_new}")

# 3. role_permissions 列清单
print("role_permissions 列清单:")
for r in cur.execute('PRAGMA table_info(role_permissions)').fetchall():
    print(f"  {r[1]:30} {r[2]}")

print("permission_set_permissions 列清单:")
for r in cur.execute('PRAGMA table_info(permission_set_permissions)').fetchall():
    print(f"  {r[1]:30} {r[2]}")

# 4. 取 role_permissions 的 role_id 全部, 验证新表有对应
print()
print("role_permissions.role_id 唯一值:", end=" ")
role_ids = cur.execute('SELECT DISTINCT role_id FROM role_permissions').fetchall()
print(len(role_ids), "个")

# 5. permission_sets 行数
print(f"permission_sets 行数: {cur.execute('SELECT COUNT(*) FROM permission_sets').fetchone()[0]}")

# 6. 关键: 尝试从 role_permissions 取 (role_id, permission_id) 集合,
#    比对 permission_set_permissions 是否有同 (permission_set_id, permission_id) 集合
sample = cur.execute(
    'SELECT role_id, permission_id FROM role_permissions LIMIT 5'
).fetchall()
print()
print("role_permissions sample 5 行 (role_id, permission_id):")
for r in sample:
    print(f"  {r}")

# 对应的 permission_set_id 应该 = role_id (v070 RENAME 时角色记录应一并改名)
# 检查 user_roles / permission_set_permissions 是否含对应 (ps_id, perm_id)
print()
print("user_roles 行数:", cur.execute('SELECT COUNT(*) FROM user_roles').fetchone()[0])
print("user_permission_sets 行数:", cur.execute('SELECT COUNT(*) FROM user_permission_sets').fetchone()[0])

conn.close()
'''


def audit(env: str, db_path: str) -> None:
    print(f'\n=== [{env}] legacy safety audit ===')
    if env == 'prod':
        use_prod_gateway()
    script = INLINE % {'db_path': db_path}
    remote_path = _build_remote_py_helper('v089audit', script)
    r = remote_exec(f'python3 {remote_path} && rm -f {remote_path}', timeout=60)
    if r.get('ok') and r.get('exit_code') == 0:
        print(r.get('stdout', ''))
    else:
        print(f'ERROR: rc={r.get("exit_code")}')
        if r.get('stderr'):
            print('STDERR:', r['stderr'])
        if r.get('stdout'):
            print('STDOUT:', r['stdout'])


if __name__ == '__main__':
    env = sys.argv[1] if len(sys.argv) > 1 else 'prod'
    db_path = (
        '/opt/app/staging/meta/architecture.db'
        if env == 'staging'
        else '/opt/app/deployments/meta/architecture.db'
    )
    audit(env, db_path)