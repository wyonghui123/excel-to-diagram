# 图表展示模块 · 排查/迭代/验证 Cookbook

> 目的: 让后续排查"3 分钟搭好复现场景、10 分钟定位根因、一键回归验证"。
> 覆盖: 标准场景一键直达、debug API 速查、已知陷阱、动作序列回归。

---

## 一、快速开始

```bash
# 1) 一键拿到命名场景 URL (直接浏览器打开, 已含 scope/关系)
python -c "from test_helpers import scenario as sc; print(sc.get_scenario_url('mm-cross-domain'))"

# 2) 用动作序列自动复现+断言 (推荐)
python test_helpers/demo_scenario_mm_hide.py
```

**命名场景** (`test_helpers/scenario.py` 的 `SCENARIOS`):

| 场景名 | 内容 | 用途 |
|--------|------|------|
| `mm-cross-domain` | 采购供应(MM,339) + 所有跨领域关系 | 用户核心场景 / ELK 隐藏回归 |
| `scp` | 供应链计划(SCP) 约30 BO (scopeCode 快捷) | 标准测试范围 (效率铁律) |
| `mm-proc` | 采购供应 + 跨采购云(PROC) | 领域间关系场景 |
| `mm-fin` | 采购供应 + 跨财务云(FIN) | 同上 (财务) |
| `mm-prj` | 采购供应 + 跨项目云(PM/PRJ) | 同上 (项目) |

```python
# 编程取 scope dict (供 ChartDiag.open_chart / ScenarioRunner)
from test_helpers import scenario as sc
scope = sc.scope_dict(sub_domain='MM', relation_mode='all_cross_domain')  # {'sub_domain':[339], 'relation_ids':[...]}
```

---

## 二、debug API 速查表 (`window.__archPage.debug.*`, 需 `?mode=debug`)

| API | 作用 | 示例 |
|-----|------|------|
| `setGroupVisible(code, v)` | 隐藏/显示分组 (增量, 走 updateVisibilityOnly) | `setGroupVisible('PM', false)` |
| `setExpandLevel(key)` | 全局展开到层级 (domain/subDomain/serviceModule/businessObject) | `setExpandLevel('businessObject')` |
| `expandGroup(code, level)` | 展开单个分组子树 (level: 0域/1子域/2服务模块/99业务对象) | `expandGroup('SCM', 99)` |
| `collapseGroup(code)` | 折叠分组 | `collapseGroup('SCP')` |
| `testDblClick(selector)` | 模拟双击 SVG 元素 | `testDblClick('g.cluster[data-container-code="MM"]')` |
| `testRightClick(selector)` | 模拟右键 SVG 元素 | `testRightClick('g.cluster')` |
| `checkVisibility()` | 列出所有隐藏分组 | `checkVisibility()` |
| `highlightRelations(code)` | 关系高亮 | `highlightRelations('PO201')` |
| `store` | configStore 引用 (可调 markGroupManualSet 等) | `debug.store.markGroupManualSet()` |

**只读状态** (`window.__archPage.*`): `mermaid.lastRenderedCode` / `mermaid.lastRender` / `mermaid.renderCount` / `storeProxy.layoutControlConfig` / `diagramData`。

**实时观测助手** (`window.__archPage.*`, 2026-08-15 新增, 任意模式):
| API | 作用 | 示例 |
|-----|------|------|
| `getDiagramData()` | 当前 diagramData 值 (**ref 解包**; 直接读 `.nodes`/`.links`, 避免 `__archPage.diagramData` 是 ref 需 `.value` 的坑) | `getDiagramData().nodes.length` |
| `getColorState()` | 实时颜色配置快照 (colorGroupBy/colorScheme/highlight/centerScopeColor/isCenter 统计) — **不依赖**增量路径副作用 `colorState` (全量渲染后为 null) | `getColorState()` |
| `getExpandState()` | 实时展开层级/折叠统计 (expandLevel/userSet/groupManualSet/collapsed 分层计数) | `getExpandState()` |
| `whyHidden(code)` | 一键诊断某 BO/分组"为何不可见": 是否在数据/中心范围/SVG + 分组树祖先链 (visible/collapsed) + 原因清单 | `whyHidden('PO201')` |
| `focusElement(type,id)` | 高亮+居中图表元素 (`'container'`/`'node'`, 跨类型兜底); TruthPanel 表格行点击即调用 | `focusElement('container','SCM')` |
| `exportUrl()` | 生成**完整状态快照**复现链接: fold + scopeHighlight + `cfg`(colorGroupBy/colorScheme/expandLevel/customColors, base64) | `exportUrl()` |

> 背景: `colorState`/`expandState` 原先只在增量路径 (`updateColorsOnly`) 或特定时机写入, 全量渲染后读不到;
> `diagramData` 暴露的是 Vue ref 直接 `.nodes` 返回 undefined — 排查时极易踩坑。这三个函数改为"实时计算、随时可读"。

**渲染稳定等待**: `ChartDiag.wait_render_stable()` — 读 `.embedded-chart-view__canvas[data-chart-rendered]` 标记, 替代固定 sleep (见 `test_helpers/chart_diag.py`)。

---

## 三、已知陷阱 (必读)

### 1. ELK 系统自动分组 = 不是用户隐藏 ⚠️
ELK 布局下每个服务模块自动生成「无关系/有关系」系统分组 (`_elkGroup=inner/boundary`), 其 `visible=false` 是**无边框盒但节点照常渲染**语义, **不是用户隐藏**。
- 陷阱: 把 `visible=false` 当用户隐藏处理 → 收集其下 BO 为隐藏 → 采购供应全部 BO 消失且取消隐藏不恢复 (2026-08-14 bug)。
- 处理: 涉及可见性/上提/着色的遍历必须用 `isElkSystemAuto(g)` 跳过 (`_elkGroup inner/boundary`)。已修复点: `updateVisibilityOnly.walk` / `hasVisibleContent` / `computeUplift` / `applyUpliftNodeColors` / `buildUpliftAncestorMap`。
- 新增可见性相关逻辑时, **第一件事就是判断要不要跳过 ELK 系统分组**。

