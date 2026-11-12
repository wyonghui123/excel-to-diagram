# 研究稿：ETO（按单设计）头部产品研究 — Oracle 专题

- 文档版本：v0.1
- 日期：2026-11-03
- 状态：研究稿（仅研究，**尚未实施**）
- 关联文档：
  - `spec-project-g4-engineering-bom-2026-11-03.md`（G4 工程 BOM / ECM，v1.4）
  - `spec-routing-process-manufacturing-benchmark-2026-11-01.md`（P5 工艺路线研究稿）
  - `spec-oracle-fusion-project-object-model-2026-10-31.md`（Oracle 项目对象模型研究）
- 研究范围：Oracle Fusion Cloud SCM / ERP 25C + Oracle EBS 12.2；横向仅做定位，不展开 SAP / IFS 细节。

---

## 0. 结论摘要（先看这里）

1. **Oracle 没有一个叫 ETO 的模块。** Oracle 的 ETO 是组合能力：Product Development / PLM（工程结构与变更）+ Manufacturing（工作定义 / 工单）+ Project-Driven Supply Chain（项目化供应链）+ Project Financials（项目成本）+ Order Management / CPQ（订单与配置）。Oracle 官方把它表述为 `make-to-project`、`按订单设计`、`project-driven supply chain`，而不是独立的 ETO 产品。
2. **Oracle 把「产品定义」和「项目归属」分开。** BOM、工艺路线、工作定义都是**物料级**对象；项目归属通过**订单 / 工单 / 库存 / 采购 / 成本的 project reference**表达，不给 BOM 加 `project_id`。
3. **真正定制的 BOM 有两条 Oracle 路线：**
   - **一项目一物料**：为项目 / 订单新建 item，BOM 和工艺挂在该 item 上；这是 ETO 最常用的做法。
   - **一物料多单元**：一个 model item + `Model / Unit Number` 生效控制，结构按 unit（项目 / 订单 / 序列号）变化；Oracle 产品文档明确说 model-effective structure 通常与 project manufacturing 关联。
4. **工程 BOM 与制造 BOM：EBS 是显式两套，Fusion 是一套结构 + 变更单 / 版本 + 发布。** EBS 有 Engineering Item / Engineering BOM，ECO 可把工程 BOM 转移或复制到制造 BOM；Fusion 用 item structure + change order + revision / effectivity，工作定义随结构变更同步。平台当前 `usage=engineering / production` + ECM 更接近 EBS，方向正确。
5. **变更单是产品级的，不是项目级的。** Oracle 的 change order 管 item / structure / revision / effectivity；项目影响通过 where-used、受影响对象和项目引用去查询，而不是给每个项目建一套变更单。
6. **项目执行靠 project reference，不靠项目专用主数据。** Oracle 制造工单上有 Project Number、Task Number、Expenditure Item Date、Expenditure Type、Expenditure Organization 五个字段；项目库存、项目采购、项目维修、项目成本都围绕这条引用展开。
7. **成本唯一事实源是 Expenditure Item，归集粒度是 Task。** 项目成本由人工、采购、工时、制造等业务事件生成支出项，再经 burden（间接费用）、capitalization（资本化）、billing（开票）加工；不是每个模块各算一套成本。
8. **ETO 与 CTO 必须分开。** CTO 是 model + option class + configured item，配置由销售订单驱动；ETO 是每单重新设计，没有预定义选项。Oracle 同一工厂支持 mixed-mode，但 **contract manufacturing 不支持 configured item**，这是一条硬边界。
9. **对平台 G15 的直接结论：** G4 D5（不建项目 BOM 快照）应保持；G4 A.5 的第 1 项应改写为「项目物料 / 项目配置 + 复用标准结构」，而不是新增项目专用 BOM 表。真正的缺口在**库存的项目维度**和**项目成本的统一口径**，不在 BOM 语义。
10. **G15 最小闭环：** 项目物料 + 工程结构 + ECM 发布 + 项目工单（project_id / task）+ 项目采购 / 库存引用 + 派生项目成本。报价 / CPQ、CAD / PDM、项目开票、完整项目会计都不做。

---

## 1. 研究方法与证据强度

| 证据 | 来源 | 强度 | 用途 |
|---|---|---|---|
| Oracle Fusion SCM `Using Manufacturing` 25C（G34542-01） | `docs.oracle.com` 官方 PDF | 强 | 工作定义、工单、ATO / 配置项、项目工单字段 |
| Oracle Fusion SCM `Using Product Development` 25C（G34546-03） | `docs.oracle.com` 官方 PDF | 强 | 变更单类型、受影响对象、红线、版本与生效日 |
| Oracle Fusion SCM `Implementing Product Management` 25C（G34519-01） | `docs.oracle.com` 官方 PDF | 强 | item structure、effectivity 控制、model / unit |
| Oracle Fusion SCM `Using Supply Chain Cost Management` 25C（G34557-02） | `docs.oracle.com` 官方 PDF | 强 | 项目驱动供应链成本、项目 / 任务估值、支出 |
| Oracle `Project-Driven Supply Chain in the Cloud` 方案简介（2020） | `oracle.com` 官方 PDF | 强 | PDSC 能力边界与价值 |
| Oracle `Fusion Cloud Manufacturing` 数据表（v4.0，2024） | `oracle.com` 官方 PDF | 强 | MTS / MTO / CTO / make-to-project / 合同制造 / 外协 |
| Oracle EBS 12.2 `Project Manufacturing Implementation Guide`（E48955-01） | `docs.oracle.com` 官方 PDF | 强 | project reference、project locator、project MRP |
| Oracle EBS 12.2 `Project Manufacturing User's Guide`（E48956-01） | `docs.oracle.com` 官方 PDF | 强 | 项目工单、跨项目发料、成本组 |
| Oracle EBS 12.2 `Engineering User's Guide`（E48939-02） | `docs.oracle.com` 官方 PDF | 强 | ECO、审批、版本、日期 / 单元生效、批量变更 |
| Oracle EBS 12.2 `Bills of Material User's Guide`（E48954-01） | `docs.oracle.com` 官方 PDF | 强 | 工程 / 制造 BOM、model / option class、配置 BOM |
| 平台 schema / 迁移 / ECM 实现 | 本仓库代码 | 强 | 现状盘点与差距判断 |
| ERP Research `Oracle Cloud ERP for Manufacturing (2026)` | 第三方评测 | 中 / 低 | 横向定位（长周期 ETO 的深度判断） |
| OAUG 2008 `Implementing Oracle Discrete Manufacturing in an ETO Environment` | 行业论文 | 中 / 低 | ETO 需要增强的历史证据 |
| SAP / IFS 资料 | 二手页面 | 低 | 仅做横向定位，不作为设计依据 |

