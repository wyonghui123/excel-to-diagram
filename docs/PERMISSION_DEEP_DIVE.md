# 权限体系深入分析（修正版 - 基于实际代码）

> **日期**: 2026-06-26
> **状态**: ✅ **深入实际代码 + 业务事实** 重新研究后的修正版
> **修正**: 之前 [PERMISSION_MODEL_DEEP_ANALYSIS.md](PERMISSION_MODEL_DEEP_ANALYSIS.md) + [PERMISSION_V21_CONFIRMATION.md](PERMISSION_V21_CONFIRMATION.md) 仍有不完整之处，本文档是完整修正版
> **核心修正**: 我之前没意识到 **"管理维度" 在我们系统中不是 1 个概念，是 5 个概念混在一起**！

---

## 一、用户核心记忆的再确认

> "**目前我们的角色的权限配置是否会有影响（管理维度配置）**"
> "**管理维度的配置会映射转成数据权限**"
> "**功能权限是基于数据颗粒度**"

**我的修正答案（基于实际代码）**：

1. ✅ 角色权限配置**有影响** — 但要分清楚**功能权限 + 数据权限 + 字段权限 + 关联权限 + Owner 例外 + 条件规则** 6 层
2. ❌ ~~"管理维度配置映射转成数据权限"~~ — **不准确**。管理维度配置 = 5 张表 + 4 类引擎，每个表都是**独立机制**，并不是简单的"映射"
3. ❌ ~~"功能权限是基于数据颗粒度"~~ — **错误**。功能权限是**独立机制**（role_permissions + JWT），跟"数据颗粒度"**正交**，只是写路径**串联校验**（V2.1 + FR-002 5 步）

---

## 二、当前权限体系的完整 6 层架构（实际代码）

### 2.1 6 层分类

