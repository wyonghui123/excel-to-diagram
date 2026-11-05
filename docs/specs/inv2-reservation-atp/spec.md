# INV-2 实现规格：库存段、预留与 ATP

- 日期：2026-11-04
- 状态：**已实施 + 细化已落地**（2026-11-05 语义/不变量细化与含在途 ATP 扣减均已实现，见 §3.3、§3.4、§4.2、§8、§10.2）
- 迁移号：**v205**（主体；v201 = INV-1，v202 = P6a，v203 = INV-4）+ **v218**（2026-11-05：`inventory_reservations` status CHECK 增加 `closed`；v216/v217 已被并发会话占用）
- 对标依据：`docs/specs/reservation-oracle-vs-sap-2026-11-05.md`（Oracle / SAP 及 Infor、IFS、D365、NetSuite、Epicor 二次研究，R1–R18）
- 上游依据：
  - `docs/specs/spec-mto-eto-stock-segment-design-2026-11-04.md`（MTO/ETO 段方案与 4 条口径）
  - `docs/specs/spec-demand-pegging-oracle-2026-11-04.md`（即时来源 / 需求线索 / pegging 分层）
  - `docs/specs/spec-inventory-project-pegging-oracle-sap-2026-11-04.md`（项目/WBS/SO 维度对标）
  - `docs/specs/p6b-serial-execution/spec.md`（执行层口径）

---

## 1. 目标与范围

**做（INV-2 全量，分 S1–S5 实施）**：

1. **S1 段铺底**：`inventory_transactions` / `inventory_balances` 增段列；余额唯一键重建；存量归 `owned`；`owned` + `project_task` 先行可用。
2. **S2 预留/ATP**：`inventory_reservations` 表与服务；按段 ATP；MTO 标准走 soft/hard 预留。
3. **S3 需求线索**：`demand_trace_links` 表与服务；SO/项目/PO/工单/发运接入；端到端追溯视图。
4. **S4 SO 专用段**：`sales_order_line` 段，按物料策略开启；跨段转移与审批。
5. **S5 供应商寄售**：`supplier_consignment` 段；`owner_party_id`；消耗时所有权转移并计价标记。

**不做（后续阶段）**：

- 库存金额、估值分录、科目确定（INV-5）。
- 客户所有/客供料（`customer_owned`）——Oracle 无原生实体模型，延后。
- 计划引擎级 pegging（`plan_version` 重算）。
- SO 段默认开启（默认关闭，按物料策略）。
- 批次承载线索/段；动态属性承载段。
- 3PL owner、监管库等第 6 类段。

---

## 2. 已定决策

| # | 决策 | 依据 |
|---|---|---|
| D1 | 三层分离：即时来源（对象列）/ 需求线索（关系）/ 库存段（事务+余额键） | Oracle `TRANSACTION_SOURCE_*` 与 `MSC_FULL_PEGGING` 分离 |
| D2 | 段用**有限枚举 + 强类型伙伴列**，不建通用 EAV 段表，不引入 SAP 单一 `special_stock` | 段类型有限；强类型列保留 FK/索引/报表直查 |
| D3 | 段列同时进事务与余额键；自有段用 0 哨兵，不用 NULL | SQLite 唯一索引对 NULL 不友好；重建可重算 |
| D4 | **SO 段默认关闭**，按物料 `so_segment_enabled` 开启；仅四类场景开启 | SAP `E` 碎片化；Oracle 以 reservation/pegging 表达 |
| D5 | **项目段固定任务级**；单任务项目自动建根任务，不引入 project 级段 | SAP `Q` = WBS；Oracle on-hand 含 `PROJECT_ID`+`TASK_ID` |
| D6 | **第一版纳入供应商寄售**，客供料延后；`owner_party_id` 从 S1 就进键 | Oracle supplier consignment 原生；客户所有权库存无原生模型 |
| D7 | 预留带需求节点 + 段 + `hard/soft`；MTO 标准默认 soft，ETO/SO 专用默认 hard | Oracle reservation / SAP 个别需求 |
| D8 | 需求线索用 `demand_trace_links`，支持多对多与部分分配 | `MSC_FULL_PEGGING` 链 + `ALLOCATED_QUANTITY` |
| D9 | 库存层不做金额；段上只留 `valuation_relevant`，金额交 INV-5 | SAP 估值可配；Oracle 库存不按 SO 估值 |
| D10 | 批次只做 lot 身份；动态属性只做筛选；都不进段键/线索 | 两套主档正交；EAV 无约束 |
| D11 | 段变更只能走显式“段转移”事务，禁止普通收发模拟 | 审计与数量守恒 |
| D12 | ATP 按段计算；公共池不得自动挪用硬钉/项目/客供料库存 | SAP 特殊库存隔离；Oracle reservation 扣减 |

---

## 3. 数据模型

### 3.1 枚举

| 枚举 | 值 |
|---|---|
| `stock_segment_type` | `owned` / `project_task` / `sales_order_line` / `supplier_consignment` / `customer_owned`（后者暂不启用） |
| `inventory_reservation_status` | `open` / `partially_fulfilled` / `fulfilled` / `cancelled` / `closed` / `expired` |
| `inventory_peg_type` | `hard` / `soft` |
| `demand_object_type` | `sales_order_line` / `work_order_component` / `project_task` / `work_order` / `service_order` / `forecast` |
| `demand_trace_type` | `reservation` / `pegging` / `allocation` |

