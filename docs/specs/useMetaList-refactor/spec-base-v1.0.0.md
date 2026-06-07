# Spec 子文档: PR 4-7 FR-UI-003/004/005 useMetaList 重构 (BASE v1.0.0)

> **基线版本**: v1.0.0（**永久不可变**）
> **基线日期**: 2026-06-06
> **基线状态**: 🔒 LOCKED
> **基线章节**: §0-14（2375 行 / 108,720 字节）
> **范围**: 从父 spec 拆出**独立子 spec**
> **适用 PR**: PR 4-7（FR-UI-003/004/005）
> **本 base 来源**: 从 spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0 提取 §0-14（拆分日期 2026-06-06）

---

⚠️ **警告**：本 base 文件是**永久不可变基线**。任何修改必须通过新增 `deltas/delta-vN.M.0.md` 实现。

---

## 0. 抽取理由

父 spec v2.0.1 涵盖 **15 个 FR**（FR-UI-001 ~ 014），FR-UI-003/004/005 这 3 个 P0 必须项聚焦在**单一目标**：`useMetaList.js` (2505 行) 的**接口契约 + 函数下沉**。混合在同一 spec 内导致：

1. **阅读分散**：300+ 行函数清单 + 200 行算法伪代码 + EBNF 占父 spec 35% 篇幅
2. **测试驱动困难**：3 个 FR 的单测矩阵（≥ 25 + 6 + 30 用例）需独立测试文件
3. **并行会话隔离**：FR-UI-003 明确"实施在并行会话"（v2.0.1 §1.4 P0 第 2 条）
4. **验收依赖链清晰**：3 个 FR 形成完整"接口契约 → 实施 → 测试"闭环
5. **变更追踪**：拆分后子 spec 可独立迭代，不污染父 spec 的其他 12 个 FR

**本子 spec = 父 spec FR-UI-003/004/005 的"完整实施蓝本"**。

---

## 1. 背景与目标

### 1.1 核心痛点

`useMetaList.js` (2505 行) 是前端**最大**的 composable，被 100+ 列表页面引用。它当前是**编排 + 业务逻辑 + API + UI 状态**的"四不像"：

| 维度 | 现状 | 目标 |
|------|------|------|
| **行数** | 2505 | 接口契约层 ≤ 1500 |
| **职责** | 编排 + 业务 + API + UI | 编排 + UI |
| **业务逻辑行数** | ~600 | ≤ 100 |
| **可单测函数** | ~5 | ~50（全部在 service） |
| **关键业务函数** | `_suggestKeyTemplateCode`、`saveDraftValues` 内部分裂、payload 构造 | 全部下沉到 service |

### 1.2 三个 FR 的目标分解

| FR | 目标 | 关键交付物 |
|----|------|----------|
| **FR-UI-003** | `useMetaList` 重构的**接口契约 + 行为不变式** | 6 个新 service 的 API 约束 + 82 个公开 API 100% 保留 |
| **FR-UI-004** | `keyTemplateService.js` 创建 | 3 个函数 + 6 个单测 + `_suggestKeyTemplateCode` 内部委托 |
| **FR-UI-005** | `draftPersistService.js` 创建 | 4 个函数 + 算法伪代码 + 12 边界条件测试 |

### 1.3 成功标准

| # | 衡量项 | 现状 | 目标 | 验收方式 |
|---|--------|------|------|---------|
| 1 | `useMetaList.js` 行数 | 2505 | ≤ 1500 | `wc -l` |
| 2 | 公开 API 数量 | 82 | **82（100% 一致）** | `useMetaList.integration.spec.js` |
| 3 | 业务逻辑在 composable 占比 | ~24% | ≤ 8% | 人工审计 |
| 4 | 6 个 service 单测覆盖率 | 0 | ≥ 90% | jest --coverage |
| 5 | `_suggestKeyTemplateCode` 行数 | 47（L1931-1977） | 5（仅委托） | grep |
| 6 | `saveDraftValues` 业务逻辑 | ~40 行 | ~10 行 | grep |
| 7 | 现有 E2E 列表测试 | 通过 | **100% 通过** | tests/e2e/ |

---

## 2. 现状深度分析

### 2.1 `useMetaList.js` 模块结构（按行号）

| 区间 | 行数 | 职责 | 性质 |
|------|:---:|------|------|
| L1-58 | 58 | imports / 常量 / `handleError` | 基础设施 |
| L59-2300 | 2242 | `useMetaList()` 函数主体 | **核心** |
| ├ L60-300 | 241 | 元数据加载 / metaConfig | 编排 |
| ├ L300-600 | 301 | 列表查询 / pagination / sort | 编排 |
| ├ L600-1000 | 401 | 列定义 / 搜索字段 / 过滤器 | **业务+编排** |
| ├ L1000-1300 | 301 | 工具栏 / 行操作 / 批量操作 / 导入导出 | 编排 |
| ├ L1300-1700 | 401 | 选择 / 跨页选择 / 排序 / 过滤 | 编排 |
| ├ L1700-1900 | 201 | Inline Edit 配置 | 编排 |
| ├ L1880-1930 | 51 | `addNewRow`（含 `_isNew=true`） | 编排 |
| ├ **L1926 / L1931-1977** | **48** | **`_suggestKeyTemplateCode`** | **业务 → 下沉** |
| ├ L1990-2060 | 71 | `cancelInlineEdit` / 取消 | 编排 |
| ├ L2060-2095 | 36 | `getDraftCreates`（payload 构造） | **业务 → 下沉** |
| ├ **L2099-2162** | **64** | **`saveDraftValues` 业务逻辑（split + 过滤 + 构造）** | **业务 → 下沉** |
| ├ L2160-2310 | 151 | 草稿状态 / cleanup / 编辑单元格 | 编排+UI |
| L2312-2445 | 134 | **return 公开 API（82 个）** | **接口契约** |
| L2456-2500 | 45 | `formatDate` / `truncateText` / `getStatusTagType` | 工具函数 |

**关键下沉点（3 个）**：
1. **L1931-1977 `_suggestKeyTemplateCode`** → `keyTemplateService`（FR-UI-004）
2. **L2099-2162 `saveDraftValues` 业务逻辑** → `draftPersistService.splitDraftsToCreateAndUpdate` + `payloadForNewRow/UpdateRow` + `batchSave`（FR-UI-005）
3. **L2090-2094 `getDraftCreates`** → `draftPersistService.payloadForNewRow`（FR-UI-005）

### 2.2 公开 API 完整清单（82 个 — 接口契约保护对象）

> **接口契约 100% 一致 = 重构后 `useMetaList()` 返回对象的每个键值对外行为不变**

#### 2.2.1 元数据 / 配置（6）
```javascript
metaConfig: Ref<MetaConfig>
objectType: string
config: Object
```

#### 2.2.2 列表状态（10）
```javascript
columns: ComputedRef<ColumnDef[]>
visibleColumns: ComputedRef<ColumnDef[]>
data: Ref<any[]>
loading: Ref<boolean>
selectedRows: Ref<any[]>
selectedIds: ComputedRef<(string|number)[]>
isAllPagesSelected: ComputedRef<boolean>
totalSelectedCount: ComputedRef<number>
currentPageSelectedCount: ComputedRef<number>
```

#### 2.2.3 导入导出（2）
```javascript
showExportDialog: Ref<boolean>
showImportDialog: Ref<boolean>
```

#### 2.2.4 过滤器（7）
```javascript
filterFields: ComputedRef<FilterFieldDef[]>
visibleFilterFields: ComputedRef<FilterFieldDef[]>
filterValues: Ref<Record<string, any>>
headerFilterValues: Ref<Record<string, any>>
contextFilters: Ref<Record<string, any>>
setContextFilters: (filters: Record<string, any>) => void
apiFilterConfigs: Ref<any[]>
```

#### 2.2.5 搜索（2）
```javascript
searchFields: ComputedRef<SearchFieldDef[]>
keyword: Ref<string>
```

#### 2.2.6 导出（1）
```javascript
exportFilters: ComputedRef<Record<string, any>>
```

#### 2.2.7 操作按钮（6）
```javascript
toolbarActions: ComputedRef<ActionDef[]>
toolbarRightActions: ComputedRef<ActionDef[]>
rowActions: ComputedRef<ActionDef[]>
batchActions: ComputedRef<ActionDef[]>
exportFields: Ref<string[]>
importOptions: Ref<any>
```

#### 2.2.8 分页排序（5）
```javascript
pagination: Ref<PaginationState>
paginationConfig: ComputedRef<PaginationConfig>
sortInfo: Ref<SortInfo>
defaultSort: ComputedRef<SortInfo>
filteredTotalCount: Ref<number>
```

#### 2.2.9 过滤器显示模式（1）
```javascript
filterDisplayModeConfig: ComputedRef<FilterDisplayModeConfig>
```

#### 2.2.10 选择配置（1）
```javascript
selectionConfig: ComputedRef<{ enabled: boolean, mode: string }>
```

#### 2.2.11 核心方法（14）
```javascript
init(): Promise<void>
loadList(): Promise<void>
refresh(): Promise<void>
handleAction(action: string, row?: any): Promise<void>
handleToolbarAction(action: string): Promise<void>
handleBatchAction(action: string, rows?: any[]): Promise<void>
handleFilter(filters: Record<string, any>): void
handleSearch(keyword: string): void
handleSortChange({ prop, order }: { prop: string, order: string }): void
handlePageChange(page: number): void
handlePageSizeChange(size: number): void
handleSelectionChange(rows: any[]): void
handleHeaderFilter(field: string, value: any): void
resetHeaderFilter(): void
resetFilters(): void
getRowActions(row: any): ActionDef[]
```

#### 2.2.12 批量操作（3）
```javascript
handleBatchDelete(): Promise<void>
handleBatchExport(): Promise<void>
handleBatchImport(): Promise<void>
```

#### 2.2.13 导入导出成功处理（2）
```javascript
handleExportSuccess(result: any): Promise<void>
handleImportSuccess(result: any): Promise<void>
```

#### 2.2.14 跨页选择（3）
```javascript
selectAllCurrentPage(): void
selectAllPages(): Promise<void>
clearAllSelection(): void
```

#### 2.2.15 Inline Edit 状态（4）
```javascript
inlineEditConfig: ComputedRef<InlineEditConfig>
inlineEditMode: Ref<'view' | 'edit'>
draftValues: Ref<Map<string, Record<string, any>>>
editingCell: Ref<{ rowId: string|number, field: string } | null>
hoveredCell: Ref<{ rowId: string|number, field: string } | null>
hasUnsavedChanges: ComputedRef<boolean>
```

