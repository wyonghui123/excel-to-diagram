# 权限体系统一重构方案（数据权限 + 功能权限 + 管理维度）

> **日期**: 2026-06-26
> **作者**: Solo Agent (深入研究后)
> **状态**: 📋 **方案阶段**，待用户确认
> **前置文档**:
>   - [PERMISSION_TODOS.md](PERMISSION_TODOS.md) (当前 3 层并存体系盘点)
>   - [docs/research/head-product-metadata-permission-research.md](research/head-product-metadata-permission-research.md) (SAP/Salesforce/ServiceNow 对标)
>   - [docs/specs/research-yaml-config-boundary.md](specs/research-yaml-config-boundary.md) (YAML 配置边界研究)
>   - [docs/permission-metadata-driven-solution.md](permission-metadata-driven-solution.md) (元数据驱动 5 方案)
>   - [docs/sap-deep-authorization-analysis.md](sap-deep-authorization-analysis.md) (SAP Deep Authorization 机制)
>   - [docs/specs/spec-m11-rls-implementation.md](specs/spec-m11-rls-implementation.md) (M11 RLS v1.4.0)
>   - [docs/specs/spec-permission-derivation-MASTER-PLAN-2026-06-08.md](specs/spec-permission-derivation-MASTER-PLAN-2026-06-08.md) (15 FR + 7 NFR + 6 TR)

---

## 一、用户核心问题的明确化

> "**我们是不是需要统一为数据＋功能权限？dimention 管理维度是不是也是基于数据权限的，管理维度映射到数据权限中的维度？**"

### 答案（明确）：

**是的，必须统一。** 当前 3 层并存是错的，统一方向就是 **"功能权限 (Action Gate) + 数据权限 (Row Filter + Field Mask) + 维度配置 (Dimension Config → 是数据权限的查询输入)"**。

**关键洞察**：
- **管理维度（Dimension）不是独立的第三层** —— 它是**数据权限的输入参数**
- 就像**SAP CAP 的 `@restrict: { where: ... }`**、**Salesforce 的 OWD/Sharing Rules**、**ServiceNow 的 Row-level Security** —— **维度 = 数据权限的配置载体**，不是独立体系

---

## 二、现状盘点（错在哪里）

### 2.1 当前 3 层并存（架构债）

```
┌──────────────────────────────────────────────────────────┐
│  Layer A: M11 声明式 RLS (rls_rules/*.yaml)               │
│   - row_filters / field_masks / actions                   │
│   - [DECORATIVE] 标记 ← 130% 完成但未被启用为主路径        │
└──────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────┐
│  Layer B: DimensionScopeEngine (运行时派生)                 │
│   - 实际主路径                                              │
│   - 硬编码 HIERARCHY_CHAIN / PARENT_FIELD_MAP             │
│   - 走 role_dimension_scopes 表 (inherits + scope values)  │
└──────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────┐
│  Layer C: DataPermissionService (旧表实例级)                │
│   - role_data_permissions / group_data_permissions         │
│   - 0 条数据，但代码仍在查                                  │
└──────────────────────────────────────────────────────────┘
```

**Layer A / B / C 互相不知对方存在 → 规则可能冲突 → 权限泄漏风险**

### 2.2 当前 6 大断裂点（沿用 [docs/permission-metadata-driven-design.md](permission-metadata-driven-design.md) §1.1）

| # | 断裂点 | 现状 |
|---|--------|------|
| 1 | 3 层体系**独立配置** | M11 YAML + dim scope 表 + data_permissions 旧表，三处配置无 SSOT |
| 2 | 管理维度**不属于数据权限** | 维度是"独立表"角色，但本质上是行过滤的**值域来源** |
| 3 | `category_config` 未被消费 | YAML 定义了权限编码，但无代码写 permissions 表 |
| 4 | 菜单 3 套并行 | menuConfig.js + init_menu_permissions.py + useMenuPermissions.js |
| 5 | 字段级权限**未实施** | 仅 M11 YAML 有 `field_masks`，主路径完全不查 |
| 6 | 关联权限**写死** | ASSOCIATION_BOS 写死到 role_permissions，运行时不可派生 |

### 2.3 对标头部产品

| 产品 | 维度定位 | 我们的对应 |
|------|---------|-----------|
| **Salesforce** | 维度 = 记录类型 (Record Type) + OWD | ❌ 散落在 3 张表 |
| **SAP CAP** | `@restrict: { where: ... }` 一处声明 | ❌ 被 3 层体系肢解 |
| **ServiceNow** | sys_security_acl + Dimension Model | ❌ 概念未抽象 |
| **Mendix** | Entity Access Rules (XPath 表达式) | ❌ DSL 不存在 |

