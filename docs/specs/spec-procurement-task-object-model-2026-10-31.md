# 研究：采购任务的对象模型

> 范围：采购需求 → 采购订单 → 收货 → 发票 → 付款，以及「采购任务」在这条链上的位置。
> 目的：确认采购任务是不是一种新对象，并给出最小新增集。

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| 「采购任务」是不是一种对象 | **不是**。它是 `tasks` 上 `app_id + doc_ref` 的一种用法（流程节点的待办），不需要新对象。行业里也没有「采购任务表」。 |
| 采购的执行对象是什么 | 三段单据：**需求（PR）→ 订单（PO）→ 收货 / 发票**。需求行不是成本对象，订单行才是。 |
| 我们缺什么 | 整条采购单据链都缺：无 `purchase_requisition`、`purchase_order`、收货、发票；只有 `sourcing_rule` 在做「自制 / 采购 / 调拨」的来源路由。 |
| 采购需求从哪来 | 三源合一：销售计划行、`project_task`、库存补货。与 `work_order.source_demand` 同构，不要各写一套。 |
| 最容易踩的坑 | **合并采购**。一张 PO 行服务多个需求行，必须用分配表；用单个 `project_task_id` 字段会在合并后丢失归属。 |
| 内部交易用什么对象 | **A + D**：跨法人有价走 `sales_order` 内部单据类型；同法人跨地点走独立 `transfer_order`。不采用 SAP 的 PO+STO 形态，也不默认成对生成 SO/PO。 |
| 信息怎么统一 | 协议事实（数量 / 转移价 / 交付期）只存一份在 ISO 行；其余单据只引用。预留 `intercompany_deal_id` 锚点，使 A 可低成本演进为独立内部交易对象。 |

## 1. 行业实态

| 产品 | 需求 | 订单 | 收货 / 发票 | 任务层 |
|---|---|---|---|---|
| SAP MM | PR（`EBAN`），带账户分配 `EKKN`（WBS / 成本中心 / 订单） | PO（`EKKO/EKPO`）+ 计划行 `EKET` | GR（`MSEG`）→ IR（`RBKP/RSEG`） | 工作流 workitem（无独立对象） |
| Oracle Procurement | Requisition | PO + 行 + 计划行 | Receipt → Invoice → Payment（三单匹配） | 审批动作，无独立对象 |
| Coupa / Ariba | 目录化请购（guided buying） | PO | 收货 / 发票异常处理 | 审批 + 待办 |
| 金蝶 | 采购申请 / 应付单据 | 采购订单 | 收料 / 应付 | 共享任务池（与 SSC 同一底座） |
| SAP PS 项目驱动 | PR 带 WBS 账户分配 | PO | GR 成本进 WBS | — |

五条共性：

1. **单据三段，需求与订单多对多**。合并采购靠「分配表」而不是字段。
2. **需求行不是成本对象，订单行是**。成本先落 PO 行，再按分配比例回聚到需求方。
3. **审批在需求层**。先批需求，再下单；订单层只在超权限变更时再审。
4. **供应商侧是外部事件**。ASN / 送货 / 验收不进内部任务状态机，只做对账。
5. **任务只是流程节点**。所有产品都用「工作流待办 / 审批动作」，没有「采购任务」这种业务对象。

## 2. 我们的实态（代码取证）

| 能力 | 现状 | 证据 |
|---|---|---|
| 来源路由 | 已有：`sourcing_rule` / `sourcing_rule_line` / `sourcing_rule_assignment`；`source_type ∈ {supplier, internal_org, internal_location}`，`supplier_party_id → parties.id` | `meta/schemas/sourcing_rule_line.yaml` |
| 供应商主体 | 只有通用 `parties`，**无供应商准入 / 绩效 / 结算条件** | 全仓无 `supplier` 表 |
| 内部主体表达 | **已有**：`party_internal`（法人 / 管理单元台账面）、`party_relation.role`（customer / vendor）、`party_relation.internal_mark`（内｜外标记） | `meta/schemas/party_internal.yaml`、`vendor_account.yaml` §0 |
| 采购单据 | **全缺**：无 `purchase_requisition` / `purchase_order` / 收货 / 发票 | 全仓无 `purchase*` / `receipt*` / `invoice*` |
| 物料需求 | 工单侧已有 `work_order_component`；项目侧无需求行 | `meta/schemas/work_order_component.yaml` |
| 任务与审批 | 已有：11 态、`waiting_approval`、`doc_ref` / `line_refs`、审批子任务 | `meta/core/task_schema.py` |
| 队列 | 无（见 SSC 研究 S3） | 全仓无 `assignment_group` |

## 3. 设计：采购链路与任务的位置

```
project_task / 销售计划行 / 补货点
        │  统一走 source_demand（type + id）
        ▼
purchase_requisition(+line)   ← 需求层，审批在这里（tasks type=approval）
        │  sourcing_rule 选源（自制 → work_order；采购 → PO；调拨 → 内部来源）
        ▼
purchase_order(+line) ──1:N──> purchase_order_line_demand_alloc（数量分配，支持合并采购）
        │
        ├─> receipt(+line)  ──┐
        ├─> invoice(+line)  ──┼─> 三单匹配（PO / GR / Invoice）
        └─> payment          ──┘

任务层：tasks(app_id='procurement', doc_ref='PR:<no>' / 'PO:<no>', line_refs=[line_id])
动作：询价 / 比价 / 审批 / 催交 / 三单匹配异常处理
```

关键约束：

- **采购不挂 `work_order_operation`**：它不是工序，是外部交易。
- **采购任务不建表**：复用 `tasks`，靠 `app_id` + `doc_ref` 归类；与「活动 / 待办」同一纪律。
- **合并采购必须有分配表**：`purchase_order_line_demand_alloc(po_line_id, source_demand_type, source_demand_id, qty)`。
- **外协不是采购**：委外加工走 `work_order(order_type=production)` + 供应商，不走 PO。
- **供应商不建新主数据表**：先给 `parties` 加供应商角色与准入字段。

### 3.1 内部交易：载体选择与「信息统一」的锚点

采购链唯一需要额外设计的边角是**跨法人内部交易**（内部销售订单 / 库存转储），它决定 `purchase_order` 是否要背 `from_org / to_org`。

#### 3.1.1 行业载体分布

