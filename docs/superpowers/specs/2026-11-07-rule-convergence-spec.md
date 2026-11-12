# Spec：规则化收敛（Rule Convergence）

> 文档编号: 待定 | 状态: 执行基线 v2.2 | 日期: 2026-11-07（v1.1：TBD 决议；v1.2：官方文档二次确认；v1.3：TBD-4 关闭，进入 M1 执行；v1.4：细化规则中心 FR-014/015/016 与单据级推导设计；v1.5：补规则试算 FR-017、配置发布流 FR-018，回写头部产品对标结论；v1.6：规则中心改为视图元数据驱动，新增 §9.6.9 与 TBD-15；v1.7：细化 FR-015 / IF-007 单据推导的可操作入口——规则中心「单据推导」页签 + 详情分区、参数与渲染契约、场景能力矩阵、实现差距与验收；v1.8：信封 v2 语义落地（`kind` / `factor_sources` / 全量规则明细）；v1.9：L1 落地——运行期节点字段、200 节点截断、前端规则全集表与场景/归属筛选；v2.0：规则语义范畴与类型分层（§12），二次确认修正 4 处，`rule_type` 改为三轴拆分；v2.1：新增 §13 元数据驱动与单一事实源（SSOT）规范，修正 FR-012 / FR-014 / §9.6.1 / §9.6.9；v2.2：澄清单据流语义本体为「数量关系」而非字段拷贝，新增 §14，修正 FR-006，确认不引入数量时段）
> 主题: 把仍硬编码在 Python 中的业务规则，按「元模型 / 配置 / 代码」三层归属收敛到规则模型
> 前置: [2026-10-02 规则模型 Spec](./2026-10-02-rule-model-spec.md)、[24 · 业务对象组织边界](../spec_权限体系升级/24_org_scope_business_object_phase2.md)
> 关联: `meta/core/rule_executor.py`、`meta/core/rule_provider.py`、`meta/core/hierarchy_loader.py`

---

## 1. 背景与目标

### 1.1 背景

平台已具备规则模型骨架：`RuleType` 8 类（validation / constraint / computation / state_transition / permission / trigger / derivation / default）、`RuleProvider` 统一读取、`RuleEngine` 执行、DEFAULT 的 first-match / `FILL_IF_EMPTY` / dry-run / 可回放日志均已落地。

但当前规则存在形式是**三层载体并存**：

| 层 | 载体 | 现状 |
|---|---|---|
| L1 元模型 | BO YAML（`rules` / `doc_effect` / `org_scope` / `state_transition` / `computed` / `state_field_policies`） | 覆盖部分域，缺编号、审批、层级等 |
| L2 配置 | DB 规则表（doc_flow / approval_rule / config_rule / number_sequence / data_permission_rules） | 有表，但对象注册与绑定关系仍写在代码 |
| L3 代码 | Python 常量字典 + guard service | 约 50 处层级映射 + 多域状态图/规则号写死 |

典型证据：

- 层级/维度映射在 `permission_dimension_engine.py`、`management_dimension_engine.py`、`condition_permission_service.py`、`chain_owner_resolver.py`、`dimension_scope_engine.py`、`value_help_providers.py` 重复 6+ 份；规则模型 Spec §7A.6 已登记「5 种值形状、约 50 处」。
- `sales_order_guard_service.SCHEDULE_TRANSITIONS`、`serial_number_service.TRANSITIONS` 用 Python 字典表达状态图，而 `RuleType.STATE_TRANSITION` 已存在却未接入。
- `document_number_service.NUMBERING` 把「对象 → 编号列 / 日期列 / 序列表」写死在代码里，新增单据需要改 Python。
- `document_approval_service.APPROVAL_TABLES`、`_AMOUNT_FIELDS` 把审批对象与金额优先级写死。
- `org_scope_validator.REQUIRED_ORG_SCOPE_BOS` 用 43 项硬编码清单做一致性校验。
- `field_policy_engine.SYSTEM_FIELDS` 用常量判断系统字段。

### 1.2 业务目标

1. **单一真源**：同一业务语义只有一处声明，消除多份映射漂移。
2. **可配置**：租户可调的策略（审批阈值、单据流、组织范围）不发版即可变更。
3. **可解释**：任何拒绝/默认/流转都能给出规则来源与原因。
4. **可回归**：每次收敛都可证明「行为等价」，不引入隐性变更。

### 1.3 涉众目标

| 涉众 | 目标 |
|---|---|
| 产品/实施 | 新流程、新编号、新审批不需要研发改代码 |
| 研发 | 新增 BO/维度只改声明；减少重复常量维护 |
| 运维/审计 | 能回答「为什么这条数据被拒绝/被默认成这个值」 |

---

## 2. 需求类型总览

| 类型 | 适用 | 证据来源 |
|---|---|---|
| 业务需求 | 是 | 平台化与多产品交付需要降低发版耦合 |
| 用户/涉众需求 | 是 | 实施配置化、研发减负、审计可解释 |
| 解决方案需求 | 是 | 三层归属 + 统一 Provider + Explain |
| 功能需求 | 是 | §3 FR-001 ~ FR-018 |
| 非功能需求 | 是 | §4 NFR-001 ~ NFR-006 |
| 外部接口需求 | 是 | §5 IF-001 ~ IF-008 |
| 过渡需求 | 是 | §6 TR-001 ~ TR-004 |

---

## 3. 功能需求

### FR-001 规则载体分层判定准则

- **描述**：系统 MUST 为每类业务逻辑定义唯一归属层：L1 元模型（结构/语义/默认/校验/状态图/组织边界）、L2 配置（租户可调策略）、L3 代码（算法/安全/集成）；并形成归属矩阵。
- **验收标准**：
  - 产出「逻辑类型 → 归属层 → 载体 → 读取入口」矩阵，覆盖本次盘点 10 类候选。
  - 新增逻辑的评审清单包含「是否可声明」检查项。
  - 安全边界（认证白名单、表达式白名单、审计哈希链、事务锁、SQL/CTE）明确列入 L3，不得配置化。
- **优先级**：Must
- **类型映射**：解决方案需求
- **来源**：本次规则模型审查

### FR-002 层级/维度单一真源

- **描述**：系统 MUST 将 `RESOURCE_TABLE_MAP` / `PARENT_FIELD_MAP` / `DISPLAY_FIELD_MAP` / `CODE_FIELD_MAP` / `CHILD_TYPE_MAP` / `HIERARCHY_CHAIN` 等映射收敛为单一声明源，`hierarchy_loader` 作为唯一读取入口。
- **验收标准**：
  - `permission_dimension_engine`、`management_dimension_engine`、`condition_permission_service`、`chain_owner_resolver`、`dimension_scope_engine`、`value_help_providers` 不再各自定义同名映射。
  - 运行时映射值与旧常量逐项相等（等价性测试）。
  - 层级深度不写死：`dimension_levels` 声明 `level_type / parent_level / scope_anchor / owner_field`，`profile` 只决定默认深度（默认 4 层，完整 6 层）。
  - 数据授权只认 `scope_anchor=true` 的层级；展示层级不授予数据访问权。
  - 新增层级/维度只改声明，不改 Python。
- **优先级**：Must
- **类型映射**：解决方案需求
- **来源**：规则模型 Spec §7A.6；本次审查 P0-1

### FR-003 组织边界清单推导化

- **描述**：系统 MUST 以「扫描全部 BO 推导候选 + 显式豁免清单」替代 `REQUIRED_ORG_SCOPE_BOS` 硬编码清单；豁免项进入 YAML 并带理由。
- **验收标准**：
  - 新增 BO 未声明 `org_scope` 时，一致性测试仍能报 `ORG_SCOPE_UNDECLARED`。
  - 豁免项只能通过声明文件添加，且必须填写理由。
  - Python 中不存在 43 项对象清单。
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：本次审查 P0-2

### FR-004 状态机声明化

- **描述**：系统 MUST 先将 `sales_order_schedule` 与 `serial_number` 的状态图迁移到 BO YAML `state_transition`；guard service 仅保留副作用与跨字段复杂校验。
- **验收标准**：
  - 新旧状态图逐项等价（合法流转集合、终态、不可回退）。
  - 非法流转的错误码与用户提示保持不变。
  - 新增状态/流转只改 YAML。
  - 错误响应继续携带规则号（如 `R-SCH-9`）。
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：`sales_order_guard_service.py:251`、`serial_number_service.py:84`

### FR-005 审批注册表与金额优先级元数据化

- **描述**：系统 MUST 将 `APPROVAL_TABLES`（审批对象→表）与 `_AMOUNT_FIELDS`（金额取值优先级）改为元数据/规则表驱动。
- **验收标准**：
  - 新增审批对象零代码改动。
  - 金额字段优先级可配置，默认顺序与旧实现一致。
  - 审批规则读取统一经 RuleProvider facade（见 FR-010）。
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：`document_approval_service.py:31-39`、`v178__approval_rule_model.py`

### FR-006 单据流规则数据化

- **描述**：系统 MUST 将单据流业务规则作为数据/种子维护，迁移脚本只负责建表与基线数据，不得继续把新增业务流写进 Python 迁移。
- **语义本体**：单据流的本体是**基于数量的上下游对象关系**——上游行按未结量向下游分批派生，上游累计下游消耗量；字段拷贝只是派生时的目标字段填充动作，不是关系本体。详见 §14。
- **验收标准**：
  - 新增一条单据流不需要发版（通过配置数据完成）。
  - `v214` / `v215` / `v222` 已承载的规则行为保持不变。
  - CI 增加静态守卫，禁止在迁移文件中新增业务流分支。
  - 同一源行 MUST 支持分批派生（多次调用）；任意时刻累计消耗（active 正向 − active 红字）MUST NOT 超过源行数量。
  - 字段映射链 MUST NOT 覆盖目标数量字段；目标数量由派生引擎按派生量显式写入。
- **优先级**：Should
- **类型映射**：过渡需求 + 功能需求
- **来源**：`meta/migrations/v214/v215/v222`、`doc_flow_rule_store.py`

### FR-007 编号绑定 YAML 化

- **描述**：系统 MUST 将 `NUMBERING`（对象→编号列/日期列/序列/作用域）迁入 BO YAML `numbering` 声明；`document_number_service` 只读取声明。
- **验收标准**：
  - 5 个现有单据取号结果逐项相等（前缀、日期分段、序列来源）。
  - 新增单据只改 YAML，不改 Python。
  - 加载期校验 `no_field` / `date_field` 必须存在于 BO 字段。
- **优先级**：Must（低风险优先）
- **类型映射**：功能需求
- **来源**：`document_number_service.py:13-40`

### FR-008 系统字段策略推导

- **描述**：系统 MUST 用 `MetaField.system` 或 `field_policy` 元数据替代 `field_policy_engine.SYSTEM_FIELDS` 常量。
- **验收标准**：
  - 现有系统字段行为（隐藏/只读/必填）不变。
  - 新增系统字段不需要修改引擎代码。
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：`field_policy_engine.py:82-96`

### FR-009 业务映射常量配置化

- **描述**：系统 SHOULD 将以下映射改为 `control_parameter` 或 YAML `mappings`：税率/税务处理取值、付款条件基准日期字段、预留需求数量来源、承诺策略、采购申请行类型映射。
- **验收标准**：
  - 映射变更不需要发版。
  - 默认值与旧常量逐项相等。
  - 加载期校验 key 合法、无重复、无未知枚举。
- **优先级**：Could
- **类型映射**：功能需求
- **来源**：`tax_guard_service.py:31-34`、`payment_term_schedule_service.py:148`、`inventory_reservation_service.py:78`、`commitment_policies.py:26`、`requisition_po_conversion.py:32`

### FR-010 统一 RuleProvider facade

- **描述**：系统 MUST 扩展规则读取入口，使 YAML 规则与 DB 规则（doc_flow / approval / config_rule）对调用方透明。
- **验收标准**：
  - 业务调用方不直接 import 各域 store。
  - 新增规则载体时调用方零改动。
  - 静态守卫禁止在业务代码中直接遍历 `meta_obj.rules`（豁免清单除外）。
- **优先级**：Should
- **类型映射**：解决方案需求
- **来源**：`rule_provider.py`、`doc_flow_rule_store.py`、`permission_rule_v2_dao.py`

### FR-011 统一 explain / dry-run

- **描述**：系统 SHOULD 提供统一规则解释接口，至少覆盖：默认值（已有）、权限拒绝、状态流转拒绝、审批命中。
- **验收标准**：
  - 返回 `rule_id` / 来源载体 / 命中或拒绝原因 / 因子快照 / 耗时。
  - 解释过程不落库、不改变数据。
  - 权限与状态流转的拒绝原因可从接口获得，而不是只能查日志。
- **优先级**：Should
- **类型映射**：外部接口需求
- **来源**：DEFAULT dry-run 已落地；权限/状态机缺失

### FR-012 加载期一致性校验

- **描述**：系统 MUST 为每个规则域提供加载期校验器（仿 `org_scope_validator` V1-V6）。
- **验收标准**：
  - 编号：字段存在、序列存在、日期字段类型合法。
  - 状态机：无孤儿状态、无不可达状态、终态不可出边（除显式声明）。
  - 审批：对象/表存在、金额字段存在。
  - 映射：key 合法、无重复、无未知枚举。
  - 视图元数据闭合：`rule_center_view.yaml` 的 `sources` 与 `RuleCatalogService.SOURCES` MUST 双向等值；`trace.scenarios` ⊆ `TRACE_SCENARIOS`；`trace.factor_keys` ⊆ 因子轴声明；`filter_options` 值域封闭（规则见 §13.4）。
  - 描述符必填：`RuleDescriptor.rule_key / source / name` 非空，`rule_type` 属于已声明白名单，`source_tags ⊆ 来源标签集合`（契约见 §13.2）。
  - 非法声明在启动或 CI 阶段失败，错误码稳定；请求期非法筛选值返回 400（`RULE_FILTER_UNKNOWN_VALUE`），不得静默返回空列表。
- **优先级**：Must
- **类型映射**：非功能/功能
- **来源**：`org_scope_validator.py` 已验证的模式

### FR-013 静态守卫与等价性回归

- **描述**：系统 MUST 为每次收敛提供「新旧逐项相等」的等价性测试，并增加静态守卫防止回潮。
- **验收标准**：
  - 每个迁移项都有等价性用例（运行时值 vs 旧常量），不能只依赖「测试通过」。
  - 静态守卫能拦截：新增扁平映射、重复常量、迁移中写业务流分支。
  - 统一通过 `python d:\filework\test.py` 执行。
- **优先级**：Must
- **类型映射**：非功能需求
- **来源**：规则模型 Spec §7A.6 的验证方法

### FR-014 规则中心（统一目录 + 配置入口）

- **描述**：系统 MUST 提供统一的「规则中心」页面入口，聚合展示、查询、管理现有规则，解决「规则散落在 YAML、DB 表、代码常量中，实施与研发无法一眼看全」的问题。
- **聚合范围（一期）**：

| # | 来源 | 载体 | 可配置性 |
|---|---|---|---|
| 1 | BO 元模型 `rules`（default / validation / constraint / computation / trigger / derivation） | L1 YAML | 只读 |
| 2 | 单据流 `doc_flow_rule` | L2 DB（app.yaml 声明 + 运行态 status） | 只读（status 二期可改） |
| 3 | 审批策略 `approval_policies` / `_conditions` / `_steps` | L2 DB | 只读（二期提供编辑器） |
| 4 | 控制参数 `control_parameter_defs` / `control_parameter_values` | L2 DB（已 BO 化） | **可编辑**（复用通用 BO 表单） |
| 5 | 行类型 `line_types` / `line_type_assignments` | L2 DB（已 BO 化） | **可编辑**（复用通用 BO 表单） |
| 6 | 状态机 / 编号声明（来自 BO YAML） | L1 YAML | 只读 |

- **验收标准**：
  - 规则列表可按「域 / 作用对象 / 规则类型 / 载体 / 可配置性 / 状态 / 关键词」筛选与分页。
  - 每条规则展示：`rule_key`、名称、类型、载体、作用对象、适用因子（org / document_type / line_type / item_group）、生效范围、状态、更新时间。
  - 可编辑规则在 2 次点击内进入现有 BO 编辑面；只读规则展示声明原文（YAML 片段或表行快照）。
  - 写操作前 MUST 调用校验/dry-run；非法值即时拒绝，不允许「保存后运行时才报错」。
  - 目录数据 MUST 与运行时同源（读取 `RuleProvider` 与各域 store），不允许维护第二份规则清单。
  - 权限码使用双段式并在 `permissions` 表真实存在（见 §9.6.5）。
  - **页面由视图元数据驱动**：页签、列、筛选、行操作、详情分区 MUST 来自 `meta/schemas/rule_center_view.yaml`（设计见 §9.6.9）；Vue 组件内不得硬编码页签名或列 key。验收以「只改 YAML 即可增删页签、列与筛选」为准。
  - **筛选项取值不得手写**：`filter_options` 只允许两种来源——静态封闭值域（如 `configurable` / `status`），或服务端按目录声明派生（如 `source` / `rule_type` / `domain`）；YAML 不得内联与代码重复的业务枚举（见 §13.3 F-13-03）。
  - **前端零业务常量**：`RuleCenterPage.vue` / `RuleTracePanel.vue` 只保留通用交互动词；来源名、列标签、动作名、决策文案、试算提示、`source → 目标表` 映射 MUST 由服务端元数据下发，兜底配置不得包含业务取值（见 §13.3 F-13-05 / F-13-07）。
  - **可编辑目标由服务端下发**：`RuleDescriptor.links` 为唯一来源，前端不得维护 `TARGET_BY_SOURCE` 之类的第二份映射（见 §13.2）。

- **优先级**：Should
- **类型映射**：功能需求
- **来源**：IF-004 原「二期」占位；本次规则模型审计发现规则来源 6 类、调用点覆盖不均

### FR-015 单据级规则推导追踪

- **描述**：系统 MUST 在业务单据详情页提供「规则推导」分区（页签），展示当前单据相关规则的判定过程，回答「这个值/这个状态/这个审批是谁决定的」。
- **覆盖场景（按接入程度渐进）**：

