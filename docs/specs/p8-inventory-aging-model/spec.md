# P8 入库日期与库存库龄模型（Inventory Aging）实现规格

> 状态：**已细化 · 待评审**（未实施）
> 日期：2026-11-06（初稿 2026-11-05）
> 关联：`docs/specs/p7-shelf-life-expiry-model/spec.md`

---

## 0. 结论先行

1. **入库日期已经是事实数据**：收货过账时 `inventory_transactions.transaction_date = receipt.receipt_date`（`meta/services/receipt_service.py` L1126-1134），无需新增“入库单”字段。
2. **缺的是投影与层**：`inventory_balances` 只有 `updated_at`（L252），没有日期维度；因此现在只能回答“有多少”，回答不了“这批货什么时候进来的、库龄多少”。
3. **正确的对象模型是「库存层（receipt layer）」**：入库日期属于“某一次入库形成的库存层”，不属于物料、也不属于批次主档的单一字段。SAP / Oracle / D365 的库龄与 FIFO 都建立在事务层上。
4. **P0 用「余额行最早入库日」做近似**：在 `inventory_balances` 增加 `first_received_date`，成本最低且能覆盖按 批次/库位/状态/段 的库龄分布；当余额清零时重置。
5. **P1 再上「库存层表」**：需要精确 FIFO 成本、层级别追溯、跨多次收货同批次的精确库龄时，新增 `inventory_layers`。
6. **性能风险不在"加一列"，而在"在哪算"**：P0 写入 **0 条额外 SQL**、报表 **O(余额行)**、重建 **单遍窗口函数**。真正会炸的是「从事务流水现场重算」和「Python 读全量事务做 FIFO」，规格已逐条封堵，见 §10。

---

## 1. 现状盘点

| 对象 | 现有时间字段 | 说明 | 缺口 |
|---|---|---|---|
| `inventory_transactions` | `transaction_date`（L92-102，required） | 业务发生日期，注释已写明“用于 INV 编号分月与账龄查询” | 账龄查询并未实现 |
| `inventory_transactions` | `created_at`（L413） | 落库时间，非业务日期 | 不能用 `created_at` 算库龄（补录/回写会失真） |
| `inventory_transactions` | `direction`（L180）、`batch_id`（L200）、`source_doc_type`（L326）、`reversal_of_transaction_id`（L378） | 可完整还原收发与红冲 | 无层概念 |
| `inventory_balances` | 仅 `updated_at`（L252）；唯一键 L266 | 数量投影，按 org/location/item/batch/status/segment 聚合 | **无入库日期** |
| `inventory_balances` | `qty_on_hand`（L145）、`batch_id`（L105） | 批次库存即“带 batch_id 的余额行” | 同批次多次入库被合并，日期会丢失 |
| `batches` | `produced_at`（L408）、`created_at`（L482） | 生产日期、主档创建时间 | **无入库日期**（且产出日 ≠ 入库日） |
| `receipt` | `receipt_date`（L120）、`actual_arrival_date`（L135） | 收货业务日期 / 实际到货日 | 未投影到库存 |
| 库存服务 | `_apply_balance`（`inventory_posting_service.py` L681-704） | upsert 余额 | 不维护任何日期 |
| 库存服务 | `rebuild_balances`（L503-525） | 按分录重建余额 | 重建后日期信息全部丢失 |

**关键区分**：
- **货龄（shelf age）** = 今天 − `produced_at`，用于效期/保质期（P7）。
- **库龄（stock age）** = 今天 − `first_received_date`，用于资金占用/呆滞分析。
- 两者不能混用；`produced_at` 不能替代入库日期。

---

## 2. 主流系统对标

| 能力 | SAP S/4HANA | Oracle（EBS / Fusion） | Dynamics 365 | 本项目 |
|---|---|---|---|---|
| 入库日期载体 | 物料凭证 `MATDOC/MSEG` 的收货日期；批次库存 `MCHB` 按工厂/库位/批次记数量 | `MTL_MATERIAL_TRANSACTIONS.TRANSACTION_DATE`；成本层 `CST_LAYER`（receipt layer） | `InventTrans.DatePhysical` + `InventBatchId`；库存层按收/发匹配 | `inventory_transactions.transaction_date`（已有） |
| 批次主档日期 | `MCH1` 有生产日/到期日，**不是**库龄精确来源 | Lot 有 `ORIGINATION_DATE/EXPIRATION_DATE`，收货日仍在事务 | `InventBatch.ProdDate/ExpDate`，无收货日 | `produced_at / expiry_date`，无入库日 |
| 库龄计算 | 基于收货层 + FIFO 评估；账龄报表按“最早未清收货层” | Inventory Aging 报表按事务日期与 receipt layer 重建 | Inventory Aging report 按 FIFO 层匹配收/发 | 未实现 |
| FIFO 成本层 | 物料账/库存层 | `CST_LAYER` | `InventTrans` 层 + 成本事务 | 无 |

### 2.1 二次确认（官方文档核对结果）

