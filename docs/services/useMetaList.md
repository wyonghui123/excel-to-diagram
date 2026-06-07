# useMetaList

> **Composable 路径**: `src/composables/useMetaList.js`
> **重构版本**: v1.5.0 (PR 4 + PR 5 完成)
> **原始版本**: 2,499 行 / 76,688 字节
> **重构后版本**: 2,402 行 / 73,319 字节（**-97 行 / -3.9%**）
> **关联 spec**: [spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md)

---

## 1. 概述

`useMetaList` 是 v1 frontend 的"中间件 + 双向 + self-loop"三角中心 composable（spec v1.5.0 §0.5.1）。它提供元数据驱动的动态列表能力，被 12 个组件消费（12 consumer / 25 文件 / 4 displayMode）。

## 2. 重构历程

| 版本 | 日期 | 关键变更 | 行数 |
|:---:|------|---------|:---:|
| v1.0.0 | 2026-06-05 | 初版 | 2,499 |
| v1.5.0 (PR 4) | 2026-06-06 | 3 个下沉点（keyTemplate + draftPersist）| **2,402** |

### 2.1 PR 4 下沉的 3 个函数

| 函数 | 原行数 | 新行数 | 抽到 service |
|------|:-----:|:-----:|---------|
| `_suggestKeyTemplateCode` | 47 | 11 | [keyTemplateService](./keyTemplateService.md) |
| `saveDraftValues` 业务逻辑 | 64 | 21 | [draftPersistService](./draftPersistService.md) |
| `getDraftCreates` | 24 | 1 | [draftPersistService](./draftPersistService.md) |
| **总计** | **135** | **33** | **2 service** |

## 3. 公开 API（85 顶层 + 4 export）

完整 API 列表见 [api_contract.spec.js](../specs/spec-fr-ui-003-004-005-useMetaList-refactor.md) 或 [useMetaList.api_contract.spec.js](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useMetaList.api_contract.spec.js)。

### 3.1 主函数：`useMetaList(objectType, options)`

**参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|:---:|:---:|------|
| `objectType` | `string` | ✅ | — | 实体类型（如 'user', 'role'）|
| `options` | `Object` | ❌ | `{}` | 配置选项 |
| `options.mode` | `string` | ❌ | `'element-plus'` | 渲染模式 |
| `options.columnsOverride` | `Array` | ❌ | `null` | 列定义覆盖（compact mode）|
| `options.pageSize` | `number` | ❌ | `20` | 每页数量 |
| `options.autoLoad` | `boolean` | ❌ | `false` | 是否自动加载 |
| `options.debug` | `boolean` | ❌ | `false` | 调试模式（打印日志）|
| `options.displayMode` | `string` | ❌ | `'page'` | 4 种模式（page/embedded/dialog/默认）|
| `options.enableDetail` | `boolean` | ❌ | `false` | 启用详情 |
| `options.enableAutoCrud` | `boolean` | ❌ | `false` | 启用自动 CRUD |
| `options.enableInlineEdit` | `boolean` | ❌ | `false` | 启用 Inline Edit |

### 3.2 4 类返回 API（85 顶层）

#### 3.2.1 State（响应式状态）= 35 个
- 元数据：`metaConfig` / `objectType` / `config`
- 列表：`columns` / `visibleColumns` / `data` / `loading` / `selectedRows` / `selectedIds` / `isAllPagesSelected` / `totalSelectedCount` / `currentPageSelectedCount`
- 对话框：`showExportDialog` / `showImportDialog`
- 过滤器：`filterFields` / `visibleFilterFields` / `filterValues` / `headerFilterValues` / `contextFilters` / `apiFilterConfigs`
- 搜索：`searchFields` / `keyword`
- 导出/导入：`exportFilters` / `exportFields` / `importOptions`
- 操作按钮：`toolbarActions` / `toolbarRightActions` / `rowActions` / `batchActions`
- 分页排序：`pagination` / `paginationConfig` / `sortInfo` / `defaultSort` / `filteredTotalCount`
- 过滤器显示模式：`filterDisplayModeConfig`
- 选择配置：`selectionConfig`

#### 3.2.2 Inline Edit State（6 个）
- `inlineEditConfig` / `inlineEditMode` / `draftValues` / `editingCell` / `hoveredCell` / `hasUnsavedChanges`

#### 3.2.3 Methods（35 个）
- 核心：`init` / `loadList` / `refresh` / `getRowActions`
- 操作：`handleAction` / `handleToolbarAction` / `handleBatchAction` / `handleFilter` / `handleSearch` / `handleSortChange` / `handlePageChange` / `handlePageSizeChange` / `handleSelectionChange` / `handleHeaderFilter` / `resetHeaderFilter` / `resetFilters`
- 批量：`handleBatchDelete` / `handleBatchExport` / `handleBatchImport` / `handleExportSuccess` / `handleImportSuccess`
- 跨页选择：`selectAllCurrentPage` / `selectAllPages` / `clearAllSelection`

#### 3.2.4 Inline Edit Methods（16 个）
- 模式切换：`enableInlineEdit` / `disableInlineEdit`
- 单元格：`startEditCell` / `finishEditCell` / `updateDraftValue` / `cancelCellEdit`
- 新增/取消：`addNewRow` / `cancelInlineEdit`
- 保存/获取：`saveDraftValues` / `getDraftCreates`（**PR 4 下沉到 draftPersistService**）
- 判断：`isCellEditable` / `getFieldEditConfig` / `getCellValue` / `isEditing` / `isHovered` / `setHoveredCell` / `clearHoveredCell`

#### 3.2.5 关联导航（2 个）
- `navigableAssociations` / `getNavigableAssociations`

