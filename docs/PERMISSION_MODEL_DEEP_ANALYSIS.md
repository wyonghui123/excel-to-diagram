# 角色权限配置影响分析 + "功能权限基于数据颗粒度"评估

> **日期**: 2026-06-26
> **回答用户两个核心问题**:
>   1. 角色权限配置（管理维度）是否会有影响？管理维度如何映射成数据权限？
>   2. "数据 + 功能权限"（功能权限基于数据颗粒度）的合理性评估
> **状态**: 📋 **深度分析** (已结合 8 份 spec + 实际生产数据观察)
> **前置**: [PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md](PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) (架构重设计)

---

## 一、问题 1: 角色权限配置（管理维度）会有影响吗？

### 1.1 直接答案

**会有影响，但是"数据"的影响，不是"结构"的影响**。即：
- ✅ **不会改动** `role_dimension_scope` 表结构
- ✅ **不会改动** UI 配维度的流程
- ✅ **不会改动** 角色的"我能看哪些数据"语义
- ⚠️ **会改动** 维度的元数据来源（从硬编码 → YAML）
- ⚠️ **会改动** 维度到 BO 的映射（从 `dimension_object_mapping.yaml` 加载 → 嵌入到 BO.yaml 内）
- ⚠️ **会改动** 拦截器链（3 套 → 1 套 PermissionResolver）

### 1.2 管理维度配置 = 角色数据范围

当前**生产数据流**：

```
1. 管理员打开 /permission/dimension-config
   ↓
2. 配置 role 111 (Product Manager) 在 product 维度的取值
   role_dimension_scope:
     role_id: 111
     dimension_code: "product"
     dimension_values: "[1, 17, 21]"   ← 这就是"管理维度配置"
     inherit_children: true             ← 是否自动展开子节点
   ↓
3. 用户登录 → expand_dimension_values(role_id=111)
   expanded = {
     'product': {1, 17, 21},
     'version': {2, 11, 12, 21, 22},   ← 自动展开 (inherit_children)
     'domain': {101, 102, ...},
     'sub_domain': {...}
   }
   ↓
4. derive_data_conditions(role_id=111) 构造 SQL
   conditions = {
     'product':    "products.id IN (1, 17, 21)",
     'version':    "versions.id IN (2, 11, 12, 21, 22)",
     'domain':     "domains.id IN (...) OR domains.version_id IN (2, 11, 12, ...)",
     ...
   }
   ↓
5. DataPermissionInterceptor 注入 SQL
   SELECT * FROM domains WHERE domains.id IN (...) AND ...
```

**用户对"管理维度"的理解**：

- ❌ 错位理解: "管理维度 = 独立第三层权限"
- ✅ 正确理解: **"管理维度" = "数据权限的配置载体"** (即 `role_dimension_scope.dimension_values` 是 `WHERE` 的值域)

### 1.3 配置 UI 的实际形态

参考 [BACKLOG-Permission-System-Improvement.md](BACKLOG-Permission-System-Improvement.md) + 实际生产环境:

| 角色类型 | 典型配置 | 展开后数据范围 |
|---------|---------|--------------|
| **admin** (role 1) | 不需配置 | 所有数据 |
| **TEST60** (role 60) | `product=[1]`, inherit=true | product=1 → version=[2,11,12] → domain=... |
| **product_manager** (role 111) | `version=[2, 11, 12, 21]` | 直接限定 4 个 version |
| **domain_editor** (role 222) | `domain=[703]` | 仅 1 个 domain |

**核心洞察**：

> **"管理维度"不是"管理"什么，是"在什么维度的什么范围内有数据权限"**。
> 它本质就是 **SAP CDS `@restrict: { where: ... }`** 或 **Salesforce OWD** 的配置化表达。

### 1.4 重构后会发生什么

