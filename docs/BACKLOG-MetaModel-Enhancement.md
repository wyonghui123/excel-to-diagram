# 元模型增强 Backlog

> **文档来源**: 会话重构分析 (chats/重构.md)
> **创建日期**: 2026-01-06
> **最后更新**: 2026-05-21
> **优先级标注**: ⭐ 高 | 🟡 中 | 🟢 低

---

## 零、实现状态总览（2026-05-21 更新）

### 已完整实现的能力

| 功能 | 实现文件 | 说明 |
|------|---------|------|
| **RuleEngine 规则引擎** | `meta/core/rule_executor.py` | 支持 Validation/Computation/StateTransition/Trigger/Derivation/Constraint |
| **RuleChain 规则链** | `meta/core/rule_chain.py` | 数据流驱动的规则链执行器 |
| **ConditionEvaluator** | `meta/core/condition_evaluator.py` | 安全的条件评估引擎（基于 AST） |
| **Deletability/Addability** | `meta/services/manage_service.py` | 动态 CRUD 控制，已集成到 ManageService |
| **StateTransition 状态转换** | `meta/core/rule_executor.py` | `MetaStateTransition` + `StateTransitionExecutor` 已完整实现 |
| **Lifecycle Events 生命周期事件** | `meta/core/action_executor.py` | `BEFORE/AFTER_CREATE/UPDATE/DELETE/SAVE` 全部触发时机已实现 |
| **TriggerExecutor 触发规则** | `meta/core/rule_executor.py` | `AFTER_SAVE` 事件处理器已实现 |
| **AuditLogger** | `meta/core/action_executor.py` | 审计日志自动记录 |
| **BusinessKeyService** | `meta/services/business_key_service.py` | ID → Business Key 转换 |
| **ObjectIdentityService** | `meta/services/object_identity_service.py` | 统一对象标识服务 |
| **Composition 关系** | `meta/core/models.py` | RelationType.COMPOSITION 已实现 |
| **BO 数据分类** | `meta/core/models.py` | `BusinessObjectCategory` + `BoSubCategory` + `BoCategoryConfig` |
| **托管枚举** | `meta/schemas/enum_type.yaml` | `enum_type` + `enum_value` + `EnumBindingStrength` + 多维枚举 |
| **Soft Delete 逻辑删除** | `meta/services/deletion_service.py` | `DeletionPolicy.soft_delete` + `DeletionService.soft_delete()` |
| **公式字段（计算规则）** | `meta/core/rule_executor.py` | `MetaComputation` + `ComputationService` 覆盖 Formula Fields 核心能力 |

### 部分实现的能力

| 功能 | 已实现 | 待实现 |
|------|--------|--------|
| **ActionBehavior** | 模型定义、YAML解析 | `ActionExecutor._execute_business()` 声明式执行引擎 |
| **Pseudo Variables** | `$now`, `$user`, `$uuid` 硬编码 | 配置驱动的 auto_fill 解析器 |
| **Soft Delete 应用** | 模型+服务已实现，`user.yaml` 有配置 | 所有业务对象均 `enabled: false`，无实际启用 |
| **Formula 增强** | `MetaComputation` + `ComputationService` | 跨对象引用语法、日期函数库、更多内置函数 |
| **状态模式定义** | `MetaStateTransition` 状态转换规则 | 状态模式定义（所有状态的可视化定义） |
| **字段变更检测** | 已计算 `changed_fields` | 暴露给规则上下文，支持 `on_field_change` 语法 |

### 待实现的能力（元数据完备性差距）

| 功能 | 来源 | 价值 | 优先级 |
|------|------|------|--------|
| **NumberRange 编号范围对象** | SAP NRIV | 企业级编号管理，审计合规 | P1 |
| **KeyTemplate 编号模板** | SAP | 灵活的业务编号规则 | P1 |
| **Business Key 双向查找** | SAP BOPF | 业务键反向查找，外部集成友好 | P1 |
| **Soft Delete 业务启用** | OutSystems/Dynamics | 关键业务对象启用逻辑删除 | P2 |
| **Formula 增强（跨对象+日期函数）** | Salesforce | 增强 MetaComputation 能力 | P2 |
| **Deep Insert/Update API** | SAP OData | 一次请求操作整个 BO | P2 |
| **Composition 权限继承** | SAP BO Node | 子对象继承父对象权限 | P2 |
| **多态 Composition 支持** | SAP BOPF | 多态关联 + 生命周期绑定（Annotation） | P2 |
| **Effective Dating 有效期** | Workday/Dynamics | 日期驱动的记录有效性 | P2 |
| **Entity Lifecycle Events** | OutSystems/BOPF | OnCreate/OnUpdate/OnDelete 原生实体事件 | P2 |

### 已覆盖的能力（无需单独实现）

| 功能 | 原计划 | 现状 | 说明 |
|------|--------|------|------|
| **BO Node 结构** | P1-9 | ✅ **已覆盖** | Composition 已实现级联删除、所有权语义、删除前检查 |
| **BO 级审计追溯** | P2 | ✅ **已实现** | `trace_id` + `parent_object_type/id` 已支持 |
| **Alternative Key** | P1-8 | 🟡 **部分实现** | BusinessKeyService 已支持 ID→Key，待增强 Key→ID 反向查找 |
| **Data Category 数据分类** | P1 新增 | ✅ **已实现** | `BusinessObjectCategory` + `BoSubCategory` + `BoCategoryConfig`，比 SAP CDS 更丰富 |
| **托管枚举 / Value Sets** | P1 新增 | ✅ **已实现** | `enum_type` + `enum_value` + `EnumBindingStrength`，多维枚举超越 SAP/Salesforce |
| **Soft Delete 逻辑删除** | P1 新增 | ✅ **模型已实现** | `DeletionPolicy.soft_delete` + `DeletionService.soft_delete()`，但业务对象均未启用 |
| **Formula Fields 公式字段** | P1 新增 | 🟡 **规则引擎可覆盖** | `MetaComputation` + `ComputationService` 覆盖核心能力，需增强跨对象引用和日期函数 |
| **State Transition 状态转换** | P2-11 | ✅ **已实现** | `MetaStateTransition` + `StateTransitionExecutor` 已完整实现 |
| **Entity Lifecycle Events** | P2-22 | ✅ **已实现** | `BEFORE/AFTER_CREATE/UPDATE/DELETE/SAVE` 全部触发时机已实现 |

### 元数据模型完备性对比

| 概念 | SAP BOPF | Salesforce | Dynamics | ServiceNow | Workday | 我们 | 状态 |
|------|----------|-----------|----------|-----------|---------|------|------|
| 对象定义 | BO | Object | Entity | CI Class | Business Object | `MetaObject` | ✅ |
| 字段定义 | Node Property | Field | Attribute | Column | Field | `MetaField` | ✅ |
| 组合关系 | Composition | Master-Detail | 1:N | Contains | - | `RelationType.COMPOSITION` | ✅ |
| 引用关系 | Association | Lookup | N:1 | Depends on | - | `RelationType.REFERENCE` | ✅ |
| 多态关联 | ✅ | - | - | ✅ | - | ✅ `polymorphic` | ✅ 已实现 |
| 多态 Composition | ✅ | - | - | - | - | ❌ | 📋 P2-16 |
| Root/Child Node | ✅ | - | - | ✅ | - | ✅ Composition 覆盖 | ✅ 已实现 |
| 级联删除 | ✅ | ✅ | ✅ | ✅ | - | `cascade_delete` | ✅ 已实现 |
| BO 级审计追溯 | ✅ | - | - | - | - | `trace_id` + `parent_object` | ✅ 已实现 |
| Business Key 显示 | ✅ | - | - | ✅ | - | `BusinessKeyService` | ✅ 已实现 |
| Business Key 查找 | ✅ | - | ✅ | ✅ | - | ❌ | 📋 P1-8 |
| 数据分类 | #MASTER/#TRANS | - | - | - | - | `BusinessObjectCategory` + `BoSubCategory` | ✅ 已实现 |
| 托管枚举 | Value Sets | Picklist | OptionSet | Choice | - | `enum_type` + `enum_value` | ✅ 已实现 |
| Soft Delete | ✅ | IsDeleted | statecode | active | - | `DeletionPolicy.soft_delete` | ✅ 模型已实现 |
| Soft Delete 业务启用 | ✅ | ✅ | ✅ | ✅ | - | ❌ 均为 `enabled: false` | 📋 P2-19 |
| 公式字段 | - | Formula | Calculated | - | ✅ | `MetaComputation` | 🟡 核心已覆盖 |
| Formula 增强 | - | ✅ | - | - | ✅ | ❌ 跨对象引用+日期函数 | 📋 P2-20 |
| NumberRange | ✅ | - | - | - | - | ❌ | 📋 P1-6 |
| Deep Insert API | ✅ | - | - | - | - | ❌ | 📋 P2-14 |
| 权限继承 | ✅ | - | - | - | - | ❌ | 📋 P2-15 |
| RecordType | - | ✅ | - | - | - | ❌ | 📋 P2-17 |
| Workflow | ✅ | Flow | BP | Flow | BP | ❌ | 📋 P2-18 |
| Effective Dating | - | - | ✅ | - | ✅ | ❌ | 📋 P2-21 |
| Lifecycle Events | ✅ | - | ✅ | ✅ | - | ✅ BEFORE/AFTER_CREATE/UPDATE/DELETE/SAVE | ✅ 已实现 |
| 状态转换规则 | ✅ | - | ✅ | ✅ | ✅ | `MetaStateTransition` | ✅ 已实现 |
| 状态模式定义 | ✅ | - | ✅ | - | - | ❌ 无可视化状态定义 | 📋 P2-23 |
| 字段变更检测 | ✅ Determination | - | ✅ | - | - | 🟡 已计算但未暴露 | 📋 P2-24 |

