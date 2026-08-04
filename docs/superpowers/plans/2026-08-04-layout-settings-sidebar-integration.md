# 布局设置整合到左侧 Sidebar — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把右侧 el-drawer 布局设置面板整合到左侧 sidebar 作为 RelationScopeTree 第 4 个 CollapsiblePanel，参与 4-panel 互斥 accordion。

**Architecture:** 方案 B (store 承载渲染数据快照) — EmbeddedChartView 将 containers/domainProducts/links 写入 diagramConfigStore.chartDataSnapshot (shallowRef)；RelationScopeTree 从 store 读 snapshot 后以 props 传给 LayoutControlPanel (零改动)。chartConfig.layoutControl 不进 store，通过 RelationshipManagement provide('chartConfig') → RelationScopeTree inject 跨树共享（与现有 inject('refreshCoordinator')/inject('metaObject') 同模式）。

**Tech Stack:** Vue 3 (Composition API), Pinia, Element Plus, Vitest

**Spec:** `docs/superpowers/specs/2026-08-04-layout-settings-sidebar-integration-design.md`

---

## 关键设计决策（spec self-review 补充）

**spec 中的歧义已解决**: RelationScopeTree 如何读写 chartConfig.layoutControl？

- `chartConfig` 由 RelationshipManagement 持有 (L109 `reactive(createDefaultChartConfig())`)
- RelationshipManagement 是 MultiObjectManagementPage 的父组件，MultiObjectManagementPage 在 #master slot 内渲染 RelationScopeTree
- 组件树: `RelationshipManagement → MultiObjectManagementPage → RelationScopeTree (#master slot)`
- **解法**: RelationshipManagement `provide('chartConfig', chartConfig)`，RelationScopeTree `inject('chartConfig', null)`
- RelationScopeTree 内: `:model-value="chartConfig?.layoutControl"` + `@update:model-value="(v) => Object.assign(chartConfig.layoutControl, v)"`
- 与 ArchDataChartSwitcher L59-60 现有模式完全一致，不违反 §4.3 "layoutControl 不进 store"

---

## File Structure

| 文件 | 职责 | 改动 |
|------|------|------|
| `src/stores/diagramConfigStore.js` | Pinia store | +chartDataSnapshot, +layoutPanelExpanded, +2 actions, resetConfig 扩展 |
| `src/stores/__tests__/diagramConfigStore.spec.js` | store 单测 | +3 test cases |
| `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` | 图表渲染 | +watch 写 snapshot |
| `src/views/SystemManagement/RelationshipManagement.vue` | 页面根 | +provide chartConfig, -layoutDrawerVisible, -drawer props/bindings |
| `src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue` | 通用页 | +provide viewMode |
| `src/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue` | 图表切换器 | -el-drawer, -LayoutControlPanel import, -drawer props/computed/emit |
| `src/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue` | 工具条 | -布局设置按钮, -open-layout-settings emit, -SetUp import |
| `src/components/common/RelationScopeTree/RelationScopeTree.vue` | sidebar 容器 | +4th CollapsiblePanel, +layoutExpanded, +handleLayoutToggle, +inject, +hasChartData, +CSS |
| `src/views/AADiagramApp/components/LayoutControlPanel.vue` | 布局 UI | **不改** |

---

## Task 1: Store — 新增 chartDataSnapshot + layoutPanelExpanded

**Files:**
- Modify: `src/stores/diagramConfigStore.js` (L43 附近新增字段, L204 resetConfig, L244 return)
- Test: `src/stores/__tests__/diagramConfigStore.spec.js`

- [ ] **Step 1: 写 store 新字段的失败测试**

在 `src/stores/__tests__/diagramConfigStore.spec.js` 末尾追加：

