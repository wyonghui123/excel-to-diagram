import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试1: 不带 type 字段
print("=== 测试1: 不带 type 字段 ===")
resp1 = requests.post(
    'http://localhost:3010/api/v2/bo/user_group',
    headers=headers,
    json={
        'code': 'TEST100',
        'name': 'TEST Group 100',
        'parent_id': 1,
        'manager_id': 1,
    }
)
print(f"Status: {resp1.status_code}")
print(f"Response: {resp1.text}")
