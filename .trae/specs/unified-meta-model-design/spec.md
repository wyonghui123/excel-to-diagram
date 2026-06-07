# 统一元模型设计 Spec

## Why

现有元模型中对象类型概念分散（`persistent`、`is_view`、`view_definition`），缺乏统一的对象类型分类；字段存储策略与对象类型的关系不明确；规则与不同对象类型的约束关系未定义；视图（VIEW）、聚合（AGGREGATE）、复合（COMPOSITE）概念重复，可以统一。

### 架构参考分析

#### Palantir Foundry Ontology 架构

Palantir 的核心概念：
- **Object Type**: 核心实体，对应数据集，有主键、属性、链接
- **Link Type**: 对象间的关系定义
- **Function**: 跨对象的计算函数，支持复杂业务逻辑
- **Action Type**: 对对象的操作定义
- **Object Set**: 对象集合，支持过滤、聚合

关键设计思想：
1. Object 是一等公民，所有数据建模围绕 Object 展开
2. Function 支持跨对象计算，可被规则引用
3. 对象间通过 Link 建立关系，支持双向导航

#### SAP HANA CDS View 架构

SAP CDS 的核心概念：
- **Entity**: 物理存储的实体，对应数据库表
- **View**: 基于 Entity 或其他 View 的查询定义
- **Stored/Virtual 字段**: 存储字段 vs 运行时计算字段
- **@Analytics 注解**: 定义聚合、维度等分析属性
- **Association**: 实体间的关系定义

关键设计思想：
1. Entity 和 View 是两种不同的对象类型
2. 字段级别的存储策略（stored/virtual）
3. View 可以组合多个 Entity，支持聚合和关联
4. 通过注解扩展元数据能力

#### 架构对比与设计决策

| 特性 | Palantir | SAP CDS | 本设计 |
|-----|----------|---------|-------|
| 对象类型 | Object Type | Entity/View | ENTITY/VIEW/VIRTUAL |
| 存储策略 | 隐式 | 字段级 stored/virtual | 字段级 storage/source |
| 聚合能力 | Object Set | View + @Analytics | ViewConfig |
| 跨对象计算 | Function | 计算视图 | MetaFunction |
| 关系定义 | Link Type | Association | base_objects + joins |

**统一 VIEW/AGGREGATE/COMPOSITE 的理由**：
1. 聚合（AGGREGATE）本质上是一种计算，可通过 ViewConfig.group_by + aggregates 表达
2. 组合（COMPOSITE）本质上是多表关联，可通过 ViewConfig.joins 表达
3. 单一 VIEW 类型配合 ViewConfig 可覆盖所有场景，减少概念复杂度
4. 与 SAP CDS 的 View 设计一致，支持聚合和关联的任意组合

**VIRTUAL 类型的必要性**：
1. DTO/表单对象：API 请求响应、前端表单验证
2. 计算结果承载：复杂计算的中间结果或最终结果
3. 临时数据结构：会话级、请求级的数据传递
4. 与 Palantir 的 Function 返回值、SAP 的计算视图结果对应

## What Changes

- **统一对象类型**：将对象类型简化为 3 种（ENTITY / VIEW / VIRTUAL）
- **新增 ObjectType 枚举**：明确定义对象类型
- **新增 ViewConfig 配置类**：统一聚合和关联能力
- **新增 VirtualConfig 配置类**：定义虚拟对象配置
- **扩展 MetaField**：增加 `storage` 和 `source` 属性
- **扩展 MetaRule**：增加 `metric_refs` 支持跨对象指标引用
- **新增 MetaFunction**：支持跨对象计算函数（借鉴 Palantir）
- **新增 MetricReference**：定义指标引用结构
- **向后兼容**：保留现有 `persistent`、`is_view`、`view_definition` 属性

## Impact

- Affected specs: 元模型核心定义、规则系统、Schema 生成
- Affected code: 
  - `meta/core/models.py` - 核心模型定义
  - `meta/core/yaml_loader.py` - YAML 解析
  - `meta/core/schema_generator.py` - Schema 生成
  - `meta/core/rule_executor.py` - 规则执行
  - `meta/tests/` - 测试文件

## ADDED Requirements

### Requirement: 统一对象类型定义

系统 SHALL 提供统一的 `ObjectType` 枚举，定义三种对象类型：

