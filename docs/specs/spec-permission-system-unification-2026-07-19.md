# Spec: 权限体系全面统一与优化

> **Spec ID**: spec-permission-system-unification-2026-07-19
> **创建日期**: 2026-07-19
> **状态**: Draft v2 (待评审)
> **作者**: AI Assistant
> **优先级**: P1 (高)
> **范围**: 权限体系全面优化（11 机制 → 10 机制\[M3 统一] → 3 层 → 1 统一 PermissionResolver）
> **变更**: v2 补充 15 项遗漏（V2.1 联动 / UI 3 Panel / 3 阶段灰度 / 管理维度映射 / 继承 5 规则 / M1-M11 重编号 / 读权限语义 / 3 拦截器 / Profile 瘦化 / 24 月路线图 / 审计清洗 / ReBAC 分析 / **Visibility 统一模型研究**）

***

## 1. 背景与目标

### 1.1 研究背景

本 Spec 整合以下研究与 TODO 文档：

1. **`docs/WILDCARD_SUPPORT_RESEARCH.md`** — `*` 通配符支持研究（2026-07-19）
2. **`docs/INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md`** — 行业权限架构深度研究（6 份子研究，约 19,000 行）
   - §6.3.10 — `*` 通配符支持
   - §6.3.11 — Owner 机制统一模型
   - §6.4 — 9 机制 → 3 层统一模型
   - §6.5 — 24 个月长期演进路径
3. **`docs/PERMISSION_TODOS.md`** — 权限体系专题待办（P0-P4）
4. **`docs/auth/role-migration-guide.md`** — 3 阶段灰度发布指南
5. **`docs/CLOUD_IAM_ARCHITECTURE_RESEARCH.md`** — 云厂商 IAM 架构研究
6. **`docs/PERMISSION_ACADEMIC_MODELS_RESEARCH.md`** — 学术理论模型研究
7. **`docs/ENTERPRISE_APP_PERMISSION_RESEARCH.md`** — 企业应用权限研究
8. **`docs/COMPLIANCE_FRAMEWORK_PERMISSION_RESEARCH.md`** — 合规框架权限研究

行业研究覆盖 29+ 头部产品/模型，提炼出 5 大业界共识：

- **共识 1**: 数据权限 = 条件表达式（读权限本质）
- **共识 2**: 声明式 > 命令式（BO.yaml 声明式配置）
- **共识 3**: PDP/PEP 分离（权限决策点与执行点分离）
- **共识 4**: Deny 优先 / Secure by Default
- **共识 5**: 资源层级继承（6 层 HIERARCHY\_CHAIN）

### 1.2 核心问题（11 大问题）

#### 问题 1: 11 机制并存，缺乏统一模型（M1-M11 重新编号，消除歧义）

当前权限体系有 11 个机制并存，分散在 20+ Python 模块：

| 机制  | 名称                 | 实现位置                                                     | 状态               |
| --- | ------------------ | -------------------------------------------------------- | ---------------- |
| M1  | Functional Perm    | `permission_interceptor.py`                              | ✅ 主路径            |
| M2  | Dim Scope          | `dimension_scope_engine.py`                              | ✅ 主路径            |
| M3  | Visibility Scope   | `data_permission_interceptor.py`                         | ✅ 主路径            |
| M4  | Owner Exception    | `owner_chain_interceptor.py` + `chain_owner_resolver.py` | ✅ 主路径            |
| M5  | Instance Perm      | `data_permission_interceptor.py`                         | ⚠️ 部分            |
| M6  | Condition Rule     | `condition_evaluator.py` + `permission_rules` 表          | ✅ 主路径            |
| M7  | Field Mask         | `field_policy_interceptor.py`                            | ⚠️ 部分            |
| M8  | Owner Auto Perm    | `owner_permission_interceptor.py`                        | ✅ 主路径            |
| M9  | YAML RLS           | `rls_rules/*.yaml` + `rls/loader.py`                     | ⚠️ \[DECORATIVE] |
| M10 | Prohibition        | ❌ 缺失                                                     | ❌ 待设计            |
| M11 | Resource Hierarchy | `hierarchy_validation_interceptor.py`                    | ⚠️ 部分            |

**注1**: v1 spec 中 "M11 YAML RLS" 与新增的 "M11 Resource Hierarchy" 命名冲突，v2 重新编号为 M9 (YAML RLS) / M10 (Prohibition) / M11 (Resource Hierarchy)，消除歧义。

**注2 (v2 Visibility 研究)**: §3.18 Visibility 统一模型研究结论——M3 (Visibility Scope) 统一到 `data_permission_rules` 的 `rule_type='visibility'`，M3 不再是独立机制。**统一后实际机制数：11 → 10**（M3 作为 rule\_type 保留，但不独立计数）。6/7 行业头部产品（Salesforce/SAP CAP/ServiceNow/飞书/AWS IAM/Dynamics 365）将 visibility 统一到权限模型，验证了此方案的合理性。

#### 问题 2: `*` 通配符支持不完整

| 层级                  | 当前支持 `*`      | 需要支持               |
| ------------------- | ------------- | ------------------ |
| 功能权限（M1）            | ✅ 已支持         | -                  |
| Dimension Scope（M2） | ❌ 不支持         | `scope_mode='all'` |
| Condition（M6）       | ❌ 不支持         | `condition='*'`    |
| 写路径（V2.1）           | ✅ 功能权限 `*` 跳过 | dimension `*` 也需跳过 |

#### 问题 3: Owner 机制分散，读/写路径不对称

Owner 逻辑分散在 4 个模块：

- `owner_chain_interceptor.py` — 写路径
- `chain_owner_resolver.py` — 共享解析
- `write_scope_interceptor.py` — 写路径集成
- `data_permission_interceptor.py` L859-962 — 读路径

#### 问题 4: 三层权限体系并存（核心架构债）

1. **M9 YAML RLS**（`rls_rules/*.yaml`）— v1.4.0 已 130% 完成，但仍是 `[DECORATIVE]`
2. **DimensionScopeEngine**（运行时派生，实际主路径）
3. **DataPermissionService**（旧表，已为空）

#### 问题 5: 缺乏 PDP/PEP 分离

权限决策逻辑分散在 11+ 拦截器中，没有统一的 PDP。

#### 问题 6: 缺乏 5 维正交模型

当前权限检查没有明确的 5 维正交模型（Action / Field / Row / Owner / Org）。

#### 问题 7: 缺乏声明式配置

权限配置分散在 Python 硬编码、数据库表、YAML 文件中。

#### 问题 8: 缺乏 M10 Prohibition

当前只有 Allow 规则，没有 Deny 规则（Prohibition）。

#### 问题 9: V2.1 写路径联动未明确（v2 补充）

`write_scope_interceptor.py` L38-40 的 `_WRITE_SCOPE_V2_1_PERM_CHECK` 开关体现了关键联动：

- **读路径**: 功能权限 ∩ 数据权限（正交）
- **写路径**: 功能权限 → 数据权限（串联，前置条件）

spec v1 未明确这个联动关系。

#### 问题 10: UI 3 Panel 改造未规划（v2 补充）

前端 `PermissionConfigPanel.vue` 有 3 个 Panel：

- Panel 1: 功能权限（菜单与功能权限）
- Panel 2: 维度权限（role\_dimension\_scope）
- Panel 3: 条件型权限（permission\_rules）

spec v1 未详细描述 UI 改造。

#### 问题 11: 管理维度映射链未明确（v2 补充）

`permission_dimension_engine.py` L28-46 体现了映射链：

```
管理维度（组织、部门） → role dimension → 数据权限（condition）
```

spec v1 未明确这个映射链。

### 1.3 目标

1. **11 机制 → 10 机制 → 3 层 → 1 统一 PermissionResolver** — 统一权限决策入口（M3 Visibility 统一到 rule\_type 后不再独立）
2. **5 维正交权限模型** — Action / Field / Row / Owner / Org 独立检查
3. **PDP/PEP 分离** — PermissionResolver 作为 PDP，拦截器改造为 PEP
4. **data\_permission\_rules 统一表** — 合并 `role_dimension_scopes` + `permission_rules` + Visibility 配置
5. **`*`** **通配符全面支持** — 功能权限、Dimension Scope、Condition 三层均支持
6. **Owner 机制统一** — 统一到 `rule_type='owner'`，读/写路径对称
7. **Visibility 机制统一** — M3 统一到 `rule_type='visibility'`，保留 DB 列（性能+UI+兼容），与行业实践一致
8. **M10 Prohibition** — 新增 Deny 规则，Deny 优先
9. **M11 Resource Hierarchy Inheritance** — 资源层级继承（5 条规则完整）
10. **声明式配置** — BO.yaml 统一声明式权限配置
11. **Secure by Default** — 默认拒绝，`*` 受 4 层约束
12. **V2.1 写路径联动** — 明确读写路径联动关系
13. **UI 3 Panel 改造** — 适配统一模型
14. **3 阶段灰度发布** — audit-only → soft-default → hard-reject
15. **三级缓存** — L1/L2/L3 性能优化
16. **审计与合规** — 完整决策日志 + 合规报告

### 1.4 范围

**包含**：

- P0.1 BUG-V026 修复验证
- P1.1 三层权限体系统一
- P1.6 `*` 通配符支持
- 6.3.11 Owner 机制统一
- Visibility 统一模型（M3 → rule\_type='visibility'）
- 6.4 11 → 10 机制 → 3 层统一模型（含 Visibility 统一）
- 6.5 24 个月长期演进路径
- M10 Prohibition 设计
- M11 Resource Hierarchy Inheritance（5 条规则）
- PDP/PEP 分离架构
- 5 维正交权限模型
- V2.1 写路径联动
- UI 3 Panel 改造
- 3 阶段灰度发布
- 管理维度映射链
- 声明式配置（BO.yaml）
- Profile 瘦化
- 三级缓存
- 审计与合规（含字段清洗规则）
- ReBAC 引入必要性分析

**不包含**（单独 spec）：

- 多租户隔离
- AI Agent 操作契约
- Record Type 设计

***

## 2. 现状深度分析

### 2.1 数据库表结构现状

#### 2.1.1 role\_dimension\_scopes 表（`generated_schema.sql` L308-315）

```sql
CREATE TABLE IF NOT EXISTS role_dimension_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    dimension_code VARCHAR(200) NOT NULL,
    dimension_values TEXT NOT NULL,
    inherit_children INTEGER DEFAULT 1,
    scope_mode VARCHAR(200) DEFAULT 'include'
)
```

**Gap**: `scope_mode` 枚举只有 `include` / `exclude`，缺少 `all`。

#### 2.1.2 permission\_rules 表（`generated_schema.sql` L263-275）

```sql
CREATE TABLE IF NOT EXISTS permission_rules (
    role_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    condition TEXT NOT NULL,
    permission_level VARCHAR(200) NOT NULL DEFAULT 'read',
    is_denied INTEGER DEFAULT 0,
    inherit_to_children INTEGER DEFAULT 1,
    propagate_to_parents INTEGER DEFAULT 1,
    analysis_mode VARCHAR(200),
    created_at VARCHAR(200),
    created_by INTEGER,
    updated_at VARCHAR(200)
)
```

**Gap**: 没有 `rule_type` 字段，无法与 `role_dimension_scopes` 统一。

#### 2.1.3 role\_permissions 表（`generated_schema.sql` L318-323）

```sql
CREATE TABLE IF NOT EXISTS role_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    created_at DATETIME
)
```

### 2.2 拦截器架构现状（v2 补充：11 个权限相关拦截器）

当前有 20+ 拦截器，**权限相关的有 11 个**（v1 只列了 8 个，v2 补充 3 个）：

| 拦截器                               | 职责         | 机制          | v2 新增  |
| --------------------------------- | ---------- | ----------- | ------ |
| `PermissionInterceptor`           | 功能权限检查     | M1          | <br /> |
| `DataPermissionInterceptor`       | 数据权限（读路径）  | M2/M3/M4/M5 | <br /> |
| `WriteScopeInterceptor`           | 写路径数据范围    | V2.1 联动     | <br /> |
| `OwnerChainInterceptor`           | Owner 链检查  | M4          | <br /> |
| `OwnerAutoPermissionInterceptor`  | Owner 自动权限 | M8          | <br /> |
| `FieldPolicyInterceptor`          | 字段策略       | M7          | <br /> |
| `HierarchyValidationInterceptor`  | 层级校验       | M11         | <br /> |
| `AssociationInterceptor`          | 关联处理       | M11         | <br /> |
| `VersionContextInterceptor`       | 版本上下文过滤    | M2 辅助       | ✅ v2   |
| `ConstraintValidationInterceptor` | 约束校验       | M10 辅助      | ✅ v2   |
| `EnumProtectionInterceptor`       | 枚举保护       | M7 辅助       | ✅ v2   |

**v2 补充说明**：

- `VersionContextInterceptor` — 注入版本上下文过滤条件，确保用户只能看到当前版本上下文中的数据
- `ConstraintValidationInterceptor` — 集成 ConstraintEngine，在 BO 操作前后执行约束检查（M10 Prohibition 的辅助）
- `EnumProtectionInterceptor` — 保护枚举类型和枚举值的完整性，基于三层矩阵控制

### 2.3 `*` 通配符使用现状

#### 2.3.1 功能权限 `*`（`permission_interceptor.py` L85-88）

```python
def user_info_has_perm(permissions, required: str) -> bool:
    if '*' in permissions:
        return True
    return required in permissions
```

#### 2.3.2 写路径 `*` 跳过（`write_scope_interceptor.py` L343-344）

```python
if '*' in permissions:
    return  # 跳过写路径检查
```

#### 2.3.3 数据权限 `*` 跳过（`data_permission_interceptor.py` L727-736）

通配符跳过过滤器，然后添加 owner 例外。

### 2.4 Condition Evaluator 现状