| 系统 | 官方口径 | 对本项目的含义 |
|---|---|---|
| Dynamics 365 | 官方文档明确：库龄报表「按期间桶汇总各桶的**入库总量**，然后按 **FIFO 原则扣减出库总量**，与物料所用库存模型无关」；金额用**平均单位成本**；并建议「物料和仓库很多时」改用 **Inventory aging report storage**（持久化存储版） | ① FIFO 扣减是行业标准算法，与本规格 §5.3 一致；② 微软自己承认大数据量要落存储 → 本规格 P0 余额投影 + P1 快照的路线正确 |
| SAP | 即时库存放 `MARD`（物料/工厂/库位），**历史期间库存**放 `MARDH`（按会计年度+期间的行快照）、批次库存历史放 `MCHBH`；期间库龄 = 上一期间快照 + 本期 `MSEG` 变动 | SAP 不靠全量扫描物料凭证算库龄，而是**按月快照**。这直接支撑本规格「P0 投影、P1 月度快照」的分层 |
| Oracle EBS | 库龄报表的通行实现是对收发事务做 **FIFO 回溯**，原因是「Oracle Inventory 并不总是记录某一具体单位的具体收货日期」；成本取 `CST_ITEM_COSTS` / `CST_QUANTITY_LAYERS` | ① 「不记录每单位收货日」是行业普遍现状，改造成本高；② 精确到层必须引入 `CST_QUANTITY_LAYERS` 这类层表 → 本规格 P1 |

**二次确认结论**：三家头部产品没有一家把「入库日期」放在批次主档上作为唯一来源。

- D365 用**事务的 Physical date** 现场按 FIFO 扣减；
- SAP 用**月度库存快照表**做历史口径；
- Oracle 用**成本层表**承载 receipt layer。

三者共同点：**入库日期属于"库存层/事务"，属于批次库存的派生属性，不属于物料或批次主档**。本规格 §3 选 B（余额行投影）作为 P0、C（层表）作为 P1，与三家路线一致；差异只在"是否物化"。

本项目的差异化优势：`inventory_balances` 已经按 组织/库位/物料/批次/状态/段 聚合，天然就是 SAP `MARD`+`MCHB` 的等价物，所以 P0 只需补一个日期列，不需要新建宽表。

### 2.2 Oracle Fusion 补充确认（2026-11-06）

| Oracle Fusion 对象 | 事实 | 对本规格的含义 |
|---|---|---|
| `INV_ONHAND_QUANTITIES_DETAIL` | 一行 = **一次收货切片**，字段 **`DATE_RECEIVED`**，出库按 FIFO 消耗；`SUM(quantity)` 才是余额 | 精确库龄的正解是"收货层"，即本规格 P1 `inventory_layers` |
| `INV_ONHAND_QUANTITIES_SUMMARY` | 由明细汇出的即时余额 | 即本规格 P0 的 `inventory_balances` 角色 |
| `INV_LOT_NUMBERS` | 只有 `ORIGINATION_DATE` / `EXPIRATION_DATE` / `RETEST_DATE` / `MATURITY_DATE` / `HOLD_DATE`，**无收货日期** | 佐证 D3：不往 `batches` 加收货日 |
| Cost Management | Standard / Average / **Actual(FIFO)**，FIFO 为逐收货层；不支持 LIFO；Valuation Unit 可到批次/序列号 | 层表同时承载 `receipt_date` + `unit_cost` 是可行路线（P1） |

**关键差异**：Oracle 是 **detail 为源、summary 为派生**（同事务汇出）；本规格 P0 是"事务 → 余额"投影。P1 落地时必须照 Oracle：`inventory_layers` 为源，`inventory_balances` 由层汇出并对账 `SUM(remaining_qty) = qty_on_hand`，**不能维护两本独立账**。

详见 `docs/specs/research-oracle-fusion-inventory-costing-2026-11-06.md`。

---

## 3. 模型选项对比

| 方案 | 载体 | 优点 | 缺点 | 适用 |
|---|---|---|---|---|
| A 批次主档 | `batches.first_received_at` | 最简单，批次列表可直接显示 | 同批次多次收货/多库位只有一个日期；部分消耗后仍显示最早日期；无法做精确 FIFO | 仅展示 |
| B 余额行 | `inventory_balances.first_received_date` | 无需新表；天然按 组织/库位/批次/状态/段 拆分；能出库龄分布 | 余额是聚合，旧层耗尽而新层仍在时日期偏老（近似） | **P0 推荐** |
| C 库存层 | `inventory_layers.receipt_date` + `qty_remaining` | 精确 FIFO/库龄/成本；支持层追溯 | 新增台账，必须与余额对账；出库/红冲/调拨都要改 | **P1** |
| D 纯事务流派生 | 不建表，扫描 `inventory_transactions` | 零冗余、零一致性问题 | 每次报表全量扫描；红冲/调拨/负库存逻辑复杂；SQLite 性能差 | 临时报表 |

**推荐路线**：P0 = B；P1 = C（B 作为 C 的汇总投影保留）。

---

## 4. 决策点（默认建议）

