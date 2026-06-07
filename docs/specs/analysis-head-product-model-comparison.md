# 头部产品模型架构对比分析

> **创建日期**: 2026-05-22
> **目的**: 对比 SAP BOPF、Salesforce、Dynamics 365 的核心模型要素，识别差距

---

## 1. 核心模型要素对比矩阵

### 1.1 SAP BOPF 核心要素

| 模型要素 | 说明 | 我们是否有 | 对应实现 |
|----------|------|-----------|---------|
| **Node** | 业务对象节点，支持 Root/Child 层级 | ✅ | MetaObject + composition |
| **Attribute Mapping** | 代理结构与内部数据模型的映射 | ❌ | - |
| **Action** | 显式触发的业务操作 | ✅ | MetaAction |
| **Determination** | 自动派生的副作用逻辑 | ✅ | MetaDerivation |
| **Validation** | 一致性验证 + 动作验证 | ✅ | MetaValidation |
| **Association** | 节点间关联 | ✅ | MetaRelation |
| **Value Sets** | 枚举值集 | ✅ | enum_values |
| **Query** | 数据查询 | ✅ | MetaQuery |
| **Alternative Keys** | 替代键（业务键查找） | ⚠️ 部分 | display_name_field（仅显示） |
| **Status Schema** | 状态模式定义 | ✅ | MetaStateTransition |
| **Trigger** | 生命周期事件触发 | ✅ | MetaTrigger |
| **Dependency** | Determination 依赖顺序 | ❌ | - |

### 1.2 Salesforce 核心要素

| 模型要素 | 说明 | 我们是否有 | 对应实现 |
|----------|------|-----------|---------|
| **CustomObject** | 自定义对象 | ✅ | MetaObject |
| **CustomField** | 字段定义 | ✅ | MetaField |
| **ValidationRule** | 验证规则 | ✅ | MetaValidation |
| **RecordType** | 记录类型（同一对象多种业务形态） | ❌ | - |
| **PageLayout** | 页面布局 | ✅ | UIViewConfig |
| **Workflow/Flow** | 工作流/流程自动化 | ❌ | - |
| **PermissionSet** | 权限集 | ✅ | authorization |
| **SharingRules** | 共享规则 | ✅ | data_permission_dimensions |
| **BusinessProcess** | 业务流程（状态流转定义） | ⚠️ 部分 | MetaStateTransition |
| **FieldSet** | 字段集（字段分组） | ❌ | - |
| **DuplicateRule** | 重复检测规则 | ❌ | - |
| **MatchingRule** | 匹配规则 | ❌ | - |
| **Trigger** | Apex 触发器 | ✅ | MetaTrigger |
| **Formula Field** | 公式字段 | ✅ | MetaComputation + Formula |
| **Roll-up Summary** | 汇总字段（子→父聚合） | ⚠️ 部分 | computation(type=count_children) |
| **Lookup Filter** | 关联过滤 | ❌ | - |
| **External Object** | 外部对象 | ❌ | - |

### 1.3 Dynamics 365 核心要素

| 模型要素 | 说明 | 我们是否有 | 对应实现 |
|----------|------|-----------|---------|
| **Entity** | 实体 | ✅ | MetaObject |
| **Attribute** | 属性 | ✅ | MetaField |
| **Relationship** | 关系（1:N, N:1, N:N） | ✅ | MetaRelation |
| **OptionSet** | 选项集 | ✅ | enum_values |
| **Status/StatusReason** | 状态 + 状态原因 | ⚠️ 部分 | state_transition（缺 StatusReason） |
| **Business Process Flow** | 业务流程可视化 | ❌ | - |
| **Connections** | 多态关联 | ✅ | polymorphic association |
| **Rollup Fields** | 汇总字段 | ⚠️ 部分 | computation |
| **Calculated Fields** | 计算字段 | ✅ | MetaComputation |
| **Access Teams** | 访问团队 | ❌ | - |
| **Queue** | 队列 | ❌ | - |
| **SLA** | 服务级别协议 | ❌ | - |

---

## 2. 差距分析：缺失的核心模型要素

### 2.1 高优先级差距

| # | 模型要素 | 来源 | 业务价值 | 建议优先级 |
|---|----------|------|---------|-----------|
| 1 | **Alternative Keys** | SAP BOPF | 业务键双向查找（code→id, id→code） | P1 |
| 2 | **RecordType** | Salesforce | 同一对象多种业务形态（客户：企业/个人） | P1 |
| 3 | **Workflow/Flow** | Salesforce/D365 | 流程自动化、审批流 | P1 |
| 4 | **Business Process Flow** | D365 | 业务流程可视化、阶段管理 | P2 |

