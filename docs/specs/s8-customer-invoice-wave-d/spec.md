# S8 Wave D — 客户发票借贷项凭证：单一事实与元数据驱动补全

> 状态：待确认（Spec + RFC 已定稿）
> 基线：Wave C 已交付（`agent/s8-billing`，提交 `000f8a46` 含发票号一致性补丁）
> 关联：`docs/specs/s8-customer-invoice-wave-c/spec.md`、`docs/ARCHITECTURE_PRINCIPLES.md` §1、`docs/architecture/01-principles.md` §1

---

## 1. 背景与目标

### 1.1 背景

Wave C 已实现销售发票的提交/过账/红冲、计划开票、退货贷项、部分/多次/on-account 贷项。但“借贷项凭证”在**语义层**没有单一事实源，现状存在 5 处重复与 3 个隐式事实：

| 事实 | 现状分散位置 |
|---|---|
| 单据角色/类别 | `type_definitions.document_category`（`standard`/`credit_memo`/`debit_memo`）+ 头表 `document_category` + Python `_TYPE_CATEGORY_TO_DOCUMENT_CATEGORY` + YAML enum + v237 `ALLOWED_CATEGORIES` |
| 方向（正/负） | 不存在；由 `_is_red()` 的“类别 = credit_memo **或** `reversal_of_invoice_id` 非空”推断 |
| 红冲用哪个类型 | 硬编码 `SCR`（`RED_INVOICE_TYPE_CODE`），与贷项共用同一类型与号段 |
| 默认类型 | 硬编码 `SINV`（`DEFAULT_INVOICE_TYPE_CODE`） |
| 冻结策略 | YAML `state_field_policies` + Python `SUBMITTED_FROZEN_FIELDS` 双写 |
| 行来源许可 | 服务层隐式判断，借项行可引用 `order_line_id` 并在过账时回写 `billed_qty/billed_amount` |
| 血缘 | 行外键 + `doc_flow` 边双写 |

行业对照（Oracle Fusion AR / SAP SD / Odoo / D365 F&O）结论：头部产品普遍把**角色（Transaction Class / Billing Type）与方向（Creation Sign / 负数量）分离**，号段绑定类型，红冲/取消为独立类型。我们的目标形态取 Oracle 的“角色 + 方向”二维、SAP 的“类型级号段 + 独立红冲类型”。

### 1.2 目标

1. `type_definitions` 成为“角色 + 方向 + 号段 + 红冲映射 + 默认类型”的唯一事实源，前后端从元数据派生。
2. 删除类别翻译字典与隐式方向判断，未知类型**fail-closed**。
3. 红冲类型由元数据 `reversal_type_id` 决定，不再硬编码 `SCR`。
4. Debit Memo（借项通知单）正式开放为可创建单据，具备独立 action、权限与行来源约束。
5. 冻结策略与行来源策略回归 YAML 单一事实源，内核读取而非另行声明。

### 1.3 非目标

- 不做发票号取号时机调整（方案 B 已评估为非必需，见 Wave C 决策）。
- 不重写历史单据类型/号码（号码不可变，历史偏差只记录不迁移）。
- 不引入 AP 侧（供应商）借贷项；`scope_bo` 已分离，本波只做 AR。
- 不做前端自定义页面改造；action 与字段声明由 YAML 派生。

---

## 2. 需求类型总览

| 编号 | 类型 | 名称 | 优先级 | 里程碑 |
|---|---|---|---|---|
| FR-1 | 功能 | 类型元数据扩展（role/direction/reversal_type_id/is_default） | P0 | M1 |
| FR-2 | 功能 | 词汇统一与 fail-closed | P0 | M1 |
| FR-3 | 功能 | 方向驱动行符号与红字口径 | P0 | M1 |
| FR-4 | 功能 | 红冲类型元数据化（SINV→SRV） | P0 | M1 |
| FR-5 | 功能 | 贷项与红冲类型分离、贷项来源角色校验 | P0 | M2 |
| FR-6 | 功能 | Debit Memo 正式开放（action + 权限 + 行来源限制） | P0 | M2 |
| FR-7 | 功能 | 冻结策略单一来源（内核读 YAML） | P1 | M3 |
| FR-8 | 功能 | 行来源策略元数据化并由内核执行 | P1 | M3 |
| FR-9 | 功能 | 血缘一致性断言（行外键 ⇔ doc_flow 边） | P2 | M4 |
| NFR-1 | 非功能 | 迁移幂等、可回滚、不破坏历史数据 | P0 | M1 |
| NFR-2 | 非功能 | 类型元数据读取无 N+1、单请求 ≤ 1 次额外查询 | P1 | M2 |
| NFR-3 | 非功能 | 新增规则全部可测试、错误码稳定可断言 | P0 | 全程 |
| NFR-4 | 非功能 | 不改变既有前端契约（action 只增不改） | P1 | 全程 |
| IF-1 | 接口 | `customer_invoice.create_debit_memo` action 契约 | P0 | M2 |
| IF-2 | 接口 | YAML 新字段（`line_source_policy`、`direction`） | P1 | M3 |
| IF-3 | 接口 | `type_definitions` 表结构与字段元数据声明 | P0 | M1 |
| IF-4 | 接口 | 错误码清单 | P0 | M1 |
| TR-1 | 技术 | 迁移 v243 与回填方案 | P0 | M1 |
| TR-2 | 技术 | 服务层解析与缓存方案 | P0 | M1 |
| TR-3 | 技术 | 测试方案与回归范围 | P0 | 全程 |

