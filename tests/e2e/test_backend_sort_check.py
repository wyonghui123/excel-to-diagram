# -*- coding: utf-8 -*-
"""验证：对比 API 返回的排序和 enrichment 前后的值是否一致"""
import sys, os, json, urllib.request, urllib.error

def get_cookie():
    data = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
    req = urllib.request.Request('http://localhost:3004/api/v1/auth/login', data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=5) as resp:
        cookies = resp.headers.get('Set-Cookie', '')
        for c in cookies.split(';'):
            if 'auth_token=' in c:
                return c.strip()

def fetch(path, cookie):
    req = urllib.request.Request(f'http://localhost:3004{path}')
    req.add_header('Cookie', cookie)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

cookie = get_cookie()

# Get all items (large page_size to see the full picture)
print("=== DESC: ordering=-updated_at (all items) ===")
r = fetch('/api/v2/bo/user?page=1&page_size=100&ordering=-updated_at', cookie)
items = r['data']['items']
print(f"Total items: {len(items)}")

# Check consistency
print("\nDESC order check:")
dates = []
for item in items:
    ua = item.get('updated_at', '')
    ca = item.get('created_at', '')
    dates.append((item['id'], item['username'], ua, ca))

# Check if updated_at values are in DESC order
violations = []
for i in range(len(dates)-1):
    if dates[i][2] and dates[i+1][2]:
        if dates[i][2] < dates[i+1][2]:
            violations.append((i, dates[i], dates[i+1]))

if violations:
    print(f"  [FAIL] {len(violations)} DESC order violations:")
    for idx, a, b in violations[:5]:
        print(f"    [{idx}] id={a[0]} ({a[1]}) ua={a[2][:22]} < id={b[0]} ({b[1]}) ua={b[2][:22]}")
else:
    print("  [OK] DESC order correct")

# Compare with ASC
print("\n=== ASC: ordering=updated_at (all items) ===")
r = fetch('/api/v2/bo/user?page=1&page_size=100&ordering=updated_at', cookie)
items_asc = r['data']['items']

asc_dates = []
for item in items_asc:
    ua = item.get('updated_at', '')
    asc_dates.append((item['id'], item['username'], ua))

asc_violations = []
for i in range(len(asc_dates)-1):
    if asc_dates[i][2] and asc_dates[i+1][2]:
        if asc_dates[i][2] > asc_dates[i+1][2]:
            asc_violations.append((i, asc_dates[i], asc_dates[i+1]))

if asc_violations:
    print(f"  [FAIL] {len(asc_violations)} ASC order violations")
else:
    print("  [OK] ASC order correct")

# Verify ASC is reverse of DESC
print("\n=== Cross-check: ASC == reverse(DESC)? ===")
desc_ids = [item['id'] for item in items if item.get('updated_at')]
asc_ids = [item['id'] for item in items_asc if item.get('updated_at')]
print(f"  DESC first 5 IDs: {desc_ids[:5]}")
print(f"  ASC  first 5 IDs: {asc_ids[:5]}")
print(f"  DESC reversed first 5: {list(reversed(desc_ids[:5]))}")
if asc_ids[:5] == list(reversed(desc_ids[:5])):
    print("  [OK] ASC first 5 == reverse(DESC first 5)")
else:
    print("  [FAIL] Cross-check failed")
