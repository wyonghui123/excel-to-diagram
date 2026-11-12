# 研究：共享服务中心（SSC）的对象模型

> 范围：服务目录 → 请求 → 任务 → 队列 → 履约 → 契约（SLA/OLA/UC）→ 成本。
> 目的：判断现有对象能否承载「共享中心」，并给出最小新增集。

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| 行业有没有统一模型 | 有。全行业都是同一个五件套：**目录 → 请求 → 任务 → 队列 → SLA**，差异只在「请求是否与工单合并」和「是否做 OLA/UC」。 |
| 我们现有底座够不够 | **执行底座够，服务前端缺**。`tasks` 的 11 态 + 候选池 + 认领超时 + 审核态，已经是标准派工引擎；缺的是目录、请求单、队列对象、契约分层。 |
| 最大的结构差异 | **双组织**。共享中心是「A 组织提需求、B 组织提供服务」，普通服务台只有单边。请求必须同时携带 `requester_org_id` 与 `provider_org_id`。 |
| 请求能不能塞进 `work_order` | **不能**。请求是「我要什么」（客户视角、可未受理），工单是「谁去做、怎么做」（执行视角、必有承接方）。合表会让未受理请求被迫生成工单。 |
| 最小新增集 | `service_catalog_item`、`service_request`（+ 行）、`assignment_group`（队列）、`requester/provider_org_id` 两个字段、SLA 的 `agreement_level`。 |

## 1. 行业实态

| 产品 | 目录 | 请求 | 任务 | 队列 | 契约 |
|---|---|---|---|---|---|
| ServiceNow（含 GBS / HR Service Delivery） | `sc_catalog` / `sc_cat_item` | `sc_request` → `sc_req_item` | `sc_task` | `assignment_group` | SLA / OLA / UC 三件套 |
| Jira Service Management | Request type + Portal | Request | Issue（子任务） | Queue | SLA（按 request type 绑定） |
| Zendesk | 无独立目录（表单近似） | Ticket | 子任务 | Group | SLA policy |
| Freshservice | Service Catalog | Incident / Service Request | Task | Group | SLA |
| SAP SuccessFactors EC Service Center | 服务项 | Case | Activity / Task | 服务团队 | SLA |
| SAP S/4 财务共享（Financial Shared Services） | 业务类型（报销 / 应付 / 总账） | Case / 单据 | Task | 处理组 | SLA + 分摊 |
| Workday Help | 服务目录 | Case | Task | 支持组 | SLA |
| 金蝶（任务共享中心 / 财务共享） | 无独立目录（业务单据即入口） | 业务单据（报销 / 应付 / 收款） | 共享任务 | 任务池（待分配 / 待办 / 已办 / 我管理的） | 时效 + 质检 |

五条共性：

1. **目录是"可申请清单"，不是价格表**。目录项绑定的是流程、表单、SLA、审批策略，不是金额。
2. **请求与任务是两层**。一个请求可拆多个任务、可跨团队；任务才是可认领、可计时的最小单元。
3. **队列是对象，不是字段**。队列承载技能、容量、SLA、派工策略；人员变动不改任务数据。
4. **契约是三层**。SLA 对请求人、OLA 对内部协作团队、UC 对供应商；三层共用同一事实载体，靠层级字段区分。
5. **共享中心必有分摊**。财务/HR/IT 共享都要把成本分摊回请求方组织，这是与普通客服的实质区别。

### 1.1 金蝶：单据即请求

金蝶的「共享任务中心」不走目录 + 请求，而是：

```
业务单据（报销单 / 应付单 / 收款单，可来自多组织、甚至 EAS/SAP 等异构系统）
   → 单据流程中的「共享服务节点」
   → 共享任务入任务池
   → 任务分配规则（按组织 / 金额 / 技能 / 负载）派给共享会计或机器人
   → 处理（含影像核对）→ 审核 → 归档
```

四个关键差异：