- **支持操作符**: `=`, `!=`, `<`, `>`, `<=`, `>=`, `IN`, `NOT IN`, `LIKE`, `STARTS_WITH`, `CONTAINS`
- **白名单字段**: `id`, `product_id`, `version_id`, `domain_id`, `sub_domain_id`, `service_module_id`, `business_object_id`, `domain_type`, `code`, `name`, `status`, `created_by`, `owner_id`, `organization_id`, `department_id`, `resource_type`, `category`, `type`
- **未支持** **`*`** **通配符**

### 2.5 Dimension Scope Engine 现状

- `expand_dimension_values`（L148-207）: 只支持 JSON list 格式，不支持 `*`
- `derive_data_conditions`（L209+）: 根据展开的维度值派生 SQL 条件
- `HIERARCHY_CHAIN` = `['product', 'version', 'domain', 'sub_domain']`
- `VERSION_AWARE_BOS` = `{'service_module', 'business_object', 'relationship'}`
- `ALWAYS_VISIBLE_BOS` = `{'enum_type', 'enum_value', 'user', 'role', ...}`

### 2.6 Owner 机制现状

Owner 逻辑分散在 4 个模块：

1. **`owner_chain_interceptor.py`** — 写路径 owner 检查
   - 路径 1: 直接 `owner_id` 字段
   - 路径 2: 沿 `HIERARCHY_CHAIN` 向上追 `product.owner_id`
   - 路径 3: fallback to `created_by`
2. **`chain_owner_resolver.py`** — 共享的 chain owner 解析
3. **`write_scope_interceptor.py`** — 写路径集成
4. **`data_permission_interceptor.py`** **L859-962** — 读路径 owner exception

### 2.7 M9 YAML RLS 现状（v2 重编号）

- v1.4.0 已 130% 完成（155 PASS 测试）
- 36 个 BO YAML 全覆盖
- 但仍是 `[DECORATIVE]` 标记，主路径仍是 DimensionScopeEngine
- D1-D5 + TODO 1-6 全部完成，TODO-7（M10 协同）留待

### 2.8 V2.1 写路径联动现状（v2 补充）

`write_scope_interceptor.py` L38-40 的 `_WRITE_SCOPE_V2_1_PERM_CHECK` 开关：

```python
_WRITE_SCOPE_V2_1_PERM_CHECK = True  # v2.1: 功能权限是 dim scope 派生的前置条件
```

**联动关系**：

- **读路径**: 功能权限 ∩ 数据权限（正交，独立检查）
- **写路径**: 功能权限 → 数据权限（串联，功能权限是数据权限派生的前置条件）

**含义**：

- 读：用户有 `product:read` 功能权限 + 在 dim scope 内 → 允许读
- 写：用户有 `product:update` 功能权限 → 才能进入 dim scope 检查 → 在 dim scope 内 → 允许写

### 2.9 UI 3 Panel 现状（v2 补充）

前端 `PermissionConfigPanel.vue` L11-75 有 3 个 Panel：

| Panel   | 名称      | 数据源                     | 作用                        |
| ------- | ------- | ----------------------- | ------------------------- |
| Panel 1 | 菜单与功能权限 | `role_permissions`      | 配置角色的功能权限                 |
| Panel 2 | 维度权限    | `role_dimension_scopes` | 配置角色的 dimension scope     |
| Panel 3 | 条件型权限   | `permission_rules`      | 配置角色的条件型权限（独立于 dim scope） |

**Gap**: Panel 3 的条件型权限与 Panel 2 的 dim scope 未统一，UI 需要适配统一模型。

### 2.10 管理维度映射链现状（v2 补充）

`permission_dimension_engine.py` L28-46：

```python
RESOURCE_TABLE_MAP = {
    'product': 'products',
    'version': 'versions',
    'domain': 'domains',
    'sub_domain': 'sub_domains',
}
PARENT_FIELD_MAP = {
    'version': 'product_id',
    'domain': 'version_id',
    'sub_domain': 'domain_id',
}
```

**映射链**：

```
管理维度（组织、部门）  ← UI 配置
    ↓ 映射
role dimension（product/version/domain/sub_domain）
    ↓ 派生
数据权限（condition: field IN (...)）
```

### 2.11 Gap 分析矩阵（v2 更新）

| 层级                     | 当前状态             | 需要改进                                     |
| ---------------------- | ---------------- | ---------------------------------------- |
| 功能权限（M1）               | ✅ 支持 `*`         | 统一到 PDP                                  |
| Dimension Scope（M2）    | ❌ 不支持 `*`        | 支持 `scope_mode='all'`                    |
| Visibility Scope（M3）   | ✅ 主路径            | 统一到 `rule_type='visibility'`，不再独立（§3.18） |
| Owner Exception（M4）    | ❌ 分散             | 统一到 `rule_type='owner'`                  |
| Instance Perm（M5）      | ⚠️ 部分            | 统一到 PDP                                  |
| Condition Rule（M6）     | ❌ 不支持 `*`        | 支持 `condition='*'`                       |
| Field Mask（M7/M8）      | ⚠️ 部分            | 统一到 PDP                                  |
| M9 YAML RLS            | ⚠️ \[DECORATIVE] | 成为 SSOT 或与 DimensionScope 统一             |
| M10 Prohibition        | ❌ 缺失             | 新增 Deny 规则                               |
| M11 Resource Hierarchy | ⚠️ 部分            | 完善 Resource 模型 + 5 条继承规则                 |
| V2.1 写路径联动             | ⚠️ 有开关未明确        | 明确读写路径联动                                 |
| UI 3 Panel             | ⚠️ 未统一           | 适配统一模型                                   |
| 3 阶段灰度发布               | ⚠️ 有文档未执行        | 实施 3 阶段策略                                |
| 管理维度映射链                | ⚠️ 有实现未明确        | 明确映射链语义                                  |
| PDP/PEP 分离             | ❌ 缺失             | PermissionResolver 作为 PDP                |
| 5 维正交                  | ❌ 缺失             | Action / Field / Row / Owner / Org       |
| 声明式配置                  | ⚠️ 部分            | BO.yaml 统一声明式                            |
| Profile 瘦化             | ❌ 缺失             | 用户身份与权限解耦                                |
| 三级缓存                   | ❌ 缺失             | L1/L2/L3                                 |
| 审计字段清洗                 | ⚠️ 有实现未规范        | 规范清洗规则                                   |
| ReBAC 引入               | ❌ 未分析            | 分析必要性                                    |

***

## 3. 统一模型设计

### 3.1 3 层权限模型

11 机制收敛为 3 层（统一后 M3 不再独立，实际 10 机制）：

```
Layer 1: 功能权限 (Functional Permission)  ← M1
Layer 2: 数据权限 (Data Permission)         ← M2/M3(rule_type='visibility')/M4/M5/M6/M9/M10/M11
Layer 3: 字段权限 (Field Security)          ← M7/M8
```

> **注**: M3 (Visibility Scope) 统一到 `data_permission_rules` 的 `rule_type='visibility'` 后，不再作为独立机制计数，但仍保留在 Layer 2 中作为 rule\_type。详见 §3.18。

### 3.2 data\_permission\_rules 统一表设计

```sql
CREATE TABLE IF NOT EXISTS data_permission_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    rule_type VARCHAR(50) NOT NULL,
    -- rule_type: 'dimension' | 'condition' | 'visibility' | 'owner' | 'prohibition'
    resource_type VARCHAR(200),
    dimension_code VARCHAR(200),
    condition TEXT,
    scope_mode VARCHAR(20) DEFAULT 'include',
    -- scope_mode: 'include' | 'exclude' | 'all'
    permission_level VARCHAR(50) DEFAULT 'read',
    -- permission_level: 'read' | 'write' | 'admin'
    is_denied INTEGER DEFAULT 0,
    inherit_to_children INTEGER DEFAULT 1,
    propagate_to_parents INTEGER DEFAULT 1,
    analysis_mode VARCHAR(200),
    created_at VARCHAR(200),
    created_by INTEGER,
    updated_at VARCHAR(200),
    FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE INDEX idx_dpr_role ON data_permission_rules(role_id);
CREATE INDEX idx_dpr_type ON data_permission_rules(rule_type);
CREATE INDEX idx_dpr_resource ON data_permission_rules(resource_type);
```

### 3.3 5 维正交权限模型

```
Layer 1: Action (功能权限) — M1
  - 检查 user 是否有 resource:action 权限
  - 支持 * 通配符

Layer 2: Field (字段权限) — M7/M8
  - 检查 user 是否能访问特定字段
  - 独立于 Row 层

Layer 3: Row (数据权限) — M2/M3/M6/M9
  - 检查 user 是否能访问特定行
  - dimension scope + condition + visibility scope

Layer 4: Owner (Owner 例外) — M4/M8
  - 检查 user 是否是 resource 的 owner
  - 3 路径: direct / chain / fallback

Layer 5: Org (组织约束) — M10/M11
  - 检查组织级约束
  - Prohibition (Deny 优先) + Resource Hierarchy
```

### 3.4 PDP/PEP 分离架构

```
┌─────────────────────────────────────────┐
│           PEP (Policy Enforcement Point) │
│  ┌─────────────────────────────────┐    │
│  │  PermissionInterceptor (M1)     │    │
│  │  DataPermissionInterceptor      │    │
│  │  WriteScopeInterceptor (V2.1)   │    │
│  │  OwnerChainInterceptor (M4)     │    │
│  │  FieldPolicyInterceptor (M7)    │    │
│  │  OwnerAutoPermissionInterceptor │    │
│  │  VersionContextInterceptor (v2) │    │
│  │  ConstraintValidationInter. (v2)│    │
│  │  EnumProtectionInterceptor (v2) │    │
│  │  HierarchyValidationInterceptor │    │
│  │  AssociationInterceptor         │    │
│  └─────────────────────────────────┘    │
│                  │ delegate              │
│                  ▼                       │
│  ┌─────────────────────────────────┐    │
│  │  PermissionResolver (PDP)       │    │
│  │  ┌───────────────────────────┐  │    │
│  │  │ 5 层决策                  │  │    │
│  │  │ 0. Prohibition (M10)      │  │    │
│  │  │ 1. Action (M1)            │  │    │
│  │  │ 2. Field (M7/M8)          │  │    │
│  │  │ 3. Row (M2/M3/M6/M9)      │  │    │
│  │  │ 4. Owner (M4/M8)          │  │    │
│  │  │ 5. Org (M10/M11)          │  │    │
│  │  └───────────────────────────┘  │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

### 3.5 PermissionResolver 统一 PDP

```python
class PermissionResolver:
    """统一权限决策点（PDP）"""

    def __init__(self, data_source):
        self._ds = data_source
        self._condition_eval = ConditionEvaluator()
        self._dimension_engine = DimensionScopeEngine(data_source)
        self._owner_resolver = ChainOwnerResolver(data_source)
        self._cache = PermissionCache()

    def check(self, user, action, resource_type, resource=None, resource_id=None):
        """5 维正交权限检查"""
        # Layer 0: Prohibition (Deny 优先)
        if self._check_prohibition(user, action, resource_type, resource):
            return Deny("prohibition denied")

        # Layer 1: Action (功能权限)
        if not self._check_action(user, action, resource_type):
            return Deny("missing functional permission")

        # Layer 2: Field (字段级)
        if not self._check_field(user, action, resource_type):
            return Deny("field mask denied")

        # Layer 3: Row (数据权限)
        if not self._check_row(user, action, resource_type, resource, resource_id):
            return Deny("row filter denied")

        # Layer 4: Owner (owner exception)
        if not self._check_owner(user, action, resource_type, resource, resource_id):
            return Deny("owner check failed")

        # Layer 5: Org (组织级约束)
        if not self._check_org(user, action, resource_type, resource, resource_id):
            return Deny("org level denied")

        return Allow()
```

### 3.6 Resource 模型与权限继承

#### 3.6.1 Resource 模型颗粒度

| 类型                     | 定义      | 示例                           | 权限继承           |
| ---------------------- | ------- | ---------------------------- | -------------- |
| **独立资源** (Independent) | 独立管理的资源 | product, user, role          | 不继承            |
| **关联资源** (Association) | 表达对象关系  | relationship                 | 不继承            |
| **附属资源** (Subordinate) | 依附于父资源  | annotation, audit\_log       | 自动继承 parent 权限 |
| **层级资源** (Hierarchy)   | 层级链中的资源 | version, domain, sub\_domain | 向下展开，不自动继承     |

#### 3.6.2 权限继承 5 条规则（v2 补充完整）

代码 `write_scope_interceptor.py` L730-750 的 `_check_ancestor_dim_scope` 和 `_check_parent_dim_scope` 体现了 5 条规则：

| 规则   | 名称    | 描述                                  | 实现                          |
| ---- | ----- | ----------------------------------- | --------------------------- |
| 规则 1 | 向下继承  | parent 的 dim scope 向下展开到 children   | `inherit_children=1`        |
| 规则 2 | 加严不放松 | children 的 dim scope 不能比 parent 更宽松 | `_check_ancestor_dim_scope` |
| 规则 3 | 关联取交集 | Association 关系的资源取两端 dim scope 交集   | `_check_parent_dim_scope`   |
| 规则 4 | 附属跟随  | Subordinate 资源自动继承 parent 的 owner   | `owner_chain_interceptor`   |
| 规则 5 | 向上传播  | children 的 dim scope 变更向上传播到 parent | `propagate_to_parents=1`    |

### 3.7 声明式配置（BO.yaml）

```yaml
# meta/schemas/product.yaml
permission:
  functional:
    - grant: ['READ', 'CREATE', 'UPDATE', 'DELETE']
      to: ['product_manager', 'admin']
  data:
    dimension_scope:
      dimension: product
      field: id
      filter_type: direct
    owner_rule:
      owner_field: owner_id
      fallback_field: created_by
      chain_inheritance: hierarchy_chain
    condition: "status = 'active'"
  field_mask:
    public: ['id', 'name', 'code', 'status']
    restricted: ['owner_id', 'created_by']
  prohibition:
    - condition: "status = 'archived'"
      grant: ['DELETE']
