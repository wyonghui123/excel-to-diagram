# 研究稿：ETO 双雄深度对比 — Oracle vs SAP

- 文档版本：v0.1
- 日期：2026-11-04
- 状态：研究稿（仅研究，**尚未实施**）
- 前置文档：
  - `spec-project-g15-eto-oracle-benchmark-2026-11-03.md`（Oracle 专题）
  - `spec-project-g15-eto-sap-benchmark-2026-11-04.md`（SAP 专题）
- 目的：在两份单产品研究之上做**跨产品对比与判断**，回答三个问题：
  1. 两家的差异是"功能多少"还是"架构哲学"？
  2. 哪些差异对平台 G15 是真约束，哪些只是产品规模带来的副作用？
  3. G15 应该学谁、学哪一层、不学什么？

> 阅读顺序建议：先看 §0，再看 §2（哲学）、§7（裁决）、§9（反向思考）。§3-§6 是证据铺陈。

---

## 0. 结论摘要（十条判断）

1. **两家都不是"ETO 产品"，而是"用既有对象拼出 ETO 流程"。** Oracle 拼的是 PLM + Manufacturing + PDSC + Project Financials；SAP 拼的是 PS + PP + MM + LO-ECM + CO。差别不在有没有 ETO 模块，而在**拼装的接缝在哪**。
2. **真正的架构分歧只有一个：项目结构是不是主数据对象。** SAP 说"是"（Order BOM / WBS BOM）；Oracle 说"不是"（物料级结构 + 项目物料 / effectivity + 项目引用）。其余差异（库存、成本、变更）都是这条分歧的下游结果。
3. **SAP 的轴是 WBS，Oracle 的轴是事务。** SAP 让所有后勤事务都挂 WBS 元素，成本/库存/预算天然同轴；Oracle 让所有执行事务带 project/task 引用，再在项目财务侧汇总。一个是"账户驱动"，一个是"事务驱动"。
4. **SAP 用项目 BOM 换来了"标准件复用 + 批次差异"，代价是主数据复杂；Oracle 用项目物料换来了"边界干净"，代价是物料膨胀。** 两者没有优劣，只有规模与复用率的匹配。
5. **项目库存的隔离粒度，两家其实一致：任务级。** SAP 固定绑 WBS 元素；Oracle PJM 可选 Project 或 Task 控制级别，Fusion 按项目/任务维度。**平台只做 `project_id` 是不够的，`project_task_id` 是 P1 必做项。**
6. **变更管理两家同构：产品级 + 生效控制 + 留痕。** SAP 多了 parameter effectivity / release key / revision level；Oracle 多了 redline / affected objects / NIR。平台现有 ECM 已覆盖主干，缺的是"revision 自动算"和"影响预览的项目过滤"，不是缺一整套机制。
7. **成本口径是两家最容易被误读的地方。** Oracle 的事实源是 Expenditure Item（bottom-up 事务汇总），SAP 的结果是 PS 归集 + CO 结算（account-based 期末加工）。平台没有 CO 引擎，**应先学 Oracle 的 bottom-up 派生视图**，而不是学 SAP 的 RA/结算。
8. **计划能力是两家的分水岭，但都不该进 G15。** Oracle 有 PDSC planning；SAP 有 Project MRP + PMMO（分组/溯源/分摊）。平台首期只需要"长周期件先采购、结构后到"这一条时序能力。
9. **对 G15 的最终裁决：D5 保持（不建项目 BOM 表），但补三件事——任务轴、库存任务维度、采购先行。** 其余（WBS BOM、RA、PMMO、release key）全部后置，并给出明确的"再评估触发条件"。
10. **最深的一层洞察：ETO 产品化的本质不是 BOM 管理，而是"不确定性管理"。** 三家都在回答同一个问题——设计没完成时，钱、料、工、库存先记在哪里，事后怎么归位。谁把这个"占位与归位"做得顺，谁就赢。

---

## 1. 对比方法与口径

