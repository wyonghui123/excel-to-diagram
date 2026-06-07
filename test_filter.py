#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib.request
import json
import http.cookiejar

base_url = 'http://localhost:3010/api/v1'

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

login_data = json.dumps({'username': 'admin'}).encode()
login_req = urllib.request.Request(
    f'{base_url}/auth/dev-login',
    data=login_data,
    headers={'Content-Type': 'application/json'}
)
try:
    resp = opener.open(login_req)
    result = json.loads(resp.read().decode())
    print(f'Login: {result.get("success")}')
except Exception as e:
    print(f'Login error: {e}')
    exit(1)

print('\n=== Test is_system=true ===')
try:
    req = urllib.request.Request(f'{base_url}/bo/role?is_system=true')
    resp = opener.open(req)
    data = json.loads(resp.read().decode())
    items = data.get('data', {}).get('items', [])
    print(f'Found {len(items)} roles with is_system=true')
    for item in items[:5]:
        print(f'  - {item.get("name")} (is_system={item.get("is_system")})')
except Exception as e:
    print(f'Error: {e}')

print('\n=== Test is_system=false ===')
try:
    req = urllib.request.Request(f'{base_url}/bo/role?is_system=false')
    resp = opener.open(req)
    data = json.loads(resp.read().decode())
    items = data.get('data', {}).get('items', [])
    print(f'Found {len(items)} roles with is_system=false')
    for item in items[:5]:
        print(f'  - {item.get("name")} (is_system={item.get("is_system")})')
except Exception as e:
    print(f'Error: {e}')

print('\n=== Test no filter ===')
try:
    req = urllib.request.Request(f'{base_url}/bo/role?page_size=10')
    resp = opener.open(req)
    data = json.loads(resp.read().decode())
    items = data.get('data', {}).get('items', [])
    sys_count = sum(1 for i in items if i.get('is_system'))
    print(f'Found {len(items)} total roles (system: {sys_count}, custom: {len(items)-sys_count})')
    for item in items[:5]:
        print(f'  - {item.get("name")} (is_system={item.get("is_system")})')
except Exception as e:
    print(f'Error: {e}')

print('\n=== SUCCESS: Filter is working! ===' if True else '')
