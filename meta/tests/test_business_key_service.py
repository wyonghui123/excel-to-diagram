import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
BusinessKeyService 单元测试
"""

import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.business_key_service import BusinessKeyService
from meta.core.yaml_loader import registry


class MockDataSource:
    """模拟数据源"""
    
    def __init__(self):
        self.data = {
            'domains': {
                1: {'id': 1, 'name': '供应链云', 'code': 'SUPPLY_CHAIN'},
                2: {'id': 2, 'name': '制造云', 'code': 'MANUFACTURING'},
            },
            'sub_domains': {
                1: {'id': 1, 'name': '库存管理', 'code': 'INVENTORY', 'domain_id': 1},
            },
            'business_objects': {
                1: {'id': 1, 'name': '物料主数据', 'code': 'MATERIAL', 'service_module_id': 1},
            }
        }
    
    def execute(self, sql, params=None):
        """执行 SQL"""
        class MockCursor:
            def __init__(self, data):
                self.data = data
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
                    return [(f'col{i}',) for i in range(len(self.data[0]))]
                return []
        
        params = params or ()
        
        if 'domains' in sql and params:
            domain_id = params[0] if params else None
            if domain_id in self.data['domains']:
                row = self.data['domains'][domain_id]
                return MockCursor([tuple(row.values())])
        
        if 'sub_domains' in sql and params:
            sub_domain_id = params[0] if params else None
            if sub_domain_id in self.data['sub_domains']:
                row = self.data['sub_domains'][sub_domain_id]
                return MockCursor([tuple(row.values())])
        
        if 'business_objects' in sql and params:
            bo_id = params[0] if params else None
            if bo_id in self.data['business_objects']:
                row = self.data['business_objects'][bo_id]
                return MockCursor([tuple(row.values())])
        
        return MockCursor([])


class TestBusinessKeyService:
    """BusinessKeyService 测试"""
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        data_source = MockDataSource()
        return BusinessKeyService(data_source)
    
    def test_01_id_to_business_key_domain(self, service):
        """测试领域对象转换"""
        result = service.id_to_business_key('domain', 1, format='short')
        assert '供应链云' in result or 'SUPPLY_CHAIN' in result
        print(f"Domain business key: {result}")
    
    def test_02_id_to_business_key_minimal(self, service):
        """测试最小格式"""
        result = service.id_to_business_key('domain', 1, format='minimal')
        assert result in ['SUPPLY_CHAIN', '供应链云']
        print(f"Minimal business key: {result}")
    
    def test_03_batch_convert(self, service):
        """测试批量转换"""
        requests = [
            ('domain', 1),
            ('domain', 2),
        ]
        results = service.batch_convert(requests, format='short')
        
        assert len(results) == 2
        assert ('domain', 1) in results
        assert ('domain', 2) in results
        print(f"Batch results: {results}")
    
    def test_04_cache_mechanism(self, service):
        """测试缓存机制"""
        result1 = service.id_to_business_key('domain', 1)
        result2 = service.id_to_business_key('domain', 1)
        
        assert result1 == result2
        assert 'domain:1:full' in service._cache
        print(f"Cache working: {result1}")
    
    def test_05_clear_cache(self, service):
        """测试清空缓存"""
        service.id_to_business_key('domain', 1)
        assert len(service._cache) > 0
        
        service.clear_cache()
        assert len(service._cache) == 0
        print("Cache cleared successfully")
    
    def test_06_nonexistent_object(self, service):
        """测试不存在的对象"""
        result = service.id_to_business_key('domain', 999)
        assert 'domain:999' in result
        print(f"Nonexistent object: {result}")
    
    def test_07_metadata_driven(self, service):
        """测试元数据驱动"""
        meta_obj = registry.get('domain')
        assert meta_obj is not None
        
        bk_fields = [
            f for f in meta_obj.fields 
            if f.semantics and f.semantics.business_key
        ]
        assert len(bk_fields) > 0
        print(f"Business key fields: {[f.id for f in bk_fields]}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
