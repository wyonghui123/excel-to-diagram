# -*- coding: utf-8 -*-
"""
[FILE] test_chain_owner_resolver.py
[DESCRIPTION] chain_owner_resolver v1.1.5 单元测试
[COVERAGE]
  - is_in_chain 边界 (4 个 chain BO + 业务外 BO)
  - resolve_root_owner (product / version / domain / sub_domain / 业务外)
  - resolve_root_product_id (同上)
  - build_owner_exception_subquery (4 种 BO 的 SQL 形态)
  - SQL 注入防护 (user_id 必须 int)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from meta.services.chain_owner_resolver import (
    is_in_chain,
    HIERARCHY_CHAIN,
    PARENT_FIELD_MAP,
    RESOURCE_TABLE_MAP,
    build_owner_exception_subquery,
)


# Mock DataSource
class MockDataSource:
    def __init__(self, rows_by_query=None):
        self.rows_by_query = rows_by_query or {}
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        sql_lower = sql.lower()
        for key, rows in self.rows_by_query.items():
            if key in sql_lower:
                return MockCursor(rows)
        return MockCursor([])


class MockCursor:
    def __init__(self, rows):
        self._rows = rows
    def fetchone(self):
        return self._rows[0] if self._rows else None
    def fetchall(self):
        return self._rows


# ============================================================================
# is_in_chain
# ============================================================================
class TestIsInChain:
    def test_product_in_chain(self):
        assert is_in_chain('product') is True

    def test_version_in_chain(self):
        assert is_in_chain('version') is True

    def test_domain_in_chain(self):
        assert is_in_chain('domain') is True

    def test_sub_domain_in_chain(self):
        assert is_in_chain('sub_domain') is True

    def test_relationship_not_in_chain(self):
        """[v1.1.5] 业务外 BO 不在 HIERARCHY_CHAIN"""
        assert is_in_chain('relationship') is False

    def test_business_object_not_in_chain(self):
        """[v1.1.5] business_object 也不在 (已从 chain 移除)"""
        assert is_in_chain('business_object') is False

    def test_hierarchy_chain_order(self):
        """链顺序: product → version → domain → sub_domain (顶层到底层)"""
        assert HIERARCHY_CHAIN == ['product', 'version', 'domain', 'sub_domain']

    def test_parent_field_map_correct(self):
        assert PARENT_FIELD_MAP['version'] == 'product_id'
        assert PARENT_FIELD_MAP['domain'] == 'version_id'
        assert PARENT_FIELD_MAP['sub_domain'] == 'domain_id'

    def test_resource_table_map_correct(self):
        assert RESOURCE_TABLE_MAP['product'] == 'products'
        assert RESOURCE_TABLE_MAP['version'] == 'versions'
        assert RESOURCE_TABLE_MAP['domain'] == 'domains'
        assert RESOURCE_TABLE_MAP['sub_domain'] == 'sub_domains'


# ============================================================================
# resolve_root_owner
# ============================================================================
class TestResolveRootOwner:
    def test_product_owner_direct(self):
        """product: 直接查 products.owner_id"""
        ds = MockDataSource(rows_by_query={'from products': [(333,)]})
        from meta.services.chain_owner_resolver import resolve_root_owner
        result = resolve_root_owner(ds, 'product', 1)
        assert result == 333
        assert len(ds.executed) == 1

    def test_version_uses_chain(self):
        """version: 沿 chain 查 product.owner_id (单次 SQL)"""
        ds = MockDataSource(rows_by_query={'from products': [(333,)]})
        from meta.services.chain_owner_resolver import resolve_root_owner
        result = resolve_root_owner(ds, 'version', 766)
        assert result == 333
        # 关键: 只 1 次 SQL
        assert len(ds.executed) == 1

    def test_domain_uses_chain(self):
        """domain: 沿 chain (domain→version→product) 查 product.owner_id"""
        ds = MockDataSource(rows_by_query={'from products': [(3385,)]})
        from meta.services.chain_owner_resolver import resolve_root_owner
        result = resolve_root_owner(ds, 'domain', 50)
        assert result == 3385
        assert len(ds.executed) == 1

    def test_sub_domain_uses_chain(self):
        """sub_domain: 沿 chain (sub→domain→version→product) 查 product.owner_id"""
        ds = MockDataSource(rows_by_query={'from products': [(3385,)]})
        from meta.services.chain_owner_resolver import resolve_root_owner
        result = resolve_root_owner(ds, 'sub_domain', 100)
        assert result == 3385
        assert len(ds.executed) == 1

    def test_relationship_returns_none(self):
        """[v1.1.5] 业务外 BO (relationship) 返回 None, caller 走 created_by fallback"""
        ds = MockDataSource()
        from meta.services.chain_owner_resolver import resolve_root_owner
        result = resolve_root_owner(ds, 'relationship', 1)
        assert result is None
        # 关键: 不查 DB
        assert len(ds.executed) == 0

    def test_zero_id_returns_none(self):
        """record_id=0 返回 None (避免误查)"""
        ds = MockDataSource()
        from meta.services.chain_owner_resolver import resolve_root_owner
        result = resolve_root_owner(ds, 'version', 0)
        assert result is None
        assert len(ds.executed) == 0

    def test_no_match_returns_none(self):
        """无记录时返回 None"""
        ds = MockDataSource()  # 空 rows
        from meta.services.chain_owner_resolver import resolve_root_owner
        result = resolve_root_owner(ds, 'version', 999)
        assert result is None


# ============================================================================
# resolve_root_product_id
# ============================================================================
class TestResolveRootProductId:
    def test_product_returns_self(self):
        """product 直接返回 record_id"""
        from meta.services.chain_owner_resolver import resolve_root_product_id
        result = resolve_root_product_id(MockDataSource(), 'product', 1)
        assert result == 1

    def test_version_chain(self):
        """version 查 product_id"""
        ds = MockDataSource(rows_by_query={'from versions': [(476,)]})
        from meta.services.chain_owner_resolver import resolve_root_product_id
        result = resolve_root_product_id(ds, 'version', 766)
        assert result == 476

    def test_domain_chain(self):
        """domain 沿 chain 查 product_id"""
        ds = MockDataSource(rows_by_query={'from domains': [(476,)]})
        from meta.services.chain_owner_resolver import resolve_root_product_id
        result = resolve_root_product_id(ds, 'domain', 50)
        assert result == 476

    def test_relationship_returns_none(self):
        from meta.services.chain_owner_resolver import resolve_root_product_id
        result = resolve_root_product_id(MockDataSource(), 'relationship', 1)
        assert result is None


# ============================================================================
# build_owner_exception_subquery (核心, 用于 _add_owner_exception)
# ============================================================================
class TestBuildOwnerExceptionSubquery:
    def test_product_subquery(self):
        """[v1.1.5 BUG FIX] product: 纯子查询 (不带 id IN 前缀)"""
        ds = MockDataSource()
        result = build_owner_exception_subquery(ds, 'product', 333)
        expected = "SELECT id FROM products WHERE owner_id = 333"
        assert result == expected

    def test_version_subquery(self):
        """[v1.1.5 BUG FIX] version: 纯子查询"""
        ds = MockDataSource()
        result = build_owner_exception_subquery(ds, 'version', 333)
        expected = (
            "SELECT id FROM versions "
            "WHERE product_id IN (SELECT id FROM products WHERE owner_id = 333)"
        )
        assert result == expected

    def test_domain_subquery(self):
        """[v1.1.5 BUG FIX] domain: 3 层嵌套纯子查询"""
        ds = MockDataSource()
        result = build_owner_exception_subquery(ds, 'domain', 333)
        expected = (
            "SELECT id FROM domains "
            "WHERE version_id IN ("
            "  SELECT id FROM versions "
            "  WHERE product_id IN (SELECT id FROM products WHERE owner_id = 333)"
            ")"
        )
        assert result == expected

    def test_sub_domain_subquery(self):
        """[v1.1.5 BUG FIX] sub_domain: 4 层嵌套纯子查询"""
        ds = MockDataSource()
        result = build_owner_exception_subquery(ds, 'sub_domain', 333)
        expected = (
            "SELECT id FROM sub_domains "
            "WHERE domain_id IN ("
            "  SELECT id FROM domains "
            "  WHERE version_id IN ("
            "    SELECT id FROM versions "
            "    WHERE product_id IN (SELECT id FROM products WHERE owner_id = 333)"
            "  )"
            ")"
        )
        assert result == expected

    def test_relationship_returns_none(self):
        """[v1.1.5] 业务外 BO (relationship) 返回 None"""
        ds = MockDataSource()
        result = build_owner_exception_subquery(ds, 'relationship', 333)
        assert result is None

    def test_zero_user_id_returns_none(self):
        """user_id=0 返回 None"""
        ds = MockDataSource()
        result = build_owner_exception_subquery(ds, 'version', 0)
        assert result is None

    def test_user_id_int_casting(self):
        """user_id 强制 int, 防止 SQL 注入"""
        ds = MockDataSource()
        result = build_owner_exception_subquery(ds, 'version', '333')  # str
        assert 'WHERE owner_id = 333' in result  # 转成 int

    def test_subquery_uses_index_id(self):
        """[v1.1.5] 关键: 子查询用 id (不是 owner_id)"""
        result = build_owner_exception_subquery(MockDataSource(), 'version', 333)
        # 必须用 id (代表 versions 表的 id), 不是 product_id
        assert 'SELECT id FROM versions' in result

    def test_no_id_in_prefix_in_value(self):
        """[v1.1.5 BUG FIX 验证] value 不应含 'id IN' 前缀

        之前版本会返回 'id IN (SELECT ...)', 配合 persistence 渲染
        变成 'id IN (id IN (SELECT ...))' 语法错误.
        """
        result = build_owner_exception_subquery(MockDataSource(), 'version', 333)
        assert not result.startswith('id IN'), \
            f'value 不应以 "id IN" 开头, 实际: {result[:30]!r}'


# ============================================================================
# [v1.1.5] 集成场景: 模拟 TEST333 创建 V10 后能见
# ============================================================================
class TestTest333Scenario:
    """[v1.1.5] 模拟用户报告的 bug 场景: TEST333 创建 product 476 + V10"""

    def test_v10_owner_exception_subquery(self):
        """[v1.1.5 BUG 修复] TEST333 (user_id=3385) 读 V10 (version 766) 时
        构造的 owner 例外 SQL 应能匹配"""
        ds = MockDataSource()
        # version subquery: 测试 TEST333 user
        result = build_owner_exception_subquery(ds, 'version', 3385)
        # 实际查询时拼成: WHERE (...) OR (id IN (SELECT id FROM versions WHERE product_id IN (SELECT id FROM products WHERE owner_id = 3385)))
        # 验证: TEST333 自己创建的 product 476 满足 owner_id=3385, V10 (id=766) 满足 product_id=476
        assert 'WHERE owner_id = 3385' in result
        assert 'SELECT id FROM versions' in result
        assert 'SELECT id FROM products' in result
        # [v1.1.5 BUG FIX] 不应有 'id IN' 前缀
        assert not result.startswith('id IN'), f'value 不应以 id IN 开头: {result[:30]!r}'
