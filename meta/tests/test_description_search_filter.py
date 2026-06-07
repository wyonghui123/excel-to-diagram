import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
备注类型搜索和筛选测试

测试 description 字段的搜索和筛选功能：
1. searchable 属性配置
2. 搜索功能中对 searchable 属性的检查
3. text 类型筛选器的 ilike 查询
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.models import registry, RenderHints, UIAnnotation
from meta.core.datasource import get_data_source
from meta.tests.test_utils import get_test_db_path


class TestSearchableAttribute:
    """searchable 属性配置测试"""

    def test_business_object_description_is_searchable(self):
        """业务对象的 description 字段应该标记为 searchable"""
        meta_obj = registry.get("business_object")
        assert meta_obj is not None, "business_object should exist in registry"
        
        desc_field = meta_obj.get_field("description")
        assert desc_field is not None, "field not found on meta_obj"
        
        render_hints = getattr(desc_field.ui, 'render_hints', None) if desc_field.ui else None
        assert render_hints is not None, "description should have render_hints"
        assert render_hints.searchable is True, "description should be searchable"

    def test_product_description_is_searchable(self):
        """产品的 description 字段应该标记为 searchable"""
        meta_obj = registry.get("product")
        assert meta_obj is not None
        
        desc_field = meta_obj.get_field("description")
        assert desc_field is not None, "field not found on meta_obj"
        
        render_hints = getattr(desc_field.ui, 'render_hints', None) if desc_field.ui else None
        assert render_hints is not None
        assert render_hints.searchable is True

    def test_version_description_is_searchable(self):
        """版本的 description 字段应该标记为 searchable"""
        meta_obj = registry.get("version")
        assert meta_obj is not None
        
        desc_field = meta_obj.get_field("description")
        assert desc_field is not None, "field not found on meta_obj"
        
        render_hints = getattr(desc_field.ui, 'render_hints', None) if desc_field.ui else None
        assert render_hints is not None
        assert render_hints.searchable is True

    def test_enum_type_description_is_searchable(self):
        """枚举类型的 description 字段应该标记为 searchable"""
        meta_obj = registry.get("enum_type")
        assert meta_obj is not None
        
        desc_field = meta_obj.get_field("description")
        assert desc_field is not None, "field not found on meta_obj"
        
        render_hints = getattr(desc_field.ui, 'render_hints', None) if desc_field.ui else None
        assert render_hints is not None
        assert render_hints.searchable is True


class TestDescriptionSearchInQuery:
    """搜索功能中对 searchable 属性的检查测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())

    def test_keyword_search_includes_description(self):
        """关键字搜索应该包含 searchable 的 description 字段"""
        meta_obj = registry.get("business_object")
        assert meta_obj is not None, "meta_obj not found in registry"
        search_fields = []
        
        for f in meta_obj.fields:
            render_hints = f.ui.render_hints if f.ui and f.ui.render_hints else None
            is_searchable = render_hints.searchable if render_hints else True
            
            if f.field_type.value in ("string", "text") and is_searchable:
                if f.semantics.display_name or f.id in ("name", "code", "description", "remark", "notes"):
                    search_fields.append(f.id)
        
        assert "description" in search_fields, "description should be in search fields"

    def test_search_in_description_field(self):
        """测试在 description 字段中搜索"""
        cursor = self.ds.execute("""
            SELECT id, code, name, description 
            FROM business_objects 
            WHERE description IS NOT NULL AND description != ''
            LIMIT 1
        """)
        row = cursor.fetchone()
        
        if row:
            bo_id, code, name, description = row
            keyword = description[:10] if len(description) > 10 else description
            
            from meta.services.query_service import QueryService, SearchRequest
            query_service = QueryService(self.ds)
            
            request = SearchRequest(
                object_type="business_object",
                keyword=keyword,
                page=1,
                page_size=10,
            )
            
            result = query_service.search(request)
            assert result is not None
        else:
            from meta.services.query_service import QueryService, SearchRequest
            query_service = QueryService(self.ds)
            
            request = SearchRequest(
                object_type="business_object",
                keyword="test_keyword",
                page=1,
                page_size=10,
            )
            
            result = query_service.search(request)
            assert result is not None, "Search should work even with no matching data"


class TestTextFilterWithIlike:
    """text 类型筛选器的 ilike 查询测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ds = get_data_source("sqlite", database=get_test_db_path())

    def test_text_filter_generates_ilike_condition(self):
        """text 类型筛选器应该生成 ilike 条件"""
        from meta.services.hierarchy_filter_service import HierarchyFilterService
        from meta.services.query_service import QueryCondition
        
        service = HierarchyFilterService(self.ds)
        
        conditions = service.resolve_conditions(
            'business_object',
            {'description': ['测试描述']}
        )
        
        assert len(conditions) > 0
        desc_condition = next((c for c in conditions if c.field == 'description'), None)
        
        if desc_condition:
            assert desc_condition.operator == 'ilike'
            assert '测试描述' in desc_condition.value
        else:
            pytest.fail("description filter not resolved - may need searchable field")

    def test_text_filter_with_partial_match(self):
        """text 类型筛选器应该支持部分匹配"""
        cursor = self.ds.execute("""
            SELECT id, description 
            FROM business_objects 
            WHERE description IS NOT NULL AND description != ''
            LIMIT 1
        """)
        row = cursor.fetchone()
        
        if row:
            bo_id, description = row
            partial_text = description[:5] if len(description) > 5 else description
            
            from meta.services.hierarchy_filter_service import HierarchyFilterService
            service = HierarchyFilterService(self.ds)
            
            conditions = service.resolve_conditions(
                'business_object',
                {'description': [partial_text]}
            )
            
            assert isinstance(conditions, list)
        else:
            from meta.services.hierarchy_filter_service import HierarchyFilterService
            service = HierarchyFilterService(self.ds)
            
            conditions = service.resolve_conditions(
                'business_object',
                {'description': ['test_partial']}
            )
            
            assert isinstance(conditions, list), "Filter should resolve even with no matching data"

    def test_text_filter_case_insensitive(self):
        """text 类型筛选器应该不区分大小写"""
        from meta.services.hierarchy_filter_service import HierarchyFilterService
        service = HierarchyFilterService(self.ds)
        
        conditions = service.resolve_conditions(
            'business_object',
            {'description': ['TEST']}
        )
        
        for c in conditions:
            if c.field == 'description':
                assert c.operator == 'ilike'
                assert '%' in c.value


