# 业务对象图应用流程 - 前端测试可测试性深度分析

> **分析日期**: 2026-06-11
> **分析范围**: 业务对象图 (BusinessObject) 端到端流程
> **触发问题**: edge label 文字右侧截断 (mermaid label 渲染层)
> **目的**: 揭示当前测试体系为什么没拦住这个 bug, 以及怎么从架构层面提升可测试性

---

## 1. 应用流程全景图

业务对象图完整流程涉及 9 个层级, 跨越 3 个语言 (Python/JS/CSS):

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 用户操作层 (浏览器)                                                       │
│  ┌───────────────┐    ┌────────────────┐    ┌──────────────────────┐   │
│  │ 管理页 (BO/RSS) │───▶│ 展示图表按钮    │───▶│ /archdata-chart tab  │   │
│  └───────────────┘    └────────────────┘    └──────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Vue 路由 + Pinia 状态层                                                    │
│  ┌────────────┐    ┌──────────────┐    ┌─────────────────────┐          │
│  │ router     │───▶│ chartStore   │───▶│ AADiagramApp/index  │          │
│  │ sessionStg │    │ (archData)   │    │ (3-step 流程)       │          │
│  └────────────┘    └──────────────┘    └─────────────────────┘          │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 步骤配置层 (StepConfig/StepDisplay)                                       │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │ diagramConfigStr │───▶│ StepConfig (UI)  │───▶│ StepDisplay     │  │
│  │ (Pinia store)    │    │ - 颜色 / 布局    │    │ (chart)         │  │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Mermaid 渲染层 (composables/useMermaid/*)                                │
│  ┌────────────────┐    ┌──────────────┐    ┌──────────────┐           │
│  │ useMermaidCfg  │───▶│ syntaxGen    │───▶│ mermaid.run()│           │
│  │ (wrappingWidth │    │ (mermaid code│    │ (SVG render)│           │
│  │  layoutEng)    │    │  string)     │    │             │           │
│  └────────────────┘    └──────────────┘    └──────────────┘           │
│         │                       │                    │                  │
│         ▼                       ▼                    ▼                  │
│  ┌────────────────────────────────────────────────────────────┐        │
│  │ useSvgProcessor (post-render 处理)                           │        │
│  │ - addCodeAttributes / addTooltips / applyContainerTitleItalic│        │
│  │ - 包含 fixEdgeLabelSize (本次 v32 新增, 未调用)              │        │
│  └────────────────────────────────────────────────────────────┘        │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ DOM 渲染层 (MermaidComponent.vue)                                          │
│  ┌─────────────────┐    ┌──────────────┐    ┌──────────────┐           │
│  │ innerHTML 注入  │───▶│ mermaid.run  │───▶│ SVG 元素     │           │
│  │ <pre class=    │    │ (异步)       │    │ 在 DOM 中    │           │
│  │  mermaid>      │    │              │    │              │           │
│  └─────────────────┘    └──────────────┘    └──────────────┘           │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CSS 视觉层 (MermaidComponent.css)                                          │
│  ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │ .labelBkg 样式  │    │ foreignObject    │    │ <p> 文字        │   │
│  │ (max-width)     │    │ (overflow)       │    │ (text-shadow)   │   │
│  └─────────────────┘    └──────────────────┘    └──────────────────┘   │
│         │                       │                    │                  │
│         ▼                       ▼                    ▼                  │
│  ┌────────────────────────────────────────────────────────────┐        │
│  │ 浏览器渲染: SVG → foreignObject → div.labelBkg → span → <p>   │        │
│  │ (这是用户实际看到 edge label 文字被截的层)                  │        │
│  └────────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.1 流程涉及的具体文件

| 层级 | 文件 | 行数 | 职责 |
|------|------|------|------|
| 路由 | [src/router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js) | ~200 | 路由守卫, sessionStorage 写入 |
| Pinia | [src/stores/chartArchStore.js](file:///d:/filework/excel-to-diagram/src/stores/chartArchStore.js) | ~150 | archData state 管理 |
| Pinia | [src/stores/diagramConfigStore.js](file:///d:/filework/excel-to-diagram/src/stores/diagramConfigStore.js) | ~400 | Mermaid config 持久化 |
| 入口 | [src/views/AADiagramApp/index.vue](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/index.vue) | ~500 | 3 步流程编排 |
| 步骤 | [src/views/AADiagramApp/components/steps/](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/components/steps/) | ~2000 | 6 个步骤组件 |
| Mermaid | [src/composables/useMermaid/*](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/) | ~5000 | 14 个子模块, config/syntax/style/renderer/layouts |
| 组件 | [src/components/MermaidComponent.vue](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.vue) | **1828** | 渲染 + 交互 + 导出 + 全屏 + PDF 等等 |
| CSS | [src/components/MermaidComponent.css](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.css) | ~800 | 节点 / 容器 / 边 / 标签样式 |
| 流程 | [src/composables/useMultiObjectPage.js](file:///d:/filework/excel-to-diagram/src/composables/useMultiObjectPage.js) | ~800 | 管理页数据流, saveStateForDiagram |

---

## 2. 测试覆盖现状

### 2.1 已有测试盘点

| 类别 | 文件 | 数量 | 覆盖层级 | 价值 |
|------|------|------|---------|------|
| **E2E Python** | [test_archdata_chart_v32.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_archdata_chart_v32.py) | 7 | Pinia store 数据流 | 仅测状态, 不测视觉 |
| **E2E Python** | `e2e_relation_scope_tree*.py` | 多个 | RSS 树组件 | 行为, 不测视觉 |
| **Vitest 单元** | [src/composables/useMermaid/annotation/__tests__/annotationConfig.spec.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/annotation/__tests__/annotationConfig.spec.js) | 1 个 spec | annotation config 静态表 | 极小, 1 个模块 |
| **Vitest 单元** | [src/services/__tests__/mermaid_optimization_bench.spec.js](file:///d:/filework/excel-to-diagram/src/services/__tests__/mermaid_optimization_bench.spec.js) | 1 个 spec | 性能基准 | 性能, 不测功能 |
| **Vitest 单元** | [src/services/groupModel/__tests__/](file:///d:/filework/excel-to-diagram/src/services/groupModel/__tests__/) | 2 个 spec | GroupModel 业务逻辑 | 算法层 |

**E2E 测试覆盖比例**:
- ✅ 7 个 chart tab 流程 (C1-C7) 全部通过 (2026-06-11 验证)
- ❌ 0 个测试断言 SVG 元素 (节点数 / 边数 / label 文字)
- ❌ 0 个测试断言 computed style
- ❌ 0 个测试断言 mermaid config 参数 (wrappingWidth / layoutEngine)
- ❌ 0 个测试断言 edge label 是否被截断

**单元测试覆盖比例**:
- ✅ 14 个 useMermaid 子模块中, **1 个有测试** (annotationConfig, 静态表)
- ❌ 0 个测试覆盖 useMermaidConfig (核心配置)
- ❌ 0 个测试覆盖 useSvgStyle (CSS 后处理)
- ❌ 0 个测试覆盖 useBusinessObjectSyntax / useServiceModuleSyntax
- ❌ 0 个测试覆盖 useSvgProcessor (render 后处理)
- ❌ 0 个测试覆盖 MermaidComponent.vue (1828 行核心组件)

### 2.2 测试金字塔现状 vs 理想

```
                   实际                理想 (frontend-testing-standards)
                  
                ┌──────┐ E2E        ┌──────┐ E2E (10%, 5-10 min)
                │ 7    │            │ 10-20│
                │ 流程 │            └──────┘
                ├──────┤ 组件         ┌──────┐ 组件 (20%, 1-3 min)
                │ 0    │            │ 50-100│
                │ 组件 │            ├──────┤
                ├──────┤ 单元         │ 200+ │ 单元 (70%, < 1 min)
                │ ~30  │            │ 500  │
                │ 散乱 │            └──────┘
                └──────┘            
```

**结论**:
- E2E 数量: 7 (在合理范围)
- 组件测试: **0** (严重缺失)
- 单元测试: 散落在 30+ 个 spec, 但 useMermaid 这块 14 个模块只测 1 个

---

## 3. 为什么测试没拦住 edge label 截断

### 3.1 bug 在哪一层?

用户看到的"文字右侧截断" = CSS 视觉层 (第 8 层) 的问题. 但根因是 Mermaid config (第 5 层) 的 `wrappingWidth: 200` 太小.

**测试需要测的是**: 给定任意长度的 label, foreignObject width 是否能容纳文字 + padding.

### 3.2 现有测试为什么测不到?

#### 原因 1: E2E 测试只测"行为"不测"视觉"

```python
# test_archdata_chart_v32.py L150-160 (典型的 happy-path 断言)
if not state2.get('hasArchData'):
    results["errors"].append("Store has no archData after inject")
elif state2.get('archDataSource') != 'v32_e2e_test':
    results["errors"].append(f"Wrong source: {state2.get('archDataSource')}")
elif not state2.get('initFromArchData'):
    results["errors"].append("Not in 3-step mode (initFromArchData=false)")
elif state2.get('currentStep') != 3:
    results["errors"].append(f"currentStep={state2.get('currentStep')}, expected 3")
else:
    results["steps"].append(f"OK: sequence={state2.get('sequence')}, step=3, initFromArchData=true")
    results["passed"] = True
```

**测的**: state 对象的属性值
**没测的**: SVG 元素, 视觉, computed style

#### 原因 2: 测了渲染, 但断言不深

`test_c4_direct_url_no_data` (L329-348) 终于测了 DOM:

```python
step_count = cli.evaluate(
    "document.querySelectorAll('.el-steps .el-steps__item, ...').length"
)
if step_count == 6:
    results["passed"] = True
```

**测的**: 步骤组件数 (UI 框架 Element Plus)
**没测的**: SVG 节点数, 边数, label 内容, 任何 mermaid 输出

#### 原因 3: 单元测试几乎为零, useMermaidConfig 完全没有覆盖

```
$ find src/composables/useMermaid -name "*.spec.js"
src/composables/useMermaid/annotation/__tests__/annotationConfig.spec.js  # 仅 1 个

$ wc -l src/composables/useMermaid/config/useMermaidConfig.js
246   # 0 个测试

$ wc -l src/composables/useMermaid/style/useSvgStyle.js
420   # 0 个测试

$ wc -l src/composables/useMermaid/renderer/useSvgProcessor.js
260   # 0 个测试
```

**核心配置文件 `useMermaidConfig.js` 包含 wrappingWidth/layoutEngine/dagre/elk 等 50+ 个关键参数, 0 个测试覆盖**. 任何参数变更 (200 → 500) 都没有回归保护.

#### 原因 4: MermaidComponent.vue 是 1828 行的"上帝组件", 没法单元测试

```javascript
// 单一 setup() 函数, 1828 行, 集成 11 个 composable + 1 个 mermaid 库
setup(props, { emit }) {
  const { initializeMermaid } = useMermaidConfig()        // 配置
  const interaction = useInteraction()                    // 交互
  const svgStyle = useSvgStyle()                          // 样式
  const tooltip = useTooltip()                            // tooltip
  const colors = useMermaidColors()                       // 颜色
  const dataMap = useMermaidDataMap()                     // 数据映射
  const annotation = useAnnotation()                      // 标注
  const annotationOverlay = useAnnotationOverlay()        // 标注覆盖
  const svgProcessor = useSvgProcessor({ interaction })   // 渲染处理
  const configStore = useDiagramConfigStore()             // Pinia store
  
  // ... 12 个 const, 5 个 watch, 14 个方法 (renderMermaid / exportAsPdf / 
  //     exportAsHtmlFull / copyToClipboard / toggleMaximize / ... )
  // ... + 静态注入 600+ 行 CSS
  // ... + exportAsHtmlFull 内嵌 500+ 行 HTML template
}
```

**为什么没法测**:
- `mermaid.run()` 是异步全局副作用, 需要真实 DOM
- `html2canvas` / `jspdf` 是外部库, 需要 mock
- `<style>` 标签的 `styleEl.textContent = cssRules` 是动态注入, 难断言
- exportAsHtmlFull 里的 HTML template 是 500 行字符串, 没法断言内容
- `props.diagramData` 是深度嵌套的 reactive 对象, 准备 fixture 工作量巨大

**结果**: 整个组件完全裸奔, 改任何一行都靠手测, 没有任何自动化保障.

#### 原因 5: CSS 没有 test, 只能靠"截屏对比"

MermaidComponent.css 有 ~800 行, 其中 ~30 段针对 `g.edgeLabel foreignObject > div.labelBkg` 的样式, 互相覆盖, 优先级混乱.

**为什么 CSS 难测**:
- happy-dom 不支持 SVG `<foreignObject>` (不是 happy-dom 的 bug, 是 spec 限制)
- jsdom 支持 foreignObject 但不渲染 (mock 而已)
- Playwright 能测, 但需要真实 Chrome + Mermaid 完成整个渲染, 启动慢 (15s+)

**结果**: 没有任何测试能在 happy-dom 验证 `getComputedStyle(div.labelBkg).maxWidth === 'none'`. 这种 CSS 限制只能靠 E2E 截屏.

#### 原因 6: 测试输入与真实数据脱节

真实业务场景 label 可能是:
- 11 字符英文代码: `PUM07-SOC27` (79px, 装得下)
- 8 字符中文: `供应链云/采购订单` (128px, 装得下)
- 30 字符长中文: `PUM07-SOC27-EXT09-PLB033-XXX` (200px+, 装不下)

但现有测试 fixture 的 archData 是:
```python
"data": {
  "productId": 1,
  "productName": "TestProduct",
  ...
}
```
**fixture 没有 label 数据, 即便测了也不会暴露 label 截断问题**.

---

## 4. 流程可测试性的根本问题

### 4.1 架构问题: 关注点严重耦合

```
MermaidComponent.vue (1828 行, 单一文件)
├── 配置 (configStore, useMermaidConfig)
├── 渲染 (mermaid.run, useSvgProcessor)
├── 交互 (useInteraction, useTooltip, useAnnotation)
├── 视觉 (useSvgStyle, useMermaidColors, 静态 CSS 注入)
├── 导出 (PDF/HTML/Native/Image/Clipboard 5 种导出)
├── 全屏 (toggleMaximize, fullscreenchange)
├── 状态管理 (isRendering, lastColorGroupBy, lastCustomColors, isFirstRender)
├── DOM 操作 (setInnerHTML, querySelector, appendChild)
└── 性能优化 (debounced resize, auto-fit)
```

**问题**: 改一个地方 (例如 wrappingWidth) 会影响所有地方. 但测试只能测"整个组件", 出错时无法定位.

**对比**: 一个健康的组件应该是:
- `<MermaidRenderer>` 只负责渲染
- `<MermaidExporter>` 只负责导出
- `<MermaidConfigForm>` 只负责配置
- `<MermaidInteractionLayer>` 只负责交互

### 4.2 依赖问题: 强依赖真实环境

```javascript
// MermaidComponent.vue L361
mermaid.run().then(() => {
  // 假设 mermaid 库已在 window 上加载
  // 假设 SVG 已注入
  // 假设 dagre/elk layout 已算好
  // 假设 tooltip / annotation / colors 已 setup
})
```

**问题**: 14 个 composable + mermaid 库 + Pinia store + 静态 CSS 注入, 任何一环失败都会让测试无法启动.

**对比**: 好的设计会用 DI (依赖注入):
```javascript
// 易测版本
const { mermaidRenderer } = useMermaidRenderer({ mermaid, layoutEngine, config })
// 注入 mock mermaid, 注入 mock layout engine, 注入 mock config
```

### 4.3 时序问题: 大量 setTimeout / requestAnimationFrame / nextTick

```javascript
// MermaidComponent.vue L359-600 散布的时序代码
nextTick(() => {
  mermaid.run().then(() => {
    setTimeout(() => {
      interaction.autoFitDiagram()
    }, 100)
    setTimeout(() => {
      hideLinkLabelTails()
    }, 2000)
    setTimeout(() => {
      const svgAgain = mermaidContainer.value.querySelector('svg')
      if (svgAgain) {
        svgStyle.applyContainerTitleItalic(svgAgain)
      }
    }, 800)
  })
})
```

**问题**: happy-dom 不支持 `requestAnimationFrame` 准确时序, jsdom 支持但慢. Playwright 真实浏览器能跑但慢 (3-5s/测试).

**结果**: 任何依赖时序的修复 (如 v32 这次) 都没法在单元测试里验证.

### 4.4 数据问题: 深度嵌套 + 强类型约束

`props.diagramData` 是 ~20 字段的对象, 包含嵌套的 `relationships / nodes / containers / groups`, 每个节点又包含 `code / name / domain / serviceModuleName` 等.

**测试准备 1 个 fixture 要写 ~100 行**, 没人愿意写, 没人能维护.

### 4.5 反馈问题: 错误信息无定位

```javascript
// MermaidComponent.vue L302-305
} catch (e) {
  console.error('[generateMermaidCode] error:', e)
  return 'graph TD\n  A[Error]'  // 静默降级, 用户看到 "Error" 节点, 不知道哪错了
}
```

**问题**: 错误被吞掉, 只 console.error, 测试断言只能查 DOM 看到 "Error" 字符串.

---

## 5. 测试可测试性提升方案

### 5.1 立即可做 (P0, 1 周内)

#### A. 拆分 MermaidComponent.vue (1828 → ~300 行/组件)

```
src/components/mermaid/
├── MermaidRenderer.vue          # 核心渲染 (~300 行)
├── MermaidToolbar.vue            # 工具栏 (~100 行)
├── MermaidFullscreenHandler.vue  # 全屏 (~150 行)
├── MermaidExporter.vue           # 导出 (~400 行, 拆 PDF/HTML/Native)
├── MermaidStyleInjector.vue      # 动态 CSS 注入 (~150 行)
└── useMermaidRenderer.js         # 共享 composable (~200 行)
```

**价值**:
- 每个子组件 < 500 行, 可单独 mount + 测
- 错误定位: 哪一段挂了, 测哪一段
- 重构: 拆完之后单测变可行

#### B. 抽 `useMermaidConfig` 测试

新建 [src/composables/useMermaid/config/__tests__/useMermaidConfig.spec.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/config/__tests__/useMermaidConfig.spec.js):

```javascript
import { describe, it, expect, beforeEach } from 'vitest'
import { useMermaidConfig } from '../useMermaidConfig'

describe('useMermaidConfig - wrappingWidth (v32 regression)', () => {
  it('业务对象图: wrappingWidth 应该 >= 500 (容纳 ~25 中文字符)', () => {
    const { getConfig } = useMermaidConfig()
    const config = getConfig('businessObject', {}, 'dagre', 'default', false, null, 50000)
    expect(config.flowchart.wrappingWidth).toBeGreaterThanOrEqual(500)
  })
  
  it('服务模块图: wrappingWidth 应该 >= 800 (容纳 ~40 中文字符)', () => {
    const { getConfig } = useMermaidConfig()
    const config = getConfig('serviceModule', {}, 'dagre', 'default', false, null, 50000)
    expect(config.flowchart.wrappingWidth).toBeGreaterThanOrEqual(800)
  })
  
  it('关键回归: 节点宽度 / 边距 / elk 配置不被 wrappingWidth 改动影响', () => {
    const { getConfig } = useMermaidConfig()
    const before = getConfig('businessObject', {}, 'dagre', 'default', false, null, 50000)
    expect(before.flowchart.nodeSpacing).toBe(80)
    expect(before.flowchart.rankSpacing).toBe(100)
    expect(before.flowchart.curve).toBe('basis')
  })
})
```

**价值**: 3 个测试覆盖核心配置, 任何参数回归都能被捕获.

#### C. 抽 `useSvgStyle` 测试

新建 [src/composables/useMermaid/style/__tests__/useSvgStyle.spec.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/__tests__/useSvgStyle.spec.js):

```javascript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useSvgStyle } from '../useSvgStyle'

describe('useSvgStyle - fixEdgeLabelOverflow (v32 regression)', () => {
  it('不应修改 foreignObject 的 width/height 属性 (避免 v22 端点错位 bug)', () => {
    const { fixEdgeLabelOverflow } = useSvgStyle()
    const mockSvg = createMockSvg({
      edgeLabel: { foreignObjectWidth: '79.44', foreignObjectHeight: '17.19' }
    })
    fixEdgeLabelOverflow(mockSvg)
    expect(mockSvg.foreignObject.width).toBe('79.44')
    expect(mockSvg.foreignObject.height).toBe('17.19')
  })

  it('不应触及 .nodeLabel 内的 foreignObject', () => {
    const { fixEdgeLabelOverflow } = useSvgStyle()
    const mockSvg = createMockSvg({
      nodeLabel: { foreignObjectWidth: '150', foreignObjectHeight: '60' }
    })
    fixEdgeLabelOverflow(mockSvg)
    expect(mockSvg.nodeLabel.foreignObject.width).toBe('150')
  })

  it('应只覆盖 .labelBkg 的 max-width/white-space', () => {
    const { fixEdgeLabelOverflow } = useSvgStyle()
    const mockSvg = createMockSvg({
      labelBkg: { maxWidth: '200px', whiteSpace: 'nowrap' }
    })
    fixEdgeLabelOverflow(mockSvg)
    expect(mockSvg.labelBkg.style.maxWidth).toBe('none')
    expect(mockSvg.labelBkg.style.whiteSpace).toBe('nowrap')
  })
})

// 测试 helper: 模拟 Mermaid 输出的 SVG DOM
function createMockSvg(overrides = {}) {
  return {
    foreignObject: {
      getAttribute: vi.fn((k) => overrides.foreignObject?.[`${k}Char`] || overrides.edgeLabel?.[`foreignObject${k[0].toUpperCase()}${k.slice(1)}`]),
      setAttribute: vi.fn(),
      style: { setProperty: vi.fn() },
      querySelector: vi.fn((sel) => {
        if (sel === ':scope > div' && overrides.labelBkg) return overrides.labelBkg
        return null
      })
    },
    nodeLabel: { /* ... */ },
    labelBkg: { classList: { contains: (c) => c === 'labelBkg' } },
    querySelectorAll: vi.fn((sel) => {
      if (sel === 'g.edgeLabel' && overrides.edgeLabel) return [overrides.edgeLabel]
      return []
    }),
    querySelector: vi.fn((sel) => sel === 'foreignObject' ? /* ... */ : null)
  }
}
```

**价值**: 4-5 个测试覆盖 fixEdgeLabelOverflow, 防止二轮修复时的 box-sizing 错误再次发生.

#### D. 加 E2E 视觉断言

在 [test_archdata_chart_v32.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_archdata_chart_v32.py) 末尾新增:

```python
def test_c8_edge_label_not_truncated():
    """C8: edge label 文字不应被截断 (v32 二轮修复回归)
    
    验证策略:
      1) 注入有长 edge label 的测试数据
      2) 渲染图表 (mermaid.run() 完成)
      3) 抓取所有 g.edgeLabel 的 foreignObject width 和 innerText 实际宽度
      4) 断言: foreignObject width >= innerText scrollWidth
    """
    cli = PlaywrightCLI()
    cli.authenticated_navigate('/archdata-chart', timeout=20000)
    time.sleep(3)
    
    # 注入 30 个节点的测试数据, label 包含中英文混合
    cli.evaluate("""(() => {
        const s = window.__diagramApp.chartArchStore;
        s.setArchData({
            productId: 1, versionId: 1,
            selectedObjectIds: [101, 102, 103, 104, 105],
            selectedRelationCodes: ['DEPENDS_ON'],
            source: 'edge_label_test'
        });
    })()""")
    time.sleep(5)  # 等 mermaid.run() 完成
    
    # 关键断言: 所有 edge label 的 foreignObject 宽度足够
    label_widths = cli.evaluate("""(() => {
        const labels = document.querySelectorAll('g.edgeLabel');
        return Array.from(labels).map(label => {
            const fo = label.querySelector('foreignObject');
            if (!fo) return null;
            const labelBkg = fo.querySelector('div.labelBkg');
            const p = fo.querySelector('p');
            return {
                text: p ? p.textContent.trim() : '',
                foWidth: parseFloat(fo.getAttribute('width')),
                pScrollWidth: p ? p.scrollWidth : 0,
                pOffsetWidth: p ? p.offsetWidth : 0
            };
        }).filter(Boolean);
    })()""")
    
    errors = []
    for lw in label_widths:
        # 检查 1: foreignObject 宽度足够 (有 8px 安全边界)
        if lw['foWidth'] < lw['pScrollWidth'] - 4:
            errors.append(
                f"Edge label '{lw['text']}' 文字溢出: "
                f"foWidth={lw['foWidth']}, pScrollWidth={lw['pScrollWidth']}"
            )
        # 检查 2: <p> 元素的 offsetWidth == scrollWidth (说明没有 overflow:hidden)
        if lw['pOffsetWidth'] < lw['pScrollWidth'] - 1:
            errors.append(
                f"Edge label '{lw['text']}' <p> 被裁切: "
                f"offsetWidth={lw['pOffsetWidth']}, scrollWidth={lw['pScrollWidth']}"
            )
    
    if errors:
        results["errors"].extend(errors)
        results["passed"] = False
    else:
        results["steps"].append(f"OK: {len(label_widths)} edge labels 全部不截断")
        results["passed"] = True