| 项 | 口径 |
|---|---|
| 对比对象 | Oracle Fusion Cloud SCM/ERP 25C（EBS 12.2 作历史对照）；SAP S/4HANA（on-premise 为主，Cloud 能力差异见 §8 未核实项） |
| 对比维度 | 产品哲学、对象模型、数据模型、流程时序、变更/配置、成本/财务、计划/供应链、实施与生态 |
| 证据等级 | 强：官方文档 / 官方 PDF；中：行业媒体、伙伴白皮书；弱：培训资料、论坛 |
| 不比较 | 具体许可价格、具体实施人天、具体客户案例（均无可靠公开数据，见 §8） |
| 判断原则 | 只把"会影响平台数据模型与流程"的差异当成约束；纯规模差异（模块数量、许可复杂度）不作为设计依据 |

---

## 2. 产品哲学：接缝在哪

### 2.1 Oracle：平台化拼装，边界优先

Oracle 的做法是**先定义对象，再让对象互相引用**：

- BOM 只认物料，不认项目；
- 项目归属通过执行事务上的 project reference 表达；
- 成本通过 Expenditure Item 汇总到 Task；
- 项目库存通过库存维度 / project locator 隔离，不复制 BOM。

优点：**对象职责单一，跨项目复用天然成立**。
代价：**项目视图是"查出来的"，不是"存出来的"**；一旦要按项目做计划、开票、结算，就要在多个模块之间缝合。

一句话：Oracle 的 ETO 是"**用引用把项目穿起来**"。

### 2.2 SAP：流程集成，账户优先

SAP 的做法是**先定义一个横切所有模块的账户对象（WBS 元素），再让所有事务往里记**：

- 采购、生产订单、工时、库存移动都可以 account assignment 到 WBS；
- 项目库存直接绑 WBS；
- 成本先落 WBS，再由 CO 做结算；
- BOM 允许按订单 / WBS 存差异（Order BOM / WBS BOM）。

优点：**成本、库存、预算、进度天然同轴**，期末结算顺畅。
代价：**主数据与配置复杂**，WBS 成为"什么都挂"的枢纽；项目一多，库存段与 BOM 变体都碎片化。

一句话：SAP 的 ETO 是"**用账户把项目装进去**"。

### 2.3 哲学差异如何变成功能差异

| 哲学差异 | 直接后果 | 再下游后果 |
|---|---|---|
| 项目结构是否主数据 | SAP 有 Order/WBS BOM；Oracle 无 | SAP 主数据多、复用弱；Oracle 物料膨胀、项目检索弱 |
| 项目归属存在哪 | SAP 存在 WBS 账户上；Oracle 存在事务引用上 | SAP 预算/结算强；Oracle 查询/集成强 |
| 成本何时成型 | SAP 期末结算成型；Oracle 事务发生即成型 | SAP 会计闭环完整；Oracle 实时性好但缺 WIP/收入 |
| 变更管到哪一层 | 两家都管产品级 | 项目影响都要靠查询，谁都没有"项目变更单" |

**判断：** 这不是"谁更先进"，而是"谁把复杂度放在了哪"。SAP 把复杂度放在主数据与账户；Oracle 把复杂度放在集成与查询。平台要选的是**把复杂度放在哪一层**，而不是把两家的复杂度都搬过来。

---

## 3. 对象模型逐项对照

| 维度 | Oracle | SAP | 平台现状 | 差距性质 |
|---|---|---|---|---|
| 项目头 | Project | Project Definition | `projects` | 基本对齐 |
| 任务 / WBS | Task | WBS Element（billing / account assignment / planning） | `project_tasks`（层级 + 类型 + 状态） | 缺 WBS 类型语义与任务级预算 |
| 项目级 BOM | **无**；项目物料 / model-unit effectivity | **有**；Order BOM（订单行）、WBS BOM（生产批次） | 物料级 `item_structures` | 结构性差异（见 §4） |
| 执行快照 | Work Order Component | Production Order BOM | `work_order_components` | 已具备 |
| 工艺 | Work Definition（item 级、版本 + 生效日） | Routing + Production Version | `work_definitions` / `production_versions` | 缺项目/批次差异化 |
| 变更单 | Change Order / ECO（redline + affected objects + NIR） | Change Master（parameter effectivity + release key + revision level） | `engineering_changes` + lines | 缺 revision 自动算 / 参数生效 |
| 库存隔离 | 项目库存维度 / project locator（PJM 可选 Project 或 Task） | 特殊库存 `Q`，固定绑 WBS 元素 | `inventory_*` 无项目维度 | **P1 缺口** |
| 成本事实源 | Expenditure Item（Task 粒度） | PS WBS 归集 + CO 结算（WBS 粒度） | 工时派生视图 | **P1 缺口（口径）** |
| 配置 | Configured Item / CPQ | VC / Super BOM / 装配处理 | `configuration` 系列 | 已具备（仅 CTO） |
| 文档 | PLM attachment | DMS DIR + change number | 无 | 不做 |
| 计划 | PDSC planning | Project MRP + PMMO | 无 | 首期只做采购先行 |

