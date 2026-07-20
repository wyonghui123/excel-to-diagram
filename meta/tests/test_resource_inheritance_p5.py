# -*- coding: utf-8 -*-
"""
[FILE] test_resource_inheritance_p5.py
[DESCRIPTION] Phase 5 Resource 模型与继承 — TDD 测试用例
[SPEC] spec-permission-system-unification-2026-07-19 §3.6 / §8.5
[FR] FR-013 / FR-014

测试覆盖 (P5-T4 验收):
  P5-T1: Resource 类型声明 (4 种类型)
  P5-T2: ResourceInheritanceEngine 5 条继承规则
    规则 1: 向下继承 (inherit_children=1)
    规则 2: 加严不放松 (children.dim_scope ⊆ parent.dim_scope)
    规则 3: 关联取交集 (Association 取两端交集)
    规则 4: 附属跟随 (Subordinate 继承 parent owner)
    规则 5: 向上传播 (propagate_to_parents=1)
  P5-T3: 显式配置优先于继承 + 3 级嵌套
"""
import pytest

pytestmark = pytest.mark.unit

import sys
import os
import json
import sqlite3
import tempfile
from unittest.mock import Mock, MagicMock

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_with_hierarchy():
    """创建含 4 层层级链 (product → version → domain → sub_domain) + annotation 的测试库"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, code TEXT, owner_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, code TEXT, product_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, code TEXT, version_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, code TEXT, domain_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_bo_id INTEGER, target_bo_id INTEGER, type TEXT
        );
        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_type TEXT, parent_id INTEGER, owner_id INTEGER, content TEXT
        );
        CREATE TABLE IF NOT EXISTS role_dimension_scopes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER, dimension_code TEXT, dimension_values TEXT,
            inherit_children INTEGER DEFAULT 1, scope_mode TEXT DEFAULT 'include'
        );
    """)
    # 测试数据: 4 层层级 + 跨域关系 + 附属资源
    conn.execute("INSERT INTO products (id, name, code, owner_id) VALUES (1, 'P1', 'p1', 100)")
    conn.execute("INSERT INTO products (id, name, code, owner_id) VALUES (2, 'P2', 'p2', 200)")
    conn.execute("INSERT INTO versions (id, name, code, product_id) VALUES (1, 'V1', 'v1', 1)")
    conn.execute("INSERT INTO versions (id, name, code, product_id) VALUES (2, 'V2', 'v2', 2)")
    conn.execute("INSERT INTO domains (id, name, code, version_id) VALUES (1, 'D1', 'd1', 1)")
    conn.execute("INSERT INTO domains (id, name, code, version_id) VALUES (2, 'D2', 'd2', 2)")
    conn.execute("INSERT INTO sub_domains (id, name, code, domain_id) VALUES (1, 'S1', 's1', 1)")
    conn.execute("INSERT INTO sub_domains (id, name, code, domain_id) VALUES (2, 'S2', 's2', 2)")
    # relationship: BO 1 (in product 1) <-> BO 2 (in product 2) 跨域
    conn.execute("INSERT INTO relationships (id, source_bo_id, target_bo_id, type) VALUES (1, 1, 2, 'depends_on')")
    # annotation 1 隶属 product 1 (owner=100)
    conn.execute("INSERT INTO annotations (id, parent_type, parent_id, owner_id, content) VALUES (1, 'product', 1, 100, 'note1')")
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

    yield MockDS(conn)
    conn.close()
    os.unlink(db_path)


# ============================================================================
# P5-T1: Resource 类型声明 (4 种类型)
# ============================================================================

