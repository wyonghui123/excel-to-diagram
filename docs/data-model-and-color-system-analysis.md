# 数据模型与颜色系统深度分析报告

> 更新日期：2026-04-16  
> 基于：代码现状 + 历史分析文档 + 2026-04-16 修复实践  
> 关联文档：`unified-model-analysis.md`、`unified-model-refactor-plan.md`、`数据模型文档.md`、`架构设计文档.md`

---

## 一、问题溯源：今天修复的三个 Bug

### 1.1 Bug 清单

| # | 问题 | 根因 | 修复文件 |
|---|------|------|---------|
| 1 | 未选关系时，类型/配置步骤的关系统计有值 | `filteredRelations.value.length \|\| totalStats.objectRelations` 回退到总数 | `useDiagramData.js` |
| 2 | 业务对象图在服务模块分组下 Legend 显示编码而非名称 | `groupKey = node.serviceModule \|\| node.serviceModuleName` 优先取编码 | `useSvgProcessor.js` |
| 3 | 服务模块图没有 Legend | ① SM Syntax 不返回 nodeColorMappings ② MermaidComponent 不提取 ③ groupKey 计算缺少 serviceModule 分支 | `useServiceModuleSyntax.js`、`MermaidComponent.vue`、`useSvgProcessor.js` |

### 1.2 根因共性

**三个 Bug 的共同根因是：BO 图和 SM 图的数据管线独立演化，修改一处时遗漏另一处。**

具体表现为：
- SM 图的 Syntax 层没有像 BO 图一样返回 `nodeColorMappings`
- Legend 构建函数只考虑了 BO 图的节点结构（有 `serviceModule`/`serviceModuleName` 字段），没考虑 SM 图的节点结构（只有 `name`）
- 统计计算中，SM 图和 BO 图的关系数量取值逻辑不一致

---

## 二、数据管线全景图

### 2.1 两条并行的数据管线

