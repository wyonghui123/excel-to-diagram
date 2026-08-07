# 实施计划：图表折叠语义 + 任意类型连线 + 视图模板

> 版本：v2.1 | 日期：2026-08-05 | 关联 Spec：`docs/superpowers/specs/2026-08-05-chart-collapse-links-templates-spec.md`

## 方向变更（2026-08-05 v2.1）：多态下拉取代显式折叠

> 用户确认：**移除显式 collapsed 折叠 UI**，改为**多态操作下拉菜单**，由 `enabled` 自动推导"上提"，
> 修复"仅服务模块"下 SM 空容器只显示标题的问题。

### 新语义（enabled 两态 + 自动上提推导）
| 用户可见状态 (enabled) | 渲染引擎推导 | 说明 |
|--------------------|-------------|------|
| **启用** | 若有启用子孙 → **容器**；若**无任何可见子孙** → **上提为节点**（有颜色） | 上提全自动，无需手动折叠 |
| **禁用 (c)** | 自身隐藏；**子孙若启用则上浮显示** | 禁用只隐藏自身，子孙可上浮 |

> 关键：a/b/c 是**渲染推导结果**，不是可勾选状态。故用**多态操作按钮**（下拉菜单）表达意图。

### 多态操作（替代 折叠按钮 + 禁用按钮）
| 操作 | 设置 enabled | 渲染结果 |
|------|-------------|---------|
| **启用全部** | 自身+全部子孙 = 启用 | 完整子树 |
| **折叠为节点** | 自身启用，全部子孙禁用 | 自身自动上提为彩色节点 |
| **仅显示子孙** | 自身禁用，全部子孙启用 | 自身隐藏，子孙上浮显示 |
| **禁用全部** | 自身+全部子孙 = 禁用 | 整棵子树隐藏 |

### 实现要点
- 新增 `upliftDerivation.js`：`computeUplift` / `markUplift` / `upliftNodeId`，基于 enabled 推导 `_uplift`。
- `groupedLayout.js`：折叠分支改为 `group._uplift === true`（复用 `COLLAPSE_<id>` 聚合节点机制）。
- `linkRemapper.js`：`buildCollapsedAncestorMap` → `buildUpliftAncestorMap`（基于 uplift 推导）。
- `useBusinessObjectSyntax.js`：`computeHiddenBoIds` 的折叠触发改为 uplift 推导。
- `useViewTemplates.js`：模板只设 enabled；新增 `setSubtreeEnabled` / `collapseToNode` / `showDescendantsOnly`。
- `MermaidComponent.vue`：重映射调用去掉 collapsed 守卫；签名移除 `cl: g.collapsed`（enabled 已触发重渲染）。
- `LayoutGroupNode.vue` / `LayoutControlPanel.vue`：移除折叠按钮 + collapse-cascade，新增多态下拉菜单。

## 方向变更（2026-08-05 v2.0）：三态自动上提 替换 显式折叠

> 用户确认：**移除显式 collapsed 显式折叠/级联折叠 UI**，改为只保留 `enabled`（启用/禁用）两态，
> 渲染引擎自动推导"上提"（upLift）为节点。这是对 P1/P4 已实现 collapsed 方案的重构。

### 新语义（三态）
| 用户勾选 (enabled) | 渲染引擎推导 | 说明 |
|--------------------|-------------|------|
| **启用** | 若有启用子孙 → **容器**；若**无任何启用子孙** → **上提为节点**（有颜色） | 上提全自动，无需手动折叠 |
| **禁用 (c)** | 自身隐藏；**子孙若启用则上浮显示** | 禁用只隐藏自身，子孙可上浮 |

### 派生能力
- **问题1修复**："仅服务模块"下 SM 容器内 BO 全禁用 → SM 无启用子孙 → SM 自动上提为有颜色节点，不再是空容器只显示标题。
- **需求1**："禁用采购云下所有子孙"→ 采购云无启用子孙 → 自动上提为节点，图表只剩采购云一个。
- **快捷操作**：新增"禁用自身 + 启用全部子孙"（保持自身禁用，子孙全启用上浮），替代"折叠"按钮的多余语义。

### 实现要点
- 移除 `collapsed` 字段的 UI 操作（折叠按钮、级联折叠 `setSubtreeCollapsed`、`collapseAllGroups`）。
- 渲染前统一做"上提推导"：把 enabled 状态映射为现有聚合节点机制（复用 `COLLAPSE_<id>` + linkRemapper），
  使"上提"与现有折叠渲染、连线重映射复用同一套代码。
- `useViewTemplates.js`：模板只设置 enabled，不再设置 collapsed。
- `linkRemapper.js`：改为基于 enabled 推导"上提祖先"（最近 enabled 且无 enabled 子孙的祖先）。

## 实施状态（2026-08-05）

| 阶段 | 状态 | 交付物 |
|------|------|--------|
| P1 | ✅ 完成 | `layoutPanelAdapter.js`(collapsed 初始化)、`groupedLayout.js`(聚合节点) |
| P2 | ✅ 完成 | `linkRemapper.js` + `MermaidComponent.vue`(渲染前重映射) |
| P3 | ✅ 完成 | `useViewTemplates.js` + `diagramConfigStore.js` + `LayoutControlPanel.vue`(模板栏) |
| P4 | ✅ 完成 | `LayoutGroupNode.vue`(级联折叠按钮) + `LayoutControlPanel.vue`(事件处理) + 单测 |

**验证结果**
- 单测：`useViewTemplates.spec.js`(9) + `linkRemapper.spec.js`(6) + `groupedLayout.spec.js` + `LayoutGroupNode.spec.js`(9) + `LayoutControlPanel.spec.js`(8) 全部通过。
- 构建：`npx vite build` 成功（无编译错误）。
- 全量单测中 271 个失败均为既有/无关失败（color 特性导致的 chartDataSnapshot 断言过期、element-plus 弃用告警等），本特性未引入任何新失败。

