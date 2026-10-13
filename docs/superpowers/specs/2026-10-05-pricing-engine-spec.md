# 定价引擎（Pricing Engine）Spec + RFC

> **版本**：v1.22 | **日期**：2026-10-13 | **状态**：**待确认**（§10 TBD **22 项（关闭 11 / 开放 11）**；**§10.1 实现侧 14 项**（I-1 / I-2 / I-10 / I-13 / I-14 已交付，I-12 待决）并补 **M8 开工前置三问**；**v1.22 `rate_supplement` 定性订正**（补充条款文本 · 非规则 → 降级为观察项、不落 yaml）；**v1.21 计算过程步骤拆表交付**（`calc_procedure.steps` JSON 列 → 独立子对象 `calc_procedure_step`，每步一行、引用回挂；执行器零改动，读路径改由服务层按 `seq` 升序装配；迁移建子表并移除父表 `steps` 列）；**v1.20 定价域 UI 呈现层接线交付**（菜单 18 条 + 3 对象切独立详情页 + 2 处详情子表，实测验证；附带登记 4 项缺口）；§10.2 零消费字段盘点；里程碑状态回填 M1–M8）（**决策点（D 系列）待拍板项已清零** —— v1.4 拍板 D18 补第四消解范式 `weighted` / D19 单位换算归事实源取值阶段；v1.5 拍板 D16 费用归属 / D17 重算节奏 / D20 多账簿不纳入 / D21 结果能力接口本期不做 / D22 + D23 改价必填原因（Override 复用 `adjustment`）/ D24 输出映射改为字段约定。**v1.6 新增 §7B 三件套通用性分析（代码级取证）并据此收窄 FR-003 / FR-004 职责边界 + 切出 T0 先行批次**；**v1.7 M6 FR-013 分摊执行已交付并提升为平台级端点 `POST /api/v1/allocation/allocate`、TBD-18 拆表落地（留痕迁至独立表 `allocation_result`）、分摊链路二次检查完成**；**T0/T1/T2 已交付、T1-5 定价 API 层（IF-001/002/003）已落地并结项 TBD-3**；**v1.12 逐项复查结论：TBD-4 降观察项（软作废已实现，真问题只剩无限增长）、TBD-6 形态事实上已定为"文件 + git"、TBD-7 收敛为"`target` 字段 + 采购侧取值算法"（待**业务**输入）、TBD-14 纠错（`key_schema` 是运行期一等公民，真正零引用仅 `key_fields`，废表代价远高于原设想）、TBD-2 措辞修正（两表已落地，只差运行期接线）、TBD-10/12/13/15/16 启动条件均未触发**；**TBD-14 / TBD-15 / TBD-16 为 v1.6 新登记、TBD-17 / TBD-18 为 2026-10-07 登记并均已落地、TBD-19 为 2026-10-07 新登记（观察项）**；**v1.8：TBD-14 的「`key_fields` 运行期校验」以通用声明式字段属性交付（`key_schema.key_fields.semantics.custom.value_set_from` + `MetadataDrivenValidator._check_value_set`，写入即拦）、TBD-17 遗留②（未知类型静默回落）已修（类型别名补全 + `UnknownFieldTypeError` 守卫）、FR-009 AC 状态回填（三条均非缺口）、TBD-19 新登记（`rate_type.display_scale` / `numeric_field` 零消费，与 TBD-10 合并）**；**v1.9：删除死 schema `role_effective_intents`（表从未存在，`v070` 迁移已记载并跳过）及其手写 migration、schema 注册判据由硬编码文件名黑名单改为「顶层有无 `id:`」语义判据（消除 `id=''` 幽灵对象）**；**v1.10：`_template.yaml` 按「`_` 前缀」判据从注册链排除（此前被注册成业务对象 `new_object`，连带生成表 `new_objects` / 菜单 `new_object-list` / 5 条权限码；权限码经逐表取证零引用后已清理，三库复验 CLEAN）**；**v1.11：同源第二出口修复——`ref_graph.py` 第一遍扫描补「`_` 前缀」判据（第二遍早有、第一遍漏判，属活代码缺陷而非陈旧快照），入库产物 `.ref_graph.json` 随之刷新；`generated_schema.sql`（2026-05-26 快照）本批不动**）
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
- **AC 状态（2026-10-07 回填）**：三条 AC **均非缺口** ——
  - AC1 阶梯两语义（整单取档 / 逐档累进）→ **已交付**（T1 阶梯实现：`rate_record` 阶梯列 + `pricing_service` 两分支，`meta/tests/test_pricing_service.py` 有对应用例）；
  - AC2 过期记录不取价 → **已交付**（`meta/services/pricing_service.py` 取价 SQL 内置 `(valid_from IS NULL OR valid_from <= ?) AND (valid_to IS NULL OR valid_to > ?)`）；
  - AC3 UoM 换算 → **已由 D19 明确后置**：换算归**事实源取值阶段**，本期只补 `base_source = scaled_quantity` 枚举，完整 `conversion` 对象后置 P6（TBD-10）。
  - 附带（**非 AC**）：与本 FR 相关的 `rate_type.display_scale` / `numeric_field` 两列**运行期零消费**，已新登记 **TBD-19**（观察项，与 TBD-10 合并处置）——**不是本 FR 的验收缺口**。
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
| **T1-4 定价编排服务** | ✅ **已交付** | `meta/services/pricing_service.py` + `meta/tests/test_pricing_service.py`（**65 用例**，真建表 + 真跑全链路）。把 T2 内核与 T1 配置链串成一条：`price_line`（查表 → 算过程 → 落结果+明细）/ `explain`（IF-002 回放）/ **`write_back`（TBD-9 ② 结果按 `result_semantic` 写回单据字段）** / 有效期过滤 / 草稿价目表拒绝 / dry-run / **FR-016 条件更新（累计用量触顶自动失效 + 落库同事务累加）**。**全程零 `order_line`、零主数据依赖**（有专项用例守护） |
| **T1-5 定价 API 层** | ✅ **已交付** | `meta/api/pricing_api.py` + `meta/tests/test_pricing_api.py`（**30 用例**，Flask `test_client` 契约测试）。暴露 IF-001/002/003 三条端点；**只做参数校验 + 响应包装**，业务全在服务层。已注册于 `meta/server.py:create_app()`（**实测 `url_map` 三条路由俱在**）。**2026-10-07 追加分摊端点**：`POST /api/v1/allocation/allocate`（`meta/api/allocation_api.py`，已由 pricing 提升为平台级、旧路径不留别名）+ `GET /api/v1/allocation/result/...`（二次检查新增），契约测试独立为 `meta/tests/test_allocation_api.py`（**21 用例**），见 §9.3.3 M6 注记 |
| **T1-6 阶梯取价（FR-009）** | ✅ **已交付** | `lookup_resolver.resolve_scale`（费率记录**自带档位** · 产**费率**）+ `calc_procedure_executor._tier_bounds`/`_op_tier`（过程**内联档位** · 产**金额**）+ 服务层接线（`scale_qty=base` / 三处改读 `LookupResult.rates`）。两语义（`total` 整单取档 / `incremental` 逐档累进）**同义**由 `TestScaleParity` 逐例守护；服务层 `TestFR009阶梯链路` 5 用例覆盖全链路 + 写回防护 |
| **TBD-14 验证**（key_schema 是否废表） | 🔍 **已取证，结论：暂不废表**（原定「观察一个周期」不具备条件，详见下方注记） | 代码级取证三条：① `key_fields` **运行时代码零引用**（全仓 `meta/` 内仅见于 yaml 注释与测试夹具），匹配实际只走 `rate_records.keys{}` 逐键比对（`lookup_resolver._matches`）；② `key_schema` ↔ `rate_table` **无任何绑定关系**（`rate_table.yaml` 零 `key_schema` 引用），复用通道是 `rate_records.key_schema_id`，**结构上允许**一钥多表；③ 现存 DB 无定价数据（`meta/architecture.db` 12 张定价表**全 0 行**，`data/*.db` 无定价表），**无法观测复用是否真实发生** |
| **P2 六对象补齐**（§9.3.1 已声明未落地） | ✅ **已交付** | `meta/schemas/` 六个对象：`allocation_rule`（`basis` 六值 · FR-013）/ `adjustment`（`adjustment_type` 七值含 `override` · FR-014）/ `usage_group`（三上限 · FR-016）/ `cumulative_usage`（FR-016）/ `external_rate_source`（`source` 五值 · FR-015）/ `pricing_period`（`period_type` 四值 + `average_basis` 四值 · FR-015）。`meta/tests/test_pricing_p2_schemas.py`（**69 用例**）逐项守护：注册与 `table_name` · DDL 真建表 · FK 子句**逐条**（含列名）· `pricing_period_id` 已为 INTEGER · 枚举**逐值** + `is_initial` 唯一 · **FK 真约束**（悬空引用抛 `IntegrityError` / 可空 NULL 放行）· 删除保护反补。**六对象零主数据依赖**（C-T0-6） |

> **P2 六对象补齐实施注记**（2026-10-06）：
> ① **平台级 FK 生成缺口（已修）**：`SchemaGenerator._generate_foreign_key` 原先**只对 `PARENT_CHILD` 生成 FK**，且 FK 列名写死 `{target_object}_id`、**完全忽略 `source_field`**。后果有二：yaml 中以 `type: reference` 声明的真引用被**静默丢弃**；`adjustments.original_result_id → calc_result` 会推出**表内不存在的 `calc_result_id`**，建表即失败。现把 `REFERENCE`（须显式声明 `source_field`）纳入生成门，并让 FK 列名优先取 `source_field`。**实测影响面**：全仓 13 条 `reference` 关系，其中 4 条无 `source_field` 被新门挡掉，仅 **2 条存量关系**（`change_events.audit_log_id→audit_logs`、`change_subscriptions.user_id→users`）新获 FK——两者目标表与源列均存在，且既有测试用手写 DDL 建表（无 FK 子句）故不受影响；
> ② **`calc_result.pricing_period_id` 由 string 收紧为 INTEGER**（原按 `pricing_periods.code` 引用 → 改按 `id`），与其余 `*_id` 口径统一；`data/app.db` 实测**无任何 `calc_*` / `rate_*` 表**，故无存量数据风险。注：`schema_generator` 只支持 CREATE + ADD COLUMN，类型变更**仅对新建库生效**；
> ③ **删除保护反补**：`allocation_rule` / `external_rate_source` / `pricing_period` 的 `restrict_on` 登记服务层友好提示（指向 `calc_results.*`），`calc_result.restrict_on` 登记 `adjustments.original_result_id`；DB 级 FK 兜底。口径与同期 foundation 的 `address` / `calendar` 做法一致；
> ④ **仍待接线的部分**：这六个对象目前是**声明已落地、端点未实现**——`allocate`（P4/M6）已于 2026-10-07 交付（见 §9.3.3 M6 注记）；`reprice`（P6/M8）**本期后置**；`conversion` **不在 §9.3.1 清单内**且已由 D19 / TBD-10 后置 P6，本轮不含。条件更新累计（`cumulative_usage` / `usage_group`）已于下条接线。
>
> **`reprice` 后置的取证结论（2026-10-07）**：比原登记的更不 ready，故本期不实装而非"排期靠后"——
> ① `PricingService` **无 `recalc` 方法**（`price_line` / `explain` / `write_back` 三条，无重算入口）；
> ② `freeze_policy` / `reprice_trigger` / `fact_snapshot` 三列**只在测试里被断言存在，生产代码零读写**——即 §9.3.1 D 表登记的 FR-012 策略元数据与 FR-015 回放要素**全是死字段**；
> ③ `external_rate_sources` / `pricing_periods` 两张表**已建但零服务代码**（与 `allocation_rule` 交付前的状态完全同构）；
> ④ 叠加下条 ③ 登记的「重算会重复计数」代价（`cumulative_usage` 只增不减），实装须一并处理冲销，跨两个 FR 的改动面。
> 结论：**先接线重算链路（FR-015 事实源 + 策略字段读侧），再开端点**，否则 `reprice` 只是一个会写错数的壳。
>
> **M5 实施注记 · FR-016 条件更新 + FR-012 策略元数据**（2026-10-06）：
> ① **读侧——"用满"复用 `inactive` 通道**（对标 SAP Condition Update `KOUPD`）。`load_candidates` 装载后 JOIN `cumulative_usages × usage_groups`，三维度（`used_amount`/`max_amount`、`used_quantity`/`max_quantity`、`used_documents`/`max_documents`）任一 `used >= cap` 即置 `inactive`（`cap` 为 NULL = 该维度不限）。**不新增第三种跳过原因**：失效是**配置状态**而非异常，故与"停用"走同一条回放路径（记 `record_inactive`）；
> ② **写侧——累计用量与结果落库同事务**。`_persist_with_invalidate` 的 `transaction()` 与 `SAVEPOINT` **两个分支均已接入** `_accumulate_usage`（金额累加本次 `net`、数量累加计算基 `base`、单据数 +1，**按命中候选逐条各计一次**）。同事务是硬要求：分开写会出现"结果已生效但用量没计"，下次取价仍判未触顶 = **超发**。**已用测试逐项守护**：明细写失败（故障注入）时累计一并回滚；
> ③ **已知代价（本期不做）**：**重算会重复计数**——重算先作废旧结果，累计只增不减。取舍理由是「手工冲销累计值」对标 SAP 亦然，本期不做自动冲销；`reprice` 端点（M8/P6）落地时须一并处理（该端点已于 2026-10-07 **取证后本期后置**，见上条 `reprice` 后置结论——本项为其落地的前置条件之一，不因后置而消失）；
> ④ **FR-012 三策略字段已落 `calc_result`**（§9.3.1 D 表补齐）：`freeze_policy`（`recompute`/`freeze`）、`reprice_trigger`（7 值，**空 = 不自动重定价**）、`qty_basis`（7 值）。三者在 Spec 层**一次给全枚举**（D17 设计侧③），实施侧**只实装依赖已就绪者**——`on_quality_result` / `on_pricing_period_end` / `dry_weight` / `net_dry_weight` / `assayed_content` 的枚举**先声明后接线**（依赖 FR-015 事实源与 UoM 换算，后者由 TBD-10 后置 P6）。落库时**须为 NULL**（红线：已开票/已过账行不得隐式重定价），已用测试锁定；
> ⑤ **缺表容错**：读侧与写侧均 `try/except` 兜底并 `logger.debug`——`cumulative_usages` / `usage_groups` 属 P2 对象，晚于 T0 交付，早期库无此表，**不得阻断取价**。

