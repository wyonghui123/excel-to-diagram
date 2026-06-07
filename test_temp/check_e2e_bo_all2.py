#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询业务对象 E2E_* 状态 - 简化版"""
import urllib.request
import http.cookiejar
import json

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 查所有 BO 不带 version_id filter
resp = opener.open('http://localhost:3010/api/v2/bo/business_object?page_size=500')
data = json.loads(resp.read().decode('utf-8-sig'))
items = data.get('data', {}).get('items', [])
total = data.get('data', {}).get('total')
print(f"Total: {total}, returned: {len(items)}")

e2e_items = [it for it in items if it.get('code', '').startswith('E2E_')]
e2e_items.sort(key=lambda x: x.get('created_at') or '', reverse=True)
print(f"E2E_ items: {len(e2e_items)}")
print()
for it in e2e_items[:30]:
    code = it.get('code') or ''
    bid = it.get('id')
    vid = it.get('version_id')
    cat = it.get('created_at') or ''
    print(f"  id={str(bid):>5} v={vid}  {code:35s}  created={cat}")
