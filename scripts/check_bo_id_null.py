# -*- coding: utf-8 -*-
"""
验证 business_object API 的 id=NULL bug
执行: python scripts/check_bo_id_null.py
"""
import requests
import time
import sys

BASE = "http://localhost:3010"


def main():
    s = requests.Session()
    # 1. dev-login
    r = s.get(f"{BASE}/api/v1/auth/dev-login?username=admin", timeout=10)
    print(f"[1] dev-login status: {r.status_code}")
    if r.status_code != 200:
        print(f"    FAILED: {r.text[:200]}")
        return 1

    # 2. 找 product
    r = s.get(f"{BASE}/api/v2/bo/product?page_size=10", timeout=10)
    products = r.json()
    items = (products.get("data") or {}).get("items") if isinstance(products.get("data"), dict) else products.get("data")
    if not items:
        print(f"[2] no products, response: {str(products)[:300]}")
        return 1
    p = items[0]
    print(f"[2] products: {len(items)}, using id={p.get('id')} name={p.get('name')}")

    # 3. 找 version
    r = s.get(f"{BASE}/api/v2/bo/version?product_id={p['id']}", timeout=10)
    versions = r.json()
    v_items = (versions.get("data") or {}).get("items") if isinstance(versions.get("data"), dict) else versions.get("data")
    if not v_items:
        print(f"[3] no versions for product {p['id']}")
        return 1
    v = v_items[0]
    print(f"[3] versions: {len(v_items)}, using id={v.get('id')} name={v.get('name')}")

    # 4. 创建 business_object
    code = f"E2E_TEST_{int(time.time())}"
    payload = {
        "code": code,
        "name": "Test BO (id=NULL check)",
        "version_id": v["id"],
        "is_active": True,
    }
    r = s.post(f"{BASE}/api/v2/bo/business_object", json=payload, timeout=10)
    print(f"[4] create status: {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"    FAILED: {r.text[:500]}")
        return 1
    result = r.json()
    data = result.get("data") or {}
    print(f"[5] response: status={r.status_code} id={data.get('id')} code={data.get('code')}")

    # 5. 关键检查
    if data.get("id") is None:
        print("[BUG-CONFIRMED] API response id IS NULL!")
    else:
        print(f"[OK] response id is {data.get('id')}")

    # 6. 验证 DB (再次 GET)
    if data.get("id"):
        r2 = s.get(f"{BASE}/api/v2/bo/business_object/{data['id']}", timeout=10)
        data2 = (r2.json() or {}).get("data") or {}
        db_id = data2.get("id")
        print(f"[6] GET status: {r2.status_code} DB id={db_id}")
        if db_id is None:
            print("[BUG-CONFIRMED] DB has id=NULL!")
        else:
            print(f"[OK] DB id is {db_id}")

    # 7. 清理: 删除测试数据
    if data.get("id"):
        s.delete(f"{BASE}/api/v2/bo/business_object/{data['id']}", timeout=10)
        print(f"[7] cleanup done")

    return 0


if __name__ == "__main__":
    sys.exit(main())
