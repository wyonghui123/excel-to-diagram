import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 获取列表
print("=== 用户组列表 API（查找有 FK 值的记录）===")
resp = requests.get(
    'http://localhost:3010/api/v2/bo/user_group',
    params={'page': 1, 'page_size': 20},
    headers=headers
)
data = resp.json()
if data.get('success'):
    items = data.get('data', {}).get('items', [])
    found = False
    for item in items:
        if item.get('parent_id') is not None or item.get('manager_id') is not None:
            print(f"id: {item.get('id')}")
            print(f"parent_id: {item.get('parent_id')}")
            print(f"parent_id_display: {item.get('parent_id_display')}")
            print(f"manager_id: {item.get('manager_id')}")
            print(f"manager_id_display: {item.get('manager_id_display')}")
            print(f"\n所有字段: {list(item.keys())}")
            found = True
            break
    if not found:
        print("没找到有 FK 值的记录")
else:
    print(f"请求失败: {data.get('message')}")