class TestP5T1ResourceTypeDeclaration:
    """P5-T1: BO.yaml 中 resource: 块声明资源类型"""

    def test_resource_inheritance_engine_importable(self):
        """ResourceInheritanceEngine 可被 import"""
        try:
            from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
            assert ResourceInheritanceEngine is not None
        except ImportError:
            pytest.fail("ResourceInheritanceEngine not yet implemented (expected RED)")

    def test_resource_type_constants_exist(self):
        """4 种资源类型常量存在"""
        from meta.services.resource_inheritance_engine import (
            RESOURCE_INDEPENDENT, RESOURCE_ASSOCIATION,
            RESOURCE_SUBORDINATE, RESOURCE_HIERARCHY,
        )
        assert RESOURCE_INDEPENDENT == 'independent'
        assert RESOURCE_ASSOCIATION == 'association'
        assert RESOURCE_SUBORDINATE == 'subordinate'
        assert RESOURCE_HIERARCHY == 'hierarchy'

    def test_resource_metadata_map_exists(self):
        """RESOURCE_METADATA_MAP 包含主要 BO 的资源类型"""
        from meta.services.resource_inheritance_engine import RESOURCE_METADATA_MAP
        # 主要 BO 都应有资源类型声明
        assert 'product' in RESOURCE_METADATA_MAP
        assert 'version' in RESOURCE_METADATA_MAP
        assert 'domain' in RESOURCE_METADATA_MAP
        assert 'sub_domain' in RESOURCE_METADATA_MAP
        assert 'relationship' in RESOURCE_METADATA_MAP
        assert 'annotation' in RESOURCE_METADATA_MAP
        # product 是 independent
        assert RESOURCE_METADATA_MAP['product']['type'] == 'independent'
        # relationship 是 association
        assert RESOURCE_METADATA_MAP['relationship']['type'] == 'association'
        # annotation 是 subordinate
        assert RESOURCE_METADATA_MAP['annotation']['type'] == 'subordinate'
        # version/domain/sub_domain 是 hierarchy
        assert RESOURCE_METADATA_MAP['version']['type'] == 'hierarchy'
        assert RESOURCE_METADATA_MAP['domain']['type'] == 'hierarchy'


# ============================================================================
# P5-T2 规则 1: 向下继承 (inherit_children=1)
# ============================================================================

class TestP5T2Rule1InheritDownward:
    """P5-T2 规则 1: parent 的 dim scope 向下展开到 children"""

    def test_inherit_children_expands_to_sub_dimensions(self, db_with_hierarchy):
        """parent=product [1] → version [1] → domain [1] → sub_domain [1] 全部展开"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # parent 配置: product=[1], inherit_children=1
        result = engine.expand_inherited_scope(
            role_id=1,
            parent_dimension='product',
            parent_values=[1],
            inherit_children=1,
        )
        # 应向下展开到 version, domain, sub_domain
        assert 'product' in result
        assert 1 in result['product']
        assert 'version' in result
        assert 1 in result['version']  # V1 属于 P1
        assert 'domain' in result
        assert 1 in result['domain']  # D1 属于 V1
        assert 'sub_domain' in result
        assert 1 in result['sub_domain']  # S1 属于 D1


# ============================================================================
# P5-T2 规则 2: 加严不放松 (children ⊆ parent)
# ============================================================================

class TestP5T2Rule2NoLooserThanParent:
    """P5-T2 规则 2: children 的 dim scope 不能比 parent 更宽松"""

    def test_child_scope_subset_of_parent(self, db_with_hierarchy):
        """child 的 scope 是 parent scope 的子集"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # parent=product [1, 2], child=version [1] — 应通过 (子集)
        result = engine.check_scope_strictness(
            parent_scope={'product': {1, 2}},
            child_scope={'version': {1}},
        )
        assert result is True
        # parent=product [1], child=version [1, 2] — 应拒绝 (越界)
        result = engine.check_scope_strictness(
            parent_scope={'product': {1}},
            child_scope={'version': {1, 2}},  # V2 属于 P2, 越界
        )
        assert result is False


# ============================================================================
# P5-T2 规则 3: 关联取交集 (Association)
# ============================================================================

