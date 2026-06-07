# Spec: 企业平台架构缺失要素补充方案

> **前置文档**: [unified-metadata-api-architecture/spec.md](../unified-metadata-api-architecture/spec.md)
>
> **关联分析**: 基于 SAP CAP / Palantir Foundry / Salesforce / D365 / OutSystems / Mendix / Appian 头部产品对比分析
>
> **当前进度**: 本 spec 为架构演进路线图，覆盖 14 项待补充架构要素

---

## 1. 背景与目标

### 1.1 背景

当前系统已经构建了完整的元数据驱动 CRUD 平台架构，核心能力包括：

| 已完成 | 能力 |
|--------|------|
| 元数据模型层 | YAML 单一事实原则、字段语义、关联定义、枚举、计算字段、DisplayName |
| BO Framework | 统一 CRUD、Association 操作、Deep Insert、9 个拦截器、4 个引擎 |
| 前端 Dynamic UI | MetaListPage、MetaTable、MetaForm、DetailPage、AssociationSelector |
| UI 规范 | YonDesign + Element Plus、组件分层体系 |
| 权限体系 | 四层权限（数据/字段/菜单/操作权限） |
| 导入导出 | Excel 级联导入导出、冲突处理 |
| 日志审计 | StructuredLogger（5类）、AuditInterceptor |
| Enrichment | RedundancyRegistry 统一冗余字段 + 枚举关联填充 |
| Inline Edit | 列表内联编辑、行级可编辑性控制 |

通过与 SAP CAP、Palantir Foundry、Salesforce Lightning、Microsoft Dynamics 365 / Power Platform、OutSystems、Mendix、Appian 等头部企业平台的全面对比，识别出 **14 项架构缺失要素**，分为三个层级：

- **P0 结构性缺失**（5项）：决定架构完备性，缺失将导致平台无法覆盖企业级核心场景
- **P1 能力延伸性缺失**（4项）：提升平台完整度，缺失将限制平台在更多业务场景的适用性
- **P2 工程质量性缺失**（5项）：提升工程成熟度，缺失将影响团队协作效率和长期可维护性

### 1.2 业务目标

- 将当前"元数据驱动 CRUD 管理工具"进化为"元数据驱动企业事务分析一体平台"
- 补充缺失的架构要素，使平台具备与头部产品对等的企业级能力
- 建立清晰的演进路线图，按优先级分阶段推进

### 1.3 用户 / 涉众目标

| 涉众 | 目标 |
|------|------|
| 架构团队 | 建立完整的架构蓝图，指导和约束后续开发 |
| 后端开发 | 获得明确的实施路径和技术方案 |
| 前端开发 | 理解新能力的 UI 交互模式和组件需求 |
| 业务用户 | 获得审批流程、决策规则、通知等业务能力 |

---

## 2. 需求类型概览

| 类型 | 适用 | 来源 |
|------|------|------|
| 业务需求 | 是 | 头部产品对比分析、业务场景扩展需求 |
| 用户/涉众需求 | 是 | 架构团队、业务用户的功能期望 |
| 解决方案需求 | 是 | 13 项缺失要素的技术方案设计 |
| 功能需求 | 是 | 本 spec 第3节 |
| 非功能需求 | 是 | 本 spec 第4节 |
| 外部接口需求 | 是 | 本 spec 第5节 |
| 过渡需求 | 是 | 本 spec 第6节 |

---

## 3. 功能需求

### 3.1 缺失要素总览

```
P0 结构性缺失 (Phase 19-23)
├── FR-001: 决策规则引擎 (Business Rules Engine) [用户最高优先级]
├── FR-014: 技术ID策略与Business Key编码规则引擎 (ID Strategy & Business Key) [NEW]
├── FR-002: 工作流/业务流程引擎 (Workflow/BPM Engine)
├── FR-003: 事件驱动架构 (Event-Driven Architecture)
├── FR-004: 环境/租户管理 (Environment/Tenancy)

P1 能力延伸性缺失 (Phase 23-26)
├── FR-005: 外部系统连接器框架 (Connector Framework)
├── FR-006: 通知/消息服务 (Notification Service)
├── FR-007: 流程监控与分析 (Process Monitoring/Visibility)
├── FR-008: 国际化 (i18n)

P2 工程质量性缺失 (Phase 27-31)
├── FR-009: DevOps/CI-CD 能力
├── FR-010: 沙箱/开发环境
├── FR-011: AI 辅助开发
├── FR-012: 数据血缘追踪
├── FR-013: 模板市场/组件复用生态
```

---

### FR-001: 决策规则引擎 (Business Rules Engine) [Must]

> **用户明确指定最高优先级**

- **描述**: 系统必须提供元数据驱动的业务规则引擎，允许在 YAML 中声明决策规则，在运行时按条件自动触发规则评估，并产生决策结果。规则应与流程和 CRUD 操作解耦，支持热更新。
- **对标产品**: SAP BRM、Salesforce Validation Rules、D365 Business Rules Engine、Appian Decision Rules
- **验收标准**:
  - 支持在 YAML 中声明规则（条件 + 动作），格式与现有 `fields` / `semantics` 风格一致
  - 规则类型至少支持：校验规则（Validation Rule）、计算规则（Calculation Rule）、决策规则（Decision Rule）
  - 规则可绑定到 BO CRUD 操作的生命周期（before_create / after_update / before_delete 等）
  - 规则支持 AND/OR 条件组合、比较运算符、枚举匹配、关联字段引用
  - 规则执行结果包含：通过（PASS）、警告（WARN）、阻断（BLOCK）
  - 规则评估引擎支持批量执行和短路优化
  - 规则变更后无需重启服务即可生效（热更新）
  - 规则执行日志自动记录审计信息
- **优先级**: Must
- **类型映射**: 业务需求 / 功能需求
- **来源**: 头部产品对比分析 + 用户明确优先级指定

