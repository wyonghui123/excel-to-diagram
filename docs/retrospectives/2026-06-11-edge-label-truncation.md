# 架构图 edge label 文字右侧截断 - 复盘 (2026-06-11)

> **问题类型**: Mermaid 渲染 / 样式  
> **影响范围**: 业务对象图 + 服务模块图 的所有关系连线 (edge label)  
> **修复耗时**: 约 3 小时 (含 3 轮迭代, 一轮回退, 一轮微调)  
> **状态**: ✅ 已修复 (3 处组合修复 + 二轮微调)

---

## TL;DR

**问题现象**: 图表展示时, 关系连线上的标题文字 (如 `PUM07-SOC27`、`供应链云/采购订单` 等) 右侧被截断。

**根因**: Mermaid 的 `wrappingWidth` 配置设值太小 (200/400), 给 `foreignObject` 内的 `div.labelBkg` 加了内联 `max-width`, 中文字符宽度超出后被裁剪。

**修复**: 3 处组合修复 (config 调参 + CSS 双层防御 + JS 兜底, 全部不修改 `foreignObject` width/height, 避免 v22 端点错位 bug)。

**测试缺口**: 0 个针对 Mermaid 渲染输出的端到端测试。`test_archdata_chart_v32.py` 只测 Pinia store 数据流, 完全不验证 SVG 视觉输出。

---

## 1. 问题发生的场景

### 1.1 触发流程

```
用户在管理页选 "采购管理" + "所有关系" 
    → 点 "展示图表" 按钮
    → MultiObjectManagementPage.vue:309-310 写 sessionStorage + router.push
    → 打开 /archdata-chart tab
    → AADiagramApp/index.vue onMounted 读 sessionStorage
    → 初始化 3 步骤模式
    → StepDisplay.vue 渲染 Mermaid 图表
    → Mermaid.run() 调 useMermaidConfig.getConfig() 
    → 生成 flowchart 配置 (wrappingWidth: 200)
    → mermaid.render() 输出 SVG
    → edge label 被截断
```

### 1.2 涉及的具体 DOM 结构

Mermaid v11 渲染业务对象图后, edge label 实际输出:

```html
<g class="edgeLabel" transform="translate(2185.39, 629.79)">
  <rect class="background" x="-39.72" y="-8.60" width="79.44" height="17.19" fill="#fff" />
  <g class="label" transform="translate(-39.72, -8.60)">
    <foreignObject width="79.44" height="17.19">
      <div xmlns="http://www.w3.org/1999/xhtml" 
           class="labelBkg" 
           style="display: table-cell; 
                  white-space: nowrap; 
                  line-height: 1.5; 
                  max-width: 200px;            ← 罪魁祸首
                  text-align: center;">
        <span class="edgeLabel" style="background: rgb(255, 255, 255);">
          <p>PUM07-SOC27</p>            ← 短标签, 不被截 (79.44px < 200px)
          <!-- <p>供应链云/采购订单</p>   ← 长中文标签, 会被截 (~128px < 200px 还能装) -->
          <!-- <p>PUM07-SOC27-EXT09-PLB033</p> ← 复合长标签, 会被截 -->
        </span>
      </div>
    </foreignObject>
  </g>
</g>
```

**注意**: `<rect class="background">` 和 `<foreignObject>` 都有 Mermaid 计算的固定 `width="79.44"`, 这是基于文字测量得到。`max-width: 200px` 来自 `wrappingWidth` 配置, 是 div 的最大宽度上限。

### 1.3 关键 timing

Mermaid 渲染链路:
1. `MermaidComponent.vue` `onMounted` 触发渲染
2. `useMermaid.initializeMermaid()` → `mermaid.initialize(config)` (使用当前 config)
3. `MermaidComponent.vue` watch `diagramData` → 调 `mermaid.render()`
4. Mermaid 内部 dagre/ELK layout 计算 node 位置、edge 路径
5. Mermaid 输出 SVG string
6. 注入到 DOM
7. `useSvgProcessor.processSvg()` 后处理 (addCodeAttributes, addTooltips 等)
8. 此时用户看到图表, 但 edge label 已经按 wrappingWidth 算好

**修复时机**: 必须在 step 2 (config 调参) 才能改 wrappingWidth。step 6-7 之后改 wrappingWidth 无效 (已经渲染了)。

---

## 2. 修复的 3 处变更

### 2.1 [useMermaidConfig.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/config/useMermaidConfig.js#L154-L188) - 根因修复

