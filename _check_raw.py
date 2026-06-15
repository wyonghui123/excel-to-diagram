#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check raw list.columns dict for one object to see all keys."""
import urllib.request
import json

login = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
req = urllib.request.Request(
    'http://localhost:3010/api/v1/auth/login',
    data=login,
    headers={'Content-Type': 'application/json'}
)
r = json.loads(urllib.request.urlopen(req).read())
token = r['data']['token']

req2 = urllib.request.Request(
    'http://localhost:3010/api/v2/meta/business_object/view-config/default',
    headers={'Authorization': f'Bearer {token}'}
)
r2 = json.loads(urllib.request.urlopen(req2).read())
data = r2['data']

print('=== business_object list.columns full dump (sm + sdn + dn) ===')
for c in data['list']['columns']:
    if c.get('key') in ('service_module_name', 'sub_domain_name', 'domain_name'):
        print(f"\n  {c.get('key')}:")
        for k, v in c.items():
            print(f"    {k} = {v!r}")
