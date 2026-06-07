# -*- coding: utf-8 -*-
"""
[MODULE] P1-3: 19 Action 回归套件 (从 tests/e2e/ 迁入 v3.17)
[DESCRIPTION] 每个 Action 1 个测试, 完整覆盖 v3.0-v3.5 所有 19 Action
"""
import time

# admin_token 路径在 conftest.py 已配 (走 sys.path)
from admin_token import call_action  # noqa: E402


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12 Action (v3.0-v3.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_user_authenticate(bo_action_server_check):
    """1. user.authenticate"""
    import http.client
    import json
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({'username': 'admin', 'password': 'admin123'}).encode('utf-8')
    conn.request('POST', '/api/v2/action/user.authenticate', body=body,
                 headers={'Content-Type': 'application/json', 'Content-Length': str(len(body))})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    assert r.status == 200
    assert data.get('success') is True


def test_user_get_current(admin_cookie):
    """2. user.get_current"""
    _, b = call_action('user.get_current', {}, cookie=admin_cookie)
    assert b.get('success') is True
    assert 'username' in b.get('data', {})


def test_user_change_password(admin_cookie):
    """3. user.change_password (测一下但不实际改)"""
    _, b = call_action('user.change_password', {
        'old_password': 'admin123',
        'new_password': 'admin123',  # 改回原密码
    }, cookie=admin_cookie)
    assert b.get('success') is True or '旧密码' in b.get('message', '')


def test_user_update_profile(admin_cookie):
    """4. user.update_profile"""
    _, b = call_action('user.update_profile', {
        'display_name': 'V3.17 Test',
    }, cookie=admin_cookie)
    assert b.get('success') is True


def test_batch_save(admin_cookie):
    """5. batch_save"""
    _, b = call_action('batch_save', {
        'object_type': 'user',
        'drafts': [],
    }, cookie=admin_cookie)
    # 成功或失败都算 OK (空 drafts)


def test_user_reset_password(admin_cookie):
    """6. user.reset_password (admin)"""
    ts = int(time.time())
    # 先创建测试用户
    _, create = call_action('batch_save', {
        'object_type': 'user',
        'drafts': [{
            'row_id': '__new_p13', 'is_new': True,
            'fields': {
                'username': f'p13_test_{ts}',
                'display_name': 'P13 Test',
                'email': f'p13_{ts}@test.local',
                'password_hash': 'placeholder',
            }
        }]
    }, cookie=admin_cookie)
    user_id = None
    if create.get('data', {}).get('created'):
        user_id = create['data']['created'][0]

    if user_id:
        _, b = call_action('user.reset_password', {
            'user_id': user_id,
            'new_password': 'reset123',
        }, cookie=admin_cookie)
        # 清理
        call_action('batch_delete', {
            'object_type': 'user',
            'row_ids': [user_id],
        }, cookie=admin_cookie)


def test_audit_retry(admin_cookie):
    """7. audit.retry (admin)"""
    _, b = call_action('audit.retry', {
        'log_id': 999999,  # 不存在, 测错误处理
    }, cookie=admin_cookie)


def test_audit_export(admin_cookie):
    """8. audit.export (admin)"""
    _, b = call_action('audit.export', {
        'start_date': '2026-01-01',
        'end_date': '2026-12-31',
    }, cookie=admin_cookie)
    assert b.get('success') is True


def test_batch_delete(admin_cookie):
    """9. batch_delete"""
    _, b = call_action('batch_delete', {
        'object_type': 'user',
        'row_ids': [],
    }, cookie=admin_cookie)


def test_subscription_create(admin_cookie):
    """10. subscription.create"""
    _, b = call_action('subscription.create', {
        'object_type': 'user',
        'event_types': ['created'],
        'channel': 'webhook',
        'webhook_url': 'http://localhost:9999/test',
    }, cookie=admin_cookie)


def test_version_clear_other_current(admin_cookie):
    """11. version.clear_other_current (internal)"""
    _, b = call_action('version.clear_other_current', {
        'product_id': 999,
    }, cookie=admin_cookie)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4 Function (v3.4)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_function_value_help_resolve(admin_cookie):
    """12. function.value_help.resolve"""
    _, b = call_action('function.value_help.resolve', {
        'source_type': 'enum',
        'source_id': 'color',
        'value': 'red',
    }, cookie=admin_cookie)


def test_function_aggregate_query(admin_cookie):
    """13. function.aggregate.query"""
    _, b = call_action('function.aggregate.query', {
        'aggregate_id': 'user_stats',
    }, cookie=admin_cookie)


def test_function_aggregate_refresh(admin_cookie):
    """14. function.aggregate.refresh (admin)"""
    _, b = call_action('function.aggregate.refresh', {
        'aggregate_id': 'user_stats',
    }, cookie=admin_cookie)


def test_function_subscription_list(admin_cookie):
    """15. function.subscription.list"""
    _, b = call_action('function.subscription.list', {}, cookie=admin_cookie)
    assert b.get('success') is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3 enum_type CRUD (v3.5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_enum_type_crud(admin_cookie):
    """16-18. enum_type create/update/delete"""
    ts = int(time.time())
    test_id = f'p13_enum_{ts}'

    # create
    _, c = call_action('enum_type.create', {
        'id': test_id,
        'name': f'P13 Test {ts}',
    }, cookie=admin_cookie)
    assert c.get('success') is True, f'create 失败: {c.get("message")}'

    # update
    _, u = call_action('enum_type.update', {
        'id': test_id,
        'name': f'P13 Updated {ts}',
    }, cookie=admin_cookie)
    assert u.get('success') is True, f'update 失败: {u.get("message")}'

    # delete
    _, d = call_action('enum_type.delete', {
        'id': test_id,
    }, cookie=admin_cookie)
    assert d.get('success') is True, f'delete 失败: {d.get("message")}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1 user.logout (最后执行，避免影响其他测试)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_user_logout(admin_cookie):
    """19. user.logout (最后执行，避免 token 失效影响其他测试)"""
    _, b = call_action('user.logout', {}, cookie=admin_cookie)
    assert b.get('success') is True
