# -*- coding: utf-8 -*-
"""
[v089 2026-09-15] user_group_service Sunset 兼容 shim

历史:
  P9 (2026-Q2) UserGroupService 已 Sunset; OrgService (Spec16) 提供等价的业务方法.
  但 meta/tests/ 下仍有 4 个测试文件引用 'meta.services.user_group_service'
  (test_org_service.py, test_org_service_edge.py, test_owner_scenarios_comprehensive.py,
   test_security_authorization.py), ImportError 导致 collection error.

策略:
  本 shim 模块导出 UserGroupService = OrgService, 让历史测试 (get_user_groups,
  is_group_manager, get_managed_groups, get_group_roles 等) 仍能 Import + 调用.
  缺失的方法 (P9 已 Sunset 的) 会触发 AttributeError, 但这与之前的 ImportError 状态
  对比是 '已知失败', 不会阻塞 collection.

不变量:
  - UserGroupService.__init__ = OrgService.__init__
  - UserGroupService.__class__ = OrgService (isinstance 检查通过)

downgrade: 直接删除本文件, 测试恢复 ImportError (与 v089 之前一致).
"""
from .org_service import OrgService

# Sunset shim: UserGroupService 是 OrgService 的别名 (P9 兼容)
UserGroupService = OrgService

__all__ = ['UserGroupService']