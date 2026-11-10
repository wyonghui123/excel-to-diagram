# Spec: 销售开票价格与金额（元数据驱动 · 单一事实源）

> 版本：v1.0 ｜ 日期：2026-11-10 ｜ 状态：待评审（未开发）
> 关联：`research-fusion-billing-deep-dive-2026-11-09.md`、`spec-doc-flow-single-fact-model-2026-11-05.md`、
> `spec-enum-single-source-of-truth.md`、`spec-reversal-platform-2026-11-06.md`

---

## 0. 用户决策记录（Decision Log）

| 编号 | 决策 | 结论来源 |
|---|---|---|
| D-01 | **Q1 开票金额基数**：以「订单行净额（含抬头折扣/附加费分摊）」为发票行净额基数，单价仅作展示与重算基线；引入 `billing_pricing_mode`（对标 SAP 复制控制 A/B/C/D/G），默认 `copy_frozen_redetermine_tax`；必须有「发票净额 − 订单行净额」容差校验 | 用户认可（2026-11-10） |
| D-02 | **Q2 费用行归属**：双层模型——计算层用条件（`rate_class=freight/discount_surcharge` + 分摊基数），落库层生成 `freight/misc` 发票行并带来源条件引用 | 用户认可（2026-11-10） |
| D-03 | **Q7 范围**：Spec 一次写全，实施分 P0/P1；P0=净额基数+分摊明细+精度/舍入差+价格溯源，P1=费用行类型+条件快照+改价原因码+策略层 | 用户认可（2026-11-10） |
| D-04 | **追加约束**：方案必须符合「元数据模型驱动 + 单一事实源（YAML 唯一真源）」规范，先审视再落 Spec | 用户 2026-11-10 指令 |
| D-05 | **不新建 `rounding_profile` 实体**：精度=`currencies.decimal_places`，方向=`rounding_mode` 字典，税方向=`tax_codes.rounding`；现金舍入（MAU）/税舍入层级按 TBD-8/TBD-9 触发式评估 | 用户 2026-11-10 评审（见 §11.2） |
| D-06 | **发票税额舍入方向与订单同口径**：重算税读 `tax_codes.rounding`，不再固定 half-up | 用户 2026-11-10（对应 G10） |
| D-07 | **付款期次金额走币种精度**：过账生成的 `customer_invoice_schedules.amount` 按 `currency.decimal_places` 舍入，尾差归末期 | 用户 2026-11-10（对应 G8） |

---

## 1. 背景与目标

### 1.1 背景（现状缺陷，证据等级 C＝代码已核实）

| 编号 | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| G1 | 开票净额丢失抬头分摊：发票行只按 `qty × unit_price` 重建，未取订单行 `net_amount` | `meta/services/customer_invoice_service.py` `_build_line_from_order_line`（≈L1957） | **P0 金额虚高**：发票净额 > 订单净额 |
| G2 | 无价格溯源：发票行无 `rate_table_id / calc_result_id / source_rate_record_id / price_trace` | `meta/schemas/customer_invoice_line.yaml` 字段清单 | **P0 不可追溯**：无法解释「这个价格怎么来的」 |
| G3 | 精度硬编码：`_finalize_line`（≈L2116）固定 `round(..., 4)`；行 YAML `net_amount` 也固定 4 位 | 同上 + `customer_invoice_line.yaml` | **P0 与引擎口径不一致**：引擎按币种精度 |
| G4 | 费用无单据模型：`rate_class=freight` 可配置但无消费方；发票行类别无 `freight/misc` | `rate_type.yaml`、`type_definition.yaml` | P1 运费/杂费只能塞进物料行 |
| G5 | 改价控制弱：仅有自由文本 `price_change_reason` + 自由文本审批人 | `customer_invoice_line.yaml` | P1 无原因码字典、无阈值、无审批流 |
| G6 | 策略层缺失：`pricing_determination` 仅 `sales_order` scope；`reprice_trigger=on_invoice` 空转 | `pricing_determination.yaml`、`calc_result.yaml` | P1 无法按客户/单据类型差异化取价 |
| G7 | 已具备未打通：`PricingService.price_line` 已支持泛化宿主；`calc_result` 已支持 freeze/reprice/qty_basis | `meta/services/pricing_service.py`、`calc_result.yaml` | 机会：复用而非新建 |
| G8 | 付款期次金额固定 4 位：`_allocate_amounts` 与期次落库未按币种精度 | `customer_invoice_service.py` `_allocate_amounts`（≈L1588-1599）、期次写入（≈L1558） | **P0 期次金额出现多余小数**（JPY 等 0 位币种），且 Σ期次 ≠ gross |
| G9 | 计划期次行只写净额：`_build_line_from_schedule` 未写行分摊明细 | 同上（≈L3074-3105） | 净额正确但行分摊恒为 0，Σ行 ≠ 头（FR-002 可追溯性） |
| G10 | 中间金额固定 4 位二次舍入：红冲 / on-account 贷项 / 计划行先 `_round(...,4)` 再由 `_finalize_line` 按币种舍入 | 同上（≈L2369-2398 / L2468-2476 / L3045-3068） | 边界值偏 1 个最小单位（如 `1.004999` → 1.01，直接舍入应为 1.00） |
| G11 | 税额方向未消费：`_finalize_line` 固定 half-up，不读 `tax_codes.rounding` | 同上（`_finalize_line` ≈L2217） | 默认模式 G 重算税时与订单侧差 0.01，差异无法解释 |

### 1.2 目标

1. **金额正确**：发票行净额 = 订单行净额（含抬头调整），差异可解释且在容差内。
2. **可追溯**：任一发票金额可回放到「定价过程 → 条件记录 → 基数 → 结果快照」。
3. **可配置**：定价模式、费用行类别、改价原因、分摊基数均为元数据/数据驱动，不改代码结构。
4. **单一事实源**：每个数字只有一个权威写入口，其余为只读快照或可重建投影。
5. **精度统一**：金额精度唯一来源 = `currencies.decimal_places`。

### 1.3 涉众

| 角色 | 关注点 |
|---|---|
| 开票员 | 发票金额与订单一致、改价有据可查 |
| 财务/审计 | 金额可追溯、红冲/贷项可回放、舍入差额可解释 |
| 定价管理员 | 价目表/条件/分摊规则可配置，无需发版 |
| 实施顾问 | 客户差异通过元数据配置，不fork代码 |
| 平台研发 | 不绕过元数据直接写死枚举/精度/行类别 |

### 1.4 非目标

- 不实现税务引擎（税仍取税码快照 + 税率）。
- 不实现完整审批流引擎（阈值审批见 TBD-2）。
- 不改红冲/贷项/借项既有逆向模型（另见 `spec-reversal-platform`）。
- 不在本期实现多币种换算引擎（沿用订单汇率快照）。

---

## 2. 需求类型总览

| 类型 | 数量 | P0 | P1 | P2 |
|---|---|---|---|---|
| FR（功能需求） | 11 | 5 | 5 | 1 |
| NFR（非功能需求） | 5 | 4 | 1 | 0 |
| IF（外部接口需求） | 4 | 3 | 1 | 0 |
| TR（过渡需求） | 5 | 3 | 2 | 0 |

---

## 3. 功能需求（FR）