---

## 3. 功能需求

### FR-1 类型元数据扩展（P0）

`type_definitions` 新增 4 列：

| 列 | 类型 | 约束 | 语义 |
|---|---|---|---|
| `document_role` | VARCHAR(32) | 可空（迁移回填后非空由应用层保证） | `invoice` / `credit_memo` / `debit_memo` / `cancellation` |
| `direction` | INTEGER | NOT NULL DEFAULT 1，取值 `1` / `-1` | 单据方向：正/负 |
| `reversal_type_id` | INTEGER | 自关联 FK，可空 | 该类型的红冲目标类型；空 = 不可红冲 |
| `is_default` | INTEGER | NOT NULL DEFAULT 0 | 同 `scope_bo + level + document_role` 内的默认类型 |

回填规则（按 code，幂等）：

| code | 现名称 | document_role | direction | is_default | reversal_type_id |
|---|---|---|---|---|---|
| `SINV` | 销售发票 | `invoice` | `1` | `1` | `SRV` |
| `SCR` | 红字销售发票 | `credit_memo` | `-1` | `0` | `NULL` |
| `SDN` | 借项通知单 | `debit_memo` | `1` | `1` | `NULL` |
| `SRV`（新增） | 红字销售发票 | `invoice` | `-1` | `0` | `NULL` |

其他 `scope_bo=customer_invoice` 的类型：按 `document_category` 映射（`standard`→`invoice`+1，`credit_memo`→`credit_memo`-1，`debit_memo`→`debit_memo`+1，`cancellation`→`cancellation`+1），默认方向 +1，`is_default=0`。

**验收标准**
- AC-1.1 迁移后 6 个类型行的 4 列均符合上表；`SRV` 存在且有独立号段 `SRV-{DATE:yyyymm}-{SEQ:5}`。
- AC-1.2 同 `scope_bo+level+document_role` 内 `is_default=1` 至多一条（唯一索引或迁移期断言）。
- AC-1.3 迁移可重复执行不产生重复列/重复类型/重复号段。

### FR-2 词汇统一与 fail-closed（P0）

- 删除 `_TYPE_CATEGORY_TO_DOCUMENT_CATEGORY`（`customer_invoice_service.py` L54-71 附近）。
- 新 `_resolve_document_meta(document_type_id)` 单次查询 `type_definitions` 返回 `(document_role, direction, reversal_type_id)`；实例级缓存，避免逐行查询。
- `document_category` 统一取 `document_role` 的 4 值（`invoice/credit_memo/debit_memo/cancellation`），头表列写快照。
- 类型不存在、`status != active`、`document_role` 为空/非法 → 抛 `INVOICE_TYPE_UNKNOWN`（`field_name='document_type_id'`）。
- v237 `ALLOWED_CATEGORIES` 白名单改为从 `type_definitions.document_role` 取值，不再维护独立常量。

**验收标准**
- AC-2.1 传入未登记类型 → `INVOICE_TYPE_UNKNOWN`，不再默认成 `invoice`。
- AC-2.2 已登记类型的头表 `document_category` 等于其 `document_role`（含 `SCR` → `credit_memo`）。
- AC-2.3 代码中不存在 `'standard'` 字面值与类别翻译字典。

### FR-3 方向驱动行符号与红字口径（P0）

- 头表新增 `direction INTEGER NOT NULL DEFAULT 1` 快照，创建时取类型 `direction` 并回填。
- 行符号统一由 `direction` 决定：`direction=-1` 时调用 `_negate_line` 生成负数行；`direction=1` 时行金额为正。
- `_is_red(header)` 改为 `header['direction'] == -1`，删除“类别=credit_memo 或 反转指针非空”的判断。
- 期次生成、核销、报表口径一律以 `direction` 为准，不再按类别推断。

**验收标准**
- AC-3.1 贷项（SCR）与红冲（SRV）头表 `direction=-1`，发票（SINV）与借项（SDN）为 `1`。
- AC-3.2 `_is_red` 仅依赖 `direction`，删除对 `document_category`/`reversal_of_invoice_id` 的依赖。
- AC-3.3 贷项/红冲行金额为负、发票/借项为正；头金额 = Σ 行金额恒成立（R-INV-7）。

### FR-4 红冲类型元数据化（P0）

- `reverse` 不再引用 `RED_INVOICE_TYPE_CODE`，改为读取源类型 `reversal_type_id`。
- 仅当源类型 `document_role='invoice'` 且 `direction=1` 且 `reversal_type_id` 非空时允许红冲；否则抛 `INVOICE_REVERSE_ROLE_UNSUPPORTED`。
- 红字单据 `direction=-1`、`reversal_type_id=NULL`，不生成期次（保持 R-INV-24）。