| 场景 | 推导内容 | 一期来源 |
|---|---|---|
| `default` | 字段默认值为何被填充 / 为何跳过 | `rule_explainer` |
| `control_parameter` | 命中哪个参数定义与取值、四维因子、是否回落默认值 | `ControlParameterResolver` |
| `line_type` | 行类型来源（assignment / default / missing） | `LineTypeResolver` |
| `approval` | 是否需审批、命中策略、金额分段、审批链 | `DocumentApprovalResolver` |
| `state_transition` | 允许/拒绝的目标状态及声明来源 | `state_machine_loader` |
| `doc_flow` | 上游/下游派生关系与规则 | `doc_flow_rule_store` |

**入口（v1.7 细化）**

| 入口 | 声明处 | 记录来源 | 适用 |
|---|---|---|---|
| A 单据详情「规则推导」分区 | `ui_view_config.detail.rule_trace` | 当前记录 id 自动带入 | 看「这张单」 |
| B 规则中心「单据推导」页签 | `rule_center_view.yaml` 的 `tabs[trace]` | 手输 `object_type` + `record_id` | 跨 BO 排查 / 无详情页的 BO |

- 两个入口 MUST 复用同一接口（IF-007）与同一渲染组件 `RuleTracePanel.vue`，差异仅在外壳与参数来源；禁止第二套渲染逻辑。
- 必填：`object_type`（须在 `registry` 已注册）、`record_id`（存在且在读取维度范围内）。
- 可选：`scenarios`（缺省 6 类全量）、`codes[]`（控制参数场景必需，去重后 ≤20）、`dims`（`org_id / document_type_id / line_type_id / item_group_id`，缺省由单据字段回填）、`from_state / to_state`。
- 字段映射、决策徽标、空态文案由视图元数据声明（§9.6.9 `trace.decisions`），不写在组件里。

- **验收标准**：
  - 详情页新增「规则推导」分区，按决策时间线展示；每条含场景、规则 ID、载体、因子快照、候选集、命中/未命中原因、结果、耗时。
  - 推导为只读，MUST NOT 落库、MUST NOT 触发业务副作用；提供「重新推导」按钮。
  - 未接入场景返回 `decision = "not_instrumented"` 并说明原因，不得显示空白或伪装成功。
  - 推导结果与写入路径同源（同一 Provider / Resolver），并与最近一次实际落库结果可对照。
  - （v1.7）两个入口 MUST 均可实际点击到达并产出结果；仅后端接口可用不算交付完成。
  - （v1.7）卡片 MUST 展示服务端 `decision` / `reason` / `elapsed_ms`；前端不得按场景名自行推断结果或本地重算候选。
  - （v1.7）`factors` 中未提供的维度显示「未提供」，MUST NOT 用 0 / 空串 / 默认值静默补位（与 FR-016 同口径）。
  - （v1.7）控制参数场景未给 `codes` 时显示「需选参数」引导；行类型场景缺 `document_type_id` 时显示补全提示，均不得空表静默。
  - （v1.7）未接入场景（validation / numbering）不出现在场景选择器中，也不展示伪造结果。
  - （v1.7）无 `rule_center:rule_center_trace` 时 A 入口不渲染分区、B 页签不可见；服务端返回 403，不得用伪空态掩盖。
  - 追踪受单据数据权限约束；敏感字段按字段策略脱敏。
  - 一期不新增持久化表；二期如需事后审计再评估 `rule_trace` 表（需 DDL 审批）。

- **优先级**：Should
- **类型映射**：功能需求
- **来源**：NFR-004；本次审计发现 control_parameter / line_type 的 explain 形状不统一、无单据级入口

### FR-016 规则因子完整性治理

- **描述**：系统 MUST 治理「因子少传导致细粒度配置静默失效」的问题：控制参数解析必须显式声明维度集合，行类型解析必须走统一 Resolver，规则中心提供因子覆盖健康视图。
- **验收标准**：
  - `resolve / resolve_many` 调用方 MUST 显式传入 `dims`；空 dims 仅允许声明为全局参数（`scope: global`），否则开发期告警。
  - 行类型解析统一经 `LineTypeResolver`；禁止在业务流程中硬编码行类型 code（迁移期豁免清单需登记理由）。
  - 规则中心「健康检查」展示：调用点因子覆盖矩阵、未被引用的规则、静默回落次数（按 explain 采样）、硬编码残留清单。
  - 新增控制参数或行类型规则时，加载期校验覆盖维度完整性。

- **优先级**：Should
- **类型映射**：功能需求
- **来源**：2026-11-07 规则模型通盘审计（8 个控制参数接入点中仅 1 个用满四维；行类型统一 Resolver 仅 1 处生产调用）

### FR-017 规则试算（what-if）

- **描述**：规则中心 MUST 提供「试算」能力：给定一组因子快照（可附单据），返回该场景下的候选集、命中规则、最终值与解释，用于配置变更前预判，不落库、不改数据。
- **验收标准**：
  - 输入：`scenario` + 因子（`org_id / document_type_id / line_type_id / item_group_id`）+ 可选 `record_id`（用于回填因子与继承单据上下文）。
  - 输出：与 IF-003 同构的信封 + `candidates[]`（按 `specificity_rank` 降序）+ `final`（命中值或 `default_value` 及其来源）。
  - 支持对比模式：一次返回 `baseline`（当前生效配置）与 `draft`（草稿配置）的试算结果，差异字段高亮。
  - 试算 MUST 与运行时同源（同一 Resolver / Provider），MUST NOT 写库、MUST NOT 触发业务副作用。
  - 未接入场景返回 `decision=not_instrumented`，禁止返回推测值。
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：对标 Oracle AME Test Workbench、ServiceNow Decision Table 模拟；配套 FR-014 规则中心

### FR-018 配置发布流

- **描述**：可配置规则（控制参数 / 行类型）的变更 MUST 经「草稿 → 校验 → 发布 → 生效」流程，编辑动作不得直接改变生产解析结果。
- **验收标准**：
  - 状态机：`draft`（不参与解析）→ `validated`（试算与加载期校验通过）→ `active`（参与解析）；`inactive` 为停用终态。
  - 发布 MUST 记录变更摘要（操作人、时间、变更前后值、校验结论），可查询历史；不新增表时写入 `audit_log`（`biz_type=rule_config`）。
  - 回滚 = 将上一版本重新置为 `active`，不物理删除历史记录。
  - 草稿态对业务解析零影响；同一规则同一时刻最多一个 `active` 版本。
  - 发布动作需 `rule_center:rule_center_write` 且通过对应 BO 的写权限校验。
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：对标 Oracle Sandbox Publish、SAP 传输请求、NetSuite SDF 发布；配套 FR-014

---

## 4. 非功能需求

### NFR-001 行为等价

- **描述**：除显式声明的语义变更外，收敛前后运行时输出、错误码、排序、默认值必须一致。
- **度量**：每个迁移项提供逐项比对用例；差异数为 0。
- **优先级**：Must

### NFR-002 可灰度、可回滚

- **描述**：每个域支持独立开关；回滚不依赖数据回滚。
- **度量**：关闭声明即回到旧代码路径；单域回滚不影响其他域。
- **优先级**：Must

### NFR-003 性能

- **描述**：元数据在加载期解析并缓存，运行期不得重复解析 YAML；读路径不得新增 N+1 查询。
- **度量**：与基线相比，列表/详情 P95 延迟增幅 ≤ 5%；加载时间增幅 ≤ 10%。
- **优先级**：Must

### NFR-004 可解释

- **描述**：规则命中/拒绝必须能给出规则 ID、载体、原因。
- **度量**：FR-011 接口覆盖四类场景；日志可回放。
- **优先级**：Should

### NFR-005 安全边界不配置化

- **描述**：认证白名单、表达式白名单、审计哈希字段、事务/锁、SQL 生成保持代码实现。
- **度量**：代码评审清单 + 静态守卫白名单。
- **优先级**：Must

### NFR-006 可测试

- **描述**：每个新声明块必须有正例、负例、加载期校验用例。
- **度量**：新增声明块的测试覆盖率 ≥ 80%；负例覆盖主要错误码。
- **优先级**：Must

---

## 5. 外部接口需求

### IF-001 元模型声明接口

- **类型**：元模型加载
- **入口**：BO YAML 顶层新增/复用 `numbering`、`approval`，复用 `state_transition`、`org_scope`
- **交互**：`yaml_loader` 解析 → `MetaObject` 字段 → 加载期校验器
- **错误处理**：非法声明返回稳定错误码，启动/CI 失败
- **来源**：FR-004/005/007

### IF-002 规则读取 facade

- **类型**：内部 API
- **入口**：`RuleProvider.get_rules / get_enabled_rules / get_rules_by_type`
- **交互**：屏蔽 YAML 与 DB 载体差异
- **错误处理**：载体不可用时降级并告警
- **来源**：FR-010

### IF-003 规则解释接口

- **类型**：HTTP API
- **入口**：`POST /api/v2/bo/<object_type>/rules/explain`
- **请求/响应**：请求含 `scenario`、动作/字段/因子快照或 `record_id`（由服务端回填因子）；响应统一 8 字段信封，并含 `steps[]` / `candidates[]`
- **场景**：一期 `default / permission / state_transition / approval`；二期扩展 `control_parameter / line_type / doc_flow / validation`
- **错误处理**：不落库；对象/动作/场景非法返回 400；未接入场景返回 `decision=not_instrumented`
- **来源**：FR-011、FR-015

### IF-004 规则中心页面入口

- **类型**：UI
- **入口**：系统管理 → 规则中心（菜单 `rule-center`）；单据详情 → 「规则推导」分区
- **交互**：全量规则检索/筛选/详情；可配置规则跳转现有 BO 编辑面；只读规则展示声明原文；单据详情按需推导，不落库
- **错误处理**：写操作前校验/dry-run；非法值即时拒绝；未接入场景显式标注
- **来源**：FR-014、FR-015

### IF-005 迁移与校验命令

- **类型**：CLI / 测试入口
- **入口**：迁移脚本 `migrate / verify / rollback`；测试 `python d:\filework\test.py`
- **交互**：幂等；支持 dry-run
- **错误处理**：失败回滚事务
- **来源**：FR-012/013

### IF-006 规则目录查询接口

- **类型**：HTTP API
- **入口**：`GET /api/v2/rules`、`GET /api/v2/rules/<rule_key>`
- **请求/响应**：支持 `domain / bo / rule_type / layer / configurable / status / q / page / page_size`；响应为 §9.6.1 的 `RuleDescriptor` 列表与总数
- **错误处理**：只读；未知 `rule_key` 返回 404；无权限返回 403
- **来源**：FR-014

### IF-007 单据规则推导接口

- **类型**：HTTP API
- **入口**：`GET /api/v2/bo/<object_type>/<record_id>/rule-trace`
- **查询参数（v1.7 细化）**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `scenarios` | csv | 否 | 6 类场景任意子集，缺省全量；含非法值 → 400 |
| `codes` | csv | 否 | 控制参数参数码，trim + 去重后 ≤20；缺省时该场景 `skipped / no_codes_requested` |
| `org_id` / `document_type_id` / `line_type_id` / `item_group_id` | int | 否 | 显式因子，优先于单据字段回填 |
| `user_id` / `action_id` | int / str | 否 | 权限场景上下文；缺省当前登录用户 + `read` |
| `from_state` / `to_state` | str | 否 | 状态流转场景；`from_state` 缺省取单据状态字段 |

- **响应**：顶层 `trace_id`（UUID，仅日志关联）、`object_type`、`record_id`、`factors`、`scenarios[]`；每条为统一信封 `ok / scenario / decision / rule_id / source / reason / factors / elapsed_ms`，可选 `detail`（`control_parameter` 给 `codes / missing / chain[]`，`line_type` 给命中行快照，`doc_flow` 给声明列表）
- **`decision` 取值**：`hit / resolved / allow / deny / missing / skipped / not_instrumented`；由服务端返回，前端 MUST NOT 自行推断
- **错误处理**：只读、不落库；`object_type` 未注册或单据不存在 / 越维度 → 404 `NOT_FOUND`（不暴露记录存在性）；`scenarios` / 参数非法 → 400；无 `rule_center:rule_center_trace` → 403；单场景异常 → 200 且该 `step.ok=false`，不影响其他场景
- **来源**：FR-015

### IF-008 规则试算接口

- **类型**：HTTP API
- **入口**：`POST /api/v2/rules/simulate`
- **请求/响应**：请求含 `scenario`、`factors`（`org_id / document_type_id / line_type_id / item_group_id`）、可选 `record_id`、可选 `codes[]`（控制参数批量）、`config_mode`（`baseline` / `draft` / `both`）；响应为 IF-003 同构信封 + `candidates[]` + `final`，`config_mode=both` 时附 `baseline` / `draft` 两组结果
- **错误处理**：只读、不落库；因子类型或长度非法返回 400；无 `rule_center:rule_center_read` 返回 403；未接入场景返回 `decision=not_instrumented`
- **来源**：FR-017

---

## 6. 过渡需求

### TR-001 分波次切换

- **描述**：按 M1（低风险）→ M2（流程）→ M3（权限层级）分波次，每波独立验收。
- **策略**：每波先只读双跑，再切换读取入口。
- **回滚**：单域开关关闭即回旧路径。

### TR-002 影子读取与双跑

- **描述**：切换前同时计算旧常量与声明结果，差异写告警日志。
- **策略**：至少运行一个回归周期，差异为 0 后切换。
- **回滚**：停止影子读取即可。

### TR-003 兼容期

- **描述**：旧常量保留一个版本作为 fallback，声明缺失时回退并告警。
- **策略**：fallback 只读、不写；下个版本删除。
- **回滚**：恢复旧读取入口。

### TR-004 数据不变

- **描述**：本次收敛不修改业务数据、不删列、不改索引。
- **策略**：只改读取与校验路径。
- **回滚**：无需数据回滚。

---

## 7. 约束与假设

### 7.1 技术约束

- 复用现有 `RuleType` 8 类，**不新增 `RuleType` 枚举值**（状态图用 `STATE_TRANSITION`）；语义扩展一律以正交属性承载（`semantic_class` / `semantic_type` / `constraint_kind` / `hit_policy` / `reference`），见 §12。
- 规则中心列表的 `rule_type` 混入来源标签（`control_parameter` / `doc_flow` / `approval` / `line_type_assignment`），属**展示层兼容字段**，不得回写为 `RuleType`；目标契约见 §12.5。
- 元数据在加载期完成解析与校验，运行期零 YAML 解析。
- 数据库为 SQLite，规则表变更走迁移；禁止直读写 `meta/architecture.db`。
- 测试唯一入口为 `python d:\filework\test.py`。

### 7.2 业务约束

- 安全边界不配置化。
- 不改变现有 API 契约与前端路由。
- 不在本轮引入规则在线热更新与多租户隔离。

### 7.3 假设

- 假设 1：现有常量即为当前正确行为（已由测试与线上行为验证）——来源：已验证。
- 假设 2（已定，TBD-4）：4 层与 6 层不是二选一。层级深度由 `dimension_levels` 声明，默认 profile=4；授权只认 `scope_anchor` 层级。已确认保持现状：`sub_domain` 为授权叶子，`service_module` 不升锚点。
- 假设 3（已定，TBD-2/TBD-3）：状态主图与编号绑定放 L1；租户可配的仅限原因/子状态/门槛与编号区间参数。

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|---|---|---|---|
| FR-001 | 分层判定准则 | Must | 后续所有工作的判据 |
| FR-002 | 层级/维度 SSOT | Must | 重复最多、漂移风险最高 |
| FR-003 | 组织清单推导化 | Should | 影响面小，但防止新增 BO 漏配 |
| FR-004 | 状态机声明化 | Must | 规则类型已具备，收益直接 |
| FR-005 | 审批注册表元数据化 | Should | 减少发版耦合 |
| FR-006 | 单据流数据化 | Should | 已有 store，只差约束 |
| FR-007 | 编号 YAML 化 | Must | 低风险、可作试点 |
| FR-008 | 系统字段推导 | Should | 减少引擎分支 |
| FR-009 | 业务映射配置化 | Could | 收益分散，后置 |
| FR-010 | 统一 Provider | Should | 平台化关键接缝 |
| FR-011 | 统一 explain | Should | 排障与可解释 |
| FR-012 | 加载期校验 | Must | 防止声明漂移 |
| FR-013 | 等价性回归与守卫 | Must | 保证不回归 |
| FR-014 | 规则中心（目录 + 配置入口） | Should | 规则来源 6 类，实施无法一眼看全 |
| FR-015 | 单据级推导追踪 | Should | 回答「值/状态/审批是谁决定的」 |
| FR-016 | 规则因子完整性治理 | Should | 因子少传导致细粒度配置静默失效 |
| FR-017 | 规则试算（what-if） | Should | 配置变更前可预判，避免「保存后才知道命中谁」 |
| FR-018 | 配置发布流 | Should | 控制参数/行类型变更需草稿、校验、发布与回滚 |

**里程碑**

- M1（低风险试点）：FR-007、FR-008、FR-009、FR-013
- M2（流程域）：FR-004、FR-005、FR-006、FR-012
- M3（权限/平台域）：FR-002、FR-003、FR-010、FR-011
- M4（规则中心）：FR-014、FR-015、FR-016、FR-017、FR-018（依赖 M3 的 Provider 与 Explain）

---

## 9. 变更/设计方案（RFC）

### 9.1 现状分析（As-Is）

| # | 位置 | 硬编码内容 | 目标载体 | 难度 | 风险 |
|---|---|---|---|---|---|
| 1 | `permission_dimension_engine.py:45-100` 等 6 处 | 对象→表/父外键/显示列/子类型 | L1 层级声明 | 高 | 高（权限语义） |
| 2 | `org_scope_validator.py:21` | 43 项组织边界清单 | L1 豁免声明 + 推导 | 低 | 低 |
| 3 | `field_policy_engine.py:82-96` | `SYSTEM_FIELDS` | L1 字段元数据 | 低 | 低 |
| 4 | `sales_order_guard_service.py:251`、`serial_number_service.py:84` | 状态图 + 规则号 | L1 `state_transition` | 中 | 中 |
| 5 | `document_approval_service.py:31-39` | 审批对象表、金额优先级 | L1/L2 审批规则 | 中 | 中 |
| 6 | `v214/v215/v222` 迁移 | 单据流业务分支 | L2 doc_flow 数据 | 中 | 中 |
| 7 | `document_number_service.py:13-40` | 编号绑定 | L1 `numbering` | 低 | 低 |
| 8 | `tax_guard_service.py:31` 等 5 处 | 业务映射常量 | L2 参数/映射 | 低 | 低 |
| 9 | `rule_provider.py` + 各域 store | 读取入口分散 | 统一 facade | 中 | 中 |
| 10 | DEFAULT 之外无 explain | 只能查日志 | 统一 explain | 中 | 低 |

