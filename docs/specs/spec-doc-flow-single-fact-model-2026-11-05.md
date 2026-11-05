# 单据流单一事实模型规格（DOC_FLOW Single-Fact Model）

- 状态：**提案（待评审）**
- 日期：2026-11-05
- 关联：`docs/specs/spec-doc-flow-end-to-end-2026-11-05.md`（端到端实现基线）
- 适用范围：`doc_flow_edges` / `doc_flow_rule` 及其写入路径（交货、收货、调拨、退货、冲销）
- 性质：模型演进规格；不改变库存过账语义，不重写派生引擎

---

## 1. 背景

DOC_FLOW 已具备边表、规则注册、派生引擎、冲销引擎、追溯视图与对账四类检查。功能可用，但「事实」的边界与身份仍不闭合：

- 一次业务动作横跨状态、库存、边、计划行、序列号、HU、预留多个写面，且分布在多个事务域；
- 同一数量在边、目标行、计划投影中被多次计算；
- 同一事实存在 7 元组 / `rule_id#red:` 后缀 / `derive_key` 字符串三套身份；
- 关系行 `status` 可原地翻转，A 档冲销还会级联抹除红字子边历史；
- 消耗量公式在 4 处复制，一致性靠测试锁定而非单一实现。

本规格把上述讨论收敛为可评审、可实施、可验收的模型演进方案。

---

## 2. 目标与非目标

### 2.1 目标

1. **一个业务动作 = 一个事务域**：状态、过账、边、计划投影在同一事务内提交或全部回滚。
2. **一条事实 = 一个稳定身份**：可被对账、追溯、外部系统以单一键引用。
3. **事实不可变，修正 = 追加**：冲销/红字以补偿事实表达，不原地抹除历史。
4. **一个数量只有一个权威**：其余位置只允许「同事务重算」，禁止第二套算术。
5. **投影单一引擎**：消耗量、余额、履约状态等投影由唯一实现生成。
6. **保留软引用 + 对账**：不追求数据库级强制外键（与 Oracle/Dynamics 实践一致）。

### 2.2 非目标

- 不重写 `doc_flow_derive_engine` 的派生算法与 7 元组幂等契约。
- 不引入新数据库、消息队列、独立事件存储服务。
- 不在本阶段实现需求分配（`demand_allocation`）的 M:N 重构。
- 不修改库存过账的科目/成本语义（仅改事务边界与调用顺序）。
- 不改前端交互；仅保证后端事实一致性。

---

## 3. 外部基准（二次确认的外部证据）

| 产品 | 存储形态 | 数量与状态归属 | 冲销方式 |
|---|---|---|---|
| **SAP** `VBFA` | 透明表，一行 = 前序单据行 → 后续单据行；S/4 有 `RUUID`，`STUFE` 为流层级 | 数量在边上（`RFMNG/RFWRT/MEINS`、`PLMIN` 符号）；业务状态在 `VBUK/VBUP`（S/4 并入 `VBAK/VBAP`），**不在 VBFA** | 生成取消单据（`VBRK-FKSTO/SFAKN`）+ 新 VBFA 行；**不修改原行**，无 reversal 标志 |
| **Oracle EBS/Cloud** | 已过账事务在 `MTL_MATERIAL_TRANSACTIONS`；无统一 document flow 链接表，各模块用 `TRANSACTION_SOURCE_TYPE_ID / SOURCE_ID / TRX_SOURCE_LINE_ID` 软关联 | 余额 `MTL_ONHAND_QUANTITIES` 为存储余额（官方未承诺可重建） | 新增反向/调整事务行，原事务不可编辑 |
| **NetSuite** | 头级 `nexttransactionlink`（`linktype/previousdoc/nextdoc`）+ 行级 `nexttransactionlinelink`（`previoustype/nexttype/previousline/nextline/foreignamount`） | link **不存数量**（数量在单据行）、**无 status**（状态在单据） | 新增 Credit Memo / Item Receipt → 新增 link |
| **Dynamics 365** | 单据行 `SourceDocumentLine` 外键；库存 `InventTrans` 经 `InventTransOrigin` + 来源 bridge；无通用链接表 | 数量在事务/单据行 | 新增反向事务；storno 用负数保留原记录 |
| **事件溯源 / CQRS** | append-only store = system of record；状态由 replay 重建，投影可再生成 | 补偿事件表达撤销，保留反转历史 | 追加补偿事件 |

