# Mermaid 连线高亮功能开发指南

## 概述

本文档记录了在 Mermaid 图表中实现连线标签点击高亮功能时遇到的问题及解决方案，为后续类似开发提供参考。

## 核心功能

### 功能需求
- 点击连线标签时，对应的连线高亮显示（加粗 + 阴影）
- 点击空白区域时，取消连线高亮，恢复原始样式
- 连线颜色保持不变，只改变粗细

### 实现效果
- **选中时**: `stroke-width: 4px` + `drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))`
- **非选中时**: `stroke-width: 2px`（两种图表统一）

---

## 问题与解决方案

### 问题 1: MutationObserver 移除动态添加的样式

#### 问题描述
点击连线标签后，连线高亮效果立即消失。

#### 根本原因
之前为了解决 Mermaid 默认选中样式问题，添加了 MutationObserver 监控 style 属性变化。当设置 `strokeWidth = '8px'` 时：
1. MutationObserver 检测到 style 属性变化
2. 检查到 `strokeWidth` 存在
3. 调用 `removeAttribute('style')` 移除整个 style 属性
4. 导致连线高亮效果立即消失

#### 解决方案
**删除 MutationObserver**，改用 CSS 样式覆盖 Mermaid 默认选中样式。

```javascript
// 删除这段代码
const observer = new MutationObserver((mutations) => {
  // ... 移除选中样式
})
observer.observe(svg, { attributes: true, subtree: true })
```

#### 经验总结
- MutationObserver 会监控所有 style 变化，包括我们主动添加的样式
- 在需要动态修改样式的场景下，应避免使用 MutationObserver 移除样式
- 优先使用 CSS 覆盖或事件阻止的方式处理默认行为

---

### 问题 2: 点击容器内部空白区域无法清除高亮

#### 问题描述
选中连线后，点击容器内部的空白区域没有反应，只有点击容器外部才能清除高亮。

#### 根本原因
判断条件过于严格：
```javascript
// 错误的判断
if (e.target === svg || e.target.tagName === 'svg') {
  clearHighlight()
}
```

这个条件只有直接点击 SVG 元素才会触发，点击容器内部的背景 rect 等元素时，`e.target` 不是 SVG 本身。

#### 解决方案
使用更宽松的判断逻辑，检查点击目标是否为节点、连线或标签：

```javascript
svg.addEventListener('click', (e) => {
  const target = e.target
  const isNode = target.closest('.node')
  const isEdgePath = target.closest('.edgePath') || target.classList.contains('flowchart-link')
  const isEdgeLabel = target.closest('.edgeLabel')
  
  // 如果点击的不是节点、连线或标签，则清除高亮
  if (!isNode && !isEdgePath && !isEdgeLabel) {
    clearHighlight()
  }
})
```

#### 经验总结
- 使用 `element.closest()` 方法向上查找父元素，判断点击位置
- 避免使用 `e.target === svg` 这种过于严格的判断
- 考虑 SVG 内部结构的复杂性，使用更灵活的判断方式

---

### 问题 3: 连线粗细恢复不一致

#### 问题描述
取消选中后，连线粗细与原始状态不一致。

#### 根本原因
清除高亮时，设置 `strokeWidth = ''` 会移除内联样式，但不会恢复到 Mermaid 生成的原始值。

```javascript
// 错误的做法
selectedElements.path.style.strokeWidth = ''  // 移除内联样式，但可能不是原始值
```

#### 解决方案
根据图表类型恢复到原始的 strokeWidth：

```javascript
const clearHighlight = () => {
  if (selectedElements.path) {
    // 恢复到原始的 strokeWidth (2px)
    selectedElements.path.style.strokeWidth = '2px'
    selectedElements.path.style.filter = ''
    selectedElements.path = null
  }
}
```

#### 经验总结
- 在修改样式前，保存原始值
- 恢复时使用具体的值，而不是空字符串
- 不同图表类型可能有不同的默认样式，需要区分处理

---

### 问题 4: edgeLabel 背景色无法设置为透明

#### 问题描述
服务模块图的连线标签背景显示为深灰色，无法通过 CSS 设置为透明。