### 9.2 目标态（Target）

```text
L1 元模型（随产品版本，Git 管理）
  BO YAML: rules / computed / validation / state_transition / org_scope / numbering / approval
  层级声明: dimension_levels（level_type / parent_level / scope_anchor / owner_field）
        ↓ 加载期解析 + 校验（V1-Vn）
L2 配置（租户可改，DB 规则表）
  data_permission_rules / doc_flow_rules / approval_rules / config_rules / number_sequence / control_parameter
        ↓
RuleProvider（唯一读取入口，屏蔽载体差异）
        ↓
RuleEngine（8 类型执行）+ Domain Services（只保留算法/副作用）
        ↓
ExplainService（默认/权限/状态/审批统一解释）
```

### 9.3 详细设计

**模块职责**

| 模块 | 职责 |
|---|---|
| `yaml_loader` | 解析新声明块，构造 `MetaObject` 字段 |
| 各域 validator | 加载期校验，稳定错误码 |
| `RuleProvider` | 统一取规则（YAML + DB） |
| `RuleEngine` | 执行 default/validation/computation |
| 域服务 | 只保留副作用、跨对象算法、复杂校验 |
| `ExplainService` | 统一解释与 dry-run |

**数据模型**

- `dimension_levels`（L1，独立声明文件）：`{level_type, parent_level, scope_anchor, owner_field, profile}`；`profile=4` 为当前行为，`profile=full` 含 `service_module / business_object`。
- `MetaObject.numbering: Dict`：`{field, date_field, sequence_code, scope_bo, fallback_sequence_code, gapless}`。
- `MetaObject.approval: Dict`：`{enabled, table, amount_fields, rule_set}`。
- 复用 `MetaObject.state_transitions`、`MetaObject.org_scope`、`MetaObject.rules`。
- L2 规则表沿用现有表，不新增重复表。

**主流程**

1. 加载：YAML → MetaObject → 各域 validator → 缓存。
2. 读取：调用方 → RuleProvider → 规则列表。
3. 执行：RuleEngine / 域服务。
4. 解释：ExplainService 读取同一 Provider 与因子快照，输出原因。

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A 全部 YAML | 单一真源、版本可追溯 | 租户不可改、发版耦合 | 否 |
| B 全部 DB | 租户可配 | 结构语义不可版本化、测试困难 | 否 |
| C 分层归属（本方案） | 各取所长 | 需要判定准则与 Provider | **选中** |
| D 维持现状 | 零成本 | 漂移持续、发版耦合 | 否 |

### 9.5 实施与迁移计划

**本轮范围**：仅 M1（TBD-1 决议）；M2、M3 以独立变更单推进。

**实施顺序**

1. M1：FR-007 编号 → FR-008 系统字段 → FR-009 映射 → FR-013 守卫。
2. M2：FR-004 状态机试点 → FR-005 审批 → FR-006 单据流 → FR-012 校验。
3. M3：FR-002 层级 SSOT（影子双跑）→ FR-003 组织清单 → FR-010 Provider → FR-011 Explain。

**风险与缓解**

| 风险 | 缓解 |
|---|---|
| 层级 SSOT 改变权限语义 | 只读双跑 + 逐项等价 + 独立开关 |
| 状态机迁移改变错误码 | 错误码与文案回归用例 |
| 编号迁移导致重复/跳号 | 事务外取号约束不变 + 取号结果比对 |
| 规则载体分散回潮 | 静态守卫 + 评审清单 |

**测试策略**

- 单元：validator 正/负例、Provider 载体透明、映射等价。
- 集成：列表/详情/保存/流转/审批链路。
- E2E：权限可见性、状态流转拒绝、编号生成。
- 全部经 `python d:\filework\test.py`。

**回滚方案**

- 每域独立开关；关闭即回旧代码路径。
- 旧常量保留一个版本作为 fallback。
- 不涉及数据回滚。

### 9.6 规则中心与单据级推导设计（v1.4 新增）

#### 9.6.1 统一规则描述符（RuleDescriptor）

规则中心不新建规则表，而是把 6 类来源归一为只读描述符：

```json
{
  "rule_key": "control_parameter:PAYMENT_TERM",
  "name": "付款条件默认值",
  "rule_type": "control_parameter",
  "layer": "L2",
  "source": "control_parameter",
  "source_tags": ["validation", "default"],
  "scope_bo": "sales_order",
  "factors": {
    "domain": "sales",
    "value_type": "string",
    "default_value": "NET30",
    "value_count": 12
  },
  "configurable": true,
  "status": "active",
  "priority": null,
  "updated_at": "2026-11-07T10:00:00",
  "detail": {
    "condition": "付款条件按组织 + 单据类型取值",
    "values": "[...前 20 条]",
    "values_truncated": false
  },
  "links": {
    "edit": "/api/v2/bo/control_parameter/42",
    "publish": "/api/v2/rules/publish",
    "rollback": "/api/v2/rules/rollback"
  }
}
```

- **字段契约以 §13.2 为准**：本节仅为示例；新增字段 MUST 先改 §13.2，禁止在适配器里私自扩字段或并存两种形状。
- `rule_key` 命名：`{source}:{natural_key}`，由各来源适配器**唯一生成**；目录 / 试算 / 推导 / 发布四处禁止各自拼接（见 §13.3 F-13-04）。
- `factors`：**对象形状**（键为因子名），空对象表示全局规则；不得与 `detail` 重复承载同一语义。
- `configurable`：L1 YAML 与 doc_flow / approval 为 `false`；控制参数与行类型为 `true`。
- `status`：`active / inactive / draft`；`draft` 与 `active` **同表以 status 区分**，不另建草稿表；列表默认排除，勾选「包含草稿」才显示并标注「草稿未生效」。
- `links`：由服务端下发，前端不维护 `source → 目标表` 映射；`links.edit` 仅对 `configurable=true` 下发；草稿态额外下发 `links.publish` / `links.rollback`（见 §9.6.8）。`links` 当前实现尚未落地（§13.3 F-13-05）。

#### 9.6.2 聚合服务（RuleCatalogService）

新增 `meta/services/rule_catalog_service.py`，职责仅为「读 + 归一 + 过滤」：

| 适配器 | 读取入口 | 备注 |
|---|---|---|
| `YamlRuleAdapter` | `RuleProvider.get_rules(meta_obj)` | 遍历 registry 中的 BO，展开 YAML 规则 |
| `DocFlowAdapter` | `doc_flow_rule` 表（现有 `get_rule` 仅单条，列表需补只读查询） | 含 `status`，只读 |
| `ApprovalAdapter` | BO YAML `approval` 声明（现状）；`approval_policies` + conditions + steps（DB 化后） | 一策略一描述符，条件/步骤放详情；当前实现读 YAML 声明（§13.3） |
| `ControlParameterAdapter` | `control_parameter_defs` / `_values` | 已 BO 化，直接查询 |
| `LineTypeAdapter` | `line_types` / `line_type_assignments` | 已 BO 化，直接查询 |
| `StateMachineAdapter` | `state_machine_loader` / BO YAML | 只读 |

约束：

- **不新增表、不写库**；目录结果按请求实时聚合，可加 60s 进程内缓存（NFR-003）。
- 目录与运行时共用同一读取入口；禁止在目录服务里复制匹配算法。
- 控制参数 / 行类型适配器 MUST 支持 `include_draft: bool = False`：默认仅取 `status='active'`（与运行时一致），发布流与试算需显式开启（见 §9.6.7 / §9.6.8）。**当前实现无该参数**，默认过滤口径见 §13.3 F-13-11。
- 详情页的「规则原文」由适配器返回：YAML 规则给声明块，DB 规则给行快照。

#### 9.6.3 规则中心页面信息架构

- 路由：`/system/rule-center`，菜单 `rule-center`，`page_type=rule_center`（`menu.yaml` 新增枚举值，属 L1 schema 变更、零 DDL；`dynamicRoutes.js` 的 `PAGE_TYPE_COMPONENTS` 注册 `RuleCenterPage.vue`，由菜单表自动注册路由）。
- **页面由视图元数据驱动**：页签、列、筛选项、行操作、详情分区与试算场景全部来自 `meta/schemas/rule_center_view.yaml`（结构见 §9.6.9）。Vue 侧只保留一个通用壳 `RuleCenterPage.vue`，按元数据渲染；新增/调整页签不得改前端代码。
- 默认 `rule_center_view.yaml` 声明 9 个页签（实施时可增删，无需改前端）：
  1. **全部规则**：统一列表（默认页签）。
  2. **控制参数**：按 domain → 参数定义 → 取值矩阵展示；四维列默认 组织 / 单据类型 / 行类型 / 物料组（列由 YAML 声明，非组件固定）。
  3. **行类型**：`line_type_assignments` 按单据类型 + 物料组展示命中顺序与默认值。
  4. **单据流**：source_bo → target_bo 有向列表，标注 status。
  5. **审批策略**：策略头 + 条件 + 步骤（只读）。
  6. **校验与默认值**：YAML rules 只读列表。
  7. **规则试算**：因子快照输入 + 基线/草稿对照（见 §9.6.7）。
  8. **健康检查**：见 FR-016（因子覆盖矩阵 / 未引用规则 / 静默回落 / 硬编码残留）。
  9. **单据推导**：输入 `object_type` + `record_id`（可选 `codes` / 四维因子），展示 6 场景推导信封与因子快照（见 §9.6.4，`kind=rule_trace`，需 `rule_center:rule_center_trace`）。
- 默认列表列：`rule_key`、名称、类型、载体、作用对象、适用因子、可配置、状态、更新时间、操作。
- 默认行操作：查看详情（抽屉）、编辑（跳转 BO 详情/抽屉）、查看声明、**试算**（跳转试算页签并预填因子）、复制 `rule_key`；发布 / 回滚为 §9.6.8 的链接动作（`links.publish` / `links.rollback`）。
- 筛选条件可写入 URL query，支持从单据详情反向跳转（带 `bo` / `rule_type`）。
- 接口不可用或响应不可解析时，前端 MUST 回落到「全部规则 + 默认列」的**纯结构**兜底（不得包含业务取值），并按 `not_instrumented` 口径提示，不得白屏；服务端元数据非法则在加载期失败，不下发降级配置（§13.4）。

#### 9.6.4 单据规则推导的展示设计（v1.7 细化）

同一份数据、同一套渲染契约，两个入口：

| 入口 | 位置 | 适用 | 记录来源 |
|---|---|---|---|
| A 单据详情分区 | 任意 BO 详情页，`ui_view_config.detail.rule_trace.enabled=true` 时追加 | 看「当前这张单」 | 当前记录 id 自动带入 |
| B 规则中心页签 | `/system/rule-center?tab=trace`，`rule_center_view.yaml` 的 `tabs[trace]` | 跨 BO 排查 / 无详情页的 BO | 手输 `object_type` + `record_id` |

**A. 详情分区声明（`ui_view_config`，单一真源）**

```yaml
ui_view_config:
  detail:
    rule_trace:
      enabled: true
      label: 规则推导
      permission: rule_center:rule_center_trace
      lazy: true                    # 首次展开分区才请求
      scenarios: [default, control_parameter, line_type, approval, doc_flow]   # state_transition 需 from_state/to_state，A 入口缺省不选
      codes: []                     # 控制参数场景必填；为空时该场景显示「需选参数」引导
```

- `DetailPage.computedSections` 在 `enabled=true` **且** 当前用户具备 `permission` 时追加 `type='custom'`、`key='rule_trace'` 的分区（经 ObjectPage 的 `section-*` slot 转发渲染）；缺权限不渲染分区（不是渲染空态）。
- 组件 `src/components/common/RuleTrace/RuleTracePanel.vue`，props：`objectType`、`recordId`、`scenarios`、`codes?`、`dims?`；组件不读 store、不拼 URL，统一走 `getRuleTrace()`（`src/services/ruleCenterService.js`）。
- 操作：「重新推导」（只 GET，不写）、「复制因子快照」。视图元数据缺失时回落为不带分区，不白屏。

**B. 规则中心页签声明（`rule_center_view.yaml`）**

```yaml
  - id: trace
    label: 单据推导
    kind: rule_trace
    require: rule_center:rule_center_trace
    fields: [object_type, record_id, scenarios, codes, org_id, document_type_id, item_group_id]
    actions: [rerun]
```

- `kind=rule_trace` 为封闭枚举中的新增值（与 `simulate` / `health` 同级），需同步升 `version`。
- 渲染组件与 A 复用 `RuleTracePanel.vue`，仅外壳不同（B 多一层表单壳），**不新增第二套渲染逻辑**。
- `object_type` 下拉取值来自 `registry.list()`（BO 注册表），不写死在 YAML；`record_id` 必填数值。
- 页签 MUST NOT 自动请求：先选对象 + 填记录 id，再点「推导」，避免打空请求。

**请求契约（IF-007）**

参数以 IF-007 为准：`scenarios`（csv，缺省 6 类）、`codes`（csv，≤20）、四维因子（`org_id / document_type_id / line_type_id / item_group_id`）、`user_id / action_id`、`from_state / to_state`。两个入口的差异仅在于谁填这些值。

**渲染契约（信封 → UI）**

| 响应字段 | UI 位置 | 展示规则 |
|---|---|---|
| `trace_id` | 顶部标题右侧（monospace，可复制） | 仅日志关联，不参与判定 |
| `object_type` / `record_id` / `factors` | 顶部因子快照条 | `factors` 全量展示；`null` 显示「未提供」，禁止显示 0 / 空串 |
| `scenarios[].scenario` / `decision` / `rule_id` / `source` / `reason` / `elapsed_ms` | 场景卡片头 | `decision` 用元数据映射的固定徽标（见 §9.6.9 `trace.decisions`） |
| `scenarios[].detail.chain[]`（control_parameter） | 参数链路表 | 每行 `code / value / source.type / candidates[]（specificity_rank 升序）/ missing`；命中行高亮 |
| `scenarios[].detail`（line_type） | 行类型命中表 | `line_type_id` + `source`（assignment / default / missing）+ 候选 assignment 顺序 |
| `scenarios[].detail`（doc_flow） | 上下游列表 | 每条 `rule_id / target_bo / pool / status` |
| `scenarios[].ok=false` | 卡片红色边 + 可展开错误 | 单场景失败不隐藏、不阻塞其他卡片 |

- 卡片顺序 MUST 与 `scenarios[]` 一致（即 `scenarios` 入参顺序），前端不重排。
- `decision` 文案与徽标色放 `rule_center_view.yaml` 的 `trace.decisions`；未知值回落原文，不写死在组件里。
- `codes` 前端先 trim + 去重 + 截断到 20 并提示；与 `simulate.max_codes` 同口径。

**场景能力矩阵（当前实现）**

| 场景 | 状态 | 前置条件 | 缺前置时表现 | 前端引导 |
|---|---|---|---|---|
| `default` | 已接入 | 单据数据 | — | — |
| `control_parameter` | 已接入 | `codes[]` | `decision=skipped, reason=no_codes_requested` | 显示「需选参数」+ 跳控制参数页签；A 入口由 YAML `codes` 预置 |
| `line_type` | 已接入 | `document_type_id` | `decision=skipped, reason=document_type_id_missing` | 提示补单据类型；`final.assignment_id=null` 表示未匹配 |
| `approval` | 已接入 | 记录存在 | — | — |
| `state_transition` | 已接入 | `from_state` 或单据状态字段 | 缺 `to_state` 时只列允许状态 | — |
| `doc_flow` | 已接入 | 该 BO 有 active 声明 | 空列表（非错误） | 空态文案「该单据无上下游派生声明」 |
| `validation` / `numbering` | **未接入** | — | 不在 6 场景枚举内，入参直接 400 | 选择器不提供，**不展示伪造结果** |

**口径（MUST）**

- 推导只读：GET 无写副作用；「重新推导」只重复 GET。
- 前端 MUST 消费服务端 `decision` / `reason`，不得按场景名自行推断，也不得本地重算候选。
- 同一单据连续重新推导不做前端缓存（服务端推导不缓存），避免看到过期结论。
- 受单据数据权限约束（越维度 404）；敏感字段按字段策略脱敏。

**空态与错误态**

| 情形 | HTTP | 前端表现 |
|---|---|---|
| 单据不存在 / 不在读取维度范围 | 404 `NOT_FOUND` | 分区内「单据不存在或无权限查看」，不弹全局错误 |
| 无 `rule_center:rule_center_trace` | 403 | A 不渲染分区；B 页签不可见（按 `tabs[].require` 裁剪） |
| `object_type` 未注册 | 404 `NOT_FOUND` | 页签内提示「对象未注册」，不白屏 |
| `scenarios` 非法 | 400 | 前端限制选项，正常路径不可达；命中则展示 400 原文 |
| 单场景内部异常 | 200，该 `scenarios[].ok=false` | 单卡片告警，其余正常 |
| `success=false`（其他） | 5xx | 顶部 `message.error(message)`，保留上次成功结果 |

**落地状态（v1.7 P2 已实施）**

1. trace 端点已补 `@require_permission('rule_center:rule_center_trace')`，403 / 非法 `scenarios` / 未知对象 404 均有用例覆盖。
2. B 入口：`rule_center_view.yaml` 已加 `trace` 页签（`kind: rule_trace`，`version: 2`），`RuleCenterPage.vue` 按 `kind` 分派并消费 `getRuleTrace`。
3. A 入口：`DetailPage` 已按 `ui_view_config.detail.rule_trace` 追加分区（权限裁剪 + 首见懒加载），`RuleTracePanel.vue` 共用渲染。
4. `trace.decisions` 文案映射已进 YAML（13 种 decision），前端未知值回落原文。
5. A 入口 `codes` 预置来源已定为 `ui_view_config.detail.rule_trace.codes`（`sales_order` 已声明 3 个控制参数码）。

**推导计算（不变）**

