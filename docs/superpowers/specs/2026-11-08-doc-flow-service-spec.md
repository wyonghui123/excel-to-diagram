# Spec：单据流服务层与元数据驱动 UI（Document Flow Service）

> 文档编号: 待定 | 状态: 草案 v1.1 | 日期: 2026-11-08（v1.1：补元数据驱动头部平台横向对标，见 §4.4）
> 前置: [2026-11-07 规则化收敛 Spec](./2026-11-07-rule-convergence-spec.md)（v2.2，§14 数量关系模型、§14.4 头行模式约束、TBD-32）
> 关联: `meta/core/doc_flow_*.py`、`meta/services/*_service.py`、`meta/api/bo_api.py`、`src/components/common/*`
> 对标: Oracle Fusion Cloud SCM（Procurement / Order Management）、SAP SD（VBFA 文档流）、Microsoft Dynamics 365 SCM

---

## 1. 背景与现状差距

### 1.1 已具备的能力（引擎层）

| 能力 | 实现 | 状态 |
|---|---|---|
| 数量关系边表 | `doc_flow_edges`（7 元组 + quantity + pool + status + 冲销字段） | 已落地 |
| 单源行派生 | `doc_flow_derive_engine.derive()` | 已落地 |
| 批量拆合派生 | `doc_flow_batch_engine.derive_batch()`（split_key 分单 / 头行两级 / 整批回滚） | 已落地，**唯一调用方是测试** |
| 累计消耗公式 | `_consumed_in_pool()`：`Σ active normal − Σ active red`，按 `pool` 隔离 | 已落地 |
| 冲销族 | `doc_flow_reversal`：`reverse_edge` / `red_ink_edge` / `counter_edge` / `compensate_edge` | 已落地 |
| 挂边（不传数量） | `doc_flow_attach.attach_edge()` | 已落地 |
| 对账 | `doc_flow_reconcile` | 已落地 |

### 1.2 缺口（本 Spec 要解决的）

| # | 缺口 | 证据 |
|---|---|---|
| G-01 | **无通用服务层**：业务代码直接调引擎，或根本不调 | `meta/api/` 下无任何 doc_flow 路由；`grep doc_flow meta/api` 零命中 |
| G-02 | **无「候选上游 + 未结量」读接口**：调用方拿不到「还能生成多少」 | `doc_flow_schema.py` 明确不做通用 `open_qty` 视图 |
| G-03 | **无「可编辑本次生成数量」入口**：`derive_batch` 的 `items[].quantity` 需调用方自己算 | 现有唯一调用方是测试 |
| G-04 | **取消不释放额度**：`shipment_service.cancel` / `receipt_service.cancel` / `transfer_order_service.cancel` 只改单据 status，不碰边表 | `shipment_service.py:623-636`、`receipt_service.py:694-710`、`transfer_order_service.py:643-667` |
| G-05 | **幂等键不排除冲销边**：`_find_edge_by_key` / `_find_edge_loose` 不筛 `status`，`reversed` 边仍命中重放 → 「取消后对同一目标再生成」走不通 | `doc_flow_derive_engine._find_edge_by_key()` |
| G-06 | **只有 5 条硬编码业务链路**调 `attach_edge` / 引擎：采购申请→PO、销售→发货、收货、调拨、发货过账 | `requisition_po_conversion.py:160-164`、`shipment_service.py:178-190`、`receipt_service.py:1200-1224`、`transfer_order_service.py:520/588` |
| G-07 | **前端零单据流组件**：`src/` 下无任何 `doc_flow` 页面/组件 | 现状盘点 |
| G-08 | **无批量生成的下游确认视图**：多选上游后无法预览会拆成几张单、每张含哪些行 | 现状盘点 |

### 1.3 目标

1. 提供**一个**通用服务入口：输入「规则 + 上游实例（带数量）+ 目标（新建或追加）」，输出「生成/重放结果」。
2. 提供**一个**通用读入口：按规则列出候选上游行，带 `quantity / consumed_qty / open_qty`。
3. 让「取消 / 红冲 / 关闭」对上游累计量的影响**有明确定义**并落到代码。
4. 提供**元数据驱动**的两个 UI 入口：上游多选批量生成、下游单据内追加。
5. 不改变已有 5 条业务链路的对外行为（等价性回归）。

---

## 2. 范围与边界

### 2.1 在范围内

- 服务层：`meta/services/doc_flow_service.py`（新建）。
- API：`meta/api/doc_flow_api.py`（新建），`/api/v2/doc-flow/*`。
- 取消/红冲/关闭的关系层语义修正（含幂等键排除冲销边）。
- 前端：`DocFlowSourcePicker` / `DocFlowDerivePanel` / `DocFlowTracePanel`（新建），复用现有 `MetaListPage` / `SearchHelpDialog` / `ActionExecutor`。
- 视图元数据：单据流入口的动作声明与列配置。

### 2.2 不在范围内

- 重新设计边表结构（沿用 `doc_flow_edges`）。
- 重建 `doc_flow_batch_engine` 的拆合算法（沿用 split_key / head_overrides）。
- 通用图形化流程画布（P3 可选项，见 §12）。
- 成本、价格、库存可用量的派生（各自域已独立实现）。
- 跨库事务（保持单库单事务，与 F5 一致）。

### 2.3 必须遵守的既有约束