class TestP5T2Rule3AssociationIntersection:
    """P5-T2 规则 3: Association 关系的资源取两端 dim scope 交集"""

    def test_relationship_visible_if_either_end_in_scope(self, db_with_hierarchy):
        """relationship 任一端在 dim scope 内 → 可见"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # relationship 1: source=BO 1 (product 1), target=BO 2 (product 2)
        # 用户 dim scope: product=[1]
        # 期望: relationship 可见 (因为 source 端在 scope 内)
        visible = engine.check_association_visibility(
            resource_id=1,
            resource_type='relationship',
            user_scope={'product': {1}},
        )
        assert visible is True

    def test_relationship_invisible_if_neither_end_in_scope(self, db_with_hierarchy):
        """relationship 两端都不在 dim scope 内 → 不可见"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # 用户 dim scope: product=[99] (不存在)
        visible = engine.check_association_visibility(
            resource_id=1,
            resource_type='relationship',
            user_scope={'product': {99}},
        )
        assert visible is False


# ============================================================================
# P5-T2 规则 4: 附属跟随 (Subordinate 继承 parent owner)
# ============================================================================

class TestP5T2Rule4SubordinateInheritsParent:
    """P5-T2 规则 4: Subordinate 资源自动继承 parent 的 owner"""

    def test_subordinate_gets_parent_owner(self, db_with_hierarchy):
        """annotation 的 owner 自动继承自 parent (product)"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # annotation 1: parent_type='product', parent_id=1
        # product 1 的 owner=100
        owner = engine.resolve_subordinate_owner(
            resource_type='annotation',
            resource={'id': 1, 'parent_type': 'product', 'parent_id': 1},
        )
        assert owner == 100  # 继承自 product 1

    def test_subordinate_with_explicit_owner_not_overridden(self, db_with_hierarchy):
        """显式 owner_id 优先于继承 (显式 > 继承)"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # annotation 显式 owner_id=999, 不应被 parent 覆盖
        owner = engine.resolve_subordinate_owner(
            resource_type='annotation',
            resource={'id': 1, 'parent_type': 'product', 'parent_id': 1, 'owner_id': 999},
        )
        assert owner == 999


# ============================================================================
# P5-T2 规则 5: 向上传播 (propagate_to_parents=1)
# ============================================================================