```
                         ┌─────────────────────────────────────┐
                         │        diagramConfigStore            │
                         │  colorGroupBy, colorScheme,          │
                         │  centerScope, centerScopeHighlight   │
                         └──────────┬──────────────┬───────────┘
                                    │              │
                     ┌──────────────▼──────┐  ┌───▼────────────────┐
                     │   BO 数据管线        │  │  SM 数据管线        │
                     └──────────────┬──────┘  └───┬────────────────┘
                                    │              │
┌───────────────────────────────────▼──────────────▼───────────────────────────┐
│                         useDiagramData.js                                    │
│                                                                              │
│  ┌─────────────────────────┐    ┌──────────────────────────────┐             │
│  │ buildDiagramData()      │    │ buildServiceModuleDiagramData()│            │
│  │                         │    │                               │            │
│  │ 节点无 color 字段       │    │ 节点有 color 字段             │            │
│  │ isCenter 来自上游       │    │ isCenter 在此计算             │            │
│  │ 返回 centerScope 数组   │    │ 返回 centerScopeHighlight    │            │
│  └──────────┬──────────────┘    └──────────┬───────────────────┘            │
│             │                              │                                 │
│  ┌──────────▼──────────────┐    ┌──────────▼───────────────────┐            │
│  │ ColorCalculator.compute │    │ ColorCalculator.compute       │            │
│  │ (统一渲染器路径)         │    │ (统一渲染器路径)              │            │
│  │ 传入 serviceModule 字段  │    │ ⚠️ 未传入 serviceModule 字段  │            │
│  └──────────┬──────────────┘    └──────────┬───────────────────┘            │
└─────────────┼──────────────────────────────┼──────────────────────────────┘
              │                              │
┌─────────────▼──────────────────────────────▼──────────────────────────────┐
│                         MermaidComponent.vue                               │
│                                                                            │
│  ┌──────────────────────────┐    ┌────────────────────────────┐            │
│  │ useBusinessObjectSyntax  │    │ useServiceModuleSyntax     │            │
│  │                          │    │                            │            │
│  │ 自行计算颜色             │    │ 直接读 node.color          │            │
│  │ 自行判断 isCenter        │    │ isCenter 已预计算          │            │
│  │ ✅ 返回 nodeColorMappings│    │ ✅ 返回 nodeColorMappings  │            │
│  │    (nodeId=N1,N2...)     │    │    (nodeId=sm.code)        │            │
│  └──────────┬───────────────┘    └──────────┬─────────────────┘            │
│             │                               │                              │
│             └───────────┬───────────────────┘                              │
│                         │                                                  │
│  ┌──────────────────────▼──────────────────────────────┐                   │
│  │              useSvgProcessor.js                      │                   │
│  │                                                      │                   │
│  │  processSvg() → buildColorLegendData()               │                   │
│  │  通用 Legend 构建逻辑（需兼容两种节点结构）            │                   │
│  └──────────────────────────────────────────────────────┘                   │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 关键差异对比表

| 维度 | 业务对象图 (BO) | 服务模块图 (SM) | 影响 |
|------|:---:|:---:|------|
| **节点 ID** | `bo.name` | `sm.code` | Legend 匹配逻辑不同 |
| **节点 color** | ❌ 无（语法层计算） | ✅ 有（构建层计算） | Legend 取色路径不同 |
| **serviceModule 字段** | ✅ 有（编码） | ❌ 无 | groupKey 计算需回退 |
| **serviceModuleName 字段** | ✅ 有（名称） | ❌ 无 | groupKey 计算需回退 |
| **isCenter 计算** | 上游 `bo.isCenter` | `centerScopeHighlight && codes.has(sm.code)` | 判断时机不同 |
| **颜色计算时机** | 语法层（useBusinessObjectSyntax） | 构建层（serviceModuleDiagramBuilder） | 修改颜色需改不同位置 |
| **centerScope 传递** | 作为数组传递 | 不传递（用 centerServiceModuleCodes） | 中心范围判断方式不同 |
| **nodeColorMappings.nodeId** | `N1, N2...`（自动递增） | `sm.code`（直接用编码） | SVG 元素匹配方式不同 |

---

## 三、颜色系统：五套定义、四种 groupKey 策略

### 3.1 COLOR_SCHEMES 定义重复情况

| # | 文件 | 颜色数量 | default 方案首色 | 与标准版一致？ |
|---|------|---------|----------------|:---:|
| 1 | `ColorCalculator.js` | 8 | `#1890FF` | ❌ 只有 8 色 |
| 2 | `useMermaidColors.js` | 12 | `#1890FF` | ✅ 标准版 |
| 3 | `serviceModuleDiagramBuilder.js` | 12 | `#1890FF` | ✅ 标准版 |
| 4 | `ServiceModuleConfig.vue` | 30 | `#1890FF` | ❌ 扩展到 30 色 |
| 5 | `CenterDomainSelect.vue` | 30 | `#1890FF` | ❌ 扩展到 30 色 |
| 6 | `StepConfig.vue` | 12 | `#1890FF` | ✅ 标准版 |

**问题**：配置页面（30色）与渲染器（8-12色）使用不同的色板，导致：
- 配置页面颜色预览 ≠ 最终图表渲染颜色
- ColorCalculator（8色）分配完颜色后，第9个分组就循环回第一个色
- 其他地方（12色）可以支持到12个分组不循环

### 3.2 groupKey 计算策略不一致

当 `colorGroupBy === 'serviceModule'` 时：

| # | 位置 | groupKey 取值 | 说明 |
|---|------|-------------|------|
| 1 | `ColorCalculator.js:20` | `node.serviceModule` | 取编码（如 `PR`） |
| 2 | `useMermaidColors.js:32` | `moduleInfo.serviceModuleName \|\| moduleInfo.serviceModule` | 优先取名称 |
| 3 | `useSvgProcessor.js:185` | `node.serviceModuleName \|\| node.serviceModule \|\| node.name` | 三级回退 |
| 4 | `serviceModuleDiagramBuilder.js:190` | `sm.name` | 直接取名称 |

**影响**：
- 配置页面按"名称"分组显示颜色分配
- ColorCalculator 按"编码"分组分配颜色
- Legend 按"名称 > 编码 > name"回退取值
- **同一分组在不同层可能有不同的 key**，导致颜色对不上

### 3.3 颜色计算时机差异

```
BO 图颜色计算路径（3层）：
  diagramDataBuilder → 节点无 color
      ↓
  ColorCalculator.compute → 计算颜色（统一渲染器路径）
      ↓
  useBusinessObjectSyntax → 重新计算颜色（主要路径，覆盖 ColorCalculator 结果）
      ↓
  nodeColorMappings → 传给 Legend

SM 图颜色计算路径（2层）：
  serviceModuleDiagramBuilder → 节点有 color（在此计算）
      ↓
  ColorCalculator.compute → 计算颜色（统一渲染器路径，但未传入 serviceModule 字段！）
      ↓
  useServiceModuleSyntax → 直接读 node.color
      ↓
  nodeColorMappings → 传给 Legend
```

