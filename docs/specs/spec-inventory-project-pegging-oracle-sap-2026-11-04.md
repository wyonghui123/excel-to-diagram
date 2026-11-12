# 研究稿：项目 / WBS / 销售订单作为库存维度（pegging）——Oracle 与 SAP 对标

- 文档版本：v0.1
- 日期：2026-11-04
- 状态：研究稿（尚未实施；为 INV-2 预留/ATP 与库存维度迁移提供设计输入）
- 关联文档：
  - `spec-project-g15-eto-oracle-vs-sap-2026-11-04.md` §5（库存与任务轴）
  - `spec-project-g15-eto-oracle-benchmark-2026-11-03.md`（PJM / project reference / project locator）
  - `spec-project-g15-eto-sap-benchmark-2026-11-04.md` §4.6（项目库存 `Q`）
  - `spec-project-g15-finance-boundary-2026-11-04.md`（库存事务是 L1 业务事实，项目成本是 L3 投影）
- 研究方法：官方文档核实 + 现有仓库模型比对；结论标注置信度

---

## 0. 结论摘要

1. **两家都把"项目/销售订单归属"做成库存段，而不是给物料复制一份库存。** SAP 用特殊库存标识（`Q` 项目库存、`E` 销售订单库存）；Oracle 用 project reference + project locator（EBS）或 project/task 库存属性（Fusion）。
2. **隔离粒度是任务级，不是项目级。** SAP 的 `Q` 固定绑 WBS 元素；Oracle PJM 的 control level 可选 Project 或 Task，但项目库存实际按任务落库。平台只加 `project_id` 会留下"同项目多任务互相抢料"的洞。
3. **维度必须同时进事务账和余额键。** 只写事务会让余额无法按项目/WBS/SO 隔离；只写余额会丢失重算能力。这与平台"事务是真相、余额是投影"的单一事实架构天然一致。
4. **销售订单库存与项目库存是两种段，不是同一段。** SAP 中 `E` 绑销售订单行 + 客户，`Q` 绑 WBS；同一物料可同时存在自有、`E`、`Q` 三种库存（mixed-mode），靠特殊库存标识区分。
5. **"自有库存"用空值哨兵表达，不用 NULL。** SAP 的余额表以 `物料 + 工厂 + 库存地点 + 批次 + SOBKZ + WBS` 为键，自有库存就是 SOBKZ 为空；对应平台应使用 `0` 哨兵，避免唯一索引对 NULL 的重复放行。
6. **跨项目发料默认禁止。** SAP 明确"组件只能为该 WBS 领用"；Oracle PJM 默认禁止跨项目发料，需显式开关且限于同一 planning group；Fusion 用 hard pegged / common supply 决定能否动用公共库存。
7. **预留对象自带维度。** SAP 预留表 `RESB` 带 `SOBKZ`（特殊库存）、`PSPEL`（WBS）、`KDAUF/KDPOS`（SO 行）；Oracle 的 project MRP / 硬钉按 project/task 分离供需。平台的 INV-2 预留必须从第一天就带维度，否则后续无法补。
8. **估值是下一层，不是库存层。** 两家都允许项目库存"有估值 / 无估值"。平台库存不承担金额，估值留给 INV-5；库存层只回答"哪个段、多少数量、谁可用"。

---

## 1. 问题定义

平台当前状态（已核查 `meta/schemas`）：

| 对象 | 现状 | 缺口 |
|---|---|---|
| `projects` / `project_tasks` | 有项目与 WBS 层级（`project_tasks`） | 无任务级预算/可用性 |
| `sales_order` / `sales_order_line` | 都有 `project_id` | 无行级 WBS/task 归属；无 `sales_order_line_id` 到库存的链路 |
| `work_order` | 有 `project_id` | 无 `project_task_id`；`source_demand` 未落 SO 行 |
| `purchase_order` / `receipt` / `shipment` / `transfer_order` | 表头有 `project_id` | 行级无 `project_task_id` / `sales_order_line_id`，收货/转库会丢归属 |
| `inventory_transactions` / `inventory_balances` | **无任何项目/SO 维度** | 无法回答"这批料属于哪个项目/WBS/SO" |

因此本次研究要回答的只有三件事：

1. 项目 / WBS / SO 归属应存在哪一层（单据？事务？余额？）；
2. 隔离键怎么设计（维度组合、空值表达、唯一键）；
3. 与预留/ATP、跨项目转移、估值的关系边界。

---

## 2. Oracle 模型

### 2.1 EBS Project Manufacturing（PJM）

