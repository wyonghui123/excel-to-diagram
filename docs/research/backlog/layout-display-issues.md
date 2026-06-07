# Backlog

## 布局与显示问题

### [HIGH] 图表超出灰色背景被截断

**问题描述**：
当图表内容较宽时（如节点数量多、使用 ELK 布局等），图表会超出灰色背景（`.draggable-area`）的宽度，导致左右两侧被截断无法显示。

**复现条件**：
- 图表节点数量较多
- 使用 ELK 布局引擎
- 分组嵌套较深

**已尝试的解决方案**：

1. **修改 `.mermaid-wrapper` overflow**：
   - `overflow: hidden` → `overflow: auto`
   - 添加 `top: 0; left: 0; width: 100%; height: 100%`
   - 结果：图表消失

2. **修改 `.draggable-area` 尺寸**：
   - 使用 `min-width: 100%; min-height: 100%` 替代固定的 `width/height: 100%`
   - 结果：图表消失

3. **在 `autoFitDiagram` 中动态设置 `.draggable-area` 尺寸**：
   - 设置 `draggableAreaEl.style.width = contentWidth`
   - 结果：图表消失

**根本原因分析**：

当前结构：
- `.mermaid-wrapper`: `position: absolute; overflow: hidden; width: 100%; height: 100%`
- `.draggable-area`: `position: absolute; width: 100%; height: 100%; transform: scale(N)`
- `.mermaid-content`: 包含 SVG 内容

问题：
1. `autoFitDiagram` 计算缩放比例（例如 0.3）并应用到 `.draggable-area`
2. `transform: scale()` 只改变视觉大小，不改变元素占据的空间
3. 缩放后的内容可能被 `.mermaid-wrapper` 的 `overflow: hidden` 裁剪
4. 灰色背景始终是 100% x 100%，与缩放后的内容不匹配

**需要的解决方案**：

需要重新设计布局逻辑，让灰色背景 `.draggable-area` 的大小能够：
1. 至少填满 `.mermaid-wrapper`
2. 如果内容更大，能够扩展以覆盖整个图表内容
3. 不破坏现有的缩放和平移功能

可能的方向：
- 使用 `min-width/min-height` 配合 `inline-size` 或容器查询
- 重新设计 `autoFitDiagram` 逻辑，使其同时考虑灰色背景和内容缩放
- 考虑使用 CSS `contain` 属性

**状态**：待分析

---

## 已解决问题

### [RESOLVED] ELK 布局相关问题

**解决时间**：2026-04-12

**已解决内容**：

1. **容器标题与间距问题** ✅
   - 通过 `formatContainerTitle.js` 实现标题分行显示
   - 在 `useMermaidConfig.js` 中增加 ELK 间距配置
   - 移除了约 500 行违反原生布局原则的 SVG 后处理代码

2. **相关文件更新**：
   - `src/utils/formatContainerTitle.js` - 标题格式化
   - `src/composables/useMermaid/config/useMermaidConfig.js` - ELK 配置
   - `src/composables/useMermaid/layouts/groupedLayout.js` - 布局代码生成
   - `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js` - titleMap 应用
   - `src/services/groupModel/GroupModel.js` - titleMap 生成

**解决方案详情**：
参见 `d:\filework\excel-to-diagram\.trae\specs\elk-container-title-layout-notes.md`

**状态**：已解决
