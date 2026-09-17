"""[v19 P2] 真实 staging + prod 数据摸底 — read-only"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from tools.staging_round import (
    remote_exec, remote_upload, use_prod_gateway, GW_PORT,
    _build_remote_py_helper,
)

QUERIES = [
    ('orgs.manager_id 非空行数', "SELECT COUNT(*) FROM orgs WHERE manager_id IS NOT NULL"),
    ('org_members.is_manager=1 行数', "SELECT COUNT(*) FROM org_members WHERE is_manager = 1"),
    ('is_manager=1 详细 (user_id, org_id, is_manager)',
     "SELECT user_id, org_id, is_manager FROM org_members WHERE is_manager = 1 LIMIT 10"),
    ('is_manager=1 关联 user (username)',
     """SELECT u.id, u.username, u.status
        FROM org_members m JOIN users u ON u.id = m.user_id
        WHERE m.is_manager = 1 LIMIT 10"""),
    ('is_manager=1 关联 org (org_id, name)',
     """SELECT o.id, o.name, o.code
        FROM org_members m JOIN orgs o ON o.id = m.org_id
        WHERE m.is_manager = 1 LIMIT 10"""),
    ('orgs 总行数', "SELECT COUNT(*) FROM orgs"),
    ('org_members 总行数', "SELECT COUNT(*) FROM org_members"),
    ('permission_sets 总行数', "SELECT COUNT(*) FROM permission_sets"),
    ('user_groups 表是否存在 (legacy)',
     "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='user_groups'"),
    ('user_group_members 表是否存在 (legacy)',
     "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='user_group_members'"),
    ('roles 表是否存在 (legacy)',
     "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='roles'"),
    ('schema_migrations 已应用总数',
     "SELECT COUNT(*) FROM schema_migrations"),
    ('schema_migrations 列清单',
     "PRAGMA table_info(schema_migrations)"),
    ('已应用迁移 (前5 行)',
     "SELECT * FROM schema_migrations LIMIT 5"),
    ('admin 用户的所有 org_members (org_id, role_name, is_manager)',
     """SELECT om.org_id, om.user_id, om.role, om.is_manager, o.name
        FROM org_members om LEFT JOIN orgs o ON o.id = om.org_id
        WHERE om.user_id = 1"""),
    ('admin 用户名/角色元数据',
     """SELECT id, username, role, is_admin, status FROM users WHERE id = 1"""),
    ('org_members 行示例 (前5)',
     "SELECT * FROM org_members LIMIT 5"),
    ('org_members.is_manager 列缺省值',
     "PRAGMA table_info(org_members)"),
]

INLINE = '''
import sqlite3
QUERIES = %(QUERIES)r
DB_PATH = "%(db_path)s"
conn = sqlite3.connect(DB_PATH, timeout=10)
cur = conn.cursor()
for label, sql in QUERIES:
    try:
        rows = cur.execute(sql).fetchall()
        if not rows:
            print(f"  {label:55} 0 行")
        elif len(rows) == 1 and len(rows[0]) == 1:
            print(f"  {label:55} {rows[0][0]}")
        else:
            print(f"  {label}:")
            for row in rows[:10]:
                print(f"    {row}")
    except sqlite3.OperationalError as e:
        print(f"  {label:55} ERROR: {e}")
    except Exception as e:
        print(f"  {label:55} EXC: {e}")
conn.close()
'''


def probe(env: str, db_path: str) -> None:
    print(f'\n=== [{env}] {db_path} ===')
    if env == 'prod':
        use_prod_gateway()
    script = INLINE % {'QUERIES': QUERIES, 'db_path': db_path}
    remote_path = _build_remote_py_helper('v19audit', script)
    r = remote_exec(f'python3 {remote_path} && rm -f {remote_path}', timeout=60)
    rc = r.get('exit_code')
    if rc == 0:
        print(r.get('stdout', ''))
    else:
        print(f"ERROR: rc={rc}")
        if r.get('stderr'):
            print('STDERR:', r['stderr'])
        if r.get('stdout'):
            print('STDOUT:')
            print(r['stdout'])


if __name__ == '__main__':
    env = sys.argv[1] if len(sys.argv) > 1 else 'staging'
    db_path = (
        '/opt/app/staging/meta/architecture.db'
        if env == 'staging'
        else '/opt/app/deployments/meta/architecture.db'
    )
    probe(env, db_path)