```python
class ObjectType(Enum):
    ENTITY = "entity"       # 实体对象（对应物理表）
    VIEW = "view"           # 视图对象（SQL VIEW）
    VIRTUAL = "virtual"     # 虚拟对象（无存储）
```

#### Scenario: 实体对象定义
- **WHEN** 用户定义 `object_type: entity` 的对象
- **THEN** 系统生成对应的物理表，支持 CRUD 操作

#### Scenario: 视图对象定义
- **WHEN** 用户定义 `object_type: view` 的对象
- **THEN** 系统生成对应的 SQL VIEW，只读

#### Scenario: 虚拟对象定义
- **WHEN** 用户定义 `object_type: virtual` 的对象
- **THEN** 系统不生成任何存储，对象仅存在于内存中

### Requirement: 视图配置统一

系统 SHALL 提供 `ViewConfig` 配置类，统一支持：
- 数据源配置（sources）
- 关联配置（joins）- 原 COMPOSITE 能力
- 聚合配置（group_by, aggregates）- 原 AGGREGATE 能力
- 过滤配置（filters）
- 直接 SQL 定义（sql_definition）

#### Scenario: 聚合视图定义
- **WHEN** 用户在 `view_config` 中配置 `group_by` 和 `aggregates`
- **THEN** 系统生成带 GROUP BY 的 SQL VIEW

#### Scenario: 关联视图定义
- **WHEN** 用户在 `view_config` 中配置 `joins`
- **THEN** 系统生成带 JOIN 的 SQL VIEW

#### Scenario: 聚合+关联视图定义
- **WHEN** 用户同时配置 `joins` 和 `group_by`
- **THEN** 系统生成同时包含 JOIN 和 GROUP BY 的 SQL VIEW

### Requirement: 字段存储策略

系统 SHALL 在 `MetaField` 中提供明确的存储策略属性：

```python
class FieldStorage(Enum):
    STORED = "stored"           # 存储到物理表
    VIRTUAL = "virtual"         # 运行时计算，不存储

class FieldSource(Enum):
    OWN = "own"                 # 自身字段
    MAPPED = "mapped"           # 映射字段
    COMPUTED = "computed"       # 计算字段
    DERIVED = "derived"         # 派生字段
    AGGREGATED = "aggregated"   # 聚合字段
```

**字段级存储策略与对象类型的关系**：

| 对象类型 | 默认 storage | 允许的 source | 说明 |
|---------|-------------|--------------|------|
| ENTITY | STORED | OWN, MAPPED, COMPUTED, DERIVED | 物理表字段 |
| VIEW | VIRTUAL | MAPPED, COMPUTED, AGGREGATED | 视图字段，映射或计算 |
| VIRTUAL | VIRTUAL | OWN, COMPUTED | 内存对象字段 |

**设计理由**：
1. 字段级存储策略提供更细粒度的控制，与 SAP CDS 的 stored/virtual 字段设计一致
2. 对象类型决定整体存储策略，字段级属性可覆盖或细化
3. `source` 属性明确字段值的来源，便于理解和维护
4. `DERIVED` 支持从其他对象派生字段值，`AGGREGATED` 支持聚合计算

#### Scenario: 存储字段
- **WHEN** 字段配置 `storage: stored, source: own`
- **THEN** 字段存储到物理表列

#### Scenario: 计算字段
- **WHEN** 字段配置 `storage: virtual, source: computed`
- **THEN** 字段不存储，查询时计算

#### Scenario: 聚合字段
- **WHEN** 字段配置 `source: aggregated`（仅 VIEW 对象）
- **THEN** 字段值由聚合函数计算

#### Scenario: 派生字段
- **WHEN** 字段配置 `source: derived, derive_from_object: "product", derive_from_field: "price"`
- **THEN** 字段值从 product.price 派生

### Requirement: 虚拟对象配置

系统 SHALL 提供 `VirtualConfig` 配置类，定义虚拟对象的用途和来源：

```python
@dataclass
class VirtualConfig:
    usage: str = "general"         # general / dto / form / calculation
    source_type: str = "memory"    # memory / api / frontend
    lifecycle: str = "transient"   # transient / session / request
    serializable: bool = True
```

#### Scenario: DTO 对象
- **WHEN** 用户定义 `usage: dto, source_type: api` 的虚拟对象
- **THEN** 对象用于 API 请求/响应，支持校验规则

#### Scenario: 计算结果对象
- **WHEN** 用户定义 `usage: calculation` 的虚拟对象
- **THEN** 对象用于承载计算结果

