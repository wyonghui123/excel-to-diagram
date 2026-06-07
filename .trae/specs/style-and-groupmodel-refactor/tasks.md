# 样式与GroupModel重构任务清单

## 阶段一：样式优化

### 任务 1.1：优化 useSvgStyle.js - 移除内联样式
- [x] 1.1.1 备份当前 `useSvgStyle.js` 文件
- [x] 1.1.2 将 `applyContainerTitleItalic` 改为 `validateContainerTitles`，只检测不做修改
- [x] 1.1.3 将 `fixArrowMarkers` 中的样式设置移除，保留 DOM 操作
- [x] 1.1.4 保留 `updateNodeStyles` 中的颜色设置（因为是动态的）
- [x] 1.1.5 移除所有 `el.style.fontStyle`、`el.style.fontSize`、`el.style.transform` 设置
- [x] 1.1.6 移除 `setTimeout` 调用（改用 waitForRender）

### 任务 1.2：修复 useTooltip.js - 拖尾线改用 CSS 类控制
- [x] 1.2.1 备份当前 `useTooltip.js` 文件
- [x] 1.2.2 在 `addTrailingDottedLines` 函数中，删除 `if (hideTails) { tailLine.style.display = 'none' }`
- [x] 1.2.3 删除 `if (hideTails) { endMarker.style.display = 'none' }`
- [x] 1.2.4 在函数末尾添加 `if (hideTails) { svg.classList.add('hide-tails') }`
- [x] 1.2.5 确认 `edgeLabel-common.css` 中 `.hide-tails` 规则存在

### 任务 1.3：移除 setTimeout hack - 改用 waitForRender
- [x] 1.3.1 在 `useSvgStyle.js` 中创建 `waitForRender` 辅助函数
- [x] 1.3.2 使用轮询机制替代固定延迟的 setTimeout
- [x] 1.3.3 保留 MutationObserver 作为渲染完成检测的备选方案

### 任务 1.4：确保 font-synthesis 正确设置
- [x] 1.4.1 检查 `edgeLabel-common.css` 中是否已有 `font-synthesis: style !important`
- [x] 1.4.2 确认 `font-synthesis: style !important` 已存在于 CSS

### 任务 1.5：功能验证
- [x] 1.5.1 启动开发服务器 (http://localhost:3006/)
- [ ] 1.5.2 测试容器标题是否正确显示斜体（待用户验证）
- [ ] 1.5.3 测试拖尾线隐藏功能是否正常（待用户验证）
- [ ] 1.5.4 确认无控制台错误（待用户验证）

## 阶段二：GroupModel 重构收尾

### 任务 2.1：验证 useDiagramData.js 日志集成
- [x] 2.1.1 检查 `useDiagramData.js` 是否导入 `DataFlowLogger`
- [ ] 2.1.2 确认 `generateDiagram` 方法有日志输出（console.log 待清理）

### 任务 2.2：验证旧 console.log 清理
- [x] 2.2.1 检查 `GroupModel.js` 是否还有遗留的 console.log - 无
- [x] 2.2.2 检查 `groupedLayout.js` 是否还有遗留的 console.log - 无
- [x] 2.2.3 检查 `useBusinessObjectSyntax.js` 是否还有遗留的 console.log - 已替换为 DataFlowLogger
- [ ] 2.2.4 检查 `useDiagramData.js` 是否还有遗留的 console.log - 有（待清理）

### 任务 2.3：添加单元测试
- [x] 2.3.1 检查 `GroupModel.test.js` 是否存在 - 存在
- [ ] 2.3.2 添加循环引用测试用例（构造 A→B→C→A 数据）
- [ ] 2.3.3 添加深度限制测试用例（构造深度 > 20 的数据）
- [ ] 2.3.4 验证测试通过

### 任务 2.4：验证日志系统完整性
- [x] 2.4.1 检查 `DataFlowLogger` 是否已挂载到 `window.DataFlowLogger` - 是
- [x] 2.4.2 确认日志默认关闭（`LOG_CONFIG.* = false`）
- [ ] 2.4.3 测试 `DataFlowLogger.enable('GroupModel')` 是否正常工作（待验证）

## 阶段三：文档与长效机制

### 任务 3.1：创建 style-control-map.md
- [ ] 3.1.1 创建 `docs/research/style-control-map.md`
- [ ] 3.1.2 记录容器标题样式控制位置和优先级
- [ ] 3.1.3 记录拖尾线样式控制位置和优先级
- [ ] 3.1.4 记录其他重要样式控制点

### 任务 3.2：更新样式代码优化待办记录
- [ ] 3.2.1 打开 `docs/research/样式代码优化待办记录.md`
- [ ] 3.2.2 更新已完成项的复选框状态
- [ ] 3.2.3 添加本次重构的经验教训

### 任务 3.3：更新 groupModel-refactor-plan.md
- [ ] 3.3.1 打开 `docs/research/groupModel-refactor-plan.md`
- [ ] 3.3.2 更新 Phase 1-4 的实施状态
- [ ] 3.3.3 添加遗留问题和后续优化建议

---

## 任务依赖关系

```
阶段一
├── 1.1 (已完成)
├── 1.2 (已完成)
├── 1.3 (已完成)
├── 1.4 (已完成)
└── 1.5 (部分完成，待用户验证)

阶段二
├── 2.1 (已完成)
├── 2.2 (部分完成)
└── 2.3 (待完成)
    └── 2.4 (待完成)

阶段三
├── 3.1 (待完成)
├── 3.2 (待完成)
└── 3.3 (待完成)
```

## 并行执行建议

以下任务可以并行执行：
- 2.2.4 和 3.1 和 3.2（各自独立）

## 遗留问题

1. **console.log 清理**：`useDiagramData.js` 中仍有 9 处 console.log
2. **单元测试**：缺少循环引用和深度限制的测试用例
3. **文档**：style-control-map.md 和待办记录文档待更新