```javascript
  describe('chartDataSnapshot & layoutPanelExpanded', () => {
    it('初始状态: chartDataSnapshot 为空对象, layoutPanelExpanded 为 false', () => {
      const store = useDiagramConfigStore()
      expect(store.chartDataSnapshot).toEqual({ containers: [], domainProducts: [], links: [] })
      expect(store.layoutPanelExpanded).toBe(false)
    })

    it('updateChartDataSnapshot 应该整体替换 snapshot', () => {
      const store = useDiagramConfigStore()
      store.updateChartDataSnapshot({
        containers: [{ id: 'c1' }],
        domainProducts: [{ name: 'dp1' }],
        links: [{ source: 'a', target: 'b' }]
      })
      expect(store.chartDataSnapshot.containers).toEqual([{ id: 'c1' }])
      expect(store.chartDataSnapshot.domainProducts).toEqual([{ name: 'dp1' }])
      expect(store.chartDataSnapshot.links).toEqual([{ source: 'a', target: 'b' }])
    })

    it('updateChartDataSnapshot 缺省字段应 fallback 为空数组', () => {
      const store = useDiagramConfigStore()
      store.updateChartDataSnapshot({ containers: [{ id: 'c1' }] })
      expect(store.chartDataSnapshot.containers).toEqual([{ id: 'c1' }])
      expect(store.chartDataSnapshot.domainProducts).toEqual([])
      expect(store.chartDataSnapshot.links).toEqual([])
    })

    it('setLayoutPanelExpanded 应该切换展开状态', () => {
      const store = useDiagramConfigStore()
      store.setLayoutPanelExpanded(true)
      expect(store.layoutPanelExpanded).toBe(true)
      store.setLayoutPanelExpanded(false)
      expect(store.layoutPanelExpanded).toBe(false)
    })

    it('resetConfig 应该重置 chartDataSnapshot 和 layoutPanelExpanded', () => {
      const store = useDiagramConfigStore()
      store.updateChartDataSnapshot({ containers: [{ id: 'c1' }], domainProducts: [{}], links: [{}] })
      store.setLayoutPanelExpanded(true)
      store.resetConfig()
      expect(store.chartDataSnapshot).toEqual({ containers: [], domainProducts: [], links: [] })
      expect(store.layoutPanelExpanded).toBe(false)
    })
  })
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npx vitest run src/stores/__tests__/diagramConfigStore.spec.js -t "chartDataSnapshot"`
Expected: FAIL — `store.chartDataSnapshot is undefined`

- [ ] **Step 3: 在 diagramConfigStore.js 新增字段**

在 `src/stores/diagramConfigStore.js` L50 (`annotationCategoryFilter` ref) 之后、L52 (`useUnifiedRenderer`) 之前插入：

```javascript
  // [布局设置 sidebar 整合] 图表渲染数据快照 — EmbeddedChartView 写入, RelationScopeTree 读取
  //   shallowRef 避免对 1000+ 节点的 containers/domainProducts/links 创建深 Proxy (同 positions/centerScopeMarkers 模式)
  const chartDataSnapshot = shallowRef({
    containers: [],
    domainProducts: [],
    links: []
  })
  // [布局设置 sidebar 整合] 布局 panel 展开状态 — 跨组件共享 (RelationScopeTree 写, 外部可读)
  const layoutPanelExpanded = ref(false)
```

- [ ] **Step 4: 新增 actions**

在 `src/stores/diagramConfigStore.js` L194 (`clearAnnotationCategoryFilter` 函数) 之后插入：

```javascript
  // [布局设置 sidebar 整合] 更新图表渲染数据快照 (整体替换引用, 触发 shallowRef 依赖)
  function updateChartDataSnapshot(snapshot) {
    chartDataSnapshot.value = {
      containers: snapshot?.containers ?? [],
      domainProducts: snapshot?.domainProducts ?? [],
      links: snapshot?.links ?? []
    }
  }

  // [布局设置 sidebar 整合] 设置布局 panel 展开状态
  function setLayoutPanelExpanded(expanded) {
    layoutPanelExpanded.value = expanded
  }
```

- [ ] **Step 5: 扩展 resetConfig**

在 `src/stores/diagramConfigStore.js` 的 `resetConfig` 函数内，L241 (`mermaidMaxTextSize.value = 500000`) 之前插入：

```javascript
    // [布局设置 sidebar 整合] 重置 snapshot 和 panel 状态
    chartDataSnapshot.value = { containers: [], domainProducts: [], links: [] }
    layoutPanelExpanded.value = false
```

- [ ] **Step 6: 在 return 中导出新字段和 actions**

在 `src/stores/diagramConfigStore.js` return 对象中，L270 (`layoutControlConfig,`) 之后添加：

```javascript
    chartDataSnapshot,
    layoutPanelExpanded,
```

在 return 对象的 Actions 部分，L298 (`updateLayoutControlConfig,`) 之后添加：

```javascript
    updateChartDataSnapshot,
    setLayoutPanelExpanded,
```

- [ ] **Step 7: 运行测试确认通过**