### FR-001 发票行净额以订单行净额为基数（P0）

**规则**
1. `source_doc_type=sales_order` 时，发票行 `net_amount` 必须取 `order_line.net_amount`（已含抬头折扣/附加费分摊），不得用 `qty × unit_price` 重算。
2. `unit_price` 降级为「展示价 + 重算基线」，其值 = `order_line.unit_price`，不得反向推导 `net_amount`。
3. `billing_basis=percent/amount` 时，仍以 `billing_base_amount × billing_percent` 计算，不走 `qty × unit_price`。
4. 保存时校验：`|invoice_line.net_amount − order_line.net_amount| ≤ tolerance`，超差拒绝并提示差异来源（价格/分摊/精度）。

**元数据落点**
- `customer_invoice_line.yaml` → `net_amount.description` 改为「含抬头调整分摊后的行净额；来源订单行净额，禁止由单价重算」。
- 容差值走 `control_parameter_def`（`domain=invoice`，`value_type=number`），不在代码常量里写死。

**验收**
- 订单：2 行 × 100，抬头折扣 20（按金额分摊 10/10）→ 发票两行净额各 90，发票净额 180（原实现为 200）。
- 单价 100、数量 2、折扣 20 → 展示单价仍 100，净额 180。

### FR-002 抬头折扣/附加费分摊明细落行（P0）

**规则**
1. 发票行新增 `header_discount_amount`（≥0）与 `header_surcharge_amount`（≥0），单位为单据币种。
2. 发票头新增 `header_discount_amount / header_surcharge_amount`，其值 = Σ 行同名字段（唯一聚合入口）。
3. 行净额恒等式：`net_amount = qty × unit_price + header_surcharge_amount − header_discount_amount`（仅作为校验式，不作为写入路径）。
4. 分摊由引擎产出并写入 `calc_result`（`level=line`，`result_semantic=price`），发票只复制结果，不自行分摊。
5. **计划期次行必须携带分摊明细**：`source_doc_type=billing_schedule` 时，行 `header_discount_amount / header_surcharge_amount` 按 `billing_percent × order_line 同名字段` 拆分（复用 `_order_line_basis` 的比例口径），尾差归最后一期；不得只写净额而把明细留空。

**元数据落点**
- `customer_invoice_line.yaml` + `customer_invoice.yaml` 字段声明；`ui_view_config.detail` 增加分组「抬头调整分摊」。
- 分摊基数枚举 `distribution_basis` 落在 `rate_record.yaml`（见 FR-006）。

**验收**
- 抬头附加费 30 按重量分摊（权重 1:2）→ 行金额 10 / 20，Σ=30。
- 手工删除分摊明细被拒（字段只读或受动作守卫）。
- 计划开票：订单行净额 900、折扣 100、附加费 0，两期 50%/50% → 两期发票行净额各 450、折扣各 50；Σ行折扣 100 = 头折扣。

### FR-003 精度与舍入差额（P0）

**规则**
1. **舍入三要素**（各有唯一真源，互不替代）：
   - **精度**：`currencies.decimal_places`（服务层查询后传入，core 层不访问数据库）；
   - **方向**：平台字典 `rounding_mode`（`none / round / ceil / floor`，`round` = half-up）；金额默认 `round`，税额按 `tax_codes.rounding`；
   - **层级**：默认**行级**（逐行算净额/税额后求和）；单据级舍入未启用，配置能力见 TBD-8。
2. 所有金额舍入统一走 `round_amount(value, decimals, mode='round')`；禁止服务内写 `round(x, 4)` 或直接 `quantize` 金额。
3. `round_amount` 只在**落库边界**调用一次；中间计算（拆分 / 换算 / 比例）保留全精度 `Decimal`，禁止先舍到固定 4 位再按币种舍入（双舍入会偏 1 个最小单位）。
4. 发票头 `rounding_diff`（单据币种，可为负），恒等式：`gross_amount = net_amount + tax_amount + rounding_diff`。
5. **付款期次金额**（`customer_invoice_schedules.amount`）同样按币种精度舍入；尾差归最后一期，保证 `Σ期次金额 == gross_amount`。
6. 行 YAML 删除固定 `decimal_places: 4` 的数值约束，改由服务层按币种判定；若平台支持声明式精度，使用 `precision_source: currency.decimal_places`（否则以文档+守卫保证）。
7. `currency.yaml` 注释已同步更新：`decimal_places` 是金额舍入精度的唯一真源，消费者为 `meta/core/rounding.py::round_amount`（与销售订单金额服务同口径）；`Extended Precision / Minimum Accountable Unit` 维持不做（触发条件见 TBD-10）。

**验收**
- 币种 JPY（0 位）：净额 100.4 → 100；行级残差 -0.4 低于最小单位，按币种精度落库后 `rounding_diff = 0`。
- 币种 USD（2 位）：净额 100.456 → 100.46；行级残差 -0.004 归 0，仅分摊尾差（≥ 最小单位）才进 `rounding_diff`。
- 税码 `rounding=ceil`、净额 100.10、税率 13% → 税额 13.02（half-up 为 13.01）；发票与订单侧一致。
- 付款期次：JPY 发票 gross 100001、3 期 40/30/30 → 40000 / 30000 / 30001，Σ=100001；除不尽时尾差归末期。
- 全库 grep 无业务服务内 `round(..., 4)` / `_round_float(..., 4)` 金额硬编码。

### FR-004 价格溯源快照（P0）

**规则**
1. 发票行新增：`calc_result_id`（引用 `calc_result`）、`source_rate_record_id`（引用命中的 `rate_record`）、`price_trace`（JSON 文本，引擎决策链）。
2. 发票头新增：`pricing_date`（定价日快照）、`billing_pricing_mode`（模式快照）。
3. `price_source` 枚举扩展为 `order / manual / pricing`；当 `price_source=pricing` 时 `calc_result_id` 必填；当 `manual` 时 `calc_result_id` 可为空但必须填 `price_change_reason`。
4. `price_trace` 只写不解析（前端只做只读展示），禁止用它反算金额。

**元数据落点**
- `customer_invoice_line.yaml`（3 字段 + 枚举扩展）、`customer_invoice.yaml`（2 字段）。
- 关联关系 `customer_invoice_line_to_calc_result`、`..._to_rate_record`（软引用，遵循 D6「不新增强制 FK」）。

**验收**
- 任一新开票行可展示：价目表、条件记录、基数、费率、定价过程、定价日。
- 手工改价行：`price_trace` 记录「原价 → 新价 → 原因码 → 操作人」。

### FR-005 定价模式 `billing_pricing_mode`（P0）

**规则**
1. 值域（枚举 `billing_pricing_mode`，`category=business`，`mutability=editable`）：

| 值 | 标签 | 对标 SAP 复制控制 | 行为 |
|---|---|---|---|
| `copy_frozen` | 原样复制 | D | 复制订单净额与税，不重算 |
| `copy_scale_update` | 复制并按阶梯更新 | A | 复制，按阶梯/数量更新 |
| `copy_reprice_all` | 全部重新取价 | B | 重新执行定价过程 |
| `copy_manual_reprice_rest` | 复制手工价，其余重算 | C | 手工价冻结，其余重算 |
| `copy_frozen_redetermine_tax` | 复制净额，重算税 | G | **默认**；净额冻结，税按开票税码重算 |
| `legacy` | 历史数据 | — | 仅回填用，`is_system=true`，不可手工选择 |