### 2.2 中优先级差距

| # | 模型要素 | 来源 | 业务价值 | 建议优先级 |
|---|----------|------|---------|-----------|
| 5 | **FieldSet** | Salesforce | 字段分组、API 字段选择 | P2 |
| 6 | **StatusReason** | D365 | 状态原因细分（状态=已拒绝，原因=资质不符/价格过高） | P2 |
| 7 | **Roll-up Summary 增强** | Salesforce | 声明式子→父聚合（SUM/COUNT/AVG/MAX/MIN） | P2 |
| 8 | **Lookup Filter** | Salesforce | 关联字段动态过滤 | P2 |

### 2.3 低优先级差距

| # | 模型要素 | 来源 | 业务价值 | 建议优先级 |
|---|----------|------|---------|-----------|
| 9 | **DuplicateRule** | Salesforce | 重复检测 | P3 |
| 10 | **MatchingRule** | Salesforce | 数据匹配 | P3 |
| 11 | **Attribute Mapping** | SAP BOPF | 多层映射 | P3 |
| 12 | **Dependency** | SAP BOPF | Determination 依赖顺序 | P3 |
| 13 | **Queue** | D365 | 工作队列 | P3 |
| 14 | **SLA** | D365 | 服务级别协议 | P3 |
| 15 | **Access Teams** | D365 | 团队访问权限 | P3 |
| 16 | **External Object** | Salesforce | 外部数据源集成 | P3 |

---

## 3. 详细分析：高优先级差距

### 3.1 Alternative Keys（替代键）

**来源**: SAP BOPF

**当前状态**: 
- 有 `display_name_field` 用于显示
- 有 `business_key` 概念但未完整实现

**业务场景**:
```
订单编号 "SO-2026-001" → 查找订单 ID 123
订单 ID 123 → 获取订单编号 "SO-2026-001"
客户代码 "CUST001" → 查找客户 ID 456
```

**建议实现**:
```yaml
alternative_keys:
  - name: code
    fields: [code]
    unique: true
    lookup_api: true      # 启用 /api/objects?code=xxx 查找
  - name: business_key
    fields: [company_code, document_type, document_number]
    unique: true
```

**API 扩展**:
```
GET /api/v1/orders?code=SO-2026-001
GET /api/v1/orders/lookup?business_key=COMP1,SO,001
```

### 3.2 RecordType（记录类型）

**来源**: Salesforce

**当前状态**: 无

**业务场景**:
```
客户对象：
- RecordType: 企业客户 → 字段：公司规模、行业、税号
- RecordType: 个人客户 → 字段：性别、生日、职业

同一对象，不同业务形态，不同字段集、不同页面布局、不同流程。
```

**建议实现**:
```yaml
record_types:
  - id: corporate
    name: 企业客户
    description: 企业或组织客户
    is_default: false
    field_set: [name, industry, company_size, tax_id]
    page_layout: corporate_layout
    business_process: corporate_onboarding
  - id: individual
    name: 个人客户
    description: 个人客户
    is_default: true
    field_set: [name, gender, birthday, occupation]
    page_layout: individual_layout
```

**模型扩展**:
```python
@dataclass
class RecordTypeDefinition:
    id: str
    name: str
    description: str = ""
    is_default: bool = False
    is_active: bool = True
    field_set: List[str] = field(default_factory=list)
    page_layout: Optional[str] = None
    business_process: Optional[str] = None
    ui: Dict[str, Any] = field(default_factory=dict)
```

### 3.3 Workflow/Flow（工作流）

**来源**: Salesforce Workflow / Flow, Dynamics 365 Workflow

**当前状态**: 
- 有 `MetaTrigger` 支持生命周期事件
- 有 `MetaStateTransition` 支持状态转换
- 缺少可视化流程编排

**业务场景**:
```
审批流程：
草稿 → 提交 → [经理审批] → 通过 → 完成
                  ↓
                拒绝 → 退回修改

自动化规则：
当 金额 > 10000 时，自动触发高级审批流程
当 状态=已完成 时，自动发送通知邮件
```

**建议实现**:
```yaml
workflows:
  - id: approval_workflow
    name: 采购审批流程
    trigger:
      type: record_change
      when: before_update
      condition: "amount > 5000"
    steps:
      - id: submit
        name: 提交审批
        type: state_transition
        from: draft
        to: pending_approval
      - id: manager_approve
        name: 经理审批
        type: approval
        approver: "self.department.manager"
        timeout: 3d
        timeout_action: escalate
      - id: complete
        name: 完成
        type: state_transition
        from: pending_approval
        to: approved
```

