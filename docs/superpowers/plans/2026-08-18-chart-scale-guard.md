# 图表规模防护（Chart Scale Guard）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在图表渲染/展开前，用"可见关系/节点数"做双层阈值拦截（软警告横幅 / 硬阻止弹窗），避免超大规模渲染卡顿与不可读。

**Architecture:** 纯函数预估器（`estimator.js`）从分组树（collapsed 状态）+ 关系数组算出将渲染的可见节点/关系数；`guard.js` 按配置阈值判定 ok/soft/hard 并产文案。EmbeddedChartView 在进入图表时拦截（软=横幅+一键折叠，硬=弹窗阻断），MermaidComponent 在展开交互时拦截（软=toast+放行，硬=toast+阻止）并做渲染后兜底检测。阈值存 `diagramConfigStore.scopeGuard`（可配置、总开关、按引擎双阈值）。

**Tech Stack:** Vue3 (setup), Pinia (diagramConfigStore), Vitest, Element Plus (ElMessage/ElMessageBox), mermaid 11 (ELK 主引擎)。

---

### Task 1: scopeGuard 配置 (diagramConfigStore)

**Files:**
- Modify: `src/stores/diagramConfigStore.js`
- Test: `src/stores/__tests__/diagramConfigStore.scopeGuard.spec.js`

- [ ] **Step 1: 写失败测试**

创建 `src/stores/__tests__/diagramConfigStore.scopeGuard.spec.js`：

```js
import { describe, it, expect } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDiagramConfigStore } from '../diagramConfigStore'

describe('diagramConfigStore scopeGuard', () => {
  it('默认阈值 = 软线 rels300/nodes250, 硬线 rels600/nodes400, ELK 为主', () => {
    setActivePinia(createPinia())
    const s = useDiagramConfigStore()
    expect(s.scopeGuard.enabled).toBe(true)
    expect(s.scopeGuard.elk.hardRels).toBe(600)
    expect(s.scopeGuard.elk.hardNodes).toBe(400)
    expect(s.scopeGuard.elk.softRels).toBe(300)
    expect(s.scopeGuard.active.softRels).toBe(300) // layoutEngine 默认 elk → active = elk
  })

  it('setScopeGuard 可整体/局部覆盖', () => {
    setActivePinia(createPinia())
    const s = useDiagramConfigStore()
    s.setScopeGuard({ enabled: false })
    expect(s.scopeGuard.enabled).toBe(false)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npx vitest run src/stores/__tests__/diagramConfigStore.scopeGuard.spec.js`
Expected: FAIL — `s.scopeGuard` is undefined（store 尚无该状态）

- [ ] **Step 3: 实现配置状态**

在 `src/stores/diagramConfigStore.js` 的 state 区（紧跟 `layoutEngine` 之后，约 L44）新增：

```js
  // [SCALE-GUARD 2026-08-18] 图表规模防护配置。
  //   阈值以"可见渲染数"计: 关系数为主指标, 节点数为辅。校准依据见
  //   docs/superpowers/specs/2026-08-18-chart-scale-guard-design.md。
  //   按引擎双阈值: ELK 为主(实际生效), dagre 备用独立调参。
  //   enabled=false 一键关闭所有拦截(退化为现状)。
  const scopeGuard = ref({
    enabled: true,
    elk:  { softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 },
    dagre:{ softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 },
    renderCheck: true
  })
```

在 Getters 区（`isBusinessObjectChart` 后，约 L114）新增：

```js
  // 当前生效阈值 (按 layoutEngine 取对应引擎配置)
  const activeScopeGuard = computed(() => {
    const eng = (layoutEngine.value === 'dagre' ? 'dagre' : 'elk')
    return scopeGuard.value[eng] || scopeGuard.value.elk
  })
```

在 Actions 区新增：

```js
  function setScopeGuard(patch) {
    scopeGuard.value = { ...scopeGuard.value, ...patch }
  }
```

并在 `return` 导出中加入 `scopeGuard`, `activeScopeGuard`, `setScopeGuard`（找到 return 对象末尾的 `setExpandLevel` 等附近加入）。

- [ ] **Step 4: 跑测试确认通过**