1. **请求被折叠进业务单据**。没有独立 `service_request`：单据本身就是请求。因此不需要「未受理请求」这个阶段，单据流程节点决定任务何时产生。
2. **任务池是核心对象**，分「待分配 / 待办 / 已办 / 流程消息 / 我管理的任务」五种视图，说明队列不是简单字段，而是带状态与可见范围的容器。
3. **影像与质检是对象级能力**：影像扫描点（OCR）作为单据附件通道；智能质检按抽检规则与质检方案抽单，**不合格自动生成整改任务**。
4. **服务多组织 + 异构系统**：共享中心同时处理各组织的单据，印证了「双组织」判断——请求方组织来自单据，服务方是共享中心组织。

对我们的直接启示：财务型共享**不需要** `service_request`，业务单据即请求；只有服务型共享（HR / IT 服务台）才需要目录 + 请求。这条把 S2 从「必建」收窄为「服务型必建」。

## 2. 我们的实态（代码取证）

| 能力 | 现状 | 证据 |
|---|---|---|
| 任务与派工 | 已有：11 态、`executor_type/assignee/candidates`、`assign_policy`（direct / claim / round_robin / skill_based / ai_routed）、`claim_timeout_seconds`、`waiting_approval`、父子任务 | `meta/core/task_schema.py` |
| 编排 | 已有：workflow 定义 + `trigger_kind=schedule` 作业派生 + `workflow_run` 执行实例 | `meta/core/workflow_schedule_scheduler.py` |
| 时限 | 部分：`sla_milestone` + `service_event`，只有单层，无 OLA/UC | `meta/schemas/work_order.yaml`、`service_event.yaml` |
| 履约 | 已有：`work_order`（service / production）+ `work_order_operation` | `meta/schemas/work_order.yaml`、`work_order_operation.yaml` |
| ITSM 邻接 | 仅 `change_request` 一个对象，无 incident / problem / request | `meta/schemas/change_request.yaml` |
| 服务目录 | **无** | 全仓无 `service_catalog` / `cat_item` |
| 请求单 | **无** | 全仓无 `service_request` / `case` / `ticket` |
| 队列 / 组 | **无**（只有任务上的 `executor_candidates` JSON） | 全仓无 `queue` / `assignment_group` / `workgroup` |
| 知识 | **无** | 全仓无 `knowledge` |
| 分摊 / 费率 | **无**（只有 `worklogs`） | 无费率 / 分摊对象 |

## 3. 设计：SSC 五层对象模型

```
服务层   service_catalog_item ──(流程/表单/SLA/审批策略)──> workflow 定义
                    │
请求层   service_request ──1:N──> service_request_item
          requester_org_id / provider_org_id（双组织）
                    │
分解层   tasks（11 态，app_id=ssc，doc_ref=service_request）
          queue_id ──> assignment_group（技能/容量/派工策略/SLA）
                    │
履约层   work_order（现场/实物） ｜ purchase_order ｜ knowledge_article
                    │
契约层   sla_milestone（agreement_level = SLA / OLA / UC） ｜ 审批 = tasks(type=approval)
成本层   task_worklogs ──派生视图──> 分摊到 requester_org_id（不落汇总表）
```

关键约束：

- **请求不生成动作，任务才生成动作**（与 `project_task` 同一纪律）。
- **队列是对象**：`tasks.queue_id` 只引用 `assignment_group`；`executor_candidates` 由队列的技能/容量派生，不手工填人。
- **双组织必填**：`requester_org_id` 决定数据权限（走 org 维度），`provider_org_id` 决定派工范围（走队列/组）。
- **契约只加一个层级字段**：`sla_milestone.agreement_level ∈ {SLA, OLA, UC}`，不新建三张表。
- **审批复用任务**：不新增审批表，沿用 `waiting_approval` + 审核子任务（`type=approval`）。
- **分摊先做视图**：与项目侧 D11 一致，等对账/结账出现再固化。

### 3.1 SR 与 SO 的关系：同为需求单，不是子类型