- `meta/core/rule_trace_service.py`：接收 `object_type + record_id + scenarios`，按场景调用现有 Resolver / Explainer，组装统一 `scenarios[]`。
- `control_parameter` 调用 `ControlParameterResolver.explain(code, dims)`，输出候选行 `specificity_rank`、命中行与回落 `default` 原因。
- `line_type` 调用 `LineTypeResolver.explain(doc_type_id, item_group_id)`，输出 `assignment / default / missing` 来源。
- 其余场景复用 `rule_explainer.explain()`；`doc_flow` 查询 `doc_flow_rule_store` 的 active 声明。
- 每步强制携带 `factors` 与 `elapsed_ms`；顶层带请求级 `trace_id`（UUID，仅日志关联）。

**实施切片（均在 P2，见 §9.6.6）**

| 切片 | 范围 | 验收 |
|---|---|---|
| T1 后端对齐 | trace 端点补 `rule_center:rule_center_trace`；补 403 / 非法 `scenarios` / `codes` 上限用例 | 无权限 403；非法 400；6 场景信封结构不变 |
| T2 页签（B） | `rule_center_view.yaml` 加 `trace` 页签 + `kind=rule_trace`；新增 `RuleTracePanel.vue`；`RuleCenterPage.vue` 按 `kind` 分派 | 输入 `sales_order` + 真实 id → 6 场景卡片 + 因子快照；改 YAML 可隐藏页签且不改 Vue |
| T3 详情分区（A） | `DetailPage` 追加 `rule-trace` 分区 + `ui_view_config.detail.rule_trace` 声明 + 权限裁剪 + 懒加载 | 销售订单详情能看到当前单据推导；无权限不显示分区 |
| T4 口径收口 | `trace.decisions` 入 YAML；空态 / 错误态 / `codes` 去重截断用例 | 前端无硬编码文案；异常不白屏；`codes` 行为与试算一致 |

#### 9.6.5 权限与安全

- 权限码（双段式，需在 `permissions` 表真实存在）：
  - `rule_center:rule_center_read`：查看规则目录与详情，**并含规则试算**（试算只读，不单独设码）。
  - `rule_center:rule_center_write`：编辑控制参数 / 行类型（复用 BO 写权限校验）；发布与回滚同权限。
  - `rule_center:rule_center_trace`：查看单据规则推导。
- 单据推导必须复用详情读取的数据权限（不得绕过组织/维度范围）；无权限返回 403，不返回「无数据」伪空态。
- 规则试算用 `record_id` 回填因子时，MUST 先校验该单据的读权限；仅给因子不查单据时按规则中心权限放行。
- 敏感字段（金额、成本、供应商等）按字段策略脱敏后再进入 `factors`。
- 规则目录中 L1 声明只读；前端不提供 YAML 编辑入口。

#### 9.6.6 实施阶段

| 阶段 | 范围 | 验收 |
|---|---|---|
| P1（只读） | 规则目录 + 详情抽屉 + 推导接口（default / control_parameter / line_type / approval / state_transition / doc_flow）；视图元数据落地（`page_type=rule_center` 注册 + `rule_center_view.yaml` + 通用壳 `RuleCenterPage.vue`） | 6 类来源可检索；推导接口对一张销售订单/采购订单/调拨单/需求单返回 6 场景信封；只改 YAML 即可增删页签与列，无需改 Vue 组件 |
| P2（可配置） | 控制参数 / 行类型进入发布流（draft → 校验 → active）、内联编辑、规则试算（含基线/草稿对照）、**单据推导入口（B 规则中心「单据推导」页签 + A 详情分区，见 §9.6.4 T1–T4）**、doc_flow status 变更、审批策略编辑器 | 编辑只写草稿不改变生产解析；发布前必须通过试算与加载期校验；发布留痕且可回滚；**规则中心与单据详情均能实际打开推导并看到因子值 / 候选集 / 命中输出** |
| P3（增强） | `validation` 场景、规则影响分析、配置导出/导入 + diff、可选 `rule_trace` 持久化 | 需单独 DDL 审批与保留期策略 |

**测试策略**

- 单元：`RuleCatalogService` 各适配器归一、过滤、权限；`rule_trace_service` / `rule_simulate_service` 各场景组装与 `not_instrumented`；发布流状态机非法迁移拒绝。
- 集成：目录 API、追踪 API、试算 API、详情页分区渲染、写操作校验、发布/回滚。
- 回归：规则中心只读路径与试算路径不得改变任何业务数据；草稿态不得影响 `status='active'` 解析结果；推导/试算结果与写入路径一致。
- 全部经 `python d:\filework\test.py`。

#### 9.6.7 规则试算（what-if）设计

**服务与入口**

| 项 | 设计 |
|---|---|
| 服务 | `meta/services/rule_simulate_service.py`，场景分派复用 `rule_trace_service` 的 handler 注册表 |
| 接口 | IF-008 `POST /api/v2/rules/simulate` |
| 前端 | 规则中心「规则试算」页签：左栏因子表单，右栏「基线 / 草稿 / 差异」三列结果 |
| 来源 | 评级同 `RuleCatalogService`：全部走 Provider / Resolver，不复制匹配算法 |

**因子解析优先级**

1. 显式 `factors` 优先；
2. 未给全时用 `record_id` 从单据回填（复用 `rule_trace_service` 的因子采集）；
3. 仍缺失则为 `null`，并在响应 `factors.missing[]` 中标注——不得用默认值静默补位。

**响应结构（示例）**

```json
{
  "ok": true,
  "scenario": "control_parameter",
  "decision": "hit",
  "rule_id": "control_parameter:mrp_lot_sizing:org=1,item_group=RM",
  "source": "db:control_parameter_values",
  "factors": {"org_id": 1, "document_type_id": null, "line_type_id": null, "item_group_id": 7},
  "codes": ["mrp_lot_sizing"],
  "candidates": [
    {"rank": 4, "specificity": 4, "status": "active", "value": "LOT_FOR_LOT", "hit": true},
    {"rank": 1, "specificity": 0, "status": "active", "value": "EOQ", "hit": false, "reason": "维度不匹配"}
  ],
  "final": {"code": "mrp_lot_sizing", "value": "LOT_FOR_LOT", "from": "specific", "fallback": false},
  "baseline": {"value": "EOQ", "rule_id": "control_parameter:mrp_lot_sizing:*"},
  "draft": {"value": "LOT_FOR_LOT"},
  "diff": [{"code": "mrp_lot_sizing", "baseline": "EOQ", "draft": "LOT_FOR_LOT"}],
  "elapsed_ms": 3
}
```

**约束**

- `config_mode=baseline` 仅加载 `status='active'`（与运行时完全一致）；`draft` 额外加载 `status='draft'`，并在候选中标注 `status`。
- 候选集加载函数新增 `include_draft: bool = False` 参数，默认关闭，保证 NFR-001 行为等价。
- 试算 MUST NOT 写库、MUST NOT 触发 trigger/computation；
- 单次 `codes[]` ≤ 20，候选行 ≤ 500，超出返回 400 并提示收窄因子；
- 结果按「因子 + config_mode + 配置版本号」缓存 ≤ 30s，配置发布后立即失效。

#### 9.6.8 配置发布流设计

**状态机（复用现有 `status` 列，零 DDL）**

```
draft ──(校验+试算通过)──> active ──(停用)──> inactive
  ↑                          │
  └──────(回滚上一版本)───────┘
```

- `control_parameter_value.status` 与 `line_type_assignment.status` 现仅 `active / inactive`，本次新增 `draft` 枚举值（L1 schema 变更，无 DDL）；`status` 列的 `default` 保持不变。
- 运行期解析已按 `status='active'` 过滤（`control_parameter_service` 的 `VALUE_SQL`；`line_type_service` 同口径），因此 `draft` 天然不参与解析，无需改运行时读取逻辑。
- 表单层只允许选择 `active / inactive`；`draft` 由发布流内部置位，避免用户手工造出「已发布」假象。

**发布动作**

| 步骤 | 行为 | 失败处理 |
|---|---|---|
| 保存 | 写入 `status='draft'`，同一 `(参数/行类型, 因子)` 组合只允许一条草稿 | 覆盖原草稿 |
| 校验 | 加载期校验器 + `simulate(config_mode='both')` | 返回校验错误，草稿保留 |
| 发布 | 旧 `active` → `inactive`，草稿 → `active`，写 `audit_log(biz_type=rule_config)` | 事务内失败则整体回滚 |
| 回滚 | 上一版本 → `active`，当前 → `inactive` | 按 `audit_log` 版本号定位 |

**发布历史**

- 写入 `audit_log`：`biz_type=rule_config`、`biz_id`、`action=save/publish/rollback`、`before` / `after` JSON、`operator`、`trace_id`。
- 规则中心详情抽屉提供「历史」页签，读 `audit_log` 渲染，不新增表。
- 多版本并行编辑（多人同时改同一规则）为 P3 话题；P2 采用「最后保存覆盖草稿 + 发布前校验」的乐观策略。

---

#### 9.6.9 规则中心视图元数据设计

**定位**

规则中心展示的是「多来源、非同构」的规则集合（BO YAML / DB 配置 / 只读声明），无法用单张 BO 的 `ui_view_config` 表达。因此新增一份**页面级视图元数据** `meta/schemas/rule_center_view.yaml`，与 `ui_view_config` 同构但独立：

| 元数据 | 回答的问题 | 是否参与运行时解析 |
|---|---|---|
| 规则元数据（`MetaRule` 家族、`control_parameter`、`line_type_assignment`、`doc_flow`） | 规则「是什么」、何时命中 | 是 |
| 视图元数据（`ui_view_config`、`rule_center_view`） | 规则「怎么显示」 | 否 |

两者 MUST 并列、不合并：把展示字段塞进 `MetaRule` 会让规则定义与 UI 耦合，且无法覆盖 DB 来源的规则行。

**载体与路由注册**

- `menus` 表新增 `page_type=rule_center` 枚举（L1 schema 变更，零 DDL），`page_config` 只需 `{ "view": "rule_center_view" }`。
- `dynamicRoutes.js` 的 `PAGE_TYPE_COMPONENTS` 增加 `rule_center → views/RuleCenterPage.vue`，路由由菜单表自动注册；**不使用 `custom_page`**（`custom_page` 不自动注册路由，须在 `router/index.js` 手写静态路由，正是本设计要消除的硬编码）。
- 若短期不便扩充 `page_type`，可退而使用 `page_type=report` + `MetaReportPage`，但仅限于「无写操作、无试算」的只读形态；TBD-15 记录取舍。

**YAML 结构**

```yaml
# meta/schemas/rule_center_view.yaml
version: 2
title: 规则中心
permission:
  read: rule_center:rule_center_read
  write: rule_center:rule_center_write
  trace: rule_center:rule_center_trace   # 固定码，不配置化
tabs:
  - id: all
    label: 全部规则
    default: true
    sources: [bo_yaml, doc_flow, approval, control_parameter, line_type, state_machine, numbering, validation]
    columns: [rule_key, name, rule_type, source, scope_bo, factors, configurable, status, updated_at]
    filters: [domain, rule_type, source, configurable, status, keyword]
    actions: [detail, edit, view_source, simulate, copy_key]
    row_link: /system/rule-center?tab={tab}&rule_key={rule_key}
  - id: control_parameter
    label: 控制参数
    sources: [control_parameter]
    columns: [rule_key, name, org, document_type, line_type, item_group, value, status]
    actions: [detail, edit, publish, rollback]
  # ... line_type / doc_flow / approval / validation / simulate / health
detail:
  sections:
    - { id: basic, fields: [rule_key, name, rule_type, source, scope_bo, factors, priority, status] }
    - { id: expression, widget: code }
    - { id: factors, widget: factor_matrix }
    - { id: source, widget: source_snippet }
    - { id: history, widget: audit_log, params: { biz_type: rule_config, biz_id: "{rule_key}" } }
trace:
  scenarios: [default, control_parameter, line_type, approval, state_transition, doc_flow]
  decisions:                 # 决策徽标文案 + 颜色档；未知值回落原文，不写死在组件里
    applied: { label: 已应用, type: success }
    skipped: { label: 已跳过, type: info }
    granted: { label: 已授予, type: success }
    denied: { label: 已拒绝, type: danger }
    allowed: { label: 已允许, type: success }
    rejected: { label: 已拒绝, type: danger }
    matched: { label: 已命中, type: success }
    not_matched: { label: 未命中, type: info }
    resolved: { label: 已解析, type: success }
    missing: { label: 缺配置, type: warning }
    declared: { label: 已声明, type: success }
    not_declared: { label: 未声明, type: info }
    not_instrumented: { label: 未接入, type: info }
  tab:                       # §9.6.4 入口 B
    id: trace
    label: 单据推导
    require: rule_center:rule_center_trace
    fields: [object_type, record_id, scenarios, codes, org_id, document_type_id, item_group_id]
    actions: [rerun]
simulate:
  fields: [scenario, org_id, document_type_id, line_type_id, item_group_id, record_id, config_mode]
  max_codes: 20
```

**渲染契约**

| 元数据节点 | 渲染组件 | 说明 |
|---|---|---|
| `tabs[].columns` | `GenericObjectList` 列定义 | 列 key 对应 `RuleDescriptor` 字段；未知 key 为**加载期错误**（§13.4），不得静默跳过 |
| `filters` | FilterBar 配置 | 筛选项生成规则同列定义，不写死下拉值 |
| `actions` | 行操作注册表 | `detail / edit / view_source / simulate / publish / rollback / copy_key / rerun` 为固定动作类型（`rerun` 于 v2 新增，用于推导页签） |
| `detail.sections[].widget` | widget 注册表 | `code / factor_matrix / source_snippet / audit_log` 为固定 widget 类型 |
| `trace.scenarios` | 推导场景选择器 | 与 IF-003 `scenario` 枚举同源；只提供已接入场景，`validation` / `numbering` 未接入不出现选项 |
| `trace.decisions` | 决策徽标（文案 + 颜色档） | 未知 `decision` 回落原文；组件内禁止硬编码中文 |
| `trace.tab.fields` | 推导表单（入口 B） | 与 IF-007 query 参数一一对应；`object_type` 选项取自 BO 注册表，不写死在 YAML |
| `trace.tab.require` | 页签可见性 | 缺该权限时按 `tabs[].require` 裁剪页签 |
| `ui_view_config.detail.rule_trace` | 详情分区（入口 A） | 在 BO 侧声明，规则中心 YAML 不重复定义；缺权限不渲染分区 |
| `simulate.fields` | 试算表单 | 与 IF-008 请求体字段一一对应 |

- 动作与 widget 是**封闭枚举**（代码注册、元数据引用），YAML 不能引入新类型；新增类型需改代码并升 `version`。
- 列 / 筛选 / 动作 / 分区均为「引用式」：YAML 只声明 id 与顺序，具体取值渲染时由服务端 `RuleDescriptor` 返回，避免元数据与数据双写。

**校验与演进**

- `rule_center_view.yaml` 随 BO schema 一起在加载期校验：未知 `sources` / `actions` / `widget` / 重复 `tab.id` 直接报错，阻止启动期脏配置。
- **集合等值与引用闭合**同时校验：视图 `sources` ↔ `RuleCatalogService.SOURCES` 双向等值；`trace.scenarios` ⊆ `TRACE_SCENARIOS`；`trace.factor_keys` ⊆ 因子轴声明；`trace.decisions` / `trace.stages` / `messages` 键等值；`filter_options` 值域封闭。矩阵、错误码与负例见 §13.4。
- **版本与指纹**：结构变更 MUST 升 `version`；API 响应携带 `version` + 内容指纹，便于定位「前后端各缓存一版」问题（§13.3 F-13-10）。
- 服务端加载期失败即拒绝启动；前端仅在接口不可用时回落「全部规则 + 默认列」（§9.6.3 末条），且兜底不得含业务取值（§13.3 F-13-07），不白屏。
- 视图元数据**不参与规则解析**：试算、推导、发布校验仍分别走 `rule_simulate_service` / `rule_trace_service` 与运行时同源逻辑；改 YAML 不可能改变任何业务判定。

**权限边界**

- 权限码固定为 `rule_center:rule_center_read` / `_write` / `_trace` 三枚，**不做配置化**：权限码需在 `permissions` 表存在，配置化会绕过权限中心治理。
- 页签级可见性由 `tabs[].require`（引用上述三枚之一，可缺省）控制，仅做**呈现裁剪**；服务端 API 仍独立鉴权（§9.6.5）。

---

## 10. TBD 决议

> 决议日期：2026-11-07。对标依据：Oracle Fusion、SAP S/4HANA / Solution Manager、Workday、ServiceNow CSDM、Microsoft Dynamics 365、NetSuite、LeanIX 的公开产品机制。

### 10.1 决议表

| ID | 事项 | 决议 | 判定依据 | 状态 |
|---|---|---|---|---|
| TBD-1 | 本轮实施范围 | 仅 M1（编号 / 系统字段 / 映射 / 等价性守卫）；M2、M3 另立变更单 | 载体迁移与语义变化必须解耦，否则回归不可定位；Oracle Sandbox 亦按对象分批发布 | 已定 |
| TBD-2 | 状态机载体 | L1 声明主状态图与终态；L2 只允许原因码 / 子状态 / 动作门槛，不得新增主状态 | Dynamics `statecode` 固定 + `statuscode` 可配；SAP 系统状态固定 + 用户状态附加 | 已定 |
| TBD-3 | 编号载体 | L1 声明绑定（field / scope_bo / date_field / sequence_code / gapless）；L2 只配前缀、补零、区间、重置策略、起始值 | SAP SNRO 号码范围对象由产品定义、区间由客户维护；D365 编号序列按法人 | 已定 |
| TBD-4 | 层级口径 | 4 层与 6 层并存：`dimension_levels` 声明层级类型与深度，`scope_anchor` 单独标记可授权层级；默认 profile=4 | Workday Functional Area / Domain / Business Process 三轴分离；ServiceNow CSDM 按关注点分层；SAP SolMan 组织单元 / 主数据 / 业务流程三正交 | 已定：保持现状，`sub_domain` 仍为授权叶子，`service_module` 不升第 5 锚点 |
| TBD-5 | 等价性边界 | 错误码、HTTP 状态、放行/拒绝结论冻结；日志与文案可改，但 i18n key 稳定 | Oracle / SAP 均为 message class + message number 稳定、文本可翻译 | 已定 |
| TBD-6 | 审批注册表 | 结构放 L1（对象→表、金额字段优先级、开关、默认规则集）；策略放 L2（条件、步骤、金额段、审批人、生效期）；L2 不存表名 | Oracle BPM 策略为租户配置，对象可审批性与金额字段为产品元数据 | 已定 |
| TBD-7 | Explain 范围 | 一期覆盖 permission / state / validation；approval 与 derivation 二期 | 三类是写入拒绝与不可见的主因，且数据已在拦截器/状态机/校验器内；审批解释依赖 L2 快照 | 已定 |

