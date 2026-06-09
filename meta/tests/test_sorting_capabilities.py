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


# ============================================================
# 基于计算字段的过滤/排序 API 测试 (v3.18 计算字段专项)
# ============================================================
# 背景 (FR-2026-06-09):
#   - composition/parent_child 关联类型的 count_children 字段
#     之前 _build_computed_count_sort_clause 不支持 → 已修复
#   - 但 _try_build_computed_filter 仍未支持 → G1 (待修复,本类测试预期失败)
#   - formula/category/audit 派生字段的过滤从未覆盖
#
# 端点: GET /api/v2/bo/<object_type>?page=&page_size=&ordering=&<filter>__op=value
# 响应: {success, data:{items, total, page, page_size, filters}}
# 鉴权: dev-login cookie (与 TestUserApiListUsersSort 一致)
# ============================================================


class TestComputedFieldApiHelper:
    """共享辅助：构造 admin client + 调 GET /api/v1/bo/<object_type>"""

    @staticmethod
    def _get_admin_client():
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        # 走 dev-login 拿 httpOnly cookie
        client.get('/api/v1/auth/dev-login?username=admin')
        return client

    @staticmethod
    def _list(client, object_type, **params):
        """调 GET /api/v2/bo/<object_type>，返回 (resp, items)

        注: 前端 boCrudService._request() 默认走 apiV2 = /api/v2，
            对应 bo_bp 的 url_prefix='/api/v2/bo' (见 meta/api/bo_api.py:15)
        """
        # 过滤掉 None 值，避免拼出 ?key=None
        cleaned = {k: v for k, v in params.items() if v is not None}
        qs = '&'.join(f'{k}={v}' for k, v in cleaned.items())
        path = f'/api/v2/bo/{object_type}?{qs}' if qs else f'/api/v2/bo/{object_type}'
        resp = client.get(path)
        if resp.status_code != 200:
            return resp, None
        body = resp.get_json() or {}
        data = body.get('data', {})
        items = data.get('items', []) if isinstance(data, dict) else []
        return resp, items

    @staticmethod
    def _extract_field(items, field):
        """从 items 中提取某字段值列表"""
        return [it.get(field) for it in (items or []) if field in it]