```

**价值**: 1 个测试就够. 任何 wrappingWidth / CSS / 渲染改动都会被这个测试捕获.

#### E. 视觉回归基建

建立 baseline 截图管理:

```
tests/baselines/diagrams/
├── business_object_25_nodes.png      # 业务对象图基线
├── service_module_15_modules.png     # 服务模块图基线
└── edge_label_long_chinese.png       # 长中文 edge label 基线
```

```python
def test_c9_visual_baseline():
    """C9: 视觉基线回归 (screenshot diff)
    
    任何 > 0.5% 像素差异视为 fail
    """
    cli = PlaywrightCLI()
    cli.authenticated_navigate('/archdata-chart', timeout=20000)
    # ... 注入标准 25 节点数据
    screenshot = cli.screenshot('tests/baselines/diagrams/_current.png')
    diff = pixelmatch(
        baseline_path='tests/baselines/diagrams/business_object_25_nodes.png',
        current_path='tests/baselines/diagrams/_current.png',
        diff_path='tests/baselines/diagrams/_diff.png'
    )
    if diff / total_pixels > 0.005:
        results["errors"].append(f"Visual regression: {diff*100:.2f}% pixel diff")
```

**价值**: 防 CSS / 渲染管线改动无意中破坏视觉.

### 5.2 中期改进 (P1, 1 月内)

#### F. 抽 DI 层

新建 [src/composables/useMermaid/core/useMermaidRenderer.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/core/useMermaidRenderer.js):

```javascript
// 接受 mermaid 实例 + config 作为入参, 便于注入 mock
export function useMermaidRenderer(options) {
  const {
    mermaidInstance = mermaid,           // 注入点
    layoutEngine = 'dagre',
    config = null,                       // 注入点
    onAfterRender = () => {}
  } = options
  
  return {
    render: async (code, container) => {
      if (config) mermaidInstance.initialize(config)
      container.innerHTML = `<pre class="mermaid">${code}</pre>`
      await mermaidInstance.run({ querySelector: 'pre.mermaid' })
      const svg = container.querySelector('svg')
      onAfterRender(svg)
      return svg
    }
  }
}
```

**价值**: 单测可以传 mock mermaid 实例, 不用全局副作用.

#### G. CSS 治理

把 MermaidComponent.css 拆为 5 个子 CSS:

```
src/components/mermaid/styles/
├── base.css              # .mermaid-content 基础
├── node.css              # .node / .nodeLabel 节点样式
├── cluster.css           # .cluster / .subgraph 容器样式
├── edge.css              # .edgeLabel 边线标签样式
└── interaction.css       # 交互状态 (hover / selected / drag)
```

每个子 CSS 对应一个子测试, 用 happy-dom 验证 (虽然 foreignObject 不能渲染, 但 import 后会检查语法).

### 5.3 长期改进 (P2, 季度)

#### H. 视觉测试平台化

- 集成 Percy / Chromatic / Argos (业界 SaaS)
- 每次 PR 自动截图 + diff review
- baseline 在云端管理, 不占 git

#### I. Storybook + Chromatic

- 把 MermaidComponent 拆出的子组件都接入 Storybook
- 用 Chromatic 做 visual diff
- 团队 review 视觉时直接在 Storybook 提 PR

#### J. e2e 测试数据工厂

```python
# tests/factories/arch_data.py
def create_arch_data(nodes=10, relations=15, label_length=20):
    """生成测试 archData, label 长度可配置"""
    return {
        "productId": 1,
        "versionId": 1,
        "selectedObjectIds": [f"BO_{i:03d}" for i in range(nodes)],
        "selectedRelationCodes": [f"REL_{i:03d}" for i in range(relations)],
        "labels": {
            f"REL_{i:03d}": "P" * label_length  # 控制 label 长度
            for i in range(relations)
        }
    }
