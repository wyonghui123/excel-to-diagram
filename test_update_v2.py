import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试1: 不发送 type 字段
print("=== 测试1: 不发送 type 字段 ===")
resp1 = requests.put(
    'http://localhost:3010/api/v2/bo/user_group/591',
    headers=headers,
    json={
        'id': 591,
        'name': 'test100',
        'parent_id': 2,
        'manager_id': 3,
    }
)
print(f"Status: {resp1.status_code}")
print(f"Response: {resp1.text[:500]}")

# 测试2: 不发送 parent_id 和 manager_id
print("\n=== 测试2: 不发送 parent_id 和 manager_id ===")
resp2 = requests.put(
    'http://localhost:3010/api/v2/bo/user_group/591',
    headers=headers,
    json={
        'id': 591,
        'name': 'test100',
        'description': 'test',
    }
)
print(f"Status: {resp2.status_code}")
print(f"Response: {resp2.text[:500]}")