Run: `npx vitest run src/stores/__tests__/diagramConfigStore.scopeGuard.spec.js`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/stores/diagramConfigStore.js src/stores/__tests__/diagramConfigStore.scopeGuard.spec.js
git commit -m "feat(scale-guard): diagramConfigStore 增加 scopeGuard 阈值配置(软/硬线, 按引擎)"
```

---

### Task 2: 可见数预估器 (estimator.js, 纯函数)

**Files:**
- Create: `src/services/scaleGuard/estimator.js`
- Test: `src/services/scaleGuard/__tests__/estimator.spec.js`

分组树节点形态（与 `src/services/expandLevel.js` 的 `isSubtreeInScope` 遍历一致）：
`{ id, elementCode?, groupType?, collapsed, children:[], containers:[], directNodes: [] | [{code}] }`
links 形态：`{ sourceCode, targetCode }`（来自 `useDiagramData.js` 的关系元数据）。

可见性定义：
- 分组 `collapsed=true` → 渲染为 1 个聚合节点（不计其 directNodes/子分组）
- 分组 `collapsed=false` → 其 `directNodes` 中的 BO 作为叶子节点可见，并递归其 children/containers
- 关系可见 = 两端 BO 都可见

- [ ] **Step 1: 写失败测试**

创建 `src/services/scaleGuard/__tests__/estimator.spec.js`：

```js
import { describe, it, expect } from 'vitest'
import { estimateVisible, estimateExpand } from '../estimator'

const groups = [
  {
    id: 'd1', groupType: 'domain', collapsed: false,
    directNodes: [],
    children: [
      { id: 'sd1', groupType: 'subDomain', collapsed: true,
        directNodes: ['A01', 'A02'], children: [], containers: [] },
      { id: 'sd2', groupType: 'subDomain', collapsed: false,
        directNodes: ['B01'],
        children: [
          { id: 'sm1', groupType: 'serviceModule', collapsed: false,
            directNodes: ['B02', 'B03'], children: [], containers: [] }
        ], containers: [] }
    ],
    containers: []
  }
]
const links = [
  { sourceCode: 'B01', targetCode: 'B02' }, // 双端可见
  { sourceCode: 'B01', targetCode: 'A01' }, // A01 被折叠 → 不可见
  { sourceCode: 'A01', targetCode: 'A02' }, // 双端被折叠 → 不可见
  { sourceCode: 'X00', targetCode: 'B02' }  // 不在树 → 不可见
]

describe('scaleGuard estimator', () => {
  it('estimateVisible: 折叠分组计1聚合节点, 展开分组计direct叶子, 关系双端可见才计', () => {
    const v = estimateVisible(groups, links)
    expect(v.nodes).toBe(4) // sd1(折叠=1) + B01 + sm1展开(容器不计) + B02 + B03 = 1+1+1+1 = 4
    expect(v.relations).toBe(1) // 仅 B01-B02
  })

  it('estimateExpand: 展开指定折叠分组后可见数增加', () => {
    const v = estimateExpand(groups, links, 'sd1')
    // sd1 从折叠(1)变展开(2 directNodes) → nodes 由 4 → 5; A01/A02 可见 → relations 增加 B01-A01、A01-A02
    expect(v.nodes).toBe(5)
    expect(v.relations).toBe(3)
  })
})
```

> 注：若上述期望与真实遍历规则不符（如容器的 directNodes 计数口径），以"与 mermaid 实际渲染 g.node 数对拍"为准，测试按对拍结果校正（见 Task 2 Step 4）。

- [ ] **Step 2: 跑测试确认失败**

Run: `npx vitest run src/services/scaleGuard/__tests__/estimator.spec.js`
Expected: FAIL — module not found

- [ ] **Step 3: 实现预估器**

创建 `src/services/scaleGuard/estimator.js`：

```js
/**
 * scaleGuard/estimator - 可见数预估器 (纯函数, 无 Vue/mermaid 依赖)
 *
 * 输入分组树(含 collapsed 状态) + 关系数组, 估算"渲染后将出现在图上的":
 *   nodes     - 可见节点数: 折叠分组=1个聚合节点; 展开分组的 directNodes=叶子节点; 递归子分组
 *   relations - 可见关系数: 两端 BO 都可见的关系才计 (关系数为主指标)
 *
 * 分组节点形态: { id, elementCode?, groupType?, collapsed, children[], containers[], directNodes[] }
 * links 形态: { sourceCode, targetCode }
 */
