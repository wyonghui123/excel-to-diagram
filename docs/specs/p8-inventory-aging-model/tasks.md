# P8 实施任务清单（Inventory Aging）

> 对应规格：`docs/specs/p8-inventory-aging-model/spec.md`
> 状态：待执行　｜　原则：按序执行，每阶段可独立验证

---

## 阶段 1：字段与迁移（可独立验收）

| ID | 任务 | 文件 | 验收 |
|---|---|---|---|
| P8-0 | 迁移首行断言 `sqlite3.sqlite_version_info >= (3,33,0)` | 迁移文件 | 低版本显式失败，不静默降级 |
| P8-1 | `inventory_balances` 增加 `first_received_date` YAML 字段（`readonly/derived`，`filter_type: date_range`） | `meta/schemas/inventory_balance.yaml` | YAML 加载通过；生成 schema 含列 |
| P8-2 | 新增迁移 `v224__inventory_balance_received_date.py`：判列 + `ADD COLUMN` + `UPDATE … FROM` 回填 | `meta/migrations/v224__inventory_balance_received_date.py` | 重复执行幂等；`qty>0 且日期 NULL` 数量打印 |
| P8-3 | 重建 `generated_schema.sql` | 生成流程 | 列存在 |

**注意**：不建新索引（`idx_inv_balance_org_item` 已存在）。

---

## 阶段 2：写入路径（核心）

| ID | 任务 | 文件 | 验收 |
|---|---|---|---|
| P8-4 | `_apply_balance(entry, reversal_of=None)`：显式红冲标记；调用点传 `txn.get('reversal_of_transaction_id')`；入库日期截断为 10 位 | `meta/services/inventory_posting_service.py` | 两处调用点（L185-188、L335-338）同步 |
| P8-5 | UPSERT 增加 `first_received_date` 列 + 4 分支 `CASE`（≤0 → NULL；excluded 空 → 保留；旧空 → 取新；更早 → 前移） | 同上 | 规则 R1-R6 全部覆盖 |
| P8-6 | `rebuild_balances` 调用 `InventoryAgingService.first_received_date_sql()`，按 `org_id` 分批回填日期；数量对比逻辑不变 | 同上 | 重建后日期与逐笔一致 |

**红线**：不得新增 SQL 条数；不得在循环内查 `items`/`batches`。

---

## 阶段 3：读模型

| ID | 任务 | 文件 | 验收 |
|---|---|---|---|
| P8-7 | 新增 `first_received_date_sql(org_filter=True)`：receipt CTE（排除红冲入库）+ outbound CTE（扣减红冲出库）+ 首个未清层 | `meta/services/inventory_aging_service.py` | 与 §5.3 SQL 逐字一致 |
| P8-8 | `report()`：只读余额行，输出 `days_in_stock` / `age_bucket` / `summary` / `unassigned_qty` | 同上 | `Σsummary == Σqty` |
| P8-9 | `detail()`：单键逐层重放，返回 `remaining_qty` 与 `reconciled` | 同上 | `Σremaining == qty_on_hand` |
| P8-10 | 错误码：`INV_AGING_ORG_REQUIRED`、`INV_AGING_DATE_INVALID` | 同上 | 入参校验用例通过 |
| P8-15 | 期初库存口径：无事务余额保持 NULL，落 `UNASSIGNED`；提供一次性脚本 `scripts/backfill_first_received_date.py --org N --date YYYY-MM-DD` | `scripts/backfill_first_received_date.py` | 指定日期后报表不再 UNASSIGNED；脚本二次执行幂等 |
| P8-16 | 聚合口径：`group_by=item/batch` 先分桶再求和，展示日期取 `MIN` | `inventory_aging_service.py` | T17 通过，合计仍等于 `qty_on_hand` |
| P8-17 | 只读 API 薄路由：`GET /api/v1/inventory-aging/report`、`/detail`；权限复用 `inventory_balance:inventory_balance_read`；**不新增 View BO**（余额行明细走既有 `/api/v1/inventory_balances`，`first_received_date` 已自动生成 `date_range`） | `meta/api/inventory_aging_api.py` + `app_builder.py` + `server.py` | 200/400/401 用例通过；两条启动路径均登记 |

---

## 阶段 4：测试与回归

| ID | 任务 | 验收 |
|---|---|---|
| P8-11 | 新增 `meta/tests/test_inventory_aging.py`，覆盖 T1-T13 | 全绿 |
| P8-12 | 跑 P8 单文件测试 | `python d:\filework\test.py --single meta/tests/test_inventory_aging.py` |
| P8-13 | 跑库存相关回归 | `python d:\filework\test.py --file meta/tests/test_inventory_posting.py` 等 |
| P8-14 | 全量后串行确认 | `python d:\filework\test.py --all` → `--failed` |

---

## 完成定义（DoD）

- [x] 迁移在真实库执行成功，`verify` 输出可解释（v224 SUCCESS，回填 0 行、`qty>0 且日期 NULL` = 0；执行前已备份 `meta/architecture.db.bak-before-v224`）
- [x] 过账单条 SQL 数不变（8 条）：`_apply_balance` 仍是同一条 UPSERT，仅增加 4 个 CASE 分支
- [x] T1-T18 全绿，库存/收货/调拨无回归
- [x] 报表 `Σ桶 == qty_on_hand`，负库存落 `UNASSIGNED`
- [x] 日期只到“天”（无时分秒），桶边界按闭区间（30 天属 0-30）
- [x] 期初无事务余额不伪造日期，数量可解释
- [x] `group_by` 聚合先分桶再求和，日期取 `MIN`
- [x] 规格 §5.2/§5.3/§7 与代码逐条对应（无“文档一套、代码一套”）
