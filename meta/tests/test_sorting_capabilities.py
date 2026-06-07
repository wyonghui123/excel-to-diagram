# -*- coding: utf-8 -*-
"""
通用排序功能测试

测试场景：
1. 对象列表排序
   - 物理字段排序（name, code, created_at）
   - 虚拟字段排序（relation_count with different scopes）

2. 关系列表排序
   - 物理字段排序（source_code, target_code, relation_code, created_at）
   - 计算字段排序（category_label）

3. 排序方向测试
   - 升序（ASC）
   - 降序（DESC）

4. 分页与排序结合测试
   - 排序后分页是否正确
"""

import sys
import os
import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.test_utils import get_test_db_path, get_data_source_for_test
from meta.services.query_service import QueryService, SearchRequest

pytestmark = pytest.mark.integration


@pytest.fixture(scope='class')
def sorting_query_service():
    ds = get_data_source_for_test()
    query_service = QueryService(ds)
    return ds, query_service


@pytest.fixture(scope='class')
def sorting_query_service_try():
    try:
        ds = get_data_source_for_test()
        query_service = QueryService(ds)
    except Exception:
        ds = None
        query_service = None
    return ds, query_service


class TestObjectListSorting:

    def test_physical_field_sort_asc(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="name",
            sort_order="asc"
        )
        result = qs.search(request)

        data = result.data
        assert isinstance(data, list)

        if len(data) > 1:
            names = [item.get("name", "") for item in data]
            assert names == sorted(names), "Names should be sorted ascending"

    def test_physical_field_sort_desc(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="name",
            sort_order="desc"
        )
        result = qs.search(request)

        data = result.data
        assert isinstance(data, list)

        if len(data) > 1:
            names = [item.get("name", "") for item in data]
            assert names == sorted(names, reverse=True), "Names should be sorted descending"

    def test_created_at_sort(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="created_at",
            sort_order="desc"
        )
        result = qs.search(request)

        assert isinstance(result.data, list)

    def test_sort_with_pagination(self, sorting_query_service):
        ds, qs = sorting_query_service
        request1 = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=10,
            sort_by="name",
            sort_order="asc"
        )
        request2 = SearchRequest(
            object_type="business_object",
            page=2,
            page_size=10,
            sort_by="name",
            sort_order="asc"
        )

        result1 = qs.search(request1)
        result2 = qs.search(request2)

        data1 = result1.data
        data2 = result2.data

        if data1 and data2:
            last_name_page1 = data1[-1].get("name", "")
            first_name_page2 = data2[0].get("name", "")
            assert last_name_page1 <= first_name_page2


class TestVirtualFieldSorting:

    def test_relation_count_sort_business_object(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="relation_count",
            sort_order="desc"
        )
        result = qs.search(request)

        data = result.data
        assert isinstance(data, list)

        if len(data) > 1:
            counts = [item.get("relation_count", 0) for item in data]
            for i in range(len(counts) - 1):
                assert counts[i] >= counts[i + 1]

    def test_relation_count_sort_domain(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="domain",
            page=1,
            page_size=20,
            sort_by="relation_count",
            sort_order="desc"
        )
        result = qs.search(request)

        assert isinstance(result.data, list)

    def test_relation_count_sort_sub_domain(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="sub_domain",
            page=1,
            page_size=20,
            sort_by="relation_count",
            sort_order="desc"
        )
        result = qs.search(request)

        assert isinstance(result.data, list)

    def test_relation_count_sort_service_module(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="service_module",
            page=1,
            page_size=20,
            sort_by="relation_count",
            sort_order="desc"
        )
        result = qs.search(request)

        assert isinstance(result.data, list)

    def test_relation_count_sort_asc(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="relation_count",
            sort_order="asc"
        )
        result = qs.search(request)

        data = result.data
        assert isinstance(data, list)

        if len(data) > 1:
            counts = [item.get("relation_count", 0) for item in data]
            for i in range(len(counts) - 1):
                assert counts[i] <= counts[i + 1]


