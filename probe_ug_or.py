import requests
r = requests.post('http://localhost:3010/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
cookies = {'auth_token': r.json()['data']['token']}

# 用户组 1 的 audit_logs
r = requests.get('http://localhost:3010/api/v1/audit/logs?object_type=user_group&object_id=1&parent_object_id=1&page=1&page_size=10', cookies=cookies, timeout=5)
data = r.json()
print(f'user_group/1 + parent=1: status={r.status_code} total={data.get("total")}')
for it in data.get('data', [])[:5]:
    print(f'  [{it["id"]}] action={it["action"]:13s} field={it["field_name"]:20s} parent={it["parent_object_type"]}/{it["parent_object_id"]}')

# 用户组 8217
print()
r = requests.get('http://localhost:3010/api/v1/audit/logs?object_type=user_group&object_id=8217&parent_object_id=8217&page=1&page_size=10', cookies=cookies, timeout=5)
data = r.json()
print(f'user_group/8217 + parent=8217: status={r.status_code} total={data.get("total")}')
for it in data.get('data', [])[:5]:
    print(f'  [{it["id"]}] action={it["action"]:13s} field={it["field_name"]:20s} parent={it["parent_object_type"]}/{it["parent_object_id"]}')
