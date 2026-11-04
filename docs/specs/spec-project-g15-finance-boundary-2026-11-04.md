# 设计稿：财务模块边界与过账架构 — 元数据驱动 + 单一事实架构

- 文档版本：v0.1
- 日期：2026-11-04
- 状态：设计稿（仅研究，**尚未实施**）
- 约束前提（用户给定）：
  1. 平台**可能自建财务模块**；
  2. 平台**也必须能对接外部财务系统**；
  3. 平台是**元数据模型驱动**（YAML schema → API / UI / 权限）；
  4. 平台坚持**单一事实架构原则**（余额是事务投影、不落第二套台账、派生视图唯一口径）。
- 关联文档：
  - `spec-project-g15-eto-oracle-vs-sap-2026-11-04.md`（G15 裁决，含成本双层口径）
  - `spec-project-g15-eto-oracle-benchmark-2026-11-03.md`（Expenditure Item 唯一事实源）
  - `spec-project-g15-eto-sap-benchmark-2026-11-04.md`（PS + RA + Settlement）
  - `spec-project-g15-eto-infor-ifs-benchmark-2026-11-04.md`
  - `spec-project-g4-engineering-bom-2026-11-03.md`

---

## 0. 结论摘要（先看这里）

1. **"单一事实"不是"一张表"，而是"一件事只有一个源头"。** 平台要区分三类事实：**业务事实**（订单、收发、库存事务、工单、工时）、**会计事实**（借贷平衡、不可变、可审计的凭证）、**派生结果**（余额、项目成本、损益）。前者是源头，中者是依据规则派生的产物，后者必须可随时重算。三者都不能各建一套账。
2. **业务事实的唯一书（book of record）永远是平台**；**法定账簿的唯一书按法人二选一**——要么平台内建账簿，要么外部财务系统。**同一法人主体绝不允许同时存在两套法定账**，这是本稿的硬红线。
3. 因此财务模块的第一性设计不是"建总账"，而是**建过账契约（accounting event → posting rule → journal）**。没有契约，自建和外部对接两条路都会退化成"业务模块各自写财务"的重复台账。
4. **凭证是业务事实的确定性投影，不是第二事实源。** 凭证的每一行都必须可追溯到 `accounting_event_id` + 业务单据；凭证一旦 `posted` 不可修改，更正只能"冲销 + 重记"。
5. **余额与成本都是投影**。推荐直接复用平台已验证的投影范式（`inventory_balances` 只读投影、`auto_crud: false`）：`gl_balances` 同构；项目成本沿用既有 `v_project_cost` 单一派生视图，**不新建项目成本表**。
6. **过账规则必须元数据化，但必须有表达力上限。** 采用"事件类型 → 科目映射 → 凭证模板"三层，规则是版本化数据（`valid_from/valid_to`），**不引入脚本引擎**；凭证保存 `rule_version` 快照以保证历史可复现。
7. **跨系统一致性复用平台已有的 `event_outbox` + 幂等消费**（`meta/core/event_outbox.py` 已具备同事务入队、重试、死信、`idempotency_key` 强制校验）。**不新建第二套 outbox**——否则连"单一事实"的第一条都破了。
8. **外部财务对接的最小契约只有三件**：主数据（科目/币种/汇率/法人）、凭证（含借贷行与维度）、状态回写（凭证号/过账/冲销/期间状态）。其余（对账、差异、重发）都是这三件的配套。
9. **ETO 的财务落点不是"项目会计模块"，而是"带 `project_id/task_id` 维度的分录"。** 工单、发料、报工、外协、采购、开票各自在正确的时点产生会计事件；项目成本只是这些分录按 `(project, task)` 的聚合，与 SAP 的 PS+Settlement、Oracle 的 Expenditure Item 口径一致。
10. **建议分三期，先做契约后做账**：Phase 0 会计事件 + 科目映射 + 过账契约（不建 GL）；Phase 1 外部对接（outbox + adapter + 对账）；Phase 2 自建总账（凭证/期间/冲销/余额投影）；Phase 3 多币种、税、AR/AP、WIP/收入确认。

---

## 1. 问题定义

用户提出的是**四个约束叠加**下的设计问题：

| # | 约束 | 对设计的直接影响 |
|---|---|---|
| C1 | 可能自建财务模块 | 需要一个"财务管理"产品边界，而不是零散字段 |
| C2 | 也要支持外部财务系统 | 需要适配层，且不能假设外部系统与本平台同构 |
| C3 | 元数据模型驱动 | 科目、映射、规则、期间、外部系统都必须是 **schema 对象**，不是代码常量 |
| C4 | 单一事实架构 | 余额/成本/损益必须可重算；禁止第二套台账；禁止双账 |

传统 ERP 的做法在这四条约束下会失败的地方：

- **失败模式 A（各自建账）**：库存模块算库存成本、生产模块算 WIP、项目模块算项目成本、财务模块再抄一遍 → 四套数字，月度对不上。
- **失败模式 B（财务后置补录）**：业务跑完，财务月底手工做凭证 → 财务是"事后翻译"，永远滞后且不可追溯。
- **失败模式 C（对接即复制）**：对接外部财务时把业务表整表推送 → 外部系统成为第二套事实源，平台与外部双向漂移。
- **失败模式 D（规则代码化）**：过账规则写死在 Python `if/else` → 元数据驱动失效，换一个客户就要改代码。