Run: `npx vitest run src/stores/__tests__/diagramConfigStore.spec.js -t "chartDataSnapshot"`
Expected: PASS — 5 tests passed

- [ ] **Step 8: 运行全量 store 测试确认无回归**

Run: `npx vitest run src/stores/__tests__/diagramConfigStore.spec.js`
Expected: PASS — all tests passed

- [ ] **Step 9: Commit**

```bash
git add src/stores/diagramConfigStore.js src/stores/__tests__/diagramConfigStore.spec.js
git commit -m "feat(store): add chartDataSnapshot + layoutPanelExpanded for sidebar layout integration"
```

---

## Task 2: EmbeddedChartView — watch 写 snapshot 到 store

**Files:**
- Modify: `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` (L469 附近新增 watch)

- [ ] **Step 1: 确认 store import 已存在**

在 `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` 中搜索 `useDiagramConfigStore`。EmbeddedChartView 已有 `configStore` 引用 (L459 `configStore.updateLayoutControlConfig`)，确认 `const configStore = useDiagramConfigStore()` 存在于 script setup 顶部。若已存在则跳过此步。

- [ ] **Step 2: 在现有 layoutControl watch 之后新增 snapshot watch**

在 `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` L469 (现有 `watch(chartConfig.layoutControl, ...)` 的 `})` 闭合之后) 插入：

```javascript

// ============================================================
// [布局设置 sidebar 整合] 将 containers/domainProducts/links 同步到 store
//   RelationScopeTree 第 4 个 CollapsiblePanel 从 store 读取后传给 LayoutControlPanel
//   immediate: true 确保首次渲染即写入 (chart 视图打开时 panel 立即可用)
//   注意: containers/domainProducts/links 都是 computed (L797/L941/L952),
//         watch 监听 computed ref 的 .value 变化自动触发
// ============================================================
watch(
  [containers, domainProducts, links],
  ([c, dp, l]) => {
    configStore.updateChartDataSnapshot({
      containers: c,
      domainProducts: dp,
      links: l
    })
  },
  { immediate: true }
)
```

- [ ] **Step 3: 验证无语法错误**

Run: `npx vue-tsc --noEmit src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue 2>&1 | head -20` (若项目无 vue-tsc 则跳过)
或检查 IDE diagnostics 无报错。

- [ ] **Step 4: Commit**

```bash
git add src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue
git commit -m "feat(chart-view): sync containers/domainProducts/links to store snapshot"
```

---

## Task 3: RelationshipManagement — provide chartConfig + 清理 drawer 状态

**Files:**
- Modify: `src/views/SystemManagement/RelationshipManagement.vue` (L109 后加 provide, L43/L53-54/L112 删 drawer 相关)

- [ ] **Step 1: 新增 provide('chartConfig', chartConfig)**

在 `src/views/SystemManagement/RelationshipManagement.vue` L112 (`const layoutDrawerVisible = ref(false)`) 之前（即 L109 `const chartConfig = ...` 之后）插入：

```javascript
// [布局设置 sidebar 整合] 提供 chartConfig 给 RelationScopeTree (sidebar)
//   组件树: RelationshipManagement → MultiObjectManagementPage → RelationScopeTree (#master slot)
//   RelationScopeTree inject('chartConfig') 读取 layoutControl, 用 Object.assign 写回
//   与 ArchDataChartSwitcher L59-60 模式一致, layoutControl 不进 store
provide('chartConfig', chartConfig)
```

确保 `provide` 已在 vue import 中。检查 L87 `import { ref, reactive, computed } from 'vue'`，改为：

```javascript
import { ref, reactive, computed, provide } from 'vue'
```

- [ ] **Step 2: 删除 layoutDrawerVisible ref**

删除 L112:
```javascript
const layoutDrawerVisible = ref(false)
```
及其上方注释 L111:
```javascript
// [FIX 2026-07-31] 布局设置抽屉可见性：ChartMiniToolbar 的"布局设置"按钮触发
```

- [ ] **Step 3: 删除 ChartMiniToolbar 的 @open-layout-settings 绑定**

在 `src/views/SystemManagement/RelationshipManagement.vue` L43 删除：
```html
        @open-layout-settings="layoutDrawerVisible = true"
```

- [ ] **Step 4: 删除 ArchDataChartSwitcher 的 drawer 相关 props**

