import urllib.request, json

# 登录
req1 = urllib.request.Request(
    'http://localhost:3010/api/v1/auth/login',
    data=json.dumps({'username': 'admin', 'password': 'admin123'}).encode(),
    headers={'Content-Type': 'application/json'}
)
token = json.loads(urllib.request.urlopen(req1).read().decode())['data']['token']

# v2 API
req2 = urllib.request.Request(
    'http://localhost:3010/api/v2/meta/user_group/view-config/default',
    headers={'Authorization': f'Bearer {token}'}
)
resp = json.loads(urllib.request.urlopen(req2).read().decode())
data = resp.get('data', {})

print("Top-level keys:", list(data.keys()))

if 'list' in data:
    list_config = data['list']
    print("list keys:", list(list_config.keys()))
    
    if 'columns' in list_config:
        for c in list_config['columns']:
            if c.get('prop') == 'parent_id' or c.get('key') == 'parent_id':
                vhc = c.get('value_help_config')
                if vhc:
                    print(f"\nparent_id value_help_config.behavior.multiple = {vhc.get('behavior', {}).get('multiple')}")
                    print(f"parent_id value_help_config.behavior keys: {list(vhc.get('behavior', {}).keys())}")
                else:
                    print("No value_help_config")
                break

if 'fields' in data:
    print(f"\nTop-level fields count: {len(data['fields'])}")
    for f in data['fields']:
        key = f.get('id', f.get('key', ''))
        if key == 'parent_id':
            vh = f.get('value_help')
            if vh:
                print(f"  parent_id value_help.behavior.multiple = {vh.get('behavior', {}).get('multiple')}")
            break