**问题**：
1. BO 图的颜色在语法层重新计算，ColorCalculator 的结果被覆盖 → ColorCalculator 对 BO 图实际无效
2. SM 图的 ColorCalculator 未传入 `serviceModule` 字段 → `colorGroupBy='serviceModule'` 时无法正确分组
3. 两条路径最终颜色可能不一致

---

## 四、isCenter 判断逻辑不一致

| 位置 | 判断方式 | 依赖的数据 |
|------|---------|-----------|
| `diagramDataBuilder.js` | `bo.isCenter \|\| false` | 上游 `filteredBusinessObjects` 的 `isCenter` |
| `serviceModuleDiagramBuilder.js` | `centerScopeHighlight && finalCenterServiceModuleCodes.has(sm.code)` | `centerServiceModuleCodes` + `centerScopeHighlight` |
| `ColorCalculator.js` | `centerScopeHighlight && node.isCenter` | 节点上的 `isCenter` + `centerScopeHighlight` |
| `useBusinessObjectSyntax.js` | `centerScopeHighlight !== false && centerScopeBoCodes.includes(nodeCode)` | `data.centerScope` 数组 |
| `useSvgProcessor.js (Legend)` | `centerScopeHighlight && node.isCenter` | 节点上的 `isCenter` + `centerScopeHighlight` |

**关键差异**：

1. **BO 图语法层**：用 `centerScopeBoCodes.includes(nodeCode)` 判断，不依赖 `node.isCenter`
2. **BO 图 Legend 层**：用 `node.isCenter` 判断
3. **SM 图**：`isCenter` 在构建层就计算好了，后续只读

**潜在问题**：如果 `centerScopeBoCodes` 和 `node.isCenter` 不一致（比如 `centerScopeHighlight` 为 false 但 `isCenter` 仍为 true），Legend 和实际着色会不匹配。

---

## 五、nodeColorMappings 结构差异

### 5.1 当前结构

**BO 图**（useBusinessObjectSyntax.js）：
```javascript
{
  nodeId: 'N1',           // Mermaid 自动递增 ID
  color: '#1890FF',       // 语法层运行时计算
  nodeCode: 'BO_001',     // 业务对象编码
  nodeName: '用户'         // originalName || name
}
```

**SM 图**（useServiceModuleSyntax.js）：
```javascript
{
  nodeId: 'PR',           // 直接用 sm.code
  color: '#1890FF',       // 直接读 node.color
  nodeCode: 'PR',         // 服务模块编码
  nodeName: '采购供应'     // name
}
```

### 5.2 Legend 中如何使用

```javascript
// useSvgProcessor.js buildColorLegendData
const mapping = nodeColorMappings.find(m => m.nodeCode === node.code)
if (mapping) {
  color = mapping.color
}
```

**问题**：
- `nodeId` 在 BO 图中是 `N1`（Mermaid 内部 ID），在 SM 图中是 `sm.code`
- Legend 只用 `nodeCode` 匹配，不用 `nodeId`，所以当前能工作
- 但 `nodeId` 的不一致会在未来需要通过 `nodeId` 操作 SVG 元素时造成问题

---

## 六、配置组件差异

| 特性 | CenterDomainSelect (BO) | ServiceModuleConfig (SM) |
|------|:---:|:---:|
| 中心范围传入方式 | `centerScopeBoCodes` (Set) | `centerScope` (Array) |
| isCenter 判断 | `centerScopeBoCodes.has(boCode)` | `centerBoCodes.has(groupName \|\| groupCode)` |
| centerScopeMarkers | ✅ 使用 | ❌ 不使用 |
| 颜色方案定义 | 30色（扩展版） | 30色（扩展版） |
| 颜色分配逻辑 | 按业务对象编码检查 | 按服务模块名称/编码检查 |
| 区分中心范围时 | 过滤掉完全在中心范围内的分组 | 过滤掉完全在中心范围内的分组 |

**核心问题**：两个组件有大量重复逻辑（颜色方案定义、颜色分配、中心范围过滤），但细节不同，导致维护成本高。

---

## 七、统计系统数据模型

### 7.1 当前统计计算逻辑

