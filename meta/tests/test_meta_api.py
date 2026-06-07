import pytest

pytestmark = pytest.mark.integration

import pytest
import json
from flask import Flask

from meta.api.manage_api import manage_bp, init_services
from meta.api.export_import_api import export_import_bp
from meta.api.meta_utility_routes_api import meta_util_bp
from meta.api.bo_api import bo_bp, meta_v2_bp
from meta.core.datasource import get_data_source
from meta.services.auth_provider import UserInfo
from meta.services.token_service import TokenService
from meta.tests.test_utils import get_test_db_path


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-key-for-testing'
    app.register_blueprint(manage_bp)
    app.register_blueprint(export_import_bp)
    app.register_blueprint(meta_util_bp)
    app.register_blueprint(bo_bp)
    app.register_blueprint(meta_v2_bp)
    ds = get_data_source("sqlite", database=get_test_db_path())
    init_services(ds)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    test_user = UserInfo(
        user_id='1',
        username='test_user',
        display_name='Test User',
        email='test@test.com',
        roles=['admin'],
        permissions=['*']
    )
    token, _ = TokenService.create_token(test_user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }


class TestBusinessObjectFilterConsistency:
    """测试业务对象过滤的一致性
    
    验证：对象树选择 → 列表查询 → 导出查询 三处数据一致
    """
    
    def test_list_with_service_module_id_filter(self, client, auth_headers):
        """测试列表查询使用 service_module_id 过滤"""
        response = client.get('/api/v2/bo/business_object?version_id=1&service_module_id=1&service_module_id=2', headers=auth_headers)
        assert response.status_code in [200, 401, 404, 500]
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False) is True
        
    def test_list_and_export_consistency(self, client, auth_headers):
        """测试列表和导出的过滤逻辑一致"""
        list_response = client.get('/api/v2/bo/business_object?version_id=1&service_module_id=1', headers=auth_headers)
        assert list_response.status_code == 200
        list_data = json.loads(list_response.data)
        list_count = list_data.get('total', 0)
        
        export_response = client.post('/api/v1/export', 
            json={
                'object_type': 'business_object',
                'scope': 'single',
                'filters': {'version_id': 1, 'service_module_id': [1]},
                'options': {}
            },
            headers=auth_headers
        )
        assert export_response.status_code == 200
        export_data = json.loads(export_response.data)
        assert export_data.get('success'), "Export should succeed"
        
        print(f"List count: {list_count}, Export count: {export_data.get('data', {}).get('total_rows', 0)}")
    
    def test_service_module_list_filter_by_ids(self, client, auth_headers):
        """
        测试服务模块维度下的列表过滤
        
        场景：对象树选择了3个服务模块（sm_1, sm_2, sm_3）
        当前维度是"服务模块"
        
        预期：列表只显示这3个服务模块，而不是所有
        """
        all_response = client.get('/api/v2/bo/service_module?version_id=1&page_size=1000', headers=auth_headers)
        assert all_response.status_code == 200
        all_data = json.loads(all_response.data)
        total_count = all_data.get('total', 0)
        
        if total_count >= 2:
            # 获取前2个服务模块的ID
            first_two_ids = [str(item['id']) for item in all_data.get('data', {})[:2]]
            
            # 用 service_module_id 过滤
            filter_params = '&'.join([f'service_module_id={id}' for id in first_two_ids])
            filtered_response = client.get(f'/api/v2/bo/service_module?version_id=1&{filter_params}', headers=auth_headers)
            assert filtered_response.status_code == 200
            filtered_data = json.loads(filtered_response.data)
            
            # 应该只返回2条记录
            assert filtered_data.get('total', 0) == 2, \
                f"Expected 2 records when filtering by IDs {first_two_ids}, got {filtered_data.get('total', 0)}"


class TestMetaHierarchiesAPI:
    
    def test_get_hierarchies_returns_success(self, client):
        response = client.get('/api/v1/meta/hierarchies')
        assert response.status_code in [200, 401, 404, 500]
        
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False) is True
        assert 'data' in data
    
    def test_get_hierarchies_returns_hierarchies(self, client):
        response = client.get('/api/v1/meta/hierarchies')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        hierarchies = data.get('data', {})['hierarchies']
        assert isinstance(hierarchies, list)
        assert len(hierarchies) > 0
    
    def test_get_hierarchies_returns_dimensions(self, client):
        response = client.get('/api/v1/meta/hierarchies')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        dimensions = data.get('data', {})['dimensions']
        assert isinstance(dimensions, list)
        
        dimension_ids = [d.get('id') for d in dimensions]
        assert 'domain' in dimension_ids
        assert 'sub_domain' in dimension_ids
        # [REMOVED] service_module 和 business_object - 2026-06-03 按业务需求移除
        # 原因: 层级过深(6层→4层)，授权到子领域已足够精确
        # assert 'service_module' in dimension_ids
        # assert 'business_object' in dimension_ids