#### 根本原因
1. **Mermaid 配置**: 服务模块图使用 `htmlLabels: true`，导致标签使用 foreignObject 渲染
2. **CSS 样式冲突**: 多个 CSS 规则设置了不同的背景色
3. **优先级问题**: Mermaid 默认样式优先级较高

#### 解决方案

**方案 1: Mermaid 配置**
```javascript
mermaid.initialize({
  themeVariables: {
    edgeLabelBackground: 'transparent'
  }
})
```

**方案 2: CSS 样式覆盖**
```css
/* 服务模块图 - 关系标签样式 - 透明背景 */
.mermaid-content.service-module :deep(.edgeLabel),
.mermaid-content.service-module :deep(.edgeLabel *),
.mermaid-content.service-module :deep(.edgeLabel rect),
.mermaid-content.service-module :deep(.edgeLabel foreignObject) {
  background-color: transparent !important;
  background: transparent !important;
  fill: transparent !important;
}
```

**方案 3: JavaScript 动态设置**
```javascript
// 强制设置 edgeLabel 背景透明
edgeLabels.forEach((label) => {
  label.style.backgroundColor = 'transparent'
  
  const rects = label.querySelectorAll('rect')
  rects.forEach((rect) => {
    rect.style.fill = 'transparent'
    rect.setAttribute('fill', 'transparent')
  })
  
  const foreignObjects = label.querySelectorAll('foreignObject')
  foreignObjects.forEach((fo) => {
    fo.style.background = 'transparent'
  })
})
```

#### 经验总结
- Mermaid 的 `htmlLabels` 配置会影响标签的渲染方式
- CSS 样式需要覆盖多个层级（edgeLabel、rect、foreignObject、div、span）
- 使用 `!important` 确保样式优先级
- 必要时使用 JavaScript 动态设置样式

---

## 最佳实践

### 1. 样式管理
- 优先使用 CSS 类名管理样式，避免大量内联样式
- 使用 `!important` 确保样式优先级
- 考虑 SVG 和 HTML 元素的样式差异

### 2. 事件处理
- 使用事件委托处理 SVG 内部元素的事件
- 使用 `element.closest()` 判断元素层级关系
- 注意事件冒泡和传播

### 3. 状态管理
- 保存选中元素的引用，便于清除状态
- 区分不同图表类型的默认样式
- 恢复状态时使用具体的值

### 4. 调试技巧
- 使用 `console.log` 输出元素结构和样式
- 检查 Mermaid 生成的 DOM 结构
- 使用浏览器开发者工具检查样式优先级

---

## 代码示例

### 完整的连线高亮实现

```javascript
// 保存选中状态
const selectedElements = {
  path: null,
  label: null
}

// 清除高亮
const clearHighlight = () => {
  if (selectedElements.path) {
    selectedElements.path.style.strokeWidth = '2px'
    selectedElements.path.style.filter = ''
    selectedElements.path = null
  }
  if (selectedElements.label) {
    selectedElements.label = null
  }
}

// 标签点击事件
label.addEventListener('click', (e) => {
  e.stopPropagation()
  
  // 清除之前的高亮
  clearHighlight()
  
  // 记录选中状态
  selectedElements.label = label
  
  // 找到对应的连线
  const correspondingPath = findPathByLabel(label)
  
  if (correspondingPath) {
    selectedElements.path = correspondingPath
    // 高亮连线
    correspondingPath.style.strokeWidth = '4px'
    correspondingPath.style.filter = 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'
  }
})

// SVG 点击事件（清除高亮）
svg.addEventListener('click', (e) => {
  const target = e.target
  const isNode = target.closest('.node')
  const isEdgePath = target.closest('.edgePath')
  const isEdgeLabel = target.closest('.edgeLabel')
  
  if (!isNode && !isEdgePath && !isEdgeLabel) {
    clearHighlight()
  }
})
```

---

## 相关文件

- `src/components/MermaidComponent.vue` - Mermaid 图表组件
- `docs/mermaid-node-text-solution.md` - 节点文字显示问题解决方案

---

## 更新日志

- 2026-03-19: 初始版本，记录连线高亮功能的开发经验