```
步骤0（导入）: displayStats.import = stats.value（总数）
步骤1（中心）: displayStats.center = calculateStatsForBoCodes(centerBoCodes)
步骤2（关系）: displayStats.incremental = totalStats - centerStats
步骤3（类型）: displayStats.total = calculateStatsForBoCodes(center ∪ external)
步骤4（配置）: displayStats.config = 根据 chartType 区分
```

### 7.2 关系统计修复

**修复前**：`filteredRelations.value.length || totalStats.objectRelations`
- 当 `filteredRelations` 为空时回退到总数，导致未选关系时仍显示关系数量

**修复后**：`filteredRelations.value.length` 或 `filteredRelations.value.length || 0`
- 不再回退，未选关系时正确显示 0

### 7.3 配置步骤默认选择规则

**新增逻辑**（index.vue watch）：
```javascript
watch(currentStep, (newStep) => {
  if (newStep === 4) {
    const hasSelectedRelations = selectedRelationNodeIds.value?.length > 0
    if (!hasSelectedRelations) {
      configStore.updateCenterScopeHighlight(false)
    }
  }
})
```

**设计意图**：当只有中心范围没有关系时，区分中心范围没有意义（所有节点都是中心），自动关闭。

---

## 八、统一方向思考

### 8.1 与现有重构计划的关系

现有 `unified-model-refactor-plan.md` 侧重于 **分组模型（GroupModel）层面的统一**，解决 `containers` vs `children` 的问题。

本报告侧重于 **颜色系统和数据结构的统一**，解决颜色计算、Legend、isCenter 判断的问题。

两者互补，不冲突。

### 8.2 建议的统一方向

#### P0：统一 COLOR_SCHEMES 定义（影响用户可见的颜色不一致）

**现状**：6 处定义，3 种色板（8色/12色/30色）

**目标**：1 处定义，1 种色板

**方案**：
```
src/constants/colorSchemes.js  ← 唯一定义（30色扩展版，向后兼容）
    ├── ColorCalculator.js      ← 引用
    ├── useMermaidColors.js     ← 引用
    ├── serviceModuleDiagramBuilder.js ← 引用
    ├── ServiceModuleConfig.vue ← 引用
    └── CenterDomainSelect.vue  ← 引用
```

**风险**：低。纯常量提取，不改变逻辑。

#### P0：统一 groupKey 计算逻辑（影响 Legend 和颜色分配）

**现状**：4 种策略

**目标**：1 个工具函数

**方案**：
```javascript
// src/utils/colorUtils.js
export function getGroupKey(node, colorGroupBy) {
  switch (colorGroupBy) {
    case 'subDomain': return node.subDomain
    case 'serviceModule': return node.serviceModuleName || node.serviceModule || node.name
    default: return node.domain
  }
}
```

所有位置统一调用此函数。

**风险**：低。纯函数提取，需确保所有调用点的 node 结构兼容。

#### P1：统一 isCenter 计算逻辑（影响 Legend 和中心范围着色）

**现状**：5 种判断方式

**目标**：在数据构建层统一计算 `isCenter`，后续只读

**方案**：
```
数据构建层 → 计算 isCenter → 写入 node.isCenter
    ↓
ColorCalculator → 读 node.isCenter（不再自行判断）
    ↓
语法生成 → 读 node.isCenter（不再自行判断）
    ↓
Legend → 读 node.isCenter
```

**风险**：中。需要修改 BO 图语法层的 isCenter 判断逻辑，可能影响现有着色行为。

#### P1：统一节点数据模型（降低维护成本）

**现状**：BO 节点无 color，SM 节点有 color；BO 用 name 做 ID，SM 用 code 做 ID

**目标**：统一节点结构

**方案**：
```javascript
// 统一节点结构
{
  id: String,                // 统一用 code
  code: String,
  name: String,
  domain: String,
  subDomain: String,
  serviceModule: String,     // SM 节点 = 自身 code
  serviceModuleName: String, // SM 节点 = 自身 name
  color: String,             // 统一在构建层计算
  isCenter: Boolean,         // 统一在构建层计算
}
```

**关键变化**：
- `id` 统一用 `code`（消除 BO 用 `name`、SM 用 `code` 的差异）
- SM 节点也带上 `serviceModule` 和 `serviceModuleName`（= 自身的编码和名称）
- `color` 统一在数据构建层计算（消除 BO 在语法层计算、SM 在构建层计算的差异）

