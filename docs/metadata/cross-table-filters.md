# 跨表过滤配置契约

> **版本**: v1.0.0
> **创建日期**: 2026-05-08
> **参考**: SAP CDS Association + Path Expression, SAP Fiori Elements SmartFilterBar

---

## 一、概述

跨表过滤（Cross-Table Filters）是一种特殊的过滤机制，允许用户基于关联表的数据过滤主表记录。例如：通过"备注类型"过滤包含特定类型备注的业务对象。

本配置契约定义了如何在元模型中声明和使用跨表过滤。

---

## 二、配置位置

跨表过滤配置位于元模型的 `analytical_model.cross_table_filters` 节点：

```yaml
# 示例：business_object.yaml
analytical_model:
  enabled: true
  
  # 跨表过滤配置
  cross_table_filters:
    - id: annotation_category
      display_name: 备注类型
      # ... 更多配置
```

---

## 三、配置结构

### 3.1 完整配置示例

```yaml
cross_table_filters:
  - id: annotation_category                    # 过滤字段唯一标识（必需）
    display_name: 备注类型                     # 显示名称（必需）
    description: 按备注类型过滤包含该类型备注的业务对象  # 描述（可选）
    
    # Association 定义（SAP CDS 风格）
    association:
      target_table: annotations               # 目标表名（必需）
      target_alias: a                         # 目标表别名（可选，默认: t）
      join_type: exists                       # JOIN 类型（可选，默认: exists）
      
      # ON 条件（必需）
      on_conditions:
        - left_field: bo.id                  # 左字段（主表字段）
          operator: eq                        # 操作符
          right_field: a.target_id            # 右字段（目标表字段）
        - left_field: "'business_object'"   # 字面量值
          operator: eq
          right_field: a.target_type
      
      # WHERE 条件（用户选择的过滤值）
      where_conditions:
        - field: a.category                  # 过滤字段
          operator: in                       # 操作符
          parameter: annotation_categories    # 前端参数名
      
    # UI 配置
    ui:
      filter_type: multi-select              # 过滤组件类型（必需）
      filter_label: 备注类型                 # 显示标签（可选）
      filter_placeholder: 请选择备注类型     # 占位符（可选）
      
      # 选项配置（必需，选择其一）
      options_source: enum                    # 选项来源
      # options_source: static               #   - static: 静态选项
      # options_source: api                 #   - api: API 端点
      # options_source: enum                #   - enum: 枚举类型
      
      # 当 options_source=static 时
      static_options:
        - value: important
          label: "⚠️ 重要"
        - value: warning
          label: "🚨 警告"
      
      # 当 options_source=enum 时（推荐）
      enum_type: annotation_category         # 枚举类型 ID
      
      # 当 options_source=api 时
      api_endpoint: /api/v1/custom-options  # API 端点
      
      position: 50                           # 排序位置（可选）
```

---

## 四、字段说明

### 4.1 顶层字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| id | string | ✅ | 过滤字段唯一标识，用于前端参数名 |
| display_name | string | ✅ | 显示名称 |
| description | string | - | 描述信息 |
| association | object | ✅ | 关联定义 |
| ui | object | ✅ | UI 配置 |

---

### 4.2 association（关联定义）

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| target_table | string | ✅ | 目标表名（数据库表名） |
| target_alias | string | - | 目标表别名（默认: t） |
| join_type | enum | - | JOIN 类型：`exists`（默认）/ `inner` / `left` |
| on_conditions | array | ✅ | ON 条件列表 |
| where_conditions | array | - | WHERE 条件列表 |

#### 4.2.1 on_conditions（ON 条件）

定义 JOIN 的 ON 条件。

```yaml
on_conditions:
  - left_field: bo.id              # 左字段
    operator: eq                   # 操作符
    right_field: a.target_id      # 右字段
```

**支持的操作符**:

| 操作符 | 说明 | SQL 示例 |
|--------|------|----------|
| eq | 等于 | `a = b` |
| ne | 不等于 | `a != b` |
| gt | 大于 | `a > b` |
| ge | 大于等于 | `a >= b` |
| lt | 小于 | `a < b` |
| le | 小于等于 | `a <= b` |
| like | 模糊匹配 | `a LIKE b` |

**字面量值**: 使用单引号包裹表示字面量

```yaml
# 字面量示例
left_field: "'business_object'"  # 字符串字面量
right_field: a.target_type
```

#### 4.2.2 where_conditions（WHERE 条件）

定义用户选择的过滤条件。

```yaml
where_conditions:
  - field: a.category             # 过滤字段
    operator: in                  # 操作符
    parameter: annotation_categories  # 前端参数名（对应 globalFilters 中的 key）
```

**说明**:
- `field`: 目标表中的字段名
- `operator`: SQL 操作符
- `parameter`: 前端接收的参数名，会从 `globalFilters` 中读取值

---

### 4.3 ui（UI 配置）

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| filter_type | enum | ✅ | 过滤组件类型 |
| filter_label | string | - | 显示标签 |
| filter_placeholder | string | - | 占位符文本 |
| options_source | enum | ✅ | 选项来源 |
| static_options | array | - | 静态选项（options_source=static 时） |
| enum_type | string | - | 枚举类型 ID（options_source=enum 时） |
| api_endpoint | string | - | API 端点（options_source=api 时） |
| position | number | - | 排序位置 |

#### 4.3.1 filter_type（过滤组件类型）

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| search | 文本搜索框 | 模糊匹配搜索 |
| select | 单选下拉框 | 精确匹配单选 |
| multi-select | 多选下拉框 | 精确匹配多选 |
| date | 日期选择器 | 日期范围 |
| date-range | 日期范围选择器 | 起止日期范围 |
| number | 数字输入框 | 数值范围 |

