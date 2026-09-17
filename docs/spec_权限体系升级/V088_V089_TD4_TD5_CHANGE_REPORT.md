# Spec 19 M4 后续收尾变更报告 (T-D-4 + T-D-5)

> **变更范围**: 跟进 Spec 19 M4 `manager_id` 软删 + v089 DROP legacy 表后续收尾
> **对应规范**: `docs/spec_权限体系升级/19_org_admin_delegation.md` (Spec 19)
> **关联跟踪**: `docs/spec_权限体系升级/V088_V089_DATA_PICKUP_REPORT.md`
> **执行日期**: 2026-09-15
> **执行人**: Trae Agent

---

## 一、本次变更范围 (T-D-4 + T-D-5)

| 任务 | 描述 | 状态 |
|---|---|---|
| **T-D-4** | 测试 fixture 重命名 (68 文件, 685 行, 688 次替换) | DONE |
| **T-D-4 收尾** | shim 模块 `factories.permission_set.py` | DONE |
| **T-D-5** | `permission_audit.sql` 改写 (V1 → V2) | DONE |

---

## 二、T-D-4: 测试 fixture 重命名

### 2.1 改动概览

按 spec16 RENAME 表全量替换测试目录的 legacy 表名引用。

| 维度 | 数值 |
|---|---|
| **应用范围** | `meta/tests/` (68 文件) |
| **替换脚本** | `tools/.v089_bulk_rename.py` (v3) |
| **替换模式** | SQL 关键字上下文触发 + word boundary regex |
| **总替换数** | 685 行 / 688 次 |
| **跳过保护** | SKIP_PATH_PARTS × 11, SKIP_FILES × 3 |

### 2.2 跳过保护清单

```
SKIP_PATH_PARTS = [
    'tests/api', 'tests/auth', 'tests/factories',
    'tests/_tools', 'tests/shared', 'tests/interceptors',
    'tests/metadata', 'tests/migrations',
    'tests/performance', 'tests/import_export',
    'tests/permission',
]

SKIP_FILES = [
    'test_2026_08_28_*',
    'test_permission_set_v1_cleanup',
    'test_token_service',
]
```

### 2.3 误报防护 (False Positive Protection)

通过 is_protected 规则，跳过以下类型避免误改：

| 命中类型 | 例子 | 处理 |
|---|---|---|
| users.roles 列 | `users.roles = [...]` | 跳过 (非表名) |
| GraphQL schema strings | `"query { roles { ... } }"` | 跳过 |
| blueprint 变量名 | `roles = [r['code']]` | 跳过 |
| MockUserInfo.roles | `info.context.user.roles` | 跳过 |
| token payload permission_sets | `payload['roles']` | 跳过 |

### 2.4 shim 模块 (P9 Sunset Pattern)

为保持向后兼容，创建两个 P9 Sunset shim：

| Shim 文件 | 导出 | 来源 |
|---|---|---|
| `meta/services/user_group_service.py` | `UserGroupService = OrgService` | `OrgService` 别名 |
| `meta/tests/factories/permission_set.py` | `RoleFactory` 重导出 | `role.RoleFactory` 别名 |

#### 2.4.1 `user_group_service.py` 修复 4 个测试 collection error

```python
# meta/services/user_group_service.py
from .org_service import OrgService
UserGroupService = OrgService  # P9 Sunset shim
__all__ = ['UserGroupService']
```

修复文件:
- `meta/tests/test_org_service.py`
- `meta/tests/test_org_service_edge.py`
- `meta/tests/test_owner_scenarios_comprehensive.py`
- `meta/tests/test_security_authorization.py`

#### 2.4.2 `factories/permission_set.py` 修复 cascade test

```python
# meta/tests/factories/permission_set.py
from .role import RoleFactory  # P9 Sunset shim
__all__ = ['RoleFactory']
```

修复文件:
- `meta/tests/test_permission_set_delete_cascade_v061.py`

---

## 三、T-D-5: permission_audit.sql V1 → V2

### 3.1 改动概览

| 维度 | V1 (旧) | V2 (新) |
|---|---|---|
| 头部注释 | V1 简化说明 | V2 Spec 16/19 双规范说明 + RENAME 映射表 |
| 表名引用 | 11 处 legacy 表 | 0 处 (全部 spec16 RENAME) |
| 列名 | `users.is_active` | `users.status = 'active'` |
| 列名 | `orgs.is_active` | 移除 (orgs 无此列, member_count 替代) |
| GROUP_CONCAT | 多参数 DISTINCT | 单参数 DISTINCT |
| 4.3 节 | 用户组管理员 (is_manager=1) | 受托管理员 (OrgAdminScopeService 入口) |
| 6.3 节注释 | `'role'` | `'permission_set'` |

### 3.2 RENAME 映射表 (文件头显式列出)

