# 研究稿：ETO（按单设计）头部产品研究 — SAP 专题

- 文档版本：v0.1
- 日期：2026-11-04
- 状态：研究稿（仅研究，**尚未实施**）
- 关联文档：
  - `spec-project-g15-eto-oracle-benchmark-2026-11-03.md`（Oracle 专题 v0.1）
  - `spec-project-g4-engineering-bom-2026-11-03.md`（G4 工程 BOM / ECM，v1.4）
  - `spec-routing-process-manufacturing-benchmark-2026-11-01.md`（P5 工艺路线研究稿）
- 研究范围：SAP S/4HANA（on-premise / Cloud）的 ETO 组合；ECC 仅作历史对照。横向只与 Oracle 对比，不展开 IFS / Epicor。

---

## 0. 结论摘要（先看这里）

1. **SAP 也没有一个叫 ETO 的独立产品。** ETO 在 SAP 中是**以项目系统（PS）为中心的集成方案**：SD（销售订单/WBS）+ PS（项目/WBS/网络）+ PP（BOM/工艺/生产订单）+ MM（项目库存/采购）+ LO-ECM（变更）+ DMS（文档）+ CO（成本/WIP/结算）。SAP 官方材料把它表述为 `project business` / `engineer-to-order` / `design-driven enterprise`。
2. **SAP 与 Oracle 最大的分歧：SAP 有项目级 BOM，Oracle 没有。** SAP 的 BOM 体系里明确存在 **Order BOM（销售订单 BOM）** 和 **WBS BOM（生产批次 BOM，按 WBS 元素）**；Oracle 只有物料级结构 + effectivity + 项目引用。这是本轮研究对 G4 D5 最有价值的反证。
3. **SAP 的项目库存按 WBS 元素隔离，不按项目头隔离。** 特殊库存标识 `Q`（project stock）绑定到 WBS 元素；组件只能为该 WBS 发料；支持有估值 / 无估值两种模式。这意味着"项目库存"的粒度实际是**任务级**，不是项目级。
4. **变更管理与 Oracle 同构：产品级 + 生效控制。** SAP 用 change number（change master record）+ valid-from + parameter effectivity + release key；变更前后两态都留痕。**变更单不按项目建**，项目影响靠对象清单和 where-used 查。
5. **SAP 的 ETO 成本闭环比 Oracle 更"会计化"。** 成本先落 PS（WBS），期末用 **results analysis（RA）** 区分 WIP / COGS / 收入，再 settlement 到 WBS / 资产 / COGS；Oracle 是 Expenditure Item 事实源 + burden/capitalization/billing。
6. **SAP 的 ETO 前端（报价/估算）同样不是开箱即用。** 官方 ETO 材料把 bid / quotation costing 作为流程起点，但工程估算、技术结构（TOS）、多专业设计仍要 PLM / 第三方（如 ECTR / Teamcenter）补齐。
7. **SAP 的 BOM 是"分阶段成熟"的。** ETO 允许项目开始时 BOM 不完整：先建项目/长周期采购，再逐步补 BOM、按 production lot 下达。对应 Oracle 的 structure effectivity + change order。
8. **对平台 G15 的修正（相对 Oracle 稿）：**
   - D5（不建项目 BOM 表）**仍建议保留**，但理由从"Oracle 也没有"改为"平台用工单组件快照 + 结构基线指针即可覆盖 SAP order BOM / WBS BOM 的业务效果"；
   - **库存项目维度应落在 WBS/任务级**（`project_task_id`），仅 `project_id` 不足以表达 SAP/Oracle 的项目库存语义；
   - 采购同样要能"项目/任务先行、BOM 后到"，长周期件先于设计完成下单；
   - 成本维持"单一派生视图"，但口径要按 **项目 + 任务双层** 汇总。
9. **G15 最小闭环基本不变：** 项目物料 + 工程结构 + ECM 发布 + 项目工单（project/task）+ 项目采购/库存引用 + 派生项目成本。SAP 的 RA / settlement / PMMO / 生产批次属于后续专题。
10. **一句话：** Oracle 教我们"对象边界"，SAP 教我们"WBS 是唯一归集轴"。平台两样都缺一半：对象边界基本对，WBS/任务轴还没打通。

---

## 1. 研究方法与证据强度