本稿的目标就是把这四种失败模式在设计层堵死。

---

## 2. 先厘清"三个单一事实"

这是全稿最重要的一节。**"单一事实"经常被误读为"只能有一张表"**，导致团队反复争论"凭证算不算第二套台账"。正确的拆法是按事实的**性质**分层：

### 2.1 三层事实模型

| 层 | 定义 | 本平台的承载 | 是否允许重复存储 | 是否可变 |
|---|---|---|---|---|
| **L1 业务事实** | 实际发生的业务动作：下达、收货、发货、领料、报工、完工、开票 | `sales_orders`、`receipts`、`shipments`、`inventory_transactions`、`work_orders`、`time_entries`、`purchase_orders` | 否。每个动作只有一条记录 | 状态可流转，已确认的事实不可回改（靠冲销/红字） |
| **L2 会计事实** | 业务事实按会计规则翻译后的借贷分录 | `accounting_events` → `journal_entries` / `journal_lines` | **否**。分录不是业务数据的副本，是带规则与科目的**确定性投影** | `posted` 后不可改，只能 `reversed` |
| **L3 派生结果** | 由 L1/L2 聚合算出的余额、成本、损益 | `gl_balances`（投影表）、`v_project_cost`（视图）、`v_trial_balance`（视图） | **可重复**（投影可重建），但必须**只有一个口径** | 随时可重算 |

关键推论：

- **L2 不是 L1 的副本。** 凭证里的金额可能因汇率、税、舍入、科目分摊而与业务单据金额不同；凭证里的维度可能比业务单据更细。所以"把业务表再存一遍"不叫会计事实，叫冗余。
- **L3 绝不能落成手工维护的表。** 任何"项目成本表 / 库存金额表 / 科目余额表"只要允许人工修改，就已经是第二套账。必须 `auto_crud: false` + 只读投影。
- **同一个业务动作可以产生多条会计事件**（如收货 → 暂估；发票匹配 → 冲暂估 + 正式应付）。事件是"一动作多解释"，不是"一动作一凭证"。

### 2.2 与既有平台原则的对齐

平台已有两个可直接复用的范式，财务应严格同构，而不是另起一套：

