#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询业务对象 E2E_* 状态"""
import urllib.request
import http.cookiejar
import json

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

resp = opener.open('http://localhost:3010/api/v2/bo/business_object?version_id=2&page_size=100')
data = json.loads(resp.read().decode('utf-8-sig'))
items = data.get('data', {}).get('items', [])
total = data.get('data', {}).get('total')
print(f'Total: {total}, returned: {len(items)}')
print('First 3 items keys:', list(items[0].keys()) if items else 'none')
print()
print('Recent E2E_* BOs:')
e2e_items = [it for it in items if it.get('code', '').startswith('E2E_')]
e2e_items.sort(key=lambda x: x.get('created_at') or '', reverse=True)
for it in e2e_items[:15]:
    code = it.get('code') or ''
    name = it.get('name') or ''
    bid = it.get('id')
    vid = it.get('version_id')
    cat = it.get('created_at') or ''
    print(f'  id={bid} v={vid} {code:30s} {name:30s} created={cat}')

# 检查分页：默认 1 页 20 条？查前 5 条
print()
print('Test default page=1, page_size=20:')
resp2 = opener.open('http://localhost:3010/api/v2/bo/business_object?version_id=2&page=1&page_size=20')
data2 = json.loads(resp2.read().decode('utf-8-sig'))
items2 = data2.get('data', {}).get('items', [])
print(f'  Total: {data2.get("data", {}).get("total")}, returned: {len(items2)}')
for it in items2[:5]:
    code = it.get('code') or ''
    cat = it.get('created_at') or ''
    print(f'    {code:35s} {cat}')