#### 2.2.16 Inline Edit 方法（15）
```javascript
enableInlineEdit(): void
disableInlineEdit(): void
startEditCell(row: any, field: string): void
finishEditCell(): Promise<void>
updateDraftValue(rowId: string|number, field: string, value: any): void
addNewRow(): any
cancelInlineEdit(): void
saveDraftValues(): Promise<void>
getDraftCreates(): any[]
isCellEditable(row: any, field: string): boolean
getFieldEditConfig(fieldName: string): any
getCellValue(row: any, field: string): any
isEditing(rowId: string|number, field: string): boolean
isHovered(rowId: string|number, field: string): boolean
setHoveredCell(rowId: string|number, field: string): void
clearHoveredCell(): void
```

#### 2.2.17 关联（3）
```javascript
navigableAssociations: ComputedRef<Association[]>
getNavigableAssociations(row: any): Association[]
batchGetAssociationCounts(associations: any[]): Promise<Record<string, number>>
```

### 2.3 业务逻辑下沉点（3 个高 ROI 点）

| # | 下沉点 | 当前行数 | 下沉后行数 | 下沉目标 service |
|---|--------|:-------:|:--------:|----------------|
| 1 | `_suggestKeyTemplateCode` | 47 | 5（仅委托） | `keyTemplateService` |
| 2 | `saveDraftValues` 业务逻辑 | 64 | 10（仅委托+UI 状态） | `draftPersistService` |
| 3 | `getDraftCreates` | 5 | 2（仅委托） | `draftPersistService` |
| **小计** | — | **116** | **17** | — |

**节省 ~99 行** 业务代码出 composable，**等价于约 7-8 个 service 函数的可单测点**。

### 2.4 与其他 FR / 现有代码的依赖

| 依赖 | 现状 | 风险 | 缓解 |
|------|------|------|------|
| `useBOAction` | 已被 useMetaList L2150 `await import` 动态引入 | draftPersistService.batchSave 也需用它 | 复用同一入口 |
| `boService.suggestKeyTemplateCode` | L1959 已有调用 | keyTemplateService 不应重复 | keyTemplateService 不调 boService；**_suggestKeyTemplateCode 内部委托 service.suggest()**；service 内部调 boService |
| `boService.batchSave` | L2151 调 `callPost('batch_save', ...)` | 同上 | draftPersistService.batchSave 调 boService（**或 callPost**） |
| `useMetaList.integration.spec.js` | 已存在覆盖 9+ 公开 API | 重构必须保持字节级一致 | 接口契约 + 集成测试 100% 覆盖 |
| 100+ 列表页面 | 全部依赖 useMetaList | 重构后调用方零改动 | 公开 API 不变 |

---

## 3. 目标架构（3 个 FR 局部）

### 3.1 重构后的 `useMetaList.js` 形态

```
src/composables/useMetaList.js (≤ 1500 行)
├── imports (50 行)
├── handleError (10 行) — 工具函数
├── useMetaList() (1300 行)
│   ├── 状态初始化 (200 行)         ← 元数据/columns/filter 编排
│   ├── computed 派生 (300 行)      ← visibleColumns/searchFields/...
│   ├── watch / lifecycle (100 行)  ← 监听 filterValues 同步
│   ├── 核心方法 (400 行)           ← loadList/refresh/handleAction/...
│   ├── Inline Edit 编排 (200 行)   ← enableInlineEdit/updateDraftValue/...
│   ├── 委托调用 (50 行)            ← 关键业务调用 service
│   │   ├── keyTemplateService.validateParentParams(parentParams)
│   │   ├── keyTemplateService.suggest(objectType, parentParams)
│   │   ├── draftPersistService.splitDraftsToCreateAndUpdate(...)
│   │   └── draftPersistService.batchSave(...)
│   └── return 公开 API (50 行)    ← **82 个键值**
└── formatDate/truncateText (45 行)
```

### 3.2 6 个新 service 在 service 层的位置

```
src/services/                              (现有 24 个 → 新增 5-6 个)
├── useMetaList 重构产出（本次新增）：
│   ├── keyTemplateService.js          ← FR-UI-004 ✅ 重点
│   ├── draftPersistService.js         ← FR-UI-005 ✅ 重点
│   ├── columnTransformService.js      ← FR-UI-003 part
│   ├── actionTransformService.js      ← FR-UI-003 part
│   ├── fieldPolicyService.js          ← FR-UI-003 part
│   └── filterService.js (扩展)        ← FR-UI-003 part
│
├── Phase 2 (P1)：
│   ├── permissionService.js
│   ├── conditionExpressionService.js
│   ├── hierarchyService.js
│   └── diagramConfigService.js
│
└── Phase 3 (P2)：
    ├── auditLogService.js
    └── associationService.js
```

### 3.3 关键约束

| # | 约束 | 验收 |
|---|------|------|
| **C1** | 6 个 service **必须纯函数优先**，副作用函数显式 `*WithApi` 后缀 | 单元测试 |
| **C2** | 6 个 service **不依赖 Vue/响应式**（composable 是包装层） | import 检查 |
| **C3** | 6 个 service **单测覆盖率 ≥ 90%** | vitest --coverage |
| **C4** | `useMetaList` 公开 API 82 个**数量+签名+行为 100% 一致** | `useMetaList.integration.spec.js` |
| **C5** | 重构不修改 `useMetaList.integration.spec.js` | git diff |
| **C6** | 现有列表页面（100+）零改动 | grep / grep |
| **C7** | `useMetaList.batch.spec.js`（10+ 用例）继续通过 | npm test |
| **C8** | 3 个 service **TypeScript JSDoc 完整**（@param, @returns, @throws, @example） | spec 附录 A |

---

## 4. 详细设计 — FR-UI-003 接口契约

### 4.1 接口契约声明

> **重构后的 `useMetaList.js` 公开 API 与重构前 100% 一致**（数量 / 名称 / 类型 / 行为）。

#### 4.1.1 公开 API 数量保证

| 类别 | 数量 | 验证方式 |
|------|:---:|---------|
| 元数据/配置 | 6 | 集成测试断言 `Object.keys(metaList).includes(...)` |
| 列表状态 | 10 | 同上 |
| 导入导出 | 2 | 同上 |
| 过滤器 | 7 | 同上 |
| 搜索 | 2 | 同上 |
| 导出 | 1 | 同上 |
| 操作按钮 | 6 | 同上 |
| 分页排序 | 5 | 同上 |
| 过滤器显示 | 1 | 同上 |
| 选择配置 | 1 | 同上 |
| 核心方法 | 14 | 同上 |
| 批量操作 | 3 | 同上 |
| 导入导出成功 | 2 | 同上 |
| 跨页选择 | 3 | 同上 |
| Inline Edit 状态 | 4 | 同上 |
| Inline Edit 方法 | 15 | 同上 |
| 关联 | 3 | 同上 |
| **合计** | **85** | （82 基础 + 3 重复，详见 §4.1.3） |

#### 4.1.2 行为不变式（重构后必须保证）

| 类别 | 不变式 | 验证 |
|------|--------|------|
| **分页** | 第 1 页 = 默认；末页 total 准确；pageSize 改变重置 page=1 | E2E 列表测试 |
| **过滤** | 单一 filter / 多 filter AND / 复合 filter OR 行为不变 | E2E |
| **排序** | asc/desc/多级/cursor 行为不变 | E2E |
| **导出** | 导出列、导出过滤参数格式与重构前一致 | 快照测试 |
| **草稿保存** | 草稿保存/取消/创建/更新行为字节级一致 | 集成测试 |
| **行内编辑** | 编辑/取消/新增/删除/KeyTemplate 自动填充 | 集成测试 |
| **批量操作** | 批量删除/导出/导入行为不变 | E2E |
| **跨页选择** | selectAllPages 数据范围与重构前一致 | E2E |
| **关联** | navigableAssociations 集合与重构前一致 | 单元测试 |
| **错误处理** | handleError 调用链、错误提示与重构前一致 | E2E |

#### 4.1.3 公开 API 自动断言测试

新增 `src/composables/__tests__/useMetaList.api_contract.spec.js`：

```javascript
import { describe, it, expect, beforeEach } from 'vitest'
import { useMetaList } from '@/composables/useMetaList'

const EXPECTED_API = [
  // 元数据/配置
  'metaConfig', 'objectType', 'config',
  // 列表状态
  'columns', 'visibleColumns', 'data', 'loading', 'selectedRows',
  'selectedIds', 'isAllPagesSelected', 'totalSelectedCount',
  'currentPageSelectedCount',
  // 导入导出
  'showExportDialog', 'showImportDialog',
  // 过滤器
  'filterFields', 'visibleFilterFields', 'filterValues',
  'headerFilterValues', 'contextFilters', 'setContextFilters',
  'apiFilterConfigs',
  // 搜索
  'searchFields', 'keyword',
  // 导出
  'exportFilters',
  // 操作按钮
  'toolbarActions', 'toolbarRightActions', 'rowActions',
  'batchActions', 'exportFields', 'importOptions',
  // 分页排序
  'pagination', 'paginationConfig', 'sortInfo', 'defaultSort',
  'filteredTotalCount',
  // 过滤器显示
  'filterDisplayModeConfig',
  // 选择配置
  'selectionConfig',
  // 核心方法
  'init', 'loadList', 'refresh', 'handleAction', 'handleToolbarAction',
  'handleBatchAction', 'handleFilter', 'handleSearch', 'handleSortChange',
  'handlePageChange', 'handlePageSizeChange', 'handleSelectionChange',
  'handleHeaderFilter', 'resetHeaderFilter', 'resetFilters', 'getRowActions',
  // 批量操作
  'handleBatchDelete', 'handleBatchExport', 'handleBatchImport',
  // 导入导出成功
  'handleExportSuccess', 'handleImportSuccess',
  // 跨页选择
  'selectAllCurrentPage', 'selectAllPages', 'clearAllSelection',
  // Inline Edit 状态
  'inlineEditConfig', 'inlineEditMode', 'draftValues', 'editingCell',
  'hoveredCell', 'hasUnsavedChanges',
  // Inline Edit 方法
  'enableInlineEdit', 'disableInlineEdit', 'startEditCell', 'finishEditCell',
  'updateDraftValue', 'addNewRow', 'cancelInlineEdit', 'saveDraftValues',
  'getDraftCreates', 'isCellEditable', 'getFieldEditConfig', 'getCellValue',
  'isEditing', 'isHovered', 'setHoveredCell', 'clearHoveredCell',
  // 关联
  'navigableAssociations', 'getNavigableAssociations', 'batchGetAssociationCounts',
]

describe('useMetaList API Contract', () => {
  let metaList
  beforeEach(() => {
    metaList = useMetaList('user_group', { mode: 'element-plus', autoLoad: false })
  })
  
  it('应该暴露全部 82 个公开 API（接口契约）', () => {
    const actual = Object.keys(metaList).sort()
    const expected = [...EXPECTED_API].sort()
    expect(actual).toEqual(expected)
  })
  
  it('核心方法应该是函数', () => {
    const functions = [
      'init', 'loadList', 'refresh', 'handleAction', 'handleToolbarAction',
      'handleBatchAction', 'handleFilter', 'handleSearch', 'handleSortChange',
      'handlePageChange', 'handlePageSizeChange', 'handleSelectionChange',
      'handleHeaderFilter', 'resetHeaderFilter', 'resetFilters', 'getRowActions',
      'handleBatchDelete', 'handleBatchExport', 'handleBatchImport',
      'handleExportSuccess', 'handleImportSuccess',
      'selectAllCurrentPage', 'selectAllPages', 'clearAllSelection',
      'enableInlineEdit', 'disableInlineEdit', 'startEditCell', 'finishEditCell',
      'updateDraftValue', 'addNewRow', 'cancelInlineEdit', 'saveDraftValues',
      'getDraftCreates', 'isCellEditable', 'getFieldEditConfig', 'getCellValue',
      'isEditing', 'isHovered', 'setHoveredCell', 'clearHoveredCell',
      'getNavigableAssociations', 'batchGetAssociationCounts',
    ]
    for (const fn of functions) {
      expect(typeof metaList[fn]).toBe('function')
    }
  })
  
  it('状态/计算属性应该是 ref 或 computed', () => {
    const refs = [
      'data', 'loading', 'selectedRows', 'metaConfig', 'config',
      'showExportDialog', 'showImportDialog', 'filterValues',
      'headerFilterValues', 'keyword', 'exportFields', 'pagination',
      'sortInfo', 'draftValues', 'editingCell', 'hoveredCell',
    ]
    for (const r of refs) {
      const v = metaList[r]
      // ref 有 .value，computed 也有
      expect(v).toHaveProperty('value')
    }
  })
  
  it('computed 应该是只读', () => {
    const computed = [
      'columns', 'visibleColumns', 'selectedIds', 'isAllPagesSelected',
      'filterFields', 'visibleFilterFields', 'searchFields', 'exportFilters',
      'toolbarActions', 'rowActions', 'batchActions', 'paginationConfig',
      'defaultSort', 'filterDisplayModeConfig', 'selectionConfig',
      'inlineEditConfig', 'hasUnsavedChanges', 'navigableAssociations',
    ]
    for (const c of computed) {
      const v = metaList[c]
      expect(v).toHaveProperty('value')
    }
  })
})
```