### 10.2 TBD-4 头部产品研究

**结论：4 层 vs 6 层是伪命题；真正要定的是「层级类型」「深度」「授权锚点」三件事。**

> 现状依据：`meta/schemas/hierarchies.yaml` 已记录 2026-06-03 由 6 层裁剪为 4 层，
> 理由为「层级过深，授权到子领域已足够精确」。这正说明 6 层仍有展示价值，只是不适合做授权粒度。

| 产品 | 机制 | 对我们的启示 |
|---|---|---|
| Workday | Functional Area（导航分组）→ Domain（安全集合）→ Business Process Type；一个 Domain 可属于多个 Functional Area | 导航层级与安全范围是两套坐标，不能共用一棵树做授权 |
| ServiceNow CSDM | 4 层（Ideation / Design / Build / Service Delivery）7 个域，按关注点分层，实体跨层多对多 | 层级是关注点分层，不是固定元数；深度随模型演进 |
| SAP Solution Manager | Business Blueprint 将组织单元、主数据、业务流程分三类管理 | 组织、对象、流程是正交维度，不应压成一条链 |
| Oracle Fusion | 以产品族 / 功能范围 / 任务组织功能；数据授权另由 Data Role + 组织层级决定 | 展示深度可到 6 层，授权锚点另立 |
| LeanIX / EA 工具 | 能力地图深度可变，实践建议每层 5-10 项、优先广度 | 固定深度会逼迫模型裁剪，最终产生「假层级」 |

**落地模型**

```yaml
dimension_levels:
  - level_type: product          # 层级语义类型
    parent_level: null
    scope_anchor: true           # 可作数据授权锚点
    owner_field: product_id
  - level_type: version
    parent_level: product
    scope_anchor: true
    owner_field: version_id
  - level_type: domain
    parent_level: version
    scope_anchor: true
    owner_field: domain_id
  - level_type: sub_domain
    parent_level: domain
    scope_anchor: true           # 当前 4 层 profile 的叶子
    owner_field: sub_domain_id
  - level_type: service_module
    parent_level: sub_domain
    scope_anchor: false          # 展示层级，不授权
    owner_field: service_module_id
  - level_type: business_object
    parent_level: service_module
    scope_anchor: false
    owner_field: business_object_id
```

**两条不变量**

1. `scope_anchor=true` 的层级集合必须能覆盖所有业务表的归属字段；不能覆盖时，加载期报 `DIMENSION_ANCHOR_UNCOVERED`。
2. 任一深度的对象向上解析归属时，只能命中最近的一个 `scope_anchor`；跨锚点解析报 `DIMENSION_ANCHOR_AMBIGUOUS`。

**已确认（2026-11-07）：保持现状，不做行为变化**

- `product / version / domain / sub_domain` 四个 `scope_anchor=true` 不变；
- `sub_domain` 仍为授权叶子；
- `service_module / business_object` 仍为 `scope_anchor=false`，只做展示与归属解析；
- 默认 `profile=4`，现有权限行为零变化。

### 10.3 关联修正

- FR-002 验收标准改为「深度可声明 + 锚点分离」。
- §7.3 假设 2、3 更新为已定结论。
- §9.5 明确本轮只实施 M1。

### 10.4 二次确认（官方文档级）

对 §10.1 的每条决议做了第二轮核实，优先采用产品官方文档而非二手文章。

| ID | 核实到的产品事实 | 对 Spec 的影响 | 结论 |
|---|---|---|---|
| TBD-1 | Oracle Fusion 的自定义在 Sandbox 内完成，验证后 Publish 合并回主线 | 变更应以「可验证的发布单元」推进，而非一次性全量 | 维持 M1 |
| TBD-2 | Microsoft：`statecode` 的状态选项不能新增，只能改标签；`statuscode`（Status Reason）可按状态增删 | 比原决议更严格：L1 主状态值冻结，L2 只能扩原因码 | 维持并收紧 |
| TBD-3 | Oracle Document Sequence 分 Automatic / Gapless / Manual，可设初始值并按单据类别分配；Gapless 会阻止删除已编号单据 | `gapless` 不能只理解为「不跳号」，还要加删除约束 | 微调（新增约束） |
| TBD-4 | ServiceNow CSDM 明确四层用于 separation of concerns；Workday 一个 Domain 可属于多个 Functional Area | 层级是关注点切分，且允许非树形引用；授权锚点与展示层级必须分离 | 维持并补「允许多对多引用」 |
| TBD-5 | SAP 消息由 message class + message number 定位，长文本可独立维护（SE91） | 错误码/消息号稳定、文案可翻译，与原决议一致 | 维持 |
| TBD-6 | Oracle AME 以规则引擎按金额区间等条件路由审批，配置而非编码 | 审批策略属租户配置层，与原决议一致 | 维持 |
| TBD-7 | SAP SU53 只能在报错后立即查看「最后一次失败的授权检查」，缓冲区易失 | Explain 必须同步记录当次失败因子，不能事后从日志重建 | 微调（新增约束） |

### 10.5 二次确认带来的微调

1. **TBD-2 收紧**：`state_transition.states[].code` 为主状态主键，加载期禁止租户新增/删除；租户只能维护 `label` 与 `reason_codes`。
2. **TBD-3 增约束**：`gapless: true` 时，已编号单据禁止物理删除；作废必须保留号码并置 `voided`，否则报 `NUMBER_SEQUENCE_GAP_FORBIDDEN`。
3. **TBD-7 增约束**：Explain 的 `factors[]` 必须在同一次请求内生成并随响应返回（含 `rule_id`、`level`、期望值/实际值）；禁止依赖日志回捞。
4. **TBD-4 补边界**：`dimension_levels` 的展示层级（`scope_anchor=false`）允许一个对象被多个父级引用；授权层级仍要求唯一归属，避免权限歧义。

### 10.6 研究来源

- Microsoft Learn：Define custom state model transitions（statecode 不可新增状态值）
- SAP：User Status Profile（系统状态不可改，用户状态附加）
- Oracle：Document Sequences（Automatic / Gapless / Manual，初始值，Gapless 阻止删除）
- Oracle：AME（Approval Management Engine）规则化审批
- SAP：SU53 授权检查
- SAP：SE91 消息维护
- ServiceNow：CSDM 5 White Paper（四层 separation of concerns）
- Workday：Configurable Security Framework（Functional Area / Domain）
- Oracle：Sandbox Publish
- （v1.5 补充）Oracle Fusion：Application Composer、Flexfield（KFF / DFF / EFF）、AME Test Workbench
- （v1.5 补充）SAP S/4HANA：Key User Extensibility（In-App / Developer / Side-by-Side）、Clean Core、BRFplus 决策表
- （v1.5 补充）Microsoft Dynamics 365 F&O：AOT 元模型、Workflow History、Business Events
- （v1.5 补充）ServiceNow：Decision Tables（specific → generic 优先级）、Decision Builder
- （v1.5 补充）NetSuite：SuiteBuilder、SuiteCloud Development Framework（元数据即代码）
- （v1.5 补充）Workday：Business Process Framework、Object Management Services
- （v1.5 补充）Odoo：ORM 元数据模型、Server Actions
- （v2.0 补充，规则语义范畴）SAP：MDG BRFplus Configuration Guide（对属性值做 check / derive）
- （v2.0 补充）SAP：Variant Configuration Object Dependencies（Precondition / Selection Condition / Action / Constraint / Procedure）
- （v2.0 补充）SAP：条件技术 access sequence（候选集 + most-specific-first + 命中即停 + 回退）
- （v2.0 补充）Oracle Fusion：Value Sets（8 种校验类型、`$FLEX$` 上下文绑定）、Cross-Validation Rules、Related Value Sets、Defaulting Rules
- （v2.0 补充）Microsoft Dynamics 365：Business Rules（set field value / business required / visibility / lock-unlock / error message，scope=Entity/All forms/Specific form）
- （v2.0 补充）Workday：Calculated Fields（运行时算、不落库）、Condition Rules（entry / validation / while running / exit）
- （v2.0 补充）ServiceNow：Data Policy（服务端强制、不可绕过）、Decision Table（按 Order 逐行、首个匹配即返回）
- （v2.0 补充）NetSuite：Custom Field 的 Validation & Defaulting（Formula + Store Value 决定是否动态重算）
- （v2.0 补充）Odoo：`default` / `compute` / `inverse` / `domain` / `@api.constrains` / `_sql_constraints` / `onchange`
- （v2.0 补充）DMN 1.x：hit policy（UNIQUE / ANY / PRIORITY / FIRST / COLLECT 含 Sum·Min·Max·Count）、DRD 依赖图

### 10.7 规则中心与因子治理决议（v1.4 新增，v1.5 扩展）

| ID | 事项 | 决议 | 判定依据 | 状态 |
|---|---|---|---|---|
| TBD-8 | 规则中心聚合范围 | 一期聚合 §3 FR-014 的 6 类业务规则来源；权限规则不纳入，跳转权限中心 | 权限规则已有独立 Explain / 权限中心；业务规则与安全规则受众不同 | 已定 |
| TBD-9 | 配置写入边界 | 一期只写已 BO 化的 L2（`control_parameter_value` / `line_type_assignment`）；doc_flow / approval 只读 + 跳转；L1 YAML 永不提供 UI 编辑 | 与 TBD-1/2/3 的 L1/L2 归属一致；避免 UI 绕过加载期校验 | 已定 |
| TBD-10 | 推导追踪持久化 | 一期按需计算、不落库；二期持久化 `rule_trace` 需独立 DDL 审批 + 保留期策略 | 一期先保证可解释与同源；存储/隐私成本后置 | 已定 |
| TBD-11 | 因子缺失语义 | `resolve / resolve_many` 必须显式传 `dims`；空 dims 仅允许声明为 `scope=global` 的参数 | 当前 `_matches` 对调用方未传的维度直接判不命中并静默回落 `default_value`，细粒度配置会永久失效 | 已定 |
| TBD-12 | 规则试算范围 | 试算只覆盖已接入 `rule_trace` handler 的场景；输入因子优先于 `record_id` 回填；`baseline` 与运行时同口径，`draft` 需显式 `config_mode`；只读不落库 | Oracle AME Test Workbench 同样只模拟已注册的规则集，未注册场景不臆测结果 | 已定 |
| TBD-13 | 配置发布流载体 | 复用 `status` 列新增 `draft` 枚举（L1 schema 变更，零 DDL），不引入 `validated` 中间态；发布/回滚写 `audit_log(biz_type=rule_config)` | 运行期解析已按 `status='active'` 过滤，`draft` 天然隔离；Oracle Sandbox 也以「激活」为唯一切换点 | 已定 |
| TBD-14 | 配置版本记录 | 一期不新增版本表，用 `audit_log` 的 `before/after` JSON + `trace_id` 承载历史；P3 若需并行编辑与逐版本 diff，再评估 `rule_config_version` 表（需 DDL 审批） | 与 TBD-10「先按需计算、后置持久化」保持一致；避免为低频操作引入新表 | 已定 |
| TBD-15 | 规则中心页面载体 | 采用 `page_type=rule_center` + `rule_center_view.yaml` 视图元数据驱动；不落 `custom_page`，也不把展示字段塞进 `MetaRule` | `custom_page` 不自动注册路由、须在 `router/index.js` 手写静态路由，违背平台元数据驱动原则；规则元数据回答「是什么」、视图元数据回答「怎么显示」，职责不同（§9.6.9） | 已定 |
| TBD-16 | 单据推导 `codes` 预置来源 | 一期采用「`ui_view_config.detail.rule_trace.codes` 手配 + 页面允许用户增删」，不改 BO schema、不引入新表；若后续需要按单据类型自动推荐参数清单，再评估 BO schema 扩展 | `control_parameter` 场景缺 `codes` 会 `skipped`，但「哪张单关心哪些参数」目前无真源；为避免臆造，先由配置显式声明 | 已定 |

**关联修正**

- FR-016 新增因子完整性治理，作为规则中心「健康检查」的需求来源。
- IF-003 的 `scenario` 从 4 类扩展为 8 类，并要求未接入场景返回 `not_instrumented`。
- §8 里程碑新增 M4（规则中心），依赖 M3 的 Provider 与 Explain 收敛完成。
- §9.6 明确一期零 DDL：目录实时聚合、推导按需计算；所有编辑复用现有 BO 写路径。
- （v1.5）新增 FR-017 规则试算与 IF-008 试算接口，设计见 §9.6.7。
- （v1.5）新增 FR-018 配置发布流，设计见 §9.6.8；§9.6.3 页签由 7 个增至 8 个（新增「规则试算」）。
- （v1.5）§9.6.6 的 P2 由「直接内联编辑」改为「草稿 + 校验 + 发布」，P3 增加「配置导出/导入 + diff」。
- （v1.6）规则中心改为视图元数据驱动：新增 §9.6.9 与 TBD-15；FR-014 增补「只改 YAML 即可增删页签/列/筛选」验收项；§9.6.3 的 8 个页签改为 `rule_center_view.yaml` 的默认声明，不再是 Vue 组件内硬编码。
- （v1.7）细化单据推导的可操作入口：FR-015 增补 A/B 两入口与 v1.7 验收项；IF-007 补全 query 参数、响应信封与 400/403/404 矩阵；§9.6.4 重写为「入口 + 请求/渲染契约 + 场景能力矩阵 + 空错态 + 实现差距 + T1–T4 切片」；§9.6.3 页签增至 9 个（新增「单据推导」）；§9.6.9 补 `trace.decisions` / `trace.tab` 与渲染契约行；§9.6.6 的 P1/P2 验收同步（P1 仅要求接口可用，页面入口归入 P2）。
- （v1.8）P2 第一步「表述准确」收敛（仅新增字段，HTTP 状态与错误码不变）：①移除 `permission` 空场景——其依赖 `user_id` 而推导接口不传，属恒跳过的死分支，第二步以登录身份补回；②信封新增 `kind`（`hit/miss/skip/error/info`）与 `factor_sources`（`override/record/missing`），`detail` 升为一等字段；③`control_parameter` 改三级判定（全缺 → `missing / all_codes_missing`，部分 → `resolved / partially_resolved`，全中 → `resolved`）；④`default` 的 `detail.rules` 列出全部参与规则及 `applied/skipped/not_matched` 三态；⑤决策徽标、因子来源、空错态文案迁入 `trace.kinds / trace.factor_sources / trace.messages`，组件仅保留兜底。同步新增 §11 第二步方案（本期仅评审，不实施；全集口径已定，见 §11.9）。
- （v2.1）新增 §13 元数据驱动与单一事实源（SSOT）规范：术语与事实源登记、`RuleDescriptor` 唯一契约、13 项 SSOT 审计（F-13-01~13）、三层闭合矩阵、派生/缓存/快照边界、INV-SSOT-1~10、验收与 TBD-26~30；同步修正 FR-012 / FR-014 验收、§9.6.1 示例（移除不存在的 `control_parameter_value` / `effective` / 数组 `factors`）、§9.6.2（审批适配器现状 + `include_draft` 待补）、§9.6.3 兜底口径、§9.6.9（未知 key 加载期失败、`version: 2`）、§12.5 示例标注。
- （v2.2）澄清单据流语义本体：新增 §14「数量关系模型」——边=源行侧消耗量、上游累计下游消耗、未结量=源量−累计、Σ 守恒；字段拷贝降为派生填充策略（FR-006 同步补充语义本体与两条验收）；显式声明单表/头行两种幂等键及「同单多行」约束；确认不引入数量时段（`pool` 仅逻辑消耗池，不是时间桶，TBD-31 关闭）；新增 INV-FLOW-1~5、验收清单与 TBD-32。
- （v2.2 落地）头行模式「一源行 = 一目标行」显式化：宽松幂等预查回读既有边数量，数量相同才重放；数量不同返回 `HEAD_LINE_MULTI_NOT_SUPPORTED`（不静默吞量）。实现见 `doc_flow_derive_engine._find_edge_loose` / `_derive_core`，契约测试见 `test_doc_flow_batch.py::test_same_source_same_head_different_qty_rejected`。

### 10.8 二次确认（规则语义范畴，v2.0）

对 §12 的结论做了第二轮取证，**修正 4 处、确认 3 条**。

**修正项**

| # | 上一版结论 | 二次确认事实 | 处理 |
|---|---|---|---|
| 1 | Oracle Value Set 有「三种校验类型」 | 官方与社区共同口径为 **8 种**：None / Independent / Dependent / Table / Special / Pair / Translatable Independent / Translatable Dependent；`$FLEX$` 可绑定上下文 | 表述降级为「常用三类（Independent / Dependent / Table）」，完整枚举入 §12.3 |
| 2 | NetSuite 无声明式规则引擎（覆盖矩阵记 ○） | 官方「Creating Formula Fields」：custom field 的 **Validation & Defaulting** 子页签支持 Formula（NetSuite Tags + SQL Expressions）；勾选 `Store Value` 决定是否动态重算 | 矩阵「派生/计算」由 ○ 上调为 ◐，备注「声明式但无独立规则对象」 |
| 3 | SAP MDG 的 required / referential integrity / value range 依据为期刊论文 | 找到 SAP MDG BRFplus Configuration Guide（厂商培训材料），原文「use BRFplus to define rules for checking attribute values or to derive them」 | 证据级别由「第三方期刊」升为「厂商培训材料」，结论不变 |
| 4 | 「SaaS 平台普遍缺少 access-sequence 式 specificity」表述为事实 | 未找到任一厂商规范承认「缺失」；该判断由本项目横向对比归纳得出 | 标注为**本方案归纳，非厂商规范**，与 §11.2 的置信度纪律一致 |

**确认项（结论不变，可作设计依据）**

1. Workday 官方明确四类 condition rule：`entry` / `validation` / `while running` / `exit`。
2. ServiceNow Data Policy 服务端强制：官方 SDK 原文「enforce field mandatory and read-only rules server-side across all interfaces … cannot be bypassed, unlike client-side UI Policies」。
3. SAP 条件技术为「候选集 + most-specific-first + 命中即停 + 回退」，与 determination 同构。

**顺带发现的实现不一致（非研究结论）**