**验收标准**
- AC-4.1 `SINV` 红冲生成 `SRV` 单据，号码取自 `SRV` 号段。
- AC-4.2 对 `SCR`/`SDN` 调用 `reverse` → `INVOICE_REVERSE_ROLE_UNSUPPORTED`。
- AC-4.3 反转指针、原单 `status=reversed`、`doc_flow` 反向边行为不变。

### FR-5 贷项与红冲类型分离、贷项来源角色校验（P0）

- 贷项（含部分/多次/on-account/退货贷项）继续使用 `SCR`，角色 `credit_memo`、方向 `-1`；历史单据不改类型、不改号码。
- `SCR` 显示名调整为“销售贷项凭证”（code 不变）；`SRV` 显示名为“红字销售发票”。历史红字单据仍在 `SCR` 下，作为**已知历史偏差**记录于 §7。
- `create_credit_from_invoice` 增加源单据角色断言：允许 `invoice`、`debit_memo`；禁止 `credit_memo` → `INVOICE_CREDIT_SOURCE_ROLE_INVALID`。
- `create_credit_from_return_shipment` 与 on-account 贷项同样要求目标类型角色 `credit_memo`。

**验收标准**
- AC-5.1 对已过账发票开贷项成功，头 `document_category='credit_memo'`、`direction=-1`、类型 `SCR`。
- AC-5.2 对已过账贷项再开贷项 → `INVOICE_CREDIT_SOURCE_ROLE_INVALID`。
- AC-5.3 对已过账借项开贷项成功（用于冲正借项）。
- AC-5.4 历史 `SCR` 单据在迁移后 `direction=-1` 且 `document_category` 保持不变。

### FR-6 Debit Memo 正式开放（P0 / 方案 A）

**动作**：`customer_invoice.create_debit_memo`

**输入契约（IF-1）**

```json
{
  "customer_account_id": 101,
  "currency_id": 1,
  "org_id": 1,
  "invoice_date": "2026-11-10",
  "source_invoice_id": null,
  "reason": "运费补收",
  "remark": null,
  "lines": [
    {
      "item_id": 9001,
      "description": "运费补收",
      "qty": 1,
      "unit_price": 120.0,
      "tax_rate": 0.13,
      "order_line_id": null
    }
  ]
}
```

**行为**

1. 类型取 `scope_bo=customer_invoice, level=header, document_role=debit_memo, is_default=1` 的记录（`SDN`）；缺失 → `INVOICE_TYPE_UNKNOWN`。
2. 头表 `document_category='debit_memo'`、`direction=1`、取号（`SDN` 号段）。
3. 行金额为正；`order_line_id` 仅作**只读引用**：校验订单行存在、客户一致、币种一致，不校验可开票数量上限（借项是调整凭证）。
4. `source_invoice_id` 仅作参考引用（写入 `reversal_of_invoice_id` 留痕或关联字段），**不改变原发票状态**。
5. 过账时 `post` 对 `document_role != 'invoice'` 的行**跳过** `billed_qty/billed_amount` 回写（防污染）。
6. 权限：新增 `customer_invoice:customer_invoice_debit_memo`，授予与 `customer_invoice:customer_invoice_credit_memo` 相同的权限集；菜单 action 增加 `debit_memo`。
7. YAML `actions` 增加 `create_debit_memo`，`show_when` 与现有贷项一致（详情页对 `posted` 可见；列表页创建入口始终可见）。

**验收标准**
- AC-6.1 无 `debit_memo` 权限调用 → 403；有权限 → 创建草稿成功，`document_type_id=SDN`、`direction=1`。
- AC-6.2 借项过账后源订单行 `billed_qty/billed_amount` 不变（前后快照一致）。
- AC-6.3 借项行引用不存在/跨客户/跨币种订单行 → `INVOICE_DEBIT_LINE_SOURCE_INVALID`。
- AC-6.4 借项 `post` 生成期次（应收增加），`_is_red=false`。
- AC-6.5 借项不可红冲 → `INVOICE_REVERSE_ROLE_UNSUPPORTED`。

### FR-7 冻结策略单一来源（P1）

- 删除 Python `SUBMITTED_FROZEN_FIELDS`，`_assert_not_frozen` 改为从 YAML `customer_invoice.state_field_policies` 读取该状态的只读字段集合。
- YAML 增补：`direction`、`document_category`、`invoice_no`、`document_type_id` 在 `submitted`/`posted` 只读（`direction` 全状态只读）。
- 新增对账测试：YAML 声明的 `submitted` 只读集合 == 内核实际拦截集合。

**验收标准**
- AC-7.1 修改 YAML 只读字段后，内核行为随之变化（无需改 Python）。
- AC-7.2 对账测试在 YAML 与内核不一致时失败。
- AC-7.3 `invoice_date` 在 `submitted` 仍允许同月调整（与 Wave C 号码一致性补丁兼容），跨月仍抛 `INVOICE_NUMBER_PERIOD_MISMATCH`。

### FR-8 行来源策略元数据化（P1）

`customer_invoice.yaml` 新增顶层声明：

```yaml
line_source_policy:
  invoice: [shipment_line, order_line, plan, manual]
  credit_memo: [invoice_line, return_line, manual]
  debit_memo: [manual, order_line_readonly]
```

