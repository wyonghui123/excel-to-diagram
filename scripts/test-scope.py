import urllib.request, json

BASE = "http://localhost:3010"
def login():
    data = json.dumps({"username":"admin","password":"admin123"}).encode()
    t = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/api/v1/auth/login", data=data,
        headers={"Content-Type":"application/json"}), timeout=5).read().decode())
    return t["data"]["token"]

TOKEN = login()
H = {"Content-Type":"application/json","Authorization":f"Bearer {TOKEN}"}

# Get some BO IDs and relation codes to filter by
r = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{BASE}/api/v2/bo/relationship?version_id=15&page_size=3", headers=H), timeout=5).read().decode())
rel = r["data"]["items"][0]
src_bo_id = rel.get("source_bo_id") or rel.get("source_business_object_id")
rel_code = rel.get("relation_code") or rel.get("code")
print(f"Scope source BO: {src_bo_id}, relation_code: {rel_code}")

# Export WITH scope-source filters
body = {
    "object_type": "domain",
    "scope": "selected",
    "selected_types": ["domain","sub_domain","service_module","business_object","relationship"],
    "filters": {
        "version_id": 15,
        "source_bo_ids__in": str(src_bo_id),
        "relation_codes__in": rel_code
    },
    "options": {
        "include_hierarchy_path": False,
        "include_hierarchy_ids": True,
        "protect_sheet": False,
        "mark_readonly": False
    }
}

print(f"\nExporting with filters: {json.dumps(body['filters'])}")
r = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{BASE}/api/v1/export", data=json.dumps(body).encode(),
    headers=H), timeout=60).read().decode())

print(f"success: {r['success']}")
for s in r["data"]["sheets"]:
    marker = "[OK]" if s["row_count"] > 0 else "[X]"
    print(f"  {marker} {s['name']}: {s['row_count']} rows")

# Verify: domain/sub_domain... should be full, relationship should be filtered
print("\n预期：层级对象全量，关系过滤生效")
