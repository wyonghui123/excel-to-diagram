# 研究稿：来源需求线索（Demand Pegging）——Oracle 模型深研

- 日期：2026-11-04
- 状态：研究稿（为跨业务流“需求线索”建模提供依据；不涉及库存分隔维度）
- 范围：只研究“供应/执行对象 → 最终需求对象”的追溯关系；库存维度、估值另见
  `spec-inventory-project-pegging-oracle-sap-2026-11-04.md`
- 结论性质：官方文档 + 官方表结构确证；标注推断处单独说明

---

## 0. 先确认概念：三件事必须分开

| 概念 | 回答的问题 | 例子 | 生命周期 |
|---|---|---|---|
| **即时来源（source ref）** | 这笔事务由哪张直接上游单据触发 | 收货 ← PO 行；发运 ← SO 行；消耗 ← 工单组件 | 写入时确定，不可重算 |
| **最终需求线索（pegging）** | 这批供应最终满足哪个需求 | PO → 库存 → 工单 → 发运 → SO 行 | 计划/分配时计算，可重算、可有版本 |
| **库存分隔维度** | 这批库存归谁、能否被别的需求用 | project/task、SO 行段、owner | 随库存事务持久化，进余额键 |

用户所指是第二项：**跨所有业务流的需求线索**，不是批次、不是动态属性、不是库存维度。

平台现状：`inventory_transactions` 已有 `source_doc_type` / `source_doc_id` / `source_line_id` / `source_event_key`（即时来源 + 幂等），这对应 Oracle 的 `TRANSACTION_SOURCE_TYPE_ID/ID` 层；**缺的是最终需求关系层**。

---

## 1. Oracle EBS：需求来源写在“关系/需求镜像”里

### 1.1 预留：需求来源三段式

`MTL_RESERVATIONS` 用三段式指向需求单据：

- `DEMAND_SOURCE_TYPE_ID` → `MTL_TXN_SOURCE_TYPES`（销售订单、工单、转储单、账户等）
- `DEMAND_SOURCE_HEADER_ID` → 需求单据头
- `DEMAND_SOURCE_LINE_ID` → 需求单据行

销售订单场景分别对应 `OE_ORDER_HEADERS.HEADER_ID` / `OE_ORDER_LINES.LINE_ID`。
**预留是行级分配关系**，不是业务对象上的一个 `demand_id` 列。

### 1.2 开放需求/供应镜像

`MTL_DEMAND` / `MTL_SUPPLY` 是 ATP/计划用的开放需求与开放供应镜像（含已完成数量），类型与事务来源同域：销售订单、账户/账户别名、内部申请、工单、采购单、移库单等。预测一般不直接入这两张表（推断）。

### 1.3 事务只记“即时来源”

`MTL_MATERIAL_TRANSACTIONS` / `MTL_TRANSACTIONS` 的：

- `TRANSACTION_SOURCE_TYPE_ID` → `MTL_TXN_SOURCE_TYPES`
- `TRANSACTION_SOURCE_ID` → 具体来源单据记录
- `TRANSACTION_SOURCE_NAME` → 冗余名称

它只回答“这笔动账由哪张直接上游单据触发”，**不等于最终需求**。Oracle 明确不会在成品入库或 SO 出货事务上保存“最终 SO 行”。

---

## 2. Oracle 计划：pegging 是计算产物，不是持久列

| 事实 | 内容 | 置信度 |
|---|---|---|
| 独立 pegging 表 | Fusion `MSC_FULL_PEGGING` 主键 `(PLAN_ID, PEGGING_ID)` | 官方表结构确证 |
| 链式表达 | `PREV_PEGGING_ID` / `END_PEGGING_ID` 串成 pegging 链 | 官方表结构确证 |
| 部分分配 | `ALLOCATED_QUANTITY` 表达一段分配量 | 官方表结构确证 |
| 可重算/可关闭 | “Number of Days to Calculate Pegging” 只影响 pegging 生成，不影响净算 | 官方文档确证 |
| 版本化 | pegging 挂在 `PLAN_ID` 下，随计划版本变化 | 官方表结构确证 |

结论：**最终需求线索在 Oracle 是计划层的派生关系，不在 SO/工单/库存事务行上持久化**。

### 2.1 硬钉 / 软钉

- 硬钉（hard peg）：项目/任务引用会写进计划订单，供应被锁定给该需求；
- 软钉（soft peg）：只做优先级偏好，不写引用，仍可被其他需求使用；
- Project MRP 在净算前按 project/task（或 planning group）预分配；
- 项目任务既是库存维度，也是需求节点；它比 SO 行更粗，**不能替代最终需求线索**。

### 2.2 多对多与部分分配

Oracle 明确支持双向多对多：

- 多张 SO 可 peg 到同一供应；
- 一个 SO 行可由多个供应按数量分段满足；
- 落地形态是关系行：`RESERVATION_ID` 一行一个分配；pegging 一行 `(TRANSACTION_ID, DEMAND_ID, ALLOCATED_QUANTITY)`，并按 `DEMAND_ID` / `TRANSACTION_ID` 建索引。

---

## 3. Fusion Cloud 的对应关系

| 对象 | 作用 | 关键点 |
|---|---|---|
| `INV_RESERVATIONS` | 库存预留 | 登记 demand source（类型/头/行/名称）与 supply source；SO 行是需求，on-hand/工单/PO/TO 是供应 |
| Supply Planning | 计划 pegging | **不创建 reservation，只读取显示**；pegging 在计划引擎按 end demand 计算并落 `MSC_*` 计划表 |
| PDSC | 项目驱动供应链 | project/task 既是库存属性，也是需求归属；hard peg 决定能否动用公共库存 |