**读法：** 表格里只有"项目级 BOM"是**结构性差异**；"库存维度""成本口径""任务级预算"是**平台缺口**，两家头部产品都有，平台没有；其余是规模差异。

---

## 4. 核心分歧深挖：项目 BOM 到底该不该建

### 4.1 两家的真实做法

**Oracle：不建，但用两条路线等效替代**

- 路线 A：一项目一物料。新 item + 自有结构，项目即物料，天然隔离。
- 路线 B：一物料多单元。`Effectivity Control = Model / Unit Number`，按单元号生效。
- Oracle 官方原文明确：model effective structure 通常与 project manufacturing 关联。

**SAP：建，两种粒度**

- Order BOM：按"物料 + 销售订单 + 行项目"保存订单相关差异；未改动的装配仍走物料 BOM。
- WBS BOM：按 WBS 元素（生产批次号）保存；批次级结构 + 批次级计划/实际成本。

### 4.2 为什么会有这个分歧

| 原因 | Oracle | SAP |
|---|---|---|
| 制造执行模型 | 工单级；工单取结构版本 | 生产订单 / 生产批次；批次可独立结构 |
| 物料策略 | 倾向"一项目一料号" | 倾向"标准料号 + 订单/批次差异" |
| MRP 依赖 | 项目物料直接进 MRP | 需要按订单/批次展开差异 BOM |
| 成本粒度 | Task | WBS / 生产批次 |
| 规模假设 | 项目数适中、物料编码可管 | 项目多、标准件复用率高 |

### 4.3 两种策略的代价对比

| 策略 | 优点 | 代价 | 何时崩 |
|---|---|---|---|
| 一项目一物料（Oracle 路线 A） | 隔离彻底、实现简单、无版本分叉 | 物料主数据膨胀、跨项目复用差、报表口径碎 | 项目数量大 + 标准件复用率高时 |
| 一物料多单元（Oracle 路线 B） | 复用高、物料不膨胀 | 依赖 unit 管理、配置复杂 | 无单元号管理能力时 |
| Order BOM / WBS BOM（SAP） | 复用高、批次成本清晰、设计可分阶段 | 主数据维护重、BOM 变体多、需要强 MRP | 项目少、复用低时反而浪费 |

### 4.4 对平台的判断

**P1 维持 D5（不建项目 BOM 表），理由是"规模不匹配"，不是"Oracle 也没有"。**

- 平台没有强 MRP、没有批次成本、没有 CO 结算；建 Order/WBS BOM 的收益（复用 + 批次成本）在平台当前场景里兑现不了，成本（维护 + 版本分叉）却立刻发生。
- 平台的 `work_order_components` 已经承担"执行冻结"，等价于 SAP Production Order BOM 的作用；缺的只是"下达前可编辑的项目结构"，而这一步可以用"项目物料 + 工程结构 + ECM"覆盖。

**但要写清楚再评估触发条件（满足任一条即重新评估 WBS 级结构）：**

1. 同一标准物料被 **3 个以上项目复用**，且每个项目的结构差异 **> 30%**；
2. 出现"同一项目多批次、每批次结构/成本必须分开"的真实需求；
3. 需要按批次核算成本或按批次追溯 as-built；
4. 项目数量增长到"一项目一物料"导致物料编码不可管理（例如 > 5000 个项目物料）。

**P2 的折中：只建指针，不建结构。**
`project_structure_baseline(project_id, task_id, structure_id, revision, purpose, captured_at)`——用于合同基线、设计冻结对比、变更影响回溯。它回答"当时用的是哪版结构"，不回答"结构行是什么"。这与 Oracle 的"引用"精神一致，也避免 SAP 式的结构副本。

---

