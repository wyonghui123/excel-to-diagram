#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

base_url = 'http://localhost:3010/api/v2'
session = requests.Session()

session.get(f'{base_url}/auth/dev-login', params={'username': 'admin'})

print('=== Query roles (full response) ===')
resp = session.get(f'{base_url}/bo/role', params={'page_size': '5'})
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:2000]}')
