#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

base_url = 'http://localhost:3010/api/v1'

session = requests.Session()

print('=== Debug: Check if server is running ===')
try:
    resp = session.get(f'{base_url}/health')
    print(f'Health check: {resp.status_code} - {resp.text[:200]}')
except Exception as e:
    print(f'Health check error: {e}')

print('\n=== Debug: Login ===')
try:
    resp = session.post(f'{base_url}/auth/dev-login', json={'username': 'admin'})
    print(f'Status: {resp.status_code}')
    print(f'Headers: {dict(resp.headers)}')
    print(f'Cookies: {dict(session.cookies)}')
    print(f'Response: {resp.text[:500]}')
except Exception as e:
    print(f'Error: {e}')

print('\n=== Debug: List roles ===')
try:
    resp = session.get(f'{base_url}/bo/role', params={'page_size': '5'})
    print(f'Status: {resp.status_code}')
    print(f'Response: {resp.text[:1000]}')
except Exception as e:
    print(f'Error: {e}')