### Requirement: 规则与对象类型约束

系统 SHALL 根据对象类型限制可用的规则类型：

| 规则类型 | ENTITY | VIEW | VIRTUAL |
|---------|--------|------|---------|
| MetaValidation | ✅ | ⚠️ | ✅ |
| MetaConstraint | ✅ | ❌ | ❌ |
| MetaComputation | ✅ | ❌ | ✅ |
| MetaStateTransition | ✅ | ❌ | ❌ |
| MetaTrigger | ✅ | ✅ | ✅ |
| MetaDerivation | ✅ | ✅ | ❌ |

**约束矩阵设计理由**：

| 规则类型 | 约束原因 |
|---------|---------|
| MetaValidation | VIEW 只支持查询条件验证，不支持数据验证；VIRTUAL 支持完整验证 |
| MetaConstraint | 约束需要持久化存储，VIEW 和 VIRTUAL 无存储能力 |
| MetaComputation | VIEW 的计算应在 view_config 中定义；VIRTUAL 支持计算规则 |
| MetaStateTransition | 状态转换需要持久化状态，VIEW 和 VIRTUAL 无状态存储 |
| MetaTrigger | 触发器可基于查询事件，适用于所有对象类型 |
| MetaDerivation | VIEW 支持字段派生（映射）；VIRTUAL 无派生概念 |

#### Scenario: 实体对象规则
- **WHEN** 用户在 ENTITY 对象上定义 MetaConstraint
- **THEN** 系统正常处理约束规则

#### Scenario: 视图对象规则限制
- **WHEN** 用户在 VIEW 对象上定义 MetaConstraint
- **THEN** 系统拒绝并提示"视图对象不支持约束规则"

#### Scenario: 虚拟对象验证规则
- **WHEN** 用户在 VIRTUAL 对象上定义 MetaValidation
- **THEN** 系统正常处理验证规则（如 DTO 字段验证）

### Requirement: 跨对象指标引用

系统 SHALL 支持规则引用其他对象的字段/函数/度量：

```python
@dataclass
class MetricReference:
    object_id: str          # 对象ID
    field_id: str = ""      # 字段ID
    function_id: str = ""   # 函数ID
    filter: str = ""        # 过滤条件
```

**对象分层依赖设计**：

```
┌─────────────────────────────────────────────────────────┐
│                    应用层 (Application)                  │
│  规则、函数、触发器可引用任意层级的对象和度量              │
└─────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   ENTITY 层     │ │    VIEW 层      │ │  VIRTUAL 层     │
│   (物理存储)     │ │  (查询视图)     │ │   (内存对象)    │
│                 │ │                 │ │                 │
│  - 基础实体      │ │  - 聚合视图     │ │  - DTO          │
│  - 业务实体      │ │  - 组合视图     │ │  - 计算结果     │
│                 │ │  - 派生视图     │ │  - 表单对象     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
           │               │
           └───────┬───────┘
                   ▼
         VIEW 可引用 ENTITY
         VIRTUAL 可引用任意层
```

**设计理由**：
1. **对象层规则依赖视图层**：ENTITY 的规则可通过 `metric_refs` 引用 VIEW 的聚合结果
2. **视图层分层构建**：VIEW 可基于其他 VIEW 构建，形成多层视图架构
3. **函数作为桥梁**：MetaFunction 封装跨对象计算，规则引用函数而非直接引用字段
4. **与 Palantir 一致**：Palantir 的 Function 可引用任意 Object，规则可引用 Function

#### Scenario: 引用聚合对象度量
- **WHEN** 规则配置 `metric_refs: [{object_id: "sales_analysis", field_id: "total_sales"}]`
- **THEN** 规则条件中可使用 `metric('sales_analysis.total_sales')` 引用度量值

#### Scenario: 引用对象函数
- **WHEN** 规则配置 `metric_refs: [{object_id: "product", function_id: "calculate_risk"}]`
- **THEN** 规则条件中可引用函数计算结果

#### Scenario: 实体规则依赖视图指标
- **WHEN** ENTITY 对象 `order` 的规则配置 `metric_refs: [{object_id: "customer_stats", field_id: "total_orders"}]`
- **THEN** 规则条件可基于 `customer_stats.total_orders` 进行校验

