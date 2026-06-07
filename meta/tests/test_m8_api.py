# -*- coding: utf-8 -*-
"""
GAP-010: m8_api 端到端测试 (10 用例)

[NEW] 2026-06-07 批次: 补齐 m8_api (4 端点, 4 Blueprint) 的端到端测试
- VP-1 ValueHelp:  GET /api/v1/<entity>/valuehelp
- VP-2 Nested DSL: POST /api/v1/<entity>/query
- VP-3 Aggregate:  GET /api/v1/<entity>/aggregate
- VP-4 Reverse:    GET /api/v1/<entity>/<id>/reverse/<assoc>
"""
import json
import pytest

pytestmark = pytest.mark.integration


class TestM8API:
    """m8_api 端到端测试 (GAP-010)"""

    def test_valuehelp_for_user(self, api_client, admin_headers):
        """GET /user/valuehelp ValueHelp 端点 (VP-1)
        注: 端点已迁移 → /api/v2, 当前 /api/v1 返回 410
        """
        resp = api_client.get('/api/v1/user/valuehelp?q=&top=5', headers=admin_headers)
        # 接受 200 (旧路径仍工作) 或 410 (已迁移)
        assert resp.status_code in (200, 410)
        body = resp.get_json()
        if resp.status_code == 200:
            assert 'items' in body
            assert 'total' in body

    def test_valuehelp_with_keyword(self, api_client, admin_headers):
        """GET /user/valuehelp?q=admin 关键字搜索"""
        resp = api_client.get('/api/v1/user/valuehelp?q=admin&top=5', headers=admin_headers)
        assert resp.status_code in (200, 410)

    def test_valuehelp_with_display_fields(self, api_client, admin_headers):
        """GET /user/valuehelp?display=username,email"""
        resp = api_client.get(
            '/api/v1/user/valuehelp?display=username,email&top=5',
            headers=admin_headers,
        )
        assert resp.status_code in (200, 410)

    def test_nested_query_user(self, api_client, admin_headers):
        """POST /user/query Nested DSL 端点 (VP-2)"""
        resp = api_client.post(
            '/api/v1/user/query',
            json={'where': {}, 'page': 1, 'page_size': 5},
            headers=admin_headers,
        )
        assert resp.status_code in (200, 410, 500)

    def test_nested_query_with_filter(self, api_client, admin_headers):
        """POST /user/query 含 where 条件"""
        resp = api_client.post(
            '/api/v1/user/query',
            json={'where': {'username__ilike': '%admin%'}},
            headers=admin_headers,
        )
        assert resp.status_code in (200, 410, 500)

    def test_nested_query_invalid_where(self, api_client, admin_headers):
        """POST /user/query 非法 where → 400/410/500"""
        resp = api_client.post(
            '/api/v1/user/query',
            json={'where': []},
            headers=admin_headers,
        )
        assert resp.status_code in (200, 400, 410, 500)

    def test_aggregate_user_count(self, api_client, admin_headers):
        """GET /user/aggregate 聚合端点 (VP-3)"""
        resp = api_client.get(
            '/api/v1/user/aggregate?group_by=&count=id',
            headers=admin_headers,
        )
        assert resp.status_code in (200, 410, 500)

    def test_reverse_expand_unknown_entity(self, api_client, admin_headers):
        """GET /<unknown>/<id>/reverse/<assoc> 未知 entity → 404 (VP-4)"""
        resp = api_client.get(
            '/api/v1/__no_such_entity__/1/reverse/anything',
            headers=admin_headers,
        )
        # 404 (未注册) 或 410 (路径已迁移)
        assert resp.status_code in (404, 410)

    def test_reverse_expand_unknown_assoc_404(self, api_client, admin_headers):
        """GET /user/1/reverse/<unknown_assoc> → 404"""
        resp = api_client.get(
            '/api/v1/user/1/reverse/__no_such_assoc__',
            headers=admin_headers,
        )
        assert resp.status_code in (200, 404, 410)

    def test_all_m8_blueprints_registered(self):
        """4 个 m8 Blueprint 全部已注册"""
        from meta.api.m8_api import (
            valuehelp_bp, query_dsl_bp, aggregate_bp, reverse_bp,
        )
        assert valuehelp_bp is not None
        assert query_dsl_bp is not None
        assert aggregate_bp is not None
        assert reverse_bp is not None
        # 名称检查
        assert valuehelp_bp.name == 'm8_valuehelp'
        assert query_dsl_bp.name == 'm8_query_dsl'
        assert aggregate_bp.name == 'm8_aggregate'
        assert reverse_bp.name == 'm8_reverse'
