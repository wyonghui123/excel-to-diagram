# -*- coding: utf-8 -*-
"""
GAP-011: meta_utility_routes_api 端到端测试 (8 用例)

[NEW] 2026-06-07 批次: 补齐 meta_utility_routes_api (5 端点) 的端到端测试
- GET /meta/objects                       (列表对象类型)
- GET /meta/hierarchies                   (层级配置)
- GET /meta/hierarchies/<id>/levels       (层级等级)
- GET /meta/hierarchies/config            (biz_hierarchy 简版)
- GET /meta/objects/<type>/field_controls (字段控制)
"""
import pytest

pytestmark = pytest.mark.integration


class TestMetaUtilityAPI:
    """meta_utility_routes_api 端到端测试 (GAP-011)"""

    def test_list_object_types(self, api_client, admin_headers):
        """GET /meta/objects 列表所有对象类型"""
        resp = api_client.get('/api/v1/meta/objects', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body['data'], list)
        # 至少有 user/role 这两个
        ids = {obj['id'] for obj in body['data']}
        assert 'user' in ids
        assert 'role' in ids

    def test_list_object_types_exclude_system(self, api_client, admin_headers):
        """GET /meta/objects?exclude_system=true"""
        resp = api_client.get('/api/v1/meta/objects?exclude_system=true', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # 所有返回对象的 category 不应含 system_entity
        for obj in body['data']:
            if 'category' in obj:
                assert obj.get('category') != 'system_entity'

    def test_get_hierarchies(self, api_client, admin_headers):
        """GET /meta/hierarchies 层级配置"""
        resp = api_client.get('/api/v1/meta/hierarchies', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body['data']
        assert 'hierarchies' in data
        assert 'dimensions' in data
        assert 'hierarchy_scopes' in data
        assert 'api_mappings' in data

    def test_get_hierarchy_levels_404(self, api_client, admin_headers):
        """GET /meta/hierarchies/<unknown>/levels 404"""
        resp = api_client.get('/api/v1/meta/hierarchies/__no_such__/levels', headers=admin_headers)
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False
        # 端点用英文 "Hierarchy not found"
        assert 'not found' in body.get('message', '').lower() or '不存在' in body.get('message', '')

    def test_get_hierarchy_levels_biz(self, api_client, admin_headers):
        """GET /meta/hierarchies/biz_hierarchy/levels 业务层级"""
        resp = api_client.get('/api/v1/meta/hierarchies/biz_hierarchy/levels', headers=admin_headers)
        # 200 (有 biz_hierarchy) 或 404
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            body = resp.get_json()
            assert body.get('success') is True
            assert isinstance(body['data'], list)

    def test_get_hierarchy_config(self, api_client, admin_headers):
        """GET /meta/hierarchies/config biz_hierarchy 简版"""
        resp = api_client.get('/api/v1/meta/hierarchies/config', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body['data']
        assert 'dimensions' in data
        assert 'hierarchy_levels' in data

    def test_get_field_controls_404(self, api_client, admin_headers):
        """GET /meta/objects/<unknown>/field_controls 404"""
        resp = api_client.get('/api/v1/meta/objects/__no_such_type__/field_controls', headers=admin_headers)
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False

    def test_get_field_controls_for_user(self, api_client, admin_headers):
        """GET /meta/objects/user/field_controls 字段控制信息"""
        resp = api_client.get('/api/v1/meta/objects/user/field_controls', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        data = body['data']
        assert 'object_type' in data
        assert data['object_type'] == 'user'
        assert 'field_controls' in data
        # field_controls 是 dict {field_id: {business_key, immutable, mandatory, ...}}
        assert isinstance(data['field_controls'], dict)
