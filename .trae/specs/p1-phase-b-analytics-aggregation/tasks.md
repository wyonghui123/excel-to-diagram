# Tasks

## Task 1: Analytics 模型定义与解析
- [x] SubTask 1.1: `meta/core/models.py` - `SemanticAnnotation` 新增 `analytics: Dict[str, Any]` 属性
- [x] SubTask 1.2: `meta/core/yaml_loader.py` - `parse_semantics()` 新增 `analytics` 字段解析
- [x] SubTask 1.3: 验证：现有 YAML 无 analytics 时加载行为不变

## Task 2: ComputationService 聚合扩展
- [x] SubTask 2.1: `meta/services/computation_service.py` - 新增聚合计算类型：`sum_field`, `avg_field`, `max_field`, `min_field`
- [x] SubTask 2.2: `meta/services/computation_service.py` - 新增 `_aggregate_field()` 方法，执行字段级聚合
- [x] SubTask 2.3: `meta/services/computation_service.py` - 扩展 `compute_field()` 支持新聚合类型
- [x] SubTask 2.4: 验证：聚合计算正确返回 sum/avg/max/min 值

## Task 3: 聚合查询 API
- [x] SubTask 3.1: `meta/api/query_api.py` - 新增 `POST /api/v1/query/aggregate` 端点
- [x] SubTask 3.2: `meta/api/query_api.py` - 定义 `AggregateRequest` 和 `AggregateResult` 数据类
- [x] SubTask 3.3: `meta/api/query_api.py` - 实现聚合查询逻辑：解析请求、构建 SQL、执行查询、返回结果
- [x] SubTask 3.4: `meta/api/query_api.py` - 支持多度量、多维度、过滤条件
- [x] SubTask 3.5: 验证：聚合查询 API 返回正确结果

## Task 4: YAML Schema 标注
- [x] SubTask 4.1: 为 `business_object.yaml` 的 `relation_count` 字段添加 analytics 标注（category: measure, aggregation: count）
- [x] SubTask 4.2: 为 `domain.yaml`、`sub_domain.yaml`、`service_module.yaml` 的虚拟字段添加 analytics 标注
- [x] SubTask 4.3: 验证：标注后字段正确识别为度量/维度

## Task 5: 测试与验证
- [x] SubTask 5.1: 新增 `test_analytics_aggregation.py` - 测试 analytics 语义解析、聚合计算、聚合查询 API
- [x] SubTask 5.2: 运行现有测试套件，确保所有测试通过
- [x] SubTask 5.3: 端到端验证：聚合查询 API 返回预期结果

# Task Dependencies
- [Task 2] depends on [Task 1] (analytics 属性需要先定义)
- [Task 3] depends on [Task 2] (聚合查询依赖 ComputationService 扩展)
- [Task 4] depends on [Task 1] (YAML 标注需要 analytics 属性)
- [Task 5] depends on [Task 1, Task 2, Task 3, Task 4]
- [Task 1] 可独立开始
