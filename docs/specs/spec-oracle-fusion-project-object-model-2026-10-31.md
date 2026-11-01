# 研究：Oracle Fusion Cloud 项目对象模型架构

> 文档编号：研究稿 v1.0 | 日期：2026-10-31 | 状态：待评审（仅研究）
> 目的：为「项目类型四层对象模型」提供一手对标（对应 `spec-project-type-object-model-research-2026-10-31.md` Phase 0 核验项）
> 证据等级：Oracle 官方文档（REST API 字段、Tables and Views、Implementation Guide、Readiness Notes）

---

## 0. 一句话模型

Oracle Fusion 把「项目」拆成**两个面、一个粒度、一个事实源**：

- **两个面**：商务面由 **Contract（合同）→ Contract Line（合同行）→ Bill Plan / Revenue Plan（开票/收入计划）** 承载；执行面由 **Project → Task（WBS）→ Work Plan → Deliverable / Resource Assignment** 承载。项目本身**不持有合同金额**，只做归集与执行。
- **一个粒度**：**Task 是唯一的成本/计费/进度归集粒度**（底层实现为 `PJF_PROJ_ELEMENTS`，`OBJECT_TYPE = TASK | STRUCTURE`），所有支出、预算、收入、交付物、资源分配都挂 Task。
- **一个事实源**：成本只有一条来源——**Expenditure Item（支出项）**，由人工/采购/工时/制造等业务事件生成，再经 burden（间接费用）与 capitaliz（资本化）加工。

一句话：**合同管钱、项目管事、任务管账、支出项管成本。**

---

## 1. 企业结构层（对象挂载在哪）

```
Legal Entity（法人）
  └─ Business Unit（业务单元，项目归属与数据安全边界）
       └─ Project Unit / Project Organization（项目组织，默认值来源）
            └─ Project（项目）
                 ├─ Project Type（类型，策略容器）
                 ├─ Classifications（分类，多值标签）
                 └─ Task / WBS（执行与核算粒度）
```

| 对象 | 作用 | 关键约束 |
|---|---|---|
| Legal Entity / Business Unit | 财务与数据安全边界；合同数据安全按 BU 授权 | 合同、项目均归属 BU |
| Project Unit / Project Organization | 项目组织，提供默认值 | 与 Project Type 的 `Set` 绑定 |
| Project Type | **策略容器**：burdening / billing / capitalization 开关、默认 burden schedule、分类、work type | **项目一旦使用该类型，类型不可改**；类型只在 `Set` 对应的 BU 生效 |
| Classification | 多值分类标签（Class Category + Code） | 可按类型自动带入全部项目 |

Project Type 的 **Class**（`Contract / Indirect / Capital`）决定项目的商业模式：
- `Contract`：为客户做，产生收入（T&M、Fixed Price、Cost Plus）；
- `Indirect`：内部费用型（IT、维护），不产生收入，`BillableFlag` 固定 N；
- `Capital`：资本化项目，`BillableFlag` 复用为 `CapitalizableFlag`。

---

## 2. 对象全景

```
Contract (OKC_K_HEADERS_ALL_B)
  ├─ Contract Line (OKC_K_LINES_B, PK = ID + MAJOR_VERSION)
  │    ├─ Bill Plan        （开票方法 / 开票周期 / hold）
  │    └─ Revenue Plan     （收入确认方法 / hold）
  ├─ Contract Deliverable (OKC_DELIVERABLES)
  └─ Contract Milestone   （含开票金额）

Project
  ├─ Project Type（burdening/billing/capitalization/classification）
  ├─ Project Element（PJF_PROJ_ELEMENTS_B）
  │    ├─ TASK      ── WBS 节点（TOP / PARENT / LEVEL 反范式列）
  │    └─ STRUCTURE ── WBS 结构树
  ├─ Work Plan / Baseline（计划与基线：allocation / duration / start / finish / quantity）
  ├─ Financial Plan（Plan Type：Budget / Forecast / Bid；版本；成本/收入）
  ├─ Deliverable（挂 Task，状态 New / In Progress / Completed）
  ├─ Milestone（从合同下沉到项目计划）
  ├─ Resource Assignment（资源、项目角色、cost/bill rate）
  └─ Expenditure Item（成本事实）─► Burden ─► Capitalization ─► GL / Assets
```

---

## 3. 逐对象机制

### 3.1 Project（项目头）

