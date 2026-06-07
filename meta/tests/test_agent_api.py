# -*- coding: utf-8 -*-
"""
GAP-016: agent_api 端到端测试 (5 用例, agent 工具元数据)

[MARKER] auth_required - 全部需要 admin 认证 (admin_headers)
[EXPECT] 全部用 expect() 简化
"""
import pytest
from meta.tests.shared.assertions import (
    expect, assert_data_contains,
)

pytestmark = [pytest.mark.integration, pytest.mark.auth_required]

AGENT_URL = '/api/v1/agent'


class TestAgentAPI:
    """agent_api 端到端测试 (GAP-016)"""

    def test_get_tools(self, api_client, admin_headers):
        r = expect(api_client, 'get', f'{AGENT_URL}/tools', [200], headers=admin_headers)
        assert_data_contains(r, 'total', scope=None)
        assert r.get_json()['total'] >= 0

    def test_get_tools_includes_crud_schemas(self, api_client, admin_headers):
        r = expect(api_client, 'get', f'{AGENT_URL}/tools', [200], headers=admin_headers)
        body = r.get_json()
        tool_names = {t.get('name') for t in body['data']}
        assert any('user' in str(n) for n in tool_names)

    def test_get_object_context(self, api_client, admin_headers):
        r = expect(api_client, 'get', f'{AGENT_URL}/context/user', [200], headers=admin_headers)
        data = r.get_json()['data']
        assert data['object_type'] == 'user'
        for key in ('name', 'fields', 'relations', 'actions', 'view_config'):
            assert key in data, f"缺少字段 {key}"

    def test_get_object_context_404(self, api_client, admin_headers):
        r = expect(api_client, 'get', f'{AGENT_URL}/context/__no_such_type__',
                   [404], headers=admin_headers)
        body = r.get_json()
        assert body.get('success') is False
        assert 'not found' in body.get('error', '').lower()

    def test_get_full_schema(self, api_client, admin_headers):
        r = expect(api_client, 'get', f'{AGENT_URL}/schema', [200], headers=admin_headers)
        schema = r.get_json()['data']
        assert 'objects' in schema
        assert 'relations' in schema
        assert isinstance(schema['relations'], list)