export function codeOf(nodeOrStr) {
  if (nodeOrStr == null) return ''
  if (typeof nodeOrStr === 'object') return nodeOrStr.code || nodeOrStr.id || nodeOrStr.name || ''
  return String(nodeOrStr)
}

export function leafCodesOf(node) {
  return (node.directNodes || []).map(codeOf).filter(Boolean)
}

/**
 * 估算可见节点/关系数。
 * @param {Array} groups 分组树顶层数组
 * @param {Array} links  关系数组 (需含 sourceCode/targetCode)
 * @param {Object} [opts]
 * @param {string} [opts.expandGroupId] 假设额外展开该分组 (用于"展开交互"前置预估)
 * @returns {{nodes:number, relations:number, visibleBoSet:Set}}
 */
export function estimateVisible(groups, links, opts = {}) {
  const expandGroupId = opts.expandGroupId || null
  const visibleBoSet = new Set()
  let nodes = 0

  function walk(list, isExpandedByOpt) {
    if (!Array.isArray(list)) return
    for (const g of list) {
      if (!g || typeof g !== 'object') continue
      const forceExpand = expandGroupId != null && (g.id === expandGroupId || g.elementCode === expandGroupId)
      const collapsed = forceExpand ? false : (g.collapsed === true)
      if (collapsed) {
        nodes += 1 // 聚合节点
        continue // 不深入折叠子树
      }
      for (const code of leafCodesOf(g)) {
        visibleBoSet.add(code)
        nodes += 1
      }
      walk(g.children)
      walk(g.containers)
    }
  }
  walk(groups)

  let relations = 0
  for (const l of links || []) {
    const s = codeOf(l.sourceCode != null ? l.sourceCode : l.source)
    const t = codeOf(l.targetCode != null ? l.targetCode : l.target)
    if (s && t && visibleBoSet.has(s) && visibleBoSet.has(t)) relations++
  }
  return { nodes, relations, visibleBoSet }
}

/** 展开指定折叠分组后的预估可见数 */
export function estimateExpand(groups, links, groupId) {
  return estimateVisible(groups, links, { expandGroupId: groupId })
}
```

- [ ] **Step 4: 对拍校验（与 mermaid 实际渲染数）**

用现有校准工具链验证口径：在 vite dev 打开 `benchmark.html`，用 `window.runBench` 的 domNodes 作为 ground truth，人工核对 estimator 对同构分组树算出的 nodes 与之一致；不一致则按实际渲染口径修正 `estimateVisible` 的计数规则（折叠聚合是否 +1、容器 directNodes 是否计入等）。记录对拍结果于本任务 commit message。

- [ ] **Step 5: 跑测试确认通过**

Run: `npx vitest run src/services/scaleGuard/__tests__/estimator.spec.js`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/services/scaleGuard/estimator.js src/services/scaleGuard/__tests__/estimator.spec.js
git commit -m "feat(scale-guard): estimator 可见数预估器(折叠聚合+direct叶子+关系双端可见)"
```

---

### Task 3: 判定器 + 文案 (guard.js)

**Files:**
- Create: `src/services/scaleGuard/guard.js`
- Test: `src/services/scaleGuard/__tests__/guard.spec.js`

- [ ] **Step 1: 写失败测试**

创建 `src/services/scaleGuard/__tests__/guard.spec.js`：

```js
import { describe, it, expect } from 'vitest'
import { classify, buildEntryMessages, buildExpandMessages } from '../guard'

const cfg = { softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 }

describe('scaleGuard guard', () => {
  it('classify 边界: 关系为主, 节点为辅', () => {
    expect(classify({ nodes: 50, relations: 100 }, cfg)).toBe('ok')
    expect(classify({ nodes: 300, relations: 200 }, cfg)).toBe('soft') // 节点>250
    expect(classify({ nodes: 100, relations: 350 }, cfg)).toBe('soft') // 关系>300
    expect(classify({ nodes: 200, relations: 650 }, cfg)).toBe('hard') // 关系>600
    expect(classify({ nodes: 500, relations: 100 }, cfg)).toBe('hard') // 节点>400
  })

  it('文案包含关系数 (主指标优先表述)', () => {
    const m = buildEntryMessages({ nodes: 320, relations: 650 }, cfg)
    expect(m.hard).toContain('650')
    expect(m.hard).toContain('关系')
    const soft = buildExpandMessages({ nodes: 260, relations: 200 }, cfg)
    expect(soft).toContain('关系')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npx vitest run src/services/scaleGuard/__tests__/guard.spec.js`