---

## 一、功能总览

### P1 - 重要能力（建议实现）

| # | 功能 | 来源 | 价值 | 复杂度 | 状态 |
|---|------|------|------|--------|------|
| 1 | Analytics 聚合注解 | SAP | SAP 报表分析支持 | 🟢 低 | 📋 待开发 |
| 2 | Pseudo Variables 声明式自动填充 | SAP | 运行时灵活配置 | 🟢 低 | 🟡 部分实现 |
| 3 | Deletability/Addability 动态 CRUD 控制 | SAP | 业务场景多 | 🟡 中 | ✅ **已实现** |
| 4 | Aspect 切面 | SAP + Palantir | 字段/约束复用 | 🟡 中 | 📋 待开发 |
| 5 | Action Type 声明式操作 | Palantir | 简化规则定义，可视化配置 | 🟡 中 | 🟡 **部分实现** |
| 6 | **NumberRange 编号范围对象** | SAP NRIV | 企业级编号管理，审计合规 | 🟡 中 | 📋 待开发 |
| 7 | **KeyTemplate 编号模板** | SAP | 灵活的业务编号规则 | 🟢 低 | 📋 待开发 |
| 8 | **Business Key 双向查找** | SAP BOPF | 业务键反向查找，外部集成友好 | 🟢 低 | 🟡 **部分实现** |
| 9 | ~~BO Node 结构~~ | SAP BOPF | ~~明确 BO 层级结构~~ | - | ✅ **Composition 已覆盖** |

### P2 - 增强能力（可选实现）

| # | 功能 | 来源 | 价值 | 复杂度 | 状态 |
|---|------|------|------|--------|------|
| 10 | Interface 属性模板 | Palantir | 属性模板复用（非多态查询） | 🟢 低 | 📋 待开发 |
| 11 | **State Transition 状态转换** | SAP | 状态机可视化 | 🟢 低 | ✅ **已实现** |
| 12 | Render Hints | Palantir | UI 自动化，需前端配合 | 🟢 低 | 📋 待开发 |
| 13 | View 分层 | SAP | 模型复用、按场景裁剪 | 🟡 中 | 📋 待开发 |
| 14 | **Deep Insert/Update API** | SAP | 一次请求操作整个 BO（订单+明细） | 🟡 中 | 📋 待开发 |
| 15 | **Composition 权限继承** | SAP BO Node | 子对象继承父对象权限 | 🟢 低 | 📋 待开发 |
| 16 | **多态 Composition 支持** | SAP BOPF | 多态关联 + 生命周期绑定（Annotation） | 🟡 中 | 📋 待开发 |
| 17 | **RecordType 记录类型** | Salesforce | 同对象不同业务形态 | 🟡 中 | 📋 待开发 |
| 18 | **Workflow 审批流程** | SAP + Salesforce | 多级审批、条件分支 | 🔴 高 | 📋 待开发 |
| 19 | **Soft Delete 业务启用** | OutSystems/Dynamics | 关键业务对象启用逻辑删除 | 🟢 低 | 📋 待开发 |
| 20 | **Formula 增强** | Salesforce | 跨对象引用语法、日期函数库 | 🟡 中 | 📋 待开发 |
| 21 | **Effective Dating 有效期** | Workday/Dynamics | 日期驱动的记录有效性 | 🟡 中 | 📋 待开发 |
| 22 | **Entity Lifecycle Events** | OutSystems/BOPF | `BEFORE/AFTER_CREATE/UPDATE/DELETE/SAVE` 触发时机 | 🟡 中 | ✅ **已实现** |
| 23 | **状态模式定义** | SAP BOPF | 定义所有状态、状态组、状态属性（可视化） | 🟡 中 | 📋 待开发 |
| 24 | **字段变更检测增强** | OutSystems | `changed_fields` 暴露给规则上下文 | 🟢 低 | 📋 待开发 |

### P3 - 低优先级（暂缓）

| # | 功能 | 来源 | 价值 | 备注 |
|---|------|------|------|------|
| 19 | Value Help 增强 | SAP | 声明式值帮助 | 已有基础实现 |
| 20 | Functions 复用 | Palantir | 业务逻辑复用 | 可通过 Rule Engine 替代 |
| 21 | Search Optimization | Palantir | 搜索优化 | 需要搜索引擎支持 |
| 22 | Interface 多态查询 | Palantir | 多态查询 | 业务系统场景少，关系数据库实现成本高 |

### Backlog（暂不实现）

| # | 功能 | 来源 | 价值 | 原因 |
|---|------|------|------|------|
| 23 | Draft 草稿 | SAP | 草稿功能 | 需要完整 BO 模型支持，复杂度高 |
| 24 | ETag 并发 | SAP | 乐观锁 | 需要所有表有 timestamp 字段 |
| 25 | Localized 多语言 | SAP | 国际化 | 需要翻译表设计，业务场景有限 |
| 26 | Temporal 时效性 | SAP | 有效期过滤 | 业务场景有限 |

---

## 二、详细功能说明

### P1-1: Analytics 聚合注解

**来源**: SAP `@Analytics.dataCategory` + `@DefaultAggregation`

**SAP 实现**:
```cds
entity SalesOrderItem {
    netValue : Decimal(15,2)
        @Analytics.aggregation: #SUM
        @Analytics.dataCategory: #Measure;

    product : Association to Product
        @Analytics.dataCategory: #Dimension;
}
```

**建议 YAML 扩展**:
```yaml
domains:
  - name: sales_order_item
    fields:
      - name: net_value
        type: decimal
        semantics:
          analytics:
            aggregation: sum  # SUM/MAX/MIN/AVG/COUNT
            category: measure  # measure/dimension
```

**价值**:
- 自动支持多维分析报表
- 减少手动聚合计算

---

### P1-2: Pseudo Variables 声明式自动填充

**来源**: SAP `@cds.on.insert` + `@cds.on.update`

**SAP 实现**:
```cds
entity Books : managed {
    createdAt : Timestamp @cds.on.insert: $now;
    createdBy : User      @cds.on.insert: $user;
    modifiedAt : Timestamp @cds.on.insert: $now @cds.on.update: $now;
    modifiedBy : User      @cds.on.insert: $user @cds.on.update: $user;
}
```

**当前实现**: 在 `ActionExecutor` 中硬编码处理

**建议 YAML 扩展**:
```yaml
fields:
  - id: created_at
    type: datetime
    semantics:
      auto_fill:
        on_create: $now
        on_update: $now
  - id: created_by
    type: string
    semantics:
      auto_fill:
        on_create: $user.id
  - id: order_no
    type: string
    semantics:
      auto_fill:
        on_create: $uuid
```

---

### P1-3: Deletability/Addability 动态 CRUD 控制 ✅ 已实现

**来源**: SAP `creatable-path` + `deletable-path`

**实现状态**: ✅ 完整实现 (2026-05-21 确认)

**已实现组件**:

| 组件 | 文件 | 说明 |
|------|------|------|
| `DeletabilityConfig` | `meta/core/models.py` | 删除条件配置模型 |
| `AddabilityConfig` | `meta/core/models.py` | 新增条件配置模型 |
| `check_can_delete()` | `meta/services/manage_service.py` | 删除前条件检查 |
| `batch_check_can_delete()` | `meta/services/manage_service.py` | 批量删除检查 |
| `check_can_add()` | `meta/services/manage_service.py` | 新增前条件检查 |
| `ConditionEvaluator` | `meta/core/condition_evaluator.py` | 条件表达式评估 |

**YAML 配置示例** (已支持):
```yaml
domains:
  - name: business_object
    deletability:
      condition: "self.relation_count == 0"
      message: "存在关联关系的业务对象不能删除"
    addability:
      condition: "parent.status in ['open', 'draft']"
      message: "父对象状态不允许新增"
```

**支持的运算符**:
- 比较: `==`, `!=`, `>`, `<`, `>=`, `<=`
- 逻辑: `and`, `or`, `not`
- 成员: `in`, `not in`
- 上下文: `self.field`, `parent.field`

**SAP 原始实现** (参考):
```cds
entity SalesOrderItem {
    status : String;
}

@OData.OperationAvailable: if ($entity/status eq 'draft');
action AcceptOrder();
```

---

### P1-4: Aspect 切面

**来源**: SAP + Palantir

**Palantir 实现**:
```typescript
// 定义 Interface 作为"属性模板"
interface Auditable {
    createdAt: timestamp;
    createdBy: string;
    updatedAt: timestamp;
    updatedBy: string;
}

// 多个 Object Type 实现同一 Interface
objectType Employee implements Auditable { ... }
objectType Company implements Auditable { ... }
```