> **TBD-14 取证结论（2026-10-06 代码级）**：原定「T0-2 交付后观察一个周期」**不具备执行条件**——定价元模型 T0 走开发态、配置由 git 审计，**生产库无任何定价数据**（实测 `meta/architecture.db` 的 12 张定价表全为 0 行，`data/app.db` / `warehouse.db` / `tms.db` 连定价表都没有）。改以代码级取证回答"能否废表"，得三条事实：
> ① **`key_fields` 在运行时代码中零引用**。全 `meta/` 目录检索，该字段名只出现在 yaml 注释与测试夹具的播种 SQL 里；`pricing_service` / `lookup_resolver` 均不读它。实际匹配走 `_matches()`——**只比对 `rate_records.keys{}` 的键值**，键名是否在 `key_schema.key_fields[]` 中**从不校验**。即：本表目前**只提供"槽位分组标签"**（`key_schema_id` 作粗筛列 + `steps[].key_schema_id` 定位），**并未提供"键结构定义"**。
> ② **`key_schema` 与 `rate_table` 之间无任何绑定关系**（`rate_table.yaml` 零 `key_schema` 引用），复用通道是 `rate_records.key_schema_id` 指向同一把键——**结构上允许一把键被多张 `rate_table` 复用**，但这需要真实的配置数据才会发生。
>
> **⚠️ 2026-10-07 复查纠错**：本条 ② 的措辞**易被误读为"`key_schema` 整体与运行期无关"**，实为**只与 `rate_table` 无直接列绑定**。`key_schema` 在运行期是**一等公民**：[lookup_resolver.py](file:///d:/filework/excel-to-diagram/meta/core/lookup_resolver.py#L16-L17) 载明"槽位次序 = `lookup_sequence.steps[{seq, key_schema_id}]`"，`LookupCandidate.key_schema_id` / `LookupTrace.key_schema_id` 均为**必填字段**（[L86](file:///d:/filework/excel-to-diagram/meta/core/lookup_resolver.py#L86) / [L193](file:///d:/filework/excel-to-diagram/meta/core/lookup_resolver.py#L193)），[L533](file:///d:/filework/excel-to-diagram/meta/core/lookup_resolver.py#L533) 用它走 `idx_rate_record_lookup` 索引粗筛；`key_schema.yaml` 更声明了 `foreign_key: key_schema_id`，`rate_record.yaml` 有真实 `key_schema_id` 外键列。**真正零引用的只是 `key_fields`（键结构定义）这一个字段**（本条 ① 的结论仍然成立）。**对废表判断的影响**：本表承载"槽位分组标签 + 外键粗筛 + 回放 trace"，**不是空壳**；废表需同时改造 `lookup_sequence.steps` 的 JSON 结构与索引，代价远高于原设想。
> ③ 故**原定验收条件（"多 `rate_table` 共用同一 key 是否真实发生"）既未证真也未证伪**。
>
> **裁决：暂不废表，但本条降级为"观察项"而非"待办项"**。理由：废表（备选 D 内联进 `keys{}`）的收益是"少一张表"，而**当前连 `key_fields` 的语义都还没接线**（见 ①）——在接线之前讨论废表，是拿一个尚未成立的前提做决策。**真正的待办是补 `key_fields` 的运行期校验**（配 `keys{}` 时比对键名是否属该 `key_schema`，属 C-T0-12「结构冻结」的执行手段），复用与否等有数据后自然显现。**触发条件**：出现第二张 `rate_table` 复用同一 `key_schema` 时，本条自动关闭；若届时确认从不复用，再评估备选 D。

> **测试假绿缺陷 · 第一类「raw-SQL 门控」（2026-10-06 实测，已闭环）**：`meta/tests/conftest.py::_check_raw_sql_in_tests` 会把**含裸 SQL DML 的测试文件整体 skip**（正则 `INSERT INTO` / `UPDATE x SET` / `DELETE FROM`；白名单仅 `meta/tests/factories/` 目录与 `ALLOW_RAW_SQL=1`）。实测默认口径下**三个文件**命中、且均报 `Success: True`（假绿）：`test_metadata_driven_validator.py` **42 skipped**、`test_pricing_service.py` **42 skipped**、`test_pricing_api.py` **30 skipped**；加 `ALLOW_RAW_SQL=1` 后分别 42 / 42 / 30 **passed**——测试本身是真绿的，只是默认不跑。三处均已按 factories 口径闭环：校验器批次 `9e216d90`（`_metadata_validator_helpers.py`）；本批次新增 `_raw_sql_bridge.py`（`insert`/`update`/`delete`），`test_pricing_service.py` / `test_pricing_api.py` 迁移后默认口径 **42 / 30 passed 且零 skip**（迁移仅动 DML，`assert` / `pytest.raises` 零改动，已逐行复核）。**根因**：DML 写在测试文件内，而非 `meta/tests/factories/`（conftest 的唯一白名单目录）。**本次 P2 测试已按 factories 口径落地（`_pricing_p2_helpers.py`），默认口径即运行。**
>
> **测试假绿缺陷 · 第二类「用例内无条件 skip」（2026-10-07 实测，已闭环）**：`test_change_notification_integration.py` 默认 **14 skipped**，该文件**零 raw-SQL 匹配**——14 条来自用例体内的**无条件 `pytest.skip(...)`**（原理由 `"requires full app context"` × 8 / `"requires ManageService with proper registry setup"` × 7）。原判「纯属**用例未实现**（占位跳过）」**经实测不成立**：真实根因是三层叠加，测试当年 skip 掉的其实是**真缺陷**。现 14 条全部补实现，默认口径 **14 passed / 0 skipped**。
> ① **平台缺陷（真 bug，已修）**：`ManageService.delete()` 被 commit `86180819` **意外截断**——该提交把新方法 `_all_children_cascade_delete()` 的 `def` **插进了 `delete()` 方法体中间**，其后原有的「级联审计日志 → delete 事件发布 → `return result`」三段因新作用域开启而**沦为不可达代码**，`delete()` 执行完 `executor.execute(...)` 后**隐式返回 None**。影响面：调用方 `manage_api.py:906` 的 `result.success` 抛 `AttributeError`（DELETE 端点 500）、`import_export_service` 的级联导入删除同样炸、**delete 的 change_event 永不发布**。**实测影响面**：把该文件回退到 HEAD 后重跑本文件，3 条 delete 用例报 `AttributeError: 'NoneType' object has no attribute 'success'`（`test_delete_publishes_event` / `TestChangeNotificationDisabled::test_delete_without_notification_config` / `TestEventPublishFailureHandling::test_delete_succeeds_even_when_event_publish_fails`）；恢复修复后 14 passed。修复为**纯方法归位**，不改任何业务逻辑；归位使后半段首次可达，另需前置 `cascade_result = None`（原先只在该方法的 `else` 分支赋值，`_all_children_cascade_delete()` 为 True 时不赋值即被读取 → `UnboundLocalError`）。
> ② **测试夹具缺陷（已修）**：夹具的 `audit_logs` DDL **过期**（仅 ~23 列，缺 `log_category` / `log_level` / `outcome` / `retention_until` / `cascade_root_id` / `cascade_root_action` 等），致 `AuditService.log()` 的 27 列 INSERT **静默失败**（仅 `logger.warning`，不抛错）——审计与事件的 `audit_log_id` 关联因此无从验证。已按 `audit_async_queue.py:205-211` 的 27 列权威清单 + `v2_001_audit_log_v2.sql` 对齐重建 DDL。另：夹具自建表不在 YAML schema 内，须显式 `register_table_name(...)` 才过 `validate_table_name()`——**`registry.register()` 不会让表名缓存失效**，故仅注册 MetaObject 不够。
> ③ **测试环境闸门（测试侧规避，非缺陷）**：`ActionExecutor._write_audit_log_v2()` 开头 `if os.environ.get('PYTEST_CURRENT_TEST') is not None: return`（`action_executor.py:2414`）→ pytest 下**整条 ActionExecutor 审计链被静默跳过**；且 conftest 的 `create_app()` 会把 `async_audit_writer` 绑到**平台库** → 审计变「异步 + 写错库」，临时库的 `audit_logs` 永远收不到行，`_get_latest_audit_log_id()` 恒为 None。规避方式：用例体内 `monkeypatch.delenv('PYTEST_CURRENT_TEST')`（pytest 在 **call 阶段开始前**才会重设该变量，`_pytest/runner.py:169`，故放在夹具里会被覆盖）+ 夹具内置空 `async_audit_writer._ds` 走同步分支。
> **定向回归**：`meta/tests/test_manage_api.py` **22 passed**（含 `test_v2_delete_user`）。但须记录一条**反向发现**：`test_v2_delete_user` 断言仅 `status_code in (200, 400)`，实测**即使回退平台修复仍通过**（它在 `validate_delete()` 处先行返回 400，根本没走到 `ManageService.delete()`）——**该既有用例对本缺陷不具备检出能力**，真正守护它的是新补的 3 条 delete 用例。

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
> ① **两个序列不可混用**：`lookup_sequence.steps[]`（查找槽位 `{seq, key_schema_id}`）与 `calc_procedure_step`（计算步骤 `{seq, element_type}`）是**不同配置**。初版把计算步骤直接喂给 `lookup()`，报 `KeyError: key_schema_id`。现由 `sequence_code` 显式指定，留空则跳过查表（适用于费率已在单据上的情形）；
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
> **FR-009 本期边界登记**（五条，均为**有意取舍而非遗漏**）：
> ① **`scale_divisor`（分档基数字段）本期不消费** —— 它要求读单据行字段，与「零 `order_line` / 零主数据」前提冲突，待行对象补齐后接；本期阶梯基数一律取计算基 `base`；
> ② **「按定档后金额比优」本期不做** —— `resolution=best` 的比优发生在**记录层**（按 `value`），不比较定档后金额，与 SAP 语义一致（见 ②）；且**分档记录 + `best` 已显式拒绝**（见二次审查②），不存在静默误导；
> ③ **定档留痕落 `calc_detail.factor_snapshot["scales"]`**（复用既有 json 列，**零 schema 改动**），记「落到哪一档 / 定出什么费率」，供 FR-010 回答"为什么是这个值"。
> ④ **`LookupResult.rates` 的 key 是整型**（`{candidate_id: rate}`）；`to_dict()` 经 `json.dumps` 后 key 会变字符串。当前仅**进程内**消费（`pricing_service` 不经 JSON 读它），故本期不处理；若未来经 API 暴露，消费端须做 `int()` 回转。
> ⑤ **AC 第 3 条「订单单位 ≠ 计量单位时先按 UoM 换算」本期不做 —— 已被 D19 + TBD-10 显式后置**。D19 拍板「换算归**事实源取值阶段**，引擎内 `base` 恒为标准单位」，完整 `conversion{from_unit,to_unit,factor_expr}` 对象登记为 **TBD-10（后置 P6）**。**故 AC ③ 不是待办，是有界面的本期不做**（此前 Spec 未登记此条，导致 AC 读起来像遗漏，本次补上）。**D19 承诺的「本期只补 `base_source` 枚举 `scaled_quantity`」已于 2026-10-07 兑现**：`calc_result.base_source` / `calc_detail.base_source` 补该值，**只承载「本基来自已换算数量」的声明，引擎不读它做换算**。**重新开启条件**：TBD-10 的 `conversion` 对象落地（须同时满足：换算因子来源挂到 `source_type = market / measurement` 的字段上、且不破坏 C-T0-6 零主数据依赖）。**实测现状（2026-10-07 取证）**：数据层 `uom` / `item_uom_conversion{from,to,factor}` / `items.base_uom` 三表闭环**已注册可建表但零消费代码**；`rate_record.rate_unit` 仅有 `semantics.master_data_ref: uom` 标记，**不建外键**（C-T0-6），故定价层与 UoM 之间**无任何可执行连接**；`rate_type.display_scale` / `numeric_field` 在 `meta/tests` 与 `meta/core` / `meta/services` 中**实质命中为 0**（仅 yaml 声明）。

> **FR-009 补漏 · `rate_qty` 折算（2026-10-07 实测并修复）**：`rate_record.rate_qty`（yaml 声明「定价数量，如"每 10 个"填 10。空 = 1」）此前**全仓零消费**——只有 yaml 的 4 处自身声明，`meta/core` / `meta/services` 无任何读取。引擎契约是「金额 = **每单位**费率 × 数量」，而 `rate` 被当成"每个的单价"直接 × base。**实测**：配 `rate=100 / rate_qty=10 / base=100` 得**金额 10000**，业务期望 **1000**（`100/10 × 100`）→ **静默 10 倍超收**，无异常、无告警、无日志。**与 AC ③ 的 UoM 换算是两件事**：本字段是费率记录上的**纯标量**（不需要主数据，故 TBD-10 的 `conversion` 落地与否不影响它）。
> **修复落点**：折算收敛在 `lookup_resolver.resolve_scale` —— 它是所有费率出口的**唯一收口**（不分档 / `total` / `incremental` 三条返回路径，以及 `LookupResult.rates`、`lookup_amount` 累加、FR-008 `weighted` 分支的 `apply_weighted` 全经此）。故**只折算一次**，服务层 `initial_state["rate_<id>"]` 直接取 `lk.rates` 即已是每单位费率（其 fallback 的 `c.value` 走 `per_unit_rate()` 补齐）。**阶梯路径一并折算**，否则「每 10 个 + 阶梯」留下第二处超收口子；`tier.rate` 留痕记**折算后**值，使 FR-010 回放能直接用它复算。
> **未改动 FR-008 消解范式**：仍按毛额 `value` 比较（与 SAP「先存取序列选中条件记录、再落 Staffel 档位」一致），只把**折算**加在定档之后的费率出口。故「同一价目表内两条候选 `rate_qty` 不同」的 `best` 比优口径**仍按毛额**——本期不处理，若将来启用跨 `rate_qty` 的 `best` 比优，须先明确该语义。
> **`rate_qty <= 0` 兜底为 1 而非报错**（取舍）：抛错等于让存量脏数据**阻断整张价目表**取价，风险高于"按 1 处理"。已用测试锁定该口径。
> **存量风险实测**：全库扫描（`data/*.db` + `meta/*.db`）—— `rate_records` 仅 `meta/architecture.db` 一张表且 **0 行**，`rate_qty` 非空 **0 行**。故按 yaml「空 = 1」兜底后，对现有配置**零影响**。
> **测试**：`test_lookup_resolver.TestRateQty折算`（12 条，含非正兜底 / 文本值 / 两阶梯语义 / "折算只做一次"）+ `test_pricing_service.TestRateQty端到端`（6 条，含**落库 `calc_results.rate`** 与**写回单据 `unit_price`** 两条静默错价防护）。回归：`test_lookup_resolver` **76 passed**（原 64）、`test_pricing_service` **60 passed**（原 54）、`test_pricing_api` **30 passed**。**检出能力实测**：回退实现后新测报 `assert 10000.0 == 1000.0` / `assert 5000.0 == 500.0`，确属真守护而非陪跑。

| 里程碑 | 范围 | 关键交付 | DoD |
|---|---|---|---|
| **M1 = P0 概念定型** | 六件定成平台对象 / 枚举；费率类型落为配置对象 | 元模型草案（表 + 字段 + 枚举）**（v1.6：T0-1~T0-7 已先行交付此 DoD）** | 六件各有归属对象，与 §5.2 边界不冲突；费率类型字段与 §4.1 一致 |
| **M2 = P1 单层取价 ★** | 一个物料 × 一个客户 → 一个单价 | 匹配键表 + 因子目录 + 费率表 + 费率记录（含币种 / 计量单位）+ 查找序列（exclusive） | 命中即止，能回答"命中哪一行"；跨币种费率记录可换算 |
| **M3 = P2 多层累加 + 回放 ★** | 基价 → 折扣 → 附加费 → 税 → 运费 | 费率类型分类 + additive + 计算过程序列（带 `element_type`）+ 计算基四字段 + 小计 + 计算明细 + `calc_result` / `calc_detail` | 逐层小计可回放；每步记 `base_level`/`base_source`/`base_step`/`rolling`（默认不滚动，滚动与 `base_step` 互斥） |
| **M4 = P3 取优/互斥** | 多同类命中怎么收 | Precedence vs Best Price（显式选择）+ 排斥组 | 同一数据两范式结果可分别复现 |
| **M5 = P4 阶梯 + 有效期 + 条件更新 + 执行期重算** | 按量分档 / 按日期生效 / 合同量累计 / 发货开票按实际量重算 | 费率记录属性扩展 + 用量累计 + `freeze_policy`/`reprice_trigger`/`qty_basis` | 阶梯 / 过期 / 用满三测例；三种组合各一测例；已开票行重定价被拒 |
| **M6 = P4.5 事后费用与分摊** | 发票 / 收货 / 服务确认 / 结算上的计划外费用摊到 PO / 收货 / 订单行，可追溯补差 | `allocation_rule` + **`allocation_result`（独立留痕表，2026-10-07 由 `calc_result` 拆出）** + `adjustment`（可后置） | 一笔费用按 6 种基数摊到行且可回放；`target=cost`/`expense` 各一测例；已过账追溯被拒或留痕 |
| **M7 = P5 扩展点接线** | 复杂定制逃生门 | `ActionType.BUSINESS` hook 接线 VOFM 式例程 | 自定义例程可插拔，不改引擎 |
| **M8 = P6 事实数据驱动重算（可选）** | 优质优价 + 大宗贸易 | **因子目录事实源分类（T0-1 已交付，此处只做消费）** + `external_rate_source`/`pricing_period` + `fact_snapshot`；`qty_basis` 扩容 | 质检值命中匹配键表得升贴水；干吨折算参与计价；暂定价→终价差值可配对回放；`fact_snapshot` 缺失拒绝结算 |

> **（2026-10-07 拍板）里程碑任务清单与验收细则不再另立《定价引擎实施计划》。** 理由：Spec 已承载交付物与 DoD，另立会造成**第二真相源**（清单不集中 = 漏，本项目已两次因此误判"待办清零"）。原参照的 [rule-model 实施计划](./2026-10-02-rule-model-implementation-plan.md) 范式仅借其"里程碑 ↔ 任务"映射思路，**不照搬分文件**。

**里程碑状态回填（2026-10-07）** —— 此前状态只能从 §8.2.0.1 的批次回填里拼出，现统一归位：

| 里程碑 | 状态 | 依据 |
|---|---|---|
| M1 = P0 概念定型 | ✅ **已交付** | T0-1~T0-7（§8.2.0.1 回填） |
| M2 = P1 单层取价 | ✅ **已交付** | T0 链 + T2-1 查找序列引擎 |
| M3 = P2 多层累加 + 回放 | ✅ **已交付** | T2-2 执行器 + T1-1~T1-3 结果链三表 |
| M4 = P3 取优/互斥 | ⚠️ **验证已交、排斥组未实现** | 四范式已在 [pricing_api.py:191](file:///d:/filework/excel-to-diagram/meta/api/pricing_api.py#L191) 暴露（`precedence` / `best` / `exclusive` / `weighted`）；`exclusion_group` schema 已交（T0-5）。**I-10 已交付（2026-10-08）**：补 8 例逐范式测例 + 修正 TR-006 原夹具 `priority`/`value` 同序导致 `precedence` 与 `best(min_amount)` 不可区分的缺陷（改用反序夹具）。**遗留**：`exclusive` 的**排斥组边界无人承载**，该范式实际等价于 `precedence` → 见 **I-12**（须先定组边界形态，属设计决策） |
| M5 = P4 阶梯 + 有效期 + 条件更新 + 执行期重算 | ⚠️ **部分交付** | 阶梯（T1-6）/ 有效期 / 条件更新已交。**⚠️ 2026-10-08 拆分**：M5 遗留其实是**两条互不依赖的线**，此前一并指向 I-5 是归属错配 —— ① **FR-012 红线**（已开票/已过账行不得隐式重定价，`price_mode` 三档 + `qty_basis` 逐"目标×参考"单据类型可配）属 **P4 独立交付**，**不应等 P6** → 见 **I-11**；② **FR-015 事实源重算端点**（`reprice`）属 **P6** → 见 I-5 |
| M6 = P4.5 事后费用与分摊 | ⚠️ **部分交付** | `allocate` + `allocation_result` 已交；**`adjustment` 追溯补差可后置 → 见 I-7** |
| M7 = P5 扩展点接线（FR-017） | ❌ **未交付，且此前三类清单均未收录** | 见 **I-9**（平台只有声明式逃生门，无代码例程层） |
| M8 = P6 事实数据驱动重算（可选） | ❌ **未开始**（明确后置 P6） | 见 **I-3 / I-5 / I-6 / I-8**（**2026-10-08 修正**：原仅列前三项，漏 I-8 —— D19 已把完整 `conversion` 对象明确归 P6，`allocation_result.yaml` 注释亦按此列删列） |

> **口径**：M1–M3 已闭环；M4/M5/M6 为「主体已交、遗留项已登记」；M7/M8 未动。**M7 是唯一"既没做、也没登记"的**——本次补入 I-9。

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
| `calc_procedure`（业务别名：定价过程） | `code` / `name` / `procedure_type`（首期 = `pricing`）/ **`result_semantic ∈ {price, cost, emission, tax, hours, quantity}`（结果语义 · 轴③，默认 `price`）** / `subtotal_keys[]`；**有序步骤由子对象 `calc_procedure_step` 承载**（每步一行，`calc_procedure_id` 回挂） | SAP V/08；Oracle Pricing Algorithm；SF Pricing Procedure |
| `calc_procedure_step`（业务别名：过程步骤） | `calc_procedure_id` / `seq` / `element_type ∈ {list_price, tier, attribute, formula, manual, derived, aggregate, distribute, round, track, quality_premium}` / `rate_type_id?` / `condition?` / `params{}` / `rolling` / `base_step?` / `subtotal_key?` / `description`；业务键 `[calc_procedure_id, seq]` | SAP V/08 过程步骤；Oracle Pricing Algorithm 步骤；多家趋同 |
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
| `rate_supplement`（业务别名：条件补充） | 依附某费率记录的**补充条款文本**（研究稿 §4.2 第 2 层；**非计算逻辑、不参与取价**；本 Spec 未单列 FR，**未落地 yaml**，见 §10.1 观察项） | SAP Condition Supplement |
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
  └─ 生成 allocation_result{origin=unplanned, source_document_*≠宿主单据}（头记总额 + 行记摊得额）
  └─ 按 allocation_rule{basis, group_by, floor, target} 摊到目标单据行
       → 子行业务字段写回（与留痕同事务）
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

#### 9.3.3 API 设计（v1.7：IF-001/002/003 + 分摊端点已实现）

> **实现落点**：`meta/api/pricing_api.py`（`Blueprint('pricing', __name__, url_prefix='/api/v1/pricing')`）+ **`meta/api/allocation_api.py`**（`Blueprint('allocation', __name__, url_prefix='/api/v1/allocation')`，2026-10-07 由 pricing 提升为平台级），
> 两条启动路径（`meta/server.py:create_app()` / `meta/core/app_builder.py`）均注册。
> **契约测试**：`meta/tests/test_pricing_api.py`（30 用例）+ `meta/tests/test_allocation_api.py`（21 用例，Flask `test_client`）。
> **分层纪律**：API 层**只做参数校验 + 响应包装**，业务（查表 / 算过程 / 落库 / 写回）**全在服务层** `PricingService` / `AllocationService`。

**已实现（IF-001 / IF-002 / IF-003 · 分摊）**

- **定价调用 · IF-001**：`POST /api/v1/pricing/calculate`
  入参 = `process_code` + `rate_table_id` + `slot_keys`（`[{因子: 值}]`）+ `base`，可选 `sequence_code` / `document_type` / `document_id` / `document_line_id` / `level` / `resolution` / `measure` / `valid_on` / `persist`；出参 = 净价 / 行金额 + 结果行与明细。
  **入口校验**：三必填齐备；`slot_keys` 形状；`persist=true` 且给 `document_type` 时须给 `document_id`；`document_line_id` 不可脱离 `document_id`；`level ∈ {header, line}` 且与 `document_line_id` 空值一致；`resolution ∈` 四范式且 `best` 必带 `measure`。
- **回放查询 · IF-002**：`GET /api/v1/pricing/result/<document_type>/<int:document_id>`
  可选 query `document_line_id`（缺省 = 头级）；返回命中 / 剔除候选及原因 + 逐层小计 + 计算基四字段。
  **路径里的 `document_type` 即 `calc_result.document_type`**（宿主元模型对象 ID，如 `sales_order_enhanced`）。
- **结果写回 · IF-003**：`POST /api/v1/pricing/write-back`
  入参 = `document_type` + `document_id`（可选 `document_line_id`）；按 `result_semantic` 约定映射（TBD-9 ②，`WRITEBACK_MAP`）；出参 = `written` / `skipped` / `result_ids`。
- **分摊执行 · IF-004**：`POST /api/v1/allocation/allocate`（v1.7 由 `/api/v1/pricing/allocate` 提升，**旧路径不留别名**）
  入参 = `allocation_rule_id` + `parent_id` + `target_object` + `target_field`（规则驱动，可选 `basis_field` / `group_by` / `rounding` / `floor` / `document_type` / `charge_source` / `source_document_type` / `source_document_id` / `persist_result`）；出参 = `total` / `source_total` / `allocations` / `result_ids` / `verified`。业务在 `AllocationService.allocate_by_rule`。
- **分摊留痕回放**：`GET /api/v1/allocation/result/<document_type>/<int:document_id>`（2026-10-07 二次检查新增）
  可选 query `document_line_id`（只回该行级留痕）、`status`（默认 `active`；传 `all` = 含已作废行，审计用）；返回 1 头（待摊总额）+ N 行（各行摊得额）。业务在 `AllocationService.query_results`。**查询边界跟着表边界走**——分摊留痕**不再**由 `GET /api/v1/pricing/result/...` 混入返回（`explain` 的 `include_allocation` 已移除，见 M6 注记 ⑫）。

**错误码分界（本层确立）**

| 状态码 | 语义 | 触发 |
|---|---|---|
| **400** | **改请求** | 参数错（`INVALID_PARAM`）；编排层找不到过程 / 价目表 / 查找序列（`PRICING_ERROR`） |
| **422** | **改配置** | `ResolutionError`（候选消解失败：权重和不归一等）；`CalculationError`（未注册算子等结构性矛盾） |
| **401** | 未认证 | `login_required`（三条端点均要求登录） |

**尚未实现（P6）**

- **分摊执行**：`POST /api/v1/allocation/allocate`（FR-013 / FR-014） —— ✅ **P4/M6 已交付（2026-10-07）**。**路径已由 `/api/v1/pricing/allocate` 提升为平台级 `/api/v1/allocation/allocate`**（分摊是平台通用能力，非定价附属；算法层零业务耦合，留痕层已拆出独立表`allocation_results`）。**旧路径不留别名**——端点交付次日即改，仓库内外均无调用方，且本仓拒绝向后兼容垫片。蓝图由 `pricing_bp` 迁至新增的 `allocation_bp`（`meta/api/allocation_api.py`），两条启动路径（`server.py` / `app_builder.py`）均已注册，路由实测：`/api/v1/allocation/allocate` 在、`/api/v1/pricing/allocate` 不在。详见下方注记与 TBD-18。
- **重算**：`POST /api/v1/pricing/reprice`（FR-015）——依赖 `reprice_trigger` 消费链与 `external_rate_source` / `pricing_period`，**本期后置**（取证结论见注记，非"未开工"而是"不具备开工条件"）。

> 端点命名与既有 API 风格（`/api/v1/<module>/<resource>`、`_response_contract` 的 `ok` / `error_response`）一致；
> **命名已于 v1.6 落地**（TBD-3 结项），后续增补端点沿用同一 prefix 与错误码分界。

> **M6 实施注记 · FR-013 分摊执行（2026-10-07）**：
> ① **不是纯接线**。原登记"依赖 P2 未落地的 `allocation_rule`"**经实测不成立**：`allocation_rules` 表与 12 字段 schema 早已落地，但 `allocation_rule` 在 `meta/services` 内**零服务代码**——即 FR-013 AC 的"分摊基数是可配枚举"与"可回放"两条是**死字段**。故本轮实装的是服务能力本身，不是端点壳。
> ② **`floor` 与守恒的冲突取 waterfall 迭代**：一次钳制 `max(v, floor)` 会抬高 Σ 破坏守恒；实现把低于 floor 的行**钉住**，余额在未触顶行按原权重重分，迭代至不动点。`n × floor > total` 数学无解时**抛 422 而非静默截断**——截断会让"摊得总额 ≠ 待摊总额"，是分摊最忌的静默错误。
> ③ **`rounding` 与 `scale` 分工**：`scale` = 小数位（量化精度）；`rounding` = 总额取整**方向**。`none`/`round` 均走 `ROUND_HALF_UP`（`none` 不等于"不量化"——总额必须落到最小单位才能整数除法）。**写后守恒的比对基准是「取整后」的总额**（`sum(values)`），不是父行原值；返回体另给 `source_total` 保留父行原值供对账。
> ④ **`group_by` 语义定为「组间均分 + 组内按 basis」**：权重可加，故"两级都按 basis"与"只做统计分组"都恒等于不分组（死字段），只有组间均分才有区分度。同组行在结果中**不连续**，故分组必须携带下标而非顺序递推。`floor` 是最终行值的下限，只能在全部行这一层统一施加，组内局部钳制会破坏组总额守恒。
> ⑤ **`basis` 权重来源由调用方显式传 `basis_field`**（不猜列名）：`basis ∈ {value,quantity,weight,volume}` 时缺 `basis_field` 报错；子行该列为空/非正/非法一律 422——零权重会让该行分不到金额，静默跳过等于凭空丢钱。`basis=manual` 因 schema 声明 `manual_factor` 是**单值** number，只能等权；真要逐行手工系数应走 `allocate(weights=[...])`。
> ⑥ **落库与业务写入的关系定为「子行写字段 + 留痕」并存**：留痕（头记总额 + 行记摊得额，`origin=unplanned`）满足 FR-013 AC「可回放」，子行写字段满足"分摊结果要真的落到业务上"。两者**同事务**，结果行写失败则业务行一并回滚，不会出现"行上摊了钱但没有结果行"的不可回放状态。**（注：留痕表原为共用的 `calc_result`，同日 TBD-18 拆表后已迁至独立表 `allocation_result`，此处以"留痕"泛称。）**
> ⑦ **补齐两列 + 修一处枚举不匹配**：`source_document_type` / `source_document_id` 原在 yaml 中**根本不存在**（实测 `PRAGMA table_info` 确认缺失），是 FR-013 AC「来源单据可查」的载体，本轮补上；`allocation_basis` 原枚举 `{quantity,value,weight,volume,net_amount}` 与 `allocation_rule.basis` 六值**互不覆盖**（缺 equal/manual，多一个 rule 侧没有的 `net_amount`），已对齐为六值并移除 `net_amount`（它不是一种**分摊基数**，"净额"是结果属性）。**（注：这两列当时补在 `calc_result` 上，同日 TBD-18 拆表时随另三列一并迁出至 `allocation_result`——即"补在 `calc_result`"这个状态已被取代。）**
> ⑧ **错误码沿用本层分界**：`AllocationError` 自带 `status_code`，API 层 `_fail` **直接取用**而不另造映射表（400 参数错 / 404 规则或父行不存在 / 422 配置矛盾）——同一张映射表在两处维护必然漂移。`rounding` 等枚举**在入口拦**（400 `INVALID_PARAM`），否则会落到服务层被误标成"配置矛盾"（422）而串号。
> ⑨ **测试**：`test_allocation_by_rule.py`（M6 时 **36 用例**；同日二次检查后为 **42 用例**，新增负总额 `sign` / 留痕回放 / BO Action 分派三条）；契约层 `TestAllocateContract` 原在 `test_pricing_api.py`（**16 用例**，30 → 46），同日随路径提升迁至 `test_allocation_api.py`（末次 **21 用例**）。**检出能力已用定点变异验证**（非陪跑）：M6 三处——移除 `rounding` 入口白名单 → 恰 1 条转红且失败原因正是"错误码串号"；`basis_field` 不转发 → 恰 2 条转红；`_fail` 丢弃自带 `status_code` → 恰 3 条转红，其余 43 条不受影响。二次检查另验三处——`sign` 恒 `'+'` → 恰 1 条转红（`test_negative_total_records_minus_sign`）；BO Action 不分派 → 恰 1 条转红（`test_apply_handler_dispatches_on_rule_id`）；`query_results` 去 `status` 过滤 → 两文件各恰 1 条转红。
> ⑩ **【同日补修·交叉链路隔离】** 端点上线后实测发现：`calc_results` 是定价与分摊**共用**表，而三处消费入口（作废 / `explain` / `write_back`）**只按宿主三字段过滤、不区分来源**，导致两个活bug：① 对同一单据同一行跑一次定价，就把该行分摊留痕置`invalid`（分摊留痕 active 由 1 变 0，FR-013 AC「可回放」静默失效）；② `write_back` 会把分摊金额再按 `result_semantic='cost'` 写回单据头——分摊**已经**把金额写在子行业务字段上了，等于同一笔钱写两遍。**已修**：三处统一按 `allocation_rule_id IS NULL` 隔离（选它而非 `process_code != 'ALLOCATION'`，因前者是数据事实、后者靠字符串约定）。`explain` 当时留 `include_allocation=True` 口子，否则过滤等于把 FR-013 的可回放能力从 API 上摘掉（**该口子已随后续改动移除**——见 ⑫：查询出口改由 `AllocationService.query_results` 独立承担）。**注意 `origin` 不可作判别位**——它是「计划内/外」业务语义（D16）而非管线标识。作废范围仍按 Spec L973「同一宿主」，**刻意不**按 `process_code` 收窄（换过程重算同样应作废旧结果）。**通用化的结构性代价已登记 TBD-18。**
> ⑪ **【同日·路径提升】** 分摊端点由 `/api/v1/pricing/allocate` 提升为**平台级** `POST /api/v1/allocation/allocate`——算法层零业务耦合（数量/工时/重量同样适用）、留痕层已拆出独立表 `allocation_results`，挂在 pricing 下语义已不准。新增 `allocation_bp`（`meta/api/allocation_api.py`），`server.py` 与 `app_builder.py` **两条启动路径都注册**（实测路由表：新路径在、旧路径不在）。**旧路径不留别名**（用户拍板）：端点交付次日即改，仓库内外均无调用方。契约测试随之切至 `test_allocation_api.py`（**21 用例**，含二次检查新增的留痕回放 4 条）。
>   ⚠️ **过程中自查修掉一条空跑断言**：`test_old_pricing_path_is_gone` 最初只注册 `allocation_bp`，此时旧路径本就不存在于该app——断言恒过，什么也锁不住（加了别名后用例仍绿，实测才发现）。改为**同时注册两个蓝图**，并加一条反向断言「新路径必须 200」以证明 404 不是因 app 没起好；修好后定点变异验证：在 `pricing_api` 加回别名 → 恰 1 条转红（`assert 400 == 404`，失败原因正对）。
> ⑫ **【同日·二次检查】** 对分摊三层链路（`allocation_rule` → `AllocationService` → `plan`/`plan_floor`）做全面二次检查，取证分三类，全部落地：
>   · **清理（4 项 · 零行为变更）**：① `allocation_result.yaml` 的 `code` 描述写 `CR_`（复制自 `calc_result` 未改），实现是 `AR_`；② `allocate_by_rule` docstring 残留 `calc_result` / `target` 枚举写了不存在的 `price`；③ `allocation_api.py` 的 `logger`（含 `import logging`）全文件零引用（错误一律走 `_fail`）；④ `record_allocation_results` 的 `scale` 形参被调用方传入、函数体从不使用（量化已在上游 `plan()` 完成）。另统一了 `allocation_apply.py` / `allocation_service.py` 若干处「金额」措辞——`amount` 列语义是**量**（金额/工时/数量/重量同构）。
>   · **缺口（3 项 · 用户拍板本次全修）**：**G5** 分摊留痕在接口层查不到——`explain` 的 `include_allocation` 口子从未接线到 HTTP（`pricing_api` 恒用默认）。**裁决：查询边界跟着表边界走**——新增 `AllocationService.query_results()` 与 HTTP 出口 `GET /api/v1/allocation/result/<document_type>/<document_id>`（query：`document_line_id` 选填、`status=all` 含作废行）；同时从 `PricingService.explain` **移除** `include_allocation`（让定价服务读分摊表等于把共表耦合原样搬到服务层，表边界建了、查询边界也得建）。**G6** BO Action `allocation.apply` 走 v1 `allocate`（显式 weights、不写任何留痕）——改为**按参数分派**：带 `allocation_rule_id` 走 `allocate_by_rule`（含留痕），不带仍走直调口径（无规则 id 就写不出留痕行的非空外键）；`bo_action_registrations` 的 `input_schema` 同步放宽 `required` 并补齐规则驱动参数（该 `input_schema` 为 DECORATIVE 契约，不参与运行期校验，但须与 handler 实际支持一致）。**G7** `sign` 恒 `'+'`，与 `plan()` 允许负总额（红字/冲销）矛盾——改为由 `total` 方向推导（`'-' if total < 0 else '+'`），不再接受外部传入。
>   · **检出能力**：三处定点变异均被检出（移除 `sign` 推导 → 恰 1 条转红、BO Action 不分派 → 恰 1 条转红、`query_results` 去 `status` 过滤 → 两文件各恰 1 条转红），验证后全部恢复（Grep `MUTANT` 零残留）。
>   · **回归**：`test_allocation_by_rule.py` **42** + `test_allocation_api.py` **21** + `test_pricing_service.py` **65** + `test_pricing_api.py` **30** 全绿。

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
| | *(2026-10-07 复查修正)* | | ⚠️ 上句"尚未就绪"**指"运行期未接线"，非"表不存在"**——`external_rate_sources` / `pricing_periods` **物理表与 yaml 已落地**（`meta/tests/test_pricing_p2_schemas.py` 已锁其字段与枚举，`calc_results.external_rate_source_id` / `pricing_period_id` 为真实外键且已由 string 收紧为 INTEGER）。**待办只剩"取数接线"**，建表环节不在此列 |
| **TBD-3** | ~~**定价 API 端点路径与命名**~~ | 编排层接口（`price_line` / `explain` / `write_back`）与 **HTTP 端点命名**均已落地 | **✅ 已结项（v1.6）**：定名 `POST /api/v1/pricing/calculate`（IF-001）、`GET /api/v1/pricing/result/<document_type>/<id>`（IF-002，query `document_line_id`）、`POST /api/v1/pricing/write-back`（IF-003）。**实测证据**：① `create_app()` 后 `url_map` 三条路由俱在；② `meta/tests/test_pricing_api.py` **30 用例契约测试全绿**（状态码 / 字段名 / 字段类型 / 错误码分界）。`allocate` 与 `reprice` 仍属 P4 / P6 未实现，路径已预留 | IF-001、IF-002、IF-003、§9.3.3 |
| **TBD-4** | **可解释回放保留策略**（研究稿 D5） | ① 全量落库 ② 仅最近 N 次 ③ 仅在"手动查看"时重算（涉存储成本） | **🔍 2026-10-07 复查：降级为观察项，"三选一"已无意义**。原三个选项都假设"每次重算新增一行"，但**代码实际走的是作废而非删除**——[pricing_service.py](file:///d:/filework/excel-to-diagram/meta/services/pricing_service.py#L476-L484) 对同一宿主执行 `UPDATE calc_results SET status='invalid' WHERE ... AND status='active'`（刻意**不**按 `process_code` 区分，见该处 TBD-18 注记），`pricing_service.get_result` 也只按 `document_type/document_id` 取。**故默认行为已是选项 ① 全量保留 + 软作废**，无删除路径。**剩余真问题只有一个：无限增长**。**未达启动条件**：生产库零定价数据（同 TBD-14 取证），量级无从测量；且存储成本要等有真实数据才成立。**启动条件**：单宿主 `calc_results` 行数或表体积超阈值 | FR-010、NFR-003、R6 |
| **TBD-5** | 条件更新（累计用量）是否纳入首期（研究稿 D6） | ① 要 ② 先不要 | **✅ 已关闭（2026-10-06 选 ① 已实施）**：M5 完成 FR-016 接线——读侧「累计用量触顶 → 复用 `inactive` 自动失效（记 `record_inactive`）」+ 写侧「与结果落库**同事务**累加」（`transaction()` 与 `SAVEPOINT` 两分支均接入，测试锁定「明细写失败则累计一并回滚」）。**已知代价**：重算会重复计数（累计只增不减），本期不做自动冲销，`reprice` 端点（M8/P6）落地时须处理 | FR-016 |
| **TBD-6** | 在线配置 UI 与规则版本化 | 形态（文件 / DB）+ 历史单据复现策略 | **🔍 2026-10-07 复查：维持"本期不做"，但把"待定"改为"已取证"**。原表述含糊（"待定"读起来像还没决定）。**取证**：`meta/api/pricing_api.py` 仅 3 个端点（`/calculate` · `/result/<t>/<id>` · `/write-back`），**全是运行时消费，零配置写入端点**；配置只能经 git 改 yaml。C-T0-11 的 `rate_table.status='approved'` 闸门正是"无 UI 下的替代管控"。故形态问题**事实上已定为"文件 + git"**，剩下的"规则版本化"与 TBD-15② 同源（结构变更已由 C-T0-12 冻结）。**启动条件**：出现非开发角色改配置的真实诉求 | N8、§7.3 A2、TBD-15 |
| **TBD-7** | 采购侧成本类费用的实现时点 | D7 范围外，仅做对象设计 | **🔍 2026-10-07 复查：对象已落地，缺的是"成本侧取值算法"这一环**。TBD-1 拍板选项②（归分摊子域、`target ∈ {cost, expense}` 作规则字段）后**该字段实际未落地**——`Grep 'target'` 在 `allocation_result.yaml` 零命中，`result_semantic` 只是 `calc_procedure` 轴③ 的枚举声明，**承载不了 cost/expense 的路由**。已落地部分：分摊留痕独立表 `allocation_results`（TBD-18 拆表）、`write_back` 支持按 `result_semantic='cost'` 写回单据头（[allocation_result.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/allocation_result.yaml#L13)）。**故待办收敛为**：是否补 `target` 路由字段 + 采购侧取值算法。**属业务决策（非技术阻塞）**，需业务确认采购侧何时进入 | FR-013、B2、TBD-1 |
| **TBD-8** | ~~**「整体价覆盖」Override 语义缺口**~~ | 研究稿 §3 对标（Oracle EBS 五种调整类型含 **`Price Override`（New price）**；Salesforce `pricing element` 三态 **Charge / Adjustment / Override**）——即"不以当前累加结果为基准、直接改写"的语义。现行对象模型只能用 `element_type: manual` + `rate_class: price` **隐式**表达，**无一等概念**。缺什么：① 是否把 `override` 补为显式取值 ② 其与前序累加 / 后序步骤的交互规则须定义 | **✅ 已关闭（v1.5 拍板 D23 = ①）**：**复用 `adjustment`**，新增 `adjustment_type = override`（**不另立对象**——它与 `adjustment` 同构：引用原结果 + 留痕 + 不改原单据）。**交互规则**：`override` 在**前序累加完成后**生效，**直接给出最终价**并**清零其后累加步骤**（语义 = "New price"）；`reason` 必填 | FR-005、FR-014、§9.3.1 A/C/E |
| **TBD-9** | ~~**`pricing_output_map`（结果 → 单据行字段输出映射）缺口**~~ | Salesforce `PricingProcedureOutputMap` 决定"哪个定价结果写回单据的哪个字段"（研究稿 §4.6A）。`calc_result` 已泛化挂任意 `document`（FR-011），但**下游单据行字段名不同即断链**——现无此对象 | **✅ 已关闭（v1.5 拍板 D24 = ②）**：本期**不建对象**，改为**按 `result_semantic` 约定写回字段**（`price`→`unit_price`/`amount`、`cost`→`cost_amount`、`emission`→`emission_amount`，余者落 `result_amount`）。**接口已预留**——多过程 / 多结果结构时再补对象，本约定即默认映射。**v1.6 已实现**：`PricingService.write_back`（映射表 `WRITEBACK_MAP` + 字段候选集兜底 `unit_price/price/unit_cost`、`amount/total_amount/net_amount/line_amount`） | FR-011、§9.3.1 C、研究稿 §4.6A |
| **TBD-10** | **完整单位换算对象 `conversion{from_unit, to_unit, factor_expr}`**（v1.4 拍板 D19：换算归事实源取值阶段，本期只补 `base_source` 枚举 `scaled_quantity`） | 碳域需 kL → GJ（乘密度）、GWP 二次乘数（气体 × GWP = CO₂e）、定价域 `price_unit` 换算——三者形态各异。缺什么：① 是否建独立 `conversion` 对象放**事实源取值阶段**（非计算过程内）② 换算因子的来源（主数据 / 密度表 / 因子库）如何挂到 `source_type = market / measurement` 的字段上 | 后置（P6 随事实源子域）；本期不做 | FR-006、§9.3.1 E、研究稿 §4.9D2 |
| **TBD-11** | ~~**多账簿 / 多估值基础并行**~~（研究稿 D20） | Oracle 一个 Cost Organization 挂多本 Cost Book（primary 财务 / secondary 管理 / **ledgerless 模拟**），同一批事务按不同规则出多套结果；`pricing_procedure` 当前是**单实例** | **✅ 已关闭（v1.5 拍板 D20 = ②不纳入）**：属"**引擎实例化 / 编排**"层，非"过程定义"层。**边界现在就写清**：将来若做，走**引擎外多次调用**（同一 `procedure` 跑 N 次、每次带不同 `context`），**不在引擎内建多实例** | §1.4 N9、FR-005 |
| **TBD-12** | **定价结果的能力接口（interface）**（v1.5 保留，研究稿 D21 已拍板②本期不做） | Palantir Interface 提供对象类型多态；将来成本 / 碳 / 税四域结果都满足"可挂单据 · 有明细 · 可回放"这组能力时，可按能力挂载而不必共用一张表。缺什么：① 是否声明接口层 ② 四域是共用一表还是按能力分表 | **保留待议**（D21 已拍板本期不做——只有一个域，多态零收益；但它是多域时比"硬塞一张表"更保守的选项） | FR-011、§1.4 N9 |
| **TBD-13** | **"谁能改价"的完整权限 / 审批矩阵**（v1.5 保留，研究稿 D22 已拍板②只补最小一条） | 本期**已补最小一条**：`adjustment{adjustment_type=override}.reason` **必填**（FR-014）。仍缺：完整权限矩阵（谁能改价 / 改价要不要审批 / 改价上限），涉及角色、审批流、组织结构 | **保留待议 + 建议归权限引擎**（研究稿倾向：属**组织级治理**，不该由定价引擎单方面承担） | FR-005、FR-011、FR-014、§9.3.1 C |
| **TBD-14** | **`key_schema` 是否废表**（v1.6 新登记） | §7B.4 缺陷 1 取证：**六家中五家无独立"匹配键目录"**（SAP 把匹配维度内联在条件记录里；Fusion 直接挂 `QualifyingCriteria`）。本引擎保留 `key_schema` 的理由是**键可被多个 `rate_table` 复用**。缺什么：① 这个复用是否真实发生 ② 若从未复用，是否按备选 D 内联进 `rate_record.keys{}` 少一张表 | **🔍 已代码级取证（2026-10-06），暂不废表，降级为观察项**。原定「观察一个周期」不具条件——生产库**零定价数据**（实测 12 张定价表全 0 行）。取证结论：① `key_fields` **运行时代码零引用**，匹配实走 `keys{}` 逐键比对，**键结构定义尚未接线**；② `key_schema` 与 `rate_table` **无绑定关系**，结构上允许一钥多表；③ 故"复用是否发生"**既未证真也未证伪**。**真正的待办是补 `key_fields` 运行期校验**（C-T0-12 结构冻结的执行手段），而非先议废表。**✅ 该待办已交付（2026-10-07）**：落地为**通用声明式字段属性**（不是给 `key_schema` 写专用校验）——`key_schema.key_fields.semantics.custom.value_set_from = {object: factor_catalog, field: field_id}`，由 `MetadataDrivenValidator._check_value_set` 通用消费（**校验器不认识本对象，只认这条声明**），create / update 两条写入路径均拦；fail-open 口径与既有 `_check_fk_existence` 一致（目标对象/字段解析不到、或查询抛错时**放行并留痕**，不把存量脏数据变成阻断）。测试：`meta/tests/test_metadata_driven_validator.py` 新增 `TestCheckValueSet` 8 例，其中 `test_real_key_schema_declares_value_set_from` 守护 yaml 接线；`key_fields` 为 `ui.editable: false` 且不在 `ui.form.sections`，写入实际只走 import / API。**自动关闭条件**：出现第二张 `rate_table` 复用同一 `key_schema` | FR-003、§7B.5、§7B.8 备选 D、§8.2.0 T0-2、§7C.4.1 (4) |
| **TBD-15** | **配置作用域（租户隔离 / 结构版本）**（v1.6 新登记，§7C.4） | 三件套**全部是全局配置、无作用域字段**。Agent 时代配置的**本质变化是作用域而非格式**。缺什么：① 租户/组织隔离——`rate_table` 无租户字段，**否则跨租串价** ② 结构变更版本——`rate_record` 有行级 `valid_from/valid_to`，但**改结构（加因子/改键）无版本**，无法回溯"当时按什么算"（与 TBD-4 同源） ③ 用户级覆盖——建议走 `adjustment` 不改配置 | **本期只做预防性预留**（C-T0-9：`rate_table` 预留 `owner_org_id` 语义位）；**实际能力待明确的多租需求再开**。**③ 倾向"不做"**。**② 与 C-T0-12 直接相关——本期已禁止结构变更，故结构版本化本期无需实现** | §7C.4、§7C.5、C-T0-9、C-T0-11、C-T0-12、FR-011 |
| **TBD-16** | **运行态自举的完整机制**（v1.6 新登记，§7C.4.1 (5)） | 方向已拍板采纳（双装载 + 仿 SAP V/03 界面），但**机制本期全缺**。缺什么：① **配置变更历史表**（who / when / what diff）② **跨环境一致性**（测试环境有的配置生产没有）③ **结构版本化 + 迁移**（C-T0-12 已禁止结构变更，故本期不需）④ **`with_auto_schema` 闸门处置**（"禁止"→"需显式批准 + diff"） | **本期全部不做**（T0 走开发态，git 即审计，**零治理成本**）。**待明确的多租 / 自助需求再开**。**启动条件：出现"顾问要自己加因子"的真实诉求** | §7C.4.1、C-T0-12、C-T0-13、§7C.6 备选 D/F/G |
| **TBD-17** | **yaml `type: number` 未登记进类型映射**（2026-10-06 实测发现的跨域平台缺陷，非定价专属） | `FIELD_TYPE_MAP` 缺 `number` 键，而 yaml 侧长期用它声明金额 / 数量 / 单据数。`parse_field` 的 `FIELD_TYPE_MAP.get(str, FieldType.STRING)` **静默回落 STRING** → 建表落 `VARCHAR(200)`。**实测危害**：`PRAGMA table_info` 显示 `rate_records.rate` / `scale_divisor` / `allocation_weight` 全为 `VARCHAR(200)`；`UPDATE ... SET used_amount = COALESCE(used_amount,0) + 100.5` 后 `typeof` 返回 **text**、值为字符串 `'100.5'`；且**字符串比较 `'9' > '10'` 为真** —— 涉及金额上限 / 权重 / 费率的一切 SQL 算术与比较都不可靠。**影响面 15 表 49 处**，含 `calc_results.amount` / `calc_details.*` / `rate_records.*` 等**既有核心列**。**为何长期未暴露**：读取侧 `_to_num()` 做了归一，把类型错误掩盖成"能跑" | **✅ 已修（归 `FieldType.FLOAT` 而非 INTEGER——金额与数量允许小数）**。因属**全仓 yaml 级**改动，采用 `git stash` 前后**全量测试基线逐项对比**而非抽样：`Total: 14 (P=17807, F=848, E=175, S=3259)` **完全一致 → 零回归**。**遗留**：① `SchemaGenerator` 只支持 CREATE + ADD COLUMN，**已建的库不会自动改型**，需重建；② ~~更根本的修法是让 `parse_field` 对**未知类型抛错**而非回落 STRING（静默回落是此类缺陷的温床），本期未改~~ → **✅ 已修（2026-10-07）**：先**别名补全**（`FIELD_TYPE_MAP` 增 `timestamp`→DATETIME / `date`→DATETIME / `decimal`→FLOAT，覆盖 yaml 侧未映射声明），再**加守卫**——新增 `_resolve_field_type`：命中别名、或形如 `varchar(n)` / `char(n)` 者放行，**其余未知取值抛 `UnknownFieldTypeError`**；`load_yaml_file` 的兜底 `except Exception` 同步改为显式 re-raise（否则异常被吞会让对象**静默消失**）。测试：`meta/tests/test_yaml_loader.py` 新增 `TestFieldTypeResolution` 4 例（别名映射 / `varchar(n)` / 未知类型抛错 / `load_yaml_file` 不吞异常）。**剩余同源静默回落（本期未改）**：`MetaFunction.return_type`、字段 `storage`、字段 `source` 三处仍是 `.get(…, 默认值)` → **✅ 已于 2026-10-08 取证撤销（随 I-1 关闭，详见 §10.1 的 I-1 行：三处经全仓取证均无受害面，加守卫属 YAGNI，且 `source` 若误加守卫会破坏 20+ 处合法 yaml）** | 平台级、`meta/core/yaml_loader.py` |
| **TBD-18** | ~~分摊通用化：算法层已通用，但留痕层与定价耦合~~ → **✅ 已拆表（2026-10-07）** | **取证结论：算法层（`plan` / `plan_floor`）零业务耦合**——只吃 `total/weights/floor/scale/rounding`，全文件 import 仅 `decimal/re/datetime/typing/uuid` + `meta.core.*`，数量·工时·重量分摊**直接可用**（已实测确认）。**通用化的真实阻力在留痕层**：`calc_result` 29 列里 `rate`/`base`/`price_mode`/`rate_source`/`net_amount` 全是价格语义，非金额场景写入不是「空值」而是**错值**（`price_mode='carry'` 意为「无价格」、`base=待摊总额` 把金额当计算基数）。**支持通用化的实证**：`WRITEBACK_MAP` 已含 `hours`/`quantity` 语义并配了写回映射——平台本就打算把它们当一等语义，只是 `record_allocation_results` 写死 `result_semantic='cost'` 把位置占了 | **✅ 已拆表落地**（用户拍板「无需等新需求」）。① **新增 `allocation_result`（28 字段）**——分摊留痕专用表，`allocation_rule_id` 真外键指向 `allocation_rules`；② **列集裁剪**（用户拍板）——删净全部价格列，故工时/数量分摊不留错值；③ **`calc_result` 切走 5 列**（`charge_source`/`source_document_type`/`source_document_id`/`allocation_basis`/`allocation_rule_id` + 对应 relation）；④ **零数据迁移**——建表时 `calc_results`/`calc_details`/`adjustments`/`allocation_rules` 实测均 **0 行**；⑤ **`adjustments.original_result_id` 无需重建**——它指向的是**定价**结果（追溯改价只针对定价），拆表后继续指向 `calc_results`，**实测确认无风险**（这是最初担心的风险，实测不成立）；⑥ **`pricing_service` 三处 WHERE 条件全部回退**（用户拍板）——用表边界替代 WHERE 过滤，从根上消除「漏写一个条件就串数据」。**（⑩/⑪ 当时写的 `explain(include_allocation=True)` 改读新表，已在同日二次检查中**整体移除**：查询边界跟着表边界走，留痕回放改由 `AllocationService.query_results` + `GET /api/v1/allocation/result/...` 独立承担，`PricingService.explain` 不再触碰分摊表。见 §9.3.3 注记 ⑫。）。**新增快照列** `parent_id`/`allocation_basis_field`/`group_by`/`rounding`/`floor_value`——规则会被改，只存 `rule_id` 答不出「当时按什么摊的」。**检出能力三处定点变异**：服务层写回 `calc_results` → 两个文件各恰 1 条转红；新表加回价格列 → 恰 1 条转红；`calc_result` 加回分摊列 → 两个文件各恰 1 条转红。**遗留**：~~端点仍挂 `/api/v1/pricing/allocate`~~ → **同日已提升为平台级 `POST /api/v1/allocation/allocate`**（新增 `allocation_bp`，旧路径**不留别名**） | FR-013、FR-014、TBD-12、`meta/services/allocation_service.py`、`meta/services/pricing_service.py`、`meta/schemas/allocation_result.yaml` |
| **TBD-19** | **`rate_type.display_scale` / `numeric_field` 运行期零消费**（2026-10-07 新登记） | 这两列是 **v1.6 的迁移残留**：C-T0-1 把"量级换算"从 `key_schema` 移出到 `rate_type`（属"怎么算"而非"按什么匹配"），但迁移只完成了**声明搬家**——实测全仓 `*.py` **零命中**，两列**无任何消费者**。缺什么：① 量级换算是否要实装（对标 Oracle `单位成本 = 总成本 ÷ 缩放数量`，即 `base_source` 的 `scaled_quantity`，与 D19 / TBD-10 同源）② 若要实装，`display_scale`（展示量级）与 `numeric_field`（源字段）的语义边界（是"展示换算"还是"计算换算"）须先定义。**注意：Spec 从未把"量级换算"列为任何 FR 的验收项** —— FR-009 的三条 AC 分别已交付 / 已交付 / 已由 D19 明确后置（见 FR-009 的 AC 状态回填） | **本期不做**（D19 已拍板"换算归事实源取值阶段"、完整 `conversion` 后置 P6，此处另起实装会与之冲突）。**登记为观察项**，与 TBD-10 合并处置。**启动条件：出现"按量级展示 / 换算"的真实业务诉求**（与 TBD-14 / TBD-16 同一"待真实需求再开"口径） | FR-006、FR-009、D19、TBD-10、§9.3.1 A、`meta/schemas/rate_type.yaml` |
| **TBD-20** | ~~`generated_schema.sql` 的 `new_objects` 残留~~ → **✅ 已关闭（2026-10-08，随 I-2 交付）** | 该 SQL 是 **2026-05-26 的快照**，其中曾含 `CREATE TABLE new_objects`。它是「`_template.yaml` 被误注册为业务对象」这条链上**最后一个残留**——表 / 菜单 / 权限码三处污染已于 2026-10-07 清理（commit `8f5513d3`）、`ref_graph` 扫描链已于 commit `c6409995` 对齐，本快照亦于本次定点删除。**关闭依据（四查取证，非推测）**：库中无表 / 无人执行该 .sql / migration 链零命中 / 生产代码零引用（详见 §10.1 的 I-2 行）。**处置选型留痕**：曾评估「整体重新生成」，实测 **+1041/-65** 且会改动 v082 / v089 注释引用的行号，超出本项范围，故按用户拍板走**定点删除 14 行** | — | `meta/schemas/generated_schema.sql`、TBD-14、commit `8f5513d3` / `c6409995` |
| **TBD-21** | **`calc_detail` 明细行缺单价 / 费率类型留痕**（2026-10-07 新登记，零消费盘点产出） | **直接读 INSERT 取证（非启发式）**：[pricing_service.py:558-587](file:///d:/filework/excel-to-diagram/meta/services/pricing_service.py#L558-L587) 的 `INSERT INTO calc_details` 是**显式 22 列列名**，可逐列比对：① **`price_element_code` 根本不在列集内 → 该列从不写入**；② `rate_type_code` 恒写 `None`（L568）；③ `unit_price` 恒写 `None`（L570）；④ `base_level="line"` / `base_source="pricing_quantity"` / `rolling=False` 写死常量。**后果**：明细行**没有单价、没有费率类型**，只剩 `extended_amount` 与 `running_net_amount`——直接削弱 FR-010「能回答为什么是这个值」与 TBD-4 的回放能力。缺什么：① 这三列**该不该写**（`unit_price` 与 `extended_amount` 并存时的语义边界）② 若不写，是否应删列以免误导（同 TBD-19 口径）。**注意**：此类"列在、值恒 NULL/常量"**扫不出来**（字段名在 INSERT 里出现），是本表的**假阴性盲区** | **本期不修**（属功能增强而非缺陷修复，且涉及留痕口径变化，须与 TBD-4 一并定）。**登记为观察项**。**启动条件：TBD-4 回放需求真正启用时**（届时"缺单价"会立刻暴露） | FR-010、FR-009、TBD-4、`meta/services/pricing_service.py`、`meta/schemas/calc_detail.yaml` |
| **TBD-22** | **`generated_schema.sql` 整体过期（比 `new_objects` 大得多）**（2026-10-08 新登记，I-2 执行的附带发现） | 删 `new_objects` 时顺带用当前注册表（**82 对象**）重新生成做对照，暴露该快照的**过期程度远超一项残留**：旧快照 **710 行 / 33 表** → 新生成 **1665 行**，**diff +1041 / -65**。两类差异：① **82 张表在快照里缺失**，**含整个定价域 17 张**（`address` / `item` / `rate_table` / `calc_result` 等）+ T0–T2 全部交付物（`permission_set` 系、`org` 系）；② **单/复数命名口径不一致** —— 快照用复数（`new_objects` / `roles` / `permissions`），注册表用单数（`new_object` / `role` / `permission`），故首轮"幽灵表"判定里33 张全是复数差异而非真幽灵。**性质**：与 TBD-20**不同** —— TBD-20 是误注册链的**最后一块残留**（已清），本项是**快照工具整体未跟上 4 个多月演进**（快照停在 2026-05-26）。**是否要紧**：该文件**无人执行**（建库走 `SchemaGenerator` / migrations），故对运行期零影响；风险仅在**误导人**（让人以为库结构停在此处）。另实测一个既存事实：**该 SQL 根本无法被 `sqlite3.executescript` 执行**（注释与 `CREATE` 同行导致 `near "CREATE": syntax error`），但变更前后**失败语句集合完全相同**，即本项非新增问题 | **启动条件：有人把该快照当 schema 依据来读 / 执行时**。届时二选一 —— ① 走 `sync_schema.py generate` 整体重新生成（**须先解决单/复数命名口径**，否则生成结果与 yaml 不一致）+ 同步修正 v082 / v089 / `test_permission_migration_p3` 中引用的行号；② 明确它是**历史存档**并在文件头加一行免责说明。**本期只做 I-2 的定点清理，不动整体**（超出范围） | `meta/schemas/generated_schema.sql`、`meta/tools/sync_schema.py`、I-2 |

##### 10.1 实现侧待办清单（2026-10-07 首次汇总）

> 与上表**互补而非重复**：上表是「设计决策还没拍板」，本表是「**决策已定、对象已落地，但代码未接线**」。
> 此前散落在 §8.2.0.1 注记 ④ 与各 FR 注记里，**无集中清单**——2026-10-07 复查时正是因此把「代码层任务完成」误报为「待办清零」。
> **顺序按可执行性排列（不按编号）**：先列"不依赖任何前置、随时可做"的，再列有依赖链的。
>
> **收录规则（2026-10-08 补，直接源于 M7 漏登记的教训）**：**凡因任何 FR（含 `Could` 优先级、P5–P6 尾部）而无法达成的缺口，均须入本表，不得仅因"优先级低 / 不阻塞前面里程碑"而省略。** 三类清单的并集**不构成完备集**——M7（FR-017）曾长期掉出全部三类清单，根因是按 FR 编号顺序收集时自然跳过了 `Could` 尾部。**另需注意与 TBD 的边界**：既非"设计决策未拍板"、也非"对象未落地"的**纯验证欠账**（如 I-10：范式已暴露、schema 已交，只差测例）同样属本表——它不进 TBD（无待拍板项），也不进里程碑遗留（里程碑只登记交付状态），故此前掉进三层之间的缝。

| # | 项 | 现状（取证） | 前置 / 触发条件 | 落点 |
|---|---|---|---|---|
| **I-1** | ~~TBD-17 剩余三处静默回落~~ → **✅ 已关闭（2026-10-08，取证撤销，非漏做）**，**零代码改动** | **原登记假设**：TBD-17 遗留的 `MetaFunction.return_type`（[L1900](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1900)）/ 字段 `storage`（[:1345](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1345)）/ 字段 `source`（[:1348](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1348)）三处仍`.get(…, 默认值)` 静默回落，按同源手法加守卫。**全仓取证结论：三处均无受害面**（扫 `meta/schemas` **91 个 yaml**）：① **`storage` 零缺口** —— 字段块内实际取值仅 `stored`(9) / `virtual`(63)，与 `FIELD_STORAGE_MAP` **完全相等**，枚举 `FieldStorage` 亦只这 2 个成员；② **`source` 零缺口，且原"11 个可疑取值"是扫描误报** —— 首轮按 `^\s*source:` 裸扫得`ancestor`(4) / `fixed`(4) / `version`(3) / `dimension`(2) / `product`(2) / `enum_value`(2) / `domain` / `enum_type` / `service_module_code` / `source_code` / `target_code` 共 11 个不在映射表中的值，逐个追上下文后确认**全部落在 `api_params` / `filters` / `segments` / `filterFields` 块，无一在字段定义块内**（`source` 是通用键名）；且字段块内 `source` **零使用**；③ **`return_type` 零使用** —— 91 个 yaml 中一次未出现，`data.get("return_type", "float")` 恒走默认值。**⚠️ 若当初不加区分地动手，会误伤 20+ 处合法 yaml**（如 `hierarchies.yaml` 的 `api_params.source: ancestor` 报错即让对象加载失败）——这是本项取证的主要价值 | — | TBD-17、`meta/core/yaml_loader.py` |
| **I-2** | ~~`generated_schema.sql` 的 `new_objects` 残留~~ → **✅ 已交付（2026-10-08）**，纯删除 14 行（`CREATE TABLE` 8 + 2 索引 + 4 空行/注释） | **消费者取证（四查全过）**：① **库里无表** —— `meta/architecture.db` 125 张表、`wt-perm-test-fix` 48 张、根 `architecture.db` 均**无** `new_objects`（唯一命中是 `test_temp/tmp*` 下测试临时库，随机名会清理）；② **无人执行该.sql** —— [sync_schema.py:302](file:///d:/filework/excel-to-diagram/meta/tools/sync_schema.py#L302) 是**写方**，v082 / v089 migration 仅**注释引用**行号，唯一真读者 [test_permission_migration_p3.py:150](file:///d:/filework/excel-to-diagram/meta/tests/test_permission_migration_p3.py#L150) 只校验 `data_permission_rules`（该文件当前 15 skipped）；③ **migration 链零命中** `new_objects`；④ 全仓 2696 处提及**全在 `docs/` 历史文档**，生产代码零引用。**处置选型**：用户拍板**方案 A（只删这 3 段）** —— 曾评估方案 B「整体重新生成」实测 **+1041/-65**且会改动 v082/v089 注释引用的行号，超出 I-2 范围故否决。**⚠️ 附带发现（另立 TBD-22）**：用当前注册表（82 对象）重新生成，旧快照 710 行 → 新 1665 行，**82 张表缺失（含整个定价域 17 张）** + **单/复数命名差异**（快照 `new_objects` ↔ 注册表 `new_object`） | — | TBD-20、`meta/schemas/generated_schema.sql` |
| **I-3** | FR-015 事实源取数接线 | `external_rate_sources` / `pricing_periods` 两张表**已建但零服务代码**（与 `allocation_rule` 交付前状态完全同构）；`calc_results.pricing_period_id` / `external_rate_source_id` 两 FK 列**从不写入** | 无硬前置，但需先定"事实源从哪取数"（业务/技术共同定义） | FR-015、§8.2.0.1 注记 ④ |
| **I-4** | `cumulative_usage` 冲销 | 只增不减；**重算会重复计数**（TBD-5 登记的已知代价） | 随 I-5 一并处理（冲销是重算的必要组成） | FR-016、TBD-5 |
| **I-5** | `reprice` 端点（P6/M8） | 四项取证：无 `recalc` 方法 / 三策略列死字段 / 两表零服务代码 / 冲销未设计 | **须先完成 I-3 + I-4 + 策略字段读侧**，否则只是"会写错数的壳" | M8、§8.2.0.1 取证结论 |
| **I-6** | M8 `fact_snapshot` | 列**从不写入**，且 yaml 与表**均未落地**（`fact_snapshot.yaml` 不存在） | 随 I-5 | FR-012、FR-015、M8 |
| **I-7** | FR-014 追溯调整服务化 | `adjustment` 对象已建（9 字段），**生产代码零读写**——全仓仅 `test_pricing_p2_schemas.py` 引用 | **业务**确认追溯改价流程何时启用 | FR-014 |
| **I-8** | `conversion` 单位换算对象 | `meta/schemas/` **无此文件** | D19 / TBD-10 已后置 **P6 = M8**（2026-10-08 补关联：D19 已把它明确归 P6，`allocation_result.yaml` 注释亦按"价格列"口径把它与 `price_mode` 等一并删去，故属 M8 而非仅 TBD-10） | TBD-10、**M8** |
| **I-9** | **M7 = P5 扩展点接线（FR-017 逃生门）** —— 此前**三类清单都没收录它**（不在 TBD、不在 §10.1、不在 §10.2；Spec 中除里程碑表那一行外零提及） | **平台现状取证**：`ActionType.BUSINESS` 的分发存在于 [action_executor.py:956-957](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L956-L957)，但被调用的 `_execute_business` 只有**两个分支**（[:2591-2600](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L2591-L2600)）：① 有 `action.behavior` → 走 `_execute_declarative_business`（**声明式**：`behavior.precondition` 交 `ConditionEvaluator` 求值）；② **无 `behavior` → 直接返回 `fail("BUSINESS_ACTION_NOT_IMPLEMENTED", "needs custom implementation")`**。**结论**：平台当前只提供**"声明式逃生门"**（配置能表达的那部分），**没有"代码例程可注册 / 可替换"这一层**——超出声明式能力的定制**只能改引擎**，与 FR-017 的 DoD「自定义例程可插拔，**不改引擎**」**不符**。**两点范围提示**：① FR-017 的优先级是 **Could**（[L879](file:///d:/filework/excel-to-diagram/docs/superpowers/specs/2026-10-05-pricing-engine-spec.md#L879)），**非 Must**；② 该缺口**是平台级、不限定价**——影响所有走 `ActionType.BUSINESS` 的对象 | **无硬前置**（可独立做），但**属平台层能力，须先定接口形态**（例程注册表 / 命名空间隔离 / 沙箱边界）。**触发条件：出现"声明式 cover 不住"的真实定制需求**（Could 项，**非阻塞、不挡 M1–M6**） | FR-017（[L313-316](file:///d:/filework/excel-to-diagram/docs/superpowers/specs/2026-10-05-pricing-engine-spec.md#L313-L316) / L879）、M7、`ActionType.BUSINESS`、`meta/core/action_executor.py` |
| **I-10** | ~~M4 四范式逐范式复现测例~~ → **✅ 已交付（2026-10-08）**，但**暴露两处实现缺口** | **①夹具缺陷（已修）**：TR-006 原夹具 `priority1/2/3`与 `value 100/200/300` **同序**，导致 `precedence`与 `best(min_amount)` **必然同命中 id=1** —— 实测 `[1] vs [1]`，两者不可区分，"分别复现"等于没测。改用**反序夹具**（priority 升序 1/2/3× value 降序 300/100/200）后 `precedence→[1]` / `best(min)→[2]` / `best(max)→[1]` 才真正分得开。**② 实现缺口（已登记为 I-12）**：见下行。**已交**：8 例新测（`TestI10范式区分性` 5 + `TestI10已知实现缺口` 3）+ `resolve_candidates` docstring 补真实行为 | — | M4、D8 / D18、FR-004、FR-008、L202 / L1024 |
| **I-11** | **FR-012 价格传递策略接线（P4 红线）**（2026-10-08 新增） —— 从 M5 遗留中**拆出**，此前被错误地并入 I-5（P6） | 四列策略元数据**全部只在测试里被断言存在，生产代码零读写**：`price_mode` / `freeze_policy` / `reprice_trigger` / `qty_basis`（`.schema_version.json` 与 `calc_result.yaml` 均在册）。落库侧写死常量 `price_mode="carry"`、`rolling=False`，`qty_basis` **不在 `INSERT` 列集内 → 从不写入**。FR-012 AC 的三条「逐目标单据类型 × 参考单据类型可配」「开票默认 `delivered_qty`」「三种组合各可复现」**均未达成**；红线（已开票/已过账行不得隐式重定价）**无任何实现点** | **无硬前置**（纯 P4，不依赖 I-3/I-4/I-5）。**归属修正的关键**：M5 是 P4、M8 是 P6，**P4 的红线不应被 P6 的排期绑走** —— 此前 M5 遗留一并指向 I-5，会让人误以为"等 P6 做完 FR-012 就自然满足"，实际两者是独立线 | FR-012（[L249-260](file:///d:/filework/excel-to-diagram/docs/superpowers/specs/2026-10-05-pricing-engine-spec.md#L249-L260)）、D8、D14、**M5**、`meta/schemas/calc_result.yaml` |
| **I-12** | **排斥组边界无人承载（`exclusive` 退化为 `precedence`）**（2026-10-08 新登记，I-10 取证产出） | **M4 DoD 有一条从未实现**：[lookup_resolver.py](file:///d:/filework/excel-to-diagram/meta/core/lookup_resolver.py#L415-L423) 的 `exclusive`与 `precedence` 两个分支返回**都是 `live[:1]`**，代码注释自认"语义上获胜者 = 排序最前（同 precedence）"。而 FR-008 AC 第 3 条要求组边界由 `exclusion_group` **显式圈定**——实测两个调用方（[pricing_service.py:270](file:///d:/filework/excel-to-diagram/meta/services/pricing_service.py#L270) / [pricing_api.py:242](file:///d:/filework/excel-to-diagram/meta/api/pricing_api.py#L242)）**只传 `resolution` 字符串、不传组边界**，全仓 `exclusion_group` **零运行期引用**（仅测试夹具播种）。**后果**：`exclusive` 与 `precedence` 在任何数据上结果恒等，该范式**实际不可用**；原有 `test_exclusive_keeps_single_winner` 只断言 `len(r) == 1`，走哪个分支都过，是**陪跑测试** | **须先定组边界的承载形态**（`resolve_candidates` 加参数 / 调用方预筛 / 候选自带组标记），属设计决策非纯实现。**用户已拍板：本轮只如实登记，不补实现**（理由：补实现属功能扩展，超出 I-10 范围；且不掩盖比假闭环有价值）。**启动条件：出现"同组内多条候选需按组排斥"的真实数据** | M4、FR-008 AC 第 3 条、D3、**I-10**、`meta/core/lookup_resolver.py` |
| **I-13** | **定价域 UI 呈现层接线（菜单 + 详情形态 + 详情子表）** → **✅ 已交付（2026-10-13）** | **背景（三项"已交付但未接线"）**：① **菜单** —— 定价域 17 个对象**早已在库**（`menu_auto_generator` 自动生成 `{obj}-list`，`INSERT OR IGNORE` 硬编码 `show_in_sidebar=0` + `parent_menu=''`），但 [menu_permission_api.py:322](file:///d:/filework/excel-to-diagram/meta/api/menu_permission_api.py#L322) 主查询**只取 `show_in_sidebar=1`**、[:382-386](file:///d:/filework/excel-to-diagram/meta/api/menu_permission_api.py#L382-L386) 子菜单要求 **`parent_menu IN (可见集合)`** → 两条件均不满足 → **菜单在库但导航树完全不可达**（`dynamicRoutes.js` 已注册 `/rate-table` → `GenericObjectList`，即 **URL 可用、只缺入口**）；② **详情形态** —— `rate_table` / `calc_procedure` / `calc_result` 三对象 `detail_mode: drawer`，塞不下"建表 → 填阶梯行 → 发布"主工作流；③ **详情子表** —— `rate_table→rate_record` / `calc_result→calc_detail` 虽有真外键，但**无 `associations` 声明**，DetailPage 开不出子表。**交付（4 文件 +814/-3）**：① 菜单接线 —— [init_menu_permissions.py](file:///d:/filework/excel-to-diagram/meta/scripts/init_menu_permissions.py) **+707 行**，新增 **18 条菜单**（3 顶层 `multi_object_hub`：`pricing-price` / `pricing-calc` / `pricing-result`（sort 20/21/22），15 个 `object_list` 子菜单），**未挂** `external_rate_source` / `pricing_period`（M8 未开工，挂了会误导"能配但配了不生效"）；② 三对象 `detail_mode` `drawer`→**`page`**；③ 补 **2 处 `associations`**（`rate_table.rate_records` 8 列、`calc_result.calc_details` 7 列）。**实测验证（隔离 DB 复刻生产顺序，非"语法通过"）**：`server.py` L511 `persist_to_db` → L516 `init_menu_permissions`，dump 18 条菜单**逐项比对全部相符**（15 子 `parent_menu='pricing-*'` / `show_in_sidebar=0` / `page_type='object_list'`，3 hub `parent_menu=''` / `show_in_sidebar=1` / `multi_object_hub`）；可见性主查询复刻得 **3 hub 可见 + 15 子菜单可达**。**冲突语义已排除**：生成器 `INSERT OR IGNORE` 先跑、种子步骤 6 为 `SELECT→UPDATE` 后跑 → **父菜单被种子覆盖**（`auto_generated=1` 残留无害——实测该字段不参与可见性判定；步骤 7.6 的 `auto_generated=0` 清理亦不影响：hub 在 `system_menus` 内、子菜单为 1）。**方案被硬约束否决并调整**：原三层嵌套 hub（1 个 `pricing-management` → 3 子 hub）因 [GenericTabContainer.vue:98-105](file:///d:/filework/excel-to-diagram/src/views/GenericTabContainer.vue#L98-L105) 使**子 hub 渲染空白**（`objectType` 仅 `page_type==='object_list'` 时赋值）→ 改**3 个并列顶层 hub**，保"3 分组"语义、**零前端改动**。**既有失败基线对照**：`test_menu_visibility_h2_h3.py`(3F/11P) / `test_pricing_p2_schemas.py`(4F/65P) / `test_yaml_loader.py`(3F/41P) 三组**与 `git stash` 基线逐字相同** → **非本批引入**。**附带登记 4 项缺口**（见本表尾部 note） | 无（纯 UI 接线，不依赖 I-3/I-4/I-5） | `meta/scripts/init_menu_permissions.py`、`GenericTabContainer.vue`、`rate_table.yaml` / `calc_result.yaml` / `calc_procedure.yaml` |
| **I-14** | **`calc_procedure.steps` JSON 列拆为独立子对象 `calc_procedure_step`（方案①）** → **✅ 已交付（2026-10-13）** | **动因（I-13 暴露）**：`steps` 是 JSON 列（`ui.editable: false`），**非 `object_list`、无 `target_type` 可指** → 详情页 association 步骤子表**不成立**；且 Spec §9.3.1 早已按"独立子对象"主张、与实际 JSON 列实现不符（**文档-实现缺口**）。**交付**：① 新建子对象 [calc_procedure_step.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/calc_procedure_step.yaml)（表 `calc_procedure_steps`，每步一行、`calc_procedure_id` 回挂，`semantics.business_key=[calc_procedure_id, seq]`、`deletion_policy=cascade`、`skip_auto_menu`）；② 父对象移除 `steps` 字段、补 `associations.steps`（`target_type: calc_procedure_step`）；③ 服务层读路径改为 `get_procedure_steps(procedure_id)` 按 `seq` 升序装配 → **执行器 `execute(steps, base, initial_state)` 签名不变、零改动**（改为调用方装配）；④ [v094__calc_procedure_step.py](file:///d:/filework/excel-to-diagram/meta/migrations/v094__calc_procedure_step.py) 建子表 + DROP 父表 `steps` 列。**取证要点**：`calc_procedures.steps` 原为 `TEXT NOT NULL`（无 DEFAULT）→ 通用 BO insert 必因 NOT NULL 失败，且 `SchemaMigrator` **从不 DROP 列**，故须由迁移承担；**零数据迁移**（拆表时 `calc_procedures` 实测 0 行）。**回归**：`test_pricing_service.py` 65 + `test_pricing_api.py` 30 + `test_calc_procedure_executor.py` 34 全绿 | FR-005、§9.3.1 A、**I-13**、`meta/schemas/calc_procedure.yaml`、`meta/services/pricing_service.py` |

> **M8（P6）开工前置：I-3 三问（2026-10-11 补）** —— M8 是 M1–M8 中**唯一被显式标注「可选」**的里程碑（[L1027](file:///d:/filework/excel-to-diagram/docs/superpowers/specs/2026-10-05-pricing-engine-spec.md#L1027)；[L877](file:///d:/filework/excel-to-diagram/docs/superpowers/specs/2026-10-05-pricing-engine-spec.md#L877)：FR-015 优先级 `Could`），其开工卡点**不在技术、而在业务定义**。I-3（事实源取数接线）开通前须先答清三问（属**业务 + 技术共同定义**，工程方不能单方拍板）：
> 1. **外部报价源从哪来** —— `external_rate_source.quote_code`（`source ∈ {platts, lme, ice, index, custom}`）背后接哪个外部系统？**人工录入 / 定时抓取 / 对方推送**？取不到价时 `fallback_rule` 的默认口径是什么？
> 2. **计价期锚在哪个日期** —— `pricing_period.period_type ∈ {shipment_date, receipt_date, invoice_date, fixed_range}` 的**默认取值**是哪个单据日期？`start_offset` / `end_offset` 的相对基准、`average_basis ∈ {close, average, first, last}` 的默认均值口径？
> 3. **`fact_snapshot` 快照哪些字段** —— 快照须能**独立复现**当时那笔价（FR-015 护栏①），故须先定"复现所必需的**最小字段集**"（事实源取值 + 匹配键 + 命中的费率记录 + 计价期 + 外部报价）。
>
> **M8 现状取证归位（2026-10-11）**：M8 不是"从零开始"，而是**对象层已备好、消费层全空** —— `external_rate_source` / `pricing_period` 的**物理表与 yaml 已落地**（字段与枚举已被 `test_pricing_p2_schemas.py` 锁定，`calc_results` 两 FK 列已由 string 收紧为 INTEGER），**但零服务代码**；`fact_snapshot` 与 `conversion`（I-8）的 yaml **均未落地**；`factor_catalog.source_type`（T0-1）**已交付，此处只做消费**。**这与 M7 性质不同**：M7 缺的是**机制**（完全没有代码例程层），M8 缺的是**接线**（对象已备、消费未写）。
> **故「M8 不做」的实际后果 = 五项一并冻结**（是"明确不做"，不是"关闭"）：**I-3 / I-4 / I-5 / I-6 / I-8**（M8 直接拖 4 项；I-4 为 I-5 前置，故整链 5 项）。**一处精细关系须点明**：I-5 的前置列写"须先完成 I-3 + I-4 + **策略字段读侧**"，而"策略字段读侧"即 **I-11（FR-012）** —— 但 I-11 属 **P4 独立线**，**可独立推进**（做完不代表 M8 开工），**同时又是 M8 开工的前置**；二者"可独立推进"与"互为前置"并存，**不是重复登记**。
> **取舍依据（供业务判断）**：研究稿结论 —— **头部产品在此处普遍是半成品**（Oracle / SAP / Salesforce 均【未找到】标准链路，全靠自定义属性绕行），即**无成熟范式可抄，属探路型开发**；故该档决定权不在工程，而在**业务是否真有优质优价 / 大宗贸易场景**。若无，成本是"探路 + 五项接线"、收益是蓝图完整性；若有，它反而是**差异化优势**。

> **定价域 UI 呈现层登记（2026-10-13，I-13 附带产出）** —— 本轮 UI 接线**附带暴露 4 项缺口**（**第 1 项已按方案①交付、见 I-14**；**第 2 项已定性并降级为观察项**；其余 2 项如实登记、不由本轮处置）：
> 1. ~~**`calc_procedure.steps` 无独立对象、详情页开不出步骤子表**~~ → **✅ 已交付（I-14）** —— 原 `steps` 是 **JSON 列**（[calc_procedure.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/calc_procedure.yaml)），**非 `object_list`、无 `target_type` 可指**，故 association 子表**不成立**；且该列 `ui.editable: false`（灰色只读 JSON）。**方案①（拆独立对象）**：新建子对象 `calc_procedure_step`（表 `calc_procedure_steps`，每步一行、`calc_procedure_id` 回挂），父对象补 `associations.steps`、详情页据此开出步骤子表；JSON 列随迁移移除，执行器 `execute(steps, ...)` 签名不变、改由服务层按 `seq` 升序装配。**（原三条处置路：① 拆独立对象 ② 保留 JSON + 可视化编辑器 ③ 仅解 `editable: false`）**
> 2. **`rate_supplement`（条件补充）→ 观察项** —— 它是**依附 `rate_record` 的补充条款文本**（对标 SAP Condition Supplement，研究稿 §4.2 第 2 层），**非计算逻辑、不参与取价**，故**不是**评审时所指的"规则"（定价域规则类对象 `rate_type` / `calc_procedure`+`calc_procedure_step` / `exclusion_group` / `usage_group` / `allocation_rule` **均已落库且在菜单**——评审诉求已满足）。全 Spec 各 FR 验收项**无一引用**它。**处置：不落 yaml、降级为观察项**——将来若出现真实"补充条款"诉求，按子对象模式（同 I-14：独立表 + `rate_record_id` 回挂 + `skip_auto_menu`、挂 `rate_record` 详情子表）补，或退化用 `rate_record` 文本字段。**启动条件：出现真实"补充条款"业务诉求**。
> 3. **单据挂载（`pricing_result_aspect`）** —— `calc_result` / `allocation_result` 已有 `document_type` + `document_id` + `document_line_id`（与宿主双向可查），但 ① `relations` **无反向声明** ② 数据库层**无外键** ③ 宿主对象（`sales_order`）**在本仓根本未注册**（`examples/sales_order_enhanced.yaml` 因非递归 glob 未被 `yaml_loader` 收录） → `DetailPage` 的 association tab **开不出来**。**建议只登记、不做** —— 参照 `audit_aspect` 范式（`(object_type, object_id)` 泛型二元组 + DetailPage 自动 push tab）可在**宿主将来注册后**铺路（A1 情形）；若宿主**永久在外部**则挂载不成立（A2），退回独立查询页。
> 4. **3 个对象的权限码在 `permissions` 表缺失** —— `adjustment` / `usage_group` / `lookup_sequence` 的 yaml `actions` 齐全，但 `permissions` 表**无对应行**（属权限同步未覆盖，**非本轮引入**）。**启动条件：出现"要单对象授权"的真实诉求**。

##### 10.2 运行期零消费字段盘点（2026-10-07）

> **动因**：TBD-19（`display_scale` / `numeric_field`）是**偶然撞见**才登记的。为不再"发现一个登记一个"，做一次系统性盘点。

**判据**：取定价相关 17 个对象的 yaml 声明字段，其 `db_column` 在**生产 `.py`**（全仓排除 `tests/` / `.venv` / `venv` / `node_modules` / `test_temp` / `__pycache__`）中按**标识符边界**（`(?<![\w])name(?![\w])`）计数，**零命中即候选**。扫描面：**1431 个生产 py / 823 个测试 py**。

**两类盲区 —— 决定本表是"候选集"而非"结论"**：

| 盲区 | 成因 | 后果 |
|---|---|---|
| **假阳性** | 平台有通用机制（registry 反射 / 元数据驱动 CRUD / dict 批量写），字段可被**间接消费**而不以字段名出现在代码里 | 零命中**不等于**死字段 |
| **假阴性** | 列被写入**常量或 NULL** 时，字段名出现在 `INSERT` 列名里，**扫不出来** | 真正的"哑列"会被漏掉；本轮靠**逐列读 INSERT** 补出（见下 (c)） |

**结果：32 个字段生产代码零命中，分布在 10 个对象。**

**(a) 已登记，非新增欠账**（与既有 TBD 一一对应，此处仅归位）：

| 字段 | 归属 |
|---|---|
| `rate_table.owner_org_id` | TBD-15（预留语义位） |
| `rate_type.numeric_field` / `display_scale` | TBD-19 |
| `calc_result.freeze_policy` / `reprice_trigger` / `qty_basis` / `price_mode` | FR-012 → **I-11**（`price_mode` 此前未被本轮盘点列入，因它出现在 §10.2(c) 常量列；2026-10-08 归入 I-11 后四处已闭合）/ `reprice_trigger` + `fact_snapshot` + `pricing_period_id` + `external_rate_source_id` → FR-015 → **I-3 / I-5 / I-6** |
| `pricing_period` 4 字段（`period_type` / `start_offset` / `end_offset` / `average_basis`） | FR-015（I-3） |
| `external_rate_source` 3 字段（`quote_code` / `calendar_id` / `fallback_rule`） | FR-015（I-3） |
| `adjustment` 4 字段（`adjustment_type` / `delta_amount` / `effective_period` / `posted_flag`） | FR-014（I-7） |

**(b) 新发现，未登记任何清单**（12 项）：

| 对象 | 字段 | 备注 |
|---|---|---|
| `calc_result` | `base_formula` / `qty_basis` | **不在 `INSERT` 列集中 → 从不写入**；`base_formula` 直接关系 TBD-4 回放 |
| `calc_detail` | `price_element_code` | 同——从不写入（已登记 **TBD-21**） |
| `rate_record` | `rate_unit` / `exclude_bo` | `exclude_bo` **测试亦零命中**（与 `rate_type.exclusion_group_id` 配对，疑似"排斥机制未实现"） |
| `rate_type` | `rate_class` / `calc_type` / `statistical` / `exclusion_group_id` / `lookup_sequence_id` | 均为"**仅测试命中**"——测试只断言 schema 里有这一列 |
| `factor_catalog` | `is_price_relevant` | 测试亦零命中 |
| `calc_procedure` | `procedure_type` / `subtotal_keys` | `subtotal_keys` 与 `calc_detail.subtotal_key`（**有消费**）易混，须判定是否同一语义 |

**(c) 扫不到的常量列**（本轮逐列读 `INSERT` 补出，摘要已入 TBD-21）：

- `calc_details`：**`rate_type_code` 恒 `None`**、**`unit_price` 恒 `None`**；`base_level="line"` / `base_source="pricing_quantity"` / `rolling=False` 写死。
- `calc_results`：`rolling=False` / `sign="+"` / `sequence=0` / `origin="planned"` / `rate_source="rate_record"` / `price_mode="carry"` / `status="active"` 写死常量。**注意**：其中 `origin` / `rate_source` / `price_mode` / `status` 更像**有意冻结的初值**（`status` 另有软作废路径改写），**不宜按"死列"处理**。

**判定建议**：

1. **判据应升级**——"名字命中"既会**误报**（通用机制间接消费）也会**漏报**（常量列）。**能定论的只有直接读 `INSERT` / `UPDATE` 的列集**。本表价值在"缩小人工判定范围"，不在"给出结论"。
2. **(b) 中优先判定两项**：① `rate_type.lookup_sequence_id` —— 若真零消费，则"哪张 `rate_type` 走哪条查找序列"的接线在别处，须确认（`key_schema` 侧已确认是运行期一等公民，见 TBD-14 纠错）；② `calc_procedure.subtotal_keys` —— 与 `calc_detail.subtotal_key` 是否同一语义、是否重复声明。
3. **不建议现在批量删列** —— 平台处 T0 开发期，多数是"声明先行、实现未到"的**预留位**，删列会与后续接线冲突。**建议按 TBD 口径登记为观察项**（TBD-19 / TBD-21 即此处理）。

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
| 2026-10-07 | **v1.7** | **M6 FR-013 分摊执行交付 + TBD-18 拆表 + 端点路径提升 + 分摊链路二次检查**（用户评审「可以继续，另外二次检查下目前上面相关的设计和实现，看看是否有遗漏的」）。① **FR-013 分摊执行实装**（`POST /api/v1/allocation/allocate`）——不是纯接线：`allocation_rule` 此前在 `meta/services` 内**零服务代码**，FR-013 AC 的"分摊基数是可配枚举"与"可回放"两条是死字段；本轮实装服务能力本身（`AllocationService`：`plan` / `plan_floor` / `allocate` / `allocate_by_rule` / `record_allocation_results`）。**纯守恒算法**（waterfall 地板价迭代、`rounding` 与 `scale` 分工、`group_by` 组间均分 + 组内按 basis）零业务耦合，数量 / 工时 / 重量同样适用。落点见 §9.3.3 M6 注记 ①–⑨。② **TBD-18 拆表落地**——留痕由共用的 `calc_result` 迁至独立表 `allocation_result`（28 字段、真外键指向 `allocation_rules`、删净价格列），`calc_result` 切走 5 列；`pricing_service` 三处 WHERE 条件**全部回退**（用表边界替代过滤，根除"漏写一个条件就串数据"）；零数据迁移（建表时四表实测均 0 行）。③ **端点路径提升为平台级** `POST /api/v1/allocation/allocate`（新增 `allocation_bp`，两条启动路径都注册；**旧路径不留别名**）。④ **同日二次检查**（注记 ⑫）：清理 4 项（`code` 前缀 `CR_`→`AR_`、docstring 残留、`logger` 死代码、`scale` 死参）+ 缺口 3 项（G5 新增 `AllocationService.query_results` 与 `GET /api/v1/allocation/result/...`、并从 `explain` **移除** `include_allocation`，查询边界跟着表边界走；G6 BO Action `allocation.apply` 按 `allocation_rule_id` 分派；G7 `sign` 由总额方向推导）。**检出能力**：两轮共六处定点变异均恰 N 条转红、验证后全部恢复。**回归**：`test_allocation_by_rule.py` 42 + `test_allocation_api.py` 21 + `test_pricing_service.py` 65 + `test_pricing_api.py` 30 全绿。⑤ 落点：§9.3.3 注记 ⑨/⑩/⑪/⑫、TBD-18 行、IF-004 段 |
| 2026-10-07 | **v1.8** | **TBD-14 待办交付 + TBD-17 遗留修复 + FR-009 回填 + TBD-19 登记**（用户评审「再看看前面的待办」→ 多选四项）。① **TBD-14 的「`key_fields` 运行期校验」交付**——不写 `key_schema` 专用校验，落地为**通用声明式字段属性**：`key_schema.key_fields.semantics.custom.value_set_from = {object: factor_catalog, field: field_id}`，由 `MetadataDrivenValidator._check_value_set` 通用消费（**校验器不认识本对象，只认这条声明**），create / update 两条写入路径均拦；fail-open 与既有 `_check_fk_existence` 一致（目标解析不到 / 查询抛错即**放行并留痕**）。配套 i18n 两条（`validation.field.value_set_invalid` / `value_set_shape`）。测试 `test_metadata_driven_validator.py` 新增 `TestCheckValueSet` 8 例（含 `test_real_key_schema_declares_value_set_from` 守护 yaml 接线）→ 该文件 **50 passed**。② **TBD-17 遗留②（`parse_field` 未知类型静默回落）已修**——`FIELD_TYPE_MAP` 补 `timestamp`→DATETIME / `date`→DATETIME / `decimal`→FLOAT（覆盖全仓 yaml 未被映射的字段声明），新增 `_resolve_field_type`：命中别名、或形如 `varchar(n)` / `char(n)` 者放行，**其余未知取值抛 `UnknownFieldTypeError`**；`load_yaml_file` 的兜底 `except` 改为显式 re-raise（否则异常被吞会让对象静默消失）。测试 `test_yaml_loader.py` 新增 `TestFieldTypeResolution` 4 例。**回归证据（A/B 实测，非"测试通过"）**：因本批含平台级改动（`yaml_loader` / `metadata_driven_validator`），采用**回退—对比—恢复**的同口径 A/B —— 同一命令 `pytest meta/tests/test_yaml_loader.py meta/tests/test_metadata_driven_validator.py -n 0 -q` 下，改动前 `3 failed / 72 passed`、改动后 `3 failed / 84 passed`，**失败集完全相同**（3 例均为 `user_group→permission_set` 迁移遗留的既有失败：`test_load_user_group_yaml` / `test_load_many_to_many_association` / `test_registry_list_objects`，**非本批引入**），passed +12 即本批新增用例 → **零回归**。另取两项交叉取证：① **全量 90/90 schema 加载成功、`UnknownFieldTypeError` = 0**（直接证伪"新守卫把未映射类型的存量 schema 打挂"这一最大风险面）；② 全量 1103 个 failed/error 的成因签名 TOP20 **无一指向本批改动**，清一色为迁移遗留（`no such column: org_id` / `Unknown object type: user_group` / `role_id` 关键字参数等）。③ **FR-009 AC 状态回填**：三条 AC 均非缺口（AC1 阶梯两语义已交付 / AC2 有效期过滤已交付 / AC3 UoM 换算已由 D19 后置）。④ **新登记 TBD-19**：`rate_type.display_scale` / `numeric_field` 运行期零消费（v1.6 迁移残留，全仓 `*.py` 零命中）；**本期不做**，与 TBD-10 合并为观察项。⑤ 修正 v1.7 插入 TBD-19 时**吞掉 TBD-18「关联」单元格**的行内排版错误 |
| 2026-10-07 | **v1.9** | **死 schema 清理 + schema 注册判据由文件名黑名单改为语义判据**（用户追问 `role_effective_intents` 深入取证）。① **删除死 schema `role_effective_intents.yaml`（125 行）及其手写 migration `add_effective_intents.py`（113 行）**——该表**从未存在**：`v070__rename_roles_to_permission_sets.py` 注释明载「旧 plan 中 `role_menus` / `role_effective_intents` **不存在**，已跳过」；运行时扫全部 `*.db` 无 `effective_intent` 表；`get_meta_object()` 返回 `None`；手写脚本未登记进 `vNNN__` 迁移框架，从未执行。因顶层写 `bo:` 而非 `id:`，被 `parse_meta_object` 取默认值 `''`，注册成 `id=''` 的幽灵对象——**既建不出表、也取不到、还不报错**。② **注册判据语义化**（本批主改动）——`load_yaml_directory` 原用**硬编码 4 文件黑名单**（`shared_properties` / `aspects` / `_standard_actions` / `_action_groups`）区分"对象定义"与"配置字典"，新加的字典类文件漏进黑名单即静默注册（`role_effective_intents` 与遗留的 `_audit_materialization` / `audit_log_expectations` / `resource_types` **三处均是**）。改为按「顶层有无 `id:`」判断——实测黑名单 4 个**全部无 `id:`**，即新判据**可 100% 取代黑名单**而非仅作补充，且未来新增字典类文件自动生效。**取证**：真实 schemas 89 个 yaml 中 7 个无顶层 `id`（4 个黑名单 + 3 个漏网），85 个加载对象中 82 有 `id`、3 无 `id`，边界干净零误伤；`_template.yaml` **有 `id: new_object`**，不会被新判据误伤。**危害量化**：`register()` 以 `id` 为键，4 个文件映射到同一 key `''` **互相覆盖**，外部只见 1 个幽灵对象；逐一核 8 处 `list_objects()` 消费点——`drift_check`（有 `table_name` 空值守卫）、`query_service`（`fields` 为空自然跳过）、`import_export`（`name` 为空永不匹配）均无害，**唯一隐患是 `hierarchy_utils.resolve_object_id_by_depth(0)`**：幽灵对象 `get_hierarchy_depth()` 返回 `0`，当前因 `''` 在索引 7、`address` 在索引 0 先命中而侥幸未爆，**一旦加载顺序变化即会被当作 depth=0 的层级对象返回**。③ **测试**：`test_yaml_loader.py` 新增 `TestObjectDefinitionFilter` 5 例（真实 schemas 无空 id / 7 个字典文件均不注册 / 关键对象仍注册 / **判据按内容而非文件名**——刻意用 `_looks_like_config.yaml` 带 `id:` 验证仍被注册 / 无 `id:` 字典被跳过）。**守护有效性已反向验证**：回退到旧黑名单实现后该 5 例 **2 failed**，恢复后 **5 passed**。**回归证据（A/B 同口径，非"测试通过"）**：`pytest meta/tests/test_yaml_loader.py meta/tests/test_metadata_driven_validator.py meta/tests/test_app_builder.py meta/tests/test_v007_52_materialization_ssot.py meta/tests/test_effective_intents.py -n 0 -q` 下改动前 `6 failed / 103 passed`、改动后 `6 failed / 108 passed`，**失败集逐项相同**（3 例 `user_group→permission_set` 迁移遗留 + 3 例 `_standard_actions` 数量 `23 != 16` 既有过期断言，**均非本批引入**），passed +5 即本批新增用例 → **零回归**。④ **连带的自纠错**：上一轮结论"删除后幽灵对象已清除（空 id 1→0）"**是错的**——探测方法错误（`list_objects()` 返回 **id 字符串列表**，对其 `getattr(o,'id',None)` 恒为 `None`），重测实为空 id 仍为 1，只是被其余 3 个文件顶替位置。同批更正 `.ref_graph.json` 的表述：入库版 `total_yaml_files=54` **当时是准确的**（2026-09-22 提交时目录里确实只有 54 个 yaml），此后 2 周新增 35 个未重跑工具才变陈旧——是"**2 周未重跑**"而非"**入库时就错**"，需常态化重跑机制（→ **v1.11 已处置**：定位到 `ref_graph.py` 第一遍扫描漏 `_` 前缀判据，是活代码缺陷而非单纯陈旧，已修并刷新产物）。⑤ **遗留待取证**：`_template.yaml` 作为模板却被 `sync_schema` **真的建了表** `new_objects`（`architecture.db` / `architecture_tmp.db` 中均存在，带 5 个自动补 CRUD action 指向 API），且 `new_objects` 在 `sync_schema.py` / `migration_remove_updated_at.py` 的硬编码白名单内（L27/L62）——**历史用途待查，不在本批范围**（→ **v1.10 已处置**：`_` 前缀判据排除模板 + 表 / 菜单 / 权限三处污染清理） |
| 2026-10-07 | **v1.10** | **`_template.yaml` 从注册链排除 + 已产生的三处污染数据清理**（用户拍板「按方案 B 执行，先确认权限码无引用后清理数据」）。**背景（v1.9 遗留⑤）**：`_template.yaml` 文件头明写"复制此文件→重命名为 your_object.yaml"，是**给人复制的模板**，但它带 `id: new_object`，故 v1.9 的「顶层有无 `id:`」判据**放行**了它，注册成**真业务对象**并触发全链自动生成。① **代码层排除（根因）**——`load_yaml_directory` 追加第二条判据：**`_` 前缀文件一律跳过**（在解析前 `continue`，早于 `id` 判据）。至此两条判据为「`_` 前缀跳过」+「顶层无 `id` 跳过」，覆盖文档内已有的"非对象定义"约定（模板 / 共享片段 / 配置字典）。**必须先在代码层堵住**：`menu_auto_generator.persist_to_db` 用 `INSERT OR IGNORE`、`permission_sync_service.sync_all` 的 `orphaned = existing - expected` **只 `logger.warning` 从不删除**——自动生成**不可逆**，不先排除模板则删完数据会**长回来**。② **实测确证三处污染**（`sync_schema` 建表 `new_objects` 6 列 + `menu_auto_generator` 建菜单 `new_object-list`「新对象管理」`is_active=1` `sort_order=99` `auto_generated=1` + `permission_sync_service` 建 5 条权限码 `new_object:new_object_{create,read,update,delete,list}`——对象名重复两次的双重命名产物）。③ **权限码无引用取证（清理前置条件，逐表直查）**：`permission_set_permissions`（954 行）按 5 个 permission id（69/89/90/176/235）查 **0 命中**；`permission_set_menu_permissions` 查 `new_object-list` **0 命中**；`menu_permissions` **0 命中**；`permission_bundles` 无相关列；`role_permissions` 表 **0 行**。仅 `menus.required_permissions`（幽灵菜单自身 JSON）与 `permissions.code` 自身命中 → **删除无关联影响**。④ **数据清理（3 个库 + 1 个残留工作树）**：`meta/architecture.db` / `meta/architecture_tmp.db`（`DELETE menus` 1 行 + `DELETE permissions` 5 行 + `DROP TABLE new_objects`）、`data/app.db`（`DROP TABLE new_objects`）、`wt-perm-test-fix/meta/architecture.db`（陈旧残留目录一并清理）。**全部为 gitignored 库文件，清理不入库**。回滚脚本（15 条语句含原行内容）留存 `test_temp/newobj_cleanup_backup/rollback_20261007_161117.sql`。**复验**：三库扫 `menus` 污染行 / `permissions` 污染行 / `new_objects` 表 = **全部 0 / False（CLEAN）**。⑤ **测试**——`TestObjectDefinitionFilter` 由 5 例扩为 **7 例**：新增 `test_template_file_is_not_registered`（直接断言 `"new_object" not in ids`，守护本次修复）与 `test_underscore_prefixed_object_is_skipped`（`_tpl.yaml` 带合法 `id` 仍不注册，守护新判据）；原 `test_object_definition_with_id_is_registered` 的临时文件名由 `_looks_like_config.yaml` 改为 `looks_like_config.yaml`（否则会被新判据跳过）。⑥ **回归证据（A/B 同口径，非"测试通过"）**：`git stash` 回退本批两个文件 → 同 5 文件同命令跑基线 `6 failed / 108 passed`，恢复后 `6 failed / 110 passed`，**失败集逐项相同**（3 例 `user_group→org` 迁移遗留 + 3 例 `_standard_actions` 数量 `23 != 16` 既有过期断言，**均非本批引入**），passed +2 即新增用例 → **零回归**。**直接证据**：基线注册列表末尾含 `'new_object'`，批次 2 后该 id 消失，注册数 82→81 |
| 2026-10-07 | **v1.11** | **`ref_graph.py` 第一遍扫描补「`_` 前缀」判据 + 刷新入库产物 `.ref_graph.json`**（用户指令「你继续看看前面的待办」→ 复查 v1.9 遗留项①）。**背景（v1.9 遗留④的后半段）**：v1.10 只堵了 `load_yaml_directory` 一条链，而 `meta/tools/ref_graph.py` 是**另一条独立的 yaml 扫描链**，其 `build_ref_graph` 分两遍扫同一目录——**第二遍原有 `_` 前缀跳过，第一遍没有**，故 `_template.yaml` 的 `id: new_object` / `table_name: new_objects` 照样被收进 `all_table_names` 并写进产物 `all_known_entities`。**取证（非推断）**：`python -m meta.tools.ref_graph --out <tmp>` 实测重跑，产物 L713-714 仍含 `new_object` / `new_objects` → **只要有人重跑该工具，污染即被写回入库文件**（`.ref_graph.json` **是跟踪文件且未被 gitignore**），故这不是"陈旧快照"而是**活代码缺陷**。① **代码层修复（根因）**——`build_ref_graph` 第一遍扫描前置 `if yp.name.startswith("_"): continue`，与第二遍（L145）及 `load_yaml_directory` 的判据**三处对齐**；改动 **6 行**。② **实测影响面（重跑工具前后逐项比对）**：`all_known_entities` **162 → 157**，移除的**恰为 5 项**：`_action_groups` / `_audit_materialization` / `_standard_actions`（3 个 `_` 前缀配置的 stem）+ `new_object` / `new_objects`（`_template.yaml` 的 id 与 table_name）；**`total_yaml_files`(89) / `scanned_yaml_files`(85) / `total_edges`(8) / `total_warnings`(3) / `orphan_join_tables`(2) 逐项不变**，`edges` / `warnings` / `orphan_join_tables` **JSON 深度比对全等** → 判据只影响实体集，**不影响引用图分析结果**。产物 diff 仅 **-5 行**（`new_object` / `new_objects` 两行 + 3 个 `_` 前缀 stem）。③ **一处主动纠错**：初版测试断言"`shared_properties` 等配置字典不应进实体集"**是错的**——第一遍用 `d.get("id") or yp.stem` 兜底，无顶层 `id` 的配置字典本就以 stem 进实体集（实测 4 个全在），那是**与 `_` 前缀判据无关的既有行为**（stem 不带下划线）；已改为 `test_removed_entities_are_exactly_the_underscore_prefixed_ones`，**同时断言"移除的恰是那 5 项"与"stem 兜底的 4 项保持不变"**，把边界写死在测试里而非留给后人误读。④ **测试**：新建 `meta/tests/test_ref_graph.py`（此前该工具**零测试覆盖**）**5 例**——真实 schemas 无 `new_object` / 真实对象（`address`·`key_schema`·`factor_catalog`·`item`）仍进实体集防判据过宽误伤 / `_tpl.yaml` 带合法 `id` 仍被排除 / 移除项恰为那 5 项且 stem 兜底 4 项不变 / **入库产物 `.ref_graph.json` 零 `new_object`**（产物入库意味着脏产物会随仓库扩散，故代码与产物双向守护）。⑤ **影响面界定**：`ref_graph.py` **全仓零引用**（`Grep 'from meta.tools.ref_graph'` 仅命中自身与新测试），是**纯诊断工具**，不参与任何运行时链路。⑥ **回归证据（守护有效性反向验证 + 污染取证）**——**全量 A/B 口径作废并说明原因**：先后跑了两轮全量（AFTER `288` 条失败集 / BEFORE `232` 条），但 `git log` 时序证明**并行工作流在两轮之间提交了 `5ca267cb`（16:33）与 `c1ab4b27`（18:44）**，且跑 AFTER 时工作树已有未提交的 `party_relation.yaml` / 新文件 `party_group.yaml` → **两轮不在同一代码基线上，数字不可作 A/B 证据**（差异集中在 `condition_permission_service` / `effective_intents` / `derivation_pipeline` 等权限域，与本批零关联）。改用两项不受污染的口径：① **调用图取证**——`ref_graph.py` 除自身与新测试外**全仓零引用**，`meta/tests/` 中亦仅新测试引用它 → 本批不可能影响其他模块；② **守护有效性反向验证**——`git stash push -- meta/tools/ref_graph.py` 回退代码后新测试 **`3 failed / 2 passed`**（转红的确切是 3 条判据断言：`test_real_schemas_have_no_new_object` / `test_underscore_prefixed_file_is_excluded` / `test_removed_entities_are_exactly_the_underscore_prefixed_ones`；另 2 条仍过是因 stash 只回退代码、产物已是刷新后版本），恢复后 **`5 passed`** → **测试确能捕获该缺陷**。⑦ **本批不动 `generated_schema.sql`**（用户拍板）——该文件是 **2026-05-26** 的生成快照、含 `new_objects` 建表语句，但重新 `--generate` 会重写整文件（数百行变更）且有测试读它（`test_permission_migration_p3.py`），风险大于收益，**另案评估**；`.schema_version.json` 的 `new_object` 由 `sync_schema` **全量重建**（`version_data = {"objects": {}}` 后按当前 `meta_objects` 重写），下次真实 sync 自然清除，无需手工干预 |
| 2026-10-07 | **v1.12** | **§10 TBD 清单逐项复查（19 项 → 关闭 9 / 开放 10，全部标注取证状态与启动条件）**（用户指令「pricing engine spec 待办都没有了？」→ 发现此前把"代码层任务收口"误报为"待办清零"，实为两套体系，已逐项复核）。**性质**：纯 Spec 状态订正，**无代码改动、无回归面**。① **TBD-4 降级为观察项**——原三选项（①全量落库 ②仅最近 N 次 ③按需重算）**已无意义**：三者都假设"重算即新增一行"，而 [pricing_service.py](file:///d:/filework/excel-to-diagram/meta/services/pricing_service.py#L476-L484) 实为 `UPDATE calc_results SET status='invalid' ... AND status='active'`（软作废、**无删除路径**）→ **默认行为本就是选项 ①**，真问题只剩"无限增长"；未达启动条件（生产库零定价数据，量级无从测量）。② **TBD-6 由"待定"改为"已取证"**——`pricing_api.py` 仅 3 端点且**全是运行时消费、零配置写入**，配置只能经 git 改 yaml，C-T0-11 的 `approved` 闸门即替代管控 → 形态问题**事实上已定为"文件 + git"**；原"待定"措辞含糊（读起来像还没决定）。③ **TBD-7 收敛**——TBD-1 拍板的 `target ∈ {cost, expense}` 路由字段**实际未落地**（`Grep 'target'` 于 `allocation_result.yaml` 零命中；`result_semantic` 仅为 `calc_procedure` 轴③ 枚举，承载不了路由），已落地的是 `allocation_results` 独立表 + `write_back` 按 `cost` 写回单据头 → **待办只剩 `target` 字段 + 采购侧取值算法**，属**业务决策非技术阻塞**。④ **TBD-14 纠错（重要）**——原结论②"`key_schema` 与 `rate_table` 无绑定关系"**易被误读为"`key_schema` 整体与运行期无关"**。实测：`lookup_resolver.py` 载明槽位次序 = `steps[{seq, key_schema_id}]`，`LookupCandidate` / `LookupTrace` 的 `key_schema_id` 均**必填**，L533 用它走 `idx_rate_record_lookup` 索引粗筛，`key_schema.yaml` 声明 `foreign_key: key_schema_id`、`rate_record.yaml` 有真实外键列 → **`key_schema` 是运行期一等公民，不是空壳**；真正零引用的**仅 `key_fields` 一个字段**（原结论①仍成立）。**对废表判断的影响**：废表需同时改造 `lookup_sequence.steps` 的 JSON 结构与索引，**代价远高于原设想**。⑤ **TBD-2 措辞修正**——"依赖 `external_rate_source` / `pricing_period` 尚未就绪"**指运行期未接线，非表不存在**：两表 yaml 与物理表已落地（`test_pricing_p2_schemas.py` 已锁字段枚举，`calc_results` 两列已由 string 收紧为 INTEGER），**待办只剩取数接线**。⑥ **5 项保留待议（10/12/13/15/16）核实：启动条件均未触发**——`owner_org_id` 仅在测试夹具播种（`owner_org_id=None`），未进任何运行时路径；多租/自助/成本侧无真实诉求。**净结论：10 项开放 TBD 全部具备明确启动条件，无"悬空待定"**；其中仅 TBD-7 待**业务**输入，其余均为技术观察项 |
| 2026-10-07 | **v1.13** | **新增「实现侧待办清单」+「零消费字段盘点」两节**（用户指令「基于更新后的情况说明待办或 TBD 是哪些，需要的话研究下给出建议」→ 发现此前**只有"设计决策"一类的清单，没有"代码未接线"这类清单**，导致 v1.12 误报"待办清零"，遂补齐）。**性质**：Spec 补全 + 实证盘点，**无代码改动、无回归面**。① **新增 §10.1 实现侧待办清单（8 项，首次汇总）**——按**可执行性**（非编号）排列：**无前置可即做**的 I-1（TBD-17 剩余三处静默回落：`MetaFunction.return_type` / 字段 `storage` / 字段 `source`）、I-2（`generated_schema.sql` 残留）；**取数链** I-3（FR-015 事实源取数接线，两表已建零服务代码）→ I-4（`cumulative_usage` 冲销）→ I-5（`reprice` 端点，须前置 I-3+I-4）→ I-6（M8 `fact_snapshot`，**yaml 与表均不存在**）；**待业务输入** I-7（FR-014 `adjustment` 服务化，实测**生产代码零读写**，全仓仅 `test_pricing_p2_schemas.py` 引用）、I-8（`conversion`，schemas 无此文件）。② **新增 §10.2 运行期零消费字段盘点**——判据：17 个定价对象 yaml 声明字段的 `db_column` 在生产 `.py`（排除 `tests/` / `.venv` / `node_modules` / `test_temp` 等）中按标识符边界计数，零命中即候选；扫描面 **1431 生产 / 823 测试 py**；**结果 32 字段零命中，分布 10 对象**，分 (a) 已登记（归位到 TBD-15/19、FR-012/014/015、M8）/ (b) 新发现 12 项 / (c) 常量列三类。③ **盘点中确证扫描的两类盲区**（决定该表是"候选集"非"结论"）：**假阳性**（通用机制间接消费，如 registry 反射 / dict 批量写 → 零命中≠死字段）、**假阴性**（**列被写常量或 NULL 时字段名出现在 `INSERT` 里，扫不出来**）。④ **靠读 `INSERT` 列集补出假阴性盲区的实证**——[pricing_service.py:558-587](file:///d:/filework/excel-to-diagram/meta/services/pricing_service.py#L558-L587)（`calc_details`，显式 22 列）与 [L525-545](file:///d:/filework/excel-to-diagram/meta/services/pricing_service.py#L525-L545)（`calc_results`，显式 23 列）**均非通用字段循环**，故可逐列比对，查出：`calc_details.price_element_code` **根本不在列集内（从不写入）**、`rate_type_code` / `unit_price` **恒写 `None`**、`base_level`/`base_source`/`rolling` 写死常量。**后果**：明细行**没有单价、没有费率类型**，只剩 `extended_amount` / `running_net_amount`，直接削弱 FR-010「能回答为什么是这个值」与 TBD-4 回放。⑤ **新登记 TBD-20**（`generated_schema.sql` 的 `new_objects` 残留：误注册链上唯一未清残留，低风险收尾、启动条件"无"但须先取证消费者）、**TBD-21**（`calc_detail` 明细行缺单价/费率类型留痕：**本期不修**，属留痕口径变化，**启动条件 = TBD-4 回放需求真正启用**）。⑥ **盘点给出的方法论建议**：判据应从"名字命中"**升级为"读写入路径的列集"**——前者既误报也漏报，**能定论的只有直接读 `INSERT`/`UPDATE`**；(b) 中优先判定 `rate_type.lookup_sequence_id`（若真零消费则查找序列接线在别处）与 `calc_procedure.subtotal_keys`（与有消费的 `calc_detail.subtotal_key` 是否同一语义）；**不建议现在批量删列**（T0 开发期多为预留位，删列会与后续接线冲突）。⑦ **口径澄清**：头部「全部待拍板项已清零」易被误读为与"TBD 开放 12"矛盾，已改为「**决策点（D 系列）待拍板项已清零**」——D 系列指决策点（D1–D24），TBD 指待办项，**两者不是一套编号** |
| 2026-10-07 | **v1.14** | **补入"里程碑"这第三类待办来源 + 登记 M7**（用户指令「再看看目前的更新的待办」→ 复查发现此前只统计了 TBD 与实现侧两类，**里程碑 M1–M8 从未纳入待办盘点**，遂补齐）。**性质**：Spec 补全，**无代码改动、无回归面**。① **新增「里程碑状态回填」表（M1–M8）**——此前状态只能从 §8.2.0.1 的批次回填里**拼**出来：**M1–M3 已闭环**（M1 = T0-1~T0-7；M2 = T0 链 + T2-1；M3 = T2-2 + T1-1~T1-3 结果链三表）；**M4 基本交付**（四范式已在 [pricing_api.py:191](file:///d:/filework/excel-to-diagram/meta/api/pricing_api.py#L191) 暴露 `precedence`/`best`/`exclusive`/`weighted`，`exclusion_group` schema 已交 T0-5；**遗留：DoD「同一数据两范式分别复现」未逐范式核对测例**）；**M5 / M6 部分交付**（M5 的「执行期重算」后置 = I-5；M6 的 `adjustment` 追溯补差后置 = I-7）；**M7 / M8 未动**。② **新登记 I-9 = M7 = P5 扩展点接线（FR-017 逃生门）** —— 它是本次复查中**唯一"既没做、也没登记"**的项（不在 TBD、不在 §10.1、不在 §10.2；Spec 中除里程碑表那一行外**零提及**）。**平台现状代码级取证**：`ActionType.BUSINESS` 分发存在于 [action_executor.py:956-957](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L956-L957)，但 `_execute_business`（[:2591-2600](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L2591-L2600)）**只有两个分支**：有 `behavior` → `_execute_declarative_business`（声明式，`behavior.precondition` 交 `ConditionEvaluator` 求值）；**无 `behavior` → 直接 `fail("BUSINESS_ACTION_NOT_IMPLEMENTED", "needs custom implementation")`**。**结论：平台只有"声明式逃生门"，没有"代码例程可注册 / 可替换"这一层** → 超出声明式能力的定制**只能改引擎**，与 FR-017 的 DoD「自定义例程可插拔，**不改引擎**」**不符**。**两点范围提示**：**(a)** FR-017 优先级是 **Could**（L879）**非 Must**、**不挡 M1–M6**；**(b)** 该缺口**是平台级、不限定价**（影响所有走 `ActionType.BUSINESS` 的对象），故 I-9 的落点写为平台层能力（须先定例程注册表 / 命名空间隔离 / 沙箱边界），**触发条件 = 出现"声明式 cover 不住"的真实定制需求**。③ **拍板：不再另立《定价引擎实施计划》** —— 原 L1030 写「可另立…（对齐 rule-model 实施计划范式）」，实测 `docs/` 下**无此文件**（即里程碑一直没有逐项任务分解）。**改为：不另立**，理由=Spec 已承载交付物与 DoD，**另立会造成第二真相源**（清单不集中 = 漏，本项目已两次因此误判"待办清零"）；只借 rule-model 的"里程碑 ↔ 任务"映射思路，**不照搬分文件**。④ **汇总计数更新**：§10.1 由 8 项 → **9 项**；三类来源合计 **TBD 21（关闭 9 / 开放 12）+ 实现侧 9 + 里程碑 8（其中 3 项与 I 项重叠）** |
| 2026-10-11 | **v1.19** | **新增「M8（P6）开工前置：I-3 三问」+ M8 现状取证归位**（用户指令「更新文档，再解释下：M7 扩展点接线（FR-017 逃生门）」）。**性质**：Spec 补全，**无代码改动、无回归面**。**动因**：上一轮就「M8 要不要做」这一取舍展开分析后，其结论**只存在于对话、未落到文档**（与 v1.14 漏登记 M7 同类问题——分析结论若不入文档即等于没有）。① **新增 §10.1 尾部 note「M8 开工前置：I-3 三问」** —— M8 是 M1–M8 中**唯一被显式标注「可选」**的里程碑（L1027 + L877 `Could`），其开工卡点**不在技术、而在业务定义**，故把卡点具体化为**三问**（属**业务 + 技术共同定义**，工程方不能单方拍板）：**(1) 外部报价源从哪来**（`external_rate_source.quote_code` 背后接哪个外部系统？人工录入 / 定时抓取 / 对方推送？`fallback_rule` 默认口径）、**(2) 计价期锚在哪个日期**（`pricing_period.period_type` 默认取值 / `start_offset`·`end_offset` 基准 / `average_basis` 均值口径）、**(3) `fact_snapshot` 快照哪些字段**（须能**独立复现**当时那笔价，故须先定"复现所必需的**最小字段集**"）。② **M8 现状取证归位**：M8 **不是"从零开始"，而是「对象层已备好、消费层全空」** —— `external_rate_source` / `pricing_period` **物理表与 yaml 已落地**（字段与枚举已被 `test_pricing_p2_schemas.py` 锁定，`calc_results` 两 FK 列已由 string 收紧为 INTEGER）**但零服务代码**；`fact_snapshot` 与 `conversion`（I-8）的 yaml **均未落地**；`factor_catalog.source_type`（T0-1）**已交付、此处只做消费**。**⚠️ 与 M7 性质不同**：**M7 缺的是"机制"**（完全没有代码例程层），**M8 缺的是"接线"**（对象已备、消费未写）—— 二者虽同为"未交付"，但工作量性质与风险面不同。③ **明确「M8 不做」的实际后果 = 五项一并冻结**（是"**明确不做**"，不是"关闭"）：**I-3 / I-4 / I-5 / I-6 / I-8**（M8 直接拖 4 项；I-4 为 I-5 前置，故整链 5 项）。④ **点明 I-11 与 I-5 的精细关系**：I-5 前置列写"须先完成 I-3 + I-4 + **策略字段读侧**"，而该策略字段读侧即 **I-11（FR-012）** —— 但 I-11 属 **P4 独立线、可独立推进**（做完不代表 M8 开工），**同时又是 M8 开工的前置**；二者"可独立推进"与"互为前置"并存，**不是重复登记**。⑤ **取舍依据（供业务判断）**：研究稿结论 —— **头部产品在此处普遍是半成品**（Oracle / SAP / Salesforce 均【未找到】标准链路，全靠自定义属性绕行），即**无成熟范式可抄、属探路型开发**；故该档决定权不在工程，而在**业务是否真有优质优价 / 大宗贸易场景**。⑥ **计数不变**：TBD 22（关闭 11 / 开放 11）、§10.1 12 项、里程碑 8 项（M8 状态行本身已于 v1.15 修正，本轮只补前置与现状） |
| 2026-10-08 | **v1.18** | **执行 I-1（TBD-17 剩余三处静默回落）—— 取证撤销，零代码改动**（用户指令「好的，执行吧」，采纳方案 A）。**性质**：**纯 Spec 状态订正，零代码改动、零回归面**。① **原登记假设**：TBD-17 遗留的 `MetaFunction.return_type`（[L1900](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1900)）/ 字段 `storage`（[:1345](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1345)）/ 字段 `source`（[:1348](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1348)）三处仍 `.get(…, 默认值)`，按 TBD-17 已修两处的同源手法（别名 + 守卫）应加报错。② **全仓取证结论：三处均无受害面**（扫 `meta/schemas` **91 个 yaml**，逐处追上下文）：**`storage` 零缺口** —— 字段块内实际取值仅 `stored`(9) / `virtual`(63)，与 `FIELD_STORAGE_MAP` **完全相等**，枚举 `FieldStorage` 亦只这 2 个成员；**`source` 零缺口，且原判断是扫描误报** —— 首轮按 `^\s*source:` 裸扫得 11 个不在映射表中的值（`ancestor`(4) / `fixed`(4) / `version`(3) / `dimension`(2) / `product`(2) / `enum_value`(2) / `domain` / `enum_type` / `service_module_code` / `source_code` / `target_code`），逐个追上下文后确认**全部落在 `api_params` / `filters` / `segments` / `filterFields` 块，无一在字段定义块内**（`source` 是通用键名），且字段块内 `source` **零使用**；**`return_type` 零使用** —— 91 个 yaml 中一次未出现，恒走默认值 `"float"`。③ **⚠️ 本项取证的主要价值**：`source` 若当初**不加区分地**动手加守卫，会让 `hierarchies.yaml` 的 `api_params.source: ancestor` 等**20+ 处合法 yaml 抛错**、直接导致对象加载失败——这是「先取证再动手」的一次实证拦阻。④ **关闭口径**：I-1 与 **TBD-17 一并关闭**（后者遗留 ①② 已于 2026-10-07 修，③④ 经本轮取证证实**不存在受害面**），关闭性质记为「**取证撤销，非漏做**」以区别于「已实现」。**⚠️ 顺带校准一处计数**：本轮统计发现 TBD 的「关闭」在本文档中**无统一标记** —— 兼用 `~~删除线~~`（写在「项」列，如 TBD-17/18）与 `✅ 已关闭/已交付`（写在「现状」列，如 TBD-5/14）两种写法，且 TBD-20 的删除线在项列、状态列为 `—`，导致按单一列自动统计必然误计（实测三种口径分别得 10/ 11 / 12）。**逐行人工核对的准数：22 项中关闭 11 / 开放 11** —— 关闭 = TBD-1/2/3/5/8/9/11/14/17/18/20；开放 = TBD-4/6/7/10/12/13/15/16/19/21/22。头部已按准数校准。**建议**：后续若再动§10 计数，宜同时统一关闭标记写法 |
| 2026-10-08 | **v1.17** | **执行 I-2（`generated_schema.sql` 的 `new_objects` 残留）—— 定点删除 14 行+ 附带发现快照整体过期**（用户指令「可以你二次确认后执行」，方案 A）。**性质**：**纯删除**（1 文件 -14/-0，零新增），**无运行期影响**（取证证明该 SQL 无人执行）。① **消费者四查全过**：**库里无表**（`meta/architecture.db` 125 张 / `wt-perm-test-fix` 48 张 / 根库 0 张，均无 `new_objects`；唯一命中是 `test_temp/tmp*` 下测试临时库，随机名会清理）；**无人执行该 .sql**（[sync_schema.py:302](file:///d:/filework/excel-to-diagram/meta/tools/sync_schema.py#L302) 是**写方**不是读者，v082 / v089 migration 仅**注释引用**行号，唯一真读者 [test_permission_migration_p3.py:150](file:///d:/filework/excel-to-diagram/meta/tests/test_permission_migration_p3.py#L150) 只校验 `data_permission_rules` 且该文件当前 **15 skipped**）；**migration 链零命中** `new_objects`；**生产代码零引用**（全仓 2696 处提及**全在 `docs/` 历史文档**）。② **处置选型留痕**：曾评估方案 B「整体重新生成」实测 **diff +1041/-65**（旧快照 710 行 / 33 表 → 新生成 1665 行）**且会改动 v082 / v089 注释里引用的行号**，超出 I-2 范围，故按用户拍板走**方案 A 定点删除**（`CREATE TABLE` 8 行 + 2 个索引 + 4 空行/注释）。**TBD-20 随之关闭**——`_template.yaml` 误注册链（表 / 菜单 / 权限码 / `ref_graph` 扫描链 / 本快照）**至此全部清完**。③ **⚠️ 附带发现并新登记 TBD-22**：该快照的过期程度**远超一项残留** —— 用当前注册表（**82 对象**）重新生成对照，发现**82 张表在快照里缺失**，**含整个定价域 17 张**（`address` / `item` / `rate_table` / `calc_result` 等）+ T0–T2 全部交付物；且**单/复数命名口径不一致**（快照 `new_objects` ↔ 注册表 `new_object`，故首轮"33 张幽灵表"判定**全是复数差异**而非真幽灵）。**性质区别**：TBD-20 是误注册链最后一块残留（本项已清），TBD-22 是**快照工具整体未跟上 4 个多月演进**（快照停在 2026-05-26）。**启动条件：有人把该快照当 schema 依据来读/ 执行时**，届时须先解决单/复数口径再重新生成。④ **顺带实测一个既存事实（非本次引入）**：该 SQL **根本无法被 `sqlite3.executescript` 执行** —— 注释与 `CREATE` 同行导致 `near "CREATE": syntax error`；**变更前后失败语句集合完全相同**（各 2 条、零新增、零消失），故TBD-22 与此均非本次删除带来的问题。⑤ **变更后逐列比对确认**：其余 **32 张表逐列完全一致**（移除恰为 `new_objects` 一张、新增零张、列集变化零张）。TBD 由 21 → **22 项（关闭 11 / 开放 11）**；§10.1 中 I-2 结项、I-12 保持开放 |
| 2026-10-08 | **v1.16** | **执行 I-10（M4 四范式逐范式复现测例）—— 交付测试 + 暴露一处从未实现的 DoD**（用户指令「采纳建议继续」，方案 (a) + 改 docstring）。**性质**：测试 + docstring（**不改生产逻辑**）+ Spec 状态；**回归面 = `lookup_resolver` 唯一消费链**（`pricing_service` / `pricing_api`）。① **夹具缺陷（已修，这是 I-10 的真正价值）**：TR-006 原夹具 `priority 1/2/3` 与 `value 100/200/300` **同序**，导致 `precedence`（取priority 最前）与 `best(min_amount)`（取 value 最小）**必然同命中 id=1** —— 实测 `[1] vs [1]`，**两者不可区分，原5 例中至少 2 例是陪跑**。改用**反序夹具**（priority 升序 1/2/3 × value 降序 300/100/200）后方能区分：`precedence→[1]`（最高优先级，**恰是最贵**）/ `best(min)→[2]`（最低价）/ `best(max)→[1]`。② **⚠️ 缺口 A：排斥组边界从未实现（新登记为 I-12）** —— [lookup_resolver.py:415-423](file:///d:/filework/excel-to-diagram/meta/core/lookup_resolver.py#L415-L423) 的 `exclusive` 与 `precedence` 两分支返回**都是 `live[:1]`**，代码注释自认"同 precedence"；而 FR-008 AC 第 3 条要求组边界由 `exclusion_group` **显式圈定**，实测两个调用方（[pricing_service.py:270](file:///d:/filework/excel-to-diagram/meta/services/pricing_service.py#L270) / [pricing_api.py:242](file:///d:/filework/excel-to-diagram/meta/api/pricing_api.py#L242)）**只传 `resolution` 字符串、不传组边界**，全仓 `exclusion_group` **零运行期引用** → **该范式实际不可用**。原有 `test_exclusive_keeps_single_winner` 只断言 `len(r) == 1`，走哪个分支都过。**用户已拍板只登记不补实现**（补实现属功能扩展，且不掩盖比假闭环有价值）。③ **缺口 B：全组带权重时四范式一律退化为加权** —— 实测 `precedence`/`best`/`exclusive` 传入后均返回**全部 3 条**、`best` 的 `measure` 被**静默忽略**。**这是 FR-008 AC 第 3 条明确授权的行为**（"resolution 对其不生效"），但 `resolve_candidates` docstring 原写"precedence/best/exclusive 返回至多 1 条"**与实际不符** → 已补真实行为（含判定发生在读 `resolution` **之前**这一关键顺序）。④ **新增 8 例**：`TestI10范式区分性`（5，含"取一语义 vs 唯一多候选语义"对照 + 确定性复跑）+ `TestI10已知实现缺口`（3，把两处缺口**如实钉死为当前事实**，缺口消除时转红即提醒改写）。**口径说明**：I-10 **未闭合 M4**（`exclusive` 那半仍缺，改为 I-12），M4 状态由"验证欠账"改为"**验证已交、排斥组未实现**"。⑤ **自纠一次**：首版断言写"三范式两两不同"**失败** —— 反序夹具下 `precedence` 与 `best(max_amount)` **必然同命中 id=1**（"最高优先级"与"最高价"仍重合），属夹具固有性质非实现缺陷；已改为只断言**真正可区分的两组** + 确定性复跑，并在注释中写明为何不再要求全面两两可分。⑥ **守护有效性（变异测试）**：向`resolve_candidates` 注入两处行为变异（`precedence` 改为返回全部 / `best(min)` 忽略 measure），**6 failed**（4 新例 + 1 原 TR-006 + 1 缺口例转红）→ 确认守护有效，非陪跑；恢复后 **84 passed**（原 76，**净增 8**）。关联回归 `test_pricing_service` **65 passed** / `test_pricing_api` **30 passed**。§10.1 由 11 项 → **12 项** |
| 2026-10-08 | **v1.15** | **三类清单交叉核对：补I-10 / I-11，修三处映射缺口**（用户指令「针对这个你再系统性的分析下」→ 发现三类清单的**并集不构成完备集**，存在掉进层间缝隙的项）。**性质**：纯 Spec 状态订正 + 清单补全，**无代码改动、无回归面**。**背景**：把 §10（TBD）/ §10.1（实现侧）/ 里程碑遗留三张表的"关联"列逐行对撞，找出的不是遗漏登记，而是**三类清单各自都正确、合起来仍有缝**。① **新登记 I-10 = M4 四范式逐范式复现测例** —— **纯验证欠账**，全 Spec 仅4 处提及（L202 需求 / L1024 DoD / L1039 状态表 / CHANGELOG）**无一进任何清单**：它既非"设计决策未拍板"（四范式已在 [pricing_api.py:191](file:///d:/filework/excel-to-diagram/meta/api/pricing_api.py#L191) 暴露）、也非"对象未落地"（`exclusion_group` schema 已交 T0-5），而是**缺断言不缺实现**——已交"范式可被指定"，未验"每种范式在同一数据上各给出可复现的预期结果"。**与 M7 的成因不同**：M7 是"`Could` 优先级被按编号顺序跳过"，I-10 是"性质不属于现有任一层的定义"，故 §10.1 补**收录规则**兜住两类。**注意须逐范式核对四条而非两条**（`weighted` 是 v1.4 才补的第四范式、最易漏）。**这是 M4 从"实现已交"升到"已交付"的唯一条件，且无任何前置**。② **新登记 I-11 = FR-012 价格传递策略接线，并从 M5 遗留中拆出** —— **归属错配修正**：M5（P4）遗留此前一并指向 I-5，而 I-5 标注 `P6/M8`，会让人误以为"等 P6 做完 FR-012 就自然满足"。实测两者是**独立线**：FR-012 四列策略元数据（`price_mode` / `freeze_policy` / `reprice_trigger` / `qty_basis`）**全部只在测试里被断言存在、生产代码零读写**，落库侧写死 `price_mode="carry"`，`qty_basis` **不在 `INSERT` 列集内 → 从不写入**；FR-012 AC 三条（逐"目标×参考"单据类型可配 / 开票默认 `delivered_qty` / 三种组合各可复现）**均未达成**，**红线（已开票行不得隐式重定价）无任何实现点**。**P4 的红线不应被 P6 的排期绑走**。③ **修映射缺口**：M8 状态行原仅列 I-3/I-5/I-6，**漏 I-8**（D19 已把完整 `conversion` 明确归 P6，`allocation_result.yaml` 注释亦按此列删列）→ 已补，并回填 I-8 的关联列。④ **补计数纠错**：头部原写"关闭 9 / 开放 12"**误计** —— TBD-14 已标 `✅ 已交付（2026-10-07）`应归关闭，实为**关闭 10 / 开放 11**；§10.1 由 9 项 → **11 项**；里程碑状态回填表位置由 L1021-1028 更正为 L1019-1028（原表）+ L1032-1043（状态表）。⑤ **补 §10.1 收录规则**（M7 漏登记的直接补丁）：**凡因任何 FR（含 `Could` 优先级、P5–P6 尾部）而无法达成的缺口，均须入本表，不得仅因优先级低而省略**；并明确定义**纯验证欠账**亦属本表。⑥ **口径澄清（三类清单的终结条件不同，故"清零"无统一含义）**：**TBD 永不"清零"**（有新证据即重开——TBD-4 从"待定三选一"被降级重写、TBD-6 从"待定"被取证重写、TBD-14 更是一次"关闭"实为**换了一个问题**），I-x 与 M-x 才是"接线即终结 / 交付即终结"。这正是此前两次误报"待办清零"的机制性根因。⑦ §10.2(a) 交叉引用补 `qty_basis` / `price_mode` → I-11，FR-012 四列至此在 TBD / I-x / §10.2 三处**闭合无缝隙** |
| 2026-10-13 | **v1.20** | **定价域 UI 呈现层接线交付（I-13）+ 实测验证 + 4 项缺口登记**（用户指令「你通盘看一下…合理的 UI 呈现方案应该是什么样子的？」→「确认 hub 形态 + 追问规则是否需配置页」→「按这个方案来」→「继续」）。**性质**：**UI 层代码改动**（4 文件 +814/-3）+ Spec 状态回填，**无引擎逻辑改动、零运行期回归面**。① **根因链（取证）**：定价域 17 对象**早已在库**（`menu_auto_generator` 生成 `{obj}-list`，`INSERT OR IGNORE` 硬编码 `show_in_sidebar=0` + `parent_menu=''`），但 `menu_permission_api.py:322` 主查询**只取 `show_in_sidebar=1`**、L382-386 子菜单要求 **`parent_menu IN (可见集合)`** → 两条件均不满足 → **菜单在库但导航树完全不可达**（`dynamicRoutes.js` 已注册 `/rate-table` → `GenericObjectList`，即 **URL 可用、只缺入口**）。② **交付**：`init_menu_permissions.py` **+707 行**新增 **18 条菜单**（3 顶层 `multi_object_hub`：`pricing-price` / `pricing-calc` / `pricing-result`，15 个 `object_list` 子菜单；**未挂** M8 未开工的 `external_rate_source` / `pricing_period`），3 对象（`rate_table` / `calc_procedure` / `calc_result`）`detail_mode` `drawer`→**`page`**，补 **2 处 `associations`**（`rate_table→rate_record` 8 列 / `calc_result→calc_detail` 7 列）；字段真实性经独立校验脚本 **ALL PASS**（曾误写 `rate_value`，实为 `rate` + `value` 两列，已纠正）。③ **实测验证（隔离 DB 复刻生产顺序，非"语法通过"）**：`server.py` L511 `persist_to_db` → L516 `init_menu_permissions`，dump 18 条菜单**逐项比对全部相符**（15 子 `parent_menu='pricing-*'`/`show_in_sidebar=0`/`object_list`，3 hub `''`/`1`/`multi_object_hub`）；可见性主查询复刻得 **3 hub 可见 + 15 子可达**。**冲突语义已排除**：生成器 `INSERT OR IGNORE` 先跑、种子步骤 6 为 `SELECT→UPDATE` 后跑 → **父菜单被种子覆盖**（`auto_generated=1` 残留无害——实测该字段不参与可见性判定；步骤 7.6 的 `auto_generated=0` 清理亦不影响：hub 在 `system_menus` 内、子菜单为 1）。④ **方案被硬约束否决并调整**：原三层嵌套 hub（1 个 `pricing-management` → 3 子 hub）因 [GenericTabContainer.vue:98-105](file:///d:/filework/excel-to-diagram/src/views/GenericTabContainer.vue#L98-L105) 使**子 hub 渲染空白**（`objectType` 仅 `page_type==='object_list'` 时赋值，该坑在代码注释中被记录为用户实测过）→ 改**3 个并列顶层 hub**，保"3 分组"语义、**零前端改动**。⑤ **既有失败基线对照（`git stash` 逐字排除）**：`test_menu_visibility_h2_h3.py`(3F/11P) / `test_pricing_p2_schemas.py`(4F/65P) / `test_yaml_loader.py`(3F/41P) 三组**与基线逐字相同** → **非本批引入**。⑥ **新登记 4 项缺口（详见 §10.1 尾部 note，均不由本轮处置）**：`calc_procedure.steps` 无独立对象/详情页开不出步骤子表（JSON 列，三条处置路**待拍板**；Spec §9.3.1 曾主张拆 `calc_procedure_step` 独立对象，**与实际实现不符**，属文档-实现缺口）、`rate_supplement` 无 yaml 未接线（**待用户确认**是否即所指"规则"）、单据挂载 `pricing_result_aspect`（**建议只登记不做**，宿主 `sales_order` 本仓未注册）、`adjustment`/`usage_group`/`lookup_sequence` 权限码在 `permissions` 表缺失（权限同步未覆盖）。⑦ §10.1 由 12 项 → **13 项**；头部状态同步 v1.20 |
| 2026-10-13 | **v1.21** | **计算过程步骤拆表交付（方案①）—— `calc_procedure.steps` JSON 列拆为独立子对象 `calc_procedure_step`**（用户指令「按方案①执行拆分，并更新相关文档」）。**性质**：**数据模型拆表**（新建 1 schema + 1 migration + 改 4 文件）+ 测试适配 + Spec 回填，**无引擎逻辑改动**（执行器签名不变）。① **动因**：I-13（UI 呈现层接线）暴露 `calc_procedure.steps` 为 JSON 列——`ui.editable: false`、**非 `object_list`、无 `target_type`** → 详情页 association 子表**不成立**；且 Spec §9.3.1 早已按"独立子对象"主张、与实际实现不符（**文档-实现缺口**）。② **交付**：新建 [calc_procedure_step.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/calc_procedure_step.yaml)（13 字段 / 2 索引 / `relations:[]` / `skip_auto_menu`，`semantics.business_key=[calc_procedure_id, seq]`、`deletion_policy=cascade`）；[calc_procedure.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/calc_procedure.yaml) 移除 `steps` 字段、补 `associations.steps`、改 form/detail 引用；[pricing_service.py](file:///d:/filework/excel-to-diagram/meta/services/pricing_service.py) 读路径改为 `get_procedure_steps(procedure_id)` 按 `seq` 升序装配（**执行器 `execute(steps, base, initial_state)` 签名不变、零改动**，改为调用方装配）。③ **迁移** [v094__calc_procedure_step.py](file:///d:/filework/excel-to-diagram/meta/migrations/v094__calc_procedure_step.py) 建子表 + DROP 父表 `steps` 列（**`SchemaMigrator` 从不 DROP 列**，故须由迁移承担；`calc_procedures.steps` 原为 `TEXT NOT NULL`（无 DEFAULT），不移除则通用 BO insert 必因 NOT NULL 失败）。**零数据迁移**（拆表时 `calc_procedures` 实测 0 行）。④ **回归**：`test_pricing_service.py` 65 + `test_pricing_api.py` 30 + `test_calc_procedure_executor.py` 34 全绿（测试改用逐行 insert 的 `_set_steps` 助手——`_raw_sql_bridge` 的 `rows=` 多行路径有 binding bug）。⑤ **文档同步**：§9.3.1 A 表拆出 `calc_procedure_step` 行、`calc_procedure` 行步骤改由子对象承载；§8.2.0.1 注① 与 [calc_detail.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/calc_detail.yaml) 中 `calc_procedure.steps[]` 措辞改为 `calc_procedure_step`；§10.1 新增 **I-14**（13 → 14 项）；§10.1 尾部 note 第 1 项由"待拍板"改为"已交付"。**⚠️ 未决**：`meta/schemas/.schema_version.json`（git 跟踪的生成物）未随 yaml 变更重跑 `sync_schema`，判定为良性漂移、本批不动 |
| 2026-10-13 | **v1.22** | **`rate_supplement`（条件补充）定性订正并降级为观察项**（用户指令「按方案 A 执行，将 rate_supplement 降级为观察项」）。**性质**：**纯 Spec 状态订正**，**无代码改动、无回归面**。① **定性**：`rate_supplement` 是**依附 `rate_record` 的补充条款文本**（对标 SAP Condition Supplement，研究稿 §4.2 第 2 层），**非计算逻辑、不参与取价** → **不是**评审时（I-13）所指的"规则"。② **误判来源**：I-13 复核 §9.3.1 B 时，`rate_supplement` 是**唯一"在 §9.3.1 B 登记却无 yaml、未接线"的对象**，因而被当作"规则缺失"候选登记；但定价域**规则类对象**（`rate_type` 计算规则 / `calc_procedure`+`calc_procedure_step` 执行规则 / `exclusion_group` 互斥规则 / `usage_group` 累计规则 / `allocation_rule` 分摊规则）**均已落库且在菜单** —— 评审诉求其实早已满足。③ **取证**：全 Spec 中 `rate_supplement` 仅出现于 §9.3.1 B 对象表 / §10.1 缺口 note / CHANGELOG，**各 FR 验收项无一引用**；`meta/schemas/` 无文件、库中无表/菜单/权限码（实测）。④ **处置（方案 A）**：**不落 yaml、降级为观察项** —— 将来若出现真实"补充条款"诉求，按子对象模式（同 I-14：独立表 + `rate_record_id` 回挂 + `skip_auto_menu`、挂 `rate_record` 详情子表）补，或退化用 `rate_record` 文本字段。**启动条件：出现真实"补充条款"业务诉求**。⑤ **同步**：§9.3.1 B 该行改为"补充条款文本 · 非计算逻辑 · 未落地 yaml，见 §10.1 观察项"；§10.1 缺口 note 第 2 项由"待确认是否规则"改为"已定性 · 观察项"、note 抬头同步；头部版本 v1.22 |