```yaml
# 规则 YAML 声明示例（目标形态）
rules:
  - id: "enum_type_unique_code"
    name: "枚举类型编码唯一性"
    type: "validation"
    bindings:
      - entity: "enum_type"
        lifecycle: ["before_create", "before_update"]
    condition:
      operator: "exists"
      query:
        entity: "enum_type"
        filter:
          field: "code"
          operator: "eq"
          value: "${input.code}"
          exclude_self: true
    actions:
      - type: "block"
        message: "编码 '${input.code}' 已存在，请使用其他编码"
        severity: "error"

  - id: "user_email_required_for_active"
    name: "激活用户必须填写邮箱"
    type: "validation"
    bindings:
      - entity: "user"
        lifecycle: ["before_create", "before_update"]
    condition:
      operator: "and"
      conditions:
        - field: "status"
          operator: "eq"
          value: "active"
        - field: "email"
          operator: "is_null"
    actions:
      - type: "block"
        message: "激活状态的用户必须填写邮箱地址"
        severity: "error"

  - id: "auto_set_domain_status"
    name: "子领域状态跟随父领域"
    type: "calculation"
    bindings:
      - entity: "domain"
        lifecycle: ["after_update"]
        trigger_fields: ["status"]
    actions:
      - type: "cascade_update"
        target_entity: "sub_domain"
        target_filter:
          field: "domain_id"
          operator: "eq"
          value: "${trigger_record.id}"
        updates:
          field: "status"
          value: "${trigger_record.status}"
```

---

### FR-002: 工作流/业务流程引擎 (Workflow/BPM Engine) [Must]

- **描述**: 系统必须提供元数据驱动的业务流程引擎，支持在 YAML 中声明多步骤、多人协作的业务流程，包括人工任务、自动任务、条件分支、审批链、状态转换。
- **对标产品**: SAP Workflow + BPM、Palantir Process Orchestration、Salesforce Flow + Approval、D365 Business Process Flow + Power Automate、Appian Process Modeler
- **验收标准**:
  - 支持在 YAML 中声明流程定义（步骤、任务、转换条件、分配规则、截止时间）
  - 支持人工任务（Human Task）：任务分配给角色/用户/用户组、支持审批/驳回/转交
  - 支持自动任务（Auto Task）：调用 BO API 操作、发送通知、执行规则
  - 支持条件分支（Gateway）：基于规则引擎评估结果路由到不同步骤
  - 支持并行分支和合并
  - 支持子流程调用
  - 支持状态持久化和流程实例查询
  - 支持任务列表（我的待办/已办/我发起的）
  - 流程节点进入/离开事件触发通知
- **优先级**: Must
- **类型映射**: 业务需求 / 功能需求

```yaml
# 工作流 YAML 声明示例（目标形态）
workflows:
  - id: "enum_type_approval"
    name: "枚举类型审批流程"
    entity: "enum_type"
    start_condition:
      field: "mutability"
      operator: "eq"
      value: "locked"
    steps:
      - id: "submit"
        name: "提交审批"
        type: "human_task"
        assignee: "${trigger_user}"
        allowed_actions: ["submit"]
        transitions:
          - to: "review"
            condition: "always"

      - id: "review"
        name: "管理员审核"
        type: "human_task"
        assignee_expression: "${roles:admin}"
        allowed_actions: ["approve", "reject", "return"]
        deadline:
          duration: "48h"
          escalate_to: "${roles:super_admin}"
        transitions:
          - to: "approved"
            condition: "${action == 'approve'}"
          - to: "rejected"
            condition: "${action == 'reject'}"
          - to: "submit"
            condition: "${action == 'return'}"

      - id: "approved"
        name: "审批通过"
        type: "auto_task"
        actions:
          - type: "bo_update"
            entity: "enum_type"
            record_id: "${workflow.record_id}"
            updates:
              status: "approved"
          - type: "notify"
            template: "approval_passed"
        transitions: []

      - id: "rejected"
        name: "审批驳回"
        type: "auto_task"
        actions:
          - type: "notify"
            template: "approval_rejected"
        transitions: []

  - id: "role_permission_change"
    name: "角色权限变更流程"
    entity: "role"
    steps:
      - id: "request_change"
        name: "提交变更申请"
        type: "human_task"
        assignee: "${trigger_user}"
        allowed_actions: ["submit"]
        transitions:
          - to: "security_review"
            condition: "always"

      - id: "security_review"
        name: "安全审核"
        type: "human_task"
        assignee_expression: "${roles:security_officer}"
        allowed_actions: ["approve", "reject"]
        transitions:
          - to: "apply_changes"
            condition: "${action == 'approve'}"
          - to: "request_change"
            condition: "${action == 'reject'}"

      - id: "apply_changes"
        name: "应用变更"
        type: "auto_task"
        actions:
          - type: "bo_update"
            entity: "role"
            record_id: "${workflow.record_id}"
            updates: "${workflow.context.pending_changes}"
          - type: "notify"
            template: "permission_changed"
```

---

### FR-003: 事件驱动架构 (Event-Driven Architecture) [Must]

- **描述**: 系统必须引入事件总线机制，使 BO CRUD 操作自动产生事件，支持异步事件监听和处理，实现系统模块间的解耦通信。
- **对标产品**: SAP Event Mesh、Palantir Event-driven Streaming、Salesforce Platform Events + CDC、D365 Event Framework + Azure Service Bus
- **验收标准**:
  - BO 的 CRUD 操作自动发布标准事件（created / updated / deleted / associated / disassociated）
  - 支持在 YAML 中声明事件订阅者（handlers），绑定到特定实体的特定事件类型
  - 支持同步事件处理（拦截器管道内）和异步事件处理（独立队列）
  - 事件包含完整上下文（entity_type, record_id, changes, user_id, timestamp）
  - 支持事件重放和死信队列
  - 事件处理失败不影响主业务流程（异步模式下）
  - 前端可订阅实时事件（用于列表刷新、通知推送）
- **优先级**: Must
- **类型映射**: 解决方案需求 / 功能需求

```yaml
# 事件声明 YAML 示例（目标形态）
events:
  subscribers:
    - id: "audit_on_user_change"
      entity: "user"
      event_types: ["created", "updated", "deleted"]
      handler: "audit_handler"
      mode: "async"

    - id: "recalc_on_role_update"
      entity: "role"
      event_types: ["updated"]
      trigger_fields: ["permissions"]
      handler: "permission_recalc_handler"
      mode: "async"

    - id: "sync_on_enum_change"
      entity: "enum_value"
      event_types: ["created", "updated", "deleted"]
      handler: "enum_cache_invalidator"
      mode: "sync"
```

