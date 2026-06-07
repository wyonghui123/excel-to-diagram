# P0 元模型核心增强 Spec

## Why

当前元模型缺少三个核心能力：组合关系（Composition）语义、声明式权限绑定、共享属性复用。这导致级联删除策略只能从 hierarchies.yaml 全局配置、权限码已定义但未与 API 端点绑定、大量字段在多个 YAML 中重复定义。需要在最小化影响的前提下，逐步增强元模型核心能力。

## What Changes

- **Composition 组合关系**：扩展 RelationType 枚举新增 `COMPOSITION`，MetaRelation 新增 `cascade_delete`/`ownership` 属性，CascadeService 支持从 relation 定义读取级联策略
- **Authorization 声明式权限绑定**：在 YAML 对象定义中新增 `authorization` 配置节，自动为 CRUD 端点绑定权限码，利用现有 `require_permission` 装饰器
- **Shared Property 共享属性**：新增 `shared_properties.yaml` 定义共享字段组，YAML 对象通过 `includes` 引用，yaml_loader 解析时展开合并

## Impact

- Affected specs: unified-meta-model-design（对象类型扩展）、auth-permission-system（权限绑定增强）
- Affected code:
  - `meta/core/models.py` - RelationType 枚举、MetaRelation 属性、MetaObject 属性
  - `meta/core/yaml_loader.py` - 解析 composition 关系、authorization 配置、includes 引用
  - `meta/core/schema_generator.py` - 生成 SQL 时处理级联删除约束
  - `meta/services/cascade_service.py` - 支持从 relation 定义读取级联策略
  - `meta/services/manage_service.py` - 创建/删除时处理组合关系
  - `meta/api/manage_api.py` - 自动绑定权限码
  - `meta/schemas/` - 新增 shared_properties.yaml，修改现有 YAML 添加 includes/authorization
  - `src/stores/` - 前端感知组合关系

## ADDED Requirements

### Requirement: Composition 组合关系

系统 SHALL 支持在 relation 定义中标记 `type: composition`，表示子实体生命周期由父实体管理。

#### 现有实现分析

| 组件 | 现状 | 影响 |
|------|------|------|
| `RelationType` 枚举 | PARENT_CHILD / REFERENCE / MANY_TO_MANY | 新增 COMPOSITION，不影响现有 |
| `MetaRelation` 数据类 | 无 cascade_delete/ownership 属性 | 新增可选属性，默认值保持兼容 |
| `CascadeService` | 策略从 hierarchies.yaml 读取 | 新增从 relation 读取的路径，保留 hierarchies.yaml 作为 fallback |
| `hierarchies.yaml` | 所有策略为 RESTRICT | 不修改，composition 策略从 relation 定义读取 |
| `yaml_loader.py` | parse_relation() 映射 type 字段 | 扩展 RELATION_TYPE_MAP，向后兼容 |
| 前端 | 无组合关系概念 | 新增组合关系的视觉标识 |

#### Scenario: 定义组合关系
- **WHEN** 用户在 YAML 中定义 `type: composition` 的 relation
- **THEN** 系统识别该关系为组合关系，子实体生命周期由父实体管理

#### Scenario: 组合关系级联删除
- **WHEN** 用户删除拥有 composition 关系的父实体
- **AND** 该 relation 配置了 `cascade_delete: true`
- **THEN** 系统自动删除所有关联的子实体

#### Scenario: 组合关系阻止删除
- **WHEN** 用户删除拥有 composition 关系的父实体
- **AND** 该 relation 配置了 `cascade_delete: false`（默认）
- **THEN** 系统检查是否有子实体存在，有则阻止删除并提示

#### Scenario: 向后兼容
- **WHEN** 现有 YAML 中 relation 使用 `type: parent_child`
- **THEN** 行为与修改前完全一致，不自动升级为 composition

#### Scenario: 级联策略优先级
- **WHEN** relation 定义了 composition + cascade_delete
- **AND** hierarchies.yaml 也定义了该层级的 delete_behavior
- **THEN** relation 定义优先，hierarchies.yaml 作为 fallback

### Requirement: Authorization 声明式权限绑定

系统 SHALL 支持在 YAML 对象定义中声明 `authorization` 配置，自动为 CRUD 端点绑定权限码。

#### 现有实现分析

| 组件 | 现状 | 影响 |
|------|------|------|
| `require_permission` 装饰器 | 已实现，但 manage_api 中未使用 | 直接复用，无需修改 |
| `permission.yaml` | 已定义 resource_type + action 权限码 | 复用现有权限码格式 |
| `PermissionService` | has_permission() 支持通配符 | 直接复用 |
| `DataPermissionService` | 行级数据权限已实现 | 直接复用 |
| `manage_api.py` | `@_auth_required` 仅验证登录 | 扩展为支持权限码绑定 |
| `MetaObject` | 无 authorization 属性 | 新增可选属性 |
| Token | 携带 permissions 列表 | 无需修改 |