| 证据 | 来源 | 强度 | 用途 |
|---|---|---|---|
| SAP Help（Project Stock，MM-IM） | SAP 官方文档镜像（原文来自 SAP Help Portal） | 强 | 项目库存 `Q` 标识、WBS 绑定、有/无估值 |
| SAP Help（BOM Categories，PP-BD-BOM） | SAP 官方文档镜像 | 强 | Material / Order / WBS BOM 的定义与边界 |
| SAP Help（DMS 中的 ECM） | SAP 官方文档镜像 | 强 | change number 与文档信息记录（DIR）联动 |
| SAP 官方《Design-Driven Enterprise — From Bid to Design & Procurement》(2022) | `assets.dm.ux.sap.com` 官方 PDF | 强 | ETO 阶段划分、as-projected / as-designed / as-built 结构 |
| SAPinsider《Complete the ETO Process with Period-End Postings for Project Valuation》 | 行业媒体（引 SAP 顾问实践） | 中 | PS 成本、results analysis、WIP/COGS/收入 |
| SAPinsider《Changing Production Master Data with ECM》 | 行业媒体 | 中 | change master、parameter effectivity、release |
| Noveco《Project Manufacturing (ETO) in SAP》 | SAP 合作伙伴白皮书 | 中 / 低 | ETO 财务诉求与估算范围 |
| RevTech《SAP PMMO》 | 咨询公司解读 | 中 / 低 | PMMO 的分组 / 溯源 / 分摊 |
| SAP PS WBS Element 讲义页 | 第三方培训资料 | 低 | WBS 作为成本/收入归集单元 |
| 平台 schema / 迁移 / ECM 实现 | 本仓库代码 | 强 | 现状盘点与差距判断 |

> 说明：凡"官方文档明确"仅指上表前四项；其余标注为二手，不进入 G15 设计依据的硬约束。

---

## 2. SAP 的 ETO 定位

### 2.1 定义与特征

SAP 的 ETO 场景与 Oracle 一致：**订单后才设计、工程在关键路径、每单独立核算**。SAP 合作伙伴材料把它拆成四条工程特征：

- 最终产品唯一，由标准件 + 自制件 + 客户专用组件构成；
- 客户需求带来高强度工程活动；
- 估算基于标准组件成本 + 工程成本 + 制造成本；
- **项目启动时最终设计可能尚未完成**，最终成本可能因设计变更或制造失误偏离初始估算。

最后一条是 SAP 与 MTS/MTO 的本质差异，也是"BOM 分阶段成熟"的来源。

### 2.2 ETO / MTO / ATO / CTO 在 SAP 中的落点

| 模式 | SAP 落点 | 关键对象 |
|---|---|---|
| MTS | 标准物料 + 计划策略 10/40 + 生产订单 | Material、Production Order |
| MTO | 计划策略 20 + 销售订单库存（`E`） | Sales Order、Individual Stock |
| ATO | 计划策略 40/45 + 变式配置 + 装配处理 | Configurable Material、VC、Assembly Processing |
| CTO | VC + 超级 BOM + 配置剖面 + 可选工艺 | Super BOM、Class 300、Object Dependencies |
| **ETO** | **销售订单 → WBS / 项目 → 订单 BOM / WBS BOM → 生产订单 → 项目库存 → 项目结算** | **PS、WBS、Order BOM、WBS BOM、Project Stock、CO-PC** |

关键判断：

- SAP 的 ATO/CTO 复用对象是**可配置物料 + 超级 BOM**；ETO 复用对象是**标准组件 + 工程能力**，不是预定义配置。
- SAP 的同厂 mixed-mode 靠 **requirement class / requirement type** 切换：同一物料按不同需求类型走库存、走销售订单库存、走项目库存。
- 平台已有 `configuration` 系列对象，只能对标 CTO；ETO 不应扩成配置器。

### 2.3 SAP 的用词

- `Engineer-to-Order`、`Project Business`、`Design-Driven Enterprise`、`Project Manufacturing`。
- `Order BOM`（销售订单 BOM）、`WBS BOM`（生产批次 BOM）、`Project Stock`（项目库存）。
- 产品化的 ETO 增强是 **SAP PMMO（Project Manufacturing Management and Optimization）**，属于附加许可，不是标准 PP 的一部分。

---

## 3. SAP 产品矩阵：ETO 是集成，不是模块

| 层次 | SAP 组件 / 能力 | 在 ETO 中的角色 | 关键对象 |
|---|---|---|---|
| 商机与报价 | SD（询价/报价）、Quotation Costing | 报价与初步估算 | Inquiry、Quotation、Costing Sheet |
| 项目与合同 | PS（Project System） | 项目定义、WBS、网络、里程碑、预算 | Project Definition、WBS Element、Network、Milestone |
| 产品定义 | PP-BD-BOM、PLM、DMS | 物料 BOM / 订单 BOM / WBS BOM、文档 | Material、BOM、Document Info Record（DIR） |
| 工艺定义 | PP-BD-RTG | 工艺路线、工作中心、产能 | Routing、Work Center、Capacity |
| 变更 | LO-ECM | change number、生效、发布 | Change Master、Object Management Record |
| 生产执行 | PP（Production Order / Process Order） | 生产订单、确认、发料、完工 | Production Order、Confirmation |
| 库存与采购 | MM-IM / MM-PUR | 项目库存（`Q`）、项目采购 | Special Stock `Q`、PO Account Assignment `Q` |
| 成本 | CO-PC、CO-OM、CO-PA | 成本估算、WIP、差异、results analysis、结算 | Cost Estimate、WIP、RA、Settlement |
| 计划 | MRP、Project MRP、PMMO | 项目维度需求/供应、跨项目分组 | Planned Order、Grouping WBS |
| 质量 | QM | 检验、不合格 | Inspection Lot |
| 文档 | DMS / ECTR | 图纸、规范、变更联动 | DIR、Class、Change Number |