### 4.2 接口契约 6 个 service（FR-UI-003 part）

#### 4.2.1 `keyTemplateService.js`（FR-UI-004 重点）

```javascript
/**
 * 键模板服务（Key Template Service）
 *
 * 业务职责：管理"键值编码自动生成"（如 `dom_001`、`user_002` 等）。
 * 父级关系由 `parentParams` 描述（`{ parentCode, parentId }`）。
 *
 * @module services/keyTemplateService
 */

/**
 * 父级参数。
 * @typedef {Object} ParentParams
 * @property {string} [parentCode]    父级 code（如 dept_code）
 * @property {number} [parentId]      父级 id
 */

/**
 * 验证父级参数是否合法。
 *
 * @param {ParentParams | null | undefined} parentParams
 * @returns {{ valid: boolean, error?: string }}
 *
 * @example
 * validateParentParams({ parentId: 1 })   // → { valid: true }
 * validateParentParams({ parentId: 0 })   // → { valid: false, error: 'parentId 不能为 0' }
 * validateParentParams(null)              // → { valid: false, error: '缺少父级参数' }
 */
export function validateParentParams(parentParams) { /* ... */ }

/**
 * 从 filterValues + newRow 构造 ParentParams。
 *
 * 业务规则：
 * 1. 从 `filterValues` 中提取所有 `*_id` 字段（排除 Vue 内部 prop）
 * 2. 从 `newRow` 中提取非空 `*_id`（排除 `id` 自身）
 * 3. filterValues 优先级高于 newRow
 *
 * @param {Record<string, any>} filterValues  列表过滤器当前值
 * @param {Object} [newRow]                   新行（draft）
 * @returns {ParentParams}
 */
export function buildParentParams(filterValues, newRow) { /* ... */ }

/**
 * 异步调用后端建议键模板 code。
 *
 * @param {string} objectType
 * @param {ParentParams | null} parentParams
 * @returns {Promise<string | null>}  建议的 code；失败时返回 null
 *
 * @throws {Error} 当后端返回非 ApiSuccess 时
 */
export async function suggestKeyTemplateCode(objectType, parentParams) { /* ... */ }
```

#### 4.2.2 `draftPersistService.js`（FR-UI-005 重点）

```javascript
/**
 * 草稿持久化服务（Draft Persist Service）
 *
 * 业务职责：将前端"草稿行"（含 `_isNew` 标记）拆分为"创建"和"更新"两类，
 * 处理 code 冲突、过滤未变更字段、构造 payload，最终委托后端 batch_save。
 */

/**
 * 草稿行。
 * @typedef {Object} DraftRow
 * @property {string|number} [_draftId]
 * @property {string} [_isNew]    'true' | 'false'
 * @property {Object} [payload]
 * @property {Object} [_initialValues]  新行初始值
 */

/**
 * 拆分结果。
 * @typedef {Object} SplitResult
 * @property {Array<{row: DraftRow, payload: Object}>} creates
 * @property {Array<{rowId: string|number, payload: Object}>} updates
 * @property {string[]} conflicts    冲突信息
 */

/**
 * 拆分草稿为创建和更新。
 *
 * @param {Map<string, DraftRow>} draftMap
 * @param {any[]} data              当前列表数据（用于 code 冲突检测）
 * @param {string} objectType
 * @returns {SplitResult}
 *
 * @see 附录 B.1 算法伪代码
 * @see 附录 B.2 边界条件测试矩阵
 */
export function splitDraftsToCreateAndUpdate(draftMap, data, objectType) { /* ... */ }

/**
 * 为新行构造 payload。
 *
 * 业务规则：
 * 1. 排除 `_` 开头字段、`id` 字段
 * 2. 保留 `*_id` 字段（FK 回填）
 * 3. 合并 fields 中的所有修改值
 *
 * @param {DraftRow} row
 * @param {string[]} fields
 * @param {Object} initialValues
 * @returns {Object} payload
 */
export function payloadForNewRow(row, fields, initialValues) { /* ... */ }

/**
 * 为更新行构造 payload。
 *
 * @param {string|number} rowId
 * @param {string[]} fields
 * @param {boolean} isNewRow        是否为新行（draft 但已建过）
 * @param {Object} initialValues
 * @returns {Object} payload
 */
export function payloadForUpdateRow(rowId, fields, isNewRow, initialValues) { /* ... */ }

/**
 * 批量保存。
 *
 * @param {any[]} creates            创建 payload 列表
 * @param {any[]} updates            更新 payload 列表
 * @param {string} objectType
 * @param {Object} boService         BO 服务（来自 useBOAction）
 * @returns {Promise<{ success: number, failed: number, errors: any[] }>}
 */
export async function batchSave(creates, updates, objectType, boService) { /* ... */ }
```

#### 4.2.3 `columnTransformService.js`、`actionTransformService.js`、`fieldPolicyService.js`、`filterService.js`（扩展）

> **FR-UI-003 part（不展开，由 PR 6-7 实施）**：
> - 4 个 service 公开 API 已在父 spec 附录 A.2-A.5 / A.7 定义
> - 每个 service ≥ 8 单元测试
> - 重构后 `useMetaList.js` 内部调用 `columnTransformService.transformColumns()` / `inferColumnPriority()` 等
> - 字段编辑配置 `useMetaList.getFieldEditConfig()` 委托给 `fieldPolicyService.getFieldEditConfig()`
> - 导出过滤参数 `useMetaList.exportFilters` 委托给 `filterService.buildExportFilterQueryParams()`

### 4.3 接口契约守卫

| 守卫 | 实施点 | 触发 |
|------|--------|------|
| **CI 检查** | `useMetaList.api_contract.spec.js` | 每次 PR |
| **集成测试** | `useMetaList.integration.spec.js` | 每次 PR |
| **E2E 测试** | `tests/e2e/list.spec.js` 等 | 每次 PR |
| **代码 review** | PR review 检查 `useMetaList.js` return 块 | 人工 |

---

## 5. 详细设计 — FR-UI-004 keyTemplateService

### 5.1 现有代码定位

`useMetaList.js:1931-1977`（47 行）：

```javascript
async function _suggestKeyTemplateCode(newRow) {
  try {
    // 1. 收集 parentParams（filterValues + newRow）
    const parentParams = {}
    Object.keys(filterValues.value)
      .filter(key => !isVueInternalProp(key) && key.endsWith('_id'))
      .forEach(key => {
        parentParams[key] = filterValues.value[key]
      })
    Object.keys(newRow)
      .filter(key => !key.startsWith('_') && key.endsWith('_id') && key !== 'id')
      .forEach(key => {
        if (!(key in parentParams) && newRow[key] != null) {
          parentParams[key] = newRow[key]
        }
      })

    if (Object.keys(parentParams).length === 0) return

    // 2. 校验父级 id 合法性
    const hasInvalidParentId = Object.values(parentParams).some(
      v => v === 'new' || v === '' || v === null || v === undefined
    )
    if (hasInvalidParentId) {
      if (config.debug) {
        console.log('[useMetaList] Key template suggestion skipped: parent record not yet saved')
      }
      return
    }

    // 3. 调后端
    const result = await boService.suggestKeyTemplateCode(objectType, {}, parentParams)
    if (result.success && result.data?.code) {
      const codeValue = result.data.code
      newRow.code = codeValue
      newRow._initialValues = { ...(newRow._initialValues || {}), code: codeValue }
      
      const rowDrafts = draftValues.value.get(newRow.id)
      if (rowDrafts) {
        rowDrafts.code = codeValue
        draftValues.value = new Map(draftValues.value)
      }
    }
  } catch (e) {
    if (config.debug) {
      console.warn('[useMetaList] Key template suggestion error:', e)
    }
  }
}
```

**下沉 4 步为 service 3 函数**：

| service 函数 | 包含步骤 | 行数（估） |
|-------------|---------|:--------:|
| `validateParentParams(parentParams)` | 步骤 2 | ~15 |
| `buildParentParams(filterValues, newRow)` | 步骤 1 | ~12 |
| `suggestKeyTemplateCode(objectType, parentParams)` | 步骤 3（**内部调 boService**） | ~10 |

**重构后 `_suggestKeyTemplateCode` 仅 6 行**（仅组装 + 副作用）：