### 3.2 事务与余额

`inventory_transactions` 追加：

| 列 | 类型 | 默认 | 语义 |
|---|---|---|---|
| `stock_segment_type` | VARCHAR(20) | `owned` | 段类型 |
| `project_id` | INTEGER | 0 | 项目段/项目归属 |
| `project_task_id` | INTEGER | 0 | 任务段 |
| `sales_order_line_id` | INTEGER | 0 | SO 段 |
| `owner_party_id` | INTEGER | 0 | 寄售/客供料所有权方 |

`inventory_balances` 追加同 5 列，唯一键改为：

```text
(org_id, location_id, item_id, batch_id, stock_status,
 stock_segment_type, project_id, project_task_id,
 sales_order_line_id, owner_party_id)
```

规则（服务层 `validate_segment` 统一校验，**不建表级 CHECK**）：

- `owned`：5 个段列全 0；
- `project_task`：`project_id` + `project_task_id` 非 0；
- `sales_order_line`：`sales_order_line_id` 非 0；
- `supplier_consignment` / `customer_owned`：`owner_party_id` 非 0；
- 段类型与伙伴列一一对应，非法组合报 `INV_SEGMENT_INVALID`；
- `customer_owned` 本期即使传值也一律拒绝（枚举保留、默认禁用）。

> SQLite 的 `ALTER TABLE ADD COLUMN` 无法追加表级 CHECK，重建事务表代价过高；校验固定在 `stock_segment_service.validate_segment`，迁移只负责加列，并在 `verify` 中抽查存量行。

**余额预留量口径（单一事实）：**

- `inventory_reservations` 是预留量的**唯一事实源**；
- `inventory_balances.qty_reserved` 降级为其**投影**（按段键汇总 `open` / `partially_fulfilled` 预留），由 `inventory_posting_service.rebuild_reserved_qty()` 维护；
- 业务代码禁止直接写 `qty_reserved`，也不得自行累加该值。

### 3.3 `inventory_reservations`

**单义模型（2026-11-05 细化）**：本表每行只陈述一个事实——**承诺量**。需求由需求单据陈述，供应由段/库位/批次陈述，可用量由二者在读取时相减派生。因此不存在"需求镜像"与"分配记录"两种语义并存的情况。

| `peg_type` | 业务含义 | 受可用量校验 | 可挪用 | 五家对标术语 |
|---|---|---|---|---|
| `hard` | 固化承诺 | 是（不足即拒） | 否 | Infor hard peg / IFS allocate / NetSuite firm |
| `soft` | 共同承诺 | 否（可超，形成短缺） | 是 | D365 软预留 / NetSuite commit / IFS 预留 |

- `location_id`/`batch_id` 非空 = **实物分配**档（对应 IFS allocate / NetSuite reserve）；为空 = **数量承诺**档。
- **不新增 `reservation_kind` 列**：两档由 `peg_type` + 定位列表达（研究稿 R1/R13）。
- `soft` 是**占可用的软承诺**，不是 Infor 那种"信息性软钉"（不占可用、重排即丢）；禁止拿它存纯痕迹（研究稿 R12）。

| 列 | 类型 | 可空 | 语义 |
|---|---|---|---|
| `id` | INTEGER PK | 否 | 主键 |
| `reservation_no` | VARCHAR(32) | 否 | RSV 序列号 |
| `org_id` / `item_id` / `uom_id` | INTEGER | 否 | 库存组织 / 物料 / 单位 |
| `demand_object_type` | VARCHAR(30) | 否 | 需求节点类型 |
| `demand_object_id` / `demand_line_id` | INTEGER | 否 | 需求对象 / 行 |
| `location_id` / `batch_id` | INTEGER | 是 | 指定库位/批次（可空=不限定） |
| `stock_segment_type` | VARCHAR(20) | 否 | 段 |
| `project_id` / `project_task_id` / `sales_order_line_id` / `owner_party_id` | INTEGER | 否 | 段伙伴列，0 哨兵 |
| `qty_reserved` / `qty_fulfilled` | DECIMAL | 否 | 预留量 / 已核销量 |
| `peg_type` | VARCHAR(10) | 否 | `hard` / `soft` |
| `status` | VARCHAR(20) | 否 | 预留状态 |
| `valid_from` / `valid_to` | DATETIME | 是 | 有效期 |
| `source_doc_type` / `source_doc_id` / `source_line_id` | — | 是 | 来源单据 |
| `reservation_key` | VARCHAR(200) | 否 | 幂等键 |
| `created_by` / `created_at` / `updated_by` / `updated_at` | — | 是 | 审计 |

索引：

- `uq_reservation_key`：`(reservation_key)` 唯一；
- `idx_reservation_demand`：`(demand_object_type, demand_object_id, demand_line_id)`；
- `idx_reservation_segment`：`(org_id, item_id, stock_segment_type, project_task_id, sales_order_line_id, owner_party_id, status)`。

