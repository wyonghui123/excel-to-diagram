# 研究稿：ETO 其他头部产品研究 — IFS / Infor（附 Epicor / D365）

- 文档版本：v0.1
- 日期：2026-11-04
- 状态：研究稿（仅研究，**尚未实施**）
- 前置文档：
  - `spec-project-g15-eto-oracle-benchmark-2026-11-03.md`
  - `spec-project-g15-eto-sap-benchmark-2026-11-04.md`
  - `spec-project-g15-eto-oracle-vs-sap-2026-11-04.md`
- 目的：补齐 Oracle / SAP 之外的中高端 ETO 产品证据，检验平台 G15 的既有裁决是否只在"两大厂"语境下成立。

---

## 0. 结论摘要（十条）

1. **IFS 是"项目交付物"路线。** IFS Cloud 用 Project + WBS + **Project Deliverable（项目交付物）+ Project Deliverable Item** 承载 ETO：项目交付物可以有**项目专属 BOM**、**项目专属工序**，下达时按开关选择"用项目工序"还是"用标准工序"。
2. **Infor LN 是"工程开关"路线。** LN 的 PCS（Project Control System）为 ETO 生成 **customized item + customized BOM + customized routing**；但项目上有 **Engineering Allowed** 开关：关闭时走 standard-to-order（lean PCS），**不复制 BOM/Routing**，只把物料挂到项目上。
3. **Infor CSI（原 SyteLine）是"估算 → 订单/工单"路线。** 先做 Estimate（材料/人工/制造费用/外协），中标后从 Estimate 直接生成销售订单与工单；项目、服务、质量、ETO/MTS 混合模式打包在中端制造 ERP 里。
4. **Epicor Kinetic 是"Job 中心"路线。** 报价 → 销售订单 → Job；BOM/工序/成本随 Job 走；Engineering Workbench 做 revision / ECO；Advanced Project Accounting 做项目账。
5. **Dynamics 365 的 ETO 主要靠"项目"承载。** 官方表述：ETO 通常在项目里处理；制造项目把产品/服务、进度、预算组合起来，制造部分再用其他订单类型执行；原生 ETO 深度弱于 IFS/Infor/SAP。
6. **"项目 BOM"不是大厂专利。** SAP、IFS、Infor LN、Epicor（Job BOM）都支持某种形式的项目/订单级结构；Oracle 与 D365 更偏"项目引用 + 物料/项目"。
7. **但所有产品都有一个"是否复制结构"的开关或等价机制。** Infor LN 的 `Engineering Allowed`、IFS 的 `Use Project Operations`、Oracle 的"项目物料 / effectivity"、SAP 的 Order/WBS BOM，本质都是同一个决策：**这次项目要不要拥有自己的结构。**
8. **中端 ETO 产品的成本口径天然是"Job/Project Costing + Estimate vs Actual"，不是 SAP 式 CO 结算。** Infor CSI、Epicor、IFS 都是这个路子。这直接验证平台"派生成本视图 + 预算对比"的选择是行业中端标准做法，不是简化偷懒。
9. **对 G15 的裁决没有反转，反而更稳。** 任务轴、库存任务维度、采购先行、变更产品级、成本单一口径——五条结论在 IFS/Infor/Epicor 上都能找到对应证据。
10. **唯一值得吸收的新概念：项目级的"设计模式开关"。** Infor LN 用 `Engineering Allowed` 明确区分"有工程的项目"与"只挂项目的标准单"；平台可在 P2 给项目加一个 `design_mode`（engineered / standard），避免所有项目都被迫走 ETO 重流程。

---

## 1. 研究方法与证据强度

