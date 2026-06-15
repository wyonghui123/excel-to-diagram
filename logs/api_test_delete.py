# -*- coding: utf-8 -*-
"""
[FIX 2026-06-12] 端到端验证：删除限制是否真的生效
- 场景 1：删除有成员的用户组 → 应被拒 (RESTRICT_ON_DELETE)
- 场景 2：删除有版本的产品 → 应被拒 (RESTRICT_ON_DELETE)
- 场景 3：删除空用户组 → 应成功

用法：python logs/api_test_delete.py
要求：服务在 3010 端口跑（service_manager.ps1 status）
"""
import json
import sys
import time

import requests

BASE = "http://localhost:3010"


def dev_login(session: requests.Session) -> dict:
    """user.authenticate 拿 cookie + user_id

    dev-login 端点目前有 NotFound 500 bug（F.3 待修），改用稳定的 authenticate action
    """
    r = session.post(f"{BASE}/api/v2/action/user.authenticate",
                     json={"username": "admin", "password": "admin123"})
    r.raise_for_status()
    data = r.json()
    if not data.get("data", {}).get("token"):
        raise RuntimeError(f"no token in response: {data}")
    return data


def call_bo(method: str, path: str, session: requests.Session, body=None):
    """直接调 /api/v2/bo/{type}/{id}"""
    url = f"{BASE}{path}"
    if method == "GET":
        r = session.get(url)
    elif method == "POST":
        r = session.post(url, json=body or {})
    elif method == "PUT":
        r = session.put(url, json=body or {})
    elif method == "DELETE":
        r = session.delete(url)
    else:
        raise ValueError(method)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:500]}


def call_action(action_id: str, params: dict, session: requests.Session):
    """调 /api/v2/action/{action_id}"""
    url = f"{BASE}/api/v2/action/{action_id}"
    r = session.post(url, json={"params": params})
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:500]}


def find_one_user(session):
    """拿一个存在的 user id（用于绑成员）"""
    status, data = call_bo("GET", "/api/v2/bo/user?page=1&page_size=1", session)
    if status == 200 and data.get("success") and data.get("data", {}).get("items"):
        return data["data"]["items"][0]["id"]
    return None


def find_one_product(session):
    """拿一个存在的 product id"""
    status, data = call_bo("GET", "/api/v2/bo/product?page=1&page_size=1", session)
    if status == 200 and data.get("success") and data.get("data", {}).get("items"):
        return data["data"]["items"][0]["id"]
    return None


def find_version_for_product(session, product_id):
    """找 product 下的 version，没有就创一个"""
    status, data = call_bo(
        "GET", f"/api/v2/bo/version?filters=product_id=={product_id}&page=1&page_size=1", session
    )
    if status == 200 and data.get("success") and data.get("data", {}).get("items"):
        return data["data"]["items"][0]["id"]
    return None


