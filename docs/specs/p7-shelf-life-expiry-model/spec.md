# P7 效期模型（Shelf Life / Expiration）实现规格

> 状态：**草案 · 待评审**（未实施）
> 日期：2026-11-05
> 依据：现有代码盘点 + SAP / Oracle / Dynamics 365 对标
> 关联：`docs/specs/p4c-batch-master-data/spec.md`、`docs/specs/p5-routing-branch-parallel-batch-selection/spec.md`、`docs/specs/p6-serial-number-model/spec.md`

---

## 0. 决策点（已给默认建议，评审时逐条确认）

| # | 决策 | 建议 | 理由 |
|---|---|---|---|
| D1 | 效期归属对象 | **批次**；序列号不新增效期字段 | SAP MCH1 / Oracle lot / D365 InventBatch 均把效期挂在批次；序列号只做单件追溯 |
| D2 | 过期是否新增持久状态 | **不新增**；`expired` 由 `expiry_date` 与业务日期派生 | 避免定时任务漏跑导致状态与事实不一致；避免与 `quality_status=blocked` 混淆 |
| D3 | 物料级效期字段 | **新增 3 个**：总保质期天数 / 最小剩余保质期天数 / 近效期预警天数 | 没有物料级保质期就无法自动推导批次效期（SAP MARA-MHDHB 的最小等价物） |
| D4 | 过期库存出库 | **可用桶禁止出库**；盘亏/报废/状态转移等非可用桶场景放行（显式 `allow_expired_batch=True`） | 与现有 `blocked` 批次的放行口径保持一致 |
| D5 | 单据行 `lot_no` 字符串 | **本期不改**，仍按 `batch_no` 关联批次主档 | 改 `batch_id` 影响收货/发运/调拨多张单据，单独立项 |
| D6 | FEFO 是否自动生效 | **不自动 seed 策略**；默认谓词排除过期批次，FEFO 仍由范围策略显式启用 | P5 已定「模板仅常量」，强行默认会改变既有拣货结果 |
| D7 | 收货剩余效期校验 | **P0 只做出库侧**；收货侧最小剩余效期校验列入 P1 | 收货侧还牵涉采购/调拨/完工三条链路，P0 控制范围 |
| D8 | 保质期单位 | **统一按天**（integer），不引入月/年与舍入规则 | SAP `IPRKZ/MTVER` 的月/年与舍入规则对当前业务过重 |

---

## 1. 目标与范围

**目标**：让「批次效期」从“手工填一个日期”升级为可推导、可校验、可拣货、可拦截的最小闭环。

**P0 包含**：
1. 物料主数据补效期字段（总保质期 / 最小剩余保质期 / 近效期阈值）。
2. 批次保存时按「产出时间 + 物料总保质期」自动推导 `expiry_date`（手工填写优先）。
3. 库存出库时拦截已过期批次；剩余效期不足时拦截。
4. 批次选择默认排除过期批次。
5. `expiry_date` 索引（FEFO / 效期查询性能）。

**P1（本文只留接口，不实施）**：收货侧剩余效期校验、近效期报表 / 通知、跨组织调拨效期延续、过期批次自动冻结作业。

**非目标**：序列号效期、`lot_controlled` 开关、单据行 `batch_id` 化、保质期月/年单位、批次成本。

---

## 2. 现状盘点