| 约束 | 来源 | 说明 |
|---|---|---|
| 数量本体 | 规则收敛 Spec §14 | 单据流 = 数量关系，字段拷贝只是目标字段填充动作 |
| 头行模式一源行一目标行 | 规则收敛 Spec §14.4 硬约束 2 | 同量重放；异量返回 `HEAD_LINE_MULTI_NOT_SUPPORTED` |
| 不引入数量时段 | 规则收敛 Spec §14.5 / TBD-31 | `pool` 不是时间桶，仅用于多池隔离 |
| 分单 ≠ 分行 | 规则收敛 Spec §14.3 | `split_key` 产出多张目标单据；同单多行需单表模式或另设行因子（不在本 Spec） |
| Σ 守恒 | 规则收敛 Spec §14.2 | 任意时刻 `Σ active normal − Σ active red ≤ 源行数量`，按 `pool` 隔离 |
| 单库单事务 | `doc_flow_derive_engine` 模块注释 F5 | 引擎只接受同一 `app_ds` |

---

## 3. 术语

| 术语 | 定义 |
|---|---|
| 源行（source line） | 上游单据明细行，由 `(source_bo, source_id, source_item)` 唯一标识 |
| 边（edge） | 一条「源行 → 目标行」的数量关系记录，落在 `doc_flow_edges` |
| 消耗量 consumed_qty | 某源行在指定 `pool` 内所有 `active` 边的净数量：`Σ normal − Σ red` |
| 未结量 open_qty | `源行数量 − consumed_qty`，即本次最多可生成量 |
| 本次生成量 | 本次请求为该源行写入新边的数量，必须 `0 < qty ≤ open_qty` |
| 分单 split_key | 决定目标单据拆分的源行字段组合；同一组合进同一张目标单据 |
| 头行模式 | 规则声明 `target_line_bo`，目标为「单头 + 明细行」两级 |
| 单表模式 | 规则未声明 `target_line_bo`，目标只有一张表 |
| create 模式 | 目标行由引擎新建（`target_data` 不含 `id`） |
| append 模式 | 目标行/单头已存在，本次挂接（`target_data` 含 `id`，或 `head_overrides['id']`） |

---

## 4. 头部产品对标

> 调研口径：官方产品文档 + 产品内可观察行为。调研日期 2026-11-08。用户口述的「Allo Allo confusion」按 **Oracle Fusion Cloud SCM** 理解。

### 4.1 Oracle Fusion Cloud SCM

#### 4.1.1 单据流展示

| 模块 | 形态 | 关键点 |
|---|---|---|
| Procurement | **Requisition Life Cycle** 页 | 按 PO 分组，逐行展示 `Ordered / Delivered / Received / Invoiced` 的数量与金额；上方金额柱状图；点数量可下钻到对应单据 |
| Order Management | **无独立 Document Flow 页** | 靠 `Fulfillment Lines` 列表 + `Orchestration Plan` 任务树 + `View Fulfillment Details` 弹窗表达「一单多线、每线多任务」 |
| 共性 | 列表 + 数量列 + 下钻，**不是图形化 flow 图** | 未见 OM 的官方图形化 Document Flow 页面 |

**结论**：头部产品的「单据流」首先是一张**带数量列的台账**，而不是画布。这与本项目「边 = 数量关系」的本体一致。

#### 4.1.2 从上游生成下游

| 场景 | 产品动作 | 交互要点 |
|---|---|---|
| 申请 → PO | **Process Requisitions**（文档构建器） | 多选申请行 → 按分组规则生成一张或多张 PO；可指定供应商、采购员等目标头字段 |
| 收货 | **Create Receipt** / **Add to Receipt** | 既支持新建收货单，也支持**向既有收货单追加行**；数量默认填满未收量，可改小；受 overreceipt tolerance 约束 |
| 订单 → 发运 / 开票 | 编排（Orchestration）自动派生 | 用户不直接「选行生成」，而是由编排计划推进 |
| 订单复制 / 拆行 | **Copy Sales Orders** / **Split Order Lines** | 拆行时 `Ordered Quantity` 守恒：拆出量之和 = 原行量 |

**结论**：生成下游的输入是「一组上游行 + 数量 + 目标（新建/追加）」，与 §5 设计一致；「追加到既有单据」是**一等公民**，不是边缘场景。

#### 4.1.3 可用数量

- 可用（未结）数量**实时计算**，未做物化字段。
- 数量可**改小**（部分生成），不可超过可用量。
- 超过容差（如 overreceipt tolerance）才拒绝。

**结论**：`open_qty` 实时算 + 请求期校验，不新增物化列（见 D-10）。

#### 4.1.4 取消 / 关闭 / 红冲 / 退回

| 产品 | 语义 | 对上游量的影响 |
|---|---|---|
| OM **Cancel Line** | 置数量与金额为 0，释放额度 | 释放 |
| OM 限制 | 已发运 / 待开票 / 已关闭的行**禁止取消** | 只能走 **Return Sales Order**，`Return Qty ≤ 原订量 − 历次退货量` |
| Procurement **Cancel** | 取消未履行需求 | 释放；是否连带取消申请行由 `Cancel Unfulfilled Demand` 决定 |
| Procurement **Close for Receiving** | 停止收货，已收不受影响 | 未收部分不再允许生成收货 |
| Procurement **Close for Invoicing** | 停止开票 | 不影响收货 |
| Procurement **Finally Close** | 终态关闭 | 全部动作停止 |
| Procurement `Cancel Unfulfilled Demand` | `Never / Always / Optional` | `Always` 时申请行连带取消**并可再次转 PO** |