- 内核在插入行时按头表 `document_role` 校验 `source_doc_type` / `shipment_line_id` / `order_line_id` / `schedule_id` 组合，违规抛 `INVOICE_LINE_SOURCE_POLICY_VIOLATION`。
- `order_line_readonly` 语义：允许写入引用键，但过账不回写数量/金额（与 FR-6 第 3、5 条一致）。
- 行来源互斥（R-INV-3）保持：三选一或全空。

**验收标准**
- AC-8.1 发票行引用发货行合法；贷项行引用发货行 → `INVOICE_LINE_SOURCE_POLICY_VIOLATION`。
- AC-8.2 借项行引用订单行合法但不回写；手工行合法。
- AC-8.3 策略缺失的 role → 默认拒绝（fail-closed），并有测试覆盖。

### FR-9 血缘一致性断言（P2）

- 保留“行外键 + `doc_flow` 边”双事实，明确二者粒度不同：行外键=数量事实，`doc_flow`=单据关系事实。
- 新增校验：存在来源行外键 ⇒ 必存在对应 `doc_flow` 边；反向不强制（手工单据无边）。
- 提供只读诊断查询/测试，不作为运行时强拦截（避免阻塞历史数据）。

**验收标准**
- AC-9.1 新建发货开票单据的行外键与 `doc_flow` 边一一对应。
- AC-9.2 断言以测试形式运行，不改变过账事务行为。

### FR-10 逆向模型平台化（P0）

平台逆向统一为三层，各层单一事实源，不得互相替代：

| 层 | 回答的问题 | 单一事实源 |
|---|---|---|
| L1 凭证身份 | 什么凭证、方向、号段、红冲对应类型 | `type_definitions`（`document_role` / `direction` / `reversal_type_id` / `is_default`，**全 scope_bo 通用**） |
| L2 事实冲销 | 逆向如何冲事实边/库存/金额/状态 | `doc_effect.reversal` + `reversal_orchestrator`（固定 7 步） |
| L3 业务形态 | 红冲 / 退货 / 价值调整 | `document_category`（由 L1 派生，三类互不混同） |

三类逆向语义：`reversal`（同对象纠错凭证，回指原单，无新增库存流动）、`return`（实物逆流，产生反向库存事务，复用原 BO + `document_category=return`）、`adjustment`（借项/贷项等纯金额调整）。**补货不是逆向**，属正向新供给，不得进入本模型。

**行为**

1. `customer_invoice.yaml` 声明 `doc_effect`：`posting.direction_field: direction`；`reversal.from_states: [posted]`、`to_state: reversed`、`idempotent_states: [reversed]`、`order: declared`、`create_document.primitive: customer_invoice_red_letter`、`write_audit_fields`。
2. `faces`：`billed_release`（回滚 `billed_qty/billed_amount`）、`schedule_cancel`（取消原期次）、`doc_flow_red_edge`（写红字边 + 补偿原边）；`projections`：`order_billing_recompute`（重算订单 `billing_status`）。
3. `reverse` 委托 `reversal_orchestrator.execute`，**删除服务内手写红冲路径**（取号、建红字单、改状态、写边合并进创建器/写面）；返回契约保持 `red_invoice_id` / `red_invoice_no` / `red_line_ids` / `amounts`。
4. `reversal_profiles` 新增 `customer_invoice`（`mode=red_reverse`，档位与收货单一致）。
5. 一致性校验（fail-closed，双向）：`type_definitions.reversal_type_id` 非空 ⇔ 该 `scope_bo` 的 schema 声明了 `doc_effect.reversal`；类型有映射但 YAML 未声明 → `REVERSAL_NOT_DECLARED`，YAML 已声明但类型缺映射 → `INVOICE_REVERSE_ROLE_UNSUPPORTED`。
6. 迁移回填覆盖**所有** `scope_bo`：`document_category` → `direction`（`credit_memo`/`return`/`cancellation` 为 -1，其余 1），`document_category` → `document_role`（`standard`→`invoice`，其余同名）。
7. 已有的 `shipment` / `receipt` / `transfer_order` / `inventory_adjustment` 逆向声明不改写，只做兼容性回归。

**验收标准**
- AC-10.1 发票红冲经 `reversal_orchestrator.execute` 执行（单测断言调用入口），结果与既有契约一致。
- AC-10.2 发票 YAML 未声明 `doc_effect.reversal` 时，`reverse` fail-closed（`REVERSAL_NOT_DECLARED`）。
- AC-10.3 `reversal_type_id` 与 `doc_effect.reversal` 不一致时 `reverse` 双向 fail-closed（`REVERSAL_NOT_DECLARED` / `INVOICE_REVERSE_ROLE_UNSUPPORTED`），且无红字副作用。
- AC-10.4 迁移后 `shipments`、`receipt`、`transfer_order`、`inventory_adjustment` 既有逆向测试全部通过。
- AC-10.5 补货/正向补发单据不进入逆向模型（无 `reversal_type_id`）。

---

## 4. 非功能需求

