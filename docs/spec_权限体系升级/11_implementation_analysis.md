# Spec 11: 现有权限实现分析与变更清单

> 日期：2026-07-24 | 版本：v1.0 | 状态：现状分析
> 目的：基于 Spec 10 统一权限架构，详细分析现有实现，列出具体变更项

---

## 1. 数据表现状与变更

### 1.1 现有权限相关表（13张）

| # | 表名 | YAML Schema | 实际表定义 | 职责 | 数据量 |
|---|------|-------------|-----------|------|--------|
| 1 | `role_intents` | ❌ 无YAML | migration: [add_role_intents_2026.py](file:///d:/filework/worktrees/release-prep/meta/migrations/add_role_intents_2026.py#L52) | Intent权限(granted/denied) | 有数据 |
| 2 | `role_dimension_scopes` | [role_dimension_scope.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/role_dimension_scope.yaml) | [generated_schema.sql#L308](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L308) | 维度范围声明 | 有数据 |
| 3 | `permission_rules` | [permission_rule.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/permission_rule.yaml) | [generated_schema.sql#L263](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L263) | 条件权限规则(legacy) | 有数据 |
| 4 | `data_permission_rules` | ❌ 无独立YAML | [generated_schema.sql#L321](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L321) | 统一规则表(P3-T1, rule_type区分) | 有数据 |
| 5 | `role_permissions` | [role_permission.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/role_permission.yaml) | [generated_schema.sql#L340](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L340) | 角色-功能权限关联 | 有数据 |
| 6 | `permissions` | [permission.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/permission.yaml) | [generated_schema.sql#L237](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L237) | 功能权限定义 | 有数据 |
| 7 | `role_data_permissions` | [role_data_permission.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/role_data_permission.yaml) | [generated_schema.sql#L296](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L296) | 角色数据权限(实例级) | 有数据 |
| 8 | `data_permissions` | [data_permission.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/data_permission.yaml) | [generated_schema.sql#L111](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L111) | 用户数据权限(实例级) | 有数据 |
| 9 | `group_data_permissions` | [group_data_permission.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/group_data_permission.yaml) | [generated_schema.sql#L177](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L177) | 用户组数据权限 | 有数据 |
| 10 | `menu_permissions` | [menu_permission.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/menu_permission.yaml) | [generated_schema.sql#L219](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L219) | 菜单权限定义 | 有数据 |
| 11 | `menus` | [menu.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/menu.yaml) | [generated_schema.sql#L195](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L195) | 菜单(含bo_bindings) | 有数据 |
| 12 | `permission_bundles` | [permission_bundle.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/permission_bundle.yaml) | [generated_schema.sql#L249](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L249) | 权限包(模板) | 有数据 |
| 13 | `employee_data_scopes` | [employee_data_scope.yaml](file:///d:/filework/worktrees/release-prep/meta/schemas/employee_data_scope.yaml) | [generated_schema.sql#L121](file:///d:/filework/worktrees/release-prep/meta/schemas/generated_schema.sql#L121) | 员工数据范围模板 | 有数据 |

### 1.2 表结构详解

#### role_intents (Layer 1 候选, 需升级)

```sql
-- migration: add_role_intents_2026.py L52
CREATE TABLE role_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    bo_id VARCHAR(100) NOT NULL,
    action_name VARCHAR(100) NOT NULL,
    parameters_hash VARCHAR(64),
    granted INTEGER NOT NULL DEFAULT 1,        -- ← 只有 granted/denied, 无 data_scope!
    source VARCHAR(50) DEFAULT 'manual',
    created_at DATETIME,
    updated_at DATETIME,
    UNIQUE (role_id, bo_id, action_name, parameters_hash)
);
```

**与 Spec 10 差距**:
- ❌ 无 `data_scope` 字段 (只有 granted/denied, 无法表达数据范围)
- ❌ 无 `derivation_mode` 字段
- ❌ 无 `include_conditions` / `exclude_conditions`
- 变更类型: **升级** → `role_effective_intents`

#### data_permission_rules (P3-T1 统一表, 部分对齐)

```sql
-- generated_schema.sql L321
CREATE TABLE data_permission_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    rule_type VARCHAR(50) DEFAULT 'condition',  -- condition|dimension|owner|visibility|prohibition
    resource_type VARCHAR(200),
    dimension_code VARCHAR(200),
    condition TEXT,                              -- ← 自由文本表达式!
    scope_mode VARCHAR(50) DEFAULT 'include',
    permission_level VARCHAR(50) DEFAULT 'read',
    is_denied INTEGER DEFAULT 0,                 -- ← 独立字段, 非 exclude
    inherit_to_children INTEGER DEFAULT 1,
    propagate_to_parents INTEGER DEFAULT 0,
    source_table VARCHAR(100),
    source_id INTEGER,
    created_at VARCHAR(200),
    updated_at VARCHAR(200)
);
```

**与 Spec 10 差距**:
- ❌ `condition` 是自由文本, 非结构化 `[{field, op, value}]`
- ❌ `is_denied` 是独立字段, 非 `exclude_conditions`
- ❌ 无 `derivation_mode` 字段
- ❌ 无 `include_conditions` / `exclude_conditions` JSON字段
- ⚠️ `rule_type` 区分 condition/dimension/owner — Spec 10 要求统一为 field op value
- 变更类型: **重构** → 新增 `include_conditions`/`exclude_conditions` JSON列, 废弃 `condition`/`is_denied`/`rule_type`

#### role_dimension_scopes (维度范围, 需合并)

```sql
-- generated_schema.sql L308
CREATE TABLE role_dimension_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    dimension_code VARCHAR(200) NOT NULL,
    dimension_values TEXT NOT NULL,              -- JSON: [1, 2, 3]
    inherit_children INTEGER DEFAULT 1,
    scope_mode VARCHAR(200) DEFAULT 'include'    -- include|exclude|all
);
```

**与 Spec 10 差距**:
- ❌ 独立表, 与条件规则分离 — Spec 10 要求合并到 `permission_rules`
- ❌ `dimension_values` 是简单数组, 非 `{field, op, value}` 结构
- ❌ 无 `permission_level` 字段 (维度范围不绑定级别)
- 变更类型: **合并** → 数据迁移到 `permission_rules.include_conditions`

#### permission_rules (legacy 条件规则, 需废弃)

```sql
-- generated_schema.sql L263
CREATE TABLE permission_rules (
    role_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    condition TEXT NOT NULL,                     -- ← 自由文本!
    permission_level VARCHAR(200) DEFAULT 'read',
    is_denied INTEGER DEFAULT 0,
    inherit_to_children INTEGER DEFAULT 1,
    propagate_to_parents INTEGER DEFAULT 1,
    analysis_mode VARCHAR(200),
    created_at VARCHAR(200),
    created_by INTEGER,
    updated_at VARCHAR(200)
);
```

**与 Spec 10 差距**:
- ❌ 与 `data_permission_rules` 功能重叠 (P3-T1 已部分迁移)
- ❌ `condition` 自由文本
- 变更类型: **废弃** → 数据已迁移到 data_permission_rules, 表可删除

### 1.3 表变更清单

| 操作 | 表名 | 变更内容 |
|------|------|---------|
| **新建** | `role_effective_intents` | Layer 1 事实表, 含 data_scope JSON + derivation_mode |
| **新建** | `permission_rules_v2` | Layer 2 统一规则表, 含 include_conditions/exclude_conditions JSON |
| **新建** | `field_metadata` | 字段元数据注册表 (is_dimension, is_owner, default_derivation_mode) |
| **新建** | `object_owd` | 对象基线权限 (FR-012, Could) |
| **重构** | `data_permission_rules` | 增加 include_conditions/exclude_conditions/derivation_mode 列 |
| **合并** | `role_dimension_scopes` → `permission_rules_v2` | 维度数据迁移到统一规则表 |
| **废弃** | `permission_rules` (legacy) | 数据已迁移到 data_permission_rules |
| **保留** | `role_permissions` | 功能权限关联, 保持不变 |
| **保留** | `permissions` | 功能权限定义, 保持不变 |
| **保留** | `menus` / `menu_permissions` | 菜单定义, 保持不变 |
| **保留** | `role_data_permissions` / `data_permissions` / `group_data_permissions` | 实例级权限, 保持不变 (未来可考虑统一) |
| **保留** | `permission_bundles` | 权限包(模板), 对应 Spec 10 的 permission_templates |
| **保留** | `employee_data_scopes` | 员工范围模板, 对应 Spec 10 的 Owner 条件模板 |
| **升级** | `role_intents` → `role_effective_intents` | 增加 data_scope, derivation_mode |

---

## 2. 后端服务现状与变更

### 2.1 核心服务清单

| 服务 | 文件 | 行数 | 职责 | 变更类型 |
|------|------|------|------|---------|
| DimensionScopeEngine | [dimension_scope_engine.py](file:///d:/filework/worktrees/release-prep/meta/services/dimension_scope_engine.py) | ~1000行 | 维度范围展开+推导 | **重构** |
| ConditionPermissionService | [condition_permission_service.py](file:///d:/filework/worktrees/release-prep/meta/services/condition_permission_service.py) | ~925行 | 条件权限检查+规则CRUD | **重构** |
| RoleIntentDAO | [intent_resolver.py](file:///d:/filework/worktrees/release-prep/meta/core/intent_resolver.py) L45 | ~170行 | role_intents表CRUD | **升级** |
| IntentPermissionChecker | [intent_resolver.py](file:///d:/filework/worktrees/release-prep/meta/core/intent_resolver.py) L215 | ~250行 | Intent权限5步检查 | **升级** |
| DataPermissionInterceptor | [data_permission_interceptor.py](file:///d:/filework/worktrees/release-prep/meta/core/interceptors/data_permission_interceptor.py) | ~1060行 | 读权限拦截器 | **重构** |
| WriteScopeInterceptor | [write_scope_interceptor.py](file:///d:/filework/worktrees/release-prep/meta/core/interceptors/write_scope_interceptor.py) | ~2700行 | 写权限拦截器 | **重构** |
| MenuBOLinker | [menu_bo_linker.py](file:///d:/filework/worktrees/release-prep/meta/core/menu_bo_linker.py) | ~135行 | 菜单-BO关联 | **扩展** |
| PermissionService | [permission_service.py](file:///d:/filework/worktrees/release-prep/meta/services/permission_service.py) | — | 功能权限服务 | **保留** |
| MenuPermissionService | [menu_permission_service.py](file:///d:/filework/worktrees/release-prep/meta/services/menu_permission_service.py) | — | 菜单权限服务 | **保留** |

### 2.2 关键服务分析

#### DimensionScopeEngine (需重构)

**现有方法**:
- `expand_dimension_values(role_id)` → 维度值展开 (含笛卡尔积 AC-008)
- `derive_data_conditions(role_id)` → 推导SQL WHERE条件
- `derive_recommended_menus(role_id)` → 推导菜单
- `derive_permissions(role_id)` → 推导功能权限码
- `auto_sync_all(role_id)` → 全量同步
- `_has_explicit_include_for_dim()` → 笛卡尔积检测 (AC-008)

**与 Spec 10 差距**:
- ❌ 输出是 SQL WHERE 字符串, 非 `{field, op, value}` 结构
- ❌ 维度展开和条件规则完全分离
- ❌ 无 `derivation_mode` (CHILDREN_OF vs static IN) 支持
- ❌ 无向上推导 (ANCESTORS_OF)
- 变更: 输出改为结构化 conditions, 增加 derivation_mode 支持

#### ConditionPermissionService (需重构)

**现有方法**:
- `check_permission()` → 权限检查 (Owner → Deny → Condition)
- `LEVEL_ORDER = {'none':0, 'read':1, 'write':2, 'admin':3}` → 级别包含
- `_action_to_level()` → action→level 映射
- `_is_owner()` → Owner检查
- `_check_denied_rules()` → Deny检查
- `_check_condition_rules()` → 条件检查
- `create_unified_rule()` → 统一规则CRUD (data_permission_rules)
- `preview_matching_resources()` → 资源预览
- `resolve_employee_scope_condition()` → 员工范围解析

**与 Spec 10 差距**:
- ❌ `LEVEL_ORDER` 隐含包含 (write≥read) — Spec 10 要求 action 独立
- ❌ `is_denied` 独立字段 — Spec 10 要求 `exclude_conditions`
- ❌ `condition` 自由文本 — Spec 10 要求 `[{field, op, value}]`
- ❌ 求值优先级: Owner→Deny→Condition — Spec 10: Owner→Exclude→Include
- 变更: 求值引擎重写, 规则CRUD适配新表结构

#### IntentPermissionChecker (需升级)

**现有5步检查**:
1. `role_intents` 表查 granted/denied
2. 静态权限检查 (role_permissions)
3. 条件评估 (`_evaluate_conditions`)
4. 菜单 Intent 检查
5. 默认拒绝

**与 Spec 10 差距**:
- ❌ `role_intents` 无 `data_scope` — 无法做数据范围检查
- ❌ 检查逻辑与 ConditionPermissionService 部分重叠
- 变更: 升级为 `EffectiveIntentChecker`, 从 `role_effective_intents` 读取

#### DataPermissionInterceptor (需重构)

**现有逻辑**:
- `_apply_dimension_scope_filter()` → 调用 DimensionScopeEngine.derive_data_conditions
- `_apply_scope_filter_after_dimension()` → 应用条件过滤
- `_apply_data_permission_filter()` → 实例级权限
- `_add_owner_exception()` → Owner例外

**与 Spec 10 差距**:
- ❌ 维度过滤和条件过滤分两步, 而非统一 data_scope
- ❌ 直接调用 DimensionScopeEngine (运行时推导), 非 effective_intents
- 变更: 改为从 `role_effective_intents` 读取 data_scope, 一次性应用

#### WriteScopeInterceptor (需重构)

**现有逻辑** (2700行, 最复杂):
- `_check_dim_scope()` → 维度范围检查
- `_check_owner_chain()` → Owner链检查
- `_check_visibility()` → 可见性检查
- `_is_fk_value_in_scope()` → 外键范围检查

**与 Spec 10 差距**:
- ❌ 直接调用 DimensionScopeEngine
- ❌ 维度检查和条件检查分离
- 变更: 改为调用 `EffectiveIntentChecker.check()`

### 2.3 服务变更清单

| 操作 | 服务 | 变更内容 |
|------|------|---------|
| **新建** | `EffectiveIntentChecker` | Layer 1 求值引擎: Owner > Exclude > Include |
| **新建** | `PermissionDerivationPipeline` | Layer 2 推导管道 (8步) |
| **新建** | `FieldMetadataRegistry` | 字段元数据注册表 |
| **新建** | `ConditionExpressionParser` | `{field,op,value}` → SQL WHERE |
| **新建** | `PermissionSimulator` | 访问模拟 (FR-016) |
| **重构** | `DimensionScopeEngine` | 输出改为结构化 conditions |
| **重构** | `ConditionPermissionService` | 求值引擎适配 exclude/include |
| **升级** | `RoleIntentDAO` → `EffectiveIntentDAO` | 适配 role_effective_intents |
| **升级** | `IntentPermissionChecker` | 从 effective_intents 读取 |
| **重构** | `DataPermissionInterceptor` | 从 effective_intents 读取 data_scope |
| **重构** | `WriteScopeInterceptor` | 调用 EffectiveIntentChecker |
| **扩展** | `MenuBOLinker` | 增加反向推导 (FR-011) |

---

## 3. API端点现状与变更

### 3.1 现有权限相关API

| 端点 | 方法 | 文件 | 职责 | 变更 |
|------|------|------|------|------|
| `/api/v2/permission-rules` | GET/POST | [bo_api.py#L3223](file:///d:/filework/worktrees/release-prep/meta/api/bo_api.py#L3223) | 条件规则CRUD | **适配** |
| `/api/v2/permission-rules/<id>` | PUT/DELETE | [bo_api.py#L3323](file:///d:/filework/worktrees/release-prep/meta/api/bo_api.py#L3323) | 规则更新/删除 | **适配** |
| `/api/v1/role_dimension_scopes` | GET/POST | bo_api.py | 维度范围CRUD | **合并** |
| `/api/v1/intents` | GET/POST | [intent_api.py](file:///d:/filework/worktrees/release-prep/meta/api/intent_api.py) | Intent管理 | **升级** |
| `/api/v1/roles/<id>/permissions` | GET | role_api.py | 角色权限列表 | **保留** |
| `/api/v1/roles/<id>/menus` | GET/POST | role_menu_api.py | 角色菜单 | **保留** |
| `/api/v1/menu_permissions` | GET/POST | menu_permission_api.py | 菜单权限 | **保留** |
| `/api/v1/permission/preview` | POST | bo_api.py L280 | 资源预览 | **扩展** |

### 3.2 新增API

| 端点 | 方法 | 职责 | 对应FR |
|------|------|------|--------|
| `/api/v1/permission/effective-intents` | GET | 查询有效Intent | FR-001 |
| `/api/v1/permission/derive` | POST | 触发推导 | FR-003 |
| `/api/v1/permission/simulate` | POST | 访问模拟 | FR-016 |
| `/api/v1/permission/diff` | GET | 角色对比 | FR-018 |
| `/api/v1/permission/field-metadata` | GET | 字段元数据 | FR-004 |
| `/api/v1/permission/completeness` | GET | 完整性检查 | FR-017 |

---

## 4. 前端组件现状与变更

### 4.1 现有组件

| 组件 | 文件 | 职责 | 变更 |
|------|------|------|------|
| PermissionConfigPanel | [PermissionConfigPanel.vue](file:///d:/filework/worktrees/release-prep/src/views/SystemManagement/components/PermissionConfigPanel.vue) | 权限配置主面板(5个section) | **重构** |
| DimensionScopePanel | [DimensionScopePanel.vue](file:///d:/filework/worktrees/release-prep/src/views/SystemManagement/components/DimensionScopePanel.vue) | 维度范围配置 | **合并** |
| MenuPermissionMatrix | [MenuPermissionMatrix.vue](file:///d:/filework/worktrees/release-prep/src/views/SystemManagement/components/MenuPermissionMatrix.vue) | 菜单权限矩阵 | **扩展** |
| ConditionRuleList | [ConditionRuleList.vue](file:///d:/filework/worktrees/release-prep/src/views/SystemManagement/components/ConditionRuleList.vue) | 条件规则列表 | **重构** |
| ConditionRuleDialog | [ConditionRuleDialog.vue](file:///d:/filework/worktrees/release-prep/src/views/SystemManagement/ConditionRuleDialog.vue) | 条件规则编辑 | **重构** |
| RolePermissionDetail | [RolePermissionDetail.vue](file:///d:/filework/worktrees/release-prep/src/views/SystemManagement/RolePermissionDetail.vue) | 角色权限详情 | **扩展** |
| useConditionRules | [useConditionRules.ts](file:///d:/filework/worktrees/release-prep/src/views/SystemManagement/composables/useConditionRules.ts) | 条件规则composable | **适配** |
| useMenuPermission | [useMenuPermission.ts](file:///d:/filework/worktrees/release-prep/src/views/SystemManagement/composables/useMenuPermission.ts) | 菜单权限composable | **保留** |

### 4.2 PermissionConfigPanel 现状

当前5个section纵向堆叠:
1. DimensionScopePanel (维度范围)
2. MenuPermissionMatrix (菜单权限)
3. ConditionRuleList (条件规则)
4. (禁止规则 — 可能内嵌在条件规则中)
5. (Owner规则 — 可能内嵌在条件规则中)

**与 Spec 10 差距**:
- ❌ 5个section割裂, 无推导链可视化
- ❌ 无双模式切换 (高效/细粒度)
- ❌ 无完整性指示 (红黄绿灯)
- ❌ 无SQL预览
- ❌ 无角色对比
- 变更: 重构为双模式同页切换

### 4.3 新增前端组件

| 组件 | 职责 | 对应FR |
|------|------|--------|
| `UnifiedPermissionPanel.vue` | 统一权限配置面板(双模式) | FR-006/007/019 |
| `DerivationChainViewer.vue` | 推导链可视化 | FR-008 |
| `SqlPreviewPanel.vue` | SQL预览+资源预估 | FR-009 |
| `CompletenessIndicator.vue` | 完整性指示(红黄绿灯) | FR-017 |
| `RoleDiffViewer.vue` | 角色对比 | FR-018 |
| `PermissionSimulator.vue` | 访问模拟面板 | FR-016 |
| `ConditionEditor.vue` | 结构化条件编辑器 `{field,op,value}` | FR-005 |
| `EffectiveIntentTable.vue` | 细粒度Intent编辑表 | FR-007 |

---

## 5. 推导逻辑现状与变更

### 5.1 现有推导链

```
当前推导链 (分散, 无统一编排):
  role_dimension_scopes
    → DimensionScopeEngine.expand_dimension_values()
    → DimensionScopeEngine.derive_data_conditions()  → SQL WHERE
    → DimensionScopeEngine.derive_recommended_menus() → 菜单列表
    → DimensionScopeEngine.derive_permissions()       → 权限码列表
    → DimensionScopeEngine.auto_sync_all()            → 同步到各表

  data_permission_rules
    → ConditionPermissionService.check_permission()   → 运行时检查
    → ConditionPermissionService.create_unified_rule()→ CRUD

  role_intents
    → RoleIntentDAO.grant/deny/revoke()               → CRUD
    → IntentPermissionChecker.check()                 → 5步检查
```

### 5.2 与 Spec 10 差距

| 维度 | 现状 | Spec 10 |
|------|------|---------|
| 推导编排 | 无统一管道, 各服务独立 | 8步统一推导管道 |
| 推导输出 | SQL WHERE字符串 / 权限码列表 | 结构化 `role_effective_intents` |
| 推导触发 | `auto_sync_all()` 手动调用 | 配置变更自动触发 + 手动重推导 |
| 维度+条件 | 完全分离 | 统一展开 (Step 3) |
| action独立性 | LEVEL_ORDER隐含包含 | LEVEL_BUNDLES展开为独立action |
| 反向推导 | 无 | BO→menu建议 (FR-011) |

### 5.3 推导逻辑变更

| 操作 | 内容 |
|------|------|
| **新建** | `PermissionDerivationPipeline` — 8步统一管道 |
| **重构** | `DimensionScopeEngine` — 输出改为结构化 conditions |
| **新建** | 配置变更监听 → 自动标记 stale (FR-014) |
| **新建** | 重推导触发器 (定时/手动) |

---

## 6. 菜单-BO关联现状与变更

### 6.1 现有实现

**MenuBOLinker** ([menu_bo_linker.py](file:///d:/filework/worktrees/release-prep/meta/core/menu_bo_linker.py)):
- `get_default_bo_permissions(bo_id)` → BO默认权限码
- `get_effective_permissions_for_menu()` → 菜单有效权限
- `get_cross_menu_bo_intent_summary()` → 跨菜单Intent汇总

**menus表**:
- `bo_bindings` (TEXT/JSON) → 菜单绑定的BO列表
- `required_permissions` (TEXT/JSON) → 菜单所需权限
- `primary_object_type` → 主对象类型

### 6.2 与 Spec 10 差距

- ❌ 只有正向 (menu→BO), 无反向 (BO→menu建议) — FR-011
- ❌ `bo_bindings` 是简单JSON, 无 primary/secondary 标记
- 变更: 扩展反向推导, 完善 bo_bindings 结构

---

## 7. 变更影响评估

### 7.1 影响范围

| 层 | 影响文件数 | 影响程度 | 风险 |
|----|-----------|---------|------|
| 数据层 | 13张表 | 高 (4新建+2重构+1合并+1废弃) | 数据迁移风险 |
| 后端服务 | ~10个服务 | 高 (5新建+4重构+2升级) | 求值逻辑变更 |
| API层 | ~8个端点 | 中 (6适配+6新建) | 接口兼容性 |
| 前端组件 | ~8个组件 | 高 (1重构+8新建) | UI重写 |
| 测试 | ~40个测试文件 | 高 | 回归测试 |

### 7.2 高风险项

1. **WriteScopeInterceptor (2700行)**: 最复杂的写权限拦截器, 重构风险最高
2. **DataPermissionInterceptor (1060行)**: 读权限拦截器, 影响所有查询
3. **数据迁移**: role_dimension_scopes → permission_rules_v2, 需保证零丢失
4. **LEVEL_ORDER 变更**: 从隐含包含→action独立, 影响所有权限检查

### 7.3 缓解策略

1. **Feature flag**: 新旧系统并行, 灰度切换
2. **增量迁移**: 先建新表+服务, 再迁移数据, 最后切换拦截器
3. **回归测试**: 40个测试文件全量回归 + 新增Spec 10验收测试
4. **WriteScopeInterceptor 分阶段**: 先适配新接口, 再优化内部逻辑
