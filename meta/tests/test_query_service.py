import pytest

pytestmark = pytest.mark.integration

import pytest
from unittest.mock import MagicMock, patch
from meta.services.query_service import (
    QueryService,
    SearchRequest,
    SearchResult,
)
from meta.core.models import registry, FieldStorage
from meta.core.redundancy_registry import redundancy_registry


@pytest.fixture(autouse=True)
def setup_registry():
    """确保 redundancy_registry 已构建"""
    if not redundancy_registry.is_built():
        redundancy_registry.build_from_registry()


@pytest.fixture
def mock_datasource():
    ds = MagicMock()
    ds.query.return_value = []
    return ds


@pytest.fixture
def query_service(mock_datasource):
    return QueryService(mock_datasource)


class TestVirtualFieldSortJoinBuilding:
    """测试虚拟字段 JOIN 排序构建"""

    def test_build_join_for_domain_name(self, query_service):
        """测试 domain_name 虚拟字段的 JOIN 构建"""
        meta_obj = registry.get('service_module')
        
        result = query_service._build_virtual_field_order_join(
            meta_obj, 'domain_name', 'asc'
        )
        
        assert result is not None
        join_clause, order_alias, direction = result
        
        assert 'LEFT JOIN' in join_clause
        assert 'sub_domains' in join_clause
        assert 'domains' in join_clause
        assert order_alias == '_j2.name'
        assert direction == 'asc'

    def test_build_join_for_sub_domain_name(self, query_service):
        """测试 sub_domain_name 虚拟字段的 JOIN 构建"""
        meta_obj = registry.get('service_module')
        
        result = query_service._build_virtual_field_order_join(
            meta_obj, 'sub_domain_name', 'asc'
        )
        
        assert result is not None
        join_clause, order_alias, direction = result
        
        assert 'LEFT JOIN' in join_clause
        assert 'sub_domains' in join_clause
        assert order_alias == '_j1.name'

    def test_physical_field_returns_none(self, query_service):
        """测试物理字段返回 None（不需要 JOIN）"""
        meta_obj = registry.get('service_module')
        
        result = query_service._build_virtual_field_order_join(
            meta_obj, 'name', 'asc'
        )
        
        assert result is None

    def test_unknown_field_returns_none(self, query_service):
        """测试未知字段返回 None"""
        meta_obj = registry.get('service_module')
        
        result = query_service._build_virtual_field_order_join(
            meta_obj, 'unknown_field', 'asc'
        )
        
        assert result is None

    def test_desc_direction_preserved(self, query_service):
        """测试降序方向被保留"""
        meta_obj = registry.get('service_module')
        
        result = query_service._build_virtual_field_order_join(
            meta_obj, 'domain_name', 'desc'
        )
        
        assert result is not None
        _, _, direction = result
        assert direction == 'desc'


class TestVirtualFieldSortBusinessObject:
    """测试 business_object 的虚拟字段排序"""

    def test_build_join_for_bo_domain_name(self, query_service):
        """测试 business_object.domain_name 的 JOIN 构建（2步 JOIN）"""
        meta_obj = registry.get('business_object')
        
        result = query_service._build_virtual_field_order_join(
            meta_obj, 'domain_name', 'asc'
        )
        
        assert result is not None
        join_clause, order_alias, _ = result
        
        assert 'service_modules' in join_clause
        assert 'sub_domains' in join_clause
        assert 'domains' in join_clause
        assert order_alias == '_j3.name'

    def test_build_join_for_bo_domain_id(self, query_service):
        """测试 business_object.domain_id 的 JOIN 构建"""
        meta_obj = registry.get('business_object')
        
        result = query_service._build_virtual_field_order_join(
            meta_obj, 'domain_id', 'asc'
        )
        
        assert result is not None
        join_clause, order_alias, _ = result
        
        assert order_alias == '_j2.domain_id'