2. 配置真源：`control_parameter_def.code=billing_pricing_mode`（`value_type=enum`，`enum_type_id` → 上表枚举，`default_value=copy_frozen_redetermine_tax`），按 `control_parameter_values.document_type_id`（发票类型）取值；组织级可覆盖（`specificity_rank`）。
3. 实例快照：`customer_invoices.billing_pricing_mode` 在建单时解析写入，后续只读；历史发票回填 `legacy`。
4. 三处一致：枚举字典（值域）/ 控制参数（配置）/ 单据字段（快照）。禁止在前端或服务内写字符串常量。

**验收**
- 发票类型 SINV 配置为 G → 新建发票 `billing_pricing_mode=copy_frozen_redetermine_tax`。
- 改配置不影响已建发票（快照不可变）。
- 未配置时取 `default_value`，不报错。

### FR-006 费用行模型：双层（P1）

**规则**
1. **计算层**：费用是条件——`rate_type.rate_class ∈ {freight, discount_surcharge}`，通过 `rate_record` 命中并产出 `calc_result`（`level=header|line`）。
2. **落库层**：发票行通过 `line_type_id` 指向新增行类型（`FRT` 运费 / `MSC` 杂费），行类别 `line_category ∈ {freight, misc}`。
3. 费用行必须带 `source_rate_record_id`（来源条件）与 `calc_result_id`；`item_id` 可为空；税率独立（`tax_code_id` 必填）。
4. 抬头费用分摊到行时，写行 `header_surcharge_amount`（或 `header_discount_amount`），Σ = 抬头条件金额。
5. 分摊基数新增 `rate_record.distribution_basis ∈ {none, weight, volume, amount, quantity}`：`none`=不分摊（只生成抬头级费用行），其余按行属性归一化权重。

**元数据落点**
- 写面唯一真源：`type_definition.yaml` 的 `line_category.enum_values` 追加 `freight` / `misc`。
- 只读视图镜像：`line_type.yaml` 的 `category.enum_values` 同步（由一致性测试锁定，禁止独立演化）。
- 种子数据：`type_definitions(scope_bo=customer_invoice, level=line)` 新增 `FRT` / `MSC`（迁移 v245）。
- 计算层：`rate_record.yaml` 新增 `distribution_basis`。

**验收**
- 运费条件（抬头级，按重量分摊）→ 生成 1 条 `FRT` 行或分摊到各物料行的 `header_surcharge_amount`（由配置决定，二选一），两种模式金额守恒。
- 新增第 3 种费用行（如保险 `INS`）只需配置，不改代码。

### FR-007 费用分摊守恒与舍入（P1）

**规则**
1. 分摊后 Σ 行分摊额 = 抬头条件金额（尾差进最大权重行，或进 `rounding_diff`，二选一但必须配置固定）。
2. 分摊权重全部为 0 时拒绝分摊并报错，不静默均摊。
3. 分摊明细写入 `calc_result.fact_snapshot`，发票侧只读。

**验收**
- 3 行权重 1:1:1，金额 100 → 33.34/33.33/33.33（尾差策略 A）或 33.33×3 + `rounding_diff=0.01`（策略 B）。

### FR-008 改价控制：原因码 + 权限 + 阈值（P1）

**规则**
1. 新增枚举 `price_override_reason`（`category=business`，`mutability=editable`），初始值：`promotion` 促销 / `contract` 合同价 / `compensation` 补偿 / `freight_adjust` 运费调整 / `other` 其他。
2. 发票行 `price_change_reason` 语义从「自由文本」改为「原因码引用 + 备注」：新增 `price_override_reason_code`（枚举引用），`price_change_reason` 保留为备注文本。
3. 新增权限 `customer_invoice:customer_invoice_override_price`（双段式），未授权不得改价。
4. 偏差超过 `control_parameter_def(price_override_tolerance_pct)` 时，需 `price_override_approval` 动作（P1 先做权限 + 留痕，审批流见 TBD-2）。

**验收**
- 未授权用户改价被拒（403 + 权限码）。
- 改价保存后 `price_trace` 含原因码 + 审批人 + 原/新价。

### FR-009 定价策略层（P1 → P2 拆分）

**规则**
1. `pricing_determination` 扩展支持 `scope_bo=customer_invoice`（或新增 `pricing_profile` 统一宿主），键组合沿用 SAP 5 键：销售组织 + 分销渠道 + 产品组 + 单据定价过程 + 客户定价过程。
2. 发票取价时按策略定位 `process_code / rate_table_id`，不硬编码价目表。
3. 无匹配策略时回落到订单已冻结的 `calc_result`（FR-005 的 `copy_frozen`）。

**验收**
- 同一客户两种发票类型命中不同价目表，仅配置差异。
- 无策略时不报错、走冻结回放。

### FR-010 重定价触发 `on_invoice`（P1）

**规则**
1. `calc_result.reprice_trigger=on_invoice` 在发票保存（草稿态）时执行，等价 SAP B 模式。
2. `billing_pricing_mode` 与 `reprice_trigger` 冲突时，以 `billing_pricing_mode` 为准并在 `price_trace` 记录「忽略重定价，原因=模式 D/G」。
3. 已过账发票禁止重定价（`freeze_policy=freeze` 生效）。

**验收**
- 模式 B + `on_invoice` → 重取价。
- 模式 G + `on_invoice` → 只重算税，净额不变，trace 有记录。

### FR-011 策略/费用行的对账断言（P1）

**规则**
1. 提供只读一致性检查（服务或诊断脚本）：
   - `Σ line.net_amount == header.net_amount`
   - `header.net_amount + header.tax_amount + header.rounding_diff == header.gross_amount`
   - `Σ line.header_discount_amount == header.header_discount_amount`
   - 每个费用行必有 `source_rate_record_id`
   - `price_source=pricing` ⇒ `calc_result_id` 非空
2. 断言失败只告警不阻断过账（除金额恒等式，阻断）。

**验收**
- 人为篡改行净额 → 保存被拒并给出恒等式差异。

---

## 4. 非功能需求（NFR）

### NFR-001 单一事实源（P0）
每条需求满足项目「单一事实模型五判据」：唯一写入口 / 稳定身份 / 不可变 / 不重复计算 / 边界原子。映射见 §7.4 与 §9.9。

### NFR-002 可观测性（P0）
`price_trace` 每次取价/重定价/改价必写；含 `process_code`、`rate_record_id`、`base`、`rate`、`amount`、`currency`、`pricing_date`、`decision`（hit/exclusive/skip/reason）。

### NFR-003 迁移幂等与可回滚（P0）
沿用 `v243__customer_invoice_document_role.py` 范式：列先查后加、种子先查后插、`UPDATE` 幂等、索引 `IF NOT EXISTS`、权限 `INSERT OR IGNORE`、菜单 JSON 按值合并、重复执行打印 `[SKIP]`；回滚脚本对称。

### NFR-004 性能（P1）
开票取价按行批量解析策略（一次查询策略 + 价目表），禁止 N+1；1000 行开票取价 P95 ≤ 2s（不含税）。