| # | 决策 | 建议 |
|---|---|---|
| D1 | 库龄起算日期 | ✅ **入库过账日**（`inventory_transactions.transaction_date`）；`actual_arrival_date` 仅作辅助指标，不参与库龄（ADR-02） |
| D2 | 日期归属粒度 | ✅ **余额行**（org/location/item/batch/status/segment），即“批次库存属性”；明细页按需精确重建，不建全量层表（ADR-01） |
| D3 | 批次主档是否加入库日 | **P0 不加**；批次入库日由余额行/读模型提供，避免双写 |
| D4 | 清零规则 | `qty_on_hand` 变为 0 时 `first_received_date = NULL`；再次入库重新起算 |
| D5 | 红冲 | REVERSAL 分录不参与“最早入库日”起算；若红冲导致清零，按 D4 |
| D6 | 跨组织调拨 | 库龄在**目标组织**重新起算（目标入库事务日期）；全局原始库龄 P1 用层链路实现 |
| D7 | 负数库存 | 允许负库存时 `first_received_date = NULL`，报表单列“负库存/未定义”桶 |
| D8 | 库龄分桶 | 0-30 / 31-60 / 61-90 / 91-180 / >180 天；参数化，默认以上 |
| D9 | 精确 FIFO | P1 `inventory_layers`；P0 不上层表 |

---

## 5. P0 模型设计

### 5.1 字段

`meta/schemas/inventory_balance.yaml` 增加：

| 字段 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `first_received_date` | date | 否 | 当前余额行“最早未清零入库日期”；空 = 无库存 / 负数 / 历史数据未回填 |

- 唯一键不变（L263-268）。
- 不加 `last_received_date`：P0 报表不需要；需要时从事务查询。
- UI：列表默认隐藏，库龄报表/详情展示；`semantics.filterable: true`，`filter_type: date_range`。

YAML 字段定义（插在 `updated_at` 之前）：

```yaml
  - id: first_received_date
    name: 最早入库日期
    type: date
    db_column: first_received_date
    nullable: true
    description: 当前余额行最早未清零的入库过账日；空=无库存/负库存/未回填
    semantics:
      meaning: 库龄起算日（最早未清零入库层）
      filterable: true
      filter_type: date_range
      readonly: true
      derived: true
      note: 由库存过账维护，不可手工编辑；口径为过账日，非实际到货日
```

索引：**不需要新增 `(org_id, item_id)`**——现有 `idx_inv_balance_org_item (org_id, item_id, stock_status)` 已覆盖（`inventory_balance.yaml` L269-270）。仅可选增加：

```yaml
  - fields: [first_received_date]
    name: idx_inv_balance_first_received
    description: 可选；仅跨组织“最早库存”排序查询使用，单组织报表不需要
```

**默认不加**该索引：库龄报表必带 `org_id` 过滤，走现有唯一索引最左前缀即可；加了反而增加每次 UPSERT 的写放大。

### 5.2 写入规则（`inventory_posting_service._apply_balance` L681-704）

**必须先改签名**：`_apply_balance(normalized)` 拿不到红冲标记（`reversal_of` 只作为参数传给 `_insert_transaction`，且 `normalized` 本身不含该键）。改为：

```python
def _apply_balance(self, entry, reversal_of=None):
    is_receipt = entry.get('direction') == 'in' and not reversal_of
    # transaction_date 在 schema 中是 datetime，统一截到日期
    received = str(entry.get('transaction_date'))[:10] if is_receipt else None
```

调用点同步（`txn` 在 `_apply_balance` 之前已返回，直接复用其红冲标记，避免手工重复判断）：
- L185-188：`txn = self._insert_transaction(...)` → `self._apply_balance(normalized, reversal_of=txn.get('reversal_of_transaction_id'))`
- L335-338：同上，**不要**写死 `original['id']`

> 为什么必须显式传：`reverse()` 会把方向翻转（L301），**红冲出库 = direction 'in'**。若只按方向判断，红冲出库会被误当新入库层，日期直接回到红冲日。
>
> 为什么不直接把 `txn` 当 entry：`txn` 不含 `transaction_date`，仍需要 `normalized`；只借它的 `reversal_of_transaction_id` 一个字段。

UPSERT 改为：

```sql
INSERT INTO inventory_balances (
  org_id, location_id, item_id, batch_id, stock_status,
  stock_segment_type, project_id, project_task_id,
  sales_order_line_id, owner_party_id,
  qty_on_hand, qty_reserved, first_received_date, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
ON CONFLICT(org_id, location_id, item_id, batch_id, stock_status,
            stock_segment_type, project_id, project_task_id,
            sales_order_line_id, owner_party_id)
DO UPDATE SET
  first_received_date = CASE
    WHEN qty_on_hand + excluded.qty_on_hand <= 0 THEN NULL
    WHEN excluded.first_received_date IS NULL     THEN first_received_date
    WHEN first_received_date IS NULL              THEN excluded.first_received_date
    WHEN excluded.first_received_date < first_received_date
         THEN excluded.first_received_date
    ELSE first_received_date
  END,
  qty_on_hand = qty_on_hand + excluded.qty_on_hand,
  updated_at  = excluded.updated_at
```

要点（每条都对应一个测试用例）：

| # | 规则 | 原因 |
|---|---|---|
| R1 | 入库取更早日期 | 支持补录早于当前最早入库的单据 |
| R2 | 出库不改日期 | 出库不产生层 |
| R3 | 余额 ≤ 0 置 NULL | 清零后重新起算（D4） |
| R4 | **红冲不入层**（显式 `reversal_of`） | 红冲出库方向是 `in`，只判方向会误起算 |
| R5 | 先判断 `<= 0` 再判断日期 | SQLite `SET` 表达式按旧行值求值，顺序不能反 |
| R6 | 用 `CASE` 而非 `MIN()` | SQLite 标量 `min(NULL, x)` 返回 NULL，会丢日期 |

**不新增 SQL 条数**：仍是同一条 UPSERT，只多了 4 个 CASE 分支。

