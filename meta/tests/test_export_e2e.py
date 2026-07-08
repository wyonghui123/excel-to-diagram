# -*- coding: utf-8 -*-
"""E2E test: export business_object as wyonghui on release-prep 3011."""
import urllib.request, json, io, http.cookiejar

BASE = 'http://localhost:3011'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Login
req = urllib.request.Request(f'{BASE}/api/v1/auth/dev-login?username=wyonghui')
resp = opener.open(req, timeout=15)
login_data = json.loads(resp.read())
print(f'Login: {login_data.get("success")}')

# Export
body = json.dumps({'object_type': 'business_object', 'scope': 'cascade', 'filters': {}}).encode()
req = urllib.request.Request(f'{BASE}/api/v1/export', data=body, headers={'Content-Type': 'application/json'})
resp = opener.open(req, timeout=120)
result = json.loads(resp.read())
if result.get('success'):
    data = result.get('data', {})
    print(f'Total rows: {data.get("total_rows")}')
    for sheet in data.get('sheets', []):
        print(f'  {sheet["name"]}: {sheet["row_count"]} rows')
    result_str = 'OK' if any(s['object_type'] == 'business_object' and s['row_count'] < 200 for s in data.get('sheets', [])) else 'FAIL'
    print(f'Result: {result_str} (BO rows should be ~155, not 3813)')
else:
    print(f'Error: {result.get("error")}')
