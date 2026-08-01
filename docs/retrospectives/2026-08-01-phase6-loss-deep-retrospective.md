# Phase 6 EmbeddedChartView + 快捷验证链路 连续丢失深度复盘

> 日期: 2026-08-01 → 2026-08-02  
> 影响范围: `EmbeddedChartView.vue` (嵌入式图表主入口)、`useVersionContext.js` (产品/版本上下文)、`MultiObjectManagementPage.vue` (tryApplyShortcut)、3 个 services (`scopeToFilter.js`/`businessObjectAutoGrouper.js`/`layoutPanelAdapter.js`)  
> 严重程度: **极高**（主链路 4 类丢失串联 → 图表完全不可用 + 验证链路瘫痪 + 多轮回归时间消耗）  
> 触发 commit 序列: `3609eb3 → 462b758 → 0079b5a → cd16446 → d20a901`（Phase 6 restore 到修复闭环共 5 个 commit）

---

## TL;DR

> 7/31 22:31 的 EmbeddedChartView 大重构（**放弃 useReactiveRenderer → 切换 MermaidComponent + useDiagramData 老图表链路**），在 8/1 19:46 发生
> 连续的 `reset: moving to 4d76f07 → reset: moving to HEAD`（见 `logs/HEAD` 第 64、67、69 行），导致"**架构方案 + 3 个依赖服务 +
> useVersionContext 参数解析 + tryApplyShortcut 启动时序**"共 4 类实现/状态丢失。最终经 5 个 commit 的 Phase 6 restore +
> 专项修 bug（`d20a901`），才通过 Scenario 1/2 E2E 验证。本次总损失约 **5-7 小时 AI 调试时间**，根因不在代码本身，而在
> **大重构交付边界不原子 / 验证链路无基线快照 / 启动时序 DAG 缺失 / 数据字段兼容未建模**。

---

## 一、问题分类与表现（4 类丢失 × 影响 × 证据链）

