# "第三部分数据权限" 命名澄清 + role_dimension_scope 明细分析

> **日期**: 2026-06-26
> **状态**: ✅ **深入实际 UI + 实际代码** 后澄清
> **基于**: [MANAGEMENT_DIMENSION_VS_ROLE_DIMENSION.md](MANAGEMENT_DIMENSION_VS_ROLE_DIMENSION.md) 修正版

---

## 一、你提的问题的明确答案

> "**那我理解我们权限配置的第三部分数据权限 是不是需要重新命名，算是 role dimension scope 明细，照这个理解是否正确**"

**直接答案**: ⚠️ **部分正确，但完全对调了** — 你说的"第三部分"不是 role_dimension_scope 的明细，**而是另一个独立的"条件型权限"**。让我详细说明。

---

## 二、当前"权限配置" UI 的 3 个实际部分

[PermissionConfigPanel.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue) L1-86 实际只有 **3 个 panel**:

| # | 实际 UI 标题 | 数据存储 | 含义 | 代码位置 |
|---|--------------|----------|------|----------|
| **1** | **管理维度范围** | `role_dimension_scopes` | 业务人员配的 dim value 白名单 | [L4-8](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue#L4-L8) |
| **2** | **菜单与功能权限** | `menus` + `role_menu_permissions` + `permissions` + `role_permissions` | 勾选菜单 = 派功能权限 | [L11-54](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue#L11-L54) |
| **3** | **条件型权限** | `permission_rules` | 业务人员写 condition 表达式 | [L57-75](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue#L57-L75) |

[RoleDetailDrawer.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/RoleDetailDrawer.vue) L160-186 **也是同样 3 个**（独立 view）:

```vue
<!-- L160 标题 -->
<div class="standalone-data-section">
  <h4>条件型权限 <span class="section-desc">(基于条件表达式，新增资源自动继承)</span></h4>
```

**所以"第三部分"实际是 "条件型权限"**, 不是"数据权限" (虽然叫 permission_rules, 但**跟"数据权限"概念不同**)。

---

## 三、3 个 panel 实际存储 + 语义对比

### 3.1 Panel 1: 管理维度范围 (RoleDimensionScope)

**实际数据存储**：[role_dimension_scopes](file:///d:/filework/excel-to-diagram/meta/schemas/role_dimension_scope.yaml) 表

```sql
CREATE TABLE role_dimension_scopes (
  id, role_id, dimension_code, dimension_values JSON,
  inherit_children, scope_mode  -- 'include' / 'exclude'
);
```

**业务含义**: **白名单** — 业务人员选 dim + 选 dim values

**实际 UI** ([DimensionScopePanel](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/DimensionScopePanel.vue)):
```
[产品]   [智能座舱 ×] [自动驾驶 ×] [+ 添加产品] ☐ 包含下级
[版本]   [v1.0 ×] [v2.0 ×] [+ 添加版本] ☐ 包含下级
[领域]   [供应链 ×] [+ 添加领域]   ☐ 包含下级
[子领域] [+ 添加子领域]           ☐ 包含下级
[自动推导并应用] [保存维度范围]
```

**实际实现**：[DimensionScopeEngine.derive_data_conditions](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L209-L260) → SQL

### 3.2 Panel 2: 菜单与功能权限 (Menu + Functional Perm)

**实际数据存储**：
```sql
CREATE TABLE menus (
  id, menu_code, menu_name, bo_bindings JSON,  -- 含 include_actions
  required_permissions JSON, ...
);
CREATE TABLE permissions (id, code, name, ...);  -- 'domain:read' etc.
CREATE TABLE role_permissions (id, role_id, permission_id, ...);
CREATE TABLE role_menu_permissions (id, role_id, menu_code, ...);
```

**业务含义**: **能力清单** — 业务人员勾菜单 (自动派生 functional perm)

**实际 UI** ([MenuPermissionMatrix](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/MenuPermissionMatrix.vue)):
```
[产品管理]    [✓ 读] [✓ 写] [✓ 删] [✓ 导入] [✓ 导出]
[版本管理]    [✓ 读] [✓ 写] [✓ 删]
[领域管理]    [✓ 读] [✓ 写] [✓ 删] [✓ 导出]
[关系管理]    [✓ 读] [✓ 写]
[关联权限配置] (弹窗配置关联 permission)
```

**实际实现**：[PermissionService.has_permission](file:///d:/filework/excel-to-diagram/meta/services/permission_service.py#L91) → JWT check

### 3.3 Panel 3: 条件型权限 (ConditionRule)

**实际数据存储**：[permission_rules](file:///d:/filework/excel-to-diagram/meta/schemas/permission_rule.yaml) 表

```sql
CREATE TABLE permission_rules (
  id, role_id, resource_type,
  condition TEXT,  -- 'version_id IN (1, 2) AND domain_type = "CORE"'
  permission_level VARCHAR(20),  -- 'none' / 'read' / 'write' / 'admin'
  is_denied INTEGER,  -- 禁止权优先
  inherit_to_children INTEGER,
  propagate_to_parents INTEGER,
  analysis_mode TEXT,  -- JSON
  ...
);
```

**业务含义**: **条件表达式** — 业务人员手写 SQL 谓词

**实际 UI** ([ConditionRuleList](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/ConditionRuleList.vue)):
```
[领域]  version_id IN (2, 11, 12)  [可读] [继承] [编辑] [删除]
[领域]  domain_type = "FINANCE"    [禁止] [继承] [编辑] [删除]
[产品]  is_public = 1 AND owner_id != 333  [可写] [继承] [编辑] [删除]
[+ 添加条件规则]
```

**实际实现**：[ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) + [ConditionEvaluator](file:///d:/filework/excel-to-diagram/meta/services/condition_evaluator.py) → 安全白名单 + SQL 解析

**关键警告** ([ConditionPermissionService.py L1-13](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py)):
> "**Oracle 风格混合权限模型 + 用友BIP特性**:
> - 条件型权限规则 (替代实例型 resource_id)
> - Owner 自动权限
> - **禁止权优先原则**
> - **向下继承** (天然实现)
> - **向上传播**"

**注意**: [ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) 在 **主路径拦截器未集成** — 它被设计为"分析模式"独立工具, 实际**不参与拦截器链**。

---

## 四、你说的"role dimension scope 明细" 实际是什么？

**你的理解**:
> "第三部分数据权限 算是 role dimension scope 明细"

**实际状态**:
- ⚠️ **role_dimension_scope (Panel 1) 没有"明细"子页面** — 它本身就是主配置, 业务人员直接配 dim value
- ⚠️ **role_dimension_scope 的"明细"概念不存在** — `role_dimension_scopes` 表只有 5 个字段 (id, role_id, dimension_code, dimension_values, inherit_children, scope_mode)
- ❌ **Panel 3 (条件型权限) 跟 role_dimension_scope 完全无关** — 它用 `permission_rules` 表, 不读 `role_dimension_scopes`

**所以你说的"第三部分"和"role_dimension_scope 明细"对调了**:

| 实际 UI 面板 | 实际存储 | 业务概念 | 你的理解 |
|------------|----------|---------|----------|
| Panel 1: 管理维度范围 | `role_dimension_scopes` | dim value 白名单 | ✓ 跟 role_dimension_scope 强相关 |
| Panel 2: 菜单与功能权限 | `permissions` + `role_permissions` | functional perm 矩阵 | ✗ 跟 role_dimension_scope 无关 |
| **Panel 3: 条件型权限** | `permission_rules` | **条件表达式 (跟 dim scope 无关)** | ❌ 你以为它是 dim scope 明细 |

**真相是**:
- **Panel 1 (管理维度范围)** 才是 `role_dimension_scope` 的配置入口
- **Panel 3 (条件型权限)** 跟 `role_dimension_scope` **完全没有关系**, 是**完全独立的"高级权限"机制**

---

## 五、那 "Panel 3 条件型权限" 应该改名叫什么？

### 5.1 现在的命名问题

当前叫"**条件型权限**" ([PermissionConfigPanel.vue L60](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue#L60)):

```vue
<h4>
  <AppIcon name="filter" :size="14" />
  条件型权限
</h4>
<p class="section-desc">(基于条件表达式，新增资源自动继承)</p>
```

**问题**:
- ⚠️ 叫"权限" 但 UI 标题和位置让业务人员误以为是"数据权限"
- ⚠️ 实际是**条件表达式驱动的权限规则** (跟 data permission 不是一回事)
- ⚠️ 但 [ConditionPermissionService L30](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L30) 头部说: "**条件型权限规则 (替代实例型 resource_id)**"
- ⚠️ 你说的"第三部分数据权限" 实际是 UI 标签里没有"数据"二字, 但你直觉认为它是"数据权限"

### 5.2 建议的新命名 (4 个备选)

| 备选 | 命名 | 理由 | 推荐度 |
|------|------|------|--------|
| **A** | **"高级数据权限规则"** | 明确"数据"属性 + "高级"区别于 Panel 1 白名单 | ⭐⭐⭐ |
| **B** | **"条件规则 (Condition Rules)"** | 保留原意 + 中英对照, 不混淆 | ⭐⭐ |
| **C** | **"自定义 SQL 谓词"** | 直接说技术实现, 业务人员少用 | ⭐ |
| **D** | **"实例级权限规则"** | 跟 [ConditionPermissionService L30](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L30) "替代实例型 resource_id" 对齐 | ⭐ |

**我推荐 A (高级数据权限规则)**, 因为:
- ✅ 业务人员能直接理解 (有"数据"+"权限"两词)
- ✅ "高级" 跟 Panel 1 的"白名单"区分 (高级 = 表达式)
- ✅ 跟 [DimensionScopePanel](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/DimensionScopePanel.vue) 的"管理维度范围" 概念层级一致 (都是"数据权限"的子集)

### 5.3 不建议改的命名 (3 个反例)

| 命名 | 反例原因 |
|------|---------|
| ~~"role dimension scope 明细"~~ | ❌ 完全错误, role_dimension_scope 跟 permission_rules 无关系 |
| ~~"数据权限"~~ | ❌ 太宽泛, 跟 Panel 1 (管理维度范围) 冲突 |
| ~~"权限规则"~~ | ❌ 太抽象, 看不出是数据相关还是功能相关 |

---

## 六、Panel 3 跟 "数据权限" 关系 (实际代码)

### 6.1 业务人员视角 (UI 标题 + 描述)

**Panel 1**: "管理维度范围" + "配置角色的管理维度范围。系统将基于此自动推导菜单、功能权限和数据权限规则。"
**Panel 3**: "条件型权限" + "基于条件表达式，新增资源自动继承"

**业务人员看到 "数据权限" 二字** → 误以为 Panel 1 = "数据权限"，Panel 3 = "高级数据权限"。

**但实际**:

| Panel | 实际功能 | 跟"数据权限"关系 |
|-------|----------|-----------------|
| Panel 1 (管理维度范围) | 配 dim value 白名单 | ✅ **是** "数据权限" (读路径行过滤) |
| Panel 2 (菜单与功能权限) | 配 functional perm | ❌ "功能权限" |
| Panel 3 (条件型权限) | 写 condition 表达式 | ⚠️ **"高级数据权限"** (但 UI 没标"数据") |

**所以"第三部分数据权限" = "Panel 3 条件型权限"** — 你的理解部分正确 (确实是数据权限), 但 **它跟 role_dimension_scope 无关**, 是**独立的 condition 表达式机制**。

### 6.2 实际数据流对比

#### Panel 1 (role_dimension_scope) 数据流
```
Business: 配 dim scope "产品" = [1, 17]
  ↓
DB: role_dimension_scopes (60, 'product', '[1,17]')
  ↓
Runtime: DimensionScopeEngine.expand → derive_data_conditions
  ↓
SQL: "version.product_id IN (1, 17)"
  ↓
Interceptor: DataPermissionInterceptor (P30 读) + WriteScopeInterceptor (P35 写)
```

#### Panel 3 (permission_rules) 数据流
```
Business: 写 condition "version_id IN (2, 11) AND domain_type = 'CORE'"
  ↓
DB: permission_rules (60, 'domain', 'version_id IN ...', 'read', 0, 1, 1)
  ↓
Runtime: ConditionEvaluator.evaluate(condition, record)
  ↓
Boolean: True/False (匹配/不匹配)
  ↓
Interceptor: ⚠️ **主路径拦截器未集成** — 实际不参与拦截器链
```

**关键差异**:
- Panel 1 → **拦截器自动用** (派生 SQL 注入到 query_conditions)
- Panel 3 → **业务 UI 独立工具**, **拦截器不读**

---

## 七、Panel 3 的真实角色 (基于实际代码)

[ConditionPermissionService.py L1-13](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L1-L13) 头部说明:

> "条件解析器 / Oracle 风格混合权限模型 + 用友BIP特性:
> - 条件型权限规则 (替代实例型 resource_id)
> - Owner 自动权限
> - **禁止权优先原则**
> - **向下继承** (天然实现)
> - **向上传播**"

[ConditionPermissionService L30](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L30) 文档说明:

> "**禁止权优先原则**"
> "**向下继承** (天然实现)"
> "**向上传播**"

[ConditionPermissionService L571-573](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L571-L573) 重要注释:

> "[重构后] 权限解析路径: User → UserGroup → Role → DataPermission
> 不再直接查询 group_data_permissions (**已废弃**)"

**所以 Panel 3 的真实角色**:
- ⚠️ **历史**: Oracle / 用友 BIP 风格的"高级数据权限" (跟 SAP 早期 SU24/SU53 类似)
- ⚠️ **现状**: 业务 UI 已实现, **主路径拦截器未集成** (仅 [preview_matching_resources](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L426) 用作分析预览)
- 📋 **设计意图**: 替代 [role_data_permissions](file:///d:/filework/excel-to-diagram/meta/schemas/role_data_permissions.yaml) (实例级, 已废弃) — 但实际未完全替代

---

## 八、回答你的问题: "第三部分数据权限 是不是 role dimension scope 明细"

### Q: 第三部分数据权限 是不是 role dimension scope 明细？

**答**: ❌ **完全不是** — 这两个是**完全独立的机制**:

| 维度 | Panel 1 (管理维度范围) | Panel 3 (条件型权限) |
|------|------------------------|---------------------|
| **存储** | `role_dimension_scopes` 表 | `permission_rules` 表 |
| **输入** | dim code + dim values (白名单) | resource_type + condition 表达式 |
| **输出** | SQL WHERE 条件 | Boolean 匹配 (True/False) |
| **拦截器集成** | ✅ 全部集成 (P30 读 + P35 写) | ❌ 主路径未集成 |
| **数据范围** | role + dimension + values | role + resource + condition |
| **业务感知** | "我能看哪些产品" | "对哪些资源按条件生效" |
| **关系** | 跟 dimension 链 (product→version→domain) 联动 | 跟 condition 表达式 联动 |
| **dim mapping** | 用 [dimension_object_mapping.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/dimension_object_mapping.yaml) | 用 [condition_evaluator](file:///d:/filework/excel-to-diagram/meta/services/condition_evaluator.py) ALLOWED_FIELDS 白名单 |

**它们是**:
- **平行独立**: 2 个不同表, 2 个不同 service, 2 个不同 UI panel
- **互不依赖**: 配 Panel 1 不影响 Panel 3, 配 Panel 3 不影响 Panel 1
- **互补关系**: Panel 1 (白名单) + Panel 3 (条件规则) = 数据权限的"白+黑"双维度

### Q: 那 Panel 3 应该叫什么？

**我建议**:
- **A (推荐)**: "**高级数据权限规则**" — 业务能理解, 跟 Panel 1 区分, 跟 [ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) "高级" 调性一致
- **B (备选)**: "**条件规则 (Condition Rules)**" — 保留中英对照, 不混淆

**不推荐**:
- ~~"role dimension scope 明细"~~ — 完全错误的概念
- ~~"数据权限"~~ — 太宽泛, 跟 Panel 1 冲突
- ~~"权限规则"~~ — 太抽象

---

## 九、Panel 3 是不是要重命名？

### 9.1 业务影响

- 业务人员**没有"重命名"诉求** — 当前名称"条件型权限"已用了很久
- 但**新业务人员**容易误解 (你这次就误以为它是 role_dimension 明细)
- **重命名有教育意义**, 但**功能 0 变化**

### 9.2 建议

1. **短期 (1 天)**: 不改 UI 标题, 但在 [PermissionConfigPanel.vue L62](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue#L62) 加说明:
   ```vue
   <p class="section-desc">
     (基于条件表达式的高级数据权限规则, 跟"管理维度范围"独立)
   </p>
   ```

2. **中期 (1 周)**: 改 UI 标题 + 描述:
   ```vue
   <h4>
     <AppIcon name="filter" :size="14" />
     高级数据权限规则
   </h4>
   <p class="section-desc">
     (基于条件表达式的高级数据权限, 跟管理维度范围 (白名单) 独立)
   </p>
   ```

3. **长期 (1 月)**: 统一命名规范:
   - Panel 1: "**管理维度范围**" → 保留
   - Panel 2: "**菜单与功能权限**" → 保留
   - Panel 3: "**高级数据权限规则**" → 改
   - 加 "**字段脱敏**" 4th panel (M11 YAML 的 field_masks)

### 9.3 是否需要重命名？

**答**: ⚠️ **可以重命名, 但不是优先级最高的事情**。

**优先级**:
- **P1 (高)**: 修 [ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) 主路径未集成 (它现在只是个 UI 工具, 拦截器不读)
- **P2 (中)**: 把 Panel 3 跟 [role_data_permissions](file:///d:/filework/excel-to-diagram/meta/schemas/role_data_permissions.yaml) (废弃) 合并, 让 [ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) 真正成为"数据权限 = read/write/admin 3 级" 的主路径
- **P3 (低)**: UI 标题改为 "高级数据权限规则"

---

## 十、最终答案

### Q: 第三部分数据权限 是不是 role dimension scope 明细?

**❌ 完全不是** — 它们是**完全独立的 2 个机制**:

| 实际 | 存储表 | 拦截器集成 |
|------|--------|-----------|
| 管理维度范围 (Panel 1) | `role_dimension_scopes` | ✅ 全部集成 |
| 条件型权限 (Panel 3) | `permission_rules` | ❌ 主路径未集成 (仅 UI 工具) |

### Q: 第三部分数据权限 需要重命名吗?

**⚠️ 可以, 但不是优先项** — 推荐改名为 "**高级数据权限规则**" (P3 优先级)。

### Q: 实际关系?

- Panel 1 (管理维度范围) = "我能看/写哪些数据 (白名单)"
- Panel 3 (条件型权限) = "对哪些资源按什么条件生效 (高级规则)"
- **两者都是数据权限**, 但 **存储 / 服务 / 拦截器 / UI 都独立**

### 加分理解

- "**管理维度范围**" = dim value 白名单, 自动派生 SQL → 拦截器自动用
- "**条件型权限**" = condition 表达式, 仅 UI 工具, **拦截器不读** (这是 [ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) 当前的真实状态)
- **真正的"统一数据权限"** = 1 个 PermissionResolver 整合 role_dimension_scope + permission_rules + role_data_permissions (废弃) + 字段脱敏, 走主路径

### 文档关联

- [MANAGEMENT_DIMENSION_VS_ROLE_DIMENSION.md](MANAGEMENT_DIMENSION_VS_ROLE_DIMENSION.md) — 管理维度 vs role_dimension 关系
- [PERMISSION_DEEP_DIVE.md](PERMISSION_DEEP_DIVE.md) — 9 机制完整分析
- [PermissionConfigPanel.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue) — 3 panel 实际 UI
- [RoleDetailDrawer.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/RoleDetailDrawer.vue) — 独立 view, 同样 3 panel
- [DimensionScopePanel.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/DimensionScopePanel.vue) — Panel 1 实际 UI
- [ConditionRuleList.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/ConditionRuleList.vue) — Panel 3 实际 UI
- [ConditionPermissionService.py](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) — Panel 3 背后的服务
- [role_dimension_scope.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/role_dimension_scope.yaml) — Panel 1 存储表 schema
- [permission_rule.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/permission_rule.yaml) — Panel 3 存储表 schema