| 既有范式 | 位置 | 财务对应 |
|---|---|---|
| 余额是事务投影，可随时重建，只读无 CRUD | [inventory_balance.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/inventory_balance.yaml) | `gl_balances`：分录投影，`auto_crud: false` |
| 跨应用事件 outbox：同事务入队 + at-least-once + 幂等键 + 死信 | [event_outbox.py](file:///d:/filework/excel-to-diagram/meta/core/event_outbox.py) | `accounting_event` 入队与外部投递复用同一机制 |
| 汇率单向存储、只存不算、舍入由消费方执行 | [currency_rate.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/currency_rate.yaml) | 凭证折算存**快照汇率**，不实时取汇率 |
| 法人资格由职能决定，不由 org_type 决定 | [org_legal_entity.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/org_legal_entity.yaml) | `ledger` 必须挂在**法人主体**上，不挂任意 org |
| 维度 → 对象字段映射是配置而非硬编码 | [dimension_object_mapping.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/dimension_object_mapping.yaml) | 凭证维度用固定 FK 列 + 权限维度映射，不建通用维度引擎 |

---

## 3. 财务边界矩阵：平台做什么、外部做什么

### 3.1 能力清单与归属

判定原则：**"产生业务动作的能力"归平台；"产生法定报送与合规申报的能力"归外部（除非自建）**。

| 能力 | 平台内建（必须） | 可选内建 | 外部财务系统典型拥有 | 边界说明 |
|---|---|---|---|---|
| 业务单据（订单/收货/发货/领料/报工/开票申请） | ● | | | 平台是 L1 唯一源 |
| 库存数量与库存事务 | ● | | | 已有 `inventory_transactions` |
| 会计事件（业务动作 → 会计含义） | ● | | | 平台必须能解释自己的业务 |
| 科目主数据 | | ● | ● | 外部为账本时，科目由外部下发；平台只读缓存 |
| 科目映射 / 过账规则 | ● | | | 规则的"决定权"必须在平台，否则无法自建 |
| 凭证（借贷分录） | | ● | ● | **二选一**，见 §3.2 |
| 总账 / 试算平衡 | | ● | ● | 同上 |
| 会计期间与关账 | | ● | ● | 同上 |
| 余额投影 | ● | | | 无论谁记账，平台侧都要能算（用于运营决策） |
| 项目成本 / 项目损益 | ● | | | 平台必须自持，但不能与 GL 冲突（见 §6.3） |
| 多币种折算 | | ● | ● | Phase 1 单功能币，多币种延后 |
| 税务计算与申报 | | | ● | 平台只做税码/税率承载（已有 `tax_code`/`tax_rate`/`tax_classification`） |
| AR / AP 明细与账龄 | | ● | ● | 平台侧只需"应收/应付发生额"，账龄归外部 |
| 固定资产 | | | ● | 不建 |
| 合并报表 / 法定报表 | | | ● | 不建 |
| 资金 / 银行 / 支付 | | | ● | 不建 |
| 成本核算（标准/实际） | | ● | ○ | ETO 用实际归集；标准成本延后 |
| WIP / 收入确认（POC） | | ● | ● | Phase 3，或整体交外部 |

### 3.2 `ledger_scope`：杜绝双账的唯一开关

**设计：一个法人主体（`org_legal_entity`）在任一时刻只能有一个"记账主体"（book of record）。**

`ledger` 对象关键字段：

| 字段 | 含义 | 约束 |
|---|---|---|
| `legal_entity_id` | 法人主体（引用 `org_legal_entity`） | 必填 |
| `ledger_type` | `primary`（主账）/ `secondary`（报告账）/ `consolidation` | 一个法人**只能有一个** `primary` |
| `ledger_scope` | `internal`（平台记账）/ `external`（外部记账） | `primary` 的 scope 决定该法人走哪条路 |
| `functional_currency_id` | 功能币 | 引用 `currency` |
| `fiscal_calendar_id` | 会计日历 | 引用 `calendar` |
| `external_system_id` | 外部系统（仅 `external` 时有值） | 引用 `external_system` |
| `status` | active / inactive | |

唯一性守卫：`(legal_entity_id, ledger_type='primary')` 全局唯一 → **从结构上不可能出现同一法人两套主账**。

补充规则：

- `secondary` / 报告账**只能由 `primary` 派生**（折算而来），不允许独立手工记账。
- 同一集团下不同法人可以混用：A 法人 `internal`、B 法人 `external`。这是允许的，也是"混合模式"的实现方式；**但每个法人内部仍只能一个账**。
- 外部系统一旦接管某法人，平台对该法人的凭证能力应**关闭写入口**（只保留"生成待推送凭证"与"对账"），避免两处都能记账。

### 3.3 三种部署形态

| 形态 | 描述 | 适用条件 | 必须守住的红线 |
|---|---|---|---|
| **A. 契约型（最小）** | 平台只做 L1 + 会计事件 + 过账契约；凭证与总账全在外部 | 客户已有成熟财务系统（SAP/Oracle/金蝶/用友），且不愿迁移 | 平台**不得**自己算"法定口径"的账；项目成本只能用运营口径 |
| **B. 自建型** | 平台内建 `internal` ledger，凭证/期间/总账/余额全在平台 | 客户无财务系统，或希望业财一体 | 平台必须承担审计要求（不可变、留痕、可追溯） |
| **C. 混合型（推荐演进路径）** | 先用 A 打通，再把部分法人迁到 B | 现实中最常见 | 迁移时**必须先冻结外部账、再启用内部账**，同一期间不得双写 |

---

## 4. 架构分层：事件、规则、凭证、投影

```
[业务动作 L1]
   sales_order / receipt / shipment / inventory_transaction
   work_order / time_entry / purchase_order / 开票申请
        │  ① 同事务写入
        ▼
[会计事件 accounting_event]  ← 平台自有，不可丢失
        │  ② 按事件类型匹配规则
        ▼
[过账规则 posting_rule + posting_rule_line]  ← 元数据，版本 + 生效日
        │  ③ 生成借贷行
        ▼
[凭证 journal_entry / journal_line]  ← 不可变；posted 后仅可冲销
        │  ④ 过账
        ▼
[余额投影 gl_balances] + [项目成本视图 v_project_cost]  ← 只读，可重建
        │  ⑤ 投递
        ▼
[event_outbox] → 外部财务系统 / 内部下游
```

五个必要的"硬点"：

1. **① 必须同事务**：会计事件与业务写在同一 DB 事务内落库。否则业务成功、事件丢失 = 永久性账实不符。
2. **② 必须可重放**：同一事件重复处理必须幂等（`accounting_event.idempotency_key` 唯一）。
3. **③ 必须可复现**：凭证要存 `rule_version` + `rate_snapshot`，三年后重算仍得同一结果。
4. **④ 必须单向**：凭证只能从事件生成；**不允许人工直接新增凭证**（否则绕过审计链）。人工调整走"调整凭证"，也必须锚定一个事件。
5. **⑤ 必须 at-least-once**：外部投递复用 outbox，消费端幂等；失败进死信，人工补偿而不是静默丢弃。

---

## 5. 元数据对象建议（可直接落 YAML）

### 5.1 复用（**不重复造**）

| 已有对象 | 财务用途 | 注意 |
|---|---|---|
| `currency` / `currency_rate` / `external_rate_source` | 币种、汇率、外部汇率源 | 汇率单向存储，凭证折算存快照，不实时取 |
| `tax_code` / `tax_rate` / `tax_classification` | 税码、税率、税分类 | 只做承载，不做申报 |
| `payment_term` / `payment_term_line` | 付款条件 | AR/AP 若外部做，仅作业务参考 |
| `org_legal_entity` | 法人主体 | `ledger` 必须挂它 |
| `dimension_object_mapping` | 权限维度（org / territory） | 财务维度**不要**扩成通用维度引擎 |
| `number_sequence` | 凭证号 | 按 `(ledger_id, period, journal_type)` 分段 |
| `calendar` / `calendar_day` | 会计日历 | 期间边界由日历派生，不另建 |
| `event_outbox` | 会计事件投递 / 外部对接 | **复用，不新建 outbox** |

### 5.2 新增对象（建议 8 个，分期落地）

| # | 对象 | 表名 | 定位 | 关键约束 | 期次 |
|---|---|---|---|---|---|
| 1 | `ledger` 账簿 | `ledgers` | 记账主体 | `(legal_entity_id,'primary')` 唯一 | P0 |
| 2 | `gl_account` 会计科目 | `gl_accounts` | 科目主数据（树） | 只有叶子可记账；`normal_balance` 决定余额方向 | P0 |
| 3 | `posting_rule` 过账规则 | `posting_rules` | 事件类型 → 凭证模板 | 版本 + `valid_from/valid_to`；同一 `(ledger, event_type, condition_key)` 同时段唯一 | P0 |
| 4 | `posting_rule_line` 规则行 | `posting_rule_lines` | 借贷方向、科目来源、金额来源、维度模板 | 借贷必须能在规则层配平 | P0 |
| 5 | `accounting_event` 会计事件 | `accounting_events` | 业务动作的会计解释 | `idempotency_key` 唯一；与业务写同事务 | P0 |
| 6 | `journal_entry` 凭证头 | `journal_entries` | 一张凭证 | `posted` 不可改；`reversal_of_id` 表达冲销 | P1/P2 |
| 7 | `journal_line` 凭证分录 | `journal_lines` | 借贷行 | 借/贷二选一；必带 `project_id`/`task_id`（可空） | P1/P2 |
| 8 | `fiscal_period` 会计期间 | `fiscal_periods` | open / closing / closed | 已 `closed` 期间拒绝任何写入 | P2 |

> 可选后置（Phase 3）：`external_system`（外部财务系统注册与适配配置）、`external_doc_link`（平台单据 ↔ 外部凭证号/状态）、`gl_balances`（只读投影）、`account_mapping`（当科目映射复杂到需要独立维护时再拆）。

### 5.3 明确"不建"清单

| 不建 | 原因 |
|---|---|
| 第二张 `project_cost` 表 | 与 `v_project_cost` 重复，违反单一口径 |
| 库存金额表（与 `inventory_transactions` 并行） | 库存金额应由"分录 × 移动价"派生 |
| 通用维度引擎（任意维度值表） | 元数据驱动的边界内，固定 3~5 个 FK 列足够；通用维度会变成第二套元模型 |
| 独立 `posting_outbox` | 复用 `event_outbox`，避免两套投递语义 |
| 独立"财务日历" | 复用 `calendar`，避免期间口径分裂 |
| 独立"财务币种/汇率" | 复用 `currency`/`currency_rate` |

### 5.4 关键字段草案（`journal_line` 最重要）

```yaml
# journal_lines（示意，非最终 YAML）
- account_id            # 科目，必填，叶子科目
- side                  # debit / credit
- amount                # 交易币金额
- currency_id           # 交易币
- debit_amount_func     # 功能币借方（0 或正数）
- credit_amount_func    # 功能币贷方（0 或正数）
- rate_snapshot         # 记账时汇率快照
- project_id            # 项目（可空）
- task_id               # 项目任务/WBS（可空）
- org_id                # 组织/成本中心承载
- event_id              # 回溯到会计事件，必填，不可空
- rule_version          # 生成该行的规则版本，必填
```

三条结构性断言（应由服务层守卫强制，而不是靠人）：

- `debit_amount_func + credit_amount_func` 每行只能一边非零；
- 一张凭证 `sum(debit) == sum(credit)`（功能币口径）；
- `event_id` 非空且指向 `accounting_events` 中 `status='accounted'` 的事件。

---

## 6. 过账规则如何元数据化（本稿的技术核心）

### 6.1 三层结构，而非一张大规则表

| 层 | 对象 | 回答的问题 | 变更频率 |
|---|---|---|---|
| **事件类型** | `accounting_event.event_type`（枚举/字典） | "发生了什么会计含义" | 低 |
| **科目映射** | `posting_rule_line.account_source` | "记到哪个科目" | 中（随科目表调整） |
| **凭证模板** | `posting_rule` + `posting_rule_line` | "借贷怎么配平、金额怎么取、维度怎么带" | 中 |

把三层混成一张表，规则数会随场景×科目×组织爆炸。分层后：

- 新增一种业务场景 → 只加 `event_type` + 1 条规则；
- 科目表调整 → 只改映射，不动规则结构；
- 多法人不同科目 → 同一 `event_type` 在不同 `ledger` 下各一条规则。

### 6.2 表达力上限（必须写进规范）

**允许**（声明式，可静态校验）：

| 能力 | 表达方式 |
|---|---|
| 条件匹配 | 字段比较 / `in` / `and-or-not`（白名单 AST，参照 `event_outbox.evaluate_condition` 的既有实现） |
| 金额来源 | 单据头/行字段、已算好的小计、固定比例（如税率）、上一条规则行金额的引用 |
| 科目来源 | 固定科目 / 按维度值查映射 / 按物料组查映射 |
| 维度模板 | 直接取单据字段（`project_id`、`task_id`、`org_id`） |
| 借贷配平 | 规则行必须声明配平策略（末行"差额入某科目"或"等额反向"） |

**禁止**：

- 脚本 / 表达式语言 / 任意 SQL；
- 规则内发起跨表查询（会导致规则不可复现）；
- 规则调用外部系统；
- 规则内做币种折算（折算应在事件生成时快照）。

### 6.3 版本与快照：让历史可复现

- 规则是**版本化数据**：`valid_from` / `valid_to` / `version`，与平台 `item_structures`、`work_definitions` 的版本机制同构。
- `journal_lines.rule_version` 记录生成时的规则版本。**规则改版后，历史凭证不重算**。
- 重算工具（如重跑某期间）必须支持"用历史版本重放"，结果须与已过账凭证逐行一致；不一致即为 bug，不是"规则升级"。
- 科目映射同样要版本化，否则同一规则在新旧科目表下会产出不同科目。

### 6.4 与既有 `engineering_change` / `change_event` 的关系

平台的变更留痕（`audit_log`、`change_event`）已能回答"谁改了规则"。财务侧只需额外保证：

- 规则变更**必须**产生一条审计事件（不能绕过 `audit_aspect`）；
- 规则变更影响的是**未来事件**，不能静默重写历史。

---

## 7. 事件契约、幂等与外部对接

### 7.1 事件契约（复用现有应用包机制）

平台已有 `apps/*/app.yaml` 的 `events.publish` / `events.subscribe` 契约，并在启动期校验订阅方必须声明 `idempotency_key`。财务应作为**应用包**接入，而不是硬塞进 `meta`：

```
apps/finance/
  app.yaml            # events.publish: accounting.journal_posted / journal_reversed
                      # events.subscribe: sales_order.confirmed / receipt.posted ...
  schemas/            # ledger / gl_account / posting_rule / accounting_event / journal_*
  blueprints/         # 仅放"规则解析 / 配平校验 / 投递适配"这类无法声明式表达的部分
  handlers/           # 幂等消费入口
```

这样做的好处：

- 财务可**按客户启用/禁用**（`ENABLED_APPS`），符合"可能自建也可能不自建"；
- 数据库可独立（`APP_DB_ROUTING`），财务库与业务库解耦，但**事件与业务写仍同库同事务**（outbox 位于发布方库）；
- 权限命名空间 `finance` 天然隔离。

> 注意：若财务与业务被拆到两个库，"同事务"就失效。**推荐：会计事件表与业务表同库**；凭证/总账可以独立库，通过 outbox 异步。这是本设计对 `APP_DB_ROUTING` 的唯一硬要求。

### 7.2 幂等键设计

```
idempotency_key = f"{source_doc_type}:{source_doc_id}:{event_type}:{seq}"
```

- `seq` 用于"同一单据同一事件类型可发生多次"（如分批收货、分次报工）。
- 唯一约束在 `accounting_events` 上；重复投递 → 直接返回原事件，不重复生成凭证。
- 外部投递的幂等键**必须透传**给外部系统（若外部不支持，则在 `external_doc_link` 做本地去重 + 对账兜底）。

### 7.3 外部对接的最小契约（三件套）

| # | 契约 | 内容 | 落地形式 |
|---|---|---|---|
| 1 | **主数据同步** | 科目表、币种、汇率、法人、税码 | 定时拉取或文件；平台侧**只读缓存**，不反向写外部 |
| 2 | **凭证推送** | 凭证头 + 分录 + 维度 + 源单据号 + 幂等键 | outbox → adapter → 外部 API / 中间表 / 文件 |
| 3 | **状态回写** | 外部凭证号、过账状态、期间状态、冲销关系、错误码 | 外部回调 / 平台轮询；写入 `external_doc_link` |

配套但非必需：

- **对账三件套**：总量对账（笔数/金额合计）、明细对账（幂等键逐个匹配）、差异清单（平台有外部无 / 外部有平台无 / 金额不一致）。
- **死信处理**：`event_outbox.status='dead'` 的事件必须进入"待人工处理"工作台，并有补偿入口（重推 / 作废 / 人工凭证）。

### 7.4 迟到事件与跨期

这是外部对接最容易出事故的地方，必须在设计层定死：

| 概念 | 定义 | 规则 |
|---|---|---|
| `event_date` | 业务发生日（如收货日） | 来自业务单据，不可改 |
| `posting_date` | 记账日 | 默认 = `event_date`；若期间已关，顺延至最早可用期间 |
| `period_id` | 会计期间 | 由 `posting_date` + `fiscal_calendar` 派生 |
| 已关期间的迟到事件 | 业务补录、跨月到货 | **不得回写已 `closed` 期间**；只能入当前期或"调整期"，并在凭证上标记 `late_event=true` |

---

## 8. ETO 场景的过账时点（与 G15 直接相关）

ETO 的特点是"长周期、按项目、变更频繁"。下面这张表把每个业务动作映射到会计事件与维度，是 G15 落地的具体依据：

| 业务动作 | 会计事件 `event_type` | 借贷方向（简化） | 维度 | 期次 |
|---|---|---|---|---|
| 采购订单下达 | `po_committed` | 不入账（仅承诺） | project/task | 可选（管理口径） |
| 采购收货 | `goods_receipt` | Dr 原材料/在途；Cr 应付暂估 | project/task | P1 |
| 采购发票匹配 | `invoice_match` | Dr 应付暂估；Cr 应付账款 | project/task | P2 |
| 生产发料 | `material_issue` | Dr WIP（项目）；Cr 原材料 | project/task | P1 |
| 报工 | `labor_booking` | Dr WIP；Cr 人工吸收/应付职工薪酬 | project/task | P1 |
| 外协发出 | `subcontract_issue` | Dr 委外加工；Cr 原材料 | project/task | P2 |
| 外协收货 | `subcontract_receipt` | Dr WIP/成品；Cr 委外加工 + 应付 | project/task | P2 |
| 完工入库 | `production_completion` | Dr 成品库存；Cr WIP | project/task | P1 |
| 销售发货 | `shipment` | Dr 主营业务成本；Cr 成品库存 | project/task | P1 |
| 开票 | `invoice_issued` | Dr 应收账款；Cr 收入 + 销项税 | project/task | P2 |
| 项目变更（ECM 实施） | `engineering_change_applied` | 通常不入账（影响未来成本） | project | — |
| 期末 WIP 结转 / 收入确认 | `wip_close` / `revenue_recognition` | 按完工百分比 | project/task | P3（或交外部） |

三条 ETO 专属口径：

1. **项目成本不是独立账**：上表每一行的 `journal_lines.project_id/task_id` 就是项目成本的唯一来源；`v_project_cost` 只做聚合。
2. **变更不入账，但影响未来**：ECM 实施改变 BOM/工艺 → 改变未来的领料与工时 → 自然反映在后续事件里。**不要**为变更建"预计成本调整凭证"。
3. **项目库存必须带项目维度**（对齐 SAP 项目库存绑 WBS / Oracle 项目库存）：`inventory_transactions` 若缺项目维度，发料就无法归集到项目。这与既有的"库存需补 `project_task_id`"结论一致。

---

## 9. 分三期路线

### Phase 0：契约先行（不建总账）

**交付**

- `ledger`（只建配置，不建账）
- `gl_account` + `posting_rule` + `posting_rule_line`
- `accounting_event`（核心表，含幂等键与 `rule_version` 预留）
- 事件采集：接入 3~5 个高频动作（收货、发料、报工、完工、发货）
- 配平校验服务 + 规则静态校验（禁止非法表达式）

**验收**

- 任一业务动作能产出**结构化、可配平**的"待过账事件"；
- 规则改版后历史事件不重算；
- 重放同一事件 100 次只产生 1 条记录。

**退出条件**：能导出一份"凭证草稿"（不落 `journal_entries`），交财务人工核对无误。

### Phase 1：外部对接

**交付**

- `external_system` + `external_doc_link`
- outbox 投递适配（API / 中间表 / 文件三选一，先做一种）
- 对账三件套 + 死信工作台

**验收**

- 凭证推送幂等、可重发；
- 对账差异可定位到具体 `idempotency_key`；
- 外部冲销能回写并在平台可见。

**退出条件**：连续 2 个会计期间，平台事件与外部凭证 100% 匹配（或差异全部有解释）。

### Phase 2：自建总账

**交付**

- `journal_entry` / `journal_line`（posted 不可变）
- `fiscal_period`（open/closing/closed）
- 冲销机制（`reversal_of_id`）
- `gl_balances` 只读投影 + `v_trial_balance`
- 关账流程（试算平衡 → 差异检查 → 关闭）

**验收**

- 试算平衡恒成立；
- 已关期间无法写入（API 400 + 守卫）；
- 冲销后余额回到冲销前；
- 投影可从分录全量重建，结果一致（逐分）。

**退出条件**：能独立出具资产负债表/利润表草稿（不要求合并与附注）。

### Phase 3：进阶

- 多币种（交易币/功能币/报告币三层 + 折算差额科目）
- 税（销项/进项 + 税码映射；申报仍交外部）
- AR/AP 发生额与账龄（若外部不做）
- WIP / 收入确认 / 项目损益结转

---

## 10. 验收与验证方法

| # | 验证项 | 方法 | 通过标准 |
|---|---|---|---|
| V1 | 黄金凭证集 | 固定 20~30 个业务场景，断言生成的凭证逐行一致 | 与基线零差异 |
| V2 | 幂等重放 | 同一事件重复投递 N 次 | 只产生 1 凭证 |
| V3 | 借贷配平 | 全量凭证扫描 | `sum(debit)==sum(credit)` 恒成立 |
| V4 | 试算平衡 | 全科目余额汇总 | 借方合计 == 贷方合计 |
| V5 | 投影重建 | 清空 `gl_balances` 后从 `journal_lines` 重建 | 逐分一致 |
| V6 | 关账守卫 | 对已 `closed` 期间写入 | 100% 被拒 |
| V7 | 规则版本回放 | 用旧版本规则重算历史事件 | 与历史凭证一致 |
| V8 | 对账 | 平台 vs 外部 | 差异可逐条定位 |
| V9 | 回溯性 | 任一凭证行 → 事件 → 业务单据 | 链路完整，无断点 |
| V10 | 汇率快照 | 改汇率后重查历史凭证 | 金额不变 |

---

## 11. 风险与反模式

| # | 风险 | 表现 | 处置 |
|---|---|---|---|
| R1 | **双账** | 同一法人同时有内部账与外部账 | `ledger` 唯一约束 + 迁移前冻结 |
| R2 | **规则爆炸** | 每个场景×组织×科目一条规则，几百条 | 三层结构 + 事件类型收敛；规则数设上限（建议 < 80/法人），超出即设计问题 |
| R3 | **规则代码化** | `if/else` 写进 Python | 静态校验 + Code Review 红线 |
| R4 | **项目成本二次台账** | 项目模块自建成本表 | 只允许 `v_project_cost` 视图 |
| R5 | **FX / 舍入漂移** | 实时取汇率导致历史金额变化 | 快照汇率 + 舍入规则固定在事件层 |
| R6 | **跨期迟到事件** | 回写已关期间 | `posting_date` 顺延 + `late_event` 标记 |
| R7 | **维度漂移** | 事后改 `project_id` | 凭证维度来自业务单据快照，禁止更新 |
| R8 | **ack 丢失** | 外部已记账、平台仍 pending | 幂等键透传 + 对账兜底 + 死信工作台 |
| R9 | **审计缺口** | 直接改 posted 凭证 | 只允许冲销；API/守卫双层拦截 |
| R10 | **事件丢失** | 业务成功但事件未落 | 同事务 + outbox + 每日对账（业务单据数 vs 事件数） |

---

## 12. 待决策问题（建议默认值）

| # | 问题 | 建议默认 | 影响 |
|---|---|---|---|
| Q1 | 财务做应用包（`apps/finance`）还是进 `meta` 核心？ | **应用包** | 可禁用、可独立库、权限隔离 |
| Q2 | 第一个外部对接目标是谁？ | 先定**接口形态**（API / 中间表 / 文件），不绑定厂商 | 决定 adapter 设计 |
| Q3 | Phase 0 先接哪些业务动作？ | 收货、发料、报工、完工、发货（五件） | 覆盖 80% 制造金额流 |
| Q4 | 是否需要多法人？ | 若需要，`ledger` 必须按法人建，且允许混合 scope | 决定 Q1 的库设计 |
| Q5 | 多币种何时做？ | Phase 3；Phase 1 单功能币 | 避免汇率复杂度前置 |
| Q6 | 成本口径：标准 vs 实际？ | ETO 用**实际归集**；标准成本延后 | 影响 WIP 与差异科目 |
| Q7 | WIP/收入确认在平台还是外部？ | 优先外部；平台只出"项目成本明细" | 影响 Phase 3 范围 |
| Q8 | 税额计算在平台还是外部？ | 平台算"业务参考税额"，法定以外部为准 | 避免双重税务口径 |

---

## 13. 参考

- Oracle Subledger Accounting（SLA）架构：子账不直接记账，先发"会计事件"，由会计方法规则生成子账凭证，再 transfer 到 GL 并 post。→ 与本稿 §4 的"事件 → 规则 → 凭证"链路同构。
  - `https://oracleappsguide.com/learning/sla-architecture-rules`
  - `https://govoracleapps.wordpress.com/2020/05/10/create-accounting/`
  - `https://open-exam-prep.com/study-guides/oracle-1z0-1055-26/invoice-automation-imaging-sla/subledger-accounting-invoices`
- SAP S/4HANA Universal Journal（ACDOCA）：把 FI / CO / AA / ML / 盈利能力分析合并到**单一统驭表**，是"单一事实架构"在财务域最彻底的工业实现。→ 佐证 §2"会计事实只有一份"，但不等于"平台要把所有业务维度塞进一张表"。
  - `https://www.archondatastore.com/blog/acdoca-table-in-sap/`
  - `https://sapsolutionlab.com/demystifying-the-universal-journal-acdoca-the-heart-of-sap-s-4hana-finance-migration/`
- 平台既有实现：
  - [event_outbox.py](file:///d:/filework/excel-to-diagram/meta/core/event_outbox.py)（同事务 outbox + 幂等消费 + 死信）
  - [inventory_balance.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/inventory_balance.yaml)（只读投影范式）
  - [currency_rate.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/currency_rate.yaml)（单向汇率、只存不算）
  - [org_legal_entity.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/org_legal_entity.yaml)（法人主体面）
  - [apps/warehouse/app.yaml](file:///d:/filework/excel-to-diagram/apps/warehouse/app.yaml)（应用包与事件契约范式）

> 证据强度说明：Oracle SLA / SAP ACDOCA 部分为二手技术资料（架构层面可靠，具体配置细节未逐项核实）；平台侧结论均基于本仓库代码与 schema，强度为强。

---

## 14. 模式裁决：SAP 还是 Oracle？

### 14.1 结论

**不是二选一。**按维度切开：

- **数据形态取 SAP**：一个 `ledger` 只有**一张分录表**，FI / 成本 / 项目 / 存货金额全部落在同一批 `journal_lines` 上，靠维度列区分。这是 ACDOCA 的真正内核，也是"单一事实"在财务域唯一成立的形态。
- **生成机制取 Oracle**：业务动作先成为 `accounting_event`，再由版本化 `posting_rule` 派生成凭证，最后"过账"进账簿。这是 SLA 的内核，也是"元数据驱动 + 可对接外部"唯一成立的形态。
- **外部为账簿时不建总账**：某法人 `ledger_scope='external'`，平台只保留事件与契约，**连 ACDOCA 式分录表都不建**。此时"选哪个模式"这个问题本身不成立。

一句话：**Oracle 的骨架，SAP 的表**。

### 14.2 为什么不能纯 SAP

| 问题 | 说明 |
|---|---|
| ACDOCA 的前提是"全模块同系统" | 它的价值来自 FI/CO/AA/ML 实时写同一行。一旦法定账在外部系统，这个前提消失，ACDOCA 退化成一张普通分录表，却要求你实现 CO/AA/ML 的完整语义——投入产出比极差。 |
| 科目确定是隐式配置 | SAP 的 account determination 是"事务键 → 科目"的映射表（如 BSX/WRX），表达力面向固定事务类型，**难以版本化、难以逐条审计、难以按项目/任务动态派生**。与"规则是显式元数据"的要求冲突。 |
| 实时集成不可断点 | 实时统驭意味着业务写成功即财务已写，中间没有可重放的契约层。对接外部系统时，这个"不可断点"会变成不可重发、不可对账。 |
| 结构化代价 | 引入 CO、AA、ML 的语义，等于把平台改造成一个 ERP 财务内核；与"平台是业务事实源"的定位冲突。 |

### 14.3 为什么不能纯 Oracle

| 问题 | 说明 |
|---|---|
| SLA 对象太重 | 完整的 SLA 有 accounting method、journal line rule、account rule、description rule、supporting reference、event entity、event class 等一整套。对只有一个法人、一套科目的场景，是 20 个对象干 3 件事。 |
| 多账簿默认能力过剩 | Oracle 的 primary / secondary / reporting currency 三账体系面向跨国集团。若无合并报表需求，多账簿只会增加"哪本账是真的"的歧义。 |
| 子账与总账分离 | Oracle 允许每个子账各自一套记账逻辑，这在 ERP 里是优点，在"单一事实"平台上是风险——容易演变成"每个业务模块各写一套凭证"。 |

### 14.4 逐维裁决表

| 维度 | SAP 做法 | Oracle 做法 | 本平台裁决 | 理由 |
|---|---|---|---|---|
| 记账触发 | 业务过账即写统驭表（实时） | 业务发事件，SLA 规则生成子账凭证 | **Oracle** | 需要可重放、可断点、可对接外部 |
| 规则表达 | 事务键 → 科目（隐式配置） | 会计方法 → 规则 → 派生科目（显式配置） | **Oracle** | 元数据驱动 + 可版本化 + 可审计 |
| 分录存储 | 单表统驭（ACDOCA） | 子账凭证 + GL 凭证（可分开） | **SAP（单表）** | 单一事实、余额可重建 |
| 维度承载 | 同一行多维度列 | 子账凭证行带分配 | **SAP（同行）** | 避免"成本在另一张表" |
| 多账簿 | 一个公司代码一套账，多账靠平行分类账 | primary / secondary / reporting | **两者取中**：允许多账簿，但每法人仅一个 primary | 防双账 |
| 外部对接 | 内部实时集成，外部靠接口 | 事件 → 凭证 → transfer → post 四段契约 | **Oracle** | 外部系统是硬需求 |
| 项目成本 | CO 内部订单/WBS + 结算 | 子账分录带 project/task，Expenditure Item | **Oracle 形态 + SAP 单表** | 项目成本是分录聚合，不是独立模块 |
| 冲销/审计 | 冲销凭证、审计轨迹 | 冲销 + 子账追溯 | **Oracle（事件锚定）** | 每行必须能回溯源单据 |
| 期末处理 | RA + Settlement（重） | 关账 + 重估 + 结转（中） | **Oracle（轻）**，RA/Settlement 不建 | ETO 用实际归集，POC 交外部或 Phase 3 |
| 资产/物料分类账 | AA / ML | 独立子账 | **不建** | 超出边界 |

### 14.5 落到本平台的具体形态

```
ledger（Oracle 式多账簿，但每法人唯一 primary）
  └─ journal_entry（凭证头：ledger / period / posting_date / source_event / rule_version）
       └─ journal_line（SAP 式单表统驭：科目 + 借贷 + 功能币 + project/task/org 维度同行）
```

四条落地细则：

1. **一张分录表承担所有口径**：不再区分"财务凭证表 / 成本凭证表 / 项目凭证表"。项目成本、WIP、存货金额都从 `journal_lines` 的维度列取。
2. **余额是投影**：`gl_balances` 由 `journal_lines` 汇总重建，与 `inventory_balances` 同构，`auto_crud: false`。
3. **规则只做"生成"，不做"记账"**：`posting_rule` 的产物是 `journal_entry` 草案；`posted` 是独立动作，由期间状态与权限控制。
4. **`ledger_scope='external'` 时降级**：只有 `accounting_events` + outbox + 对账，**不落地 `journal_entries`**（或只落"待推送凭证"的影子记录，且标记 `shadow=true`，不可作为余额来源）。

### 14.6 明确不采用的部分

| 不采用 | 出处 | 原因 |
|---|---|---|
| ACDOCA 的 CO/AA/ML 子语义 | SAP | 平台无资产、无物料分类账 |
| 平行分类账（Parallel Ledger）独立记账 | SAP | 只允许派生，不允许独立写 |
| Results Analysis + Settlement | SAP | ETO 用实际归集；结算交外部 |
| Accounting Method 多套并存 | Oracle | 一套规则体系，靠 `valid_from` 版本化 |
| 子账各自记账 | Oracle | 所有子账统一走 `accounting_event` |
| 多币种三层账簿 | 两者 | Phase 3 再开；Phase 1 单功能币 |

### 14.7 一句话决策

> **账簿形状学 SAP，记账流程学 Oracle；法定账在外部时不学任何一家。**

这条裁决与 §3 的 `ledger_scope`、§4 的五段链路、§5 的对象清单完全自洽：`journal_lines` 是"一张表"，`accounting_event + posting_rule` 是"两段流程"，`ledger_scope` 是"一个开关"。