**状态语义与写入校验（2026-11-05 细化）：**

| `status` | 含义 | 可迁移到 |
|---|---|---|
| `open` | 新建，有未核销量 | `partially_fulfilled` / `fulfilled` / `cancelled` / `closed` / `expired` |
| `partially_fulfilled` | 部分核销 | `fulfilled` / `cancelled` / `closed` / `expired` |
| `fulfilled` | 全部核销（终态） | — |
| `closed` | **终止履行、保留历史**（对齐 NetSuite `Closed` / SAP `KZEAR`）；未核销量不再占用可用 | — |
| `cancelled` | 业务作废并释放 | — |
| `expired` | 有效期到点（时间派生，见 §4.2） | — |

- `closed` 与 `cancelled` 必须区分：前者保留已核销量与链路供追溯，后者表示承诺作废；不得把"停止履行"塞进 `cancelled`（研究稿 R2）。
- 写入校验：`qty_reserved > 0`；`qty_fulfilled <= qty_reserved`；同一需求节点的未核销承诺合计不得超过可解析的需求剩余量（见 §4.2 `create_reservation`）。

### 3.4 `demand_trace_links`

| 列 | 类型 | 语义 |
|---|---|---|
| `id` | INTEGER PK | 主键 |
| `supply_object_type` / `supply_object_id` / `supply_line_id` | VARCHAR/INTEGER | 供应节点（库存段行 / PO 行 / 工单 / TO） |
| `demand_object_type` / `demand_object_id` / `demand_line_id` | VARCHAR/INTEGER | 需求节点（SO 行 / 项目任务 / 预测 / 服务单） |
| `trace_type` | VARCHAR(20) | `reservation` / `pegging` / `allocation` |
| `peg_type` | VARCHAR(10) | `hard` / `soft`，仅 pegging |
| `allocated_qty` | DECIMAL | 本段分配量 |
| `plan_version` | VARCHAR(40) | 计划型 trace 用；事务型空 |
| `valid_from` / `valid_to` | DATETIME | 有效期 |
| `source_doc_type` / `source_doc_id` / `source_line_id` | — | 来源 |
| `computed_at` / `created_at` | DATETIME | 审计 |

索引：

- `uq_trace_link`：`(supply_object_type, supply_object_id, supply_line_id, demand_object_type, demand_object_id, demand_line_id, trace_type)` 唯一；
- `idx_trace_supply`：`(supply_object_type, supply_object_id, supply_line_id)`；
- `idx_trace_demand`：`(demand_object_type, demand_object_id, demand_line_id)`。

**与既有 `demand_allocation` 的边界：**

- `demand_allocation` 继续负责**单据内**的需求归属（如采购行归到哪个项目任务）；
- `demand_trace_links` 只负责**跨单据**的供应—需求链与分配量；
- 采购行的项目任务归属仍写 `demand_allocation`，本表不重复；两者通过需求节点关联，**不双写同一分配量**。

**互斥消费（R15，2026-11-05）**：同一数量不得同时由本表与 `inventory_reservations` 陈述。

| 供应形态 | 数量唯一事实源 | 另一侧要求 |
|---|---|---|
| 库存段行（已在库） | `inventory_reservations.qty_reserved` | 本表 `allocated_qty` 必须为 0，只记录链路 |
| 未来供应（PO / 工单 / TO，未收货） | 本表 `allocated_qty`（`trace_type=pegging`、`peg_type=hard`） | 收货前禁止对其建预留；收货转为库存段行后，数量改由预留陈述 |
| 计划型（`plan_version` 非空） | 本表 | 不参与 ATP，不占用可用 |

- 校验点：`DemandTraceService` 写 hard pegging 且供应为库存段行时，`allocated_qty` 必须为 0，否则报 `TRACE_SUPPLY_DOUBLE_COUNT`。
- ATP 只需按上表取数一次，口径见 §4.2。该规则的依据是 IFS 官方行为：预留会等量扣减已钉数量（研究稿 §8.4）。

### 3.5 `items` 追加

| 列 | 类型 | 默认 | 语义 |
|---|---|---|---|
| `so_segment_enabled` | boolean | false | 是否允许 SO 专用段 |
| `consignment_enabled` | boolean | false | 是否允许供应商寄售 |
| `hard_peg_default` | boolean | false | 默认硬钉（MTO/ETO 物料设 true） |
| `valuation_relevant` | boolean | true | 估值相关标记，INV-5 使用 |

> 与 `item.serial_tracked` / `require_on_issue` 保持一致，统一用 `boolean`，避免元数据生成的 UI 控件不一致。

### 3.6 段解析优先级（服务层唯一入口）

```text
1. owner_party_id 非空且 consignment_enabled=1 → supplier_consignment
2. project_task_id 非空 → project_task（project_id 由任务反查）
3. so_segment_enabled=1 且 sales_order_line_id 非空 → sales_order_line
4. 其他 → owned
```

- 无项目任务时不得凭空填 `project_id`；
- SO 段关闭时，SO 行只作为预留/线索，不建段；
- 段解析结果由 `stock_segment_service.resolve_segment()` 返回，禁止各服务各自拼装。

