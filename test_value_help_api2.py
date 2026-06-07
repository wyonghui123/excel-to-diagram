import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

url = 'http://localhost:3010/api/v2/value-help/bo/user'

# 测试1: 不带任何过滤，获取前几条
print("=== 测试1: 获取前 5 条用户 ===")
params1 = {
    'page': 1,
    'page_size': 5,
    'value_field': 'id',
    'display_field': 'display_name',
    'code_field': 'username',
}
resp1 = requests.get(url, params=params1, headers=headers)
data1 = resp1.json()
print(f"Status: {resp1.status_code}")
print(f"Total: {data1.get('data', {}).get('total', 0)}")
print(f"Items: {len(data1.get('data', {}).get('items', []))}")
if data1.get('data', {}).get('items'):
    for item in data1['data']['items'][:5]:
        print(f"  - {item}")

# 测试2: 搜索 username 字段
print("\n=== 测试2: 搜索 username ===")
params2 = {
    'search': 'no_pwd',
    'page': 1,
    'page_size': 50,
    'value_field': 'id',
    'display_field': 'display_name',
    'code_field': 'username',
}
resp2 = requests.get(url, params=params2, headers=headers)
data2 = resp2.json()
print(f"Status: {resp2.status_code}")
print(f"Total: {data2.get('data', {}).get('total', 0)}")
print(f"Items: {len(data2.get('data', {}).get('items', []))}")
if data2.get('data', {}).get('items'):
    for item in data2['data']['items'][:3]:
        print(f"  - {item}")

# 测试3: 直接获取用户
print("\n=== 测试3: 直接查询用户 ===")
resp3 = requests.get('http://localhost:3010/api/v2/bo/user', params={'page': 1, 'page_size': 3}, headers=headers)
data3 = resp3.json()
print(f"Status: {resp3.status_code}")
print(f"Total: {data3.get('data', {}).get('total', 0)}")
if data3.get('data', {}).get('items'):
    for item in data3['data']['items'][:3]:
        print(f"  - id={item.get('id')}, username={item.get('username')}, display_name={item.get('display_name')}")