| 证据 | 来源 | 强度 | 用途 |
|---|---|---|---|
| IFS Cloud 文档：Project Deliverable Item / Create Item Operations | `docs.ifs.com` 官方文档 | 强 | 项目交付物、项目工序、下达时复制规则 |
| IFS Cloud 文档：Connect Shop Order to Project Activity | `docs.ifs.com` 官方文档 | 强 | 工单与项目活动的连接 |
| IFS Cloud 文档：MRP | `docs.ifs.com` 官方文档 | 强 | 项目需求进入 MRP |
| IFS《Project Solution Overview》PDF | IFS 官方 PDF（签名链接） | 强 / 中（链接可能失效） | 项目专属 BOM、项目 WBS 需求、制造供应项目化 |
| Infor LN 文档：Lean PCS projects | `docs.infor.com` 官方文档 | 强 | standard-to-order 不复制 BOM/Routing |
| Infor LN 文档：Generate (Budget PCS) Structure | `docs.infor.com` 官方文档 | 强 | 报价阶段生成 customized item / BOM / routing |
| Infor LN 文档：Projects（Engineering Allowed） | `docs.infor.com` 官方文档 | 强 | 工程开关语义 |
| Infor LN 文档：Items（Customized） | `docs.infor.com` 官方文档 | 强 | customized item 与项目代码 |
| Infor CSI 产品页 / 方案页 / 概述 PDF | Infor 官方 + 伙伴 | 中 | ETO/MTO/MTS 混合、Estimate 流程 |
| Epicor 官方：Kinetic Project Management / Product Data Management | `epicor.com` 官方 | 强 / 中 | Job、项目会计、Engineering Workbench、revision/ECO |
| Epicor 官方：Make-to-Order | `epicor.com` 官方 | 中 | ETO 定位 |
| Microsoft Learn：Production process overview | `learn.microsoft.com` 官方 | 强 | ETO 由项目承载、制造项目 |
| 第三方榜单 / 咨询文章 | gaugius / erpimplementation 等 | 低 | 只作旁证，不进结论 |

> 说明：IFS 的 PDF 链接带签名，可能过期；本稿以 `docs.ifs.com` 的稳定文档为主证据。

---

## 2. IFS：项目交付物路线

### 2.1 定位

IFS Cloud 的 ETO 不是独立模块，而是 **Projects + Manufacturing + Supply Chain + Document Management + Change Management** 的组合。官方材料把它概括为"工程、文档、采购、生产、项目、变更控制在一个流里"，适合专用机械、资本设备、基础设施类项目。

### 2.2 对象模型

| 对象 | 作用 | 官方要点 |
|---|---|---|
| Project | 项目头 | 项目、活动、里程碑、进度 |
| Project Activity / WBS | 项目活动与工作分解 | 制造需求可直接挂项目 WBS |
| **Project Deliverable** | 项目交付物 | 项目交付物的集合，可按交付物组织 |
| **Project Deliverable Item** | 项目交付物物料 | 可以有**项目专属结构**与**项目专属工序** |
| Project Operations | 项目工序 | `Use Project Operations = Yes` 时，下达工单复制项目工序；`No` 时用标准工序 |
| Shop Order | 生产工单 | 可通过项目杂项需求、客户订单或手工连接到项目活动 |
| Customer Order | 项目关联客户订单 | 项目可以直接接客户订单 |
| Project Miscellaneous Demand | 项目杂项需求 | 在项目 WBS 上直接产生制造/采购需求 |

### 2.3 ETO 机制

1. **项目 WBS 是需求入口。** 可以直接在项目活动/WBS 上录入制造需求（project miscellaneous demand），也可以接项目关联的客户订单。
2. **项目交付物物料是结构载体。** 项目交付物物料可以定义项目专属 BOM；工单下达时按 `Use Project Operations` 决定"用项目工序"还是"用标准工序"。
3. **工单必须与项目连接。** 官方前置条件：工单要通过项目杂项需求、客户订单或手工连接挂到项目活动；MRO 类工单不能手工连接。
4. **制造供应全项目化。** 官方概述：无论走哪种方式，工单与后续采购申请/订单都项目连接。
5. **标准与项目的切换是显式开关。** 这与 Oracle 的"项目物料 / effectivity"、SAP 的"Order BOM / WBS BOM"是同一决策的不同实现。

