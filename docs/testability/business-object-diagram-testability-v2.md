# 业务对象图 全交互与展示能力 - 可测试性深度分析 (v2.0)

> **分析日期**: 2026-06-11
> **触发**: 用户反馈"不只是 edge label, 需要更关注整个交互过程和视图/信息展示能力"
> **范围**: 业务对象图 (BusinessObject) + 服务模块图 (ServiceModule) 全交互流程
> **目的**: 不只测"有没有报错", 而是测"功能是否完整、视觉是否正常、交互是否正确、导出是否可用"

---

## 0. 与上一版分析的关键差异

用户明确指出: 上一版分析**过于聚焦 edge label**, 忽略了整个应用的**功能完整性**和**体验完整性**。本版将:

| 维度 | 上一版 | 本版 |
|------|--------|------|
| 测试对象 | edge label 截断 (1 个 bug) | **14 大类功能 × 60+ 测试场景** |
| 测试层级 | CSS 视觉层 | 渲染/交互/布局/导出/响应式/错误处理/可访问性 |
| 评估方法 | "测不到" | **"测得到但没人测" + "测不到需基建"** 两分法 |
| 输出 | 修复方案 | **可执行测试矩阵 + 缺失基建清单** |

---

## 1. 业务对象图全功能矩阵 (MermaidComponent + 配套)

### 1.1 完整功能地图 (14 大类)

