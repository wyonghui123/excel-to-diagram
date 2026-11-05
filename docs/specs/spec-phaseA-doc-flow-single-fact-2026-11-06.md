# 阶段 A 实施规格：单据流单一事实模型 P0

- 状态：**已实施（阶段 A / P0 完成）**
- 日期：2026-11-06
- 上游：`docs/specs/spec-doc-flow-single-fact-model-2026-11-05.md` §7.1 / §8 阶段 A
- 范围：仅 P0 五项（R-SF-01~05 / AC-SF-01~05），不含迁移回填与消耗公式单一化（阶段 B）

---

## 1. 已核实的代码事实（本次实现依据）

| 编号 | 位置 | 事实 |
|---|---|---|
| F1 | `meta/core/datasource.py:357-390` | `transaction()` 嵌套时直接 `yield`，不做 begin/commit；内层异常冒泡到外层统一回滚 |
| F2 | `meta/core/bo_framework.py:210-246` | 写动作默认由拦截器链事务包裹（`DISABLE_AUTO_TRANSACTION` 可关） |
| F3 | `meta/core/interceptors/shipment_guard_interceptor.py:20-23` | 拦截器自述边界：`before_action` 内服务已提交，随后持久化失败会留下跨表半真状态 |
| F4 | `meta/services/shipment_service.py:294-297` | 过账开关关闭 → `logger.info` 后返回 `{}`（无过账） |
| F5 | `meta/services/shipment_service.py:419-444` | 某行无库存事务 → `logger.warning` + `continue`；派生异常同样只告警 |
| F6 | `meta/services/shipment_service.py:240-256` | 过账/建边/计划行回写先执行，抬头行状态后更新；全程无显式事务 |
| F7 | `meta/services/shipment_service.py:716-738` | 冲销用 `delivered_qty = MAX(delivered_qty - ?, 0)` 增量算术 |
| F8 | `meta/services/shipment_service.py:1050-1060` | 发运用 `delivered_qty = COALESCE(delivered_qty,0) + ?` 增量算术 |
| F9 | `meta/core/doc_flow_attach.py:109-122` | 业务冲销 = `red_ink_edge` + `reverse_edge`（原地翻转 + 级联红字子边） |
| F10 | `meta/core/doc_flow_reversal.py:103-162` | `reverse_edge` 级联把 `derive_key LIKE 'red:<id>:%'` 的 active 红字边置 reversed |
| F11 | `meta/core/doc_flow_schema.py:44-121` | 边表 21 列，无 `edge_kind` / `reverses_edge_id`；`ensure_doc_flow_edge_tables` 走 `sync_schema_from_meta`，**启动期自动补列** |
| F12 | `meta/tests/test_shipment_service.py:126-138` | 测试替身 `_MemDS` 只有 `query/execute`，无 `transaction()` |
| F13 | `meta/tests/inventory_test_doubles.py:132-154` | 库存替身 `MemDS` 有 `transaction()` / `in_transaction` |
| F14 | `meta/migrations/v201__inventory_foundation.py:215` | `inventory_posting_enabled` 迁移默认值 `'0'`（过渡期默认关闭） |

---

## 2. 决策（决策完整，可直接落码）