## 5. 库存与任务轴：两家其实一致，平台缺一半

### 5.1 事实

- SAP 官方：项目库存分配给 **WBS 元素**，组件只能为该 WBS 领用；特殊库存 `Q`；有估值 / 无估值。
- Oracle PJM：project reference 的**控制级别可选 Project 或 Task**；Project Locator 按项目/任务隔离。
- Oracle Fusion PDSC：项目库存隔离，不需要独立库存组织。

### 5.2 推论

1. **头部产品的默认粒度是任务级。** 项目级只是"控制级别"的一个粗选项。
2. **任务级隔离直接支撑三件事**：跨任务不混料、任务级成本、部分完工。
3. **平台只加 `project_id` 会留下三个洞**：同一项目多任务互相抢料、成本无法按任务落、部分完工无法结算。

### 5.3 平台建议（P1 必做）

- `work_orders` + `project_task_id`（可空，服务层校验 project/task 一致）。
- `inventory_transactions` / `inventory_balances` + `project_id` + `project_task_id`（空值 0 哨兵）。
- `purchase_order` / `receipt` / `transfer_order` + `project_task_id`（收货链路三级传递，避免入库丢归属）。
- 发料校验：有项目归属时必须与工单的 project/task 一致（复刻 SAP"只能为该 WBS 领用"）。
- 余额唯一键扩为 `(org, location, item, batch, stock_status, project_id, project_task_id)`。

**注意：** 这是本专题**唯一需要改库存主键**的地方，迁移风险最高；必须先事务后余额、先可空后收紧，并按 P1 验收场景 D 验证。

---

## 6. 变更、成本、计划的三组对比

### 6.1 变更：同构，差异在"控制精细度"

| 能力 | Oracle | SAP | 平台 |
|---|---|---|---|
| 变更对象 | Change Order / ECO / Change Request | Change Master / Change Number | `engineering_changes` |
| 结构红线 | Redlines | 无独立 redline，靠 BOM 变更状态 | 无（只有 add/modify/remove 预览） |
| 版本 | ECO 自动算 revision | revision level（物料主数据）+ BOM 行版本 | 手工 revision |
| 生效 | 日期 / model-unit / use-up date | valid-from / parameter effectivity / release key | valid_from / valid_to |
| 审批 | Workflow + approval privilege | Release key + 审批流程 | 已有审批 |
| 项目归属 | 无（产品级） | 无（产品级） | 无（产品级） |

**判断：**

- ETO 变更的 80% 是"结构行增删改 + 日期生效"，平台现有 ECM 已覆盖。
- **值得补的只有两项**：revision 自动算（减少人工错）、影响预览的项目/在途工单过滤。
- **不建议补**：release key（平台没有"分域发布"的组织前提）、parameter effectivity（平台没有序列号/批次生效的结构基础，P3 再评估）、redline 可视化（成本高、收益低，先用差异对比替代）。

### 6.2 成本：bottom-up vs account-based

| 维度 | Oracle | SAP |
|---|---|---|
| 成本何时产生 | 事务发生时（收货、发料、报工） | 事务发生时先记 WBS，期末结算成型 |
| 事实源 | Expenditure Item | PS 归集 + CO 凭证 |
| 归集粒度 | Task | WBS |
| 期末加工 | burden / capitalization / billing | variance / WIP / results analysis / settlement |
| 实时性 | 高（事务即成本） | 中（要等结算） |
| 会计完整性 | 依赖 Project Financials | 完整（CO 闭环） |

**判断：**

- 平台没有 CO 引擎，学 SAP 的 RA/结算会变成"造一个半成品会计系统"。
- **应学 Oracle 的 bottom-up**：以事务为事实源，做一个**只读派生视图** `v_project_cost`，按 project + task 双层汇总人工 / 采购 / 制造，与预算对比。
- 明确红线：**不落第二套成本台账**。派生视图是唯一口径，任何"为了报表再存一张表"的做法都拒绝。
- WIP / 收入确认 / 结算 / 开票属于 P3 财务专题，不在 G15。

### 6.3 计划：两家分水岭，但都不进 G15

