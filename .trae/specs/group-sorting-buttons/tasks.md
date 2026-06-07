# 分组排序按钮功能 - 实施任务

## 任务概述

添加两个排序按钮，让用户可以灵活控制分组排序，优化布局均匀性。

**核心目标**：
1. 添加"整体排序"按钮
2. 添加"层内排序"按钮
3. 实现排序逻辑
4. 按钮状态控制
5. 验证效果

---

## 阶段1：排序逻辑实现

### 任务 1.1：实现分组节点计数函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 创建 `countNodesInGroup(group)` 函数
- 递归计算分组内的所有节点数量
- 返回节点总数

**验收**：
- [x] 函数实现完成
- [x] 节点计数正确

### 任务 1.2：实现分组连线密度计算函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 创建 `calculateGroupConnectionDensity(group, links)` 函数
- 计算分组与其他分组的连线数量
- 返回连线密度

**验收**：
- [x] 函数实现完成
- [x] 连线密度计算正确

### 任务 1.3：实现整体排序函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 创建 `handleOverallSort()` 函数
- 对所有顶层分组按综合策略排序
- 更新 `localConfig.value.groups`
- 调用 `emitUpdate()` 触发更新

**验收**：
- [x] 函数实现完成
- [x] 排序逻辑正确
- [x] 更新触发正确

### 任务 1.4：实现层内排序函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 创建 `handleInLayerSort()` 函数
- 找到所有虚拟层（`_isVirtualLayer`）
- 对每个虚拟层的 children 排序
- 调用 `emitUpdate()` 触发更新

**验收**：
- [x] 函数实现完成
- [x] 虚拟层识别正确
- [x] 层内排序正确

---

## 阶段2：UI 按钮实现

### 任务 2.1：添加整体排序按钮

**文件**：`src/views/AADiagramApp/components/LayoutSelector.vue`

**内容**：
- 在"虚拟分层"按钮旁边添加"整体排序"按钮
- 绑定点击事件到 `handleOverallSort`
- 添加按钮样式

**验收**：
- [x] 按钮显示正确
- [x] 点击事件绑定正确

### 任务 2.2：添加层内排序按钮

**文件**：`src/views/AADiagramApp/components/LayoutSelector.vue`

**内容**：
- 在"整体排序"按钮旁边添加"层内排序"按钮
- 绑定点击事件到 `handleInLayerSort`
- 添加按钮样式

**验收**：
- [x] 按钮显示正确
- [x] 点击事件绑定正确

### 任务 2.3：实现按钮状态控制

**文件**：`src/views/AADiagramApp/components/LayoutSelector.vue`

**内容**：
- "整体排序"按钮：有分组时可用
- "层内排序"按钮：有虚拟分层时可用
- 使用 computed 属性控制禁用状态

**验收**：
- [x] 状态控制正确
- [x] 无分组时整体排序禁用
- [x] 无虚拟分层时层内排序禁用

---

## 阶段3：集成与导出

### 任务 3.1：导出排序函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 在 `defineExpose` 中导出 `handleOverallSort` 和 `handleInLayerSort`
- 确保 LayoutSelector 可以调用这些函数

**验收**：
- [x] 函数正确导出
- [x] LayoutSelector 可以调用

### 任务 3.2：连接 LayoutSelector 和 LayoutControlPanel

**文件**：`src/views/AADiagramApp/components/LayoutSelector.vue`

**内容**：
- 通过 `layoutControlPanelRef` 调用排序函数
- 添加错误处理

**验收**：
- [x] 调用链正确
- [x] 错误处理完善

---

## 阶段4：验证效果

### 任务 4.1：测试整体排序

**内容**：
- 点击"基于领域自动分组"
- 点击"整体排序"
- 验证分组顺序是否优化
- 验证布局是否更均匀

**验收**：
- [x] 整体排序生效
- [x] 布局有所改善

### 任务 4.2：测试层内排序

**内容**：
- 点击"基于领域自动分组"
- 点击"虚拟分层"
- 点击"层内排序"
- 验证每个虚拟层内部的分组顺序是否优化

**验收**：
- [x] 层内排序生效
- [x] 层内布局更均匀

### 任务 4.3：测试组合场景

**内容**：
- 测试场景 A：自动分组 → 整体排序
- 测试场景 B：自动分组 → 虚拟分层 → 层内排序
- 测试场景 C：自动分组 → 整体排序 → 虚拟分层 → 层内排序

**验收**：
- [x] 所有场景正常工作
- [x] 排序效果符合预期

---

## 任务依赖

- [任务 1.3] 依赖 [任务 1.1], [任务 1.2]
- [任务 1.4] 依赖 [任务 1.1], [任务 1.2]
- [任务 2.1] 依赖 [任务 1.3]
- [任务 2.2] 依赖 [任务 1.4]
- [任务 2.3] 依赖 [任务 2.1], [任务 2.2]
- [任务 3.1] 依赖 [任务 1.3], [任务 1.4]
- [任务 3.2] 依赖 [任务 3.1]
- [任务 4.1] 依赖 [任务 3.2]
- [任务 4.2] 依赖 [任务 3.2]
- [任务 4.3] 依赖 [任务 4.1], [任务 4.2]

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 排序逻辑错误 | 布局混乱 | 添加日志调试 |
| 按钮状态控制错误 | 用户体验差 | 添加 computed 属性 |
| 函数调用链错误 | 功能失效 | 添加错误处理 |

---

## 预期结果

### 成功标准

1. **整体排序按钮可用**：有分组时可点击
2. **层内排序按钮可用**：有虚拟分层时可点击
3. **排序效果明显**：布局更均匀
4. **用户体验良好**：按钮状态清晰