REST 字段口径（26D `Get a project`）：`ProjectId、ProjectNumber、ProjectDescription、ProjectStartDate、ProjectEndDate、ProjectCurrencyCode、ProjectLedgerCurrencyCode、BusinessUnitId/Name、ProjectStatus（实现定义，典型 Active/Closed）` 等。

要点：
- 项目状态是**实现定义**的（不是硬编码枚举），与我们的 `type_definition` 思路一致。
- 项目头不持有合同金额、不含开票计划；收入与开票全部在 Contract 侧。
- 项目类型、BU、货币、分类决定后续所有默认行为。

### 3.2 Task / Project Element（最关键的建模决策）

`PJF_PROJ_ELEMENTS_B` 把 **Task 与 WBS Structure 统一为「项目元素」**：

| 列 | 语义 | 对我们的启示 |
|---|---|---|
| `PROJ_ELEMENT_ID` | 与任务序列共用（PA_TASKS_S） | Task 是项目内的第一等对象 |
| `OBJECT_TYPE` | `TASK` 或 `STRUCTURE` | WBS 结构与任务同表，避免两套树 |
| `DENORM_TOP_ELEMENT_ID` / `DENORM_PARENT_ELEMENT_ID` / `DENORM_WBS_LEVEL` | 顶层/父级/WBS 层级反范式 | 树查询不递归（我们应同样反范式） |
| `CHARGEABLE_FLAG` | **只有最末级任务可计费** | 新增强约束：叶子节点才可挂成本/工单 |
| `BILLABLE_FLAG` | 可计费；Capital 项目复用为 `CAPITALIZABLE_FLAG`；Indirect 固定 N | 一个标志按项目类型改变语义（我们不照搬） |
| `LIMIT_TO_TXN_CONTROLS_FLAG` | 只允许任务交易控制清单内的支出 | 可借鉴为「任务级可用物料/服务清单」 |
| `START_DATE` / `COMPLETION_DATE` | 日期外支出项不可入 | 任务级成本时间边界 |
| `SERVICE_TYPE_CODE` / `WORK_TYPE_ID` | 工作类型（决定是否可计费、交叉计费分类） | 对应我们的 `type_definition` + `item` 服务属性 |
| `COST_IND_RATE_SCH_ID` / `OVR_...` | burden schedule（默认/覆盖） | 任务级费率覆盖 |
| `ALLOW_CROSS_CHARGE_FLAG` / `CC_PROCESS_LABOR_FLAG` / `CC_PROCESS_NL_FLAG` | 跨 BU 交叉计费 | 多组织结算能力强，暂不需要 |
| `CLIN_ELEMENT_ID` | **父任务直接关联合同行** | 合同行 ↔ 项目任务的挂载点 |

Task REST 字段（26C `Get all tasks`）另含：`TaskNumber、TaskName、ParentTaskId、BillableFlag、ChargeableFlag、CapitalizableFlag、AllowCrossChargeTransactionsFlag、ProgressStatusCode(NOT_STARTED / IN_PROGRESS / COMPLETED)、BaselineStartDate/FinishDate/Quantity/Duration/Allocation、CurrentStartDate/FinishDate/Quantity、ActualQuantity、ConstraintType/ConstraintDate、CriticalFlag、LowestLevelTask、ExternalTaskId/ExternalParentTaskId、BurdenSchedule`。

结论：Oracle 的 Task 同时是 **WBS 节点 + 成本对象 + 计费对象 + 进度对象 + 计划对象**，用一个实体承载五种用途，靠 `flags` 与类型策略区分。这是它最值得学的点，也是最不该照搬的点（见 §6）。

### 3.3 Work Plan / Baseline / Financial Plan

- **Work Plan**：任务级计划（allocation、duration、planned start/finish、planned effort）；可发布（publish）后才成为执行计划。
- **Baseline**：计划基线（`Baseline*` 字段族），用于偏差对比。
- **Financial Plan**：Plan Type（Budget / Forecast / Bid 等）+ Plan Version + 成本/收入；Plan Type 决定「只允许成本 / 只允许收入 / 两者」。
- **ETC（Estimate to Complete）**：`GEN_ETC_SOURCE_CODE`，支持从支出/计划/手工推导。

对我们：计划与基线应分别建模（`project_plan_version` + `project_baseline`），不要把预算字段堆在 project 头上。

### 3.4 Deliverable（交付物）