| 能力 | Oracle | SAP |
|---|---|---|
| 项目需求计划 | PDSC planning | Project MRP |
| 跨项目合并采购 | 弱（以项目执行隔离为主） | 强（PMMO grouping / pegging / distribution） |
| 项目 ATP | 有 | 有 |
| 长周期件先行 | 支持（项目采购先于 BOM） | 支持（PO 挂 WBS，BOM 可分阶段） |

**判断：**

- 两家都支持"结构未完成先采购"，这是 ETO 的刚需，**平台 P1 必须支持**。
- 跨项目合并采购（PMMO）是大型 ETO 的成本优化，平台没有 MRP 基础，**不做**。
- 项目 MRP / 项目 ATP / 项目排程全部 P3+。

---

## 7. 对平台 G15 的最终裁决

| # | 决策 | 证据 | 结论 | 再评估触发条件 |
|---|---|---|---|---|
| 1 | 是否建项目 BOM 表 | Oracle 无、SAP 有 | **不建**（D5 保持）；P2 只建指针 | §4.4 四条触发条件任一 |
| 2 | 库存项目维度 | 两家均任务级 | **加 `project_id` + `project_task_id`** | 若任务级迁移风险过高，可先项目级 + 任务可空 |
| 3 | 工单项目归属 | Oracle 五字段、SAP WBS 结算 | **加 `project_task_id`**，支出字段暂不落库 | 需要项目支出类型/组织时 |
| 4 | 采购先行 | 两家均支持 | **P1 支持"project/task 先行、BOM 后到"** | 无 |
| 5 | 成本口径 | Oracle bottom-up、SAP account-based | **单一派生视图，project + task 双层** | 需要 WIP/收入确认时 |
| 6 | 变更归属 | 两家均产品级 | **保持产品级**；影响预览加项目过滤 | 无 |
| 7 | revision | Oracle 自动、SAP revision level | **P2 加自动算** | 无 |
| 8 | 参数生效 / release key | SAP 有 | **P3 再评估，不实现** | 出现序列号生效或分域发布需求 |
| 9 | 项目结构基线 | Oracle 引用、SAP 副本 | **P2 指针表，不存行** | 需要合同冻结对比时 |
| 10 | 项目成本报表 | 两家都有 | **项目 360 复用现有五段，补成本段** | 无 |
| 11 | WBS BOM / Order BOM | SAP 有 | **不建**，用工单快照 + 基线指针 | §4.4 |
| 12 | PMMO / 项目 MRP | SAP 有 | **不做** | 出现跨项目合并采购需求 |
| 13 | RA / 结算 / 开票 | SAP 有、Oracle 有 | **不做**（P3 财务专题） | 需要项目会计合规时 |
| 14 | DMS / CAD / 报价 | 两家都有 | **不做** | 无 |

### 7.1 P1 必做清单（收敛后）

1. 项目物料（`item.code = <project_no>-<seq>`，可选 `items.project_id` 仅检索）。
2. 工程结构 → ECM 发布 → 生产结构（复用现有机制）。
3. `work_orders.project_task_id`。
4. 库存事务/余额 `project_id` + `project_task_id`（0 哨兵 + 唯一键扩展）。
5. 采购/收货/调拨 `project_task_id` + 三级传递 + 结构缺失不阻断。
6. `v_project_cost` 派生视图（project + task 双层，人工/采购/制造，预算对比）。
7. ECM 影响预览的项目过滤。

### 7.2 P2 / P3 边界

- P2：项目结构基线指针、任务级预算/可用性控制、项目库存台账/locator、长周期齐套、项目变更联合查询、revision 自动算。
- P3：参数生效、WBS 级结构（若触发）、as-built genealogy、RA/WIP/结算、项目 MRP/排程、项目开票。

---

## 8. 实施、生态与 TCO（二手判断，不作为设计依据）

| 维度 | Oracle | SAP |
|---|---|---|
| 产品形态 | Fusion Cloud 套件；EBS 仍大量在用 | S/4HANA（本地 / 云）；ECC 存量巨大 |
| ETO 上手难度 | 中高：需 PLM + Manufacturing + PDSC + Project Financials 组合 | 高：PS + PP + MM + CO + ECM 全链路 |
| 扩展方式 | Oracle 云扩展 / OIC / 自定义 | ABAP / BTP / 增强 |
| 顾问市场 | 相对集中，Fusion ETO 经验稀缺 | 顾问基数大，PS/PP 经验丰富 |
| 强项行业 | 项目型供应链、离散制造、EPC | 大型装备、汽车/航空供应链、项目会计 |
| 弱项 | 无项目 BOM；项目会计依赖额外模块 | 实施重、许可贵；前端报价仍需 PLM/第三方 |
| TCO | 未量化（无可靠公开数据） | 未量化（无可靠公开数据） |