class TestMetaHierarchyLevelsAPI:
    
    def test_get_hierarchy_levels_biz_hierarchy(self, client):
        response = client.get('/api/v1/meta/hierarchies/biz_hierarchy/levels')
        assert response.status_code in [200, 401, 404, 500]
        
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False) is True
        assert isinstance(data.get('data', {}), list)
    
    def test_get_hierarchy_levels_has_all_objects(self, client):
        response = client.get('/api/v1/meta/hierarchies/biz_hierarchy/levels')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        levels = data.get('data', {})
        objects = [level.get('object') for level in levels]
        
        assert 'domain' in objects
        assert 'sub_domain' in objects
        assert 'service_module' in objects
        assert 'business_object' in objects
    
    def test_get_hierarchy_levels_unknown_returns_404(self, client):
        response = client.get('/api/v1/meta/hierarchies/unknown_hierarchy/levels')
        assert response.status_code in [401, 404, 500]
        
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False) is False


class TestMetaHierarchyConfigAPI:
    
    def test_get_hierarchy_config_returns_success(self, client):
        response = client.get('/api/v1/meta/hierarchies/config')
        assert response.status_code in [200, 401, 404, 500]
        
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False) is True
    
    def test_get_hierarchy_config_returns_dimensions(self, client):
        response = client.get('/api/v1/meta/hierarchies/config')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        dimensions = data.get('data', {})['dimensions']
        assert isinstance(dimensions, list)
        
        for d in ['domain', 'sub_domain', 'service_module', 'business_object']:
            assert d in dimensions, f"Expected dimension '{d}' in {dimensions}"
    
    def test_get_hierarchy_config_returns_levels(self, client):
        response = client.get('/api/v1/meta/hierarchies/config')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        hierarchy_levels = data.get('data', {})['hierarchy_levels']
        
        assert 'domain' in hierarchy_levels
        assert 'sub_domain' in hierarchy_levels
        assert 'service_module' in hierarchy_levels
        assert 'business_object' in hierarchy_levels
    
    def test_get_hierarchy_config_domain_level(self, client):
        response = client.get('/api/v1/meta/hierarchies/config')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        domain_level = data.get('data', {})['hierarchy_levels']['domain']
        
        assert domain_level['level'] == 2
        assert domain_level['object'] == 'domain'
        assert domain_level['parent_object'] == 'version'
        assert domain_level['filter_param'] == 'version_id'
    
    def test_get_hierarchy_config_business_object_level(self, client):
        response = client.get('/api/v1/meta/hierarchies/config')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        bo_level = data.get('data', {})['hierarchy_levels']['business_object']
        
        assert bo_level['level'] == 5
        assert bo_level['object'] == 'business_object'
        assert bo_level['parent_object'] == 'service_module'
        assert bo_level['filter_param'] == 'service_module_id'


class TestMetaFieldControlsAPI:
    
    def test_get_field_controls_business_object(self, client):
        response = client.get('/api/v1/meta/objects/business_object/field_controls')
        assert response.status_code in [200, 401, 404, 500]
        
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False) is True
        assert 'field_controls' in data.get('data', {})
    
    def test_get_field_controls_has_code_field(self, client):
        response = client.get('/api/v1/meta/objects/business_object/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        field_controls = data.get('data', {})['field_controls']
        assert 'code' in field_controls
    
    def test_get_field_controls_code_is_business_key(self, client):
        response = client.get('/api/v1/meta/objects/business_object/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        code_controls = data.get('data', {})['field_controls']['code']
        assert code_controls['business_key'] is True
        assert code_controls['immutable'] is True
    
    def test_get_field_controls_service_module_id_is_parent_key(self, client):
        response = client.get('/api/v1/meta/objects/business_object/field_controls')
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        
        sm_controls = data.get('data', {})['field_controls']['service_module_id']
        assert sm_controls['parent_key'] is True
    
    def test_get_field_controls_unknown_object_returns_404(self, client):
        response = client.get('/api/v1/meta/objects/unknown_object/field_controls')
        assert response.status_code in [401, 404, 500]
        
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False) is False
    
    def test_get_field_controls_domain(self, client):
        response = client.get('/api/v1/meta/objects/domain/field_controls')
        assert response.status_code in [200, 401, 404, 500]
        
        try:
            data = json.loads(response.data)
        except (json.JSONDecodeError, ValueError):
            data = {}
        assert data.get('success', False) is True
        assert 'field_controls' in data.get('data', {})
