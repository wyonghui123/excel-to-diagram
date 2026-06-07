# E2E 测试覆盖率 Gap 报告

> **生成时间**: 2026-06-07 15:49:26
> **项目**: excel-to-diagram / ArchWorkspace
> **元数据对象**: 36
> **E2E specs**: 47
> **路由数**: 32

## 一、总体覆盖率

- **业务对象总数**: 36
- **已覆盖**: 25
- **未覆盖**: 11
- **覆盖率**: **69.4%**

## 二、按优先级 Gap

### P0 (共 14 个, 未覆盖 0)

| 对象 | 名称 | 审计 | 层级 | CRUD | 覆盖 | 覆盖 spec | 字段数 |
|------|------|------|------|------|------|-----------|--------|
| `audit_log` | 审计日志 | 否 | 否 | 否 | [OK] | e2e\features\audit-log-base.spec.js, e2e\features\audit-log-embedded-access.spec.js +3 | 27 |
| `business_object` | 业务对象 | 是 | 是 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\arch-data-crud-v2.spec.js +17 | 16 |
| `domain` | 领域 | 是 | 是 | 否 | [OK] | e2e\features\arch-data-crud.spec.js, e2e\features\audit-log-embedded-access.spec.js +5 | 11 |
| `menu` | 菜单 | 否 | 否 | 否 | [OK] | e2e\features\audit-log-embedded-access.spec.js, e2e\features\audit-log-filter.spec.js +5 | 20 |
| `permission` | 功能权限 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +21 | 8 |
| `product` | 产品线 | 是 | 否 | 否 | [OK] | e2e\features\arch-data-crud-v2.spec.js, e2e\features\arch-data-crud.spec.js +11 | 7 |
| `relationship` | 业务关系 | 是 | 是 | 否 | [OK] | e2e\features\arch-data-crud.spec.js, e2e\features\audit-log-objects-p1.spec.js | 37 |
| `role` | 角色 | 是 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-levels.spec.js +14 | 13 |
| `service_module` | 服务模块 | 是 | 是 | 否 | [OK] | e2e\features\audit-log-objects-p1.spec.js | 16 |
| `sub_domain` | 子领域 | 是 | 是 | 否 | [OK] | e2e\features\arch-data-crud.spec.js, e2e\features\audit-log-embedded-access.spec.js +5 | 15 |
| `user` | 用户 | 是 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +17 | 22 |
| `user_group` | 用户组 | 是 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +17 | 8 |
| `user_group_member` | 用户组成员 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +17 | 5 |
| `version` | 产品版本 | 是 | 否 | 否 | [OK] | e2e\features\arch-data-crud-v2.spec.js, e2e\features\arch-data-crud.spec.js +8 | 11 |

### P1 (共 13 个, 未覆盖 2)

| 对象 | 名称 | 审计 | 层级 | CRUD | 覆盖 | 覆盖 spec | 字段数 |
|------|------|------|------|------|------|-----------|--------|
| `employee_data_scope` | 员工数据权限范围 | 否 | 否 | 否 | [GAP] | - | 5 |
| `filter_variant` | 过滤变体 | 否 | 否 | 否 | [GAP] | - | 9 |
| `annotation` | 备注信息 | 是 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\arch-data-filter-scope.spec.js +1 | 8 |
| `data_permission` | 数据权限 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +19 | 6 |
| `enum_type` | 枚举类型 | 是 | 否 | 否 | [OK] | e2e\features\audit-log-objects-p1.spec.js, e2e\features\enum-management.spec.js | 9 |
| `enum_value` | 枚举值 | 是 | 否 | 否 | [OK] | e2e\features\audit-log-objects-p1.spec.js | 13 |
| `group_data_permission` | 用户组数据权限 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +19 | 7 |
| `menu_permission` | 菜单权限 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +21 | 12 |
| `permission_bundle` | 权限包 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +19 | 10 |
| `permission_rule` | 条件权限规则 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +19 | 11 |
| `role_data_permission` | 角色数据权限 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +24 | 8 |
| `role_dimension_scope` | 角色维度范围 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-levels.spec.js +14 | 6 |
| `role_permission` | 角色权限 | 否 | 否 | 否 | [OK] | e2e\features\ValueHelp-5-layer-link.spec.js, e2e\features\audit-log-embedded-access.spec.js +24 | 5 |