| # | 功能大类 | 子功能数 | 关键文件 | 当前测试覆盖 |
|---|---------|---------|---------|-------------|
| 1 | **图表渲染** | 5 | MermaidComponent.vue:309 renderMermaid | ❌ 0 个 SVG 元素断言 |
| 2 | **缩放与平移** | 6 | useInteraction.js:8-167 addZoomAndPan | ❌ 0 个事件断言 |
| 3 | **节点/容器标题展示** | 4 | syntax/*.js + CSS | ❌ 0 个文字截断/换行断言 |
| 4 | **容器与子图布局** | 8 | layouts/*.js (4 种) | ❌ 0 个布局结果断言 |
| 5 | **关系连线展示** | 7 | useTooltip.js:290-447 addTrailingDottedLines | ❌ 0 个连线/拖尾/箭头断言 |
| 6 | **Tooltip 交互** | 5 | useTooltip.js:30-58 | ❌ 0 个 tooltip 断言 |
| 7 | **高亮与选择** | 4 | useTooltip.js:112-151 highlightNode | ❌ 0 个高亮断言 |
| 8 | **点击清除** | 1 | useTooltip.js:449-460 addClickToClearHighlight | ❌ 0 个清除断言 |
| 9 | **响应式/Resize** | 3 | MermaidComponent.vue relayoutAfterSizeChange | ❌ 0 个 resize 断言 |
| 10 | **全屏切换** | 3 | MermaidComponent.vue:211-307 toggleMaximize | ❌ 0 个 fullscreen 断言 |
| 11 | **布局引擎切换** | 3 | useMermaidConfig (dagre/elk) + useElkLoader | ❌ 0 个 engine diff 断言 |
| 12 | **导出功能** | 5 | exportAsPdf/exportAsHtmlFull/exportAsImage/exportAsNative/copyToClipboard | ❌ 0 个导出文件断言 |
| 13 | **错误处理** | 4 | mermaid.run catch + 5 处 try/catch | ❌ 0 个错误状态断言 |
| 14 | **Annotation 标注** | 5 | useAnnotation + useAnnotationOverlay | ❌ 0 个 annotation 断言 |

**总计: ~75 个功能场景, 0 个有针对性测试**.

### 1.2 完整数据流 (用户视角)

```
┌────────────────────────────────────────────────────────────────────┐
│ 0. 进入: 用户从管理页点 "展示图表"                                  │
│    sessionStorage 写入 → router.push → AADiagramApp mount            │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ 1. 步骤流程: StepIndicator → StepConfig → StepDisplay                │
│    - 当前步骤 (1/2/3)                                                │
│    - 颜色模式 (byDomain/byNode/custom)                              │
│    - 自定义颜色映射                                                  │
│    - 布局配置 (grouped/zone/linear/grid)                            │
│    - 布局引擎 (dagre/elk)                                           │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ 2. MermaidComponent 挂载 (StepDisplay)                              │
│    2.1 mermaid.initialize(config)  ← useMermaidConfig               │
│    2.2 mermaid.run()              ← 渲染 SVG                        │
│    2.3 注入容器                                                       │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ 3. 后处理 (post-render)                                              │
│    3.1 addCodeAttributes        ← 加 data-code 给节点/边           │
│    3.2 addTooltips              ← useTooltip                       │
│    3.3 applyContainerTitleItalic ← useSvgStyle                      │
│    3.4 addTrailingDottedLines   ← useTooltip                       │
│    3.5 applyAnnotation          ← useAnnotation                    │
│    3.6 applyAnnotationOverlay   ← useAnnotationOverlay              │
│    3.7 buildColorLegendData     ← svgProcessor (legend 数据)        │
│    3.8 hideLinkLabelTails (延迟 2s)                                │
│    3.9 applyContainerTitleItalic 再次 (延迟 800ms)                  │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ 4. 交互层                                                            │
│    4.1 滚轮缩放       wheel → scale 0.3~3, 以鼠标位置为中心        │
│    4.2 拖动平移       mousedown + mousemove + mouseup              │
│    4.3 双击重置       dblclick → autoFitDiagram                    │
│    4.4 重置按钮       toolbar.refresh → autoFit                    │
│    4.5 全屏切换       toggleMaximize → requestFullscreen           │
│    4.6 节点 hover     mouseenter → tooltip show                    │
│    4.7 边线 hover     mouseenter → tooltip show                    │
│    4.8 节点 click     highlightNode (rect stroke + font-weight)     │
│    4.9 边线 click     highlightNode source+target + path stroke     │
│    4.10 空白 click    clearHighlight                              │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ 5. 导出层                                                            │
│    5.1 PDF 导出        exportAsPdf                                  │
│         - svg → Image (5s 超时)                                    │
│         - html2canvas legend (中文)                                 │
│         - jsPDF 多页 (a4/a3/a5/letter/legal)                       │
│    5.2 HTML 彩色版     exportAsHtmlFull                              │
│         - 完整 HTML + 600 行 CSS inline                            │
│         - 双击可直接打开                                            │
│    5.3 HTML 简洁版     exportAsHtmlSimple                            │
│    5.4 复制 Mermaid 代码 copyToClipboard                            │
│    5.5 图片导出        exportAsImage (PNG/JPG)                      │
│    5.6 Native 导出     exportAsNative (浏览器内置)                   │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ 6. 异常路径                                                          │
│    6.1 mermaid 渲染失败    → try/catch → return 'graph TD\n  A[Error]' │
│    6.2 数据为空            → 静默不渲染, 显示空状态                  │
│    6.3 SVG 加载失败 (PDF)  → reject 5s timeout, "SVG 加载失败"     │
│    6.4 html2canvas 失败    → catch → console.error                  │
│    6.5 复制失败            → catch → showToast '复制失败'           │
│    6.6 Pinia store 缺失    → undefined 访问抛错                      │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. 14 大功能 × 测试场景矩阵 (60+ 场景)

### 2.1 图表渲染 (5 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| R1 | 渲染后 SVG 存在 | `.mermaid-content svg` 数量 | ✅ E2E 慢 | Playwright 验证 querySelectorAll |
| R2 | 节点数 = 数据数 | `.node` 元素数 = diagramData.nodes.length | ✅ E2E 慢 | 计数 + 等于 |
| R3 | 边数 = 关系数 | `.edgePath` 数 = diagramData.relationships.length | ✅ E2E 慢 | 计数 + 等于 |
| R4 | 节点文字内容 | `.nodeLabel` textContent = data.name | ✅ E2E 慢 | 文本匹配 |
| R5 | 重复渲染无残留 | watch 触发 3 次后 DOM 节点数仍正确 | ✅ E2E 慢 | 多次切换注入 |

### 2.2 缩放与平移 (6 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| Z1 | 滚轮放大 | wheel 上滚 → scale 1.1x | ✅ E2E 慢 | Playwright page.mouse.wheel + 读 transform |
| Z2 | 滚轮缩小 | wheel 下滚 → scale 0.9x | ✅ E2E 慢 | 同上 |
| Z3 | 缩放限制 | 持续滚轮 → scale 在 [0.3, 3] | ✅ E2E 慢 | 触发 50 次后断言 |
| Z4 | 拖动平移 | mousedown→move→up → transform | ✅ E2E 慢 | Playwright drag |
| Z5 | 双击重置 | dblclick → scale=1, translate=0 | ✅ E2E 慢 | dblclick + 断言 |
| Z6 | 全屏下交互 | toggleMaximize 后 wheel 仍触发 | ✅ E2E 慢 | 进入全屏 + wheel |

### 2.3 节点/容器标题展示 (4 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| T1 | 节点标题不截断 | foreignObject width ≥ scrollWidth | ✅ E2E 慢 | (本次 v32 修复) |
| T2 | 节点标题完整显示 | `.nodeLabel` textContent 全字符 | ✅ E2E 慢 | 字符串匹配 |
| T3 | 容器标题不截断 | `.cluster-label` 文字完整 | ✅ E2E 慢 | 字符匹配 + scrollWidth |
| T4 | 容器/子图标题正确 | subgraph 标签 = 容器 name | ✅ E2E 慢 | 文本对比 |

### 2.4 容器与子图布局 (8 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| L1 | 4 种 layoutType | grouped/zone/linear/grid | ✅ E2E 慢 | 切换 4 次 + 断言 subgraph 数量 |
| L2 | 容器内节点顺序 | container.nodes 顺序在 SVG 中保留 | ❌ happy-dom 不能 layout | E2E |
| L3 | 行布局 (zone) | row0/row1/row2 顺序 | ✅ E2E 慢 | 检查 .cluster 位置 |
| L4 | 网格布局 (grid) | 4x4 网格, 空格占位 | ✅ E2E 慢 | 检查 EmptyN 节点 |
| L5 | 整体方向 (LR/TB) | rankdir 切换 | ✅ E2E 慢 | 检查节点 x/y 关系 |
| L6 | 容器边框样式 | stroke + fill 正确 | ✅ E2E 慢 | 检查 SVG attribute |
| L7 | 容器标题位置 | cluster-label 在容器顶部居中 | ✅ E2E 慢 | BoundingClientRect |
| L8 | 节点跨容器引用 | 节点正确归位 (使用 nodeMap) | ✅ E2E 慢 | 节点 x 位置在容器内 |

### 2.5 关系连线展示 (7 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| E1 | 边线存在 | path.flowchart-link 数 = 关系数 | ✅ E2E 慢 | 计数 |
| E2 | 边线端点正确 | 起点在 source, 终点在 target | ❌ 难断言 | BoundingClientRect 容差 |
| E3 | 边线方向 | 箭头方向正确 (source→target) | ✅ E2E 慢 | 检查 marker-end |
| E4 | 曲线类型 | curve: 'basis' / 'linear' / 'cardinal' | ✅ E2E 慢 | 检查 path d 属性 |
| E5 | 拖尾虚线 | data-trailing-line 存在 | ✅ E2E 慢 | querySelector |
| E6 | 拖尾圆点 | data-trailing-marker 存在 | ✅ E2E 慢 | querySelector |
| E7 | 边线 label 背景 | rect.fill = #fff | ✅ E2E 慢 | 检查 attribute |

### 2.6 Tooltip 交互 (5 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| P1 | 节点 hover 显示 | mouseenter → tooltip 出现 | ✅ E2E 慢 | mouseenter + visibility |
| P2 | 边线 hover 显示 | mouseenter path → tooltip | ✅ E2E 慢 | 同上 |
| P3 | tooltip 内容 | relationCode + sourceName + targetName + desc | ✅ E2E 慢 | textContent 匹配 |
| P4 | tooltip 移动 | mousemove → tooltip 跟随 | ✅ E2E 慢 | 检查 left/top 变化 |
| P5 | tooltip 隐藏 | mouseleave → visibility: hidden | ✅ E2E 慢 | 检查 style |

### 2.7 高亮与选择 (4 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| H1 | 节点 click 高亮 | rect stroke = #FF6B6B | ✅ E2E 慢 | 检查 inline style |
| H2 | 节点 label 加粗 | fontWeight = bold | ✅ E2E 慢 | 检查 inline style |
| H3 | 边线 click 高亮 | path strokeWidth = 4px | ✅ E2E 慢 | 检查 inline style |
| H4 | 双节点高亮 | source + target 都高亮 | ✅ E2E 慢 | 2 个 rect 都被改 stroke |

### 2.8 点击清除 (1 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| C1 | 空白处 click 清除 | 之前高亮的 rect 恢复 stroke | ✅ E2E 慢 | click 空白 + 断言恢复 |

### 2.9 响应式 / Resize (3 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| RS1 | 窗口 resize | 容器尺寸变化, 重新 fit | ✅ E2E 慢 | setViewportSize + wait |
| RS2 | 移动端尺寸 | 320px 宽度仍可渲染 | ✅ E2E 慢 | viewport 320x800 |
| RS3 | 横屏切换 | viewport 旋转 (手机模拟) | ✅ E2E 慢 | setViewport |

### 2.10 全屏切换 (3 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| F1 | 进入全屏 | .mermaid-container.maximized | ✅ E2E 慢 | click 按钮 + classList |
| F2 | 全屏下事件触发 | wheel/drag 仍工作 | ✅ E2E 慢 | 全屏 + 触发事件 |
| F3 | 退出全屏 | 按钮切换 class | ✅ E2E 慢 | click 退出 + classList |

### 2.11 布局引擎切换 (3 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| E1 | dagre 渲染 | 节点位置由 dagre 算 | ✅ E2E 慢 | 检查 transform |
| E2 | elk 渲染 | 节点位置由 elk 算 (dagre 同位置?) | ✅ E2E 慢 | 切换 + 对比 |
| E3 | 引擎差异 | dagre vs elk 节点 x/y 不一样 | ❌ 难断言 | 容差比较 |

### 2.12 导出功能 (5 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| X1 | PDF 导出成功 | jsPDF.save() 触发下载 | ✅ E2E 中 | waitForEvent('download') |
| X2 | PDF 多页 | 高度超 1 页, 自动 addPage | ✅ E2E 中 | PDF 内部断言 |
| X3 | PDF 中文不乱码 | image 含中文 | ❌ 难断言 | 视觉对比 |
| X4 | HTML 彩色版导出 | HTML 含 mermaid + legend | ✅ E2E 中 | 检查 file 内容 |
| X5 | 复制 Mermaid 代码 | clipboard 内容 = mermaidCode | ✅ E2E 中 | clipboard.readText |

### 2.13 错误处理 (4 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| ER1 | 渲染失败降级 | 注入坏数据, 不崩溃 | ✅ E2E 慢 | 注入坏数据 + 断言 fallback |
| ER2 | 数据为空 | diagramData=null, 不渲染 | ✅ E2E 慢 | 置空 + 断言 |
| ER3 | PDF SVG 加载失败 | 5s 超时, showToast | ✅ E2E 慢 | mock 慢 SVG + 计时 |
| ER4 | 复制失败 | clipboard 不可用, catch | ✅ E2E 慢 | mock clipboard 抛错 |

### 2.14 Annotation 标注 (5 个场景)

| # | 场景 | 测什么 | 当前能测吗 | 测试方法 |
|---|------|--------|-----------|---------|
| A1 | 标注数据存在 | data-annotation-layer 元素 | ✅ E2E 慢 | querySelectorAll |
| A2 | 标注 tooltip | annotation overlay 显示 | ✅ E2E 慢 | hover 标注 |
| A3 | 中心范围高亮 | data-center-scope 属性 | ✅ E2E 慢 | 检查 attribute |
| A4 | 标注拖动 | annotation 位置改变 | ✅ E2E 慢 | drag 标注 |
| A5 | 标注编辑 | 双击进 edit 模式 | ✅ E2E 慢 | dblclick 标注 |

---

## 3. 测试覆盖率热力图

### 3.1 各维度的可测性

```
                   测得到     测得到但无测试   测不到 (需基建)
                   ✅        ⚠️            ❌
─────────────────────────────────────────────────
渲染输出 (R)        -         R1-R5         -
交互事件 (Z/H/C)    -         Z1-Z6/H1-H4/C1 -
视觉 (T/P)          -         T1-T4/P1-P5   -
布局 (L)            -         L1,L3-L7      L2 (顺序断言难)
连线 (E)            -         E1,E3-E7      E2 (端点位置难)
响应式 (RS)         -         RS1-RS3       -
全屏 (F)            -         F1-F3         -
引擎 (E11)          -         E1-E2         E3 (差异难)
导出 (X)            -         X1,X4,X5      X2-X3 (PDF 内容难)
错误 (ER)           -         ER1-ER4       -
标注 (A)            -         A1-A5         -
```

**结论**:
- **62 个场景** "测得到但无测试" (88%)
- **2 个场景** "测不到" (12%)

**意味着**: 大部分功能**可以测**, 但**没人测**. 不是工具问题, 是流程问题.

### 3.2 测试金字塔应然状态

```
                    实际          应然
                  ┌──────┐ E2E   ┌──────┐ E2E (视觉/集成/不可单测的)
                  │ 7    │       │ 30+  │
                  │ 测试 │       │ 测试 │
                  ├──────┤ 组件  ├──────┤
                  │ 0    │       │ 100+ │ 组件测试 (mount + 测 props/events)
                  ├──────┤ 单元  ├──────┤
                  │ 30+  │       │ 300+ │ 单元 (composable 逻辑)
                  │ 散乱 │       │ 集中 │
                  └──────┘       └──────┘
                  
数量: 37            →    430+ (11.6x)
```

---

## 4. 各功能的具体测试实现示例

### 4.1 渲染类 (vitest + happy-dom + mock mermaid)

**useMermaidConfig.spec.js** (4 个测试) - 测**关键配置参数**:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock mermaid
vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(() => Promise.resolve({ svg: '<svg></svg>' })),
    run: vi.fn(() => Promise.resolve())
  }
}))

import { useMermaidConfig } from '../useMermaidConfig'

describe('useMermaidConfig', () => {
  describe('业务对象图 - 关键参数', () => {
    it('wrappingWidth 应 >= 500 (容纳 ~25 中文字符, v32 修复回归)', () => {
      const { getConfig } = useMermaidConfig()
      const config = getConfig('businessObject', {}, 'dagre', 'default', false, null, 50000)
      expect(config.flowchart.wrappingWidth).toBeGreaterThanOrEqual(500)
    })

    it('nodeSpacing 应 = 80 (业务对象图标准)', () => {
      const { getConfig } = useMermaidConfig()
      const config = getConfig('businessObject', {}, 'dagre', 'default', false, null, 50000)
      expect(config.flowchart.nodeSpacing).toBe(80)
    })

    it('htmlLabels 应 = true (启用 <foreignObject>)', () => {
      const { getConfig } = useMermaidConfig()
      const config = getConfig('businessObject', {}, 'dagre', 'default', false, null, 50000)
      expect(config.flowchart.htmlLabels).toBe(true)
    })
  })

  describe('服务模块图 - 关键参数', () => {
    it('wrappingWidth 应 >= 800 (服务模块图更大)', () => {
      const { getConfig } = useMermaidConfig()
      const config = getConfig('serviceModule', {}, 'dagre', 'default', false, null, 50000)
      expect(config.flowchart.wrappingWidth).toBeGreaterThanOrEqual(800)
    })

    it('padding 应 = 25 (比业务对象大)', () => {
      const { getConfig } = useMermaidConfig()
      const config = getConfig('serviceModule', {}, 'dagre', 'default', false, null, 50000)
      expect(config.flowchart.padding).toBe(25)
    })
  })

  describe('ELK 引擎', () => {
    it('应注入 elk 配置', () => {
      const { getConfig } = useMermaidConfig()
      const config = getConfig('businessObject', {}, 'elk', 'default', false, null, 50000)
      expect(config.layout).toBe('elk')
      expect(config.elk).toBeDefined()
      expect(config.elk['elk.algorithm']).toBe('layered')
    })
  })

  describe('回流保护 (maxTextSize)', () => {
    it('节点数 > 50000 时应禁回流', () => {
      const { getConfig } = useMermaidConfig()
      const config = getConfig('businessObject', {}, 'dagre', 'default', false, null, 60000)
      expect(config.maxTextSize).toBe(100000)  // 禁回流模式
    })
  })
})
```

**useSvgStyle.spec.js** (8 个测试) - 测**后处理不影响 layout**:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useSvgStyle } from '../useSvgStyle'

describe('useSvgStyle - fixEdgeLabelOverflow (v32 回归)', () => {
  it('不应修改 foreignObject width/height (v22 端点错位 bug 防护)', () => {
    const { fixEdgeLabelOverflow } = useSvgStyle()
    const mockSvg = createMockSvg({
      edgeLabel: { foWidth: '79.44', foHeight: '17.19' }
    })
    fixEdgeLabelOverflow(mockSvg)
    expect(mockSvg.foreignObject.setAttribute).not.toHaveBeenCalledWith('width', expect.anything())
    expect(mockSvg.foreignObject.setAttribute).not.toHaveBeenCalledWith('height', expect.anything())
  })

  it('不应触及 .nodeLabel foreignObject', () => { /* ... */ })
  it('应覆盖 .labelBkg max-width', () => { /* ... */ })
  it('应只针对 edgeLabel, 不影响 cluster', () => { /* ... */ })
  it('应支持多 edge label (3 个以上)', () => { /* ... */ })
  it('无 edge label 时不报错', () => { /* ... */ })
  it('labelBkg 缺失时优雅降级', () => { /* ... */ })
  it('中文 label 不被截 (用 text-shadow + padding)', () => { /* ... */ })
})

