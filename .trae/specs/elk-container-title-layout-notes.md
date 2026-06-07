# ELK 布局容器标题与间距经验记录

## 核心发现

### 1. Mermaid ELK 集成的已知问题

**问题**：Mermaid 的 ELK 布局在计算 subgraph（容器）尺寸时，**可能没有正确考虑标题的宽度**。

**参考**：[GitHub Issue #4196](https://github.com/mermaid-js/mermaid/issues/4196)
> "In flowchart/graph diagrams, if I create a subgraph and use the elk layout, the subgraph title has no collision: the nodes and subgraphs inside it overlap the title"

**影响**：当容器标题变长（如包含禁用父级路径信息）时，容器宽度计算不正确，导致相邻容器发生重叠。

### 2. ELK 布局算法流程

ELK 布局算法的执行顺序：
1. **首先计算节点/容器尺寸**（基于标签内容）
2. 然后进行层级分配（layer assignment）
3. 节点排序（node ordering）
4. 最后计算坐标（positions）

**关键点**：尺寸计算在位置计算之前，但 Mermaid 的 ELK 集成可能存在尺寸计算不准确的问题。

## 解决方案

### 方案一：增加间距配置（治标）

在 `useMermaidConfig.js` 中增加 ELK 间距：

```javascript
// 容器间距 - 标题变长后需要更大间距
'elk.spacing.componentComponent': 250,
'elk.layered.spacing.componentComponent': 250,

// 父容器间距 - 嵌套容器之间的间距
'elk.spacing.parentParent': 50,

// 节点与容器边缘的间距
'elk.padding.nodes': '[top=30,left=50,right=50,bottom=30]',

// subgraph 标题边距
subGraphTitleMargin: { top: 15, bottom: 15 }
```

**局限性**：间距是固定值，无法根据实际标题长度动态调整。

### 方案二：标题分行显示（推荐）

通过分行显示减少单行宽度，避免容器过宽：

```javascript
// 格式化前
"需求管理（制造云 / 生产制造）"

// 格式化后
"需求管理\n（制造云 / 生产制造）"
```

**实现位置**：`src/utils/formatContainerTitle.js`

**格式化规则**：
1. 检测括号格式 `主名称（路径信息）`
2. 主名称单独一行
3. 括号内容整体一行（不拆分路径）
4. 无括号的超长标题按字符数分行

---

## 当前标题格式化实现的问题

### 文件位置
`src/utils/formatContainerTitle.js`

### 问题 1：括号内的路径仍然可能过长

**场景**：
```javascript
// 格式化后
"需求管理\n（供应链云 / 供应链计划 / 需求计划 / 需求预测）"
```

**问题**：路径信息仍然在一行，可能超过合理宽度

### 问题 2：maxLength 固定为 12 可能不够

**当前代码**：
```javascript
export function formatContainerTitle(title, maxLength = 12) {
  // ...
  if (title.length > maxLength) {
    // ...
  }
}
```

**问题**：
- 12 字符对中文字符来说可能不够
- 中文字符和英文字符宽度不同（中文字符通常是英文的 2 倍）

### 问题 3：分行逻辑不够稳健

**当前代码**：
```javascript
if (currentLine.length >= maxLength && char !== ' ') {
  lines.push(currentLine)
  currentLine = char
}
```

**问题**：
- 当刚好在非空格字符处分行时，可能导致单词/词组被截断
- 中文字符没有空格分隔，分行位置需要更智能

### 问题 4：未考虑 `\n` 已经存在的情况

**场景**：
- titleMap 可能已经包含换行符
- 再次格式化可能导致重复换行

---

## 标题格式化改进建议

### 改进 1：路径信息智能分行

```javascript
// 优化前
const pathPart = bracketMatch[2].trim()
return `${mainPart}\n（${pathPart}）`

// 优化后：路径超过一定长度也分行
const pathPart = bracketMatch[2].trim()
const pathSegments = pathPart.split(' / ')
if (pathSegments.length > 2) {
  const midIndex = Math.ceil(pathSegments.length / 2)
  const pathLine1 = pathSegments.slice(0, midIndex).join(' / ')
  const pathLine2 = pathSegments.slice(midIndex).join(' / ')
  return `${mainPart}\n（${pathLine1} / \n${pathLine2}）`
} else {
  return `${mainPart}\n（${pathPart}）`
}
```

### 改进 2：考虑字符宽度

```javascript
function calculateTextWidth(text) {
  let width = 0
  for (const char of text) {
    // 中文字符算 2，英文算 1
    width += char.charCodeAt(0) > 127 ? 2 : 1
  }
  return width
}

// 使用宽度而非字符数判断
if (calculateTextWidth(currentLine) + calculateTextWidth(char) > maxWidth) {
  // ...
}
```

### 改进 3：优化超长标题分行策略

```javascript
// 在中文字符的标点符号处优先分行
const punctuationChars = ['，', '。', '；', '、', '：']

// 优先在标点符号处换行
if (currentLine.length >= maxLength) {
  const lastPunctuation = punctuationChars
    .map(p => currentLine.lastIndexOf(p))
    .filter(idx => idx > 0)
    .sort((a, b) => b - a)[0]
  
  if (lastPunctuation && lastPunctuation > maxLength * 0.5) {
    lines.push(currentLine.substring(0, lastPunctuation + 1))
    currentLine = currentLine.substring(lastPunctuation + 1) + char
  } else {
    lines.push(currentLine)
    currentLine = char
  }
}
```

### 改进 4：避免重复换行

```javascript
// 先检查是否已经包含换行符
if (title.includes('\n')) {
  // 已经分行，返回原标题或做轻量处理
  return title
}
```

### 优先级建议

| 优先级 | 改进项 | 复杂度 | 效果 |
|--------|--------|--------|------|
| 高 | 改进 1（路径信息智能分行） | 低 | 直接解决长路径导致的问题 |
| 中 | 改进 2（考虑字符宽度） | 中 | 更准确的宽度计算 |
| 中 | 改进 4（避免重复换行） | 低 | 防止格式错乱 |
| 低 | 改进 3（优化超长标题分行） | 高 | 改善可读性 |

## 数据流关键点

### titleMap 的生成与传递

1. **生成位置**：`GroupModel.toMermaidConfig()`
   - 在遍历分组树时，为禁用分组的子容器生成带路径信息的标题
   - 格式：`${containerName}（${disabledPath.join(' / ')}）`

2. **传递路径**：
   ```
   GroupModel.toMermaidConfig()
     → layoutControlConfig.titleMap
     → MermaidComponent.effectiveLayoutControlConfig
     → businessObjectSyntax.generateMermaidCode()
     → buildVirtualContainers() 应用 titleMap
     → groupedLayout.js 生成 Mermaid 代码
     → formatContainerTitle() 分行格式化
   ```

3. **应用位置**：
   - `buildVirtualContainers()` 中更新 `group.title` 和 `container.fullTitle`
   - `groupedLayout.js` 中使用 `formatContainerTitle()` 格式化后输出

## 最佳实践

### 原生布局原则

**原则**：尊重布局引擎的计算结果，避免后处理修改位置/尺寸。

**遵循方式**：
- 在数据传入布局引擎之前完成所有标题计算
- 不在 SVG 后处理中修改容器位置或尺寸
- 通过调整输入数据（标题分行）而非输出结果来解决布局问题

### 标题设计建议

1. **控制单行长度**：尽量控制在 10-15 个字符以内
2. **合理分行**：主名称与附加信息分行显示
3. **避免过深嵌套**：禁用层级过多会导致标题过长

## 已移除的代码

以下 SVG 后处理代码因违反原生布局原则已被移除：

| 函数 | 原位置 | 功能 | 移除原因 |
|------|--------|------|----------|
| `fixElkContainerBounds` | useSvgProcessor.js | 调整容器间距 | 修改 ELK 计算的位置/尺寸 |
| `fixContainerTitleY` | useSvgProcessor.js | 修复标题 Y 坐标 | 修改 ELK 计算的位置 |
| `fixContainerTitlePosition` | useSvgProcessor.js | 增加容器高度 | 修改 ELK 计算的尺寸 |
| `moveContainerContentDown` | useSvgProcessor.js | 移动容器内容 | 修改边路径等关键属性 |

**移除代码量**：约 500 行

## 相关文件

- `src/utils/formatContainerTitle.js` - 标题格式化
- `src/composables/useMermaid/config/useMermaidConfig.js` - ELK 配置
- `src/composables/useMermaid/layouts/groupedLayout.js` - 布局代码生成
- `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js` - titleMap 应用
- `src/services/groupModel/GroupModel.js` - titleMap 生成

## 更新记录

- 2026-04-12：初始记录，解决容器重叠问题
- 2026-04-12：移除违反原生布局原则的 SVG 后处理代码
- 2026-04-12：新增当前实现问题分析和改进建议