### 3.4 Business Process Flow（业务流程可视化）

**来源**: Dynamics 365

**当前状态**: 无

**业务场景**:
```
销售流程阶段：
线索 → 资格确认 → 需求分析 → 方案报价 → 谈判 → 成交

每个阶段：
- 显示当前阶段
- 阶段完成条件
- 阶段字段集
- 阶段时长统计
```

**建议实现**:
```yaml
business_process_flows:
  - id: sales_process
    name: 销售流程
    stages:
      - id: qualify
        name: 资格确认
        order: 1
        entry_condition: "status == 'new'"
        exit_condition: "is_qualified == true"
        fields: [contact_name, company_size, budget]
      - id: analyze
        name: 需求分析
        order: 2
        entry_condition: "previous_stage_completed"
        exit_condition: "requirements_document != null"
        fields: [requirements, timeline, stakeholders]
      - id: propose
        name: 方案报价
        order: 3
        ...
```

---

## 4. 与现有能力的关系分析

### 4.1 可通过现有能力覆盖的需求

| 需求 | 现有能力 | 说明 |
|------|---------|------|
| 状态转换 | MetaStateTransition | 已覆盖 |
| 计算字段 | MetaComputation + Formula | 已覆盖 |
| 字段验证 | MetaValidation | 已覆盖 |
| 生命周期事件 | MetaTrigger | 已覆盖 |
| 派生逻辑 | MetaDerivation | 已覆盖 |
| 软删除 | soft_delete | 已覆盖 |
| 层级结构 | hierarchy | 已覆盖 |
| 数据权限 | data_permission_dimensions | 已覆盖 |
| 审计日志 | audit | 已覆盖 |

### 4.2 需要新增模型的需求

| 需求 | 新增模型 | 复杂度 |
|------|---------|--------|
| Alternative Keys | AlternativeKeyDefinition | 低 |
| RecordType | RecordTypeDefinition | 中 |
| Workflow/Flow | WorkflowDefinition, WorkflowStep | 高 |
| Business Process Flow | BusinessProcessFlow, ProcessStage | 高 |
| FieldSet | FieldSetDefinition | 低 |
| StatusReason | 扩展 enum_values | 低 |
| Lookup Filter | LookupFilterDefinition | 中 |

---

## 5. 建议实施优先级

### Phase 3.5（近期补充）

| # | 功能 | 工期 | 价值 |
|---|------|------|------|
| 1 | Alternative Keys | 0.5天 | 业务键查找是高频场景 |
| 2 | enum_values 扩展（icon/is_initial/category） | 0.5天 | 状态管理增强 |
| 3 | 状态转换历史 | 1天 | 审计追溯 |

### Phase 4（下一阶段）

| # | 功能 | 工期 | 价值 |
|---|------|------|------|
| 1 | RecordType | 2天 | 多业务形态支持 |
| 2 | FieldSet | 1天 | 字段分组 |
| 3 | Lookup Filter | 1天 | 关联过滤 |
| 4 | Roll-up Summary 增强 | 1天 | 声明式聚合 |

### Phase 5（远期规划）

| # | 功能 | 工期 | 价值 |
|---|------|------|------|
| 1 | Workflow/Flow | 5天 | 流程自动化 |
| 2 | Business Process Flow | 3天 | 流程可视化 |
| 3 | DuplicateRule | 2天 | 数据质量 |
| 4 | SLA | 2天 | 服务管理 |

---

## 6. 结论

### 当前架构完备性评估

| 维度 | 完备度 | 说明 |
|------|--------|------|
| 数据模型 | 90% | 核心要素齐全 |
| 规则引擎 | 85% | 缺 Workflow |
| 状态管理 | 80% | 需增强 StatusReason |
| 业务流程 | 30% | 缺 BPF/Workflow |
| 数据质量 | 20% | 缺 DuplicateRule |
| 多态支持 | 70% | 有 polymorphic，缺 RecordType |

### 关键差距总结

1. **Alternative Keys**: 业务键双向查找是 SAP BOPF 的核心能力，建议优先补充
2. **RecordType**: Salesforce 核心能力，支持多业务形态，企业应用必备
3. **Workflow/Flow**: 流程自动化是头部产品的标配，建议纳入 Phase 4
4. **Business Process Flow**: 流程可视化提升用户体验，建议纳入 Phase 5

### 与 Phase 3 的关系

Phase 3 已完成的能力（Deep Insert、多态 Composition、Formula 增强）为后续功能奠定了基础：
- RecordType 可复用 Formula 进行字段条件计算
- Workflow 可复用 MetaTrigger 和 MetaStateTransition
- Business Process Flow 可复用状态转换历史