describe('useSvgStyle - applyContainerTitleItalic', () => {
  it('容器标题应斜体 (data-italic=true)', () => { /* ... */ })
  it('不影响节点标题', () => { /* ... */ })
  it('深嵌套 cluster 也生效', () => { /* ... */ })
})
```

**useInteraction.spec.js** (6 个测试) - 测**缩放/拖动算法**:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'

// happy-dom 不支持 mouse 事件, 用 jsdom
import { JSDOM } from 'jsdom'
const dom = new JSDOM('<!DOCTYPE html>')
global.window = dom.window
global.document = dom.window.document

import { useInteraction } from '../useInteraction'

describe('useInteraction - autoFitDiagram', () => {
  it('重置后 scale = 1, translateX = 0, translateY = 0', () => {
    const { autoFitDiagram, scale, translateX, translateY } = useInteraction()
    autoFitDiagram()
    expect(scale.value).toBe(1)
    expect(translateX.value).toBe(0)
    expect(translateY.value).toBe(0)
  })
})

describe('useInteraction - 缩放限制', () => {
  it('wheel 上滚后 scale 应 * 1.1 但不超过 3', () => { /* ... */ })
  it('wheel 下滚后 scale 应 * 0.9 但不低于 0.3', () => { /* ... */ })
  it('以鼠标位置为中心缩放 (offsetX 调整)', () => { /* ... */ })
})

describe('useInteraction - 拖动', () => {
  it('mousedown 后 cursor 变 grabbing', () => { /* ... */ })
  it('mousemove 修改 translateX/Y', () => { /* ... */ })
  it('mouseup 清除 dragging 状态', () => { /* ... */ })
  it('点击 toolbar 不触发拖动', () => { /* ... */ })
})
```

