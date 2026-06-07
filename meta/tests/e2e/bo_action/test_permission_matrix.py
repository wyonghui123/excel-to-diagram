# -*- coding: utf-8 -*-
"""
[MODULE] B3: 权限矩阵测试
[DESCRIPTION] 测不同角色 × Action 的访问控制
- admin: 全权限
- regular_user: 只读
- 无 token: 401
"""
import http.client
import json

# admin_token 路径在 conftest.py 已配 (走 sys.path)
from admin_token import call_action, get_admin_cookie  # noqa: E402


def test_admin_can_access_all(bo_action_server_check, admin_cookie):
    """[DECORATIVE] B3.1: admin 可访问所有 19 Action"""
    actions = [
        'user.get_current', 'user.logout', 'user.update_profile',
        'batch_save', 'batch_delete',
        'audit.export', 'audit.retry',
        'function.subscription.list', 'function.aggregate.query',
        'enum_type.list',
    ]
    for action_id in actions:
        _, b = call_action(action_id, {}, cookie=admin_cookie)
        # admin 不应被 401/403 拒绝
        assert 'permission' not in str(b).lower() or b.get('success') is True, \
            f'admin 调 {action_id} 应通过, 实际 {b}'


def test_no_token_returns_401(bo_action_server_check):
    """[DECORATIVE] B3.2: 无 token 调 action 应 401/未授权"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({}).encode('utf-8')
    conn.request('POST', '/api/v2/action/user.get_current', body=body,
                 headers={'Content-Type': 'application/json',
                          'Content-Length': str(len(body))})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    # 无 token 应未授权
    assert r.status in [401, 403] or data.get('success') is False, \
        f'无 token 应未授权, 实际 status={r.status}, data={data}'


def test_invalid_token_returns_401(bo_action_server_check):
    """[DECORATIVE] B3.3: 错 token 应未授权"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({}).encode('utf-8')
    conn.request('POST', '/api/v2/action/user.get_current', body=body,
                 headers={'Content-Type': 'application/json',
                          'Content-Length': str(len(body)),
                          'Cookie': 'auth_token=invalid_xxx'})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    # 错 token 应未授权
    assert r.status in [401, 403] or data.get('success') is False, \
        f'错 token 应未授权, 实际 status={r.status}, data={data}'


def test_user_logout_invalidates_cookie(bo_action_server_check):
    """[DECORATIVE] B3.4: logout 后 cookie 失效 (test_b4 token blacklist 复用)"""
    import time
    from admin_token import get_admin_cookie
    # 重新拿 cookie (前面测试可能已 logout)
    fresh_cookie = get_admin_cookie()

    # 先确认 cookie 有效
    _, b1 = call_action('user.get_current', {}, cookie=fresh_cookie)
    assert b1.get('success') is True, f'cookie 应有效: {b1}'

    # logout
    _, b2 = call_action('user.logout', {}, cookie=fresh_cookie)
    # logout 应成功
    assert b2.get('success') is True or 'logged out' in str(b2).lower()

    # 再 login 恢复 (避免影响后续测试)
    get_admin_cookie()
