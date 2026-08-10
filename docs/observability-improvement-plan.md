# 图表展示模块「可排查 / 可验证」能力改进方案

> 版本: v0.3 | 作者: AI Assistant | 日期: 2026-08-10 | 状态: 主要落地
>
> 触发背景: 用户多次反馈折叠问题无法定位、验证只能靠慢速浏览器、环境连续多次卡顿。
> 核心诉求: 把图表的"可观测、可复现、可断言"做成本模块一等公民, 并吃自己的狗粮(dogfood)——
>   用改进后的观测能力去定位仍存在的"双击展开→切区分/不区分→折叠回去"遗留 bug。
>
> 落地进度:
> - [x] P1-2 `diag()` + P0-2 `verify()` 基础版 (任意模式, 三份状态一致性)
> - [x] A(2026-08-09) 行为级 verify: `captureNodeSignature()` + `verify({before, expandKeys})` 节点签名稳定性/展开保持断言
> - [x] P0-1(2026-08-10) 状态真相面板 `TruthPanel.vue` (任意模式可用, store/chart/渲染树三份并排、差异高亮、一键自检、导出复现链接)
> - [x] P1-1(2026-08-10) URL 状态编码 `?fold=<json>&scopeHighlight=0|1` + `__archPage.exportUrl()` 应用与导出
> - [x] (2026-08-10) 可发现性入口 `__archPage.help()` 统一能力清单 (后续能力容易被知道)
> - [x] (2026-08-10) 复盘教训固化: 颜色字段统一 `colorStateTracker` 快照 diff (见 §七 S1~S4)
> - [x] (2026-08-10) 验证通过: 单测 41/41 (useMermaidColors/foldPreservation/colorStateTracker) +
>   `test_helpers/diag_observability.py` 浏览器实测 (help 完整、fold/scopeHighlight 应用、exportUrl、
>   真相面板渲染、工具栏按钮)。注: headless 环境图表渲染极慢 (~38s), 脚本已改为轮询等待
>   `__archPage.diag` 就绪而非固定超时等 selector。

---

## 〇、快速上手（开发者先看这里）— 能力入口速查

图表展示模块所有诊断/验证/复现能力**任意模式可用**（不依赖 `?mode=debug`），统一挂在 `window.__archPage`：

| 能力 | 调用 | 用途 |
|---|---|---|
| 能力清单 | `__archPage.help()` | **先敲这个**, 列出全部 API 与用途 |
| 状态真相面板 | `__archPage.openTruthPanel()` / 工具栏「真相」按钮 / `Ctrl+Shift+T` | 可视化 store/chart/渲染树三份状态, 差异高亮 |
| 状态聚合 | `__archPage.diag()` | store/chart/render + divergences 分歧清单 (JSON) |
| 行为断言 | `__archPage.verify({before, expandKeys})` | `{pass, checks}` 结构化自检 |
| 节点签名 | `__archPage.captureNodeSignature()` | 判定是否全量重建 |
| 复现链接 | `__archPage.exportUrl()` | 生成当前折叠态+区分/不区分的可复现 URL |

复现 URL 约定:
```
/system/archdata?preset=scp&fold={"MM":false,"SCP":true}&scopeHighlight=1
```
- `fold`: JSON 对象, key=分组 elementCode/id, value=collapsed (false=展开, true=折叠)
- `scopeHighlight`: 0=不区分, 1=区分



---

## 一、现状问题（为什么难排查 / 难验证）

### 1.1 状态多源、会漂移 —— 最致命
图表的"当前折叠/展开状态"至少存在**三份**副本，且可能不一致：

| 副本 | 位置 | 写入来源 |
|---|---|---|
| Store | `configStore.layoutControlConfig` | 双击/右键 `executeContextMenuAction` → `updateLayoutControlConfig` |
| 面板源 | `chartConfig.layoutControl.groups` | `syncVisibilityToChartConfig` 从 store 同步 |
| 渲染树 | `effectiveLayoutControlConfig` (= `props.layoutControlConfig` 合并结果) | `EmbeddedChartView.layoutControlConfig` computed |

现状：代码里已出现"store 说折叠、图表却显示展开"这类分歧，专门写了
`computeCollapsedDivergences` 对比。**但没有把三份做成始终可见、差异高亮、一眼能看的"真相视图"**，
全靠事后写对比函数 + 手动浏览器看。

