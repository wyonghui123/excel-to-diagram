# 布局设置整合到左侧 Sidebar — 设计文档

> **日期**: 2026-08-04
> **项目**: excel-to-diagram (Vue 3 + Element Plus + Pinia)
> **状态**: 待评审 (Pending Review)
> **作者**: AI Assistant (Brainstorming Session)

---

## 一、背景与目标

### 1.1 当前现状

「布局设置」面板当前以 `el-drawer`（宽度 380px）形式从右侧滑出，承载 `LayoutControlPanel` 组件，用于在图表视图下调整图表布局（分组、间距、对齐等）。

**当前调用链**:
```
ChartMiniToolbar「布局设置」按钮 (@open-layout-settings)
  → RelationshipManagement.archDataChartSwitcherProps.layoutDrawerVisible
  → ArchDataChartSwitcher.<el-drawer v-model="drawerVisible">
  → <LayoutControlPanel :containers :domain-products :links :model-value />
```

### 1.2 痛点

1. **入口割裂**: 「布局设置」是图表视图的常用操作，但入口位于顶部 toolbar，与左侧 sidebar 中的图表范围/对象范围/过滤面板分离，用户视线需要在屏幕两侧反复跳转。
2. **drawer 与 sidebar 风格不一**: drawer 是浮层、sidebar 是固定栏，两套交互心智模型并存。
3. **互斥交互缺失**: drawer 展开时不会自动收起 sidebar 中其他面板，用户需要在两处分别管理折叠状态。

### 1.3 目标

把当前右侧 `el-drawer`(380px) 的布局设置面板整合到左侧 sidebar，作为 `RelationScopeTree` 的第 4 个 `CollapsiblePanel`（最底层，参与互斥 accordion），统一交互心智模型。

### 1.4 非目标 (Non-Goals)

- 不调整 sidebar 整体宽度（保持过滤区域当前 320px，用户后续会进一步优化内部布局设置元素和控件交互）。
- 不改动 `LayoutControlPanel.vue` 内部实现（保持为纯 UI 组件）。
- 不引入新的图表渲染逻辑。
- 不重构 `chartConfig.layoutControl` 的归属（仍由 `RelationshipManagement` 持有，不进 store）。

---

## 二、现状分析

### 2.1 关键文件与使用点

| 文件 | 角色 | 备注 |
|------|------|------|
| `src/stores/diagramConfigStore.js` | Pinia store，持有图表配置 | 已有 `chartConfig`、`positions`、`centerScopeMarkers` 等 |
| `src/components/common/RelationScopeTree/RelationScopeTree.vue` | sidebar 容器，含 3 个 CollapsiblePanel | 现有互斥逻辑在 L151-176 |
| `src/views/AADiagramApp/components/LayoutControlPanel.vue` | 布局设置 UI 组件（纯 props 驱动） | **有两个使用点**，不改 |
| `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` | 图表渲染视图 | 产出 containers/domainProducts/links（computed L797/L941/L952）|
| `src/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue` | 图表视图切换器，含 `el-drawer`（L45-62）| 待删除 drawer |
| `src/views/SystemManagement/RelationshipManagement.vue` | 系统管理页根，持有 `layoutDrawerVisible`（L112）| 待清理 |
| `src/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue` | 图表顶部小工具条，含「布局设置」按钮（L128-131）| 待删除按钮 |
| `src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue` | 多对象管理页（sidebar 宿主之一），持有 `viewMode` | 需 provide viewMode |
| `src/views/AADiagramApp/components/LayoutSelector.vue` | LayoutControlPanel 的**第二使用点**（L102-119）| 不改，是 LayoutControlPanel 保持 props 的关键原因 |
| `src/components/common/CollapsiblePanel/CollapsiblePanel.vue` | 通用可折叠面板 | 复用，不改 |

### 2.2 LayoutControlPanel 的两个使用点

```
使用点 A: ArchDataChartSwitcher.vue (el-drawer 内)
  <LayoutControlPanel
    :containers="containers"
    :domain-products="domainProducts"
    :links="links"
    :model-value="layoutControlValue"
    @update:model-value="onLayoutUpdate" />

使用点 B: LayoutSelector.vue (AADiagramApp, L102-119)
  <LayoutControlPanel
    :containers="..."
    :domain-products="..."
    :links="..."
    ... />
```