### P2 (共 9 个, 未覆盖 9)

| 对象 | 名称 | 审计 | 层级 | CRUD | 覆盖 | 覆盖 spec | 字段数 |
|------|------|------|------|------|------|-----------|--------|
| `ai_async_task` | AI异步任务 | 否 | 否 | 否 | [GAP] | - | 26 |
| `change_event` | 变更事件 | 否 | 否 | 否 | [GAP] | - | 16 |
| `change_subscription` | 变更订阅 | 否 | 否 | 否 | [GAP] | - | 10 |
| `hierarchies` | 层级定义 | 否 | 否 | 否 | [GAP] | - | 0 |
| `scheduled_task` | 任务定义 | 否 | 否 | 否 | [GAP] | - | 23 |
| `task_execution` | 任务执行记录 | 否 | 否 | 否 | [GAP] | - | 31 |
| `task_queue` | 任务队列配置 | 否 | 否 | 否 | [GAP] | - | 10 |
| `test_objects` | 测试对象 | 否 | 否 | 否 | [GAP] | - | 6 |
| `test_table` | 测试表 | 否 | 否 | 否 | [GAP] | - | 3 |

## 三、关键 Gap 清单 (P0 未覆盖)

**[OK] 全部 P0 对象已覆盖**

## 四、路由级覆盖

| 路由 | 标签 | E2E 覆盖 |
|------|------|---------|
| `/` | 工作台 (Workspace) | [GAP] |
| `/diagram` | 架构图生成器 | [GAP] |
| `/product-management` | 产品管理 | [OK] |
| `/user-permission/:tab?` | 用户/角色/用户组 | [GAP] |
| `/business-config/enums/:id` | 业务配置 (枚举) | [GAP] |
| `/business-config/:tab?` | 业务配置 (枚举) | [GAP] |
| `/system/role-permission/:roleId` | 角色管理 | [OK] |
| `/system/role-detail/:roleId` | 角色管理 | [OK] |
| `/system/archdata` | 架构数据管理 | [GAP] |
| `/system/task-management` | 任务调度 | [GAP] |
| `/account` | 账户设置 | [GAP] |
| `/` | 工作台 (Workspace) | [GAP] |
| `/` | 工作台 (Workspace) | [GAP] |
| `/` | 工作台 (Workspace) | [GAP] |
| `/` | 工作台 (Workspace) | [GAP] |

## 五、E2E Spec 统计

- **Spec 文件数**: 47
- **测试总数**: 218

### Top 10 Spec (按测试数)

| 文件 | 测试数 |
|------|--------|
| `e2e\features\role-permission-center.spec.js` | 27 |
| `e2e\features\useMetaList-21-keypath.spec.js` | 21 |
| `e2e\features\ValueHelp-5-layer-link.spec.js` | 15 |
| `e2e\features\audit-log-embedded-access.spec.js` | 14 |
| `e2e\features\audit-log-objects-p1.spec.js` | 11 |
| `e2e\features\audit-log-grouping-detail.spec.js` | 10 |
| `e2e\features\condition-rule-dialog-spec-v14.spec.js` | 9 |
| `e2e\features\audit-log-actions.spec.js` | 7 |
| `e2e\features\audit-log-filter.spec.js` | 7 |
| `e2e\features\audit-log-levels.spec.js` | 6 |

## 六、行动建议

### P0 Gap (必须补)
- [OK] 无 P0 Gap

### P1 Gap (建议补)
- [ ] **employee_data_scope** (员工数据权限范围)
- [ ] **filter_variant** (过滤变体)

### P2 Gap (可选)
- [ ] **ai_async_task** (AI异步任务)
- [ ] **change_event** (变更事件)
- [ ] **change_subscription** (变更订阅)
- [ ] **hierarchies** (层级定义)
- [ ] **scheduled_task** (任务定义)
- [ ] ... 还有 4 个 P2 Gap
