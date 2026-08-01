# chart_diag.py — EmbeddedChartView 一键诊断工具

> **目的**: 把"排查 EmbeddedChartView 问题"这件事从写一次性 `diag_*.py` 脚本升级为参数化、可复用的工具调用。

---

## 背景

排查 chart 相关 bug 时, AI 反复需要:

| 重复步骤 | 原做法 | 新做法 |
|---------|--------|--------|
| 一键打开图表 (含产品/版本/scope) | 10 行 setup | `diag.open_chart(scope=...)` |
| 重置 mermaid-content transform | dblclick 模拟 | `diag.reset_transform()` |
| 点击元素 (避开 playwright pointer 模拟) | dispatchEvent + 8 行 | `diag.click(selector)` |
| 测量元素屏幕位置 + wrapper center | evaluate 30 行 | `diag.measure(selector)` |
| 点击 + 断言居中 | verify_center_v2.py 50 行 | `diag.click_and_assert_centered(selector)` |
| 对比 path 的 3 种中心算法 | 写 4 个 diag_*.py | `diag.compare_path_centers()` |
| 捕获 click 重复触发链 | 手写 console hook | `diag.trace_click_listeners(sel)` |
| 一键 dump 图表状态 (含渲染耗时) | 临时加 console.log | `diag.dump_state()` + `useDiagnostics` |
| 跑回归同时输出渲染性能报告 | 手动 grep console | `chart_diag regression` 自动报告 |

**节省**: 单个 bug 排查从 ~30 分钟 (写脚本 + 调通) 降到 ~3 分钟 (复用 + 即时反馈)。

---

## 使用

### 1. 一键回归测试 (CI 也可跑)

```bash
python -m test_helpers.chart_diag regression
```

输出:
```
=== click center 回归测试  viewport=(1280, 720) ===
[OK] svg g.node[data-code][0]    diff=(0.0, 0.0)
[OK] svg g.cluster[0]            diff=(-0.0, 0.0)
[OK] g.edgeLabel[0]              diff=(-0.0, 0.0)
[OK] path.flowchart-link[0]      diff=(0.0, -0.0)

--- 副测试: empty click 不动 (验证 v3 修复) ---
  [OK] svg root 空白处 (左上角)                   transform 未变
  [OK] g.subgraphs (cluster 集合层, 透明 wrapper) transform 未变
  [OK] g.subgraph (单 cluster wrapper, 单数)       transform 未变
  [OK] g.root (顶层 SVG group)                    transform 未变
=== 总结: 5/5 通过 ===

=== 渲染性能报告 (useDiagnostics.lastRender) ===
  durationMs: 1234 ms
  layoutEngine: elk
  nodeCount: 41
  edgeCount: 38
  containerCount: 28
  stepTimings:
    process_svg: 113.2 ms
  stepMeta (key=calls):
    setupCanvasLayout: 2 entries
    processSvg: 1 entries
    addLinkCodeAttributes: 1 entries
    addBidirectionalAttributes: 2 entries
```

4 个测试场景:
- **node**: 点击业务对象节点, 应当精确居中到 wrapper center
- **container**: 点击 cluster 容器 (mermaid 11 ELK g.cluster 有 id)
- **label**: 点击连线标签 (g.edgeLabel > foreignObject)
- **path**: 点击连线本身 (path.flowchart-link)

### 2. 对比 path 的中心算法

```bash
python -m test_helpers.chart_diag compare --n 5
```

列出前 5 个 flowchart-link path 的三种"中心"算法:
- `mid`: `getPointAtLength(totalLen/2) + getScreenCTM` — 沿 stroke 走到一半
- `bbox`: `getBBox + getScreenCTM` — 几何包围盒中心 (当前算法)
- `rect`: `getBoundingClientRect` — 屏幕 rect 中心 (含 stroke + 父 transform)

