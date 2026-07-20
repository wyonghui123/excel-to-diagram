# -*- coding: utf-8 -*-
"""
[FILE] test_prohibition.py
[DESCRIPTION] Phase 6 M10 Prohibition — TDD 测试用例
[SPEC] spec-permission-system-unification-2026-07-19 §3.10 / §8.6

测试覆盖 (P6-T4 验收):
  P6-T1: Prohibition rule_type 验证 (is_denied=1 行可插入)
  P6-T2: Deny 优先实现 (Layer 0 短路)
  P6-T4: Deny vs Allow 冲突 → Deny 永远胜出
"""
import pytest

pytestmark = pytest.mark.unit

import sys
import os
import sqlite3
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_with_prohibition_rules():
    """创建含 data_permission_rules 表 + Prohibition 规则的测试库"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS data_permission_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            rule_type VARCHAR(50) NOT NULL DEFAULT 'condition',
            resource_type VARCHAR(200),
            dimension_code VARCHAR(200),
            condition TEXT,
            scope_mode VARCHAR(50) DEFAULT 'include',
            permission_level VARCHAR(50) DEFAULT 'read',
            is_denied INTEGER DEFAULT 0,
            inherit_to_children INTEGER DEFAULT 1,
            propagate_to_parents INTEGER DEFAULT 0,
            source_table VARCHAR(100),
            source_id INTEGER,
            created_at VARCHAR(200),
            updated_at VARCHAR(200)
        );
        CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS role_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            permission_id INTEGER,
            permission_code VARCHAR(200),
            created_at DATETIME
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, code TEXT, owner_id INTEGER, status TEXT
        );
    """)
    # 测试数据
    conn.execute("INSERT INTO products (id, name, code, owner_id, status) VALUES (1, 'P1', 'p1', 100, 'active')")
    conn.execute("INSERT INTO products (id, name, code, owner_id, status) VALUES (2, 'P2', 'p2', 200, 'archived')")
    # user_roles: alice (id=100) 拥有 role 1; bob (id=200) 拥有 role 2
    conn.execute("INSERT INTO user_roles (user_id, role_id) VALUES (100, 1)")
    conn.execute("INSERT INTO user_roles (user_id, role_id) VALUES (200, 2)")
    # role_permissions: role 1 和 role 2 都有 product.read
    conn.execute("INSERT INTO role_permissions (role_id, permission_code) VALUES (1, 'product.read')")
    conn.execute("INSERT INTO role_permissions (role_id, permission_code) VALUES (2, 'product.read')")
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
# P6-T1: Prohibition rule_type 验证 (is_denied=1 行可插入)
# ============================================================================

class TestP6T1ProhibitionRuleType:
    """P6-T1: rule_type='prohibition' + is_denied=1 行可正确插入和查询"""

    def test_insert_prohibition_rule(self, db_with_prohibition_rules):
        """可以插入 rule_type='prohibition' + is_denied=1 的行"""
        ds = db_with_prohibition_rules
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "condition, permission_level, is_denied) "
            "VALUES (1, 'prohibition', 'product', \"status = 'archived'\", 'delete', 1)"
        )
        rows = ds.execute(
            "SELECT rule_type, resource_type, is_denied, condition "
            "FROM data_permission_rules WHERE rule_type='prohibition'"
        ).fetchall()
        assert len(rows) == 1
        rule_type, rt, is_denied, cond = rows[0]
        assert rule_type == 'prohibition'
        assert rt == 'product'
        assert is_denied == 1
        assert "archived" in cond

    def test_query_prohibition_rules(self, db_with_prohibition_rules):
        """可按 rule_type='prohibition' AND is_denied=1 过滤"""
        ds = db_with_prohibition_rules
        # 插入多条规则
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (1, 'prohibition', 'product', 1)"
        )
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (2, 'condition', 'product', 0)"
        )
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (1, 'prohibition', 'version', 1)"
        )
        # 查询 prohibition + is_denied=1
        rows = ds.execute(
            "SELECT resource_type FROM data_permission_rules "
            "WHERE rule_type='prohibition' AND is_denied=1"
        ).fetchall()
        assert len(rows) == 2
        resource_types = {r[0] for r in rows}
        assert 'product' in resource_types
        assert 'version' in resource_types

    def test_is_denied_defaults_to_zero(self, db_with_prohibition_rules):
        """未指定 is_denied 时默认为 0 (Allow)"""
        ds = db_with_prohibition_rules
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type) "
            "VALUES (1, 'condition', 'product')"
        )
        row = ds.execute(
            "SELECT is_denied FROM data_permission_rules "
            "WHERE rule_type='condition' LIMIT 1"
        ).fetchone()
        assert row[0] == 0


