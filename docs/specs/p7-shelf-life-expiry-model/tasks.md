# P7 效期模型 —— 任务清单

> 状态：**待评审批准**（批准前不写实现代码）
> 规格：[spec.md](./spec.md)

## 前置

- [ ] **G0 评审批准**：确认 D1–D8 决策；未批准不进入 T1。
  验收：评审记录（本文件勾选或会话确认）。

## 实施任务

- [ ] **T1 物料效期字段**
  文件：`meta/schemas/items.yaml`（`valuation_relevant` 之后、`barcode` 之前）
  内容：`shelf_life_days` / `min_remaining_shelf_life_days` / `expiry_warn_days`，`fieldGroup: 效期`，位置 280/290/300。
  验收：YAML 可被 schema loader 加载；字段出现在 item 表单/详情。

- [ ] **T2 批次到期索引**
  文件：`meta/schemas/batches.yaml` `indexes`
  内容：`idx_batch_expiry_date (expiry_date)`。
  验收：生成的 DDL 含索引；FEFO 查询可用索引。

- [ ] **T3 批次效期自动推导**
  文件：`meta/services/batch_service.py`
  内容：`_validate_dates` 改实例方法；空 `expiry_date` + `produced_at` + 物料 `shelf_life_days>0` ⇒ 推导；手工值优先；`_load_item` SELECT 加 `shelf_life_days`。
  验收：T2 用例（spec §7）通过；既有 `BATCH_EXPIRY_INVALID` 不回归。

- [ ] **T4 出库过期拦截**
  文件：`meta/services/inventory_guard_service.py`
  内容：`resolve_batch` 增加 `allow_expired` / `as_of`；SELECT 加 `expiry_date`；新增 `INV_BATCH_EXPIRED`、`INV_SHELF_LIFE_SHORT`；`_item_min_remaining` fail-open。
  验收：T5–T7 用例通过。

- [ ] **T5 过账透传与豁免**
  文件：`meta/services/inventory_posting_service.py`（及 adjustment/count 调用点）
  内容：`post`/`reverse` 增加 `allow_expired_batch`；reverse 默认 True；盘亏/报废传 True。
  验收：报废过期批次可过账；正常出库被拦截。

- [ ] **T6 批次选择排除过期**
  文件：`meta/services/batch_selection_service.py`
  内容：`select_batches` 加 `as_of`；默认谓词加 `(expiry_date IS NULL OR expiry_date >= ?)`；审计 `default_predicate` 含 expiry。
  验收：T8 通过；`test_batch_selection_policy.py` 无回归。

- [ ] **T7 迁移 v224**
  文件：`meta/migrations/v224__item_shelf_life.py`
  内容：3 列 + 1 索引，幂等/verify/rollback（列不回滚）。
  验收：临时库 `migrate`+`verify` 通过；重复执行全 `[SKIP]`。

- [ ] **T8 测试文件**
  文件：`meta/tests/test_batch_shelf_life.py`
  内容：spec §7 T1–T8。
  验收：全部通过。

- [ ] **T9 回归与 schema 重建**
  内容：重建 `meta/schemas/generated_schema.sql`；跑既有批次/库存/选择策略测试。
  验收：`python d:\filework\test.py --failed` 全绿。

## 执行命令

```
python d:\filework\test.py --single meta/tests/test_batch_shelf_life.py
python d:\filework\test.py --single meta/tests/test_batches.py
python d:\filework\test.py --single meta/tests/test_batch_selection_policy.py
python d:\filework\test.py --failed
```

## P1（本清单不实施）

- 收货侧最小剩余效期校验（采购 / 调拨 / 完工三条链路）。
- 近效期 / 过期报表与通知（`ops_scheduler` 只读扫描，不改状态）。
- 跨组织调拨效期延续（`_clone_tree` / `_resolve_batch` 目标组织重建批次时复制 `produced_at` / `expiry_date`）。
- 单据行 `lot_no` → `batch_id` 改造评估。