### 5.3 重建规则（`rebuild_balances` L503-525）

现有重建只按收发净额重算数量，会丢日期。**不能用 Python 把事务读进内存再做 FIFO**（O(事务数) 内存，千万级不可接受），改用**单条窗口函数 SQL**（本机 SQLite 3.50.4，项目 Python 3.11 内置 ≥3.37，窗口函数可用）：

```sql
-- 1) 只把“真实入库”当层；红冲入库（reversal_of 非空）排除
WITH receipt AS (
  SELECT location_id, item_id, COALESCE(batch_id, 0) AS batch_id,
         stock_status, stock_segment_type, project_id, project_task_id,
         sales_order_line_id, owner_party_id,
         date(transaction_date) AS transaction_date, id,
         SUM(base_qty) OVER (
           PARTITION BY location_id, item_id, COALESCE(batch_id, 0),
                        stock_status, stock_segment_type, project_id,
                        project_task_id, sales_order_line_id, owner_party_id
           ORDER BY transaction_date, id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS cum_in
  FROM inventory_transactions
  WHERE org_id = ?
    AND direction = 'in'
    AND reversal_of_transaction_id IS NULL
),
-- 2) 净出库 = 出库 - 被红冲的出库（红冲出库为 direction='in'）
outbound AS (
  SELECT location_id, item_id, COALESCE(batch_id, 0) AS batch_id,
         stock_status, stock_segment_type, project_id, project_task_id,
         sales_order_line_id, owner_party_id,
         SUM(CASE WHEN direction = 'out' THEN base_qty ELSE -base_qty END)
           AS net_out
  FROM inventory_transactions
  WHERE org_id = ?
    AND (direction = 'out'
         OR (direction = 'in' AND reversal_of_transaction_id IS NOT NULL))
  GROUP BY location_id, item_id, COALESCE(batch_id, 0), stock_status,
           stock_segment_type, project_id, project_task_id,
           sales_order_line_id, owner_party_id
)
-- 3) 累计入库首次超过净出库的那一层 = 最早未清层
SELECT r.location_id, r.item_id, r.batch_id, r.stock_status,
       r.stock_segment_type, r.project_id, r.project_task_id,
       r.sales_order_line_id, r.owner_party_id,
       MIN(r.transaction_date) AS first_received_date
FROM receipt r
LEFT JOIN outbound o
  ON  o.location_id = r.location_id
  AND o.item_id = r.item_id
  AND o.batch_id = r.batch_id
  AND o.stock_status = r.stock_status
  AND o.stock_segment_type = r.stock_segment_type
  AND o.project_id = r.project_id
  AND o.project_task_id = r.project_task_id
  AND o.sales_order_line_id = r.sales_order_line_id
  AND o.owner_party_id = r.owner_party_id
WHERE r.cum_in > COALESCE(o.net_out, 0)
GROUP BY r.location_id, r.item_id, r.batch_id, r.stock_status,
         r.stock_segment_type, r.project_id, r.project_task_id,
         r.sales_order_line_id, r.owner_party_id
```

原理（FIFO 等价式）：总出库会优先吃掉最早的入库，所以「累计入库量 > 净出库量」的第一笔入库，就是仍有剩余的**最早未清层**。无满足行 ⇒ 余额 ≤ 0 ⇒ NULL。

三个必须写对的细节：

| 细节 | 若写错会怎样 |
|---|---|
| `reversal_of_transaction_id IS NULL` 才计入层 | 红冲出库（方向 `in`）被当成新层，库龄回到红冲日 |
| `net_out` 减去红冲出库 | 红冲出库后净出库偏大，最早层判晚，库龄偏年轻 |
| 不加 `total_in > total_out` | 负库存时该条件把所有行过滤掉，结果仍是 NULL，属冗余；但误加在窗口里会引发全表再聚合 |

代价：一次表扫描 + 窗口排序，O(事务数)，无 Python 侧累积。**按 `org_id` 分批执行**，避免跨组织大排序。

同一段 SQL 必须只存在一份：抽到 `inventory_aging_service.first_received_date_sql()`，供 `rebuild_balances`、迁移回填、测试对照共用。

### 5.4 读模型（新增 `meta/services/inventory_aging_service.py`）

```python
class InventoryAgingService:
    BUCKETS = (30, 60, 90, 180)          # 闭区间上界：0-30 表示 0 <= d <= 30

    def report(self, *, org_id: int, as_of: str | None = None,
               location_id: int | None = None, item_id: int | None = None,
               batch_id: int | None = None, stock_status: str | None = None,
               group_by: str = 'balance',
               bucket_edges: Sequence[int] | None = None,
               include_zero: bool = False) -> dict

    def detail(self, *, org_id: int, location_id: int, item_id: int,
               batch_id: int = 0, stock_status: str = 'unrestricted',
               stock_segment_type: str = 'owned',
               project_id: int = 0, project_task_id: int = 0,
               sales_order_line_id: int = 0, owner_party_id: int = 0,
               as_of: str | None = None) -> dict

    @staticmethod
    def first_received_date_sql(org_filter: bool = True) -> str
```

**report 契约**

