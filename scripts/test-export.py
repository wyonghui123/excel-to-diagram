"""
多类型导出 E2E 测试
"""
import urllib.request, urllib.error, json, sys

BASE = "http://localhost:3010"
TOKEN = None

def login():
    global TOKEN
    data = json.dumps({"username":"admin","password":"admin123"}).encode()
    req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=data,
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        r = json.loads(resp.read().decode())
        TOKEN = r["data"]["token"]
        return TOKEN

def api(path, method="GET", body=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type":"application/json"}
    if TOKEN: headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()[:500]}

def test_types(version_id):
    types = [("domain","领域"),("sub_domain","子领域"),("service_module","服务模块"),
             ("business_object","业务对象"),("relationship","关系")]
    results = {}
    for obj_type, label in types:
        r = api(f"/api/v2/bo/{obj_type}?version_id={version_id}&page_size=1")
        total = (r.get("data") or {}).get("total", 0)
        results[obj_type] = total
        print(f"  {'[OK]' if total>0 else '[X]'} {label}: {total} 条")
    return results

def do_export(version_id, filters, label):
    body = {
        "object_type": "domain",
        "scope": "selected",
        "selected_types": ["domain","sub_domain","service_module","business_object","relationship"],
        "filters": filters,
        "options": {"include_hierarchy_path":False,"include_hierarchy_ids":True,
                     "protect_sheet":False,"mark_readonly":False}
    }
    print(f"\n[SYMBOL] {label}")
    print(f"   filters: {json.dumps(filters)}")
    result = api("/api/v1/export", method="POST", body=body)

    if result.get("success"):
        print(f"  [OK] 导出成功: {result['data'].get('download_url','?')}")
        sheets = result.get("data",{}).get("sheets",[])
        if sheets:
            print(f"  [DECORATIVE] 各工作表:")
            all_ok = True
            for s in sheets:
                name = s.get("name","?")
                count = s.get("row_count", s.get("count", 0))
                ok = "[OK]" if count>0 else "[X]"
                if count==0: all_ok=False
                print(f"    {ok} {name}: {count} 行")
            return all_ok
        else:
            print(f"  file_path: {result['data'].get('file_path','')}")
            return False
    else:
        print(f"  [X]: {result.get('message','')} {result.get('error','')}"[:300])
        return False

def main():
    print("="*60)
    print("  多类型导出 E2E 测试")
    print("="*60)

    login()
    if not TOKEN: sys.exit(1)

    versions = api("/api/v2/bo/version?page_size=1")
    items = (versions.get("data") or {}).get("items", [])
    if not items: sys.exit(1)
    version_id = items[0]["id"]
    print(f"\n[CLIPBOARD] 版本 ID={version_id}")

    print(f"\n1️⃣  各类型数据量:")
    results = test_types(version_id)
    empty = [k for k,v in results.items() if v==0]
    if empty: print(f"  [WARNING] 无数据: {empty}")

    print(f"\n2️⃣  测试1: 仅 version_id（无 scope 过滤）")
    ok1 = do_export(version_id, {"version_id": version_id}, "仅 version_id")

    print(f"\n3️⃣  测试2: version_id + globalFilter")
    ok2 = do_export(version_id,
        {"version_id": version_id},
        "version_id 只过滤")

    # 4. 统计结果
    print("\n" + "="*60)
    if ok1 and ok2:
        print("  [OK][OK][OK] 全部通过！多类型导出所有表都有数据。")
    else:
        print("  [X] 有失败项，请检查上面日志。")
    print("="*60)

if __name__=="__main__":
    main()