| 旧 | 新 | 配置 UI 影响 |
|----|----|------------|
| `role_dimension_scope.dimension_code = "product"` | `role_dimension_scope.dimension_code = "product"` | **0 变化**（YAML 已声明 product 是合法 dimension） |
| 展开子节点（`inherit_children=true`） | 展开子节点（`inherit_children=true`） | **0 变化**（展开规则从 HIERARCHY_CHAIN YAML 读） |
| 注入 SQL `domains.id IN (...)` | 注入 SQL `domains.id IN (...)` | **0 变化**（BO.yaml 声明 field = "id"） |
| UI 选 dimension | UI 选 dimension | **0 变化**（YAML 维度列表就是 UI 下拉） |
| 7 维硬编码 | N 维可扩展 | **正影响**（新增维度无需改代码） |

**结论**：**业务人员无需重新配置任何角色**，所有现有 `role_dimension_scope` 数据**继续有效**，仅底层实现从硬编码切换到 YAML 驱动。

---

## 二、问题 2: "功能权限基于数据颗粒度"是否合理？

### 2.1 直接答案

**不合理（当前隐含的问题），需要重新定义**。

**当前"功能权限"和"数据权限"的关系**：

| 概念 | 现状 | 问题 |
|------|------|------|
| **功能权限** | "user 能对 domain 执行 create/read/update/delete" (action 级) | ✅ 独立于数据 |
| **数据权限** | "user 能看哪些 product/version/domain" (row 级) | ✅ 独立于功能 |
| **字段权限** | "cost 字段对 user 脱敏" (field 级) | ⚠️ 挂在 M11 YAML，但未串通 |
| **关联权限** | "user 能看 relationship 的 source/target" | ⚠️ 写死 role_permissions，未派生 |

**你说的"功能权限基于数据颗粒度"**，我理解的意思可能是：

> **"用户要先满足数据权限（即数据行可见），才能执行功能权限（即 action）"**

这是**对的**，但**不是"基于"**，而是**"先 data filter，再 action gate"** 的**顺序关系**：

```
请求 /api/v2/bo/domain?version_id=764
    ↓
1. 认证: 用户是谁 (auth_middleware)
    ↓
2. 功能权限: domain:read (PermissionInterceptor → role_permissions)
    → 如果没权限 → 403 forbidden
    ↓
3. 数据权限: 用户能看哪些 domain? (DataPermissionInterceptor → DimensionScopeEngine)
    → SQL 注入: domains.id IN (user 可见的 id 列表)
    → 如果有 read 权限但数据范围为空 → 200 OK + 空列表
    ↓
4. 字段权限: 哪些字段脱敏? (BO.yaml.field_masks)
    → SELECT 时 cost → '***'
    ↓
5. 关联权限: relationship.source_id 也要过滤? (FR-007/008)
    → 多表关联时也注入 SQL
```

**所以正确理解是**：

> ✅ **功能权限和数据权限是"两把锁"**，必须**先开功能锁，再过数据锁**。
> ❌ 不是"功能权限基于数据颗粒度"（容易被误解为"功能 = 数据的子集"）。
> ✅ 正确表述: **"功能权限是前置 Action Gate, 数据权限是后置 Row Filter"**。

### 2.2 为什么不合理（当前隐含的 3 个问题）

#### 问题 A: **3 套权限独立配置 → 配置爆炸**

```
配置管理员的实际体验:

1. 角色 111 配置
   - 角色权限: domain:read, domain:create
   - 维度范围: version=[2, 11, 12]
   - 字段权限: cost mask=***
   - 关联权限: relationship.write
   - 特殊权限: data_permissions[legacy]

2. 新增 role 333 (team_lead)
   - 完全复制 role 111 配置 + 改 dimension_values
   - 任何一处改动 → 4 处都要同步
   
3. 角色 111 想改个字段脱敏规则 → 改 YAML 重新部署
   角色 111 想改个数据范围 → 改数据库表 role_dimension_scope
   角色 111 想关个 action → 改数据库表 role_permissions
   
→ 没有任何 SSOT (Single Source of Truth)
```

#### 问题 B: **隐含的"数据颗粒度"被忽略**

如果只说"功能权限基于数据颗粒度"（假设意味着"数据可见 = 功能可用"）：