> 说明：本稿的核心设计结论只依赖 Oracle 官方文档与平台代码；横向对比部分明确标注为二手证据，不进入 G15 设计依据。

---

## 2. ETO 的定义与边界

### 2.1 定义

ETO（Engineer-to-Order，按单设计）是**接到客户订单后才开始设计**的制造模式：客户规格不完整、工程活动进入交付周期关键路径、BOM / 工艺路线 / 物料需要新建或大幅修改、每个项目有独立的合同与成本归集。

ETO 的三个硬特征：

1. **设计在订单之后**：报价阶段只能基于相似产品估算，不能直接复用标准 BOM。
2. **工程是关键路径**：设计、评审、冻结、变更直接决定交期。
3. **项目即核算单元**：材料、人工、外协、制造费用必须归到项目 / 任务。

### 2.2 ETO 与相邻模式的边界

| 模式 | 客户介入点 | 产品定义 | BOM / 工艺 | 典型对象 | Oracle 对应 |
|---|---|---|---|---|---|
| MTS 按库存生产 | 无 | 标准产品 | 预先定义、复用 | 标准 item + BOM | Make-to-Stock |
| MTO 按订单生产 | 下单时 | 标准产品，可能有小改 | 基本复用 | 标准 item + 销售订单 | Make-to-Order |
| ATO 按订单装配 | 下单时选配置 | 标准模型 + 选项 | 模型 BOM + 配置 BOM | model / option class / configured item | Assemble-to-Order |
| CTO 按订单配置 | 下单时配置 | 标准模型 + 可配置特征 | 模型 BOM + 配置规则 | configured item + 配置工作定义 | Configure-to-Order |
| **ETO 按单设计** | **下单后才设计** | **每单新建或大改** | **工程 BOM → 制造 BOM** | **项目物料 / 项目配置 / 项目工单** | **Make-to-Project + PLM + PDSC** |

关键判断：

- ATO / CTO 的复用对象是**模型与选项**；ETO 的复用对象是**工程师的经验与相似件**，不是预定义配置。
- 平台已有 `configuration` / `configuration_component` / `configuration_value`，可以做 CTO；**不要**把它扩成 ETO 设计器。
- ETO 不需要“配置器”，需要“工程变更 + 项目物料 + 项目执行引用”。

### 2.3 Oracle 的用词

- Oracle Manufacturing 页面把生产方式列为：按库存生产、按订单生产、按订单配置、**按订单设计**、按项目生产。
- Oracle 数据表列出的执行模式是：make-to-stock、make-to-order、configure-to-order、**make-to-project**、contract manufacturing、outside processing。
- Oracle 的 ETO 落地词是 **Project-Driven Supply Chain（PDSC）** 与 **make-to-project**；`ETO` 本身更多是行业术语，不是产品名。

---

## 3. Oracle 产品矩阵：ETO 是组合，不是模块

| 层次 | Oracle 产品 / 能力 | 在 ETO 中的角色 | 关键对象 |
|---|---|---|---|
| 商机与报价 | Oracle CPQ、Order Management | 标准配置报价；定制报价通常仍需工程估算 | Quote、Sales Order、Model、Configuration |
| 项目与合同 | Project Management、Project Contracts / Billing | 项目、WBS、合同、开票计划 | Project、Task、Contract、Bill Plan |
| 产品定义 | Product Development / PLM、Product Hub | 新建 item、结构、版本、变更单、生效控制 | Item、Structure、Revision、Change Order、Redline、NIR |
| 工艺定义 | Manufacturing | 工作定义、工序、资源、产出 | Work Definition、Operation、Resource、Output |
| 生产执行 | Manufacturing | 工单、项目工单、完工、外协、合同制造 | Work Order、Project Details、Completion |
| 项目化供应链 | Project-Driven Supply Chain | 项目库存、项目采购、项目制造、项目维修 | Project Reference、Project Inventory、Project PO |
| 成本 | Supply Chain Cost Management + Project Costing | 项目 / 任务估值、支出项、burden、资本化 | Expenditure Item、Cost Group、Burden |
| 计划 | Planning Central / PDSC planning | 项目化需求与供应计划 | Project Demand、Project Supply |
| 质量 | Quality Management | 不合格、CAPA、闭环质量 | Nonconformance、CAPA |
| 文档 | PLM attachments / DMS | 图纸、规范、变更附件 | Attachment、Document |