---

### FR-004: 环境/租户管理 (Environment/Tenancy) [Should]

- **描述**: 系统需要支持环境隔离（开发/测试/生产）和多租户（或产品版本）管理能力。
- **对标产品**: SAP BTP Subaccounts、Salesforce Sandboxes、D365 Environments、OutSystems LifeTime
- **验收标准**:
  - 支持多环境配置（development / staging / production）
  - 环境间 YAML 配置和数据的迁移工具
  - 支持环境级变量（数据库连接、API Key、特性开关）
  - 生产环境保护（禁止直接删除、修改保护）
  - 环境健康检查和状态监控
- **优先级**: Should
- **类型映射**: 解决方案需求

---

### FR-014: 技术ID策略与Business Key编码规则引擎 (ID Strategy & Business Key) [Must]

> **新增（2026-05-14）**: 基于 D365 AutoNumber、Salesforce Record ID/External ID、SAP CAP cuid/managed、Palantir Primary Key + RID 双标识体系对比分析

- **描述**: 系统必须提供可声明的技术ID策略和业务编码规则引擎。技术ID策略决定每个实体的主键生成方式（自增整数 vs UUID），Business Key 编码规则引擎支持在 YAML 中声明自动编码格式（序列号、日期、随机串、前缀的组合），在记录创建时自动生成业务标识，同时支持 External ID 标记用于 upsert 和外部系统匹配。
- **对标产品**: 
  - **D365/Power Platform AutoNumber**: 一类公民字段类型，格式占位符 `{SEQNUM:N}`, `{RANDSTRING:N}`, `{DATETIMEUTC:format}` + Seed + 数据库级唯一保证 → **行业最佳实践**
  - **SAP CAP cuid/managed Aspect**: `cuid` 提供 UUID PK + `managed` 提供审计字段，以 Aspect 形式复用 → **声明式复用模式**
  - **Salesforce Record ID + Auto Number + External ID**: 15/18-char 系统 ID + Auto Number 字段 + External ID 用于 upsert → **三标识分层模型**
  - **Palantir Primary Key + RID**: 用户定义 PK（建议有意义）+ 系统 RID → **双标识分离**
- **验收标准**:
  - **技术 ID 策略**:
    - 支持在 YAML 实体定义中声明 `id_strategy`：`auto_increment`（默认）| `uuid` | `custom`
    - `auto_increment` 策略使用数据库自增机制（SQLite AUTOINCREMENT / PostgreSQL SERIAL / MySQL AUTO_INCREMENT）
    - `uuid` 策略在 BO Framework 创建记录前自动生成 UUID 作为主键值
    - 支持全局默认策略配置 + 单实体覆盖
    - 与现有 `sql_adapters.py` 中的三种数据库适配器兼容
  - **Business Key 编码规则**:
    - 支持在 YAML 字段中声明 `business_key` 语义和 `auto_number_format` 格式
    - 格式占位符支持: `{SEQNUM:N}` 序列号（N位补零）、`{RANDSTRING:N}` 随机字母数字串、`{DATETIMEUTC:format}` UTC日期时间、字符串常量（如 `PO-`, `WID-`）
    - 序列号支持 Seed（起始值）配置和 `reset_cycle`（重置周期：never/daily/monthly/yearly）
    - 编码在记录创建时自动生成，数据库级保证唯一性
    - 编码字段在创建后自动变为只读（不可修改）
    - 格式支持两个序列号段（如 `{SEQNUM:4}-{SEQNUM:3}`）
  - **External ID**:
    - 支持在字段上标记 `external_id: true`
    - External ID 字段自动建立索引
    - upsert 操作支持通过 External ID 匹配现有记录
    - 每个实体最多支持 25 个 External ID 字段
- **优先级**: Must
- **类型映射**: 业务需求 / 功能需求 / 数据模型基础设施
- **来源**: 头部产品对比分析 + 用户指定新增

```yaml
# ID 策略与编码规则 YAML 声明示例（目标形态）

# === 全局 ID 策略（settings.yaml）===
id_strategy:
  default: "auto_increment"      # 全局默认：auto_increment | uuid
  global_prefix: ""              # 可选全局前缀

# === 实体级 ID 策略 + 业务编码 ===
entities:
  - id: "enum_type"
    name: "枚举类型"
    id_strategy: "auto_increment"  # 覆盖全局策略
    fields:
      - id: "code"
        name: "编码"
        type: "string"
        semantics:
          business_key: true       # 标记为业务键
        auto_number_format: "ENUM-{SEQNUM:4}"  # 自动编码格式
        # 生成: ENUM-0001, ENUM-0002, ENUM-0003...
        seed: 1
        ui:
          readonly: true           # 自动推导（business_key 字段创建后不可修改）

  - id: "purchase_order"
    name: "采购订单"
    id_strategy: "uuid"           # 使用 UUID 作为技术主键
    fields:
      - id: "po_number"
        name: "订单编号"
        type: "string"
        semantics:
          business_key: true
          external_id: true        # 标记为 External ID
        auto_number_format: "PO-{DATETIMEUTC:yyyyMM}-{SEQNUM:5}"
        # 生成: PO-202605-00001, PO-202605-00002...
        seed: 1
        reset_cycle: "monthly"     # 每月重置序号

      - id: "erp_ref_code"
        name: "ERP引用编码"
        type: "string"
        semantics:
          external_id: true        # 外部系统 ID，用于 upsert 匹配

  - id: "user"
    name: "用户"
    id_strategy: "auto_increment"
    fields:
      - id: "employee_no"
        name: "员工编号"
        type: "string"
        semantics:
          business_key: true
        auto_number_format: "EMP{SEQNUM:6}"
        # 生成: EMP000001, EMP000002...
        seed: 1000

      - id: "username"
        name: "用户名"
        type: "string"
        semantics:
          external_id: true        # 用于外部系统 upsert

# === UUID 策略时的实体 ===
  - id: "audit_log"
    name: "审计日志"
    id_strategy: "uuid"           # 高并发写入场景使用 UUID
    # 无需声明 business_key，主键本身就是 UUID
```