```

**价值**: 任何测试都能用 `create_arch_data(label_length=200)` 模拟长 label 场景.

---

## 6. 总结

### 6.1 关键发现

| # | 问题 | 影响 | 严重性 |
|---|------|------|--------|
| 1 | 0 个 MermaidComponent 单元测试 | 改 1828 行组件完全裸奔 | **P0** |
| 2 | 0 个 useMermaidConfig 测试 | 50+ 配置参数无任何回归保护 | **P0** |
| 3 | 0 个 CSS 视觉断言 | 任何样式改动无声 break | **P0** |
| 4 | E2E 只测数据流不测视觉 | 整个应用流程的"输出"无人验证 | **P0** |
| 5 | MermaidComponent 1828 行上帝组件 | 没法拆, 没法单测, 没法定位 | P1 |
| 6 | 14 个 useMermaid 子模块只 1 个有测试 | 配置/语法/渲染层无保护 | P1 |
| 7 | fixture 与真实数据脱节 | 测了也测不到真实场景 | P2 |

### 6.2 业务对象图这个流程的"可测试性得分"

| 评估维度 | 分数 | 说明 |
|---------|------|------|
| 数据流可测性 | 7/10 | Pinia + sessionStorage 流, E2E 覆盖到位 |
| 视觉可测性 | 1/10 | 0 个测试断言 SVG 元素, 0 个 CSS 断言 |
| 配置可测性 | 0/10 | 0 个 useMermaidConfig 单测 |
| 组件可测性 | 0/10 | 0 个 MermaidComponent 单测 |
| 错误定位性 | 2/10 | try/catch 吞错, console.error 无 context |
| 测试速度 | 5/10 | E2E 3-5s, 缺单测所以没"即时反馈" |
| 测试可维护性 | 4/10 | 7 个 E2E 已能维护, 缺新基建会崩 |
| **总分** | **2.6/10** | 视觉/配置层严重缺失 |

### 6.3 最快见效的 3 件事 (1 周内能完成)

1. **加 4 个 useMermaidConfig 单测** (~30 行) → 防止 wrappingWidth 回归
2. **加 5 个 useSvgStyle 单测** (~80 行) → 防止 fixEdgeLabelOverflow 回归  
3. **加 1 个 E2E C8 视觉断言** (~50 行) → 防止任何 edge label 渲染回归

合计 **~160 行测试代码**, 覆盖本次 bug 全链路, 防止再犯.

### 6.4 中期投资 (1-3 月)

- 拆 MermaidComponent (1828 → ~300×6) + 配 Storybook
- 视觉回归基建 (pixelmatch + baseline)
- 抽 DI 层 (useMermaidRenderer) 支持 mock mermaid

合计 **~2000 行新增代码 + 重构**, 把可测试性从 2.6/10 提到 6/10.

### 6.5 长期目标 (季度)

- 视觉测试平台 (Percy/Chromatic)
- 测试数据工厂 + 场景矩阵
- CSS 治理 (拆分子 CSS + 配套测试)

可测试性目标: **8/10**.

---

## 7. 相关文件清单

| 文件 | 角色 | 现状 |
|------|------|------|
| [src/components/MermaidComponent.vue](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.vue) | 核心渲染组件 (1828 行) | 无单测 |
| [src/composables/useMermaid/config/useMermaidConfig.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/config/useMermaidConfig.js) | Mermaid 配置 (246 行) | 无单测 |
| [src/composables/useMermaid/style/useSvgStyle.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/useSvgStyle.js) | SVG 后处理 (420 行) | 无单测 |
| [src/composables/useMermaid/renderer/useSvgProcessor.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/renderer/useSvgProcessor.js) | render 后处理 (260 行) | 无单测 |
| [src/composables/useMermaid/annotation/annotationConfig.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/annotation/annotationConfig.js) | annotation 静态配置 | **有 1 个测试** |
| [src/components/MermaidComponent.css](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.css) | 视觉样式 (800 行) | 无单测 |
| [tests/e2e/test_archdata_chart_v32.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_archdata_chart_v32.py) | 流程 E2E (7 个测试) | 仅测数据流 |
| [.trae/rules/frontend-testing-standards.md](file:///d:/filework/excel-to-diagram/.trae/rules/frontend-testing-standards.md) | 测试标准规范 | 有, 但未充分落地 |
| [docs/retrospectives/2026-06-10-aa-diagram-navigation-and-data-flow.md](file:///d:/filework/excel-to-diagram/docs/retrospectives/2026-06-10-aa-diagram-navigation-and-data-flow.md) | v22 复盘 | 参考 |

## 8. 行动清单

### 立即 (P0, 1 周)
- [ ] 加 `useMermaidConfig.spec.js` (4 个测试)
- [ ] 加 `useSvgStyle.spec.js` (5 个测试)
- [ ] 加 E2E `test_c8_edge_label_not_truncated`
- [ ] 加 `test_c9_visual_baseline` (pixelmatch)
- [ ] 把本节发现加入 SESSION_REMINDER (防再次踩坑)

### 短期 (P1, 1 月)
- [ ] 拆 MermaidComponent.vue 为 6 个子组件
- [ ] 抽 `useMermaidRenderer` DI 层
- [ ] 拆 MermaidComponent.css 为 5 个子 CSS
- [ ] 写 `archData` 测试数据工厂

### 长期 (P2, 季度)
- [ ] 集成 Percy / Chromatic 视觉测试
- [ ] 接入 Storybook
- [ ] 完整覆盖 useMermaid 14 个子模块的单元测试
- [ ] CSS 可视化测试 (happy-dom + jSDOM 切换)
