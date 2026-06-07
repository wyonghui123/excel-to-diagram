import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

url = 'http://localhost:3010/api/v2/value-help/bo/user'

# 测试1: 不带 value_filter
print("=== 测试1: 不带 value_filter，搜索 'ste' ===")
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
print(f"Total: {data1.get('data', {}).get('total', 0)}")
items1 = data1.get('data', {}).get('data', [])
print(f"Items: {len(items1)}")
if items1:
    for item in items1[:3]:
        print(f"  - {item.get('username')}, {item.get('display_name')}, status={item.get('status')}")

# 测试2: 带 value_filter={"status":"active"}
print("\n=== 测试2: 带 value_filter status=active ===")
params2 = {
    'search': 'ste',
    'search_fields': 'username,display_name',
    'page': 1,
    'page_size': 50,
    'value_field': 'id',
    'display_field': 'display_name',
    'code_field': 'username',
    'value_filter': '{"status":"active"}',
}
resp2 = requests.get(url, params=params2, headers=headers)
data2 = resp2.json()
print(f"Total: {data2.get('data', {}).get('total', 0)}")
items2 = data2.get('data', {}).get('data', [])
print(f"Items: {len(items2)}")
if items2:
    for item in items2[:3]:
        print(f"  - {item.get('username')}, {item.get('display_name')}, status={item.get('status')}")

# 测试3: 查询 no_pwd_d1a3798a 详情
print("\n=== 测试3: 查询 no_pwd_d1a3798a 详情 ===")
import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cur = conn.execute("SELECT id, username, display_name, status FROM users WHERE username='no_pwd_d1a3798a'")
for r in cur.fetchall():
    print(f"  id={r[0]}, username={r[1]}, display_name={r[2]}, status={r[3]}")
conn.close()
