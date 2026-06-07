# Tasks

## Phase 1: 元模型配置完善

- [x] Task 1: 完善 relationship.yaml 元模型配置
  - [x] SubTask 1.1: 添加完整的 ui_view_config（list/detail/form/filter）
  - [x] SubTask 1.2: 添加虚拟字段 source_bo_name, target_bo_name, category_label
  - [x] SubTask 1.3: 配置筛选器定义（业务对象/分类维度/关系类型）

- [x] Task 2: 扩展 business_object.yaml 元模型配置
  - [x] SubTask 2.1: 在 detail.facets 中添加 relation_list 分面
  - [x] SubTask 2.2: 配置关联关系展示参数

## Phase 2: 后端 API 扩展

- [x] Task 3: 扩展视图配置 API
  - [x] SubTask 3.1: 在 meta_api.py 中添加 filter-config 端点
  - [x] SubTask 3.2: 扩展 detail-view 端点支持 relation_list 分面类型
  - [x] SubTask 3.3: 返回筛选器配置数据

- [x] Task 4: 实现关系查询 API
  - [x] SubTask 4.1: 在 manage_api.py 中添加 GET /api/v1/relationships 端点
  - [x] SubTask 4.2: 实现多条件筛选逻辑（业务对象/分类维度/关系类型）
  - [x] SubTask 4.3: 实现关系统计计算（by_category, by_type）
  - [x] SubTask 4.4: 添加 GET /api/v1/business_object/{id}/relations 端点

- [x] Task 5: 实现关系分类计算
  - [x] SubTask 5.1: 在 manage_api.py 中实现分类计算函数
  - [x] SubTask 5.2: 实现分类计算逻辑（跨领域/同领域/同模块）
  - [x] SubTask 5.3: 在关系查询时自动计算分类

## Phase 3: 前端框架调整

- [x] Task 6: 实现主框架 Tab 切换
  - [x] SubTask 6.1: 在 index.vue 中添加顶部 Tab（层级数据/业务关系）
  - [x] SubTask 6.2: 实现 Tab 切换状态管理
  - [x] SubTask 6.3: 根据Tab切换左侧导航内容

- [x] Task 7: 实现筛选器组件
  - [x] SubTask 7.1: 创建 DynamicFilter.vue 组件
  - [x] SubTask 7.2: 实现 multi_select 类型筛选器
  - [x] SubTask 7.3: 实现 checkbox_group 类型筛选器
  - [x] SubTask 7.4: 实现筛选器联动逻辑
  - [x] SubTask 7.5: 创建 useFilter.js composable（集成在组件内）

## Phase 4: 业务对象详情增强

- [x] Task 8: 实现关联关系展示组件
  - [x] SubTask 8.1: 创建 RelationFacet.vue 组件
  - [x] SubTask 8.2: 实现作为源/目标的关系分列展示
  - [x] SubTask 8.3: 实现关系数量统计显示
  - [x] SubTask 8.4: 实现"查看全部"跳转功能

- [x] Task 9: 集成关联关系到 DynamicDetail
  - [x] SubTask 9.1: 在 DynamicDetail.vue 中支持 relation_list 分面类型
  - [x] SubTask 9.2: 加载业务对象关联关系数据
  - [x] SubTask 9.3: 渲染 RelationFacet 组件

## Phase 5: 业务关系管理页面

- [x] Task 10: 实现业务关系列表视图
  - [x] SubTask 10.1: 复用 DynamicView 组件展示关系列表
  - [x] SubTask 10.2: 集成筛选器组件
  - [x] SubTask 10.3: 实现关系编辑/新建表单（复用 DynamicForm）

## Phase 6: 关系数量统计列

- [x] Task 11: 扩展层级对象元模型配置
  - [x] SubTask 11.1: 在 domain.yaml 的 list.columns 中添加 relation_count 列
  - [x] SubTask 11.2: 在 sub_domain.yaml 的 list.columns 中添加 relation_count 列
  - [x] SubTask 11.3: 在 service_module.yaml 的 list.columns 中添加 relation_count 列
  - [x] SubTask 11.4: 在 business_object.yaml 的 list.columns 中添加 relation_count 列

- [x] Task 12: 实现统计规则计算服务
  - [x] SubTask 12.1: 创建 computation_service.py 统计规则计算服务
  - [x] SubTask 12.2: 实现 count_relations 统计规则
  - [x] SubTask 12.3: 支持 descendants 和 self 两种 scope
  - [x] SubTask 12.4: 在列表查询时自动计算 computed 字段

- [x] Task 13: 前端统计列展示
  - [x] SubTask 13.1: 在 DynamicTable.vue 中支持 computed 列渲染
  - [x] SubTask 13.2: 实现关系数量点击跳转功能
  - [x] SubTask 13.3: 添加统计列样式（可点击链接）

## Phase 7: 自动化测试

- [x] Task 14: 后端单元测试
  - [x] SubTask 14.1: 测试 relation_category_service.py 分类计算逻辑
  - [x] SubTask 14.2: 测试 computation_service.py 统计规则计算
  - [x] SubTask 14.3: 测试 filter-config API 端点
  - [x] SubTask 14.4: 测试 relationships API 端点（筛选/统计）
  - [x] SubTask 14.5: 测试 business_object/{id}/relations API 端点

- [x] Task 15: 后端集成测试
  - [x] SubTask 15.1: 测试关系创建→分类计算→列表展示完整流程
  - [x] SubTask 15.2: 测试统计列计算（领域/子领域/服务模块/业务对象）
  - [x] SubTask 15.3: 测试筛选器联动（业务对象→分类维度→关系类型）

- [x] Task 16: 前端组件测试
  - [x] SubTask 16.1: 测试 DynamicFilter.vue 组件渲染和交互
  - [x] SubTask 16.2: 测试 RelationFacet.vue 组件渲染
  - [x] SubTask 16.3: 测试主框架 Tab 切换
  - [x] SubTask 16.4: 测试统计列点击跳转

# Task Dependencies

- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 5]
- [Task 6] depends on [Task 3]
- [Task 7] depends on [Task 3]
- [Task 8] depends on [Task 4]
- [Task 9] depends on [Task 8]
- [Task 10] depends on [Task 6, Task 7]
- [Task 12] depends on [Task 11]
- [Task 13] depends on [Task 12]

# Parallel Execution

以下任务可并行执行：
- Task 1 和 Task 2（元模型配置）
- Task 3 和 Task 5（后端 API）
- Task 7 和 Task 8（前端组件）
- Task 11 和 Task 1（元模型配置可并行）
- Task 12 和 Task 4（后端服务可并行）
