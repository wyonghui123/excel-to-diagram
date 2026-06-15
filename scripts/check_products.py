#!/usr/bin/env python3
"""检查 TEST888121, TEST888122, TEST99999 及其版本"""
import urllib.request, http.cookiejar, json

def check(name):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')
    r = op.open(f'http://localhost:3010/api/v2/bo/product?name={name}')
    products = json.loads(r.read().decode())['data']['items']
    print(f'{name}: {len(products)} found')
    for p in products:
        pid = p['id']
        r2 = op.open(f'http://localhost:3010/api/v2/bo/version?product_id={pid}&page_size=20')
        versions = json.loads(r2.read().decode())['data']['items']
        print(f'  id={pid} name={p["name"]} versions={len(versions)}')
        for v in versions:
            print(f'    - id={v["id"]} name={v["name"]}')

for name in ['TEST888121', 'TEST888122', 'TEST99999']:
    check(name)