- 合同侧 `OKC_DELIVERABLES`：定义在合同/合同模板上的交付物。
- 项目侧 Deliverable：**挂 Task（一个 Task 可挂多个）**，状态 `New / In progress / Completed`（REST 默认 New，POST 必填）。
- 交付物可触发 **Billing / Procurement 动作**（交付即开票/采购），并可回填进度。

对我们：`project_deliverable` 应挂 WBS 节点，而不是挂项目头；状态与开票/验收动作解耦。

### 3.5 Milestone（里程碑）与开票

Oracle 的里程碑是**一份数据、三处消费**：
1. 合同管理员在固定价合同中创建里程碑及开票金额；
2. 合同批准后，里程碑**自动出现在项目计划**中，项目经理跟踪完成；
3. 完成后触发开票（Milestone Billing）与收入确认。

进度型开票另有 **Schedule of Values × Percent Complete**：`Invoice Amount = Percent Complete × SOV`，`Current Invoice = Invoice Amount − Prior Billed`。

对我们：这直接验证了「商务里程碑（收款）/ SLA 里程碑 / 计划行」三分不合并的决策——Oracle 也是「合同里程碑 → 项目计划 → 开票」一条链，SLA 不在 PPM 内。

### 3.6 Contract / Contract Line / Bill Plan / Revenue Plan

- `OKC_K_HEADERS_ALL_B`（合同头，按 BU 做数据安全）、`OKC_K_LINES_B`（合同行，主键 `ID + MAJOR_VERSION`，**行是版本化的**）。
- **Bill Plan / Revenue Plan 建在合同上，可被一条或多条合同行共享**（不是每行一份）；Bill Plan 绑定 Invoice Method，Revenue Plan 绑定 Revenue Method；均支持 hold 与 billing cycle。
- 合同行按「人工 / 费用」拆分（示例中同一顾问拆成 labor 行与 expense 行）。

对我们：我们目前的 `sales_order_schedule(schedule_kind=billing)` 相当于「合同里程碑 + 账单计划」的合并体，粒度是行级；Oracle 是「合同级计划 + 行级归属」，更适合一条计划管多行。**这是本项目最值得重新审视的结构差异。**

### 3.7 Resource Assignment / Project Role / Rate

- 资源请求（Project Resource Request）→ 资源分配（Assignment），带项目角色、分配比例、起止日期。
- 费率来源：Job / Project Role / Resource 三类 Rate Schedule；可设 cost rate 与 bill rate；可覆盖。
- 资源管理是独立 Offering（Project Resource Management），与 PPM 解耦。

对我们：这印证「资源实例 + 能力/技能 + 费率」应是独立主数据（G5），而不是 `items.required_resource_type` 三值枚举。

### 3.8 Expenditure Item / Burden / Capitalization / Cross-charge

- **Expenditure Item** 是唯一成本事实：挂在 Project + Task 上，受任务起止日期约束，可被 `LIMIT_TO_TXN_CONTROLS_FLAG` 限制。
- **Burden**：按 Project Type 的默认 burden schedule 计算间接费用；可在任务级覆盖；可选择 burden 与 raw cost 是否同条支出项。
- **Capitalization（CIP）**：Project Type 决定是否资本化（cost type raw/burdened、asset line grouping、资本化利息）；`CIP` 成本转入 `Oracle Fusion Assets`。
- **Cross-charge**：跨 BU 的人工/非人工交易，通过 transfer price schedule 定价。

对我们：如果未来要算项目成本，必须补「支出项」这个事实层；否则项目只能做归集视图，不能做成本核算。

### 3.9 Project-Driven Supply Chain（与我们的履约层直接对应）

Oracle 用 **Project-Driven Supply Chain（PDSC）** 把项目接到制造/采购：
- 库存组织开启 `Enable inventory tracking by project`；
- 采购申请、**制造工单**都携带 **project + task number**；
- 领料从普通库存或项目专用库存发出，产成品入项目专用库存；
- 物料与资源成本**回写为项目支出项**；
- 支持 project-specific manufacturing（工单或 orderless 执行）。

**这是「项目类型履约层」最有力的外部证据：履约单据挂 `project_id + task_id` 是行业标准做法**，我们当前设计只挂了 `project_id`，应补 `project_task_id`。

---

## 4. 与我们四层模型的对照