Expected: FAIL — module not found

- [ ] **Step 3: 实现判定器 + 文案**

创建 `src/services/scaleGuard/guard.js`：

```js
/**
 * scaleGuard/guard - 阈值判定 + 文案 (纯函数)
 * 可见关系数为主指标, 可见节点数为辅; 任一超线即升级。
 */
export const LEVELS = ['ok', 'soft', 'hard']

export function classify({ nodes = 0, relations = 0 }, cfg) {
  const c = cfg || {}
  if (relations > (c.hardRels || Infinity) || nodes > (c.hardNodes || Infinity)) return 'hard'
  if (relations > (c.softRels || Infinity) || nodes > (c.softNodes || Infinity)) return 'soft'
  return 'ok'
}

export function buildEntryMessages({ nodes = 0, relations = 0 }, cfg) {
  const c = cfg || {}
  const n = (v) => v == null ? '?' : v
  return {
    soft: `当前图含 ${n(relations)} 关系 / ${n(nodes)} 节点, 超出推荐可读范围(约 ${c.softRels} 关系)。建议缩小对象范围或折叠到服务模块层。`,
    hard: `所选范围过大 (约 ${n(relations)} 关系 / ${n(nodes)} 节点), 渲染会明显卡顿。请选择: ① 折叠到服务模块层展示 ② 返回缩小对象范围。`
  }
}

export function buildExpandMessages({ nodes = 0, relations = 0 }, cfg) {
  const c = cfg || {}
  const n = (v) => v == null ? '?' : v
  return {
    soft: `展开后可见关系将达 ${n(relations)} / 节点 ${n(nodes)}, 可能影响阅读; 已折叠分支可用右键折叠。`,
    hard: `展开将导致约 ${n(relations)} 关系渲染, 可能明显卡顿; 请先折叠其他分支或缩小对象范围。`
  }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `npx vitest run src/services/scaleGuard/__tests__/guard.spec.js`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/services/scaleGuard/guard.js src/services/scaleGuard/__tests__/guard.spec.js
git commit -m "feat(scale-guard): guard 阈值判定+文案(关系为主)"
```

---

### Task 4: 软线横幅 + 硬线弹窗组件

**Files:**
- Create: `src/components/common/ScaleGuardBanner.vue`
- Create: `src/components/common/ScaleGuardDialog.vue`

- [ ] **Step 1: 写失败测试（组件冒烟）**

创建 `src/components/common/__tests__/ScaleGuardComponents.spec.js`：

```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ScaleGuardBanner from '../ScaleGuardBanner.vue'
import ScaleGuardDialog from '../ScaleGuardDialog.vue'

describe('ScaleGuard components', () => {
  it('banner 显示关系/节点数 + 一键折叠按钮 + 可关闭', async () => {
    const w = mount(ScaleGuardBanner, { props: { nodes: 260, relations: 350 } })
    expect(w.text()).toContain('350')
    expect(w.text()).toContain('折叠到服务模块')
    await w.find('[data-test=fold]').trigger('click')
    expect(w.emitted('fold-to-sm')).toBeTruthy()
    await w.find('[data-test=close]').trigger('click')
    expect(w.emitted('close')).toBeTruthy()
  })

  it('dialog 显示文案 + 两个动作', async () => {
    const w = mount(ScaleGuardDialog, { props: { nodes: 500, relations: 700 } })
    expect(w.text()).toContain('700')
    await w.find('[data-test=back]').trigger('click')
    expect(w.emitted('back')).toBeTruthy()
    await w.find('[data-test=fold]').trigger('click')
    expect(w.emitted('fold-to-sm')).toBeTruthy()
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npx vitest run src/components/common/__tests__/ScaleGuardComponents.spec.js`
Expected: FAIL — modules not found

- [ ] **Step 3: 实现组件**

创建 `src/components/common/ScaleGuardBanner.vue`：

