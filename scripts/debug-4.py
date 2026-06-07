"""Test only service_module_ids"""
import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')
import json, urllib.request

BASE = "http://localhost:3011"
TOKEN = None

def login():
    global TOKEN
    data = json.dumps({"username":"admin","password":"admin123"}).encode()
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=data,
        headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        TOKEN = json.loads(resp.read().decode())["data"]["token"]

def get(path):
    url = f"{BASE}{path}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

def post(path, body):
    url = f"{BASE}{path}"
    headers = {"Content-Type":"application/json", "Authorization": f"Bearer {TOKEN}"}
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

login()
versions = get("/api/v2/bo/version?page_size=1")
version_id = versions["data"]["items"][0]["id"]
sms = get(f"/api/v2/bo/service_module?version_id={version_id}&page_size=2")
sm_ids = [s["id"] for s in sms["data"]["items"]]
print(f"SM IDs: {sm_ids}")
result = post("/api/v1/export", {
    "object_type":"domain","scope":"selected","selected_types":["relationship"],
    "filters":{"version_id":version_id,"service_module_id":sm_ids},
    "options":{"include_hierarchy_path":False,"include_hierarchy_ids":True,"protect_sheet":False,"mark_readonly":False}
})
sheets = result.get("data",{}).get("sheets",[])
for s in sheets:
    print(f"  {s.get('name')}: {s.get('row_count')} rows")
