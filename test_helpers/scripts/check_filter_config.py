import requests
import json
s = requests.Session()
s.get('http://localhost:3004/api/v1/auth/dev-login?username=admin')
r = s.get('http://localhost:3004/api/v1/meta/user_group/list-view')
data = r.json().get('data', {})
columns = data.get('columns', [])
for col in columns:
    cid = col.get('id', '') or col.get('key', '')
    if cid in ['parent_id', 'manager_id']:
        print(f'\n=== {cid} ===')
        vh = col.get('value_help_config', {})
        print(json.dumps(vh, ensure_ascii=False, indent=2)[:800])