### 2. `debug.expandGroup` 与右键"展开到X"的语义 (已对齐)
右键"展开到X"会 `markGroupManualSet()` (防止渲染层默认展开覆盖用户状态); 旧版 `debug.expandGroup` 不标记 → **探针展开被渲染层静默覆盖, 图表根本没到目标层级**。已修复为对齐右键语义。若再遇到"脚本展开无效", 先确认是否走了 `expandGroup`。

### 3. `data-code` 时序 / 选择器
- BO 节点 `data-code` 由 `addNodeCodeAttributes` 在 processSvg 设置; **大图渲染中快照可能读到半渲染 SVG (节点缺失)**。快照前必须 `wait_render_stable(clear_marker=True)`。
- BO 节点归属容器读最近祖先的 `data-container-code`, **不要**假设 BO 的 `data-container-code` 等于其子领域编码。

### 4. scope URL 格式
- 完整: `?scope=<base64(JSON {sub_domain, business_object, service_module, domain, relation_ids})>` — 用 `scenario.py` 生成, 不要手写。
- 快捷: `?scopeCode=SCP` (按编码选对象, 不含关系)。
- `scope` 优先于 `scopeCode`。

### 5. 终端中文乱码
Windows 控制台打印中文可能乱码。排查脚本统一: 结果写 JSON 文件 (`runner.dump()` / `scenario.py` 探针), 控制台只打 ASCII 摘要。

---

## 四、动作序列回归示例

```python
from test_helpers.scenario_runner import ScenarioRunner

runner = ScenarioRunner(scenario='mm-cross-domain')
result = runner.run([
    {'op': 'open'},
    {'op': 'expand_level', 'key': 'businessObject'},
    {'op': 'snapshot', 'name': 'init', 'watch': ['MM', 'PM']},
    {'op': 'hide', 'code': 'PM'},            # 隐藏项目云
    {'op': 'render_stable'},
    {'op': 'snapshot', 'name': 'after_hide', 'watch': ['MM', 'PM']},
    {'op': 'unhide', 'code': 'PM'},
    {'op': 'render_stable'},
    {'op': 'snapshot', 'name': 'after_unhide', 'watch': ['MM', 'PM']},
    # 回归断言: 隐藏/取消隐藏 PM 均不影响 MM 的 BO 可见性
    {'op': 'diff', 'a': 'init', 'b': 'after_hide', 'watch': ['MM'], 'expect_unchanged': True},
    {'op': 'diff', 'a': 'init', 'b': 'after_unhide', 'watch': ['MM'], 'expect_unchanged': True},
])
runner.dump('test_helpers/out/mm_hide_regression.json')
runner.close()
```

直接运行: `python test_helpers/demo_scenario_mm_hide.py`

---

## 五、回归测试

### 5.1 单元测试 (vitest, 快, 无需浏览器)

| 测试 | 覆盖修复 | 断言要点 |
|------|---------|---------|
| `useMermaid/visibility/__tests__/collectHiddenState.spec.js` | **ELK 系统分组误判 (最核心)** | 隐藏任意分组不误伤 ELK 系统分组下 BO; 空容器判定; 范围保护; 隐藏真实分组仍收集其后代 |
| `useMermaid/contextMenu/__tests__/contextMenuItems.spec.js` | 右键菜单结构 | 折叠/展开首位 + 分隔线 + 关系高亮; 全局「展开层级」小标题 + 4 项 |
| `useMermaid/tooltip/__tests__/containerStats.spec.js` | 容器统计 tooltip | BO 数量(子树+仅展示); 内部关系(两端在子树内); 兜底 layoutGroups |

运行: `npx vitest run src/composables/useMermaid/visibility src/composables/useMermaid/contextMenu src/composables/useMermaid/tooltip`

### 5.2 E2E 回归 (pytest, 需前端+后端运行)

`test_helpers/tests_chart/test_chart_regression.py` (marker: e2e):

| 测试 | 覆盖修复 |
|------|---------|
| `test_elk_hide_unhide_mm_bo_visible` | 隐藏/取消隐藏项目云不误伤采购供应 BO |
| `test_dblclick_expanded_does_not_collapse` | 双击已展开容器不折叠 |
| `test_rightclick_temporary_highlight` | 右键临时高亮出现 + 点击清除 |
| `test_context_menu_structure` | 对象/全局右键菜单结构 |

运行: `python -m pytest test_helpers/tests_chart/test_chart_regression.py -v -m e2e`

### 5.3 已知: useSvgStyle.spec.js 2 个陈旧断言 (与本次改动无关)
`fixEdgeLabelOverflow` 的 `padding` 断言仍是 `4px 8px` (代码已按 v40.4 改为 `0`) 与
`fixForeignObjectWidth` 的 `whiteSpace` 断言 — 属历史遗留陈旧测试, 待后续更新。

---

## 六、相关探针索引

| 探针 | 场景 |
|------|------|
| `demo_scenario_mm_hide.py` | ScenarioRunner 回归示例 (ELK 隐藏不误伤) |
| `probe_mm_proj_hide.py` / `probe_mm_elk_confirm.py` | 采购供应 ELK 隐藏 bug 复现/确认 |
| `probe_proc_unhide.py` / `probe_proc_scm_dblclick.py` | 隐藏→双击→取消隐藏回归 |
| `chart_e2e.py` / `chart_diag.py` | 五类断言 / 一键诊断基础设施 |