**建议 YAML 扩展**:
```yaml
aspects:
  - name: auditable
    description: 审计字段模板
    fields:
      - name: created_at
        type: timestamp
        auto_fill: $now
      - name: created_by
        type: string
        auto_fill: $user.id
      - name: updated_at
        type: timestamp
        auto_fill: $now_on_update
      - name: updated_by
        type: string
        auto_fill: $user.id

domains:
  - name: sales_order
    aspects: [auditable]  # 引用切面
```

---

### P1-5: Action Type 声明式操作 🟡 部分实现

**来源**: Palantir

**实现状态**: 🟡 部分实现 (2026-05-21 确认)

**已实现组件**:

| 组件 | 文件 | 说明 |
|------|------|------|
| `ActionPrecondition` | `meta/core/models.py` | 前置条件模型 |
| `ActionEffect` | `meta/core/models.py` | 效果模型 (set_fields/trigger) |
| `ActionBehavior` | `meta/core/models.py` | 行为配置模型 |
| `MetaAction.behavior` | `meta/core/models.py` | Action 已集成 behavior 属性 |
| YAML 解析 | `meta/core/yaml_loader.py` | 已支持 behavior 块解析 |

**待实现**:

| 组件 | 文件 | 说明 |
|------|------|------|
| `_execute_business()` | `meta/core/action_executor.py` | 声明式执行引擎 |
| Action API 端点 | `meta/api/manage_api.py` | `POST /api/v1/<object_type>/actions/<action_id>` |

**已支持的 YAML 配置**:
```yaml
actions:
  - id: promote
    name: 晋升
    type: custom
    method: POST
    path: /api/v1/employees/{id}/actions/promote
    parameters:
      - id: new_role
        name: 新角色
        type: string
        required: true
    behavior:
      precondition:
        condition: "self.status == 'active'"
        message: "非活跃员工不能晋升"
      effects:
        - type: set_fields
          target: self
          fields:
            role: $parameters.new_role
            promoted_at: $now
            promoted_by: $user.name
        - type: trigger
          handler: notify_promotion
```

**Palantir 原始实现** (参考):
```yaml
Action: PromoteEmployee
Parameters:
  - employee: ObjectReference<Employee>
  - newRole: String

Rules:
  - ModifyObject:
      target: $employee
      properties:
        role: $newRole

Validation:
  - Condition: $employee.status == 'active'
  - Message: "Cannot promote inactive employee"
```

**价值**:
- 声明式定义，易于理解和维护
- 支持可视化配置

---

### P1-6: NumberRange 编号范围对象

**来源**: SAP `NRIV` 表 + `NUMBER_GET_NEXT` 函数

**SAP 实现**:
- 号码范围对象（Number Range Object）：定义编号的格式、长度、缓冲机制
- 号码区间（Number Range Interval）：起始值、结束值、当前编号
- 内部编号（Internal）：系统自动生成，严格连续
- 外部编号（External）：用户手动输入
- 缓冲机制（Buffering）：应用服务器缓存，提升性能但可能导致断号
- 年份相关（Year-Dependent）：按会计年度定义独立号码段

**建议 YAML 扩展**:
```yaml
number_ranges:
  - id: sales_order
    name: 销售订单编号
    intervals:
      - id: "01"
        from: "0000000001"
        to:   "9999999999"
        internal: true
      - id: "02"
        from: "A000000001"
        to:   "A999999999"
        external: true
    grouping:
      by_company: true
      by_year: true
    buffer: 10
    warning_threshold: 90

domains:
  - name: sales_order
    fields:
      - id: order_no
        type: string
        number_range: sales_order
        semantics:
          business_key: true
```

**影响文件**:
- 新增 `meta/core/number_range_service.py`
- 新增 `meta/core/models.py` NumberRangeConfig
- 改造 `meta/core/action_executor.py` 集成编号生成

**价值**:
- 企业级编号管理，满足审计合规要求
- 支持多维度分组（公司代码、年份等）
- 缓冲机制提升性能

---

### P1-7: KeyTemplate 编号模板

**来源**: SAP 编号规则

**建议 YAML 扩展**:
```yaml
key_templates:
  - id: sales_order_no
    pattern: "{prefix}-{year}-{sequence:05d}"
    components:
      prefix:
        type: constant
        value: "SO"
      year:
        type: date_part
        format: "%Y"
      sequence:
        type: number_range
        range_id: sales_order
        reset: yearly

domains:
  - name: sales_order
    fields:
      - id: order_no
        key_template: sales_order_no
```

**支持的模式组件**:
- `{prefix}` - 固定前缀
- `{year}`, `{month}`, `{day}` - 日期部分
- `{sequence}` - 流水号
- `{company_code}` - 公司代码
- `{object_type}` - 对象类型

**价值**:
- 灵活的业务编号规则
- 支持日期嵌入、流水号重置
- 可配置校验位

---

### P1-8: Business Key 双向查找 🟡 部分实现

**来源**: SAP BOPF Alternative Key

**现状分析**:

| 能力 | 状态 | 说明 |
|------|------|------|
| ID → Business Key 显示 | ✅ 已实现 | `BusinessKeyService.id_to_business_key()` |
| Business Key → ID 查找 | ❌ 待实现 | 反向查找功能 |
| API 业务键查询端点 | ❌ 待实现 | `GET /<object_type>/by_key?...` |
| 业务键唯一性约束 | ❌ 待实现 | 数据库层面约束 |

**已实现代码**:
```python
# meta/services/business_key_service.py
class BusinessKeyService:
    def id_to_business_key(self, object_type, object_id, format='full'):
        """将对象 ID 转换为业务键字符串（用于显示）"""
        # 查询 semantics.business_key 字段
        # 返回格式化字符串，如 "销售订单 → SO-001"
```

**待实现增强**:
```python
# 新增方法
def business_key_to_id(self, object_type: str, key_values: Dict[str, Any]) -> Optional[int]:
    """
    通过业务键查找对象 ID
    
    Args:
        object_type: 对象类型
        key_values: 业务键字段值，如 {"company_code": "1000", "order_no": "SO-001"}
    
    Returns:
        对象 ID，未找到返回 None
    """
```

**待实现 API 端点**:
```python
# meta/api/manage_api.py
@manage_api.route('/<object_type>/by_key', methods=['GET'])
def get_by_business_key(object_type):
    """
    通过业务键查找对象
    
    示例：GET /sales_orders/by_key?company_code=1000&order_no=SO-001
    """
```

**影响文件**:
- 改造 `meta/services/business_key_service.py` 增加反向查找方法
- 改造 `meta/api/manage_api.py` 增加业务键查询端点

**价值**:
- 外部系统集成友好（无需维护 UUID 映射表）
- 用户可读的 API
- 减少查询次数（一次请求直接定位）

---

### P1-9: ~~BO Node 结构~~ ✅ Composition 已覆盖

**来源**: SAP BOPF Business Object Node

**结论**: **无需单独实现**，我们的 Composition 关系已覆盖 BO Node 的核心能力。

**能力对比**:

| SAP BO Node 能力 | 我们的实现 | 状态 |
|-----------------|-----------|------|
| Root/Child 角色标记 | Composition 语义隐含 | ✅ 已覆盖 |
| 级联删除 | `cascade_delete: true` | ✅ 已实现 |
| 所有权语义 | `ownership: true` | ✅ 已实现 |
| 删除前检查 | `check_can_delete()` | ✅ 已实现 |
| 临时字段 | `FieldStorage.VIRTUAL` | ✅ 已实现 |
| BO 级审计追溯 | `trace_id` + `parent_object_type/id` | ✅ 已实现 |
| Access Node 查询优化 | - | 📋 可后期优化 |

**已实现代码**:
```python
# meta/core/models.py
class RelationType(Enum):
    COMPOSITION = "composition"  # ✅ 组合关系

class MetaRelation:
    relation_type: RelationType
    cascade_delete: bool = False  # ✅ 级联删除
    ownership: bool = False       # ✅ 所有权

# meta/services/manage_service.py
def check_can_delete(self, object_type, record):
    # ✅ 检查 composition 子对象
    for relation in meta_obj.relations:
        if relation.relation_type == RelationType.COMPOSITION:
            ...

# meta/services/audit_service.py - BO 级审计追溯
record = {
    'object_type': object_type,
    'object_id': str(object_id),
    'parent_object_type': parent_object_type,  # ✅ 父对象类型
    'parent_object_id': str(parent_object_id), # ✅ 父对象ID
    'trace_id': trace_id,                      # ✅ 同一请求共享
}
```

**待增强的便利性能力**（P2）:

| 能力 | 说明 | 对应 Backlog |
|------|------|-------------|
| **Composition 权限继承** | 子对象自动继承父对象权限 | P2-15 |
| **Deep Insert/Update API** | 一次请求创建整个 BO（订单+明细） | P2-14 |

**示例场景**：
```
订单 (sales_order)          ← Root（隐含）
├── 订单明细 (sales_order_item)  ← Child（Composition）
│   └── cascade_delete: true    ← 级联删除
│   └── trace_id 共享           ← 审计追溯
│
├── 权限继承（待实现）          ← P2-15
└── Deep Insert API（待实现）   ← P2-14
```

---

### P2-10: Interface 属性模板

**来源**: Palantir

