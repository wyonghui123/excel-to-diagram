# 测试 FK 过滤
import requests
import json

# 登录获取 token
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
print(f"Login status: {login_resp.status_code}")
login_data = login_resp.json()

if not login_data.get('success'):
    print("Login failed!")
    exit(1)

token = login_data['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试 1: 获取所有用户组
print("\n=== 测试 1: 获取所有用户组 ===")
resp1 = requests.get(
    'http://localhost:3010/api/v2/bo/user_group',
    params={'page': 1, 'page_size': 5},
    headers=headers
)
data1 = resp1.json()
print(f"Status: {resp1.status_code}")
print(f"Total: {data1.get('data', {}).get('total', 0)}")

# 测试 2: 使用 parent_id=2 过滤（数据库中存在）
print("\n=== 测试 2: parent_id=2 过滤（应该返回 1 条）===")
resp2 = requests.get(
    'http://localhost:3010/api/v2/bo/user_group',
    params={'page': 1, 'page_size': 5, 'parent_id': '2'},
    headers=headers
)
data2 = resp2.json()
print(f"Status: {resp2.status_code}")
print(f"Total: {data2.get('data', {}).get('total', 0)}")
print(f"Items count: {len(data2.get('data', {}).get('items', []))}")
if data2.get('data', {}).get('items'):
    for item in data2['data']['items']:
        print(f"  - id={item.get('id')}, name={item.get('name')}, parent_id={item.get('parent_id')}")

# 测试 3: 使用 parent_id__in=2 过滤
print("\n=== 测试 3: parent_id__in=2 过滤（应该返回 1 条）===")
resp3 = requests.get(
    'http://localhost:3010/api/v2/bo/user_group',
    params={'page': 1, 'page_size': 5, 'parent_id__in': '2'},
    headers=headers
)
data3 = resp3.json()
print(f"Status: {resp3.status_code}")
print(f"Total: {data3.get('data', {}).get('total', 0)}")
print(f"Items count: {len(data3.get('data', {}).get('items', []))}")
if data3.get('data', {}).get('items'):
    for item in data3['data']['items']:
        print(f"  - id={item.get('id')}, name={item.get('name')}, parent_id={item.get('parent_id')}")

# 测试 4: 使用 parent_id__in=2,464 过滤（应该返回 2 条）
print("\n=== 测试 4: parent_id__in=2,464 过滤（应该返回 2 条）===")
resp4 = requests.get(
    'http://localhost:3010/api/v2/bo/user_group',
    params={'page': 1, 'page_size': 5, 'parent_id__in': '2,464'},
    headers=headers
)
data4 = resp4.json()
print(f"Status: {resp4.status_code}")
print(f"Total: {data4.get('data', {}).get('total', 0)}")
print(f"Items count: {len(data4.get('data', {}).get('items', []))}")
if data4.get('data', {}).get('items'):
    for item in data4['data']['items']:
        print(f"  - id={item.get('id')}, name={item.get('name')}, parent_id={item.get('parent_id')}")
