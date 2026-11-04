# MTO / ETO 场景下的库存段与需求线索统一方案（设计稿）

- 日期：2026-11-04
- 状态：设计稿（待口径确认；不直接进入实现）
- 关联：
  - `spec-demand-pegging-oracle-2026-11-04.md`（需求线索分层）
  - `spec-inventory-project-pegging-oracle-sap-2026-11-04.md`（项目/WBS/SO 维度对标）
  - `spec-project-g15-eto-oracle-vs-sap-2026-11-04.md`（G15 ETO 结论）
  - `spec-project-g15-finance-boundary-2026-11-04.md`（库存与财务边界）
  - `docs/specs/inv2-reservation-atp/spec.md`（INV-2 落地规格，v205）

---

## 0. 结论速览

| # | 结论 |
|---|---|
| D1 | **需求线索永远是关系**（`demand_trace_links`），不落到业务对象单列上；跨采购/工单/库存/发运/财务统一。 |
| D2 | **库存段是有限枚举 + 强类型伙伴列**：`owned` / `project_task` / `sales_order_line` / `supplier_consignment` / `customer_owned`。不引入 SAP 式单一 `special_stock` 开关。 |
| D3 | 段维度进**事务列 + 余额键**；自有库存用 `owned` + 0 哨兵，避免 NULL 唯一索引问题。 |
| D4 | **SO 段默认不做**：MTO 标准场景用「预留 + 硬钉 + pegging」实现，on-hand 仍是组织自有；仅“客户专用物料 / 需按 SO 独立估值 / 必须物理隔离”时按物料策略开启 SO 段。 |
| D5 | **ETO 项目段默认做**：`project_task` 是真实库存段（项目拥有、按 WBS 估值、只对项目可用）。 |
| D6 | 寄售/客供料用**所有权段**：`supplier_consignment`（消耗时转移所有权并计价）、`customer_owned`（非估值、只对客户可用）。 |
| D7 | 需求线索支持**多对多 + 部分分配**；硬钉/软钉是关系属性，不是库存字段。 |
| D8 | 批次只做物理 lot 身份，动态属性只做长尾筛选；**都不承载线索或库存段**。 |

---

## 1. 场景矩阵

| 场景 | 供应来源 | 库存归属 | 是否物理分段 | 关键诉求 |
|---|---|---|---|---|
| MTS 备货 | 计划/PO/工单 | 组织自有 | 否 | 公共池 ATP、批量效率 |
| MTO 标准 | SO 行驱动工单/PO | 组织自有 | **默认否** | 不被其他订单抢占，但可共享余料 |
| MTO 客户专用 | SO 行驱动 | 组织自有但专用 | **是（SO 段）** | 客户专用物料、独立估值、监管隔离 |
| ATO 配置 | 通用组件 + 装配 | 组件公共池，成品挂 SO | 组件否/成品可选 | 组件共用、装配级 pegging |
| ETO 项目 | 项目任务驱动 | **项目/任务拥有** | **是（任务段）** | WBS 成本、项目独占、跨项目禁发 |
| 供应商寄售 | 供应商备货 | 供应商拥有 | **是（所有权段）** | 消耗时转移所有权与计价 |
| 客户所有/客供料 | 客户提供 | 客户拥有 | **是（所有权段）** | 非估值、只用于该客户 |
| 退货 | 原发运反向 | 视原段 | 继承原段 | 回到原段或释放到自有 |

---

## 2. 核心分歧：SO 要不要做物理库存段

### 2.1 SAP 路线（`E` 销售订单库存）

- 收益：物理隔离、可按 SO 独立估值、可用量天然只对该 SO 可见；
- 代价：余额键变宽、同物料多 SO 产生大量段行、余料/转用需显式转移、MTS 与 MTO 混合时池子碎片化。

### 2.2 Oracle 路线（reservation / pegging）

- 收益：on-hand 保持组织自有，ATP 由预留扣减，余料可共享；段行不爆炸；
- 代价：物理上不隔离（客户专用物料可能被误用，需靠硬钉与校验兜底）；独立估值需另建成本对象。

### 2.3 平台裁决：**默认 Oracle，按策略可选 SAP**

判据（满足任一才开启 SO 段）：