```

### 3.8 `*` 通配符统一语义

| 层级              | `*` 语义                                               | 实现                                  |
| --------------- | ---------------------------------------------------- | ----------------------------------- |
| 功能权限            | `*` 在 permissions 集合 = 所有功能放行                        | `user_info_has_perm()` 已支持          |
| Dimension Scope | `scope_mode='all'` 或 `dimension_values='*'` = 全量维度值  | `expand_dimension_values()` 查询所有 ID |
| Condition       | `condition='*'` = 无条件匹配（SQL `1=1`）                   | `evaluate()` 直接返回 True              |
| Owner           | `rule_type='owner'` + `condition='*'` = 所有 owner 可访问 | 等价于 dimension `*`                   |

### 3.9 Owner 统一模型

`rule_type='owner'` 的 condition 结构：

```json
{
    "rule_type": "owner",
    "condition": {
        "owner_field": "owner_id",
        "fallback_field": "created_by",
        "chain_inheritance": "hierarchy_chain",
        "inherit_to_children": true
    },
    "resource_type": "product"
}
```

3 路径统一校验：

```python
def check_owner(rule_def, user, resource):
    # 路径 1：显式 owner 字段
    if resource.get(rule_def.get('owner_field', 'owner_id')) == user.id:
        return True
    # 路径 2：Fallback to created_by
    fallback = rule_def.get('fallback_field', 'created_by')
    if fallback:
        created_by = resource.get(fallback)
        if created_by and (created_by == user.username or created_by == user.id):
            return True
    # 路径 3：链式 owner
    if rule_def.get('chain_inheritance') == 'hierarchy_chain':
        return resolve_chain_owner(resource) == user.id
    return False
```

### 3.10 M10 Prohibition

新增 `rule_type='prohibition'` 或 `is_denied=1`：

```json
{
    "rule_type": "prohibition",
    "condition": "status = 'archived'",
    "permission_level": "delete",
    "resource_type": "product"
}
```

Deny 优先原则：

- Prohibition 检查在所有 Allow 之前
- 任何 Prohibition 匹配 = 立即 Deny
- 即使有 `*` 通配符，Prohibition 仍然生效

### 3.11 M11 Resource Hierarchy Inheritance

#### 3.11.1 HIERARCHY\_CHAIN

```
product → version → domain → sub_domain → service_module → business_object
```

#### 3.11.2 继承规则（5 条完整）

见 §3.6.2。

### 3.12 Secure by Default + Deny 优先

```
默认行为（未配置任何 scope）:
  功能权限: 无 → 403
  Dimension Scope: 无 → 仅 owner 可访问
  Condition: 无 → 拒绝
  Owner: 无 → 拒绝

显式配置 *:
  功能权限: * → 所有功能放行
  Dimension Scope: * → 所有维度值放行
  Condition: * → 所有数据放行

4 层约束:
  1. visibility scope 约束 — * 不突破可见性边界
  2. org level 约束 — * 不突破组织边界
  3. field mask 约束 — * 不突破字段级安全
  4. Prohibition 约束 — * 可被 Deny 覆盖
```

### 3.13 三级缓存

```
L1 Cache (请求级) — 单次请求内缓存
  - TTL: 请求生命周期
  - 存储: 用户权限列表
  - 命中率: > 90%

L2 Cache (角色级) — 角色权限缓存
  - TTL: 5 分钟
  - 存储: 角色的 dimension scope + permission rules
  - 失效: 角色配置变更时

L3 Cache (全局级) — 全局 schema 缓存
  - TTL: 1 小时
  - 存储: BO.yaml + dimension_object_mapping.yaml
  - 失效: 配置文件变更时
```

### 3.14 V2.1 写路径联动（v2 补充）

**读路径（正交）**：

```
用户请求 → PermissionInterceptor (M1) → DataPermissionInterceptor (M2/M3)
         ↓                              ↓
         功能权限检查                    数据权限检查
         (独立)                         (独立)
         ↓                              ↓
         Allow/Deny                     Allow/Deny
                    ↓
                    两者都 Allow → 允许读
```

**写路径（串联）**：

```
用户请求 → PermissionInterceptor (M1) → WriteScopeInterceptor (V2.1)
         ↓                              ↓
         功能权限检查                    数据权限检查
         (前置条件)                     (依赖功能权限)
         ↓                              ↓
         Allow                           检查 dim scope + owner
         ↓                              ↓
                    两者都 Allow → 允许写
```

**关键差异**：

- 读：功能权限和数据权限独立检查（正交）
- 写：功能权限是数据权限的前置条件（串联），`_WRITE_SCOPE_V2_1_PERM_CHECK` 开关控制

### 3.15 管理维度映射链（v2 补充）

```
┌─────────────────────────────────────┐
│ UI 层: 管理维度配置                  │
│ (组织、部门、团队)                   │
└──────────────┬──────────────────────┘
               ↓ 映射
┌─────────────────────────────────────┐
│ role dimension (role_dimension_     │
│ scopes)                             │
│ - dimension_code: product/version/  │
│   domain/sub_domain                 │
│ - dimension_values: [1, 5, 10]      │
└──────────────┬──────────────────────┘
               ↓ 派生
┌─────────────────────────────────────┐
│ 数据权限 (condition)                │
│ - product.id IN (1, 5, 10)          │
│ - version.product_id IN (1, 5, 10)  │
│ - ...                               │
└─────────────────────────────────────┘
```

**映射规则**：

- 管理维度 → role dimension: 1:N 映射（一个管理维度可映射多个 role dimension）
- role dimension → condition: 自动派生（DimensionScopeEngine）

### 3.16 数据权限 = 读权限语义（v2 补充）

`write_scope_interceptor.py` L728-748 明确：

**语义**：

- `role_dimension_scope` 背后是条件表达式（`field IN (...)`）
- 数据权限本质是 **read 的权限**（控制能读哪些数据）
- 写权限 = 功能权限（M1）+ 数据权限（M2）+ Owner 检查（M4）的串联

**统一模型**：

```
读权限 = 功能权限(read) ∩ 数据权限(condition)
写权限 = 功能权限(write) → 数据权限(condition) → Owner 检查
```

### 3.17 审计字段清洗规则（v2 补充）

`write_scope_interceptor.py` L2200-2380 的 `_is_fk_value_in_scope` 体现了清洗逻辑：

**清洗规则**：

- `legacy_null` → `-`
- `null` → `-`
- `undefined` → `-`
- `none` → `-`
- `n/a` → `-`
- `na` → `-`
- 空字符串 → `-`

**统一实现**：

```python
def clean_audit_field(value):
    """清洗审计字段的历史占位值"""
    if value is None:
        return '-'
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ('legacy_null', 'null', 'undefined', 'none', 'n/a', 'na', ''):
            return '-'
    return value
```

**应用场景**：所有 enum/关系类型字段渲染时需清洗。

### 3.18 Visibility 统一模型研究（v2 补充）

#### 3.18.1 当前 Visibility Scope (M3) 实现

`data_permission_interceptor.py` 中 Visibility 的核心逻辑：

```sql
-- Dimension Scope + Visibility + Owner 的复合条件
WHERE (
    (dimension_scope 派生条件)              -- 维度范围
    AND                                     -- AND 叠加
    (visibility='public' OR owner_id=$user) -- visibility/owner
)
OR (owner_id = $user_id)                    -- 自己 owner 始终可见
```

**关键设计**：

- Visibility 是 **AND 叠加**在 Dimension Scope 之上的子条件
- `visibility='public'` = 所有人可见
- `visibility='private'` = 仅 owner 可见
- `ASSOCIATION_BOS_SKIP_VISIBILITY = {'relationship'}` — 关联 BO 跳过 visibility
- M11 RLS 中 annotation 的 visibility 也通过条件表达式：`annotation.created_by == $user.name OR annotation.visibility == 'public'`

#### 3.18.2 行业头部产品 Visibility 处理方式

| 产品                  | Visibility 是否权限模型一部分 | 实现方式                 | Visibility 语义                                                         |
| ------------------- | -------------------- | -------------------- | --------------------------------------------------------------------- |
| **Salesforce**      | ✅ 是                  | OWD → 条件表达式          | Private / Public Read Only / Public Read/Write / Controlled by Parent |
| **SAP CAP**         | ✅ 是                  | `@restrict` where 子句 | 无独立 visibility，全部通过 where 条件                                          |
| **ServiceNow**      | ✅ 是                  | ACL condition        | 无独立 visibility，Read ACL condition 控制                                  |
| **飞书多维表格**          | ✅ 是                  | 行权限                  | 行权限 = 数据级 visibility                                                  |
| **AWS IAM**         | ✅ 是                  | Policy condition     | 无法 GetObject = 不可见，无法 ListBucket = 不知道存在                              |
| **Dynamics 365**    | ✅ 是                  | Read privilege       | Read privilege = 0 → 记录不可见                                            |
| **Notion / Google** | ⚠️ 表面独立，底层条件         | share → 条件表达式        | private / shared / public                                             |

**6/7 头部产品将 visibility 统一到权限模型中**。

#### 3.18.3 Salesforce OWD 详细分析

Salesforce 的 OWD (Organization-Wide Defaults) 是 Visibility 的标准实现：

| OWD 设置               | 语义         | 等价条件表达式                                      |
| -------------------- | ---------- | -------------------------------------------- |
| Private              | 仅 owner 可见 | `owner_id = $user.id`                        |
| Public Read Only     | 所有人可读      | `1=1` (read) / `owner_id = $user.id` (write) |
| Public Read/Write    | 所有人可读写     | `1=1`                                        |
| Controlled by Parent | 跟随 parent  | `parent.owner_id = $user.id`                 |

**Salesforce 的 Visibility 层级**：

1. **OWD** (基线) — 表级默认 visibility
2. **Role Hierarchy** (扩展) — 上级自动看到下级数据
3. **Sharing Rules** (扩展) — 基于条件扩展 visibility（如"同部门可见"）
4. **Manual Sharing** (扩展) — 记录级手动共享

**关键洞察**：OWD 是 **默认条件表达式**，Salesforce 将 visibility 完全统一到了权限模型中。

#### 3.18.4 Visibility 的本质分析

**Visibility 与 Read 权限的区别**：

| 概念             | 语义       | 影响                  |
| -------------- | -------- | ------------------- |
| **Visibility** | 能否看到记录存在 | 列表页过滤、搜索结果过滤、关联选择过滤 |
| **Read**       | 能否读取记录内容 | 详情页访问、API 返回内容      |
| **Write**      | 能否修改记录内容 | 编辑、删除操作             |

**在我们的系统中**：

- Visibility = Read（没有区分"看到存在"和"读取内容"）
- 这与 Salesforce / SAP 一致（它们也不区分）
- ServiceNow 可以区分（ACL 分别控制 read / write / create / delete）

**Visibility 的条件表达式映射**：

| Visibility 值 | 条件表达式                                 | 语义                                  |
| ------------ | ------------------------------------- | ----------------------------------- |
| `public`     | `1=1`                                 | 所有人可见                               |
| `private`    | `owner_id = $user.id`                 | 仅 owner 可见                          |
| `team`       | `team_id IN ($user.teams)`            | 团队可见                                |
| `department` | `department_id = $user.department_id` | 部门可见                                |
| `parent`     | `parent.owner_id = $user.id`          | Controlled by Parent（Salesforce 语义） |

#### 3.18.5 统一方案：Visibility → `rule_type='visibility'`

**核心结论**：Visibility Scope (M3) 可以统一到 `data_permission_rules` 表的 `rule_type='visibility'`，无需独立机制。

**统一表配置**：

```json
{
    "rule_type": "visibility",
    "resource_type": "product",
    "condition": "visibility = 'public' OR owner_id = $user.id",
    "scope_mode": "include"
}
```

**与 Dimension Scope 的 AND 关系保持不变**：

```sql
WHERE (dimension_scope_condition) AND (visibility_condition)
```

**好处**：

1. 减少一个独立机制（11 → 10 机制，M3 不再独立）
2. Visibility 条件可配置、可审计、可通过 `*` 通配符控制
3. 与行业实践一致（6/7 产品统一到权限模型）
4. 简化 PDP 实现（PermissionResolver Row 层统一处理 dimension + visibility + condition）
5. 支持 Salesforce OWD 4 种模式（Private / Public RO / Public RW / Controlled by Parent）

**保留 Visibility 字段的理由**：

- **UI 友好**：`public` / `private` / `team` 比条件表达式更直观
- **性能优化**：Visibility 字段是 DB 列，可以直接索引，比条件表达式求值更快
- **向后兼容**：现有数据中已有 `visibility` 字段

**最终方案**：

- 保留 `visibility` 字段作为 DB 列（性能 + UI 友好 + 向后兼容）
- 统一到 `data_permission_rules` 的 `rule_type='visibility'` 作为配置入口（与权限模型统一）
- Visibility 字段值 → 自动生成条件表达式
- 这与 Salesforce 的做法一致：OWD 是权限配置入口，底层仍是 ACL 条件

#### 3.18.6 Visibility → 条件表达式自动映射

```python
VISIBILITY_CONDITION_MAP = {
    'public': '1=1',                                          # 所有人可见
    'private': 'owner_id = {user_id}',                        # 仅 owner 可见
    'team': 'team_id IN ({user_team_ids})',                   # 团队可见
    'department': 'department_id = {user_department_id}',     # 部门可见
    'parent': 'parent.owner_id = {user_id}',                  # Controlled by Parent
}

def generate_visibility_condition(visibility_value, user):
    """将 visibility 字段值转化为条件表达式"""
    template = VISIBILITY_CONDITION_MAP.get(visibility_value)
    if not template:
        return f"visibility = '{visibility_value}'"  # fallback
    return template.format(
        user_id=user.id,
        user_team_ids=','.join(str(t) for t in user.team_ids),
        user_department_id=user.department_id,
    )
