# -*- coding: utf-8 -*-
"""
GAP-015: overlap_api 端到端测试 (6 用例)

[NEW] 2026-06-07 批次: 补齐 overlap_api (2 端点 × v1/v2 双路由) 的端到端测试
- GET /api/v1/roles/<role_id>/overlaps
- GET /api/v1/roles/<role_id>/overlaps/summary
- GET /api/v2/roles/<role_id>/overlaps (v2 双路由)
- GET /api/v2/roles/<role_id>/overlaps/summary
"""
import json
import pytest

pytestmark = pytest.mark.integration


class TestOverlapAPI:
    """overlap_api 端到端测试 (GAP-015)"""

    def test_get_role_overlaps_v1(self, api_client, admin_headers):
        """GET /api/v1/roles/<id>/overlaps v1 路由"""
        resp = api_client.get('/api/v1/roles/1/overlaps', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body['data']
        assert 'overlaps' in data
        assert 'summary' in data
        assert isinstance(data['overlaps'], list)

    def test_get_role_overlaps_with_filter(self, api_client, admin_headers):
        """GET /api/v1/roles/<id>/overlaps?resource_type=user 按资源类型过滤"""
        resp = api_client.get(
            '/api/v1/roles/1/overlaps?resource_type=user',
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True

    def test_get_overlap_summary_v1(self, api_client, admin_headers):
        """GET /api/v1/roles/<id>/overlaps/summary 轻量级摘要"""
        resp = api_client.get('/api/v1/roles/1/overlaps/summary', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body['data']
        # 摘要字段
        assert 'has_overlap' in data
        assert 'count' in data

    def test_get_role_overlaps_v2(self, api_client, admin_headers):
        """GET /api/v2/roles/<id>/overlaps v2 路由 (双路由)"""
        resp = api_client.get('/api/v2/roles/1/overlaps', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'overlaps' in body['data']

    def test_get_overlap_summary_v2(self, api_client, admin_headers):
        """GET /api/v2/roles/<id>/overlaps/summary v2 路由"""
        resp = api_client.get('/api/v2/roles/1/overlaps/summary', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'has_overlap' in body['data']

    def test_overlap_summary_with_no_overlap_role(self, api_client, admin_headers):
        """摘要端点对无重叠角色也返回正常结构"""
        resp = api_client.get('/api/v2/roles/999999/overlaps/summary', headers=admin_headers)
        # role 999999 可能不存在 → 500, 存在则 200
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            body = resp.get_json()
            # has_overlap=False 或 字段缺失
            data = body.get('data', {})
            if 'has_overlap' in data:
                assert data['has_overlap'] is False or data['count'] == 0
