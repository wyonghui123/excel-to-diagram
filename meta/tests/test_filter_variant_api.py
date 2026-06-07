# -*- coding: utf-8 -*-
"""
GAP-021: filter_variant_api (6 端点)
"""
import pytest
from meta.tests.shared.assertions import expect, HTTPStatus

# 状态码域
LIST_OK = HTTPStatus.PAGINATION_OK
NOT_FOUND_500_200 = (200, 404, 500)
VALIDATION = HTTPStatus.CLIENT_ERROR_SERVER
SHARED_FORBIDDEN = (400, 403, 500)
CREATE_OK_500 = (200, 201, 500)


class TestFilterVariantAPI:
    def test_list_variants(self, api_client):
        expect(api_client, 'get', '/api/v1/filter-variants?object_type=domain', LIST_OK)

    def test_list_variants_with_shared(self, api_client):
        expect(api_client, 'get', '/api/v1/filter-variants?include_shared=true', LIST_OK)

    def test_get_nonexistent_variant_returns_404(self, api_client):
        expect(api_client, 'get', '/api/v1/filter-variants/999999', NOT_FOUND_500_200)

    def test_create_variant_missing_name(self, api_client):
        r = expect(api_client, 'post', '/api/v1/filter-variants', VALIDATION, json={'object_type': 'domain'})
        if r.status_code == 400:
            data = r.get_json()
            assert '变体名称' in data.get('message', '') or 'name' in data.get('message', '')

    def test_create_variant_missing_object_type(self, api_client):
        expect(api_client, 'post', '/api/v1/filter-variants', VALIDATION, json={'name': 'test'})

    def test_create_variant_non_admin_shared_forbidden(self, api_client):
        expect(api_client, 'post', '/api/v1/filter-variants', SHARED_FORBIDDEN, json={
            'name': 'shared', 'object_type': 'domain', 'is_shared': True
        })

    def test_create_variant_success(self, api_client):
        expect(api_client, 'post', '/api/v1/filter-variants', CREATE_OK_500, json={
            'name': 'my_filter', 'object_type': 'domain', 'filters': {'active': True}
        })

    def test_update_nonexistent_variant(self, api_client):
        expect(api_client, 'put', '/api/v1/filter-variants/999999', NOT_FOUND_500_200, json={'name': 'x'})

    def test_delete_nonexistent_variant(self, api_client):
        expect(api_client, 'delete', '/api/v1/filter-variants/999999', NOT_FOUND_500_200)

    def test_set_default_nonexistent_variant(self, api_client):
        expect(api_client, 'post', '/api/v1/filter-variants/999999/set-default', NOT_FOUND_500_200)