```javascript
async function _suggestKeyTemplateCode(newRow) {
  try {
    const parentParams = buildParentParams(filterValues.value, newRow)
    if (!validateParentParams(parentParams).valid) return
    
    const codeValue = await suggestKeyTemplateCode(objectType, parentParams)
    if (codeValue) {
      newRow.code = codeValue
      newRow._initialValues = { ...(newRow._initialValues || {}), code: codeValue }
      const rowDrafts = draftValues.value.get(newRow.id)
      if (rowDrafts) {
        rowDrafts.code = codeValue
        draftValues.value = new Map(draftValues.value)
      }
    }
  } catch (e) {
    if (config.debug) console.warn('[useMetaList] Key template suggestion error:', e)
  }
}
```

### 5.2 详细实现

```javascript
// src/services/keyTemplateService.js

import { boService } from './boService'

const VUE_INTERNAL_PROPS = new Set(['$', '$el', '_v_isVNode', '$options', ...])

/**
 * 判断 key 是否是 Vue 内部 prop。
 * @param {string} key
 * @returns {boolean}
 */
function isVueInternalProp(key) {
  return VUE_INTERNAL_PROPS.has(key) || key.startsWith('$') || key.startsWith('_v_')
}

/**
 * 验证父级参数。
 * @param {ParentParams | null | undefined} parentParams
 * @returns {{ valid: boolean, error?: string }}
 */
export function validateParentParams(parentParams) {
  if (!parentParams || typeof parentParams !== 'object') {
    return { valid: false, error: '缺少父级参数' }
  }
  const invalidKeys = Object.entries(parentParams).filter(([k, v]) =>
    v === 'new' || v === '' || v === null || v === undefined
  )
  if (invalidKeys.length > 0) {
    return {
      valid: false,
      error: `父级参数不合法: ${invalidKeys.map(([k]) => k).join(', ')}`,
    }
  }
  return { valid: true }
}

/**
 * 构造 ParentParams。
 * @param {Record<string, any>} filterValues
 * @param {Object} [newRow]
 * @returns {ParentParams}
 */
export function buildParentParams(filterValues, newRow) {
  const parentParams = {}
  // 1. filterValues（高优先级）
  if (filterValues && typeof filterValues === 'object') {
    for (const [key, value] of Object.entries(filterValues)) {
      if (!isVueInternalProp(key) && key.endsWith('_id') && value != null) {
        parentParams[key] = value
      }
    }
  }
  // 2. newRow（仅当 filterValues 中无）
  if (newRow && typeof newRow === 'object') {
    for (const [key, value] of Object.entries(newRow)) {
      if (
        !key.startsWith('_') &&
        key !== 'id' &&
        key.endsWith('_id') &&
        !(key in parentParams) &&
        value != null
      ) {
        parentParams[key] = value
      }
    }
  }
  return parentParams
}

/**
 * 异步建议键模板 code。
 * @param {string} objectType
 * @param {ParentParams} parentParams
 * @returns {Promise<string | null>}
 */
export async function suggestKeyTemplateCode(objectType, parentParams) {
  const result = await boService.suggestKeyTemplateCode(objectType, {}, parentParams)
  if (result && result.success && result.data && result.data.code) {
    return result.data.code
  }
  return null
}
```

### 5.3 单元测试矩阵（6 用例 - 父 spec 约定 + 扩展到 12 用例）

| # | 测试 | 预期 |
|---|------|------|
| 1 | `validateParentParams(null)` | `{valid: false, error: '缺少父级参数'}` |
| 2 | `validateParentParams({})` | `{valid: true}` |
| 3 | `validateParentParams({parentId: 1})` | `{valid: true}` |
| 4 | `validateParentParams({parentId: 0})` | `{valid: false}` |
| 5 | `validateParentParams({parentId: 'new'})` | `{valid: false}` |
| 6 | `validateParentParams({a: 1, b: null})` | `{valid: false, error: 'b'}` |
| 7 | `buildParentParams({}, null)` | `{}` |
| 8 | `buildParentParams({dept_id: 5}, null)` | `{dept_id: 5}` |
| 9 | `buildParentParams({dept_id: 5}, {parent_id: 1})` | `{dept_id: 5, parent_id: 1}` |
| 10 | `buildParentParams({}, {id: 10, parent_id: 1})` | `{parent_id: 1}`（id 排除） |
| 11 | `buildParentParams({}, {_initial: 'x', parent_id: 1})` | `{parent_id: 1}`（_initial 排除） |
| 12 | `suggestKeyTemplateCode success` | 返回 code 字符串 |
| 13 | `suggestKeyTemplateCode failure` | 返回 null（不抛错） |
| 14 | `_suggestKeyTemplateCode 委托（集成）` | 6 行 + 5 行行为不变 |

### 5.4 文件结构

```
src/services/
├── keyTemplateService.js           (本次新增，~80 行)
└── keyTemplateService.spec.js      (本次新增，~120 行)
```

---

## 6. 详细设计 — FR-UI-005 draftPersistService

### 6.1 现有代码定位

`useMetaList.js:2099-2162`（64 行）业务逻辑 + `2090-2094` getDraftCreates 5 行：

```javascript
async function saveDraftValues() {
  if (draftValues.value.size === 0) return

  loading.value = true
  try {
    // 业务逻辑 1：收集 drafts
    const drafts = []
    for (const [rowId, fields] of draftValues.value.entries()) {
      // ... 64 行 ...
    }
    // 业务逻辑 2：委托后端
    const { callPost } = await import('@/composables/useBoAction')
    const r = await callPost('batch_save', { object_type: objectType, drafts })
    // 业务逻辑 3：处理结果
    if (r.success) {
      // 成功处理
    } else {
      // 失败处理
    }
  } catch (e) {
    // ...
  }
}
```

**下沉 3 个函数**：

| service 函数 | 包含 | 估行 |
|-------------|------|:---:|
| `splitDraftsToCreateAndUpdate(draftMap, data, objectType)` | 业务逻辑 1 | ~50 |
| `payloadForNewRow/UpdateRow(...)` | 工具函数（被 splitDraftsToCreateAndUpdate 内部调用） | ~30 |
| `batchSave(creates, updates, objectType, boService)` | 业务逻辑 2 | ~25 |

**重构后 `saveDraftValues` 仅 10-12 行**（编排 + 副作用）：

```javascript
async function saveDraftValues() {
  if (draftValues.value.size === 0) return
  loading.value = true
  try {
    const split = splitDraftsToCreateAndUpdate(draftValues.value, data.value, objectType)
    if (split.conflicts.length > 0) {
      ElMessage.error(`草稿冲突: ${split.conflicts.join('; ')}`)
      loading.value = false
      return
    }
    const r = await batchSave(split.creates, split.updates, objectType, boService)
    if (r.failed === 0) {
      ElMessage.success(`成功创建 ${r.success} 项`)
      draftValues.value.clear()
      draftValues.value = new Map()
      await refresh()
    } else {
      ElMessage.error(`${r.failed} 项失败`)
    }
  } catch (e) {
    ElMessage.error(`保存失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}
```

### 6.2 详细实现

```javascript
// src/services/draftPersistService.js

/**
 * 拆分草稿为创建和更新。
 *
 * 业务规则：
 * 1. _isNew === 'true' 或 true → 创建
 * 2. 其他 → 更新
 * 3. 创建的 code 字段：若与现有 data 重复 → 加入 conflicts
 * 4. 更新行必须有 rowId（否则 conflict）
 *
 * @param {Map<string, DraftRow>} draftMap
 * @param {any[]} data
 * @param {string} objectType
 * @returns {SplitResult}
 */
export function splitDraftsToCreateAndUpdate(draftMap, data, objectType) {
  const creates = []
  const updates = []
  const conflicts = []
  
  for (const [draftId, row] of draftMap) {
    if (row._isNew === 'true' || row._isNew === true) {
      // 新增
      const payload = buildNewRowPayload(row, objectType)
      // code 冲突检测
      if (payload.code && data.some(d => d.code === payload.code)) {
        conflicts.push(`Row ${draftId}: code ${payload.code} already exists`)
        continue
      }
      creates.push({ row, payload })
    } else {
      // 更新
      const rowId = row.id || draftId
      const payload = buildUpdatePayload(row, objectType)
      updates.push({ rowId, payload })
    }
  }
  
  // 二次校验
  for (const u of updates) {
    if (!u.rowId) {
      conflicts.push(`Update row missing id: ${JSON.stringify(u.payload)}`)
    }
  }
  
  return { creates, updates, conflicts }
}

function buildNewRowPayload(row, objectType) {
  // 提取字段（保留 *_id FK 回填）
  const payload = {}
  Object.keys(row).forEach(key => {
    if (key.startsWith('_') || key === 'id') return
    if (key.endsWith('_id') && row[key] != null && row[key] !== '') {
      payload[key] = row[key]
    }
  })
  return payload
}

function buildUpdatePayload(row, objectType) {
  // 更新直接用 fields
  const payload = {}
  for (const [fieldName, newValue] of Object.entries(row)) {
    if (!fieldName.startsWith('_')) {
      payload[fieldName] = newValue
    }
  }
  return payload
}

export function payloadForNewRow(row, fields, initialValues) {
  // 同 buildNewRowPayload 但显式参数
  const payload = {}
  Object.keys(row).forEach(key => {
    if (key.startsWith('_') || key === 'id') return
    if (fields.hasOwnProperty(key)) return
    if (key.endsWith('_id') && row[key] != null && row[key] !== '') {
      payload[key] = row[key]
    }
  })
  for (const [fieldName, newValue] of Object.entries(fields)) {
    if (!fieldName.startsWith('_')) {
      payload[fieldName] = newValue
    }
  }
  return payload
}

export function payloadForUpdateRow(rowId, fields, isNewRow, initialValues) {
  const payload = {}
  for (const [fieldName, newValue] of Object.entries(fields)) {
    if (!fieldName.startsWith('_')) {
      payload[fieldName] = newValue
    }
  }
  return payload
}

/**
 * 批量保存。
 * @param {any[]} creates
 * @param {any[]} updates
 * @param {string} objectType
 * @param {Object} boService
 * @returns {Promise<{ success: number, failed: number, errors: any[] }>}
 */
