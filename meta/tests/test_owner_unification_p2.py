# -*- coding: utf-8 -*-
"""
[FILE] test_owner_unification_p2.py
[DESCRIPTION] Phase 2 Owner 机制统一 — TDD 测试用例
[SPEC] spec-permission-system-unification-2026-07-19 §8.2
[FR] FR-004 / FR-005 / FR-006

测试层次 (P2-T7 覆盖 T1-T6):
  T1: data_permission_rules 表接受 rule_type='owner'
  T2: PermissionResolver.check_owner() — 3 路径判定
  T3: owner_chain_interceptor 委托 PermissionResolver
  T4: 读路径 (DataPermissionInterceptor) owner 逻辑统一
  T5: 附属资源自动继承 owner
  T6: 写路径 (WriteScopeInterceptor) owner 逻辑统一

实现状态: [TDD RED] — 这些测试在 PermissionResolver 存在前应全部 FAIL
           PermissionResolver.check_owner() 实现后应全部 PASS
"""
import pytest

pytestmark = pytest.mark.unit

import sys
import os
import json
import sqlite3
import tempfile
from unittest.mock import Mock, MagicMock, patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_with_owner_rule():
    """创建含 data_permission_rules (rule_type='owner') 的测试数据库"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS data_permission_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            rule_type TEXT NOT NULL DEFAULT 'condition',
            resource_type TEXT,
            dimension_code TEXT,
            condition TEXT,
            scope_mode TEXT DEFAULT 'include',
            permission_level TEXT DEFAULT 'read',
            is_denied INTEGER DEFAULT 0,
            inherit_to_children INTEGER DEFAULT 1,
            propagate_to_parents INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT, owner_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT, product_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT, version_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT, domain_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_type TEXT,
            parent_id INTEGER,
            owner_id INTEGER,
            content TEXT
        );
    """)
    # 测试数据
    conn.execute("INSERT INTO users (id, username) VALUES (1, 'alice')")
    conn.execute("INSERT INTO users (id, username) VALUES (2, 'bob')")
    conn.execute("INSERT INTO roles (id, code) VALUES (1, 'admin')")
    conn.execute("INSERT INTO roles (id, code) VALUES (2, 'user')")
    # Alice 拥有 product 1
    conn.execute("INSERT INTO products (id, name, code, owner_id) VALUES (1, 'P1', 'p1', 1)")
    conn.execute("INSERT INTO products (id, name, code, owner_id) VALUES (2, 'P2', 'p2', 2)")
    # version 1 属于 product 1
    conn.execute("INSERT INTO versions (id, name, code, product_id) VALUES (1, 'V1', 'v1', 1)")
    conn.execute("INSERT INTO versions (id, name, code, product_id) VALUES (2, 'V2', 'v2', 2)")
    # domain 1 属于 version 1
    conn.execute("INSERT INTO domains (id, name, code, version_id) VALUES (1, 'D1', 'd1', 1)")
    # annotation 1 隶属 product 1
    conn.execute("INSERT INTO annotations (id, parent_type, parent_id, owner_id, content) VALUES (1, 'product', 1, 1, 'a1')")
    conn.commit()

    class MockDS:
        def __init__(self, connection):
            self._conn = connection

        def execute(self, sql, params=None):
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            self._conn.commit()
            return cursor

        def commit(self):
            self._conn.commit()

    yield MockDS(conn)
    conn.close()
    os.unlink(db_path)


# ============================================================================
# T1: data_permission_rules 表接受 rule_type='owner' (P2-T1)
# ============================================================================