### NFR-005 向后兼容（P0）
存量发票不重算、不改金额；新字段可空或带 `legacy` 值；旧接口返回结构只增不改。

---

## 5. 外部接口需求（IF）

### IF-001 定价服务泛化宿主（P0）
`PricingService.price_line(process_code, rate_table_id, slot_keys, base, *, sequence_code, document_type, document_id, document_line_id, level, resolution, measure, valid_on, persist, result_code)` 复用为发票取价入口；新增薄适配层 `InvoicePricingAdapter`，不复制引擎逻辑。

### IF-002 元数据解析契约（P0）
字段/枚举/UI 配置全部通过既有 `enum_resolver` 与 schema 加载器解析；**禁止**服务内出现 `'freight'`、`'copy_frozen'` 等字面量分支；确需分支时用 `rate_class` / `line_category` 的解析结果比较。

### IF-003 迁移接口（P0）
`python -m meta.migrations.v244__... upgrade|rollback`（与现有迁移入口一致）；迁移后必须能通过 `python scripts/lint_tests.py` 与元模型声明守卫。

### IF-004 前端契约（P1）
新增列/表单/详情全部由 `ui_view_config` 驱动；费用行新增按钮由 `type_definitions` 可用行类型决定；改价按钮由 `ui_actions` + 权限码控制。

---

## 6. 过渡需求（TR）

### TR-001 存量数据不重算（P0）
已存在发票：`net_amount` 原值保留，`billing_pricing_mode=legacy`，`rounding_diff=0`；不回填 `header_discount_amount`（无法可靠重建），列表以 `—` 展示。

### TR-002 草稿态自动取价（P0）
自动取价仅草稿态（沿用 `sales_order_pricing_service` 的 `_DRAFT` 约束）；已提交/已过账只读。

### TR-003 精度消费者启用（P0）
`currency.decimal_places` 从「声明无消费者」转为「唯一精度消费者」，同步更新 `currency.yaml` 注释与 `currency_rate.yaml` 引用说明。

### TR-004 权限与菜单种子（P0/P1）
v244 增 `customer_invoice:customer_invoice_override_price`；v245 增 `customer_invoice:customer_invoice_fee_line`；均授予 `admin`/`default`，并挂 `customer_invoice-list` 菜单（按值合并）。

### TR-005 分阶段上线（P0）
M1（P0 金额与溯源）→ M2（P1 费用行）→ M3（P2 策略层/审批）；每阶段可独立回滚。

---

## 7. 约束与假设

### 7.1 技术约束
- SQLite + Flask + Waitress；软引用不新增强制 FK（沿用 D6）。
- 前端 Vue 3 + Element Plus，UI 由 `ui_view_config` 渲染。
- 测试唯一入口 `python d:\filework\test.py`；禁 pytest 直跑。
- 不直改 `meta/architecture.db`；DB 变更走迁移。

### 7.2 业务约束
- 发票金额必须可审计、可回放；已过账金额不可变。
- 客户差异通过元数据配置，不 fork 代码。
- 费用行税率独立于物料行。

### 7.3 假设
- 订单行 `net_amount` 已包含抬头折扣/附加费（现状成立）。
- 订单已冻结 `calc_result` 可被发票引用（`document_type/document_id/document_line_id` 泛化已支持）。
- 币种主数据 `decimal_places` 已维护且可信。

### 7.4 元数据驱动与单一事实源合规审视

#### 7.4.1 审视口径

采用项目既有判据：
1. **单一事实模型五判据**（唯一写入口 / 稳定身份 / 不可变 / 不重复计算 / 边界原子）。
2. **YAML 为真源**：字段、枚举、UI、权限、动作声明在 `meta/schemas/*.yaml`；跨 BO 共享枚举在 `enum_types` 数据。
3. **写面收敛**：`type_definitions` 是行类型唯一写面，`line_type` 只是只读视图（`auto_crud: false`）。
4. **声明即事实**：YAML 声明的字段必须有消费方，否则视为漂移。

#### 7.4.2 逐项审视结论

| # | 变更项 | 唯一真源落点 | 现状 | 结论 |
|---|---|---|---|---|
| 1 | 行净额基数语义 | `customer_invoice_line.yaml::net_amount.description` + 服务实现 | description 写死 `ROUND(qty × unit_price)` | ✅ 可落（改描述 + 改服务） |
| 2 | 抬头分摊明细 | 行/头 YAML 新字段 `header_discount_amount` / `header_surcharge_amount` | 不存在 | ✅ 需新增（P0） |
| 3 | 金额精度 | `currency.yaml::decimal_places` | 已声明且已由销售订单金额服务消费；`meta/core/rounding.py` 已有 `normalize_decimals` / `round_by_mode` | ⚠️ 复用扩展：补 `round_amount(value, decimals)` 统一入口，同步 `currency.yaml` 注释写明消费者 |
| 4 | 舍入差额 | `customer_invoice.yaml::rounding_diff` | 不存在 | ✅ 需新增（P0） |
| 5 | 定价模式 | 枚举 `enum_types.billing_pricing_mode` + `control_parameter_def/value`（类型级） + `customer_invoices.billing_pricing_mode`（实例快照） | 不存在 | ✅ 三层一致（字典/配置/快照） |
| 6 | 价格溯源 | 行 `calc_result_id` / `source_rate_record_id` / `price_trace` + 头 `pricing_date` | 不存在 | ✅ 需新增（P0） |
| 7 | 费用行类别 | `type_definition.yaml::line_category.enum_values`（写面） + `type_definitions` 种子 + `line_type.yaml` 只读镜像 | 枚举在 `type_definition.yaml` 与 `line_type.yaml` **重复声明**，且无 `freight/misc` | ⚠️ 同步改两处 + 一致性测试锁定，禁止独立演化 |
| 8 | 费用分摊规则 | `rate_record.yaml::distribution_basis`（新增） | 只有 `allocation_weight`，语义 = 候选加权累加（第四消解范式） | ⚠️ **禁止复用**同名，必须新字段，否则一列两义 |
| 9 | 改价原因码 | `enum_types.price_override_reason`（`category=business`, `mutability=editable`） | 仅自由文本 `price_change_reason` | ✅ 需新增（P1） |
| 10 | 权限 | 迁移种子 `customer_invoice:customer_invoice_override_price` 等 | 无 | ✅ 双段式命名，复用 v243 helpers |
| 11 | 前端展示 | `ui_view_config.list/form/detail` + `filter` | 无新列配置 | ✅ 只改 YAML，不改前端硬编码 |
| 12 | 定价策略层 | `pricing_determination` scope 扩展 | 仅 `sales_order` | ⚠️ 平台级改动，P2 另立 spec，避免本期膨胀 |
| 13 | 舍入三要素 | 精度=`currency.yaml::decimal_places`；方向=字典 `rounding_mode`（`rounding.py` 静态镜像，测试锁定）；税方向=`tax_code.yaml::rounding` | 三者均已存在；发票仅消费精度 | ⚠️ 补税方向消费者（D-06），层级默认行级（TBD-8），**不新建 `rounding_profile` 实体**（§11.2） |
| 14 | 舍入档（rounding profile） | 不建表；触发条件与最小 schema 记入 TBD-9 | `currency.yaml` 已裁定 MAU / Extended Precision 不做 | ✅ 裁决：P2 触发式，避免无消费者字段（重演 `decimal_places` 教训） |

