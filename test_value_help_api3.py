import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

url = 'http://localhost:3010/api/v2/value-help/bo/user'

# 测试1: 获取数据
params = {
    'page': 1,
    'page_size': 5,
    'value_field': 'id',
    'display_field': 'display_name',
    'code_field': 'username',
}
resp = requests.get(url, params=params, headers=headers)
data = resp.json()

print("=== 完整响应 ===")
print(data)

print("\n=== 解析 data 字段 ===")
print(f"data type: {type(data.get('data'))}")
print(f"data keys: {data.get('data', {}).keys() if isinstance(data.get('data'), dict) else 'N/A'}")
