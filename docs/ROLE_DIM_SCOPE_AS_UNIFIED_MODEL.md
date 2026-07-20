# role_dimension_scope 统一模型深度分析

> **日期**: 2026-06-26
> **状态**: ✅ **深入实际代码** 后澄清
> **基于**: [DATA_PERMISSION_THIRD_PANEL_RENAMING.md](DATA_PERMISSION_THIRD_PANEL_RENAMING.md) 修正版

---

## 一、你的问题核心洞察

> "**role dimension scope 背后不也是条件吗，这个是否可以作为 role dimension scope 统一的模型？**"

**直接答案**: ⚠️ **观察正确！但方向反了**。

让我详细说明你的洞察:
- ✅ **正确**: role_dimension_scope 背后**确实是条件** (生成的 SQL 是 `field IN (v1, v2, ...)` 这种条件表达式)
- ✅ **正确**: permission_rules (条件型权限) **可以**统一到 role_dimension_scope 模型
- ⚠️ **但应该反过来**: 不是"permission_rules 改成 role_dimension_scope", 而是 **"role_dimension_scope 应该是 condition 表达式的特例"**

**真相**:
- role_dimension_scope = 简化版 condition (用 ID 列表自动生成 `field IN (...)`)
- permission_rules = 通用版 condition (业务人员手写 `field OP value [AND ...]`)
- **两者是同一件事的不同表达层级**

---

## 二、role_dimension_scope 实际生成的 SQL（实证）

### 2.1 业务人员配的"白名单"配置

```sql
-- role_dimension_scopes 表
role_id: 60
dimension_code: 'product'
dimension_values: '[1, 17]'   -- 白名单 ID 列表
inherit_children: true        -- 沿 chain 展开
scope_mode: 'include'         -- include/exclude
```

### 2.2 实际派生出的 SQL（看代码就懂）

[DimensionScopeEngine.derive_data_conditions](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L209-L260) 生成的 SQL:

```python
# Case 1: 直接匹配 (filter_type='direct')
#   dimension=product, bo=product, field=id
#   → product.id IN (1, 17)  # ← 实际上就是 "条件"!

# Case 2: 外键匹配 (filter_type='fk')
#   dimension=product, bo=version, field=product_id
#   → version.product_id IN (1, 17)  # ← 也是 "条件"!

# Case 3: 链式追溯 (filter_type='chain')
#   dimension=product, bo=domain, field=product_id (chain)
#   → 沿 version 表追溯 product_id
#   → 实际 SQL:
#   domain.id IN (SELECT id FROM domains
#                 WHERE version_id IN (SELECT id FROM versions
#                                      WHERE product_id IN (1, 17)))  # ← 还是 "条件"!
```

**关键**: **role_dimension_scope 派生的 SQL 本质上就是 "WHERE field IN (v1, v2, ...)"** — **这就是条件表达式!**

### 2.3 role_dimension_scope 的"条件表达式"视角重新理解

| 业务人员视角 | 条件表达式视角 | SQL |
|------------|--------------|-----|
| 配 dim scope "产品"=[1, 17] | `product_id IN (1, 17)` | `WHERE product_id IN (1, 17)` |
| inherit_children=True | 自动添加 `version_id` 链 | `AND version_id IN (...)` |
| scope_mode=exclude | `NOT (product_id IN ...)` | `WHERE NOT (product_id IN ...)` |
| 多个 dim 同时配 | `dim1 IN (...) AND dim2 IN (...)` | `WHERE ... AND ...` |

**关键洞察**:
- role_dimension_scope = **"白名单形式的条件表达式"**
- permission_rules = **"通用形式的条件表达式"**
- **两者都是 WHERE 子句, 只是表达方式不同**

---

## 三、permission_rules 实际支持的语法

### 3.1 ConditionEvaluator 实际支持的表达式

