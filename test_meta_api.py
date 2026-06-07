import requests
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 获取元数据
print("=== 获取元数据 ===")
resp = requests.get(
    'http://localhost:3010/api/v2/meta/user_group/view-config/default',
    headers=headers
)
data = resp.json()
if data.get('success'):
    config = data.get('data', {})
    fields = config.get('fields', [])
    print(f"fields 数量: {len(fields)}")
    for field in fields[:5]:
        print(f"  - {field.get('id')}: {field.get('type')}")
        vh = field.get('value_help')
        if vh:
            print(f"    value_help: {vh}")
