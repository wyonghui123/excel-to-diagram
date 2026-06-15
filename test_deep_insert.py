#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test deep insert for product + version"""
import json
import sys
import os
import re

# 解析 cookies.txt - 支持 #HttpOnly_ 前缀
cookies_path = '/tmp/cookies.txt'
cookies = {}
with open(cookies_path) as f:
    for line in f:
        if line.startswith('#') and not line.startswith('#HttpOnly_'):
            continue
        if line.startswith('#HttpOnly_'):
            line = line[len('#HttpOnly_'):]
        if not line.strip():
            continue
        parts = line.strip().split('\t')
        if len(parts) >= 7:
            cookies[parts[5]] = parts[6]

cookie_header = '; '.join(f'{k}={v}' for k, v in cookies.items())
print(f"[*] Cookies loaded: {list(cookies.keys())}")

# 1. 测试普通 POST 创建
import urllib.request
import urllib.error

def post(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Cookie': cookie_header}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))

print("\n[TEST 1] POST /api/v2/bo/product (simple create)")
import random
code = f'TEST_{random.randint(100000, 999999)}'
name = f'TestProduct_{code}'
status, resp = post('http://localhost:3010/api/v2/bo/product', {
    'name': name,
    'code': code,
    'description': 'test',
    'visibility': 'private',
    'is_active': True
})
print(f"  status={status}")
print(f"  response={json.dumps(resp, ensure_ascii=False, indent=2)}")

if resp.get('success'):
    new_product_id = resp['data'].get('id')
    print(f"  [OK] product created id={new_product_id}")

    print("\n[TEST 2] POST /api/v2/bo/product/deep (deep insert product + version)")
    code2 = f'TEST_{random.randint(100000, 999999)}'
    status, resp = post('http://localhost:3010/api/v2/bo/product/deep', {
        'parent': {
            'name': f'TestDeep_{code2}',
            'code': code2,
            'description': 'deep insert test',
            'visibility': 'private',
            'is_active': True
        },
        'children': {
            'version': [{
                'name': 'v1.0_test',
                'description': 'first version',
                'is_current': True
            }]
        }
    })
    print(f"  status={status}")
    print(f"  response={json.dumps(resp, ensure_ascii=False, indent=2)}")
else:
    print("  [FAIL] product create failed, cannot test deep insert")