| 机制 | 内容 | 置信度 |
|---|---|---|
| Project Reference | 库存组织启用项目引用后，库存事务可带 Project / Task；控制级别可选 Project 或 Task | 高（官方 PJM 文档） |
| Project Locator | Stock Locator 的键弹性域追加 Project、Task 两段（常见为 segment19/20）；项目/任务随库位写入事务与 on-hand | 高（官方文档；"不建独立库存组织"为推断，中） |
| 隔离方式 | **同一库存组织内按项目/任务隔离**，不为每个项目建库存组织 | 中（官方文档未强制，实践如此） |
| 跨项目发料 | 默认禁止；需勾选 Allow Cross Project Issues，且仅限同一 planning group | 高 |
| 项目制造 | 项目工单只允许使用项目拥有的组件，完工入项目库存 | 高 |

来源：Oracle EBS 12.2 PJM User's Guide（`docs.oracle.com/cd/E26401_01/doc.122/e48956/`）。

### 2.2 Fusion Cloud：Project-Driven Supply Chain（PDSC）

| 机制 | 内容 | 置信度 |
|---|---|---|
| 库存属性 | Project Number、Task Number 作为**库存属性**加入，用于分隔与估值库存 | 高（官方） |
| 组织参数 | 组织级 `Enable inventory tracking by project`；组织须分类为项目支出组织（project expenditure organization），估值结构包含 project + task | 高 |
| on-hand | 按项目/任务分段查看；跨项目用 Create Project Transfer 重分类 | 高 |
| 供给策略 | Item 可设 hard pegged；决定项目库存能否动用公共库存 | 高 |
| 预留 | 预留可细化到 project/task；无项目引用的供给是否可用由 item 设置决定 | 高 |

来源：Fusion `How the Project-Driven Supply Chain Solution Works`（官方 help）。

### 2.3 Oracle 的关键取舍

- **不给物料/BOM 加项目字段**，所有归属通过执行事务的 project reference 表达（与 G15 结论一致）；
- **项目库存的隔离落在库位（EBS）或库存属性（Fusion）**，不是在项目主数据上建库存组织；
- **控制级别可配**（Project 或 Task），但推荐直接按 Task，避免后续二次迁移。

---

## 3. SAP 模型

### 3.1 特殊库存

| 标识 | 名称 | 绑定对象 | 估值 | 置信度 |
|---|---|---|---|---|
| `Q` | Project stock（项目库存） | **WBS 元素** | 支持有估值 / 无估值（无估值走成本收集器） | 高（SAP Help） |
| `E` | Sales order stock（销售订单库存） | **销售订单号 + 行 + 客户** | 支持有估值 / 无估值 | 高 |

- 同一物料可同时在自有库存、`E`、`Q` 中，`MSPR` 以 `物料 + 工厂 + 库存地点 + 批次 + SOBKZ + WBS` 为键；
- 库存科目按"项目/销售订单库存评估类"区分，估值层在 MM/CO，不在库存数量层。

来源：SAP Help `Project Stock`、`Sales Order Stock`（MM-IM）。

### 3.2 事务与约束

- 采购订单或生产订单做**科目分配类别 Q/E** 时，收货自动带出特殊库存标识与 WBS/SO；
- **项目库存只能为该 WBS 领料**（发料校验）；
- 移动类型 411 可把 `E`/`Q` 转回自有库存；项目间、项目与 SO 库存间互转必须走显式转移记账，不能当普通发料；
- **预留表 `RESB` 自带维度**：`SOBKZ`（特殊库存）、`PSPEL`（WBS）、`KDAUF/KDPOS`（SO 行），可用量按段计算。

### 3.3 SAP 的关键取舍

- WBS 是唯一归集轴：库存、成本、预算、结算全部同轴；
- 特殊库存标识是**段标记**，WBS/SO 行是**段内键**；
- 有/无估值由业务模式决定，不在库存层强制金额。

---

## 4. 三家对比与平台裁决

### 4.1 对比表

| 议题 | Oracle EBS PJM | Oracle Fusion PDSC | SAP MM-IM | 平台建议 |
|---|---|---|---|---|
| 项目归属存放 | 事务 + project locator | 事务 + 库存属性 | 事务 + 特殊库存 `Q` | 事务 + 余额键 |
| 隔离粒度 | Project 或 Task（可配） | Project / Task | WBS 元素（任务级） | **Task 级**（`project_task_id`） |
| SO 归属 | 单据 project reference；SO 行另建链路 | 预留/供给可细化 | 特殊库存 `E`（SO 行 + 客户） | **`sales_order_line_id`** |
| 自有库存表达 | locator 无 project/task 段 | 无 project/task 属性 | `SOBKZ` 为空 | **`0` 哨兵** |
| 跨项目发料 | 默认禁，开关 + planning group | hard peg / common supply | 只能为该 WBS 领料 | **默认禁，参数开关** |
| 预留 | Project MRP / 硬钉 | 预留带 project/task | `RESB` 带 SOBKZ/PSPEL/KDAUF/KDPOS | **INV-2 预留带维度** |
| 估值 | 项目库存可估值 | 项目库存可估值 | 有/无估值 | **库存不做金额，INV-5 承接** |
| 独立库存组织 | 不建（推断） | 不建 | 不建 | **不建** |

