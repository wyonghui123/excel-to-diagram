# YAML 配置规范

> 本文档详细说明了 YAML 元数据文件的配置规范，遵循「单一事实原则」。

---

## 一、文件结构

### 1.1 目录结构

```
meta/schemas/
├── user.yaml              # 用户
├── role.yaml             # 角色
├── user_group.yaml       # 用户组
├── _template.yaml        # 新对象模板
└── _examples/           # 示例参考
    ├── basic.yaml        # 基础对象
    ├── with_associations.yaml  # 带关联
    └── with_hierarchy.yaml    # 带层级
```

### 1.2 标准文件结构

```yaml
# ============================================
# [对象名称]元模型
# 说明: [简短描述]
# ============================================

id: [object_name]           # 必填：对象标识，snake_case
name: [显示名称]            # 必填：对象中文名称
table_name: [表名]          # 必填：数据库表名

# 元数据
description: [描述]
semantics:
  meaning: [业务含义]
  category: [分类]

# 删除策略
deletion_policy:
  mode: [cascade|restrict|set_null]
  cascade_delete: []       # 级联删除的表

# 审计配置
audit:
  enabled: true
  create:
    enabled: true
    fields: all
  update:
    enabled: true
    fields: changed_only

# 字段定义
fields:
  - id: id
    name: ID
    type: integer
    # id 字段默认只读、隐藏

  - id: code
    name: 编码
    type: string
    required: true
    semantics:
      business_key: true    # 业务键：创建后只读

  - id: name
    name: 名称
    type: string
    required: true

# 关联定义
associations:
  [association_name]:
    name: [显示名称]
    target_type: [目标对象]
    type: many_to_many
    through: [中间表]

# UI 视图配置
ui_view_config:
  list:
    title: [列表标题]
    columns: []
  detail:
    layout: tabs
    tabs: []
```

---

## 二、字段配置

### 2.1 字段类型

| type | 说明 | 示例 |
|------|------|------|
| `string` | 字符串 | `"hello"` |
| `text` | 长文本 | 多行描述 |
| `integer` | 整数 | `123` |
| `float` | 浮点数 | `1.23` |
| `boolean` | 布尔值 | `true/false` |
| `datetime` | 日期时间 | `2024-01-01` |
| `date` | 日期 | `2024-01-01` |
| `enum` | 枚举 | 通过 `enum_values` 定义 |

### 2.2 字段属性

```yaml
fields:
  - id: field_id              # 必填：字段标识
    name: 字段名称             # 必填：显示名称
    type: string              # 必填：字段类型
    db_column: field_id       # 可选：数据库列名，默认同 id
    required: false          # 可选：是否必填，默认 false
    unique: false            # 可选：是否唯一，默认 false
    default: null           # 可选：默认值
    max_length: 255          # 可选：最大长度
    nullable: true           # 可选：是否可空，默认 true
    description: 描述        # 可选：字段描述
```

### 2.3 semantics 语义配置

```yaml
fields:
  - id: code
    semantics:
      business_key: true     # 业务键：自动只读
      immutable: true         # 不可变：创建后不可修改
      computed: true         # 计算字段：只读
      audit_field: true     # 审计字段：隐藏
      display_name: true    # 显示名称
      searchable: true      # 可搜索
      parent_key: true      # 父级键：层级结构
      hierarchy_field: parent  # 层级字段
```

### 2.4 ui 界面配置

```yaml
fields:
  - id: status
    ui:
      widget: select         # 表单控件类型
      visible: true          # 是否可见（通常不配置）
      editable: true        # 是否可编辑（通常不配置）
      hidden_in_list: false # 列表中隐藏
      hidden_in_form: false # 表单中隐藏
      hidden_in_detail: false # 详情中隐藏
      width: 120            # 列宽
      placeholder: 请选择   # 占位符
      hint: 提示信息        # 帮助提示
```

### 2.5 控件类型 (widget)

| widget | 说明 | 适用场景 |
|--------|------|---------|
| `input` | 文本输入框 | 默认 |
| `textarea` | 多行文本 | 描述、备注 |
| `select` | 下拉选择 | 枚举、外键 |
| `switch` | 开关 | 布尔值 |
| `checkbox` | 复选框 | 多选 |
| `radio` | 单选框 | 少量选项 |
| `date-picker` | 日期选择 | 日期字段 |
| `datetime-picker` | 日期时间 | 时间字段 |
| `number` | 数字输入 | 数值字段 |
| `association_selector` | 关联选择 | 外键字段 |

---

## 三、关联配置 (associations)