**结论**: `LayoutControlPanel` 必须保持纯 UI 组件（接收 props），不能改为直接从 store 读取。否则使用点 B 会被破坏。这意味着 `RelationScopeTree` 需要从 store 读取 snapshot 后再以 props 形式传给 `LayoutControlPanel`。

### 2.3 RelationScopeTree 现有 3-panel 互斥逻辑（L151-176）

```
现有状态变量:
  - objectExpanded   (对象范围 panel)
  - relationExpanded (关系范围 panel)
  - filterExpanded   (过滤 panel)

互斥规则: 展开任一时，收起其他两个
```

---

## 三、设计方案

### 3.1 方案选型

**方案 B (store 承载渲染数据快照)** + **§4 修正 (LayoutControlPanel 保持 props 不变)**

**核心思想**: `EmbeddedChartView` 渲染图表时产出的 `containers`/`domainProducts`/`links` 同步写入 `diagramConfigStore.chartDataSnapshot`（新增 shallowRef），`RelationScopeTree` 第 4 个 panel 从 store 读取后以 props 传给 `LayoutControlPanel`。

### 3.2 选择理由

- **保持 LayoutControlPanel 纯 UI**: 因 `LayoutSelector.vue` 第二使用点存在，不能让 LayoutControlPanel 直接依赖 store。
- **store 已有同模式**: `positions`/`centerScopeMarkers` 已使用 shallowRef 承载大体量渲染数据，新增 `chartDataSnapshot` 与现有模式一致。
- **解耦渲染与编辑**: 图表数据快照由渲染层写入，编辑层（LayoutControlPanel）只读消费，职责清晰。

---

## 四、数据流

### 4.1 整体数据流图（ASCII）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              左侧 Sidebar                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    RelationScopeTree                                 │  │
│  │                                                                      │  │
│  │  ┌──[ CollapsiblePanel: 对象范围 ]──┐  (panel 1)                     │  │
│  │  │  用户选区 → scopeIds                                             │  │
│  │  └──────────────────────────────────┘                                │  │
│  │  ┌──[ CollapsiblePanel: 关系范围 ]──┐  (panel 2)                     │  │
│  │  │  用户选区 → scopeIds                                             │  │
│  │  └──────────────────────────────────┘                                │  │
│  │  ┌──[ CollapsiblePanel: 过滤      ]──┐  (panel 3)                     │  │
│  │  │  filter 配置                                                     │  │
│  │  └──────────────────────────────────┘                                │  │
│  │  ┌──[ CollapsiblePanel: 布局设置 ]──┐  (panel 4, 新增)               │  │
│  │  │  v-if="hasChartData"                                             │  │
│  │  │  ┌─────────────────────────────────────────────────────────┐   │  │
│  │  │  │  LayoutControlPanel (不改, 纯 props)                     │   │  │
│  │  │  │   :containers="snapshot.containers"                     │   │  │
│  │  │  │   :domain-products="snapshot.domainProducts"            │   │  │
│  │  │  │   :links="snapshot.links"                               │   │  │
│  │  │  │   :model-value="layoutControlValue"                     │   │  │
│  │  │  │   @update:model-value="onLayoutUpdate"                  │   │  │
│  │  │  └─────────────────────────────────────────────────────────┘   │  │
│  │  └──────────────────────────────────┘                                │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
        ▲                                              ▲
        │ inject('mompViewMode')                       │ props (从 store 读)
        │                                              │
┌───────┴───────────────────┐         ┌────────────────┴──────────────────────┐
│ MultiObjectManagementPage │         │       diagramConfigStore              │
│  provide('mompViewMode')  │         │  ┌─────────────────────────────────┐  │
└───────────────────────────┘         │  │ chartDataSnapshot (shallowRef)  │  │
                                      │  │   { containers,                 │  │
                                      │  │     domainProducts,             │  │
                                      │  │     links }                     │  │
                                      │  │ layoutPanelExpanded (ref)       │  │
                                      │  └─────────────────────────────────┘  │
                                      └────────────────┬──────────────────────┘
                                                       ▲ updateChartDataSnapshot
                                                       │
                                      ┌────────────────┴──────────────────────┐
                                      │       EmbeddedChartView               │
                                      │  watch([containers, domainProducts,  │
                                      │         links]) →                    │
                                      │    diagramConfigStore                 │
                                      │      .updateChartDataSnapshot(...)   │
                                      │                                       │
                                      │  containers    (computed L797)        │
                                      │  domainProducts (computed L941)      │
                                      │  links         (computed L952)        │
                                      └────────────────┬──────────────────────┘
                                                       ▲ 消费 chartConfig.layoutControl
                                                       │ (图表配置仍由 RelationshipManagement 持有)
                                      ┌────────────────┴──────────────────────┐
                                      │       RelationshipManagement          │
                                      │  chartConfig.layoutControl (主源)     │
                                      │  layoutControlValue (computed)        │
                                      │  onLayoutUpdate (handler)             │
                                      └───────────────────────────────────────┘
