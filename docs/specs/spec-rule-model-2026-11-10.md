# Spec: 规则模型（条件构建 · 判定 · 处置动作）

> **版本**: v1.2（`hold` 存储方案二次评估后修订）
> **日期**: 2026-11-10
> **状态**: 设计中（M1 词表/矩阵/加载期校验、M2 统一谓词求值器 + explain、M3 派生度量注册表、M4 typed 判定结果、M5 命中策略 + 治理字段、M6a 容差规则接线、M6b `holds` 表 + 释放路径 + 盘点 post 拦截 / 全规则释放 / 审计留痕已实现；见 §11.2.2）
> **v1.2 变更**: 撤回「单据 `hold_state` 汇总字段」，`holds` 为唯一事实源，单据侧不落冗余状态（§10.4、TBD-6、TBD-11）
> **v1.1 变更**: `hit_policy` 由 `priority_first` 修正为 `first`（§10 TBD-9）；`hold` / `warn_ack` 落点确定（§10 TBD-6/7）；治理字段分两档（§10 TBD-8）
> **作者**: AI Agent
> **触发**: 「其他 ERP 头部产品如何让规则模型在建模时清晰：条件怎么建、规则怎么控、后面是审批还是报错」

**上游 / 关联文档**

| 文档 | 关系 |
|---|---|
| [spec-validation-metadata-driven.md](./spec-validation-metadata-driven.md) §9.6 / §9.7 | 校验执行链与「审批触发条件与校验正交」的既有结论；本文不推翻，只在其上固化规则模型 |
| [spec-condition-rule-builder.md](./spec-condition-rule-builder.md) | 条件**构建 UI**（`ConditionRuleBuilder` / `ConditionNode`）。本文引用其模型，不重写 UI |
| [spec-notification-task-alert.md](./spec-notification-task-alert.md) | L3 动作中 `notify / warn_ack / hold` 的落地通道（`tasks`、Alert、message 中心） |

---

## 1. Background & Objectives

### 1.1 问题

建模时规则模型不清晰，表现为三个具体问题：

1. **条件怎么建**：同一个业务条件在审批侧、校验侧、状态机侧各写一遍，写法还不一样；有的支持 AND/OR，有的只支持单层 AND。
2. **规则怎么控**：规则有类型、有优先级、有生效期、有作用域，但哪些是必填治理字段、命中多条时取哪条，没有统一口径。
3. **后面做什么**：同样是「条件不成立」，有时要报错拦住、有时只提示、有时挂起等人工补齐、有时转审批。当前实现里这些处置动作散落在拦截器、`resolve()`、前端提示三处，没有一张表能回答「这个规则命中后到底发生什么」。

### 1.2 目标

- 建立**一种条件语义**（谓词 / 决策表），消除多处重复实现。
- 建立**判定结果与处置动作的分离**：判定说「什么不成立」，动作说「因此做什么」。
- 给出 `rule_type × action` 的**封闭矩阵**，作为配置期白名单，禁止运行期自由字符串。
- 明确规则的**治理字段**（版本、生效期、优先级、命中策略、作用域），让「同一条件下多条规则」有确定答案。
- 给出统一 **explain / 试算** 契约，使建模者能看到「哪条规则、哪个字段、期望多少、实际多少、通过与否」。

### 1.3 非目标

- 不重写 [ConditionRuleBuilder](../spec-condition-rule-builder.md) 的前端组件与 `condition_converter.py` 的文本解析。
- 不动审批流程本身的 `tasks(type=approval)` 状态机。
- 不改 `metadata_validator.py` 现有的字段级校验（required / unique / pattern / enum / max_length），只在其外层新增「规则模型」层。
- 不引入工作流引擎（BPMN / Flow）作为规则执行器。

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|---|---|---|
| Business | Yes | 规则模型是元数据驱动建模能力的核心构件 |
| User/Stakeholder | Yes | 建模者需要「一条规则 = 条件 + 判定 + 动作 + 治理」的单一视图 |
| Solution | Yes | 五层模型 L0–L4 + `rule_type × action` 矩阵 |
| Functional | Yes | FR-001 ~ FR-009 |
| Nonfunctional | Yes | 求值确定性、explain 可观测性、配置期校验 |
| External Interface | Partial | explain / simulate 的响应结构 |
| Transition | Yes | 存量规则需要映射到新的 action 词表，`rule_center_view.yaml` 需要补列 |

---

## 3. Functional Requirements

### FR-001: 条件只有一种语义

- **Description**: 所有规则类型的条件统一表达为谓词 AST（`and / or / not / group` + 原子比较），不再按规则类型分叉出另一套条件写法。
- **Acceptance Criteria**:
  - 审批策略条件、校验规则条件、状态守卫条件经同一求值器求值。
  - 原子比较至少覆盖 `= / != / > / >= / < / <= / in / not_in / between / is_null / is_not_null / like`。
  - 嵌套深度受控（沿用 `maxNestingLevel=3`）。
- **Priority**: Must

### FR-002: 单一求值器

- **Description**: 条件求值只有一处实现，输出结构化结果而非布尔值。
- **Acceptance Criteria**:
  - 输出 `explain[]`，每项含 `field / op / expected / actual / passed`。
  - 求值器不感知 `rule_type`，不感知处置动作。
- **Priority**: Must

### FR-003: 派生度量（L0）单点定义

- **Description**: 「金额」「价格偏差率」等派生度量在注册表中定义一次，校验规则与审批策略按名字引用，不各自重算。
- **Acceptance Criteria**:
  - 度量定义含 `code / formula / inputs / unit / precision`。
  - 同一度量在一张单据内只计算一次，多处引用结果一致。
  - 度量公式为事实源；落库缓存（如有）标记为 `derived_cache`，不得作为事实源被其他规则读取。
- **Priority**: Must

### FR-004: 判定结果为 typed 结构

- **Description**: 求值结果按用途分成不同类型，不共用一个大而全的结构。
- **Acceptance Criteria**:
  - `ValidationDecision{ ok, findings[{ code, severity, message, explain }] }`
  - `ApprovalRequirement{ required, policy_id, steps[], amount, snapshot, reason }`
  - `AssignmentDecision{ assignee, pool, reason }`
  - `DefaultDecision{ field, value, source_rule }`
  - `StateGuardDecision{ allowed, from, to, blocking_rules[] }`
  - 不同类型不得互相塞入（例如 approval 结果不得放进 `ValidationDecision.findings`）。
- **Priority**: Must

### FR-005: 处置动作封闭枚举

- **Description**: 动作词表固定为 7 个：`block / warn_ack / hold / route / notify / default / lock`，配置期校验 `rule_type` 与动作的合法组合。
- **Acceptance Criteria**:
  - 非法组合（如 `default` 规则配置 `block`）在加载 YAML / 保存规则时即报错，不是运行期静默忽略。
  - 动作不得以自由字符串写进规则表。
- **Priority**: Must

### FR-006: 命中策略显式化

- **Description**: 每条规则集必须声明 `hit_policy`（`first / all / unique`）与 `order_by`，不得依赖 SQL `ORDER BY` 的隐式语义。
- **Acceptance Criteria**:
  - 运行期默认 `hit_policy=first`，`order_by=[priority DESC, effective_from DESC, id DESC]`（与现状等价）。
  - `unique` 只用于建模期静态检查：命中多条即报「规则重叠」，不进入运行期。
- **Priority**: Must

### FR-007: 规则治理字段

- **Description**: 规则必须携带 `version / effective_from / priority / scope{factor}`，并可按 `rule_key` 追溯变更。
- **Acceptance Criteria**:
  - 规则中心视图能看到 `version / effective_from / priority`（当前 validation 页签缺失）。
  - 变更写 `audit_log`。
- **Priority**: Should

### FR-008: 统一 explain / 试算