- **与现有 `semantics` 机制的集成**:

```yaml
# 已有 semantics.business_key 推导规则（engineering-guidelines.md）
# 当前: business_key: true → 自动 readonly: true
# 新增: business_key: true + auto_number_format → 自动生成编码
# 新增: external_id: true → 自动索引 + upsert 匹配

# 自动推导规则扩展:
# | semantics.business_key | auto_number_format  | → 创建时自动生成编码, readonly: true |
# | semantics.business_key | 无 auto_number_format | → 手动输入, readonly: true (创建后) |
# | semantics.external_id  | -                    | → 自动索引, upsert 可用 |
```

---

### FR-005: 外部系统连接器框架 (Connector Framework) [Should]

- **描述**: 系统需要建立可扩展的连接器框架，支持声明式集成外部数据源和系统。
- **对标产品**: Palantir 200+ Connectors、D365 Virtual Entities + 1000+ Connectors、Mendix REST Connectors + Event Broker
- **验收标准**:
  - 连接器抽象接口（BaseConnector）：connect / query / execute / disconnect
  - 内置连接器：REST API Connector、Database Connector、File Connector（CSV/Excel）
  - 支持在 YAML 中声明外部数据源和映射规则
  - 支持外部数据源与 BO 实体的字段映射
  - 连接器支持认证配置（OAuth2 / API Key / Basic Auth）
  - 连接测试和健康检查
  - 支持定时同步调度
- **优先级**: Should
- **类型映射**: 解决方案需求 / 外部接口需求

```yaml
# 连接器 YAML 声明示例（目标形态）
connectors:
  - id: "external_hr_system"
    name: "外部HR系统"
    type: "rest_api"
    config:
      base_url: "${env:HR_API_BASE_URL}"
      auth:
        type: "oauth2"
        token_url: "${env:HR_OAUTH_TOKEN_URL}"
        client_id: "${env:HR_CLIENT_ID}"
        client_secret: "${env:HR_CLIENT_SECRET}"
    mappings:
      - entity: "user"
        direction: "import"
        sync_schedule: "0 */6 * * *"
        field_mappings:
          - source: "employee_id"
            target: "username"
          - source: "full_name"
            target: "display_name"
          - source: "email_address"
            target: "email"
          - source: "department"
            target: "department_code"
```

---

### FR-006: 通知/消息服务 (Notification Service) [Should]

- **描述**: 系统需要提供统一的通知服务，支持多渠道消息推送和模板化管理。
- **对标产品**: SAP Alert Notification、Salesforce Notification Builder、D365 Power Automate Notifications
- **验收标准**:
  - 通知渠道至少支持：站内消息、邮件、Webhook
  - 支持 YAML 消息模板定义（支持变量插值）
  - 通知触发方式：事件驱动（订阅 FR-003 事件）、API 调用、规则触发
  - 站内消息支持已读/未读管理
  - 通知发送日志和失败重试
  - 用户级通知偏好设置（渠道开关、免打扰时段）
- **优先级**: Should
- **类型映射**: 功能需求

---

### FR-007: 流程监控与分析 (Process Monitoring) [Could]

- **描述**: 系统需要提供流程级别的监控、瓶颈分析、SLA 指标统计能力。
- **对标产品**: Appian Process Intelligence、SAP Process Visibility、D365 Process Mining
- **验收标准**:
  - 流程实例统计：总数、进行中、已完成、已终止、超时数
  - 任务统计：平均处理时间、各步骤耗时分布
  - SLA 指标：超时率、按时完成率
  - 瓶颈分析：识别耗时最长的步骤
  - 可视化仪表板
- **优先级**: Could
- **类型映射**: 功能需求 / 非功能需求

---

### FR-008: 国际化 (i18n) [Should]

- **描述**: 系统需要支持多语言，实现界面文本、字段标签、错误消息的国际化。
- **对标产品**: SAP @sap.i18n Text Pool、Salesforce Translation Workbench
- **验收标准**:
  - YAML 字段支持 `name_i18n` 多语言声明
  - 界面语言切换（中文 / 英文）
  - 错误消息国际化
  - 枚举值多语言显示
  - 语言包可扩展
- **优先级**: Should
- **类型映射**: 功能需求

---

### FR-009: DevOps/CI-CD 能力 [Could]

- **描述**: 系统需要支持自动化测试流水线、部署流水线、版本发布管理。
- **对标产品**: SAP CAP CI/CD Pipeline、OutSystems LifeTime、Mendix CI/CD
- **验收标准**:
  - 自动化测试流水线（单元测试 + 集成测试 + E2E）
  - YAML schema 变更自动验证
  - 部署脚本和环境配置
  - 版本号管理和发布日志
- **优先级**: Could
- **类型映射**: 解决方案需求

---

### FR-010: 沙箱/开发环境 [Could]

- **描述**: 提供独立的开发测试沙箱环境，支持数据隔离和安全实验。
- **对标产品**: SAP Dev Spaces、Salesforce Sandboxes
- **验收标准**:
  - 独立沙箱环境创建和销毁
  - 沙箱内数据与生产数据隔离
  - 沙箱环境配置独立管理
  - 沙箱使用配额管理
- **优先级**: Could
- **类型映射**: 解决方案需求

---

### FR-011: AI 辅助开发 [Could]

- **描述**: 引入 AI 辅助能力，支持智能配置建议、自然语言生成 YAML、问题自动诊断。
- **对标产品**: Mendix Maia、Salesforce Einstein GPT、OutSystems AI Mentor、SAP Joule
- **验收标准**:
  - YAML 配置智能补全和校验建议
  - 自然语言转换为 YAML 配置
  - 规则冲突检测和建议
  - 性能建议和优化提示
- **优先级**: Could
- **类型映射**: 功能需求

---

### FR-012: 数据血缘追踪 [Could]

- **描述**: 追踪数据的来源、流转路径和变更历史，支持影响分析和数据溯源。
- **对标产品**: Palantir column-level lineage、SAP Data Intelligence
- **验收标准**:
  - 数据创建来源记录（手动/导入/API/连接器同步）
  - 数据变更链路追踪（谁/何时/从什么改成什么）
  - 字段级血缘关系可视化
  - 影响分析：修改某字段可影响哪些下游
