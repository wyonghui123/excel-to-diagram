# Tasks

## Task 1: 扩展 archDataStore 状态
- [x] SubTask 1.1: 添加 activeDimension 状态（默认值 'business_object'）
- [x] SubTask 1.2: 添加 selectedRows 状态用于存储表格选中行

## Task 2: 添加维度子 Tab 组件
- [x] SubTask 2.1: 在 index.vue 中定义 dimensionTabs 配置数组
- [x] SubTask 2.2: 添加 adm-sub-tabs 区域，仅在 activeTab === 'hierarchy' 时显示
- [x] SubTask 2.3: 实现 switchDimension 方法切换维度 Tab
- [x] SubTask 2.4: 添加子 Tab 样式（.adm-sub-tabs, .adm-sub-tab, .adm-sub-tab-active）

## Task 3: 实现操作栏联动
- [x] SubTask 3.1: 在 index.vue 中定义 toolbarConfig 配置对象
- [x] SubTask 3.2: 添加 adm-toolbar 区域，包含新建、删除、搜索按钮
- [x] SubTask 3.3: 实现 currentTypeLabel 计算属性，根据当前维度显示对应标签
- [x] SubTask 3.4: 实现 handleCreate 方法，调用 DynamicView 的创建功能
- [x] SubTask 3.5: 实现 handleBatchDelete 方法，调用 DynamicView 的批量删除功能
- [x] SubTask 3.6: 实现 handleSelectionChange 方法，更新 selectedRows 状态
- [x] SubTask 3.7: 添加操作栏样式

## Task 4: 实现左侧树与右侧 Tab 联动
- [x] SubTask 4.1: 定义 nodeTypeToDimension 映射对象
- [x] SubTask 4.2: 修改 handleNodeSelect 方法，根据节点类型自动切换维度 Tab
- [x] SubTask 4.3: 实现 currentFilterParams 计算属性，根据选中节点生成过滤参数
- [x] SubTask 4.4: 确保 activeTab 自动切换为 'hierarchy'

## Task 5: 调整 DynamicView 组件
- [x] SubTask 5.1: 移除 DynamicView 内部的 view-header 区域（操作栏已移至 index.vue）
- [x] SubTask 5.2: 添加 selection-change 事件暴露选中行变化
- [x] SubTask 5.3: 确保通过 ref 暴露 create/delete 方法供父组件调用

## Task 6: 样式优化与测试
- [x] SubTask 6.1: 确保子 Tab 与主 Tab 视觉层级区分
- [x] SubTask 6.2: 确保操作栏按钮样式与项目规范一致
- [x] SubTask 6.3: 测试维度切换功能
- [x] SubTask 6.4: 测试左侧树节点点击联动
- [x] SubTask 6.5: 测试 CRUD 功能完整性

---

# Task Dependencies

- Task 2 依赖 Task 1（需要 activeDimension 状态）
- Task 3 依赖 Task 1（需要 selectedRows 状态）
- Task 4 依赖 Task 2（需要维度 Tab 切换功能）
- Task 5 可与 Task 2-4 并行
- Task 6 依赖所有前置任务完成
