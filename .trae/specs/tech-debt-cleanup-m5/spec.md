# Spec: 技术债务清理与架构对齐 (M5)

## 1. 背景与目标

### 1.1 背景

在 M1-M4 阶段，项目完成了元数据模型驱动 BOF、统一 UI Framework（MetaListPage / DetailPage / MultiObjectManagementPage）、统一审计日志、统一导入导出、统一菜单框架等核心能力建设。代码库中存在以下遗留问题：

1. **SystemSettings.vue** 仍使用手写 HTML 表单，未迁移到统一 MetaForm 组件
2. **change_event / change_subscription** 的 notification_api.py 绕过 BO 框架通过直接 SQL 操作表，导致 YAML schema 中定义的审计、权限、字段验证规则对该两个表不生效
3. 多个已废弃组件仍残留在代码库中，占用维护成本

### 1.2 目标

- 对 SystemSettings.vue 迁移进行需求分析和方案记录，供后续实施
- 对 change_event / change_subscription 架构不一致问题进行根因分析和方案记录
- 清理已确认的死代码组件及其测试文件

---

## 2. 需求类型概述

| 类型 | 适用 | 来源 |
|------|------|------|
| 业务需求 | 是 | 系统健康度和可维护性下降 |
| 用户/涉众需求 | 是 | 开发团队需要统一的架构规范 |
| 解决方案需求 | 是 | 迁移方案、架构对齐方案 |
| 功能需求 | 是 | 清理死代码、记录迁移方案 |
| 非功能需求 | 是 | 代码清洁度、架构一致性 |
| 外部接口需求 | 否 | 无外部接口变更 |
| 过渡需求 | 是 | 废弃组件删除、旧代码迁移 |

---

## 3. 功能需求

### FR-001: SystemSettings.vue 迁移方案记录

- **描述**: 对 SystemSettings.vue 当前实现进行分析，记录迁移到 MetaForm 的技术方案和前置依赖，暂不实施代码变更
- **当前状态**: 
  - 文件位置: `src/views/SystemManagement/SystemSettings.vue`
  - 当前实现: 手写 HTML 表单，使用原生 `<input>`、`<select>`、`<textarea>`
  - 配置存储: `localStorage`（浏览器本地）
  - 配置项: AI 服务提供商（智谱/DeepSeek）、API Key、数据库路径、导入路径、导出路径、日志级别
  - 路由入口: `/business-config/:tab?` → GenericTabContainer → menuConfig → SystemSettings
- **目标方案**:
  - 前端: 使用 `MetaForm` 或 `ObjectPage` 渲染配置表单，字段从 YAML schema 驱动
  - 后端: 需新建配置管理 API（如 `POST/GET /api/v1/system-config`），配置持久化到 SQLite
  - 存储迁移: `localStorage` → 后端数据库 + API
- **前置依赖**:
  1. 新建 `system_config` YAML schema 定义配置字段
  2. 新建 `system_config_api.py` 提供配置 CRUD API
  3. 前端 SystemSettings.vue 替换为 MetaForm/ObjectPage
- **验收标准** (待实施时启用):
  - SystemSettings.vue 完全使用 MetaForm/ObjectPage 渲染
  - 配置项持久化到后端数据库，不再依赖 localStorage
  - 页面布局保持与现有 Tab 容器一致
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: 代码审查

### FR-002: change_event / change_subscription 架构不一致记录

- **描述**: 记录 change_event 和 change_subscription 表绕过 BO 框架的技术债务，暂不实施代码变更
- **当前问题**:
  - YAML schema `change_event.yaml` 和 `change_subscription.yaml` 被 `yaml_loader.py` 正常加载到元模型注册表
  - 但在 `notification_api.py` 中，对这两个表的 CRUD 操作通过**直接编写 SQL** 完成，完全绕过了 BO 框架
  - 导致 YAML 中定义的字段验证、权限控制、审计日志等规则对这两个表**不生效**
  - 两个表的创建不在 `generated_schema.sql` 中，而是通过独立的迁移脚本创建