# ============================================================================
# P6-T2: Deny 优先 (Layer 0 短路)
# ============================================================================

class TestP6T2DenyPriorityShortCircuit:
    """P6-T2: Prohibition 命中 → 立即 Deny (Layer 0 短路)"""

    def test_check_prohibition_returns_true_when_rule_matches(self, db_with_prohibition_rules):
        """命中 prohibition 规则时, _check_prohibition 返回 True"""
        ds = db_with_prohibition_rules
        # 插入 prohibition 规则: 禁止删除 archived 状态的 product
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "condition, permission_level, is_denied) "
            "VALUES (1, 'prohibition', 'product', \"status = 'archived'\", 'delete', 1)"
        )
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        # resource 2 (P2, status='archived') 应命中 prohibition
        resource = {'id': 2, 'name': 'P2', 'status': 'archived', 'owner_id': 200}
        result = resolver._check_prohibition(
            user={'id': 100, 'username': 'alice'},
            action='delete',
            resource_type='product',
            resource=resource,
        )
        assert result is True

    def test_check_prohibition_returns_false_when_no_rule(self, db_with_prohibition_rules):
        """无 prohibition 规则时, _check_prohibition 返回 False"""
        ds = db_with_prohibition_rules
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        resource = {'id': 1, 'name': 'P1', 'status': 'active', 'owner_id': 100}
        result = resolver._check_prohibition(
            user={'id': 100, 'username': 'alice'},
            action='delete',
            resource_type='product',
            resource=resource,
        )
        assert result is False

    def test_check_prohibition_returns_false_when_condition_not_match(self, db_with_prohibition_rules):
        """prohibition 规则的 condition 不匹配时, 返回 False"""
        ds = db_with_prohibition_rules
        # 插入 prohibition 规则: 禁止删除 archived 状态的 product
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "condition, permission_level, is_denied) "
            "VALUES (1, 'prohibition', 'product', \"status = 'archived'\", 'delete', 1)"
        )
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        # resource 1 (P1, status='active') 不应命中 prohibition
        resource = {'id': 1, 'name': 'P1', 'status': 'active', 'owner_id': 100}
        result = resolver._check_prohibition(
            user={'id': 100, 'username': 'alice'},
            action='delete',
            resource_type='product',
            resource=resource,
        )
        assert result is False

    def test_check_returns_deny_when_prohibition_hits(self, db_with_prohibition_rules):
        """[关键] PDP.check() 命中 prohibition → 立即 Deny, 不进入 Layer 1-5"""
        ds = db_with_prohibition_rules
        # 插入 prohibition 规则
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "condition, permission_level, is_denied) "
            "VALUES (1, 'prohibition', 'product', \"status = 'archived'\", 'delete', 1)"
        )
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        # alice 有 product.read 功能权限, 但 prohibition 命中 → Deny
        resource = {'id': 2, 'name': 'P2', 'status': 'archived', 'owner_id': 200}
        result = resolver.check(
            user={'id': 100, 'username': 'alice'},
            action='read',
            resource_type='product',
            resource=resource,
        )
        assert result is False  # Prohibition 短路


# ============================================================================
# P6-T4: Deny vs Allow 冲突 → Deny 永远优先
# ============================================================================

