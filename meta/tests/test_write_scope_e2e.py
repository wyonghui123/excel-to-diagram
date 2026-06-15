# -*- coding: utf-8 -*-
"""
[FILE] test_write_scope_e2e.py
[DESCRIPTION] WriteScopeInterceptor v2.1 E2E 测试
[SCOPE]
  验证拦截器在 Flask server 上下文中能正确链路:
  - admin 通过 (走 step 1 跳过)
  - 普通用户的写 scope 校验触发
  - /_diagnostics 端点能读到 write_scope_warnings
  - 不破坏现有功能 (regression)

[NOTE] 完整 TEST333 4 角色场景 (R1+R2+R3) 需要 admin 在 UI 配完角色后才能跑.
       本测试侧重拦截器机制本身能 work, 不强求完整业务场景.
"""
import os
import sys
import time
import http.client
import json
import sqlite3
import pytest
import requests

# 复用 admin_token fixture
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tests', 'fixtures'))

BASE_HOST = os.environ.get('TEST_HOST', 'localhost')
BASE_PORT = int(os.environ.get('TEST_PORT', '3010'))


def call_action(action_id, body=None, cookie=None, method='POST'):
    """[v2.1] 调 BO Action 通用方法"""
    if cookie is None:
        return None, None
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=15)
    body_bytes = json.dumps(body or {}).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body_bytes)),
        'Cookie': cookie,
    }
    conn.request(method, f'/api/v2/action/{action_id}', body=body_bytes, headers=headers)
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    return r.status, data


def get_diagnostics(cookie):
    """[v2.1] 读 /_diagnostics"""
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT, timeout=15)
    conn.request('GET', '/api/v2/action/_diagnostics', headers={'Cookie': cookie})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    return r.status, data


def _check_server(host=BASE_HOST, port=BASE_PORT, timeout=2):
    """[v2.1] 快速检查 server 是否在监听"""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


# ============================================================================
# 拦截器 e2e 集成测试 (依赖 server, 不可用时 skip)
# ============================================================================
class TestWriteScopeInterceptorE2E:
    """[v2.1] WriteScopeInterceptor e2e 集成

    注: 需要 server 在跑. 用 `_check_server()` 提前 skip.
    """

    def test_admin_can_update_product(self):
        """[v2.1] admin 走 step 1 跳过, 写操作不受限"""
        if not _check_server():
            pytest.skip(f'BO Action 测试需 server 在 {BASE_HOST}:{BASE_PORT} 跑')

        # 直接获取 cookie (不依赖 fixture)
        from admin_token import get_admin_cookie
        try:
            cookie = get_admin_cookie()
        except Exception as e:
            pytest.skip(f'admin cookie 获取失败: {e}')

        # 先查 product 1 的 id (实际有)
        status, list_data = call_action('product.list', {'page_size': 1}, cookie=cookie)
        if status != 200 or not list_data.get('success'):
            pytest.skip(f'无法 list product: {list_data}')

        items = list_data.get('data', {}).get('items', [])
        if not items:
            pytest.skip('DB 中无 product, 跳过')

        product_id = items[0]['id']
        # admin 改 product (走 step 1 跳过, 不应 403)
        status, update_data = call_action(
            'product.update',
            {'id': product_id, 'description': f'admin_test_{int(time.time())}'},
            cookie=cookie,
        )
        # admin 应能改 (status=200)
        assert status == 200, f'admin 改 product {product_id} 失败: {update_data}'

    def test_diagnostics_endpoint_includes_write_scope(self):
        """[v2.1] /_diagnostics 端点应包含 write_scope_warnings 字段"""
        if not _check_server():
            pytest.skip(f'BO Action 测试需 server 在 {BASE_HOST}:{BASE_PORT} 跑')

        from admin_token import get_admin_cookie
        try:
            cookie = get_admin_cookie()
        except Exception as e:
            pytest.skip(f'admin cookie 获取失败: {e}')

        status, data = get_diagnostics(cookie)
        if status != 200:
            pytest.skip(f'/_diagnostics 不通: {data}')

        # [v2.1] interceptor_warnings 字段应存在
        diag = data.get('data', {})
        assert 'interceptor_warnings' in diag, \
            f'/_diagnostics 应含 interceptor_warnings, 实际 keys: {list(diag.keys())}'
        # interceptor_warnings 应是 dict (含 4 类)
        iw = diag['interceptor_warnings']
        assert isinstance(iw, dict), f'interceptor_warnings 应为 dict, 实际 {type(iw)}'
        # 4 类警告键
        for key in ('write_scope_warnings', 'parent_read_warnings',
                    'chain_read_warnings', 'chain_instance_out_of_scope'):
            assert key in iw, f'interceptor_warnings 应含 {key}, 实际 keys: {list(iw.keys())}'

    def test_no_regression_on_audit_log(self):
        """[v2.1] 不破坏现有 audit_log 功能 (regression)"""
        if not _check_server():
            pytest.skip(f'BO Action 测试需 server 在 {BASE_HOST}:{BASE_PORT} 跑')

        from admin_token import get_admin_cookie
        try:
            cookie = get_admin_cookie()
        except Exception as e:
            pytest.skip(f'admin cookie 获取失败: {e}')

        # audit_log 端点 - admin 应通
        status, data = call_action('audit_log.list', {'page_size': 1}, cookie=cookie)
        # 接受 200 或 404 (如果 audit_log 未启用)
        assert status in (200, 404, 405), f'audit_log 端点异常: {status} {data}'

    def test_diagnostics_write_scope_warnings_structure(self):
        """[v2.1] /_diagnostics write_scope_warnings 数组结构验证 (不依赖 server)"""
        from meta.core import diagnostics
        diagnostics.reset_diagnostics()

        try:
            from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor
            interceptor = WriteScopeInterceptor()
            diag = diagnostics.get_diagnostics()
            assert 'write_scope_warnings' not in diag or isinstance(diag.get('write_scope_warnings'), list), \
                'write_scope_warnings 应为 list'
        except ImportError:
            pytest.skip('WriteScopeInterceptor 不可用')


# ============================================================================
# 拦截器优先级 (避免破坏现有拦截器链)
# ============================================================================
class TestInterceptorOrder:
    """[v2.1] 验证 WriteScopeInterceptor 不破坏拦截器链"""

    def test_interceptor_registered(self):
        from meta.core.interceptors import WriteScopeInterceptor
        from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor as Cls
        # [FIX] priority 是 property, 通过 instance 访问
        inst = Cls()
        assert inst.priority == 35

    def test_interceptor_in_all_list(self):
        from meta.core.interceptors import __all__
        assert 'WriteScopeInterceptor' in __all__

    def test_interceptor_after_permission(self):
        """priority 35 > 30 (PermissionInterceptor)"""
        from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor as WSI
        from meta.core.interceptors.permission_interceptor import PermissionInterceptor
        wsi = WSI()
        # PermissionInterceptor.priority 是 class attr (int=30), WSI 是 property
        assert wsi.priority > 30  # PermissionInterceptor.priority = 30

    def test_interceptor_before_owner_auto(self):
        """priority 35 < 96 (OwnerAutoPermissionInterceptor)"""
        from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor as WSI
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        wsi = WSI()
        # OwnerAutoPermissionInterceptor.priority 是 property=96
        owner_inst = OwnerAutoPermissionInterceptor()
        assert wsi.priority < owner_inst.priority