| 编号 | 决策 | 理由 / 边界 |
|---|---|---|
| **DA-1** | 在 `shipment_service.py` 增加模块级 `_atomic(ds)` 上下文管理器：`ds` 有 `transaction()` 就进入，否则 `nullcontext()` | 兼容 F12 测试替身；生产数据源均实现 `transaction()`（F1）。不修改任何测试替身 |
| **DA-2** | `ship_confirm` / `receive` / `reverse` 三个入口整体包 `_atomic(self.ds)`；原方法体改名为 `_ship_confirm_impl` / `_receive_impl` / `_reverse_impl`，公开方法只做事务包裹 | 满足 R-SF-01；API 路径下为嵌套透传（F1/F2），直调服务路径也获得原子性 |
| **DA-3** | `_post_issue_inventory` 返回 `(txns, mode)`，`mode ∈ {'posted','disabled'}`；开关开启且某非取消行（qty>0）无事务 id，或 `post()` 返回 `skipped` ⇒ 抛 `ShipmentError(rule='DN_ISSUE_NOT_POSTED')` | F4/F5 的静默降级改为 fail-closed（R-SF-02）；开关关闭保持「显式降级」：`logger.error` + 返回体 `inventory_mode='disabled'`，不写边 |
| **DA-4** | 新增 `compensate_edge(app_ds, orig_edge_id, *, ref_id, derived_by='')`：追加 `edge_kind='reversal'`、`reverses_edge_id=原边`、`quantity_sign` 取原边反号（normal→red，red→normal）、`quantity=原边数量`、`rule_id=原规则#rev:{ref_id}`、`derive_key='rev:<原边id>:<ref_id>'`、`status='active'`；**不改原边** | R-SF-03/D3。聚合公式（active normal − active red）无需改动即可归零（F11 视图 / 引擎 Σ / 对账 / 追溯四处口径一致） |
| **DA-5** | `compensate_edge` 幂等键 = `derive_key`；重复同 `ref_id` 返回 `replay=True`；不同 `ref_id` 且 Σ active reversal > 原边数量 ⇒ `COMPENSATE_OVER_ORIGINAL` | 二次冲销幂等（AC-SF-03），防重复补偿 |
| **DA-6** | `reverse_edges_by_source` 改为补偿模式：对每条 active normal 边调 `compensate_edge`；再对其 active 红字子边（`derive_key LIKE 'red:<原边id>:%'`）同样调 `compensate_edge`（红字边补偿为 normal 号，聚合还原）；全程不改任何边 `status` | 满足 R-SF-03/04、AC-SF-03/04；历史红字边保持 `active` 可查 |
| **DA-7** | 旧三档 `reverse_edge` **保留原契约与级联**，仅在目标边已存在 active 补偿边时抛 `EDGE_HAS_COMPENSATION`；业务路径不再调用它 | R-SF-04 的「历史不抹除」在业务路径已达成；直接删级联会让 `0 − 红字` 聚合为负，且 `test_doc_flow_reversal.py` 6 处断言锁定该契约。此点记为本规格对 R-SF-04 的落地解释 |
| **DA-8** | 边表 `MetaObject` 增加 `edge_kind`（默认 `'normal'`）与 `reverses_edge_id`（默认 `''`）两列；不新增迁移，依赖启动期 `ensure_doc_flow_edge_tables` 补列 | F11；阶段 B 再补索引与 `biz_ref_*` |
| **DA-9** | 计划行 `delivered_qty` 改为同事务重算：`Σ shipment_lines.qty WHERE schedule_id=? AND status IN ('shipped','delivered','closed')`；`status` 按「promised_qty 非空且重算值≥promised_qty → completed，否则 confirmed」；重算值≤0 时 `delivery_id=NULL` | R-SF-05；行状态是唯一事实，边/计划行都只是投影 |
| **DA-10** | `ship_confirm` 内把「行/抬头置 shipped」提前到重算之前；`reverse` 内把 `_mark_reversed` 提前到重算之前 | 让重算能看到本次状态，无需第二套算术；同事务内顺序调整不改变对外语义 |
| **DA-11** | 删除 `_apply_schedule_delivery` / `_rollback_schedule_delivery` 的增量 SQL，合并为 `_refresh_schedule_delivery(schedule_ids)` | 一个数量只有一个权威（D4） |

---

## 3. 精确改动清单

### 3.1 `meta/core/doc_flow_schema.py`

在 `_build_edge_meta()` 的 fields 末尾（`derive_key` 之后）追加：

```python
_f("edge_kind", FieldType.STRING, required=True, default="normal",
   description="边类型：normal / counter / red_ink / reversal（D5）"),
_f("reverses_edge_id", FieldType.STRING, default="",
   description="补偿边指向的被补偿边 ID（reversal 专用，补偿不可变历史）"),
```

### 3.2 `meta/core/doc_flow_reversal.py`

1. `ReversalResult.kind` 新增取值 `'compensation'`。
2. 新增：

```python
def compensate_edge(app_ds, orig_edge_id, *, ref_id, derived_by="") -> ReversalResult
```