### 2.4 流程（推断 + 官方对象）

| 阶段 | IFS 对象 |
|---|---|
| 报价 / 项目立项 | Customer Order / Project / Project Deliverable |
| 设计 | Project Deliverable Item、项目 BOM、文档 |
| 长周期采购 | 项目 WBS 需求 → 采购申请/订单 |
| 生产 | Shop Order 连接项目活动；项目工序或标准工序 |
| 交付 | 项目交付物 → 客户订单/发货 |
| 成本 | 项目维度成本归集（Project Cost） |

### 2.5 取舍

- 优点：项目交付物把"交付什么"与"怎么造"分开，ETO 语义清晰；项目/标准工序可切换，复用与定制兼顾。
- 代价：项目交付物 + 项目 BOM + 项目工序形成三层主数据，项目多时维护量大；需要成熟的 Projects 模块配套。

---

## 3. Infor：两条产品线，两种路线

Infor 在 ETO 上不是一款产品，而是至少三条线：

- **Infor LN**：中大型离散制造，PCS 项目控制，ETO 能力强。
- **Infor CloudSuite Industrial（CSI，原 SyteLine）**：中端制造，ETO/MTO/CTO/MTS 混合，Estimate → 订单/工单。
- **Infor VISUAL**：中小型按单制造 / job shop（本稿只作提及，未展开）。

### 3.1 Infor LN：工程开关 + 定制结构

#### 3.1.1 PCS 项目

官方定义：项目是"为某个客户订单专门执行的一组生产与采购活动"，由"订单策略 = To Order"的物料销售订单触发；项目用于计划与协调物料生产。

#### 3.1.2 ETO：生成 customized item / BOM / routing

官方文档（Generate Budget PCS Structure for Sales Quotations）：

- LN 为报价行物料创建 **customized item**，同时创建 **customized BOM** 与 **customized routing**；
- 如果 BOM 子件的订单策略是 To Order，则为子件也创建 customized item，并插入父件的 customized BOM；
- 只为报价行上的 To Order 物料创建 customized item。

#### 3.1.3 关键开关：Engineering Allowed

官方文档（Projects）：

- `Engineering Allowed` 勾选 = 允许项目维护 customized BOM / routing、项目结构、项目级成本计算；
- 未勾选 = 项目所有 end item 都是 standard-to-order；**不能维护 customized BOM / routing**；一旦加入 customized item，系统自动勾选。

#### 3.1.4 Lean PCS：standard-to-order 不复制结构

官方文档（Lean PCS projects）：

- 目的：项目活动可 pegged 到具体销售订单，成本可按 PCS 项目归集；
- 物料被复制到 PCS 项目（项目代码加入物料编码，成为 customized item），**但 BOM 与 Routing 不复制**，因为它们是标准结构；
- 因此工程不再可能；BOM/Routing 只存一份，避免重复数据。

**这是本稿最有价值的一条证据：** Infor LN 明确把"项目是否需要工程"做成开关，并用它决定"项目是否拥有自己的结构"。这比"一律建项目 BOM"或"一律不建"都更精确。

#### 3.1.5 取舍

- 优点：复用与定制边界清晰；标准单不产生冗余结构；ETO 单有完整定制结构。
- 代价：开关一旦误设，工程能力会被关闭；定制 item 仍会随项目增长（项目代码进物料编码）。

### 3.2 Infor CSI（SyteLine）：Estimate → 订单/工单

官方/伙伴资料给出的流程：

