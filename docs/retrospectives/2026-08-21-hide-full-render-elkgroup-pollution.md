# 复盘：隐藏分组触发全图 loading —— `_elkGroup` 字段被双重使用导致的误判

> 日期：2026-08-21 ｜ 范围：图表模块（useMermaid / archdata 图） ｜ 状态：**方案 A 已实施**（两分支），待运行时验证
> 复现载体：`release-merge` worktree；对照主仓：`feat/annotation-category-filter`（消费层一致、产生层仅标签转义差异，分层盘点见第四章）。

> 【2026-08-21 实施记录】方案 A 已落地：`isElkSystemAuto` 加 `groupType==='custom'` 前置，改动 3 文件×2 分支：
> - `MermaidComponent.vue` L3004（同时覆盖 L3039 sigNoFold / L3103 unhideMissing，同一 const）
> - `collectHiddenState.js` L19-21
> - `__tests__/collectHiddenState.spec.js` L60（夹具补 groupType）
> - `groupedLayout.js` L70-71 本地副本**故意不动**：改了会让隐藏的污染模块在 hasGroupContent(L214) 被判空 → 父级不渲染，破坏"隐藏≠禁用"语义。
> - 单测验证：collectHiddenState 10 + groupedLayout 51 + linkRemapper 8 全过。
> - 后续运行时验证（需先恢复 dev 后端）：探针复跑，期望 `[WATCH] sig changed=false` + 无 loading。

## 一、症状

在图示页点击图例 / 配置树"隐藏"一个**服务模块**（如「供应网络」SNC）：
- 期望：隐藏是**增量**操作（`updateVisibilityOnly`，只隐藏该容器框，不重排、不闪屏）。
- 实际：整图进入 loading，走了**全量 `renderMermaid()`** 重渲染。

实测日志（点击「供应网络」后）：
```
[WATCH] layoutControlConfig sig changed=true   ← 结构签名发生变化 → renderMermaid() 全量重渲
```

## 二、关键语义：隐藏（visible）≠ 禁用（enabled）

这是理解本问题的前提，两条是完全独立的路径：

| 操作 | 字段 | 语义 | 预期实现 |
|------|------|------|---------|
| 隐藏 | `visible=false` | 容器框隐藏，**子孙/布局/空位保留** | **增量**：`updateVisibilityOnly` → 只对容器 `display:none`，不重排 |
| 禁用 | `enabled=false` | 该分组整棵子树**打平上浮到父级**（结构调整） | **全量**：`renderMermaid()` 重排 |

