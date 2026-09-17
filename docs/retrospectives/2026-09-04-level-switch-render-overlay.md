# 复盘：切换展开层级无"正在渲染"反馈 —— fold 路径从不触发整屏遮罩

> 日期：2026-09-04 ｜ 范围：图表模块（MermaidComponent / fold 渲染状态机） ｜ 状态：已修复并浏览器验证（dev 3005）
> 复现载体：主仓 dev（localhost:3005 + backend），SCP 子领域五节点图；时间线探针 `.runtime/chart_probe_render_overlay.py`（未入仓）
> 关联历史：A1 双缓冲平滑过渡（2026-08-10）→ CSS 补齐（2026-09-04 早间）→ 用户复报"仍无渲染中反馈" → 本修复

## TL;DR

用户切换展开层级（子领域 → 服务模块 / 业务对象）时，页面**没有任何"正在渲染，请等待"过渡反馈**：既无整屏遮罩、也无角落指示器，旧图静置约 0.5s 后突然换成新图，观感等同"冻结"。

根因不是 CSS 缺失：折叠类变化（含**全局展开层级切换**）与**单节点折叠/展开**共用同一 `layoutControlConfig` watch 分支，一律置 `foldRenderPending` → 走 A1 fold 缓冲平滑路径，**该路径从不调用 `setRendering(true)`**，自然永不出现整屏"图表渲染中"遮罩。层级切换与单节点折叠在配置里都只表现为分组树 `collapsed` 变化，此前无法区分。

修复：以 `configStore.expandLevel`（仅全局层级切换会经 `setExpandLevel` 修改）作为区分信号——**层级切换走全量渲染 `setRendering(true)` 整屏遮罩；单节点折叠/展开保留 A1 fold 缓冲**。两条浏览器探针均验证通过。

## 一、症状与用户确认的目标语义

| 分支 | 操作 | 目标行为（用户确认） |
|------|------|---------|
| A | 切换全局展开层级（domain / subDomain / serviceModule / businessObject） | **整屏遮罩**：白色背景 + "图表渲染中"，与初始渲染同款 |
| B | 单节点折叠/展开（右键 / 双击 / URL fold） | 保留 A1 双缓冲平滑过渡（新 SVG 淡入替换旧缓冲），**不闪整屏遮罩** |

用户原话要点：
- "切换展开子领域、服务模块、业务对象，系统没有展示'正在渲染 / 请等待'之类的过渡交互"
- "页面是完全静止 freeze（但图表还展示着）"
- "请你采用类似初始化展示的白色背景 + 文字（正在渲染...）"、"切层级也要整屏遮罩"

## 二、根因

### 2.1 两条渲染路径的反馈差异（状态机事实）

MermaidComponent 内置两条渲染路径：

1. **全量渲染路径**：`setRendering(true)` → `.mermaid-rendering-overlay` 整屏遮罩（"图表渲染中"），渲染期间新 SVG 隐藏（`.is-rendering svg { opacity:0 }`）。
2. **折叠渲染路径（A1）**：`foldRenderPending` → `foldRendering=true`、`captureFoldBuffer()`（旧 SVG 克隆为缓冲层保留在画面）、角落 indicator（**500ms 延迟**防快速折叠闪烁）、2s 后才升级为整屏遮罩。**全程不调用 `setRendering(true)`**。

### 2.2 层级切换被 fold 路径吞掉，是"无反馈"的直接原因

`props.layoutControlConfig` watch 对分组变化先做**签名**比较：

- `sig`（sigGroup）递归含 `co: g.collapsed === true`；
- `sigNoFold` 递归**剔除** `co`（即剔除折叠位）。

于是 `sig` 变而 `sigNoFold` 不变 = "仅折叠类变化" → 一律 `foldRenderPending = true`（watch 折叠分支）。**单节点折叠和全局层级切换都只改 `collapsed`，因此都被 fold 路径接管** → 永不出现整屏遮罩。

### 2.3 时间线探针证实：SCP 小图 531ms 内"零可见反馈"

对 domain → businessObject 做层级切换并高频采样 DOM：