#### 7.4.3 语义重叠裁决（冲突点）

| 重叠项 | 冲突描述 | 裁决（唯一真源 → 引用方） |
|---|---|---|
| `rate_class` vs `line_category` | 前者是「条件类型语义」（计算层），后者是「单据行性质」（落库层） | `rate_type.rate_class` 为计算层唯一真源；发票行通过 `source_rate_record_id` 引用，**不复制字符串**；`line_category` 只表达行性质 |
| `billing_basis` vs `calc_result.base_source` | 前者是发票行「计费方式」（数量/百分比/金额），后者是引擎「基数来源」 | `calc_result.base_source` 为权威；`billing_basis` 仅决定税基与展示，不得独立算钱；保存时校验一致 |
| `price_source` vs `calc_result.rate_source` | 都表达价格从哪来 | `calc_result.rate_source` 为权威；`price_source` 降级为 UI 来源标记，`pricing` 时强制 `calc_result_id` 非空 |
| `net_amount`（订单行）vs `net_amount`（发票行） | 同名不同口径 | 订单行是**源事实**；发票行是**派生快照**，只复制不反算；以恒等式与容差校验锁死 |
| `allocation_weight` vs 分摊权重 | 同名不同义 | 保留 `allocation_weight`（候选加权）；新增 `distribution_basis` 表达抬头费用分摊；文档与字段 description 必须写明差别 |

#### 7.4.4 审视发现的不合规风险（必须在实施时消除）

1. **硬编码风险**：`customer_invoice_service.py` 内不得出现 `'freight'` / `'misc'` / `'copy_frozen'` 字符串分支，必须走枚举解析。
2. **精度硬编码**：`_finalize_line` 的 `round(..., 4)` 必须删除，改调 `round_amount()`。
3. **枚举双写**：`line_category` 两处声明必须由一致性测试（YAML enum vs `type_definition.yaml`）锁定。
4. **声明无消费**：`decimal_places` 必须在本次产生真实消费者，否则不得在新 Spec 中宣称「已支持币种精度」。
5. **快照与配置混淆**：`billing_pricing_mode` 的配置（`control_parameter_values`）可改，实例（`customer_invoices`）不可改；禁止前端直接编辑实例字段。

---

## 8. 优先级与里程碑

| 优先级 | 内容 | 交付物 |
|---|---|---|
| **P0** | FR-001 / FR-002 / FR-003 / FR-004 / FR-005；NFR-001/002/003/005；TR-001/002/003 | v244 迁移 + 服务改造 + schema + 测试 |
| **P1** | FR-006 / FR-007 / FR-008 / FR-010 / FR-011；NFR-004；TR-004 | v245 迁移 + 费用行 + 改价控制 |
| **P2** | FR-009 策略层；`hit_policy=best`（TBD-4） | 另立 spec |

| 里程碑 | 范围 | 验收 |
|---|---|---|
| M1 | P0 金额/精度/溯源 | 发票净额=订单净额；JPY/USD 精度用例通过；任一金额可溯源 |
| M2 | P1 费用行 | 运费/杂费成行且分摊守恒；改价有原因码与权限 |
| M3 | P2 策略层 | 按客户/类型命中不同价目表，仅配置差异 |

---

## 9. 变更/设计方案（RFC）

### 9.1 As-Is 分析

```
订单行 (net_amount 含抬头分摊)
   │  ✗ 只复制 unit_price + qty
   ▼
发票行 net_amount = ROUND(qty × unit_price, 4)   ← 金额虚高 + 精度错
   │  ✗ 无 calc_result / rate_record 引用
   ▼
发票头 net_amount = Σ 行（可重算）              ← 无 rounding_diff
```

- 引擎侧：`pricing_service.price_line` 已支持泛化宿主，但**无发票调用方**。
- `calc_result` 已具备 `freeze_policy / reprice_trigger / qty_basis / fact_snapshot`，能力闲置。
- `adjustment` 模型无消费方；`rate_class=freight` 无单据落点。

### 9.2 目标态

```
定价过程/价目表/条件 (rate_table + rate_record)
        │  price_line(document_type=customer_invoice, ...)
        ▼
   calc_result（不可变快照：rate/base/amount/fact_snapshot）
        │  复制（copy_frozen / G / B / C / A/D）
        ▼
发票行（net_amount 权威 + header_* 分摊 + calc_result_id + price_trace）
        │  Σ（唯一聚合）
        ▼
发票头（net_amount / tax_amount / rounding_diff / gross_amount / billing_pricing_mode 快照）
```

职责边界：
- **引擎**：算钱、分摊、写 `calc_result`。
- **发票服务**：复制/校验/落库，不重算金额。
- **前端**：读 `ui_view_config` 展示，不做金额计算。

### 9.3 详细设计

#### 9.3.1 Schema 变更清单

**`meta/schemas/customer_invoice_line.yaml`**

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `header_discount_amount` | number | 否 | 0 | 抬头折扣分摊到本行（单据币种） |
| `header_surcharge_amount` | number | 否 | 0 | 抬头附加费分摊到本行（单据币种） |
| `calc_result_id` | integer | 否 | — | 定价结果快照引用（软引用） |
| `source_rate_record_id` | integer | 否 | — | 命中的条件记录引用（软引用） |
| `price_trace` | string(text) | 否 | — | 引擎决策链 JSON（只写不解析） |
| `price_override_reason_code` | string | 否 | — | 改价原因码（枚举引用） |

同时：
- `net_amount.description` 改为「含抬头调整分摊后的行净额；来源订单行净额，禁止由单价重算」。
- `net_amount.constraints[].decimal_places: 4` 删除，改由币种精度执行。
- `price_source.enum_values` 追加 `pricing`（标签「定价引擎」）。
- `ui_view_config.detail` 增加「价格溯源」分组（`calc_result_id / source_rate_record_id / pricing_date / price_trace`）。
- `ui_view_config.list` 增加 `price_source`（badge）、`header_surcharge_amount`（默认隐藏）。

**`meta/schemas/customer_invoice.yaml`**

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `billing_pricing_mode` | string | 否 | `legacy`（历史）/ 新单由控制参数注入 | 定价模式快照 |
| `pricing_date` | date | 否 | 发票日期 | 定价日快照 |
| `rounding_diff` | number | 否 | 0 | 舍入差额（单据币种） |
| `header_discount_amount` | number | 否 | 0 | Σ 行折扣分摊 |
| `header_surcharge_amount` | number | 否 | 0 | Σ 行附加费分摊 |

同时：
- `ui_view_config.list` 增加 `billing_pricing_mode`（badge）。
- `ui_view_config.detail` 增加「金额构成」分组（`net/tax/rounding_diff/gross` + 抬头调整）。

**`meta/schemas/rate_record.yaml`**

| 字段 | 类型 | 说明 |
|---|---|---|
| `distribution_basis` | string(enum) | `none / weight / volume / amount / quantity`，默认 `none`；仅抬头级条件用于向行分摊 |

**`meta/schemas/type_definition.yaml`**

- `line_category.enum_values` 追加 `freight`（运费行）/ `misc`（杂费行）。
- `line_type.yaml` 的 `category.enum_values` 同步（只读镜像）。