- ❌ **反例 1**: admin 看所有数据，**但不允许删 permission** (没 `permission:delete` action) → 数据可见 ≠ 功能可用
- ❌ **反例 2**: 普通 user 能看 product (action `read`)，**但不能 export 全部 product** (没 `export` action) → 同一对象不同 action 独立
- ❌ **反例 3**: TEST60 能看 version=[2,11,12] 的 product (data)，**但不能 list 所有 product** (action `list`) → 数据颗粒度是子集，但功能权限可能更严

**所以数据颗粒度 ≠ 功能权限基线**。它们是**正交的两轴**：

```
                    功能权限 (Action)
                       read    create    delete
                  ┌────────┬────────┬────────┐
       product=1  │   ✅   │   ✅   │   ❌   │
   数据权限  product=17 │   ✅   │   ❌   │   ❌   │
       (DimScope)  product=21 │   ✅   │   ❌   │   ❌   │
                  └────────┴────────┴────────┘
```

#### 问题 C: **用户可能误以为"维度 = 角色"，实际不是**

| 角色 (role) | 维度 (dim) | 关系 |
|------------|------------|------|
| product_manager | product=[1, 17, 21] | role 111 限定在 product 维度的 3 个值 |
| domain_editor | domain=[703] | role 222 限定在 domain 维度的 1 个值 |
| 同一个 user 可有多个 role | TEST60 有 role 60 + role 111 | 维度范围是 union |

**维度不是角色的属性，是角色配置中的"数据范围参数"**。一个 role 可以在多个维度上配范围。

### 2.3 重新定义: 正确的权限模型

**正确的提法**：

> **"4 维权限模型" (4-dimensional Permission Model)**

| 维度 | 含义 | 当前实现 | 重构后 |
|------|------|---------|--------|
| **1. Action (功能)** | 能做什么操作 (read/create/update/delete/...) | `role_permissions` 表 | **不变** (YAML SSOT) |
| **2. Row (数据行)** | 能看哪些数据行 | `role_dimension_scope` + `DimensionScopeEngine` | **不变** (YAML 驱动) |
| **3. Field (数据列)** | 哪些字段脱敏 | `BO.yaml.field_masks` (M11) | **升级** (纳入 PermissionResolver) |
| **4. Association (关联)** | 跨对象访问如何派生 | `ASSOCIATION_BOS` 写死 | **重设计** (运行时派生) |

**"4 维正交，互不依赖"**：

- 改 Action 配置 → 不影响 Row/Field/Association
- 改 Row 维度范围 → 不影响 Action/Field/Association
- 改 Field 脱敏 → 不影响 Action/Row/Association
- 改 Association 派生规则 → 不影响 Action/Row/Field

### 2.4 "数据 + 功能权限" + "管理维度映射数据权限" = 完整答案

**用户的两个问题的合并答案**：

```
权限模型 = 功能权限 (Action) 
        + 数据权限 (Row) 
        + 字段权限 (Field) 
        + 关联权限 (Association)
                 ↑
        ┌────────┴────────┐
        │   管理维度配置    │  ← 业务人员在 UI 配的"数据范围"
        │   role_dimension │
        │   _scope 表      │
        └─────────────────┘
                ↓
        维度值 (dimension_values) 是数据权限的 WHERE 值
        维度链 (hierarchy_chain) 是数据权限的展开规则
        维度映射 (BO.yaml.data_permission_dimensions) 是数据权限的字段映射
```

**"管理维度"不是独立第三层**，而是 **数据权限的"配置输入"**。

---

## 三、重构后对角色权限配置的具体影响

### 3.1 配置数据 0 变化

```sql
-- 重构前 (现在)
SELECT * FROM role_dimension_scope WHERE role_id = 111;
-- 返回: dimension_code="product", dimension_values="[1,17,21]"

-- 重构后 (Phase 1 完成后)
SELECT * FROM role_dimension_scope WHERE role_id = 111;
-- 返回: 完全相同 → 业务配置无需迁移
```

### 3.2 配置 UI 0 变化

- `/permission/dimension-config` 页面继续可用
- 维度下拉框从 `permission_dimension` 元数据表读
- 维度链 (product→version→domain→sub_domain) 从 `permission_dimension.yaml` 读
- **所有现有 role 的配置继续工作**

### 3.3 后端实现变化（仅运维人员感知）