```
READY: {"mc":1,"node":6}
t=  69ms [F][FB]  foldRendering=true + fold buffer (opacity=1)
t= 224ms [FB]     fold buffer 淡出 (opacity 0.887)
t= 531ms          settled — 30 nodes rendered
```

全程无 overlay、无 fold-loading（角落 indicator 500ms 延迟在渲染完成前不出现）。用户感知 = "点了没反应，页面静止"。

> 教训：**"渲染花了多久"与"用户看不看得到渲染过程"是两件事**。只要某条渲染路径承诺了过渡反馈（fold buffer），它同时就**承诺了不打扰**——但对于用户认为"应该重"的操作（切层级），"不打扰"反而变成"无反馈"。反馈策略必须按操作语义显式选择，不能按内部优化路径隐式决定。

## 三、修复（唯一文件：MermaidComponent.vue）

### 3.1 设计：区分信号选 `configStore.expandLevel`

调查了所有全局层级切换入口：

| 入口 | 是否先改 `store.expandLevel` |
|------|------|
| 空白区右键 expandGlobal → `expandGlobalToLevel` | ✅ `setExpandLevel` |
| 面板层级下拉 `LayoutControlPanel.handleExpandToLevel` | ✅ `setExpandLevel` |
| 折叠到服务模块按钮 `EmbeddedChartView.foldToServiceModule` | ✅ `setExpandLevel` |
| `debug.setExpandLevel` | ✅（经 `expandGlobalToLevel`） |
| 单节点右键/双击折叠展开 | ❌ 只 `markGroupManualSet` |

结论：**全局层级切换必先改 `store.expandLevel`；单节点折叠/展开从不改它**。这就是可靠区分信号。

### 3.2 改动点

