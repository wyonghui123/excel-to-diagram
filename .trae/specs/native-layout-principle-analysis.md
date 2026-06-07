# 原生布局原则 - 全面深入分析

## 概述

**原生布局原则**：尊重布局引擎（ELK/Dagre）的计算结果，避免后处理修改位置/尺寸。

本文档从数据流全链路分析所有可能影响原生布局的逻辑。

---

## 一、数据准备阶段

### 1.1 enabled 状态处理

**位置**：`GroupModel.js`、`groupFlattener.js`、`featureProcessor.js`

**影响**：
- `enabled=false` 的分组不创建容器，子元素被提升到父级
- 影响容器层次结构，进而影响 ELK 布局计算

**风险等级**：🟢 低（这是预期行为，在布局前完成）

**代码示例**：
```javascript
// groupFlattener.js:60
const isEnabled = group.layout?.enabled !== false
```

### 1.2 titleMap 生成

**位置**：`GroupModel.toMermaidConfig()` (GroupModel.js:302-398)

**影响**：
- 为禁用分组的子容器生成带路径信息的标题
- 标题长度直接影响 ELK 计算的容器宽度

**风险等级**：🟡 中（标题过长可能导致容器过宽）

**关键代码**：
```javascript
// GroupModel.js:374
const containerDisplayTitle = `${container.name || container.title}（${disabledPath.join(' / ')}）`
```

**改进建议**：
- ✅ 已实现：`formatContainerTitle()` 分行显示
- 可考虑：限制标题最大长度

### 1.3 fullTitle 计算

**位置**：`GroupModel.toMermaidConfig()` (GroupModel.js:340)

**影响**：
- 直接影响容器标题显示
- 如果在布局后修改，会违反原生布局原则

**风险等级**：🟢 低（已在布局前完成）

---

## 二、Mermaid 代码生成阶段

### 2.1 direction 设置

**位置**：`groupedLayout.js:219, 400, 437, 455`

**影响**：
- 设置 subgraph 的布局方向
- ELK 会根据 direction 计算节点排列

**风险等级**：🟢 低（这是 Mermaid 语法，ELK 正确处理）

**关键代码**：
```javascript
// groupedLayout.js:219
let direction = group.direction || 'TB'
code += `${indent}direction ${direction}\n`
```

### 2.2 inner/boundary 分离 ⚠️

**位置**：`groupedLayout.js:434-473`

**影响**：
- 将容器内节点分为"内部节点"和"边界节点"
- 创建两个额外的子容器：`_inner` 和 `_boundary`
- **这会影响 ELK 的布局计算**，因为创建了额外的 subgraph

**风险等级**：🟡 中（改变了容器结构）

**关键代码**：
```javascript
// groupedLayout.js:434-473
if (innerNodes.length > 0 && boundaryNodes.length > 0) {
  code += `${indent}    subgraph ${actualContainerId}_inner[" "]\n`
  code += `${indent}      direction ${containerDirection}\n`
  // ...
  code += `${indent}    subgraph ${actualContainerId}_boundary[" "]\n`
  // ...
}
```

**问题分析**：
1. 创建了额外的 subgraph，增加了布局复杂度
2. `_inner` 和 `_boundary` 容器有 `fill:none,stroke:none` 样式
3. ELK 需要为这些额外容器计算布局

**改进建议**：
- 评估是否真的需要这种分离
- 如果是为了连线优化，考虑其他方案

### 2.3 style 设置

**位置**：`groupedLayout.js:451, 469, 496, 509, 517`

**影响**：
- 设置容器颜色、边框等样式
- 不影响位置/尺寸计算

**风险等级**：🟢 低（仅影响视觉样式）

---

## 三、ELK 布局计算阶段

### 3.1 Mermaid ELK 集成问题 ⚠️⚠️

**问题**：Mermaid 的 ELK 集成在计算 subgraph 尺寸时，**可能没有正确考虑标题的宽度**