**一句话：** Oracle 的 ETO 能力不是“一个模块开箱即用”，而是“把 PLM 的产品定义、制造的工艺与执行、项目的成本与合同、供应链的项目引用拼起来”。这也是为什么 Oracle 在 ETO 项目上通常需要实施增强，而不是只做配置。

---

## 4. Oracle Fusion 机制逐域

### 4.1 产品定义与工程变更（Product Development / PLM）

#### 4.1.1 Item、Structure、Revision

- Item 是物料主数据；Structure 是 BOM；Revision 是版本。
- 结构有 **Effectivity Control**：
  - `Date`：按日期生效；
  - `Model / Unit Number`：按单元号生效。
- Oracle 产品文档明确：**Model effective structures are typically associated with project manufacturing.** 这句话是“一物料多项目”路线的基础。
- `Model / Unit Number` 生效需要 item 设置 `Effectivity Control = Model / Unit Number`、`Structure Item Type = Model` 等前置条件。

#### 4.1.2 变更单类型

Oracle Product Development 有三类变更对象：

| 类型 | 是否控制版本 | 用途 |
|---|---|---|
| **ECO（Engineering Change Order）** | 是，自动计算 revision | 正式工程变更，最常用 |
| **Change Order without revision control** | 否 | 不触发版本递增的变更 |
| **Change Request** | 否 / 轻量 | 变更申请，审批后再转 ECO |

变更单的核心能力：

- **Affected Objects**：受影响 item、旧 / 新 revision、旧 / 新 lifecycle phase；
- **Redlines**：在变更单里对结构做增删改的“红线”，审批通过后实施；
- **Revision 计算**：ECO 自动算新版本；多个变更单对同一对象时，每个 revision 必须有不同生效日；
- **Effective Date**：可以指定未来生效日，也可以用 Supply Planning 的 use-up date；新版本生效日必须落在既有版本生效日之间；
- **Scheduled 状态**：变更单可处于 Scheduled（未来生效），此时可被后续变更单引用；
- **Workflow**：审批 / 驳回 / 终止 / 重启，支持按角色校验 item approval privilege；
- **New Item Request（NIR）**：新物料申请，常与 ETO 的新件设计配合。

#### 4.1.3 变更单的边界

- 变更单是**产品级**的：它管 item / structure / revision / effectivity，不持有 `project_id`。
- 项目影响不是变更单字段，而是通过 **where-used + 项目引用** 查询得到。
- 这一点对平台很关键：**不要把 ECM 改成项目级对象**；项目影响应作为查询维度，而不是变更单的归属。

#### 4.1.4 结构变更与工作定义的同步

Oracle Manufacturing 明确：

- 产品工程师在 Product Development 中实施结构变更；如果通过 ECO 引入，结构行的日期会带上 ECO 编号 / 行号。
- Work Definition 可以按生效日与 item structure 同步；结构变更会触发工作定义版本 / 组件行的更新。
- 工作定义版本有生效日；工单按**开工日**选取生效版本；被工单引用的工作定义不能删除，只能新建版本。

平台对应：`item_structures.valid_from / valid_to` + `work_definitions.valid_from / valid_to` 已有日期版本；ECM apply 目前把工程结构差异写入生产结构。G15 应补的是“项目物料的结构如何进入这套版本机制”，不是另建一套。

### 4.2 制造：工作定义、工单、项目字段

#### 4.2.1 工作定义

Oracle Work Definition 的层级：

```
Work Definition（Item、Version、Effective Dates、Production Priority）
└ Operation（Seq、Work Center、Count Point、Optional、Yield、MTQ）
  ├ Output（Product / By-Product、Qty、Cost Allocation）
  ├ Item（Component、Basis、Qty、Supply Type）
  └ Resource（Usage、Assigned Units、Charge Type、Alternate Resources）
```

要点：

- 工作定义按 **item** 建，不按项目建；项目差异通过“项目物料 / 配置项 / 替代工作定义”表达。
- 工作定义有版本与生效日；同一 item 可以有多个版本，按开工日选版本。
- `Production Priority` 用于多套工作定义 / 替代工艺的优先级。
- 工序产出支持 product / by-product / co-product；成本分摊比例在 output 上。
- 外协工序通过资源 / supplier operation 表达，不建独立“外协工序类型”。
- 合同制造使用客户提供的工作定义；**configured item 不支持 contract manufacturing**。

#### 4.2.2 工单上的项目字段（关键）

Oracle 工单的 **Project Details** 区域有五个字段：

| 字段 | 作用 |
|---|---|
| Project Number | 项目号 |
| Task Number | 任务号（WBS） |
| Expenditure Item Date | 支出项日期 |
| Expenditure Type | 支出类型（决定人工 / 制造费用归集） |
| Expenditure Organization | 支出组织（必须是 project expenditure organization） |

配套规则：

- 工厂参数必须启用 **Inventory Tracking by Project**，工厂必须是 **project expenditure organization**。
- 保存 / 发放工单时校验项目、任务、支出类型、支出组织的有效性。
- 工单只有 `Unreleased` 状态可改项目字段。
- **Back-to-back fulfillment** 会把销售订单上的项目字段传到工单。
- 项目工单只允许使用项目拥有的组件，完工产品进入项目库存。

这五个字段是平台 G15 最值得直接对标的部分：平台 `work_orders` 已有 `project_id`，但缺 `project_task_id` 与支出字段；`project_tasks` 已有 WBS 层级，可以直接承接。