- `ref_id` 必填（否则 `REF_ID_REQUIRED`）。
- 幂等：`derive_key='rev:{orig_id}:{ref_id}'` 已存在 → `replay=True`。
- 守卫：`Σ(active, reverses_edge_id=orig_id) + 本次 > 原边 quantity` → `COMPENSATE_OVER_ORIGINAL`。
- 原边可为 `active` 任意 sign；`reversed` 边拒绝（`COMPENSATE_ORIG_REVERSED`）。
- 新边 `rule_id = orig.rule_id + '#rev:' + ref_id`，其余源/目标三元组、pool、unit、currency 复制原边。

3. `reverse_edge` 在守卫段追加：存在 `reverses_edge_id=? AND status='active'` ⇒ `EDGE_HAS_COMPENSATION`。

### 3.3 `meta/core/doc_flow_attach.py`

`reverse_edges_by_source` 主体替换为：

```python
rows = ... active normal 边
for row in rows:
    compensate_edge(app_ds, row['id'], ref_id=str(ref_id), derived_by=derived_by)
    for child in ... active 红字子边（derive_key LIKE 'red:<id>:%'）:
        compensate_edge(app_ds, child['id'], ref_id=str(ref_id), derived_by=derived_by)
```

保持「边表不可读 / 单边失败仅告警不阻断」的既有降级口径；返回成功补偿的**原边**条数。

### 3.4 `meta/services/shipment_service.py`

| 位置 | 改动 |
|---|---|
| 模块头 | 新增 `_atomic(ds)`（`contextlib.contextmanager` + `nullcontext`） |
| `ship_confirm` | 包装 `_atomic(self.ds)`；实现体改名 `_ship_confirm_impl` |
| `_ship_confirm_impl` | ① `_post_issue_inventory` 返回 `(txns, mode)`；② 状态更新块提前到计划行重算前；③ 调 `_refresh_schedule_delivery`；④ 返回体新增 `inventory_mode` |
| `_post_issue_inventory` | 开关关闭 → `logger.error('[shipment] 库存过账关闭，发运降级无事实边 id=%s')` + 返回 `({}, 'disabled')`；开关开启 → 逐行校验事务 id，缺失或 `skipped` ⇒ `ShipmentError(rule='DN_ISSUE_NOT_POSTED')` |
| `_write_issue_edges` | 无事务行分支不再需要（前置已抛错），保留整体 try/降级 |
| `receive` | 包装 `_atomic`；实现体改名 `_receive_impl` |
| `reverse` | 包装 `_atomic`；实现体改名 `_reverse_impl`；`_mark_reversed` 提到 `_refresh_schedule_delivery` 之前 |
| `_apply_schedule_delivery` / `_rollback_schedule_delivery` | 删除，统一为 `_refresh_schedule_delivery(schedule_ids)`（重算 SQL 见 DA-9） |

### 3.5 新测试 `meta/tests/test_shipment_single_fact.py`

| 用例 | 断言 |
|---|---|
| T1 AC-SF-01 | 过账开启；monkeypatch `_write_issue_edges` 抛异常 → `ShipmentError`/异常冒泡后：抬头仍 `staged`、`inventory_transactions` 为空、计划行 `delivered_qty=0` |
| T2 AC-SF-02 | 过账开启且 `post()` 返回 `skipped` → 抛 `ShipmentError(rule='DN_ISSUE_NOT_POSTED')`，抬头 `staged` |
| T3 AC-SF-02b | 过账关闭 → 发运成功且 `inventory_mode='disabled'`、边表 0 行 |
| T4 AC-SF-03 | `compensate_edge` 两次同 `ref_id`：第二次 `replay=True`；原边 `active`；消耗视图聚合 0；`edge_kind='reversal'`、`reverses_edge_id` 正确 |
| T5 AC-SF-04 | 原边先 `red_ink_edge`，再 `reverse_edges_by_source` → 红字子边仍 `active`；聚合 0；补偿边 2 条 |
| T6 AC-SF-05 | 计划行 100：先发 30、再发 20、冲销第二单 → `delivered_qty` 依次 30/50/30（重算，非算术漂移） |

---

## 4. 验证步骤（唯一入口）