#### Scenario: 视图分层构建
- **WHEN** VIEW 对象 `sales_summary` 的 `base_objects` 包含 `sales_analysis`（另一个 VIEW）
- **THEN** `sales_summary` 可引用 `sales_analysis` 的字段和聚合结果

### Requirement: 计算函数支持

系统 SHALL 提供 `MetaFunction` 类，支持跨对象计算：

```python
@dataclass
class MetaFunction:
    id: str
    name: str
    expression: str               # 计算表达式
    return_type: FieldType
    parameters: List[Dict]        # 参数列表
    references: List[str]         # 引用的对象.字段
```

**设计理由**：
1. **借鉴 Palantir Function**：Palantir 的 Function 是一等公民，可被规则和视图引用
2. **封装复杂计算**：将跨对象计算逻辑封装为函数，提高复用性
3. **支持参数化**：函数可接受参数，支持动态计算
4. **依赖追踪**：`references` 字段记录函数依赖的对象和字段，便于影响分析

#### Scenario: 定义计算函数
- **WHEN** 用户在对象上定义 `functions: [{id: "risk_score", expression: "turnover * 10"}]`
- **THEN** 规则可引用该函数的计算结果

#### Scenario: 带参数的函数
- **WHEN** 用户定义 `functions: [{id: "calculate_discount", parameters: [{name: "level", type: "int"}], expression: "base_price * (1 - level * 0.1)"}]`
- **THEN** 规则可调用 `calculate_discount(3)` 获取计算结果

#### Scenario: 跨对象函数
- **WHEN** 用户定义 `functions: [{id: "customer_value", references: ["customer.total_orders", "customer.avg_amount"], expression: "total_orders * avg_amount"}]`
- **THEN** 函数依赖被记录，customer 对象变更时可触发相关规则重新计算

## MODIFIED Requirements

### Requirement: MetaObject 对象类型

`MetaObject` SHALL 新增以下属性：

```python
object_type: ObjectType = ObjectType.ENTITY
view_config: Optional[ViewConfig] = None
virtual_config: Optional[VirtualConfig] = None
base_objects: List[str] = field(default_factory=list)
functions: List[MetaFunction] = field(default_factory=list)
```

保留兼容属性：
- `persistent: bool = True` → 等价于 `object_type=ENTITY`
- `is_view: bool = False` → 等价于 `object_type=VIEW`
- `view_definition: str = ""` → 等价于 `view_config.sql_definition`

### Requirement: MetaField 存储策略

`MetaField` SHALL 新增以下属性：

```python
storage: FieldStorage = FieldStorage.STORED
source: FieldSource = FieldSource.OWN
derive_from_object: str = ""
derive_from_field: str = ""
aggregate_function: str = ""
aggregate_source_field: str = ""
```

保留兼容属性：
- `persistent: bool = True` → 等价于 `storage=STORED`
- `computed: bool = False` → 等价于 `source=COMPUTED`

### Requirement: MetaRule 指标引用

`MetaRule` SHALL 新增以下属性：

```python
metric_refs: List[MetricReference] = field(default_factory=list)
```

### Requirement: MetaRegistry 扩展

`MetaRegistry` SHALL 新增以下方法：

```python
def get_objects_by_type(self, object_type: ObjectType) -> List[MetaObject]
def get_functions(self, object_id: str) -> List[MetaFunction]
```

## REMOVED Requirements

无移除的需求。所有现有功能保持向后兼容。

## YAML 示例

### ENTITY 对象示例

```yaml
objects:
  - id: customer
    name: 客户
    object_type: entity
    fields:
      - id: id
        name: 客户ID
        type: STRING
        primary_key: true
        storage: stored
        source: own
      
      - id: name
        name: 客户名称
        type: STRING
        storage: stored
        source: own
      
      - id: credit_limit
        name: 信用额度
        type: FLOAT
        storage: stored
        source: own
      
      - id: risk_level
        name: 风险等级
        type: STRING
        storage: virtual
        source: computed
        expression: "CASE WHEN credit_limit > 100000 THEN 'HIGH' ELSE 'NORMAL' END"
    
    functions:
      - id: calculate_risk_score
        name: 计算风险分数
        expression: "credit_limit * 0.1"
        return_type: FLOAT
        parameters: []
        references: ["credit_limit"]
    
    rules:
      - id: credit_limit_check
        name: 信用额度校验
        type: validation
        condition: "credit_limit > 0"
        message: "信用额度必须大于0"
```

