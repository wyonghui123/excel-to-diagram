import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试创建
print("=== 测试创建 user_group ===")
resp = requests.post(
    'http://localhost:3010/api/v2/bo/user_group',
    headers=headers,
    json={
        'type': 'user_group',
        'code': 'TEST001',
        'name': 'TEST Group',
        'parent_id': 1,
        'manager_id': 1,
    }
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")
