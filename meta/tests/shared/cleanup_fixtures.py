"""
Auto-cleanup Fixtures (Phase 1 新建)
=====================================

提供自动清理的 fixture, 解决:
- 1007 个测试创建但无清理
- DB 污染
- 跨测试干扰

TBD-3 采纳: P0+P1 必, P2 视情况
TBD-7 采纳: Phase 1-3 warning, Phase 4+ error

使用示例:
    def test_user_create(test_users):
        user = test_users()  # auto-cleanup
        assert user['id'] > 0
    # test_users 自动清理, 不需 try/finally
"""
import pytest
from typing import Callable, Iterator, List, Dict, Any

from meta.tests.factories import (
    UserFactory, RoleFactory, UserGroupFactory,
    BusinessObjectFactory, VersionFactory, DomainFactory,
    SubscriptionFactory,
)


# ============================================================
# Auto-cleanup Fixture 模板
# ============================================================

def make_cleanup_fixture(factory_class, name: str) -> Callable:
    """
    工厂函数: 生成 auto-cleanup fixture

    Args:
        factory_class: 工厂类
        name: fixture 名

    Returns:
        pytest fixture
    """
    @pytest.fixture
    def cleanup_fixture(admin_cookie) -> Iterator[Callable]:
        """
        Auto-cleanup fixture for {name}
        创建的对象会在测试结束后自动清理
        """
        created_ids: List[int] = []
        original_create = factory_class.create

        def tracked_create(**kwargs):
            obj = original_create(cookie=admin_cookie, **kwargs)
            if obj.get('id', -1) > 0:
                created_ids.append(obj['id'])
            return obj

        yield tracked_create

        # 测试结束, 逆序清理
        for obj_id in reversed(created_ids):
            try:
                factory_class.cleanup(obj_id, cookie=admin_cookie)
            except Exception:
                pass  # 清理失败不抛 (避免掩盖测试失败)

    cleanup_fixture.__name__ = name
    return cleanup_fixture


# ============================================================
# 导出具体 fixture
# ============================================================

test_users = make_cleanup_fixture(UserFactory, 'test_users')
"""auto-cleanup test users"""

test_roles = make_cleanup_fixture(RoleFactory, 'test_roles')
"""auto-cleanup test roles"""

test_user_groups = make_cleanup_fixture(UserGroupFactory, 'test_user_groups')
"""auto-cleanup test user groups"""

test_bos = make_cleanup_fixture(BusinessObjectFactory, 'test_bos')
"""auto-cleanup test BOs"""

test_versions = make_cleanup_fixture(VersionFactory, 'test_versions')
"""auto-cleanup test versions"""

test_domains = make_cleanup_fixture(DomainFactory, 'test_domains')
"""auto-cleanup test domains"""

test_subscriptions = make_cleanup_fixture(SubscriptionFactory, 'test_subscriptions')
"""auto-cleanup test subscriptions"""


# ============================================================
# 高级 fixture: 组合数据
# ============================================================

@pytest.fixture
def test_user_with_role(test_users, test_roles, admin_cookie) -> Iterator[Dict[str, Any]]:
    """
    创建带角色的用户 (auto-cleanup)
    """
    role = test_roles(permissions=['user:read'])
    user = test_users(role='user', role_id=role['id'])
    user['_role'] = role
    yield user


@pytest.fixture
def test_bo_with_version(test_bos, test_versions, admin_cookie) -> Iterator[Dict[str, Any]]:
    """
    创建 BO + Version 组合 (auto-cleanup)
    """
    bo = test_bos(status='published')
    version = test_versions(bo_id=bo['id'], status='released')
    yield {'bo': bo, 'version': version}
