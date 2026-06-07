# 画布背景颜色分层方案经验总结

## 问题描述

在实现图表缩放和拖拽功能时，需要区分三个区域：
1. **天空**（最外层，不可拖拽）= 白色背景
2. **画**（可拖拽区域）= 灰色背景
3. **图表内容** = 白色背景

**核心需求**：zoom out 时，画（灰色）和图表（白色）一起缩小，露出天空（白色）。

## 错误尝试

### 尝试1：简单的百分比宽高
```css
.draggable-area {
  width: 100%;
  height: 100%;
  background-color: #E0E0E0;
}
```
**问题**：灰色区域太小，图表内容溢出到白色背景上。

### 尝试2：基于 SVG viewBox 计算尺寸
```javascript
const viewBox = svgEl.getAttribute('viewBox')
const parts = viewBox.split(' ').map(Number)
svgWidth = parts[2]
svgHeight = parts[3]
```
**问题**：viewBox 和实际渲染尺寸不匹配，导致灰色区域仍然不够大。

### 尝试3：使用 scrollWidth/scrollHeight
```javascript
svgWidth = svgEl.scrollWidth
svgHeight = svgEl.scrollHeight
```
**问题**：时机问题，SVG 可能还没完全渲染，获取到的尺寸不准确。

### 尝试4：动态计算倍数
```javascript
const multiplier = 3
draggableAreaEl.style.width = (contentWidth * multiplier) + 'px'
```
**问题**：CSS 中的 `width: 100%` 会覆盖 JavaScript 设置的值。

## 根本原因分析

1. **CSS 优先级问题**：CSS 中的 `width: 100%; height: 100%;` 会覆盖 JavaScript 动态设置的尺寸
2. **transform-origin 问题**：使用 `top left` 导致缩放从左上角开始，而不是中心
3. **overflow 问题**：父容器使用 `overflow: visible` 导致超出部分无法正确显示
4. **缩放限制问题**：minScale 计算不合理，限制了 zoom out 的范围

## 正确解决方案

### 1. HTML 结构
```html
<div class="mermaid-container">
  <div class="mermaid-wrapper">
    <div class="draggable-area">
      <div class="diagram-canvas">
        <div class="mermaid-content"></div>
      </div>
    </div>
  </div>
</div>
```

### 2. CSS 关键设置
```css
/* 天空 - 白色背景，overflow: hidden 确保超出部分不显示 */
.mermaid-wrapper {
  width: 100%;
  height: 100%;
  overflow: hidden !important;
  position: relative;
  background-color: #FFFFFF;
}

/* 画 - 灰色背景，绝对定位居中，transform-origin: center */
.draggable-area {
  overflow: visible !important;
  position: absolute;
  top: 50%;
  left: 50%;
  background-color: #E0E0E0;
  transform-origin: center center !important;
  /* 注意：不要设置 width/height，由 JavaScript 动态设置 */
}

/* 图表画布 - 透明背景，显示灰色 */
.diagram-canvas {
  width: 100%;
  height: 100%;
  background-color: transparent;
}
```

### 3. JavaScript 关键设置
```javascript
// 设置灰色区域为固定大尺寸
const canvasSize = 8000
draggableAreaEl.style.width = canvasSize + 'px'
draggableAreaEl.style.height = canvasSize + 'px'

// 使用负 margin 实现居中
draggableAreaEl.style.marginLeft = (-canvasSize / 2) + 'px'
draggableAreaEl.style.marginTop = (-canvasSize / 2) + 'px'

// 图表内容居中显示
mermaidContent.style.position = 'absolute'
mermaidContent.style.top = '50%'
mermaidContent.style.left = '50%'
mermaidContent.style.transform = 'translate(-50%, -50%)'
```

### 4. 缩放限制设置
```javascript
// 允许更小的缩放比例，让用户能看到整个图表
const minScaleX = containerWidth / contentWidth
const minScaleY = containerHeight / contentHeight
const minScale = Math.max(0.01, Math.min(minScaleX, minScaleY) * 0.15)
```

## 核心要点

1. **CSS 不要设置固定尺寸**：让 JavaScript 动态控制 `.draggable-area` 的尺寸
2. **使用绝对定位 + 负 margin 居中**：确保灰色区域始终居中
3. **transform-origin: center center**：缩放从中心开始，而不是左上角
4. **overflow: hidden**：父容器隐藏超出部分，确保白色天空可见
5. **足够大的固定尺寸**：使用 8000px 等大尺寸，确保 zoom out 后仍能看到灰色
6. **合理的缩放限制**：minScale 要足够小（如 0.01），确保能看到完整图表

## 物理世界比喻

- 🪟 **窗户** = 浏览器视口（我们能看到的全部区域）
- 🌌 **天空** = 最外层区域（白色背景，不可拖拽）
- 🖼️ **画** = 可拖拽区域（灰色背景，可以拖拽和平移）
- 📊 **画中的图表** = 图表内容（白色背景）

**zoom out 的效果**：
- 人和窗户不动，画远离窗户
- 画（灰色）本身大小不变，但在窗户里看起来变小了
- 能看到更多的天空（白色）

## 最终效果

- ✅ 初始状态：灰色背景上显示白色的图表容器
- ✅ zoom out 后：灰色区域从中心缩小，露出白色天空
- ✅ zoom out 范围：可以缩小到 1%，看到完整图表
- ✅ 拖拽功能：可以在灰色区域内拖拽图表

## 注意事项

1. 不要在 CSS 中为 `.draggable-area` 设置 `width` 和 `height`
2. 确保 `transform-origin` 设置为 `center center`
3. 父容器必须设置 `overflow: hidden`
4. 缩放限制要根据实际图表尺寸动态计算
