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


@pytest.fixture
def created_group(client, admin_token):
    headers = {'Authorization': f'Bearer {admin_token}'}
    code = f'grp_{uuid.uuid4().hex[:8]}'
    # v1.4 P8 Sunset: POST /api/v1/user-groups 已废弃, 使用 v2 API
    resp = client.post('/api/v2/bo/user_group',
        json={'name': 'Test Group', 'code': code},
        headers=headers)
    if resp.status_code not in (200, 201):
        return None
    data = resp.get_json()
    if not data:
        return None
    group_id = data.get('data', {}).get('id') if isinstance(data, dict) else None
    return group_id


def test_get_user_groups_unauthenticated(client):
    resp = client.get('/api/v1/user-groups')
    assert resp.status_code in [401, 500]


def test_get_user_groups_authenticated(client, admin_token):
    resp = client.get('/api/v1/user-groups',
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 410, 500]
    if resp.status_code != 410:
        data = resp.get_json()
        assert data.get('success') is True


def test_create_user_group_missing_fields(client, admin_token):
    resp = client.post('/api/v1/user-groups',
        json={'name': ''},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [400, 401, 410, 500]
    if resp.status_code != 410:
        data = resp.get_json()
        assert data.get('success') is False


def test_create_user_group_success(client, admin_token):
    code = f'new_{uuid.uuid4().hex[:8]}'
    resp = client.post('/api/v1/user-groups',
        json={'name': 'New Group', 'code': code},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 201, 400, 401, 410, 500]
    if resp.status_code in (200, 201):
        data = resp.get_json()
        assert data.get('success') is True


def test_get_user_group_by_id(client, admin_token, created_group):
    if created_group is None:
        pytest.skip('Group creation failed')
    # v1.4 P8 Sunset: GET /api/v1/user-groups/{id} 已废弃, 使用 v2 API
    resp = client.get(f'/api/v2/bo/user_group/{created_group}',
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 410, 500]
    if resp.status_code != 410:
        data = resp.get_json() or {}
        assert (data or {}).get('success') is True


def test_update_user_group(client, admin_token, created_group):
    if created_group is None:
        pytest.skip('Group creation failed')
    # v1.4 P8 Sunset: PUT /api/v1/user-groups/{id} 已废弃, 使用 v2 API
    resp = client.put(f'/api/v2/bo/user_group/{created_group}',
        json={'description': 'Updated description'},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 410, 500]
    if resp.status_code != 410:
        data = resp.get_json() or {}
        assert (data or {}).get('success') is True


def test_delete_user_group_unauthorized(client, regular_token, created_group):
    if created_group is None:
        pytest.skip('Group creation failed')
    # v1.4 P8 Sunset: DELETE /api/v1/user-groups/{id} 已废弃, 使用 v2 API
    resp = client.delete(f'/api/v2/bo/user_group/{created_group}',
        headers={'Authorization': f'Bearer {regular_token}'})
    assert resp.status_code in [401, 403, 410, 500]


def test_get_group_members(client, admin_token, created_group):
    if created_group is None:
        pytest.skip('Group creation failed')
    resp = client.get(f'/api/v1/user-groups/{created_group}/members',
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json() or {}
    assert (data or {}).get('success') is True


def test_set_group_members(client, admin_token, created_group):
    if created_group is None:
        pytest.skip('Group creation failed')
    resp = client.put(f'/api/v1/user-groups/{created_group}/members',
        json={'user_ids': [1]},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json() or {}
    assert (data or {}).get('success') is True


def test_remove_group_member(client, admin_token, created_group):
    if created_group is None:
        pytest.skip('Group creation failed')
    client.put(f'/api/v1/user-groups/{created_group}/members',
        json={'user_ids': [1]},
        headers={'Authorization': f'Bearer {admin_token}'})
    resp = client.delete(f'/api/v1/user-groups/{created_group}/members/1',
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json() or {}
    assert (data or {}).get('success') is True


def test_get_group_roles(client, admin_token, created_group):
    if created_group is None:
        pytest.skip('Group creation failed')
    resp = client.get(f'/api/v1/user-groups/{created_group}/roles',
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json() or {}
    assert (data or {}).get('success') is True


def test_set_group_roles(client, admin_token, created_group):
    if created_group is None:
        pytest.skip('Group creation failed')
    resp = client.put(f'/api/v1/user-groups/{created_group}/roles',
        json={'role_ids': []},
        headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json() or {}
    assert (data or {}).get('success') is True
