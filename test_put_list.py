import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试 PUT id=3 with list parent_id
print("=== 测试 PUT list parent_id ===")
resp = requests.put(
    'http://localhost:3010/api/v2/bo/user_group/3',
    headers=headers,
    json={
        'id': 3,
        'name': 'TEST Group 100 edited',
        'parent_id': [1, 2],
        'manager_id': 1,
    }
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")