**一句话：** SAP 的 ETO 是"把 SD 的订单、PS 的 WBS、PP 的 BOM/工艺、MM 的项目库存、CO 的项目成本串成一条轴"，这条轴的名字叫 **WBS 元素**。

---

## 4. SAP 机制逐域

### 4.1 销售订单与项目：WBS 是入口

- 销售订单行项目可做 **account assignment** 到 WBS 元素；该 WBS 可以是 billing element（收入归集）或 account assignment element（成本归集）。
- **Assembly Processing** 可以从销售订单直接生成项目 / 网络活动，减少手工建项。
- **Requirement class / requirement type** 决定该行是否产生项目库存、是否进入项目成本、是否触发装配。
- 多行订单可拆到不同 WBS（按交付批次、按子系统）。
- 平台对应：`sales_order` 有 `project_id`，但**没有行级 WBS 归属**，也没有"订单生成项目/任务"的入口。

### 4.2 项目系统（PS）：WBS 是唯一归集轴

SAP PS 的核心对象：

| 对象 | 作用 |
|---|---|
| Project Definition | 项目头（工厂、计划工厂、日期、项目类型） |
| WBS Element | 层级节点；成本 / 收入 / 预算 / 结算的归集单元 |
| Network / Activity | 作业网络；与生产订单、采购、能力衔接 |
| Milestone | 里程碑；billing / 进度确认 |
| Budget / Availability Control | 预算与超支控制 |
| Settlement Rule | 结算规则（到 WBS / 资产 / COGS / 成本中心） |

SAP 的 WBS 类型（对平台最有用）：

- **billing element**：承接收入、开票计划；
- **account assignment element**：承接成本、采购、生产订单；
- **planning element**：只做计划与汇总，不直接过账。

平台对应：`project_tasks` 已有 WBS 层级、`task_type`、状态机；`projects.budget_amount` 只有项目级预算，**没有任务级预算/可用性控制，也没有 billing/account assignment 的类型区分**。

### 4.3 BOM：SAP 有四种与 ETO 相关的 BOM

SAP 官方 BOM 分类里，与 ETO 直接相关的有四种：

| BOM 类型 | 参照对象 | ETO 用途 | 官方要点 |
|---|---|---|---|
| **Material BOM** | 物料 | 标准件、通用组件 | 标准结构，可复用于多项目 |
| **Order BOM（销售订单 BOM）** | 物料 + 销售订单 + 行项目 | 为某张订单定制的结构 | 订单相关的新建/修改 BOM 按"物料 + 订单 + 行项"保存 |
| **WBS BOM（生产批次 BOM）** | WBS 元素（生产批次号） | 为某个生产批次/项目阶段定制结构与成本 | 生产批次号就是 PS 的 WBS 元素；用于计划/制造并计算计划与实际成本 |
| **Variant BOM / Super BOM** | 可配置物料 | CTO / ATO | 超级 BOM 含全部可能组件，按配置筛选 |

关键结论：

1. **SAP 确实有项目级（更准确说订单级 / 批次级）BOM。** Order BOM 锚在销售订单行，WBS BOM 锚在 WBS 元素。这是 SAP 与 Oracle 最大的结构性差异。
2. **SAP 的 Order BOM 不是"复制一份完整 BOM"那么容易。** 它按"物料 + 订单 + 行项"保存差异；只有被改动/新建的装配才有订单 BOM 记录，未改动的仍走物料 BOM。
3. **WBS BOM 的粒度是生产批次，不是整个项目。** 一个项目可以有多个 WBS BOM（多个批次/多个子系统）。
4. **平台现状**：`item_structures` 无 `project_id`；`work_order_components` 是工单级快照。平台相当于"只有物料 BOM + 执行快照"，缺"订单/批次级可编辑结构"。

### 4.4 工艺路线与生产版本

- Routing 挂物料 + 工厂，按工序/工作中心/工时定义；支持可选工序、替代工序。
- **Production Version** 把 BOM + Routing 组合成一个可下达版本，按批量/有效期选择。
- ETO 的工艺差异通常通过：订单 BOM 对应工艺、可选工序、或在生产订单中改工序实现。
- 平台对应：`work_definitions` + `production_versions` 已有版本与生效日；缺"项目/批次维度的工艺差异化"。

### 4.5 变更管理（LO-ECM）：产品级 + 生效控制

SAP ECM 的机制（官方 + 行业资料一致）：

- **Change Master Record（change number）**：变更主记录，含 valid-from、变更原因、对象类型。
- **Parameter Effectivity**：除日期外，可用生效参数（如序列号、批次、订单）控制生效；生效类型在定制中定义。
- **Release Key**：把变更"发布"到特定功能域（例如只放给成本，不放给生产），实现"先算成本、后投产"。
- **Revision Level**：物料主数据上的版本级别，由 change number 控制；BOM 行也可带 revision。
- **Object Management Record**：记录被变更的对象（物料、BOM、工艺、文档）。
- **变更前后两态留痕**：系统保存变更前与变更后状态，可随时追溯。
- **DMS 联动**：文档信息记录（DIR）的基本数据里填 change number，valid-from 给文档一个时间参照；图纸/规范与物料、BOM、工艺一起被变更单管理。

