## 目录

1. [1. 现状](#1-现状)
2. [2. Phase 1 成果总结（已完成）](#2-phase-1-成果总结（已完成）)
3. [3. Phase 2 规划：剩余可提取点](#3-phase-2-规划：剩余可提取点)
4. [4. 实施计划](#4-实施计划)
5. [5. 约束与守卫](#5-约束与守卫)
6. [6. 风险](#6-风险)
7. [7. 不做的事](#7-不做的事)
8. [8. 验收标准](#8-验收标准)
9. [变更记录](#变更记录)
10. [附录 A：v1.5.1 归档说明](#附录-a：v151-归档说明)

---
# Spec: useMetaList 重构 v2.0

> **版本**: v2.0
> **日期**: 2026-06-06
> **状态**: Phase 1 已完成 / Phase 2 规划中
> **替代**: 本文件替代 v1.5.1（185K/30 章节），全面重写基于代码库实际状态
> **父 spec**: [spec-ui-business-logic-downflow.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) §4 FR-UI-003/004/005

---

## 1. 现状

### 1.1 useMetaList.js 代码结构（2412 行）

| 区域 | 行范围 | 行数 | 占比 | 性质 |
|------|--------|:----:|:----:|------|
| Imports / Constants / Utilities | L1-59 | 57 | 2.4% | 基础设施 |
| Config 解析 | L63-93 | 31 | 1.3% | UI 编排 |
| 响应式状态声明 | L95-311 | 217 | 9.0% | UI 编排 |
| 核心方法 (init/loadList/refresh/handleAction) | L313-808 | 236 | 9.8% | UI 编排 + 少量业务 |
| 过滤/排序/分页 | L541-754 | 63 | 2.6% | UI 编排 |
| 选择方法（跨页选择） | L586-800 | 48 | 2.0% | UI 编排 |
| 导入/导出 | L604-691 | 71 | 2.9% | UI 编排 + 少量业务 |
| **内部辅助方法** | **L856-1758** | **740** | **30.7%** | **业务逻辑为主** |
| Inline Edit | L1769-2175 | 306 | 12.7% | UI 编排 + 少量业务 |
| 关联方法 | L2177-2207 | 29 | 1.2% | 业务逻辑 |
| 生命周期钩子 | L2210-2221 | 11 | 0.5% | UI 编排 |
| Return 语句 | L2223-2358 | 136 | 5.6% | 接口契约 |
| 导出工具函数 | L2361-2412 | 49 | 2.0% | 业务逻辑 |

**关键发现**：内部辅助方法（2i 区域）占 30.7%，且绝大部分是**纯业务逻辑**（零 Vue 依赖），是提取 ROI 最高的区域。

### 1.2 已完成的 Service 下沉

| Service | 文件 | 行数 | 导出 API | 测试用例 | useMetaList 委托方式 |
|---------|------|:----:|---------|:-------:|---------------------|
| keyTemplateService | [keyTemplateService.js](file:///d:/filework/excel-to-diagram/src/services/keyTemplateService.js) | 169 | 4 | 18 | `_suggestKeyTemplateCode` → `suggestKeyTemplateCode()` |
| draftPersistService | [draftPersistService.js](file:///d:/filework/excel-to-diagram/src/services/draftPersistService.js) | 242 | 5 | 17 | `getDraftCreates` / `saveDraftValues` → `getDraftCreates()` / `saveAllDrafts()` |
| filterService | [filterService.js](file:///d:/filework/excel-to-diagram/src/services/filterService.js) | 517 | 11 | 33 | 9 个薄包装函数（`_addFilterParam` → `addFilterParam()` 等） |
| useFieldPolicy | [useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js) | 390 | 14 | 35 | `isCellEditable()` 内调用 `policyIsEditable()` / `isNewRowCheck()` |

**合计**：4 个 service/composable，1318 行代码，103 个测试用例。

### 1.3 消费者全景

```
useMetaList (composable, 2412 行)
    ↓ 唯一调用者
MetaListPage.vue (容器组件, 解构 53 个 API)
    ↓ props 下发
    ├─ InlineEditCell (展示, 仅用 formatDate)
    ├─ InlineEditToolbar (纯展示)
    ├─ AssociationNavigationMenu (纯展示)
    ├─ NavigationSourceInfo (纯展示)
    ├─ TableHeaderFilter (纯展示)
    ├─ ExportDialog (纯展示)
    ├─ ImportDialog (纯展示)
    └─ FkLinkField (纯展示)

MetaListPage.vue 的外部消费者:
    ├─ GenericObjectList.vue (displayMode='page', 路由级统一壳)
    ├─ AuditLogManagement.vue (displayMode='page', 真定制页)
    ├─ AssociationSection.vue (displayMode='embedded', 3 处)
    ├─ ObjectChildSection.vue (默认, useMetaList=true 时)
    ├─ SearchHelpDialog.vue (displayMode='dialog', 值选择)
    ├─ AssignmentDialog.vue (displayMode='dialog', 关联分配)
    └─ MultiObjectManagementPage.vue (默认, 多对象管理)
```

**真实破坏面**：1 个直接消费者（MetaListPage.vue）+ 7 个间接消费者。6 个死代码 stub 已全部删除。

### 1.4 公开 API 清单（85 个）

| 类别 | 数量 | API |
|------|:----:|-----|
| 元数据/配置 | 3 | `metaConfig`, `objectType`, `config` |
| 列表状态 | 10 | `columns`, `visibleColumns`, `data`, `loading`, `selectedRows`, `selectedIds`, `isAllPagesSelected`, `totalSelectedCount`, `currentPageSelectedCount` |
| 导入导出 | 2 | `showExportDialog`, `showImportDialog` |
| 过滤器 | 7 | `filterFields`, `visibleFilterFields`, `filterValues`, `headerFilterValues`, `contextFilters`, `setContextFilters`, `apiFilterConfigs` |
| 搜索 | 2 | `searchFields`, `keyword` |
| 导出 | 1 | `exportFilters` |
| 操作按钮 | 6 | `toolbarActions`, `toolbarRightActions`, `rowActions`, `batchActions`, `exportFields`, `importOptions` |
| 分页排序 | 5 | `pagination`, `paginationConfig`, `sortInfo`, `defaultSort`, `filteredTotalCount` |
| 过滤器显示 | 1 | `filterDisplayModeConfig` |
| 选择配置 | 1 | `selectionConfig` |
| 核心方法 | 16 | `init`, `loadList`, `refresh`, `handleAction`, `handleToolbarAction`, `handleBatchAction`, `handleFilter`, `handleSearch`, `handleSortChange`, `handlePageChange`, `handlePageSizeChange`, `handleSelectionChange`, `handleHeaderFilter`, `resetHeaderFilter`, `resetFilters`, `getRowActions` |
| 批量操作 | 3 | `handleBatchDelete`, `handleBatchExport`, `handleBatchImport` |
| 导入导出成功 | 2 | `handleExportSuccess`, `handleImportSuccess` |
| 跨页选择 | 3 | `selectAllCurrentPage`, `selectAllPages`, `clearAllSelection` |
| Inline Edit 状态 | 6 | `inlineEditConfig`, `inlineEditMode`, `draftValues`, `editingCell`, `hoveredCell`, `hasUnsavedChanges` |
| Inline Edit 方法 | 15 | `enableInlineEdit`, `disableInlineEdit`, `startEditCell`, `finishEditCell`, `updateDraftValue`, `addNewRow`, `cancelInlineEdit`, `saveDraftValues`, `getDraftCreates`, `isCellEditable`, `getFieldEditConfig`, `getCellValue`, `isEditing`, `isHovered`, `setHoveredCell`, `clearHoveredCell` |
| 关联 | 3 | `navigableAssociations`, `getNavigableAssociations`, `batchGetAssociationCounts` |
| **合计** | **85** | |

### 1.5 死代码

| 行范围 | 方法 | 证据 |
|--------|------|------|
| L398-399 | `if (result?.data) {}` 空 if 块 | 条件体为空 |
| L1520-1522 | `_autoGenerateFiltersFromFields()` | 定义但未调用 |
| L1756-1758 | `_getNestedValue()` | 定义但未调用 |

---

## 2. Phase 1 成果总结（已完成）

### 2.1 已达成的目标

| 目标 | 结果 | 状态 |
|------|------|:----:|
| 3 个业务逻辑下沉点 | keyTemplateService + draftPersistService + filterService 已提取 | ✅ |
| 接口契约守卫 | api_contract.spec.js (17 用例) | ✅ |
| 行为不变式守卫 | behavior.spec.js (12 用例) | ✅ |
| displayMode 守卫 | displaymode.spec.js (15 用例) | ✅ |
| 集成测试 | integration.spec.js (20 用例) | ✅ |
| Consumer 契约守卫 | consumer.spec.js (34 用例) | ✅ |
| 公开 API 100% 不变 | 85 个 API 数量+签名不变 | ✅ |
| C2 修复：service 不操作 ref | draftPersistService 接受纯 array | ✅ |

### 2.2 未达成的目标（v1.5.1 已承认）

| 目标 | 原规划 | 实际 | 原因 |
|------|--------|------|------|
| useMetaList.js 行数 ≤ 1500 | 1500 | 2412 | UI 编排代码无法下沉 |
| 6 个新 service | 6 | 2 | 4 个评估为过度规划 |
| 业务逻辑下沉率 85% | 99/116 行 | 73/116 行 (63%) | composable 须保留 loading/refresh/ElMessage |
| service 单测覆盖率 ≥ 90% | 量化 | 103 PASS 但未跑 --coverage | 未执行覆盖率检测 |

### 2.3 经验教训

1. **UI 编排代码不可下沉**：loading/refresh/ElMessage/draftValues.value = new Map() 等 UI 副作用必须留在 composable
2. **service 下沉比例约 63%**：不是 85%，剩余 37% 是胶水代码
3. **过度规划代价高**：4 个"过度规划"的 service（columnTransform/actionTransform/fieldPolicy/filterService 扩展）浪费了 spec 编写时间
4. **接口契约守卫价值极高**：api_contract.spec.js 在后续 PR 中多次防止了 API 变更遗漏

---

## 3. Phase 2 规划：剩余可提取点

### 3.1 提取 ROI 分析

| 优先级 | 目标方法 | 行数 | 提取为 | 理由 |
|:------:|---------|:----:|--------|------|
| **P0** | `_transformMetaToComponentFormat` | 153 | `metaTransformService` | 最大单方法，纯数据转换，零 Vue 依赖 |
| **P1** | `_enrichColumnsWithFieldMeta` | 94 | 合并入 `metaTransformService` | 第二大方法，纯数据回填 |
| **P1** | `_inferColumnWidth` | 84 | 合并入 `metaTransformService` | 纯计算，零依赖 |
| **P2** | `_transformColumns` | 81 | 合并入 `metaTransformService` | 纯数据映射 |
| **P2** | `_addExportFilterParam` | 60 | 合并入 `filterService` | 与 filterService 高度内聚 |
| **P2** | `_transformActions` + `_inferActionPosition` + `_mapVariant` | 72 | 合并入 `metaTransformService` | 操作按钮转换链 |
| **P2** | `getFieldEditConfig` | 45 | `inlineEditConfigService` | typeInferMap + widgetTypeMap 纯映射 |
| **P3** | `handleBatchDelete` | 41 | `batchOperationService` | 含确认对话框 + API 调用 |
| **P3** | `getRowActions` | 34 | 合并入 `metaTransformService` | 行操作权限/条件过滤 |
| **P3** | `_inferColumnPriority` + `_fixDatetimeColumns` + `_getDefaultOrdering` | 44 | 合并入 `metaTransformService` | 小型纯函数 |
| **P3** | `navigableAssociations` computed + `batchGetAssociationCounts` | 26 | `associationService` | 关联导航逻辑 |

**潜在总提取行数**：约 734 行（占函数体 31%）

### 3.2 推荐提取策略：metaTransformService

**核心洞察**：P0-P2 中 6 个方法（`_transformMetaToComponentFormat` / `_enrichColumnsWithFieldMeta` / `_inferColumnWidth` / `_transformColumns` / `_transformActions` / `_inferActionPosition` / `_mapVariant` / `_inferColumnPriority` / `_fixDatetimeColumns` / `_getDefaultOrdering`）都属于**元数据转换链**，可统一提取为 `metaTransformService`。

```
metaTransformService.js（预估 ~450 行）
├── transformMetaToComponentFormat(metaConfig, options)   ← 原 _transformMetaToComponentFormat
│   ├── transformColumns(yamlColumns, filterDisplayMode)  ← 原 _transformColumns
│   ├── transformActions(yamlActions)                     ← 原 _transformActions
│   ├── inferActionPosition(action)                       ← 原 _inferActionPosition
│   ├── mapVariant(variant, position)                     ← 原 _mapVariant
│   ├── inferColumnPriority(col)                          ← 原 _inferColumnPriority
│   ├── fixDatetimeColumns(columns)                       ← 原 _fixDatetimeColumns
│   ├── enrichColumnsWithFieldMeta(columns, fields, metaConfig) ← 原 _enrichColumnsWithFieldMeta
│   └── getDefaultOrdering(metaConfig)                    ← 原 _getDefaultOrdering
├── inferColumnWidth(col)                                 ← 原 _inferColumnWidth
└── getRowActions(rowActions, row, objectType, rowMutability) ← 原 getRowActions
```

**提取后 useMetaList.js 预估行数**：2412 - ~400（提取行） + ~50（委托胶水） ≈ **2060 行**

### 3.3 次要提取：filterService 扩展

将 `_addExportFilterParam`（60 行）合并入已有 `filterService.js`，统一导出过滤参数构建逻辑。

### 3.4 可选提取：inlineEditConfigService

将 `getFieldEditConfig`（45 行）提取为独立 service，包含 typeInferMap + widgetTypeMap 纯映射表。

---

## 4. 实施计划

### 4.1 PR 序列

| PR | 内容 | 提取行 | 新增 service | 工作量 |
|:--:|------|:------:|-------------|:------:|
| **R2-1** | `metaTransformService` 提取 | ~400 | metaTransformService.js (~450 行) | 2d |
| **R2-2** | `filterService` 扩展（`_addExportFilterParam`） | ~60 | filterService.js 扩展 | 0.5d |
| **R2-3** | `inlineEditConfigService` 提取 | ~45 | inlineEditConfigService.js (~60 行) | 0.5d |
| **R2-4** | 死代码清理 + 测试补全 | ~8 | 无 | 0.5d |
| **R2-5** | 覆盖率检测 + 达标 | 0 | 无 | 0.5d |

**总计**：4d，提取 ~513 行，useMetaList.js 降至 ~1900 行。

### 4.2 PR 依赖

```
R2-1 (metaTransformService) ──→ R2-4 (死代码清理)
R2-2 (filterService 扩展)  ──→ R2-4
R2-3 (inlineEditConfig)    ──→ R2-4
R2-4 (清理)                ──→ R2-5 (覆盖率)
```

R2-1 / R2-2 / R2-3 可并行。

### 4.3 每个 PR 的验证流程

1. 新 service 单元测试全通过
2. `useMetaList.api_contract.spec.js` 全通过（85 个 API 不变）
3. `useMetaList.behavior.spec.js` 全通过
4. `useMetaList.integration.spec.js` 全通过
5. `python d:\filework\test.py --failed` 全通过

---

## 5. 约束与守卫

### 5.1 硬约束

| # | 约束 | 验证方式 |
|---|------|---------|
| C1 | 公开 API 85 个数量+签名+行为 100% 不变 | api_contract.spec.js |
| C2 | service 必须纯函数优先，副作用显式标注 | 代码 review |
| C3 | service 不依赖 Vue 响应式（composable 是包装层） | import 检查 |
| C4 | service 单测覆盖率 ≥ 80% | vitest --coverage |
| C5 | 现有 103 个 service 测试不回归 | test.py --failed |

### 5.2 行数目标（现实版）

| 指标 | 当前 | Phase 2 目标 | 说明 |
|------|:----:|:----------:|------|
| useMetaList.js 行数 | 2412 | ~1900 | 不追求 ≤ 1500 |
| 业务逻辑占比 | ~31%（740/2412） | ~15%（~285/1900） | 内部辅助方法区域 |
| service 文件数 | 4 | 6 | +metaTransformService +inlineEditConfigService |
| service 测试用例 | 103 | ~150 | +metaTransform ~40 +inlineEditConfig ~7 |

---

## 6. 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|:----:|:----:|------|
| metaTransformService 提取后 `_transformMetaToComponentFormat` 内部状态依赖 | 中 | 高 | 仔细审计：该方法内引用了 `config`/`columns`/`filterFields` 等 ref，需通过参数传入 |
| 提取后胶水代码过多 | 低 | 中 | 参考已有 3 个 service 的胶水代码比例（~37%），预期可控 |
| `_enrichColumnsWithFieldMeta` 修改 `columns.value` 引用 | 中 | 中 | 该方法直接修改 columns 数组元素属性，提取后需返回新数组 |
| 接口契约测试误报 | 低 | 低 | api_contract.spec.js 已稳定运行 |

---

## 7. 不做的事

| 项 | 理由 |
|----|------|
| useMetaList.js 降到 ≤ 1500 行 | UI 编排代码无法下沉，2412 → 1800 已达成（超出预期） |
| 创建 columnTransformService / actionTransformService / fieldPolicyService | v1.5.1 已评估为过度规划，合并入 metaTransformService |
| 重写 useMetaList 为 reactive utility | 公开 API 变更影响 8 个消费者，风险远大于收益 |
| ValueHelp 弹窗 5 层链路重构 | 功能正常，无 bug 报告，ROI 低 |
| 8 大遗漏补强（9 composable 依赖分析） | 战略性发现但非紧急，可后续独立推进 |

---

## 8. 验收标准

### 8.1 Phase 2 完成条件

- [x] `metaTransformService.js` 文件就位，≥ 10 个导出函数（11 个导出函数，336 行）
- [x] `metaTransformService.spec.js` ≥ 40 个测试用例（59 个测试用例）
- [x] `filterService.js` 扩展 `addExportFilterParam`（+65 行）
- [x] `inlineEditConfigService` 合并入 `metaTransformService`（`inferFieldEditConfig`）
- [x] 死代码清理（3 处：`_autoGenerateFiltersFromFields`、`_getNestedValue`、`_normalizeFilterType`/`_inferFilterType` 未调用包装）
- [x] `useMetaList.api_contract.spec.js` 全通过（85 个 API 不变）
- [x] `useMetaList.behavior.spec.js` 全通过
- [x] `useMetaList.integration.spec.js` 全通过
- [ ] service 单测覆盖率 ≥ 80%（待 `--coverage` 验证）
- [x] useMetaList.js 行数 ≤ 2000（实际 1800 行，-25.4%）

### 8.2 质量门禁

```bash
# 每个 PR 必须通过
npx vitest run src/composables/__tests__/useMetaList.api_contract.spec.js
npx vitest run src/composables/__tests__/useMetaList.behavior.spec.js
npx vitest run src/composables/__tests__/useMetaList.integration.spec.js
npx vitest run src/services/__tests__/metaTransformService.spec.js
python d:\filework\test.py --failed
```

---

## 变更记录

| 版本 | 日期 | 变更内容 |
|:----:|------|---------|
| v2.0.1 | 2026-06-06 | Phase 2 实施：metaTransformService(11函数/336行/59测试) + filterService扩展(addExportFilterParam) + 死代码清理；useMetaList.js 2412→1800行(-25.4%) |
| v2.0 | 2026-06-06 | 全面重写：基于代码库实际状态，删除 v1.5.1 的 15 个分析章节（§15-29），更新行数目标为现实值，重新规划 Phase 2 |
| v1.5.1 | 2026-06-06 | C2 修复 + 6→2 service 调整 + 行数目标调整（已归档） |
| v1.0.0 | 2026-06-06 | 初稿（已归档） |

---

## 附录 A：v1.5.1 归档说明

v1.5.1 spec（185K 字符 / 30 章节 / 3970 行）已归档。本 v2.0 spec 保留了 v1.5.1 的核心设计（§0-14），删除了以下分析章节：

- §15 头部产品对标 + backlog
- §16-18 真实消费侧 + 组件依赖 + v3 衔接
- §19 DetailPage 双向链路
- §20 ValueHelp 弹窗 5 层链路
- §21-25 8 大遗漏审计
- §26-28 spec 整体架构重构
- §29 v1.5.0 完整交付清单

这些章节的分析结论已融入 v2.0 的 §1-3（现状/Phase 1 成果/Phase 2 规划），不再保留原始分析过程。
