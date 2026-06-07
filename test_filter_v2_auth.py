#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

# v1 session
session1 = requests.Session()
session1.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'admin'})
print(f'v1 auth: {session1.cookies.get_dict()}')

# Query v1
resp1 = session1.get('http://localhost:3010/api/v1/bo/role', params={'page_size': '5'})
print(f'v1 /bo/role: {resp1.status_code} - {resp1.text[:200]}')

# Try /bo/roles
resp1b = session1.get('http://localhost:3010/api/v1/bo/roles', params={'page_size': '5'})
print(f'v1 /bo/roles: {resp1b.status_code} - {resp1b.text[:200]}')

# v2 session
session2 = requests.Session()
# Try v2 dev-login without cookie
resp2login = session2.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'admin'})
print(f'\nv2 session cookie: {session2.cookies.get_dict()}')

# Use v2 API
resp2 = session2.get('http://localhost:3010/api/v2/bo/role', params={'page_size': '5'})
print(f'v2 /bo/role: {resp2.status_code} - {resp2.text[:200]}')
