import pytest

pytestmark = pytest.mark.e2e

# -*- coding: utf-8 -*-
"""
使用 Playwright 进行浏览器端到端测试（使用 Flask Test Client）
测试前端过滤功能
"""

import pytest
import os
import sys
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture(scope="module")
def app():
    """创建测试用 Flask 应用"""
    from flask import Flask
    from meta.api.filter_variant_api import filter_variant_bp, _init_table, _execute_query, _get_db_path
    import meta.api.filter_variant_api as fva
    
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    app.config['DATABASE'] = db_path
    fva._db_path = db_path
    
    with app.app_context():
        _init_table()
        
        _execute_query('''
            INSERT INTO filter_variants (name, object_type, filters, user_id, is_shared, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('预置变体1', 'domain', '{"created_at_from":"2024-01-01"}', 1, 0, 1, '2024-01-01', '2024-01-01'), fetch=False)
        
        _execute_query('''
            INSERT INTO filter_variants (name, object_type, filters, user_id, is_shared, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('预置变体2', 'business_object', '{"status":"active"}', 1, 0, 0, '2024-01-01', '2024-01-01'), fetch=False)
    
    app.register_blueprint(filter_variant_bp)
    
    yield app, db_path
    
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(scope="module")
def client(app):
    """创建测试客户端"""
    return app[0].test_client()


class TestFilterVariantE2EWithClient:
    """使用 Flask Test Client 的端到端测试"""
    
    def test_list_variants_via_client(self, client):
        """测试通过 Test Client 列出变体"""
        response = client.get('/api/v1/filter-variants')
        data = response.get_json()
        
        assert response.status_code in [200, 401, 404, 500]
        assert data.get('success', False) is True
        assert len(data.get('data', {})) == 2
        print(f"[DECORATIVE] 列出 {len(data.get('data', {}))} 个变体")
    
    def test_create_variant_via_client(self, client):
        """测试通过 Test Client 创建变体"""
        response = client.post('/api/v1/filter-variants', json={
            'name': 'Test E2E Variant',
            'object_type': 'domain',
            'filters': {'created_at_from': '2024-06-01'},
            'is_shared': False,
            'is_default': False
        })
        data = response.get_json()
        
        assert response.status_code in [200, 401, 404, 500]
        assert data.get('success', False) is True
        assert data.get('data', {})['name'] == 'Test E2E Variant'
        print(f"[DECORATIVE] 创建变体成功: {data.get('data', {})['name']}")
    
    def test_get_variant_via_client(self, client):
        """测试通过 Test Client 获取单个变体"""
        create_resp = client.post('/api/v1/filter-variants', json={
            'name': 'Get Test Variant',
            'object_type': 'domain',
            'filters': {}
        })
        variant_id = create_resp.get_json()['data']['id']
        
        get_resp = client.get(f'/api/v1/filter-variants/{variant_id}')
        data = get_resp.get_json()
        
        assert get_resp.status_code == 200
        assert data.get('data', {})['name'] == 'Get Test Variant'
        print(f"[DECORATIVE] 获取变体成功: {data.get('data', {})['name']}")
    
    def test_update_variant_via_client(self, client):
        """测试通过 Test Client 更新变体"""
        create_resp = client.post('/api/v1/filter-variants', json={
            'name': 'Original Name',
            'object_type': 'domain',
            'filters': {'old': 'value'}
        })
        variant_id = create_resp.get_json()['data']['id']
        
        update_resp = client.put(f'/api/v1/filter-variants/{variant_id}', json={
            'name': 'Updated Name',
            'filters': {'new': 'value'}
        })
        data = update_resp.get_json()
        
        assert update_resp.status_code == 200
        assert data.get('data', {})['name'] == 'Updated Name'
        print(f"[DECORATIVE] 更新变体成功: {data.get('data', {})['name']}")
    
    def test_delete_variant_via_client(self, client):
        """测试通过 Test Client 删除变体"""
        create_resp = client.post('/api/v1/filter-variants', json={
            'name': 'To Delete',
            'object_type': 'domain',
            'filters': {}
        })
        variant_id = create_resp.get_json()['data']['id']
        
        delete_resp = client.delete(f'/api/v1/filter-variants/{variant_id}')
        assert delete_resp.status_code == 200
        
        get_resp = client.get(f'/api/v1/filter-variants/{variant_id}')
        assert get_resp.status_code == 404
        print("[DECORATIVE] 删除变体成功")
    
    def test_set_default_variant_via_client(self, client):
        """测试通过 Test Client 设置默认变体"""
        create_resp = client.post('/api/v1/filter-variants', json={
            'name': 'New Default',
            'object_type': 'domain',
            'filters': {}
        })
        variant_id = create_resp.get_json()['data']['id']
        
        set_default_resp = client.post(f'/api/v1/filter-variants/{variant_id}/set-default')
        assert set_default_resp.status_code == 200
        
        get_resp = client.get(f'/api/v1/filter-variants/{variant_id}')
        assert get_resp.get_json()['data']['is_default'] is True
        print("[DECORATIVE] 设置默认变体成功")
    
    def test_filter_by_object_type_via_client(self, client):
        """测试按对象类型过滤"""
        response = client.get('/api/v1/filter-variants?object_type=domain')
        data = response.get_json()
        
        assert all(v['object_type'] == 'domain' for v in data.get('data', {}))
        print(f"[DECORATIVE] 按对象类型过滤成功，找到 {len(data.get('data', {}))} 个 domain 变体")


class TestQueryServiceIntegration:
    """查询服务集成测试"""
    
    def test_search_request_with_filter_params(self):
        """测试 SearchRequest 包含 filter_params"""
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
        print("[DECORATIVE] SearchRequest 支持 filter_params")
    
    def test_filter_service_builds_correct_conditions(self):
        """测试过滤服务构建正确的条件"""
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
        print(f"[DECORATIVE] 过滤服务构建了 {len(conditions)} 个过滤条件")


class TestFilterServiceE2E:
    """过滤服务端到端测试"""
    
    def test_complete_filter_flow(self):
        """测试完整的过滤流程"""
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
                    'id': 'created_by',
                    'db_column': 'created_by',
                    'semantics': {
                        'filterable': True,
                        'filter_type': 'user',
                        'filter_scope': 'global',
                        'filter_operator': 'like'
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
            'created_by': 'admin',
            'status': 'active'
        }
        
        global_conditions = filter_service.build_filters_from_meta(meta_obj, params, 'global')
        assert len(global_conditions) == 3
        
        local_conditions = filter_service.build_filters_from_meta(meta_obj, params, 'local')
        assert len(local_conditions) == 1
        
        print(f"[DECORATIVE] 全局过滤: {len(global_conditions)} 个条件, 局部过滤: {len(local_conditions)} 个条件")
        
        for cond in global_conditions:
            print(f"  - {cond.field} {cond.operator} {cond.value}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
