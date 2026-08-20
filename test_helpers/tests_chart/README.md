# tests_chart — 图表配置/展示模块回归套件

> **目的**: 图表模块持续迭代时, 以「回归 + 问题排查」为第一优先, 把排查到的问题**固化成可重复运行的回归用例**, 收敛散落的一次性 `diag_*`/`test_*`/`_probe_*` 脚本。

## 1. 运行方式

依赖: 前端 `3004` + 后端 `3010` 在跑 (`preflight` 会自动探活, 失败即报错)。

```bash
# 跑整套图表回归
python -m pytest test_helpers/tests_chart -m e2e -q

# 只跑某个文件 / 某个用例
python -m pytest test_helpers/tests_chart/test_layout_drag_regression.py -m e2e -q
python -m pytest test_helpers/tests_chart/test_layout_drag_regression.py::test_drag_after_group_reorder_still_works -m e2e -q
```

## 2. 标准场景

统一用 **供应链计划（SCP）** 子领域（约 30 个业务对象）——**严禁加载全部对象**（效率铁律）。
- 打开: `scenario.get_scenario_url('scp')` → `/system/archdata?...scopeCode=SCP`
- 断言数据尽量读**权威暴露面** `window.__archPage`（`debug.*` / `mermaid.snapshot()` / `storeProxy`），而非脆弱 DOM 探测。
- 已有权威读法见 `chart_diag.py`（`wait_render_stable`/`get_snapshot`/`get_layout_membership` 等）。

## 3. 共享 fixture（conftest.py）

| fixture | 作用 |
|---------|------|
| `chart_page` | 模块级打开 SCP 图表 + 收集 `pageerror` |
| `panel` | 展开"图表设置"面板，返回 `page` 供分组/拖拽交互 |

辅助函数（拖拽类，稳定可跑）：
- `row_titles(page)` — 面板分组行标题
- `drop_zone_visible(page)` — 顶层放置区是否可见
- `dragstart_group(page, title)` / `drop_group(page, src, dst)` — 拖拽模拟

> 注意: HTML5 拖拽在 headless 下**不用真实 `page.mouse`**（不可靠），用 `DragEvent`+`DataTransfer` 模拟，与既有 `_diag_drag_broken` 口径一致——足够触达拖拽处理的真实代码路径。

## 4. 收敛规范（重要）

- **新增问题修复** → 在 `tests_chart/` 下加一个 `test_<模块>_regression.py`，把该问题的**最小复现 + 断言**固化，不要只写一次性脚本。
- **一次性脚本**（`_diag_*` / `_probe_*` / `diag_*` / `test_*`）**只在临时排查时用，跑完即删**；能固化的部分沉淀进 `tests_chart/`。
- **命名**：`.py` 以 `test_` 开头，并用 `pytestmark = pytest.mark.e2e`。
- **数据源**：优先 `__archPage` 权威暴露面；确需 DOM 时用稳定 class（`.lgn-row` 等）而非文本 `find`。
- 运行超时/失败先看 `preflight` 探活信息，再判断是环境问题还是真回归。

## 5. 现有可复用资产

- `chart_diag.py`：打开图表、`wait_render_stable`、快照、布局合并链路断言
- `chart_e2e.py`：四维校验引擎（A结构/B颜色/C备注/D交互）+ golden
- `scenario_runner.py`：动作序列「复现→操作→快照→对比」
- `error_collector.py`：四层错误聚合（page/console/vue/network）
- `inject_helpers.js`：store/DOM/network 三层突变追踪