1. **Estimate**：计算材料、人工、制造费用（burden）、外协成本；可从其他 Estimate、工单或 BOM 复制；估算过程可挂文档。
2. **中标**：从 Estimate 直接生成销售订单与工单。
3. **执行**：Job/Work Order 跟踪人工、物料、机器、成本、废品、WIP、成品库存。
4. **项目/服务/质量**：项目、服务、质量打包；支持 ETO、MTS、MTO、CTO、混合模式。
5. **CPQ**：Infor 的配置器在多级配置规则、自动生成 BOM 上较成熟（二手评价，未逐项核实）。

**判断：** CSI 的 ETO 是"估算驱动 + Job 驱动"，项目结构不是主数据重点，成本与执行在 Job 上；比 LN 轻，适合中端。

### 3.3 Infor 的配置能力

- Infor CPQ / Configure-to-Order 在 ETO 场景里承担"可配置部分"的报价与 BOM 生成；纯 ETO 的从零设计仍靠工程。
- 与 Oracle CPQ、SAP VC 的边界一致：配置器解决"选项组合"，不解决"重新设计"。

---

## 4. 其他产品速览

### 4.1 Epicor Kinetic

- **Job 中心**：报价接受后直接转销售订单与 Job；BOM、工序、成本随 Job 前推，估算与实际保持对齐。
- **Engineering Workbench**：装配修改、评审、审批、revision 更新与控制、check-out、ECO、BOM 维护、what-if BOM / 成本滚算、routing 维护。
- **Project Management / Advanced Project Accounting**：项目估算、计划、排程、成本、合同、收入确认、项目分类账。
- **定位**：中端离散制造 / 工业机械 / 金属加工，ETO 与 MTO 混合。

### 4.2 Microsoft Dynamics 365

- 官方《Production process overview》：ETO 通常由**项目**承载；制造项目把产品与服务、进度、预算组合；制造部分可由其他订单类型执行。
- 项目会计主要由 Project Operations 承担；供应链侧的项目库存/项目采购深度弱于 Oracle PDSC / SAP PS。
- **定位**：已有 Microsoft 生态、项目与服务混合的企业；纯 ETO 制造不是最强项。

### 4.3 Rootstock / NetSuite（只作旁证）

- Rootstock：云 ERP，强调 revision-aware 的订单与制造文档、工程发布门禁（二手）。
- NetSuite：原生工单与库存，但 ETO 深度有限，通常需要 SuiteBilling/项目模块补齐（二手）。
- 本稿不把它们纳入主对比。

---

## 5. 跨产品能力矩阵

| 能力维度 | Oracle | SAP | IFS | Infor LN | Infor CSI | Epicor Kinetic | D365 |
|---|---|---|---|---|---|---|---|
| 项目/WBS 轴 | Project + Task | Project + WBS | Project + Activity/WBS | PCS Project + 结构 | Project（较轻） | Project | Project |
| 项目级结构 | 项目物料 / effectivity | Order BOM / WBS BOM | **Project Deliverable Item BOM** | **customized BOM（受 Engineering Allowed 控制）** | Estimate/Job BOM（订单级） | **Job BOM + revision** | 弱（项目 + 标准 BOM） |
| 结构复制开关 | 项目物料 / unit | BOM 类别选择 | `Use Project Operations` | **`Engineering Allowed`** | 从 Estimate/工单复制 | Job 生成时复制 | 无显式 |
| 项目库存 | project/task 维度 | 特殊库存 `Q`（WBS） | 项目连接供应 | 项目 pegging | 项目/工单 | Job/项目 | 项目库存较弱 |
| 变更/版本 | Change Order + redline | Change Master + effectivity | Change Management + 文档 | ECO / revision | ECO / revision | Engineering Workbench + ECO | 工程变更模块 |
| 成本 | Expenditure + 项目财务 | PS + CO 结算 | Project Cost | PCS 项目成本 | Estimate vs Actual / Job Cost | Job Cost + Project Accounting | Project Operations |
| 计划 | PDSC planning | Project MRP + PMMO | MRP + 项目需求 | MRP + 项目结构 | APS / 有限产能 | MRP / 排程 | MRP |
| 配置/CPQ | CPQ（CTO 强） | VC / Super BOM | IFS CPQ | 配置管理 | Infor CPQ（较强） | Epicor CPQ | 产品配置 |
| 文档/PLM | PLM attachment | DMS / DIR | 文档管理较强 | PLM / EDM | 附件 | Product Data Management | 文档管理 |
| 主战场 | 大型项目型供应链 | 大型集团 / 项目会计 | 项目型制造 / 资产密集 | 中大型离散 | 中端制造 | 中端离散 / Job Shop | MS 生态 / 项目服务 |