- **优先级**: Could
- **类型映射**: 非功能需求

---

### FR-013: 模板市场/组件复用生态 [Could]

- **描述**: 提供模板机制和组件共享市场，促进复用和生态建设。
- **对标产品**: Mendix Marketplace、OutSystems Forge、Appian AppMarket
- **验收标准**:
  - 模板创建和导出（YAML + 组件）
  - 模板导入和快速实例化
  - 模板版本管理
  - 模板分享和搜索
- **优先级**: Could
- **类型映射**: 功能需求

---

## 4. 非功能需求

### NFR-001: 规则引擎性能 [Must]

- **描述**: 规则评估不能显著增加 CRUD 操作延迟
- **测量**: 单次 CRUD 操作增加延迟 < 50ms（100 条规则以内）
- **优先级**: Must

### NFR-002: 工作流引擎可靠性 [Must]

- **描述**: 工作流状态持久化，服务重启后流程状态不丢失
- **测量**: 流程实例状态可在重启后完整恢复
- **优先级**: Must

### NFR-003: 事件处理吞吐量 [Should]

- **描述**: 异步事件处理能力满足当前系统的操作频率
- **测量**: 支持每秒 100 个事件的异步处理
- **优先级**: Should

### NFR-004: 向后兼容 [Must]

- **描述**: 新增架构能力不应破坏现有 API 和行为
- **测量**: 现有 86+ 核心测试在引入新能力后全部通过
- **优先级**: Must

### NFR-005: YAML Schema 一致性 [Must]

- **描述**: 新 YAML 声明格式必须与现有字段语义风格一致，遵循已有的命名约定
- **测量**: 通过 YAML Schema 验证器的自动校验
- **优先级**: Must

### NFR-006: 编码生成唯一性 [Must]

- **描述**: Business Key 编码必须在并发创建场景下保证全局唯一，不产生重复编码
- **测量**: 100 并发创建请求下，所有 business_key 字段值唯一
- **优先级**: Must

### NFR-007: 编码生成性能 [Should]

- **描述**: 编码生成不能显著增加记录创建延迟
- **测量**: 单次创建增加延迟 < 10ms（不含数据库写入时间）
- **优先级**: Should

---

## 5. 外部接口需求

### IF-001: 规则引擎 API

- **类型**: API
- **端点**: `POST /api/v2/rules/evaluate` - 触发规则评估
- **端点**: `GET /api/v2/rules?entity={entity_type}` - 查询实体关联规则
- **端点**: `POST /api/v2/rules/validate` - 校验规则定义
- **错误处理**: 返回规则评估结果列表，每个结果包含 rule_id / status / message

### IF-002: 工作流 API

- **类型**: API
- **端点**: `POST /api/v2/workflows/{workflow_id}/start` - 启动流程实例
- **端点**: `GET /api/v2/workflows/instances?assignee={user_id}&status={status}` - 查询流程实例
- **端点**: `POST /api/v2/workflows/instances/{instance_id}/tasks/{task_id}/complete` - 完成任务
- **端点**: `GET /api/v2/workflows/instances/{instance_id}/history` - 流程历史

### IF-003: 事件 WebSocket

- **类型**: WebSocket
- **入口**: `ws://<host>/api/v2/events?topics=user,role,enum_type`
- **交互**: 服务端实时推送 BO 变更事件给前端

### IF-004: 通知 API

- **类型**: API
- **端点**: `GET /api/v2/notifications?status=unread` - 获取未读通知
- **端点**: `POST /api/v2/notifications/{id}/read` - 标记已读
- **端点**: `POST /api/v2/notifications/send` - 发送通知

### IF-005: ID 策略与编码 API

- **类型**: API
- **端点**: `GET /api/v2/entities/{entity_type}/next-auto-number?field={field_id}` - 预览下一个编码（不消耗）
- **端点**: `POST /api/v2/entities/{entity_type}/reset-sequence?field={field_id}&seed={value}` - 重置编码序列
- **端点**: `GET /api/v2/entities/{entity_type}/auto-number-status` - 查询实体编码状态
- **错误处理**: 序列冲突返回 409，无效格式返回 400

---

## 6. 过渡需求

### TR-001: 规则引擎与现有拦截器体系的共存

- **描述**: 规则引擎引入时，现有的 ConstraintEngine 和拦截器体系保持不变。规则引擎作为独立的新层，通过事件订阅与拦截器管道对接。
- **策略**: 
  1. 规则引擎独立模块，不修改现有拦截器代码
  2. 通过新增 `RuleInterceptor` 桥接规则引擎到现有拦截器管道
  3. 逐步将现有硬编码校验逻辑迁移到 YAML 规则声明
- **回滚方案**: 移除 RuleInterceptor 即可恢复原有行为

### TR-002: 工作流引擎渐进引入

- **描述**: 工作流引擎自成一体的独立模块，不影响现有 CRUD 操作。
- **策略**:
  1. 工作流引擎作为独立模块开发
  2. 初期仅支持简单审批流（枚举类型审批）
  3. 逐步扩展支持更多流程模式
- **回滚方案**: 工作流模块可独立启停

### TR-003: 事件架构与请求响应模式共存

- **描述**: 事件架构为附加能力，不替代现有请求响应模式。
- **策略**: 事件发布在拦截器管道最后阶段触发，异步处理不影响主流程
- **回滚方案**: 关闭事件发布开关，系统回退到纯请求响应模式

### TR-004: ID 策略迁移

- **描述**: 引入 UUID 策略和 Business Key 编码时，现有 auto_increment 实体的数据不受影响。
- **策略**:
  1. 默认保持 `auto_increment`，现有实体无需任何修改
  2. 新实体可自由选择 `uuid` 策略
  3. Business Key 编码字段仅对新创建的记录自动生成，存量记录不受影响
  4. External ID 标记仅需 YAML 声明 + 数据库加索引，无数据迁移
- **回滚方案**: 恢复 `id_strategy` 为默认值、移除 `auto_number_format` 声明，不影响现有数据

---

## 7. 约束与假设

### 7.1 技术约束

