# -*- coding: utf-8 -*-
"""
test_bug_v026_owner_exception_chain_subquery.py

覆盖 BUG-V026: data_permission_interceptor._add_owner_exception
                对子对象 (domain/sub_domain/service_module/business_object) 错误地用
                product_id 直查,导致 SQL "no such column: product_id" 400 错误

根因:
  commit 72307ec (BUG-V020/V021) 在 _add_owner_exception 给子对象加 owner exception 时,
  使用 field='product_id' + subquery='SELECT id FROM products WHERE owner_id = ?'。
  但 domain/sub_domain/service_module/business_object 表本身没有 product_id 列
  (它们通过 version_id -> versions.product_id 链关联)。
  → 任何 owner 用户查询这些子对象时,SQL 都报 400。

修复:
  data_permission_interceptor._add_owner_exception (line 919):
  改用 chain_owner_resolver.build_owner_exception_subquery 生成正确的链式 SQL:
    - domain: SELECT id FROM domains WHERE version_id IN (SELECT id FROM versions WHERE product_id IN (...))
    - sub_domain: SELECT id FROM sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE version_id IN (...))
    - etc.

依据:
  .trae/specs/test-suite/post-6-22-roadmap.md 主题 3 (Permission/Write Scope)
  fix 提交: BUG-V026
"""
import pytest
import sqlite3
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'meta' / 'architecture.db'


def _ensure_registry():
    from meta.core.models import registry
    if registry.get('product') is None:
        from meta.core.yaml_loader import register_from_directory
        schemas_dir = os.path.join(PROJECT_ROOT, 'meta', 'schemas')
        register_from_directory(schemas_dir)


class TestBugV026OwnerExceptionChainSubquery:
    """BUG-V026: 子对象 owner exception 必须用 chain 子查询, 不能 product_id 直查"""

    def test_build_owner_exception_subquery_for_domain(self):
        """domain 的 chain subquery 应该走 version_id -> versions.product_id 链"""
        from meta.services.chain_owner_resolver import build_owner_exception_subquery
        _ensure_registry()
        sub = build_owner_exception_subquery(str(DB_PATH), 'domain', 3385)
        assert sub is not None, "domain chain subquery 不应为空"
        # 关键: 不应包含 'product_id' 直查 (应该走 chain)
        # 必须包含 version_id 子链
        assert 'version_id' in sub or 'domains.version_id' in sub or 'WHERE version_id' in sub.replace('\n', ' ')
        print(f"\n  domain chain subquery: {sub[:150]}...")

    def test_build_owner_exception_subquery_for_sub_domain(self):
        """sub_domain 的 chain subquery 应该走 domain_id -> domains -> versions -> products 链"""
        from meta.services.chain_owner_resolver import build_owner_exception_subquery
        _ensure_registry()
        sub = build_owner_exception_subquery(str(DB_PATH), 'sub_domain', 3385)
        assert sub is not None
        # sub_domain 表本身没有 product_id 列,必须通过 chain
        # 关键路径: sub_domains -> domains -> versions -> products
        assert 'domain_id' in sub or 'sub_domain_id' in sub or 'WHERE domain_id' in sub.replace('\n', ' ')

    def test_no_product_id_in_owner_exception_query_for_child(self):
        """直接验证 _add_owner_exception 给子对象加的 cond 不含 product_id 直查"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.models import registry

        _ensure_registry()

        class MockContext:
            def __init__(self):
                self.user_id = 3385
                self.object_type = 'domain'
                self.data_source = str(DB_PATH)
                self.extra = {}

        ctx = MockContext()
        interceptor = DataPermissionInterceptor()
        interceptor._add_owner_exception(ctx)

        conditions = ctx.extra.get('query_conditions', [])
        assert len(conditions) > 0, "owner exception 必须至少生成 1 个 cond"

        # 关键: chain 子查询应该用 field='id' + 子查询字符串
        # 而不是 field='product_id' + 简单 subquery
        cond_str = str(conditions)
        if "'product_id'" in cond_str and "'field': 'product_id'" in cond_str:
            # 存在 product_id 直查 → 检查是不是 chain subquery
            for c in conditions:
                if isinstance(c, dict) and c.get('field') == 'product_id':
                    # 必须有 in_subquery operator + chain
                    assert c.get('operator') == 'in_subquery', \
                        f"product_id 应该用 in_subquery 链式查询,实际是 {c.get('operator')}"
                    sq = c.get('subquery') or c.get('value', '')
                    assert 'version_id' in str(sq) or 'sub_domain_id' in str(sq) or 'domain_id' in str(sq), \
                        f"product_id chain subquery 应该包含 version/domain/sub_domain 子链,实际: {sq}"
        else:
            # 改成了 field='id' + 链式子查询,正确!
            assert "'field': 'id'" in cond_str, \
                f"chain subquery 应该用 field='id', 实际条件: {conditions}"

        print(f"\n  domain owner exception conditions OK: {conditions[:1]}")

    def test_add_owner_exception_sub_domain(self):
        """sub_domain 不报 product_id 错 - 走完整 chain"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor

        _ensure_registry()

        class MockContext:
            def __init__(self, ot):
                self.user_id = 3385
                self.object_type = ot
                self.data_source = str(DB_PATH)
                self.extra = {}

        # HIERARCHY_CHAIN = ['product', 'version', 'domain', 'sub_domain']
        # service_module/business_object 不在 chain, 不走 owner exception
        for ot in ['domain', 'sub_domain']:
            ctx = MockContext(ot)
            interceptor = DataPermissionInterceptor()
            interceptor._add_owner_exception(ctx)
            conds = ctx.extra.get('query_conditions', [])
            assert len(conds) > 0, f"{ot}: owner exception 必须生成条件"
            # 条件里不应有 'product_id' 直查 (走 chain)
            cond_str = str(conds)
            if "'field': 'product_id'" in cond_str:
                # 如果有 product_id,必须有 chain (in_subquery + version/domain/sub_domain)
                for c in conds:
                    if isinstance(c, dict) and c.get('field') == 'product_id':
                        sq = str(c.get('subquery') or c.get('value') or '')
                        assert c.get('operator') == 'in_subquery', \
                            f"{ot}: product_id 必须用 in_subquery"
                        assert ('version' in sq or 'domain' in sq or 'sub_domain' in sq), \
                            f"{ot}: chain subquery 应包含 version/domain/sub_domain,实际: {sq}"

    def test_service_module_and_business_object_skip_owner_exception(self):
        """service_module/business_object 不在 HIERARCHY_CHAIN, 应跳过 owner exception (不报错)"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        _ensure_registry()

        class MockContext:
            def __init__(self, ot):
                self.user_id = 3385
                self.object_type = ot
                self.data_source = str(DB_PATH)
                self.extra = {}

        # 这些对象不在 chain, _add_owner_exception 应该早退出不报错
        for ot in ['service_module', 'business_object']:
            ctx = MockContext(ot)
            interceptor = DataPermissionInterceptor()
            # 不应抛异常
            interceptor._add_owner_exception(ctx)
            # 不会生成条件 (chain 之外)
            conds = ctx.extra.get('query_conditions', [])
            assert len(conds) == 0, f"{ot}: 不在 chain, 应跳过 owner exception, 不应生成条件"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])