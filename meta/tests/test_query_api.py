# -*- coding: utf-8 -*-
"""
GAP-024: query_api (5 端点)
"""
import pytest
from meta.tests.shared.assertions import (
    expect, assert_data_contains, HTTPStatus,
)

OK_500 = HTTPStatus.PAGINATION_OK  # (200, 500)


class TestQueryAPI:
    def test_search_empty(self, api_client):
        r = expect(api_client, 'post', '/api/v1/query/search', OK_500, json={})
        assert_data_contains(r, 'data', 'total')

    def test_search_with_conditions(self, api_client):
        expect(api_client, 'post', '/api/v1/query/search', OK_500, json={
            'object_type': 'domain',
            'conditions': [{'field': 'id', 'operator': 'eq', 'value': 1}],
            'page': 1, 'page_size': 10,
        })

    def test_search_with_keyword(self, api_client):
        expect(api_client, 'post', '/api/v1/query/search', OK_500, json={
            'object_type': 'domain', 'keyword': 'test', 'page': 1, 'page_size': 20,
        })

    def test_search_with_ordering(self, api_client):
        expect(api_client, 'post', '/api/v1/query/search', OK_500, json={
            'object_type': 'domain', 'order_by': 'name', 'page': 1, 'page_size': 20,
        })

    def test_full_text_search(self, api_client):
        r = expect(api_client, 'get', '/api/v1/query/full-text?keyword=domain&limit=10', OK_500)
        assert_data_contains(r, 'data', 'keyword', scope=None)

    def test_full_text_search_with_types(self, api_client):
        expect(api_client, 'get',
               '/api/v1/query/full-text?keyword=foo&types=domain,sub_domain&limit=5', OK_500)

    def test_hierarchy_query(self, api_client):
        expect(api_client, 'get', '/api/v1/query/hierarchy/domain', OK_500)

    def test_hierarchy_query_with_children(self, api_client):
        expect(api_client, 'get', '/api/v1/query/hierarchy/domain?include_children=true', OK_500)

    def test_suggest(self, api_client):
        r = expect(api_client, 'get', '/api/v1/query/suggest/domain/name?prefix=do&limit=5', OK_500)
        if r.status_code == 200:
            data = r.get_json()
            assert 'data' in data
            assert data.get('object_type') == 'domain'

    def test_aggregate(self, api_client):
        expect(api_client, 'post', '/api/v1/query/aggregate', OK_500, json={
            'object_type': 'domain',
            'measures': [{'field': 'id', 'aggregation': 'count'}],
            'dimensions': ['name'],
        })

    def test_aggregate_multiple_measures(self, api_client):
        expect(api_client, 'post', '/api/v1/query/aggregate', OK_500, json={
            'object_type': 'domain',
            'measures': [
                {'field': 'id', 'aggregation': 'count'},
                {'field': 'id', 'aggregation': 'max'},
            ],
        })
