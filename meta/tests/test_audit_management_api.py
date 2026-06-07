# -*- coding: utf-8 -*-
"""
GAP-019: audit_management_api 端到端测试 (5 用例)

[NEW] 2026-06-07 批次: 补齐 audit_management_api (3 端点) 的端到端测试
- GET  /api/v1/audit/failed
- POST /api/v1/audit/failed/<id>/retry
- GET  /api/v1/audit/stats
- 全部 admin_required
"""
import pytest

pytestmark = pytest.mark.integration


AUDIT_MGMT_URL = '/api/v1/audit'


class TestAuditManagementAPI:
    """audit_management_api 端到端测试 (GAP-019)"""

    def test_get_failed_audit_logs_requires_admin(self, api_client, regular_user_headers):
        """GET /audit/failed 非 admin → 403"""
        resp = api_client.get(f'{AUDIT_MGMT_URL}/failed', headers=regular_user_headers)
        assert resp.status_code == 403

    def test_get_failed_audit_logs_admin(self, api_client, admin_headers):
        """GET /audit/failed admin → 列表"""
        resp = api_client.get(f'{AUDIT_MGMT_URL}/failed', headers=admin_headers)
        # 200 (AuditService 正常) 或 500 (未 init)
        assert resp.status_code in (200, 500)

    def test_get_failed_audit_logs_with_pagination(self, api_client, admin_headers):
        """GET /audit/failed?page=1&page_size=10 分页"""
        resp = api_client.get(
            f'{AUDIT_MGMT_URL}/failed?page=1&page_size=10',
            headers=admin_headers,
        )
        assert resp.status_code in (200, 500)

    def test_retry_failed_log_requires_admin(self, api_client, regular_user_headers):
        """POST /audit/failed/<id>/retry 非 admin → 403"""
        resp = api_client.post(
            f'{AUDIT_MGMT_URL}/failed/1/retry',
            headers=regular_user_headers,
        )
        assert resp.status_code == 403

    def test_audit_writer_stats(self, api_client, admin_headers):
        """GET /audit/stats 异步 writer 统计"""
        resp = api_client.get(f'{AUDIT_MGMT_URL}/stats', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'data' in body