适用: 在排查"中心位置错"类 bug 时, 直观看出**哪种中心对应用户视觉感知**。

### 3. 捕获 click 触发链

```bash
python -m test_helpers.chart_diag trace --sel 'svg g.edgeLabel'
```

输出每个 click event 在 capture/bubble 阶段分别触发了哪些 listener, 调了几次。

适用: 排查"transform 累加"类 bug — 单次 click 触发 onSvgClick N 次会导致 dx/dy 被累加 N 次。

### 4. 一键 dump 完整状态

```python
from test_helpers.chart_diag import ChartDiag
with ChartDiag() as diag:
    diag.open_chart()
    state = diag.dump_state()
    # state['diagnostics']['lastRender'] → { durationMs, stepTimings, mermaidCode, ... }
    # state['diagnostics']['stepMeta'] → 各步骤统计 (addLinkCodeAttributes 标了多少 edgeLabel)
    # state['diagnostics']['errors'] → ring buffer 最近 50 个错误
    # state['wrapperRect'] → wrapper 屏幕位置
```

---

## Python API

```python
from test_helpers.chart_diag import ChartDiag, DEFAULT_SCOPE, SHORT_SCOPE

with ChartDiag(viewport=(1280, 720)) as diag:
    diag.open_chart(scope=DEFAULT_SCOPE)
    diag.reset_transform()

    # 单个回归断言
    r = diag.click_and_assert_centered('svg g.node[data-code="DP01"]', tolerance=1.0)
    assert r['passed'], f"DP01 没居中: diff={r['diff']}"

    # 对比 path 中心算法 (用于排查 "click 居中错位" 类问题)
    diag.compare_path_centers(n=5)

    # 捕获 click 重复触发 (用于排查 "transform 累加" 类问题)
    diag.trace_click_listeners('svg g.edgeLabel')

    # 测量任意元素
    info = diag.measure('path.flowchart-link', index=0)
    print(info['elCenter'], info['wrapperCenter'])

    # 一键 dump 完整状态
    state = diag.dump_state()
    print(json.dumps(state, indent=2))

    # 保存截图
    diag.screenshot('after_regression')

    # 列出 svg DOM 层级
    diag.dump_dom_tree('svg.mermaid', depth=3)
```

---

## 配套模块: useDiagnostics

`test_helpers/chart_diag.py` 是 Python 端入口, 对应的 JavaScript 端核心是
`src/composables/useMermaid/core/useDiagnostics.js` — **模块级可观测性基础设施**.

### 它解决了什么

排查 chart bug 时, 反复需要在代码里加 `console.log` → 提交 → 让 AI 重新触发 → 看 console 输出, **流程极慢**.

现在所有关键模块调用 `diag.beginRender/endStep/endRender/recordError`, 数据自动收集到
`window.__archPage.mermaid.dump()`, Python 端 `diag.dump_state()` 一键读取.

### 暴露的 API

```js
window.__archPage.mermaid = {
  lastRender:    { durationMs, mermaidCode, layoutEngine, nodeCount, edgeCount, ... },
  currentRender: { startedAt, step },          // 进行中的渲染 (排查卡死场景)
  stepTimings:   { syntax_gen: 12, mermaid_run: 480, ... },  // 各步骤累计 ms
  stepMeta:      { addLinkCodeAttributes: [...], ... },     // 各步骤统计数据
  errors:        [...],   // ring buffer 50 个, 含 stack
  warnings:      [...],
  hooks: { onRenderStart, onRenderEnd, onError },  // 业务可挂回调
  dump: () => ({ ... })
}
```

### 调用点

| 模块 | 埋点 |
|------|------|
| `useMermaidRenderer.js` | `beginRender / endRender / syntax_gen / mermaid_run / post_render` |
| `useSvgProcessor.js` | `process_svg / addLinkCodeAttributes / addBidirectionalAttributes / setupCanvasLayout` |
| `MermaidComponent.vue` (renderMermaid) | `beginRender / endRender / error / warning` |