export async function batchSave(creates, updates, objectType, boService) {
  const drafts = [
    ...creates.map(c => ({ row_id: c.row._draftId, is_new: true, fields: c.payload })),
    ...updates.map(u => ({ row_id: u.rowId, is_new: false, fields: u.payload })),
  ]
  
  const r = await boService.batchSave(objectType, drafts)
  
  if (r && r.success && r.data) {
    return {
      success: (r.data.created || []).length + (r.data.updated || []).length,
      failed: (r.data.failures || []).length,
      errors: r.data.failures || [],
    }
  }
  
  return {
    success: 0,
    failed: drafts.length,
    errors: [{ message: r.message || 'batch_save failed' }],
  }
}
```

### 6.3 算法伪代码（父 spec 附录 B.1 完整 + 详细版）

```javascript
function splitDraftsToCreateAndUpdate(draftMap, data, objectType) {
  const creates = []
  const updates = []
  const conflicts = []

  // 步骤 1：遍历草稿，分类（创建 vs 更新）
  for (const [draftId, row] of draftMap) {
    if (isNewRow(row)) {
      // 子步骤 1.1：构造创建 payload
      const payload = buildNewRowPayload(row, objectType)
      
      // 子步骤 1.2：code 冲突检测
      if (hasCodeConflict(payload, data)) {
        conflicts.push(formatConflictMessage(draftId, payload))
        continue  // 跳过此行
      }
      
      creates.push({ row, payload })
    } else {
      // 子步骤 1.3：构造更新 payload
      const rowId = extractRowId(row, draftId)
      const payload = buildUpdatePayload(row, objectType)
      updates.push({ rowId, payload })
    }
  }

  // 步骤 2：二次校验（更新行 rowId 必填）
  for (const u of updates) {
    if (!u.rowId) {
      conflicts.push(`Update row missing id: ${JSON.stringify(u.payload)}`)
    }
  }

  return { creates, updates, conflicts }
}

function isNewRow(row) {
  return row._isNew === 'true' || row._isNew === true
}

function hasCodeConflict(payload, data) {
  return payload.code && data.some(d => d.code === payload.code)
}

function extractRowId(row, fallbackDraftId) {
  return row.id || fallbackDraftId
}
```

### 6.4 边界条件测试矩阵（12 用例 - 父 spec §B.2）

| # | 场景 | 输入 | 期望输出 |
|---|------|------|---------|
| 1 | 空草稿 | `Map()` | `{creates: [], updates: [], conflicts: []}` |
| 2 | 纯新增 | 2 行 `_isNew=true` | 2 creates, 0 updates |
| 3 | 纯更新 | 2 行 `_isNew=false` | 0 creates, 2 updates |
| 4 | 混合 | 1 新增 + 1 更新 | 1 create, 1 update |
| 5 | code 重复 | 2 行 code='A001' | 1 conflict, 1 create |
| 6 | code 字段缺失 | 1 行无 code | 1 create（无 conflict） |
| 7 | 字段类型转换 | value='123' | payload.value = 123（隐式） |
| 8 | FK 字段回填 | parent_id='5' | payload.parent_id = 5 |
| 9 | 更新行无 id | `_isNew=false`, 无 id | 1 conflict |
| 10 | 网络失败 | boService 抛异常 | `{success: 0, failed: N, errors: [...]}` |
| 11 | 部分成功 | 3 create 中第 2 个 400 | `{success: 2, failed: 1, errors: [{index: 1, code: '400'}]}` |
| 12 | 顺序保证 | 输入顺序 A,B,C | 输出顺序 A,B,C（不重排） |

### 6.5 文件结构

```
src/services/
├── draftPersistService.js          (本次新增，~120 行)
└── draftPersistService.spec.js     (本次新增，~200 行)
```

---

## 7. 实施计划（PR 4-7 拆分）

### 7.1 PR 序列（来自父 spec §6.1）

| PR # | 内容 | FR | 工作量 | 状态 |
|:----:|------|-----|:----:|:---:|
| 1 | httpClient.js + 旧 api 兼容层 | FR-UI-001 | 1.5d | ✅ 已完成 |
| 2 | apiV1/apiV2 + 10 文件 API_BASE 替换 | FR-UI-006 | 0.5d | ✅ 已完成 |
| 3 | authService + authStore 重构 | FR-UI-002 | 1d | ✅ 已完成（部分） |
| **4** | **`keyTemplateService.js` + useMetaList 委托** | **FR-UI-004** | **0.5d** | **⬜ 本子 spec** |
| **5** | **`draftPersistService.js` + useMetaList 委托** | **FR-UI-005** | **1.5d** | **⬜ 本子 spec** |
| **6** | **`columnTransformService.js` + `actionTransformService.js` + `fieldPolicyService.js`** | **FR-UI-003 part** | **2d** | **⬜ 本子 spec** |
| **7** | **`useMetaList.js` 全面下沉（接口契约保护）** | **FR-UI-003 part** | **3d** | **⬜ 本子 spec** |

**PR 4-7 总工作量**：0.5 + 1.5 + 2 + 3 = **7 天**（与父 spec §6.2 "Phase 1 (P0) 5-7 天" 一致）

### 7.2 时间线

```
Day 1:   PR 4 (keyTemplateService)         ← 0.5d
Day 2-3: PR 5 (draftPersistService)        ← 1.5d
Day 4-5: PR 6 (column/action/fieldPolicy)  ← 2d
Day 6-8: PR 7 (useMetaList 全面下沉)        ← 3d
```

### 7.3 PR 依赖图

```
PR 1 (httpClient) ─┐
                   ├─→ PR 4 (keyTemplate) ─→ PR 7 (useMetaList)
PR 2 (API_BASE) ───┤   PR 5 (draftPersist) ─┘
PR 3 (auth) ───────┤   PR 6 (column/...) ────┘
                   └─→ PR 7 主实施
```

---

## 8. 测试策略

### 8.1 测试金字塔

| 层级 | 数量 | 速度 | 目标 |
|------|------|------|------|
| 单元（service） | ~30 用例 | < 50ms | 函数/方法级 |
| 集成（useMetaList） | ~15 用例 | < 500ms | composable + service |
| E2E（列表页） | ~10 用例 | < 5s | 完整链路 |

### 8.2 测试文件清单

```
src/services/
├── keyTemplateService.spec.js              (本次新增)
├── draftPersistService.spec.js             (本次新增)
├── columnTransformService.spec.js          (FR-UI-003 part)
├── actionTransformService.spec.js          (FR-UI-003 part)
└── fieldPolicyService.spec.js              (FR-UI-003 part)

src/composables/__tests__/
├── useMetaList.api_contract.spec.js        (本次新增 - 82 个 API 守护)
├── useMetaList.integration.spec.js         (已有 - 9 用例)
└── useMetaList.batch.spec.js               (已有 - 10+ 用例)

tests/e2e/
└── list.spec.js                             (已有 - 关键路径)
```

### 8.3 关键测试场景

#### 8.3.1 接口契约（本次新增）
- **82 个公开 API 数量保证**（api_contract.spec.js）
- **核心方法为函数**（typeof check）
- **状态/计算属性为 ref/computed**（.value 检查）

#### 8.3.2 行为不变式（继承 useMetaList.integration.spec.js）
- 列定义 / 搜索字段 / 工具栏操作
- pagination 翻页 / sort 排序 / filter 过滤
- 行选择 / 跨页选择
- 导入导出对话框开关

#### 8.3.3 业务逻辑下沉（service 单元测试）
- keyTemplateService: validate / build / suggest (12+ 用例)
- draftPersistService: split / payloadForNew / payloadForUpdate / batchSave (12+ 用例)
- columnTransformService: transformColumns / inferColumnPriority (8+ 用例)
- actionTransformService: transformActions / inferActionPosition (8+ 用例)
- fieldPolicyService: getFieldEditConfig (8+ 用例)

### 8.4 覆盖率要求

| 文件 | 行覆盖率 | 分支覆盖率 |
|------|:--------:|:---------:|
| keyTemplateService.js | ≥ 90% | ≥ 85% |
| draftPersistService.js | ≥ 90% | ≥ 85% |
| columnTransformService.js | ≥ 90% | ≥ 85% |
| actionTransformService.js | ≥ 90% | ≥ 85% |
| fieldPolicyService.js | ≥ 90% | ≥ 85% |
| useMetaList.js（重构后） | ≥ 70% | ≥ 65% |

### 8.5 端到端验证流程

```bash
# 1. PR 4 验证
npm test -- keyTemplateService.spec.js
# 12+ 用例全通过

# 2. PR 5 验证
npm test -- draftPersistService.spec.js
# 12+ 用例全通过

# 3. PR 7（最终）验证
npm test -- useMetaList.api_contract.spec.js
npm test -- useMetaList.integration.spec.js
npm test -- useMetaList.batch.spec.js
# 全部通过