**结论**：
- 「取消」与「关闭」不是同义词；取消释放额度，关闭只封口不释放。
- 已过账/已执行的下游不能物理删除关系，只能走**冲销/退回**（本项目对应 `reverse_edge` / `compensate_edge` / `red_ink_edge`）。
- 上游取消需要**显式策略**（是否连带、是否允许）。

#### 4.1.5 未找到官方明文的点

- OM 的图形化 Document Flow 页面。
- 直接编辑「已生成数量」字段（产品用「可用量 + 本次量」表达，而非改历史边）。
- Quote → Order 的直接推单动作（按订单复制/拆分理解）。

**对本项目的含义**：不设计「编辑历史边数量」，只设计「本次生成量」；历史修正只走冲销。

### 4.2 其他头部产品（简要）

| 产品 | 机制 | 可借鉴点 |
|---|---|---|
| SAP SD | `VBFA` 文档流表记录单据间关系；部分交货（partial delivery）允许多次交付 | 关系表 + 多次部分交付；数量在行项目上累计 |
| Dynamics 365 SCM | 销售行上维护 `Delivered / Invoiced / Remaining` 数量；支持 delivery schedule 多次交货 | 「剩余量」是行上的派生读模型，不是独立单据 |

### 4.3 对标结论 → 设计决策

| # | 决策 | 依据 |
|---|---|---|
| D-01 | 一期做「数量台账 + 下钻」，**不做图形画布** | Oracle 三处均为列表 + 数量列；画布放 P3 可选 |
| D-02 | 读模型统一为「候选上游行 + quantity / consumed / open」 | Requisition Life Cycle、Fulfillment Lines |
| D-03 | 写模型统一为「一批源行 → 一个目标」，支持 create 与 append | Process Requisitions、Add to Receipt |
| D-04 | 本次生成量**可编辑**，默认填满 open_qty，校验 `0 < qty ≤ open_qty` | 部分生成/改小是常态 |
| D-05 | 头行模式沿用 §14.4「一源行一目标行」，不做同单多行 | 现有引擎约束，避免静默吞量 |
| D-06 | `cancel`（未过账）→ 关系层 `reverse_edge`；已过账 → 冲销/补偿，不物理删边 | OM Cancel vs Return；Procurement Cancel vs Close |
| D-07 | `close` 只封口，**不释放** open_qty；若要释放必须显式「取消未履行量」 | Procurement 的 Close / Cancel 区分 |
| D-08 | 幂等键查询必须排除 `status='reversed'` 的边 | 否则取消后无法对同一目标重新生成 |
| D-09 | UI 元数据驱动，两个入口（上游先行 / 下游先行）共用同一组件 | 与规则收敛 Spec §13 SSOT 一致 |
| D-10 | `open_qty` 实时聚合，不新增物化列 | Oracle / SAP / D365 均为实时或行上派生 |

### 4.4 元数据驱动头部平台横向对标

> 调研口径：厂商官方开发者文档 / 架构文档 / 产品资料页。调研日期 2026-11-08。
> 目的：确认「元数据驱动」在头部企业应用中的**共同骨架**，避免本项目只做局部配置化。

#### 4.4.1 平台机制对照

| 平台 | 元数据载体 | 关键机制 | 对本项目的启示 |
|---|---|---|---|
| **Salesforce** | Universal Data Dictionary（UDD）：`MT_Objects` / `MT_Fields` 等 | 多租户 + 元数据驱动；表单、报表、工作流、权限、业务逻辑、甚至表/索引定义均为元数据；Metadata API 以 `CustomObject` / `CustomField` / `Profile` / `PermissionSet` 声明式部署 | 元数据是**一等公民**：对象、字段、权限、UI、逻辑读同一份定义；字段元数据含类型/索引/顺序 |
| **Workday** | Data Object Model：Business Object = 实例 + 字段 + 关系 | 交付字段 vs 自定义字段；纵向继承 + 横向 Related BO；Extend 的 model component BO 可用可视化或 JSON 定义，**自动获得 RDS 报表数据源 + 完整 REST API + 独立安全**；BPF 是 "if this, then that" 引擎，支持步骤条件/路由/审批链 | **对象即服务**：声明一个对象，平台自动补齐 API/报表/权限；业务过程用声明式步骤条件，不写代码 |
| **ServiceNow** | Table Dictionary（`sys_*` 表、列、字典覆盖）+ 策略表 | UI Policies（前端显隐/必填/只读）vs Data Policies（服务端，任何入口都生效）vs Business Rules（服务端复杂逻辑）；表可继承（`task`）、按 scope 覆盖 | **策略按执行面分层**：界面策略 / 数据策略 / 业务规则各司其职，禁止把服务端校验只写在前端 |
| **NetSuite** | SuiteBuilder：自定义记录/字段/表单/事务 + SDF | 点击式建模，自定义与标准记录同构；官方强调 customization 随版本升级自动保留（"never version lock"） | **扩展与基线分离**：自定义内容升级安全，不修改基线代码 |
| **SAP（RAP/CDS）** | CDS 视图 + 注解 + Metadata Extension | interface view / consumption view 分层；`@UI` 注解与模型分离；`@Metadata.allowExtensions: true` 允许扩展；Key User Extensibility 可在标准 BO 上加自定义字段并配 Value Help | **模型 / 展现 / 扩展三层分离**：UI 注解不污染核心模型，扩展单独一层 |
| **Oracle Fusion / EBS** | Flexfields（DFF/EFF）+ 标准字段分类 | DFF 分全局与上下文相关；EFF 用**独立扩展表**而非基表 `ATTRIBUTEx` 列；标准字段沿用应用定义的安全，扩展字段需显式分类与治理 | **扩展字段的物理策略与治理**：小量用附加列，大量用扩展表；扩展字段必须纳入安全与分类 |
| **Dynamics 365 F&O** | 模型 + 扩展程序集 + Data Entity | 扩展编译为独立程序集，禁止 overlayering（对比 AX 2012）；Data Entity 暴露 OData | **可组合模型**：扩展不改基线，按模型引用组装 |

