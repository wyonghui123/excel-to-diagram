"""
端到端验证：图表页关系数 11 → 12
通过 API 直接对比 management 页 vs chart 页的关系数
"""
import json
import urllib.request
import urllib.parse

API = "http://localhost:3010"

def req(path, cookies=None):
    url = f"{API}{path}"
    r = urllib.request.Request(url)
    if cookies:
        r.add_header("Cookie", cookies)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return json.loads(resp.read().decode()), resp.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()}, ""

# 1. 登录
print("=== 1. 登录 ===")
login, cookie = req("/api/v1/auth/dev-login?username=admin")
print(f"  success: {login.get('success')}")
cookie_str = cookie.split(";")[0]

# 2. 找版本
print("\n=== 2. 找有数据的版本 ===")
versions, _ = req("/api/v1/versions?page_size=20", cookies=cookie_str)
items = versions.get("data", {}).get("items", versions.get("items", []))
print(f"  总版本数: {len(items)}")

target_vid = None
for v in items[:10]:
    vid = v.get("id") or v.get("version_id")
    # 看关系数
    r, _ = req(f"/api/v1/relationships?version_id={vid}&page_size=1", cookies=cookie_str)
    if isinstance(r, dict):
        total = r.get("total", r.get("data", {}).get("total", 0))
        if total > 5:
            target_vid = vid
            print(f"  ✓ 找到有数据的版本: id={vid}, name={v.get('name')}, relations={total}")
            break

if not target_vid:
    # 任意挑一个
    if items:
        target_vid = items[0].get("id") or items[0].get("version_id")
        print(f"  任意选: id={target_vid}")
    else:
        print("  没有版本数据")
        exit(1)

# 3. Management 页 API: /api/v1/relationships
print(f"\n=== 3. Management API (version_id={target_vid}) ===")
mgmt, _ = req(f"/api/v1/relationships?version_id={target_vid}&page_size=10000", cookies=cookie_str)
if isinstance(mgmt, dict):
    mgmt_items = mgmt.get("data", {}).get("items", mgmt.get("items", []))
    mgmt_total = mgmt.get("total", len(mgmt_items))
    print(f"  Management 总关系数: {mgmt_total}")
    print(f"  Sample: {json.dumps(mgmt_items[0], ensure_ascii=False)[:200] if mgmt_items else 'empty'}")
    # 拿前 5 条的 id
    mgmt_ids = sorted([r.get("id") for r in mgmt_items if r.get("id")])[:5]
    print(f"  前 5 个关系 id: {mgmt_ids}")

# 4. Chart 页 API: /api/v1/bo/architecture/preview
print(f"\n=== 4. Chart API (v39.6 修复后) ===")
# 试不同的参数
for params in [
    f"version_id={target_vid}",
    f"version_id={target_vid}&business_object_ids=",
    f"version_id={target_vid}&service_module_ids=",
]:
    preview, _ = req(f"/api/v1/bo/architecture/preview?{params}", cookies=cookie_str)
    if isinstance(preview, dict):
        if "data" in preview:
            data = preview["data"]
        else:
            data = preview
        rels = data.get("relationships", [])
        bos = data.get("business_objects", [])
        # 算管理页 vs chart 页差
        if mgmt_items and rels:
            mgmt_ids = set(r.get("id") for r in mgmt_items if r.get("id"))
            chart_ids = set(r.get("id") for r in rels if r.get("id"))
            missing = mgmt_ids - chart_ids
            extra = chart_ids - mgmt_ids
            print(f"  params={params}: chart={len(rels)} 关系, mgmt={len(mgmt_ids)} 关系")
            print(f"    差集 (管理页有，图表页无): {sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}")
            print(f"    差集 (图表页有，管理页无): {sorted(extra)[:5]}{'...' if len(extra) > 5 else ''}")
        else:
            print(f"  params={params}: chart={len(rels)} 关系, BOs={len(bos)}")

# 5. 选具体 BO 测试
print(f"\n=== 5. 选前 3 个 BO 测试 OR 过滤 ===")
# 先拿 BOs
bos_res, _ = req(f"/api/v1/business-object?version_id={target_vid}&page_size=3", cookies=cookie_str)
if isinstance(bos_res, dict):
    bo_items = bos_res.get("data", {}).get("items", bos_res.get("items", []))
    if bo_items:
        bo_ids = [b.get("id") for b in bo_items if b.get("id")][:3]
        print(f"  选中 BO ids: {bo_ids}")
        params = f"version_id={target_vid}&business_object_ids={','.join(map(str, bo_ids))}"
        preview, _ = req(f"/api/v1/bo/architecture/preview?{params}", cookies=cookie_str)
        if isinstance(preview, dict):
            rels = preview.get("data", {}).get("relationships", [])
            print(f"  选 3 个 BO 后，preview 返回 {len(rels)} 条关系")
            if mgmt_items and rels:
                mgmt_ids = set(r.get("id") for r in mgmt_items if r.get("id"))
                chart_ids = set(r.get("id") for r in rels if r.get("id"))
                print(f"  交集 (OR 语义): {len(mgmt_ids & chart_ids)} / management 总 {len(mgmt_ids)}")
            # 抽样验证: src 或 tgt 在选中 BO 里
            rels_in_scope = [r for r in rels if r.get("source_bo_id") in bo_ids or r.get("target_bo_id") in bo_ids or r.get("sourceBoId") in bo_ids or r.get("targetBoId") in bo_ids]
            rels_out_scope = [r for r in rels if not (r.get("source_bo_id") in bo_ids or r.get("target_bo_id") in bo_ids or r.get("sourceBoId") in bo_ids or r.get("targetBoId") in bo_ids)]
            print(f"  关系 in scope (OR): {len(rels_in_scope)}")
            print(f"  关系 out scope: {len(rels_out_scope)}")

print("\n=== Done ===")