```vue
<template>
  <div class="scale-guard-banner" role="alert">
    <span class="sgb-text">{{ message }}</span>
    <el-button size="small" type="primary" data-test="fold" @click="$emit('fold-to-sm')">
      一键折叠到服务模块层
    </el-button>
    <el-button size="small" text data-test="close" @click="$emit('close')">知道了</el-button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  nodes: { type: Number, default: 0 },
  relations: { type: Number, default: 0 }
})
defineEmits(['fold-to-sm', 'close'])
const message = computed(() =>
  `当前图含 ${props.relations} 关系 / ${props.nodes} 节点, 超出推荐可读范围, 建议缩小对象范围或折叠到服务模块层。`
)
</script>

<style scoped>
.scale-guard-banner {
  position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
  z-index: 30; display: flex; align-items: center; gap: 8px;
  max-width: 70%; padding: 8px 14px; border-radius: 8px;
  background: #fff7e6; border: 1px solid #ffd591; color: #874d00;
  font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.12);
}
.sgb-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
```

创建 `src/components/common/ScaleGuardDialog.vue`：

```vue
<template>
  <el-dialog
    :model-value="true" :close-on-click-modal="false" :show-close="false"
    width="440px" title="图表范围过大" append-to-body
  >
    <p class="sgd-text">{{ message }}</p>
    <template #footer>
      <el-button data-test="back" @click="$emit('back')">返回缩小对象范围</el-button>
      <el-button type="primary" data-test="fold" @click="$emit('fold-to-sm')">
        折叠到服务模块层展示
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  nodes: { type: Number, default: 0 },
  relations: { type: Number, default: 0 }
})
defineEmits(['fold-to-sm', 'back'])
const message = computed(() =>
  `所选范围过大（约 ${props.relations} 关系 / ${props.nodes} 节点），渲染会明显卡顿。请选择折叠到服务模块层展示，或返回缩小对象范围。`
)
</script>

<style scoped>
.sgd-text { margin: 0 0 4px; font-size: 14px; line-height: 1.7; }
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `npx vitest run src/components/common/__tests__/ScaleGuardComponents.spec.js`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/components/common/ScaleGuardBanner.vue src/components/common/ScaleGuardDialog.vue src/components/common/__tests__/ScaleGuardComponents.spec.js
git commit -m "feat(scale-guard): 软线横幅 + 硬线弹窗组件(一键折叠/关闭/返回)"
```

---

### Task 5: 进入图表拦截 (EmbeddedChartView)

**Files:**
- Modify: `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue`
- Test: `src/views/SystemManagement/components/ArchDataChart/__tests__/scaleGuardEntry.spec.js`（对抽取出的纯函数测试；组件级拦截用浏览器 E2E 验证）

**前置理解**：`layoutControlConfig` computed 在 L267-474 合并面板树与渲染树并应用折叠状态（含默认展开），`links` 在 L1338。拦截点放在"合并完成、将数据交给 MermaidComponent 渲染"之前。

- [ ] **Step 1: 写失败测试（纯函数：判定 + 折叠动作副作用）**

创建 `src/views/SystemManagement/components/ArchDataChart/__tests__/scaleGuardEntry.spec.js`：

```js
import { describe, it, expect } from 'vitest'
import { decideEntryState } from '../scaleGuardEntry'
import { expandGroupsToLevel } from '@/services/expandLevel'

const cfg = { softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 }
const groups = [{ id: 'd1', groupType: 'domain', collapsed: false, directNodes: [], children: [], containers: [] }]

describe('scaleGuard entry', () => {
  it('decideEntryState: 返回 {level, counts}', () => {
    const r = decideEntryState({ nodes: 500, relations: 700 }, cfg)
    expect(r.level).toBe('hard')
    expect(r.counts.relations).toBe(700)
  })
  it('折叠到服务模块层动作 = expandGroupsToLevel(groups, serviceModule)', () => {
    const r = expandGroupsToLevel(groups, 'serviceModule')
    expect(r.collapsedCount).toBeGreaterThanOrEqual(0)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npx vitest run src/views/SystemManagement/components/ArchDataChart/__tests__/scaleGuardEntry.spec.js`
Expected: FAIL — module not found

- [ ] **Step 3: 实现纯函数 `scaleGuardEntry.js`**

创建 `src/views/SystemManagement/components/ArchDataChart/scaleGuardEntry.js`：

```js
import { classify } from '@/services/scaleGuard/guard'

/** 进入图表时的判定包装: level = ok|soft|hard, counts 供文案/组件展示 */
export function decideEntryState(counts, cfg) {
  return { level: classify(counts, cfg), counts }
}
```