**风险**：高。需要修改 BO 图的 ID 策略，可能影响 Mermaid 语法生成和 SVG 元素匹配。

#### P2：统一 nodeColorMappings 结构（改善可维护性）

**现状**：BO 用 `N1,N2...`，SM 用 `sm.code`

**目标**：统一 `nodeId` 的取值策略

**方案**：统一用 `code` 作为 `nodeId`

**风险**：中。需要修改 BO 图的 Mermaid 语法生成逻辑。

#### P2：合并配置组件（减少重复代码）

**现状**：CenterDomainSelect 和 ServiceModuleConfig 有大量重复逻辑

**目标**：抽取通用的 `ColorConfigPanel.vue`

**风险**：低。纯 UI 层重构，不影响数据逻辑。

### 8.3 实施路线图

```
Phase 0（已完成）：修复当前 Bug
  ✅ 关系统计回退问题
  ✅ Legend groupKey 计算
  ✅ SM 图 nodeColorMappings 缺失

Phase 1（P0，低风险）：提取常量和工具函数
  ├── 提取 COLOR_SCHEMES 到 constants/colorSchemes.js
  ├── 提取 getGroupKey() 到 utils/colorUtils.js
  └── 全局替换引用

Phase 2（P1，中风险）：统一 isCenter 计算
  ├── 修改 diagramDataBuilder 在构建层计算 isCenter
  ├── 修改 useBusinessObjectSyntax 使用 node.isCenter
  └── 验证 BO 图和 SM 图的中心范围着色一致

Phase 3（P1，高风险）：统一节点数据模型
  ├── BO 图 id 改为 code
  ├── SM 图节点添加 serviceModule/serviceModuleName 字段
  ├── 颜色统一在构建层计算
  └── 全面回归测试

Phase 4（P2，低风险）：UI 层统一
  ├── 合并配置组件
  └── 统一 nodeColorMappings 结构
```

---

## 九、与 unified-model-refactor-plan 的关系

| 维度 | unified-model-refactor-plan | 本报告 |
|------|---------------------------|--------|
| **关注层** | GroupModel 层（containers vs children） | 颜色系统 + 数据结构 |
| **核心问题** | SM 图的终端节点在 children 而非 containers | 颜色计算、Legend、isCenter 不一致 |
| **Phase 1** | 修改 architectureProcessor（1行） | 提取 COLOR_SCHEMES + getGroupKey |
| **风险** | 低-中 | 低-高（按 Phase 递增） |
| **是否冲突** | ❌ 不冲突 | ❌ 不冲突 |

**建议**：两个重构计划可以并行执行。refactor-plan 的 Phase 1（修改 architectureProcessor）与本报告的 Phase 1（提取常量）互不影响。

---

## 十、补充发现：历史分析中的深层问题

> 以下内容来自历史分析文档的综合，发现我之前的分析遗漏了以下关键问题。

### 10.1 containers vs children 的双重含义问题

这是 `unified-model-analysis.md` 中指出的核心架构问题，与颜色系统问题相互交织。

#### 问题描述

`containers` 和 `children` 在系统中承担了不同的职责，但职责划分不一致：

| 职责 | containers | children |
|------|-----------|----------|
| **控制面板显示** | ✅ 用于渲染可拖拽的节点列表 | ❌ 不用于显示 |
| **控制面板分组** | ❌ 不用于分组 | ✅ 用于递归渲染分组树 |
| **合并用户配置** | ❌ 不被合并 | ✅ 被合并 |
| **图表渲染（统一渲染器）** | ❌ 不使用 | ✅ 从 children 取终端节点 |
| **图表渲染（旧渲染器）** | ✅ 从 containers 取终端节点 | ❌ 不使用 |

#### 具体表现

| 图表类型 | 终端节点位置 | 控制面板是否可见 | 渲染器来源 |
|---------|------------|----------------|----------|
| **业务对象图** | `containers` | ✅ 可见 | `toMermaidConfig` 从 containers |
| **服务模块图** | `children` | ❌ 不可见（因为 SM 在 children 而非 containers） | `UnifiedRenderer` 从 children |

#### 根本原因

`handleServiceModuleAutoGroup` 把服务模块添加到 `children`（用于图表渲染），但 `GroupItem.vue` 从 `containers` 渲染可拖拽列表，导致：
- 控制面板看不到服务模块节点（SM 的 containers 为空）
- 用户无法在控制面板中管理服务模块