**`meta/schemas/currency.yaml`**

- 更新注释：`decimal_places` 的唯一消费者 = `meta/core/rounding.py::round_amount`。

#### 9.3.2 枚举与字典种子（`enum_types`）

| code | category | mutability | values |
|---|---|---|---|
| `billing_pricing_mode` | business | editable | copy_frozen / copy_scale_update / copy_reprice_all / copy_manual_reprice_rest / copy_frozen_redetermine_tax / legacy(system) |
| `price_override_reason` | business | editable | promotion / contract / compensation / freight_adjust / other |

控制参数（`control_parameter_defs`）：

| code | domain | value_type | enum_type | default_value |
|---|---|---|---|---|
| `billing_pricing_mode` | billing | enum | `billing_pricing_mode` | `copy_frozen_redetermine_tax` |
| `price_override_tolerance_pct` | billing | number | — | `0` |
| `invoice_amount_tolerance` | billing | number | — | `0.01` |

#### 9.3.3 服务改造

1. **`meta/core/rounding.py`（复用扩展，P0）**
   已有 `normalize_decimals` / `round_by_mode`；本次新增 `round_amount(value, decimals=DEFAULT_AMOUNT_DECIMALS, mode='round') -> Decimal`：精度由调用方按 `currencies.decimal_places` 查询后传入，方向默认 half-up（`mode` 可传 `none/round/ceil/floor`）；作为销售发票金额舍入唯一入口（不新建重复模块）。
2. **`meta/services/customer_invoice_service.py`**
   - `_build_line_from_order_line`：`net_amount = order_line.net_amount`；`unit_price` 仅展示；写 `header_*` 分摊（来自 `calc_result`）；写 `calc_result_id / source_rate_record_id / price_trace`。
   - `_finalize_line`：删除 `round(..., 4)`，改 `round_amount(net, decimals)`；税额按 `tax_codes.rounding` 经 `round_amount(..., mode)` 计算（与订单侧同口径）；累计 `rounding_diff` 到发票头。
   - `_allocate_amounts` / 期次落库：`_round(..., 4)`、`_round_float(..., 4)` 改 `round_amount(..., decimals)`，尾差归末期。
   - `_build_line_from_schedule`：补写行 `header_discount_amount / header_surcharge_amount`（按 `billing_percent` 拆分订单行分摊明细，尾差归末期）。
   - `create_from_schedule` 期次累计校验：按行 `net_amount` 累计（原按 `unit_price`，携带分摊明细后单价 ≠ 净额，会误判超额）。
   - 红冲 / on-account 贷项行：中间金额不再固定 4 位，保留全精度后再由 `_finalize_line` 一次舍入。
   - 保存前置校验：净额恒等式 + 容差（FR-001.4）。
   - 取价入口：草稿态调用 `InvoicePricingAdapter`（内部复用 `PricingService.price_line`）。
3. **`meta/services/invoice_pricing_adapter.py`（新增，P0）**
   - 解析 `billing_pricing_mode`（控制参数 + 类型级 + 组织级 `specificity_rank`）。
   - 模式 D/G：读订单 `calc_result`（`freeze_policy=freeze`）复制；G 额外按开票税码重算税。
   - 模式 B：重新 `price_line`；模式 C：手工价冻结，其余重算；模式 A：按阶梯更新。
   - 所有分支输出统一结构（行净额、分摊、trace、引用 id），不直接写库。
4. **`meta/services/pricing_service.py`**：仅新增可选参数/返回值（`distribution` 明细），不改既有语义。
5. **`meta/services/customer_invoice_pricing_audit.py`（新增，P1）**：FR-011 一致性断言（只读）。

#### 9.3.4 迁移设计

**`v244__customer_invoice_pricing_trace.py`（P0，幂等 + 回滚）**

1. `customer_invoice_lines` 加 6 列（`header_discount_amount / header_surcharge_amount / calc_result_id / source_rate_record_id / price_trace / price_override_reason_code`）。
2. `customer_invoices` 加 5 列（`billing_pricing_mode / pricing_date / rounding_diff / header_discount_amount / header_surcharge_amount`）。
3. `rate_records` 加 `distribution_basis`（默认 `none`）。
4. 枚举种子：`billing_pricing_mode`、`price_override_reason`（先查后插）。
5. 控制参数种子：3 条 `control_parameter_defs`（先查后插）。
6. 存量回填：`billing_pricing_mode='legacy'`、`rounding_diff=0`、`pricing_date=invoice_date`。
7. 权限：`customer_invoice:customer_invoice_override_price`（INSERT OR IGNORE + 授权 admin/default）。
8. 菜单：`customer_invoice-list` 的 `bo_bindings/required_permissions` 按值合并。
9. 回滚：删权限/授权/菜单项 → 删种子（无业务引用时）→ 尽力 DROP 列（SQLite 3.35+）；不删业务数据。

**`v245__customer_invoice_fee_line_types.py`（P1）**

1. `line_category` 枚举扩展（YAML 同步 + 若 DB 有检查约束则迁移重建）。
2. `type_definitions` 种子：`FRT`（运费行）、`MSC`（杂费行），`scope_bo=customer_invoice`、`level=line`、`status=active`。
3. 权限：`customer_invoice:customer_invoice_fee_line`。
4. 回滚：无业务引用时删类型；否则置 `inactive`。

#### 9.3.5 前端设计（P1）

- 全部通过 `ui_view_config` 渲染，无新增硬编码列。
- 改价弹窗：原因码下拉（枚举加载）、备注、原/新价对比、权限控制按钮。
- 溯源抽屉：只读展示 `price_trace`（键值表），不参与计算。

### 9.4 备选方案对比

| 方案 | 描述 | 优点 | 缺点 | 裁决 |
|---|---|---|---|---|
| A 发票自定价 | 发票完全重新取价 | 与订单解耦 | 与订单金额不一致，客户对账困难 | 否 |
| B 复制订单净额 | 只复制，不重算税 | 最简单 | 税率变化无法反映（G 场景刚需） | 否 |
| C 双轨（本方案） | 净额冻结 + 可配置重算（默认 G） | 金额一致 + 税可重算 + 模式可配 | 需 `billing_pricing_mode` 三层一致 | **采用** |

### 9.5 实施顺序

1. `rounding.py` 扩展 `round_amount(value, decimals, mode='round')` + 单元测试（P0 前置，复用既有模块）。
2. v244 迁移 + 迁移幂等/回滚测试。
3. schema 字段 + 枚举/控制参数 + `lint_tests` / 声明守卫。
4. 发票服务改造（来源净额 + 溯源 + 税方向 + 期次精度 + 计划分摊明细 + 中间精度）+ 适配层 + 恒等式校验。
5. P0 回归（订单→开票金额、精度、溯源、税码 `ceil` 用例、JPY 期次）。
6. P1：v245 费用行 + 改价控制 + 对账断言。

### 9.6 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 存量发票金额口径变化 | 高 | 不重算，`legacy` 标记，回滚脚本保留原值 |
| 枚举双写漂移（`line_category`） | 中 | 一致性测试锁定两处 enum |
| 分摊尾差引发对账失败 | 中 | 固定尾差策略 + `rounding_diff` 单列 |
| `billing_pricing_mode` 配置误改影响新单 | 中 | 实例快照不可变 + 审计日志 |
| 精度改造影响其他金额模块 | 中 | `round_amount` 先只接入发票/定价，其他模块逐步 |

