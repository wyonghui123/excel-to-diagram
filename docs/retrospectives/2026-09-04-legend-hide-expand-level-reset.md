# 复盘：图例隐藏 × 展开层级重置 —— "改了又复发、排查耗时极长" 的根因与 P0 纯治理收敛

> 日期：2026-09-04 ｜ 范围：图表模块（MermaidComponent / EmbeddedChartView / expandLevel） ｜ 状态：**P0 已实施并验证（零行为变更）**；P1/P2 记入 backlog 本次不执行
> 复现载体：主仓 dev（localhost:3005 + backend 3011），SCP 子领域；正式回归探针 `test_helpers/chart_probe_legend_reset.py`
> 关联历史：2026-08-12 旧规则 → 2026-08-14 VIS-RESET（切层级重置用户隐藏）→ 2026-09-03 复发 → 2026-09-04 P0 收敛

## 一、症状与用户确认的目标语义

在图示页点击图例隐藏「✎供应网络」(SNC)，随后切换全局展开层级（subDomain → serviceModule）时，已折叠/隐藏的聚合节点重新出现，尽管 store 与图例仍标记为 hidden —— 三处状态不一致。

用户确认语义（方案 B，本次 P0 对齐目标）：

| 分支 | 操作 | 目标行为 |
|------|------|---------|
| A | 图例/面板直接点击隐藏（**不**切层级） | store + 面板树 + SVG 三者一致隐藏，稳定可用、不被误重置 |
| B | 用户显式切换全局展开层级（expandLevelUserSet=true） | **重置为全显**：清空 store 与面板树的用户隐藏位并同步 SVG（排除 ELK 系统自动分组与自定义原始组） |

## 二、为什么这个问题花了"非常多的时间"（根因复盘）

### 2.1 可见性状态存在 3~4 处镜像载体，天然易失同步

1. `store.layoutControlConfig.groups` —— 渲染权威
2. `chartConfig.layoutControl.groups` —— 面板树（LayoutControlPanel v-model）
3. `layoutControlConfig` computed —— 派生 render view
4. SVG `style.display` —— 运行时副作用（`updateVisibilityOnly` 写入）

**每处都能表达"隐藏"，但没有单一真相源**；谁在何时写哪份，全靠调用点自觉。

### 2.2 reset 逻辑四处复制粘贴，新增入口必漏 reset

"setExpandLevel + clone + resetVisible + updateLayoutControlConfig" 这一段曾被复制到：
`executeGlobalExpand`（右键）、`debug.setExpandLevel`（调试）、`LayoutControlPanel.handleExpandToLevel`（面板本地 config）、`EmbeddedChartView` watcher（跨组件同步）。

复制粘贴的直接后果：后续任何新增"切层级"入口，**大概率漏掉 reset** → 图例隐藏残留 → 2026-09-03 复发。复发不是新逻辑写错，而是**旧逻辑散落多处、改了一处漏了另一处**。

### 2.3 探针断言"拿错语义层" → 假失败，误导排查方向（v11 教训）

`probe_legend_v11` 类断言用 `COLLAPSE_SM_SNC` 去 subDomain 层找 node，两个错误假设：

- 该聚合节点（`COLLAPSE_SM_SNC`）是 **container/cluster** 而非 `g.node`，切到 subDomain 层后根本不存在；
- SNC 折叠子分组是 **ELK inner group**（`_elkGroup='inner'`），其 `visible=false` 是布局内在（无标题框），**不属于用户隐藏语义**；`collectHiddenState` / `expandLevel.isElkSystemAuto` 早已排除。

探针在错误的语义层断言 → 判"真实 bug"→ 大量时间排查并不存在的缺陷。

### 2.4 固定 sleep 采样构造"竞态窗口"（v11 假失败第二根因）

旧探针在操作后 sleep 固定毫秒再采样；而历史补丁残留了 `setTimeout(resetAll, 400/900)` 的收敛重试。探针恰好在未收敛窗口采样 → 误判。**实测证明 400/900ms 重试冗余**：清掉后 probe 6/6 全过，唯一需要的只是 `setTimeout(resetAll, 0)` 把 reset 排到 `setExpandLevel` 自身 `updateLayoutControlConfig` 之后。

### 2.5 ELK 系统分组"双重语义"是隐蔽背景噪声

`_elkGroup=inner/boundary` 在布局侧承载"是否渲染有标题盒"，而压平的扁平 serviceModule 也可能被打上 `_elkGroup`（污染，见 2026-08-21 复盘）。导致"哪些 `visible=false` 算用户隐藏"的口径分散在 `isElkSystemAuto` / `collectHiddenState` / `expandLevel` 三处，任何一处漂移都会制造假象。

> 一句话总结：**复发 = 三处镜像状态 × 四处复制粘贴 reset × 探针断言选错语义层 × 固定 sleep 竞态采样**，四者叠加才把单个 bug 拖成超长排查。

## 三、P0 治理措施（已实施，零行为变更）

> P0 原则：只收敛代码组织与可验证性，**不改任何用户可见行为**（A/B 分支语义本就是目标语义，本次不触碰）。

### P0-1 收敛"切层级重置"为唯一入口 `expandGlobalToLevel`

- `src/components/MermaidComponent.vue` L2265 新增 `expandGlobalToLevel(key)`（setExpandLevel + clone + resetVisible + updateLayoutControlConfig 的唯一实现）。
- `executeGlobalExpand`（右键）与 `debug.setExpandLevel`（调试）改为复用它，删除复制粘贴副本。
- 保留 `LayoutControlPanel.handleExpandToLevel` 面板本地 reset：AADiagramApp/LayoutSelector 场景无 EmbeddedChartView 的 VIS-RESET-SYNC watcher，面板树必须自 reset 后 emit —— 处理的是**不同树**（面板 localConfig vs 渲染配置树），不属重复。

