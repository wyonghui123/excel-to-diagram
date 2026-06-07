# MetaAction 权限体系深度分析与设计方案

> 日期：2026-05-26
> 状态：研究分析完成，方案设计阶段
> 前置阅读：[权限体系_单一事实源补充分析.md](./permission-ssot-analysis.md) | [方案设计_元数据驱动权限体系.md](./permission-metadata-driven-solution.md)

---

## 目录

1. [权限体系全景架构](#一-权限体系全景架构)
2. [MetaAction 表的定位与现状诊断](#二metaaction-表的定位与现状诊断)
3. [头部产品权限模型对标研究](#三-头部产品权限模型对标研究)
4. [MetaAction vs 枚举模型承载分析](#四metaaction-vs-枚举模型承载分析)
5. [MetaAction 的单一事实源角色分析](#五metaaction-的单一事实源角色分析)
6. [业务 Action 的 input/output 参数模型设计](#六-业务-action-的-inputoutput-参数模型设计)
7. [执行链路全景](#七-执行链路全景)
8. [改进建议与 Roadmap](#八-改进建议与-roadmap)

---

## 一、权限体系全景架构

### 1.1 三层权限模型

系统采用 **功能权限 (RBAC) + 数据权限 (Data Permission) + 菜单权限 (Menu Permission)** 三层架构：

```
                           用户 (users)
                              |
          +-------------------+-------------------+
          |                   |                   |
    直接分配              角色分配             用户组继承
          |              (user_roles)      (user_group_members
          |                   |              -> group_roles)
          v                   v                   v
+------------------------------------------------------------------+
|                    第三层：菜单权限                                |
|  决定"能看到哪些页面和菜单"                                        |
|  menu_permissions -> role_menu_permissions                       |
|  menus 导航表（含 bo_bindings + required_permissions）            |
+------------------------------------------------------------------+
                                   |
+----------------------------------v----------------------------------+
|                       第二层：功能权限 (RBAC)                       |
|  决定"能执行什么操作"                                               |
|  permissions -> role_permissions                                  |
|  权限编码格式: {resource_type}:{action_code}                       |
|  例: domain:create,  user:read,  enum_type:delete                 |
+----------------------------------v----------------------------------+
|                       第一层：数据权限                              |
|  决定"能访问哪些数据行"                                             |
|  data_permissions / role_data_permissions                          |
|  permission_rules (条件型动态规则)                                  |
|  DataPermissionInterceptor 透明注入 SQL 过滤条件                    |
+-------------------------------------------------------------------+
```

### 1.2 权限相关数据表

| 序号 | 表名 | 说明 | 类型 |
|------|------|------|------|
| 1 | `users` | 系统用户，含认证信息 | 主体 |
| 2 | `roles` | 系统角色，RBAC 核心 | 主体 |
| 3 | `user_groups` | 用户组（组织单元） | 主体 |
| 4 | `user_group_members` | 用户-用户组关系 | 关联 |
| 5 | `user_roles` | 用户-角色关系 | 关联 |
| 6 | `group_roles` | 用户组-角色关系 | 关联 |
| 7 | `permissions` | 功能权限定义 | 定义 |
| 8 | `role_permissions` | 角色-功能权限关系 | 关联 |
| 9 | `data_permissions` | 用户数据权限（实例级） | 数据安全 |
| 10 | `role_data_permissions` | 角色数据权限（实例级） | 数据安全 |
| 11 | `permission_rules` | 条件型权限规则 | 数据安全 |
| 12 | `role_dimension_scopes` | 角色维度范围声明 | 数据安全 |
| 13 | `management_dimensions` | 管理维度定义 | 元数据 |
| 14 | `meta_actions` | 服务动作定义 | 元数据 |
| 15 | `menu_permissions` | 菜单权限配置 | 菜单 |
| 16 | `menus` | 菜单导航表 | 菜单 |
| 17 | `permission_bundles` | 权限包（预定义组合） | 配置 |
| 18 | `role_menu_permissions` | 角色-菜单关系 | 关联 |

### 1.3 权限生产与消费链路

```
[生产者链路]                                [消费者链路]

BO YAML actions[]                          用户请求
  |                                           |
  +-> PermissionSyncService                 auth_middleware.py
  |     .sync_all()                         @login_required / is_admin()
  |        |                                   |
  |        +-> _derive_from_object()         +-> 功能权限检查
  |             使用 MetaAction                |   PermissionService
  |             .ACTION_SUFFIX_MAP             |   .has_permission()
  |             (仅4个硬编码映射)               |
  |                |                         +-> 数据权限过滤
  |                +-> 生成 permissions 行     |   DataPermissionInterceptor
  |                                            |   (注入 SQL WHERE)
  +------------------------------------+       |
                                       |     +-> Owner 自动授权
                          permissions 表      |   OwnerAutoPermissionInterceptor
                                       |     |   (创建后自动加 admin)
                                       |       |
                          meta_actions 表     +-> 菜单权限过滤
                          (未接入生产链路)       |   MenuPermissionService
                                              |   (可见性检查)
                                              |
                                              +-> 前端权限检查
                                                  useMetaList._checkPermission()
                                                  -> return true (空桩)
```

### 1.4 权限服务层全景

| 服务 | 文件 | 核心职责 |
|------|------|---------|
| `PermissionService` | `meta/services/permission_service.py` | 功能权限 CRUD、统一语义权限检查 |
| `DataPermissionService` | `meta/services/data_permission_service.py` | 实例级数据访问控制、权限级别计算 |
| `ConditionPermissionService` | `meta/services/condition_permission_service.py` | 条件型动态权限规则、维度匹配 |
| `MenuPermissionService` | `meta/services/menu_permission_service.py` | 菜单可见性检查、权限报告 |
| `PermissionSyncService` | `meta/services/permission_sync_service.py` | YAML -> DB 权限自动同步 |
| `PermissionBundleService` | `meta/services/permission_bundle_service.py` | 权限包一键分配 |
| `PermissionAuditService` | `meta/services/permission_audit_service.py` | 权限变更审计、孤儿权限检测 |
| `DataPermissionFilter` | `meta/services/data_permission_filter.py` | 查询层 SQL 条件注入 |
| `DataPermissionGenerator` | `meta/services/data_permission_generator.py` | 创建后自动授予创建者权限 |

---

## 二、MetaAction 表的定位与现状诊断

### 2.1 表结构与 YAML 定义

**数据库表** (`generated_schema.sql`):

```sql
CREATE TABLE IF NOT EXISTS meta_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    action_type VARCHAR(200),     -- crud / batch / business / custom
    method VARCHAR(200),           -- GET / POST / PUT / DELETE
    description TEXT,
    created_at DATETIME
)
```

**permissions 表的外键**:

```sql
CREATE TABLE IF NOT EXISTS permissions (
    ...
    action_id INTEGER,              -- FK -> meta_actions.id
    action_code VARCHAR(200),       -- 冗余存储 meta_actions.code
    ...
)
```

**YAML Schema** (`meta/schemas/meta_action.yaml`):

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | string | 动作编码（business_key, immutable） |
| `name` | string | 动作显示名称 |
| `action_type` | string | crud / batch / business / custom |
| `method` | string | HTTP 方法 GET/POST/PUT/DELETE |
| `description` | text | 描述 |

**关键发现**: `relations: []` 和 `actions: []` 均为空。这意味着对 permissions 的 FK 关系仅在 DB 层存在，YAML 层未声明。

### 2.2 种子数据（9条标准动作）

```python
# meta/scripts/migrate_permission_unified_semantic.py
standard_actions = [
    ('create',  '创建', 'crud',     'POST', '创建资源'),
    ('read',    '读取', 'crud',     'GET',  '读取资源'),
    ('update',  '更新', 'crud',     'PUT',  '更新资源'),
    ('delete',  '删除', 'crud',     'DELETE','删除资源'),
    ('export',  '导出', 'batch',    'GET',  '导出资源'),
    ('import',  '导入', 'batch',    'POST', '导入资源'),
    ('approve', '审批', 'business', 'POST', '审批操作'),
    ('list',    '列表', 'crud',     'GET',  '列表查询'),
    ('search',  '搜索', 'crud',     'GET',  '搜索查询'),
]
```

缺失的动作: `assign` / `revoke` / `manage`。

### 2.3 当前状态诊断

```
meta_actions 表
|
+-- [已完成] CREATE TABLE                         OK
+-- [已完成] 种子数据 (9条)                        OK
+-- [已完成] CRUD API (/api/v1/meta-actions)       OK
+-- [已完成] PermissionService 校验时查询           OK
|
+-- [缺失] YAML relations: []                      - 无关联声明
+-- [缺失] BO Framework 不查表校验                 - 非法 action 可传入
+-- [缺失] ACTION_SUFFIX_MAP 只有 4/9              - 缺少5个标准动作映射
+-- [缺失] PermissionSync 不读此表                  - 关键断裂点
+-- [缺失] 前端完全不查此表                         - 完全硬编码
+-- [缺失] 缺少 assign/revoke/manage 种子数据       - 无法创建这些权限
+-- [缺失] authStore.hasPermission() 不存在         - 运行时缺陷
+-- [缺失] _checkPermission 是空桩                  - 操作级权限不生效
```

### 2.4 核心断裂点：四条互不相通的"动作定义"路径

系统中存在 4 条互不相通的"动作定义"路径：

| 路径 | 位置 | 示例 |
|------|------|------|
| **路径A**: YAML actions[] | BO 的 YAML 文件 | `id: crud_create, type: crud` |
| **路径B**: meta_actions 表 | SQLite 数据库 | `code: 'create', action_type: 'crud'` |
| **路径C**: 硬编码字符串 | 前端组件 + 后端服务 | `actionIcons = { update: Edit, delete: Delete }` |
| **路径D**: ACTION_SUFFIX_MAP | models.py 类变量 | `{'crud_create': 'create', ...}` (仅4个) |

**这意味着：要新增一个动作，可能需要改 4 个地方。**

---

## 三、头部产品权限模型对标研究

### 3.1 五大产品核心对比

| 维度 | AWS IAM | Google Cloud IAM | SAP BTP/CAP | Kubernetes RBAC | 本项目 |
|------|---------|------------------|-------------|-----------------|--------|
| **权限原子** | Statement (Effect+Action+Resource) | Permission (`service.resource.verb`) | `@requires`/`@restrict` 注解 | Rule (apiGroups+resources+verbs) | Permission (`resource_type:action`) |
| **动作命名** | `s3:GetObject` | `storage.objects.get` | 注解隐式 | `get pods` | `domain:create` |
| **动作注册表** | 分服务 Authorization Reference | 集中 Permissions Reference (~4000+) | CDS 模型内聚 | 固定 8 标准 Verb | `meta_actions` 表 (未充分使用) |
| **单一事实源** | IAM Policy JSON 文档 | IAM Policy | CDS 模型文件 | Role/ClusterRole YAML | **分散**: YAML + 硬编码 + 种子 + 配置 |
| **条件/ABAC** | Condition Keys | CEL 表达式 | `$user` 占位符 + WHERE | 无原生 | `ConditionEvaluator` + `permission_rules` |
| **权限继承** | SCP -> Boundary -> Policy | Org -> Folder -> Project | Role Template -> Collection | ClusterRole ns 引用 | user -> user_roles -> group_roles |

### 3.2 关键启示

**启示1: 动作注册表是权限系统的基石。**
K8s 仅 8 个 Verb 但通过子资源机制和 CRD 扩展实现灵活权限。AWS/GCP 支持数千服务数万 API，正因有完善的动作注册表/权限参考系统。

**启示2: 各产品动作定义的存放方式不同，但都不放入通用配置系统。**
K8s 放在源码常量中，AWS 分服务独立注册，GCP 集中式管理，SAP CAP 在 CDS 模型注解中。**没有一家将操作定义放入通用枚举/标签/配置表。**

**启示3: 所有产品的动作定义本质都是元数据。**
但它们在"是否将元数据同步为结构化数据"这一点上分道扬镳。K8s 和 CAP 纯元数据运行时解释；本项目通过 `PermissionSyncService` 将元数据物化为 `permissions` 表的结构数据——这是本项目最独特的设计。

### 3.3 动作注册表设计权衡

| 系统 | 固定枚举 vs 动态 | 集中 vs 分散 | 命名规范 | 业务可自定义 |
|------|-----------------|-------------|---------|------------|
| **K8s** | 固定 8 动词 | 源码集中 | 小写单字: `get` | 否 |
| **AWS IAM** | 动态注册 | 分服务自治 | `service:VerbNoun` | 否 |
| **GCP IAM** | 动态注册 | 集中式 | `service.resource.verb` | 否 |
| **SAP CAP** | 注解模式 | 模型散布 | CDS 注解值 | 部分 |
| **本项目** | YAML actions -> DB | 集中 YAML | `object:action` | 是 |

---

## 四、MetaAction vs 枚举模型承载分析

### 4.1 问题的由来

`meta_actions` 和 `enum_value` 在"数据形状"上高度相似：

| 表象对比 | enum_value | meta_action |
|----------|-----------|-------------|
| 都是 code + name 对 | `IMPORTANT` -> "重要" | `create` -> "创建" |
| 都有类型归属 | `enum_type_id = 'annotation_category'` | (隐式: 所有 action 属于同一"类") |
| 都需要不可变保护 | `category=system, mutability=locked` | 缺少明确保护机制 |
| 都是"被引用"的数据 | `relation_type = 'GENERATES'` | `action = 'create'` |

### 4.2 决定不适合的核心差异

**差异1: 消费方式不同。**

```
枚举值：被动比较（分类标签）
  if relation.relation_type == 'GENERATES':
      style = 'solid'

操作定义：主动分发（控制信号）
  @property
  def is_create_action(self) -> bool:
      return self.action == 'crud_create'    # -> 触发 OwnerAutoPermissionInterceptor
  
  # PersistenceInterceptor: 按 action 分发到不同执行路径
  if context.is_create_action:
      result = self._do_create(context, registry)
  elif context.is_update_action:
      result = self._do_update(context, registry)
```

**差异2: 结构字段 vs 扩展元数据。**

`action_type` 和 `method` 是操作语义的结构性描述。把它们塞进 JSON 字段，相当于把发动机控制参数放进"车辆装饰配置"里。

**差异3: FK 关系的语义纯度。**

如果 meta_actions 用 enum_value 承载，`permissions.action_id` 将指向 `enum_values.id`，而 enum_values 表中还存储着 `annotation_category` 的 `IMPORTANT`、`relation_type` 的 `GENERATES`。需要额外约束 "只有 enum_type_id='meta_action' 的 enum_value 可以被引用"——这是"在通用模型上打补丁"。

**差异4: 生命周期不同。**

| 维度 | enum_value (参考数据) | meta_action (元数据) |
|------|----------------------|---------------------|
| 谁定义 | 系统预置 + 管理员可扩展 | 框架开发者定义 |
| 变化频率 | 相对频繁 | 极少（新架构能力） |
| 变更周期 | 业务运营级 | 架构演进级 |

### 4.3 架构配置层级

```
L1: 元数据层 (Metadata)
    meta_actions, field_type, bo_actions
    -> 独立 BO，框架级保护，YAML 驱动
    -> 定义"系统能做什么"

L2: 参考数据层 (Reference Data)
    annotation_category, relation_type
    -> 枚举模型，三级可变性保护
    -> 定义"业务数据怎么分类"

L3: 配置数据层 (Configuration)
    feature flags, thresholds
    -> 简单键值对，运行时可变
    -> 定义"系统行为参数"
```

### 4.4 结论

**meta_actions 不适合用枚举模型承载。** 枚举承载的是"分类参考数据"，meta_actions 承载的是"系统操作元数据"——两者处于不同的架构配置层级。

但应借鉴枚举模型的三级可变性保护模式（locked/extensible/fully_editable）。核心 CRUD 动作等效于 `locked`，自定义业务动作等效于 `extensible`。

---

## 五、MetaAction 的单一事实源角色分析

### 5.1 理想架构

```
                    +-------------------------+
                    |   meta_actions 表        |  <- 唯一的动作定义源
                    |   (扩展为完整注册表)      |
                    |                         |
                    | code        name   type |
                    | create      创建    crud |
                    | read        读取    crud |
                    | update      更新    crud |
                    | delete      删除    crud |
                    | list        列表    crud |
                    | export      导出   batch |
                    | import      导入   batch |
                    | approve     审批 business|
                    | assign      分配   admin |
                    | revoke      撤销   admin |
                    | manage      管理   admin |
                    +-----------+-------------+
                                |
          +---------------------+---------------------+
          |                     |                     |
          v                     v                     v
   YAML actions[]        permissions 表         前端组件
   引用 meta_action      action_id FK           API 查询获取
   code 作为 key         -> 强约束校验             动作列表+图标
          |                     |                     |
          v                     v                     v
   PermissionSync        create_permission      MetaListPage
   从 meta_actions       _unified()             根据 action_type
   读取完整映射          校验 action_code        渲染正确按钮
```

### 5.2 当前断裂点清单

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0 | `authStore.hasPermission()` 方法不存在 | 路由守卫权限检查崩溃 |
| P0 | 前端 `_checkPermission` 是空桩 | 操作级权限不生效 |
| P1 | `assign`/`revoke`/`manage` 未入种子数据 | 无法创建这些操作的权限 |
| P1 | `ACTION_SUFFIX_MAP` 只有 4/9 | PermissionSync 产物不完整 |
| P2 | `init_menu_permissions` 缺少 `list` | 菜单权限与 bo_bindings 不一致 |
| P2 | BO Framework 不查表校验 | 非法 action 可传入 |
| P3 | YAML relations 全空 | 无法通过元数据驱动导航 |
| P3 | 前端硬编码动作字符串 | 维护成本高，新增动作需改多处 |

### 5.3 新 BO 业务 action 是否需要进 meta_actions 表？

**标准 CRUD 动作（create/read/update/delete/list）应该进 meta_actions 表**，作为权威定义。

**业务专属 action（如 `version.set_current`）不应进 meta_actions 表**，应由各自 BO 的 YAML `actions[]` 定义，通过 `PermissionSyncService` 同步到 `permissions` 表。

设计原则：**`meta_actions` 表定位为"标准动作注册表"，而非"所有动作的集中仓库"。** 这与 AWS 每个服务独立定义 action 的设计理念一致。

---

## 六、业务 Action 的 input/output 参数模型设计

### 6.1 Python 模型已就绪

```python
@dataclass
class MetaAction:
    """元数据操作"""
    id: str
    name: str
    action_type: ActionType          # crud / batch / business / custom
    method: str                      # HTTP method
    path: str                        # API path
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    parameters: List[ActionParameter] = field(default_factory=list)
    behavior: Optional[ActionBehavior] = None
```

```python
@dataclass
class ActionParameter:
    """操作参数定义"""
    id: str
    name: str
    type: str = "string"              # string / integer / boolean / array / object
    required: bool = True
    description: str = ""
    default: Any = None
    enum_values: List[str] = field(default_factory=list)
    i18n_key: str = ""
```

```python
@dataclass
class ActionBehavior:
    """声明式行为配置"""
    precondition: Optional[ActionPrecondition] = None
    effects: List[ActionEffect] = field(default_factory=list)

@dataclass
class ActionEffect:
    type: str = ""                    # set_fields / trigger
    target: str = "self"
    fields: Dict[str, Any] = field(default_factory=dict)
    handler: str = ""                 # handler 函数路径 (用于 trigger 类型)
```

### 6.2 YAML 解析器已就绪

`meta/core/yaml_loader.py` 的 `parse_action()` 已支持解析 `parameters`、`input_schema`、`output_schema`、`behavior`。

### 6.3 唯一实际案例

`meta/schemas/version.yaml`:

```yaml
actions:
  - id: set_current
    name: 设为当前版本
    type: business
    method: POST
    path: /api/v1/versions/{id}/set-current
    description: 将版本设为当前活跃版本
    behavior:
      effects:
        - type: set_fields
          target: self
          fields:
            is_current: true
        - type: trigger
          handler: meta.services.action_handlers.clear_other_current_versions
```

### 6.4 完整参数化 Action YAML 模板

```yaml
actions:
  # ---- 标准 CRUD (无需参数, 框架自动处理) ----
  - id: business_object_create
    name: 创建业务对象
    type: crud
    method: POST
    path: /api/v1/business_objects

  # ---- 带参数的业务 action ----
  - id: assign_to_service_module
    name: 分配到服务模块
    type: business
    method: POST
    path: /api/v1/business_objects/{id}/assign
    description: 将业务对象分配到指定服务模块
    parameters:
      - id: target_module_id
        name: 目标服务模块
        type: integer
        required: true
        description: 目标服务模块的ID
      - id: inherit_permissions
        name: 继承权限
        type: boolean
        required: false
        default: true
        description: 是否继承目标模块的权限配置
    behavior:
      precondition:
        expression: "status == 'active'"
        message: "只有活跃状态的业务对象才能分配"
      effects:
        - type: set_fields
          target: self
          fields:
            service_module_id: "${target_module_id}"
        - type: trigger
          handler: meta.services.action_handlers.sync_permissions_on_assign
    output_schema:
      type: object
      properties:
        previous_module_id:
          type: integer
        new_module_id:
          type: integer
        inherited_permission_count:
          type: integer
```

### 6.5 AI Agent 集成设计

`MetaAction.to_tool_schema()` 方法已实现，可将参数化 action 自动转换为 OpenAI Function Calling 格式：

```json
{
  "name": "assign_to_service_module",
  "description": "分配到服务模块: 将业务对象分配到指定服务模块",
  "parameters": {
    "type": "object",
    "properties": {
      "id": { "type": "integer", "description": "业务对象ID" },
      "target_module_id": { "type": "integer", "description": "目标服务模块的ID" },
      "inherit_permissions": { "type": "boolean", "description": "是否继承目标模块的权限配置" }
    },
    "required": ["id", "target_module_id"]
  }
}
```

这意味着只需在 YAML 中定义 `parameters`，系统自动具备"AI Agent 可调用此 action"的能力——这是 SAP CAP `@requires` 注解在 LLM 时代的等价物。

### 6.6 设计原则

| 原则 | 来源 | 说明 |
|------|------|------|
| **parameters（输入）** | `ActionParameter` 结构体 | 已在 Python 模型中定义，添加 YAML 即可 |
| **input_schema** | JSON Schema 格式 | 用于复杂结构化输入，如文件上传元数据 |
| **output_schema** | JSON Schema 格式 | 用于 AI Agent 理解返回值 |
| **behavior.effects** | 声明式 + 命令式混合 | `set_fields` 声明式，`trigger` 命令式 |
| **behavior.precondition** | 条件表达式 | 基于 `ConditionEvaluator` 引擎 |
| **to_tool_schema()** | 自动转换 | 有 parameters 的 action 自动生成 LLM Tool Schema |

---

## 七、执行链路全景

以 `assign_to_service_module` action 为例：

```
POST /api/v2/bo/business_object/assign_to_service_module
  |  body: { "id": 42, "target_module_id": 7, "inherit_permissions": true }
  |
  v
BOFramework.execute("business_object", "assign_to_service_module", params)
  |
  +-> MetaObject.actions 中找到 id="assign_to_service_module" 的 MetaAction
  |
  +-> [before interceptors]
  |     +-> ContextInterceptor (注入 user 上下文)
  |     +-> DataPermissionInterceptor (权限过滤)
  |     +-> FieldPolicyInterceptor (字段策略校验)
  |
  +-> ActionExecutor._execute_business(action, params)
  |     |
  |     +-> 1. 解析 parameters -> 生成默认值
  |     |     target_module_id=7, inherit_permissions=true
  |     |
  |     +-> 2. 检查 behavior.precondition
  |     |     ConditionEvaluator.evaluate("status == 'active'", 上下文)
  |     |
  |     +-> 3. 遍历 behavior.effects:
  |     |     +-> set_fields -> UPDATE business_objects SET service_module_id=7 WHERE id=42
  |     |     +-> trigger    -> import & call sync_permissions_on_assign(42, 7, True)
  |     |
  |     +-> 4. 构造 output:
  |           { prev_module_id: 3, new_module_id: 7, inherited_count: 15 }
  |
  +-> [after interceptors]
  |     +-> AuditInterceptor (自动记录变更)
  |
  +-> 返回 { success: true, data: { prev_module_id: 3, ... } }
```

---

## 八、改进建议与 Roadmap

### 8.1 改进清单

| 优先级 | 改进项 | 影响范围 | 复杂度 |
|--------|--------|---------|--------|
| **P0** | 修复 `authStore.hasPermission()` 缺失 | 路由守卫崩溃 | 低 |
| **P0** | 修复前端 `_checkPermission` 空桩 | 操作级权限不生效 | 低 |
| **P1** | 完整化 `ACTION_SUFFIX_MAP` (补全 9 个标准动作) | PermissionSync 产物不完整 | 低 |
| **P1** | 补充种子数据 (assign/revoke/manage) | 无法创建这些权限 | 低 |
| **P2** | `permission.yaml` 声明与 `meta_actions` 的 relation | 元数据导航断裂 | 中 |
| **P2** | BO Framework 执行前校验 action | 安全性增强 | 中 |
| **P3** | 前端从 API 动态获取动作列表替代硬编码 | 维护成本降低 | 中 |
| **P3** | 完善 `init_menu_permissions` 中的 `required_permissions` | 菜单权限不完整 | 低 |
| **P4** | 为 `meta_action.action_type` 字段引入枚举类型 | 类型安全 | 低 |

### 8.2 实施 Roadmap

```
Phase A (当前迭代): 止血
  1. 修复 authStore.hasPermission()
  2. 修复 _checkPermission 空桩
  3. 补全 ACTION_SUFFIX_MAP (从 4 扩展到 9)
  4. 补全种子数据 (assign/revoke/manage)

Phase B (下一迭代): 补完
  5. permission.yaml 声明 relation
  6. BO Framework 添加 action 校验
  7. init_menu_permissions 补全 list 权限

Phase C (后续迭代): 升华
  8. 前端动态动作列表（从 API 获取替代硬编码）
  9. 参数化 action 落地（YAML parameters -> Tool Schema）
  10. meta_actions 表与 BO YAML actions 的一致性自动校验
```

### 8.3 MetaAction 表定位总结

| 维度 | 定位 |
|------|------|
| **是什么** | 系统标准动作的权威注册表（对标 K8s Verb Registry + GCP Permissions Reference） |
| **不是什么** | 不是所有业务 action 的集中仓库、不是通用枚举配置 |
| **数据来源** | 种子脚本预定义标准动作 + 管理员通过 API 创建自定义标准动作 |
| **消费方** | `permissions` 表 (FK)、`PermissionService` 校验、前端动作列表 |
| **与 BO YAML actions 的关系** | `meta_actions` 提供标准动作的权威 code/name/type 定义；BO YAML actions 定义业务专属 action，通过 `PermissionSyncService` 同步到 `permissions` 表 |

## 九、meta_actions 表消除决策

> **日期**：2026-05-26
> **决策**：消除 `meta_actions` 数据库表，标准动作统一由 YAML 声明。

### 9.1 决策依据

经过深入分析，`meta_actions` 表是当前架构中的"冗余复制层"：

| 证据 | 说明 |
|------|------|
| **行为不由表决定** | `BOFramework.create()` 硬编码调用 `self.execute('crud_create')`，删除 `meta_actions` 表中 `create` 行不影响框架行为 |
| **`PersistenceInterceptor` 硬编码分发** | `if context.is_create_action → _do_create()`，新增 DB 行不会自动创建新的分发分支 |
| **`ACTION_SUFFIX_MAP` 硬编码在 Python 中** | `{'crud_create': 'create', ...}` 是类变量，不是从 DB 读取的 |
| **仅一个消费点** | `PermissionService.create_permission_unified()` 中校验 action_code 是否在 `meta_actions` 表中——此校验可改为从 MetaRegistry 查询 |
| **前端不读此表** | 前端全量硬编码动作字符串和图标映射，没有任何 API 调用从 `meta_actions` 表获取数据 |
| **头部产品对标** | K8s verb 在 Go 常量中、SAP CAP action 在 CDS 注解中、OpenAPI operationId 在 YAML 中——无一用 DB 表存储标准动作 |

### 9.2 决策结论

| 维度 | 结论 |
|------|------|
| **消除 meta_actions 表** | 是，删除 DB 表及相关服务（MetaActionService, meta_action_api.py） |
| **标准动作声明方式** | 新建 `meta/schemas/_standard_actions.yaml`（纯 YAML 声明，不映射 DB 表） |
| **permissions 表 action_id 字段** | 完全删除 |
| **前端元操作 Tab** | 直接移除 |
| **权限校验替代方案** | 从 MetaRegistry 查询所有 BO YAML `actions[]` + `_standard_actions.yaml` 的标准动作 |
| **ACTION_SUFFIX_MAP 替代** | 从 `_standard_actions.yaml` 加载后构建动态映射（`crud_{code}` → `code`） |

### 9.3 决策对比

| 方案 | 结论 | 原因 |
|------|------|------|
| 消除表 + 用 YAML 声明 | **采纳** | 符合 YAML 单一事实源原则，结构化字段是第一公民，与 MetaRegistry 加载链路一致 |
| 消除表 + 用枚举模型 | **不采纳** | `action_type`/`method` 等结构字段会沦为 JSON blob，丢失类型安全；枚举承载"参考数据"而非"操作元数据" |
| 保留表但降级 | **不采纳** | 保留无行为约束能力的表只会增加维护负担，且与单一事实源原则矛盾 |

### 9.4 目标架构

```
【声明层】
  _standard_actions.yaml          各 BO YAML actions[]
  (create/read/update/delete/     (version.set_current/
   list/export/import/approve/     business_object.assign/...)
   assign/revoke/manage)
       │                                  │
       └────────────┬─────────────────────┘
                    │ 启动时加载进 MetaRegistry
                    ▼
              MetaRegistry
              (运行时统一动作注册表)
                    │
       ┌────────────┼────────────┐
       │            │            │
       ▼            ▼            ▼
  PermissionSync  Permission    无前端 Tab
  (YAML→permissions  Service     (标准动作由
   表自动同步)       (校验通过     framework 使用
                    MetaRegistry   不需要UI管理)
                    替代 DB查询)

【运行时】
  BOFramework.create() 硬编码 'crud_create' — Python 方法签名（不变）
  PersistenceInterceptor 硬编码分发 — 代码契约（不变）
  ActionContext.is_create_action — 语义常量（不变）
```

---

## 附录

### A. 相关文档索引

| 文档 | 说明 |
|------|------|
| [权限体系_单一事实源补充分析.md](./permission-ssot-analysis.md) | 10 处单一事实源违规分析 |
| [方案设计_元数据驱动权限体系.md](./permission-metadata-driven-solution.md) | 权限体系元数据驱动方案 |
| [权限体系元数据驱动化_细化方案设计.md](./permission-metadata-driven-design.md) | 权限细化方案 |
| [权限配置流程优化_维度驱动vs菜单驱动.md](./permission-config-optimization.md) | 权限配置流程分析 |
| [用友BIP权限模型研究补充.md](./yonyou-bip-permission-research.md) | 用友 BIP 权限模型对标 |
| [竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md) | 头部产品对标分析 |
| [ARCHITECTURE_V2.md](./ARCHITECTURE_V2.md) | 架构总览文档 |

### B. 关键代码文件

| 文件 | 说明 |
|------|------|
| `meta/schemas/meta_action.yaml` | MetaAction BO YAML 定义 |
| `meta/schemas/permission.yaml` | Permission BO YAML 定义 |
| `meta/core/models.py:L1339-L1391` | MetaAction 类定义 |
| `meta/core/action_context.py` | ActionContext 执行上下文 |
| `meta/core/action_executor.py` | ActionExecutor 执行引擎 |
| `meta/core/yaml_loader.py:L1293-L1312` | parse_action YAML 解析 |
| `meta/services/permission_sync_service.py` | 权限同步服务 |
| `meta/services/meta_action_service.py` | MetaAction CRUD 服务 |
| `meta/api/meta_action_api.py` | MetaAction REST API |
| `meta/scripts/migrate_permission_unified_semantic.py` | 权限迁移脚本（含种子数据） |
| `src/config/menuConfig.js` | 前端菜单 Tab 配置 |
| `src/views/GenericTabContainer.vue` | 泛化 Tab 容器 |
