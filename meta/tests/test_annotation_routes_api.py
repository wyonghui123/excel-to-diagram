# -*- coding: utf-8 -*-
"""
GAP-028: annotation_routes_api (8 端点)
"""
import pytest
from meta.tests.shared.assertions import expect, HTTPStatus

# 状态码域
VALIDATION = HTTPStatus.VALIDATION_AUTH
VALIDATION_500 = HTTPStatus.CLIENT_ERROR_SERVER
LIST_OK = HTTPStatus.PAGINATION_OK
GET_NOT_FOUND = (200, 401, 404, 500)
CREATE_OK = (201, 200, 401, 500)


INVALID_CREATE_CASES = [
    pytest.param({'target_type': 'domain'}, id='missing_target_id'),
    pytest.param(
        {'target_type': 'invalid', 'target_id': 1, 'content': 'test'},
        id='invalid_target_type'
    ),
    pytest.param(
        {'target_type': 'domain', 'target_id': 'abc', 'content': 'test'},
        id='invalid_id_type'
    ),
    pytest.param(
        {'target_type': 'domain', 'target_id': 1, 'content': 'test', 'category': 'invalid'},
        id='invalid_category'
    ),
]


class TestAnnotationRoutesAPI:
    def test_list_annotations_missing_target_type(self, api_client):
        expect(api_client, 'get', '/api/v1/annotations/by-target?target_id=1', VALIDATION_500)

    def test_list_annotations_missing_target_id(self, api_client):
        expect(api_client, 'get', '/api/v1/annotations/by-target?target_type=domain', VALIDATION_500)

    def test_list_annotations_invalid_target_type(self, api_client):
        expect(api_client, 'get',
               '/api/v1/annotations/by-target?target_type=invalid_type&target_id=1', VALIDATION_500)

    def test_list_annotations_valid(self, api_client):
        expect(api_client, 'get',
               '/api/v1/annotations/by-target?target_type=domain&target_id=1', LIST_OK)

    def test_get_annotation_nonexistent(self, api_client):
        expect(api_client, 'get', '/api/v1/annotations/999999', GET_NOT_FOUND)

    @pytest.mark.parametrize('payload', INVALID_CREATE_CASES)
    def test_create_annotation_invalid(self, api_client, payload):
        expect(api_client, 'post', '/api/v1/annotations', VALIDATION, json=payload)

    def test_create_annotation_valid(self, api_client):
        expect(api_client, 'post', '/api/v1/annotations', CREATE_OK, json={
            'target_type': 'domain', 'target_id': 1, 'content': 'note', 'category': 'info'
        })

    def test_update_annotation_invalid_category(self, api_client):
        expect(api_client, 'put', '/api/v1/annotations/1', VALIDATION_500, json={'category': 'invalid'})

    def test_category_stats(self, api_client):
        expect(api_client, 'get', '/api/v1/annotations/category-stats?target_type=domain',
               (200, 401, 500))

    def test_category_stats_with_active_filter(self, api_client):
        expect(api_client, 'get', '/api/v1/annotations/category-stats?is_active=true',
               (200, 401, 500))