### 4.2 组件测试 (vitest + @vue/test-utils)

**MermaidToolbar.spec.js** (5 个测试):

```javascript
import { mount } from '@vue/test-utils'
import MermaidComponent from '../MermaidComponent.vue'
import { vi, describe, it, expect } from 'vitest'

// mock mermaid
vi.mock('mermaid', () => ({ default: { /* ... */ } }))
vi.mock('html2canvas', () => ({ default: vi.fn() }))
vi.mock('jspdf', () => ({ jsPDF: vi.fn() }))

describe('MermaidComponent - 工具栏', () => {
  it('渲染 6 个工具按钮 (重置/全屏/复制/HTML/PDF)', () => {
    const wrapper = mount(MermaidComponent, {
      props: { diagramData: mockData, diagramType: 'businessObject' }
    })
    expect(wrapper.findAll('.toolbar-btn')).toHaveLength(5)
  })

  it('点击重置调用 autoFitDiagram', async () => {
    const wrapper = mount(MermaidComponent, { /* ... */ })
    const spy = vi.spyOn(wrapper.vm, 'resetAdaptive')
    await wrapper.find('[title="重置视图"]').trigger('click')
    expect(spy).toHaveBeenCalled()
  })

  it('全屏按钮切换 isMaximized 状态', async () => { /* ... */ })

  it('PDF 按钮调用 exportAsPdf', async () => { /* ... */ })

  it('HTML 彩色版按钮调用 exportAsHtmlFull', async () => { /* ... */ })
})
```