- **Description**: 规则中心提供解释与试算：给定单据（或样例数据 + 配置口径），输出逐条规则的命中情况。
- **Acceptance Criteria**:
  - 复用 [rule_center_view.yaml](../../meta/schemas/rule_center_view.yaml) 已有的 `conditions_columns{field,op,expected,actual,passed}` 与 `messages.condition_passed / condition_failed`。
  - `simulate.config_modes: [baseline, draft, both]` 语义不变。
  - `trace.scenarios` 覆盖 `default / control_parameter / line_type / approval / state_transition / doc_flow`。
- **Priority**: Should

### FR-009: 权限与规则正交

- **Description**: 「用户有没有权限改这条单据」与「这条单据的条件是否成立」是两条独立判据，不得互相替代。
- **Acceptance Criteria**:
  - 越权时返回权限错误，不进入规则求值。
  - 有权时规则条件仍独立求值。
  - 该结论与 [spec-validation-metadata-driven.md](./spec-validation-metadata-driven.md) §9.7 一致。
- **Priority**: Must

---

## 4. Nonfunctional Requirements

### NFR-001: 求值确定性

- **Description**: 相同输入 + 相同规则版本，求值结果必须完全一致（含 explain 文本顺序）。
- **Measurement**: 同参数重复试算 10 次，输出逐字节一致。

### NFR-002: explain 可观测性

- **Description**: 任一拦截都必须能回答「哪条规则、哪个字段、期望值、实际值」。
- **Measurement**: 阻断类错误的响应体含 `rule_key` 与至少一条 `explain`。

### NFR-003: 配置期失败优于运行期失败

- **Description**: 非法 `rule_type × action`、非法 `hit_policy`、空条件、引用不存在的度量，必须在加载期或保存期报错。

---

## 5. External Interface Requirements

### IF-001: Explain 响应

```json
{
  "rule_key": "R-PO-12",
  "rule_type": "state_transition",
  "matched": false,
  "decision": { "allowed": false, "from": "draft", "to": "confirmed" },
  "explain": [
    { "field": "approval_status", "op": "in", "expected": ["not_required", "approved"], "actual": "pending", "passed": false }
  ],
  "action": "block"
}
```

### IF-002: 试算响应

- 输入：`object_type`、`record_id`（或样例 payload）、`scenarios[]`、`config_mode`。
- 输出：每个场景一份 `explain[]` + 最终 `actions[]`（按 `rule_type × action` 矩阵解析后的实际处置）。

---

## 6. Transition Requirements

### TR-001: 存量规则映射

- **Description**: 现有规则需要映射到新的 action 词表，映射关系写入迁移脚本，不允许人工逐条改 YAML。

| 现状表达 | 新表达 |
|---|---|
| 校验失败抛 `ValidationFailedError` 并阻断 | `validation × block` |
| 校验失败返回 `errors` 但允许保存 | `validation × warn_ack` |
| SAP Incompletion Log 式「可存不可过」 | `validation × hold` |
| 金额超阈值 → 走审批 | `state_transition × route`（由 approval policy 承载） |
| 字段自动带出 | `default × default` |
| 字段置灰不可改 | `permission × lock` |

### TR-002: 视图补列

- `rule_center_view.yaml` 的 `validation` 页签补 `version / effective_from / priority`（与 `approval` 页签对齐治理字段）。

---

## 7. Constraints & Assumptions

- SQLite 为当前数据源；跨对象规则需要显式 join 描述，不做隐式 N+1。
- 条件文本解析沿用 `condition_converter.py`，其能力边界是「单层 AND + 不支持 OR / 嵌套括号」，嵌套条件必须由结构化 AST 承载。
- `_condition_matches` 现有运算符集合（`= / in / between / >= / <= / is_null`）是求值器的起点，扩展需保证向后兼容。
- 审批侧现状为「`priority DESC, effective_from DESC, id DESC` + 取首条」，等价 DMN 的 `First`（按规则顺序首命中），但语义是**隐式**的；本次要求显式声明 `hit_policy=first` + `order_by`。
- 不引入外部规则引擎依赖。

---

## 8. Priorities & Milestone Suggestions

| 阶段 | 内容 | 依赖 |
|---|---|---|
| M1 | 词表与矩阵落地：`rule_type × action` 白名单 + 加载期校验 | 无 |
| M2 | 求值器统一：把 `_condition_matches` 抽成公共谓词求值器 + `explain[]` | M1 |
| M3 | 派生度量注册表，校验 / 审批共同引用 | M2 |
| M4 | typed 判定结果改造（`ValidationDecision` / `ApprovalRequirement`） | M2 |
| M5 | `hit_policy` 显式化 + 治理字段补列 + 试算对齐 | M1、M4 |

---

## 9. Change / Design Proposal (RFC)

### 9.1 行业研究（二次复核版）

#### 9.1.1 复核方法

对上一轮结论逐条回源核对，改以「**条件怎么建 / 判定怎么出 / 动作是什么 / 治理怎么控**」四问重排证据，并补充 Palantir Foundry / Gotham 作为第八个样本。

#### 9.1.2 八产品对照

| 产品 | 条件构建 | 判定结果 | 处置动作 | 治理 |
|---|---|---|---|---|
| SAP S/4HANA | BRFplus 决策表 + Release Strategy 特征组合 + Validation/Substitution 自定义出口 | 特征组合命中 → 释放策略；Incompletion Log 记录缺项 | 释放（route）/ 阻止保存（block）/ 不完整但可存（hold）/ Output Control（notify） | 策略版本、有效起止日期 |
| Oracle Fusion | AME 规则（条件列表）+ 发票容差 | 容差判定、Hold 判定、AME 审批链 | Holds（可存不可付款）/ 审批链（route）/ 容差警告（warn_ack） | 规则优先级、启停、作用业务实体 |
| Salesforce | Validation Rule 公式；Approval 入口条件；Duplicate Rule | 布尔成立 / 不成立 | 错误（block）/ 重复告警 Allow-Block-Alert（三态）/ 提交审批（route） | 每条规则独立启停；无统一优先级 |
| ServiceNow | Condition Builder（可视化）；Decision Builder | 条件命中 → 决策 | before 业务规则阻断（block）/ after 业务规则副作用 / Flow 触发（route、notify） | 执行顺序（order）、before/after |
| Dynamics 365 / Dataverse | Business Rule 条件编辑器 | 条件成立 → 执行动作 | Show Error Message（block）/ Set Field Value（default）/ Lock Field（lock），同一规则可混装 | 范围（实体/字段）、启停 |
| Odoo | domain 过滤器；`@api.constrains` | Python 断言 / domain 匹配 | 抛异常（block）/ 自动化动作（notify、route） | 模块版本、依赖顺序 |
| DMN / Pega / Appian | 决策表（输入 → 输出，hit policy 显式） | 决策表求值结果 | 与流程节点解耦，由流程决定 route / notify | hit policy（U/A/F/C/P/R）、决策版本 |
| **Palantir Foundry** | Action Type 的 **submission criteria**（条件 + 运算符可组合嵌套） | 全部条件满足 → 允许提交 | 拒绝提交（block）/ Automate 触发 function（notify、route、回写） | Action Type 版本与权限分离 |
| **Palantir Gotham / Monitoring** | Monitoring view rules 条件 | 命中 → 产生告警 | Alert（notify）/ 可配置 Alert severity | 规则集、severity 部分固定 |

**共性结论**：条件只有一种（谓词或决策表）；处置动作按用途分家；没有任何一家把「金额超阈值」建模成 error message，它一律是「路由到审批 / 产生告警 / 挂起」。

#### 9.1.3 Palantir 专项（本轮新增证据）