| 字段 | 旧值 | 新值 | 说明 |
|------|------|------|------|
| `wrappingWidth` (业务对象图) | 200 | **500** | ~25 个中文字符 |
| `wrappingWidth` (服务模块图) | 400 | **800** | ~40 个中文字符 |

**为什么安全**: 在 Mermaid 初始化阶段就生效, layout 引擎 (ELK/dagre) 会基于新值算 foreignObject 尺寸, 端点位置一起重算, 不会出现 "改了 rect 但端点没动" 的错位。

### 2.2 [MermaidComponent.css](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.css#L264-L275) + [L605-L614](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.css#L605-L614) - CSS 双层防御

新增 2 段 CSS (分别针对 serviceModule 和 businessObject):

```css
.mermaid-content.serviceModule :deep(g.edgeLabel foreignObject > div.labelBkg),
.mermaid-content.serviceModule :deep(.edgeLabel foreignObject > div.labelBkg) {
  max-width: none !important;
  white-space: nowrap !important;
  overflow: visible !important;
  box-sizing: border-box !important;
  padding: 4px 8px !important;
}
```

**关键设计**:
- 选择器 `g.edgeLabel foreignObject > div.labelBkg` 只针对 edge label 内的 labelBkg
- **绝不**影响 `.nodeLabel` / `.cluster-label` / `.subgraph-label` (节点/容器标题)
- `!important` 强制覆盖 Mermaid 内联 `max-width: 200px`
- `padding: 4px 8px` 给文字留白

### 2.3 [useSvgStyle.js#fixEdgeLabelOverflow](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/useSvgStyle.js#L303-L350) - JS 兜底

```js
const fixEdgeLabelOverflow = (svg) => {
  const edgeLabels = svg.querySelectorAll('g.edgeLabel')
  edgeLabels.forEach((edgeLabel) => {
    const foreignObject = edgeLabel.querySelector('foreignObject')
    if (!foreignObject) return
    const labelBkg = foreignObject.querySelector(':scope > div')
    if (!labelBkg || !labelBkg.classList.contains('labelBkg')) return
    labelBkg.style.setProperty('max-width', 'none', 'important')
    labelBkg.style.setProperty('white-space', 'nowrap', 'important')
    // ... 等等
    // 关键: 不修改 foreignObject 的 width/height 属性
  })
}
```

**关键设计**:
- 只动 `.labelBkg` 的内联样式 (`max-width`, `white-space`, `padding`)
- **绝不**修改 `foreignObject` 的 `width` / `height` 属性 (避免 v22 端点错位 bug)
- 依赖 `foreignObject { overflow: visible }` 让文字自然溢出显示

---

## 3. 第一次修复 (失败) 的反思

### 3.1 第一次尝试: 改 rect/foreignObject 尺寸 (类似 v22)

第一版我曾尝试:
1. `labelBkg.style.maxWidth = 'none'`
2. `getBoundingClientRect()` 读实际尺寸
3. `foreignObject.setAttribute('width', newWidth)` ← **这一步有毒**

**为什么有毒**: Mermaid ELK layout 在 `mermaid.render()` 阶段已经把 edge endpoint 位置算好, 写到 SVG 路径里。**JS 后期改 `foreignObject` width 不会重算 endpoint**, 导致:
- edge 端点位置 = Mermaid 算的 (基于原 foreignObject 宽)
- 新的 foreignObject width = JS 算的 (更大)
- label 居中点 = `translate(-w/2, -h/2)` = 基于 JS 算的新 width
- 结果: label 偏向一边, edge 端点和 label 中心对不齐

