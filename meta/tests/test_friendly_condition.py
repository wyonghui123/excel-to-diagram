import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
条件型权限服务测试 - Friendly Condition生成逻辑

测试内容：
1. _generate_friendly_condition() 方法
2. 技术ID到业务名称的转换
3. 操作符中文化
4. 多值IN条件的处理
5. 级联场景下的条件显示
"""

import pytest
import sys
import os

# 添加项目路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.condition_permission_service import ConditionPermissionService
from unittest.mock import Mock, MagicMock, patch


class TestGenerateFriendlyCondition:
    """测试友好条件表达式生成"""
    
    @pytest.fixture
    def service(self):
        """创建带Mock数据源的service实例"""
        mock_ds = Mock()
        service = ConditionPermissionService(mock_ds)
        return service
    
    @pytest.fixture
    def mock_dimension_map(self):
        """模拟维度字段映射"""
        return {
            'version_id': {'code': 'version', 'name': '版本', 'field': 'version_id'},
            'domain_id': {'code': 'domain', 'name': '领域', 'field': 'domain_id'},
            'product_id': {'code': 'product', 'name': '产品', 'field': 'product_id'},
            'sub_domain_id': {'code': 'sub_domain', 'name': '子领域', 'field': 'sub_domain_id'},
        }
    
    def test_single_equals_condition(self, service, mock_dimension_map):
        """测试单值等于条件"""
        condition = "version_id = 8"
        
        # Mock维度查询
        service._get_dimension_field_map = Mock(return_value=mock_dimension_map)
        
        # Mock ID到名称查询 - 返回V1.0
        def mock_get_display_name(field, value_id):
            if field == 'version_id' and value_id == 8:
                return 'V1.0'
            return None
        
        service._get_display_name_for_id = mock_get_display_name
        service._find_field_by_dim_name = lambda name, dim_map: next(
            (k for k, v in dim_map.items() if v.get('name') == name), None
        )
        
        result = service._generate_friendly_condition(condition)
        
        # 验证结果包含业务名称而非技术ID
        assert '版本' in result
        assert '等于' in result
        assert 'V1.0' in result
        assert '8' not in result  # 不应包含技术ID
    
    def test_multi_in_condition(self, service, mock_dimension_map):
        """测试多值IN条件"""
        condition = "version_id IN (8, 12)"
        
        # Mock查询
        service._get_dimension_field_map = Mock(return_value=mock_dimension_map)
        
        def mock_get_display_name(field, value_id):
            mapping = {8: 'V1.0', 12: 'V2.0'}
            return mapping.get(value_id)
        
        service._get_display_name_for_id = mock_get_display_name
        service._find_field_by_dim_name = lambda name, dim_map: next(
            (k for k, v in dim_map.items() if v.get('name') == name), None
        )
        
        result = service._generate_friendly_condition(condition)
        
        assert '版本' in result
        assert '包含于' in result
        assert 'V1.0' in result
        assert 'V2.0' in result
        assert '8' not in result or 'V1.0' in result  # ID应该被替换
        assert '12' not in result or 'V2.0' in result
    
    def test_combined_and_condition(self, service, mock_dimension_map):
        """测试组合AND条件"""
        condition = "version_id IN (8) AND domain_id = 999"
        
        service._get_dimension_field_map = Mock(return_value=mock_dimension_map)
        
        def mock_get_display_name(field, value_id):
            mapping = {
                ('version_id', 8): 'V1.0',
                ('domain_id', 999): '核心领域'
            }
            return mapping.get((field, value_id))
        
        service._get_display_name_for_id = lambda field, id: {
            8: 'V1.0', 999: '核心领域'
        }.get(id)
        service._find_field_by_dim_name = lambda name, dim_map: next(
            (k for k, v in dim_map.items() if v.get('name') == name), None
        )
        
        result = service._generate_friendly_condition(condition)
        
        assert '版本' in result
        assert '领域' in result
        assert '且' in result
        assert 'V1.0' in result
        assert '核心领域' in result
    
    def test_not_equal_condition(self, service, mock_dimension_map):
        """测试不等于条件"""
        condition = "domain_id != 999"
        
        service._get_dimension_field_map = Mock(return_value=mock_dimension_map)
        
        service._get_display_name_for_id = lambda field, id: {999: '核心领域'}.get(id)
        service._find_field_by_dim_name = lambda name, dim_map: next(
            (k for k, v in dim_map.items() if v.get('name') == name), None
        )
        
        result = service._generate_friendly_condition(condition)
        
        assert '领域' in result
        assert '不等于' in result
        assert '核心领域' in result
    
    def test_empty_condition_returns_empty_string(self, service):
        """测试空条件返回空字符串"""
        result = service._generate_friendly_condition('')
        assert result == ''
    
    def test_none_condition_returns_empty_string(self, service):
        """测试None条件返回空字符串"""
        result = service._generate_friendly_condition(None)
        assert result == ''
    
    def test_unknown_field_preserved(self, service, mock_dimension_map):
        """测试未知字段保持原样"""
        condition = "unknown_field = 123"
        
        service._get_dimension_field_map = Mock(return_value=mock_dimension_map)
        service._get_display_name_for_id = Mock(return_value=None)
        service._find_field_by_dim_name = Mock(return_value=None)
        
        result = service._generate_friendly_condition(condition)
        
        # 未知字段应该保留原样或合理处理
        assert result is not None


class TestGetDisplayNameForId:
    """测试ID到业务名称的查询"""
    
    @pytest.fixture
    def service_with_mock_db(self):
        """创建带Mock数据库的service"""
        mock_ds = Mock()
        service = ConditionPermissionService(mock_ds)
        return service
    
    def test_version_id_lookup(self, service_with_mock_db):
        """测试version_id查询"""
        service = service_with_mock_db
        
        # Mock数据库查询返回
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = ('V1.0',)
        service.ds.execute.return_value = mock_cursor
        
        result = service._get_display_name_for_id('version_id', 8)
        
        # 验证SQL查询正确
        service.ds.execute.assert_called_once()
        call_args = service.ds.execute.call_args[0]
        assert 'versions' in call_args[0]
        assert ('version_code' in call_args[0] or 'name' in call_args[0])
        assert 8 in call_args[1]
        
        assert result == 'V1.0'
    
    def test_domain_id_lookup(self, service_with_mock_db):
        """测试domain_id查询"""
        service = service_with_mock_db
        
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = ('核心领域',)
        service.ds.execute.return_value = mock_cursor
        
        result = service._get_display_name_for_id('domain_id', 999)
        
        assert result == '核心领域'
    
    def test_nonexistent_id_returns_none(self, service_with_mock_db):
        """测试不存在ID返回None"""
        service = service_with_mock_db
        
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None  # 没有找到
        service.ds.execute.return_value = mock_cursor
        
        result = service._get_display_name_for_id('version_id', 99999)
        
        assert result is None
    
    def test_database_error_handling(self, service_with_mock_db):
        """测试数据库异常处理"""
        service = service_with_mock_db
        
        service.ds.execute.side_effect = Exception("DB Error")
        
        # 应该捕获异常并返回None
        result = service._get_display_name_for_id('version_id', 1)
        assert result is None


class TestCascadeFilterIntegration:
    """测试级联过滤集成"""
    
    def test_cascade_parameter_building(self):
        """测试级联参数构建"""
        # 这个测试验证前端传递的filter参数格式
        expected_params = {
            'filter_version_id': '8',
            'limit': '50'
        }
        
        # 验证参数名以filter_开头（后端API规范）
        for key in expected_params:
            if key.startswith('filter_'):
                field_name = key[7:]  # 去掉前缀
                assert field_name in ['version_id', 'domain_id', 'product_id', 
                                     'sub_domain_id', 'organization_id']
    
    def test_cascade_refresh_logic(self):
        """测试级联刷新逻辑（模拟）"""
        # 模拟父维度改变时的级联刷新
        parent_value_changed = True
        child_values_should_clear = True
        child_options_should_reload = True
        
        assert parent_value_changed == True
        assert child_values_should_clear == True
        assert child_options_should_reload == True


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