| 项 | 规则 |
|---|---|
| `org_id` | **必填**，缺失抛 `INV_AGING_ORG_REQUIRED` |
| `as_of` | 缺省今天；非法日期抛 `INV_AGING_DATE_INVALID`；**不晚于今天不强制**（允许模拟未来时点） |
| `group_by` | `balance`（默认，逐余额键）/ `item` / `batch`；后两者在服务内聚合，不新增 SQL |
| `include_zero` | 默认 `False`，过滤 `qty_on_hand = 0` |
| 数据源 | **只读 `inventory_balances`**，不扫事务（§10.7 红线） |
| `days_in_stock` | `(as_of - first_received_date).days`；`< 0` 时取 0 且标 `date_anomaly=true`（补录未来日期） |
| `age_bucket` | `0-30 / 31-60 / 61-90 / 91-180 / >180`；`qty <= 0` 或日期为空 ⇒ `UNASSIGNED` |

响应：

```json
{
  "as_of": "2026-11-06",
  "bucket_edges": [30, 60, 90, 180],
  "rows": [{
    "org_id": 1, "location_id": 3, "item_id": 42, "batch_id": 0,
    "stock_status": "unrestricted", "stock_segment_type": "owned",
    "project_id": 0, "project_task_id": 0,
    "sales_order_line_id": 0, "owner_party_id": 0,
    "qty_on_hand": 12.0, "first_received_date": "2026-08-01",
    "days_in_stock": 97, "age_bucket": "91-180", "date_anomaly": false
  }],
  "summary": [{"bucket": "0-30", "qty": 120.0}, {"bucket": "UNASSIGNED", "qty": 5.0}],
  "total_qty": 125.0,
  "unassigned_qty": 5.0
}
```

**合计约束（验收 AC-3）**：`Σ summary.qty == Σ rows.qty_on_hand`，且 `unassigned_qty == summary[UNASSIGNED]`。

不做物化视图、不加报表表：按余额行实时计算，数据量可控。

### 5.5 明细钻取（精确重建，补偿余额法误差）

余额法只给“最早未清零日期”。用户点开某个余额键时，对**该键**重放 §5.3 的 receipt/outbound CTE，逐层输出：

```sql
WITH receipt AS (
  SELECT transaction_date, id, base_qty,
         SUM(base_qty) OVER (ORDER BY transaction_date, id
                             ROWS UNBOUNDED PRECEDING) AS cum_in
  FROM inventory_transactions
  WHERE <key 全等> AND direction = 'in'
    AND reversal_of_transaction_id IS NULL
), net AS (
  SELECT COALESCE(SUM(CASE WHEN direction = 'out' THEN base_qty
                           ELSE -base_qty END), 0) AS net_out
  FROM inventory_transactions
  WHERE <key 全等>
    AND (direction = 'out'
         OR (direction = 'in' AND reversal_of_transaction_id IS NOT NULL))
)
SELECT date(transaction_date) AS receipt_date,
       base_qty AS layer_qty,
       MAX(0, MIN(base_qty, cum_in - net.net_out)) AS remaining_qty,
       CAST(julianday(?) - julianday(transaction_date) AS INTEGER) AS days_in_stock
FROM receipt, net
WHERE cum_in > net.net_out
ORDER BY transaction_date, id
```

| 列 | 说明 |
|---|---|
| `receipt_date` | 该入库层日期 |
| `layer_qty` | 该次入库数量 |
| `remaining_qty` | 扣减 FIFO 后剩余 |
| `days_in_stock` | 该层库龄 |

约束：`Σ remaining_qty == inventory_balances.qty_on_hand`（同键）——这是钻取页的自校验，不一致时返回 `reconciled: false` 并在日志告警，不抛错阻断。

代价 O(该键事务数)，通常几十到几百行，毫秒级；只在用户钻取时执行，不进入列表默认路径。这是 P0 在不建层表的前提下拿到“精确到底层”的手段。

---

## 6. P1 库存层（预留设计，不实施）

`inventory_layers` 关键列：

| 列 | 说明 |
|---|---|
| `org_id / location_id / item_id / batch_id / stock_status / stock_segment_type+段键` | 与余额键一致，便于对账 |
| `receipt_date` | 入库业务日期 |
| `receipt_qty / remaining_qty` | 层数量与剩余 |
| `unit_cost` | 可选，FIFO 成本 |
| `source_transaction_id / source_doc_type / source_doc_id` | 溯源 |
| `created_at` | 落库时间 |

约束：`Σ remaining_qty = inventory_balances.qty_on_hand`（按余额键）；出库按 FIFO 消耗层（与 P7 的 FEFO 选择正交：选择决定拣哪个批次，层决定该批次内先耗哪次入库）。

---

## 7. 迁移 `v224__inventory_balance_received_date.py`

最新迁移为 `v223__shipment_reverse.py`，故本迁移取 **v224**。

| 步骤 | 内容 |
|---|---|
| 1 | `PRAGMA table_info(inventory_balances)` 判列；缺则 `ALTER TABLE inventory_balances ADD COLUMN first_received_date DATE`（幂等） |
| 2 | 回填：`UPDATE inventory_balances AS b SET first_received_date = a.first_received_date FROM (<§5.3 CTE>) AS a WHERE <10 列全等> AND b.qty_on_hand > 0 AND a.first_received_date IS NOT NULL`；无事务历史的保持 NULL。**不把事务加载到 Python** |
| 3 | 索引：**默认不建**（§5.1 / §10.4）；仅当后续出现跨组织“最早库存”查询再加 |
| 4 | `verify`：列存在；`SELECT COUNT(*) FROM inventory_balances WHERE qty_on_hand > 0 AND first_received_date IS NULL` 输出为“待人工核查数”；`rollback`：不回滚列（SQLite 删列风险高），仅允许重跑回填 |