### 3.1 关联类型

```yaml
associations:
  users:
    name: 用户              # 关联显示名称
    target_type: user      # 目标对象类型
    type: many_to_many     # 关联类型
    through: user_roles    # 中间表（多对多）
    source_key: role_id    # 本端外键
    target_key: user_id    # 目标端外键
```

### 3.2 支持的关联类型

| type | 说明 | 需要的配置 |
|------|------|-----------|
| `many_to_many` | 多对多 | `through`, `source_key`, `target_key` |
| `one_to_many` | 一对多 | `foreign_key` |
| `many_to_one` | 多对一 | 自动识别 |
| `one_to_one` | 一对一 | `foreign_key` |

### 3.3 关联显示配置

```yaml
associations:
  users:
    display:
      label: 用户
      plural_label: 用户列表
      target_display_field: display_name  # 显示字段
      target_code_field: username        # 编码字段
      target_avatar_field: avatar_url    # 头像字段
```

---

## 四、detail.tabs 详情页配置

### 4.1 基础配置

```yaml
detail:
  layout: tabs              # 布局类型：tabs/card/fields
  title: "{record.name} 详情"  # 标题，支持变量替换

  tabs:
    - id: basic
      label: 基本信息
      type: fields
      fields: [code, name, description]
    
    - id: members
      label: 成员
      type: association
      association: members
      actions: [assign, unassign]
    
    - id: history
      label: 变更历史
      type: history
```

### 4.2 Tab 类型

| type | 说明 | 配置项 |
|------|------|--------|
| `fields` | 字段表单 | `fields: [field1, field2]` |
| `association` | 关联面板 | `association: xxx`, `actions` |
| `history` | 变更历史 | 无需配置 |

---

## 五、ui_view_config 视图配置

### 5.1 list 列表配置

```yaml
ui_view_config:
  list:
    title: 对象管理
    description: 对象列表描述
    
    columns:               # 列表列配置
      - field: code
        width: 120
        sortable: true
        filterable: true
      - field: name
        width: 180
    
    searchFields:          # 全局搜索字段
      - name
      - code
      - description
    
    actions:               # 工具栏按钮
      - id: create
        label: 新建
        icon: plus
        type: primary
    
    batch_actions:         # 批量操作
      - id: batch_delete
        label: 批量删除
        type: danger
    
    filters:              # 过滤器
      - field: name
        type: string
        operator: contains
```

### 5.2 form 表单配置

```yaml
ui_view_config:
  form:
    title: 对象信息
    layout: vertical
    
    groups:               # 字段分组
      - id: basic
        label: 基本信息
        columns: 2
        fields: [code, name]
    
    fields:               # 字段级配置
      code:
        placeholder: 请输入编码
        required: true
      name:
        placeholder: 请输入名称
```

---

## 六、权限配置

### 6.1 category_config

```yaml
category_config:
  create_permission: object:create
  update_permission: object:update
  delete_permission: object:delete
  owner_auto_permission: false
```

### 6.2 字段级权限

```yaml
fields:
  - id: sensitive_field
    ui:
      visible: false       # 完全隐藏
      # 或
      editable: false      # 显示但不可编辑
```

---

## 七、最佳实践

### 7.1 最小化配置

```yaml
# ✅ 正确：最小配置
fields:
  - id: name
    required: true

# ❌ 错误：冗余配置
fields:
  - id: name
    required: true
    ui:
      visible: true        # 冗余
      editable: true       # 冗余
```

### 7.2 审计字段

```yaml
fields:
  - id: created_at
    type: datetime
    semantics:
      audit_field: true    # 自动隐藏、只读
```

### 7.3 业务键

```yaml
fields:
  - id: code
    required: true
    unique: true
    semantics:
      business_key: true   # 创建后只读
```

### 7.4 外键关联

```yaml
fields:
  - id: role_id
    type: integer
    ui:
      widget: select
      target_type: role    # 关联对象
      multiple: false
```

---

## 八、常见问题

### Q1: 字段需要在多处显示，如何配置？

A: 使用 `ui_view_config.list` 控制列表列，`detail.tabs` 控制详情页。

### Q2: 某些字段需要特殊权限？

A: 在字段的 `ui` 中配置 `editable: false` 或 `visible: false`。

### Q3: 如何添加计算字段？

A: 在 `fields` 中添加字段，设置 `semantics.computed: true`。

### Q4: 关联如何实现添加/移除功能？

A: 在 `associations` 中配置 `actions: [assign, unassign]`。

---

## 九、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-05-12 | 初始版本 |