#### 4.2.3 ATO / CTO 流程（与 ETO 的边界）

Oracle 的 CTO 流程：

1. 销售订单加入 model item；
2. Configurator 按选项生成配置；
3. Supply Chain Orchestration 检查配置是否已存在；
4. 不存在则在 Product Model 中创建 configured item；
5. 工单使用**动态生成的 configured item work definition**，它基于 ATO model work definition、所选选项和 TIA 生成，不持久化；
6. 工单按 configured item 执行。

对 ETO 的启示：

- CTO 的“配置项工作定义动态生成”是**选项驱动**，不适用于 ETO 的“每单重新设计”。
- ETO 应走“项目物料 + 工程结构 + 工作定义版本”，而不是把配置器扩成设计器。
- 平台已有 `configuration` 对象，足以支撑 CTO；G15 不要碰它。

### 4.3 Project-Driven Supply Chain（PDSC）

Oracle PDSC 的官方能力清单：

- **项目库存隔离**：不需要为每个项目建独立库存组织；在同一组织内按项目隔离、估值、收发。
- **项目采购**：项目专用采购订单、项目专用价格、项目收货。
- **项目库存操作**：按项目接收、拣货、发货、调拨。
- **项目制造**：在同一工厂用共用资源服务多个项目；项目工单只领项目物料，完工入项目库存。
- **项目维修**：维修活动按项目归集。
- **项目化计划**：可以在不接项目财务的情况下，先做项目维度的供应链计划与执行。
- **项目成本**：供应链成本作为项目支出归集，按合同规则开票。

关键设计：

- PDSC 不改 BOM，不改工艺；它只给**执行事务**加项目引用。
- 一个组织可以同时支持项目物料和非项目物料。
- 项目库存隔离靠 **project locator**（EBS）或项目库存维度（Fusion）；不是靠复制 BOM。

### 4.4 项目成本

Oracle Supply Chain Cost Management 有专门一节 **Cost Management for Project Driven Supply Chain**：

- 成本可以在 **project / task 级别**估值（valuation at project and task）。
- 供应链活动的成本捕获为 **project expenditures**。
- 不需要为每个项目建独立库存组织。
- 工单上的 Project Details 决定支出类型、支出组织、间接费用（work center / plant overhead）。
- 成本事实源是 **Expenditure Item**；归集粒度是 **Task**；burden / capitalization / billing 在项目财务侧加工。

平台对应：

- `project.budget_amount` 有预算；`project_tasks` 有 WBS 与 percent_complete；`time_entries.project_task_id` 已有工时；`v_project_task_labor` 已回聚项目任务工时。
- `purchase_order` / `receipt` / `transfer_order` / `sales_order` / `work_order` 已有 `project_id`。
- **缺**：库存事务 / 余额的项目维度；统一的项目成本视图；支出类型 / 组织 / burden；项目开票。

G15 不需要一步做到 Oracle 的 Expenditure + Burden + Capitalization + Billing；先做**派生项目成本视图**即可，但口径必须唯一。

### 4.5 订单、配置与报价

- Oracle CPQ 做配置报价；Order Management 做订单与配置项创建；Manufacturing 做配置项工单。
- CPQ 擅长 CTO，不擅长 ETO 的“从零设计 + 工程估算”。
- ETO 的报价通常需要：相似项目成本、工程工时估算、长周期物料询价、外协询价；这些在 Oracle 中往往通过 Project Estimates / 自定义流程补齐，不是 CPQ 原生能力。
- 平台目前没有报价 / CPQ；G15 不应从报价起步，应从项目立项起步。

### 4.6 计划

- EBS PJM 有 **Project MRP**、项目 ATP、项目 drop shipment、项目采购建议。
- Fusion PDSC 支持项目化计划与执行；具体计划引擎细节本稿未逐页核实（见 §10）。
- 平台 G15 首期不做项目 MRP；先用现有需求 / 采购 / 工单闭环。

---

## 5. Oracle EBS 传统 ETO 组合（历史对照）

EBS 的 ETO 组合比 Fusion 更“模块化”，也更能看清对象边界。

### 5.1 Oracle Engineering：ECO

- ECO 类型：engineering / manufacturing；类型决定能否修改工程 item / BOM / 工艺，也可同时修改两者。
- ECO 头：类型、优先级、部门、审批清单、原因、物料处置、自动编号。
- 修订对象：item、bill、component、operation、resource / routing。
- 审批：ECO 类型 + 优先级可触发 workflow；审批清单按部门 / 角色。
- 实施：ECO 可以立即实施、未来生效、或手工实施；支持 reschedule。
- 版本与生效：
  - 按 **日期** 生效；
  - 按 **model / unit number** 生效；
  - 日期生效的修订项只能带日期生效的组件；单元生效的修订项可以带单元 / 日期生效组件；
  - 旧版本组件默认带入新版本，再按需删除。
- 批量变更：Mass Change ECO 可批量增删替换组件、改用量 / 产出率，按 item 范围 / 类别 / 类型选择所有使用该组件的装配。
- **工程 BOM → 制造 BOM**：EBS 明确区分 engineering item / BOM 与 manufacturing item / BOM；ECO 可以把工程 item、BOM、routing 转移或复制到制造侧。
- MRP：可以计划未发布 ECO 的修订，支持“先备料、后生效”。

### 5.2 Oracle BOM：Model / Option Class / Configured Item

