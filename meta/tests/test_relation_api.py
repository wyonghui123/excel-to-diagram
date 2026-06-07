import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
业务关系 API 单元测试
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.datasource import get_data_source
from meta.services.computation_service import computation_service
from meta.api.meta_api import _build_hierarchy_tree, _build_category_tree, _compute_tree_relation_counts
from meta.tests.test_utils import get_test_db_path


class TestRelationCategoryService:
    """关系分类服务测试"""
    
    @pytest.fixture
    def data_source(self):
        return get_data_source("sqlite", database=get_test_db_path())
    
    def test_count_bo_relations(self, data_source):
        """测试业务对象关系数量计算"""
        count = computation_service._count_bo_relations(data_source, 1)
        assert isinstance(count, int)
        assert count >= 0
    
    def test_count_descendant_relations_domain(self, data_source):
        """测试领域下级关系数量计算"""
        count = computation_service._count_descendant_relations(data_source, 'domain', 1)
        assert isinstance(count, int)
        assert count >= 0
    
    def test_batch_count_bo_relations(self, data_source):
        """测试批量计算业务对象关系数量"""
        records = [{'id': 1}, {'id': 2}, {'id': 3}]
        computation_service._batch_count_bo_relations(data_source, records, 'relation_count')
        for record in records:
            assert 'relation_count' in record
            assert isinstance(record['relation_count'], int)


class TestComputationService:
    """统计规则计算服务测试"""
    
    def test_compute_field_count_relations(self):
        """测试计算字段"""
        ds = get_data_source("sqlite", database=get_test_db_path())
        result = computation_service.compute_field(
            ds, 'business_object', 1, 'relation_count',
            {'type': 'count_relations', 'scope': 'self'}
        )
        assert isinstance(result, int)
    
    def test_compute_batch(self):
        """测试批量计算"""
        ds = get_data_source("sqlite", database=get_test_db_path())
        records = [{'id': 1}, {'id': 2}]
        computed_columns = [{'key': 'relation_count', 'computation': {'type': 'count_relations', 'scope': 'self'}}]
        result = computation_service.compute_batch(ds, 'business_object', records, computed_columns)
        for record in result:
            assert 'relation_count' in record


class TestHierarchyTree:
    """业务对象层级树测试"""
    
    def test_build_hierarchy_tree_no_filter(self):
        """测试构建层级树（无版本过滤）"""
        tree = _build_hierarchy_tree(['domain', 'sub_domain', 'service_module', 'business_object'])
        assert isinstance(tree, list)
        if tree:
            assert 'id' in tree[0]
            assert 'name' in tree[0]
            assert 'level' in tree[0]
            assert 'relation_count' in tree[0]
            assert tree[0]['level'] == 'domain'
    
    def test_build_hierarchy_tree_with_version(self):
        """测试构建层级树（带版本过滤）"""
        tree = _build_hierarchy_tree(['domain', 'sub_domain', 'service_module', 'business_object'], version_id=1)
        assert isinstance(tree, list)
        for node in tree:
            assert 'relation_count' in node
    
    def test_hierarchy_tree_relation_count(self):
        """测试层级树关系数量统计"""
        tree = _build_hierarchy_tree(['domain', 'sub_domain', 'service_module', 'business_object'])
        if tree:
            for domain in tree:
                assert domain.get('relation_count', 0) >= 0
                for sd in domain.get('children', []):
                    assert sd.get('relation_count', 0) >= 0


class TestCategoryTree:
    """分类维度树测试"""
    
    def test_build_category_tree_no_filter(self):
        """测试构建分类树（无过滤）"""
        tree = _build_category_tree('relationship')
        assert isinstance(tree, list)
        assert len(tree) > 0
        assert tree[0]['id'] == 'internal'
        assert tree[0]['name'] == '中心范围内'
        assert 'relation_count' in tree[0]
    
    def test_category_tree_structure(self):
        """测试分类树结构"""
        tree = _build_category_tree('relationship')
        if tree:
            scope = tree[0]
            assert 'children' in scope
            if scope['children']:
                category = scope['children'][0]
                assert 'level' in category
                assert category['level'] == 'category_type'
                assert 'relation_count' in category
    
    def test_category_tree_with_business_objects(self):
        """测试分类树（带业务对象过滤）"""
        tree = _build_category_tree('relationship', business_object_ids=[1, 2])
        assert isinstance(tree, list)
        assert tree[0]['id'] == 'internal'


class TestTreeRelationCounts:
    """树节点关系数量统计测试"""
    
    @pytest.fixture
    def data_source(self):
        return get_data_source("sqlite", database=get_test_db_path())
    
    def test_compute_tree_relation_counts(self, data_source):
        """测试批量计算树节点关系数量"""
        counts = _compute_tree_relation_counts(data_source)
        assert isinstance(counts, dict)
    
    def test_compute_tree_relation_counts_with_version(self, data_source):
        """测试带版本过滤的关系数量计算"""
        counts = _compute_tree_relation_counts(data_source, version_id=1)
        assert isinstance(counts, dict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