#### 4.3.2 options_source（选项来源）

| 来源 | 说明 | 配置字段 |
|------|------|----------|
| static | 静态选项 | static_options |
| enum | 枚举类型（推荐） | enum_type |
| api | API 端点 | api_endpoint |

---

## 五、配置示例

### 5.1 按备注类型过滤

```yaml
cross_table_filters:
  - id: annotation_category
    display_name: 备注类型
    description: 按备注类型过滤包含该类型备注的业务对象
    
    association:
      target_table: annotations
      target_alias: a
      join_type: exists
      
      on_conditions:
        - left_field: bo.id
          operator: eq
          right_field: a.target_id
        - left_field: "'business_object'"
          operator: eq
          right_field: a.target_type
      
      where_conditions:
        - field: a.category
          operator: in
          parameter: annotation_categories
    
    ui:
      filter_type: multi-select
      filter_label: 备注类型
      filter_placeholder: 请选择备注类型
      options_source: enum
      enum_type: annotation_category
      position: 50
```

**生成的 SQL**:

```sql
SELECT * FROM business_objects bo
WHERE EXISTS (
  SELECT 1 FROM annotations a
  WHERE a.target_id = bo.id
    AND a.target_type = 'business_object'
    AND a.category IN ('important', 'warning')
)
```

### 5.2 按备注内容搜索

```yaml
cross_table_filters:
  - id: annotation_content_search
    display_name: 备注内容
    description: 按备注内容模糊搜索业务对象
    
    association:
      target_table: annotations
      target_alias: a
      join_type: exists
      
      on_conditions:
        - left_field: bo.id
          operator: eq
          right_field: a.target_id
        - left_field: "'business_object'"
          operator: eq
          right_field: a.target_type
      
      where_conditions:
        - field: a.content
          operator: like
          parameter: annotation_content
    
    ui:
      filter_type: search
      filter_label: 备注内容
      filter_placeholder: 输入备注内容关键词...
      position: 51
```

**生成的 SQL**:

```sql
SELECT * FROM business_objects bo
WHERE EXISTS (
  SELECT 1 FROM annotations a
  WHERE a.target_id = bo.id
    AND a.target_type = 'business_object'
    AND a.content LIKE '%架构设计%'
)
```

### 5.3 静态选项示例

```yaml
cross_table_filters:
  - id: priority_filter
    display_name: 优先级
    description: 按优先级过滤
    
    association:
      target_table: tasks
      target_alias: t
      join_type: exists
      
      on_conditions:
        - left_field: bo.id
          operator: eq
          right_field: t.business_object_id
      
      where_conditions:
        - field: t.priority
          operator: eq
          parameter: priority
    
    ui:
      filter_type: select
      filter_label: 优先级
      filter_placeholder: 请选择优先级
      options_source: static
      static_options:
        - value: high
          label: "🔴 高"
        - value: medium
          label: "🟡 中"
        - value: low
          label: "🟢 低"
```

---

## 六、错误配置示例

### ❌ 错误 1：缺少必需字段

```yaml
# 错误：缺少 association
cross_table_filters:
  - id: test_filter
    display_name: 测试过滤
    ui:
      filter_type: search
```

**错误**:
- 缺少 `association` 字段

**修复**:
```yaml
cross_table_filters:
  - id: test_filter
    display_name: 测试过滤
    association:
      target_table: other_table
      on_conditions:
        - left_field: bo.id
          operator: eq
          right_field: t.id
    ui:
      filter_type: search
```

---

### ❌ 错误 2：enum 类型但缺少 enum_type

```yaml
# 错误：options_source=enum 但未指定 enum_type
cross_table_filters:
  - id: test_filter
    display_name: 测试过滤
    association:
      target_table: annotations
      on_conditions:
        - left_field: bo.id
          operator: eq
          right_field: a.target_id
    ui:
      filter_type: multi-select
      options_source: enum
      # enum_type 缺失！
```

**错误**:
- `options_source=enum` 但缺少 `enum_type`

**修复**:
```yaml
ui:
  filter_type: multi-select
  options_source: enum
  enum_type: annotation_category  # 添加枚举类型 ID
```

---

### ❌ 错误 3：api 类型但缺少 endpoint

```yaml
# 错误：options_source=api 但未指定 api_endpoint
cross_table_filters:
  - id: test_filter
    display_name: 测试过滤
    ui:
      filter_type: select
      options_source: api
      # api_endpoint 缺失！
```

**修复**:
```yaml
ui:
  filter_type: select
  options_source: api
  api_endpoint: /api/v1/custom-options  # 添加 API 端点
```

---

## 七、验证规则

系统会在运行时验证配置：

### 7.1 必需字段验证

- [ ] `id` 必须存在且唯一
- [ ] `association.target_table` 必须存在
- [ ] `association.on_conditions` 必须至少包含一个条件
- [ ] `ui.filter_type` 必须存在
- [ ] `ui.options_source` 必须存在

### 7.2 选项来源验证

| options_source | 必需字段 |
|--------------|----------|
| static | static_options |
| enum | enum_type |
| api | api_endpoint |

### 7.3 验证日志

配置错误会在控制台输出警告：

```
[ConfigValidator] cross_table_filters validation warnings:
  [0] Missing ui.filter_placeholder
[ConfigValidator] cross_table_filters validation errors:
  [1] Missing ui.enum_type when options_source=enum
```

---

## 八、相关文档

- [枚举 API 规范](../api/enum-api.md)
- [组件治理规范](../../.trae/rules/component-governance.md)
- [元模型驱动过滤规范](../../.trae/specs/meta-model-driven-filters/spec.md)

---

**最后更新**: 2026-05-08