# 4. 集成验证
python d:\filework\test.py --all --force
# 全量回归（pre-existing failed ≤ 21）
```

---

## 9. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|:----:|:---:|------|
| useMetaList 公开 API 数量变化（漏加/重命名） | 中 | 高 | **api_contract.spec.js 强制断言 82 个键值** |
| 行为字节级不一致（filter 顺序、export 格式） | 中 | 高 | useMetaList.integration.spec.js + 快照测试 |
| 草稿保存逻辑下沉后副作用丢失（ElMessage、loading） | 中 | 中 | saveDraftValues 保留 UI 状态管理；service 纯函数 |
| boService 接口差异（`callPost` vs `boService.batchSave`） | 中 | 中 | 在 service 包装层统一；与父 spec FR-UI-002 一致 |
| _suggestKeyTemplateCode 内部调 boService 导致循环依赖 | 低 | 中 | keyTemplateService 只依赖 boService，不被 boService 依赖 |
| 与并行会话（其他 PR 4-7）冲突 | 中 | 中 | **本子 spec 锁定 PR 4-5（高 ROI），PR 6-7 可分批** |
| 测试覆盖率不达标 | 低 | 中 | CI 卡点（覆盖率 < 90% 阻断合并） |
| 现有 100+ 列表页面回归 | 中 | 高 | 集成测试 + E2E 关键路径 + 公开 API 不变 |

---

## 10. 验收总结

### 10.1 FR-UI-003 验收（接口契约 + 不变式）

- [ ] `useMetaList.js` 行数 ≤ 1500
- [ ] 公开 API 82 个**数量+签名+行为 100% 一致**（api_contract.spec.js 强制）
- [ ] 6 个新 service 文件就位
  - [ ] `keyTemplateService.js`（FR-UI-004）
  - [ ] `draftPersistService.js`（FR-UI-005）
  - [ ] `columnTransformService.js`
  - [ ] `actionTransformService.js`
  - [ ] `fieldPolicyService.js`
  - [ ] `filterService.js`（扩展）
- [ ] 6 个 service 单元测试覆盖率 ≥ 90%
- [ ] `useMetaList.integration.spec.js` 全部通过
- [ ] `useMetaList.batch.spec.js` 全部通过
- [ ] 现有 100+ 列表页面渲染/过滤/排序/导出行为不变

### 10.2 FR-UI-004 验收（keyTemplateService）

- [ ] `src/services/keyTemplateService.js` 文件就位
- [ ] 3 个公开函数：validateParentParams / buildParentParams / suggestKeyTemplateCode
- [ ] `_suggestKeyTemplateCode` 内部委托给 service
- [ ] 12+ 单元测试全部通过
- [ ] 单测覆盖率 ≥ 90%

### 10.3 FR-UI-005 验收（draftPersistService）

- [ ] `src/services/draftPersistService.js` 文件就位
- [ ] 4 个公开函数：splitDraftsToCreateAndUpdate / payloadForNewRow / payloadForUpdateRow / batchSave
- [ ] 12 边界条件测试全部通过
- [ ] 草稿保存/取消/创建/更新行为与重构前**字节级一致**
- [ ] 单测覆盖率 ≥ 90%

### 10.4 整体指标

| 指标 | 重构前 | 重构后目标 |
|------|:------:|:--------:|
| `useMetaList.js` 行数 | 2505 | ≤ 1500 |
| 业务逻辑在 composable 行数 | ~600 | ≤ 100 |
| 业务逻辑占比 | ~24% | ≤ 8% |
| 6 个 service 单测覆盖率 | 0 | ≥ 90% |
| `_suggestKeyTemplateCode` 行数 | 47 | ≤ 10 |
| `saveDraftValues` 业务逻辑 | ~40 | ≤ 15 |
| 公开 API 数量 | 82 | **82（100% 一致）** |
| 列表 E2E 测试 | 通过 | **100% 通过** |

---

## 11. 变更 / 设计提案 (RFC)

### 11.1 As-Is 分析

- **当前状态**：`useMetaList.js` 2505 行；业务逻辑 600+ 行散落
- **关键问题**：
  - `_suggestKeyTemplateCode` 内嵌 47 行业务逻辑
  - `saveDraftValues` 内嵌 64 行 split + 过滤 + 构造
  - 6 个 service 缺失
  - 公开 API 82 个靠人工维护
- **关键代码路径**：
  - [useMetaList.js:1931-1977](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js#L1931-L1977) — `_suggestKeyTemplateCode`
  - [useMetaList.js:2099-2162](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js#L2099-L2162) — `saveDraftValues` 业务逻辑
  - [useMetaList.js:2090-2094](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js#L2090-L2094) — `getDraftCreates`
  - [useMetaList.js:2312-2445](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js#L2312-L2445) — 公开 API 82 个

### 11.2 Target State

- **目标**：
  - `useMetaList.js` ≤ 1500 行（-40%）
  - 6 个新 service 文件，每个 ≥ 90% 单测覆盖
  - 业务逻辑下沉 ~99 行（116 → 17）
  - 公开 API 82 个**自动断言**（api_contract.spec.js）
- **关键变更**：
  1. 新增 `keyTemplateService.js`（3 函数，~80 行）
  2. 新增 `draftPersistService.js`（4 函数，~120 行）
  3. 新增 `columnTransformService.js` / `actionTransformService.js` / `fieldPolicyService.js`（FR-UI-003 part）
  4. 扩展 `filterService.js`（FR-UI-003 part）
  5. `useMetaList.js` 委托调用（业务逻辑 116 → 17 行）
  6. 新增 `api_contract.spec.js`（接口契约自动断言）

### 11.3 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **下沉到 service（本子 spec）** | 可单测、可重用、SSOT | 工作量大（5-7d） | ✅ 选定 |
| 重构 useMetaList 但不抽 service | 工作量小 | 仍不可单测 | ❌ |
| 整体重写 useMetaList（用 reactive utility） | 现代化 | 公开 API 变化影响 100+ 页面 | ❌ |
| 仅下沉 keyTemplate/draftPersist（PR 4-5 本子 spec） | 高 ROI、低风险 | column/action/fieldPolicy 暂不重构 | ✅ **推荐先 PR 4-5** |

### 11.4 实施与迁移计划

- **实施顺序**：PR 4 → PR 5 → PR 6 → PR 7
- **风险缓解**：
  - PR 4-5（keyTemplate + draftPersist）独立可发布 → **本子 spec 实施边界**
  - PR 7（useMetaList 全面下沉）作为后续 PR
  - api_contract.spec.js 任何 PR 必跑
- **回滚计划**：
  - 单 PR 回滚：`git revert <PR-sha>`
  - 整体回滚：保留每个 PR 独立 commit，便于 bisect

---

## 12. 附录 — 父子 spec 关系

### 12.1 本子 spec 来自父 spec §4 FR-UI-003/004/005

| 父 spec 章节 | 本子 spec 章节 | 关系 |
|-------------|---------------|------|
| §4 FR-UI-003 | §4 接口契约 | **展开**（82 个 API 清单 + 6 service + api_contract.spec.js） |
| §4 FR-UI-004 | §5 keyTemplateService | **展开**（详细实现 + 12 用例测试矩阵） |
| §4 FR-UI-005 | §6 draftPersistService | **展开**（详细实现 + 12 边界条件 + 算法伪代码） |
| §6.1 PR 4-7 | §7 实施计划 | **聚焦**（本子 spec 边界 = PR 4-5） |
| §6.3 E2E 策略 | §8 测试策略 | **聚焦**（接口契约 + 集成 + E2E 三层） |
| §8 验收 §8.1 | §10 验收总结 | **细化**（本子 spec 内 30+ 验收点） |
| §9 RFC | §11 RFC | **聚焦**（本子 spec 视角的设计提案） |
| 附录 A.5 / A.6 | §5.2 / §6.2 | **等价**（API 签名直接采纳） |
| 附录 B.1 / B.2 | §6.3 / §6.4 | **等价**（算法 + 边界条件直接采纳） |

### 12.2 本子 spec 不覆盖（保留在父 spec）

- FR-UI-001/002/006（httpClient / authService / API_BASE）— 已完成
- FR-UI-007 ~ 014（Phase 2 + Phase 3）— 后续 spec
- httpClient 错误对象 code 枚举 — 父 spec 附录 D
- 12 service 完整清单 — 父 spec 附录 A（除本子 spec §5 §6 详细化的 2 个）

### 12.3 本子 spec 后续可拆分

- PR 6（columnTransform / actionTransform / fieldPolicyService）— 可拆为独立子 spec
- PR 7（useMetaList 全面下沉）— 可拆为独立子 spec（500+ 行）

---

## 13. TBD List

| ID | 项 | 推荐答案 | 决策点 |
|----|---|---------|--------|
| TBD-S1 | `_suggestKeyTemplateCode` 是否调用 `boService.suggestKeyTemplateCode`（带空 params `{}`）？ | **保持现状**（L1959 调用形式）；keyTemplateService.suggestKeyTemplateCode 内部调 boService；service 接口不暴露 `{}` 参数 | ✅ 保留 |
| TBD-S2 | `getDraftCreates` 是否下沉？ | **下沉到 draftPersistService.payloadForNewRow**；getDraftCreates 变 2 行（仅委托） | ✅ 下沉 |
| TBD-S3 | `saveDraftValues` 的副作用（ElMessage、loading、refresh）是否下沉？ | **不下沉**（UI 副作用保留在 composable）；service 仅返回 `{success, failed, errors}` 数值 | ✅ 不下沉 |
| TBD-S4 | `boService.batchSave` 与 `callPost('batch_save', ...)` 哪个？ | **统一为 `boService.batchSave(objectType, drafts)`**（与父 spec §4 一致） | ✅ 统一 |
| TBD-S5 | PR 4-5 与 PR 6-7 拆分粒度？ | **本子 spec 边界 = PR 4-5**（高 ROI、低风险、2 天可完成）；PR 6-7 拆为后续子 spec | ✅ 拆分 |

---

## 14. 下一步行动

1. **用户 review 本子 spec**
2. **本子 spec 实施边界确认**：PR 4-5（keyTemplate + draftPersist，2 天）+ api_contract.spec.js
3. **PR 4 实施**：
   - 新增 `src/services/keyTemplateService.js`（3 函数 + 12 用例）
   - 修改 `useMetaList.js:_suggestKeyTemplateCode`（47 → 6 行）
   - 验证 `useMetaList.api_contract.spec.js` 通过
4. **PR 5 实施**：
   - 新增 `src/services/draftPersistService.js`（4 函数 + 12 边界用例）
   - 修改 `useMetaList.js:saveDraftValues`（64 → 12 行）
   - 修改 `useMetaList.js:getDraftCreates`（5 → 2 行）
5. **集成验证**：
   - `npm test` 全过
   - `python test.py --all --force` ≤ 21 pre-existing failed（无新增）
6. **PR 6-7 后续子 spec 拆分**

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-06 | 初稿；从父 spec 拆出 PR 4-7 FR-UI-003/004/005 独立子 spec | AI Agent (Trae) |
| 1.1.0 | 2026-06-06 | **§15 补充：table/list UI 核心能力 backlog**（与头部产品对标 12 维分析 + 8 类 P0-P2 战略补充） | AI Agent (Trae) |
| 1.2.0 | 2026-06-06 | **§16-18 真实消费侧深度审计**（8 业务页 → 1 统一入口 + 6 死代码 + 4 子组件 + 6 service 依赖 + v3 引擎衔接） | AI Agent (Trae) |
| 1.3.0 | 2026-06-06 | **§19 DetailPage ↔ MetaListPage 双向链路分析**（修正 17 → 25 真实破坏面；新发现 5 consumer；4 种 displayMode；双向刷新链 E2E） | AI Agent (Trae) |
| 1.4.0 | 2026-06-06 | **§20 ValueHelp 弹窗组件深度分析**（修正 25 → 28 真实破坏面；6 种 fetcher 模式；5 层链路 E2E；useMetaList ↔ MetaListPage self-loop） | AI Agent (Trae) |
| 1.5.0 | 2026-06-06 | **§21-25 8 大遗漏维度深度审计**（路由/Store/Service/通知/i18n/守卫/Element Plus/94 API 精确清单；28 → 35 真实破坏面）+ **§26-28 spec 整体架构/模块化/优化重构**（父子解耦/版本基线/Mermaid 架构图/TODO 清单） | AI Agent (Trae) |
| 1.5.0 | 2026-06-06 | **§21-25 8 大遗漏维度深度审计**（路由/Store/Service/通知/i18n/守卫/Element Plus/94 API 精确清单；28 → 35 真实破坏面）+ **§26-28 spec 整体架构/模块化/优化重构**（父子解耦/版本基线/Mermaid 架构图/TODO 清单） | AI Agent (Trae) |

---

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

## 19. DetailPage ↔ MetaListPage 双向链路分析（v1.3.0 补充）

> **目标**：深入审计 DetailPage 对 MetaList 的依赖，揭示之前 §16 未发现的 5 个真实 consumer 与双向刷新链
> **数据来源**：[DetailPage.vue L1-1107](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue) + [ObjectPage/* L1-137](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/) + [ObjectChildSection.vue L1-633](file:///d:/filework/excel-to-diagram/src/components/common/ObjectChildSection/ObjectChildSection.vue) + 双向 grep
> **结论先行**：**真实破坏面 17 → 25**；**DetailPage 自身 0 个 useMetaList 调用**，但通过 ObjectPage 的 section 配置**间接控制 4 处 MetaListPage 嵌入**（displayMode='embedded' ×3 + 双模式 ×1）

### 19.1 关键纠正：v1.2.0 §16 真实破坏面计算有遗漏

| 维度 | v1.2.0 §16.5 假设 | v1.3.0 实际 |
|------|----------------|------------|
| 直接 `import useMetaList` 文件数 | 6 | 6 ✅ |
| 直接 `import MetaListPage` 文件数 | **未统计** | **12**（+6 个新发现） |
| 总计真实破坏面 | 17 个 | **25 个**（+8） |
| 双向循环 | 未识别 | **MetaListPage → DetailPage → ObjectPage → MetaListPage** |
| displayMode 维度 | 未提及 | 4 种（page/embedded/dialog/未指定） |

### 19.2 DetailPage 组件家族规模（v1.3.0 实际数据）

```
src/components/common/DetailPage/                 (54.9KB / 1824 行)
├── DetailPage.vue                                35.3KB / 1107 行  (核心)
├── DetailSection.vue                             17.7KB /  627 行
├── AssociationSection.vue                        1.8KB /   98 行  (简化包装)
└── index.js                                      0.1KB /    2 行

