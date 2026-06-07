# 架构方案合理性评估：对标头部企业产品的深度分析

> **版本**: v1.0.0
> **日期**: 2026-05-26
> **前置文档**: [ARCHITECTURE_V2_GAP_ANALYSIS.md](./ARCHITECTURE_V2_GAP_ANALYSIS.md)
> **对标产品**: SAP CAP/Fiori、Salesforce Platform、ServiceNow
> **评估目标**: 基于 GAP 分析发现的6个差距领域，对照头部企业产品的设计模式，评估当前方案的合理性并提出改进建议

---

## 目录

1. [评估总览](#1-评估总览)
2. [StateTransition 方案评估](#2-statetransition-方案评估)
3. [ValueHelp 方案评估](#3-valuehelp-方案评估)
4. [ObjectPage 方案评估](#4-objectpage-方案评估)
5. [CascadeSelect 方案评估](#5-cascadeselect-方案评估)
6. [KeyTemplate 方案评估](#6-keytemplate-方案评估)
7. [跨领域系统性建议](#7-跨领域系统性建议)

---

## 1. 评估总览

### 1.1 评估方法论

本文采用 **"对标-差距-根因-建议"** 四步法：

```
头部企业产品实践（SAP/Salesforce/ServiceNow）
    ↓ 对标
我们的当前实现
    ↓ 差距识别
差距根因分析（设计取舍 vs 实现遗漏）
    ↓ 建议
保留 / 改进 / 重构
```

### 1.2 总体评分

| 领域 | 方案合理性 | 与头部产品对齐度 | 需要改进程度 |
|------|:---------:|:-------------:|:----------:|
| StateTransition | B | 60% | **需要改进** |
| ValueHelp | A- | 85% | 微调即可 |
| ObjectPage | B+ | 75% | 需要结构优化 |
| CascadeSelect | A | 90% | 基本合理 |
| KeyTemplate | A- | 80% | 微调即可 |

> 评分标准：A=与头部产品对齐，B=方向正确但有差距，C=需要重新设计

---

## 2. StateTransition 方案评估

### 2.1 头部企业产品实践

#### SAP CAP — Bound Action 模式（最佳实践）

SAP CAP 在 2024-2025 年推出了 `@flow.status` 注解体系，这是业界最成熟的状态转换元数据驱动方案：

```cds
// SAP CAP CDS 定义
annotate TravelService.Travels with @flow.status: Status actions {
  acceptTravel @from: [ #Open ]    @to: #Accepted;
  rejectTravel @from: [ #Open ]    @to: #Rejected;
  deductDiscount @from: [ #Open ];  // restricted action, no state change
}
```

**SAP 的核心设计决策**：

| 设计点 | SAP CAP 做法 | 原因 |
|--------|------------|------|
| 状态字段标记为 `@readonly` | 禁止客户端直接 PUT 修改状态 | 防止绕过转换规则 |
| 转换通过 Bound Action 触发 | `POST /Travels(ID)/acceptTravel` | 状态变更是行为，不是数据修改 |
| Generic Handler 自动执行 | 框架内置 from/to 校验 + 状态更新 | 消除自定义编码 |
| UI 自动发现可用转换 | OData Metadata 暴露 available actions | Fiori Elements 自动渲染按钮 |

**关键原则**：**状态转换是行为（Action），不是数据修改（PUT）**。SAP 严格禁止通过通用 PUT 修改状态字段。

#### Salesforce — Approval Process + Flow Orchestration

Salesforce 在 Spring '25 推出了 Flow Approval Orchestration，替代 Classic Approval Process：

```
Salesforce 模式:
  Stage 1 → Approval Step (Screen Flow, 交互式)
  Stage 2 → Background Step (Auto-launched Flow, 自动)
  Stage 3 → Decision Element (条件路由)

关键设计:
  - ProcessDefinition: 只读的流程定义
  - ProcessInstance: 每次提交产生一个实例
  - ProcessInstanceStep: 记录每一步的审批结果
  - ProcessInstanceWorkItem: 待办事项
```

Salesforce 的核心思想：**状态转换与审批流程是一体化的**，不是独立的两个功能。

#### ServiceNow — State Machine + Workflow Engine

ServiceNow 采用 State Machine + Workflow 双引擎：

```
State Model (数据层):
  - 定义合法状态和转换
  - 条件表达式控制转换可用性

Workflow Engine (流程层):
  - 定义转换触发的工作流
  - 支持并行/串行审批
  - 事件驱动（onEnter/onExit/onTransition）
```

### 2.2 我们的方案评估

#### 当前问题

| # | 问题 | 严重度 | 根因 |
|---|------|:------:|------|
| P1 | 前端 PUT 直接修改状态字段，绕过 StateTransitionExecutor | **高** | 缺少 Action 语义 |
| P2 | entered_at 时间戳在 PUT 路径不自动设置 | 中 | P1 的副作用 |
| P3 | condition 条件校验在 PUT 路径不执行 | 中 | P1 的副作用 |
| P4 | StateTransitionButton 和 StateTransitionButtons 功能重叠 | 低 | 组件设计冗余 |

#### 合理性判断

**方向正确，但执行有偏差**。我们的 YAML rules 声明式设计（from_states/to_state/ui_hints）与 SAP CAP 的 @flow.status 高度对齐，这是正确的。但前端通过 PUT 直接修改状态字段，违反了 **"状态转换是行为不是数据修改"** 这一核心原则。

#### 改进建议

**建议1：引入 StateTransition Bound Action（对标 SAP CAP）**

```
当前:
  PUT /api/v2/bo/user/42  { status: "active" }     ← 绕过引擎

建议:
  POST /api/v2/bo/user/42/actions/activate_user     ← 走引擎
  Body: { _comment: "审批意见" (可选) }
```

实现路径：
1. 在 `bo_api.py` 中新增 `POST /bo/{entity}/{id}/actions/{action_id}` 端点
2. 该端点内部调用 `BOFramework.execute_action(action_id)` → 经过拦截器链 → `StateTransitionExecutor`
3. 状态字段在 YAML 中标记 `readonly: true`（SAP CAP 同款策略）
4. 前端 `StateTransitionButtons` 调用新端点而非通用 PUT

**建议2：统一两个前端组件**

将 `StateTransitionButton` 和 `StateTransitionButtons` 合并为一个组件，通过 props 区分 API 驱动和 props 驱动模式。

**建议3：补充 ProcessInstance 审计模型（对标 Salesforce）**

当前审计日志只记录 "UPDATE status: inactive→active"，缺少转换上下文。建议：

```yaml
# 新增 state_transition_logs 表
state_transition_logs:
  fields:
    - id: id
    - id: object_type
    - id: object_id
    - id: action_id          # activate_user / lock_user
    - id: from_state
    - id: to_state
    - id: comment            # 用户填写的转换原因
    - id: actor_id
    - id: created_at
```

---

## 3. ValueHelp 方案评估

### 3.1 头部企业产品实践

#### SAP Fiori — OData V4 Annotation 驱动

SAP Fiori Elements 的 ValueHelp 是业界最完整的元数据驱动值帮助体系：

```
SAP ValueHelp 架构:

后端 CDS Annotation:
  @Common.ValueList: {                  ← 数据源定义
    CollectionPath: 'I_CountryStdVH',
    Parameters: [
      { $Type: 'Common.ValueListParameterInOut', LocalDataProperty: 'Country', ValueListProperty: 'Country' },
      { $Type: 'Common.ValueListParameterOut', LocalDataProperty: 'CountryName', ValueListProperty: 'Name' }
    ],
    SearchSupported: true
  }

前端自动渲染:
  - 候选集 < 100: Dropdown
  - 候选集 100-1000: Dropdown with Search
  - 候选集 > 1000: Value Help Dialog (FilterBar + Table + Variant)

关键设计:
  - In/Out Parameter Mapping: 前端字段 ↔ ValueHelp字段的双向映射
  - $search: OData V4 标准搜索
  - Variant Management: 保存/加载过滤条件组合
  - sap:value-list="standard" vs "fixed-values": 控制下拉 vs 对话框
```

**SAP 的核心原则**：
1. **Annotation 是唯一配置入口** — 后端 CDS 注解自动推导前端 UI
2. **In/Out Mapping** — 选择一个值后可以同时回填多个字段（如选 Country 同时回填 CountryCode 和 CountryName）
3. **三级渲染策略** — 根据候选集大小自动选择 Dropdown / Dropdown+Search / Dialog

#### Salesforce — Lookup + Dependent Picklist

Salesforce 的值帮助分为两种：

```
Lookup (引用字段):
  - 指向另一个对象的关联
  - Lookup Filter: 限制可选范围
  - Recently Viewed / Search: 自动提供最近查看 + 搜索

Dependent Picklist (依赖选择列表):
  - Controlling Field → Dependent Field
  - Dependency Matrix: 控制项 × 依赖项的可见性矩阵
  - 仅支持 Picklist → Picklist 的依赖
```

### 3.2 我们的方案评估

#### 合理性判断：**A- 级别，方向高度正确**

| 设计点 | SAP 做法 | 我们的做法 | 评价 |
|--------|---------|----------|------|
| 元数据驱动 | CDS Annotation | YAML value_help | 对齐 |
| 数据源类型 | CollectionPath | source_type (enum/bo/custom) | 对齐，更灵活 |
| 参数映射 | In/Out Parameters | parameter_bindings | 对齐 |
| Provider 工厂 | CDS 自动解析 | EnumVH/BoVH/CustomVH Provider | 对齐 |
| 三级渲染 | Dropdown/Dialog 自动选择 | display_mode 配置 | **需改进** |

#### 需要改进的点

**改进1：In/Out Mapping（对标 SAP）**

当前 `parameter_bindings` 只支持"上级字段过滤下级选项"（单向），缺少 SAP 的 In/Out Mapping（选择后回填多个字段）。

```yaml
# 当前：只支持过滤
value_help:
  behavior:
    parameter_bindings:
      - field: domain_id
        binds_to: filter_param

# 建议：增加 out_mapping（对标 SAP ValueListParameterOut）
value_help:
  behavior:
    parameter_bindings:
      - field: domain_id
        binds_to: filter_param
    out_mappings:
      - value_help_field: name
        local_field: domain_name
      - value_help_field: code
        local_field: domain_code
```

**改进2：三级渲染自动推导（对标 SAP）**

SAP 根据候选集大小自动选择 Dropdown / Dialog。我们当前需要手动配置 `display_mode`。

建议增加自动推导规则：

```python
# value_help_service.py 中增加
def infer_display_mode(vh_config, candidate_count):
    if candidate_count <= 50:
        return 'dropdown'
    elif candidate_count <= 500:
        return 'dropdown_with_search'
    else:
        return 'dialog'
```

**改进3：Enum Fallback 机制显式化**

当前 `EnumVHProvider` 有隐式 fallback（DB 无数据时回退到 YAML enum_values），但这个行为不可配置。建议：

```yaml
value_help:
  source:
    source_type: enum
    source_id: user_status
    fallback: yaml_enum_values    # 显式声明 fallback 策略
    fallback_order: [db, yaml]    # 优先 DB，fallback 到 YAML
```

---

## 4. ObjectPage 方案评估

### 4.1 头部企业产品实践

#### SAP Fiori — Object Page Floorplan

SAP Fiori 的 Object Page 是一个标准 Floorplan（页面模板）：

```
SAP Object Page 结构:

Header Area:
  - Title + Subtitle + Status
  - KPI Tags
  - Action Buttons (Edit / Delete / Custom Actions)

Content Area:
  - Sections (Facets):
    - ReferenceFacet: 字段组（对标我们的 standard section）
    - CollectionFacet: 关联对象列表（对标我们的 association section）
    - NavigationFacet: 导航链接
  - Section 可以是 SubSection 的容器

关键设计:
  - CDS @UI.Facet 注解驱动
  - @UI.LineItem → 表格列
  - @UI.FieldGroup → 字段组
  - @UI.Identification → 标识区域
  - Criticality: 状态颜色自动推导
```

**SAP 的核心原则**：
1. **Facet 注解是唯一配置** — 后端 CDS @UI.Facet 自动推导页面布局
2. **SmartField 自动渲染** — 根据字段类型 + 注解自动选择控件
3. **Section 懒加载** — Tab 切换时才加载关联数据

#### Salesforce — Lightning Record Page + Dynamic Forms

```
Salesforce 模式:
  - Page Layout: 经典布局（管理员配置）
  - Lightning Record Page: 动态布局（拖拽式）
  - Dynamic Forms: 字段级可见性控制
  - Related Lists: 关联对象列表（内嵌）
  - Actions: 页面级操作按钮
```

### 4.2 我们的方案评估

#### 合理性判断：**B+ 级别，功能完备但结构需优化**

| 设计点 | SAP 做法 | 我们的做法 | 评价 |
|--------|---------|----------|------|
| Section 类型 | Facet (3种) | Section (5种) | 更丰富，但需规范 |
| 字段渲染 | SmartField 自动推导 | autoLoadMeta + ValueHelpField | 对齐 |
| 关联对象 | CollectionFacet | association section + 内嵌 MetaListPage | 对齐 |
| 审计日志 | 独立 TimeLine 组件 | history section | 对齐 |
| 备注/附件 | 独立 Attachment 组件 | annotation section | 对齐，但耦合度高 |
| 页面配置 | CDS @UI.Facet | YAML ui_view_config.detail | 对齐 |

#### 需要改进的点

**改进1：ObjectPage 组件职责过重（~1800行）**

SAP Fiori Elements 的 ObjectPage 是由多个子组件组合而成，而非单一巨组件。我们的 ObjectPage 承载了过多职责：

```
当前 ObjectPage 职责（过多）:
  - Section 渲染（5种类型）
  - 字段渲染（ValueHelp / Enum / Cascade）
  - Action 语义推理
  - Annotation CRUD
  - AuditLog 加载与展示
  - 关联对象加载
  - Merged Relationships 加载
  - StateTransition 集成

建议拆分:
  ObjectPage (骨架，~400行)
    ├─ ObjectPageHeader (标题/状态/Actions/StateTransition)
    ├─ ObjectPageSection (Section 容器)
    │   ├─ FieldGroupSection (standard)
    │   ├─ AssociationSection (association)
    │   ├─ AnnotationSection (annotation)
    │   └─ HistorySection (history)
    └─ ObjectPageField (字段渲染，含 ValueHelpField 集成)
```

**改进2：Annotation 独立化（对标 SAP Attachment）**

当前 Annotation 的 CRUD 逻辑全部内嵌在 ObjectPage 中（L1131-L1274），包括：
- 表单状态管理（annotationFormVisible / annotationFormData / annotationEditingId）
- API 调用（fetch /annotations CRUD）
- 类别加载（loadAnnotationCategories + fallback）

建议抽取为独立的 `AnnotationSection` 组件，ObjectPage 仅负责 slot 渲染。

**改进3：Merged Relationships 数据加载策略**

当前 `loadMergedRelationships()` 发起两个并行请求（source_bo_id + target_bo_id），然后前端去重合并。这个逻辑更适合后端完成：

```
当前:
  前端: Promise.all([query(source_bo_id), query(target_bo_id)]) → 前端去重

建议:
  后端: GET /api/v2/bo/relationship?related_bo_id={id}  ← 后端合并
  前端: 单次请求
```

---

## 5. CascadeSelect 方案评估

### 5.1 头部企业产品实践

#### Salesforce — Dependent Picklist

Salesforce 的 Dependent Picklist 是最经典的级联选择实现：

```
Salesforce 模式:
  - Controlling Field (控制项): Picklist 或 Checkbox
  - Dependent Field (依赖项): Picklist 或 Multi-select Picklist
  - Dependency Matrix: 可视化矩阵配置哪些值可见

限制:
  - 最多支持 ~300 个控制值
  - 不支持 Multi-select Picklist 作为控制项
  - Record Type 会进一步过滤可用值
  - 最多 3-4 级依赖（超过后维护困难）

最佳实践:
  - 超过 3 级依赖时，建议改用 Lookup + Reference Qualifier
  - 依赖关系在 API 导入时不强制（需 Validation Rule 补充）
```

#### ServiceNow — Dependent Choice + Lookup Select Box

```
ServiceNow 模式:
  - Dependent Choice: 基于 sys_choice 表的 value 匹配
  - Lookup Select Box: 基于 Reference Qualifier 动态过滤
  - UI Builder: Client State Parameter + Data Resource 联动

关键设计:
  - value 是机器ID，label 是人可读 → 依赖基于 value 而非 label
  - Reference Qualifier: javascript:'u_server=' + current.variables.server
  - 变量属性: ref_qual_elements=server → 声明依赖关系
```

#### SAP — ValueList Parameter In/Out

SAP 通过 ValueHelp 的 Parameter Mapping 实现级联：

```cds
// SAP: Country → Region 级联
@Common.ValueList: {
  CollectionPath: 'I_RegionVH',
  Parameters: [
    { $Type: 'Common.ValueListParameterIn', LocalDataProperty: 'CountryCode', ValueListProperty: 'Country' },
    { $Type: 'Common.ValueListParameterInOut', LocalDataProperty: 'RegionCode', ValueListProperty: 'Region' }
  ]
}
region : RegionCode;
```

### 5.2 我们的方案评估

#### 合理性判断：**A 级别，高度对齐**

| 设计点 | Salesforce | ServiceNow | 我们 | 评价 |
|--------|-----------|------------|------|------|
| 级联配置 | Dependency Matrix | Reference Qualifier | YAML cascade_select | 更声明式 |
| 级联深度 | 3-4级（推荐） | 无硬限制 | 6级 | 需注意性能 |
| 过滤机制 | 前端矩阵 | 后端 SQL WHERE | ValueHelp parameter_bindings | 混合模式 |
| 值清空 | 自动 | 需手动 | 自动（上级变更清空下级） | 对齐 |
| 后端校验 | Validation Rule | Business Rule | StateTransitionExecutor condition | 需补充 |

#### 需要注意的点

**注意1：6级级联的性能风险**

Salesforce 官方建议不超过 3-4 级依赖。我们 relationship.yaml 中定义了 6 级级联（version → domain → sub_domain → service_module → business_object），每级都会触发一次 ValueHelp API 请求。

建议：
- 考虑对高频级联场景增加预加载（一次请求返回整棵子树）
- 或引入 `cascade_prefetch: true` 配置项，允许一次 API 调用获取多级数据

**注意2：cascade_select 与 ValueHelp parameter_bindings 的统一**

当前存在两套级联配置方式（cascade_select 和 parameter_bindings），这增加了理解和维护成本。建议：

```
短期: 保持两套并存，文档明确各自适用场景
  - cascade_select: 用于 BO 级别的全局级联策略
  - parameter_bindings: 用于字段级别的精细控制

长期: 统一为 parameter_bindings，cascade_select 作为语法糖自动展开
  cascade_select:
    - field: source_domain_id
      filter_by: version_id
  ↓ 自动展开为
  fields:
    - id: source_domain_id
      value_help:
        behavior:
          parameter_bindings:
            - field: version_id
              binds_to: filter_param
```

---

## 6. KeyTemplate 方案评估

### 6.1 头部企业产品实践

#### SAP — SemanticKey + BusinessKey

```cds
// SAP CAP: SemanticKey 标识业务键
annotate Books with @ObjectModel.SemanticKey: [title];

// Auto Number: SAP S/4HANA 使用 Number Range Object
// 配置: SNRO (Number Range Object) → 定义范围和前缀
// 运行时: NUMBER_GET_NEXT() 获取下一个编号
```

#### Salesforce — Auto Number Field

```
Salesforce Auto Number:
  - 格式: {YYYY}-{MM}-{0000}
  - 前缀/后缀/序号段
  - 每天重置/永不重置
  - 并发安全: 数据库序列保证唯一性
```

### 6.2 我们的方案评估

#### 合理性判断：**A- 级别，设计良好**

| 设计点 | SAP | Salesforce | 我们 | 评价 |
|--------|-----|-----------|------|------|
| 模板定义 | CDS Annotation | Field Metadata | YAML key_template | 对齐 |
| 序号生成 | SNRO | Auto Number | SEQ:N 段 | 对齐 |
| 触发时机 | before_save | before_insert | before_action (CREATE) | 对齐 |
| 用户覆盖 | 不允许 | 可配置 | auto_suggest: true | 更灵活 |
| 拦截器位置 | Framework | Trigger | Priority 45 | 合理 |

#### 微调建议

**建议1：增加 Number Range 配置**

当前 `SEQ:2` 只定义了位数，缺少 Salesforce 风格的 Number Range 配置：

```yaml
# 当前
key_template:
  pattern: "{source_code}-{target_code}-{SEQ:2}"

# 建议：增加 range 配置
key_template:
  pattern: "{source_code}-{target_code}-{SEQ:2}"
  sequence:
    start: 1
    reset: never          # never / daily / monthly / yearly
    padding: 2            # 补零位数
    scope: global         # global / per_source / per_day
```

**建议2：并发安全**

当前 `KeyTemplateEngine` 在高并发下可能产生重复编号。建议引入数据库序列或乐观锁机制。

---

## 7. 跨领域系统性建议

### 7.1 统一的 Action 语义模型

当前最大的架构缺口是 **缺少统一的 Action 语义模型**。SAP CAP 和 Salesforce 都将状态转换、业务操作统一为 Action/ActionFunction：

```
SAP CAP:
  - Bound Action: POST /Travels(ID)/acceptTravel
  - Bound Function: GET /Travels(ID)/availableTransitions
  - CRUD: 标准 OData CRUD (POST/GET/PATCH/DELETE)

Salesforce:
  - Quick Action: 页面级操作按钮
  - Flow Action: 流程中的自动化步骤
  - CRUD: 标准 REST API
```

建议我们建立统一的 Action 语义模型：

```yaml
# YAML 声明
actions:
  - id: activate_user
    type: state_transition
    binding: bound            # bound=绑定到实例, unbound=全局
    http_method: POST         # 统一为 POST
    path: /actions/activate   # RESTful path
    from_states: [inactive, locked]
    to_state: active
    ui_hints:
      label: 激活
      icon: check_circle

  - id: export_report
    type: custom
    binding: unbound
    http_method: POST
    handler: export_service.generate_report
```

```python
# bo_api.py 统一端点
@bo_bp.route('/<entity>/<int:obj_id>/actions/<action_id>', methods=['POST'])
def execute_action(entity, obj_id, action_id):
    return bo_framework.execute_action(entity, obj_id, action_id)
```

### 7.2 前端组件分层优化

对标 SAP Fiori Elements 的组件分层，建议：

```
当前:
  ObjectPage (1800行巨组件)
    → 直接包含所有逻辑

建议:
  ObjectPageShell (骨架, ~300行)
    ├─ ObjectPageHeader (标题/状态/Actions)
    │   └─ StateTransitionButtons
    ├─ ObjectPageContent (Section 容器)
    │   ├─ FieldGroupSection
    │   ├─ AssociationSection → 内嵌 MetaListPage
    │   ├─ AnnotationSection (独立组件)
    │   └─ HistorySection → 内嵌 AuditLog
    └─ ObjectPageField (字段渲染)
        └─ ValueHelpField
```

### 7.3 后端校验与前端校验的一致性保障

对标 Salesforce 的 "前端 Dependent Picklist + 后端 Validation Rule" 双重保障模式：

| 校验层 | 当前状态 | 建议 |
|--------|---------|------|
| 前端 UI 级联 | cascade_select + parameter_bindings | 保持 |
| 后端 StateTransition 校验 | StateTransitionExecutor（仅引擎路径） | 统一到 Action 路径 |
| 后端 CascadeSelect 校验 | 无 | 新增：Interceptor 校验级联合法性 |
| 后端 KeyTemplate 唯一性 | UniqueCheckInterceptor | 保持 |

### 7.4 渐进式改进路线图

| 阶段 | 改进项 | 影响范围 | 优先级 |
|------|--------|---------|:------:|
| **Phase 1** | StateTransition Bound Action 端点 | bo_api.py + StateTransitionButtons | 高 |
| **Phase 1** | 状态字段标记 readonly | YAML + bo_framework.py | 高 |
| **Phase 2** | ObjectPage 拆分为子组件 | ObjectPage.vue | 中 |
| **Phase 2** | AnnotationSection 独立化 | ObjectPage.vue | 中 |
| **Phase 2** | ValueHelp In/Out Mapping | models.py + value_help_service.py | 中 |
| **Phase 3** | cascade_select → parameter_bindings 统一 | yaml_loader.py + ObjectPage.vue | 低 |
| **Phase 3** | KeyTemplate Number Range | key_template_engine.py | 低 |
| **Phase 3** | ValueHelp 三级渲染自动推导 | value_help_service.py | 低 |

---

## 附录：头部企业产品参考矩阵

| 能力领域 | SAP CAP/Fiori | Salesforce | ServiceNow | 我们 |
|---------|:------------:|:----------:|:----------:|:----:|
| 状态转换 | @flow.status + Bound Action | Approval Orchestration | State Machine + Workflow | YAML rules + PUT (需改进) |
| 值帮助 | @Common.ValueList + In/Out | Lookup + Dependent Picklist | Lookup Select Box + Ref Qual | 五层架构 (对齐) |
| 对象页面 | Object Page Floorplan | Lightning Record Page | Workspace | 渲染引擎 (需拆分) |
| 级联选择 | ValueList Parameter In | Dependent Picklist Matrix | Dependent Choice | cascade_select (对齐) |
| 自动编码 | SemanticKey + SNRO | Auto Number Field | Auto Number | KeyTemplate (对齐) |
| 元数据驱动 | CDS Annotation | Custom Metadata + Field Definition | Dictionary + Choice | YAML Schema (对齐) |
| 审计追踪 | CDS managed aspect | ProcessInstance History | Audit Trail | AuditInterceptor (对齐) |
| 权限模型 | CDS @AccessControl + PFCG | FLS + Sharing Rules | ACL + Business Rules | 四层权限 (对齐) |

---

## 结论

我们的架构方案在**方向上与头部企业产品高度对齐**，特别是：
- YAML 元数据驱动（对标 SAP CDS Annotation）
- ValueHelp 五层架构（超越 Salesforce，接近 SAP）
- CascadeSelect 声明式配置（优于 ServiceNow 的 Reference Qualifier）
- KeyTemplate 拦截器模式（对标 SAP SNRO + Salesforce Auto Number）

**最需要改进的是 StateTransition 的双路径问题**：前端 PUT 直接修改状态违反了 "状态转换是行为不是数据修改" 的核心原则。引入 Bound Action 端点是最高优先级的改进项。

**其次是 ObjectPage 的结构优化**：~1800 行的单组件承载了过多职责，需要拆分为子组件以保持可维护性。
