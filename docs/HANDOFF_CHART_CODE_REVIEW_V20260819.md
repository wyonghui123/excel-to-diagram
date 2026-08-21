# 图表展示模块代码质量审查 + 修改交接文档

> **交接对象**：开发智能体（二次分析确认）
> **背景**：对「图表展示/渲染」模块做了代码质量审查，并（按当时的确认）实施了一批低风险修复。
> ⚠️ **重要**：管理方已明确——**本表不该由分析侧直接处理功能代码**。以下所有对源码的改动仅供开发智能体**复核确认**，按需采纳或回退。已保留全部改动明细、行号与验证证据，便于核对。

---

## 一、审查范围

渲染管线（~30k 行），当前嵌入图表展示主链路：
- 核心组件：`src/components/MermaidComponent.vue`（6064 行）
- 渲染管线：`src/composables/useMermaid/*`（64 文件：renderer/style/interaction/annotation/tooltip/syntax/layouts/color/config/dataMap/export …）
- 布局：`src/composables/useMermaid/layouts/`（groupedLayout.js 940 行 等）
- 编排：`src/components/common/RelationScopeTree/*`、`src/stores/diagramConfigStore.js`、`src/services/scaleGuard/*`
- 模型：`src/services/groupModel/*`、`hierarchyTree/*`

**排除（废弃链路，不作处理）**：`GroupModel` 的 `MermaidGenerator`/`getNodeData`/`_cachedDisabledPath` —— 已被弃用的 `useReactiveRenderer` 管线，无生产实例化（见第五节 E）。

---

## 二、总体结论

- 功能正确性基础扎实：渲染时序、折叠缓冲、竞态守卫、签名增量、事件委托都是亮点。
- 系统性问题：① 巨型组件职责过重（MermaidComponent 6064 行）；② 与 mermaid 内部 DOM 深度耦合 + 样式全量重刷；③ 生产代码遗留大量 console.log/死代码/死状态。

---

## 三、本次已修改文件清单（请开发智能体复核）

> 以下 9 个文件均为本次会话改动，`git status` 可查。每一处都给出「改动点 + 文件:行号 + 理由 + 验证」。开发侧请重点确认**改动是否符合预期 / 是否需回退**。

| 文件 | 改动摘要 | 对应项 |
|------|---------|--------|
| `src/components/common/RelationScopeTree/RelationScopeSection.vue` | ①版本切换竞态守卫(3处 return 比对 versionId) ②清理 8 处调试 console.log | 见三.1 / 三.2 |
| `src/composables/useMermaid/syntax/nodeLabelTemplate.js` | `businessObjectLabel` + `collapseFormatMarker` 加 HTML 实体转义 | 见三.3 |
| `src/composables/useMermaid/syntax/__tests__/nodeLabelTemplate.spec.js` | 新增转义单测 | 三.3 配套 |
| `src/composables/useMermaid/style/useSvgStyle.js` | MutationObserver 泄漏修复(cleanup) | 见三.4 |
| `src/composables/useMermaid/renderer/useSvgProcessor.js` | cleanup 补 svgStyle + annotationOverlay 清理 | 三.4 / 三.7 |
| `src/composables/useMermaid/layouts/groupedLayout.js` | 容器标题 4 处转义 + try/finally 保 flatElkGroups | 三.3 / 三.8 |
| `src/composables/useMermaid/tooltip/useTooltip.js` | setupPathEvents.onClick 补 wasDrag 守卫 | 三.6 |
| `src/composables/useMermaid/interaction/useInteraction.js` | dragState 加实例归属修多图串扰 | 三.5 |
| `src/composables/useMermaid/annotation/annotationOverlay.js` | 暴露 cleanupListeners | 三.7 |

---

### 三.1 RelationScope 版本切换竞态（主要行为改动，需重点复核）

**文件**：`RelationScopeSection.vue`

**问题**：`loadRelationships` 的 `cachedVersionId.value = props.versionId` 在分页 await 后读取**最新** versionId，但 `allRelationships` 是请求开始时捕获的旧版数据 → versionId 中途变化时**旧版本数据 ↔ 新版本缓存 key 错配**，后续命中缓存拿到错版本数据。

