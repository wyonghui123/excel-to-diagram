import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 获取一个用户详情
print("=== 用户详情（id=3 no_pwd_d1a3798a）===")
resp = requests.get('http://localhost:3010/api/v2/bo/user/3', headers=headers)
data = resp.json()
if data.get('success'):
    record = data.get('data', {})
    print(f"username: {record.get('username')}")
    print(f"status: {record.get('status')}")
    print(f"\n所有字段: {list(record.keys())}")

# 测试 state_transitions API
print("\n=== State Transitions API ===")
resp2 = requests.get('http://localhost:3010/api/v2/bo/user/3/state_transitions', headers=headers)
print(f"Status: {resp2.status_code}")
data2 = resp2.json()
print(f"Response: {data2}")