| 编号 | 要求 |
|---|---|
| NFR-1 | 迁移幂等（`ADD COLUMN IF NOT EXISTS` 或列探测）、提供 `down` 回滚脚本；回填可重复执行 |
| NFR-2 | 类型元数据在服务实例内缓存，红冲/贷项/借项路径不产生额外 N+1 查询 |
| NFR-3 | 每条新规则有独立 rule code，测试以 rule code 断言，不匹配中文文案 |
| NFR-4 | 前端契约只增不改：新增 action/权限，不改既有 action 的入参出参 |
| NFR-5 | 日志：`INVOICE_TYPE_UNKNOWN`、策略违规记录 `document_type_id` 与 `document_role` |
| NFR-6 | 性能：单笔创建额外查询 ≤ 2（类型元数据 + 默认类型），过账路径不新增查询 |

---

## 5. 接口需求

### IF-1 `customer_invoice.create_debit_memo`

| 项 | 值 |
|---|---|
| 权限 | `customer_invoice:customer_invoice_debit_memo` |
| 幂等 | `False` |
| 必填 | `lines`（至少 1 行） |
| 输出 | `_customer_invoice_output_schema`（含 `id`、`invoice_no`、`document_type_id`、`document_category`、`direction`） |
| 错误 | 权限 403 / `INVOICE_TYPE_UNKNOWN` / `INVOICE_DEBIT_LINE_SOURCE_INVALID` / `INVOICE_LINE_SOURCE_POLICY_VIOLATION` |

### IF-2 YAML 契约

- `customer_invoice.yaml`
  - 新增字段 `direction`（integer，enum `1/-1`，只读，可筛选）。
  - 新增顶层 `line_source_policy`。
  - `actions` 增加 `create_debit_memo`。
  - `state_field_policies` 增补 `direction`、`document_category`、`invoice_no`、`document_type_id`。
- `type_definition.yaml`（若存在）：声明 `document_role`、`direction`、`reversal_type_id`、`is_default` 四个字段的 UI/筛选元数据。
- 权限种子：`v243` 插入 `customer_invoice:customer_invoice_debit_memo` 并授予 `customer_invoice:customer_invoice_credit_memo` 的全部权限集；菜单 `include_actions` 增加 `debit_memo`。

### IF-3 表结构

```sql
ALTER TABLE type_definitions ADD COLUMN document_role VARCHAR(32);
ALTER TABLE type_definitions ADD COLUMN direction INTEGER NOT NULL DEFAULT 1;
ALTER TABLE type_definitions ADD COLUMN reversal_type_id INTEGER;
ALTER TABLE type_definitions ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customer_invoices ADD COLUMN direction INTEGER NOT NULL DEFAULT 1;
CREATE UNIQUE INDEX uq_type_default_role
  ON type_definitions(scope_bo, level, document_role)
  WHERE is_default = 1;
```

### IF-4 错误码

| rule code | 触发条件 |
|---|---|
| `INVOICE_TYPE_UNKNOWN` | 类型不存在 / 非 active / 角色缺失或非法 |
| `INVOICE_REVERSE_ROLE_UNSUPPORTED` | 红冲非正向发票或缺少 `reversal_type_id` |
| `INVOICE_CREDIT_SOURCE_ROLE_INVALID` | 以贷项为来源再开贷项 |
| `INVOICE_DEBIT_LINE_SOURCE_INVALID` | 借项引用订单行不存在/跨客户/跨币种 |
| `INVOICE_LINE_SOURCE_POLICY_VIOLATION` | 行来源不符合 `line_source_policy` |
| `INVOICE_DEBIT_BILLED_WRITEBACK_FORBIDDEN` | 借项/贷项过账试图回写 billed 数量（防御性断言） |
| `REVERSAL_NOT_DECLARED` | 类型配置了 `reversal_type_id` 但 YAML 未声明 `doc_effect.reversal`（反向缺失由 `INVOICE_REVERSE_ROLE_UNSUPPORTED` 覆盖） |

### IF-5 `doc_effect.reversal` 契约（发票）

```yaml
doc_effect:
  posting:
    direction_field: direction
  faces:
    - id: billed_release
      primitive: invoice_billed_release
      args: {doc_id: "{id}", sign: -1}
    - id: schedule_cancel
      primitive: invoice_schedule_cancel
      args: {doc_id: "{id}"}
    - id: doc_flow_red_edge
      primitive: invoice_doc_flow_red_edge
      args: {doc_id: "{id}", red_doc_id: "{reversal.doc.id}"}
  projections:
    - id: order_billing_recompute
      primitive: recompute_customer_billing_status
      args: {order_ids: "{reversal.doc.order_ids}"}
  reversal:
    from_states: [posted]
    to_state: reversed
    idempotent_states: [reversed]
    order: declared
    create_document:
      primitive: customer_invoice_red_letter
    write_audit_fields:
      reversed_at: "{now}"
      updated_at: "{now}"
```

---

## 6. 技术需求

### 6.1 迁移 v243

文件：`meta/migrations/v243__customer_invoice_document_role.py`