**参考**：[GitHub Issue #4196](https://github.com/mermaid-js/mermaid/issues/4196)

**影响**：
- 容器宽度计算不准确
- 导致相邻容器重叠

**风险等级**：🔴 高（这是根本原因）

**ELK 布局流程**：
1. 计算节点/容器尺寸（基于标签内容）← 问题出在这里
2. 层级分配（layer assignment）
3. 节点排序（node ordering）
4. 计算坐标（positions）

**问题根源**：
- Mermaid 在传递 subgraph 标题给 ELK 时，可能没有正确计算标题的实际渲染宽度
- 特别是使用 `foreignObject` 渲染 HTML 标签时

### 3.2 ELK 配置参数

**位置**：`useMermaidConfig.js:74-118`

**当前配置**：
```javascript
'elk.spacing.nodeNode': 100,
'elk.spacing.componentComponent': 250,
'elk.spacing.parentParent': 50,
'elk.padding.nodes': '[top=30,left=50,right=50,bottom=30]',
```

**风险等级**：🟡 中（固定值无法适应动态标题长度）

---

## 四、SVG 后处理阶段 ⚠️⚠️⚠️

### 4.1 fixElkContainerBounds 🔴🔴

**位置**：`useSvgProcessor.js:414-778`

**功能**：调整 ELK 嵌套容器的边界和间距

**影响**：
- **直接修改 ELK 计算的位置和尺寸**
- 修改容器的 `transform` 属性
- 修改 `rect` 的 `x`, `y`, `width`, `height`
- 移动容器内的所有内容（节点、标签、边）

**风险等级**：🔴 高（严重违反原生布局原则）

**关键代码**：
```javascript
// useSvgProcessor.js:531
containerToMove.container.setAttribute('transform', `translate(${tx}, ${ty + offset})`)

// useSvgProcessor.js:535
containerToMove.rect.setAttribute('y', containerToMove.y + offset)

// useSvgProcessor.js:752-753
parentRect.setAttribute('width', Math.max(currentParentW, requiredW))
parentRect.setAttribute('height', Math.max(currentParentH, requiredH))
```

**问题分析**：
1. 这是一个"补丁"方案，用于修复 ELK 布局的重叠问题
2. 但它违反了原生布局原则
3. 可能引入新的布局问题（如边线错位）

**改进建议**：
- ✅ 已添加开关：`enableContainerSpacingFix`
- 长期方案：优化 ELK 配置或标题分行

### 4.2 fixContainerTitleY 🔴

**位置**：`useSvgProcessor.js:361-401`

**功能**：修复容器标题的 Y 坐标

**影响**：
- 修改 `foreignObject` 的 `y` 属性
- 修改 `transform` 属性

**风险等级**：🔴 高（修改了 ELK 计算的位置）

**关键代码**：
```javascript
// useSvgProcessor.js:391
fo.setAttribute('y', newY)

// useSvgProcessor.js:397
labelEl.setAttribute('transform', `translate(${labelMatch ? labelMatch[1] : 0}, ${newY})`)
```

**当前状态**：🟡 已禁用（第 857 行注释掉）

### 4.3 fixContainerTitlePosition 🟡

**位置**：`useSvgProcessor.js:335-359`

**功能**：增加容器矩形的高度，给标题留出空间

**影响**：
- 修改 `rect` 的 `height` 属性

**风险等级**：🟡 中（修改了 ELK 计算的尺寸）

**关键代码**：
```javascript
// useSvgProcessor.js:354
rect.setAttribute('height', newHeight.toFixed(2))
```

**当前状态**：🟡 已禁用（第 858 行注释掉）

### 4.4 fixContainerTitleCenter 🟢

**位置**：`useSvgProcessor.js:295-329`

**功能**：设置容器标题居中对齐

**影响**：
- 仅修改 CSS 样式（`textAlign`, `margin`, `padding`）
- 不修改位置/尺寸属性

**风险等级**：🟢 低（仅影响视觉样式）

### 4.5 moveContainerContentDown 🔴

**位置**：`useSvgProcessor.js:783-837`

**功能**：递归移动容器内所有内容向下

**影响**：
- 移动子容器的 `rect.y`
- 移动节点的 `y`, `cy` 坐标
- 移动标签的 `y` 坐标
- 修改节点的 `transform` 属性
- **修改边的路径 `d` 属性**

**风险等级**：🔴 高（严重违反原生布局原则）

**关键代码**：
```javascript
// useSvgProcessor.js:789
childRect.setAttribute('y', currentY + offsetY)

// useSvgProcessor.js:799-802
shape.setAttribute('y', currentY + offsetY)
shape.setAttribute('cy', cy + offsetY)

// useSvgProcessor.js:819
node.setAttribute('transform', `translate(${tx}, ${ty + offsetY})`)

// useSvgProcessor.js:830-833
const newD = d.replace(/(\d+\.?\d*)\s*,\s*(\d+\.?\d*)/g, ...)
path.setAttribute('d', newD)
```

**问题分析**：
- 这是最危险的后处理函数
- 它修改了边的路径，可能导致连线错位
- 被 `fixElkContainerBounds` 调用

---

## 五、CSS 样式阶段 ⚠️

### 5.1 foreignObject 宽度设置 🟡

**位置**：`edgeLabel-common.css:146-147, 206-207, 256-257`

**样式**：
```css
.mermaid-content :deep(.cluster-label foreignObject) {
  width: auto !important;
  min-width: 100% !important;
}
```

**影响**：
- `width: auto` 让浏览器自动计算宽度
- `min-width: 100%` 强制最小宽度
- **这可能与 ELK 计算的宽度不一致**

**风险等级**：🟡 中（可能影响标题实际渲染宽度）

### 5.2 标题最大宽度限制 🟡

**位置**：`edgeLabel-common.css:338`

**样式**：
```css
.mermaid-content :deep(.cluster-label foreignObject > div) {
  max-width: 350px !important;
}
```

**影响**：
- 限制标题最大宽度为 350px
- 超长标题会被截断或换行
- **这与 ELK 计算的宽度可能不一致**

**风险等级**：🟡 中（可能导致标题显示不完整）

### 5.3 标题 padding/margin 🟡

**位置**：`edgeLabel-common.css:212-214, 262-264, 334-335`

**样式**：
```css
.mermaid-content :deep(.cluster-label foreignObject > div) {
  padding: 4px 8px !important;
  margin-left: 10px !important;
}
```

**影响**：
- 增加了标题的实际渲染尺寸
- **ELK 可能没有考虑这些额外的 padding/margin**

**风险等级**：🟡 中（可能导致标题溢出容器）

### 5.4 字体大小 🟡

**位置**：`edgeLabel-common.css:248`

**样式**：
```css
.mermaid-content :deep(.cluster-label p) {
  font-size: 24px !important;
}
```

**影响**：
- 24px 字体比默认字体大
- **ELK 可能使用默认字体大小计算宽度**

**风险等级**：🟡 中（可能导致标题宽度计算不准确）

### 5.5 white-space 设置 🟡

**位置**：`edgeLabel-common.css:229, 270, 336`

**样式**：
```css
white-space: nowrap !important;  /* 第 229, 270 行 */
white-space: normal !important;  /* 第 336 行 */
```

**影响**：
- `nowrap` 阻止标题换行
- `normal` 允许标题换行
- **不同选择器有不同的设置，可能导致不一致**

**风险等级**：🟡 中（可能导致标题显示不一致）

---

## 六、问题汇总

### 高风险 🔴

| 问题 | 位置 | 影响 | 状态 |
|------|------|------|------|
| ~~fixElkContainerBounds~~ | ~~useSvgProcessor.js~~ | ~~修改容器位置/尺寸~~ | ✅ 已移除 |
| ~~fixContainerTitleY~~ | ~~useSvgProcessor.js~~ | ~~修改标题位置~~ | ✅ 已移除 |
| ~~moveContainerContentDown~~ | ~~useSvgProcessor.js~~ | ~~移动所有内容~~ | ✅ 已移除 |
| ~~fixContainerTitlePosition~~ | ~~useSvgProcessor.js~~ | ~~修改容器高度~~ | ✅ 已移除 |
| Mermaid ELK 标题宽度 | Mermaid 集成 | 容器宽度计算不准确 | ✅ 标题分行显示 |

### 中风险 🟡

| 问题 | 位置 | 影响 | 建议 |
|------|------|------|------|
| inner/boundary 分离 | groupedLayout.js:434-473 | 创建额外 subgraph | 评估必要性 |
| CSS width: auto | edgeLabel-common.css | 宽度计算不一致 | 考虑固定宽度 |
| CSS max-width: 350px | edgeLabel-common.css | 标题可能截断 | 调整或移除 |
| CSS padding/margin | edgeLabel-common.css | 尺寸计算不一致 | 统一设置 |
| CSS font-size: 24px | edgeLabel-common.css | 宽度计算不准确 | 确保 ELK 配置一致 |

### 低风险 🟢

| 问题 | 位置 | 影响 | 建议 |
|------|------|------|------|
| enabled 状态处理 | GroupModel.js | 影响容器层次 | 预期行为 |
| titleMap 生成 | GroupModel.js | 影响标题长度 | 已分行处理 |
| direction 设置 | groupedLayout.js | 影响布局方向 | 预期行为 |
| style 设置 | groupedLayout.js | 影响视觉样式 | 无影响 |
| fixContainerTitleCenter | useSvgProcessor.js | 仅修改样式 | 无影响 |

---

## 七、改进建议

### 7.1 已完成

1. ✅ 标题分行显示（`formatContainerTitle.js`）
2. ✅ 增加 ELK 间距配置
3. ✅ 移除违反原生布局原则的 SVG 后处理代码：
   - `fixElkContainerBounds`（约 370 行）
   - `fixContainerTitleY`（约 40 行）
   - `fixContainerTitlePosition`（约 30 行）
   - `moveContainerContentDown`（约 55 行）
4. ✅ 移除 `enableContainerSpacingFix` prop

### 7.2 待优化

1. 统一 CSS 样式设置，确保与 ELK 计算一致
   - 移除 `width: auto`
   - 移除 `max-width: 350px`
   - 统一 `white-space` 设置

2. 评估 `inner/boundary` 分离的必要性
   - 如果不需要，移除以简化布局

3. 确保 ELK 配置与 CSS 样式一致
   - 字体大小
   - padding/margin

### 7.3 长期方案

1. 优化 ELK 配置
   - 动态计算间距
   - 根据标题长度调整

2. 贡献 Mermaid
   - 修复 ELK 标题宽度计算问题

---

## 八、验证清单

在修改任何影响布局的代码时，请检查：

- [ ] 是否在布局前完成所有数据准备？
- [ ] 是否避免修改 ELK 计算的位置/尺寸？
- [ ] CSS 样式是否与 ELK 配置一致？
- [ ] 是否测试了不同标题长度的场景？
- [ ] 是否测试了禁用父级后的标题显示？

---

## 更新记录

- 2026-04-12：初始版本，全面分析原生布局影响因素
- 2026-04-12：移除违反原生布局原则的 SVG 后处理代码（约 500 行）