| 维度 | 销售订单（SO） | 服务请求（SR） |
|---|---|---|
| 当事人 | 外部客户 `customer_account` | 内部员工 / 组织 `party_internal` |
| 行内容 | 物料 + 价格 | 目录项 + SLA（可能无物料） |
| 金额 | 有价、有收入确认 | 无价（或按成本分摊） |
| 履约判定 | 发货 + 开票 | 验收 / 关闭 + SLA |
| 成本 | 毛利 | 分摊到请求方组织 |

结论：SR 与 SO、`project_task`、补货点处于**同一层**——都是「需求单」，各表达「谁要什么、何时要」。供给方式由 `sourcing_rule` 决策（自制 / 采购 / 调拨），执行落在 `work_order` / `purchase_order` / 调拨单。SR 因此**不是** SO 的子类型，也不复用 `sales_order` 表。

实物场景：SR 要实物时，SR 仍是需求壳，实物走 sourcing_rule → 调拨 / 采购 / 生产；若为「服务 + 备件」，一个 SR 产出 1 张 `work_order` + N 条物料需求。

术语提醒：SAP 的 "internal sales order" 指法人间交易（有价有票），与 SR 语义不同，不沿用该词。

口径补充：我们的 `sales_order` 已统一承载实物与服务（按行类型区分），因此 SR 可视为**同一订单形状的内部版本**——行是目录项而非 SKU，价是 SLA 而非金额，完成是关闭而非开票。若内部需要收费，生成内部结算 / 分摊，不改变请求对象本身。三层术语仍须分开：Service Order（有价服务订单）≠ Service Request（内部请求）≠ Work Order（执行派工）。

对外场景同样复用 SR。判断要不要换对象，不看当事人是内是外，而看**履约是否计价**：① 保修内（免费但受权益约束）；② 合同内（已付费）；③ 单次收费（需订单行）。三种都由「服务权益（entitlement）」判定，SR 本身不携带价格。因此外部维修 / 维护走同一个 SR，只是多一步权益校验。

### 3.2 SR 行：服务与实物都承载

区分放在**行**，不放在单据头——与 `sales_order` 已统一的 `line_type` 一致。

| 行类型 | 必填 | 履约路径 | 完成判定 |
|---|---|---|---|
| service | `catalog_item_id`（不强制 `item_id`） | `work_order` / `tasks` | 验收关闭 |
| goods | `item_id` + 数量 + 需求日期 | `sourcing_rule` → 调拨 / 采购 / 生产 | 出库 / 收货 |

四条规则：

1. **单据头不带价格与开票字段**；计价只在订单 / 合同层。
2. **实物行必须有 `item_id`**；服务行只要求目录项，允许无物料（如权限开通）。
3. **完成按行判定**，单据状态取「全部行关闭」。
4. **拆履约不拆需求**：一个混合 SR 可产出多张执行单据（如 2 张 `work_order` + 1 张调拨单），但请求只有一张。
5. **goods / service 行都派生 `requisition` 行，或按轻路径直连执行单据**：service 行若承接方已定且无需结算，可直连 `work_order(service)`（T-D18 轻路径）；goods 行一律派生 `requisition` 行再走 sourcing。行类型**不决定**「买还是自供」——买 / 做由 sourcing 判定（T-D17）。

### 3.3 纯实物 SR：内部请购 / 领用 / 调拨

判断「是不是新对象」仍按履约路径分，不按物料占比分：

| 场景 | 执行载体 | 是否计价 |
|---|---|---|
| 同组织、同库存地点 | 领用 / 出库（issue） | 无价，成本转到请求方成本中心 |
| 跨库存地点 / 工厂（同法人） | 调拨单（transfer / STO） | 无价，成本随货转移 |
| 跨法人 / 跨 BU | 内部销售订单（internal SO）+ 内部发票 | **有价**，这才是真正意义上的「内部销售订单」 |
| 库存不足 / 需外购 | 采购申请（PR）→ 采购订单 | 有价（外部价） |

三条结论：

1. 纯实物 SR 就是**内部请购 / 领用申请**，不新造对象；SR 仍是申请，领用单 / 调拨单 / PR 才是执行。
2. 「SR 是不是内部销售订单」**只在跨法人时成立**；同法人内它只是领用需求。
3. SAP 的 Reservation（预留）是占库机制，不是需求单据，不能拿它替代 SR。