1. 加列（幂等探测 `PRAGMA table_info`）。
2. 按 §FR-1 回填 6 个类型；插入 `SRV` 类型与号段；设置 `SINV.reversal_type_id`。
3. 回填 `customer_invoices.direction`（join `type_definitions`）。
4. 权限与菜单种子。
5. `down`：删除新增列/索引、删除 `SRV`、删除新权限（仅在无引用时）。

### 6.2 服务改动点

| 文件 | 改动 |
|---|---|
| `meta/services/customer_invoice_service.py` | `_resolve_document_meta`（替换 `_resolve_document_category`）、`prepare_header` 写 `direction`、`_is_red` 改方向、`_negate_line` 调用点由方向驱动、`reverse` 读 `reversal_type_id`、`post` 按 role 跳过 billed 回写、新增 `create_debit_memo`、贷项来源角色断言、行来源策略校验 |
| `meta/core/interceptors/customer_invoice_guard_interceptor.py` | `_assert_not_frozen` 读 YAML；新增 `direction` 不可变断言；红冲角色断言 |
| `meta/services/bo_action_registrations.py` | 注册 `create_debit_memo`（权限、schema） |
| `meta/migrations/v243__customer_invoice_document_role.py` | 新增 |
| `meta/schemas/customer_invoice.yaml` | `direction` 字段、`line_source_policy`、`actions`、`state_field_policies` |
| `meta/schemas/type_definition.yaml` | 4 个新字段声明 |
| `meta/tests/factories/_customer_invoice_helpers.py` | 种子增 `SRV` 类型/号段、`document_role/direction` 列回填 |

### 6.3 测试方案

入口（唯一）：

```
python d:\filework\test.py --root D:\filework\s8-billing-worktree --port 3012 --file <path>
```

| 测试文件 | 覆盖 |
|---|---|
| `meta/tests/test_customer_invoice_service.py` | FR-2/3/5/6 主路径：类型解析、方向、贷项来源断言、借项创建与过账不回写 |
| `meta/tests/test_customer_invoice_guard.py` | FR-4/7：红冲角色断言、冻结策略从 YAML 派生、direction 不可变 |
| `meta/tests/test_customer_invoice_actions.py`（或现有 action 测试） | FR-6：权限 403/成功、action 注册契约 |
| `meta/tests/test_customer_invoice_document_role.py`（新增） | FR-1/2：迁移回填、fail-closed、默认类型唯一、YAML↔内核冻结对账、行来源策略 |

预计新增/修改测试 ≥ 18 条，全部以 rule code 断言。

### 6.4 回归范围

- 发票：手工/发货/计划/退货贷项/on-account/红冲全链路。
- 订单：`billed_qty/billed_amount`、`billing_status` 不变（借项不参与）。
- 期次：仅发票与借项生成，贷项/红字不生成。
- 逆向平台：`shipment` / `receipt` / `transfer_order` / `inventory_adjustment` 既有红冲测试全量回归。

### 6.5 平台化落地（FR-10）

| 文件 | 改动 |
|---|---|
| `meta/core/reversal_primitives.py` | 新增 `customer_invoice_red_letter` 创建器 + `invoice_billed_release` / `invoice_schedule_cancel` / `invoice_doc_flow_red_edge` / `recompute_customer_billing_status` 原语并注册 |
| `meta/core/reversal_profiles.py` | 新增 `customer_invoice` profile（`red_reverse`） |
| `meta/core/doc_effect_validator.py` | 保持既有声明校验；新增 `reversal_type_id` ↔ `doc_effect.reversal` 一致性校验入口 |
| `meta/schemas/customer_invoice.yaml` | 新增 `doc_effect` 段 |
| `meta/services/customer_invoice_service.py` | `reverse` 改为 `reversal_orchestrator.execute`；删除手写红冲事务块 |

**兼容策略**：原语内部复用现有服务方法（`_negate_line` / `_apply_billed` / `_write_doc_flow_edges`），不复制业务规则；`reverse` 的取号与业务日期通过 `params` 透传给创建器（与 `receipt_red_letter` 同构）。

---

## 7. 约束与假设

1. 号码不可变：历史 `SCR` 红字单据不重编号、不重分类，`document_role` 按 `SCR` 统一记为 `credit_memo`。这是**已知历史偏差**，在发布说明中注明。
2. `SCR` 的 code 不变，仅显示名调整为“销售贷项凭证”；避免破坏既有单据引用与筛选。
3. 借项是调整凭证，不占用订单可开票量，不做数量上限校验。
4. 仅 `SINV` 可红冲；贷项/借项通过反向凭证冲正，不走 `reverse`。
5. 不修改 Wave C 的号码一致性补丁行为；`invoice_date` 在 submitted 允许同月调整。
6. 工作树：`D:\filework\s8-billing-worktree`，分支 `agent/s8-billing`，端口 3012；禁 pytest。
7. 若 `meta/schemas/type_definition.yaml` 不存在，则以 `type_definitions` 实际字段声明为准，并在 Spec 交付说明中标注。
8. 平台化边界：`document_role/direction` 是**类型元数据**，不是每张单据表的枚举；单据表只存 `direction` 快照（发票表已加），不新增 `document_role` 列（角色由类型派生）。
9. 补货/正向补发属正向新单，不纳入逆向模型；如需追溯“退货后补货”，走 `doc_flow` 正向新边。

