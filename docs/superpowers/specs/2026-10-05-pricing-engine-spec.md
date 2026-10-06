# 定价引擎（Pricing Engine）Spec + RFC

> **版本**：v1.6 | **日期**：2026-10-06 | **状态**：**待确认**（**全部待拍板项已清零** —— v1.4 拍板 D18 补第四消解范式 `weighted` / D19 单位换算归事实源取值阶段；v1.5 拍板 D16 费用归属 / D17 重算节奏 / D20 多账簿不纳入 / D21 结果能力接口本期不做 / D22 + D23 改价必填原因（Override 复用 `adjustment`）/ D24 输出映射改为字段约定。**v1.6 新增 §7B 三件套通用性分析（代码级取证）并据此收窄 FR-003 / FR-004 职责边界 + 切出 T0 先行批次**；**T0/T1/T2 已交付、T1-5 定价 API 层（IF-001/002/003）已落地并结项 TBD-3**；残留 TBD-4~TBD-7 为实施期事项；TBD-10 后置 P6；TBD-12 / TBD-13 保留待议；**TBD-14 / TBD-15 / TBD-16 为 v1.6 新登记**）
> **三件套通用性结论（v1.6 拍板，详见 §7B）**：因子目录 / 匹配键表 / 查找序列**不是三个定价专表，而是「因子 / 键 / 取数计划」三原语的一种实例化**——通用的是原语，不是表。**通用点已由代码取证**：平台内**四处**（数据权限 / 属性确定 / 派生 / 文档流）自发实现了同一套三问，**无一通用**。据此收窄：`key_schema` 只留 `key_fields[]`、`lookup_sequence` 只留槽位顺序（`exclusive` 下沉为 `rate_record.hit_policy`）、`factor_catalog` **不再重复 `MetaField` 的 `data_type`/`aliases`**（消除双重真相源）。**不新增对象数量。**
> **配置载体结论（v1.6 拍板，详见 §7C）**：**真正分岔不是"载体"，而是「谁在什么时候写 SSOT」。** 拍板走**「双装载并存」**——**开发态预置**（本期 T0，git 即审计）+ **运行态自举**（方向采纳）**两条路径都产出同一份 yaml**，汇入同一条 `register_from_directory` → `schema_generator` 管线，**不存在两条 SSOT**。**行业基线即运行态**：SAP **V/03 就是顾问勾选字段、生成条件表的事务码**（研究稿 S20/S47）。**关键修正**：`MetaObject` **装不下** yaml 的 4 块（`audit` / `ui_view_config` / `category_config` / `import_export`，§7C.1.1）——故它是**建表中间产物**而非 SSOT，**yaml 才是唯一 SSOT**。**本期禁止结构变更**（C-T0-12，顾问只能选既有因子组合；增删 PK 本身即数据迁移需求）。**EAV 泛化模型不适合因子/键/费率记录**（`keys{}` 组合匹配需索引，JSON 做不到），但**适合"少而固定"的配置**（`permission_rules_v2` 已验证）。
> **命名声明（v1.3 拍板）**：**元模型层一律使用领域中立名**——费率类型 / 查找序列 / 计算过程 / 费率记录 / 计算结果…；**SAP 术语（条件类型 / 存取序列 / 定价过程 / 条件记录 / 定价结果）降为"业务别名"，只出现在 [§9.3.1](#931-对象模型数据模型) 的"业务别名"与"溯源"列**，不再作主名。通用化只参数化**三个正交轴**（① 计算基来源 ② 率载体 ③ 结果语义），**成本归集层与碳组织边界 / 合并层不属本引擎**（§1.4 N9）。
> **通用性外部验证（v1.4）**：**v2.0 跨域对撞**（研究稿 §4.9）——三轴在 Oracle **成本域**（`总成本 = 固定 + 变动[单位资源成本 × 消耗数量]`、`单位成本 = 总成本 ÷ 缩放数量`）与**碳域**（`排放量 = 活动数据 × 排放因子`）**逐字同构**；据此补入**第四消解范式 `weighted`**（Oracle 成本域 Sourcing Rule 分配百分比等三处）。**v2.1 Palantir 对照**（研究稿 §4.10）——**两条通用化路径的分野不在能力而在"谁承担域特有逻辑"**；本引擎走"元模型 + 参数化"，故 **N9 边界是这条路径的必要成本**。
> **关联文档**：
> - [2026-10-05-pricing-engine-research.md](./2026-10-05-pricing-engine-research.md)（**v2.1**，对标研究报告 —— **本 Spec 的唯一事实来源**）
> - [2026-10-02-rule-model-spec.md](./2026-10-02-rule-model-spec.md)（v1.3，属性确定 Spec；本 Spec 的对齐范式与上游接缝）
> - [2026-10-02-rule-model-research.md](./2026-10-02-rule-model-research.md)（v1.11；§10.4 判定"定价宜独立引擎"）
> - [2026-09-29-doc-flow-copy-control-research.md](./2026-09-29-doc-flow-copy-control-research.md)（下游消费方：复制时"带价 vs 重定价"）
> - [2026-09-30-object-model-guideline-plan-vs-fact.md](./2026-09-30-object-model-guideline-plan-vs-fact.md)（计划对象 vs 事实对象）

> **一句话**：`default` 规则回答"**填哪个价目表**"，`compute` 回答"**总额 = 数量 × 单价**"，**本引擎回答"这个单价 / 这行金额是怎么一层层算出来的"**。
>
> **本文档性质**：把研究稿（940+ 行对标）**收敛为可实施、可验收的需求规格**。研究稿讲"为什么/对标/边界"，本 Spec 讲"**要什么/对象长什么样/怎么分期/怎么验收**"。所有需求均可回溯到研究稿章节（Source 列）。

---

## 1. 背景与目标

### 1.1 背景

平台**目前没有定价引擎**——不是"弱"，是"没有"（研究稿 §2 代码级取证：全仓无 `*pricing*` 文件，`meta/core` 下 13 个 `*engine*.py` 中无定价引擎）。现状能力天花板：

- `MetaDefaultRule` 能按"客户 + 订单类型"**确定用哪张价目表**（`rate_table = PL_ZOR`），但**没有任何东西能把这张价目表算成一个价格**；
- `MetaComputation` 能算 `total_amount = qty × unit_price` 这类**尾算**，但算不了 `unit_price` **本身怎么来**；
- 单据行只有"放价格的格子"（`unit_price` / `net_price` / `total_amount`），**没有算价格的机器**。

上位文档 [规则模型研究](./2026-10-02-rule-model-research.md) 已判定：**定价是"同族里最复杂的一类"**（多层累加 / 互斥 vs 累加 / 冲突取优 / 值类型多样），**宜独立引擎**，不能再用属性确定规则表凑合。

**痛点**：一旦业务需要"客户 + 物料 + 数量 → 逐层得到净价（基价 → 折扣 → 附加费 → 税 → 运费）"，平台无任何机制承载；而头部六家（SAP / Oracle / Salesforce / D365 / Odoo / 金蝶）**骨架高度一致**（研究稿 §3、§4）：`价目表 + 条件规则 + 可配置计算序列 + 优先级/取优消解 + 可解释回放`。

### 1.2 业务目标

- **G1** 让"**逐层算出一个价格**"成为平台一等能力：一条**可配置的计算序列**，把一组因子算成一个金额（及小计明细），且**改配置不改代码**。
- **G2** 覆盖六家共性骨架的**六个必备件**（研究稿 §4）：① 价目表 ② 条件类型 ③ 存取序列 ④ 定价过程 ⑤ 取优/消解 ⑥ 可解释回放。
- **G3** 可解释：每次定价都能回答"**命中了哪一行、被谁否决、逐层小计、基准是什么**"（对标 Oracle Request Viewer / SF Price Waterfall / 金蝶取价日志）。
- **G4** 与单据链协同：明确"**搬价 vs 重算**""**按哪一版数量**"，且**已开票/已过账行不得隐式重定价**（红线）。
- **G5** **不重复造轮子**：复用既有条件内核、首个命中语义、安全表达式求值、`MetaComputation` 宿主，只补真正缺的三件——"**多层累加 + 多候选取优 + 条件记录（价目行）**"。

### 1.3 用户 / 涉众目标

| 角色 | 想要达成 |
|---|---|
| 业务配置人员（定价管理员） | 不写代码即可维护价目表 / 价目行 / 条件类型 / 定价过程 / 分摊规则 |
| 销售 / 开票人员 | 单据上能看到价格怎么来的（逐层明细），并可"查看计算过程" |
| 财务 / 成本 | 事后计划外费用能摊到业务单据行，去向（成本 / 费用）可配，追溯补差成对留痕 |
| 平台开发 | 一套"通用确定"元模型，未来可扩展伙伴 / 批次 / 输出 / 文本确定而不改引擎 |

### 1.4 本期目标 / 非目标

**本期目标（须交付）**：P1 单层取价 → P2 多层累加 + 回放 → P3 取优/互斥（研究稿 §7）。

**本期非目标（明确不做，边界登记见 FR-018）**：

- **N1** 选价目表 → 归 `default`（`MetaDefaultRule`）——**选价目表 ≠ 算价格**。
- **N2** 总额尾算（`total = qty × unit_price`）→ 归 `compute`（`MetaComputation`）。
- **N3** 跨单据 / 跨期间 **纯财务口径**的费用分摊（无"业务单据行"落点）→ 归待建 `allocation`。
- **N4** 限价校验（"净价不得低于限价"）→ 归 `validation`（`MetaValidation`）——定价只**产出** min/max 快照。
- **N5** **搬运动作本身** → 归 `doc_flow`（定价只**声明**策略 `price_mode`）。
- **N6** 采购侧（供应商 / PO）定价与**成本核算**（移动平均 / 标准价 / 价差取值算法）→ **D7 范围外**（研究稿 §4.7 只做费用对象与分摊模型设计）。
- **N7** 期货保值 / 风险管理 / 头寸 → 归 **CTRM / 风控**；**质检本身**（检验批 / 使用决策 UD / 质量通知）→ 归 **QMS**（定价只消费"质检结果 → 定价输入字段"这一层）。
- **N8** 在线配置 UI、规则版本化（首期不做，随元数据定义发布）。
- **N9 通用化边界（v1.3 拍板）**：元模型虽按"**确定 + 计算**"通用设计，但**只参数化三个正交轴**（① 计算基来源 ② 率载体 ③ 结果语义）；**成本归集层**（成本对象 / 成本构成拆分 cost component split / 价格控制：标准价 · 移动平均 · 价差）与**碳排放的组织边界 / 合并层**（GHG 组织与运营边界、合并口径）**不属本引擎**——引擎只承担"**量 × 率 × 多步**"的计算骨架（研究稿 N6、§4.8E）。

---

## 2. 需求类型总览

| 类型 | 编号段 | 说明 | 来源 |
|---|---|---|---|
| 业务需求 Business | §1.2 G1–G5 | 为什么需要定价引擎 | 研究稿 §2、§2.2 |
| 涉众需求 User | §1.3 | 配置 / 销售 / 财务 / 开发各角色诉求 | 研究稿 §4.6、§4.7 |
| 方案需求 Solution | §9.2 / §9.3 | 独立引擎 + 通用确定元模型 | 研究稿 §5、§8.2（D7） |
| 功能需求 FR | FR-001 … FR-018 | 逐条可验收行为 | 研究稿 §3–§7 |
| 非功能需求 NFR | NFR-001 … NFR-007 | 质量属性 | 研究稿 §5.1、§7 |
| 接口 / 集成需求 IF | IF-001 … IF-008 | 与既有引擎 / 单据 / 主数据的接缝 | 研究稿 §5.2、§6、§7 |
| 过渡 / 迁移需求 TR | TR-001 … TR-004 | 灰度、依赖补齐、回滚 | 研究稿 §6.1、§7 |

---

## 3. 功能需求（FR）

> **优先级约定**：Must = P0–P2（本期必须）；Should = P3–P4；Could = P4.5–P6（可后置）。
> **通用护栏**（适用于全部 FR）：① 已开票 / 已过账的行**不得隐式重定价**；② 重算**须显式触发且留痕**；③ 表达式一律走 `SafeExpressionEvaluator`（禁 `eval`）。

### FR-001 费率表与费率记录（Rate Table / Rate Record）—— 件①（业务别名：价目表 / 价目行·条件记录）

- **Description**：系统 MUST 提供**费率表 `rate_table`**（业务别名：价目表）与其**费率记录 `rate_record`**（业务别名：价目行 / 条件记录），作为"**率**"的库存——**价格、排放因子、作业费率、税率装在同一种载体里**。费率记录 MUST 携带：来自匹配键表的**键**、**值 / 费率**、**有效期**、**币种**、**计量单位 / 计量数量**、**阶梯**、**状态**。
- **Acceptance Criteria**：
  - 仅有 **`status = approved`**（审核态）的费率表参与取用（对标金蝶"仅审核态参与取价"）；
  - 费率记录支持逐行"键 + 值 + 有效期 + 币种 + 计量单位"落库，可被**查找序列**按键检索；
  - 跨币种费率记录可按汇率换算为单据币种（依赖 IF-008 汇率主数据）；
  - **载体中立（v1.3）**：同一 `rate_record` 靠所属 `rate_type` 区分"这是价格 / 因子 / 费率 / 税率"，**不为碳因子或作业费率另建表**。
- **Priority**：Must
- **Type Mapping**：Solution / Functional
- **Source**：研究稿 §4 件①、§4.2 第 2 层、§3.1.6（金蝶审核态）

### FR-002 费率类型（Rate Type：配置对象，非硬编码枚举）—— 件②（业务别名：条件类型 / 价格类型 / 因子类型）

- **Description**：系统 MUST 把**费率类型 `rate_type`**（业务别名：条件类型 / 价格类型 / 因子类型）落成**可维护的配置对象**（不是硬编码枚举）。硬编码的只是其**属性枚举**（费率类 / 计算类型 / 率载体）。
- **Acceptance Criteria**：
  - 费率类型字段至少含：`编码 / 名称 / 费率类 rate_class`（**枚举按过程类型扩展**：pricing 实例取 `{price, discount_surcharge, tax, freight, statistical}`）/ `计算类型 calc_type ∈ {percent, fixed, quantity, formula}` / **`rate_source ∈ {rate_record, external_quote, formula}`（率载体，v1.3 通用化轴②）** / 正负号 `sign` / 舍入规则 `rounding` / 互斥组 `exclusion_group` / 是否手动可录入 `manual_allowed` / 是否必填 `mandatory` / 是否统计 `statistical` / 查找序列引用 `lookup_sequence_id`（研究稿 §4.1 设计含义）；
  - 六家对标全部支持自建费率类型，本 FR 须满足"**自建即生效**"，改配置不改代码；
  - 与 D7"通用确定"一致：未来复用同表做伙伴 / 批次确定或碳排放核算时，只新增 `rate_class` 枚举值 / 新增 `rate_source` 取值，**不改表结构**。
- **Priority**：Must
- **Type Mapping**：Solution / Functional
- **Source**：研究稿 §4.1（含六家对标表）、§8 D7/§8.2、§8 D9

### FR-003 因子目录与匹配键表（Factor Catalog / Key Schema）—— 件①/③ 的前置键（业务别名：字段目录 / 条件表）

- **Description**：系统 MUST 提供**因子目录 `factor_catalog`**（业务别名：字段目录；哪些字段可当键，含事实源分类）与**匹配键表 `key_schema`**（业务别名：条件表；用哪些因子的**组合**做键）。
- **职责边界（v1.6 收窄 · 见 §7B.5 / C-T0-1 / C-T0-3）**：
  - `factor_catalog` **只**声明 `source_type` + `is_price_relevant` 两项**`MetaField` 不具备**的能力；**不得**重复声明 `data_type` / `aliases`（引用 `MetaField.field_type` / `semantics.aliases`），避免**同一字段两处真相源**（§7B.4 缺陷 3）；
  - `key_schema` **只**承载 `key_fields[]`（匹配维度）；**量级换算（`display_scale` / `numeric_field`）归 `rate_type`，阶梯基数（`scale_divisor`）与排除对象（`exclude_bo`）归 `rate_record`**（§7B.4 缺陷 1）。
- **Acceptance Criteria**：
  - 因子目录项含 `source_type ∈ {static, master, quality, measurement, market}`，使**质检 / 计量 / 外部报价**三类事实源字段与主数据字段**同权**（FR-015 前置）；
  - 匹配键表由因子目录中选字段组成，是费率记录"键"的定义来源；**键可被多个 `rate_table` 复用**（复用价值是本表存在的理由，若实施中从未复用则按 §7B.8 备选 D 废表 → TBD-14）；
  - 匹配键表 + 因子目录与 FR-002 费率类型**同批**交付（研究稿 §6.1 #10 定为 P0）。
- **Priority**：Must
- **Type Mapping**：Solution / Functional
- **Source**：研究稿 §4.2 第 1 层、§4.8D①、§6.1 #10、#27；**§7B 三件套通用性分析（代码级取证）**

### FR-004 查找序列与取数范式（Lookup Sequence：exclusive / additive）—— 件③（业务别名：存取序列）

- **Description**：系统 MUST 提供**查找序列 `lookup_sequence`**（业务别名：存取序列）：一条**有序查表列表**。**命中策略下沉到费率记录**（`rate_record.hit_policy`，v1.6）：序列只管"第几个槽位、用哪把键"，**"命中即停还是继续累加"由每条费率记录自带**。
- **职责边界（v1.6 · 见 §7B.4 缺陷 2 / §7B.5 / C-T0-2 / C-T0-4）**：
  - `lookup_sequence` **只**含 `code` / `name` / `steps[{seq, key_schema_id}]`，**不含 `exclusive`**；
  - **命中策略改由 `rate_record.hit_policy ∈ {exclusive, additive}` 承载**（默认 `exclusive`），对标 SAP **逐条条件自带** `%GET_VAL` 累加 / 首命中退出；
  - **消除后果**：支持"**第 1 槽累加 + 第 2 槽取优**"**无需整表复制序列**。
- **Acceptance Criteria**：
  - 默认语义 = **exclusive 首个命中**（对标 SAP 存取序列 Exclusive 标志、Odoo 首个、金蝶"命中即止"）；
  - 需**继续累加**时，在**该条费率记录**上显式置 `additive`（原为序列级开关，现下沉）；
  - 同 `priority` 必须有**确定 tie-break**（`priority` asc，其次 `rate_record.id` 字典序），**禁止不确定顺序**；
  - 命中后可回答"**命中哪一行 / 为什么其它行被跳过**"（回放最小骨架，配 FR-010）；
  - **兼容性**：`hit_policy` 缺省 = `exclusive`，与 v1.5 及更早设计**行为完全一致**（零迁移风险，并入 TR-001）。
- **Priority**：Must
- **Type Mapping**：Functional
- **Source**：研究稿 §4 件③、§5.1（复用 `default_by_priority` 语义）、§8 D2/§8.1、§5.2；**§7B.4 缺陷 2（逐条件自带的对标取证）**

### FR-005 计算过程（Calculation Procedure：可配置计算序列 + 可插拔算子）—— 件④（业务别名：定价过程）

- **Description**：系统 MUST 提供**计算过程 `calc_procedure`**（业务别名：定价过程）：由 `calc_procedure_step` 组成的**有序计算序列**；每步 = `seq + element_type + rate_type? + condition + params`，**步骤须带类型（不是硬编码 if-else）**。
- **Acceptance Criteria**：
  - **`result_semantic ∈ {price, cost, emission, tax, hours, quantity}`（默认 `price`）—— 过程声明"产出什么语义"（元 / 吨CO₂e / 小时），引擎不写死为价格（v1.3 通用化轴③）**；
  - `element_type` 至少覆盖：`list_price / tier / attribute / formula / manual / derived / aggregate / distribute / round / track`（★ 另预留 `quality_premium`，FR-015）；
  - 过程可按"过程类型 = `pricing`"确定（通用确定骨架，D7 要求**不写死 price**）；未来新增 `costing` / `emission` 过程类型 = **新增过程实例 + 复用同一引擎**，非改引擎；
  - 每步执行**有条件地更新内存中的中间结果**（对标 Oracle Pricing Algorithm 逐步更新内存 SDO / SAP 定价过程 V/08）；
  - 步骤可存放**小计**（subtotal），供后续步骤与报表引用（SAP `KZWI1..6`）；
  - 对标补充（研究稿 v1.9 收口）：金蝶"计算策略"经复证**属定价过程内**（公式化因子聚合层、可回放），且**仅星空旗舰版 / 星瀚具备、星空标准版无**——佐证"过程内多因子聚合"在七家中普遍存在。
- **Priority**：Must（P2）
- **Type Mapping**：Solution / Functional
- **Source**：研究稿 §4 件④、§4.4 启示 1、§6.1 #18、§8 D7/§8.2、§1.16、§3.1.6

### FR-006 计算基显式建模（Calculation Base：一等对象）

- **Description**：系统 MUST 把"**基准 base**"显式建模为**一等配置**，而非隐含在公式里的变量。计算明细每步 MUST 记录**四个维度**：
  - `base_level`（层级：`header` / `line`）
  - **`base_source`（计算基来源 —— 通用化轴①）**：`pricing_quantity`（定价数量，默认）/ **`activity_quantity`（活动量：燃料消耗 / 用电量 / 工时 —— 碳排放与作业成本用）** / `value` / `weight` / `volume` / `energy` / `hours` / `attribute` / `formula`（选 `formula` 时另记 `base_formula`）
  - `base_step`（计算基步骤：From/To，百分比 / 折扣基于哪个前序步骤的中间结果）
  - `rolling`（是否滚动：`true` 时计算基 = 持续更新的**当前滚动净额 `running_net_amount`**）
- **Acceptance Criteria**：
  - **`rolling = true` 与 `base_step` 互斥**——滚动时不指定具体前序步骤（对标 Oracle Running Net Price 是单一累加器对象）；
  - **默认不滚动（cumulative）**，滚动（cascade）**须显式开启**，开启时明细记 `running_net_amount`；
  - `base_source` 默认为**定价数量**（`qty × rate_unit`），可被 `base_formula` 改写为价值 / 重量 / 活动量 / 能耗（共用 `SafeExpressionEvaluator`）；
  - **跨域可复用（v1.3）**：把 `base_source` 换成 `activity_quantity`、把率载体换成"排放因子表 / 作业费率表"，同一套**计算基 + 步骤序列**即可算 **碳排放**（活动量 × 排放因子，Scope1→2→3 逐层累加）与 **作业成本**（动因量 × 作业费率）——**无需改引擎**（§1.4 N9 边界：碳的组织边界 / 合并层、成本归集层仍在本引擎外）。
- **Priority**：Must（P2，与 FR-005 同批）
- **Type Mapping**：Solution / Functional
- **Source**：研究稿 §4.3 A–D 行 / ⑥、§4.4 启示 2/3、§6.1 #17、§8 D10/D11/D12

### FR-007 多层累加与逐层小计

- **Description**：系统 MUST 支持**步骤间 additive（逐层累加）**：基价 → 折扣 → 附加费 → 税 → 运费，逐层产出小计，最终得净价与行金额。
- **Acceptance Criteria**：
  - 步骤间默认 **additive**（不累加就算不出净价）；
  - 逐层小计可回放（对标 Oracle Request Viewer / SF Waterfall）；
  - 行金额（`extended_amount`）= 净价 × 数量（按定价单位换算），并可被 `compute` 尾算接续。
- **Priority**：Must（P2）
- **Type Mapping**：Functional
- **Source**：研究稿 §4.3③/④、§4.4、§3.1.2B3（官方算例）、§8 D2/§8.1

### FR-008 多候选取优、互斥与权重分配（weighted）—— 件⑤

- **Description**：系统 MUST 提供**同粒度多候选的冲突消解**，共**四种范式**（详见 §9.3.1 B2）：
  - **互斥（`exclusive`）**：排斥组内**只保留获胜者**；
  - **优先级（`precedence`）**：逐级覆盖，**首个命中获胜**（默认）；
  - **取优（`best`）**：按度量选最优，**须显式开启并先定义度量**；
  - **权重分配（`weighted`）· v1.4 新增**：**多候选不取一，全部参与**，按 `rate_record.allocation_weight` **加权累加** `result_amount = Σ(rateᵢ × base × weightᵢ)`，**`Σweightᵢ = 1`**。
- **Acceptance Criteria**：
  - 默认 **Precedence**（可预测 / 可回放 / 无需遍历候选全集；合同价应压过促销价）；
  - **Best Price 绝不隐式默认**——开启时须显式定义度量（最低净价 / 最大折扣 / 含税否）；
  - 排斥组内按"只保留获胜者"处理（对标 SAP Condition Exclusion OV31/OV32、Oracle Incompatible）；
  - **权重分配（weighted，v1.4）**：
    - `allocation_weight` **可空**；**非空即该候选参与加权累加**，不参与"取一"；
    - **权重和须归一**：同组内 `Σweight = 1`，不满足则**拒绝计算并报错**，禁止静默按比例缩放（可预测性优先于"宽容"）；
    - **同组内 `allocation_weight` 非空候选与"取一"类候选不可混用**——若组内存在非空 `allocation_weight`，该组按加权累加执行，`exclusion_group.resolution` 与 `lookup_sequence` 优先级对其不生效；
    - 加权结果**可回放**：每条参与候选的 `rate × base × weight` 贡献值可在 `calc_result` / `calc_detail` 中逐条追出；
    - 溯源：Oracle 成本域 `Standard cost = (Buy cost × Buy allocation) + (Rolled-up cost × Make allocation) + (Transfer cost × Transfer allocation)`（**多候选全部参与**）、工单 `Cost Factor Allocation`（Pulp 25% / Orange Juice 100%）、LCM `Charge Basis = % of item price`；
    - **对偶说明**：`allocation_rule` 是 **1→N 摊金额**，`allocation_weight` 是 **N→1 合率**，两者共用同一数学形式的两个方向。
  - 同一数据下多种范式结果可**分别复现**（验收标准，研究稿 §7 P3）。
- **Priority**：Should（P3）
- **Type Mapping**：Functional
- **Source**：研究稿 §4 件⑤、§8 D3/§8.1、§3.1.2A、**§4.9D1 / §4.9A3（v2.0 跨域对撞：Oracle 成本域第四范式）**

### FR-009 阶梯、有效期、币种与计量单位

- **Description**：费率记录 MUST 支持**阶梯 scale**（按数量 / 按金额分档）、**有效期**（`valid_from` / `valid_to`）、**币种**与**计量单位 / 计量数量**。
- **Acceptance Criteria**：
  - 阶梯至少支持两种语义：**整单取档**（数量落入某档取档内单一价）与**逐档累进**（各档分别计价再求和）（对标 D365 / SF Volume vs Tier）；
  - 过期费率记录不参与取价；
  - 订单单位 ≠ 计量单位时先按 UoM 换算（依赖 IF-008 单位换算）。
- **Priority**：Should（P4）
- **Type Mapping**：Functional
- **Source**：研究稿 §4 件①/②、§4.3②、§3.1.4、§6.1 #6

### FR-010 可解释回放 —— 件⑥

- **Description**：系统 MUST 为每次定价产出**可回放明细**，回答"为什么是这个值"。
- **Acceptance Criteria**：
  - 每个槽位记两样：**"命中哪一行" + "是否累加"**（最小骨架）；
  - 逐步记 `seq / element_type / unit_price / extended_amount / base_level / base_source / base_step / rolling`（`rolling=true` 时加 `running_net_amount`）；
  - 可显示**被选中的、被删除的候选行及删除原因**（对标 Oracle Request Viewer）；
  - 明细结构**按可回放设计**（含基准与中间小计），不只在"手动查看"时才重算。
- **Priority**：Must（P2，与 FR-005 同批）
- **Type Mapping**：Solution / Functional
- **Source**：研究稿 §4 件⑥、§4.4 启示、§3.1.2A/§3.1.6、§5.1、§6 #8

### FR-011 结果对象宿主与生命周期

- **Description**：计算结果 MUST 落成 **`calc_result`（结果行）+ `calc_detail`（步骤明细）**，**附属于业务单据**（`bo_category: transactional` + `bo_sub_category: document` + `composition 1:N`），**不引入独立"定价单据"**。
- **Acceptance Criteria**：
  - 结果对象泛化宿主：`document_type` + `document_id` + `document_line_id`（可空 = 头级），使同一套对象可挂**任意 `document` 型 BO**（订单 / 交货 / 开票）；
  - 值落**行**，头只放**参数 / 开关**（`level ∈ {header, line}` 标记 + 头→行分摊明细）；
  - 生命周期**随单据**（`cascade_delete`）；重算 = **版本化替换明细 + 留痕**；**已开票 / 已过账行冻结**；
  - 结果**两层**：结果行（一个费率类型 / 一个 Charge 一条）与步骤明细（一步一条）；
  - **与 `doc_flow` 边界**：`doc_flow` 只搬**结果字段**（`unit_price` / `net_price`），**不搬明细**；
  - **结果 → 单据行字段写回 · v1.5 拍板（TBD-9）**：本期**不建 `output_map` 对象**，改为**按 `result_semantic` 约定写回字段**（`price` → `unit_price` / `amount`；`cost` → `cost_amount`；`emission` → `emission_amount`；余者落 `result_amount`）。依据：本期**只有一个过程实例、一套结果结构**，映射关系用约定即可表达，**零配置零新表**；真正的痛点在**多过程 / 多结果结构**时（碳结果要写碳足迹字段、成本结果要写成本字段）——**那才需要对象**。**接口已预留**：将来补 `output_map` 对象时，本条约定即为默认映射，不破坏存量。
- **Priority**：Must（P2，与 FR-010 同批）
- **Type Mapping**：Solution / Functional
- **Source**：研究稿 §4.6、§4.6B、§6.1 #21、§8 D4/D15、§5.2

### FR-012 单据链价格传递策略（搬运 / 按量重算金额 / 完全重定价）

- **Description**：系统 MUST 支持把"上游价格流到下游单据"的策略建模为**策略对象**（非布尔），核心为 `price_mode`，并可**逐属性**（价 / 运费 / 税）与**逐费率类型**覆盖；同时把**数量基准来源 `qty_basis`** 与"**单价是否重取**"**解耦**。
- **Acceptance Criteria**：
  - `price_mode ∈ {carry（纯搬运）/ recompute_amount（按实际量重算金额）/ repricing（完全重定价）}`，**逐"目标单据类型 × 参考单据类型"**可配（对标 SAP `KNPRS`/`TVCPF`、Oracle Freeze Price/Shipping/Tax、SF Repricing Service）；
  - `qty_basis ∈ {order_qty, delivered_qty, goods_issued_qty, billed_to_date_qty}`，**开票默认取 `delivered_qty`**（SAP `FKMGK=D` 惯例）；
  - 三种组合各可复现：① 纯搬运（订单量 + 订单价）；② **订单价 × 实际量**；③ 实际量 + 重取价；
  - **红线**：已开票 / 已过账行不得隐式重定价；重定价须显式触发（`reprice_trigger`）且留痕；
  - 策略声明属**计算结果的元数据**（由定价引擎产出、`doc_flow` 与下游单据消费），避免两边各自猜。
- **Priority**：Should（P4）
- **Type Mapping**：Functional
- **Source**：研究稿 §4.5A/B/C、§6.1 #19/#20、§8 D8/D14

### FR-013 事后 / 计划外费用与分摊

- **Description**：系统 MUST 支持"**事后 / 计划外费用**"作为 `calc_result` 的另一种来源：**不改原单价、独立费用行 + 分摊**，并可**反向挂载**到 PO / 收货 / 订单行。
- **归属拍板（v1.5 · TBD-1）**：**归定价"费用 / 分摊"子域**（② 方案）——**不破 D7 边界**、不为它另立引擎。依据：三家一致（Oracle `Retroactive Price Adjustment` → 独立 `acquisition cost adjustment` 回写库存估值；SAP 计划外交付成本走独立行 / 独立科目），且**它就是一条 `origin = unplanned` 的 `calc_result`**，**不新建费用单据对象**。三类费用中 **② 事后计划外** 与 **③ 过程执行费** 同构（都是"事后才知金额"）可共用本模型；但 **③ 的成本侧取值算法不在 D7 范围**（见下）。
- **Acceptance Criteria**：
  - 结果行扩展 `origin ∈ {planned, unplanned}`、`charge_source ∈ {order, invoice, receipt, service_confirm, settlement}`、`source_document_type` / `source_document_id`（**可 ≠ 宿主单据**）、`target ∈ {price, cost, expense}`、`allocation_basis`、`allocation_rule_id`；
  - 新增 **`allocation_rule`**：`basis ∈ {equal, value, quantity, weight, volume, manual}`（对标 Oracle LCM **六种**分摊基数）、`manual_factor` / `group_by` / `rounding` / `floor`（地板价）/ **`target ∈ {cost, expense}`**；
  - **分摊基数是可配枚举、去向是可配字段**（不写死"按行价值比例"、不写死"进费用"）；
  - 分摊可回放：头记总额、行记摊得额，来源单据与分摊规则可查；
  - **采购侧成本类费用本期只做对象设计、不实现**（D7 范围外）；`target=cost` 的取值算法归**成本核算**。
- **Priority**：Could（P4.5）
- **Type Mapping**：Functional
- **Source**：研究稿 §4.7B/C/D、§6.1 #22/#23、§8 D16（TBD-1）

### FR-014 追溯调整与补差

- **Description**：系统 MUST 提供 **`adjustment`** 承载追溯 / 补差：**引用原结果、成对留痕、只结算差额、不改原单据**。
- **Acceptance Criteria**：
  - 字段：`original_result_id`（被调整的原费用 / 原价）/ `adjustment_type ∈ {subsequent_debit, subsequent_credit, retro_price_change, rebate_settlement, delta_accrual, provisional_settlement, **override**}` / `delta_amount` / `effective_period` / `posted_flag` / **`reason`（v1.5 拍板 TBD-8 + D22：`adjustment_type = override` 时**必填**，见下）**；
  - **整体价覆盖（override）· v1.5 拍板（TBD-8）**：**复用 `adjustment`、不新增对象**——`adjustment_type = override` 即"人工整体改价"，语义为"**在原结果上覆盖一个最终价**"。依据：这是六家**零分歧的共识机制**（SAP `Price Override` / SF `pricing element = Override` / Oracle 人工覆盖需 `override_reason` / D365 价格覆盖），缺失最突兀；且它与 `adjustment` **同构**（都是"引用原结果 + 留痕 + 不改原单据"），另立对象会造成重复。**`reason` 必填 = 最小版"谁能改价"（D22）**——**完整权限 / 审批矩阵归权限引擎，不由定价引擎承担**（见 TBD-13）；
  - 追溯调整**必须显式触发**（费率记录变更**不自动**重算已过账单据，对标 SAP 须 `New Pricing` / `Update Pricing`）；
  - **成对产生贷 / 借项、仅结算差额**（对标 SAP 开票更正请求订单类型 RK、返利"最终结算冲抵已结算部分"）；
  - 已过账单据的追溯调整**被拒或强制留痕**（与 FR-012 红线同源）。
- **Priority**：Could（P4.5，可后置）
- **Type Mapping**：Functional
- **Source**：研究稿 §4.7B/D、§6.1 #24、§4.8D⑤

### FR-015 事实数据驱动重算（优质优价 / 大宗贸易）

- **Description**：系统 MUST（蓝图）支持"**事实数据**"作为定价输入与重算触发：① 作为**匹配键表的一个字段维度**（优质优价）；② 作为**数量折算输入**（干吨 / 净干重 / 金属量）；③ **价可来自外部报价与计价期**（大宗两段式）。
- **Acceptance Criteria**：
  - 因子目录 `source_type` 支持 `quality` / `measurement` / `market`（与 FR-003 同权）；
  - 新增 **`external_rate_source`**（`source ∈ {platts, lme, ice, index, custom}` / `quote_code` / `calendar_id` / `fallback_rule`）与 **`pricing_period`**（`period_type` / `start_offset` / `end_offset` / `average_basis ∈ {close, average, first, last}` / `rounding`）；
  - `calc_result` 扩展 `rate_source ∈ {rate_record, external_quote, formula}` / `pricing_period_id` / `external_rate_source_id` / **`fact_snapshot`（JSON）**；`qty_basis` 扩容 `dry_weight` / `net_dry_weight` / `assayed_content`；
  - 优质优价落成 `element_type = quality_premium` 结果行；大宗两段式落成 `adjustment{adjustment_type = provisional_settlement}`（**只结算差额、不改原单据**）；
  - **`reprice_trigger` 增加 `on_quality_result` / `on_pricing_period_end`**（**蓝图枚举一次给全 · v1.5 拍板 TBD-2 设计侧③**）；
  - **三条护栏**：① `fact_snapshot` 必须存档（缺一即不可复现）；② 重算须显式触发；③ 暂定价与终价**必须配对可查**（`original_result_id`）；
  - **`fact_snapshot` 缺失时拒绝结算**；无质检链路 / 无报价源的行业**可不用本机制**（非强制）。
- **实施节奏拍板（v1.5 · TBD-2）**：**设计侧③（蓝图留全）／实施侧②（只实装 `on_quality_result` 一条链路）**。依据：另两个触发器**依赖尚未实施的对象**——`on_pricing_period_end` 依赖 `external_rate_source` + `pricing_period`（本 FR 内两个新对象，随 P6 走），`provisional_settlement` 依赖 TBD-1 的 `origin` 与 FR-013；**先把枚举给全（零成本），只实装依赖已就绪的那一条**，避免半配置状态。另注：研究稿 §4.8C 规律 2 指出"**质检值直接改价在头部产品里普遍是半成品**"（Oracle / SAP / SF 均【未找到】标准链路，全靠自定义属性绕行）——**这既是本 FR 的机会，也说明它无成熟范式可抄，故须走"蓝图留全 + 分步实施"**。
- **Priority**：Could（P6，可选；其中 FR-003 的事实源分类建议与 P1 同批先行）
- **Type Mapping**：Functional
- **Source**：研究稿 §4.8B/C/D/E、§6.1 #25/#26/#27、§8 D17（TBD-2）

### FR-016 用量更新（业务别名：条件更新；累计已用量）

- **Description**：系统 SHOULD 支持**用量更新**（业务别名：条件更新）：费率记录跨单据**累计已用量**（如年度合同量用满即失效），由 `usage_group` + `cumulative_usage` 承载。
- **Acceptance Criteria**：可设最大金额 / 数量 / 单据数，超限**自动失效**（对标 SAP Condition Update `KOUPD`）。
- **Priority**：Could（P4，可后置；D6 定为"先不做"）
- **Type Mapping**：Functional
- **Source**：研究稿 §4.2 第 1/2 层、§6 #7、§8 D6

### FR-017 扩展点例程（逃生门）

- **Description**：系统 SHOULD 提供 **VOFM 式例程**接线（Requirement / Formula），使复杂定制**可插拔、不改引擎**。
- **Acceptance Criteria**：复用既有 `ActionType.BUSINESS` hook 骨架；自定义例程可注册 / 可替换。
- **Priority**：Could（P5）
- **Type Mapping**：Solution / Functional
- **Source**：研究稿 §4 件④、§6 #9、§7 P5、§5.1

### FR-018 边界登记（防重复造轮子）

- **Description**：系统 MUST 在文档与代码层面**显式登记六条边界**（研究稿 §5.2），且**判据单一化**：

| 界别 | 它回答什么 | 归谁 | 判据 |
|---|---|---|---|
| 定价 vs `default` | 金额怎么算 / 填哪个价目表 | 定价 / `MetaDefaultRule` | 选价目表 ≠ 算价格 |
| 定价 vs `compute` | 多层累加多候选取优 / 无条件表达式覆盖一字段 | 定价 / `MetaComputation` | `compute` 做不了 `unit_price` 怎么来 |
| 定价 vs `rollup` | 过程内按组聚合 / 跨单据层级守恒汇总 | 定价 / `analytical_engine` | **过程内属定价**；rollup 输入是"已算好的金额" |
| 定价 vs `allocation` | ① 过程内一步（头→行折扣分摊，哪怕守恒、跨行）② 过程外独立分摊 | 定价 / 待建 `allocation` | **是否在计算过程内**；★ 升级判据：**是否有"可分摊到一个业务单据行"的价格 / 费用语义** |
| 定价 vs `validation` | 算出净价 / 净价不得低于限价 | 定价 / `MetaValidation` | 定价**产出** min/max；validation **拦** |
| 定价 vs `doc_flow` | 重新算价 / 把源单价 `field_map` 一对一搬 | 定价 / `doc_flow_rule` | 搬 vs 算；`doc_flow` 只搬结果字段不搬明细 |

- **Acceptance Criteria**：
  - 上述判据在 Spec / 代码注释 / 评审记录中可查；
  - **通用化（D7）≠ 把不属于定价的东西塞进定价引擎**——通用化只针对"同一族（SAP 条件技术同族）的确定过程"。
- **Priority**：Must（文档约束，全程生效）
- **Type Mapping**：Solution
- **Source**：研究稿 §5.2、§4.4 启示 4、§4.7E、§8 D13/§8.2、§7 非目标

---

## 4. 非功能需求（NFR）

### NFR-001 性能
- **Description**：单行定价（P1 单层取价）须在可接受延迟内完成；整单 N 行须支持**批量**（逐行调用但主数据批量 / 缓存）；跨对象取数（客户 / 物料 / 组织主数据）须批量 / 缓存。
- **Measurement**：基准测试；单行 P1 取价增量与整单 N 行批量耗时；增量重定价（SF `enableDeltaPricing` 式）作为 P4+ 性能项。
- **Priority**：Must
- **Source**：研究稿 §4.5C4、§5.1

### NFR-002 安全
- **Description**：条件与公式一律走 `SafeExpressionEvaluator` **AST 白名单**，**禁止 `eval`**。
- **Measurement**：危险表达式（如 `__import__`）被拒绝的单测。
- **Priority**：Must
- **Source**：研究稿 §5.1

### NFR-003 可观测 / 可解释
- **Description**：每次定价产出可回放明细（FR-010），支持"查看计算过程"；日志 / 明细结构与回放复用同一份数据结构。
- **Measurement**：给定一次定价，能还原"命中哪行 + 每步小计 + 基准四字段"。
- **Priority**：Must
- **Source**：研究稿 §4 件⑥、§5.1

### NFR-004 兼容（最小改动）
- **Description**：复用既有 `condition_parser` / `condition_evaluator` / `condition_converter`、`default_by_priority` 首个命中语义、`SafeExpressionEvaluator` + `FormulaFunctionRegistry`、`MetaComputation` 宿主；**不改动 `default` / `compute` 既有行为**，存量测试全绿。
- **Measurement**：存量测试零回归。
- **Priority**：Must
- **Source**：研究稿 §5.1、§5.2

### NFR-005 可测试
- **Description**：每条 FR 有对应单测；引擎支持 stub 注入（价目行 / 主数据）。**按项目铁律用 `python d:\filework\test.py`，禁止直接 `pytest`**。
- **Measurement**：FR ↔ 测试用例映射；`test.py` 全绿。
- **Priority**：Must
- **Source**：项目测试铁律；研究稿 §7 各阶段 DoD

### NFR-006 最小改动 / 不新造单据
- **Description**：**不引入独立"定价单据"**；结果对象复用 `document` 型 BO + `composition 1:N` 范式；避免与 `doc_flow` 争"谁是单据"。
- **Measurement**：对象结构评审；无独立 pricing document BO。
- **Priority**：Must
- **Source**：研究稿 §4.6、§8 D15

### NFR-007 可配置性
- **Description**：费率类型 / 计算过程 / 查找序列 / 分摊规则**均为配置对象**，改配置不改代码。
- **Measurement**：新增一个费率类型 / 一条过程步骤，无需改引擎代码。
- **Priority**：Must
- **Source**：研究稿 §4.1、§4.4、§8 D9

---

## 5. 外部接口需求（IF）

### IF-001 定价调用入口（引擎 API）
- **Type**：API / Internal
- **Entry**：引擎方法，输入 = **一行 + 表头上下文**（行对象携带币种 / 客户 / 销售区域等表头字段），输出 = 净价 / 行金额 + 计算明细（`calc_result` + `calc_detail`）。
- **Interaction**：逐行调用，行对象携带所需表头字段；首期不做真表头条件（D10）。
- **Error Handling**：无可用费率记录 / 过程未命中 → 返回明确原因 + 回放日志；表达式求值失败 → 记录并被 `SafeExpressionEvaluator` 拒绝。
- **Source**：研究稿 §4.3⑥1、§4.6B

### IF-002 与 `default` 的接缝
- **Type**：System Integration
- **Entry**：`MetaDefaultRule` 确定 `rate_table` → 定价引擎消费该价目表。
- **Error Handling**：`rate_table` 为空 → 定价回退到 Base Price / 报错（按配置）。
- **Source**：研究稿 §2.1、§5.2

### IF-003 与 `compute` 的接缝
- **Type**：System Integration
- **Entry**：定价产出 `unit_price` / `net_price` → `MetaComputation` 尾算 `total_amount = qty × unit_price`。
- **Source**：研究稿 §5.2

### IF-004 与 `doc_flow` 的接缝
- **Type**：System Integration
- **Entry**：定价引擎**产出** `price_mode` / `freeze_policy` 声明 → `doc_flow` 与下游单据**消费**；`doc_flow` 只搬结果字段，不搬明细。
- **Error Handling**：未声明策略 → 禁止静默重定价（红线）。
- **Source**：研究稿 §4.5C、§4.6B、§5.2

### IF-005 与 `validation` 的接缝
- **Type**：System Integration
- **Entry**：定价**产出** min/max 价格快照（对标 SF Price Tracking）→ `MetaValidation` 做限价**拦截**（金蝶最低限价）。
- **Source**：研究稿 §4.4 启示 5、§5.2

### IF-006 与 `rollup` / `analytical` 的接缝
- **Type**：System Integration
- **Entry**：过程内按组聚合（SF Aggregate Price，不跨单据）属定价；跨行 / 跨单据层级守恒汇总归 `analytical_engine`。
- **Source**：研究稿 §5.2

### IF-007 回放查询接口
- **Type**：API
- **Entry**：按 `document_type` + `document_id`（+ 可选 `document_line_id`）查询 `calc_result` + `calc_detail`。
- **Interaction**：返回"命中哪行 / 被删候选及原因 / 逐层小计 / 基准四字段"。
- **Source**：研究稿 §4 件⑥、§4.6

### IF-008 依赖主数据引用
- **Type**：System Integration
- **Entry**：引用 **币种 / 汇率 / 税码·税率·税分类 / 客户价格组·客户定价过程 / 物料价格组·税分类·参考物料 / 销售区域（销售组织 + 分销渠道 + 产品组）/ UoM + 单位换算 / 有效期日历**（研究稿 §4.2 第 3 层）。
- **Error Handling**：缺失依赖 → 对应费率类型 / 键**不上线**（分期），已上线键在依赖缺失时明确报错，不静默错算。
- **Source**：研究稿 §4.2、§6.1 #11–#16

---

## 6. 过渡 / 迁移需求（TR）

### TR-001 存量行为不变（天然灰度）
- **Description**：存量对象无计算过程时，行为完全不变。
- **Strategy**：计算过程 / 费率类型为**新增配置**，未配置即不触发。
- **Rollback**：禁用配置即失效。

### TR-002 依赖主数据分期补齐顺序
- **Description**：引擎依赖一批通用主数据，缺失则不能开跑。
- **责任方划分（v1.6）**：**主数据补齐由数据模块负责**（#11 币种、#16 销售区域、#12 汇率、#14/#15 价格组、#13 税码等）。**本引擎侧不等待**——配置链 T0-1~T0-7 与内核 T1 **均已零主数据依赖**（§8.2.0、C-T0-6），通过 `currency` 降级为 `string` + `master_data_ref` 标记解耦；主数据到位后**仅需补引用完整性校验，不改表结构**。**唯一仍需等待的是 IF-008 跨币种换算与税 / 价格组类费率类型**（T1 之后的事）。
- **Strategy**（研究稿 §6.1 排序原则，**先依赖后优先级**）：
  - **P0 前置**：#11 币种主数据、#16 销售区域（`sales` 已有，补渠道 / 产品组）——须先于引擎开跑；
  - **P1 随费率类型**：#12 汇率（跨币种取价前）、#14 客户价格组 / 客户计算过程、#15 物料价格组 / 税分类 / 参考物料（对应折扣组 / 物料组取价前）；
  - **P2**：#13 税码 / 税率 / 税分类（税费率类型前）；
  - **P6**：#25/#26/#27 事实源相关（可选）。
- **Rollback**：依赖未补齐时，对应条件的计算过程不启用。

### TR-003 结果对象为新增声明
- **Description**：`calc_result` / `calc_detail` / `allocation_rule` / `adjustment` / `external_rate_source` / `pricing_period` 均为**新增**对象声明。
- **Strategy**：通过元数据 BO 声明方式新增，**无存量数据迁移**。
- **Rollback**：停用 / 删除新增 BO 声明；存量单据不受影响。

### TR-004 回滚总策略
- **Description**：所有新能力以"配置开关 + 新增对象"承载，可单点回退。
- **Strategy**：① 计算过程 `enabled=false`；② 费率类型 / 费率表停用；③ 新增对象声明移除；④ 引擎调用点可短路。
- **Rollback**：**无 schema 迁移 → 无数据迁移回滚**（与规则模型 Spec 同范式）。

### TR-005 权重分配（`allocation_weight`）零迁移
- **Description**：`rate_record.allocation_weight` 为**新增可空字段**，不改动既有取值与算法。
- **Strategy**：**默认 `null` = 行为完全不变**——存量费率记录一律视为"取一"类候选，三种原有范式（`exclusive` / `precedence` / `best`）行为不受影响；仅当配置了非空权重且同组 Σweight = 1 时，该组才切换为加权累加。
- **Rollback**：清空所有 `allocation_weight` 即回到 v1.3 行为（无需改代码）。

### TR-006 消解范式验收矩阵（v1.4）
- **Description**：同一份候选数据下，四种范式各跑一次，结果须与预期一致且互不干扰。
- **Strategy**：准备**三候选**测试夹具（如 3 条同键费率记录，rate = 100 / 200 / 300）：
  | 场景 | 配置 | 预期 |
  |---|---|---|
  | 优先级 `precedence` | priority 1/2/3 | 命中 priority 1 → 100 |
  | 取优 `best`（最低净价） | 显式开启 + 度量 | 命中 100 |
  | 互斥 `exclusive` | 同组 | 只保留获胜者 |
  | **权重分配 `weighted`** | 权重 0.5 / 0.3 / 0.2 | **100×.5 + 200×.3 + 300×.2 = 170**<br>**（算术修正 2026-10-06：原文写"= 140"是错的，50+60+60=170）** |
  | **权重和不归一** | 权重 0.5 / 0.3 | **拒绝计算并报错**（不静默缩放） |
- **Rollback**：清空权重字段回到默认范式。

---

## 7. 约束与假设

### 7.1 技术约束
- **C1** 复用既有 `condition_parser` / `condition_evaluator` / `condition_converter`、`default_by_priority`（`meta/core/rule_executor.py` L1432 起）、`SafeExpressionEvaluator` + `FormulaFunctionRegistry`、`MetaComputation`（`meta/core/models.py` L207-221）；不重复造这些轮子。
- **C2** 表达式求值走 AST 白名单，禁 `eval`。
- **C3** 结果对象复用 `bo_category: transactional` + `bo_sub_category: document` + `composition 1:N / ownership / cascade_delete`（[sales_order_enhanced.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/examples/sales_order_enhanced.yaml#L378-L387) 范式），**不引入独立"定价单据"**。
- **C4** 测试按项目铁律用 `python d:\filework\test.py`。
- **C5** 步骤 = 带 `element_type` 的**算子列表**，禁止硬编码 if-else 分支。

### 7.2 业务约束
- **B1** **D7 已拍板**：只做定价；元模型按"**通用确定**"设计（命名过程无关；未来加"伙伴确定"= 新增过程类型 + 一张规则表，而非改引擎）。
- **B2** **采购侧成本类费用本期只做对象设计、不实现**（D7 范围外）；`target=cost` 取值算法归**成本核算**。
- **B3** 期货 / 风控 / QMS / 成本核算**不属定价**（研究稿 §4.8E）。
- **B4** **已开票 / 已过账的行禁止隐式重定价**（红线）。

### 7.3 假设
- **A1** 主数据补齐有排期（TR-002），否则引擎无法引用 → Source：研究稿 §4.2（**已验证缺失**）。
- **A2** 首期不做在线配置 UI，配置随元数据定义发布 → Source：研究稿 §7 N4（**假设**）。
- **A3** 匹配键表 + 因子目录 + 费率类型同批（P0）→ Source：研究稿 §6.1 #10（**建议**）。
- **A4** 平台现在能回答"用哪张价目表"（`MetaDefaultRule`）与"总额 = 数量 × 单价"（`MetaComputation`），不能回答"这张价目表里这个客户这个物料的价格是多少、又叠了哪些折扣" → Source：研究稿 §5.3（**代码级验证**）。

---

## 7B. 三件套通用性分析（v1.6 · 2026-10-06）

> **为何补这一节**：D7 / §9.2 已声明"元模型 = 通用确定"，但**未回答"通用到什么粒度"**。
> 因子目录 / 匹配键表 / 查找序列被当作**三张定价专表**直接进入 §8.2 P0 与 §9.3.1 A 表——
> **本节用代码取证回答：通用的是它们背后的三个原语，不是这三张表。**
> 结论直接改写 FR-003 / FR-004 的职责边界，并给出 T0 建模口径，**不新增对象数量**。

### 7B.1 结论一句话

> **三件套是"通用取数"的一种实例化，通用点在「因子 / 键 / 取数计划」三原语**；
> 当前设计把**定价特例**（量级换算、阶梯基数、排除对象）与**通用骨架**混装在同两张表里，
> **若不拆，第一次复用（伙伴确定 / 税 / 碳）时必然重造**。

### 7B.2 三原语：任何"按已知条件算出未知值"的机制都逃不掉的三问

| 问 | 原语 | 平台现有形态（**代码级取证**） | 定价形态 |
|---|---|---|---|
| **看什么** | **因子** Input | `MetaRule.condition` 里**隐含**的字段引用 —— [models.py](file:///d:/filework/excel-to-diagram/meta/core/models.py#L156) | `factor_catalog` 显式立档 |
| **按什么组合** | **键** Key | 无显式概念（同样隐含在表达式中） | `key_schema.key_fields[]` |
| **先查谁、命中算不算完** | **取数计划** Plan | `priority` + first-match —— [rule_executor.py](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1344-L1354) | `lookup_sequence.steps[]` |

**关键区分**：`condition` 是**自由表达式**（`SafeExpressionEvaluator` 语法），因子**藏在字符串里**——
**不可枚举、不可复用、不可做 UI 下拉、无法回答"哪些字段参与价格"**。
三件套把同一件事**拆成三层可配置结构**，这是一次**从表达式驱动到目录驱动的升维**，不是重复造轮子。

### 7B.3 平台内已四处自发实现了「三原语」，但无一通用

| 域 | 因子 | 键 | 取数计划 |
|---|---|---|---|
| 属性确定（DEFAULT） | condition 引用字段 | 无 | `priority` + first-match |
| **数据权限** | 记录字段 | `(bo, action, role)` | **Owner > Exclude > Include > 默认拒绝** |
| 派生（DERIVATION） | `source_fields` | `group_by` | `order_by` + `strategy` |
| 文档流 | 源字段 | `(doc_type, trigger)` | `flow_mode` |

**四处各造了一套，无一是可复用组件** —— 这正是"通用性"主张的**实证支撑**：不是本引擎的抱负，是已在四处自然涌现的需求。
（对标：`MetaDerivation` 的 `group_by`/`order_by` 见 [models.py](file:///d:/filework/excel-to-diagram/meta/core/models.py#L391-L394)。）

### 7B.4 三个缺陷（必须修，否则 T0 锁死错误结构）

**缺陷 1：`key_schema` 严重超载 —— 塞了 3+1 个互不相干职责**

| 承载内容 | 归属判断 |
|---|---|
| `key_fields[]`（匹配维度） | **通用**（唯一有跨业务价值的部分） |
| `display_scale` / `numeric_field`（量级换算） | **定价特例**（Part 1 消费，与匹配无关） |
| `scale_divisor` / `exclude_bo`（阶梯与排除） | **定价特例**（Part 2/3，与匹配无关） |
| 承载加性取数槽位 | 与 `rate_record.scale[]` / `allocation_weight` 语义重叠 |

> **对标反证**：**六家里五家没有独立的"匹配键目录"**——SAP 只有「条件表 + 存取序列」两层
> （匹配维度**内联在条件记录里**）；Oracle Fusion 直接在 `ListPrice` 上挂 `QualifyingCriteria`。
> **独立 `key_schema` 表是本引擎的选择，不是行业基线**，故须收窄到只承载 `key_fields[]`。

**缺陷 2：`lookup_sequence` 把「查」与「怎么用」混在一张表**

- **检索计划**：第几槽位、什么键 —— `seq` / `key_schema_id`
- **聚合策略**：exclusive（命中即停）vs additive（累加）—— `exclusive`

这两个在六家是**分离且逐条自带**的：SAP 条件表可按 `%GET_VAL` 累加、也可首命中退出，**是每条条件自己的属性，不是序列级属性**。
混在一张表的直接后果：**"第 1 槽累加、第 2 槽取优"必须整表复制**。

**缺陷 3：`factor_catalog` 与 `MetaField` 是同一事实的两个真相源**

| `MetaField` 已有 | `factor_catalog` 又声明一遍 | 冲突 |
|---|---|---|
| `id` / `name` / `field_type` | `id` / `name` / `data_type` | 枚举不同 |
| `semantics.data_category ∈ {text, code, date, number, amount, quantity, boolean}` | `data_type ∈ {string, number, date, enum, boolean}` | **`amount`/`quantity` vs `string`/`enum` 逐项不对齐** |
| `semantics.aliases` | `aliases` | 重复 |

> **风险等级**：与 A1 修掉的「表名映射 6 份副本」**是同一类风险**，只是下沉到字段层。
> 同一字段的类型可能被两处声明为不同枚举 → 换算与校验行为不可预测。

### 7B.5 修正方案（**不新增对象数量**，只收窄职责 + 加一个 flag）

```
平台层三原语（跨业务，本期只做取证不做实现）
├─ 因子声明 → 复用 MetaField + semantics，**不新建目录表**
├─ 键       → 命名的一组因子引用（收窄到只含 key_fields[]）
└─ 取数计划 → 有序槽位 + **每槽独立**命中策略（exclusive/additive 下沉到 rate_record）
```

**职责重划（改写 §9.3.1 A 表）**

| 字段 | 从 | 移到 | 理由 |
|---|---|---|---|
| `key_schema.display_scale` / `numeric_field` | `key_schema` | `rate_type` | 量级换算属"怎么算"，非"按什么匹配" |
| `key_schema.scale_divisor` / `exclude_bo` | `key_schema` | `rate_record` | 阶梯基数 / 排除对象属**某条费率记录的属性** |
| `lookup_sequence.steps[].exclusive` | `lookup_sequence` | `rate_record.hit_policy` | 对标 SAP **逐条件自带**；消除整表复制 |
| `factor_catalog.data_type` | `factor_catalog` | **删**（引用 `MetaField.field_type`） | 消除双重真相源 |
| `factor_catalog.aliases` | `factor_catalog` | **删**（引用 `MetaField.semantics.aliases`） | 同上 |
| `factor_catalog.source_type` + `is_price_relevant` | `factor_catalog` | **保留** | **本表唯一不可替代的内容**：事实源分类 + 价格相关性标记，二者**皆非 `MetaField` 现有能力** |

**`factor_catalog` 收窄后的唯一职责**（这才是它必须独立成表的理由）：
1. `source_type ∈ {static, master, quality, measurement, market}` —— **让质检 / 计量 / 外部报价与主数据同权**（FR-015 前置，§7B.6）
2. `is_price_relevant` —— 回答"哪些字段影响价格"（表达式驱动**答不了**）

> **判据统一**：**这个字段换个业务还需要吗？** 需要 → 平台层；不需要 → 定价。
> 依此：`rate_type` / `calc_procedure` / `base_level` / `scale` / `allocation_weight` / `exclude_bo`
> **全为定价独有**（B1「未来加伙伴确定 = 新增过程类型 + 一张规则表」，**成立**）。

### 7B.6 与 FR-015 的依赖关系（重排优先级）

`factor_catalog.source_type` 是 **FR-015（事实数据驱动重算）的前置**：
若主数据字段与非主数据字段（质检值 / 计量值 / 市场报价）**不同权**，FR-015 无法成立。
故 §8.2 **P0 必须包含 `factor_catalog`**，不可推迟到与 `order_line` 同期。

### 7B.7 对 T0 建模口径的直接约束

| 约束 | 内容 |
|---|---|
| **C-T0-1** | `key_schema` **只**含 `code` / `name` / `key_fields[]`；量级换算、阶梯、排除**不得**入表 |
| **C-T0-2** | `lookup_sequence` **只**含 `code` / `name` / `steps[{seq, key_schema_id}]`；**不含** `exclusive` |
| **C-T0-3** | `factor_catalog` **不得**声明 `data_type` / `aliases`（引用 `MetaField`）；**只**声明 `source_type` / `is_price_relevant` |
| **C-T0-4** | `rate_record` 新增 `hit_policy ∈ {exclusive, additive}`（默认 `exclusive`），承载原 `steps[].exclusive` 语义 |
| **C-T0-5** | 迁移零风险：`exclusive` 默认值 = 原 Spec 语义，存量无配置 → 行为不变（并入 TR-001） |
| **C-T0-6** | 三表**零主数据依赖**（`currency` 降级为 `string` + `master_data_ref` 标记），可与主数据并行交付 |
| **C-T0-7~C-T0-13** | **配置载体与作用域约束**（Agent / 运行态背景，见 §7C.5）：yaml 作 SSOT + table 自动物化 / 主数据引用不建外键 / `rate_table` 预留 `owner_org_id` / Agent 生成走同一份 yaml 不旁路写 DB / `status` 草稿发布分离必须落地 / **`key_fields` 本期冻结（禁止结构变更）** / **yaml 仍是唯一 SSOT（`MetaObject` 仅为建表中间产物）** |

### 7B.8 备选方案与否决理由

| 备选 | 否决理由 |
|---|---|
| **A. 维持三表原样** | 缺陷 1/2 在**第二次复用**（伙伴确定）时即爆发：量级换算与匹配维度耦合，无法被非定价域复用 |
| **B. 只加注释说明"这些字段是定价专用"** | 不解决**双重真相源**（`data_type` 枚举冲突是实打实的错），也不解决整表复制 |
| **C. 抽象出独立"决策原语"包（新模块）** | **超范围**：本期只有一个过程实例，YAGNI。原语**先在文档层立口径**（本节），实现层待第二个实例出现再抽——**这与 §7.2 B1「新增过程类型 + 一张规则表」的承诺一致** |
| **D** `key_schema` 彻底废掉，匹配维度内联进 `rate_record.keys{}`** | **更接近 SAP 基线**（SAP 条件表内联匹配维度），少一张表。但**六家中 Fusion / Odoo 亦内联**，且本引擎 `key_schema` 承担**可复用的键定义**（多个 `rate_table` 共享同一键结构）——**保留表、收窄职责**是折中；若 P0 实施时发现"键从不复用"，则按 D 废表（登记 TBD-14） |

---

## 7C. 配置载体的未来形态：AI Agent 背景下的选择（v1.6 · 2026-10-06）

> **为何补这一节**：§7B 解决"配置**结构**该怎么分层"，本节解决"配置**载体**该是什么形态"。
> **现实起点**：本平台**已经是** yaml 声明式，且**已在做** Agent 动态生成——
> 提这个问题不是"要不要切换"，而是"**已选的路要不要承认它**、边界划在哪"。
> **结论先行：Agent 时代 yaml 与 table 不是二选一，而是「同一份 SSOT 的两个投影」——
> yaml 是 SSOT，table 是查询加速物。** Agent 要动的是**生成侧与作用域**，不是载体本身。

### 7C.1 事实前提：yaml 是 SSOT，`MetaObject` 只是建表中间产物

**这不是推论，是仓库既有实现**：

| 事实 | 取证 |
|---|---|
| **yaml 是唯一事实源，`.bip`/`manifest.json` 是构建产物** | [app_package.py](file:///d:/filework/excel-to-diagram/meta/core/app_package.py#L10-L12) 原文："包内 `manifest.json` 是**构建产物**; `app.yaml` 仍是唯一事实源" |
| yaml → registry → 建表流水线已通 | [app_builder.py](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py#L48-L57) `with_yaml_schemas()` → `register_from_directory` → `invalidate_table_cache` |
| 反向也有：DB → BODefinition 内省 | [app_builder.py](file:///d:/filework/excel-to-diagram/meta/core/app_builder.py#L59-L80) `with_auto_schema()`（`SchemaIntrospector`），**注释标明"仅 introspect，不注册"** |
| 运行时可增量加工策略（不改代码） | [materialization_registry.py](file:///d:/filework/excel-to-diagram/meta/core/materialization_registry.py#L9-L11) "新表加 `updated_at` 时，只需在 SSOT 加一行，无需改代码" |
| 枚举已有**双轨**：静态 → DB | [enum_resolver.py](file:///d:/filework/excel-to-diagram/meta/core/enum_resolver.py#L31-L45) `field.enum_values`（静态）→ `value_help` → `enum_values`（DB） |

> **由此得出两个关键约束**：
> ① **双轨制（yaml 优先 + DB 兜底）已是既成事实**——不是待选方案，是**已在运行的模式**；
> ② **反向内省存在但刻意不注册**——`with_auto_schema` 明确"仅 introspect，不注册"，
> 说明**"从 table 反推模型"路上有一道人为闸门**。**这道闸门在 Agent 时代会成为关键设计点**（见 §7C.4）。

#### 7C.1.1 关键修正：`MetaObject` **装不下** yaml 的全部（v1.6 修订）

> **本节修正了 v1.6 初稿的一处立论错误**：初稿曾写「`MetaObject` 是唯一 SSOT，yaml 降级为装载格式」。
> **经 `_template.yaml` 与 `models.py` 逐块比对，该立论不成立**——`MetaObject` 是**不完整投影**。

[\\_template.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/_template.yaml) 顶层共 **13 个块**，`MetaObject` 的覆盖情况：

| yaml 顶层块 | `MetaObject` 覆盖 |
|---|---|
| `id` / `name` / `table_name` / `description` / `semantics` / `fields[]` / `associations` / `indexes` / `rules` / `deletion_policy` | ✅ 有对应字段 |
| **`audit`**（create / update / delete 三套，字段级 `all` / `changed_only` / `business_only`） | ❌ **无对应字段** |
| **`ui_view_config`**（list / form / detail 三套视图，含 `searchFields` / `batch_actions` / `placeholder` / `widget: textarea`） | ⚠️ 有 `ViewConfig` 但**是另一个东西**（`sources` / `joins` / `aggregates` = 查询视图，非 UI 布局） |
| **`category_config`**（`create_permission` / `owner_auto_permission`） | ❌ **无对应字段** |
| **`import_export`**（`conflict_strategy: upsert` / `conflict_key`） | ❌ **无对应字段** |
| `enums` | ⚠️ `MetaField.enum_values` 仅覆盖字段级枚举 |

**正确的链路（推翻初稿的"SSOT 下移"）**：

```
yaml（完整 SSOT，含 MetaObject 装不下的 4 块）
   │
   ├─ register_from_directory() → MetaObject（**不完整投影**）→ registry
   │                                    └→ schema_generator（**只消费 fields / indexes / relations**）→ 建表
   │
   └─ 前端 UI / 权限 / 审计 / 导入导出（**直接读 yaml，不经过 MetaObject**）
```

**两条重要推论**：
1. **`schema_generator` 从不需要那 4 块**——建表只用到 `fields` / `indexes` / `associations`；
   故**"让顾问勾字段生成 yaml"这条路完全走得通**，`MetaObject` 在该链路上**只是建表中间产物**。
2. **这反而降低了运行态自举的治理成本**——见 §7C.4.1 的"顾问只勾 4 项、其余走模板默认值"。

### 7C.2 四种候选载体的对比

| 方案 | 载体 | Agent 适配 | 检索性能 | 版本/回滚 | 校验时机 | 判定 |
|---|---|---|---|---|---|---|
| **A. 纯 yaml** | 文件 | ★★★ 生成即写文件，天然 diff | ★ 靠启动期建表 + 索引 | ★★★ git 友好 | **启动期**（fail fast） | **SSOT 应当如此** |
| **B. 纯 table** | DB 表 | ★ 需 DDL，Agent 改结构风险高 | ★★★ | ★ 需自建版本表 | 运行时 | **不宜作 SSOT** |
| **C. yaml + table 投影**（平台现状） | A + B | ★★★ | ★★★ | ★★★ | 启动期 + 运行时双校验 | **✅ 就是正确形态** |
| **D. 泛化 EAV 模型** | 单表 + JSON 列 | ★★ 灵活但查询退化 | ★（JSON 扫描） | ★ | 运行时 | **仅适用于"配置本身即数据"的少数场景** |

**为什么不是 A（纯 yaml，无 table）**：Agent 生成的配置要能被**业务数据查询**。
因子目录、键、费率记录**是数据不是代码**——若只存 yaml，每次取价都要解析文件 + 内存过滤，**等于把 IO 成本挪到每次业务操作**。

**为什么不是 B（纯 table）**：Agent 改 DDL 意味着**改结构**。
`CREATE TABLE` 无版本、无回滚、无 diff——**"Agent 动态加一张配置表"在纯 table 下不可审查**。

**为什么不是 D（EAV）**：仓库里已有它的形态且已被验证为**专用**——
`permission_rules_v2`（[permission_rule_v2_dao.py](file:///d:/filework/excel-to-diagram/meta/core/permission_rule_v2_dao.py#L7-L11)）用 `include_conditions` / `exclude_conditions` **JSON 列**。
**它是对的**，因为规则**数量少、形状固定、只按 `role_id` 查**。
但**费率记录不同**：需按 `keys{}` 做**组合等值匹配**（`WHERE key_customer = ? AND key_material = ?`）——
**JSON 列做不了索引等值匹配**；EAV 要么退化全表扫，要么给每种键组合建宽表（= 回到 B）。

### 7C.3 关键结论：Agent 改变的是**三件事**，不是载体

| 变化 | 说明 | 对载体的要求 |
|---|---|---|
| **① 生成侧动态化** | Agent 写 yaml / 建表，而非人手写 | 载体必须**声明式 + 可校验**（A 天然满足；B 不满足） |
| **② 作用域动态化** | 配置从"全局静态"到"租户/用户/时刻可变" | 需要**作用域维度**（见 §7C.4），**不是换载体能解决的** |
| **③ 结构稳定、表结构不固定** | 业务加新因子，**不应改 schema** | 决定 `key_schema` 存在与否（**TBD-14 的真正权重**） |

> **反直觉但重要的推论**：Agent 越强，**越需要把载体收紧到声明式**。
> 手写配置时"表结构随意"成本可接受；**Agent 生成时，宽松载体会把错误从"一次人工返工"变成"自动化污染"**。
> 即：**灵活性应放在「配置内容」，不该放在「配置结构」**。

### 7C.4 真正需要设计的：作用域维度（而非载体形态）

Agent 时代配置的**本质变化是作用域**，不是格式。当前三件套**全部是全局配置、无作用域字段**：

| 作用域 | 语义 | 现状 | 必要性 |
|---|---|---|---|
| **租户 / 组织隔离** | A 公司价目不影响 B 公司 | `rate_table` 无租户字段 | **必须**——否则跨租串价 |
| **版本 / 生效期** | 规则改动能回溯"当时按什么算" | `rate_record` 有 `valid_from/valid_to`（**行级**），但**结构变更无版本** | **必须**——TBD-4 遗留 |
| **用户级覆盖** | 某人/某单有特殊价 | **无** | 可能，但应走 `adjustment` 而非改配置 |
| **草稿 / 发布分离** | Agent 生成的配置先预览再生效 | `rate_table.status ∈ {draft, approved, inactive}`（**已有一半**） | **已有，够用** |

> **`with_auto_schema` 那道闸门的意义**：它当前"仅 introspect，不注册"是**正确的保守设计**——
> **DB 里的东西不该自动变成模型**。Agent 时代应保持这道闸门，但把闸门从"禁止"改成"**需显式批准**"：
> Agent 可提议从 table 生成 yaml，**但必须产出 diff 供人确认**，而非静默注册。

### 7C.4.1 运行态自举：双装载 + 仿 SAP V/03 界面（v1.6 **拍板**）

> **本节回答一个 v1.6 初稿未识别的架构问题**：初稿默认"yaml 是开发态产物"，
> 但**行业基线恰恰是运行态交互生成**——SAP **V/03 就是顾问勾选字段、生成条件表的事务码**
> （研究稿 **S20**：「条件表 V/03：字段目录选字段生成条件表」；**S47** 路径 V/03 → V/07 → V/08 全为**交互式 T-code**）。
> 用户评审明确指出该偏差并拍板如下。

#### （1）三种建设模式的对比

| 模式 | 谁写 yaml | 何时写 | 变更留痕 | 回滚 | 判定 |
|---|---|---|---|---|---|
| **① 开发态预置** | 开发人员 | 发版 | **git 天然有** | `git revert` | 本期 T0 采用 |
| **② 运行态自举** | **顾问 / 专家** | **系统运行中，随时** | **须新建配置变更历史** | **须新建快照** | **方向采纳，界面定位见 (3)** |
| **③ 双装载并存** | 开发人员 + 顾问 | 两者 | **两者都导出 yaml 进 git** | 统一 | ✅ **拍板采用** |

**③ 的关键点：不存在两条 SSOT。** 两条路径**都产出 yaml**，汇入同一条
`register_from_directory` → `schema_generator` 管线（§7C.1.1 链路图）——
顾问界面走的是**同一份 yaml 的另一种产生方式**，不是另一套模型。

#### （2）拍板结论（三条）

| # | 拍板项 | 内容 |
|---|---|---|
| **P-1** | **SSOT 仍是 yaml**（修正初稿"SSOT 下移至 `MetaObject`"的立论错误） | `MetaObject` 是**建表中间产物**（因 §7C.1.1 它装不下 yaml 的 4 块：`audit` / `ui_view_config` / `category_config` / `import_export`）。**"让顾问勾字段生成 yaml"因此完全走得通**——`schema_generator` 从不需要那 4 块 |
| **P-2** | **界面定位：仿 SAP V/03** | 顾问在界面**勾选因子 → 预览生成的表结构 → 确认后建表**（研究稿 S20 已取证为行业基线） |
| **P-3** | **本期禁止结构变更** | `key_fields` **冻结**：顾问只能从**既有因子**中选组合，**不得增删 PK**。变更走发版。理由见 (4) |

#### （3）V/03 式界面的最小字段集（治理成本的关键）

**顾问只暴露 4 项，其余全部由平台模板填充默认值**：

| yaml 块 | 界面暴露 | 默认值 | 说明 |
|---|---|---|---|
| `id` / `name` / `fields[]`（键） | ✅ **暴露** | — | 核心：勾选因子 |
| `table_name` | ✅ 暴露（自动生成可改） | 按 `id` 推导 | 避免手填冲突 |
| `semantics` | 部分 | `category: system_entity` | |
| `deletion_policy` | ❌ 不暴露 | `mode: restrict` | **最安全默认** |
| `audit` | ❌ 不暴露 | `enabled: true` + `changed_only` | **平台默认，不可关** |
| `category_config` | ❌ 不暴露 | `owner_auto_permission: false` | **保守默认** |
| `import_export` | ❌ 不暴露 | `conflict_strategy: upsert` + `conflict_key: code` | |
| `ui_view_config` | ❌ 不暴露 | 前端自动生成 | `skip_auto_menu` 由系统定 |

> **这是本节最重要的结论**：**界面只需暴露「因子勾选 + 名称 + 有效期」**。
> 顾问动不了 `audit` / `category_config` / `import_export`，
> **也就动不了最容易出事的权限与审计部分**——运行态自举的**治理成本因此大幅下降**，
> 远低于"完整 YAML 编辑器"方案。

#### （4）为什么本期禁止结构变更（P-3 的依据）

顾问在生产把 `PK1,PK2` 改成 `PK1,PK2,PK3`，**这次变更本身就是一次数据迁移需求**——
已有费率记录的 `keys{}` 缺 PK3，且历史 `calc_result` 引用旧结构。
这不是配置问题，是**元数据版本管理**问题：

| 维度 | 本期禁止结构变更 | 允许结构变更所需 |
|---|---|---|
| 顾问能力 | 勾选**既有因子**组合 | 增删 PK |
| 历史数据 | **无需迁移** | 须迁移 + 须能回滚 |
| 配置变更历史 | 记录行级增删即可 | 须记录**结构版本**（TBD-15） |
| 回滚 | 按行回滚 | **结构回滚，难度陡增** |

**这同时收紧了 TBD-14 的验证条件**（见 §10）：因结构冻结，
`key_schema` 的存在价值**完全取决于「多个 `rate_table` 共用同一 `key`」是否真实发生**——
若键从不复用，则应按 §7B.8 备选 D 内联进 `rate_record.keys{}`。

#### （5）遗留：运行态自举的完整机制（本期**不做**，登记 TBD-16）

| 缺失机制 | 说明 | 本期处置 |
|---|---|---|
| **配置变更历史表** | 运行态改动须有审计流水（who / when / what diff） | **本期不做**（T0 走开发态，git 即审计） |
| **跨环境一致性** | 测试环境有的配置生产没有 | **本期不做** |
| **结构版本化 + 迁移** | 见 (4) | **本期禁止结构变更** |
| **`with_auto_schema` 闸门处置** | 从"禁止"改为"需显式批准 + diff" | **本期不做**（保持现状） |

### 7C.5 给 T0 的口径（T0 方案不变，但边界要写清）

| 约束 | 内容 |
|---|---|
| **C-T0-7** | T0-1~T0-7 走 `meta/schemas/*.yaml` 声明（**yaml 作 SSOT**），`schema_generator` 自动物化表 —— **与平台现状一致，无需新机制**；`MetaObject` 仅为建表中间产物（§7C.1.1） |
| **C-T0-8** | `currency` / `rate_unit` 等主数据引用**不建外键**，只留 `master_data_ref` 标记 —— **Agent / 顾问改 yaml 时不必连带改主数据**（主数据归数据模块） |
| **C-T0-9** | T0 表**不加租户/作用域字段**（本期不需要），但 `rate_table` **预留 `owner_org_id`** 语义位（登记 TBD-15），**避免 T1 后加字段要动 yaml 结构** |
| **C-T0-10** | Agent 生成配置走**同一份 yaml**，**不得旁路写 DB** —— 否则回到"两处真相源"（§7B.4 缺陷 3 同类风险） |
| **C-T0-11** | `status ∈ {draft, approved, inactive}` **必须在 T0 落地**（`rate_table`）—— 它是 C-T0-9 预留机制的唯一现成落点，且 **Agent 生成配置天然需要"先草稿后发布"** |
| **C-T0-12** | **`key_fields` 本期冻结**（§7C.4.1 P-3）—— 顾问运行态**只能从既有因子中选组合**，**不得增删 PK**；结构变更走发版。理由：增删 PK **本身就是一次数据迁移需求**（历史 `keys{}` 缺新 PK、`calc_result` 引用旧结构），属**元数据版本管理**问题而非配置问题 |
| **C-T0-13** | **yaml 仍是唯一 SSOT**（§7C.4.1 P-1）—— T0 全部走 yaml 声明；`MetaObject` 仅为 `register_from_directory` 产出的**建表中间产物**（因它装不下 `audit` / `ui_view_config` / `category_config` / `import_export` 四块，见 §7C.1.1）。**后续若做运行态自举，顾问界面亦产出 yaml，不旁路构造 `MetaObject`** |

### 7C.6 备选方案与否决理由

| 备选 | 否决理由 |
|---|---|
| **A. 纯 yaml 不物化表** | 业务查询要解析文件 + 内存过滤，**IO 成本挪到每次取价**；且因子目录/费率记录**是数据不是代码** |
| **B. 纯 table（Agent 直改 DDL）** | `CREATE TABLE` **无版本、无回滚、无 diff**；Agent 改结构**不可审查**——与"配置须可审计"直接冲突 |
| **C. EAV 单表 + JSON 列** | **JSON 无法索引等值匹配**；`rate_record` 要按 `keys{}` 组合匹配，EAV 退化为全表扫或给每种键组合建宽表（= 回到 B）。**已在 `permission_rules_v2` 验证：EAV 适合"少而固定"，不适合"多而组合"** |
| **D. 让 Agent 从 DB 反向生成 yaml 并自动注册** | 放开 `with_auto_schema` 的"不注册"闸门。**否决**：DB 里可能有运行时产物（缓存 / 中间态），自动注册会把垃圾变成模型。**改为"提议 + diff + 人工批准"**（§7C.4）——**本期保持现状不动**（§7C.4.1 (5)） |
| **E. 本期就做 yaml ↔ table 双向同步** | **超范围**。yaml → table 已通；table → yaml 仅在**显式迁移/审计**场景按需触发，非运行时常态。**先要一个明确需求再开** |
| **F. 让运行态自举旁路构造 `MetaObject`（不经 yaml）** | **否决**——`MetaObject` 装不下 yaml 的 4 块（`audit` / `ui_view_config` / `category_config` / `import_export`，见 §7C.1.1），旁路构造将**丢配置**；且会形成**第二条 SSOT**。**顾问界面必须产出 yaml**（§7C.4.1 P-1） |
| **G. 本期就做完整 YAML 编辑器供顾问自由编辑全部 13 个块** | **否决**——把 `audit` / `category_config` / `import_export` 暴露给顾问，等于**把权限与审计的开关交给非技术人员**。改为**最小暴露面**（§7C.4.1 (3)：只勾 4 项，其余模板填充） |

### 7C.7 一句话回答题问

> **「灵活因子配置」vs「yaml 声明式动态生成表」不是二选一——后者本就是前者的实现手段**。
> 通用泛化模型（EAV）**不适合因子/键/费率记录**（组合匹配要索引，JSON 列做不到），
> 但**适合"结构随用户任意扩展"的配置本身**（如权限规则，`permission_rules_v2` 已验证）。
>
> **更正的补充（v1.6 拍板）**：这个问题的真正分岔不是"载体"，而是**"谁在什么时候写 SSOT"**——
> **开发态预置**（本期 T0，git 即审计）vs **运行态自举**（顾问在 V/03 式界面勾因子生成 yaml）。
> **拍板走「双装载并存」**：两条路径**都产出同一份 yaml**，汇入同一条
> `register_from_directory` → `schema_generator` 管线，**不存在两条 SSOT**。
> **这在行业上有基线**——SAP V/03 正是"字段目录选字段生成条件表"的事务码（研究稿 S20）。
>
> **Agent 时代真正该加的不是换载体，是三件事**：**作用域（租户/版本，TBD-15）** +
> **生成侧校验（diff 审批，TBD-16）** + **草稿发布分离（T0 已具备 `rate_table.status`）**。
> **其中「本期禁止结构变更」（C-T0-12）是刻意选择**——增删 PK 本身就是数据迁移需求，
> 属元数据版本管理问题，**不在本期解决**。

---

## 8. 优先级与里程碑

### 8.1 需求优先级

| ID | 需求 | 优先级 | 阶段 | 理由 |
|---|---|---|---|---|
| FR-001 | 费率表 + 费率记录（价目表 / 价目行） | Must | P1 | 价格的"库存"，取价前提 |
| FR-002 | 费率类型（条件类型，配置对象） | Must | P1 | 六家全部如此；硬编码不可扩展 |
| FR-003 | 因子目录 + 匹配键表（字段目录 / 条件表） | Must | P0/P1 | 键 = 因子组合，与费率类型同批 |
| FR-004 | 查找序列（存取序列，exclusive/additive） | Must | P1 | 取数范式，首个命中已具备 |
| FR-005 | 计算过程（定价过程）+ 可插拔算子 | Must | P2 | 多层累加的载体 |
| FR-006 | 计算基显式建模 | Must | P2 | 回放必要条件；滚动危险须显式 |
| FR-007 | 多层累加 + 逐层小计 | Must | P2 | 净价 = 多层叠加产物 |
| FR-008 | 取优 / 互斥 / **权重分配（weighted）** | Should | P3 | 多命中怎么收；`weighted` 为**跨域补齐**（研究稿 §4.9D1，Oracle 成本域三处在用），v1.4 并入 |
| FR-009 | 阶梯 + 有效期 | Should | P4 | 费率记录属性 |
| FR-010 | 可解释回放 | Must | P2 | 区别于普通公式的本质 |
| FR-011 | 结果对象宿主 | Must | P2 | 回放的宿主；不建独立单据 |
| FR-012 | 单据链传递策略 | Should | P4 | 搬 vs 算，需显式配置 |
| FR-013 | 事后 / 计划外费用与分摊 | Could | P4.5 | 有价格语义的费用分摊 |
| FR-014 | 追溯调整与补差 | Could | P4.5 | 可后置；红线约束 |
| FR-015 | 事实数据驱动重算 | Could | P6 | 可选；头部普遍"半成品"，平台做成一等即增量 |
| FR-016 | 条件更新（累计用量） | Could | P4 | D6 先不做 |
| FR-017 | 扩展点例程 | Could | P5 | 已有 hook 骨架 |
| FR-018 | 边界登记 | Must | 全程 | 防重复造轮子 |

### 8.2 建议里程碑（对齐研究稿 §7 P0–P6）

#### 8.2.0 T0 先行批次（v1.6 新增 · **零主数据依赖 · 零 `order_line` 依赖**）

> **为何前置**：FR-003 / FR-004 的三件套是**纯配置元数据**，**不引用任何单据、不依赖 `order_line`、不依赖主数据**
> （`currency` 降级为 `string` + `master_data_ref` 标记，见 C-T0-6）。
> 且 `factor_catalog.source_type` 是 **FR-015 的前置**（§7B.6），晚建会阻塞 M8。
> 故从 M1 中切出 T0，**可与主数据补齐并行**（主数据由数据模块负责，见 TR-002）。

| 批次 | 范围 | 对象 | 依赖 | DoD |
|---|---|---|---|---|
| **T0-1** | 因子目录 | `factor_catalog` | **无** | `source_type` 五值 + `is_price_relevant`；**不声明 `data_type`/`aliases`**（C-T0-3） |
| **T0-2** | 匹配键表 | `key_schema` | 无 | **仅** `code`/`name`/`key_fields[]`（C-T0-1） |
| **T0-3** | 查找序列 | `lookup_sequence` | 无 | **仅** `code`/`name`/`steps[{seq,key_schema_id}]`，**无 `exclusive`**（C-T0-2） |
| **T0-4** | 费率类型 | `rate_type` | 无 | 承接 `display_scale`/`numeric_field`（v1.6 由 `key_schema` 迁入） |
| **T0-5** | 排斥组 | `exclusion_group` | 无 | `members[]` + `resolution` |
| **T0-6** | 费率表 | `rate_table` | 无 | `currency` 为 `string` + `master_data_ref: currency`（C-T0-6） |
| **T0-7** | 费率记录 | `rate_record` | 无 | 含 `hit_policy`（默认 `exclusive`）+ `scale[]` + `allocation_weight`（C-T0-4） |

> **全部为 `meta/schemas/*.yaml` 声明，零代码**（`_template.yaml` 范式）。
> **T1 内核（查找序列引擎 / 计算过程执行器 / 多层累加 / 消解范式）亦零主数据依赖**——
> 均为纯函数，**用内存 dict 夹具单测，不碰任何 BO 表**（IF-001 入口签名即"一行 + 表头上下文"）。
> **仅 FR-011 落库挂载（`document_line_id` 指向真实行）受阻于 `order_line`**，可拆两步：先头级（`document_line_id` 可空），待行对象补齐后仅填值。

##### 8.2.0.1 T0/T2 实施进度（2026-10-06 回填）

| 批次 | 状态 | 落点 |
|---|---|---|
| **T0-1 ~ T0-7** | ✅ **已交付** | `meta/schemas/` 七张表（`factor_catalog` / `key_schema` / `lookup_sequence` / `rate_type` / `exclusion_group` / `rate_table` / `rate_record`）；`registry.reload` 注册 + `schema_generator` 实测建表 7/7 通过，C-T0 约束 16 项逐项相符 |
| **T2-1 查找序列引擎** | ✅ **已交付** | `meta/core/lookup_resolver.py` + `meta/tests/test_lookup_resolver.py`（**64 用例**，含 T1-6 追加的 FR-009 定档、两路径同义 parity、二次审查三处守护）。实现 FR-004（有序槽位 / `hit_policy` 下沉 / `(priority,id)` 确定性 tie-break / 回放骨架 `LookupTrace`）与 FR-008（四范式含 `weighted` Σ=1 校验）。**纯函数，零 BO 依赖** |
| **T2-2 计算过程执行器** | ✅ **已交付** | `meta/core/calc_procedure_executor.py` + `meta/tests/test_calc_procedure_executor.py`（34 用例）。实现 FR-005（**算子注册表**落地 C5：新增算子 = 注册一个函数，不改引擎）/ FR-006（基四字段 + `rolling` 与 `base_step` **互斥校验**）/ FR-007（步骤间 additive + 逐层小计 + `rolling` 覆盖）/ NFR-002（**双防线**：字符白名单 + AST 白名单，**禁 `eval`**）。11 个算子已注册 |
| **T1-1 ~ T1-3 结果链三表** | ✅ **已交付** | `calc_procedure`（13 列 · 轴③ `result_semantic` 六值 + `procedure_type` 不写死 price）/ `calc_result`（38 列 · **泛化宿主** `document_type`+`document_id`+`document_line_id`可空+`level`，本期**先挂头级**）/ `calc_detail`（28 列 · `running_net_amount` + `factor_snapshot` + `hit_ids`/`skipped_candidates` 回放骨架）。`registry.reload` 79 对象，**10 张表实测建表全部成功**，conflict_key / business_key / 四块齐全 / 19 项 T1 专项口径逐项通过 |
| **T1-4 定价编排服务** | ✅ **已交付** | `meta/services/pricing_service.py` + `meta/tests/test_pricing_service.py`（**42 用例**，真建表 + 真跑全链路）。把 T2 内核与 T1 配置链串成一条：`price_line`（查表 → 算过程 → 落结果+明细）/ `explain`（IF-002 回放）/ **`write_back`（TBD-9 ② 结果按 `result_semantic` 写回单据字段）** / 有效期过滤 / 草稿价目表拒绝 / dry-run。**全程零 `order_line`、零主数据依赖**（有专项用例守护） |
| **T1-5 定价 API 层** | ✅ **已交付** | `meta/api/pricing_api.py` + `meta/tests/test_pricing_api.py`（**30 用例**，Flask `test_client` 契约测试）。暴露 IF-001/002/003 三条端点；**只做参数校验 + 响应包装**，业务全在服务层。已注册于 `meta/server.py:create_app()`（**实测 `url_map` 三条路由俱在**）|
| **T1-6 阶梯取价（FR-009）** | ✅ **已交付** | `lookup_resolver.resolve_scale`（费率记录**自带档位** · 产**费率**）+ `calc_procedure_executor._tier_bounds`/`_op_tier`（过程**内联档位** · 产**金额**）+ 服务层接线（`scale_qty=base` / 三处改读 `LookupResult.rates`）。两语义（`total` 整单取档 / `incremental` 逐档累进）**同义**由 `TestScaleParity` 逐例守护；服务层 `TestFR009阶梯链路` 5 用例覆盖全链路 + 写回防护 |
| **P2 六对象补齐**（§9.3.1 已声明未落地） | ✅ **已交付** | `meta/schemas/` 六个对象：`allocation_rule`（`basis` 六值 · FR-013）/ `adjustment`（`adjustment_type` 七值含 `override` · FR-014）/ `usage_group`（三上限 · FR-016）/ `cumulative_usage`（FR-016）/ `external_rate_source`（`source` 五值 · FR-015）/ `pricing_period`（`period_type` 四值 + `average_basis` 四值 · FR-015）。`meta/tests/test_pricing_p2_schemas.py`（**69 用例**）逐项守护：注册与 `table_name` · DDL 真建表 · FK 子句**逐条**（含列名）· `pricing_period_id` 已为 INTEGER · 枚举**逐值** + `is_initial` 唯一 · **FK 真约束**（悬空引用抛 `IntegrityError` / 可空 NULL 放行）· 删除保护反补。**六对象零主数据依赖**（C-T0-6） |

> **P2 六对象补齐实施注记**（2026-10-06）：
> ① **平台级 FK 生成缺口（已修）**：`SchemaGenerator._generate_foreign_key` 原先**只对 `PARENT_CHILD` 生成 FK**，且 FK 列名写死 `{target_object}_id`、**完全忽略 `source_field`**。后果有二：yaml 中以 `type: reference` 声明的真引用被**静默丢弃**；`adjustments.original_result_id → calc_result` 会推出**表内不存在的 `calc_result_id`**，建表即失败。现把 `REFERENCE`（须显式声明 `source_field`）纳入生成门，并让 FK 列名优先取 `source_field`。**实测影响面**：全仓 13 条 `reference` 关系，其中 4 条无 `source_field` 被新门挡掉，仅 **2 条存量关系**（`change_events.audit_log_id→audit_logs`、`change_subscriptions.user_id→users`）新获 FK——两者目标表与源列均存在，且既有测试用手写 DDL 建表（无 FK 子句）故不受影响；
> ② **`calc_result.pricing_period_id` 由 string 收紧为 INTEGER**（原按 `pricing_periods.code` 引用 → 改按 `id`），与其余 `*_id` 口径统一；`data/app.db` 实测**无任何 `calc_*` / `rate_*` 表**，故无存量数据风险。注：`schema_generator` 只支持 CREATE + ADD COLUMN，类型变更**仅对新建库生效**；
> ③ **删除保护反补**：`allocation_rule` / `external_rate_source` / `pricing_period` 的 `restrict_on` 登记服务层友好提示（指向 `calc_results.*`），`calc_result.restrict_on` 登记 `adjustments.original_result_id`；DB 级 FK 兜底。口径与同期 foundation 的 `address` / `calendar` 做法一致；
> ④ **仍待接线的部分**：这六个对象目前是**声明已落地、端点未实现**——`allocate`（P4/M6）/ `reprice`（P6/M8）/ 条件更新累计（M5 剩余）仍待开工；`conversion` **不在 §9.3.1 清单内**且已由 D19 / TBD-10 后置 P6，本轮不含。

> **测试假绿缺陷 · 第一类「raw-SQL 门控」（2026-10-06 实测，已闭环）**：`meta/tests/conftest.py::_check_raw_sql_in_tests` 会把**含裸 SQL DML 的测试文件整体 skip**（正则 `INSERT INTO` / `UPDATE x SET` / `DELETE FROM`；白名单仅 `meta/tests/factories/` 目录与 `ALLOW_RAW_SQL=1`）。实测默认口径下**三个文件**命中、且均报 `Success: True`（假绿）：`test_metadata_driven_validator.py` **42 skipped**、`test_pricing_service.py` **42 skipped**、`test_pricing_api.py` **30 skipped**；加 `ALLOW_RAW_SQL=1` 后分别 42 / 42 / 30 **passed**——测试本身是真绿的，只是默认不跑。三处均已按 factories 口径闭环：校验器批次 `9e216d90`（`_metadata_validator_helpers.py`）；本批次新增 `_raw_sql_bridge.py`（`insert`/`update`/`delete`），`test_pricing_service.py` / `test_pricing_api.py` 迁移后默认口径 **42 / 30 passed 且零 skip**（迁移仅动 DML，`assert` / `pytest.raises` 零改动，已逐行复核）。**根因**：DML 写在测试文件内，而非 `meta/tests/factories/`（conftest 的唯一白名单目录）。**本次 P2 测试已按 factories 口径落地（`_pricing_p2_helpers.py`），默认口径即运行。**
>
> **测试假绿缺陷 · 第二类「用例内无条件 skip」（另一根因，未闭环）**：`test_change_notification_integration.py` 默认 **14 skipped**，但该文件**零 raw-SQL 匹配**——14 条来自用例体内的**无条件 `pytest.skip(...)`**（共 15 处，覆盖两个测试类：`"Change notification requires full app context"` × 8、`"…requires ManageService with proper registry setup"` × 7）。这是**测试用例未实现**（占位跳过）而非门控误伤，与第一类不可混为一谈，单列为独立待办。

> **T2-1 / T2-2 实施中纠正的四处问题**：
> ① **TR-006 算术错误**：原文"100×.5 + 200×.3 + 300×.2 = 140"实为 **170**（50+60+60），已修正；
> ② `keys{}` 为 json **不可索引**，取价须先按 `rate_table_id + key_schema_id` 收窄（`idx_rate_record_lookup`）再在结果集内比对——这是 C-T0-12 结构冻结的既定代价，已写入 T0-7 遗留说明；
> ③ **步骤级控制项与算子参数须分离**：`rolling` / `base_step` / `subtotal_key` / `condition` 是"步骤怎么参与累加"的控制项，**不是算子业务参数**。原实现混在 `params` 内导致互斥校验可被绕过，已改为从步骤顶层读取（顶层优先，兼容 params）；
> ④ **只读算子须在累加之后执行**：`round` / `aggregate` / `derived` / `track` 返回 `0.0` 不参与累加，但需读到"含本步"的 `running_net_amount`，故在累加后**补跑一次**（原实现先执行后累加，导致 `aggregate(source="running_net_amount")` 取到本步之前的净额）。
>
> **T1 三表的两处设计取舍**（实施时明确，登记备查）：
> ① **`calc_result` / `calc_detail` 对过程与费率类型只存字符串快照（`process_code` / `rate_type_code`），不建整型外键** —— 结果是**历史快照**，源记录被删后仍须可回放（FR-010）；建外键会产生孤儿。代价是删除保护须由业务层承担，故两表 `restrict_on` 为空，这是**有意取舍而非遗漏**；
> ② **`calc_detail` 不冗余存 `currency` 与 `bo 宿主字段`** —— 它是 1:N 从属行（`business_key = [result_id, seq]`），币种与宿主已在 `calc_result` 上，重复存会造成两份真相源。
>
> **FR-011 当前落点**：因本仓 `bo_sub_category: document` 仅 `sales_order_enhanced.yaml` 一个且**单头无行**（`order_line` 对象缺失），本期按 §8.2.0 的两步法**先挂头级**（`document_line_id = null` / `level = header`）。待 `order_line` 补齐后**仅填 `document_line_id`**，三表结构与 T2 内核**零改动**。
>
> **T1-4 编排层实施中纠正的六处问题**（都是"单测能过、语义是错的"类型，值得记录）：
> ① **两个序列不可混用**：`lookup_sequence.steps[]`（查找槽位 `{seq, key_schema_id}`）与 `calc_procedure.steps[]`（计算步骤 `{seq, element_type}`）是**不同配置**。初版把计算步骤直接喂给 `lookup()`，报 `KeyError: key_schema_id`。现由 `sequence_code` 显式指定，留空则跳过查表（适用于费率已在单据上的情形）；
> ② **json 列须反序列化**：`rate_records.keys` 从 sqlite 读出是 **json 文本**，`Candidate.from_dict` 未解析 → 下游 `ck[k]` 报 `string indices must be integers`；
> ③ **NULL 数值须兜底**：`rate` / `priority` 为 NULL 时原实现透传 `None`，下游 `int + None` 抛 `TypeError`；
> ④ **加权分支判定须区分"全空/部分空/全有值"**：原用 `any(w is not None)` 使"全空"也走进加权。FR-008 的「不可混用」只约束**部分有值**；
> ⑤ **`lookup_amount` 应始终在公式白名单内**：未走查表时它缺失属正常情形，不该报"变量不在白名单"这种安全错误；
> ⑥ **回放接口须归一数值/布尔**：sqlite 可能把 REAL/BOOLEAN 读回 `str` / `0`，`explain` 已统一 `_to_num` / `bool` 归一，否则前端拿到 `"100.0"` 字符串做不了算术。
>
> **一条语义边界（实测确认）**：`calc_detail.skipped_candidates` 记的是「**因键不匹配 / 被更小 seq 槽位抢先**而跳过」的候选；**同槽位内**被 precedence/exclusive 取一落选**不算 skipped**——那是消解范式的正常结果，不是"跳过"。
>
> **T1-4 二次审查补的三处不变量**（都是首轮「23 个用例全绿」时查不出来的，因为它们只在**跨调用**或**列名不对**时才显现）：
> ① **重算须作废旧结果**：同一宿主（`document_type`+`document_id`+`document_line_id`）重复定价，旧行置 `status='invalid'` 而非删除——`calc_result.status` 枚举里 `invalid` 的语义正是「已被重算取代，保留以便审计」。首轮实现只追加不留痕，`explain` 只查 `active`，会返回 2 条互相矛盾的结果；
> ② **作废 + 新写 + 明细必须同事务**：否则中途失败会留下「有 `calc_result` 无 `calc_detail`」的孤儿结果，而 FR-010 要求「可解释 = 可回放」，孤儿结果无法解释。实现上用 `bo_framework` 的 `transaction()`，裸 sqlite 连接退化为 `SAVEPOINT`（**不能用 `BEGIN`**——python sqlite3 默认已在隐式事务中）；
> ③ **明细金额列名是 `extended_amount` 不是 `amount`**：归一化列表里写错列名，导致回放接口明细金额**始终返回 `None`** 而非数值。这是典型的"加了一行归一代码但没验证它作用在哪个字段上"。

> **T1-5 API 层二次审查补的四处问题**（30 用例全绿后才查出，与前几轮同型：**实现正确但缺跨字段 / 跨调用不变量**）：
> ① **`best` 范式永不可达**：服务层 `price_line` 未透传 `measure`，而内核 `resolve_candidates` 对 `best` **绝不隐式默认**（缺 `measure` 直接抛 `ResolutionError`）。即 FR-008 的 `RESOLUTION_BEST` 虽在服务层签名里，**实际调不通**。已补 `measure` 透传 + API 侧校验 `resolution=best` 时 `measure` 必填；
> ② **`level` 与 `document_line_id` 的一致性此前无人在入口守护**：`calc_result.yaml` 的跨字段不变量（`header`⟺NULL / `line`⟺非 NULL）只在表声明里写了语义，API 层若不校验，会写入**自相矛盾的结果行**（`level=line` 却无行）。现于入口做**推导 + 双向一致性校验 + 枚举白名单**（缺省按 `document_line_id` 推导；`line` 必带行、`header` 必不带行）；
> ③ **非法 `resolution` 的错误码串号**：`resolution` 写错（如 `first`）会被内核报成 `ResolutionError` → **422「改配置」**，而它其实是**参数写错（400「改请求」）**。现于入口白名单拦为 400。**错误码分界据此确立：400 = 改请求（参数错 / 编排层找不到过程、价目表、查找序列）；422 = 改配置（`ResolutionError` 候选消解失败 / `CalculationError` 未注册算子等结构性矛盾）**；
> ④ **HTTP 端点命名落地**：§9.3.3 原为建议路径（`/price` `/explain`），实际实现按 RESTful 资源语义定为 `calculate` / `result/<document_type>/<id>` / `write-back`，且**路径里的 `document_type` 即 `calc_result.document_type`**（不是 `object_type`）——与表字段同名，减少心智转换。

> **一条环境事实（实测）**：**live 注册点是 `meta/server.py:create_app()`**（`__main__` 第 1066 行调用它，含自己的 55+ 条 `register_blueprint`）。而 `meta/core/app_builder.py:with_blueprints()` 是**并行的、当前已损坏的**路径——它 `from meta.api.identity_api import identity_bp`，而该模块**在 git 中从未存在**（真实模块是 `meta.api.object_identity_api`），故该函数一旦被调用必然 `ImportError`。本轮**两处都同步注册**（保全照既有 parity），但**验证以 `create_app()` 的 `url_map` 为准**。

> **T1-6 / FR-009 阶梯取价实施注记**（2026-10-06；核内 `resolve_scale` + `_op_tier` + 服务层接线）：
> ① **定档产出「费率」而非「金额」**：`lookup()` 的产出量纲与 `Candidate.value` 一致（TR-006 权重夹具 `100×.5+200×.3+300×.2=170` / `base=1.0`，即费率口径；下游过程再乘数量）。故 `resolve_scale` 返回**等效费率**——`incremental` 用 `Σ(分段量 × 档费率) / 总量`。**若返金额，同一个 `lookup_amount` 变量会时而费率时而金额，配置无法统一书写**；
> ② **定档时机 = 记录选定之后**：对标 SAP 存取序列（先选中条件记录、再按数量落 Staffel 档位）。故 `resolve_candidates` 保持按 `value` 比较（比优发生在定档前）——这是**有意的语义边界，不是遗漏**；
> ③ **`scale` 与 `keys` 同为 json 列，但容错策略必须相反**：`keys` 解析失败 → 该候选匹配不上（保守，不会算错价）→ 静默当 `{}`；`scale` 解析失败 → 若静默当"不分档"就会取占位 `value`（分档记录的 `value` 多半是 0）→ **静默算出错误价格**，故**必须抛 `ResolutionError`**（HTTP 层 422）；
> ④ **修掉 `_op_tier` 的真实缺陷**：原写 `float(t.get("to", float("inf")))` 只兜「缺键」，兜不住「**显式 null**」；而 yaml 里顶档写 `to:`（留空）读出正是 `None`，`float(None)` 抛 `TypeError`。该缺陷由 `TestScaleParity` 首轮 10 例失败暴露（**不是新代码错，是既有实现错**）。现抽 `_tier_bounds` 同时兜两种情形；
> ⑤ **两路径同义由可执行断言守护**：`resolve_scale`（自带档位 · 产费率）`× 数量` **==** `_op_tier`（内联档位 · 产金额），由 `TestScaleParity` 逐例（`total`/`incremental` × 10 个数量点，含 **0 / 负值** / 档界 / 顶档）断言。**优于抽公共函数**：两条路径的输入结构本就不同，抽函数会强行耦合；用断言守护可在任一侧改动导致分叉时**立即失败**；
> ⑥ **服务层三处改读定档后费率**（`LookupResult.rates` 作**单一真相源**）：`rate_{id}` 初值 / `calc_result.rate` 落库 / 加权分支。原因：分档记录的 `c.value` 是**无意义占位**，下游若继续读会把 0 当单价写回单据——这是**静默错价路径**，故服务层 `TestFR009阶梯链路` 专设「写回单价 ≠ 0」用例守护。
>
> **T1-6 二次审查补的三处**（都是「一次实现看起来对、但存在**不报错却算错价**的旁路」）：
> ① **`scale` 只兜「json 畸形」兜不住「**形状不对**」**：原实现 `if not isinstance(scale, list): scale = []`，把「对象而非数组 / 元素非 dict」静默降级为"不分档"——与畸形 json 同样会取占位 `value` 得出错价。现对「已声明但形状不符」一并抛 `ResolutionError`（`None`/空串/空数组仍合法 = 不分档）；
> ② **`best` 范式与分档记录组合会静默选出错误记录**：`best` 按 `c.value` 比优，而分档记录的 `value` 是**占位值**（真实费率由档位定），比优 = 比一串占位值。正确的比优须按**定档后费率**（需数量），本期未实现，故**显式拒绝**（`ResolutionError` → 422），引导配置者改用 `precedence`；
> ③ **负数量下两条路径分叉**：原 `resolve_scale` 只判 `q == 0`，负数量落入档位匹配 → `total` 找不到覆盖负值的档位 → **抛错**；而 `_op_tier` 对同一输入**静默返 0**。`TestScaleParity` 原来只测非负值，故未暴露。现统一为「非正数量 → 费率 0」（与 `_op_tier` 同口径），并把负值纳入 parity 参数集。**退货/红字应由 `calc_result.sign` 表达，不在阶梯算子内取负**。
>
> **FR-009 本期边界登记**（四条，均为**有意取舍而非遗漏**）：
> ① **`scale_divisor`（分档基数字段）本期不消费** —— 它要求读单据行字段，与「零 `order_line` / 零主数据」前提冲突，待行对象补齐后接；本期阶梯基数一律取计算基 `base`；
> ② **「按定档后金额比优」本期不做** —— `resolution=best` 的比优发生在**记录层**（按 `value`），不比较定档后金额，与 SAP 语义一致（见 ②）；且**分档记录 + `best` 已显式拒绝**（见二次审查②），不存在静默误导；
> ③ **定档留痕落 `calc_detail.factor_snapshot["scales"]`**（复用既有 json 列，**零 schema 改动**），记「落到哪一档 / 定出什么费率」，供 FR-010 回答"为什么是这个值"。
> ④ **`LookupResult.rates` 的 key 是整型**（`{candidate_id: rate}`）；`to_dict()` 经 `json.dumps` 后 key 会变字符串。当前仅**进程内**消费（`pricing_service` 不经 JSON 读它），故本期不处理；若未来经 API 暴露，消费端须做 `int()` 回转。

| 里程碑 | 范围 | 关键交付 | DoD |
|---|---|---|---|
| **M1 = P0 概念定型** | 六件定成平台对象 / 枚举；费率类型落为配置对象 | 元模型草案（表 + 字段 + 枚举）**（v1.6：T0-1~T0-7 已先行交付此 DoD）** | 六件各有归属对象，与 §5.2 边界不冲突；费率类型字段与 §4.1 一致 |
| **M2 = P1 单层取价 ★** | 一个物料 × 一个客户 → 一个单价 | 匹配键表 + 因子目录 + 费率表 + 费率记录（含币种 / 计量单位）+ 查找序列（exclusive） | 命中即止，能回答"命中哪一行"；跨币种费率记录可换算 |
| **M3 = P2 多层累加 + 回放 ★** | 基价 → 折扣 → 附加费 → 税 → 运费 | 费率类型分类 + additive + 计算过程序列（带 `element_type`）+ 计算基四字段 + 小计 + 计算明细 + `calc_result` / `calc_detail` | 逐层小计可回放；每步记 `base_level`/`base_source`/`base_step`/`rolling`（默认不滚动，滚动与 `base_step` 互斥） |
| **M4 = P3 取优/互斥** | 多同类命中怎么收 | Precedence vs Best Price（显式选择）+ 排斥组 | 同一数据两范式结果可分别复现 |
| **M5 = P4 阶梯 + 有效期 + 条件更新 + 执行期重算** | 按量分档 / 按日期生效 / 合同量累计 / 发货开票按实际量重算 | 费率记录属性扩展 + 用量累计 + `freeze_policy`/`reprice_trigger`/`qty_basis` | 阶梯 / 过期 / 用满三测例；三种组合各一测例；已开票行重定价被拒 |
| **M6 = P4.5 事后费用与分摊** | 发票 / 收货 / 服务确认 / 结算上的计划外费用摊到 PO / 收货 / 订单行，可追溯补差 | `allocation_rule` + `calc_result` 费用口径字段 + `adjustment`（可后置） | 一笔费用按 6 种基数摊到行且可回放；`target=cost`/`expense` 各一测例；已过账追溯被拒或留痕 |
| **M7 = P5 扩展点接线** | 复杂定制逃生门 | `ActionType.BUSINESS` hook 接线 VOFM 式例程 | 自定义例程可插拔，不改引擎 |
| **M8 = P6 事实数据驱动重算（可选）** | 优质优价 + 大宗贸易 | **因子目录事实源分类（T0-1 已交付，此处只做消费）** + `external_rate_source`/`pricing_period` + `fact_snapshot`；`qty_basis` 扩容 | 质检值命中匹配键表得升贴水；干吨折算参与计价；暂定价→终价差值可配对回放；`fact_snapshot` 缺失拒绝结算 |

> 里程碑的任务清单与验收细则可另立《定价引擎实施计划》（对齐 [rule-model 实施计划](./2026-10-02-rule-model-implementation-plan.md) 范式）。

---

## 9. 变更设计方案（RFC）

### 9.1 As-Is 分析

- **现有架构**：`meta/core` 下 13 个 `*engine*.py`（workflow / doc_flow_derive / doc_flow_batch / association / key_template / index_rule / enrichment / deep_mutation / deep_insert / constraint / bo / async_interceptor / analytical），**无定价引擎**；全仓无 `*pricing*` 文件。
- **现有痛点**：单据行只有价格字段（`unit_price` / `net_price` / `total_amount`），无"算价格的机器"；`compute` 只做单表达式尾算，无序列 / 无小计 / 无候选竞争 / 无回放。
- **可复用代码路径**：
  - 条件内核：`meta/core/condition_parser.py` / `condition_evaluator.py` / `condition_converter.py`；
  - 分组 + 首个命中 + tie-break：`meta/core/rule_executor.py`（`default_by_priority`，**L1432 起**）+ `MetaDefaultRule`（`meta/core/models.py` **L224-270**）；
  - 安全求值：`meta/core/safe_expr_evaluator.py` + `FormulaFunctionRegistry`（`rule_executor.py` L229-230）；
  - 值计算宿主：`MetaComputation`（`meta/core/models.py` **L207-221**）；
  - 单据宿主范式：`meta/schemas/examples/sales_order_enhanced.yaml`（`bo_category: transactional` L6-7 + `rel_lines` `composition 1:N / ownership / cascade_delete` L378-387）。

### 9.2 目标状态（Target State）

- **新增独立定价引擎**（D1：独立引擎，非扩展 `compute`）—— `determination`（确定）过程类型第一个实例 = `pricing`。
- **元模型通用性与命名声明（v1.3 拍板，v1.4 补入第四消解范式）**：本引擎的**元模型 = "通用确定与计算"**（可配置序列 + 量 × 率 + 多步累加 + 候选消解），**本期首个过程实例 = `pricing`**；元模型层一律**领域中立命名**（费率类型 / 查找序列 / 计算过程 / 费率记录 / 计算结果），SAP 术语降为**业务别名**（§9.3.1 命名与溯源对照表）；通用化只参数化**三轴**（`base_source` / `rate_source` / `result_semantic`），**成本归集层与碳组织边界不属本引擎**（§1.4 N9）。**候选消解共四范式**（v1.4 补入第四范式 `weighted` 权重分配：多候选不取一、按权重加权累加，承载于 `rate_record.allocation_weight`，对标 Oracle 成本域 Sourcing Rule 分配百分比，详见 §9.3.1 B2 与 FR-008）。**v2.0 跨域验证（研究稿 §4.9）**：三轴在 Oracle **成本域**（`总成本 = 固定 + 变动[单位资源成本 × 消耗数量]`，`单位成本 = 总成本 ÷ 缩放数量`）与**碳域**（`排放量 = 活动数据 × 排放因子`）**逐字同构**；**v2.1 Palantir 对照**（研究稿 §4.10）：**两条通用化路径的分野不在能力而在"谁承担域特有逻辑"**——本引擎走"元模型 + 参数化"，故域特有逻辑压力落在本引擎，**§1.4 N9 边界是这条路径的必要成本，不是保守**。
- **两条对象链分开**（研究稿 §4.6）：
  - **配置 / 主数据链**（计划侧，元模型）：因子目录 → 匹配键表 → 查找序列 → 费率类型 → 计算过程；费率表 + 费率记录（业务别名：价目表 / 价目行·条件记录）；
  - **单据运行时链**（事实侧）：单据头 → 单据行 → `calc_result`（结果行）→ `calc_detail`（步骤明细）。
- **配置链三原语 vs 定价特例的职责分离（v1.6 · §7B）**：
  - **通用骨架（平台层三原语）** = **因子**（看什么）/ **键**（按什么组合）/ **取数计划**（先查谁、命中算不算完）。**平台内已在四处自发实现，无一通用**（数据权限 / 属性确定 / 派生 / 文档流，见 §7B.3），故将其**在文档层立口径**；
  - **定价特例（不通用化）** = `rate_type` / `calc_procedure` / `base_level` / `scale` / `allocation_weight` / `hit_policy` / `exclude_bo`——依判据「换个业务还需要吗」全部留在定价层（B1 承诺成立）；
  - **落地动作**：`key_schema` 收窄到仅 `key_fields[]`（量级换算 → `rate_type`，阶梯基数 / 排除 → `rate_record`）；`lookup_sequence` 收窄到仅槽位顺序（`exclusive` → `rate_record.hit_policy`）；`factor_catalog` 收窄到仅 `source_type` + `is_price_relevant`（**不重复 `MetaField` 的 `data_type`/`aliases`**）。**不新增对象数量**。
- **关键变更**：
  1. 新增定价元模型对象（FR-001 ~ FR-003、FR-005、FR-013~FR-015）；
  2. 新增定价引擎执行器（查找序列命中 + 过程逐步执行 + 计算基求值 + 取优消解）；
  3. 新增结果对象并复用 `document` BO 范式（FR-011）；
  4. 与 `default` / `compute` / `doc_flow` / `validation` / `rollup` 按 §5.2 边界接线（IF-002~IF-006）。

### 9.3 详细设计

#### 9.3.1 对象模型（数据模型）

> **命名原则（v1.3 拍板）**：**元模型层一律领域中立**（费率 / 查找 / 计算），**SAP 术语降为"业务别名"**，只出现在本节的"业务别名"与"溯源（对标）"列，**不再作主名**；实例层保留业务别名。命名三段式 = **主名（领域中立）· 代码标识（snake_case）· 业务别名（SAP 等）**。

**命名与溯源对照表（v1.3）**

| 主名（业务别名） | 代码标识 | 业务别名 · 研究稿术语 | 结构溯源 |
|---|---|---|---|
| 因子目录（字段目录） | `factor_catalog` | 字段目录 | **SAP 骨架**（KOMG/KOMP）；SF Context / `IsPriceImpacting` |
| 匹配键表（条件表） | `key_schema` | 条件表 | **SAP 骨架**（V/03·M/03） |
| 查找序列（存取序列） | `lookup_sequence` | 存取序列 | **SAP 骨架**（V/07·M/07）；D365 find-next |
| 费率类型（条件类型） | `rate_type` | 条件类型 / 价格类型 / 因子类型 | **六家趋同**（SAP V/06；SF pricing element）；`rate_source` 为 v1.3 新增轴② |
| 计算过程（定价过程） | `calc_procedure` | 定价过程 | **SAP 骨架**（V/08）；Oracle Pricing Algorithm；SF Pricing Procedure |
| 计算步骤 | `calc_procedure_step` | 过程步骤 | 多家趋同 |
| 费率表（价目表） | `rate_table` | 价目表 | Oracle Price List；金蝶价目表（仅审核态） |
| 费率记录（价目行 / 条件记录） | `rate_record` | 条件记录 | SAP 条件记录 VK11；SF Price Book Entry |
| 计算结果（结果行） | `calc_result` | 定价结果 | SAP `KONV`；Oracle `Charge` |
| 计算明细（步骤明细） | `calc_detail` | 定价明细 | Oracle `ChargeComponent`；SF waterfall |
| 调整（追溯 / 补差） | `adjustment` | 追溯调整 | Oracle retroactive price adjustment；SAP 后续借 / 贷项 |
| 分摊规则 | `allocation_rule` | — | **Oracle LCM 独有贡献**（六种基数） |
| 累计用量（累计值） | `cumulative_usage` | 累计值 | SAP Condition Update |
| 排斥组 | `exclusion_group` | — | SAP Condition Exclusion；Oracle Incompatible |
| 外部率源（外部价格源） | `external_rate_source` | 外部价格源 | SAP MIC + DCS + Quotation；SF `IndexRate` |
| 计价期 | `pricing_period` | 计价期 | SAP F&A；SF `PriceRevisionPolicy` |

**通用化三轴（v1.3）**

| 轴 | 归属对象 | 字段 | 取值（"域"示例） |
|---|---|---|---|
| ① 计算基来源 | 计算明细 `calc_detail` | `base_source` | `pricing_quantity`（定价）/ `activity_quantity`（碳 · 作业）/ `value` / `weight` / `volume` / `energy` / `hours` / `attribute` / `formula` |
| ② 率载体 | 费率类型 `rate_type` | `rate_source` | `rate_record`（价目行 · 排放因子 · 作业费率）/ `external_quote`（外部报价）/ `formula`（公式） |
| ③ 结果语义 | 计算过程 `calc_procedure` | `result_semantic` | `price`（默认）/ `cost` / `emission` / `tax` / `hours` / `quantity` |

> **通用化等价性（v1.3）**：改配三轴，同一引擎即可算 **销售定价**（定价数量 × 价目行 → `price`）、**碳排放**（活动量 × 排放因子 → `emission`，Scope1→2→3 逐层累加）、**作业成本**（动因量 × 作业费率 → `cost`）。**成本归集层 / 碳组织边界与合并层不属本引擎**（§1.4 N9）。

**A. 配置 / 主数据链（元模型，非事务数据）**

| 对象 | 关键字段 | 溯源（对标） |
|---|---|---|
| `factor_catalog`（业务别名：字段目录） | `field_id` / `object_type` / **`source_type ∈ {static, master, quality, measurement, market}`** / `is_price_relevant`<br>**（v1.6 收窄：不声明 `data_type` / `aliases`，引用 `MetaField`；本表只承载 `MetaField` 不具备的两项能力，见 §7B.5）** | SAP 字段目录（KOMG/KOMP）；SF Context / `IsPriceImpacting` |
| `key_schema`（业务别名：条件表） | `code` / `name` / `key_fields[]`（来自因子目录）<br>**（v1.6 收窄：仅匹配维度。`display_scale` / `numeric_field` → `rate_type`；`scale_divisor` / `exclude_bo` → `rate_record`，见 §7B.5）** | SAP V/03（SD）/ M/03（MM） |
| `lookup_sequence`（业务别名：存取序列） | `code` / `name` / `steps[{seq, key_schema_id}]`<br>**（v1.6 收窄：`exclusive` 已下沉为 `rate_record.hit_policy`，序列只管"第几槽位、用哪把键"，见 §7B.5）** | SAP V/07 / M/07；D365 find-next |
| `rate_type`（业务别名：条件类型，**配置对象**） | `code` / `name` / `rate_class ∈ {price, discount_surcharge, tax, freight, statistical}` / `calc_type ∈ {percent, fixed, quantity, formula}` / **`rate_source ∈ {rate_record, external_quote, formula}`（率载体 · 轴②）** / `sign ∈ {+, -}` / `rounding` / **`exclusion_group_id`（v1.6 实施时改：原 `exclusion_group` 存 string 引用 code → 改为整型外键，否则 `exclusion_group` 表孤立无引用）** / `manual_allowed` / `mandatory` / `statistical` / **`lookup_sequence_id`（v1.6 实施时改：原存 string 引用 code → 改为整型外键，与其余 `*_id` 口径统一）** / **`display_scale` + `numeric_field`（v1.6 由 `key_schema` 迁入 · 量级换算属"怎么算"）** | SAP V/06；SF pricing element |
| `calc_procedure`（业务别名：定价过程） | `code` / `name` / `procedure_type`（首期 = `pricing`）/ **`result_semantic ∈ {price, cost, emission, tax, hours, quantity}`（结果语义 · 轴③，默认 `price`）** / `steps[{seq, element_type, rate_type_id?, condition?, params{}}]` / `subtotal_keys[]` | SAP V/08；Oracle Pricing Algorithm；SF Pricing Procedure |
| `exclusion_group`（排斥组） | `code` / `members[]` / `resolution`（保留较高价 / 前置优先；**取值示意，研究稿未给枚举**） | SAP Condition Exclusion OV31/OV32；Oracle Incompatible |
| `usage_group`（业务别名：条件更新组） | `code` / `max_amount` / `max_quantity` / `max_documents` | SAP Condition Update |
| `allocation_rule`（分摊规则） | `id` / `basis ∈ {equal, value, quantity, weight, volume, manual}` / `manual_factor` / `group_by` / `rounding` / `floor` / **`target ∈ {cost, expense}`** | Oracle LCM 6 基数；SF DDS 规则决策表 |
| `external_rate_source`（业务别名：外部价格源） | `id` / `source ∈ {platts, lme, ice, index, custom}` / `quote_code` / `calendar_id` / `fallback_rule` | SAP MIC + DCS + Quotation；SF `IndexRate` |
| `pricing_period`（计价期） | `id` / `period_type ∈ {shipment_date, receipt_date, invoice_date, fixed_range}` / `start_offset` / `end_offset` / `average_basis ∈ {close, average, first, last}` / `rounding` | SAP F&A 计价期；SF `PriceRevisionPolicy` |

**B. 费率记录（事务性主数据 = 费率记录 / 业务别名：价目行 · 条件记录）**

| 对象 | 关键字段 | 溯源（对标） |
|---|---|---|
| `rate_table`（业务别名：价目表） | `code` / `name` / `type` / `currency` / **`status ∈ {draft, approved, inactive}`**（仅 `approved` 参与取价；**枚举取值示意，研究稿仅述"仅审核态参与取价"**） | Oracle Price List；金蝶价目表（仅审核态） |
| `rate_record`（业务别名：价目行 / 条件记录） | **`code`**（业务键 · **v1.6 实施时补**）· `rate_table_id`（**v1.6 实施时补**）· `key_schema_id` + `keys{}` / `rate_type_id` / `rate` / `value` / `valid_from` / `valid_to` / `currency` / `rate_unit` / `rate_qty` / `scale[]`（阶梯）/ **`scale_semantic`（v1.6 实施时补 · 阶梯两语义之选）** / **`priority`（v1.6 实施时补 · 同组取用优先级 + tie-break）** / **`allocation_weight`（权重 · 第四消解范式 weighted，可空；非空 = 该候选参与"加权累加"而非"取一"，见下方消解范式表）** / **`hit_policy ∈ {exclusive, additive}`（v1.6 新增 · 由 `lookup_sequence.steps[].exclusive` 下沉，默认 `exclusive`，对标 SAP 逐条件自带，见 §7B.4 缺陷 2）** / **`scale_divisor` + `exclude_bo`（v1.6 由 `key_schema` 迁入 · 阶梯基数 / 排除对象属单条记录属性）** / `status` | SAP 条件记录 VK11；SF Price Book Entry；**Oracle Sourcing Rule `source_allocation_percentage` / 工单 `Cost Factor Allocation` / LCM `Charge Basis = % of item price`（跨域同构，见研究稿 §4.9D1）** |
| `rate_supplement`（业务别名：条件补充） | 依附某费率记录的**补充条款**（研究稿 §4.2 第 2 层；本 Spec 未单列 FR，随 FR-001 费率记录交付） | SAP Condition Supplement |
| `cumulative_usage`（业务别名：累计值） | 费率记录**跨单据累计已用量**（合同量用满失效）——由 FR-016 条件更新组驱动 | SAP Condition Update |

**B2. 候选消解的四种范式（v1.4 拍板 · 补齐第四范式 `weighted`）**

> **背景**：前三期只对标**定价域**（研究稿 §3–§4），得到三种"**取一**"范式；**v2.0 跨域对撞**（研究稿 §4.9）在 Oracle **成本域**发现第四种：**多候选不取一，全部参与，按权重加权累加**。该范式在 Oracle 内部**至少三处在用**（Sourcing Rule 分配百分比 / 工单 `Cost Factor Allocation` / LCM `Charge Basis = % of item price`），且它是已设计的 `allocation_rule`（1→N 摊金额）的**对偶**（N→1 合率）。故本期补齐。

| 范式 | 候选如何处理 | 平台承载 | 结构溯源 |
|---|---|---|---|
| **互斥（`exclusive`）** | **取一**（保留较高价 / 前置优先） | `exclusion_group.resolution` | SAP OV31/OV32；Oracle Incompatible |
| **优先级（`precedence`）** | **取一**（逐级覆盖，首个命中获胜） | `lookup_sequence` + 首个命中 | SAP 条件序列；Oracle **Precedence**；**Oracle 碳域因子 5 级链（物料 > 供应商 > 组织 > 政府地点 > 政府通用）**；平台 `default_by_priority` |
| **取优（`best`）** | **取一**（按度量选最优） | 随 D3 口径 | Oracle **Best Price** |
| **权重分配（`weighted`）· ★v1.4 新增** | **全部参与**，按 `allocation_weight` **加权累加**：`result_amount = Σ(rateᵢ × base × weightᵢ)`，`Σweightᵢ = 1` | **`rate_record.allocation_weight`（可空；非空即参与加权累加）** | **Oracle Sourcing Rule `source_allocation_percentage` / `Cost Factor Allocation` / LCM `Charge Basis`**；成本域 `Standard cost = Σ(rateᵢ × allocationᵢ)` |

> **对偶关系**：`allocation_rule`（1 → N，把**一个金额**摊到多行）与 `allocation_weight`（N → 1，把**多个率**合成一个率）共用同一数学形式的两个方向。
>
> **互斥约束（v1.4）**：同一消解组内 **`allocation_weight` 非空的候选与"取一"类候选不可混用**——若组内存在非空 `allocation_weight`，则该组按加权累加执行，`exclusion_group.resolution` / `lookup_sequence` 优先级对其不生效。

**C. 单据运行时链（事务数据，属单据）**

| 对象 | 关键字段 | 溯源（对标） |
|---|---|---|
| **`calc_result`**（结果行） | `document_type` / `document_id` / **`document_line_id`（可空 = 头级）** / `level ∈ {header, line}` / `rate_type` / `element_type` / `base_level` / `base_source` / `base_step` / `rolling` / `base_formula?` / `rate` / `amount` / `currency` / `sign` / `sequence`；**费用扩展**：`origin ∈ {planned, unplanned}` / `charge_source ∈ {order, invoice, receipt, service_confirm, settlement}` / `source_document_type` / `source_document_id` / `target ∈ {price, cost, expense}` / `allocation_basis` / `allocation_rule_id`；**事实扩展**：`rate_source ∈ {rate_record, external_quote, formula}` / `pricing_period_id` / `external_rate_source_id` / **`fact_snapshot`（JSON）** | SAP 条件行 `KONV`/`PRCD_COND`（`KNUMV`+`KPOSN`+`KSCHL`+`STUNR`+`ZAEHK`；`KHERK=D` 头条件）；Oracle `Charge` |
| **`calc_detail`**（步骤明细） | `result_id` / `seq` / `element_type` / `price_element_code` / `rollup_flag` / `skip_running_price` / `unit_price` / `extended_amount` / **`running_net_amount`（仅 `rolling=true`）** | Oracle `ChargeComponent`；SF waterfall |
| **`adjustment`**（追溯 / 补差 / **改价**） | `original_result_id` / `adjustment_type ∈ {subsequent_debit, subsequent_credit, retro_price_change, rebate_settlement, delta_accrual, provisional_settlement, **override**}` / `delta_amount` / `effective_period` / `posted_flag` / **`reason`（`override` 时必填 · v1.5）** | SAP 后续借 / 贷项 + 返利结算；Oracle retroactive price adjustment；**SAP `Price Override` / SF `pricing element = Override` / Oracle 人工覆盖 `override_reason`（TBD-8 已拍板：复用本对象，不另立）** |

**D. 结果元数据（计算结果携带的策略）**

| 元数据 | 取值 | 溯源（对标） |
|---|---|---|
| `price_mode` | `carry` / `recompute_amount` / `repricing`（逐"目标单据类型 × 参考单据类型"，可逐属性 price/shipping/tax 覆盖） | SAP `KNPRS`/`TVCPF`；Oracle Freeze Price/Shipping/Tax；SF Repricing |
| `freeze_policy` | 逐 `price` / `shipping` / `tax`：`recompute` / `freeze` | Oracle `CalculatePricingChargesFlag` 等 |
| `reprice_trigger` | `on_copy` / `on_ship_confirm` / `on_invoice` / `manual` / `scheduled` / `on_quality_result` / `on_pricing_period_end` | SF Repricing；SAP `New Pricing` / `Update Pricing` |
| `qty_basis` | `order_qty` / `delivered_qty`（开票默认）/ `goods_issued_qty` / `billed_to_date_qty` / `dry_weight` / `net_dry_weight` / `assayed_content` | SAP `FKMGK`；Oracle 21D/24C |

**E. 关键枚举汇总**

| 枚举 | 取值 |
|---|---|
| `element_type`（过程步骤算子） | `list_price` / `tier` / `attribute` / `formula` / `manual` / `derived` / `aggregate` / `distribute` / `round` / `track` / ★`quality_premium` |
| `rate_class` | `price` / `discount_surcharge` / `tax` / `freight` / `statistical` |
| `calc_type` | `percent` / `fixed` / `quantity` / `formula` |
| `base_level` | `header` / `line` |
| `base_source`（轴① 计算基来源） | `pricing_quantity`（默认）/ **`activity_quantity`（活动量：燃料消耗 / 用电量 / 工时）** / `value` / `weight` / `volume` / `energy` / `hours` / `attribute` / **`scaled_quantity`（缩放数量：量已归一，取"单位 = 总量 ÷ 缩放数量"的分母，对标 Oracle `per-unit cost = total ÷ scaled quantity`；v1.4 拍板 D19）** / `formula` |
| `rolling` | `true`（cascade，记 `running_net_amount`）/ `false`（cumulative，默认） |
| `source_type`（因子目录事实源） | `static` / `master` / `quality` / `measurement` / `market` |
| `rate_source`（轴② 率载体） | `rate_record` / `external_quote` / `formula` |
| `result_semantic`（轴③ 结果语义） | `price`（默认）/ `cost` / `emission` / `tax` / `hours` / `quantity` |

> **互斥约束**：`rolling=true` 时 `base_step` 不填写；`base_source=formula` 时必填 `base_formula`。

#### 9.3.2 主流程

**流程 A · 单据定价（P1–P2）**

```
单据保存（头 + 行）
  └─ [选源] MetaDefaultRule 确定 rate_table          （default，非本引擎）
  └─ [逐行] 定价引擎调用（行 + 表头上下文）           （IF-001）
       1. 确定计算过程（procedure_type = pricing）
       2. 逐步骤执行 calc_procedure_step：
          - 按 rate_type 的 lookup_sequence 检索 rate_record
            · exclusive：首个命中即停；additive：继续累加
            · tie-break：priority asc, record.id asc
          - 命中后按 calc_type 求值（percent/fixed/quantity/formula）
            计算基 = base_level/base_source/base_step/rolling（FR-006）
          - 产出 calc_detail（含中间小计；rolling=true 记 running_net_amount）
       3. 步骤间 additive 累加 → 净价 / 行金额
       4. 冲突消解（P3）：Precedence 默认 / Best Price 显式 / 排斥组
       5. 产出 calc_result（结果行）+ calc_detail（明细）
  └─ [落库] 展平 unit_price / net_price / extended_amount 到单据行字段
  └─ [尾算] MetaComputation 计算 total_amount         （compute，非本引擎）
  └─ [校验] MetaValidation 用 min/max 快照拦限价       （validation，非本引擎）
```

**流程 B · 下游单据价格传递（P4，FR-012）**

```
下游单据复制 / 发货确认 / 开票
  └─ 读计算结果元数据 price_mode
       ├─ carry            → doc_flow 一对一搬结果字段（不搬明细）
       ├─ recompute_amount → 金额 = 订单单价 × qty_basis 取到的量（不重取价）
       └─ repricing        → 用 qty_basis 作输入重跑计算过程（可能跨阶梯档）
  └─ 红线：已开票 / 已过账行禁止隐式重定价；重定价须显式触发 + 留痕
```

**流程 C · 事后 / 计划外费用与分摊（P4.5，FR-013/FR-014）**

```
来源单据（发票 / 收货 / 服务确认 / 结算）录入一笔计划外费用
  └─ 生成 calc_result{origin=unplanned, source_document_*≠宿主单据}
  └─ 按 allocation_rule{basis, group_by, floor, target} 摊到目标单据行
       → 生成 level=line 分摊明细；头记总额
  └─ 追溯：adjustment{original_result_id, delta_amount}
       → 成对留痕、只结算差额、不改原单据
```

**流程 D · 事实数据驱动重算（P6，FR-015）**

```
质检结果 / 计量值 / 外部报价 → 写入事实源字段（source_type∈{quality,measurement,market}）
  └─ reprice_trigger ∈ {on_quality_result, on_pricing_period_end} 显式触发
  └─ 重跑计算过程（事实源字段可入匹配键表 / 可用于数量折算 / 可经外部报价源 + 计价期取价）
  └─ 结果落 calc_result（含 fact_snapshot 快照）
  └─ 暂定价 → 终价：adjustment{adjustment_type=provisional_settlement} 只结算差额
  └─ 护栏：fact_snapshot 缺失拒绝结算；暂定价与终价配对可查
```

#### 9.3.3 API 设计（v1.6：IF-001/002/003 已实现）

> **实现落点**：`meta/api/pricing_api.py`（`Blueprint('pricing', __name__, url_prefix='/api/v1/pricing')`），
> 注册于 `meta/server.py:create_app()`。**契约测试**：`meta/tests/test_pricing_api.py`（30 用例，Flask `test_client`）。
> **分层纪律**：API 层**只做参数校验 + 响应包装**，业务（查表 / 算过程 / 落库 / 写回）**全在服务层** `PricingService`。

**已实现（IF-001 / IF-002 / IF-003）**

- **定价调用 · IF-001**：`POST /api/v1/pricing/calculate`
  入参 = `process_code` + `rate_table_id` + `slot_keys`（`[{因子: 值}]`）+ `base`，可选 `sequence_code` / `document_type` / `document_id` / `document_line_id` / `level` / `resolution` / `measure` / `valid_on` / `persist`；出参 = 净价 / 行金额 + 结果行与明细。
  **入口校验**：三必填齐备；`slot_keys` 形状；`persist=true` 且给 `document_type` 时须给 `document_id`；`document_line_id` 不可脱离 `document_id`；`level ∈ {header, line}` 且与 `document_line_id` 空值一致；`resolution ∈` 四范式且 `best` 必带 `measure`。
- **回放查询 · IF-002**：`GET /api/v1/pricing/result/<document_type>/<int:document_id>`
  可选 query `document_line_id`（缺省 = 头级）；返回命中 / 剔除候选及原因 + 逐层小计 + 计算基四字段。
  **路径里的 `document_type` 即 `calc_result.document_type`**（宿主元模型对象 ID，如 `sales_order_enhanced`）。
- **结果写回 · IF-003**：`POST /api/v1/pricing/write-back`
  入参 = `document_type` + `document_id`（可选 `document_line_id`）；按 `result_semantic` 约定映射（TBD-9 ②，`WRITEBACK_MAP`）；出参 = `written` / `skipped` / `result_ids`。

**错误码分界（本层确立）**

| 状态码 | 语义 | 触发 |
|---|---|---|
| **400** | **改请求** | 参数错（`INVALID_PARAM`）；编排层找不到过程 / 价目表 / 查找序列（`PRICING_ERROR`） |
| **422** | **改配置** | `ResolutionError`（候选消解失败：权重和不归一等）；`CalculationError`（未注册算子等结构性矛盾） |
| **401** | 未认证 | `login_required`（三条端点均要求登录） |

**尚未实现（P4 / P6）**

- **分摊执行**：`POST /api/v1/pricing/allocate`（FR-013 / FR-014）——依赖 `allocation_rule`（P2 未落地的 5 张表之一），**P4 实装**。
- **重算**：`POST /api/v1/pricing/reprice`（FR-015）——依赖 `reprice_trigger` 消费链与 `external_rate_source` / `pricing_period`，**P6 实装**。

> 端点命名与既有 API 风格（`/api/v1/<module>/<resource>`、`_response_contract` 的 `ok` / `error_response`）一致；
> **命名已于 v1.6 落地**（TBD-3 结项），后续增补端点沿用同一 prefix 与错误码分界。

#### 9.3.4 与既有资产的复用映射

| 资产 | 位置 | 复用方式 |
|---|---|---|
| 条件表达式内核 | `condition_parser.py` / `condition_evaluator.py` / `condition_converter.py` | "适用条件"直接用条件表达式 |
| 分组 + 首个命中 + tie-break | `rule_executor.py` `default_by_priority`（L1432 起）、`models.py` L224-270 | 查找序列"首个命中"借其语义 |
| 安全表达式求值 | `safe_expr_evaluator.py` + `FormulaFunctionRegistry`（`rule_executor.py` L229-230） | `calc_type=formula` / `base_formula` 复用 |
| 值计算宿主 | `MetaComputation`（`models.py` L207-221） | 承接小计行 / 尾算 |
| 单据宿主范式 | `sales_order_enhanced.yaml` L6-7 / L378-387 | `calc_result` / `calc_detail` 挂单据 |

### 9.4 备选方案

| 决策点 | 选项 | 优点 | 代价 | 结论 |
|---|---|---|---|---|
| **D1 引擎形态** | A 独立引擎 / B 扩展 `MetaCompute` 加序列 | A：语义显式、可解释最好、边界清晰；B：零新引擎 | B：`compute` 承不住多层累加 / 取优 / 费率记录 | **选 A**（研究稿 §2.2、§6） |
| **D9 费率类型（条件类型）** | A 配置对象 / B 硬编码枚举 | A：六家全部如此、可扩展；B：实现简单 | B：无法自建、违背 D7 | **选 A** |
| **D13 过程内派生 / 汇总 / 分摊归属** | A 一律归 `allocation` / B 按"是否在计算过程内"切 | B：符合 SF DDS / Oracle Spread Discount / SAP 组条件事实 | A：会把头级折扣分摊切碎 | **选 B**（判据 = 是否作为计算过程的一步） |
| **D15 结果宿主** | A 独立"定价单据" / B 附属于业务单据 / C 仅展平字段 | B：三家一致、不与 `doc_flow` 争单据、明细可回放 | A 多一跳且语义冲突；C 不够（D4 要明细） | **选 B** |
| **D2/D3 取数 / 消解** | Precedence vs Best Price | Precedence：可预测可回放；Best Price：商务最优 | Best Price 需遍历全集 + 先定义度量 | **分层默认**：槽位内 exclusive、步骤间 additive；消解默认 Precedence，Best Price 显式开 |
| **D12 基准滚动** | 不滚动 / 滚动 | 不滚动：可解释、金额可控；滚动：复利式叠加 | 滚动误配会连带放大 | **默认不滚动，滚动显式开** |
| **D18 第四消解范式 `weighted`**（v1.4） | A 只做三种"取一" / B 补"多候选按权重加权累加" | B：Oracle 成本域三处在用的真实范式；补上后"定价专属"降为"定价为首个实例"；与 `allocation_rule` 互为对偶 | B：多一个可空字段 + 一条归一校验 | **选 B**（研究稿 §4.9D1；`rate_record.allocation_weight`，Σweight=1 须归一否则报错） |
| **D19 单位换算放哪一层**（v1.4） | A 塞进 `base_formula` / B 归事实源取值阶段 / C 建完整 `conversion` 对象放引擎内 | B：换算是"单位声明"不是"公式"，混进公式会让同一 `× 率` 无法同时服务 kL 与 GJ，丧失跨域复用 | A：公式失去可复用性；C：新表新枚举，本期收益不可见 | **选 B**（本期只补 `base_source` 枚举 `scaled_quantity`；完整 `conversion` 登记 **TBD-10**） |

#### 9.4.1 研究稿决策点处置映射（D1–D17，回溯表）

> 研究稿 §8 的 17 个决策点在本 Spec 中的处置一览（避免决策散落、便于回溯）：
> **v1.4 追加**：研究稿 v2.0 / v2.1 新增 **D18–D22**（跨域二次研究 + Palantir 对照）已并入下方 D18–D22 行。

| # | 决策点（研究稿 §8） | 处置 | 本 Spec 落点 |
|---|---|---|---|
| D1 | 独立引擎 vs 扩展 `compute` | 采纳 ①独立引擎 | §9.2、§9.4 |
| D2 | 取数范式默认值 | 采纳"分层默认"（槽位内 exclusive / 步骤间 additive） | FR-004、FR-007 |
| D3 | 冲突消解范式 | 采纳 ③（默认 Precedence；Best Price 显式开 + 先定度量） | FR-008 |
| D4 | 定价结果落库形态 | 采纳 ③（字段 + 明细都要） | FR-010、FR-011 |
| D5 | 可解释回放保留策略 | **待定** | TBD-4 |
| D6 | 是否要条件更新（累计用量） | 倾向 ②先不做（P4 后置） | FR-016、TBD-5 |
| D7 | 是否统一"确定引擎" | **✅ 已拍板**：只做定价；元模型按"通用确定与计算"设计（v1.3：参数化三轴 `base_source`/`rate_source`/`result_semantic`，本期首个过程实例 = `pricing`） | §7.2 B1、FR-002、§9.2 |
| D8 | 复制带价 vs 重定价 | **✅ 已拍板**：③逐"目标单据类型 × 参考单据类型"配 `price_mode` 三档 + 逐属性覆盖 | FR-012 |
| D9 | 条件类型：配置对象 vs 硬编码枚举 | 采纳 ①配置对象（仅"计算类型"为属性枚举） | FR-002、§9.4 |
| D10 | 计算基准默认层级 | 采纳 ①行级（表头条件 + 组条件分摊列 P3+） | FR-006、IF-001 |
| D11 | 基准量默认 | 采纳 ①定价数量（预留 `base_formula`） | FR-006 |
| D12 | 基准是否滚动 | 采纳 ①默认不滚动（滚动显式开启） | FR-006、§9.4、R3 |
| D13 | 过程内派生 / 汇总 / 分摊的归属 | 采纳 ②（判据 = 是否在定价过程内） | FR-018 |
| D14 | 数量基准来源 `qty_basis` | **✅ 已拍板**：②开票默认 `delivered_qty`，与"单价是否重取"解耦 | FR-012 |
| D15 | 定价结果的对象宿主 | **✅ 已拍板**：②附属于业务单据 | FR-011、§9.4 |
| D16 | 事后 / 计划外费用归属与去向 | **✅ 已拍板（v1.5）**：**②归定价"费用 / 分摊"子域**——它是 `origin=unplanned` 的 `calc_result`，不新建费用单据、不破 D7；成本侧取值算法仍归成本核算 | FR-013、§9.3.1 C |
| D17 | 事实数据驱动重算归属与节奏 | **✅ 已拍板（v1.5）**：**设计侧③（`reprice_trigger` 枚举一次给全）／实施侧②（只实装 `on_quality_result`）**——另两个触发器依赖尚未实施的对象，先枚举留全、只实装依赖已就绪者 | FR-015、FR-016 |
| D18 | 是否补第四消解范式 `weighted`（权重分配） | **✅ 已拍板（v1.4）**：②补——`rate_record.allocation_weight`（可空），非空即参与加权累加；Σweight=1 须归一否则报错 | FR-008、§9.3.1 B2、TR-005/006 |
| D19 | 单位换算 / 归一化放哪一层 | **✅ 已拍板（v1.4）**：②归事实源取值阶段——取数时上游归一，引擎内 `base` 恒为标准单位；本期只补 `base_source` 枚举 `scaled_quantity`，完整 `conversion` 后置 | FR-006、§9.3.1 E、TBD-10 |
| D20 | 多账簿 / 多估值基础并行是否纳入 | **✅ 已拍板（v1.5）**：**②不纳入**——属"引擎实例化 / 编排"层，非"过程定义"层；将来若做，走**引擎外多次调用**（同 `procedure` 跑 N 次带不同 `context`），**不在引擎内建多实例** | TBD-11（已关闭） |
| D21 | 是否给定价结果补能力接口（interface） | **✅ 已拍板（v1.5）**：**②本期不做**，登记 TBD-12——本期只有一个域，多态零收益；将来多域时它比"硬塞一张表"更保守 | TBD-12 |
| D22 | 是否补"谁能改价"策略位 | **✅ 已拍板（v1.5）**：**②只补最小一条"改价必填原因"**（`adjustment{adjustment_type=override}.reason` 必填），**与 TBD-8 合并实现**；完整权限 / 审批矩阵归权限引擎 | FR-014、TBD-13 |
| D23 | **整体价覆盖（Override）语义是否补**（原 TBD-8） | **✅ 已拍板（v1.5）**：**①补，复用 `adjustment` + `reason` 必填，不新增对象**——六家零分歧的共识机制，与 `adjustment` 同构；另立对象会重复 | FR-014 |
| D24 | **结果 → 单据行字段输出映射是否建对象**（原 TBD-9） | **✅ 已拍板（v1.5）**：**本期不建对象**，改为**按 `result_semantic` 约定写回字段**（零配置零新表）；多过程 / 多结果结构时才需要对象，**接口已预留** | FR-011 |

### 9.5 实施与迁移计划

**实施顺序**（对齐 §8.2；**先依赖后优先级**）：

1. **P0**：元模型定型（六件字段 / 枚举）+ 主数据前置（#11 币种、#16 销售区域渠道 / 产品组）
   - **v1.6 拆分**：元模型定型 → **§8.2.0 T0-1~T0-7（yaml 声明，零代码，零主数据 / 零 `order_line` 依赖，可立即开工）**；主数据前置 → **移交数据模块**（TR-002），本引擎侧**不阻塞**；
   - **T0 须遵守 C-T0-1~C-T0-6**（§7B.7）：`key_schema` 只留 `key_fields[]`、`lookup_sequence` 不含 `exclusive`、`factor_catalog` 不重复 `MetaField`、`rate_record.hit_policy` 默认 `exclusive`、`currency` 降级为 `string`；
2. **P1**：匹配键表 + 因子目录 + 费率类型 + 费率表 + 费率记录 + 查找序列（exclusive）；
3. **P2**：费率类型分类 + additive + 计算过程序列（`element_type`）+ 计算基四字段 + 小计 + 计算明细 + `calc_result` / `calc_detail`；
4. **P3**：取优 / 互斥（Precedence vs Best Price + 排斥组）；
5. **P4**：阶梯 + 有效期 + 用量更新 + 执行期重算（`freeze_policy` / `reprice_trigger` / `qty_basis`）；
6. **P4.5**：`allocation_rule` + 费用口径字段 + `adjustment`（追溯可后置）；
7. **P5**：扩展点接线；
8. **P6**（可选）：事实源分类 + `external_rate_source` / `pricing_period` + `fact_snapshot`。

**风险与缓解**：

| 风险 | 缓解 |
|---|---|
| R1 依赖主数据缺失（币种 / 汇率 / 税 / 价格组）导致引擎空转 | TR-002 分期补齐；对应费率类型不上线；缺失时明确报错不静默错算 |
| R2 Best Price 静默改变金额、不可回放 | **绝不隐式默认 Best Price**；开启须先定义"最优"度量（D3） |
| R3 基准滚动误配连带放大金额 | **默认不滚动**；滚动显式开启；`rolling` 与 `base_step` 互斥校验（D12） |
| R4 已开票 / 已过账行被隐式重定价 | 红线 + `reprice_trigger` 显式触发 + 留痕；重定价被拒不静默（§4.5C） |
| R5 与 `doc_flow` / `allocation` / `rollup` 争边界 | FR-018 六条边界登记 + 单一判据（过程内；是否有"可分摊到业务单据行"的价格语义） |
| R6 结果明细体积膨胀 | 回放保留策略（TBD-4，D5）；结果版本化替换而非无限追加 |
| **R7 `factor_catalog` 与 `MetaField` 双重真相源**（v1.6） | 同一字段类型被两处声明且**枚举不对齐**（`amount`/`quantity` vs `string`/`enum`）→ 换算与校验行为不可预测；**已由 C-T0-3 收窄**：`factor_catalog` 只声明 `source_type` + `is_price_relevant`，类型 / 别名一律引用 `MetaField`（§7B.4 缺陷 3） |
| **R8 `key_schema` / `lookup_sequence` 职责超载**（v1.6） | 量级换算与阶梯基数耦合在"键"里，**换个业务无法复用**；且"第 1 槽累加 + 第 2 槽取优"需整表复制序列。**已由 C-T0-1 / C-T0-2 / C-T0-4 收窄**（§7B.4 缺陷 1/2） |

**测试策略**：

- **单元测试**：费率类型枚举 / 计算类型（percent/fixed/quantity/formula）；查找序列 exclusive vs additive；tie-break 稳定性；计算基四字段（含 `rolling` 与 `base_step` 互斥、`base_formula`）；阶梯两语义；有效期过滤；取优（Precedence / Best Price）与排斥组；`SafeExpressionEvaluator` 拒绝危险表达式；分摊六基数 × `target ∈ {cost, expense}`；`adjustment` 成对 / 只结算差额。
- **集成测试**：经单据保存链路跑完整"取价 → 累加 → 落库 → 展平字段"；三种传递组合（搬运 / 订单价 × 实际量 / 实际量重取价）；已开票行重定价被拒；`fact_snapshot` 缺失拒绝结算；存量测试全绿（**`python d:\filework\test.py`**）。
- **E2E**：单据上"查看计算过程"可回放；限价校验（`validation`）拦截生效。

**回滚计划**：

- 计算过程 `enabled=false`；费率类型 / 费率表停用；新增对象声明移除；引擎调用点短路。
- **无 schema 迁移 → 无数据迁移回滚**（结果对象为新增声明）。

---

## 10. TBD 清单

| 编号 | 待定项 | 缺什么信息 | 下一步 | 关联 |
|---|---|---|---|---|
| **TBD-1** | ~~**事后 / 计划外费用的归属与去向**~~（研究稿 D16） | 归属选项：① 归 `allocation` ② 归定价"费用 / 分摊"子域（复用 `calc_result` + `allocation_rule`，`target ∈ {cost, expense}` 作规则字段）③ 只做"进费用" | **✅ 已关闭（v1.5 拍板 D16 = ②）**：归定价"费用 / 分摊"子域；它是 `origin=unplanned` 的 `calc_result`，**不新建费用单据、不破 D7**；成本侧取值算法仍归成本核算 | FR-013、§9.3.1 A/C、§9.4 |
| **TBD-2** | ~~**事实数据驱动重算（优质优价 / 大宗）的归属与节奏**~~（研究稿 D17） | 选项：① 不做 ② 只做"事实源作为匹配键表字段 + 事实快照"，大宗两段式后置 ③ 完整做（+ `external_rate_source` / `pricing_period` / 暂定价结算） | **✅ 已关闭（v1.5 拍板 D17 = 设计③ / 实施②）**：`reprice_trigger` 枚举**一次给全**（零成本）；**只实装 `on_quality_result`**（另两个依赖 `external_rate_source` / `pricing_period` / TBD-1 的 `origin`，尚未就绪） | FR-015、§8.2 M8 |
| **TBD-3** | ~~**定价 API 端点路径与命名**~~ | 编排层接口（`price_line` / `explain` / `write_back`）与 **HTTP 端点命名**均已落地 | **✅ 已结项（v1.6）**：定名 `POST /api/v1/pricing/calculate`（IF-001）、`GET /api/v1/pricing/result/<document_type>/<id>`（IF-002，query `document_line_id`）、`POST /api/v1/pricing/write-back`（IF-003）。**实测证据**：① `create_app()` 后 `url_map` 三条路由俱在；② `meta/tests/test_pricing_api.py` **30 用例契约测试全绿**（状态码 / 字段名 / 字段类型 / 错误码分界）。`allocate` 与 `reprice` 仍属 P4 / P6 未实现，路径已预留 | IF-001、IF-002、IF-003、§9.3.3 |
| **TBD-4** | **可解释回放保留策略**（研究稿 D5） | ① 全量落库 ② 仅最近 N 次 ③ 仅在"手动查看"时重算（涉存储成本） | 待定；**P2 必须先有结构** | FR-010、NFR-003、R6 |
| **TBD-5** | 条件更新（累计用量）是否纳入首期（研究稿 D6） | ① 要 ② 先不要 | **倾向 ② 先不做**（P4 后置） | FR-016 |
| **TBD-6** | 在线配置 UI 与规则版本化 | 形态（文件 / DB）+ 历史单据复现策略 | 待定（首期不做） | N8、§7.3 A2 |
| **TBD-7** | 采购侧成本类费用的实现时点 | D7 范围外，仅做对象设计 | 待业务确认（涉及采购侧时另立） | FR-013、B2 |
| **TBD-8** | ~~**「整体价覆盖」Override 语义缺口**~~ | 研究稿 §3 对标（Oracle EBS 五种调整类型含 **`Price Override`（New price）**；Salesforce `pricing element` 三态 **Charge / Adjustment / Override**）——即"不以当前累加结果为基准、直接改写"的语义。现行对象模型只能用 `element_type: manual` + `rate_class: price` **隐式**表达，**无一等概念**。缺什么：① 是否把 `override` 补为显式取值 ② 其与前序累加 / 后序步骤的交互规则须定义 | **✅ 已关闭（v1.5 拍板 D23 = ①）**：**复用 `adjustment`**，新增 `adjustment_type = override`（**不另立对象**——它与 `adjustment` 同构：引用原结果 + 留痕 + 不改原单据）。**交互规则**：`override` 在**前序累加完成后**生效，**直接给出最终价**并**清零其后累加步骤**（语义 = "New price"）；`reason` 必填 | FR-005、FR-014、§9.3.1 A/C/E |
| **TBD-9** | ~~**`pricing_output_map`（结果 → 单据行字段输出映射）缺口**~~ | Salesforce `PricingProcedureOutputMap` 决定"哪个定价结果写回单据的哪个字段"（研究稿 §4.6A）。`calc_result` 已泛化挂任意 `document`（FR-011），但**下游单据行字段名不同即断链**——现无此对象 | **✅ 已关闭（v1.5 拍板 D24 = ②）**：本期**不建对象**，改为**按 `result_semantic` 约定写回字段**（`price`→`unit_price`/`amount`、`cost`→`cost_amount`、`emission`→`emission_amount`，余者落 `result_amount`）。**接口已预留**——多过程 / 多结果结构时再补对象，本约定即默认映射。**v1.6 已实现**：`PricingService.write_back`（映射表 `WRITEBACK_MAP` + 字段候选集兜底 `unit_price/price/unit_cost`、`amount/total_amount/net_amount/line_amount`） | FR-011、§9.3.1 C、研究稿 §4.6A |
| **TBD-10** | **完整单位换算对象 `conversion{from_unit, to_unit, factor_expr}`**（v1.4 拍板 D19：换算归事实源取值阶段，本期只补 `base_source` 枚举 `scaled_quantity`） | 碳域需 kL → GJ（乘密度）、GWP 二次乘数（气体 × GWP = CO₂e）、定价域 `price_unit` 换算——三者形态各异。缺什么：① 是否建独立 `conversion` 对象放**事实源取值阶段**（非计算过程内）② 换算因子的来源（主数据 / 密度表 / 因子库）如何挂到 `source_type = market / measurement` 的字段上 | 后置（P6 随事实源子域）；本期不做 | FR-006、§9.3.1 E、研究稿 §4.9D2 |
| **TBD-11** | ~~**多账簿 / 多估值基础并行**~~（研究稿 D20） | Oracle 一个 Cost Organization 挂多本 Cost Book（primary 财务 / secondary 管理 / **ledgerless 模拟**），同一批事务按不同规则出多套结果；`pricing_procedure` 当前是**单实例** | **✅ 已关闭（v1.5 拍板 D20 = ②不纳入）**：属"**引擎实例化 / 编排**"层，非"过程定义"层。**边界现在就写清**：将来若做，走**引擎外多次调用**（同一 `procedure` 跑 N 次、每次带不同 `context`），**不在引擎内建多实例** | §1.4 N9、FR-005 |
| **TBD-12** | **定价结果的能力接口（interface）**（v1.5 保留，研究稿 D21 已拍板②本期不做） | Palantir Interface 提供对象类型多态；将来成本 / 碳 / 税四域结果都满足"可挂单据 · 有明细 · 可回放"这组能力时，可按能力挂载而不必共用一张表。缺什么：① 是否声明接口层 ② 四域是共用一表还是按能力分表 | **保留待议**（D21 已拍板本期不做——只有一个域，多态零收益；但它是多域时比"硬塞一张表"更保守的选项） | FR-011、§1.4 N9 |
| **TBD-13** | **"谁能改价"的完整权限 / 审批矩阵**（v1.5 保留，研究稿 D22 已拍板②只补最小一条） | 本期**已补最小一条**：`adjustment{adjustment_type=override}.reason` **必填**（FR-014）。仍缺：完整权限矩阵（谁能改价 / 改价要不要审批 / 改价上限），涉及角色、审批流、组织结构 | **保留待议 + 建议归权限引擎**（研究稿倾向：属**组织级治理**，不该由定价引擎单方面承担） | FR-005、FR-011、FR-014、§9.3.1 C |
| **TBD-14** | **`key_schema` 是否废表**（v1.6 新登记） | §7B.4 缺陷 1 取证：**六家中五家无独立"匹配键目录"**（SAP 把匹配维度内联在条件记录里；Fusion 直接挂 `QualifyingCriteria`）。本引擎保留 `key_schema` 的理由是**键可被多个 `rate_table` 复用**。缺什么：① 这个复用是否真实发生 ② 若从未复用，是否按备选 D 内联进 `rate_record.keys{}` 少一张表 | **P0 实施时验证**（T0-2 交付后观察一个周期）；若键从不复用则废表，**不阻塞 T0 先行**。**注意：C-T0-12 结构冻结后，本条的验证条件更严格**——键无法增删 PK，故其存在价值**完全取决于"多 `rate_table` 共用同一 `key`"是否发生**（§7C.4.1 (4)） | FR-003、§7B.5、§7B.8 备选 D、§8.2.0 T0-2、§7C.4.1 (4) |
| **TBD-15** | **配置作用域（租户隔离 / 结构版本）**（v1.6 新登记，§7C.4） | 三件套**全部是全局配置、无作用域字段**。Agent 时代配置的**本质变化是作用域而非格式**。缺什么：① 租户/组织隔离——`rate_table` 无租户字段，**否则跨租串价** ② 结构变更版本——`rate_record` 有行级 `valid_from/valid_to`，但**改结构（加因子/改键）无版本**，无法回溯"当时按什么算"（与 TBD-4 同源） ③ 用户级覆盖——建议走 `adjustment` 不改配置 | **本期只做预防性预留**（C-T0-9：`rate_table` 预留 `owner_org_id` 语义位）；**实际能力待明确的多租需求再开**。**③ 倾向"不做"**。**② 与 C-T0-12 直接相关——本期已禁止结构变更，故结构版本化本期无需实现** | §7C.4、§7C.5、C-T0-9、C-T0-11、C-T0-12、FR-011 |
| **TBD-16** | **运行态自举的完整机制**（v1.6 新登记，§7C.4.1 (5)） | 方向已拍板采纳（双装载 + 仿 SAP V/03 界面），但**机制本期全缺**。缺什么：① **配置变更历史表**（who / when / what diff）② **跨环境一致性**（测试环境有的配置生产没有）③ **结构版本化 + 迁移**（C-T0-12 已禁止结构变更，故本期不需）④ **`with_auto_schema` 闸门处置**（"禁止"→"需显式批准 + diff"） | **本期全部不做**（T0 走开发态，git 即审计，**零治理成本**）。**待明确的多租 / 自助需求再开**。**启动条件：出现"顾问要自己加因子"的真实诉求** | §7C.4.1、C-T0-12、C-T0-13、§7C.6 备选 D/F/G |

---

## CHANGELOG

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-05 | v1.0 | 初版：由 spec-rfc 流程产出，以研究稿 v1.9 为唯一事实来源，收敛为 10 节 Spec + RFC。含 FR-001~FR-018 / NFR-001~NFR-007 / IF-001~IF-008 / TR-001~TR-004 / M1~M8（P0–P6）；对象模型（配置主数据链 + 价目行 + 单据运行时链 + 结果元数据 + 枚举汇总）；RFC（As-Is / Target / 详细设计 / 备选方案 D1·D9·D13·D15·D2·D3·D12 / 实施迁移 / 风险 / 测试 / 回滚）；TBD-1~TBD-7（其中 TBD-1/TBD-2 对应对标研究的 D16/D17 待拍板） |
| 2026-10-05 | v1.1 | 二次检查（研究稿忠实性审计）修正 4 处：① FR-005 补记金蝶"计算策略属过程内 + 仅旗舰版/星瀚"（研究稿 §1.16、§3.1.6）；② §9.3.1 B 补 `rate_supplement`（条件补充）与 `cumulative_usage`（累计值）两对象（研究稿 §4.2 第 2 层）；③ 新增 §9.4.1「研究稿决策点处置映射（D1–D17）」回溯表；④ 对研究稿未给枚举的自造取值（`rate_table.status`、`exclusion_group.resolution`）标注"取值示意" |
| 2026-10-05 | v1.2 | 补记 2 项对象缺口（用户评审提出，本次仅登记、待拍板）：TBD-8 整体价覆盖 Override 语义（Oracle `Price Override` / SF `Override` 三态）—— 对象模型现仅能用 `element_type: manual` 隐式表达；TBD-9 `pricing_output_map`（SF `PricingProcedureOutputMap`）—— `calc_result` 泛化宿主缺"写回哪个字段"的映射 |
| 2026-10-05 | v1.3 | **命名去 SAP 化 + 通用化边界拍板**（用户评审「不要完全无脑看SAP」）：① 元模型层全面改为**领域中立命名**（`rate_table`/`rate_record`/`rate_type`/`key_schema`/`lookup_sequence`/`calc_procedure`/`calc_result`/`calc_detail`/`adjustment` 等），SAP 术语降为**业务别名**，仅见于 §9.3.1「业务别名」「溯源（对标）」列；② §9.3.1 新增「命名原则 + 命名与溯源对照表（含 SAP 骨架 / 六家趋同 / 某家独有贡献标注）+ 通用化三轴表」；③ 通用化只参数化**三轴**——`base_source`（轴①，扩容 `activity_quantity`/`volume`/`energy`/`hours`）、`rate_source`（轴②，`rate_type` 新增）、`result_semantic`（轴③，`calc_procedure` 新增，默认 `price`）；④ §1.4 新增 **N9 通用化边界**（成本归集层 / 碳组织边界·合并层不属本引擎）；⑤ §9.2 新增「元模型通用性与命名声明」（元模型 = 通用确定与计算，本期首个过程实例 = `pricing`）；⑥ FR-001~FR-006 / NFR-007 / TR-001~TR-004 / §8.1 / §8.2 / §9.3.1 A–E 表 / §9.3.2 流程 A / §9.4 D7·D9 / §9.4.1 D7 行术语同步 |
| 2026-10-05 | **v1.4** | **跨域验证回写 + 补第四消解范式 `weighted`**（用户评审「② 第四种消解范式 weighted 这个可以补充」）：**背景**——研究稿 v2.0（Oracle 跨域二次研究）与 v2.1（Palantir 对照）已落盘，结论回写本 Spec。① **补第四消解范式 `weighted`（D18 拍板）**——`rate_record` 新增 **`allocation_weight`（可空）**，**非空即该候选参与"加权累加"而非"取一"**，`result_amount = Σ(rateᵢ × base × weightᵢ)`、**Σweight=1 须归一否则拒绝计算并报错**（不静默缩放）；同组内非空权重候选与"取一"类候选**不可混用**；对标 Oracle 成本域 **Sourcing Rule 分配百分比**（`Standard cost = (Buy × Buy alloc) + (Rolled-up × Make alloc) + (Transfer × Transfer alloc)`）、工单 `Cost Factor Allocation`、LCM `Charge Basis = % of item price`；与 `allocation_rule`（1→N 摊金额）**互为对偶**（N→1 合率）。落点：**§9.3.1 B2 新增"候选消解的四种范式"表** / FR-008 扩写四种范式与验收 / §8.1 FR-008 / §9.2 声明 / §9.4 备选方案 D18 / §9.4.1 D18 / §9.5 决策表。② **D19 拍板：单位换算归事实源取值阶段**——取数时上游归一，引擎内 `base` 恒为标准单位（**换算是"单位声明"不是"公式"的一部分**，混进 `base_formula` 会让同一 `× 率` 公式无法同时服务 kL 与 GJ）；本期只补 `base_source` 枚举 **`scaled_quantity`**（对标 Oracle `per-unit cost = total ÷ scaled quantity`），完整 `conversion` 对象登记 **TBD-10**。③ 新增 **TR-005**（`allocation_weight` 零迁移：默认 `null` = 行为完全不变）与 **TR-006**（消解范式验收矩阵，含"权重和不归一须报错"用例）。④ 外部验证结论入 §9.2 与 header：三轴在 Oracle **成本域**（`总成本 = 固定 + 变动[单位资源成本 × 消耗数量]`）与**碳域**（`排放量 = 活动数据 × 排放因子`）**逐字同构**；Palantir 对照结论——**两条通用化路径的分野不在能力而在"谁承担域特有逻辑"**，本引擎走"元模型 + 参数化"，故 **N9 边界是这条路径的必要成本，不是保守**。⑤ 决策表补 **D20 / D21 / D22**（多账簿并行 / 结果能力接口 / 谁能改价，均待拍板）；§10 TBD 补 **TBD-10~TBD-13**；关联研究稿版本同步为 **v2.1** |
| 2026-10-05 | **v1.5** | **七项待拍板全部落定**（用户评审「采纳你的建议，请更新 spec」）。**共性观察：七项没有一项需要新增对象或改引擎结构**——全落在"已有字段加可空枚举"或"字段名约定"上，**说明元模型骨架已够用，剩下的是填充与约定**。① **D16 / TBD-1 事后费用归属**：**②归定价"费用 / 分摊"子域**——它是 `origin=unplanned` 的 `calc_result`，**不新建费用单据、不破 D7**（依据：Oracle retroactive adjustment 生成独立 acquisition cost adjustment、SAP 计划外交付成本走独立行；且 `origin` 只是一个可空枚举，现在加近乎零成本）。落点 FR-013 新增"归属拍板"段。② **D17 / TBD-2 事实数据重算节奏**：**设计侧③（`reprice_trigger` 枚举一次给全）／实施侧②（只实装 `on_quality_result`）**——另两个触发器依赖尚未实施的 `external_rate_source` / `pricing_period` / TBD-1 的 `origin`，**先枚举留全、只实装依赖已就绪者，避免半配置状态**；并记下研究稿 §4.8C 规律 2"质检值直接改价在头部产品里普遍是半成品"（三家均【未找到】标准链路）——既是机会也说明无成熟范式可抄。落点 FR-015 新增"实施节奏拍板"段。③ **D23 / TBD-8 Override 语义**：**①补，且复用 `adjustment`、不新增对象**——新增 `adjustment_type = override`，语义 = "**前序累加完成后直接给出最终价，并清零其后累加步骤**"（对应 "New price"）；依据是**六家零分歧的共识机制**，缺失最突兀，且它与 `adjustment` 同构（引用原结果 + 留痕 + 不改原单据），另立对象会重复。④ **D22 "谁能改价"**：**②只补最小一条，且与 ③ 合并实现**——`adjustment{adjustment_type=override}.reason` **必填**；**完整权限 / 审批矩阵归权限引擎**（涉及角色 / 审批流 / 组织结构，属组织级治理，不该由定价引擎单方面承担，登记 TBD-13 保留）。⑤ **D24 / TBD-9 输出映射**：**本期不建 `output_map` 对象**，改为**按 `result_semantic` 约定写回字段**（`price`→`unit_price`/`amount`、`cost`→`cost_amount`、`emission`→`emission_amount`，余者落 `result_amount`）——本期只有一个过程实例、一套结果结构，约定即可表达，**零配置零新表**；痛点在多过程 / 多结果结构时才显现，**接口已预留**（本约定即将来对象的默认映射）。落点 FR-011 新增写回约定条目。⑥ **D20 多账簿并行**：**②不纳入**——属"**引擎实例化 / 编排**"层而非"过程定义"层；**边界现在就写清**：将来若做走**引擎外多次调用**（同 `procedure` 跑 N 次带不同 `context`），**不在引擎内建多实例**。**D21 结果能力接口**：**②本期不做**（只有一个域，多态零收益），登记 TBD-12 保留。⑦ 决策表新增 **D23 / D24** 两行；**§10 TBD-1 / TBD-2 / TBD-8 / TBD-9 / TBD-11 五项划线关闭**，TBD-12 / TBD-13 改为"保留待议"并补记已落地的最小版；§9.3.1 C 表 `adjustment` 补 `override` + `reason` + 六家溯源；header 状态改为 **v1.5 · 全部待拍板项已清零** |
| 2026-10-06 | **v1.6** | **三件套通用性分析 + T0 先行批次切出**（用户评审「因子目录 / 匹配键表 / 查找序列是不是通用规则模型？做深入研究」）。**背景**——D7 / §9.2 已声明"元模型 = 通用确定"，但**未回答"通用到什么粒度"**；三件套此前被当作**三张定价专表**直接进 P0。**本版用代码取证回答该问题，结论：通用的是「因子 / 键 / 取数计划」三原语，不是这三张表。**① **新增 §7B 三件套通用性分析**：**§7B.2 三原语**（看什么 / 按什么组合 / 先查谁命中算不算完）对位平台现有形态（`MetaRule.condition` 隐含因子 + `default_by_priority` 排序，**代码级取证**）——性质是**从表达式驱动到目录驱动的升维**，非重复造轮子；**§7B.3 实证支撑**——平台内**四处**（数据权限 Owner>Exclude>Include>默认拒绝 / 属性确定 / 派生 `group_by`+`order_by` / 文档流）**已自发实现同一套三问，无一通用**；**§7B.4 三个缺陷**——(a) `key_schema` **超载 3+1 职责**（匹配维度 + 量级换算 + 阶梯基数 + 排除对象），**对标反证：六家中五家无独立匹配键目录**（SAP 内联于条件记录、Fusion 挂 `QualifyingCriteria`）；(b) `lookup_sequence` **混"检索计划"与"聚合策略"**，而 SAP 是**逐条件自带** `%GET_VAL` 累加/首命中退出 → 现状"第 1 槽累加 + 第 2 槽取优"须**整表复制序列**；(c) `factor_catalog` 与 `MetaField` 是**同一事实的两个真相源**，且 `data_category`（`amount`/`quantity`）与 `data_type`（`string`/`enum`）**枚举逐项不对齐**——**与 A1 修掉的"表名映射 6 份副本"同类风险，下沉到字段层**。② **据此收窄职责（不新增对象数量）**：`key_schema` 只留 `key_fields[]`（量级换算 → `rate_type`，阶梯基数 / 排除 → `rate_record`）；`lookup_sequence` 只留槽位顺序（**`exclusive` 下沉为 `rate_record.hit_policy ∈ {exclusive, additive}`，默认 `exclusive` 零迁移**）；`factor_catalog` **不再声明 `data_type`/`aliases`**，只留 `MetaField` 不具备的 `source_type` + `is_price_relevant`。**判据统一为「换个业务还需要吗」**。③ **新增 §8.2.0 T0 先行批次（T0-1~T0-7）**：三件套为**纯配置元数据，零主数据依赖、零 `order_line` 依赖**（`currency` 降级为 `string` + `master_data_ref` 标记），**全部为 yaml 声明零代码**，可与主数据补齐**并行**（主数据归数据模块）；且 `factor_catalog.source_type` 是 **FR-015 前置**，晚建阻塞 M8。**T1 内核亦零主数据依赖**（纯函数，内存 dict 夹具单测），**仅 FR-011 落库挂载受阻于 `order_line`**，可拆两步（先头级、待行对象补齐仅填值）。④ 落点同步：FR-003 / FR-004 补"职责边界"与新 Source；§9.2 增"三原语 vs 定价特例"条目；§9.3.1 A/B 表字段迁入迁出逐条标注；§9.5 风险表增 **R7 / R8**；§10 新登记 **TBD-14（`key_schema` 是否废表）**；§7B.7 落 **C-T0-1~C-T0-6** 六条建模口径约束；§7B.8 记四个备选与否决理由（含备选 D"内联进 `rate_record.keys{}`"更近 SAP 基线，故保留表+收窄职责为折中）。⑤ **同版新增 §7C「配置载体的未来形态：AI Agent 背景下的选择」**（用户评审「未来方向上是灵活因子配置还是 yaml 声明式动态生成表？AI Agent 背景下配置结构是否更灵活、基于动态用户指定、载体是 yaml+table 还是通用泛化模型」）。**结论：yaml 与 table 不是二选一，而是同一份 SSOT 的两个投影——yaml 是 SSOT，table 是查询加速物。** 关键是**该问题在平台上已是既成事实**（`app_package.py` 原文「`app.yaml` 仍是唯一事实源」，`.bip`/`manifest.json` 皆构建产物；`app_builder.with_yaml_schemas` 走 yaml→registry→建表；`with_auto_schema` 反向内省**刻意标注"仅 introspect，不注册"**；`enum_resolver` 已有静态→DB 双轨；`materialization_registry` 已有"加一行 SSOT 即生效"先例）——故本节不是"要不要切换"而是"**已选的路要不要承认它**"。**§7C.1 事实取证**（5 条代码级）/ **§7C.2 四载体对比**（A 纯 yaml / B 纯 table / C yaml+table 投影 / D EAV 泛化）与逐条否决理由——**D 否决的硬依据是 `rate_record.keys{}` 需组合等值匹配而 JSON 列无法索引**，且 `permission_rules_v2` 已实证 EAV 适合"少而固定"不适合"多而组合"；**§7C.3 Agent 真正改变的是三件事**（生成侧动态化 / 作用域动态化 / 结构不固定）而非载体本身，并给出**反直觉推论：Agent 越强越要把载体收紧到声明式**（宽松载体把错误从"一次人工返工"变成"自动化污染"）→ **灵活性放在配置内容、不放在配置结构**；**§7C.4 指出真正设计点是作用域而非格式**，逐项盘出三件套**全部无作用域字段**的缺口（租户隔离缺失=跨租串价 / 结构变更无版本 / 用户级覆盖应走 `adjustment`），并给出 `with_auto_schema` 闸门的正确处置——**从"禁止"改为"需显式批准 + diff 人工确认"**；**§7C.5 落 C-T0-7~C-T0-11**（yaml 作 SSOT + table 自动物化 / 主数据引用不建外键 / `rate_table` 预留 `owner_org_id` 语义位 / **Agent 生成走同一份 yaml 不得旁路写 DB**（否则回到双重真相源）/ **`status` 草稿发布分离必须落地——这是 Agent 生成配置天然需要的、且是 T0 唯一现成落点**）；**§7C.6** 记五个备选与否决理由（新增"从 DB 反向生成并自动注册"与"本期做双向同步"两条）；**§7C.7 一句话回答题问**。⑥ §10 新登记 **TBD-15（配置作用域：租户隔离 / 结构版本）**，含"本期只做预防性预留、用户级覆盖倾向不做"的处置。⑦ **同版二次修订 §7C（用户评审指出理解偏差：「配置表结构 PK1/PK2/value1/value2 是否可能**运行态由用户交互生成**，不是开发态」——并反驳「MetaObject 应无法完整覆盖 yaml 吧，是不是 SSOT 是 yaml，只是 MetaObject 辅助 yaml 的生成？」）**。**修正 v1.6 初稿的一处立论错误**：初稿曾写「`MetaObject` 是唯一 SSOT，yaml 降级为装载格式」——经 `_template.yaml`（13 个顶层块）与 `models.py` **逐块比对**，该立论不成立。**新增 §7C.1.1**：`MetaObject` **装不下** yaml 的 4 块（`audit` / `ui_view_config` / `category_config` / `import_export` **完全无对应字段**；`ViewConfig` 是 `sources`/`joins`/`aggregates` **查询视图而非 UI 布局**），故 **`MetaObject` 是不完整投影、只是建表中间产物**；而 `schema_generator` **只消费 `fields`/`indexes`/`relations`**，从不需要那 4 块——**故"让顾问勾字段生成 yaml"这条路完全走得通**。**新增 §7C.4.1 记录三条拍板**：**P-1 SSOT 仍是 yaml**（推翻了初稿"SSOT 下移"）· **P-2 界面定位仿 SAP V/03**（**关键取证：V/03 就是"字段目录选字段生成条件表"的事务码**，研究稿 S20；S47 路径 V/03→V/07→V/08 全为交互式 T-code——**说明行业基线恰恰是运行态自举，v1.6 初稿误把 yaml 当开发态产物**）· **P-3 本期禁止结构变更**（顾问只能选既有因子组合；**理由：增删 PK 本身就是一次数据迁移需求**——历史 `keys{}` 缺新 PK、`calc_result` 引用旧结构，属元数据版本管理问题）。**「双装载」的关键点是不存在两条 SSOT**：两条路径**都产出同一份 yaml**，汇入同一条 `register_from_directory` → `schema_generator` 管线。**§7C.4.1 (3) 给出 V/03 式界面的最小暴露面（治理成本的关键）**：顾问**只勾 4 项**（`id`/`name`/`fields[]`/`table_name`），其余 8 块**全部由平台模板填充默认值**，且 `audit` / `category_config` / `import_export` **明确不暴露**——顾问动不了权限与审计，**运行态自举的治理成本因此远低于"完整 YAML 编辑器"方案**（§7C.6 备选 G 已否决该方案）。**连带影响**：C-T0-12 结构冻结**收紧了 TBD-14 的验证条件**——键无法增删 PK，故 `key_schema` 的存在价值**完全取决于"多 `rate_table` 共用同一 `key`"是否真实发生**。⑧ 新增 **C-T0-12**（`key_fields` 本期冻结）/ **C-T0-13**（yaml 仍是唯一 SSOT，`MetaObject` 仅为建表中间产物，后续运行态自举亦产出 yaml 不旁路构造）；§7B.7 汇总行由 C-T0-7~11 扩为 **C-T0-7~13**；§7C.6 新增备选 **F**（旁路构造 `MetaObject`——丢配置 + 第二条 SSOT）与 **G**（完整 YAML 编辑器——把权限审计开关交给非技术人员）；§7C.7 重写（点明"真正分岔是**谁在什么时候写 SSOT**"而非载体）；§10 新登记 **TBD-16（运行态自举的完整机制：配置变更历史表 / 跨环境一致性 / 结构版本化 / `with_auto_schema` 闸门处置——本期全部不做，启动条件为"出现顾问要自己加因子的真实诉求"）** |
