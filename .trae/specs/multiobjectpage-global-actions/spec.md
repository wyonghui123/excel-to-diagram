# Spec: MultiObjectPage 全局 Actions 元数据驱动方案

## 1. 背景与目标

### 1.1 背景

当前 MultiObjectPage 的 GlobalToolbar 已渲染了导入/导出/图表/刷新 4 个图标按钮（Upload/Download/TrendCharts/Refresh），它们通过 `@action` 事件向上 emit。但 MultiObjectManagementPage 仅将事件透传为 `toolbarAction` 到父页面，所有实际的 action 处理逻辑（弹窗、API 调用、图表跳转）都需要父页面自行实现。

老页面 ArchDataManageApp 在父页面内联了所有相关代码：ImportDialog、ExportDialog、图表数据组装、sessionStorage 传递等，形成了大量耦合代码。

**核心理念**: GlobalToolbar 按钮已就位 → useMultiObjectPage 承载所有 action 状态与逻辑 → MultiObjectManagementPage 内部渲染对应弹窗 → 父页面零代码。

### 1.2 业务目标

- 使用 MultiObjectPage 构建的任何页面，自动获得导入/导出/图表/刷新能力
- 通过元数据驱动 action 的启用/禁用状态
- 导出支持单 Tab 类型 + 多类型批量两种模式
- 图表沿用 sessionStorage 方案（TODO: 未来改进传递方式）

### 1.3 涉众目标

- **框架开发者**: 零配置即可获得完整 actions 能力
- **最终用户**: 统一的导入/导出/图表操作体验，无需在不同页面学习不同交互

---

## 2. 需求类型总览

| 类型 | 适用 | 来源 |
|------|------|------|
| Business | Yes | 通用框架能力提升 |
| User/Stakeholder | Yes | 开发者、最终用户 |
| Solution | Yes | 元数据驱动架构 |
| Functional | Yes | FR-001 ~ FR-006 |
| Nonfunctional | Yes | NFR-001 ~ NFR-002 |
| External Interface | Yes | boService API、sessionStorage |
| Transition | Yes | ArchDataManageApp 逐步迁移 |

---

## 3. 功能需求

### FR-001: Global Action 按钮渲染与状态控制

- **描述**: GlobalToolbar 中的导入/导出/图表/刷新按钮的可见性和禁用状态必须由元数据驱动计算得出。
- **验收标准**:
  - 导入按钮: 当 `versionContext.selectedVersionId` 存在时启用，否则禁用
  - 导出按钮: 当 `versionContext.selectedVersionId` 存在时启用，否则禁用
  - 图表按钮: 当 `chartActionsEnabled && versionContext.selectedVersionId` 时启用，否则禁用
  - 刷新按钮: 当 `versionContext.selectedVersionId` 存在时启用，否则禁用
  - 无版本选择时所有按钮显示但 disabled
- **优先级**: Must
- **类型映射**: Functional
- **来源**: 用户确认 — 按钮内置于 GlobalToolbar

### FR-002: useMultiObjectPage 承载 Action 状态与逻辑

- **描述**: `useMultiObjectPage` 必须暴露以下 action 相关状态和方法：
  - `importDialogVisible`: 导入弹窗可见性 (ref)
  - `exportDialogVisible`: 导出弹窗可见性 (ref) — 复用 common ExportDialog，天然支持多对象
  - `canImport` / `canExport` / `canShowChart` / `canRefresh`: 功能可用性 (computed)
  - `handleGlobalAction(action)`: 统一 action 分发入口，参数为 `'import' | 'export' | 'chart' | 'refresh'`
  - `handleImportSuccess()`: 导入成功回调（刷新数据）
  - `handleExportSuccess()`: 导出成功回调
  - `handleShowChart()`: 图表跳转逻辑
  - `handleRefresh()`: 刷新当前数据
  - `exportContext`: 导出上下文（objectType, filters, objectTypes 等）(computed)
  - `importContext`: 导入上下文（version_id, product_id 等）(computed)
  - `chartContext`: 图表数据上下文 (computed)
- **验收标准**:
  - `handleGlobalAction('import')` → `importDialogVisible = true`
  - `handleGlobalAction('export')` → 如果只有 1 个可导出类型则打开单类型导出，否则弹出模式选择（或默认多类型）
  - `handleGlobalAction('chart')` → 执行图表跳转
  - `handleGlobalAction('refresh')` → 刷新当前 Tab 列表