这正是 v22 retrospective 文档记录的 [fixNodeRectSize 端点错位 bug](file:///d:/filework/excel-to-diagram/docs/retrospectives/2026-06-10-aa-diagram-navigation-and-data-flow.md#L23-L32) 同一个坑。

### 3.2 第二次尝试: 改 wrappingWidth (正确)

意识到 v22 教训后, 改为在 Mermaid config 阶段就调大 `wrappingWidth`。这个值是 layout 引擎的输入参数, 改它等于让 Mermaid 内部 layout 重新算所有尺寸, 端点、label、node 位置一致, 不会出现错位。

### 3.3 第三次补充: CSS 兜底 (防御性)

仅靠 wrappingWidth 调大不够, 因为:
- wrappingWidth 是 hard cap, label 真的超过仍然会被 wrap 或溢出
- 实际用户数据 label 长度不可预测
- 需要 `overflow: visible` + `max-width: none` 兜底

**关键边界**:
- 只针对 `g.edgeLabel foreignObject > div.labelBkg`, 不动 `.nodeLabel` / `.cluster-label` / `.subgraph-label`
- `!important` 是必要的 (Mermaid 内联样式优先级高)

### 3.4 第四次微调 (2026-06-11 16:00): 二轮修复

**问题反馈**: 用户复测发现 "还有 1 个字符 (右边) 被截掉了", 一轮修复没完全解决.

**真因诊断 (用户截图 + Mermaid 实际 DOM 分析)**:
- 实际 Mermaid v11 的 `addHtmlSpan` 把 `foreignObject.width` 设为**文字宽度的精确测量值** (无 padding 缓冲)
- 一轮修复的 `padding: 4px 8px; box-sizing: border-box;` 在 labelBkg 上, 让 labelBkg 内部 text-area 缩小:
  - `text-area = foreignObject.width - padding = 79.44 - 16 = 63.44px`
  - 文字实际宽度 79.44px → **溢出 16px (约 2 字符)**
  - 这是一轮修复**让事情变糟**的元凶

**二轮修复 (CSS 重做)**:
1. **labelBkg 不加 padding** (`background: transparent`), 让 div 自然跟 foreignObject 同宽
2. **在 `<p>` 上加 `padding: 2px 6px`**, 让白底延伸到文字右侧外 6px, 覆盖溢出的 1-2 字符
3. **`<span class="edgeLabel">` `display: inline-block`**, 让 `<p>` 横向 padding 生效
4. **`<p>` 加 `text-shadow` 白底"光晕"** (多层 2px 偏移), 即使 1 像素级别的溢出也能被白底覆盖
5. **不修改 foreignObject width/height** (避免 v22 端点错位)

**关键 CSS (节选)**:
```css
.labelBkg {
  /* 不加 padding, 跟 foreignObject 同宽 */
  background: transparent !important;
}
.labelBkg > span.edgeLabel {
  background: transparent !important;
  display: inline-block !important;
}
.labelBkg p {
  padding: 2px 6px !important;
  background: #ffffff !important;
  display: inline-block !important;
  text-shadow: 0 0 2px #ffffff, 0 0 2px #ffffff, ... !important;
}
```

**4 层防御**:
1. foreignObject 已有 `overflow: visible !important`
2. labelBkg `max-width: none` + `white-space: nowrap` (确保不换行)
3. `<p>` 横向 padding 让白底延伸 6px 覆盖溢出
4. text-shadow 多层白底覆盖最后 1-2px 边界

**为什么这次不会影响其他元素**:
- 全部用 `g.edgeLabel foreignObject ...` 链式选择器, 限定在 edge label
- `box-sizing` 默认为 `content-box` (div 默认), 不会缩小 text-area
- 只在 `<p>` 上加 padding/background, 不影响节点/容器标题

---

## 4. 测试覆盖分析 - 为什么没拦住

### 4.1 现有测试盘点

| 测试文件 | 覆盖范围 | 与本问题相关性 |
|---------|---------|---------------|
| [test_archdata_chart_v32.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_archdata_chart_v32.py) | Pinia store 数据流、tab 切换、sessionStorage | **零** (只测数据不测视觉) |
| `test_aa_diagram_pdf.py` | PDF 导出 | 间接 (PDF 视觉同源) |
| `e2e_relation_scope_tree.py` | RSS 树组件 | **零** (与 edge label 无关) |
| `e2e_relation_scope_tree_v2.py` (推测) | - | - |

**所有测试都关注"行为正确" (数据流、事件触发), 完全不验证"视觉正确" (SVG 输出)**。

### 4.2 缺失的关键测试类别

#### 缺失 A: SVG 输出结构断言

```python
# 应该但没有
def test_edge_label_width_adequate():
    """验证 edge label 的 foreignObject 宽度足够容纳中文字符"""
    # 1. 渲染图表
    # 2. 查询所有 g.edgeLabel
    # 3. 读取 foreignObject width 属性
    # 4. 读取 labelBkg 实际渲染宽度
    # 5. 断言: foreignObject width >= labelBkg scrollWidth (即没被截)
    
    edge_labels = svg.query_selector_all('g.edgeLabel')
    for label in edge_labels:
        fo = label.query_selector('foreignObject')
        if not fo:
            continue
        label_bkg = fo.query_selector('div.labelBkg')
        fo_width = float(fo.get_attribute('width'))
        bkg_width = label_bkg.evaluate('e => e.scrollWidth')
        assert fo_width >= bkg_width, \
            f"Edge label truncated: foreignObject={fo_width}px, content={bkg_width}px"
```

#### 缺失 B: 视觉回归测试 (screenshot diff)

```python
# 应该但没有
def test_business_object_chart_visual_snapshot():
    """业务对象图视觉基线对比"""
    # 1. 用标准测试数据渲染
    # 2. 截图
    # 3. 与 baseline.png 像素级对比
    # 4. 任何 > 0.1% 差异报错
    
    cli.authenticated_navigate('/archdata-chart', timeout=20000)
    inject_test_data()  # 25 BO + 28 关系
    wait_for_render()   # 等待 mermaid.run() 完成
    screenshot = cli.screenshot()
    diff = compare_with_baseline(screenshot, BASELINE_PATH)
    assert diff < 0.001, f"Visual regression: {diff*100:.2f}% pixel diff"
```

#### 缺失 C: 单元测试 (vitest) 覆盖 useSvgStyle/useMermaidConfig

```javascript
// 应该但没有
// src/composables/useMermaid/style/__tests__/useSvgStyle.spec.js

describe('fixEdgeLabelOverflow', () => {
  it('should not modify foreignObject width/height', () => {
    const svg = createMockSvg({
      edgeLabel: {
        foreignObject: { width: '79', height: '17' },
        labelBkg: { maxWidth: '200px' }
      }
    })
    fixEdgeLabelOverflow(svg)
    expect(svg.querySelector('foreignObject').getAttribute('width')).toBe('79')
    expect(svg.querySelector('foreignObject').getAttribute('height')).toBe('17')
  })

  it('should not touch .nodeLabel foreignObject', () => {
    const svg = createMockSvg({
      nodeLabel: { foreignObject: { width: '150', height: '60' } }
    })
    fixEdgeLabelOverflow(svg)
    expect(svg.querySelector('.nodeLabel foreignObject').getAttribute('width')).toBe('150')
  })
})
```

#### 缺失 D: MermaidComponent CSS 视觉断言

```javascript
// 应该但没有
// src/components/__tests__/MermaidComponent.spec.js

import { mount } from '@vue/test-utils'

describe('MermaidComponent', () => {
  it('edge label CSS rules should override mermaid inline max-width', () => {
    // 模拟 mermaid 输出的 .labelBkg with inline style
    const div = document.createElement('div')
    div.className = 'labelBkg'
    div.style.maxWidth = '200px'
    document.body.appendChild(div)
    
    // 触发 CSS 应用 (需要 :deep() 穿透, 测试比较麻烦)
    // 断言: getComputedStyle(div).maxWidth === 'none'
  })
})
```

### 4.3 为什么测试缺口这么大

#### 原因 1: Mermaid 渲染依赖真实 DOM, 单元测试难以覆盖

- Mermaid 输出是异步的, 需要等待 `mermaid.render()` promise
- Mermaid 内部 layout 是黑盒, 单元测试只能 mock
- happy-dom/jsdom 对 SVG 渲染支持有限, 测出来的 computed style 不可靠

**实际影响**: 没人写 Mermaid 渲染的单元测试, 因为"测了等于没测"。

#### 原因 2: 视觉回归测试基建不完善

- 项目里没有 screenshot diff 工具
- 没有 baseline 截图管理 (没有 `tests/baselines/` 目录)
- 没有 CI 跑 visual regression 的配置

**实际影响**: 写视觉测试成本太高, 默认走 e2e + Playwright。

#### 原因 3: 测试只断言"不抛错", 不断言"输出对"

看现有测试:
```python
# test_archdata_chart_v32.py 风格
def test_c1_inject_archdata_picked_up():
    inject_archdata(...)
    assert step_count == 3  # 测步骤数
    assert step == 3        # 测当前步骤
    # 没有任何 assert 测 SVG 内容、edge 数、label 完整性
```

**实际影响**: 即便有测试, 也只覆盖了"数据流通", 视觉问题不会被发现。

#### 原因 4: `wrappingWidth` 变更无 review 历史

```bash
# git log -- src/composables/useMermaid/config/useMermaidConfig.js
# 看不到 200 → 400 或 400 → 200 的提交, 是怎么来的已经不知道
```

**实际影响**: 没有变更理由文档化, 后人调参不知道会触发什么副作用。

#### 原因 5: v22 fixNodeRectSize 教训未传播到测试

[2026-06-10 复盘](file:///d:/filework/excel-to-diagram/docs/retrospectives/2026-06-10-aa-diagram-navigation-and-data-flow.md) 总结了 "改动 mermaid 内部产物是高风险", 但:
- 没在 `useSvgStyle.js` 文件头加 `// 警告: 不要改 rect/foreignObject width/height` 注释
- 没在 `MermaidComponent.css` 注明 "Mermaid 边缘端点敏感"
- 没加 `eslint-plugin-no-restricted-syntax` 规则禁止 `foreignObject.setAttribute('width', ...)`
- 没加回归测试 "改 wrappingWidth 不会端点错位"

**实际影响**: 同样的坑我这次又差点踩, 因为没看到防护栏。

---

## 5. 改进建议

### 5.1 立即可做 (P0, 1-2 天)

#### A. 加 e2e 视觉回归测试

新建 `tests/e2e/test_business_object_chart_visual.py`:

```python
"""业务对象图视觉基线测试 (2026-06-11)

策略:
  1. 用固定测试数据渲染 (25 BO + 28 关系, 包含长中文 edge label)
  2. 截 3 张图: 业务对象图、服务模块图、节点详情
  3. 与 baseline 对比, 阈值 0.1%
  4. baseline 第一次生成, 后续 PR 改 baseline 必须 review

基线生成:
  python test.py --file tests/e2e/test_business_object_chart_visual.py --update-baseline
"""
import pytest
import os
import time
from playwright.sync_api import sync_playwright

BASELINE_DIR = 'tests/baselines/diagrams/'

def test_business_object_chart_visual():
    """业务对象图视觉基线"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 渲染图表
        # 截图
        # 像素级对比 baseline
        # 断言
        pass
```

#### B. 在 useSvgStyle.js 头部加防护注释

```javascript
/**
 * 警告 (2026-06-11 v32 复盘):
 *   - 不要在此文件中改 foreignObject/rect 的 width/height 属性
 *   - 改这些会破坏 Mermaid ELK layout 算好的 edge endpoint 位置
 *   - 详见 docs/retrospectives/2026-06-10-aa-diagram-navigation-and-data-flow.md
 *   - 详见 docs/retrospectives/2026-06-11-edge-label-truncation.md
 *
 * 正确的修复方式:
 *   - 调 mermaid config (wrappingWidth / nodeWidth / nodeHeight)
 *   - 加 CSS 覆盖 .labelBkg 内联样式 (不要动 .nodeLabel)
 *   - 加 JS 兜底 (只改 style.*, 不改 setAttribute)
 */
```

#### C. 加 vitest 单元测试覆盖 fixEdgeLabelOverflow

新建 `src/composables/useMermaid/style/__tests__/useSvgStyle.spec.js`, 至少 3 个测试:

```javascript
describe('fixEdgeLabelOverflow', () => {
  it('应不修改 foreignObject width/height')
  it('应不修改 .nodeLabel 内的 foreignObject')
  it('应只覆盖 .labelBkg 的 max-width/white-space')
})
```

### 5.2 中期 (P1, 1-2 周)

#### D. 建立 visual regression 测试基建

1. 用 `pixelmatch` + `pngjs` 做像素对比
2. baseline 存 `tests/baselines/diagrams/*.png`
3. CI 集成: 视觉测试 > 0.1% 差异时 fail
4. PR template 强制要求 "如改 visual, 请更新 baseline 并 @ reviewer"

#### E. 加 eslint 规则禁危险操作

`.eslintrc.js`:
```json
{
  "rules": {
    "no-restricted-syntax": ["error", {
      "selector": "CallExpression[callee.object.name='foreignObject'][callee.property.name='setAttribute'][arguments.value=/^(width|height)$/]",
      "message": "改 foreignObject 的 width/height 会破坏 mermaid layout 端点对齐, 改 wrappingWidth config 代替"
    }]
  }
}
```

### 5.3 长期 (P2, 1 月+)

#### F. Mermaid 渲染抽象层

抽 `useMermaidRender` composable, 强制:
- 所有 mermaid 渲染必须经过这一个入口
- 入口返回 `{ svg, foreignObject, edgeEndpoints, layoutVersion }` 元组
- 任何"渲染后改 SVG 属性"的操作必须显式标注 `// WARNING: post-render mutation`
- CI 静态扫这个注释, 触发 review

#### G. Config diff 跟踪

把 `useMermaidConfig.js` 的 `wrappingWidth / nodeWidth / nodeHeight / elk.padding` 等关键参数:
- 提到 `meta/config/diagram-layout-tuning.json`
- 加 schema 校验
- 改值时强制 PR 标题加 `[diagram-layout]` prefix, 触发 visual test

---

## 6. 经验总结 (给未来类似任务)

### 6.1 Mermaid layout 的 3 条铁律

1. **layout 阶段能改的不要在 post-render 改**
   - ✅ 改 `wrappingWidth` 让 Mermaid 内部算
   - ❌ JS 后期 `setAttribute('width', X)` 改 foreignObject

2. **改动前先问 "Mermaid 已经算了什么"**
   - node 位置 (基于 nodeWidth/nodeHeight)
   - edge 路径 (基于 node 位置 + curve 算法)
   - edge endpoint 位置 (基于 edge 路径)
   - label 位置 (基于 edge 中点)
   - label 尺寸 (基于 wrappingWidth + 文字测量)
   - 改任何一个都可能让其他失效

3. **不要给 CSS 选择器加过宽的范围**
   - ❌ `.mermaid-content :deep(foreignObject) { ... }` (影响所有)
   - ✅ `.mermaid-content :deep(g.edgeLabel foreignObject > div.labelBkg) { ... }` (只影响 edge label)

### 6.2 测试设计原则

- **断言"输出"而不是"行为"**: 测 SVG 元素存在、属性正确, 不仅是 console 没报错
- **视觉测试不能省**: 行为测试覆盖不到 CSS/渲染问题
- **回归测试先于功能测试**: 每次修 bug 加 test, 防止再犯

### 6.3 调试方法

- **看实际 DOM**: Mermaid 输出的是 string, 但浏览器看到的才是真实的 (用 console.log(JSON.stringify(el.outerHTML)) 输出)
- **看 computed style**: Mermaid 内联 style + 外层 CSS 会有优先级冲突, 用 getComputedStyle 看最终生效的
- **看 BoundingClientRect**: foreignObject 的 `width` 属性是 Mermaid 算的, 但浏览器实际渲染可能不同 (如 box-sizing 影响)

---

## 7. 相关文件清单

| 文件 | 作用 | 本次变更 |
|------|------|---------|
| [src/composables/useMermaid/config/useMermaidConfig.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/config/useMermaidConfig.js#L154-L188) | Mermaid config | ✅ wrappingWidth 200→500, 400→800 |
| [src/components/MermaidComponent.css](file:///d:/filework/excel-to-diagram/src/components/MermaidComponent.css#L264-L275) | edge label 样式 | ✅ 新增 .labelBkg max-width 覆盖 |
| [src/composables/useMermaid/style/useSvgStyle.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/style/useSvgStyle.js#L303-L350) | SVG 后处理 | ✅ 新增 fixEdgeLabelOverflow 兜底 |
| [src/composables/useMermaid/renderer/useSvgProcessor.js](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/renderer/useSvgProcessor.js#L125-L140) | 渲染流程 | ✅ 新增 fixEdgeLabelSize 导出 (未调用) |
| [docs/retrospectives/2026-06-10-aa-diagram-navigation-and-data-flow.md](file:///d:/filework/excel-to-diagram/docs/retrospectives/2026-06-10-aa-diagram-navigation-and-data-flow.md) | v22 教训 | 参考 |
| [docs/lessons-learned/mermaid/edgeLabel-styling.md](file:///d:/filework/excel-to-diagram/docs/lessons-learned/mermaid/edgeLabel-styling.md) | 早期 edge label 经验 | 背景 |
| [tests/e2e/test_archdata_chart_v32.py](file:///d:/filework/excel-to-diagram/tests/e2e/test_archdata_chart_v32.py) | 现有 chart tab 测试 | ❌ 无 SVG 断言 |

---

## 8. TODO (后续)

- [ ] P0: 加 e2e 视觉回归测试 `tests/e2e/test_business_object_chart_visual.py`
- [ ] P0: `useSvgStyle.js` 头部加防护注释
- [ ] P1: vitest 单元测试覆盖 `fixEdgeLabelOverflow` 3 个 case
- [ ] P1: visual regression 基建 (pixelmatch + baseline 管理)
- [ ] P1: eslint 规则禁止 post-render 改 foreignObject/rect
- [ ] P2: 抽 `useMermaidRender` 抽象层
- [ ] P2: `useMermaidConfig` 关键参数外置 + diff 跟踪