**MermaidRenderer.spec.js** (10 个测试) - 测**渲染触发**:

```javascript
describe('MermaidComponent - 渲染', () => {
  it('mount 后调 mermaid.initialize', async () => { /* ... */ })
  it('diagramData 变化时重新渲染', async () => { /* ... */ })
  it('相同 data 不重复渲染 (lastRenderData 检查)', async () => { /* ... */ })
  it('渲染中 (isRendering) 不并发触发', async () => { /* ... */ })
  it('渲染失败降级到 "graph TD\\n  A[Error]"', async () => { /* ... */ })
  it('容器引用正确 (mermaidContainer 存在)', () => { /* ... */ })
  it('CSS 注入 (styleEl.textContent)', () => { /* ... */ })
  it('post-render 调用 svgProcessor.processSvg', async () => { /* ... */ })
  it('addMouseOverTooltips 绑定事件', async () => { /* ... */ })
  it('addTrailingDottedLines 创建拖尾', async () => { /* ... */ })
})
```

### 4.3 E2E 测试 (Playwright + Python)

**test_chart_full_ux.py** (15 个测试场景):

```python
"""业务对象图全功能 E2E - 60+ 场景中可 E2E 测的 15 个"""
import pytest
from playwright.sync_api import sync_playwright

class TestChartRendering:
    """R1-R5: 图表渲染"""
    
    def test_r1_svg_exists(self, chart_page):
        """R1: 渲染后 SVG 存在"""
        chart_page.wait_for_selector('.mermaid-content svg', timeout=15000)
        assert chart_page.query_selector_all('.mermaid-content svg') >= 1
    
    def test_r2_node_count_matches_data(self, chart_page, arch_data_25_nodes):
        """R2: 节点数 = 数据数"""
        chart_page.inject_arch_data(arch_data_25_nodes)
        nodes = chart_page.query_selector_all('.mermaid-content .node')
        assert len(nodes) == 25
    
    def test_r3_edge_count_matches_data(self, chart_page, arch_data_with_relations):
        """R3: 边数 = 关系数"""
        chart_page.inject_arch_data(arch_data_with_relations)
        edges = chart_page.query_selector_all('.mermaid-content .edgePath')
        assert len(edges) == len(arch_data_with_relations['relationships'])


class TestZoom:
    """Z1-Z6: 缩放与平移"""
    
    def test_z1_wheel_zoom_in(self, chart_page):
        """Z1: 滚轮放大"""
        scale_before = chart_page.evaluate("parseFloat(getComputedStyle(document.querySelector('.mermaid-content')).transform.split(',')[0].replace('matrix(', ''))")
        chart_page.mouse.wheel(0, -100)  # 向上滚
        chart_page.wait_for_timeout(500)
        scale_after = chart_page.evaluate("getComputedStyle(document.querySelector('.mermaid-content')).transform")
        assert scale_after != scale_before  # 缩放状态变化
    
    def test_z3_zoom_clamp(self, chart_page):
        """Z3: 持续滚轮缩放限制在 [0.3, 3]"""
        for _ in range(50):
            chart_page.mouse.wheel(0, -100)
        chart_page.wait_for_timeout(500)
        transform = chart_page.evaluate("getComputedStyle(document.querySelector('.mermaid-content')).transform")
        # 解析 matrix 第一个数字, 应该是缩放值
        scale = chart_page.evaluate("""(() => {
            const t = getComputedStyle(document.querySelector('.mermaid-content')).transform;
            const m = t.match(/matrix\\(([^,]+)/);
            return m ? parseFloat(m[1]) : 1;
        })()""")
        assert 0.3 <= scale <= 3.0


class TestInteraction:
    """H1-H4, C1: 高亮与清除"""
    
    def test_h1_node_highlight(self, chart_page):
        """H1: 节点 click 高亮"""
        node = chart_page.query_selector('.mermaid-content .node')
        node.click()
        rect_stroke = chart_page.evaluate(
            "(node) => node.querySelector('rect').style.stroke",
            [node]
        )
        assert rect_stroke == 'rgb(255, 107, 107)'  # #FF6B6B
    
    def test_c1_click_blank_clears(self, chart_page):
        """C1: 空白 click 清除高亮"""
        # 先点击节点
        node = chart_page.query_selector('.mermaid-content .node')
        node.click()
        # 再点击空白
        chart_page.query_selector('.mermaid-content').click(position={'x': 5, 'y': 5})
        # 验证高亮被清除
        rect_stroke = chart_page.evaluate(
            "(node) => node.querySelector('rect').style.stroke",
            [node]
        )
        assert rect_stroke == '' or rect_stroke == 'rgb(0, 0, 0)'


class TestExport:
    """X1, X4, X5: 导出"""
    
    def test_x1_pdf_export(self, chart_page):
        """X1: PDF 导出触发下载"""
        with chart_page.expect_download(timeout=15000) as info:
            chart_page.click('[title="导出 PDF（横版矢量图）"]')
        download = info.value
        assert download.suggested_filename.endswith('.pdf')
        assert download.path().exists()
    
    def test_x4_html_export(self, chart_page):
        """X4: HTML 彩色版导出"""
        with chart_page.expect_download(timeout=15000) as info:
            chart_page.click('[title="导出 HTML（彩色版 - 可直接双击打开）"]')
        download = info.value
        html_content = open(download.path(), 'r', encoding='utf-8').read()
        assert 'mermaid' in html_content
        assert '图例' in html_content  # legend 存在
        assert 'subgraph' in html_content  # 容器子图存在
    
    def test_x5_copy_mermaid(self, chart_page):
        """X5: 复制 Mermaid 代码"""
        chart_page.context.grant_permissions(['clipboard-write', 'clipboard-read'])
        chart_page.click('[title="复制代码"]')
        chart_page.wait_for_timeout(500)
        clipboard = chart_page.evaluate("navigator.clipboard.readText()")
        assert 'graph' in clipboard  # mermaid 关键字


class TestErrorHandling:
    """ER1-ER4: 错误处理"""
    
    def test_er1_render_failure_fallback(self, chart_page):
        """ER1: 注入坏数据不崩溃"""
        chart_page.inject_arch_data({'nodes': 'invalid', 'relationships': None})
        # 应不抛错, 可能降级渲染
        chart_page.wait_for_timeout(3000)
        # 检查页面没崩
        assert chart_page.is_visible('.mermaid-container')
    
    def test_er2_null_data(self, chart_page):
        """ER2: 数据为空不渲染"""
        chart_page.evaluate("window.__diagramApp.chartArchStore.clearArchData()")
        chart_page.wait_for_timeout(1000)
        # 没有 SVG
        assert chart_page.query_selector_all('.mermaid-content svg') == 0
```