**说明**: 定义一次，多处复用，与 Aspect 类似但更轻量

**建议 YAML 扩展**:
```yaml
shared_properties:
  - name: name
    type: string
    display_name: 名称
    constraints:
      max_length: 100
    render_hints:
      searchable: true
      sortable: true
      prominent: true
```

---

### P2-9: View 分层

**来源**: SAP CDS 三层架构

**SAP 实现**:
```
Layer 1: Interface View (接口视图) - 业务语义
Layer 2: Projection View (投影视图) - 技术实现
Layer 3: Metadata Extension - UI 配置
```

**建议 YAML 扩展**:
```yaml
domains:
  - name: sales_order
    views:
      - name: summary  # 消费视图
        fields: [id, customer_name, total_value, status]

      - name: detail
        fields: [*]  # 所有字段

      - name: analytics
        fields: [id, total_value, quantity]
        analytics:
          enabled: true
```

---

### P2-14: Deep Insert/Update API

**来源**: SAP OData Deep Insert

**说明**: 一次请求创建/更新整个 BO 树（订单 + 订单明细）

**当前问题**:
- 创建订单 + 订单明细需要多次 API 调用
- 无法保证原子性（部分成功/部分失败）

**建议 API 扩展**:
```json
POST /api/v1/sales-orders/deep
{
  "order": {
    "code": "SO001",
    "customer_id": 1,
    "items": [
      { "product_id": 101, "quantity": 10 },
      { "product_id": 102, "quantity": 5 }
    ]
  }
}
```

**影响文件**:
- 新增 `meta/services/deep_insert_service.py`
- 改造 `meta/api/manage_api.py` 增加 `/deep` 端点

**价值**:
- 减少网络往返
- 保证 BO 操作原子性
- 与 SAP OData 对齐

---

### P2-15: Composition 权限继承

**来源**: SAP BO Node 权限继承

**说明**: Composition 子对象自动继承父对象权限

**当前问题**:
```yaml
# 需要分别配置权限
permissions:
  - object_type: sales_order
    roles: [sales_manager, sales_rep]
  - object_type: sales_order_item  # 需要重复配置
    roles: [sales_manager, sales_rep]
```

**建议实现**:
```yaml
# 只需配置父对象权限
permissions:
  - object_type: sales_order
    roles: [sales_manager, sales_rep]
    inherit_to_composition: true  # 自动继承到子对象
```

**实现逻辑**:
```python
# data_permission_service.py
def check_permission(self, object_type, object_id, action, user):
    meta_obj = registry.get(object_type)
    
    # 检查是否是 Composition 子对象
    if self._is_composition_child(object_type):
        parent = self._get_composition_parent(object_type, object_id)
        # 使用父对象的权限
        return self.check_permission(parent.object_type, parent.object_id, action, user)
    
    # 正常权限检查
    return self._check_direct_permission(object_type, object_id, action, user)
```

**影响文件**:
- 改造 `meta/services/data_permission_service.py`
- 改造 `meta/core/models.py` 增加 `inherit_to_composition` 配置

**价值**:
- 简化权限配置
- 保证父子对象权限一致性
- 与 SAP BO Node 对齐

---

### P2-16: 多态 Composition 支持

**来源**: SAP BOPF Alternative Node + Polymorphic Association

**问题背景**:

Annotation（备注）是一种典型的多态 Composition 场景：
- 可以关联到任意对象类型（domain, sub_domain, service_module 等）
- 生命周期应该与目标对象绑定（目标删除，备注也删除）
- 但当前实现是**多态关联**，没有生命周期绑定

**当前设计问题**:
```yaml
# annotation.yaml - 当前配置
associations:
  - name: target
    target_type: polymorphic        # ✅ 多态关联已实现
    type: many_to_one
    polymorphic_type_field: target_type
    polymorphic_id_field: target_id
    # ❌ 没有 cascade_delete，目标删除后 annotation 成为孤儿数据
```

**关系类型对比**:

| 关系类型 | 多父支持 | 生命周期绑定 | 级联删除 | 适用场景 |
|---------|---------|------------|---------|---------|
| Composition | ❌ | ✅ | ✅ | 订单 → 订单明细 |
| Reference | ✅ | ❌ | ❌ | 订单明细 → 产品 |
| 多态关联 | ✅ | ❌ | ❌ | 任意对象 → 标签（可选） |
| **多态 Composition** | ✅ | ✅ | ✅ | 任意对象 → Annotation |

**建议实现**:

```yaml
# annotation.yaml - 增强配置
associations:
  - name: target
    target_type: polymorphic
    type: many_to_one
    polymorphic_type_field: target_type
    polymorphic_id_field: target_id
    cascade_delete: true           # 新增：反向级联删除
    ownership: true                # 新增：生命周期绑定
```

**实现逻辑**:
```python
# cascade_service.py 增强
def execute_reverse_cascade(self, parent_type: str, parent_id: int) -> List[Dict]:
    """
    执行反向级联删除（多态 Composition）
    
    当父对象删除时，查找所有通过多态关联绑定到它的子对象
    """
    deleted = []
    
    # 遍历所有配置了多态 Composition 的对象
    for child_meta in registry.get_all():
        for assoc in child_meta.associations:
            if getattr(assoc, 'target_type', None) == 'polymorphic' and \
               getattr(assoc, 'cascade_delete', False):
                
                type_field = assoc.polymorphic_type_field
                id_field = assoc.polymorphic_id_field
                
                # 查询匹配的子对象
                query = f"""
                    SELECT id FROM {child_meta.table_name}
                    WHERE {type_field} = ? AND {id_field} = ?
                """
                cursor = self.data_source.execute(query, [parent_type, parent_id])
                child_ids = [row[0] for row in cursor.fetchall()]
                
                if child_ids:
                    self._delete_children(child_meta.table_name, child_ids)
                    deleted.append({'object_type': child_meta.id, 'ids': child_ids})
    
    return deleted
```

**影响文件**:
- 改造 `meta/core/models.py` 增加 `cascade_delete` 支持 polymorphic 关联
- 改造 `meta/services/cascade_service.py` 增加 `execute_reverse_cascade()` 方法
- 改造 `meta/services/manage_service.py` 在删除时调用反向级联
- 更新 `meta/schemas/annotation.yaml` 配置

**价值**:
- 避免 Annotation 孤儿数据
- 保证数据一致性
- 与 SAP BOPF Alternative Node 对齐

**典型应用场景**:
- Annotation（备注）- 任意对象的备注
- Tag（标签）- 任意对象的标签（可选绑定）
- Attachment（附件）- 任意对象的附件
- Comment（评论）- 任意对象的评论

---

### P2-17: RecordType 记录类型

**来源**: Salesforce RecordType

**Salesforce 实现**:
- 同一对象的不同业务形态
- 每种 RecordType 可有不同的 PageLayout
- 支持按 Profile 分配不同的 RecordType

**建议 YAML 扩展**:
```yaml
domains:
  - name: opportunity
    record_types:
      - id: new_business
        name: 新业务
        description: 新客户销售机会
        default_layout: opportunity_new_business
      - id: renewal
        name: 续约
        description: 客户续约机会
        default_layout: opportunity_renewal
      - id: upsell
        name: 增购
        description: 客户增购机会
        default_layout: opportunity_upsell

    fields:
      - id: record_type_id
        type: string
        semantics:
          record_type: true
```

**影响文件**:
- 新增 `meta/core/models.py` RecordTypeConfig
- 改造 `meta/services/manage_service.py` 支持 RecordType 过滤
- 改造 `meta/api/manage_api.py` 支持 RecordType 参数

**价值**:
- 同对象不同业务形态
- 支持差异化 UI 布局
- 支持业务流程差异化

---

### P2-18: Workflow 审批流程

**来源**: SAP Workflow Builder + Salesforce Flow

**SAP Workflow 特性**:
- 可视化流程设计
- 多级审批、条件分支
- 事件触发（创建/修改/删除）
- 任务分配（角色/用户/规则）
- 超时处理（SLA 监控）
- 历史追溯（完整审计日志）

**建议 YAML 扩展**:
```yaml
workflows:
  - id: purchase_order_approval
    name: 采购订单审批
    trigger:
      on: create
      condition: "total_amount > 10000"
    
    steps:
      - id: manager_approval
        type: approval
        assign_to:
          role: manager
          or_field: requester.manager
        timeout:
          days: 3
          action: escalate
          escalate_to: director
      
      - id: finance_approval
        type: approval
        condition: "total_amount > 50000"
        assign_to:
          role: finance_director
        
      - id: auto_approve
        type: auto
        condition: "total_amount <= 10000"
        action: approve
    
    on_complete:
      action: update_status
      fields:
        status: "approved"
        approved_by: $workflow.approver
        approved_at: $now
```

**影响文件**:
- 新增 `meta/core/workflow_engine.py`
- 新增 `meta/core/models.py` WorkflowConfig, WorkflowStep
- 新增 `meta/services/workflow_service.py`
- 新增 `meta/api/workflow_api.py`

**价值**:
- 多级审批、条件分支
- 可视化流程编排
- 完整审计追溯

---

### P2-19: Soft Delete 业务启用

**来源**: OutSystems / Dynamics 365 / Salesforce

**现状分析**:

| 组件 | 状态 | 说明 |
|------|------|------|
| `DeletionPolicy.soft_delete` | ✅ 已实现 | 模型定义 |
| `DeletionService.soft_delete()` | ✅ 已实现 | 软删除执行 |
| `user.yaml` 配置 | ✅ 已有 | `soft_delete.enabled: false` |
| **业务对象实际启用** | ❌ 均为 `false` | 无任何对象启用软删除 |

**当前问题**:
- 所有业务对象的 `soft_delete.enabled` 均为 `false`
- 删除操作直接硬删除，无法恢复
- 不满足审计合规要求（关键业务数据应支持恢复）

**建议启用对象**（按 `BusinessObjectCategory` 分类）:

| 分类 | 对象 | 建议 | 理由 |
|------|------|------|------|
| TRANSACTIONAL | 订单、凭证 | ✅ 启用 | 事务数据不应硬删除 |
| MASTER_DATA | 客户、产品 | ✅ 启用 | 主数据变更需追溯 |
| CONFIGURATION | 枚举、参数 | ❌ 不启用 | 配置数据可硬删除 |
| ANALYTICAL | 报表、KPI | ❌ 不启用 | 分析数据可硬删除 |

**建议实现**:
```yaml
# user.yaml - 启用软删除
deletion_policy:
  soft_delete:
    enabled: true           # 改为 true
    field: deleted_at
    deleted_by_field: deleted_by
```

**影响文件**:
- 更新各 schema YAML 的 `deletion_policy.soft_delete.enabled`
- 改造 `meta/api/manage_api.py` 查询时自动过滤已删除记录

**价值**:
- 数据安全，防止误删
- 审计合规
- 与 BoCategoryConfig.default_soft_delete 对齐

---

### P2-20: Formula 增强（跨对象引用 + 日期函数）

**来源**: Salesforce Formula Fields

**现状分析**:

| Salesforce Formula 能力 | 我们的实现 | 状态 |
|------------------------|-----------|------|
| 简单公式 `price * qty` | ✅ `MetaComputation.formula` | 已实现 |
| 源字段变更自动重算 | ✅ `compute_on_change: True` | 已实现 |
| Roll-up Summary（子对象聚合） | ✅ `ComputationService.count_children/sum_field` | 已实现 |
| 跨对象引用 `Account.Name` | ❌ 需增强 | 待实现 |
| 日期函数 `TODAY()`, `ADD_MONTHS()` | ❌ 需增强 | 待实现 |
| 条件公式 `IF(cond, a, b)` | 🟡 `SafeExpressionEvaluator` 部分支持 | 部分实现 |

**建议增强**:

```yaml
# 跨对象引用
fields:
  - id: customer_name
    type: string
    storage: virtual
    computation:
      type: expression
      formula: "self.customer.name"           # 跨对象引用
      source_fields: [customer_id]

# 日期函数
fields:
  - id: deadline
    type: date
    computation:
      type: expression
      formula: "ADD_DAYS(self.created_at, 30)"  # 日期函数
```

**影响文件**:
- 改造 `meta/core/rule_executor.py` ComputationExecutor 增加跨对象引用解析
- 新增 `meta/core/formula_functions.py` 日期/字符串/数学函数库
- 改造 `meta/core/expression_evaluator.py` 增加函数调用支持

**价值**:
- 零代码的业务计算
- 与 Salesforce Formula Fields 对齐
- 增强 MetaComputation 的表达能力

---

### P2-21: Effective Dating 有效期

**来源**: Workday / Dynamics 365

**说明**: 日期驱动的记录有效性，支持历史数据追溯和未来变更预览

**Workday 实现**:
- 每条记录有 `effective_start_date` 和 `effective_end_date`
- 查询时指定"生效日期"，返回该日期有效的记录
- 支持未来变更（预设定生效日期）
- `is_current` 标记当前生效的记录

**Dynamics 实现**:
- `validfrom` / `validto` 字段
- 时间切片（Time State）查询

**建议 YAML 扩展**:
```yaml
domains:
  - name: employee_position
    effective_dating:
      enabled: true
      start_field: effective_from
      end_field: effective_to
      current_flag_field: is_current
      allow_future_changes: true       # 允许预设定未来变更
      overlap_strategy: latest         # 重叠时取最新

fields:
  - id: effective_from
    type: date
    semantics:
      auto_fill:
        on_create: $today
  - id: effective_to
    type: date
    default: "9999-12-31"
  - id: is_current
    type: boolean
    default: true
```

**查询示例**:
```python
# 查询指定日期有效的记录
GET /employee_positions?effective_date=2026-01-01

# 查询当前有效的记录
GET /employee_positions?effective_date=today
```

**影响文件**:
- 新增 `meta/core/models.py` EffectiveDatingConfig
- 新增 `meta/services/effective_dating_service.py`
- 改造 `meta/api/query_api.py` 增加 `effective_date` 参数

**价值**:
- 支持历史数据追溯
- 支持未来变更预览
- 满足 HR/财务等业务场景

---

### P2-22: Entity Lifecycle Events

**来源**: OutSystems / SAP BOPF Determination

**说明**: 实体生命周期的原生事件钩子

**OutSystems 实现**:
```csharp
// 实体级事件
OnCreate: 触发器
OnUpdate: 触发器
OnDelete: 触发器
```

**SAP BOPF Determination**:
```abap
determination CalcTotalAmount on modify { create; field item.net_value; }
```

**与现有能力对比**:

| 能力 | 现有实现 | Lifecycle Events | 差异 |
|------|---------|-----------------|------|
| 创建后触发 | `AFTER_SAVE` Trigger 规则 | `on_create` 事件 | 类似 |
| 更新后触发 | `AFTER_SAVE` Trigger 规则 | `on_update` 事件 | 类似 |
| 删除后触发 | `AFTER_DELETE` Trigger 规则 | `on_delete` 事件 | 类似 |
| 字段变更触发 | `compute_on_change` | `on_field_change` | **差异** |
| 条件触发 | Rule precondition | `condition` | 类似 |

**结论**: 🟡 现有 RuleEngine 的 Trigger 规则已覆盖大部分场景，Lifecycle Events 是更简洁的语法糖

**建议 YAML 扩展**:
```yaml
domains:
  - name: sales_order
    lifecycle_events:
      on_create:
        - action: send_notification
          parameters:
            template: order_created
      on_update:
        - action: recalculate_total
          condition: "changed_fields includes 'items'"
      on_field_change:
        field: status
          - action: update_timestamp
            parameters:
              field: status_changed_at
              value: $now
      on_delete:
        - action: archive_order
```

**影响文件**:
- 改造 `meta/core/action_executor.py` 增加生命周期事件分发
- 改造 `meta/core/yaml_loader.py` 解析 lifecycle_events 配置

**价值**:
- 更简洁的事件定义语法
- 字段级变更监听（`on_field_change`）
- 与 OutSystems/BOPF 对齐

**实际实现状态**: ✅ **已实现** (2026-05-21 确认)

| 触发时机 | 实现位置 | 说明 |
|---------|---------|------|
| `AFTER_CREATE` | `ActionExecutor._execute_create()` | ✅ 已实现 |
| `AFTER_UPDATE` | `ActionExecutor._execute_update()` | ✅ 已实现 |
| `AFTER_DELETE` | `ActionExecutor._execute_delete()` | ✅ 已实现 |
| `AFTER_SAVE` | `ActionExecutor` 创建/更新后 | ✅ 已实现 |

**注**: 字段级变更检测（`on_field_change`）需增强，参见 P2-24

---

### P2-23: 状态模式定义

**来源**: SAP BOPF State Schema / Dynamics Status Reason

**说明**: 定义所有可能的状态、状态组、状态属性，用于状态可视化和管理

**SAP BOPF 实现**:
```abap
// 状态模式定义
@ObjectModel.lifecycleType: #ACTIVE
entity SalesOrder {
    @ObjectModel.status: {
        schema: 'SALES_ORDER_STATUS',  // 状态模式
        derivator: 'CALC_STATUS'       // 状态衍生器
    }
    status: String;
}

// 状态模式
define enum SalesOrderStatus {
    DRAFT = 'draft';
    SUBMITTED = 'submitted';
    APPROVED = 'approved';
    REJECTED = 'rejected';
    COMPLETED = 'completed';
}

// 状态组
define status group SalesOrderStatusGroup {
    ACTIVE = {SUBMITTED, APPROVED};
    CLOSED = {COMPLETED, REJECTED};
}
```

**Dynamics 365 实现**:
```
Status Reason (状态原因):
- Active: New, In Progress, On Hold, Waiting, Researching
- Inactive: Cancelled, Closed, Merged

Status (状态):
- 0: Open
- 1: Completed
```

**我们现有的实现**:
```python
# MetaStateTransition - 状态转换规则
@dataclass
class MetaStateTransition(MetaRule):
    state_field: str = "status"
    from_states: List[str] = []
    to_state: str = ""
    allowed_roles: List[str] = []
    side_effects: List[StateTransitionSideEffect] = []
    ui_hints: Optional[StateTransitionUIHints] = None
```

**缺失的能力**:

| 能力 | SAP | Dynamics | 我们 | 说明 |
|------|-----|----------|------|------|
| **状态模式定义** | ✅ `enum SalesOrderStatus` | ✅ Status Reason | ❌ | 所有可能状态的定义 |
| **状态组** | ✅ `status group` | ✅ Active/Inactive | ❌ | 状态分组 |
| **状态属性** | ✅ `is_critical`, `is_final` | ✅ | ❌ | 状态元数据 |
| **状态可视化** | ✅ | ✅ | ❌ | 状态机的可视化展示 |

**建议 YAML 扩展**:
```yaml
domains:
  - name: sales_order
    state_machine:
      enabled: true
      state_field: status

    state_schema:
      statuses:
        - id: draft
          name: 草稿
          category: active          # active / inactive / final
          is_initial: true         # 初始状态
          ui:
            color: gray
            icon: edit
        - id: submitted
          name: 已提交
          category: active
          ui:
            color: blue
            icon: send
        - id: approved
          name: 已审批
          category: active
          ui:
            color: green
            icon: check
        - id: rejected
          name: 已拒绝
          category: inactive
          is_final: true
          ui:
            color: red
            icon: x
        - id: completed
          name: 已完成
          category: final
          is_final: true
          ui:
            color: gray
            icon: flag

    state_groups:
      - id: active
        name: 进行中
        statuses: [draft, submitted, approved]
      - id: closed
        name: 已结束
        statuses: [rejected, completed]

    transitions:
      - from: draft
        to: submitted
        allowed_roles: [sales_rep, manager]
      - from: submitted
        to: approved
        allowed_roles: [manager, director]
      - from: submitted
        to: rejected
        allowed_roles: [manager, director]
      - from: approved
        to: completed
        allowed_roles: [sales_rep]
```

**影响文件**:
- 新增 `meta/core/models.py` StateSchema, StateDefinition, StateGroup
- 改造 `meta/core/yaml_loader.py` 解析 state_schema 配置
- 改造 `meta/core/rule_executor.py` StateTransitionExecutor 使用状态模式验证
- 改造前端支持状态机可视化

**价值**:
- 状态可视化展示
- 状态转换规则自动验证（检查目标状态是否在 state_schema 中定义）
- 状态组支持（按状态组过滤）
- UI 状态颜色/图标配置

---

### P2-24: 字段变更检测增强

**来源**: OutSystems / SAP BOPF Determination

**说明**: 将 `changed_fields` 暴露给规则上下文，支持字段级变更监听

**OutSystems 实现**:
```csharp
OnUpdate: {
    if (changed(CustomerId)) {        // 字段变更检测
        RecalculateDiscount();
    }
}
```

**SAP BOPF Determination**:
```abap
determination CalcTotalAmount on modify {
    if (is_dirtiness_field('item.net_value')) {
        recalculate();
    }
}
```

**我们现有的实现**:
```python
# ActionExecutor._execute_update() 中已计算
changed_fields = {
    k: v for k, v in data.items()
    if original_data.get(k) != v
}
# 但未传递给规则上下文
```

**建议增强**:
```python
# RuleContext 增加 changed_fields 支持
class RuleContext:
    def __init__(self, data, original_data=None):
        self.data = data
        self.original_data = original_data or {}
        self._changed_fields = None
    
    @property
    def changed_fields(self) -> Dict[str, Any]:
        """返回变更的字段字典"""
        if self._changed_fields is None:
            self._changed_fields = {
                k: v for k, v in self.data.items()
                if self.original_data.get(k) != v
            }
        return self._changed_fields
    
    def has_changed(self, field_name: str) -> bool:
        """检查字段是否变更"""
        return field_name in self.changed_fields
```

**Trigger 规则 YAML 扩展**:
```yaml
rules:
  - id: on_status_change
    name: 状态变更触发
    type: trigger
    trigger: AFTER_UPDATE
    condition: "changed_fields includes 'status'"
    handler: send_status_notification
    
  - id: on_customer_change
    name: 客户变更触发
    type: trigger
    trigger: AFTER_UPDATE
    condition: "changed_fields includes 'customer_id'"
    handler: recalculate_discount
```

**Action Behavior YAML 扩展**:
```yaml
behavior:
  effects:
    - type: trigger
      handler: on_field_changed
      condition: "changed_fields includes 'items'"  # 订单明细变更时触发
```

**影响文件**:
- 改造 `meta/core/rule_context.py` 增加 `changed_fields` 属性
- 改造 `meta/core/action_executor.py` 将 `changed_fields` 传递给规则上下文
- 改造 `meta/core/yaml_loader.py` 解析 `changed_fields includes 'field'` 语法

**价值**:
- 字段级变更监听
- 精确触发条件
- 与 OutSystems/BOPF 对齐

---

## 三、P1 分阶段深度分析

### 3.1 现有基础设施盘点

在决定分阶段策略前，先梳理每个 P1 功能可复用的现有基础设施：

| P1 功能 | 已有基础设施 | 需要新建/改造 | 改造规模 |
|---------|-------------|-------------|---------|
| **P1-2 Pseudo Variables** | `ActionExecutor._prepare_data()` 硬编码 `datetime.now()`；`AuditLogger.set_user()` 已有用户上下文；`SemanticAnnotation.context_field` 已有上下文字段概念 | `_prepare_data()` 改为读取 YAML `auto_fill` 配置；新增伪变量解析器 | 🟢 小 |
| **P1-1 Analytics** | `ComputationService` 已有 `count_relations`；`DerivationExecutor._execute_aggregation()` 已支持 SUM/COUNT/AVG/MAX/MIN；`AggregateType` 枚举已存在；UI 列表列已支持 `computed: true` + `computation` 块 | `ComputationService` 扩展聚合计算类型；API 层新增聚合查询端点 | 🟢 小 |
| **P1-4 Aspect** | `shared_properties.yaml` 已有字段模板；`yaml_loader._resolve_includes()` 已实现字段合并；`MetaObject.includes` 字段已存在；`MetaField.included_from` 已追踪来源 | 升级 `includes` 为完整 Aspect（支持 semantics/validations/rules 合并）；新增 `aspects` 顶级定义 | 🟡 中 |
| **P1-3 Deletability** | `CascadeService` 已检查级联删除条件；`HierarchyValidationService.validate_delete_allowed()` 已存在；`PermissionAnnotation.writable` 已有字段级写入控制 | 新增 `deletability`/`addability` YAML 配置块；运行时条件评估；API 响应返回 `can_delete`/`can_add` | 🟡 中 |
| **P1-5 Action Type** | `MetaAction` 已定义操作结构；`RuleEngine` 已支持 validation/computation/trigger；`ActionParameter` 已有参数定义；`ActionExecutor._execute_business()` 返回"未实现" | 新增 `behavior` YAML 块（precondition/effect/set_fields）；实现声明式执行引擎；新增自定义 action API 端点 | 🟡 中偏大 |

### 3.2 功能依赖关系图

```
                    ┌─────────────┐
                    │  P1-4 Aspect │ ← 结构基础
                    │  (切面复用)   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
     ┌────────────┐ ┌────────────┐ ┌────────────┐
     │ P1-2 Pseudo │ │ P1-1 Analytics│ │ P1-3 Delete │
     │  Variables  │ │  (聚合注解)   │ │  /Addability │
     │ (自动填充)  │ │             │ │ (CRUD控制)  │
     └─────┬──────┘ └─────────────┘ └──────┬──────┘
           │                                │
           │    ┌───────────────────┐       │
           └───►│  P1-5 Action Type │◄──────┘
                │  (声明式操作)      │
                └───────────────────┘
```

**关键依赖分析**：

1. **P1-4 Aspect → P1-2 Pseudo Variables**：Aspect 是 Pseudo Variables 的最佳载体。`audit_aspect` 可以打包 `created_at`/`updated_at`/`created_by`/`updated_by` 四个字段及其 `auto_fill` 配置，一次引用即可获得完整的审计能力。如果不做 Aspect，Pseudo Variables 只能逐字段配置。

2. **P1-4 Aspect → P1-1 Analytics**：`analytics_aspect` 可以打包聚合维度字段（如 `analytics.aggregation` + `analytics.category`），让多个对象共享分析配置。

3. **P1-4 Aspect → P1-3 Deletability**：`controllable_aspect` 可以打包 `can_delete`/`can_add` 虚拟字段及其计算规则，让多个对象共享行为控制逻辑。

4. **P1-2 + P1-3 → P1-5 Action Type**：Action Type 的 `set_fields` 需要 Pseudo Variables（如 `$now`、`$user`），`precondition` 需要 Deletability 的条件评估能力。

### 3.3 相关性聚类

按功能内在相关性，5 个 P1 功能自然聚为三类：

| 聚类 | 功能 | 相关性说明 |
|------|------|-----------|
| **A: 字段语义增强** | P1-2 Pseudo Variables + P1-1 Analytics | 都在 `fields[].semantics` 层面扩展；都涉及运行时计算/自动填充；都是"字段级"能力 |
| **B: 结构复用** | P1-4 Aspect | 为 A、C 类功能提供打包和复用机制；是其他功能的结构基础 |
| **C: 行为控制** | P1-3 Deletability + P1-5 Action Type | 都控制"什么操作可以执行"；都需要运行时条件评估；P1-5 是 P1-3 的超集 |

### 3.4 分阶段方案（推荐）