```

### 4.2 数据流步骤

1. **对象范围/关系范围**（sidebar panel 1, 2）→ 用户选区 → `scopeIds` → 触发图表数据加载。
2. **EmbeddedChartView 渲染** → 产出 `containers`/`domainProducts`/`links` → 写入 `diagramConfigStore.chartDataSnapshot`（新增 shallowRef）。
3. **RelationScopeTree 第 4 个 CollapsiblePanel「布局设置」** 从 store 读 snapshot → 传 props 给 `LayoutControlPanel`。
4. **LayoutControlPanel 编辑** `chartConfig.layoutControl`（仍由 `RelationshipManagement` 持有，不进 store）+ `GlobalToolbar` 的颜色配置 → `EmbeddedChartView` 消费 `chartConfig` → 渲染图表。

### 4.3 关键决策点

- **LayoutControlPanel 零改动**: 因 `LayoutSelector.vue` 第二使用点存在，LayoutControlPanel 保持纯 UI 组件（接收 props），不改为从 store 读取。`RelationScopeTree` 负责从 store 读 snapshot 再传 props。
- **layoutControl 不进 store**: `chartConfig.layoutControl` 的主源仍是 `RelationshipManagement`，保持现有 sync 从属关系。store 只承载渲染数据快照，不承载编辑态。

---

## 五、改动文件清单

| 文件 | 改动类型 | 改动内容 |
|------|---------|---------|
| `src/stores/diagramConfigStore.js` | 新增字段 + 扩展 action | 新增 `chartDataSnapshot`（shallowRef `{containers,domainProducts,links}`）、`layoutPanelExpanded`（ref bool）；新增 `updateChartDataSnapshot` action、`setLayoutPanelExpanded` action；`resetConfig` 扩展重置这两个字段；return 导出 |
| `src/components/common/RelationScopeTree/RelationScopeTree.vue` | 模板追加 + 逻辑扩展 | template 末尾追加第 4 个 `CollapsiblePanel title="布局设置" v-if="hasChartData"`，内含 `<LayoutControlPanel :containers :domain-products :links :model-value @update:model-value />`；新增 `layoutExpanded` ref + `handleLayoutToggle`（参与 4-panel 互斥，同步 `store.layoutPanelExpanded`）；`handleObjectToggle`/`handleRelationToggle`/`handleFilterToggle` 各加 `layoutExpanded.value=false`；`inject('mompViewMode')`；`hasChartData` computed（`viewMode==='chart' && snapshot.containers.length>0`）；watch `store.layoutPanelExpanded`；CSS `.rst-panel-layout:not(.is-collapsed){flex:1 1 0;min-height:200px}` |
| `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` | 新增 watch | 新增 `watch([containers,domainProducts,links])` 写入 `diagramConfigStore.updateChartDataSnapshot`，`immediate:true`，位置在 L451 现有 `watch(chartConfig.layoutControl)` 附近。`containers`/`domainProducts`/`links` 已是 computed（L797/L941/L952） |
| `src/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue` | 删除 drawer | 删除 L45-62 `el-drawer` 整段；移除 `layoutDrawerVisible` prop + `update:layoutDrawerVisible` emit + `drawerVisible` computed + `LayoutControlPanel` import |
| `src/views/SystemManagement/RelationshipManagement.vue` | 删除 drawer 状态 | 删除 L112 `layoutDrawerVisible` ref；`ArchDataChartSwitcher` props 移除 `:layout-drawer-visible` 和 `@update:layout-drawer-visible`；`ChartMiniToolbar` 的 `@open-layout-settings` 绑定删除 |
| `src/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue` | 删除按钮 | 删除 L128-131「布局设置」按钮（`el-tooltip`+`el-button`）；`open-layout-settings` 从 emits 列表移除；`SetUp` icon import 若无其他用处可删 |
| `src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue` | 新增 provide | `provide('mompViewMode', viewMode)`（viewMode ref 已存在） |
| `src/views/AADiagramApp/components/LayoutControlPanel.vue` | **不改** | 保持纯 UI 组件，接收 `containers`/`domainProducts`/`links` props |

---

## 六、互斥逻辑设计

### 6.1 现状扩展

`RelationScopeTree` 现有 3 panel 互斥（L151-176）：`objectExpanded`/`relationExpanded`/`filterExpanded`。展开任一时收起其他两个。

### 6.2 扩展为 4-panel 互斥

新增 `layoutExpanded` ref。展开任一 panel 时收起其他三个：

```
状态变量 (4 个):
  - objectExpanded   (对象范围)
  - relationExpanded (关系范围)
  - filterExpanded   (过滤)
  - layoutExpanded   (布局设置, 新增)

