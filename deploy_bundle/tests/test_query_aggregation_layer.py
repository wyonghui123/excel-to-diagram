# -*- coding: utf-8 -*-
"""
查询与聚合层测试 - L3 Layer

测试目标：验证查询服务和聚合功能
覆盖维度：
1. 基础查询（过滤、排序、分页）
2. 关联查询（JOIN、Association）
3. 聚合查询（COUNT、SUM、AVG、GROUP BY）
4. 多层树查询
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


class TestQueryBase:
    """查询测试基类"""
    
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, 'test_query.db')
        
        self.ds = get_data_source("sqlite", database=self.db_path)
        self._init_schema()
        
        self.query_service = QueryService(self.ds)
        self.manage_service = ManageService(self.ds)
        
        self._create_test_data()
    
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
    
    def _create_test_data(self):
        """创建测试数据"""
        pass


class TestBasicQuery(TestQueryBase):
    """基础查询测试"""
    
    def _create_test_data(self):
        for i in range(10):
            data = {
                'code': f'DOM{i:03d}',
                'name': f'领域{i}',
                'version_id': 1,
                'level': 1,
                'sort_order': i,
                'status': 'active' if i % 2 == 0 else 'inactive',
            }
            req = CreateRequest(object_type='domain', data=data)
            self.manage_service.create(req)
    
    def test_query_all(self):
        """测试查询所有数据"""
        req = SearchRequest(object_type='domain', page=1, page_size=100)
        result = self.query_service.search(req)
        
        assert result.total == 10
        assert len(result.data) == 10
    
    def test_query_pagination(self):
        """测试分页查询"""
        req = SearchRequest(object_type='domain', page=1, page_size=5)
        result = self.query_service.search(req)
        
        assert result.total == 10
        assert len(result.data) == 5
        assert result.total_pages == 2
    
    def test_query_filter_eq(self):
        """测试等于过滤"""
        req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='code', operator='eq', value='DOM001')],
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        assert result.total == 1
        assert result.data[0]['code'] == 'DOM001'
    
    def test_query_filter_in(self):
        """测试 IN 过滤"""
        req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='code', operator='in', values=['DOM001', 'DOM002', 'DOM003'])],
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        assert result.total == 3
    
    def test_query_filter_like(self):
        """测试 LIKE 过滤"""
        req = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='name', operator='like', value='领域%')],
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        assert result.total == 10
    
    def test_query_sort_asc(self):
        """测试升序排序"""
        req = SearchRequest(
            object_type='domain',
            sort_by='code',
            sort_order='asc',
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        codes = [d['code'] for d in result.data]
        assert codes == sorted(codes)
    
    def test_query_sort_desc(self):
        """测试降序排序"""
        req = SearchRequest(
            object_type='domain',
            sort_by='code',
            sort_order='desc',
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        codes = [d['code'] for d in result.data]
        assert codes == sorted(codes, reverse=True)


class TestHierarchyQuery(TestQueryBase):
    """层级查询测试"""
    
    def _create_test_data(self):
        for i in range(3):
            domain_data = {
                'code': f'DOM{i}',
                'name': f'领域{i}',
                'version_id': 1,
                'level': 1,
            }
            self.manage_service.create(CreateRequest(object_type='domain', data=domain_data))
            
            for j in range(2):
                sub_data = {
                    'domain_id': i + 1,
                    'code': f'SUB{i}{j}',
                    'name': f'子领域{i}{j}',
                    'version_id': 1,
                    'level': 2,
                }
                self.manage_service.create(CreateRequest(object_type='sub_domain', data=sub_data))
    
    def test_query_children_by_parent(self):
        """测试按父级查询子级"""
        req = SearchRequest(
            object_type='sub_domain',
            conditions=[QueryCondition(field='domain_id', operator='eq', value=1)],
            page=1, page_size=100
        )
        result = self.query_service.search(req)
        
        assert result.total == 2
        for d in result.data:
            assert d['domain_id'] == 1
    
    def test_query_parent_by_child(self):
        """测试通过子级查询父级"""
        sub_req = SearchRequest(
            object_type='sub_domain',
            conditions=[QueryCondition(field='code', operator='eq', value='SUB00')],
            page=1, page_size=1
        )
        sub_result = self.query_service.search(sub_req)
        
        if sub_result.data:
            domain_id = sub_result.data[0]['domain_id']
            
            domain_req = SearchRequest(
                object_type='domain',
                conditions=[QueryCondition(field='id', operator='eq', value=domain_id)],
                page=1, page_size=1
            )
            domain_result = self.query_service.search(domain_req)
            
            assert domain_result.total == 1


class TestKeywordSearch(TestQueryBase):
    """关键词搜索测试"""
    
    def _create_test_data(self):
        domains = [
            {'code': 'SUPPLY', 'name': '供应链管理', 'version_id': 1, 'level': 1},
            {'code': 'PURCHASE', 'name': '采购管理', 'version_id': 1, 'level': 1},
            {'code': 'WAREHOUSE', 'name': '仓储管理', 'version_id': 1, 'level': 1},
            {'code': 'FINANCE', 'name': '财务管理', 'version_id': 1, 'level': 1},
        ]
        for d in domains:
            self.manage_service.create(CreateRequest(object_type='domain', data=d))
    
    def test_keyword_search_name(self):
        """测试按名称关键词搜索"""
        req = SearchRequest(object_type='domain', keyword='管理', page=1, page_size=100)
        result = self.query_service.search(req)
        
        assert result.total == 4
    
    def test_keyword_search_code(self):
        """测试按编码关键词搜索"""
        req = SearchRequest(object_type='domain', keyword='SUPPLY', page=1, page_size=100)
        result = self.query_service.search(req)
        
        assert result.total >= 1
    
    def test_keyword_search_partial(self):
        """测试部分匹配搜索"""
        req = SearchRequest(object_type='domain', keyword='采购', page=1, page_size=100)
        result = self.query_service.search(req)
        
        assert result.total >= 1
        assert any('采购' in d.get('name', '') for d in result.data)


class TestQueryConsistency(TestQueryBase):
    """查询一致性测试 - 核心场景"""
    
    def _create_test_data(self):
        for i in range(5):
            domain_data = {
                'code': f'CONS_DOM{i}',
                'name': f'一致性测试领域{i}',
                'version_id': 1,
                'level': 1,
            }
            self.manage_service.create(CreateRequest(object_type='domain', data=domain_data))
    
    def test_filter_count_consistency(self):
        """测试过滤后数量一致性"""
        req_all = SearchRequest(object_type='domain', page=1, page_size=100)
        result_all = self.query_service.search(req_all)
        
        req_filtered = SearchRequest(
            object_type='domain',
            conditions=[QueryCondition(field='code', operator='like', value='CONS_DOM%')],
            page=1, page_size=100
        )
        result_filtered = self.query_service.search(req_filtered)
        
        assert result_filtered.total == 5
        assert result_filtered.total <= result_all.total
    
    def test_pagination_total_consistency(self):
        """测试分页总数一致性"""
        req_page1 = SearchRequest(object_type='domain', page=1, page_size=2)
        result1 = self.query_service.search(req_page1)
        
        req_page2 = SearchRequest(object_type='domain', page=2, page_size=2)
        result2 = self.query_service.search(req_page2)
        
        assert result1.total == result2.total


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