### VIEW 对象示例（聚合视图）

```yaml
objects:
  - id: sales_analysis
    name: 销售分析视图
    object_type: view
    base_objects:
      - order
      - customer
    
    view_config:
      sources:
        - object_id: order
          alias: o
        - object_id: customer
          alias: c
      
      joins:
        - type: LEFT
          source: o
          target: c
          on: "o.customer_id = c.id"
      
      group_by:
        - "c.id"
        - "c.name"
      
      aggregates:
        - field_id: total_amount
          function: SUM
          source_field: "o.amount"
        - field_id: order_count
          function: COUNT
          source_field: "o.id"
      
      filters:
        - "o.status = 'COMPLETED'"
    
    fields:
      - id: customer_id
        name: 客户ID
        type: STRING
        source: mapped
      
      - id: customer_name
        name: 客户名称
        type: STRING
        source: mapped
      
      - id: total_amount
        name: 总金额
        type: FLOAT
        source: aggregated
        aggregate_function: SUM
      
      - id: order_count
        name: 订单数
        type: INT
        source: aggregated
        aggregate_function: COUNT
```

### VIEW 对象示例（组合视图）

```yaml
objects:
  - id: product_detail
    name: 产品详情视图
    object_type: view
    base_objects:
      - product
      - category
      - supplier
    
    view_config:
      sources:
        - object_id: product
          alias: p
        - object_id: category
          alias: cat
        - object_id: supplier
          alias: s
      
      joins:
        - type: LEFT
          source: p
          target: cat
          on: "p.category_id = cat.id"
        - type: LEFT
          source: p
          target: s
          on: "p.supplier_id = s.id"
    
    fields:
      - id: id
        name: 产品ID
        type: STRING
        source: mapped
      
      - id: name
        name: 产品名称
        type: STRING
        source: mapped
      
      - id: category_name
        name: 分类名称
        type: STRING
        source: mapped
        derive_from_object: category
        derive_from_field: name
      
      - id: supplier_name
        name: 供应商名称
        type: STRING
        source: mapped
        derive_from_object: supplier
        derive_from_field: name
```

### VIRTUAL 对象示例（DTO）

```yaml
objects:
  - id: order_create_dto
    name: 订单创建DTO
    object_type: virtual
    
    virtual_config:
      usage: dto
      source_type: api
      lifecycle: request
      serializable: true
    
    fields:
      - id: customer_id
        name: 客户ID
        type: STRING
        source: own
      
      - id: items
        name: 订单项列表
        type: ARRAY
        source: own
      
      - id: remark
        name: 备注
        type: STRING
        source: own
    
    rules:
      - id: customer_required
        name: 客户必填
        type: validation
        condition: "customer_id IS NOT NULL"
        message: "客户ID不能为空"
      
      - id: items_not_empty
        name: 订单项不能为空
        type: validation
        condition: "ARRAY_LENGTH(items) > 0"
        message: "订单项不能为空"
```

### 规则引用视图指标示例

```yaml
objects:
  - id: order
    name: 订单
    object_type: entity
    fields:
      - id: id
        name: 订单ID
        type: STRING
        primary_key: true
      - id: customer_id
        name: 客户ID
        type: STRING
      - id: amount
        name: 金额
        type: FLOAT
    
    rules:
      - id: credit_check
        name: 信用额度校验
        type: validation
        condition: "amount <= metric('customer_stats.credit_available')"
        message: "订单金额超过可用信用额度"
        metric_refs:
          - object_id: customer_stats
            field_id: credit_available
            filter: "customer_id = ${customer_id}"
```

### 多层视图示例

```yaml
objects:
  - id: monthly_sales
    name: 月度销售汇总
    object_type: view
    base_objects:
      - sales_analysis
    
    view_config:
      sources:
        - object_id: sales_analysis
          alias: sa
      
      group_by:
        - "DATE_TRUNC('month', sa.order_date)"
      
      aggregates:
        - field_id: monthly_total
          function: SUM
          source_field: "sa.total_amount"
        - field_id: customer_count
          function: COUNT
          source_field: "sa.customer_id"
          distinct: true
    
    fields:
      - id: month
        name: 月份
        type: DATE
        source: mapped
      
      - id: monthly_total
        name: 月度总额
        type: FLOAT
        source: aggregated
      
      - id: customer_count
        name: 客户数
        type: INT
        source: aggregated
```