| 能力 | 官方口径 | 对我们的映射 |
|---|---|---|
| **Submission criteria** | 提交标准由条件和运算符组成；条件是控制参数或用户属性值的单个语句；运算符用于组合与嵌套；**只有当所有提交标准都满足时，操作才能提交**；并且「这与管理用户是否可以编辑操作类型本身的权限无关」 | 直接印证 §9.7 的「规则与权限正交」：条件全满足才允许提交，权限另算。对应我们 `StateGuardDecision` + `permission` 两条独立判据 |
| **Derived properties** | 在**查询时**从其他属性或关联对象计算，不存储；底层数据变化后仍然正确 | 印证 L0 派生度量「公式为事实源、不做持久化事实」；我们允许落库缓存，但必须标记 `derived_cache` 且不可被其他规则当作输入 |
| **Functions** | TypeScript / Python 函数，可被 derived properties、Automate、Action 复用 | 印证「一个度量 / 一个判定只实现一次，多处引用」 |
| **Automate** | 条件命中后自动执行 function；异步执行，最长可运行 4 小时；Object Monitors 已被 Automate 取代且向后兼容 | 印证 L3「条件命中 → 动作」应独立于同步校验链；同时提示我们：`notify / route` 这类副作用动作应走异步任务，不要挂在同步拦截器里阻塞保存 |
| **Monitoring rules** | 多数规则含可配置的 `Alert severity`；**部分规则 severity 固定** | 印证「severity 是告警展示级别，不是处置动作」；固定 severity 的规则说明 severity 可以由规则类型本身决定，不需要使用者配置 |

文档来源：
- <https://www.palantir.com/docs/zh/foundry/action-types/submission-criteria>
- <https://www.palantir.com/docs/foundry/ontology/derived-properties>
- <https://www.palantir.com/docs/foundry/functions/use-functions>
- <https://www.palantir.com/docs/foundry/monitoring-views/rules-reference>
- <https://www.palantir.com/docs/zh/foundry/object-monitors/condition>

#### 9.1.4 容差专项：SAP / Oracle Fusion 的可借鉴结构

两家都没有「通用容差规则引擎」，但都把一个容差拆成三个可复用部分：**键（key）字典 / 维度解析 / 限值 + 动作**。这是 M6 唯一值得照搬的结构。

| 维度 | SAP S/4HANA | Oracle Fusion | 对我们的映射 |
|---|---|---|---|
| 容差载体 | 三套互不相同的键表：MM 收货容差 OMC0（公司代码 × 容差键，上下限 × 百分比/绝对值，动作 = 警告/错误）；发票校验 OMR6（15 个键：AN/AP/BD/BR/BW/DQ/DW/KW/LA/LD/PC/PP/PS/ST/VP）；FI 容差组 OBA3/OBA4（科目/员工，与 MM 无关） | 收货参数（按库存组织：超收 %、早收/晚收天数，动作 None/Warning/Reject）；发票容差集（数量型/金额型，百分比 + 绝对额，分配给供应商地点） | 限值只落 `control_parameter_defs`（`domain='tolerance'`），不另建代码侧键字典 |
| 维度解析 | 键定义在公司代码级，PO 行可覆盖（`UEBTO`/`UNTTO`/`UEBTK`，默认值来自物料主数据采购值代码） | 库存组织 → 收货参数；供应商地点 → 容差集（未分配则取发票选项默认） | 参数行按 `org_id / document_type_id / item_group_id` + `specificity_rank` 首命中；单据头字段为实例层覆盖 |
| 限值形态 | 上下限分离（超收 / 短收各一键）；百分比与绝对值可同时生效 | 数量容差与金额容差各自成集；价格容差仅百分比 | 限值身份 =「方向 × 基准」（over/under × pct/abs），不可压成单一标量 |
| 超限结果 | 警告 / 错误；BD 类超限**不能过账**；发票超限 → 付款冻结 | 系统 Hold（Price / Qty Ordered / Qty Received / Quality），**可存不可付款**；改单修正或人工释放（需 Match Release Code）后重新审批；Hold Resolution Routing 走 BPM 通知 | 判定与处置分离：`block`（不能过账）/ `hold`（可存不可过）/ `warn_ack`；hold 必须配释放路径 |
| 组合语义 | 多键各自判定，任一 error 即阻断（error 优先于 warning） | 多个 Hold 可同时挂起 | key 之间 `all` + 动作按 severity 升级（error > warning > info），不是 `first` |
| 治理 | 容差配置随传输请求版本化 | 容差集有有效日期、按供应商地点分配、可按业务实体启停 | 阈值走参数（启停态 + `specificity_rank`）；判定规则走 BO YAML（版本 / 生效期 / 优先级） |

来源（检索关键词，非官方链接直引）：SAP Help「Define Tolerances for Goods Receipts (OMC0)」「Tolerance Keys for Invoice Verification (OMR6)」「Define Tolerance Groups for Employees/GL Accounts (OBA3/OBA4)」；Oracle「Manage Receiving Parameters」「Manage Invoice Tolerances」「Invoice Holds and Hold Resolution」。

**四点结论**：

1. **不新增「容差场景」**。两家都没有；新增场景会引入第四套命中词表，且 `ScenarioSpec.source` 单值无法表达多载体。容差 =「参数承载限值」+「`constraint` 规则承载判定」的组合。
2. **限值必须按键拆分**。`allow_over_delivery` / `allow_under_delivery` 是方向独立的开关，合并成一个 `tolerance_pct` 会丢信息。
3. **key 内首命中、key 之间全量**。key 内复用参数 `specificity_rank` 首命中；key 之间 `all` + 动作升级。M5 的 `first` 只适用于前者。
4. **`hold` 是一等结果**。SAP 付款冻结与 Oracle 系统 Hold 都证明「可存不可过」不是 `block` 的变体，必须配套释放动作（改单 / 人工释放）。

### 9.2 二次复核的修正点

| # | 上一轮口径 | 复核后修正 | 影响 |
|---|---|---|---|
| C-1 | 把 `severity`（error/warning/info）与处置动作放在一起讨论 | `severity` 是**展示级别**，处置动作是**操作语义**；二者通过映射表关联，不是同一个字段。`hold` 绝不能塞进 severity | 新增 §9.4.3 边界表；[rule_center_view.yaml](../../meta/schemas/rule_center_view.yaml) 的 `severity: [error, warning, info]` 保持不变 |
| C-2 | 认为审批侧已有「优先级排序」即已具备命中策略 | 现状是 SQL `ORDER BY priority DESC, effective_from DESC, id DESC` 的**隐式** first-hit，配置里没有 `hit_policy` 声明 | R-6 从「建议」升级为「必须」；补 `hit_policy` 字段 |
| C-3 | 笼统说「治理字段不对齐」 | 具体缺口：`validation` 页签缺 `version / effective_from / priority`，`approval` 页签有 `status` 无 `version` | R-8 给出字段级清单 |
| C-4 | 派生度量倾向「算完存下来」 | Palantir derived properties 明确「查询时算、不存储」。结论改为：公式是事实源，落库只允许作为 `derived_cache` | FR-003 增补「不得作为事实源被其他规则读取」 |
| C-5 | 未区分「同步校验」与「异步副作用」 | Palantir Automate 异步执行（最长 4 小时）说明 `notify / route` 不应阻塞保存 | 新增 §9.5.2「同步 / 异步分界」 |

### 9.3 设计结论：条件一种，动作分家

一句话：**校验管「能不能过门」，审批管「要不要人点头」，告警管「要不要让人知道」，默认值管「没人填时填什么」。四件事共用一个条件求值器，不共用一个结果结构。**

### 9.4 五层模型

#### 9.4.1 L0 事实层（字段 + 派生度量）

- 输入：单据字段、关联对象字段、上下文（用户、组织、单据类型、行类型、物料组）。
- 派生度量注册表：`code / formula / inputs / unit / precision`。
- 原则：**一处计算，多处引用**；派生结果可缓存，但公式为唯一事实源。

示例（沿用 [spec-validation-metadata-driven.md](./spec-validation-metadata-driven.md) §9.7.2 的结论）：

```text
computed: price_deviation_rate  ← 注册表定义一次
  ├─ validation rule 引用 → 判 warning / error
  └─ approval policy 条件引用 → 判 required
```

#### 9.4.2 L1 条件层（谓词 AST + explain）

```text
ConditionNode = RuleNode | GroupNode

RuleNode  { field, op, value, value_type }
GroupNode { connector: and|or|not, children[] }
```