class TestVirtualFieldSortIntegration:
    """集成测试：完整查询流程"""

    def test_search_with_virtual_field_sort(self, query_service, mock_datasource):
        """测试带虚拟字段排序的完整搜索"""
        mock_datasource.query.return_value = [
            {'id': 1, 'name': 'A', 'domain_name': 'Alpha'},
            {'id': 2, 'name': 'B', 'domain_name': 'Beta'},
        ]
        
        request = SearchRequest(
            object_type='service_module',
            sort_by='domain_name',
            sort_order='asc',
            page=1,
            page_size=10,
        )
        
        result = query_service.search(request)
        
        assert isinstance(result, SearchResult)
        assert result.page == 1
        assert result.page_size == 10

    def test_search_with_physical_field_sort(self, query_service, mock_datasource):
        """测试物理字段排序走标准路径"""
        mock_datasource.query.return_value = [
            {'id': 1, 'name': 'Alpha'},
            {'id': 2, 'name': 'Beta'},
        ]
        
        request = SearchRequest(
            object_type='service_module',
            sort_by='name',
            sort_order='asc',
            page=1,
            page_size=10,
        )
        
        result = query_service.search(request)
        
        assert isinstance(result, SearchResult)

    def test_search_without_sort(self, query_service, mock_datasource):
        """测试无排序的查询"""
        mock_datasource.query.return_value = [
            {'id': 1, 'name': 'Test'},
        ]
        
        request = SearchRequest(
            object_type='service_module',
            page=1,
            page_size=10,
        )
        
        result = query_service.search(request)
        
        assert isinstance(result, SearchResult)


class TestVirtualFieldSortEdgeCases:
    """边界情况测试"""

    def test_object_without_virtual_fields(self, query_service):
        """测试没有虚拟字段的对象"""
        meta_obj = registry.get('product')
        
        result = query_service._build_virtual_field_order_join(
            meta_obj, 'name', 'asc'
        )
        
        assert result is None

    def test_virtual_field_without_join_path(self, query_service):
        """测试没有 join_path 的虚拟字段（如果存在）"""
        meta_obj = registry.get('service_module')
        assert meta_obj is not None, "meta_obj not found in registry"
        
        found_virtual_without_join = False
        for f in meta_obj.fields:
            if getattr(f, 'storage', None) == FieldStorage.VIRTUAL:
                from meta.core.redundancy_registry import redundancy_registry
                red_def = redundancy_registry.get_redundancy('service_module', f.id)
                if not red_def or not red_def.join_path:
                    found_virtual_without_join = True
                    result = query_service._build_virtual_field_order_join(
                        meta_obj, f.id, 'asc'
                    )
                    assert result is None
                    break
        
        if not found_virtual_without_join:
            pytest.fail("No virtual field without join_path found")

    def test_join_failure_fallback(self, query_service, mock_datasource):
        """测试 JOIN 失败时回退到标准查询"""
        mock_datasource.query.side_effect = Exception('JOIN failed')
        
        request = SearchRequest(
            object_type='service_module',
            sort_by='domain_name',
            sort_order='asc',
            page=1,
            page_size=10,
        )
        
        result = query_service.search(request)
        
        assert isinstance(result, SearchResult)


class TestSearchRequestOrderBy:
    """测试 SearchRequest 的排序参数处理"""

    def test_order_by_direct(self):
        """测试直接指定 order_by"""
        request = SearchRequest(
            object_type='test',
            order_by='name desc',
        )
        
        assert request.get_order_by_clause() == 'name desc'

    def test_sort_by_and_sort_order(self):
        """测试分开指定 sort_by 和 sort_order"""
        request = SearchRequest(
            object_type='test',
            sort_by='name',
            sort_order='asc',
        )
        
        assert request.get_order_by_clause() == 'name asc'

    def test_sort_order_defaults_to_asc(self):
        """测试 sort_order 默认为 asc"""
        request = SearchRequest(
            object_type='test',
            sort_by='name',
        )
        
        assert request.get_order_by_clause() == 'name asc'

    def test_invalid_sort_order_corrected(self):
        """测试无效的 sort_order 被修正"""
        request = SearchRequest(
            object_type='test',
            sort_by='name',
            sort_order='invalid',
        )
        
        assert request.get_order_by_clause() == 'name asc'

    def test_empty_order_by(self):
        """测试空的排序参数"""
        request = SearchRequest(object_type='test')
        
        assert request.get_order_by_clause() == ''

    def test_order_by_takes_precedence(self):
        """测试 order_by 优先于 sort_by"""
        request = SearchRequest(
            object_type='test',
            order_by='code desc',
            sort_by='name',
            sort_order='asc',
        )
        
        assert request.get_order_by_clause() == 'code desc'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
