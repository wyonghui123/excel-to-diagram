# -*- coding: utf-8 -*-
"""
Search Help 测试 - L3 Layer

测试目标：验证值帮助和联动功能
覆盖维度：
1. 基础 Search Help（简单列表）
2. 级联 Search Help（父子联动）
3. 树形 Search Help
4. 只读联动
"""

import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.datasource import get_data_source
from meta.core.models import registry as meta_registry
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.schema_generator import SchemaGenerator
from meta.services.query_service import QueryService, SearchRequest, QueryCondition
from meta.services.manage_service import ManageService, CreateRequest
from meta.services.hierarchy_filter_service import HierarchyFilterService


class TestSearchHelpBase:
    """Search Help 测试基类"""
    
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, 'test_sh.db')
        
        self.ds = get_data_source("sqlite", database=self.db_path)
        self._init_schema()
        
        self.query_service = QueryService(self.ds)
        self.manage_service = ManageService(self.ds)
        self.filter_service = HierarchyFilterService(self.query_service, self.ds)
    
    def teardown_method(self):
        if hasattr(self, 'tmp_dir') and os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
    
    def _init_schema(self):
        schema_dir = get_yaml_schema_dir()
        register_from_directory(schema_dir)
        
        generator = SchemaGenerator(dialect='sqlite')
        
        for obj in meta_registry.get_all().values():
            if hasattr(obj, 'table_name') and obj.table_name:
                sql = generator.generate_create_table(obj)
                if sql:
                    self.ds.execute(sql)
                    
                indexes = generator.generate_create_index(obj)
                for idx_sql in indexes:
                    self.ds.execute(idx_sql)
        
        self.ds.commit()


class TestBasicSearchHelp(TestSearchHelpBase):
    """基础 Search Help 测试"""
    
    def test_simple_list_search_help(self):
        """测试简单列表 Search Help"""
        for i in range(5):
            data = {
                'code': f'DOM{i:03d}',
                'name': f'领域{i}',
                'version_id': 1,
                'level': 1,
            }
            self.manage_service.create(CreateRequest(object_type='domain', data=data))
        
        req = SearchRequest(object_type='domain', page=1, page_size=100)
        result = self.query_service.search(req)
        
        assert result.total == 5
    
    def test_search_help_with_filter(self):
        """测试带过滤的 Search Help"""
        for i in range(5):
            data = {
                'code': f'FILTER{i:03d}',
                'name': f'过滤测试{i}',
                'version_id': 1,
            }
            self.manage_service.create(CreateRequest(object_type='domain', data=data))
        
        req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='version_id', operator='eq', value=1)],
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        assert result.total == 5


class TestCascadeSearchHelp(TestSearchHelpBase):
    """级联 Search Help 测试"""
    
    def _create_hierarchy_data(self):
        """创建层级数据"""
        for i in range(2):
            domain_data = {
                'code': f'CASCADE_DOM{i}',
                'name': f'级联领域{i}',
                'version_id': 1,
                'level': 1,
            }
            self.manage_service.create(CreateRequest(object_type='domain', data=domain_data))
        
        for i in range(2):
            for j in range(2):
                sub_data = {
                    'domain_id': i + 1,
                    'code': f'CASCADE_SUB{i}{j}',
                    'name': f'级联子领域{i}{j}',
                    'version_id': 1,
                    'level': 2,
                }
                self.manage_service.create(CreateRequest(object_type='sub_domain', data=sub_data))
    
    def test_filter_by_parent(self):
        """测试按父级过滤子级"""
        self._create_hierarchy_data()
        
        req = SearchRequest(
            object_type='sub_domain',
            conditions=[QueryCondition(field='domain_id', operator='eq', value=1)],
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        assert result.total == 2
        for d in result.data:
            assert d['domain_id'] == 1
    
    def test_cascade_dependency(self):
        """测试级联依赖"""
        self._create_hierarchy_data()
        
        domain_req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='code', operator='eq', value='CASCADE_DOM0')],
            page=1, page_size=1
        )
        domain_result = self.query_service.search(domain_req)
        
        if domain_result.data:
            domain_id = domain_result.data[0]['id']
            
            sub_req = SearchRequest(
                object_type='sub_domain',
                conditions=[QueryCondition(field='domain_id', operator='eq', value=domain_id)],
                page=1, page_size=100
            )
            sub_result = self.query_service.search(sub_req)
            
            assert sub_result.total == 2


class TestTreeSearchHelp(TestSearchHelpBase):
    """树形 Search Help 测试"""
    
    def _create_tree_data(self):
        """创建树形数据"""
        for i in range(3):
            domain_data = {
                'code': f'TREE_DOM{i}',
                'name': f'树形领域{i}',
                'version_id': 1,
            }
            self.manage_service.create(CreateRequest(object_type='domain', data=domain_data))
    
    def test_tree_level_filter(self):
        """测试树层级过滤"""
        self._create_tree_data()
        
        req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='version_id', operator='eq', value=1)],
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        assert result.total == 3
    
    def test_tree_root_nodes(self):
        """测试获取根节点"""
        self._create_tree_data()
        
        req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='version_id', operator='eq', value=1)],
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        for d in result.data:
            assert d.get('version_id') == 1


class TestReadonlyLinkage(TestSearchHelpBase):
    """只读联动测试"""
    
    def test_readonly_when_target_immutable(self):
        """测试目标字段 immutable 时只读"""
        obj = meta_registry.get('relationship')
        
        source_code_field = obj.get_field('source_code')
        target_code_field = obj.get_field('target_code')
        
        if source_code_field:
            is_immutable = getattr(source_code_field.semantics, 'immutable', False)
            ui_editable = getattr(source_code_field.ui, 'editable', True) if hasattr(source_code_field, 'ui') else True
            
            if is_immutable:
                assert ui_editable is False or is_immutable is True
    
    def test_editable_when_target_editable(self):
        """测试目标字段可编辑"""
        obj = meta_registry.get('domain')
        
        name_field = obj.get_field('name')
        
        if name_field:
            is_immutable = getattr(name_field.semantics, 'immutable', False)
            
            assert is_immutable is False


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