与 Oracle 的差异：

| 维度 | SAP | Oracle |
|---|---|---|
| 变更对象名 | Change Master / Change Number | Change Order / ECO |
| 生效方式 | valid-from + parameter effectivity + release key | effective date + model/unit effectivity |
| 版本 | revision level（物料主数据） | revision（结构/工作定义） |
| 项目归属 | 无（产品级） | 无（产品级） |
| 文档联动 | DIR + change number | attachment / redline |

平台对应：`engineering_changes` + lines + 审批 + apply 已有；缺 parameter effectivity、release key 语义、revision 自动算。

### 4.6 项目库存（MM-IM）：按 WBS 元素隔离

SAP 官方定义（Project Stock）：

- 项目库存是"为完成项目而持有的物料数量"，**分配给 WBS 元素**；
- **组件只能为该 WBS 元素领用**；
- 支持**有估值**与**无估值**两种：
  - 无估值：通过成本收集器管理，收货时不产生发票校验过账，期末才能看到估值；
  - 有估值：FI 立即可见，收发即过账；
- 从 MRP 角度，项目库存对项目"可用"；
- 特殊库存标识 **`Q`**；手工移动需带 `Q` + WBS 元素；
- 采购订单若 account assignment 为项目，收货时系统**自动带出 `Q`**；
- 支持项目库存 → 项目库存的转移过账、转自有库存、库存调拨。

关键结论：

1. **项目库存的隔离键是 WBS 元素（任务级），不是项目号。** 一个项目多个 WBS，就有多个库存段。
2. **有估值 / 无估值是财务口径选择，不是技术实现差异。** ETO 通常选有估值，便于 WIP 与成本实时。
3. **跨 WBS 领料默认被禁止。** 需要显式转移或跨项目费用处理。
4. 平台现状：`inventory_transactions` / `inventory_balances` 无项目维度；`inventory_balances` 唯一键是 `(org, location, item, batch, stock_status)`。若要复刻 SAP，需要 `(org, location, item, batch, stock_status, project_task_id)`。

### 4.7 生产执行：生产订单 / 生产批次

- **Production Order**：按物料 + 工厂 + 数量下达；可带 WBS 结算规则；发料、确认、收货都归集到 WBS。
- **Production Lot（生产批次）**：ETO 的典型做法，批次号即 WBS 元素；配合 WBS BOM 做批次级结构与成本。
- **Process Order**：流程行业等价物。
- **Backflush / Confirmation**：按工序倒冲与报工；与平台 `work_order_components` + 报工模型对应。
- 平台对应：`work_orders` 有 `project_id`；缺 `project_task_id`（WBS）与结算规则。

### 4.8 成本：PS 归集 + Results Analysis + Settlement

SAP 的 ETO 成本闭环：

```
采购 / 生产订单 / 工时 / 外协
        ↓（account assignment）
      WBS Element（成本归集）
        ↓（期末）
  Results Analysis（RA）：WIP / COGS / 收入确认
        ↓（Settlement）
  WBS / 固定资产 / COGS / CO-PA
```

要点：

- 成本在 ETO 环境里先落 PS，进入 P&L；期末用 **results analysis** 计算 WIP、COGS 与收入，保证跨期项目的财务报表正确。
- **有估值项目库存**让物料价值实时进 FI；无估值则通过成本收集器，期末才结算。
- **Product Costing** 可按销售订单 / WBS 做估算，BOM + Routing 是成本估算的基础；估算随设计成熟多次重算。
- **Settlement Rule** 决定成本最终去向（WBS、资产、COGS、利润中心）。
- 平台对应：只有 `v_project_task_labor` 工时回聚 + `projects.budget_amount`；缺 WIP、RA、结算规则、任务级成本汇总。

### 4.9 计划：项目 MRP 与 PMMO

- **MRP** 可按 WBS 账户分配跑需求；计划订单带 WBS，收货进项目库存。
- **Project MRP**：项目维度的需求/供应计划。
- **PMMO（附加许可）**：
  - **Grouping**：把多个 WBS（可跨项目）的需求合并到一个 grouping WBS，统一采购/生产，拿到批量经济性；
  - **Pegging**：把合并后的供应按数量回挂到各原始 WBS，保证成本可追溯；
  - **Distribution**：按 pegging 把供应/成本分摊回各项目。
- 这条能力解决"集中采购 vs 单项目成本"的矛盾，是 SAP 在大型 ETO 上的差异化。
- 平台 G15 不做项目 MRP / PMMO；但**"长周期件先采购、BOM 后到"** 是 P1 就要支持的。

### 4.10 CTO 边界