- BOM 类型：standard、model、option class、planning 等。
- Model BOM 由 option class 与选项组成；配置 BOM 在订单配置时生成。
- 配置项编号可按 sequence、order / line number 等规则自动生成。
- 工艺路线支持 option-dependent operations：只有被选中的选项才带出对应工序。
- 替代资源、替代 BOM、替代工艺路线都是独立能力。
- 工程变更单在 BOM 上有 **ECO** 页签，记录变更单、版本、生效日期。

### 5.3 Oracle Project Manufacturing（PJM）

PJM 是 EBS 的“项目制造”模块，官方定义支持 **engineer-to-order、make-to-order、Seiban** 环境，也支持 ATO / PTO。核心机制：

- **Project Reference**：库存组织可启用项目引用；单据带 Project / Task；控制级别可选 Project 或 Task。
- **Project Locator**：按项目 / 任务隔离库位与库存，避免项目物料混用。
- **Project Work Order**：离散工单带项目 / 任务；工单组件、发料、完工都受项目约束。
- **Cross-project Issues**：默认禁止跨项目发料；可配置允许，但会产生跨项目费用。
- **Cost Group + Burden Schedule**：项目成本组、间接费用计划，成本回写 Oracle Projects。
- **Project MRP**：按项目计划需求；支持项目 ATP、项目 drop shipment、项目采购。
- **Project Manufacturing Flow**：从投标 / 报价开始，工程评审、NPI、产能模拟、合同专用外协采购分析、RFQ，再进入项目执行。

EBS 的 PJM 说明了 ETO 的完整前端：**报价与工程估算在项目制造流程里，不是在 BOM 里**。

### 5.4 Oracle Projects

- 项目、任务、支出项、预算、负担、资本化、开票。
- PJM 把制造 / 库存 / 采购成本写入 Oracle Projects 的支出项，再按合同开票。
- 项目成本归集粒度是 Task，不是 Project。

### 5.5 EBS 与 Fusion 的差异

| 维度 | Oracle EBS 12.2 | Oracle Fusion 25C | 对平台的启示 |
|---|---|---|---|
| 工程 / 制造 BOM | 显式两套（ENG / MFG），ECO 转移 / 复制 | 一套 item structure + change order + revision / effectivity | 平台 `usage=engineering / production` + ECM 接近 EBS，保留 |
| 项目制造 | 独立 PJM 模块，project reference / locator / project MRP | PDSC 贯穿 SCM + ERP，project reference + 项目库存 / 成本 | 平台已有 project_id 铺底，补库存维度即可 |
| 项目库存 | Project Locator | 项目库存 / 项目组织参数 | 平台需补 inventory 的项目维度 |
| 变更单 | ECO 有独立模块与审批清单 | Change Order / ECO + workflow + redline | 平台 ECM 已有审批与 apply，缺 redline / revision 自动算 |
| 成本 | PJM 成本组 + Oracle Projects | Cost Management PDSC + Project Costing | 平台先做派生视图，后补支出台账 |
| 配置 | Model / Option Class / Configured Item | ATO model WD / configured item WD | 平台 configuration 可支撑 CTO，ETO 不用 |

---

## 6. Oracle Fusion 端到端 ETO 流程

| 阶段 | 业务动作 | Oracle 对象 / 事务 | 关键控制 | 平台对应 | 差距 |
|---|---|---|---|---|---|
| 1. 商机 / 报价 | 相似项目估算、长周期询价、外协询价 | CPQ / OM / 自定义估算 | 报价版本、毛利率 | 无报价对象 | G15 不做 |
| 2. 项目立项 | 建项目、WBS、预算、合同 | Project、Task、Contract、Budget | 项目类型、组织、预算 | `projects`、`project_tasks`、`budget_amount` | 合同 / 开票无 |
| 3. 初步设计 | 新建项目物料、工程结构、版本 | Item、NIR、Structure、Revision | 设计评审、版本 | `items`、`item_structures(usage=engineering)` | 项目物料标记 / 编号规范 |
| 4. 长周期采购 | 项目专用采购、项目收货 | PO Project Reference、Receipt | 项目 / 任务、价格 | `purchase_order.project_id`、`receipt.project_id` | 项目库存维度 |
| 5. 设计冻结 / 变更 | ECO / Change Request、红线、审批、生效日 | Change Order、Affected Objects、Redline | revision / effectivity | `engineering_changes` + lines + 审批 | 红线、revision 自动算、单元生效 |
| 6. 发布制造 | 工程结构 → 生产结构 / 工作定义 | ECO release、Work Definition sync | 生效日、版本 | ECM apply + `work_definitions` | 项目物料的发布路径 |
| 7. 工单执行 | 项目工单、项目领料、工序执行 | Work Order + Project Details | 项目 / 任务 / 支出类型 | `work_orders.project_id`、`work_order_components` | `project_task_id`、支出字段 |
| 8. 完工 / 发货 | 完工入项目库存、项目发货、as-built | Completion、Shipment、Serial / Lot | 项目库存、序列号 | `shipment.project_id`、`serial_number` | 项目库存、as-built |
| 9. 项目成本 / 结算 | 支出项、burden、资本化、开票 | Expenditure、Burden、Capitalization、Billing | Task 粒度 | 派生视图（工时 / 采购 / 工单） | 支出台账、burden、开票 |
| 10. 售后 / 维保 | 项目维修、服务合同 | PDSC Maintenance | 项目 / 合同 | 无 | G15 不做 |

---

## 7. Oracle 的关键设计取舍