- **优先级**: Must
- **类型映射**: Functional

### FR-003: 导入对话框集成

- **描述**: MultiObjectManagementPage 内部渲染 common ImportDialog 组件，由 useMultiObjectPage 管理其状态。
- **验收标准**:
  - 使用 `@/components/common/ImportDialog/ImportDialog.vue`
  - Props: `objectType` = 当前 activeTab, `objectTypes` = 所有层级对象类型, `context` = { version_id, product_id }
  - 导入成功后自动刷新当前列表和 scope tree
  - 弹窗关闭逻辑完整（reset state）
- **优先级**: Must
- **类型映射**: Functional
- **来源**: 通用 ImportDialog 已完善，直接复用

### FR-004: 导出对话框集成

- **描述**: MultiObjectManagementPage 内部渲染 common ExportDialog 组件。MultiObject 本身就是多对象定位，导出自然支持多对象——common ExportDialog 已通过元数据驱动的级联链（cascade chain）覆盖此场景。
- **验收标准**:
  - 使用 `@/components/common/ExportDialog/ExportDialog.vue`
  - Props: `objectType` = 当前 activeTab, `filters` = combinedFilters, `objectTypes` = 所有层级对象类型, `showExportMode` = true, `showExportOptions` = true
  - ExportDialog 内部通过 `metaService.buildCascadeChain(schema)` 自动推导可导出层级
  - 导出成功后弹窗关闭并按需刷新
- **优先级**: Must
- **类型映射**: Functional
- **来源**: common ExportDialog 已完善，直接复用

### FR-005: 展示图表 Action

- **描述**: 图表按钮触发时将当前页面状态序列化到 sessionStorage，然后路由跳转到 `/diagram`。沿用老 ArchDataManageApp 的数据结构。
- **验收标准**:
  - `canShowChart` 条件: `versionContext.selectedVersionId` 存在 **且** 存在层级过滤条件（`scopeIds` 中任一层级有选中项 或 `combinedFilters` 中有层级过滤字段）
  - 图表数据包含: `versionId`, `productId`, `hierarchyFilter`, `checkedNodeIds`, 各层级 selected IDs
  - sessionStorage key: `archDataForDiagram`
  - 路由跳转: `router.push('/diagram')`
- **优先级**: Must
- **类型映射**: Functional
- **来源**: 用户确认 — 保持 sessionStorage 方案，留 TODO

### FR-006: Action 可用性配置（元数据驱动）

- **描述**: Action 的启用逻辑由元数据驱动，支持配置化覆盖。
- **配置模型**:
  ```yaml
  # 在 useMultiObjectPage 的 config.options.actions 中配置
  actions:
    import:
      enabled: true       # boolean | 'auto' = 基于 objectTypes 自动推导
    export:
      enabled: true
      multi_type: true    # 是否支持多类型批量导出
    chart:
      enabled: true       # boolean
      require_filters: true  # 是否需要过滤条件才能激活
    refresh:
      enabled: true
  ```
- **自动推导规则**:
  - `import.enabled = 'auto'` 时: 如果任一 `objectType` 不是 `'relationship'` 且不是纯关联类型，则启用
  - `export.enabled = 'auto'` 时: 如果任一 `objectType` 存在，则启用
  - `chart.enabled`: 必须显式配置（不自动推导）
  - `refresh.enabled`: 默认 true
- **验收标准**:
  - 默认配置下（所有 actions enabled），行为符合老 ArchDataManageApp
  - 可通过 `options.actions.chart.enabled = false` 隐藏图表按钮
  - `enabled = false` 时对应按钮不渲染
- **优先级**: Should
- **类型映射**: Functional / Solution

---

## 4. 非功能需求

### NFR-001: 组件复用性

- **描述**: 导入/导出逻辑复用现有 common ImportDialog / ExportDialog 组件，不新建重复组件。
- **测量**: 新增代码行数 < 200 行（主要在 useMultiObjectPage 中添加 action 状态管理 + MultiObjectManagementPage 中添加弹窗引用）
- **优先级**: Must

### NFR-002: 可测试性

- **描述**: useMultiObjectPage 中的 action 逻辑必须可单独测试。
- **测量**: 新增测试用例覆盖 action 状态切换、enable/disable 逻辑、handleGlobalAction 分发
- **优先级**: Should

