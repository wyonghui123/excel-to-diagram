# -*- coding: utf-8 -*-
"""
[FILE] test_frontend_e2e_test111.py
[DESCRIPTION] 真正的前端 E2E 测试 (模拟前端 HTTP 请求)
[场景] 复现用户报告: TEST111 产品 + 2 个同名 V11 → 整批回滚
[路径] HTTP POST /api/v2/action/batch_save (前端真实调用路径)
[NOTE] 这是用户视角的端到端测试, 不是单元测试:
       前端 → HTTP → Flask → batch_save_handler → DB
       通过 → 真实 (没绕过任何层)
"""
import os
import sys
import time
import json
import requests
from pathlib import Path

BASE_URL = 'http://localhost:3010'


def _list_versions_via_api(s: requests.Session, product_id: int) -> list:
    """用 HTTP 列出 product 下所有 version (避免 raw SQL)"""
    r = s.get(
        f'{BASE_URL}/api/v2/action/version/_list',
        params={'where': json.dumps({'product_id': product_id}),
                'limit': 100},
        timeout=15,
    )
    data = r.json()
    if not data.get('success'):
        return []
    return data.get('data', {}).get('rows', [])


def _delete_via_api(s: requests.Session, object_type: str, record_id: int) -> bool:
    """用 HTTP 删除记录 (避免 raw SQL)"""
    r = s.post(
        f'{BASE_URL}/api/v2/action/{object_type}/_delete',
        json={'id': record_id},
        timeout=15,
    )
    return r.json().get('success', False)


def _login() -> requests.Session:
    """模拟前端登录: dev-login 拿 httpOnly cookie"""
    s = requests.Session()
    r = s.get(f'{BASE_URL}/api/v1/auth/dev-login?username=admin', timeout=10)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    assert 'auth_token' in s.cookies, "no auth_token cookie"
    return s


def _create_product(s: requests.Session, name: str, code: str) -> int:
    """前端调用 batch_save 创建产品"""
    r = s.post(f'{BASE_URL}/api/v2/action/batch_save',
               json={
                   'object_type': 'product',
                   'drafts': [{
                       'row_id': f'__new_p_{int(time.time()*1000)}',
                       'is_new': True,
                       'fields': {'name': name, 'code': code}
                   }]
               }, timeout=15)
    data = r.json()
    assert data.get('success'), f"product create failed: {data}"
    product_id = data.get('data', {}).get('created', [None])[0]
    assert product_id, f"no product_id: {data}"
    return product_id


def _batch_create_versions(s: requests.Session, product_id: int, name: str, code1: str, code2: str):
    """前端调用 batch_save 一次创建 2 个版本 (相同 name)"""
    r = s.post(f'{BASE_URL}/api/v2/action/batch_save',
               json={
                   'object_type': 'version',
                   'drafts': [
                       {'row_id': '__new_v1', 'is_new': True,
                        'fields': {'name': name, 'code': code1, 'product_id': product_id}},
                       {'row_id': '__new_v2', 'is_new': True,
                        'fields': {'name': name, 'code': code2, 'product_id': product_id}},  # 同名
                   ]
               }, timeout=15)
    return r.status_code, r.json()


def _cleanup(s: requests.Session, product_id: int):
    """通过 HTTP API 清理 (避免 raw SQL)"""
    versions = _list_versions_via_api(s, product_id)
    for v in versions:
        _delete_via_api(s, 'version', v['id'])
    _delete_via_api(s, 'product', product_id)


def test_test111_frontend_e2e():
    """[场景1] 用户报告的 TEST111 场景: 模拟前端 HTTP 一次提交 2 个同名 V11"""
    print("=" * 70)
    print("[前端 E2E 场景1] 用户报告: TEST111 + V11_重名")
    print("=" * 70)

    s = _login()
    print(f"[1/5] login OK, cookie auth_token 长度: {len(s.cookies.get('auth_token', ''))}")

    suffix = int(time.time() * 1000)
    product_name = f'TEST111_FRONTEND_E2E_{suffix}'
    product_code = f'PCODE_{suffix}'
    version_name = f'V11_{suffix}'

    print(f"[2/5] 创建产品 {product_name} (用前端 batch_save API)...")
    product_id = _create_product(s, product_name, product_code)
    print(f"      product_id = {product_id}")

    print(f"[3/5] 模拟前端一次提交 2 个同名 version ({version_name})...")
    status, resp = _batch_create_versions(s, product_id, version_name,
                                          f'V1_{suffix}', f'V2_{suffix}')
    print(f"      HTTP status: {status}")
    print(f"      success: {resp.get('success')}")
    print(f"      message: {resp.get('message', '')[:200]}")
    print(f"      data.failures: {resp.get('data', {}).get('failures', [])}")

    print(f"[4/5] HTTP _list version: product_id={product_id} 下有几个 version?")
    versions = _list_versions_via_api(s, product_id)
    count = len(versions)
    print(f"      rows: {[v.get('name') for v in versions]}")
    print(f"      count: {count}")

    print(f"[5/5] 清理...")
    _cleanup(s, product_id)

    # 断言
    print("\n" + "=" * 70)
    print("[VERIFICATION]")
    print("=" * 70)
    print(f"  - HTTP success (期望 False): {resp.get('success')}")
    print(f"  - DB version count (期望 0): {count}")

    assert resp.get('success') is False, "前端 E2E: 失败时 HTTP 应返回 success=False"
    assert count == 0, f"前端 E2E: 事务未回滚! DB 仍有 {count} 个 version, rows={[v.get('name') for v in versions]}"
    print("\n[PASS 前端 E2E 场景1] 整批回滚生效! 用户报告的 TEST111 bug 已修复")
    return True


def test_generic_frontend_e2e():
    """[场景2] 通用前端场景: 不同产品名 + 同名版本"""
    print("=" * 70)
    print("[前端 E2E 场景2] 通用场景: TEST_GENERIC + V_DUP")
    print("=" * 70)

    s = _login()
    suffix = int(time.time() * 1000)
    product_name = f'TEST_GENERIC_FE_E2E_{suffix}'
    product_code = f'PCODE_{suffix}'
    version_name = f'V_DUP_{suffix}'

    print(f"[1/4] 创建产品 {product_name}...")
    product_id = _create_product(s, product_name, product_code)

    print(f"[2/4] 一次提交 2 个同名 version ({version_name})...")
    status, resp = _batch_create_versions(s, product_id, version_name,
                                          f'V1_{suffix}', f'V2_{suffix}')
    print(f"      HTTP success: {resp.get('success')}")
    print(f"      data.failures: {resp.get('data', {}).get('failures', [])}")

    versions = _list_versions_via_api(s, product_id)
    count = len(versions)
    print(f"[3/4] HTTP _list count: {count}, rows: {[v.get('name') for v in versions]}")

    _cleanup(s, product_id)
    print(f"[4/4] cleanup done")

    assert resp.get('success') is False
    assert count == 0
    print("\n[PASS 前端 E2E 场景2] 整批回滚生效")
    return True


if __name__ == '__main__':
    print("=" * 70)
    print("[前端 E2E] 真实 HTTP 路径, 模拟前端操作 batch_save")
    print(f"  - 目标: {BASE_URL}")
    print("=" * 70)

    try:
        test_test111_frontend_e2e()
        test_generic_frontend_e2e()
        print("\n" + "=" * 70)
        print("[ALL PASS] 真实前端 E2E 全部通过! 用户报告的 bug 已闭环修复")
        print("=" * 70)
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[ERROR] {e}")
        sys.exit(1)
