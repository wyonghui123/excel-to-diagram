# S8 Wave D 任务分解

> 依据：`docs/specs/s8-customer-invoice-wave-d/spec.md`
> 工作树：`D:\filework\s8-billing-worktree`（分支 `agent/s8-billing`，端口 3012）
> 测试唯一入口：`python d:\filework\test.py --root D:\filework\s8-billing-worktree --port 3012 --file <path>`

## M1 — 元数据基座（P0）

| 编号 | 任务 | 涉及文件 | 验收 |
|---|---|---|---|
| T46 | 迁移 v243：`type_definitions` 4 列 + `customer_invoices.direction` + 回填 + `SRV` 类型/号段 + `SINV.reversal_type_id` + 默认唯一索引 + `down` | `meta/migrations/v243__customer_invoice_document_role.py` | AC-1.1/1.2/1.3；迁移重复执行无副作用 |
| T47 | 服务层 `_resolve_document_meta` 替换 `_resolve_document_category`，删除映射字典，未知类型 fail-closed，`prepare_header` 写 `document_category/document_role` 与 `direction` | `meta/services/customer_invoice_service.py` | AC-2.1/2.2/2.3、AC-3.1/3.3 |
| T48 | `_is_red` 改方向驱动；`_negate_line` 调用点由 `direction` 判定；期次/核销口径同步 | 同上 | AC-3.2/3.3 |
| T49 | `reverse` 读 `reversal_type_id`，仅正向发票可红冲，否则 `INVOICE_REVERSE_ROLE_UNSUPPORTED` | 同上 | AC-4.1/4.2/4.3 |
| T50 | 测试：迁移回填、fail-closed、方向、红冲映射 | `meta/tests/test_customer_invoice_document_role.py`（新）、`meta/tests/test_customer_invoice_service.py` | 新增用例通过 |

## M1.5 — 逆向平台化（P0，FR-10）

| 编号 | 任务 | 涉及文件 | 验收 |
|---|---|---|---|
| T60 | 新增 `customer_invoice_red_letter` 创建器 + `invoice_billed_release` / `invoice_schedule_cancel` / `invoice_doc_flow_red_edge` / `recompute_customer_billing_status` 原语并注册 | `meta/core/reversal_primitives.py` | 原语注册可被 orchestrator 解析 |
| T61 | `customer_invoice.yaml` 增 `doc_effect`（posting.direction_field / faces / projections / reversal）；`reversal_profiles` 增 `customer_invoice`（red_reverse） | `meta/schemas/customer_invoice.yaml`、`meta/core/reversal_profiles.py` | AC-10.2 |
| T62 | `reverse` 改委托 `reversal_orchestrator.execute`，删除手写红冲事务块，保持返回契约 | `meta/services/customer_invoice_service.py` | AC-10.1 |
| T63 | `reversal_type_id` ⇔ `doc_effect.reversal` 一致性校验 + 既有四 BO 逆向回归 | `meta/core/doc_effect_validator.py`、测试 | AC-10.3/10.4/10.5 |

## M2 — 贷项分离与借项开放（P0）

| 编号 | 任务 | 涉及文件 | 验收 |
|---|---|---|---|
| T51 | 贷项来源角色断言（允许 invoice/debit_memo，禁止 credit_memo）；`SCR` 显示名调整 | `meta/services/customer_invoice_service.py`、`meta/migrations/v243__...py` | AC-5.1/5.2/5.3/5.4 |
| T52 | 新增 `create_debit_memo`：服务方法 + action 注册 + 权限种子 + 菜单 action + YAML action | `customer_invoice_service.py`、`bo_action_registrations.py`、`v243__...py`、`customer_invoice.yaml` | AC-6.1/6.3/6.4/6.5 |
| T53 | 过账回写按角色守卫：仅 `invoice` 回写 billed；借项/贷项防御性断言 | `customer_invoice_service.py` | AC-6.2 |
| T54 | 测试：借项创建/权限/引用校验/过账不回写/不可红冲 | `meta/tests/test_customer_invoice_debit_memo.py`（新）、`meta/tests/test_customer_invoice_document_role.py` | 用例通过 |

## M3 — 单一事实收敛（P1）