| 层 | Oracle | 我们现状 | 差距 / 建议 |
|---|---|---|---|
| 商务层 | Contract → Contract Line（版本化）→ Bill Plan / Revenue Plan（合同级、可多行共享）→ Milestone | `sales_order → line → schedule(delivery/billing/service)`，计划行级 | 计划行可保留；新增 `project_id`；评估「账单计划合同级共享」是否需要（D3 修订） |
| 商务↔执行挂载 | `CLIN_ELEMENT_ID`：合同行 ↔ 任务 | 无 | 新增 `sales_order_line.project_task_id`（而非只挂 project） |
| 执行层 | Project → Task（=project element，WBS 与结构同表）→ Work Plan / Baseline | 无 project/task | 新增 `project` + `project_task`（叶子节点才可挂成本/工单） |
| 交付/里程碑 | Deliverable 挂 Task；合同里程碑下沉项目计划 | 无 | `project_deliverable` 挂 task；billing milestone 复用 schedule |
| 主数据 | Item + BOM（制造域） | `items` + `item_structure` | 保持一致；不要再造项目专用物料类型 |
| 履约 | 制造工单/采购申请携带 project + task；成本回写支出项 | `work_order` 服务/生产，无 project | `work_order` 补 `project_id + project_task_id`；用料保留 structure_line 快照 |
| 资源 | Project Resource Assignment + Role + Rate Schedule；工作中心在制造域 | 无资源实例；`work_center_id` 悬空 | 项目资源（人）与制造资源（工作中心/设备）分开建模 |
| 成本 | Expenditure Item → Burden → Capitalization | 无支出项事实层 | 项目成本核算前必须先补支出项；否则只做归集视图 |
| 类型 | Project Type = 策略容器，项目用后不可改；状态实现定义 | `type_definition(scope_bo+level)` | 项目类型挂 `type_definition`，并把策略参数放 `control_parameter`（勿塞类型字典） |
| 权限/安全 | 按 BU；合同按 BU 数据安全 | org 维度（Spec 23） | 项目数据权限可复用 org 维度；BU ≈ org |

---

## 5. 可直接借鉴（5 条）

1. **Task 是唯一核算粒度**：项目下所有成本、收入、进度、交付物、资源分配只挂 Task，不挂 Project 头。我们应把 `project_wbs` 定义成「执行与归集的最小单元」，而非纯展示树。
2. **叶子节点才可挂载**：`CHARGEABLE_FLAG` 只允许最末级任务；我们应在服务层强校验（工单/支出/交付物只能挂叶子）。
3. **反范式树列**：`TOP_ELEMENT_ID / PARENT_ELEMENT_ID / WBS_LEVEL` 直接落列，避免递归查询。
4. **合同行 ↔ 任务显式挂载**：`CLIN_ELEMENT_ID` 让商务行与执行任务一一可对账；我们的 `sales_order_line.project_task_id` 应照此设计。
5. **履约单据携带 project + task**：PDSC 的工单/采购申请标签是行业标准，我们的 `work_order` 应同时挂两级。

## 6. 不要照搬（5 条）

1. **Project Element 多态**（TASK/STRUCTURE 同表）：Oracle 历史包袱；我们应分开 `project_task` 与 `project_wbs_structure`，或用单一 `project_task(parent_id)` 表达树。
2. **一个 flag 按项目类型变语义**（Capital 项目的 `BillableFlag` 复用为 `CapitalizableFlag`）：可读性差、易错；我们应分列 `billable_flag` / `capitalizable_flag`。
3. **Bill Plan / Revenue Plan 的高度抽象**（合同级计划 + 多行共享 + invoice method + billing extension）：对我们是过度设计；先用行级 schedule，保留升级空间。
4. **Project Type 用后不可改**：Oracle 为保护已发生交易；我们可用「类型快照 + 变更审计」替代硬锁（更符合迭代式平台）。
5. **Cross-charge / Burden / CIP 全家桶**：在我们还没有支出项事实层前不要引入；否则只有表没有数据。

---

## 7. 对本项目设计的修订建议

| 原决策 | 修订 |
|---|---|
| D1 项目是商务层一等对象，SO 挂 `project_id` | **保留**，并补 `sales_order_line.project_task_id`（对齐 `CLIN_ELEMENT_ID`） |
| D3 三套里程碑不合并，只补 `project_id` | **保留**，补「合同里程碑可下沉项目计划」的只读镜像（不新建表，用视图） |
| D4 新增 `work_center / resource / routing` | **拆分**：项目资源（人/角色/费率，对齐 Resource Assignment）与制造资源（工作中心/设备/工序，对齐 SCM）分开建模 |
| D5 项目 BOM 用快照 | **保留**，并明确快照粒度是「结构行级」，供工单用料只读 |
| D7 履约统一入口是 `work_order` | **保留**，`work_order` 增 `project_id + project_task_id`，`source_demand_type=project` |
| 新增 | **后续评估**：`project_expenditure_item`（成本事实层）——项目成本核算的前置，优先级低于 Phase 1-3 |

