import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试 PUT id=3 (TEST Group 100)
print("=== 测试 PUT user_group/3 ===")
resp = requests.put(
    'http://localhost:3010/api/v2/bo/user_group/3',
    headers=headers,
    json={
        'id': 3,
        'name': 'TEST Group 100 edited',
        'parent_id': 1,
        'manager_id': 1,
    }
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")