### 1.2 验证太重、强依赖浏览器
`verifyChart` / `inspectGroups` / `computeCollapsedDivergences` 等诊断能力**只在 `?mode=debug` 下暴露**，
且必须浏览器 + 一步步看。导致排查进入"改代码 → 慢速浏览器复现 → 再改"的循环——这正是用户反复喊卡的主因。
缺少**秒级、确定性、不依赖浏览器**的验证入口。

### 1.3 复现路径不固化
虽有 `preset=scp` / `mode=debug` / `debug=scopeCodes`，但**当前具体状态（哪个分组展开、centerScopeHighlight 开关）无法编码进 URL**。
"采购供应展开后再切换有问题"是一段描述，不是一条可一键复现的链接。

### 1.4 诊断信息分散
`diag.stepMeta` / `renderSkippedCount` / `lastRenderedCode` / `expandState` / `colorState` 分散在
`window.__archPage.*` 多个角落，无统一入口、无结构化断言。

---

## 二、目标

1. **可观测**: 三份状态并排可对比，差异一眼可见，且不限于 debug 模式。
2. **可复现**: 一条 URL 编码当前展开态 + centerScopeHighlight，精确重放。
3. **可断言**: 一条秒级自检命令，读状态 → 返回 pass/fail 清单，不依赖浏览器。

---

## 三、改动点（按优先级）

### P0-1 状态真相面板（可观测）
- 复用已有 `computeCollapsedDivergences` / `inspectGroups`，但把触发条件从 `?mode=debug` 提升为
  **任意模式可用**（仍默认折叠，面板按钮或快捷键展开）。
- 面板内容：把 store / chartConfig / 渲染树三份的 `collapsed·enabled·visible` 并排，逐 group 对齐，差异行高亮。
- 目标：任何状态下都能一眼看出"哪一份说了算、哪里漂移"。
- 安全：全部只读，不写状态；独立开关可快速关闭。

### P0-2 确定性自检命令（可断言）
- 把 `verifyChart` 的断言固化为一条命令：
  `window.__archPage.verify()` → 返回结构化 `{ checks: [{name, pass, detail}] }`。
- 覆盖典型不变式（如：双击展开后切 centerScopeHighlight，采购供应 collapsed 保持 false）。
- 可在浏览器 console 一键调用，也可被脚本读取做断言。

### P1-1 URL 状态编码（可复现）
- 在 URL query 追加可选的 `fold=<json>` / `scopeHighlight=0|1` 参数。
- 加载时若存在，则应用到 store + chartConfig，实现"一条链接精确复现"。
- 提供 `window.__archPage.exportUrl()` 生成当前状态的复现链接。

### P1-2 诊断聚合入口（可观测/可断言）
- 新增 `window.__archPage.diag()`：一次返回 `{ config, storeLayout, chartLayout, renderLayout,
  expandState, colorState, renderMeta(stepMeta/renderSkippedCount/lastRender), divergences }`。
- 所有数据同一对象、结构化、可被单测/脚本断言。

---

## 四、Dogfood 工作流（用新能力定位遗留折叠 bug）

> 目标 bug: 双击展开"采购供应"到服务模块 → 切换"区分/不区分" → 采购供应折叠回去（用户实测仍存在）。

已有进展: 单测 [foldPreservation.spec.js](src/services/groupModel/__tests__/foldPreservation.spec.js) 已锁定
"`groupManualSet=true` → 保留展开 / `false` → 折叠回单节点"的不变式，且 `markGroupManualSet()` 已在双击路径调用。

行为级断言 (2026-08-09 落地): 一条 console 命令客观判定"未重建 + 展开保持"，不再肉眼看。
```
// 1. 双击展开"采购供应"到服务模块后，抓取切换前签名
const b = __archPage.captureNodeSignature()      // { hash, nodeCount, clusterCount, edgeCount }
// 2. 切换"区分/不区分业务对象"
__archPage.debug.store.updateCenterScopeHighlight(true)  // 或 UI 按钮
// 3. 一键断言: 未发生全量重建 + SD_MM/SM_PUM 保持展开
const r = __archPage.verify({ before: b, expandKeys: ['SD_MM', 'SM_PUM'] })
r.pass   // false → 某条断言失败; 逐项看 r.checks[].detail 定位
```
判定依据: `no-full-rebuild` 比对节点签名 hash（全量重建会重编号节点 id → hash 变）；
`expanded-kept:<key>` 检查 store/chart/render 三份该分组 collapsed 是否均为 false。