### 性能开销

- 每次渲染: 约 0.1ms (ref/object 赋值)
- 内存: stepMeta + stepTimings + errors 各 ≤ 50 项

---

## 取代的脚本

chart_diag 取代以下一次性脚本 (可清理):
- `diag_center_path.py`, `diag_first_path.py`, `diag_label_paths.py`
- `diag_label_click.py`, `diag_label_single.py`, `diag_console_label.py`
- `diag_dom_tree.py`, `diag_edgeLabels_center.py`
- `diag_layout.py`, `diag_click_node_layout.py`, `diag_node_positions.py`
- `diag_container_layout.py`, `diag_user_coords.py`, `diag_user_viewport.py`
- `diag_node_label.py`, `diag_click_listener.py`, `diag_click_node_layout.py`
- `verify_center_v2.py` (大幅简化)

---

## 排查实例: click center 错位 bug (本次回归发现)

**症状**: 用户点击 cluster 容器无响应 (不居中不高亮), 点击 node/path/label 都正常。

**排查路径**:
1. 写 chart_diag 一键回归脚本: `python -m test_helpers.chart_diag regression`
2. 发现 container FAIL, 其他 OK
3. 用 `diag.measure('svg g.cluster')` 看 click 后的位置: cluster rect 没有任何 shift
4. 用 `diag.trace_click_listeners('svg g.cluster')` 看 click 触发链: onSvgClick 跑了, 但 `findTargetFromEvent` 没识别 cluster → `clickedTargetId = null` → 整个分支跳过
5. 进一步: 实际 click event 的 `e.target` 是 `<g class="subgraphs">` (集合层), 而不是 `<g class="cluster">` (单容器). findTargetFromEvent 没匹配 subgraphs.
6. 修复: `findTargetFromEvent` 加 `subgraphs` class 识别 + 递归找子 cluster
7. 再回归: 4/4 通过

**如果当时直接手写脚本**: 至少要 1 小时 (15 个一次性脚本)。**用 chart_diag**: 5 分钟。

---

## 排查实例: 空白点击导致位置变更 (本次回归发现)

**症状**: 用户在 annotation 面板选某个备注后图表自动居中, 然后用户"随便点一下"图表空白处, 图表又跳到其他位置. 用户体验混乱.

**根因**: mermaid 11 ELK 渲染时, cluster 集合层是 `<g class="subgraphs">`, bbox 覆盖整个图表, 但本身不渲染 (透明 wrapper). 用户在空白处点击时, e.target 落到 `g.subgraphs`, `findTargetFromEvent` 上溯命中 `subgraphs` class → 触发 onCenterElement → 跳到第一个 cluster.

**修复**: 在 `findTargetFromEvent` 中, 只对**真正的 cluster** (`g.cluster`, 有 id, 用户视觉上能看到边框/背景) 触发 center. 集合层 `g.subgraphs` / `g.subgraph` 视为"透明 wrapper", 上溯命中时**直接跳过** (不返回 containerEl), 让 click 走到 `else` 分支只 clearHighlight 不居中.

**永久回归**: 副测试 4 个 case (svg root / subgraphs / subgraph / 顶层 g) 全部要求 transform 不变. 现在跑 `chart_diag regression` 会自动跑这个副测试.

---

## 排查实例: 备注联动单向 (本次回归发现)

**症状**: 用户点 annotation panel 上某条备注 → chart 联动 (高亮 + 居中), 看起来双向; 但当用户**直接点 chart 上的节点/连线**时, panel 上之前选中的那条备注"消失" (selected 视觉被清掉). 用户感知 "我点了图表, 备注面板上的选中怎么没了?"