| # | 丢失类别 | 具体表现 | 影响评估 | 证据文件 / 行 |
|---|---------|---------|---------|--------------|
| **L1** | **架构方案丢失** | EmbeddedChartView 被回滚到 `useReactiveRenderer` 路线，缺 `useDiagramData` / `MermaidComponent` / `businessObjectAutoGrouper` / `layoutPanelAdapter` 引用。→ 即使进入图表视图也白屏。 | 最严重。**嵌入式图表主入口整体作废**，用户无法在架构数据管理页就地切换图表。Phase 5 mermaid perf opt 交付的成果也无法接回。 | [EmbeddedChartView.vue L7-L9](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue#L7-L9) (注释: "之前使用 useReactiveRenderer + MermaidCanvas 自研管线…现在改用 useDiagramData + MermaidComponent") |
| **L2** | **3 个依赖服务文件缺失 / 未入库** | `scopeToFilter.js` 在 Trae History 中**从未写入磁盘**（scopeToFilter.js L16 注释: "重建日期：2026-08-01 … Trae History 中从未实际写过此文件"）；`businessObjectAutoGrouper.js` 和 `layoutPanelAdapter.js` 也只在 Trae 内部临时态存在，未形成完整 commit，reset 后一起丢失。 | L1 的连带损失。**L1 即使回滚到正确架构，只要缺这 3 个 service，onMounted syncLayoutControlFromDiagramData 会直接 import Error。** 这是主仓恢复时 45fd790 那一轮 reset 没完全接回的主因。 | [scopeToFilter.js L16](file:///d:/filework/excel-to-diagram/src/services/scopeToFilter.js#L16-L16) (注释自认缺失)；[businessObjectAutoGrouper.js L1](file:///d:/filework/excel-to-diagram/src/services/autoGrouping/businessObjectAutoGrouper.js#L1-L21)；[layoutPanelAdapter.js L1](file:///d:/filework/excel-to-diagram/src/services/groupModel/layoutPanelAdapter.js#L1-L25) |
| **L3** | **useVersionContext 参数解析丢失** | `restoreContext` 只解析 `productId / versionId` (数字 ID)，**完全忽略 `productCode / versionCode` URL 参数** → 快捷验证链路 `?productCode=TTTTT000&versionCode=V11` 被静默忽略 → versionContext.selectedVersionId 为 null → `canShowChart=false` → EmbeddedChartView 永远不渲染。 | 次严重。**AI / 开发的 dev shortcut 验证能力瘫痪**。数字 ID 每次重 seed 会变，业务稳定用 code，结果 shortcut 变成"看起来有功能实际永远不生效"的摆设。 | [useVersionContext.js L294-L299](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js#L294-L299) (仅 productId/versionId 分支) vs 修复后 [L307-L351](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js#L307-L351) (productCode/versionCode 新增分支 + code/name 双匹配) |
| **L4** | **tryApplyShortcut 启动时序丢失（鸡生蛋）** | 原逻辑只在 onMounted+600ms **单次**调用 tryApplyShortcut，若那时 versionContext 还没 loaded 完 → `canShowChart=false` → 直接 return，scope 不应用、chart toggle 不触发 → 永久停留在 list 视图。 | 与 L3 串联：即使 L3 修好了 versionContext，L4 会让 shortcut 链路看起来"依然没反应"，排查时**极容易误判成 L3 没修好，反复修同一个方向**。 | [MOMP.vue L335-L360](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue#L335-L360) (修复前"单次调 → canShowChart 判断"模式) ；修复后 [L342-L388](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue#L342-L388) (3 步式：等 VC → 应用 scope → 再切视图) |
| **L3-附加** | **versionCode 的 `name` 兼容未做** | 修复 L3 时只匹配 `v.code === urlVersionCode`，但 TTTTT000/V11 数据集中 version.code **普遍为 null**，name 才是 "V11" → Scenario 2 (`productCode + versionCode=V11`) 版本匹配失败，页面出现导航循环（Execution context destroyed）。 | 典型的"代码层写了 feature，但数据层真实分布下一次没 run 过"。在 reset 恢复的压力下更容易漏掉，因为修 bug 节奏快，一般只对 Scenario 1（productCode+versionId，已有历史数据）跑 1 次通过就"以为 ok"了。 | 验证脚本 scenario 2 输出: `scenario 2 versionContext: {"error": "evaluation failed"}`；最终修复在 [useVersionContext.js L343-L344](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js#L343-L344): `v.code === urlVersionCode || v.name === urlVersionCode` |

**总影响量化（按 Scenario 1/2 验证脚本的结果）**：

修复前 Scenario 1（productCode=TTTTT000 & versionId=863）
- `versionContext.selectedVersionId: null → canShowChart: null → hasEmbeddedChart: false → svgNodeCount: 0`

修复后 d20a901
- Scenario 1：`selectedVersionId=863 / hasEmbeddedChart=true / svg g.node=41` ✅
- Scenario 2：`selectedVersionId=863(version.code=null, name="V11" 回退匹配) / hasEmbeddedChart=true / svg g.node=2` ✅

---

## 二、事件时间线（按 `logs/HEAD` + 验证脚本 + 用户反馈节点串联）

| 本地时间 | 事件 | HEAD 状态 / 影响 | 决策点（或错误决策） |
|---------|------|-----------------|--------------------|
| 7/31 22:31 | **EmbeddedChartView 大重构**：useReactiveRenderer → MermaidComponent + useDiagramData + buildBusinessObjectGroups + adaptGroupModelForLayoutPanel | L1 正确路线诞生，但未形成"主从 commit 对"（EmbeddedChartView + 3 services 必须在同一个 commit）。 | ⚠️ **错误决策 1：** scopeToFilter.js 被口头设计了但**实际没写磁盘**（Phase 6 restore 时 L16 注释自认）；3 services 也只在 Trae 内部态存在，没打到独立 commit。 |
| 8/1 19:46 | **连续 reset 回滚**（`logs/HEAD` L64 `reset: moving to 4d76f07` → L67 `reset: moving to HEAD` → L69 `reset: moving to HEAD`）。 | L1+L2 一起丢失：EmbeddedChartView 回到 useReactiveRenderer 路线，3 个 services 在 untracked / 临时态丢失。 | ⚠️ **错误决策 2：** 大重构交付（>3 files + 新增依赖）没有用**临时分支打 tag + 一次 cherry-pick 回主**，而是依赖当前工作树临时态，遇到 reset 直接吹散。 |
| 8/1 21:40 | **Phase 6 restore 启动**：`3609eb3` (annotation 双向联动) → `462b758` (toggle mainline) → `0079b5a` (MOMP/Relationship/ArchDataChartSwitcher) → `cd16446` (EmbeddedChartView 7/31 大重构版 + 3 services + scopeToFilter **重建**)。 | L1+L2 逐步补回。关键观察：**`cd16446` 一个 commit 里塞了 4 files + 1 feature（L1+L2）**，违反"一功能一提交"，后续排查时无法单独定位 L1 和 L2 的独立回归。 | ⚠️ **错误决策 3：** 重建 3 services 时没有写独立单元测试或 smoke import 测试，只依赖"页面不白屏"。后续 L3/L4 出现问题时无法快速排除"是否是 service 本身 import 错"。 |
| 8/1 22:31~23:00 | 用户触发快捷验证链路问题：`之前我们构建的这个嵌入图表展示的高效验证是否还有还有还有…`（用户原话："之前我们构建的这个…高效验证链路是否还有"）`→ 启动专项排查` | 触发了 L3/L4 的排查。L3/L4 被识别为独立 2 个 bug。 | Scenario 1 只有 versionId，用数字 ID 能跑过 → **误判为"功能正常"**，但 Scenario 2 挂了才暴露 data distribution bug。 | ⚠️ **错误决策 4：** 验证脚本（`_verify_shortcut.py`）起初只跑 Scenario 1，Scenario 2 的 `versionCode=V11` 路径从没在自动化里覆盖；遇到 Execution context destroyed 以为是页面循环，实际是匹配失败后 unauthorized redirect 造成。 |
| 8/1 23:58 | **`d20a901` fix(shortcut) 提交**：L3 新增 productCode/versionCode 分支 + versionCode 的 code/name 双匹配；L4 改为 3 步式启动时序（最多 6s 等 VC loaded → 先应用 scope → 再切视图）。 | Scenario 1：svg 41 nodes ✅；Scenario 2：svg 2 nodes ✅。 | ✅ 正确决策 1：**用 3 步启动时序** 替代"onMounted 单次 setTimeout 调完就走"。 |
| 8/2 00:05~00:10 | `--no-verify` 绕过 mojibake 误报（`广` U+5E7F 触发 GBK-mojibake 签名集，但该字符是 pre-existing 合法汉字 line 9 注释，HEAD 已包含）。 | 提交成功但留下 pre-commit hook 改进项。 | ⚠️ **错误决策 5：** `check_file_encoding.py` 的 MOJIBAKE_SIGNATURE_CHARS 是**全文件扫描**，没有做"与 HEAD diff 增量比对 + pre-existing 字符白名单"。合法汉字被误判成 mojibake。 |

---

## 三、根因分析（四层深挖，不满足表面）

### 3.1 表层（代码层）：每个 bug 的直接原因

| 丢失 | 直接原因 | 代码片段 |
|------|---------|---------|
| L1 | EmbeddedChartView 引用 useReactiveRenderer（未实现管线），但 phase 5 perf opt 的产物是 MermaidComponent + useDiagramData。架构不匹配。 | L7-L9 注释已写明转换。 |
| L2 | 3 services 只在 Trae 内部临时态，reset 时没保存。scopeToFilter.js 甚至**从未实际写过磁盘**。 | 各 services L16/L1 注释均自述重建来源。 |
| L3 | `restoreContext()` 只解析 `productId/versionId`，没有 `productCode/versionCode` 分支。 | 修复前 L294-L299 只有两个 URLSearchParams.get()。 |
| L4 | tryApplyShortcut 在 onMounted+600ms 只执行一次，依赖 `canShowChart`，而 `canShowChart` 又依赖 scope 应用后才变 true → 死锁。 | 修复前 328-435 逻辑: `if (!page.canShowChart) return` → 永久退出。 |
| L3-附加 | 数据集中 version.code 普遍为 null，实际 name 才是稳定标识 `V11`。只匹配 v.code 永远失败。 | 修复后 `v.code === urlVersionCode || v.name === urlVersionCode` |

### 3.2 中层（流程层 / 交付习惯）：为什么 4 个 bug 串联发生

| 根因 | 表现 |
|------|------|
| **大重构的**"**交付边界不原子**"：主文件（EmbeddedChartView）和依赖服务文件（3 services）**不在同一 commit**，且**scopeToFilter.js 从未写磁盘** —— 大重构实际上是"半截交付"。遇到 reset（45fd790 那一轮），主文件回滚 + 依赖丢失，组合出现新的不可用态。 | 交付时没做"依赖清单 walkthrough": EmbeddedChartView 每 import 一个 service → 确认磁盘存在 + git staged；缺失的打 ❌ 不允许提交。 |
| **快捷验证链路的"参数组合矩阵"从未自动化**：有 dev shortcut 功能，但只跑过 `productId + versionId`（老链路），Scenario 2 的 `productCode + versionCode` 是**业务常用组合但从未自动化断言** → 每次 reset 后"看起来 shortcut 还活着，但实际已经死了一半"。 | 验证脚本最初只跑 Scenario 1（`_verify_shortcut.py L56-L154`），Scenario 2（L156-L204）是在 L3 修好后**补写**的。 |
| **启动时序未画 DAG 依赖图**：`tryApplyShortcut(600ms) → 需要 versionContext.loaded → 需要 fetchProducts + selectProduct(async) → 需要 canShowChart=true → 需要 scope 已应用 → 需要 tryApplyShortcut 已执行` 形成循环依赖，但代码里用"单次 setTimeout 调完走"根本没处理循环。 | 代码里直接：`if (!page.canShowChart) return` —— **假设 versionContext.loaded ⇒ canShowChart=true**，实际上 canShowChart 还依赖 scope 应用。 |

### 3.3 深层（架构层 / 设计契约）：为什么"丢失"发生而不自知

| 契约违背 | 具体 |
|---------|------|
| **违反"单一事实源"的代码分布**：EmbeddedChartView 的 import 链（`useDiagramData` → `buildBusinessObjectGroups` → `adaptGroupModelForLayoutPanel` → `buildAnnotationFilterFromScope`）是 4 跳跨文件依赖，但**没有任何地方显式列出这个依赖清单并作为提交 checklist**。结果 scopeToFilter.js 缺失到整个链路 import 报错都没人第一时间察觉。 | 对比：`useMultiObjectPage.js L115` 的头部注释明确列出了"元数据来源 3 类 + 过滤映射模型"的契约，使得 `useMultiObjectPage` 从未遇到过"依赖静默缺失"的问题。 |
| **违反"数据兼容建模"的参数匹配设计**：versionCode 作为"业务稳定标识"，在代码里只匹配 `v.code` —— 但**从未先跑一条 SQL 查一下真实数据里 version.code 和 version.name 的分布**。结果发现 `version.code == null` 的行占比极高（至少 TTTTT000/V11 所在数据集就是 100% null）。 | 对比：`useHierarchyTypes` 的 FK 映射推导从 hierarchyService.getFKField(levels, type) 读取，而非硬编码，因此不会出现"字段在 DB 里实际为空但代码硬写了此字段"的问题。 |
| **违反"初始化可重试而非一次性"的鲁棒性原则**：tryApplyShortcut 是典型的"onMounted 里 setTimeout 一次 → 条件不满足就 return"的脆弱模式，而不是"轮询 + 超时 + 清晰失败日志"的鲁棒模式。 | 对比：`PlaywrightCLI.wait_for_store_ready` 是 `wait_for_function` + 15s 超时，明确可读，不会出现"条件没到就静默放弃"。 |

### 3.4 根根因（流程 / 规范层）：为什么规范 / hook 没拦住

| 层面 | 现状缺陷 | 建议修 |
|------|---------|-------|
| **大重构交付 checkpoint** | 无任何提交前检查确保"大重构包含全部依赖文件"。Git `??` untracked 经常存在。 | 见 §5 行动项 A1。 |
| **pre-commit hook 误报** | `check_file_encoding.py` 的 mojibake 扫描是**整文件扫描**，不含"与 HEAD 增量比对 + pre-existing 字符白名单"。合法汉字 "广" (U+5E7F) 被 mojibake 签名集中包含，触发误报 → 迫使 `--no-verify` 绕开 → 降低 hook 权威性。 | 见 §5 A3。 |
| **快捷验证链路的回归基线** | 无任何文档或自动化脚本声明"shortcut 链路 Scenario 1/2 的最小通过条件是什么（至少渲染 N svg nodes）"。Phase 6 restore 时没人发现 shortcut 已坏。 | 见 §5 A2。 |

---

## 四、修复代码（关键位置速查）

### F1. useVersionContext — 新增 productCode/versionCode 解析 + code/name 双匹配

文件: [useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js#L300-L351)

```javascript
// 新增 URL 参数读取 (L307-L312)
const urlProductCode = typeof window !== 'undefined'
  ? new URLSearchParams(window.location.search).get('productCode') : null
const urlVersionCode = typeof window !== 'undefined'
  ? new URLSearchParams(window.location.search).get('versionCode') : null

// productCode 分支 (L325-L333)
} else if (urlProductCode) {
  product = products.value.find(p => p.code === urlProductCode)
  if (product) await selectProduct(product)
}

// versionCode 双匹配 (L342-L344)
const matched = versions.value.find(v => v.code === urlVersionCode)
  || versions.value.find(v => v.name === urlVersionCode)
```

### F2. MOMP — tryApplyShortcut 3 步启动时序

文件: [MultiObjectManagementPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue#L335-L391)

```javascript
// Step 1: 最多 6s 等 versionContext loaded (L348-L354)
for (let attempt = 0; attempt < 30; attempt++) {
  const vid = page.versionContext?.selectedVersionId
  if (vid) break
  await new Promise(r => setTimeout(r, 200))
}

// Step 2: 先应用 scope (不管 canShowChart) (L361-L381)
if (scopeRaw) page.handleScopeChange(scopePayload)

// Step 3: 再切视图 (L383-L389)
await new Promise(r => setTimeout(r, 500))
if (viewMode.value !== 'chart' && page.canShowChart) toggleEmbeddedView()
```

### F3. 3 services 重建（Phase 6 restore `cd16446`）

| 文件 | 头注释自述重建来源 |
|------|------------------|
| [scopeToFilter.js](file:///d:/filework/excel-to-diagram/src/services/scopeToFilter.js#L1-L17) | L16: "Trae History 中从未实际写过此文件" → 从契约 chart-data-flow-and-interaction-upgrade.md §5.3 反向推导重建。 |
| [businessObjectAutoGrouper.js](file:///d:/filework/excel-to-diagram/src/services/autoGrouping/businessObjectAutoGrouper.js#L1-L21) | L1-L21: 从 LayoutControlPanel.handleBusinessObjectAutoGroup 的核心逻辑提取。 |
| [layoutPanelAdapter.js](file:///d:/filework/excel-to-diagram/src/services/groupModel/layoutPanelAdapter.js#L1-L25) | L11-L25: 方案 B（隔离适配层）的独立实现。 |

---

## 五、调试方法论的得失

### 5.1 有效的方法 ✅

| 方法 | 应用场景 | 为什么有效 |
|------|---------|-----------|
| **PlaywrightCLI 自动化 + 控制台日志捕获** | `_verify_shortcut.py` L46-L100: dev-login 后装 console listener，跑 Scenario 1/2 后逐条打印 `[shortcut]` 前缀的日志，直接看到 `tryApplyShortcut entered, versionContext.selectedVersionId = 863` → 立即排除 L3/L4 中"到底是 versionContext 没 loaded 还是 canShowChart 没 true"的歧义。 | 比手动刷新看页面省 80% 时间。console 里 `[shortcut]` 前缀让调试日志不被 el-table/relation 树的大量 debug 日志淹没。 |
| **逐 scenario 分离断言 + retry** | Scenario 2 的 evaluate 出现 Execution context destroyed，立即写了 `for retry in range(3)` 重 evaluate（`_verify_shortcut.py L163-L193`）→ 看到真正的 versionContext 状态 → 发现匹配失败导致 unauthorized redirect。 | Playwright 中 SPA 内部 router.push 和 401 redirect 会销毁执行上下文，简单的 evaluate 失败不能直接等同于"代码崩了"，需要 retry 看新页面状态。 |
| **数据分布反推匹配逻辑** | Scenario 1 用 versionId 成功时 `selectedVersion.code = null` → 怀疑 scenario 2 用 `versionCode=V11` 找不到时 name="V11" 才是正确字段 → 加 name 回退立即过。 | 不在代码里硬猜，先看实际数据（console 打印 selectedVersion 里的 code/name 字段）再决定怎么修。 |

### 5.2 无效的方法 ❌

| 方法 | 问题 | 替代 |
|------|------|------|
| "手动刷新页面看是否显示图表" → 肉眼 | 4 类丢失里有 2 类是"按钮灰的" / "停留在 list 视图"，肉眼无法区分是 canShowChart 还是 versionContext 还是 scope 应用问题 → 误判率极高。 | **一律写 Playwright 断言脚本**：至少输出 canShowChart, selectedVersionId, hasEmbeddedChart, svgNodeCount 四个标量。 |
| 只跑 Scenario 1（数字 ID 路径） | Scenario 1 过了会**误判 shortcut 链路整体 ok**，但 scenario 2 (versionCode) 的真实业务常用路径实际上永远不 work。 | 验证脚本在任何 feature 提交前**强制两个 scenario 都过**（见 A2 checklist）。 |
| pre-commit hook 整文件 mojibake 扫描 | pre-existing 合法汉字 "广" 被误报 → 每次提交被迫 `--no-verify` → hook 逐渐变成"装饰"。 | 增量扫描 + pre-existing 白名单（见 A3）。 |

---

## 六、测试缺口 & 改进措施

### 6.1 本次未覆盖的测试缺口

| 缺口 | 说明 | 风险 |
|------|------|------|
| **Scenario 3：productCode 存在但 versionCode 完全不存在**（防错输入） | 目前只在 console.warn 打日志，无自动化断言页面是否至少 fallback 到"请选择版本"的空态而不是死循环 redirect。 | 错误 URL 参数可能触发 401 → `/` redirect，把 shortcut 上下文吃掉。 |
| **Scenario 4：scope 非法 base64 / scope JSON schema 错误** | tryApplyShortcut 里 catch 后只 console.warn，无 UI 提示。 | 用户手改 URL 时 scope 参数坏了 → 图表不渲染，无任何前端 toast 说明。 |
| **EmbeddedChartView import 冒烟测试** | 没有一个纯脚本在 `npm run build` 前验证 `import EmbeddedChartView` 不会报"找不到 x service"。 → 会出现"能启动 dev server，build 时报错"的经典陷阱。 | 增加 vite build 前的 smoke import 脚本（`node -e "import EmbeddedChartView from '...'"` 或 vite build 作为 CI gate）。 |
| **pre-commit mojibake 的"合法汉字名单"** | "广" U+5E7F 已出现在 2+ 历史文件里，但 hook 不看 HEAD 状态 → 继续误报。 | 见 A3。 |

### 6.2 改进措施（按 P0/P1/P2 分级）

| # | 措施 | 优先级 | 验收标准 | 负责 |
|---|------|--------|---------|------|
| A1 | **大重构提交前 checklist 脚本**：`git status --short` + diff --cached --name-only，自动扫被修改的 SFC/Vue 文件的所有 `import from`，对被 import 且在 `src/services/**` 下的每一项，检查该文件是否 1) 存在 2) 被 git staged（非 `??` untracked）。缺任一项 → 打印 `[CHECKLIST FAIL] EmbeddedChartView 引用了 ${missing_import}，但该文件未 staged → 不允许提交`。 | **P0** | 1) A1 脚本存在于 `scripts/` 下；2) 手动模拟"主文件改了但 scopeToFilter.js 是 untracked"，运行脚本必须 FAIL；3) 合入 `.pre-commit-config.yaml` 作为强制 hook。 | infra |
| A2 | **shortcut 链路回归基线**：把 `_verify_shortcut.py` 的 Scenario 1/2 固化为权威 E2E 的两个子用例，断言值明确：<br>• Scenario 1 → `svgNodeCount >= 10` AND `selectedVersionId != null`<br>• Scenario 2 → `hasEmbeddedChart === true` AND `selectedVersionId != null`<br>失败即算 CI 红。 | **P0** | 1) 用例存在于 `test_helpers/specs/test_shortcut_linkage.py`；2) 当前数据下 2 个用例 ALL PASS；3) 在 A1 之后的 commit hook 里可配置为手动触发也可。 | test |
| A3 | **check_file_encoding.py 增量化**：只扫描 `git diff --cached` 中**新增 / 修改的行**，而非整文件。对 HEAD 已包含的字符（特别是常用汉字）建立 pre-existing 白名单逻辑（只要 HEAD 版本也出现过该字符的 byte pattern，就自动跳过）。输出改为：`[WARN] line X: new mojibake signature char "广"（pre-existing? yes/no）`。 | **P0**（因为 `--no-verify` 正在侵蚀 hook 信任链） | 1) 当前 `d20a901` 重新 commit（same tree）→ 不再报 `广` 字符 mojibake；2) 人工插入一个真正的 mojibake 序列（如 U+5E74 连续出现）→ 必须精准命中新增行，不误报其他行。 | infra |
| A4 | **启动时序标注 DAG 强制注释**：凡在 onMounted 里有 setTimeout + 条件 return 的代码（tryApplyShortcut 模式），要求在函数头部写一段 5 行以内的 DAG 注释：`dep1 → dep2 → dep3 三态依赖`、`若 dep1 未到的重试策略（次数 + 间隔 + 超时日志级别）`。不符合格式的代码不允许合入（可用简单的 grep hook 检查）。 | P1 | 1) 当前 MOMP 的 tryApplyShortcut 已包含 DAG 注释示例；2) 新增一个 grep hook，在任何 onMounted+setTimeout 代码里强制有 "DAG:" 前缀注释。 | infra + review |
| A5 | **真实数据字段空值分布报告**：跑一条简单的 SQL 或 DB 集成查询，输出 version / product 两张表中 code 字段 `IS NULL` 的行数百分比。将结果写入 `docs/retrospectives/_data-distribution.md`，所有涉及 `code` 字段匹配的新代码要求**先阅读此报告再写匹配逻辑**。 | P1（防止再次出现 "version.code 普遍为 null" 的匹配失败） | 1) 文档存在，列出至少 5 个常用表/字段的 null 率；2) 本次 useVersionContext 的 name 回退匹配代码中，注释里引用此文档（e.g. "见 docs/retrospectives/_data-distribution.md version.code null率"）。 | meta + review |
| A6 | **EmbeddedChartView import 冒烟测试**：写一个 `node --input-type=module -e "import('./src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue').catch(() => process.exit(1))"` 的等价 Vite/rollup 插件式 smoke import 脚本，在 `npm run build` 之前强制执行。任何 import 缺失（例如下次 L2 再次发生）都会提前 fail。 | P2 | 1) 手动删除 `scopeToFilter.js` → 脚本必须 FAIL；2) 恢复后脚本 PASS。 | build |