| 载体路线 | 产品 | 计数 |
|---|---|---|
| **A 复用销售订单 + 内部单据类型**（Internal Requisition → Internal Sales Order） | Oracle EBS / Fusion | 1 |
| **B 复用采购订单 + 库存转储单据类型**（`UB`，存 `EKKO/EKPO`） | SAP | 1 |
| **C 成对生成 SO + PO + 关联** | Dynamics 365、NetSuite、Epicor、IFS（inter-site PO + CO）、JDE（ST/OT）、Sage X3、Infor M3、用友、金蝶 | **9（主流）** |
| **D 独立调拨 / 转储单（只承载物流）** | 几乎所有产品都另有这一条，与 A/B/C 并存 | 通用 |
| **E 独立内部交易对象** | Infor LN（Intercompany Trade Order）、浪潮 GS（内部订单） | 2 |

三条共性：

1. **跨法人用购销单据对（C），同法人用调拨单（D）**——D 只承载物流，不承载收入与利润分割，替代不了跨法人。
2. **结算 / 开票独立成对象是行业标配**（用友结算单、金蝶结算清单、M3 Internal Invoice、LN ICO、Sage 300 ICT、Workday Intercompany Event）。
3. **A / B 都依赖一个主数据前提**：客户或供应商档案能指向我方内部组织（Oracle 的 internal customer、SAP 的 plant as vendor）。

#### 3.1.2 为什么我们选 A + D，而不选 C 或 B

| 理由 | 说明 |
|---|---|
| 单系统、单订单实体 | 9 家走 C 的动机是「两侧各自有独立销售 / 采购模块与审批链」；我们是单系统，`sales_order` 已是唯一订单实体 |
| A 的前置条件已备 | `party_internal`（法人 / 管理单元）+ `party_relation(role='customer')` + `internal_mark` + `sourcing_rule_line.source_type=internal_org` 四件套已存在 |
| B 的前提我们不具备 | SAP 的供货方是 **plant（工厂）**，不是有独立销售组织的法人；我们有 `org_legal_entity / division / sales_org`，用采购单当销售载体属欠建模 |
| C 会立刻产生双份事实 | 成对单据天然存两份数量与金额，需要同步与对账；只有「两侧需独立审批 / 收货 / 三单匹配」时才值得付这个成本 |

#### 3.1.3 判据拆成三问（不是「是否独立审批」一条）

| 问题 | 性质 | 作用 |
|---|---|---|
| Q1 是否跨法人 | 法定主体变更 | 决定有没有价、内部发票、结算单 |
| Q2 接收法人是否需要自己的收货凭证与库存估值 | **法定账，跨法人恒为「是」** | 决定必须存在接收侧单据 |
| Q3 接收法人是否需要独立审批与三单匹配 | 治理 | 只在「是」时才升级到 C |

决策矩阵：

| 法人 | 库存组织 | 独立审批 | 载体 |
|---|---|---|---|
| 同 | 同 | — | 无单据（领用 / 库内移动） |
| 同 | 异 | — | `transfer_order`（无售价、无发票，**但有成本价**用于库存估值） |
| 异 | 异 | 否 | **ISO（A）+ 自动需求记录 + 接收方收货 + 内部发票** |
| 异 | 异 | 是 | C：成对 SO + PO（PO 承载审批 / 收货 / 三单匹配） |
| 异 | 同（寄售 / 共享仓） | — | ISO + 内部发票；物流不跨库存组织，但须记**所有权转移** |

#### 3.1.4 「信息统一」的三条硬规则

统一信息不等于合并对象：C 式的双份数量与金额才是信息不统一的根源。三条规则：

| # | 规则 | 说明 |
|---|---|---|
| R1 | **协议事实只存一份** | 数量 / 转移价 / 交付期的唯一载体是 ISO 行；需求记录、收货、发票只**引用**，不回写 |
| R2 | **预留迁移锚点** | `sales_order_line.intercompany_deal_id`（可空）。将来若引入独立内部交易对象（E 范式，LN / 浪潮），各单据行挂同一锚，A→C/E 迁移不丢对齐 |
| R3 | **单一变更入口** | 数量 / 日期变更只允许在 ISO 上发起；接收方通过 `change_request`（已有对象）申请，不在收货单上改 |

范式对比（信息统一度）：**单据单 + 视图（A / SAP STO）> 单据对 + 协议对象（E / LN）> 单据对无协议对象（C / D365）**。A 是当前信息最统一的选项，配 R2 后可演进到 E。

#### 3.1.5 七个容易漏的点

| # | 遗漏点 | 后果 / 需要的字段 |
|---|---|---|
| 1 | **货权转移点**未定义 | 发货 / 收货 / 开票三选一；按「法人对」配置，不是单据字段。影响两法人库存账与收入确认时点 |
| 2 | **转移价来源**缺失 | `sourcing_rule` 只答「谁供」，不答「多少钱」；需 `transfer_price_policy`（成本价 / 成本加成 / 市场价 / 协商价），按法人对 × 物料类 |
| 3 | **内部发票另建表** | 禁止。发票按 `source_doc_type ∈ {sales_order, purchase_order, intercompany}` 复用同一对象 |
| 4 | **内部退货 / 红冲** | 接收方退回 → 红冲 ISO + 反向收货；行上需 `direction ∈ {outbound, return}` |
| 5 | **链式内部交易**（A→B→C 转手） | 实物只动一次而单据成链；需 `movement_chain_id` 串起，否则结算追溯不到底层实物 |
| 6 | **集团合并抵消标识** | 内部交易若混入对外销售报表会虚增收入；需 `is_intercompany`（可由 `internal_mark` 派生）供报表排除与抵消 |
| 7 | **两侧权限隔离** | 同一张 ISO 被供需两法人访问；售价 / 毛利对接收方不可见，需组织级数据范围。C 模式天然隔离，这是 A 的隐性成本 |

### 3.2 需求 → sourcing → 载体：一条单向因果链

