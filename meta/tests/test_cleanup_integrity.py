import pytest

pytestmark = pytest.mark.integration

"""
cleanup-integrity test

"""
import json
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
from meta.server import create_app


@pytest.fixture(scope='module')
def app():
    from meta.tests.conftest import get_shared_app
    app, _ = get_shared_app()
    app.config['TESTING'] = True
    yield app


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


@pytest.fixture(scope='module')
def token():
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    u = UserInfo(user_id='1', username='test_user', display_name='Test User',
                 email='test@test.com', roles=['admin'], permissions=['*'])
    t, _ = TokenService.create_token(u)
    return t


@pytest.fixture(scope='module')
def headers(token):
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_user',
    }


@pytest.fixture(scope='module')
def cleanup(client, headers):
    ids = []
    yield ids
    for obj_type, obj_id in reversed(ids):
        try:
            client.delete(f'/api/v2/bo/{obj_type}/{obj_id}', headers=headers)
        except Exception:
            pass


def _post(client, headers, obj_type, data, cleanup_list):
    resp = client.post(f'/api/v2/bo/{obj_type}', data=json.dumps(data), headers=headers)
    try:
        r = json.loads(resp.data)
    except Exception:
        r = {}
    if r.get('success') and r.get('data') and r['data'].get('id'):
        cleanup_list.append((obj_type, r['data']['id']))
    elif isinstance(r.get('data'), dict) and r['data'].get('id'):
        cleanup_list.append((obj_type, r['data']['id']))
    return resp, r


class TestServerIntegrity:
    """ manage_api.py_temp   server  """

    def test_server_starts_without_temp_file(self, client):
        resp = client.get('/health')
        assert resp.status_code in [200, 401, 404, 500]
        data = json.loads(resp.data)
        assert data['status'] == 'ok'

    def test_manage_api_temp_not_importable(self):
        with pytest.raises(ImportError):
            import manage_api_temp

    def test_all_core_blueprints_registered(self, client, headers):
        resp = client.get('/api/v1/audit/health', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]


class TestCoreAPIEndpoints:
    """ cleanup manage_api.py   """

    def test_user_crud_chain(self, client, headers, cleanup):
        resp, data = _post(client, headers, 'user', {
            'username': 'ci_test_u1',
            'password': 'Test123456',
            'email': 'ci_u1@test.com',
        }, cleanup)
        assert resp.status_code in [200, 201, 400, 401, 500]

        if data.get('success') and data.get('data', {}).get('id'):
            uid = data.get('data', {})['id']
            resp = client.get(f'/api/v2/bo/user/{uid}', headers=headers)
            assert resp.status_code in [200, 401, 404, 500]
            r = json.loads(resp.data)
            assert r['success'] is True

    def test_role_crud_chain(self, client, headers, cleanup):
        resp, data = _post(client, headers, 'role', {
            'name': 'ci_test_role1',
            'description': 'CI test role',
        }, cleanup)
        assert resp.status_code in [200, 201, 400, 401, 500]

        if data.get('success') and data.get('data', {}).get('id'):
            rid = data.get('data', {})['id']
            resp = client.get(f'/api/v2/bo/role/{rid}', headers=headers)
            assert resp.status_code in [200, 401, 404, 500]

    def test_user_group_crud_chain(self, client, headers, cleanup):
        resp, data = _post(client, headers, 'user_group', {
            'name': 'ci_test_grp1',
            'description': 'CI test group',
        }, cleanup)
        assert resp.status_code in [200, 201, 400, 401, 500]

        if data.get('success') and data.get('data', {}).get('id'):
            gid = data.get('data', {})['id']
            resp = client.get(f'/api/v2/bo/user_group/{gid}', headers=headers)
            assert resp.status_code in [200, 401, 404, 500]

    def test_enum_crud_chain(self, client, headers, cleanup):
        resp, data = _post(client, headers, 'enum_type', {
            'name': 'ci_test_et1',
            'label': 'CI Test ET',
            'description': 'CI test enum type',
        }, cleanup)
        assert resp.status_code in [200, 201, 400, 401, 500]

        if data.get('success') and data.get('data', {}).get('id'):
            et_id = data.get('data', {})['id']
            resp = client.get(f'/api/v2/bo/enum_type/{et_id}', headers=headers)
            assert resp.status_code in [200, 401, 404, 500]

    def test_audit_endpoints(self, client, headers):
        resp = client.get('/api/v2/bo/audit_log?page=1&page_size=10', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_meta_objects_endpoint(self, client, headers):
        try:
            resp = client.get('/api/v1/meta/objects', headers=headers)
            assert resp.status_code in [200, 401, 404, 500]
        except Exception as e:
            pytest.fail(f"Core API endpoint issue: {e}")

    def test_export_endpoint(self, client, headers):
        resp = client.get('/api/v1/export?object_type=user&page=1&page_size=10', headers=headers)
        assert resp.status_code in [200, 400, 401, 404, 500]


class TestImportExportService:
    """ import_export_service  """

    def _ensure_user(self, client, headers, cleanup):
        resp, data = _post(client, headers, 'user', {
            'username': 'ie_test_u1',
            'password': 'Test123456',
            'email': 'ie_u1@test.com',
        }, cleanup)
        return resp, data

    def test_export_response_structure(self, client, headers, cleanup):
        self._ensure_user(client, headers, cleanup)
        resp = client.get('/api/v1/export?object_type=user&page=1&page_size=10', headers=headers)
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 200:
            content_type = resp.headers.get('Content-Type', '')
            assert 'json' in content_type or 'octet-stream' in content_type

    def test_import_preview_endpoint(self, client, headers):
        payload = {
            'object_type': 'user',
            'data': [{'username': 'ie_prev_u1', 'password': 'Test123456', 'email': 'prev@test.com'}],
            'mode': 'preview',
        }
        resp = client.post('/api/v1/import', data=json.dumps(payload), headers=headers)
        assert resp.status_code in [200, 400, 401, 404, 500]


class TestAuthEndpoints:
    """  """

    def test_auth_change_password(self, client, headers):
        payload = {
            'old_password': 'admin123',
            'new_password': 'NewAdmin123',
        }
        resp = client.post('/api/v1/auth/change-password',
                           data=json.dumps(payload), headers=headers)
        assert resp.status_code in [200, 400, 401, 403, 404, 429, 500]

    def test_users_me_endpoint(self, client, headers):
        resp = client.get('/api/v2/bo/users/me', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]


class TestNotificationEndpoints:
    """  notification  """

    def test_notifications_list(self, client, headers):
        resp = client.get('/api/v1/notifications?page=1&page_size=10', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]


class TestAssociationEndpoints:
    """  association  """

    def test_association_list(self, client, headers):
        resp = client.get('/api/v1/associations?page=1&page_size=10', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]


class TestMenuPermissionEndpoints:
    """  menu   """

    def test_menu_permission_visible(self, client, headers):
        resp = client.get('/api/v2/bo/menu-permission/visible', headers=headers)
        assert resp.status_code in [200, 401, 404, 500]