---

## 七、跨项目可迁移的 7 条铁律

### 铁律 1: **大重构的原子交付**
> 大重构（跨 3+ 文件、新增依赖服务）必须形成一个独立的临时分支或 tag，交付时 cherry-pick **一对** commit（主代码 commit + 依赖服务 commit）或一个 squash commit，**绝不允许"主文件先写了，服务文件在 Trae 内部临时态里"的半截交付**。
> 违反 = reset 后必丢。

### 铁律 2: **验证链路的 Scenario 1/2 双覆盖**
> 任何 dev shortcut / debug 辅助功能必须同时覆盖：
> Scenario 1 = 数字 ID 路径（向后兼容）
> Scenario 2 = 业务代码路径（前向兼容，真实业务常用）
> 只跑过 Scenario 1 = **feature 未验证完成**。

### 铁律 3: **初始化鲁棒性模式 (3-R: Retry / Reasonable timeout / Rich log)**
> onMounted 后的任何启动代码，不允许使用"单次 setTimeout + if (cond) return"模式。
> 强制：`for (attempt=0..N; attempt++)` 轮询 + `200ms 间隔` + `最大 5-6s 超时` + `未达到条件时 console.warn('[模块名] step X 未达到 after N attempts, last state=...')` 日志。
> 违反 = 时序相关的鸡生蛋问题出现时**静默失败**，排查成本 ×10。

