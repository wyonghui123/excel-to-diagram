# 拖尾线隐藏功能实现经验总结

## 1. 问题背景

用户需求：配置页面增加"隐藏关系标签拖尾线"开关，默认值逻辑：
- ELK 布局下默认隐藏
- Dagre 布局下默认显示

## 2. 拖尾线构成元素

通过 DOM 分析发现，Mermaid 生成的 `edgeLabel` 结构如下：

```html
<g class="edgeLabel edge-label-clean" transform="translate(2609, 412)">
  <!-- 拖尾线背景：需要隐藏的元素 -->
  <rect x="-41.95" y="-8.59" width="83.9" height="17.19"
        fill="#ffffff" fill-opacity="1" data-bg-rect="true"/>

  <!-- 标签内容：需要保留 -->
  <g class="label" transform="translate(...)">
    <foreignObject width="79" height="17">
      <div class="labelBkg">
        <span class="edgeLabel">
          <p>PPC13-PUM07</p>  <!-- 关系标签文字 -->
        </span>
      </div>
    </foreignObject>
  </g>
</g>
```

**关键发现**：
- 拖尾线主要是 `<rect>` 背景元素
- 文字内容在 `<p>` 标签中，**不应该被隐藏**
- 没有发现 `polygon` 或虚线 `line` 元素

## 3. 控制影响因素

### 3.1 布局引擎 (layoutEngine)

| 布局引擎 | 默认行为 | 说明 |
|---------|---------|------|
| `elk` | 隐藏拖尾线 | ELK 布局本身标签背景较复杂，默认隐藏 |
| `dagre` | 显示拖尾线 | Dagre 布局标签清晰，默认显示 |

### 3.2 用户配置 (hideLinkLabelTails)

| 配置值 | 含义 |
|-------|------|
| `null` | 自动模式，根据 layoutEngine 决定 |
| `true` | 强制隐藏 |
| `false` | 强制显示 |

### 3.3 优先级

```
强制隐藏 (true) > 强制显示 (false) > 自动模式 (null)
```

## 4. 实现方案

### 4.1 配置传递链路

```
StepConfig.vue (用户选择)
    ↓ updateConfig('hideLinkLabelTails', value)
useDiagramData.js (状态管理)
    ↓ generateDiagram()
buildServiceModuleDiagramData() / buildDiagramData() (数据构建)
    ↓
MermaidComponent.vue (渲染控制)
    ↓
hideLinkLabelTails() (DOM 操作)
```

### 4.2 核心代码

**MermaidComponent.vue** - 隐藏逻辑：

```javascript
const shouldHideTails = props.layoutEngine === 'elk' ||
  props.diagramData?.hideLinkLabelTails === true

if (shouldHideTails) {
  setTimeout(() => hideLinkLabelTails(), 500)
}

const hideLinkLabelTails = () => {
  const svg = mermaidContainer.value?.querySelector('svg')
  if (!svg) return

  const edgeLabels = svg.querySelectorAll('.edgeLabel, .edge-label')
  edgeLabels.forEach(label => {
    // 隐藏 rect 背景
    const rect = label.querySelector('rect')
    if (rect) {
      rect.style.display = 'none'
    }
  })
}
```

### 4.3 关键实现点

1. **延迟执行**：使用 `setTimeout(..., 500)` 等待 Mermaid 渲染完成
2. **只隐藏 rect**：不隐藏 `<p>` 或 `<text>` 元素，保留标签文字
3. **布局引擎判断**：在 MermaidComponent 层判断，不依赖上游配置默认值

## 5. 排查记录

### 5.1 问题1：配置值传递丢失

**现象**：`hideLinkLabelTails` 在 `useDiagramData.js` 中是 `null`，但传到 `MermaidComponent` 时变成了 `undefined`

**排查方法**：在每个环节添加日志

```javascript
console.log('=== generateDiagram 调试 ===')
console.log('hideLinkLabelTails:', diagramConfig.value.hideLinkLabelTails)
```

**结论**：用户之前手动选择了"否"，导致值被固定为 `false`，默认值逻辑不会重新计算

### 5.2 问题2：拖尾线元素定位错误

**现象**：隐藏了 `polygon` 和 `path`，但拖尾线依然存在

**排查方法**：打印每个 `edgeLabel` 的 `innerHTML`

```javascript
edgeLabels.forEach((label, index) => {
  console.log(`--- edgeLabel ${index} ---`)
  console.log('label.innerHTML:', label.innerHTML.substring(0, 100))
  console.log('找到 rect:', label.querySelector('rect'))
  console.log('找到 polygon:', label.querySelectorAll('polygon').length)
})
```

**结论**：拖尾线实际上是 `<rect>` 背景，不是 `polygon`

## 6. 经验教训

1. **SVG 结构分析**：通过浏览器 DevTools 检查实际 DOM 结构，不要假设
2. **延迟渲染**：Mermaid 渲染是异步的，需要等待 DOM 完全生成后再操作
3. **精确选择器**：使用 `querySelector('rect')` 而非 `querySelectorAll('polygon')`
4. **配置默认值**：用户手动选择会覆盖默认值，需要设计"自动模式"

## 7. 相关文件

| 文件 | 说明 |
|------|------|
| `src/components/MermaidComponent.vue` | 拖尾线隐藏逻辑实现 |
| `src/views/AADiagramApp/composables/useDiagramData.js` | 配置状态管理 |
| `src/views/AADiagramApp/components/steps/StepConfig.vue` | 配置页面 UI |
| `src/services/diagramDataBuilder.js` | 业务对象图数据构建 |
| `src/services/serviceModuleDiagramBuilder.js` | 服务模块图数据构建 |

---

*文档创建日期：2026-03-31*