#### 与颜色系统的关联

当统一渲染器（UnifiedRenderer）被启用时：
- BO 图：`containers` 中的 BO 节点会被 ColorCalculator 处理颜色
- SM 图：`children` 中的 SM 节点会被 ColorCalculator 处理颜色

但 ColorCalculator 对 SM 图的 `colorGroupBy='serviceModule'` 分组处理不正确（未传入 serviceModule 字段），导致颜色分配出问题。

### 10.2 两套渲染路径的并行问题

#### 架构设计文档中的 Feature Flag

```javascript
// diagramConfigStore.useUnifiedRenderer
// true  → 使用 UnifiedRenderer + enrichGroupModel + ColorCalculator
// false → 使用旧 diagramDataBuilder / serviceModuleDiagramBuilder 路径
```

#### 现状

根据 `unified-model-analysis.md`，存在两套并行路径：

**路径1：统一渲染路径（UnifiedRenderer）**
```
GroupModel.buildIndex → GroupModel.fromUserConfig → enrichGroupModel
    → ColorCalculator.compute → UnifiedRenderer.render → Mermaid Code
```

**路径2：旧渲染路径（diagramDataBuilder / serviceModuleDiagramBuilder）**
```
useDiagramData.js → diagramDataBuilder.buildDiagramData (BO)
                               或
                → serviceModuleDiagramBuilder.buildServiceModuleDiagramData (SM)
    → useBusinessObjectSyntax / useServiceModuleSyntax.generateMermaidCode
```

#### 问题

1. **代码复杂度增加**：两套路径需要同时理解
2. **行为可能不一致**：两套路径的颜色计算逻辑不同
3. **维护成本高**：修改一处容易遗漏另一处
4. **unified-model-refactor-plan.md** 指出：UnifiedRenderer 未生效（缺少 80%+ 渲染功能）

### 10.3 数据源差异问题

#### unified-model-analysis.md 的发现

| 数据流 | 业务对象图 | 服务模块图 |
|--------|-----------|-----------|
| **控制面板数据源** | `props.containers` | `props.domainProducts` |
| **图表渲染数据源** | `buildBusinessObjectGroupModel` | `buildServiceModuleGroupModel` |
| **数据格式** | 扁平容器 + 嵌套 nodes | 层级 domainProducts |

#### 问题

两套数据源意味着：
- 数据验证逻辑可能不同
- 过滤逻辑可能不同
- 颜色分配逻辑可能不同

### 10.4 节点 ID 策略不一致（深层问题）

#### 问题描述

- BO 图节点 ID：`bo.name`（使用业务对象名称）
- SM 图节点 ID：`sm.code`（使用服务模块编码）

这导致：
1. Mermaid 语法中的节点 ID 含义不同
2. SVG 元素 ID 不同（BO 用 N1,N2...，SM 用 sm.code）
3. 交互处理逻辑可能需要区分处理

#### unified-model-analysis.md 建议

统一用 `code` 作为 ID，消除 BO 用 `name`、SM 用 `code` 的差异。

### 10.5 颜色方案定义不一致（深层问题）

#### 架构设计文档中的定义

在 `架构设计文档.md` 第 853-866 行定义了 **7 种配色方案，每种 8 色**：

```javascript
const COLOR_SCHEMES = {
  default: ['#1890FF', '#2FC25B', '#FACC14', '#223273', '#8543E0', '#13C2C2', '#3436C7', '#F04864'],
  vibrant: ['#5B8FF9', '#5AD8A6', '#5D7092', '#F6BD16', '#E86452', '#6DC8EC', '#945FB9', '#FF9845'],
  pastel:  ['#A0C4FF', '#B5EAD7', '#FFDAC1', '#C7CEEA', '#E2F0CB', '#FFB7B2', '#FFFFD8', '#D5A6BD'],
  warm:    ['#FF6B6B', '#FFA07A', '#FFD93D', '#6BCB77', '#4D96FF', '#9B59B6', '#E17055', '#00B894'],
  cool:    ['#74B9FF', '#81ECEC', '#55EFC4', '#A29BFE', '#DFE6E9', '#00CEC9', '#6C5CE7', '#0984E3'],
  business:['#2C3E50', '#3498DB', '#1ABC9C', '#E67E22', '#9B59B6', '#E74C3C', '#F39C12', '#27AE60'],
  nature:  ['#2D6A4F', '#40916C', '#52B788', '#74C69D', '#95D5B2', '#B7E4C7', '#D8F3DC', '#1B4332']
}
```