[ConditionEvaluator.py L62-79](file:///d:/filework/excel-to-diagram/meta/services/condition_evaluator.py#L62-L79):

```python
# 支持的表达式语法 (WHERE 子句子集):
# - field = value
# - field = 'string'
# - field != value
# - field IN (v1, v2, v3)
# - field > 数字
# - field < 数字
# - AND 组合
# - JSON 范围 ({field: {gte: 1, lte: 100}})
```

**完整表达式能力**:
```sql
-- 业务人员手写 (ConditionRuleList UI 输):
version_id IN (2, 11, 12)
domain_type = "FINANCE"
is_public = 1 AND owner_id != 333
created_at > '2026-01-01'
amount >= 1000 AND amount < 10000
{priority: {gte: 1, lte: 5}}  -- JSON 范围
```

### 3.2 对比: role_dimension_scope 支持的"子集"

| 表达式 | permission_rules | role_dimension_scope | 差距 |
|--------|------------------|----------------------|------|
| `field IN (v1, v2, v3)` | ✅ | ✅ (dimension_values) | 完全等价 |
| `field = value` | ✅ | ❌ | permission_rules 多 |
| `field != value` | ✅ | ❌ (但可配 scope_mode=exclude) | permission_rules 多 |
| `field > value` | ✅ | ❌ | permission_rules 多 |
| `field < value` | ✅ | ❌ | permission_rules 多 |
| `field BETWEEN` | ✅ | ❌ | permission_rules 多 |
| **AND 组合** | ✅ | ✅ (多 dim 联动) | 完全等价 |
| **OR 组合** | ❌ (不支持) | ❌ | 都缺 |
| **JSON 范围** | ✅ | ❌ | permission_rules 多 |

**关键**:
- role_dimension_scope = **简化版**, 只支持 `IN` + 多 dim AND
- permission_rules = **完整版**, 支持 `IN/=/!=/>/<` + AND 组合 + JSON
- **permission_rules ⊇ role_dimension_scope** (从表达力看)

---

## 四、统一模型的可行性分析

### 4.1 你的统一方案 (我的理解)

**目标**: 把 role_dimension_scope + permission_rules 统一为 1 个模型

**核心想法**:
- role_dimension_scope = permission_rules 的 "白名单特例"
- permission_rules = role_dimension_scope 的 "通用形式"
- **统一为 1 个 "条件表达式模型"**

**实施后**:
- 业务人员不区分 "配白名单" vs "写条件"
- 所有"数据权限"都走 1 个表 + 1 个 service + 1 个 UI

### 4.2 可行性结论: ✅ **完全可行, 且强烈推荐**

**为什么可行**:

1. **底层都是条件表达式**
   - role_dimension_scope → 派生 `field IN (...)` SQL
   - permission_rules → 业务人员写 `field OP value` 表达式
   - **两者都是 WHERE 子句, 可以统一存储 + 统一执行**

2. **role_dimension_scope 已经是 "简化条件表达式"**
   - 业务人员配 "产品"=[1,17] ≡ 写 `product_id IN (1, 17)`
   - 业务人员配 inherit_children ≡ 写 `AND version_id IN (...)` (自动展开)
   - 业务人员配 scope_mode=exclude ≡ 写 `NOT (product_id IN ...)`
   - **role_dimension_scope 是 permission_rules 的"用户友好封装"**

3. **permission_rules ⊇ role_dimension_scope** (表达力)
   - permission_rules 支持所有 role_dimension_scope 表达式
   - 反之不成立

4. **UI 现状已经隐含"统一"**
   - Panel 1 (管理维度范围) 是 "简化表单"
   - Panel 3 (条件型权限) 是 "通用表达式"
   - 业务人员已经知道两者是"同一类权限"的不同表达形式

### 4.3 实施影响

| 影响 | 业务感知 |
|------|----------|
| 统一表 (permission_rules 扩展 + role_dimension_scopes 退役) | ⚠️ 业务 0 变化 (新表兼容旧表) |
| 统一 service (ConditionPermissionService 升级) | ⚠️ 开发 0 变化 (API 兼容) |
| 统一 UI (Panel 1 + Panel 3 合并为 "数据权限规则") | ⚠️ UI 改 |
| 统一拦截器 (主路径集成 [ConditionPermissionService](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py)) | ✅ 解决 P1 主路径未集成问题 |

---

## 五、推荐统一模型设计

### 5.1 统一表 schema (Phase 1, 1 周)

```sql
-- 统一表: data_permission_rules (合并 role_dimension_scopes + permission_rules)
CREATE TABLE data_permission_rules (
  id INTEGER PRIMARY KEY,
  role_id INTEGER NOT NULL,                          -- 角色
  resource_type VARCHAR(50) NOT NULL,                 -- 'product' / 'version' / 'domain' / ...
  rule_type VARCHAR(20) NOT NULL,                    -- 'dimension' / 'condition' (区分两种)
  -- 通用字段:
  condition TEXT NOT NULL,                           -- 通用条件表达式
  permission_level VARCHAR(20) DEFAULT 'read',        -- 'read' / 'write' / 'admin'
  is_denied INTEGER DEFAULT 0,                       -- 禁止权优先
  inherit_to_children INTEGER DEFAULT 1,             -- 向下继承
  propagate_to_parents INTEGER DEFAULT 0,           -- 向上传播
  analysis_mode TEXT,                                -- JSON: 维度元数据
  created_at, updated_at, created_by
);

-- 旧表保留 (向后兼容, 6 个月观察期):
-- role_dimension_scopes (被 dimension_type 替代, 自动迁移)
-- permission_rules (被通用化, 自动迁移)
```

**两种 rule_type**:
- `dimension`: 由"白名单"自动派生的 condition (用 `rule_type` 标识)
- `condition`: 业务人员手写的 condition

**统一 condition 表达式**:
- 全部存为 `condition TEXT` (跟 permission_rules 一致)
- dimension 类型: 自动派生成 `field IN (v1, v2)` 格式, 由 trigger 维护

### 5.2 统一 service (Phase 2, 2 周)

```python
# 升级 ConditionPermissionService
class ConditionPermissionService:
    # 现有 CRUD 保留
    def create_rule(self, role_id, resource_type, condition, ...):
        # 接受 dimension 形式的 condition (如 'product_id IN (1, 17)')
        # 自动展开 + 写入 data_permission_rules
        ...

    def expand_dimension(self, role_id, dim_code, dim_values):
        # 跟 DimensionScopeEngine.expand_dimension_values 融合
        # 沿 chain 展开 + 写回 condition
        ...

    # 新增: 集成到拦截器链
    def evaluate_request(self, user, action, bo, record):
        # 1. 查 data_permission_rules
        # 2. 评估所有 condition (用 ConditionEvaluator)
        # 3. 任意匹配即放行 (or 拒绝权优先)
        # 4. 返回 (True, reason) / (False, reason)
        ...
```

**统一拦截器集成** (解决 P1 主路径未集成问题):

```python
# meta/core/interceptors/permission_interceptor.py
# 现有: _check_legacy_permission + _check_yaml_permission
# 新增: _check_condition_rule
def _check_condition_rule(self, context):
    rules = condition_perm_service.get_matching_rules(
        user_id=context.user.id,
        resource_type=context.bo,
        action=context.action
    )
    for rule in rules:
        matched, reason = condition_perm_service.evaluate(rule, context.record)
        if matched:
            if rule.is_denied:
                return False, f"DENIED_BY_RULE_{rule.id}"
            return True, f"ALLOWED_BY_RULE_{rule.id}"
    return None, None  # 没有匹配规则, 继续其他检查
```

### 5.3 统一 UI (Phase 3, 1 周)

**合并 Panel 1 + Panel 3** → "**数据权限规则**" (单一 panel):

```vue
<template>
  <div class="data-permission-panel">
    <h4>数据权限规则 <span class="desc">(统一管理: 白名单 + 条件表达式)</span></h4>

    <!-- 快速区: 白名单 (原 Panel 1 简化) -->
    <div class="quick-section">
      <h5>快速模式 - 维度白名单</h5>
      <DimensionQuickForm v-model="dimensionConfig" />
      <!-- 业务人员选 "产品" = [1, 17] → 自动写 condition: product_id IN (1, 17) -->
    </div>

    <!-- 高级区: 通用表达式 (原 Panel 3) -->
    <div class="advanced-section">
      <h5>高级模式 - 通用条件表达式</h5>
      <ConditionRuleList v-model="conditionRules" />
      <!-- 业务人员写 condition: version_id IN (2,11) AND domain_type = "CORE" -->
    </div>
  </div>
</template>
```

**业务感知**:
- 简化业务人员路径: "我要配数据权限" → 进 1 个 panel → 选简化模式或高级模式
- 老用户 0 改 (Panel 1 快速区完整保留)
- 新用户更清晰 (一个 panel 一种业务: "数据权限")

### 5.4 Phase 4: 退役旧表 (3 个月后, 1 周)

- role_dimension_scopes 表保留但**停止写入** (写 trigger 转写到 data_permission_rules)
- permission_rules 表保留但**停止写入** (同 trigger)
- 6 个月后**DROP 旧表**

---

## 六、实施路线 (3 阶段, 4 周)

### Phase 1: 统一表 + 数据迁移 (1 周)

| 任务 | 工作量 |
|------|--------|
| 创建 data_permission_rules 表 | 0.5d |
| 数据迁移脚本 (role_dimension_scopes → dimension 形式) | 1d |
| 数据迁移脚本 (permission_rules → 通用化) | 1d |
| 双写 trigger (兼容期) | 0.5d |
| 单元测试 | 1d |
| 集成测试 | 1d |

**产出**: 旧表 + 新表双写, 业务 0 变化, 新表可读

### Phase 2: 统一 service + 拦截器集成 (2 周)

| 任务 | 工作量 |
|------|--------|
| ConditionPermissionService 升级 (兼容 dimension + condition) | 1d |
| DimensionScopeEngine 与 ConditionPermissionService 融合 | 2d |
| 拦截器集成 (_check_condition_rule) | 1d |
| 单元测试 (condition 评估) | 1d |
| E2E 测试 (业务人员视角) | 2d |
| 性能测试 (SQL 注入正确性) | 1d |
| 文档更新 | 1d |

**产出**: 拦截器链支持 condition rules, 业务人员配的 condition 真的生效了 (解决 P1!)

### Phase 3: 统一 UI + 退役旧表 (1 周)

| 任务 | 工作量 |
|------|--------|
| UI 合并 (Panel 1 + Panel 3) | 2d |
| UI 测试 (旧用户 + 新用户) | 1d |
| 退役旧表 (停止双写) | 0.5d |
| 6 个月观察期 (DROP 计划) | - |

**产出**: 1 个数据权限 panel, 业务更清晰

### 累计 4 周, 1 人

---

## 七、对比: 不统一的现状 vs 统一的未来

### 7.1 不统一 (现状)

**业务人员视角**:
```
Panel 1: "管理维度范围"
  - 配 "产品"=[1, 17] → 系统自动生成 SQL
Panel 2: "菜单与功能权限"
  - 勾菜单 → 系统自动派生 functional perm
Panel 3: "条件型权限"
  - 手写 condition → 业务人员自己写 SQL
```

**问题**:
- ⚠️ Panel 3 拦截器不集成 (业务人员配了**实际不生效**)
- ⚠️ 业务人员不知道 "配 Panel 3 没用"
- ⚠️ 维护 3 个表 + 3 个 service + 3 个 UI panel

### 7.2 统一 (未来)

**业务人员视角**:
```
"数据权限规则" (1 个 panel)
  - 快速模式: 配 "产品"=[1, 17] (原 Panel 1)
  - 高级模式: 手写 condition (原 Panel 3)
  - **都真正生效** (拦截器集成)
```

**优势**:
- ✅ 业务人员知道 "我配的都对生效"
- ✅ 维护 1 个表 + 1 个 service + 1 个 UI panel
- ✅ 表达力统一 (condition 通用化)
- ✅ 解决 P1 主路径未集成问题

---

## 八、回答你的 2 个核心问题

### Q1: role dimension scope 背后不也是条件吗?

**✅ 完全正确**。我读 [derive_data_conditions](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L209-L260) 后确认:
- role_dimension_scope 派生的 SQL **本质就是 `field IN (v1, v2, ...)`** 条件
- inherit_children = 自动添加 `AND parent_field IN (...)` 条件
- scope_mode=exclude = 自动加 `NOT (...)` 条件
- **业务人员配的"白名单"就是"白名单形式的条件表达式"**

### Q2: 是否可以作为 role dimension scope 统一的模型?

**✅ 完全可行, 且强烈推荐**。

**核心思路**:
- role_dimension_scope = **"白名单"形式的条件表达式** (简化)
- permission_rules = **"通用"形式的条件表达式** (完整)
- **统一为 1 个 condition 表达式模型** (底层都是 WHERE 子句)

**具体方案** (4 周实施):
1. **统一表**: data_permission_rules (合并 role_dimension_scopes + permission_rules)
2. **统一 service**: ConditionPermissionService 升级, 集成 DimensionScopeEngine
3. **统一 UI**: 合并 Panel 1 + Panel 3 → "数据权限规则"
4. **统一拦截器**: 解决 P1 主路径未集成问题 (关键收益!)

**业务影响**:
- ⚠️ 业务 0 变化 (旧表双写兼容, 旧 UI 保留)
- ✅ 业务人员知道 "配的都对生效"
- ✅ 减少 1 个 panel (从 3 减到 2)

**技术价值**:
- ✅ 解决 [ConditionPermissionService 主路径未集成 P1 问题](PERMISSION_TODOS.md)
- ✅ 解决 [PERMISSION_DEEP_DIVE.md 9 机制并存](PERMISSION_DEEP_DIVE.md) 的"条件型权限" 那一支
- ✅ 整合 [DATA_PERMISSION_THIRD_PANEL_RENAMING.md 命名问题](DATA_PERMISSION_THIRD_PANEL_RENAMING.md) — 不用纠结叫"条件型权限"还是"管理维度范围", 统一叫"数据权限规则"

---

## 九、关键洞察总结

### 9.1 你的核心洞察

> "**role dimension scope 背后不也是条件吗**"

**✅ 100% 正确**。这是整个权限体系的核心 insight:
- **数据权限的本质 = 条件表达式** (SQL WHERE 子句)
- role_dimension_scope = 简化条件 (`field IN (白名单)`)
- permission_rules = 完整条件 (`field OP value [AND ...]`)
- **两者底层都是条件表达式**

### 9.2 你的统一建议

> "**是否可以作为 role dimension scope 统一的模型**"

**✅ 完全可行**。统一模型:
- 单一表: `data_permission_rules` (condition TEXT 通用化)
- 单一 service: ConditionPermissionService (升级)
- 单一 UI: 合并 Panel 1 + Panel 3
- **关键收益**: 解决主路径未集成 P1 问题

### 9.3 副效应: 也解决了之前的命名问题

之前的 [DATA_PERMISSION_THIRD_PANEL_RENAMING.md](DATA_PERMISSION_THIRD_PANEL_RENAMING.md) 纠结于 Panel 3 该叫"条件型权限"还是"高级数据权限规则"。

**统一后, 不需要纠结**:
- Panel 叫 "**数据权限规则**" (统一)
- 内部 `rule_type` 区分: `dimension` (白名单) vs `condition` (通用表达式)
- 业务感知 0: 都是"数据权限规则", 只是两种表达形式

### 9.4 终极模型: 4 维正交统一

完整数据权限 = 4 维正交 (基于你的洞察):

| 维度 | 表达式 | 表达形式 |
|------|--------|----------|
| **1. Dimension (白名单)** | `dim_code IN (v1, v2, ...)` | 简化 |
| **2. Condition (通用)** | `field OP value [AND ...]` | 完整 |
| **3. Visibility (BO.yaml)** | `field OP value` | 硬编码 |
| **4. Owner Exception** | 沿 HIERARCHY_CHAIN 追溯 | 自动 |

**统一为 1 个模型** = 1 个 ConditionEvaluator + 1 个 rule_type 枚举:
- `dimension` (原 role_dimension_scopes)
- `condition` (原 permission_rules)
- `visibility` (原 BO.yaml.authorization.scope, 升级为 DB 存储)
- `owner` (自动)

**完美统一**: 业务人员配 1 处, 系统用 1 个 evaluator, 1 个拦截器。

---

## 十、文档关联

- [DATA_PERMISSION_THIRD_PANEL_RENAMING.md](DATA_PERMISSION_THIRD_PANEL_RENAMING.md) — 之前的命名问题 (统一后不需要纠结)
- [MANAGEMENT_DIMENSION_VS_ROLE_DIMENSION.md](MANAGEMENT_DIMENSION_VS_ROLE_DIMENSION.md) — 管理维度 vs role_dimension 关系
- [PERMISSION_DEEP_DIVE.md](PERMISSION_DEEP_DIVE.md) — 9 机制完整分析 (条件型权限是其中 1 个)
- [PERMISSION_TODOS.md](PERMISSION_TODOS.md) — P1 主路径未集成问题 (本文统一后能解决)
- [derive_data_conditions L209-L260](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L209-L260) — role_dim_scope 实际 SQL 生成
- [_build_chain_condition L414](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L414) — 链式 SQL 构造 (证明白名单就是条件)
- [ConditionPermissionService.py](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py) — Panel 3 背后服务 (主路径未集成)
- [ConditionEvaluator.py L62-79](file:///d:/filework/excel-to-diagram/meta/services/condition_evaluator.py#L62-L79) — 表达式语法
- [PermissionConfigPanel.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue) — 3 panel 实际 UI
- [RoleDetailDrawer.vue L160-186](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/RoleDetailDrawer.vue) — 独立 view, 同样 3 panel