### 3.4 转换机制：sourcing 只回答「谁供」

`sourcing_rule` 的职责边界是**选源**（自制 / 采购 / 调拨 / 内部供应），产出只是「供方组织 / 供应商」。真正落单还要四个条件同时成立：

1. **供应关系**：Oracle 要求供方组织配置为 internal supplier、请求方为 internal customer，且有 shipping network；SAP 要求 source list / 供货工厂。
2. **转换方式**：push（保存即自动生成供方单据）或 pull（供方在任务池认领后再转，金蝶 / 共享中心模式）。
3. **转移价**：跨法人必须有内部转移价，否则无法开内部发票；同法人按成本价或成本中心转移。
4. **转换动作**：由单据服务执行，失败要能回退到需求态。

### 3.5 内部销售订单是怎么生成的

| 产品 | 同法人 | 跨法人 |
|---|---|---|
| Oracle EBS / Fusion | Internal Requisition → Internal Sales Order（不开发票） | 同上 + Intercompany AR/AP 与内部发票 |
| SAP | STO（一单兼具采购订单与销售订单身份，无 billing） | 跨公司 STO + intercompany billing（或公司间销售订单） |
| Dynamics 365 SCM | Transfer Order | 成对生成「公司间销售订单 + 公司间采购订单」 |
| NetSuite | Transfer Order | 成对生成 Intercompany SO / PO（Advanced Intercompany） |
| Epicor | Transfer Order | Intercompany Sales Order / Purchase Order 成对 |

结论：「跨法人才有内部销售订单」只在**开票**层面成立——跨法人才开内部发票。载体是否叫 ISO 取决于产品：SAP 看起来没有 ISO，是因为 STO 一单两身份。纯采购平台（Coupa / Ariba）没有内部需求模型，不参与这一层。

我们的载体选择与判据（A + D、三问切换、信息统一锚点）见 [采购任务对象模型](./spec-procurement-task-object-model-2026-10-31.md) §3.1 / T-D8。

## 4. 缺口清单

| # | 缺口 | 等级 | 影响 |
|---|---|---|---|
| S1 | 无服务目录（`service_catalog_item`） | P0 | 用户无「可申请清单」，请求只能自由文本 |
| S2 | 无请求单（`service_request` + 行） | P0（仅服务型） | 服务型共享缺请求载体；财务型共享以业务单据为请求，不需此对象 |
| S3 | 无队列对象（`assignment_group`） | P0 | 派工靠 `executor_candidates` 手填，无技能/容量/队列级 SLA |
| S4 | 无双组织字段 | P0 | 共享中心跨组织服务无法表达「谁提的 / 谁服务的」 |
| S5 | SLA 只有单层，无 OLA / UC | P1 | 内部协作与供应商时限无契约，升级路径断裂 |
| S6 | 无知识对象 | P1 | 自助解决率无载体，复用经验无落点 |
| S7 | 无审批策略对象 | P1 | 审批人靠流程硬编码，无法按目录项/金额自动选 |
| S8 | 无满意度 / 回访（CSAT） | P2 | 服务质量不可度量 |
| S9 | 无分摊 / 费率 | P2 | 共享中心无法向内收费 |
| S10 | 无质检抽检与整改任务 | P1 | 共享中心运营质量不可度量（对标金蝶「智能质检」） |
| S11 | 无合同 / 服务权益（entitlement） | P0 | 对外保修、合同内服务无法判定「是否免费、是否覆盖、限几次」 |

## 5. 决策建议

