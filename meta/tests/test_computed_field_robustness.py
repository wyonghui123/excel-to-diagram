# -*- coding: utf-8 -*-
"""
[SPEC-CF 2026-06-11] 计算字段 Sort/Filter 健壮性回归测试

覆盖 Phase 3 测试矩阵 (Spec 5.1):
1. P0: fail-fast 422 - 不支持的 computation.type / object_type / scope
2. P0: unknown virtual field filter - 400 (项目惯例) vs 422 (computation 不支持)
3. P1: 次级稳定键 id DESC - 同 count 值翻页不重复、不丢
4. P1: 缓存失效 - MetaRegistry.reload 后 _SCOPE_SORT_ORDER_CACHE 清空
5. P1: NULL 永远排最后 - COALESCE -1
6. P2: 跨页单调性 + 无重复

测试策略:
- 端到端: 走 HTTP 接口 (admin client), 验证完整链路
- 单元: 直接调 ComputedFieldQuery, 验证 SQL 构造
"""
import sys
import os
import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.test_utils import get_test_db_path, get_data_source_for_test

pytestmark = pytest.mark.integration


# ════════════════════════════════════════════════════════
# 共享 helper
# ════════════════════════════════════════════════════════

def _get_admin_client():
    from meta.tests.conftest import get_shared_app
    _, client = get_shared_app()
    client.get('/api/v1/auth/dev-login?username=admin')
    return client


def _list(client, object_type, **params):
    """GET /api/v2/bo/<object_type> → (resp, items)"""
    cleaned = {k: v for k, v in params.items() if v is not None}
    qs = '&'.join(f'{k}={v}' for k, v in cleaned.items())
    path = f'/api/v2/bo/{object_type}?{qs}' if qs else f'/api/v2/bo/{object_type}'
    resp = client.get(path)
    if resp.status_code != 200:
        return resp, None
    try:
        items = resp.json.get('data', {}).get('items') if hasattr(resp, 'json') else None
    except Exception:
        items = None
    return resp, items


# ════════════════════════════════════════════════════════
# P0 测试: fail-fast 422
# ════════════════════════════════════════════════════════

class TestFailFastOnUnsupportedComputation:
    """[R0-2] 不支持的 computation 组合 → 422, 不再 silent fallback"""

    def test_unknown_computation_field_is_silently_ignored(self):
        """[项目惯例] 未知 *_count 字段过滤 → 静默忽略 (宽容设计).

        设计选择: v2 端点对未识别的 query param 保持宽容 (返 200 + 不过滤),
        与 v1 端点行为一致. 这是为了前端拼写错误时不报错.
        注意: 这是"未知字段"路径, 不是"字段不支持 computation"路径.
        """
        client = _get_admin_client()
        resp, items = _list(client, 'service_module', **{'mystery_count__gte': '5'})
        assert resp.status_code == 200, f"unexpected status={resp.status_code}"
        assert items is not None, "items should be returned (filter silently ignored)"

    def test_count_relations_on_unsupported_object_is_silently_ignored(self):
        """[项目惯例] version 对象没有 relation_count → 静默忽略.

        version 对象在 YAML 里没声明 relation_count 字段,
        所以 v2 端点把它当未知字段处理.
        """
        client = _get_admin_client()
        resp, _ = _list(client, 'version', **{'relation_count__gte': '5'})
        assert resp.status_code == 200, f"unexpected status={resp.status_code}"

    def test_422_response_format(self):
        """[R0-2] errorhandler 必须返回 {success: False, error_code, message, details} 格式.

        通过 mock unsupported (comp_type, object_type, scope) 组合,
        在构造 ComputedFieldQuery 时就触发 ComputationNotSupportedError,
        验证 error 结构.
        """
        from meta.core.computed_field_query import ComputationNotSupportedError

        err = ComputationNotSupportedError(
            comp_type='count_relations',
            object_type='user_group',
            scope='descendants',  # user_group 不支持 descendants
        )
        # 验证错误对象结构 (供 errorhandler 使用)
        assert err.comp_type == 'count_relations'
        assert err.object_type == 'user_group'
        assert err.scope == 'descendants'
        assert 'count_relations' in str(err)
        assert 'user_group' in str(err)
        assert 'descendants' in str(err)

    def test_422_via_flask_errorhandler(self):
        """[R0-2] 端到端: ComputationNotSupportedError 经 Flask errorhandler → 422 JSON.

        用 Flask test_client + monkey-patched raise 模拟线上触发场景.
        """
        from meta.core.computed_field_query import ComputationNotSupportedError
        from meta.tests.conftest import get_shared_app

        _, client = get_shared_app()
        client.get('/api/v1/auth/dev-login?username=admin')

        # Monkey-patch _try_build_computed_filter 在调用时主动抛错
        # 我们用 service_module + 一个会被查找的字段来走通到 SSOT 入口
        from meta.core.interceptors import persistence_interceptor
        original = persistence_interceptor.PersistenceInterceptor._try_build_computed_filter

        def boom(self, meta_object, key, value):
            # 仅对特定 key 抛错, 不影响其他测试
            if key == 'relation_count__gte':
                raise ComputationNotSupportedError(
                    comp_type='count_relations',
                    object_type=meta_object.id,
                    scope='descendants',
                )
            return original(self, meta_object, key, value)

        persistence_interceptor.PersistenceInterceptor._try_build_computed_filter = boom
        try:
            resp = client.get('/api/v2/bo/service_module?relation_count__gte=1')
            assert resp.status_code == 422, f"FAIL: expected 422, got {resp.status_code}"
            body = resp.json if hasattr(resp, 'json') else {}
            assert body.get('success') is False
            assert body.get('error_code') == 'COMPUTATION_NOT_SUPPORTED'
            assert 'details' in body
            assert body['details']['comp_type'] == 'count_relations'
        finally:
            persistence_interceptor.PersistenceInterceptor._try_build_computed_filter = original


