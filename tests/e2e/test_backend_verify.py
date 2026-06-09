# -*- coding: utf-8 -*-
"""
完整后端链路验证：排序 + 分页
"""
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

# Test all three states
print("=== 1. No ordering (default) ===")
r = fetch('/api/v2/bo/user?page=1&page_size=5', cookie)
for item in r['data']['items']:
    print(f"  id={item['id']}, username={item['username']}, updated_at={item.get('updated_at', 'N/A')[:19]}")

print("\n=== 2. ordering=updated_at (ASC) ===")
r = fetch('/api/v2/bo/user?page=1&page_size=5&ordering=updated_at', cookie)
for item in r['data']['items']:
    print(f"  id={item['id']}, username={item['username']}, updated_at={item.get('updated_at', 'N/A')[:19]}")

print("\n=== 3. ordering=-updated_at (DESC) ===")
r = fetch('/api/v2/bo/user?page=1&page_size=5&ordering=-updated_at', cookie)
for item in r['data']['items']:
    print(f"  id={item['id']}, username={item['username']}, updated_at={item.get('updated_at', 'N/A')[:19]}")

# Verify the sort is ACTUALLY correct
print("\n=== Verification: DESC sort ===")
r = fetch('/api/v2/bo/user?page=1&page_size=20&ordering=-updated_at', cookie)
items = r['data']['items']
dates = [(item['username'], item.get('updated_at', '')) for item in items if item.get('updated_at')]
for i in range(len(dates)-1):
    if dates[i][1] < dates[i+1][1]:
        print(f"  [FAIL] DESC order broken at index {i}: {dates[i]} < {dates[i+1]}")
        break
else:
    print("  [OK] DESC order correct")

print("\n=== Verification: ASC sort ===")
r = fetch('/api/v2/bo/user?page=1&page_size=20&ordering=updated_at', cookie)
items = r['data']['items']
dates = [(item['username'], item.get('updated_at', '')) for item in items if item.get('updated_at')]
for i in range(len(dates)-1):
    if dates[i][1] > dates[i+1][1]:
        print(f"  [FAIL] ASC order broken at index {i}: {dates[i]} > {dates[i+1]}")
        break
else:
    print("  [OK] ASC order correct")

# Check pagination consistency
print("\n=== Pagination check ===")
r1 = fetch('/api/v2/bo/user?page=1&page_size=5&ordering=-updated_at', cookie)
r2 = fetch('/api/v2/bo/user?page=2&page_size=5&ordering=-updated_at', cookie)
ids_page1 = [item['id'] for item in r1['data']['items']]
ids_page2 = [item['id'] for item in r2['data']['items']]
print(f"  Page 1 IDs: {ids_page1}")
print(f"  Page 2 IDs: {ids_page2}")
overlap = set(ids_page1) & set(ids_page2)
print(f"  Overlap: {overlap if overlap else 'None'} [{'FAIL' if overlap else 'OK'}]")
