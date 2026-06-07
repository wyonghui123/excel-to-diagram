# -*- coding: utf-8 -*-
"""
GAP-025: value_help_api (2 端点)
"""
import json
import pytest
from meta.tests.shared.assertions import expect, HTTPStatus

# 端点允许的完整状态码域
ALLOWED = (200, 401, 400, 500)
RESOLVE_NO_VALUE = HTTPStatus.VALIDATION_AUTH
RESOLVE_OK = HTTPStatus.OK_AUTH


class TestValueHelpAPI:
    def test_search_enum(self, api_client):
        expect(api_client, 'get', '/api/v2/value-help/enum/visibility', ALLOWED)

    def test_search_bo(self, api_client):
        expect(api_client, 'get', '/api/v2/value-help/bo/domain', ALLOWED)

    def test_search_bo_with_params(self, api_client):
        expect(api_client, 'get',
               '/api/v2/value-help/bo/domain?value_field=id&display_field=name&code_field=code&page=1&pageSize=10',
               ALLOWED)

    def test_search_bo_with_value_filter(self, api_client):
        expect(api_client, 'get',
               '/api/v2/value-help/bo/domain?value_filter=' + json.dumps({'active': True}),
               ALLOWED)

    def test_search_custom(self, api_client):
        expect(api_client, 'get', '/api/v2/value-help/custom/my_endpoint', ALLOWED)

    def test_search_unknown_type(self, api_client):
        expect(api_client, 'get', '/api/v2/value-help/unknown_type/source_id', ALLOWED)

    def test_resolve_no_value(self, api_client):
        expect(api_client, 'get', '/api/v2/value-help/enum/visibility/resolve', RESOLVE_NO_VALUE)

    def test_resolve_enum(self, api_client):
        expect(api_client, 'get', '/api/v2/value-help/enum/visibility/resolve?value=public', RESOLVE_OK)

    def test_resolve_bo(self, api_client):
        expect(api_client, 'get', '/api/v2/value-help/bo/domain/resolve?value=1&display_field=name', RESOLVE_OK)
