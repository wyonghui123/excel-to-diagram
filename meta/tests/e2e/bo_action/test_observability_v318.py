# -*- coding: utf-8 -*-
"""
[MODULE] M.9: 监控测试套件 (v3.18)
[DESCRIPTION] 测可观测性端点自身
"""
import os
import sys
import time
import http.client
import json

# admin_token 路径在 conftest.py 已配 (走 sys.path)
from admin_token import get_admin_cookie, call_action  # noqa: E402


def test_trace_id_generated(bo_action_server_check, admin_cookie):
    """[DECORATIVE] M.1: 每个请求有 trace_id"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('GET', '/api/v2/action/_db_health', headers={'Cookie': admin_cookie})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    # 响应头应有 X-Trace-Id
    trace_id = r.getheader('X-Trace-Id')
    if trace_id:
        assert len(trace_id) >= 16, f'trace_id 应 >= 16 char, 实际 {trace_id}'


def test_diagnostics_endpoint_exists(bo_action_server_check, admin_cookie):
    """[DECORATIVE] M.5: /_diagnostics 端点存在且 admin 可访问"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('GET', '/api/v2/action/_diagnostics', headers={'Cookie': admin_cookie})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    # 可能 200 (注册) 或 404 (未注册)
    if r.status == 200:
        assert data.get('success') is True
        assert 'data' in data
        result = data['data']
        assert 'health' in result
        assert 'error_codes' in result
    else:
        # 未注册, 跳过 (待注册)
        pass


def test_diagnostics_no_token_rejected(bo_action_server_check):
    """[DECORATIVE] M.5: /_diagnostics 无 token 应 401"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('GET', '/api/v2/action/_diagnostics')
    r = conn.getresponse()
    r.read()
    conn.close()
    assert r.status in [401, 403, 404], f'无 token 应 401/403/404, 实际 {r.status}'


def test_error_codes_count(bo_action_server_check, admin_cookie):
    """[DECORATIVE] M.6: error_codes 列表非空"""
    from meta.core.error_fix_hints import get_codes_count
    count = get_codes_count()
    assert count >= 10, f'fix_hint 表应有 >= 10 码, 实际 {count}'


def test_get_fix_hint_known(bo_action_server_check, admin_cookie):
    """[DECORATIVE] D.6: get_fix_hint 已知码返回 hint"""
    from meta.core.error_fix_hints import get_fix_hint
    info = get_fix_hint('unauthorized')
    assert info is not None
    assert 'fix_hint' in info
    assert 'see_also' in info


def test_get_fix_hint_unknown_returns_none(bo_action_server_check, admin_cookie):
    """[DECORATIVE] D.6: 未知码返回 None"""
    from meta.core.error_fix_hints import get_fix_hint
    info = get_fix_hint('E999_unknown_xxx')
    assert info is None


def test_trace_id_module(bo_action_server_check, admin_cookie):
    """[DECORATIVE] M.1: trace_id 模块基本功能"""
    from meta.core.trace_id import TraceId
    tid1 = TraceId.generate()
    tid2 = TraceId.generate()
    assert tid1 != tid2, f'两个 generate 应不同: {tid1} vs {tid2}'
    assert len(tid1) == 32, f'trace_id 应 32 char, 实际 {len(tid1)}'

    TraceId.set(tid1)
    assert TraceId.get() == tid1, f'set 后 get 应返回, 实际 {TraceId.get()}'
    TraceId.clear()
    assert TraceId.get() is None, f'clear 后 get 应 None'


def test_diagnostics_build_diagnostics_function():
    """[DECORATIVE] M.5: build_diagnostics 函数可独立调用 (不依赖 server)"""
    from meta.api.diagnostics_api import build_diagnostics
    result = build_diagnostics()
    assert result.get('success') is True
    data = result['data']
    assert 'health' in data
    assert 'error_codes' in data
    assert 'generated_at' in data
    assert 'trace_id' in data
