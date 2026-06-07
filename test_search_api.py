import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

url = 'http://localhost:3010/api/v2/value-help/bo/user'

# 测试1: 不带 search_fields
print("=== 测试1: 不带 search_fields ===")
params1 = {
    'search': 'no_pwd_d1a3798a',
    'page': 1,
    'page_size': 50,
    'value_field': 'id',
    'display_field': 'display_name',
    'code_field': 'username',
}
resp1 = requests.get(url, params=params1, headers=headers)
data1 = resp1.json()
print(f"Status: {resp1.status_code}")
print(f"Total: {data1.get('data', {}).get('total', 0)}")
items1 = data1.get('data', {}).get('data', [])
print(f"Items count: {len(items1)}")
if items1:
    for item in items1[:3]:
        print(f"  - username={item.get('username')}, display_name={item.get('display_name')}")

# 测试2: 带 search_fields
print("\n=== 测试2: 带 search_fields ===")
params2 = {
    'search': 'no_pwd_d1a3798a',
    'search_fields': 'username,display_name',
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
items2 = data2.get('data', {}).get('data', [])
print(f"Items count: {len(items2)}")
if items2:
    for item in items2[:3]:
        print(f"  - username={item.get('username')}, display_name={item.get('display_name')}")