- 后端语言：Python（Flask/Flask 扩展），不能改变现有技术栈
- 前端框架：Vue 3 + Element Plus + YonDesign，保持现有 UI 规范
- 数据库：现有 SQLite/PostgreSQL，规则引擎和工作流需要新增表
- YAML 解析：扩展 `yaml_loader.py`，保持解析器向后兼容

### 7.2 业务约束

- 所有新能力必须遵循 YAML 单一事实原则
- 新能力必须与现有 BO Framework 无缝集成
- 渐进式交付，每个 Phase 独立可验收
- 规则引擎优先于工作流引擎（用户明确指定）

### 7.3 假设

- 假设当前系统规模适合轻量级嵌入式实现，不需要独立的规则引擎服务器（Drools/JRules） - 来源: 推测
- 假设工作流引擎不需要完整的 BPMN 2.0 编辑器，YAML 声明即可满足需求 - 来源: 推测
- 假设事件驱动架构使用进程内事件总线（类似 Flask Signals），暂时不需要外部消息队列 - 来源: 推测

---

## 8. 优先级与里程碑建议

### 8.1 优先级排序

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-001 | 决策规则引擎 | Must | 用户指定最高优先级；规则是工作流的前置能力 |
| FR-014 | ID策略与Business Key编码 | Must | P0 数据模型基础设施；规则引擎/工作流/连接器的前置依赖 |
| FR-002 | 工作流/业务流程引擎 | Must | P0 结构性缺失，平台进化为"企业事务分析一体平台"的关键 |
| FR-003 | 事件驱动架构 | Must | P0 结构性缺失，系统解耦和实时通信的基础 |
| FR-004 | 环境/租户管理 | Should | 条件成熟后推进 |
| FR-005 | 连接器框架 | Should | 依赖事件架构（FR-003）成熟后 |
| FR-006 | 通知服务 | Should | 依赖事件架构（FR-003）和规则引擎（FR-001） |
| FR-007 | 流程监控 | Could | 依赖工作流引擎（FR-002）数据积累 |
| FR-008 | 国际化 | Should | 独立可并行推进 |
| FR-009 | DevOps/CI-CD | Could | 独立可并行推进 |
| FR-010 | 沙箱/开发环境 | Could | 依赖环境管理（FR-004） |
| FR-011 | AI 辅助 | Could | 依赖规则引擎和 YAML schema 成熟后 |
| FR-012 | 数据血缘 | Could | 依赖审计日志体系完善 |
| FR-013 | 模板市场 | Could | 依赖平台能力相对成熟后 |

### 8.2 建议里程碑

| 里程碑 | 范围 | 依赖 |
|--------|------|------|
| M1: Phase 19 | FR-001 决策规则引擎 | 无 |
| M2: Phase 20 | FR-014 ID策略与Business Key编码 + FR-002 工作流引擎 | FR-001（规则决策点） |
| M3: Phase 21 | FR-003 事件驱动架构 | 无（可并行） |
| M4: Phase 22-23 | FR-004 环境管理 + FR-005 连接器框架 | FR-003, FR-014（External ID） |
| M5: Phase 24-26 | FR-006 通知 + FR-007 监控 + FR-008 i18n | FR-002, FR-003 |
| M6: Phase 27-31 | P2 工程质量性要素 | 平台基本稳定后 |

---

## 9. 变更/设计提案 (RFC)

### 9.1 现状分析

- **当前架构**: 参见 [unified-metadata-api-architecture/spec.md](../unified-metadata-api-architecture/spec.md)，当前已完成 18 个 Phase，构建了完整的元数据驱动 CRUD 平台
- **当前痛点**: 
  1. 业务校验逻辑分散在拦截器和 API 代码中，不可声明、不可热更新
  2. 缺少多步骤协作的业务流程能力
  3. 系统为纯请求响应模式，模块间紧耦合
  4. 无环境隔离和外部系统集成能力
  5. 只有 auto_increment 整数 ID，不支持 UUID；无 Business Key 编码规则能力
- **相关代码路径**:
  - `meta/core/interceptors/` - 9 个拦截器（ConstraintEngine 在此之下）
  - `meta/core/bo_framework.py` - BO Framework 核心
  - `meta/core/yaml_loader.py` - YAML 解析器（需要扩展）
  - `meta/api/bo_api.py` - v2 API 统一入口
  - `meta/core/models.py` - 数据模型定义

### 9.2 目标状态

- **目标架构**:

```
┌─────────────────────────────────────────────────────────────────┐
│                  元数据驱动企业事务分析一体平台                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 6: 流程层 (Workflow Layer)                                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ WorkflowEngine │ TaskManager │ SLA Monitor │ Process History │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │                                      │
│  Layer 5: 规则层 (Rules Layer) [Phase 19 优先]                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ RulesEngine │ RuleRegistry │ RuleEvaluator │ RuleTracer     │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │                                      │
│  Layer 4: 事件层 (Event Layer) [Phase 21]                       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ EventBus │ EventPublisher │ EventSubscriber │ EventStore    │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │                                      │
│  Layer 3: 连接层 (Integration Layer) [Phase 23]                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ ConnectorRegistry │ RESTConnector │ DBConnector │ FileConn  │ │
│  └────────────────────────┬───────────────────────────────────┘ │
│                           │                                      │
│  Layer 2: 核心层 (现有 - 保持不变)                               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ BO Framework │ 9 Interceptors │ 4 Engines │ Enrichment      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Layer 1: 基础设施层 (新增)                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Environment Manager │ Notification Service │ i18n Service  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

- **关键变更**:
  1. 在现有拦截器管道之上新增 Rules Layer（规则引擎），通过 `RuleInterceptor` 桥接
  2. 新增独立的 Workflow Layer，不侵入现有 BO Framework
  3. 新增 Event Layer，作为系统解耦和异步通信基础设施
  4. 新增 Connector Layer，实现外部系统集成
  5. 基础设施层补充通知、i18n、环境管理

### 9.3 详细设计

#### 9.3.1 Phase 19: 决策规则引擎 (优先实施)

**模块设计**:

```
meta/rules/
├── __init__.py
├── rule_engine.py          # 规则引擎核心：加载、评估、缓存
├── rule_registry.py        # 规则注册表：从 YAML 解析规则定义
├── rule_evaluator.py       # 规则评估器：条件评估 + 动作执行
├── rule_interceptor.py     # 拦截器桥接：RuleInterceptor 接入管道
└── rule_types.py           # 规则类型模型：Rule / Condition / Action