**基准结论（5 条）**

1. 单据流链接在头部产品中**是独立存储的事实**（SAP、NetSuite），不是由外键临时拼出的视图。
2. 但**并非所有产品都维护统一链接表**（Oracle、Dynamics 用软引用/来源外键）——基数不是判据。
3. **业务状态与关系行分离**：SAP 状态在头/项表，NetSuite link 无 status。
4. **冲销一律追加**：无产品把“原关系行改成 reversed”作为主机制。
5. 各产品都只让**一个位置**承载数量：SAP 放在 VBFA，NetSuite 放在单据行；不允许两处独立累加。

来源：
- SAP VBFA：<https://www.se80.co.uk/sap-s4-hana-tables/?name=vbfa>
- SAP UPFLV（创建单据流记录）：<https://www.sapdatasheet.org/abap/dtel/upflv.html>
- Oracle Inventory Guide：<https://docs.oracle.com/cd/V77972_02/current/acrobat/122invug.pdf>
- NetSuite NextTransactionLink：<https://www.netsuite.com/help/helpcenter/en_US/srbrowser/Browser2021_1/analytics/record/NextTransactionLink.html>
- NetSuite 事务链接：<https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N551392.html>
- Dynamics InventTrans 重构：<https://download.microsoft.com/download/4/E/3/4E36B655-568E-4D4A-B161-152B28BAAF30/Implementing_InventTrans_refactoring_for_Microsoft_Dynamics_AX_Applications_AX2012.pdf>
- Azure 事件溯源模式：<https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing>

---

## 4. 术语与判据

| 术语 | 定义 |
|---|---|
| **事实（Fact）** | 一次已发生的业务派生：源对象、目标对象、数量、时间、执行者、类型。不可原地改写。 |
| **投影（Projection）** | 由事实派生、可重建的读模型：余额、消耗量、`delivered_qty`、履约状态、追溯视图。 |
| **补偿事实（Compensation）** | 为撤销/修正而追加的新事实；指向被补偿事实，不修改原行。 |
| **分配量** | 本条关系占用的源侧数量；可与目标业务数量不同（拆分/部分核销）。 |
| **边类型（edge_kind）** | `normal` / `counter`（反向）/ `red_ink`（红字调整）/ `reversal`（补偿撤销）。 |

### 4.1 单一事实模型五判据

1. **唯一写入口**：每类事实只有一个写入路径，其他路径只读。
2. **稳定身份**：每条事实有可引用的唯一键（非字符串约定）。
3. **不可变**：修正以新事实表达，原事实保留。
4. **不重复计算**：同一数量只有一个权威，投影由单一引擎生成。
5. **边界原子**：一个业务动作的全部事实在同一事务域内提交。

### 4.2 边表使用判据（回答「是否只有 M:N 才需要边表」）

基数**不是**判据。对每条规则问 4 个问题，任一为「是」则保留边表：

1. 目标行是否已存源单据 FK？—— 是 ⇒ 结构链接可退化。
2. 分配量是否恰等于目标行数量？—— 不等 ⇒ 需要独立分配量。
3. 是否需要独立于目标行的修正历史（红字/冲销/撤销）？—— 是 ⇒ 需要独立事实表。
4. 终点是否跨 BO / 跨库 / 跨实例？—— 是 ⇒ 需要统一边。

**本系统裁决**：问题 1 多为「是」、问题 2 为「是」、问题 3 为「是」、问题 4 为「否」。
因此边表应保留，但定位为**派生事实流水**，而不是「多对多关系表」。

---

## 5. 现状诊断（G1–G8）

> 证据等级：**C** = 代码已核实；**B** = 外部基准；**U** = 未验证/待确认。线上 `doc_flow_edges` 当前为空表，基数结论仅为代码级。