---

## 5. 外部接口需求

### IF-001: boService 导出接口

- **类型**: API
- **端点**: `POST /api/v1/export`
- **请求体**:
  ```json
  {
    "object_type": "domain",
    "scope": "single" | "cascade" | "selected",
    "selected_types": ["domain", "sub_domain", ...],
    "filters": { "version_id": 1, ... },
    "options": {
      "include_hierarchy_path": true,
      "include_hierarchy_ids": true,
      "include_metadata_sheet": true,
      "protect_sheet": false
    }
  }
  ```
- **响应**: `{ success: true, data: { download_url, sheets, total_rows } }`
- **来源**: 已有 boService.exportData

### IF-002: boService 导入接口

- **类型**: API
- **端点**: `POST /api/v1/import` (preview), `POST /api/v1/import/async` (execute)
- **来源**: 已有 common ImportDialog 调用 boService

### IF-003: sessionStorage 图表数据

- **类型**: Browser Storage
- **Key**: `archDataForDiagram`
- **Value**: JSON 序列化的图表上下文
- **来源**: 已有 ArchDataManageApp 实现

---

## 6. 过渡需求

### TR-001: 老 ArchDataManageApp 兼容

- **描述**: 本方案不修改老 ArchDataManageApp 的任何代码。新方案在 MultiObjectManagementPage 内部闭环。
- **策略**: 老页面保持现状，待新页面验证稳定后另行评估废弃。
- **回滚计划**: 如 MultiObjectPage 内 actions 有问题，父页面仍可通过 `toolbarAction` 事件自行处理（兼容模式）
- **来源**: 用户确认

### TR-002: 图表传递方案待改进

- **描述**: sessionStorage 方案有命名冲突风险（多页面同时使用时 key 相同）。
- **策略**: 本次保持 sessionStorage，标记为 TBD，未来迁移到 URL params 或 store 方案。
- **来源**: 用户确认

---

## 7. 约束与假设

### 7.1 技术约束

- 导入/导出依赖 `boService` 模块，必须可用
- 图表跳转依赖 `/diagram` 路由存在
- GlobalToolbar 当前渲染 4 个 action 按钮，不增不减
- Element Plus 组件库可用

### 7.2 业务约束

- 导入/导出/图表/刷新这 4 个 action 是固定的全局操作集
- 产品/版本选择由 GlobalToolbar 独立管理，不在 actions 范围内

### 7.3 假设

- 所有 objectType 都支持导出（通过 boService） — 来源: 已验证
- 所有非关系类型都支持导入 — 来源: 已验证
- `/diagram` 路由和 `AADiagramApp` 的 `initFromArchData` 逻辑不变 — 来源: 假设
- common ImportDialog / ExportDialog 组件功能满足需求 — 来源: 已验证

---

## 8. 优先级与里程碑

| ID | 需求 | 优先级 | 原因 |
|----|------|--------|------|
| FR-002 | useMultiObjectPage action 状态与逻辑 | Must | 核心基础设施 |
| FR-003 | 导入对话框集成 | Must | 基础功能 |
| FR-004 | 导出对话框集成 | Must | 基础功能 |
| FR-001 | 按钮渲染与状态控制 | Must | 用户可见入口 |
| FR-005 | 展示图表 Action | Must | 基础功能 |
| FR-006 | Action 可用性配置 | Should | 提升灵活性 |

**里程碑建议**:
- **M1**: useMultiObjectPage action 核心逻辑 + GlobalToolbar 按钮状态绑定
- **M2**: 导入/导出/图表对话框集成到 MultiObjectManagementPage
- **M3**: Action 可用性元数据配置化 + 测试补齐

---

## 9. 变更/设计提案 (RFC)

### 9.1 As-Is 分析

#### 当前架构