```

#### 3.18.7 对 11 机制的影响

| 机制                    | 变化   | 说明                                                              |
| --------------------- | ---- | --------------------------------------------------------------- |
| M3 (Visibility Scope) | 不再独立 | 统一到 `rule_type='visibility'`，逻辑仍在 data\_permission\_interceptor |
| M2 (Dim Scope)        | 不变   | 与 visibility 的 AND 关系保持                                         |
| M4 (Owner Exception)  | 不变   | visibility='private' 等价于 owner exception                        |

**机制数量**：11 → 10（M3 不再是独立机制，但仍作为 rule\_type 存在）

#### 3.18.8 实施清单

1. 扩展 `data_permission_rules` 表，新增 `rule_type='visibility'`
2. 实现 `generate_visibility_condition()` 映射函数
3. 迁移现有 visibility 字段值到 `data_permission_rules`
4. 在 PermissionResolver Row 层统一处理 visibility 条件
5. 保留 `visibility` DB 列（性能 + UI + 向后兼容）
6. UI 支持配置 visibility 级别（public / private / team / department / parent）
7. 审计日志记录 visibility 变更

***

## 4. 详细方案

### 4.1 Phase 1: `*` 通配符全面支持（P1.6，1-2 周）

#### 4.1.1 扩展 role\_dimension\_scopes.scope\_mode 枚举

```yaml
# meta/schemas/role_dimension_scope.yaml
- id: scope_mode
  name: 范围模式
  type: string
  db_column: scope_mode
  default: include
  enum_values:
    - include
    - exclude
    - all  # 新增
```

#### 4.1.2 DimensionScopeEngine 支持 `*`

```python
def expand_dimension_values(self, role_id: int) -> Dict[str, Set[int]]:
    scopes = self._load_scopes(role_id)
    expanded = {}
    for scope in scopes:
        code = scope['dimension_code']

        # 新增：scope_mode='all' 或 dimension_values='*'
        if scope.get('scope_mode') == 'all' or scope.get('dimension_values') == '*':
            all_ids = self._get_all_dimension_ids(code)
            expanded[code] = set(all_ids)
            if scope.get('inherit_children') == 1:
                self._expand_to_children(code, all_ids, expanded)
            continue

        # 原有逻辑不变
        ...
    return expanded

def _get_all_dimension_ids(self, dimension_code: str) -> List[int]:
    """查询维度的所有 ID"""
    table_map = {
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
        'sub_domain': 'sub_domains',
    }
    table = table_map.get(dimension_code)
    if not table:
        return []
    rows = self._ds.execute(f"SELECT id FROM {table}").fetchall()
    return [row[0] for row in rows]
```

#### 4.1.3 ConditionEvaluator 支持 `*`

```python
def evaluate(self, condition: str, resource: Dict[str, Any]) -> bool:
    """评估条件表达式"""
    # 新增：* 通配符 = 无条件匹配
    if not condition or condition.strip() == '*':
        return True

    # 原有逻辑不变
    ...
```

#### 4.1.4 写路径拦截器同步支持

```python
# write_scope_interceptor.py
def _check_dim_scope_wildcard(self, role_id):
    """检查角色是否配置了 dimension scope '*'"""
    scopes = self._load_scopes(role_id)
    for scope in scopes:
        if scope.get('scope_mode') == 'all' or scope.get('dimension_values') == '*':
            return True
    return False

def before_action(self, context):
    ...
    if '*' in permissions:
        return  # 功能权限 * 跳过
    if self._check_dim_scope_wildcard(role_id):
        return  # dimension scope * 跳过
    ...
```

#### 4.1.5 UI 增加"全部"选项

权限配置 UI 的 DimensionScopePanel 增加"全部"选项，对应 `scope_mode='all'`。

#### 4.1.6 审计日志记录 `*` 配置

```python
def audit_wildcard_config(role_id, scope_type, configured_by):
    """配置 * 时记录审计日志"""
    log_audit(
        event='wildcard_permission_configured',
        role_id=role_id,
        scope_type=scope_type,
        configured_by=configured_by,
        severity='high',
    )
```

### 4.2 Phase 2: Owner 机制统一（6.3.11，2-3 周）

#### 4.2.1 data\_permission\_rules 增加 rule\_type='owner'

```sql
INSERT INTO data_permission_rules (role_id, rule_type, resource_type, condition, permission_level)
SELECT
    r.id,
    'owner',
    'product',
    '{"owner_field": "owner_id", "fallback_field": "created_by", "chain_inheritance": "hierarchy_chain"}',
    'write'
FROM roles r
WHERE r.code IN ('admin', 'user', 'auditor');
```

#### 4.2.2 PermissionResolver 实现 check\_owner()

见 §3.5 和 §3.9。

#### 4.2.3 迁移 owner\_chain\_interceptor 逻辑

```python
class OwnerChainInterceptor(Interceptor):
    def before_action(self, context):
        resolver = get_permission_resolver()
        result = resolver.check_owner(
            user=context.user,
            action=context.action,
            resource_type=context.object_type,
            resource=context.record,
        )
        if not result:
            raise PermissionDenied("owner check failed")
```

#### 4.2.4 附属资源自动继承

```yaml
# 在 BO.yaml 中声明附属资源
annotation:
  resource_type: subordinate
  parent: parent_object
  inherit_owner: true
```

#### 4.2.5 统一读/写路径

读路径和写路径统一委托 `PermissionResolver.check_owner()`。

### 4.3 Phase 3: data\_permission\_rules 统一表（P1.1，3-4 周）

#### 4.3.1 创建 data\_permission\_rules 表

见 §3.2 DDL。

#### 4.3.2 迁移 role\_dimension\_scopes 数据

```sql
INSERT INTO data_permission_rules (role_id, rule_type, dimension_code, condition, scope_mode, permission_level)
SELECT
    role_id,
    'dimension',
    dimension_code,
    dimension_values,
    scope_mode,
    'read'
FROM role_dimension_scopes;
```

#### 4.3.3 迁移 permission\_rules 数据

```sql
INSERT INTO data_permission_rules (role_id, rule_type, resource_type, condition, permission_level, is_denied, inherit_to_children, propagate_to_parents)
SELECT
    role_id,
    'condition',
    resource_type,
    condition,
    permission_level,
    is_denied,
    inherit_to_children,
    propagate_to_parents
