#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

# Try v2 API
base_url = 'http://localhost:3010/api/v2'
session = requests.Session()

print('=== Try v2 auth ===')
try:
    resp = session.post(f'{base_url}/auth/dev-login', json={'username': 'admin'})
    print(f'Status: {resp.status_code}')
    print(f'Response: {resp.text[:300]}')
except Exception as e:
    print(f'Error: {e}')

print('\n=== Try v2 bo ===')
try:
    resp = session.get(f'{base_url}/bo/role', params={'page_size': '5'})
    print(f'Status: {resp.status_code}')
    print(f'Response: {resp.text[:500]}')
except Exception as e:
    print(f'Error: {e}')

print('\n=== Try v1 with cookies ===')
session2 = requests.Session()
try:
    resp = session2.get('http://localhost:3010/api/v1/bo/role', params={'page_size': '5'})
    print(f'Status: {resp.status_code}')
    print(f'Response: {resp.text[:500]}')
except Exception as e:
    print(f'Error: {e}')