| 编号 | 现象 | 证据 | 影响 | 外部裁决 |
|---|---|---|---|---|
| **G1** | 一次发运多写面、多事务域：过账、建边、计划行、状态、HU、序列号、预留各自提交 | `action_executor.py` 的 `before_update` 钩子在行更新事务之前执行；`shipment_service.ship_confirm` 无外层事务（C） | 崩溃/异常产生「已过账无边」「已发运预留仍占用」等半真事实 | 确认。SAP/NetSuite 在单据保存时一并写流（B） |
| **G2** | 同一数量多处计算：`delivered_qty` 增量 `+=` / `-=`、边聚合、事务数量 | `shipment_service.py` 计划行增减；边与 `inventory_transactions.qty`（C） | 口径漂移，新增分支时对账失败 | 确认。外部每家只选一个权威（B） |
| **G3** | 身份三套：7 元组、`rule_id#red:{id}`、`derive_key` 字符串；普通边 `derive_key` 为空 | `doc_flow_schema.py` 唯一索引；`doc_flow_reversal.py`；`doc_flow_derive_engine.py` 插入 `derive_key`（C） | 外部无法用统一键引用事实；同一列承担多语义 | 确认。SAP `RUUID/STUFE`、NetSuite `linktype`（B） |
| **G4** | 关系行 `status` 原地改；A 档级联把红字子边置 `reversed` | `doc_flow_reversal.reverse_edge`（C） | 红字调整历史被抹除，审计链断裂 | 确认，四家产品均追加补偿（B） |
| **G5** | 消耗量公式 4 处复制：schema 视图、引擎 Σ 校验、对账比对、追溯视图 | `doc_flow_schema.py`、`doc_flow_derive_engine.py`、`doc_flow_reconcile.py`、v219/v222 视图（C） | 一致性靠测试锁，改口径需改 4 处 | 降级为工程问题；外部也维护投影，但由单一引擎（B） |
| **G6** | 规则语义在代码：`check_hook/map_hook/create_hook` 字符串 + 服务内 `is_return` 分支 | `doc_flow_rule_store.py`；`shipment_service.py`（C） | 规则不可静态校验、不可视化、不可配置 | 确认。SAP Copy Control 配置化（B） |
| **G7** | 状态真源三处：YAML 枚举、服务常量、DB 行值 | `meta/schemas/shipment*.yaml`、服务 `STATUS_*`（C） | 新增状态易漏改 | 确认。外部状态单点存放（B） |
| **G8** | 无强制 FK，靠 `doc_flow_reconcile` 事后发现 | 边表 DDL；`doc_flow_reconcile` 四类检查（C） | 一致性是事后证明 | **推翻「必须加 FK」**。Oracle 同样软引用（B） |

### 5.1 附带的静默降级

`ship_confirm` 在无库存事务时仅 `logger.warning` 并跳过建边，状态仍推进到 `shipped`（C）。
后果：出现「有单据状态、无事实边」的断链，且不产生错误。

---

## 6. 决策

| 编号 | 决策 | 理由 |
|---|---|---|
| **D1** | 边表定位为**不可变派生事实流水**（不是联表） | SAP VBFA / NetSuite link 的实践；解释为何 1:N 也使用边 |
| **D2** | 边表使用与否按 §4.2 四问判定，不按基数 | NetSuite 在已有 `Created from` 外键时仍维护 link；Dynamics/Oracle 不维护 |
| **D3** | 冲销改为**追加补偿事实**（`edge_kind='reversal'` + `reverses_edge_id`），原边不改 | 四家产品一致；避免历史抹除 |
| **D4** | 每个数量只允许一个权威：**边存分配量**；单据行存业务量；计划行 `delivered_qty` 仅同事务重算 | 对齐 SAP；消除 `+=`/`-=` 双算术 |
| **D5** | 边身份结构化：新增 `edge_kind`、`reverses_edge_id`、`biz_ref_type`、`biz_ref_id`、`stufe` | 对齐 SAP `RUUID/STUFE`、NetSuite `linktype` |
| **D6** | 保持软引用 + 对账，不新增强制 FK | Oracle/Dynamics 同为软引用；SQLite 跨库不可行 |
| **D7** | 规则语义元数据化（`edge_kind`/`direction`/`idem_key_fields`），hook 仅做映射 | 可静态校验与可视化 |
| **D8** | 状态枚举单点：YAML 为真源，服务常量由生成/校验保证一致 | 消除三处真源 |

---

## 7. 需求

### 7.1 P0（正确性底线）

| 编号 | 需求 | 验收 |
|---|---|---|
| **R-SF-01** | 交货 `ship_confirm` / `receive` / `reverse` 的全部写面纳入同一事务域 | 在任一后置步骤注入异常，库存、边、状态、计划行全部回滚 |
| **R-SF-02** | 无库存事务时**不得**推进到 `shipped`；改为失败或停留在 `staged` 并记录显式异常事实 | 关闭过账开关后发运被拒/降级，不出现「shipped 无边」 |
| **R-SF-03** | 新增 `compensate_edge(...)`：追加 `edge_kind='reversal'` 事实，指向原边；不改原边 `status` | 冲销后原边仍 `active`；聚合为 0；二次冲销幂等 |
| **R-SF-04** | A 档冲销不再级联修改红字子边 | 冲销后红字边仍可查询，历史可重建 |
| **R-SF-05** | 计划行 `delivered_qty` 由同事务重算（基于边/行），禁止增量算术 | 拆行、改量、退货、冲销后与边聚合一致 |