class TestRelationshipSorting:

    def test_source_code_sort(self, sorting_query_service_try):
        ds, qs = sorting_query_service_try
        if qs is None:
            pytest.fail("Relationship sorting requires complete relationship schema data")
        try:
            request = SearchRequest(
                object_type="relationship",
                page=1,
                page_size=20,
                sort_by="source_code",
                sort_order="asc"
            )
            result = qs.search(request)

            data = result.data
            assert isinstance(data, list)

            if len(data) > 1:
                codes = [item.get("source_code", "") for item in data]
                assert codes == sorted(codes), "source_code should be sorted ascending"
        except Exception as e:
            pytest.fail(f"Relationship sorting requires complete relationship schema data: {e}")

    def test_target_code_sort(self, sorting_query_service_try):
        ds, qs = sorting_query_service_try
        if qs is None:
            pytest.fail("Relationship sorting requires complete relationship schema data")
        try:
            request = SearchRequest(
                object_type="relationship",
                page=1,
                page_size=20,
                sort_by="target_code",
                sort_order="asc"
            )
            result = qs.search(request)

            assert isinstance(result.data, list)
        except Exception as e:
            pytest.fail(f"Relationship sorting requires complete relationship schema data: {e}")

    def test_relation_code_sort(self, sorting_query_service_try):
        ds, qs = sorting_query_service_try
        if qs is None:
            pytest.fail("Relationship sorting requires complete relationship schema data")
        try:
            request = SearchRequest(
                object_type="relationship",
                page=1,
                page_size=20,
                sort_by="relation_code",
                sort_order="asc"
            )
            result = qs.search(request)

            data = result.data
            assert isinstance(data, list)

            if len(data) > 1:
                codes = [item.get("relation_code", "") for item in data]
                assert codes == sorted(codes), "relation_code should be sorted ascending"
        except Exception as e:
            pytest.fail(f"Relationship sorting requires complete relationship schema data: {e}")

    def test_category_label_sort_asc(self, sorting_query_service_try):
        ds, qs = sorting_query_service_try
        if qs is None:
            pytest.fail("Relationship sorting requires complete relationship schema data")
        try:
            request = SearchRequest(
                object_type="relationship",
                page=1,
                page_size=20,
                sort_by="category_label",
                sort_order="asc"
            )
            result = qs.search(request)

            data = result.data
            assert isinstance(data, list)

            if len(data) > 1:
                labels = [item.get("category_label", "") for item in data]
                assert labels == sorted(labels), "category_label should be sorted ascending"
        except Exception as e:
            pytest.fail(f"Relationship sorting requires complete relationship schema data: {e}")

    def test_category_label_sort_desc(self, sorting_query_service_try):
        ds, qs = sorting_query_service_try
        if qs is None:
            pytest.fail("Relationship sorting requires complete relationship schema data")
        try:
            request = SearchRequest(
                object_type="relationship",
                page=1,
                page_size=20,
                sort_by="category_label",
                sort_order="desc"
            )
            result = qs.search(request)

            data = result.data
            assert isinstance(data, list)

            if len(data) > 1:
                labels = [item.get("category_label", "") for item in data]
                assert labels == sorted(labels, reverse=True), "category_label should be sorted descending"
        except Exception as e:
            pytest.fail(f"Relationship sorting requires complete relationship schema data: {e}")

    def test_created_at_sort_relationship(self, sorting_query_service_try):
        ds, qs = sorting_query_service_try
        if qs is None:
            pytest.fail("Relationship sorting requires complete relationship schema data")
        try:
            request = SearchRequest(
                object_type="relationship",
                page=1,
                page_size=20,
                sort_by="created_at",
                sort_order="desc"
            )
            result = qs.search(request)

            assert isinstance(result.data, list)
        except Exception as e:
            pytest.fail(f"Relationship sorting requires complete relationship schema data: {e}")


class TestSortingEdgeCases:

    def test_invalid_sort_field(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="invalid_field_name",
            sort_order="asc"
        )

        with pytest.raises(Exception):
            qs.search(request)

    def test_empty_result_sort(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="name",
            sort_order="asc"
        )
        request.conditions = []
        result = qs.search(request)

        assert isinstance(result.data, list)

    def test_single_item_sort(self, sorting_query_service):
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=1,
            sort_by="name",
            sort_order="asc"
        )
        result = qs.search(request)

        assert isinstance(result.data, list)


class TestComputedFieldHandler:

    def test_compute_category_same_module(self):
        from meta.api.manage_api import _compute_category

        relation = {
            'source_domain_id': 1,
            'target_domain_id': 1,
            'source_sub_domain_id': 1,
            'target_sub_domain_id': 1,
            'source_service_module_id': 1,
            'target_service_module_id': 1,
        }

        label, type_id = _compute_category(relation)
        assert label == "同服务模块"
        assert type_id == "same_module"

    def test_compute_category_cross_domain(self):
        from meta.api.manage_api import _compute_category

        relation = {
            'source_domain_id': 1,
            'target_domain_id': 2,
            'source_sub_domain_id': 1,
            'target_sub_domain_id': 2,
            'source_service_module_id': 1,
            'target_service_module_id': 2,
        }

        label, type_id = _compute_category(relation)
        assert label == "跨领域"
        assert type_id == "cross_domain"

    def test_compute_category_same_subdomain_cross_module(self):
        from meta.api.manage_api import _compute_category

        relation = {
            'source_domain_id': 1,
            'target_domain_id': 1,
            'source_sub_domain_id': 1,
            'target_sub_domain_id': 1,
            'source_service_module_id': 1,
            'target_service_module_id': 2,
        }

        label, type_id = _compute_category(relation)
        assert label == "同子领域跨服务模块"
        assert type_id == "same_subdomain_cross_module"

    def test_on_before_save_relationship(self):
        from meta.core.consistency_guard import ComputedFieldHandler

        handler = ComputedFieldHandler(None)

        data = {
            'source_domain_id': 1,
            'target_domain_id': 1,
            'source_sub_domain_id': 1,
            'target_sub_domain_id': 1,
            'source_service_module_id': 1,
            'target_service_module_id': 1,
        }

        result = handler.on_before_save('relationship', data)

        assert 'category_label' not in result, "category_label is now virtual, not stored"

    def test_on_before_save_other_object(self):
        from meta.core.consistency_guard import ComputedFieldHandler

        handler = ComputedFieldHandler(None)

        data = {'name': 'test'}
        result = handler.on_before_save('business_object', data)

        assert 'category_label' not in result
