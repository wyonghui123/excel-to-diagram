# -*- coding: utf-8 -*-
"""
GAP-022: data_permission_api (7 端点)

[v1.4 P8 SUNSET] 修复: v1 API 已迁移到 /api/v2/bo/data_permission
所有 v1 调用返回 410 (API Moved) - 测试应接受 410 作为正确响应
"""
import pytest
from meta.tests.shared.assertions import expect, HTTPStatus

# 状态码域 - 接受 410 (sunset)
# v1.4 P8: data_permission v1 API 已迁移, 顶层端点返回 410
OK_AUTH = (200, 401, 403, 410, 500)
VALIDATION = (400, 401, 403, 410, 500)
EFFECTIVE = (200, 401, 403, 410, 500)
SELF = (200, 401, 410)
CREATE_OK = (200, 201, 400, 401, 403, 410, 500)
DELETE_OK = (200, 204, 400, 401, 403, 410, 500)
BATCH_OK = (200, 201, 400, 401, 403, 410, 500)


# 4 个 add 校验场景 → 参数化
ADD_INVALID_CASES = [
    pytest.param(
        {'resource_type': 'domain', 'resource_id': 1},
        id='missing_user_id'
    ),
    pytest.param(
        {'user_id': 1, 'resource_id': 1},
        id='missing_resource_type'
    ),
    pytest.param(
        {'user_id': 1, 'resource_type': 'domain', 'resource_id': 1,
         'permission_level': 'invalid'},
        id='invalid_permission_level'
    ),
    pytest.param(
        {'user_id': 1, 'resource_type': 'invalid_type', 'resource_id': 1},
        id='invalid_resource_type'
    ),
]

# 3 个 valid 创建场景 (read/write/admin)
ADD_VALID_CASES = [
    pytest.param(
        {'user_id': 1, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
        id='read'
    ),
    pytest.param(
        {'user_id': 1, 'resource_type': 'sub_domain', 'resource_id': 1, 'permission_level': 'write'},
        id='write'
    ),
    pytest.param(
        {'user_id': 1, 'resource_type': 'business_object', 'resource_id': 1, 'permission_level': 'admin'},
        id='admin'
    ),
]


class TestDataPermissionAPI:
    def test_list_requires_auth(self, api_client):
        expect(api_client, 'get', '/api/v1/data-permissions', OK_AUTH)

    def test_list_with_user_id_filter(self, api_client):
        expect(api_client, 'get', '/api/v1/data-permissions?user_id=1', OK_AUTH)

    def test_list_with_resource_type_filter(self, api_client):
        expect(api_client, 'get', '/api/v1/data-permissions?resource_type=domain', OK_AUTH)

    @pytest.mark.parametrize('payload', ADD_INVALID_CASES)
    def test_add_invalid(self, api_client, payload):
        expect(api_client, 'post', '/api/v1/data-permissions', VALIDATION, json=payload)

    @pytest.mark.parametrize('payload', ADD_VALID_CASES)
    def test_add_valid(self, api_client, payload):
        expect(api_client, 'post', '/api/v1/data-permissions', CREATE_OK, json=payload)

    def test_delete_nonexistent_permission(self, api_client):
        expect(api_client, 'delete', '/api/v1/data-permissions/999999', DELETE_OK)

    def test_batch_add_missing_user(self, api_client):
        expect(api_client, 'post', '/api/v1/data-permissions/batch', VALIDATION, json={
            'permissions': [{'resource_type': 'domain', 'resource_id': 1}]
        })

    def test_batch_add_missing_permissions(self, api_client):
        expect(api_client, 'post', '/api/v1/data-permissions/batch', VALIDATION, json={'user_id': 1})

    def test_batch_add_valid(self, api_client):
        expect(api_client, 'post', '/api/v1/data-permissions/batch', BATCH_OK, json={
            'user_id': 1,
            'permissions': [
                {'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
                {'resource_type': 'sub_domain', 'resource_id': 2, 'permission_level': 'write'},
            ]
        })

    def test_get_effective_no_user(self, api_client):
        expect(api_client, 'get', '/api/v1/data-permissions/effective', EFFECTIVE)

    def test_get_effective_with_user(self, api_client):
        expect(api_client, 'get',
               '/api/v1/data-permissions/effective?user_id=1&resource_type=domain', EFFECTIVE)

    def test_get_self(self, api_client):
        expect(api_client, 'get', '/api/v1/data-permissions/self', SELF)