### 4.4 视觉回归 (Playwright + pixelmatch)

**test_visual_baseline.py** (5 个测试):

```python
"""视觉回归基线测试"""
import pytest
from pathlib import Path
import subprocess

BASELINE_DIR = Path('tests/baselines/diagrams/')
BASELINE_DIR.mkdir(parents=True, exist_ok=True)

class TestVisualBaseline:
    """视觉基线 - 5 个核心场景"""
    
    def test_business_object_25_nodes(self, chart_page):
        """业务对象图 25 节点基线"""
        chart_page.inject_arch_data(load_fixture('archdata_25_nodes.json'))
        chart_page.wait_for_timeout(3000)
        
        current = BASELINE_DIR / '_current_business_25.png'
        chart_page.screenshot(path=str(current))
        
        baseline = BASELINE_DIR / 'business_object_25_nodes.png'
        if not baseline.exists():
            chart_page.screenshot(path=str(baseline))  # 首次生成基线
            pytest.skip('baseline generated, re-run to compare')
        
        diff_pct = pixelmatch(baseline, current, threshold=0.1)
        assert diff_pct < 0.005, f"Visual regression: {diff_pct*100:.2f}% diff"
    
    def test_service_module_15_modules(self, chart_page):
        """服务模块图 15 模块基线"""
        chart_page.inject_arch_data(load_fixture('archdata_15_modules.json'))
        chart_page.wait_for_timeout(3000)
        # ... 同上
    
    def test_edge_label_long_chinese(self, chart_page):
        """长中文 edge label 基线 (v32 修复)"""
        chart_page.inject_arch_data(load_fixture('archdata_long_labels.json'))
        chart_page.wait_for_timeout(3000)
        # ... 同上
    
    def test_fullscreen_chart(self, chart_page):
        """全屏状态基线"""
        chart_page.click('[title="全屏查看"]')
        chart_page.wait_for_timeout(1000)
        chart_page.screenshot(path=str(BASELINE_DIR / '_current_fullscreen.png'))
        # ... 比较
    
    def test_zoomed_chart(self, chart_page):
        """缩放 1.5x 基线"""
        chart_page.mouse.wheel(0, -200)  # 放大
        chart_page.mouse.wheel(0, -200)
        chart_page.wait_for_timeout(500)
        chart_page.screenshot(path=str(BASELINE_DIR / '_current_zoomed.png'))
        # ... 比较
```

---

## 5. 不可测场景的基建需求 (2 个真正测不到)

### 5.1 L2: 节点顺序断言 (Container 内部节点顺序)

**问题**: Mermaid 的 ELK/Dagre 引擎**自己决定**节点最终顺序, 即使你在 syntax 里写 `A -> B -> C`, Mermaid 内部可能重排.

**当前能做的**:
- 检查节点存在 (`.querySelector('#A')` not null)
- 检查节点位置 (BoundingClientRect)

**做不到的**:
- 严格断言"先 A 再 B" 的视觉顺序 (因为可能有 wrap)

**需要的新基建**:
- [ ] **布局快照**: 对同一份 syntax, 每次渲染记录每个节点的 x/y. 多次对比回归
- [ ] **顺序指纹**: 不是断言绝对位置, 而是断言相对位置 (A.x < B.x)

### 5.2 E2: 边线端点位置断言

**问题**: SVG path 的 `d="M..."` 由 mermaid 计算, 没法断言端点"应该在 source 的右中" (因为 source 是矩形, 端点可能 top/right/bottom/left 任意边)

**当前能做的**:
- 检查 path 存在
- 检查 path 起点 = source 中心 ± 半径

**做不到的**:
- 端点连接的具体边 (top vs right vs left)

**需要的新基建**:
- [ ] **几何容差比较**: 端点位置 vs node center 距离 < node.diagonal/2
- [ ] **连接正确性**: startPoint 在 source 节点的 4 边之一上 (容差 5px)

---

## 6. 可执行改进路线图

### 6.1 立即 (P0, 1 周内)

#### 任务 A: useMermaidConfig 单测 (4 个测试, ~50 行)

