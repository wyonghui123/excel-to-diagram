"""
直接调用 API 对比管理页和图表页的关系数据源

管理页: GET /api/v1/relationships?version_id=X&page_size=10000
图表页: GET /api/v1/architecture/preview?version_id=X&...
"""
import json
import urllib.request
import urllib.parse

API = "http://localhost:3010"

def req(path, method="GET", data=None, cookies=None):
    url = f"{API}{path}"
    req = urllib.request.Request(url, method=method)
    if cookies:
        req.add_header("Cookie", cookies)
    if data:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            set_cookie = resp.headers.get("Set-Cookie", "")
            return json.loads(body), set_cookie
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"error": e.code, "body": body}, ""
    except Exception as e:
        return {"error": str(e)}, ""

# 1. 登录拿 cookie
print("=== Step 1: 登录 ===")
login_data, cookie = req("/api/v1/auth/dev-login?username=admin")
print(f"  Login response: {json.dumps(login_data, ensure_ascii=False)[:200]}")
print(f"  Cookie: {cookie[:100]}")

# 提取 cookie
cookie_str = cookie.split(";")[0] if cookie else ""
print(f"  Cookie string: {cookie_str}")

# 2. 找版本
print("\n=== Step 2: 获取版本列表 ===")
versions, _ = req("/api/v1/versions?page_size=10", cookies=cookie_str)
print(f"  versions type: {type(versions)}")
if isinstance(versions, dict):
    items = versions.get("data", {}).get("items", versions.get("items", []))
    print(f"  Total versions: {len(items)}")
    if items:
        # 找有最多关系的版本
        first = items[0]
        version_id = first.get("id") or first.get("version_id")
        version_name = first.get("name", "")
        print(f"  Using version: id={version_id}, name={version_name}")
        # 遍历前 5 个找有数据的
        for v in items[:5]:
            vid = v.get("id") or v.get("version_id")
            vname = v.get("name", "")
            # 先看关系数
            r, _ = req(f"/api/v1/relationships?version_id={vid}&page_size=1", cookies=cookie_str)
            if isinstance(r, dict):
                total = r.get("total", r.get("data", {}).get("total", 0))
                print(f"  Version {vid} ({vname}): {total} relationships")
else:
    print(f"  Unexpected: {versions}")
    version_id = None

if not version_id:
    print("No version found, exiting")
    exit(1)

# 3. 调用管理页 API: /api/v1/relationships
print(f"\n=== Step 3: 管理页 API (version_id={version_id}) ===")
mgmt_rels, _ = req(f"/api/v1/relationships?version_id={version_id}&page_size=10000", cookies=cookie_str)
if isinstance(mgmt_rels, dict):
    items = mgmt_rels.get("data", {}).get("items", mgmt_rels.get("items", []))
    mgmt_total = mgmt_rels.get("total", len(items))
    print(f"  管理页: {mgmt_total} 条关系 (items={len(items)})")
    # 统计 src/tgt 在 center scope 的关系
    # 先拿 BOs
    bos, _ = req(f"/api/v1/business-objects?version_id={version_id}&page_size=10000", cookies=cookie_str)
    if isinstance(bos, dict):
        bo_items = bos.get("data", {}).get("items", bos.get("items", []))
        print(f"  BOs: {len(bo_items)}")
        bo_codes = [b.get("code") for b in bo_items if b.get("code")]
    else:
        bo_codes = []
else:
    mgmt_total = 0
    items = []

# 4. 调用图表页 API: /api/v1/architecture/preview
print(f"\n=== Step 4: 图表页 API ===")
# 试几种参数组合
for params in [
    f"version_id={version_id}",
    f"version_id={version_id}&limit=10000",
    f"version_id={version_id}&page_size=10000",
]:
    preview, _ = req(f"/api/v1/architecture/preview?{params}", cookies=cookie_str)
    if isinstance(preview, dict):
        if "data" in preview:
            data = preview["data"]
        else:
            data = preview
        rels = data.get("relationships", data.get("items", []))
        bos = data.get("businessObjects", data.get("business_objects", []))
        print(f"  params={params}: {len(rels)} relations, {len(bos)} BOs")
        if rels:
            print(f"    Sample: {json.dumps(rels[0], ensure_ascii=False)[:300]}")
            preview_rels = rels
    else:
        print(f"  params={params}: error {preview}")

# 5. 对比
print(f"\n=== Step 5: 对比 ===")
if 'items' in dir() and 'preview_rels' in dir():
    mgmt_ids = set(r.get("id") for r in items if r.get("id"))
    preview_ids = set(r.get("id") for r in preview_rels if r.get("id"))
    print(f"  管理页关系 IDs: {len(mgmt_ids)}")
    print(f"  图表页关系 IDs: {len(preview_ids)}")
    print(f"  差集 (管理页有，图表页无): {mgmt_ids - preview_ids}")
    print(f"  差集 (图表页有，管理页无): {preview_ids - mgmt_ids}")
    print(f"  交集: {len(mgmt_ids & preview_ids)}")

print("\n=== Done ===")