**读法：**

- "项目级结构"这一列，**五家（SAP/IFS/Infor LN/Epicor/Infor CSI）都有某种实现**；Oracle 用替代路线，D365 最弱。
- "结构复制开关"这一列，**IFS 与 Infor LN 把它做成了显式配置**；这正是平台可以借鉴的"设计模式开关"。
- "成本"这一列，中端产品（IFS/Infor/Epicor）都是 **Project/Job Costing + Estimate vs Actual**，没有一家要求平台自建 CO 引擎。

---

## 6. 对 G15 的证据校验

### 6.1 五条既有结论的交叉验证

| G15 结论 | 新证据 | 判定 |
|---|---|---|
| 任务/WBS 是归集轴（P1 必做） | IFS 项目活动/WBS、Infor LN PCS 项目、Epicor Project、D365 Project | **强化，不变** |
| 库存/采购要带任务维度 | IFS 项目连接供应、Infor LN 项目 pegging、SAP `Q`、Oracle task | **强化，不变** |
| 不建项目 BOM 表（D5） | 五家有项目级结构，但都靠"开关/复制"而非"全量快照"；平台工单快照等价 | **保持，但补开关语义** |
| 变更保持产品级 | IFS/Infor/Epicor 都是文档/物料级 ECO/revision | **强化，不变** |
| 成本只做派生视图 | IFS/Infor/Epicor 都是 Project/Job Costing + Estimate vs Actual | **强化，不变** |
| 采购先行、结构后到 | IFS 项目杂项需求、Infor LN 项目结构先生成、SAP PO→WBS | **强化，不变** |

### 6.2 唯一新增建议：项目"设计模式"开关

Infor LN 的 `Engineering Allowed` 给出一个精确模型：

- **engineered 项目**：项目拥有 customized item / BOM / routing，允许工程与项目级成本；
- **standard 项目**：只把物料挂到项目，结构仍用标准 BOM，不允许工程。

平台当前所有项目默认走 ETO 重流程。若未来出现"标准产品也按项目交付/核算"的场景，会需要这个开关。建议：

- P2 在 `projects` 增加 `design_mode`（`engineered` / `standard`），默认 `engineered`；
- `standard` 模式下：项目只做归集，不要求项目物料、不建工程结构；工单/采购/库存仍带 project/task；
- 这是**可选增强**，不影响 P1；不要在 P1 引入。

### 6.3 不该吸收的东西

1. **不要照搬 IFS 的"项目交付物"三层对象**（Deliverable → Deliverable Item → Project Operations）。平台没有交付物管理，三层会变成空壳。
2. **不要照搬 Infor LN 的"项目代码进物料编码"作为唯一路线**。平台已选项目物料路线，但应保留"标准件复用"的后路（即 6.2 的开关）。
3. **不要照搬 Epicor 的 Job 中心模型**。平台的工单已经是执行中心，再加 Job 会重复。
4. **不要引入 Infor/IFS 的 CPQ**。平台的 `configuration` 只服务 CTO，ETO 不做配置器。
5. **不要为了 D365 的"项目承载 ETO"而弱化制造**。平台的优势恰恰是制造与库存已打通。

---

## 7. G15 裁决更新（相对双雄对比稿）

