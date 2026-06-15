"""Reproduce TEST60 issue: GET /api/v1/relationships with version_id=1.

Steps:
1. dev-login as TEST60
2. GET /api/v1/relationships?version_id=1
3. Count relationships
4. Compare with admin result
"""
import requests, json

BASE = "http://localhost:3010"

# Admin
admin = requests.Session()
r = admin.get(f"{BASE}/api/v1/auth/dev-login",
              params={"username": "admin", "password": "admin"}, timeout=5)
assert r.status_code == 200, f"admin login: {r.status_code} {r.text[:200]}"
print(f"Admin logged in: {list(admin.cookies.keys())}")

# TEST60
test60 = requests.Session()
r = test60.get(f"{BASE}/api/v1/auth/dev-login",
               params={"username": "TEST60", "password": "test123"}, timeout=5)
print(f"TEST60 login: {r.status_code}")
if r.status_code != 200:
    # Try other common passwords
    for pw in ['TEST60', 'test60', 'password', '123456']:
        r = test60.get(f"{BASE}/api/v1/auth/dev-login",
                       params={"username": "TEST60", "password": pw}, timeout=5)
        if r.status_code == 200:
            print(f"  -> password = '{pw}' works")
            break
    if r.status_code != 200:
        print(f"  -> cannot login as TEST60, body: {r.text[:200]}")
        # Try with admin to find TEST60 user
        r = admin.get(f"{BASE}/api/v2/bo/user/1223", timeout=5)
        print(f"  Admin GET user/1223: {r.status_code}")
        # List users
        r = admin.post(f"{BASE}/api/v2/bo/user/list",
                       json={"page": 1, "page_size": 50}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            items = data.get('data', []) if isinstance(data.get('data'), list) else data.get('data', {}).get('items', [])
            for u in items:
                if 'test60' in str(u).lower() or 'TEST60' in str(u):
                    print(f"  Found user: {u}")
        sys.exit(1)

print()

# Both call /api/v1/relationships?version_id=1
for label, sess in [('admin', admin), ('TEST60', test60)]:
    r = sess.get(f"{BASE}/api/v1/relationships",
                 params={"version_id": 1, "page_size": 100}, timeout=10)
    print(f"--- {label} GET /api/v1/relationships?version_id=1 ---")
    print(f"  Status: {r.status_code}")
    data = r.json() if r.status_code == 200 else {}
    if isinstance(data, dict):
        items = data.get('data', [])
        if isinstance(items, dict):
            items = items.get('items', [])
    else:
        items = []
    print(f"  Items: {len(items) if isinstance(items, list) else 'N/A'}")
    if isinstance(items, list) and items:
        print(f"  Sample: {items[0].get('code') if items[0] else 'none'}")
    if r.status_code != 200:
        print(f"  Body: {r.text[:200]}")

# Try with version 2, 11, 12 (TEST60's scope)
print()
for vid in [1, 2, 11, 12]:
    for label, sess in [('admin', admin), ('TEST60', test60)]:
        r = sess.get(f"{BASE}/api/v1/relationships",
                     params={"version_id": vid, "page_size": 100}, timeout=5)
        data = r.json() if r.status_code == 200 else {}
        if isinstance(data, dict):
            items = data.get('data', [])
            if isinstance(items, dict):
                items = items.get('items', [])
        else:
            items = []
        n = len(items) if isinstance(items, list) else 'N/A'
        print(f"  v{vid} {label}: {n} items, status={r.status_code}")