**根因**:
```
onSvgClick → highlightTargetElement → clearAllHighlights (清 panel selected)
onItemClick → highlightTargetElement + 自己加 panel selected
              (因为紧接着 add, 用户看到的是 selected 重新加回去)
```
`highlightTargetElement` 内部 `clearAllHighlights` 把所有 `.annotation-item-selected` 清掉. `onItemClick` 在调完后**自己再加**回去, 看起来正常. `onSvgClick` 不加, 所以 panel selected 消失.

**修复 (v4)**: 拆出 `clearSvgHighlightsOnly` (只清 SVG, 不动 panel) 和 `setSelectedItems` (按 targetId 同步 panel). `highlightTargetElement` 调前者 + 后者, 实现**真正双向联动**:
- 点 panel item A → chart A 高亮 + 居中 + panel A selected
- 点 svg 节点 A (有对应 panel item) → chart A 高亮 + **不居中** + panel A selected (其他清掉)
- 点 svg 节点 B (无对应 panel item) → chart B 高亮 + **不居中** + **panel 全部保留原状** (用户已选的备注不丢失)
- 点 svg 空白 → chart 清 + panel 清 (用户明确取消选中)

**修复 (v5)**: `highlightTargetElement` 加 `options.syncPanel`:
  - 'forced' (默认, panel item 点击走这条): 始终同步 panel
  - 'auto' (chart 元素点击走这条): 有对应 item 时同步, 无对应时**保留 panel 原状**
  - false: 永远不同步 (保留接口)

**永久回归**: 副测试 3 个 case + 主回归 4 个 (chart click 不居中). 现在跑 `chart_diag regression` 自动跑 12 个 case (主 4 + empty 4 + 双向联动 3 + panel 触发监测 1).

---

## 排查实例: chart click 触发居中导致位置变更 (本次回归发现)

**症状**: 用户点 annotation 面板选备注后图表自动居中, 然后用户**随便点一下**chart 上任意位置 → 图表跳到对应位置. 视觉位置不稳, 用户体验差.

**根因 (v3 → v5 演化)**:
- v3: 修复了 "点 cluster 透明 wrapper 触发居中" bug (`.subgraphs` 不应被识别为 cluster click)
- v5: 进一步 — 即使点了真实元素 (node/path/label), 也**不**应该触发居中. 居中应只在 panel item 点击时发生.

**修复 (v5)**: `onSvgClick` 不再调 `onCenterElement`. chart click 永远不改变 transform (除空白 click 触发的 clearAllHighlights). 居中入口唯一 — `onItemClick` (panel item 点击).

**设计意图**: 与 VSCode 大纲/Figma 图层面板一致 — 选中元素不强制滚动, 用户视觉位置不动. 居中(滚到目标)只在用户**明确表达想过去**时触发 (点 panel item).

---

## 排查实例: 渲染耗时黑箱 (useDiagnostics 接入)

**症状**: 用户反馈"图表加载慢", 但不知道慢在哪一步.

**排查路径**:
1. 跑 `chart_diag regression` — 顶部直接输出 `durationMs / stepTimings / stepMeta`
2. 看到 `mermaid_run: 480ms` 占大头 → 锁定是 mermaid 引擎本身慢, 不是 JS overhead
3. 进一步加 `step('elk_load')` 埋点到 useElkLoader.js, 看到 elk_load: 320ms → 是 elk layout 算法本身慢
4. 决策: 业务方接受这个耗时, 但加 progress bar + skeleton 让用户感知更好

**如果当时直接手写脚本**: 至少要 1 小时 (15 个一次性脚本)。**用 useDiagnostics + chart_diag**: 5 分钟。

---

## 未来扩展

- `compare_layout()` — 对比两种布局引擎 (dagre vs elk) 的视觉差异
- `test_pan_zoom(zoom=2.0)` — 验证 zoom 后 click 居中仍然有效
- `replay_record(file)` — 重放之前录制的 click 序列 (用于 CI 回归)
- `dump_diff(before_state, after_state)` — 对比两次渲染的 metrics 差异