### 3.7 段生命周期

- 段随库存事务持久化，余额行段不可原地修改；
- 变更只能走“段转移”事务（`owned ↔ project_task ↔ sales_order_line ↔ supplier_consignment`）；
- 段转移必须带原因、原段/目标段快照，并校验不变量。

---

## 4. 服务层

### 4.1 `meta/services/stock_segment_service.py`（新建）

| 方法 | 行为 |
|---|---|
| `resolve_segment(doc_ctx)` | 按 §3.6 解析段；校验伙伴列 |
| `ensure_root_task(project_id)` | 项目无任务时自动建根任务（D5），返回 `project_task_id`；已有任务则复用，禁止跨项目借用 |
| `validate_segment(segment)` | 枚举、伙伴列、项目/任务/订单一致性 |
| `segment_key(segment)` | 生成余额键与查询键（0 哨兵） |
| `transfer_segment(payload)` | 写成对事务（出/入），生成 `transfer_group_id` |
| `assert_cross_segment_allowed(...)` | 跨项目/跨 SO/跨所有权校验 |

### 4.2 `meta/services/inventory_reservation_service.py`（新建）

| 方法 | 行为 |
|---|---|
| `create_reservation(payload)` | 幂等（`reservation_key`）；校验段与需求节点；**需求上限守卫**（R2）；硬钉冲突检查 |
| `release_reservation(id, reason)` | 取消/释放；写 `cancelled` |
| `fulfill_reservation(id, qty, tx_id)` | 部分/全部核销；累计不得超过 `qty_reserved` |
| `expire_reservations(now)` | 把到期行标记为 `expired`（不承担正确性，见下） |
| `close_reservation(id, reason)` | 终止履行并保留历史，写 `closed`（R2） |
| `sync_work_order_components(work_order_id)` | 工单组件级 soft 预留（幂等；取消/结构行消失即释放） |
| `fulfill_work_order_components(work_order_id, completed_qty)` | 完工收货按累计完工量核销组件承诺（累进到目标、只进不退） |
| `outstanding_commitments(source_doc_type, source_doc_id)` | 来源单据未核销承诺汇总（活跃且未过期） |
| `assert_source_closable(source_doc_type, source_doc_id)` | 关单前置校验；有未核销承诺时报 `INV_RESERVATION_ACTIVE_ON_CLOSE` |
| `atp(query)` | 返回 `{available_on_hand, shortage}`，按 `scope` 计算 |

ATP 口径（2026-11-05 细化；派生只在读取时发生）：

```text
active(r) = r.status IN ('open','partially_fulfilled')
            AND (r.valid_to IS NULL OR r.valid_to > now)

available_on_hand(segment) = qty_on_hand(segment)
                           - Σ(active: qty_reserved - qty_fulfilled)

atp(segment, scope='segment', include_inbound=false)
  = available_on_hand(segment)
  + expected_receipts(segment)                        # include_inbound=true
  - Σ(hard pegging to future supply, 未收货)          # 已被钉住的在途不可再承诺

shortage(segment) = max(0, Σ(active commitments) - qty_on_hand(segment))
```

- **过期由读取时判定**（`valid_to`）；`expire_reservations` 只负责把状态改成 `expired`，任务不运行不得影响可用量正确性（R15）。
- `scope` ∈ `org` / `segment` / `location` / `batch`，默认 `segment`；这是 SAP "检查范围"的裁剪版，不做配置矩阵（研究稿 R3）。
- `available_on_hand` 为对外唯一展示口径，`atp` 作为接口保留；两者必须在同一次查询内一致。
- **口径定位（2026-11-05）**：`available_on_hand` 等价于 Oracle 的 **ATR（可预留量）**；`atp` 在不含在途时与其同值，`include_inbound=true` 时额外扣减已被 hard pegging 钉住的未收货未来供应；仍不含时区与跨组织寻源，**不得对外宣称支持交期承诺**（对标见 `docs/specs/reservation-oracle-vs-sap-2026-11-05.md` §9）。
- `expected_receipts` 第一版恒为 0；`available_on_hand(include_inbound=true)` 因在途收货未接入报 `ATP_INBOUND_UNSUPPORTED`，不得静默返回 0。
- 未来供应的 hard pegging 只从 `atp(include_inbound=true)` 扣减，不影响 `available_on_hand`（互斥消费，见 §3.4）；段归属以该需求节点的活跃预留为锚点（trace 表当前无段字段）。
- `hard` 预留在目标段内扣减，且供应不得再分配；`soft` 预留在公共池扣减，允许释放/改派，并产生 `shortage`。
- 非估值段（寄售/客供料）同样扣减，但消耗时触发所有权转移。
- **需求覆盖现状（2026-11-05 核实）**：只有 SO 行在保存时自动建 soft 预留；工单 / 服务单 / 调拨**不建预留**，其需求目前不进入可用量（研究稿 A3）。最小闭环：需求单据接入时统一建 soft 预留，不为每类单据再写一套净算逻辑。

### 4.3 `meta/services/demand_trace_service.py`（新建）

