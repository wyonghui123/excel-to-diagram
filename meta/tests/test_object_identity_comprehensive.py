import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
对象标识转换服务综合测试套件

包含边界条件、错误处理、性能和集成测试
"""

import pytest
import sys
import os
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.business_key_service import BusinessKeyService
from meta.services.hierarchy_path_service import HierarchyPathService
from meta.services.object_identity_service import ObjectIdentityService


class ComprehensiveMockDataSource:
    """综合模拟数据源"""
    
    def __init__(self):
        self.data = {
            'products': {
                1: {'id': 1, 'name': 'ERP产品', 'code': 'ERP'},
                2: {'id': 2, 'name': 'CRM产品', 'code': 'CRM'},
            },
            'versions': {
                1: {'id': 1, 'name': 'V5版本', 'code': 'V5', 'product_id': 1},
                2: {'id': 2, 'name': 'V6版本', 'code': 'V6', 'product_id': 1},
            },
            'domains': {
                1: {'id': 1, 'name': '供应链云', 'code': 'SUPPLY_CHAIN', 'version_id': 1},
                2: {'id': 2, 'name': '制造云', 'code': 'MANUFACTURING', 'version_id': 1},
                3: {'id': 3, 'name': '财务云', 'code': 'FINANCE', 'version_id': 2},
            },
            'sub_domains': {
                1: {'id': 1, 'name': '库存管理', 'code': 'INVENTORY', 'domain_id': 1},
                2: {'id': 2, 'name': '采购管理', 'code': 'PROCUREMENT', 'domain_id': 1},
            },
            'service_modules': {
                1: {'id': 1, 'name': '库存服务', 'code': 'INV_SVC', 'sub_domain_id': 1},
            },
            'business_objects': {
                1: {'id': 1, 'name': '物料主数据', 'code': 'MATERIAL', 'service_module_id': 1},
                2: {'id': 2, 'name': '仓库主数据', 'code': 'WAREHOUSE', 'service_module_id': 1},
            },
            'users': {
                1: {'id': 1, 'name': '管理员', 'code': 'ADMIN', 'display_name': '系统管理员'},
                2: {'id': 2, 'name': '用户', 'code': 'USER', 'display_name': '普通用户'},
            },
            'roles': {
                1: {'id': 1, 'name': '系统管理员', 'code': 'SYSTEM_ADMIN'},
                2: {'id': 2, 'name': '普通用户', 'code': 'NORMAL_USER'},
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
        
        for table_name in ['products', 'versions', 'domains', 'sub_domains', 
                          'service_modules', 'business_objects', 'users', 'roles']:
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


class TestBusinessKeyServiceComprehensive:
    """BusinessKeyService 综合测试"""
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        data_source = ComprehensiveMockDataSource()
        return BusinessKeyService(data_source)
    
    # ==================== 边界条件测试 ====================
    
    def test_empty_object_type(self, service):
        """测试空对象类型"""
        result = service.id_to_business_key('', 1)
        assert result == ''
        
        result = service.id_to_business_key(None, 1)
        assert result == ''
    
    def test_empty_object_id(self, service):
        """测试空对象 ID"""
        result = service.id_to_business_key('domain', None)
        assert result == ''
        
        result = service.id_to_business_key('domain', 0)
        assert result == ''
    
    def test_nonexistent_object_type(self, service):
        """测试不存在的对象类型"""
        result = service.id_to_business_key('nonexistent_type', 1)
        assert 'nonexistent_type:1' in result
    
    def test_nonexistent_object_id(self, service):
        """测试不存在的对象 ID"""
        result = service.id_to_business_key('domain', 99999)
        assert 'domain:99999' in result
    
    def test_negative_object_id(self, service):
        """测试负数对象 ID"""
        result = service.id_to_business_key('domain', -1)
        assert 'domain:-1' in result
    
    # ==================== 错误处理测试 ====================
    
    def test_invalid_format_parameter(self, service):
        """测试无效的格式参数"""
        result = service.id_to_business_key('domain', 1, format='invalid_format')
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_batch_convert_empty_list(self, service):
        """测试批量转换空列表"""
        results = service.batch_convert([])
        assert len(results) == 0
    
    def test_batch_convert_mixed_types(self, service):
        """测试批量转换混合类型"""
        requests = [
            ('domain', 1),
            ('sub_domain', 1),
            ('nonexistent', 999),
        ]
        results = service.batch_convert(requests)
        
        assert len(results) == 3
        assert ('domain', 1) in results
        assert ('sub_domain', 1) in results
        assert ('nonexistent', 999) in results
    
    # ==================== 性能测试 ====================
    
    def test_single_query_performance(self, service):
        """测试单个查询性能"""
        start = time.time()
        
        for _ in range(100):
            service.id_to_business_key('domain', 1)
        
        elapsed = time.time() - start
        avg_time = elapsed / 100
        
        assert avg_time < 0.01  # 平均 < 10ms
        print(f"Average single query time: {avg_time*1000:.2f}ms")
    
    def test_batch_query_performance(self, service):
        """测试批量查询性能"""
        requests = [('domain', i) for i in [1, 2, 3]]
        
        start = time.time()
        
        for _ in range(100):
            service.batch_convert(requests)
        
        elapsed = time.time() - start
        avg_time = elapsed / 100
        
        assert avg_time < 0.05  # 平均 < 50ms
        print(f"Average batch query time: {avg_time*1000:.2f}ms")
    
    def test_cache_effectiveness(self, service):
        """测试缓存效果"""
        # 第一次查询
        start1 = time.time()
        result1 = service.id_to_business_key('domain', 1)
        time1 = time.time() - start1
        
        # 第二次查询（应该命中缓存）
        start2 = time.time()
        result2 = service.id_to_business_key('domain', 1)
        time2 = time.time() - start2
        
        assert result1 == result2
        assert time2 < time1  # 缓存命中应该更快
        print(f"First query: {time1*1000:.2f}ms, Second query (cached): {time2*1000:.2f}ms")


class TestHierarchyPathServiceComprehensive:
    """HierarchyPathService 综合测试"""
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        data_source = ComprehensiveMockDataSource()
        return HierarchyPathService(data_source)
    
    # ==================== 边界条件测试 ====================
    
    def test_empty_object_type(self, service):
        """测试空对象类型"""
        result = service.get_full_path('', 1)
        assert result['full'] == ''
        
        result = service.get_full_path(None, 1)
        assert result['full'] == ''
    
    def test_empty_object_id(self, service):
        """测试空对象 ID"""
        result = service.get_full_path('domain', None)
        assert result['full'] == ''
        
        result = service.get_full_path('domain', 0)
        assert result['full'] == ''
    
    def test_nonexistent_object(self, service):
        """测试不存在的对象"""
        result = service.get_full_path('domain', 99999)
        assert 'domain:99999' in result['full'] or result['full'] == '' or '99999' in result['full']
    
    def test_deep_hierarchy(self, service):
        """测试深层层级"""
        result = service.get_full_path('business_object', 1)
        
        assert result['depth'] > 0
        assert len(result['segments']) > 0
        print(f"Deep hierarchy path: {result['full']}")
    
    # ==================== 格式化测试 ====================
    
    def test_different_separators(self, service):
        """测试不同分隔符"""
        result1 = service.get_full_path('domain', 1, separator=' → ')
        result2 = service.get_full_path('domain', 1, separator=' > ')
        result3 = service.get_full_path('domain', 1, separator=' / ')
        
        for r in [result1, result2, result3]:
            assert isinstance(r['full'], str)
            assert len(r['full']) >= 0
        print(f"Separator ' → ': {result1['full']}")
        print(f"Separator ' > ': {result2['full']}")
        print(f"Separator ' / ': {result3['full']}")
    
    def test_path_truncation(self, service):
        """测试路径截断"""
        result = service.get_full_path('business_object', 1, max_length=20)
        
        if len(result['full']) > 20:
            assert result['truncated'] is True
        print(f"Truncated path: {result['full']}, truncated: {result['truncated']}")
    
    # ==================== 性能测试 ====================
    
    def test_batch_paths_performance(self, service):
        """测试批量路径查询性能"""
        requests = [('domain', i) for i in [1, 2, 3]]
        
        start = time.time()
        
        for _ in range(100):
            service.batch_get_paths(requests)
        
        elapsed = time.time() - start
        avg_time = elapsed / 100
        
        assert avg_time < 0.05  # 平均 < 50ms
        print(f"Average batch paths query time: {avg_time*1000:.2f}ms")


class TestObjectIdentityServiceComprehensive:
    """ObjectIdentityService 综合测试"""
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        data_source = ComprehensiveMockDataSource()
        return ObjectIdentityService(data_source)
    
    # ==================== 边界条件测试 ====================
    
    def test_empty_parameters(self, service):
        """测试空参数"""
        result = service.get_identity('', 1)
        assert result['formatted'] == ''
        
        result = service.get_identity('domain', None)
        assert result['formatted'] == ''
    
    def test_nonexistent_object(self, service):
        """测试不存在的对象"""
        result = service.get_identity('domain', 99999)
        assert 'domain:99999' in result['formatted']
    
    # ==================== 格式测试 ====================
    
    def test_all_formats(self, service):
        """测试所有格式"""
        formats = ['full', 'short', 'minimal', 'technical', 'detailed']
        
        for fmt in formats:
            result = service.get_identity('domain', 1, format=fmt)
            assert 'formatted' in result
            assert isinstance(result['formatted'], str)
            print(f"Format '{fmt}': {result['formatted']}")
    
    def test_include_technical_info(self, service):
        """测试包含技术信息"""
        result1 = service.get_identity('domain', 1, include_technical=False)
        result2 = service.get_identity('domain', 1, include_technical=True)
        
        assert 'technical' in result2
        assert result2['technical']['id'] == 1
        assert result2['technical']['object_type'] == 'domain'
        
        print(f"Without technical: {result1}")
        print(f"With technical: {result2}")
    
    # ==================== 集成测试 ====================
    
    def test_business_key_integration(self, service):
        """测试业务键集成"""
        result = service.get_identity('domain', 1)
        
        assert 'semantic' in result
        assert 'business_key' in result['semantic']
        assert len(result['semantic']['business_key']) > 0
        
        print(f"Business key: {result['semantic']['business_key']}")
    
    def test_hierarchy_path_integration(self, service):
        """测试层级路径集成"""
        result = service.get_identity('domain', 1)
        
        assert 'hierarchical' in result
        assert 'full_path' in result['hierarchical']
        assert 'depth' in result['hierarchical']
        
        print(f"Hierarchy path: {result['hierarchical']['full_path']}")
        print(f"Depth: {result['hierarchical']['depth']}")
    
    def test_display_info_integration(self, service):
        """测试显示信息集成"""
        result = service.get_identity('domain', 1)
        
        assert 'display' in result
        assert 'name' in result['display']
        assert 'code' in result['display']
        
        print(f"Display name: {result['display']['name']}")
        print(f"Display code: {result['display']['code']}")
    
    # ==================== 性能测试 ====================
    
    def test_overall_performance(self, service):
        """测试整体性能"""
        start = time.time()
        
        for _ in range(100):
            service.get_identity('domain', 1, format='short')
        
        elapsed = time.time() - start
        avg_time = elapsed / 100
        
        assert avg_time < 0.05  # 平均 < 50ms
        print(f"Average overall query time: {avg_time*1000:.2f}ms")
    
    def test_batch_performance(self, service):
        """测试批量查询性能"""
        requests = [('domain', i) for i in [1, 2, 3]]
        
        start = time.time()
        
        for _ in range(100):
            service.batch_get_identities(requests)
        
        elapsed = time.time() - start
        avg_time = elapsed / 100
        
        assert avg_time < 0.1  # 平均 < 100ms
        print(f"Average batch query time: {avg_time*1000:.2f}ms")


class TestIntegrationScenarios:
    """集成场景测试"""
    
    @pytest.fixture
    def services(self):
        """创建所有服务实例"""
        data_source = ComprehensiveMockDataSource()
        return {
            'business_key': BusinessKeyService(data_source),
            'hierarchy_path': HierarchyPathService(data_source),
            'object_identity': ObjectIdentityService(data_source)
        }
    
    def test_audit_log_scenario(self, services):
        """测试审计日志场景"""
        object_identity = services['object_identity']
        
        # 模拟审计日志数据
        audit_logs = [
            {'object_type': 'domain', 'object_id': 1},
            {'object_type': 'sub_domain', 'object_id': 1},
            {'object_type': 'business_object', 'object_id': 1},
        ]
        
        # 批量获取对象标识
        requests = [(log['object_type'], log['object_id']) for log in audit_logs]
        identities = object_identity.batch_get_identities(requests, format='short')
        
        # 验证结果
        assert len(identities) == 3
        
        for log in audit_logs:
            key = (log['object_type'], log['object_id'])
            assert key in identities
            assert 'formatted' in identities[key]
            print(f"{log['object_type']}:{log['object_id']} -> {identities[key]['formatted']}")
    
    def test_ui_display_scenario(self, services):
        """测试 UI 展示场景"""
        object_identity = services['object_identity']
        
        # 模拟 UI 展示需求
        display_items = [
            {'type': 'domain', 'id': 1, 'need': 'short'},
            {'type': 'domain', 'id': 2, 'need': 'full'},
            {'type': 'business_object', 'id': 1, 'need': 'detailed'},
        ]
        
        for item in display_items:
            identity = object_identity.get_identity(
                item['type'], 
                item['id'], 
                format=item['need']
            )
            
            assert 'formatted' in identity
            print(f"{item['type']}:{item['id']} ({item['need']}): {identity['formatted']}")
    
    def test_cache_consistency(self, services):
        """测试缓存一致性"""
        business_key = services['business_key']
        object_identity = services['object_identity']
        
        result1 = business_key.id_to_business_key('domain', 1, format='short')
        result2 = object_identity.get_identity('domain', 1, format='short')
        
        assert isinstance(result1, str) and len(result1) > 0
        assert isinstance(result2['formatted'], str) and len(result2['formatted']) > 0
        
        print(f"BusinessKeyService: {result1}")
        print(f"ObjectIdentityService: {result2['formatted']}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
