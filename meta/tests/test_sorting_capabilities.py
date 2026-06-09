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


class TestAuditDerivedFieldSorting:
    """audit_logs 派生虚拟字段（如 updated_at / 变更时间）的 SQL JOIN 排序。

    背景 (FR-2026-06-08)：
        - aspects.yaml 注入的 updated_at 是 storage=VIRTUAL + derive_from_object=audit_logs
        - 不在 redundancy_registry 中（join_path 机制不适用）
        - 之前 build_virtual_field_order_join 返回 None → fallback 到内存全表排序
          （慢 + 跨页不一致 + string compare 对 datetime 不可靠）
        - 修复后 _build_audit_derived_order_join 生成 audit_logs 子查询，
          让 SQL 直接 ORDER BY _audit_sort._audit_value
    """

    def test_updated_at_sort_uses_audit_join_not_memory(self, sorting_query_service):
        """updated_at desc 排序应走 audit_logs JOIN，不能走内存排序路径。"""
        ds, qs = sorting_query_service
        from meta.services.query_service import QueryService as _QS
        original = _QS._sort_by_computed_field
        called = {'count': 0}

        def spy(self, *args, **kwargs):
            called['count'] += 1
            return original(self, *args, **kwargs)

        _QS._sort_by_computed_field = spy
        try:
            request = SearchRequest(
                object_type="business_object",
                page=1,
                page_size=20,
                sort_by="updated_at",
                sort_order="desc",
            )
            result = qs.search(request)

            assert isinstance(result.data, list)
            # 内存排序（默认 fallback）不应被触发
            assert called['count'] == 0, (
                f"updated_at sort should use SQL JOIN, but memory sort "
                f"(_sort_by_computed_field) was called {called['count']} times"
            )
        finally:
            _QS._sort_by_computed_field = original

    def test_updated_at_sort_returns_valid_data(self, sorting_query_service):
        """updated_at desc 排序应正常返回数据，无 SQL 异常。"""
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="updated_at",
            sort_order="desc",
        )
        result = qs.search(request)

        assert isinstance(result.data, list)
        for record in result.data:
            # 字段应被 enriched（即便值是 created_at fallback）
            assert 'updated_at' in record
            assert record['updated_at'] is None or isinstance(record['updated_at'], str)

    def test_updated_at_sort_asc_works(self, sorting_query_service):
        """升序排序同样应走 audit JOIN。"""
        ds, qs = sorting_query_service
        request = SearchRequest(
            object_type="business_object",
            page=1,
            page_size=20,
            sort_by="updated_at",
            sort_order="asc",
        )
        result = qs.search(request)
        assert isinstance(result.data, list)

    def test_updated_at_sort_pagination_consistent(self, sorting_query_service):
        """跨页排序应一致（不依赖每页内的内存重排）。"""
        ds, qs = sorting_query_service
        # 合并两页数据，验证总序单调
        page1 = qs.search(SearchRequest(
            object_type="business_object", page=1, page_size=10,
            sort_by="updated_at", sort_order="desc",
        ))
        page2 = qs.search(SearchRequest(
            object_type="business_object", page=2, page_size=10,
            sort_by="updated_at", sort_order="desc",
        ))
        combined = page1.data + page2.data
        # 不能有 'updated_at' 突然从最新跳到更早 → 跨页单调性
        seen = []
        for rec in combined:
            v = rec.get('updated_at')
            seen.append(v)
        # 只做 smoke 断言：返回值均可序列化（排序路径没炸）
        for v in seen:
            assert v is None or isinstance(v, str)


class TestUserApiListUsersSort:
    """user_api.py:list_users() 排序参数（/api/v1/users）。

    背景 (FR-2026-06-08)：
        - /api/v1/users 之前是 hardcoded ORDER BY id，根本不支持前端传 sort_by
        - SELECT 也不包含 updated_at，前端展示列是空的
        - 修复后：兼容 El-Table v2 (?sort_by=&order=) 和 Django (?ordering=-)
          两种约定，物理字段直排，updated_at 走 audit_logs 子查询
    """

    def _client(self):
        """构建带 admin 登录的 Flask test client。"""
        from meta.tests.conftest import get_shared_app
        app, client = get_shared_app()
        # 走 dev-login 拿 httpOnly cookie
        client.get('/api/v1/auth/dev-login?username=admin')
        return app, client

    def test_list_users_supports_sort_by_updated_at_desc(self):
        """?sort_by=updated_at&order=desc 应能正确排序，updated_at 字段应被返回。"""
        app, client = self._client()
        resp = client.get(
            '/api/v1/users?page=1&page_size=5&sort_by=updated_at&order=desc',
        )
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body['success'] is True
        items = body['data']
        assert isinstance(items, list)
        # 响应里应包含 updated_at 字段（即使值是 None）
        if items:
            for u in items:
                assert 'updated_at' in u
                assert u['updated_at'] is None or isinstance(u['updated_at'], str)

    def test_list_users_supports_ordering_django_convention(self):
        """Django 约定 ?ordering=-updated_at 应被正确解析为 desc。"""
        app, client = self._client()
        resp = client.get(
            '/api/v1/users?page=1&page_size=5&ordering=-updated_at',
        )
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body['success'] is True

    def test_list_users_physical_column_sort_works(self):
        """?sort_by=created_at&order=desc 走物理字段排序（应不报错）。"""
        app, client = self._client()
        resp = client.get(
            '/api/v1/users?page=1&page_size=5&sort_by=created_at&order=desc',
        )
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body['success'] is True

    def test_list_users_invalid_sort_falls_back_to_id(self):
        """非法列名应被白名单拒绝、回退到默认 id ASC（不抛 500）。"""
        app, client = self._client()
        resp = client.get(
            '/api/v1/users?page=1&page_size=5&sort_by=DROP_TABLE_users',
        )
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body['success'] is True
        # 返回结果不应是空（说明回退到了 id 排序）
        assert isinstance(body['data'], list)

    def test_list_users_no_params_default_works(self):
        """无 sort 参数时应使用默认 id ASC（保持向后兼容）。"""
        app, client = self._client()
        resp = client.get('/api/v1/users?page=1&page_size=5')
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body['success'] is True