```
┌─ ArchDataManageApp/index.vue ─────────────────────────────────────┐
│  <AppButton @click="handleImport">导入</AppButton>                 │
│  <AppButton @click="showExportDialog=true">导出</AppButton>        │
│  <AppButton @click="handleShowChart">展示图表</AppButton>          │
│  <ImportDialog :visible="importDialogVisible" ... />               │
│  <AppModal :visible="showExportDialog" ... />                      │
│  <AppModal :visible="showListExportDialog" ... />                  │
│                                                                   │
│  handler functions: handleImport(), handleExportAll(),             │
│    executeListExport(), handleShowChart(), ...                     │
└───────────────────────────────────────────────────────────────────┘

┌─ MultiObjectManagementPage.vue ───────────────────────────────────┐
│  <GlobalToolbar @action="$emit('toolbarAction', $event)" />        │
│  <!-- 无 ImportDialog / ExportDialog / Chart 逻辑 -->              │
│                                                                   │
│  page = useMultiObjectPage(objectTypes, options)                   │
│  <!-- page 无 action 状态 -->                                      │
└───────────────────────────────────────────────────────────────────┘
```

#### 当前痛点

1. 每个使用 MultiObjectPage 的页面都需重复写 action 处理逻辑
2. 弹窗状态管理分散在父页面，无法统一
3. GlobalToolbar 按钮已渲染但需父页面自行响应事件
4. ArchDataManageApp 有自己的 ImportDialog（1036行），与 common ImportDialog（784行）功能重叠

#### 相关代码路径

| 文件 | 角色 |
|------|------|
| `src/composables/useMultiObjectPage.js` | 核心 composable，需扩展 |
| `src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue` | 页面组件，需集成弹窗 |
| `src/components/common/GlobalToolbar/GlobalToolbar.vue` | 工具栏（已有按钮） |
| `src/components/common/ImportDialog/ImportDialog.vue` | 通用导入弹窗 |
| `src/components/common/ExportDialog/ExportDialog.vue` | 通用导出弹窗 |
| `src/views/ArchDataManageApp/index.vue` | 老页面（参考，不动） |
| `src/services/boService.js` | 服务层 |

### 9.2 目标状态

```
┌─ MultiObjectManagementPage.vue ────────────────────────────────────┐
│  <GlobalToolbar                                                     │
│    @action="page.handleGlobalAction"                                │
│    :actions-disabled="{ import: !page.canImport, ... }"             │
│  />                                                                 │
│                                                                     │
│  <ImportDialog                                                      │
│    v-model:visible="page.importDialogVisible"                       │
│    :object-type="page.activeTab"                                    │
│    :object-types="page.objectTypes"                                 │
│    :context="page.importContext"                                    │
│    @success="page.handleImportSuccess"                              │
│  />                                                                 │
│                                                                     │
│  <ExportDialog                                                      │
│    v-model:visible="page.exportDialogVisible"                       │
│    :object-type="page.activeTab"                                    │
│    :filters="page.combinedFilters"                                  │
│    :object-types="page.objectTypes"                                 │
│    :show-export-mode="true"                                         │
│    :show-export-options="true"                                      │
│    @success="page.handleExportSuccess"                              │
│  />                                                                 │
│                                                                     │
│  page = useMultiObjectPage(objectTypes, options)                    │
│  <!-- page 暴露: handleGlobalAction, importDialogVisible,           │
│       canImport, importContext, handleImportSuccess, ... -->         │
└───────────────────────────────────────────────────────────────────┘
```

#### 关键变更

1. **useMultiObjectPage 新增 action 模块**: 约 80 行代码，管理弹窗可见性、可用性计算、action 分发
2. **MultiObjectManagementPage 集成弹窗**: 约 40 行模板代码，引用 common ImportDialog / ExportDialog
3. **GlobalToolbar 支持 disabled 状态**: 约 20 行，通过 props 控制按钮禁用状态（可选，如果按钮总是显示只是 disabled）
4. **多类型批量导出弹窗**: 可能复用 ExportDialog 的 cascade 模式，或用简单内联模板（约 50 行）

### 9.3 详细设计

#### 9.3.1 useMultiObjectPage action 模块设计

