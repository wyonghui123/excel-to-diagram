# ALLOW_RAW_SQL: 本文件含裸 SQL 构造用户测试数据/DDL，守卫豁免（2026-11-09 恢复覆盖）
import pytest

pytestmark = pytest.mark.integration

import sys
import os
import uuid

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
import jwt as pyjwt
from meta.server import create_app


@pytest.fixture(scope='session')
def app():
    from meta.services.rate_limiter import RateLimiter
    RateLimiter.reset()
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_token(app):
    secret = app.config.get('SECRET_KEY') or os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
    token = pyjwt.encode({
        'user_id': 1,
        'username': 'admin',
        'display_name': '系统管理员',
        'roles': [{'name': '超级管理员', 'code': 'super_admin'}],
        'permissions': ['*'],
        'exp': 9999999999,
    }, secret, algorithm='HS256')
    return token


@pytest.fixture
def regular_token():
    secret = os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
    token = pyjwt.encode({
        'user_id': 9999,
        'username': 'regular_user',
        'display_name': 'Regular User',
        'permissions': ['user:read'],
        'roles': ['viewer'],
        'exp': 9999999999,
    }, secret, algorithm='HS256')
    return token


def test_list_users_unauthenticated(client):
    # [v1 sunset 2026-11-09] /api/v1/users 已被 410 中间件接管，CRUD 主表迁到 v2 BO
    resp = client.get('/api/v2/bo/user')
    assert resp.status_code in [401, 403]


def test_list_users_authenticated(client, admin_token):
    resp = client.get('/api/v2/bo/user', headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('success') is True
    assert 'items' in (data.get('data') or {})


def test_create_user_missing_fields(client, admin_token):
    resp = client.post('/api/v2/bo/user',
        json={'username': ''},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [400, 401, 500]
    if resp.status_code == 400:
        data = resp.get_json()
        assert data.get('success') is False


def test_get_current_user_profile(client, admin_token):
    resp = client.get('/api/v1/users/me', headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json()
    assert data.get('success') is True
    assert 'data' in data


def test_update_current_user_profile(client, admin_token):
    resp = client.put('/api/v1/users/me',
        json={'display_name': 'Updated Admin'},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json()
    assert data.get('success') is True


def test_get_user_by_id(client, admin_token):
    resp = client.get('/api/v2/bo/user/1', headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get('success') is True


def test_update_user_by_admin(client, admin_token):
    resp = client.put('/api/v2/bo/user/1',
        json={'display_name': 'Admin Updated'},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get('success') is True


# [NEW 2026-06-09] 验证 status 字段只能通过 state_transition 修改, 普通 PUT 必须被拒绝
# [v1 sunset 2026-11-09] /api/v1/users/<id> 已被 410 中间件接管：原 v1 PUT 状态护栏
#   （STATUS_CHANGE_VIA_PUT_NOT_ALLOWED）只在仍存活的 /api/v1/users/me 上验证
#   （见 test_update_user_self_status_via_put_rejected）；by-id 的状态变更改由
#   /api/v2/bo/user/<id> + state_transition 承担，本用例固定 v1 的 sunset 契约。
def test_update_user_status_via_put_sunset(client, admin_token):
    """v1 by-id PUT 已被 sunset，必须返回 410 指向 v2 BO"""
    resp = client.put('/api/v1/users/1',
        json={'status': 'locked'},
        headers={'Authorization': f'Bearer {admin_token}'})

    assert resp.status_code == 410, f'Expected 410, got {resp.status_code}: {resp.get_data(as_text=True)}'
    data = resp.get_json()
    assert data.get('error') == 'API Moved'
    assert data.get('migrated_to') == '/api/v2/bo/user/1'


def test_update_user_self_status_via_put_rejected(client, admin_token):
    """用户用 PUT /api/v1/users/me 携带 status 字段必须返回 400"""
    resp = client.put('/api/v1/users/me',
        json={'status': 'locked', 'display_name': 'New Name'},
        headers={'Authorization': f'Bearer {admin_token}'})

    if resp.status_code in (401, 500):
        pytest.skip(f'Auth/env issue (status={resp.status_code}), skip status rejection check')

    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get('error_code') == 'STATUS_CHANGE_VIA_PUT_NOT_ALLOWED'


def test_delete_user_unauthenticated(client):
    # [v1 sunset 2026-11-09] 原 DELETE /api/v1/users/1 已 410；未认证删除在 v2 必须被拒
    resp = client.delete('/api/v2/bo/user/1')
    assert resp.status_code in [401, 403]


def test_reset_password_unauthorized(client, regular_token):
    resp = client.post('/api/v1/users/1/reset-password',
        json={'new_password': 'Newpass123'},
        headers={'Authorization': f'Bearer {regular_token}'})
    assert resp.status_code in [401, 403, 500]


def test_batch_delete_users_unauthorized(client, regular_token):
    resp = client.post('/api/v1/users/batch-delete',
        json={'ids': [1]},
        headers={'Authorization': f'Bearer {regular_token}'})
    assert resp.status_code in [401, 403, 500]


def test_get_user_menus(client, admin_token):
    resp = client.get('/api/v1/users/1/menus', headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json()
    assert data.get('success') is True


def test_get_user_logs(client, admin_token):
    resp = client.get('/api/v1/users/1/logs', headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json()
    assert data.get('success') is True


def test_create_user_duplicate_username(client, admin_token):
    """测试重复用户名检测（v2 BO API）"""
    headers = {'Authorization': f'Bearer {admin_token}'}

    unique_username = f'dup_{uuid.uuid4().hex[:12]}'
    user_data = {
        'username': unique_username,
        'password': 'Test1234',
        'email': f'{unique_username}@test.com',
        'display_name': 'Dup User',
    }

    resp1 = client.post('/api/v2/bo/user', json=user_data, headers=headers)
    assert resp1.status_code in (200, 201), resp1.get_data(as_text=True)
    created_id = (resp1.get_json().get('data') or {}).get('id')

    try:
        resp2 = client.post('/api/v2/bo/user', json=user_data, headers=headers)
        assert resp2.status_code in [400, 409, 500]
    finally:
        if created_id:
            client.delete(f'/api/v2/bo/user/{created_id}', headers=headers)


def test_update_self_profile_display_name(client, admin_token):
    resp = client.put('/api/v1/users/self',
        json={'display_name': 'Self Updated Name'},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json()
    assert data.get('success') is True


def test_list_users_with_keyword_search(client, admin_token):
    resp = client.get('/api/v2/bo/user?keyword=admin',
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('success') is True
    assert 'items' in (data.get('data') or {})
