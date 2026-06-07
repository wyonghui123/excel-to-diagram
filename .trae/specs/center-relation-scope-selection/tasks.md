# Tasks

## Task 1: 创建关系分类服务
- [x] SubTask 1.1: 创建 relationClassifier.js 服务文件
- [x] SubTask 1.2: 实现关系分类算法（classifyRelation）
- [x] SubTask 1.3: 实现关系分类树构建算法（buildRelationCategoryTree）
- [ ] SubTask 1.4: 添加单元测试

## Task 2: 创建中心范围选择器组件
- [x] SubTask 2.1: 创建 CenterScopeSelector.vue 组件
- [x] SubTask 2.2: 复用现有树形选择逻辑
- [x] SubTask 2.3: 添加范围预设保存功能
- [x] SubTask 2.4: 添加样式和交互

## Task 3: 创建关系分类树组件
- [x] SubTask 3.1: 创建 RelationCategoryTree.vue 组件
- [x] SubTask 3.2: 创建 RelationCategoryNode.vue 组件
- [x] SubTask 3.3: 实现逐级展开功能
- [x] SubTask 3.4: 实现多选功能
- [x] SubTask 3.5: 实现关系数量统计显示
- [x] SubTask 3.6: 实现选中优先排序

## Task 4: 修改 StepScope 组件
- [x] SubTask 4.1: 添加二级选择模式的布局
- [x] SubTask 4.2: 集成 CenterScopeSelector 组件
- [x] SubTask 4.3: 集成 RelationCategoryTree 组件
- [x] SubTask 4.4: 添加步骤切换逻辑

## Task 5: 修改 DataPreview 组件
- [x] SubTask 5.1: 添加关系范围选择Tab
- [x] SubTask 5.2: 联动业务对象关系表格
- [x] SubTask 5.3: 实现过滤展示逻辑

## Task 6: 修改 useDiagramData composable
- [x] SubTask 6.1: 添加 centerScope 状态
- [x] SubTask 6.2: 添加 relationScope 状态
- [x] SubTask 6.3: 添加 relationCategoryTree 计算属性
- [x] SubTask 6.4: 添加 filteredRelations 计算属性
- [x] SubTask 6.5: 添加中心范围预设管理

## Task 7: 集成测试与优化
- [x] SubTask 7.1: 端到端测试二级选择流程
- [ ] SubTask 7.2: 性能测试和优化
- [ ] SubTask 7.3: 用户体验优化

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 2, Task 3]
- [Task 5] depends on [Task 4]
- [Task 6] depends on [Task 1]
- [Task 7] depends on [Task 4, Task 5, Task 6]