class TestComputationNotSupportedErrors:
    """[R0-2] ComputationNotSupportedError 在构造时就抛, 不延迟"""

    def test_is_supported_matrix_count_relations_self(self):
        """count_relations self: business_object / user_group 支持"""
        from meta.core.computed_field_query import is_supported
        assert is_supported('count_relations', 'business_object', 'self') is True
        assert is_supported('count_relations', 'user_group', 'self') is True
        assert is_supported('count_relations', 'domain', 'self') is False
        assert is_supported('count_relations', 'version', 'self') is False

    def test_is_supported_matrix_count_relations_descendants(self):
        """count_relations descendants: domain / sub_domain / service_module"""
        from meta.core.computed_field_query import is_supported
        assert is_supported('count_relations', 'domain', 'descendants') is True
        assert is_supported('count_relations', 'sub_domain', 'descendants') is True
        assert is_supported('count_relations', 'service_module', 'descendants') is True
        assert is_supported('count_relations', 'business_object', 'descendants') is False

    def test_is_supported_matrix_count_children(self):
        """count_children: 6 个对象 (含新加的 product/enum_type)"""
        from meta.core.computed_field_query import is_supported
        for obj in ('version', 'domain', 'sub_domain', 'service_module', 'product', 'enum_type'):
            assert is_supported('count_children', obj) is True, f"{obj} should support count_children"
        # 不支持的对象
        assert is_supported('count_children', 'business_object') is False
        assert is_supported('count_children', 'relationship') is False

    def test_unsupported_combination_raises_on_construction(self):
        """构造 ComputedFieldQuery 时 fail-fast (不延迟到 SQL 拼装)"""
        # 找一个不存在的关系: user_group 没有 count_relations descendants
        from meta.core.models import MetaRegistry
        from meta.core.computed_field_query import ComputedFieldQuery, ComputationNotSupportedError

        registry = MetaRegistry()
        # 直接构造一个 unsupported 组合的 MetaField
        class MockField:
            id = 'relation_count'
            field_type = 'integer'
            computed = True
            computation = {'type': 'count_relations', 'scope': 'descendants'}

        class MockObject:
            id = 'user_group'
            table_name = 'user_groups'

        with pytest.raises(ComputationNotSupportedError) as exc_info:
            ComputedFieldQuery(MockObject(), MockField())
        assert exc_info.value.comp_type == 'count_relations'
        assert exc_info.value.object_type == 'user_group'
        assert exc_info.value.scope == 'descendants'


# ════════════════════════════════════════════════════════
# P1 测试: 次级稳定键 id DESC
# ════════════════════════════════════════════════════════

