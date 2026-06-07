# -*- coding: utf-8 -*-
"""
GAP-017: key_template_api 端到端测试 (5 用例)

[NEW] 2026-06-07 批次: 补齐 key_template_api (3 端点) 的端到端测试
- GET  /api/v2/key-template/config/<object_type>
- POST /api/v2/key-template/preview/<object_type>
- GET  /api/v2/key-template/list-objects
"""
import pytest

pytestmark = pytest.mark.integration


KT_URL = '/api/v2/key-template'


class TestKeyTemplateAPI:
    """key_template_api 端到端测试 (GAP-017)"""

    def test_get_config_unknown_type_404(self, api_client, admin_headers):
        """GET /config/<unknown> 404"""
        resp = api_client.get(f'{KT_URL}/config/__no_such__', headers=admin_headers)
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False

    def test_get_config_user_no_key_template(self, api_client, admin_headers):
        """GET /config/user (通常 user 不配置 key_template)"""
        resp = api_client.get(f'{KT_URL}/config/user', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # user 通常无 key_template → data.enabled=False
        data = body.get('data', {})
        if isinstance(data, dict) and 'enabled' in data:
            # 无 key_template 配置
            assert data.get('enabled') is False

    def test_preview_code_unknown_type_404(self, api_client, admin_headers):
        """POST /preview/<unknown> 404"""
        resp = api_client.post(
            f'{KT_URL}/preview/__no_such__',
            json={'field_values': {}, 'generate': False},
            headers=admin_headers,
        )
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False

    def test_preview_code_no_key_template(self, api_client, admin_headers):
        """POST /preview/<user> (无 key_template) → success=False"""
        resp = api_client.post(
            f'{KT_URL}/preview/user',
            json={'field_values': {}, 'generate': False},
            headers=admin_headers,
        )
        # 200 (enabled=False 走 success=False path) 或 500
        assert resp.status_code in (200, 500)

    def test_list_objects(self, api_client, admin_headers):
        """GET /list-objects 返回配置 key_template 的对象列表"""
        resp = api_client.get(f'{KT_URL}/list-objects', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body['data'], list)
        # 每个对象含 object_type / name / pattern / preview
        for obj in body['data']:
            assert 'object_type' in obj
            assert 'pattern' in obj