#### 4.4.2 五个共性模式

| # | 共性模式 | 头部做法 | 本项目现状 |
|---|---|---|---|
| M-01 | **单一元数据真源** | Salesforce UDD、Workday Object Model、ServiceNow Dictionary | 已有 BO YAML + 规则中心 + 视图元数据，但单据流规则在 DB、UI 入口未声明，仍有三处分散（规则收敛 Spec §13 正在收敛） |
| M-02 | **对象即服务** | Workday 自定义 BO 自动得 RDS + REST + 安全；Salesforce Metadata API | 自定义 BO 目前不自动获得派生服务/API，需按域手写 service（本 Spec §6 要补的正是这层） |
| M-03 | **声明式分层** | SAP：模型 / 注解 / 扩展；ServiceNow：UI / Data / Business 策略 | 前端校验、`field_policy`、`RuleEngine` 三层边界未显式定义，易出现「只在前端校验」 |
| M-04 | **扩展与基线分离、升级安全** | NetSuite SDF、SAP Metadata Extension、D365 extension assembly | 单据流规则已要求走配置数据、禁止迁移写业务分支（FR-006），方向一致；视图入口尚未纳入 |
| M-05 | **展现层零业务常量** | Salesforce 页面布局/记录类型均为元数据；SAP `@UI` 注解 | 规则中心已做到（§13.3 F-13-05/07）；单据流 UI 尚为空白，本 Spec §9 要求同样标准 |

#### 4.4.3 新增设计决策

| # | 决策 | 依据 |
|---|---|---|
| D-11 | 单据流的**入口、列、动作、标签、可编辑列**全部进元数据；Vue 组件零业务常量 | M-01 / M-05；Salesforce 页面布局、SAP `@UI`、规则中心既有标准 |
| D-12 | **对象即服务**：BO 一旦声明 `doc_flow_entry` + 规则，即自动获得 `/sources` `/derive` 与权限校验，不要求每域手写 service | M-02；Workday Extend 的 RDS + REST + 安全自动生成 |
| D-13 | 声明式分层固定为四层：**模型**（BO/边/规则）→ **行为**（派生/冲销/校验）→ **展现**（视图元数据）→ **扩展**（自定义字段/对象）；代码只兜底算法、集成、安全 | M-03；SAP RAP 分层、ServiceNow 策略三分 |
| D-14 | 扩展内容（规则、视图、入口）**只进配置层**，不得写进迁移脚本的业务分支；升级以「配置覆盖」而非「改基线」实现 | M-04；NetSuite / SAP / D365 的升级安全模式；沿用 FR-006 |
| D-15 | 策略按执行面三分：**UI 策略**（前端显隐/必填/只读）、**数据策略**（服务端校验，任何写入入口都生效）、**业务规则**（跨对象编排）；服务端校验为唯一权威 | ServiceNow UI Policies / Data Policies / Business Rules；避免前端校验被绕过 |
| D-16 | 自定义字段的物理策略与治理：少量用附加列（DFF 式），大量/复杂用扩展表（EFF 式）；扩展字段必须声明分类与安全等级 | Oracle DFF/EFF；避免基表无限加列 |

#### 4.4.4 对标后的差距结论

1. **我们缺的不是"元数据"概念，而是"元数据覆盖面"**：BO 与规则已元数据化，但「单据流入口 + 生成动作 + 目标表单」尚未声明，导致每个域都要写前端与 service。
2. **我们缺"对象即服务"的自动推导**：头部平台声明对象即得 API/报表/权限；我们需在 `DocFlowService` 上做第一次收敛，证明该模式可复制到其他通用能力。
3. **我们缺执行面分层约束**：若不明确「前端策略 ≠ 数据策略」，后续每个新 UI 入口都会重复实现校验。
4. **升级安全已有基础**：FR-006 的「规则进配置、不进迁移」与头部做法一致，本 Spec 只需把 UI 入口也纳入同一约束。

---

## 5. 能力模型

### 5.1 三个能力域

```
读：候选上游              写：生成/追加              状态：取消/冲销/关闭
┌──────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ list_sources │ ───► │ derive           │ ───► │ cancel/reverse   │
│ qty/consumed │      │ create | append  │      │ close            │
│ /open        │      │ 批量 + 逐行数量   │      │ 影响 open_qty    │
└──────────────┘      └──────────────────┘      └──────────────────┘
```