- **根因**: 变更通知系统开发较早，在 BO 框架成熟前即已实现，后续未重构对齐
- **目标方案**:
  1. 将 change_event / change_subscription 的表创建纳入 `generated_schema.sql`（统一 Schema 同步流程）
  2. 重构 `notification_api.py`，改为通过 `bo_framework` 的 CRUD 方法操作这两个表
  3. 如有性能敏感的实时推送逻辑，可通过 BO 框架的 `PersistenceInterceptor` 挂载 WebSocket 推送回调
- **影响范围**:
  - `meta/api/notification_api.py` — 重构 CRUD 逻辑
  - `meta/schemas/change_event.yaml` / `change_subscription.yaml` — 可能需要补充完整的字段语义定义
  - `meta/core/interceptors/` — 可能需要新增通知拦截器
  - `meta/migrations/` — 迁移脚本合并
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: 代码审查

### FR-003: 清理死代码组件

- **描述**: 删除已确认无生产引用的废弃组件及其测试文件
- **待删除文件清单**:

  | 文件 | 原因 |
  |------|------|
  | `src/components/common/DynamicFilters.vue` | 已弃用，已从 common/index.js 移除，仅自有测试引用 |
  | `src/components/common/__tests__/DynamicFilters.test.js` | 配套测试 |
  | `src/components/common/__tests__/DynamicFilters.spec.js` | 配套测试 |
  | `meta/api/manage_api.py_temp` | 零引用，功能已存在于 manage_api.py |
  | `src/components/ArchWorkspace.vue` | 旧版首页，路由已改用 ArchWorkspaceNew.vue |
  | `src/views/SystemManagement/AddMemberDialog.vue` | 零引用，已被 MetaListPage enableAutoCrud 替代 |
  | `src/views/SystemManagement/__tests__/AddMemberDialog.spec.js` | 配套测试 |
  | `src/views/SystemManagement/GroupFormDialog.vue` | 零引用，已被 MetaListPage enableAutoCrud 替代 |
  | `src/views/SystemManagement/__tests__/GroupFormDialog.spec.js` | 配套测试 |
  | `src/views/SystemManagement/UserFormDialog.vue` | 零引用，已被 MetaListPage enableAutoCrud 替代 |

- **验收标准**:
  - 所有列出的文件已从文件系统中删除
  - 运行 `npm run lint` 和 `npm run typecheck` 无新增错误
  - 后端启动无 import 错误
- **优先级**: Must
- **类型映射**: 过渡需求
- **来源**: 代码审查

### FR-004: ComponentComparison.vue 中移除 DynamicFilters 展示