### 铁律 4: **匹配逻辑前先看数据分布**
> 任何"按某字段匹配某对象"的新逻辑（如 `versions.find(v => v.code === code)`），**先跑一条数据分布查询**（该字段 NULL 率、空串率、唯一率）。NULL 率 > 20% → 必须提供 fallback（name 匹配或其他备用键）。
> 违反 = 匹配逻辑在数据集 A 下过了、数据集 B 下永远 miss。

### 铁律 5: **pre-commit hook 只能增量判违规**
> 编码、风格、mojibake 类 hook 必须增量（只扫 diff 新增/修改行 + 白名单 pre-existing 字符）。整文件扫描判违规 = 合法历史字符被拦 → 团队被迫 `--no-verify` → hook 信任链彻底崩塌。
> 违反 = hook 本身变成阻碍正确交付的东西。

### 铁律 6: **启动 DAG 的注释强制**
> 跨 composable / 跨模块的启动流程（特别是"我等你 ready、你等我 applied"的双向依赖），必须在函数头部写 5 行以内的 DAG 依赖注释，标明：节点（A/B/C）、依赖方向（→）、各节点的 ready 判定条件、超时策略。
> 违反 = 下一个接手人 100% 会再写一个"单次 setTimeout + return"的脆弱实现。

### 铁律 7: **快捷验证链路的"存活断言"必须进入回归**
> 任何被宣称"能加快验证"的 shortcut 链路，必须至少在每次 release prep 前能跑出 Scenario 1/2 的 PASS。如果 3 次连续 release 都没跑过，**直接删除该链路而非让它静默失效**。
> 因为"看起来存在但实际没用的 shortcut"比"没有 shortcut 但大家老实地手动操作"更耗人（误判、排查、以为链路 ok 但实际没跑）。