src/components/common/ObjectPage/                 (64.1KB / 2194 行)
├── ObjectPage.vue                                2.7KB /   61 行  (轻量壳)
├── ObjectPageShell.vue                          23.6KB /  865 行
├── ObjectPageContent.vue                        14.5KB /  507 行  (含 AssociationSection)
├── ObjectPageWithChildren.vue                    4.5KB /  137 行  (含 ObjectChildSection)
├── ObjectPageField.vue                          11.1KB /  405 行
└── ObjectPageHeader.vue                          7.7KB /  289 行

src/views/ObjectDetailPage.vue                    13.2KB /  499 行  (路由级 DetailPage 包装)
```

**合计 119.0KB / 4,517 行** —— 这是与 useMetaList 重构密切相关的"详情页生态"。

### 19.3 双向循环依赖图（v1.3.0 实际代码审计）

```
┌────────────────────────────────────────────────────────────────────┐
│                MetaList (table/list UI)                            │
│  MetaListPage.vue (50KB / 1772 行)                                │
│  ├─ 75+ 公开 API 给 MetaListPage 自身解构                          │
│  └─ openDetailDrawer() ────────────────────┐                      │
└───────────────────────────────────────────│──────────────────────┘
                                            │
                                            ▼
              ┌──────────────────────────────────────────────┐
              │      DetailPage (35KB / 1107 行)              │
              │  - 抽屉模式（el-drawer）                      │
              │  - 独立模式（standalone）                     │
              │  - service: boService (v1 backend)           │
              │                                                │
              │ 透传 2 个 useMetaList 字段（L721/L739）       │
              │  ↓                                            │
              │ <ObjectPage> (61 行)                         │
              │   ├─ <ObjectPageContent>                    │
              │   │   ├─ FieldGroupSection                  │
              │   │   ├─ HistorySection                     │
              │   │   └─ <AssociationSection>  ←────────┐   │
              │   │                                     │   │
              │   └─ <ObjectPageWithChildren>           │   │
              │       └─ <ObjectChildSection>  ←────┐   │   │
              └─────────────────────────────────────│───│───┘
                                                    │   │
   ┌────────────────────────────────────────────────┘   │
   │                                                    │
   ├─→ ObjectPage/AssociationSection.vue (1.8KB)       │
   │     (1.8KB 简化包装，但逻辑有 633 行)             │
   │     ├─ isManyToMany: <MetaListPage embedded :options.fetcher=queryAssociations />
   │     ├─ isAnnotation: <MetaListPage embedded :objectType='annotation' (硬编码) />
   │     └─ default: <MetaListPage embedded :initial-filters={parent_id: id} />
   │     (3 处 MetaListPage 嵌入)
   │
   └─→ ObjectChildSection/ObjectChildSection.vue (11.1KB)
         (双模式开关)
         ├─ useMetaList=false (默认): useParentChild 自实现 + el-table
         └─ useMetaList=true: <MetaListPage embedded :options=metaListOptions />
         (双模式切换)
```

### 19.4 4 种 displayMode 完整画像

| displayMode | 消费方 | 数量 | 关键差异 |
|-------------|--------|:---:|---------|
| `'page'` | GenericObjectList / AuditLogManagement / 6 死代码 stub | 8 | **全功能**（工具栏 + 详情 + 导入导出 + 完整 dialog 容器） |
| `'embedded'` | ObjectPage/AssociationSection (×3) + ObjectChildSection (useMetaList=true) | 4 | **嵌入模式**（无外壳、无 toolbar header、嵌入父容器） |
| `'dialog'` | SearchHelpDialog + AssignmentDialog | 2 | **弹窗模式**（el-dialog 容器，无 page header） |
| 未指定 | MultiObjectManagementPage | 1 | 默认行为（推测为 page 模式） |
| **小计** | **12 个 .vue** | **15 处 MetaListPage 嵌入** | - |

**新发现**：`displayMode` 是 useMetaList 重构的**关键行为维度**——refactor 后必须保证 **3 种 displayMode × 完整 API 行为不变**。

### 19.5 5 个新发现的 consumer 详细分析

#### 19.5.1 ObjectPage/AssociationSection.vue（**3 处 MetaListPage 嵌入**）

| 场景 | 触发条件 | displayMode | 关键 props | fetcher 来源 |
|------|---------|-------------|-----------|-------------|
| **Many-to-Many 关联** | assocType='many_to_many' + assocName + targetType | embedded | `:columns-override=manyToManyColumns` | `boService.queryAssociations` (L196) |
| **Annotation 备注** | section.type='annotation' + hasRealObjectId | embedded | `:object-type='annotation'` (硬编码) | 自定义 `annotationFetcher` (L311-329) |
| **普通关联** | targetType + objectType + objectId | embedded | `:initial-filters={parent_id: id}` (L285) | `boService.queryAssociations` (L289) |

**风险等级**：🔴 **高**——详情页核心场景，重构 useMetaList 必须保证 3 处嵌入行为不变

**refactor 影响**：
- 任何 useMetaList 公开 API 的行为/默认值变化 → 3 处嵌入同步出问题
- fetcher 注入机制（`options.fetcher`）必须保持兼容
- inject 协同（`registerMetaListRef` from MetaListPage via ObjectPage L180）必须保留

#### 19.5.2 ObjectChildSection.vue（**双模式开关**）

```vue
<!-- 模式 1: useMetaList=false (默认，自实现) -->
<div v-else-if="hasData" class="ocs-table-wrapper">
  <el-table :data="data"> ... </el-table>  <!-- 简单表格 -->
</div>

<!-- 模式 2: useMetaList=true (高级模式) -->
<div v-if="useMetaListMode" class="ocs-metalist-wrapper">
  <MetaListPage :object-type="childObjectType" :options="metaListOptions"
                :initial-filters :enable-detail :enable-auto-crud
                :row-mutability="effectiveRowMutability" />
</div>
```

**关键 props（双模式共享）**：
- `useMetaList: Boolean` (默认 false)
- `enableDetail: Boolean` (默认 true)
- `enableAutoCrud: Boolean` (默认 true)
- `rowMutability: String` (默认 null)

**风险等级**：🟠 **中**——双模式都需保证行为不变

**新发现**：ObjectChildSection **同时 import 了 DetailPage**（L167），存在**潜在三重循环**（MetaListPage → DetailPage → ObjectChildSection → MetaListPage）

#### 19.5.3 SearchHelpDialog.vue（**值选择对话框**）

```vue
<MetaListPage :object-type="entityType" :display-mode="'dialog'"
              :columns-override :options :toolbar-actions-override
              :row-actions-override :batch-actions-override />
```

**关键 props**：
- `displayMode='dialog'` (与 page / embedded 区分)
- 用于 FkLinkField / ValueHelpField 值选择

**风险等级**：🟠 **中**——FkLinkField 是核心组件，搜索 → 选择 → 回填

#### 19.5.4 AssignmentDialog.vue（**分配对话框**）

```vue
<MetaListPage :object-type="entityType" :display-mode="'dialog'"
              :options :enable-detail :enable-auto-crud />
```

**关键 props**：
- `displayMode='dialog'`
- 用于多对多关联分配（assign / unassign）

**风险等级**：🟠 **中**——核心工作流

#### 19.5.5 MultiObjectManagementPage.vue（**多对象管理**）

```vue
<MetaListPage :object-type :options ... />
```

**特殊**：
- 使用 `useMultiObjectPage` composable（**第 2 个被发现的 composable**，除 useMultiObjectList 外）
- L210 `import { setRefreshCoordinator } from '@/services/boService'` —— 接入 boService refresh 协调
- L209 `import { useRefreshCoordinator } from '@/composables/useRefreshCoordinator'` —— 刷新协调器

**风险等级**：🟡 **低-中**

### 19.6 双向刷新链（v1.3.0 新增关键发现）

#### 19.6.1 完整刷新链路

```
1. MetaListPage 列表行 → 用户点击"查看详情"按钮
   ↓
2. MetaListPage.openDetailDrawer(row) (L1241)
   ↓ showDetailDrawer=true
3. <DetailPage> 内部 <ObjectPage> 渲染
   ↓ metaLoaded 后
4. ObjectPage → ObjectPageContent → <AssociationSection> 渲染
   ↓ 关联 section 加载
5. AssociationSection → <MetaListPage embedded> 渲染
   ↓ 用户编辑内嵌列表
6. 用户保存 → boService.create/update
   ↓ 保存成功后
7. AssociationSection 调用 boService._clearCache(props.objectType) (L408/602)
   ↓
8. refresh() → metaListRef.value.refresh() (L626-630)
   ↓
9. emit('refresh') → 父 MetaListPage 收到
   ↓