| 决策 | Oracle 做法 | 优点 | 代价 | 对平台 G15 |
|---|---|---|---|---|
| 项目 BOM 是否独立 | 不建项目 BOM；用项目物料或 model / unit effectivity | 不复制结构、无版本分叉 | 项目检索依赖 item / unit；主数据膨胀 | **保持 D5，不建项目 BOM 快照** |
| 变更单归属 | 产品级，不挂项目 | 变更可跨项目复用 | 项目影响要额外查询 | ECM 保持产品级，影响预览加项目过滤 |
| 项目归属 | 执行事务带 project reference | 主数据干净、可多项目共用 | 每个执行对象都要带字段并校验 | 平台已铺 project_id，补 task / 库存 |
| 成本事实源 | Expenditure Item 唯一 | 口径统一、可审计 | 需要项目财务模块 | 先做单一派生成本服务，后补台账 |
| 工程 / 制造 BOM | EBS 两套；Fusion 一套 + 变更单 | EBS 边界清晰；Fusion 版本灵活 | Fusion 依赖变更流程纪律 | 平台保留 usage + ECM，不合并 |
| ETO vs CTO | 两条产品线，不混用 | 边界清晰 | 同厂要支持 mixed-mode | G15 只做 ETO，不扩配置器 |
| 生效控制 | 日期为主，model / unit 为辅 | 覆盖序列化 ETO | unit effectivity 复杂 | P1 日期；P3 再评估 unit / serial |
| 合同制造 | 支持，但 configured item 不支持 | 外协边界明确 | ETO 外协需按项目物料走 | 平台外协已可用，不扩配置项外协 |

---

## 8. 对平台 G15 的落点建议

### 8.1 先验证 G4 D5

G4 已裁决：**不建项目级 BOM 快照**，快照放在工单组件（`work_order_components`）与配置实例。

Oracle 对标后，这个裁决成立，而且理由更清楚：

- Oracle 没有项目 BOM 表；项目定制通过“项目物料 / 配置”进入物料级结构。
- 项目归属通过执行事务的 project reference 表达。
- 项目基线如确有需要，只做**指针表**，不复制结构行。

因此 G4 A.5 的第 1 项应改写为：

> 原：项目专用 BOM & 工艺
> 新：项目物料 / 项目配置承载定制；BOM 与工艺仍按物料级版本管理；项目归属落在工单 / 库存 / 采购 / 成本；如出现合同基线对比，再加轻量指针表。

### 8.2 分层落地

#### P1：最小闭环（复用现有，补 3 个缺口）

1. **项目物料**
   - 一项目一物料：`item.code = <project_no>-<seq>`（或等价命名规范）。
   - 可选：`items` 增加可空 `project_id` 仅作检索标记，不进入业务键；也可先用属性 / 分类表达。
   - 不新增 `project_item` 表，不给 `item_structures` 加 `project_id`。

2. **工程结构 → 生产结构**
   - 项目物料建 `item_structures(usage=engineering)`，按 revision 管理。
   - 用 ECM 的 add / modify / remove 行把工程结构差异发布到 `usage=production`。
   - 初次建 BOM 可直接建生产结构；后续变更走 ECM，避免把 ECM 当 BOM 创建器。

3. **项目工单**
   - 复用 `work_orders.project_id`。
   - 增加可空 `project_task_id`（WBS 任务），并在服务层校验 project / task 一致。
   - 支出字段（expenditure type / date / org）首期可不落库；如落库，保持可空，不阻塞非项目工单。

4. **项目库存（真正的缺口）**
   - `inventory_transactions` 与 `inventory_balances` 缺 `project_id`；余额唯一键也不含项目。
   - 两条路线：
     - A. 给两张表加可空 `project_id`，非空时进入唯一键（推荐，和 Oracle 项目库存语义一致）；
     - B. 项目 locator：按项目建库位，余额仍按库位隔离（改动小，但项目维度查询弱）。
   - 首期建议 A 的轻量版：先加 `project_id` 到事务与余额，唯一键用 `project_id=0` 哨兵；后续再评估 locator。

5. **项目采购**
   - `purchase_order` / `receipt` / `transfer_order` 已有 `project_id`；补“收货 → 入库事务 → 库存余额”的项目传递，避免入库后丢项目。

6. **项目成本（派生视图，不做台账）**
   - 新建单一服务 / 视图 `v_project_cost`，口径：
     - 人工：`time_entries` → `v_project_task_labor`（工时 × 费率）；
     - 采购：`receipt` / `purchase_order_line` 带 `project_id` 的金额；
     - 制造：`work_order` 带 `project_id` 的工时 + 领料数量（按标准成本或采购价）。
   - 只做“预算 vs 实际”对比（`projects.budget_amount`），不做 burden / capitalization / billing。

7. **ECM 项目影响**
   - 在影响预览中增加项目维度：受影响结构被哪些项目物料使用、哪些项目工单在途。
   - 不把 `project_id` 加到 `engineering_changes`。

#### P2：增强

- **项目结构基线指针表**：`project_structure_baseline(project_id, structure_id, revision, purpose, captured_at)`，只存指针；用于合同基线 / 设计冻结对比。
- **项目库存台账 / locator**：项目库存查询、项目间调拨、项目 ATP。
- **长周期物料跟踪**：项目采购齐套、关键件到货预警。
- **项目变更影响**：where-used + 项目引用 + 在途工单的联合查询。
- **项目物料归档**：项目结束后 item / structure 的 phase-out 与检索策略。

#### P3：可选 / 后续专题

