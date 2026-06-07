# Checklist

## Phase 1: Sort Transformation

### 元模型扩展
- [x] SemanticAnnotation 类包含 sort_transform 属性
- [x] SemanticAnnotation 类包含 filter_transform 属性
- [x] yaml_loader.py 正确解析 sort_transform 配置
- [x] yaml_loader.py 正确解析 filter_transform 配置
- [x] 单元测试验证属性解析正确

### VirtualFieldTransformEngine
- [x] transform_sort 方法正确处理 `by` 映射转换
- [x] transform_sort 方法正确处理 `sql_expr` 表达式转换
- [x] transform_filter 方法正确处理过滤条件转换
- [x] 无转换配置时返回 None（回退到内存处理）
- [x] 单元测试覆盖所有转换场景

### QueryBuilder 集成
- [x] order_by 方法支持虚拟字段排序转换
- [ ] where 方法支持虚拟字段过滤转换（待实现）
- [x] SQL 表达式正确注入到 ORDER BY 子句
- [ ] SQL 表达式正确注入到 WHERE 子句（待实现）
- [x] 集成测试验证端到端功能

### relationship.yaml 配置
- [x] category_label 字段包含 sort_transform 配置
- [x] category_label 字段包含 filter_transform 配置
- [x] 排序功能按预期工作
- [ ] 过滤功能按预期工作（待实现）

### 测试验证
- [x] 现有排序测试全部通过
- [x] 虚拟字段排序转换测试通过
- [ ] 虚拟字段过滤转换测试通过（待实现）
- [x] 性能测试显示数据库排序优于内存排序

## Phase 2: Analytics Query Engine

### AnalyticsQueryBuilder 基础
- [x] dimension 方法正确添加维度字段
- [x] measure 方法正确添加度量字段
- [x] filter 方法正确添加过滤条件
- [x] build 方法生成正确的 SQL 查询

### 虚拟字段维度支持
- [x] 正确解析虚拟字段的 sql_expr 表达式
- [x] 生成包含 CASE WHEN 的 GROUP BY 子句
- [x] 维度别名正确处理

### 聚合函数支持
- [x] COUNT 聚合正确实现
- [x] SUM 聚合正确实现
- [x] AVG 聚合正确实现
- [x] MIN/MAX 聚合正确实现

### Analytics API
- [x] /analytics 端点正确响应
- [x] 支持动态维度配置
- [x] 支持动态度量配置
- [x] 返回正确的聚合结果

### 测试验证
- [x] AnalyticsQueryBuilder 单元测试通过
- [x] 虚拟字段维度测试通过
- [x] 聚合函数测试通过
- [x] 端到端 API 测试通过

## SQLite 兼容性

- [x] CASE WHEN 表达式在 SQLite 中正确执行
- [x] ORDER BY 表达式在 SQLite 中正确执行
- [x] GROUP BY 表达式在 SQLite 中正确执行
- [ ] 所有必要索引已创建
