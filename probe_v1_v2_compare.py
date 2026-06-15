"""
v1 vs v2 端点对比 + 主表 CRUD 路径探测
"""
import requests
base = 'http://localhost:3010'
r = requests.post(f'{base}/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=10)
token = r.json()['data']['token']
cookies = {'auth_token': token}

# 1. v1 vs v2 响应对比
print('=== v1 vs v2 主表 CRUD 对比 ===')
for v1_path, v2_path in [
    ('/api/v1/users', '/api/v2/bo/user'),
    ('/api/v1/roles', '/api/v2/bo/role'),
    ('/api/v1/user-groups', '/api/v2/bo/user_group'),
    ('/api/v1/permission-bundles', '/api/v2/bo/permission_bundle'),
    ('/api/v1/data-permissions', '/api/v2/bo/data_permission'),
    ('/api/v1/identity', '/api/v2/bo/identity'),
    ('/api/v1/notifications', '/api/v2/bo/notification'),
    ('/api/v1/associations', '/api/v2/bo/association'),
    ('/api/v1/filter-variants', '/api/v2/bo/filter_variant'),
    ('/api/v1/menu-permission', '/api/v2/bo/menu_permission'),
]:
    try:
        r1 = requests.get(f'{base}{v1_path}?page=1&page_size=2', cookies=cookies, timeout=5)
        r2 = requests.get(f'{base}{v2_path}?page=1&page_size=2', cookies=cookies, timeout=5)
        v1_data_shape = type(r1.json().get('data')).__name__ if r1.status_code == 200 else 'N/A'
        v2_data_shape = type(r2.json().get('data')).__name__ if r2.status_code == 200 else 'N/A'
        print(f'  v1 {v1_path:30s} -> {r1.status_code}  data={v1_data_shape}')
        print(f'  v2 {v2_path:30s} -> {r2.status_code}  data={v2_data_shape}')
    except Exception as e:
        print(f'  v1 {v1_path:30s} -> ERROR: {e}')
    print()

# 2. 探测 v1 主表 CRUD 端点当前响应（验证是否被 manage_bp 接管）
print('=== 验证 v1 主表 CRUD 端点状态 ===')
for path in [
    '/api/v1/users',
    '/api/v1/roles',
    '/api/v1/user-groups',
    '/api/v1/user-groups/1',
    '/api/v1/permission-bundles',
    '/api/v1/data-permissions',
    '/api/v1/identity',
    '/api/v1/notifications',
    '/api/v1/associations',
    '/api/v1/filter-variants',
    '/api/v1/menu-permission',
    '/api/v1/admin/permissions',
    '/api/v1/admin/owner',
    '/api/v1/system/database',
    '/api/v1/management-dimensions',
]:
    try:
        r = requests.get(f'{base}{path}', cookies=cookies, timeout=5)
        body = r.text[:80].replace('\n', ' ')
        print(f'  {r.status_code:3d}  {path:30s} {body}')
    except Exception as e:
        print(f'  ERR  {path:30s} {e}')