### 4.2 平台裁决（拟）

| # | 裁决 | 理由 |
|---|---|---|
| D1 | `inventory_transactions` 与 `inventory_balances` **同时**增加 `project_id` / `project_task_id` | 事务用于回溯与重算，余额用于隔离与 ATP |
| D2 | 自有库存统一用 `0` 哨兵，不写 NULL | 唯一索引对 NULL 不去重；与 SAP `SOBKZ` 空值同构 |
| D3 | 余额唯一键扩为 `(org, location, item, batch, stock_status, project_id, project_task_id, sales_order_line_id)` | 段内隔离；先事务后余额、先可空后收紧 |
| D4 | SO 维度落 **`sales_order_line_id`**，不落订单头 | SAP `E` 绑 SO 行；行级才可做 MTO/ETO 追溯 |
| D5 | 默认禁止跨项目/WBS 发料，参数 `allow_cross_project_issue` 放行且校验同一 planning group | 复刻 SAP/Oracle 默认行为，避免项目串料 |
| D6 | 单据行补 `project_task_id`，沿 `PO → receipt → inventory`、`TO → transfer → inventory`、`SO → shipment → inventory` 三级传递 | 表头 project_id 不足以落任务；传递链缺失会入库丢归属 |
| D7 | INV-2 预留对象自带 `project_id` / `project_task_id` / `sales_order_line_id` + 隔离策略（hard peg / common supply） | 两家均如此；后补代价高 |
| D8 | `sales_order_line_id` 与 `project_task_id` 可共存；若 SO 行已挂项目，服务层校验 `project_id` 一致 | ETO 场景 SO 是需求来源、项目/WBS 是库存段 |

### 4.3 明确不做

- 不建"项目库存组织"或"项目独立仓"；
- 不复制物料/BOM 到项目（沿用 G15 D5）；
- 不在库存层做估值/科目（INV-5）；
- 不做全局 SO 库存池或跨法人共享库存（P7 以后）。

---

## 5. 实施分期（建议）

| 阶段 | 内容 | 前置 |
|---|---|---|
| **INV-2a 维度铺底** | 事务/余额加 `project_id` + `project_task_id`（0 哨兵）；单据行补 `project_task_id` 与三级传递；余额唯一键扩展 + 重建脚本 | INV-1 |
| **INV-2b 预留/ATP** | 预留对象带三维度 + 隔离策略；可用量视图按段计算；跨项目校验参数 | INV-2a |
| **INV-2c SO 库存段** | `sales_order_line_id` 入键；SO 库存段收发/转移；与项目段共存校验 | INV-2a |
| **INV-5** | 项目库存估值/科目（沿用财务边界稿的 accounting event 契约） | INV-2a~c |

> 顺序建议：**先维度后预留**。若先做预留、后补维度，预留表与 ATP 视图都要二次迁移。

---

## 6. 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 余额唯一键扩展 | 已有余额数据需重建，迁移风险最高 | 先加事务字段 → 重建余额 → 再收紧唯一键；保留 `inventory_rebuild` 脚本可重算 |
| 历史数据回填 | 历史事务无 project/task，无法可靠反推 | 存量留 `0` 哨兵，按单据表头 project_id 可回填的才回填，其余标记待清洗 |
| 0 哨兵与真实 ID 冲突 | 若 `project_id` 允许 0 值行 | 主数据不自增到 0；服务层禁止显式写 0 |
| 性能 | 余额键变宽，查询需多维过滤 | 组合索引按 `(org, item, project_id, project_task_id)` 先行 |
| 与财务口径漂移 | 库存段与项目成本维度不一致 | 统一使用 `(project_id, project_task_id)`，财务稿已同口径 |

---

## 7. 来源

| 来源 | 类型 | 置信度 | 用途 |
|---|---|---|---|
| Oracle EBS 12.2 PJM User's Guide / Implementation Guide（`docs.oracle.com/cd/E26401_01/doc.122/e48956/`） | 官方 | 高 | project reference / project locator / control level / 跨项目发料 |
| Oracle Fusion `How the Project-Driven Supply Chain Solution Works`（官方 help） | 官方 | 高 | 库存属性 project/task、组织参数、hard peg、on-hand 分段 |
| SAP Help `Project Stock`（MM-IM） | 官方（经镜像核实） | 高 | `Q` 绑 WBS、有/无估值、移动约束 |
| SAP Help `Sales Order Stock`（MM-IM） | 官方（经镜像核实） | 高 | `E` 绑 SO 行 + 客户、估值 |
| SAP 表 `MSPR` / `RESB` 结构 | 官方表结构（二手镜像） | 高 | 余额键 `SOBKZ`、预留字段 `SOBKZ/PSPEL/KDAUF/KDPOS` |

> 说明：`Q`/`E` 的对应关系以 SAP Help 为准，部分二手博客存在写反的情况。
</tool_result>
