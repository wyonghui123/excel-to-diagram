import requests

# 登录
login_resp = requests.post(
    'http://localhost:3010/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin123'}
)
token = login_resp.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

# 测试 value help resolve
print("=== 测试 value help resolve user_group/1 ===")
resp = requests.get(
    'http://localhost:3010/api/v2/value-help/bo/user_group/resolve',
    headers=headers,
    params={'value': 1, 'value_field': 'id', 'display_field': 'name', 'code_field': 'code'}
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")

print("\n=== 测试 value help resolve user/1 ===")
resp = requests.get(
    'http://localhost:3010/api/v2/value-help/bo/user/resolve',
    headers=headers,
    params={'value': 1, 'value_field': 'id', 'display_field': 'display_name', 'code_field': 'username'}
)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")