meta/schemas/
└── rules_schema.yaml       # 规则 YAML schema 示例 / 模板
```

**数据模型**:

```python
@dataclass
class Rule:
    id: str
    name: str
    type: str                 # validation | calculation | decision
    bindings: List[RuleBinding]  # 绑定到实体和生命周期
    conditions: CompoundCondition
    actions: List[RuleAction]
    priority: int = 0         # 评估优先级
    enabled: bool = True

@dataclass
class RuleBinding:
    entity: str               # 绑定的 BO 实体
    lifecycle: List[str]      # before_create | after_update | before_delete ...
    trigger_fields: List[str] = None  # 触发字段（空 = 任意字段变更都触发）

@dataclass
class CompoundCondition:
    operator: str             # and | or
    conditions: List[Condition]

@dataclass
class Condition:
    type: str                 # field | query | expression
    field: str = None
    operator: str = None      # eq | ne | gt | lt | gte | lte | in | contains | is_null | exists
    value: Any = None         # 支持 ${input.xxx} 和 ${record.xxx} 变量
    query: Dict = None        # 子查询条件（用于 exists 操作）

@dataclass
class RuleAction:
    type: str                 # block | warn | set_field | cascade_update | notify
    message: str = None
    severity: str = "error"   # error | warning | info
    updates: Dict = None
```

**核心流程**:

```
CRUD 请求 → BO Framework
    → 拦截器管道 (现有)
        → [NEW] RuleInterceptor.on_before_create(entity, data)
            → RuleEngine.evaluate(entity, "before_create", context)
                → 加载 entity 相关的所有 enabled 规则
                → 按 priority 排序
                → 逐条评估 conditions
                → 收集所有触发的 actions
                → 返回评估结果（pass | warn | block）
            → 如果 block → 终止请求并返回错误
        → [现有拦截器继续执行...]
    → 数据持久化
        → [NEW] RuleInterceptor.on_after_update(entity, old, new)
            → RuleEngine.evaluate(entity, "after_update", context)
                → 执行 calculation 类型规则
```

**与现有 ConstraintEngine 的关系**:
- `ConstraintEngine` 处理 Schema 级别的约束（字段必填、类型校验、唯一性）
- `RuleEngine` 处理业务级别的规则（跨字段校验、条件计算、级联操作）
- 两者互补，不替代

#### 9.3.2 Phase 20: 工作流/业务流程引擎

**模块设计**:

```
meta/workflow/
├── __init__.py
├── workflow_engine.py       # 流程引擎核心
├── workflow_loader.py       # 流程 YAML 加载器
├── task_manager.py          # 任务管理器（TODO 列表）
├── process_instance.py      # 流程实例管理
└── workflow_models.py       # 数据模型

数据库新增表:
- workflow_definitions       # 流程定义
- workflow_instances         # 流程实例
- workflow_tasks             # 任务
- workflow_history           # 流程历史
```

**核心流程**:

```
启动流程:
    POST /api/v2/workflows/{id}/start
    → WorkflowEngine.start_workflow(workflow_id, context)
    → 创建 workflow_instance
    → 执行当前步骤（first step）
    → 如果是 human_task → 创建 task 分配给 assignee
    → 如果是 auto_task → 立即执行 actions → 自动流转到下一步

完成任务:
    POST /api/v2/workflows/instances/{id}/tasks/{task_id}/complete
    → TaskManager.complete_task(task_id, action, comment)
    → 根据 action 匹配 transition
    → 流转到下一个 step
    → 发布 StepCompleted 事件
```

#### 9.3.3 Phase 21: 事件驱动架构

**模块设计**:

```
meta/events/
├── __init__.py
├── event_bus.py             # 事件总线（基于 Flask Signals 或独立实现）
├── event_publisher.py       # 事件发布器（集成到 BO Framework）
├── event_subscriber.py      # 事件订阅管理器
└── event_models.py          # 事件数据模型
```

**与拦截器的集成点**:
在 `PersistenceInterceptor` 的 `after_*` 方法中触发事件发布。

#### 9.3.4 Phase 20-21: ID 策略与编码引擎 (FR-014)

**模块设计**:

```
meta/core/
├── id_generator.py          # ID 生成器核心（扩展现有 id 生成逻辑）
├── auto_number_engine.py    # Auto Number 编码引擎
└── sequence_manager.py      # 序列管理器（Seed + 重置周期 + 并发控制）

数据库新增表:
- auto_number_sequences       # 编码序列状态（entity_type, field_id, current_value, reset_cycle）
```

**数据模型**:

```python
@dataclass
class IdStrategyConfig:
    default: str = "auto_increment"   # 全局默认策略
    global_prefix: str = ""

@dataclass
class AutoNumberFormat:
    entity_type: str
    field_id: str
    format: str                # "PO-{DATETIMEUTC:yyyyMM}-{SEQNUM:5}"
    seed: int = 1
    reset_cycle: str = "never"  # never | daily | monthly | yearly

@dataclass
class AutoNumberSequence:
    entity_type: str
    field_id: str
    current_value: int
    last_reset_at: datetime
    reset_cycle: str
```

**核心流程**:

```
BO Framework create(entity_type, data):
    1. 检查 id_strategy
       ├── "auto_increment" → 不生成 id，由数据库自增
       ├── "uuid" → import uuid; data['id'] = str(uuid.uuid4())
       └── "custom" → 调用自定义生成函数

    2. 遍历 fields，检查 auto_number_format
       ├── 解析格式字符串（占位符替换）
       │   ├── "{SEQNUM:N}" → 从 DB auto_number_sequences 获取并递增
       │   ├── "{RANDSTRING:N}" → 生成随机字母数字串
       │   ├── "{DATETIMEUTC:format}" → 当前 UTC 时间格式化
       │   └── 字符串常量 → 直接拼接
       ├── 检查 reset_cycle，必要时重置 sequence
       ├── 数据库层面唯一约束保证不冲突
       └── 设置 data[field_id] = generated_code

    3. 返回生成的 id + business_key 编码
