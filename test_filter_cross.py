#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

# Get token from v1
session = requests.Session()
login_resp = session.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'admin'})
print(f'v1 Login: {login_resp.status_code}')
token = session.cookies.get('auth_token')
print(f'Token: {token[:50]}...' if token else 'No token')

# Use v2 API with the token
v2_resp = session.get('http://localhost:3010/api/v2/bo/role', params={'page_size': '5'})
print(f'\nv2 Role query: {v2_resp.status_code}')
print(f'Response: {v2_resp.text[:2000]}')