在 `src/views/SystemManagement/RelationshipManagement.vue` L50-58 的 `<ArchDataChartSwitcher` 标签内，删除 L53-54:
```html
        :layout-drawer-visible="layoutDrawerVisible"
        @update:layout-drawer-visible="(v) => (layoutDrawerVisible = v)"
```

- [ ] **Step 5: 验证无残留 layoutDrawerVisible 引用**

Run: `grep -rn "layoutDrawerVisible" src/views/SystemManagement/RelationshipManagement.vue`
Expected: 无输出（已全部删除）

- [ ] **Step 6: Commit**

```bash
git add src/views/SystemManagement/RelationshipManagement.vue
git commit -m "refactor(rel-mgmt): provide chartConfig + remove drawer state for sidebar integration"
```

---

## Task 4: MultiObjectManagementPage — provide viewMode

**Files:**
- Modify: `src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue` (script setup 内加 provide)

- [ ] **Step 1: 找到 viewMode 定义位置**

在 `src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue` 中搜索 `viewMode`。确认 `const viewMode = ref('list')` (或类似) 存在于 script setup 中。

- [ ] **Step 2: 新增 provide('mompViewMode', viewMode)**

在 viewMode 定义之后插入：

```javascript
// [布局设置 sidebar 整合] 提供 viewMode 给 RelationScopeTree
//   RelationScopeTree 用它判断 hasChartData (viewMode==='chart' 时布局 panel 才显示)
provide('mompViewMode', viewMode)
```

确保 `provide` 已在 vue import 中。若 import 行为 `import { ref, computed } from 'vue'` 等，添加 `provide`。

- [ ] **Step 3: Commit**

```bash
git add src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue
git commit -m "feat(momp): provide viewMode for RelationScopeTree layout panel visibility"
```

---

## Task 5: ArchDataChartSwitcher — 删除 el-drawer

**Files:**
- Modify: `src/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue` (L42-62 删 drawer, L88-91/L116-134 清理 import/props/computed/emit)

- [ ] **Step 1: 删除 el-drawer 模板块**

删除 `src/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue` L42-62（从 `<!-- [FIX 2026-07-31] 布局设置抽屉` 注释到 `</el-drawer>` 闭合）：

```html
    <!-- [FIX 2026-07-31] 布局设置抽屉：回溯修复丢失的 LayoutControlPanel 功能
         之前 EmbeddedChartView 注释说"布局抽屉已上移到 ArchDataChartSwitcher"，
         但本组件从未实际渲染抽屉 → 功能丢失。现在补回。 -->
    <el-drawer
      v-model="drawerVisible"
      title="布局设置"
      direction="rtl"
      size="380px"
      :destroy-on-close="false"
      :append-to-body="true"
    >
      <LayoutControlPanel
        v-if="embeddedChartRef && drawerVisible"
        :containers="embeddedChartRef.containers"
        :domain-products="embeddedChartRef.domainProducts"
        :links="embeddedChartRef.links"
        :chart-type="chartConfig.chartType"
        :model-value="chartConfig.layoutControl"
        @update:model-value="(v) => Object.assign(chartConfig.layoutControl, v)"
      />
    </el-drawer>
```

- [ ] **Step 2: 删除 LayoutControlPanel import**

删除 L90:
```javascript
import LayoutControlPanel from '@/views/AADiagramApp/components/LayoutControlPanel.vue'
```

- [ ] **Step 3: 删除 layoutDrawerVisible prop**

在 props 定义中删除 L115-119:
```javascript
  // [FIX 2026-07-31] 布局设置抽屉可见性：由 ChartMiniToolbar 的"布局设置"按钮控制
  layoutDrawerVisible: {
    type: Boolean,
    default: false
  }
```

- [ ] **Step 4: 从 emits 列表移除 update:layoutDrawerVisible**

在 emits 定义中删除 L127:
```javascript
  'update:layoutDrawerVisible' // 布局抽屉可见性变化
```

- [ ] **Step 5: 删除 drawerVisible computed**

删除 L130-134:
```javascript
// [FIX 2026-07-31] 布局抽屉 v-model 代理
const drawerVisible = computed({
  get: () => props.layoutDrawerVisible,
  set: (v) => emit('update:layoutDrawerVisible', v)
})
```

- [ ] **Step 6: 验证无残留 drawer/LayoutControlPanel 引用**

Run: `grep -n -i "drawer\|LayoutControlPanel" src/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue`
Expected: 无输出（或仅在注释中，无代码引用）

- [ ] **Step 7: Commit**