**判断：**

- 两家都不适合"中小规模、快速上线"的 ETO 场景；它们的价值在"复杂项目 + 多组织 + 强财务"。
- 平台不应以"追上模块数量"为目标；应以"对象语义正确 + 最小闭环可运行"为目标。
- 平台真正的竞争优势是**轻**：没有 CO、没有 MRP、没有 DMS，反而可以把"项目/任务/工单/库存/成本"这条最短链路做顺。

---

## 9. 反向思考：不该照搬什么

1. **不要为了对标 SAP 建 Order BOM / WBS BOM 表。** SAP 的这两类 BOM 是为 MRP 与批次成本服务的；平台没有那套引擎，建了只会得到"没人用的主数据"。
2. **不要为了对标 Oracle 做 model/unit effectivity。** 平台没有单元号管理，`Effectivity Control` 会变成空字段。
3. **不要把 ECM 项目化。** 两家都是产品级；项目只是查询维度。加 `project_id` 会让变更无法跨项目复用。
4. **不要造第二套成本台账。** Oracle 的 Expenditure 和 SAP 的 CO 凭证都是"唯一事实源"；平台若同时存"派生视图"和"成本表"，必然双口径。
5. **不要复制项目主数据。** Oracle 用引用、SAP 用账户；平台若复制项目/物料到每个模块，等于自建数据孤岛。
6. **不要把 PMMO 的分组采购做成通用能力。** 这是大型 ETO 的批量优化，前置条件是成熟 MRP；平台不具备。
7. **不要为"完整"而做报价 / CPQ / DMS。** 两家的前端都要靠 PLM/第三方补齐，平台更没有必要。

---

## 10. 更深的洞察：ETO 的本质是"不确定性管理"

把两家产品放回业务本质，会发现它们回答的是同一个问题：

> **设计还没完成时，钱、料、工、库存先记在哪里？设计完成后，怎么归位？**

| 产品 | 占位对象 | 归位方式 |
|---|---|---|
| SAP | WBS 元素（账户） | 所有事务挂 WBS，期末 CO 结算归位 |
| Oracle | 项目物料 / 项目引用（对象） | 事务带 project/task，项目财务汇总归位 |
| 平台（建议） | 项目 + 任务（引用） | 工单快照冻结，派生成本视图归位 |

由此得到三条设计原则：

1. **先有占位，再有结构。** 项目/任务必须先能承载采购、工单、库存，不能等 BOM 齐全才允许下单。
2. **执行必须冻结。** 工单下达时快照组件，后续设计变更不静默改在途工单（两家都这么做）。
3. **归位只能有一个口径。** 成本、库存、预算都按 project + task 归集；派生视图是唯一出口。

这三条比"要不要建项目 BOM"更重要。项目 BOM 只是"占位对象"的一种实现方式，平台选择了更轻的引用方式。

---

## 11. 未核实项

1. **SAP Best Practices 中 ETO 的 scope item 编号**：未确认，不作为证据。
2. **Order BOM 的完整差异规则**：官方只说明"按物料+订单+行项保存"，未核实未改动装配是否完全不产生记录。
3. **WBS BOM 与 Production Lot 的强绑定**：未核实是否所有 WBS BOM 都必须建生产批次。
4. **PMMO 的云版本形态与许可**：仅二手。
5. **Results Analysis 方法细节**（POC / 成本法）未展开。
6. **Oracle Fusion PDSC planning 的引擎细节**：未逐页核实。
7. **两家公有云与本地版本的能力差异**：未逐项对照。
8. **TCO / 实施周期**：无可靠公开数据，本稿不给数字。
9. **两家在序列号/单元生效上的逐字段差异**：未做全字段映射。

---

## 12. 参考来源

### Oracle

