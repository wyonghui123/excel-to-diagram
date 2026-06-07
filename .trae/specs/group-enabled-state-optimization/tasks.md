# 分组启用状态优化 - 实施任务

## 任务概述

添加"优化分组状态"按钮，让用户可以手动优化大分组的启用状态，改善布局均衡性。

**核心目标**：
1. 添加"优化分组状态"按钮
2. 实现分组启用状态优化逻辑
3. 添加阈值配置项
4. 验证效果

---

## 阶段1：核心逻辑实现

### 任务 1.1：实现叶子节点计数函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 创建 `countLeafNodesInGroup(group)` 函数
- 递归计算分组内的所有叶子节点数量
- 返回叶子节点总数

**验收**：
- [x] 函数实现完成
- [x] 叶子节点计数正确

### 任务 1.2：实现终止条件判断函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 创建 `isLeafGroup(group)` 函数：判断分组是否直接包含叶子节点
- 创建 `hasSpecialGroup(group)` 函数：判断是否包含有/无外部关系分组
- 创建 `isInCenterScope(group, centerScopeCodes)` 函数：判断分组是否属于中心范围

**验收**：
- [x] 函数实现完成
- [x] 判断逻辑正确

### 任务 1.3：实现分组启用状态优化函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 创建 `optimizeGroupEnabledState()` 函数
- 实现递归处理逻辑
- 中心范围：从领域开始递归向下 disable，直到分组包含大于1个子分组或直接包含叶子节点
- 非中心范围：当子孙叶子节点数超过阈值时 disable
- 调用 `emitUpdate()` 触发更新

**验收**：
- [x] 函数实现完成
- [x] 递归逻辑正确
- [x] 中心范围处理正确
- [x] 更新触发正确

---

## 阶段2：UI 按钮实现

### 任务 2.1：添加优化分组状态按钮

**文件**：`src/views/AADiagramApp/components/LayoutSelector.vue`

**内容**：
- 在"层内排序"按钮旁边添加"优化分组状态"按钮
- 绑定点击事件到 `handleOptimizeGroupState`
- 添加按钮样式

**验收**：
- [x] 按钮显示正确
- [x] 点击事件绑定正确

### 任务 2.2：实现按钮状态控制

**文件**：`src/views/AADiagramApp/components/LayoutSelector.vue`

**内容**：
- "优化分组状态"按钮：有分组时可用
- 使用 computed 属性控制禁用状态

**验收**：
- [x] 状态控制正确
- [x] 无分组时按钮禁用

---

## 阶段3：集成与导出

### 任务 3.1：导出优化函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 在 `defineExpose` 中导出 `optimizeGroupEnabledState`
- 确保 LayoutSelector 可以调用

**验收**：
- [x] 函数正确导出
- [x] LayoutSelector 可以调用

### 任务 3.2：连接 LayoutSelector 和 LayoutControlPanel

**文件**：`src/views/AADiagramApp/components/LayoutSelector.vue`

**内容**：
- 通过 `layoutControlPanelRef` 调用优化函数
- 添加错误处理

**验收**：
- [x] 调用链正确
- [x] 错误处理完善

---

## 阶段4：配置项实现

### 任务 4.1：添加阈值配置项

**文件**：`src/views/AADiagramApp/components/steps/StepConfig.vue`

**内容**：
- 在高级配置区域添加阈值输入框
- 默认值 20%
- 范围 5%-50%

**验收**：
- [ ] 配置项显示正确
- [ ] 默认值正确
- [ ] 范围限制正确

### 任务 4.2：传递配置到优化函数

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**内容**：
- 从 props 获取阈值配置
- 传递给优化函数

**验收**：
- [ ] 配置传递正确
- [ ] 阈值生效

---

## 阶段5：验证效果

### 任务 5.1：测试中心范围分组

**内容**：
- 设置中心范围
- 点击"自动分组"
- 点击"优化分组状态"
- 验证中心范围的领域分组是否被设置为 disabled

**验收**：
- [ ] 中心范围分组正确 disabled

### 任务 5.2：测试大分组优化

**内容**：
- 不设置中心范围
- 点击"自动分组"
- 点击"优化分组状态"
- 验证超过阈值的分组是否被设置为 disabled

**验收**：
- [ ] 大分组正确 disabled
- [ ] 布局更均衡

### 任务 5.3：测试终止条件

**内容**：
- 创建包含"有外部关系"分组的场景
- 点击"优化分组状态"
- 验证递归是否在正确位置停止

**验收**：
- [ ] 终止条件正确
- [ ] 有/无外部关系分组不受影响

---

## 任务依赖

- [任务 1.3] 依赖 [任务 1.1], [任务 1.2]
- [任务 2.1] 依赖 [任务 1.3]
- [任务 2.2] 依赖 [任务 2.1]
- [任务 3.1] 依赖 [任务 1.3]
- [任务 3.2] 依赖 [任务 3.1]
- [任务 4.1] 无依赖
- [任务 4.2] 依赖 [任务 4.1], [任务 1.3]
- [任务 5.1] 依赖 [任务 3.2]
- [任务 5.2] 依赖 [任务 3.2]
- [任务 5.3] 依赖 [任务 3.2]

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 递归性能问题 | 大数据量卡顿 | 添加缓存和深度限制 |
| 配置值异常 | 逻辑错误 | 添加输入验证 |
| 终止条件遗漏 | 分组状态错误 | 完善测试用例 |

---

## 预期结果

### 成功标准

1. **按钮可用**：有分组时可点击
2. **优化效果明显**：大分组被设置为 disabled
3. **布局更均衡**：子分组直接参与布局
4. **配置生效**：阈值配置正确传递
