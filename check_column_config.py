# 检查后端返回的列配置
import requests
import json

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 获取用户组列表配置
resp = requests.get(
    'http://localhost:3010/api/v2/bo/user_group',
    params={'page': 1, 'page_size': 1},
    headers=headers
)
data = resp.json()

# 查找 parent_id 列配置
if data.get('success') and data.get('data', {}).get('columns'):
    columns = data['data']['columns']
    for col in columns:
        if col.get('prop') == 'parent_id':
            print("=== parent_id 列配置 ===")
            print(json.dumps(col, indent=2, ensure_ascii=False))
            break
else:
    print("没有找到 columns 配置")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
