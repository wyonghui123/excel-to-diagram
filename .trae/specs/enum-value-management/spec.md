# 枚举值管理功能 Spec

## Why

当前系统中的业务枚举值（如关系类型、备注类型等）分散在代码中定义，用户无法自行维护。需要提供一个统一的枚举值管理机制，支持系统枚举和业务枚举的分层管理，并支持多维枚举值。

## What Changes

- 新增 `enum_type` 元模型对象，定义枚举类型的元数据
- 新增 `enum_value` 元模型对象，存储枚举值项
- 扩展 `MetaField` 元模型，增加 `enum_type` 和 `enum_filter` 属性
- 新增枚举值管理 API（类型管理、值管理、维度过滤）
- 新增枚举值管理前端界面（类型列表、值管理、维度配置）
- 集成到现有字段配置和表单组件中

## Impact

- Affected specs: 元模型驱动架构、字段配置、表单组件
- Affected code: 
  - `meta/schemas/` - 新增 enum_type.yaml, enum_value.yaml
  - `meta/core/models.py` - 扩展 MetaField
  - `meta/api/` - 新增枚举值管理 API
  - `src/views/` - 新增枚举值管理界面
  - `src/components/common/MetaForm.vue` - 集成枚举选择

---

## ADDED Requirements

### Requirement: Enum Type Management

系统应提供枚举类型管理功能，支持系统枚举和业务枚举的分层管理。

#### Scenario: 查看枚举类型列表
- **WHEN** 用户访问系统管理 > 枚举值管理
- **THEN** 显示所有枚举类型列表，包含编码、名称、分类、可维护性、维度等信息

#### Scenario: 创建业务枚举类型
- **WHEN** 管理员点击"新建业务枚举"按钮
- **THEN** 显示创建表单，可配置枚举类型的基本信息和维度定义

#### Scenario: 系统枚举不可修改
- **WHEN** 用户尝试修改系统枚举类型（如 field_type）
- **THEN** 系统拒绝操作，提示"系统枚举不可修改"

---

### Requirement: Enum Mutability Control

系统应支持三种可维护性级别，控制用户对枚举值的操作权限。

#### Scenario: Locked - 完全锁定
- **GIVEN** 枚举类型可维护性为 `locked`
- **WHEN** 用户查看该枚举类型
- **THEN** 只能查看枚举值列表，不可新增、编辑、删除

#### Scenario: Extensible - 可扩展
- **GIVEN** 枚举类型可维护性为 `extensible`
- **WHEN** 用户管理该枚举类型的值
- **THEN** 可以新增值，可以编辑值，但系统预置值（is_system=true）不可删除

#### Scenario: Fully Editable - 完全可编辑
- **GIVEN** 枚举类型可维护性为 `fully_editable`
- **WHEN** 用户管理该枚举类型的值
- **THEN** 可以新增、编辑、删除所有值（系统预置值除外）

---

### Requirement: Multi-Dimensional Enum Support

系统应支持多维枚举值，允许同一枚举类型在不同维度下有不同的值集。

#### Scenario: 配置多维枚举
- **GIVEN** 管理员创建枚举类型时配置了维度（如产品维度）
- **WHEN** 用户管理该枚举类型的值
- **THEN** 可以按维度标签页切换，为每个维度配置不同的枚举值

#### Scenario: 维度过滤显示
- **GIVEN** 枚举类型有产品维度，包含 ERP 和 CRM 两个产品的值
- **WHEN** 用户选择 CRM 标签页
- **THEN** 只显示 dimensions.product = 'CRM' 的枚举值

#### Scenario: 同编码不同维度
- **GIVEN** 枚举类型有产品维度
- **WHEN** 用户为 ERP 产品添加编码为 'REFERENCE' 的值，为 CRM 产品也添加编码为 'REFERENCE' 的值
- **THEN** 系统允许，两个值可以有不同的名称和属性

---

### Requirement: Enum Value CRUD

系统应提供枚举值的完整 CRUD 操作。

#### Scenario: 新增枚举值
- **WHEN** 用户在枚举值管理界面点击"新增值"
- **THEN** 显示编辑表单，可填写编码、名称、英文名称、排序、状态等

#### Scenario: 编辑枚举值
- **WHEN** 用户点击枚举值的"编辑"按钮
- **THEN** 显示编辑表单，可修改名称、排序、状态等属性

#### Scenario: 删除枚举值
- **GIVEN** 枚举值 is_system = false 且枚举类型可维护性允许删除
- **WHEN** 用户点击"删除"按钮并确认
- **THEN** 删除该枚举值