`rule_center_view.yaml` 的 `filter_options.rule_type` 含 `line_type`，而 `RuleCatalogService._line_type_descriptors()` 实际下发 `rule_type='line_type_assignment'`，该筛选项当前恒为空。归入 TBD-22 一并修正。

**对既有章节的影响**

- §7.1 技术约束增补「不新增 `RuleType` 枚举」的边界（已改）。
- FR-014 的 `rule_type` 筛选需拆为 `semantic_type` / `source` 两组（TBD-22）。
- §12 按修正后口径编写；`constraint` 二级化（TBD-23）不改变现有 `RuleEngine` 求值路径。

---

## 11. 规则链与规则全集方案（v1.8 新增，本期仅评审）

> 触发：FR-015 现在能回答「某个场景的一个结论」，但回答不了「这张单到底牵涉哪些规则、谁先谁后、彼此的输入输出怎么传递」。
> 本章是第二步设计：L0 已落地；L1 及以上本期不实施，待评审确认后再排期。

### 11.1 现状差距

| 现状 | 缺口 |
|---|---|
| 6 个场景各自一个信封，通常只给一条 winner | 同一字段的其余候选规则（被覆盖、被跳过）不可见 |
| 引擎已有规则链能力（`RuleDependencyAnalyzer` + 拓扑执行），trace 未表达 | 用户看不到 A 的输出如何成为 B 的输入 |
| `doc_flow` 只列下游规则声明 | 跨单据的实际执行链无法回溯 |
| 场景即分组容器 | 想换一个维度（按字段 / 按状态 / 按审批）看，必须改代码 |

### 11.2 头部产品对照（含取证）

> 取证日期 2026-11-07。置信度：高 = 官方文档明确；中 = 官方文档间接或旧版；低 = 仅第三方资料或机制级认知。
> **未取证条目不得在评审中当作事实引用**。

| 产品 | 已取证机制 | 可借鉴 | 不照搬 | 置信度 |
|---|---|---|---|---|
| Salesforce Flow | Debug 运行时按 element 展示运行时值与路径（官方原文 “view debug details about how the flow runs”）；运行实例官方称 **interview**；持久化逐元素日志仅屏幕流有 `FlowInterviewLogEntry` | 一次运行 = 一条记录 + 节点级输入输出 | 重量级调试器交互 | 中高 |
| ServiceNow Flow Designer | **Execution details** 逐 item 展示 runtime state、duration、input/output；Decision Table 按 Order 逐行求值、**首个匹配即返回** | 执行详情的数据结构（节点 + 时长 + 输入输出） | 断点 / 逐行 Debugger | 高（执行详情）/ 中（决策表） |
| Camunda DMN | DRD 用 `requiredDecision` 表达决策依赖；评估结果含 `ruleId` / `ruleOrder`；`HistoricDecisionInstance` 按输出子句与命中规则留档 | 静态依赖图 + 命中规则回传 + 历史实例 | BPMN/DRD 全量建模成本 | 高 |
| Drools / KIE | Agenda 为激活队列；优先级由 **salience** 决定，官方术语 **conflict resolution**，默认 Salience + LIFO；Agenda View 界面说明仅见于 5.3 旧版文档 | 展示「为什么这条先执行」 | `salience` / LIFO 冲突消解策略 | 中高 |
| SAP BRFplus | **未找到官方依据**：仅第三方培训材料提到 `FDT_LEAN_TRACE` / `FDT_PROCESS_LOG`，逐表达式中间值待核 | 暂不引用 | —— | 低 |
| IBM ODM / FICO Blaze / 钉钉宜搭 / 简道云 / 金蝶苍穹 / 用友 YonBuilder / Odoo | 机制级认知，未逐条取证（Odoo 无统一 trace 为反例） | 仅作方向参考 | 私有 DSL、插件机制 | 低–中 |

**证据链接**

