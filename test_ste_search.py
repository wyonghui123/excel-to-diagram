import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

url = 'http://localhost:3010/api/v2/value-help/bo/user'

# 测试1: 搜索 "ste" (应该匹配 display_name=steve)
print("=== 测试1: 搜索 'ste' ===")
params1 = {
    'search': 'ste',
    'search_fields': 'username,display_name',
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
    for item in items1[:5]:
        print(f"  - username={item.get('username')}, display_name={item.get('display_name')}")

# 测试2: 搜索 "steve"
print("\n=== 测试2: 搜索 'steve' ===")
params2 = {
    'search': 'steve',
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
    for item in items2[:5]:
        print(f"  - username={item.get('username')}, display_name={item.get('display_name')}")

# 测试3: 不带 search_fields，搜索 'ste'
print("\n=== 测试3: 不带 search_fields，搜索 'ste' ===")
params3 = {
    'search': 'ste',
    'page': 1,
    'page_size': 50,
    'value_field': 'id',
    'display_field': 'display_name',
    'code_field': 'username',
}
resp3 = requests.get(url, params=params3, headers=headers)
data3 = resp3.json()
print(f"Status: {resp3.status_code}")
print(f"Total: {data3.get('data', {}).get('total', 0)}")
items3 = data3.get('data', {}).get('data', [])
print(f"Items count: {len(items3)}")
