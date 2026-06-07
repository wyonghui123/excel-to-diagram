# Mermaid 图表文字居中问题排查记录

## 问题描述

业务对象图和服务模块图中，节点内的文字（名称+编码）没有在节点中间位置显示，表现为偏左或偏左上。

## 排查过程

### 1. 了解 SVG 结构

通过调试发现 Mermaid 生成的节点 SVG 结构如下：

```html
<g class="node">
  <rect x="-90" y="-50" width="180" height="100" ... />
  <foreignObject x="-90" y="-50" width="100" height="60">
    <div style="display: table-cell; ...">
      <span style="...">
        <p>招标定标单<br>(AAA01)</p>
      </span>
    </div>
  </foreignObject>
</g>
```

**关键发现**：
- `rect` 的 `x` 和 `y` 是负数（如 `-90`, `-50`），表示 rect 的中心在 SVG 坐标系的原点
- `foreignObject` 的 `x` 和 `y` 是 `null`
- `foreignObject` 内部是 HTML 元素（div > span > p）

### 2. 尝试的解决方案

#### 方案1：修改 foreignObject 的 x, y 属性
```javascript
foreignObject.setAttribute('x', rectX)
foreignObject.setAttribute('y', rectY)
```
**结果**：文字跑到左上角

#### 方案2：不修改 foreignObject 属性，只用 CSS
```javascript
innerDiv.style.display = 'table'
span.style.display = 'table-cell'
span.style.verticalAlign = 'middle'
span.style.textAlign = 'center'
```
**结果**：仍在调试中

### 3. Mermaid 配置中的 htmlLabels

```javascript
// 服务模块图
htmlLabels: true  // 使用 HTML 标签

// 业务对象图
htmlLabels: false  // 理论上使用 SVG 标签
```

**注意**：即使设置 `htmlLabels: false`，Mermaid 仍然可能使用 foreignObject + HTML 标签来渲染节点内容。

### 4. 关键 CSS 属性

foreignObject 内部的 HTML 元素需要设置：

```css
/* 内部 div */
display: table;
width: 100%;
height: 100%;
margin: 0;
padding: 0;

/* 内部 span */
display: table-cell;
text-align: center;
vertical-align: middle;
width: 100%;
height: 100%;
box-sizing: border-box;
margin: 0;
padding: 0;

/* 内部 p */
text-align: center;
margin: 0;
padding: 0;
```

### 5. 调试技巧

```javascript
// 打印 foreignObject 信息
console.log(`  foreignObject: width=${foWidth}, height=${foHeight}, x=${foX}, y=${foY}`)

// 获取 foreignObject 的实际边界
const foBbox = foreignObject.getBBox()
console.log(`  foreignObject getBBox: x=${foBbox.x}, y=${foBbox.y}`)

// 检查内部 HTML 结构
console.log(`  innerDiv innerHTML: ${innerDiv.innerHTML.substring(0, 200)}`)

// 检查样式
console.log(`  innerDiv 原始样式: display=${getComputedStyle(innerDiv).display}`)
```

## 根因分析

Mermaid 生成的节点使用 `foreignObject` 来包含 HTML 元素，但：
1. foreignObject 的默认位置是 `(0, 0)`，而 rect 的中心在负坐标位置
2. HTML 元素在 foreignObject 内部需要正确设置 display 模式才能居中

## 待验证方案

1. 使用 CSS `table` / `table-cell` 布局
2. 确保 foreignObject 的宽度和高度与 rect 匹配
3. 不修改 foreignObject 的 x, y 属性，让 CSS 处理布局

## 经验总结

1. foreignObject 是 SVG 中嵌入 HTML 的元素，其坐标系与 SVG 元素独立
2. HTML 元素的居中需要使用 table/table-cell 或 flex 布局
3. 调试时应关注 getBBox() 返回的实际边界，而非属性值
4. Mermaid 的 htmlLabels 配置不一定完全控制标签类型