FROM permission_rules;
```

#### 4.3.4 迁移 Visibility 配置（v2 补充，§3.18）

基于 §3.18 Visibility 统一模型研究结论，将现有 BO 的 visibility 默认配置统一到 `data_permission_rules`：

```sql
-- 为每个 BO 的 visibility 配置生成统一规则
INSERT INTO data_permission_rules (role_id, rule_type, resource_type, condition, scope_mode, permission_level)
SELECT
    r.id,
    'visibility',
    bo.table_name,
    -- visibility='public' → 1=1; visibility='private' → owner_id=$user.id
    CASE
        WHEN bo.default_visibility = 'public' THEN '1=1'
        WHEN bo.default_visibility = 'private' THEN 'owner_id = $user.id'
        ELSE 'visibility = ''' || bo.default_visibility || ''''
    END,
    'include',
    'read'
FROM business_objects bo, roles r
WHERE bo.default_visibility IS NOT NULL;
```

**配套实现**：

1. `generate_visibility_condition()` 函数（§3.18.6）— 将 visibility 字段值自动映射为条件表达式
2. 保留 `visibility` DB 列（性能 + UI 友好 + 向后兼容，与 Salesforce OWD 做法一致）
3. UI 新增 Visibility 配置入口（public / private / team / department / parent）

#### 4.3.5 PermissionResolver 作为统一 PDP

见 §3.5。

#### 4.3.6 废弃旧表

```sql
ALTER TABLE role_dimension_scopes RENAME TO role_dimension_scopes_deprecated;
ALTER TABLE permission_rules RENAME TO permission_rules_deprecated;
```

### 4.4 Phase 4: PDP/PEP 分离架构（2-3 周）

#### 4.4.1 PermissionResolver 完整实现

```python
class PermissionResolver:
    """统一权限决策点（PDP）"""

    def __init__(self, data_source):
        self._ds = data_source
        self._condition_eval = ConditionEvaluator()
        self._dimension_engine = DimensionScopeEngine(data_source)
        self._owner_resolver = ChainOwnerResolver(data_source)
        self._cache = PermissionCache()

    def check(self, user, action, resource_type, resource=None, resource_id=None):
        """5 维正交权限检查"""
        # Layer 0: Prohibition (Deny 优先)
        if self._check_prohibition(user, action, resource_type, resource):
            return Deny("prohibition denied")

        # Layer 1: Action (功能权限)
        if not self._check_action(user, action, resource_type):
            return Deny("missing functional permission")

        # Layer 2: Field (字段级)
        if not self._check_field(user, action, resource_type):
            return Deny("field mask denied")

        # Layer 3: Row (数据权限)
        if not self._check_row(user, action, resource_type, resource, resource_id):
            return Deny("row filter denied")

        # Layer 4: Owner (owner exception)
        if not self._check_owner(user, action, resource_type, resource, resource_id):
            return Deny("owner check failed")

        # Layer 5: Org (组织级约束)
        if not self._check_org(user, action, resource_type, resource, resource_id):
            return Deny("org level denied")

        return Allow()
```

#### 4.4.2 拦截器改造为 PEP（v2: 11 个拦截器）

```python
# permission_interceptor.py 改造为 PEP
class PermissionInterceptor(Interceptor):
    def before_action(self, context):
        resolver = get_permission_resolver()
        result = resolver.check(
            user=context.user_info,
            action=context.action,
            resource_type=context.object_type,
        )
        if not result.allow:
            raise PermissionDenied(result.reason)
```

v2 补充：11 个拦截器全部改造为 PEP，委托 PermissionResolver。

### 4.5 Phase 5: Resource 模型与继承（1-2 周）

#### 4.5.1 Resource 类型声明

```yaml
# meta/schemas/resource_types.yaml
product:
  type: independent
version:
  type: hierarchy
  parent: product
domain:
  type: hierarchy
  parent: version
sub_domain:
  type: hierarchy
  parent: domain
service_module:
  type: hierarchy
  parent: sub_domain
business_object:
  type: hierarchy
  parent: service_module
relationship:
  type: association
annotation:
  type: subordinate
  parent: parent_object
  inherit_owner: true
audit_log:
  type: subordinate
  parent: parent_object
  inherit_owner: false
```

#### 4.5.2 继承规则实现（5 条完整，v2）

```python
class ResourceInheritanceEngine:
    def get_inherited_permissions(self, resource_type, resource_id, user):
        """获取继承的权限（5 条规则）"""
        resource_def = self._get_resource_def(resource_type)

        # 规则 1: 向下继承（parent → children）
        if resource_def.get('inherit_children'):
            self._propagate_to_children(resource_type, resource_id, user)

        # 规则 2: 加严不放松（children 不能比 parent 更宽松）
        if not self._check_ancestor_dim_scope(resource_type, resource_id, user):
            return False

        # 规则 3: 关联取交集（Association 两端取交集）
        if resource_def['type'] == 'association':
            if not self._check_parent_dim_scope(resource_type, resource_id, user):
                return False

        # 规则 4: 附属跟随（Subordinate 继承 parent owner）
        if resource_def['type'] == 'subordinate':
            parent_id = self._get_parent_id(resource_type, resource_id, resource_def['parent'])
            return self._get_parent_permissions(parent_id, user)

        # 规则 5: 向上传播（children 变更传播到 parent）
        if resource_def.get('propagate_to_parents'):
            self._propagate_to_parents(resource_type, resource_id)

        return True
```

### 4.6 Phase 6: M10 Prohibition（1-2 周）

#### 4.6.1 Prohibition 表设计

`data_permission_rules` 中 `rule_type='prohibition'` 或 `is_denied=1`。

#### 4.6.2 Deny 优先实现

```python
def _check_prohibition(self, user, action, resource_type, resource):
    """Layer 0: Prohibition (Deny 优先)"""
    rules = self._load_rules(user, rule_type='prohibition')
    for rule in rules:
        if rule['resource_type'] != resource_type:
            continue
        if self._condition_eval.evaluate(rule['condition'], resource or {}):
            return True  # Prohibition 匹配 = 立即 Deny
    return False
```

### 4.7 Phase 7: 声明式配置（1-2 周）

见 §3.7 BO.yaml permission 块。

### 4.8 Phase 8: 三级缓存（1 周）

见 §3.13。

### 4.9 Phase 9: 审计与合规（1 周）

#### 4.9.1 决策日志

```python
def log_permission_decision(user, action, resource_type, resource_id, decision, reason):
    """记录权限决策日志"""
    log_audit(
        event='permission_decision',
        user_id=user['id'],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        reason=reason,
        timestamp=datetime.now().isoformat(),
    )
```

#### 4.9.2 合规报告

```python
def generate_compliance_report(start_date, end_date):
    """生成合规报告"""
    return {
        'total_decisions': count_decisions(start_date, end_date),
        'denied_decisions': count_denied(start_date, end_date),
        'wildcard_configs': count_wildcard_configs(),
        'prohibition_matches': count_prohibition_matches(start_date, end_date),
        'compliance_status': 'PASS' if ... else 'FAIL',
    }
```

#### 4.9.3 审计字段清洗（v2 补充）

见 §3.17。所有审计字段渲染时需调用 `clean_audit_field()`。

### 4.10 Phase 10: Secure by Default 约束（1 周）

#### 4.10.1 `*` 受 visibility scope 约束

```python
def check(self, user, action, resource_type, resource):
    if not self._check_visibility(user, resource_type, resource):
        return Deny("visibility scope denied")
    ...
```

#### 4.10.2 `*` 受 org level 约束

```python
def check(self, user, action, resource_type, resource):
    if not self._check_org_level(user, resource):
        return Deny("org level denied")
    ...
```

#### 4.10.3 `*` 受 field mask 约束

```python
def check(self, user, action, resource_type, resource):
    if not self._check_field_mask(user, action, resource_type):
        return Deny("field mask denied")
    ...
```

#### 4.10.4 `*` 可被 Prohibition 覆盖

```python
def check(self, user, action, resource_type, resource):
    if self._check_prohibition(user, action, resource_type, resource):
        return Deny("prohibition denied")
    ...
```

### 4.11 Phase 11: UI 3 Panel 改造（v2 补充，1-2 周）

#### 4.11.1 当前 UI 3 Panel 结构

| Panel   | 名称      | 数据源                     | 作用                    |
| ------- | ------- | ----------------------- | --------------------- |
| Panel 1 | 菜单与功能权限 | `role_permissions`      | 配置角色的功能权限             |
| Panel 2 | 维度权限    | `role_dimension_scopes` | 配置角色的 dimension scope |
| Panel 3 | 条件型权限   | `permission_rules`      | 配置角色的条件型权限            |

#### 4.11.2 统一模型 UI 改造

| Panel        | 改造后                | 数据源                                                    |
| ------------ | ------------------ | ------------------------------------------------------ |
| Panel 1      | 功能权限               | `role_permissions`（不变）                                 |
| Panel 2      | 数据权限 - 维度          | `data_permission_rules` WHERE rule\_type='dimension'   |
| Panel 3      | 数据权限 - 条件          | `data_permission_rules` WHERE rule\_type='condition'   |
| Panel 4 (新增) | 数据权限 - Owner       | `data_permission_rules` WHERE rule\_type='owner'       |
| Panel 5 (新增) | 数据权限 - Prohibition | `data_permission_rules` WHERE rule\_type='prohibition' |

#### 4.11.3 UI 增强

- Panel 2 增加"全部"选项（`scope_mode='all'`）
- Panel 3 增加"无条件"选项（`condition='*'`）
- Panel 4 (新增) Owner 规则配置
- Panel 5 (新增) Prohibition 规则配置
- 配置 `*` 时二次确认 + 审计日志

### 4.12 Phase 12: 3 阶段灰度发布（v2 补充，2-3 周）

#### 4.12.1 阶段 1: audit-only（1 周）

```bash
# .env 增加
WRITE_SCOPE_AUDIT_ONLY=true
```

- 业务照常运行，写操作不再"静默越权"
- 越权行为 → log WARNING + `/_diagnostics` 计数
- 响应 header: `X-Write-Scope-Warning: <reason>`

#### 4.12.2 阶段 2: soft-default（1 周）

```bash
WRITE_SCOPE_AUDIT_ONLY=true
# 缺 dim scope 角色临时默认 scope = all（宽）
```

- admin 重新配置这些角色
- 缺 dim scope 角色临时默认 scope = `all`

#### 4.12.3 阶段 3: hard-reject（永久）

```bash
WRITE_SCOPE_AUDIT_ONLY=false
```

- 缺 dim scope = 403
- admin 已配好所有角色

### 4.13 Phase 13: Profile 瘦化（v2 补充，1-2 周）

#### 4.13.1 Salesforce Profile 瘦化参考

Salesforce 的用户身份与权限解耦：

- **Profile**: 基础权限（每个用户必须有一个 Profile）
- **Permission Set**: 附加权限（可叠加多个）
- **Role**: 数据权限层级（OWD + Role Hierarchy）

#### 4.13.2 我们的 Profile 瘦化方案

```sql
-- 当前: role 表同时包含功能权限和数据权限
-- 改造后: 拆分为 role + permission_set

-- role 表: 只保留基础身份（类似 Profile）
ALTER TABLE roles ADD COLUMN is_profile INTEGER DEFAULT 0;

-- permission_sets 表: 附加权限（类似 Permission Set）
CREATE TABLE IF NOT EXISTS permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1
);

-- user_permission_sets 表: 用户-权限集关联
CREATE TABLE IF NOT EXISTS user_permission_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    permission_set_id INTEGER NOT NULL,
    created_at DATETIME
);
```

#### 4.13.3 瘦化原则

- **role**: 每个用户必须有一个 role（基础身份）
- **permission\_set**: 可叠加多个（附加权限）
- **data\_permission\_rules**: 数据权限独立配置（不绑定 role）

***

## 5. 数据库迁移

### 5.1 Stage A: 扩展 scope\_mode 枚举

```sql
-- 无需 DDL（SQLite 不强制枚举）
-- 只需更新 schema yaml
```

### 5.2 Stage B: 创建 data\_permission\_rules 表

见 §3.2 DDL。

### 5.3 Stage C: 数据迁移

见 §4.3.2 和 §4.3.3。

### 5.4 Stage D: 应用层切换

拦截器改造为 PEP，委托 PermissionResolver。

### 5.5 Stage E: 旧表重命名

见 §4.3.5。

### 5.6 Stage F: 旧表删除（稳定运行 1 版本周期后）

```sql
DROP TABLE role_dimension_scopes_deprecated;
DROP TABLE permission_rules_deprecated;
```

### 5.7 Stage G: Profile 瘦化（v2 补充）

```sql
-- 创建 permission_sets 和 user_permission_sets 表
-- 见 §4.13.2
```

### 5.8 回滚方案

每个 Stage 独立可回滚。

### 5.9 一致性校验

```sql
SELECT
    (SELECT COUNT(*) FROM role_dimension_scopes) AS old_dim_count,
    (SELECT COUNT(*) FROM data_permission_rules WHERE rule_type='dimension') AS new_dim_count,
    (SELECT COUNT(*) FROM permission_rules) AS old_cond_count,
    (SELECT COUNT(*) FROM data_permission_rules WHERE rule_type='condition') AS new_cond_count;
```

***

## 6. API 变更

### 6.1 权限配置 API 支持 `*`

```http
POST /api/v1/roles/{id}/dimension-scopes
{
    "dimension_code": "product",
    "scope_mode": "all",
    "dimension_values": "*"
}
```

### 6.2 权限检查 API 统一入口

```http
POST /api/v1/permissions/check
{
    "user_id": 123,
    "action": "crud_update",
    "resource_type": "product",
    "resource_id": 1
}

Response:
{
    "decision": "allow",
    "reason": "owner match",
    "layers": {
        "prohibition": "pass",
        "action": "allow",
        "field": "allow",
        "row": "allow",
        "owner": "allow",
        "org": "allow"
    }
}
```

### 6.3 批量权限检查

```http
POST /api/v1/permissions/check-batch
{
    "user_id": 123,
    "checks": [
        {"action": "crud_read", "resource_type": "product", "resource_id": 1},
        {"action": "crud_update", "resource_type": "product", "resource_id": 1}
    ]
}

Response:
{
    "results": [
        {"decision": "allow", "reason": "..."},
        {"decision": "deny", "reason": "owner check failed"}
    ]
}
```

### 6.4 诊断 API

```http
GET /api/v1/_diagnostics/wildcard
{
    "wildcard_configs": [
        {"role_id": 5, "scope_type": "dimension", "dimension_code": "product"},
        {"role_id": 5, "scope_type": "condition", "resource_type": "product"}
    ]
}

GET /api/v1/_diagnostics/permission-resolver
{
    "cache_stats": {
        "l1_hit_rate": 0.92,
        "l2_hit_rate": 0.85,
        "l3_hit_rate": 0.99
    },
    "avg_latency_ms": 2.5,
    "p99_latency_ms": 4.8
}
```

### 6.5 审计 API（v2 补充清洗规则）

```http
GET /api/v1/audit/permission-decisions?start=2026-07-19&end=2026-07-20
{
    "decisions": [
        {
            "user_id": 123,
            "action": "crud_update",
            "resource_type": "product",
            "resource_id": 1,
            "decision": "allow",
            "reason": "owner match",
            "timestamp": "2026-07-19T10:30:00Z"
        }
    ]
}
```

**注**: 所有审计字段渲染时需调用 `clean_audit_field()` 清洗历史占位值。

### 6.6 兼容性

| API                                        | 变更类型                    | 兼容性    |
| ------------------------------------------ | ----------------------- | ------ |
| `POST /api/v1/roles/{id}/dimension-scopes` | 新增 `scope_mode='all'`   | 向后兼容   |
| `POST /api/v1/permissions/check`           | 新增统一入口                  | 新增 API |
| `POST /api/v1/permissions/check-batch`     | 新增批量检查                  | 新增 API |
| `GET /api/v1/_diagnostics/wildcard`        | 新增诊断                    | 新增 API |
| `POST /api/v1/permission-sets` (v2)        | 新增 Permission Set       | 新增 API |
| 现有权限检查 API                                 | 内部委托 PermissionResolver | 向后兼容   |

***

## 7. 测试计划

### 7.1 单元测试

| 测试文件                                        | 覆盖范围                               |
| ------------------------------------------- | ---------------------------------- |
| `test_wildcard_dimension_scope.py`          | `*` 通配符在 dimension scope 中的支持      |
| `test_wildcard_condition.py`                | `*` 通配符在 condition 中的支持            |
| `test_wildcard_write_scope.py`              | `*` 通配符在写路径中的跳过逻辑                  |
| `test_owner_unification.py`                 | Owner 统一模型（3 路径）                   |
| `test_owner_inheritance.py`                 | 附属资源自动继承 owner                     |
| `test_permission_resolver.py`               | 统一 PDP（5 层决策）                      |
| `test_prohibition.py`                       | M10 Prohibition（Deny 优先）           |
| `test_resource_hierarchy.py`                | M11 Resource Hierarchy Inheritance |
| `test_resource_inheritance_5_rules.py` (v2) | 权限继承 5 条规则                         |
| `test_secure_by_default.py`                 | `*` 4 层约束                          |
| `test_data_permission_rules_migration.py`   | 数据迁移脚本                             |
| `test_permission_cache.py`                  | 三级缓存                               |
| `test_bo_yaml_permission.py`                | BO.yaml 声明式配置                      |
| `test_v2_1_write_path.py` (v2)              | V2.1 写路径联动                         |
| `test_ui_3_panel.py` (v2)                   | UI 3 Panel 改造                      |
| `test_3_stage_rollout.py` (v2)              | 3 阶段灰度发布                           |
| `test_permission_dimension_mapping.py` (v2) | 管理维度映射链                            |
| `test_profile_thinning.py` (v2)             | Profile 瘦化                         |
| `test_audit_field_cleaning.py` (v2)         | 审计字段清洗规则                           |

### 7.2 集成测试

#### 7.2.1 5 维正交测试矩阵

| 维度             | Allow         | Deny           |
| -------------- | ------------- | -------------- |
| Action (M1)    | 有功能权限         | 无功能权限          |
| Field (M7)     | 字段可访问         | 字段受限           |
| Row (M2/M3/M6) | 在 dim scope 内 | 不在 dim scope 内 |
| Owner (M4)     | 是 owner       | 不是 owner       |
| Org (M10/M11)  | 无 Prohibition | 有 Prohibition  |

#### 7.2.2 `*` 通配符场景

- `*` 配置 + visibility scope 约束
- `*` 配置 + org level 约束
- `*` 配置 + field mask 约束
- `*` 配置 + Prohibition 覆盖

#### 7.2.3 Owner 统一场景

- 直接 owner\_id 匹配
- 链式 owner（沿 HIERARCHY\_CHAIN 追溯）
- Fallback created\_by
- 附属资源自动继承

#### 7.2.4 V2.1 写路径联动场景（v2 补充）

- 读路径正交：功能权限 Allow + 数据权限 Deny → Deny
- 写路径串联：功能权限 Deny → 不检查数据权限 → Deny
- 写路径串联：功能权限 Allow + 数据权限 Deny → Deny

#### 7.2.5 权限继承 5 条规则场景（v2 补充）

- 规则 1: 向下继承（parent → children）
- 规则 2: 加严不放松（children 不能比 parent 更宽松）
- 规则 3: 关联取交集（Association 两端取交集）
- 规则 4: 附属跟随（Subordinate 继承 parent owner）
- 规则 5: 向上传播（children 变更传播到 parent）

### 7.3 回归测试

- 现有功能权限 `*` 不受影响
- 现有 dimension scope（无 `*`）不受影响
- 现有 owner chain 检查不受影响
- 现有 M9 RLS 测试全部通过（155 PASS）

### 7.4 性能测试

| 指标                           | 目标     |
| ---------------------------- | ------ |
| PermissionResolver 5 层检查 P99 | < 5ms  |
| `*` 查询所有 ID                  | < 50ms |
| 1000 并发下 `*` 配置              | 无性能回退  |
| L1 缓存命中率                     | > 90%  |
| L2 缓存命中率                     | > 85%  |
| L3 缓存命中率                     | > 99%  |

### 7.5 E2E 测试场景

#### 场景 1: admin 用户配置 `*` dimension scope

```gherkin
Given admin 用户登录
When 配置 role "product_manager" 的 product dimension scope = "*"
Then 应记录审计日志 (severity='high')
And UI 显示"全部"选项
And API 返回 scope_mode='all'
```

#### 场景 2: 普通用户访问 `*` 配置的资源

```gherkin
Given role "product_manager" 配置了 product dimension scope = "*"
And role "product_manager" 有 product:read 权限
When 用户访问 /api/v2/bo/product
Then 应返回所有 product 数据
And 不受 dimension scope 限制
```

#### 场景 3: Prohibition 覆盖 `*`

```gherkin
Given role "product_manager" 配置了 product dimension scope = "*"
And 配置了 Prohibition: status='archived' 的 product 不能 delete
When 用户尝试删除 archived product
Then 应返回 403 (Prohibition denied)
```

#### 场景 4: 3 阶段灰度发布（v2 补充）

```gherkin
Given 阶段 1 (audit-only) 启用
When 用户越权写操作
Then 应 log WARNING + /_diagnostics 计数
And 业务不阻塞

Given 阶段 2 (soft-default) 启用
When 缺 dim scope 角色写操作
Then 应临时默认 scope = all
And 业务不阻塞

Given 阶段 3 (hard-reject) 启用
When 缺 dim scope 角色写操作
Then 应返回 403
```

#### 场景 5: Visibility 统一模型（v2 补充，§3.18）

```gherkin
Given BO "product" 配置了 visibility='private'
When 规则加载到 data_permission_rules
Then 应生成 rule_type='visibility' 的规则
And condition = 'owner_id = $user.id'

Given BO "annotation" 配置了 visibility='public'
When 规则加载到 data_permission_rules
Then 应生成 rule_type='visibility' 的规则
And condition = '1=1'

Given 用户查询 visibility='private' 的 BO
And 用户是记录 owner
Then 应返回记录

Given 用户查询 visibility='private' 的 BO
And 用户不是记录 owner
Then 应不返回记录
```

***

## 8. 实施计划（细化）

### 总体时间线

| 里程碑     | 内容                                        | 目标时间   |
| ------- | ----------------------------------------- | ------ |
| M1      | `*` 通配符支持完成                               | 第 2 周  |
| M2      | Owner 统一完成                                | 第 5 周  |
| M3      | data\_permission\_rules + Visibility 统一完成 | 第 9 周  |
| M4      | PDP/PEP 分离完成                              | 第 12 周 |
| M5      | Resource + M10 + 声明式配置完成                  | 第 16 周 |
| M6      | 缓存 + 审计 + Secure by Default 完成            | 第 18 周 |
| M7 (v2) | UI 3 Panel 改造完成                           | 第 20 周 |
| M8 (v2) | 3 阶段灰度发布完成                                | 第 22 周 |
| M9 (v2) | Profile 瘦化完成                              | 第 24 周 |

**总工时**: 17-24 周（可并行优化至 12-16 周）

***

### 8.1 Phase 1: `*` 通配符全面支持（1-2 周）

**概述**：为所有维度值选择引入 `*`（全选）语义，使 `scope_mode='all'` 与 `dimension_value='*'` 在引擎、评估器、拦截器、UI 各层贯通。

**FR 覆盖**：FR-001 / FR-002 / FR-003 | **前置依赖**：无

| Task ID | 任务                          | 涉及文件                                                | 交付物                               | 验证标准                          |
| ------- | --------------------------- | --------------------------------------------------- | --------------------------------- | ----------------------------- |
| P1-T1   | scope\_mode 枚举增加 `'all'`    | `role_dimension_scope.yaml`, `generated_schema.sql` | YAML 枚举含 all；SQL ALTER + CHECK 约束 | `INSERT scope_mode='all'` 不报错 |
| P1-T2   | DimensionScopeEngine 支持 `*` | `dimension_scope_engine.py`                         | `_get_all_dimension_ids()` + 早期返回 | `scope_mode='all'` 返回全量 ID    |
| P1-T3   | ConditionEvaluator 支持 `*`   | `condition_evaluator.py`                            | `evaluate()` 中 `*` 早期返回 True      | 条件为 `*` 时返回 True；非 `*` 不变     |
| P1-T4   | 写路径拦截器 `*` 同步               | `write_scope_interceptor.py`                        | `_check_dim_scope_wildcard()`     | `scope_mode='all'` 时跳过维度校验    |
| P1-T5   | UI 增加"全部"选项                 | `PermissionConfigPanel.vue`                         | 下拉增加"全部"选项                        | 选中后 `scope_mode='all'`；回显正确   |
| P1-T6   | 审计日志记录 `*` 配置               | `audit_service.py`                                  | 审计事件标注 `scope_mode='all'`         | `*` 配置变更有完整审计记录               |
| P1-T7   | 单元测试                        | `test_wildcard_support.py`                          | 覆盖 T1-T6 所有路径（≥15 个）              | 全部通过；边界：空维度表、混合 `*`/fixed     |

**验收门禁**：

1. `test_wildcard_support.py` 全部通过，覆盖率 ≥ 90%
2. 端到端：配置 `scope_mode='all'` 后读路径返回全量、写路径不触发越权拒绝
3. 审计日志可查到 `*` 配置记录
4. UI "全部"选项交互无异常

***

### 8.2 Phase 2: Owner 机制统一（2-3 周）

**概述**：将分散在读拦截器、写拦截器、chain 拦截器中的 owner 判断逻辑统一收归到 `PermissionResolver.check_owner()`，读/写路径同源。

**FR 覆盖**：FR-004 / FR-005 / FR-006 | **前置依赖**：Phase 1

| Task ID | 任务                                             | 涉及文件                                      | 交付物                                  | 验证标准                           |
| ------- | ---------------------------------------------- | ----------------------------------------- | ------------------------------------ | ------------------------------ |
| P2-T1   | data\_permission\_rules 增加 `rule_type='owner'` | `generated_schema.sql`                    | ALTER TABLE 增加枚举值                    | `rule_type='owner'` 行可插入       |
| P2-T2   | PermissionResolver.check\_owner()              | `permission_resolver.py`（新）               | 解析 owner\_chain → 判定用户是否在链中          | owner 返回 True；非 owner 返回 False |
| P2-T3   | owner\_chain\_interceptor 委托改造                 | `owner_chain_interceptor.py`              | 删除原逻辑，委托 PermissionResolver          | 改造后行为完全一致（回归）                  |
| P2-T4   | 读路径 owner 逻辑统一                                 | `data_permission_interceptor.py` L859-962 | 替换内联判定为 PermissionResolver 调用        | 读路径 owner 判定与改造前一致             |
| P2-T5   | 附属资源自动继承 owner                                 | `chain_owner_resolver.py`                 | 沿 parent\_chain 向上查找 owner           | 子资源 owner = 祖先 owner           |
| P2-T6   | 写路径 owner 逻辑统一                                 | `write_scope_interceptor.py`              | 委托 PermissionResolver.check\_owner() | 写路径 owner 判定与改造前一致             |
| P2-T7   | 单元测试                                           | `test_owner_unification.py`               | 覆盖 T1-T6（≥20 个）                      | 全部通过；回归一致                      |

**验收门禁**：

1. 读/写/chain 三处 owner 判定均委托 `PermissionResolver.check_owner()`
2. 附属资源 owner 继承链正确（3 级嵌套验证）
3. 回归：改造前后 owner 判定结果 100% 一致

***

### 8.3 Phase 3: data\_permission\_rules 统一表（3-4 周）

**概述**：将 `role_dimension_scopes`、`permission_rules`、Visibility 配置三源统一迁移到 `data_permission_rules` 单表，通过 `rule_type` 区分。

**FR 覆盖**：FR-007 / FR-008 / FR-009 / FR-033 / FR-034 / FR-035 | **前置依赖**：Phase 2

| Task ID | 任务                                   | 涉及文件                                                   | 交付物                                | 验证标准                      |
| ------- | ------------------------------------ | ------------------------------------------------------ | ---------------------------------- | ------------------------- |
| P3-T1   | 创建 data\_permission\_rules 表 DDL     | `generated_schema.sql`, `data_permission_rule.yaml`（新） | 完整 DDL + YAML schema               | DDL 可执行；YAML 与 DDL 字段对应   |
| P3-T2   | 迁移 role\_dimension\_scopes 数据        | SQL 脚本                                                 | INSERT ... SELECT 'dimension'      | 迁移行数 = 原表行数；字段一致          |
| P3-T3   | 迁移 permission\_rules 数据              | SQL 脚本                                                 | INSERT ... SELECT 'condition'      | 迁移行数 = 原表行数；字段一致          |
| P3-T4   | 迁移 Visibility 配置                     | SQL + `visibility_condition_mapper.py`                 | INSERT ... SELECT 'visibility'     | 5 种级别均有对应行                |
| P3-T5   | 实现 generate\_visibility\_condition() | `visibility_condition_mapper.py`（新）                    | Visibility 级别 → condition\_expr 映射 | 输出合法 condition\_expr；可被解析 |
| P3-T6   | 数据一致性校验                              | `test_data_migration_consistency.py`                   | 三源 vs 新表逐行对比                       | 0 条差异                     |
| P3-T7   | 废弃旧表                                 | SQL 脚本                                                 | RENAME TO _deprecated_\*           | 旧表重命名成功；新表查询不受影响          |
| P3-T8   | 回归测试                                 | `test_unified_table_regression.py`                     | 新表端到端权限判定                          | 结果与迁移前 100% 一致            |

**验收门禁**：

1. `data_permission_rules` 包含原三源全部数据
2. 数据一致性校验 0 差异
3. 旧表已重命名 `_deprecated_` 前缀
4. 回归：新表判定结果与迁移前一致
5. 回滚方案：DROP 新表 → RENAME 旧表

***

### 8.4 Phase 4: PDP/PEP 分离架构（2-3 周）

**概述**：PermissionResolver 作为唯一 PDP 执行 5 维正交检查，11 个拦截器仅负责上下文组装和结果执行。

**FR 覆盖**：FR-010 / FR-011 / FR-012 / FR-026 | **前置依赖**：Phase 3

| Task ID | 任务                             | 涉及文件                             | 交付物                      | 验证标准                                   |
| ------- | ------------------------------ | -------------------------------- | ------------------------ | -------------------------------------- |
| P4-T1   | PermissionResolver 5 维正交 check | `permission_resolver.py`         | Layer 0-5 决策流程           | 正交：任一维度变更不影响其他；短路：Prohibition 命中即 Deny |
| P4-T2   | 拦截器改造：读路径                      | `data_permission_interceptor.py` | 组装 Context → 调用 PDP → 执行 | 行为与改造前一致                               |
| P4-T3   | 拦截器改造：写路径                      | `write_scope_interceptor.py`     | 同 T2 模式                  | 行为与改造前一致                               |
| P4-T4   | 拦截器改造：其余 9 个 PEP               | `interceptors/*.py`              | 仅保留上下文组装 + 调用 PDP        | 无残留判定逻辑                                |
| P4-T5   | V2.1 写路径联动明确化                  | `write_scope_interceptor.py`     | 写操作前先调用读路径 PDP           | 不可见资源的写操作被拒绝                           |
| P4-T6   | 集成测试                           | `test_pdp_pep_separation.py`     | 11 拦截器 × 典型场景            | 所有行为与改造前回归一致                           |

**验收门禁**：

1. grep 确认拦截器中无残留判定逻辑
2. 5 维正交：各维度独立变更测试通过
3. 11 个拦截器回归全部通过
4. V2.1 联动：不可见资源写操作被拒绝

***

### 8.5 Phase 5: Resource 模型与继承（1-2 周）

**概述**：BO.yaml 声明资源类型及父子关系，ResourceInheritanceEngine 按继承规则自动派生子资源权限。

**FR 覆盖**：FR-013 / FR-014 | **前置依赖**：Phase 4

| Task ID | 任务                           | 涉及文件                                | 交付物                         | 验证标准        |
| ------- | ---------------------------- | ----------------------------------- | --------------------------- | ----------- |
| P5-T1   | Resource 类型声明设计              | `schemas/*.yaml`                    | 每个 BO.yaml 增加 `resource:` 块 | schema 校验通过 |
| P5-T2   | ResourceInheritanceEngine 实现 | `resource_inheritance_engine.py`（新） | 5 条继承规则完整实现                 | 每条规则独立可测    |
| P5-T3   | 附属资源自动继承集成                   | `permission_resolver.py`            | 调用 Engine 补全子资源缺失规则         | 显式配置优先于继承   |
| P5-T4   | 单元测试                         | `test_resource_inheritance.py`      | 5 条规则 + 显式/隐式优先级 + 3 级嵌套    | 全部通过        |

**验收门禁**：

1. 所有 BO.yaml 包含 `resource` 块且校验通过
2. 5 条继承规则均有独立测试通过
3. 显式配置优先于继承

***

### 8.6 Phase 6: M10 Prohibition（1-2 周）

**概述**：支持 `is_denied=1` 禁止规则，Deny 优先（Layer 0），确保显式禁止不可被 Allow 覆盖。

**FR 覆盖**：FR-015 / FR-016 | **前置依赖**：Phase 4

| Task ID | 任务                        | 涉及文件                        | 交付物                               | 验证标准                         |
| ------- | ------------------------- | --------------------------- | --------------------------------- | ---------------------------- |
| P6-T1   | Prohibition rule\_type 支持 | `generated_schema.sql`      | `is_denied` 字段默认 0                | `is_denied=1` 行可插入           |
| P6-T2   | Deny 优先实现                 | `permission_resolver.py`    | `_check_prohibition()` 作为 Layer 0 | 命中 → 立即 Deny；短路不执行 Layer 1-5 |
| P6-T3   | 配置 UI — Panel 5           | `PermissionConfigPanel.vue` | "禁止规则"配置面板                        | 可创建/删除 `is_denied=1` 规则      |
| P6-T4   | 单元测试                      | `test_prohibition.py`       | Deny 优先短路 + Deny vs Allow 冲突      | Deny 永远优先于 Allow             |

**验收门禁**：

1. `is_denied=1` 规则可正确存储和查询
2. Layer 0 短路机制生效
3. Deny + Allow 冲突：Deny 始终胜出

***

### 8.7 Phase 7: 声明式配置（1-2 周）

**概述**：BO.yaml 声明式 `permission:` 块定义权限规则，PermissionConfigLoader 加载并写入 data\_permission\_rules。

**FR 覆盖**：FR-017 / FR-018 / FR-029 | **前置依赖**：Phase 5, Phase 6

| Task ID | 任务                     | 涉及文件                             | 交付物                                     | 验证标准             |
| ------- | ---------------------- | -------------------------------- | --------------------------------------- | ---------------- |
| P7-T1   | BO.yaml permission 块设计 | `schemas/*.yaml`                 | `permission:` 块 schema                  | 校验通过；示例可解析       |
| P7-T2   | 配置加载器实现                | `permission_config_loader.py`（新） | `load_from_yaml()` → upsert             | 幂等；启动后表与 YAML 一致 |
| P7-T3   | 管理维度映射链明确化             | `permission_dimension_engine.py` | 管理维度链定义和解析                              | 链可正确解析到叶子节点      |
| P7-T4   | 配置校验                   | `permission_config_loader.py`    | 启动校验：rule\_type / dimension / condition | 非法配置报错；合法正常加载    |
| P7-T5   | 单元测试                   | `test_declarative_config.py`     | YAML 解析 + upsert 幂等 + 校验                | 全部通过             |

**验收门禁**：

1. 所有 BO.yaml `permission:` 块可加载
2. 加载幂等：多次执行结果一致
3. 非法配置启动报错

***

### 8.8 Phase 8: 三级缓存（1 周）

**FR 覆盖**：FR-019 | **前置依赖**：Phase 4

| Task ID | 任务       | 涉及文件                            | 交付物                                            | 验证标准                   |
| ------- | -------- | ------------------------------- | ---------------------------------------------- | ---------------------- |
| P8-T1   | L1 请求级缓存 | `permission_resolver.py`        | threading.local()                              | 同请求不重复计算               |
| P8-T2   | L2 角色级缓存 | `permission_cache.py`（新）        | TTLCache(key=(role\_id,resource\_type,action)) | 5 分钟内命中缓存              |
| P8-T3   | L3 全局级缓存 | `permission_cache.py`           | SQLite :memory:                                | 跨角色共享规则命中 L3           |
| P8-T4   | 缓存失效策略   | `permission_cache.py`           | `invalidate(role_id)` / `invalidate_all()`     | 规则变更后缓存立即失效            |
| P8-T5   | 性能测试     | `test_permission_cache_perf.py` | 无缓存 vs L1 vs L1+L2 vs L1+L2+L3                 | QPS 提升 ≥ 5 倍；P99 ≤ 5ms |

***

### 8.9 Phase 9: 审计与合规（1 周）

**FR 覆盖**：FR-020 / FR-021 / FR-031 | **前置依赖**：Phase 4

| Task ID | 任务       | 涉及文件                        | 交付物                                | 验证标准           |
| ------- | -------- | --------------------------- | ---------------------------------- | -------------- |
| P9-T1   | 决策日志记录   | `audit_service.py`          | `log_permission_decision()` 异步写入   | 每次判定有日志；不阻塞主流程 |
| P9-T2   | 合规报告生成   | `compliance_reporter.py`（新） | 按角色/资源统计允许/拒绝比例                    | 报告数据准确；格式正确    |
| P9-T3   | 审计 API   | `audit_api.py`（新）           | GET /audit/decisions + /compliance | 分页正确；仅审计角色可访问  |
| P9-T4   | 审计字段清洗规则 | `audit_service.py`          | `clean_audit_field()`              | 手机号留前3后4；不可逆   |

***

### 8.10 Phase 10: Secure by Default 约束（1 周）

**FR 覆盖**：FR-022 / FR-023 / FR-024 / FR-025 | **前置依赖**：Phase 6, Phase 8

| Task ID | 任务                        | 涉及文件                        | 交付物                     | 验证标准                          |
| ------- | ------------------------- | --------------------------- | ----------------------- | ----------------------------- |
| P10-T1  | `*` 受 Visibility scope 约束 | `permission_resolver.py`    | Layer 4 在 `*` 下仍生效      | `*` + Visibility=本部门 → 仅返回本部门 |
| P10-T2  | `*` 受 Org level 约束        | `permission_resolver.py`    | `*` 维度值被用户 org level 截断 | 部门经理 `*` 仅可见本部门及下属            |
| P10-T3  | `*` 受 Field mask 约束       | `permission_resolver.py`    | Field mask 仍对敏感字段脱敏     | `*` 下手机号仍被 mask               |
| P10-T4  | `*` 可被 Prohibition 覆盖     | `permission_resolver.py`    | Layer 0 优先于 `*` Allow   | `*` + Prohibition → Deny      |
| P10-T5  | 单元测试                      | `test_secure_by_default.py` | 四大约束场景                  | `*` 不突破安全边界                   |

***

### 8.11 Phase 11: UI 3 Panel 改造（v2 补充，1-2 周）

**FR 覆盖**：FR-027 / FR-036 | **前置依赖**：Phase 3, Phase 6

| Task ID | 任务                                 | 涉及文件                        | 交付物                          | 验证标准                  |
| ------- | ---------------------------------- | --------------------------- | ---------------------------- | --------------------- |
| P11-T1  | Panel 2 适配 data\_permission\_rules | `PermissionConfigPanel.vue` | 数据源切到 rule\_type='dimension' | 显示和保存正常               |
| P11-T2  | Panel 3 适配 data\_permission\_rules | `PermissionConfigPanel.vue` | 数据源切到 rule\_type='condition' | 显示和保存正常               |
| P11-T3  | 新增 Panel 4（Owner）                  | `PermissionConfigPanel.vue` | Owner 规则配置面板                 | CRUD 正常               |
| P11-T4  | 新增 Panel 5（Prohibition）            | `PermissionConfigPanel.vue` | 禁止规则配置面板                     | `is_denied=1` CRUD 正常 |
| P11-T5  | 新增 Panel 6（Visibility）             | `PermissionConfigPanel.vue` | 5 种级别配置面板                    | 5 种级别可选且语义正确          |
| P11-T6  | `*` 配置二次确认                         | `PermissionConfigPanel.vue` | 选择"全部"时弹出确认                  | 不误操作                  |
| P11-T7  | UI 集成测试                            | `test_ui_panels.py`         | 各 Panel CRUD + 二次确认          | 交互正常；数据持久化正确          |

***

### 8.12 Phase 12: 3 阶段灰度发布（v2 补充，2-3 周）

**FR 覆盖**：FR-028 | **前置依赖**：Phase 11

| Task ID | 任务                | 涉及文件                                          | 交付物                      | 验证标准             |
| ------- | ----------------- | --------------------------------------------- | ------------------------ | ---------------- |
| P12-T1  | 阶段 1：audit-only   | `permission_resolver.py`, `interceptors/*.py` | 新判定仅写审计，不拦截              | 用户无感知            |
| P12-T2  | 阶段 1 验收           | 审计分析脚本                                        | 运行 1 周，统计不一致率            | 不一致率 < 5% 可进阶段 2 |
| P12-T3  | 阶段 2：soft-default | `permission_resolver.py`                      | 新 Deny + 旧 Allow → 告警+放行 | 新 Allow → 放行     |
| P12-T4  | 阶段 2 验收           | 审计分析脚本                                        | 运行 1 周，统计告警              | 告警 < 1/万请求可进阶段 3 |
| P12-T5  | 阶段 3：hard-reject  | `permission_resolver.py`                      | 新体系独占                    | 旧逻辑不再执行          |
| P12-T6  | 阶段 3 验收           | 全量回归测试                                        | 端到端                      | 全部通过；无误判         |

**验收门禁**：

1. 阶段 1：不一致率 < 5%
2. 阶段 2：告警 < 1/万请求
3. 阶段 3：全量回归通过
4. 每阶段可回退（feature flag）

***

### 8.13 Phase 13: Profile 瘦化（v2 补充，1-2 周）

**FR 覆盖**：FR-030 / FR-032 | **前置依赖**：Phase 12

| Task ID | 任务                            | 涉及文件                        | 交付物                         | 验证标准          |
| ------- | ----------------------------- | --------------------------- | --------------------------- | ------------- |
| P13-T1  | 创建 permission\_sets 表         | `generated_schema.sql`      | DDL: permission\_sets       | 表可创建          |
| P13-T2  | 创建 user\_permission\_sets 关联表 | `generated_schema.sql`      | DDL: user\_permission\_sets | 联合唯一约束生效      |
| P13-T3  | 迁移现有角色权限                      | SQL 脚本                      | 提取为 Permission Set + 关联     | 迁移后判定结果一致     |
| P13-T4  | UI 支持 Permission Set 配置       | `PermissionConfigPanel.vue` | Set 管理界面                    | CRUD 正常；角色可关联 |
| P13-T5  | ReBAC 引入必要性分析                 | `rebac_analysis.md`（新）      | 对比分析文档                      | 评审通过；明确建议     |
| P13-T6  | 单元测试                          | `test_permission_set.py`    | Set CRUD + 迁移一致性            | 全部通过          |

***

### 8.14 总体验收标准

| 序号 | 验收项                                      | 对应 Phase |
| -- | ---------------------------------------- | -------- |
| 1  | `*` 通配符在全链路（引擎/评估器/拦截器/UI）语义一致           | P1       |
| 2  | Owner 判定读/写路径同源（PermissionResolver 唯一入口） | P2       |
| 3  | data\_permission\_rules 单表替代三源，数据 0 差异   | P3       |
| 4  | PDP/PEP 分离，11 个拦截器无残留判定逻辑                | P4       |
| 5  | 子资源权限可从父资源自动继承                           | P5       |
| 6  | Prohibition（Deny）优先于任何 Allow             | P6       |
| 7  | BO.yaml 声明式配置可加载且幂等                      | P7       |
| 8  | 三级缓存 QPS 提升 ≥ 5 倍                        | P8       |
| 9  | 审计日志完整且敏感字段已清洗                           | P9       |
| 10 | `*` 在四大约束下不突破安全边界                        | P10      |
| 11 | UI 6 Panel 全部可用，`*` 有二次确认                | P11      |
| 12 | 灰度 3 阶段逐步上线，无权限误判                        | P12      |
| 13 | Permission Set 模型上线，配置冗余度下降              | P13      |

### 8.15 24 个月长期演进路径（v2 补充）

基于 `INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md` §6.5：

| 阶段       | 时间      | 目标     | 内容                                                       |
| -------- | ------- | ------ | -------------------------------------------------------- |
| **短期补齐** | 0-6 月   | 补齐核心功能 | 11→10 机制统一 + Visibility 统一 + `*` 支持 + Owner 统一 + M10/M11 |
| **中期优化** | 6-12 月  | 优化架构   | PDP/PEP 分离 + 声明式配置 + 三级缓存 + Profile 瘦化                   |
| **长期演进** | 12-18 月 | 引入先进模型 | ReBAC 分析 + Field Mask 完整 + 多租户隔离                         |
| **标杆级**  | 18-24 月 | 行业标杆   | AI 驱动权限推荐 + 合规自动化 + 权限即代码                                |

## 9. 风险与缓解

### 9.1 R1: `*` 配置错误导致权限泄漏

**风险**: admin 误配 `*` 导致权限泄漏
**缓解**:

- UI 二次确认
- 审计日志 severity='high'
- 定期审计 `*` 配置
- Secure by Default 约束（4 层）
- Prohibition 可覆盖 `*`

### 9.2 R2: Owner 迁移期间读/写不一致

**风险**: 迁移期间读路径用新逻辑，写路径用旧逻辑
**缓解**:

- Phase 2 期间双写（新旧逻辑都跑）
- 对比结果，不一致时告警
- 稳定 1 周后切换到新逻辑

### 9.3 R3: 旧表迁移数据丢失

**风险**: 迁移脚本 bug 导致数据丢失
**缓解**:

- 迁移前备份
- 迁移脚本幂等
- 迁移后一致性校验
- 旧表重命名（不删除），保留 1 版本周期

### 9.4 R4: 性能回退

**风险**: PermissionResolver 5 层检查比原逻辑慢
**缓解**:

- 三级缓存（L1/L2/L3）
- 批量预加载
- 性能基准测试
- P99 < 5ms 目标

### 9.5 R5: PDP/PEP 分离引入复杂度

**风险**: 11 个拦截器改造为 PEP 可能引入 bug
**缓解**:

- 渐进式迁移（一个拦截器一个）
- 双跑对比（新旧逻辑）
- 完整回归测试

### 9.6 R6: 声明式配置学习成本

**风险**: 团队不熟悉 BO.yaml 声明式配置
**缓解**:

- 提供模板和示例
- 配置校验工具
- 文档和培训

### 9.7 R7: M10 Prohibition 配置错误

**风险**: Prohibition 配置错误导致正常操作被拒
**缓解**:

- audit-only 模式（先观察不拒绝）
- 配置校验
- 紧急回滚开关

### 9.8 R8: 缓存一致性

**风险**: 缓存未及时失效导致权限泄漏
**缓解**:

- 角色配置变更时主动失效 L2
- 全局配置变更时主动失效 L3
- TTL 兜底（L2=5min, L3=1h）

### 9.9 R9: M9 RLS 与 DimensionScope 冲突

**风险**: 两套规则不一致导致权限泄漏
**缓解**:

- 统一到 data\_permission\_rules 表
- 一致性校验脚本
- 最终 M9 YAML 作为 SSOT

### 9.10 R10: 回归测试不充分

**风险**: 现有功能受影响未发现
**缓解**:

- 完整回归测试套件
- 双跑对比（新旧逻辑）
- 灰度发布

### 9.11 R11: ReBAC 引入必要性（v2 补充）

**风险**: 当前关系型权限模型（Association）无法表达复杂关系图权限
**分析**:

- **当前模型**: Association 关系取交集（规则 3），已能处理大部分场景
- **ReBAC 优势**: Google Zanzibar / SpiceDB 能表达 "user is editor of doc" 这类关系图权限
- **引入时机**: 18-24 个月长期演进阶段（§8.15）
- **决策**: 短期不引入 ReBAC，保持当前关系型模型；长期评估引入必要性

**缓解**:

- 短期: 完善 Association 规则（规则 3）
- 中期: 评估复杂关系图场景
- 长期: 若场景需要，引入 SpiceDB 作为 PDP 后端

### 9.12 R12: V2.1 写路径联动破坏（v2 补充）

**风险**: PDP/PEP 分离后 V2.1 联动关系丢失
**缓解**:

- PermissionResolver 明确支持读写路径区分
- 写路径检查保留前置条件逻辑
- 集成测试覆盖 V2.1 场景

***

## 10. 验收标准

### 10.1 功能验收

- ✅ `*` 通配符在功能权限、Dimension Scope、Condition 三层均支持
- ✅ Owner 逻辑统一到 `data_permission_rules` 的 `rule_type='owner'`
- ✅ `data_permission_rules` 表作为 SSOT
- ✅ PermissionResolver 作为统一 PDP
- ✅ 5 维正交权限模型（Action / Field / Row / Owner / Org）
- ✅ PDP/PEP 分离架构（11 个拦截器改造）
- ✅ M10 Prohibition（Deny 优先）
- ✅ M11 Resource Hierarchy Inheritance（5 条规则完整）
- ✅ 声明式配置（BO.yaml permission 块）
- ✅ 三级缓存（L1/L2/L3）
- ✅ 审计与合规（决策日志 + 合规报告 + 字段清洗）
- ✅ 4 层 Secure by Default 约束生效
- ✅ V2.1 写路径联动明确（v2）
- ✅ UI 3 Panel 改造完成（v2）
- ✅ 3 阶段灰度发布执行（v2）
- ✅ 管理维度映射链明确（v2）
- ✅ Profile 瘦化完成（v2）
- ✅ 审计字段清洗规则规范（v2）
- ✅ ReBAC 引入必要性分析完成（v2）

### 10.2 性能验收

- ✅ PermissionResolver 5 层检查 P99 < 5ms
- ✅ `*` 查询所有 ID < 50ms
- ✅ 1000 并发下无性能回退
- ✅ L1 缓存命中率 > 90%
- ✅ L2 缓存命中率 > 85%
- ✅ L3 缓存命中率 > 99%

### 10.3 安全验收

- ✅ `*` 配置触发审计日志
- ✅ `*` 受 4 层约束
- ✅ Prohibition 可覆盖 `*`
- ✅ 无权限泄漏
- ✅ Secure by Default（默认拒绝）

### 10.4 兼容性验收

- ✅ 现有功能权限 `*` 不受影响
- ✅ 现有 dimension scope（无 `*`）不受影响
- ✅ 现有 owner chain 检查不受影响
- ✅ 现有 M9 RLS 测试全部通过（155 PASS）
- ✅ 旧表迁移后数据一致

### 10.5 验收流程

1. Phase 1 验收: `*` 通配符支持 + 单元测试通过
2. Phase 2 验收: Owner 统一 + 读/写路径对称
3. Phase 3 验收: data\_permission\_rules 表 + 数据迁移一致
4. Phase 4 验收: PermissionResolver + 5 层决策 + 11 拦截器改造
5. Phase 5-10 验收: Resource 模型 + M10 + 声明式 + 缓存 + 审计 + Secure by Default
6. Phase 11-13 验收: UI 改造 + 3 阶段灰度 + Profile 瘦化（v2）
7. 最终验收: 所有测试通过 + 性能达标 + 安全审计通过

***

## 11. 参考

### 11.1 研究文档

- [WILDCARD\_SUPPORT\_RESEARCH.md](../WILDCARD_SUPPORT_RESEARCH.md) — `*` 通配符支持研究
- [INDUSTRY\_PERMISSION\_RESEARCH\_OVERVIEW.md](../INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md) — 行业权限架构深度研究
- [CLOUD\_IAM\_ARCHITECTURE\_RESEARCH.md](../CLOUD_IAM_ARCHITECTURE_RESEARCH.md) — 云厂商 IAM 架构研究
- [PERMISSION\_ACADEMIC\_MODELS\_RESEARCH.md](../PERMISSION_ACADEMIC_MODELS_RESEARCH.md) — 学术理论模型研究
- [ENTERPRISE\_APP\_PERMISSION\_RESEARCH.md](../ENTERPRISE_APP_PERMISSION_RESEARCH.md) — 企业应用权限研究
- [COMPLIANCE\_FRAMEWORK\_PERMISSION\_RESEARCH.md](../COMPLIANCE_FRAMEWORK_PERMISSION_RESEARCH.md) — 合规框架权限研究
- [OPEN\_SOURCE\_PERMISSION\_ENGINE\_RESEARCH.md](../OPEN_SOURCE_PERMISSION_ENGINE_RESEARCH.md) — 开源权限引擎研究
- [auth/role-migration-guide.md](../auth/role-migration-guide.md) — 3 阶段灰度发布指南（v2）

### 11.2 相关 Spec

- [PERMISSION\_TODOS.md](../PERMISSION_TODOS.md) — 权限体系专题待办
- [spec-m11-rls-implementation.md](spec-m11-rls-implementation.md) v1.4.0 — M9 RLS 实现（v2 重编号）
- [spec-permission-derivation-MASTER-PLAN-2026-06-08.md](spec-permission-derivation-MASTER-PLAN-2026-06-08.md) — 权限推导 Master Plan
- [spec\_data\_permission\_unified\_model.md](../specs/spec_data_permission_unified_model.md) — 数据权限统一模型
- [spec\_role\_permission\_granular\_control.md](../specs/spec_role_permission_granular_control.md) — 角色权限粒度控制
- [auth-permission-system-design.md](../auth-permission-system-design.md) — 认证权限系统设计

### 11.3 代码文件

- `meta/services/dimension_scope_engine.py` — Dimension Scope Engine
- `meta/services/condition_evaluator.py` — Condition Evaluator
- `meta/services/chain_owner_resolver.py` — Chain Owner 解析器
- `meta/services/permission_dimension_engine.py` — 管理维度引擎（v2）
- `meta/core/interceptors/permission_interceptor.py` — 功能权限拦截器
- `meta/core/interceptors/data_permission_interceptor.py` — 数据权限拦截器
- `meta/core/interceptors/write_scope_interceptor.py` — 写路径拦截器（V2.1）
- `meta/core/interceptors/owner_chain_interceptor.py` — Owner Chain 拦截器
- `meta/core/interceptors/owner_permission_interceptor.py` — Owner 自动权限拦截器
- `meta/core/interceptors/field_policy_interceptor.py` — 字段策略拦截器
- `meta/core/interceptors/hierarchy_validation_interceptor.py` — 层级校验拦截器
- `meta/core/interceptors/version_context_interceptor.py` — 版本上下文拦截器（v2）
- `meta/core/interceptors/constraint_validation_interceptor.py` — 约束校验拦截器（v2）
- `meta/core/interceptors/enum_protection_interceptor.py` — 枚举保护拦截器（v2）
- `meta/core/interceptors/association_interceptor.py` — 关联拦截器
- `meta/schemas/role_dimension_scope.yaml` — role\_dimension\_scopes schema
- `meta/schemas/permission_rule.yaml` — permission\_rules schema
- `meta/schemas/generated_schema.sql` — 数据库 schema
- `rls_rules/*.yaml` — M9 RLS 规则（v2 重编号）
- `rls/loader.py` — M9 RLS 加载器
- `src/views/SystemManagement/components/PermissionConfigPanel.vue` — UI 3 Panel（v2）

### 11.4 行业参考

- **AWS IAM** — `Resource: "*"` / `Action: "*"` 语义，Explicit Deny 优先
- **SAP CAP** — `@restrict` 声明式权限，1 注解统一 action + role + where
- **Salesforce** — OWD + Profile + Permission Set，Profile 瘦化
- **ServiceNow** — ACL 三元组（Role + Condition + Script）
- **SpiceDB** — ReBAC 关系图权限（Google Zanzibar）
- **Cedar** — 策略引擎（Amazon）
- **XACML** — `<AnyResource/>` / `<AnyAction/>`，PDP/PEP 分离
- **飞书多维表格** — 5 层权限（角色 × 视图 × 行 × 列 × 仪表盘）
- **Dynamics 365** — 安全角色 + Owner 字段
- **Workday** — 基于位置的安全（Domain Security Groups）

### 11.5 学术模型

- **NIST RBAC** — Role-Based Access Control（NIST 标准）
- **ABAC** — Attribute-Based Access Control
- **PBAC** — Policy-Based Access Control
- **ReBAC** — Relationship-Based Access Control（Google Zanzibar）
- **NGAC** — Next Generation Access Control（NIST）

### 11.6 开源权限引擎

- **Open Policy Agent (OPA)** — 通用策略引擎
- **Cerbos** — 声明式授权
- **Polar (Oso)** — 逻辑编程式授权
- **Casbin** — 轻量级授权库

### 11.7 合规框架

- **GDPR** — 最小权限原则（Article 32）
- **SOX** — 职责分离（Segregation of Duties）
- **ISO 27001** — 访问控制（A.9）

***

## CHANGELOG

| 日期         | 变更人          | 变更内容                                                                                                                                |
| ---------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-19 | AI Assistant | 创建 Spec v1                                                                                                                          |
| 2026-07-19 | AI Assistant | v2 补充 14 项遗漏：V2.1 联动 / UI 3 Panel / 3 阶段灰度 / 管理维度映射 / 继承 5 规则 / M1-M11 重编号 / 读权限语义 / 3 拦截器 / Profile 瘦化 / 24 月路线图 / 审计清洗 / ReBAC 分析 |

***

## 附录 A: TBD List

| TBD ID | 描述                           | 优先级 |
| ------ | ---------------------------- | --- |
| TBD-1  | Field Mask（M7/M8）详细设计        | P2  |
| TBD-2  | 多租户隔离设计                      | P4  |
| TBD-3  | AI Agent 操作契约设计              | P4  |
| TBD-4  | Record Type 设计               | P4  |
| TBD-5  | ReBAC 引入必要性深度评估（v2）          | P3  |
| TBD-6  | M9 RLS 与 DimensionScope 统一方案 | P1  |
| TBD-7  | Prohibition audit-only 模式设计  | P1  |
| TBD-8  | 缓存失效策略详细设计                   | P2  |
| TBD-9  | 合规报告模板                       | P3  |
| TBD-10 | 性能监控指标定义                     | P2  |

***

## 附录 B: 需求类型映射

### 功能需求 (FR)

| FR ID       | 描述                                     | Phase    |
| ----------- | -------------------------------------- | -------- |
| FR-001      | `*` 通配符在 dimension scope 中支持           | Phase 1  |
| FR-002      | `*` 通配符在 condition 中支持                 | Phase 1  |
| FR-003      | `*` 通配符在写路径中跳过                         | Phase 1  |
| FR-004      | Owner 统一到 rule\_type='owner'           | Phase 2  |
| FR-005      | Owner 3 路径统一校验                         | Phase 2  |
| FR-006      | 附属资源自动继承 owner                         | Phase 2  |
| FR-007      | data\_permission\_rules 统一表            | Phase 3  |
| FR-008      | 数据迁移脚本                                 | Phase 3  |
| FR-009      | 旧表废弃                                   | Phase 3  |
| FR-010      | PermissionResolver 统一 PDP              | Phase 4  |
| FR-011      | 5 维正交权限模型                              | Phase 4  |
| FR-012      | 11 拦截器改造为 PEP                          | Phase 4  |
| FR-013      | Resource 模型颗粒度                         | Phase 5  |
| FR-014      | 权限继承 5 条规则                             | Phase 5  |
| FR-015      | M10 Prohibition                        | Phase 6  |
| FR-016      | Deny 优先实现                              | Phase 6  |
| FR-017      | BO.yaml 声明式配置                          | Phase 7  |
| FR-018      | 配置加载器                                  | Phase 7  |
| FR-019      | 三级缓存                                   | Phase 8  |
| FR-020      | 决策日志                                   | Phase 9  |
| FR-021      | 合规报告                                   | Phase 9  |
| FR-022      | `*` 受 visibility scope 约束              | Phase 10 |
| FR-023      | `*` 受 org level 约束                     | Phase 10 |
| FR-024      | `*` 受 field mask 约束                    | Phase 10 |
| FR-025      | `*` 可被 Prohibition 覆盖                  | Phase 10 |
| FR-026 (v2) | V2.1 写路径联动明确                           | Phase 4  |
| FR-027 (v2) | UI 3 Panel 改造                          | Phase 11 |
| FR-028 (v2) | 3 阶段灰度发布                               | Phase 12 |
| FR-029 (v2) | 管理维度映射链明确                              | Phase 7  |
| FR-030 (v2) | Profile 瘦化                             | Phase 13 |
| FR-031 (v2) | 审计字段清洗规则                               | Phase 9  |
| FR-032 (v2) | ReBAC 引入必要性分析                          | Phase 13 |
| FR-033 (v2) | Visibility 统一到 rule\_type='visibility' | Phase 3  |
| FR-034 (v2) | Visibility → 条件表达式自动映射                 | Phase 3  |
| FR-035 (v2) | Visibility DB 列保留（性能+UI+兼容）            | Phase 3  |
| FR-036 (v2) | Visibility UI 配置入口（5 种级别）              | Phase 11 |

### 非功能需求 (NFR)

| NFR ID | 描述                        | 目标     |
| ------ | ------------------------- | ------ |
| NFR-1  | PermissionResolver P99 延迟 | < 5ms  |
| NFR-2  | `*` 查询所有 ID 延迟            | < 50ms |
| NFR-3  | L1 缓存命中率                  | > 90%  |
| NFR-4  | L2 缓存命中率                  | > 85%  |
| NFR-5  | L3 缓存命中率                  | > 99%  |
| NFR-6  | 1000 并发支持                 | 无性能回退  |

### 接口需求 (IF)

| IF ID     | 描述                 |
| --------- | ------------------ |
| IF-1      | 权限配置 API 支持 `*`    |
| IF-2      | 权限检查 API 统一入口      |
| IF-3      | 批量权限检查 API         |
| IF-4 (v2) | Permission Set API |

### 技术约束 (TR)

| TR ID     | 描述           |
| --------- | ------------ |
| TR-1      | 向后兼容现有 API   |
| TR-2      | 数据迁移可回滚      |
| TR-3      | 拦截器改造渐进式     |
| TR-4 (v2) | V2.1 写路径联动保留 |

***

**End of Spec v2**