```bash
git add src/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue
git commit -m "refactor(chart-switcher): remove el-drawer layout settings (moved to sidebar)"
```

---

## Task 6: ChartMiniToolbar — 删除布局设置按钮

**Files:**
- Modify: `src/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue` (L126-131 删按钮, L145 删 import, L165 删 emit)

- [ ] **Step 1: 删除布局设置按钮**

删除 `src/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue` L126-131:

```html
    <div class="cmt-spacer"></div>

    <!-- 布局设置按钮：侧边打开 LayoutControlPanel 抽屉 -->
    <el-tooltip content="布局设置" placement="bottom" :teleported="false">
      <el-button size="small" :icon="SetUp" @click="emit('open-layout-settings')" />
    </el-tooltip>
```

注意：保留 `cmt-spacer` 之前的 toolbar 元素。仅删除 spacer + tooltip + button。若 spacer 之后无其他元素，则 spacer 也删除。

- [ ] **Step 2: 检查 SetUp icon 是否有其他使用**

Run: `grep -n "SetUp" src/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue`
若仅剩 import 行 (L145)，则删除该 import：

删除 L145:
```javascript
import { SetUp } from '@element-plus/icons-vue'
```

- [ ] **Step 3: 从 emits 列表移除 open-layout-settings**

删除 L165:
```javascript
  'open-layout-settings'
```

注意处理逗号：若 'open-layout-settings' 是最后一项，删除前一项末尾的逗号；若是中间项，删除自身及逗号。

- [ ] **Step 4: 验证无残留**

Run: `grep -n "open-layout-settings\|SetUp" src/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue`
Expected: 无输出

- [ ] **Step 5: Commit**

```bash
git add src/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue
git commit -m "refactor(toolbar): remove layout settings button (moved to sidebar panel)"
```

---

## Task 7: RelationScopeTree — 新增第 4 个 CollapsiblePanel

**Files:**
- Modify: `src/components/common/RelationScopeTree/RelationScopeTree.vue`

- [ ] **Step 1: 新增 inject 和 store 引用**

在 `src/components/common/RelationScopeTree/RelationScopeTree.vue` L119 (`const coordinator = inject(...)`) 之后添加：

```javascript
// [布局设置 sidebar 整合] inject chartConfig (由 RelationshipManagement provide)
//   用于 LayoutControlPanel 的 :model-value 和 @update:model-value
//   组件树: RelationshipManagement → MultiObjectManagementPage → RelationScopeTree
const injectedChartConfig = inject('chartConfig', null)
// [布局设置 sidebar 整合] inject viewMode (由 MultiObjectManagementPage provide)
//   用于 hasChartData 判断 (仅 chart 视图显示布局 panel)
const injectedViewMode = inject('mompViewMode', ref('chart'))

// [布局设置 sidebar 整合] diagramConfigStore — 读取 chartDataSnapshot + 同步 layoutPanelExpanded
const diagramConfigStore = useDiagramConfigStore()
```

在 import 区域 (L72) 确保 `useDiagramConfigStore` 已导入。添加到 import 区：

```javascript
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'
```

- [ ] **Step 2: 新增 layoutExpanded ref**

在 L129 (`const filterExpanded = ref(false)`) 之后添加：

```javascript
// [布局设置 sidebar 整合] 第 4 panel: 布局设置
const layoutExpanded = ref(false)
```

- [ ] **Step 3: 新增 hasChartData computed**

在 `layoutExpanded` ref 之后添加：

```javascript
// [布局设置 sidebar 整合] 仅 chart 视图且有渲染数据时显示布局 panel
const hasChartData = computed(() => {
  return injectedViewMode.value === 'chart' &&
    diagramConfigStore.chartDataSnapshot.containers.length > 0
})
```

- [ ] **Step 4: 新增 handleLayoutToggle 函数**

在 `handleFilterToggle` 函数 (L170-176) 之后添加：

```javascript
// [布局设置 sidebar 整合] 第 4 panel toggle — 参与 4-panel 互斥, 同步 store
function handleLayoutToggle(expanded) {
  layoutExpanded.value = expanded
  if (expanded) {
    objectExpanded.value = false
    relationExpanded.value = false
    filterExpanded.value = false
  }
  diagramConfigStore.setLayoutPanelExpanded(expanded)
}
```

- [ ] **Step 5: 扩展现有 3 个 toggle handler — 加入 layoutExpanded = false**