- 求值输出 `explain[] = [{field, op, expected, actual, passed}]`，不输出裸布尔。
- 与 [spec-condition-rule-builder.md](./spec-condition-rule-builder.md) 的 `ConditionNode` 同构；UI 直接复用 `ConditionRuleBuilder`，序列化仍走 `condition_converter.py` 兼容格式。
- 能力边界必须写清：文本模式只支持单层 AND；嵌套必须用结构化 AST（当前 `condition_converter.py` 明确不支持 OR 与嵌套括号）。

#### 9.4.3 L2 判定层（typed 结果）

| 判定类型 | 回答的问题 | 产出 |
|---|---|---|
| `ValidationDecision` | 数据是否合规 | `{ok, findings[{code, severity, message, explain}]}` |
| `ApprovalRequirement` | 要不要人点头 | `{required, policy_id, steps[], amount, snapshot, reason}` |
| `AssignmentDecision` | 派给谁 | `{assignee, pool, reason}` |
| `DefaultDecision` | 没人填时填什么 | `{field, value, source_rule}` |
| `StateGuardDecision` | 状态能不能变 | `{allowed, from, to, blocking_rules[]}` |

**severity 与动作的边界（C-1 修正）**

| 概念 | 取值 | 归属 | 可否互转 |
|---|---|---|---|
| severity | `error / warning / info` | 展示与告警级别 | 不可当作动作 |
| action | `block / warn_ack / hold / route / notify / default / lock` | 操作语义 | 不可当作 severity |
| 关联方式 | 映射表 `rule_type × severity → action` | L3 | 只允许通过映射表，不硬编码在拦截器 |

#### 9.4.4 L3 动作层

见 §9.5 矩阵。

#### 9.4.5 L4 治理层

| 字段 | 含义 | 必填 |
|---|---|---|
| `rule_key` | 稳定标识，可被引用与追溯 | 是 |
| `rule_type` | 封闭枚举（见 §9.5.1） | 是 |
| `version` | 规则版本 | 是 |
| `effective_from / effective_to` | 生效区间 | 是 |
| `priority` | 同条件多规则时的排序依据 | 是 |
| `hit_policy` | `first / all / unique`；`first` 时另需 `order_by` | 是（`computation / derivation` 除外） |
| `scope` | 作用域因子（org / document_type / line_type / item_group / bo） | 是 |
| `enabled` | 启停 | 是 |
| `owner` | 责任人 | 建议 |

### 9.5 `rule_type × action` 矩阵

#### 9.5.1 动作词表

| action | 语义 | 落库形态 |
|---|---|---|
| `block` | 拒绝操作，保存/提交失败 | 错误响应，无持久化 |
| `warn_ack` | 允许继续，但必须确认；确认留痕 | `audit_log` 追加记录（TBD-7）；需人工复核时另起 `tasks(type=validation_review)` |
| `hold` | 允许保存，但不允许后续流转（可存不可过） | `holds` 明细表，**唯一事实源**；单据不定制 `hold_state` 列，「是否被挂起」由 `EXISTS(holds WHERE released_at IS NULL)` 派生（§10.4） |
| `route` | 转交人工或流程 | `tasks(type=approval)` / 流程实例 |
| `notify` | 只通知，不改变操作结果 | message 中心 / Alert |
| `default` | 自动填值 | 字段值写入 |
| `lock` | 字段只读 / 不可编辑 | 权限或字段策略生效 |

**关键**：`hold` 是独立处置态，不是 severity 的一种。它对应 SAP Incompletion Log、Oracle Holds 的「可保存、不可推进」。

#### 9.5.2 同步 / 异步分界（C-5 新增）

| action | 执行时机 | 理由 |
|---|---|---|
| `block / warn_ack / default / lock` | **同步**，在保存事务内 | 影响本次写入结果，必须立即决定 |
| `hold` | **同步**写 `holds` 行，**异步**做后续检查 | 保存当时就要知道是否被挂起；补齐后的复检可异步 |
| `route / notify` | **异步**（任务队列） | Palantir Automate 同为异步；不应阻塞保存响应 |

#### 9.5.3 矩阵

图例：`主` = 该类型的主要动作；`可` = 允许配置；`—` = 禁止（配置期报错）。

| rule_type | block | warn_ack | hold | route | notify | default | lock |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `validation` | 主 | 主 | 可 | — | 可 | — | — |
| `constraint` | 主 | — | 可 | — | 可 | — | — |
| `state_transition` | 主（守卫） | — | 可 | 可 | 可 | — | — |
| `permission` | 主 | — | — | — | — | — | 主 |
| `default` | — | — | — | — | 可 | 主 | — |
| `computation` | — | — | — | — | — | 主（覆盖） | — |
| `derivation` | — | — | — | — | — | — | — |
| `trigger` | — | — | — | 可 | 可 | 可 | — |
| 审批策略（独立来源 `approval`） | — | — | 主（hold） | 主（route） | 可 | — | — |