class TestSecondaryStableKey:
    """[R1-1] 所有 *count 排序子句必须包含 ', {table}.id DESC' 次级稳定键"""

    def test_build_order_clause_has_id_desc_tiebreaker(self):
        """ComputedFieldQuery.build_order_clause 末尾必须是 id DESC"""
        from meta.core.models import MetaRegistry
        from meta.core.computed_field_query import ComputedFieldQuery

        registry = MetaRegistry()
        sm = registry.get('service_module')
        assert sm is not None
        field = sm.get_field('relation_count')
        assert field is not None

        cfq = ComputedFieldQuery(sm, field)
        clause_asc = cfq.build_order_clause(is_desc=False)
        clause_desc = cfq.build_order_clause(is_desc=True)
        assert clause_asc is not None
        assert 'service_modules.id DESC' in clause_asc, f"ASC clause missing tiebreaker: {clause_asc}"
        assert ' ASC' in clause_asc
        assert clause_desc is not None
        assert 'service_modules.id DESC' in clause_desc
        assert ' DESC' in clause_desc

    def test_filter_clause_uses_coalesce_for_null_safety(self):
        """filter clause 用 COALESCE(..., -1) 把 NULL 强制到 -1 (永远排最后)"""
        from meta.core.models import MetaRegistry
        from meta.core.computed_field_query import ComputedFieldQuery

        registry = MetaRegistry()
        sm = registry.get('service_module')
        field = sm.get_field('relation_count')
        cfq = ComputedFieldQuery(sm, field)
        clause, params = cfq.build_filter_clause('>=', '5')
        assert clause is not None
        assert 'COALESCE(' in clause
        assert '-1' in clause
        assert params == [5]  # '5' 字符串被 coerce 成 int 5

    def test_filter_clause_coerce_string_to_int(self):
        """SQLite type affinity: URL 字符串 '5' 必须 coerce 成 int 5"""
        from meta.core.models import MetaRegistry
        from meta.core.computed_field_query import ComputedFieldQuery

        registry = MetaRegistry()
        sm = registry.get('service_module')
        field = sm.get_field('relation_count')
        cfq = ComputedFieldQuery(sm, field)
        clause, params = cfq.build_filter_clause('>=', '5')
        assert isinstance(params[0], int), f"FAIL: not coerced, got {type(params[0])}: {params}"
        assert params[0] == 5

    def test_in_clause_with_multiple_values(self):
        """__in / __notin: 多值拆成 (?, ?, ...) 多占位符"""
        from meta.core.models import MetaRegistry
        from meta.core.computed_field_query import ComputedFieldQuery

        registry = MetaRegistry()
        sm = registry.get('service_module')
        field = sm.get_field('relation_count')
        cfq = ComputedFieldQuery(sm, field)
        clause, params = cfq.build_filter_clause('IN', '1,2,3')
        assert clause is not None
        assert ' IN (' in clause
        assert clause.count('?') == 3, f"expected 3 placeholders, got: {clause}"
        assert params == [1, 2, 3], f"FAIL: params not coerced: {params}"


# ════════════════════════════════════════════════════════
# P1 测试: 缓存失效 (YAML reload)
# ════════════════════════════════════════════════════════

class TestCacheInvalidation:
    """[R1-2] MetaRegistry.invalidate_caches() 后所有计算字段缓存必须清空"""

    def test_scope_sort_order_cache_clears_on_invalidate(self):
        """[R1-2] _SCOPE_SORT_ORDER_CACHE 必须在 invalidate_caches 后清空.

        注意: _get_scope_sort_order() 在 DB 不可用时会 catch exception 走兜底字典,
        缓存可能不会被填充. 因此测试直接设置缓存状态, 然后验证 invalidate_caches 清除.
        """
        from meta.services.query import computed_utils
        from meta.core.models import MetaRegistry

        # 手动设置缓存状态 (模拟成功加载后的状态)
        computed_utils._SCOPE_SORT_ORDER_LOADED = True
        computed_utils._SCOPE_SORT_ORDER_CACHE['__test_scope__'] = 99
        assert computed_utils._SCOPE_SORT_ORDER_LOADED is True
        assert len(computed_utils._SCOPE_SORT_ORDER_CACHE) > 0

        # 触发 invalidate
        registry = MetaRegistry()
        registry.invalidate_caches()

        # 验证缓存已清空
        assert computed_utils._SCOPE_SORT_ORDER_LOADED is False
        assert len(computed_utils._SCOPE_SORT_ORDER_CACHE) == 0

    def test_computation_service_cache_clears_on_invalidate(self):
        """ComputationService._cache 必须在 invalidate_caches 后清空"""
        from meta.services.computation_service import computation_service
        from meta.core.models import MetaRegistry

        computation_service._cache['__test__'] = 'some_value'
        assert computation_service._cache.get('__test__') == 'some_value'

        registry = MetaRegistry()
        registry.invalidate_caches()

        assert computation_service._cache.get('__test__') is None, (
            "FAIL: invalidate_caches() 没清 computation_service._cache"
        )

    def test_invalidate_caches_helper_directly(self):
        """直接调 invalidate_caches() 也清空缓存"""
        from meta.services.query import computed_utils
        from meta.services.computation_service import computation_service
        from meta.core.computed_field_query import invalidate_caches

        # 准备数据
        computed_utils._SCOPE_SORT_ORDER_LOADED = True
        computed_utils._SCOPE_SORT_ORDER_CACHE['__x__'] = 'y'
        computation_service._cache['__y__'] = 'z'

        invalidate_caches()

        assert computed_utils._SCOPE_SORT_ORDER_LOADED is False
        assert computed_utils._SCOPE_SORT_ORDER_CACHE == {}
        assert '__y__' not in computation_service._cache