- **描述**: `src/views/ComponentComparison.vue` 中仍引用 DynamicFilters 用于展示对比，需移除该引用
- **当前引用**: [ComponentComparison.vue:L3048-L3055](file:///d:/filework/excel-to-diagram/src/views/ComponentComparison.vue#L3048) — 标注"已弃用"的展示卡片
- **修改**: 删除该展示卡片对应的模板和脚本引用
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 代码审查

---

## 4. 非功能需求

### NFR-001: 代码清洁度

- **描述**: 删除死代码后，代码库中不再存在零引用的废弃组件文件
- **测量**: `grep -r "DynamicFilters\|AddMemberDialog\|GroupFormDialog\|UserFormDialog" src/ --include="*.vue" --include="*.js" | grep -v __tests__ | grep -v ComponentComparison` 返回空
- **优先级**: Must

### NFR-002: 构建稳定性

- **描述**: 删除文件后，`npm run lint` 和 `npm run build` 无新增错误
- **测量**: 前后 lint/build 结果对比，错误数不增加
- **优先级**: Must

### NFR-003: 后端启动零错误

- **描述**: 删除 `manage_api.py_temp` 后，Flask 后端正常启动，所有 blueprint 正常注册
- **测量**: 后端启动日志无 import 错误或模块缺失警告
- **优先级**: Must

---

## 5. 外部接口需求

本次清理不涉及外部接口变更。

---

## 6. 过渡需求

### TR-001: DynamicFilters 迁移残留确认

- **描述**: 确认所有使用 DynamicFilters 的页面已迁移到 FilterBar
  - SmartFilterBar: 100% 迁移并已删除 ✅
  - DynamicFilters: 已从所有生产页面迁移 ✅
  - ComponentComparison 展示: 待移除
- **回滚方案**: 如需回滚，从 Git 历史恢复文件
- **来源**: 组件治理规范

### TR-002: ArchWorkspace.vue 旧版首页确认

- **描述**: 确认路由已完全切换到 ArchWorkspaceNew.vue
  - 路由 `path: '/'` 指向 `ArchWorkspaceNew.vue` ✅
  - `ArchWorkspace.vue` 无任何路由引用 ✅
  - 确认 `SysConfigApp.vue`、`ArchWorkspaceNew.vue` 等不依赖 `ArchWorkspace.vue` 的任何导出
- **回滚方案**: 从 Git 历史恢复
- **来源**: 代码审查

---

## 7. 约束与假设

### 7.1 技术约束

- 前端框架: Vue 3 + Vite + Element Plus
- 后端框架: Flask + SQLite
- 元数据引擎: `meta/core/bo_framework.py`
- 组件规范: 必须遵循 YonDesign 设计规范 + Element Plus 封装规范

### 7.2 假设

- MetaListPage 的 `enableAutoCrud` 功能已完全覆盖 AddMemberDialog / GroupFormDialog / UserFormDialog 的场景 — 已验证
- ArchWorkspace.vue 无隐藏引用 — 需在删除前做最终确认
- DynamicFilters 迁移已全部完成 — 已通过全局搜索确认

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 原因 |
|----|------|--------|------|
| FR-003 | 清理死代码组件 | Must | 零风险，立即执行 |
| FR-004 | ComponentComparison 移除 DynamicFilters | Must | 依赖 FR-003 |
| FR-001 | SystemSettings.vue 迁移方案 | Should | 仅记录方案，不实施 |
| FR-002 | change_event/subscription 架构对齐 | Should | 仅记录技术债务，不实施 |

- **里程碑 M5-1**: FR-003 + FR-004 死代码清理（即刻执行）
- **里程碑 M5-2**: FR-001 SystemSettings 迁移方案（待后续）
- **里程碑 M5-3**: FR-002 架构对齐（待后续专项处理）

---

## 9. 变更/设计提案 (RFC)

### 9.1 As-Is 分析

#### SystemSettings.vue

- **当前架构**: 手写 HTML 表单 + localStorage 存储
- **当前问题**:
  - 未使用统一的 MetaForm/ObjectPage，与其他页面风格不一致
  - 配置存储在浏览器 localStorage，无法多用户共享，清除缓存即丢失
  - 缺少后端验证和审计日志
- **相关代码**:
  - [SystemSettings.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/SystemSettings.vue)
  - [menuConfig.js](file:///d:/filework/excel-to-diagram/src/config/menuConfig.js) — Tab 配置中引用

#### change_event / change_subscription

- **当前架构**: notification_api.py 直接 SQL 操作表
- **当前问题**:
  - YAML schema 被加载但规则不生效（审计、权限、字段验证）
  - 表创建不在统一 Schema 同步流程中（不在 generated_schema.sql）
  - 架构不一致，维护成本高
- **相关代码**:
  - [notification_api.py](file:///d:/filework/excel-to-diagram/meta/api/notification_api.py)
  - [change_event.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/change_event.yaml)
  - [change_subscription.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/change_subscription.yaml)
  - [change_notification_service.py](file:///d:/filework/excel-to-diagram/meta/services/change_notification_service.py)

#### 死代码组件

- **当前状态**: 所有列出的组件均为零生产引用，已被统一框架替代
- **对比验证**:

| 原组件 | 替代方案 | 验证 |
|--------|----------|------|
| AddMemberDialog (用户组成员管理) | MetaListPage + AssociationPanel + BO v2 API | 0 生产引用 |
| GroupFormDialog (用户组新增/编辑) | MetaListPage enableAutoCrud | 0 生产引用 |
| UserFormDialog (用户新增/编辑) | MetaListPage enableAutoCrud | 0 生产引用 |
| DynamicFilters | FilterBar | 已从 common/index.js 移除 |

### 9.2 目标状态

- 死代码组件文件全部删除
- SystemSettings.vue 迁移方案文档化，待后续实施
- change_event/subscription 技术债务记录到 TECH-DEBT.md，待后续专项处理

### 9.3 详细设计

#### FR-003 实施步骤

1. 创建备份分支
2. 按文件清单逐一删除
3. 删除后运行 `npm run lint` 确认无新增错误
4. 删除后启动后端确认无 import 错误
5. 更新 `src/components/common/index.js` 如有残留引用
6. 更新 `ComponentComparison.vue` 移除 DynamicFilters 展示

#### FR-001 后续实施路径

```
1. 新建 meta/schemas/system_config.yaml → 定义配置字段
2. 新建 meta/api/system_config_api.py → 配置 CRUD API
3. 在 server.py 注册 system_config_bp
4. 前端: SystemSettings.vue → 替换为 MetaForm + useMetaList
5. 数据迁移: localStorage → API 写入数据库
```

#### FR-002 后续实施路径

```
1. 合并 change_event / change_subscription 的建表 DDL 到 generated_schema.sql
2. 补充 YAML schema 中的完整语义定义
3. 重构 notification_api.py: 直接 SQL → bo_framework CRUD
4. 如有 WebSocket 推送，通过 PersistenceInterceptor 挂载
5. 回归测试变更通知功能
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| 仅清理死代码，其他仅记录 | 零风险，快速交付 | 架构问题未解决 | 本次采用 |
| 一次性全部修复 | 一步到位 | 工作量大，风险高 | 不采用 |

### 9.5 实施与测试策略

- **FR-003/FR-004 测试策略**:
  - 前端: `npm run build` 成功
  - 后端: 启动无 import 错误
  - 手动测试: 用户管理/用户组管理的 CRUD 功能正常（确认 MetaListPage enableAutoCrud 正常）
- **风险缓解**: 所有删除操作在 Git 版本控制下，可随时恢复
- **回滚方案**: `git revert`

---

## 10. TBD 清单

| ID | 条目 | 缺失信息 | 下一步 |
|----|------|----------|--------|
| TBD-1 | SystemSettings 配置持久化方案 | 是否需要多用户共享配置？是否需要配置变更审计？ | 后续评估 |
| TBD-2 | change_event 重构时机 | 是否有其他高优先级任务？变更通知功能的使用频率？ | 后续评估 |
| TBD-3 | UserPermissionManagement 目录清理 | `src/views/UserPermissionManagement/` 中的 UserProfile.vue 和 UserSettings.vue 是否仍需要？ | 后续评估 |

---

## 附录: 代码审查完整发现清单

以下为本轮代码审查中发现的所有可清理项（部分已在 FR-003 中覆盖）：

### 立即可删除（零引用，确认死代码）

1. [OK] `src/components/common/DynamicFilters.vue` — 已从公共导出移除
2. [OK] `src/components/common/__tests__/DynamicFilters.test.js`
3. [OK] `src/components/common/__tests__/DynamicFilters.spec.js`
4. [OK] `meta/api/manage_api.py_temp` — 临时文件
5. [OK] `src/components/ArchWorkspace.vue` — 旧版首页，路由已切换
6. [OK] `src/views/SystemManagement/AddMemberDialog.vue`
7. [OK] `src/views/SystemManagement/__tests__/AddMemberDialog.spec.js`
8. [OK] `src/views/SystemManagement/GroupFormDialog.vue`
9. [OK] `src/views/SystemManagement/__tests__/GroupFormDialog.spec.js`
10. [OK] `src/views/SystemManagement/UserFormDialog.vue`

### 迁后删除（有跨层依赖，需先处理依赖）

11. `src/views/ArchDataManageApp/` (整个目录) — `services/archDataConverter.js` 依赖其 `utils/hierarchyFilterBuilder.js`，需先提取工具函数
12. `src/config/menuConfig.js` — 标记 `@deprecated`，待 API 驱动菜单完全稳定后删除

### 记录技术债务（需后续专项处理）

13. `meta/schemas/employee_data_scope.yaml` — 实验性功能，需决定去留
14. `meta/api/management_dimension_api.py` 中 `roles_bp` / `meta_bp` — 悬空蓝图
15. SystemSettings.vue 迁移 — 本 Spec FR-001
16. change_event / change_subscription 架构对齐 — 本 Spec FR-002

---

Spec 包含 10 节，最后一节为 "TBD 清单"，内容完整。