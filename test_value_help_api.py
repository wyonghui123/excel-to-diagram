import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试搜索 API（带 value_filter）
print("=== 测试1: 带 value_filter 的搜索 ===")
url = 'http://localhost:3010/api/v2/value-help/bo/user'
params = {
    'search': 'no_pwd_d1a3798a',
    'page': 1,
    'page_size': 50,
    'value_field': 'id',
    'display_field': 'display_name',
    'code_field': 'username',
    'value_filter': '{"status":"active"}'
}
resp = requests.get(url, params=params, headers=headers)
data = resp.json()
print(f"Status: {resp.status_code}")
print(f"Total: {data.get('data', {}).get('total', 0)}")
print(f"Items: {len(data.get('data', {}).get('items', []))}")
if data.get('data', {}).get('items'):
    for item in data['data']['items'][:3]:
        print(f"  - {item}")

# 测试搜索 API（不带 value_filter）
print("\n=== 测试2: 不带 value_filter 的搜索 ===")
params2 = {
    'search': 'no_pwd_d1a3798a',
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