| 变化 | 谁感知 |
|------|--------|
| HIERARCHY_CHAIN 从硬编码 → `permission_dimension.yaml` | **开发** (无业务影响) |
| `DimensionScopeEngine` 改读 YAML 而非 Python 常量 | **开发** |
| `data_permission_dimensions` 字段从 `dimension_object_mapping.yaml` 移到 BO.yaml | **开发** (业务可读性 ↑) |
| 3 套拦截器 → 1 个 PermissionResolver | **开发** |
| M11 RLS 从 [DECORATIVE] → 主路径 | **开发** |
| DROP `role_data_permissions` / `group_data_permissions` (旧表) | **DBA** |

### 3.4 一个完整示例: TEST60 的权限配置

**当前** (3 套体系, 跨多个文件/表):

```yaml
# rls_rules/domain.yaml
row_filters:
  - applies_to: [role:user, role:viewer, role:manager]
    condition: "domain.company_id == $user.company_id"
  - applies_to: [role:admin]
    condition: "true"
  - applies_to: [role:ai-agent]
    condition: "domain.is_public == true"
```

```sql
-- 角色权限表
role_permissions:
  - role_id: 60, permission_code: "domain:read"
  - role_id: 60, permission_code: "version:read"
  - role_id: 60, permission_code: "product:read"
```

```sql
-- 角色维度范围表
role_dimension_scope:
  - role_id: 60, dimension_code: "version", dimension_values: "[2, 11, 12]", inherit_children: true
```

```python
# 硬编码
HIERARCHY_CHAIN = ['product', 'version', 'domain', 'sub_domain']
PARENT_FIELD_MAP = {'domain': 'version_id', ...}
```

**重构后** (SSOT, 维度就是数据权限):

```yaml
# meta/schemas/domain.yaml  (SSOT, 业务人员能读懂)
id: domain
data_permission_dimensions:
  - dimension: company
    field: company_id
    type: fk
  - dimension: product
    field: product_id
    type: chain  # 沿 hierarchy_chain 追溯
field_permissions:
  - field: internal_owner
    read: [role:admin]
    mask: "***HIDDEN***"
```

```yaml
# permission_dimension.yaml  (维度元数据, 可扩展)
dimensions:
  - code: product
    name: 产品
    hierarchy_chain: [product, version, domain, sub_domain]
  - code: version
    ...
```

```sql
-- 角色权限表 (不变)
role_permissions:
  - role_id: 60, permission_code: "domain:read"
  - ...

-- 角色维度范围表 (不变, 继续作为"数据权限的输入参数")
role_dimension_scope:
  - role_id: 60, dimension_code: "version", dimension_values: "[2, 11, 12]", inherit_children: true
```

**PermissionResolver 工作流** (统一运行时):

```python
def resolve(user, action, bo, record):
    # 1. Action Gate (功能权限, 不变)
    if not check_action(user, action, bo):
        return (False, {}, None, "ACTION_DENIED")

    # 2. Row Filter (数据权限, 走角色维度范围)
    user_dims = expand_dimension_values(user.roles)  # {version: {2,11,12}, ...}
    scope_filter = construct_row_filter(bo, user_dims)  # 走 BO.yaml.data_permission_dimensions
    # → "domain.id IN (...) OR domain.version_id IN (2, 11, 12)"

    # 3. Field Mask (字段权限, 走 BO.yaml.field_permissions)
    masked = get_field_masks(bo, user.roles)  # {internal_owner: "***HIDDEN***"}

    # 4. Association Derivation (关联权限, 运行时派生)
    assoc_perms = derive_association_perms(bo, record, user_dims)

    return (True, masked, scope_filter, "OK")
```

---

## 四、回答用户最后的两个问题

### Q1: "角色的权限配置（管理维度）是否会有影响？管理维度配置会映射转成数据权限？"

**A1**:

- **配置 UI 完全不变** (业务人员感知 0)
- **数据库数据完全不变** (`role_dimension_scope` 数据继续有效)
- **管理维度本身就是数据权限的"配置载体"** —— 不是"映射成"数据权限，**它就是**数据权限的"WHERE 值"输入
- **后端实现更优雅** (YAML 驱动, 拦截器统一, 无硬编码)
- **可扩展性提升** (新增维度 = 新增 1 个 permission_dimension.yaml entry, 0 代码改动)