### 7.2 P1（口径与身份收敛）

| 编号 | 需求 | 验收 |
|---|---|---|
| **R-SF-06** | 迁移新增边身份列与索引；回填既有边：正向=`normal`、`#red:`→`red_ink`、补偿→`reversal` | 迁移后每条边有确定 `edge_kind`；唯一键可表达同对多事实 |
| **R-SF-07** | 消耗量公式单一实现（共享 SQL 常量或唯一视图），引擎/对账/追溯全部引用它 | 删除 3 处复制后全部测试通过 |
| **R-SF-08** | `derive_key` 降级为兼容别名，新写入以 `biz_ref_type/biz_ref_id` 为准 | 新边不再依赖字符串前缀表达身份 |
| **R-SF-09** | 状态枚举单一真源：YAML → 服务常量校验（启动/测试期断言） | 人为删一个状态，测试立即失败 |

### 7.3 P2（演进）

| 编号 | 需求 | 验收 |
|---|---|---|
| **R-SF-10** | 规则表新增 `edge_kind`、`direction`、`idem_key_fields`；hook 只做字段映射 | 规则可静态列出并可视化 |
| **R-SF-11** | 引入 `doc_events`（outbox）承载跨库写面，最终一致 | 跨库场景可重放补偿 |
| **R-SF-12** | 追溯按图遍历服务，减少固定多跳视图 | 新增单据类型无需改视图 SQL |

---

## 8. 实施计划

### 阶段 A（P0，先做）

1. **事务边界**：在 `ActionExecutor` 调用 `before_update` 前开启事务，或由状态机委托入口包事务；过账服务的内部事务改为嵌套透传。
2. **静默降级修复**：无事务不推进状态。
3. **补偿边原语**：`compensate_edge()` + 视图聚合口径调整；`reverse_edges_by_source` 切换为补偿模式。
4. **计划行重算**：`_apply_schedule_delivery` / `_rollback_schedule_delivery` 改为「按边重算」。
5. 测试：新增 5 例（异常回滚、无过账拒绝、补偿边幂等、历史保留、计划行重算）。

### 阶段 B（P1）

1. 迁移：边表加列与索引，回填 `edge_kind` / `biz_ref_*`。
2. 消耗公式单一化（视图 + 常量）。
3. `derive_key` 兼容读取，停止新写入依赖。
4. 状态单一真源校验。
5. 回归：`test_shipment_reverse`、`test_shipment_issue_doc_flow`、`test_shipment_return_doc_flow`、`test_doc_flow_reconcile`、`test_demand_trace_graph`、`test_shipment_service`。

### 阶段 C（P2）

规则元数据化、outbox、图遍历追溯；按需启动，不阻塞 A/B。

---

## 9. 验收标准

| 编号 | 验收内容 |
|---|---|
| **AC-SF-01** | 发运/收货/冲销任一后置步骤失败 → 全量回滚，无半真事实 |
| **AC-SF-02** | 过账关闭时发运被拒或明确降级，不产生 `shipped` 无边 |
| **AC-SF-03** | 冲销后原边 `active`，新增 `reversal` 边；聚合量为 0；重复冲销幂等 |
| **AC-SF-04** | 冲销后红字子边仍可查询（历史不丢失） |
| **AC-SF-05** | 任意拆行/改量/退货/冲销序列后，`delivered_qty` 与边聚合一致 |
| **AC-SF-06** | 每条边有确定 `edge_kind` 与稳定身份，可被外部按键引用 |
| **AC-SF-07** | 消耗量在引擎、对账、追溯三处结果一致，且仅一处实现 |
| **AC-SF-08** | 对账新增「边 ↔ 目标源字段」双向一致性检查；现有四类检查回归通过 |
| **AC-SF-09** | 状态枚举只有一处定义，删改任一状态会触发测试失败 |
| **AC-SF-10** | 全部回归：`test.py --file` 六个套件 + 新增套件全绿 |

---

## 10. 风险