| 方法 | 行为 |
|---|---|
| `link_supply_demand(payload)` | 校验数量上限；写 trace 行 |
| `unlink(id, reason)` | 逻辑关闭（`valid_to`） |
| `inherit_from_document(doc)` | 从即时来源/预留推导 trace |
| `trace_end_demand(supply_node)` | 端到端追溯到最终需求（递归/迭代） |

边界：`link_supply_demand` **不得**写入 `demand_allocation` 已有的需求归属字段；`demand_allocation` 也不反写 `allocated_qty`。二者只通过需求节点关联。

### 4.4 `inventory_posting_service` 扩展

- `_insert_transaction` / `_apply_balance` 增加 5 个段列；
- `rebuild_balances` 按含段键重建；
- `rebuild_reserved_qty` 由预留表汇总回写 `inventory_balances.qty_reserved`（唯一写入口）；
- `on_hand` 支持段过滤；
- 出库前按段校验可用量（与预留服务共用口径）；
- `available_qty()` **不得**读 `inventory_balances.qty_reserved` 投影做判定；当前无调用方，应转调预留服务或直接删除（R4）；
- 反冲保留原段。

### 4.5 单据接入点

| 单据 | 行为 |
|---|---|
| 销售订单行 | `so_segment_enabled=1` 时创建 SO 段预留；否则只建 MTO 预留 |
| 采购申请/PO | 项目任务/寄售供应商写入行；收货继承 |
| 收货 | `resolve_segment` 后过账；SO 段来源为关联 SO 行 |
| 发运 | 校验预留与段；核销预留、写 trace |
| 工单 | 项目任务段发料；成品入库按项目任务或 SO 段；组件按 `work_order_component` 建 soft 预留（独立物料需求，与来源 SO 行不重复计量） |
| 调拨 | 段随行；跨段禁止，走段转移 |
| 调整/盘点 | 按段盘点与过账，不改变段类型 |
| 退货 | 优先回原段；原段失效转 `owned` |

---

## 5. 权限、菜单与参数

**权限（5 条）**：

- `inventory_reservation:inventory_reservation_read`
- `inventory_reservation:inventory_reservation_create`
- `inventory_reservation:inventory_reservation_update`
- `inventory_reservation:inventory_reservation_delete`
- `demand_trace_link:demand_trace_link_read`

> `demand_trace_link` **无人工写入口**（仅服务写入）；如需纠错，走运维脚本 + 审计日志，不开放 `update` / `delete` 权限。

**菜单（2 个，挂 `procurement` 根；仓库无 `inventory` 根菜单，与 v201/v203 库存菜单保持一致）**：

- `inventory-reservation-list`（只读 + 释放动作）
- `demand-trace-link-list`（只读）

**参数**：

| 参数 | 默认 | 说明 |
|---|---|---|
| `inventory.so_segment_default` | `0` | SO 段默认关闭 |
| `inventory.allow_cross_project_issue` | `0` | 跨项目发料默认拒绝 |
| `inventory.consignment_enabled` | `0` | 寄售总开关 |
| `inventory.hard_peg_default` | `0` | 全局硬钉默认，物料可覆盖 |
| `inventory.segment_valuation_enabled` | `0` | 段级估值，INV-5 开启 |

---

## 6. 错误码

| 错误码 | 触发 |
|---|---|
| `INV_SEGMENT_INVALID` | 段类型/伙伴列不匹配 |
| `INV_SEGMENT_PARTNER_MISMATCH` | 项目任务不属于项目、SO 行物料不一致等 |
| `INV_SEGMENT_IMMUTABLE` | 试图原地改余额段 |
| `INV_CROSS_SEGMENT_DENIED` | 跨段发料/发运/转移未授权 |
| `INV_SO_SEGMENT_DISABLED` | 物料未开启 SO 段却传 SO 行段 |
| `INV_CONSIGNMENT_OWNER_REQUIRED` | 寄售段缺供应商 |
| `INV_RESERVATION_QTY_EXCEEDED` | 预留/核销超量 |
| `INV_RESERVATION_NOT_FOUND` | 预留不存在 |
| `INV_RESERVATION_STATE_INVALID` | 状态不允许该动作 |
| `INV_HARD_PEG_CONFLICT` | 硬钉供应被重复分配 |
| `INV_TRACE_QTY_EXCEEDED` | trace 分配量超过供应/需求 |
| `INV_TRACE_NODE_INVALID` | 需求/供应节点类型非法 |
| `INV_VALUATION_NOT_SUPPORTED` | 库存层收到金额/估值请求 |
| `INV_RESERVATION_EXCEEDS_DEMAND` | 未核销承诺合计超过需求剩余量（§8.14） |
| `INV_RESERVATION_CLOSED` | 对 `closed` 预留再核销/释放 |
| `INV_RESERVATION_ACTIVE_ON_CLOSE` | 关单前置校验：来源单据仍有未核销承诺（先核销或释放） |
| `INV_DEMAND_QTY_UNKNOWN` | **告警（不阻断）**：需求量不可解析，无法执行上限守卫 |
| `TRACE_SUPPLY_DOUBLE_COUNT` | 库存段行同时被 hard pegging 记量与预留计数（§3.4） |
| `ATP_INBOUND_UNSUPPORTED` | `available_on_hand(include_inbound=True)`：含在途的可用量未实现（`atp(include_inbound=True)` 已支持扣在途，见 §4.2） |