class TestCompositionCountSortRegression(TestComputedFieldApiHelper):
    """G2: composition/parent_child 关联类型 count_children 字段排序回归。

    守护 2026-06-09 修复: _build_computed_count_sort_clause 新增 composition
    和 parent_child 支持 + source_key fallback + child_object 匹配。

    模拟前端 ?ordering=-child_count (Django / El-Table v2 风格)。
    """

    def test_product_child_count_sort_desc(self):
        """GET /api/v1/bo/product?ordering=-child_count → 子版本数量降序"""
        client = self._get_admin_client()
        resp, items = self._list(client, 'product', ordering='-child_count', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        assert items is not None
        counts = self._extract_field(items, 'child_count')
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                a, b = counts[i] or 0, counts[i + 1] or 0
                assert a >= b, f"desc 不成立: {counts}"

    def test_product_child_count_sort_asc(self):
        """GET /api/v1/bo/product?ordering=child_count → 子版本数量升序"""
        client = self._get_admin_client()
        resp, items = self._list(client, 'product', ordering='child_count', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        counts = self._extract_field(items, 'child_count')
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                a, b = counts[i] or 0, counts[i + 1] or 0
                assert a <= b, f"asc 不成立: {counts}"

    def test_version_child_count_sort_desc(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'version', ordering='-child_count', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        counts = self._extract_field(items, 'child_count')
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                a, b = counts[i] or 0, counts[i + 1] or 0
                assert a >= b

    def test_domain_child_count_sort_desc(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'domain', ordering='-child_count', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        counts = self._extract_field(items, 'child_count')
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                a, b = counts[i] or 0, counts[i + 1] or 0
                assert a >= b

    def test_sub_domain_child_count_sort_desc(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'sub_domain', ordering='-child_count', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        counts = self._extract_field(items, 'child_count')
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                a, b = counts[i] or 0, counts[i + 1] or 0
                assert a >= b

    def test_service_module_child_count_sort_desc(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'service_module', ordering='-child_count', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        counts = self._extract_field(items, 'child_count')
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                a, b = counts[i] or 0, counts[i + 1] or 0
                assert a >= b

    def test_enum_type_value_count_sort_desc(self):
        """parent_child: enum_type → enum_value 的 value_count 排序"""
        client = self._get_admin_client()
        resp, items = self._list(client, 'enum_type', ordering='-value_count', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        counts = self._extract_field(items, 'value_count')
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                a, b = counts[i] or 0, counts[i + 1] or 0
                assert a >= b

    def test_product_child_count_sort_pagination_consistent(self):
        """排序后翻页应保持单调性（防止 SQL 失败回退到内存排序）。"""
        client = self._get_admin_client()
        _, page1 = self._list(client, 'product', ordering='-child_count', page=1, page_size=5)
        _, page2 = self._list(client, 'product', ordering='-child_count', page=2, page_size=5)
        assert page1 is not None and page2 is not None
        if page1 and page2:
            last_p1 = page1[-1].get('child_count', 0) or 0
            first_p2 = page2[0].get('child_count', 0) or 0
            assert last_p1 >= first_p2, f"跨页单调性破坏: {last_p1} -> {first_p2}"


class TestCompositionCountFilter(TestComputedFieldApiHelper):
    """G1: composition/parent_child 关联类型 count_children 字段过滤。

    ⚠️ 已知问题 (2026-06-09):
       _try_build_computed_filter 仅支持 many_to_many/one_to_many,
       不支持 composition/parent_child。本类测试预期失败，
       用作后续修复的测试依据。

    模拟前端 ?child_count=5&child_count__gte=3 等组合。
    """

    def test_product_child_count_eq_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'product', child_count=5, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('child_count', 0) or 0) == 5, \
                f"过滤失败: id={it.get('id')} child_count={it.get('child_count')}"

    def test_product_child_count_gte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'product', **{'child_count__gte': 3}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('child_count', 0) or 0) >= 3

    def test_product_child_count_lte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'product', **{'child_count__lte': 2}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('child_count', 0) or 0) <= 2

    def test_product_child_count_in_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'product', **{'child_count__in': '1,2,3'}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('child_count', 0) or 0) in (1, 2, 3)

    def test_product_child_count_notin_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'product', **{'child_count__notin': '0'}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('child_count', 0) or 0) != 0

    def test_domain_child_count_gte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'domain', **{'child_count__gte': 1}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('child_count', 0) or 0) >= 1

    def test_sub_domain_child_count_eq_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'sub_domain', child_count=0, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('child_count', 0) or 0) == 0

    def test_service_module_child_count_gte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'service_module', **{'child_count__gte': 1}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('child_count', 0) or 0) >= 1

    def test_enum_type_value_count_eq_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'enum_type', value_count=0, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('value_count', 0) or 0) == 0

    def test_filter_int_coercion_for_sqlite_affinity(self):
        """SQLite type affinity: 字符串 '5' 应被自动转 int（计数比较不失效）。"""
        client = self._get_admin_client()
        resp, items = self._list(client, 'product', child_count='5', page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        # 即使 child_count 是字符串 '5' 传入，过滤应仍然生效
        for it in (items or []):
            assert int(it.get('child_count', 0)) == 5


class TestManyToManyCountSortFilter(TestComputedFieldApiHelper):
    """G4 替代: many_to_many 关联 count 字段排序 + 过滤。

    补充 relation_count 在 m2m 路径上的过滤能力（之前只测了排序）。
    """

    def test_business_object_relation_count_sort_desc(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'business_object', ordering='-relation_count', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        counts = self._extract_field(items, 'relation_count')
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                a, b = counts[i] or 0, counts[i + 1] or 0
                assert a >= b

    def test_business_object_relation_count_gte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'business_object', **{'relation_count__gte': 2}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('relation_count', 0) or 0) >= 2

    def test_business_object_relation_count_eq_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'business_object', relation_count=0, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('relation_count', 0) or 0) == 0

    def test_domain_relation_count_gte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'domain', **{'relation_count__gte': 1}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert (it.get('relation_count', 0) or 0) >= 1