| 步 | 回答的问题 | 输入 | 输出 | 承载 |
|---|---|---|---|---|
| ① 需求 | 要什么、多少、何时、送到哪 | 物料 + 数量（或服务规格）+ 需求日期 + 发出组织 + 送达组织/地点 | 需求行 | `requisition` 行 |
| ② sourcing | **谁供** | 发出组织 + 送达组织/地点 + 物料策略组 | `source_org_id` / `source_location_id` / `supplier_party_id` + 价格来源 | `sourcing_rule_assignments` + `sourcing_rule_lines` |
| ③ 载体映射 | 用什么单据成交 | ②的输出 + 治理开关（是否需独立审批） | 执行单据 | 下表 |

> 本节覆盖**采购型需求**（`requisition`，行可为 `goods` 或 `service`）。事件型服务请求（`service_request`，行 = 请求项 + SLA）是另一个对象，两者共享 `demand_allocation` 与 `source_demand` 抽象但不合并，见 T-D13。服务的「买 / 做」也由 sourcing 判定（T-D17）。

**关键：`location + organization` 是选源（②）的输入，不是载体（③）的判据。** 规则只需要输出「来源是谁」（`source_id`），`source_type` 与载体都是下游派生量：

```
source_type（派生，不落库） = f(mode, 非空外键, party_relation.internal_mark)
载体                （派生） = f(来源法人 vs 需求法人, 来源库存组织 vs 需求库存组织, 审批策略, mode)
```

| 来源节点（由「哪个外键非空」派生） | 来源 vs 需求归属 | 载体 | 有无价 |
|---|---|---|---|
| `source_location_id` | 同法人同库存组织 | 库内移动（无单据） | 成本价 |
| `source_location_id` / `source_org_id` | 同法人异库存组织 | `transfer_order` | 无售价，有成本价 |
| `source_org_id` + 不需审批 | 跨法人 | ISO（A）+ 接收方收货 + 内部发票 | 有价 |
| `source_org_id` + 需审批 | 跨法人 | SO + PO 成对（C） | 有价 |
| `supplier_party_id`（`internal_mark=外部`） | 外部 | `purchase_order` | 有价 |
| `supplier_party_id`（`internal_mark=内部`） | 内部法人 | 同 `source_org_id` 分支 | 有价 |
| `mode=production`（来自 `sourcing_mode_policies`） | — | `work_order(production)` + 领料 | 成本 |
| 服务行 + `supplier_party_id` | 外部 | 服务采购订单（service PO） | 有价 |
| 服务行 + `source_org_id`（内部团队） | 内部 | `work_order(service)` | 按 SLA / 内部结算 |

> 本表是**派生结果**，不是判据：判据是「来源归属 + 需求归属 + 治理 + mode」四组事实。
>
> 服务行的内部承接分两种结算形态：**同法人** = `work_order(service)` + 内部成本分摊（无发票）；**跨法人** = `work_order(service)` + 内部发票 / 结算（有价）。与 goods 的 transfer / ISO 完全同构。

#### 3.2.1 审批开关不是 sourcing 的输出

- sourcing 只答「谁供」；「是否需要独立审批」属**治理配置**，按「法人对 / 组织对」维护，与 `sourcing_rule` 平级。
- 若把审批塞进 sourcing 规则，同一来源在不同治理下要复制规则行，规则表会持续膨胀。
- 计算顺序固定：先定 `source_type`，再查治理配置；审批只在 `internal_org` 且跨法人时有意义。

一句话：**「谁供」是主数据 / 规则问题；「怎么成交」是治理问题；「单据长什么样」是映射问题。三者不能混进一张规则表。**

#### 3.2.2 载体决策在行级，不在单据级

同一张需求单的不同行可以走不同载体，因此需求单会**分裂**成多张执行单据。必须有 `demand_allocation`（`demand_line_id → 执行单(id, type)` + 分配数量）来归集，否则需求无法闭合。该表同时服务采购、调拨、ISO、生产，不需要按载体建四张。

两条边界：

- `transfer_order` = 库存组织间调拨（同法人、无售价、有成本价）；`fulfillment_order` = 销售侧履约分组（面向外部客户）。二者语义不重叠，不得互换。
- `requisition` 若允许人工指定承接方，字段必须分开：`requested_source_org_id`（人工填写）与 `resolved_source_org_id`（sourcing 回填）。后者不得被人工直接改写，否则无法区分「人定的」与「规则算的」。

#### 3.2.3 闭合靠派生

需求行 `fulfilled_qty` 由执行单据派生（视图），不存第二份；否则需求行与执行单出现两处真相，与 §3.1.4 R1 冲突。

#### 3.2.4 字段职责（已核实的现有结构）

| 对象 | 关键字段 | 职责 | 现状 |
|---|---|---|---|
| `sourcing_mode_policies` | `item_group_id / item_id + org_id → mode` | 决定自制 / 外购（**做不做**） | 已建表 |
| `sourcing_rule_assignments` | `scope_type + scope_ref_id + dest_org_id + dest_location_id + specificity_rank` | 决定用哪条规则（**需求侧**） | 已建表 |
| `sourcing_rule_lines` | `source_org_id / source_location_id / supplier_party_id`（三选一）+ `rank` + `allocation_pct` | 给出候选来源（**来源侧**） | 已建表 |
| `sourcing_rule_lines` | `source_type`（四值，含 `production`） | 现为冗余列 | 与 `mode` 职责重叠（T15 / T-D16） |
| `work_order.source_demand_type` | `{sales_order_schedule, sales_order_line}` | 需求引用 | 缺 `requisition` |

#### 3.2.5 求值链（五步）

```
1) mode = sourcing_mode_policies(item/item_group, 需求 org)
2) rule = sourcing_rule_assignments 命中（scope_type + scope_ref_id + dest_org_id + dest_location_id）
3) src  = sourcing_rule_lines 按 rank/seq 取首个可用来源（blocked / 有效期 / allocation_pct）
          → source_org_id 或 source_location_id 或 supplier_party_id
4) 归属 = 从 orgs / locations / party_relation 读取「法人与库存组织」归属
5) 载体 = 载体派生表（§3.2 上表）
```

两条硬约束：

- `dest_org_id` 是**需求侧**，`source_org_id` 是**来源侧**，二者不可混填；
- 规则行**不得**写入法人 / 库存组织归属字段，归属只在第 4 步从主数据读取（避免第二份真相）。

## 4. 缺口清单

