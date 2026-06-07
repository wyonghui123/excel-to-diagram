# -*- coding: utf-8 -*-
"""
GAP-026: owner_transfer_api (4 端点, 含 v1.4 P8 sunset 410)

[MARKER] deprecated - validate/transfer/bulk-transfer 已 sunset
"""
import pytest
from meta.tests.shared.assertions import expect, HTTPStatus

# 状态码域 (含 410 sunset)
VALIDATION = HTTPStatus.SUNSET_VALIDATION
OK_SUNSET = HTTPStatus.SUNSET_OK
HISTORY_INVALID = (200, 400, 403, 500, 410)

# 全部端点都已 sunset
pytestmark = pytest.mark.deprecated


# validate/transfer/bulk-transfer 端点 → 统一格式
OWNER_ENDPOINTS = {
    'validate': '/api/v1/admin/owner/validate',
    'transfer': '/api/v1/admin/owner/transfer',
    'bulk_transfer': '/api/v1/admin/owner/bulk-transfer',
}

MISSING_CASES = [
    pytest.param(ep, {'resource_type': 'product'},
                 id=f'{name}_missing_params')
    for name, ep in OWNER_ENDPOINTS.items()
] + [
    pytest.param(OWNER_ENDPOINTS['validate'], {}, id='validate_all_missing'),
]

VALID_CASES = [
    pytest.param('validate', OWNER_ENDPOINTS['validate'],
                 {'resource_type': 'product', 'resource_id': 1, 'from_user_id': 1, 'to_user_id': 2},
                 id='validate_valid'),
    pytest.param('transfer', OWNER_ENDPOINTS['transfer'],
                 {'resource_type': 'product', 'resource_id': 1, 'from_user_id': 1, 'to_user_id': 2,
                  'keep_original_permissions': True},
                 id='transfer_valid'),
    pytest.param('bulk_transfer', OWNER_ENDPOINTS['bulk_transfer'],
                 {'resource_type': 'product', 'from_user_id': 1, 'to_user_id': 2},
                 id='bulk_transfer_valid'),
]


class TestOwnerTransferAPI:
    @pytest.mark.parametrize('endpoint,body', MISSING_CASES)
    def test_owner_op_missing_params(self, api_client, endpoint, body):
        expect(api_client, 'post', endpoint, VALIDATION, json=body)

    @pytest.mark.parametrize('op_name,endpoint,body', VALID_CASES)
    def test_owner_op_valid(self, api_client, op_name, endpoint, body):
        expect(api_client, 'post', endpoint, OK_SUNSET, json=body)

    def test_transfer_history(self, api_client):
        expect(api_client, 'get', '/api/v1/admin/owner/transfer-history', OK_SUNSET)

    def test_transfer_history_with_filter(self, api_client):
        expect(api_client, 'get',
               '/api/v1/admin/owner/transfer-history?resource_type=product&user_id=1&limit=10',
               OK_SUNSET)

    def test_transfer_history_invalid_id(self, api_client):
        expect(api_client, 'get', '/api/v1/admin/owner/transfer-history?resource_id=abc',
               HISTORY_INVALID)