- **VC（Variant Configuration）**：可配置物料 + Class 300 特征 + 超级 BOM + 对象依赖 + 配置剖面；订单配置生成配置物料/配置 BOM。
- **Advanced Variant Configuration** 是 S/4HANA 的增强版本。
- ETO 与 CTO 的边界同 Oracle：ETO 没有预定义选项，不能靠配置器；CTO 不能替代工程设计。
- 平台 `configuration` 只服务 CTO，G15 不碰。

---

## 5. SAP 端到端 ETO 流程

| 阶段 | 业务动作 | SAP 对象 / 事务 | 关键控制 | 平台对应 | 差距 |
|---|---|---|---|---|---|
| 1. 询价 / 报价 | 相似项目估算、长周期询价 | Inquiry、Quotation、Quotation Costing | 报价版本、毛利率 | 无报价对象 | G15 不做 |
| 2. 接单 / 建项 | 销售订单 → WBS / 项目 | Sales Order、Project Definition、WBS | 需求类型、账户分配、billing element | `sales_order.project_id`、`projects`、`project_tasks` | 订单行→WBS 归属 |
| 3. 项目规划 | WBS 细化、网络、里程碑、预算 | WBS、Network、Milestone、Budget | 预算/可用性控制、结算规则 | `project_tasks`、`budget_amount` | 任务级预算、结算规则 |
| 4. 初步设计 / 长周期采购 | 建项目 BOM / 订单 BOM；先采购长周期件 | Material BOM、Order BOM、PO→WBS | 设计未完成也可采购 | `item_structures(usage=engineering)`、`purchase_order.project_id` | 订单/批次级 BOM、任务级采购 |
| 5. 设计变更 | change number、parameter effectivity、release | Change Master、Object Mgmt Record、DIR | valid-from / release key / revision | `engineering_changes` + apply | 生效参数、release、revision 自动算 |
| 6. 工艺与生产准备 | Routing、Production Version、WBS BOM | Routing、Production Version、WBS BOM | 版本/批量/有效期 | `work_definitions`、`production_versions` | 批次级结构/工艺 |
| 7. 生产执行 | 生产订单 / 生产批次，发料、确认、收货 | Production Order、Production Lot | WBS 结算、项目库存 | `work_orders.project_id` | `project_task_id`、结算规则 |
| 8. 项目库存 | 收货入 `Q`、按 WBS 领用、项目间转移 | Special Stock `Q` | 有/无估值、跨 WBS 禁止 | `inventory_transactions` / `inventory_balances` | 项目/任务库存维度 |
| 9. 交付 / 开票 | 发货、billing element、开票计划 | Delivery、Billing Plan | 里程碑开票、收入确认 | `shipment.project_id` | 开票计划、收入确认 |
| 10. 期末 / 结算 | WIP、RA、差异、settlement | CO-PC、RA、Settlement | WIP/COGS/收入 | 无 | 整体后置 |
| 11. 售后 / 服务 | 服务订单、备件 | Service Order、PM | 项目/合同 | 无 | G15 不做 |

---

## 6. SAP 的关键设计取舍

| 决策 | SAP 做法 | 优点 | 代价 | 对平台 G15 |
|---|---|---|---|---|
| 项目 BOM 是否独立 | **建 Order BOM / WBS BOM**（订单级 / 批次级） | 设计与执行解耦；批次级成本清晰 | 主数据多、维护成本高、跨订单复用弱 | **P1 不建**；用工单快照 + 基线指针覆盖 |
| 项目库存粒度 | **WBS 元素**（任务级） | 成本/库存同轴，隔离彻底 | 库存段碎片化；跨 WBS 需显式转移 | 库存维度用 `project_id + project_task_id` |
| 变更归属 | 产品级 change number | 变更可复用、可审计 | 项目影响需查询 | ECM 保持产品级 |
| 生效控制 | 日期 + parameter effectivity + release key | 支持序列号/批次/分域发布 | 定制复杂 | P1 日期；P3 再评估 |
| 成本事实源 | PS 归集 + CO 结算 | 会计闭环完整 | 需要 CO 全套 | 先派生视图，后补 |
| 计划 | MRP + Project MRP + PMMO | 大规模 ETO 可合并采购 | 许可与实施重 | 首期只做项目采购先行 |
| 估算 | Quotation Costing + Product Costing | 报价可核 | 依赖 BOM 成熟度 | G15 不做 |
| ETO vs CTO | 两条路径，requirement type 切换 | 同厂 mixed-mode | 配置复杂 | 只做 ETO |

---

## 7. Oracle vs SAP 的正面对比