| 对象 | 现状 | 缺口 |
|---|---|---|
| `batches` | 已有 `produced_at` / `expiry_date` / `potency_pct` / `grade_code` / `quality_status`（`meta/schemas/batches.yaml` §408-465） | 无 `expiry_date` 索引；无自动推导；无“过期”语义 |
| `BatchService` | 仅校验 `expiry >= date(produced_at)`（`meta/services/batch_service.py` `_validate_dates` L243-250） | 不读取物料保质期；`expiry_date` 可长期为空 |
| `InventoryGuardService.resolve_batch` | 只校验批次归属与 `quality_status=blocked`（L179-211） | **已过期批次仍可正常出库**；无剩余效期校验 |
| `InventoryPostingService.post` | 透传 `allow_blocked_batch`（L107-156） | 无 `allow_expired_batch` |
| `BatchSelectionService` | 默认谓词 `quality_status='unrestricted' AND status != 'closed'`（L32-33）；NULL 已排最后（`_order_clause` L187-196） | **默认不过滤过期**；FEFO 仅常量不生效 |
| `inventory_balances` | 已有 `batch_id` 维度，0=无批次（`meta/schemas/inventory_balance.yaml` L105-111） | 无 `expiry_date` 投影（可 join 批次，P0 不加列） |
| `items` | 有 `serial_tracked` 等开关（L616-656），**无任何效期字段** | 无保质期来源，无法自动推导 |
| 单据行 | `receipt_line.lot_no` / `shipment_line.lot_no` 为字符串（L346 / L224） | 无法在过账时直接拿到批次效期（P1 评估 `batch_id` 化） |
| `handling_unit_items` | 有 `batch_id`（L140-156），HU 不承载效期 | 正确边界，HU 无需加效期 |
| 跨组织收货 | `_clone_tree` 按目标组织重建批次关联，`_resolve_batch` 仅查不建（`handling_unit_service.py` L1542-1598 / L1289-1295） | 目标组织无批次时 `batch_id` 置空；效期延续需 P1 单独立项 |

---

## 3. 对标矩阵

| 能力 | SAP S/4HANA | Oracle（EBS / Fusion） | Dynamics 365 | 本项目 P0 |
|---|---|---|---|---|
| 物料总保质期 | `MARA-MHDHB`（总保质期）、`MARA-IPRKZ`（单位指示）、`MARA-MTVER`（舍入规则） | 物料主数据 Shelf Life（天）/ Lot Control | `InventTable` Shelf life period / unit | `items.shelf_life_days`（天） |
| 最小剩余保质期 | `MARA-MHDRZ` | 收货/发运校验参数 | 批次/物料效期控制 | `items.min_remaining_shelf_life_days` |
| 批次效期 | `MCH1-VFDAT`（到期日）、`MCH1-HSDAT`（生产日） | `MTL_LOT_NUMBERS.EXPIRATION_DATE` / `ORIGINATION_DATE`；Lot Status | `InventBatch.ProdDate` / `ExpDate`；批处置状态 | 已有 `produced_at` / `expiry_date` |
| 收货自动算效期 | 收货日期（或生产日）+ 总保质期，按舍入规则 | 收货时按 Shelf Life 推导到期日 | 按 shelf life 推导 | 产出时间 + 总保质期；**收货侧 P1** |
| 过期拦截 | 效期检查 + 批次状态 / 库存状态 | Lot Status / 效期动作 | 批次处置 + 效期控制 | 出库拦截（P0） |
| FEFO | 批次确定策略按 `VFDAT` 升序 | 拣货规则 FEFO | 预留原则 FEFO | 已有策略模板，默认排除过期 |
| 近效期预警 | 报表 / 工作流 | 报表 / 通知 | 报表 / 预警 | P1 |
| 效期与质量冻结分离 | 效期到期 ≠ 质量冻结 | Expiration action 与 Lot Status 分离 | 效期控制与批次处置分离 | 派生 `expired`，不写 `quality_status` |

结论：本项目缺的不是「批次效期字段」，而是**物料级保质期来源 + 出库拦截 + 过期默认排除**三件套。

---

## 4. 模型设计

### 4.1 `items` 新增字段（`meta/schemas/items.yaml`，插入 `valuation_relevant` 之后、`barcode` 之前）

| 字段 | 类型 | 必填 | 默认 | 约束 | 语义 |
|---|---|---|---|---|---|
| `shelf_life_days` | integer | 否 | — | `>= 0`；`0/空` = 不管理效期 | 物料总保质期（天） |
| `min_remaining_shelf_life_days` | integer | 否 | — | `>= 0`；`0/空` = 不校验 | 出库要求的最小剩余保质期（天） |
| `expiry_warn_days` | integer | 否 | — | `>= 0`；空 = 服务层默认 30 | 剩余天数 ≤ 该值进入近效期 |

UI：统一 `fieldGroup: 效期`，`fieldGroupPosition: 280 / 290 / 300`，`widget: number`。
不新增 `lot_controlled`：本期沿用“批次可选”现状，避免批次选择/库存过账口径连带改造。

### 4.2 `batches`（只加索引，不加列）

在 `meta/schemas/batches.yaml` 的 `indexes` 增加：