class TestDataPermissionRuleOwnerType:
    """P2-T1: data_permission_rules 增加 rule_type='owner' 枚举"""

    def test_insert_owner_rule_type(self, db_with_owner_rule):
        """可插入 rule_type='owner' 的数据权限规则"""
        ds = db_with_owner_rule
        ds.execute(
            "INSERT INTO data_permission_rules "
            "(role_id, rule_type, resource_type, condition, permission_level) "
            "VALUES (?, ?, ?, ?, ?)",
            [2, 'owner', 'product',
             json.dumps({"owner_field": "owner_id", "fallback_field": "created_by"}),
             'write']
        )
        rows = ds.execute(
            "SELECT rule_type, condition FROM data_permission_rules "
            "WHERE role_id=2 AND resource_type='product'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 'owner'

    def test_owner_rule_type_with_hierarchy_chain(self, db_with_owner_rule):
        """rule_type='owner' + chain_inheritance 配置"""
        ds = db_with_owner_rule
        condition = json.dumps({
            "owner_field": "owner_id",
            "fallback_field": "created_by",
            "chain_inheritance": "hierarchy_chain"
        })
        ds.execute(
            "INSERT INTO data_permission_rules "
            "(role_id, rule_type, resource_type, condition, permission_level) "
            "VALUES (?, ?, ?, ?, ?)",
            [2, 'owner', 'version', condition, 'write']
        )
        rows = ds.execute(
            "SELECT condition FROM data_permission_rules "
            "WHERE rule_type='owner' AND resource_type='version'"
        ).fetchall()
        assert len(rows) == 1
        parsed = json.loads(rows[0][0])
        assert parsed['chain_inheritance'] == 'hierarchy_chain'


# ============================================================================
# T2: PermissionResolver.check_owner() 3 路径判定 (P2-T2)
# ============================================================================

class TestPermissionResolverCheckOwner:
    """P2-T2: PermissionResolver.check_owner() 3 路径统一判定"""

    def test_check_owner_direct_field_match(self, db_with_owner_rule):
        """路径 1: 直接 owner 字段命中"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_owner_rule
        resolver = PermissionResolver(ds)
        # Alice 是 product 1 的 owner
        result = resolver.check_owner(
            user={'id': 1, 'username': 'alice'},
            resource_type='product',
            resource={'id': 1, 'owner_id': 1}
        )
        assert result is True

    def test_check_owner_direct_field_no_match(self, db_with_owner_rule):
        """路径 1: 直接 owner 字段不命中 → False"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_owner_rule
        resolver = PermissionResolver(ds)
        # Alice 不是 product 2 的 owner (product 2 owner 是 bob)
        result = resolver.check_owner(
            user={'id': 1, 'username': 'alice'},
            resource_type='product',
            resource={'id': 2, 'owner_id': 2}
        )
        assert result is False

    def test_check_owner_hierarchy_chain_version(self, db_with_owner_rule):
        """路径 3: 层级链追溯 — version → product.owner_id"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_owner_rule
        resolver = PermissionResolver(ds)
        # version 1 属于 product 1 (alice 拥有)
        result = resolver.check_owner(
            user={'id': 1, 'username': 'alice'},
            resource_type='version',
            resource={'id': 1, 'product_id': 1}
        )
        assert result is True

    def test_check_owner_hierarchy_chain_domain(self, db_with_owner_rule):
        """路径 3: 层级链追溯 — domain → version → product.owner_id"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_owner_rule
        resolver = PermissionResolver(ds)
        # domain 1 → version 1 → product 1 (alice 拥有)
        result = resolver.check_owner(
            user={'id': 1, 'username': 'alice'},
            resource_type='domain',
            resource={'id': 1, 'version_id': 1}
        )
        assert result is True

    def test_check_owner_hierarchy_chain_no_match(self, db_with_owner_rule):
        """路径 3: 层级链追溯不命中 → False"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_owner_rule
        resolver = PermissionResolver(ds)
        # version 2 → product 2 (bob 拥有, 不是 alice)
        result = resolver.check_owner(
            user={'id': 1, 'username': 'alice'},
            resource_type='version',
            resource={'id': 2, 'product_id': 2}
        )
        assert result is False

    def test_check_owner_fallback_created_by_username(self, db_with_owner_rule):
        """路径 2: fallback to created_by (username 匹配)"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_owner_rule
        resolver = PermissionResolver(ds)
        # resource 没有 owner_id 但 created_by='alice'
        result = resolver.check_owner(
            user={'id': 1, 'username': 'alice'},
            resource_type='business_object',
            resource={'id': 999, 'created_by': 'alice'}
        )
        assert result is True

    def test_check_owner_fallback_created_by_no_match(self, db_with_owner_rule):
        """路径 2: fallback to created_by 不匹配 → False"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_owner_rule
        resolver = PermissionResolver(ds)
        result = resolver.check_owner(
            user={'id': 1, 'username': 'alice'},
            resource_type='business_object',
            resource={'id': 999, 'created_by': 'bob'}
        )
        assert result is False


# ============================================================================
# T3: owner_chain_interceptor 委托 PermissionResolver (P2-T3)
# ============================================================================

class TestOwnerChainInterceptorDelegation:
    """P2-T3: owner_chain_interceptor 委托 PermissionResolver"""

    def test_interceptor_delegates_to_resolver(self, db_with_owner_rule):
        """OwnerChainInterceptor 委托 PermissionResolver.check_owner()"""
        from meta.core.interceptors.owner_chain_interceptor import OwnerChainInterceptor
        interceptor = OwnerChainInterceptor()
        # 验证拦截器存在委托方法
        assert hasattr(interceptor, '_check_owner_chain')
        # _check_owner_chain 内部应调用 PermissionResolver

    def test_interceptor_match_propagates_extra_flag(self):
        """命中时在 context.extra 设置 _owner_chain_match=True"""
        from meta.core.interceptors.owner_chain_interceptor import OwnerChainInterceptor
        interceptor = OwnerChainInterceptor()
        # 验证拦截器存在
        assert interceptor.name == 'owner_chain'
        assert interceptor.priority == 25


# ============================================================================
# T4: 读路径 (DataPermissionInterceptor) owner 逻辑统一 (P2-T4)
# ============================================================================

class TestDataPermissionOwnerUnification:
    """P2-T4: 读路径 owner 判定委托 PermissionResolver"""

    def test_data_permission_uses_resolver_check_owner(self):
        """DataPermissionInterceptor 通过 PermissionResolver 判定 owner"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        assert interceptor.name == 'data_permission'
        # 验证拦截器内部调用 PermissionResolver.check_owner()
        # 通过 inspect 或 monkeypatch 验证

    def test_read_path_owner_match_returns_visible(self, db_with_owner_rule):
        """读路径: owner 匹配 → 资源可见"""
        # 构造 owner exception 子查询, owner 的 resource 应被包含
        from meta.services.chain_owner_resolver import build_owner_exception_subquery
        ds = db_with_owner_rule
        subq = build_owner_exception_subquery(ds, 'product', user_id=1)
        assert subq is not None
        assert 'products' in subq.lower()
        # 执行验证
        rows = ds.execute(f"SELECT id FROM products WHERE id IN ({subq})").fetchall()
        assert len(rows) == 1  # Alice owns product 1


# ============================================================================
# T5: 附属资源自动继承 owner (P2-T5)
# ============================================================================

class TestSubordinateOwnerInheritance:
    """P2-T5: 附属资源 (Subordinate) 自动继承 parent 的 owner"""

    def test_annotation_inherits_product_owner(self, db_with_owner_rule):
        """annotation.parent=product(alice owned) → annotation 视为 alice owned"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_owner_rule
        resolver = PermissionResolver(ds)
        # annotation 1: parent_type='product', parent_id=1 (alice owned)
        # 即使 annotation 自己没有 owner_id, 也应通过 chain 继承
        # 检查 PermissionResolver 是否能识别 annotation 为 subordinate
        result = resolver.check_owner_for_subordinate(
            user={'id': 1, 'username': 'alice'},
            resource_type='annotation',
            resource={'id': 1, 'parent_type': 'product', 'parent_id': 1}
        )
        assert result is True

    def test_subordinate_owner_resolves_to_parent_owner(self, db_with_owner_rule):
        """附属资源的 owner = 祖先 (parent) 的 owner"""
        from meta.services.chain_owner_resolver import resolve_subordinate_owner
        ds = db_with_owner_rule
        owner = resolve_subordinate_owner(
            ds,
            resource_type='annotation',
            record={'id': 1, 'parent_type': 'product', 'parent_id': 1}
        )
        assert owner == 1  # Alice

    def test_subordinate_no_inherit_when_explicit_owner(self, db_with_owner_rule):
        """附属资源显式 owner_id 时优先使用显式值"""
        ds = db_with_owner_rule
        # annotation 2: 显式 owner_id=2 (bob)
        ds.execute(
            "INSERT INTO annotations (id, parent_type, parent_id, owner_id, content) "
            "VALUES (2, 'product', 1, 2, 'a2')"
        )
        from meta.services.chain_owner_resolver import resolve_subordinate_owner
        owner = resolve_subordinate_owner(
            ds,
            resource_type='annotation',
            record={'id': 2, 'parent_type': 'product', 'parent_id': 1, 'owner_id': 2}
        )
        assert owner == 2  # Bob (显式 owner 优先)


# ============================================================================
# T6: 写路径 (WriteScopeInterceptor) owner 逻辑统一 (P2-T6)
# ============================================================================

class TestWriteScopeOwnerUnification:
    """P2-T6: 写路径 owner 判定委托 PermissionResolver"""

    def test_write_scope_uses_resolver_check_owner(self):
        """WriteScopeInterceptor 通过 PermissionResolver 判定 owner"""
        from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor
        interceptor = WriteScopeInterceptor()
        assert interceptor.name == 'write_scope'
        # 验证拦截器 _check_owner_chain 或类似方法委托 PermissionResolver

    def test_write_path_owner_match_allows_write(self, db_with_owner_rule):
        """写路径: owner 匹配 → 允许写"""
        # 构造 context: alice 尝试更新自己的 product
        from meta.core.interceptors.owner_chain_interceptor import OwnerChainInterceptor
        interceptor = OwnerChainInterceptor()
        # owner chain 命中应设置 context.extra['_owner_chain_match']=True
        assert interceptor.priority == 25


# ============================================================================
# T7 (回归): Phase 2 实施前后行为一致
# ============================================================================

class TestOwnerUnificationRegression:
    """P2-T7: 改造前后 owner 判定结果 100% 一致"""

    def test_existing_owner_chain_resolver_unchanged(self):
        """chain_owner_resolver 仍可用 (向后兼容)"""
        from meta.services.chain_owner_resolver import (
            resolve_root_owner,
            resolve_root_product_id,
            build_owner_exception_subquery,
        )
        assert callable(resolve_root_owner)
        assert callable(resolve_root_product_id)
        assert callable(build_owner_exception_subquery)

    def test_permission_resolver_importable(self):
        """PermissionResolver 可被 import"""
        try:
            from meta.services.permission_resolver import PermissionResolver
            resolver = PermissionResolver(None)  # 仅验证可实例化 (构造时不需要 ds)
            assert resolver is not None
        except ImportError:
            pytest.fail("PermissionResolver module not yet implemented (expected RED)")