| # | 决策 | 双雄稿结论 | 本稿校验 | 变化 |
|---|---|---|---|---|
| 1 | 项目 BOM 表 | 不建 | 五家有项目级结构，但都用开关/复制，非全量快照 | **不变**，补"开关"概念到 P2 |
| 2 | 任务轴 | P1 必做 | IFS/Infor/Epicor 全部以项目/活动/Job 为轴 | **不变，强化** |
| 3 | 库存任务维度 | P1 必做 | IFS 项目供应、Infor pegging、SAP `Q` | **不变，强化** |
| 4 | 采购先行 | P1 必做 | IFS 项目杂项需求、Infor LN 先生成项目结构 | **不变，强化** |
| 5 | 成本口径 | 单一派生视图 | 中端三家都是 Project/Job Costing + Estimate vs Actual | **不变，强化** |
| 6 | 变更归属 | 产品级 | IFS/Infor/Epicor 都是物料/文档级 ECO | **不变，强化** |
| 7 | 项目结构基线 | P2 指针 | IFS 项目交付物、Infor customized BOM 都可追溯到项目 | **不变** |
| 8 | 设计模式开关 | 无 | Infor LN `Engineering Allowed` | **新增（P2 可选）** |
| 9 | 项目交付物对象 | 无 | IFS 三层对象 | **不做** |
| 10 | CPQ / 配置器 | 不做 | Infor/IFS/Epicor 都有，但服务 CTO | **不做** |
| 11 | 项目会计 / RA | P3 | IFS/Infor/Epicor 有 Project Accounting，但平台无财务域 | **P3 再议** |
| 12 | DMS / PLM | 不做 | IFS 文档较强，Infor LN 有 EDM | **不做** |

---

## 8. 未核实项

1. **IFS Project Solution Overview PDF 的完整内容**：链接签名失效，只取到搜索摘要；项目专属 BOM 的完整规则未逐页核实。
2. **IFS 项目库存/项目 WBS 的完整字段**：只确认"项目连接供应"与"WBS 需求"，未核实库存隔离的字段级实现。
3. **Infor LN 的 PCS 项目成本细节**：只确认项目级成本计算开关，未核实 WIP / 收入确认。
4. **Infor CSI 的项目库存与项目成本**：产品页与伙伴资料为主，未取到官方字段级文档。
5. **Infor CSI 的 CPQ 成熟度**：二手评价，未逐项核实。
6. **Epicor Advanced Project Accounting 的收入确认方法**：官方页面有描述，未核实具体准则支持。
7. **D365 的项目库存/项目采购深度**：只确认"ETO 由项目承载"，未逐项核实供应链侧能力。
8. **各产品的许可与实施成本**：无可靠公开数据，本稿不给数字。

---

## 9. 参考来源

### IFS