对应代码：`MermaidComponent.vue` 的结构签名已明确把 `visible` 排除在增量之外
（[L2997-2999 注释：《HIDE 2026-08-07》隐藏/显示是增量操作，不该触发全量重排。）
隐藏应走 `updateVisibilityOnly`（[L1648](file:///d:/filework/worktrees/release-merge/src/components/MermaidComponent.vue#L1648)），图例与面板两条入口都直接调用它。

## 三、为何隐藏会卷进「无关系/有关系」(`_elkGroup`)

这是本问题最绕、也最需要讲清的一点：**「无关系/有关系」本质上与隐藏无关，是 `_elkGroup` 字段被"双重使用"造成的误判。**

### 3.1 `_elkGroup` 的正常语义：标记"ELK 系统自动分组"

图表支持把服务模块下的业务对象，按"所选关系范围内是否有关联关系"自动分成两类子分组：

- `_elkGroup='inner'` = **无关系** 子分组
- `_elkGroup='boundary'` = **有关系** 子分组

这些**真正的** ELK 系统子分组满足：`groupType='custom'` 且 带 `_elkGroup`（见 `businessObjectAutoGrouper.js createElkSubGroup`、`elkSubGroupsInjector.js`）。

它们的 `visible` 决定是否渲染"有标题盒（subgraph[title]）"，属**结构变化**，因此需要全量重渲——这是**有意设计**（`MermaidComponent.vue` L3000-3003 注释《ELK-GROUP》）。`isElkSystemAuto` 就是为识别它们而设。

### 3.2 污染：压平模式下 `_elkGroup` 被标到了服务模块本体上

`businessObjectAutoGrouper.js` 里，当某服务模块**只有"无关系"节点**（或只有"有关系"节点）时，它会被**压平为单个平铺的服务模块分组**，此时代码在服务模块本体上直接打上 `_elkGroup`：

- 只含无关系节点（[L224-247](file:///d:/filework/worktrees/release-merge/src/services/autoGrouping/businessObjectAutoGrouper.js#L224-L247)）：`groupType:'serviceModule'` + `_elkGroup:'inner'`
- 只含有关系节点（[L248-271](file:///d:/filework/worktrees/release-merge/src/services/autoGrouping/businessObjectAutoGrouper.js#L248-L271)）：`groupType:'serviceModule'` + `_elkGroup:'boundary'`

即：**一个真实服务模块**（`groupType:'serviceModule'`，如 SNC）被错误打上了 `_elkGroup`。实测确认：
```
供应网络 SNC : groupType='serviceModule'  _elkGroup='inner'  groupType 真实
```

### 3.3 误判：`isElkSystemAuto` 只认 `_elkGroup` 不看 groupType

隐藏增量/全量的分流由结构签名里的 `isElkSystemAuto(g)` 决定
（[MermaidComponent.vue L3004](file:///d:/filework/worktrees/release-merge/src/components/MermaidComponent.vue#L3004)）：

```js
const isElkSystemAuto = (g) => !!g && (g._elkGroup === 'inner' || g._elkGroup === 'boundary')
// 结构签名: v: isElkSystemAuto(g) ? g.visible : undefined
```

它**只判断 `_elkGroup`，没排除真实分组（`groupType==='serviceModule'`）**。于是被污染的 SNC 满足条件 →
`isElkSystemAuto(SNC)=true` → 其 `visible` 进入**结构签名** → 点击隐藏时 `sig changed=true` → 走 `renderMermaid()` 全量重渲 → **整图 loading**。

> 一句话：隐藏本不该关心"无关系/有关系"，但压平的扁平服务模块把 `_elkGroup`(无关系/有关系标记) 写到本体上，而 upstream 的 `isElkSystemAuto` 又把 `_elkGroup` 当成了"系统自动分组"的唯一判据，导致真实模块被误判、隐藏退化成全量。

## 四、为何主仓增量、载体全量 —— 真实代码差异盘点 + 主仓环境探针

> 【2026-08-21 二次确认修正】此前断言"两分支图表源码 git diff 为空（字节级一致）"**过宽、不严谨**，特此修正为分层盘点。

### 4.1 分层盘点 `git diff feat/annotation-category-filter merge/feat-chart-into-release`

**a. 消费层 5 文件（隐藏增量/全量分流所在）—— 字节级一致，逐一 diff 为空：**
`MermaidComponent.vue` / `renderer/useSvgProcessor.js` / `annotation/annotationOverlay.js` / `color/useMermaidColors.js` / `constants/diagram.js`。
→ **隐藏分流逻辑（`isElkSystemAuto`、结构签名、L1648 `updateVisibilityOnly`）两分支完全相同**，这是本问题的真正分流点，二者一致。

**b. 产生层（syntax/layout/style）—— 用 `--ignore-cr-at-eol` 排除 EOL 噪声后，真实内容差异仅 5 文件：**
| 文件 | 差异 | 与隐藏 id 匹配的因果 |
|------|------|------|
| `layout/groupedLayout.js` | 4 行，**仅注释**（`[SEC→[2026-08-21]`） | 无逻辑改动 |
| `style/useEdgeLabelStyle.js` | 纯新增 +194（新文件，边标签样式） | 无关 |
| `syntax/_shared/arrowHelper.js` | +63/-1：新增 `sanitizeMermaidLabel`（`#XX;` 转义） | 标签转义，非 id 生成 |
| `syntax/nodeLabelTemplate.js` | +35/-1：`escapeMermaidLabelText` 改用 `sanitizeMermaidLabel` | 标签转义，非 id 生成 |
| `syntax/__tests__/nodeLabelTemplate.spec.js` | 测试用例同步 | 无关 |

→ 产生层差异集中在**标签转义方案**（release 改用 mermaid 原生 `#XX;` 防止 `innerHTML` 解码失效），**与 SM 层聚合节点 id（`flowchart-COLLAPSE_` 前缀 / `upliftNodeId`）匹配无关**。`groupedLayout.generateGroupCode`、`upliftDerivation`、`useBusinessObjectSyntax` 这两个真实分叉文件中无对应改动。`businessObjectAutoGrouper.js` 两分支一致，`_elkGroup` 污染源同源（L224-271 压平分支）。

**c. 结论：源码层面不存在"主仓 vs 载体"的隐藏行为分叉。** 两个问题的分流点都在两分支**完全一致**的代码上，差异只能由运行时数据解释。

### 4.2 运行时数据分叉（主因）

- 主仓运行时：SNC 下"无关系 + 有关系"节点**均存在** → 走**父子结构**（`businessObjectAutoGrouper.js` L196-223），父模块**不携带** `_elkGroup` → `isElkSystemAuto=false` → visible 不进结构签名 → 隐藏走**增量**。
- 载体运行时：SNC 只有"无关系"节点 → 压平为非父模块 + 携带 `_elkGroup='inner'` → 被误判 → 隐藏走**全量**。

同一模块的两处运行数据不同（关系范围多寡），决定了它是否被压平、从而是否被污染 → 表现不同。

### 4.3 主仓 dev 环境探针（2026-08-21 新增）

对主仓 dev server `localhost:3004` 跑同探针 `diag_elk_fullrender.py`，结果**无法复现主仓画面**：
- `dev-login` API 返回 **500**，页面停在「BIP应用架构管理 请登录以继续」登录页，`svg#mermaid` 始终不出现，legend 面板为空。
- 环境原因：主仓 vite(port 3004, pid15752) 的 proxy target 用默认 `BACKEND_PORT || 3010`（见 `vite.config.js` L97-102），而当前真正在跑的后端是 **3011**（pid36360），3010 无人监听 → 主仓前端所有 `/api` 一律 500。
- 载体 vite(port 3005, pid33008) 显式设了 `BACKEND_PORT=3011`，故能连通后端、探针成功复现。

> 含义：用户此前"主仓没这问题"的观察，来自其**本地浏览器真实会话**（能出图、SNC 走父子结构的运行数据），而非当前 `localhost:3004` 这个 dev server（它现在根本进不了图）。主仓 dev 环境本身需要先修 proxy/后端端口才能用探针直接对照复现。

### 4.4 SM 层（展开到服务模块）隐藏 no-op 的静态核实（2026-08-21 补充）

SM 层隐藏「无变化、无 reload」此前怀疑是聚合节点 id 两套方案错配，逐一核实后**排除**：

- `upliftNodeId(g)` = `COLLAPSE_${sanitizeId(g.id)}`（`upliftDerivation.js` L21-23）。
- `createGroupId(SERVICE_MODULE, code)` = `SM_<safeCode>`（`groupModel/types.js` L27-37）；`sanitizeId` 保留下划线 → `upliftNodeId` = `COLLAPSE_SM_<code>`。
- 容器折叠聚合节点 id（`groupedLayout.js` L789-805）= `COLLAPSE_SM_<elementRef.code>` 或 `COLLAPSE_C<n>`。
- MermaidComponent L1712-1717 从 `flowchart-COLLAPSE_<id>-<N>` 截取到首个 `-` 得到 `COLLAPSE_<id>` 再查 `hiddenCollapseIds`。

→ 三者对服务模块（g.id=`SM_<code>`）**完全一致**，折叠/上提节点隐藏路径可正常命中。容器路径（L1703-1707 按 `data-container-code`）也闭合。

**结论**：SM 层 no-op **不是** id 错配，也没有在 hide 路径上发现两分支源码差异。SM 层"无 reload"意味着隐藏根本没进结构签名（该层隐藏的服务模块未携带 `_elkGroup` 污染，或 legend 命中的是另一层级节点）；"无变化"则意味着增量 `updateVisibilityOnly` 要么未命中 SVG 元素、要么 legend 事件未触发。此点**需运行时探针进一步定位**（当前 dev 后端栈已挂，无法复现）。

> 与环境事实一并记录：`3004` 原 vite(pid15752) 已被停、`3011` 后端已不可达、`3005` 载体 vite 亦不可达 —— **当前两台 dev server 的后端链路均已断**，需人工恢复后（`start-backend-port3011.py` + `BACKEND_PORT=3011` 重启 vite）才能继续运行时对照。

## 五、修复方向（待开发智能体评估）

### 方案 A（推荐，最小）：让 `isElkSystemAuto` 只认真正的 ELK 系统子分组

真正的 ELK 系统子分组都是 `groupType='custom'`，而被污染的扁平模块是 `groupType='serviceModule'`。
在两处给判定加 `groupType==='custom'` 前置：

- `MermaidComponent.vue` L3004（驱动隐藏增量/全量分流）
- `collectHiddenState.js` L19-21 `isElkSystemAuto`（同语义，保持一致）

```js
const isElkSystemAuto = (g) => !!g
  && g.groupType === 'custom'
  && (g._elkGroup === 'inner' || g._elkGroup === 'boundary')
```

预期：被压平的 serviceModule 不再被当作系统自动分组 → `visible` 不进结构签名 → 隐藏回到 `updateVisibilityOnly` 增量。

**连带影响排查点**：`isElkSystemAuto` 还被用于：
- `MermaidComponent.vue` L3039（sigNoFold 结构签名，应同步）
- `MermaidComponent.vue` L3103（unhideMissing 收集旧隐藏态——加条件后压平模块的隐藏态会被计入，需确认取消隐藏行为不受影响）
- `useMermaidColors.js` L345-347、`groupedLayout.js` L51-71、`useBusinessObjectSyntax.js` L517/534、`linkRemapper.js` L208：这些地方**已有 `groupType==='custom'` 前置或明确按 custom 排除**，与本问题判定逻辑一致，预计无需改动，但建议核对。

### 方案 B（治本，范围更大）：消掉污染源

`businessObjectAutoGrouper.js` 压平分支（`hasInner` / `hasBoundary` 单边）不把 `_elkGroup` 打到 serviceModule 本体上，或改为与父结构统一（始终生成父模块 + 单个子分组）。改动面大，涉及布局结构，风险高，仅作备选。

## 六、验证方式

修改后，用既有探针 `test_output/diag_elk_fullrender.py`（传端口 + 目标分组名）复跑：
- 点击隐藏前：SNC 的 `_elkGroup` 仍为 `inner`（保存标记本身无错）。
- 点击隐藏后：期望 `[WATCH] layoutControlConfig sig changed=false` 且无 `renderMermaid()` 全量痕迹、loading 遮罩不出现；同时 SVG 中 SNC 容器框被隐藏（`display:none`），周围节点不重排。

## 七、参考文件

- `src/services/autoGrouping/businessObjectAutoGrouper.js`：污染源（压平分支 L224-271 打在模块本体）
- `src/views/SystemManagement/components/ArchDataChart/elkSubGroupsInjector.js`：真正的 ELK 子分组注入（custom，正确）
- `src/components/MermaidComponent.vue` L1648 `updateVisibilityOnly`、L2979-3134 隐藏增量/全量分流、L3004 `isElkSystemAuto`
- `src/composables/useMermaid/visibility/collectHiddenState.js` L19-21 `isElkSystemAuto`（保持一致）
- `src/views/SystemManagement/components/ArchDataChart/EmbeddedChartView.vue` L106/356 调用链