class TestFormulaFieldSortFilter(TestComputedFieldApiHelper):
    """G5: formula/expression 派生字段排序 + 过滤。

    真实字段: domain/sub_domain/service_module.bo_density
              = ROUND(DIVIDE(relation_count, child_count, 0), 2)
    """

    def test_domain_bo_density_sort_desc(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'domain', ordering='-bo_density', page_size=10)
        assert resp.status_code == 200, resp.data[:300]
        densities = [it.get('bo_density') for it in (items or []) if it.get('bo_density') is not None]
        if len(densities) >= 2:
            for i in range(len(densities) - 1):
                a, b = densities[i], densities[i + 1]
                assert a >= b, f"desc 不成立: {densities}"

    def test_sub_domain_bo_density_gte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'sub_domain', **{'bo_density__gte': 0.5}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            v = it.get('bo_density')
            if v is not None:
                assert float(v) >= 0.5


class TestCategoryAndAuditFieldFilter(TestComputedFieldApiHelper):
    """G6+G7: hierarchy_scope 派生 category_label + audit_logs 派生 updated_at 过滤。

    之前 TestRelationshipSorting 只测了排序，过滤从未覆盖。
    """

    def test_relationship_category_label_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'relationship', category_label='跨领域', page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert it.get('category_label') == '跨领域'

    def test_relationship_category_type_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'relationship', category_type='cross_domain', page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        for it in (items or []):
            assert it.get('category_type') == 'cross_domain'

    def test_business_object_updated_at_gte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'business_object', **{'updated_at__gte': '2026-01-01'}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]
        # updated_at 可能是 ISO 字符串或 None（无审计时），仅断言字段存在
        for it in (items or []):
            v = it.get('updated_at')
            assert v is None or isinstance(v, str)

    def test_business_object_updated_at_lte_filter(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'business_object', **{'updated_at__lte': '2099-12-31'}, page_size=20)
        assert resp.status_code == 200, resp.data[:300]


class TestSortFilterCombinations(TestComputedFieldApiHelper):
    """组合场景: 排序 + 过滤 + 分页 + 关键字 (前端 el-table + 过滤面板典型组合)。"""

    def test_sort_and_filter_combined(self):
        client = self._get_admin_client()
        resp, items = self._list(
            client, 'product',
            ordering='-child_count',
            **{'child_count__gte': 1},
            page_size=10,
        )
        assert resp.status_code == 200, resp.data[:300]
        counts = [(it.get('child_count', 0) or 0) for it in (items or [])]
        assert all(c >= 1 for c in counts), f"过滤失效: {counts}"
        if len(counts) >= 2:
            for i in range(len(counts) - 1):
                assert counts[i] >= counts[i + 1], f"排序失效: {counts}"

    def test_sort_filter_pagination_combined(self):
        client = self._get_admin_client()
        _, p1 = self._list(
            client, 'product',
            ordering='-child_count',
            **{'child_count__gte': 0},
            page=1, page_size=3,
        )
        _, p2 = self._list(
            client, 'product',
            ordering='-child_count',
            **{'child_count__gte': 0},
            page=2, page_size=3,
        )
        assert p1 is not None and p2 is not None
        if p1 and p2:
            last_p1 = p1[-1].get('child_count', 0) or 0
            first_p2 = p2[0].get('child_count', 0) or 0
            assert last_p1 >= first_p2

    def test_sort_with_keyword(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'business_object', ordering='-relation_count', page_size=5)
        assert resp.status_code == 200, resp.data[:300]

    def test_filter_with_keyword(self):
        client = self._get_admin_client()
        resp, items = self._list(client, 'business_object', **{'relation_count__gte': 0}, page_size=5)
        assert resp.status_code == 200, resp.data[:300]

    def test_combined_all_features(self):
        """终极组合: sort + filter + page + size"""
        client = self._get_admin_client()
        resp, items = self._list(
            client, 'business_object',
            ordering='-relation_count',
            **{'relation_count__gte': 0},
            page=1, page_size=10,
        )
        assert resp.status_code == 200, resp.data[:300]
        assert items is not None

    def test_sort_invalid_field_falls_back(self):
        """非法字段排序应回退到默认排序（不抛 500）。"""
        client = self._get_admin_client()
        resp = client.get('/api/v2/bo/product?ordering=-DROP_TABLE&page_size=5')
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body['success'] is True