修改 `handleObjectToggle` (L151-157)，在 `if (expanded)` 块内添加 `layoutExpanded.value = false`：

```javascript
function handleObjectToggle(expanded) {
  objectExpanded.value = expanded
  if (expanded) {
    relationExpanded.value = false
    filterExpanded.value = false
    layoutExpanded.value = false
  }
}
```

修改 `handleRelationToggle` (L159-168)，在 `if (expanded)` 块内添加：

```javascript
function handleRelationToggle(expanded) {
  relationExpanded.value = expanded
  if (expanded) {
    objectExpanded.value = false
    filterExpanded.value = false
    layoutExpanded.value = false
    if (relationStale.value) {
      scheduleAutoLoad()
    }
  }
}
```

修改 `handleFilterToggle` (L170-176)，在 `if (expanded)` 块内添加：

```javascript
function handleFilterToggle(expanded) {
  filterExpanded.value = expanded
  if (expanded) {
    objectExpanded.value = false
    relationExpanded.value = false
    layoutExpanded.value = false
  }
}
```

- [ ] **Step 6: 新增 watch — hasChartData 转 false 时收起 panel + 同步 store.layoutPanelExpanded**

在 `hasChartData` computed 定义之后添加：

```javascript
// [布局设置 sidebar 整合] chart → list 切换时自动收起布局 panel
watch(hasChartData, (val) => {
  if (!val && layoutExpanded.value) {
    layoutExpanded.value = false
    diagramConfigStore.setLayoutPanelExpanded(false)
  }
})

// [布局设置 sidebar 整合] 外部修改 store.layoutPanelExpanded 时同步本地状态
watch(() => diagramConfigStore.layoutPanelExpanded, (val) => {
  if (val !== layoutExpanded.value) {
    layoutExpanded.value = val
  }
})
```

- [ ] **Step 7: 新增 LayoutControlPanel import**

在 import 区 (L79 `import CollapsiblePanel` 之后) 添加：

```javascript
import LayoutControlPanel from '@/views/AADiagramApp/components/LayoutControlPanel.vue'
```

- [ ] **Step 8: 在 template 末尾追加第 4 个 CollapsiblePanel**

在 `src/components/common/RelationScopeTree/RelationScopeTree.vue` template 中，第 3 个 CollapsiblePanel（L49-67 "过滤条件"）的 `</CollapsiblePanel>` 之后、`</div>` (L68) 之前插入：

```html

    <CollapsiblePanel
      v-if="hasChartData"
      title="布局设置"
      :default-expanded="layoutExpanded"
      :height-full="false"
      class="rst-panel-layout"
      @toggle="handleLayoutToggle"
    >
      <LayoutControlPanel
        v-if="injectedChartConfig"
        :containers="diagramConfigStore.chartDataSnapshot.containers"
        :domain-products="diagramConfigStore.chartDataSnapshot.domainProducts"
        :links="diagramConfigStore.chartDataSnapshot.links"
        :chart-type="injectedChartConfig.chartType"
        :model-value="injectedChartConfig.layoutControl"
        @update:model-value="(v) => Object.assign(injectedChartConfig.layoutControl, v)"
      />
    </CollapsiblePanel>
```

- [ ] **Step 9: 新增 CSS**

在 `<style>` 区域（若存在 scoped style）末尾添加，或在 `<style scoped>` 标签内：

```scss
.rst-panel-layout {
  &:not(.is-collapsed) {
    flex: 1 1 0;
    min-height: 200px;
  }
}
```

若组件无 `<style>` 块，则在文件末尾 `</script>` 之后添加：

```html
<style lang="scss" scoped>
.rst-panel-layout:not(.is-collapsed) {
  flex: 1 1 0;
  min-height: 200px;
}
</style>
```

- [ ] **Step 10: 验证无语法错误**

检查 IDE diagnostics 无报错。确认：
- `LayoutControlPanel` import 正确
- `useDiagramConfigStore` import 正确
- `inject` 已在 vue import 中（L72 已有 `inject`）
- template 中 `diagramConfigStore` 可访问（store 变量在 script setup 中定义）

- [ ] **Step 11: Commit**

```bash
git add src/components/common/RelationScopeTree/RelationScopeTree.vue
git commit -m "feat(scope-tree): add 4th CollapsiblePanel for layout settings with mutex"
```

---

## Task 8: 集成验证

**Files:** 无文件改动，仅验证

- [ ] **Step 1: 运行 store 单测**

