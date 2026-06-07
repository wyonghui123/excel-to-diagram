# Tasks

- [x] Task 1: 增加关系统计数据到 useDiagramData.js
  - [x] Task 1.1: 在 stats 计算属性中增加 objectRelations 和 serviceModuleRelations 统计
  - [x] Task 1.2: 在 displayStats 中增加关系统计项
  - [x] Task 1.3: 在 selectedStats 中增加关系统计初始值

- [x] Task 2: 在 DataPreview 组件中增加"基于业务关系过滤"按钮
  - [x] Task 2.1: 在业务对象关系列表上方增加过滤按钮
  - [x] Task 2.2: 实现过滤逻辑：提取关系中的源/目标业务对象编码
  - [x] Task 2.3: 通过 emit 传递过滤后的业务对象编码列表到父组件
  - [x] Task 2.4: 更新范围选择（selectedScope）

- [x] Task 3: 更新 StepScope 组件传递过滤事件
  - [x] Task 3.1: 接收 DataPreview 发出的过滤事件
  - [x] Task 3.2: 向上传递到 index.vue

- [x] Task 4: 更新 useDiagramData 处理过滤结果
  - [x] Task 4.1: 接收过滤后的业务对象编码列表
  - [x] Task 4.2: 更新 selectedScope 为过滤后的范围

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 4] depends on [Task 2], [Task 3]