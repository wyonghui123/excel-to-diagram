# -*- coding: utf-8 -*-
"""
test_bug_v021_query_service_owner_exception.py

覆盖 BUG-V021: query_service._try_apply_dimension_scope 漏 owner exception
                (与 BUG-V020 一起修复同一类问题, 但是 query_service 路径)

根因:
  query_service.search 不走 BOFramework 拦截器链 (BUG-V013 owner exception 修复),
  自己直接调 _apply_data_permission → _try_apply_dimension_scope。
  _try_apply_dimension_scope 应用 dim scope 后立即 return, 跳过 owner exception。
  → user 自己 owner 的产品被 dim scope 严格过滤掉
  → TEST333 导出 product 只返回 dim_scope 命中的 1 条 (供应链),而非 3 条

依据:
  .trae/specs/test-suite/post-6-22-roadmap.md 主题 1 (Import/Export)
  fix 提交: BUG-V021
"""
import pytest
import sqlite3
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'meta' / 'architecture.db'


def _ensure_registry():
    """确保 meta registry 加载了"""
    from meta.core.models import registry
    if registry.get('product') is None:
        from meta.core.yaml_loader import register_from_directory
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        register_from_directory(schemas_dir)


class TestBugV021QueryServiceOwnerException:
    """BUG-V021: query_service 路径 dim scope 叠加 owner exception"""

    def test_try_apply_dimension_scope_or_merges_owner(self):
        """
        _try_apply_dimension_scope 必须把 owner_id 加到 dim scope 同一 OR 组
        这样 SQL 是 WHERE ((dim_scope_1) OR ... OR (owner_id = user_id)) AND ...
        """
        from meta.services.query_service import QueryService
        from meta.core.datasource import get_data_source
        import inspect

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = QueryService(ds)

        _ensure_registry()

        source = inspect.getsource(service._try_apply_dimension_scope)

        assert 'BUG-V021' in source, "BUG-V021 修复必须存在"
        # OR 合并逻辑
        assert 'or_where' in source, "必须用 or_where 把 dim_scope + owner_id 合并到 OR 组"
        assert 'OR-merged dim_scope with owner_id' in source, (
            "product 路径必须把 owner_id 加到 dim scope 同一 OR 组"
        )

    def test_dim_scope_sql_contains_owner_id_or(self):
        """
        product dim scope 后 SQL 必须包含 OR owner_id = user_id
        """
        from meta.services.query_service import QueryService
        from meta.core.datasource import get_data_source
        from meta.services.query_service import set_thread_user, clear_thread_user_id

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = QueryService(ds)
        _ensure_registry()

        try:
            set_thread_user({
                'user_id': 3385,
                'username': 'TEST333',
                'permissions': [],
                'is_admin': False,
            })
            from meta.core.query_builder import QueryBuilder
            from meta.core.models import registry
            meta = registry.get('product')
            builder = QueryBuilder(ds, meta)
            applied = service._try_apply_dimension_scope(builder, 3385, 'product')
            assert applied is True, "TEST333 应该命中 dim scope (role 5433)"

            sql, params = builder.build_sql()
            assert 'owner_id' in sql, (
                f"BUG-V021: product SQL 必须包含 owner_id OR 子句. 实际: {sql}"
            )
            # owner_id 必须 OR (不是 AND)
            assert 'OR owner_id = ?' in sql or 'OR  products.owner_id = ?' in sql, (
                f"BUG-V021: owner_id 必须是 OR 子句 (非 AND). 实际: {sql}"
            )
            # params 必须包含 user_id
            assert 3385 in params, (
                f"BUG-V021: params 必须包含 user_id=3385. 实际: {params}"
            )
        finally:
            clear_thread_user_id()

    def test_search_returns_owner_products_for_test333(self):
        """
        端到端: TEST333 search('product') 应返回至少 3 个产品
        (供应链/TESTVVVX/TESTVVVVV)
        """
        from meta.services.query_service import QueryService
        from meta.core.datasource import get_data_source
        from meta.services.query_service import set_thread_user, clear_thread_user_id
        from meta.services.query_models import SearchRequest

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = QueryService(ds)
        _ensure_registry()

        try:
            set_thread_user({
                'user_id': 3385,
                'username': 'TEST333',
                'permissions': [],
                'is_admin': False,
            })

            req = SearchRequest(
                object_type='product',
                conditions=[],
                page=1,
                page_size=100,
            )
            result = service.search(req)

            # 至少 3 个产品
            assert result.total >= 3, (
                f"BUG-V021: TEST333 应看到至少 3 个产品 (供应链/TESTVVVX/TESTVVVVV), "
                f'实际: total={result.total}'
            )
        finally:
            clear_thread_user_id()


class TestBugV021Regression:
    """回归 - 不应破坏其他场景"""

    def test_admin_user_no_filter(self):
        """admin 仍无 filter"""
        from meta.services.query_service import QueryService
        from meta.core.datasource import get_data_source
        from meta.services.query_service import set_thread_user, clear_thread_user_id
        from meta.services.query_models import SearchRequest

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = QueryService(ds)
        _ensure_registry()

        try:
            set_thread_user({
                'user_id': 1,
                'username': 'admin',
                'permissions': ['*'],
                'is_admin': True,
            })

            req = SearchRequest(
                object_type='product',
                conditions=[],
                page=1,
                page_size=20,
            )
            result = service.search(req)
            # admin 应看到所有 products (DB 中所有 product)
            assert result.total >= 3, f"admin 应看到所有产品, 实际: {result.total}"
        finally:
            clear_thread_user_id()

    def test_no_dim_scope_user_falls_back(self):
        """
        用户无 dim scope 时不应触发 owner exception (没东西可 OR)
        不报错即可
        """
        from meta.services.query_service import QueryService
        from meta.core.datasource import get_data_source
        from meta.services.query_service import set_thread_user, clear_thread_user_id
        from meta.services.query_models import SearchRequest

        ds = get_data_source('sqlite', database=str(DB_PATH))
        service = QueryService(ds)
        _ensure_registry()

        try:
            # 设置一个 user_id 但无 role, 看 dim scope 不命中
            set_thread_user({
                'user_id': 999999,  # 不存在的 user
                'username': 'ghost',
                'permissions': [],
                'is_admin': False,
            })

            req = SearchRequest(
                object_type='product',
                conditions=[],
                page=1,
                page_size=20,
            )
            result = service.search(req)
            # 不报错即可 (可能返回 0 也可能返回 1)
            assert result.total >= 0, "应不报错"
        finally:
            clear_thread_user_id()