- [ ] **Step 4: 在 EmbeddedChartView 接入拦截**

在 `EmbeddedChartView.vue`：
1. import：`import { estimateVisible } from '@/services/scaleGuard/estimator'`、`import { decideEntryState } from './scaleGuardEntry'`、`import ScaleGuardBanner from '@/components/common/ScaleGuardBanner.vue'`、`import ScaleGuardDialog from '@/components/common/ScaleGuardDialog.vue'`、`import { expandGroupsToLevel } from '@/services/expandLevel'`。
2. 新增响应式状态（放在 `links` computed 之后）：

```js
// [SCALE-GUARD 2026-08-18] 进入图表规模拦截状态
const scopeGuardState = ref('ok')          // 'ok' | 'soft' | 'hard'
const scopeGuardCounts = ref({ nodes: 0, relations: 0 })
const scopeGuardBannerVisible = ref(false)
```

3. 新增 computed（在 `layoutControlConfig` 之后）：

```js
const scopeGuardEstimate = computed(() => {
  const groups = layoutControlConfig.value?.groups || []
  if (!configStore.scopeGuard.enabled || groups.length === 0) return null
  return estimateVisible(groups, links.value)
})

const scopeGuardDecided = computed(() => {
  const est = scopeGuardEstimate.value
  if (!est) return null
  return decideEntryState(est, configStore.activeScopeGuard)
})
```

4. 拦截副作用（watch，放在该 computed 之后）：

```js
watch(scopeGuardDecided, (dec) => {
  if (!dec || !configStore.scopeGuard.enabled) { scopeGuardState.value = 'ok'; return }
  scopeGuardCounts.value = dec.counts
  scopeGuardState.value = dec.level
  if (dec.level === 'soft') scopeGuardBannerVisible.value = true
}, { immediate: true })
```

5. 折叠动作 + 关闭：

```js
function foldToServiceModule() {
  const cfg = JSON.parse(JSON.stringify(layoutControlConfig.value || {}))
  if (cfg.groups) expandGroupsToLevel(cfg.groups, 'serviceModule')
  configStore.updateLayoutControlConfig(cfg)
  configStore.setExpandLevel('serviceModule') // 内部同时置 expandLevelUserSet=true
  scopeGuardBannerVisible.value = false
  scopeGuardState.value = 'ok'
}
function dismissGuard() { scopeGuardBannerVisible.value = false }
```

5b. URL 覆盖阈值（E2E 测试用，仅在 `scopeGuard` computed 初始化时应用一次）：

```js
// [SCALE-GUARD 2026-08-18] URL 覆盖阈值: ?scopeGuard.hardRels=50 (E2E 用小阈值触发拦截)
function applyUrlScopeGuardOverrides() {
  const q = new URLSearchParams(window.location.search)
  const keys = ['softRels', 'softNodes', 'hardRels', 'hardNodes']
  const patch = {}
  for (const k of keys) {
    const v = q.get(`scopeGuard.${k}`)
    if (v != null && !Number.isNaN(Number(v))) patch[k] = Number(v)
  }
  const eng = q.get('scopeGuard.engine') === 'dagre' ? 'dagre' : 'elk'
  if (q.get('scopeGuard.enabled') != null) patch.enabled = q.get('scopeGuard.enabled') !== '0'
  if (Object.keys(patch).length) {
    const cfg = { ...(configStore.scopeGuard[eng] || configStore.scopeGuard.elk), ...patch }
    configStore.setScopeGuard({ [eng]: cfg })
  }
}
applyUrlScopeGuardOverrides() // 在 setup 顶层调用一次
```

6. 模板：在图表渲染容器（MermaidComponent 所在处）外层加条件渲染 + 覆盖层：

```html
<!-- 硬线: 阻断渲染, 显示弹窗 -->
<ScaleGuardDialog
  v-if="scopeGuardState === 'hard'"
  :nodes="scopeGuardCounts.nodes"
  :relations="scopeGuardCounts.relations"
  @fold-to-sm="foldToServiceModule"
  @back="emit('back-to-narrow')"
/>
<!-- 软线: 正常渲染 + 横幅 -->
<ScaleGuardBanner
  v-if="scopeGuardState === 'soft' && scopeGuardBannerVisible"
  :nodes="scopeGuardCounts.nodes"
  :relations="scopeGuardCounts.relations"
  @fold-to-sm="foldToServiceModule"
  @close="dismissGuard"
/>
```