---

## 4. 为什么 Oracle 要分两层

1. **即时来源是事务事实**：写入时确定、审计要求不可变、不能依赖计划重算；
2. **pegging 是计划产物**：随计划版本、可只算近端窗口、可关闭、可重算；
3. 合并成一个列会：陈旧、无法表达部分量、无法表达多对多、无法区分硬/软钉；
4. 代价：追溯要 join 计划表或跑计划，跨版本不可直接比较。

---

## 5. 对平台的 5 条模型启示

| # | 启示 | 落点 |
|---|---|---|
| D1 | 业务对象列只存即时来源（已有 `source_doc_*`） | 保持现状，不新增 `final_demand_id` |
| D2 | 最终需求建**关系表**，行级、带数量 | `demand_trace_links` |
| D3 | 统一节点抽象 | demand node：SO 行 / 项目任务 / 预测 / 服务单；supply node：库存 / PO / 工单 / 调拨 |
| D4 | 项目任务双重角色 | 既可做库存维度，也可做 demand node；允许“任务 → 多张 SO 行” |
| D5 | 最终需求可计算 | 预留/分配是事务型关系；端到端 pegging 用可重算视图或物化表（可选 `plan_version`） |

### 5.1 建议的关系表结构（草案）

`demand_trace_links`

| 列 | 语义 |
|---|---|
| `id` | 主键 |
| `supply_object_type` / `supply_object_id` / `supply_line_id` | 供应节点（on_hand、PO 行、工单、TO） |
| `demand_object_type` / `demand_object_id` / `demand_line_id` | 需求节点（SO 行、项目任务、预测、服务单） |
| `trace_type` | `reservation` / `pegging` / `allocation` |
| `peg_type` | `hard` / `soft`（仅 pegging 用） |
| `allocated_qty` | 本段分配量；支持部分分配 |
| `plan_version` | 计划型 trace 用；事务型留空 |
| `valid_from` / `valid_to` | 有效期 |
| `computed_at` / `created_by` | 审计 |
| 唯一键 | `(supply_object_type, supply_object_id, supply_line_id, demand_object_type, demand_object_id, demand_line_id, trace_type, plan_version)` |

约束（服务层）：

- `allocated_qty > 0`，供应/需求两侧累计分配不得超过各自数量；
- `demand_object_type` 必须有注册表（对象编码 + 主键 + 行主键），禁止裸字符串外键；
- 项目任务与 SO 行共存时校验项目一致；
- hard peg 的供应不得再分配给其他需求（除显式释放）；
- 事务型 trace 不可重算；计划型 trace 可按 `plan_version` 重建。

### 5.2 与批次 / 动态属性的边界

- **批次**：只做物理/质量 lot 身份；可在批次上记 `project_id` 作为专用提示，但不承载需求线索；
- **动态属性**：只做长尾筛选（合同阶段、资金来源等），不参与 trace 键与库存键；
- **需求线索**：统一走 `demand_trace_links`，因此天然支持新增需求类型（服务单、预测、合同）而不用改表。

---

## 6. 分期建议

| 阶段 | 内容 | 依赖 |
|---|---|---|
| D1（随 INV-2） | 预留对象带 `demand_object_type/id/line_id` + `demand_trace_links` 事务型 trace；SO 行 ↔ 预留 | INV-2 预留 |
| D2 | 采购/工单/调拨/收货/发运写入或继承 trace；手工调整 + 自动从即时来源推导 | D1 |
| D3 | 端到端 pegging 视图（递归 CTE）或物化表；可选计划版本 | D2 |

---

## 7. 来源

| 来源 | 类型 | 置信度 |
|---|---|---|
| Oracle EBS `MTL_RESERVATIONS` / `MTL_DEMAND` / `MTL_SUPPLY` 文档与表结构 | 官方 + 表结构 | 高 |
| Oracle EBS `MTL_MATERIAL_TRANSACTIONS` 事务来源字段（`TRANSACTION_SOURCE_TYPE_ID/ID/NAME`） | 官方 | 高 |
| Oracle Fusion `MSC_FULL_PEGGING`（`PLAN_ID`、`PREV_PEGGING_ID`、`END_PEGGING_ID`、`ALLOCATED_QUANTITY`） | 官方表结构 | 高 |
| Oracle Fusion `INV_RESERVATIONS`（demand source / supply source） | 官方表结构 | 高 |
| Oracle Supply Planning “Reservations in Supply Chain Planning” | 官方 | 高 |
| Oracle EBS Project MRP / hard-soft pegging（项目/任务预分配） | 官方 | 高 |
| “预测不入 MTL_DEMAND/SUPPLY” | 推断 | 中 |

- `https://docs.oracle.com/cd/E18727_01/doc.121/e13450/T291651T292014.htm`
- `https://docs.oracle.com/cd/E18727_01/doc.121/e13450/T291651T291655.htm`
- `https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/oedsc/invreservations-29866.html`
- `https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/oedsc/mscfullpegging-31224.html`
- `https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/fausp/reservations-in-supply-chain-planning.html`
- `https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/fausp/define-a-time-window-for-plan-pegging-calculations.html`
- `https://docs.oracle.com/cd/E18727_01/doc.121/e13680/T634873T635511.htm`