---

## 8. 优先级与里程碑

| 里程碑 | 内容 | 交付判据 |
|---|---|---|
| M1 | FR-1/2/3/4（迁移 + 角色/方向 + fail-closed + 红冲映射） | 迁移与守卫/服务测试通过；`SCR`/`SRV`/`SINV`/`SDN` 角色方向正确 |
| M1.5 | FR-10（逆向平台化）：发票接入 `reversal_orchestrator` + profile + 一致性校验 + 既有逆向回归 | AC-10.1~10.5 通过；删除手写红冲路径 |
| M2 | FR-5/6（贷项分离 + 借项开放） | 借项 action 可用、权限生效、过账不回写；贷项来源断言生效 |
| M3 | FR-7/8（冻结与行来源单一源） | YAML 对账测试通过；策略违规有测试 |
| M4 | FR-9 + 文档收尾 | 血缘断言测试通过；Wave D 文档与发布说明完成 |

---

## 9. RFC（架构决策）

### 9.1 决策 D1：采用“角色 + 方向”二维，落两列

**理由**：Oracle 用 Transaction Class（角色）+ Creation Sign（方向）表达同一事实；SAP 用 Billing Type 隐含角色、用数量符号隐含方向。我们现状有角色（`document_category`）却没有方向，导致 `_is_red` 必须“类别或反转指针”二选一推断，且红冲与贷项共用类型。落两列即可让角色、方向各归一处，且不动既有 `document_category` 语义（快照）。

**备选**：
- 只加 `direction` 不加 `document_role`：无法消除 `standard`↔`invoice` 词汇映射，fail-open 仍在 → 否决。
- 单枚举把角色+方向压成一个字段（Odoo 式）：报表要“发票的全部负向单据”需枚举组合，且未来加 chargeback 等角色需改枚举 → 否决。

### 9.2 决策 D2：零历史改类型，新增 `SRV`

**理由**：现网贷项与红冲都用 `SCR`，且 `reversal_of_invoice_id` 两者都有值，`status` 也会因后续红冲而漂移，**没有可靠判别式**。任何自动重分类都会把部分单据标错，且号码前缀与类型号段不一致。因此保留 `SCR`（role=credit_memo）承载历史，新增 `SRV` 只服务今后红冲；`SINV.reversal_type_id=SRV`。

**代价**：历史红字单据的类别仍显示 `credit_memo`（方向 -1 正确）。可接受，因为方向才是冲减口径的事实；类别仅用于分组展示。

**备选**：
- 迁移重分类：需要人工判定清单，风险高 → 否决。
- 红冲继续用 `SCR`：无需新类型，但“红冲与贷项不可区分”的核心问题保留 → 否决。

### 9.3 决策 D3：冻结与行来源回归 YAML

**理由**：元数据驱动的定义是“YAML 唯一配置事实源，内核读取而非重复声明”。SAP Field Status、Oracle Profile 同为“配置驱动内核”。双写必然漂移，且 Wave C 已出现 `invoice_date` 在 YAML 与 Python 间口径不一致的苗头。

**约束**：冻结字段集合必须可枚举、可测试；对账测试防止 YAML 漏配。

### 9.4 决策 D4：借项不回写 billed，且不做数量上限

**理由**：借项是“增加应收的调整凭证”，不是开票行为。D365 用负数量行表达贷项，其数量回写规则也同样受“退货单”约束，不适用于调整。Oracle Debit Memo 独立于订单履行链路。若借项占用可开票量，会导致订单提前关闭或漏开票。

### 9.5 决策 D5：逆向模型三层统一，发票接入已有逆向引擎

**选项**

| 方案 | 描述 | 结论 |
|---|---|---|
| A 各自实现 | 发票继续自写红冲；退货/收货各按现状 | 否决：平台出现第二套红冲实现，`doc_effect.reversal` 事实源被架空 |
| B 全部合并为“负向单据” | 退货、红冲、借贷项统一成 `direction=-1` 一类 | 否决：退货有实物逆流与库存事务，红冲无；合并会丢语义 |
| **C 三层分工（采纳）** | L1 类型元数据（`document_role/direction/reversal_type_id/is_default`，全 scope_bo 通用）+ L2 事实冲销（`doc_effect.reversal` + `reversal_orchestrator`）+ L3 业务形态（`document_category` 派生三类） | 采纳 |

**理由**

1. 平台已有 L2 引擎与四份 BO 声明（`shipment` / `receipt` / `transfer_order` / `inventory_adjustment`），发票未接入即为架构例外；接入成本低于长期双实现维护成本。
2. 退货必须保留 `document_category=return` 与库存反向事务，不能用 `direction=-1` + `reversal_of_*` 表达，否则财务口径与库存口径混淆（SAP 退货交货单 vs 冲销发票即两类对象）。
3. 借项/贷项是纯金额调整，无实物流动；补货是正向新供给，均不进入逆向链路。
4. `type_definitions` 是平台级单据类型表，`document_role/direction` 天然应全 scope_bo 通用；只在发票私有实现会再次形成“类型元数据两套口径”。

