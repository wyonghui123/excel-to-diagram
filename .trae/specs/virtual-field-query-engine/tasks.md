# Tasks

## Phase 1: Sort Transformation

- [x] Task 1: 扩展元模型支持 sort_transform 和 filter_transform
  - [ ] SubTask 1.1: 在 `SemanticAnnotation` 类中添加 `sort_transform` 属性
  - [ ] SubTask 1.2: 在 `SemanticAnnotation` 类中添加 `filter_transform` 属性
  - [ ] SubTask 1.3: 在 `yaml_loader.py` 的 `parse_semantics` 函数中解析新属性
  - [ ] SubTask 1.4: 编写单元测试验证属性解析

- [x] Task 2: 实现 VirtualFieldTransformEngine
  - [ ] SubTask 2.1: 创建 `meta/core/virtual_field_transform.py` 文件
  - [ ] SubTask 2.2: 实现 `transform_sort` 方法 - 处理 `by` 映射转换
  - [ ] SubTask 2.3: 实现 `transform_sort` 方法 - 处理 `sql_expr` 表达式转换
  - [ ] SubTask 2.4: 实现 `transform_filter` 方法 - 处理过滤条件转换
  - [ ] SubTask 2.5: 编写单元测试验证转换逻辑

- [x] Task 3: 集成到 QueryBuilder
  - [ ] SubTask 3.1: 在 `QueryBuilder` 中注入 `VirtualFieldTransformEngine`
  - [ ] SubTask 3.2: 修改 `order_by` 方法支持虚拟字段排序转换
  - [ ] SubTask 3.3: 修改 `where` 方法支持虚拟字段过滤转换
  - [ ] SubTask 3.4: 支持 SQL 表达式注入到 ORDER BY 子句
  - [ ] SubTask 3.5: 编写集成测试

- [x] Task 4: 更新 relationship.yaml 示例
  - [ ] SubTask 4.1: 为 `category_label` 添加 `sort_transform` 配置
  - [ ] SubTask 4.2: 为 `category_label` 添加 `filter_transform` 配置
  - [ ] SubTask 4.3: 验证排序功能正常工作

- [x] Task 5: 验证与测试
  - [ ] SubTask 5.1: 运行现有排序测试确保兼容性
  - [ ] SubTask 5.2: 添加虚拟字段排序转换测试
  - [ ] SubTask 5.3: 添加虚拟字段过滤转换测试
  - [ ] SubTask 5.4: 性能测试对比内存排序 vs 数据库排序

## Phase 2: Analytics Query Engine

- [x] Task 6: 设计 AnalyticsQueryBuilder
  - [ ] SubTask 6.1: 创建 `meta/core/analytics_query_builder.py` 文件
  - [ ] SubTask 6.2: 实现 `dimension` 方法 - 添加维度字段
  - [ ] SubTask 6.3: 实现 `measure` 方法 - 添加度量字段
  - [ ] SubTask 6.4: 实现 `filter` 方法 - 添加过滤条件
  - [ ] SubTask 6.5: 实现 `build` 方法 - 生成 SQL 查询

- [x] Task 7: 支持虚拟字段作为维度
- [x] Task 8: 实现聚合函数支持
- [x] Task 9: 创建 Analytics API
  - [ ] SubTask 9.1: 在 `manage_api.py` 添加 `/analytics` 端点
  - [ ] SubTask 9.2: 支持动态维度和度量配置
  - [ ] SubTask 9.3: 返回聚合结果

- [x] Task 10: 验证与测试
  - [ ] SubTask 10.1: 编写 AnalyticsQueryBuilder 单元测试
  - [ ] SubTask 10.2: 编写虚拟字段维度测试
  - [ ] SubTask 10.3: 编写聚合函数测试
  - [ ] SubTask 10.4: 端到端 API 测试

---

# Task Dependencies

- [Task 2] depends on [Task 1] - 转换引擎依赖元模型扩展
- [Task 3] depends on [Task 2] - QueryBuilder 集成依赖转换引擎
- [Task 4] depends on [Task 1] - YAML 更新依赖元模型扩展
- [Task 5] depends on [Task 3, Task 4] - 验证依赖所有实现完成
- [Task 7] depends on [Task 6] - 虚拟字段维度依赖基础构建器
- [Task 8] depends on [Task 6] - 聚合函数依赖基础构建器
- [Task 9] depends on [Task 6, Task 7, Task 8] - API 依赖构建器完成
- [Task 10] depends on [Task 9] - 测试依赖 API 完成

---

# Parallelizable Work

以下任务可以并行执行：
- Task 1 和 Task 6 可以并行（Phase 1 和 Phase 2 基础工作）
- Task 4 可以与 Task 2 并行（YAML 配置与引擎实现）
- SubTask 8.1-8.4 可以并行（不同聚合函数实现）
