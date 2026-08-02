# spec: 统一架构树 + 投影器（Unified Hierarchy Tree + Projector）

> 版本: v1.0 | 日期: 2026-08-02 | 状态: 待评审
> 所属模块: 图表展示（EmbeddedChartView / MermaidComponent）

---

## 1. 背景与问题

### 1.1 现象

服务模块图中出现**重复容器**：同一个服务模块（SM）既被渲染为 subgraph 容器（带边框），又在其中/外部被渲染为节点。

### 1.2 根因

SM 图渲染时**同时消费两套平行数据源**：

| 数据源 | 内容 | 生成者 |
|--------|------|--------|
| `diagramData.nodes/containers` | SM 节点 + 子领域容器（含 SM 节点） | `src/services/serviceModuleDiagramBuilder.js` |
| `layoutControlConfig.groups` | DOMAIN→SUB_DOMAIN→SERVICE_MODULE 分组树 | `src/services/groupModel/layoutPanelAdapter.js` 的 `buildServiceModuleGroupsFromDomainProducts` |

`useServiceModuleSyntax.generateMermaidCode` 在 layoutControl 启用时走 `routeLayout → groupedLayout`（渲染 groups 树），同时 `data.containers` 又被 `resolveGroupContainers` 解析进 groups（按 name/code 匹配真实容器）。同一层级两套定义，导致 SM 既出现在 groups 生成的 subgraph 结构中，又出现在 containers 生成的子图中 → 重复。

本质：**容器的唯一事实源缺失**。`layoutControlConfig.groups` 与 `diagramData.containers` 各建各的，无共享来源。

### 1.3 扩展需求（用户确认）

切换图表类型（业务对象 / 服务模块 / 子领域 / 领域）时，**只改变末端节点粒度，容器层级结构不变**。

未来可能支持**混合粒度**：同一张图内不同领域有不同的末端粒度（如"供应链领域末端到业务对象，财务领域末端到服务模块"），且 **link 的源/目标可以是不同层的元素**（BO 或 SM）。

---

## 2. 目标

1. 建立**单一事实源**的统一架构树，消除双数据源导致的重复容器。
2. chartType = 末端粒度投影，容器层级由树固定派生，天然支持 BO/SM/子领域/领域四种粒度。
3. 预留混合粒度（per-domain 末端配置 + 异构 link 端点重映射）。
4. 性能：分层数据管道 + 缓存 + 渲染跳过，配置变化走最小重建路径。

## 3. 非目标

- 不重构 MermaidComponent / syntax 层的渲染核心逻辑（保持契约稳定）。
- 不实现 mermaid 局部增量渲染（引擎不支持，属于不可行方向）。
- 不改动交互层（transform / highlight 已为增量）。
- 本次不落地混合粒度 UI（仅预留投影接口与算法）。

---

## 4. 架构设计

### 4.1 分层数据管道

```
[L0] preview 数据 (versionId + scopeHash)
  → [L1] buildHierarchyTree(treeBuilder)     缓存 key: versionId + scopeHash
  → [L2] projectTree(projector)              缓存 key: treeRef + terminalResolver
  → [L3] colorize(着色器)                    纯函数, 不需缓存
  → [L4] syntax 生成 mermaidCode              每次生成, 与上次 diff
  → [L5] mermaid.run → SVG                   仅当 mermaidCode 变化才执行
```

### 4.2 新增模块（`src/services/hierarchyTree/`）

#### 4.2.1 `buildHierarchyTree.js` — 统一架构树（L1）

从 preview 数据构建与图表类型无关的五层树：

```
PRODUCT
└── DOMAIN 领域
    └── SUB_DOMAIN 子领域
        └── SERVICE_MODULE 服务模块
            └── BUSINESS_OBJECT 业务对象
```

节点结构：

```js
{
  id: 'D_xxx' | 'SD_xxx' | 'SM_xxx' | 'BO_xxx',  // 前缀 + code, 同 types.js createGroupId 约定
  layer: 'DOMAIN' | 'SUB_DOMAIN' | 'SERVICE_MODULE' | 'BUSINESS_OBJECT',
  code, name, elementRef,                        // elementRef = 原始架构元素 (含 db id)
  children: [],                                  // 下一层节点
  // 数据来源: preview.business_objects / service_modules / 领域树 / 关系
}
```

- 输入：`{ versionId, scopeHash, preview }`（preview 由现有 fetch 链路提供）
- link 数据单独返回：`links: [{ id, source: elementRefId, target: elementRefId, ... }]`，端点引用**原始架构元素 id**（跨层稳定，不受粒度影响）

#### 4.2.2 `projectTree.js` — 投影器（L2，核心）

**输入**：`{ tree, terminalResolver, options }`

**terminalResolver**：决定某节点是否为"末端显示节点"。两种形态：