- [O1] Oracle，*Using Manufacturing*（25C）— [PDF](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faumf/using-manufacturing.pdf)
- [O2] Oracle，*Implementing Product Management*（25C）— [PDF](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faipr/implementing-product-management.pdf)
- [O3] Oracle，*Using Product Development*（25C）— [PDF](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faupd/using-product-development.pdf)
- [O4] Oracle，*Using Supply Chain Cost Management*（25C）— [PDF](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/fapma/using-supply-chain-cost-management.pdf)
- [O5] Oracle，*Project-Driven Supply Chain in the Cloud* — [PDF](https://www.oracle.com/a/ocom/docs/applications/scm/oracle-project-driven-supply-chain-in-cloud-brief.pdf)
- [O6] Oracle EBS 12.2，*Project Manufacturing Implementation Guide* — [PDF](https://docs.oracle.com/cd/E51111_01/current/acrobat/122pjmig.pdf)
- [O7] Oracle EBS 12.2，*Project Manufacturing User's Guide* — [PDF](https://docs.oracle.com/cd/E51111_01/current/acrobat/122pjmug.pdf)
- [O8] Oracle EBS 12.2，*Engineering User's Guide* — [PDF](https://docs.oracle.com/cd/E51111_01/current/acrobat/122engug.pdf)
- [O9] Oracle EBS 12.2，*Bills of Material User's Guide* — [PDF](https://docs.oracle.com/cd/E51111_01/current/acrobat/122bomug.pdf)

### SAP

- [S1] SAP Help，*Project Stock*（MM-IM）— [镜像页](https://help.freedsap.com/ENHELPhtml/MMIM/ProjectStock.html)
- [S2] SAP Help，*BOM Categories*（PP-BD-BOM）— [镜像页](https://help.freedsap.com/ENHELPhtml/PPBDBOM/BOMCategories.html)
- [S3] SAP Help，*Engineering Change Management in Document Management* — [镜像页](https://help.freedsap.com/ENHELPhtml/CADMS/EngineeringChangeManagementinDo1.html)
- [S4] SAP，*Design-Driven Enterprise — From Bid to Design & Procurement* — [PDF](https://assets.dm.ux.sap.com/eur-digitalsupplychain-hub/pdfs/2022_webinar04_eto_14.04.2022.pdf)
- [S5] SAPinsider，*Complete the Engineer-to-Order Process with Period-End Postings for Project Valuation* — [文章](https://sapinsider.org/complete-the-engineer-to-order-process-with-period-end-postings-for-project-valuation/)
- [S6] SAPinsider，*Changing Production Master Data with ECM* — [文章](https://sapinsider.org/articles/customize-your-logistics-and-finance-processes-by-changing-production-master-data-with-ecm/)
- [S7] Noveco，*Project Manufacturing (ETO) in SAP* — [PDF](https://www.novecosystems.com/pdf/ETO_Project_Manufacturing_HL_Overview.pdf)
- [S8] RevTech，*SAP PMMO* — [文章](https://revtech.consulting/insights/sap-pmmo)

### 内部

- [I1] `spec-project-g15-eto-oracle-benchmark-2026-11-03.md`
- [I2] `spec-project-g15-eto-sap-benchmark-2026-11-04.md`
- [I3] `spec-project-g4-engineering-bom-2026-11-03.md`
- [I4] `spec-oracle-fusion-project-object-model-2026-10-31.md`
- [I5] 平台 schema / 迁移 / ECM 实现

---

## 附录：一句话对照卡

| 问题 | Oracle | SAP | 平台 G15 |
|---|---|---|---|
| 项目怎么建 | Project + Task | Project Definition + WBS | `projects` + `project_tasks` |
| 定制件怎么建 | 项目物料 / unit effectivity | 标准件 + 订单/WBS BOM | 项目物料 + 工程结构 |
| 变更挂哪 | 产品级 Change Order | 产品级 Change Master | 产品级 `engineering_changes` |
| 库存怎么隔离 | project/task 维度 | WBS 元素（`Q`） | `project_id` + `project_task_id` |
| 成本怎么来 | Expenditure（事务） | PS 归集 + CO 结算 | 派生视图 |
| 计划 | PDSC planning | Project MRP + PMMO | 只做采购先行 |
| 一句话 | 用引用穿项目 | 用账户装项目 | 用任务轴串项目，保持轻 |
