import json, urllib.request
cookies = json.load(open(r'd:\filework\excel-to-diagram\e2e\.auth\admin.json', encoding='utf-8'))
auth = next(c['value'] for c in cookies['cookies'] if c['name'] == 'auth_token')

# Check users for 管理员
req = urllib.request.Request('http://localhost:3010/api/v2/bo/user?page_size=100', headers={'Cookie': f'auth_token={auth}'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read().decode())
items = data.get('data', {}).get('items', data.get('data', []))
print('=== Users matching 管理员 ===')
for u in items:
    name = u.get('name', '') or u.get('display_name', '') or ''
    if '管理员' in name or 'admin' in name.lower():
        print(f"  id={u.get('id')} name={name}")
print(f'Total users: {len(items)}')

# Check user_groups for 系统管理员
req2 = urllib.request.Request('http://localhost:3010/api/v2/bo/user_group?page_size=200', headers={'Cookie': f'auth_token={auth}'})
resp2 = urllib.request.urlopen(req2)
data2 = json.loads(resp2.read().decode())
items2 = data2.get('data', {}).get('items', data2.get('data', []))
print('=== User Groups matching 系统 ===')
for g in items2:
    name = g.get('name', '') or ''
    if '系统' in name or 'admin' in name.lower():
        print(f"  id={g.get('id')} name={name}")
print(f'Total user_groups: {len(items2)}')