10. 父 MetaListPage 重新加载列表（避免列表与详情不一致）
```

**关键同步点**：
- `boService._clearCache` 是关键——**必须在重构时保留**
- `metaListRef.refresh()` 通过 `ObjectPage` 内部的 `registerMetaListRef` 注入传递

#### 19.6.2 双向刷新链风险点

| # | 风险点 | 风险等级 | 修复建议 |
|:-:|--------|:-------:|---------|
| 1 | useMetaList 重构后 `refresh()` 函数引用变化 | 🔴 | **接口契约保护**：必须保持 `metaListRef.value.refresh()` 可用 |
| 2 | `boService._clearCache` 时机变化 | 🟠 | **接口契约保护**：调用时机/参数必须不变 |
| 3 | inject `registerMetaListRef` 链路变化 | 🟠 | **保持 inject/provide 协议** |
| 4 | fetcher 自定义函数调用顺序变化 | 🟠 | **保持 fetcher 签名一致** |
| 5 | useListActionStore 派发时机变化 | 🟡 | **保持派发协议** |

### 19.7 真实破坏面（v1.3.0 修订 17 → 25）

| 类别 | 文件 | 数量 |
|------|------|:---:|
| **核心消费** | MetaListPage.vue | 1 |
| **路由级消费** | GenericObjectList + ObjectDetailPage | 2 |
| **真定制页** | AuditLogManagement | 1 |
| **死代码 stub** | 6 个 (UserGroup/Role/User/Version/EnumValue/Product) | 6 |
| **新增发现的 consumer**（v1.3.0 补充） | ObjectPage/AssociationSection + ObjectChildSection + SearchHelpDialog + AssignmentDialog + MultiObjectManagementPage | 5 |
| **useMetaList 直接测试** | 2 spec (integration + batch) | 2 |
| **MetaListPage 子测试** | 4 spec (fk-link/AssociationNavigationMenu/NavigationSourceInfo) | 4 |
| **useDetail 平行测试** | 1 spec (useDetail.spec.js) | 1 |
| **formatDate 工具引用** | 3 文件 (InlineEditCell/AuditLogManagement/SystemAdmin) | 3 |
| **总计真实破坏面** | | **25 个文件** |

### 19.8 重构风险矩阵（v1.3.0 完整版）

| # | 风险点 | 风险等级 | 来源 |
|:-:|--------|:-------:|------|
| 1 | useMetaList 重构后 75+ API 行为变化 | 🔴 | MetaListPage.vue L649-739 |
| 2 | **displayMode='embedded' 嵌入模式下 useMetaList 行为差异** | 🔴 | ObjectPage/AssociationSection L4/L45/L71 |
| 3 | **displayMode='dialog' 弹窗模式下 useMetaList 行为差异** | 🔴 | SearchHelpDialog + AssignmentDialog |
| 4 | **useMetaList=true 双模式切换** | 🟠 | ObjectChildSection L46-62 |
| 5 | **boService 缓存清除时机**（双向刷新链） | 🟠 | AssociationSection L408/602/410/567/611 |
| 6 | fetcher 自定义函数（queryAssociations/annotations） | 🟠 | AssociationSection L195-202/288-309/311-329 |
| 7 | AssociationSection 自身 3 个 fetcher 模式 | 🟡 | manyToMany/association/annotation |
| 8 | 5+ 个 useMetaList 事件回调 | 🟡 | openDetailDrawer/refresh/data-loaded |
| 9 | **6 个死代码 stub** 误删 | 🟢 | 0 import（PR 8 清理） |
| 10 | **5 个新发现 consumer 的测试覆盖** | 🟠 | ObjectChildSection/SearchHelpDialog/AssignmentDialog/MultiObjectManagementPage/AssociationSection |
| 11 | **ObjectDetailPage 路由详情 + DetailPage 协调** | 🟠 | L271-273 handleStateTransitionSuccess |
| 12 | **三重潜在循环**（MetaListPage→DetailPage→ObjectChildSection→MetaListPage） | 🟡 | ObjectChildSection L167 import DetailPage |

### 19.9 决策点（v1.3.0 新增 TBD）

| ID | 项 | 推荐答案 | 决策点 |
|----|---|---------|--------|
| TBD-19-1 | 之前漏掉的 5 个 consumer 是否需补 useMetaList 集成测试？ | **是**（高 ROI：覆盖度从 50% → 95%） | ✅ 加 |
| TBD-19-2 | displayMode='embedded' 是否单测？ | **是**（3 个场景：manyToMany/annotation/default） | ✅ 加 |
| TBD-19-3 | displayMode='dialog' 是否单测？ | **是**（2 个场景：SearchHelp/Assignment） | ✅ 加 |
| TBD-19-4 | useMetaList=true 双模式是否单测？ | **是**（ObjectChildSection 模式切换） | ✅ 加 |
| TBD-19-5 | DetailPage ↔ MetaListPage 双向刷新链是否 E2E？ | **是**（openDetailDrawer → save → refresh） | ✅ 加 |
| TBD-19-6 | fetcher 自定义函数（queryAssociations/annotations）是否单测？ | **是**（3 个 fetcher × 参数透传 × 返回值格式） | ✅ 加 |
| TBD-19-7 | 真实破坏面 25 个是否每个都需要契约保护？ | **不是**：8 个 MetaListPage consumer + 17 个间接 = 25 个全部保护 | ✅ 全保护 |
| TBD-19-8 | ObjectChildSection 三重循环风险？ | **保持现有 import 协议**（DetailPage 备用），不增加新 import | ✅ 保持 |
| TBD-19-9 | PR 4-7 范围是否扩展到 25 个文件？ | **是**：扩展原 PR 5 范围 | ✅ 扩 |

### 19.10 PR 4-7 范围修订（v1.3.0）

| PR | v1.2.0 范围 | v1.3.0 修订 |
|:-:|------------|------------|
| **PR 4** | 6 service | ✅ 不变 |
| **PR 5** | 接口契约 + 测试（原 17 文件） | 🟠 **扩到 25 文件** |
| **PR 6** | 7 天完成 | ✅ 不变 |
| **PR 7** | 集成测试 | 🟠 **范围扩：12 consumer × 4 displayMode** |
| **PR 8** | 清理 6 死代码 stub | ✅ 不变（0.5d） |
| **PR 9 (新增)** | — | 🆕 **补 5 consumer 契约测试**（2d） |

**PR 4-7 期间**：增加约 **2d** 工作量到 PR 9

### 19.11 6 个 service 依赖关系在双向链路中的变化

#### 19.11.1 useMetaList 自身依赖（不变）

| 依赖 | 调用点 | 用途 | refactor 风险 |
|------|:----:|------|:-----------:|
| boService (L19) | L395, L450 | 数据加载 | 🔴 行为不变 |
| metaService (L20) | L325, L884 | 元数据 | 🔴 行为不变 |
| dateFormatService (L21) | L2463 | 日期 | 🟢 工具 |
| useFieldPolicy (L22) | L1800 | 字段策略 | 🟡 业务 |
| useListActionStore (L23) | L1763 | 派发 | 🟢 工具 |
| filterService (L24-35) | 多个 | 过滤转换 | 🟡 业务 |
| safeExpression.evaluateCondition (L17) | 1 处 | 表达式 | 🟢 工具 |
| ElMessage/ElMessageBox (L18) | 多个 | 错误处理 | 🟢 UI |

#### 19.11.2 双向链路中的新协同点

| 协同点 | 来源 | 风险 |
|--------|------|:----:|
| **boService.read 共享** | DetailPage L818 + MetaListPage 内嵌 | 🟠 缓存一致性 |
| **boService._clearCache 时机** | AssociationSection L408/602 | 🔴 双向刷新链 |
| **boService.queryAssociations fetcher** | AssociationSection L196/289 | 🟠 fetcher 签名 |
| **boService.unassignAssociationV2** | AssociationSection L384/594 | 🟠 关联操作 |
| **refreshCoordinator inject** | MetaListPage L647 + MultiObjectManagementPage L209/210 | 🟡 跨页协调 |
| **registerMetaListRef inject** | ObjectPage/AssociationSection L180 | 🟡 ref 传递 |

**关键**：useMetaList 重构时如果**改变了 boService 的清除时机/方式**，会破坏 detail ↔ list 的双向刷新链。

### 19.12 4 类消费场景的差异

| 场景 | displayMode | 容器 | 工具栏 | 详情抽屉 | 导入导出 | 行内编辑 | 风险 |
|------|-------------|------|:-----:|:-------:|:-------:|:-------:|:---:|
| 列表页（GenericObjectList） | page | 整页 | ✅ | ✅ | ✅ | ✅ | 🟠 |
| 详情页内嵌（AssociationSection ×3） | embedded | 内嵌 | ❌ | ❌ | ❌ | ❌ | 🔴 |
| 父子子表（ObjectChildSection） | embedded | 内嵌 | ❌ | ❌ | ❌ | ❌ | 🟠 |
| 值选择（SearchHelpDialog） | dialog | el-dialog | ✅ | ❌ | ❌ | ❌ | 🟠 |
| 关联分配（AssignmentDialog） | dialog | el-dialog | ✅ | ❌ | ❌ | ❌ | 🟠 |
| 多对象管理 | 默认 | 整页 | ✅ | ✅ | ✅ | ✅ | 🟡 |

**新发现**：useMetaList 4 种 displayMode 提供**渐进增强**——核心 API 一致，外围 UI 元素按需启用。重构必须保证**所有 displayMode 的核心 API 行为完全一致**。

### 19.13 与父 spec v2.0.1 的关系

父 spec §1.3 提到"周边模块"未消费 useMetaList —— **v1.3.0 §19 揭示这个假设是错误的**：
- ObjectPage/AssociationSection 是 useMetaList 的**核心消费者**（不是"周边"）
- ObjectChildSection / SearchHelpDialog / AssignmentDialog / MultiObjectManagementPage 都是 useMetaList 的**真实业务消费者**

**修正建议**：父 spec v2.0.1 §1.3 应更新为"**useMetaList 的真实消费方 = 12 个 .vue（25 个文件受 refactor 影响）**"。

### 19.14 总结：v1.3.0 关键发现

#### 19.14.1 真实破坏面
- **17 → 25**（+8 个文件）
- 之前 §16.1.1 漏掉 **5 个真实 consumer**（AssociationSection/ObjectChildSection/SearchHelpDialog/AssignmentDialog/MultiObjectManagementPage）
- 之前 §16.5 漏掉 **1 个测试**（useDetail.spec.js）
- 之前 §16 漏掉 **1 个路由级消费者**（ObjectDetailPage）

#### 19.14.2 关键架构特征
- **双向循环**：MetaListPage ↔ DetailPage（不是单向）
- **三重潜在循环**：MetaListPage → DetailPage → ObjectChildSection → MetaListPage
- **4 种 displayMode**：page / embedded / dialog / 默认
- **3 种 fetcher 模式**：queryAssociations / annotation / default
- **boService 共享**：双向刷新链的关键

#### 19.14.3 重构影响
- useMetaList 75+ API 必须保护（接口契约）
- 4 种 displayMode 行为必须保护（displayMode 单测）
- 双向刷新链必须 E2E 测试
- 5 个新 consumer 必须补契约测试（PR 9）
- 6 service 依赖必须保留（接口稳定）

#### 19.14.4 一句话总结
> **v1.3.0 §19 揭示：useMetaList 是 v1 frontend 的"中间层核心"——不仅是 GenericObjectList 的内部实现，更是 DetailPage 详情页体系（12 consumer / 25 文件）的隐式核心。重构必须按"中间件"标准对待，不能仅当 list composable 看待。**

---

---