```
src/composables/useMermaid/config/__tests__/useMermaidConfig.spec.js
```

**价值**: 50 个关键参数有回归保护. 防止 wrappingWidth 200→500 之外的其它参数回归.

#### 任务 B: useSvgStyle 单测 (8 个测试, ~120 行)

```
src/composables/useMermaid/style/__tests__/useSvgStyle.spec.js
```

**价值**: fixEdgeLabelOverflow + applyContainerTitleItalic 不被破坏. 防护 v22 端点错位 bug 复发.

#### 任务 C: E2E test_archdata_chart_v32 扩展 (10 个测试, ~300 行)

在 [test_archdata_chart_v32.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_archdata_chart_v32.py) 末尾追加:

```python
def test_c8_node_count_matches_data(self): pass
def test_c9_edge_count_matches_data(self): pass
def test_c10_node_label_not_truncated(self): pass
def test_c11_wheel_zoom_works(self): pass
def test_c12_drag_pan_works(self): pass
def test_c13_dblclick_reset_works(self): pass
def test_c14_node_highlight_on_click(self): pass
def test_c15_tooltip_shows_on_hover(self): pass
def test_c16_pdf_export_succeeds(self): pass
def test_c17_html_export_includes_legend(self): pass
```

**价值**: 1 周内给业务对象图加 10 个回归保护. 防 edge label 截断 bug 复发 + 防其它 9 个类似视觉 bug 复发.

#### 任务 D: useMermaidComponent 组件测试 (5 个测试, ~200 行)

```
src/components/__tests__/MermaidComponent.spec.js
```

**价值**: 工具栏按钮 (重置/全屏/复制/HTML/PDF) 都有 mount 级别回归保护. 任何 props 改动能立刻发现.

### 6.2 短期 (P1, 1 月内)

#### 任务 E: 拆 MermaidComponent.vue (1828 → ~300×6)