### 3.3 4 个 Export 工具函数

| 函数 | 用途 | spec |
|------|------|------|
| `useMetaList` | 主 composable | — |
| `formatDate(value, format)` | 日期格式化 | — |
| `truncateText(text, maxLength)` | 文本截断 | — |
| `getStatusTagType(status, colorMap)` | 状态标签类型 | — |

## 4. 4 种 displayMode（关键维度）

spec v1.5.0 §19.4 揭示 4 种 displayMode 行为差异：

| displayMode | 触发位置 | 行为差异 |
|-------------|---------|---------|
| `'page'` (default) | GenericObjectList / AuditLogManagement | 完整功能（工具栏+详情+导入导出）|
| `'embedded'` | ObjectPage/AssociationSection (3 处) + ObjectChildSection (useMetaList=true) | 嵌入模式（无外壳）|
| `'dialog'` | SearchHelpDialog (flat/tree_flat) + AssignmentDialog | 弹窗模式（无 draw header）|
| 未传 | 兜底为 page | 默认 page |

**selectionConfig 在 4 种 displayMode 下的行为矩阵**（见 [useMetaList.displaymode.spec.js](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useMetaList.displaymode.spec.js)）。

## 5. 12 个 Consumer（真实生产链路）

spec v1.5.0 §19.5 揭示 12 个组件消费 useMetaList：

### 5.1 4 displayMode 映射

| Consumer | displayMode | 用途 |
|----------|-------------|------|
| MetaListPage.vue | 自包含 | 核心（自包含）|
| GenericObjectList.vue | `'page'` | 路由级消费 |
| AuditLogManagement.vue | `'page'` | 真定制页（chart 容器 + cell slot + 详情 drawer）|
| ObjectPage/AssociationSection.vue | `'embedded'` | 3 处嵌入（m2m/annotation/default）|
| ObjectChildSection.vue | `'embedded'` (useMetaList=true) | 双模式切换 |
| SearchHelpDialog.vue | `'dialog'` | 值选择对话框（flat/tree_flat）|
| AssignmentDialog.vue | `'dialog'` | 分配对话框 |
| MultiObjectManagementPage.vue | 自定义 | 多对象管理页（useMultiObjectPage composable）|
| ObjectDetailPage.vue | 自包含 | 路由级详情页（包装 DetailPage）|
| 6 死代码 stub | `'page'` | **PR 8 已删除** |

### 5.2 35 个真实破坏面

| 类别 | 数量 |
|------|:---:|
| 核心消费 | 1 (MetaListPage) |
| 路由级消费 | 2 (GenericObjectList + ObjectDetailPage) |
| 真定制页 | 1 (AuditLogManagement) |
| 6 死代码 stub | 6 (PR 8 已删) |
| 5 嵌入 consumer | 5 (AssociationSection + ObjectChildSection + SearchHelp + Assignment + Multi) |
| 2 useMetaList 直接测试 | 2 (useMetaList.batch.spec + useMetaList.integration.spec) |
| 3 MetaListPage 子测试 | 3 (fk-link + AssociationNavigationMenu + NavigationSourceInfo) |
| 1 useDetail 平行测试 | 1 (useDetail.spec) |
| 2 formatDate 工具引用 | 2 (MetaListPage + AuditLogManagement) |
| InlineEditCell | 1 (ValueHelp 入口) |
| 其他 | 11 (ObjectPage 体系 + 详情页系列) |
| **总计** | **35 个文件** |

## 6. 集成测试覆盖

| 测试文件 | 用例 | 覆盖 |
|---------|:---:|------|
| [keyTemplateService.spec.js](file:///d:/filework/excel-to-diagram/src/services/__tests__/keyTemplateService.spec.js) | **15** | 业务规则 + 主入口 |
| [draftPersistService.spec.js](file:///d:/filework/excel-to-diagram/src/services/__tests__/draftPersistService.spec.js) | **17** | 业务规则 + 主入口 |
| [useMetaList.api_contract.spec.js](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useMetaList.api_contract.spec.js) | **17** | 85 API 数量 + 4 export |
| [useMetaList.behavior.spec.js](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useMetaList.behavior.spec.js) | **12** | 10 行为不变式 |
| [useMetaList.displaymode.spec.js](file:///d:/filework/excel-to-diagram/src/composables/__tests__/useMetaList.displaymode.spec.js) | **14** | 4 displayMode |
| **总计** | **75 PASS / 0 FAIL** | **3 层守卫** |

## 7. 风险矩阵（PR 4-5 已解决）

| # | 风险 | 来源 | 缓解 |
|:-:|------|------|------|
| 1 | useMetaList 行为变化 | spec v1.5.0 §25 | PR 5 接口契约（api_contract + behavior）|
| 2 | 响应式更新丢失 | PR 4 | 手动 set draftValues（service 纯函数）|
| 3 | callPost dynamic import 时序 | PR 4 | 保留动态 import |
| 4 | 测试覆盖不足 | spec v1.5.0 §25 | 32 service 单测 + 43 useMetaList 守卫 |

## 8. 未来扩展

- [ ] v3 引擎 M9 GraphQL 协议层（替代 boService.batch_save）
- [ ] v3 引擎 M10 MCP Server（AI Agent 工具暴露 85 API）
- [ ] v3 引擎 M11 声明式 RLS（替代 permission 配置）

## 9. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-05 | 初版（76,688 字节 / 2,499 行）| 原始 |
| 1.5.0 | 2026-06-06 | PR 4 下沉 3 个函数到 2 service（73,319 字节 / 2,402 行 / -97 行）| AI Agent (Trae) |