| # | 缺口 | 等级 | 影响 |
|---|---|---|---|
| T1 | 无采购型需求单（`requisition` + 行：`goods` 用 item + qty；`service` 用服务规格） | P0 | 需求无法审批、无法比价；内部需求也无处挂 sourcing，只能直接下单 |
| T2 | 无采购订单（`purchase_order` + 行 + 计划行） | P0 | 采购履约没有承载对象 |
| T3 | 无「PO 行 ↔ 需求行」分配表 | P0 | 合并采购后成本无法回聚到原需求 |
| T4 | 无收货单（GR） | P0 | 无三单匹配，无法确认到货与成本 |
| T5 | 无发票与三单匹配 | P1 | 付款依据缺失，无法核对价差 / 量差 |
| T6 | 供应商只有 `parties`，无准入 / 绩效 / 结算条件 | P1 | 无法做合格供应商与比价评分 |
| T7 | 采购任务无队列 / 池 | P1 | 采购共享无法集中派工（复用 SSC 的 `assignment_group`） |
| T8 | 无采购协议（合同 / 计划协议） | P2 | 框架采购、长期协议不可表达 |
| T9 | 委外工单无供应商字段 | P2 | 委外加工无法归属供应商 |
| T10 | 无内部交易标识（`is_intercompany` / 接收法人） | P0 | 内部交易混入对外销售报表会虚增收入，集团合并无法抵消 |
| T11 | 无转移价策略对象 | P0 | 跨法人有价内部交易无价格来源，内部发票开不出 |
| T12 | 无 `intercompany_deal_id` 锚点 | P1 | 将来升级为成对或独立内部交易对象时，数量与价格无法对齐 |
| T13 | 收货 / 发票不支持非 PO 来源 | P1 | A 路线（ISO 收货、内部发票）落不了地 |
| T14 | 无内部退货与链式交易标识 | P2 | 逆向红冲与 A→B→C 转手无法追溯 |
| T15 | `source_type` 与 `sourcing_mode_policies.mode` 职责重叠（`production` 两处都能表达） | P1 | 同一条规则可同时被「自制策略」与「外购策略」命中，求值结果二义 |
| T16 | 需求行无派生完成量（`fulfilled_qty`） | P1 | 需求无法闭合，只能从执行单据反推 |
| T17 | service 工单与服务需求之间缺「归属 + 契约」两层：① **归属层**——`work_order` 只有 `schedule_id`（仅接受 `schedule_kind='service'` 的销售计划行），没有可指向 SR 行 / 需求行的归属字段，工单无法回答「我为哪个服务承诺负责」；② **契约层**——R-ST-7 的完成回写目标与 `sla_milestone` 计时来源都绑在销售计划行，而 SR 自带响应 / 解决 SLA，口径不同 | P0 | `source_demand_type/id` 是**派生**关系，不应继续扩值域（与 `doc_flow_edges` 重复，构成第二份真相）；归属用字段、派生用边表，分工见 T-D19。契约层须先定「SR 的 SLA 与完成回写落点」 |
| T18 | `work_order.source_demand_type/id` 与 `doc_flow_edges` 表达力重叠：前者是单值多态外键，后者用 `source_bo/source_id/source_item → target_bo/target_id/target_item` 已能完整表达，且支持多源合并与分批消耗（[doc_flow_schema.py L46-L70](file:///d:/filework/excel-to-diagram/meta/core/doc_flow_schema.py#L46-L70)） | P1 | 同一事实存两处 = 第二份真相（与 T-D15 原则冲突）；且单值外键无法表达「一张工单由多张 SR 合并产生」。收敛需迁移存量 production 工单并保留兼容读取 |

### 4.1 现状核对：SO 下游是否已采纳「归属 vs 派生」

| 下游 | 连接方式 | 归类 | 符合 T-D19 |
|---|---|---|---|
| `fulfillment_order.order_id`（required） | → `sales_order` | 归属 | 是 |
| `sales_order_schedule.sales_order_id` / `sales_order_line_id`（required） | → SO / SO 行 | 归属 | 是 |
| `shipment.order_id`（required） | → `sales_order` | 归属 | 是 |
| `shipment_line.schedule_id`（required） | → 服务 / 计划行 | 归属 | 是 |
| `shipment_line.order_line_id`（required，注释「**冗余**：由 schedule_id 反查…不一致拒绝」） | → SO 行 | 反规范化冗余 | 否 |
| `shipment_line.item_id`（required，注释「**冗余**：由订单行带出」） | → item | 反规范化冗余 | 否 |
| `shipment_line.qty` | 本单实发量（与边表 `quantity` 同值、不同视角） | 单据事实，与边表重复 | 否 |
| `work_order.schedule_id`（required） | → 计划行 | 归属 | 是 |
| `work_order.source_demand_type/id` | 多态派生 | 派生做成了外键 | 否（T18） |
| 全部下游 | 无 app 声明 `doc_flow: enabled` | 边表未启用 | — |

结论：**归属那一半已采纳，派生那一半没有采纳**。头级归属字段全部正确；行级追溯仍走「冗余外键 + 数量 + 一致性校验」的 SAP 式做法（`shipment_line` 注释本身写明是冗余，靠「不一致拒绝」保真），`doc_flow_edges` 零使用。SAP 同样是 VBFA 边表与单据行 `VGBEL/VGPOS` 并存，因此这不算错，但**不能据此声称已统一**。

含义：T-D19 先只约束**新建对象**（`requisition` / `service_request` / PO / 收货 / 发票）；存量 `shipment_line` / `work_order` 迁移前，两套并存，需在文档中标注「冗余字段 = 缓存，真源另定」。

### 4.2 评估任务：存量迁移到边表

| 项 | 内容 |
|---|---|
| 目标 | 判定 `shipment_line.order_line_id` / `item_id`、`work_order.source_demand_type/id` 是迁移到 `doc_flow_edges`，还是保留为缓存；给出「迁移 / 部分迁移 / 不迁移」结论 |
| 范围 | `shipment_line`（2 个冗余字段 + `qty`）、`work_order`（多态外键 2 字段）；`fulfillment_order` / `shipment` / `sales_order_schedule` 的归属字段只核对、不动 |
| 前置条件 | ① 至少一个 app 声明 `doc_flow: enabled`；② derive 引擎接线并有对应 `doc_flow_rule`；③ 历史边回填脚本；④ 明确「无数量边 = `quantity=0`」口径 |
| 步骤 | 1) 盘点每个冗余字段的读取点与一致性校验点；2) 归类归属（留字段）vs 派生（入边表）；3) 设计双写过渡（边表生成后字段转只读）；4) 回填历史边 + 对账；5) 查询切读边表；6) 停写字段；7) 回归 |
| 验收判据 | `v_doc_flow_consumed_qty` 汇总 = 单据 `qty` 汇总且零差异；列表 / 详情页无性能回归；红冲（`status='reversed'`）可逆；既有测试全绿 |
| 风险 | 边表 append-only，历史修正只能红冲不能改；`quantity` 非空，需约定 0 值语义；查询多一跳；`shipment_line` 现有的「不一致拒绝」校验要转为对账任务 |