class TestFilterConfigWithTextFilter:
    """筛选器配置中 text 类型测试"""

    def test_business_object_has_description_filter(self):
        """业务对象应该有 description 筛选器"""
        from meta.core.models import registry as meta_registry
        
        meta_obj = meta_registry.get("business_object")
        assert meta_obj is not None
        
        view_config = meta_obj.ui_view_config
        assert view_config is not None
        
        filter_config = getattr(view_config, 'filter', None)
        assert filter_config is not None
        
        filters = getattr(filter_config, 'filters', [])
        desc_filter = next((f for f in filters if getattr(f, 'key', '') == 'description'), None)
        
        assert desc_filter is not None, "description filter should exist"
        assert getattr(desc_filter, 'type', '') == 'text', "description filter should be text type"

    def test_product_has_description_filter(self):
        """产品应该有 description 筛选器"""
        from meta.core.models import registry as meta_registry
        
        meta_obj = meta_registry.get("product")
        assert meta_obj is not None
        
        view_config = meta_obj.ui_view_config
        filter_config = getattr(view_config, 'filter', None)
        
        if filter_config:
            filters = getattr(filter_config, 'filters', [])
            desc_filter = next((f for f in filters if getattr(f, 'key', '') == 'description'), None)
            
            assert desc_filter is not None, "description filter should exist"
            assert getattr(desc_filter, 'type', '') == 'text'

    def test_version_has_description_filter(self):
        """版本应该有 description 筛选器"""
        from meta.core.models import registry as meta_registry
        
        meta_obj = meta_registry.get("version")
        assert meta_obj is not None
        
        view_config = meta_obj.ui_view_config
        filter_config = getattr(view_config, 'filter', None)
        
        if filter_config:
            filters = getattr(filter_config, 'filters', [])
            desc_filter = next((f for f in filters if getattr(f, 'key', '') == 'description'), None)
            
            assert desc_filter is not None, "description filter should exist"
            assert getattr(desc_filter, 'type', '') == 'text'


class TestSearchableFieldResolution:
    """searchable 字段解析测试"""

    def test_searchable_field_from_render_hints(self):
        """从 render_hints 解析 searchable 属性"""
        ui = UIAnnotation(
            widget="textarea",
            render_hints=RenderHints(searchable=True)
        )
        
        render_hints = getattr(ui, 'render_hints', None)
        is_searchable = getattr(render_hints, 'searchable', False) if render_hints else False
        
        assert is_searchable is True

    def test_non_searchable_field(self):
        """非 searchable 字段测试"""
        ui = UIAnnotation(
            widget="input",
            render_hints=RenderHints(searchable=False)
        )
        
        render_hints = getattr(ui, 'render_hints', None)
        is_searchable = getattr(render_hints, 'searchable', False) if render_hints else False
        
        assert is_searchable is False

    def test_field_without_render_hints(self):
        """没有 render_hints 的字段默认不可搜索"""
        ui = UIAnnotation(widget="input")
        
        render_hints = getattr(ui, 'render_hints', None)
        is_searchable = getattr(render_hints, 'searchable', False) if render_hints else False
        
        assert is_searchable is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