Run: `npx vitest run src/stores/__tests__/diagramConfigStore.spec.js`
Expected: PASS — all tests including new chartDataSnapshot tests

- [ ] **Step 2: 全量单测回归**

Run: `npx vitest run`
Expected: PASS — 无回归失败

- [ ] **Step 3: 启动 dev server 验证**

Run: `npm run dev` (或项目对应的 dev 命令)

- [ ] **Step 4: 手动验证 — chart 视图布局 panel 出现**

1. 打开系统管理页面，选择版本
2. 点击"图表展示"切换到 chart 视图
3. 验证: sidebar 底部出现"布局设置"CollapsiblePanel
4. 验证: panel 内 LayoutControlPanel 显示分组列表（与图表数据一致）

- [ ] **Step 5: 手动验证 — 4-panel 互斥**

1. 展开"布局设置" panel → 验证其他 3 个 panel 收起
2. 展开"对象范围" panel → 验证"布局设置" panel 收起
3. 展开"关系范围" panel → 验证其他 panel 收起
4. 展开"过滤条件" panel → 验证"布局设置" panel 收起

- [ ] **Step 6: 手动验证 — list 视图 panel 隐藏**

1. 在 chart 视图下展开"布局设置" panel
2. 点击"列表展示"切到 list 视图
3. 验证: "布局设置" panel 消失
4. 切回 chart 视图 → 验证: "布局设置" panel 重新出现

- [ ] **Step 7: 手动验证 — 布局设置生效**

1. chart 视图下展开"布局设置" panel
2. 修改分组方向 (如 TB → LR)
3. 验证: 图表正确响应布局变化

- [ ] **Step 8: 手动验证 — drawer 已移除**

1. 确认右侧无 el-drawer 弹出
2. 确认 ChartMiniToolbar 无"布局设置"按钮

- [ ] **Step 9: 手动验证 — AADiagramApp LayoutSelector 不受影响**

1. 打开 AADiagramApp (老图表路由)
2. 验证 LayoutSelector 中的 LayoutControlPanel 正常工作（第二使用点未受影响）

- [ ] **Step 10: 最终 commit (如有 lint 修复)**

```bash
git add -A
git commit -m "chore: integration verification for layout settings sidebar"
```

---

## Self-Review

**1. Spec coverage:**
- §1.3 目标 (drawer → sidebar 4th panel): Task 7 ✓
- §3.1 方案 B (store snapshot): Task 1 + Task 2 ✓
- §4 数据流 (EmbeddedChartView → store → RelationScopeTree → LayoutControlPanel): Task 2 + Task 7 ✓
- §4.3 LayoutControlPanel 零改动: 无 Task 修改 LayoutControlPanel.vue ✓
- §4.3 layoutControl 不进 store (改用 provide/inject): Task 3 (provide) + Task 7 (inject) ✓
- §5 改动文件清单 8 个文件: Task 1-7 覆盖全部 ✓
- §6 4-panel 互斥: Task 7 Step 4-5 ✓
- §7 store 字段设计: Task 1 ✓
- §8 边界情况 (list 视图隐藏, chart→list 收起): Task 7 Step 6 ✓
- §9 测试策略 (store 单测): Task 1 Step 1-8 ✓
- §12 验收标准: Task 8 Step 4-9 ✓

**2. Placeholder scan:**
- 无 TODO/TBD/XXX ✓
- 每步都有完整代码 ✓
- 无 "类似 Task N" 引用 ✓

**3. Type consistency:**
- `chartDataSnapshot` 在 Task 1 定义、Task 2 写入、Task 7 读取 — 字段名一致 ✓
- `layoutPanelExpanded` 在 Task 1 定义、Task 7 读写 — 字段名一致 ✓
- `updateChartDataSnapshot` / `setLayoutPanelExpanded` — action 名一致 ✓
- `injectedChartConfig` / `injectedViewMode` — Task 7 内一致 ✓
- `handleLayoutToggle` — Task 7 定义并绑定 ✓

**4. 关键风险点:**
- Task 7 Step 1: `useDiagramConfigStore` import 路径 `@/stores/diagramConfigStore` — 需确认 @ 别名指向 src/
- Task 7 Step 8: LayoutControlPanel 的 `:chart-type` prop — 确认 ArchDataChartSwitcher L58 已有此 prop（已有 ✓）
- Task 3 Step 1: `provide` 需加入 vue import — 已在步骤中说明 ✓
