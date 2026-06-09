## 目录

1. [1. 三大产品状态模型概览](#1-三大产品状态模型概览)
2. [2. 详细对比矩阵](#2-详细对比矩阵)
3. [3. 关键差距深度分析](#3-关键差距深度分析)
4. [4. 完整状态模型建议](#4-完整状态模型建议)
5. [5. 实施优先级建议](#5-实施优先级建议)
6. [6. 总结](#6-总结)

---
# 状态与状态机模型深度对比分析

> **创建日期**: 2026-05-22
> **目的**: 深入对比 SAP BOPF、Salesforce、Dynamics 365 的状态管理模型，识别差距

---

## 1. 三大产品状态模型概览

### 1.1 SAP BOPF Status Management

SAP BOPF 的状态管理由三个核心实体组成：

| 实体 | 说明 |
|------|------|
| **Status Schema** | 状态模式定义，定义所有可能的状态 |
| **Status Derivator** | 状态派生器，根据业务规则自动计算状态 |
| **Status Variable** | 状态变量，存储对象实例的当前状态 |

**核心特性**：
- 状态派生器（Derivator）可基于 Determination 自动计算状态
- 支持状态依赖链（状态 A 变化触发状态 B 重新计算）
- 状态与 Action/Validation 绑定（特定状态才能执行特定 Action）

### 1.2 Salesforce Opportunity Stages / BusinessProcess

Salesforce 的状态管理体现在两个层面：

| 层面 | 说明 |
|------|------|
| **Picklist (Stage)** | 简单枚举状态，如 Opportunity Stage |
| **BusinessProcess** | 业务流程定义，关联 RecordType 和 Stage |

**Opportunity Stage 核心属性**：

| 属性 | 说明 |
|------|------|
| **Stage Name** | 阶段名称（如 Prospecting, Negotiation） |
| **Type** | 阶段类型：Open / Closed Won / Closed Lost |
| **Probability** | 成交概率百分比（用于预测） |
| **Forecast Category** | 预测分类：Pipeline / Best Case / Commit / Closed / Omitted |
| **Description** | 阶段描述 |

**BusinessProcess 核心特性**：
- 与 RecordType 绑定（不同 RecordType 可有不同流程）
- 阶段顺序强制（可配置是否允许跳过阶段）
- 每个阶段可关联字段集（该阶段需要填写的字段）

### 1.3 Dynamics 365 Status / StatusReason

Dynamics 365 采用双层状态模型：

| 字段 | 说明 |
|------|------|
| **Status (statecode)** | 状态（系统级，不可扩展）：Active / Inactive / Resolved / Canceled |
| **Status Reason (statuscode)** | 状态原因（业务级，可扩展）：每个 Status 下可有多个 Reason |

**Case 实体默认状态模型**：

| Status | Status Reason |
|--------|---------------|
| **Active** | In Progress, On Hold, Waiting for Details, Researching |
| **Resolved** | Problem Solved, Information Provided |
| **Canceled** | Canceled, Merged |

**Status Reason Transitions**：
- 可定义每个 Status Reason 允许转换到哪些其他 Status Reason
- 强制阶段顺序（如 In Progress → On Hold → Waiting for Details → Researching → Resolved）

---

## 2. 详细对比矩阵

### 2.1 状态定义能力

| 能力 | SAP BOPF | Salesforce | D365 | 我们 |
|------|----------|-----------|------|------|
| 状态枚举定义 | ✅ Status Schema | ✅ Picklist | ✅ Status Reason | ✅ enum_values |
| 状态分类 | ✅ Category | ✅ Type (Open/Closed) | ✅ Status | ⚠️ 需扩展 |
| 初始状态 | ✅ is_initial | ⚠️ 默认第一个 | ✅ 默认值 | ⚠️ 需扩展 |
| 终态标识 | ✅ is_final | ✅ Closed Won/Lost | ✅ Resolved/Canceled | ⚠️ 需扩展 |
| 状态概率 | ❌ | ✅ Probability | ❌ | ❌ |
| 预测分类 | ❌ | ✅ Forecast Category | ❌ | ❌ |
| 状态图标 | ✅ | ✅ | ✅ | ⚠️ 需扩展 |
| 状态颜色 | ✅ | ✅ | ✅ | ✅ |
| 状态描述 | ✅ | ✅ | ✅ | ⚠️ 需扩展 |

### 2.2 状态转换能力

| 能力 | SAP BOPF | Salesforce | D365 | 我们 |
|------|----------|-----------|------|------|
| 转换规则定义 | ✅ Action | ✅ Validation Rule | ✅ Transitions | ✅ MetaStateTransition |
| 转换前置条件 | ✅ | ✅ | ✅ | ✅ |
| 转换后副作用 | ✅ Side Effects | ✅ Workflow | ✅ | ✅ |
| 强制顺序转换 | ✅ | ⚠️ 需配置 | ✅ Transitions | ⚠️ 需扩展 |
| 跳过阶段检测 | ❌ | ✅ Validation Rule | ✅ | ❌ |
| 转换权限控制 | ✅ | ✅ | ✅ | ✅ |

### 2.3 状态派生能力

| 能力 | SAP BOPF | Salesforce | D365 | 我们 |
|------|----------|-----------|------|------|
| 自动状态派生 | ✅ Status Derivator | ✅ Workflow | ✅ Business Rule | ✅ MetaDerivation |
| 基于字段变化派生 | ✅ | ✅ | ✅ | ✅ |
| 基于子对象聚合派生 | ✅ | ✅ Roll-up | ✅ | ⚠️ 部分 |
| 状态依赖链 | ✅ | ❌ | ❌ | ❌ |

### 2.4 状态历史与追溯

| 能力 | SAP BOPF | Salesforce | D365 | 我们 |
|------|----------|-----------|------|------|
| 状态变更历史 | ✅ | ✅ Field Audit | ✅ | ❌ 需新增 |
| 阶段停留时长 | ❌ | ✅ | ✅ | ❌ |
| 状态变更人 | ✅ | ✅ | ✅ | ❌ |
| 状态变更原因 | ✅ | ❌ | ✅ | ❌ |

### 2.5 状态可视化

| 能力 | SAP BOPF | Salesforce | D365 | 我们 |
|------|----------|-----------|------|------|
| 状态机图可视化 | ❌ | ✅ Path | ✅ BPF | ❌ |
| 阶段进度条 | ❌ | ✅ Path | ✅ BPF | ❌ |
| 当前阶段高亮 | ❌ | ✅ | ✅ | ❌ |

---

## 3. 关键差距深度分析

### 3.1 Status + StatusReason 双层模型（D365 特色）

**D365 模型**：
```
Status (系统级，固定)
├── Active
│   ├── In Progress
│   ├── On Hold
│   ├── Waiting for Details
│   └── Researching
├── Resolved
│   ├── Problem Solved
│   └── Information Provided
└── Canceled
    ├── Canceled
    └── Merged
```

**业务价值**：
- Status 是系统行为边界（Active 可编辑，Resolved/Canceled 只读）
- Status Reason 是业务语义细分（为什么处于这个状态）
- 状态过滤简化：`status = 'Active'` 快速筛选所有活跃记录

**我们当前模型**：
```yaml
enum_values:
  - value: in_progress
    label: 进行中
  - value: on_hold
    label: 暂停
  - value: resolved
    label: 已解决
```

**问题**：单层枚举，无法区分"系统状态"和"业务状态原因"

**建议扩展**：
```yaml
- id: status
  type: string
  enum_values:
    - value: active
      label: 活跃
      category: active           # 系统状态分类
      is_system: true            # 系统状态标记
    - value: resolved
      label: 已解决
      category: final
      is_system: true
      
- id: status_reason
  type: string
  semantics:
    status_binding: status       # 绑定到 status 字段
  enum_values:
    - value: in_progress
      label: 进行中
      parent_status: active      # 属于 Active 状态
    - value: on_hold
      label: 暂停
      parent_status: active
    - value: problem_solved
      label: 问题已解决
      parent_status: resolved
```

### 3.2 状态概率与预测（Salesforce 特色）

**Salesforce Opportunity Stage**：

| Stage | Probability | Forecast Category |
|-------|-------------|-------------------|
| Prospecting | 10% | Pipeline |
| Qualification | 20% | Pipeline |
| Proposal | 60% | Best Case |
| Negotiation | 80% | Commit |
| Closed Won | 100% | Closed |
| Closed Lost | 0% | Omitted |

**业务价值**：
- 自动计算预期收入：`Expected Revenue = Amount × Probability`
- 预测报表：按 Forecast Category 汇总
- 销售漏斗分析：各阶段转化率

**建议扩展**：
```yaml
enum_values:
  - value: prospecting
    label: 挖掘阶段
    probability: 10             # 成交概率
    forecast_category: pipeline # 预测分类
  - value: negotiation
    label: 谈判阶段
    probability: 80
    forecast_category: commit
```

### 3.3 Status Reason Transitions（D365 特色）

**D365 模型**：定义每个 Status Reason 可转换到哪些其他 Status Reason

```
In Progress → [On Hold, Waiting for Details, Researching, Canceled]
On Hold → [In Progress, Canceled]
Waiting for Details → [In Progress, On Hold, Researching, Canceled]
Researching → [Resolved, Canceled]
Resolved → [] (终态，不可转换)
Canceled → [] (终态，不可转换)
```

**业务价值**：
- 强制阶段顺序，防止随意跳转
- UI 下拉只显示允许的目标状态
- 业务流程规范化

**我们当前模型**：
```yaml
rules:
  - id: resolve_case
    type: state_transition
    from_states: [in_progress, researching]
    to_state: resolved
```

**问题**：from_states 是列表，无法表达"从 In Progress 只能到 On Hold 或 Researching"

**建议扩展**：
```yaml
state_transitions:
  - from: in_progress
    allowed_to: [on_hold, waiting_for_details, researching, canceled]
  - from: on_hold
    allowed_to: [in_progress, canceled]
  - from: researching
    allowed_to: [resolved, canceled]
    require_condition: "research_notes != null"  # 转换条件
```

### 3.4 状态派生器与依赖链（SAP BOPF 特色）

**SAP BOPF 模型**：
```
Status Derivator:
├── Derivation: calculate_overall_status
│   Trigger: after_modify (items)
│   Logic: 
│     if all items.status == 'completed' → 'completed'
│     elif any items.status == 'blocked' → 'blocked'
│     else → 'in_progress'
│
├── Dependency Chain:
│   item.status change → recalculate order.status
│   order.status change → recalculate delivery.status
```

**业务价值**：
- 状态自动计算，无需手动维护
- 父子对象状态联动
- 复杂状态逻辑声明式定义

**我们当前模型**：
```yaml
- id: status
  computation:
    formula: "IF(COUNT(items, status='blocked') > 0, 'blocked', 'in_progress')"
```

**问题**：Formula 可实现计算，但缺少"状态变化触发重新计算"的声明式机制

**建议扩展**：
```yaml
derivations:
  - id: calculate_order_status
    trigger:
      on: after_modify
      watch: [items.status]      # 监听子对象状态变化
    formula: |
      IF(COUNT(items, status='blocked') > 0, 'blocked',
         IF(COUNT(items, status='completed') == COUNT(items), 'completed',
            'in_progress'))
    cascade: true                # 变化后触发父对象重新计算
```

### 3.5 阶段停留时长（Salesforce/D365 特色）

**业务场景**：
- 销售阶段停留时长分析：每个阶段平均停留多少天
- SLA 监控：某阶段超过 N 天自动告警
- 瓶颈识别：哪个阶段停留时间最长

**建议实现**：
```yaml
- id: stage_duration_days
  name: 阶段停留天数
  type: integer
  storage: virtual
  computation:
    formula: "DATEDIFF(stage_entered_at, NOW(), 'days')"
    
# 或新增状态历史表
state_history:
  - id
  - object_type
  - object_id
  - from_stage
  - to_stage
  - entered_at      # 进入该阶段的时间
  - exited_at       # 离开该阶段的时间
  - duration_days   # 停留天数（计算字段）
```

---

## 4. 完整状态模型建议

### 4.1 扩展 enum_values 属性

```yaml
enum_values:
  - value: in_progress
    label: 进行中
    
    # 分类与标识
    category: active             # active / inactive / final / error
    is_initial: false            # 是否初始状态
    is_final: false              # 是否终态
    is_system: false             # 是否系统状态（不可删除）
    
    # UI 配置
    color: "#409EFF"
    icon: loading
    description: "问题正在处理中"
    sort_order: 10
    
    # Salesforce 风格
    probability: null            # 成交概率（用于销售预测）
    forecast_category: null      # 预测分类
    
    # D365 风格
    parent_status: active        # 所属系统状态（StatusReason 模式）
```

### 4.2 扩展 state_transition 规则

```yaml
rules:
  - id: transition_to_researching
    type: state_transition
    state_field: status
    
    # D365 风格：定义允许的目标状态
    from_state: in_progress
    allowed_to:
      - on_hold
      - waiting_for_details
      - researching
      - canceled
    
    # 转换条件
    condition: "assigned_to != null"
    condition_message: "必须先分配处理人"
    
    # 触发时机
    triggers: [before_update]
    
    # 副作用
    side_effects:
      - type: set_field
        target: stage_entered_at
        value: "NOW()"
      - type: notify
        template: "case_stage_changed"
        
    # UI 配置
    ui_hints:
      label: 开始调研
      icon: search
      confirm_message: "确定要开始调研吗？"
      highlight: true
```

### 4.3 新增状态历史表

```sql
CREATE TABLE state_transition_history (
    id INTEGER PRIMARY KEY,
    
    -- 对象标识
    object_type VARCHAR(100) NOT NULL,
    object_id INTEGER NOT NULL,
    state_field VARCHAR(50) NOT NULL,
    
    -- 状态变更
    from_state VARCHAR(50),
    from_state_label VARCHAR(100),
    to_state VARCHAR(50) NOT NULL,
    to_state_label VARCHAR(100),
    
    -- 时间信息
    entered_at TIMESTAMP,           -- 进入新状态时间
    exited_at TIMESTAMP,            -- 离开原状态时间（等于上一条记录的 entered_at）
    duration_seconds INTEGER,       -- 在原状态停留时长
    
    -- 变更信息
    transition_rule_id VARCHAR(100),
    operator_id INTEGER,
    operator_name VARCHAR(100),
    reason TEXT,                    -- 变更原因/备注
    
    -- 审计
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_object (object_type, object_id),
    INDEX idx_state_field (state_field),
    INDEX idx_created_at (created_at)
);
```

### 4.4 新增状态派生规则

```yaml
derivations:
  - id: calculate_order_status
    name: 计算订单状态
    target_field: status
    
    # 触发条件
    trigger:
      on: after_modify
      watch:
        - items.status             # 监听子对象状态
        - items.quantity           # 监听子对象数量
      scope: descendants           # self / children / descendants
    
    # 计算逻辑
    formula: |
      IF(COUNT(items, status='cancelled') == COUNT(items), 'cancelled',
         IF(COUNT(items, status='blocked') > 0, 'blocked',
            IF(COUNT(items, status='shipped') == COUNT(items), 'shipped',
               'in_progress')))
    
    # 级联触发
    cascade:
      notify_parent: true          # 通知父对象重新计算
      notify_dependents: [delivery.status]  # 触发依赖对象
```

---

## 5. 实施优先级建议

### Phase 3.5（近期）

| # | 功能 | 工期 | 来源 |
|---|------|------|------|
| 1 | enum_values 扩展 | 0.5天 | 综合 |
| 2 | 状态转换历史表 | 1天 | 综合 |
| 3 | allowed_to 转换约束 | 0.5天 | D365 |

### Phase 4（下一阶段）

| # | 功能 | 工期 | 来源 |
|---|------|------|------|
| 1 | Status + StatusReason 双层模型 | 1天 | D365 |
| 2 | 状态概率与预测 | 0.5天 | Salesforce |
| 3 | 阶段停留时长计算 | 0.5天 | Salesforce/D365 |
| 4 | 状态派生规则增强 | 1天 | SAP BOPF |

### Phase 5（远期）

| # | 功能 | 工期 | 来源 |
|---|------|------|------|
| 1 | 状态依赖链 | 2天 | SAP BOPF |
| 2 | 状态机可视化 | 2天 | Salesforce/D365 |
| 3 | 阶段进度条组件 | 1天 | Salesforce/D365 |

---

## 6. 总结

### 当前状态模型完备度

| 维度 | 完备度 | 说明 |
|------|--------|------|
| 状态定义 | 70% | 缺少 category/is_initial/is_final |
| 状态转换 | 80% | 缺少 allowed_to 精细化约束 |
| 状态派生 | 60% | 缺少依赖链和级联触发 |
| 状态历史 | 0% | 完全缺失 |
| 状态可视化 | 0% | 完全缺失 |
| 状态预测 | 0% | 缺少 probability/forecast_category |

### 核心差距

1. **状态转换历史**：三大产品均有，我们完全缺失
2. **Status + StatusReason 双层模型**：D365 核心设计，我们缺失
3. **状态概率与预测**：Salesforce 核心能力，销售场景必备
4. **allowed_to 转换约束**：D365 特色，强制阶段顺序
5. **状态派生依赖链**：SAP BOPF 特色，父子状态联动
