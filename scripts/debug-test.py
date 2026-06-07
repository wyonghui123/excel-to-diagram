"""直接测试关系导出的 SQL 逻辑"""
import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

import json, urllib.request

BASE = "http://localhost:3011"

def login():
    data = json.dumps({"username":"admin","password":"admin123"}).encode()
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=data,
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())["data"]["token"]

def api(path, method="GET", body=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type":"application/json"}
    headers["Authorization"] = f"Bearer {login()}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

# 获取 version_id 和 service_module IDs
versions = api("/api/v2/bo/version?page_size=1")
version_id = versions["data"]["items"][0]["id"]

# 获取 service_module
sms = api(f"/api/v2/bo/service_module?version_id={version_id}&page_size=2")
sm_ids = [s["id"] for s in sms["data"]["items"]]
print(f"SM IDs: {sm_ids}")

# 获取 sub_domain
sds = api(f"/api/v2/bo/sub_domain?version_id={version_id}&page_size=2")
sd_ids = [s["id"] for s in sds["data"]["items"]]
print(f"SD IDs: {sd_ids}")

# 获取 domain
doms = api(f"/api/v2/bo/domain?version_id={version_id}&page_size=2")
d_ids = [d["id"] for d in doms["data"]["items"]]
print(f"D IDs: {d_ids}")

# 获取 business_object
bos = api(f"/api/v2/bo/business_object?version_id={version_id}&page_size=2")
bo_ids = [b["id"] for b in bos["data"]["items"]]
print(f"BO IDs: {bo_ids}")

# 测试1: service_module_ids -> 应该是正确的 BO 查询
print("\n=== Test: service_module_id ===")
body = {"object_type":"domain","scope":"selected","selected_types":["relationship"],
        "filters":{"version_id":version_id,"service_module_id":sm_ids},
        "options":{"include_hierarchy_path":False,"include_hierarchy_ids":True,"protect_sheet":False,"mark_readonly":False}}
result = api("/api/v1/export", method="POST", body=body)
sheets = result.get("data",{}).get("sheets",[])
for s in sheets:
    print(f"  {s.get('name')}: {s.get('row_count')} rows")

# 测试2: sub_domain_ids
print("\n=== Test: sub_domain_id ===")
body = {"object_type":"domain","scope":"selected","selected_types":["relationship"],
        "filters":{"version_id":version_id,"sub_domain_id":sd_ids},
        "options":{"include_hierarchy_path":False,"include_hierarchy_ids":True,"protect_sheet":False,"mark_readonly":False}}
result = api("/api/v1/export", method="POST", body=body)
sheets = result.get("data",{}).get("sheets",[])
for s in sheets:
    print(f"  {s.get('name')}: {s.get('row_count')} rows")

# 测试3: domain_ids
print("\n=== Test: domain_id ===")
body = {"object_type":"domain","scope":"selected","selected_types":["relationship"],
        "filters":{"version_id":version_id,"domain_id":d_ids},
        "options":{"include_hierarchy_path":False,"include_hierarchy_ids":True,"protect_sheet":False,"mark_readonly":False}}
result = api("/api/v1/export", method="POST", body=body)
sheets = result.get("data",{}).get("sheets",[])
for s in sheets:
    print(f"  {s.get('name')}: {s.get('row_count')} rows")

# 测试4: business_object_ids
print("\n=== Test: business_object_id ===")
body = {"object_type":"domain","scope":"selected","selected_types":["relationship"],
        "filters":{"version_id":version_id,"business_object_id":bo_ids},
        "options":{"include_hierarchy_path":False,"include_hierarchy_ids":True,"protect_sheet":False,"mark_readonly":False}}
result = api("/api/v1/export", method="POST", body=body)
sheets = result.get("data",{}).get("sheets",[])
for s in sheets:
    print(f"  {s.get('name')}: {s.get('row_count')} rows")

print("\nDone!")