### 5.2 不变量

| # | 不变量 | 校验点 |
|---|---|---|
| I-01 | 对任意源行、任意 `pool`：`consumed_qty ≤ 源行数量` | 写事务内 Σ 校验（已有） |
| I-02 | 本次写入后 `consumed_qty + qty ≤ 源行数量` | 服务层预校验 + 引擎兜底 |
| I-03 | 每条 `active` 边恰好对应一个目标行（单表模式）或一个目标明细行（头行模式） | 边表 7 元组 + 外键 |
| I-04 | `reversed` 边不计入 `consumed_qty`，也不参与幂等命中 | 查询条件 |
| I-05 | 批量派生整批成功或整批回滚 | `derive_batch` 单事务 |
| I-06 | 目标单据已关闭/已取消时不得 append | 服务层校验 |

---

## 6. 服务层契约

### 6.1 模块与依赖

新建 `meta/services/doc_flow_service.py`：

```
DocFlowService
  ├─ list_rules(source_bo=None, target_bo=None) -> list[RuleDescriptor]
  ├─ list_sources(rule_id, filters, page, page_size) -> Page[SourceRow]
  ├─ derive(rule_id, sources, target, derived_by) -> DeriveBatchOutcome
  ├─ list_edges(source_bo, source_id, source_item=None) -> list[EdgeView]
  └─ (内部) _assert_quantity / _resolve_target / _map_errors
```

依赖：`doc_flow_rule_store.get_rule`、`doc_flow_batch_engine.derive_batch`、`doc_flow_derive_engine._consumed_in_pool`（或抽为公开 `consumed_qty()`）。

### 6.2 `list_sources`

输入：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `rule_id` | str | 是 | 规则唯一键 |
| `filters` | dict | 否 | 源 BO 可筛选字段（等值 / 范围），由元数据白名单约束 |
| `include_zero_open` | bool | 否 | 默认 `false`，过滤掉 `open_qty <= 0` |
| `page` / `page_size` | int | 否 | 默认 1 / 50，上限 200 |

输出行：

| 字段 | 说明 |
|---|---|
| `source_id` / `source_item` | 源行标识 |
| `quantity` | 源行数量（来自 `rule.source_qty_field`） |
| `consumed_qty` | 该 `pool` 净消耗 |
| `open_qty` | `quantity − consumed_qty` |
| `display` | 源行展示字段（按规则声明的 `display_fields`） |
| `split_key_values` | 该行 `split_key` 取值，用于前端预览会拆成几张单 |

实现要点：

- 一条 SQL 完成「源表 LEFT JOIN 聚合」：按 `(source_bo, source_id, source_item, pool)` 聚合 `doc_flow_edges`，避免 N+1。
- 需要索引：`CREATE INDEX idx_doc_flow_edges_src ON doc_flow_edges(source_bo, source_id, source_item, pool, status, quantity_sign)`。
- 字段白名单来自规则/BO 元数据，禁止拼接未声明字段。

### 6.3 `derive`

输入：

```json
{
  "rule_id": "so_line_to_delivery",
  "sources": [
    {"source_id": 1001, "source_item": "line", "quantity": 30},
    {"source_id": 1002, "source_item": "line", "quantity": 10}
  ],
  "target": {
    "mode": "create",
    "bo": "delivery",
    "id": null,
    "data": {"ship_to": "上海", "carrier": "SF"}
  },
  "derived_by": "admin"
}
```

- `mode=append` 时 `target.id` 必填（单表模式为目标行 ID；头行模式为单头 ID + 可选 `target.data` 覆盖头字段）。
- `sources[].quantity` 缺省 = 该行 `open_qty`（即全部生成）。
- 同一 `rule_id` 下 `sources` 内不得出现重复 `(source_id, source_item)`。

输出：

```json
{
  "target": {"bo": "delivery", "ids": [5001]},
  "created": [{"source_id": 1001, "target_id": 5001, "target_item": "9001", "quantity": 30, "edge_id": "..."}],
  "replayed": [{"source_id": 1002, "target_id": 5001, "edge_id": "..."}],
  "totals": {"requested": 40, "written": 40, "replayed": 0}
}
```

语义：

- `create`：调用 `derive_batch(...)`，`split_key` 决定目标单据数量；返回全部新建目标 ID。
- `append`：`split_key` 必须为空或与既有单据一致；头行模式传 `head_overrides={'id': target.id}`。
- `replayed`：宽松/精确幂等命中，零新增；计入结果但不计入 `written`。
- 任一源行校验失败 → 整批拒绝（不写入任何数据）。

### 6.4 校验顺序（必须在事务内）

1. 规则存在且 `status='active'` → 否则 `DOC_FLOW_RULE_NOT_FOUND`。
2. `mode` 合法；`append` 时目标存在且未关闭 → 否则 `DOC_FLOW_TARGET_NOT_FOUND` / `DOC_FLOW_TARGET_CLOSED`。
3. 源行存在 → 否则 `DOC_FLOW_SOURCE_NOT_FOUND`。
4. `quantity > 0` 且为有限数 → 否则 `DOC_FLOW_QTY_INVALID`。
5. `quantity ≤ open_qty` → 否则 `DOC_FLOW_QTY_EXCEEDED`（返回 `open_qty` 供前端修正）。
6. 头行模式同单异量 → 引擎抛 `HEAD_LINE_MULTI_NOT_SUPPORTED`。
7. 权限：调用方对源 BO 有读权限、对目标 BO 有新建/更新权限 → 否则 `DOC_FLOW_PERMISSION_DENIED`。