`rule_type` 取值与 [models_enums.py](../../meta/core/models_enums.py#L94-L104) 的 `RuleType` 一致：`validation / constraint / computation / state_transition / permission / trigger / derivation / default`。

**注意**：`derivation`（推导）在矩阵中全为 `—`，因为它是**计算**而非**处置**：推导产出被其他层引用，不直接作用于操作。

#### 9.5.4 配置期校验

1. 校验 `rule_type ∈ RuleType`。
2. 校验 `disposition ∈` 该 `rule_type` 允许集合（YAML 键为 `disposition`；与既有 `action`（表达式）字段正交，不得混用）。
3. 校验 `hit_policy ∈ {first, all, unique}`；`hit_policy=first` 时 `order_by` 非空。
4. 校验条件非空（`GroupNode.children.length >= 1`）。
5. 校验引用的派生度量在注册表中存在。
6. 任一失败 → 加载期 / 保存期报错，附 `rule_key` 与失败原因。

**实现状态（M1 已落地 2026-11-10）**：词表与矩阵唯一真源为 `meta/core/rule_action_matrix.py`；加载期校验入口 `meta/core/rule_declaration_validator.py::validate_rule_actions`（错误码 `RULE_ACTION_INVALID`，报文含 `rule_key`）；YAML 注入在 `yaml_loader.parse_rule`（`MetaRule.disposition`）；用例 `meta/tests/test_rule_action_matrix.py`。第 3–6 项（`hit_policy` / 条件非空 / 度量引用）随 M2–M5 落地。

### 9.6 条件模型与 explain 契约

| 项 | 约定 |
|---|---|
| 输入 | 单据快照 + 上下文 + 派生度量结果 |
| 输出 | `explain[]`，顺序固定（按 AST 深度优先） |
| 运算符 | `= / != / > / >= / < / <= / in / not_in / between / is_null / is_not_null / like` |
| 嵌套 | 允许 `and / or / not`，深度 ≤ 3 |
| 文本兼容 | 单层 AND 走 `condition_converter.py`；含 OR / 嵌套必须走结构化 AST |
| UI | 复用 `ConditionRuleBuilder`，不新增第二套条件编辑器 |

**explain 文案**：复用 [rule_center_view.yaml](../../meta/schemas/rule_center_view.yaml) 的 `messages.condition_passed: 通过` / `messages.condition_failed: 未通过`，不新增中文常量。

### 9.7 与现有实现的映射及缺口

#### 9.7.1 已具备

| 能力 | 位置 | 说明 |
|---|---|---|
| 审批判定 | [document_approval_service.py](../../meta/services/document_approval_service.py) | `resolve()` 返回 `{required, policy_id, policy_code, steps, amount, snapshot, reason}`；`_matched_policies` 按 `priority DESC, effective_from DESC, id DESC` 排序 |
| 条件求值（局部） | 同上 `_condition_matches` | 支持 `= / in / between / >= / <= / is_null`；`_conditions_hold` 为单层 AND |
| 审批执行 | [document_approval_decision.py](../../meta/services/document_approval_decision.py) | approve → `submitted → confirmed`；reject → `submitted → draft` |
| 状态守卫 | [purchase_order.yaml](../../meta/schemas/purchase_order.yaml) `R-PO-12` | 仅 `approval_status ∈ {not_required, approved}` 允许确认，等价 SAP Release Strategy |
| 规则中心视图 | [rule_center_view.yaml](../../meta/schemas/rule_center_view.yaml) | 已有 `conditions_columns{field,op,expected,actual,passed}`、`simulate(config_modes)`、`trace(scenarios)` |
| 规则类型枚举 | [models_enums.py](../../meta/core/models_enums.py#L94-L104) | `RuleType` 8 值，已封闭 |
| 条件构建 UI | [spec-condition-rule-builder.md](./spec-condition-rule-builder.md) | `ConditionNode` 树 + `maxNestingLevel` |

#### 9.7.2 缺口 R-1 ~ R-8

| ID | 缺口 | 证据 | 建议 |
|---|---|---|---|
| R-1 | 无 `rule_type × action` 白名单 | 处置动作散落在拦截器、前端提示、`resolve()` | 建矩阵 + 加载期校验（§9.5） |
| R-2 | 无统一谓词求值器 | [metadata_validator.py](../../meta/core/metadata_validator.py) 内无运算符求值；审批侧 `_condition_matches` 私有 | 抽出公共求值器，两侧共用 |
| R-3 | 无派生度量注册表 | 审批侧自行计算 `amount` 并放进 `snapshot` | 建 L0 注册表，两侧按 `code` 引用 |
| R-4 | 判定结果未分型 | `resolve()` 返回裸 dict；校验侧返回 `ValidationDetail[]` | 改为 typed 结构（FR-004） |
| R-5 | `operation × rule × severity → action` 声明位置未定 | [spec-validation-metadata-driven.md](./spec-validation-metadata-driven.md) TBD-5 | 三级解析（§10 TBD-5）：默认矩阵（代码内封闭）→ operation `enforcement_override` → 规则显式 `action` |
| R-6 | `hit_policy` 隐式 | `_matched_policies` 靠 SQL `ORDER BY` 实现 first-hit | 显式 `hit_policy=first` + `order_by`（与现状等价）；`unique` 仅作建模期重叠检查 |
| R-7 | explain / 试算未统一 | 视图已有列定义，但无统一后端契约 | 统一 `explain[]` 契约（§9.6） |
| R-8 | 治理字段不对齐 | `validation` 页签缺 `version / effective_from / priority`；`approval` 页签有 `status` 无 `version` | 两页签统一补列 |

### 9.8 反模式（必须避免）

| # | 反模式 | 现实案例 | 后果 |
|---|---|---|---|
| A-1 | 万能 rule 表 + 自由 action 字符串 | Dataverse Business Rule 把「报错 / 赋值 / 锁定」混在同一规则里 | 规则无法被静态校验，改一条影响不可预期 |
| A-2 | 条件语言太弱，配置逃逸到代码 | Salesforce Validation Rule 表达力不足 → 大量迁到 Apex / Flow | 规则资产从「元数据」退化为「代码」，不可治理 |
| A-3 | 把 `hold` 塞进 severity | 三态 `error / warning / info` 表达不了「可存不可过」 | 业务被迫用 warning 近似，丢失「挂起」语义 |
| A-4 | 隐式命中策略 | 只靠排序 SQL 决定取哪条 | 建模者看不到「为什么这条生效」 |
| A-5 | 同步执行所有副作用 | 校验链里发通知、起流程 | 保存变慢、事务超时、失败回滚导致通知丢失 |

### 9.9 里程碑与验收

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 | 词表与矩阵 | 配置非法 `rule_type × action` 时加载报错（含 `rule_key`） |
| M2 | 统一求值器 + explain | 同条件在审批侧与校验侧 explain 输出一致 **（已实现 2026-11-10：`meta/core/rule_predicate.py`，审批侧 `snapshot.conditions_explain`）** |
| M3 | 派生度量注册表 | 同一度量在一张单据只计算一次；引用方结果一致 **（已实现 2026-11-10：`meta/core/rule_metrics.py`，审批条件可直接引用度量 code，快照 `metrics` 带 `derived_cache=True`）** |
| M4 | typed 判定结果 | approval 结果不出现在 `ValidationDecision.findings` **（已实现 2026-11-10：`meta/core/rule_decisions.py`，`resolve_requirement()` 返回 `ApprovalRequirement`）** |
| M5 | `hit_policy` + 治理字段 + 试算 | 规则中心可见 `version / effective_from / priority`；试算给出逐条 explain **（已实现 2026-11-10：`meta/core/rule_hit_policy.py` 封闭词表 + `ORDER_BY` 唯一真源；`validate_hit_policies()` 报 `RULE_HIT_POLICY_INVALID / RULE_OVERLAP`；validation 页签补三列）** |

**验收标准 R-A1 ~ R-A6**

- **R-A1** 任意 `rule_type × action` 组合，非法组合在配置期被拒绝。
- **R-A2** 同一条件在审批策略与校验规则中引用，求值结果一致（同一求值器）。
- **R-A3** 同一派生度量在一张单据内只计算一次，多引用结果一致。
- **R-A4** `warn_ack` 有确认留痕；`hold` 后单据可保存但不可推进；`route` 产生 `tasks(type=approval)`。
- **R-A5** `severity` 不出现在动作字段；`hold` 不出现在 `severity` 取值域。
- **R-A6** 规则中心可回答「这条单据为什么被拦 / 为什么免审批」，输出含 `rule_key` 与 `explain[]`。

---

## 10. TBD 决议（2026-11-10 二次研究）

### 10.1 判决原则

一个 TBD 落「独立表」还是「轻量落点」，用两条判据，不看个人偏好：

| 判据 | 判「独立明细表」 | 判「轻量落点」 |
|---|---|---|
| 有没有生命周期 | 有（apply → release，需要回答「当前是否仍未闭环」） | 没有（一次性事件，发生即终态） |
| 基数 | 一张单据可同时挂多条 | 一张单据一条或零条 |

补充原则：**处置态不与业务状态混用**。Salesforce 的审批锁是审批流程自动施加的独立维度（`ENTITY_IS_LOCKED`，锁/解锁按 DML 处理），并不把 `status` 改成某个「锁定态」；Oracle 的 Holds 也是与发票状态并存的一套独立记录。这条同样适用于我们的 `hold`。

**并且：独立明细表不等于再往单据上补一个汇总标记**。「当前是否被挂起」是明细表的派生结论，不是新的状态位（v1.2 改判，见 §10.4）。

### 10.2 决议表

| ID | 议题 | 结论 | 依据 | 落地影响 |
|---|---|---|---|---|
| TBD-6 | `hold` 落库形态 | **`holds` 明细表为唯一事实源；单据不落 `hold_state` 冗余列**（v1.2 改判，推翻 v1.1） | Oracle `AP_HOLDS_ALL` 是独立表（`HOLD_ID` 主键、`HOLD_LOOKUP_CODE`、`HOLD_DATE`、`HELD_BY`、释放日期），一张发票 1:N；Oracle REST 以 `invoiceHolds` 子资源暴露「挂起 / 释放」两类事件，并不在发票资源上回写汇总列。SAP `VBAK-UVALL` 是过程内生成的不完整状态，权威仍是 Incompletion Log 明细。两者都不构成「双写汇总列」的正当理由 | `holds` 字段：`id / object_type / record_id / rule_key / code / reason / applied_by / applied_at / released_by / released_at`；「是否被挂起」由 `EXISTS` + 部分索引派生，三方案评估见 §10.4 |
| TBD-7 | `warn_ack` 留痕位置 | **`audit_log` 追加记录，不建独立表** | SAP `W` 类型消息确认后不单独留痕，系统只通过 change log 记录最终保存结果；确认是单次事件，没有「当前是否已确认」的持续查询需求 | `audit_log` 至少记 `rule_key / user / ts / payload_hash / decision`；需要人工复核时另起 `tasks(type=validation_review)`，不复用 hold |
| TBD-8 | 治理字段强制范围 | **分两档**：识别档（`rule_key / rule_type / scope / enabled`）全类型必填；时效档（`version / effective_from / priority / hit_policy / order_by`）除 `computation / derivation` 外必填 | DMN 把版本放在**决策（规则集）**级别，不是每条规则各自一个版本；`computation / derivation` 不参与「命中取哪条」，`hit_policy` 对其无意义 | `version` 默认继承规则集版本，单条规则要独立版本须显式声明；`effective_to` 可空表示长期有效 |
| TBD-9 | `hit_policy` 默认值 | **`first`**（按 `order_by` 取首条），**废弃 `priority_first`** | DMN 的 `P`（Priority）指**输出值优先级**（由输出列 allowed-values 顺序决定），不是「规则优先级排序」，用 `priority_first` 命名会误导；DMN 的 `First` 才是「按规则顺序取第一条」。`unique` 虽是 DMN 默认，但那是设计期模型（会做规则重叠校验）；运行期取 `first` 才与现状等价 | FR-006 / §7 / §9.5.4 / R-6 已同步改为 `first`；`unique` 降级为建模期 lint |
| TBD-5 | enforcement 声明位置 | **三级解析**：规则显式 `action` > operation 级 `enforcement_override` > `rule_type × severity` 默认矩阵（代码内封闭常量） | DMN 把 hit policy 声明在**决策表本身**而非流程节点，说明「判定语义」应内聚；但 operation 确实存在合理收窄（确认时 warning 升级为 block），故只给 override 不给新增 | 默认矩阵禁止在 YAML 复制；`enforcement_override` 加载期校验必须落在该 `rule_type` 允许集合内，且只能收窄 |

### 10.3 残留未决（需产品 / 架构拍板）

| ID | 内容 | 建议 |
|---|---|---|
| TBD-10 | `holds` 是否区分「可手工释放 / 仅系统释放」 | Oracle 明确区分（部分 hold code 不允许手工释放）。首版只做 `code + reason + applied_by + applied_at + released_by + released_at`，不做释放权限分级 |
| TBD-12 | `warn_ack` 是否要求「确认人 + 确认理由」 | 建议首版只要求确认人；理由字段留给 `hold` 的 release reason。**现状（2026-11-10）**：`holds` 无独立 `release_reason` 列，释放理由暂写审计 `new_data.reason`，已列入 §11.2.2 延后项 |

> TBD-11（`hold_state` 物理列 vs 视图派生）已于 v1.2 决议：**不做物理列**，见 §10.4。

### 10.4 `hold` 状态存储：三方案二次评估（SSOT / 性能 / 健壮性）

**结论先行**：首版走 **A 纯派生**。`holds` 是唯一事实源，单据侧不落任何 `hold_state` 列。B（物理列 + 同步重算）降级为「实测出现瓶颈后」才考虑的可选读模型；C（生成列 / 触发器）直接出局。

#### 10.4.1 三方案对比

| 方案 | 做法 | SSOT | 性能 | 健壮性 | 判决 |
|---|---|---|---|---|---|
| **A 纯派生** | `holds` 唯一事实源；单据「是否挂起」= `EXISTS(SELECT 1 FROM holds WHERE object_type=? AND record_id=? AND released_at IS NULL)`；配部分索引 | ✅ 单一事实源，无同步点 | 点查 O(log n)；列表页一次 `LEFT JOIN` 或批量 `IN` 查询即可 | ✅ **fail-safe**：读不到 hold 才放行，漏写 `holds` 与漏更新汇总列的风险面相反 | **首版采用** |
| **B 物理列 + 同事务重算** | 单据加 `hold_state`，在写 `holds` 的同一事务内重算 `MIN/COUNT` 回写 | ❌ 双写，存在漂移路径（框架拦截器、`batch_save`、批量导入、并发保存） | 单表可索引，略快于 JOIN | ❌ **fail-open**：列漏更新 → 系统以为未挂起 → 放行被挂起的单据；需另建对账任务纠偏 | 仅当实测证明 A 成为瓶颈时，作为**只读读模型**引入（异步、可重建、不进写路径） |
| **C 生成列 / 触发器** | `hold_state` 用 `GENERATED ALWAYS AS` 或 trigger 维护 | 生成列能保 SSOT，但**不可行** | 触发器增加写放大与锁持有时间 | 触发器逻辑对拦截器 / `batch_save` / `audit_log` 不可见，二次保存可覆盖；SQLite 生成列**不能跨表聚合**（仅可引用同一行列，禁子查询 / 聚合 / 窗口函数） | **出局** |

#### 10.4.2 SSOT 为什么关键

`hold` 是有生命周期的（`applied_at → released_at`），唯一事实是「这条 hold 行现在是否仍未释放」。一旦在单据上再存一份 `hold_state`，就出现两个可写状态位，且**没有任何数据库约束能保证两者一致**——SQLite 无物化视图，`CHECK` 也只能看本行。所有双写方案最终都要靠「对账脚本」兜底，而本项目的对账类脚本恰恰最容易「报已修复但事务回滚」（见 SESSION_REMINDER 踩坑）。

#### 10.4.3 性能量级（可验算）

- 规模假设：单据 10 万张，挂起率 10%，平均 1–2 条 active hold → **约 1–2 万 active 行**。
- 部分索引 `CREATE INDEX idx_holds_active ON holds(object_type, record_id) WHERE released_at IS NULL;` 只索引 active 行；点查命中 B-tree 深度约 3–4 层，**微秒级**。
- 列表页 50 行：一次 `LEFT JOIN holds ... AND released_at IS NULL` + `GROUP BY`，或批量 `IN (50 个 id)` 一次索引查找，**毫秒级**。
- 真正的反例不是「派生」，而是「**无索引 + 每行一次全表扫**」：`EXPLAIN QUERY PLAN` 出现 `SCAN TABLE holds` 即该种写法；目标状态是 `SEARCH TABLE holds USING INDEX idx_holds_active`。

#### 10.4.4 数据库稳定性与健壮性

| 关注点 | 结论 |
|---|---|
| 部分索引命中条件 | 查询**必须重复索引的 `WHERE` 谓词**（`released_at IS NULL`），否则规划器不用该索引 → 封装成统一查询构造器，禁止各处手写 |
| 幂等（防重复挂起） | `CREATE UNIQUE INDEX uq_holds_active ON holds(object_type, record_id, rule_key) WHERE released_at IS NULL;` |
| 释放语义 | 释放 = `UPDATE holds SET released_by, released_at WHERE ...`，不删行；历史可追溯 |
| 单据删除 | 级联清理 `holds`（应用层删除钩子或 `ON DELETE CASCADE`），避免孤儿行把「active 行数」推高 |
| 写放大 / 锁 | 仅写 `holds` 一张表；A 方案在 SQLite WAL 单写者模型下锁持有时间最短 |
| 与 `batch_save` / 拦截器 | 不引入第二写入点，`batch_save` 只需管 `holds` 一处；B 方案的触发器/回写会被批量保存路径绕过 |
| 看板类聚合 | 若后续需要「挂起总量」看板，走**异步只读汇总**（可重建），绝不进写路径 |

#### 10.4.5 何时才升级到 B

同时满足才考虑：① `EXPLAIN QUERY PLAN` 已确认为 `SEARCH ... USING INDEX` 但仍超时；② 目标页面是高频列表/看板且实测 P95 超标；③ 汇总列由异步消费者重建（可随时 `DROP` 后从 `holds` 重算），且只读、不被业务写路径更新。

### 10.5 依据来源

- Oracle `AP_HOLDS_ALL` 表结构与列语义：<https://irvineanalytics.ai/catalog/tables/ap_holds_all.html>
- Oracle 发票 Holds 子资源与「挂起 / 释放」事件：<https://processmind.com/continuous-process-improvement/accounts-payable-payment-processing/oracle-fusion/data-template>
- SAP 不完整状态字段 `VBAK-UVALL` / `VBAP-UVALL`：<https://open-exam-prep.com/study-guides/sap-s4hana-sd/basic-functions-customizing/incompletion-procedures>
- SAP Incompletion Log「允许继续处理」的语义：<https://jigarsoni.wordpress.com/sap-sd/incompletion-log/>
- Salesforce 审批记录锁 `ENTITY_IS_LOCKED`：<https://salesforcedictionary.com/errors/entity-is-locked-for-approval>
- Salesforce 锁为流程自动施加的独立维度：<https://salesforcedictionary.com/terms/initial-submission-actions>
- DMN hit policy（Unique / First / Priority 定义）：<https://issues.omg.org/secure/attachment/10873/Improved%20chapter%208.1-8.2-8.4%20FTF%20(1).pdf>
- DMN hit policy 一览（A/P/F/C/R）：<https://quantumbpm.com/docs/dmn/expressions/decision-table>
- Flowable DMN 对 Priority 的运行时解释：<https://www.flowable.com/open-source/docs/dmn/ch06-DMN-Introduction>
- SAP 消息类型 `W` 确认后可继续、不单独留痕：<https://www.corepath.es/blog/sap-gui-message-types.html>
- SQLite 部分索引（查询须重复索引的 `WHERE` 谓词）：<https://www.sqlite.org/partialindex.html>
- SQLite 查询规划器与 `EXPLAIN QUERY PLAN` 判读（`SCAN` vs `SEARCH ... USING INDEX`）：<https://www.sqlite.org/optoverview.html>
- SQLite 生成列限制（仅可引用同一行的常量与列，禁子查询 / 聚合 / 窗口函数）：<https://www.sqlite.org/gencol.html>

---

## 11. M1–M5 二次复核（2026-11-10）

### 11.1 复核遗漏清单

| # | 问题 | 证据 | 处置 |
|---|---|---|---|
| 1 | **三套 `hit_policy` 词表同名不同义**：M5 为 `first/all/unique`（规则集选择）；场景注册表为 `first/best/all`（trace 解释枚举）；lookup/rate 为 `exclusive/additive`（取值聚合） | `rule_hit_policy.py` / `rule_scenarios.py:39,63,71,79,87,95,103` / `lookup_resolver.py` | 不强行统一值域；建议场景侧字段改名 `trace_policy`，M5 侧保留 `hit_policy`，消除跨模块误读 |
| 2 | **`approval` 场景声明 `hit_policy='all'`，运行期实际取首条** | `rule_scenarios.py:79` vs `document_approval_service.resolve()` | 场景字段改名后分别声明 `trace_policy=all`、`selection_hit_policy=first`；当前文档标注「场景值不参与运行期选择」 |
| 3 | **`MetaRule.hit_policy` 声明后无运行期消费**：`RuleProvider` 明确不排序/不过滤（保持 YAML 顺序），L1 校验等价 `all` | `rule_provider.py:17-23` | 加载期加 lint：非选择型 `rule_type` 声明 `hit_policy=first/unique` 报 `RULE_HIT_POLICY_UNSUPPORTED`；或文档限定生效范围 |
| 4 | **`unique` 重叠检查只做条件文本归一相等**，不识别语义重叠（`>100` vs `>=100`），也不区分不同 `effective_from` | `rule_declaration_validator.validate_hit_policies` | 明确为 lint 下界（不替代人工建模评审），写入 §9.9 |
| 5 | **validation 页签 `severity` / `enabled` 列空白**：描述符未透出 | `rule_catalog_service._descriptor` | **已修**：新增 `severity` / `enabled` 键，`_bo_yaml_descriptors` 传入 |
| 6 | **`MetaRule.priority` 注释与 M5 排序方向相反**：注释「数字越小越先执行」，`ORDER_BY` 为 `priority DESC` | `models.py` `priority: int = 100` vs `rule_hit_policy.ORDER_BY` | 当前 `MetaRule.priority` 未参与运行期排序（仅展示），不改变行为；须统一注释口径为「数值越大优先级越高」 |
| 7 | **`FILTER_KEYS` 声明 `severity/enabled` 但 `list_rules` 未实现对应过滤** | `rule_catalog_service.FILTER_KEYS` / `list_rules` | 前端若下发该筛选则静默失效；补过滤或从 `FILTER_KEYS` 移除 |
| 8 | **销售 `allow_over_delivery` / `allow_under_delivery` 仅种子、无消费方** | `init_sales_config_seed.py:49,51,113,114`（全仓无其它引用） | 属死配置；接入 M6 容差收敛时一并处理，否则直接删除 |

> `approval_policies` 无 `version` 列（v178 仅有 `priority/effective_from/effective_to`）不算缺陷：视图留空如实反映；若需策略集版本，单独迁移补列。

### 11.2 容差（tolerance）：现状与 M6 提案

**结论：当前没有场景级容差规则模型。** 容差以四种互不相同的形态散落在各服务：

| 业务 | 形态 | 落点 |
|---|---|---|
| 采购收货 | 控制参数百分数 → 倍数 | `receipt_service.TOLERANCE_PARAM`（`receipt_over_tolerance_percent`）、`_tolerance_ratio()` |
| 调拨发运/收货 | 控制参数百分数，按维度解析 | `transfer_order_service.resolve_tolerance_ratio()`（`TOLERANCE_SHIP_PARAM` 等） |
| 库存盘点 | 单据头字段 `tolerance_qty_pct / tolerance_qty_abs` + 控制参数默认值 | `inventory_count_service`（`max(abs, snapshot_qty × pct)`） |
| 销售交货 | 布尔开关（且当前无消费方） | `init_sales_config_seed.py` |

形态差异：bool / 百分数 / 单据头字段 / float epsilon，判定逻辑也各写一遍，无法用一张 `explain` 回答「偏差多少、容差多少、为何拒绝」。

#### 11.2.1 提案（M6，按「元数据驱动 + 单一事实源」重排）

**先撤回上一版的四处设计**：

| 撤回 | 原因 |
|---|---|
| 代码侧 `tolerance_key` 封闭字典 | 与 `control_parameter_defs.code` 双写，构成第 5 套代码级词表（违反 §13.4「禁止手写第二份业务枚举」）；闭合性改由**引用完整性**保证：规则引用的 code 必须存在于 defs 且 `domain='tolerance'` |
| `source=control_parameter + bo_yaml` 的 `tolerance` 场景 | `ScenarioSpec.source` 是单值（`meta/core/rule_scenarios.py` 的 dataclass），多载体需改 `SOURCES` / `NOT_INSTRUMENTED_SOURCES` / trace handler / `validate_registry` 四处闭合校验；且当前无 trace 消费方 |
| `hit_policy=first` | 与容差「多键并行、任一超限即触发」语义相反（SAP OMC0/OMR6、Oracle 容差集都是全量判定）；`first` 只用于同一 key 内的维度覆盖 |
| `tolerance_pct` 单标量 + explain 把限值放 `expected` | 丢失「方向 × 基准」信息；且与 `control_parameter.explain()` 的候选链形成两套答案 |

**分层（每层只有一个事实源）**：

| 阶段 | 内容 | 唯一事实源 |
|---|---|---|
| **M6a-0** | 删除 `receipt_service._tolerance_ratio()` 的裸 SQL（无维度、`ORDER BY id DESC`），改走 `ControlParameterResolver`；收货 / 调拨取值口径合一 | `control_parameter_defs` + `control_parameter_values` + resolver |
| **M6a-1** | 限值只以参数存在：`domain='tolerance'`，限值身份 = 参数 code。需要结构化表达「方向 / 基准」时，给 `control_parameter_def` 加字段（`tolerance_direction` / `tolerance_basis`），走 schema + 迁移 + 目录列**一次声明**，而不是新增代码字典 | `meta/schemas/control_parameter_def.yaml` |
| **M6a-2** | 盘点单据头容差保留为**实例层**（单维度，符合控制参数进入门槛①）：优先级 = 单据头 > 参数行（`specificity_rank`）> `def.default_value`；继续遵守「落库快照、不随配置漂移」 | 盘点单据头 + resolver |
| **M6a-3** | 规则条件若用 `deviation_rate` / `deviation_qty`：先补 `metrics:` YAML → `DEFAULT_METRIC_REGISTRY` 加载通道（现状：注册表为空、`meta/schemas` 无 `metrics` 段，直接写会触发 `RULE_METRIC_UNDECLARED`） **（已实现 2026-11-10：BO YAML 新增 `metrics:` 段，`yaml_loader._parse_metric_definitions` 加载期解析，`register_metric_definitions()` 按 object_type 整体替换灌入注册表（reload 幂等）；`validate_all()` 传入 `known_fields` 校验 inputs；`inventory_count_line` 首批声明 `deviation_qty` / `deviation_rate`）** | 新增 `metrics` 元数据（与 `control_parameter_def` 同等待遇） |
| **M6b** | 判定规则化：复用 `constraint` rule_type（**不扩 `RuleType` 枚举**，避免牵动 `rule_type × action` 白名单）；规则显式声明 `combine_mode=any\|all`（默认 `all`）与超限动作（**沿用现有 `constraint` 矩阵：`block / hold / notify`**，不新增 `warn_ack / route`） **（已实现 2026-11-10，见 §11.2.2）** | BO YAML 规则 |

**判定与解释契约**：

- key 内：参数 resolver 按 `specificity_rank` 首命中，沿用现有 `explain()` 候选链（命中行、候选列表、`specificity_rank`）。
- key 之间：全部 key 求值（`all`），结果按 severity 升级（`error > warning > info`），动作取最高等级。
- explain 分两节点：`limit` 节点直接引用参数 explain；`verdict` 节点只记录度量值、比较符与结论，**不重复限值字段**。
- `hold` 是独立结果（可存不可过），必须声明释放动作（改单修正 / 人工释放），与 SAP 付款冻结、Oracle 系统 Hold 对齐。

#### 11.2.2 M6b 实现状态（2026-11-10）

**已实现（声明层 + 判定层 + 盘点服务接线 + `hold` 落库 / 释放路径）**：

| 层 | 落点 | 内容 |
|---|---|---|
| 词表 / 默认值 | `meta/core/rule_combine_mode.py` | `any / all`，默认 `all`，非法值由加载期校验拒绝 |
| 模型字段 | `meta/core/models.py` | `MetaRule.combine_mode`；`MetaConstraint.keys` / `release_action` |
| YAML 解析 | `meta/core/yaml_loader.py` | `parse_rule` 与 `parse_constraint` 均注入 `combine_mode`（小写），`keys` / `release_action` 直取 |
| 加载期校验 | `meta/core/rule_declaration_validator.py` | `RULE_COMBINE_MODE_INVALID` / `RULE_KEY_INVALID` / `RULE_HOLD_RELEASE_MISSING`；key 级 `disposition` 走既有 `validate_action`（`RULE_ACTION_INVALID`） |
| 判定器 | `meta/core/rule_constraint_evaluator.py` | `evaluate_constraint_rule()`：逐 key 求值（不短路），severity `error > warning > info`，动作取最高；`explain()` 输出 `limit`（引用参数 explain）+ `verdict`（仅度量/比较符/结论）两节点；实例层覆盖经 `overrides` 传入 |
| 单测 | `meta/tests/test_rule_constraint_evaluator.py` / `test_rule_combine_mode.py` | 判定 / explain / override / any-all / 加载期校验 |
| 服务接线 | `meta/schemas/inventory_count_line.yaml` + `meta/services/inventory_count_service.py` | `rules: inventory_count_line_tolerance` 成为容差唯一事实源；`submit()` 调 `evaluate_constraint_rule()`，规则缺失 `RuntimeError`（不代码兜底） |
| 挂起表 | `meta/schemas/rule_hold.yaml` + `meta/migrations/v231__rule_hold.py` | `holds`（TBD-6 字段）+ `idx_holds_active` / `uq_holds_active` 两个部分索引（`WHERE released_at IS NULL`）；`skip_generic_api` / `skip_auto_menu`，不做通用 CRUD 与菜单 |
| 挂起服务 | `meta/services/rule_hold_service.py` | `apply()` 幂等（部分唯一索引兜底）/ `release()` 置 `released_by/released_at` 不删行 / `is_held()`、`active_holds()`；active 谓词只在 `_active_where()` 出现，禁止手写 holds SQL |
| 盘点接线 | `meta/services/inventory_count_service.py` | `submit()` 超容差行 apply hold、容差内行 release；`approve()` / `cancel()` 释放本单**全部** active holds（不限 `rule_key`，历史行保留）；`post()` 存在任一 active hold 时抛 `INV_COUNT_HELD`（可存不可过） |
| 审计留痕 | `meta/services/inventory_count_service.py` + `audit_interceptor.py` | submit / approve / cancel 的挂起与释放写 `audit_logs`（`CNT_LINE_OBJECT`，old/new 含 `hold` / `rule_key` / `code` / `reason` / `released_by`）；审计在业务事务提交后写，失败只告警不影响业务；测试替身无 `audit_logs` 表时经 `_audit_available()` 探测跳过 |
| 单测 | `meta/tests/test_rule_hold_service.py` | 幂等 / 部分唯一索引防重 / 释放保留行可再挂起 / `EXPLAIN QUERY PLAN` 命中部分索引 / 盘点 submit-approve-cancel 全链路 / approve 释放全部规则 / active hold 阻断 post |

**key 形状（SSOT）**：`{parameter, metric, severity?, disposition?}`；方向 `over / under / both` 与基准 `percent / absolute` 只从 `control_parameter_defs`（`tolerance_direction` / `tolerance_basis`）读取，规则内不重复书写比较符。

**明确延后（不在 M6b 内）**：

1. `release_action` 执行语义：只做声明必填校验，尚未有通用执行器消费（盘点首版由 `approve()` 直接释放本单全部 active holds，与规则声明的 `inventory_count.approve` 对齐）。
2. holds 的对外查询 API / 前端挂起提示 / 人工释放入口：当前只有服务层 `active_holds()`，无 HTTP 出口与 UI 呈现。
3. 单据删除 / 作废不级联清理 holds：存在产生孤儿 active 行的风险（当前仅 `cancel()` 主动释放）。
4. `holds.release_reason` 列（TBD-12 提到的释放理由）：首版释放只记 `released_by` / `released_at`，释放理由暂由调用方写入审计 `new_data.reason`（`inventory_count.approve` / `inventory_count.cancel`），不落独立列。

**服务接线（2026-11-10）**：`inventory_count_service.submit()` 的超容差判定改由 BO 规则执行 ——
`inventory_count_line.yaml` 的 `inventory_count_line_tolerance`（`combine_mode=all`，两 key：
`deviation_rate` × 比例容差、`deviation_qty` × 绝对容差，等价原 `max()` 口径）是唯一事实源；
比例 / 绝对容差是抬头实例值，经 `overrides` 传入（绝对容差不进参数池）；快照为 0 的行裁掉
`deviation_rate` 键（除零防护，数学上与原口径等价）。

**迁移映射**：

| 存量 | 迁移后 |
|---|---|
| 收货 `receipt_over_tolerance_percent` | 参数 code 不变，读取路径改为 resolver；若历史上配了维度，行为变化需逐单 diff |
| 调拨 `resolve_tolerance_ratio()` | 保持走 resolver，仅补 `explain` 透出 |
| 盘点单据头 `tolerance_qty_pct/abs` | 保留为实例层覆盖，不搬进参数池 |
| 销售 `allow_over_delivery` / `allow_under_delivery` | 按方向各建一个参数（`gr_over_*` / `gr_under_*` 语义），**不合并为单个 `tolerance_pct=0`**；若确认无消费方，按治理规则直接下线而非迁移 |

**验收口径（M6a）**：同一 `control_parameter_values` 行在收货 / 调拨 / 盘点三个域的解析结果一致；`explain()` 能回答「命中哪条参数行、限值多少、偏差多少、为何拒绝」；全仓不再有第二处裸 SQL 读取容差参数。