基于相关性和规模，推荐将 P1 分为 **3 个子阶段**：

---

#### **P1-Phase A: 结构基础 + 快速交付**（Aspect + Pseudo Variables）

| 功能 | 规模 | 理由 |
|------|------|------|
| P1-4 Aspect 切面 | 🟡 中 | **先做结构基础**，升级 `includes` → `aspects`，为后续功能提供打包机制 |
| P1-2 Pseudo Variables | 🟢 小 | **Aspect 的杀手级用例**：`audit_aspect` 打包 4 个审计字段 + auto_fill，立竿见影 |

**实施路径**：
```
Step 1: 升级 shared_properties.yaml → aspects 定义
        - aspects 支持字段 + semantics + validations + rules
        - 对象通过 aspects: [audit_aspect] 引用
        - _resolve_includes() 升级为 _resolve_aspects()，支持冲突合并策略

Step 2: 实现 auto_fill 伪变量解析
        - SemanticAnnotation 新增 auto_fill: {on_create, on_update} 属性
        - ActionExecutor._prepare_data() 从硬编码改为读取 auto_fill 配置
        - 内置伪变量: $now, $user.id, $user.name, $uuid

Step 3: 定义标准 Aspect 库
        - audit_aspect: created_at($now), updated_at($now), created_by($user.id), updated_by($user.id)
        - hierarchy_aspect: version_id, version_name, product_code
        - naming_aspect: code, name
        - owner_aspect: owner_id
```

**YAML 示例**：
```yaml
aspects:
  audit_aspect:
    description: 审计字段切面
    fields:
      - id: created_at
        type: datetime
        semantics:
          auto_fill:
            on_create: $now
      - id: updated_at
        type: datetime
        semantics:
          auto_fill:
            on_create: $now
            on_update: $now
      - id: created_by
        type: string
        semantics:
          auto_fill:
            on_create: $user.name
      - id: updated_by
        type: string
        semantics:
          auto_fill:
            on_create: $user.name
            on_update: $user.name

# 对象引用
domains:
  - name: sales_order
    aspects: [audit_aspect, naming_aspect]
    fields:
      - id: total_value
        type: decimal
        # ... 自有字段
```

**影响文件**：
- `meta/core/models.py`: SemanticAnnotation 新增 auto_fill 属性
- `meta/core/yaml_loader.py`: _resolve_includes() → _resolve_aspects()
- `meta/core/action_executor.py`: _prepare_data() 改为配置驱动
- `meta/schemas/shared_properties.yaml` → `meta/schemas/aspects.yaml`
- 所有 schema YAML: `includes: [...]` → `aspects: [...]`

---

#### **P1-Phase B: 分析能力**（Analytics 聚合注解）

| 功能 | 规模 | 理由 |
|------|------|------|
| P1-1 Analytics 聚合注解 | 🟢 小 | 独立性强，可利用 Phase A 的 Aspect 打包分析字段 |

**实施路径**：
```
Step 1: YAML Schema 扩展
        - fields[].semantics 新增 analytics: {aggregation, category, measure_group}
        - 定义 analytics_aspect（聚合维度字段模板）

Step 2: ComputationService 扩展
        - 新增聚合计算类型: sum_relations, avg_field, max_field, min_field
        - 复用 DerivationExecutor._execute_aggregation() 的聚合逻辑

Step 3: API 层新增聚合查询端点
        - GET /api/v1/query/aggregate?object_type=xxx&group_by=xxx&measures=xxx
        - 支持按 analytics.category=dimension 的字段分组
        - 支持按 analytics.aggregation 的字段聚合
```

**YAML 示例**：
```yaml
fields:
  - id: relation_count
    type: integer
    storage: virtual
    semantics:
      analytics:
        aggregation: count
        category: measure
        measure_group: relationship
    computation:
      type: count_relations
      scope: self

  - id: domain_name
    type: string
    storage: virtual
    semantics:
      analytics:
        category: dimension
        dimension_group: organization
```

**影响文件**：
- `meta/core/models.py`: SemanticAnnotation 新增 analytics 属性
- `meta/services/computation_service.py`: 扩展聚合计算类型
- `meta/api/query_api.py`: 新增聚合查询端点
- `meta/core/yaml_loader.py`: 解析 analytics 配置

---

#### **P1-Phase C: 行为控制**（Deletability + Action Type）✅ 部分完成

| 功能 | 规模 | 状态 | 说明 |
|------|------|------|------|
| P1-3 Deletability/Addability | 🟡 中 | ✅ **已完成** | ManageService 已集成条件检查 |
| P1-5 Action Type 声明式操作 | 🟡 中偏大 | 🟡 **部分完成** | 模型已定义，执行引擎待实现 |

**实施路径**：
```
Step 1: Deletability/Addability ✅ 已完成
        - YAML 新增 deletability/addability 配置块 ✅
        - ManageService.create()/delete() 增加动态条件检查 ✅
        - API 响应返回 can_delete/can_add 标志 ✅
        - ConditionEvaluator 条件评估引擎 ✅

Step 2: Action Type 声明式操作 🟡 进行中
        - YAML 新增 behavior 块 ✅
        - 扩展 MetaAction 支持 precondition/effect/set_fields ✅
        - 实现 ActionExecutor._execute_business() 声明式执行 ⏳ 待实现
        - 新增 POST /api/v1/<object_type>/actions/<action_id> 端点 ⏳ 待实现
```

**YAML 示例（Deletability）**：
```yaml
deletability:
  condition: "status != 'released' and child_count == 0"
  message: "已发布或有子对象的数据不能删除"

addability:
  condition: "parent.status in ['open', 'draft']"
  message: "父对象状态不允许新增"
```

**YAML 示例（Action Type）**：
```yaml
actions:
  - id: promote
    name: 晋升
    type: custom
    method: POST
    path: /api/v1/employees/{id}/actions/promote
    parameters:
      - id: new_role
        name: 新角色
        type: string
        required: true
    behavior:
      precondition:
        condition: "status == 'active'"
        message: "非活跃员工不能晋升"
      effects:
        - type: set_fields
          target: self
          fields:
            role: $parameters.new_role
            promoted_at: $now
            promoted_by: $user.name
        - type: trigger
          handler: notify_promotion
```

**影响文件**：
- `meta/core/models.py`: MetaAction 扩展 behavior 属性；MetaObject 新增 deletability/addability
- `meta/core/action_executor.py`: _execute_business() 实现声明式执行
- `meta/services/manage_service.py`: create()/delete() 增加动态条件检查
- `meta/api/manage_api.py`: 新增 action 端点；响应返回 can_delete/can_add
- `meta/core/yaml_loader.py`: 解析 deletability/addability/behavior 配置

---

### 3.5 分阶段总览

```
P1-Phase A (结构基础 + 快速交付) ─────────────────────────────
│
├─ P1-4 Aspect 切面 (升级 includes → aspects)
│   └─ 改造: yaml_loader, models, schemas
│
└─ P1-2 Pseudo Variables (硬编码 → 配置驱动)
    └─ 改造: action_executor, models
    └─ 新增: auto_fill 解析器, 标准 Aspect 库

P1-Phase B (分析能力) ───────────────────────────────────────
│
└─ P1-1 Analytics 聚合注解
    └─ 扩展: computation_service, query_api
    └─ 新增: analytics 语义, 聚合查询端点

P1-Phase C (行为控制) ─────────────────────────────────────── ✅ 部分完成
│
├─ P1-3 Deletability/Addability ✅ 已完成
│   └─ 改造: manage_service, manage_api ✅
│   └─ 新增: 条件评估, can_delete/can_add 标志 ✅
│
└─ P1-5 Action Type 声明式操作 🟡 进行中
    └─ 改造: action_executor, manage_api
    └─ 新增: behavior 执行引擎, 自定义 action 端点
```

### 3.6 分阶段决策依据

| 维度 | Phase A 优先 | Phase B 居中 | Phase C 最后 |
|------|-------------|-------------|-------------|
| **相关性** | Aspect 是其他功能的基础设施；Pseudo Variables 是 Aspect 的最佳验证 | Analytics 相对独立，不依赖其他 P1 功能 | Deletability 和 Action Type 互为依赖，且依赖 Phase A 的 auto_fill |
| **规模** | 中+小，风险可控 | 小，可快速交付 | 中+中偏大，复杂度最高 |
| **价值** | 消除硬编码（技术债）+ 建立复用机制（架构提升） | 增强分析能力（业务价值） | 动态行为控制（业务灵活性） |
| **风险** | 低：升级现有 includes 机制，向后兼容 | 低：扩展现有 ComputationService | 中：需要新的条件评估和执行引擎 |
| **验证** | audit_aspect 立即可用，所有对象受益 | 聚合查询 API 立即可用 | 自定义 action 需要业务场景验证 |

---

## 四、实现路线图（更新）