**自测闭环（2026-08-05, TTTTT000 / V11 / 供应链云→供应链计划, vid=863）**
- `verify_collapse_loop.py`：11/11 PASS。折叠聚合 + 子孙隐藏 + 连线连通 + 恢复 + allEnabled/onlyServiceModules 状态。
- `probe_onlysm.py`：应用 onlyServiceModules 后，供应链计划 8 个 BO（PLB041/DP10/PLB033/DP01/PLD00601/PLB042/PLB043/PLD00202）全部隐藏，服务模块仍显示。

**关键修复：禁用 BO 叶在子图内仍渲染（2026-08-05）**
- 根因：`computeHiddenBoIds` 只过滤了 standalone 回填/style 循环，但 groupedLayout 子图渲染（`generateContainerCode`/`generateGroupCode`）与 SG 兜底路径直接按容器/分组渲染节点，不检查 hiddenBoIds → 禁用 BO 叶仍出现在服务模块 subgraph 内。
- 修复（`useBusinessObjectSyntax.js`）：
  1. 新增 `pruneHiddenBoNodes()`：在 `buildVirtualContainers` 后剪除 virtualGroups 中隐藏 BO 叶节点并移除空容器。
  2. `computeHiddenBoIds` 提升到分支外计算，disabledBoCodes 处理移出 groups 空守卫（onlyServiceModules 可能清空分组树）。
  3. SG 兜底路径（fallback）同样过滤 hiddenBoIds（节点/样式/连线），且空服务模块 subgraph 仍渲染标题（FR-005 语义：服务模块启用）。

## 阶段总览

| 阶段 | 内容 | FR | 交付物 |
|------|------|-----|--------|
| P1 | 折叠模型字段 + 聚合节点渲染 | FR-001/002 | `types.js`、`groupedLayout.js` |
| P2 | 连线重映射 + 统一端点 | FR-003/004 | remap 工具、link 构建 |
| P3 | 视图模板 | FR-005 | `diagramConfigStore.js` |
| P4 | 级联折叠/恢复 UI + 单测 | FR-006 | `LayoutControlPanel.vue` |

每阶段走"先单测 → dry-run → 本地启动验证"，不改动现有 enabled 上浮行为。

## P1：折叠模型字段 + 聚合节点渲染

### 目标
分组/容器可标记 `collapsed=true`，渲染为单个聚合节点（编码 `COLLAPSE_<group.id>`），子孙不渲染。

### 改动点
1. `src/services/groupModel/types.js`：`createGroup` 的 `layout` 增加 `collapsed: layout.collapsed !== false ? false : layout.collapsed`（默认 `false`）。
2. `src/composables/useMermaid/layouts/groupedLayout.js` `generateGroupCode`：
   - 在 `groupEnabled` 求值后新增 `groupCollapsed = group.collapsed === true`。
   - `groupCollapsed` 分支：输出单个聚合节点 `COLLAPSE_<safeId>["<title>…"]`，不遍历 directNodes/containers/children，直接 return。
3. 幂等：聚合节点写入 `definedNodes`，避免重复。

### 验证
- `groupedLayout` 单测：折叠分组输出含聚合节点编码、不含子孙节点文本。
- 本地启动，面板折叠一个领域 → 图表仅显示该领域单个节点。

## P2：连线重映射到最近可见祖先 + 统一端点

### 目标
连线端点规整到最近可见节点；聚合节点作为任意类型端点连通。

### 改动点
1. 新增 `src/composables/useMermaid/layouts/linkRemapper.js`：
   - `buildCollapsedAncestorMap(groups)`：遍历分组树，构建 `子节点编码 → 折叠聚合节点编码` 映射（取最近折叠祖先）。
   - `remapLinksToVisibleAncestors(links, collapsedMap)`：改写 source/target；两端均折叠到同一聚合节点则跳过；返回重映射 links。
2. 在 `generateGroupCode` 折叠分支侧，将聚合节点编码对应的原始端点登记进映射。
3. 渲染连线前调用 remap。

### 验证
- `linkRemapper` 单测：折叠领域后，指向其内 BO 的连线端点改为 `COLLAPSE_<领域id>`。
- 本地启动验证折叠后连线连通。

## P3：视图模板

### 目标
`allEnabled` / `onlyServiceModules` 一键应用。

### 改动点
1. `src/stores/diagramConfigStore.js` 增加 `viewTemplate` 状态 + `applyViewTemplate(template)`：
   - `allEnabled`：清空所有 `collapsed`、所有 `enabled=true`。
   - `onlyServiceModules`：所有 BO 叶节点 `enabled=false`（隐藏），SM 容器保留。
2. `LayoutControlPanel.vue` 顶部增加模板选择。

### 验证
- 应用 `allEnabled` → 无折叠/无禁用。
- 应用 `onlyServiceModules` → BO 隐藏、SM 保留。

## P4：级联折叠/恢复 UI + 单测

### 目标
面板折叠分组 → 子孙批量折叠，可单独恢复。

### 改动点
1. `LayoutControlPanel.vue` 分组行新增"折叠/展开" + "级联子孙"开关。
2. 折叠父分组时递归置子孙 `collapsed=true`（可单独改回）。

### 验证
- 折叠父 → 子孙全折叠；单点恢复子孙 → 该子孙恢复。
- E2E：面板折叠 → SVG 节点数减少（含存活断言）。

## 风险与回退
- 风险：破坏现有 enabled 上浮行为 → 折叠分支独立，旧逻辑不动。
- 回退：删除折叠分支 / 置 `collapsed=false` 即恢复。