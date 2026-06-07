# Phase A: 结构基础 + 快速交付 Spec

## Why

当前元模型缺少两个关键能力：(1) Aspect 切面——现有的 `includes` + `shared_properties.yaml` 仅支持字段级复用，无法打包 semantics/validations/rules，导致每个对象仍需重复配置审计字段的 auto_fill 逻辑；(2) Pseudo Variables 声明式自动填充——`ActionExecutor._prepare_data()` 中 `created_at`/`updated_at` 硬编码 `datetime.now()`，`created_by`/`updated_by` 未自动填充，无法通过 YAML 配置声明式地指定 `$now`/`$user` 等伪变量。Phase A 将升级 includes 为完整 Aspect 机制，并实现 auto_fill 伪变量解析，消除硬编码、建立字段/语义/规则复用的架构基础。

## What Changes

- **Aspect 切面**：升级现有 `includes` + `shared_properties.yaml` 为 `aspects` + `aspects.yaml`，支持字段 + semantics + validations + rules 合并，对象通过 `aspects: [audit_aspect]` 引用
- **Pseudo Variables 自动填充**：`SemanticAnnotation` 新增 `auto_fill` 属性，`ActionExecutor._prepare_data()` 从硬编码改为读取 YAML auto_fill 配置，新增伪变量解析器（`$now`, `$user.id`, `$user.name`, `$uuid`）
- **标准 Aspect 库**：将现有 `shared_properties.yaml` 的 4 组字段升级为完整 Aspect（含 auto_fill 配置）
- **BREAKING**：`shared_properties.yaml` → `aspects.yaml`，YAML 中 `includes: [...]` → `aspects: [...]`（提供迁移兼容）

## Impact

- Affected specs: p0-meta-model-core-enhancement（includes 升级为 aspects）、business-key-context-enhancement（context_field 可通过 Aspect 打包）
- Affected code:
  - `meta/core/models.py` - SemanticAnnotation 新增 auto_fill；MetaObject includes → aspects；新增 AspectDefinition 模型
  - `meta/core/yaml_loader.py` - _resolve_includes() → _resolve_aspects()；解析 auto_fill；解析 aspects.yaml
  - `meta/core/action_executor.py` - _prepare_data() 改为配置驱动；新增 _resolve_auto_fill()
  - `meta/schemas/shared_properties.yaml` → `meta/schemas/aspects.yaml`
  - `meta/schemas/*.yaml` - includes → aspects 迁移
  - `meta/tests/` - 新增 Aspect 和 auto_fill 测试

## ADDED Requirements

### Requirement: Aspect 切面定义与引用

系统 SHALL 支持在 `aspects.yaml` 中定义 Aspect 切面，每个 Aspect 包含 fields、semantics、validations、rules，YAML 对象通过 `aspects: [aspect_name]` 引用。

#### 现有实现分析

| 组件 | 现状 | 影响 |
|------|------|------|
| `shared_properties.yaml` | 仅定义字段列表（hierarchy_fields, audit_fields 等） | 升级为 aspects.yaml，每个 aspect 包含 fields + semantics + validations + rules |
| `MetaObject.includes` | `List[str]`，引用 shared_properties 中的字段组 | 升级为 `MetaObject.aspects: List[str]`，保留 includes 作为向后兼容别名 |
| `yaml_loader._resolve_includes()` | 仅合并 fields 列表 | 升级为 `_resolve_aspects()`，合并 fields + semantics + validations + rules |
| `MetaField.included_from` | 标记字段来自哪个 shared_property 组 | 保留，改名为 `aspect_source`（included_from 作为别名保留） |

#### Scenario: 定义 Aspect 切面
- **WHEN** 用户在 `aspects.yaml` 中定义 `audit_aspect`，包含 fields（created_at, updated_at, created_by, updated_by）及其 semantics（含 auto_fill）
- **THEN** 该 Aspect 可被任何 YAML 对象通过 `aspects: [audit_aspect]` 引用

#### Scenario: 引用 Aspect 切面
- **WHEN** 用户在 domain.yaml 中定义 `aspects: [audit_aspect, naming_aspect]`
- **THEN** 解析时自动将 Aspect 中的 fields、semantics、validations、rules 展开合并到对象

#### Scenario: 本地字段覆盖 Aspect 字段
- **WHEN** 对象本地定义了与 Aspect 同 id 的字段
- **THEN** 本地定义覆盖 Aspect 定义，`aspect_source` 标记为被覆盖的 Aspect 名称

#### Scenario: Aspect 包含 validations 和 rules
- **WHEN** Aspect 定义中包含 validations 或 rules
- **THEN** 这些 validations/rules 被合并到对象的 rules 列表中，rule.id 加 Aspect 前缀避免冲突

#### Scenario: 多个 Aspect 字段冲突
- **WHEN** 两个 Aspect 都定义了同 id 的字段
- **THEN** 后引用的 Aspect 覆盖先引用的，日志记录冲突警告

#### Scenario: 向后兼容 includes
- **WHEN** YAML 中仍使用 `includes: [hierarchy_fields]` 旧语法
- **THEN** 系统将其视为 `aspects: [hierarchy_fields]` 的别名，行为一致

#### Scenario: 向后兼容无 aspects 配置
- **WHEN** YAML 中无 aspects 和 includes 配置
- **THEN** 行为与修改前完全一致