| 维度 | Oracle Fusion / EBS | SAP S/4HANA | 对平台的含义 |
|---|---|---|---|
| **项目 BOM** | 无项目 BOM 表；靠项目物料 / model-unit effectivity | **有 Order BOM / WBS BOM** | 平台可选"轻量折中"：不建表，但保留基线指针 + 工单快照 |
| **项目库存隔离粒度** | 项目 / 任务（PJM 可选 Project 或 Task 控制级别） | **WBS 元素（任务级）** | 平台库存维度应到任务级 |
| **项目库存标识** | 项目库存维度 / project locator | 特殊库存 `Q` | 平台用 `project_id + project_task_id` 字段 |
| **估值** | PDSC 项目成本 + Expenditure | 有估值 / 无估值项目库存 | 平台只做派生视图，先不碰库存估值 |
| **变更单** | Change Order / ECO + redline + effectivity | Change Master + parameter effectivity + release key | 平台 ECM 已接近 Oracle 形态，补参数生效可选 |
| **变更归属** | 产品级 | 产品级 | 一致，保持 |
| **成本事实源** | Expenditure Item（Task 粒度） | PS WBS + CO settlement（WBS 粒度） | 一致：任务级；平台补任务级汇总 |
| **期末处理** | burden / capitalization / billing | Results Analysis + Settlement | 平台后置 |
| **配置能力** | CPQ / ATO / configured item | VC / 超级 BOM / 装配处理 | 平台 `configuration` 只做 CTO |
| **计划增强** | PDSC planning | Project MRP + PMMO（分组/溯源/分摊） | 平台后续专题 |
| **文档** | PLM attachments / DMS | DMS DIR + change number | 平台不做 DMS |
| **前端报价** | CPQ 偏 CTO，ETO 需估算补齐 | Quotation Costing，深度仍靠 PLM | G15 不做 |

**结论：** 两家头部产品在"变更产品级、成本任务级、库存按任务隔离"上高度一致；分歧只在**是否把项目结构做成主数据对象**。平台规模小，D5 的"不建项目 BOM 表"仍成立，但必须补上"任务轴"。

---

## 8. 对平台 G15 的落点建议（相对 Oracle 稿的修正）

### 8.1 D5 重新评估：保留，但改理由

Oracle 侧：无项目 BOM 表 → D5 成立。
SAP 侧：**有 Order BOM / WBS BOM** → 说明"项目 BOM"在头部产品里不是伪需求。

但 SAP 的 Order BOM 是"按订单行保存差异"，WBS BOM 是"按生产批次"，二者都服务于**设计与执行解耦**。平台已有的 `work_order_components` 是工单级快照，等价于"执行时冻结结构"，只是缺少"下达前可编辑的项目结构"。

因此建议：

- **P1 保持 D5**：不建项目 BOM 表、不给 `item_structures` 加 `project_id`。
- **P2 增加指针表**：`project_structure_baseline(project_id, task_id, structure_id, revision, purpose, captured_at)`，只存指针，用于合同基线 / 设计冻结对比。
- **P3 再评估**：若出现"同一项目多批次、每批次结构不同、且必须在下达前编辑"的真实需求，再讨论 WBS 级结构；不要提前建表。

### 8.2 分层落地

#### P1：最小闭环（在 Oracle 稿基础上补 2 个修正）

1. **项目物料**（不变）
   - 一项目一物料：`item.code = <project_no>-<seq>`；可选 `items.project_id` 仅检索。
   - 不建 `project_item` 表，不给 `item_structures` 加 `project_id`。

2. **工程结构 → 生产结构**（不变）
   - 项目物料建 `usage=engineering` 结构；ECM apply 到 `usage=production`。
   - 初次建 BOM 可直接建生产结构，后续变更走 ECM。

3. **项目工单**（补强）
   - 复用 `work_orders.project_id`。
   - **新增可空 `project_task_id`**（WBS），服务层校验 project/task 一致。
   - 支出字段首期不落库；如落库保持可空。

4. **项目库存（修正粒度）**
   - `inventory_transactions` / `inventory_balances` 增可空 `project_id` **与 `project_task_id`**。
   - 余额唯一键：`(org_id, location_id, item_id, batch_id, stock_status, project_id, project_task_id)`，空值用 0 哨兵。
   - 有项目归属时，发料必须校验 WBS 一致（复刻 SAP"只能为该 WBS 领用"）。
   - 首期不做有/无估值切换；库存估值仍按现有成本口径。

5. **项目采购（补强）**
   - `purchase_order` / `receipt` / `transfer_order` 补 `project_task_id`。
   - **允许"项目/任务先行、BOM 未完成即下单"**：采购行只要求 project/task，不要求结构存在；这是 ETO 长周期件的刚需。
   - 收货 → 入库事务 → 余额 三级都要带项目/任务，避免入库丢归属。

6. **项目成本（修正口径）**
   - 单一 `v_project_cost` 派生视图，按 **project + task 双层** 汇总：
     - 人工：`time_entries` → 项目任务工时；
     - 采购：带 project/task 的收货/发票金额；
     - 制造：带 project/task 的工单工时 + 领料。
   - 只做"预算 vs 实际"；预算含项目级（现有）与任务级（新增可空字段或汇总规则）。

7. **ECM 项目影响**（不变）
   - 影响预览加"受影响项目物料 / 在途项目工单"过滤；
   - 不给 `engineering_changes` 加 `project_id`。

#### P2：增强

- **项目结构基线指针表**（见 8.1）。
- **项目库存台账 / locator**：项目库存查询、项目间转移、项目 ATP。
- **任务级预算与可用性控制**：对标 SAP availability control。
- **长周期齐套**：项目采购齐套、关键件到货预警。
- **项目变更影响联合查询**：where-used + 项目引用 + 在途工单。