```js
// === 新增: Action 状态管理 ===

// 弹窗可见性
const importDialogVisible = ref(false)
const exportDialogVisible = ref(false)

// 导出结果
const exportResult = ref(null)
const exportError = ref('')
const exportLoading = ref(false)

// Action 配置（来自 options.actions，含默认值）
const actionsConfig = computed(() => ({
  import: { enabled: true, ...config.actions?.import },
  export: { enabled: true, multi_type: true, ...config.actions?.export },
  chart: { enabled: true, require_filters: true, ...config.actions?.chart },
  refresh: { enabled: true, ...config.actions?.refresh },
}))

// 可用性计算
const canImport = computed(() =>
  actionsConfig.value.import.enabled && !!versionContext.selectedVersionId.value
)
const canExport = computed(() =>
  actionsConfig.value.export.enabled && !!versionContext.selectedVersionId.value
)
const canShowChart = computed(() => {
  if (!actionsConfig.value.chart.enabled) return false
  if (!versionContext.selectedVersionId.value) return false
  if (!actionsConfig.value.chart.require_filters) return true
  return hasScopeSelection.value
})
const canRefresh = computed(() =>
  actionsConfig.value.refresh.enabled && !!versionContext.selectedVersionId.value
)

// 上下文
const importContext = computed(() => ({
  version_id: versionContext.selectedVersionId.value,
  product_id: versionContext.selectedProductId.value,
}))

const exportContext = computed(() => ({
  objectType: activeTab.value,
  filters: combinedFilters.value,
  objectTypes: objectTypes.filter(t => t !== 'relationship'),
}))

const exportableTypes = computed(() => {
  // 从 hierarchyTypes.levels 推导 + 可选 relationship
  const types = [...hierarchyTypes.levels.value.map(l => ({
    value: l.object_type, label: l.label || l.object_type
  }))]
  if (objectTypes.includes('relationship')) {
    types.push({ value: 'relationship', label: '关系' })
  }
  return types
})

// Action 分发
function handleGlobalAction(action) {
  switch (action) {
    case 'import':
      importDialogVisible.value = true
      break
    case 'export':
      exportDialogVisible.value = true
      break
    case 'chart':
      handleShowChart()
      break
    case 'refresh':
      handleRefresh()
      break
  }
}

// 图表跳转
function handleShowChart() {
  const chartData = {
    versionId: versionContext.selectedVersionId.value,
    productId: versionContext.selectedProductId.value,
    hierarchyFilter: { ...combinedFilters.value },
  }
  // 附加各层级 scope 数据
  objectTypes.forEach(type => {
    if (scopeIds[type]) {
      chartData[`selected${_pascalCase(type)}Ids`] = scopeIds[type].selected
    }
  })
  sessionStorage.setItem('archDataForDiagram', JSON.stringify(chartData))
  // router.push('/diagram') — 需在 MultiObjectManagementPage 层面调用 router
  return chartData
}

// 导入成功
function handleImportSuccess() {
  importDialogVisible.value = false
  // 触发刷新 — 由 MultiObjectManagementPage 响应
}

// 导出成功
function handleExportSuccess(result) {
  exportDialogVisible.value = false
  exportMultiDialogVisible.value = false
  exportResult.value = result
}

// 返回新增的 action 相关属性
return {
  // ... existing return ...
  importDialogVisible,
  exportDialogVisible,
  exportResult,
  canImport,
  canExport,
  canShowChart,
  canRefresh,
  handleGlobalAction,
  handleImportSuccess,
  handleExportSuccess,
  handleShowChart,
  importContext,
  exportContext,
}
```

#### 9.3.2 MultiObjectManagementPage 模板变更

```vue
<template>
  <div class="multi-object-management">
    <GlobalToolbar
      ref="globalToolbarRef"
      :compact="true"
      :action-disabled="actionDisabledMap"
      @change="handleToolbarChange"
      @action="page.handleGlobalAction"
    />

    <!-- 现有内容不变 ... -->

    <!-- 导入弹窗 -->
    <ImportDialog
      v-model:visible="page.importDialogVisible"
      :object-type="page.activeTab"
      :object-types="page.objectTypes"
      :context="page.importContext"
      @success="onImportSuccess"
    />

    <!-- 导出弹窗 -->
    <ExportDialog
      v-model:visible="page.exportDialogVisible"
      :object-type="page.activeTab"
      :object-type-name="currentTabLabel"
      :filters="page.combinedFilters"
      :object-types="page.objectTypes"
      :show-export-mode="true"
      :show-export-options="true"
      @success="page.handleExportSuccess"
    />
  </div>
</template>
```

#### 9.3.3 GlobalToolbar 扩展（可选）

当前 GlobalToolbar 按钮已渲染但未根据状态禁用。需要新增 `actionDisabled` prop：

