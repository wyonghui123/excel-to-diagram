# -*- coding: utf-8 -*-
"""
[MODULE] 测试 user.get_current (v3.18 自动生成, D.1)
[DESCRIPTION] AI Coding Agent 写的测试模板

[DECORATIVE] 修改点:
1. 改 action_id (已填)
2. 填 prepare_data (可选)
3. 调 assertions (默认 smoke)
4. 加更多 edge cases

跑:
  python d:\\filework\\test.py --single meta/tests/e2e/bo_action/test_user_get_current.py
"""
import time
import os
import sys

# admin_token 路径在 conftest.py 已配 (走 sys.path)
from admin_token import call_action


def test_user_get_current_happy_path(bo_action_server_check, admin_cookie):
    """[DECORATIVE] 正常路径: user.get_current 应成功"""
    _, b = call_action('user.get_current', {}, cookie=admin_cookie)
    assert b.get('success') is True, f'user.get_current 应 success, 实际 {{b}}'


def test_user_get_current_permission_denied(bo_action_server_check):
    """[DECORATIVE] 无 token 应 401/403"""
    import http.client
    import json
    conn = http.client.HTTPConnection('localhost', int(os.environ.get('AGENT_PORT', 3010)), timeout=10)
    body = json.dumps({}).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
    }
    conn.request('POST', '/api/v2/action/user.get_current', body=body, headers=headers)
    r = conn.getresponse()
    r.read()
    conn.close()
    assert r.status in [401, 403], f'无 token 应 401/403, 实际 {r.status}'


def test_user_get_current_invalid_input(bo_action_server_check, admin_cookie):
    """[DECORATIVE] 无效输入应 graceful 失败"""
    _, b = call_action('user.get_current', {'__invalid__': True}, cookie=admin_cookie)
    # 不期望崩溃
    assert isinstance(b, dict), f'响应应是 dict, 实际 {type(b)}'
    assert 'success' in b, f'响应应含 success 字段, 实际 {b.keys()}'