### 6.5 错误码

| 错误码 | HTTP | 含义 |
|---|---|---|
| `DOC_FLOW_RULE_NOT_FOUND` | 404 | 规则不存在或未生效 |
| `DOC_FLOW_SOURCE_NOT_FOUND` | 404 | 源行不存在 |
| `DOC_FLOW_TARGET_NOT_FOUND` | 404 | append 目标不存在 |
| `DOC_FLOW_TARGET_CLOSED` | 409 | 目标已关闭/取消，不可追加 |
| `DOC_FLOW_QTY_INVALID` | 400 | 数量非正/非数 |
| `DOC_FLOW_QTY_EXCEEDED` | 409 | 超过未结量，附 `open_qty` |
| `HEAD_LINE_MULTI_NOT_SUPPORTED` | 409 | 头行模式同单异量（沿用 v2.2） |
| `DOC_FLOW_SPLIT_KEY_FIELD_MISSING` | 400 | 源行缺 split_key 字段 |
| `DOC_FLOW_PERMISSION_DENIED` | 403 | 权限不足 |
| `DOC_FLOW_TARGET_MODE_INVALID` | 400 | mode 非法或与规则模式不匹配 |

### 6.6 事务与并发

- 全部写操作在 `app_ds` 单事务内完成；批量失败整批回滚。
- 并发：SQLite 下使用 `BEGIN IMMEDIATE` 获取写锁；服务层在事务开始处对涉及源行做一次 `open_qty` 重算，避免「先读后写」超卖。
- 不做跨库事务；平台库（规则）读取在事务外完成。

---

## 7. API 设计

新建 `meta/api/doc_flow_api.py`，`Blueprint('doc_flow', __name__, url_prefix='/api/v2/doc-flow')`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/rules?source_bo=&target_bo=` | 列出可用规则（供 UI 选择生成方向） |
| GET | `/sources?rule_id=&page=&page_size=&include_zero_open=&<筛选>` | 候选上游 + `open_qty` |
| POST | `/derive` | 批量生成/追加 |
| GET | `/edges?source_bo=&source_id=&source_item=` | 某源行的下游台账（含状态） |
| GET | `/edges?target_bo=&target_id=` | 某目标单据的上游来源（追溯） |

统一响应信封沿用现有 BO API（`{code, message, data}`）；错误码见 §6.5。

权限：

- `/rules`、`/sources`、`/edges` 需要登录 + 源/目标 BO 读权限。
- `/derive` 需要目标 BO 的 `create`（create 模式）或 `update`（append 模式）权限。
- 审计：`derived_by` 取当前登录用户，不接受前端伪造。

---

## 8. 取消 / 红冲 / 关闭语义

### 8.1 语义矩阵（目标形态）

| 下游动作 | 关系层操作 | `open_qty` 影响 | 前置条件 |
|---|---|---|---|
| 取消（未过账） | `reverse_edge` 该目标全部边（`edge_kind='reversal'`） | 释放 | 目标无下游消耗 |
| 取消（已过账） | 拒绝；要求先走冲销/退货 | 不释放 | 返回 `DOC_FLOW_TARGET_POSTED` |
| 红冲 | `red_ink_edge`（同 `pool`，`quantity_sign='red'`） | 净释放 | 红冲量 ≤ 原边量 |
| 退货/补偿 | `compensate_edge` | 净释放 | 补偿量 ≤ 原边量 |
| 关闭 | 仅改目标 status | **不释放** | — |
| 上游取消 | 检查该源行 `consumed_qty`，>0 则拒绝或按策略连带 | 视策略 | TBD-41 |
| 上游关闭 | 标记源行不可再派生 | 不释放 | — |

### 8.2 现状差异与改造点

| # | 现状 | 改造 |
|---|---|---|
| C-01 | `shipment_service.cancel` 只改 status | 未过账时按边 `reverse_edge`；已过账时拒绝并提示 |
| C-02 | `receipt_service.cancel` 同上 | 同上 |
| C-03 | `transfer_order_service.cancel` 同上 | 同上 |
| C-04 | `close` 不改边 | 保持（语义正确），补充「关闭 ≠ 释放」提示文案 |
| C-05 | `_find_edge_by_key` / `_find_edge_loose` 不筛 status | 增加 `AND status='active'`，使取消后可对同一目标重新生成 |
| C-06 | 取消链路的幂等重放会把已冲销边当命中 | 由 C-05 一并修复 |

### 8.3 为什么不能物理删边

- 审计要求：关系变更必须可追溯（谁在何时释放了哪条关系）。
- 对账要求：`doc_flow_reconcile` 依赖全量边（含 reversed）判断守恒。
- 因此统一用 `status='reversed'` + `edge_kind` 表达，不 `DELETE`。

---

## 9. 元数据驱动 UI

### 9.1 视图元数据

在单据流规则或 BO YAML 上声明入口（具体载体见 TBD-44）：

```yaml
doc_flow_entry:
  id: so_line_to_delivery
  rule_id: so_line_to_delivery
  source_bo: sales_order_line
  target_bo: delivery
  label: 生成交货单
  source_columns: [order_no, item_name, ship_to, quantity, consumed_qty, open_qty]
  editable_column: quantity          # 本次生成量
  display_fields: [order_no, item_name]
  allow_append: true
  append_label: 追加交货行