#### Scenario: 声明权限配置
- **WHEN** 用户在 YAML 中定义 `authorization: {check: true, permissions: {create: "domain:create", read: "domain:read"}}`
- **THEN** 系统自动为对应 CRUD 端点绑定权限检查

#### Scenario: 默认权限码生成
- **WHEN** 用户在 YAML 中定义 `authorization: {check: true}` 但未指定具体权限码
- **THEN** 系统自动生成 `{object_id}:{action}` 格式的权限码（如 `domain:create`）

#### Scenario: 行级权限声明
- **WHEN** 用户在 YAML 中定义 `authorization: {scope: "owner_id = $user.id"}`
- **THEN** 列表查询时自动注入行级过滤条件

#### Scenario: AUTH_ENABLED=false 时跳过
- **WHEN** 环境变量 AUTH_ENABLED 为 false
- **THEN** 所有权限检查自动跳过，与当前行为一致

#### Scenario: 向后兼容
- **WHEN** 现有 YAML 中无 authorization 配置
- **THEN** 行为与修改前完全一致（仅验证登录或跳过）

### Requirement: Shared Property 共享属性

系统 SHALL 支持定义共享字段组，YAML 对象通过 `includes` 引用，解析时自动展开合并。

#### 现有实现分析

| 组件 | 现状 | 影响 |
|------|------|------|
| YAML 字段定义 | 每个对象独立完整定义 | includes 引用后展开，不改变最终结构 |
| `parse_field()` | 逐字段独立解析 | 不修改，展开后仍走原解析流程 |
| `MetaField` 数据类 | 无来源标记 | 新增 `included_from: str` 可选属性 |
| `schema_generator.py` | 基于完整字段列表生成 SQL | 不修改，展开后字段列表完整 |
| `yaml_loader.py` | 逐文件独立加载 | 新增 includes 解析和合并逻辑 |

#### 重复字段统计

| 字段 | 重复 YAML 文件数 | 说明 |
|------|-----------------|------|
| version_id + version_name | 5 | domain, sub_domain, service_module, business_object, relationship |
| domain_id + domain_name | 3 | sub_domain, service_module, business_object |
| sub_domain_id + sub_domain_name | 2 | service_module, business_object |
| code + name | 4 | domain, sub_domain, service_module, business_object |
| created_at/updated_at/created_by/updated_by | 6+ | 所有业务对象 |
| owner_id | 4 | domain, sub_domain, service_module, business_object |

#### Scenario: 定义共享字段组
- **WHEN** 用户在 `shared_properties.yaml` 中定义字段组 `hierarchy_fields`
- **THEN** 该字段组可被任何 YAML 对象引用

#### Scenario: 引用共享字段组
- **WHEN** 用户在 domain.yaml 中定义 `includes: [hierarchy_fields, audit_fields]`
- **THEN** 解析时自动将共享字段组展开合并到对象的 fields 列表

#### Scenario: 本地字段覆盖共享字段
- **WHEN** 对象本地定义了与共享字段组同 id 的字段
- **THEN** 本地定义覆盖共享定义，并记录覆盖关系

#### Scenario: 向后兼容
- **WHEN** 现有 YAML 中无 includes 配置
- **THEN** 行为与修改前完全一致，字段列表不变

#### Scenario: 共享字段的 UI 注解
- **WHEN** 共享字段组中的字段包含 UI 注解
- **THEN** UI 注解随字段一起被引用，对象可本地覆盖

## MODIFIED Requirements

### Requirement: RelationType 枚举扩展

`RelationType` 枚举 SHALL 新增 `COMPOSITION = "composition"` 值。现有 `PARENT_CHILD`、`REFERENCE`、`MANY_TO_MANY` 保持不变。

### Requirement: MetaRelation 属性扩展

`MetaRelation` 数据类 SHALL 新增以下可选属性：

```python
cascade_delete: bool = False       # 是否级联删除
ownership: bool = False            # 是否拥有子实体生命周期
```

### Requirement: MetaObject 属性扩展

`MetaObject` 数据类 SHALL 新增以下可选属性：

```python
authorization: Optional[Dict] = None   # 权限配置
includes: List[str] = field(default_factory=list)  # 引用的共享字段组
```

### Requirement: MetaField 属性扩展

`MetaField` 数据类 SHALL 新增以下可选属性：

```python
included_from: str = ""   # 来自哪个共享字段组
```

### Requirement: CascadeService 级联策略来源扩展

`CascadeService` SHALL 支持从 relation 定义读取级联策略，优先级：relation 定义 > hierarchies.yaml > 默认 RESTRICT。

### Requirement: manage_api 权限绑定

`manage_api.py` 中的 CRUD 端点 SHALL 支持根据 MetaObject.authorization 配置自动绑定权限码。

## REMOVED Requirements

无移除的需求。所有现有功能保持向后兼容。
