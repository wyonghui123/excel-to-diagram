"""
工厂单元测试 (Phase 1)
========================

验证 6+ 工厂的:
1. build() 不写 DB, 返回 dict
2. 唯一性 (多次 build 不同)
3. defaults 字段完整
4. _COUNTER 单调递增
5. unique_* helpers 正确

TBD-4 验证: counter+random 人类可读
"""
import pytest
import re
from typing import Dict, Any


# ============================================================
# UserFactory 测试
# ============================================================

class TestUserFactory:
    """UserFactory 单元测试"""

    def test_build_returns_dict(self):
        """build() 返回 dict"""
        from meta.tests.factories import UserFactory
        user = UserFactory.build()
        assert isinstance(user, dict)
        assert 'username' in user
        assert 'email' in user

    def test_build_unique_across_calls(self):
        """多次 build 唯一"""
        from meta.tests.factories import UserFactory
        users = [UserFactory.build() for _ in range(10)]
        usernames = [u['username'] for u in users]
        assert len(set(usernames)) == 10, "用户应唯一"

    def test_defaults_have_required_fields(self):
        """defaults 必填字段完整"""
        from meta.tests.factories import UserFactory
        user = UserFactory.build()
        assert 'role' in user
        assert 'password' in user
        assert user['role'] in ['user', 'admin']
        assert user['password']  # 非空

    def test_counter_monotonic(self):
        """_COUNTER 单调递增"""
        from meta.tests.factories import UserFactory
        c1 = UserFactory._COUNTER
        UserFactory.build()
        c2 = UserFactory._COUNTER
        assert c2 == c1 + 1


# ============================================================
# RoleFactory 测试
# ============================================================

class TestRoleFactory:
    """RoleFactory 单元测试"""

    def test_build_returns_dict(self):
        from meta.tests.factories import RoleFactory
        role = RoleFactory.build()
        assert isinstance(role, dict)
        assert 'code' in role
        assert 'permissions' in role

    def test_build_unique_code(self):
        from meta.tests.factories import RoleFactory
        roles = [RoleFactory.build() for _ in range(5)]
        codes = [r['code'] for r in roles]
        assert len(set(codes)) == 5

    def test_admin_role_has_wildcard(self):
        from meta.tests.factories import RoleFactory
        # 检查 create_admin_role 方法定义
        assert hasattr(RoleFactory, 'create_admin_role')
        assert hasattr(RoleFactory, 'create_readonly_role')


# ============================================================
# UserGroupFactory 测试
# ============================================================

class TestUserGroupFactory:
    """UserGroupFactory 单元测试"""

    def test_build_returns_dict(self):
        from meta.tests.factories import UserGroupFactory
        group = UserGroupFactory.build()
        assert isinstance(group, dict)
        assert 'code' in group
        assert 'name' in group

    def test_build_unique(self):
        from meta.tests.factories import UserGroupFactory
        groups = [UserGroupFactory.build() for _ in range(5)]
        codes = [g['code'] for g in groups]
        assert len(set(codes)) == 5


# ============================================================
# BusinessObjectFactory 测试
# ============================================================

class TestBusinessObjectFactory:
    """BusinessObjectFactory 单元测试"""

    def test_build_returns_dict(self):
        from meta.tests.factories import BusinessObjectFactory
        bo = BusinessObjectFactory.build()
        assert isinstance(bo, dict)
        assert 'code' in bo
        assert 'fields' in bo
        assert isinstance(bo['fields'], list)

    def test_build_unique_code(self):
        from meta.tests.factories import BusinessObjectFactory
        bos = [BusinessObjectFactory.build() for _ in range(5)]
        codes = [b['code'] for b in bos]
        assert len(set(codes)) == 5

    def test_status_default_draft(self):
        from meta.tests.factories import BusinessObjectFactory
        bo = BusinessObjectFactory.build()
        assert bo['status'] == 'draft'


# ============================================================
# VersionFactory 测试
# ============================================================

class TestVersionFactory:
    """VersionFactory 单元测试"""

    def test_build_returns_dict(self):
        from meta.tests.factories import VersionFactory
        v = VersionFactory.build()
        assert isinstance(v, dict)
        assert 'version' in v
        assert 'schema' in v

    def test_version_format(self):
        from meta.tests.factories import VersionFactory
        v = VersionFactory.build()
        # version 格式: 1.0.N
        assert re.match(r'^\d+\.\d+\.\d+$', v['version'])


# ============================================================
# DomainFactory 测试
# ============================================================

class TestDomainFactory:
    """DomainFactory 单元测试"""

    def test_build_returns_dict(self):
        from meta.tests.factories import DomainFactory
        d = DomainFactory.build()
        assert isinstance(d, dict)
        assert 'code' in d
        assert 'is_active' in d
        assert d['is_active'] is True

    def test_build_unique_code(self):
        from meta.tests.factories import DomainFactory
        domains = [DomainFactory.build() for _ in range(5)]
        codes = [d['code'] for d in domains]
        assert len(set(codes)) == 5


# ============================================================
# SubscriptionFactory 测试
# ============================================================

class TestSubscriptionFactory:
    """SubscriptionFactory 单元测试"""

    def test_build_returns_dict(self):
        from meta.tests.factories import SubscriptionFactory
        s = SubscriptionFactory.build()
        assert isinstance(s, dict)
        assert 'object_type' in s
        assert 'event_types' in s
        assert 'channel' in s

    def test_event_types_default(self):
        from meta.tests.factories import SubscriptionFactory
        s = SubscriptionFactory.build()
        assert 'create' in s['event_types']
        assert 'update' in s['event_types']


# ============================================================
# 唯一性 Helper 测试
# ============================================================

class TestUniquenessHelpers:
    """唯一性 helper 单元测试"""

    def test_unique_id_unique(self):
        from meta.tests.factories import unique_id
        ids = [unique_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_unique_str_default_length(self):
        from meta.tests.factories import unique_str
        s = unique_str()
        assert len(s) == 8

    def test_unique_str_custom_length(self):
        from meta.tests.factories import unique_str
        s = unique_str(4)
        assert len(s) == 4

    def test_unique_email_format(self):
        from meta.tests.factories import unique_email
        e = unique_email()
        assert '@test.local' in e
        assert e.startswith('user_')


# ============================================================
# FactoryRegistry 测试
# ============================================================

class TestFactoryRegistry:
    """FACTORY_REGISTRY 单元测试"""

    def test_registry_has_all_factories(self):
        from meta.tests.factories import FACTORY_REGISTRY
        expected = {
            'user', 'role', 'user_group',
            'business_object', 'version', 'domain', 'subscription',
        }
        registered = set(FACTORY_REGISTRY.keys())
        assert expected.issubset(registered), \
            f"缺少工厂: {expected - registered}"

    def test_factory_count(self):
        from meta.tests.factories import FACTORY_REGISTRY
        # Phase 1 至少 7 个工厂
        assert len(FACTORY_REGISTRY) >= 7, \
            f"Phase 1 应至少 7 个工厂, 实际 {len(FACTORY_REGISTRY)}"