```js
// 全局粒度 (chartType 映射)
const GLOBAL_TERMINALS = {
  businessObject:  () => 'BUSINESS_OBJECT',
  serviceModule:   () => 'SERVICE_MODULE',
  subDomain:       () => 'SUB_DOMAIN',
  domain:          () => 'DOMAIN',
}
// 未来混合粒度 (per-domain 覆盖)
const MIXED_TERMINALS = (node) => {
  if (node.layer === 'DOMAIN' && node.code === '供应链') return 'BUSINESS_OBJECT'
  if (node.layer === 'DOMAIN' && node.code === '财务') return 'SERVICE_MODULE'
  return 'SERVICE_MODULE'  // 默认
}
```

**投影算法**：

1. **确定末端层**：对每个子树，末端层 = resolver 对该子树根节点的判定（全局时整图一致；混合时按领域不同）。
2. **折叠**：末端层以下的子树折叠进末端显示节点。例：末端层=SM → 该 SM 下所有 BO 折叠，BO 信息聚合到 SM 节点（`aggregatedCount` 等）。
3. **容器树**：末端层之上的祖先链生成容器层级（SM→子领域→领域）。
4. **link 端点重映射**：对每条 link 的 source/target（elementRefId），沿树向上找到第一个显示节点，替换为该显示节点 id；**两端折叠到同一显示节点 → 丢弃该 link**（折叠后自环无意义）。
5. **输出**：

```js
{
  nodes:      [{ id, layer, code, name, elementRef, aggregated: { count } }],
  containers: [{ id, layer, code, name, children: [容器或节点 id], }],  // 与 nodes 严格一致
  links:      [{ source: 显示节点id, target: 显示节点id, ... }],
}
```

**关键不变量**：`nodes` 与 `containers` 派生自同一棵树 → 一个元素在图中**只出现一次**（要么是节点要么在容器内），从根上消灭重复容器。

#### 4.2.3 `colorize.js` — 着色器（L3）

纯函数：`(nodes, containers, { colorScheme, colorGroupBy, centerCodes, nodeTextColor }) → 带 color 的 nodes/containers`。

- 与投影解耦：颜色变化不触发 L1/L2 重建。
- 复用现有 `useMermaidColors.js` 的颜色方案逻辑。

#### 4.2.4 `layoutGroupsDeriver.js` — 布局控制 groups 派生

`(containers, nodeIds) → layoutControlConfig.groups`

- 从投影容器树派生，取代 `buildServiceModuleGroupsFromDomainProducts` 独立生成。
- 保证 `groups` 与 `containers` 归属严格一致 → `resolveGroupContainers` 的名称匹配错乱隐患消除。

### 4.3 改造点

| 文件 | 改动 |
|------|------|
| `src/services/serviceModuleDiagramBuilder.js` | `buildServiceModuleDiagramData` 内部改为调用 4.2 管道（L1→L2→L3）产出 `{nodes, containers, links}`，**删除独立建容器逻辑** |
| `src/services/diagramDataBuilder.js` | 同 BO 图迁移（可选/后续） |
| `src/composables/useMermaid/syntax/useServiceModuleSyntax.js` | 移除 `resolveGroupContainers` 的 fallback 匹配（不再需要）；其余契约不变 |
| `src/services/groupModel/layoutPanelAdapter.js` | `buildServiceModuleGroupsFromDomainProducts` 改为调用 4.2.4（或标注废弃） |
| `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` | 接入分层缓存（L1/L2 memo），layoutControl watcher 改为触发 L4 而非全量 |

### 4.4 缓存与增量（性能）

**缓存契约**：

| 层 | 缓存 key | 失效时机 |
|----|---------|---------|
| L1 树 | `versionId + scopeHash` | scope / version 变化 |
| L2 投影 | `treeRef + terminalResolverKey` | chartType 变化 |
| L3 着色 | 无（纯函数，O(n) 极快） | — |
| L4 mermaidCode | 与上次 diff | 每次生成，diff 相同则跳过 |
| L5 SVG | mermaidCode hash | 代码变化才 mermaid.run |

**配置变化最小重建路径**：

| 变化 | 重建层级 | 现状（对比） |
|------|---------|------------|
| colorScheme / colorGroupBy | L3 + L4 | 全量 generateDiagram |
| centerScopeHighlight | L3 + L4 | 全量 |
| layoutControl.groups | L4 | 全量 |
| chartType | L2 + L3 + L4 | 全量 |
| scope / version | L1 + 全链 | 全量（一致） |

**渲染跳过**（L5）：`mermaidCode` 与上次 diff 相同 → 不调用 `mermaid.run`，SVG 保持。覆盖场景：打开布局抽屉、无意义 watch 触发、防抖后内容未变。

**交互层**：transform / highlight 已增量（不重渲染），维持现状。

### 4.5 混合粒度（扩展点，非本次实现）

