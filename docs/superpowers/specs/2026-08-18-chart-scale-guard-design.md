# 图表规模防护（Chart Scale Guard）设计

> 日期: 2026-08-18 | 状态: 已确认阈值, 待实施 | 关联: 架构数据管理图表展示 (Mermaid)

## 一、背景与目标

### 问题
用户选择大量业务对象 + 深度展开时:
1. **性能**: mermaid 全量重渲染, 节点/关系过多导致渲染秒级→分钟级卡顿, 甚至渲染塌陷
2. **可读性**: 超规模后图表变成"毛线团", 交叉关系不可读, 失去架构全貌意义

### 目标
在**渲染/展开前**用可见节点/关系数做**双层阈值拦截**:
- **软警告线**(可读性): 超限仍可渲染, 给非阻断提示 + 一键聚合兜底
- **阻止线**(性能/内存): 阻断渲染, 引导缩小范围或聚合到高层

### 非目标
- 不做渐进加载/虚拟渲染 (远期增强)
- 不改 mermaid 渲染引擎

## 二、校准数据 (合成基准, 2026-08-18)

应用同版本 mermaid 11.13.0 + @mermaid-js/layout-elk, 本机 vite dev, headless Chromium。
基准工具: `test_helpers/calibrate_scale.py` + 临时 `benchmark.html` / `src/bench/mermaid-bench.js`。

### 节点扫 (边 ≈ 1.2N, ELK)
| 可见节点 | 渲染 | 画布 WxH |
|---|---|---|
| 80 | 0.5s | 6k×4k |
| 240 | 2.3s | 34k×10k |
| 320 | 4.8s | 42k×14k |
| 400 | 7.7s | 61k×18k |
| 600 | 22s | 106k×26k |
| 1200 | 156s | 203k×55k |
| 1600+ | 渲染塌陷(仅1节点) | — |

dagre 在 ~320 节点崩溃 (`setting 'order'`) → 应用自动回退 ELK。

### 关系扫 (固定 150 节点, ELK) — 主导成本
| 可见关系 | 渲染 | 画布 WxH |
|---|---|---|
| 200 | 0.9s | 13k×7k |
| 400 | 3.3s | 14k×14k |
| 600 | 8.8s | 14k×18k |
| 1000 | 25s | 21k×33k |
| 1500 | 130s | 29k×48k |

**结论: 关系数是主导成本。** 节点不变时, 关系 200→1000 把渲染从 1s 推到 25s。
3s 渲染线 ≈ 400 关系; 1000 关系 = 25s 不可用; 1500+ 分钟级。

## 三、阈值 (已确认)

| 阈值 | 可见关系 | 可见节点 | 依据 |
|---|---|---|---|
| **软警告线** | > **300** | > **250** | 300 关系 ≈ 2-3s 仍可导航; 之后交叉开始不可读。交互功能(高亮/配色/隐藏/折叠)可消化远超 50-100 认知红线 |
| **阻止线** | > **600** | > **400** | 600 关系 ≈ 8.8s 明显卡顿; 1000 关系 25s / 1500 130s 不可用——硬线拦在灾难前 |

- **关系为主指标**(触发判定), 节点为辅(兜底)
- **锚定 ELK**(主引擎)曲线; dagre 若可用反而更快, 自动被覆盖
- 均为配置项, 可调; 仅前端生效, 不影响数据

## 四、架构

### 4.1 可见数预估器 (纯函数, 无 Vue/mermaid 依赖)

**模块**: `src/services/scaleGuard/estimator.js`

```
输入: { selectedBoCodes[], relations[{src,tgt}], currentLevel, pendingExpandNode? }
输出: { nodes, relations, level }
```

**节点预估**:
- 预构建 `BO → 祖先路径` + 各层 `child_count` 聚合 (领域=Σ子领域, 子领域=ΣSM, SM=BO 数)
- 给定折叠层级 L: 可见节点 = 当前层容器数 + 已展开分支叶子数
- 展开节点 X: `可见_new = 可见_now + subtree_size(X) − 1`

**关系预估 (第一指标, 必须算准)**:
- 对每条关系 `(src BO, tgt BO)`, 把两端映射到当前层级的可见祖先
- 双端都落在可见集合 → 计 1 条可见关系
- 星型/毛线团爆炸可被关系线捕捉

**准确性**: 单测对拍"实际渲染的 mermaid 节点/边数"。

### 4.2 判定器 + 文案

**模块**: `src/services/scaleGuard/guard.js`
- `classify(counts) → 'ok' | 'soft' | 'hard'` (基于 config 阈值)
- 生成软/硬提示文案 (关系数优先表述)

### 4.3 拦截接入点