```sql
-- V2 关键变更:
--   - roles -> permission_sets
--   - role_permissions -> permission_set_permissions
--   - user_roles -> user_permission_sets
--   - user_groups -> orgs
--   - user_group_members -> org_members
--   - group_roles -> org_permission_sets
--   - role_data_permissions -> permission_set_data_permissions
--   - role_dimension_scopes -> permission_set_dimension_scopes
--   - role_effective_intents -> permission_set_effective_intents
--   - role_menu_permissions -> permission_set_menu_permissions
--   - group_data_permissions -> org_data_permissions
--   - user_group_members.is_manager / orgs.manager_id 软删 (Spec 19 M4)
--     不再作为审计维度; 受托管理员由 OrgAdminScopeService 提供
```

### 3.3 列名适配 (实测 schema)

| 表 | 旧列名 (V1) | 新列名 (V2) | 实测来源 |
|---|---|---|---|
| `users` | `is_active` | `status = 'active'` | `PRAGMA table_info(users)` |
| `orgs` | `is_active` | (移除, 用 `member_count` 替代) | `PRAGMA table_info(orgs)` |
| `permission_sets` | `is_active` | `is_active` (保留) | 同名, 不变 |

### 3.4 SQLite GROUP_CONCAT 适配

SQLite 的 `GROUP_CONCAT(DISTINCT col1, col2)` 不允许，DISTINCT 必须只跟一个参数。

修复模式：
```sql
-- V1 (错)
GROUP_CONCAT(DISTINCT ps.name, ', ') AS permission_sets

-- V2 (对)
GROUP_CONCAT(DISTINCT ps.name) AS permission_sets
```

### 3.5 验证结果

```python
# tools/_tmp_audit_smoke.py (临时验证, 已清理)
OK: executescript ran cleanly (whole file as one script)
Legacy table references: 12 命中全部在注释里 (RENAME 映射表)
```

42 个 SELECT statement 全部执行成功，零 legacy 表残留（在 SQL 主体中）。

---

## 四、本地验证 (test collection)

| 阶段 | errors 数 | 原因 |
|---|---|---|
| v089 DROP 前 (T-D-4 前) | 8 | 4 个 import error + 4 个基础设施 |
| shim 后 (T-D-4 收尾) | 4 → 3 | shim 修 4 import + factories.permission_set shim 修 1 |

### 4.1 当前 collection errors 分类

| # | 文件 | 错误类型 | 是否可解 |
|---|---|---|---|
| 1 | `test_e2e_verify.py` | sqlite3 DB file open fail | 基础设施 (需 DB) |
| 2 | `test_export_e2e.py` | 3010 端口服务未启 | 基础设施 (需启动服务) |
| 3 | `test_v10_verify.py` | 3010 端口服务未启 | 基础设施 (需启动服务) |

> **结论**: 所有 collection error 都是基础设施问题（DB 文件 / HTTP 服务），非代码 import/语法问题。T-D-4 + T-D-5 完成 = 0 代码层 error。

---

## 五、SSOT 同步清单

| 文件 | 类型 | 变更 |
|---|---|---|
| `meta/tests/factories/permission_set.py` | 新建 (P9 shim) | DONE |
| `meta/services/user_group_service.py` | 新建 (P9 shim) | DONE (前序任务) |
| `meta/scripts/permission_audit.sql` | 重写 V1→V2 | DONE |
| `meta/tests/test_permission_set_delete_cascade_v061.py` | 由 shim 自动修 | DONE |

---

## 六、后续待办

### 6.1 v089 部署后

- [ ] 部署 v089 DROP legacy 表到 staging
- [ ] 部署 v089 DROP legacy 表到 prod
- [ ] 删 `tools/.v089_bulk_rename.py` (一次性脚本)

### 6.2 v09x 后续 (2027-Q1 排期)

- [ ] DROP COLUMN 硬删 `orgs.manager_id`
- [ ] DROP COLUMN 硬删 `org_members.is_manager`
- [ ] 删 P9 Sunset shim (`user_group_service.py` + `factories/permission_set.py`)

### 6.3 PM_GIT_COMMANDS 跟踪

- 待本次 commit 后更新 `PM_PROMOTE_STATUS.md`
- commit message 推荐: `chore(perm): T-D-4 fixture 重命名 + T-D-5 audit.sql V1→V2 (Spec 19 M4 收尾)`

---

**报告人**: Trae Agent
**日期**: 2026-09-15
**关联文档**:
- [V088_V089_DATA_PICKUP_REPORT.md](./V088_V089_DATA_PICKUP_REPORT.md)
- [PROMOTION_CHECKLIST.md](./PROMOTION_CHECKLIST.md)
- [PM_PROMOTE_STATUS.md](./PM_PROMOTE_STATUS.md)
- [19_org_admin_delegation.md](./19_org_admin_delegation.md) (Spec 19)
- [16_role_to_permission_set_and_user_group_to_org.md](./16_role_to_permission_set_and_user_group_to_org.md) (Spec 16)