```yaml
  - fields: [expiry_date]
    name: idx_batch_expiry_date
    description: FEFO / 效期区间查询
```

不新增 `expired` 状态列，不新增 `expiry_source` 列：推导逻辑只在保存时补值，事实仍是 `expiry_date`。

### 4.3 派生口径（服务层，不建视图）

- `days_to_expiry = expiry_date - 业务日期`；
- `is_expired = days_to_expiry < 0`；
- `is_near_expiry = 0 <= days_to_expiry <= COALESCE(item.expiry_warn_days, 30)`；
- 业务日期来源：出库过账用过账日期（缺省 `date.today()`）。

不建 `v_batch_expiry` 视图：P1 报表再评估，避免视图对 `date('now')` 的时区/测试不确定性。

---

## 5. 校验规则与错误码

### 5.1 `BatchService`（`meta/services/batch_service.py`）

`_validate_dates` 由 `@staticmethod` 改为实例方法，并扩展：

1. 保留：`expiry < produced` ⇒ `BATCH_EXPIRY_INVALID`。
2. 新增推导：`expiry_date` 为空、`produced_at` 非空、物料 `shelf_life_days > 0` ⇒
   `expiry_date = produced_at + shelf_life_days`（回写 `merged['expiry_date']`）。
3. 手工填写优先：`expiry_date` 非空时**不覆盖**。
4. `_load_item` 的 SELECT 增加 `shelf_life_days`。
5. 不新增“效期必填”硬校验：计划批次的 `produced_at` 可能为空，硬性必填会阻断计划流程。

错误码新增：无（推导失败不抛错；仅保留既有 `BATCH_EXPIRY_INVALID`）。

### 5.2 `InventoryGuardService.resolve_batch`（`meta/services/inventory_guard_service.py` L179-211）

签名扩展：

```python
def resolve_batch(self, batch_id, item_id, org_id, direction,
                  stock_status='unrestricted', allow_blocked=False,
                  allow_expired=False, as_of=None) -> Optional[Dict[str, Any]]:
```

新增校验（在现有 `blocked` 校验之后）：

| 条件 | 错误码 | 消息 |
|---|---|---|
| `direction='out'`、`expiry_date` 非空、`expiry_date < as_of`、`allow_expired=False` | `INV_BATCH_EXPIRED` | 批次 {batch_no} 已于 {expiry_date} 过期，禁止出库 |
| `direction='out'`、剩余天数 `< item.min_remaining_shelf_life_days`、且 `stock_status='unrestricted'`、`allow_expired=False` | `INV_SHELF_LIFE_SHORT` | 批次 {batch_no} 剩余保质期 {days} 天，低于物料要求 {min} 天 |

SELECT 增加 `expiry_date`；新增 `_item_min_remaining(item_id)` 查询（失败 fail-open，与现有风格一致）。

### 5.3 `InventoryPostingService`（`meta/services/inventory_posting_service.py`）

- `post(...)` 新增参数 `allow_expired_batch: bool = False`，透传到 `guard.resolve_batch`；逐条分录传 `as_of=posting_date`（分录无日期时 `date.today()`）。
- `reverse(...)` 同样透传，默认 `True`（冲销历史过期批次不应被新规则阻断）。
- 盘亏/报废/状态转移调用方（`inventory_adjustment_service` / `inventory_count_service`）传 `allow_expired_batch=True`。

### 5.4 `BatchSelectionService`（`meta/services/batch_selection_service.py`）

- `select_batches(...)` 新增 `as_of: Optional[str] = None`（缺省 `date.today().isoformat()`）。
- `_apply_policy` 默认谓词增加：`(expiry_date IS NULL OR expiry_date >= ?)`，参数 `as_of`。
- `allow_blocked=True` 时**仍排除过期**（质检/返工如确需过期批次，用库存调整，不走批次选择）。
- `default_predicate` 审计字段追加 `expiry` 描述，保持可追溯。
- FEFO 模板不变；不 seed 默认策略（D6）。

---

## 6. 迁移 `v224__item_shelf_life.py`

| 步骤 | 内容 |
|---|---|
| 1 | `PRAGMA table_info(items)` 逐列判断，`ALTER TABLE items ADD COLUMN shelf_life_days INTEGER` |
| 2 | 同上：`min_remaining_shelf_life_days INTEGER`、`expiry_warn_days INTEGER` |
| 3 | `batches` 存在时 `CREATE INDEX IF NOT EXISTS idx_batch_expiry_date ON batches(expiry_date)` |
| 4 | `verify`：三列 + 索引存在；`rollback`：删索引，列不删（SQLite 列回滚不可靠，文档标注） |