```

前端不得硬编码 `so_line_to_delivery` 之类的业务键；入口列表、列 key、标签均来自元数据（与规则收敛 Spec §13.3 F-13-05 一致）。

### 9.2 两个入口

**入口 A：上游先行（批量生成）**

```
源单据列表页（MetaListPage）
  └─ 多选源行
      └─ 批量操作「生成下游」（ActionExecutor 读取 doc_flow_entry）
          └─ DocFlowSourcePicker 弹窗
              ├─ 已选行表格：source 展示字段 + quantity + consumed + open + 本次量（可编辑）
              ├─ 分组预览：按 split_key 显示「将生成 N 张单据」，可展开看每张的行
              ├─ 目标头字段表单（来自目标 BO 的 create 表单元数据）
              └─ 提交 → POST /derive (mode=create)
```

**入口 B：下游先行（追加）**

```
目标单据详情页（DetailPage）
  └─ 明细行工具栏「追加行」
      └─ DocFlowSourcePicker 弹窗（target.mode=append, target.id=当前单据）
          ├─ 查询候选上游（GET /sources，可按 split_key 字段过滤为与当前单据一致）
          ├─ 多选 + 每行编辑本次量
          └─ 提交 → POST /derive (mode=append)
```

### 9.3 组件拆分

| 组件 | 职责 | 复用 |
|---|---|---|
| `DocFlowSourcePicker.vue` | 选上游 + 编辑本次量 + 分组预览 | `SearchHelpDialog`（multiple）、`el-table` 行内编辑 |
| `DocFlowDerivePanel.vue` | 承载入口 A/B 的弹窗容器与提交 | `AppModal`、`AppButton` |
| `DocFlowTracePanel.vue` | 详情页「单据流」页签：上游来源 / 下游去向 / 状态 | `AppTabs`、`el-table` |
| `docFlowService.ts` | API 封装 + 错误码到提示的映射 | 现有 service 层 |

禁止：

- 在组件内写死规则名、BO 名、列 key。
- 用 `el-button` / `el-dialog`（必须 `AppButton` / `AppModal`）。
- 任何 Emoji。

### 9.4 交互规则

| # | 规则 |
|---|---|
| U-01 | 「本次生成量」默认 = `open_qty`；用户可改小，不可改大（输入框上限 = `open_qty`） |
| U-02 | `open_qty <= 0` 的行默认不出现；若通过筛选带入，置灰并标注「已结清」 |
| U-03 | 提交前显示汇总：`选中 N 行 / 合计 M / 将生成 K 张单据` |
| U-04 | 提交失败回填服务端错误：`DOC_FLOW_QTY_EXCEEDED` 时把该行标红并显示最新 `open_qty` |
| U-05 | 重放行在结果中标注「已存在，未新增」，不报错 |
| U-06 | append 入口默认按当前单据的 split_key 值过滤上游，避免拆到别的单 |

---

## 10. 非功能需求

| # | 需求 | 验收方式 |
|---|---|---|
| N-01 | 批量派生原子性：任一失败整批回滚 | 契约测试断言边/行/头零新增 |
| N-02 | 并发不超卖：两请求同时生成同一源行，合计不得超过 `quantity` | 并发测试（线程/进程） |
| N-03 | 查询性能：`/sources` 在 10 万边、10 万源行下 P95 < 500ms | 压测脚本 |
| N-04 | 审计：每次派生记录 `derived_by` / `derived_at`；取消记录冲销边 | 查询边表 |
| N-05 | 权限：无目标 BO 写权限时 `/derive` 返回 403 | 权限测试 |
| N-06 | 兼容：现有 5 条业务链路行为不变 | 等价性回归 |
| N-07 | 测试唯一入口 `python d:\filework\test.py` | CI |

---

## 11. 验收标准

### 11.1 服务层

1. 源行 `quantity=100`，已生成 60 → `list_sources` 返回 `open_qty=40`。
2. `derive` 传 `quantity=30` → 成功，`open_qty=10`。
3. 再传 `quantity=20` → `DOC_FLOW_QTY_EXCEEDED`（附 `open_qty=10`），零写入。
4. 传 `quantity=0` / `-1` / `null` → `DOC_FLOW_QTY_INVALID`。
5. 多选 3 行，`split_key` 相同 → 生成 1 张目标单据、3 条明细行、3 条边。
6. `split_key` 不同 → 生成 3 张目标单据。
7. `append` 到既有单头 → 明细行 +N、边 +N，单头不新增。
8. 同一批重复提交 → 全部 `replayed`，边/行零新增。
9. 头行模式同源行同单头异量 → `HEAD_LINE_MULTI_NOT_SUPPORTED`，零新增（沿用 v2.2 契约测试）。

### 11.2 状态语义

10. 未过账下游 `cancel` → 边变 `reversed`，`open_qty` 恢复。
11. 已过账下游 `cancel` → 拒绝，`open_qty` 不变。
12. 红冲 → `consumed_qty` 净减少，`open_qty` 恢复。
13. `close` → `open_qty` 不变。
14. 取消后对同一目标再次生成 → 成功（幂等键排除 reversed 边）。

### 11.3 API / UI

15. `GET /api/v2/doc-flow/sources` 返回分页结构与 `open_qty`；非法筛选字段返回 400。
16. `POST /api/v2/doc-flow/derive` 错误码与 §6.5 一致。
17. 入口 A：多选 → 弹窗 → 改量 → 提交 → 目标单据生成，页面可跳转。
18. 入口 B：详情页追加 → 明细行新增，`open_qty` 相应减少。
19. 详情页「单据流」页签展示上游来源与下游去向（含状态）。
20. 全部 UI 文案/列/入口来自元数据；改 YAML 即可改标签与列，不改 Vue。

### 11.4 回归

21. `python d:\filework\test.py --all` 通过；`--failed` 串行二次确认无并发假失败。
22. 现有 5 条业务链路（采购申请→PO、销售→发货、收货、调拨、发货过账）行为等价。

---

## 12. 分期落地

| 期 | 内容 | 产出 |
|---|---|---|
| **P0** | 服务层 `DocFlowService` + `/rules` `/sources` `/derive` + 边表索引 + 契约测试 | 后端可用，前端未接 |
| **P1** | 取消语义修正（C-01~C-06）+ 幂等排除 reversed + 回归 | 额度释放正确 |
| **P2** | 前端两入口（A/B）+ 详情页「单据流」页签 + 视图元数据 | 用户可用 |
| **P3** | 图形化 flow 视图（可选）、跨规则多目标、分摊策略、上游取消策略 | 增强 |

P0 与 P1 可并行（P1 改的是既有 service，P0 是新增文件）；P2 依赖 P0 的 API 契约冻结。

---

## 13. TBD

| # | 问题 | 候选 | 建议 |
|---|---|---|---|
| TBD-40 | 未过账取消是否自动 `reverse_edge`，还是要求二次确认 | 自动 / 确认 | 默认自动，配置项可关 |
| TBD-41 | 上游取消时若已有下游消耗 | 拒绝 / 连带冲销 / 仅标记 | 默认拒绝，返回 `DOC_FLOW_SOURCE_CONSUMED` |
| TBD-42 | 同一源行匹配多条规则时的目标选择 | 全部可选 / 互斥 | 暂定「全部可选」，UI 让用户选规则 |
| TBD-43 | `open_qty` 是否物化 | 实时 / 物化 | 实时（D-10） |
| TBD-44 | `doc_flow_entry` 元数据落 BO YAML 还是独立 `doc_flow_view.yaml` | 两者 | 优先 BO YAML，复杂视图再抽独立文件 |
| TBD-45 | 单表模式 append 时是否允许改目标行数量 | 允许 / 禁止 | 禁止（改量走新边或冲销） |
| TBD-46 | 批量生成的 `split_key` 分组预览是否强制 | 强制 / 可选 | 强制，避免误建多单 |
| TBD-47 | 自定义字段物理策略（DFF 附加列 vs EFF 扩展表）的切换阈值与治理流程 | 阈值可配 / 固定 | 先定为「每 BO ≤ 10 个扩展字段用附加列，超出走扩展表」，纳入元数据校验 |

---

## 14. 附录：现有代码证据

| 证据 | 位置 |
|---|---|
| 派生入口 | `meta/core/doc_flow_derive_engine.py::derive` |
| 批量派生 | `meta/core/doc_flow_batch_engine.py::derive_batch`（`exact_idem = not two_level`，`head_overrides['id']` 支持 append） |
| 消耗公式 | `meta/core/doc_flow_derive_engine.py::_consumed_in_pool` |
| 幂等键（待修） | `meta/core/doc_flow_derive_engine.py::_find_edge_by_key`（缺 `status='active'`） |
| 宽松幂等（头行） | `meta/core/doc_flow_derive_engine.py::_find_edge_loose`（返回三元组，异量拒绝） |
| 冲销入口 | `meta/core/doc_flow_reversal.py::reverse_edge / red_ink_edge / counter_edge / compensate_edge` |
| 挂边 | `meta/core/doc_flow_attach.py::attach_edge` |
| 规则存储 | `meta/core/doc_flow_rule_store.py::get_rule / upsert_rules / set_rule_status` |
| 表结构 | `meta/core/doc_flow_schema.py::ensure_doc_flow_edge_tables`（明确不做 open_qty 视图） |
| 取消（不释放） | `meta/services/shipment_service.py:623-636`、`receipt_service.py:694-710`、`transfer_order_service.py:643-667` |
| 硬编码链路 | `meta/services/requisition_po_conversion.py:160-164`、`shipment_service.py:178-190`、`receipt_service.py:1200-1224` |
| 前端可复用 | `src/components/common/MetaListPage/MetaListPage.vue`（多选 / 行内编辑）、`src/components/common/SearchHelpDialog.vue`（multiple）、`src/components/bo/ActionExecutor.vue` |
| 头行模式约束 | 规则收敛 Spec v2.2 §14.4 / §14.7；契约测试 `meta/tests/test_doc_flow_batch.py::test_same_source_same_head_different_qty_rejected` |