产出：一页结论（迁移 / 部分迁移 / 不迁移 + 理由 + 工作量分级）。

### 4.3 头部产品对比：归属与派生怎么落地

| 产品 | 单据行直接引用 | 独立流边表 | 边表是否唯一真源 | 消耗 / 分批 / 冲销 |
|---|---|---|---|---|
| SAP S/4HANA | 交货 / 发票行 `VGBEL/VGPOS`；PO 行 `EBELN/EBELP` | `VBFA`（`VBELV/POSNV→VBELN/POSNN`，`RFMNG`）；PO 另用 `EKBE` | 否（可用量看单据与行数量；`EKBE` 对 PO 匹配接近真源） | `RFMNG` / `EKBE-MENGE`；分批 = 一源多后继行；冲销 = 反向凭证 |
| Oracle SCM | 收货 / 发货行 `SourceDocumentCode + DocumentNumber + Line` | 未找到通用流表官方依据，仅财务编排有 Document Flow Assignments | 否，靠引用 + Life Cycle 汇总 | 交易行数量；退货反向引用 |
| D365 SCM | `InventTrans` → `InventTransOrigin`（ReferenceCategory + Id） | 无流边表，`InventTrans` 即库存交易账 | 是（库存数量层面） | 交易数量 + 状态；冲销 = 反向交易 |
| NetSuite | 行级 `createdFrom` | 无通用边表，`Applied To` 是金额应用关系 | `createdFrom` 是关系真源，行上 `qtyfulfilled/billed` 是缓存 | 履行 / 开票行数量；分批 = 多履行行；冲销 = Credit Memo / RMA |
| Infor LN | 行级 `Order Origin` / `originating` / `related order` | 未找到通用流表官方依据 | 否，以 order 引用 + 仓单行为准 | 仓单 / 装运行数量；退货反向引用 |
| Odoo | `stock.move.origin`（字符串）+ picking 关联 | `stock_move_move_rel`（`move_orig_ids` / `move_dest_ids`） | 边表被业务逻辑读取（取消传播、就绪判断），但数量在 move 本身 | `quantity`；分批 = 多 move；冲销 = 反向 move |

结论：

1. 六家**没有一家是二选一**，全部「直接引用 + 派生关系」并存；SAP 最彻底（`VBFA` 与 `EKBE` 两套）。
2. 边表**几乎都不是唯一真源**：可用量与状态看单据行或交易行，边表多做导航审计（`VBFA`）或链式控制（Odoo）；唯一例外是 `EKBE` 对 PO 的三单匹配近乎真源。
3. 消耗量要么在边上（`RFMNG` / `EKBE-MENGE`），要么在交易行上（`InventTrans` / `stock.move`）；分批 = 一源多后继行，冲销 = 反向凭证或负数行，**均不改原始行**。
4. 「归属 vs 派生」在 SAP / NetSuite / LN / Odoo 是明确分离的；D365 以 Origin 为归属、Marking 为成本匹配；Oracle 只有引用 + Life Cycle 视图，分层最弱。
5. 对我们的含义：边表做**关系真源**（含消耗量与冲销），行上冗余引用降级为**只读缓存**——这是 T-D19 的补充条款，也让 §4.2 的迁移不必删字段、只需降级。

来源可靠性：SAP 官方帮助页当前检索不可访问，`VBFA` / `EKBE` 字段依据第三方表字典（leanx.eu、se80.co.uk）；Oracle EBS 的通用 Document Flow 表未找到官方依据。

### 4.4 Oracle Fusion 深挖（细化 §4.3 的 Oracle 一行）

| 机制 | 官方字段 | 落库位置 |
|---|---|---|
| 跨模块统一流表 | **不存在**；`FOS_DOC_FLOW_ASSIGNMENT` 仅是财务编排（源单据 → 财务流路由） | FOS 表 |
| 请购 → PO | `PO_DISTRIBUTIONS_ALL.REQ_DISTRIBUTION_ID` → `POR_REQ_DISTRIBUTIONS_ALL.DISTRIBUTION_ID` | 采购分配表 |
| 询价 / 协议 → PO | `PO_LINES_ALL.FROM_HEADER_ID` / `FROM_LINE_ID`（**不指请购**） | PO 行 |
| 收货 → PO | `RCV_SHIPMENT_LINES.PO_HEADER_ID / PO_LINE_ID / PO_LINE_LOCATION_ID / PO_DISTRIBUTION_ID` | 收货行 |
| 收货流水 | `RCV_TRANSACTIONS.TRANSACTION_TYPE / QUANTITY / PARENT_TRANSACTION_ID / SOURCE_DOCUMENT_CODE`，只增不改，净量入 `RCV_SUPPLY` | 收货事务表 |
| 数量缓存 | `PO_LINE_LOCATIONS_ALL.QUANTITY_RECEIVED / ACCEPTED / BILLED`；`DOO_LINES_ALL.FULFILLED_QTY / SHIPPED_QTY` | 行 / 排程 |
| AP 匹配 | `AP_INVOICE_LINES_ALL.PO_DISTRIBUTION_ID / RCV_TRANSACTION_ID / MATCH_TYPE` | AP 行 |
| SO → 履约 | `DOO_LINES_ALL.SOURCE_ORDER_ID / SOURCE_ORDER_SYSTEM / SOURCE_LINE_ID / SOURCE_SCHEDULE_ID` + `TRANSFORM_FROM_LINE_ID` | DOO 行 |

结论：