---

## 8. 开放问题

- Q1 我们的 `sales_order_schedule` 是否需要「合同级账单计划」概念，还是行级计划足够？
- Q2 `project_task` 是否允许跨项目复用（模板任务库），还是每个项目独立复制？
- Q3 叶子节点约束是否会导致「汇总任务也要挂交付物」的业务场景无法表达（Oracle 用交付物挂任意 Task）？
- Q4 项目成本事实层（支出项）是否进入本项目范围，还是单独立项？
- Q5 项目资源与 org 权限如何结合：项目成员 vs 组织成员，谁决定可见性？

---

## 9. 来源

- [Get all tasks for a project（REST，26C）](http://docs.oracle.com/en/cloud/saas/project-management/26c/fapap/op-projects-projectid-child-tasks-get.html)
- [Get a project（REST，26D）](http://docs.oracle.com/en/cloud/saas/project-management/26d/fapap/op-projects-projectid-get.html)
- [PJF_PROJ_ELEMENTS_B（Tables and Views）](https://docs.oracle.com/en/cloud/saas/project-management/24a/oedpp/pjfprojelementsb-24024.html)
- [PJF_PROJECTS_ALL_B（Tables and Views）](http://docs.oracle.com/en/cloud/saas/project-management/23b/oedpp/pjfprojectsallb-15818.html)
- [Create Project Types（Implementation Guide，25C）](https://docs.oracle.com/en/cloud/saas/project-management/25c/fapfm/create-project-types.html)
- [Project Types Window Reference（类型 Class：Indirect/Capital/Contract）](https://docs.oracle.com/cd/A60725_05/html/comnls/us/pa/projty01.htm)
- [Enabling Project Type（Contract / Indirect 定义）](http://docs.oracle.com/en/cloud/saas/planning-budgeting-cloud/epbca/proj_enable_project_type_100xf259d4d9.html)
- [Milestone Billing and Revenue Recognition（24B What's New）](https://docs.oracle.com/en/cloud/saas/readiness/erp/24b/ppm24b/24B-ppm-wn-f32064.htm)
- [Bill Plan and Revenue Plan Components（Enterprise Contracts Implementation Guide）](http://docs.oracle.com/cd/E29505_01/fusionapps.1111/e20371/F564402AN37A6F.htm)
- [OKC_K_LINES_B（合同行表，PK=ID+MAJOR_VERSION）](http://docs.oracle.com/en/cloud/saas/sales/oedms/okcklinesb-9656.html)
- [OKC_K_HEADERS_ALL_B（合同头数据安全策略）](http://docs.oracle.com/en/cloud/saas/readiness/erp/26c/ppm26c/26C-ppm-wn-f49414.htm)
- [OKC_DELIVERABLES（合同交付物表）](http://docs.oracle.com/en/cloud/saas/sales/oedms/okcdeliverables-18851.html)
- [Get all deliverables（REST，状态 New/In progress/Completed）](http://docs.oracle.com/en/cloud/saas/project-management/26b/fapap/op-deliverables-get.html)
- [Project-Driven Supply Chain for Manufacturing（工单/采购申请携带 project+task）](https://docs.oracle.com/en/solutions/project-driven-scm-manufacturing/index.html)
- [How You Set Up Project-Driven Supply Chain（Enable inventory tracking by project）](http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faims/how-you-set-up-project-driven-supply-chain.html)
- [Using Manufacturing 24B（Project-Specific Manufacturing）](http://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/24b/faumf/using-manufacturing.pdf)
- [Rate Schedule Types（Job / Project Role 费率）](http://docs.oracle.com/en/cloud/saas/project-management/26b/oapjb/rate-schedule-types.html)
- [Implementing Project Execution Management（资源请求与 cost/bill rate）](https://docs.oracle.com/en/cloud/saas/project-management/25d/oapex/implementing-project-execution-management.pdf)
- [Using Project Revenue and Billing 24C（Bill Plan / Revenue Plan 与合同行）](https://docs.oracle.com/en/cloud/saas/project-management/24c/oapjb/using-project-revenue-and-billing.pdf)

### 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-31 | 初版研究稿 v1.0（基于 Oracle 官方文档取证，未改代码、未提交） |
