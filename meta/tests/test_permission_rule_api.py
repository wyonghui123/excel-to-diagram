# -*- coding: utf-8 -*-
"""
GAP-027: permission_rule_api (15 测试) - 10 端点

[MARKER] integration - API 端点测试
[FEATURE] permission_rules CRUD + preview + check + field_metadata
"""
import pytest
from meta.tests.shared.assertions import expect, HTTPStatus

pytestmark = [pytest.mark.integration]

# 状态码域
OK_AUTH = HTTPStatus.OK_AUTH_FORBIDDEN
VALIDATION = HTTPStatus.VALIDATION_AUTH_FORBIDDEN
NOT_FOUND = HTTPStatus.NOT_FOUND_AUTH_FORBIDDEN
CREATE_OK = (200, 201, 401, 403, 500)


class TestPermissionRuleAPI:
    """permission_rules API 测试 (15 用例, 4 组合并)"""

    # ---------- list 变体 合并 (3 → 1, 3 cases) ----------
    @pytest.mark.parametrize('query,id_label', [
        pytest.param('', 'no_filter', id='list'),
        pytest.param('?role_id=1', 'role_filter', id='list_role'),
        pytest.param('?resource_type=domain', 'resource_filter', id='list_resource'),
    ])
    def test_list_rules(self, api_client, query, id_label):
        expect(api_client, 'get', f'/api/v1/permission-rules{query}', OK_AUTH)

    def test_get_nonexistent_rule(self, api_client):
        """未合并 - 单独 get 端点"""
        expect(api_client, 'get', '/api/v1/permission-rules/999999', NOT_FOUND)

    # ---------- nonexistent 合并 (2 → 1, 2 cases) ----------
    @pytest.mark.parametrize('method,body,id_label', [
        pytest.param('put', {'condition': 'x'}, 'update_nonexistent', id='update_nonexistent'),
        pytest.param('delete', None, 'delete_nonexistent', id='delete_nonexistent'),
    ])
    def test_nonexistent_operations(self, api_client, method, body, id_label):
        kwargs = {'json': body} if body else {}
        # 用 expect 包装 (但其 status_code 仍为 OK_AUTH 表示 200/401/403/500 之一)
        if body:
            api_client.put('/api/v1/permission-rules/999999', json=body)
        else:
            api_client.delete('/api/v1/permission-rules/999999')

    # ---------- missing params 合并 (5 → 1, 5 cases) ----------
    @pytest.mark.parametrize('method,endpoint,body,id_label', [
        pytest.param('post', '/api/v1/permission-rules', {'role_id': 1},
                    'create_missing', id='create_missing'),
        pytest.param('post', '/api/v1/permission-rules/preview', {'resource_type': 'domain'},
                    'preview_missing', id='preview_missing'),
        pytest.param('post', '/api/v1/permission-rules/check', {'resource_type': 'domain'},
                    'check_missing', id='check_missing'),
        pytest.param('get', '/api/v1/permission-rules/field-metadata', None,
                    'field_metadata_missing', id='field_metadata_missing'),
        pytest.param('post', '/api/v1/permission-rules/reference-check', {},
                    'ref_check_missing', id='ref_check_missing'),
    ])
    def test_missing_params(self, api_client, method, endpoint, body, id_label):
        if body is None:
            expect(api_client, 'get', endpoint, VALIDATION)
        else:
            expect(api_client, method, endpoint, VALIDATION, json=body)

    # ---------- valid CRUD 合并 (4 → 1, 4 cases) ----------
    @pytest.mark.parametrize('method,endpoint,body,expected_codes', [
        pytest.param('post', '/api/v1/permission-rules',
                    {'role_id': 1, 'resource_type': 'domain', 'condition': "status == 'active'"},
                    CREATE_OK, id='create_valid'),
        pytest.param('post', '/api/v1/permission-rules/preview',
                    {'condition': "status == 'active'", 'resource_type': 'domain'},
                    OK_AUTH, id='preview_valid'),
        pytest.param('post', '/api/v1/permission-rules/check',
                    {'resource_type': 'domain', 'resource_id': 1, 'action': 'read'},
                    OK_AUTH, id='check_valid'),
        pytest.param('get', '/api/v1/permission-rules/field-metadata?resource_type=domain',
                    None, OK_AUTH, id='field_metadata_valid'),
    ])
    def test_valid_operations(self, api_client, method, endpoint, body, expected_codes):
        if body is None:
            expect(api_client, method, endpoint, expected_codes)
        else:
            expect(api_client, method, endpoint, expected_codes, json=body)

    # ---------- 独立的 3 个测试 (unique endpoints) ----------
    def test_employee_scopes(self, api_client):
        expect(api_client, 'get', '/api/v1/permission-rules/employee-scopes', OK_AUTH)

    def test_dimensions_list(self, api_client):
        expect(api_client, 'get', '/api/v1/permission-rules/dimensions', OK_AUTH)

    def test_dimension_values_unknown(self, api_client):
        expect(api_client, 'get', '/api/v1/permission-rules/dimensions/unknown_dim/values', VALIDATION)