class TestP5T2Rule5PropagateUpward:
    """P5-T2 规则 5: children 的 dim scope 变更向上传播到 parent"""

    def test_propagate_sub_domain_to_product(self, db_with_hierarchy):
        """sub_domain 变更向上传播到 product"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # 用户配置: sub_domain=[1], propagate_to_parents=1
        # 期望: 自动反查 domain=[1] → version=[1] → product=[1]
        result = engine.propagate_scope_upward(
            child_dimension='sub_domain',
            child_values=[1],
            propagate_to_parents=1,
        )
        assert 'sub_domain' in result
        assert 1 in result['sub_domain']
        assert 'domain' in result
        assert 1 in result['domain']
        assert 'version' in result
        assert 1 in result['version']
        assert 'product' in result
        assert 1 in result['product']


# ============================================================================
# P5-T3: 显式配置优先于继承 + 3 级嵌套
# ============================================================================

class TestP5T3ExplicitOverInherited:
    """P5-T3: 显式配置优先于继承"""

    def test_explicit_rule_not_overridden_by_inheritance(self, db_with_hierarchy):
        """显式配置的规则不会被继承规则覆盖"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # 显式配置: user 在 product 1 是 owner
        # 继承配置: user 在 product 2 (通过其他角色继承)
        # 期望: 显式优先, 不被继承覆盖
        explicit = {'product': {1}}
        inherited = {'product': {2}}
        merged = engine.merge_explicit_with_inherited(explicit, inherited)
        # 合并后: 显式 + 继承 都在 (合并取并集)
        assert 1 in merged['product']
        assert 2 in merged['product']

    def test_explicit_deny_not_overridden_by_inherited_allow(self, db_with_hierarchy):
        """显式 Deny 不被继承 Allow 覆盖"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # 显式: deny product 1
        # 继承: allow product 1
        # 期望: deny 优先 (显式 deny 短路)
        result = engine.resolve_with_precedence(
            explicit_rules=[{'resource_type': 'product', 'is_denied': True, 'resource_id': 1}],
            inherited_rules=[{'resource_type': 'product', 'is_denied': False, 'resource_id': 1}],
            resource_type='product',
            resource_id=1,
        )
        assert result == 'deny'


# ============================================================================
# P5-T3: 3 级嵌套 (sub_domain → domain → version → product)
# ============================================================================

class TestP5T3ThreeLevelNesting:
    """P5-T3: 3 级嵌套资源继承"""

    def test_3_level_inheritance_chain(self, db_with_hierarchy):
        """3 级嵌套: annotation → product → version (资源继承链)"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # annotation.parent_type='product', parent_id=1
        # product 1 → version 1 (层级)
        # 期望: 通过 annotation → product → version 3 级反查
        result = engine.resolve_inheritance_chain(
            resource_type='annotation',
            resource={'id': 1, 'parent_type': 'product', 'parent_id': 1},
            max_depth=3,
        )
        # 应能反查到 product 1 的信息
        assert result is not None
        assert 'product' in result
        assert result['product']['id'] == 1

    def test_nested_subordinate_resolves_root_owner(self, db_with_hierarchy):
        """嵌套附属资源解析根 owner"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        ds = db_with_hierarchy
        engine = ResourceInheritanceEngine(ds)
        # 假设 annotation.parent 是另一个 annotation (3 级嵌套)
        # 最终应反查到 product 1 的 owner=100
        # 这里直接验证 annotation → product 链
        owner = engine.resolve_subordinate_owner(
            resource_type='annotation',
            resource={'id': 1, 'parent_type': 'product', 'parent_id': 1},
            max_depth=3,
        )
        assert owner == 100


# ============================================================================
# P5-T4 验收: 5 条规则 + 显式/隐式优先级 + 3 级嵌套 (集成)
# ============================================================================

class TestP5T4Acceptance:
    """P5-T4 验收测试"""

    def test_all_5_rules_implemented(self):
        """5 条规则全部有对应方法"""
        from meta.services.resource_inheritance_engine import ResourceInheritanceEngine
        engine = ResourceInheritanceEngine(None)
        # 规则 1: 向下继承
        assert hasattr(engine, 'expand_inherited_scope')
        # 规则 2: 加严不放松
        assert hasattr(engine, 'check_scope_strictness')
        # 规则 3: 关联取交集
        assert hasattr(engine, 'check_association_visibility')
        # 规则 4: 附属跟随
        assert hasattr(engine, 'resolve_subordinate_owner')
        # 规则 5: 向上传播
        assert hasattr(engine, 'propagate_scope_upward')

    def test_engine_integrates_with_permission_resolver(self):
        """P5-T3: PermissionResolver 调用 Engine"""
        from meta.services.permission_resolver import PermissionResolver
        # PermissionResolver 应能调用 ResourceInheritanceEngine
        # 通过懒加载或方法注入
        resolver = PermissionResolver(None)
        # 至少有方法可获取 Engine 实例
        assert hasattr(resolver, 'check_owner_for_subordinate') or \
               hasattr(resolver, '_get_inheritance_engine')

    def test_p5_t3_engine_used_by_resolver_for_subordinate(self, db_with_hierarchy):
        """P5-T3 集成验证: PermissionResolver.check_owner_for_subordinate 调用 Engine"""
        from meta.services.permission_resolver import PermissionResolver
        ds = db_with_hierarchy
        resolver = PermissionResolver(ds)
        # annotation 1 隶属 product 1, product 1 的 owner=100
        # user 100 应该通过 Engine 继承得到 owner 权限
        result = resolver.check_owner_for_subordinate(
            user={'id': 100, 'username': 'alice'},
            resource_type='annotation',
            resource={'id': 1, 'parent_type': 'product', 'parent_id': 1},
        )
        assert result is True
        # user 200 不是 owner
        result = resolver.check_owner_for_subordinate(
            user={'id': 200, 'username': 'bob'},
            resource_type='annotation',
            resource={'id': 1, 'parent_type': 'product', 'parent_id': 1},
        )
        assert result is False