### Requirement: Pseudo Variables 声明式自动填充

系统 SHALL 支持在字段 semantics 中声明 `auto_fill` 配置，在创建/更新时自动注入伪变量值，替代 ActionExecutor 中的硬编码逻辑。

#### 现有实现分析

| 组件 | 现状 | 影响 |
|------|------|------|
| `ActionExecutor._prepare_data()` | 硬编码 `datetime.now()` 填充 created_at/updated_at | 改为读取 auto_fill 配置，硬编码逻辑移除 |
| `AuditLogger.set_user()` | 已有用户上下文（user_id, user_name） | 复用，扩展为全局可访问的 UserContext |
| `SemanticAnnotation` | 无 auto_fill 属性 | 新增 `auto_fill: Dict` 可选属性 |
| `RuleContext` | 无伪变量支持 | 扩展支持 $now, $user 等 |

#### Scenario: 声明 auto_fill 配置
- **WHEN** 用户在 YAML 中定义字段的 `semantics.auto_fill.on_create: $now`
- **THEN** 创建该对象时，该字段自动填充当前时间戳

#### Scenario: on_create 自动填充
- **WHEN** 字段配置 `auto_fill.on_create: $now` 且执行创建操作
- **THEN** 该字段自动填充为当前时间，用户传入的值被忽略

#### Scenario: on_update 自动填充
- **WHEN** 字段配置 `auto_fill.on_update: $now` 且执行更新操作
- **THEN** 该字段自动填充为当前时间，用户传入的值被忽略

#### Scenario: $user 伪变量
- **WHEN** 字段配置 `auto_fill.on_create: $user.name` 且当前有登录用户
- **THEN** 该字段自动填充为当前用户的用户名

#### Scenario: $uuid 伪变量
- **WHEN** 字段配置 `auto_fill.on_create: $uuid`
- **THEN** 该字段自动填充为自动生成的 UUID 字符串

#### Scenario: 无用户上下文时 $user 返回空
- **WHEN** 字段配置 `auto_fill.on_create: $user.name` 但无登录用户
- **THEN** 该字段填充为空字符串

#### Scenario: 非 auto_fill 字段不受影响
- **WHEN** 字段无 auto_fill 配置
- **THEN** 行为与修改前完全一致，用户传入的值正常使用

#### Scenario: 硬编码逻辑迁移
- **WHEN** `_prepare_data()` 中的 `datetime.now()` 硬编码被移除
- **THEN** created_at/updated_at 的自动填充完全由 auto_fill 配置驱动

### Requirement: 标准 Aspect 库

系统 SHALL 提供标准 Aspect 库，将现有 shared_properties.yaml 的 4 组字段升级为完整 Aspect。

#### Scenario: audit_aspect
- **WHEN** 对象引用 `aspects: [audit_aspect]`
- **THEN** 自动获得 created_at($now)、updated_at($now on update)、created_by($user.name)、updated_by($user.name on update) 四个字段及其 auto_fill 配置

#### Scenario: hierarchy_aspect
- **WHEN** 对象引用 `aspects: [hierarchy_aspect]`
- **THEN** 自动获得 version_id、version_name、version_code、product_code 字段及其 semantics 配置

#### Scenario: naming_aspect
- **WHEN** 对象引用 `aspects: [naming_aspect]`
- **THEN** 自动获得 code、name 字段及其 semantics 配置（business_key、immutable、pattern 等）

#### Scenario: owner_aspect
- **WHEN** 对象引用 `aspects: [owner_aspect]`
- **THEN** 自动获得 owner_id 字段及其 semantics 配置

## MODIFIED Requirements

### Requirement: SemanticAnnotation 属性扩展

`SemanticAnnotation` 数据类 SHALL 新增以下可选属性：

```python
auto_fill: Dict[str, str] = field(default_factory=dict)  # {on_create: "$now", on_update: "$now"}
```

### Requirement: MetaObject 属性扩展

`MetaObject` 数据类 SHALL 新增 `aspects: List[str]` 属性，`includes` 保留作为向后兼容别名：

```python
aspects: List[str] = field(default_factory=list)  # 引用的 Aspect 切面
# includes 保留，加载时自动合并到 aspects
```

### Requirement: ActionExecutor._prepare_data 行为变更

`ActionExecutor._prepare_data()` SHALL 从硬编码改为读取字段的 `auto_fill` 配置。移除以下硬编码逻辑：
- `for_create and field.id == "created_at"` → 由 `auto_fill.on_create: $now` 驱动
- `for_create and field.id == "updated_at"` → 由 `auto_fill.on_create: $now` 驱动
- `for_update and field.id == "updated_at"` → 由 `auto_fill.on_update: $now` 驱动

### Requirement: yaml_loader 解析扩展

`yaml_loader.py` SHALL 扩展以下解析能力：
- `parse_semantics()` 新增 `auto_fill` 字段解析
- `_resolve_includes()` 升级为 `_resolve_aspects()`，支持 fields + semantics + validations + rules 合并
- `parse_meta_object()` 解析 `aspects` 配置，`includes` 作为别名合并
- 新增 `parse_aspects_yaml()` 函数加载 aspects.yaml

## REMOVED Requirements

无移除的需求。所有现有功能保持向后兼容，`includes` 语法继续有效。