**仍存在 bug 的可能根因（待用真相面板确认）**:
- A. 双击展开的 expanded 状态**未可靠同步**到 `chartConfig.layoutControl.groups`（`syncVisibilityToChartConfig` 匹配失败）。
- B. 切换 centerScopeHighlight 时，另有路径触发 `generateDiagram()` 全量重建，重建时丢失手动展开。
- C. `markGroupManualSet()` 在真实双击路径未被触发（事件被拦截）。

**利用 P0-1 真相面板逐一排除**:
1. 双击展开后，立即开真相面板看 store/chartConfig/渲染树三份的 `SD_MM`(采购供应) 与 `SM_PUM`/`SM_INV`(服务模块) `collapsed`。
   - 若 chartConfig 仍为 collapsed=true → 根因 A（同步失败）→ 查 `syncVisibilityToChartConfig`。
   - 若三份都正确展开 → 排除 A。
2. 切 centerScopeHighlight 后，再看三份 + `diag().renderMeta`：
   - 若 `renderSkippedCount` 未增 / `lastRenderedCode` 未变 → 未全量重建 → 根因 C 或渲染层逻辑。
   - 若发生全量重建 → 根因 B → 定位触发 generateDiagram 的那条 watch。

---

## 五、落地顺序与验证

1. P1-2 诊断聚合 → P0-2 自检命令（先有"读状态 + 断言"能力，成本最低）。
2. P0-1 真相面板（用 1 的能力渲染）。
3. P1-1 URL 编码（复用 1 的导出）。
4. 用 1-3 对遗留折叠 bug 做 dogfood 定位 → 修复 → 补单测。

验证方式：优先单测（秒级）+ `verify()` 自检命令；浏览器仅作最终确认，不用于逐步调试循环。

---

## 六、评审点（review 时请确认）

- [ ] 四项改进范围是否恰当，是否有过度设计？
- [ ] P0 两项是否应优先做（先"能看能断言"再谈其它）？
- [ ] 真相面板/诊断入口的默认形态（面板 vs console API）是否符合你习惯？
- [ ] 折叠 bug 的三个候选根因 A/B/C 是否有遗漏？

---

## 七、复盘教训固化（2026-08-10）— 从实战提炼的「可复现/可排查/可验证」硬约束

> 源自本次「双击展开→切区分/不区分→全量重建」问题的完整排查过程。这些教训是**方法论层面**的,
> 已部分固化为代码(见 §〇 能力), 后续排查/新能力开发必须遵守。

### S1. 诊断判断绝不借用"会失效的对比对象"（可排查，最致命）
- **现象**: 为修折叠改用"原地修改"(引用不变)后, deep watch 的 `oldVal === newVal`,
  `centerScopeHighlightChanged` 恒 false → 切换恒走全量重建。此前靠 `oldVal` diff 的判断**静默失效**, 肉眼不可见。
- **本质**: 排查工具的正确性依赖了被排查代码里一个易变前提(对象引用差异)。
- **铁律**: **状态 diff 判断不依赖"引用差异", 依赖显式快照对比**。
- **落地**: `createColorStateTracker`（`last*` 快照 + `changed()/snapshot()`），颜色字段统一走它。
  → 未来任何颜色字段改"原地修改"路径都安全。

### S2. 优先模型层断言, SVG 层只作最终确认（可验证稳定）
- **现象**: headless 下双击展开后 SVG 节点数 11→52 需秒级, 滞后期间抓基线会把"延迟渲染完成"
  误判为"切换导致重建"（脚本反复假失败/假通过）。
- **铁律**: 用 `lastRender.incremental`（是否走 updateColorsOnly）等**模型层事实**做断言;
  `captureNodeSignature`（依赖 mermaid 重渲染）只作最终确认, 不作逐步调试判据。

### S3. flaky 问题必须"连续多轮 + 稳定判据"（可复现）
- **现象**: 用户"第一次正常、第三次有问题"。单次观察不可靠。
- **铁律**: 时序依赖的 flaky 用脚本连续多轮 + 模型层稳定判据（见 `diag_three_toggle.py`）。

### S4. 状态必须可编码进 URL（可复现）
- **现象**: 此前"采购供应展开后再切换"是一段描述, 不是可一键重放的链接。
- **落地**: `?fold=<json>&scopeHighlight=0|1` + `exportUrl()`（见 §〇）。

### 可发现性要求（能力必须容易被人知道）
- **铁律**: 新增诊断/验证能力必须**同步注册到 `window.__archPage.help()` 能力清单**,
  否则视为"没做"（别人不知道等于不存在）。文档 §〇 是权威索引。


