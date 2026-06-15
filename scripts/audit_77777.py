#!/usr/bin/env python3
"""深入排查: 查询 TEST77777 的创建历史 (audit log)"""
import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 1. 查询 TEST77777 当前所有记录
r = op.open('http://localhost:3010/api/v2/bo/product?name=TEST77777')
data = json.loads(r.read().decode())
products = data.get('data', {}).get('items', [])
print(f'=== TEST77777 当前状态 ===')
print(f'  产品数: {len(products)}')
for p in products:
    pid = p['id']
    print(f'  - id={pid} name={p["name"]} code={p.get("code")} created_at={p.get("created_at")}')

# 2. 查询 audit log
print(f'\n=== TEST77777 audit log ===')
r = op.open('http://localhost:3010/api/v1/audit/logs?object_type=product&action=create&page=1&page_size=20')
try:
    logs = json.loads(r.read().decode()).get('data', {}).get('items', [])
    for log in logs:
        if 'TEST77777' in str(log):
            print(f'  - {log.get("created_at")} action={log.get("action")} user={log.get("user_id")} obj_id={log.get("object_id")} name={log.get("object_name")}')
except Exception as e:
    print(f'  audit log 查询失败: {e}')

# 3. 搜索所有 TEST 开头的
print(f'\n=== TEST77777 相关所有产品 (模糊搜索) ===')
r = op.open('http://localhost:3010/api/v2/bo/product?page_size=100&name=TEST77777')
try:
    data = json.loads(r.read().decode())
    items = data.get('data', {}).get('items', [])
    for p in items:
        print(f'  - id={p["id"]} name={p["name"]} code={p.get("code")}')
except Exception as e:
    print(f'  查询失败: {e}')

# 4. 用 code 字段搜索
print(f'\n=== code=TEST77777 搜索 ===')
try:
    r = op.open('http://localhost:3010/api/v2/bo/product?code=TEST77777')
    data = json.loads(r.read().decode())
    items = data.get('data', {}).get('items', [])
    print(f'  count: {len(items)}')
    for p in items:
        print(f'  - id={p["id"]} name={p["name"]} code={p.get("code")}')
except Exception as e:
    print(f'  失败: {e}')