回填幂等性：`UPDATE` 只覆盖 `first_received_date`，**且必须带 `a.first_received_date IS NOT NULL`**，否则某键事务全被红冲时会把已有日期写成 NULL；重复执行结果相同，不得清空已有值。

回填后必须抽查 3 个键（有多次入库的、有红冲的、有清零后重入的），与 §5.5 钻取结果比对，作为迁移验收证据。

### 7.1 二次检查补充口径

| 检查点 | 结论 |
|---|---|
| **SQLite 版本** | `UPDATE … FROM` 需 ≥ 3.33。运行时为 Python 3.11（内置 3.39+），迁移第一行断言 `sqlite3.sqlite_version_info >= (3, 33, 0)`，不满足直接失败并提示，不做静默降级 |
| **`transaction_date` 类型** | schema 声明为 `datetime`（实际多为 `YYYY-MM-DD`）。所有 SQL 一律 `date(transaction_date)`，写入前 `str(...)[:10]`，避免 `first_received_date` 混入时分秒 |
| **期初库存（无任何事务）** | **不伪造日期**：保持 NULL，报表落 `UNASSIGNED`，迁移打印数量。业务确认后可用一次性脚本 `scripts/backfill_first_received_date.py --org N --date YYYY-MM-DD` 指定起始日 |
| 期初口径依据 | SAP 561 期初上载默认把**过账日设为当天**，即“上线日”就是库龄起点；我们不隐藏这一假设，而是要求业务显式给日期 |
| **时区** | `as_of` 取本地日期；`transaction_date` 是业务日期（不是 `created_at` 时间戳），无需时区换算 |
| **在库 vs 可用** | 库龄按 `qty_on_hand`（含质检/冻结），不扣 `qty_reserved`；报表可按 `stock_status` 分组，但不默认排除任何状态 |
| **group_by=item/batch 聚合** | **先按余额行分桶，再对桶内数量求和**；展示用 `MIN(first_received_date)`，不得对日期求平均，也不得用聚合后的日期重算桶 |
| **负数库存** | 计入 `UNASSIGNED`；`summary` 合计与 `rows` 合计必须相等（可为负） |
| **`include_zero`** | 只过滤 `qty_on_hand = 0`；负数不被过滤（否则合计对不上） |

`generated_schema.sql` 由生成流程重建，不手改。

---

## 8. 测试与验收

新增 `meta/tests/test_inventory_aging.py`：

| 用例 | 操作 | 断言 |
|---|---|---|
| T1 | 迁移首次执行 + 重复执行 | 列存在；`first_received_date` 不为 `NOT NULL`；重复执行不报错 |
| T2 | 11-01 入库 10 | 余额行 `first_received_date='2026-11-01'`，`qty=10` |
| T3 | 继续 11-05 入库 5 | 日期仍 `11-01`（不得后移） |
| T4 | 补录 10-20 入库 2 | 日期前移为 `10-20` |
| T5 | 出库 3 | 日期不变，`qty=14` |
| T6 | 出库至清零 | `qty=0` 且日期为 `NULL` |
| T7 | 清零后再入库 4 | 日期 = 新入库日，不是旧日期 |
| T8 | 入库 10 后全量红冲 | `qty=0`、日期 `NULL` |
| T9 | 出库 5 后红冲该出库（方向 `in`） | 日期**不变**（红冲不得形成新层） |
| T10 | 分两次入库 + 部分出库，执行 `rebuild_balances` | 日期与逐笔过账结果一致 |
| T11 | 桶边界：`as_of=2026-11-06`，入库日 10-07/10-06/09-07/09-06/05-09/05-08 | 分别落 `0-30/31-60/61-90/91-180/>180`，边界值不得跨桶 |
| T12 | `qty=-2` 且日期为 NULL | `age_bucket='UNASSIGNED'`，`unassigned_qty=2` |
| T13 | `detail()` 对混合收发键 | `Σ remaining_qty == qty_on_hand`，`reconciled=true` |
| T14 | 入库时 `transaction_date='2026-11-01 14:30:00'` | 余额行存 `2026-11-01`，无时分秒 |
| T15 | 期初余额行（有 `qty_on_hand`、无事务） | `first_received_date IS NULL`，报表落 `UNASSIGNED`，迁移计数 +1 |
| T16 | 迁移回填遇到“事务全被红冲”的键 | 该键原有日期**不被写成 NULL**（幂等护栏） |
| T17 | `group_by='item'`，同物料两库位库龄不同 | 先分桶再求和；`days_in_stock` 取 `MIN` 日期计算，不是平均值 |
| T18 | SQLite 版本断言 | 版本 <3.33 时迁移显式失败，错误信息含所需版本 |

测试用 `meta/tests/inventory_test_doubles.py` 的 `inv.ORG_ID/LOCATION_ID/ITEM_ID`；红冲走 `reverse()` 而非手工插分录，确保 `reversal_of_transaction_id` 真实写入。

验收：AC-1 余额行有入库日期；AC-2 出库/清零/重建规则正确；AC-3 库龄报表按桶汇总且合计等于 `qty_on_hand`；AC-4 既有库存/收货/调拨测试无回归。

