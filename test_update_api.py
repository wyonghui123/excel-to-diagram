import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 模拟编辑态保存
print("=== 测试更新用户组（带空 parent_id） ===")
resp = requests.put(
    'http://localhost:3010/api/v2/bo/user_group/591',
    headers=headers,
    json={
        'type': 'user_group',
        'id': 591,
        'name': 'test100',
        'parent_id': None,  # 编辑态显示空
        'manager_id': None,  # 编辑态显示空
        'description': 'test',
    }
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

print("\n=== 测试更新用户组（不发送 FK 字段） ===")
resp2 = requests.put(
    'http://localhost:3010/api/v2/bo/user_group/591',
    headers=headers,
    json={
        'type': 'user_group',
        'id': 591,
        'name': 'test100',
        'description': 'test',
    }
)
print(f"Status: {resp2.status_code}")
print(f"Response: {resp2.text}")