#### P3：可选 / 后续专题

- **参数生效 / release key**：序列号、批次生效；变更分域发布（成本 / 生产）。
- **WBS 级结构（批次 BOM）**：仅在真实需求出现时评估。
- **As-built genealogy**：工单快照 + 序列号 + 批次。
- **Results Analysis / WIP / Settlement**：财务域专题。
- **项目 MRP / PMMO 类分组采购**：计划域专题。
- **项目排程 / 产能**。

### 8.3 明确不建

- 独立 ETO 模块；
- 项目 BOM 表（P1/P2 均不建，只建指针）；
- 项目专用工作定义表；
- CPQ / ETO 设计器；
- CAD / PDM / DMS；
- 完整项目会计（WIP / RA / settlement / 开票）；
- 项目维度的主数据复制；
- PMMO 式的跨项目分组/溯源/分摊。

### 8.4 验收场景

| 场景 | 步骤 | 通过标准 |
|---|---|---|
| A. 新项目定制件 | 建项目/任务 → 建项目物料 → 工程结构 → ECM 发布 → 建项目工单（project+task）→ 领料 → 完工入项目库存 → 项目成本视图 | 项目/任务/物料/工单/库存/成本全链路可追；非项目库存不受影响 |
| B. 长周期件先行 | BOM 未完成时按 project/task 下采购单 → 收货入项目库存 → 后期补 BOM 并下达工单 | 采购与收货不因结构缺失被阻断；库存归属正确 |
| C. 设计变更 | 改工程结构 → ECM 影响预览显示项目与在途工单 → 审批 → apply → 新工单取新版本 | 旧工单不被静默改版；项目维度正确 |
| D. 跨任务隔离 | 同一项目两个 WBS 各领同一物料 | 两任务库存不混、成本不串；跨任务领用被拒或需显式转移 |
| E. 标准件跨项目 | 同一标准 item 供两个项目 | 项目库存不混；BOM 不被复制 |

### 8.5 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 库存维度膨胀 | 增加 project/task 后唯一键变长、碎片化 | 空值 0 哨兵；先事务后余额；按需建索引 |
| 任务轴缺失 | 只有 project_id 时无法复刻 SAP/WBS 语义 | P1 就补 `project_task_id`，不要推迟 |
| 主数据膨胀 | 一项目一物料 | 命名规范 + 项目结束归档 |
| 成本双真源 | 采购/库存/工单各算一套 | 单一 `v_project_cost`，明确口径 |
| 结构基线被误用成项目 BOM | 指针表被扩成结构副本 | 表只存指针；禁止存行数据 |
| 变更被项目化 | 变更单挂 project_id | 保持产品级；项目只做查询维度 |
| 采购先行被滥用 | 无结构采购导致错料 | 强制 project/task + 采购类别校验 |

---

## 9. 横向定位（更新 Oracle 稿 §9）

| 产品 | ETO 定位 | 强项 | 弱项 / 代价 |
|---|---|---|---|
| **SAP S/4HANA** | PS 为中心的集成 ETO | 项目 BOM（订单/WBS）、项目库存按 WBS、成本会计闭环、PMMO 大规模项目制造 | 实施重、许可贵、前端报价仍需 PLM/第三方 |
| **Oracle Fusion** | 组合式 ETO：PLM + Manufacturing + PDSC + Project Financials | 项目化供应链、项目库存/采购/成本、制造执行完整 | 无项目 BOM；模块多、集成重 |
| **Oracle EBS** | Engineering + BOM + PJM + Projects | 工程/制造 BOM 边界清晰、PJM 成熟 | 技术栈老、迁移成本 |
| **IFS Cloud** | 工程 + 文档 + 项目 + 制造一体化 | ETO 原生感强、文档/变更协同 | 大型集团深度不如 SAP/Oracle |
| **Epicor / NetSuite** | 中端 ETO / job shop | 上手快、轻量 | 复杂项目与长周期不足 |

> 结论：SAP 是"项目化制造 + 项目会计"最完整的头部产品；Oracle 是"项目化供应链 + 制造执行"最完整。平台 G15 应学 SAP 的**WBS 归集轴**、学 Oracle 的**对象边界**，不学任何一家的模块数量。

---

## 10. 未核实项与后续研究

1. **SAP Best Practices 中 ETO 的 scope item 编号**：未确认（搜到的编号均不可靠），不作为证据。
2. **Order BOM 的完整复制/差异规则**：官方只说明"按物料+订单+行项保存"，未核实未改动装配是否完全不产生订单 BOM 记录。
3. **WBS BOM 与 Production Lot 的强绑定关系**：官方说明批次号即 WBS 元素，但未核实是否所有 WBS BOM 都必须建生产批次。
4. **PMMO 的许可与版本形态**：仅二手资料，未核实 S/4HANA 公有云是否提供。
5. **Results Analysis 的完整方法与配置**：只确认它在 ETO 期末估值中的角色，未展开 POC/成本法差异。
6. **VC 与 ETO 的混合使用边界**：仅确认 VC 服务 CTO；未核实 SAP 是否允许 ETO 订单复用 VC 生成部分结构。
7. **SAP 公有云与 on-premise 的 ETO 能力差异**：本稿以通用 S/4HANA 能力为主，未逐项对照 Cloud 范围。
8. **SAP 与 Oracle 在序列号/单元生效上的差异**：SAP 用 parameter effectivity + serial number，Oracle 用 model/unit number；未做逐字段对照。

