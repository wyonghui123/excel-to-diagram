"""
测试数据工厂库 (Phase 4 v3.18.3+, Phase 5 v3.18.5+)
====================================================

提供 18+ 个核心工厂 (v3.18.5: +5 新建), 解决:
- 硬编码 ID 泛滥 (1495 处 → ≤50)
- 工厂采用率 0.28% → 80%
- 清理率 0% → 95%
- 唯一性规范化 (TBD-4)
- [v3.18.5] HIGH 风险 schema 工厂补全 (5 个新增)

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
# [FIX 2026-07-17 P1] 新建 5 个 factory, 补 5 个 HIGH 风险 schema
from .task_queue import TaskQueueFactory
from .filter_variant import FilterVariantFactory
from .employee_data_scope import EmployeeDataScopeFactory
from .ai_async_task import AiAsyncTaskFactory
from .group_data_permission import GroupDataPermissionFactory
# [FIX 2026-07-18 P1] 新建 6 个权限域 factory, 补 6 个 HIGH 风险权限 schema
from .role_permission import RolePermissionFactory
from .role_dimension_scope import RoleDimensionScopeFactory
from .role_data_permission import RoleDataPermissionFactory
from .permission_bundle import PermissionBundleFactory
from .permission_rule import PermissionRuleFactory
from .data_permission import DataPermissionFactory
# [FIX 2026-07-18 P1-5] 新建 8 个 factory, 补 8 个 HIGH 风险无测试 schema
from .task_execution import TaskExecutionFactory
from .scheduled_task import ScheduledTaskFactory
from .change_subscription import ChangeSubscriptionFactory
from .change_event import ChangeEventFactory
from .menu_permission import MenuPermissionFactory
from .user_group_member import UserGroupMemberFactory
from .test_table import TestTableFactory
from .test_objects import TestObjectsFactory
# [FIX 2026-07-18 P1-6] 新建 3 个 factory, 补枚举和菜单
from .enum_type import EnumTypeFactory
from .enum_value import EnumValueFactory
from .menu import MenuFactory


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
    # [FIX 2026-07-17 P1] 新建 factory
    'TaskQueueFactory',
    'FilterVariantFactory',
    'EmployeeDataScopeFactory',
    'AiAsyncTaskFactory',
    'GroupDataPermissionFactory',
    # [FIX 2026-07-18 P1] 权限域 factory
    'RolePermissionFactory',
    'RoleDimensionScopeFactory',
    'RoleDataPermissionFactory',
    'PermissionBundleFactory',
    'PermissionRuleFactory',
    'DataPermissionFactory',
    # [FIX 2026-07-18 P1-5] 新建 factory
    'TaskExecutionFactory',
    'ScheduledTaskFactory',
    'ChangeSubscriptionFactory',
    'ChangeEventFactory',
    'MenuPermissionFactory',
    'UserGroupMemberFactory',
    'TestTableFactory',
    'TestObjectsFactory',
    # [FIX 2026-07-18 P1-6] 新建 factory
    'EnumTypeFactory',
    'EnumValueFactory',
    'MenuFactory',
]


__version__ = '3.18.3'
__phase__ = 'Phase 4'