#### 实际代码中的情况

| 位置 | 颜色数量 | 来源 |
|------|---------|------|
| ColorCalculator.js | 8 色 | 与架构文档一致 |
| useMermaidColors.js | 12 色 | 扩展版 |
| serviceModuleDiagramBuilder.js | 12 色 | 扩展版 |
| ServiceModuleConfig.vue | 30 色 | 扩展版 |
| CenterDomainSelect.vue | 30 色 | 扩展版 |
| StepConfig.vue | 12 色 | 扩展版 |

#### 问题

1. **架构文档与实际代码不一致**：文档说 7 种 8 色，实际代码中有 12 色和 30 色版本
2. **配置页面与渲染器不一致**：配置页面 30 色 vs 渲染器 8-12 色
3. **统一渲染器可能使用错误版本**：如果 ColorCalculator 被使用，会用 8 色版本

### 10.6 统一的 refactor 路线图

根据 `unified-model-refactor-plan.md` 和本报告，提出综合的重构路线图：

#### Phase 0：Bug 修复（已完成 ✅）
- ✅ 关系统计回退问题
- ✅ Legend groupKey 计算
- ✅ SM 图 nodeColorMappings 缺失

#### Phase 1：containers vs children 统一（来自 unified-model-refactor-plan）
- [ ] 修改 `architectureProcessor.js`：SM 的终端节点应放入 `containers` 而非 `children`
- [ ] 清理 `GroupModel.js` 中对 `containers` 的处理
- [ ] 验证 SM 图的控制面板显示正确

#### Phase 2：统一 COLOR_SCHEMES（低风险）
- [ ] 提取 `COLOR_SCHEMES` 到 `src/constants/colorSchemes.js`
- [ ] 统一为 30 色扩展版
- [ ] 全局替换所有引用

#### Phase 3：统一 groupKey 计算（低风险）
- [ ] 提取 `getGroupKey()` 到 `src/utils/colorUtils.js`
- [ ] 全局替换所有引用

#### Phase 4：统一渲染路径（中高风险）
- [ ] 评估 UnifiedRenderer 是否完整（当前可能缺少 80% 功能）
- [ ] 决定保留哪套渲染路径
- [ ] 清理另一套渲染路径的死代码

#### Phase 5：统一节点数据模型（高风险）
- [ ] 统一节点 ID 策略（都用 code）
- [ ] 统一 `isCenter` 计算时机（都在构建层）
- [ ] 统一 `color` 计算时机（都在构建层）
- [ ] 统一 `nodeColorMappings` 结构

#### Phase 6：UI 层统一（低风险）
- [ ] 合并 CenterDomainSelect 和 ServiceModuleConfig
- [ ] 抽取通用的 ColorConfigPanel.vue

### 10.7 关键代码位置索引（补充）

#### containers vs children 相关

| 功能 | 文件 | 行号 |
|------|------|------|
| handleServiceModuleAutoGroup | `LayoutControlPanel.vue` | - |
| handleBusinessObjectAutoGroup | `LayoutControlPanel.vue` | - |
| GroupItem containers 渲染 | `GroupItem.vue` | L314-L318 |
| GroupItem children 递归 | `GroupItem.vue` | L320-L328 |
| buildServiceModuleGroupModel | `architectureProcessor.js` | - |
| toMermaidConfig containers 处理 | `GroupModel.js` | L670-L688 |
| UnifiedRenderer children 处理 | `UnifiedRenderer.js` | L261-L308 |

#### 两套渲染路径相关

| 功能 | 文件 | 行号 |
|------|------|------|
| useUnifiedRenderer Feature Flag | `diagramConfigStore.js` | - |
| 统一渲染路径调用 | `useDiagramData.js` | L1167-1213 (SM) |
| 统一渲染路径调用 | `useDiagramData.js` | L1278-1328 (BO) |
| UnifiedRenderer.render | `UnifiedRenderer.js` | L260-L308 |
| 旧渲染路径（SM） | `serviceModuleDiagramBuilder.js` | - |
| 旧渲染路径（BO） | `diagramDataBuilder.js` | - |

#### 数据源相关

| 功能 | 文件 | 行号 |
|------|------|------|
| domainProducts 构建 | `DataPreview.vue` | - |
| containers 构建（BO） | `handleBusinessObjectAutoGroup` | - |
| domainProducts 结构 | `数据模型文档.md` | L56-88 |