---

## 11. 参考来源

### SAP 官方 / 官方文档镜像

- [S1] SAP Help，*Project Stock*（MM-IM）— [镜像页](https://help.freedsap.com/ENHELPhtml/MMIM/ProjectStock.html)
- [S2] SAP Help，*BOM Categories*（PP-BD-BOM）— [镜像页](https://help.freedsap.com/ENHELPhtml/PPBDBOM/BOMCategories.html)
- [S3] SAP Help，*Engineering Change Management in Document Management* — [镜像页](https://help.freedsap.com/ENHELPhtml/CADMS/EngineeringChangeManagementinDo1.html)
- [S4] SAP，*Design-Driven Enterprise — From Bid to Design & Procurement*（2022 官方 webinar PDF）— [PDF](https://assets.dm.ux.sap.com/eur-digitalsupplychain-hub/pdfs/2022_webinar04_eto_14.04.2022.pdf)

### 行业 / 二手

- [S5] SAPinsider，*Complete the Engineer-to-Order Process with Period-End Postings for Project Valuation* — [文章](https://sapinsider.org/complete-the-engineer-to-order-process-with-period-end-postings-for-project-valuation/)
- [S6] SAPinsider，*Customize Your Logistics and Finance Processes by Changing Production Master Data with ECM* — [文章](https://sapinsider.org/articles/customize-your-logistics-and-finance-processes-by-changing-production-master-data-with-ecm/)
- [S7] Noveco Solutions，*Project Manufacturing (Engineer To Order) in SAP* — [PDF](https://www.novecosystems.com/pdf/ETO_Project_Manufacturing_HL_Overview.pdf)
- [S8] RevTech，*SAP Project Manufacturing Management & Optimization (PMMO)* — [文章](https://revtech.consulting/insights/sap-pmmo)

### 内部研究

- [S9] `spec-project-g15-eto-oracle-benchmark-2026-11-03.md` — Oracle ETO 研究稿
- [S10] `spec-project-g4-engineering-bom-2026-11-03.md` — G4 ECM / D5 / G15 边界
- [S11] `spec-routing-process-manufacturing-benchmark-2026-11-01.md` — P5 工作定义 / 序列 / 产出

---

## 附录 A：术语对照

| 概念 | SAP | Oracle | 平台 |
|---|---|---|---|
| 项目 | Project Definition | Project | `projects` |
| 任务 / WBS | WBS Element | Task | `project_tasks` |
| 项目级 BOM | Order BOM / WBS BOM | 无（项目物料 / effectivity） | `item_structures`（物料级） |
| 执行快照 | Production Order BOM | Work Order Component | `work_order_components` |
| 变更单 | Change Master / Change Number | Change Order / ECO | `engineering_changes` |
| 生效 | valid-from / parameter effectivity / release key | effective date / model-unit | `valid_from` / `valid_to` |
| 项目库存 | Special Stock `Q`（WBS） | Project Inventory / Project Locator | `inventory_*`（无项目维度） |
| 成本归集 | PS WBS + CO settlement | Expenditure Item（Task） | 派生视图（待建） |
| 期末估值 | Results Analysis | Burden / Capitalization / Billing | 不做 |
| 配置 | VC / Super BOM | CPQ / ATO / Configured Item | `configuration` |

## 附录 B：SAP ETO 关键对象速查

| 对象 | 关键字段 / 行为 |
|---|---|
| Sales Order Item | account assignment = WBS；requirement type；billing plan |
| Project Definition | 项目类型、计划工厂、日期 |
| WBS Element | 层级、billing / account assignment / planning 标识、预算、结算规则 |
| Network / Activity | 作业、关系、与采购/生产衔接 |
| Order BOM | 物料 + 销售订单 + 行项；按差异保存 |
| WBS BOM | WBS 元素（生产批次）；批次级结构与成本 |
| Routing / Production Version | 工序、工作中心、BOM+工艺组合、有效期 |
| Change Master | valid-from、parameter effectivity、release key、对象清单 |
| DIR（文档信息记录） | change number、valid-from、与物料/BOM/工艺链接 |
| Production Order | 物料、数量、日期、WBS 结算规则 |
| Special Stock `Q` | WBS 绑定、有/无估值、收发/转移 |
| Results Analysis | WIP / COGS / 收入；结算前置 |
| Settlement Rule | 结算接收方（WBS / 资产 / COGS / CO-PA） |
| PMMO | grouping WBS、pegging、distribution |