详见 [上版分析](file:///d:/filework/excel-to-diagram/docs/testability/business-object-diagram-testability-analysis.md) §5.1.A.

**价值**: 拆完后, 每个子组件 < 500 行, 可单独 mount + 测. 错误定位到子组件级别.

#### 任务 F: 视觉回归基建 (pixelmatch + baseline)

详见 [上版分析](file:///d:/filework/excel-to-diagram/docs/testability/business-object-diagram-testability-analysis.md) §5.1.E.

**价值**: 防 CSS / 渲染管线改动无意中破坏视觉. 5 个核心场景的基线 (25 节点/15 模块/长 label/全屏/缩放).

#### 任务 G: archData 测试数据工厂

```python
# tests/factories/archdata_factory.py
def create_arch_data(nodes=10, relations=15, label_length=20, has_cycles=False):
    """生成可参数化的测试 archData"""
    return {
        "productId": 1,
        "versionId": 1,
        "selectedObjectIds": [f"BO_{i:03d}" for i in range(nodes)],
        "selectedRelationCodes": [f"REL_{i:03d}" for i in range(relations)],
        "labels": {
            f"REL_{i:03d}": f"CODE-{i:03d}-" + "测试" * (label_length // 2)
            for i in range(relations)
        }
    }
```

**价值**: 任何测试都能用 `create_arch_data(label_length=200)` 模拟长 label 场景. fixture 与真实数据脱节问题彻底解决.

### 6.3 中期 (P2, 季度内)

#### 任务 H: 端点位置几何断言基建

新建 [tests/utils/geometry.py](file:///d:/filework/excel-to-diagram/tests/utils/geometry.py):

```python
def assert_endpoint_near_node(endpoint, node_bbox, tolerance=5):
    """端点位置应在节点的 4 边之一上, 容差 5px"""
    x, y = endpoint.x, endpoint.y
    on_left = abs(x - node_bbox.left) < tolerance
    on_right = abs(x - node_bbox.right) < tolerance
    on_top = abs(y - node_bbox.top) < tolerance
    on_bottom = abs(y - node_bbox.bottom) < tolerance
    
    in_h_range = node_bbox.left - tolerance <= x <= node_bbox.right + tolerance
    in_v_range = node_bbox.top - tolerance <= y <= node_bbox.bottom + tolerance
    
    is_on_edge = (on_left or on_right) and in_v_range or (on_top or on_bottom) and in_h_range
    assert is_on_edge, f"Endpoint ({x},{y}) not near node bbox {node_bbox}"
```

**价值**: 让"端点连接正确性"从"测不到"变成"测得到".

#### 任务 I: 集成 Storybook + Chromatic

- 把拆完的 6 个子组件都接入 Storybook
- Chromatic 做 visual diff
- 团队 review 视觉时直接在 Storybook 提 PR

**价值**: 视觉测试平台化, 团队共享 baseline. 防"开发者改了一行 CSS, 视觉静默破坏".

#### 任务 J: 完整覆盖 useMermaid 14 个子模块

每个子模块都加 `__tests__/xx.spec.js`:
- useMermaidConfig ✓ (P0 已做)
- useSvgStyle ✓ (P0 已做)
- useInteraction
- useTooltip
- useExport
- useSvgProcessor
- useAnnotation
- useAnnotationOverlay
- useMermaidColors
- useMermaidDataMap
- useElkLoader
- useBusinessObjectSyntax
- useServiceModuleSyntax
- 4 个 layout 生成器

**价值**: 14 个核心模块, 100+ 单元测试, 全面防护.

### 6.4 长期 (P3, 半年+)

- **AI 辅助测试生成**: 用 LLM 自动生成 fixture 和测试 (从源代码提取边界条件)
- **Property-based testing**: 随机化节点数 / 边数 / label 长度, 自动找反例
- **Mutation testing**: 用 Stryker 自动检测"测了但没测到"的代码

---

## 7. 优先级与 ROI 矩阵

| 任务 | 行数 | 时间 | 防护范围 | ROI |
|------|------|------|---------|-----|
| A: useMermaidConfig 单测 | 50 | 1 天 | 配置层 (50 参数) | **★★★★★** |
| B: useSvgStyle 单测 | 120 | 2 天 | 后处理层 (4 个方法) | **★★★★★** |
| C: 10 个 E2E 场景 | 300 | 3 天 | 完整渲染/交互/导出 | **★★★★** |
| D: 5 个组件测试 | 200 | 2 天 | 工具栏 + 渲染触发 | **★★★★** |
| E: 拆 MermaidComponent | 0 (重构) | 1 周 | 解耦, 可单测 | **★★★** |
| F: 视觉回归基建 | 500 | 1 周 | CSS 视觉 | **★★★★** |
| G: archData 工厂 | 100 | 1 天 | fixture 重用 | **★★★★★** |
| H: 端点几何断言 | 50 | 1 天 | 边线连接 | **★★★** |
| I: Storybook | 0 (基建) | 1 周 | 团队视觉 review | **★★★** |
| J: 14 模块完整覆盖 | 1500+ | 1 月 | 全防护 | **★★★** |

**P0 推荐 (1 周内完成)**: **A + B + C + D + G = ~770 行, 1 周**, 防护范围覆盖 80% 的核心功能, ROI 最高.

**P1 推荐 (1 月内完成)**: **A + B + C + D + E + F + G = ~1300 行 + 1 周重构 + 1 周基建, 1 月**, 把可测试性从 2.6/10 提到 7/10.

---

## 8. 总结

### 8.1 用户反馈驱动的核心洞察

| 之前的盲点 | 现在的认识 |
|-----------|----------|
| 聚焦 1 个 bug (edge label) | **60+ 功能场景, 0 个有针对性测试** |
| 关注"截断" | **关注"截断 + 缩放 + 拖动 + 高亮 + 导出 + 响应式 + 错误处理"** |
| 关注 CSS 视觉层 | **关注渲染/交互/布局/导出/响应式/错误处理/可访问性 全 9 层** |
| 1 处修复 | **14 大类功能 × 60+ 测试场景** |

### 8.2 业务对象图全功能可测试性得分

| 评估维度 | 上一版 | 本版 |
|---------|--------|------|
| 数据流可测性 | 7/10 | 7/10 |
| 视觉可测性 | 1/10 | **3/10** (扩展到缩放/拖动/高亮/tooltip) |
| 配置可测性 | 0/10 | 0/10 |
| 组件可测性 | 0/10 | 0/10 |
| **交互可测性** | (新) | **0/10** (新增维度, 极差) |
| **导出可测性** | (新) | **1/10** (新增维度, 严重缺失) |
| **响应式可测性** | (新) | **0/10** (新增维度, 0 测试) |
| **错误处理可测性** | (新) | **0/10** (新增维度, 0 测试) |
| 错误定位性 | 2/10 | 2/10 |
| 测试速度 | 5/10 | 5/10 |
| 测试可维护性 | 4/10 | 4/10 |
| **总分** | **2.6/10** | **1.7/10** (维度更全, 分数更真实) |

### 8.3 立即可做 (1 周) 的 5 件事

1. **useMermaidConfig 单测 (50 行)** - 防止 50+ 配置参数回归
2. **useSvgStyle 单测 (120 行)** - 防止 fixEdgeLabelOverflow / applyContainerTitleItalic 回归
3. **E2E 10 个新场景 (300 行)** - 节点数/边数/label 完整/缩放/拖动/重置/高亮/tooltip/PDF/HTML
4. **MermaidComponent 组件测试 (200 行)** - 工具栏 + 渲染触发
5. **archData 测试数据工厂 (100 行)** - fixture 与真实数据脱节彻底解决

**合计 ~770 行测试代码, 1 周工作量, 覆盖 80% 核心功能**.

### 8.4 关键文件清单 (本版新增)

| 文件 | 角色 | 应有测试数 |
|------|------|----------|
| [src/composables/useMermaid/config/useMermaidConfig.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/config/useMermaidConfig.js) | Mermaid 配置 | 4-6 单测 |
| [src/composables/useMermaid/style/useSvgStyle.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/useSvgStyle.js) | SVG 后处理 | 8-10 单测 |
| [src/composables/useMermaid/interaction/useInteraction.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/interaction/useInteraction.js) | 缩放拖动 | 6-8 单测 |
| [src/composables/useMermaid/tooltip/useTooltip.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/tooltip/useTooltip.js) | Tooltip + 高亮 | 10-15 单测 |
| [src/composables/useMermaid/export/useExport.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/export/useExport.js) | PDF 导出 | 5-8 单测 |
| [src/components/MermaidComponent.vue](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.vue) | 渲染组件 | 10-15 组件测 |
| [src/components/MermaidComponent.css](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.css) | 视觉样式 | 5-10 视觉回归 |
| [tests/e2e/test_archdata_chart_v32.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_archdata_chart_v32.py) | 流程 E2E | +10 场景 (现有 7 → 17) |

## 9. 行动清单

### 立即 (P0, 1 周)
- [ ] 加 `useMermaidConfig.spec.js` (4 个测试)
- [ ] 加 `useSvgStyle.spec.js` (8 个测试)
- [ ] 加 `useInteraction.spec.js` (6 个测试)
- [ ] E2E `test_archdata_chart_v32.py` 扩展 10 个场景
- [ ] 加 `MermaidComponent.spec.js` (5 个测试)
- [ ] 加 `archData` 测试数据工厂

### 短期 (P1, 1 月)
- [ ] 拆 MermaidComponent.vue 为 6 个子组件
- [ ] 视觉回归基建 (pixelmatch + baseline 5 个场景)
- [ ] 拆 MermaidComponent.css 为 5 个子 CSS
- [ ] 加 useTooltip 单测 (10 个)
- [ ] 加 useExport 单测 (5 个)
- [ ] 加 useSvgProcessor 单测 (5 个)

### 中期 (P2, 季度)
- [ ] 端点位置几何断言基建
- [ ] 集成 Storybook + Chromatic
- [ ] 完整覆盖 useMermaid 14 个子模块
- [ ] 14 个 layouts 子模块单测
- [ ] 2 个 syntax 生成器单测
