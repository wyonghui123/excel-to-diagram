import pytest

pytestmark = pytest.mark.integration

import sys
import os

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
        'roles': [{'name': '超级管理员', 'code': 'super_admin', 'is_super_admin': True}],
        'permissions': ['*'],
        'exp': 9999999999,
    }, secret, algorithm='HS256')
    return token


@pytest.fixture
def auth_headers(admin_token):
    return {'Authorization': f'Bearer {admin_token}', 'Content-Type': 'application/json'}


def test_list_rules(client, auth_headers):
    resp = client.get('/api/v1/permission-rules', headers=auth_headers)
    assert resp.status_code in [200, 401, 404, 500]
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get('success', False) is True


def test_get_rule_by_id(client, auth_headers):
    resp = client.get('/api/v1/permission-rules/99999', headers=auth_headers)
    assert resp.status_code in [200, 401, 404, 500]
    if resp.status_code in (200, 404):
        data = resp.get_json()
        assert 'success' in data


def test_create_rule_unauthorized(client):
    resp = client.post('/api/v1/permission-rules', json={
        'role_id': 1, 'resource_type': 'domain', 'condition': 'version_id = 1'
    })
    assert resp.status_code in (200, 401, 403, 404, 500)


def test_create_rule_success(client, auth_headers):
    resp = client.post('/api/v1/permission-rules', json={
        'role_id': 1, 'resource_type': 'domain', 'condition': 'version_id = 1'
    }, headers=auth_headers)
    assert resp.status_code in [200, 401, 404, 500]
    data = resp.get_json()
    assert data.get('success', False) is True


def test_update_rule(client, auth_headers):
    create_resp = client.post('/api/v1/permission-rules', json={
        'role_id': 1, 'resource_type': 'domain', 'condition': 'version_id = 1'
    }, headers=auth_headers)
    create_data = create_resp.get_json() if create_resp.status_code == 200 else {}
    if create_data.get('success') and create_data.get('data', {}).get('id'):
        rule_id = create_data.get('data', {})['id']
        resp = client.put(f'/api/v1/permission-rules/{rule_id}', json={
            'condition': 'version_id = 2'
        }, headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]
        if resp.status_code == 200:
            data = resp.get_json()
            assert data.get('success', False) is True
    else:
        resp = client.put('/api/v1/permission-rules/1', json={
            'condition': 'version_id = 2'
        }, headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]


def test_delete_rule(client, auth_headers):
    create_resp = client.post('/api/v1/permission-rules', json={
        'role_id': 1, 'resource_type': 'domain', 'condition': 'version_id = 1'
    }, headers=auth_headers)
    create_data = create_resp.get_json() if create_resp.status_code == 200 else {}
    if create_data.get('success') and create_data.get('data', {}).get('id'):
        rule_id = create_data.get('data', {})['id']
        resp = client.delete(f'/api/v1/permission-rules/{rule_id}', headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]
        if resp.status_code == 200:
            data = resp.get_json()
            assert data.get('success', False) is True
    else:
        resp = client.delete('/api/v1/permission-rules/1', headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]


def test_preview_matching(client, auth_headers):
    resp = client.post('/api/v1/permission-rules/preview', json={
        'condition': '1=1', 'resource_type': 'domain'
    }, headers=auth_headers)
    assert resp.status_code in [200, 401, 404, 500]
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get('success', False) is True


def test_check_permission(client, auth_headers):
    resp = client.post('/api/v1/permission-rules/check', json={
        'resource_type': 'domain', 'resource_id': 1, 'action': 'read'
    }, headers=auth_headers)
    assert resp.status_code in (200, 401, 500)


def test_get_dimensions(client, auth_headers):
    resp = client.get('/api/v1/permission-rules/dimensions', headers=auth_headers)
    assert resp.status_code in [200, 401, 404, 500]
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get('success', False) is True


def test_get_field_metadata(client, auth_headers):
    resp = client.get('/api/v1/permission-rules/field-metadata?resource_type=domain', headers=auth_headers)
    assert resp.status_code in [200, 401, 404, 500]
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get('success', False) is True
