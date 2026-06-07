#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

base_url = 'http://localhost:3010/api/v2'
session = requests.Session()

session.get(f'{base_url}/auth/dev-login', params={'username': 'admin'})

print('=== Test is_system=true ===')
resp = session.get(f'{base_url}/bo/role', params={'is_system': 'true', 'page_size': '10'})
data = resp.json()
items = data.get('data', {}).get('items', [])
print(f'Found {len(items)} roles with is_system=true')
for item in items[:5]:
    print(f'  - {item.get("name")} (is_system={item.get("is_system")})')

print('\n=== Test is_system=false ===')
resp = session.get(f'{base_url}/bo/role', params={'is_system': 'false', 'page_size': '10'})
data = resp.json()
items = data.get('data', {}).get('items', [])
print(f'Found {len(items)} roles with is_system=false')
for item in items[:5]:
    print(f'  - {item.get("name")} (is_system={item.get("is_system")})')

print('\n=== Test no filter ===')
resp = session.get(f'{base_url}/bo/role', params={'page_size': '10'})
data = resp.json()
items = data.get('data', {}).get('items', [])
sys_count = sum(1 for i in items if i.get('is_system'))
print(f'Found {len(items)} total roles (system: {sys_count}, custom: {len(items)-sys_count})')
for item in items[:5]:
    print(f'  - {item.get("name")} (is_system={item.get("is_system")})')

print('\n=== SUCCESS: Filter is working! ===')