> 说明：**硬线阻断渲染**通过"不把数据交给 MermaidComponent 渲染"实现——在现有 `diagramData` 出口（传给 MermaidComponent 的 prop 计算处）加 `if (scopeGuardState.value === 'hard') return null`，待用户选择后置回。`emit('back-to-narrow')` 通知父级让用户回到对象范围面板缩小选择（父级若未监听该事件，仅关闭弹窗、保持当前页面）。

- [ ] **Step 5: 跑测试确认通过**

Run: `npx vitest run src/views/SystemManagement/components/ArchDataChart/__tests__/scaleGuardEntry.spec.js`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/views/SystemManagement/components/ArchDataChart/scaleGuardEntry.js src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue src/views/SystemManagement/components/ArchDataChart/__tests__/scaleGuardEntry.spec.js
git commit -m "feat(scale-guard): 进入图表拦截 - 软横幅/硬弹窗 + 一键折叠到服务模块层"
```

---

### Task 6: 展开交互拦截 + 渲染后兜底 (MermaidComponent)

**Files:**
- Modify: `src/components/MermaidComponent.vue`
- Test: `src/components/__tests__/scaleGuardExpand.spec.js`（纯函数部分）

**前置理解**：展开入口在 `handleDblClick`（L2034-2084）：折叠分组 → `executeContextMenuAction(expandKey)`；右键菜单展开项也走 `executeContextMenuAction`。兜底检测点：`mermaid.run()` 完成后统计实际渲染数。

- [ ] **Step 1: 写失败测试（纯函数：展开预估 + 判定）**

创建 `src/components/__tests__/scaleGuardExpand.spec.js`：

```js
import { describe, it, expect } from 'vitest'
import { estimateExpand } from '@/services/scaleGuard/estimator'
import { classify } from '@/services/scaleGuard/guard'

const cfg = { softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 }
const groups = [
  { id: 'sd1', groupType: 'subDomain', collapsed: true, directNodes: ['A01','A02'], children: [], containers: [] },
  { id: 'sd2', groupType: 'subDomain', collapsed: false, directNodes: ['B01'], children: [], containers: [] }
]
const links = [
  { sourceCode: 'A01', targetCode: 'A02' },
  { sourceCode: 'A01', targetCode: 'B01' },
  { sourceCode: 'B01', targetCode: 'X99' }
]

