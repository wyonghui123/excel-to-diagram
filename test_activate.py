import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试激活
print("=== 测试激活用户 ===")
resp = requests.put(
    'http://localhost:3010/api/v2/bo/user/3',
    headers=headers,
    json={'status': 'active'}
)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Response: {data}")

# 重新读取
print("\n=== 重新读取用户 ===")
resp2 = requests.get('http://localhost:3010/api/v2/bo/user/3', headers=headers)
data2 = resp2.json()
if data2.get('success'):
    record = data2.get('data', {})
    print(f"status: {record.get('status')}")