### 9.7 测试策略

- 单元：`round_amount`（0/2/3 位币种 × `none/round/ceil/floor`）、分摊守恒、模式 A/B/C/D/G 行为矩阵、双舍入边界（`1.004999`）。
- 集成：订单→开票净额一致（含抬头折扣/附加费）、`price_source` 与 `calc_result_id` 约束、过账后禁止重定价、付款期次精度与尾差、计划行分摊明细守恒。
- 迁移：重复执行 `[SKIP]`、回滚后列/种子消失、业务数据保留。
- 元数据：YAML 字段有消费方、枚举两处一致、`python scripts/lint_tests.py` 通过。
- 运行入口：`python d:\filework\test.py --single <path>`（禁 pytest 直跑）。

### 9.8 回滚方案

- 代码回滚：适配层与 schema 读取均向后兼容（新字段可空）。
- 数据回滚：v244/v245 `rollback` 对称执行；已产生的发票数据不删除，仅移除新增列与种子。
- 配置回滚：控制参数改回默认；枚举 `mutability` 保持 editable，可停用值但不删被引用值。

### 9.9 单一事实源落地检查清单（DoD）

- [ ] 每个新增字段都在 `meta/schemas/*.yaml` 声明，且服务/Grep 证明有唯一消费方。
- [ ] 每个新增枚举值都在 `enum_values` 或 `enum_types`，代码中无字面量分支。
- [ ] `line_category` 两处声明由一致性测试锁定。
- [ ] `distribution_basis` 与 `allocation_weight` 语义在 description 中明确区分。
- [ ] 金额恒等式与容差断言可执行（非注释）。
- [ ] 迁移幂等（连跑两次无报错、第二次全 `[SKIP]`）且回滚可验证。
- [ ] 权限双段式 + 菜单按值合并。
- [ ] `price_trace` 只写不解析。
- [ ] 发票税额消费 `tax_codes.rounding`，与订单侧同口径（`ceil/floor` 用例可执行）。
- [ ] 付款期次金额、红冲/贷项/计划行中间金额均无固定 4 位硬编码（grep 可验证）。
- [ ] 不新增 `rounding_profile` 实体；若触发 TBD-9，旧字段必须同批迁移为引用。

---

## 10. TBD List

| 编号 | 问题 | 影响 | 建议 | 状态 |
|---|---|---|---|---|
| TBD-1 | 费用行是否允许「无来源手工新增」？ | FR-006 | 默认禁止；确需时加 `manual` 来源并强制原因码 | 待业务确认 |
| TBD-2 | 改价超阈值审批由谁承载？ | FR-008 | 本期只做权限+留痕；审批流复用平台审批（另立 spec） | 待确认 |
| TBD-3 | 舍入算法是否需元数据化（half-up / banker's）？ | FR-003 | **已裁决（D-05 / §11.2）**：不建 profile；方向用 `rounding_mode` 字典，精度用币种，税方向用税码；仅新增算法（half-even 等）才扩字典值 | 已裁决 |
| TBD-4 | `hit_policy=best` 的判定准则与「条件排斥组」模型？ | FR-009/P2 | 建议加 `best_criterion(lowest/highest)` + 排斥组；本期不实施 | 待确认 |
| TBD-5 | 策略层（Pricing Profile/Segment）宿主 BO？ | FR-009 | 扩展 `pricing_determination` scope 还是新增 `pricing_profile`，P2 决策 | 待确认 |
| TBD-6 | 抬头分摊金额用单据币种还是订单币种？ | FR-002 | 建议单据币种 + 汇率快照，差额进 `rounding_diff` | 待确认 |
| TBD-7 | 净额容差按绝对值还是百分比？ | FR-001 | 建议两者并存（`invoice_amount_tolerance` + `price_override_tolerance_pct`） | 待确认 |
| TBD-8 | 发票税/净额舍入**层级**：行级（逐行算完再求和）还是单据级（汇总后一次舍入）？ | FR-003 规则 1 | **本期固定行级**（与订单/引擎同口径，零回归）；单据级需新增「层级」配置位，属 TBD-9 的 profile 触发条件之一。触发信号：出现「按行舍入与按单舍入导致总税额差 ≥ 1 个最小单位、且客户合同要求按单据级」的实际单据 | 本期不做（行级） |
| TBD-9 | `rounding_profile`（舍入档）何时建？最小 schema 是什么？ | FR-003 / §7.4.2 | **P2 触发式**：只有当「方向 + 精度 + 单位（MAU）+ 层级」四要素出现**同币种/同税制内多套并存**且无法用现有字典表达时才建；最小 schema 见 §11.2.5（含旧字段迁移要求，禁止双真源） | 已裁决（§11.2） |
| TBD-10 | 是否支持 `Extended Precision`（扩展精度）与 `Minimum Accountable Unit`（MAU，现金舍入单位）？ | FR-003 规则 7 | **本期不做**。当前无计算引擎消费者（发票/订单均按 `decimal_places` 一次性舍入，无「记账精度 vs 现金支付精度」双精度场景）。触发信号：出现「发票/台账 2 位、实际收付按 0.05 进位」的币种法规要求（如 CHF/CAD 现金舍入）时，按 TBD-9 同批评估 | 本期不做 |

---

## 11. 附：服务层 billing 覆盖审查与舍入档裁决

> 本节记录 2026-11-10 两轮分析结论，是 D-05/D-06/D-07 与 G8-G11 的推导依据。
> 目的是让后续维护者不必重新研究 Fusion/SAP，就能理解「为什么只加消费者、不建新表」。

### 11.1 服务层 billing 覆盖审查（代码已核实）

**结论：主链路已覆盖，缺口集中在「金额精度/方向/分摊明细」三处，不涉及链路结构。**

| 链路环节 | 服务 / 函数 | 是否覆盖 Spec 约束 | 结论 |
|---|---|---|---|
| 建单入口（手工 / 由订单 / 由计划 / 红冲 / 贷项） | `prepare_header` → `_finalize_line` → `_recalc_impl` | 五条建单路径**全部**经过统一收口 | ✅ 结构无需改 |
| 来源净额取值 | `_build_line_from_order_line` / `_build_line_from_schedule` | 订单路径已按 `net_amount`（P0-1~P0-4 已实施） | ✅ |
| 计划期次行分摊明细 | `_build_line_from_schedule`（≈L3074-3105） | 只写净额，未写 `header_discount_amount / header_surcharge_amount` | ❌ **G9** |
| 行最终金额舍入 | `_finalize_line`（≈L2217） | 净额按币种精度 ✅；税额固定 half-up（未读 `tax_codes.rounding`） | ⚠️ **G11**（D-06） |
| 付款期次金额 | `_allocate_amounts`（≈L1588-1599）+ 期次写入（≈L1558） | 固定 `_round(..., 4)` / `_round_float(..., 4)` | ❌ **G8**（P0，D-07） |
| 红冲 / on-account 贷项 / 计划行中间金额 | ≈L2369-2398 / L2468-2476 / L3045-3068 | 先固定 4 位，再由 `_finalize_line` 按币种二次舍入 | ❌ **G10**（双舍入） |
| 重算（改价 / 数量变更） | `_recalc_impl` | 不覆盖来源溯源字段（P0-4 已实施） | ✅ |
| 定价模式解析 | `invoice_pricing_adapter.py`（P0-5 已实施） | 类型级控制参数 + 单据快照两层 | ✅ |
| 费用行 | `billing_plan_service` / `billing_plan_actions` / `customer_invoice_actions` / `payment_term_schedule_service` | 均无金额逻辑：`billing_plan` 只写 `billing_percent`（`PERCENT_PLACES=4`）与 `billed_amount=0` | ✅ 与 FR-006/007 不冲突 |
| 税率与税方向 | `sales_order_amount_service`（参照实现，≈L60-80） | 读 `tax_codes.rounding`（`is_valid_rounding_mode` / `resolve_rounding_mode`） | ✅ 订单侧已达标，发票侧需对齐 |