| 编号 | 风险 | 应对 |
|---|---|---|
| **R1** | 事务边界改造触及通用 `ActionExecutor`，影响其他单据类型 | 仅在状态机委托入口包事务；全量回归 `test.py --all` 后串行确认 |
| **R2** | 补偿边改变聚合口径，历史数据需回填 | 迁移先回填 `edge_kind`，视图按 `edge_kind` 过滤，保留旧口径兼容视图 |
| **R3** | 计划行改为重算，可能与既有部分发运数据不一致 | 迁移后先跑对账，差异单据人工确认再做重算 |
| **R4** | 边表加列与索引影响写性能 | 索引仅加 `(source_bo, source_id, edge_kind, status)`；上线后观察 |
| **R5** | 规则元数据化范围膨胀 | 限定 P2，仅补 `edge_kind/direction/idem_key_fields`，不重写 hook 体系 |
| **R6** | 线上 `doc_flow_edges` 为空，基数结论无法数据级验证 | 上线前用影子库/测试数据验证 §4.2 判据；保留本文代码级结论标注 |

---

## 11. 待确认问题

| 编号 | 问题 | 影响 |
|---|---|---|
| **Q1** | `purchase_order_lines` 是否有 `requisition_line_id`、`receipt_lines` 是否有 `schedule_id`？ | §4.2 判据表第 2/3 行的结论 |
| **Q2** | `demand_allocation → transfer_order_line` 是否真实 M:N？ | 是否必须保留独立分配表 |
| **Q3** | `batch_save` / 导入 / 直连 SQL 是否绕过状态机与事务边界？ | G1 的实际暴露面 |
| **Q4** | 跨库部署（`APP_DB_ROUTING` 开启）时，边与规则表是否必须拆库？ | R-SF-11 的优先级 |
| **Q5** | 计划行 `delivered_qty` 是否可完全取消字段、改为按需聚合？ | R-SF-05 的实现形态（重算 vs 去字段） |

---

## 12. 附录 A：二次确认记录

| 原结论 | 复核 | 最终表述 |
|---|---|---|
| 边表不是联表，是事实账 | 成立 | 与 SAP `VBFA`、NetSuite link 一致 |
| 只有 M:N 需要边表 | 部分成立 | 纯关系层面成立；单据流层面不成立（NetSuite 反例） |
| 状态可变违背单一事实 | 成立 | 四家产品均用追加补偿 |
| 缺 FK 是一致性缺口 | 不成立 | Oracle 同样软引用；真正缺口是原子性与单一权威 |
| 公式复制是模型问题 | 降级 | 工程一致性问题，外部也维护投影，但由单一引擎 |
| 库存余额是第二事实 | 不成立 | 显式投影；风险仅在于是否有路径直写余额 |
| 冲销应保留历史 | 成立 | 外部一致；本系统为唯一反例 |
| `delivered_qty` 双算 | 成立 | 需收敛为一个权威 + 同事务重算 |

## 13. 附录 B：逐规则边表判据

| 规则 | 源 → 目标 | 基数 | 目标有源 FK | 分配量=目标量 | 需要修正历史 | 跨 BO/库 | 结论 |
|---|---|---|---|---|---|---|---|
| `shipment_line_to_issue_txn` | 发运行 → 库存事务 | 1:1 | 是 | 是 | 是（冲销） | 否 | 结构可退化，事实保留 |
| `receipt_line_to_inventory_txn` | 收货行 → 库存事务 | 1:1 / 1:N | 是 | 是 | 是（红冲） | 否 | 同上 |
| `transfer_order_line_to_issue_txn` | 调拨行 → 库存事务 | 1:1 / 1:N | 是 | 是 | 是 | 否 | 同上（P1） |
| `so_schedule_to_shipment_line` | 计划行 → 交货行 | 1:N | 是 | 是 | 否 | 否 | 可视图化 |
| `po_schedule_to_receipt_line` | 采购计划 → 收货行 | 1:N | 待确认 | 是 | 否 | 否 | 待 Q1 |
| `requisition_line_to_po_line` | 申请行 → 采购行 | 1:N | 待确认 | 待确认 | 否 | 否 | 待 Q1 |
| `allocation_to_transfer_line` | 需求分配 → 调拨行 | 可能 M:N | 否 | 否 | 否 | 否 | 保留边表 |

> 说明：线上 `doc_flow_edges` 为空，本表基数来自规则定义与索引约束（代码级），非运行数据统计。