- terminalResolver 支持 per-domain 覆盖（4.2.2 `MIXED_TERMINALS` 示例）。
- link 端点重映射天然支持异构端点（BO↔SM、BO↔子领域），因重映射只查"最近可达显示节点"。
- 本次仅保证投影器接口与算法支持该形态，不暴露 UI。

---

## 5. 数据流示例（SM 图，修复后）

```
preview (版本 863) 
  → buildHierarchyTree → 树（含 DP01 等全部 BO/SM）
  → projectTree(terminal='SERVICE_MODULE')
      → nodes = [SM 节点]           // BO 折叠进各自 SM
      → containers = [子领域 → 领域] // 只含 SM 显示节点
      → links = 端点重映射到 SM 显示节点, 两端同 SM 的 link 丢弃
  → colorize(colorScheme)
  → useServiceModuleSyntax.generateMermaidCode
      → mermaidCode (subgraph 子领域/领域 各一层, SM 均为节点, 无重复)
  → mermaid.run (仅代码变化时)
```

---

## 6. 错误处理与边界

- **link 端点找不到显示节点**（数据悬空）：丢弃该 link，记录 warning（`diag.recordWarning`）。
- **树节点无 children 且非末端层**（数据不完整）：该节点折叠到最近祖先显示节点。
- **投影结果为空**（scope 无数据）：返回空 `{nodes:[], containers:[], links:[]}`，走现有 empty 分支。
- **缓存失效竞态**：L1/L2 缓存以引用相等 + key 双重校验，防止旧树被新 scope 复用。

---

## 7. 测试

### 7.1 单元测试（Vitest）

| 用例 | 覆盖 |
|------|------|
| `buildHierarchyTree.spec.js` | 五层树构建、id 前缀、elementRef 绑定、link 引用原始 id |
| `projectTree.spec.js` | 四档末端粒度投影、BO 折叠、容器树派生、link 重映射、自环丢弃、混合粒度 resolver |
| `layoutGroupsDeriver.spec.js` | groups 与 containers 归属一致性（不变量） |

### 7.2 回归（复用现有 E2E 框架）

- `chart_e2e.py` 5 场景全量断言继续 ALL PASS（A 结构/B 颜色/C 备注/D 交互）。
- **新增断言**：SM 图 `snapshot().containers` 中无重复容器（同一 SM id 不既在 containers 又在 nodes）—— 回归本次根因修复。
- **性能断言**：`colorScheme` 切换时 `diag.stepTimings` 中 L5 渲染耗时显著下降（或 L5 被跳过）。

---

## 8. 兼容与灰度

- **渲染契约不变**：`{nodes, containers, links}` 结构保持，MermaidComponent / syntax 层零改动（除移除 resolveGroupContainers fallback）。
- **BO 图迁移可选**：本次优先 SM 图（修复重复容器）；BO 图可随后迁移到同一管道（同一份树 + 投影）。
- **风险**：`layoutControlConfig.groups` 来源变更（→ 投影派生）需验证 LayoutControlPanel 的拖拽/状态迁移功能不受影响（`extractGroupStates` / `applyGroupStates` 按 elementCode 匹配，不受结构来源影响）。
- **feature flag**：提供 `chartConfig.unifiedPipeline`（默认开启），异常时可快速回退旧 builder。

---

## 9. 文件清单

| 文件 | 类型 | 职责 |
|------|------|------|
| `src/services/hierarchyTree/buildHierarchyTree.js` | 新增 | 统一五层树构建 |
| `src/services/hierarchyTree/projectTree.js` | 新增 | 末端粒度投影 + link 重映射 |
| `src/services/hierarchyTree/colorize.js` | 新增 | 着色纯函数 |
| `src/services/hierarchyTree/layoutGroupsDeriver.js` | 新增 | groups 派生（与容器一致） |
| `src/services/hierarchyTree/index.js` | 新增 | 管道装配 + 缓存 |
| `src/services/serviceModuleDiagramBuilder.js` | 改造 | 改为消费管道产出 |
| `src/composables/useMermaid/syntax/useServiceModuleSyntax.js` | 改造 | 移除 resolveGroupContainers fallback |
| `src/services/groupModel/layoutPanelAdapter.js` | 改造 | groups 派生走新模块 |
| `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` | 改造 | 接入分层缓存 |
| `docs/specs/spec-unified-hierarchy-projector-2026-08-02-v1.0.md` | 新增 | 本文档 |

---

## 10. 验收标准

1. SM 图无重复容器：`snapshot().containers` 中每个 SM id 至多出现一次（作为节点或容器内元素）。
2. 本次实现 BO/SM 两档 chartType 切换，容器层级固定、仅末端粒度变化；子领域/领域档由投影配置启用（单测覆盖，见 7.1 projectTree.spec.js）。
3. `colorScheme` 切换只触发 L3/L4，不重建树/投影（性能断言通过）。
4. 现有 chart_e2e 5 场景 ALL PASS。
5. 混合粒度 resolver 单测通过（`MIXED_TERMINALS` 形态）。