def main():
    s = requests.Session()

    # 1) dev-login
    print("=" * 70)
    print("SETUP: dev-login")
    print("=" * 70)
    auth = dev_login(s)
    print(f"  login: {json.dumps(auth, ensure_ascii=False)[:200]}")
    if not auth.get("data", {}).get("token"):
        print("  [FATAL] authenticate failed")
        sys.exit(1)
    user_id = auth.get("data", {}).get("user", {}).get("user_id") or 1
    print(f"  user_id = {user_id}")

    ts = int(time.time())
    results = []

    # ============================================================
    # TEST 1: user_group with member → DELETE should be blocked
    # ============================================================
    print()
    print("=" * 70)
    print("TEST 1: user_group with member → DELETE should be blocked")
    print("=" * 70)
    ug_code = f"TEST_UG_DEL_{ts}"

    status, data = call_bo("POST", "/api/v2/bo/user_group", s, {
        "code": ug_code,
        "name": "测试-API-用户组",
    })
    print(f"  Create user_group: status={status}")
    print(f"  -> {json.dumps(data, ensure_ascii=False)[:200]}")
    if not data.get("success"):
        print("  [SKIP] cannot create user_group")
        results.append(("TEST 1", False, "cannot create user_group"))
    else:
        ug_id = data["data"]["id"]
        print(f"  -> ug_id = {ug_id}")

        # 加成员 — 优先用 action, 失败用 BO POST
        member_added = False
        status, data = call_action("user_group_member_create", {
            "group_id": ug_id,
            "user_id": user_id,
        }, s)
        if data.get("success"):
            member_added = True
            print(f"  Add member (action): success=True")
        else:
            # Fallback: 直接 BO POST
            print(f"  Add member (action) failed: {data.get('message', '')[:100]}")
            print(f"  -> fallback to BO POST")
            status, data = call_bo("POST", "/api/v2/bo/user_group_member", s, {
                "group_id": ug_id,
                "user_id": user_id,
            })
            member_added = data.get("success", False)
            print(f"  Add member (BO POST): success={member_added}, msg={data.get('message', '')[:100]}")

        # 尝试删除
        status, data = call_bo("DELETE", f"/api/v2/bo/user_group/{ug_id}", s)
        print(f"  DELETE user_group: status={status}")
        print(f"  -> success = {data.get('success')}")
        print(f"  -> message = {data.get('message')}")
        print(f"  -> error = {data.get('error')}")

        passed = (not data.get("success")) and ("成员" in (data.get("message") or "")
                                                 or "RESTRICT" in str(data.get("error") or "").upper())
        if passed:
            print("  ✅ TEST 1 PASSED: 有成员的组被拒")
        else:
            print("  ❌ TEST 1 FAILED: 应被拒但未拒")
        results.append(("TEST 1: user_group+member 拒绝删除", passed, data.get("message", "")))

    # ============================================================
    # TEST 2: product with version → DELETE should be blocked
    # ============================================================
    print()
    print("=" * 70)
    print("TEST 2: product with version → DELETE should be blocked")
    print("=" * 70)
    product_id = find_one_product(s)
    if not product_id:
        print("  [SKIP] no product in DB")
        results.append(("TEST 2", False, "no product"))
    else:
        print(f"  product_id = {product_id}")
        version_id = find_version_for_product(s, product_id)
        if not version_id:
            print("  [INFO] product has no version, creating one...")
            status, data = call_bo("POST", "/api/v2/bo/version", s, {
                "product_id": product_id,
                "name": f"TEST_VERSION_{ts}",
                "code": f"TEST_V_{ts}",
            })
            print(f"  Create version: success={data.get('success')}, msg={data.get('message', '')[:100]}")
            if data.get("success"):
                version_id = data["data"]["id"]
        if version_id:
            print(f"  -> version_id = {version_id}")
            # 尝试删除产品（带 version）
            status, data = call_bo("DELETE", f"/api/v2/bo/product/{product_id}", s)
            print(f"  DELETE product: status={status}")
            print(f"  -> success = {data.get('success')}")
            print(f"  -> message = {data.get('message')}")
            print(f"  -> error = {data.get('error')}")

            # 修复后 message 应包含具体子表名, 如 "（产品版本: 5, 领域: 10）"
            passed = (not data.get("success")) and (
                "版本" in (data.get("message") or "")
                or "子元素" in (data.get("message") or "")
                or "RESTRICT" in str(data.get("error") or "").upper()
                or "DELETE_FAILED" in str(data.get("error") or "").upper()
                or "HAS_CHILDREN" in str(data.get("error") or "").upper()
            )
            if passed:
                print("  ✅ TEST 2 PASSED: 有版本的产品被拒")
            else:
                print("  ❌ TEST 2 FAILED: 应被拒但未拒")
            results.append(("TEST 2: product+version 拒绝删除", passed, data.get("message", "")))
        else:
            results.append(("TEST 2: product+version 拒绝删除", False, "no version"))

    # ============================================================
    # TEST 3: empty user_group → DELETE should succeed
    # ============================================================
    print()
    print("=" * 70)
    print("TEST 3: empty user_group → DELETE should succeed")
    print("=" * 70)
    ug_code_empty = f"TEST_UG_EMPTY_{ts}"
    status, data = call_bo("POST", "/api/v2/bo/user_group", s, {
        "code": ug_code_empty,
        "name": "测试-空用户组",
    })
    if not data.get("success"):
        print(f"  [SKIP] cannot create: {data.get('message')}")
        results.append(("TEST 3: empty group 可删除", False, "cannot create"))
    else:
        ug_id = data["data"]["id"]
        print(f"  -> ug_id = {ug_id}")
        status, data = call_bo("DELETE", f"/api/v2/bo/user_group/{ug_id}", s)
        print(f"  DELETE empty: status={status}")
        print(f"  -> success = {data.get('success')}")
        print(f"  -> message = {data.get('message')}")
        passed = data.get("success") is True
        if passed:
            print("  ✅ TEST 3 PASSED: 空组可删")
        else:
            print("  ❌ TEST 3 FAILED: 空组应可删但被拒")
        results.append(("TEST 3: empty group 可删除", passed, data.get("message", "")))

    # ============================================================
    # SUMMARY
    # ============================================================
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed_count = sum(1 for _, p, _ in results if p)
    total = len(results)
    for name, p, msg in results:
        mark = "✅" if p else "❌"
        print(f"  {mark} {name}: {msg[:120]}")
    print()
    print(f"  {passed_count}/{total} passed")
    sys.exit(0 if passed_count == total else 1)


if __name__ == "__main__":
    main()
