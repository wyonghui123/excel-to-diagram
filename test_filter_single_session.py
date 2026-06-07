#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests

base_url = 'http://localhost:3010/api/v2'
session = requests.Session()

# Login with the same session
login_resp = session.get(f'{base_url}/auth/dev-login', params={'username': 'admin'})
print(f'Login: {login_resp.status_code} - {login_resp.text[:200]}')
print(f'Cookies after login: {dict(session.cookies)}')

# Now query roles with the same session
role_resp = session.get(f'{base_url}/bo/role', params={'page_size': '5'})
print(f'\nRole query: {role_resp.status_code}')
print(f'Cookies: {dict(session.cookies)}')
print(f'Response: {role_resp.text[:2000]}')
