"""Trace _list_relationships_impl for TEST60 with sub_domain filter."""
import requests, json

BASE = "http://localhost:3010"

# Login
test60 = requests.Session()
r = test60.get(f"{BASE}/api/v1/auth/dev-login",
               params={"username": "TEST60", "password": "TEST60"}, timeout=5)
print(f"TEST60 login: {r.status_code}")

# 1. Find sub_domain id for "采购管理"
print()
print("--- Find '采购管理' sub_domain id ---")
r = test60.get(f"{BASE}/api/v2/bo/sub_domain/list",
               params={"page": 1, "page_size": 100}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f"  Total sub_domains: {len(items)}")
target_sd = None
for sd in items:
    name = sd.get('name', '')
    if '采购' in name or 'purchase' in name.lower():
        print(f"  Found: id={sd.get('id')}, name={name}, version_id={sd.get('version_id')}")
        if target_sd is None:
            target_sd = sd
print(f"  Target SD: {target_sd}")

# 2. Check what BOs are in this sub_domain
print()
print("--- BOs in target sub_domain ---")
sd_id = target_sd.get('id') if target_sd else None
sd_version = target_sd.get('version_id') if target_sd else None
print(f"  sd_id={sd_id}, sd_version={sd_version}")
r = test60.get(f"{BASE}/api/v2/bo/business_object/list",
               params={"page": 1, "page_size": 100, "sub_domain_id": sd_id}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f"  BOs in this sub_domain: {len(items)}")
for bo in items[:5]:
    print(f"    id={bo.get('id')}, name={bo.get('name')}, sub_domain_id={bo.get('sub_domain_id')}")

# 3. Now call /api/v1/relationships with this sub_domain
print()
print("--- TEST60 GET /api/v1/relationships?version_id=1&sub_domain_id=... ---")
r = test60.get(f"{BASE}/api/v1/relationships",
               params={"version_id": sd_version, "sub_domain_id": sd_id, "page_size": 100},
               timeout=10)
print(f"  Status: {r.status_code}")
data = r.json() if r.status_code == 200 else {}
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f"  Items: {len(items) if isinstance(items, list) else 'N/A'}")

# 4. Without sub_domain filter, just version_id
print()
print("--- TEST60 GET /api/v1/relationships?version_id=1 (no sub_domain) ---")
r = test60.get(f"{BASE}/api/v1/relationships",
               params={"version_id": 1, "page_size": 100}, timeout=10)
print(f"  Status: {r.status_code}")
data = r.json() if r.status_code == 200 else {}
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f"  Items: {len(items) if isinstance(items, list) else 'N/A'}")