- Salesforce：[Flow 官方 PDF](https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/extend_click_automate.pdf)、[FlowInterviewLogEntry（API 256.0）](https://developer.salesforce.com/docs/atlas.en-us.256.0.object_reference.meta/object_reference/sforce_api_objects_flowinterviewlogentry.htm)
- ServiceNow：[Flow execution details（Australia）](https://www.servicenow.com/docs/r/australia/build-workflows/workflow-studio/flow-execution-details.html)、[Flow debugger](https://www.servicenow.com/docs/r/australia/build-workflows/workflow-studio/flow-debugger.html)
- Camunda：[Decision Requirements Graph（8.10）](https://docs.camunda.io/docs/components/modeler/dmn/decision-requirements-graph/)、[DMN History（7.24）](https://docs.camunda.org/manual/latest/user-guide/process-engine/decisions/history/)
- Drools：[Rule Engine 8.32](https://docs.drools.org/8.32.0.Final/drools-docs/docs-website/drools/rule-engine/index.html)、[Agenda View（5.3）](https://docs.drools.org/5.3.0.Final/drools-expert-docs/html/ch08.html)

**修正说明（相对上一版）**

- 原表把「ServiceNow 决策表 specific→generic 排序 + 命中行高亮」写成事实，官方无依据 → 已降级为「按 Order 逐行、首个匹配即返回」。
- 原表把「SAP BRFplus 有 trace/中间值」写成事实，未找到官方文档 → 已标注待核，不作为设计依据。
- 「一次评估 = 一条 trace」是**我们的设计选择**（Salesforce 仅屏幕流持久化逐元素日志，Camunda 才全量留历史），不是行业硬规范。

**三条设计共识（本方案归纳，非厂商规范）**

1. **一次评估 = 一条 trace 记录**：含输入快照、命中标识、命中位置、输出、耗时。
2. **依赖双层表达**：模型期 DAG（规则之间靠哪个字段相连）+ 运行期顺序列表（`parent_id` / `seq`，反映条件跳过后真实顺序）。
3. **UI 三件套**：可折叠 trace 树 + 命中位置高亮 + 每步输入/输出对照。

**明确不照搬**：Drools `salience` / LIFO 冲突消解、全量 working memory 快照、断点/单步调试器、仅以决策表行号表达命中、trace 默认关闭并定期删除。

### 11.3 运行期 trace 节点（信封 v2）

在现有信封上**只增不改**（后端 `_envelope` 扩展、前端按列渲染）：

| 字段 | 类型 | 阶段 | 说明 |
|---|---|---|---|
| `node_id` | string | L1 | 稳定节点标识，`{trace_id}:{seq}` |
| `parent_id` | string \| null | L1 | 上游节点；链式规则必填 |
| `seq` | int | L1 | 运行期执行序号，全局递增 |
| `stage` | string | L1 | `before_save / validate / calc / approve / status_transition` |
| `rule_id` | string \| null | 已有 | 命中的规则；未命中时为候选规则 ID 列表的首项或空 |
| `match` | object | L1 | `{conditions: [{field, op, expected, actual, passed}], matched: bool}` |
| `factors` | object | 已有 | 该节点实际读取的因子快照（只存参与判定的字段） |
| `output` | object | L1 | 该节点写出的字段与值（`default` 场景为赋值结果，`state_transition` 为目标状态） |
| `kind` / `decision` / `reason` / `elapsed_ms` | — | 已有 | v1.8 语义 |

约束：`seq` 在同一 `trace_id` 内唯一；`parent_id` 必须指向已存在的 `node_id`，否则加载期报错；节点总量 ≤200，超出置 `truncated: true` 并返回各 `kind` 计数。

> **落地状态（v1.9 / L1 已实施）**：后端由 `RuleTraceService._decorate_steps()` 统一补 `seq / node_id / parent_id / stage / match / output`；`MAX_TRACE_NODES = 200` 只截断返回体积，`kind_counts` 仍按完整求值结果统计（截断不影响求值）。L1 不跨对象递归，`parent_id` 恒为 `null`（子 trace 挂父节点属 L3）；`match.conditions` 仅对 `state_transition` / `control_parameter` / `line_type` 三个场景回填可核对项，其余场景留空，不臆造比对项。前端文案全部来自 `rule_center_view.yaml` 的 `trace.scenario_labels / stages / scopes / rules_columns / conditions_columns`。

### 11.4 规则全集分层

对目标 BO，规则全集由三类组成，界面上同表展示、用 `scope_kind` 区分：

| 类别 | 判定 | 典型原因 |
|---|---|---|
| `evaluated` | 本次实际参与求值（含 `miss` / `skip`） | 命中、条件不满足、维度不匹配 |
| `not_triggered` | 相关但未进入求值 | `state_mismatch` / `stage_not_reached` / `scope_mismatch` / `not_instrumented` |
| `downstream` | 通过 `doc_flow` / `derive` 影响其他 BO | 下游单据默认值、状态联动 |

纳入口径（可配，默认值即 L1 标准）：

1. 规则声明 `scope_bo` 命中该 BO；
2. 规则 `target_field` 出现在该 BO 的写入路径（默认值 / 校验 / 状态动作）；
3. 上下游各一跳（`max_depth=1`）。

禁止把「未在本 BO 声明且无字段关联」的规则凑数进来——否则规则全集会退化成噪音列表。

### 11.5 双层依赖

**模型期（静态 DAG）**：复用 `RuleDependencyAnalyzer.analyze()`，边补语义：

```yaml
edges:
  - from: rule_a
    to: rule_b
    via_field: unit_price     # A 写、B 读
    kind: derive              # derive | validate | gate | flow | approval
```

**运行期（动态链）**：`parent_id` + `seq`。两者不一致属正常现象（条件跳过后拓扑序 ≠ 执行序），界面以运行期为准，静态图只做导航。

不变量：`ImplicitRuleChainExecutor` 保持无生产调用方（`rule_executor.py` 已有守卫），链执行仍由 `RuleEngine.execute_rules` 的拓扑序承担。

### 11.6 UI 形态

1. **规则全集表**（默认）：一行一规则，列 = 状态 / 规则 / 场景标签 / 命中位置 / 耗时；展开行为条件项 diff（期望 vs 实际）+ 输入输出对照。场景降级为筛选 `tag`，不再是分组容器。
2. **链视图**（可选 tab）：静态 DAG（Mermaid）+ 运行期顺序列表；点节点高亮对应表行，点表行定位图上节点。
3. **命中位置**：`rule_id` 跳 YAML 声明（`source=bo_yaml`）或配置详情（`source=control_parameter / line_type`），复用现有详情页路由。

### 11.7 分档与验收

| 档 | 内容 | 验收 |
|---|---|---|
| L0（已完成） | 场景分组 + `kind` + `factor_sources` + `default.detail.rules` | 现有 `test_rule_center_api.py` 全绿 |
| L1（已完成） | 信封补 `node_id/parent_id/seq/stage/match/output`；前端规则全集表 + 展开行；场景改筛选 | 单测覆盖字段与 `seq` 唯一性；payload ≤200 节点有截断标记；页面无写死中文 |
| L2 | 链视图：`GET /api/v2/rules/rule-chain`（只读，复用 Analyzer）+ 图与表联动 | 图节点数 = 运行期节点数；点选联动可用；无生产判定改动 |
| L3 | 跨单据链：`doc_flow` 递归一层，子 trace 以 `parent_id` 挂到主 trace | 递归深度上限可配；超限标注 `truncated` |
| L4（可选） | 持久化 `rule_trace` 表 + 保留期 | 独立 DDL 审批；默认关闭 |

分档原则：L1 只改展示契约，L2 才新增接口，L3 涉及跨对象递归（性能与权限边界需要单独评审）。

> **L1 验收记录（2026-11-08）**：`meta/tests/test_rule_center_api.py` 新增 `test_node_fields_and_seq`（字段/`seq` 连续/`node_id` 唯一）、`test_nodes_truncated_when_exceed_limit`（上限截断 + 计数完整）、`test_state_transition_match_and_output`（条件回填与写出值）；`test_rule_center_api.py` + `test_rule_simulate_api.py` 共 56 passed；`npm run build` 与 ESLint 均通过。

### 11.8 风险与非目标

- **口径风险**：`default` 走 `ActionExecutor.dry_run_defaults`，与生产写入不是同一执行实例；L1 只标注来源，不做"生产回放"承诺。
- **体积风险**：条件项 diff 会放大 payload，必须有节点上限与截断标记。
- **顺序风险**：静态 DAG 的拓扑序不能替代运行期 `seq`。
- **权限风险**：`permission` 场景需以登录用户身份计算；若 L1 补回，禁止从 query 取 `user_id`（可越权）。
- **非目标**：断点/单步调试、working memory 全量快照、冲突消解策略配置、决策表行号定位、trace 默认关闭。

### 11.9 待决策

> 2026-11-07 评审结论：**本期不实施，仅评审方案**；全集成口径已定为「声明在本 BO + 字段写入路径 + 一跳（`max_depth=1`）」，其余条目待 L1 排期时再定。

| ID | 事项 | 选项 | 结论 |
|---|---|---|---|
| TBD-17 | 规则全集口径 | 仅声明在本 BO / 加字段写入路径 / 再上下游一跳 | **已定**：加字段写入路径 + 一跳，`max_depth` 可配 |
| TBD-18 | 链视图形态 | 仅顺序列表 / 列表 + DAG / 仅 DAG | 待评审（建议列表为默认，DAG 作可选 tab） |
| TBD-19 | 跨单据深度 | 不跨 / 一跳 / 可配 | 待评审（建议一跳起步） |
| TBD-20 | trace 持久化 | 不落库（现状）/ 落库 + 保留期 | 待评审（建议维持不落库） |
| TBD-21 | `permission` 场景回补 | 不补 / 以登录身份补 | 待评审（建议 L1 以会话用户补，禁止 query 传入） |

---

## 12. 规则语义范畴与类型分层（v2.0 新增，方案待评审）

> 触发：FR-014 的规则中心已能聚合 8 类来源，但「规则类型」在实现里同时承担了**语义**（`default`）、**来源**（`control_parameter`）、**场景**（`doc_flow`）三种含义。新增规则形态时无法判断该不该加枚举，筛选也无法按「约束 vs 赋值」这类真正想知道的口径切分。

### 12.1 四个正交维度

| 维度 | 回答的问题 | 取值 | 承载位置 |
|---|---|---|---|
| 语义 | 这条规则产出什么 | 赋值 / 约束 / 决策 / 动作（§12.2） | 元模型 `semantic_class` + `semantic_type` |
| 求值时机 | 什么时候生效 | 加载期 / 保存前 / 保存时 / 保存后 / 查询时 / 异步 | 元模型 `stage`（与 §11.3 的 `stage` 同源） |
| 作用域 | 对谁生效 | 字段 / 跨字段 / 单记录 / 记录集合 / 单据流 | 元模型 `scope`（复用 `RuleScope`：field / cross_field / object / set / cross_object；`set` 为待补值，单据流用 `cross_object`） |
| 表达形式 | 怎么算出来 | 声明式 / 决策表 / 表达式 / 脚本 | 载体（L1 YAML / L2 DB / L3 Python） |

**不变量**：任一规则都能在四轴上各取一值；不得用单一 `rule_type` 同时编码多轴。四轴中只有「语义」进目录筛选，「时机 / 作用域」进详情，「表达形式」进 `layer`。

### 12.2 语义四主类与 16 子类

| 主类 | 子类 | 产出 | 判定所需参照系 | 本项目现状 |
|---|---|---|---|---|
| **ASSIGN** 赋值 | `default` 默认 | 字段值 | 因子匹配 | 已有 `RuleType.DEFAULT` |
| | `derivation` 派生 | 字段值 | 其他字段 / 其他记录 | 已有 `RuleType.DERIVATION`（声明多、执行少） |
| | `computation` 计算 | 字段值 | 表达式 | 已有 `RuleType.COMPUTATION` |
| | `aggregation` 聚合 | 字段值 | 子记录集合 | **缺口**：现用 `computation` 表达，无 `group_by` 契约 |
| **CONSTRAINT** 约束 | `value_list` 值列表 | 通过 / 拒绝 | 本地枚举 | 已有（`VALIDATION` + enum） |
| | `range` 区间 | 通过 / 拒绝 | 区间 | 已有（`VALIDATION`） |
| | `reference` 参照完整性 | 通过 / 拒绝 | 外部实体存在性 | **缺口**：仅外键存在性，无「状态 / 组织」限定参照 |
| | `cross_field` 跨字段 | 通过 / 拒绝 | 同一记录其他字段 | 已有（`VALIDATION` / `CONSTRAINT`） |
| | `uniqueness` 唯一性 | 通过 / 拒绝 | 全集合 | **缺口**：仅 DB 唯一索引，无业务口径的条件唯一 |
| | `cross_record` 跨记录 | 通过 / 拒绝 | 其他记录 | **缺口**：散落在 L3 guard service |
| **DECISION** 决策 | `determination` 确定 | 候选值 / 分支 | 候选集 + 优先级 + 回退 | **部分**：`control_parameter` 已实现候选链，未抽象为通用能力 |
| | `decision_table` 决策表 | 输出行 | 条件矩阵 | **缺口**：现用多条 `derivation` 近似，无 hit policy |
| **ACTION** 动作 | `trigger` 触发 | 副作用 | — | 已有 `RuleType.TRIGGER` |
| | `state_transition` 状态流转 | 目标状态 | 状态图 | 已有 `RuleType.STATE_TRANSITION` |
| | `approval` 审批 | 审批链 | 策略条件 | 已有（DB 层），无 `RuleType` 枚举 |
| | `doc_flow` 单据流 | 目标单据 / 字段 | 上下游关系 | 已有（DB 层），无 `RuleType` 枚举 |
| | `notification` 通知 | 消息 | 事件 | **缺口**（一期非目标） |

**三条边界规则**

1. **「计算算不算规则」**：判定标准为「可声明、可禁用、可追溯、可测试」四特征同时满足。`computation` / `aggregation` 属**赋值型**（产出值 + 依赖图），`constraint` 属**判定型**（产出结论 + 反例）；在 trace 中分别落在 `output` 与 `decision`，不得混用。
2. **`permission` 不纳入业务规则范畴**：受众、Explain 语义、授权模型均不同，维持 TBD-8「跳转权限中心」。
3. **`default` ≠ `determination`**：前者单向幂等（无值则填），后者有候选集与回退（命中即停）。当规则声明 `candidates` + `hit_policy` 时按 determination 处理，否则按 default。

### 12.3 约束子类的参照系（修正后口径）

「约束」的本质差异不是字段数，而是**判定所需的参照系**：

| 参照系 | 子类 | 代表实现 | 可配置边界 |
|---|---|---|---|
| 本地枚举 | `value_list` | Oracle Value Set **Independent**；D365 `optionset` | 值集可扩，主键冻结 |
| 区间 | `range` | Oracle Value Set 的 min / max；D365 Business Rule | 阈值可配 |
| 外部实体存在性 | `reference` | Oracle Value Set **Table**；SAP MDG referential integrity | 目标对象 / 过滤条件可配 |
| 上下文绑定 | `reference`（受限） | Oracle Value Set **Dependent**（`$FLEX$`）；Salesforce Dependent Picklist | 父字段可配 |
| 其他字段 | `cross_field` | Oracle Cross-Validation Rules；Odoo `@api.constrains` | 表达式可配（白名单内） |
| 全集合 | `uniqueness` | Odoo `_sql_constraints`；Salesforce Duplicate Rules | 匹配键 + 模糊度可配 |
| 其他记录 | `cross_record` | ServiceNow Data Policy；NetSuite `validateField` | 一期不配置化 |

> Oracle Value Set 完整枚举为 **8 种**（None / Independent / Dependent / Table / Special / Pair / Translatable Independent / Translatable Dependent）；上表只列与本项目相关的 4 种，`Pair` / `Translatable` 依赖多语言主数据，暂不引入（见 §10.8 修正 1）。

### 12.4 命中策略（hit policy）通用化

决策类规则统一用 `hit_policy` 表达「多条命中怎么处理」，不再把 `specificity_rank` 做成 `control_parameter` 的私有字段：

| `hit_policy` | 语义 | 头部对应 | 本项目 |
|---|---|---|---|
| `first` | 按稳定排序取首个命中 | SAP access sequence；ServiceNow Decision Table Order；Drools salience | `default` / `control_parameter` 现状 |
| `unique` | 至多一条命中，多条即冲突 | DMN `UNIQUE` | 待补 |
| `priority` | 取声明优先级最高的命中 | DMN `PRIORITY` | 待补（可用 `first` + priority 排序等价） |
| `collect` | 收集全部命中 | DMN `COLLECT`（含 Sum / Min / Max / Count） | 待补（与 `aggregation` 一并） |

**约束**

- `hit_policy=first` 时 MUST 声明稳定排序键（`priority` 或 `specificity_rank`），否则加载期报 `HIT_POLICY_UNORDERED`。
- `hit_policy=unique` 出现多命中时报 `RULE_MULTI_MATCH`，并回传全部 `rule_id`，不得静默取第一条。
- `hit_policy` 只对 `default` / `determination` / `decision_table` / `aggregation` 有意义；`constraint` 与 `action` 无多命中语义，声明该字段即加载期报错。

### 12.5 与现有 `RuleType` 的映射（不新增枚举）

| 现有 `RuleType` | `semantic_class` | `semantic_type` | 备注 |
|---|---|---|---|
| `DEFAULT` | assign | default | 声明 `candidates` 时升格为 determination |
| `DERIVATION` | assign | derivation | |
| `COMPUTATION` | assign | computation / aggregation | 有 `group_by` 时判 aggregation |
| `VALIDATION` | constraint | value_list / range / cross_field | 由 `constraint_kind` 细分 |
| `CONSTRAINT` | constraint | cross_field / cross_record | |
| `TRIGGER` | action | trigger | |
| `STATE_TRANSITION` | action | state_transition | |
| `PERMISSION` | —（排除） | — | 不进规则中心（TBD-8） |
| （DB 层，无枚举） | action | approval / doc_flow | `legacy_rule_type` 保持兼容 |

**`RuleDescriptor` 三轴拆分**（§9.6.1 的非破坏性增补）：

```json
{
  "rule_key": "control_parameter:PAYMENT_TERM",
  "semantic_class": "assign",
  "semantic_type": "default",
  "constraint_kind": null,
  "hit_policy": "first",
  "source": "control_parameter",
  "stage": "before_save",
  "scope": {"kind": "field", "bo": "sales_order"},
  "legacy_rule_type": "control_parameter"
}
```

- `source` **已存在**（§9.6.1），取值与 `RuleCatalogService.SOURCES` 一致（`bo_yaml` / `doc_flow` / `approval` / `control_parameter` / `line_type` / `state_machine` / `numbering` / `validation`）；本次不改其语义。
- 需要拆的是 `rule_type`：现状既装语义（`default` / `validation`）又装来源（`line_type_assignment`）。目标为新增 `semantic_type`（+ 可选的 `semantic_class` / `constraint_kind` / `hit_policy`），旧值平移到 `legacy_rule_type`。
- 上述 JSON 为三轴**增量示意**，不是完整描述符；完整字段与命名（`scope_bo` 为字符串、`source_tags`、`factors` 为对象）以 §13.2 为唯一契约，禁止并存 `scope: {kind, bo}` 两套形状。
- `legacy_rule_type` 一期保留供前端展示与筛选；二期前端改读 `semantic_type` + `source` 后删除。
- 视图元数据 `filter_options.rule_type` MUST 拆为 `semantic_type` 与 `source` 两组，并同时修正 `line_type` ↔ `line_type_assignment` 命名不一致（§10.8）。

### 12.6 缺口与优先级

| 缺口 | 归入 | 优先级 | 理由 |
|---|---|---|---|
| `reference` 参照完整性 | FR-012 加载期校验扩展 | P1 | 只声明校验，不新增执行引擎 |
| `uniqueness` 条件唯一 | FR-012 + 索引生成 | P1 | 可复用迁移，风险低 |
| `determination` 通用化 | `default` + `candidates` + `hit_policy` | P1 | 复用 `control_parameter` 已验证的候选链 |
| `cross_record` | 维持 L3 + 目录只读展示 | P2 | 需集合级求值，性能与权限未评估 |
| `aggregation` | `computation` 增 `group_by` 契约 | P2 | 现有单据已有汇总需求 |
| `decision_table` | 规则试算 + trace 渲染 | P2 | 需 hit policy；§11.2 / §11.9 已把「仅以行号表达命中」与「行号定位」列为非目标，故命中须回传 `rule_id`（可选 `row_key` 仅供人工定位） |
| `notification` | 一期非目标 | — | 属消息基础设施，不进规则收敛范围 |

### 12.7 不变量

1. 新增规则形态 MUST 优先用正交属性表达；确需新增 `RuleType` 时须证明「无法用 `semantic_class` + 子属性表达」，并在评审记录中留证。
2. API 响应中的 `rule_type` 不得再承担来源含义；兼容字段统一命名 `legacy_rule_type`。
3. 任何 `hit_policy=first` 的规则 MUST 有稳定排序键，保证「同一输入同一结果」。
4. 语义分类只影响目录展示与加载期校验，不改变现有执行路径；一期不改 `RuleEngine.execute_rules` 的求值顺序。

### 12.8 待决策

| ID | 事项 | 选项 | 建议 |
|---|---|---|---|
| TBD-22 | `rule_type` 三轴拆分 | 保持单字段 / 增 `semantic_class`+`semantic_type`+`source` / 仅前端拆 | 增字段 + `legacy_rule_type` 兼容（§12.5），并修 `line_type` 命名 |
| TBD-23 | `constraint` 二级化 | 不拆 / 按参照系拆 6 类 / 只拆 value_list+range | 按参照系拆，由 `constraint_kind` 承载 |
| TBD-24 | `hit_policy` 落地范围 | 仅决策类 / 全部规则 | 仅 `default` / `determination` / `decision_table` / `aggregation` |
| TBD-25 | `reference` / `uniqueness` 实施批次 | M1 / M4 之后 | M4 之后（先有目录与健康检查，再补校验） |

---

## 13. 元数据驱动与单一事实源（SSOT）规范（v2.1）

> 本节不新增功能，只回答四个问题：**同一语义由谁声明、谁读取、谁只能派生、谁必须失败**。
> 与本节冲突的旧表述（含 §9.6.1 / §9.6.2 / §9.6.9 的示例与碎句）以本节为准。

### 13.1 事实源分层与术语

| 术语 | 定义 | 可写 | 可读 |
|---|---|---|---|
| 事实源 owner | 某类语义的唯一权威载体 | 仅其写入入口 | 任何人经唯一读取入口 |
| 投影 projection | 为展示/检索做的实时归一，不新增语义 | 否 | 只读 owner |
| 派生 derived | 由 owner 计算出的值（`rule_key` / `source_tags` / `scope_of` / `factor_keys` / `links`） | 否 | owner 计算并下发；消费方不得复算 |
| 缓存 cache | 进程内短期副本 | 否 | 失效即重建；禁止写 DB/文件、禁止跨进程 |
| 快照 snapshot | 历史时点副本（审计） | 仅审计表 | 仅回滚重放；运行期禁止读取 |

四层归属不变（§1.1）；**视图元数据是呈现层 overlay，不是第四类业务事实**：不得承载判定、取值或第二份枚举。

**事实源登记表**

| 事实 | owner | 唯一读取入口 | 允许的投影/派生 | 禁止 |
|---|---|---|---|---|
| BO 规则定义 | BO YAML `rules` | `RuleProvider.get_rules` | 目录描述符 | 业务代码直接遍历 `meta_obj.rules`（FR-010 豁免除外） |
| 控制参数/行类型/审批/单据流 | L2 表（已 BO 化） | 各域 store / resolver | 目录、试算、推导 | 目录服务复制匹配算法 |
| 规则目录 | 实时聚合 | `RuleCatalogService.list_rules` | 前端表格 | 落库、另建目录表 |
| `rule_key` | 键生成器（唯一 helper） | 所有消费方 import | — | 各服务自行拼接前缀 |
| 视图结构（页签/列/筛选/动作/分区） | `rule_center_view.yaml` | `GET /rules/view-config` | 前端通用壳 | Vue 内硬编码页签/列/业务文案 |
| 枚举值域（source/scenario/stage/decision/kind/action/widget） | 代码常量 / `models_enums` | 对应服务常量 + 目录 API | YAML 只引用 id | YAML 或前端另立同义列表 |
| 展示文案（label/messages/kinds/scopes） | `rule_center_view.yaml` | view-config | 前端渲染 | 前端业务中文常量、后端拼中文 |
| 生效态（active/draft） | 主表 `status` | 各域 resolver（只读 active） | 目录行状态 | 另建草稿表；审计表参与运行读取 |
| 可编辑目标（BO/表/字段） | 各来源适配器声明 | 目录 `links.edit` | 前端跳转、发布服务 | 前端 `source→table` 映射、发布服务 `TARGETS` 常量 |
| 因子轴 | 因子维度声明（唯一） | 目录/推导 API 下发 `factor_keys` | YAML 只放 labels | 后端、YAML、前端各存一份数组 |

### 13.2 `RuleDescriptor` 契约（唯一定义处）

| 字段 | 类型 | 必填 | owner | 说明 |
|---|---|---|---|---|
| `rule_key` | string | 是 | 键生成器 | `{source}:{natural_key}`，全局唯一 |
| `name` | string | 是 | 来源 | 缺省回落 `rule_key` |
| `source` | enum(`SOURCES`) | 是 | 代码 | **载体 carrier**，不是业务域 |
| `source_tags` | string[] | 是（可空） | 目录派生 | 逻辑归属（如 `validation`）；不得冒充 carrier |
| `rule_type` | string | 是 | 来源/代码 | 过渡期可为语义值或来源派生值（`control_parameter` / `line_type_assignment` / `doc_flow` / `approval`）；**不得为空** |
| `legacy_rule_type` | string? | 否 | 目录 | §12.5 拆分后保留旧值，二期删除 |
| `semantic_type` / `semantic_class` / `constraint_kind` / `hit_policy` | enum? | 否（预留） | 代码 | §12.5 目标字段；未完整落地前不得半套下发 |
| `scope_bo` | string | 是（全局规则可空） | 来源 | 作用 BO；规划 `scope{kind,bo}` 见 TBD-22 |
| `factors` | object | 是 | 来源 | 键为因子轴；`domain` 为业务域投影；未声明为 `null` |
| `layer` | enum | 是 | 来源 | `L1` / `L2` / `L3` |
| `configurable` | bool | 是 | 来源 | 仅 L2 可编辑域为 `true` |
| `status` | enum | 是 | 来源 | `active` / `inactive` / `draft`；草稿与生效值同表 |
| `priority` | int? | 否 | 来源 | first-match 排序辅助 |
| `updated_at` | ISO8601 | 是 | 来源 | 目录不另维护时间 |
| `detail` | object | 是 | 来源 | 原文/快照/取值矩阵，只读 |
| `links` | object? | 否 | 适配器 | `edit` / `publish` / `rollback` / `explain`；M1 未实现（F-13-05） |

约束：

1. 新增/改名字段 MUST 先改本节表格，再改实现与示例；禁止只在示例中出现。
2. 消费方（试算 / 推导 / 发布 / 前端）禁止自行拼接 `rule_key`、推导因子键、维护 `source → 目标表`。
3. `source` 过滤只匹配 carrier；逻辑归属用独立 `tag` 过滤（TBD-26）。
4. 同一字段不得同时下发两套形状（例如 `scope_bo` 与 `scope{}` 并存）；过渡期只能有一套，另一套标注「预留」。

### 13.3 双写 / 双声明审计（本次检查结论）

| ID | 第二事实源 | 证据 | 风险 | 处置 | 优先级 |
|---|---|---|---|---|---|
| F-13-01 | 来源枚举两处声明 | `rule_catalog_service.py:25-31`；`rule_center_view.yaml:19-38`；`_validate_view_config`（`rule_catalog_service.py:292-316`）只校验页签引用，不做集合等值 | 单侧新增来源 → 页签请求未知来源或来源无文案；启动不报错 | 加载期双向等值（§13.4） | P0 |
| F-13-02 | 推导值域三处声明 | `rule_trace_service.py:26`（scenarios）、`:33`（DIMENSION_FIELDS）、`:37`（DECISION_KINDS）、`:58`（STAGE_MAP）；`rule_center_view.yaml:191/201/213`；前端 `RuleCenterPage.vue:417`、`RuleTracePanel.vue:289` | 改一处漏一处 → 选项与后端不认、分组错位、数组漂移 | 代码为值域 owner；YAML 只放文案；API 下发 `factor_keys`；前端删数组 | P0 |
| F-13-03 | `rule_type` 筛选项已漂移 | `rule_center_view.yaml:93`；实际值 `rule_catalog_service.py:110/152/185/212/243` | `line_type` ≠ `line_type_assignment` ⇒ 该筛选项恒空；缺 `state_transition` / `permission` ⇒ 无法筛选；来源值混入语义轴 | 按 §12.5 拆 `source` / `semantic_type`；候选值由描述符值域派生或等值校验；删除手写列表 | P0 |
| F-13-04 | `rule_key` 生成四处重复 | `rule_catalog_service.py:114/152/185/212/243`；`rule_simulate_service.py:252/307`；`rule_trace_service.py:423/446`；`rule_config_publish_service.py:412` | 前缀/天然键格式改动不同步 → 详情、历史、试算互相找不到 | 单一键生成器，全部 import（§13.2） | P0 |
| F-13-05 | 可编辑目标两处硬编码 | `rule_config_publish_service.py:26`（`TARGETS`）；`RuleCenterPage.vue:427`（`TARGET_BY_SOURCE`）、`:536` 使用；目录未下发 `links` | 新增可编辑来源要改后端+前端，违背 FR-014「零改动」 | 适配器声明 `edit/publish target`，目录下发 `links`；删除两处常量 | P1 |
| F-13-06 | 契约存在两套示例 | §9.6.1 示例（`source=control_parameter_value`、`scope{}`、`factors[]`、`effective`、`links`）vs §12.5 示例 vs 实现（`scope_bo`、`factors{}`、无 `links`） | 前后端按不同示例实现，联调才暴露 | §13.2 唯一定义；§9.6.1 示例已校正；预留字段显式标注 | P1 |
| F-13-07 | 前端文案/选项第二份 | `RuleCenterPage.vue:369`（`FALLBACK_CONFIG`）、`:418`（`SIMULATE_HINTS`）、`:431`（`ACTION_LABELS`）、`:432`（`BLOCK_LABELS`）、`:212/214/221/273/304/307/314/317/322`（表格与按钮中文）；`RuleTracePanel.vue:292`（`FALLBACK_MESSAGES` 与 `rule_center_view.yaml:288` 同键重复） | 改 YAML 不生效；中英文双份；违反 FR-014 | 前端仅保留通用交互动词；业务文案全量入 YAML；兜底只留空态，由契约测试锁定键集合 | P1 |
| F-13-08 | `source` 过滤混用逻辑归属 | `rule_catalog_service.py:369-374`（`source in wanted or wanted ∩ source_tags`）、`:111`（`validation` 标签） | `source=validation` 返回 carrier=`bo_yaml` 的规则；同一筛选两种语义，结果不可解释 | `source` 只匹配 carrier；新增 `tag` 过滤；`validation` 从 sources 降为 tag（TBD-26） | P1 |
| F-13-09 | 未知枚举静默降级 | `rule_catalog_service.py:369-385` 无值域校验（未知值 → 空列表）；`rule_center_view.yaml:232`「未知场景回落通用两列」；§9.6.9 原有「未知 key 记 warn 并跳过」（v2.1 已改为加载期失败）；前端 `RuleCenterPage.vue:798/802` 文案缺失回落 key | 拼写错误表现为「没数据 / 英文键」，无告警 | 请求值域 → 400；元数据未知键 → 加载期失败；来源读失败 → `sources.status=error` + 健康检查 | P1 |
| F-13-10 | 版本与配置指纹缺失 | YAML 实际 `version: 2`（§9.6.9 示例已于 v2.1 对齐）；`get_view_config` 不校验版本；API 不回传 hash | 破坏性改版无法识别；前端缓存无法判断失效；文档与文件漂移 | 加载期校验受支持版本；view-config 回传 `{version, hash}`；破坏性变更升版登记 | P2 |
| F-13-11 | 草稿可见性双机制 | §9.6.2 要求 `include_draft`，实现无该参数；前端以 `status=active` 默认过滤 | 文档与实现两套口径；目录与运行时可能不一致 | 二选一写入 §9.6.2；生效态判定收敛为单一函数 | P2 |
| F-13-12 | 因子轴四处声明 | `rule_trace_service.py:33`；`rule_center_view.yaml:213`；`RuleCenterPage.vue:417`；`RuleTracePanel.vue:289` | 新增因子需改四处 | 因子轴元模型/后端单一常量；API 下发；YAML 只放 labels（TBD-27） | P2 |
| F-13-13 | 缓存与降级边界未成文 | `rule_catalog_service.py:329-345`（来源异常降级）、`:276-290`（view-config 进程缓存，无失效入口） | 有人把「来源读失败」当「空目录」；发布后目录最长 60s 旧值 | 明确两层语义（§13.4）；发布/回滚后主动失效缓存；缓存不得持久化 | P2 |

### 13.4 加载期闭合校验与运行期零解析

三层语义：

- **L0 加载期（启动 / CI）**：封闭枚举与引用关系必须闭合，任一不满足 → 启动失败（配置错误，错误码稳定）。视图元数据随 BO schema 一起校验。
- **L1 请求期**：用户输入（筛选值、推导参数）值域校验 → 400；不得静默返回空结果。
- **L2 运行期**：规则解析只读 owner；视图只读内存副本；来源读取失败允许降级，但 MUST 在响应 `sources.status` 与健康检查中显式可见。

**闭合矩阵**

| 集合 | owner | 校验 | 未闭合处置 |
|---|---|---|---|
| view `sources` | `RuleCatalogService.SOURCES` | 双向等值 | 启动失败 |
| `tabs[].sources` | `SOURCES` + `NOT_INSTRUMENTED` | ⊆；`not_instrumented` 不得出现在要求数据的页签 | 启动失败 |
| `tabs[].kind` | `{table, simulate, health, rule_trace}` | 封闭枚举 | 启动失败 |
| `tabs[].columns` | `column_labels` 键 | 引用闭合 | 启动失败（取消 warn 跳过） |
| `tabs[].filters` | `filter_labels` + 已实现筛选项 | 引用闭合 | 启动失败 |
| `tabs[].actions` | 动作注册表 | 封闭枚举 | 启动失败 |
| `detail.sections[].widget` | widget 注册表 | 封闭枚举 | 启动失败 |
| `trace.scenarios` | `TRACE_SCENARIOS` | ⊆（未接入场景不得出现在 UI） | 启动失败 |
| `trace.scenario_labels` / `scenario_rules` / `messages` / `source_types` | `trace.scenarios` + 代码输出 | 键集合等值 | 启动失败 |
| `trace.stages` | `STAGE_MAP` 值域 | 键集合等值 | 启动失败 |
| `trace.factor_labels` | 因子轴 | 键 ⊆ 因子轴 | 启动失败 |
| `trace.scopes` / `decisions` / `kinds` | `scope_of` / `DECISION_KINDS` | 值域等值（文案可多不可少） | 启动失败 |
| `filter_options.*` | 静态封闭（status/severity/enabled/configurable）或描述符值域（source/rule_type/domain） | 静态=封闭枚举；动态=服务端派生 | 手写动态列表 → 启动失败 |
| 描述符 `rule_type` | `RuleType` 8 值 + 已登记来源派生值 | 非空且 ∈ 白名单 | 来源读取失败（`status=error`） |
| 描述符 `factors` 键 | 因子轴 | ⊆ | 记 error 并进健康检查 |
| 请求 `source` / `rule_type` / `status` | 上述值域 | ∈ | 400 `RULE_FILTER_UNKNOWN_VALUE` |

**运行期零解析**：YAML 只在加载时解析一次；请求路径不得读文件、不得重新拼装枚举。目录 60s 缓存与 view-config 进程缓存都只是派生副本，失效即重建。

### 13.5 派生、缓存、快照的边界

- 目录 / 推导 / 试算 MUST NOT 落库（与 FR-015 同口径）；审计只记录写操作（发布 / 回滚）。
- 审计快照不是运行期事实源：运行时只读主表 `status=active`；回滚是把审计内容重放为**新的主表写入**，不得让 resolver 直读历史表。
- 缓存仅进程内；不得写 DB / 文件；发布或回滚后 MUST 主动失效目录与 view-config 缓存；缓存命中与否不得改变结果语义。
- 派生值（`rule_key` / `source_tags` / `scope_of` / `factor_keys` / `links`）由 owner 计算下发；消费方复算即视为 SSOT 违规（F-13-04 / F-13-12）。
- 文档派生：API 示例、Spec 示例、测试期望不得各自定义契约，统一以 §13.2 为准。

### 13.6 变更影响面：审计、发布、回滚、版本

- 写路径唯一：发布 = 主表状态迁移（`draft → active`，旧 `active → inactive`）；回滚 = 原子「写主表 + 记审计」；禁止只改审计。
- 审计最小字段：`target / rule_key / action / old_data / new_data / operator / at`；`rule_key` 必须由键生成器产出。
- 版本：
  - 视图元数据 `version` 为整数；破坏性变更（删字段 / 删动作 / 改语义）必须升版，加载期拒绝不支持的版本。
  - `semantic_*` 落地时，目录响应 MUST 携带 `contract_version`；前端按版本选字段，禁止猜字段。
- 生效时间（`effective_from/to`）当前未实现（TBD-30）；落地前，任何「定时生效」需求一律走发布动作，不得在业务代码里加时间判断。

### 13.7 L3 边界（不可配置化）

| 类别 | 示例 | 理由 |
|---|---|---|
| 安全 | 认证白名单、表达式白名单、审计哈希链 | 配置化即绕过治理 |
| 事务/并发 | 锁、序列原子性、幂等 | 正确性依赖数据库语义 |
| 算法 | 匹配算法、集合级求值（`cross_record` / `aggregation`）、排序稳定性 | 需要可证明的复杂度与性能边界 |
| 集成 | 外部协议、重试、熔断 | 非业务策略 |
| 求值器 | 条件 AST 求值、沙箱 | 注入面 |

配置化的准入条件（四条缺一不可）：

1. 有声明 schema；2. 有加载期校验；3. 有唯一读取入口；4. 有等价性测试。缺一 → 不得配置化。

**禁止措辞**：「也可配置化」「视配置而定」而不写 owner / schema / validator / 默认值 / 回滚路径。出现即视为规范缺陷。

### 13.8 不变量

1. **INV-SSOT-1** 一个语义只有一处声明（枚举、键格式、文案、目标映射均适用）。
2. **INV-SSOT-2** 视图元数据只引用 id，不内联取值、业务文案或目标表。
3. **INV-SSOT-3** 目录是投影：不落库、不复制匹配算法、不成为第二事实源。
4. **INV-SSOT-4** 缓存 / 快照 / 历史不是运行期事实源；运行期只读 owner。
5. **INV-SSOT-5** 未知枚举键必须失败（加载期启动失败 / 请求期 400），不得静默空结果。
6. **INV-SSOT-6** 可配置域必须同时具备 schema、validator、唯一入口、等价性测试。
7. **INV-SSOT-7** 文档示例必须来自实现契约；同一契约不得有第二套字段集。
8. **INV-SSOT-8** 派生值由 owner 计算并下发，消费方不得复算。
9. **INV-SSOT-9** 发布 / 回滚只写主表；审计只追加，不参与运行读取。
10. **INV-SSOT-10** L3 清单内不得出现「也可配置化」；清单外新增配置化必须走 INV-SSOT-6。

### 13.9 验收（可执行清单）

1. 新增 `test_rule_center_view_contract.py`：逐项断言 §13.4 闭合矩阵，失败信息必须给出具体键。
2. 目录契约测试：所有描述符必填字段完整、`rule_type` 非空、`source ∈ SOURCES`、`factors` 键 ⊆ 因子轴。
3. 请求负例：`GET /rules?source=__x__` / `rule_type=__x__` / `status=__x__` → 400 `RULE_FILTER_UNKNOWN_VALUE`。
4. 前端静态守卫：`RuleCenterPage.vue` 与 `RuleTrace/*.vue` 不出现 `source→table` 映射、业务中文常量、因子轴数组；白名单仅通用交互动词（查询 / 重置 / 刷新 / 关闭 / 取消 / 确定）。
5. 发布闭环：publish 后同名规则状态与值立即可见（缓存失效）；rollback 后主表恢复且审计新增一条。
6. 文档一致性门禁：§9.6.1 示例字段 ⊆ §13.2 表格且无表外字段（人工评审项，不写脚本）。
7. 全部经 `python d:\filework\test.py` 执行。

### 13.10 待决策（SSOT）

| ID | 事项 | 选项 | 建议 |
|---|---|---|---|
| TBD-26 | `source` / `source_tags` / `tag` 三轴收敛 | 维持 union 过滤 / `source` 只认 carrier + 独立 `tag` | 后者；`validation` 从 sources 枚举降为 tag，避免来源与逻辑域混用 |
| TBD-27 | 因子轴 owner | 后端常量 / 元模型 `dimension_levels.factor=true` / 目录配置 | 元模型声明，API 下发 `factor_keys`；YAML、前端只消费 |
| TBD-28 | 文案 i18n | 单语中文 / YAML 内 `{zh,en}` / 独立 i18n key 文件 | 若近期无多语言需求，保持单语但禁止前端复制；有需求时选独立 key 文件 |
| TBD-29 | 多租户覆盖层 | 不引入 / 引入覆盖层 | 若引入，必须定义 `tenant > org > default` 单一合并点，禁止各域自行合并 |
| TBD-30 | 视图元数据版本、热更新与生效时间 | 重启生效 / 发布即失效缓存 / 定时生效 | 一期重启生效 + `version/hash`；「定时生效」需独立设计，禁止散落业务代码 |

---

## 14 单据流语义本体：数量关系（v2.2 澄清）

> 本章修正一个此前的表述偏差：单据流不是「按规则拷贝字段生成下游单据」，而是**上游行按数量向下游分批派生、上游累计下游消耗量**。字段拷贝只是派生时的填充动作。
> 代码基线：`meta/core/doc_flow_schema.py`、`doc_flow_derive_engine.py`、`doc_flow_batch_engine.py`、`doc_flow_attach.py`。

### 14.1 本体定义（四个一等公民）

| 要素 | 定义 | 代码事实 |
|---|---|---|
| 边 | `(source_bo, source_id, source_item) → (target_bo, target_id, target_item)` 的派生事实 | 7 元组唯一索引 `uq_doc_flow_idem` |
| 数量 | `quantity` = **源行侧消耗量**（本边让源行被消耗多少，≥0，对标 RFMNG） | `doc_flow_schema.py` 字段 `quantity` |
| 累计 | 上游行已消耗 = 同 `(源行, pool)` 下 active 正向 − active 红字 | 视图 `v_doc_flow_consumed_qty` |
| 未结 | `open_qty = 源行数量字段值 − consumed_qty` | 引擎 `_replay_result` / 批量默认派生量 |

守恒约束：每次派生后 MUST 满足「累计消耗 ≤ 源行数量」，越界即 `OVER_DERIVE` 并回滚整事务。

**不做物化的 open_qty 通用视图**：源行数量在异构业务表里，无法通用 JOIN；未结量由使用方/引擎相减（沿用 Phase 1 决议）。

### 14.2 字段拷贝的定位

派生时目标字段的填充链固定为三段，且**数量字段被刻意排除**：

1. 同名全量直拷：`copy_field_ids = 目标持久字段 ∩ 源持久字段 − 数量字段`；
2. `field_map` 改名映射；
3. `target_data` 静态覆盖（调用方显式传值）。

结论：

- 「copy control」在本 spec 中只作**派生填充策略**的别名，不得再作为模型名使用；
- 目标数量由引擎按派生量显式写入，任何字段映射都不得覆盖它；
- 字段拷贝与拆分因子是派生阶段的配置，不能反过来定义单据流本体。

### 14.3 分批派生语义

同一源行允许**多次**派生，每次只消耗当时未结量的一部分：

```
源行 100：
  第 1 次 派生 60 → 累计 60，未结 40
  第 2 次 派生 20 → 累计 80，未结 20
  第 3 次 派生 20 → 累计 100，未结 0
  第 4 次 派生 1  → OVER_DERIVE（累计将达 101 > 100），拒绝
```

- 调用方不传数量时，默认派生量 = 当前未结量（批量引擎）；
- 数量必须 > 0，否则 `INVALID_QUANTITY`；
- 红字边可回退累计（active 正向 − active 红字），未结量随之回升；
- 累计与未结是**实时计算结果**，不是字段维护值。

### 14.4 派生模式与幂等键（重要约束）

| 模式 | 判定 | 幂等键 | 同一源行的多次派生 |
|---|---|---|---|
| 单表模式 | 规则 `target_line_bo` 为空 | 7 元组（含 `target_id` / `target_item`） | 允许；每次新建目标行即新键 |
| 头行模式 | 规则 `target_line_bo` 非空 | `(源行, 目标单头, rule_id)`，**不含行身份** | 同一单头同一规则仅允许一次，第二次判定为重放 |

由此得出两条硬约束：

1. **同一张下游单据的多行追加**：单表模式天然支持（每次派生新行，`target_data` 携带同一单据头外键即可）；头行模式不支持，必须换单头或换规则。
2. **头行模式是「一源行 = 一目标行」**，不是「一源行 = 同单多行」。该约束必须显式断言，禁止依赖调用方试错发现：
   - 同 `(源行, 单头, rule_id)` 且派生量相同 → 幂等重放（`replay=True`，零新增）；
   - 同 `(源行, 单头, rule_id)` 但派生量不同 → 拒绝并返回 `HEAD_LINE_MULTI_NOT_SUPPORTED`，不得静默吞掉本次数量；
   - 需要分批 → 改用单表模式（`target_line_bo` 为空），或换单头/规则。

幂等键与「同单多行」不可同时按单头收敛又要求多行——二者只能选一（见 TBD-32）。

**头部产品对标结论**（2026-11-08 取证）：

| 产品 | 同单多行 | 触发机制 | 幂等口径 |
|---|---|---|---|
| SAP S/4HANA SD | 支持 | 批次拆分（CHSP，交货单内同源行拆多批次子项）；跨单另按交货日期/工厂/装运点拆单 | 源行 + 批次子项 |
| D365 F&O | 支持 | 交货计划（commercial line → delivery lines，按数量/日期/运输方式/存储维度） | 源行 + delivery line 因子组合 |
| Oracle Fusion OM | 支持 | Split Line / Split Fulfillment Line（仓库、装运方式、日期、替代品、数量）；`Splits Allowed` 可关闭 | 拆分后的行（属性组合） |
| NetSuite | 不支持 | 一源行对应一条 IF 行；部分履行只能生成新 IF | 源行 + IF 头 |
| Odoo 17/18 | 仅明细层 | 一个 stock move 可有多条 move line（批次/序列号/库位/包装）；部分交付走 backorder 新单据 | 源行 → move；按 move line 明细 |

可复用结论：

1. **同单多行普遍存在，但无一例外由可枚举拆分因子驱动**（批次/序列号、日期、仓库/库位、装运方式、存储维度），不存在「无因子自由追加同一源行到同一单据」。
2. **拆分是一次性的、总量守恒的**：拆完即封闭，同因子重放返回同一行，而不是反复追加。
3. **分单与分行是两级**：现有 `split_key` 只做「分单」（多张目标单据，对标 SAP delivery split）；若要同单多行，需另设「行因子」（对标 SAP batch split / D365 delivery line），二者不得混用。

据此，头行模式的默认语义保持「一源行 = 一目标行」；若未来开放同单多行，只做**因子驱动的一次性拆行**，幂等键扩展为 `(源行, 目标单头, rule_id, 因子值集合)`，因子为空时退化为现键（向后兼容）。无因子追加仅保留给单表模式。

### 14.5 数量时段：不引入（已确认）

业务已确认：单据流**不承载时段语义**。数量关系只按「源行 + 池」累计，不做按日历/期间的数量切分。

- `doc_flow_rule` **无** `valid_from` / `valid_to` / 生效期列，发布即长期有效；
- `doc_flow_edges` **无**时间窗列，只有 `derived_at`（事实发生时间）；
- 唯一的「时段」概念在计划层 `demand_trace_links.valid_to`（reservation 有效线索），属跨层对账，不属边模型；
- `pool` 是**逻辑消耗池**（同池共享上限、异池独立），不是时间桶；不得把日期/期间折叠进 `pool` 值来模拟时段。

后续若出现真实的时段诉求，必须单独立项设计，不得在各业务流散落实现；本版不预留字段。

### 14.6 不变量

1. **INV-FLOW-1** 边 append-only，唯一写入口 = 派生引擎；冲销只追加补偿边，不改历史。
2. **INV-FLOW-2** 数量字段不参与字段拷贝，由引擎按派生量写入。
3. **INV-FLOW-3** 任意时刻、任意池内：Σ(active normal) − Σ(active red) ≤ 源行数量。
4. **INV-FLOW-4** 未结量由消费方计算，不新增物化通用视图。
5. **INV-FLOW-5** 幂等键必须包含目标行身份，或明确按单头收敛；不得二者兼取。

### 14.7 验收（可执行清单）

1. 同一源行 100 连续派生 60 / 20 / 20：累计为 60 / 80 / 100，未结为 40 / 20 / 0；第 4 次派生失败并返回 `OVER_DERIVE`。
2. 单表模式同单多行：`target_data` 传同一单据头外键，产生 N 条边且 `target_id` 互不相同。
3. 头行模式：同一源行对同一单头第二次派生（数量相同）返回 `replay=True`，边数不增；数量不同则返回 `HEAD_LINE_MULTI_NOT_SUPPORTED`，边/明细行/单头均零新增（显式断言该约束）。
4. 追加红字边后未结量回升，且视图查询与边表复算结果一致。
5. 结构断言：规则表无生效期列、边表无时间窗列（防后续误加，回归即失败）。
6. 若未来启用因子拆行：同源行 + 同单头 + 不同因子值 → 多行；同因子值重放 → 不新增；拆出行数量之和 = 源行数量。
7. 全部经 `python d:\filework\test.py` 执行。

### 14.8 待决策

| ID | 事项 | 选项 | 建议 |
|---|---|---|---|
| TBD-31 | ~~数量时段维度~~ | — | **已关闭**：业务确认不存在时段语义；本版不引入、不预留字段，`pool` 仅作逻辑消耗池 |
| TBD-32 | 头行模式同单多行 | 维持一源行一行 / 因子驱动一次性拆行 / 无因子自由追加 | **默认维持一源行一行**；若开放，只做因子驱动的一次性拆行，幂等键 = 源行 + 单头 + 规则 + 因子值集合（空则退化现键）；无因子追加仅单表模式，头行模式收到即报明确错误码 |
