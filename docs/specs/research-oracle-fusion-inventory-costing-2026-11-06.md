# 研究：Oracle Fusion Cloud 库存与成本模型（Inventory / Cost Management）

> 日期：2026-11-06　类型：**只读研究**（不含实施）
> 目的：补齐头部产品第三方样本，判断 P8 库龄/P7 效期/INV-5 估值的模型选型
> 关联：`docs/specs/research-sap-s4-material-ledger-2026-11-06.md`、`docs/specs/p8-inventory-aging-model/spec.md`

---

## 0. 一句话结论

**Oracle Fusion 是三家头部产品里唯一把"库存数量"直接按"收货切片（receipt slice）"存储的：**

- `INV_ONHAND_QUANTITIES_DETAIL` = 每次收货一片，字段 `DATE_RECEIVED`，出库按 FIFO 消耗；
- `INV_ONHAND_QUANTITIES_SUMMARY` = 由明细汇出的即时余额；
- 批次主档 `INV_LOT_NUMBERS` **没有收货日期**，只有 `ORIGINATION_DATE`（批次创建日）/ `EXPIRATION_DATE` / `RETEST_DATE` / `MATURITY_DATE`。

**对我们最重要的三条启示**：

1. **"入库日期"一定属于收货切片，不属于批次主档**——Oracle 用表结构直接证明了 P8 的 D3。
2. **精确库龄 = 切片日期聚合**，不需要二次推算；这正是 P8 P1 `inventory_layers` 的等价物。
3. **明细 + 汇总两张表不是"双账"，而是"源 + 派生"**——汇总由明细汇出，同事务维护。P1 若上层表，应照此办理，而不是维护两本独立账。

---

## 1. 库存数量模型（最关键）

| 对象 | 角色 | 关键字段 / 语义 |
|---|---|---|
| `INV_ONHAND_QUANTITIES_DETAIL` | **收货切片明细**，库存数量的源 | 一行 = 一次收货；`PRIMARY_TRANSACTION_QUANTITY` 为该片数量；**`DATE_RECEIVED` 是切片收货日，用于排序 FIFO 消耗**；`SUM` 后才是余额，单行不是余额 |
| `INV_ONHAND_QUANTITIES_SUMMARY` | 即时余额汇总（派生） | 由 detail 汇总，供快速查询 |
| `INV_LOT_NUMBERS` | 批次主档 | `ORIGINATION_DATE`（批次创建日）、`EXPIRATION_DATE`、`RETEST_DATE`、`MATURITY_DATE`、`HOLD_DATE`、`EXPIRATION_ACTION_CODE/DATE`、`SUPPLIER_LOT_NUMBER`；**无 RECEIPT_DATE** |

**结构要点**：

- 同一物料在同一货位可以有多行，一行对应一次收货；
- 出库按 `DATE_RECEIVED` 升序消耗（FIFO），每片数量递减；
- 汇总表是"现成可用"的聚合，避免每次 `SUM` 明细。

这解释了一个常见误解：Oracle 的"库龄"不是算出来的，而是**读出来的**——直接按 `DATE_RECEIVED` 分桶即可。

---

## 2. 成本模型

| 维度 | Oracle Fusion Cost Management |
|---|---|
| 成本方法 | Standard、Average（Perpetual Average）、**Actual（FIFO）**；**不支持 LIFO**（EBS 时代的 LIFO 未延续） |
| 估值粒度 | **Valuation Structure + Valuation Unit**：可按 **物料 / 批次 / 序列号** 级别维成本 |
| 层级 | Actual(FIFO) 下，收货与完工入库形成 **receipt layer**，出库按最早剩余层计价；期末保留仍有数量的层，**以前期间/年度的层在期末合并为单层** |
| 组织 | Cost Organization / Cost Book / Cost Profile 三层配置 |
| 期末 | 事务转成本 → 处理成本 → 创建会计分录 → 关闭期间 |

与 SAP 的差异：

| | Oracle Fusion | SAP S/4 ML |
|---|---|---|
| FIFO 形态 | **逐收货层**（receipt layer） | **期间层**（periodic layer，估值口径） |
| 数量明细 | 收货切片明细表 | `MARD`/`MCHB` 即时 + `MARDH`/`MCHBH` 月度快照 |
| 估值粒度 | Valuation Unit 可到批次/序列号 | 物料 × 估值视图 × 期间 |
| LIFO | 不支持 | 支持（资产负债表估值） |