1. **没有跨模块统一流表**；「Document Flow」在 Fusion 只属 SFO 财务编排，不是销售或采购单据链。
2. 来源字段**按模块各一套且语义不同**：`PO_LINES_ALL.FROM_*` 指询价 / 协议，**不指请购**；请购派生落在分配级的 `REQ_DISTRIBUTION_ID`。
3. `SOURCE_TRANSACTION_ID` 只存在于导入接口表 `DOO_ORDER_LINES_ALL_INT`；主表用文本型 `SOURCE_ORDER_ID / SYSTEM`，OM → AR 发票无强 FK。
4. 数量是「**缓存净量 + 只增流水**」双轨：`QUANTITY_RECEIVED` 是缓存，`RCV_TRANSACTIONS` 是不改写的流水，退货为反向事务、缓存按净额回算。
5. 归属与派生部分分离：归属 `ORG_ID` / `PRC_BU_ID` / `OWNER_ID`，派生 `SOURCE_*` / `FROM_*` / `REQ_DISTRIBUTION_ID`。
6. 相对 EBS 基本沿用同一套表结构，仅新增 DOO 编排层与 Life Cycle UI，**未收敛为单一模型**。

对我们的映射：`RCV_TRANSACTIONS` ≈ `doc_flow_edges`（只增、`TRANSACTION_TYPE` ≈ `quantity_sign`、`PARENT_TRANSACTION_ID` ≈ 红冲指向原边）；`QUANTITY_RECEIVED` ≈ 只读缓存列。这是 T-D19 补充条款最直接的行业先例。

## 5. 决策建议

| # | 决策 | 理由 |
|---|---|---|
| T-D1 | 采购单据独立于 `work_order` | 生命周期不同：外部交易 + 三单匹配 + 付款，混进工单会打乱 11 态 |
| T-D2 | 审批只做在需求层；订单层仅超权限变更再审 | 先批需求再下单是行业一致做法，双重审批只会拖慢 |
| T-D3 | 合并采购必须用分配表，禁止在 PO 行上放单个 `project_task_id` | 一张 PO 行可服务多个需求行，单字段必丢归属 |
| T-D4 | 供应商走 `parties` + 角色字段，不新建 supplier 表 | 避免两套主体数据；准入/绩效作为角色属性 |
| T-D5 | 采购任务复用 `tasks` + `assignment_group`，不建「采购任务」对象 | 与金蝶「共享任务」同构，已有 11 态与认领机制 |
| T-D6 | 委外走 `work_order(production)` + 供应商；PO 只管物料与服务 | 委外有工序与报工，采购没有 |
| T-D7 | 需求三源统一为 `source_demand`（新增 `inventory_replenishment`） | 与 `work_order.source_demand_type` 保持同一结构 |
| T-D8 | 内部交易载体为 **A（`sales_order` 内部单据类型）+ D（独立 `transfer_order`）**；不采用 SAP 的 PO+STO 形态，`purchase_order` 不背 `from_org / to_org` | 9 家主流走 C，其动机是两侧有独立销售 / 采购模块；我们单系统、`party_internal` 与 `internal_mark` 已具备内部主体表达，A 前置条件齐备且零新对象；SAP 的供货方是 plant，不是有 sales_org 的法人 |
| T-D9 | 切换判据为三问：是否跨法人 / 是否需独立收货与库存估值 / 是否需独立审批与三单匹配；**不是「是否独立审批」一条** | 跨法人恒需各自收货凭证（法定账），与审批无关；只问审批会漏掉法定账需求 |
| T-D10 | 跨法人即使不审批，接收侧也必须有**轻量需求记录**（自动生成、不可人工编辑、无三单匹配） | 否则接收方入库与应付无单据来源；Oracle 的 Internal Requisition 即此角色 |
| T-D11 | 协议事实唯一载体 + 预留 `intercompany_deal_id` 锚点；变更只从 ISO 发起（复用 `change_request`） | 避免 C 式双份事实；锚点让 A 可低成本演进为独立内部交易对象（LN / 浪潮 范式） |
| T-D12 | 发票与收货按 `source_doc_type` 复用同一对象，禁止建内部专用发票表 | 行业里结算 / 发票独立成对象，但从不按「内部 / 外部」分表 |
| T-D13 | 需求层分两个对象：**`requisition`（采购型，行可为 `goods` 或 `service` 采购项）** 与 **`service_request`（事件型，行 = 请求项 + SLA）**；两者共享 `source_demand` 抽象与 `demand_allocation` 归集表，不合并成一张表 | 字段集**可以同构**：`qty`、`need_date`、`deliver_to_*`、`provider_org` 两边都可有，靠条件必填（goods 必填 / 纯服务可空）区分，不以「有 / 无」划界。但四组结构不同：① **状态机**（受理→派工→验收 / 不予解决 vs 审批→寻源→转单 / 取消）；② **持有者与权限域**（服务台承接方 vs 采购受理方）；③ **终态语义**（「不予解决」是 SR 的正常终态，requisition 只能「取消」，合并后同一状态字段承载两套口径）；④ **产生频率**（IT 报修按日级、请购按周级，合并会污染查询、待办与报表）。分界仍是**事件 vs 承诺**，不是「实物 vs 服务」也不是「采购 vs 自供」；载体一律由 sourcing 决定（T-D17 / T-D18）。本平台新建一个对象的成本是一个 yaml + 一个迁移，合并省下的几乎是零，而代价是上述四项，故不合并实体；要统一的是字段词表、行结构、`source_demand` / `demand_allocation` 桥和策略表达（审批策略、寻源策略、承接方指定） |
| T-D13a | `requisition` **禁止**单据类型取 `purchase / internal` 这类载体方向值——外部 / 内部由 sourcing 结果派生，与 `source_type` 同理；但**单据类型本身作为编号 / 审批 / 打印 / 权限的治理挂载点必须存在**（见 T-D20），二者是同名字段的不同用途，不可互相替代 | 提前写死方向等于在规则结果出来之前先判一次载体，必然与 sourcing 冲突；而把治理语义与载体方向合并进一个字段，会让同一张单据无法既走采购又被复用为内部需求 |
| T-D14 | 分配表统一为 `demand_allocation`（需求行 → 任意执行单行），不按载体分建 | 合并采购、调拨、ISO、生产是同一类「需求分裂后归集」问题 |
| T-D15 | `sourcing_rule` 只输出「来源是谁」（三选一外键），**不输出 `source_type`、不决定载体**；`source_type` 降级为派生视图字段，载体由「来源归属 + 需求归属 + 治理 + mode」派生 | 同一来源在不同法人 / 库存组织关系下对应不同载体，把它写成规则输出会让一个来源被错误地固化到一种单据；且法人归属若写进规则行会造成第二份真相 |
| T-D16 | `production` 归属 `sourcing_mode_policies.mode`，`sourcing_rule_lines` 不再承担「自制」语义 | 自制是「做不做」的决策（mode），不是「谁供」的候选；两处都能表达会产生求值二义 |
| T-D17 | 「服务的买 vs 做」同样由 sourcing 判定：`supplier` → 服务采购订单；`internal_org`（内部团队）→ `work_order(service)` | 服务既可外购也可自供，若按「服务 / 实物」切对象，则同一笔服务需求会在两个对象里各存一份；载体一律由 sourcing 出口决定才与 goods 侧同构 |
| T-D18 | 「轻路径 / 重路径」：同法人自供且无需结算 → 需求入口直接生成执行单据（领用出库 / `work_order(service)`），不经 `requisition`；需寻源、跨法人结算或外部采购 → 建 `requisition` 再走 sourcing | 让所有供应都进 `requisition` 会把 IT 报修这类琐事变成伪采购单；行业（D365 / Maximo）同样是 SR 直连工单，只有真采购才走 PR |
| T-D19 | 单据之间的上游关系只保留两类：**归属（ownership）**用字段——一对一或 N:1、参与自身不变量（如 `schedule_id` 决定 SLA 里程碑、采购行决定收货对象）；**派生（derivation）**用 `doc_flow_edges`——可多源、可分次、带消耗量与红冲。不再保留**可写**的 `source_demand_type/id` 这类派生型多态外键（允许保留只读缓存列） | 归属回答「我是谁的组成部分」，派生回答「我从谁产生」。前者参与不变量校验，必须是列约束（DDL 能强制非空）；后者本质是流水账，必须是边表，才能表达 SR N:1 合并与分批消耗。把流水做成外键就会与 `doc_flow_edges` 形成第二份真相，违背 T-D15 同源原则。业界六家（SAP / Oracle / D365 / NetSuite / LN / Odoo）均保留行上的派生引用，故允许保留**只读缓存列**（由边表回写、不得单独作为关系真源、不得单独参与业务判断），但不得存在可写的第二份真源；缓存值域允许扩（`project_task` / `service_request` / `requisition_line` / `inventory_replenishment`），但只由边表回写 |
| T-D20 | **单据类型规范**：所有业务单据头必须声明单据类型（`document_type_id` → `type_definitions` 的 `scope_bo=<本 BO>` + `level='header'` 行）；创建时必填、离开草稿后不可改；类型只承载编号 / 审批 / 打印 / 权限等治理语义。`sales_order` 原 `order_type_id` 为历史命名，已由 v171 迁移统一为 `document_type_id` | 治理语义（编号规则、审批策略、打印模板、权限域）必须有稳定挂载点，否则每加一张单据都要另造一套配置；同时它**不承担**载体方向（T-D13a）也**不承担**行级分类（`line_type`），三者层级不同不可替代。Oracle `DOCUMENT_TYPE_CODE` / SAP `BSART` 同为头级单据类型，都不编码内外方向 |