handleLayoutToggle(expanded):
  layoutExpanded.value = expanded
  if expanded:
    objectExpanded.value = false
    relationExpanded.value = false
    filterExpanded.value = false
  diagramConfigStore.setLayoutPanelExpanded(expanded)  // 同步 store

handleObjectToggle(expanded):    // 现有，扩展
  objectExpanded.value = expanded
  if expanded:
    relationExpanded.value = false
    filterExpanded.value = false
    layoutExpanded.value = false   // 新增

handleRelationToggle(expanded):  // 现有，扩展
  relationExpanded.value = expanded
  if expanded:
    objectExpanded.value = false
    filterExpanded.value = false
    layoutExpanded.value = false   // 新增

handleFilterToggle(expanded):    // 现有，扩展
  filterExpanded.value = expanded
  if expanded:
    objectExpanded.value = false
    relationExpanded.value = false
    layoutExpanded.value = false   // 新增
```

### 6.3 store 同步

`handleLayoutToggle` 调用 `diagramConfigStore.setLayoutPanelExpanded(expanded)`，使外部（如 `MultiObjectManagementPage` 或其他需要感知布局 panel 状态的逻辑）可读取。`RelationScopeTree` 同时 watch `store.layoutPanelExpanded`，支持外部强制收起/展开。

---

## 七、Store 字段设计

### 7.1 新增字段

```javascript
// diagramConfigStore.js

// 图表渲染数据快照（大体量，shallowRef 避免深响应式）
const chartDataSnapshot = shallowRef({
  containers: [],
  domainProducts: [],
  links: []
})

// 布局 panel 展开状态（轻量，ref）
const layoutPanelExpanded = ref(false)
```

### 7.2 选择 shallowRef 的理由

`chartDataSnapshot` 中的 `containers`/`domainProducts`/`links` 可能含 1000+ 节点，使用 `shallowRef` 避免深响应式开销，与 store 中现有 `positions`/`centerScopeMarkers` 同模式。每次 `updateChartDataSnapshot` 整体替换引用即可触发依赖更新。

### 7.3 新增 action

```javascript
function updateChartDataSnapshot(snapshot) {
  chartDataSnapshot.value = {
    containers: snapshot.containers ?? [],
    domainProducts: snapshot.domainProducts ?? [],
    links: snapshot.links ?? []
  }
}

