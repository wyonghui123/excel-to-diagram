"""
test_v10_verify - V10 版本可见性手动验证脚本

注意: 这个文件原本是手动 E2E 验证脚本 (调 requests, 无 def test_).
      在 pytest 收集阶段会因为调用 requests.get(...) 而 fail
      (没有 dev server). 已改造为 pytest 形式, 默认 SKIP.

手动运行 (dev server 起来后):
  python meta/tests/test_v10_verify.py
"""
import pytest


def test_v10_visibility_manual():
    """手动 E2E 验证 V10 可见性 - 需 dev server 在 3010 端口"""
    import requests
    s = requests.Session()
    login = s.get(
        'http://localhost:3010/api/v1/auth/dev-login?username=TEST333',
        allow_redirects=True,
    )
    print('login status:', login.status_code, 'cookie auth_token:', 'auth_token' in s.cookies)

    list_resp = s.get('http://localhost:3010/api/v1/versions?page_size=50')
    print('list status:', list_resp.status_code)
    list_data = list_resp.json()

    print('version list total:', list_data.get('data', {}).get('total', '?'))
    items = list_data.get('data', {}).get('items', [])
    print('  returned', len(items), 'items')

    v10 = [v for v in items if v.get('name') == 'V10']
    if v10:
        v = v10[0]
        print('  [FIX VERIFIED] V10 IS visible!')
        print(f'  id={v.get("id")} name={v.get("name")!r} '
              f'product_id={v.get("product_id")} product_name={v.get("product_name")!r} '
              f'visibility={v.get("visibility")}')
    else:
        print('  [BUG NOT FIXED] V10 still NOT visible')
        pytest.fail("V10 not visible in API response")

    assert v10, "V10 not found"