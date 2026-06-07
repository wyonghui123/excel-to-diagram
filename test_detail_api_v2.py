import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 获取用户组详情
print("=== 用户组详情 API (v2) ===")
resp = requests.get(
    'http://localhost:3010/api/v2/bo/user_group/591',
    headers=headers
)
data = resp.json()
if data.get('success'):
    record = data.get('data', {})
    print(f"id: {record.get('id')}")
    print(f"name: {record.get('name')}")
    print(f"parent_id: {record.get('parent_id')}")
    print(f"parent_id_display: {record.get('parent_id_display')}")
    print(f"manager_id: {record.get('manager_id')}")
    print(f"manager_id_display: {record.get('manager_id_display')}")
else:
    print(f"请求失败: {data.get('message')}")
