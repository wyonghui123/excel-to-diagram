#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

session = requests.Session()

# Login via v1 API
session.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'admin'})

# Get v2 API token
print('=== Login Status ===')
print(f'Cookie: {session.cookies.get("auth_token")[:50]}...')

# Test various filter parameters
base_url = 'http://localhost:3010/api/v2'

tests = [
    ('No filter', {}),
    ('is_system=1', {'is_system': '1'}),
    ('is_system=true', {'is_system': 'true'}),
    ('is_system=true (lowercase)', {'is_system': 'True'}),
    ('is_system=0', {'is_system': '0'}),
    ('is_system=false', {'is_system': 'false'}),
]

for name, params in tests:
    resp = session.get(f'{base_url}/bo/role', params={**params, 'page_size': '50'})
    data = resp.json()
    items = data.get('data', {}).get('items', [])
    sys_count = sum(1 for i in items if i.get('is_system') == 1)
    custom_count = sum(1 for i in items if i.get('is_system') == 0)
    print(f'{name}: {len(items)} roles (system: {sys_count}, custom: {custom_count})')
