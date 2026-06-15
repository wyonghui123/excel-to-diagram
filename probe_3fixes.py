"""
3 项修复点 E2E 验证:
1. P0-1: user_group_member 创建后 parent_object_type/user_group 正确填
2. P0-2: /audit/logs 默认过滤掉 __audit_failure__, admin 用 include_internal=true 可恢复
3. P2-1: status=failed 归零 (DB 已确认, 这里再验)
"""
import requests
import time
import sqlite3

base = 'http://localhost:3010'
r = requests.post(f'{base}/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
cookies = {'auth_token': r.json()['data']['token']}
print(f'Login: {r.status_code}')

# ============================================================
# 验证 1: P0-1 user_group_member parent 修复
# ============================================================
print('\n' + '=' * 80)
print('验证 1: P0-1 user_group_member parent 修复')
print('=' * 80)

# 找一个用户组和用户
r = requests.get(f'{base}/api/v2/bo/user_group?page=1&page_size=1', cookies=cookies, timeout=5)
group_id = r.json()['data']['items'][0]['id'] if r.json()['data']['items'] else None
r = requests.get(f'{base}/api/v2/bo/user?page=1&page_size=1', cookies=cookies, timeout=5)
user_id = r.json()['data']['items'][0]['id'] if r.json()['data']['items'] else None
print(f'使用 group_id={group_id}, user_id={user_id}')

# 走 v1 管理 API 添加成员 (用 manage_service 路径, 会写 audit)
ts = int(time.time())
r = requests.post(f'{base}/api/v1/user-groups/{group_id}/members',
    cookies=cookies,
    json={'user_id': user_id + 1000, 'is_manager': False},  # 假设 user_id+1000 不存在
    timeout=5)
print(f'POST members: {r.status_code} {r.text[:200]}')

# 不行的话, 直接通过 manage_api 走 manage_service 路径
# user_group_member 没单独 CRUD, 但 manage_bp 通用路由应该可以
# 试 manage_bp
r = requests.post(f'{base}/api/v1/user_group_member',
    cookies=cookies,
    json={'user_id': 99, 'group_id': group_id, 'is_manager': False},
    timeout=5)
print(f'POST user_group_member (catch-all): {r.status_code} {r.text[:200]}')

# 直接看 DB: 最新一条 user_group_member 的 audit
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("""
    SELECT id, object_id, action, parent_object_type, parent_object_id, field_name
    FROM audit_logs
    WHERE object_type = 'user_group_member'
    ORDER BY id DESC LIMIT 5
""")
print('\n最新 5 条 user_group_member audit:')
for row in cur.fetchall():
    print(f'  [{row[0]}] ugm/{row[1]} action={row[2]:7s} parent={row[3]}/{row[4]!s:5} field={row[5]}')

# 检查最新的 parent 字段
cur.execute("""
    SELECT
        SUM(CASE WHEN parent_object_type='user_group' THEN 1 ELSE 0 END) as has_parent,
        SUM(CASE WHEN parent_object_id IS NULL OR parent_object_id = '' THEN 1 ELSE 0 END) as no_parent
    FROM audit_logs
    WHERE object_type = 'user_group_member'
""")
row = cur.fetchone()
print(f'\nugm 总: {row[0]+row[1]}, 有 parent: {row[0]}, 无 parent: {row[1]}')

# ============================================================
# 验证 2: P0-2 __audit_failure__ 过滤
# ============================================================
print('\n' + '=' * 80)
print('验证 2: P0-2 __audit_failure__ 过滤')
print('=' * 80)

# 2a: 不带 include_internal
r = requests.get(f'{base}/api/v1/audit/logs?object_type=__audit_failure__&page=1&page_size=3', cookies=cookies, timeout=5)
print(f'\n  query: object_type=__audit_failure__ (无 include_internal)')
print(f'  status: {r.status_code}, total: {r.json().get("total", "?")}')

# 2b: 带 include_internal=true
r = requests.get(f'{base}/api/v1/audit/logs?object_type=__audit_failure__&page=1&page_size=3&include_internal=true', cookies=cookies, timeout=5)
data = r.json()
print(f'\n  query: object_type=__audit_failure__ + include_internal=true')
print(f'  status: {r.status_code}, total: {data.get("total", "?")}, items: {len(data.get("data", []))}')

# 2c: domain/683 默认查询, 应当不含 __audit_failure__
r = requests.get(f'{base}/api/v1/audit/logs?object_type=domain&object_id=683&parent_object_id=683&page=1&page_size=3', cookies=cookies, timeout=5)
data = r.json()
print(f'\n  query: object_type=domain&object_id=683&parent_object_id=683 (无 include_internal)')
print(f'  status: {r.status_code}, total: {data.get("total", "?")}')
has_af = any(it.get('object_type') == '__audit_failure__' for it in data.get('data', []))
print(f'  含 __audit_failure__ 记录: {has_af} (期望 False)')

# 2d: domain/683 include_internal=true, 应当含 __audit_failure__
r = requests.get(f'{base}/api/v1/audit/logs?object_type=domain&object_id=683&parent_object_id=683&page=1&page_size=3&include_internal=true', cookies=cookies, timeout=5)
data = r.json()
print(f'\n  query: + include_internal=true')
print(f'  status: {r.status_code}, total: {data.get("total", "?")}')

# ============================================================
# 验证 3: P2-1 status=failed 归零
# ============================================================
print('\n' + '=' * 80)
print('验证 3: P2-1 status=failed 归零')
print('=' * 80)
cur.execute("SELECT COUNT(*) FROM audit_logs WHERE status='failed'")
print(f'  当前 status=failed: {cur.fetchone()[0]} (期望 0)')
cur.execute("SELECT COUNT(*) FROM audit_logs WHERE error_message LIKE '%migrated 2026-06-15%'")
print(f'  migrated 标记: {cur.fetchone()[0]} (期望 8)')

# 业务抽样
print('\n' + '=' * 80)
print('业务抽样: 整体 audit 统计')
print('=' * 80)
cur.execute("SELECT status, COUNT(*) FROM audit_logs GROUP BY status ORDER BY 2 DESC")
for row in cur.fetchall():
    print(f'  {row[0]:15s} {row[1]:5d}')

conn.close()
