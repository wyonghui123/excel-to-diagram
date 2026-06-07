# ADR-003: Mermaid EdgeLabel 白色背景问题解决方案

## 状态
✅ 已采纳

## 背景

业务对象图的关系连线标签周围出现白色圆角矩形边框，影响视觉效果。该问题在多次尝试修复后仍然存在。

## 问题根因

**关键发现**: 白色圆角矩形不是 SVG 元素，而是 HTML 的 `<span>` 元素！

Mermaid 使用 **SVG + HTML 混合渲染**:
- 外层是 SVG `<g>` 容器
- 内层通过 `<foreignObject>` 嵌入 HTML
- HTML 部分带有 Mermaid 默认的白色背景样式

## 决策

采用 **CSS + JavaScript 混合方案**:

1. **CSS 方案**: 隐藏所有 HTML 子元素的背景和边框
2. **JavaScript 方案**: 添加白色背景矩形覆盖底层装饰元素

## 解决方案

### CSS 修复

```css
/* 隐藏 labelBkg 内部的 span 元素背景 */
.mermaid-content.businessObject :deep(.labelBkg span) {
  display: inline !important;
  background: transparent !important;
  background-color: transparent !important;
  border-radius: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
}

/* 隐藏 edgeLabel 内部所有 HTML 元素的背景和边框 */
.mermaid-content.businessObject :deep(.edgeLabel span),
.mermaid-content.businessObject :deep(.edgeLabel p),
.mermaid-content.businessObject :deep(.edgeLabel div) {
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}
```

### JavaScript 辅助

在 `useTooltip.js` 中添加白色背景矩形:

```javascript
// 为所有图表类型添加白色背景矩形来覆盖 S 型装饰线条
const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
bgRect.setAttribute('x', (labelLeft - 4).toFixed(2))
bgRect.setAttribute('y', (labelTop - 2).toFixed(2))
bgRect.setAttribute('width', (finalWidth + 8).toFixed(2))
bgRect.setAttribute('height', (finalHeight + 4).toFixed(2))
bgRect.setAttribute('fill', '#FFFFFF')
bgRect.setAttribute('stroke', 'none')
bgRect.setAttribute('rx', '3')
bgRect.setAttribute('ry', '3')
bgRect.setAttribute('opacity', '0.95')
labelParent?.insertBefore(bgRect, label)

// 隐藏 edgeLabel 内部的所有装饰性 SVG 元素
label.querySelectorAll('path, rect, polygon, polyline, circle, ellipse').forEach(el => {
  el.style.display = 'none'
  el.style.visibility = 'hidden'
  el.style.opacity = '0'
})
```

## 理由

1. **问题定位**: 通过调试日志输出真实 DOM 结构，发现是 HTML 样式问题
2. **foreignObject 陷阱**: Mermaid 使用 foreignObject 嵌入 HTML，需要同时处理 SVG 和 HTML 两套样式系统
3. **CSS 选择器策略**: 需要使用 `:deep()` 穿透 Vue 的作用域样式，`!important` 覆盖内联样式

## 影响

### 正面影响
- 解决了长期存在的视觉问题
- 提升了图表美观度
- 积累了 Mermaid 渲染机制的经验

### 需要注意
- 需要同时处理 SVG 和 HTML 两套样式系统
- `!important` 是必要的，用于覆盖 Mermaid 的内联样式
- 需要使用 `:deep()` 穿透 Vue 作用域

## 相关文件

- `src/components/MermaidComponent.vue` - CSS 样式定义
- `src/composables/useMermaid/tooltip/useTooltip.js` - 标签背景处理逻辑

## 详细文档

完整的问题排查过程和经验总结，请查看：
- [EdgeLabel 样式经验总结](../../docs/lessons-learned/mermaid/edgeLabel-styling.md)

## 决策日期
2026-03-24