---

## 7. 关键流程

### 7.1 MTO 标准（不建 SO 段）

```text
SO 行（demand node）
  → 预留（soft 默认；hard_peg_default=1 时 hard）
  → 计划/工单/PO
  → 收货进 owned 段
  → 发运核销预留 + trace
```

- 取消：释放预留与 trace；
- 部分发运：`qty_fulfilled` 分段累计；
- 余料：留在 `owned`，可被其他需求使用。

### 7.2 MTO 客户专用（SO 段）

```text
SO 行（so_segment_enabled=1）
  → 采购/工单 → 收货进 sales_order_line 段
  → 只允许该 SO 行发运
  → 取消/余料：显式段转移至 owned
```

### 7.3 ETO（项目任务段）

```text
项目任务（demand node）
  → 项目采购/工单 → 收货进 project_task 段
  → 项目发料/发运
  → 任务关闭：余料转 owned 或报废
```

- 跨任务/跨项目默认拒绝；
- 单任务项目自动建根任务。

### 7.4 供应商寄售

```text
收货进 supplier_consignment（owner=供应商）
  → 消耗：所有权转移事务 → owned → 应付/计价标记
```

### 7.5 退货 / 段转移

- 退货优先回原段（原 SO/项目仍有效）；
- 原段失效则转 `owned`；
- 所有段转移走 `transfer_segment`，禁止普通收发模拟。

---

## 8. 不变量

1. 一条余额行只有一个段类型，伙伴列匹配；
2. 段不可原地修改，只能段转移；
3. `project_task` 必须属于 `project_id` 且组织一致；
4. `sales_order_line` 必须与物料/客户/组织一致且订单未关闭；
5. 非估值段不产生库存金额；
6. 硬钉供应不得重复分配；
7. 段内可用量不为负；公共池不得挪用已隔离库存；
8. 退货优先回原段；
9. 段行仍需 trace 到需求节点，二者不互相替代；
10. 段转移必须留原因、操作人、原/目标段快照；
11. `inventory_reservations` 是预留量唯一事实源，`qty_reserved` 只能是其投影；
12. `customer_owned` 段任何写入一律拒绝（`INV_SEGMENT_INVALID`）；
13. 同一 `(supply 节点, demand 节点, trace_type)` 只允许一条有效 trace（`valid_to` 为空）；
14. 未核销承诺合计不得超过需求剩余量；需求量不可解析时告警 `INV_DEMAND_QTY_UNKNOWN`，不得静默放行；
15. 过期是时间派生：读取按 `valid_to` 排除，批处理任务不承担正确性；
16. 同一库存段行的数量只能由预留陈述；hard pegging 的 `allocated_qty` 必须为 0（否则 `TRACE_SUPPLY_DOUBLE_COUNT`）；
17. 未收货的未来供应不得建预留，其数量只能由 hard pegging 陈述；
18. `qty_reserved` 投影只能用于展示与重建校验，不得作为任何判定输入。
19. 含在途 ATP 只扣已 hard 钉住的未收货未来供应；段归属以需求节点的活跃预留为锚点，无预留的需求不进入 L0 在途扣减。

---

## 9. 测试计划

| 文件 | 覆盖 |
|---|---|
| `meta/tests/test_inventory_segment_migration.py` | v205 建列/建表/枚举/权限/菜单/回填幂等 |
| `meta/tests/test_inventory_segment_posting.py` | owned/project/SO/寄售过账、余额键、重建、负库存 |
| `meta/tests/test_inventory_reservation_service.py` | 幂等、释放、部分核销、状态机、硬钉冲突 |
| `meta/tests/test_inventory_atp.py` | 按段 ATP、软/硬预留、跨段隔离 |
| `meta/tests/test_demand_trace_service.py` | 多对多、部分分配、上限、端到端追溯 |
| `meta/tests/test_mto_consignment_flow.py` | MTO 预留→发运、SO 段、ETO 跨项目拒绝、寄售消耗转移 |
| `meta/tests/test_inventory_foundation_regression.py` | INV-1/P6b 回归（只读，不改旧断言） |

### 9.1 细化新增用例（2026-11-05）