**影响面**：`reversal_primitives.py`（4 个原语 + 1 个创建器）、`reversal_profiles.py`（1 个 profile）、`customer_invoice.yaml`（`doc_effect`）、`customer_invoice_service.reverse`（改委托）、`doc_effect_validator`（一致性校验）；既有四份逆向声明的运行时行为不变。

**回滚**：保留旧 `reverse` 事务块在 `_legacy_reverse`（仅测试期对照），发布前删除；profile 与 YAML 声明可单独回退，数据层无新列依赖（`direction` 已在 v243）。

---

### 9.6 影响面与风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 迁移回填错误 | 全量单据类别/方向错 | 迁移幂等 + 回填前后计数对账 + `down` 脚本 |
| 历史红字分类偏差 | 报表按类别分组时红字并入贷项 | 发布说明标注；报表改用 `direction` |
| YAML 漏配冻结字段 | 可改字段回归 | 对账测试（AC-7.2） |
| 借项被误用为开票 | 应收虚增 | 权限独立 + 行来源限制 + 不回写 billed |
| 前端读不到新字段 | 列表无方向列 | 字段声明 `filterable`，前端元数据自动派生 |

### 9.7 回滚方案

- 回滚代码即可（新增字段对旧代码无影响，默认值兼容）。
- 若已产生 `SRV` 单据，回滚前需确认其状态；`down` 迁移仅在无 `SRV` 单据时删除类型与号段。

---

## 10. TBD List

| 编号 | 事项 | 状态 |
|---|---|---|
| TBD-1 | `meta/schemas/type_definition.yaml` 是否存在，不存在时新字段的 UI 元数据落在哪 | ✅ 已确认存在；4 个字段（`document_role`/`direction`/`reversal_type_id`/`is_default`）已声明，只读 + 可筛选 |
| TBD-2 | `SCR` 显示名改名是否会影响前端菜单/筛选的硬编码文案 | ✅ 已检索 `src/`，无 `SCR` / “销售贷项”硬编码 |
| TBD-3 | 借项是否需要在列表页提供独立“新建借项”入口（当前仅详情/动作） | 默认仅 action，若需要再加 |
| TBD-4 | 历史红字单据是否需要一次性报表口径说明（对财务） | ✅ 见 §11 发布说明 |
| TBD-5 | `shipment`/`receipt` 是否也改用 `type_definitions.direction` 驱动（当前用 `posting.direction_field: document_category`） | 本次只回填元数据，不改既有运行时口径；后续平台 spec 处理 |

---

## 11. 发布说明（Wave D 交付）

**交付范围**：L1 凭证身份元数据（`type_definitions` 4 列，全 `scope_bo` 通用）→ L2 发票接入 `reversal_orchestrator` → L3 `document_category` 三类语义（`reversal` / `return` / `adjustment`）。补货/正向补发不进逆向模型。

**行为变化（对外可见）**

1. 红冲（`SRV`）与贷项（`SCR`）分离：`SINV.reversal_type_id = SRV`；红冲单号前缀 `SRV-yyyymm-00001`。
2. 单据头新增 `direction` 快照（1 正向 / -1 逆向），全状态只读；行金额符号、期次生成、billed 回写均以方向/角色为准。
3. 新增借项通知单动作 `customer_invoice.create_debit_memo`（权限 `customer_invoice:customer_invoice_debit_memo`，`SDN` 类型，号段 `SDN-yyyymm-00001`）。借项不回写订单 `billed_qty/billed_amount`，不校验可开票数量上限。
4. 贷项来源仅允许 `invoice` / `debit_memo`；以贷项再开贷项 → `INVOICE_CREDIT_SOURCE_ROLE_INVALID`。
5. 已提交发票的冻结字段由 YAML `state_field_policies` 驱动；`invoice_date` 保持同月可调（跨月仍报 `INVOICE_NUMBER_PERIOD_MISMATCH`）。
6. 行来源策略由 YAML `line_source_policy` 驱动；违规 → `INVOICE_LINE_SOURCE_POLICY_VIOLATION`（红字镜像行豁免）。

**已知历史偏差（不回填、不重编号）**

- 迁移前用 `SCR` 表示红冲的历史单据：`document_category` 仍为 `credit_memo`，但 `direction = -1` 正确。**财务/报表口径请使用 `direction` 而非 `document_category`**；`document_role` 按类型统一记为 `credit_memo`。
- 不自动把历史 `SCR` 重分类为 `SRV`：缺乏可靠判别式，且重编号会破坏既有引用。

**诊断能力**

- `meta/services/customer_invoice_service.py` 提供只读 `lineage_violations(ds, invoice_id)`：行来源外键 ⇒ 对应 `doc_flow_edges` active 边（反向不强制），用于测试与历史数据巡检，不进入过账事务。

**验证**

- 回归：`python d:\filework\test.py --root D:\filework\s8-billing-worktree --port 3012 --file <路径>`，Wave D 合并回归 **633 passed / Exit 0**。
- 迁移幂等重复执行无副作用；`down` 可回滚（仅无 `SRV` 单据时删除类型/号段）。