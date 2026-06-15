#!/usr/bin/env python3
"""[BMRD 2026-06-14] 查 TEST888 用户 + audit log"""
import urllib.request, http.cookiejar, json, urllib.error

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 1. /users/me
print('=== /users/me ===')
r = opener.open('http://localhost:3010/api/v1/users/me')
data = json.loads(r.read().decode())['data']
print(f'  id={data.get("id")} username={data.get("username")}')

# 2. 查 audit log 最近 20 条
print('\n=== /audit/logs 最近 20 ===')
try:
    r = opener.open('http://localhost:3010/api/v1/audit/logs?page_size=20')
    data = json.loads(r.read().decode())['data']
    items = data.get('items', [])
    print(f'  total: {data.get("total")}')
    for a in items[:20]:
        ts = a.get('created_at', '')
        op = a.get('operation', '')
        obj = a.get('object_type', '')
        oid = a.get('object_id', '')
        user = a.get('user_id', '')
        st = a.get('status', '')
        print(f'  {ts[:19]} {st:6} {op:10} {obj:15} {oid:5} user={user}')
except urllib.error.HTTPError as e:
    print(f'  err: {e.code} {e.read().decode()[:200]}')