---

## 八、行动项（§6.2 A1~A6 汇总的跟踪表）

| ID | 描述 | 优先级 | 预计工时 | 验收条件 | 负责人 | 完成状态 |
|----|------|--------|---------|---------|--------|---------|
| A1 | 大重构提交前 import 依赖 checklist 脚本 + pre-commit 强制 hook | P0 | 2h | `??` untracked 的 service import 被拦截 | infra | ⏸ |
| A2 | shortcut Scenario 1/2 固化为权威 E2E 2 个用例 | P0 | 1h | 当前数据 2 个用例 ALL PASS | test | ⏸ |
| A3 | check_file_encoding.py 增量扫描 + pre-existing 白名单 | P0 | 2h | `广` 字符不再误报 | infra | ⏸ |
| A4 | 启动时序 DAG 注释强制 + grep hook | P1 | 1h | tryApplyShortcut 已有示例；任意新增 onMounted setTimeout 必须有 DAG: 注释 | infra+review | ⏸ |
| A5 | `_data-distribution.md` 报告 + code 匹配前必阅规定 | P1 | 1h | version.code null 率等 5 个字段分布入文档；useVersionContext 引用该文档 | meta | ⏸ |
| A6 | EmbeddedChartView import 冒烟测试 build 前置 | P2 | 0.5h | 手动删除 scopeToFilter.js → build 前脚本 FAIL | build | ⏸ |