### P0-2 debug API 新增 `visibilitySnapshot()` 四层统一快照（只读）

`MermaidComponent.vue` L3494，一次调用返回：

- `ctx`：expandLevel / expandLevelUserSet
- `store` / `chart`（面板树）items 全量
- `storeUserHidden` / `chartUserHidden`：**已排除 ELK 系统分组**的用户隐藏 code 列表（统一口径）
- `svg`：`updateVisibilityOnly` 置 display:none 的节点/聚合/容器实况
- `hiddenMeta`：`collectHiddenState` 分类（nodeCodes/containerCodes/collapseIds）

→ 探针一律消费该快照，杜绝各自拼装 DOM/store 断言再"拿错层"。

### P0-3 探针模板化 + 唯一正式回归探针入仓

- 新增 `test_helpers/chart_probe_base.py`：`ChartProbe`（登录/直达图表/`legend_click`/`set_expand_level`/`snapshot`/`wait_until_snapshot` 轮询）+ `CheckCollector`。核心教训落进骨架：确定性 debug API、事件驱动稳态（**禁固定 sleep**）、统一四层快照断言。
- 正式探针迁移为 `test_helpers/chart_probe_legend_reset.py`（自 probe_legend_v10 迁移）。
- **治理修正**：`probe_legend_v10.py` 原名被 `.gitignore` 的 `probe_*.py`（有意忽略历史临时探针 v2~v9）误伤 → 正式探针**移入 `chart_probe_*` 家族命名**（与 chart_probe_base.py 同族），脱离忽略规则，确保入仓可追溯。
- 清理本 saga 调试期临时脚本：probe_legend_v2~v5、v11~v14、repro_legend_hide.py。

### P0-4 EmbeddedChartView watcher 清理冗余重试

`src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` L801-827：删除 `setTimeout(resetAll, 400)` 与 `setTimeout(resetAll, 900)`（实测冗余且有害），保留 `resetAll()` + `setTimeout(resetAll, 0)` 一次收敛。

## 四、验证

| 层 | 结果 |
|----|------|
| 正式回归探针（改名前的 probe_legend_v10 内容，6/6） | A.click hides SNC in store / A.panel user-hidden / A.svg display=none / B.store cleared / B.panel cleared / B.svg visible —— **ALL PASS** |
| 单测回归 `vitest run`（3 文件 33 tests） | collectHiddenState 24 + elkSubGroupsInjector 7 + scaleGuardEntry 2 —— **全过**（证明收敛未破坏既有可见性语义） |

## 五、P1/P2 backlog（本次不执行，仅记录）

- **[P1]** 语义收敛：`_userHidden` 独立字段承载"用户隐藏"，与 `visible`（布局/渲染字段）分离 —— 治本，消掉"同一字段混两套语义"的根。影响面大（涉及 store 结构、序列化、collectHiddenState/expandLevel 全链路），须单独排期 + 数据迁移评估。
- **[P2]** 统一 ELK 排除口径为一个共享 helper（`isElkSystemAuto` / `collectHiddenState` / `expandLevel` 三处目前各有一份判断），防止再次漂移。P0-1 已收敛 reset 入口，但口径函数仍分散。

## 六、关键教训（写给未来的排查者）

1. **画 reset 前先验证"延迟来源"**：先判断是真实覆盖回写、还是探针采样时序问题，再决定补丁方向；补丁用轮询稳态验证而非固定 sleep。
2. **探针断言先选对语义层**：目标 node 在该层级是否真的存在？是 container 还是 node？是否属于 ELK 排除域（用户隐藏 vs 布局内在）？
3. **复制粘贴的"状态变换"逻辑必然漂移** → 收敛唯一入口 + 提供跨载体统一快照（visibilitySnapshot）让断言有单一事实。
4. **多载体状态的 bug 复发，先盘点载体与写入点清单**（本复盘 2.1/2.2），比逐点试错快一个量级。

## 七、改动文件清单

| 文件 | 改动 |
|------|------|
| `src/components/MermaidComponent.vue` | P0-1 收敛 `expandGlobalToLevel`（L2265）；P0-2 `visibilitySnapshot()`（L3494）；`setExpandLevel` 复用统一入口（L3635） |
| `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` | P0-4 VIS-RESET-SYNC watcher 清 400/900 setTimeout（L801-827） |
| `test_helpers/chart_probe_base.py` | P0-3 新增 ChartProbe / CheckCollector 共享骨架 |
| `test_helpers/chart_probe_legend_reset.py` | P0-3 唯一正式回归探针（自 probe_legend_v10 迁移改名，脱离 probe_* 忽略规则） |
| `test_helpers/probe_legend_v2~v5 / v11~v14 / repro_legend_hide.py` | 删除（调试期临时脚本） |

> 注：工作区另有**本 P0 之前已存在**的未提交改动（`collectHiddenState.js` 及 spec、`vite.config.js`、`tools/_deploy_delta_staging.py`、`cookies_qa.txt` 删除、`.runtime/`），不属于本次 P0 范围，commit 前请单独确认归属。

## 八、参考文件

- `src/components/MermaidComponent.vue` L2255-2280（P0-1）、L3481-3495+（P0-2）、L3635（setExpandLevel）
- `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` L801-827（VIS-RESET-SYNC）
- `src/services/expandLevel.js`（resetVisible 语义）；`src/composables/useMermaid/visibility/collectHiddenState.js`（ELK 排除）
- 既有复盘：`docs/retrospectives/2026-08-21-hide-full-render-elkgroup-pollution.md`（ELK 污染同源背景）