约束：幂等（重复执行打印 `[SKIP]`），不写业务数据，不建菜单/权限。

`meta/schemas/generated_schema.sql` 由 schema 生成流程重建，**不手工编辑**；重建时注意工作区可能存在的其他会话改动。

---

## 7. 测试与验收

新增 `meta/tests/test_batch_shelf_life.py`：

| 用例 | 断言 |
|---|---|
| T1 | `v224` 在临时库建列 + 索引；重复执行幂等 |
| T2 | 物料 `shelf_life_days=365` + `produced_at=2026-01-01` ⇒ `expiry_date=2027-01-01` |
| T3 | 手工 `expiry_date` 不被覆盖 |
| T4 | `expiry < produced` ⇒ `BATCH_EXPIRY_INVALID` |
| T5 | 出库过期批次 ⇒ `INV_BATCH_EXPIRED` |
| T6 | `allow_expired=True` ⇒ 出库成功 |
| T7 | 剩余效期低于物料最小剩余 ⇒ `INV_SHELF_LIFE_SHORT`；非可用桶放行 |
| T8 | 批次选择排除过期、保留 `expiry_date IS NULL`；FEFO 顺序仍为 NULL 最后 |

验收：

- AC-1：物料可维护三个效期字段。
- AC-2：批次保存后自动得到正确 `expiry_date`。
- AC-3：过期批次无法通过可用桶出库过账。
- AC-4：报废/盘亏仍可处理过期批次。
- AC-5：批次选择结果不含过期批次。
- AC-6：新增索引在 `verify` 与真实库均存在。
- AC-7：既有批次/库存/选择策略测试无回归。

执行：

```
python d:\filework\test.py --single meta/tests/test_batch_shelf_life.py
python d:\filework\test.py --single meta/tests/test_batches.py
python d:\filework\test.py --single meta/tests/test_batch_selection_policy.py
python d:\filework\test.py --failed
```

---

## 8. 影响文件清单

| 文件 | 改动 |
|---|---|
| `meta/schemas/items.yaml` | 新增 3 个字段（效期分组） |
| `meta/schemas/batches.yaml` | 新增 `idx_batch_expiry_date` |
| `meta/services/batch_service.py` | `_validate_dates` 实例化 + 自动推导；`_load_item` 加列 |
| `meta/services/inventory_guard_service.py` | `resolve_batch` 加过期/剩余效期校验 |
| `meta/services/inventory_posting_service.py` | `post` / `reverse` 透传 `allow_expired_batch`、`as_of` |
| `meta/services/batch_selection_service.py` | 默认谓词排除过期；`as_of` 入参 |
| `meta/services/inventory_adjustment_service.py` | 盘亏/报废传 `allow_expired_batch=True`（以实际调用点为准） |
| `meta/services/inventory_count_service.py` | 盘亏传 `allow_expired_batch=True`（以实际调用点为准） |
| `meta/migrations/v224__item_shelf_life.py` | 新迁移 |
| `meta/tests/test_batch_shelf_life.py` | 新测试 |
| `meta/schemas/generated_schema.sql` | 由生成流程重建（不手改） |

---

## 9. 性能约束（与 P8 同一口径）

| 路径 | 要求 |
|---|---|
| 过账写入 | **0 条额外 SQL**。`resolve_batch` 现有 SELECT（`inventory_guard_service.py` L184-186）里增加 `expiry_date`，`min_remaining_shelf_life_days` 用 `LEFT JOIN items` 一并取出；禁止在 `post()` 循环里再查 `items` |
| 批次选择 | `_apply_policy` 新增的 `expiry_date` 条件走 `idx_batch_expiry_date`，不引入子查询 |
| 推导效期 | 只在批次保存时算一次，不在读路径计算 |
| 禁止 | 建 `v_batch_expiry` 视图或在列表接口里 `date('now')` 逐行比较 |

规模阈值：`batches` < 50 万行时索引足够；超过且 FEFO 查询变慢，再考虑按组织分区或物化近效期列表（P1）。