---

## 十一、附录：关键代码位置索引

### 11.1 颜色相关

| 功能 | 文件 | 行号 |
|------|------|------|
| COLOR_SCHEMES 定义（8色） | `services/groupModel/ColorCalculator.js` | L1-L9 |
| COLOR_SCHEMES 定义（12色） | `composables/useMermaid/color/useMermaidColors.js` | L1-L9 |
| COLOR_SCHEMES 定义（12色） | `services/serviceModuleDiagramBuilder.js` | L27-L35 |
| COLOR_SCHEMES 定义（30色） | `components/ServiceModuleConfig.vue` | L134-L170 |
| COLOR_SCHEMES 定义（30色） | `components/CenterDomainSelect.vue` | 内联 |
| groupKey 计算 | `services/groupModel/ColorCalculator.js` | L19-L21 |
| groupKey 计算 | `composables/useMermaid/color/useMermaidColors.js` | L31-L37 |
| groupKey 计算 | `composables/useMermaid/renderer/useSvgProcessor.js` | L181-L188 |
| groupKey 计算 | `services/serviceModuleDiagramBuilder.js` | L187-L191 |
| 颜色计算（BO） | `composables/useMermaid/syntax/useBusinessObjectSyntax.js` | L621-L655 |
| 颜色计算（SM） | `services/serviceModuleDiagramBuilder.js` | L182-L253 |
| nodeColorMappings（BO） | `composables/useMermaid/syntax/useBusinessObjectSyntax.js` | L820-L828, L963-L970 |
| nodeColorMappings（SM） | `composables/useMermaid/syntax/useServiceModuleSyntax.js` | L422-L430 |
| nodeColorMappings 提取 | `components/MermaidComponent.vue` | L189-L200 |
| Legend 构建 | `composables/useMermaid/renderer/useSvgProcessor.js` | L171-L218 |

### 11.2 isCenter 相关

| 功能 | 文件 | 行号 |
|------|------|------|
| BO isCenter 设置 | `services/diagramDataBuilder.js` | L43 |
| SM isCenter 计算 | `services/serviceModuleDiagramBuilder.js` | L225 |
| ColorCalculator isCenter | `services/groupModel/ColorCalculator.js` | L34 |
| BO 语法层 isCenter | `composables/useMermaid/syntax/useBusinessObjectSyntax.js` | centerScopeBoCodes.includes |
| Legend isCenter | `composables/useMermaid/renderer/useSvgProcessor.js` | L192 |

### 11.3 统计相关

| 功能 | 文件 | 行号 |
|------|------|------|
| filteredRelations | `composables/useDiagramData.js` | L358-L360 |
| incrementalStats | `composables/useDiagramData.js` | L378-L384 |
| displayStats | `composables/useDiagramData.js` | L797-L829 |
| centerScopeHighlight 默认规则 | `views/AADiagramApp/index.vue` | L278-L286 |

### 11.4 containers vs children 相关

| 功能 | 文件 | 行号 |
|------|------|------|
| SM 终端节点位置 | `architectureProcessor.js` | L154-L161 |
| BO 终端节点位置 | `handleBusinessObjectAutoGroup` | L69-L76 |
| containers 渲染 | `GroupItem.vue` | L314-L318 |
| children 递归 | `GroupItem.vue` | L320-L328 |
| containers 合并 | `GroupModel.js` | L197-199 |
| containers toMermaidConfig | `GroupModel.js` | L670-L688 |

### 11.5 两套渲染路径相关

| 功能 | 文件 | 行号 |
|------|------|------|
| useUnifiedRenderer | `diagramConfigStore.js` | - |
| SM 统一渲染调用 | `useDiagramData.js` | L1167-1213 |
| BO 统一渲染调用 | `useDiagramData.js` | L1278-1328 |
| UnifiedRenderer.render | `UnifiedRenderer.js` | L260-L308 |
| 旧 SM 渲染路径 | `serviceModuleDiagramBuilder.js` | 全文 |
| 旧 BO 渲染路径 | `diagramDataBuilder.js` | 全文 |

---

*文档更新时间：2026-04-16（第二版）*
*历史文档：`unified-model-analysis.md`、`service-module-diagram-analysis.md`、`数据模型文档.md`、`架构设计文档.md`、`unified-model-refactor-plan.md`*
