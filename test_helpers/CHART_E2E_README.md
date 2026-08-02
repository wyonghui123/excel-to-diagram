# chart_e2e.py — 图表 E2E 校验框架（expose 优先）

> **目的**: 把散碎的图表 E2E 校验脚本升级为**参数化、可复用的测试框架**，
> 服务于「图表展示模块的高效排查、重现与回归」——因为模块会持续迭代变更。

---

## 1. 设计原则：expose 优先

断言数据源**优先从前端统一暴露面读取**，而不是从 DOM 逐节点探测。

| 方式 | 脆弱性 | 现状 |
|------|--------|------|
| 解析 console 日志 | 格式漂移、噪音大 | 废弃 |
| 多次 `page.evaluate` DOM 探测 | 每次往返有状态漂移、选择器散落 | 降级为 fallback |
| 前端 `window.__archPage.mermaid.snapshot()` | 单次调用、结构化、权威 | **主路径** |

前端暴露面（`useDiagnostics.js` + `EmbeddedChartView.vue`）：

```js
window.__archPage.chartConfig   // 配置写入口 (FE3, E2E 切换配置)
window.__archPage.mermaid = {
  lastRender, stepTimings, stepMeta, errors, warnings,  // 渲染诊断
  dump(), snapshot()                                     // 一键导出
}
```

`snapshot()` 一次返回 `{ render, nodes, links, containers, legend, annotations }`，
Python 端 `chart_diag.get_snapshot()` 一行读取；未安装时 `chart_e2e._snap()`
自动回退为旧方法逐项探测（兼容旧前端构建）。

---

## 2. 分层架构

```
数据层     chart_fixtures.py   场景/scope/golden/数据指纹 (fingerprint)
           chart_seed.py       语义种子注入/幂等/清理 (target_code 定位)
打开层     chart_diag.py       打开图表 → 等待渲染 → show_all_annotations
断言层     chart_e2e.py        四维校验矩阵 (A/B/C/D) → PASS/FAIL 报告
```

## 3. 四层数据模型

| 层 | 文件 | 说明 |
|----|------|------|
| 数据集声明 | `chart_fixtures.py` | 5 场景（bo_short/bo_default/sm_default/bo_annotations/bo_large），scope 定义 + `scope_hash` 防 fixture 被改 |
| 种子资产 | `chart_seed.py` | 语义种子（`target_code` 业务码）+ preview 解析 `code→id`，注入幂等、清理按 `[E2E-SEED]` 前缀 |
| 行为探针 | `chart_diag.py` | 打开/等待/读取/切换的一揽子方法（`open_chart`/`wait_render_stable`/`get_snapshot`/`switch_chart_config`） |
| golden 基线 | `chart_fixtures_golden.json` | 实测指标 + 数据指纹（node_codes 全量 + scope_hash），区分「数据漂移」vs「代码回归」 |

## 4. 四维校验矩阵

| 维度 | 断言 | 数据源 |
|------|------|--------|
| **A 结构** | A1 渲染指标==golden / A2 SVG节点数==报告数 / A3 关键节点存在 / A2b 标签非空 / A3b 边端点有效 / A4 容器嵌套 / A5 节点集合==golden（数据指纹）/ A5b scope 指纹 | `snapshot.nodes/containers` + `get_render_metrics` |
| **B 颜色** | B1 nodeColorMappings 非空 / B2 SVG fill 与映射一致 / B3-B5 方案/分组/中心范围切换生效 / B6 fill 合法性 / B7 同组同色 / B8 图例完整性 / B9 link 颜色 | `snapshot.nodes.fills` + `snapshot.links` + `snapshot.legend` |
| **C 备注** | C1 items 数量==golden / C2 类型过滤生效 / C3 点击节点→item 选中 / C4 文本非空 / C5 孤儿备注 / C6 类型分布==golden | `snapshot.annotations` |
| **D 交互** | D1/D2 点击 transform 不变 / D3 图表类型切换 / D4 快速连点竞态守卫 / D5 点击高亮 / D6 panel→chart 反向联动 / D7 双击重置 | 交互中间态探测 |

