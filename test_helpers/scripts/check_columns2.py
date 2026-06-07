import requests, json
s = requests.Session()
s.get('http://localhost:3004/api/v1/auth/dev-login?username=admin')
r = s.get('http://localhost:3004/api/v1/meta/user_group/list-view')
data = r.json().get('data', {})
columns = data.get('columns', [])
for i, col in enumerate(columns):
    cid = col.get('id', '') or col.get('key', '')
    title = col.get('title', '')
    vh = col.get('value_help_config') or {}
    src = vh.get('source', {}) if vh else {}
    target = src.get('target_bo', '') if src else ''
    df = src.get('display_field', '') if src else ''
    print(f'  [{i}] id={cid!r} | title={title!r} | vh.target_bo={target!r}, vh.display_field={df!r}')