**① 进入图表时** (EmbeddedChartView, 数据就绪 / `mermaid.run()` 前)
- 用默认展开层级估算可见数 → `classify`
- **soft**: 照常渲染 + 顶部非阻断横幅: "当前图含 N 关系 / M 节点, 超出推荐可读范围, 建议缩小对象范围或折叠到服务模块层" + 按钮「一键折叠到服务模块层」+ 可关闭
- **hard**: 阻断渲染 + 弹窗: "所选范围过大 (预估 N 关系 / M 节点), 渲染会明显卡顿。请选择: ① 折叠到服务模块层展示 ② 返回缩小对象范围"

**② 展开交互时** (MermaidComponent `handleDblClick` / 右键菜单展开)
- 预估 `当前可见 + 该子树` → `classify`
- **soft**: 允许展开 + toast: "展开后可见关系将达 N, 可能影响阅读; 已折叠分支可用右键折叠"
- **hard**: 阻止本次展开 + toast: "展开将导致约 N 关系渲染, 可能卡顿; 请先折叠其他分支或缩小范围"

**③ 兜底保险 (渲染后检测)**
- 渲染完成后统计实际可见数; 若仍超硬线 (预估误差), 自动提示 + 「折叠到服务模块层」按钮
- 独立开关 `renderCheck` (默认开)

### 4.4 配置与开关

**模块**: `configStore` 新增 `scopeGuard`:

```js
scopeGuard: {
  enabled: true,          // 总开关 (feature flag, 可一键关闭所有拦截)
  // 按引擎双阈值结构; 当前 ELK 为主引擎, 实际生效以 ELK 为准。
  // 注: dagre 实际在 ~320 节点即崩溃, 其阈值保持与 ELK 一致(保守),
  //     结构上独立便于未来 ELK/dagre 各自校准调参, 互不牵制。
  elk:  { softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 },
  dagre:{ softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 },
  renderCheck: true,
}
```

- **按引擎双阈值**: ELK 为主 (实际生效), dagre 备用独立调参, 不互相牵制
- URL 参数 / localStorage 可覆盖阈值 (测试用): `?scopeGuard.hardRels=800`
- 总开关关闭 = 完全退化为现状行为

## 五、数据流

```
RelationScopeTree (范围树 emit scope-change)
  → EmbeddedChartView (数据编排)
     → 进入拦截: estimator(selectedBoCodes, relations, 默认折叠层级)
        → guard.classify → soft: 渲染+横幅 / hard: 弹窗阻断
     → MermaidComponent (mermaid.run)
        → 渲染后兜底: 统计实际可见 → 超硬线提示
        → 展开拦截: estimator(当前 + 子树) → guard.classify → toast/阻止
```

## 六、测试

1. **单元 (estimator 准确性)**: 给定 scope+level, 预估可见数 vs 实际渲染 mermaid 节点/边数 对拍一致
2. **单元 (guard 判定)**: 软/硬边界值判定
3. **交互**: 进入图表软/硬两档; 展开软/硬两档; 兜底渲染后检测
4. **回归**: SCP (30 BO / ~36 关系) 不误报; 大范围默认折叠到 SM 层不误报; 3200 全量被硬线拦截
5. **校准工具保留**: `test_helpers/calibrate_scale.py` 可重跑验证阈值

## 七、文件清单

| 操作 | 文件 | 说明 |
|---|---|---|
| 新增 | `src/services/scaleGuard/estimator.js` | 可见数预估器 (纯函数) |
| 新增 | `src/services/scaleGuard/guard.js` | 阈值判定 + 文案 |
| 新增 | `src/services/scaleGuard/index.js` | 统一出口 |
| 修改 | `src/stores/diagramConfigStore.js` (或 config) | `scopeGuard` 配置块 |
| 修改 | `src/views/.../EmbeddedChartView.vue` | 进入拦截 (横幅/弹窗) |
| 修改 | `src/components/MermaidComponent.vue` | 展开拦截 + 渲染后兜底 |
| 新增 | `src/components/common/ScaleGuardBanner.vue` | 软线横幅 |
| 新增 | `src/components/common/ScaleGuardDialog.vue` | 硬线弹窗 |
| 测试 | `src/services/scaleGuard/__tests__/estimator.spec.js` | 预估对拍 |
| 测试 | `src/services/scaleGuard/__tests__/guard.spec.js` | 判定 |
| 保留 | `benchmark.html` + `src/bench/mermaid-bench.js` | 校准基准页 (仅 vite dev 提供, 不进 build) |
| 保留 | `test_helpers/calibrate_scale.py` | 校准驱动, 可重跑验证阈值 |

## 八、风险与缓解

| 风险 | 缓解 |
|---|---|
| 预估误差 → 误放行/误拦截 | 兜底渲染后检测; 阈值对拍单测 |
| 误报 (选大范围但折叠高层) | 以"可见数"计, 天然低误报 |
| 用户想硬看大图被拦 | 软线不阻断; 硬线可配置; 总开关一键关闭 |
| dagre/ELK 行为变化 | 按引擎双阈值, 独立调参 |
