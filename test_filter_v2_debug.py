#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

# Try v2 API
base_url = 'http://localhost:3010/api/v2'
session = requests.Session()

session.get(f'{base_url}/auth/dev-login', params={'username': 'admin'})

print('=== Query roles (v2) ===')
resp = session.get(f'{base_url}/bo/role', params={'page_size': '5'})
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:2000]}')