```
python d:\filework\test.py --file meta/tests/test_shipment_single_fact.py
python d:\filework\test.py --file meta/tests/test_shipment_reverse.py
python d:\filework\test.py --file meta/tests/test_shipment_issue_doc_flow.py
python d:\filework\test.py --file meta/tests/test_shipment_return_doc_flow.py
python d:\filework\test.py --file meta/tests/test_shipment_service.py
python d:\filework\test.py --file meta/tests/test_doc_flow_reconcile.py
python d:\filework\test.py --file meta/tests/test_doc_flow_reversal.py
python d:\filework\test.py --file meta/tests/test_doc_flow_stage3_reversal.py
```

全部通过后 `python d:\filework\test.py --all`，若有并发假失败再 `--failed` 串行确认。

---

## 5. 显式不做（本阶段边界）

- 不新增迁移；不补 `biz_ref_type/biz_ref_id/stufe` 与索引（阶段 B R-SF-06）。
- 不合并 4 处消耗量公式（阶段 B R-SF-07）。
- 不改 `red_ink_edge` / `counter_edge` 的既有契约（阶段 C 视需要）。
- 不改前端、不改 `ActionExecutor` 通用事务（DA-2 已足够，规避 R1 风险）。
- 不做 `git commit`（需用户明确指示）。

---

## 6. 实施记录与验收证据（2026-11-06）

### 6.1 代码落点

| 决策 | 落点 |
|---|---|
| DA-1 / DA-2 | `shipment_service._atomic` + `ship_confirm/_receive_impl/_reverse_impl` 包装 |
| DA-3 | `_post_issue_inventory` 返回 `(txns, mode)`；开关开启时逐行校验事务 id |
| DA-4 / DA-5 | `doc_flow_reversal.compensate_edge`（`#rev:{ref}` 规则后缀 + `rev:{orig}:{ref}` 幂等锚） |
| DA-6 | `doc_flow_attach.reverse_edges_by_source` 全量改补偿，返回「新增补偿的原边数」 |
| DA-7 | `reverse_edge` 增加 `EDGE_HAS_COMPENSATION` 守卫；级联契约保持不变 |
| DA-8 | `doc_flow_schema` 两列 + `v214`/`v215` DDL 常量同步（旧库由 `sync_schema_from_meta` 补列） |
| DA-9 / DA-10 / DA-11 | 删除 `_apply/_rollback_schedule_delivery`，改 `_refresh_schedule_delivery`；状态先落再重算 |

### 6.2 验收状态

| 编号 | 状态 | 证据 |
|---|---|---|
| AC-SF-01 | ✅ | T1：注入后置异常后抬头仍 `staged`、无库存事务、余额与计划行不变 |
| AC-SF-02 | ✅ | T2 `DN_ISSUE_NOT_POSTED`；T3 `inventory_mode='disabled'` 且边表 0 行 |
| AC-SF-03 | ✅ | T4：原边 `active`、聚合 0、同 ref 重放 `replay=True`、超额 `COMPENSATE_OVER_ORIGINAL` |
| AC-SF-04 | ✅ | T5：原边与红字子边均 `active`，补偿边 2 条，聚合 0 |
| AC-SF-05 | ✅ | T6：30 → 50 → 30，同事务按交货行重算 |
| AC-SF-10 | ⚠️ | 新增 6 例 + 7 个既有套件全绿；`--all` 命中工作区基线失败（YAML / 权限 / 缺表 / 文件锁），已单独复现证明与本阶段无关（见任务清单执行记录） |

### 6.3 行为变更声明

- 业务冲销不再把原边置 `reversed`，改为追加 `edge_kind='reversal'` 补偿边；原边与红字子边保持 `active`。
- 冲销接口返回的 `idempotent` 语义不变；`reverse_edges_by_source` 的返回值为「本次新增补偿的原边数」。
- `ship_confirm` 返回体新增 `inventory_mode ∈ {'posted','disabled'}`。
- 过账开关开启时，缺失库存事务从「告警继续」改为「抛错回滚」。

---

## 7. 批准结论

DA-3 与 DA-7 已随本规格一并批准并落地；本阶段无待确认项。

