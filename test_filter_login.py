#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

# Try v1 dev-login
base_url = 'http://localhost:3010/api/v1'
session = requests.Session()

print('=== Try v1 dev-login ===')
try:
    resp = session.post(f'{base_url}/auth/dev-login', json={'username': 'admin'})
    print(f'Status: {resp.status_code}')
    print(f'Cookies: {dict(session.cookies)}')
    print(f'Response: {resp.text[:500]}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
