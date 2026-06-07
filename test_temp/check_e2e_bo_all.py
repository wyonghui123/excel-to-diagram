#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询业务对象 E2E_* 状态 - 检查所有版本"""
import urllib.request
import http.cookiejar
import json

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 先获取所有版本
resp_v = opener.open('http://localhost:3010/api/v2/archdata/version?page_size=100')
data_v = json.loads(resp_v.read().decode('utf-8-sig'))
versions = data_v.get('data', {}).get('items', [])
print(f"Versions: {len(versions)}")
for v in versions[:5]:
    print(f"  v={v.get('id')} product={v.get('product_id')} name={v.get('name')}")

print()
print("=== All E2E_* BOs across all versions ===")
for v in versions:
    vid = v.get('id')
    try:
        resp = opener.open(f'http://localhost:3010/api/v2/bo/business_object?version_id={vid}&page_size=200')
        data = json.loads(resp.read().decode('utf-8-sig'))
        items = data.get('data', {}).get('items', [])
        e2e_items = [it for it in items if it.get('code', '').startswith('E2E_')]
        if e2e_items:
            print(f"  version_id={vid}: {len(e2e_items)} E2E BOs")
            for it in e2e_items[:5]:
                code = it.get('code') or ''
                bid = it.get('id')
                cat = it.get('created_at') or ''
                print(f"    id={bid} {code:30s} created={cat}")
    except Exception as e:
        print(f"  version_id={vid}: ERROR {e}")
