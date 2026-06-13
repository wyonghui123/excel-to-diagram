"""
测试数据工厂库 (Phase 4 v3.18.3+)
====================================

提供 13+ 个核心工厂, 解决:
- 硬编码 ID 泛滥 (1495 处 → ≤50)
- 工厂采用率 0.28% → 80%
- 清理率 0% → 95%
- 唯一性规范化 (TBD-4)

设计原则:
1. 必须走真实 API (不能用 mock)
2. 必须支持多 Agent 并行 (含 PID)
3. 必须配 cleanup() 防止 DB 污染
4. 必须生成唯一标识 (counter + random + ts)
5. 必须有 docstring 和使用示例

使用示例:
    from meta.tests.factories import UserFactory, BusinessObjectFactory

    def test_user_create(test_users):
        user = test_users()  # auto-cleanup
        assert user['id'] > 0
"""
from ._base import (
    BaseFactory,
    unique_id,
    unique_str,
    unique_email,
    FACTORY_REGISTRY,
    register_factory,
)
from .user import UserFactory
from .role import RoleFactory
from .user_group import UserGroupFactory
from .bo import BusinessObjectFactory
from .version import VersionFactory
from .domain import DomainFactory
from .subscription import SubscriptionFactory
from .annotation import AnnotationFactory
from .audit import AuditLogFactory
from .permission import PermissionFactory
from .relationship import RelationshipFactory
from .product import ProductFactory
from .import_export import ImportExportFactory
from .webhook import WebhookFactory


__all__ = [
    # 基础
    'BaseFactory',
    'unique_id',
    'unique_str',
    'unique_email',
    'FACTORY_REGISTRY',
    'register_factory',
    # 工厂类
    'UserFactory',
    'RoleFactory',
    'UserGroupFactory',
    'BusinessObjectFactory',
    'VersionFactory',
    'DomainFactory',
    'SubscriptionFactory',
    'AnnotationFactory',
    'AuditLogFactory',
    'PermissionFactory',
    'RelationshipFactory',
    'ProductFactory',
    'ImportExportFactory',
    'WebhookFactory',
]


__version__ = '3.18.3'
__phase__ = 'Phase 4'