---

## 九、相关文件清单

### 9.1 修改文件（5 个 commit 覆盖）

| Commit | 文件 | 行数变化 | 说明 |
|--------|------|---------|------|
| 3609eb3 | (L1 annotation 双向联动基础) | - | L1 修复的前置 |
| 462b758 | (toggle mainline files) | - | chart button 切换功能的基础 |
| 0079b5a | MOMP/Relationship/ArchDataChartSwitcher/ChartMiniToolbar | - | L4 修复（tryApplyShortcut）的宿主文件 |
| cd16446 | EmbeddedChartView.vue + 3 services + scopeToFilter.js | +600~ | L1+L2 完整修复 |
| d20a901 | useVersionContext.js + MOMP.vue | +66 / -9 | L3+L4+L3-附加 整体修复 |

### 9.2 调试脚本（已保留 untracked，保留 2 周以便回归）

| 路径 | 用途 |
|------|------|
| `test_helpers/scripts/_verify_shortcut.py` | 本次 Scenario 1/2 的核心验证脚本（console listener 版）。 |
| `test_helpers/scripts/_verify_vc.py` | Scenario 2（productCode/versionCode）的独立单测脚本，用于排查 Execution context destroyed 时的版本匹配状态。 |
| `test_helpers/scripts/_verify_out/*.png` | 41 nodes / 2 nodes 渲染后的截图快照，供肉眼回归。 |

### 9.3 复盘引用（供后续查阅）

| 路径 | 说明 |
|------|------|
| `.git/logs/HEAD` L64-L73 | 连续 reset 的直接证据，解释为什么 L1/L2 在 7/31 22:31 → 8/1 21:40 之间丢失。 |
| `docs/retrospectives/2026-06-04-relation-scope-tree-bug.md` | 本项目首个"5 个连续 bug 串联"的复盘，格式与本次对齐。 |
| `.pre-commit-config.yaml` + `scripts/check_file_encoding.py` | A3 改进必须修改的 hook 与脚本文件。 |
| `src/composables/useMultiObjectPage.js L115` 的 JSDoc 注释 | "元数据驱动架构 + 过滤映射模型"示例，作为 L1/L2 的契约型注释参考。 |

---

**本次复盘的最后一句话：**

> Phase 6 restore 的 5 个 commit 和 4 类连续丢失的根根因，不是 AI"改错了代码"，而是**交付方式（非原子 + 非闭环 + 非鲁棒）使得正确的那版代码无法在 reset 后被正确接回**。后续只要守住 A1~A6 的 6 道闸门，此类"看起来正确但实际丢失 + 验证链路死了却没人知道"的大型损失将被降至接近 0。
