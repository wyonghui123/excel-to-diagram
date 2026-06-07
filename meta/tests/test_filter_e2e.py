import pytest

pytestmark = pytest.mark.e2e

# -*- coding: utf-8 -*-
"""
过滤系统端到端测试
测试完整的过滤流程：前端 -> API -> 数据库 -> 返回前端
"""

import pytest
import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from playwright.sync_api import sync_playwright, expect
from meta.api.filter_variant_api import filter_variant_bp, _init_table, _execute_query, _get_db_path
from flask import Flask


@pytest.fixture(scope="module")
def app_with_db():
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    app.config['DATABASE'] = db_path
    
    import meta.api.filter_variant_api as fva
    fva._db_path = db_path
    
    with app.app_context():
        _init_table()
        
        _execute_query('''
            INSERT INTO filter_variants (name, object_type, filters, user_id, is_shared, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('预置变体1', 'domain', '{"created_at_from":"2024-01-01"}', 1, 0, 1, time.time(), time.time()), fetch=False)
        
        _execute_query('''
            INSERT INTO filter_variants (name, object_type, filters, user_id, is_shared, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('预置变体2', 'business_object', '{"status":"active"}', 1, 0, 0, time.time(), time.time()), fetch=False)
    
    app.register_blueprint(filter_variant_bp)
    
    yield app, db_path
    
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(scope="module")
def api_url(app_with_db):
    """v3.18 P1: 端口由 env var 控制 (默认 3010). 注: 此 fixture 当前未被使用 (L64-73 用 app.test_client)."""
    return os.environ.get('TEST_API_URL', 'http://127.0.0.1:3010')


class TestFilterVariantE2E:
    """过滤变体端到端测试"""
    
    def test_api_returns_variants(self, app_with_db, api_url):
        """测试API返回预置的变体"""
        app, _ = app_with_db
        
        with app.test_client() as client:
            resp = client.get('/api/v1/filter-variants')
            data = resp.get_json()
            
            assert resp.status_code in [200, 401, 404, 500]
            assert data.get('success', False) is True
            assert len(data.get('data', {})) == 2
    
    def test_create_and_retrieve_variant(self, app_with_db):
        """测试创建和检索变体的完整流程"""
        app, _ = app_with_db
        
        with app.test_client() as client:
            create_resp = client.post('/api/v1/filter-variants', json={
                'name': 'E2E测试变体',
                'object_type': 'domain',
                'filters': {'created_at_from': '2024-06-01', 'created_by_like': 'admin'},
                'is_shared': False,
                'is_default': False
            })
            
            assert create_resp.status_code == 200
            variant_id = create_resp.get_json()['data']['id']
            
            get_resp = client.get(f'/api/v1/filter-variants/{variant_id}')
            assert get_resp.status_code == 200
            
            variant = get_resp.get_json()['data']
            assert variant['name'] == 'E2E测试变体'
            assert variant['filters']['created_at_from'] == '2024-06-01'
            assert variant['filters']['created_by_like'] == 'admin'
    
    def test_update_variant_flow(self, app_with_db):
        """测试更新变体的完整流程"""
        app, _ = app_with_db
        
        with app.test_client() as client:
            create_resp = client.post('/api/v1/filter-variants', json={
                'name': '待更新变体',
                'object_type': 'domain',
                'filters': {'old': 'value'}
            })
            variant_id = create_resp.get_json()['data']['id']
            
            update_resp = client.put(f'/api/v1/filter-variants/{variant_id}', json={
                'name': '已更新变体',
                'filters': {'new': 'value', 'extra': 'data'}
            })
            
            assert update_resp.status_code == 200
            assert update_resp.get_json()['data']['name'] == '已更新变体'
            
            get_resp = client.get(f'/api/v1/filter-variants/{variant_id}')
            variant = get_resp.get_json()['data']
            assert variant['filters'] == {'new': 'value', 'extra': 'data'}
    
    def test_delete_variant_flow(self, app_with_db):
        """测试删除变体的完整流程"""
        app, _ = app_with_db
        
        with app.test_client() as client:
            create_resp = client.post('/api/v1/filter-variants', json={
                'name': '待删除变体',
                'object_type': 'domain',
                'filters': {}
            })
            variant_id = create_resp.get_json()['data']['id']
            
            delete_resp = client.delete(f'/api/v1/filter-variants/{variant_id}')
            assert delete_resp.status_code == 200
            
            get_resp = client.get(f'/api/v1/filter-variants/{variant_id}')
            assert get_resp.status_code == 404
    
    def test_default_variant_behavior(self, app_with_db):
        """测试默认变体行为：同一对象类型只能有一个默认变体"""
        app, _ = app_with_db
        
        with app.test_client() as client:
            client.post('/api/v1/filter-variants', json={
                'name': '第二个默认',
                'object_type': 'domain',
                'filters': {},
                'is_default': True
            })
            
            list_resp = client.get('/api/v1/filter-variants?object_type=domain')
            variants = list_resp.get_json()['data']
            
            default_count = sum(1 for v in variants if v['is_default'])
            assert default_count == 1
            
            default_variant = next(v for v in variants if v['is_default'])
            assert default_variant['name'] == '第二个默认'
    
    def test_filter_variants_by_object_type(self, app_with_db):
        """测试按对象类型过滤变体"""
        app, _ = app_with_db
        
        with app.test_client() as client:
            resp = client.get('/api/v1/filter-variants?object_type=domain')
            variants = resp.get_json()['data']
            
            assert all(v['object_type'] == 'domain' for v in variants)


class TestFilterServiceE2E:
    """过滤服务端到端测试"""
    
    def test_filter_service_with_meta_definition(self):
        """测试过滤服务使用元模型定义构建过滤条件"""
        from meta.services.filter_service import FilterService
        
        filter_service = FilterService()
        
        meta_obj = {
            'fields': [
                {
                    'id': 'created_at',
                    'db_column': 'created_at',
                    'semantics': {
                        'filterable': True,
                        'filter_type': 'date',
                        'filter_scope': 'global'
                    }
                },
                {
                    'id': 'status',
                    'db_column': 'status',
                    'semantics': {
                        'filterable': True,
                        'filter_type': 'enum',
                        'filter_scope': 'local',
                        'filter_options': [
                            {'value': 'active', 'label': '活跃'},
                            {'value': 'inactive', 'label': '未激活'}
                        ]
                    }
                }
            ]
        }
        
        params = {
            'created_at_from': '2024-01-01',
            'created_at_to': '2024-12-31',
            'status': 'active'
        }
        
        global_conditions = filter_service.build_filters_from_meta(meta_obj, params, 'global')
        assert len(global_conditions) == 2
        
        local_conditions = filter_service.build_filters_from_meta(meta_obj, params, 'local')
        assert len(local_conditions) == 1
        assert local_conditions[0].field == 'status'
        assert local_conditions[0].value == 'active'
    
    def test_filter_service_date_range(self):
        """测试日期范围过滤"""
        from meta.services.filter_service import FilterService
        
        filter_service = FilterService()
        
        meta_obj = {
            'fields': [
                {
                    'id': 'created_at',
                    'db_column': 'created_at',
                    'semantics': {
                        'filterable': True,
                        'filter_type': 'date',
                        'filter_scope': 'global'
                    }
                }
            ]
        }
        
        params = {
            'created_at_from': '2024-06-01',
            'created_at_to': '2024-06-30'
        }
        
        conditions = filter_service.build_filters_from_meta(meta_obj, params, 'global')
        
        assert len(conditions) == 2
        from_field = next(c for c in conditions if c.operator == '>=')
        to_field = next(c for c in conditions if c.operator == '<=')
        
        assert from_field.field == 'created_at'
        assert from_field.value == '2024-06-01'
        assert to_field.field == 'created_at'
        assert to_field.value == '2024-06-30'
    
    def test_filter_service_user_like(self):
        """测试用户模糊过滤"""
        from meta.services.filter_service import FilterService
        
        filter_service = FilterService()
        
        meta_obj = {
            'fields': [
                {
                    'id': 'created_by',
                    'db_column': 'created_by',
                    'semantics': {
                        'filterable': True,
                        'filter_type': 'user',
                        'filter_scope': 'global',
                        'filter_operator': 'like'
                    }
                }
            ]
        }
        
        params = {'created_by': 'admin'}
        
        conditions = filter_service.build_filters_from_meta(meta_obj, params, 'global')
        
        assert len(conditions) == 1
        assert conditions[0].field == 'created_by'
        assert conditions[0].operator == 'like'
        assert conditions[0].value == '%admin%'


class TestQueryServiceIntegration:
    """查询服务集成测试"""
    
    def test_search_request_with_filter_params(self):
        """测试SearchRequest包含filter_params"""
        from meta.services.query_service import SearchRequest
        
        request = SearchRequest(
            object_type='domain',
            conditions=[],
            keyword='',
            filter_params={'created_at_from': '2024-01-01'},
            filter_scope='global'
        )
        
        assert request.filter_params == {'created_at_from': '2024-01-01'}
        assert request.filter_scope == 'global'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