class TestP6T4DenyVsAllowConflict:
    """P6-T4: Deny + Allow 冲突场景: Deny 永远优先"""

    def test_deny_overrides_allow_same_resource(self, db_with_prohibition_rules):
        """同一资源上同时有 Deny 和 Allow 规则 → Deny 优先"""
        ds = db_with_prohibition_rules
        # 插入 Allow 规则 (condition)
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (1, 'condition', 'product', 0)"
        )
        # 插入 Deny 规则 (prohibition)
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (1, 'prohibition', 'product', 1)"
        )
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        resource = {'id': 1, 'name': 'P1', 'status': 'active', 'owner_id': 100}
        # 即使有 Allow 规则, prohibition 仍优先
        result = resolver._check_prohibition(
            user={'id': 100, 'username': 'alice'},
            action='read',
            resource_type='product',
            resource=resource,
        )
        assert result is True

    def test_wildcard_does_not_bypass_prohibition(self, db_with_prohibition_rules):
        """`*` 通配符不突破 Prohibition 约束 (Spec §3.12 第 4 层约束)"""
        ds = db_with_prohibition_rules
        # 插入 prohibition 规则: 所有 product 操作禁止
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (1, 'prohibition', 'product', 1)"
        )
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        # alice 即使有 `*` 通配权限, prohibition 仍生效
        resource = {'id': 1, 'name': 'P1', 'status': 'active', 'owner_id': 100}
        result = resolver.check(
            user={'id': 100, 'username': 'alice', 'permissions': ['*']},
            action='read',
            resource_type='product',
            resource=resource,
        )
        assert result is False  # Prohibition 优先于通配符

    def test_prohibition_resource_type_filter(self, db_with_prohibition_rules):
        """prohibition 仅对指定 resource_type 生效"""
        ds = db_with_prohibition_rules
        # prohibition: 仅禁止 product
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (1, 'prohibition', 'product', 1)"
        )
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        # 对 version 操作不应命中
        result = resolver._check_prohibition(
            user={'id': 100, 'username': 'alice'},
            action='read',
            resource_type='version',
            resource={'id': 1, 'name': 'V1'},
        )
        assert result is False

    def test_no_prohibition_rule_allows_normal_flow(self, db_with_prohibition_rules):
        """无 prohibition 规则时, 正常 Allow 流程不受影响"""
        ds = db_with_prohibition_rules
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        # alice 有 product.read 功能权限, 无 prohibition → Allow
        resource = {'id': 1, 'name': 'P1', 'status': 'active', 'owner_id': 100}
        result = resolver.check(
            user={'id': 100, 'username': 'alice'},
            action='read',
            resource_type='product',
            resource=resource,
        )
        assert result is True  # 正常 Allow 流程


# ============================================================================
# P6-T4 验收: 综合 Deny 优先场景
# ============================================================================

class TestP6T4Acceptance:
    """P6-T4 验收: Layer 0 短路 + Deny vs Allow"""

    def test_prohibition_short_circuits_layer_1_to_5(self, db_with_prohibition_rules):
        """Prohibition 命中时, Layer 1-5 不执行 (短路)"""
        ds = db_with_prohibition_rules
        # prohibition 规则
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (1, 'prohibition', 'product', 1)"
        )
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        # 即使 alice 是 owner (Layer 4), prohibition 仍优先
        resource = {'id': 1, 'name': 'P1', 'status': 'active', 'owner_id': 100}
        result = resolver.check(
            user={'id': 100, 'username': 'alice'},
            action='read',
            resource_type='product',
            resource=resource,
        )
        assert result is False  # Layer 0 短路, Layer 4 owner 不生效

    def test_super_user_bypasses_prohibition(self, db_with_prohibition_rules):
        """[例外] Superuser 跳过所有 Layer, 包括 Prohibition"""
        ds = db_with_prohibition_rules
        ds.execute(
            "INSERT INTO data_permission_rules (role_id, rule_type, resource_type, "
            "is_denied) VALUES (1, 'prohibition', 'product', 1)"
        )
        from meta.services.permission_resolver import PermissionResolver
        resolver = PermissionResolver(ds)
        resource = {'id': 1, 'name': 'P1', 'status': 'active', 'owner_id': 100}
        result = resolver.check(
            user={'id': 999, 'username': 'root', 'is_superuser': True},
            action='read',
            resource_type='product',
            resource=resource,
        )
        assert result is True  # Superuser 短路 (Layer 0 之前)