1. 物料为客户专用/唯一件，物理混用会造成不可逆后果；
2. 需要按 SO 独立归集成本或独立估值；
3. 法规/质量要求按客户隔离（如客户签署放行）；
4. 同一物料同时存在 MTS 与 MTO，且业务不接受“余料共享”。

其余 MTO 场景：`owned` 段 + 预留（hard/soft）+ pegging，不建 SO 段。

> 这样既避免 SO 段爆炸，又保留“需要时能隔离”的能力；策略挂在物料/订单类型上，不写死在代码里。

---

## 3. 统一模型

### 3.1 三层结构

| 层 | 载体 | 生命周期 | 作用 |
|---|---|---|---|
| 即时来源 | 各业务对象的 `source_*` 字段（已有） | 写入即定，不可重算 | 审计、幂等、直接上游 |
| 需求线索 | `demand_trace_links` | 分配/计划时生成，可重算 | 最终需求追溯、硬/软钉、部分分配 |
| 库存段 | 事务列 + 余额键 | 随库存事务持久化 | 可用量隔离、所有权、估值归属 |

### 3.2 库存段定义

`stock_segment_type`（VARCHAR 20，默认 `owned`）：

| 值 | 语义 | 伙伴列 | 估值 | ATP 范围 |
|---|---|---|---|---|
| `owned` | 组织自有公共库存 | 无（0 哨兵） | 是 | 公共池 |
| `project_task` | 项目任务拥有 | `project_id` + `project_task_id` | 是（按 WBS） | 仅该项目任务 |
| `sales_order_line` | 销售订单行专用 | `sales_order_line_id` | 是（可按 SO） | 仅该 SO 行 |
| `supplier_consignment` | 供应商寄售 | `owner_party_id`（供应商） | 否（消耗时转自有计价） | 可消耗，触发所有权转移 |
| `customer_owned` | 客户所有/客供料 | `owner_party_id`（客户） | 否 | 仅该客户订单 |

强类型列（不建通用 EAV 段）：

- `project_id`、`project_task_id`、`sales_order_line_id`、`owner_party_id`；
- CHECK 约束：段类型与伙伴列一一对应；`project_task` 必须同时有 `project_id`（由任务反查校验）。

### 3.3 事务与余额

```text
inventory_transactions 增列：
  stock_segment_type, project_id, project_task_id,
  sales_order_line_id, owner_party_id

inventory_balances 增列 + 唯一键：
  (tenant, org_id, location_id, item_id, batch_id, stock_status,
   stock_segment_type, project_id, project_task_id,
   sales_order_line_id, owner_party_id)
```

- 自有段：段列全部为 0；余额唯一键不放 NULL。
- 事务列与余额键同时冗余保存段维度，保证可回溯、可重建。

### 3.4 预留与 ATP（INV-2）

`inventory_reservations` 至少包含：

- 需求节点：`demand_object_type/id/line_id`（SO 行 / 项目任务 / 工单组件 / 服务单）；
- 供应节点：`supply_object_type/id/line_id`（on-hand 段行 / PO / 工单 / TO）；
- `peg_type`：`hard` / `soft`；
- `reserved_qty`、`fulfilled_qty`、状态、有效期。

ATP：

```text
available(seg) = on_hand(seg) - hard_reserved(seg) - soft_allocated(seg 按策略)
```

- `owned`：可服务 MTS 与软钉 MTO；
- `project_task`：仅该项目任务可用，跨项目需显式转移；
- `sales_order_line`：仅该 SO 行可用；
- `supplier_consignment`：消耗即所有权转移；
- `customer_owned`：不进入公共 ATP。

### 3.5 需求线索

沿用 `demand_trace_links`：

- `supply_node`：库存段行 / PO 行 / 工单 / TO；
- `demand_node`：SO 行 / 项目任务 / 预测 / 服务单；
- `allocated_qty` 支持部分分配；`peg_type` 支持硬/软；
- 事务型 trace 不可重算；计划型 trace 可带 `plan_version` 重算。

---

## 4. 场景决策矩阵