| 编号 | 任务 | 涉及文件 | 验收 |
|---|---|---|---|
| T55 | 冻结策略内核读 YAML：删除 `SUBMITTED_FROZEN_FIELDS`，YAML 增补只读字段，加对账测试 | `customer_invoice_guard_interceptor.py`、`customer_invoice.yaml`、`test_customer_invoice_guard.py` | AC-7.1/7.2/7.3 |
| T56 | `line_source_policy` 声明 + 内核执行 + 违规错误码 | `customer_invoice.yaml`、`customer_invoice_service.py`、测试 | AC-8.1/8.2/8.3 |

## M4 — 收尾（P2）

| 编号 | 任务 | 涉及文件 | 验收 |
|---|---|---|---|
| T57 | 血缘一致性断言（行外键 ⇒ doc_flow 边） | 测试 + 诊断查询 | AC-9.1/9.2 |
| T58 | 全量回归（发票全链路 + 订单 billed/billing_status + 期次） | `test.py --file` 分批 | 无回归 |
| T59 | 文档勾选与发布说明（含历史红字偏差说明） | `spec.md`、`tasks.md` | 交付说明完成 |

---

## 交付状态（2026-11-10）

| 任务 | 状态 | 证据 |
|---|---|---|
| T46 迁移 v243 | ✅ | `meta/migrations/v243__customer_invoice_document_role.py`；`test_customer_invoice_document_role.py` |
| T47 类型解析 fail-closed | ✅ | `_resolve_document_meta`；`INVOICE_TYPE_UNKNOWN` 用例 |
| T48 direction 驱动红字 | ✅ | `_is_red` / `_negate_line`；方向用例 |
| T49 reverse 映射 `reversal_type_id` | ✅ | `INVOICE_REVERSE_ROLE_UNSUPPORTED` 用例 |
| T50 元数据基座测试 | ✅ | 角色/方向/回填对账用例 |
| T60 逆向原语 + 创建器 | ✅ | `reversal_primitives.py` 注册表 |
| T61 YAML `doc_effect` + profile | ✅ | `customer_invoice.yaml`、`reversal_profiles.py` |
| T62 `reverse` 委托 orchestrator | ✅ | `test_customer_invoice_reversal_platform.py` |
| T63 声明一致性校验 | ✅ | `REVERSAL_NOT_DECLARED`（YAML 缺声明）/ `INVOICE_REVERSE_ROLE_UNSUPPORTED`（类型缺映射）；既有四 BO 逆向回归 |
| T51 贷项来源角色 | ✅ | `INVOICE_CREDIT_SOURCE_ROLE_INVALID` 用例 |
| T52 create_debit_memo | ✅ | action/权限/菜单/YAML；`test_customer_invoice_debit_memo.py` |
| T53 过账按角色回写 | ✅ | 借项 `billed_qty/billed_amount` 前后不变 |
| T54 借项测试 | ✅ | 9 用例 |
| T55 冻结策略 YAML 单一源 | ✅ | AC-7.1（monkeypatch）、AC-7.2（集合对账）、AC-7.3（同月可调） |
| T56 `line_source_policy` | ✅ | `test_customer_invoice_line_source_policy.py` 9 用例 |
| T57 血缘一致性断言 | ✅ | `test_customer_invoice_lineage.py` 9 用例；只读诊断 `lineage_violations` |
| T58 全量回归 | ✅ | 合并回归 **633 passed**（发票 207 / 计费·doc_effect 58 / doc_flow·发货 362 + 类型·YAML·BO API），Exit 0 |
| T59 文档与发布说明 | ✅ | `spec.md` §11；`type_definition.yaml` 4 字段声明（补 TBD-1） |

**回归命令（唯一入口）**

```
python d:\filework\test.py --root D:\filework\s8-billing-worktree --port 3012 --file <逗号分隔路径>
```

**遗留已知项**：历史 `SCR` 红字单据 `document_category` 仍为 `credit_memo`（`direction=-1` 正确），见 `spec.md` §11 发布说明；TBD-3（借项列表页入口）与 TBD-5（shipment/receipt 改类型级 direction 驱动）不在 Wave D 范围。