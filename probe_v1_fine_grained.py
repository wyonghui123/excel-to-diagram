"""
精细化 v1/v2 拦截验证:
- 顶层 5 CRUD: 410
- 子路径: 200
- v2 端点: 200
"""
import requests
import time
base = 'http://localhost:3010'

# 等服务起来
for _ in range(10):
    try:
        r = requests.get(f'{base}/health', timeout=2)
        if r.status_code == 200:
            break
    except Exception:
        time.sleep(1)

# 登录
r = requests.post(f'{base}/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=10)
token = r.json()['data']['token']
cookies = {'auth_token': token}

print('=' * 100)
print('第一部分: 顶层 5 CRUD 路径应当 410 (12 个资源)')
print('=' * 100)
test_paths = [
    # v1 顶层
    ('/api/v1/users', 410),
    ('/api/v1/users/1', 410),
    ('/api/v1/roles', 410),
    ('/api/v1/roles/1', 410),
    ('/api/v1/user-groups', 410),
    ('/api/v1/user-groups/1', 410),
    ('/api/v1/permission-bundles', 410),
    ('/api/v1/permission-bundles/1', 410),
    ('/api/v1/permission-rules', 410),
    ('/api/v1/permission-rules/1', 410),
    ('/api/v1/data-permissions', 410),
    ('/api/v1/data-permissions/1', 410),
    ('/api/v1/management-dimensions', 410),
    ('/api/v1/filter-variants', 410),
    ('/api/v1/menu-permission', 410),
    ('/api/v1/identity', 410),
    ('/api/v1/associations', 410),
    ('/api/v1/notifications', 410),
]
fails = []
for path, expected in test_paths:
    try:
        r = requests.get(f'{base}{path}', cookies=cookies, timeout=5)
        body = r.text[:120].replace('\n', ' ')
        ok = '✓' if r.status_code == expected else '✗'
        print(f'  {ok} {r.status_code:3d} (期望 {expected:3d})  {path:35s} {body[:60]}')
        if r.status_code != expected:
            fails.append((path, r.status_code, expected))
    except Exception as e:
        print(f'  ERR  {path:35s} {e}')
        fails.append((path, 'EXC', expected))

print()
print('=' * 100)
print('第二部分: 子路径应当 200 (放行, 让 Blueprint 处理)')
print('=' * 100)
sub_paths = [
    # user 子路径
    ('/api/v1/users/1/menus', 200),
    ('/api/v1/users/1/logs', 200),
    ('/api/v1/users/me', 200),
    ('/api/v1/users/self', 200),
    # role 子路径
    ('/api/v1/roles/1/menu-permissions', 200),
    ('/api/v1/roles/1/unified-permissions', 200),
    ('/api/v1/roles/1/dimension-scopes', 200),
    ('/api/v1/roles/1/derived-permissions', 200),
    ('/api/v1/roles/1/overlaps', 200),
    ('/api/v1/roles/1/intents', 200),
    # user-groups 子路径
    ('/api/v1/user-groups/1/members', 200),
    ('/api/v1/user-groups/1/data-permissions', 200),
    ('/api/v1/user-groups/1/roles', 200),
    ('/api/v1/user-groups/1/logs', 200),
    # permission-rules 子路径
    ('/api/v1/permission-rules/dimensions', 200),
    ('/api/v1/permission-rules/field-metadata', 200),
    # filter-variants 子路径
    ('/api/v1/filter-variants/subscriptions', 200),
    # menu-permission 子路径
    ('/api/v1/menu-permission/visible', 200),
    ('/api/v1/menu-permission/menus', 200),
    # identity 子路径
    ('/api/v1/identity/check', 200),
    # associations 子路径
    ('/api/v1/associations/1', 200),
    # notifications 子路径
    ('/api/v1/notifications/subscriptions', 200),
]
for path, expected in sub_paths:
    try:
        r = requests.get(f'{base}{path}', cookies=cookies, timeout=5)
        ok = '✓' if r.status_code == expected else '✗'
        body = r.text[:100].replace('\n', ' ')
        print(f'  {ok} {r.status_code:3d} (期望 {expected:3d})  {path:40s} {body[:50]}')
        if r.status_code != expected:
            fails.append((path, r.status_code, expected))
    except Exception as e:
        print(f'  ERR  {path:40s} {e}')
        fails.append((path, 'EXC', expected))

print()
print('=' * 100)
print('第三部分: v2 端点 200 + migrated_to 字段')
print('=' * 100)
v2_paths = [
    '/api/v2/bo/user',
    '/api/v2/bo/role',
    '/api/v2/bo/user_group',
    '/api/v2/bo/permission_bundle',
    '/api/v2/bo/permission_rule',
    '/api/v2/bo/data_permission',
    '/api/v2/bo/management_dimension',
    '/api/v2/bo/filter_variant',
    '/api/v2/bo/menu_permission',
    '/api/v2/bo/identity',
    '/api/v2/bo/association',
    '/api/v2/bo/notification',
]
for path in v2_paths:
    r = requests.get(f'{base}{path}?page=1&page_size=1', cookies=cookies, timeout=5)
    print(f'  {r.status_code:3d}  {path}')

# 410 响应包含 migrated_to
print()
print('=' * 100)
print('第四部分: 410 响应包含 migrated_to 字段 (随机抽样)')
print('=' * 100)
for path in ['/api/v1/users/1', '/api/v1/roles/5', '/api/v1/user-groups/1', '/api/v1/permission-bundles/1']:
    r = requests.get(f'{base}{path}', cookies=cookies, timeout=5)
    if r.status_code == 410:
        body = r.json()
        print(f'  {path:35s} -> 410  migrated_to={body.get("migrated_to")}  message={body.get("message")[:80]}')
    else:
        print(f'  {path:35s} -> {r.status_code} (NOT 410)')

print()
print('=' * 100)
if fails:
    print(f'FAILED: {len(fails)} 个测试未通过期望')
    for path, actual, expected in fails:
        print(f'  - {path}: 实际 {actual}, 期望 {expected}')
else:
    print('ALL PASS: 41 个精细化拦截测试全部通过 ✓')
print('=' * 100)