### Q2: "数据 + 功能权限模型, 功能权限基于数据颗粒度, 是否合理？"

**A2**:

- **方向对** (Action + Row + Field + Association 4 维正交)
- **表述需要修正**:
  - ❌ "功能权限基于数据颗粒度" (容易被误解为层级)
  - ✅ **"功能权限 (Action Gate) 和数据权限 (Row Filter) 是两把独立的锁，先开后过"**
- **当前不合理之处**:
  1. 3 套体系独立配置 (无 SSOT)
  2. 维度 (管理维度) 被错误地当成独立第三层
  3. 字段权限和关联权限未纳入统一框架
- **重构后合理**:
  - YAML 单一真实源 (SSOT)
  - 维度 = 数据权限的输入参数 (不是独立层)
  - PermissionResolver 统一 4 维检查
  - 配置 UI 0 变化, 数据 0 迁移

---

## 五、给用户的最终建议

### 决策点

| 选项 | 含义 | 建议 |
|------|------|------|
| **A. 维持现状** | 3 套体系并存, 慢慢打补丁 | ❌ 不建议 (技术债加重) |
| **B. 只修 BUG-V026** | 解用户阻塞, 不动架构 | ⚠️ 短期可接受 |
| **C. 启动 4 阶段重构 (6 周)** | 完整统一, 6 周交付 | ⭐ **推荐** (用户阻塞 + 长期收益) |
| **D. 只做 Phase 1 (1 周)** | YAML 化维度元数据, 暂不统一拦截器 | ⚠️ 折中 |

### 我推荐 **C** (完整 6 周重构)

**理由**：

1. **用户已遇到 BUG-V026** (3 套体系不一致的代价)
2. **管理维度已经就是数据权限的"值域"**, 统一 0 阻力
3. **MASTER-PLAN 13-17 天文档已齐**, 实施路径明确
4. **架构债 6 周解决 vs 12+ 周拖延**, 越早越省
5. **业务人员 0 感知** (配置 UI 不变, 数据不变)

**如果担心风险**，可分两批:

- **第一批 (1.5 周)**: BUG-V026 修复 + Phase 1 (维度 YAML 化) → 立即收益
- **第二批 (4.5 周)**: Phase 2/3/4 (PermissionResolver + 字段/关联 + 废弃) → 长期收益

---

## 六、文档关联

| 文档 | 角色 |
|------|------|
| [PERMISSION_TODOS.md](PERMISSION_TODOS.md) | 当前 3 层体系盘点 (39 spec 清单) |
| [PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md](PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) | 统一架构方案 (4 阶段 6 周) |
| **[PERMISSION_MODEL_DEEP_ANALYSIS.md](PERMISSION_MODEL_DEEP_ANALYSIS.md)** | **本文档: 角色配置影响 + 权限模型评估** |
| [permission-metadata-driven-solution.md](permission-metadata-driven-solution.md) | 5 方案详细设计 |
| [permission-metadata-driven-design.md](permission-metadata-driven-design.md) | 6 断裂点诊断 |
| [meta-action-permission-analysis.md](meta-action-permission-analysis.md) | 三层权限模型现状 (待替换) |
| [specs/spec-m11-rls-implementation.md](specs/spec-m11-rls-implementation.md) | M11 RLS v1.4.0 (待升级到 v2.0) |
| [specs/spec-permission-derivation-MASTER-PLAN-2026-06-08.md](specs/spec-permission-derivation-MASTER-PLAN-2026-06-08.md) | 15 FR 派生逻辑 (Phase 3 输入) |
| [research/head-product-metadata-permission-research.md](research/head-product-metadata-permission-research.md) | SAP/Salesforce/ServiceNow 对标 |
| [sap-deep-authorization-analysis.md](sap-deep-authorization-analysis.md) | SAP Deep Authorization 机制 |
| [BACKLOG-Permission-System-Improvement.md](BACKLOG-Permission-System-Improvement.md) | 改进待办 (2026-05-08) |