**改动**：`loadRelationships` 开头捕获 `targetVersion = props.versionId`，在两次 await 副作用前 `if (props.versionId !== targetVersion) return`（分页 await 后、loadBusinessObjects await 后）。
- 性质：纯增量守卫，单请求路径零变化；同版本并发刷新数据相同、覆盖无害，未防。
- 回归风险：仅版本切换场景丢弃旧请求。
- **复核点**：确认「丢弃旧请求」不破坏任何依赖旧请求结果的场景；确认 `finally` 的 loading 逻辑未被破坏（本次**未**改 finally）。

### 三.2 RelationScope console.log 清理

**文件**：`RelationScopeSection.vue`
清理 8 处纯调试 `console.log`（loadRelationships/handleClassifierCheck 热路径）。保留 `console.error`/`console.warn` 及 ObjectScopeSection 的 dev-shortcut 日志。

### 三.3 mermaid 标签 HTML 实体转义（P0 XSS，安全修复，需重点复核显示是否一致）

**文件**：`nodeLabelTemplate.js`、`groupedLayout.js`

**背景**：渲染用 `securityLevel:'loose'` + `htmlLabels:true`（`useMermaidConfig.js:142/168`）。进入 `["..."]` 的文本若不转义：
- `& < >` 会被当 HTML 解析 → XSS 注入风险
- `"` 会提前结束 mermaid 字符串 → 非法语法

**改动**：
- 新增 `escapeMermaidLabelText()`（转义 `& < > "`，顺序先 `&` 防二次转义，不碰 `\n` 换行）
- 应用到所有进 `["..."]` 的文本：
  - `businessObjectLabel`（BO 叶子节点，自动覆盖 `useBusinessObjectSyntax` 全部 6 处 + `groupedLayout` 全部 11 处节点标签）
  - `collapseFormatMarker`（折叠/聚合标题，**保留容器标记** `<>{}[]`，仅转义内部 name/code）
  - `groupedLayout` 容器标题 4 处：`baseTitle`(L358)、collapsed fallback(L795)、`containerName`(L807)、SubDomain wrapper(L629)
- **运行验证**：用 mermaid 11 loose+htmlLabels 实际渲染 `A["采购&lt;订单&gt; &amp; 研发&quot;X&quot;"]`，DOMParser 解析后真实文本为 `采购<订单> & 研发"X"` → 实体正确解码、**显示不变**，同时阻断注入。

**复核点**：确认实体转义后**所有图类型/场景的标签显示与原先一致**（正常中文/数字场景是 no-op）；确认容器标记 `< >` 未被破坏。

### 三.4 MutationObserver 泄漏修复（useSvgStyle）

**文件**：`useSvgStyle.js`、`useSvgProcessor.js`

**问题**：`fixArrowMarkers`（serviceModule 分支）每次渲染 new 一个 MutationObserver 且从不 disconnect，组件卸载后仍存活。

**改动**：`useSvgStyle` 维护 `activeObservers` 数组 + 幂等 `cleanup()`；`useSvgProcessor.cleanup()` 调用 `svgStyle.cleanup()`（挂入 MermaidComponent `onBeforeUnmount → svgProcessor.cleanup()` 卸载链）。`typeof === 'function'` 防御兼容 mock。

### 三.5 多图拖拽串扰修复（useInteraction）

**文件**：`useInteraction.js`

**问题**：`window.__mermaidDrag` 全局单例 + `document` 级 mousemove，多图并存时 A 图 mousedown 后 B 图也响应移动。

**改动**：dragState 加 `target` 实例归属；handleMouseMove 开头 `if (dragState.target !== mermaidContainerElRef.value) return`。
- 单图场景 target 恒匹配，零行为影响。

### 三.6 setupPathEvents.onClick 补 wasDrag 守卫（useTooltip）

**文件**：`useTooltip.js` L683

**问题**：label 分支有 wasDrag 守卫（L637），path 分支没有 → 拖拽后落连线会误触发选中高亮。

**改动**：onClick 开头补 `if (window.__mermaidDrag?.wasDrag) return`（与 label 对齐）。

### 三.7 卸载清理链补齐（annotationOverlay）

**文件**：`annotationOverlay.js`、`useSvgProcessor.js`

**问题**：`useSvgProcessor.cleanup()` 只调 tooltip/svgStyle，未调 annotationOverlay → 卸载时 svg/edgeLabel/path/panel 监听靠 DOM 回收兜底。

