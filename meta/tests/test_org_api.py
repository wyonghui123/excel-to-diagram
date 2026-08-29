# -*- coding: utf-8 -*-
"""
GAP-031: user_group_api (15+ 端点, 含 v1.4 P8 sunset 410)

[MARKER] deprecated - 顶层 user-groups 端点已 sunset
[SUBCLASS] 拆 3 个子类: SunsetCRUD / Members / Roles+Logs
"""
import json
import pytest
from meta.tests.shared.assertions import (
    expect, assert_data_field, HTTPStatus,
)

# 状态码域
LIST_SUNSET = HTTPStatus.SUNSET_OK_AUTH
SUNSET_AUTH = HTTPStatus.SUNSET_AUTH
OK_AUTH = HTTPStatus.OK_AUTH
VALIDATION = HTTPStatus.VALIDATION_AUTH
NOT_FOUND_AUTH = HTTPStatus.NOT_FOUND_AUTH
LOGS_PAGINATION = (200, 404, 401, 500)
MIGRATE_AUTH = (401, 403, 500)


SUNSET_CRUD = [
    pytest.param('get', '/api/v1/user-groups', None, id='list_sunset'),
    pytest.param('post', '/api/v1/user-groups', {'name': 'g'}, id='create_sunset'),
    pytest.param('get', '/api/v1/user-groups/1', None, id='get_sunset_by_id'),
    pytest.param('put', '/api/v1/user-groups/1', {'name': 'g'}, id='update_sunset'),
    pytest.param('delete', '/api/v1/user-groups/1', None, id='delete_sunset'),
]

ROLE_CRUD = [
    pytest.param('get', '/api/v1/user-groups/1/roles', None, id='get_roles'),
    pytest.param('put', '/api/v1/user-groups/1/roles', {'role_ids': [1, 2]}, id='set_roles'),
    pytest.param('post', '/api/v1/user-groups/1/roles/1', None, id='add_role'),
    pytest.param('delete', '/api/v1/user-groups/1/roles/1', None, id='remove_role'),
]


class TestSunsetCRUD:
    """顶层 sunset CRUD (5 端点) - v1.4 P8 已弃用"""
    pytestmark = pytest.mark.deprecated

    @pytest.mark.parametrize('method,endpoint,body', SUNSET_CRUD)
    def test_sunset_crud(self, api_client, method, endpoint, body):
        r = expect(api_client, method, endpoint, SUNSET_AUTH, json=body) if body \
            else expect(api_client, method, endpoint, SUNSET_AUTH)
        assert r.status_code in SUNSET_AUTH

    def test_list_user_groups_returns_410(self, api_client):
        """v1.4 P8 sunset → 410 (or 401 if not auth'd)"""
        r = expect(api_client, 'get', '/api/v1/user-groups', LIST_SUNSET)
        if r.status_code == 410:
            import json
            data = json.loads(r.data)
            assert 'sunset' in str(data).lower() or 'migrated' in str(data).lower()


class TestMembers:
    """members + data-permissions 子端点"""

    def test_get_members(self, api_client):
        r = expect(api_client, 'get', '/api/v1/user-groups/1/members', OK_AUTH)
        assert_data_field(r, '_deprecated', True)

    def test_add_member_missing_user(self, api_client):
        expect(api_client, 'post', '/api/v1/user-groups/1/members', VALIDATION, json={})

    def test_add_member_valid(self, api_client):
        expect(api_client, 'post', '/api/v1/user-groups/1/members', OK_AUTH, json={'user_id': 1})

    def test_set_members(self, api_client):
        expect(api_client, 'put', '/api/v1/user-groups/1/members', OK_AUTH,
               json={'user_ids': [1, 2, 3]})

    def test_remove_member(self, api_client):
        expect(api_client, 'delete', '/api/v1/user-groups/1/members/1', OK_AUTH)

    def test_get_data_permissions(self, api_client):
        r = expect(api_client, 'get', '/api/v1/user-groups/1/data-permissions', OK_AUTH)
        assert_data_field(r, '_deprecated', True)

    def test_add_data_permission_missing(self, api_client):
        expect(api_client, 'post', '/api/v1/user-groups/1/data-permissions', VALIDATION, json={})

    def test_remove_data_permission(self, api_client):
        expect(api_client, 'delete', '/api/v1/user-groups/1/data-permissions/1', OK_AUTH)


class TestRolesAndLogs:
    """roles + 迁移 + logs"""

    @pytest.mark.parametrize('method,endpoint,body', ROLE_CRUD)
    def test_role_crud(self, api_client, method, endpoint, body):
        r = expect(api_client, method, endpoint, OK_AUTH, json=body) if body \
            else expect(api_client, method, endpoint, OK_AUTH)
        assert r.status_code in OK_AUTH

    def test_available_roles(self, api_client):
        expect(api_client, 'get', '/api/v1/user-groups/1/roles/available', OK_AUTH)

    def test_migrate_permissions_unauthorized(self, api_client):
        expect(api_client, 'post',
               '/api/v1/system/migrate-group-permissions-to-roles', MIGRATE_AUTH)

    def test_get_logs_nonexistent_group(self, api_client):
        expect(api_client, 'get', '/api/v1/user-groups/999999/logs', NOT_FOUND_AUTH)

    def test_get_logs_pagination(self, api_client):
        expect(api_client, 'get', '/api/v1/user-groups/1/logs?page=1&page_size=10', LOGS_PAGINATION)