#### Scenario: 删除系统值被拒绝
- **GIVEN** 枚举值 is_system = true
- **WHEN** 用户尝试删除
- **THEN** 系统拒绝操作，提示"系统预置值不可删除"

#### Scenario: 停用枚举值
- **WHEN** 用户将枚举值的 is_active 设置为 false
- **THEN** 该值不会在业务表单的下拉选项中显示

---

### Requirement: Field Enum Configuration

系统应支持在字段配置中关联枚举类型，并支持维度过滤。

#### Scenario: 字段关联枚举类型
- **WHEN** 开发者在字段定义中设置 enum_type 属性
- **THEN** 该字段在表单中显示为下拉选择框，选项来自枚举值

#### Scenario: 字段配置维度过滤
- **GIVEN** 字段关联了多维枚举类型
- **WHEN** 开发者在字段定义中设置 enum_filter 属性（如 {product: 'ERP'}）
- **THEN** 业务表单中该字段的下拉选项只显示匹配维度条件的枚举值

#### Scenario: 字段配置默认值
- **WHEN** 开发者在字段定义中设置 enum_default_value 属性
- **THEN** 新建记录时该字段自动填充默认值

---

### Requirement: Runtime Enum Selection

系统应在运行时提供枚举值选择功能。

#### Scenario: 业务表单枚举选择
- **GIVEN** 字段配置了 enum_type
- **WHEN** 用户在业务表单中编辑该字段
- **THEN** 显示下拉选择框，选项为该枚举类型的所有启用值（按排序排列）

#### Scenario: 动态维度过滤
- **GIVEN** 字段配置了 enum_type 和 enum_filter
- **WHEN** 用户在业务表单中编辑该字段
- **THEN** 显示下拉选择框，选项为过滤后的枚举值

---

## MODIFIED Requirements

### Requirement: MetaField Model Extension

扩展 MetaField 元模型，增加枚举相关属性。

**修改内容**：
- 新增 `enum_type` 属性：关联的枚举类型ID
- 新增 `enum_filter` 属性：维度过滤条件（JSON）
- 新增 `enum_default_value` 属性：默认枚举值编码

---

## Technical Design

### Data Model

#### enum_type 表
```sql
CREATE TABLE enum_types (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    category VARCHAR(32) NOT NULL,        -- system | business
    mutability VARCHAR(32) NOT NULL,      -- locked | extensible | fully_editable
    dimension_schema JSON,                 -- 维度定义
    description TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

#### enum_value 表
```sql
CREATE TABLE enum_values (
    id SERIAL PRIMARY KEY,
    enum_type_id VARCHAR(64) NOT NULL,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(256) NOT NULL,
    name_en VARCHAR(256),
    dimensions JSON,                        -- 多维值
    sort_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    is_system BOOLEAN DEFAULT FALSE,
    parent_code VARCHAR(64),
    metadata JSON,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    UNIQUE(enum_type_id, code),
    FOREIGN KEY (enum_type_id) REFERENCES enum_types(id)
);
```

### API Design

```
# 枚举类型 API
GET    /api/v1/enum-types                    # 列表
GET    /api/v1/enum-types/{id}               # 详情
POST   /api/v1/enum-types                    # 创建（仅业务枚举）
PUT    /api/v1/enum-types/{id}               # 更新
DELETE /api/v1/enum-types/{id}               # 删除（仅无值时）

# 枚举值 API
GET    /api/v1/enum-types/{type_id}/values   # 获取枚举值列表
GET    /api/v1/enum-values/{id}              # 详情
POST   /api/v1/enum-types/{type_id}/values   # 新增值
PUT    /api/v1/enum-values/{id}              # 更新值
DELETE /api/v1/enum-values/{id}              # 删除值（检查 is_system）
```

### Frontend Components

1. **EnumTypeList.vue** - 枚举类型列表页
2. **EnumValueManagement.vue** - 枚举值管理页
3. **EnumValueForm.vue** - 枚举值编辑表单
4. **EnumSelect.vue** - 枚举选择组件（用于业务表单）

---

## Migration Strategy

1. **Phase 1**: 创建元模型和数据库表
2. **Phase 2**: 迁移现有枚举值到新表（作为系统枚举）
3. **Phase 3**: 实现后端 API
4. **Phase 4**: 实现前端管理界面
5. **Phase 5**: 集成到字段配置和表单组件
