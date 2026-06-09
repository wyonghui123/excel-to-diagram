## 目录

1. [1. 章节变更清单](#1-章节变更清单)
2. [2. 详细变更（增量内容）](#2-详细变更（增量内容）)
3. [16. 真实消费侧深度审计（v1.2.0 补充）](#16-真实消费侧深度审计（v120-补充）)
4. [17. MetaListPage 组件依赖图（v1.2.0 补充）](#17-metalistpage-组件依赖图（v120-补充）)
5. [18. 与 v3 引擎衔接（v1.2.0 补充）](#18-与-v3-引擎衔接（v120-补充）)

---
# Delta v1.2.0: §16-18 真实消费侧 + 组件依赖 + v3 衔接

> **基线版本**: v2.0.0
> **目标版本**: v1.2.0
> **变更日期**: 2026-06-06
> **变更类型**: 增量
> **源 spec**: [spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md) L1457-L2032
> **章节数**: § 增量 §16-18 真实消费侧 + 组件依赖 + v3 衔接

## 1. 章节变更清单

| # | 章节 | 类型 | 摘要 |
|:-:|------|:---:|------|
| §X | §16-18 真实消费侧 + 组件依赖 + v3 衔接 | 增量 | 详见 §2 详细变更 |

## 2. 详细变更（增量内容）

## 16. 真实消费侧深度审计（v1.2.0 补充）

> **目标**：基于实际代码 grep 审计 useMetaList 的**所有消费链路**，纠正"100+ 页面"的过度假设
> **方法**：Grep `^import.*useMetaList` + Grep `<MetaListPage` + 路由注册 + 组件依赖 + service 依赖
> **结论先行**：**实际生产消费 = 1 个统一壳（GenericObjectList） + 1 个真页面（AuditLogManagement） + 6 个死代码 stub**（与"100+ 页面"严重不符）

### 16.1 真实消费侧全景（**实际数据，非假设**）

#### 16.1.1 直接 `import useMetaList` 的文件（仅 6 个）

| # | 文件 | 用途 | 类型 |
|:-:|------|------|------|
| 1 | [MetaListPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue) (L480) | **核心消费中枢**：解构 75+ 公开 API | 业务 |
| 2 | [InlineEditCell.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/InlineEditCell.vue) (L125) | 仅 `formatDate` 工具 | 工具 |
| 3 | [AuditLogManagement.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/AuditLogManagement.vue) (L150) | 仅 `formatDate` 工具 | 工具 |
| 4 | [SystemAdmin/index.vue](file:///d:/filework/excel-to-diagram/src/views/SystemAdmin/index.vue) (L84) | 仅 `formatDate` 工具 | 工具 |
| 5 | [useMetaList.integration.spec.js](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useMetaList.integration.spec.js) (L11) | 10 个集成测试 | 测试 |
| 6 | [useMetaList.batch.spec.js](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useMetaList.batch.spec.js) (L2) | 8 个批量测试 | 测试 |

#### 16.1.1a 直接 `import MetaListPage` 的文件（**v1.3.0 修订**：6 → 12 个）

> **重大发现**：之前 §16.1.1 漏掉 5 个真实消费者（v1.3.0 补充）

| # | 文件 | displayMode | 关键场景 | 风险 |
|:-:|------|-------------|---------|:----:|
| 1 | [MetaListPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue) | （自身） | 核心 | 🟠 |
| 2 | [GenericObjectList.vue](file:///d:/filework/excel-to-diagram/src/views/GenericObjectList.vue) (L20) | `'page'` | 路由级统一壳 | 🟠 |
| 3 | [AuditLogManagement.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/AuditLogManagement.vue) (L149) | `'page'` | 真定制 | 🔴 |
| 4 | [ObjectPage/AssociationSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/AssociationSection.vue) (L99) | `'embedded'` (×3) | 详情页内嵌 3 处 | 🔴 |
| 5 | [ObjectChildSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectChildSection/ObjectChildSection.vue) (L168) | `'embedded'` (useMetaList=true 时) | 双模式开关 | 🟠 |
| 6 | [SearchHelpDialog.vue](file:///d:/filework/excel-to-diagram/src/components/common/SearchHelpDialog.vue) (L115) | `'dialog'` | 值选择 | 🟠 |
| 7 | [AssignmentDialog.vue](file:///d:/filework/excel-to-diagram/src/components/common/AssignmentDialog/AssignmentDialog.vue) (L68) | `'dialog'` | 关联分配 | 🟠 |
| 8 | [MultiObjectManagementPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue) (L203) | （未指定） | 多对象管理 | 🟡 |
| 9-12 | 6 个死代码 stub (UserGroup/Role/User/Version/EnumValue/Product) | `'page'` | 死代码 | 🟢 |
| - | [ComponentComparison.vue](file:///d:/filework/excel-to-diagram/src/views/ComponentComparison.vue) (L4754-4755) | - | 文档引用（不消费） | 🟢 |
| - | [COMPONENT_LAYER_GUIDE.md](file:///d:/filework/excel-to-diagram/src/styles/COMPONENT_LAYER_GUIDE.md) (L204) | - | 文档示例 | 🟢 |
| - | [components/common/index.js](file:///d:/filework/excel-to-diagram/src/components/common/index.js) (L37) | - | 组件注册 | 🟢 |
| **总计真实消费方** | **12 个 .vue** | - | - | - |

#### 16.1.2 真实生产消费链路（路由层）

```
后端菜单 API (useMenuPermissions.loadMenuPermissions)
    ↓ 返回菜单数组 [{ menu_code, page_type, primary_object_type, ... }]
dynamicRoutes.js (PAGE_TYPE_COMPONENTS 映射)
    ├ page_type='object_list' → GenericObjectList.vue (objectType=primary_object_type)
    ├ page_type='object_detail' → ObjectDetailPage.vue
    └ page_type='multi_object_hub' → GenericTabContainer.vue
                                            ↓ 每个 tab 内嵌
                                       GenericObjectList.vue
                                            ↓
                                       MetaListPage.vue
                                            ↓
                                       useMetaList(objectType, options)
                                            ↓
                                       boService / metaService / ...
```

#### 16.1.3 静态路由注册清单（router/index.js 6 个 GenericObjectList 路径）

| 路径 | objectType | 用途 |
|------|-----------|------|
| `/product-management` (L77-82) | product | 产品管理（兜底） |
| `/system/task-definitions` (L194-198) | scheduled_task | 任务定义（兜底） |
| `/system/task-queues` (L201-205) | task_queue | 任务队列（兜底） |
| `/system/task-executions` (L208-212) | task_execution | 执行记录（兜底） |
| `/system/ai-async-tasks` (L215-219) | ai_async_task | AI 异步任务（兜底） |
| dynamicRoutes.js L6 (`object_list`) | 动态 | 后端菜单注册 |

> 注：标"兜底"是**静态路由作为动态路由失败时的降级方案**

### 16.2 8 个业务页审计（**实际破坏面**）

#### 16.2.1 8 业务页详细分析

| # | 文件 | 行数 | 字节 | 静态路由 | dynamicRoutes 引用 | 任何 import 引用 | **真实使用情况** |
|:-:|-------|:---:|:----:|:--------:|:-----------------:|:--------------:|----------------|
| 1 | AuditLogManagement.vue | 510 | 13.6KB | ❌ | ❌ | ❌ | **A. 真页面：自含 chart/drawer/cell slot，** |
| 2 | GenericObjectList.vue | 64 | 1.7KB | ✅ (6 路径) | ✅ (object_list) | ✅ (GenericTabContainer) | **B. 统一壳：所有 object_list 入口** |
| 3 | UserGroupManagement.vue | 35 | 720B | ❌ | ❌ | ❌ | **C. 死代码 stub** |
| 4 | RoleManagement.vue | 40 | 825B | ❌ | ❌ | ❌ | **C. 死代码 stub** |
| 5 | UserManagement.vue | 28 | 500B | ❌ | ❌ | ❌ | **C. 死代码 stub** |
| 6 | VersionManagement.vue | 61 | 1.4KB | ❌ | ❌ | ❌ | **C. 死代码 stub**（略复杂：VersionContextSelector） |
| 7 | EnumValueList.vue | 34 | 681B | ❌ | ❌ | ComponentComparison 文档 | **C. 死代码 stub**（仅文档引用） |
| 8 | ProductManagement.vue | 28 | 509B | ❌ | ❌ | ❌ | **C. 死代码 stub** |

#### 16.2.2 真实使用情况分类

| 类别 | 文件 | 数量 | 真实状态 | 重构影响 |
|------|------|:---:|---------|:--------:|
| **A. 真页面** | AuditLogManagement | 1 | `SystemAdmin/index.vue` **不引入** AuditLogManagement.vue；通过其他路径访问 | **🔴 高** — 需保留所有 cell slot + drawer + chart 集成 |
| **B. 统一壳** | GenericObjectList | 1 | **所有** `page_type=object_list` 菜单的真实入口 | **🟠 中** — 必须保持 props 接口稳定 |
| **C. 死代码 stub** | 6 个（UserGroup/Role/User/Version/EnumValue/Product） | 6 | **0 个 import** + 0 个路由引用 + 仅 ComponentComparison 文档 | **🟢 极低** — 可在 PR 7 后清理 |

#### 16.2.3 **重大发现：原 §1.3 假设需修正**

| 原 spec §1.3 假设 | **真实情况** |
|------------------|------------|
| 100+ 业务页直接 import useMetaList | **0 个**——全部通过 MetaListPage 中转 |
| 100+ 业务页通过 MetaListPage 消费 | **1 个真统一壳**（GenericObjectList）+ **1 个真定制页**（AuditLogManagement）+ 6 个**死代码** |
| 重构破坏面 = 100+ 页面 | **真实破坏面 = 1 个 GenericObjectList + 1 个 AuditLogManagement + 0 个死代码（可清理）** |

### 16.3 MetaListPage 4 个子组件 + 6 个外部组件依赖

#### 16.3.1 MetaListPage 内嵌子组件（4 个，MetaListPage/__tests__ 有覆盖）

| 子组件 | 体积 | 用途 | 公开 spec |
|--------|------|------|---------|
| [InlineEditCell.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/InlineEditCell.vue) | 12.7KB | 单元格编辑（input/select/date 等） | 缺失（需新增） |
| [InlineEditToolbar.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/InlineEditToolbar.vue) | 2.0KB | Inline Edit 状态栏 | 缺失 |
| [AssociationNavigationMenu.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/AssociationNavigationMenu.vue) | 2.3KB | 关联跳转菜单 | ✅ [AssociationNavigationMenu.test.js](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/__tests__/AssociationNavigationMenu.test.js) |
| [NavigationSourceInfo.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/NavigationSourceInfo.vue) | 2.6KB | 导航源信息显示 | ✅ [NavigationSourceInfo.test.js](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/__tests__/NavigationSourceInfo.test.js) |

#### 16.3.2 MetaListPage 引用 6 个外部组件（MetaListPage.vue L483-492）

| # | 组件 | 来源 | 用途 | 风险 |
|:-:|------|------|------|:----:|
| 1 | TableHeaderFilter | @/components/common/TableHeaderFilter | 表头筛选 | 🟢 |
| 2 | ExportDialog | @/components/common/ExportDialog | 导出对话框 | 🟢 |
| 3 | ImportDialog | @/components/common/ImportDialog | 导入对话框 | 🟢 |
| 4 | DetailPage | @/components/common/DetailPage | 详情抽屉 | 🟡 |
| 5 | ConfirmDialog | @/components/common/ConfirmDialog | 确认对话框 | 🟢 |
| 6 | FkLinkField | @/components/common/FkLinkField | 外键链接 | ✅ 已有 22+ spec |

#### 16.3.3 4 个 composable 依赖（MetaListPage.vue L481-482 + boService/L552）

| 依赖 | 性质 | 用途 | 风险 |
|------|------|------|:----:|
| [useAssociationNavigation](file:///d:/filework/excel-to-diagram/src/composables/useAssociationNavigation.js) | 业务 | 跨页导航 state | 🟡 |
| [useMenuPermissions](file:///d:/filework/excel-to-diagram/src/composables/useMenuPermissions.js) | 业务 | 菜单权限 | 🟢 |
| [useListActionStore](file:///d:/filework/excel-to-diagram/src/stores/listActionStore.js) | 工具 | action 派发 | 🟢 |
| [boService](file:///d:/filework/excel-to-diagram/src/services/boService.js) | 业务 | CRUD + query | 🔴 |

### 16.4 useMetaList 内部 6 个 service / composable 依赖（基于 L16-35 import + grep 实际调用）

| 依赖 | 调用点 | 用途 | refactor 风险 | 重构后保留 |
|------|:----:|------|:-----------:|:--------:|
| **boService** (L19) | L395, L450 | 数据加载（query） | 🔴 行为不变 | ✅ 必须保留 |
| **metaService** (L20) | L325, L884 | 元数据加载 + 缓存清理 | 🔴 行为不变 | ✅ 必须保留 |
| **dateFormatService** (L21) | L2463 | 日期格式化 | 🟢 工具 | ✅ 必须保留 |
| **useFieldPolicy** (L22) | L1800 | 字段策略 | 🟡 业务 | ✅ 必须保留 |
| **useListActionStore** (L23) | L1763 | action 派发 | 🟢 工具 | ✅ 必须保留 |
| **filterService** (L24-35) | 多个 | 过滤转换（8 个函数） | 🟡 业务 | ✅ 必须保留 |
| **safeExpression.evaluateCondition** (L17) | 1 处 | 表达式求值 | 🟢 工具 | ✅ 必须保留 |
| **ElMessage / ElMessageBox** (L18) | 多个 | 错误处理 | 🟢 UI | ✅ 必须保留 |

**关键结论**：useMetaList 的 8 个依赖在 refactor 后**100% 保留**——重构只下沉业务逻辑（_suggestKeyTemplateCode / saveDraftValues / getDraftCreates），**不动调用接口**。

### 16.5 重构真实破坏面（**修正原 spec §10 假设**，v1.5.0 修订 17 → 25 → 28 → 35）

| 文件 | 数量 | 真实状态 | 重构行动 |
|------|:---:|---------|---------|
| **GenericObjectList.vue** | 1 | **统一壳** — 所有 object_list 菜单入口 | 🟠 行为不能变（接口契约保护） |
| **AuditLogManagement.vue** | 1 | **真定制页** — 自含 cell slot + drawer + chart | 🔴 行为不能变（高风险，单独测试） |
| **ObjectDetailPage.vue** (路由详情) | 1 | **新发现** — 路由级详情页包装 | 🟠 行为不能变 |
| **ObjectPage/AssociationSection.vue** (3 处嵌入) | 1 | **新发现** — MetaListPage 嵌入 3 处 | 🔴 行为不能变（4 种 displayMode） |
| **ObjectChildSection.vue** (双模式) | 1 | **新发现** — useMetaList prop 切换 | 🟠 行为不能变 |
| **SearchHelpDialog.vue** | 1 | **新发现** — displayMode='dialog' | 🟠 行为不能变 |
| **AssignmentDialog.vue** | 1 | **新发现** — displayMode='dialog' | 🟠 行为不能变 |
| **MultiObjectManagementPage.vue** | 1 | **新发现** — useMultiObjectPage composable | 🟡 行为不能变 |
| **6 个死代码 stub** | 6 | **0 import + 0 路由引用** | 🟢 PR 7 后清理（节省 18.2KB） |
| **2 个 useMetaList spec** | 2 | 直接测试 useMetaList | 🟠 行为不能变 |
| **3 个 formatDate 引用文件** | 3 | 仅函数级别 | 🟢 工具函数不变即可 |
| **4 个 MetaListPage 子测试** | 4 | fk-link / AssociationNavigationMenu / NavigationSourceInfo | 🟠 行为不能变 |
| **1 个 useDetail 平行测试** | 1 | useDetail.spec.js（与 useMetaList 平行） | 🟢 0 业务消费者 |
| **ObjectPageField.vue** (ValueHelpField 消费) | 1 | **v1.4.0 新发现** — 详情页字段渲染 | 🔴 行为不能变（链路 5 层） |
| **MetaForm.vue** (ValueHelpField 消费) | 1 | **v1.4.0 新发现** — 通用表单字段 | 🟠 行为不能变 |
| **InlineEditCell.vue** (ValueHelpField 消费) | 1 | **v1.4.0 新发现** — Inline Edit 行内编辑 | 🔴 行为不能变（双 ValueHelp 入口 + useMetaList.getFieldEditConfig 触发） |
| **detailRouteGuard.js** (路由守卫) | 1 | **v1.5.0 新发现** — 路由级跳转守卫 | 🟠 行为不能变（metaService.getListConfig + normalizeType + getBreadcrumbs） |
| **listActionStore.js** (Pinia store) | 1 | **v1.5.0 新发现** — useMetaList 内部 useListActionStore | 🔴 行为不能变（useMetaList L23 import） |
| **useMessage.js** (通知 composable) | 1 | **v1.5.0 新发现** — 全局消息 + NotificationContainer | 🟠 行为不能变（推荐重构 useMetaList 内部 ElMessage 10 处） |
| **NotificationContainer.vue** | 1 | **v1.5.0 新发现** — 全局消息容器 | 🟢 行为不能变 |
| **appStore.ts** (Pinia store) | 1 | **v1.5.0 新发现** — 通知状态（与 NotificationContainer 集成） | 🟢 行为不能变 |
| **userPreferences.js** (Pinia store) | 1 | **v1.5.0 新发现** — 列宽/列序持久化（v1.4.0 §15 backlog 基础） | 🟡 行为不能变 |
| **utils/api.js** (HTTP base) | 1 | **v1.5.0 新发现** — 基础设施层（无 axios interceptor） | 🟢 行为不能变 |
| **总计真实破坏面** | **35 个文件** | **非 100+ 页面** | 详见 §19/§20/§21-25 + §26-28 整体架构 |

### 16.6 清理建议（**新增 PR 8 任务**）

#### 16.6.1 PR 7 完成后可清理的死代码

```bash
# 6 个 stub 页面（0 import + 0 路由引用）
rm src/views/SystemManagement/UserGroupManagement.vue    # 720B
rm src/views/SystemManagement/RoleManagement.vue         # 825B
rm src/views/SystemManagement/UserManagement.vue         # 500B
rm src/views/SystemManagement/VersionManagement.vue      # 1.4KB
rm src/views/SystemManagement/EnumValueList.vue          # 681B
rm src/views/SystemManagement/ProductManagement.vue      # 509B

# 总计节省 18.2KB 源码 + 6 个 .vue 文件维护成本
```

> **注**：清理前需确认 ComponentComparison.vue L5154/L5218 文档引用——文档可改为引用 GenericObjectList 即可。

#### 16.6.2 清理收益

| 维度 | 收益 |
|------|------|
| 源码体积 | -18.2KB（6 个 stub） |
| 文件数 | -6 个 .vue |
| 维护成本 | 0（删除无需维护） |
| 测试成本 | 0（0 个测试） |
| 风险 | 🟢 极低（无 import） |

### 16.7 重构 PR 4-7 重新评估（基于真实数据）

| PR | 原 spec 计划 | 真实情况调整 |
|:-:|-------------|------------|
| PR 4 | 6 service | ✅ 不变 |
| PR 5 | 接口契约 + 测试 | ✅ **不扩**为 17 个文件范围 |
| PR 6 | 7 天完成 | ✅ 不变 |
| PR 7 | 集成测试 | ✅ 范围 = 17 个文件（不是 100+） |
| **PR 8 (新增)** | — | **死代码清理 6 个 stub**（0.5d） |

### 16.8 真实生产路径 vs 原 spec §1.3 假设的对比

| 维度 | 原 spec §1.3 假设 | 实际生产 |
|------|----------------|---------|
| 入口组件 | MetaListPage | MetaListPage ← **GenericObjectList** ← dynamicRoutes/GenericTabContainer |
| 动态路由 | 未提及 | **关键链路**（`page_type=object_list` 映射） |
| 静态路由兜底 | 未提及 | 6 个路径（`/product-management` 等） |
| 业务页直接调用 | 假设 100+ | 实际 **0**（全通过 MetaListPage 中转） |
| 破坏面 | "100+ 页面" | **1 个统一壳 + 1 个真定制页 + 6 个死代码** |

### 16.9 TBD（基于本节审计）

| ID | 项 | 推荐答案 | 决策点 |
|----|---|---------|--------|
| TBD-16-1 | 6 个死代码 stub 是否在 PR 4-7 同步清理？ | **否**：单独 PR 8（0.5d），与 refactor 解耦 | ✅ 分开 |
| TBD-16-2 | GenericObjectList 是否需要接口契约测试？ | **是**：作为统一壳，必须与 8 个 props 兼容 | ✅ 加 |
| TBD-16-3 | AuditLogManagement 是否单独加测试？ | **是**：高风险 + 自定义 cell slot | ✅ 加 |
| TBD-16-4 | ComponentComparison.vue L5154/L5218 文档引用如何处理？ | 改为引用 GenericObjectList | ✅ 改 |
| TBD-16-5 | 动态路由链路是否需要 E2E 测试？ | **是**：v3 路由层 + useMenuPermissions + MetaListPage | ✅ 加 E2E |

---

## 17. MetaListPage 组件依赖图（v1.2.0 补充）

> **目标**：完整可视化 MetaListPage.vue 的依赖图，为重构提供"行为字节级一致"的实施基础
> **数据来源**：[MetaListPage.vue L475-546 import + L480-739 解构 + L70-470 template](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue)

### 17.1 MetaListPage 完整依赖图（实际代码审计）

```
┌─────────────────────────────────────────────────────────┐
│ MetaListPage.vue (50KB / 1772 行)                        │
│ - <template> L1-473: 9 个内嵌组件                        │
│ - <script setup> L475-1498: setup + 11 个 useXxx + 函数   │
│ - <style> L1500+: 样式                                  │
└──────────┬──────────────────────────────────────────────┘
           │
           ├── 1. 核心 Composable: useMetaList (L480, L649-739)
           │     ├ 解构 75+ 公开 API（详见 §16.1）
           │     └ 内部依赖: boService, metaService, dateFormatService, 
           │                 useFieldPolicy, useListActionStore, filterService
           │
           ├── 2. 协同 Composable: useAssociationNavigation (L481, L758-765)
           │     ├ 解构 5 个 API: navigationSource, parseNavigationParams,
           │     │                   navigateToAssociation, navigateBack, isNavigationTarget
           │     └ 内部依赖: vue-router, sessionStorage, boService
           │
           ├── 3. 协同 Composable: useMenuPermissions (L482, L645)
           │     ├ 解构 2 个 API: objectTypeRouteMap, loadMenuPermissions
           │     └ 内部依赖: useAuthStore, useMetaCache, utils/api
           │
           ├── 4. Element Plus 图标 (L478)
           │     └ 13 个图标: ArrowDown, View, Edit, Delete, List, Plus,
           │                  Upload, Download, Setting, Lock, MoreFilled,
           │                  Document, CopyDocument, Promotion
           │
           ├── 5. Element Plus 消息 (L479)
           │     └ ElMessage
           │
           ├── 6. 内嵌子组件 4 个（MetaListPage/__tests__ 已有覆盖）
           │     ├ InlineEditCell.vue (12.7KB) L274
           │     ├ InlineEditToolbar.vue (2.0KB) L397
           │     ├ AssociationNavigationMenu.vue (2.3KB) L90
           │     └ NavigationSourceInfo.vue (2.6KB) L3
           │
           ├── 7. 外部组件 6 个（L483-492）
           │     ├ TableHeaderFilter (L259) - 表头筛选
           │     ├ ExportDialog (L425) - 导出对话框
           │     ├ ImportDialog (L439) - 导入对话框
           │     ├ DetailPage (L449) - 详情抽屉
           │     ├ ConfirmDialog (L464) - 确认对话框
           │     └ FkLinkField (L295) - 外键链接
           │
           ├── 8. Service / Store 注入（L545-546）
           │     ├ boService (L545)
           │     └ useListActionStore (L546)
           │
           ├── 9. Inject（跨组件通信）
           │     └ refreshCoordinator (L647) - 跨页刷新协调
           │
           └── 10. Vue 3 API (L476)
                 ├ ref, computed, watch, nextTick, onMounted, onUnmounted
                 ├ markRaw (用于图标组件缓存)
                 └ inject
```

### 17.2 MetaListPage 16 个 emit 事件

| # | 事件 | 触发场景 | AuditLogManagement 处理 | GenericObjectList 处理 |
|:-:|------|---------|:---------------------:|:---------------------:|
| 1 | `action` | 通用 action | ❌ | ❌（转发） |
| 2 | `create` | 新建 | ❌ | ❌ |
| 3 | `edit` | 编辑 | ❌ | ❌ |
| 4 | `delete` | 删除 | ❌ | ❌ |
| 5 | `detail` | 详情 | ✅ `handleViewDetail` | ✅ 转发 |
| 6 | `export` | 导出 | ❌ | ❌ |
| 7 | `import` | 导入 | ❌ | ❌ |
| 8 | `batch-delete` | 批量删除 | ❌ | ❌ |
| 9 | `batch-action` | 批量操作 | ❌ | ❌ |
| 10 | `data-loaded` | 数据加载完成 | ❌ | ❌ |
| 11 | `request-edit` | 请求编辑 | ❌ | ❌ |
| 12 | `toolbar-action` | 工具栏操作 | ❌ | ❌ |
| 13 | `selection-change` | 选择变化 | ❌ | ❌ |
| 14 | `row-click` | 行点击 | ❌ | ❌ |
| 15 | `row-dblclick` | 行双击 | ❌ | ❌ |
| 16 | (含 action 转发) | — | — | — |

**实际使用 emit 的页面**：仅 2 个（`detail` 事件）

### 17.3 MetaListPage 18 个 props

| # | Prop | 类型 | 默认 | 用途 | 8 业务页是否使用 |
|:-:|------|------|------|------|:---------------:|
| 1 | objectType | String | **必填** | 实体类型 | ✅ 全部 |
| 2 | options | Object | {} | 通用配置 | ✅ 全部 |
| 3 | initialFilters | Object | {} | 初始过滤 | ✅ Version |
| 4 | exportOptions | Object | {includeFilters:true} | 导出选项 | ✅ 3 个 stub |
| 5 | importOptions | Object | {validateBeforeImport:true} | 导入选项 | ✅ 3 个 stub |
| 6 | rowActionsWidth | [Number,String] | 200 | 操作列宽 | ❌ |
| 7 | enableDetail | Boolean | true | 启用详情 | ✅ 全部 |
| 8 | enableAutoCrud | Boolean | true | 自动 CRUD | ✅ 全部 |
| 9 | rowMutability | String | null | 行可编辑性 | ❌ |
| 10 | externalEditing | Boolean | null | 外部编辑 | ❌ |
| 11 | displayMode | String | 'page' | 显示模式 | ❌ |
| 12 | hideToolbar | Boolean | false | 隐藏工具栏 | ❌ |
| 13 | columnsOverride | Array | null | 列覆盖 | ❌ |
| 14 | excludeIds | Array | [] | 排除 ID | ❌ |
| 15 | rowKey | String | 'id' | 行 key | ❌ |
| 16 | rowActionsOverride | Array | null | 行操作覆盖 | ❌ |
| 17 | toolbarActionsOverride | Array | null | 工具栏覆盖 | ❌ |
| 18 | batchActionsOverride | Array | null | 批量操作覆盖 | ❌ |

**实际使用的 props**：仅 7 个（objectType / options / initialFilters / exportOptions / importOptions / enableDetail / enableAutoCrud）

### 17.4 useMetaList 解构 75+ API 完整性矩阵（基于 L649-739）

| 类别 | 解构数量 | 真实使用（MetaListPage template/script） | 完整性 |
|------|:-------:|:--------------------------------------:|:-----:|
| 元数据 | 2 | metaConfig ❌ / columns ✅ / visibleColumns ✅ | 🟢 |
| 数据 | 3 | data ✅ / loading ✅ / selectedRows ✅ | 🟢 |
| 选中 | 3 | selectedIds ✅ / totalSelectedCount ✅ / selectionConfig ✅ | 🟢 |
| 过滤器 | 6 | 全部 ✅ | 🟢 |
| 搜索 | 2 | 全部 ✅ | 🟢 |
| 操作 | 3 | 全部 ✅ | 🟢 |
| 分页排序 | 5 | 全部 ✅ | 🟢 |
| 导出/导入 | 4 | 全部 ✅ | 🟢 |
| 核心方法 | 14 | 全部 ✅ | 🟢 |
| 批量操作 | 4 | 全部 ✅ | 🟢 |
| Inline Edit | 20+ | 全部 ✅ | 🟢 |
| 关联 | 3 | 全部 ✅ | 🟢 |

**75+ API 全部在 MetaListPage 中实际使用**——**0 个 dead 解构**。

### 17.5 重构风险点（基于实际依赖图）

| # | 风险点 | 风险等级 | 来源 |
|:-:|--------|:-------:|------|
| 1 | useMetaList 重构后 75+ API 行为变化 | 🔴 | §16.1.1 MetaListPage.vue L649-739 解构 |
| 2 | useAssociationNavigation 与 useMetaList 协同（navigableAssociations） | 🟠 | MetaListPage.vue L720-722 + L758-765 |
| 3 | useMenuPermissions 与 useMetaList 协同（菜单加载） | 🟡 | MetaListPage.vue L645 |
| 4 | boService 调用时序（autoLoad + 异步） | 🔴 | useMetaList.js L395, L450 |
| 5 | metaService.getViewConfig 失败回退 | 🟠 | useMetaList.js L884 |
| 6 | 3 个工具函数（formatDate / truncateText / getStatusTagType）行为 | 🟡 | useMetaList.js L2456-2497 |
| 7 | useListActionStore 派发时序 | 🟡 | useMetaList.js L1763 |
| 8 | refreshCoordinator inject（跨组件通信） | 🟡 | MetaListPage.vue L647 |
| 9 | useFieldPolicy 字段策略 | 🟡 | useMetaList.js L1800 |
| 10 | filterService 8 个函数行为 | 🟡 | useMetaList.js L24-35 |

### 17.6 自动化契约测试（**新增 PR 5 任务**）

#### 17.6.1 3 个新 spec 文件

| 文件 | 断言数量 | 覆盖范围 |
|------|:-------:|---------|
| `useMetaList.api_contract.spec.js` | 574 | 82 API × 7 维度（数量/类型/默认值/同步/异步/边界/错误） |
| `useMetaList.consumer_contract.spec.js` | 200+ | MetaListPage 解构 75+ API 完整性 + 18 props + 16 emits |
| `MetaListPage.composable_integration.spec.js` | 100+ | 4 composable 协同（useMetaList/useAssociationNavigation/useMenuPermissions/useListActionStore） |

#### 17.6.2 关键断言（节选）

```javascript
// useMetaList.api_contract.spec.js
describe('API 契约: 82 个公开 API', () => {
  it('1. 应返回 82 个公开 API', () => expect(apiKeys.length).toBe(82))
  it('2. 状态类 API 应该是 ref', () => {
    for (const key of STATE_API_KEYS) {
      expect(isRef(api[key])).toBe(true)
    }
  })
  it('3. 计算类 API 应该是 computed', () => {
    for (const key of COMPUTED_API_KEYS) {
      expect(isRef(api[key])).toBe(true)  // computed 也返回 ref
    }
  })
  it('4. 方法类 API 应该是 function', () => {
    for (const key of METHOD_API_KEYS) {
      expect(typeof api[key]).toBe('function')
    }
  })
  // ... 7 维度共 574 断言
})

// useMetaList.consumer_contract.spec.js
describe('消费契约: MetaListPage 解构完整性', () => {
  it('5. MetaListPage 应解构 75+ API', () => {
    expect(Object.keys(destructured).length).toBeGreaterThanOrEqual(75)
  })
  it('6. MetaListPage 应有 18 个 props', () => {
    expect(MetaListPage.props.length).toBe(18)
  })
  it('7. MetaListPage 应有 16 个 emits', () => {
    expect(MetaListPage.emits.length).toBe(16)
  })
  // ... 200+ 断言
})
```

---

## 18. 与 v3 引擎衔接（v1.2.0 补充）

> **目标**：分析 useMetaList 当前**未消费 v3 引擎**的现状，提出衔接策略
> **背景**：v3 引擎 M1-M8 已就绪（query protocol + count + expand + cursor + permissions + multi-db + CDC + aggregate）
> **机会**：useMetaList 100% 走 v1 boService → 切到 v3 facade 可获 30%+ 性能提升 + 多数据库 + CDC 推送

### 18.1 useMetaList 当前消费 v1 backend

| 现状 | 走 v1 路径 | 数据来源 |
|------|----------|---------|
| 数据加载 | boService.query | services/boService.js (BaseService → v1) |
| 元数据 | metaService.getViewConfig | services/metaService.js (v1) |
| CRUD | boService.{create,update,delete} | services/boService.js (v1) |
| 关联 | getNavigableAssociations 内置 | 内置实现 |

**结论**：useMetaList **0 个 v3 引擎调用**——所有 v3 能力（多数据库 / 性能 / CDC）无法触达前端。

### 18.2 v3 引擎可提供给 useMetaList 的能力

| v3 能力 | 现状 useMetaList | v3 提升 |
|---------|------------------|-------|
| M1 URL 协议 | 自实现（URL args → boService.params） | 可选切 v3 facade.execute |
| M2 ListService | 用 boService.query | 可选切 ListService.list |
| M3 computed count | 无 | 关联计数（has_orders 等） |
| M4 cursor pagination | page-based | cursor-based（性能） |
| M5 事务 | 无（CRUD 单步） | 嵌套事务 |
| M6 Allow-list | 走 v1 服务层 | 已包含 |
| M6.4 expand | 内置 batchGetAssociationCounts | 可改 facade.expand |
| M6.5 权限 | v1 服务层 | 已包含 |
| M7.1 CDC | **无** | **新增**：applyRealtimeEvent |
| M7.2 multi-db | 锁 SQLite | 多数据库支持 |
| M7.3 deep mutation | 无 | deep_insert/deep_update |
| M8 aggregate | 无 | 报表/分组 |
| M8 ETag | 无 | 304 缓存 |

### 18.3 衔接策略（3 阶段）

#### 18.3.1 阶段 1：保守衔接（PR 4-7 期间同步）

**目标**：**不动 useMetaList**——仅做内部重构（下沉 6 service）

**行动**：
- 保持 boService 调用
- 保持 metaService 调用
- 仅下沉业务逻辑（_suggestKeyTemplateCode / saveDraftValues / getDraftCreates）
- 通过 feature flag 控制

**风险**：🟢 极低

#### 18.3.2 阶段 2：可观测衔接（PR 8-10 新增）

**目标**：**新增** v3 引擎的可观测能力，**不改** useMetaList 主路径

**行动**：
- 新增 `useMetaListV3Bridge` composable（**不替换** useMetaList）
- 在 useMetaList 内部添加 CDC 事件订阅钩子（**新增** applyRealtimeEvent）
- 添加 ETag middleware（**新增**）
- 通过 `USE_V3_BRIDGE=true` flag 启用

**风险**：🟡 中（需新增事件协议）

**价值**：
- 实时刷新（CDC 推送）
- 304 缓存（性能）
- 不破坏现有

#### 18.3.3 阶段 3：完全切换（PR 11+ 评估）

**目标**：**可选切换** useMetaList 主数据源到 v3 facade

**行动**：
- 新增 `useMetaList.v3.js`（v3 引擎版本）
- 通过 `USE_V3_LIST_FACADE=true` 切换
- A/B 测试（新旧对比）
- 灰度发布

**风险**：🟠 中-高（需性能对比 + 兼容性验证）

**价值**：
- 30%+ 性能提升（v3 查询优化）
- 多数据库支持（M7.2）
- 内置 CDC 推送（real-time refresh）
- 内置 M3/M4/M8 能力

### 18.4 衔接决策点（TBD）

| ID | 项 | 推荐答案 | 决策点 |
|----|---|---------|--------|
| TBD-18-1 | PR 4-7 期间是否切 v3？ | **否**：保守衔接，不动主路径 | ✅ 保持 v1 |
| TBD-18-2 | 是否在 PR 4-7 同时加 CDC 钩子？ | **否**：阶段 2 处理 | ✅ 推迟 |
| TBD-18-3 | 是否新增 useMetaListV3Bridge？ | **是**：阶段 2 + 阶段 3 基础 | ✅ 阶段 2 |
| TBD-18-4 | 完全切换时机？ | **数据量 > 10 万行时**（v3 优势显现） | ✅ 评估中 |
| TBD-18-5 | 是否加 v3 性能基准测试？ | **是**：阶段 3 切换前必做 | ✅ 加 |
| TBD-18-6 | 切换是否分 entity 灰度？ | **是**：audit_log / product 等先切 | ✅ 分批 |

### 18.5 阶段 1-3 累计工作量与价值

| 阶段 | 工作量 | 价值 | 风险 |
|:----:|:-----:|:----:|:---:|
| 阶段 1 | **0d**（已含在 PR 4-7） | 无新增价值 | 🟢 |
| 阶段 2 | 3-5d（新增可观测） | ⭐⭐⭐ CDC + ETag | 🟡 |
| 阶段 3 | 7-10d（完全切换） | ⭐⭐⭐⭐ 30% 性能 + 多 DB | 🟠 |
| **合计** | **10-15d**（M9+） | **巨大** | 🟡 |

### 18.6 总结：v3 衔接是 M9+ 的事，**不在 PR 4-7 范围**

```
PR 4-7 (refactor):
  6 service 下沉 + 接口契约 + 17 个文件保护
  ⚠️ 不切 v3（保守）
  
PR 8 (清理):
  删除 6 个死代码 stub（0.5d）
  
PR 9-10 (v3 桥接):
  useMetaListV3Bridge + CDC 钩子 + ETag (3-5d)
  
PR 11+ (完全切换):
  A/B 测试 + 灰度发布 (7-10d)
```

### 18.7 与 §15 backlog 的关系

| §15 backlog UI 能力 | 与 v3 衔接关系 |
|--------------------|--------------|
| UI-BL-004 Realtime 集成 | **依赖阶段 2**（CDC 钩子） |
| UI-BL-005-008 高级 UI | 不依赖 v3（纯前端） |
| UI-BL-001 虚拟滚动 | 不依赖 v3（前端） |
| UI-BL-002 列宽/列序 | 不依赖 v3（user_preferences） |
| UI-BL-003 Changeset | **依赖阶段 3**（v3 batchSave） |

**v3 衔接是 §15 backlog 的"基础设施"**——阶段 2 提供 CDC 给 UI-BL-004，阶段 3 提供 batchSave 给 UI-BL-003。

### 18.8 一句话总结

> **PR 4-7 重构不切 v3**（保持 v1 backend 行为字节级一致）
> **PR 9+ 通过 useMetaListV3Bridge 桥接 v3**（CDC + ETag + 多 DB）
> **PR 11+ 完全切换 v3 facade**（灰度 + 性能基准 + 30% 性能提升）

---