## 5. 语义种子（跨环境复用）

`chart_seed.py` 用**业务 code** 代替环境 ID：

```python
DEFAULT_SEEDS = [
    {'target_type': 'business_object', 'target_code': 'DP01', 'category': 'important', ...},
    {'target_type': 'relationship',    'target_code': 'PLA001-PLD00201', 'category': 'warning', ...},
    {'target_type': 'service_module',  'target_code': 'DP', 'category': 'tip', ...},
]
```

- 注入时 `resolve_targets()` 从 preview 数据解析 `code→id`（BO/关系/SM 三个映射），解析失败抛错并附可用 code 示例（`--probe` 可探测当前环境）
- 幂等：已存在同 target+category 则 SKIP；`--cleanup` 按 `[E2E-SEED]` 前缀删除
- 覆盖四类 target × 四类 category，支撑 C 类过滤/分布断言

## 6. 使用流程

```bash
# 1. 注入语义种子（幂等，可重复执行）
python test_helpers/chart_seed.py --inject
python test_helpers/chart_seed.py --status

# 2. 生成 golden 基线（打开真实图表记录指标）
python -m test_helpers.chart_e2e --regenerate-golden

# 3. 回归：读 golden 跑四类断言
python -m test_helpers.chart_e2e
python -m test_helpers.chart_e2e --scenario bo_default --category A,B
```

## 7. 已知渲染行为约束（断言前提，勿当 bug 改）

> 以下 4 点是 2026-08-02 全量验证期间确认的**当前渲染实现的稳定行为**，
> 断言已按此适配。若未来渲染实现改变，先改断言再改实现。

1. **mermaid 11 ELK：嵌套 subgraph 渲染为平铺 cluster**。DOM 中 `g.cluster` 之间无
   包含关系、节点全部挂在顶层 `g.nodes`；嵌套通过 rect **bbox 包含**体现（内层 cluster
   画在外层 cluster 的 rect 内）。`snapshot().containers` 的 nestedClusters/maxDepth/
   leafClusters 基于 `getBoundingClientRect()` 计算（不能用 `getBBox()`——本地坐标系
   与节点 transform 不可比，也不能用 DOM contains）。
2. **recordStepMeta 嵌套数组**。`stepMeta[key]` 每次 push 形成 `[[...]]`，读取
   `nodeColorMappings` / `linkColorMappings` 必须 `.flat()`（`get_node_colors` /
   `get_center_codes` 与 snapshot 已处理）。
3. **中心节点双色**。nodeColorMappings 记录**分组原始色**，渲染时中心节点被
   `centerScopeColor` 覆盖——映射与 SVG fill 的差异是预期行为。映射带 `isCenter` 字段，
   B2 断言跳过中心节点（`get_center_codes()`）。
4. **颜色格式不一致**。SVG fill 是 `rgb(r, g, b)`，图例色块是 hex——比较必须经
   `_norm_color()` 归一化（B8/B2 已处理）。

## 8. 文件地图

| 文件 | 职责 |
|------|------|
| `src/composables/useMermaid/core/useDiagnostics.js` | 前端诊断 store + `dump()`/`snapshot()` 暴露 |
| `src/views/SystemManagement/.../EmbeddedChartView.vue` | `window.__archPage.chartConfig` 暴露 |
| `test_helpers/chart_seed.py` | 语义种子注入/幂等/清理 |
| `test_helpers/chart_diag.py` | 打开/等待/读取/切换 + `get_snapshot()` |
| `test_helpers/chart_e2e.py` | 四维校验引擎 + golden 生成 |
| `test_helpers/chart_fixtures.py` | 场景声明 + golden + 数据指纹 |