1. 新增追踪变量并统一记录（[MermaidComponent.vue L372-397](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.vue#L372-L397)）：
   - `let lastAppliedExpandLevel = null`；
   - `setRendering(false)`（所有渲染出口：全量/折叠/跳过/错误）记录 `lastAppliedExpandLevel = configStore.expandLevel`。
   - 语义：**"上次已渲染 SVG 对应的展开层级"**。首个用户折叠必然发生在初始渲染完成之后，故初始 `null` 不会误判。

2. watch 折叠判定分支（[MermaidComponent.vue L3108-3122](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.vue#L3108-L3122)）：
   - `configStore.expandLevel !== lastAppliedExpandLevel` → **不置 `foldRenderPending`** → `renderMermaid()` 落入 `setRendering(true)` 整屏遮罩路径；
   - 相等 → 维持原 `foldRenderPending = true`（单节点折叠 A1 平滑，零回归）。

## 四、验证（浏览器前端渲染层 / dev 3005）

| 场景 | 结果 |
|---|---|
| 全局层级切换 domain → businessObject | t=202ms 出现 `[R][OV]` 整屏遮罩（文本"图表渲染中"），t=851ms 收敛淡出 ✅ |
| 单节点双击展开（dblclick `COLLAPSE_D_SCM` 领域聚合） | 走 fold 平滑（`[F][FB]` 缓冲层），**未出现**整屏遮罩，断言 PASS ✅ |

说明：SCP 小图遮罩仅约 650ms 可见；大图/大数据下层级切换渲染耗时更长，遮罩全程覆盖，正是用户诉求。单测与诊断无报错。

## 五、沉淀 / 铁律

1. **操作语义决定反馈策略，不由渲染内部路径决定。** 切全局层级 = "重操作"应整屏遮罩；单节点折叠 = "轻操作"应平滑。两者共路径实现时必须显式分流，不能只靠 A1 fold 的隐式"不打扰"。
2. **找一个"只被该操作改写的状态"作为判别信号**（这里 `store.expandLevel`），比在 watch 里做模式匹配可靠得多。单节点操作 `markGroupManualSet`、层级切换 `setExpandLevel`，互斥且各入口收敛，判别成本几乎为零。
3. **统一记录点价值**：所有渲染出口都经 `setRendering(false)`，把"上次渲染对应层级"的记录放在这里，天然覆盖全量/折叠/跳过/错误各路径，避免每个分支各自记。
4. 探针纪律沿用 2026-09-04 legend 复盘：事件驱动稳态轮询 + 语义层断言（`is-rendering` class / overlay / foldBuffer 各归各层），不用固定 sleep。

## 六、边界与风险备注

- **初始化默认展开**：`setDefaultExpandLevel`（userSet=false）不改 userSet，但会改 `expandLevel`；若它引发"仅折叠类变化"会显示一次遮罩。实践中初始化/换范围本身已伴随全量渲染遮罩，无额外观感成本。
- **连续多次队列渲染**（VIS-RESET 同步写 store + chartConfig 可能产生多次 props 更新）：第一次按层级切换进遮罩，后续同层级更新因 `lastAppliedExpandLevel` 已同步而走 fold 平滑/无变化，不会无限闪遮罩。
- **极边缘竞态**：某次折叠点击恰撞上前一个渲染正在收尾（`setRendering(false)` 在分类前把新层级记录下来）可能使该次折叠也走遮罩。概率低、观感无害（等同一次短暂全屏）。

## 七、相关文件

- 修复：`src/components/MermaidComponent.vue`（+24/-1）
- 复现/验证探针（`.runtime/`，未入仓）：`chart_probe_render_overlay.py`（层级切换遮罩时间线）、临时 `chart_probe_fold_check.py`（单节点折叠回归，已验证后删除）

---

## 附：RSS 默认展开被勾选重建覆盖（2026-09-04 同 session 反馈）

### 现象
用户二次反馈：与图表层级切换无关，"勾选 RSS 节点后约几秒，顶部分类被自动展开到第 3 层"。时序有"几秒延迟"是另一关键线索。

### 根因
我初次定位错误（猜"图表影响 RSS"），用户即时纠正"与图表无关"。重新顺链路：

1. 用户在 RSS 节点勾选 → `handleClassifierCheck` 写 `preservedCheckedKeys` → emit('scope-change')
2. `RelationScopeTree.handleRelationScopeChange` 写回 `selectedRelationCodes/Ids` 并 emit 给上层
3. 上层把 relationCodes 写入 store / props → `RelationScopeSection.props.scopeIds.relationExtra.relationCodes` 变化
4. `RelationScopeSection` 内 `classifierTreeData` 异步重建（`loadRelationships` 重新执行）
5. `watch(classifierTreeData)`（[RelationScopeSection.vue L309](file:///d:/filework/excel-to-diagram/src/components/common/RelationScopeTree/RelationScopeSection.vue#L309)）触发 → `expandDefaultLevels()` 强制展开到第 3 层
6. `watch(classifierLoading)`（L799）加载完成时同样调 → 重复展开

**"几秒延迟" = `loadRelationships` 异步拉取后端 relations 数据的耗时**。

### 修复
**一次性默认展开**：引入 `_defaultExpandApplied` ref，仅 RSS 首次挂载/首次加载完成时应用默认展开，之后用户怎么操作就怎么展示（不强行回滚到默认）。

```js
const _defaultExpandApplied = ref(false)
function expandDefaultLevelsOnce() {
  if (_defaultExpandApplied.value) return
  expandDefaultLevels()
  _defaultExpandApplied.value = true
}
// 两处调用点 (classifierTreeData watch + classifierLoading watch) 都改用 expandDefaultLevelsOnce()
```

### 教训
1. **"几秒延迟"是异步重建的指纹**——立刻想到 `loadRelationships` 这类后端 IO 链路，而不只是前端状态机。
2. **第一次定位偏差教训**：用户主动说"与图表无关"时，应该立刻停手不动现有假设（不要先射箭再画靶），先重新顺 RSS 输入端 → 重建 → 展开的全链路，而不是把已有"图表影响 RSS"猜想继续打磨。这是"听清用户否定" > "完成自己猜想"的取舍。
3. **默认展开的语义应该是"页面打开首次见到树"**，而不是"每次树重建"。重建可能来自任何源头（OSS 变更、用户勾选、refresh），用户语义要求只首次应用。