执行：

```
python d:\filework\test.py --single meta/tests/test_inventory_aging.py
python d:\filework\test.py --failed
```

---

## 9. 影响文件清单

| 文件 | 改动 |
|---|---|
| `meta/schemas/inventory_balance.yaml` | 新增 `first_received_date`（不新增索引） |
| `meta/services/inventory_posting_service.py` | `_apply_balance` 维护日期；`rebuild_balances` 重建日期 |
| `meta/services/inventory_aging_service.py` | 新增：FIFO 首个未清层日期 + 库龄报表 |
| `meta/migrations/v224__inventory_balance_received_date.py` | 新迁移（列 + 回填） |
| `meta/tests/test_inventory_aging.py` | 新测试 |
| `meta/schemas/generated_schema.sql` | 由生成流程重建 |

---

## 10. 性能专章（二次确认）

### 10.1 结论

| 问题 | 结论 |
|---|---|
| 加库龄列会让过账变慢吗 | **不会**。`_apply_balance` 是 `INSERT … ON CONFLICT DO UPDATE`，只多几个 `CASE` 表达式，**SQL 条数不变** |
| 库龄报表会不会拖垮系统 | **取决于数据源**。读余额行 = O(余额行数)；读事务流水 = O(事务行数)。前者是本规格的选择 |
| 重建会不会 OOM | 用窗口函数单遍 SQL，**不把事务读进内存**，不会 |
| 什么时候必须升级 | 事务 > 500 万行且要反复查历史时点库龄 → 加月度快照（SAP 路线）；要精确 FIFO 成本 → 上层表 |

### 10.2 写入路径（每次过账）

现状单行过账的 SQL 次数（`inventory_posting_service.py` L143-189）：`normalize_entry`（物料/单位/库位约 3 查）+ `validate_segment` + `_posting_block_active` + `_find_existing` + `_current_qty` + `INSERT transaction` + `_apply_balance` ≈ **8 条**。

P0 库龄增量：**0 条**。日期在同一条 UPSERT 的 `CASE` 里算完（§5.2）。

P7 效期（并行需求）增量也必须为 **0 条**：`resolve_batch` 现在 `SELECT id, batch_no, item_id, org_id, quality_status`（L184-186），把 `expiry_date` 加进同一 SELECT、`min_remaining_shelf_life_days` 用 `LEFT JOIN items` 取，**不新增查询**。切忌在循环里再查一次 `items`。

### 10.3 查询路径（库龄报表）

`SELECT … FROM inventory_balances WHERE org_id = ? AND qty_on_hand <> 0` → 代价 **O(余额行数)**。

量级估算（SQLite 单机 SSD）：

| 余额行数 | 全组织扫描 | 单组织切片（有索引） |
|---|---|---|
| 1 万 | < 10 ms | < 3 ms |
| 10 万 | 50-100 ms | 10-20 ms |
| 100 万 | 0.5-1 s | 50-100 ms |

余额行 = 组织×库位×物料×批次×状态×段的组合数，**天然远小于事务行数**（事务每天累积，余额只增组合）。这就是 SAP 用 `MARD` 而不是扫 `MSEG` 的原因。

反面参照：Oracle EBS 的自定义库龄 SQL 需要按 FIFO 回溯 `MTL_MATERIAL_TRANSACTIONS`，同量级库要跑几分钟——用户担心的"性能问题"是真实存在的，但它属于**方案 D（纯事务流派生）**，本规格不采用。

### 10.4 索引补充

| 表 | 现状 | 新增 | 理由 |
|---|---|---|---|
| `inventory_balances` | 唯一索引 `uq_inv_balance_segment`（首列 `org_id`）+ **`idx_inv_balance_org_item (org_id, item_id, stock_status)` 已存在** | **无** | 库龄报表必带 `org_id`；按物料筛选走 `idx_inv_balance_org_item`，无需重复建索引 |
| `inventory_transactions` | `idx_inv_tx_org_item_date`、`idx_inv_tx_location` | **P0 不加** | 重建本就按组织整批扫；`batch_id` 维度查询若后续变热，再加 `(org_id, batch_id, transaction_date)` |

> 修正：早期草稿称“只按物料查库龄无法走索引”，与实际不符——`idx_inv_balance_org_item` 已在 L269-270 建好。

### 10.5 P1 层表的写入放大（提前说明）

`inventory_layers` 上线后：每次入库 +1 行；每次出库按 FIFO 更新 N 个层的 `remaining_qty`（N = 涉及层数，通常 1-3）。写入放大约 **1.5-2 倍**，且需要与余额行对账。这是"精确"的代价，所以 P0 不采用。

### 10.6 规模阈值（触发升级的条件）

| 指标 | 阈值 | 动作 |
|---|---|---|
| 余额行数 | < 50 万 | P0 实时计算，不预聚合 |
| 余额行数 | ≥ 50 万 且报表慢 | 加只读缓存或按组织预聚合（先不动模型） |
| 事务行数 | > 500 万 且需反复查历史时点 | 加 `inventory_aging_snapshots`（月度快照，SAP `MARDH` 路线），由 `ops_scheduler` 月初写 |
| 需要精确 FIFO 成本 | 任意规模 | 上 P1 `inventory_layers` |

### 10.7 禁止项（性能红线）

