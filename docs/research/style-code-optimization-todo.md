# 样式和代码优化待办记录

## 创建日期

2026-04-07

## 问题反思

### 问题1: 拖尾线不显示

**现象**: 用户多次反馈拖尾线不显示

**根本原因**:

- `useTooltip.js` 创建拖尾线元素时无条件设置 `style.display = 'none'`
- JavaScript 内联样式优先级高于 CSS，导致 CSS 规则无法生效

**涉及文件**:

- `useTooltip.js`
- `useSvgProcessor.js`
- `edgeLabel-common.css`

### 问题2: 容器标题字体大小不生效

**现象**: 用户多次反馈容器标题字体大小没有变化

**根本原因**:

1. CSS 选择器与实际 DOM 结构不匹配
   - 实际结构: `.cluster-label > foreignObject > div > span > p`
   - CSS 选择器: `.cluster-label foreignObject p` (不匹配)
2. `useSvgStyle.js` 中的 `processElement` 只检查到 grandparentClass，没有检查 greatGrandparentClass
3. `processElement` 设置内联样式但没有设置 `fontSize`

**涉及文件**:

- `useSvgStyle.js`
- `MermaidComponent.vue`
- `MermaidComponent.css`
- `edgeLabel-common.css`

### 问题3: 容器标题斜体样式不生效

**现象**: 用户多次反馈容器标题斜体没有生效，HTML 结构中已设置 `font-style: italic` 但浏览器未渲染

**根本原因**:

- `:root` 中设置了 `font-synthesis: none`，阻止浏览器合成斜体样式
- 即使 `font-style: italic` 已设置，由于字体本身没有斜体变体，浏览器无法渲染斜体效果
- 该属性位于全局样式文件，影响范围广但隐蔽性高

**排查难点**:

1. HTML 结构显示 `font-style: italic` 已正确设置
2. CSS 选择器优先级正确，`!important` 已使用
3. JavaScript 逻辑无问题
4. `font-synthesis` 是较少使用的 CSS 属性，容易被忽略

**解决方案**:

- 从 `:root` 移除 `font-synthesis: none`
- 为 foreignObject 内元素显式设置 `font-synthesis: style !important`

**涉及文件**:

- `style.css` (全局样式)
- `edgeLabel-common.css` (foreignObject 样式)

**经验教训**:

- 全局样式设置需要谨慎评估影响范围
- 对于 `font-synthesis`、`text-rendering` 等高级 CSS 属性，需要了解其对字体渲染的具体影响
- 样式问题排查时，除了检查 `font-style` 等常规属性，也需要检查字体合成相关设置

### 问题4: 分组拖拽功能无效

**现象**: 在分组控制面板中，拖拽分组到其他容器的 drop-zone-area 没有效果

**根本原因**（初步分析）:

1. **索引问题**: `GroupItem.vue` 中 `handleGroupDragStart` 使用 `props.index` 作为 `sourceIndex`，但 `index` 是 flat groups 数组的索引。当分组嵌套时，嵌套分组的索引与 flat groups 数组索引不匹配。
2. **drop-zone-area 可见性问题**: `drop-zone-area` 使用 `isDragOver` 来显示，但拖拽分组时可能触发的是 `isGroupDragOver`。
3. **事件传递链问题**: 嵌套分组拖拽时，事件可能没有正确传递到父组件。

**涉及文件**:

- `GroupItem.vue` (分组拖拽逻辑)
- `LayoutControlPanel.vue` (事件处理)

**待排查**:

- [ ] 确认嵌套分组时 `props.index` 是否正确传递
- [ ] 确认 `drop-zone-area` 的显示条件是否正确
- [ ] 确认 dragOver/drop 事件是否正确触发
- [ ] 确认 `handleReorderGroups` 是否正确处理嵌套分组

***

## 图表配置和架构优化

### 问题5: 中心范围颜色配置不一致（排查历时约20次）

**现象**: 服务模块图配置步骤中，变更中心范围颜色后，分组控制节点和图表节点都没有实时更新