- **单元 / 序列号生效**：`Model / Unit Number` 或 serial effectivity；与现有 serial number 模型衔接。
- **As-built genealogy**：工单组件快照 + 序列号 + 批次，形成项目交付构型。
- **项目支出 / burden / 资本化 / 开票**：财务域专题，不在 G15。
- **项目排程 / 产能**：多项目资源冲突、项目优先级。
- **项目 MRP**：项目维度计划，依赖计划域。

### 8.3 明确不建

- 独立 ETO 模块；
- 项目 BOM 快照 / 项目专用 BOM 表；
- 项目专用工作定义表（用项目物料 / 版本即可）；
- CPQ / ETO 设计器（现有 `configuration` 只服务 CTO）；
- CAD / PDM / DMS；
- 完整项目会计（Expenditure / Burden / Capitalization / Billing）；
- 项目合同与开票；
- 项目维度的主数据复制（项目物料不是“第二套 item master”）。

### 8.4 验收场景

| 场景 | 步骤 | 通过标准 |
|---|---|---|
| A. 新项目定制件 | 建项目 → 建项目物料 → 建工程结构 → ECM 发布到生产结构 → 建项目工单 → 领料 → 完工入项目库存 → 项目成本视图 | 项目 / 任务 / 物料 / 工单 / 库存 / 成本全链路可追；非项目库存不受影响 |
| B. 设计变更 | 改工程结构 → ECM 影响预览显示项目与在途工单 → 审批 → apply → 新工单取新版本 | 旧工单不被静默改版；影响预览项目维度正确 |
| C. 标准件跨项目 | 同一标准 item 供两个项目 → 项目采购 / 收货 / 入库 / 领料 | 两个项目库存不混、成本不串；BOM 不被复制 |

### 8.5 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 物料主数据膨胀 | 一项目一物料会产生大量 item | 命名规范 + 项目结束归档 / phase-out；后续评估 unit effectivity |
| 库存项目维度改动大 | 余额唯一键变更、历史数据迁移 | 可空 `project_id` + 0 哨兵；先事务后余额；用迁移脚本回填 |
| 成本口径双真源 | 采购金额、库存成本、工单工时各算一套 | 单一 `v_project_cost` 服务；明确“采购按收货、制造按工单、人工按工时” |
| 项目任务缺失 | 工单只有 project_id，成本无法落到 WBS | 增加可空 `project_task_id`；首期允许项目级归集，任务级逐步补齐 |
| 变更与生效控制 | 平台只有日期生效，ETO 需要 unit / serial | P1 日期；P3 再评估；不要提前引入复杂 effectivity |
| ECM 被项目化 | 把 project_id 加到变更单，导致变更无法跨项目复用 | 保持产品级；项目影响只做查询 |

---

## 9. 横向定位（简要，二手证据）

| 产品 | ETO 定位 | 强项 | 弱项 / 代价 |
|---|---|---|---|
| **Oracle Fusion** | 组合式 ETO：PLM + Manufacturing + PDSC + Project Financials | 项目化供应链、项目库存 / 采购 / 成本、制造执行完整；同厂 mixed-mode | 模块多、集成重；ETO 前端报价 / 工程估算非原生；长周期深序列化 ETO 不如专用 ETO 产品 |
| **Oracle EBS** | Engineering + BOM + PJM + Projects | 工程 / 制造 BOM 边界清晰；PJM 项目引用 / locator / project MRP 成熟 | 技术栈老；Fusion 迁移成本 |
| **SAP** | PS + VC + ECM + DMS + project stock | 长周期、复杂 ETO、项目库存、变更管理深 | 配置复杂、实施重 |
| **IFS Cloud** | 工程 + 文档 + 项目 + 制造一体化 | ETO 原生感强，项目制造 / 文档 / 变更协同 | 生态与大型集团深度不如 SAP / Oracle |
| **Epicor / NetSuite** | 中端 ETO / job shop | 上手快、报价 / 工程变更轻量 | 复杂项目、长周期、深配置不足 |

> 结论：Oracle 在“项目化供应链 + 制造执行 + 项目成本”上是最完整的头部产品之一；但它不是“ETO 开箱即用”，而是“ETO 可组合”。平台 G15 应学它的**对象边界**，不要学它的**模块数量**。

---

## 10. 未核实项与后续研究

1. **Fusion 的“项目专用 BOM”是否存在显式对象**：官方文档只明确 model / unit effectivity 与 project manufacturing 的关联；“一项目一物料”是行业实践推断，未在 Oracle 文档中逐字确认。
2. **Fusion PDSC 的计划细节**：项目 MRP / 项目 ATP / 项目 drop shipment 在 EBS 文档中明确；Fusion 侧本稿未逐页核实。
3. **Fusion 项目开票 / 合同集成**：本稿只引用 Project Financials 的支出 / burden / capitaliz / billing 概念，未核对 Fusion 具体页面。
4. **Change Order 状态全集**：本稿确认 `Scheduled` 与 workflow 完成生效；完整状态枚举未逐页核对。
5. **CPQ 的 ETO 估算能力**：未核实 Oracle CPQ 是否支持“从零设计”的工程估算；本稿倾向“不支持，需项目估算补齐”。
6. **EBS PJM 的 ATO / PTO 细节**：只确认支持；未展开配置项与项目引用的组合规则。
7. **SAP / IFS 的具体字段**：本稿只用二手资料做定位，不作为设计依据。

---

## 11. 参考来源

### Oracle 官方

