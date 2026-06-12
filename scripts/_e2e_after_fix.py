# -*- coding: utf-8 -*-
"""[E2E v1.0.1] 验证 TEST60 现在能看到 product"""
import requests
import json

BASE = 'http://localhost:3010'
s = requests.Session()
r = s.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'test60pass'}, timeout=10)
print(f'login: {r.status_code}')

# 1. product 列表
print('\n[1] /api/v2/bo/product')
r = s.get(f'{BASE}/api/v2/bo/product?page=1&page_size=20', timeout=10)
j = r.json()
print(f'  status: {r.status_code}, total: {j["data"]["total"]}')
for item in j['data']['items']:
    print(f'  - {item.get("id")}: {item.get("code")} | {item.get("name")} | is_active={item.get("is_active")}')

# 2. version 列表
print('\n[2] /api/v2/bo/version')
r = s.get(f'{BASE}/api/v2/bo/version?page=1&page_size=20', timeout=10)
j = r.json()
print(f'  status: {r.status_code}, total: {j["data"]["total"]}')
for item in j['data']['items']:
    print(f'  - {item.get("id")}: {item.get("code")} | {item.get("name")}')

# 3. domain 列表
print('\n[3] /api/v2/bo/domain')
r = s.get(f'{BASE}/api/v2/bo/domain?page=1&page_size=20', timeout=10)
j = r.json()
print(f'  status: {r.status_code}, total: {j["data"]["total"]}')

# 4. sub_domain 列表
print('\n[4] /api/v2/bo/sub_domain')
r = s.get(f'{BASE}/api/v2/bo/sub_domain?page=1&page_size=20', timeout=10)
j = r.json()
print(f'  status: {r.status_code}, total: {j["data"]["total"]}')

# 5. admin 对比
print('\n[5] admin 对比:')
s2 = requests.Session()
s2.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=10)
r = s2.get(f'{BASE}/api/v2/bo/product?page=1&page_size=20', timeout=10)
j = r.json()
print(f'  admin product: total: {j["data"]["total"]}')
for item in j['data']['items']:
    print(f'  - {item.get("id")}: {item.get("code")} | {item.get("name")}')
