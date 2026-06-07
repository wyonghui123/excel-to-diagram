---
title: 七、元数据体系
version: 3.0.2
date: 2026-06-07
status: 活跃
parent: ARCHITECTURE_V2.md
---

# 七、元数据体系

> 本章节从 [ARCHITECTURE_V2.md §七](../ARCHITECTURE_V2.md#七-元数据体系) 提取（2026-06-07 v3.0.2 拆分）
> 
> **拆分原因**：原章节 836 行/26.9KB，是 ARCHITECTURE_V2.md 最大的章节，独立成文便于维护
> 
> **同步说明**：本文件为单一事实源，主文档 §七 仅保留链接

---

## 七、元数据体系

### 7.1 YAML 元数据结构

**模板文件**: [meta/schemas/_template.yaml](meta/schemas/_template.yaml)

```yaml
# 业务对象元数据模板
name: {object_name}                    # 对象标识名
label: {显示名称}                      # 对象显示标签
table_name: {table_name}              # 数据库表名
persistent: true                       # 是否持久化
display_name_field: name              # 显示名称字段

# 导入导出配置
import_export:
  import_enabled: true
  export_enabled: true
  cascade_export: false
  cascade_import: false
  conflict_strategy: upsert
  conflict_key: code

# 字段定义
fields:
  - id: field_id
    name: 显示名称
    type: string|integer|datetime|text|boolean|enum
    description: 字段描述
    required: false

    # 存储策略
    storage: stored|virtual           # STORED=物理存储, VIRTUAL=不存储

    # 语义定义
    semantics:
      business_key: false             # 是否业务键
      computed: false                 # 是否计算字段
      computed_by: ""                 # 计算方式引用
      sensitive: false                # 是否敏感字段
      source_of_truth: ""             # 数据来源
      display_format: ""              # 显示格式（关联字段）

    # UI 配置（遵循单一事实原则，只配置例外）
    ui:
      visible: true                   # 可见性（默认true）
      editable: true                  # 可编辑性（默认true）
      readonly: false                 # 只读（默认false）
      export_visible: true            # 可导出（默认true）

    # 枚举值定义
    enum_values:
      - value: active
        label: 活跃
        color: success

    # 关联配置
    relation:
      target_object: ""
      foreign_key: ""
      display_field: ""

# 关联定义
associations:
  - id: association_id
    label: 显示名称
    type: one_to_many|many_to_many|many_to_one
    target_object: ""
    foreign_key: ""
    through: ""                        # 中间表（多对多）
    metadata_fields: []                # 关联元数据字段

    # UI 配置
    display:
      format: "{name}"                 # 显示格式
      widget: table|list|tree          # 展现控件

    ui:
      actions:                         # 支持的操作
        - assign
        - unassign
        - view

# 列表视图配置
ui_view_config:
  list:
    title: 列表标题
    selection:
      enabled: true
      mode: multiple
    columns:
      - key: field_name
        title: 列标题
        width: 120px
        default_visible: true
        sortable: true

  # 详情视图配置
  detail:
    tabs:
      - id: basic
        label: 基本信息
        fields:
          - field_name1
          - field_name2

      - id: associations
        label: 关联信息
        sections:
          - id: assoc_id
            label: 关联标题
            association: assoc_id

  # 表单视图配置
  form:
    sections:
      - id: basic
        label: 基本信息
        fields:
          - key: field_name
            widget: input|select|textarea|date-picker
            span: 12  # 栅格占用

# 工具栏操作
actions:
  - id: create
    label: 新建
    icon: plus
    type: primary

# 行级操作
row_actions:
  - id: edit
    label: 编辑
    icon: edit
  - id: delete
    label: 删除
    icon: delete
    type: danger
    confirm: 确定要删除吗？

# 批量操作
batch_actions:
  - id: batch_delete
    label: 批量删除
    icon: delete
    type: danger
    confirm: 确定要删除选中的记录吗？

# 过滤器配置
filter_fields:
  - key: keyword
    label: 关键词
    type: search
    placeholder: 请输入关键词

# 排序配置
default_ordering:
  - field: created_at
  - direction: desc

# Value Help 配置
value_help:
  type: enum|association|tree|custom
  provider: EnumVHProvider|BoVHProvider|CustomVHProvider
  parameters: {}

# 权限配置
permissions:
  create: []
  read: []
  update: []
  delete: []

# 审计配置
audit:
  enabled: true
  track_changes: true

# 状态机配置（可选）
state_machine:
  initial: draft
  states:
    - id: draft
      label: 草稿
      transitions:
        - target: active
          action: publish
    - id: active
      label: 已发布
      transitions:
        - target: archived
          action: archive
```

### 7.2 已实现元数据的业务对象（35+ 个）[v3.0 扩展]

| # | 对象 | YAML 文件 | 表名 | 状态 | 说明 |
|---|------|----------|------|------|------|
| 1 | **User** | user.yaml | users | 完成 | 用户管理 |
| 2 | **Role** | role.yaml | roles | 完成 | 角色管理 |
| 3 | **UserGroup** | user_group.yaml | user_groups | 完成 | 用户组管理 |
| 4 | **UserGroupMember** | user_group_member.yaml | user_group_members | 完成 [NEW] | 用户组成员(独立关联表) |
| 5 | **Permission** | permission.yaml | permissions | 完成 | 权限定义 |
| 6 | **DataPermission** | data_permission.yaml | data_permissions | 完成 | 数据权限 |
| 7 | **PermissionRule** | permission_rule.yaml | permission_rules | 完成 | 权限规则 |
| 8 | **MenuPermission** | menu_permission.yaml | menu_permissions | 完成 | 菜单权限 |
| 9 | **PermissionBundle** | permission_bundle.yaml | permission_bundles | 完成 | 权限包 |
| 10 | **RolePermission** | role_permission.yaml | role_permissions | 完成 [NEW] | 角色-权限直连 |
| 11 | **RoleDataPermission** | role_data_permission.yaml | role_data_permissions | 完成 [NEW] | 角色-数据权限 |
| 12 | **RoleDimensionScope** | role_dimension_scope.yaml | role_dimension_scopes | 完成 [NEW] | 角色-维度范围 |
| 13 | **GroupDataPermission** | group_data_permission.yaml | group_data_permissions | 完成 [NEW] | 用户组-数据权限 |
| 14 | **EmployeeDataScope** | employee_data_scope.yaml | employee_data_scopes | 完成 [NEW] | 员工数据范围 |
| 15 | **Domain** | domain.yaml | domains | 完成 | 领域 |
| 16 | **SubDomain** | sub_domain.yaml | sub_domains | 完成 | 子领域 |
| 17 | **Product** | product.yaml | products | 完成 | 产品 |
| 18 | **Version** | version.yaml | versions | 完成 | 版本 |
| 19 | **ServiceModule** | service_module.yaml | service_modules | 完成 | 服务模块 |
| 20 | **BusinessObject** | business_object.yaml | business_objects | 完成 | 业务对象（元模型） |
| 21 | **EnumType** | enum_type.yaml | enum_types | 完成 | 枚举类型 |
| 22 | **EnumValue** | enum_value.yaml | enum_values | 完成 | 枚举值 |
| 23 | **Relationship** | relationship.yaml | relationships | 完成 | 关系定义 |
| 24 | **Annotation** | annotation.yaml | annotations | 完成 | 注解 |
| 25 | **AuditLog** | audit_log.yaml | audit_logs | 完成 | 审计日志 |
| 26 | **Menu** | menu.yaml | menus | 完成 | 菜单 |
| 27 | **Hierarchies** | hierarchies.yaml | - | 完成 | 层级定义（元模型） |
| 28 | **Aspects** | aspects.yaml | - | 完成 | 切面定义（元模型） |
| 29 | **ChangeEvent** | change_event.yaml | change_events | 完成 | 变更事件 |
| 30 | **ChangeSubscription** | change_subscription.yaml | change_subscriptions | 完成 [NEW] | 变更订阅(WebSocket 订阅者) |
| 31 | **MetaAction** | meta_action.yaml | meta_actions | 完成 | 元动作 |
| 32 | **FilterVariant** | filter_variant.yaml | filter_variants | 完成 [NEW] | 过滤变体(用户保存的过滤器) |
| 33 | **TaskQueue** | task_queue.yaml | task_queues | 完成 [NEW] | 任务队列(§7.11) |
| 34 | **TaskExecution** | task_execution.yaml | task_executions | 完成 [NEW] | 任务执行历史(§7.11) |
| 35 | **ScheduledTask** | scheduled_task.yaml | scheduled_tasks | 完成 [NEW] | 定时任务(cron 调度)(§7.11) |
| 36 | **AiAsyncTask** | ai_async_task.yaml | ai_async_tasks | 完成 [NEW] | AI Agent 异步任务(§7.5) |

**辅助 YAML（非业务对象）**:
- `shared_properties.yaml` [NEW] — 跨 BO 共享字段定义(DRY)
- `_standard_actions.yaml` [NEW] — 12 标准动作定义(§7.5)
- `_action_groups.yaml` [NEW] — 动作按业务场景分组
- `audit_log_expectations.yaml` [NEW] — 审计日志期望(声明式合规)
- `_template.yaml` — YAML 模板

### 7.3 元数据验证与同步

**Schema 同步工具**: [meta/tools/sync_schema.py](meta/tools/sync_schema.py)

```bash
# 查看变更差异
python -m meta.tools.sync_schema --diff

# 预览 SQL（不执行）
python -m meta.tools.sync_schema --dry-run

# 执行同步
python -m meta.tools.sync_schema --execute

# 运行测试验证
python meta/tests/run_all_tests.py
```

**启动时验证**：

```python
from meta.core.metadata_validator import MetadataValidator

def validate_metadata_on_startup():
    validator = MetadataValidator()
    result = validator.validate_all()
    validator.log_results()

    if not result['valid']:
        logger.warning("[Startup] Metadata validation failed")
```

### 7.4 ValueHelp 五层架构

**设计模式**: BRIDGE（将「数据来源」与「呈现方式」解耦）

ValueHelp 不是简单的下拉框——它是一个**五层解耦架构**，将数据来源（Source）、业务行为（Behavior）、参数映射（In/Out Mapping）、后端 Provider 和前端呈现（Presentation）完全分离：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ValueHelp 五层架构                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 1: Source（数据来源）— YAML 声明                              │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │   source:                                                     │ │
│  │     type: bo                   # bo | enum | tree | custom    │ │
│  │     target_bo: domain          # 目标业务对象（bo 类型）       │ │
│  │     value_field: id            # 值字段                        │ │
│  │     display_field: name        # 显示字段                      │ │
│  │     code_field: code           # 编码字段                      │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  Layer 2: Behavior（业务行为）— YAML 声明                             │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │   behavior:                                                   │ │
│  │     binding_strength: strict   # strict | loose               │ │
│  │     search_fields: [name, code]# 搜索字段                      │ │
│  │     min_search_length: 0       # 最小搜索长度                  │ │
│  │     debounce_ms: 300           # 防抖延迟                      │ │
│  │     multiple: false            # 多选模式                      │ │
│  │     enabled_condition: ""      # 启用条件表达式                │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  Layer 3: In/Out Mapping（参数映射）— 🆕 双向数据绑定                │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │   parameter_bindings:           # In Mapping（表单 → VH 请求）  │ │
│  │     - local_field: version_id                                  │ │
│  │       target_field: version_id                                 │ │
│  │       required: true                                           │ │
│  │   out_mappings:                 # 🆕 Out Mapping（VH 结果 → 表单）│ │
│  │     - value_help_field: name                                   │ │
│  │       local_field: domain_name                                 │ │
│  │     - value_help_field: code                                   │ │
│  │       local_field: domain_code                                 │ │
│  │   cascade_select:               # 🆕 级联选择语法糖              │ │
│  │     - parent_field: domain_id                                  │ │
│  │       child_field: sub_domain_id                               │ │
│  │       cascade_source: sub_domain                               │ │
│  │       cascade_field: domain_id                                 │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  Layer 4: Provider（后端桥接）— 自动路由                              │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  EnumVHProvider    → 枚举静态值                                 │ │
│  │  BoVHProvider      → 业务对象动态查询（支持 in/out mapping）     │ │
│  │  TreeVHProvider    → 层级树结构                                 │ │
│  │  CustomVHProvider  → 自定义端点                                 │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  Layer 5: Presentation（前端渲染）— 自动推导                          │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  ValueHelpField.vue  → 搜索帮助字段（dropdown/dialog/autocomplete）│ │
│  │  SearchHelpDialog.vue → 搜索帮助对话框                          │ │
│  │  CascadeSelect       → 级联下拉（cascade_select 语法糖驱动）     │ │
│  │  EnumSelect.vue      → 枚举单选/多选                            │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### In/Out Mapping 对称设计

```
  In Mapping (parameter_bindings)                Out Mapping (out_mappings)
  ┌──────────┐    搜索请求参数    ┌──────────────┐    ┌──────────────┐    自动回填       ┌──────────┐
  │ 表单字段  │ ────────────────→ │ ValueHelp API │    │ ValueHelp 结果 │ ────────────────→ │ 表单字段  │
  │ local_field│  target_field   │  查询参数     │ →  │ extra 字段    │  value_help_field │ local_field│
  └──────────┘                   └──────────────┘    └──────────────┘                    └──────────┘
  
  SAP 对标: @Consumption.valueHelpDefinition + @ObjectModel.resultElement
```

| 维度 | In Mapping | Out Mapping |
|------|-----------|-------------|
| 方向 | 表单 → VH 请求 | VH 结果 → 表单 |
| 触发时机 | 打开/搜索 VH 时 | 选择 VH 项时 |
| 源字段 | `local_field`（表单字段名） | `value_help_field`（结果字段名） |
| 目标字段 | `target_field`（API 参数名） | `local_field`（表单字段名） |

#### CascadeSelectConfig — parameter_bindings 的声明式语法糖

`cascade_select` 配置在 YAML 层面提供更直观的级联选择配置，由 `yaml_loader.py` **自动展开**为 `parameter_bindings`，保持向后兼容：

```yaml
# 声明式写法
behavior:
  cascade_select:
    - parent_field: domain_id
      child_field: sub_domain_id
      cascade_source: sub_domain
      cascade_field: domain_id
      required: false

# 自动展开等价于
behavior:
  parameter_bindings:
    - local_field: sub_domain_id
      target_field: domain_id
      required: false
```

**Provider 注册机制**: 前端 `useValueHelp.js` 根据 `value_help.type` 自动选择正确的 Provider，`applyOutMappings()` 在选择后自动将结果中的 `extra` 字段值回填到表单。

#### 数据模型

```python
# meta/core/models.py

@dataclass
class ValueHelpOutMapping:
    value_help_field: str = ""   # ValueHelp 结果中的字段名
    local_field: str = ""        # 表单/实体中的字段名

@dataclass
class CascadeSelectConfig:
    parent_field: str = ""       # 父字段名
    child_field: str = ""        # 子字段名
    cascade_source: str = ""     # 级联数据源（BO 名）
    cascade_field: str = ""      # 级联过滤字段
    required: bool = False

@dataclass
class ValueHelpBehavior:
    # ... 现有字段 ...
    out_mappings: List[ValueHelpOutMapping] = field(default_factory=list)
    cascade_select: List[CascadeSelectConfig] = field(default_factory=list)
```

### 7.5 MetaAction → Tool Schema（AI Agent 基础设施）[v3.0 已实现]

**代码位置**: [meta/core/action_executor.py](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py), [meta/core/standard_action_loader.py](file:///d:/filework/excel-to-diagram/meta/core/standard_action_loader.py), [meta/services/action_handlers.py](file:///d:/filework/excel-to-diagram/meta/services/action_handlers.py), [meta/services/action_policy.py](file:///d:/filework/excel-to-diagram/meta/services/action_policy.py), YAML: `meta_actions.yaml` + `_standard_actions.yaml` + `_action_groups.yaml`

系统通过 `MetaAction` 对象定义操作契约。在 AI Agent 场景下，这些 Action 可以自动转换为 LLM 的 **Function Calling Tool Schema**：

```
YAML（MetaAction 定义）:
  - id: create_emergency_order
    name: 创建紧急订单
    handler: create_order_handler
    parameters:
      - name: part_number
        type: string
        required: true
      - name: quantity
        type: integer
        required: true
      - name: supplier
        type: string
        required: true
    preconditions:
      - "user.role in ['buyer', 'manager']"
      - "inventory.get(part_number).stock < threshold"
    side_effects:
      - "notify(warehouse_manager)"
      - "audit_log('EMERGENCY_ORDER')"

         │
         ▼  ActionExecutor 自动转换
         
LLM Tool Schema (OpenAI Function Calling 格式):
  {
    "name": "create_emergency_order",
    "description": "创建紧急订单",
    "parameters": { ... },
    "required_permissions": ["buyer", "manager"],
    "pre_checks": ["stock < threshold"]
  }
```

**[NEW] 12 标准动作** (v3.0 已实现,定义在 `_standard_actions.yaml`):

| # | Action ID | 名称 | 用途 | Handler |
|---|-----------|------|------|---------|
| 1 | `list` | 列表查询 | 通用列表 | `bo_api.list` |
| 2 | `get` | 详情查询 | 单条记录 | `bo_api.get` |
| 3 | `create` | 创建 | 通用创建 | `bo_api.create` |
| 4 | `update` | 更新 | 通用更新 | `bo_api.update` |
| 5 | `delete` | 删除 | 通用删除 | `bo_api.delete` |
| 6 | `bulk_create` | 批量创建 | 导入场景 | `bo_api.bulk_create` |
| 7 | `bulk_update` | 批量更新 | 批量操作 | `bo_api.bulk_update` |
| 8 | `bulk_delete` | 批量删除 | 批量操作 | `bo_api.bulk_delete` |
| 9 | `recover` | 恢复 | 从 audit_log 恢复 | `deletion_service.recover_from_log` |
| 10 | `clone` | 克隆 | 复制记录 | `clone_handler` |
| 11 | `export` | 导出 | Excel 导出 | `import_export_service.export` |
| 12 | `import` | 导入 | Excel 导入 | `import_export_service.import` |

**[NEW] 动作分组** (v3.0,定义在 `_action_groups.yaml`):
- `user_management` — 用户管理类(创建/更新/删除/重置密码)
- `role_management` — 角色管理类
- `permission_management` — 权限管理类
- `data_lifecycle` — 数据生命周期(create/update/delete/recover)
- `batch_operations` — 批量操作
- `import_export` — 导入导出
- `audit_recovery` — 审计与恢复

**关键组件**:
- [action_executor.py](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py) — 统一执行器
- [standard_action_loader.py](file:///d:/filework/excel-to-diagram/meta/core/standard_action_loader.py) — 标准动作加载器(FACTORY 模式)
- [action_handlers.py](file:///d:/filework/excel-to-diagram/meta/services/action_handlers.py) — handler 注册表
- [action_policy.py](file:///d:/filework/excel-to-diagram/meta/services/action_policy.py) — 策略(POLICY 模式:谁能执行什么)

**设计要点**:
- **Action Types 已实现** — v2.x 文档说"待设计",v3.0 实际已完成
- AI Agent 通过 API 查询可执行操作列表（运行时自省）
- 前置条件（preconditions）依赖运行时数据，需要实时求值
- 副作用（side_effects）定义了操作的安全边界
- **ai_async_task** BO 专门承载 AI Agent 触发的异步任务(支持轮询/取消)

### 7.6 KeyTemplate 编码引擎

声明式编码模板引擎，自动为业务对象生成唯一 code。引擎定义在 YAML，模板值存储在 DB。

**YAML（引擎定义，唯一来源）**:
```yaml
key_template:
  enabled: true
  auto_suggest: true       # 自动建议但用户可变更
  auto_detect: true        # 存量数据自动检测最大序号
  segments:
    - type: parent_field
      source: service_module_code
    - type: separator
      value: "_"
    - type: sequence
      length: 4
```

**DB config_values（配置值，唯一来源）**:
```json
{
  "config_key": "key_template.business_object",
  "config_value": {"pattern": "{service_module_code}_{SEQ:4}"}
}
```

**启用对象**:

| 对象 | 模板示例 | 说明 |
|------|---------|------|
| **BusinessObject** | `ORDER_SVC_0001` | `{service_module_code}_{SEQ:4}` |
| **Version** | `SCM_01` | `{product_code}_{SEQ:2}` |
| **Relationship** | `PUM07-PUM14-01` | `{source_code}-{target_code}-{SEQ:2}` |
| product/domain/sub_domain/service_module/role/user_group | — | 不需要编码模板 |

**存量数据处理**: `auto_detect: true` 扫描现有 code，从 MAX(已有序号) + 1 开始。

### 7.7 Record Type：配置级核心承载体

Record Type 是 Tier 2（配置级）的核心概念——它把 KeyTemplate、Field Visibility、Validation、UI Layout、State Machine **打包**成不同的业务视角，实现在**同一张物理表**上呈现**不同业务表单**。

```
同一张 business_object 表:

Record Type "purchase_order":
  key_template:    "PO_{service_module_code}_{SEQ:5}"
  field_visibility: vendor_code(required), contract_term(hidden)
  validations:     [{rule: "amount > 0", severity: "error"}]
  ui_layout:       purchase_order_form_v1

Record Type "contract":
  key_template:    "CON_{service_module_code}_{SEQ:4}"
  field_visibility: contract_term(required), vendor_code(hidden)
  validations:     [{rule: "start_date < end_date", severity: "error"}]
  ui_layout:       contract_form_v1
```

**行业对标**:
- **Salesforce Record Type**: 不同 Picklist 值集 + Page Layout
- **SAP Document Type**: NB/MK/LPA 决定号码范围 + 字段状态组
- **我们的 Record Type**: YAML(结构) + config_values(配置组合) 的分工方案

### 7.8 三层配置分层模型

基于 Salesforce/SAP/ServiceNow/Kubernetes/Palantir 五家头部产品的深度研究，确立三层配置分层：

| 层级 | 谁操作 | 影响范围 | 变更方式 | 是否需要 ALTER TABLE |
|------|--------|----------|----------|:---:|
| **Tier 1 开发级** | 开发者 | 全局 | Git + CI/CD 部署 | 部分需要 |
| **Tier 2 配置级** | 关键用户/顾问 | 全局或按 Record Type | Web UI + DB（唯一来源） | **不需要** |
| **Tier 3 个性化级** | 最终用户 | 仅自己 | 前端 + 个人偏好存储 | 不需要 |

```
Tier 1 (开发级): YAML — Schema结构 · 引擎定义 · KeyTemplate引擎 · 关系/关联
Tier 2 (配置级): config_values DB — 配置值 · Record Type · UI布局 · 校验规则 · virtual字段公式
Tier 3 (个性化级): User Preferences DB — 个人筛选 · 列表视图 · 仪表盘
```

### 7.9 YAML 模板完整要素清单

基于 `_template.yaml` 和实际 `meta_actions.yaml` / `business_object.yaml` 等文件的完整要素：

```
业务对象元数据:
  name · label · table_name · persistent · display_name_field
  import_export (import_enabled/export_enabled/cascade_*/conflict_*)

字段定义 (fields[]):
  id · name · type · description · required · nullable · default · max_length
  storage: stored | virtual
  semantics: business_key · computed · computed_by · sensitive · source_of_truth · display_format
  ui: visible · editable · readonly · export_visible · hidden_in_list · hidden_in_detail · hidden_in_form
  enum_values[] / relation{} / validations[]

关联定义 (associations[]):
  id · label · type · target_object · foreign_key · through · metadata_fields[]
  display: format · widget
  ui: actions (assign/unassign/view)

视图配置:
  ui_view_config:
    list: title · selection · columns[] · default_ordering
    detail: tabs[] · sections[] · fields[]
    form: sections[] · fields[] · widget · span

操作定义:
  actions[] · row_actions[] · batch_actions[]
  (每项含: id · label · icon · type · confirm · visible_when)

过滤与排序:
  filter_fields[] · default_ordering[] · filter_sources[]

高级能力:
  value_help: type · provider · parameters · cascade_from
  key_template: enabled · auto_suggest · auto_detect · segments[]
  state_machine: initial · states[] · transitions[]
  audit: enabled · track_changes · retention_days
  permissions: create · read · update · delete
  authorization: auto_owner · auto_permission
  computation: formula · triggers · dependencies
  derivation: conditions · target_field · formula
```

### 7.10 菜单自动生成与动态路由架构（Phase 21 交付）

菜单不再是手动配置的——它由 **YAML 声明 + 自动推导 + 缓存容错** 三层机制驱动。

**后端：MenuAutoGenerator（BUILDER + VISITOR 模式）**

```
输入: 所有 BO YAML 的 bo_bindings 声明
   │
   ├→ 1. 遍历 YAML: 读取每个对象的 bo_bindings.app_group / menu_label / icon / order
   ├→ 2. 过滤: 排除 ui_view_config.skip_auto_menu = true 的对象（FR-003 元数据化）
   ├→ 3. 分组: 按 app_group 归类 → System Management / Architecture Data / ...
   ├→ 4. 排序: 按 order 字段排序，无 order 的按字母序
   ├→ 5. 权限: 从 YAML required_permissions 推导菜单权限
   └→ 6. 输出: 完整菜单树 JSON → REST API → 前端

YAML 声明示例:
  bo_bindings:
    - app_group: "system_management"    # 菜单分组
      menu_label: "用户管理"            # 显示名称
      menu_icon: "user"                 # 图标
      menu_order: 10                    # 排序
      page_type: "object_list"          # 页面类型
      primary_object_type: "user"       # 主对象
      required_permissions: ["user.read"] # 权限要求
```

**前端：dynamicRoutes.js — 菜单驱动的路由注册**

```
菜单 API 响应 (JSON)           dynamicRoutes.js 处理                Vue Router
══════════════════             ═══════════════════                  ═══════════
                                                                    
[{                             1. 按 parent_id 构建菜单树          router.addRoute({
  id: 1,                       2. page_type 决定路由路径:              path: '/objects/user',
  parent_id: null,                object_list → /objects/:type        component: MetaListPage,
  page_type: 'object_list',    3. 提取 required_permissions           meta: { permissions: [...] }
  primary_object_type: 'user',    → router.beforeEach 守卫          })
  ...
}]                             4. API 故障时:
                                  localStorage 缓存恢复
                                  (FR-004 Fallback 缓存化)            
```

**声明式授权闭环**（Phase 21 架构核心）

```
        ┌─────────────────────────────────────────────────┐
        │              YAML 声明（单一来源）                 │
        │  authorization.auto_owner: true                 │
        │  authorization.auto_permission: [{role, perm}]  │
        │  bo_bindings.required_permissions: [...]        │
        └──────────────────┬──────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   DataPermissionGenerator  MenuAutoGenerator   dynamicRoutes.js
   (拦截器链触发创建)       (API调用触发生成)    (前端启动时加载)
          │                │                │
          ▼                ▼                ▼
   data_permissions 表    menus 表          Vue Router routes[]
          │                │                │
          └────────────────┼────────────────┘
                           ▼
              PermissionSyncService (定期巡检)
              ← detect YAML vs DB 差异
              ← auto_repair() 修复不一致
```

这个架构的关键意义：
- **YAML 是唯一的声明源**：不再有分散在代码中的权限判断、菜单定义、路由映射
- **拦截器链是执行管道**：`OwnerAutoPermissionInterceptor`(96) 在 after_action 触发 `DataPermissionGenerator`，无缝融入现有请求链路
- **RECONCILIATION 是保障**：`PermissionSyncService` 持续校验 YAML 声明与 DB 实际状态的一致性，类似 K8s Controller 的 reconcile loop
- **缓存是容错手段**：菜单 API 失败时，前端从 localStorage 恢复上次成功的菜单数据，而非退化到硬编码 fallback

#### 路由路径统一解析（Phase 19 FR-010 交付）

`routeTemplate.js` 统一了原先分散在两处 `switch(page_type)` 中的路由路径生成逻辑：

```
menu.yaml（page_type 枚举新增 route_template）:
  object_list:       "/objects/{primary_object_type}"
  object_detail:     "/objects/{primary_object_type}/{id}"
  multi_object_hub:  "/{menu_code}"
  custom_page:       "/{menu_code}"
  dashboard:         "/{menu_code}"
         │
         ▼
routeTemplate.js resolveRoutePath(menu):
  1. menu.menu_path 已存在 → 直接使用（向后兼容）
  2. menu.route_template 已配置 → 模板变量替换
     {primary_object_type} → menu.primary_object_type
     {menu_code} → menu.menu_code
     {id} → :id
  3. 无 template → 内置默认模板（与 YAML 定义一致）
  4. 统一 replace(/_/g, '-') 下划线替换

调用方（两处统一）:
  AppRootLayout.vue  → menu.menu_path || resolveRoutePath(menu)
  dynamicRoutes.js   → resolveRoutePath(menu)
```

**设计要点**：
- **消除双重不一致**：原 `deriveRoutePath`（不做下划线替换）和 `_resolvePath`（做下划线替换）default 分支行为不同，现统一
- **向后兼容**：存量 menu 记录无 `route_template` 字段时，使用内置默认模板（行为与原 switch 一致）
- **YAML 声明式扩展**：新增 `page_type` 只需在 menu.yaml 枚举中加一行 `route_template`，无需改 JS 代码

---

### 7.11 任务调度子系统 [NEW v3.0]

> **背景**: v2.x 文档"远期规划"提到"audit_log Formula（日志老化计算）",v3.0 已落地为**完整的任务调度三件套**。

#### 7.11.1 三个业务对象

| BO | YAML | 作用 | 关键字段 |
|----|------|------|---------|
| **TaskQueue** | `task_queue.yaml` | 任务队列(可入队/出队/优先级) | `queue_name`, `priority`, `status`, `payload` |
| **TaskExecution** | `task_execution.yaml` | 任务执行历史(全量审计) | `task_id`, `started_at`, `finished_at`, `result`, `error` |
| **ScheduledTask** | `scheduled_task.yaml` | 定时任务(cron 调度) | `cron_expression`, `next_run_at`, `handler`, `enabled` |

#### 7.11.2 调度架构

```
ScheduledTask (cron 表达式)
        ↓
  cron_parser 解析 (标准 5/6 字段格式)
        ↓
  调度器循环 (30s 一次) → 找出 next_run_at <= now 的任务
        ↓
  TaskQueue 入队
        ↓
  Worker 进程 (多并发,默认 4)
        ↓
  执行 handler (同步 or 异步)
        ↓
  写 TaskExecution
        ↓
  Update next_run_at
```

#### 7.11.3 关键能力

| 能力 | 实现 | 测试 |
|------|------|------|
| Cron 解析 | `cron_parser.py` (标准格式 + 区间 + 列表) | 单元测试覆盖 |
| 队列持久化 | `task_queue` BO + BOFramework 拦截器链 | 集成测试 |
| 失败重试 | `max_retries` + 指数退避 | 单元测试 |
| 超时控制 | `timeout_seconds` + worker kill | 单元测试 |
| 分布式锁 | Redis SETNX(防多实例重复执行) | 集成测试 |
| 监控指标 | 队列深度/成功率/P99 延迟 | Prometheus 导出 |

#### 7.11.4 典型使用场景

- **审计日志老化**: ScheduledTask → 每天 02:00 → 删除 365 天前 audit_log
- **数据备份**: ScheduledTask → 每 6h → 触发 DB backup API
- **批量同步**: ScheduledTask → 每 15min → 从外部系统拉取数据
- **AI Agent 异步任务**: `ai_async_task` BO + TaskQueue 协同(AI 长任务)

---

### 7.12 辅助 YAML 与声明式合规 [NEW v3.0]

#### 7.12.1 `shared_properties.yaml` — 共享属性 (DRY)

```yaml
# meta/schemas/shared_properties.yaml
shared_properties:
  audit_fields:           # 审计 5 字段(可被任意 BO 引用)
    - created_at: timestamp, default=now()
    - created_by: fk(user)
    - updated_at: timestamp, default=now(), onupdate=now()
    - updated_by: fk(user)
    - version: int, default=1
  ownership_fields:       # 所有者字段
    - owner_id: fk(user)
    - owner_group_id: fk(user_group)
  status_fields:          # 状态字段
    - status: enum(active,inactive,archived)
    - is_deleted: bool, default=false
```

**YAML 引用方式**:
```yaml
id: business_object
aspects: [audit_fields, ownership_fields, status_fields]  # 引用 shared
```

**价值**: 减少 50%+ 重复字段定义,保证跨 BO 行为一致。

#### 7.12.2 `audit_log_expectations.yaml` — 审计期望(声明式合规)

```yaml
# meta/schemas/audit_log_expectations.yaml
audit_expectations:
  - entity: user
    operations: [CREATE, UPDATE, DELETE]
    required_fields: [actor_id, trace_id, ip_address]
  - entity: role
    operations: [CREATE, UPDATE, DELETE, ASSIGN, REVOKE]
    required_fields: [actor_id, trace_id, ip_address, target_user_id]
  - entity: data_permission
    operations: [CREATE, UPDATE, DELETE]
    sensitivity: high  # 触发 P1 告警
    required_fields: [actor_id, trace_id, ip_address, reason]
```

**验证机制**:
- CI 阶段: `tools/validate_audit_expectations.py` 解析 YAML + 扫描实际 audit_log → 报警
- 运行时: `AuditInterceptor` 在 after_action 检查是否写入必需字段
- 缺失字段 → 阻断写入(高敏场景) / 警告日志(低敏场景)

**价值**: 把"哪些操作必须审计"从代码注释提升为**可执行的合规契约**。

#### 7.12.3 `_action_groups.yaml` — 动作分组

见 §7.5 — 把 12 个标准动作按业务场景(user_management / role_management / ...)分组,UI 按分组动态显示工具栏。

---