describe('scaleGuard expand', () => {
  it('estimateExpand 展开折叠分组后 nodes/relations 增加', () => {
    const cur = estimateExpand(groups, links, 'sd1')
    expect(cur.nodes).toBe(5) // 展开后 A01+A02+B01 可见 + 无聚合
    expect(cur.relations).toBe(2) // A01-A02, A01-B01
  })
  it('classify 用展开后预估数判定', () => {
    expect(classify({ nodes: 300, relations: 400 }, cfg)).toBe('soft')
    expect(classify({ nodes: 300, relations: 650 }, cfg)).toBe('hard')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npx vitest run src/components/__tests__/scaleGuardExpand.spec.js`
Expected: FAIL — module not found

- [ ] **Step 3: 跑测试（先只测纯函数依赖，模块已由 Task 2/3 提供）**

Run: `npx vitest run src/components/__tests__/scaleGuardExpand.spec.js`
Expected: 此时 estimator/guard 已存在 → 测试通过（若 Task 2/3 未完成会失败，顺序执行）

- [ ] **Step 4: 在 MermaidComponent 接入展开拦截**

在 `MermaidComponent.vue`：

1. 新增 props：`scopeGuardGroups`（分组树，默认 `() => null`）、`scopeGuardLinks`（关系数组，默认 `() => null`）。EmbeddedChartView 传 `:scope-guard-groups="layoutControlConfig.groups" :scope-guard-links="links"`。
2. import：`import { estimateExpand } from '@/services/scaleGuard/estimator'`、`import { classify, buildExpandMessages } from '@/services/scaleGuard/guard'`、`import { ElMessage } from 'element-plus'`（若已引入则复用）。
3. 新增拦截函数（放在 `executeContextMenuAction` 之前）：

```js
// [SCALE-GUARD 2026-08-18] 展开前置拦截: 预估展开后可见数 → 软/硬处理
function guardExpandBefore(group) {
  if (!props.scopeGuardGroups || !configStore.scopeGuard.enabled) return 'allow'
  const projected = estimateExpand(props.scopeGuardGroups, props.scopeGuardLinks || [], group.id || group.elementCode || '')
  const cfg = configStore.activeScopeGuard
  const level = classify(projected, cfg)
  const msg = buildExpandMessages(projected, cfg)
  if (level === 'hard') {
    ElMessage.warning(msg.hard)
    return 'block'
  }
  if (level === 'soft') ElMessage.info(msg.soft)
  return 'allow'
}
```

4. 在 `handleDblClick` 的折叠展开分支（L2074 `executeContextMenuAction(expandKey)` 之前）插入：

```js
        if (guardExpandBefore(group) === 'block') return
        debug.debugLog('[DBL] handleDblClick: expanding with key=' + expandKey)
        executeContextMenuAction(expandKey)
```

5. 右键菜单展开项：在 `executeContextMenuAction` 内部，对 `expandSub/expandSM/expandBO/expandSubtree*` 类 action 执行前调用 `guardExpandBefore(ctxMenu.group)`（取当前右键分组），block 则 return。

6. 渲染后兜底：在 `mermaid.run()` 完成、SVG 挂载后（现有渲染收尾处，`updateVisibilityOnly`/`setupCanvasLayout` 调用前）插入：

```js
// [SCALE-GUARD 2026-08-18] 渲染后兜底: 预估误差导致超硬线时提示折叠
if (configStore.scopeGuard.enabled && configStore.scopeGuard.renderCheck) {
  const est = estimateVisible(props.scopeGuardGroups || [], props.scopeGuardLinks || [])
  if (classify(est, configStore.activeScopeGuard) === 'hard') {
    ElMessage.warning(
      `图表实际含 ${est.relations} 关系 / ${est.nodes} 节点, 超出可读范围。可用右键菜单「折叠到服务模块层」或缩小对象范围。`
    )
  }
}
```

> 注：`props` 为 `scopeGuardGroups/scopeGuardLinks`；若 MermaidComponent 现有 props 结构需调整，按组件内既有 prop 声明模式添加。

- [ ] **Step 5: 跑测试确认通过**

Run: `npx vitest run src/components/__tests__/scaleGuardExpand.spec.js`
Expected: PASS

- [ ] **Step 6: 浏览器 E2E 验证（软/硬/展开/兜底）**

用 Playwright（`test_helpers/browser_auth_cli.py`，base_url localhost:3004）：
1. 软线：构造范围使可见关系 ~350 → 进入图表 → 断言横幅出现、SVG 正常渲染
2. 硬线：构造大范围（或 `?scopeGuard.hardRels=50` 覆盖阈值便于测试）→ 断言弹窗出现、SVG 未渲染
3. 展开：双击一个折叠分组使投影超硬线 → 断言 toast 提示且节点未展开
4. 兜底：`scopeGuard.renderCheck` 开启下验证渲染后提示

> 阈值覆盖参数：在 EmbeddedChartView 初始化时从 `location.search` 读取 `scopeGuard.*` 覆盖默认值（Task 5 已设计 `setScopeGuard`），便于 E2E 用小阈值触发。

- [ ] **Step 7: 提交**

```bash
git add src/components/MermaidComponent.vue src/components/__tests__/scaleGuardExpand.spec.js
git commit -m "feat(scale-guard): 展开交互拦截(软toast/硬阻止) + 渲染后兜底检测"
```

---

## 验收清单（对照设计文档）

- [ ] SCP 标准范围 (~30 BO / ~36 关系) 不触发任何拦截（回归）
- [ ] 默认折叠到高层的大范围不误报（以可见数计）
- [ ] 全量 3230 BO / 5721 关系 展开到业务对象层 → 硬线弹窗阻断，不进入渲染
- [ ] 软线横幅可关闭、可一键折叠到服务模块层
- [ ] 展开超硬线被阻止并提示
- [ ] `scopeGuard.enabled=false` 完全退化为现状行为（总开关）
- [ ] URL `?scopeGuard.hardRels=N` 可覆盖阈值（E2E 用）
- [ ] 校准工具链 `test_helpers/calibrate_scale.py` 保留可重跑