**排版说明**：`billing` 域不存在「另一套金额引擎」，所有金额都收敛在 `customer_invoice_service` 的 `_finalize_line`；因此修复点只有 4 个，且均为**局部替换**（不改调用链、不改表结构）。

### 11.2 舍入档（rounding profile）裁决

#### 11.2.1 对标事实

**Oracle Fusion**：舍入不是单一字段，而是四元组：

| 要素 | Fusion 载体 | 作用域 |
|---|---|---|
| 精度（Precision） | `FND_CURRENCIES.PRECISION` | 币种 |
| 扩展精度（Extended Precision） | 币种扩展属性 | 币种（计算/展示分离） |
| 最小可记账单位（MAU） | 币种/币种组合 | 币种（现金舍入） |
| 方向 | 税制 `Rounding Rule`（Nearest / Up / Down）+ `Rounding Factor` | 税制、价目表 `Round To` |

即 Fusion 的「profile」本质是**按作用域拆开的三张配置表**，不是一张统一档位表。

**SAP**：金额侧只有两件——条件类型 `Rounding rule`（Standard / Always up / Always down）+ 公司代码×币种舍入单位（T001R）；`Rounding Profile`（阈值 + 舍入值阶梯）在 SAP 中**仅用于数量语义**（如按包装单位取整），不用于金额。SAP 的金额尾差走 `DIFF` 条件类型单独成行。

#### 11.2.2 本项目现状映射

| 要素 | 本项目唯一真源 | 消费者 |
|---|---|---|
| 精度 | `currencies.decimal_places` | `round_amount(value, decimals)` → 订单金额服务 / 发票服务 |
| 方向 | 平台字典 `rounding_mode`（`none/round/ceil/floor`），`meta/core/rounding.py` 为静态镜像（测试锁定一致） | 分摊 `/` 定价取整 `/` 金额服务 |
| 税方向 | `tax_codes.rounding`（引用 `rounding_mode` 字典） | `sales_order_amount_service`（发票待补，D-06） |
| 层级 | 无配置位，代码固定行级 | — （TBD-8） |
| MAU / 扩展精度 | 无字段，`currency.yaml` 已注明「本期不做」 | — （TBD-10） |
| 尾差 | 发票头 `rounding_diff` | 发票（FR-003 规则 4） |

**关键事实**：全库 `rounding` 字段共 5 处业务对象（`allocation_rule` / `allocation_result` / `rate_type` / `pricing_period` / `tax_code`），语义均为「方向」；没有任何表存「档位/阶梯」。

#### 11.2.3 单一事实源五判据评估

| 判据 | 新建 `rounding_profile` 表的后果 |
|---|---|
| ① 唯一写入口 | ❌ profile 会同时持有方向/精度，与 `rounding_mode` + `decimal_places` 形成**三真源**；除非同批删除旧字段（破坏 5 处 BO 引用） |
| ② 稳定身份 | ⚠️ profile 是「组合命名」，同一 (方向, 精度) 可被多条 profile 重复表达 → 命名即歧义 |
| ③ 不可变 | ⚠️ 合同口径变更时 profile 必改，历史单据若只存 profile_id 则金额不可回放；须额外快照四要素 |
| ④ 不重复计算 | ❌ 发票仍需逐次读 profile → 解析出四要素，等于多一跳，无收益 |
| ⑤ 边界原子 | ✅ 若做成「币种级覆盖表」（profile 挂在币种上）可原子替换；但当前币种精度已够用，替换无业务驱动力 |

**结论**：现在建 profile = 用一个聚合名把三个已有真源复制一份（第二真源），重演 `decimal_places` 曾「有字段无消费者」的教训（见 `currency.yaml` 注释与 SPEC-1 修正）。

#### 11.2.4 方案裁决

| 方案 | 内容 | 判定 |
|---|---|---|
| **α（采纳）** | 不建实体：精度=币种、方向=字典、税方向=税码；本期只补**已有元数据的消费者**（G8-G11） | ✅ 本期执行 |
| β（触发式） | 出现「同币种多档位/层级」硬需求时，建 `rounding_profile`（见 §11.2.5），并**同批**把 5 处 BO 的 `rounding` 与币种精度改为引用 profile | ⏸ 挂 TBD-9 |
| γ（拒绝） | 现在就建 profile 但保留旧字段 | ❌ 违反单一事实源判据 ① |

#### 11.2.5 TBD-9 触发条件与最小 schema（备查，不做）

**触发条件（全部满足）**：
1. 同一币种（或同一税制）内，确实存在 ≥2 套「方向 + 精度」组合需要按单据类型/客户/日期切换；
2. 现有字典 + 币种字段无法表达（例如需要「精度 2、现金单位 0.05」这类 MAU 语义）；
3. 业务能给出配置归属（挂币种 / 挂税制 / 挂价目表），而非「全局唯一」。

**最小 schema（若触发）**：

```yaml
id: rounding_profile
table_name: rounding_profiles
fields:
  - id: code            # 唯一业务键，禁止用中文名做键
  - id: currency_id     # 作用域一：币种（可空，空=通配）
  - id: tax_code_id     # 作用域二：税制（可空）
  - id: price_list_id   # 作用域三：价目表（可空）
  - id: decimals_source # enum: currency | profile（显式声明覆盖关系，禁止隐式）
  - id: decimals        # decimals_source=profile 时必填
  - id: rounding_mode   # 引用字典 rounding_mode
  - id: increment_unit  # MAU / Rounding Factor；空=不启用
  - id: level           # enum: line | document（TBD-8）
  - id: status
```

**迁移前置条件（强制）**：`allocation_rule` / `allocation_result` / `rate_type` / `pricing_period` / `tax_code` 五处 `rounding` 字段必须**同批**改为 `rounding_profile_id` 引用或删除，且 `round_amount` 增加 profile 参数；否则视为驳回（第二真源）。

**Sources**
- Oracle Fusion：`research-fusion-billing-deep-dive-2026-11-09.md` §币种精度/税制舍入/价目表 Round To
- SAP：条件类型舍入规则、T001R（公司代码×币种舍入单位）、`DIFF` 条件类型、Rounding Profile（数量语义）
- 项目内：`meta/core/rounding.py`（方向静态镜像 + 测试锁定）、`meta/schemas/currency.yaml#decimal_places`（精度注释）、`meta/services/sales_order_amount_service.py#L60-L80`（税方向参照实现）