```

**序列号并发安全**:
- 使用数据库事务 + `SELECT ... FOR UPDATE` 锁定序列行
- 或使用数据库自增特性（每个 entity_type + field_id 一个独立序列表）
- 生成失败（唯一冲突）时自动重试（最多 3 次）

#### 9.3.5 Phase 22-31: 后续阶段

参见各 FR 的详细描述，各阶段独立设计文档将在启动时补充。

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **A: 嵌入式自研** | 零外部依赖、完全可控、与 YAML 模型无缝集成 | 开发工作量大、缺少社区生态 | **选中** |
| B: 集成 Drools (Python 桥接) | 成熟的规则引擎、DRL 语法丰富 | 引入 Java 依赖、运维复杂、与 YAML 模型脱节 | 否决（过重） |
| C: 集成 Camunda BPM | 完整的 BPMN 2.0 支持 | 引入 Java 依赖、部署运维复杂、过度设计 | 否决（过重） |
| D: 集成 Celery + Redis | 成熟的异步任务队列 | 引入中间件依赖、增加运维复杂度 | 暂缓评估 |

**选择 A 的理由**: 当前系统规模和定位适合轻量级嵌入式实现。YAML 已经建立了完整的元数据模型，规则引擎和工作流引擎自然扩展这个模型。未来规模增长后可考虑升级到方案 D。

### 9.5 实施与迁移计划

#### 实施顺序

1. **Phase 19**: 决策规则引擎（3-4周）
   - Week 1: `rule_engine.py` + `rule_registry.py` + YAML schema 设计
   - Week 2: `rule_evaluator.py` + `RuleInterceptor` + 接入拦截器管道
   - Week 3: rules API + 前端规则管理页面（规则列表/编辑/测试）
   - Week 4: 迁移现有硬编码校验 → YAML 规则 + 测试 + 文档

2. **Phase 20**: ID 策略与编码引擎（2周）
   - Week 1: `id_generator.py` + `auto_number_engine.py` + `sequence_manager.py` + 数据库序列表
   - Week 2: Business Key 编码集成到 BO Framework 创建流程 + 测试 + 文档

3. **Phase 21**: 工作流引擎（3-4周）
   - 依赖 Phase 19 完成
   - Week 1: 数据模型设计 + workflow_loader
   - Week 2: workflow_engine + task_manager
   - Week 3: 前端任务列表 + 审批页面
   - Week 4: 端到端测试 + 示例流程上线

4. **Phase 22**: 事件驱动架构（2-3周）
   - 可并行 Phase 19
   - Week 1: event_bus + event_publisher
   - Week 2: event_subscriber + 前端 WebSocket 对接
   - Week 3: 测试 + 文档

5. **Phase 23+**: 按依赖关系后续推进

#### 风险缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 规则引擎性能影响 CRUD | 高 | 规则编译缓存、条件短路优化、基准测试 |
| Auto Number 并发重复 | 高 | 数据库事务 + SELECT FOR UPDATE + 唯一约束 + 重试机制 |
| Auto Number 序列间隙 | 低 | 文档说明、业务接受间隙（与 D365 行为一致） |
| Auto Number 重置周期边界 | 中 | 原子性检查 + 分布式锁 |
| 工作流状态丢失 | 高 | 持久化到数据库、事务保证、定期备份 |
| YAML 配置膨胀 | 中 | 规则模板化、分文件管理、Schema 校验 |
| 事件积压 | 中 | 异步处理、死信队列、监控告警 |
| 与现有拦截器冲突 | 中 | RuleInterceptor 放在管道末尾、独立启停开关 |

#### 测试策略

- **单元测试**: 每个模块独立测试覆盖 > 80%
- **集成测试**: 
  - 规则引擎 + BO Framework 管道集成测试
  - 工作流引擎端到端流程测试
  - 事件发布订阅链路测试
- **回归测试**: 确保现有 86+ 核心测试全部通过
- **性能测试**: CRUD 延迟基准测试（引入规则前后对比）

#### 回滚方案

- 规则引擎：通过特性开关关闭 RuleInterceptor
- 工作流引擎：独立模块，移除 routing 即可
- 事件总线：关闭事件发布，系统回退到请求响应模式
- 所有新能力通过环境配置开关控制

---

## 10. 待定列表

| ID | 项目 | 缺失信息 | 下一步 |
|----|------|---------|--------|
| TBD-1 | 规则引擎条件表达式语法 | 是否需要支持自定义函数、是否需要数学计算 | 与用户讨论业务场景后确定 |
| TBD-2 | 工作流子流程嵌套深度 | 允许几层嵌套？ | 初期限制 1 层，后续评估 |
| TBD-3 | 连接器框架安全策略 | 外部系统凭证存储方案（环境变量 vs 加密数据库 vs Vault） | Phase 22 启动时确定 |
| TBD-4 | 事件总线持久化方案 | 是否需要外部消息队列（Redis/RabbitMQ） | Phase 21 实现时评估规模决定 |
| TBD-5 | 多租户数据隔离模式 | 数据库级隔离 vs Schema 级隔离 vs 行级隔离 | Phase 22 启动时确定 |
| TBD-6 | i18n 语言包管理方式 | 内置在 YAML vs 独立 JSON vs 外部翻译平台集成 | Phase 26 启动时确定 |
| TBD-7 | UUID 策略时的关联字段类型 | 关联字段在父实体 UUID 下应为 String(36) 而非 Integer | Phase 20 实现时处理 `sql_adapters.py` 外键类型推导 |
| TBD-8 | Auto Number 重置周期实现 | 跨月/跨年边界的高精度原子重置方案 | Phase 20 实现时设计 + 基准测试 |

---

> **引用文档**:
> - [unified-metadata-api-architecture/spec.md](../unified-metadata-api-architecture/spec.md) - 当前已完成架构（Phase 1-18）
> - 头部产品对比分析报告（2026-05-14，上一轮对话产出）
> - D365 AutoNumber 格式参考：`WID-{SEQNUM:5}-{RANDSTRING:6}-{DATETIMEUTC:yyyyMMddhhmmss}`