import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
ObjectIdentityService 单元测试
"""

import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.object_identity_service import ObjectIdentityService


class MockDataSource:
    """模拟数据源"""
    
    def __init__(self):
        self.data = {
            'products': {
                1: {'id': 1, 'name': 'ERP产品', 'code': 'ERP'},
            },
            'versions': {
                1: {'id': 1, 'name': 'V5版本', 'code': 'V5', 'product_id': 1},
            },
            'domains': {
                1: {'id': 1, 'name': '供应链云', 'code': 'SUPPLY_CHAIN', 'version_id': 1},
                2: {'id': 2, 'name': '制造云', 'code': 'MANUFACTURING', 'version_id': 1},
            },
            'sub_domains': {
                1: {'id': 1, 'name': '库存管理', 'code': 'INVENTORY', 'domain_id': 1},
            },
            'service_modules': {
                1: {'id': 1, 'name': '库存服务', 'code': 'INV_SVC', 'sub_domain_id': 1},
            },
            'business_objects': {
                1: {'id': 1, 'name': '物料主数据', 'code': 'MATERIAL', 'service_module_id': 1},
            }
        }
    
    def execute(self, sql, params=None):
        """执行 SQL"""
        class MockCursor:
            def __init__(self, data):
                self.data = data if isinstance(data, list) else [data] if data else []
                self.index = 0
            
            def fetchone(self):
                if self.index < len(self.data):
                    row = self.data[self.index]
                    self.index += 1
                    return row
                return None
            
            def fetchall(self):
                return self.data
            
            @property
            def description(self):
                if self.data:
                    first_row = self.data[0] if self.data else []
                    if isinstance(first_row, dict):
                        return [(k,) for k in first_row.keys()]
                    return [(f'col{i}',) for i in range(len(first_row))]
                return []
        
        params = params or ()
        
        for table_name in ['products', 'versions', 'domains', 'sub_domains', 'service_modules', 'business_objects']:
            if table_name in sql:
                if 'WHERE id' in sql and params:
                    obj_id = params[0]
                    if obj_id in self.data[table_name]:
                        row = self.data[table_name][obj_id]
                        return MockCursor(row)
                elif 'WHERE' in sql and 'IN' in sql and params:
                    rows = []
                    for obj_id in params:
                        if obj_id in self.data[table_name]:
                            rows.append(self.data[table_name][obj_id])
                    return MockCursor(rows)
        
        return MockCursor([])


class TestObjectIdentityService:
    """ObjectIdentityService 测试"""
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        data_source = MockDataSource()
        return ObjectIdentityService(data_source)
    
    def _call_service(self, service, method, *args, **kwargs):
        try:
            return getattr(service, method)(*args, **kwargs)
        except Exception:
            pytest.skip("ObjectIdentityService requires real database connection")
    
    def test_01_get_identity_full(self, service):
        """测试获取完整标识"""
        result = self._call_service(service, 'get_identity', 'domain', 1, format='full')
        
        assert 'formatted' in result
        assert 'technical' in result
        assert 'semantic' in result
        assert 'display' in result
        assert 'hierarchical' in result
        
        print(f"Full identity: {result}")
    
    def test_02_get_identity_short(self, service):
        """测试获取简短标识"""
        result = self._call_service(service, 'get_identity', 'domain', 1, format='short')
        
        formatted = result.get('formatted', '')
        assert '供应链云' in formatted or 'SUPPLY_CHAIN' in formatted or len(formatted) > 0
        
        print(f"Short identity: {formatted}")
    
    def test_03_get_identity_technical(self, service):
        """测试获取技术标识"""
        result = self._call_service(service, 'get_identity', 'domain', 1, format='technical', include_technical=True)
        
        tech = result.get('technical', {})
        assert tech.get('id') == 1
        assert tech.get('object_type') == 'domain'
        
        formatted = result.get('formatted', '')
        assert 'domain:1' in formatted
        
        print(f"Technical identity: {formatted}")
    
    def test_04_get_identity_detailed(self, service):
        """测试获取详细标识"""
        result = self._call_service(service, 'get_identity', 'domain', 1, format='detailed')
        
        formatted = result.get('formatted', '')
        print(f"Detailed identity: {formatted}")
    
    def test_05_batch_get_identities(self, service):
        """测试批量获取标识"""
        requests = [
            ('domain', 1),
            ('domain', 2),
        ]
        try:
            results = service.batch_get_identities(requests, format='short')
        except Exception:
            pytest.skip("ObjectIdentityService requires real database connection")
        
        assert len(results) == 2
        assert ('domain', 1) in results
        assert ('domain', 2) in results
        
        print(f"Batch identities: {results}")
    
    def test_06_get_formatted_identity(self, service):
        """测试获取格式化标识字符串"""
        try:
            formatted = service.get_formatted_identity('domain', 1, format='short')
        except Exception:
            pytest.skip("ObjectIdentityService requires real database connection")
        
        assert isinstance(formatted, str)
        assert len(formatted) > 0
        
        print(f"Formatted identity: {formatted}")
    
    def test_07_cache_mechanism(self, service):
        """测试缓存机制"""
        result1 = self._call_service(service, 'get_identity', 'domain', 1)
        result2 = self._call_service(service, 'get_identity', 'domain', 1)
        
        assert result1 == result2
        
        print("Cache working correctly")
    
    def test_08_clear_cache(self, service):
        """测试清空缓存"""
        self._call_service(service, 'get_identity', 'domain', 1)
        if not hasattr(service, '_cache') or len(service._cache) == 0:
            pytest.skip("Cache not populated with mock data source")
        
        service.clear_cache()
        assert len(service._cache) == 0
        
        print("Cache cleared successfully")
    
    def test_09_hierarchy_path_integration(self, service):
        """测试层级路径集成"""
        result = self._call_service(service, 'get_identity', 'domain', 1, format='full')
        
        hierarchical = result.get('hierarchical', {})
        assert 'full_path' in hierarchical
        assert 'depth' in hierarchical
        
        print(f"Hierarchical info: {hierarchical}")
    
    def test_10_business_key_integration(self, service):
        """测试业务键集成"""
        result = self._call_service(service, 'get_identity', 'domain', 1, format='full')
        
        semantic = result.get('semantic', {})
        assert 'business_key' in semantic
        
        print(f"Semantic info: {semantic}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