- [O1] Oracle Fusion Cloud SCM, *Using Manufacturing*, 25C, G34542-01 — [PDF](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faumf/using-manufacturing.pdf)
- [O2] Oracle Fusion Cloud SCM, *Implementing Product Management*, 25C, G34519-01 — [PDF](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faipr/implementing-product-management.pdf)
- [O3] Oracle Fusion Cloud SCM, *Using Product Development*, 25C, G34546-03 — [PDF](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faupd/using-product-development.pdf)
- [O4] Oracle Fusion Cloud SCM, *Using Supply Chain Cost Management*, 25C, G34557-02 — [PDF](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/fapma/using-supply-chain-cost-management.pdf)
- [O5] Oracle, *Project-Driven Supply Chain in the Cloud*（方案简介，2020）— [PDF](https://www.oracle.com/a/ocom/docs/applications/scm/oracle-project-driven-supply-chain-in-cloud-brief.pdf)
- [O6] Oracle, *Oracle Fusion Cloud Manufacturing* 数据表（v4.0，2024）— [PDF](https://www.oracle.com/a/ocom/docs/applications/scm/oracle-manufacturing-cloud-ds.pdf)
- [O7] Oracle EBS 12.2, *Project Manufacturing Implementation Guide*, E48955-01 — [PDF](https://docs.oracle.com/cd/E51111_01/current/acrobat/122pjmig.pdf)
- [O8] Oracle EBS 12.2, *Project Manufacturing User's Guide*, E48956-01 — [PDF](https://docs.oracle.com/cd/E51111_01/current/acrobat/122pjmug.pdf)
- [O9] Oracle EBS 12.2, *Engineering User's Guide*, E48939-02 — [PDF](https://docs.oracle.com/cd/E51111_01/current/acrobat/122engug.pdf)
- [O10] Oracle EBS 12.2, *Bills of Material User's Guide*, E48954-01 — [PDF](https://docs.oracle.com/cd/E51111_01/current/acrobat/122bomug.pdf)

### 内部研究

- [S1] `spec-oracle-fusion-project-object-model-2026-10-31.md` — 项目 / 任务 / 支出 / 合同对象模型
- [S2] `spec-project-g4-engineering-bom-2026-11-03.md` — G4 ECM / D5 / G15 边界
- [S3] `spec-routing-process-manufacturing-benchmark-2026-11-01.md` — P5 工作定义 / 序列 / 产出

### 二手 / 定位

- [S4] ERP Research, *Oracle Cloud ERP for Manufacturing (2026)* — [页面](https://erpresearch.com/en-gb/oracle-cloud-erp-for-manufacturing)
- [S5] OAUG 2008, *Implementing Oracle Discrete Manufacturing in an Engineer to Order Environment* — [PDF](https://idealpenngroup.tripod.com/sitebuildercontent/OAUG2008/Collaborate20Collaborate07/pdfs/smajumdar_wp.pdf)
- [S6] IFS, ETO 能力介绍（二手）— [页面](https://www.ifs-erp.com/en/blog/the-architectural-failure-of-static-manufacturing)

---

## 附录 A：术语

| 术语 | 含义 |
|---|---|
| ETO | Engineer-to-Order，按单设计 |
| MTO | Make-to-Order，按订单生产 |
| ATO | Assemble-to-Order，按订单装配 |
| CTO | Configure-to-Order，按订单配置 |
| EBOM / MBOM | 工程 BOM / 制造 BOM |
| ECO | Engineering Change Order，工程变更单 |
| Effectivity | 生效控制：日期 / 模型 / 单元号 / 序列号 |
| PDSC | Project-Driven Supply Chain，项目驱动供应链 |
| PJM | Oracle Project Manufacturing（EBS 模块） |
| WBS | Work Breakdown Structure，工作分解结构 |
| Expenditure Item | 支出项，项目成本唯一事实源 |
| Burden | 间接费用 / 负担 |
| Capitalization | 资本化 |
| NIR | New Item Request，新物料申请 |

## 附录 B：Oracle 对象与平台对象速查

| Oracle 对象 | 作用 | 平台对应 | 状态 |
|---|---|---|---|
| Item | 物料 | `items` | 有 |
| Item Structure | BOM | `item_structures` / `item_structure_lines` | 有（usage=engineering / production） |
| Revision | 结构版本 | `item_structures.revision` | 有 |
| Change Order / ECO | 工程变更 | `engineering_changes` / `engineering_change_lines` | 有（无 redline / 自动 revision） |
| Affected Objects | 受影响对象 | ECM 行 + 影响预览 | 部分 |
| Effectivity（Date） | 日期生效 | `valid_from` / `valid_to` | 有 |
| Effectivity（Model / Unit） | 单元生效 | 无 | 缺口 |
| Work Definition | 工作定义 | `work_definitions` | 有 |
| Work Definition Version | 工作定义版本 | `revision` + `valid_from` / `valid_to` | 有 |
| Work Order | 工单 | `work_orders` | 有 |
| Work Order Project Details | 项目 / 任务 / 支出字段 | `project_id`；缺 `project_task_id` / 支出字段 | 部分 |
| Project | 项目 | `projects` | 有 |
| Task / WBS | 项目任务 | `project_tasks` | 有（层级 + 状态） |
| Project Inventory | 项目库存 | `inventory_balances` / `inventory_transactions` | 缺 project 维度 |
| Project PO / Receipt | 项目采购 | `purchase_order` / `receipt` | 有 `project_id` |
| Project Cost / Expenditure | 项目成本 | `time_entries` + 派生视图 | 部分（无台账） |
| Configuration / Configured Item | 配置项 | `configuration` / `configuration_component` / `configuration_value` | 有（CTO 基础） |
| Serial Number | 序列号 | serial number 模型（P6） | 有（未接结构生效） |