1. **禁止**在报表接口里现场扫 `inventory_transactions` 做 FIFO。
2. **禁止**在过账循环里新增按行查询 `items` / `batches`（必须并入既有 SELECT）。
3. **禁止**用 Python 全量加载事务做 FIFO（重建/迁移都不行）。
4. **禁止**给 `inventory_balances` 加无索引的 `created_at` 排序分页（用键集分页）。

---

## 11. 决策记录（ADR，2026-11-06 二次确认）

### ADR-01：余额行近似 vs 直接上库存层

**决策：P0 采用余额行 `first_received_date` + 明细页按需精确重建；不建全量 `inventory_layers`。**

| 维度 | 余额行近似（选中） | 全量库存层（暂不选） |
|---|---|---|
| 模型改动 | 1 个列（不新增索引） | 1 张新表 + BO/API/UI/权限 + 对账 |
| 写入成本 | 0 条额外 SQL（同一条 UPSERT 内 CASE） | 入库 +1 行；出库更新 N 层，写入放大 1.5-2 倍 |
| 一致性 | 单一投影，天然与余额一致 | 双台账，必须常驻对账，否则数量对不上 |
| 精确度 | 只到“最早未清零日期”，同键多次入库会偏老 | 精确到每次入库层 |
| 风险 | 近似误差（有界、可解释） | 红冲/补录/负库存/调拨/预留/并发都要逐条定义 |
| 适用 | 库龄报表、呆滞分析、资金占用 | FIFO 成本核算、层级冻结/预留 |

**为什么现在不上层表**：

1. 当前诉求是“库龄”（资金/呆滞口径），不是 FIFO 成本核算；库存链路没有成本层需求。
2. 误差有界：同一余额键在“旧层未耗尽 + 新层进入”时才会偏老。批次通常一次产出、一次入库，同键多次入库是少数场景。
3. 层表是“第二本账”：SQLite 单写锁下，出库更新多层会拉长事务；红冲/补录/负库存/跨组织调拨每个都要定义层语义，属于独立项目量级。
4. 有补偿手段：明细钻取（§5.5）对单个键精确重放，用户点开才付费，成本 O(该键事务数)。

**升级触发条件（任一满足即启动层表）**：

- 需要按层做 FIFO 成本或按层冻结/预留；
- 发现“余额最早日”与钻取结果差异的金额占比超过阈值（建议 5%，按季度统计）；
- 事务量 > 500 万且需要频繁查询历史时点库龄（先用月度快照，仍不够再上层表）。

**已知误差示例（必须在报表口径中声明）**：

```
1/10 入库 10，3/15 入库 5，4/20 出库 10 → 余额 5
余额法：first_received_date = 1/10（偏老 64 天）
实际剩余：3/15 那批（钻取可见）
```

报表对外表述统一为“**最早未清零入库日**”，不承诺“精确 FIFO 层龄”；需要精确时走钻取。

---

### ADR-02：库龄按过账日 vs 实际到货日

**决策：主口径 = 过账日（`transaction_date`）；实际到货日只作辅助指标，不进入库龄主口径。**

| 维度 | 过账日（选中） | 实际到货日（不选为主口径） |
|---|---|---|
| 定义 | 库存事务/财务确认的业务日期 | 货物 physical 到达仓库的日期 |
| 一致性 | 与库存分录、余额、财务期间同源，可对账 | 与账期脱钩，期间库存无法解释 |
| 数据质量 | `required: true`，一定有值 | 可空；补录/提前过账会导致早于或晚于过账日 |
| 行业口径 | SAP 期间库存/库龄基于过账；D365 用 Physical date；Oracle 用 transaction date | WMS 的“在库停留/dock-to-stock”用实际到货 |
| 适用 | **库存库龄、呆滞、资金占用、期间报表** | 收货作业效率、在库停留、上架时效 |

**为什么选过账日**：

1. 库龄本质是“库存资金占用”，必须和账期一致；用实际到货日会出现“账上没入库但已计龄”的无法解释区间。
2. 现有链路已保证 `transaction_date = receipt.receipt_date`（收货过账），调拨/完工入库同理取各自业务日期，无需追加数据源。
3. `actual_arrival_date` 非必填，直接当主口径会让大量历史数据落到 `UNASSIGNED`。
4. 两家头部产品的主口径也都是事务日期，不是物理到货日。

**若业务确实需要物理口径**：增加并行指标 `physical_age_days = as_of - actual_arrival_date`，与 `stock_age_days` 并列展示；两者不互相替代，也不混入同一张桶报表。列入 P1。

**边界说明**：

- 跨组织调拨：目标组织按目标入库过账日重新起算（D6）；“原始收货日”需要层链路，P1。
- 退货入库：按退货过账日重新起算，不继承原发货日期。
- 红冲：按 D5，不参与最早入库日起算。

---

## 12. 非目标

- 批次主档新增入库日期列（D3）。
- 精确 FIFO 成本与层级别追溯（P1）。
- 库龄快照表/月末结账冻结（P1）。
- **库存金额与物料分类账**：SAP S/4 的 Material Ledger 属于 INV-5 估值范围，与库龄正交，见 `docs/specs/research-sap-s4-material-ledger-2026-11-06.md`。
- 跨组织原始库龄链路（P1）。
- 库龄报表前端页面（本规格只定义服务与数据模型；只读薄路由见 §5.4 / tasks P8-17，不新增 View BO）。
