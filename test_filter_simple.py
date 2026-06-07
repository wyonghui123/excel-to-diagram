#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

base_url = 'http://localhost:3010/api/v1'

session = requests.Session()

try:
    resp = session.post(f'{base_url}/auth/dev-login', json={'username': 'admin'})
    result = resp.json()
    print(f'Login: {result.get("success")}')
except Exception as e:
    print(f'Login error: {e}')
    exit(1)

print('\n=== Test is_system=true ===')
try:
    resp = session.get(f'{base_url}/bo/role', params={'is_system': 'true'})
    data = resp.json()
    items = data.get('data', {}).get('items', [])
    print(f'Found {len(items)} roles with is_system=true')
    for item in items[:5]:
        print(f'  - {item.get("name")} (is_system={item.get("is_system")})')
except Exception as e:
    print(f'Error: {e}')

print('\n=== Test is_system=false ===')
try:
    resp = session.get(f'{base_url}/bo/role', params={'is_system': 'false'})
    data = resp.json()
    items = data.get('data', {}).get('items', [])
    print(f'Found {len(items)} roles with is_system=false')
    for item in items[:5]:
        print(f'  - {item.get("name")} (is_system={item.get("is_system")})')
except Exception as e:
    print(f'Error: {e}')

print('\n=== Test no filter ===')
try:
    resp = session.get(f'{base_url}/bo/role', params={'page_size': '10'})
    data = resp.json()
    items = data.get('data', {}).get('items', [])
    sys_count = sum(1 for i in items if i.get('is_system'))
    print(f'Found {len(items)} total roles (system: {sys_count}, custom: {len(items)-sys_count})')
    for item in items[:5]:
        print(f'  - {item.get("name")} (is_system={item.get("is_system")})')
except Exception as e:
    print(f'Error: {e}')
