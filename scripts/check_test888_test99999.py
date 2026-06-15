#!/usr/bin/env python3
"""[BMRD 2026-06-14] 检查 TEST99999 + TEST888 用户"""
import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 1. 找 TEST99999
print('=== TEST99999 product ===')
r = opener.open('http://localhost:3010/api/v2/bo/product?page_size=50')
data = json.loads(r.read().decode())['data']['items']
for p in data:
    name = str(p.get('name', ''))
    if 'TEST99999' in name or 'TEST999' in name:
        pid = p.get('id')
        print(f'  id={pid} name={name} code={p.get("code")}')
        # 查 version
        r2 = opener.open(f'http://localhost:3010/api/v2/bo/version?product_id={pid}&page_size=20')
        vs = json.loads(r2.read().decode())['data']['items']
        print(f'  versions: {len(vs)}')
        for v in vs:
            print(f'    - id={v.get("id")} name={v.get("name")} created_by={v.get("created_by")}')

# 2. 找 TEST888 用户
print('\n=== TEST888 用户 ===')
r = opener.open('http://localhost:3010/api/v1/users?page_size=50')
try:
    data = json.loads(r.read().decode())
    if data.get('data'):
        for u in data['data'].get('items', []):
            if 'TEST888' in str(u.get('username', '')) or 'test888' in str(u.get('username', '')):
                print(f'  - id={u.get("id")} username={u.get("username")} name={u.get("name")}')
except Exception as e:
    print(f'  err: {e}')

# 3. 全部 users
print('\n=== 所有用户 ===')
r = opener.open('http://localhost:3010/api/v1/users?page_size=20')
try:
    data = json.loads(r.read().decode())
    if data.get('data'):
        for u in data['data'].get('items', []):
            print(f'  - id={u.get("id")} username={u.get("username")}')
    else:
        print(f'  body: {data.get("message")}')
except Exception as e:
    print(f'  err: {e}')