```
Phase A (P1-A) ──────────────────────────────────────────────────
│
├─ Aspect 切面
│   └─ 升级 includes → aspects（字段+语义+规则合并）
│
└─ Pseudo Variables
    └─ auto_fill: $now/$user/$uuid（配置驱动替代硬编码）

Phase B (P1-B) ──────────────────────────────────────────────────
│
└─ Analytics 聚合注解
    └─ analytics.aggregation + category + 聚合查询 API

Phase C (P1-C) ──────────────────────────────────────────────────
│
├─ Deletability/Addability
│   └─ deletability.condition + addability.condition
│
└─ Action Type 声明式操作
    └─ behavior: precondition + effects + set_fields

Phase D (P2) ────────────────────────────────────────────────────
│
├─ Interface 属性模板
│   └─ YAML: shared_properties
│
├─ View 分层
│   └─ YAML: views 配置
│
├─ Deep Insert/Update API
│   └─ 扩展 API 接收嵌套 JSON
│
├─ State Transition 注解 ✅ 已实现
│   └─ StateTransitionExecutor 已在 Rule Engine 中实现
│
└─ Render Hints
    └─ 前端配合

Phase E (P3 + Backlog) ──────────────────────────────────────────
│
├─ Value Help 增强
├─ Functions 复用
├─ Search Optimization
├─ Draft 草稿
├─ ETag 并发
├─ Localized 多语言
└─ Temporal 时效性
```

---

## 五、P3 详细说明

### P3-11: Value Help 增强

**来源**: SAP `@Consumption.valueHelpDefinition`

**当前状态**: ✅ 已实现 `value_help.validation` 输入验证

**已实现功能**:
```yaml
fields:
  - id: domain_id
    ui:
      widget: select
      relation: domain
      display_field: name
      value_help:
        validation: true                    # 输入验证
        validation_message: "请选择有效的领域"
        distinct: true                      # 去重
        label: "选择领域"                   # 弹窗标题
```

**待实现功能**:
- `enabled_condition`: 动态启用条件
- 前端弹窗 UI 增强

---

### P3-12: Functions 复用

**来源**: Palantir Functions

**当前状态**: ⚠️ Rule Engine 已覆盖核心需求，暂不需要独立实现

**Palantir Functions 特性**:
```typescript
@Function()
public airportLocation(airport: Airport): string {
    return `${airport.city}, ${airport.country}`;
}
```

**我们的替代方案**:

| Palantir Functions | 我们的实现 | 状态 |
|-------------------|-----------|------|
| 基于对象的计算 | Computation Rule | ✅ 已支持 |
| 跨对象引用 | Derivation Rule | ✅ 已支持 |
| 纯计算无副作用 | MetaFunction 设计 | ✅ 已支持 |
| 可被其他规则引用 | Rule Engine 链式调用 | ✅ 已支持 |

**可选增强（低优先级）**:

1. **添加 `functions:` 配置块到 schemas**
2. **支持函数库（跨 schema 复用）**

```yaml
# functions.yaml - 函数库
functions:
  - id: format_currency
    name: 格式化货币
    expression: "currency_symbol + ' ' + round(value, 2)"
    parameters:
      - name: value
        type: float
      - name: currency_symbol
        type: string
        default: "$"

# 在 schema 中引用
rules:
  - id: compute_price_display
    type: computation
    target_field: price_display
    function_ref: format_currency
    parameters:
      value: price
      currency_symbol: currency
```

**建模待办**:
- [ ] 添加 `functions:` 配置块到 MetaObject
- [ ] 实现函数库加载和引用机制
- [ ] 支持 `function_ref` 在规则中引用函数

---

### P3-13: Search Optimization

**来源**: Palantir Search Optimization

**当前状态**: ⚠️ 基础搜索已实现，优化项待开发

**已实现功能**:

| 功能 | 实现位置 | 状态 |
|------|----------|------|
| 基础搜索 | `query_service.search()` | ✅ |
| 全文搜索 | `query_service.full_text_search()` | ✅ |
| 关键词搜索 | `ILIKE %keyword%` | ✅ |
| 搜索建议 | `query_service.suggest()` | ✅ |
| 层级路径搜索 | `query_service.query_by_hierarchy_path()` | ✅ |
| searchable 属性 | `RenderHints.searchable` | ✅ |

**待实现功能**:

| 优先级 | 功能 | 成本 | 说明 |
|--------|------|------|------|
| P3 | search_property 合并字段 | 低 | 提升搜索便利性 |
| P3 | 字段权重排序 | 低 | 提升搜索结果质量 |
| P3 | 搜索高亮 | 低 | 前端展示优化 |
| Backlog | 语义搜索 | 高 | 需要向量数据库 |

**search_property 配置示例**:

```yaml
# 在 schema 中定义搜索属性
search_config:
  search_property: true           # 自动生成合并字段
  search_fields: [name, code, description]  # 参与搜索的字段
  weight:                         # 字段权重
    name: 10
    code: 8
    description: 3
```

**字段权重排序实现**:

```python
def calculate_relevance(record, keyword, weights):
    score = 0
    for field, weight in weights.items():
        if keyword.lower() in str(record.get(field, "")).lower():
            score += weight
    return score
```

**建模待办**:
- [ ] 添加 `search_config:` 配置块到 MetaObject
- [ ] 实现 search_property 虚拟字段自动生成
- [ ] 实现字段权重相关性排序
- [ ] 前端搜索结果高亮显示

---

### P3-14: Interface 多态查询

**来源**: Palantir Interface Polymorphism

**当前状态**: ⚠️ 业务场景少，关系数据库实现成本高

**Palantir Interface 特性**:

```typescript
// 定义 Interface
interface NamedEntity {
  name: string;
  code: string;
}

// 多个 Object Type 实现同一 Interface
objectType Product implements NamedEntity { ... }
objectType Domain implements NamedEntity { ... }
objectType BusinessObject implements NamedEntity { ... }

// 多态查询 - 跨对象类型查询
query NamedEntitySearch(keyword: string) {
  return objects(NamedEntity)
    .filter(obj => obj.name.contains(keyword))
    .limit(100);
}
```

**关系数据库实现挑战**:

| 挑战 | 说明 |
|------|------|
| 联合查询 | 需要 UNION ALL 多个表 |
| 类型识别 | 需要额外的 `_object_type` 字段 |
| 性能 | 大表联合查询性能差 |
| 索引 | 无法跨表建立索引 |

**我们的替代方案**:

| 需求 | 当前实现 | 状态 |
|------|----------|------|
| 属性模板复用 | Aspect 切面 | ✅ 已支持 |
| 共享字段定义 | `aspects: [naming_aspect]` | ✅ 已支持 |
| 跨对象搜索 | `full_text_search()` | ✅ 已支持 |
| 多态查询 | - | ❌ 暂不需要 |

**可选实现（低优先级）**:

```yaml
# 定义 Interface
interfaces:
  - id: named_entity
    name: 命名实体
    properties:
      - id: name
        type: string
      - id: code
        type: string

# Object Type 实现 Interface
object_types:
  - id: product
    implements: [named_entity]
    fields:
      - id: name
        type: string
      - id: code
        type: string
      # ... 其他字段
```

**建模待办**:
- [ ] 添加 `interfaces:` 配置块定义
- [ ] 添加 `implements:` 属性到 MetaObject
- [ ] 实现跨对象类型查询 API
- [ ] 评估业务场景必要性

**决策建议**: 当前业务系统场景少，建议暂缓实现。如有多态查询需求，可使用 `full_text_search()` 替代。

---

## 六、统计

| 优先级 | 总数 | 子阶段 | 说明 |
|--------|------|--------|------|
| P1 | 5 | Phase A: 2, Phase B: 1, Phase C: 2 | 重要能力，分3阶段实施 |
| P2 | 15 | - | 增强能力，可选实现 |
| P3 | 4 | - | 低优先级，暂缓 |
| Backlog | 4 | - | 暂不实现 |
| **总计** | **28** | | |

---

## 七、关联文档

| 文档 | 说明 |
|------|------|
| [CONSOLIDATED-BACKLOG](CONSOLIDATED-BACKLOG.md) | 项目完整功能规划 |
| [BACKLOG-P0-2](BACKLOG-P0-2-MetaModel-Improvement.md) | P0-2 元模型改进计划 |
| [需求Backlog](requirements-backlog.md) | 原始需求清单 |
| [chats/重构.md](..%2Fchats%2F重构.md) | 会话分析原始记录 |

---

## 八、更新记录

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-05-21 | 2.7 | 深入分析状态管理和生命周期事件，确认 State Transition 和 Lifecycle Events 已完整实现；新增 P2-23 状态模式定义、P2-24 字段变更检测增强 | AI助手 |
| 2026-05-21 | 2.6 | 深入分析头部产品（SAP/Salesforce/Dynamics/ServiceNow/Workday/OutSystems），新增 P2-19~P2-22；确认数据分类/托管枚举/Soft Delete 模型/Formula 已实现 | AI助手 |
| 2026-05-01 | 2.3 | 添加 P3-14 Interface 多态查询详细说明和建模待办 | AI助手 |
| 2026-05-01 | 2.2 | 添加 P3-13 Search Optimization 详细说明和建模待办 | AI助手 |
| 2026-05-01 | 2.1 | 添加 P3 详细说明：Value Help 增强、Functions 复用建模待办 | AI助手 |
| 2026-04-30 | 2.0 | P1 分阶段深度分析：基础设施盘点、依赖关系图、相关性聚类、3阶段实施方案 | AI助手 |
| 2026-01-06 | 1.0 | 初始版本，整合会话分析结果 | AI助手 |
