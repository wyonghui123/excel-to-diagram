# 样式与GroupModel重构检查清单

## 阶段一：样式优化

### 1.1 useSvgStyle.js 优化
- [x] `useSvgStyle.js` 已备份
- [x] `applyContainerTitleItalic` 已改为 `validateContainerTitles`
- [x] 无 `el.style.fontStyle` 内联样式设置
- [x] 无 `el.style.fontSize` 内联样式设置
- [x] 无 `el.style.transform` 内联样式设置
- [x] `setTimeout(..., 1200)` 已移除（改用 waitForRender）

### 1.2 useTooltip.js 拖尾线修复
- [x] `tailLine.style.display = 'none'` 已删除
- [x] `endMarker.style.display = 'none'` 已删除
- [x] `svg.classList.add('hide-tails')` 已添加
- [x] CSS `.hide-tails` 规则存在

### 1.3 MutationObserver 替代 setTimeout
- [x] `waitForRender` 辅助函数已创建
- [x] 使用轮询机制替代固定延迟的 setTimeout
- [x] 样式延迟应用问题已解决

### 1.4 font-synthesis 设置
- [x] `font-synthesis: style !important` 已存在于 CSS

### 1.5 功能验证
- [x] 开发服务器启动成功 (http://localhost:3006/)
- [ ] 容器标题斜体显示正确（待用户验证）
- [ ] 拖尾线隐藏功能正常（待用户验证）
- [ ] 无控制台错误（待用户验证）

## 阶段二：GroupModel 重构收尾

### 2.1 日志集成验证
- [x] `useDiagramData.js` 导入 `DataFlowLogger`
- [x] 日志调用存在（console.log 需进一步清理）

### 2.2 旧日志清理验证
- [x] `GroupModel.js` 无遗留 console.log
- [x] `groupedLayout.js` 无遗留 console.log
- [ ] `useBusinessObjectSyntax.js` 有 1 处 console.log 需清理
- [ ] `useDiagramData.js` 有 9 处 console.log 需清理

### 2.3 单元测试
- [ ] 循环引用测试用例存在（待添加）
- [ ] 深度限制测试用例存在（待添加）
- [ ] 所有测试通过（待验证）

### 2.4 日志系统验证
- [x] `DataFlowLogger` 已挂载到 window
- [x] 日志默认关闭（已改为 false）
- [ ] `DataFlowLogger.enable()` 正常工作（待验证）

## 阶段三：文档

### 3.1 style-control-map.md
- [ ] 文件已创建
- [ ] 容器标题样式控制已记录
- [ ] 拖尾线样式控制已记录

### 3.2 样式代码优化待办记录
- [ ] 已更新完成状态
- [ ] 经验教训已添加

### 3.3 groupModel-refactor-plan.md
- [ ] Phase 1-4 状态已更新
- [ ] 遗留问题已记录

---

## 遗留问题

1. **console.log 清理**：useDiagramData.js 和 useBusinessObjectSyntax.js 中仍有 console.log
2. **单元测试**：缺少循环引用和深度限制的测试用例
3. **文档**：style-control-map.md 和待办记录文档待更新