**共同点**：**维度配置 + 行过滤 + 字段脱敏 = 同一处声明**（YAML 或 ACL 表）

---

## 三、统一架构设计 (目标态)

### 3.1 三层收成两层 (YAML 驱动 + 维度配置 BO)

```
┌─────────────────────────────────────────────────────────────┐
│                 YAML Schema (SSOT — 唯一真实源)                │
│  meta/schemas/*.yaml:                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ id: domain                                            │   │
│  │ fields: [...]                                         │   │
│  │                                                       │   │
│  │ # ✨ 新增: data_permission_dimensions (数据权限维度声明) │   │
│  │ data_permission_dimensions:                            │   │
│  │   - dimension: company                                 │   │
│  │     field: company_id                                 │   │
│  │     type: fk        # direct / fk / chain / cross_bo  │   │
│  │     description: 域所属公司                             │   │
│  │   - dimension: product                                 │   │
│  │     field: product_id                                 │   │
│  │     type: chain     # 沿 hierarchy 链追溯              │   │
│  │                                                       │   │
│  │ # ✨ 新增: 维度字段 (manager_dimension_code + 业务键)     │   │
│  │ semantics:                                            │   │
│  │   manager_dimension_code: company   # 关联到维度 BO    │   │
│  │   business_key: [code]                                │   │
│  │                                                       │   │
│  │ # ✨ 新增: 字段级权限 (P2 长期, 暂用 M11)              │   │
│  │ field_permissions:                                     │   │
│  │   - field: cost                                       │   │
│  │     read: [role:admin, role:manager]                  │   │
│  │     mask: "***"                                       │   │
│  │   - field: internal_owner                             │   │
│  │     read: [role:admin]                                │   │
│  │                                                       │   │
│  │ # ✨ 新增: 关联权限派生 (P3 长期)                      │   │
│  │ association_derivation:                               │   │
│  │   - on: source                                        │   │
│  │     inherit: parent's read permission                 │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
       ┌─────────────────┼─────────────────┐
       ↓                 ↓                 ↓
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ 维度配置 BO     │ │ 菜单/功能权限 BO │ │ Action 派生服务  │
│ (bo_category:   │ │ (bo_category:   │ │ (SSOT 同步)     │
│  configuration) │ │  configuration) │ │                 │
│                 │ │                 │ │ BO actions[] →  │
│ management_     │ │ permissions     │ │ permissions 表  │
│ dimension_def   │ │ + role_perms    │ │ + role_perms    │
│ + role_dim_     │ │ + menu_perms    │ │                 │
│   scope         │ │                 │ │                 │
│                 │ │                 │ │ 15 FR 派生逻辑  │
│ ✅ 已存在       │ │ ✅ 已存在       │ │ ✅ 已设计       │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────┐
│             PermissionResolver (统一运行时)               │
│                                                           │
│  输入: (user, action, bo, record)                         │
│  输出: 4 元组: (allow, masked_fields, scope_filter, reason)│
│                                                           │
│  流程:                                                    │
│  1. 功能权限 (Action Gate):                                │
│     - 查 permissions + role_permissions                   │
│     - 检查 user.action 是否在允许列表中                     │
│     - 未通过 → (False, {}, null, "ACTION_DENIED")         │
│                                                           │
│  2. 维度配置 (Dimension Values):                          │
│     - 查 role_dimension_scope (已展开 inherit_children)    │
│     - 查 management_dimensions (代码元数据)                │
│     - 查 dimension_object_mapping (BO → dim 映射)         │
│     - 输出: { 'company': {1,2}, 'product': {17,21} }      │
│                                                           │
│  3. 数据权限 (Row Filter):                                │
│     - 根据 BO.yaml 的 data_permission_dimensions[]         │
│       → 构造 SQL WHERE: company_id IN (1,2)               │
│     - 如果 BO 不在维度范围 (e.g. product=17 不在 user 范围) │
│       → 注入 OR false 拒绝                                │
│                                                           │
│  4. 字段级权限 (Field Mask):                              │
│     - 查 BO.yaml.field_permissions[]                       │
│     - 标记哪些字段需要脱敏 (cost → "***")                  │
│     - 返回: {'cost': '***', 'margin': '***'}              │
│                                                           │
│  5. 关联权限 (Association Derivation):                     │
│     - 查 BO.yaml.association_derivation[]                  │
│     - source BO inherit parent.read → 多 SQL 注入         │
│     - 返回: 子对象 permission 列表                         │
│                                                           │
│  6. Owner 例外 (Optional):                                │
│     - 如果 user 是 owner → 跳过维度检查                    │
│     - 走 chain_owner_resolver 链式 SQL                    │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### 3.2 关键设计原则

#### 原则 1：**维度是数据权限的"值域"**，不是独立层

| 概念 | 旧定位 | 新定位 |
|------|--------|--------|
| `permission_dimension` (元数据表) | 独立概念 | **维度元数据** (描述维度的结构: code, type, hierarchy_chain) |
| `role_dimension_scope` (运行时表) | 独立概念 | **角色在维度上的取值范围** (数据权限的"WHERE 值"来源) |
| `data_permissions` (旧表) | 独立概念 | **DEPRECATED** (改为 yaml + role_dimension_scope) |
| `DimensionScopeEngine` | 独立服务 | **退化为 DimValueResolver** (只负责展开 inherit_children) |

#### 原则 2：**所有权限规则只在 YAML 声明一次** (SSOT)

```yaml
# meta/schemas/domain.yaml
id: domain