**改动**：`annotationOverlay` 暴露 `cleanupListeners`；`useSvgProcessor.cleanup()` 补调。幂等安全。

### 三.8 groupedLayout try/finally 保 flatElkGroups

**文件**：`groupedLayout.js` `generateGroupedLayout`

**问题**：空 groups 提前 return 跳过 reset；异常中断会残留模块级 `flatElkGroups`/`elkCollectorStack`。

**改动**：主逻辑包 `try`，`finally { resetFlatElkGroups() }`；空分组也 reset。`return` 先求值 `flatElkGroups.flatMap(...)` 快照再 finally 清空，无副作用。

---

## 四、验证情况

- useMermaid 全量：**273 passed / 4 failed**（4 个失败为**既有基线**——`useSvgStyle.spec` 的 white-space/padding 断言、`annotationConfig.spec` 的分类断言，与本次改动无关，已用 `git stash` 证实）
- 本次改动相关 spec 全过：groupedLayout（51）/ useTooltip（23）/ useInteraction（7）/ useSvgProcessor（21）/ nodeLabelTemplate（29，含新增转义单测）
- 改动文件 `GetDiagnostics` 均无错误

---

## 五、审查中发现但【未修改】的项（供开发智能体排期）

| 项 | 位置 | 判定 | 建议 |
|----|------|------|------|
| **linkStyle 索引错位** | `useBusinessObjectSyntax.js:1382/1627` | **误报**。亲读确认 filter 与 forEach 判定自洽（filter 通过 ⇒ 必输出边，index=输出边序） | 无需改 |
| **console.log 大量遗留** | MermaidComponent:3048、useSvgStyle、useTooltip、annotationOverlay、EmbeddedChartView:977(L977 还打印调用栈) 等 25+ 处 | 确认，注释与"已改 diag"矛盾 | 可批量清理，风险低 |
| **C① 统一拖拽判定** | annotationOverlay `isDraggingState` / useTooltip `_mouseDownPos` / wasDrag(8px) 三套阈值不一 | 确认，行为分歧 | 有行为变化，需 Playwright 回归，独立专项 |
| **C④ 收窄 clearSvgHighlightsOnly** | `annotationOverlay.js:989-993` 无差别清全 path 误伤 useTooltip 选择高亮 | 确认 | 需先确认 useTooltip 独立覆盖，独立专项 |
| **F② liftedParentRegistry 出参透传** | `layouts/index.js` 返回字符串 | 确认，多图交错才触发；单图安全 | 改造成本高，暂缓 |
| **E. GroupModel 缓存**（`_cachedDisabledPath` 漏清 / `_mermaidConfigCache` 假缓存 / 空 if 死代码） | `groupModel/GroupModel.js` | 确认，但**废弃链路**（MermaidGenerator 无生产实例化），无生产触发面 | 不作优先级处理 |
| **巨型文件拆分** | MermaidComponent（6064）、useDiagramData（2629）、LayoutControlPanel（2077）等 | 确认 | 长期重构 |
| **模块级可变状态** | `groupedLayout.js` 的 liftedParentRegistry | 确认，单图安全；F② 已单列 | 见 F② |

---

## 六、给开发智能体的复核要点（优先级从高到低）

1. **三.1 RelationScope 版本竞态守卫**——唯一的行为改动，确认丢弃旧请求逻辑无误、未破坏 loading/勾选时序。
2. **三.3 HTML 实体转义**——安全修复，确认全图类型/场景标签显示无回归（正常文本 no-op，特殊字符显示不变）。
3. **三.4/3.7 清理链**——纯资源清理，确认无重复清理/时序问题。
4. **三.8 try/finally**——确认 `finally` 清空不破坏 `return` 快照。
5. 若上述任一处不符合预期，可 `git checkout <file>` 回退单个文件后重审。

---

## 七、遗留运作记录

- 本会话还完成了 staging 的 delta 部署（`feat/annotation-category-filter` HEAD 59a0897 及 scale-guard 8 commits），见 `docs/HANDOFF_STAGING_REG_V20260818.md`。
- `tools/baseline_20260819.yaml`、`test_helpers/_*.py` 等为 staging 运维诊断产生的未跟踪文件，与本审查无关。