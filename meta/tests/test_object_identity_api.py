# -*- coding: utf-8 -*-
"""
GAP-023: object_identity_api (4 端点)
"""
import pytest
from meta.tests.shared.assertions import expect, HTTPStatus

# 状态码域 (复用 HTTPStatus)
VALIDATION_500 = HTTPStatus.CLIENT_ERROR_SERVER
GET_OK = HTTPStatus.PAGINATION_OK
BATCH_400 = HTTPStatus.CLIENT_ERROR_SERVER


class TestObjectIdentityAPI:
    def test_get_identity_missing_type(self, api_client):
        expect(api_client, 'get', '/api/v1/identity?object_id=1', VALIDATION_500)

    def test_get_identity_missing_id(self, api_client):
        expect(api_client, 'get', '/api/v1/identity?object_type=domain', VALIDATION_500)

    def test_get_identity_invalid_id(self, api_client):
        expect(api_client, 'get', '/api/v1/identity?object_type=domain&object_id=abc', VALIDATION_500)

    def test_get_identity_valid(self, api_client):
        expect(api_client, 'get', '/api/v1/identity?object_type=domain&object_id=1', GET_OK)

    def test_get_identity_with_format(self, api_client):
        expect(api_client, 'get', '/api/v1/identity?object_type=domain&object_id=1&format=short', GET_OK)

    def test_get_identity_with_technical(self, api_client):
        expect(api_client, 'get',
               '/api/v1/identity?object_type=domain&object_id=1&include_technical=true', GET_OK)

    def test_get_formatted_missing_type(self, api_client):
        expect(api_client, 'get', '/api/v1/identity/formatted?object_id=1', VALIDATION_500)

    def test_get_formatted_valid(self, api_client):
        expect(api_client, 'get', '/api/v1/identity/formatted?object_type=domain&object_id=1', GET_OK)

    def test_batch_no_requests(self, api_client):
        expect(api_client, 'post', '/api/v1/identity/batch', BATCH_400, json={})

    def test_batch_valid(self, api_client):
        expect(api_client, 'post', '/api/v1/identity/batch', GET_OK, json={
            'requests': [
                {'object_type': 'domain', 'object_id': 1},
                {'object_type': 'domain', 'object_id': 2},
            ]
        })

    def test_batch_invalid_request_type(self, api_client):
        expect(api_client, 'post', '/api/v1/identity/batch', BATCH_400, json={
            'requests': 'not_a_list'
        })

    def test_batch_skips_invalid_items(self, api_client):
        expect(api_client, 'post', '/api/v1/identity/batch', BATCH_400, json={
            'requests': [
                'invalid',
                {'object_type': 'domain'},
                {'object_type': 'domain', 'object_id': 'abc'},
            ]
        })

    def test_clear_cache(self, api_client):
        expect(api_client, 'post', '/api/v1/identity/cache/clear', GET_OK)