## 6. 开放问题

- Q1 纯补货需求是否允许无项目 / 无销售来源？建议允许——按 T-D19 不落 `source_demand_type`，以「在 `doc_flow_edges` 中无入边」表达纯补货。
- Q2 多币种与税：PO 行是否需要独立的币种 / 税率字段，还是走价格条件？
- Q3 三单匹配的容差策略（价差 / 量差）首版做到什么粒度？
- Q4 采购共享是否跨法人集中下单（影响 PO 的 `buyer_org_id` 与审批链）？
- Q5 服务类采购（无收货）如何判定完成：验收单还是服务确认？
- Q6 项目驱动采购时，`project_task` 是挂在 PR 行还是 PO 分配行？
- Q7 货权转移点默认取哪个（发货 / 收货 / 开票）？它决定两法人的库存账与收入确认时点。
- Q8 转移价策略按「法人对 + 物料类」还是「法人对 + 物料」配置？粒度越细维护成本越高。
- Q9 链式内部交易（A→B→C 转手、实物只动一次）首版是否支持？不支持则需在规则上明确禁止该路径。

## 7. 证据清单

- `meta/schemas/sourcing_rule.yaml`、`sourcing_rule_line.yaml`、`sourcing_rule_assignment.yaml`（来源路由；`source_type` / `supplier_party_id`）
- `meta/schemas/work_order_component.yaml`（工单物料需求）
- `meta/core/task_schema.py`（`doc_ref` / `line_refs` / `waiting_approval`）
- `meta/schemas/work_order.yaml`（`source_demand_type` 现有枚举）
- `docs/specs/spec-project-type-object-model-research-2026-10-31.md`（履约三链与「桥只两键」）
- `docs/specs/spec-shared-service-center-object-model-2026-10-31.md`（任务池 / 队列 / 共享任务）

### 外部样本（内部交易载体）

- Infor LN Intercompany Trade Order：<https://docs.infor.com/ln/10.5/en-us/lnolh/help/tc/glossary/glossary.html>
- Infor M3 Internal Invoicing：<https://docs.infor.com/m3udi/16.x/en-us/m3beud/finaccths/hjy1567539152080.html>
- IFS 跨地点移库：<https://docs.ifs.com/ifsclouddocs/24r1/MaintainInventory/AboutMovingPartsInMaintainInvent.htm>
- JDE ST/OT 转储单：<https://docs.oracle.com/en/applications/jd-edwards/supply-chain-manufacturing/9.2/eoaso/understanding-interbranch-and-intercompany-orders.html>
- Sage X3 Inter-companies：<https://online-help.sagex3.com/erp/12/en-us/Content/FCT/FUNBCH.htm>
- 金蝶组织间结算：<https://help.open.kingdee.com/dokuwiki/doku.php?id=%E7%BB%84%E7%BB%87%E9%97%B4%E7%BB%93%E7%AE%97>
- Workday Intercompany：<https://doc.workday.com/workday-education/en-us/course-manuals/financial-accounting-for-administrators/intercompany.html>