**根本原因**:

1. **配置属性不统一**: 业务对象图和服务模块图使用不同的属性存储中心范围颜色
   - 业务对象图: `centerObjectColor`
   - 服务模块图: `serviceModuleBgColor`
2. **共享组件期望统一 prop**: `LayoutSelector` / `LayoutControlPanel` / `GroupItem` 统一使用 `centerObjectColor` prop
3. **组件层级过深**: 数据流经过 4 层组件 (StepConfig → LayoutSelector → LayoutControlPanel → GroupItem)，每层都需要正确传递 props

**排查难点**:

- 普通函数（`getContainerColor`）不会自动追踪依赖变化
- Vue 模板中的函数调用不会建立响应式依赖
- 需要手动引用计算属性来"钩住"响应式系统

**涉及文件**:

- `StepConfig.vue`
- `LayoutSelector.vue`
- `LayoutControlPanel.vue`
- `GroupItem.vue`
- `ServiceModuleConfig.vue`
- `CenterDomainSelect.vue`

**经验教训**:

- 不同图表类型使用不同配置属性，但共享组件期望统一 prop，这是问题的根源
- 如果一开始就统一了配置属性，这个问题根本不会出现
- Vue 响应式系统中，普通函数的依赖追踪需要特别注意

**待优化**:

- [ ] 重构配置属性统一性：统一为 `centerScopeColor`
- [ ] 使用 Pinia/Vuex 集中状态管理，避免组件层层传递 props
- [ ] GroupItem 重构为 provide/inject 模式

### 问题6: 服务模块图节点颜色忽略 isCenter 状态

**现象**: 服务模块图中，属于中心范围的服务模块节点没有采纳中心范围颜色

**根本原因**:

- `buildServiceModuleDiagramData` 函数缺少 `serviceModuleBgColor` 参数
- `isCenter` 状态正确计算了，但节点颜色完全忽略它，统一使用子领域颜色

**涉及文件**:

- `serviceModuleDiagramBuilder.js` - 图表数据构建
- `useDiagramData.js` - 调用处

**数据模型**:

- 节点 `isCenter` = `centerServiceModuleCodes.has(sm.code)`
- 但 `color` = `subDomainColors[sm.subDomain]`（忽略了 isCenter）

**待优化**:

- [ ] 统一 `buildServiceModuleDiagramData` 和 `buildBusinessObjectDiagramData` 的参数结构
- [ ] 将中心范围颜色逻辑提取为独立的颜色策略 composable
- [ ] 构建器应接收"中心范围标识"而非"中心范围颜色"，颜色由渲染层决定

***

## 数据流与配置问题

### 问题7: 业务对象图颜色配置数据流（2026-04-13）

**背景**: 今天重新梳理了颜色配置的**数据模型**和**数据流程**，最终解决了分组控制节点颜色没有实时更新的问题。

**数据模型**:

```
Domain → SubDomain → ServiceModule → BusinessObject
isCenter 衍生属性：基于包含的业务对象计算
```

**数据流程（四个步骤）**:

1. **步骤1（中心选择）**: 用户选择中心范围业务对象 → `centerScope` 数组
2. **步骤2（关系选择）**: 基于中心范围选择关系 → `relationFilteredBoCodes`（并集，只增不减）
3. **步骤3（配置）**: 颜色配置、分组控制等
4. **步骤4（图表展示）**: 分组控制区域 + 图表渲染

**核心问题**: 颜色配置组件（`CenterDomainSelect`/`ServiceModuleConfig`）与分组控制组件（`GroupItem`）使用**不同的数据模型**判断节点是否为中心范围。

**解决关键**:

- 引入 `centerScopeMarkers` 计算属性，包含 `domains`、`subDomains`、`serviceModules` 三个 Map
- 统一数据模型：服务模块 isCenter = 包含中心范围业务对象

**涉及文件**:

- `useDiagramData.js` - `centerScopeMarkers` 计算属性
- `CenterDomainSelect.vue` - 业务对象图颜色配置
- `ServiceModuleConfig.vue` - 服务模块图颜色配置
- `GroupItem.vue` - 分组控制颜色渲染
- `LayoutControlPanel.vue` - 分组控制面板
- `LayoutSelector.vue` - 布局选择器
- `StepConfig.vue` - 配置步骤

**待优化**:

- [ ] 统一配置页面到分组控制的数据流，避免层层传递 props
- [ ] `centerScopeMarkers` 响应式优化，确保深层变化能触发更新

### 问题8: 服务模块图颜色配置问题

**背景**: 与问题7类似，但针对服务模块图。服务模块图的中心范围判断逻辑不同：服务模块是否为中心，取决于它**包含的子领域**是否为中心。

**核心区别**:

| 图表类型  | 中心范围判断依据                                      |
| ----- | --------------------------------------------- |
| 业务对象图 | 业务对象 code 是否在 `centerScope` 中                 |
| 服务模块图 | 服务模块的子领域是否在 `centerScopeMarkers.subDomains` 中 |

**已修复**:

- `buildServiceModuleDiagramData` 添加了 `serviceModuleBgColor` 参数
- 节点颜色根据 `isCenter` 状态选择使用 `serviceModuleBgColor` 或 `subDomainColors`

**待优化**:

- [ ] 统一业务对象图和服务模块图的颜色配置数据模型
- [ ] 避免 `centerObjectColor` vs `serviceModuleBgColor` 的分裂

### 问题9: 配置页面到展示的完整数据流问题

**问题描述**: 配置页面变更颜色后，需要经过多层组件才能到达分组控制和图表渲染，路径过长且缺乏统一性。

**当前数据流**:

```
配置组件（CenterDomainSelect/ServiceModuleConfig）
  ↓ update:colorGroupBy / update:serviceModuleBgColor
StepConfig
  ↓ :color-group-by / :center-object-color
LayoutSelector
  ↓ :color-group-by / :center-object-color
LayoutControlPanel
  ↓ :color-scheme / :center-object-color
GroupItem（递归）
  ↓ getContainerColor() / getNodeColor()
最终渲染
```

**问题**:

1. 4层组件传递，每层都需要正确定义 prop 和 watch
2. 普通函数（`getContainerColor`）不会自动响应变化
3. Vue 模板中的函数调用不建立响应式依赖
4. 需要手动引用计算属性（`centerObjectColorVersion`）来"钩住"响应式系统

**解决关键**:

- 添加 `centerObjectColorVersion` 计算属性，确保 `getContainerColor` 能响应变化
- 添加 `centerObjectColor` 到 `:key` 绑定，强制组件重新渲染

**待优化**:

- [ ] 使用 Pinia/Vuex 集中状态管理，减少 props 层层传递
- [ ] GroupItem 重构为 provide/inject 模式，避免递归传递 props
- [ ] 统一颜色配置状态管理，建立单一数据源

***

## 优化项

### 优化1: 建立样式控制地图

**描述**: 在一个文件中记录所有样式控制点

**待办**:

- [ ] 创建 `style-control-map.md`
- [ ] 记录拖尾线样式控制位置和优先级
- [ ] 记录容器标题样式控制位置和优先级
- [ ] 记录其他重要样式控制点

**应包含内容**:

```
容器标题字体:
  - CSS: edgeLabel-common.css (.cluster-label, .subgraph-label)
  - JS: useSvgStyle.js (内联)
  - 优先级: JS内联 > CSS

拖尾线显示:
  - JS: useTooltip.js (hideTails参数)
  - CSS: edgeLabel-common.css (.hide-tails)
  - 优先级: JS内联 > CSS
```

### 优化2: 统一样式控制职责

**描述**: 消除 JavaScript 内联样式和 CSS 的冲突

**待办**:

- [ ] 将拖尾线的显示/隐藏逻辑从 `useTooltip.js` 移除
- [ ] 改用 CSS 类 (`.hide-tails`) 控制拖尾线显示
- [ ] 统一容器标题样式由 CSS 控制，移除 `useSvgStyle.js` 中的 fontSize 设置