- [I1] IFS Cloud Docs，*Create Item Operations*（Project Deliverables）— [页面](https://docs.ifs.com/ifsclouddocs/24r1/ProjectDeliverables/ActivityCreateItemOperations.htm)
- [I2] IFS Cloud Docs，*Connect Shop Order to Project Activity* — [页面](https://docs.ifs.com/ifsclouddocs/24r1/Manufacturing/ActivityConnectShopOrderToProjectActivity.htm)
- [I3] IFS Cloud Docs，*Material Requirements Planning* — [页面](https://docs.ifs.com/ifsclouddocs/25r2/lang/en/Planning/AboutMrp.htm)
- [I4] IFS，*IFS Cloud – Projects Solution Overview* — [PDF（签名链接，可能失效）](https://attachments-eu-west-1.insided.com/d7595261-d3fa-4e96-b3e7-3ae2fdbda579/IFS%20Cloud%20-%20Projects%20Solution%20Overview.pdf)
- [I5] IFS，*IFS Cloud Releases*（CPQ / Manufacturing / Service Projects）— [页面](https://www.ifs.com/en/ifs-cloud/releases)

### Infor

- [N1] Infor LN Docs，*Lean PCS projects* — [页面](https://docs.infor.com/ln/10.5/en-us/lnolh/help/ti/onlinemanual/000345.html)
- [N2] Infor LN Docs，*Generate (Budget PCS) Structure for Sales Quotations* — [页面](https://docs.infor.com/ln/10.4/en-us/lnolh/help/td/sls/tdsls1201m100.html)
- [N3] Infor LN Docs，*Projects*（Engineering Allowed）— [页面](https://docs.infor.com/ln/10.5.2/en-us/lnolh/help/ti/pcs/tipcs2101m000.html)
- [N4] Infor LN Docs，*Items*（Customized）— [页面](https://docs.infor.com/ln/10.5/en-us/lnolh/help/tc/ibd/tcibd0501m000.html)
- [N5] Infor LN Docs，*Production orders – functional overview* — [页面](https://docs.infor.com/ln/10.7/en-us/lnolh/help/ti/onlinemanual/000001.html)
- [N6] Infor，*Infor SyteLine / CloudSuite Industrial* — [页面](https://www.infor.cn/solutions/erp/syteline)
- [N7] Infor，*CloudSuite Industrial* — [页面](https://www.infor.cn/products/cloudsuite-industrial)
- [N8] essoft，*Infor CloudSuite Industrial (CSI)*（Estimate → 订单/工单）— [页面](https://www.essoft.com/products/cloudsuite-industrial-erp)

### Epicor / Microsoft

- [E1] Epicor，*Kinetic Project Management* — [页面](https://www.epicor.com/en-us/products/enterprise-resource-planning-erp/kinetic/project-management/)
- [E2] Epicor，*Kinetic Product Management*（Engineering Workbench / revision / ECO）— [页面](https://www.epicor.com/en/products/enterprise-resource-planning-erp/epicor-kinetic/product-data-management/)
- [E3] Epicor，*Make-to-Order Manufacturing* — [页面](https://www.epicor.com/en-us/solutions/industries/manufacturing/make-to-order/)
- [E4] Epicor，*Advanced Project Management* — [页面](https://www.epicor.com/vi-vn/products/epicor-financials/advanced-project-management/)
- [M1] Microsoft Learn，*Production process overview*（Dynamics 365 Supply Chain）— [页面](https://learn.microsoft.com/en-US/dynamics365/supply-chain/production-control/production-process-overview)

### 内部

- [X1] `spec-project-g15-eto-oracle-benchmark-2026-11-03.md`
- [X2] `spec-project-g15-eto-sap-benchmark-2026-11-04.md`
- [X3] `spec-project-g15-eto-oracle-vs-sap-2026-11-04.md`

---

## 附录：术语对照（跨产品）

| 概念 | Oracle | SAP | IFS | Infor LN | Infor CSI | Epicor | D365 |
|---|---|---|---|---|---|---|---|
| 项目 | Project | Project Definition | Project | PCS Project | Project | Project | Project |
| 任务/WBS | Task | WBS Element | Activity / WBS | Project Structure | Project Task（轻） | Project Phase | WBS |
| 项目级结构 | 项目物料 / effectivity | Order BOM / WBS BOM | Project Deliverable Item BOM | Customized BOM | Estimate/Job BOM | Job BOM | 标准 BOM 为主 |
| 结构复制开关 | 项目物料 / unit | BOM 类别 | Use Project Operations | Engineering Allowed | 从 Estimate/工单复制 | Job 生成复制 | 无显式 |
| 执行单元 | Work Order | Production Order | Shop Order | Production Order | Job / Work Order | Job | Production Order |
| 变更 | Change Order | Change Master | Change Management | ECO | ECO | ECO / Workbench | 工程变更 |
| 成本 | Expenditure | PS + CO | Project Cost | PCS Cost | Job Cost | Job Cost | Project Operations |
| 配置 | CPQ | VC | IFS CPQ | Config Management | Infor CPQ | Epicor CPQ | Product Config |