### 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-31 | 初版研究稿 v1.0（仅取证与设计建议，未改代码、未提交） |
| 2026-10-31 | v1.1：新增 §3.1「内部交易载体与信息统一锚点」（行业五路线分布、A+D 选择依据、三问判据、五组合矩阵、信息统一三规则、七个遗漏点）；缺口补 T10-T14；决策补 T-D8~T-D12；开放问题补 Q7-Q9；证据补外部样本。修正 v1.0 两处口径：「是否独立审批」不等于「是否跨法人」（法定账恒需收货凭证）；`transfer_order` 非「无价」而是「无售价、有成本价」 |
| 2026-10-31 | v1.2：新增 §3.2「需求 → sourcing → 载体单向因果链」（三步输入输出、`source_type`→载体映射、审批开关属治理配置而非 sourcing 输出、行级分裂与 `demand_allocation`、枚举缺口）；T1 改为 `requisition`（PR / IR 合一）；缺口补 T15-T16；决策补 T-D13~T-D15 |
| 2026-10-31 | v1.3：§3.2 重写为「规则只输出来源、`source_type` 与载体均为派生量」；新增 §3.2.4 字段职责表与 §3.2.5 求值链（`assignment` 是需求侧、`line` 是来源侧、归属从主数据读取）；T15 改写为「`source_type` 与 `mode` 职责重叠」（原「缺 `production`」表述有误，枚举已含 `production`）；决策补 T-D16 |
| 2026-10-31 | v1.4：T-D13 拆清需求层两个对象（`requisition` 数量型 / `service_request` 事件型，共享 `demand_allocation`）；新增 T-D13a 撤销 `requisition_type ∈ {purchase, internal}`（外部 / 内部同属 sourcing 派生结果）；T1 同步改写；§3.2 补适用范围说明 |
| 2026-10-31 | v1.5：确认 `requisition` 行支持 `service`（采购服务），派生表补「服务行 → service PO / `work_order(service)`」两行；T-D13 改写为「分界是采购 vs 自供，不是实物 vs 服务」；新增 T-D17（服务的买 / 做也由 sourcing 判定）；T1 改为 `goods` / `service` 两种行 |
| 2026-10-31 | v1.6：修正 v1.5 的服务边界表述——`requisition` 的 service 行**可以**命中内部组织并落到 `work_order(service)`（同法人无发票 / 跨法人内部发票）；SR 与 requisition 的分界改为「事件 vs 承诺」，不再用「采购 vs 自供」；派生表补服务内部承接的两种结算形态；新增 T-D18（轻路径 / 重路径） |
| 2026-10-31 | v1.7：补强 T-D13 的对象边界口径——`service_request` 与 `requisition` 的字段集可以同构（`qty` / `need_date` / `deliver_to_*` / `provider_org` 两边都可有，靠条件必填区分），不合并实体的判据改为四组结构差异（状态机 / 持有者与权限域 / 终态语义 / 产生频率）+ 平台建对象成本极低；新增 T17（`work_order` service 分支缺少 SR / 需求行挂载点，R-ST-0 需改为二选一必填） |
| 2026-10-31 | v1.8：T17 改写为两层——关联层（`schedule_id` / `source_demand_type` 均未覆盖 service 需求，`doc_flow_edges` 基建已存在但无 app 声明启用）+ 契约层（完成回写与 SLA 计时绑在 `sales_order_schedule`）；明确 `doc_flow_edges`（行级数量消耗流水）与单据级多态外键（强引用）用途不同、并存不互斥，后者沿用 `work_order(production)` 范式 |
| 2026-10-31 | v1.9：新增 T-D19（上游关系只分**归属**与**派生**：归属用字段、派生用 `doc_flow_edges`）与 T18（`work_order.source_demand_type/id` 与边表表达力重叠、属第二份真相，待收敛）；T17 改为「归属层 + 契约层」，撤销「扩 `source_demand_type` 值域」的修法；Q1 同步改为以「无边」表达纯补货 |
| 2026-10-31 | v1.10：新增 §4.1「SO 下游现状核对」——头级归属字段（`fulfillment_order.order_id` / `shipment.order_id` / `work_order.schedule_id` 等）符合 T-D19，行级追溯（`shipment_line.order_line_id` / `item_id` 冗余字段、`qty` 与边表 `quantity` 重复、`work_order.source_demand_type` 多态外键）未采纳，`doc_flow_edges` 零使用；T-D19 先约束新建对象，存量迁移前两套并存 |
| 2026-10-31 | v1.11：新增 §4.2「评估任务：存量迁移到边表」——范围（`shipment_line` 冗余字段 / `work_order` 多态外键）、前置（启用 `doc_flow` + 回填脚本 + 无边数量口径）、7 步过渡、验收判据与风险 |
| 2026-10-31 | v1.12：新增 §4.3「头部产品对比」——SAP `VBFA`+`EKBE`、Oracle 引用 + Life Cycle、D365 `InventTrans`、NetSuite `createdFrom`、LN `Order Origin`、Odoo `move_orig_ids`；六家均为「直接引用 + 派生关系」并存，边表几乎都不是唯一真源（`EKBE` 例外）；据此给 T-D19 加补充条款：允许派生引用保留为**只读缓存列**，禁止可写的第二份真源 |
| 2026-10-31 | v1.13：新增 §4.4「Oracle Fusion 深挖」——无跨模块统一流表（`FOS_DOC_FLOW_ASSIGNMENT` 仅财务编排）；来源字段按模块各一套（`PO_DISTRIBUTIONS_ALL.REQ_DISTRIBUTION_ID` 指请购、`PO_LINES_ALL.FROM_*` 指询价 / 协议）；数量为「缓存净量 + `RCV_TRANSACTIONS` 只增流水」双轨，与 `doc_flow_edges` + 只读缓存同构 |
| 2026-11-01 | v1.14：新增 T-D20「单据类型规范」——所有业务单据头必须有 `document_type_id`（`type_definitions` 的 header 行），只承载治理语义；T-D13a 收窄为「禁止单据类型编码 `purchase` / `internal` 载体方向」，不再等同于「不设单据类型」；`requisition` 已按此落地（`meta/schemas/requisition.yaml` + 迁移 v169） |