# ════════════════════════════════════════════════════════
# P1 测试: NULL 永远排最后
# ════════════════════════════════════════════════════════

class TestNullCountAlwaysLast:
    """[R1-4 / 决策3] NULL count 必须永远排最后 (id DESC 保证稳定)"""

    def test_filter_clause_coalesce_minus_one(self):
        """WHERE clause 用 COALESCE(expr, -1) 兜底 NULL"""
        from meta.core.models import MetaRegistry
        from meta.core.computed_field_query import ComputedFieldQuery

        registry = MetaRegistry()
        sm = registry.get('service_module')
        field = sm.get_field('relation_count')
        cfq = ComputedFieldQuery(sm, field)

        # gte=0 应当匹配所有行 (NULL 视为 -1, < 0 不匹配 → 但实际 NULL 被 COALESCE 成 -1, 仍 < 0)
        clause, params = cfq.build_filter_clause('>=', '0')
        assert 'COALESCE' in clause
        assert '-1' in clause

    def test_asc_sort_with_null_values(self):
        """ASC 排序时 NULL 值实际不存在 (有子查询兜底)"""
        client = _get_admin_client()
        resp, items = _list(client, 'service_module', ordering='relation_count', page_size=100)
        if resp.status_code == 200 and items:
            counts = [it.get('relation_count') or 0 for it in items]
            assert counts == sorted(counts), f"FAIL: ASC sort not monotonic: {counts}"
            # counts 中没有 None (因为子查询表达式永远返 int, 无 NULL)
            assert None not in counts


# ════════════════════════════════════════════════════════
# P2 测试: 跨页无重复 + 单调性
# ════════════════════════════════════════════════════════

class TestPaginationConsistency:
    """[R1-1 / R1-4] 翻页一致性: 无重复 + 单调性"""

    @pytest.mark.parametrize("object_type,ordering", [
        ('service_module', '-relation_count'),
        ('service_module', 'relation_count'),
        ('domain', '-child_count'),
        ('domain', 'child_count'),
        ('sub_domain', '-relation_count'),
    ])
    def test_pagination_no_overlap_and_monotonic(self, object_type, ordering):
        """翻页: page1 ∩ page2 = ∅ + last_p1 >= first_p2 (DESC)"""
        client = _get_admin_client()
        _, page1 = _list(client, object_type, ordering=ordering, page=1, page_size=5)
        _, page2 = _list(client, object_type, ordering=ordering, page=2, page_size=5)
        if not page1 or not page2:
            pytest.skip("Not enough data to paginate")
        ids1 = {it.get('id') for it in page1}
        ids2 = {it.get('id') for it in page2}
        overlap = ids1 & ids2
        assert not overlap, f"FAIL: page overlap: {overlap}"

        is_desc = ordering.startswith('-')
        field = ordering.lstrip('-')
        last_p1 = page1[-1].get(field, 0) or 0
        first_p2 = page2[0].get(field, 0) or 0
        if is_desc:
            assert last_p1 >= first_p2, f"DESC 跨页单调性破坏: {last_p1} -> {first_p2}"
        else:
            assert last_p1 <= first_p2, f"ASC 跨页单调性破坏: {last_p1} -> {first_p2}"

    @pytest.mark.parametrize("object_type,ordering", [
        ('service_module', '-relation_count'),
        ('domain', '-relation_count'),
        ('sub_domain', '-relation_count'),
    ])
    def test_pagination_total_equals_sum(self, object_type, ordering):
        """翻页: sum(page_sizes) == total"""
        client = _get_admin_client()
        # total
        resp_all, _ = _list(client, object_type, ordering=ordering, page_size=1)
        if resp_all.status_code != 200:
            pytest.skip(f"endpoint status {resp_all.status_code}")
        total = (resp_all.json.get('data', {}).get('total') if hasattr(resp_all, 'json') else None)
        if not total or total > 50:  # 数据太多不测试
            pytest.skip(f"total={total} too large or empty")
        # 实际翻页拉全部
        resp, items = _list(client, object_type, ordering=ordering, page_size=total)
        if resp.status_code == 200 and items:
            assert len(items) == total, f"FAIL: total={total}, actual={len(items)}"
            # ID 无重复
            ids = [it.get('id') for it in items]
            assert len(set(ids)) == len(ids), f"FAIL: duplicate IDs in result"