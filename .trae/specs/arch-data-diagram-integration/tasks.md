# Tasks

## 阶段1：后端API扩展

- [x] Task 1: 扩展现有API支持层级过滤参数
  - [x] Task 1.1: 确认现有API是否支持domain_id, sub_domain_id, service_module_id过滤参数
  - [x] Task 1.2: 如不支持，扩展business_object API支持层级过滤
  - [x] Task 1.3: 扩展relationships API支持层级过滤

## 阶段2：前端数据转换层

- [x] Task 2: 实现数据转换函数
  - [x] Task 2.1: 实现 `convertToCenterScope` 函数 - 将层级过滤条件转换为业务对象编码列表
  - [x] Task 2.2: 实现 `buildPreviewDataFromArchData` 函数 - 构建完整的previewData
  - [x] Task 2.3: 实现 `convertToRelationNodeIds` 函数 - 将关系类型映射为关系节点ID
  - [x] Task 2.4: 实现 `buildDomainProductsHierarchy` 函数 - 构建领域-子领域-服务模块层级结构

- [x] Task 3: 扩展useDiagramData composable
  - [x] Task 3.1: 新增 `initFromArchData` 方法 - 从架构管理数据初始化AA图
  - [x] Task 3.2: 新增状态标记 `isInitializedFromArchData`
  - [x] Task 3.3: 在初始化时计算centerScopeMarkers
  - [x] Task 3.4: 在初始化时构建relationCategoryTree

## 阶段3：导航控制

- [x] Task 4: 扩展useDiagramSteps composable
  - [x] Task 4.1: 新增 `initFromArchData` 状态标记
  - [x] Task 4.2: 扩展 `canGoToStep` 方法 - 架构管理入口时禁用步骤0-2
  - [x] Task 4.3: 扩展 `handlePrev` 方法 - 步骤3时返回架构管理
  - [x] Task 4.4: 新增 `initFromArchDataManager` 初始化方法

- [x] Task 5: 修改StepNavigator组件
  - [x] Task 5.1: 添加禁用步骤的样式显示（灰色勾选）
  - [x] Task 5.2: 确保禁用步骤点击无效

## 阶段4：架构管理页面集成

- [x] Task 6: 架构数据管理页面添加"展示图表"按钮
  - [x] Task 6.1: 添加按钮到页面（放在"导出"按钮旁边）
  - [x] Task 6.2: 实现按钮启用条件逻辑（已选择版本和范围）
  - [x] Task 6.3: 实现点击处理逻辑 - 数据转换和跳转

- [x] Task 7: 实现返回架构管理时的状态恢复
  - [x] Task 7.1: 通过路由state或全局状态传递选择状态
  - [x] Task 7.2: 架构管理页面接收并恢复选择状态

## 阶段5：测试验证

- [x] Task 8: 单元测试
  - [x] Task 8.1: 测试 `convertToCenterScope` 函数
  - [x] Task 8.2: 测试 `buildPreviewDataFromArchData` 函数
  - [x] Task 8.3: 测试 `convertToRelationNodeIds` 函数
  - [x] Task 8.4: 测试导航控制逻辑

- [x] Task 9: E2E测试
  - [x] Task 9.1: 测试从架构管理跳转到AA图
  - [x] Task 9.2: 测试步骤导航禁用功能
  - [x] Task 9.3: 测试返回架构管理功能
  - [x] Task 9.4: 测试Excel导入入口不受影响

---

# Task Dependencies

- [Task 2] 依赖 [Task 1] - 数据转换函数需要API支持
- [Task 3] 依赖 [Task 2] - useDiagramData扩展依赖转换函数
- [Task 4] 依赖 [Task 3] - 导航控制需要初始化方法
- [Task 5] 依赖 [Task 4] - StepNavigator需要状态标记
- [Task 6] 依赖 [Task 3, Task 4] - 按钮点击需要初始化逻辑
- [Task 7] 依赖 [Task 6] - 状态恢复依赖跳转逻辑
- [Task 8] 依赖 [Task 2, Task 3, Task 4] - 单元测试依赖实现
- [Task 9] 依赖 [Task 6, Task 7] - E2E测试依赖完整流程

---

# Parallelizable Work

以下任务可以并行执行：
- [Task 1] 和 [Task 4] 可以并行 - API扩展和导航控制无依赖
- [Task 5] 和 [Task 6] 可以并行 - StepNavigator和架构管理页面修改无依赖
- [Task 8] 和 [Task 9] 可以并行 - 单元测试和E2E测试可以同时编写