function setLayoutPanelExpanded(expanded) {
  layoutPanelExpanded.value = expanded
}
```

### 7.4 resetConfig 扩展

```javascript
function resetConfig() {
  // ... 现有重置逻辑 ...
  chartDataSnapshot.value = { containers: [], domainProducts: [], links: [] }
  layoutPanelExpanded.value = false
}
```

### 7.5 不动 layoutControlConfig

`chartConfig.layoutControl` 仍是 sync 从属，主源是 `RelationshipManagement` 持有的 `chartConfig.layoutControl`。store 不承载编辑态，只承载渲染数据快照。

### 7.6 return 导出

```javascript
return {
  // ... 现有导出 ...
  chartDataSnapshot,
  layoutPanelExpanded,
  updateChartDataSnapshot,
  setLayoutPanelExpanded
}
```

---

## 八、边界情况

| 场景 | 行为 |
|------|------|
| **list 视图** | 布局 panel 隐藏（`v-if="hasChartData"` 中 `viewMode==='chart'` 为 false） |
| **chart 视图未渲染** | `hasChartData` 为 false（`snapshot.containers.length===0`）→ panel 隐藏 |
| **chart 视图首次渲染完成** | `EmbeddedChartView` watch `immediate:true` 立即写入 snapshot → `hasChartData` 转 true → panel 出现 |
| **版本切换** | `EmbeddedChartView` 重渲染 → snapshot 更新 → 自动重新分组 |
| **图表类型切换** | `LayoutControlPanel` 已有 `chartType` watch，行为不变 |
| **LayoutSelector 第二使用点** | 不受影响，`LayoutControlPanel` 仍接收 props |
| **用户切换 chart → list** | `hasChartData` 转 false → 布局 panel 自动隐藏；若该 panel 正展开，`layoutExpanded` 应同步收起（详见下方实现说明） |
| **resetConfig 调用** | snapshot 与 layoutPanelExpanded 一并重置 |

### 8.1 chart → list 切换时 panel 收起

当 `viewMode` 从 `chart` 切到 `list`，`hasChartData` 变为 false，`v-if` 会卸载 panel。但 `layoutExpanded` ref 仍可能为 true。需在 `hasChartData` watch 中处理：

```javascript
watch(hasChartData, (val) => {
  if (!val && layoutExpanded.value) {
    layoutExpanded.value = false
    diagramConfigStore.setLayoutPanelExpanded(false)
  }
})
```

---

## 九、测试策略

### 9.1 store 单元测试

- `updateChartDataSnapshot`: 写入后 `chartDataSnapshot.value` 正确更新；`containers`/`domainProducts`/`links` 任一缺省时 fallback 为 `[]`。
- `setLayoutPanelExpanded`: 切换 `layoutPanelExpanded.value`。
- `resetConfig`: 调用后 `chartDataSnapshot` 重置为 `{containers:[],domainProducts:[],links:[]}`，`layoutPanelExpanded` 重置为 `false`。

### 9.2 组件单元测试

- **RelationScopeTree 4-panel 互斥**:
  - 展开布局 panel → 其他三个收起。
  - 展开任一其他 panel → 布局 panel 收起。
  - `hasChartData` 为 false 时布局 panel 不渲染。
  - `hasChartData` 由 true 转 false 时 `layoutExpanded` 自动收起。
  - `store.layoutPanelExpanded` 外部变更 → `layoutExpanded` 同步。
- **LayoutControlPanel**: 不变（已有测试覆盖，本次不改）。
- **EmbeddedChartView**: watch 触发后调用 `updateChartDataSnapshot`，传入的 snapshot 与 computed 值一致。

### 9.3 E2E 测试

- chart 视图下点击 sidebar「布局设置」panel header → panel 展开 + 其他三个 panel 收起 → `LayoutControlPanel` 分组列表可见。
- 调整布局设置 → 图表正确响应。
- 切到 list 视图 → 布局 panel 消失。
- 切回 chart 视图 → 布局 panel 重新出现。

---

## 十、业界对标

| 产品 | 模式 | 本设计借鉴点 |
|------|------|------------|
| **VS Code Activity Bar** | 侧边栏多个 panel 互斥展开（单 panel 主视图） | 4-panel 互斥 accordion |
| **Notion sidebar** | sidebar 状态由 store 承载，跨组件共享 | `chartDataSnapshot` 入 store，`RelationScopeTree` 从 store 读 |
| **现有 RelationScopeTree** | 已有 CollapsiblePanel accordion 模式 | 直接复用，仅追加第 4 个 panel |

---

## 十一、风险与权衡

### 11.1 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| snapshot 与渲染不同步 | LayoutControlPanel 显示过期数据 | `EmbeddedChartView` watch `immediate:true` + 依赖响应式 computed，保证同步 |
| shallowRef 误用深属性修改 | 依赖不更新 | 严格通过 `updateChartDataSnapshot` 整体替换引用 |
| `inject('mompViewMode')` 在非 MultiObjectManagementPage 宿主下 undefined | `hasChartData` 计算异常 | `inject` 提供默认值 `'chart'`，或在 `RelationScopeTree` 内做 undefined 兜底 |
| 4-panel 互斥时 sidebar 高度溢出 | 视觉抖动 | CSS `.rst-panel-layout:not(.is-collapsed){flex:1 1 0;min-height:200px}` + 现有滚动容器 |

### 11.2 权衡

- **store 承载 snapshot vs. props 透传**: 选 store 是因为 `EmbeddedChartView` 与 `RelationScopeTree` 在组件树中距离较远，props 透传需穿透多层。store 已有同模式（positions/centerScopeMarkers）。
- **保留 LayoutControlPanel props vs. 改为读 store**: 选保留 props 是因为第二使用点 `LayoutSelector.vue`。改为读 store 会破坏该使用点。
- **移除 toolbar「布局设置」按钮 vs. 保留快捷入口**: 用户确认移除，统一从 sidebar panel header 进入。
- **宽度不自动扩展**: 用户确认保持 320px，后续单独优化内部布局设置元素。

---

## 十二、验收标准

- [ ] chart 视图下，sidebar 出现第 4 个「布局设置」CollapsiblePanel。
- [ ] 点击「布局设置」panel header 展开，其他三个 panel 自动收起。
- [ ] 点击其他任一 panel header 展开，「布局设置」panel 自动收起。
- [ ] 「布局设置」panel 内的 LayoutControlPanel 分组列表与图表实际数据一致。
- [ ] 调整布局设置后图表正确响应。
- [ ] list 视图下「布局设置」panel 隐藏。
- [ ] 右侧 el-drawer 已完全移除，ChartMiniToolbar「布局设置」按钮已删除。
- [ ] `LayoutSelector.vue`（AADiagramApp）中的 LayoutControlPanel 使用点不受影响。
- [ ] `resetConfig` 后 snapshot 与 layoutPanelExpanded 重置。
- [ ] store 单测、组件单测、E2E 测试通过。

---

## 十三、待评审决策点

以下决策已在 brainstorming 阶段由用户确认，列入文档供 review 时复核：

1. **§4 修正**: LayoutControlPanel 保持 props 不变（因 LayoutSelector 第二使用点），RelationScopeTree 从 store 读再传。
2. **§7**: 移除 toolbar「布局设置」按钮，不保留快捷入口，用户直接点 sidebar panel header。
3. **§7**: viewMode 通过 `inject` 传入 RelationScopeTree（用户接受通用组件 inject 业务上下文）。
4. **§8**: 宽度不自动扩展，保持过滤区域当前 320px，用户后续会进一步优化内部布局设置元素和控件交互。

---

## 十四、参考文件路径

| 文件 | 路径 |
|------|------|
| diagramConfigStore | `d:\filework\excel-to-diagram\src\stores\diagramConfigStore.js` |
| RelationScopeTree | `d:\filework\excel-to-diagram\src\components\common\RelationScopeTree\RelationScopeTree.vue` |
| LayoutControlPanel | `d:\filework\excel-to-diagram\src\views\AADiagramApp\components\LayoutControlPanel.vue` |
| EmbeddedChartView | `d:\filework\excel-to-diagram\src\views\SystemManagement\components\ArchDataChart\EmbeddedChartView.vue` |
| ArchDataChartSwitcher | `d:\filework\excel-to-diagram\src\views\SystemManagement\components\ArchDataChart\ArchDataChartSwitcher.vue` |
| RelationshipManagement | `d:\filework\excel-to-diagram\src\views\SystemManagement\RelationshipManagement.vue` |
| ChartMiniToolbar | `d:\filework\excel-to-diagram\src\views\systemmanagement\components\archdatachart\ChartMiniToolbar.vue` |
| MultiObjectManagementPage | `d:\filework\excel-to-diagram\src\components\common\MultiObjectManagementPage\MultiObjectManagementPage.vue` |
| LayoutSelector（第二使用点，不改） | `d:\filework\excel-to-diagram\src\views\AADiagramApp\components\LayoutSelector.vue` |
| CollapsiblePanel | `d:\filework\excel-to-diagram\src\components\common\CollapsiblePanel\CollapsiblePanel.vue` |

---

**文档结束** — 请 review 后批准进入实现计划阶段（writing-plans skill）。
