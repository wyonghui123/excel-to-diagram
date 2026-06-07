import requests, json
s = requests.Session()
s.get('http://localhost:3004/api/v1/auth/dev-login?username=admin')
r = s.get('http://localhost:3004/api/v1/meta/user_group/list-view')
data = r.json().get('data', {})
columns = data.get('columns', [])
for i, col in enumerate(columns):
    cid = col.get('id', '') or col.get('key', '')
    title = col.get('title', '')
    print(f'  [{i}] {cid} | {title}')