**原则**: 要么全部用 CSS（推荐），要么全部用 JS，不要混用

### 优化3: 全局样式审查与规范

**描述**: 建立全局样式管理规范，避免隐蔽的样式影响

**待办**:

- [ ] 审查 `:root` 和全局选择器中的所有样式设置
- [ ] 评估 `font-synthesis`、`text-rendering`、`font-feature-settings` 等高级属性的影响
- [ ] 建立全局样式白名单，仅允许经过评估的属性设置
- [ ] 为特殊全局样式添加注释说明其用途和潜在影响

**应审查的属性清单**:

```css
/* 字体渲染相关 */
font-synthesis: none; /* 阻止斜体/粗体合成 - 影响大 */
text-rendering: optimizeLegibility; /* 优化可读性 - 影响性能 */
-webkit-font-smoothing: antialiased; /* 字体平滑 - 跨浏览器差异 */

/* 布局相关 */
* { box-sizing: border-box; } /* 盒模型 - 影响所有元素 */
```

**原则**: 全局样式应该最小化，避免对特定组件产生意外影响

### 优化4: 图表构建器参数统一

**描述**: 统一业务对象图和服务模块图的图表构建器参数结构

**待办**:

- [ ] 统一 `buildServiceModuleDiagramData` 和 `buildBusinessObjectDiagramData` 的参数
- [ ] 中心范围颜色参数统一命名（如 `centerScopeColor`）
- [ ] 将中心范围颜色逻辑提取为独立的颜色策略 composable
- [ ] 构建器接收"中心范围标识"而非"颜色值"，颜色由渲染层决定

### 优化5: 状态管理重构

**描述**: 使用集中状态管理，避免组件层层传递 props

**待办**:

- [ ] 引入 Pinia/Vuex 管理图表配置状态
- [ ] 减少 StepConfig → LayoutSelector → LayoutControlPanel → GroupItem 的 props 层层传递
- [ ] 相关状态和逻辑内聚在同一个 store 中

### 优化6: 增加样式验证机制

**描述**: 在开发环境增加样式检查器

**待办**:

- [ ] 添加 DOM 结构打印功能
- [ ] 添加生效 CSS 规则检查
- [ ] 标记有冲突的样式

### 优化7: 增加单元测试

**描述**: 为关键样式逻辑添加测试

**待办**:

- [ ] 测试 `addTrailingDottedLines(hideTails=false)` 元素显示
- [ ] 测试 `addTrailingDottedLines(hideTails=true)` 元素隐藏
- [ ] 测试 CSS 选择器能匹配真实 DOM 结构

### 优化8: 文档结构整理

**描述**: 整理现有经验总结文档

**待办**:

- [ ] 合并重复的拖尾线相关文档
- [ ] 更新 `标签虚线方案经验总结.md` 中的实现细节
- [ ] 更新 `拖尾线隐藏功能实现经验总结.md` 中的代码示例

***

## 优先级

1. **高**: 优化4 - 图表构建器参数统一（避免颜色配置问题重复发生）
2. **高**: 优化2 - 统一样式控制职责（避免样式问题重复发生）
3. **高**: 优化3 - 全局样式审查与规范（避免隐蔽样式影响）
4. **高**: 优化5 - 状态管理重构（减少 props 层层传递）
5. **中**: 优化1 - 建立样式控制地图（便于后续维护）
6. **中**: 优化8 - 文档结构整理（保持知识同步）
7. **低**: 优化6,7 - 验证机制和单元测试（长期改进）

***

## 备注

这些问题反映了代码库中存在的深层问题：

- 样式职责分散在多个文件中
- DOM 结构与 CSS 选择器缺乏关联
- 缺乏对实际渲染结果的验证机制
- 配置属性在不同图表类型间不统一
- 组件层级过深，props 传递链复杂

建议优先处理优化4和优化5，从根本上避免类似问题再次发生。