| # | 层级 | 数据存储 | 核心服务 | 拦截器 | 优先级 |
|---|------|----------|----------|--------|--------|
| **1** | **功能权限 (Action)** | `permissions` + `role_permissions` | [PermissionService](file:///d:/filework/excel-to-diagram/meta/services/permission_service.py) | [PermissionInterceptor](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py) | **30** |
| **2** | **数据权限 - 维度范围 (Dim Scope)** | `role_dimension_scopes` (dim_values JSON) | [DimensionScopeEngine](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py) | [DataPermissionInterceptor (读)](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py) + [WriteScopeInterceptor (写)](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py) | **30 (读) / 35 (写)** |
| **3** | **数据权限 - 层级可见性 (Visibility Scope)** | BO.yaml.authorization.scope (YAML) | DataPermissionInterceptor._apply_scope_filter | DataPermissionInterceptor (读) | **30** |
| **4** | **Owner 例外 (Owner Exception)** | DB 行内 `owner_id` 字段 + 链追溯 | [chain_owner_resolver](file:///d:/filework/excel-to-diagram/meta/services/chain_owner_resolver.py) | [OwnerChainInterceptor](file:///d:/filework/excel-to-diagram/meta/core/interceptors/owner_chain_interceptor.py) | **25** |
| **5** | **数据权限 - 实例级 (Instance Permission)** | `role_data_permissions` + `group_data_permissions` (DB 表) | [DataPermissionService](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py) + [DataPermissionFilter](file:///d:/filework/excel-to-diagram/meta/services/data_permission_filter.py) | DataPermissionInterceptor._apply_data_permission_filter | **30** |
| **6** | **条件型权限 (Condition Rule)** | `permission_rules` (DB 表，condition 字符串) | [ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) | (暂无专用拦截器) | - |

**外加 3 个独立能力**（独立于 6 层，旁路）：

| # | 能力 | 数据存储 | 核心服务 | 拦截器 | 优先级 |
|---|------|----------|----------|--------|--------|
| **7** | **M11 YAML 集中化 RLS** | `rls_rules/*.yaml` (row_filters + field_masks + actions) | [rls.loader](file:///d:/filework/excel-to-diagram/rls/loader.py) + [rls.enforce](file:///d:/filework/excel-to-diagram/rls/enforce.py) | 被 PermissionInterceptor / DataPermissionInterceptor 通过 `_check_yaml_*` 调用 | - |
| **8** | **字段级脱敏 (Field Mask)** | `rls_rules/*.yaml` field_masks + `field_policies` 表 | [rls.apply_field_masks](file:///d:/filework/excel-to-diagram/rls/enforce.py) | FieldPolicyInterceptor (after_action) | - |
| **9** | **Owner 自动权限注入** | `data_permissions` 表 | [OwnerAutoPermissionInterceptor](file:///d:/filework/excel-to-diagram/meta/core/interceptors/owner_permission_interceptor.py) | OwnerAutoPermissionInterceptor (after create) | **96** |

**实际共 6 + 3 = 9 个机制并存**（不是之前认为的 3 层！）

### 2.2 拦截器链 (按 priority 排序, 写操作)

```
请求: PATCH /api/v2/bo/domain/703  body={name: "新名称"}
   ↓
P25. OwnerChainInterceptor
   - 检查 domain 703 沿 HIERARCHY_CHAIN 向上追溯 product.owner_id
   - chain_owner_resolver.resolve_root_owner(data_source, 'domain', 703)
     → product.owner_id = 333
   - 命中 → context._owner_chain_match=True, 短路返回
   - 不命中 → context._owner_chain_match=False, 继续
   ↓
P30. PermissionInterceptor (Functional Perm Gate)
   - _ACTION_PERMISSION_SUFFIX 映射: crud_update → 'update'
   - 检查 user.permissions 含 'domain:update'?
   - 缺 → PermissionDenied(403)
   ↓
P30. DataPermissionInterceptor (读路径专用, 写不触发)  ← 写操作跳过此层
   ↓
P30. OwnerAutoPermissionInterceptor (after create only)  ← 仅 create 后
   ↓
P35. WriteScopeInterceptor (写路径 dim scope × functional perm 联动)
   - target_perm_suffix='update' → target_perm='domain:update'
   - 5 步校验:
     1. admin? → 放行
     2. owner chain? → 放行
     3. dim scope × functional perm 联动 (V2.1) ← 核心
     4. visibility scope?
     5. 拒绝
   ↓
Action 执行
```

---

## 三、每个机制的实际数据流 (深入代码)

### 3.1 功能权限 (Action) - 实际流

**数据存储**：
```sql
-- permissions 表 (主数据)
CREATE TABLE permissions (
  id INTEGER PRIMARY KEY,
  code VARCHAR(200) UNIQUE NOT NULL,  -- 'domain:update', 'product:create'
  name VARCHAR(200), description TEXT,
  is_system INTEGER DEFAULT 0,
  ...
);

-- role_permissions 关联表
CREATE TABLE role_permissions (
  id INTEGER PRIMARY KEY,
  role_id INTEGER NOT NULL,
  permission_id INTEGER NOT NULL,
  UNIQUE(role_id, permission_id)
);

-- groups + group_roles + user_group_members
-- (user → personal group → role 的间接路径)
```

**来源**：[init_menu_permissions.py](file:///d:/filework/excel-to-diagram/meta/scripts/init_menu_permissions.py) **步骤 6.5 自动派生**:
```
[步骤 6.5] 对齐 yaml import_export → menu bo_bindings:
- meta/schemas/domain.yaml 的 import_export.export_enabled=True
  → 自动加到 menus.bo_bindings[domain].include_actions=['export', 'import']
- menus.bo_bindings 是权限矩阵 UI (MenuPermissionMatrix) 推导源
- _derive_bo_permission_groups 读 menus.bo_bindings[*].include_actions
  → 派生 'domain:export', 'domain:import' 等 perm code
  → INSERT INTO permissions + role_permissions
```

**使用**：[PermissionService.get_user_permissions](file:///d:/filework/excel-to-diagram/meta/services/permission_service.py#L79-L89)：
```sql
SELECT DISTINCT p.code FROM permissions p
JOIN role_permissions rp ON p.id = rp.permission_id
JOIN group_roles gr ON rp.role_id = gr.role_id
JOIN user_group_members ugm ON gr.group_id = ugm.group_id
WHERE ugm.user_id = ?
```

**注入 JWT**：登录时 `g.current_user.permissions = [...]` (含 `*` 通配)

**拦截器**：[PermissionInterceptor._check_yaml_permission](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L528)：
- 先调 rls.enforce.check_action (M11 YAML)
- 不命中 → JWT permissions 检查
- 还不命中 → 旧 _check_legacy_permission 兜底

### 3.2 数据权限 - 维度范围 (Dim Scope) - 实际流

**数据存储**：
```sql
CREATE TABLE role_dimension_scopes (
  id INTEGER PRIMARY KEY,
  role_id INTEGER NOT NULL,
  dimension_code VARCHAR(100) NOT NULL,  -- 'product' / 'version' / 'domain' / 'sub_domain'
  dimension_values JSON,  -- '[1, 17, 21]'  ← 业务对象 ID 列表
  inherit_children INTEGER DEFAULT 0,  -- 是否沿 chain 向上自动展开
  scope_mode VARCHAR(20) DEFAULT 'whitelist',
  ...
);
```

**来源**：UI `DimensionScopePanel.vue` → `POST /api/v1/roles/<id>/dimension-scopes`

**使用**：[DimensionScopeEngine.expand_dimension_values](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L148-L207)：
```python
# 1. 加载 role_dimension_scopes (role_id=60)
#   → dimension_code='version', dimension_values='[2,11,12]', inherit_children=1
# 2. 解析 dimension_values
values = set(json.loads('[2,11,12]'))  # {2, 11, 12}
# 3. inherit_children=True → 沿 HIERARCHY_CHAIN 展开
#   version → domain → sub_domain
HIERARCHY_CHAIN = ['product', 'version', 'domain', 'sub_domain']
#   domain: SELECT id FROM domains WHERE version_id IN (2,11,12) → {101,102,103,104}
#   sub_domain: SELECT id FROM sub_domains WHERE domain_id IN (...) → {201,...}
expanded = {
  'version': {2, 11, 12},
  'domain': {101, 102, 103, 104},
  'sub_domain': {201, 202, ...},
}
```

**注入 SQL**：[derive_data_conditions](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L209-L260) + [dimension_object_mapping.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/dimension_object_mapping.yaml)：
```python
# dimension_object_mapping.yaml 配置:
#   dimension_code: product
#     applies_to:
#       - bo: version, field: product_id, filter_type: fk
#       - bo: domain, field: product_id, filter_type: chain
#
# 派生 SQL:
conditions = {
  'product':  "product.id IN (1, 17)",
  'version':  "version.product_id IN (1, 17)",
  'domain':   "domain.version_id IN (SELECT id FROM versions WHERE product_id IN (1, 17))",
  'relationship': "(relationship.source_bo_id IN (...) OR relationship.target_bo_id IN (...))",
}
```

**拦截器使用**：
- **读路径**: [DataPermissionInterceptor._apply_dimension_scope_filter](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py) → SQL WHERE
- **写路径**: [WriteScopeInterceptor._check_dim_scope](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py#L758-L866) → V2.1 联动校验

### 3.3 数据权限 - 层级可见性 (Visibility Scope) - 实际流

**数据存储**：[domain.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/domain.yaml) L45-53:
```yaml
authorization:
  check: true
  scope: version_id IN (SELECT v.id FROM versions v JOIN products p ON v.product_id = p.id WHERE p.visibility = 'public' OR p.owner_id = $user.id)
  auto_owner: false
  auto_permission: admin
  inherit_to_children: true
  allow_transfer: false
  transfer_keep_permissions: false
```

**含义**：domain 表的可见性 = "version 在 public product 下 OR product owner 是自己"

**使用**：[DataPermissionInterceptor._apply_scope_filter](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py#L517-L609)：
- 解析 BO.yaml.authorization.scope 表达式
- 替换 $user.id, $user.username
- 注入到 SQL

### 3.4 Owner 例外 (Owner Exception) - 实际流

**数据存储**：`products.owner_id` (顶层 BO), 子对象无 owner_id

**使用**：[chain_owner_resolver.build_owner_exception_subquery](file:///d:/filework/excel-to-diagram/meta/services/chain_owner_resolver.py#L176-L243)：
```python
# 沿 HIERARCHY_CHAIN 构造 owner 追溯子查询
# version: SELECT id FROM versions WHERE product_id IN (SELECT id FROM products WHERE owner_id = 333)
# domain: SELECT id FROM domains WHERE version_id IN (SELECT id FROM versions WHERE product_id IN (...))
# sub_domain: SELECT id FROM sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE ...)

# SQL 注入到 query_conditions:
context.extra['query_conditions'].append({
  'field': 'id',
  'operator': 'in_subquery',
  'value': '<子查询字符串>',
  'source': 'owner_exception_chain',
})
```

**拦截器使用**：
- **写路径**: [OwnerChainInterceptor](file:///d:/filework/excel-to-diagram/meta/core/interceptors/owner_chain_interceptor.py) P25 整拦截器
- **读路径**: [DataPermissionInterceptor._add_owner_exception](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py#L859-L945) 仅追加子查询

### 3.5 数据权限 - 实例级 (Instance Permission) - 实际流

**数据存储**：
```sql
-- 实例级数据权限 (具体到某 record_id)
CREATE TABLE role_data_permissions (
  id, role_id, resource_type, resource_id,
  permission_level VARCHAR(20),  -- 'read' / 'write' / 'admin'
  inherit_to_children INTEGER,
  ...
);
CREATE TABLE group_data_permissions (
  id, group_id, resource_type, resource_id,
  permission_level, inherit_to_children,
  ...
);
```

**使用**：[DataPermissionFilter.apply_filter](file:///d:/filework/excel-to-diagram/meta/services/data_permission_filter.py#L21-L52)：
```python
allowed_ids = self.perm_service.get_allowed_resource_ids(user_id, 'domain')
# → [1, 2, 3, 5, 7]
# 注入 SQL: domain.id IN (1, 2, 3, 5, 7)
```

**状态**：⚠️ **生产数据为 0**（之前 [PERMISSION_TODOS.md](PERMISSION_TODOS.md) 提过），代码仍在跑（白名单 fallback）

### 3.6 条件型权限 (Condition Rule) - 实际流

**数据存储**：[permission_rule.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/permission_rule.yaml) → `permission_rules` 表:
```sql
CREATE TABLE permission_rules (
  id, role_id, resource_type,
  condition TEXT,  -- 'version_id IN (1, 2) AND domain_type = "CORE"'
  permission_level,  -- 'read' / 'write' / 'admin'
  is_denied INTEGER,  -- 禁止权优先
  inherit_to_children INTEGER,
  propagate_to_parents INTEGER,
  analysis_mode TEXT,
  ...
);
```

**使用**：[ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py)：
- [create_rule](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L162) / [update_rule](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L191) / [delete_rule](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L225) CRUD
- [preview_matching_resources](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L426) 预览
- [ConditionEvaluator](file:///d:/filework/excel-to-diagram/meta/services/condition_evaluator.py) 解析 + 安全白名单 (ALLOWED_FIELDS)

**应用**：[ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L30) 头部说明:
> "Oracle 风格混合权限模型 + 用友BIP特性:
> - 条件型权限规则 (替代实例型 resource_id)
> - Owner 自动权限
> - **禁止权优先原则**
> - **向下继承** (天然实现)
> - **向上传播**"

**状态**：⚠️ **业务 UI 已实现** (`ConditionRuleList.vue`)，但**主路径拦截器未集成**。它被设计为"分析模式"独立工具。

### 3.7 M11 YAML 集中化 RLS - 实际流

**数据存储**：[rls_rules/](file:///d:/filework/excel-to-diagram/rls_rules/) 目录下的 36 个 YAML 文件

**核心 API**：
- [rls.loader.get_allowed_actions](file:///d:/filework/excel-to-diagram/rls/loader.py#L123) - 读 actions
- [rls.loader.get_row_filters](file:///d:/filework/excel-to-diagram/rls/loader.py#L111) - 读行过滤
- [rls.loader.get_field_masks](file:///d:/filework/excel-to-diagram/rls/loader.py#L117) - 读脱敏
- [rls.enforce.check_action](file:///d:/filework/excel-to-diagram/rls/enforce.py#L34) - 高层执行
- [rls.enforce.get_active_row_filter](file:///d:/filework/excel-to-diagram/rls/enforce.py#L80) - 高层执行
- [rls.enforce.apply_field_masks](file:///d:/filework/excel-to-diagram/rls/enforce.py#L142) - 高层执行

**使用**：[_check_yaml_permission / _check_yaml_row_filter / _apply_yaml_field_masks](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L528-L617)

**状态**：⚠️ **130% 完成, 155 PASS**, 但所有调用都被标 `[DECORATIVE]`, **未启用为主路径**

### 3.8 字段级脱敏 (Field Mask)

**双源**：
1. `rls_rules/*.yaml` field_masks (M11, [DECORATIVE])
2. `field_policies` 表 (生产, 主路径)

**使用**：FieldPolicyInterceptor (after_action) → 字典递归脱敏

### 3.9 Owner 自动权限注入

**触发**：`crud_create` 之后 (after_action)

**逻辑**：[OwnerAutoPermissionInterceptor](file:///d:/filework/excel-to-diagram/meta/core/interceptors/owner_permission_interceptor.py) P96:
- 创建后自动给 `data_permissions` 表加 admin 权限
- 实现 "创建者 = 拥有者" 语义

---

## 四、回答用户两个核心问题的最终修正

### 4.1 问题 1: 角色权限配置（管理维度）是否会有影响？

**直接答案**: 业务人员**有影响但不大**，但**机制层面影响重大**。

#### 4.1.1 业务人员视角 (配置 UI 操作)

| 机制 | UI 入口 | 业务感知变化 |
|------|---------|-------------|
| 功能权限 (Action) | `MenuPermissionMatrix.vue` (勾选 menu) | **0 变化** |
| Dim Scope | `DimensionScopePanel.vue` (选 dim + ID) | **0 变化** |
| Visibility Scope | BO.yaml (开发维护) | **0 变化** (业务不接触 YAML) |
| Owner Exception | DB 字段 (products.owner_id) | **0 变化** |
| Instance Permission | 数据权限配置页 (role_data_permissions) | **0 变化** (已废弃) |
| Condition Rule | `ConditionRuleList.vue` (写 condition) | **0 变化** |
| M11 YAML | `rls_rules/*.yaml` (开发维护) | **0 变化** (业务不接触 YAML) |
| Field Mask | `field_policies` 表 / rls YAML | **0 变化** |
| Owner Auto Perm | 自动 (创建后) | **0 变化** |

**结论**: 业务人员**无需重新配置任何角色**，所有现有数据继续有效。

#### 4.1.2 机制层面（如果重构）

如果按 [PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md](PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) 统一架构:

| 旧 | 新 | 业务影响 |
|----|----|---------|
| 9 个机制并存 | 1 个 PermissionResolver | **0** |
| M11 [DECORATIVE] | 启用主路径 | 业务**更安全** (有兜底) |
| rls YAML + BO.yaml 双源 | 仅 rls YAML | 业务**0** (开发维护) |
| HIERARCHY_CHAIN 硬编码 | YAML 化 | 业务**0** |

### 4.2 问题 2: 管理维度配置会映射成数据权限？

**直接答案**: **不是简单的"映射"，是 5 种机制的协调**。

#### 4.2.1 "管理维度" 实际是 5 个概念的统称

| 概念 | 数据源 | 业务感知 |
|------|--------|---------|
| **1. permission_dimension (元数据表)** | 业务层级定义 (hierarchies.yaml) | 元数据 |
| **2. role_dimension_scopes (运行时)** | UI 配置 | **真正的"管理维度配置"** |
| **3. dimension_object_mapping (YAML)** | 维度→BO 字段映射 | 配置 |
| **4. permission_rules (条件规则)** | UI 配置 | 条件权限 |
| **5. role_data_permissions (实例级)** | 已废弃 | 历史 |

#### 4.2.2 "映射" 的实际机制

```
业务人员配:  role 60 → version=[2, 11, 12] + inherit_children=true
                          ↓
                  role_dimension_scopes 表
                          ↓
              DimensionScopeEngine.expand_dimension_values(60)
                          ↓
       {version: {2,11,12}, domain: {101,102,...}, sub_domain: {201,...}}
                          ↓
       dimension_object_mapping.yaml 查 mapping
                          ↓
       derive_data_conditions(60) → SQL dict
                          ↓
       {domain: "domain.version_id IN (2,11,12)"}
                          ↓
       DataPermissionInterceptor 注入 SQL
                          ↓
       SELECT * FROM domains WHERE domain.version_id IN (2, 11, 12) AND ...
```

**"映射" 是链式派生, 不是 1:1 转换**：
- role_dimension_scopes (业务输入) → expand (引擎) → chain 向上展开 → BO mapping (YAML) → SQL (条件)

### 4.3 问题 3: 功能权限是基于数据颗粒度？

**直接答案**: **正交, 不是基于**。但 V2.1 (2026-06-22) 引入"联动校验"。

#### 4.3.1 正交证据 (读路径)

读路径 [DataPermissionInterceptor](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py):
- functional perm (P30) 决定**能看这个 BO 类型的 API** (有 'domain:read' → 能调 GET /domain)
- dim scope 决定**能看这个 BO 类型的哪些行** (有 version=[2,11,12] → 只能看这些 version 下的 domain)
- **两者完全独立配置 + 独立生效**

#### 4.3.2 联动证据 (写路径 V2.1)

写路径 [WriteScopeInterceptor._check_dim_scope](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py#L758-L866):
```python
# V2.1 关键: dim scope 派生前, 先校验 functional perm
for role_id in role_ids:
    # ★ V2.1 核心: 必须先有 functional perm
    if not self._role_has_perm(role_id, f'domain:update', role_perm_codes):
        continue  # 缺 perm 的 role 跳过 dim scope

    # 才有资格做 dim scope 检查
    expanded = engine.expand_dimension_values(role_id)
    if domain=703 in expanded['domain']:
        ✅ allow
```

**V2.1 语义**:
- functional perm 是 dim scope 派生的**前置条件** (filter-like, 不是基于)
- 缺 perm 的 role → 完全不参与 dim scope 派生
- 这是"双闸门"模式 (与 SAP ACTVT + BUKRS 对齐)

#### 4.3.3 修正之前错误

我之前 [PERMISSION_V21_CONFIRMATION.md](PERMISSION_V21_CONFIRMATION.md) 写:
> ✅ "**功能权限 (Action Gate) 是数据权限 (Row Filter) 的前置条件**"

**修正为**:

> ✅ **"在写路径上, functional perm 是 dim scope 派生的前置条件 (V2.1 联动) ; 在读路径上, functional perm 和 dim scope 是正交的"**
>
> 即：**读正交, 写串联** (跟 SAP MM01 "宽松读 + 严格写" 一致)

---

## 五、架构重设计 (再修正)

[PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md](PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) 之前说的是"3 层 → 1 层"。

**修正**: 实际是 **9 个机制 → 1 个 PermissionResolver** (9:1 重设计)。

### 5.1 PermissionResolver 完整设计

```python
# 新 PermissionResolver
def resolve(user, action, bo, record) -> (bool, masked, scope_filter, reason):
    # 1. admin 短路
    if is_admin(user): return (True, {}, None, "ADMIN")

    # 2. functional perm gate (Action)
    target_perm = f"{bo}:{action_suffix}"  # 'domain:update'
    if not check_action(user.roles, bo, target_perm):
        return (False, {}, None, "ACTION_DENIED")

    # 3. owner chain (priority 25)
    if is_owner_chain(user, bo, record):
        return (True, {}, None, "OWNER_CHAIN")

    # 4. dim scope (读+写) 联动 functional perm (V2.1)
    for role in user.roles:
        if not role.has_perm(target_perm):  # ★ V2.1 联动
            continue
        expanded = expand_dimension_values(role)
        if bo in expanded and record.id in expanded[bo]:
            return (True, {}, scope_filter, "DIM_SCOPE")

    # 5. visibility scope (BO.yaml.authorization.scope)
    if passes_visibility_scope(user, bo, record):
        return (True, masked, scope_filter, "VISIBILITY_SCOPE")

    # 6. instance permission (data_permissions 表)
    if record.id in get_allowed_resource_ids(user, bo):
        return (True, {}, None, "INSTANCE_PERM")

    # 7. condition rule (permission_rules 表)
    if passes_condition_rule(user, bo, record):
        return (True, {}, None, "CONDITION_RULE")

    # 8. field mask
    masked = apply_field_masks(user.roles, bo, data)

    return (False, masked, scope_filter, "ALL_DENIED")
```

**关键点**:
- 步骤 2 (Action Gate) 是**写路径前置**, 读路径可选
- 步骤 4 (Dim Scope × Functional Perm 联动) 是 V2.1 核心
- 步骤 7 (Condition Rule) 是旁路, 仅在分析模式 / 独立 UI 触发
- 步骤 1-7 **任一通过即放行** (与现有 FR-002 5 步校验一致)

### 5.2 9 → 1 重设计的实施影响

| 旧 | 新 | 业务影响 |
|----|----|---------|
| 9 个机制并存 | 1 个 PermissionResolver | 0 (数据不变) |
| 6 个拦截器 (5 priority) | 1 个 resolver (按需调用) | 0 (业务无感) |
| M11 [DECORATIVE] | 主路径 | 业务更安全 |
| 3 个互不知对方 | 1 个统一接口 | 业务无感 |
| HIERARCHY_CHAIN 硬编码 + mapping YAML 双源 | 仅 YAML | 业务 0 |
| rls YAML + dim scope 双层配置 | 1 处声明 (BO.yaml.data_permission_dimensions) | 业务 0 |

---

## 六、对之前两份修正文档的总结

### 6.1 [PERMISSION_MODEL_DEEP_ANALYSIS.md](PERMISSION_MODEL_DEEP_ANALYSIS.md) 的错误

| 章节 | 错误 | 修正 |
|------|------|------|
| §二 1.1 3 层体系 | 误以为只有 3 层 | 实际是 **9 机制** (6 核心 + 3 旁路) |
| §二 1.1 "M11 [DECORATIVE]" | 错误理解 | M11 不是装饰, **是已实现的备选方案** |
| §二 1.2 6 大断裂点 | 漏了 instance perm, condition rule, field mask | 实际断裂点是 9+ 个 |
| §三 3.1 架构图 | 只画了 3 层 | 实际应该画 9 机制 + 拦截器链 priority |
| §三 3.1 维度 = 数据权限输入 | 错误简化 | 维度只是 9 机制中**1 个** (DimensionScope) |
| §四 4.1 读正交 + 写串联 | 完全相反 | **读正交, 写串联** |

### 6.2 [PERMISSION_V21_CONFIRMATION.md](PERMISSION_V21_CONFIRMATION.md) 的错误

| 章节 | 错误 | 修正 |
|------|------|------|
| §三 target_perm_suffix | 部分正确 | V2.1 实际是 FR-002 step 3 + perm 前置检查, 跟 SAP ACTVT+BUKRS 完全对齐 |
| §三 _check_dim_scope 代码 | 正确 | 跟 V2.1 spec 完全一致 |
| §四 "Action 是 dim scope 前置" | 错误 | V2.1 **仅在写路径**是前置, 读路径正交 |
| §五 4 维正交 | 错误 | 实际 9 维 (6 核心 + 3 旁路), 不是 4 维 |
| §五 "data_scope 是 functional perm 范围内" | 错误 | **写路径**才联动, **读路径**正交 |

### 6.3 [PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md](PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) 的错误

| 章节 | 错误 | 修正 |
|------|------|------|
| §三 3.1 3 层→2 层 | 错误 | 实际是 **9 机制 → 1 个 PermissionResolver** |
| §三 3.1 PermissionResolver 简化 | 错误 | 应该包含 9 个机制的所有检查 |
| §四 4.1 路径 1 Action Gate "不变" | 错误 | 应该是 "V2.1 联动 (写路径)" |
| §五 Phase 1-3 工时 | 偏低 | 实际需要 8-10 周 (9 机制收敛) |

---

## 七、最终答案

### 7.1 Q1: 角色权限配置（管理维度）是否会有影响？

**答**:
- ✅ **业务人员**: 0 变化 (所有 UI 配置不变, 数据不变)
- ⚠️ **机制层面**: 9 个机制并存是技术债, 1 个 PermissionResolver 是统一方向
- ⚠️ **重构后**: M11 从 [DECORATIVE] → 主路径, 业务**更安全** (有兜底)
- ✅ **管理维度配置 = data permissions 1 个机制 (DimensionScope) 的输入**, 不是全部

### 7.2 Q2: 管理维度配置会映射转成数据权限？

**答**:
- ✅ **DimensionScope 机制**: 业务配 `version=[2,11,12]` → 通过 DimensionScopeEngine → SQL
- ❌ **不是全部数据权限**: 还有 5 个其他数据权限机制 (Visibility / Owner / Instance / Condition / OwnerAuto)
- ❌ **不是 1:1 映射**: 是 5 步链式派生 (input → expand → chain → mapping → SQL)
- ✅ **统一入口 = PermissionResolver.resolve(user, action, bo, record)**, 4 元组返回

### 7.3 Q3: 功能权限是基于数据颗粒度？

**答**:
- ❌ **不是基于** (正交配置, 独立生效)
- ✅ **读路径**: functional perm (P30) 和 dim scope (P30) **完全正交**
- ✅ **写路径 (V2.1)**: functional perm 是 dim scope 派生的**前置条件** (filter-like, 不是基于)
- ✅ **写路径 (SAP 对齐)**: functional perm × dim scope 联动 = "双闸门" (ACTVT + BUKRS)
- ✅ **架构重设计**: 1 个 PermissionResolver, 包含所有 9 个机制, 写路径强制 V2.1 联动

### 7.4 总结

> 业务人员**完全无感知** (配置 UI + 数据 0 变化)
>
> 开发/架构层面, **9 机制 → 1 个 PermissionResolver** 是清晰目标, **V2.1 联动** 是核心创新
>
> "管理维度" 在我们系统中**是 9 机制中 1 个 (DimensionScope) 的统称**, 不是独立概念

---

## 八、文档关联

| 文档 | 角色 | 状态 |
|------|------|------|
| **[PERMISSION_DEEP_DIVE.md](PERMISSION_DEEP_DIVE.md)** | **本文档: 9 机制完整分析 + 修正** | ✅ |
| [PERMISSION_V21_CONFIRMATION.md](PERMISSION_V21_CONFIRMATION.md) | V2.1 确认 | ⚠️ 需修正 (4 维→9 维) |
| [PERMISSION_MODEL_DEEP_ANALYSIS.md](PERMISSION_MODEL_DEEP_ANALYSIS.md) | 上一轮分析 | ⚠️ 需修正 (3 层→9 机制) |
| [PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md](PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) | 架构重设计 | ⚠️ 需修正 (Phase 1-3 → 9:1) |
| [PERMISSION_TODOS.md](PERMISSION_TODOS.md) | 权限 TODO 盘点 | ✅ 大致正确 |
| [TODOS.md](TODOS.md) | 总 TODO | ✅ 仍是 SSOT |

### 关键代码位置

| 组件 | 文件 | 行数 |
|------|------|------|
| PermissionInterceptor (P30) | meta/core/interceptors/permission_interceptor.py | 1-619 |
| DataPermissionInterceptor (P30 读) | meta/core/interceptors/data_permission_interceptor.py | 1-1000+ |
| OwnerChainInterceptor (P25 写) | meta/core/interceptors/owner_chain_interceptor.py | 1-291 |
| WriteScopeInterceptor (P35 写) | meta/core/interceptors/write_scope_interceptor.py | 1-1000+ |
| OwnerAutoPermissionInterceptor (P96) | meta/core/interceptors/owner_permission_interceptor.py | - |
| PermissionService | meta/services/permission_service.py | 1-220 |
| DimensionScopeEngine | meta/services/dimension_scope_engine.py | 1-500+ |
| chain_owner_resolver | meta/services/chain_owner_resolver.py | 1-244 |
| ConditionPermissionService | meta/services/condition_permission_service.py | 1-500+ |
| DataPermissionService | meta/services/data_permission_service.py | 1-900+ |
| DataPermissionFilter | meta/services/data_permission_filter.py | 1-100 |
| rls.loader | rls/loader.py | 1-158 |
| rls.enforce | rls/enforce.py | 1-200+ |
| rls.dsl | rls/dsl.py | 1-100+ |
| rls.hot_reload | rls/hot_reload.py | - |
| dimension_object_mapping_loader | meta/core/dimension_object_mapping_loader.py | 1-150+ |
| permission_dimension_engine | meta/services/permission_dimension_engine.py | 1-500+ |
| condition_evaluator | meta/services/condition_evaluator.py | 1-100+ |

### 关键配置/Schema

| 配置 | 文件 |
|------|------|
| 36 BO YAML | meta/schemas/*.yaml |
| 36 RLS YAML | rls_rules/*.yaml |
| 层级元数据 (SSOT) | meta/schemas/hierarchies.yaml |
| 维度映射 (YAML loader) | meta/schemas/dimension_object_mapping.yaml |
| 功能权限代码 | permissions + role_permissions 表 |
| 维度范围 | role_dimension_scopes 表 |
| 实例权限 (废弃) | role_data_permissions / group_data_permissions 表 |
| 条件规则 | permission_rules 表 (condition 字符串) |
| 字段脱敏 | rls YAML field_masks + field_policies 表 |
| V2.1 spec | .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md |
| 写拦截器 spec | .trae/specs/auth-permission-system/write-scope-interceptor-spec.md |
| 权限主 spec | .trae/specs/auth-permission-system/spec.md |