| 用例 | 目标文件 | 断言 |
|---|---|---|
| 手工预留超过需求剩余量 | `test_inventory_reservation_service.py` | `INV_RESERVATION_EXCEEDS_DEMAND` |
| 需求量不可解析时告警放行 | 同上 | 不抛错，日志 `INV_DEMAND_QTY_UNKNOWN` |
| `close_reservation` 保留已核销量 | 同上 | 状态 `closed`，`qty_fulfilled` 不变，未核销量退出 ATP |
| `closed` 不可再核销/释放 | 同上 | 状态机拒绝，`INV_RESERVATION_CLOSED` |
| 过期不跑任务仍不计入 ATP | `test_inventory_atp.py` | `valid_to` 过后 `available_on_hand` 立即恢复 |
| soft 超可用返回短缺 | 同上 | `shortage > 0`，`available_on_hand < 0` |
| `available_on_hand` 含在途未实现时报错 | 同上 | `ATP_INBOUND_UNSUPPORTED` |
| 库存段 hard pegging 带量被拒 | `test_demand_trace_service.py` | `TRACE_SUPPLY_DOUBLE_COUNT` |
| 已钉住的未来供应从含在途 ATP 中扣减 | `test_inventory_atp.py` | `inbound_pegged = 5`，`available_on_hand` 由 5 降为 0 |
| 工单组件建 soft 预留并扣减可用量 | `test_inventory_reservation_service.py` | 需求节点 `work_order_component`、`peg_type=soft`，ATP `reserved=4` |
| 组件重展开不重复承诺、旧结构行释放 | 同上 | 二次同步 `created=0`；结构行变化后旧承诺 `cancelled` |
| 工单取消释放组件承诺 | 同上 | `released=1`，可用量恢复 |
| 有未核销组件承诺时拒绝关单 | 同上 | `INV_RESERVATION_ACTIVE_ON_CLOSE`，`outstanding` 带入明细 |
| 核销/释放后允许关单 | 同上 | 拦截器放行 |
| 完工收货按累计完工比例核销组件承诺 | `test_inventory_reservation_service.py` / `test_serial_completion_genealogy.py` | 完工 2/5 时核销 4/10，完工 5/5 时全部 `fulfilled` |
| optional 组件不自动核销 | 同上 | `skipped=1`，承诺保留 |
| 组件任务段继承工单头任务 | `test_work_order_production.py` | `expand_components` 写入 `project_task_id` |
| 重展开保留逐组件任务覆盖 | 同上 | 按 `structure_line_id` 保留，不被 DELETE/INSERT 抹掉 |

---

## 10. 验收标准

1. 存量余额全部归 `owned`，重建结果与 INV-1 一致；
2. MTS 流程行为不变，回归全绿；
3. ETO 收货进 `project_task` 段，跨项目发料被拒；
4. MTO 标准只建预留不建段，取消即释放；
5. 开启 `so_segment_enabled` 的物料，SO 段只对该行可用；
6. 供应商寄售收货非估值，消耗写所有权转移；
7. 端到端可从 PO/工单追溯到 SO 行或项目任务；
8. 余额重建可复现含段结果；
9. 库存层无金额字段与分录。

10. 手工预留超过需求剩余量被拒，SO 镜像路径行为不变；
11. `expire_reservations` 未运行时，过期预留已不占用可用量；
12. 同一库存段行不会同时被 hard pegging 与预留计数（互斥消费）；
13. `closed` 终态保留历史且不再占用可用量；
14. `qty_reserved` 投影无任何判定调用方（`available_qty` 已移除或改调预留服务）；
15. `atp(include_inbound=True)` 扣减已 hard 钉住的未收货未来供应，且不重复承诺同一在途；
16. 工单组件以 `work_order_component` 建 soft 预留，重展开幂等、取消即释放，且不与来源 SO 行重复计量。

### 10.1 实施验收结果（2026-11-04）

| 测试文件 | 结果 |
|---|---|
| `test_inventory_segment_migration.py` | 7/7 |
| `test_inventory_segment_posting.py` | 8/8 |
| `test_inventory_reservation_service.py` | 9/9 |
| `test_inventory_atp.py` | 3/3 |
| `test_demand_trace_service.py` | 6/6（含 I11 边界） |
| `test_mto_consignment_flow.py` | 2/2 |
| `test_inventory_schema.py` | 12/12 |
| `test_inventory_posting.py` | 23/23 |
| `test_inventory_receipt_bridge.py` | 通过 |
| `test_inventory_transfer_bridge.py` | 9/9 |
| P6b 序列号（tracking/transfer/adjustment） | 9/9 + 5/5 + 7/7 |

- 已知既有失败（与 INV-2 无关）：`test_server_app_integration.py` 2 例（hello_world 路由 404）、`test_sales_order_fulfillment_status.py` 1 例（`test_inv1_single_writer`）。
- 本期未接入：收货/工单/调拨的 trace 继承（仅提供 `DemandTraceService.inherit_from_document` 服务 API）；发运已接入。

### 10.2 细化验收（2026-11-05，已实施）

| 项 | 状态 |
|---|---|
| §3.3 单义模型、档位映射、`closed` 状态表 | ✅ 文档完成 |
| §3.4 互斥消费规则（库存段行 / 未来供应 / 计划型） | ✅ 文档完成 |
| §4.2 ATP 口径（`valid_to` 读取时判定、`scope`、`shortage`、在途扣减） | ✅ 文档完成 |
| §8.14–8.19 不变量 | ✅ 文档完成 |
| 代码实现（需求守卫、`closed`、互斥校验、投影解耦、在途扣减） | ✅ 已实施 |
| §9.1 新增用例 | ✅ 已实施（预留服务 18、ATP 6、trace 7 全绿） |
| 工单组件级 soft 预留（A3） | ✅ 已实施（`expand_components` + 工单写后置钩子） |

---

## 11. 迁移与风险

