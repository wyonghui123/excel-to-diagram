#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详细查询业务对象"""
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
print()

if items:
    print("First item full dump:")
    print(json.dumps(items[0], ensure_ascii=False, indent=2))

    e2e = [it for it in items if (it.get('code') or '').startswith('E2E_')]
    print(f"\nE2E items: {len(e2e)}")
    for it in e2e:
        print(json.dumps(it, ensure_ascii=False, indent=2))