---

## 3. 批次与效期

- 拣货规则的批次排序支持四种：**Expiration Date（最早到期）/ Receipt Date（最早收货）/ Lot Number（最小批号）/ None**。
  - 注意：`Receipt Date` 语义是"货物进入**当前库位**的日期"，来自收货切片，不是批次创建日。
- 效期控制由物料属性驱动：`LotExpirationControlValue`、`ShelfLifeDays`、`MaturityDays`、`HoldDays` 等；批次主档承载到期/复验/成熟/冻结日期与到期动作。
- 因此 Oracle 的 FEFO 是"**批次效期排序 + 切片 FIFO 消耗**"的组合：FEFO 决定拣哪个批次，FIFO 决定该批次内先耗哪次收货。

这与 P7 的 FEFO 设计完全同构：P7 的 `_apply_policy` 选批次，P8 P1 的层决定批次内消耗顺序。两者正交。

---

## 4. 库龄

| 口径 | Oracle |
|---|---|
| 精确库龄 | 按 `DATE_RECEIVED` 切片分桶（0-30 / 31-60 / …），`SUM(quantity)` |
| 历史时点库龄 | 依赖切片与事务回放；EBS 提供标准 Inventory Aging Report（需开启 profile `INV: FIFO for Original Receipt Date`） |
|  Fusion 报表 | OTBI "Inventory Balances Real Time" 主题域 + 计算列做分桶（常见实施方式） |

**注意**：EBS 的标准库龄报表都要求专门开启"原始收货日 FIFO"profile，说明"保留原始收货日"本身是一个显式能力，不是默认就有的。Fusion 把它下沉成了明细表结构。

---

## 5. 与本项目的映射

| Oracle Fusion | 本项目现状 | 映射关系 |
|---|---|---|
| `INV_ONHAND_QUANTITIES_DETAIL`（收货切片） | 无 | **P8 P1 `inventory_layers`** |
| `INV_ONHAND_QUANTITIES_SUMMARY` | `inventory_balances` | P0 的余额行就是 summary 角色 |
| `INV_LOT_NUMBERS` | `batches` | 已有 `produced_at`/`expiry_date`，**同样没有收货日** |
| `INV_TRANSACTIONS` | `inventory_transactions` | 事务流，`transaction_date` 即过账日 |
| Cost Organization / Book / Profile | 无 | INV-5 范围 |
| Valuation Unit（物料/批次/序列号） | 无 | INV-5 范围；P8 P1 若加 `unit_cost` 可复用 |

**P8 的 P0/P1 正好对应 Oracle 的 summary/detail**：

- P0 余额行 = `SUMMARY`；
- P1 层表 = `DETAIL`；
- 且 Oracle 的做法是 **detail 为源、summary 为派生**，P1 落地时应让 `inventory_balances` 由层汇总校验，而不是两套独立写入。

---

## 6. 决策影响

### 6.1 对 P8 决策①（余额行 vs 层表）：**不变，但强化了升级路径**

- Oracle 证明了"层表是精确库龄的正解"，也证明了它的代价：多一张明细表 + 汇总派生 + FIFO 消耗引擎 + 成本层 + 估值单元配置。
- 本项目当前只需库龄报表，不核算 FIFO 成本；P0 继续用余额行近似 + 钻取。
- P1 一旦启动，**照 Oracle 的 detail/summary 关系实现**：层是源，余额是汇出结果；每次过账同事务写层并更新余额，另设对账任务校验 `SUM(remaining) = qty_on_hand`。

### 6.2 对 P8 决策②（过账日 vs 实际到货日）：**不变**

- Oracle 的 `DATE_RECEIVED` 是收货事务日期（进入当前库位的日期），不是供应商发货日、也不是批次创建日；
- Fusion 批次主档只有 `ORIGINATION_DATE`，说明"批次创建/生产"与"收货入库"是两个日期，不能互相替代；
- 本项目 `transaction_date = receipt_date`（过账日）与 Oracle 口径一致。

### 6.3 对 P7（效期）：**补充一条设计确认**

Oracle 的批次效期字段与我们 `batches.expiry_date` 对齐；但 Oracle 还区分了 **retest / maturity / hold** 三类日期。若未来做食品/医药，P7 需扩展：