# ── 数据权限维度声明 (SSOT) ──
data_permission_dimensions:
  - dimension: company
    field: company_id
    type: fk
  - dimension: product
    field: product_id
    type: chain  # 沿 hierarchy 追溯到 product

# ── 字段级权限 (P2) ──
field_permissions:
  - field: cost
    read: [role:admin, role:manager]
    mask: "***"

# ── 关联权限派生 (P3) ──
association_derivation:
  - on: source
    inherit: parent.read
```

#### 原则 3：**M11 RLS YAML 是 SSOT**，DimensionScope 是执行器

- M11 YAML (`rls_rules/domain.yaml`) 描述规则 (what)
- DimensionScopeEngine 负责**展开 dim value** + 构造 SQL (how)
- DataPermissionService **DEPRECATED**
- 拦截器统一从 PermissionResolver 拿 `(allow, masked_fields, scope_filter)` 四元组

#### 原则 4：**维度配置走配置 BO** (bo_category: configuration)

| 配置 BO | 现状 | 用途 |
|---------|------|------|
| `permission_dimension` | ✅ 已实现 | 维度元数据 (code, name, hierarchy_chain) |
| `role_dimension_scope` | ✅ 已实现 | 角色在维度上的取值 + inherit_children |
| `dimension_object_mapping` | ✅ YAML 配置 (loader 已实现) | BO → dim 映射 (硬编码 → 配置) |
| `permission` / `role_permission` | ✅ 已实现 | Action 权限定义 + 角色绑定 |
| `data_permission` (旧表) | ❌ DEPRECATED | 迁移到 dim scope |

---

## 四、映射对比 (从旧到新)

### 4.1 权限检查从 3 条路径 → 1 条路径

| 旧 | 新 |
|----|----|
| `permission_interceptor._check_action()` (查 role_permissions) | `PermissionResolver.check_action()` (查 role_permissions，**不变**) |
| `permission_interceptor._check_yaml_row_filter()` (M11, [DECORATIVE]) | `PermissionResolver.check_row_filter()` (**启用为主路径**) |
| `data_permission_interceptor._add_owner_exception()` (硬编码 product_id) | `PermissionResolver.check_owner_exception()` (走 chain_owner_resolver) |
| `dimension_scope_engine.derive_data_conditions()` (硬编码 HIERARCHY_CHAIN) | `PermissionResolver.resolve_dim_value()` (查 role_dimension_scope + 展开 inherit_children) |
| `data_permission_service.get_allowed_resource_ids()` (查旧表) | **DEPRECATED** |

### 4.2 管理维度映射数据权限维度

| 旧"管理维度"概念 | 新"数据权限维度"概念 |
|----------------|-------------------|
| `permission_dimension` (表) | **= BO.yaml.data_permission_dimensions[].dimension** (YAML SSOT) |
| `dimension_object_mapping` (loader 派生) | **= BO.yaml.data_permission_dimensions[].field** (YAML SSOT, **不再需要 loader**) |
| `role_dimension_scope.dimension_values` (JSON) | **= 角色在维度上的"WHERE 值"** (不变, 仍是配置 BO) |
| `role_dimension_scope.inherit_children` (boolean) | **= 是否沿 hierarchy_chain 自动展开** (不变) |
| `HIERARCHY_CHAIN = ['company', 'product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object']` (硬编码) | **= permission_dimension.yaml.hierarchy_chain** (YAML 化) |
| `PARENT_FIELD_MAP` (硬编码 FK 关系) | **= BO.yaml.data_permission_dimensions[].field** (YAML SSOT) |

### 4.3 关键简化点

| 旧 | 新 | 收益 |
|----|----|----|
| 3 张权限表 (permissions, role_permissions, data_permissions) | **2 张** (permissions, role_permissions) | 减少维护 |
| HIERARCHY_CHAIN 硬编码 (7 维) | **YAML 声明** (可扩展) | 灵活 |
| 3 套拦截器 (permission, data_permission, owner) | **1 个 PermissionResolver** | 简化 |
| M11 YAML + dim scope 互不知对方 | **同一 yaml 引用同 dimension code** | 一致性 |
| 关联权限写死 role_permissions | **运行时派生 (BO.yaml.association_derivation)** | 自动 |

---

## 五、实施路线图 (4 阶段, 6 周)

### Phase 1: 收敛维度元数据 (1 周)

**目标**: 把 HIERARCHY_CHAIN / PARENT_FIELD_MAP / RESOURCE_TABLE_MAP 全部 YAML 化

**Task 1.1: 创建 permission_dimension.yaml** (新增)
- 7 个内置维度的元数据
- `hierarchy_chain` 字段
- 关联 BO 的 `parent_field` 信息

**Task 1.2: 改造 BO.yaml, 新增 `data_permission_dimensions[]`**
- 7 个核心 BO (product, version, domain, sub_domain, service_module, business_object, relationship) 全部加
- 不再依赖 dimension_object_mapping loader

**Task 1.3: DimValueResolver 重构**
- 读 permission_dimension.yaml 拿 hierarchy_chain
- 读 BO.yaml.data_permission_dimensions 拿 FK 映射
- 移除硬编码 HIERARCHY_CHAIN / PARENT_FIELD_MAP

**测试**: 7 BO x 5 场景 = 35 PASS

### Phase 2: PermissionResolver 合并 (1.5 周)

**目标**: 3 个拦截器合 1 个 PermissionResolver

**Task 2.1: 新建 `meta/core/permission_resolver.py`**
- 4 元组接口: `resolve(user, action, bo, record) → (allow, masked, scope_filter, reason)`
- 调用 4 个子服务: action_check, dim_resolve, row_filter, field_mask

**Task 2.2: 拦截器切换**
- permission_interceptor → PermissionResolver
- data_permission_interceptor → PermissionResolver (废弃)
- owner_auto_permission_interceptor → PermissionResolver (合并到 owner exception)

**Task 2.3: 启用 M11 [DECORATIVE] 标记解除**
- permission_interceptor.py L582 _check_yaml_row_filter → 主路径
- 移除 fallback 逻辑

**Task 2.4: 保留向后兼容**
- role_data_permissions / group_data_permissions 表保留 3 个月
- DataPermissionService 输出 warning, 但仍可用

**测试**: 12 场景 x 7 BO = 84 PASS

### Phase 3: 字段级 + 关联权限 (1.5 周)

**目标**: P2 字段级权限 + P3 关联权限派生

**Task 3.1: BO.yaml.field_permissions[] → PermissionResolver**
- 6 BO x 3 字段 = 18 PASS

**Task 3.2: BO.yaml.association_derivation[] → PermissionResolver**
- 5 关联类型 (m2m, polymorphic, self_ref, reverse, sibling) 全实现
- 4.5-6 天 (按 MASTER-PLAN Phase C)

**Task 3.3: 实施 MASTER-PLAN Phase A/B 全部 15 FR**
- FR-001 ~ FR-009 + FR-010 ~ FR-014 + FR-003b
- 4 层次防御 (init / 启动 / 运行时 / 自助)
- 6 天 (按 MASTER-PLAN 13-17 天预估)

**测试**: 12 场景 x 7 BO + 5 关联 = 119 PASS

### Phase 4: 废弃 + 文档 (2 周)

**目标**: 完成废弃 + 用户培训 + 文档

**Task 4.1: 写迁移脚本 DROP role_data_permissions / group_data_permissions**
- 备份 → 校验无遗留 → DROP

**Task 4.2: 删 DimensionScopeEngine 硬编码** (完整走 YAML)
- HIERARCHY_CHAIN / PARENT_FIELD_MAP / RESOURCE_TABLE_MAP 全部删

**Task 4.3: 删 DataPermissionService**
- 所有引用 → PermissionResolver

**Task 4.4: 更新 spec-m11-rls-implementation.md v2.0**
- 从 v1.4.0 (130% 完成, 但 [DECORATIVE]) → v2.0 (主路径)
- TODO-7 M10 协同 = spec-m10-mcp-server.md 启动

**Task 4.5: 用户文档 + 培训**
- 权限体系 v2.0 白皮书
- 配置指南 (permission_dimension.yaml + role_dimension_scope)
- 迁移指南 (data_permissions → role_dimension_scope)

**测试**: E2E 端到端回归 (5 业务场景 x 4 角色) = 20 PASS

### 总体工时

| Phase | 工期 | 测试用例 |
|-------|------|---------|
| Phase 1: 维度元数据收敛 | 1 周 | 35 |
| Phase 2: PermissionResolver 合并 | 1.5 周 | 84 |
| Phase 3: 字段级 + 关联权限 | 1.5 周 | 119 |
| Phase 4: 废弃 + 文档 | 2 周 | 20 |
| **合计** | **6 周** | **258 PASS** |

---

## 六、关键风险与缓解

| 风险 | 缓解 |
|------|------|
| 3 层 → 1 层切换可能引入权限泄漏 | 灰度发布 (Phase 2 Task 2.4 保留旧表 3 个月) |
| HIERARCHY_CHAIN 硬编码删除后,旧 dim 范围数据无法解析 | 写迁移脚本: 旧 dim code → 新 permission_dimension.yaml 引用 |
| 关联权限派生 (5 类型) 实现复杂度高 | 按 MASTER-PLAN Phase C 6 天预估, 5 关联独立测试 |
| 字段级权限与 M11 field_masks 可能冲突 | PermissionResolver 先 M11 后 BO.yaml, M11 优先 |
| 权限决策埋点完整化 (P4) | 已有 FR-005 audit hook, 直接进 audit_log |

---

## 七、是否启动？

**建议**: **是**。理由:

1. **用户已遇到 BUG-V026** (owner exception 对子对象 SQL 错) —— 暴露 3 层体系不一致
2. **M11 RLS 已 130% 完成** (155 PASS) —— 切换成本极低
3. **MASTER-PLAN 文档齐备** (15 FR + 7 NFR + 6 TR, 13-17 天) —— 实施路径明确
4. **架构债越拖越重** (3 层并存 + [DECORATIVE] 标记) —— 现在统一 6 周, 未来统一可能 12+ 周

**用户决策点**:
- (A) **立即启动** (按 4 阶段 6 周实施) — 推荐
- (B) **先做 Phase 1 (1 周收敛维度元数据)** — 保守
- (C) **先做 BUG-V026 修复 (用户阻塞)** + Phase 1 (1.5 周) — 最稳
- (D) **暂不统一, 接受 3 层并存** — 不可取 (技术债加重)

**默认推荐**: (C) — BUG-V026 修复 + Phase 1, 1.5 周交付, 既解用户阻塞又迈出统一第一步

---

## 八、文档关联

| 文档 | 角色 |
|------|------|
| [PERMISSION_TODOS.md](PERMISSION_TODOS.md) | 当前 3 层体系盘点 + 39 spec 清单 |
| [permission-metadata-driven-solution.md](permission-metadata-driven-solution.md) | 5 方案详细设计 (本方案的 Phase 1-3 输入) |
| [permission-metadata-driven-design.md](permission-metadata-driven-design.md) | 6 断裂点诊断 + 目标架构蓝图 |
| [meta-action-permission-analysis.md](meta-action-permission-analysis.md) | 三层权限模型现状 (待替换) |
| [spec-m11-rls-implementation.md](specs/spec-m11-rls-implementation.md) | M11 RLS v1.4.0 (待升级到 v2.0 主路径) |
| [spec-permission-derivation-MASTER-PLAN-2026-06-08.md](specs/spec-permission-derivation-MASTER-PLAN-2026-06-08.md) | 15 FR 派生逻辑 (Phase 3 输入) |
| [research/head-product-metadata-permission-research.md](research/head-product-metadata-permission-research.md) | SAP/Salesforce/ServiceNow 对标 |
| [sap-deep-authorization-analysis.md](sap-deep-authorization-analysis.md) | SAP Deep Authorization 机制 |
| [specs/research-yaml-config-boundary.md](specs/research-yaml-config-boundary.md) | YAML 配置边界研究 (支撑 SSOT 决策) |