| 场景 | 段类型 | 预留/钉 | 估值 | 关键规则 |
|---|---|---|---|---|
| MTS | `owned` | 无 | 是 | 公共池，先到先得 |
| MTO 标准 | `owned` | SO 行 soft/hard 预留 | 是 | 不建段；取消即释放 |
| MTO 客户专用 | `sales_order_line` | hard | 是（可独立） | 只对该 SO 可用；余料需转移 |
| ATO | 组件 `owned`；成品可选 `sales_order_line` | 装配级 hard | 是 | 组件共用，成品按 SO |
| ETO | `project_task` | hard | 是（WBS） | 跨项目禁发；任务关闭即释放 |
| 供应商寄售 | `supplier_consignment` | 按消耗 | 否→消耗计价 | 消耗时所有权转移 |
| 客户所有 | `customer_owned` | 按客户 | 否 | 不进入公共 ATP |
| 退货 | 继承原段 | 无 | 继承 | 原段有效则回原段，否则转自有 |

---

## 5. 关键流程

### 5.1 MTO 标准（不建 SO 段）

```text
SO 行（需求节点）
  → 计划/工单/PO（供应节点）
  → 收货（继承 SO 行引用 + trace）
  → 库存 owned 段（预留占用）
  → 发运（核销预留与 trace）
```

- 取消：释放预留与 trace；
- 部分发运：`allocated_qty` 分段核销；
- 超产/余料：留在 `owned`，可被其他需求使用（策略允许时）。

### 5.2 MTO 客户专用（SO 段）

```text
SO 行 → 采购/工单 → 收货进 sales_order_line 段
     → 发运只允许该段
     → 取消/余料：显式转移至 owned（原因 + 审批）
```

### 5.3 ETO（项目任务段）

```text
项目任务（需求节点）→ 项目采购/工单 → 收货进 project_task 段
  → 项目发料/发运 → 项目关闭：余料转 owned 或报废
```

- 跨任务发料默认拒绝；同一 planning group 且开关允许才放行；
- 任务层级校验（子任务可继承父任务段，需显式规则）。

### 5.4 供应商寄售

```text
收货进 supplier_consignment（owner=供应商，非估值）
  → 消耗：写“所有权转移”事务 → 转 owned → 生成应付/计价
```

### 5.5 跨段转移

统一为显式“段转移”事务，禁止用普通发料/收货模拟：

- `owned → project_task`（项目领用）；
- `sales_order_line → owned`（SO 取消/余料）；
- `supplier_consignment → owned`（寄售消耗）；
- 项目间/项目与 SO 间需原因 + 审批 + 数量上限校验。

---

## 6. 不变量（服务层强制）

1. 一条余额行只能有一个段类型，伙伴列必须匹配；
2. 段一旦形成，只能通过段转移事务改变；
3. `project_task` 必须属于 `project_id`，且组织一致；
4. `sales_order_line` 必须属于同物料同客户，且订单未关闭；
5. 非估值段（寄售/客供料）不产生库存金额与科目；
6. 硬钉供应不得重复分配给其他需求；
7. 段内可用量不得为负；公共池不得挪用已硬钉/项目/客供料库存；
8. 退货优先回原段；原段失效才转自有；
9. 需求线索与库存段不得互相替代：SO 段行仍需 trace 到 SO 行；
10. 跨段转移必须留原因、操作人、原段/目标段快照。

---

## 7. 取舍分析

### 7.1 为什么不用通用 `stock_segment_id` 维度表

- 段类型是**有限已知集合**（上述 5 类），强类型列能保留外键、索引、报表直查；
- 通用段表只是把校验推迟到运行期，仍要为每种伙伴列加列，收益不大；
- 余额键已包含段列，通用段反而多一次 join，重建更慢。

> 若未来出现第 6 类段（如 3PL owner、监管库），再加枚举值与列，属于受控迁移。

### 7.2 为什么不用批次承载

- 批次是物理/质量 lot；SO/项目是逻辑归属；
- 用批次承载会把批次切成“每单一批”，破坏质量、效期、COA 与谱系；
- 项目专用批次可在批次上记 `project_id` 作为提示，但不进余额键。

### 7.3 为什么不用动态属性承载

- EAV 无外键/唯一约束/索引，撑不起余额键与 ATP；
- 属性适合长尾筛选（合同阶段、资金来源），不适合段与线索。

---

