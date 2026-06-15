#!/usr/bin/env python3
import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 查 audit log
r = opener.open('http://localhost:3010/api/v1/audit/logs?page_size=20')
data = json.loads(r.read().decode())
print('type:', type(data['data']).__name__)
print('data:', data['data'] if isinstance(data['data'], dict) else 'list')
if isinstance(data['data'], list):
    for a in data['data'][:10]:
        print(' -', json.dumps(a, ensure_ascii=False)[:200])
elif isinstance(data['data'], dict):
    print(' - items:', len(data['data'].get('items', [])))
    for a in data['data'].get('items', [])[:10]:
        print(' -', json.dumps(a, ensure_ascii=False)[:200])
