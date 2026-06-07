# Phase B: Analytics 聚合注解 Spec

## Why

当前元模型缺少对分析场景的语义标注能力。业务对象字段没有声明其分析角色（度量/维度），导致：(1) 前端无法自动识别哪些字段可聚合、哪些字段用于分组；(2) 后端需要手动编写聚合查询逻辑，无法根据元模型自动生成；(3) 与 SAP CDS 的 `@Analytics.dataCategory` + `@DefaultAggregation` 注解体系不对齐，影响从 SAP 系统迁移的用户。Phase B 将为字段语义增加 `analytics` 标注，支持声明式定义度量/维度，并扩展聚合查询 API。

## What Changes

- **Analytics 语义标注**：`SemanticAnnotation` 新增 `analytics` 属性，包含 `aggregation`（SUM/MAX/MIN/AVG/COUNT）和 `category`（measure/dimension）
- **聚合查询 API**：`query_api.py` 新增 `/api/v1/query/aggregate` 端点，支持按维度分组、对度量字段聚合
- **ComputationService 扩展**：新增聚合计算类型（sum_field, avg_field, max_field, min_field），复用 `DerivationExecutor._execute_aggregation()` 的聚合逻辑
- **UI 列表增强**：支持在 `ui_view_config.list.columns` 中声明聚合列，自动调用聚合计算

## Impact

- Affected specs: p1-phase-a-aspect-pseudo-variables（analytics 可通过 Aspect 打包）
- Affected code:
  - `meta/core/models.py` - SemanticAnnotation 新增 analytics 属性
  - `meta/core/yaml_loader.py` - parse_semantics() 解析 analytics 配置
  - `meta/services/computation_service.py` - 扩展聚合计算类型
  - `meta/api/query_api.py` - 新增聚合查询端点
  - `meta/schemas/*.yaml` - 为度量字段添加 analytics 标注

## ADDED Requirements

### Requirement: Analytics 语义标注

系统 SHALL 支持在字段 semantics 中声明 `analytics` 配置，标记字段的分析角色（度量/维度）和聚合方式。

#### 现有实现分析

| 组件 | 现状 | 影响 |
|------|------|------|
| `SemanticAnnotation` | 无 analytics 属性 | 新增 `analytics: Dict` 可选属性 |
| `ComputationService` | 已有 `count_relations` | 扩展支持字段聚合（sum/avg/max/min） |
| `DerivationExecutor._execute_aggregation()` | 已支持 SUM/COUNT/AVG/MAX/MIN | 复用，通过 API 暴露 |
| `UIListViewColumn` | 已有 `computed: true` + `computation` | 可复用，扩展聚合类型 |

#### Scenario: 声明度量字段
- **WHEN** 用户在 YAML 中定义字段的 `semantics.analytics.category: measure` 和 `semantics.analytics.aggregation: sum`
- **THEN** 该字段被识别为可聚合的度量字段，聚合方式为求和

#### Scenario: 声明维度字段
- **WHEN** 用户在 YAML 中定义字段的 `semantics.analytics.category: dimension`
- **THEN** 该字段被识别为分组维度，可用于聚合查询的 GROUP BY

#### Scenario: 度量字段带聚合方式
- **WHEN** 字段配置 `analytics.aggregation: avg`
- **THEN** 聚合查询时对该字段使用 AVG 函数

#### Scenario: 无 analytics 配置的字段
- **WHEN** 字段无 analytics 配置
- **THEN** 该字段不参与自动聚合分析，行为与修改前一致

### Requirement: 聚合查询 API

系统 SHALL 提供聚合查询 API，支持按维度分组、对度量字段聚合。

#### Scenario: 基本聚合查询
- **WHEN** 用户调用 `POST /api/v1/query/aggregate`，请求体包含 `object_type`, `measures`, `dimensions`
- **THEN** 返回按维度分组的聚合结果

#### Scenario: 聚合查询请求格式
```json
{
  "object_type": "business_object",
  "measures": [
    {"field": "relation_count", "aggregation": "sum"}
  ],
  "dimensions": ["domain_name"],
  "filters": [
    {"field": "version_id", "operator": "eq", "value": 1}
  ]
}
```

#### Scenario: 聚合查询响应格式
```json
{
  "success": true,
  "data": [
    {"domain_name": "销售域", "relation_count_sum": 42},
    {"domain_name": "采购域", "relation_count_sum": 28}
  ],
  "total": 2
}
```

#### Scenario: 多度量聚合
- **WHEN** 请求包含多个度量字段
- **THEN** 返回结果包含每个度量的聚合值

#### Scenario: 无维度聚合
- **WHEN** 请求不包含 dimensions
- **THEN** 返回全局聚合结果（单行）

### Requirement: ComputationService 聚合扩展

系统 SHALL 扩展 ComputationService 支持字段级聚合计算。

#### Scenario: sum_field 聚合计算
- **WHEN** 字段配置 `computation.type: sum_field` 和 `computation.source_field: amount`
- **THEN** 计算指定字段的总和

#### Scenario: avg_field 聚合计算
- **WHEN** 字段配置 `computation.type: avg_field`
- **THEN** 计算指定字段的平均值

#### Scenario: max_field / min_field 聚合计算
- **WHEN** 字段配置 `computation.type: max_field` 或 `min_field`
- **THEN** 计算指定字段的最大值或最小值

### Requirement: UI 列表聚合列

系统 SHALL 支持在 UI 列表配置中声明聚合列，自动调用聚合计算。

#### Scenario: 列表列配置聚合
- **WHEN** `ui_view_config.list.columns` 中某列配置 `computed: true` 和 `computation.type: sum`
- **THEN** 列表查询时自动计算该列的聚合值

## MODIFIED Requirements

### Requirement: SemanticAnnotation 属性扩展

`SemanticAnnotation` 数据类 SHALL 新增以下可选属性：

```python
analytics: Dict[str, Any] = field(default_factory=dict)
# 包含:
#   category: str  # "measure" | "dimension"
#   aggregation: str  # "sum" | "avg" | "max" | "min" | "count"
#   measure_group: str  # 可选，度量分组名称
#   dimension_group: str  # 可选，维度分组名称
```

### Requirement: yaml_loader 解析扩展

`yaml_loader.py` SHALL 扩展 `parse_semantics()` 解析 `analytics` 配置：

```python
analytics = data.get("analytics", {})
```

### Requirement: UIListViewColumn 扩展

`UIListViewColumn` 数据类 SHALL 支持聚合配置：

```python
# 已有 computation 字段扩展支持:
computation: Dict[str, Any] = field(default_factory=dict)
# 新增支持的类型: sum_field, avg_field, max_field, min_field
```

## REMOVED Requirements

无移除的需求。所有现有功能保持向后兼容。