| Oracle 字段 | 含义 | 本项目 |
|---|---|---|
| `EXPIRATION_DATE` | 到期日 | `expiry_date`（已有） |
| `RETEST_DATE` | 复验日 | 待加（P7 P1） |
| `MATURITY_DATE` | 成熟/可用日 | 待加（P7 P1） |
| `HOLD_DATE` | 冻结至 | 待加（P7 P1） |
| `EXPIRATION_ACTION_CODE` | 到期动作（冻结/报废等） | 待加（P7 P1） |

当前 P7 只做 `expiry_date`，与 Oracle 最小集一致；扩展项不进 P0。

### 6.4 对 INV-5（估值）：**Valuation Unit 值得借鉴**

Oracle 允许把成本维护在 **物料 / 批次 / 序列号** 粒度。本项目若将来做估值，建议：

- 默认 `valuation_unit = item`（移动平均/标准价）；
- 可选 `valuation_unit = lot`（Actual/FIFO，配合 P8 P1 层表的 `unit_cost`）；
- 不引入 Cost Organization/Book/Profile 三层，用组织 + 估值方法两个字段表达即可。

---

## 7. 风险与教训

1. **不要把 `INV_ONHAND_QUANTITIES_DETAIL` 的"一行"当余额**——Oracle 明确要求 `SUM`，单行只是切片。P1 层表同样必须 `SUM(remaining_qty)` 才是余额，UI 不得直接展示单行数量为库存。
2. **明细 + 汇总必须同事务维护**，否则对账成本高于收益；Oracle 的 summary 是"现成聚合"，不是独立账本。
3. **期末合并层**：Oracle 在期间关闭时把旧层合并为单层，控制层数膨胀。P1 若长期运行，需要同样的"层合并/归档"策略，否则层表会随事务无限增长。
4. **FEFO 与 FIFO 是两层逻辑**：FEFO 选批次（效期），FIFO 选层（收货日）。不要把两者写进同一个排序键，否则调拨/退货场景无法解释。

---

## 8. 来源

- [INV_ONHAND_QUANTITIES_DETAIL — Oracle Fusion 表参考（Summit Analytics）](https://summit-bi.com/resources/fusion-reference/tables/inv_onhand_quantities_detail)：收货切片、`DATE_RECEIVED`、FIFO 消耗、单行不是余额、存在 SUMMARY 聚合
- [INV_LOT_NUMBERS — Oracle Fusion 表参考（Summit Analytics）](https://summit-bi.com/resources/fusion-reference/tables/inv_lot_numbers)：批次主档字段：`ORIGINATION_DATE`、`EXPIRATION_DATE`、`RETEST_DATE`、`MATURITY_DATE`、`HOLD_DATE`、`SUPPLIER_LOT_NUMBER`；无收货日
- [Deriving Actual Cost, Actually! — Trinamix 白皮书](https://www.trinamix.com/wp-content/uploads/2025/09/DERIVING-ACTUAL-COST-ACTUALLY.pdf)：Fusion 支持 Standard / Average / Actual(FIFO)，不支持 LIFO；Valuation Structure 与 Valuation Unit 可到批次/序列号粒度
- [Cost Management in Oracle Apps — Nvision](https://nvisioninfotech.com/PDF/Cost%20Management%20in%20Oracle%20Apps.pdf)：Layer Cost 语义：收货/完工入库形成层，出库按最早剩余层计价，期末保留有余额的层
- [Oracle Fusion Inventory Aging / OTBI 实施说明](https://unogeeks.com/otbi-reports-in-oracle-fusion-scm/)：用 Inventory Balances Real Time 主题域 + 计算列做库龄分桶
- [Oracle EBS Inventory Aging Report](https://oraclereporting.com/INV%20Aging/)：标准库龄报表需开启 profile `INV: FIFO for Original Receipt Date`，按 FIFO 回溯原始收货日
- [Oracle 拣货规则（批次排序：Expiration / Receipt Date / Lot Number / None）](https://bpcblogsoracle.wordpress.com/category/pick/)
- [Oracle 物料属性：`LotExpirationControlValue` / `MaturityDays` / `HoldDays`](https://efob-test.fa.em2.oraclecloud.com/fscmService/ItemServiceV2?XSD=/oracle/apps/scm/productModel/items/itemServiceV2/Item.xsd)
