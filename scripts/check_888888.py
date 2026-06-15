#!/usr/bin/env python3
import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 登录 admin
op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 查询 TEST888888
r = op.open('http://localhost:3010/api/v2/bo/product?name=TEST888888')
data = json.loads(r.read().decode())
products = data.get('data', {}).get('items', [])

print(f'TEST888888 产品数: {len(products)}')
for p in products:
    pid = p['id']
    print(f'  产品 ID={pid}, name={p["name"]}, code={p.get("code", "N/A")}')
    
    # 查询该产品下的版本
    r2 = op.open(f'http://localhost:3010/api/v2/bo/version?product_id={pid}&page_size=20')
    vdata = json.loads(r2.read().decode())
    versions = vdata.get('data', {}).get('items', [])
    print(f'  版本数: {len(versions)}')
    for v in versions:
        print(f'    - id={v["id"]} name={v["name"]} value={v.get("value", "N/A")}')
