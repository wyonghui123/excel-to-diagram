# -*- coding: utf-8 -*-
"""Test API as TEST60 - check what versions are visible"""
import urllib.request
import urllib.parse
import json
import http.cookiejar

BASE = 'http://localhost:3010'

# Use cookie jar for session
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. Login as TEST60
print('=== 1. Login TEST60 ===')
login_url = f'{BASE}/api/v1/auth/dev-login?username=TEST60'
try:
    resp = opener.open(login_url, timeout=10)
    data = json.loads(resp.read().decode())
    print('  Login OK:', data.get('success'), 'user:', data.get('data', {}).get('user', {}).get('username'))
except Exception as e:
    print(f'  Login FAIL: {e}')
    import sys; sys.exit(1)

# 2. Query /api/v2/bo/version
print()
print('=== 2. GET /api/v2/bo/version ===')
versions_url = f'{BASE}/api/v2/bo/version?page=1&page_size=50'
try:
    resp = opener.open(versions_url, timeout=10)
    raw = resp.read().decode()
    data = json.loads(raw)
    print('  Success:', data.get('success'))
    items = data.get('data', {}).get('items', data.get('data', []))
    print(f'  Returned {len(items)} versions')
    print('  IDs returned:', [v.get('id') for v in items])
    print()
    print('  Detail (id / name / owner_id):')
    for v in items:
        marker = ' <-- owner=TEST60' if v.get('owner_id') == 1223 else ''
        print(f'    id={v.get("id")} name={v.get("name")} owner_id={v.get("owner_id")}{marker}')

    # Expected: TEST60 should see dimension scope [2,11,12,1] PLUS his own [17,19,20]
    expected_ids = sorted([1, 2, 11, 12, 17, 19, 20])
    actual_ids = sorted([v.get('id') for v in items])
    missing = set(expected_ids) - set(actual_ids)
    extra = set(actual_ids) - set(expected_ids)
    print()
    print('  EXPECTED (scope + owner):', expected_ids)
    print('  ACTUAL                  :', actual_ids)
    if missing:
        print(f'  MISSING (BUG!): {sorted(missing)}')
    if extra:
        print(f'  EXTRA: {sorted(extra)}')
except Exception as e:
    print(f'  Query FAIL: {e}')