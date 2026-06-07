import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试锁定
print("=== 测试锁定用户（当前 active）===")
resp = requests.put(
    'http://localhost:3010/api/v2/bo/user/3',
    headers=headers,
    json={'status': 'locked'}
)
print(f"Status: {resp.status_code}")
data = resp.json()
record = data.get('data', {})
print(f"New status: {record.get('status')}")

# 重新读取
print("\n=== 重新读取用户 ===")
resp2 = requests.get('http://localhost:3010/api/v2/bo/user/3', headers=headers)
data2 = resp2.json()
record2 = data2.get('data', {})
print(f"Status: {record2.get('status')}")

# 测试停用
print("\n=== 测试停用用户（当前 locked）===")
resp3 = requests.put(
    'http://localhost:3010/api/v2/bo/user/3',
    headers=headers,
    json={'status': 'inactive'}
)
print(f"Status: {resp3.status_code}")
data3 = resp3.json()
record3 = data3.get('data', {})
print(f"New status: {record3.get('status')}")

# 重新读取
print("\n=== 重新读取用户 ===")
resp4 = requests.get('http://localhost:3010/api/v2/bo/user/3', headers=headers)
data4 = resp4.json()
record4 = data4.get('data', {})
print(f"Status: {record4.get('status')}")
