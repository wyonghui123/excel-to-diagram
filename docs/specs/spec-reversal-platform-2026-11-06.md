# 逆向能力平台化规格（Reversal Platform）

* 状态：**提案（待评审）**

* 日期：2026-11-06

* 关联：

  * `docs/specs/spec-doc-flow-single-fact-model-2026-11-05.md`（单一事实模型，D1-D8）

  * `docs/specs/spec-phaseA-doc-flow-single-fact-2026-11-06.md`（阶段 A 已实施：事务边界 / 补偿边 / 计划行重算）

  * `docs/specs/spec-doc-flow-end-to-end-2026-11-05.md`（端到端基线）

* 适用范围：`ActionExecutor` 状态过渡委托链、`doc_effect` 元数据、`ReversalOrchestrator`、
  各单据服务的 `reverse()` 入口

* 性质：**元数据驱动的平台能力** + **一个正向对象补充（采购退货）**；不改变库存过账语义、不重写派生引擎

***

## 1. 背景与问题

### 1.1 出发点

业务模型优先表达**正向**流程（下单 → 发运 → 过账）。「逆向」（取消 / 红冲）不应是每类单据
独立实现的业务特例，而应是正向模型**自然具备**的派生能力。这与单一事实模型的结论一致：

> 一条事实不可变，修正是**对某事实键追加补偿**——这是一个**通用操作**，与业务类型无关。

### 1.2 现状：原语已通用，编排是重复的

经代码核实（证据等级 C），四个逆向原语**全部按事实键工作**，不依赖业务类型：