- **v205 单迁移**：加列 → 建表 → 枚举/权限/菜单 → 重建唯一键 → 存量回填 `owned`；
- 唯一键重建前先建新索引、再删旧索引，避免中途无索引；
- 回填只按“默认 owned”，不做历史项目猜测；需要时另跑清洗脚本；
- 风险：段行爆炸（SO 默认关闭缓解）、双写不一致（段变更只走服务层）、ATP 性能（按段索引）、重建耗时（分批 org）。
- **回滚（downgrade）**：仅当 `inventory_transactions` 无任何非 `owned` 段数据时，才允许删列 / 删表；否则保留结构并报错，交人工清洗后再回滚。`qty_reserved` 投影列不随降级删除，只停止回写。
- **v218（2026-11-05）**：重建 `inventory_reservations` 表，status CHECK 增加 `closed`；保留数据与索引，降级把 `closed` 回写为 `cancelled`。语义、ATP 口径、互斥校验仍在服务层与读取层。
- **含在途 ATP（2026-11-05）**：`atp(include_inbound=True)` 只扣已 hard 钉住的未收货未来供应（PO 行 / 工单 / 调拨行），不引入 `expected_receipts`；`available_on_hand` 的含在途分支继续报 `ATP_INBOUND_UNSUPPORTED`。
- **工单组件预留（2026-11-05）**：不新增表/迁移。`work_order_component` 作需求节点，统一 soft；幂等键 `WO-COMP-{work_order_id}-{structure_line_id}` 以结构行稳定，重展开只更新数量与组件 id，结构行消失或工单取消/关闭时释放。
- **关单前置校验（2026-11-05）**：通用 BO 更新 `status → Closed` 时，`ProjectTaskGuardInterceptor` 调 `assert_source_closable('work_order', id)`；仍有活跃未核销组件承诺则拒绝（`INV_RESERVATION_ACTIVE_ON_CLOSE`）。取消（`Cancelled`）不走该校验，按显式释放语义处理。
- **组件任务段（2026-11-05）**：`expand_components` 重建组件时按 `structure_line_id` 保留逐组件 `project_task_id`，无值时继承工单头任务；重展开的 DELETE/INSERT 不再抹掉任务覆盖。组件预留据此落到各自任务段，而非全部堆在头任务段。旧库缺列时自动跳过写入（`_insert` 列探测）。
- **组件核销链路（2026-11-05）**：P6c 不建领料单据，完工收货即唯一的组件消耗事件；`ReceiptService._post_work_order` 过账后按累计净完工量调 `fulfill_work_order_components`。目标量由结构行反推工单数量（`(qty_required/(1+scrap) − fixed)/qty_per`），按比例累进核销；`qty_per` 缺失按整单处理；optional 组件不自动核销。只进不退——红冲保留谱系，组件退回需走独立退料流程。预留层失败仅告警，不阻断完工过账。

---

## 12. 演进路线：L0（当前）→ L1（ATP）→ L2（CTP / MIP）

> 大方向已定：后续要构建**真正意义上的 ATP**（含日期与供应来源）与 **CTP**（产能承诺），并由 MIP（计划引擎）供给计划。为避免返工，当前 L0 必须按下面的边界落。

### 12.1 三层职责

| 层 | 名称 | 输入 | 输出 | 现在做？ |
|---|---|---|---|---|
| **L0** | 库存承诺层（本 spec，INV-2） | 现有库存 + 预留事实 | `available_on_hand`（ATR）、`shortage`、简化 `atp` | ✅ 现在 |
| **L1** | 可承诺层（Promise Service） | L0 原子量 + 在途/计划供应 + 时区 | **承诺日期 + 数量** | ⏳ 下一步 |
| **L2** | 产能承诺层（CTP） | L1 + 产能日历 / 工艺路线（MIP 提供） | 可承诺产能、建议计划单 | 🔜 后续 |

### 12.2 三条"不返工"铁则

1. **预留表永不存日期、供应来源、产能**——只存承诺量。L1/L2 通过叠加实现，而不是改 L0 表。
2. **上层只通过 `snapshot(segment, scope)` 读 L0 原子量**（on_hand / reserved / shortage / pegs），禁止直读 `inventory_balances` 或预留表。
3. **方法名分级，契约冻结**：`available_on_hand`(ATR) → `atp`(L0 简化) → `promise`(L1) → `ctp`(L2)。**不得给 `atp` 加日期参数**，日期能力属于 L1 的 `promise`。

### 12.3 启动条件（进入下一层前必须满足）

| 进入 | 条件 |
|---|---|
| L0 → L1 | §8.14–8.19 六条新不变量全部有测试且绿；供应计划（在途/计划订单）有稳定数据源 |
| L1 → L2 | `promise` 能稳定给出交期；产能日历/工艺路线可用；MIP 与库存层的边界书面确认 |

### 12.4 当下落地顺序（L0 收口）

1. 互斥消费校验（R15）；2. 需求上限守卫；3. `valid_to` 读取过滤；4. 投影解耦；5. `closed` 终态；6. `shortage` 视图；7. 工单/服务单接入 soft 预留（A3 最小闭环）——工单组件级已完成，服务单待其备件批次落地；8. 工单关闭前置校验——有未核销组件承诺时拒绝 `Closed`。