| # | 决策 | 理由 |
|---|---|---|
| S-D1 | 服务型共享新建 `service_request`（不复用 `work_order`）；财务型共享以业务单据为请求载体 | 工单是执行视角、必有承接方；金蝶证明财务共享「单据即请求」成立，但服务台无单据可依 |
| S-D2 | `assignment_group` 作为独立对象，`tasks.queue_id` 单一引用 | 队列承载技能/容量/SLA/派工策略；人员变动不该改写任务数据 |
| S-D3 | 双组织字段落在请求单，不落在任务 | 权限判据是「请求属于谁」，任务只继承 |
| S-D4 | SLA / OLA / UC 共用 `sla_milestone`，加 `agreement_level` | 三者的计时、暂停、升级逻辑同构，分表会造成三套实现 |
| S-D5 | 审批复用 `tasks(type=approval)` | 已有 `waiting_approval` 与审核子任务，保持 11 态唯一状态机 |
| S-D6 | 目录项只绑定流程/表单/SLA/审批策略，不绑定价格 | 价格属于商务层（`sales_order` / 合同），目录是入口不是报价 |
| S-D7 | 分摊先出派生视图，不落汇总表 | 与项目侧一致，避免过度设计 |
| S-D8 | 权限双向但分轨：requester 走 org 维度，provider 走队列范围 | 两套判据语义不同，混用会互相污染 |

## 6. 开放问题

- Q1 请求单与 `work_order` 是否要 1:1 强绑（一次请求一次上门），还是允许「一个请求多张工单」？建议后者。
- Q2 队列与组织是否合并（队列 = org + 能力标签），还是独立对象？建议独立，避免组织调整打散派工历史。
- Q3 知识对象首版是否只做「文章 + 关联目录项/请求」，不做版本与评审？
- Q4 SSC 是否需要「服务目录版本化」（目录项下线不影响历史请求）？
- Q5 `requester_org_id` 是否允许为空（外部客户提请求时用 `customer_account` 代替）？
- Q6 是否需要「一次请求跨法人」的分摊规则，还是按请求行拆组织？

## 7. 证据清单

- `meta/core/task_schema.py`（11 态、`executor_candidates`、`assign_policy`、`claim_timeout_seconds`、`waiting_approval`）
- `meta/core/workflow_schedule_scheduler.py`（workflow 定义 → 作业派生）
- `meta/schemas/work_order.yaml`、`work_order_operation.yaml`（履约与工序）
- `meta/schemas/service_event.yaml`、`sla_milestone` 相关定义（单层时限）
- `meta/schemas/change_request.yaml`（唯一 ITSM 邻接对象）
- `meta/services/org_admin_scope_service.py`、`meta/schemas/dimension_object_mapping.yaml`（org 数据权限载体）
- `docs/specs/spec_权限体系升级/23_primary_org_data_permission.md`（requester 侧权限）
- `docs/specs/spec-project-type-object-model-research-2026-10-31.md`（分层与「计划不产动作」纪律）

### 外部样本（公开资料）

- 金蝶云·星瀚《共享任务中心整体介绍》：接收各组织及异构系统单据，按任务分配规则智能派工，机器人智能审批，任务分布 / 时效 / 质量统计
- 金蝶云产品手册《任务共享中心》：任务池分待分配 / 待办 / 已办 / 流程消息 / 我管理的任务；影像扫描点
- 金蝶 EAS Cloud 财务共享：费用任务池、OCR / RPA、多组织批量处理
- 金蝶云·星瀚财务共享解决方案：智能质检（抽检规则 + 质检方案 + 不合格自动生成整改任务）

### 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-31 | 初版研究稿 v1.0（仅取证与设计建议，未改代码、未提交） |
| 2026-10-31 | v1.1：补金蝶「任务共享中心」样本（§1.1）；S2 收窄为「服务型必建」；新增 S10 质检；S-D1 同步 |
| 2026-10-31 | v1.2：补 §3.1 SR 与 SO 关系、对外场景与权益；§3.2 SR 行承载服务与实物；§3.3 纯实物 SR = 内部请购 / 领用 / 调拨；新增 S11 合同 / 权益 |
| 2026-10-31 | v1.3：补 §3.4 转换四条件、§3.5 各产品 ISO 生成差异；修正「同法人不转 ISO」的表述 |
| 2026-10-31 | v1.4：§3.5 增加与采购 spec §3.1（内部交易载体与判据）的交叉引用，避免两份研究各自演化出口径分裂 |