| 原语                                                                   | 位置                                                                                   | 定位方式               |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------ |
| `InventoryPostingService.reverse_by_source(original_event_key, ...)` | [inventory\_posting\_service.py](../meta/services/inventory_posting_service.py#L209) | `source_event_key` |
| `InventoryPostingService.reverse(transaction_ids, ...)`              | [inventory\_posting\_service.py](../meta/services/inventory_posting_service.py#L253) | 分录 id              |
| `SerialNumberService.reverse_serial_event(inventory_transaction_id)` | [serial\_number\_service.py](../meta/services/serial_number_service.py#L607)         | 库存事务 id            |
| `compensate_edge(app_ds, orig_edge_id, ref_id=...)`                  | [doc\_flow\_reversal.py](../meta/core/doc_flow_reversal.py#L346)                     | 边 id               |

`inventory_adjustment_service.reverse()` 就是纯拼装这几个原语（[L256-L291](../meta/services/inventory_adjustment_service.py#L256-L291)），
与 `shipment_service.reverse()` / `receipt_service.reverse()` 使用同一套底层。

### 1.3 真正重复的五件事

| #  | 重复项         | 现状（每服务各写一遍）                                                                                  |
| -- | ----------- | -------------------------------------------------------------------------------------------- |
| R1 | 前置状态守卫      | `from_states` 判定 + 错误码（`DN_STATE_INVALID` / `RC_REVERSAL_INVALID` / `INV_ADJ_STATE_INVALID`） |
| R2 | 幂等探测        | 已冲销 → 返回 replay（三处独立实现）                                                                      |
| R3 | **写面倒序编排**  | 库存 → 序列号 → HU → 预留 → 边 → 计划行，顺序写死在各服务方法体内                                                    |
| R4 | 事务边界        | `_atomic` / `with self.ds.transaction()` 各自包裹                                                |
| R5 | 投影重算 + 履约派生 | `_refresh_schedule_delivery` / `recompute_order` 各自调用                                        |

新增单据类型时，上述五件事必须**再抄一遍**，且容易漏（如 G4：调拨发货至今无红冲入口）。

### 1.4 关键有利条件

状态过渡**已经是声明式的**：schema `rules` 段已用
`type: state_transition` + `from_states` + `to_state` + `triggers: [before_update]` 表达
（[shipment.yaml L522-L606](../meta/schemas/shipment.yaml#L522-L606)）。

因此平台化**不需要新造状态机**，只需在同一份声明旁边补一个「写面清单」，逆向即由清单镜像得出。

***

## 2. 目标与非目标

### 2.1 目标

1. **正向声明一次，逆向自动派生**：新增单据类型只需写 YAML，不写 Python 编排。
2. **五件事单点实现**：守卫 / 幂等 / 顺序 / 事务 / 投影重算只有一份代码。
3. **失败即全回滚**：任一写面异常，整个业务动作不留半真事实。
4. **未声明即拒绝**：没有 `doc_effect.reversal` 声明的单据，平台拒绝逆向（不静默成功）。
5. **可静态校验**：声明与状态机、原语注册表在启动/测试期交叉校验。
6. **补齐逆向的业务前提**：新增采购退货正向对象（退货采购单 + 退货出库），
   使「采购到出库」闭环可被平台逆向覆盖（§11）。

### 2.2 非目标

* **不把「退货」纳入逆向编排**。退货是正向新事实（新单 + 新过账事务），见 §3.2；
  其中销售退货已存在，采购退货缺失属正向对象缺口，由 §11 补齐（仍不走 Orchestrator）。

* 不重写 `doc_flow_derive_engine` 的派生算法。

* 不引入新数据库 / 消息队列 / 事件存储。

* 不改库存过账的科目与成本语义。

* 不做跨库分布式事务（跨库场景留给 P2 的 outbox）。

* 不改造 `cancel`（取消无副作用，仅状态流转，保持现状）。

* **不实现 Oracle 式「退货后重开原 PO 未收量」**：退货单独立、原 PO 不变（SAP 路线）；
  需要补货时新建普通 PO。

* **不实现** **`RETURN TO RECEIVING`（退到收货区待检）**：仅保留 `return_to` 枚举占位，
  本期只支持 `supplier`。

* **不实现「无原收货的供应商退货」**（Oracle Fusion 的 Manage Supplier Returns Without Receipt）：
  本模型的退货必须可回指原单（D16），无原单则无 `origin_receipt_id` / `origin_purchase_order_id`，
  与单一事实模型冲突。若未来需要，应新建独立 `supplier_return` 单据，不复用 `receipt`。

***

## 3. 术语与边界

### 3.1 术语

| 术语                       | 定义                                                     |
| ------------------------ | ------------------------------------------------------ |
| **写面（face）**             | 一次业务过账会写入的一个持久化面：库存事务、序列号事件、HU 事件、预留台账、单据流边、计划投影       |
| **逆向原语（primitive）**      | 按事实键抵消某一写面的通用函数，签名统一为 `(ds, args, ctx) -> FaceResult`  |
| **doc\_effect**          | schema 中声明「正向写面清单 + 逆向过渡条件」的元数据段                       |
| **ReversalOrchestrator** | 读取 doc\_effect、倒序执行原语、统一事务与投影重算的通用执行器                  |
| **业务权威锚（ref）**           | 冲销依据的业务单号（`reversal_no` / 红字单号），写入边 `derive_key` 与规则后缀 |

### 3.2 逆向 vs 退货的边界（必须明确）

| 语义            | 事实方向          | 是否新单     | 是否走 Orchestrator    |
| ------------- | ------------- | -------- | ------------------- |
| 取消 cancel     | 无事实           | 否（原单作废）  | ❌ 保持状态机直转           |
| 红冲 reverse    | **负向补偿**      | 否（原单保留）  | ✅ 本规格范围             |
| 退货 return（销售） | **正向新事实**（入库） | 是（退货订单）  | ❌ 走正向过账链            |
| 退货 return（采购） | **正向新事实**（出库） | 是（退货采购单） | ❌ 走正向过账链；对象由 §11 新增 |

结论：本规格只平台化 **reverse**。销售退货已具备；采购退货缺失是**正向对象缺失**，
不是逆向缺陷——由 §11 以「复用采购订单 + 收货单」的方式补齐，不新建独立 BO。

***

## 4. 外部基准

| 产品                   | 逆向机制                                                             | 与本规格的对应                         |
| -------------------- | ---------------------------------------------------------------- | ------------------------------- |
| SAP                  | 取消单据（`VBRK-FKSTO`）+ 新 VBFA 行；原行不改                                | 补偿事实 + 原事实保留                    |
| Oracle（EBS / Fusion） | 新增反向/调整事务行，原事务不可编辑；仅当**没有原事务可挂**（无收货退货）时才出现独立 Supplier Return 单据 | `reverse_by_source` 追加 REVERSAL |
| NetSuite             | Credit Memo / Item Receipt → 新 link                              | 业务锚 ref + 补偿边                   |
| Dynamics 365         | storno 负数事务保留原记录                                                 | `quantity_sign` 反转              |
| 事件溯源                 | 补偿事件表达撤销                                                         | Orchestrator 即补偿事件编排器           |

**共性结论**：四家产品的撤销都是「按原事实键追加反事实」，且**都由单据保存动作统一触发**，
而不是各模块自建通道——这正是本规格把编排下沉到平台的依据。

***

## 5. 现状诊断（G1-G7）

| 编号     | 现象                                  | 证据                                                                                     | 影响                     |
| ------ | ----------------------------------- | -------------------------------------------------------------------------------------- | ---------------------- |
| **G1** | 写面编排在服务方法体内硬编码                      | `shipment_service.reverse()` / `receipt_service.reverse()` / `adjustment.reverse()` 三处 | G4 类漏实现                |
| **G2** | 逆向守卫错误码三套                           | `DN_STATE_INVALID` / `RC_REVERSAL_*` / `INV_ADJ_STATE_INVALID`                         | 前端需按单据分支处理             |
| **G3** | 幂等探测三套                              | 各自查状态 / 查红字单 / 查 derive\_key                                                           | 边界行为不一致                |
| **G4** | 调拨发货侧无红冲                            | `TO_SHIPPED_CANNOT_CANCEL`，仅提示「改走反向调拨」                                                 | 录错只能盘点调整               |
| **G5** | 未声明逆向的单据静默无能力                       | 无声明即无入口，无平台级拒绝                                                                         | 调用方无从判断是否支持            |
| **G6** | 采购退货（退货给供应商）无正向对象                   | 无 `purchase_return` schema；`inventory_transaction_types` 无出库退货类型                       | 「采购到出库」闭环缺失，红冲无法替代业务退货 |
| **G7** | `document_category='return'` 两侧语义相反 | 收货侧 `return` = 红字（`reversal_of_receipt_id` 必填、不独立过账）；交货侧 `return` = 业务退货               | 采购退货无法沿用同一枚举，基础语义不一致   |

**覆盖矩阵（正向 / 逆向）**

| 单据对象               | 正向写面                      | 取消     | 红冲         | 业务退货                |
| ------------------ | ------------------------- | ------ | ---------- | ------------------- |
| 交货 `shipment`      | 库存·边·序列号·HU·预留·计划行        | ✅      | ✅ 端到端      | ✅ 正向退货交货            |
| 收货 `receipt`       | 库存·边·计划行·分配·序列号·HU        | ✅      | ✅ 端到端      | ⚠️ 红字有、业务退货无（§11 补） |
| 调拨 `transfer`      | 出库事务·边·序列号 ／ 收货侧借 receipt | ✅ 仅发货前 | ✅ 发货侧已接管（D5） | ⚠️ 反向调拨未挂链接（Q3 复用 `reversal_of_transfer_id`） |
| 库存调整 `adjustment`  | 库存事务                      | ✅      | ✅ 端到端      | n/a                 |
| 工单 `work_order`    | 完工收货（借 receipt）           | 借道收货   | 借道收货红冲     | n/a                 |
| 销售订单 `sales_order` | 计划行·履约状态                  | ✅      | n/a（无库存事实） | ✅ 退货订单类型            |

***

## 6. 决策

| 编号      | 决策                                                                               | 理由                                                             |
| ------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **D1**  | 逆向能力下沉为**元数据声明 + 通用执行器**，不下沉为「通用 reverse 函数」                                     | 守卫/顺序有业务差异，声明可表达差异；硬编码函数无法表达                                   |
| **D2**  | 只声明**正向写面清单**，逆向由清单**倒序镜像**                                                      | 实现「逆向自然具备」；避免正/逆两套声明漂移                                         |
| **D3**  | `doc_effect` 作为 schema 顶层段，与 `rules` 并列                                          | 状态机已在 `rules` 声明，不新造机制                                         |
| **D4**  | 挂载点 = `state_transition` 的 `to_state == doc_effect.reversal.to_state`            | 复用既有 `before_update` 委托链                                       |
| **D5**  | 执行器自持事务（嵌套透传），不依赖 `ActionExecutor` 的外层事务                                         | 阶段 A 已证实钩子早于事务（R-SF-01）                                        |
| **D6**  | 原语必须**幂等**且**按事实键定位**；契约由注册表强制                                                   | 保证重放安全、避免依赖执行顺序                                                |
| **D7**  | 写面执行序默认 `inverted`（倒序），可由声明覆盖                                                    | 与正向对称；避免外键悬挂                                                   |
| **D8**  | 无声明 = 平台**拒绝**（`REVERSAL_NOT_DECLARED`），不静默                                      | 消除 G5                                                          |
| **D9**  | 投影重算在 faces 之后、同一事务内执行                                                           | 投影是事实的函数；跨事务会产生半真投影                                            |
| **D10** | 分阶段接管：先 adjustment → receipt → shipment → transfer，白名单开关                         | 降低回归面；每阶段保留旧实现做对照                                              |
| **D11** | 「退货」不进 Orchestrator，另立正向对象                                                       | 语义不同（§3.2）                                                     |
| **D12** | 采购退货**复用** `purchase_order` + `receipt`，不新建独立 RTV BO                             | 与销售退货对称；复用编号/审批/行/计划行/单据流；避免同语义两套对象                            |
| **D13** | `document_category` 统一三值：`standard` / `return` / `red`                           | 修正 G7：`return` 恒为业务退货、方向由对象决定；`red` 恒为纠错凭证                     |
| **D14** | 过账方向**只由类型类别决定**：收货 `standard→in`、`return→out`、`red→不独立过账`                       | 消除服务内 `is_return` 布尔分支的歧义                                      |
| **D15** | 新增移动类型 `RETURN_TO_VENDOR`（`direction='out'`）与规则 `receipt_line_to_return_out_txn` | 退货出库是新事实；追溯净贡献为负                                               |
| **D16** | 退货单必须可回指原单（`origin_purchase_order_id` / `origin_receipt_id`，至少其一）                | 补齐追溯链，回答「退的是哪张单」                                               |
| **D17** | 提供「从原收货单一键生成退货单」快捷入口，但复用 D12 链路                                                  | 对应 Oracle RTV 的即时退回形态，不新增模型                                    |
| **D18** | 退货量独立为 `returned_qty`，**不复用** `received_qty`                                     | 对齐 SAP EKBE 的 WE/RE 分流水；复用会污染收货口径                              |
| **D19** | 审批沿用 PO 流程，条件增加 `document_category` 维度                                           | 对齐 SAP release strategy 按 document type 差异化；退货是资产流出，不应降级管控     |
| **D20** | 退货主入口 = 收货详情（带原单与可退量上限），辅以 PO 新建选类型                                              | 对齐 Oracle 单入口 + SAP 双入口；原单是唯一能带出可退量与批次/序列号的来源                  |
| **D21** | **不**重开原 PO 未收量（拒绝 Oracle 路线）；原 PO 保持原状                                          | 退货是独立事实，修改原单会破坏单一事实模型的不可变性                                     |
| **D22** | 红字镜像单由 `reversal.create_document` 声明的**创建器**生成，平台只负责顺序与事务                        | 单据复制是业务语义，写面清单表达不了；声明创建器既保持「正向声明一次」，又不把业务复制逻辑塞进通用编排器（D2 实施时补充） |

***

## 7. `doc_effect` 元数据规格

### 7.1 完整 YAML 示例（以交货单为目标态）

```yaml
doc_effect:
  posting:
    event_key: "shipment:{id}:{direction}"        # 正向过账事件键模板
    direction_field: document_category             # standard | return
  faces:                                           # 正向写面；声明序 = 正向写入序
    - id: inventory
      primitive: inventory_reverse_by_event
      args:
        event_key: "{posting.event_key}"
        new_event_key: "shipment:{id}:reverse"
      on_missing: strict                           # strict | skip
    - id: serial
      primitive: serial_reverse_by_txn
      args:
        txn_ids: "{inventory.txn_ids}"
      on_missing: skip
    - id: hu
      primitive: hu_rewind_by_txn
      args:
        txn_ids: "{inventory.txn_ids}"
      on_missing: skip
    - id: reservation
      primitive: reservation_release_by_demand
      args:
        doc_id: "{id}"
      on_missing: skip
    - id: doc_flow
      primitive: edge_compensate_by_source
      args:
        source_bo: shipment_line
        rule_ids:
          - shipment_line_to_issue_txn
          - shipment_line_to_return_in_txn
        ref: "{reversal.ref}"
      on_missing: skip
  projections:
    - id: schedule_delivered
      primitive: recompute_schedule_delivered
      args:
        doc_id: "{id}"
    - id: order_fulfillment
      primitive: recompute_fulfillment
      args:
        order_id: "{order_id}"
  reversal:
    from_states: [shipped, delivered]
    to_state: reversed
    ref_field: reversal_no                         # 业务权威锚来源
    idempotent_states: [reversed]
    order: inverted                                # inverted | declared
    write_audit_fields:
      reversed_at: "{now}"
      reversal_reason: "{reason}"
```

### 7.2 字段定义

| 路径                                   | 类型     | 必填   | 说明                                                                        |
| ------------------------------------ | ------ | ---- | ------------------------------------------------------------------------- |
| `posting.event_key`                  | string | 否    | 正向过账事件键模板；缺省时 `inventory` 面须改用 `inventory_reverse_by_txn`                 |
| `posting.direction_field`            | string | 否    | 方向字段名（退货单共用同一对象时使用）                                                       |
| `faces[].id`                         | string | ✅    | 写面标识；须在 §8.1 注册表中唯一可辨识                                                    |
| `faces[].primitive`                  | string | ✅    | 原语 id（§8.1）                                                               |
| `faces[].args`                       | map    | 否    | 模板参数，支持 `{id}` / `{posting.*}` / `{<face_id>.txn_ids}` / `{reversal.ref}` |
| `faces[].on_missing`                 | enum   | 否    | `strict` / `skip`，默认 `skip`                                               |
| `faces[].enabled_when`               | string | 否    | 简易条件表达式，如 `direction == 'standard'`（仅支持 `==` / `!=` / `and`）              |
| `projections[].id`                   | string | ✅    | 投影标识                                                                      |
| `projections[].primitive`            | string | ✅    | 投影原语 id                                                                   |
| `reversal.from_states`               | list   | ✅    | 可逆向状态；须与 `rules` 中该过渡的 `from_states` 一致                                   |
| `reversal.to_state`                  | string | ✅    | 逆向终态；须在 schema `status` 枚举中存在                                             |
| `reversal.ref_field`                 | string | 条件必填 | 若存在 `edge_compensate_*` 面则必填（补偿需业务锚）                                      |
| `reversal.idempotent_states`         | list   | 否    | 命中即返回 replay，默认 `[to_state]`                                              |
| `reversal.order`                     | enum   | 否    | `inverted`（默认）/ `declared`                                                |
| `reversal.write_audit_fields`        | map    | 否    | 逆向时一并写入的审计字段（模板值）                                                         |
| `reversal.create_document.primitive` | string | 否    | 红字单创建器 id（创建器注册表）；声明后先建单再执行写面                                             |
| `reversal.create_document.args`      | map    | 否    | 创建器参数模板（占位符规则同 `faces[].args`）                                            |

### 7.3 声明校验规则（启动期 + 测试期）

| 编号  | 规则                                                                                | 违反时                           |
| --- | --------------------------------------------------------------------------------- | ----------------------------- |
| V1  | `reversal.to_state` 必须存在于 schema 状态字段枚举                                           | `DECL_INVALID_TO_STATE`       |
| V2  | `reversal.from_states` 必须等于同 `to_state` 的 `state_transition` rule 的 `from_states` | `DECL_STATE_MISMATCH`         |
| V3  | `faces[].primitive` 必须在 §8.1 注册表内                                                 | `DECL_UNKNOWN_PRIMITIVE`      |
| V4  | 存在 `edge_compensate_*` 面时，`reversal.ref_field` 或面内显式 `args.ref` 至少其一（业务权威锚）       | `DECL_REF_FIELD_REQUIRED`     |
| V5  | `faces[].args` 引用的占位符必须可解析                                                        | `DECL_UNRESOLVED_PLACEHOLDER` |
| V6  | 同一 schema 内 `faces[].id` 唯一                                                       | `DECL_DUPLICATE_FACE`         |
| V7  | `order: inverted` 时 `projections` 仍在 faces 之后执行（不参与倒序）                            | 固定行为，无需校验                     |
| V3+ | `reversal.create_document.primitive` 必须在创建器注册表内                                   | `DECL_UNKNOWN_PRIMITIVE`      |

校验入口：`meta/core/doc_effect_validator.py`，由 schema 加载器在 `load_all` 后统一执行；
失败 → 启动期告警 + 测试期失败（`test_doc_effect_declarations`）。

### 7.4 红字单创建器（`reversal.create_document`）

部分单据（库存调整）的红冲在业务上表现为**新建一张红字镜像单**，而写面清单
只能描述「抵消哪些事实」。为避免把单据复制逻辑塞进平台，声明层增加一个
**创建器引用**：

```yaml
reversal:
  create_document:
    primitive: inventory_adjustment_red_letter
```

执行序：`resolve → guard → txn → create_document → faces → projections → state`。

* 创建器签名 `(ds, ctx) -> dict`，必须在事务内执行，返回至少 `id` / `no`；

* 返回值写入模板作用域 `{reversal.doc.*}`，写面据此引用红字单
  （如 `{reversal.doc.id}` / `{reversal.doc.event_key}`）；

* 返回 `replay: true` 表示红字单已存在：**跳过 faces / projections**，仅推进原单状态
  （对齐既有「重复红冲只置状态」分支）；

* 创建器是业务特许：仅当单据语义要求独立红字凭证时声明，普通单据保持原地冲销。

***

## 8. ReversalOrchestrator 规格

### 8.1 原语注册表（17 个，随 D3 / D4 / D5 扩充）

| primitive id                        | 签名                                                            | 幂等机制                          | 无事实时           |
| ----------------------------------- | ------------------------------------------------------------- | ----------------------------- | -------------- |
| `inventory_reverse_by_event`        | `(ds, event_key, new_event_key) -> {txn_ids, source_txn_ids}` | 新事件键唯一                        | 由 `on_missing` |
| `inventory_reverse_by_txn`          | `(ds, txn_ids, new_event_key) -> {txn_ids}`                   | 同上                            | `skip`         |
| `serial_reverse_by_txn`             | `(ds, txn_ids) -> {count}`                                    | 事件已撤销即跳过                      | `skip`         |
| `serial_reverse_completion`         | `(ds, work_order_id, receipt_id) -> {reversed}`               | 完工序列号状态回退                     | `skip`         |
| `hu_rewind_by_txn`                  | `(ds, txn_ids) -> {count}`                                    | 同                             | `skip`         |
| `hu_reverse_document`               | `(ds, doc_type, doc_id) -> {count}`                           | 倒序回退整单容器事件                    | `skip`         |
| `reservation_release_by_demand`     | `(ds, doc_id) -> {count}`                                     | 已释放即跳过                        | `skip`         |
| `edge_compensate_by_source`         | `(ds, source_bo, rule_ids, ref) -> {created}`                 | `derive_key='rev:<id>:<ref>'` | `skip`         |
| `recompute_schedule_delivered`      | `(ds, doc_id) -> {updated}`                                   | 纯重算（幂等）                       | n/a            |
| `recompute_fulfillment`             | `(ds, order_id) -> {}`                                        | 纯重算                           | `skip`         |
| `recompute_purchase_fulfillment`    | `(ds, order_ids) -> {updated}`                                | 纯重算                           | `skip`         |
| `reverse_schedule_received`         | `(ds, items) -> {updated}`                                    | 按红字净收量回退                      | `skip`         |
| `reservation_unfulfill_by_shipment` | `(ds, doc_id) -> {count, unfulfilled}`                        | 按交货行汇总核销                      | `skip`         |
| `shipment_reverse_lines`            | `(ds, doc_id, now) -> {count}`                                | 不改 cancelled 行                | `skip`         |
| `inventory_reverse_by_source`       | `(ds, source_doc_type, source_doc_id) -> {created, existing, txn_ids, source_txn_ids}` | 事件键逐一镜像，已红冲跳过 | `skip` |
| `transfer_reverse_lines`            | `(ds, doc_id, now) -> {count}`                                | 发货/收货量归零，不改 cancelled 行       | `skip`         |
| `recompute_transfer_fulfillment`    | `(ds, doc_id) -> {updated, fulfillment_status}`               | 纯重算（幂等）                        | `skip`         |

注册表实现：`meta/core/reversal_primitives.py`，`PRIMITIVES: Dict[str, Callable]`。
所有原语必收 `ReversalContext`（含 `ds`、`schema`、`doc_id`、`ref`、`now`、`reason`、
`executed`、`params`）。

### 8.2 公共接口

```python
# meta/core/reversal_orchestrator.py

class ReversalError(Exception):
    """逆向守卫拒绝 / 声明错误 / 原语失败统一异常。"""
    def __init__(self, code: str, message: str, field: str = '', rule: str = ''): ...

@dataclass
class ReversalOutcome:
    doc_id: Any
    to_state: str
    replay: bool = False                # True = 命中幂等状态，零变更
    faces: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    projections: Dict[str, Dict[str, Any]] = field(default_factory=dict)

def execute(ds, *, schema_id: str, doc_id: Any, reason: str = '',
            ref: Optional[str] = None, user_info: Optional[dict] = None) -> ReversalOutcome:
    """按 schema 的 doc_effect 声明执行逆向。# 无声明 → REVERSAL_NOT_DECLARED"""

def supports(schema_id: str) -> bool:
    """该 schema 是否声明了逆向能力（供 API / 前端判定）。"""
```

### 8.3 执行序（固定 7 步）

```
1. resolve   解析 schema 的 doc_effect；缺失 → REVERSAL_NOT_DECLARED
2. guard     读当前状态 → idempotent_states 命中则返回 replay（**不开事务**）
             → from_states 不含则 REVERSAL_STATE_INVALID
             → ref_field 有值则 ref 必须非空，否则 REVERSAL_REF_MISSING
3. txn       with ds.transaction():（对嵌套调用透传）
4. faces     按 order 排序（默认 inverted）逐个调用原语
             任一抛错 → 事务回滚，异常以 ReversalError 抛出
             on_missing='strict' 且写面无事实 → REVERSAL_FACT_MISSING
5. project   执行 projections（依赖 faces 输出；纯重算，幂等）
6. state     写 to_state + write_audit_fields（同事务）
7. commit    提交；事务外不再做写操作
```

### 8.4 错误码（统一命名，替代三套旧码）

| code                         | 含义      | 触发条件                    |
| ---------------------------- | ------- | ----------------------- |
| `REVERSAL_NOT_DECLARED`      | 单据未声明逆向 | 无 `doc_effect.reversal` |
| `REVERSAL_STATE_INVALID`     | 状态不可逆   | 当前状态 ∉ `from_states`    |
| `REVERSAL_REF_MISSING`       | 业务锚缺失   | `ref_field` 必填但为空       |
| `REVERSAL_FACT_MISSING`      | 写面无事实   | `on_missing='strict'`   |
| `REVERSAL_PRIMITIVE_UNKNOWN` | 原语未注册   | 声明引用未知 primitive        |
| `REVERSAL_DECL_INVALID`      | 声明非法    | §7.3 任一校验失败             |
| `REVERSAL_FAILED`            | 原语执行失败  | 原语异常（含底层业务码与原因）         |

兼容：旧服务错误码保留一个版本周期，映射到新码（`DN_STATE_INVALID` → `REVERSAL_STATE_INVALID`
等），前端改造完成后删除映射。

### 8.5 失败语义

| 场景                           | 行为                                                       |
| ---------------------------- | -------------------------------------------------------- |
| faces 中第 k 个原语抛错             | 整个事务回滚（前 k-1 个写面一并撤销），对外抛 `REVERSAL_FAILED`              |
| projections 抛错               | 同上，全回滚                                                   |
| 状态写入失败                       | 同上，全回滚                                                   |
| 幂等状态命中                       | **不开启事务**，直接返回 `replay=True`（零 IO）                       |
| 并发两次同单逆向                     | 第二事务在 `guard` 阶段读到 `reversed` → replay；若在 `state` 阶段冲突 → |
| 唯一键/条件更新失败 → 回滚 → 重读后 replay | <br />                                                   |

### 8.6 与状态机 / ActionExecutor 的集成

```
前端/PUT status  →  ActionExecutor._validate_before_update
                    └─ rule type=state_transition 且 to_state == reversal.to_state
                       └─ ReversalOrchestrator.execute(...)     ← 平台接管
                           （自持事务，原 before_update 事务问题不再存在）
                    └─ 若 schema 无 doc_effect → 回落原委托链（兼容期）
```

要点：

* **状态推进与写面在同一事务**（Orchestrator 自持事务，ActionExecutor 的行更新随后在
  同一连接内完成）。

* Orchestrator 返回 `to_state` 后，ActionExecutor 只做**行更新 + 审计**，不再重复业务写。

* 未声明 `doc_effect` 的对象按 D10 白名单回落旧路径，不中断既有行为。

***

## 9. 投影契约

| 编号 | 契约            | 说明                                                    |
| -- | ------------- | ----------------------------------------------------- |
| P1 | 投影只读事实，不写第二事实 | `recompute_schedule_delivered` 只从 `shipment_lines` 求和 |
| P2 | 投影在同一事务内执行    | 与 faces 同事务；失败即全回滚                                    |
| P3 | 投影必须幂等        | 纯重算（`UPDATE ... SET x = (SELECT SUM ...)`）            |
| P4 | 投影不得依赖执行顺序    | 所有投影在 faces 全部完成后统一执行                                 |
| P5 | 投影可缺席         | 无投影声明的单据照常逆向（如 adjustment 仅有库存面）                      |

***

## 10. 迁移与兼容

| 编号 | 内容                                                                                     |
| -- | -------------------------------------------------------------------------------------- |
| M1 | 无 DDL 变更（`doc_effect` 为纯元数据段，不落库）                                                      |
| M2 | 新增模块：`doc_effect_validator.py` / `reversal_primitives.py` / `reversal_orchestrator.py` |
| M3 | schema 加段：先在目标对象上加 `doc_effect`，其余不加（未声明 = 不接管）                                        |
| M4 | 开关：`REVERSAL_ORCHESTRATOR_ENABLED`（全局）+ 每 schema 的 `declared: true`（隐式）                |
| M5 | 旧实现保留：`*_service.reverse()` 保留一版，内部改为调用 Orchestrator（薄包装）                              |
| M6 | 错误码映射层保留一版                                                                             |
| M7 | 回滚策略：删除 `doc_effect` 段即回到旧路径（无需改代码）                                                    |

***

## 11. 采购退货正向对象（RTV，补齐「采购到出库」）

> 本节回答 §16 Q1：**需要**。但它不是逆向能力，而是逆向平台覆盖完整业务前提所缺的**正向对象**。

### 11.1 外部基准：SAP 与 Oracle 的实现细节（已查证）

| 维度               | SAP（S/4HANA MM）                                                                             | Oracle EBS（R12）                                                      | Oracle Fusion（Cloud）                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 单据形态             | **退货采购订单**（ME21N，勾选 Return Item 标识，`RETPO`）——同一 PO 对象，非新文档类型                                | **无退货单**：Receiving → Returns 直接对收货单发起                                | **两种并存**：有原收货时仍是收货事务；**无原收货时才出现独立 Supplier Return 单据**（有编号、Submit、发运、Fulfilled）               |
| 过账事务             | 移动类型 **161**（退货 PO 的"收货"，实为出库）；另有 **122** = 对普通 PO 已收货物做退货交付（与 102 取消的区别在于 122 是真实退货，必须填原因） | `RETURN TO VENDOR` 负向事务，`PARENT_TRANSACTION_ID` 指向原 `RECEIVE` 事务     | 沿用 `RCV_TRANSACTIONS` 事务链（25C 有 Receiving Transactions REST API）；无收货退货按当前物料成本计价，从**非预留子库存**发出 |
| 入口               | **双入口**：ME21N（计划性退货）／ MIGO + 122（即时退回）                                                      | **单入口**：输入收货单号 + 退货量 + Return To                                     | Receiving 的 Return to Supplier；无收货走 `Manage Supplier Returns Without Receipt`                 |
| 数量归属             | **EKBE 独立流水**：`BEWTP='WE'`（收货）/ `'RE'`（退货），**不混入收货口径**                                      | **回退原收货量**（官方帮助："reducing the original receipt quantity"，并重开 PO 未收量） | 有原收货则沿原事务链回退；无收货退货不涉及 PO 数量                                                                   |
| 审批               | Release strategy 绑定 **document type**（OMGS），可在 characteristic 中加维度做差异化                      | **不走 PO 审批**；依赖 RTV 权限 + 库存事务审计                                      | 无收货退货由 Supplier Return 自身 Submit/状态控制（公开文档未给审批模型）                                             |
| 财务凭证             | 贷项凭证（Credit Memo）                                                                           | 负向库存事务；供应商站点选项可**自动生成 Debit Memo**                                   | RTS 可自动建 Debit Memo；**无收货退货需手工建 Debit Memo**                                                  |
| Return To 目标     | 仅供应商                                                                                        | **两值**：`RETURN TO SUPPLIER` / `RETURN TO RECEIVING`（退到收货区待检）         | 同 EBS 事务模型                                                                                    |
| 约束               | —                                                                                           | —                                                                    | 无收货退货：仅 stockable/transactable；不支持公司间与寄售；可用 Supplier Returns REST 增删改查/提交                     |
| NetSuite（参照）     | —                                                                                           | Vendor Return Authorization，从原 Item Receipt 生成                       | —                                                                                             |
| Dynamics 365（参照） | —                                                                                           | Return order（`ReturnOrderHeader/Line`）+ 行级 disposition               | —                                                                                             |

**三者的真实差异不是「有没有退货单」，而是「退货挂在哪一层」**：

* SAP：挂在**单据层**——新单据（退货 PO / 退货交货）+ 新流水（EKBE `RE`），原单不动；

* Oracle EBS：挂在**收货事务层**——新事务（RTV）挂原 `RECEIVE`，同时回退原收货量、重开 PO 未收量；

* Oracle Fusion：**两层并存**——有原收货时仍走事务层；没有原收货可挂时，才补一个 Supplier Return 单据。

最后一条最能说明问题：**单据只在没有事实可挂时才出现**。Fusion 的 Supplier Return 不是
「Oracle 也改成 SAP 模式」，而是「无原事务可补偿时，必须先造一个可承载意图与状态的载体」。

**结论**：本系统已有完整 `PO → schedule → receipt` 链，且退货需要计划与审批，
因此选 **(a) SAP 路线：退货采购单（计划性）+ 收货后即时退回（快捷入口）**，
不采用 Oracle 的「回退原量」——退货单独立、原 PO 不变（见 §11.8 与 §2.2 非目标）。
Oracle 可借鉴的只有两点，且均已在规格内：原单锚（D16）与父事务链追溯。

来源：

* SAP 退货 PO 与移动类型 161：<https://www.cnblogs.com/sap-ronny/articles/8717683.html>

* SAP 122 / 161 语义：<https://allabouts4hana.com/vendor-return/>

* 122 与 102 的区别（真实退货 vs 取消）：<https://developer.aliyun.com/article/287961>

* Return Item 标识翻转方向：<https://www.learntosap.com/mmtutorialcreditmemoandreturnpo.html>

* PO Release Strategy 按 document type（OMGS）：<https://www.erpgreat.com/materials/purchasing-tips.htm>

* Oracle 退货回退原收货量：<https://hrispub.asmnet.com/OA_HTML/help/state/content/navId.2/navSetId.iHelp/vtTopicFile.iHelp%7CHelpServlet%7CUS%7CPO%7C@return/>

* Oracle RTV 入口与 Return To：<https://govoracleapps.wordpress.com/author/govindbalramn/page/5/>

* Oracle EBS 采购退货（批次/序列号）：<http://m.blog.itpub.net/4682/viewspace-1063913/>

* Oracle ROI 退货事务（PARENT\_TRANSACTION\_ID）：<http://m.blog.itpub.net/22816976/viewspace-1192524/>

* Oracle Fusion 无收货供应商退货（Supplier Return 单据 / REST / Debit Memo）：<https://www.vm-oracle.com/ebs/supplierreturnwithoutreceipt/>

* Oracle Fusion Receiving 25C 与 Receiving Transactions REST API：<https://www.syntraflow.cloud/oracle-release-intelligence/oracle-quarterly-updates/25c/receiving/>

* Oracle 自动 Debit Memo（Create Debit Memo From RTS Transaction）：<https://hrispub.asmnet.com/OA_HTML/help/state/content/navId.2/navSetId.iHelp/vtAnchor.t_inv_creditmat/vtTopicFile.iHelp%7CHelpServlet%7CUS%7CAP%7C@t_inv_creditmat/>

### 11.2 方案对比与裁决

| 方案                                                         | 形态                                                     | 成本                   | 与单一事实模型一致性  | 裁决                     |
| ---------------------------------------------------------- | ------------------------------------------------------ | -------------------- | ----------- | ---------------------- |
| A. 独立 `purchase_return` BO                                 | 新头/行/编号/状态机/守卫/菜单                                      | 最高（≈再造一个收货单）         | 低：同一语义两套对象  | ❌                      |
| **B. 复用** **`purchase_order`** **+** **`receipt`，用类别表达方向** | 退货采购单（`category=return`）+ 退货出库单（`category=return`，out） | 中（类别三值化 + 移动类型 + 规则） | 高：与销售退货完全对称 | ✅ **推荐**               |
| C. 仅复用 `receipt` 做 RTV                                     | 从原收货单直接建退货收货                                           | 低                    | 中：无计划/审批环节  | ✅ 作为 B 的**快捷入口**，不单独建模 |

**推荐 = B + C 快捷入口**：

* 计划性退货：建退货采购单 → 退货出库单 → `RETURN_TO_VENDOR` 出库事实。

* 即时退回：从原收货单「一键生成」退货采购单（自动带 `origin_receipt_id`），
  后续仍走 B 的链路，不新增模型（D17）。

### 11.3 关键发现：`receipt.document_category='return'` 已被「红字」占用

| 现状                      | 语义                                                   | 证据                                                        |
| ----------------------- | ---------------------------------------------------- | --------------------------------------------------------- |
| 收货单 `category='return'` | **红字收货（纠错凭证）**，`reversal_of_receipt_id` 必填，**不独立过账** | `receipt.yaml` R-RC-0；`receipt_service` L18 / L440 / L709 |
| 交货单 `category='return'` | **业务退货（正向新事实）**，独立过账 `RETURN_IN`                     | v222 迁移；`shipment.yaml`                                   |

**同一枚举值在两侧含义相反**——这是基础模型缺陷（G7）。若不修，采购退货只能叫
`vendor_return`，与销售侧永久不对称。

**决策 D13**：`document_category` 统一三值语义，所有单据共用：

| 值          | 含义                | 过账                      | 是否必须有原单                 |
| ---------- | ----------------- | ----------------------- | ----------------------- |
| `standard` | 正向业务              | 独立过账                    | 否                       |
| `return`   | **业务退货**（方向由对象决定） | 独立过账                    | 建议有（`origin_*`）         |
| `red`      | **红字纠错**          | **不独立过账**（REVERSAL 挂原单） | **必须**（`reversal_of_*`） |

迁移（一次性、幂等）：把现有收货类型 `code='RETURN'` 的 `document_category` 改为 `red`，
名称改「红字收货单」；存量红字单仍指向该 type id，行为不变。新增
`code='VENDOR_RETURN'`、`category='return'` 的收货类型承载采购退货出库。

### 11.4 对象与字段

| 对象                            | 变更                                                                    | 说明                                  |
| ----------------------------- | --------------------------------------------------------------------- | ----------------------------------- |
| `type_definitions`            | 新增 `RETURN_PO`（scope=`purchase_order`, `return`）                      | 退货采购单头类型                            |
| `type_definitions`            | 新增 `VENDOR_RETURN`（scope=`receipt`, `return`）                         | 采购退货出库单                             |
| `type_definitions`            | 现有 `RETURN`（scope=`receipt`）→ `red`                                   | 红字收货单（语义固化）                         |
| `purchase_order`              | 新增可选字段 `origin_purchase_order_id`、`origin_receipt_id`、`return_reason` | 业务锚，追溯「退的是哪张单」                      |
| `purchase_order_schedules`    | 新增 `returned_qty`（投影，默认 0）                                            | Q6：退货量独立口径，禁止混入 `received_qty`      |
| `receipt`                     | 新增 `return_to` 枚举（默认 `supplier`，预留 `receiving`）                       | 对齐 Oracle 两值；本期只实现 `supplier`       |
| `inventory_transaction_types` | 新增 `RETURN_TO_VENDOR`（`category='issue'`, `direction='out'`）          | 出库移动类型                              |
| `doc_flow_rule`               | 新增 `receipt_line_to_return_out_txn`                                   | 退货出库边，`pool='inventory_return_out'` |
| `v_demand_trace_graph`        | `signed_qty` 增加该规则分支：`-quantity`（红字再取反）                               | 净贡献为负                               |

### 11.5 服务改造点（`receipt_service`）

| #  | 改造                                                                             | 现状                                                                         |
| -- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| 1  | 方向解析：`standard → in`；`return → out`；`red → 不独立过账`                              | 目前 `is_return` 直接拒绝入库（L440），仅支持红字                                          |
| 2  | 出库守卫：可用量 + 序列号/HU 在库校验（从 `shipment_service` 抽出共享 `OutboundGuard`）              | 出库校验目前内嵌在 shipment                                                         |
| 3  | 出库不做入库序列号登记，改记序列号出库事件                                                          | 现有仅入库登记                                                                    |
| 4  | 退货出库 `qty_rejected` 必须为 0                                                      | 现无约束                                                                       |
| 5  | 计划行同事务重算：退货量写 `returned_qty`（按退货行重算），`received_qty` 对 `category='return'` 恒为 0 | 现有 `_apply_schedule_receipt` / `_apply_schedule_reversal` 为增量算术（同 R-SF-05） |
| 6  | 单据流边按规则分流：`receipt_line → RETURN_TO_VENDOR`                                    | 现固定 `receipt_line_to_inventory_txn`                                        |
| 7  | 类别一致性守卫：`standard` PO 不得开 `return` 收货单（镜像 `DN_CATEGORY_MISMATCH`）              | 无                                                                          |
| 8  | 审批复用 PO 审批流，条件表达式增加 `document_category` 维度（默认沿用，可配置退货加签）                       | 对齐 SAP release strategy 按 document type 差异化                                |
| 9  | 入口：收货详情「退货」按钮（带 `origin_receipt_id` 与可退量上限）；采购订单新建可选「退货采购单」                    | 对齐 Oracle 单入口 + SAP 双入口                                                    |
| 10 | `returned_qty` 上限守卫：`0 ≤ returned_qty ≤ received_qty`（按原收货回指时）                 | 对齐 Oracle「可退量 = 原收 − 已退」                                                   |

### 11.6 取消与红冲

| 语义     | 行为                                                                                                                                  |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| 取消     | 收货单 `draft → cancelled`（现有状态机），未过账、无写面                                                                                              |
| 红冲退货出库 | 走 `ReversalOrchestrator`：`inventory_reverse_by_event` 自动反向（`out → in`，`reverse_by_source` 已实现方向翻转） + 补偿边 + 序列号回退 + 计划行重算，**无需新增原语** |
| 红冲红字单  | 仍拒绝（现有守卫）：红字是补偿凭证，不可再冲                                                                                                              |

### 11.7 迁移与验收

**迁移** `v224__purchase_return_object.py`（幂等）：

1. `type_definitions`：新增 `RETURN_PO` / `VENDOR_RETURN`；`RETURN`（receipt）改 `red`。
2. `inventory_transaction_types`：种子 `RETURN_TO_VENDOR`。
3. `doc_flow_rule`：种子 `receipt_line_to_return_out_txn`。
4. 追溯视图重建（新增 `signed_qty` 分支）。
5. `verify`：断言四个类型/移动类型/规则存在；断言无 `category='return'` 的红字收货类型残留。

**验收**

| 编号       | 内容                                                   |
| -------- | ---------------------------------------------------- |
| AC-RP-11 | 退货采购单 + 退货出库单 → `RETURN_TO_VENDOR` 出库，余额减少、边存在       |
| AC-RP-12 | 红字收货单迁移后仍不独立过账，红冲行为零回归                               |
| AC-RP-13 | 退货出库在库存不足 / 序列号不在库时被拒（不产生任何写面）                       |
| AC-RP-14 | 追溯 `signed_qty` 对退货出库为负；红冲后恢复为正                      |
| AC-RP-15 | `returned_qty` 与 `received_qty` 互不污染：退货后前者等于退货量、后者不变 |
| AC-RP-16 | 审批沿用 PO 流程；`document_category='return'` 可命中差异化加签规则   |
| AC-RP-17 | 可退量守卫：`returned_qty ≤ received_qty`，超退被拒             |
| AC-RP-18 | 原 PO 未被重开：退货完成后原 PO 未收量不变（SAP 路线，非 Oracle 路线）        |

### 11.8 三个关键决策（Q6-Q8）及依据

| 问题          | 决策                                                 | SAP / Oracle 依据                                                                    | 落地                                  |
| ----------- | -------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------- |
| **Q6** 数量口径 | **新增** **`returned_qty`**，`received_qty` 对退货类别恒为 0 | SAP 在 EKBE 用 `BEWTP='RE'` 独立记退货，从不混入收货；Oracle 复用回退原量，因其退货不是独立单据                    | §11.4 字段、§11.5-5 投影重算、§11.5-10 上限守卫 |
| **Q7** 审批   | **沿用 PO 审批流**，条件增加 `document_category` 维度          | SAP release strategy 绑 document type，可按 characteristic 差异化；Oracle RTV 不走审批，仅有权限+审计 | §11.5-8；不新建审批引擎                     |
| **Q8** 入口   | **收货详情为主入口**（带原单与可退量上限），PO 新建可选退货类型                | Oracle 唯一入口是「输入收货单号」；SAP 122 同样从已收货批次发起，ME21N 只用于计划性退货                             | §11.5-9                             |

**两条附带约束（写入 §2.2 非目标）**：

1. **不实现 Oracle 式「退货后重开原 PO 未收量」**。退货单独立，原 PO 不变；需要补货则新建普通 PO。
2. **`return_to`** **本期仅实现** **`supplier`**；`receiving`（退到收货区待检）只留枚举占位，不实现流程。

***

## 12. 实施计划

### 阶段 D1：平台骨架（不改任何业务行为）

1. `reversal_primitives.py`：8 个原语封装为注册表（全部转调既有实现，不重写）。
2. `reversal_orchestrator.py`：7 步执行 + 错误码。
3. `doc_effect_validator.py`：V1-V6 校验。
4. 测试：`test_reversal_orchestrator.py` T1-T10（用 fake schema + 记录型原语）。
5. **不接管任何单据**（无 `doc_effect` 段）。

### 阶段 D2：库存调整试点（风险最低）—— ✅ 已实施 2026-11-06

1. `inventory_adjustment.yaml` 加 `doc_effect`：`inventory`（strict，含
   `allow_blocked_batch`）+ `serial`（skip）两面，`order: declared`（序列号按原分录回退）。
2. `adjustment.reverse()` 改为调 Orchestrator；服务层守卫与错误码映射保持原契约
   （`INV_ALREADY_REVERSED` / `INV_ADJ_STATE_INVALID` / `INV_ADJ_NO_TRANSACTIONS`）。
3. 红字镜像单由声明的创建器 `inventory_adjustment_red_letter` 生成（§7.4），
   用户可见行为与旧实现一致（`reversal_of_adjustment_id`、红字单号、余额回滚、
   REVERSAL 分录 `source_doc_id` 指向红字单）。
4. 回归：`test_inventory_adjustment_service`（14 例，含编排路径断言）+
   `test_reversal_platform`（15 例）+ `test_yaml_loader`（46 例）全绿。

### 阶段 D3：收货接管 —— ✅ 已实施 2026-11-06

1. `receipt.yaml` 加 `doc_effect`：`inventory`（skip）+ `doc_flow` + `hu` +
   `serial_completion`（`enabled_when: source_doc_type == 'work_order'`）四个写面，
   `order: declared`（保持旧实现的库存 → 边 → HU → 完工序列号顺序）；
   投影 `schedule`（`reverse_schedule_received`）+ `fulfillment`
   （`recompute_purchase_fulfillment`）。
2. `receipt.reverse()` 改薄包装：状态 / 红字单 / 重复冲销守卫保留在服务层，
   `R-RC-8` 取号在开事务前完成（`allocate_reversal_no`），随后调 Orchestrator。
3. 红字单创建器 `receipt_red_letter`（§7.4）承载 PO / TO / WO 三分支的全部单据事实：
   红字头 + 行、负分配、TO 行回写、红字过账、原单行置 reversed。计划行回退与
   PO 履约改为投影，在 faces 之后同一事务内执行。
4. 错误码映射：`REVERSAL_STATE_INVALID → RC_STATE_INVALID`；创建器 / 原语透传的
   `RC_*` / `INV_*` / `HU_*` / `SERIAL_*` 规则码经 `REVERSAL_FAILED.rule` 还原。
5. **互斥守卫保留**：`document_category='return'` 的红字收货单不可再冲销
   （`RC_REVERSAL_INVALID`），且先于编排器入口拦截。
6. 行为对齐：REVERSAL 分录 `transaction_date` 取红字单日期；`source_doc_no` 等
   字段与旧实现一致；净收为 0 仍报 `RC_REVERSAL_INVALID`（field\_name=`lines`）。
7. 回归：`test_receipt_reversal`（9 例，含编排路径断言）+
   `test_receipt_service` + `test_receipt_schema` + `test_receipt_allocation` +
   `test_inventory_receipt_bridge` + `test_transfer_order_receipt_bridge` +
   `test_serial_completion_genealogy` + `test_reversal_platform` +
   `test_reversal_orchestrator` + `test_yaml_loader` 全绿。

### 阶段 D4：交货接管 —— ✅ 已实施 2026-11-06

1. `shipment.yaml` 加 `doc_effect`：库存面按方向拆为 `inventory_standard` /
   `inventory_return`（`enabled_when: direction == 'standard' | 'return'`）；
   `serial` / `hu` / `reservation` 仅在出库方向启用；单据边按方向各一面
   （`shipment_line_to_issue_txn` / `shipment_line_to_return_in_txn`，`derived_by:
   shipment_reverse`）；`lines` 面把交货行置 reversed。
2. `shipment.reverse()` 改薄包装：状态守卫与幂等 replay 保留，`direction` 由
   `document_category` 判定后经 `params` 透传（`document_category` 不在单据行上，
   故编排器 `direction` 解析支持调用方优先）。
3. 投影 `schedule`（`recompute_schedule_delivered`）+ `fulfillment`
   （`recompute_fulfillment`）；`write_audit_fields` 写 `reversed_at` /
   `reversal_reason` / `updated_at`。
4. 新增原语：`reservation_unfulfill_by_shipment`（按交货行汇总核销 SO 行预留）、
   `shipment_reverse_lines`；`edge_compensate_by_source` 支持 `derived_by` 与
   `params.line_ids` 兜底。
5. 删除服务内 `_reverse_impl` / `_reverse_inventory` / `_reverse_serial_tracking` /
   `_reverse_hus` / `_unfulfill_reservations` / `_mark_reversed` /
   `_recompute_order_fulfillment`（写面编排全部由声明承担）。
6. 回归：`test_shipment_reverse`（6 例，含编排路径断言）+
   `test_shipment_service` / `test_shipment_single_fact` /
   `test_shipment_return_doc_flow` / `test_shipment_issue_doc_flow` /
   `test_shipment_schema_rules` / `test_shipment_guard_interceptor` +
   `test_receipt_reversal` / `test_inventory_adjustment_service` +
   `test_reversal_platform` / `test_reversal_orchestrator` / `test_yaml_loader` 全绿。

### 阶段 D5：调拨发货侧红冲（新能力）—— ✅ 已实施 2026-11-06

**语义（决策）**：原地红冲「发货事实」，不新建反向调拨单（对应 G4 / AC-RP-09）。

* 复用单一事实模型：库存追加 `REVERSAL`、DOC\_FLOW 追加红字补偿边；原边 / 原分录保留。

* 既有 `create_reversal()`（反向草稿调拨单）保留为**业务反向**路径（货物已收 /
  需反向运输）；与本次「数据错误红冲」互斥：已收货只能走反向调拨。

* **Q3 决议**：复用既有 `reversal_of_transfer_id`（`create_reversal` 已落库），
  不新增 `reversed_transfer_id` 列；本次原地红冲不产生反向单。

* 目标状态：`transfer_order.status` 新增 `reversed`（终态，`category=inactive`）；
  `released` → `reversed`；幂等状态 `reversed`。

* 守卫：`status=released`；总发货量 > 0；总收货量 = 0
  （否则 `TO_RECEIVED_CANNOT_REVERSE`，提示改走反向调拨）；`closed/cancelled` 拒绝。

* 落库：头 `status=reversed`、`updated_at=now`；行 `qty_shipped=0`
  （收货守卫保证 `qty_received=0`）；履约派生回到 `open`。
  不新增 `reversed_at` / `reversal_reason` 列（审计由 audit\_log + 库存/边事实承担）。

**声明（`meta/schemas/transfer_order.yaml`）**

```yaml
doc_effect:
  faces:
    - id: inventory_ship            # 1. 库存：按来源单据反冲全部 ship:{seq} 事件
      primitive: inventory_reverse_by_source
      args: {source_doc_type: transfer_order, source_doc_id: "{id}", remark: "调拨单 {id} 发货冲销"}
      on_missing: skip
    - id: serial                    # 2. 序列号：按被冲销的原分录回退
      primitive: serial_reverse_by_txn
      args: {txn_ids: "{inventory_ship.source_txn_ids}"}
      on_missing: skip
    - id: hu                        # 3. 容器：按单据整体倒序回退
      primitive: hu_reverse_document
      args: {doc_type: transfer_order, doc_id: "{id}"}
      on_missing: skip
    - id: doc_flow                  # 4. 边：按行追加红字补偿边（指向原边）
      primitive: edge_compensate_by_source
      args:
        source_bo: transfer_order_line
        rule_ids: [transfer_order_line_to_issue_txn]
        ref: "{id}"
        derived_by: transfer_order_reverse
      on_missing: skip
    - id: lines                     # 5. 行：发货事实归零
      primitive: transfer_reverse_lines
      args: {doc_id: "{id}", now: "{now}"}
      on_missing: skip
  projections:
    - id: fulfillment
      primitive: recompute_transfer_fulfillment
      args: {doc_id: "{id}"}
  reversal:
    from_states: [released]
    to_state: reversed
    idempotent_states: [reversed]
    order: declared
    write_audit_fields: {updated_at: "{now}"}
```

同时补 `status.enum_values.reversed` 与 `rules`（V2 校验要求存在
`to_state=reversed` 的 `state_transition`）：

```yaml
rules:
  - id: reverse_transfer_shipment
    name: 调拨发货红冲
    type: state_transition
    state_field: status
    from_states: [released]
    to_state: reversed
    triggers: [before_update]
```

**原语（`meta/core/reversal_primitives.py`，14 → 17）**

1. `inventory_reverse_by_source`：查询 `source_doc_type/source_doc_id` 下全部
   未红冲事件键（排除已红冲），逐键镜像为 `{key}:reverse` 调
   `InventoryPostingService.reverse_by_source`；返回 `created/existing/source_txn_ids`。
2. `transfer_reverse_lines`：`qty_shipped=0`（跳过 `cancelled` 行），返回 rowcount。
3. `recompute_transfer_fulfillment`：转调 `TransferOrderService.recompute_fulfillment`。

**服务与入口**

* `transfer_order_service.py`：新增 `STATUS_REVERSED` 并纳入 `TERMINAL_STATUSES`；
  新增 `reverse_shipment(transfer_order_id, reason=None, user_info=None)`（幂等短路 +
  守卫 + 计算 `line_ids` + 调 Orchestrator + `_map_reversal_error`；错误码透传 `TO_*`）。

* `transfer_order_actions.py`：新增 `reverse_shipment_handler`。

* `bo_action_registrations.py`：注册 `transfer_order.reverse_shipment`
  （权限 `transfer_order:transfer_order_reverse_shipment`）。

* `meta/migrations/v226__transfer_order_reverse.py`：种子权限并授予 `admin/default`
  （仅权限，无列变更；D6 迁移号顺延为 v227）。

**测试（新增** **`meta/tests/test_transfer_ship_reversal.py`** **3 例）**

* `T1` 全链路：发货 10 → 红冲 → 余额恢复、`REVERSAL` 分录事件键
  `transfer_order:1:ship:1:reverse`、补偿边 `#rev:1`（`red/active` 且指向原边）、
  头 `reversed`、行 `qty_shipped=0`、履约 `open`、二次调用 `idempotent=True`。

* `T2` 守卫：已收货 → `TO_RECEIVED_CANNOT_REVERSE`；未发货 → `TO_SHIP_NOT_FOUND`；
  `draft/cancelled` → `TO_STATE_INVALID` / `TO_TERMINAL_IMMUTABLE`。

* `T3` 编排路径：spy `reversal_orchestrator.execute`，断言
  `schema_id='transfer_order'`、`doc_id`、`params['line_ids']`；已红冲返回 `replay`。

**验证命令**

```
python d:\filework\test.py --file meta/tests/test_transfer_ship_reversal.py,meta/tests/test_transfer_order_service.py,meta/tests/test_transfer_order_schema.py,meta/tests/test_transfer_order_guard.py,meta/tests/test_transfer_order_receipt_bridge.py,meta/tests/test_reversal_platform.py,meta/tests/test_reversal_orchestrator.py,meta/tests/test_yaml_loader.py
```

**回归记录（2026-11-06）**
- `test_transfer_ship_reversal`（3 例）全绿：全链路 / 守卫 / 编排路径。
- 调拨全套（`service` / `schema` / `tbd` / `from_allocation` / `guard` /
  `receipt_bridge` + 新增红冲）141 例全绿。
- `test_reversal_platform`（15）/ `test_reversal_orchestrator`（7）/
  `test_yaml_loader`（46）全绿。
- `test_transfer_order_schema.test_header_status_enum` 同步纳入 `reversed`。

### 阶段 D6：采购退货正向对象（§11）

1. `v227` 迁移（D5 占用 v226）：类型三值化 + `RETURN_TO_VENDOR` + 规则 + 追溯视图 + `returned_qty` / `return_to` 列。
2. `receipt_service`：方向解析 / 出库守卫（抽 `OutboundGuard`）/ `returned_qty` 重算与上限守卫 / 边规则分流。
3. `purchase_order` 加 `origin_*` / `return_reason` 字段；审批条件增加 `document_category` 维度。
4. 入口：「收货详情 → 退货」按钮（带原单与可退量）；PO 新建可选退货类型。
5. 新增 `test_purchase_return.py` 9 例（见 §14 补充）。
6. 回归 `test_receipt_service` / `test_receipt_reversal` / `test_doc_flow_reconcile` /
   `test_demand_trace_graph` / `test_purchase_order*`。

### 阶段 D7：收口

1. 删除旧编排代码与错误码映射（保留一版后清理）。
2. `test_doc_effect_declarations` 纳入常规回归。
3. 更新单一事实模型规格的实施记录。

***

## 13. 验收标准

| 编号               | 验收内容                                        | 对应测试                                 |
| ---------------- | ------------------------------------------- | ------------------------------------ |
| **AC-RP-01**     | 新增单据类型仅写 `doc_effect` 即可获得逆向能力（零 Python 编排） | T1 + D5 实证                           |
| **AC-RP-02**     | 五件事只有一份实现（守卫/幂等/顺序/事务/投影）                   | 代码审查 + 覆盖矩阵                          |
| **AC-RP-03**     | 任一写面抛错 → 库存/边/序列号/投影全回滚                     | T5                                   |
| **AC-RP-04**     | 幂等状态重复调用 → 零 IO、`replay=True`               | T3                                   |
| **AC-RP-05**     | 未声明单据调用逆向 → `REVERSAL_NOT_DECLARED`（不静默）    | T9                                   |
| **AC-RP-06**     | 声明与状态机不一致 → 启动/测试期失败                        | T10 + `test_doc_effect_declarations` |
| **AC-RP-07**     | 倒序执行可被观测且可切换为 `declared`                    | T2                                   |
| **AC-RP-08**     | 投影与事实一致（任意拆行/改量/退货/冲销序列后）                   | T8                                   |
| **AC-RP-09**     | 调拨发货侧红冲可用，且补偿边指向原边                          | D5 新测试 3 例                           |
| **AC-RP-10**     | 全量回归：阶段 A 的 6 例 + 7 个既有套件 + 新增套件全绿          | `test.py --file`                     |
| **AC-RP-11\~14** | 采购退货正向对象（退货出库 / 红字零回归 / 出库守卫 / 追溯符号）        | 见 §11.7                              |

***

## 14. 测试用例清单（`meta/tests/test_reversal_orchestrator.py`）

| #   | 用例                                               | 断言                                   |
| --- | ------------------------------------------------ | ------------------------------------ |
| T1  | 声明解析：最小合法声明可执行                                   | `execute` 返回 `to_state`，faces 全部被调用  |
| T2  | 倒序：`order=inverted` 时调用序 = 声明序的反向；`declared` 时一致 | 记录型原语的调用日志                           |
| T3  | 幂等重放：状态已是 `reversed`                             | `replay=True`，原语调用次数 = 0             |
| T4  | 状态守卫：当前状态 ∉ `from_states`                        | `REVERSAL_STATE_INVALID`             |
| T5  | 原语抛错：第 2 个面失败                                    | 事务回滚（第 1 面写入不存在），抛 `REVERSAL_FAILED` |
| T6  | 业务锚：`ref_field` 有声明值为空                           | `REVERSAL_REF_MISSING`               |
| T7  | `on_missing`：strict 无事实抛错 / skip 正常通过            | 两分支断言                                |
| T8  | 投影：faces 后重算，值 = 事实聚合                            | 投影值断言                                |
| T9  | 未声明：无 `doc_effect`                               | `REVERSAL_NOT_DECLARED`              |
| T10 | 声明校验：`to_state` 与 `from_states` 不一致              | `DECL_STATE_MISMATCH`                |

补充（阶段化）：

* D2：`test_adjustment_reversal_via_orchestrator`

* D3：`test_receipt_reversal_via_orchestrator`

* D4：`test_shipment_reversal_via_orchestrator`（用例复用阶段 A 的 6 例）

* D5：`test_transfer_ship_reversal`（含补偿边指向校验）

* D6：`test_purchase_return.py` 9 例：

  1. 退货 PO + 退货出库 → `RETURN_TO_VENDOR`（out）且余额减少、边存在
  2. 红字收货（`red`）迁移后仍不独立过账 → 零回归
  3. 库存不足 / 序列号不在库 → 拒绝且无任何写面
  4. `returned_qty` 同事务重算（拆行/改量后一致），`received_qty` 不变
  5. 退货出库红冲 → REVERSAL 入库 + 补偿边 + 序列号回退
  6. 追溯 `signed_qty` = 负；红冲后恢复为正
  7. 类别不一致（`standard` PO + `return` 收货）→ 拒绝
  8. 超退（`returned_qty > received_qty`）→ 拒绝
  9. 审批：`document_category='return'` 命中差异化规则；原 PO 未收量不变

***

## 15. 风险

| 编号      | 风险                                           | 应对                                                                                          |
| ------- | -------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **R1**  | 元数据表达式（占位符/`enabled_when`）膨胀成 DSL            | 只支持占位符替换 + 三个运算符（`==`/`!=`/`and`），超出一律写原语                                                   |
| **R2**  | 接管 receipt / shipment 时行为漂移                  | 每阶段保留旧实现，双路径跑同一测试对照一周                                                                       |
| **R3**  | `before_update` 回落后旧委托链与 Orchestrator 双写     | 白名单互斥：声明 `doc_effect` 即不再走旧委托                                                               |
| **R4**  | 红字收货单（迁移后 `document_category='red'`）被误判为"逆向" | Orchestrator 只处理 `to_state == reversed`；红字单是补偿凭证，不独立过账，两者不交叉                                |
| **R5**  | 调拨发货红冲改变既有取消语义                               | 只在 `shipped` 之后允许；`shipped` 前仍走 cancel（`TO_SHIPPED_CANNOT_CANCEL` 保留）                       |
| **R6**  | 原语注册表与既有服务实现漂移                               | 原语**转调**既有实现，不复制逻辑；单测锁定调用参数                                                                 |
| **R7**  | 类别三值化的存量迁移误伤红字单                              | 迁移按 type id 回填（红字单以 `reversal_of_receipt_id` 可识别）；提供 downgrade；迁移后跑 `test_receipt_reversal` |
| **R8**  | 抽出 `OutboundGuard` 影响销售发运                    | 抽取时保持 shipment 行为逐行等价，阶段 A 的 6 例 + `test_shipment_service` 锁定                               |
| **R9**  | 退货采购单被当作普通采购单使用                              | 守卫：`category=return` 的 PO 只能被 `return` 收货引用，反向亦然（D14 + §11.5-7）                             |
| **R10** | 退货出库后 `received_qty` 语义混淆（收货量 vs 退货量）        | 短期复用字段并在报表标注；若口径冲突则 D6 内改 `returned_qty`（Q6）                                                |

***

## 16. 待确认问题

| 编号     | 问题                                                                                                                                                                     | 影响                           |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| **Q1** | ~~采购退货单是否立项？~~ **已决策：纳入本规格 §11**（复用 PO + receipt，方案 B）                                                                                                                 | —                            |
| **Q2** | 工单完工收货的红冲是否需独立入口，还是继续借道 receipt？                                                                                                                                       | 决定 D7 是否扩到工单                 |
| **Q3** | ~~反向调拨的链接字段用~~ ~~`reversed_transfer_id`~~ ~~还是复用~~ ~~`demand_allocation`~~ ~~链？~~ **已决策：复用既有** **`reversal_of_transfer_id`**（`create_reversal` 已落库，不新增列；D5 原地红冲不产生反向单） | —                            |
| **Q4** | `enabled_when` 条件是否足够表达「退货交货不走出库序列号面」？                                                                                                                                 | 若不足，需引入 `face.applies_to` 枚举 |
| **Q5** | 旧错误码映射保留几个版本周期？                                                                                                                                                        | 决定 D7 清理时点                   |
| **Q6** | ~~退货采购单复用~~ ~~`received_qty`~~ ~~还是新增~~ ~~`returned_qty`？~~ **已决策：新增** **`returned_qty`**（§11.8，对齐 SAP EKBE 分流水）                                                       | —                            |
| **Q7** | ~~退货采购单是否沿用 PO 审批流？~~ **已决策：沿用 + 增加** **`document_category`** **维度**（§11.8）                                                                                            | —                            |
| **Q8** | ~~「从收货单一键生成退货单」入口放何处？~~ **已决策：收货详情为主入口，PO 新建为辅**（§11.8）                                                                                                                | —                            |

***

## 17. 附录 A：与单一事实模型的对应

| 单一事实模型决策         | 本规格承接                                   |
| ---------------- | --------------------------------------- |
| D1 边表 = 不可变事实流水  | 逆向只追加 `reversal` 边，不改原边                 |
| D3 冲销 = 追加补偿事实   | `edge_compensate_*` 原语即该决策的执行体          |
| D4 一个数量一个权威      | `recompute_schedule_delivered` 投影契约（P1） |
| D5 边身份结构化        | `ref` 写入 `derive_key` + `rule_id` 后缀    |
| R-SF-01 事务边界     | Orchestrator 自持事务（D5 / 8.6）             |
| R-SF-02 无过账不推进状态 | `inventory` 面 `on_missing: strict`      |
| R-SF-03/04 补偿边   | `compensate_edge` 转调，保留原边与红字子边          |
| R-SF-05 计划行重算    | `projections` 统一执行（P4）                  |

## 18. 附录 B：覆盖矩阵转为声明后的预期

| 单据                    | D2-D6 完成后         | 声明内容                                                                        |
| --------------------- | ----------------- | --------------------------------------------------------------------------- |
| adjustment            | `doc_effect` 声明接管 | inventory                                                                   |
| receipt（正向 / 红字）      | 声明接管              | inventory · serial · hu · doc\_flow · allocation · schedule 投影              |
| receipt（采购退货出库）       | 新增（§11）           | inventory(out) · serial · hu · doc\_flow · schedule 投影                      |
| shipment              | 声明接管              | inventory · serial · hu · reservation · doc\_flow · schedule/fulfillment 投影 |
| transfer（发货侧）         | 新增                | inventory · serial · doc\_flow                                              |
| purchase\_order（退货类型） | 新增（§11）           | 无库存事实；提供 `origin_*` 锚与单据链                                                   |
| work\_order           | 维持借道（Q2）          | —                                                                           |
| sales\_order          | 不适用（无库存事实）        | —                                                                           |