## 8. 分期建议

| 阶段 | 内容 | 前置 |
|---|---|---|
| **S1 段铺底** | 事务/余额加段列；余额键重建；`owned` 与 `project_task` 先行；单据行补 `project_task_id` | INV-1 |
| **S2 预留/ATP** | `inventory_reservations` 带需求节点与 peg_type；按段 ATP；MTO 标准走 soft/hard 预留 | S1 |
| **S3 需求线索** | `demand_trace_links` 上线；SO/项目/PO/工单/发运接入；端到端视图 | S2 |
| **S4 SO 专用段** | `sales_order_line` 段 + 物料策略开关；跨段转移与审批 | S3 |
| **S5 所有权段** | 寄售/客供料；所有权转移事务；非估值规则 | S4（可并行） |
| **S6 估值** | 段级估值（含 SO 段独立估值）交 INV-5 | S5 |

---

## 9. 风险

| 风险 | 缓解 |
|---|---|
| 余额键扩展导致重建失败 | 先加列 → 重建 → 再收紧唯一键；保留 `inventory_rebuild` 可重算 |
| SO 段爆炸 | 默认关闭，按物料策略开启；监控段行数 |
| 段与 trace 双写不一致 | 段变更只走服务层；trace 与段在同一事务写入；定期对账脚本 |
| 历史数据无段 | 存量归 `owned`；可按单据 project 回填项目段，其余标记待清洗 |
| 跨段误操作 | 段转移独立动作 + 审批 + 不变量校验 |
| 性能 | 余额索引按 `(org, item, segment_type, project_task_id)`；ATP 查询避免全表 |

---

## 10. 口径建议（基于 SAP / Oracle）

| # | 口径 | SAP 做法 | Oracle 做法 | 建议 |
|---|---|---|---|---|
| 1 | SO 段是否默认开启 | MTO 标准通常用特殊库存 `E`，绑定 SO 行 + 客户，可独立估值；MTS 不建段 | 无 SO 实体库存，靠 reservation / pegging 表达 SO 归属 | **默认关闭，按物料/订单类型策略开启**；仅“客户专用 / 独立估值 / 法规隔离 / 混合模式不接受共享”四类开启 |
| 2 | 项目段粒度 | `Q` 固定绑 **WBS 元素**（任务级） | PJM control level 可选 Project/Task；Fusion on-hand 明细含 `PROJECT_ID` + `TASK_ID` | **固定任务级**；单任务项目自动建根任务，不引入 project 级段 |
| 3 | 第一版是否纳入寄售/客供料 | `K` 供应商寄售成熟；客户所有/客供料用独立标识 | 供应商寄售原生支持（owning party + 消耗转移）；**客户所有权库存无原生实体模型** | **纳入供应商寄售**；客供料延后；段键从 S1 就保留 `owner_party_id`，避免二次迁移 |
| 4 | SO 段是否独立估值 | `E` 支持有/无估值，按评估类配置 | SO 不单独估值，项目库存按项目成本归集 | **库存层不做金额**；段上留 `valuation_relevant` 标记，金额与科目交 INV-5；SO 段默认 `valuation_relevant = 1` |

### 10.1 建议的默认参数

| 参数 | 建议值 | 依据 |
|---|---|---|
| `stock_segment_policy`（物料/分类） | `owned` | MTS 与大多数 MTO 标准场景 |
| `so_segment_default` | `off` | 避免 SO 段碎片化；Oracle 路线 |
| `project_segment_level` | `task` | SAP `Q` = WBS；Oracle 任务级明细 |
| `allow_cross_project_issue` | `0` | SAP 只允许为该 WBS 领料；Oracle PJM 默认禁止 |
| `enable_supplier_consignment` | `1`（S5 实现） | 所有权维度必须早进键 |
| `enable_customer_owned` | `0`（后续版本） | Oracle 无原生模型，需先定非估值与 ATP 规则 |
| `segment_valuation_enabled` | `0`（INV-5 开启） | 库存层只回答数量与归属 |
| `hard_peg_default` | 按订单类型（MTO/ETO 为 `1`） | SAP/Oracle 硬钉语义 |

> 以上为专业建议，仍需业务确认后固化为 INV-2 Spec 的决策项。