```vue
<!-- GlobalToolbar.vue 变更 -->
<el-tooltip content="导入" placement="bottom">
  <el-button size="small" :icon="Upload" :disabled="actionDisabled?.import"
    @click="handleAction('import')" />
</el-tooltip>
<!-- 同理: export, chart, refresh -->
```

### 9.4 备选方案对比

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A. action 处理在 useMultiObjectPage 内 | 父页面零代码，纯元数据驱动 | composable 需引用 boService | **选定** |
| B. action 处理在 MultiObjectManagementPage 内 | 职责清晰（composable 只管过滤，component 管 UI action） | 父页面不可覆写行为 | 否决 — 与"通用"目标冲突 |
| C. 保持现状，每个父页面自己实现 | 无任何变更风险 | 老问题不解决 | 否决 |

### 9.5 实现与迁移计划

#### 实现顺序

1. **Phase 1: useMultiObjectPage 扩展**
   - 新增 action 状态 refs 和 computeds
   - 实现 `handleGlobalAction` 分发
   - 实现 `handleShowChart` (sessionStorage)
   - 新增测试用例

2. **Phase 2: MultiObjectManagementPage 集成弹窗**
   - 引入 `ImportDialog`, `ExportDialog`
   - 绑定 `@action` 事件到 `page.handleGlobalAction`
   - 图表跳转（MultiObjectManagementPage 中执行 router.push）
   - 从图表返回后恢复原状态（sessionStorage `lastArchDataForDiagram`）

3. **Phase 3: GlobalToolbar disabled 状态**
   - 添加 `actionDisabled` prop
   - 如果 Phase 不确定需要，可延后

4. **Phase 4: Action 可用性配置化**
   - 在 `options.actions` 中支持配置
   - 实现自动推导逻辑

#### 风险缓解

| 风险 | 缓解策略 |
|------|----------|
| GlobalToolbar disabled prop 影响现有使用者 | 设为可选 prop，默认 `{}`，向后兼容 |
| 图表 router 调用需在 Vue 组件上下文中 | useMultiObjectPage 返回 `chartData`，由 MultiObjectManagementPage 调用 router |
| ImportDialog/ExportDialog 依赖 metaService | 已在项目中可用，无额外依赖 |
| 多类型导出 API 与单类型不同 | 独立弹窗，独立 API 调用 |

#### 测试策略

- **单元测试**: `useMultiObjectPage` action 模块新增 10+ 测试用例
  - `handleGlobalAction('import')` 设置 `importDialogVisible = true`
  - `handleGlobalAction('export')` 判断 multi_type 配置选择弹窗
  - `canImport` / `canExport` / `canShowChart` 在不同状态下正确计算
  - `canShowChart` 在无 scope 选择时返回 false
  - `handleShowChart` 生成正确的 chartData 写入 sessionStorage
  - actions 配置为 false 时对应 canXxx 返回 false
- **集成测试**: MultiObjectManagementPage 渲染验证
  - 弹窗 v-model:visible 绑定正确
  - 导入成功后列表刷新

#### 回滚计划

- useMultiObjectPage 新增 return 属性向后兼容（纯增量）
- MultiObjectManagementPage 新增弹窗不影响现有功能
- 父页面仍可监听 `@toolbarAction` 自行处理（如果 props 传入自定义 handler）

---

## 10. TBD 列表

| ID | 事项 | 缺失信息 | 下一步 |
|----|------|----------|--------|
| TBD-1 | 图表数据传递方案改进 | sessionStorage 有命名冲突风险 | 评估 URL params / store 方案，后续迭代 |
| TBD-2 | 老 ArchDataManageApp 废弃 | 需确认新方案覆盖所有老功能 | 新页面验证后评估 |
| TBD-3 | ImportDialog 模板下载 action | 需要独立入口还是放在导入弹窗内？ | 当前 ImportDialog 内已有模板下载，无需额外 action |
| TBD-4 | chart 跳转时 router 访问 | useMultiObjectPage 不直接持有 router | ✅ 已确认: useMultiObjectPage 返回 chartData，MultiObjectManagementPage 执行 router.push；返回时恢复原状态 |
| TBD-5 | 多类型导出弹窗 | 用户指出 MultiObject 本身就定位多对象，common ExportDialog 已覆盖 | ✅ 已确认: 直接复用 common ExportDialog，无需单独多类型弹窗 |

---

*Spec 包含 10 个章节, 最后章节为 "TBD 列表", 内容完整。*
