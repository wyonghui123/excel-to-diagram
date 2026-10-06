# 定价引擎（Pricing Engine）研究 —— 头部产品对标与平台建设路径

> **版本**：v2.1 | **日期**：2026-10-05 | **状态**：研究报告（**D7 / D8 / D14 / D15 已拍板**；D2/D3 已给专业建议，见 §8；二期深化：条件类型 / 主数据全景 / 计算基准，见 §4.1–§4.3；**三期深挖：Oracle Fusion 与 Salesforce 定价引擎逐层解构与启示，见 §3.1.2 / §3.1.3 / §4.4**；**v1.4 为二次检查修正版**——重核 SF 元素计数（15+5，非 16）、重定"过程内分摊"判据、厘清 `base_roll` 与 `base_step` 关系；**v1.5 为四期深化版**——单据流价格传递策略（搬运 / 按量重算金额 / 完全重定价）与数量基准（`qty_basis`）；**v1.6 为五期深化版**——定价的业务对象结构与订单 / 订单行 / 单据对象的关系，见 §4.6 / §10；**v1.7 为六期深化版**——**事后 / 计划外费用与分摊**（含采购侧对称与追溯补差），见 §4.7 / §10；**v1.8 为七期深化版**——基于**质检结果 / 事实数据**的重新计算（**优质优价 / 大宗贸易**），见 §4.8 / §10；**v1.9 为二次检查修正版**——把 v1.7 / v1.8 新增内容与全篇口径重新对齐（`provisional_settlement` 入枚举 / 件号笔误 / 阶段口径 / D17 笔误），并复证**金蝶"计算策略"属定价过程内**，见 §3.1.6 / §3.2 / §10；**v2.0 为跨域二次研究版**——元模型已改"领域中立 + 三轴参数化"后，用 **Oracle 自家成本域（SCM Cost Management）与碳域（EAR / OFS 气候 / EPM Sustainability）** 做反向验证：三轴全部成立、发现**第四消解范式 `weighted`**、同时取得一条"**Oracle 自己也不做通用引擎**"的反证，见 §4.9 / §1(17) / §6.1 #28–#30 / §8 D18–D20 / §9 S53–S58 / §10；**v2.1 为 Palantir 研究版**——引入**第三条通用化路径**作对照组（通用对象图 + 行为附着 vs 元模型 + 参数化），并确认 **Palantir 无产品化定价引擎**、**Action Type 与本引擎同构**、**"配置化 vs 代码化"被官方定为二选一**，见 §4.10 / §1(18) / §6.1 #31–#32 / §8 D21–D22 / §9 S59–S63 / §10）
>
> **关联文档**：
> - [规则模型研究（属性确定与自动带出）](2026-10-02-rule-model-research.md)（**上位/姊妹篇**：那篇讲"**因子 → 属性的确定**"；本篇是它 §10.4 单列的**定价**专题，讲"**金额是怎么一层层算出来的**"）
> - [规则模型实现计划](2026-10-02-rule-model-implementation-plan.md) / [规则模型 Spec](2026-10-02-rule-model-spec.md)
> - [规则的消费与分层](2026-10-03-rule-model-consumption-and-layering.md) / [规则的编排、次序与传播](2026-10-03-rule-orchestration-ordering-and-propagation.md)
> - [单据流 Copy Control 深度研究](2026-09-29-doc-flow-copy-control-research.md)（下游消费方：复制时"带价 vs 重定价"）
> - [对象模型总纲：计划与事实](2026-09-30-object-model-guideline-plan-vs-fact.md)
>
> **本文回答**：平台**有没有**定价引擎？**该不该**造一个独立的？头部产品（SAP / Oracle / Salesforce / Microsoft / Odoo / 金蝶）的定价机制**共性骨架**是什么？落到我们平台，**能复用哪些既有资产、边界在哪、缺口怎么补、先做哪一步**？二期深化三问：**条件类型是配置对象还是枚举**？定价还依赖**哪些主数据/配置对象**？**计算基准**是表头还是行、基准怎么定？（§4.1–§4.3）
>
> **核实说明**：本篇头部产品结论均来自官方文档 / 官方帮助页（SAP Help、Oracle Docs、Salesforce Developer、Microsoft Learn、Odoo Docs、金蝶官方社区）及权威二手资料，标注 **【确定】/【基本确定】/【未找到】**；未检索到的一律写【未找到】，不臆造。平台侧结论均经**代码级核实**并附文件行号。

---

## 1. 结论先行

1. **平台目前没有定价引擎**——不是"弱"，是"没有"。全仓无任何 `*pricing*` 文件；`meta/core` 下 13 个 `*engine*.py` 中没有定价引擎（§2 取证）。
2. **它确实该是一个独立引擎**，而不是"再写几张规则表凑合"。上位文档 [规则模型研究](2026-10-02-rule-model-research.md) §10.4 已判定：定价是"同族里最复杂的一类"（多层累加 / 互斥 vs 累加 / 冲突取优 / 值类型多样），**宜独立引擎**。
3. **头部六家的骨架高度一致**：`价目表 + 条件规则 + 可配置计算序列 + 优先级/取优消解 + 可解释回放`（§3、§4）。分歧只在"**判定范式默认选哪个**"和"**扩展点长什么样**"。
4. **平台已有的确定性机制可以复用约一半**：条件表达式内核（`condition_parser`/`condition_evaluator`）、"分组 + 首个命中 + tie-break"语义（`MetaDefaultRule`）、安全表达式求值（`SafeExpressionEvaluator`）、值计算的宿主（`MetaComputation` 的 `formula`）。**真正缺的是"多层累加 + 多候选取优 + 条件记录（价目行）"这三件**（§5、§6）。
5. **建议路径**：先做"**单层取价（首个命中）→ 多层累加 → 取优/互斥 → 阶梯/有效期 → 可解释回放**"的渐进式独立引擎，**不要**在上位规则表里硬塞（§7）。
6. **一句话边界**：`default` 规则回答"**填哪个价目表**"，`compute` 回答"**总额 = 数量 × 单价**"，**定价引擎回答"这个单价/这行金额是怎么一层层算出来的"**（§5）。
7. **条件类型（Condition Type）必须是"配置对象"，不是硬编码枚举**——六家全部如此（SAP 的 V/06 / M/06 **可自建**条件类型，含条件类 / 计算类型 / ± / 舍入 / 排斥组 / 条件更新 / 组条件）。硬编码的只是"**计算类型**"这个**属性枚举**（百分比/定额/数量/公式），条件类型本身要可维护（§4.1）。
8. **定价不止依赖"六个必备件"，还依赖一串主数据 / 配置对象**：条件表（字段组合）、价目行、客户价格组 / 客户定价过程、物料价格组 / 税分类 / 参考物料、销售区域、UoM + 换算、币种 + 汇率、税码 / 税率……平台现存仅 **UoM / 单位换算 / 物料组 / 物料 / 伙伴 / 组织**，**币种（仅枚举引用）、汇率、税、客户价格组、物料价格组、销售区域细分**多为缺口（§4.2）。
9. **计算基准是"行级默认、表头可选、且基准 ≠ 数量"**：默认**逐行**计算；表头条件算一次并（挂组条件时）**按行价值分摊到行**；基准量默认取**定价数量（pricing quantity）**，可被 **Condition Base Value 公式**改写为价值 / 重量等；**From/To 步骤**决定"基于哪个前序步骤的中间结果"。故"基准"要拆成**层级 / 基准量 / 基准步骤 / 是否滚动**四件（§4.3、§4.4）；其中 **"是否滚动"与"基准步骤"互斥**——滚动即改以"**当前滚动净价**"为基准（Oracle Running Net Price 是一个**持续更新的单一累加器对象**），不再指定具体前序步骤。
10. **Oracle Fusion 把整条定价链拆成"服务映射 + 定价矩阵 + 定价算法"三件套**：算法是**逐步骤更新内存 SDO** 的**有序可改序列**，输出 **Charge + ChargeComponent**（每步一个 component，即"定价明细"的现成形态），并把"**基准**"提升为**一等对象**（Price Element + **Pricing Basis**，Usage = Adjustment Basis）；折扣分 **cascading（以 Running Net Price 为滚动基准） vs cumulative（以 List Price 为固定基准）**——证明**"基准量是否滚动"必须可配**（§3.1.2、§4.4）。
11. **Salesforce（Revenue Cloud Advanced）把定价过程做成"可插拔 Element 列表"**：Pricing Procedure = **ExpressionSet 扩展**，标准含 **15 个价格元素 + 5 个控制元素**（List / Volume / Tier / Attribute / Bundle / Formula / Manual / Subscription / Proration / Price Adjustment Matrix / **Derived Price / Aggregate Price / Discount Distribution Service / Price Tracking** / Rounding；控制类 List Operation / List Group / Map Line Item / Assignment / Price Setting），底层是**可引用 SF 对象的决策表**（需 **Pricing Recipe** 批量刷新）——据此**重划了原稿 §5.2 的边界**：**判据从"是否守恒 / 是否跨单据"改为"是否作为定价过程的一步"**——因为 SF 的 **Discount Distribution Service 本身就是过程内的一步**（头级折扣跨行分摊、带地板价与分摊规则决策表），故**同一单据内的头→行分摊属定价**，只有**过程之外**的跨单据/跨期间搬运才归 allocation（§3.1.3、§4.4、§5.2）。
12. **上游订单的价流到下游单据时，"搬 vs 算"是必须显式配置的策略**（§4.5）：这不是一个布尔，而是**两个正交维度**——① **传递策略**（搬运 / 按量重算金额 / 完全重定价，且可**逐属性**价·运费·税与**逐条件类型**覆盖；对标 SAP 复制控制 `Pricing Type A–Z`、Oracle `Freeze Price/Shipping/Tax`、SF Repricing Service）；② **数量基准**（订单量 / **实际交货·发货量** / 累计已开票量；对标 SAP `FKMGK`、Oracle 21D/24C 按实际发货量与重量回写 extended amount）。**"单价是否重取"与"用哪一版数量"必须解耦**，否则会出现"想只按实际量重算金额、却把价也重取了"这类静默错误。**红线：已开票/已过账的行不得隐式重定价。**

13. **定价结果不是独立"定价单据"，而是业务单据的从属对象**（§4.6）：三家无一建独立定价单据——SAP `KONV`/`PRCD_COND` 的**条件行随单据存**（头表只有聚合号 `KNUMV`），Oracle **`Charge` 挂订单行**（`ChargeComponent` 挂 Charge），SF 用 **`PricingProcedureOutputMap`** 把结果**映射回单据行字段**。→ 平台应**复用 `document` 型 BO + `composition 1:N` 范式**，落成 **`pricing_result`（行级/头级 `level` 标记）+ `pricing_step`（步骤明细）**，**不引入独立"定价单据"**（否则与 `doc_flow` 争"谁是单据"）。**两条链须分开**：价目行/条件记录=主数据（计划侧），`pricing_result`=事实（单据从属）。

14. **"事后 / 计划外费用"与"过程内条件费用"是两类，须分开建模**（§4.7）：① **过程内条件费用**（运费 / 附加费 / 税，下单时由条件记录命中）已在 §4.3 / P2 覆盖；② **事后计划外费用**（采购的计划外交付成本、后续借项贷项、落地成本、返利结算；执行期的仓储滞期费、服务费）**发生晚于单据创建、且来源单据不是订单**，三家一致的打法都是"**不改原单价、独立费用行 + 分摊**"（Oracle 生成独立 **acquisition cost adjustment**；SAP 计划外交付成本走独立行 / 独立 G/L 科目）；③ **分摊基数必须落成可配枚举**（**Oracle LCM 六种：均等 / 价值 / 手工系数 / 数量 / 体积 / 重量**；SF **DDS 分摊规则决策表**），**去向（进成本 or 进费用）也是可配字段**（Oracle 计入**库存成本与 COGS**；SAP 按**物料价格控制 + 库存覆盖**决定进库存价值 / 价差 / 总账费用）；④ **追溯调整必须显式触发 + 引用原结果 + 成对留痕**（SAP 条件记录变更**不自动**重算已过账单据、返利**最终结算冲抵已结算部分**；Oracle 事后调价由 **Cost Accounting** 回写库存估值）——**与 §4.5C 红线同源**。

15. **"事实数据驱动的重算"是独立一路，原稿只有"按实际数量"**（§4.8）：① 事实源切三类——**质量（质检 / 化验）、计量（重量 / 水分）、市场（外部报价）**，共同点是"**来源 ≠ 订单条件记录**"（与 §4.7 事后费用**同族**）；② 进入定价有**两条路**——**作为条件表的一个字段维度**（SAP **`VARCOND` 变式键** / SF **`AttributeBasedAdjustment`** / Oracle **extensible attribute**）→ 支撑**优质优价**；或**作为数量折算输入**（**干吨 / 净干重 / 金属量**）→ 支撑**按品质计量结算**；③ **大宗贸易 = 两段式（暂定价 → 终价）**，靠"**重算 + 差值结算、不改原单据**"实现（SAP **CPE**：差额自动生成 credit / debit memo；**F&A** 按**计价期**取外部报价均价）；④ **"质检值直接改价"在头部产品普遍是"半成品"**（Oracle / SAP / SF 均【未找到】现成链路）→ 平台把**事实源字段做成一等**（`source_type ∈ {static, master, quality, measurement, market}`）即**能力增量**；⑤ 护栏：**事实快照必须存档**（`fact_snapshot`）+ **重算须显式触发**（`reprice_trigger` 加 `on_quality_result` / `on_pricing_period_end`）+ **暂定价与终价配对可查**（`pricing_adjustment.original_result_id`）。

16. **金蝶"计算策略"经复证属"定价过程内"（v1.9 收口）**（§3.1.6）：它不是"取价后二次加工"，而是**公式化因子聚合层**——把基础价 / 变式价 / 区域价差等设为**计算因子**，用公式组合成取价结果，并进入**"查看定价过程 / 取价日志"可回放链路**（金蝶官方实践案例【基本确定】）。→ 说明**"过程内多因子聚合"在七家中普遍存在**，只是金蝶**非 SAP 式多步条件序列**（合并为一条公式）；且该能力**仅星空旗舰版 / 星瀚具备，星空标准版无**（写稿须标版本）。

17. **★ 跨域二次研究（v2.0 新增）：把同一套骨架拿到 Oracle 成本域 / 碳域逐字对撞，三轴全部成立，但 Oracle 自己也不通用**（§4.9）：① **成本域**——`Roll up Costs` 官方定义"总成本 = 固定成本 + 变动成本（**单位资源成本 × 消耗数量**）→ **单位成本 = 总成本 ÷ 缩放数量**"，与定价域 `Net Price = Σ(价目行 × 数量)` **逐字同构**；碳域 `排放量 = 活动数据 × 排放因子`（100,000 KWh × 0.9 kg CO2-e/KWh = 90,000 kg）**同样同构**；② **消解机制跨域同构**——Oracle 碳域的排放因子有一条 **5 级 precedence 链**（**物料 > 供应商 > 组织 > 政府(按地点) > 政府(通用)**），与它自己定价域的 `Precedence`、与平台 `default_by_priority` **同一套"逐级覆盖 + 首个命中"**；③ **发现第四种消解范式 `weighted`**——多条同 rank 候选**不取一，而是全部参与按权重加权求和**（Oracle 内部至少三处：Sourcing Rule allocation% / 工单 `Cost Factor Allocation` / LCM `Charge Basis = % of item price`），这是平台**当前唯一缺失的消解范式**，建议落 `rate_record.allocation_weight`；④ **但 Oracle 自己没做通用引擎**——定价 / 成本 / 碳分属 **三套独立应用与三套结果结构**（`Charge` / `Cost Component` / `Environmental Ledger`），碳甚至**建在 EPM Planning 引擎上** → **正面印证 D7 / N9 的边界**（只做"因子→率→逐层累加→结果"这一层），同时也说明**平台统一结果对象（一张 `pricing_result` + 一张 `pricing_step` 承载三域）是相对 Oracle 的真实增量**。

18. **★ Palantir 提供了"第三条通用化路径"，且它明确不做定价引擎**（v2.1 新增，§4.10）：① **没有产品化定价引擎**【确定】——化工"集成定价"用例里，**定价计算在 Microsoft Dynamics 侧**，Palantir 只做"上下文汇聚 + Quiver 决策 + Webhook 写回"；零售用例官方措辞是"**建议**最优价，**让人可以**改价"；成本侧官方措辞始终是 **model / workflow / optimization**，不是 engine；② 它走的是**与六家完全不同的路径**——**"通用对象图（Object / Property / Link / Interface）+ 行为附着（Action Type / Function）"**，而非"元模型 + 参数化"；③ **两条路径的真正分野不在能力，在"谁承担域特有逻辑"**——六家沉进元模型换开箱即用，Palantir 拒绝沉下去换跨域零妥协 → **我们走路径①，就必须自己扛域特有逻辑，因此 N9 的边界不是保守，而是这条路径的必要成本**；④ **它的 Action Type 与我们的"过程 + 结果 + 调整"高度同构**（参数 + 12 类规则 + 提交条件 + 校验 + 副作用 + 一次事务 + writeback dataset），**逐项对得上**；⑤ 两条可直接落地的观察——**我们的 `field_catalog` 比它的 Property 多一层 `source_type` 是合理增量**（它没有"按计量结果重算"的诉求），**但它有 Interface（能力多态）与 Validation（谁能改价）而我们缺**（后者建议本期只补"改价必填原因"）。

---

## 2. 现状取证：平台确实没有定价引擎

### 2.1 代码级证据

| 检查项 | 方法 | 结果 |
|---|---|---|
| 是否存在定价引擎文件 | `meta/core/*engine*.py` 枚举 | **不存在**。现有 13 个：workflow / doc_flow_derive / doc_flow_batch / association / key_template / index_rule / enrichment / deep_mutation / deep_insert / constraint / bo / async_interceptor / analytical |
| 全仓是否有 `*pricing*` 文件 | 文件名检索 | **0 个** |
| 是否有"价目表/条件类型/存取顺序/定价过程"资产 | 全仓内容检索 | **无**。命中的只有：① 测试夹具里的字段名 `price_list`（`meta/tests/test_default_rule_unit.py` L41-42 等）；② 研究/计划文档里对定价的**讨论**，非实现 |
| 现有"价格"相关能力 | 字段级 | 仅有普通字段：`discount_rate`（`meta/schemas/examples/sales_order_enhanced.yaml` L178-183）、`total_amount`（L242-245）、`unit_price`（明细，L319），即"**有放价格的格子，没有算价格的机器**" |

> **关键辨析**：`price_list`（价目表）字段虽然是测试夹具，但它恰好说明平台现有能力的天花板——`MetaDefaultRule` 可以按"客户 + 订单类型"**确定用哪张价目表**（`price_list = PL_ZOR`），但**没有任何东西能把这张价目表算成一个价格**。这正是"属性确定"与"定价"的分界线（§5）。

### 2.2 上位文档已判定该缺口

[规则模型研究](2026-10-02-rule-model-research.md) 中已有三处明确判定：

- §10.2 结果类型分族表末行：**`金额 · 多层` → 定价 Pricing → ❌（同族里最复杂，宜独立引擎）**。
- §10.4 专节《定价：同族里最复杂的一类（建议独立引擎）》，列出四条复杂性：**多层累加 / 互斥 vs 累加 / 冲突取优 / 值类型多样**，结论「**不该用属性确定规则表凑合**」。
- §10.6 覆盖清单第 9 项「定价」= **❌ 缺口（同族·宜独立引擎）**。

本报告是在此判定基础上的**深化**：补齐头部对标、概念模型、复用边界与建设路径。

---

## 3. 头部产品对标矩阵

### 3.1 逐家要点

#### 3.1.1 SAP 条件技术（Condition Technique）【确定】

**五构件**（即上位文档 §3.1 的五件，本处补事务码与定价专属属性）：

| 构件 | 事务码 | 作用 |
|---|---|---|
| 条件表 Condition Table | V/03 | 用哪些因子做键（客户+物料+订单类型+数量…） |
| 存取顺序 Access Sequence | V/07 | 按什么优先次序去查条件表 |
| 条件类型 Condition Type | V/06 | 这个槽位是什么语义（价格 / 折扣或附加费 / 税） |
| 条件记录 Condition Record | VK11 | 具体取值（键 + 值 + 有效期 + 阶梯） |
| 定价过程 Procedure | V/08 | 用哪些条件类型、什么次序、怎么算 |

**定价专属属性**（本报告新增，上位文档未展开）：
- **计算类型 Calculation Type**：百分比（A）/ 定额（B）/ 数量（C）——决定"这个值怎么作用到金额上"。
- **条件类 Condition Class**：价格 / 折扣或附加费 / 税——决定"落在瀑布的哪一层"。
- **Plus/Minus**：加项还是减项。
- **阶梯 Scale**：按数量/金额分档取值。
- **组条件 Group Condition**：多行共享一个条件基准。
- **舍入规则 Rounding Rule**、**排斥组 Exclusion Group**。
- **存取顺序的 Exclusive 标志**【确定】：勾选则**首个命中即停**（独占）；不勾则**继续向后查**（累加语义）——这是"同一台机器同时支持 exclusive / additive"的开关。
- **Requirement 例程**：返回未满足则**跳过该条件**（否决）。
- **Condition Exclusion**（OV31/OV32）：按"只保留较高价"排除其余折扣——**互斥机制**。
- **Condition Update**：条件记录跨单据**累计已用量**（如年度合同量用满即失效）。
- **定价过程的计算步骤字段**：【确定】From/To Step、Requirement、AltCTyp（替代条件类型）、Alt 计算基准、Subtotal（小计）、Print——**一条"可配置的计算序列"**。
- **扩展点 VOFM**：Requirement / Formula（Value / Rate / Base Value / Scale Base Value）等例程，承担复杂定制。

> **借鉴点**：SAP 证明定价不是"一条规则给一个数"，而是**一台通用确定引擎 + 一张可配置的计算序列**；且同一台机器被复用于伙伴/批次/输出/文本确定——**框架化胜过硬编码**。

#### 3.1.2 Oracle Fusion Cloud Pricing（含 EBS 对照）【确定】

**A. Oracle EBS Advanced Pricing（历史形态，逻辑仍是 Fusion 的底子）**

- **两组核心对象**：**Price List**（价目表）+ **Modifier List / Modifier**（修饰列表/修饰，承载折扣、附加费、运费、赠品、优惠券）。
- **资格 Qualifier**：分**列表级（list level）**与**行级（line level）**，决定"谁有资格命中此行"（客户类别、订单类型、产品、产品组、定价属性）。
- **调整方式（adjustment method）四种**【确定】：`Percent`（按单位百分比）/ `Amount`（按单位定额）/ `Lumpsum`（整行一笔）/ `New price`（直接改写售价，按"列表价与新售价的差额"记调整）。
- **修饰控制特征**：**Exclusive（排他）**、**级联 cascading**、**Incompatibility（不兼容）**、**Phase / Event / Bucket**（Bucket = 用子总计实现级联折扣）。
- **冲突消解（重要，修正原稿口径）**【确定】：阶段设 `incompatibility resolution method`——= **precedence** 时先选**最具体**的修饰，若**同优先级**则**回退 best price**；= **best price** 时找**折扣最大**者，若仍并列再按次要规则。即二者是 **"主 + 兜底"关系**，不是纯二选一。
- **引擎架构**【确定】：**Search Engine（按资格/生效期/不兼容/排他/优先级筛候选行）+ Calculation Engine（算调整效果）**；调用方传 **pricing request structure**（单行或多行），引擎回结果集。
- **Pricing Engine Request Viewer**【确定】：回放一次取数，显示**被选中的、被删除的价目行及删除原因**。

**B. Oracle Fusion Cloud Pricing（现役；比 EBS 更"框架化"）**

Fusion 把定价重构成 **"运行时对象链 + 三件可配置件 + 一台可改算法"**。

**B1. 运行时对象链（谁决定"用哪套定价"）**【确定】

```
调用方(OM) → Service Mapping → Pricing Profile → Pricing Segment
   → Strategy Assignment → Pricing Strategy → Lists(价/折/成本/币/运费)
   → Pricing Algorithm 逐步骤算 → Charge + ChargeComponent → 回写 OM
```

- **Pricing Profile**：把"客户的采购行为属性"（Size 规模 / Rating 评级 / Cost to Serve 服务成本…）**描述到每个客户**。
- **Pricing Segment**：按属性把客户**分组**（如 Tier 1 = Large + High + Medium）；引擎**逐属性比对**直到命中段。
- **Strategy Assignment**：按"**段 + 交易类型 + 渠道**"**指派策略**（Tier 1 + 销售订单 + 直销 → Commercial）。
- **Pricing Strategy**：引用各 **List** 上的规则；**五类 List**【确定】——**Price / Discount / Cost / Currency Conversion / Shipping Charge**（价目表、折扣表、成本表、币种换算表、运费表）。
- **Sales Transaction Type / Pricing Process Assignment**：决定用哪个**算法**。

**B2. 三件可配置件（改配置不改代码）**【确定】

| 构件 | 作用 | 平台对照 |
|---|---|---|
| **Service Mapping** | 定义"**调用方输入字段 ↔ 定价内部实体/属性**"的映射，并可**自定义属性**（官方示例加 `TermName_Custom`）；定义输出 SDO 结构（Header / Order Line / Charge / ChargeComponent）| ≈ 我们的**字段目录**（哪些字段可入条件）|
| **Pricing Matrix** | **条件维度（condition dimensions）→ 结果列（result columns）**，字段受 **Matrix Class** 约束；用**运行时值**比对**建规则时的值** | ≈ SAP **条件表 + 存取顺序** 合一 |
| **Pricing Algorithm** | **有序步骤序列**，每步**有条件地更新内存中的输出 SDO**；预置 `Price Sales Transaction`（主算法，逐行定价）+ `Calculate Sales Order Totals`（算总额）| ≈ SAP **定价过程 V/08** |

**B3. 一次定价的逐步算例**【确定】（官方示例 AS54888）

| 步骤 | 动作 | 结果 |
|---|---|---|
| 1 | 基价（Corporate 价目表）| Base List Price = **$1,000** |
| 2 | **Tier Adjustment**（按量/按额）| −$200 |
| 3 | **List Price** | **$800** |
| 4 | **Discount**（折扣表 10%）| −$100 |
| 5 | **Net Price** | **$700** |
| 6 | Extended Amount | $700 × 2 = **$1,400** |
| 7 | 调 Oracle Tax 算税 → 生成**税 ChargeComponent** | — |
| 8 | 按 Cost List（成本表）算利润边际 | — |

- **运行时重算触发点**【确定】：设客户 / 加行 / 改数量或 UoM / 手工改价 / 改运费属性 / `Reprice Order` / `Submit`——**每次整单全量重算**（逐行定价 + 算总额）。
- **输出粒度**【确定】：一个物料可有**多个 Charge**（如 `Sale Price Charge`），每个 Charge 带**多个 ChargeComponent**（每一步的分解）→ **这本身就是"定价明细/可回放"的现成数据形态**。

**B4. 调整类型与两种阶梯**【确定】

- **五种调整类型**：`Discount Amount` / `Discount Percent` / `Markup Amount` / `Markup Percent` / `Price Override`。
- **Tier Pricing（按量或按额分档）vs Pricing Matrix（按属性）**；两类调整**可挂的清单不同**（价格表两者皆可；成本表仅阶梯；币种换算表 / 运费表仅矩阵）。

**B5. ★ 基准：cascading vs cumulative（本次深挖最关键的一条）**【确定】

Oracle 明确给出**两种折扣叠加语义**，**都按"规则名升序（alphabetic ascending）"执行**，**差别只在基准量**：

| 语义 | 基准量 | 效果 |
|---|---|---|
| **Cumulative（累积）** | **List Price（固定基准）** | 每条规则都基于**同一个** List Price 算折扣并**累加**总额；List Price **不被修改** → 折扣**不滚动** |
| **Cascading（级联）** | **Running Net Price（滚动基准）** | 每条规则基于**上一步算完的 running net price** 算折扣，**逐条递减** running net price → 基准**滚动**，等效**复利式叠加** |

- 为此 Fusion 把"基准"做成**一等配置对象**：新建 **Price Element（Type = Price，如 Running Net Price）+ Pricing Basis（Usage = Adjustment Basis）**，再挂到服务映射上。→ **"基准"不是公式里的隐变量，而是一张可维护的配置**。
- **"累积 vs 级联"是同一台引擎的开关**——正如 SAP 用 `From/To` 切基准步骤、D365 用 `find next` 切取数范式。

> **借鉴点（升级）**：① **把"基准"提升为一等配置对象**（我们的 `base` 应显式建模为 `base_level / base_basis / base_step / base_roll`，而非隐含在公式里）；② **"基准量是否滚动"（cascading vs cumulative）必须可配**——原稿 §4.3 只讲了"基准量可被公式改写"，本稿补上"**基准可滚动**"这一维；③ **算法步骤更新内存对象 + 输出 Charge/ChargeComponent** 是"可解释回放"的最干净落法；④ **同一引擎用开关支持两种叠加语义**，不必造两套。

#### 3.1.3 Salesforce：Industries CPQ → Revenue Cloud Advanced【确定（架构）/ 基本确定（细节）】

Salesforce 有**两代并存**的定价实现：老 **Salesforce CPQ**（已 **end-of-sale**，非 end-of-life：继续支持、可续订，但不再向新客户售卖）与 **Revenue Cloud Advanced（RCA，2024 年末起，CPQ 的官方继任者）**。RCA 把定价重构为**声明式 Pricing Procedure**。

**A. 基础对象（两代共用）**

- **Product / Price Book / Price Book Entry**：PBE = 某产品在某价目表下的**基价（list price）**。价目表的选择仍是报价的前提（Quote 由某 Price Book 下的产品生成）。
- **Product Selling Model**【确定】：一次性 / 月 / 年…… **一个产品可按不同售卖模型拥有多条 PBE**（订阅定价的关键扩展）。
- **Catalog + Category**：产品目录 / 分类，负责"发现"，与定价解耦。

**B. Revenue Cloud 的 Pricing Procedure = ExpressionSet 的扩展**【确定】

RCA 的定价过程沿袭 **Salesforce Industries** 的决策引擎：**Lookup Table**（**Decision Table / Decision Matrix**，可**引用 SF 对象**、需**刷新**）+ **Expression Set**（用**可插拔 Elements** 编排业务过程）。**Pricing Procedure 就是"带标准价格元素的 Expression Set"**。

**B1. 标准 Element 20 个 = 15 个价格元素 + 5 个控制元素**【确定】

| # | Element | 作用 |
|---|---|---|
| 1 | **List Price** | 读 Price Book Entry 决策表（输入：产品 + 价目表 + 售卖模型）→ list price |
| 2 | **Volume Discount** | 按**数量区间整单取值**（Price Adjustment Tier），调整/覆盖当前价 |
| 3 | **Tier Discount** | **逐档分别打折**（与 Volume 的差别 = §4.3⑤ D365"整单取档 vs 逐档累进"同款）|
| 4 | **Attribute-Based Price** | 按**产品属性**调/覆盖价（ABP）|
| 5 | **Bundle-Based Price** | 按**组合（bundle）**配置的折扣定价 |
| 6 | **Formula Based Pricing** | 内联**公式/函数**算价 |
| 7 | **Manual Discount** | 应用报价行上**手工录入**的折扣额/折扣率 |
| 8 | **Subscription Pricing** | 输入价 × 期数（年/月）算订阅总价 |
| 9 | **Proration** | 配 Subscription 用，按**期内已用时长**算比例乘数（可配"部分月是否按整月"）|
| 10 | **Price Adjustment Matrix** | 按**自定义决策表/对象**调/覆盖价 |
| 11 | **★ Derived Price** | **从另一来源派生价**（另一产品行 / 表头级总额计算）|
| 12 | **★ Price Tracking** | **取并保存产品最低/最高价**（Product Price Range Entries）|
| 13 | **Rounding Values** | 应用**取整规则** |
| 14 | **★ Aggregate Price** | 用 **SUM/AVG/MAX/MIN** 聚合**一组产品**的价 |
| 15 | **★ Discount Distribution Service** | 控制折扣**跨行分摊**（头级折扣摊到各产品行；带**地板价限制** + **分摊规则决策表**；支持**等分 / 按行值比例**两种摊法）|
| 16–20 | **（控制类，5 个）List Operation / List Group / Map Line Item / Assignment / Price Setting** | 控制**数据引用与分组**（非价格计算）|

> **计数说明（v1.4 修正）**：标准定价过程共 **20 个 Element**——**15 个价格元素**（第 1–15 行）+ **5 个控制元素**（第 16–20 行）。此前稿件的"16 个 / 12+4"计数有误，本次按 revenuecloud.info《Architecture》原始清单重核（§9 S28/S30）。
>
> 另：**Contract Pricing**（按客户合同定价）不是独立元素，而是上述多个价格元素上的一个**复选开关**，由 **List Operation** 元素筛出受合同约束的定价行。

**B2. 三个外围构造**【确定】

- **Context**：把元素里用的 **tag** 映射到**对象字段**（"这次定价能取到哪些数据"）——≈ 我们的**字段目录 / 因子上下文**。
- **Pricing Recipe**：声明**哪些决策表需要批量刷新**——因为**决策表把 SF 对象数据物化了**，改了源对象必须刷新。
- **Sales Transaction Type**：决定**哪个报价/订单用哪个 Pricing Procedure**——≈ SAP 的"定价过程确定"。

**B3. 瀑布（两代各一套）**

- **RCA**：按 **Configure → Rate → Discount → Net** 依次计算；API 返回 **price waterfall 明细**（含 pricing / context / waterfall 三段，可 headless 调用）。
- **CPQ 价格点【确定】**：**Original → List → Special → Regular → Customer → Partner（+ Distributor）→ Net**，每一档都有 unit / total；**顺序可被特殊字段改写**：`ChannelDiscountsOffList__c`（渠道折扣基于 List）、`ApplyPartnerDiscountFirst__c`（伙伴折扣提前）、`ApplyAdditionalDiscountLast__c`（额外折扣最后）。
  - 注意：不同家教程的分档名次序略有出入（Special 与 Regular 谁先），但 **"多档级联、每档可被改序"** 这一骨架一致【基本确定】。
- **老 Industries CPQ**：条目由 **pricing variable**（一次性/周期、override 或 adjustment、金额或百分比）+ **pricing element**（Charge / Adjustment / Override）组成；Promotion/Discount 由 Pricing Plan **步骤 35「Apply Context Discounts」**应用。

> **借鉴点（升级）**：① **每个定价能力都是一个"可插拔 Element"，且 Element 有类型**——我们的"定价过程步骤"应做成**带 `element_type` 的算子列表**（`list_price / tier / attribute / formula / manual / derived / aggregate / distribute / round / track`），而不是硬编码 if-else；② **Derived Price / Aggregate / Discount Distribution / Price Tracking 都是一等元素**——说明**"派生价、过程内汇总、过程内分摊、最低最高价"本就在定价引擎内**；其中 **DDS 尤其关键**：它把**头级折扣分摊到各产品行**（守恒），却仍是**定价过程内的一个标准步骤**——证明 §5.2 的判据须改为"**是否作为定价过程的一步**"，而非"是否守恒"（见 §4.4 启示 4）；③ **Context 独立建模** = 我们的字段目录；④ **决策表物化需配套刷新（Pricing Recipe）**——平台若走"条件表达式直查价目行"，则**天然免刷新**，不必复刻 Matrix / Recipe。

#### 3.1.4 Microsoft Dynamics 365【确定】

- **Trade Agreement**（销售价/折扣）优先级高于 item base price；价格用 **price component 序列**构建（10=基价，20/25/30=加价组件），售价 = 基价 ± 组件调整。
- **冲突消解**【确定】：`Enable default find next` = **Yes** → 检查所有适用贸易协议价并**取最低价（best price）**；= **No** → 按 **price attribute combination rank** 判定（最高排名者胜，平级再比表头属性/价格组）。
- 零售侧**定价优先级**：**数值大者先评估，命中即忽略更低优先级**（可覆盖 best price）。
- **净价 Net pricing**：`Allow Price Adjustment = No` + `Prevent Discount = Yes` → 生成**排他净价**，不再参与任何折扣。

> **借鉴点**：同一家产品**同时**提供 best-price 与 rank-first 两种范式，且用"是否继续找下一个"这根开关切换——与我们"exclusive 标志"的思路一致。

#### 3.1.5 Odoo（轻量参照）【确定】

- **Pricelist + Pricelist Rules**；计算方式 **Fixed Price / Discount / Formula**；Formula 需指定基数（Sales Price / Cost / Other Pricelist），可选百分比折扣/加价、额外固定费（Extra Fee）、舍入、利润上下限。
- 适用对象：全部 / 类别 / 产品 / 变体；条件含 **Min Quantity 与有效期**。
- **取数语义**：多条价目表共享同一条件时**只取列表中第一个**；同为规则时**产品级优先于类别级**（首个命中）。

> **借鉴点**：**轻量但完整覆盖"价目表 + 规则 + 条件 + 公式 + 阶梯"**——证明独立定价引擎不必一开始就做全套 SAP，可小步起步。

#### 3.1.6 金蝶（云·星空 / 旗舰版）【确定（取价/限价）；促销 基本确定】

- 价目表按"**价格类型**"定价；价格类型配"**取价优先级**"（数值越小优先级越高）；启用"优先级取价"后按 1→2→3 逐表取价，**命中即止**；未设优先级时取**创建日期最新**者；仅"**审核**"状态价目表参与取价。
- 支持**按销量阶梯**、按辅助属性定价。
- **最低限价**：控制强度分 不予控制 / 预警 / 禁止交易 / 密码特批，按**净价**校验。
- **可回放**：简易取价提供 取价策略 / 取价方案 / 取价日志，单据上有"**查看定价过程**"按钮。

- **★ 计算策略（v1.9 复证）**：**旗舰版 / 星瀚**另有"取价方案 → 计算策略 → 取价策略"三段——**计算策略把"基础价 / 变式价 / 区域价差"等设为计算因子，用公式组合成取价结果**，并进入 **"查看定价过程 / 取价日志"可回放**（金蝶官方实践案例【基本确定】）→ **属"定价过程内"的公式化因子聚合层**，非 SAP 式多步条件序列；**星空标准版无此能力**（仅为"价目表 + 优先级取价"）。

> **借鉴点**：国产主流 ERP 的实现是"**价格类型 + 优先级 + 命中即止**"，属 **exclusive 范式**；促销以独立"促销价格类型"接入优先级，**未发现独立促销引擎**；**旗舰版 / 星瀚另以"计算策略"做过程内公式化因子聚合**（可回放，见上 ★）。**最低限价 = 定价之后的校验**（属 validation，不属定价引擎）。

### 3.2 对标汇总表

| 抽象概念 | SAP | Oracle (EBS/Fusion) | Salesforce | D365 | Odoo | 金蝶 | **平台可复用资产** |
|---|---|---|---|---|---|---|---|
| **价目表** | 条件记录 + 条件表 | Price List / PBE | Price Book / Entry | Trade Agreement | Pricelist | 价目表 | ❌ 无（须新建） |
| **条件/适用规则** | 条件类型 + 条件表键 | Qualifier / Modifier + **Pricing Matrix** | Price Rule / ABP / **Decision Table** | Price component 条件 | Pricelist Rule 条件 | 价格类型 | 🔵 `condition_parser` 条件内核 |
| **存取序列/优先级** | Access Sequence + Exclusive 标志 | Context Precedence + **规则名升序** | Procedure 步骤顺序 | attribute rank / retail 优先级 | 规则顺序 | 取价优先级 | 🔵 `priority` + tie-break |
| **计算序列（过程）** | 定价过程 V/08（Step/Subtotal） | **Pricing Algorithm**（有序步骤；Service Mapping 管输入建模 / Pricing Matrix 管条件） | **Pricing Procedure = ExpressionSet + 15 价格元素 + 5 控制元素** | price component 序列 | Formula | 取价方案 | ❌ 无（`compute` 太薄）；**步骤须带 element_type** |
| **取数范式** | exclusive / additive（开关） | Precedence（**主**）+ Best Price（**兜底**） | Waterfall 顺序（可改序） | find-next / rank | 首个命中 | 命中即止 | 🔵 首个命中已具备；**累加/取优缺** |
| **阶梯** | Scale | **Tier Pricing（按量/按额）** | **Volume（整单取档）/ Tier（逐档累进）** | — | Min Quantity | 按销量 | ❌ 无 |
| **互斥** | Exclusive 标志 / 排斥组 | Exclusive / Incompatible | 改序特殊字段 | Prevent Discount | — | — | ❌ 无 |
| **★ 基准（一等对象）** | 公式 From/To | **Price Element + Pricing Basis（Usage=Adjustment Basis）+ Running Net Price** | Context tag（隐式） | — | 基数（售价/成本/其他价目表） | 打折依据（零售价/批发价） | ❌ 无（应显式建模 `base_*`） |
| **★ 过程内派生/汇总/分摊** | Group Condition + 小计 | Totaling & Rollups + Spread Discount | **Derived / Aggregate / Discount Distribution（DDS 把头级折扣摊到行，仍是过程内一步）** | — | — | 计算策略（**公式化因子聚合**，纳入取价过程、可回放 → **属过程内**，v1.9 核定；仅旗舰版 / 星瀚） | ❌ 无 |
| **★ 最低/最高价** | — | — | **Price Tracking（过程内取/存）** | — | 利润上下限 | 最低限价（**过程后校验**） | 🔵 `validation` 可承接"拦" |
| **可解释回放** | 条件分析 | **Request Viewer + ChargeComponent** | **Price Waterfall（API 明细）** | — | — | 查看定价过程/取价日志 | ❌ 无（仅规则判定日志雏形） |
| **扩展点** | VOFM 例程 | 改 Service Mapping / Algorithm / Matrix | 自定义 Element + Price Adjustment Matrix | 定价组件 | Formula | 取价方案 | 🔵 `ActionType.BUSINESS` hook |

---

## 4. 概念模型：定价引擎的六个必备件

把上表横着读，六家反复出现的机制可收敛为**六个必备件**。这也是本报告建议平台对齐的概念骨架：

| # | 构件 | 回答的问题 | 形态 | 对标 |
|---|---|---|---|---|
| **① 价目表 Price List** | 价格的"库存"放哪 | 表 + 行（价目行：键 + 值 + 有效期 + 币种 + 阶梯） | SAP 条件记录 / Oracle Price List / SF Price Book |
| **② 条件类型 Condition Type** | 这个槽位是什么语义、值怎么作用 | 枚举 + 属性（类=价格/折扣/附加费/税/运费；计算类型=百分比/定额/数量/公式；±；舍入） | SAP 条件类型 / SF pricing element |
| **③ 存取序列 Access Sequence** | 按什么优先次序找价目行；找到几条 | 有序查表列表 + **每条一个 Exclusive 开关**（首个命中 vs 继续累加） | SAP Access Sequence / D365 find-next |
| **④ 定价过程 Pricing Procedure** | 用哪些条件类型、什么次序、怎么算 | **可配置的计算序列**（Step 序列 + 小计 + 基准） | SAP V/08 / SF Recipe / Oracle Algorithm |
| **⑤ 取优与消解 Best/Precedence** | 多条同类命中，选哪个 | **显式选范式**：Precedence（优先级）/ Best Price（取最优）；+ 排斥组 | Oracle Precedence vs Best Price / D365 rank |
| **⑥ 可解释回放 Explain** | 为什么是這個值 | 定价明细：命中了哪行、被谁否决、逐层小计 | Oracle Request Viewer / 金蝶 取价日志 |

> **一句话**：**①②③④ 决定"算什么"，⑤ 决定"多命中怎么收"，⑥ 决定"算完能不能解释"**。少任何一个都不算定价引擎——尤其 ⑤ 和 ⑥，是它区别于普通计算公式的本质。

### 4.1 条件类型：枚举还是配置对象？（二期深化）

**结论：是"配置对象"，不是硬编码枚举。** 六家**无一家**把条件类型写死；它们只把"**值怎么作用**"抽象成一个**属性枚举**（计算类型）。

| 产品 | 条件类型可否自定义 | "值怎么作用"的枚举 | 条件类型上可配的属性 |
|---|---|---|---|
| **SAP SD（V/06）** | **可自建**（复制相似类型再改）【确定】 | 计算类型：A 百分比 / B 定额 / C 数量 / D 重量 | 条件类（价格/折扣附加费/税）、±、舍入规则、排斥组、手动/必填/统计/打印、条件更新、组条件、存取顺序、Requirement 例程、AltCTyp、Alt 计算基准 |
| **SAP MM（M/06）** | **可自建**【确定】 | 同上 | Condition class（Prices/Discount-Surcharge/Taxes）、Calculation type（A/B/C）、+/- |
| **Oracle EBS Pricing** | **可自建**修饰【确定】 | 调整方式：Percent / Amount / Lumpsum / New price | Qualifier（资格条件）、Exclusive、cascading、Incompatibility |
| **Salesforce** | 用 `pricing element`（Charge/Adjustment/Override）组合【基本确定】 | pricing variable：金额 / 百分比；Override / Adjustment；一次性 / 周期 | 组合成 Charge / Adjustment / Override，挂到 Recipe 序列 |
| **D365** | **可自建** price component（10 基价；20/25/30 加价）【确定】 | 组件类型（基价 / 加价 / 折扣） | 组件序号构成可扩展序列 |
| **Odoo** | **可自建** Pricelist Rule【确定】 | 计算方式：Fixed Price / Discount / Formula | 基数（售价/成本/其他价目表）、百分比、Extra Fee、舍入、上下限 |
| **金蝶** | **可自建**价格类型【确定】 | 折扣 / 折扣率 / 折扣额；打折依据（零售价/批发价） | 取价优先级、按销量阶梯、按辅助属性 |

> **设计含义**：件②（§4）在平台上应落成一张**可维护的元模型对象**，字段至少含：`编码 / 名称 / 条件类（价格·折扣附加费·税·运费·统计）/ 计算类型（百分比·定额·数量·公式）/ 正负号 / 舍入规则 / 排斥组 / 是否手动可录入 / 是否必填 / 是否统计 / 存取顺序引用`。
>
> **与 D7 "通用确定"一致**：条件类 / 计算类型是**枚举属性**，条件类型是**配置数据**——这样"伙伴确定/批次确定"复用同表时，只需新增条件类枚举值，不改表结构。

### 4.2 定价的主数据与配置对象全景（分层清单）（二期深化）

定价**不是**只依赖 §4 的"六个必备件"。把六家横着读，依赖对象可分**四层**：

**第 1 层 · 引擎配置对象（元模型，非主数据）**

| 对象 | 回答什么 | 对标 |
|---|---|---|
| 字段目录 Field Catalog | 哪些字段可当条件的键 | SAP 字段目录（KOMG/KOMP 允许字段）|
| **条件表 Condition Table** | **用哪些因子的组合做键**（客户+物料+订单类型+数量…） | SAP V/03（SD）/ M/03（MM）|
| 存取顺序 Access Sequence | 按什么优先次序查条件表、查到几条 | SAP V/07 / M/07 |
| **条件类型 Condition Type** | 这个槽位是什么语义、值怎么作用 | SAP V/06 / M/06（见 §4.1）|
| 定价过程 Procedure | 用哪些条件类型、什么次序、怎么算 | SAP V/08 / M/08 |
| 排斥组 / 条件类型组 | 哪几个互斥 | SAP Exclusion Group / Condition Type Group |
| 条件更新组 | 哪些条件记录跨单累计用量 | SAP Condition Update |
| Requirement / Formula 例程 | 复杂定制的逃生门 | SAP VOFM |

**第 2 层 · 价目行（事务性主数据 = 条件记录）**

| 对象 | 关键属性 |
|---|---|
| 价目表 Price List | 名称 / 类型 / 币种 / 状态（**仅审核态参与取价**，金蝶）|
| **价目行 Condition Record** | 键（来自条件表）+ 值 + **有效期** + **币种** + **定价单位/定价数量** + **阶梯** + 状态 |
| 条件补充 Condition Supplement | 依附某条件记录的补充条款 |
| 累计值 Cumulative Values | 跨单据累计已用量（合同量用满失效）|

**第 3 层 · 被引用的通用主数据（= 条件表键的字段来源）**

| 域 | 具体字段 / 对象 | 用途 |
|---|---|---|
| 客户 | **客户定价过程**、**客户价格组**、价格清单类型、税分类 | 决定用哪套定价过程 / 折扣组 / 价目表 |
| 物料 | **物料价格组**、**物料税分类**、**参考物料**（price material）、物料组 | 折扣按物料组；参考物料复用条件记录 |
| 组织 | **销售区域**（销售组织 + 分销渠道 + 产品组）、工厂、装运点 | 定位条件表键、定价过程确定（OVKK）|
| 单位 | UoM + **单位换算** | 定价数量与库存数量的换算 |
| 货币 | 币种 + **汇率** | 价目行币种 ≠ 单据币种时换算 |
| 税务 | 税码 / 税率 / 税分类 | 税条件类型的取值 |
| 日历 | 有效期 / 生效日历 | 条件记录按时效过滤 |

**第 4 层 · 相邻校验对象（不属引擎，但定价结果被其约束）**

最低/最高限价（按**净价**校验，金蝶）、折扣基础（零售价/批发价，金蝶）、免税判定。

**平台现状取证（对照）**

| 依赖对象 | 平台现状 | 证据 |
|---|---|---|
| UoM | ✅ 已有 | [uom.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/uom.yaml) |
| 单位换算 | ✅ 已有 | [item_uom_conversion.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/item_uom_conversion.yaml) |
| 物料组（树） | ✅ 已有 | [item_group.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/item_group.yaml) |
| 物料 / 伙伴 / 组织 | ✅ 已有 | `items.yaml` / `party.yaml` / `org.yaml` |
| **币种** | ⚠️ **仅枚举引用**，无主数据表 | `sales_order_enhanced.yaml` L258-264（`currency_code` → `enum_type_id: currency`）|
| **汇率** | ❌ 无 | 全 `meta/schemas` 无 `exchange_rate` |
| **税码 / 税率 / 税分类** | ❌ 无 | 全 `meta/schemas` 无 `tax_*` |
| **客户价格组 / 客户定价过程** | ❌ 无 | `party.yaml` 无价格相关字段 |
| **物料价格组 / 税分类 / 参考物料** | ❌ 无 | `items.yaml` 无价格相关字段 |
| 销售区域（分销渠道/产品组细分）| ⚠️ **部分具备**：`org_functions.function_type` 含 **`sales`**（销售组织职能），**渠道 / 产品组两段无**（★ v1.9 复证）| `org.yaml`（`org_type` / `org_scope` / `parent_id` 树）+ `org_functions`（12 职能白名单，含 `sales`）|
| 条件表 / 字段目录 / 存取顺序 / 定价过程 | ❌ 无 | 见 §2.1（无定价资产）|

> **含义**：即使引擎骨架造好，**第 1、2、3 层里有大量对象要先补齐**（尤其**币种主数据、汇率、税、客户/物料价格组**）。这些**不是定价引擎的一部分**，而是它**依赖的通用主数据**——应优先在 foundation 层补齐，定价引擎只做"引用 + 计算"。

### 4.3 计算基准与输入：算在表头还是行？（二期深化）

**先拆概念**："基准"（base）在定价里有**三个不同含义 + 一个模式开关**，常被混为一谈：

| # | 基准的维度 | 问的是 | 典型取值 |
|---|---|---|---|
| A | **基准层级 base level** | 算在**表头**还是**明细行** | Item（行）/ Header（头）|
| B | **基准量 base basis**（`base_basis`） | 拿**什么量**去乘费率 | 数量（定价数量）/ 价值 / 重量 / 其他（可配公式 `base_formula`）|
| C | **基准步骤 base step** | 百分比/折扣**基于哪个前序步骤**的中间结果 | From/To 步骤号（如"步骤 10 之后"）|
| D | **是否滚动 base roll**（v1.4 补） | 基准是**固定在某个前序步骤**，还是**跟随"当前滚动净价"** | 不滚动（固定步骤）/ 滚动（Running Net Price）|

> **D 与 C 互斥**：选了"滚动"，基准就是**持续更新的单一净价累加器**（Oracle Running Net Price），此时"基于哪个具体步骤"无意义，`base_step` 不填写。

**结论：默认"行级"计算，表头是可选补充；且基准量默认不是"数量"本身，而是"定价数量"，并可被公式改写；是否滚动另由开关控制。**

**① 层级：行 vs 头（SAP 为准）**【确定】

- **Item Condition（行条件）**：只作用于该行，**大多数条件类型都是行条件**（如物料折扣 K004、客户/物料 K005、客户折扣 K007、物料价 PR01）。→ **取价是逐行进行的**。
- **Header Condition（表头条件）**：作用于**所有行**；订单层**只算一次**，再向下作用：
  - **挂 Group Condition**：按**行价值比例分摊到各行**（如运费按各行净价摊）；
  - **不挂 Group Condition**：**全额作用到每一行**（示例：表头折扣）。
- 部分条件类型**两头都能配**（RA01 百分比折扣 / RB00 绝对折扣 / RD00 重量折扣）。
- **订单头字段**（如总净额）在定价后被写回；表头条件通常**人工录入**（标准系统不为表头条件建条件记录）。

**② 基准量：默认定价数量，可被 Condition Base Value 公式改写**【确定】

- SAP 标准：把条件费率作用在**销售单据里的数量**上（$45/case × 100 cases）。"**定价数量 Pricing Quantity**"与**定价单位**（如 USD/100 PC）决定这个乘数。
- **Condition Base Value 公式**：可改用其他基准（价值/重量/自定义）替代标准数量。
- **Scale Base 公式**：读阶梯前先改写用于查档的量。
- **单位换算**参与：订单单位 ≠ 定价单位时先换算（依赖 §4.2 第 3 层的 UoM 换算）。

**③ 基准步骤：From/To 级联**【确定】

- 定价过程每步有 `From / To`：**步骤 20 的百分比折扣若 From=10，则基于步骤 10 算出的毛价**。"From/To 配错"是最常见的定价配置错误。
- **小计 Subtotal**：把中间结果存入小计键（SAP `KZWI1..6`），供后续步骤/报表引用——**这是"基准级联"的落点**，也是可解释回放的骨架。

**④ 汇总方向与对标**

| 方向 | 机制 | 对标 |
|---|---|---|
| **行 → 头** | 汇总各行金额到订单头（净额、税额、运费）| SAP（税/运费/表头折扣 + Subtotal）、Oracle **Totaling and Rollups**、金蝶**计算策略（过程内公式化因子聚合，v1.9 核定属过程内；仅旗舰版 / 星瀚）** |
| **头 → 行** | 表头条件按行价值分摊（组条件）| SAP **Group Condition + 组条件例程**、Oracle **Spread Discount** |

**⑤ 其他家的"基准/瀑布"对照**

- **Oracle**：**Pricing Waterfall**——从 list price 起，依次叠加 volume discount / attribute pricing / aggregate discount / manual，**逐步记价**终得 net price，可回放每一步【确定】。
- **Salesforce CPQ**：**7 个价格点** Original → List → Special → Regular → Customer → Partner → Net，每点含 unit/total【确定】；调整挂在 **Price Rule** 上，作用对象可分**行/组合/表头**。
- **D365**：price component 序列（**10 = 基价**，20/25/30 = 加价）；阶梯有**两种语义**——**整单取档**（数量落入某档，取档内单一价）vs **逐档累进**（各档分别计价再求和）；还有"一定档金额"型【确定】。
- **金蝶**：报价单取到**含税价**时，按 `单位价 = 含税单价 ÷ (1 + 税率)` 折算；折扣依据可选零售价/批发价【确定】。

**⑥ 落到平台的设计建议**

1. **引擎调用粒度 = "一行 + 表头上下文"**：逐行调用，行对象携带所需表头字段（币种、客户、销售区域等），首期不做真表头条件。
2. **基准量默认 = 定价数量（qty × price unit）**，并预留 `base_formula`（价值/重量）——与件②的"计算类型=公式"共用 `SafeExpressionEvaluator`。
3. **保留 `From/To` 语义**（基准步骤级联）与**小计**——这是 P2"多层累加 + 回放"的必要条件。
4. **头条件 / 组条件分摊**列为 **P3+**，且**归定价**（它是 `element_type=distribute` 的一个步骤，对标 SF **Discount Distribution Service**、Oracle **Spread Discount**）——**不再归 allocation**；判据见 §4.4 启示 4、§5.2 修订行。
5. **落库**：价目行须带 `币种 / 定价单位 / 阶梯`；定价明细每步须记 **`base_level`（层级）+ `base_basis`（基准量来源：定价数量/价值/重量/公式）+ `base_step`（基准步骤）+ `base_roll`（是否滚动）**——四者齐备才可完整回放；**`base_roll=true` 时 `base_step` 不适用（二者互斥）**，`base_basis=公式` 时另记 `base_formula`。

### 4.4 三期深挖：Oracle Fusion 与 Salesforce 的引擎解构与直接启示

把 §3.1.2 / §3.1.3 深挖后的两台引擎并列，可看到**两条"框架化"路线**，但对平台的启示高度一致。

**① 两台引擎逐层对照**

| 维度 | Oracle Fusion | Salesforce（RCA） |
|---|---|---|
| **定"用哪套价"** | Profile → Segment → Strategy Assignment → Strategy | Sales Transaction Type → Pricing Procedure |
| **输入字段建模** | **Service Mapping**（输入 ↔ 实体/属性，可自定义属性） | **Context**（tag ↔ 对象字段） |
| **键 / 条件** | **Pricing Matrix**（维度→结果，Matrix Class 限字段） | **Decision Table / Matrix**（可引用 SF 对象，需刷新） |
| **计算序列** | **Pricing Algorithm**（有序步骤，逐步骤更新内存 SDO） | **Pricing Procedure**（ExpressionSet + **20 Elements** = 15 价格 + 5 控制） |
| **基价** | Price 表 | List Price Element → Price Book Entry |
| **叠加语义** | **cascading（滚动基准） vs cumulative（固定基准）**，按规则名升序 | 瀑布逐档级联，顺序可被特殊字段改写 |
| **基准** | **一等对象**：Price Element + **Pricing Basis（Usage=Adjustment Basis）** + Running Net Price | Context tag（隐式，无独立"基准"对象） |
| **结果形态** | **Charge + ChargeComponent**（每步一个 component） | **Price Waterfall**（每档 unit/total） |
| **可解释** | Request Viewer + ChargeComponent | Waterfall API 明细 |
| **最低 / 最高价** | — | **Price Tracking Element**（过程内取并存 min/max） |
| **过程内派生 / 汇总 / 分摊** | Totaling & Rollups、Spread Discount | **Derived Price / Aggregate Price / Discount Distribution Service** |
| **扩展点** | 改 Service Mapping / Algorithm / Matrix | 自定义 Element + Price Adjustment Matrix |
| **数据新鲜度** | 运行时直查定价实体 | 决策表**物化**，需 **Pricing Recipe** 批量刷新 |

**② 对平台的六条直接启示（含对原稿边界的修正）**

1. **计算序列 = "带类型的算子列表"**：两台引擎的步骤都是**具名、可插拔、有类型**的元素（不是硬编码分支）。→ 平台 §4 件④应落成 `procedure_step(seq, element_type, condition, params)`，`element_type` 至少覆盖 `list_price / tier / attribute / formula / manual / derived / aggregate / distribute / round / track`（★ v1.8 增 `quality_premium`，§4.8D⑤）。
2. **"基准"要显式建模为一等对象**（Oracle 的 Pricing Basis 是最强证据）：把 §4.3 的**四个维度**落成字段——`base_level`（层级）/ `base_basis`（基准量来源）/ `base_step`（From/To）/ **`base_roll`（是否滚动）**。
3. **★ 补一维："基准是否滚动"**（§4.3 原稿只讲"基准量可被公式改写"）：默认建议 **不滚动（cumulative，以基价/前序步骤为固定基准）**——更可解释、金额更可控；**滚动（cascade）须显式开启**，其基准是 Oracle 所谓 **Running Net Price——一个在计算过程中持续增减的单一净价累加器对象**（等价于"全部前序步骤累计后的当前净价"），开启时在明细里记 `running_net_price`。**该维与 `base_step` 互斥**（滚动时不指定具体前序步骤，见 §4.3 D 行）。理由：与 D2/D3"默认选可解释、危险项显式开"的取向一致。
4. **★ 修正 §5.2 第 4 条边界**——判据改为"**是否作为定价过程的一步**"，而**不是**"是否守恒 / 是否跨行"：
   - **作为定价过程内的一步**（行价派生、SUM/AVG 汇总、**头→行折扣分摊**——哪怕它守恒、哪怕它跨行）→ **属定价引擎**。证据：SF **Discount Distribution Service** 明确是标准 Pricing Procedure 里的一个 **Element**，功能正是把**头级折扣摊到各产品行**，还带**地板价限制 + 分摊规则决策表**；Oracle **Spread Discount**、SAP **组条件**同理。
   - **定价过程之外的独立分摊**（把已算好的成本/费用**跨单据、跨期间**搬运，无价格语义）→ **仍归 allocation**。
   → **修正要点**：v1.3 曾用"跨单据守恒"作判据，**不准确**——DDS 属于"**同一单据内、跨行、守恒**"，却仍在过程内；故判据只能是"**是否在过程内**"（见 §5.2 修订行、§8 D13）。
5. **最低 / 最高价的"算"与"拦"分家**：**取并记录 min/max 值**属定价（SF Price Tracking 有、Oracle 无）；**预警 / 禁止交易**属 `validation`（金蝶）。→ 平台：定价**产出** min/max 快照，`validation` 拿它做**拦截**——同一数据两处用，按"**算 vs 拦**"切。
6. **不要复刻"决策表物化 + 刷新"**：SF 的 element 依赖**物化决策表**，故需 Pricing Recipe 刷新（改源对象要重建）。平台既有 `condition_parser` 是**直查条件表达式**，**天然无刷新问题**。→ 走"**价目行 + 条件表达式直查 + 存取序列**"，**不做矩阵物化**（省钱、少一处不一致）。

### 4.5 四期深化：单据流里的价格传递与"按实际执行数量"重算

**问题（用户提出）**：上游订单的价，流到下游单据（交货 / 发货 / 开票）时，是**搬过去**还是**重算**？能不能**基于实际执行的数量**算，甚至**重新定价**？

**答案：需要——但这是两个正交维度，必须分开定；且都不是"二选一"，而是"逐属性 / 逐条件类型可配"。**

#### A. 维度一：单据链上的价格传递策略（复制 vs 重算）

| 家 | 机制 | 关键点 |
|---|---|---|
| **SAP** | **复制控制**里的 **Pricing Type（`KNPRS`）** 枚举（表 `TVCPF`，逐"目标单据类型 × 参考单据类型"维护；售→售 `VTAA` / 售→交货 `VTLA` / 交货→开票 `VTFL`）| **A** 复制价组件+重定阶梯 / **B 全新定价** / **C** 复制手工定价元素+重定其余 / **D** 复制价元素不变（价格固定、不读阶梯，条件基值/值重定）/ **E** 采纳价组件并固定值 / **G** 复制不变+**只重定税** / **H 只重定运费** / **I 只重定返利** → **传递策略是逐文档类型、逐条件类别的策略枚举**，不是全局开关 |
| **Oracle Fusion** | 三个 **freeze 开关**：**Freeze Price / Freeze Shipping Charge / Freeze Tax**（映射为 SDO 头部 `CalculatePricingChargesFlag` / `CalculateShippingChargesFlag` / `CalculateTaxFlag`）；外加全局参数 **"Use Price on Imported Orders That OM Already Priced"** | **逐属性**（价 / 运费 / 税）决定"不重算"；且 **revision 时开关值必须与首次一致**（否则行为不定）→ 传递策略是**稳定契约**，不是一次性入参 |
| **Salesforce** | **Repricing Service**（`RepricingElementServiceImplementation`）；另有 **`enableDeltaPricing`**（API v63+）| 对**已存在的订单行 / 资产**重定价，**遵守 context rules 与价目行有效期**；delta 模式**只重算变更部分**以加速 → 重定价是**显式服务调用**，不是隐式副作用 |

**结论**：传递策略应建模为**一个策略对象**（而非布尔），核心是 **`price_mode ∈ {搬运 / 按量重算金额 / 完全重定价}**，并可**逐属性**（价 / 运费 / 税）与**逐条件类型**覆盖。

#### B. 维度二：数量基准——订单量 vs 实际执行量

| 家 | 机制 | 关键点 |
|---|---|---|
| **SAP** | 开票复制控制里的 **Billing Quantity Indicator（`FKMGK`）** | 取值：**订单量 / 交货量 / 订单量−已开票量 / 交货量−已开票量 / 收货量−已开票量**…… → **"拿哪个量开票"本身就是可配枚举**；且与 Pricing Type **正交**（`D/E` 固定单价 + `FKMGK=D` 取交货量 = "**单价不动、按实际发货量算金额**"）|
| **Oracle Fusion** | 实际发货数量回写订单行 | **21D 起**：从履约系统捕获**实际发货数量（含第二计量单位 / 重量）**，OM **自动调整订单行的 extended amount**；**24C** 进一步允许自建履约任务在**发货后、开票前**触发**重算订单总额**（`RecomputeOrderTotalsFlag`），典型场景 = 大宗商品价格波动、发货后确认运费 |
| **EBS（历史）** | `Price Line` 行动 | 手动触发按**当前 list price 与自动折扣**重算 Selling / Extended Price（有 `Honor Holds at Repricing`）→ 重定价是**显式动作** |

**结论**：**"数量基准来源"必须与"单价是否重取"解耦**——这是两个独立开关，组合出三种语义：

| 组合 | 数量 | 单价 | 机制 | 对标 |
|---|---|---|---|---|
| ① **纯搬运** | 订单量 | 订单价 | 字段一对一搬运 | `doc_flow` `field_map`（一期已做）|
| ② **按实际量重算金额** | **实际发货 / 交货量** | **订单价（不重取）** | `金额 = 订单单价 × 实际量` | Oracle 21D 自动调整 extended amount；SAP pricing type `D/E` + `FKMGK=D` |
| ③ **完全重定价** | 实际量 | **重取价** | 用实际量作定价输入、**重跑定价过程**（可能跨阶梯档）| Oracle 24C reprice；SAP pricing type `B`；SF Repricing Service |

#### C. 落到平台的元模型建议

1. **定价结果带"冻结 / 重算策略"元数据**（件④配套）：`freeze_policy`（逐 `price / shipping / tax` 三粒度）+ `reprice_trigger`（`on_copy / on_ship_confirm / on_invoice / manual / scheduled`；★ v1.8 增加 **`on_quality_result` / `on_pricing_period_end`**——事实数据驱动重算，§4.8D⑥）。
2. **数量基准显式建模**：`qty_basis ∈ {order_qty, delivered_qty, goods_issued_qty, billed_to_date_qty}`，**开票默认取 `delivered_qty`**（SAP 惯例）；**须与 §4.3 的 `base_basis` 区分**——后者是"费率乘什么量"，前者是"**单据链上取哪一版数量**"。
3. **与 §5.2 边界的关系**：**重算归定价引擎、搬运归 `doc_flow`**——但**"用哪个策略"的声明属定价结果的元数据**，由定价引擎产出、`doc_flow` 与下游单据消费（避免两边各自猜）。这是 D8 的具体化（原来只有三档粗选项，现细化为"三档 × 逐属性"）。
4. **增量重定价（SF `enableDeltaPricing`）**列为**性能项**（P4+）：全量重算正确但贵，长单据链尤甚。
5. **红线**：**已开票 / 已过账的行不得隐式重定价**（对标 Oracle freeze 开关"revision 必须一致"、SAP 开票即价格冻结点）——重定价**必须显式触发且留痕**（进回放记录）。

> **与上位文档的衔接**：[单据流 Copy Control 深度研究](2026-09-29-doc-flow-copy-control-research.md) 讲的是"**搬哪些字段**"（复制控制的字段映射）；本节补的是它的**定价专属子问题**——"**价这个字段，搬、还是算**"，以及"搬/算时**用哪一版数量**"。

### 4.6 五期深化：定价的业务对象结构 —— 与订单 / 订单行 / 单据对象的关系

**问题（用户提出）**：定价引擎的**业务对象结构**怎么设计？它与**订单、订单行**等单据对象是什么关系——独立一套对象，还是挂在单据上？挂头还是挂行？

**先分清两条对象链**（混在一起是设计混乱的根源）：

| 链 | 对象 | 性质 | 生命周期 |
|---|---|---|---|
| **配置 / 主数据链** | 字段目录 → 条件表 → 存取顺序 → 条件类型 → 定价过程；价目表 + 价目行（条件记录） | **主数据**（版本化、有有效期） | 长期存在，与单据无关 |
| **单据运行时链** | **单据头 → 单据行 → 定价结果（Charge / 条件行）→ 步骤明细（Component / 条件项）** | **事务数据**（属单据） | 随单据创建 / 重算 / 作废 |

**关键结论：定价结果不是独立"定价单据"，而是"业务单据的从属对象"**——但需要一个**单据级的聚合锚**。

#### A. 三家如何把定价结果挂到单据对象上

| 家 | 单据对象（头 / 行） | 定价结果的宿主 | 聚合锚 | 明细粒度（键 / 字段） |
|---|---|---|---|---|
| **SAP** | `VBAK`/`VBAP`（订单）→ `LIKP`/`LIPS`（交货）→ `VBRK`/`VBRP`（开票），均头 + 行、以 `VBELN` 相连 | **条件行 `KONV`**（新结构 `PRCD_COND`/`PRCD_ELEMENTS`），**随单据存** | 头表的 **`KNUMV`（文档条件号）** | 键 = `KNUMV + KPOSN(行号) + KSCHL(条件类型) + STUNR(步骤) + ZAEHK(计数器)`；`KAWRT`=条件基准、`KBETR`=费率、`KPEIN`/`KMEIN`=定价单位/单位；**`KHERK=D` 标记"头条件"**；`KNTYP`=类别（税/运费/价/成本）|
| **Oracle Fusion** | SDO：**Header / Order Line** | **`Charge` 挂订单行**；`ChargeComponent` 挂 `Charge` | 无独立号，整条 SDO 一次回传 | 每个 Charge 带多组件；组件含 `SequenceNumber` / `PriceElementCode` / `PriceElementUsageCode` / `RollupFlag` / `SkipRunningPrice` / `TaxIncludedFlag`；头上有 `CalculateTaxFlag` 等开关 |
| **Salesforce** | `Quote`/`QuoteLineItem`、`Order`/`OrderItem` | 结果经 **`PricingProcedureOutputMap`** 映射回**单据行字段**；明细走 API 返回的 **price waterfall** | 无 | 输出映射（Tooling 元数据）决定"哪个定价结果写回单据的哪个字段"；价目行侧有 `PriceBookEntryDerivedPrice`（派生价）|

**归纳出三个结构事实**：

1. **值落"行"，不落"头"**：三家结果最终都写到**单据行**；单据头只放**参数 / 开关**（Oracle `CalculateTaxFlag`）与**聚合号**（SAP `KNUMV`）。
2. **"头条件"靠"层级标记 + 分摊"表达，不建独立头对象**：SAP 头条件仍是行级条件表里的一行（靠 `KHERK=D` 标记 + 按 `KPOSN` 展开）；SF 头折扣靠 **DDS 摊到行**（§4.4 启示 4）。→ 与 §4.3 的 `base_level=header` 是同一件事。
3. **结果天然分两层**：**结果行**（一个条件类型 / 一个 Charge 一条）与**步骤明细**（一步一个 Component / 一条子项）——正好是 D4"**字段 + 明细都要**"的落点。

#### B. 落到平台的对象结构建议

复用平台**既有范式**：`bo_category: transactional` + `bo_sub_category: document`（[sales_order_enhanced.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/examples/sales_order_enhanced.yaml#L6-L7) 已用），头→行用 **`composition 1:N / ownership / cascade_delete`**（`rel_lines`，[L378-387](file:///d:/filework/excel-to-diagram/meta/schemas/examples/sales_order_enhanced.yaml#L378-L387)）。**不另造"定价单据"**：

```
sales_order (document，已有)
 ├─ order_line (composition 1:N，关系已声明；对象待建)
 │    ├─ unit_price / net_price / extended_amount      ← 结果字段（展平，供业务读取）
 │    └─ pricing_result (composition 1:N)              ← 结果行：一个条件类型 / 一个 Charge 一条
 │         └─ pricing_step (composition 1:N)           ← 步骤明细：一步一条（回放用）
 └─ pricing_result (composition 1:N)                   ← 头级条件（运费 / 整单折扣）：level=header
```

| 对象 | 建议字段 | 对标 |
|---|---|---|
| **`pricing_result`**（结果行） | `document_type` / `document_id` / **`document_line_id`（可空 = 头级）** / `level ∈ {header, line}` / `condition_type` / `element_type` / `base_level` / `base_basis` / `base_step` / `base_roll` / `rate` / `amount` / `currency` / `sign` / `sequence` | SAP 条件行（`KSCHL`/`KAWRT`/`KBETR`/`KHERK`）；Oracle `Charge` |
| **`pricing_step`**（步骤明细） | `result_id` / `seq` / `element_type` / `price_element_code` / `rollup_flag` / `skip_running_price` / `unit_price` / `extended_amount` / **`running_net_price`**（仅 `base_roll=true` 时记）| Oracle `ChargeComponent`；SF waterfall 各档 |

- **泛化宿主**：`document_type` + `document_id` 让同一套对象**挂到任意单据 BO**（订单 / 交货 / 开票都是 `document`），无需为每种单据复刻——呼应 §4.5"价在下游单据怎么来"。
- **头级分摊**：`level=header` 的结果 + 由 DDS 式分摊**生成的 `level=line` 分摊明细**两者并存（头记总额、行记摊得额），对标 SF DDS。
- **生命周期随单据**：`cascade_delete`；**重算 = 版本化替换明细 + 留痕**（配合 D5 保留策略），**已开票 / 已过账行冻结**（§4.5C 红线）。
- **与 `doc_flow` 的边界**：`doc_flow` 搬的是**结果字段**（`unit_price` / `net_price`），**不搬明细**——明细在下游单据**重新生成或引用**。这正是 D8 `price_mode` 在对象层的体现（"搬运"=只搬字段；"重算"=重新生成明细）。
- **与对象模型总纲（计划 vs 事实）**：**价目行 / 条件记录 = 主数据（计划侧）**；**`pricing_result` = 事实（单据从属）**。

> **一句话**：定价对象结构 = **"单据为主、结果为从、行级落值、头级靠标记与分摊、明细可回放"**——**不引入独立"定价单据"**，避免与 `doc_flow` 争"谁是单据"。

### 4.7 六期深化：事后 / 计划外费用与分摊 —— 采购侧与执行期费用

**问题（用户提出）**：**事后 unplanned charge**（比如针对采购）、**过程中的费用**、**分摊**——上面是否已经考虑了？

**答**：**分摊只覆盖了"过程内"的一半；事后费用与过程费用基本没覆盖**（前者在 §4.3① 只做了"头→行按行价值比例"一种，后者完全没进模型）。本节把"费用"按 **发生时机 × 来源单据** 切成三类，补齐缺的两类，并给出**分摊规则**与**追溯调整**的对象设计。

#### A. 先把"费用"切三类（混在一起是设计混乱的第二次根源）

| 类 | 金额何时确定 | 来源单据 | 现状 |
|---|---|---|---|
| **① 过程内条件费用** | 单据创建时（取价即定） | 订单 / 报价本身 | ✅ 模型已设计（§4.3；**头条件 / 组条件分摊按 D10 属 P3+**，行级五层随 P2）（原文另引 "基价→折扣→附加费→税→运费"） |
| **② 事后计划外费用（unplanned）** | **单据创建之后**（发票校验 / 收货 / 服务确认 / 结算） | **不是订单**——发票 / 收货单 / 服务确认单 / 结算单 | ❌ 本版补（B–E） |
| **③ 过程执行费用** | **执行期才发生**（生产 / 在途物流） | 工序报工 / 仓储 / 运输 | ❌ 与 ② **同构**（都是"事后才知道金额"），共用一套模型；**成本侧取值不在 D7（只做定价）范围**，本版只做对象设计 |

> **关键**：②③ 与 ① 的分水岭**不是**"是否守恒 / 是否跨行"（那是 §5.2 的**过程内外**判据），而是"**金额何时确定 + 谁说了算**"——订单的条件记录，还是**后来的另一张单据**。

#### B. 三家对标

| 家 | 机制 | 关键点 |
|---|---|---|
| **SAP（采购侧）** | **Unplanned Delivery Costs（计划外交付成本，德语 planlose Bezugskosten）**：在 **MIRO 发票校验**抬头录入（界面字段 *Unplanned delivery costs*，数据字典 `BEZNK`） | 两种处理：① **按发票行分摊**（Distribute among invoice items）② **记独立 G/L 费用科目**；配置点 = SPRO → MM → Logistics Invoice Verification → Incoming Invoice → *Configure How Unplanned Delivery Costs Are Posted*（公司代码级，空白=分摊）；**入账去向取决物料价格控制 + 库存覆盖**——移动平均价且有库存→**计入库存价值**，标准价→**价差科目**，选独立科目→**总账费用** |
| **SAP（采购侧·技术）** | 计划内交货成本走 **PO 条件类型 FRA1/FRA2**；**未计划费用不走条件技术** | 独立科目走 **OBYC 事务码 `UPF`**，自定义分摊规则用 **BAdI `MRM_UDC_DISTRIBUTE`**；分摊基数**默认按发票金额比例**（重量 / 数量 / 体积有资料提及，**官方口径未证实**）→ 结论：**"费用不一定走条件技术"** |
| **SAP（销售侧·事后）** | **Subsequent Debit / Credit**（后续借项 / 贷项）**属 MM 发票校验**：MIRO 顶部事务类型下拉，对**已过账的供应商发票**做增减值增量凭证，**引用同一 PO、不改原凭证**——注意**它不是 SD 开票字段** | SD 侧事后调整走 **开票更正请求**（VA01 订单类型 **RK**，参考原始发票，**成对产生贷 / 借项、仅结算差额**，自动开票冻结）；或贷项 / 借项凭证请求（G2 / L2 → VF01）。**开票过账后不可改，只能 VF11 取消重建** |
| **SAP（追溯）** | 定价日期 **`PRSDT`** 可设为过去（默认提议由 **VOV8** 与复制控制决定）；**条件记录有效期变更不自动重算已过账单据** | 批量重定价 = **VA05 → Edit → Mass Change → New Pricing**；单张 = **VF02 Update Pricing**；成本后更新 = 事务 **VF_VPRS / 报表 SDINVUPDR** → **追溯必须显式触发** |
| **SAP（返利）** | 返利协议 **VB01 / VBO1**（S/4 = **WCOCO 条件合同**），条件类型 **BO01–BO05**，账码 **ERB 计提 / ERU 冲销** | **条件更新字段 `KOUPD`**（V/06 配置，表 `REBC_COND_CT` / `PRCC_COND_CT`）→ **累计已用量，可设最大金额 / 数量 / 单据数，超限自动失效**；结算 = VB02 状态改 B 释放 → 生成返利贷项请求（G2）/ 凭证（B1）；**支持多期部分结算 + 最终结算，最终结算冲抵已结算部分**；S/4 由 **Condition Contract Settlement** 取代，另有 **Delta Accrual** 补提已开票期间 |
| **Oracle Fusion（采购侧）** | **Landed Cost Management（LCM）**：Trade Operation 容器 + **费用行 Charge** 挂 PO schedule / 收货 / 装运 | **★ 分摊基数 6 种【确定】：`Equally`（均等）/ `Item value`（采购价×数量）/ `Manual allocation factor`（手工系数）/ `Quantity`（数量）/ `Volume`（体积）/ `Weight`（重量）**；另 Charge Basis = Aggregate / Per unit / % of item price / % of other charges；**分摊去向 = 计入物料 / 库存成本与 COGS**；**独立费用行**——每条 landed cost charge 生成**独立的 acquisition cost adjustment，不改原单价** |
| **Oracle Fusion（事后调价）** | **Retroactive Price Adjustment** + **Acquisition Cost Adjustment** | PO 价事后 100→120 → 对**未开票数量**生成回溯调整 → Cost Accounting 生成 acquisition cost adjustment **回写库存估值**；发票价差（IPV）/ 汇率差 / 税额差同理做 true-up |
| **Oracle Fusion（订单侧）** | 仅有 `CalculateShippingChargesFlag` / 行级 `SkipShippingChargesFlag` 控制**是否重算**运费 | **"发货后再追加运费"的标准 ad-hoc charge 机制：未找到**【未找到】 |
| **Salesforce** | `PriceAdjustmentSchedule` / `PriceAdjustmentTier` 是**预先配置**的调整计划 | **"下单后追加一次性费用"的专门标准机制：未找到**【未找到】；替代路径 = Cart 阶段 **apply adjustment API**（discount / markup / override，作用于 Opportunity / Quote / Order 行）或 order-based 一次性折扣；**对已成交订单行与 Asset 的事后调整走显式 Repricing Service** |

#### C. 归纳四条规律（+ 一条边界启发）

1. **不改原单价，独立费用行 + 分摊**：三家一致（Oracle 生成独立 acquisition cost adjustment；SAP 计划外交付成本走独立行 / 独立科目）。→ 平台：**事后费用是 `pricing_result` 的另一种 `origin`，不改原价目行、不改原条件行**。
2. **分摊基数是可配枚举、且是"一等配置对象"**：Oracle 6 种基数、SF DDS 分摊规则决策表、SAP BAdI 可自定义 → **不能把"按行价值比例"写死**（原稿 §4.3① 只有这一种，是缺口）。
3. **去向（进成本 / 进费用）是可配字段，不是硬编码**：Oracle 计入库存成本与 COGS；SAP 由**物料价格控制 + 库存覆盖 + 公司代码配置**三者决定进库存价值 / 价差 / 总账费用。→ 平台：`target ∈ {cost, expense}` 作为**分摊规则的字段**。
4. **追溯调整必须显式触发 + 引用原结果 + 留痕**：SAP 条件记录变更**不自动**重算已过账单据（须 `New Pricing` / `Update Pricing`）；返利**最终结算冲抵已结算部分**；Oracle 事后调价由 **Cost Accounting** 单独处理并回写估值。→ **与 §4.5C 红线同源**，且**补差要成对（只结算差额）**。

> **第五条（边界启发）**：**费用不一定走条件技术**（SAP 未计划费用走 OBYC `UPF` + BAdI，不走条件记录）→ **定价引擎不能垄断"费用确定"**；平台要有"**条件技术内**（`pricing_result` 由条件记录命中）"与"**条件技术外**（费用行 + 分摊规则）"两档——**二者落同一张 `pricing_result` 表、以 `origin` 区分**。

#### D. 落到平台的对象结构建议（在 §4.6B 上扩展，**不新建费用单据**）

```
pricing_result  ← 扩展为"价格 / 费用通用结果行"
 ├─ origin ∈ {planned, unplanned}          ← 计划内（条件记录命中）/ 计划外（事后录入）
 ├─ charge_source ∈ {order, invoice, receipt, service_confirm, settlement}
 │                                         ← 来源单据类型（可 ≠ 宿主单据！）
 ├─ source_document_type / source_document_id
 │                                         ← 来源单据（发票 / 收货单 / 服务确认单）——反向挂到 PO / 订单
 ├─ target ∈ {price, cost, expense}        ← 去向：价 / 成本 / 费用
 ├─ allocation_basis ∈ {equal, value, quantity, weight, volume, manual, none}
 ├─ allocation_rule_id                      ← → allocation_rule
 └─ (原有 level / document_line_id / condition_type / rate / amount …)
```

| 新增对象 | 建议字段 | 对标 |
|---|---|---|
| **`allocation_rule`**（分摊规则） | `id` / `basis ∈ {equal, value, quantity, weight, volume, manual}` / `manual_factor` / `group_by`（按什么分组摊）/ `rounding` / `floor`（地板价）/ **`target ∈ {cost, expense}`** | Oracle LCM **6 种 Allocation Basis**；SF **DDS 分摊规则决策表**（地板价 + 等分 / 按行值） |
| **`pricing_adjustment`**（追溯 / 补差） | `original_result_id`（被调整的原费用 / 原价）/ `adjustment_type ∈ {subsequent_debit, subsequent_credit, retro_price_change, rebate_settlement, delta_accrual, provisional_settlement}`（★ v1.8 增 `provisional_settlement`——大宗暂定价 → 终价，§4.8D⑤）/ `delta_amount` / `effective_period` / `posted_flag` | SAP 后续借项 / 贷项 + 返利结算（部分 / 最终结算冲抵）；Oracle retroactive price adjustment |

- **反向挂载**：`source_document_type / source_document_id` 让"**发票上的费用**"能摊到"**PO / 收货 / 订单行**"——这正是 §4.6B 泛化宿主（`document_type` / `document_id`）**预留位**的用途；只是现在要**允许"宿主单据 ≠ 来源单据"**。
- **两条落库去向**：`target=cost`（进库存成本 / COGS，对标 Oracle）与 `target=expense`（进总账费用，对标 SAP 独立科目）**共用同一套数据结构**，由 `allocation_rule.target` 决定。
- **三条护栏**：① **已过账 / 已开票不隐式重算**（§4.5C）；② **追溯调整须引用原结果、成对、只结算差额**（对标 SAP 更正请求"成对贷 / 借项"、返利"最终结算冲抵"）；③ **分摊可回放**——头记总额、行记摊得额，来源单据与分摊规则可查（呼应 §4.6A 结构事实 2）。
- **成本侧的边界**：`target=cost` 的**取值算法**（移动平均 / 标准价 / 价差）属**成本核算**，不属定价；定价只产出"**一笔费用 + 摊到哪些行 + 摊多少**"（= D7"只做定价"的边界）。

#### E. 与既有边界的关系（§5.2 / §7 须细化）

原稿把"**过程外的跨单据 / 跨期间成本费用分摊**"整体推给**待建 allocation**（§5.2、§7 非目标）——**本版细化为两档**：

| 档 | 内容 | 归属 | 判据 |
|---|---|---|---|
| **① 费用分摊（有价格语义）** | 一笔费用**摊到一个业务单据的行**（计划外交付成本摊 PO 行 / 收货；运费摊订单行；报关费摊收货） | **定价的"费用 / 分摊"子域**（`pricing_result` 家族 + `allocation_rule`） | **是否"把一笔费用摊到某个业务单据的行"** |
| **② 财务分摊（无价格语义）** | 跨期间 / 跨成本中心 / 跨主体的费用归集与分摊（管理会计口径） | **仍归 allocation** | 无"业务单据行"这个落点 |

> 判据从 §5.2 的"**是否在定价过程内**"**升级为**："**是否有'可分摊到一个业务单据行'的价格 / 费用语义**"——**有 → 定价家族；无 → allocation**。（前者是过程内的粗判，后者把过程外的**费用分摊**也纳入定价家族。）

> **一句话**：**费用 = 价格结果的特例**——"事后 unplanned charge"就是一条 `origin=unplanned`、`source_document ≠ 宿主单据`、带 `allocation_rule` 的 `pricing_result`；**追溯补差另立 `pricing_adjustment`**，全程守"**不隐式重算 + 成对留痕**"两条红线。

### 4.8 七期深化：基于质检结果 / 事实数据的重新计算 —— 优质优价与大宗贸易

**问题（用户提出）**：基于**质检结果**或**其他事实数据**进行重新计算，比如**优质优价**、**大宗贸易**——这个考虑了吗？

**答**：**没有专门考虑**。原稿的"重算"只有一路——**按实际数量**（§4.5 的 `qty_basis` / `freeze_policy` / `reprice_trigger`）；**"按质量 / 计量 / 市场等事实数据重算"这一路整体缺失**。本节把"事实数据"切三源，补上"**事实源作为定价输入**"这条链，并给出大宗贸易的两段式结算。

#### A. 先把"事实数据"切三源（与 §4.7 同源：事实源 ≠ 订单条件记录）

| 事实源 | 典型数据 | 驱动什么 |
|---|---|---|
| **① 质量事实（质检 / 化验）** | 品位（Fe / Cu 含量）、热值（calorific value）、水分、杂质、蛋白 / 脂肪 | **质量升贴水（优质优价）** + **数量折算**（按品位折算金属量） |
| **② 计量事实** | 实际重量 / 体积 / 水分 | **结算数量**（**干吨 / 净干重**）——★ **"结算数量"本身依赖质量事实** |
| **③ 市场事实（外部报价）** | Platts / LME / ICE / 指数 | **公式定价 + 计价期均价**（大宗贸易） |

> **共同点**：三者**都不是"订单创建时可确定的条件"**，而是"**后来由另一个事实源给出**"——与 §4.7 的"事后费用"**同族**（来源 ≠ 订单条件记录），因此**复用同一套扩展**（事实快照 + 显式触发 + 差值结算）。

#### B. 三家对标

| 家 | 机制 | 关键点 |
|---|---|---|
| **SAP（特性 / 变式定价）** | **变式定价（Variant Pricing）**：特性值**不直接**做条件表字段，而是经"**参考特性**"把变式键写入 `SDCOM-VKOND` → 落到 **`KONV-VARCOND`（变式条件键，CHAR26）**；条件表用 **`VARCOND`** 字段（如条件表 **A900**、条件类型 **VA00**，表 `TVARC`） | 路径 **V/03 条件表 → V/07 存取顺序 → V/08 定价过程**；**变式定价在 SD 抬头层**。★ 注意：**`VACOND` 不存在**，标准字段是 `VARCOND` |
| **SAP（批次定价）** | 标准做法 = 条件表放 **批次号** 字段，按批建条件记录（批次属性靠**分类系统，类类型 023**） | **把"批次分类特性值本身"直接当条件表字段 → 未找到标准功能**（须增强 / CPE）→ **头部产品这里也是"半成品"** |
| **SAP（大宗贸易 / CPE）** | 官方框架 **CPE（Commodity Pricing Engine）**：公式驱动、挂钩市场 | **暂定价 → 终价**：Provisional（装运时估算）→ Final（**质检结果 / 计价期结束**等条件齐备后），**差额自动生成 credit / debit memo（两段式开票）**；**报价源** Platts / Reuters / LME / ICE 经 **MIC + DCS + Quotation 规则**进 CPE；**F&A（Formula and Average Pricing）** 用外部报价按**计价期**算价（原 IS-OIL-DS-MAP，MM / SD 均可用，现迁 CPE，包 `OIC_MIGR`）；**Differential（价差）/ Quality premium-discount（质量升贴水）/ Partial quantity pricing** 均为**标准概念** |
| **SAP（按品位折算数量）** | **Active Ingredient Batch Management + 批次特定计量单位（动态替代单位）** | 按**批次特性**折算数量 → **"结算数量"依赖质检特性**（干吨 / 净干重 / 金属量） |
| **SAP（采购侧）** | **"质检结果自动改采购价"的标准功能：未找到** | 现实路径 = **UD（使用决策）后付款冻结** + **MIRO 后续借 / 贷记（只调金额、不调数量）** + **贷方凭证（可减数量）** + 容差 **OMR6 / OBA3** 触发发票冻结；QM 质量分只进**供应商评估 ME61** |
| **Oracle Fusion** | **属性驱动定价【确定】**：物料 **extensible attribute / attribute group** 可接入定价规则做折扣 / 加价（Domain 写作 `attribute_group.attribute:...`），也可用可扩展弹性域值**覆盖基础目录价** | **"质检 / 化验值 → 定价"无标准链路【未找到】**——替代做法 = 把质检值落到**自定义 item extensible attribute / pricing attribute**，再经 Service Mapping 或 Pricing Algorithm 注入上下文 |
| **Oracle（公式定价）** | **EBS Advanced Pricing 有完整 Pricing Formulas**（`QP_Formulas`；表达式 `+ - / *`、括号、NVL / SQRT / MOD；公式行 / Step；公式类型 = Pricing Attribute / Numeric Constant；Static / Dynamic Formula） | **Fusion Pricing 未找到独立 Formula 对象**（靠 **Pricing Algorithm / Price Element** 承担）；**外部报价源 + 计价期【未找到】开箱机制**（只能 SOAP / REST 接外部成本，指数须自定义属性注入） |
| **Oracle（大宗）** | **GTM（合规 / 落地成本模拟）与 Trade Management（渠道促销索赔）均无 provisional → final 货价、无按干吨 / 品位结算【未找到】** | 最接近的旁证：**Landed Cost 的 estimated → actual**（成本而非货价）、**JD Edwards 的 Grade & Potency Pricing（品位定价）** |
| **Salesforce** | **`AttributeBasedAdjustment`**：属性调价，`AdjustmentType = Override / Percentage / Amount`（覆盖 / 加减价），可配**区间 / 阶梯** | **`PriceAdjustmentSchedule` 是容器（Master-Detail 父）**，下挂 `AttributeBasedAdjustment`（**属性调价**）与 `PriceAdjustmentTier`（**数量区间阶梯**：Tier Type = Percentage/Amount/Override、Lower/Upper Bound）；`AttributeBasedAdjRule` 归组、`AttributeAdjustmentCondition` 定义"**属性 = 值**"条件行；**`ProductAttributeDefinition` 须 `IsPriceImpacting = True` 才参与定价**；由 Pricing Procedure 的 *Attribute-Based Price / Attribute Discount Entries* 元素驱动 |
| **Salesforce（暂定价 / 指数）** | **"暂定价 → 结算价 / 质量升贴水"未找到**；替代 = `PriceRevisionPolicy`（续约调价）+ 自定义属性调整 | **指数定价【基本确定】= `IndexRate` + `PriceRevisionPolicy（Type = Price Index）`** |

#### C. 归纳四条规律

1. **事实数据进入定价有两条路**：**① 作为"条件表的一个字段维度"**（SAP `VARCOND` 变式键；SF `AttributeBasedAdjustment` + `PriceAdjustmentSchedule`；Oracle extensible attribute）——这是"**优质优价**"的主路径；**② 作为"数量 / 计量折算的输入"**（SAP 批次特定计量单位 → 干吨 / 金属量）——这是"**按实际品质计量结算**"的路径。
2. **"质检值直接改价"在头部产品里普遍是"半成品"**：Oracle【未找到】、SAP 采购侧【未找到】、SAP 批次特性当条件字段【未找到】、SF 无质量升贴水标准机制【未找到】——**都要靠自定义属性 / 增强绕行**。→ **平台若把"事实源字段"做成一等，就是相对头部的能力增量**（呼应 D7"元模型按通用设计"）。
3. **大宗贸易 = 两段式（暂定价 → 终价）**：靠"**重新计价 + 差额结算**"实现，**不改原单据**（SAP CPE：差额自动生成 credit / debit memo）——**与 §4.7 的 `pricing_adjustment` 天然衔接**（`adjustment_type` 加 `provisional_settlement`），也落在 §4.5 的"完全重定价"那一档。
4. **计价期 + 外部报价源是"一等配置"**（SAP：MIC / DCS / Quotation 规则 + F&A 计价期；SF：`IndexRate` + `PriceRevisionPolicy`）→ 平台需要**外部价格源对象 + 计价期定义**，不能只是"某天取一个数"。

#### D. 落到平台的对象结构建议（在 §4.6B / §4.7D 上扩展）

**① 字段目录（件①）扩展 —— 让"事实源字段"与主数据字段同权**：

| 新增 | 说明 |
|---|---|
| **字段来源分类 `source_type ∈ {static, master, quality, measurement, market}`** | 条件表可直接引用 **`quality`（质检值）/ `measurement`（计量值）/ `market`（外部报价）** 三类**事实源字段**；配置方式与主数据字段一致（进入存取顺序）——对标 SAP **`VARCOND` 变式键** / SF **`IsPriceImpacting` 属性** / Oracle **extensible attribute** |

**② 新增两个配置对象**：

| 新增对象 | 建议字段 | 对标 |
|---|---|---|
| **`external_price_source`**（外部价格源） | `id` / `source ∈ {platts, lme, ice, index, custom}` / `quote_code` / `calendar_id`（发布日历）/ `fallback_rule`（缺报价降级） | SAP **MIC + DCS + Quotation 规则**；SF **`IndexRate`** |
| **`pricing_period`**（计价期） | `id` / `period_type ∈ {shipment_date, receipt_date, invoice_date, fixed_range}` / `start_offset` / `end_offset` / `average_basis ∈ {close, average, first, last}` / `rounding` | SAP **F&A 计价期**；SF **`PriceRevisionPolicy（Type = Price Index）`** |

**③ `pricing_result` 再扩展（复用 §4.7D 的扩展位）**：

```
pricing_result
 ├─ price_source ∈ {condition_record, external_quote, formula}   ← 价从哪来
 ├─ pricing_period_id / external_price_source_id                  ← 计价期 / 报价源
 ├─ fact_snapshot（JSON）                                         ← ★ 本次结算用到的质检值 / 计量值 / 报价值
 └─ (原有 origin / charge_source / source_document_* / target / allocation_* …)
```

**④ `qty_basis`（§4.5）扩容**：加 `dry_weight` / `net_dry_weight` / `assayed_content`（按品位折算金属量）→ **"结算数量"本身依赖质量事实**（对标 SAP Active Ingredient Batch Management + 批次特定计量单位）。

**⑤ 复用既有对象，不新增"结算单"**：
- **质量升贴水（优质优价）** = 一条 `pricing_result`（`element_type` 可加 **`quality_premium`**，或走 `base_basis = attribute` + 公式）；
- **暂定价 → 终价** = **`pricing_adjustment{adjustment_type = provisional_settlement}`**（**只结算差额、不改原单据**，对标 SAP CPE 两段式开票 + §4.7 的后续借 / 贷记）。

**⑥ 三条护栏**：① **事实快照必须存档**（`fact_snapshot` 随结果留痕——质检值 / 计量值 / 报价值缺一即不可复现）；② **重算须显式触发**（§4.5C 红线，`reprice_trigger` 增加 **`on_quality_result` / `on_pricing_period_end`**）；③ **暂定价与终价必须配对可查**（`pricing_adjustment.original_result_id`，对标 SAP 差额 memo）。

#### E. 边界（本节只做"定价"这一层）

| 不做 | 归属 |
|---|---|
| **期货保值 / 风险管理 / 头寸** | 归 **CTRM / 风控**——定价只消费其给出的价 |
| **质检本身**（检验批、使用决策 UD、质量通知） | 归 **QMS**——定价只消费"**质检结果 → 定价输入字段**"这一层 |
| **质量成本**（返工 / 报废 / 降级损失） | 归 **成本核算**（§4.7 边界） |
| **纯财务口径的期间 / 成本中心分摊** | 归 **allocation**（§4.7E） |

> 若某行业**没有质检链路、也没有外部报价源**，走 §4.3 的条件记录即可，**本节的机制可不用**（非强制）。

> **一句话**：**"事实数据重算" = 条件表多一维事实源（`source_type ∈ {quality, measurement, market}`）+ 数量可折算（`qty_basis`）+ 价可来自外部报价与计价期（`external_price_source` / `pricing_period`）+ 结果带事实快照（`fact_snapshot`）**；优质优价落成 `quality_premium` 结果行，大宗两段式落成 `provisional_settlement` 差值——**均不改原单据，守"显式触发 + 快照留痕"两条红线**。

### 4.9 八期深化（跨域二次研究）：把同一套骨架拿到 **Oracle 成本域 / 碳域** 去逐字对撞

> **本节目的**：前七期都是从**定价域**向外看（SAP/Oracle/SF 的定价机制），本节**反向操作**——已把元模型改成"领域中立 + 三轴参数化"（见 Spec v1.3 §9.3.1），那就必须做一次**反向验证**：拿 Oracle 自家**另外两个域**的引擎来对撞，看三轴是否真的成立。
>
> **为何选 Oracle 做二次研究**：① 它是六家里**唯一一家在同一品牌内同时存在三套"量 × 率 × 多步"引擎**——定价（Fusion Pricing）、成本（SCM Cost Management）、碳（EAR / OFS Climate Change Analytics）；② 跨厂商比容易掺入"各家术语不同"的噪音，**同厂商内部比**更能证明"骨架相同、只是实例参数不同"。
>
> **术语提示**：本节沿用本稿 §4.2–§4.8 的旧标识符（`pricing_result` / `pricing_step` / `pricing_procedure` / `condition_record` / `base_basis`），以便与前文一致；对应 Spec v1.3 的新名见括号——`pricing_result→calc_result` / `pricing_step→calc_detail` / `pricing_procedure→calc_procedure` / `condition_record→rate_record` / `base_basis→base_source`。

#### A. 成本域取证：Oracle SCM Cost Management / Cost Accounting【确定】

**A1. 它的对象链**【确定】

```
Cost Organization（成本组织）
  └─ Cost Book（成本簿：primary 财务 / secondary 管理 / ledgerless 模拟）
       └─ Cost Scenario（成本情景，绑 成本组织 × 成本簿）
            ├─ Cost Element（成本元素：Material / Overhead / …）
            ├─ Cost Component（成本构成项 → 映射到 Cost Element）
            ├─ Resource Rate（资源费率）/ Overhead Rate（间接费率）
            └─ Sourcing Rule（自制 / 采购 / 转移 + 分配百分比 + rank）
                 ↓ Roll Up Costs（成本卷积）
            Standard Cost（标准成本） → Cost Accounting（实际成本核算）
                 ↓
            Cost Accounting Distribution（成本会计分录行）
```

**A2. ★ 逐字对撞：卷积公式就是"量 × 率 + 逐层累加 + 归一化除法"**【确定】

Oracle 官方对 `Roll up Costs` 的定义（原文直译）：

> 总成本 = **固定成本工序** + **变动成本**（**单位资源成本 × 消耗数量**）；
> 随后计算**单位成本 = 总成本 ÷ 缩放数量（scaled quantity）**。

对撞结果：

| 定价域（§3.1.2） | 成本域（本节 A2） | 同构点 |
|---|---|---|
| `Net Price = 价目行费率 × 定价数量`，逐条累加 | `Total Cost = 资源费率 × 资源消耗量`，逐层累加（BOM 树） | **同一骨架**：`Σ(rate_i × qty_i)` |
| 官方算例 `$700 × 2 = $1,400`（AS54888） | 官方算例 `SC_ABCDEF`：`Labor-3 用 10 hours`、`Mach-01 用 5 hours` → 卷积出单位成本 | **都是"取活动量 × 率"** |
| `pricing_result.rate` / `amount` / `currency` | `Cost Accounting Distribution`（结果行，含金额与科目） | **结果都落"行"**，不落头 |
| 阶梯价目表 `scale[]`（按量分档） | `Cost Scenario` 版本化（`In process` → `publish`） | **都是"按量/按期取一档"** |

**A3. ★★ 重大发现：Oracle 成本域的候选消解是「按权重加权求和」，不是「取一」**【确定】

当**多条同 rank 的 Sourcing Rule 并存**时，Oracle 官方公式为：

```
Standard cost of product
  = (User entered buy cost      × Buy      sourcing rule allocation)
  + (Rolled-up cost from work def × Make     sourcing rule allocation)
  + (Transfer cost              × Transfer sourcing rule allocation)
```

**三条候选全部参与，按各自 allocation% 加权求和**——这与定价域的 `exclusion_group`（互斥组内**取一**）和 `precedence`（**取一**）**都不同**，是**第四种消解范式**。同一范式在 Oracle 内部至少出现三次：
- `Sourcing Rule.source_allocation_percentage`（成本卷积，如示例表的 25% / 100%）；
- 工单事务上的 **`Cost Factor Allocation`**（官方示例：Pulp 二次产出 25%、Orange Juice 主产出 100%）；
- LCM 费用行的 **`Charge Basis = % of item price / % of other charges`**（§4.7D）。

**A4. 三种成本方法 = 同一批事务、三套估值基础**【确定】

`Actual`（按 receipt layer 逐层取实际成本）/ `Standard`（当期标准成本）/ `Perpetual Average`（永续平均）——**同一批事务，三种 valuation basis 出三种结果**。且 Oracle 强制"多结果并存需挂在不同 Cost Book 上"（primary 财务 / secondary 管理 / **ledgerless 纯模拟**）。

**A5. 暂估 → 实际两段式在成本域是原生能力**【确定】

- `Provisional completion`（暂估完工）+ `Adjustment propagation`（差异传播）——完工时先按暂估价结转，差异随后传播；
- **`adjustment propagation` 内建循环依赖检测**：允许"完工产出反哺材料领用"形成环，**但传播 3 圈后强制停止**；`Enforce Transaction Order` 用于防死锁；
- `Landed Cost Management`：**Estimated Landed Cost → Actual Landed Cost** 两段（§4.7D 已引）。

**A6. 域特有逻辑确实厚重（★ 反证，见 §4.9F）**

成本域有大量**不属"量×率"计算**的东西：成本会计期间与截止日（`Cost Accounting Periods` / `Cost Cutoff Dates`）、期间状态、成本差异（`standard cost vs actual` 差异分析）、WIP 余额、成本簿与总账关联、**Cost Accounting Distribution 的科目映射**。**这一层 Oracle 不放进"计算"里，而放在计算之后的核算与报告里。**

#### B. 碳域取证：Oracle EAR（EBS）/ OFS Climate Change Analytics / EPM for Sustainability【确定】

**B1. Oracle EAR（Environmental Accounting & Reporting）——★ 最干净的"量×率"标本**【确定】

| 对象 | Oracle 定义（直译） |
|---|---|
| **Emission Factor**（排放因子） | "用于计算**消耗或产生某个 Emission Source 所产生的 Emission Type 数量**的因子"，单位如 **kg CO2-e / KWh**、**kg CO2-e / GJ** |
| **Emission Source**（排放源） | 如 Purchased Electricity（外购电） |
| **Emission Type**（排放类型/温室气体） | CO2 / CH4 / N2O / HFCs / PFCs / SF6 / NF3 |
| **Emission Scope**（范围） | Direct = **Scope 1** / Indirect = **Scope 2** / 其余 = **Scope 3** |
| **Environmental Ledger**（环境台账） | 计算结果落库对象 |

**计算式（官方算例）**：

```
排放量 = 活动数据 × 排放因子
        = 100,000 KWh × 0.9 kg CO2-e / KWh
        = 90,000 kg CO2-e
```

**逐字对撞**：这就是 **`pricing_result.amount = rate × qty` 的碳版**——`base_source = activity_quantity`（活动数据），`rate_source = rate_record`（排放因子），`result_semantic = emission`。
Oracle 官方还把活动数据写成 **activity data**（示例：kL 燃油 × 能量密度），即**量纲换算（kL → GJ）被显式写在活动数据的组装里**。

**B2. ★★ 关键发现：排放因子有一条 5 级 precedence 链——与 Oracle 自己的定价 Precedence 完全同构**【确定】

Oracle 明确写出的因子取值优先级：

```
Item specific（按物料）
  > Supplier specific（按供应商）
    > Organization specific（按组织）
      > Government — location specific（政府·按地点）
        > Government — universal（政府·通用）
```

> "The decision regarding which factor to apply is done within the application based on the above order."

**这条链的意义**：它证明 **"按 specificity 逐级覆盖、首个命中获胜"不是定价独有，而是 Oracle 跨域复用的统一消解机制**——在 Oracle 定价域叫 `Precedence`（§3.1.2 B 段），在碳域叫"因子适用性判定"。**与平台既有 `MetaDefaultRule` + `default_by_priority`（§5.1）逐字同构。**
另还有 `Location Specific Emission Factor Selection` profile option（按地点选因子开关）。

**B3. 碳域的"率来源分类"远比定价域细**【确定】

Oracle 列出算排放的**四种因子来源**：① 物料直接监测的排放（**Scope 1 专用**）；② 供应商特定因子；③ 组织特定因子；④ 政府因子（分"按地点"与"通用"两档）。
另：`Emission Calculation API` 用**组织级预置公式（seeded formulas）** 计算——**公式载体在碳域同样存在**。

**B4. 事实数据入口有 4 条（印证 §4.8"事实源 ≠ 订单条件记录"）**【确定】
Payables **AP Invoice** 录入 / Inventory **Miscellaneous Transaction**（发料到资产）/ **Web ADI** 批量上传 / Environmental Transaction Batches 手工录入。

**B5. OFS Climate Change Analytics（银行碳）：GWP 二次乘数 + 因子库层级**【确定】

- **GWP（Global Warming Potential，100 年）**：按 **IPCC AR4 / AR5 / AR6** 把各气体折算成 **CO2-e** → **这是串联的第二次"量 × 率"**：`气体量 × GWP = 碳当量`。→ 印证 B1 的"量纲 / 换算层"必须存在。
- **预置 6 个排放因子数据库来源，且以层级树（hierarchies）形式预置**：**UNFCC / DEFRA / EPA / GHG Protocol / PCAF / IFI**。
- **Scope × 活动类型二维矩阵**：Scope 1 = Fuels / Refrigerants / Owned Transportation；Scope 2 = Electricity / Heat and Steam / District Cooling；Scope 3 = **17 类**（Purchased goods and services、Capital goods、Upstream transportation…）。

**B6. EPM for Sustainability：碳计算器建在 Planning 引擎上（★ 反证，见 §4.9F）**【确定】

- 含**预构建 KPI / 度量 / 碳计算器（Carbon Calculator）/ 输入模板 / 仪表板**；碳计算器 = 用户选一组"控制因素"后**生成范围状况、报告数据与输出度量**；
- 仪表板按 **Scope 1 / 2 / 3** 组织，可下钻；底层由 **EPM 引擎**驱动；
- 官方声明："EPM for Sustainability 是一个**可配置的配置型 Planning 应用程序**"，而非标准 Planning 模块。

#### C. 逐轴检验：v1.3 三轴在 Oracle 跨域下是否成立

| 轴（Spec v1.3） | Oracle 定价域 | Oracle 成本域 | Oracle 碳域 | 判定 |
|---|---|---|---|---|
| **① `base_source`**（计算基来源，落在 `pricing_step`） | 定价数量 | **资源消耗量（hours）/ 采购数量 / scaled quantity** | **activity data（KWh / kL / 吨）** | **✅ 成立**——三域全是"某物 × 某率"。**唯一补充**：成本域的 `scaled quantity`（归一化除数）当前枚举无对应值 → 建议补 `scaled_quantity` |
| **② `rate_source`**（率载体，落在 `pricing_procedure`/条件类型） | 价目行 / 外部报价 | **资源费率 / 间接费率 / 买价 / 转移价** | **排放因子（5 级 precedence + 6 库层级）/ 预置公式** | **✅ 成立且三值够用**——B3 的 4 类来源、B2 的 5 级覆盖、OFS 的 6 库层级，**本质都是 `rate_record` 的 `lookup_sequence`（逐级首个命中）+ `rate_type` 细分**，不需要新的 `rate_source` 取值 |
| **③ `result_semantic`**（结果语义，落在 `pricing_procedure`） | price | cost | emission（**且必带 Scope + 气体类型两个副维度**） | **✅ 主语义成立；⚠️ 副维度需承载**——碳的结果是三元组 `(scope, 气体类型, 总量)`，但 Oracle 自己的做法也是**用并列字段**（`Emission Scope` + `Emission Type` + Ledger 行）承载，**不是复合语义** → **`result_semantic` 保持单值，不扩** |

#### D. 三条 v1.3 未覆盖的维度（本轮新增缺口）

**D1. ★ 权重分配（weighted allocation）——第四种消解范式，本轮唯一"强烈建议本期补"的项**

- **证据**：Oracle 内部至少三处用"多候选**全部参与**、按权重加权求和"：Sourcing Rule allocation%（§4.9A3）、工单 `Cost Factor Allocation`、LCM `Charge Basis = % of item price`。
- **与现有三种范式的区别**：

| 范式 | 候选处理 | 平台现状 |
|---|---|---|
| `exclusive`（互斥组） | 组内**取一** | `exclusion_group` ✅ |
| `precedence`（优先级） | 按优先级**取一** | `lookup_sequence` + 首个命中 ✅ |
| `best`（取优） | 按度量**取一** | 待定（D3 拍板口径）|
| **weighted（权重分配）** | **全部参与，按权重分摊** | **✗ 缺口** |

- **建议**：`condition_record`（→`rate_record`）加 **`allocation_weight`（数值，可空）**——**非空即"该候选参与加权累加"，而非参与"取一"**。语义极简、与现有表结构同层，且它是 §4.7D `allocation_rule.basis` 的**对偶**：两者是同一数学形式的两个方向——

| 对象 | 方向 |
|---|---|
| **`allocation_rule`**（§4.7D） | **把一个金额摊到多行**（1 → N） |
| **`allocation_weight`**（本节新增） | **把多个率合成一个率**（N → 1） |

**D2. 单位换算 / 归一化层（conversion & normalization）——建议轻处理**

- **证据**：① 碳域量纲换算写在**活动数据组装**里（kL × 能量密度 = GJ，§4.9B1）；② 成本域 `per-unit cost = total cost ÷ scaled quantity`（§4.9A2）；③ 碳的 GWP 二次乘数（kg CH4 × GWP → CO2-e，§4.9B5）；④ 定价域 D365 `qty × price ÷ price unit`。
- **判断**：**换算不是"公式"的一部分，而是"单位声明"的一部分**——混进 `base_formula` / `params` 会让公式失去跨域复用能力（同一个"× 率"公式无法同时服务 KWh 与 GJ）。
- **建议（最小改动）**：本期**只在 `base_basis`（→`base_source`）枚举补 `scaled_quantity`（归一化除数）**；把完整的 `conversion{from_unit, to_unit, factor_expr}` 登记为 **TBD-10**，不在本期动结构。理由：碳域的量纲换算发生在**活动数据取值阶段**（属 §4.8 事实源子域，P6），不在计算过程内。

**D3. 多账簿 / 多估值基础并行——本期不做，登记 TBD**

- **证据**：Oracle 一个 Cost Organization 挂多本 Cost Book（primary / secondary / **ledgerless 模拟**），**同一批事务按不同规则同时算出多套结果**（§4.9A4）；`Cost Scenario` 支持多个 rollup 并行。
- **平台现状**：`pricing_procedure`（→`calc_procedure`）是**单实例**——一个单据一次只跑一个过程。
- **判断**：这属于**"引擎实例化 / 编排"层**，不是"过程定义"层。定价域通常只需一套；但成本 / 税 / 合并抵消场景确实需要。**本期不做**（避免把编排层塞进定价引擎），登记 **TBD-11**。

#### E. 对应到平台：新增建议清单（**建议 ≠ 已实施**，Spec v1.3 未改）

| 编号 | 建议 | 强度 | 理由 |
|---|---|---|---|
| **R-1** | `rate_record` 加 `allocation_weight`（可空）→ 支撑"权重分配"第四消解范式 | **本期建议做** | 结构同层、语义极简、补上 Oracle 用了三次的既有范式 |
| **R-2** | `base_source` 枚举补 `scaled_quantity` | **本期建议做** | 一行枚举值，消除"归一化除数无处安放" |
| **R-3** | 完整 `conversion{from_unit, to_unit, factor_expr}` 对象 | 登记 **TBD-10**，后置 | 换算属事实源取值阶段（P6），不在本期 |
| **R-4** | 多账簿 / 多估值基础并行 | 登记 **TBD-11**，不做 | 属编排层，非定价引擎自身 |
| **R-5** | `rate_source` 保持三值、**不扩** | **明确不做** | Oracle 的 4 类因子来源 / 5 级 precedence / 6 库层级，本质都是 `lookup_sequence` + `rate_type` 细分 |
| **R-6** | `result_semantic` 保持单值、**不扩** | **明确不做** | Oracle 自己也用并列字段承载 Scope / 气体类型，非复合语义 |

#### F. ★ 本节最重要的一条：一条**反证**——Oracle 自己也不通用

> 前七期的隐含假设是"元模型应通用，实例参数化"。本节的对撞结果是：**Oracle 作为全球最完整的套装厂商，恰恰没有做"一个通用计算引擎 + 多域实例化"**——
> - **定价**在 **Fusion Pricing**（OM 域）；
> - **成本**在 **SCM Cost Management / Cost Accounting**（SCN 域），连"卷积"与"核算/差异/期间"都分属两套应用；
> - **碳**在 **EAR**（EBS 域，做因子 × 活动数据 + 环境台账）与 **EPM for Sustainability**（**建在 Planning 引擎上**，做碳计算器 / 范围状况 / CSRD 披露）与 **OFS Climate Change Analytics**（GWP + 因子库层级）。

**这产生两条结论：**

**F1. 印证并加强 D7 / N9（Spec 侧）**——Oracle 的做法恰恰说明**"域特有逻辑"很厚**：成本归集层（成本对象 / 成本要素 → 科目映射 / 成本期间与截止日 / 差异分析 / WIP 余额 / 成本簿挂总账）、碳的组织边界与合并层（Scope 归集 / 抵消 / CSRD 披露）**都不可能被塞进一台通用引擎里**。
→ **对 Spec v1.3 §1.4 N9 与 §9.2「元模型通用性与命名声明」是正面印证**：本引擎只做"**因子 → 率 → 逐层累加 → 结果**"这一层，**不改表结构**、仅**参数化三轴**，剩下的交回各域。

**F2. 但通用性仍有可做空间——反哺 3 处（这三条是 Oracle 没做、而本平台可做的）**：

| # | Oracle 的做法 | 平台可做的增量（相对 Oracle） |
|---|---|---|
| 1 | **三套引擎 = 三套独立元模型**（`Charge` / `Cost Component` / `Environmental Ledger` 三套结果结构） | **一张 `pricing_result` + 一张 `pricing_step`（→`calc_result` / `calc_detail`）承载三域结果**，靠 `result_semantic` 区分语义——**Oracle 尚未做到的统一** |
| 2 | 碳的 **6 个因子库 / 5 级 precedence** 硬编码在应用内 | 因子目录 + `lookup_sequence` **可配**，因子库按数据接入而非按应用内置 |
| 3 | 碳结果按 Scope / 气体类型**分列**且**无统一回放** | `pricing_result` 天然带 `level` / `rate_type` / `base_basis` / `rolling` / `sequence` → **可回放**，跨域同构 |

#### G. 落回决策清单（新增 3 项，见 §8 D18–D20）

- **D18**：是否补**第四消解范式 `weighted`（权重分配）**？（研究稿建议：**补**，落 `rate_record.allocation_weight`）
- **D19**：**单位换算 / 归一化**放哪一层？（研究稿建议：**归事实源取值阶段**，本期只补 `scaled_quantity` 枚举，完整 `conversion` 后置 TBD-10）
- **D20**：**多账簿 / 多估值基础并行**是否纳入？（研究稿建议：**不纳入**，属编排层，登记 TBD-11）

> **本节对 D7 的影响**：D7 拍板"只做定价、元模型按通用确定设计"**不变**；本节只是把"通用确定"从**六家定价域的横向趋同**，扩展为**同厂商跨三域的纵向验证**，并把"通用到什么程度、什么坚决不做"从**推断**升级为**有官方文档支撑的边界**。

### 4.10 九期深化：Palantir 视角——**第三条通用化路径**（对象图 + 行为附着），以及"无定价引擎"的事实

> **为何研究 Palantir**：前八期的六家（SAP / Oracle / SF / D365 / Odoo / 金蝶）都是 **"业务套件 + 预置引擎"** 路线——它们各自造一套**贴合本域的元模型**，靠"加字段 / 加条件类型"来扩域。**Palantir 是唯一一家不卖预置业务套件的厂商**，它卖的是**通用对象层（Ontology）**。因此它是检验"对象模型通用性"的**最佳对照组**——**如果连 Palantir 都不做定价引擎，说明了什么？**
>
> **核心发现预告**：① Palantir **没有产品化的定价引擎**【确定】——但它的 **Action Type** 与我们的"计算过程 + 结果 + 调整"**高度同构**；② 它走了**与六家完全不同的第三条通用化路径**——**"统一对象图 + 行为附着"**，而非"元模型 + 参数化"；③ 它给我们一条**独立的外部印证**：`Object Type` / `Property` / `Link` / `Action Type` / `Function` / `Interface` 六元组，**与我们的"业务对象 + 字段目录 + 关联 + 定价过程 + 规则 + 条件表"逐项对得上**，甚至我们的**字段目录**比它多一层。

#### A. Palantir Ontology 的六元组【确定】

官方对 Ontology 的定位（原文直译）：

> "Ontology 是组织的**运营层**，位于平台内已集成的数字资产（datasets / virtual tables / models）之上，把它们连接到其**真实世界对应物**——从工厂、设备、产品这类**物理资产**，到客户订单、财务交易这类**概念**。在许多场景下，Ontology 是组织的**数字孪生**，同时包含**语义元素（objects, properties, links）**与**动力元素（actions, functions, dynamic security）**。"

| 元素 | 职责（官方定义要点） | 我们的对应物 | 差异 |
|---|---|---|---|
| **Object Type** | 真实实体 / 事件的 schema 定义；带**主键（primary key）**与**标题键（title key）**；由**元数据源（backing datasource）**映射列自动生成属性 | **业务对象**（`sales_order` 等）+ 字段 | 我们的对象是**轻量宿主**（只挂业务身份）；它是**本体的一等公民** |
| **Property** | 对象特征；类型受限（primitive / 日期 / 引用 / 数组…）；数组属性在 TS v1 侧为 `ReadOnlyArray`（**修改须整值替换**） | **字段目录**的 `field_catalog` | 我们的目录含**事实源分类（`source_type`）**（§4.8D①），它**没有**——我们多一层 |
| **Link Type** | 对象间关系，支持 **1:1 / 1:n / n:n**；遍历开销需注意（后端加载链接） | 对象关联 / 引用 | 它是**显式一等对象**（可遍历、可反查） |
| **Interface** | "描述对象类型**及其能力**的抽象类型，提供**对象类型多态**" | **无直接对应** | ★ 平台缺"接口 / 能力抽象"层（见 §4.10D3） |
| **Action Type** | "一次**事务**，基于用户定义逻辑改变一个或多个对象的属性"；含**参数定义 + 规则 + 副作用 + 提交条件 + 校验**；**同一套 Action 逻辑与校验可跨所有前端应用复用** | **定价过程** + **调整**（`pricing_adjustment`）+ 触发/校验 | 它是**"动作"的一等抽象**，我们把"算价"与"调价"都塞在定价过程里 |
| **Function** | "服务端业务逻辑"，**一等支持读对象属性、遍历链接、灵活编辑 Ontology**；语言 **TypeScript / Python** | 表达式 / 公式引擎（`SafeExpressionEvaluator`） | 它的公式是**可编程的通用程序**，不是受限 DSL |

> ★ **注意这条官方定位**："Ontology **不是**语义层（**not a semantic layer**）。Ontology 的设计目的是通过 **data / logic / action / security 四重集成**表达企业复杂的、互联的**决策**。"
> → **它明确拒绝了"只做语义映射"的定位**，坚持把**逻辑与动作放在同一层**。这与我们的判断一致（`MetaDefaultRule` 也是"元数据 + 行为"合一）。

#### B. ★ Action Type = 我们的"计算过程 + 结果 + 调整"，逐项对撞【确定】

官方定义的结构（`action types` 文档原文直译）：

```
Action Type
 ├─ Parameters        （参数定义，含类型化入参表单；object reference / object set）
 ├─ Rules             （把参数转成 Ontology 编辑的逻辑；12 类规则）
 ├─ Submission criteria（提交条件）
 ├─ Validation       （谁有权执行，如"仅 HR 员工可改角色"）
 └─ Side effects     （通知新旧 manager 等）
        ↓ 提交
    一次事务 → 提交到 Ontology → 反映到所有前端应用
        ↓
    携带用户编辑的最新对象数据 → object type 的 writeback dataset
```

**12 类规则**（全部【确定】，官方列举）：Create object / Modify object(s) / Create or modify object(s) / Delete object(s) / Create link(s) / Delete link / **Function rule** / Create object(s) of interface / Modify object(s) of interface / Delete object(s) of interface / Create link(s) on object(s) of interface / Delete link(s) on object(s) of interface。

**逐项对撞**：

| Action Type 机制 | 我们的对应 | 差异 / 启示 |
|---|---|---|
| **Parameters**（类型化入参） | `pricing_procedure` 的触发上下文 + `pricing_condition` 的字段引用 | 它参数是**强类型 + 表单化**的；我们的条件字段是**字符串引用** |
| **Rules**（12 类编辑动作，声明式配置） | `pricing_step`（计算步骤）+ `pricing_result`（结果行） | 它把"编辑什么"枚举死了（增删改对象/链接）；我们的步骤是"算什么" |
| **Validation / Submission criteria** | 无 | ★ **平台缺"谁能改价 / 何时可重算"的策略位**（见 D21） |
| **Side effects**（通知等） | 无 | ★ 平台缺副作用位（可后置） |
| **一次事务** | `pricing_result` 落库事务 | 一致 |
| **writeback dataset**（携带用户编辑的最新数据） | `fact_snapshot`（§4.8D②） | ★ **同一个模式**：改动要进"权威数据集"，而非散落各表 |
| **Function rule**："引用一个 Ontology 编辑函数，其输入由 action 的参数派生。**存在此规则时，不得配置其他规则**，因为函数代码本身已能处理其他规则能做的一切" | — | ★★ **Palantir 把"配置化"与"代码化"当成二选一**，见 §4.10C |

#### C. ★★ 最重要的架构发现：Palantir 走的是**第三条通用化路径**，且它主动拒绝了"定价引擎"

**C1. 三条路径的对照**

| 路径 | 代表 | 通用化方式 | 域特有逻辑的安置 |
|---|---|---|---|
| **路径① 元模型 + 参数化**（本引擎所走） | SAP / Oracle / SF / D365 | 定义**一套中立元模型**，靠**加字段 / 加条件类型 / 加枚举**扩域 | 塞进同一元模型（→ 故有 §4.9F 的"三套独立结果结构"问题） |
| **路径② 通用对象图 + 行为附着**（Palantir） | Palantir Foundry | 定义**通用对象层**（对象 / 属性 / 链接 / 接口），**行为作为 Action Type / Function 附着其上** | **不预置**——由 FDE / AIP 按客户场景现搭 |
| **路径③ 套件内建** | Odoo / 金蝶 | 域内做**半通用**（标准 vs 旗舰分版本） | 域内固化 |

**C2. Palantir 明确"不预置业务域"**——官方文档只有 use case 示例（`use-case-examples`），无任何"定价模块 / 成本模块 / 碳模块"产品化文档。
- 化工行业用例 **"Drive revenue with integrated pricing"**：Palantir 官方把它定位为 **use case（用例）** 而非产品，流程是——Sales 在 **Microsoft Dynamics** 提报价请求 → 每 5 分钟经 **Magritte REST 插件**同步到 Foundry → Marketing 经理在 **Quiver 分析**里看"相似机会的历史量价成本毛利 + 前瞻成本估算（未来材料价 + BOM）"→ 人工给出建议价 → **经 Webhook 写回 Dynamics**。
- → **定价计算本身在 Dynamics 侧，Palantir 只做"上下文汇聚 + 决策 + 写回"**。
- 零售用例同构：官方措辞是"Foundry **建议**最优价，**让人可以**按业务输入修改价格"（suggests the best price… **letting humans modify**）。

**C3. 成本侧同理，但更"模型化"而非"引擎化"**——`Optimize COGS` / `Bill of Material` 用例：
- 整合 **7+ 套 ERP** 建供应链数字孪生；用 **out-of-the-box BOM workflow** 优化 COGS 与采购；
- 核心是 **granular COGS / profitability model**，答案形态是"**SKU 级毛利分析 + 机会告警**"，且强调"规则可由业务用户用 low-code 定义"（另一用例）；
- → 官方表述始终是 **model / workflow / optimization**，**不是 engine**。

**C4. AIP Logic：把"逻辑"也交给 LLM 编排**【确定】
`AIP Logic` 是**无代码 LLM 函数环境**：输入（primitive 或对象类型）→ **块**（创建变量 / 取对象属性 / **用 LLM** / 变换块 / **Apply Action**（确定性调 Action，绕过 LLM）/ **Execute**（确定性调函数））→ 输出。块可链式前馈，**可嵌函数、可单元测试、可被 Automate 触发**。
- **重要限制**（官方明写）："**必须**从 Action 调用 Logic 函数，Ontology 才会被编辑；即使函数里含 Apply Action 块，**不经 Action 执行则不会写入**"。
- → **可编程性不等于可变性**：能力仍在 Action 这道"受控门"后。**这条与我们的"规则不可绕过元模型"是同一条设计原则。**

**C5. 由此得到本节最锋利的一条结论**

> ★ **两条"通用化路径"的真正分野，不在能力，在"谁承担域特有逻辑"**：
> - **六家**把域特有逻辑**沉进元模型**（加条件类型、加字段），换取"开箱即用"；
> - **Palantir** 拒绝沉下去，改为**通用对象层 + 现搭行为**，换取"跨域零妥协"。
>
> **对本引擎的含义**：我们走的是路径①，**所以"域特有逻辑"的压力必然落在本引擎身上**——这正是 §4.9F 与本节共同指向的同一件事：**引擎边界必须写死**（N9）。而 Palantir 的做法给了一条**替代解**：**若某域特有逻辑实在装不下，就把它变成"接口 + 现搭行为"，而不是继续加枚举**。

#### D. 三条可落地的观察（对平台）

**D1. ✅ 印证：`field_catalog` 比 Palantir 多一层，是合理增量**
Palantir 的 Property 只有"类型"；我们有 **`source_type ∈ {static, master, quality, measurement, market}`**（§4.8D①）。
→ **不需要向 Palantir 对齐，反而印证 §4.8D① 的设计是对的**：Palantir 缺"事实源分类"，因为它**没有"按计量结果重算"这个业务诉求**（它的对象属性多为同步进来的既有数据）。**我们有，所以必须多这一层。**

**D2. ★ 值得考虑：给定价结果对象补 `interface`（能力抽象）**
Palantir 的 Interface 提供**对象类型多态**：统一描述"有哪些对象类型具备这个能力"。这对我们的意义：
- 若将来**成本 / 碳 / 税**要挂到本引擎，**四种域结果都满足"可挂单据 · 有明细 · 可回放"这组能力** → 可声明一个接口（如 `PricedDocumentResult`），而**不必让四种域共用一张表**。
- 这是一条**比"硬塞进同一张表"更保守、也更贴近 Palantir** 的路子。**建议本期不做**（只有一个域），登记 **TBD-12**。

**D3. ★ 值得考虑：定价过程补两个策略位（Validation / Submission criteria）**
Palantir 的 Action Type 自带**谁能执行**（"仅 HR 员工可改角色"）与**何时可提交**。我们的 `pricing_procedure` 目前**只有"何时触发"的策略位（IF-001）**，缺**"谁能改价"**。
- 定价场景的真实诉求：**销售能否手工改价？改价是否需审批？改价是否留痕？**——这在 ERP 里普遍存在（Oracle 的人工覆盖需 `override_reason`，§3.1.4）。
- **建议：本期只补"改价必填原因"这一条最小约束**（可归入现有调整 `pricing_adjustment`），完整的权限 / 审批矩阵登记 **TBD-13**。

#### E. 落回决策清单（新增 2 项，见 §8 D21–D22）

- **D21**：是否给定价结果补**能力接口（interface）**？（研究稿建议：**本期不做**，登记 TBD-12——只有一个域，多态无收益；将来多域时它是比"共用一张表"更保守的选项）
- **D22**：是否给定价过程补**"谁能改价"的策略位**？（研究稿建议：**本期只补最小一条"改价必填原因"**，完整权限 / 审批矩阵登记 TBD-13）

> **本节对 D7 的影响**：**不变**。本节的增量是**一条独立的第三条路径证据**——说明"通用化"有两种做法，我们选的是"元模型 + 参数化"，代价是**必须自己扛域特有逻辑**，因此 N9 的边界不是保守，而是**这条路径的必要成本**。

---

## 5. 与平台既有资产的关系与边界（防重复造轮子）

### 5.1 能复用的四件资产（代码级核实）

| 资产 | 位置 | 可复用点 | 复用方式 |
|---|---|---|---|
| **条件表达式内核** | `meta/core/condition_parser.py` / `condition_evaluator.py` / `condition_converter.py` | 因子的"相等/区间/属于集合/表达式"判定 | 直接复用；定价的"适用条件"就是条件表达式 |
| **分组 + 首个命中 + tie-break** | `meta/core/rule_executor.py`（`default_by_priority` 分组首个命中，L1432 起）与 `MetaDefaultRule`（`meta/core/models.py` L224-270） | **exclusive 范式**已经实现 | 存取序列的"首个命中"可直接借用其语义 |
| **安全表达式求值** | `meta/core/safe_expr_evaluator.py` + `FormulaFunctionRegistry`（`rule_executor.py` L229-230） | 公式 / 百分比 / 定额的计算求值 | 定价的"计算类型=公式"复用 |
| **值计算的宿主** | `MetaComputation`（`models.py` L207-221，`formula` / `target_field` / `compute_on_change`） | "字段 = 表达式"的落点 | 承接"定价过程的小计行" |

### 5.2 须显式划界的六条边界（勿混）

| 界别 | 它回答什么 | 归谁 | 为什么不能混 |
|---|---|---|---|
| **定价 vs 属性确定 `default`** | 前者"金额怎么算出来"；后者"填哪个价目表/付款条件" | 定价引擎 / `MetaDefaultRule` | `default` 能确定 `price_list=PL_ZOR`，但算不出 `PL_ZOR` 里的价。**选价目表 ≠ 算价格** |
| **定价 vs 计算 `compute`** | 前者"多层累加 + 多候选取优 + 条件记录命中"；后者"无条件表达式覆盖一个字段" | 定价引擎 / `MetaComputation` | `compute` 能做 `total = qty × unit_price` 这类**尾算**，做不了 `unit_price` **怎么来** |
| **定价 vs 汇总 rollup** | 前者含"**过程内**按组聚合（SF Aggregate Price，不跨单据）"；后者"**跨行/跨单据层级**把子行金额 SUM 到父（守恒）" | 定价引擎 / 聚合（`analytical_engine` `AGGREGATION_SQL`、`count_children`） | 与分摊同一判据：**过程内属定价，跨单据层级守恒归 rollup**；rollup 的输入是"已算好的金额"，不是"算金额" |
| **定价 vs 分摊 allocation（★ v1.4 重定判据）** | ① **定价过程内的一步**（头→行折扣分摊、跨行派生价、按组聚合——**即使守恒、即使跨行**）**归定价**；② **过程之外的独立分摊**（把已算好的成本/费用**跨单据、跨期间**搬运，无价格语义）归 allocation | 定价引擎 / 待建分摊 | 判据 = "**是否作为定价过程的一步**"，**不是"是否守恒"**：SF **Discount Distribution Service** 把**头级折扣摊到行（守恒）**却仍是过程内 Element。v1.3 曾用"跨单据守恒"作判据，**不准确**，v1.4 已修正（§4.4 启示 4、§8 D13）。★ v1.7 再细化（§4.7E）：② 拆两档——**"费用摊到业务单据行（有价格语义）"归定价的"费用 / 分摊"子域**；**纯财务口径的跨期间 / 跨成本中心分摊仍归 allocation**。判据升级为"**是否有'可分摊到一个业务单据行'的价格 / 费用语义**" |
| **定价 vs 校验 `validation`** | 前者"算出净价"；后者"净价不得低于限价" | 定价引擎 / `MetaValidation` | 金蝶"最低限价"、`discount_rate > 0.15` 都是**定价之后的校验**，不属定价 |
| **定价 vs 单据复制 `doc_flow`** | 前者"重新算价"；后者"把源单的价 field_map 一对一搬过来" | 定价引擎 / `doc_flow_rule`（`doc_flow_derive_engine.py` L196-287，`field_map` 一对一） | 复制是**搬运**，重定价是**重算**；两者要显式二选一。★ v1.6：`doc_flow` **搬的是结果字段（`unit_price` / `net_price`），不搬定价明细**——明细在下游单据重新生成或引用（§4.6B）|

> **划界条款**：**定价引擎只负责"一条可配置的计算序列，把一组因子算成一个金额（及小计明细），含过程内的派生 / 汇总 / 分摊"**；**选源（`default`）、过程外跨单据成本费用分摊（`allocation`）、限价校验（`validation`）、单据复制（`doc_flow`）仍归各自的引擎**。★ v1.4 统一为**一条判据**——"**是否在定价过程内**"：**在过程内**（哪怕守恒、跨行）→ 定价；**过程外** → 归各自的引擎（§4.4 启示 4）。★ v1.7 再细化两档（§4.7E）：**过程外但"费用摊到业务单据行"（有价格语义）→ 归定价的"费用 / 分摊"子域（`pricing_result` + `allocation_rule`）**；**纯财务口径分摊 → allocation**。

### 5.3 平台当前能力天花板一句话

> 平台现在能回答"**这条单用哪张价目表**"（`MetaDefaultRule`）、"**总额 = 数量 × 单价**"（`MetaComputation`），**不能回答"这张价目表里这个客户这个物料的价格是多少、又叠了哪些折扣"**（无定价引擎）。

---

## 6. 差距分析

对照 §4 六个必备件，平台缺口如下（★ = 建议首期必做）：

| # | 缺失构件 | 现状 | 缺口性质 | 建议 P |
|---|---|---|---|---|
| 1 | **价目表 + 价目行（条件记录）** ★ | 无（只有普通 `unit_price` 字段） | 数据模型缺口：键 + 值 + 有效期 + 币种 + 阶梯 | **P1** |
| 2 | **条件类型（含计算类型/条件类/±/舍入）** ★ | 无 | 元模型缺口 | **P1** |
| 3 | **存取序列（含 Exclusive 开关）** ★ | 有"首个命中"，无"继续累加" | 语义缺口：**additive 未实现** | **P1** |
| 4 | **定价过程（可配置计算序列 + 小计）** ★ | `compute` 仅单表达式，无序列概念 | 引擎缺口 | **P2** |
| 5 | **取优/互斥（Precedence vs Best Price + 排斥组）** | 无 | 冲突消解缺口 | **P3** |
| 6 | **阶梯 + 有效期** | 无 | 条件记录属性缺口 | **P4** |
| 7 | **条件更新（累计已用量）** | 无 | 高级缺口（合同量用满失效） | **P4（可后置）** |
| 8 | **可解释回放（定价明细）** ★ | 仅规则判定日志雏形 | 可观测缺口 §3.1.2/§3.1.6 | **P2（与序列同批）** |
| 9 | **扩展点（VOFM 式例程）** | 有 `ActionType.BUSINESS` hook | 逃生门已具备，需接线 | **P5** |

> **与上位文档的一致性**：§2.2 的四条复杂性（多层累加 / 互斥 vs 累加 / 冲突取优 / 值类型多样）在本表分别对应 **#4 / #3+#5 / #5 / #2**，全部落在"独立引擎"内，**没有一条能用现有规则表消化**——佐证"独立引擎"的判定。

### 6.1 二期起逐期新增：依赖主数据 / 配置对象 / 元模型细化的缺口（§4.2–§4.8 引出）

§4.2 的全景清单显示，"六个必备件"之外还有一批**依赖对象**在平台缺失——它们**不属定价引擎**，但引擎一旦开跑就必须能引用到；§4.4 深挖又暴露两处**元模型细化项**（#17/#18）；四期至七期深化（§4.5–§4.8）又陆续加出 **#19–#27**（执行期重算 / 结果对象 / 费用分摊 / 事实源），一并列入：

| # | 缺失依赖 | 现状 | 归属 | 建议 P |
|---|---|---|---|---|
| 10 | **条件表 + 字段目录**（键 = 因子组合） | 无 | foundation / 定价元模型 | **P0（与条件类型同批）** |
| 11 | **币种主数据** | 仅 `enum_type_id: currency` 枚举引用，无主数据表 | foundation · 货币 | **P0（先补主数据）** |
| 12 | **汇率** | 无 | foundation · 货币 | **P1（跨币种取价前）** |
| 13 | **税码 / 税率 / 税分类** | 无 | foundation · 税务 | **P2（税条件类型前）** |
| 14 | **客户价格组 / 客户定价过程** | 无 | 客户主数据扩展 | **P1（折扣组取价前）** |
| 15 | **物料价格组 / 税分类 / 参考物料** | 无 | 物料主数据扩展 | **P1（物料组取价前）** |
| 16 | **销售区域（销售组织+分销渠道+产品组）细分** | 部分：`org_functions` 已有 `sales`（销售组织职能），**缺渠道 / 产品组**（★ v1.9 复证）| 组织（`org.yaml` + `org_functions`）| **P0（定价过程确定键）** |
| 17 | **基准（Base）显式建模**：`base_level` / `base_basis` / `base_step` / **`base_roll`** | 无（基准仅隐式出现在 `compute` 公式里） | 定价元模型（件④配套，§4.4 启示 2/3） | **P2（与定价过程同批）** |
| 18 | **过程步骤 = 可插拔算子**：`procedure_step.element_type` | 无（`compute` 是单表达式、无"类型"概念） | 定价元模型（件④，§4.4 启示 1） | **P2（与序列同批）** |
| 19 | **执行期重算策略**：`freeze_policy`（价/运费/税三粒度）+ `reprice_trigger` | 无 | 定价元模型（件④配套，§4.5C） | **P4（与执行期重定价同批）** |
| 20 | **数量基准来源** `qty_basis`（`order_qty` / `delivered_qty` / `goods_issued_qty` / `billed_to_date_qty`；★ v1.8 扩容：+ `dry_weight` / `net_dry_weight` / `assayed_content`，§4.8D④） | 无 | 定价元模型（件④配套，§4.5B/C） | **P4（开票接口前）** |
| 21 | **定价结果对象**：`pricing_result`（结果行，含 `level` / `document_line_id`）+ `pricing_step`（步骤明细） | 无（价仅隐式落在单据字段） | 定价元模型（件⑤/⑥的**宿主**，§4.6B） | **P2（与定价明细同批）** |
| 22 | **分摊规则对象** `allocation_rule`（`basis ∈ {equal, value, quantity, weight, volume, manual}` / `manual_factor` / `group_by` / `floor`（地板价）/ `target ∈ {cost, expense}`） | 无 | 定价元模型（**费用 / 分摊子域**，§4.7D） | **P4.5（与事后费用同批）** |
| 23 | **费用口径字段扩展**：`pricing_result` 加 `origin ∈ {planned, unplanned}` / `charge_source` / `source_document_type` + `source_document_id` / `target` / `allocation_basis` / `allocation_rule_id` | 无 | 定价元模型（件⑤宿主扩展，§4.7D） | **P4.5** |
| 24 | **追溯 / 补差对象** `pricing_adjustment`（`original_result_id` / `adjustment_type ∈ {subsequent_debit, subsequent_credit, retro_price_change, rebate_settlement, delta_accrual, provisional_settlement}`（★ v1.8 增 `provisional_settlement`，§4.8D⑤）/ `delta_amount` / `effective_period` / `posted_flag`） | 无 | 定价元模型（**费用 / 分摊子域**，§4.7D） | **P4.5（追溯调整可后置）** |
| 25 | **外部价格源 + 计价期**：`external_price_source`（`source` / `quote_code` / `calendar_id` / `fallback_rule`）+ `pricing_period`（`period_type` / `start_offset` / `end_offset` / `average_basis` / `rounding`） | 无 | 定价元模型（**事实数据子域**，§4.8D②） | **P6（可选）** |
| 26 | **结果事实源扩展**：`pricing_result` 加 `price_source ∈ {condition_record, external_quote, formula}` / `pricing_period_id` / `external_price_source_id` / **`fact_snapshot`**（本次结算用到的质检值 / 计量值 / 报价值） | 无 | 定价元模型（件⑤宿主扩展，§4.8D③） | **P6（可选）** |
| 27 | **字段目录事实源分类**：`source_type ∈ {static, master, quality, measurement, market}`——条件表可直接引用**质检 / 计量 / 外部报价**字段（与主数据字段同权） | 无（`unit_price` / `quantity` 仅 UI 定义） | 定价元模型（**件①扩展**，§4.8D①） | **P6（可选；建议先做，与 P1 条件表同批）** |
| 28 | **权重分配（第四消解范式）**：`condition_record.allocation_weight`（可空）——**非空即"该候选参与加权累加"，而非参与"取一"**；与 `allocation_rule`（1→N 摊金额）互为对偶（N→1 合率） | 无（现有 `exclusion_group` / `lookup_sequence` 均只"取一"） | 定价元模型（**件②扩展**，§4.9D1） | **P2（与定价过程同批；Oracle 内部三处使用）** |
| 29 | **归一化除数**：`base_basis` 枚举补 **`scaled_quantity`** | 无 | 定价元模型（件④配套，§4.9D2） | **P2（一行枚举值）** |
| 30 | **单位换算对象** `conversion{from_unit, to_unit, factor_expr}` | 无 | **事实源取值阶段**（非计算过程内，§4.9D2） | **后置 → TBD-10** |
| 31 | **改价必填原因**（最小版"谁能改价"策略位） | 无（`pricing_adjustment` 无 `reason` 必填约束） | 定价元模型（件⑤配套，§4.10D3） | **P2（与定价过程同批；完整权限 / 审批矩阵 → TBD-13）** |
| 32 | **结果能力接口（interface）**——声明"本结果对象具备 可挂单据 · 有明细 · 可回放 这组能力"，供多域结果多态挂载 | 无 | 跨域扩展位（§4.10D2） | **后置 → TBD-12** |

> **排序原则（用户偏好：先依赖后优先级）**：#11/#16 是 P1 单层取价的**前置键**，须先于引擎；#12/#13/#14/#15 按对应条件类型上线时补齐。**#17/#18 不是外部依赖，而是件④自身的元模型细化**——它们决定了 P2 能否把"基准"与"步骤"讲清楚，故与 P2 同批落地。**#19/#20 是文档链（执行期）细化**，单层取价与首版累加不依赖它们，随 P4 执行期重定价一并落地。**#21 是件⑤/⑥的宿主对象**（结果行 + 步骤明细挂单据，§4.6B），与 P2 的定价明细同批落地。**#22–#24 属"事后 / 计划外费用与分摊"子域**（§4.7）——依赖 #21 的结果对象与 P4 的重算策略，**随 P4.5 落地**；其中 **#24 追溯调整可后置**（红线：已过账不隐式重算）。**#25–#27 属"事实数据驱动重算"子域**（§4.8）——**P6（可选）**；其中 **#27 字段目录事实源分类**成本极低、且正对头部产品"半成品"的空白，**建议与 P1 条件表同批先行**。**#28/#29 属"跨域通用性补齐"（§4.9 跨域二次研究）**——#28（权重分配第四消解范式）与 #29（`scaled_quantity` 归一化除数）**均为 P2 同批**：前者是 Oracle 内部用了三次的既有范式、后者仅一行枚举值，二者都不引入新表、不改流程，却把"定价专属"降为"定价为首个实例"。**#30 单位换算属事实源取值阶段**（碳域 kL→GJ、定价域 price unit 换算都发生在取值侧），**不在计算过程内，本期后置为 TBD-10**。**#31 属"改价留痕与约束"**（§4.10 Palantir Action Type 的 Validation 位）——**P2 同批**（仅一条"改价必填原因"，不引新表），**完整权限 / 审批矩阵后置 TBD-13**；**#32 结果能力接口**是**跨域扩展位**，**本期不做、后置 TBD-12**（只有一个域，多态无收益；将来多域时它比"硬塞进同一张表"更保守）。

---

## 7. 建设路径（渐进式，先核心后边角）

> 原则：**小步起步、可解释先行、范式显式**。Odoo 证明"轻量完整"可行；SAP 证明"框架化"是终点。我们不一步跳到 SAP。

| 阶段 | 目标 | 交付 | 依赖/复用 | 可验证标准（DoD） |
|---|---|---|---|---|
| **P0 概念定型** | 把 §4 六件定成平台对象/枚举，并**落定条件类型为可维护配置对象（§4.1）** | 元模型草案（表 + 字段 + 枚举，含条件类/计算类型/±/舍入/排斥组） | 对象模型总纲 §9 五问；**依赖主数据盘点（§6.1 #11/#16）** | 六件各有归属对象，与 §5.2 边界不冲突；条件类型字段与 §4.1 一致 |
| **P1 单层取价** ★ | 一个物料 × 一个客户 → 一个单价 | **条件表 + 字段目录** + 价目表 + 价目行（含**币种/定价单位**）+ 存取序列（exclusive） | `condition_parser` + 首个命中语义；**依赖 #11 币种 / #16 销售区域** | 命中即止，能回答"命中哪一行"；跨币种价目行可换算 |
| **P2 多层累加 + 回放** ★ | 基价 → 折扣 → 附加费 → 税 → 运费 | 条件类型分类 + additive + **定价过程序列（步骤带 `element_type` 可插拔算子，§6.1 #18）** + **基准四字段 `base_level`/`base_basis`/`base_step`/`base_roll`（§4.3②、§6.1 #17）** + 小计 + **定价明细** + **结果对象 `pricing_result` / `pricing_step`（挂单据，§4.6B、§6.1 #21）** | `SafeExpressionEvaluator` / `FormulaFunctionRegistry`；**依赖 #13 税** | 逐层小计可回放（对标 Request Viewer）；每步记 `base_level` / `base_basis` / `base_step` / **`base_roll`**（默认不滚动；`base_roll` 与 `base_step` 互斥） |
| **P3 取优/互斥** | 多同类命中怎么收 | Precedence vs Best Price（显式选择）+ 排斥组 | — | 同一数据两范式结果可分别复现 |
| **P4 阶梯 + 有效期 + 条件更新 + 执行期重算** | 按量分档、按日期生效、合同量累计、**发货/开票时按实际量重算** | 价目行属性扩展 + 用量累计 + **`freeze_policy` / `reprice_trigger` / `qty_basis`（§6.1 #19/#20）** | `doc_flow` 交界（§4.5C）；增量重定价后置 | 阶梯/过期/用满三测例；**"搬价+订单量" / "订单价×实际量" / "实际量重取价"三组合各一测例**（§4.5B）；已开票行重定价被拒 |
| **P4.5 事后 / 计划外费用与分摊** | 把"发票 / 收货 / 服务确认 / 结算"上的**计划外费用**摊到 PO / 收货 / 订单行，并可追溯补差 | **`allocation_rule`（含 `basis` / `target`，§6.1 #22）** + **`pricing_result` 费用口径字段（#23）** + **`pricing_adjustment` 追溯 / 补差（#24，可后置）** | 依赖 P2 `pricing_result` + P4 重算策略（§4.5C 红线）；复用 `SafeExpressionEvaluator` 求值 | 一笔计划外费用能按 **6 种基数**分别摊到行且可回放；`target=cost` / `expense` 两去向各一测例；**已过账单据的追溯调整被拒或留痕**（§4.5C 红线）。★ **采购侧成本类费用本期只做对象设计、不实现**（D7 范围外） |
| **P5 扩展点接线** | 复杂定制逃生门 | `ActionType.BUSINESS` hook 接线 VOFM 式例程 | 已有 hook 骨架 | 自定义例程可插拔，不改引擎 |
| **P6 事实数据驱动重算（可选）** | **优质优价**（质检 / 特性调价）与**大宗贸易**（暂定价 → 终价、计价期均价） | **字段目录事实源分类（§6.1 #27）** + **`external_price_source` / `pricing_period`（#25）** + **`pricing_result` 事实源与 `fact_snapshot`（#26）**；`qty_basis` 扩容（干吨 / 净干重 / 金属量） | 依赖 P1 条件表（事实源字段入存取顺序）与 P4.5（`pricing_adjustment` 差值结算）；**无质检链路 / 无报价源的行业可不用** | 质检值命中条件表 → 得出升贴水；干吨折算数量参与计价；暂定价 → 终价差值可配对回放；**`fact_snapshot` 缺失时拒绝结算** |

**明确不做（非目标）**：选价目表（归 `default`）、总额尾算（归 `compute`）、**纯财务口径**的跨期间 / 跨成本中心费用分摊（归 allocation；★ v1.7 细化：**"费用摊到业务单据行"归定价的"费用 / 分摊"子域**，见 §4.7E）、限价校验（归 `validation`）、**搬运动作**（归 `doc_flow`）。★ v1.4 澄清：**定价过程内的派生 / 汇总 / 分摊（含头→行守恒分摊）属定价**，不在"不做"之列（§4.4 启示 4、§5.2 修订行）。★ v1.5 补充：**"搬价还是重算"的策略声明**属定价结果元数据（§4.5C），只有**搬运动作本身**归 `doc_flow`——下游按此策略消费。★ v1.7 声明：**采购侧（供应商 / PO）定价与成本核算不在本期范围**（D7 只做定价）——§4.7 只做**费用对象与分摊模型**的设计，`target=cost` 的取值算法（移动平均 / 标准价 / 价差）归**成本核算**。★ v1.8 声明：**期货保值 / 风险管理 / 头寸**不属定价（归 **CTRM / 风控**）；**质检本身**（检验批 / 使用决策 UD / 质量通知）归 **QMS**，定价只消费"**质检结果 → 定价输入字段**"这一层。

---

## 8. 待决策清单（需 PM/评审拍板）

| # | 决策点 | 选项 | 本报告倾向 |
|---|---|---|---|
| D1 | 独立引擎 vs 扩展 `compute` | ①独立引擎 ②扩 `MetaCompute` 加序列 | **①独立引擎**（§2.2 §6 已证四条复杂性） |
| D2 | 取数范式**默认值**（须分两层看，见 §8.1） | ①exclusive ②additive ③best price | **分层默认**：槽位内（存取序列）= **exclusive 首个命中**；步骤间（定价过程）= **additive 累加**。若要反过来用，一律显式开启 |
| D3 | 冲突消解范式（**同粒度**多候选择一） | ①只做 Precedence ②只做 Best Price ③两个都做、显式选 | **③，默认 Precedence**：可预测/可回放/成本低，且符合"合同价优先于促销价"；**Best Price 显式开启，并须先定义"最优"度量**（见 §8.1） |
| D4 | 定价结果落库形态 | ①展平到字段（unit_price/净价）②明细行（定价结果表）③两者都要 | **③**：字段供业务、明细供回放（对标 SF Waterfall + Oracle Viewer） |
| D5 | 可解释回放保留策略 | ①全量落库 ②仅最近 N 次 ③仅在"手动查看"时重算 | 待定（涉存储成本）——**但 P2 必须先有结构** |
| D6 | 是否要条件更新（累计用量） | ①要 ②先不要 | **②先不做**（P4 后置，非首期刚需） |
| D7 | 是否统一"确定引擎" | ①只做定价 ②一并做伙伴/批次/输出确定 | **✅ 已拍板（2026-10-05）：只做定价；元模型按"通用确定"设计**，为伙伴/批次/输出/文本确定留形（见 §8.2） |
| D8 | 复制时带价 vs 重定价（**v1.5 按 §4.5A 细化**） | ①默认带价（只搬运）②默认全程重定价 ③**逐"目标单据类型 × 参考单据类型"配 `price_mode` 三档**（搬运 / 按量重算金额 / 完全重定价），并**逐属性**（价·运费·税）覆盖 | **③**：SAP `KNPRS`、Oracle `Freeze Price/Shipping/Tax`、SF Repricing 三家**都是逐文档类型 × 逐属性可配**，无一用全局布尔；`doc_flow_rule` 已有逐规则配置先例。**✅ 已拍板（2026-10-05）** |
| D9 | 条件类型：配置对象 vs 硬编码枚举（§4.1） | ①配置对象 ②硬编码枚举 | **①配置对象**：六家全部如此，且与 D7"通用确定"一致；只把**计算类型**做成属性枚举 |
| D10 | 计算基准默认层级（§4.3①） | ①行级（Item）②表头级（Header）③两头都做 | **①行级为默认**（逐行取价）；**表头条件 + 组条件分摊列为 P3+**，首期不实现 |
| D11 | 基准量默认（§4.3②） | ①定价数量（qty × price unit）②单据金额 ③重量 | **①定价数量**；同时预留 `base_formula` 供价值/重量改写（与件②"计算类型=公式"共用求值器） |
| D12 | **基准是否滚动**（§4.4 启示 3） | ①默认**不滚动**（cumulative：以基价/前序步骤为**固定**基准）②默认**滚动**（cascading：以 Running Net Price 为基准） | **①默认不滚动**：可解释、金额可控（配错一条不会连带放大）；**滚动须显式开启**，开启时在明细里记 `running_net_price`。取向与 D2/D3 一致——**危险项一律显式开** |
| D13 | **过程内"派生 / 汇总 / 分摊"的归属**（§4.4 启示 4） | ①一律归 `allocation` ②**按"是否在定价过程内"切**：过程内归定价、过程外归 `allocation` | **②（v1.4 修正判据）**：判据 = **是否作为定价过程的一步**，**不是"是否守恒 / 跨单据"**——SF **Discount Distribution Service 是本过程的标准 Element**，功能即"头级折扣摊到各产品行（守恒）"，仍属定价；Oracle Spread Discount / SAP 组条件同理（§5.2 修订行） |
| D14 | **数量基准来源 `qty_basis`**（§4.5B） | ①订单量 ②**实际交货 / 发货量** ③累计已开票量 ④逐单据类型配 | **② 作开票默认**（SAP `FKMGK=D` 惯例）：贴合"按实际执行数量结算"；且**与"单价是否重取"解耦**——只换数量、不换价（SAP `D/E` + `FKMGK=D`、Oracle 21D 自动调 extended amount）。**已开票 / 已过账行禁止隐式重定价**（§4.5C 红线）。**✅ 已拍板（2026-10-05）**|
| D15 | **定价结果的对象宿主**（§4.6） | ①独立"定价单据"（与订单平级）②**附属于业务单据**（行级 `pricing_result` + 头级 `level=header` 标记 + 分摊明细 + `pricing_step` 步骤明细）③仅展平到单据行字段 | **②**：三家**无一建独立定价单据**——SAP `KNUMV` 只是头表**聚合号**、条件行仍随单据；Oracle `Charge` 挂订单行；SF 输出映射回单据行。**①会与 `doc_flow` 抢"谁是单据"**，且多一跳关联。③不够（明细要供回放，D4 已定"两者都要"）。**✅ 已拍板（2026-10-05）**|
| D16 | **事后 / 计划外费用的归属与去向**（§4.7） | ①归 **allocation**（与定价分开）②归**定价的"费用 / 分摊"子域**（复用 `pricing_result` + 新增 `allocation_rule`），去向 `target ∈ {cost, expense}` 作规则字段 ③只做"进费用"、不做"进成本" | **②**：三家一致"**不改原单价、独立费用行 + 分摊**"（Oracle 独立 acquisition cost adjustment；SAP 计划外交付成本独立行 / 独立科目）；分摊基数是**可配枚举**（Oracle LCM 6 种）、去向是**可配字段**（Oracle 计入库存成本 / SAP 按价格控制走库存价值或费用）——归 allocation 会把"**费用行摊到业务单据行**"这条**有价格语义**的链切碎。**采购侧成本类费用本期只做对象设计、不实现**（D7 范围外） |
| D17 | **事实数据驱动重算（优质优价 / 大宗）的归属与节奏**（§4.8） | ①不做——只做条件记录定价 ②**只做"事实源作为条件表字段 + 事实快照"（优质优价）**，大宗两段式后置 ③完整做（＋`external_price_source` / `pricing_period` / 暂定价结算） | **蓝图按 ③ 设计、实施按 ② 起步**（倾向；即介于选项 ② 与 ③ 之间）：D7"元模型按通用设计"要求**字段目录预留 `source_type`**（成本极低、收益大，且**头部产品此处普遍是"半成品"**——Oracle / SAP / SF 均【未找到】质检值直接改价的链路）；**大宗两段式（`provisional_settlement`）与外部报价源放 P6 可选**，视业务是否涉及大宗；**期货 / 风控 / QMS 明确不属定价** |
| D18 | **是否补第四消解范式 `weighted`（权重分配）**（§4.9D1）——多条同 rank 候选**不取一、全部按权重加权累加** | ①不补（只做 exclusive / precedence / best 三种"取一"）②**补**：`condition_record.allocation_weight`（可空），非空即参与加权累加 | **建议 ② 补**（倾向）：Oracle **内部三处**在用（Sourcing Rule allocation% / 工单 `Cost Factor Allocation` / LCM `Charge Basis = % of item price`），**是本次跨域对撞发现的唯一真实缺口**；语义极简（一个可空数值）、与现有表结构同层、**不引入新表不改流程**；且它与 `allocation_rule`（1→N 摊金额）互为对偶（N→1 合率），两者共用同一数学形式 |
| D19 | **单位换算 / 归一化放哪一层**（§4.9D2） | ①塞进 `base_formula` / `params` ②**归事实源取值阶段**，计算过程内只留 `scaled_quantity` 除数 ③做完整的 `conversion` 对象且放计算过程内 | **建议 ②**（倾向）：**换算是"单位声明"不是"公式"的一部分**——混进公式会让同一个"× 率"公式无法同时服务 KWh 与 GJ，**丧失跨域复用能力**；证据侧也一致（碳域 kL→GJ 写在活动数据组装、Oracle `per-unit cost = total ÷ scaled quantity`）；**本期只补一行枚举 `scaled_quantity`（缺口 #29），完整 `conversion` 登记 TBD-10 后置** |
| D20 | **多账簿 / 多估值基础并行是否纳入**（§4.9D3） | ①纳入本期（`pricing_procedure` 支持多实例并行）②**不纳入**，登记 TBD ③完全不考虑 | **建议 ②**（倾向）：Oracle 一个 Cost Organization 挂多本 Cost Book（primary / secondary / **ledgerless 模拟**）确实做到"同一批事务多套结果"，但这属于**"引擎实例化 / 编排"层**而非"过程定义"层；定价域通常只需一套，塞进来会让定价引擎承担编排职责；**登记 TBD-11** |
| D21 | **是否给定价结果补"能力接口（interface）"**（§4.10D2，Palantir Interface 提供对象类型多态） | ①**本期补**：给结果对象声明一组能力（可挂单据 / 有明细 / 可回放），多域结果按能力多态挂载 ②**本期不做**，登记 TBD ③不做且不登记 | **建议 ②**（倾向）：本期**只有一个域（定价）**，多态**无收益**，属"为未来付今天的复杂度"；但它是将来多域时**比"硬塞进同一张表"更保守**的选项（Palantir 已验证可行）——故**登记 TBD-12 保留，而不是否掉** |
| D22 | **是否给定价过程补"谁能改价"的策略位**（§4.10D3，Palantir Action Type 有 Validation / Submission criteria） | ①完整做权限 + 审批矩阵 ②**只补最小一条"改价必填原因"**，完整矩阵后置 ③不做 | **建议 ②**（倾向）：**"销售能否手工改价、改价要不要留痕"是定价场景的真实诉求**，且六家里普遍存在（Oracle 人工覆盖需 `override_reason`，§3.1.4）；但**完整权限 / 审批矩阵是组织级治理问题，不该由定价引擎单方面承担**（与 D19「域特有逻辑不进引擎」同源）；**最小一条不引新表、可落 `pricing_adjustment.reason` 必填**，完整矩阵 **TBD-13** |

### 8.1 D2 / D3 专业建议：**分两个粒度**看，别把"混用"警告套错层

> **首要澄清**：上位文档 §10.4 警告"**互斥 vs 累加**不要混、**Precedence vs Best Price** 二选一"，指的是**同一粒度内**不要混用范式。而定价天然有**两个粒度**，各用各的默认，**不矛盾**：

| 粒度 | 是什么 | 默认范式 | 依据 |
|---|---|---|---|
| **A · 槽位内** | 一个条件类型下、**多条候选价目行**竞争（"找哪一条价格记录"） | **exclusive（首个命中即停）** | SAP 存取序列 Exclusive 标志、Odoo 首个、金蝶"命中即止"——6 家里 5 家默认先命中 |
| **B · 槽位间** | 定价过程的**步骤序列**（基价 → 折扣 → 附加费 → 税 → 运费） | **additive（逐层累加）** | SAP 定价过程各步累加、SF Price Waterfall——不累加就算不出净价 |

**为什么 A 默认 exclusive（而非 additive/best price）**：① 结果**确定**且**可回放**（"命中第 3 行"）；② 性能最优（排序取首，无需遍历全集）；③ **避免静默累加出错**——金额类字段一旦默认累加，配错一条价目行就会多算钱，风险不可接受。

**为什么 B 必须默认 additive**：净价本身就是"多层叠加"的产物；把 B 也设成 exclusive 等于只认第一个命中，折扣/税/运费全部丢失。

**D3 为什么默认 Precedence 而非 Best Price**：
- **Precedence**：可预测、可回放（"优先级 10 胜出"）、无需遍历候选全集；商务上"**约定优先于最优**"更符合合同精神（合同价应压过促销价）。
- **Best Price**：需**遍历候选全集**，且"最优"必须先定义度量（最低净价？最大折扣？含税否？）——定义不清则结果不可解释。故**必须显式开启 + 显式定义度量**，典型用于零售/电商。
- **红线**：**绝不隐式默认 Best Price**——那会静默改变金额且无法回放。

**落到回放**：每个槽位记两样——"**命中哪一行**"+"**是否累加**"——即为可解释回放的最小骨架（对标 Oracle Request Viewer / 金蝶取价日志）。

### 8.2 D7 已拍板：只做定价，但元模型按"通用确定"设计

**决策（用户 2026-10-05 拍板）**：**首个（当前唯一）消费者只做定价**；但 §4 六个必备件一律按**通用确定（determination）**语义命名与建模，**不写死 price**。

**"通用"的具体含义（落成可执行的约束，非口号）**：

1. **命名过程无关**：用"**确定过程 Determination Procedure + 过程步骤 + 条件类型 + 条件记录 + 结果行**"这套中性名字；"定价"只是"**过程类型 = pricing**"的一个实例。
2. **骨架可共用**：伙伴/批次/输出/文本确定与定价的差异只在两处——① **结果形态**（一值 vs 一组）② **取数语义**（exclusive vs 集合）；**查找—命中—计算序列的引擎骨架完全相同**。这正是 SAP 条件技术"**一机五用**"的先例（上位文档 §3.2）。
3. **本期不实现其他过程**：只是元模型**不把门焊死**；未来加"伙伴确定"应是"新增一个过程类型 + 一张规则表"，而非改引擎。
4. **与 §5.2 边界不冲突**：通用化 **≠** 把 `default`/`compute`/**跨单据** rollup/`validation`/**过程外**分摊 都塞进定价引擎——那些仍各归其位（**过程内的派生 / 汇总 / 分摊本属定价**，见 §4.4 启示 4）。通用化只针对"**同一族（SAP 条件技术同族）的确定过程**"。

> **一句话**：**引擎按"通用确定"造，本期只装"定价"这一个过程**。

---

## 9. 证据表

| # | 结论 | 来源 | 信心 |
|---|---|---|---|
| S1 | SAP 条件技术五构件 + 事务码（V/03、V/07、V/06、VK11、V/08） | SAP SD Forum《Pricing in detail》；allabouts4hana《Pricing Procedure》 | 【确定】 |
| S2 | SAP 计算类型 A/B/C、条件类、阶梯、排斥组、舍入、组条件 | 同上 + SAP Help（V/06 条件类型维护） | 【确定】 |
| S3 | 存取顺序 Exclusive 标志 = 首个命中 vs 继续累加；Requirement 例程否决 | SAP SD Forum | 【确定】 |
| S4 | 定价过程 Step 字段（From/To、Requirement、AltCTyp、Alt 基准、Subtotal、Print） | allabouts4hana；erpgreat | 【确定】 |
| S5 | Condition Exclusion（OV31/OV32）、Condition Update（累计用满） | erpgreat《Cumulative Condition Records》 | 【确定】 |
| S6 | VOFM 例程类型（Requirement / Formula: Value/Rate/Base/Scale） | SAP VOFM 简介 | 【基本确定】 |
| S7 | Oracle EBS：Price List/Qualifier/Modifier；调整方式 Percent/Amount/Lumpsum/New price | Oracle Advanced Pricing User's Guide | 【确定】 |
| S8 | Oracle：Exclusive / cascading / Incompatibility；Precedence vs Best Price | Oracle Advanced Pricing User's Guide / Implementation Guide | 【确定】 |
| S9 | Oracle：Pricing Engine Request Viewer 可回放取数过程（含删除原因） | Oracle Advanced Pricing Implementation Guide | 【确定】 |
| S10 | Oracle Fusion：Profile/Segment/Strategy、Lists、Rules、Pricing Matrixes、Pricing Algorithms | Oracle Fusion《Administering Pricing》 | 【基本确定】 |
| S11 | Salesforce CPQ：Price Book/Entry、pricing variable/element、步骤 35、Price Waterfall | Salesforce CPQ 官方教程（Exercise 4-5 / 5-6） | 【基本确定】 |
| S12 | Salesforce Revenue Cloud：PricingProcedureResolution / PricingRecipe / PriceAdjustmentTier / ABP；Configure→Rate→Discount→Net | Salesforce RLM Developer Guide | 【基本确定】 |
| S13 | D365：Trade Agreement 优先于基价；price component 序列（10/20/25/30） | Microsoft Learn《Sales trade agreement prices》《Base price versions》 | 【确定】 |
| S14 | D365：find next=Yes→best price；=No→attribute rank；零售"数值大者先、命中即止" | Microsoft Learn《Sales trade agreement prices》《Retail price management》 | 【确定】 |
| S15 | D365：Allow Price Adjustment=No + Prevent Discount=Yes → 排他净价 | Microsoft Learn《Sales trade agreement prices》 | 【确定】 |
| S16 | Odoo：Pricelist Rules 计算方式 Fixed/Discount/Formula；基数三选一；Min Qty + 有效期；首个命中、产品级优先 | Odoo Docs《Pricelists》《POS Pricelists》 | 【确定】 |
| S17 | 金蝶：价格类型 + 取价优先级（小者先）、命中即止、无优先级取最新、仅审核态参与 | 金蝶官方帮助《销售价格管理》《如何设置优先级取价》 | 【确定】 |
| S18 | 金蝶：最低限价四级强度、按净价校验；"查看定价过程"/取价日志 | 金蝶官方帮助 / 云社区 | 【确定（限价）/ 基本确定（促销）】 |
| P1 | 平台无定价引擎，`meta/core` 13 个引擎中无定价 | 本仓 `meta/core/*engine*.py` 枚举 | 【确定】 |
| P2 | 平台无 `*pricing*` 文件；`price_list` 仅测试夹具 | 全仓文件名 + 内容检索 | 【确定】 |
| P3 | 已有可复用资产：条件内核 / 首个命中 / 安全表达式 / `MetaComputation` | `condition_parser.py`、`rule_executor.py` L1432 起、`models.py` L224-270 / L207-221 | 【确定】 |
| S19 | 条件类型**可自建**：V/06 复制相似类型再改；条件类 / 计算类型 / ± 可配 | technosap《SAP SD Pricing Procedure Overview》；CSDN《SAP·SD 后台配置》 | 【确定】 |
| S20 | 条件表 V/03：字段目录选字段生成条件表（键=因子组合）；MM 对应 M/03 | tutorialkart《Define Condition Table in SAP SD (V/03)》；guru99《Access Sequence & Condition Table》 | 【确定】 |
| S21 | 表头 vs 行条件：表头影响所有行，挂组条件按行价值分摊、不挂则全额作用每行；部分类型两头均可 | allabouts4hana《Pricing Procedure》；SAP SD 博客《Automatic pricing》 | 【确定】 |
| S22 | 条件基准：标准作用在单据数量上，可用 Condition Base Value / Scale Base 公式改写；From/To 决定基准步骤 | pdfcoffee《SAP SD VOFM Routines – Pricing Formulaes》 | 【确定】 |
| S23 | D365 阶梯两语义（整单取档 vs 逐档累进）与计算式 qty×price÷price unit；Oracle Waterfall 逐步记价；SF 7 价格点 | Microsoft Learn《D365 请求日程表功能 / 零售销售价管理》；Oracle《Pricing in the Run-Time Application》；Salesforce CPQ Price Waterfall 教程 | 【确定（D365/Oracle）/ 基本确定（SF 7 点）】 |
| S24 | Oracle Fusion 运行时对象链：Service Mapping → Pricing Profile → Pricing Segment → Strategy Assignment → Pricing Strategy → 五类 List → Algorithm | Oracle《How Profiles, Segments, and Strategies Work Together》 | 【确定】 |
| S25 | Oracle Fusion 三件可配置件：Service Mapping（输入↔实体/属性，可自定义属性）/ Pricing Matrix（条件维度→结果列，Matrix Class 限字段）/ Pricing Algorithm（有序步骤，逐步更新内存 SDO） | Oracle《How Service Mappings, Pricing Algorithms, and Matrixes Work》 | 【确定】 |
| S26 | Oracle Fusion 官方算例：$1,000 → Tier −$200 → List $800 → 折扣 10% −$100 → Net $700 → ×2 = $1,400；含重算触发点 | Oracle《How Pricing Prices Sales Orders》 | 【确定】 |
| S27 | Oracle Fusion **cascading vs cumulative**：前者以 **Running Net Price** 滚动、逐条递减；后者以 **List Price** 为固定基准、累加折扣额；两者均按**规则名升序**；**Price Element(Type=Price) + Pricing Basis(Usage=Adjustment Basis)** 把"基准"做成**一等对象** | Oracle《Create Discounts That Accumulate or Cascade》 | 【确定】 |
| S28 | Salesforce **Pricing Procedure = ExpressionSet 扩展**：底层 Decision Table/Matrix（可引用 SF 对象、需刷新）+ 可插拔 Elements；标准 **15 个价格元素 + 5 个控制元素 = 20 个 Element**（List Price / Volume / Tier / ABP / Bundle / Formula / Manual / Subscription / Proration / Price Adjustment Matrix / **Derived / Price Tracking / Aggregate / Discount Distribution** / Rounding；控制类 List Operation / List Group / Map Line Item / Assignment / Price Setting）| revenuecloud.info《Architecture》；Salesforce RLM Developer Guide | 【确定（元素清单）】 |
| S29 | Salesforce 三个外围构造：**Context**（tag↔字段）/ **Pricing Recipe**（批量刷新决策表）/ **Sales Transaction Type**（选 pricing procedure）；CPQ 价格点 = Original→List→Special→Regular→Customer→Partner→Net，可被 `ChannelDiscountsOffList__c` / `ApplyPartnerDiscountFirst__c` / `ApplyAdditionalDiscountLast__c` 改序 | revenuecloud.info；Salesforce CPQ Price Waterfall 教程 | 【基本确定（架构）/ 确定（价格点）】 |
| S30 | SF **Discount Distribution Service（DDS）是标准 Pricing Procedure 内的一个 Element**：控制折扣**跨产品行**应用，带**地板价限制** + **分摊规则决策表**，支持**等分 / 按行值比例**两种摊法 → 证明"同一单据内、跨行、守恒的头→行分摊"**属定价过程内**（据此把 D13 判据从"是否守恒"改为"**是否在过程内**"） | revenuecloud.info《Architecture》；Salesforce Revenue Cloud 认证资料（DDS 描述） | 【基本确定】 |
| S31 | Oracle Fusion **Running Net Price 是"计算过程中持续增减的单一净价累加器对象"**：cascading 以它（= 全部前序累计后的当前净价）为基准逐条递减，cumulative 以 List Price 为固定基准 → **`base_roll`（滚动）与 `base_step`（指定前序步骤）互斥** | Oracle《Create Discounts That Accumulate or Cascade》 | 【确定】 |
| S32 | Oracle EBS：不同层级（合同级 + 行级）的调整**均为 cumulative 且作用于 price list price**（示例 $1,000 − $100 − $150 = $750）→ 头级条件既可"**全额作用每行**"，也可"**挂组条件按行分摊**"，是两种模式 | Oracle Service Contracts《Adjusting Prices》（Advanced Pricing 引擎） | 【确定】 |
| S33 | SAP 单据链"**复制 vs 重算**"由 **Pricing Type（`KNPRS`，表 `TVCPF`）** 枚举控制：A=复制价组件 + 重定阶梯；**B=全新定价**；C=复制手工定价元素 + 重定其余；**D=复制价元素不变**（价格固定、不读阶梯，条件基值/值重定）；E=采纳价组件并固定值；G=复制不变 + 只重定税；H=只重定运费；I=只重定返利 → 证明"搬运 / 按量重算 / 完全重定价"是**可配策略，且可按条件类型分档** | SAP 复制控制 `VTAA`/`VTLA`/`VTFL`/`VTFA`；tutorialkart；leanx.eu（表 `TVCPF`） | 【确定】 |
| S34 | SAP **Billing Quantity Indicator（`FKMGK`）** 决定开票取哪个数量：A=订单量−已开票量；B=交货量−已开票量；C=订单量；**D=交货量**；E=收货量−已开票量；F=发票收据量−已开票量；G/H=批次量；I=采购量−已开票量 → **与 Pricing Type 正交**（`D/E` + `FKMGK=D` = "单价不动、按实际发货量算金额"） | SAP 开票复制控制（`FKMGK`）；leanx.eu | 【确定】 |
| S35 | Oracle Fusion **三个 freeze 开关**：**Freeze Price / Freeze Shipping Charge / Freeze Tax** → 头部 `CalculatePricingChargesFlag` / `CalculateShippingChargesFlag` / `CalculateTaxFlag`；**revision 时开关值必须与首次一致**；另有全局参数 **"Use Price on Imported Orders That OM Already Priced"**（Yes = 导入不重算） | Oracle《Freeze Price on Sales Orders》 | 【确定】 |
| S36 | Oracle Fusion **按实际执行量重算**：**21D** 起从履约系统捕获**实际发货数量（含第二计量单位/重量）**，OM 自动调整订单行 **extended amount**；**24C** 允许自建履约任务在**发货后、开票前**触发**重算订单总额**（`RecomputeOrderTotalsFlag`）；EBS OM 有 **`Price Line`** 行动手动重算 Selling/Extended Price | Oracle 21D / 24C What's New；26B 双计量单位例（picked 6 / 实称 34 lbs）；EBS Order Management 用户指南 | 【确定】 |
| S37 | Salesforce **Repricing Service**：`RepricingElementServiceImplementation` 对已存在订单行/资产重定价，遵守 context rule 与价目行有效期；**`enableDeltaPricing`（API v63+）** 只对变更部分（delta）重算以提速 | Salesforce《Exercise 10-1 Work with Repricing》；RLM Developer Guide | 【确定】 |
| S38 | SAP 定价结果是**随单据的"条件行"、而非独立单据**：`KONV`（新结构 `PRCD_COND`）键 = `KNUMV`（**文档条件号，存在单据头**）`+ KPOSN`（行号）`+ KSCHL`（条件类型）`+ STUNR`（步骤）`+ ZAEHK`（计数器）；`KAWRT`=条件基准、`KBETR`=费率、`KPEIN`/`KMEIN`=定价单位/单位；**`KHERK=D` 标记"头条件"**、`KNTYP`=类别（税/运费/价/成本）；单据头/行（`VBAK`/`VBAP`、`LIKP`/`LIPS`、`VBRK`/`VBRP`）以 `VBELN` 相连 | sapdatasheet.org / leanx.eu（`KONV`）；learntosap 表映射（`KONV` 主键 `KNUMV + KPOSN + KSCHL`）| 【确定】 |
| S39 | Oracle Fusion 输出 SDO = **Header / Order Line / Charge / ChargeComponent**：**`Charge` 挂订单行**（一个物料可多 Charge），`ChargeComponent` 挂 Charge 且带 `SequenceNumber` / `PriceElementCode` / `PriceElementUsageCode` / `RollupFlag` / `SkipRunningPrice` / `TaxIncludedFlag`；头上有 `CalculateTaxFlag` 控制是否算税 → **定价结果挂单据行，头只放开关** | Oracle docs《Example of How Pricing Algorithms Price Items, Part 7》《How Pricing Prices Sales Orders》（24B/24D）| 【确定】 |
| S40 | Salesforce Revenue Cloud Pricing 标准对象清单（`PriceBook2` / `PriceBookEntry` / **`PriceBookEntryDerivedPrice`** / `PriceAdjustmentSchedule` / `PriceAdjustmentTier` / `CostBook` / `ProductSellingModel` / `ContractItemPrice` 等）+ Tooling 对象 **`PricingProcedureOutputMap`**（定价输出 → 单据行字段的映射）→ **定价结果经"输出映射"写回 `QuoteLineItem` / `OrderItem`** | Salesforce《Revenue Lifecycle Management Developer Guide》v61（Salesforce Pricing Standard Objects / Tooling API Objects）| 【基本确定（对象清单确定；OutputMap 语义基本确定）】 |
| S41 | SAP **Unplanned Delivery Costs（计划外交付成本）**在 **MIRO 发票校验**抬头录入（字段 `BEZNK`）；两种处理——**按发票行分摊** or **独立 G/L 科目**（配置点 SPRO → MM → LIV → Incoming Invoice，公司代码级）；**入账去向随物料价格控制 + 库存覆盖**（移动平均价有库存→库存价值 / 标准价→价差 / 独立科目→总账费用）；**不走条件技术**（独立科目走 OBYC 事务码 `UPF`，自定义分摊走 BAdI `MRM_UDC_DISTRIBUTE`）；计划内交货成本才走 PO 条件类型 FRA1/FRA2 | ganeshsapscm《Handling Unplanned Delivery Costs》；erpgreat《Unplanned and Plan Delivery Costs》；sapdocs.info 配置指南；leanx.eu `RBINVPRNT` | 【基本确定（机制）/ 未找到（官方 Help 原文与分摊基数全清单）】 |
| S42 | SAP 事后调整**两入口**：① **MM 发票校验**的 Subsequent Debit/Credit（MIRO 顶部事务类型下拉，引用同一 PO、**不改原凭证**）；② **SD 开票更正请求**（VA01 订单类型 **RK**，参考原发票，**成对产生贷 / 借项、仅结算差额**，自动开票冻结）；**开票过账后不可改，只能 VF11 取消重建** | learntosap《Subsequent Credit (MIRO)》；guru99《Invoice Correction Request》；erpgreat《Credit and Debit Memo》 | 【基本确定】 |
| S43 | SAP **追溯定价**：定价日期 `PRSDT` 可设为过去（默认提议由 VOV8 + 复制控制决定）；**条件记录有效期变更不自动重算已过账单据**；批量重定价 = **VA05 → Edit → Mass Change → New Pricing**；单张 = **VF02 Update Pricing**；成本后更新 = 事务 **VF_VPRS / 报表 SDINVUPDR** | erpgreat《Mass Update of Condition Pricing》；stechno `SDINVUPDR`；CSDN 定价日期取值 | 【基本确定】 |
| S44 | SAP **返利**：协议 VB01/VBO1（S/4 = **WCOCO 条件合同**），条件类型 **BO01–BO05**，账码 **ERB 计提 / ERU 冲销**；**条件更新字段 `KOUPD`**（V/06 配置，表 `REBC_COND_CT` / `PRCC_COND_CT`）累计已用量并可设上限、超限失效；结算 = VB02 状态改 B 释放 → 生成返利贷项请求（G2）/ 凭证（B1）；**部分结算 + 最终结算（最终结算冲抵已结算部分）**；S/4 由 **Condition Contract Settlement** 取代，另有 **Delta Accrual** | tekslate《Rebate Process in SAP SD》；gotothings 返利协议；docsfortec `REBC_COND_CT`；Espresso Tutorials《Condition Contract Settlement》 | 【基本确定】 |
| S45 | Oracle Fusion **Landed Cost Management**：Trade Operation + **费用行 Charge** 挂 PO schedule / 收货 / 装运；**分摊基数 6 种【确定】—— Equally / Item value（采购价×数量）/ Manual allocation factor / Quantity / Volume / Weight**（另 Charge Basis = Aggregate / Per unit / % of item price / % of other charges）；**分摊去向计入物料 / 库存成本与 COGS**；**独立费用行 → 独立 acquisition cost adjustment，不改原单价**；**Retroactive Price Adjustment**（PO 价事后变 → 对未开票量回溯调整 → Cost Accounting 回写库存估值）；订单侧仅 `CalculateShippingChargesFlag` / `SkipShippingChargesFlag` 控制**是否重算**（"发货后追加运费"标准机制【未找到】） | Oracle Docs《Trade Operations》《Add Charges to a Trade Operation》《Acquisition Cost Adjustment》《Freeze Price on Sales Orders》《Example of Tax Accounting for a PO Retroactive Price Change》 | 【确定（分摊基数与机制）/ 未找到（订单侧 ad-hoc charge）】 |
| S46 | Salesforce：`PriceAdjustmentSchedule` / `PriceAdjustmentTier` 是**预先配置**的调整计划；**"下单后追加一次性费用"的专门标准机制【未找到】**——替代路径 = Cart 阶段 apply adjustment API（discount / markup / override 作用于 Opportunity/Quote/Order 行）+ 对已成交订单行 / Asset 走 **Repricing Service** | Salesforce RLM Developer Guide；《Apply pricing for items》（CPQ v55）；《Exercise 10-1 Work with Repricing》 | 【确定（对象与 Repricing）/ 未找到（ad-hoc charge 标准机制）】 |
| S47 | SAP **变式定价**：特性值经"参考特性"写入 `SDCOM-VKOND` → **`KONV-VARCOND`（变式条件键，CHAR26）**，条件表用 **`VARCOND`** 字段（条件表 **A900**、条件类型 **VA00**、表 `TVARC`）；路径 **V/03 → V/07 → V/08**；**变式定价在 SD 抬头层**；★ 我最初设想的 **`VACOND` 不存在**。**批次定价**标准做法 = 条件表放**批次号**字段（批次属性靠**分类系统类类型 023**）；**"批次分类特性值本身"当条件表字段【未找到】** | SAPinsider《Manage Your Sales with Configurable Products》；leanx `KONV`；trailsap `A900`；CSDN 批次管理 | 【基本确定 / 未找到（批次特性直接入条件表）】 |
| S48 | SAP 大宗 **CPE（Commodity Pricing Engine）**：**暂定价 → 终价**（Provisional → Final，条件齐备后）+ **差额自动生成 credit / debit memo（两段式开票）**；报价源 Platts / Reuters / LME / ICE 经 **MIC + DCS + Quotation 规则**；**F&A（Formula and Average Pricing）** 用外部报价按**计价期**算价（原 IS-OIL-DS-MAP，MM / SD 均可用，现迁 CPE，包 `OIC_MIGR`）；**Differential / Quality premium-discount / Partial quantity pricing** 为标准概念；**按品位折算数量** = Active Ingredient Batch Management + **批次特定计量单位** | saptix《Commodity Management Essentials》/《…in the Chemical Industry》；EPAM whitepaper（CPE + Aggregator Feeds）；it-definition（F&A 词汇表）；SAP Note 90764；SAPinsider（AIBM） | 【确定（F&A）/ 基本确定（其余）】 |
| S49 | SAP 采购侧**"质检结果自动改采购价"【未找到】**；现实路径 = **UD 后付款冻结** + **MIRO 后续借 / 贷记（只调金额、不调数量）** + **贷方凭证（可减数量）** + 容差 **OMR6 / OBA3** 触发发票冻结；QM 质量分只进**供应商评估 ME61** | cnblogs（QM 与 MM 集成）；VoiSAP（容差组） | 【确定（路径）/ 未找到（自动改价）】 |
| S50 | Oracle：**属性驱动定价【确定】**（item **extensible attribute / attribute group**，Domain `attribute_group.attribute:...`；可覆盖基础目录价）；**"质检值 → 定价"【未找到】**；**EBS 完整 Pricing Formulas**（`QP_Formulas`、表达式 `+ - / *` 与 NVL / SQRT / MOD、公式行 / Step、**Pricing Attribute / Numeric Constant**、Static / Dynamic）而 **Fusion 无独立 Formula 对象**；**外部报价源 + 计价期【未找到】**；**GTM / Trade Management 无 provisional → final**【未找到】，旁证 = **Landed Cost estimated → actual** + **JDE Grade & Potency Pricing** | Oracle Docs《Add Your Own Attributes to Items in Pricing》《Override Base List Price》《Seeded Formulas》《Landed Cost Management Process Guide》；JDE Grade & Potency Pricing | 【确定（属性定价 / EBS 公式）/ 未找到（质检链路、Fusion 公式、外部报价源）】 |
| S51 | Salesforce：**`AttributeBasedAdjustment`**（`AdjustmentType = Override / Percentage / Amount`，可区间 / 阶梯）+ **`PriceAdjustmentSchedule` 容器** + **`PriceAdjustmentTier`（数量阶梯：Lower / Upper Bound）** + `AttributeBasedAdjRule` / `AttributeAdjustmentCondition` + **`ProductAttributeDefinition.IsPriceImpacting`**；由 Pricing Procedure 的 *Attribute-Based Price / Attribute Discount Entries* 驱动；**暂定价 → 结算价 / 质量升贴水【未找到】**；**指数定价 = `IndexRate` + `PriceRevisionPolicy（Type = Price Index）`** | Salesforce RLM Developer Guide；《Salesforce Pricing Data Model》；《Apply pricing for items》；Gearset（部署顺序） | 【基本确定 / 未找到（质量升贴水、暂定价结算）】 |
| S52 | 金蝶**"计算策略"属定价过程内**（v1.9 复证）：流程 = 取价方案（价格来源 / 条件 / 排序）→ 取价方案组（因子归组）→ **计算策略（因子 + 公式 → 取价结果）** → 取价策略（绑单据 + 优先级 + 记录日志 + 触发取价）；官方案例把**基础价 / 变式价 / 区域价差设为计算因子、公式相加得取价结果**，且 **"查看定价过程"可追溯价格构成** → **属"过程内"的公式化因子聚合层**（非 SAP 式多步条件序列）；**该能力仅星空旗舰版 / 星瀚具备，星空标准版仅为"价目表 + 优先级取价"** | 金蝶云社区《实践案例：某整车制造企业的销售高级定价管理应用实践》《取价方案介绍》《星空旗舰版-多业务场景取价配置指导》《利润中心计算策略》 | 【基本确定】 |
| S53 | **Oracle Cost Management 官方对象链与卷积公式**：Cost Organization → **Cost Book**（primary 财务 / secondary 管理 / **ledgerless 模拟**，可"按不同规则对同一批事务同时计算"）→ **Cost Scenario**（绑 成本组织 × 成本簿，`In process` → `publish` 版本化）→ **Cost Element**（Material / Overhead 等类型，"item 成本在存货生命周期中被追踪的层级"，Cost Component 映射到 Cost Element）；**`Roll up Costs` = 总成本(固定成本工序 + 变动成本[单位资源成本 × 消耗数量]) → 单位成本 = 总成本 ÷ 缩放数量(scaled quantity)**；**Cost Accounting Distribution** 为结果分录行；**Cost Accounting Periods / Cost Cutoff Dates / 期间状态**为核算外壳 | Oracle《Using Supply Chain Cost Management》(23B/26B)《Overview of Cost Management》《Roll Up Costs》《Estimating Standard Costs》《Cost Accounting for Manufacturing Work Orders》《Define Cost Accounting》(11i)；`docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/*/fapma/` | 【确定】 |
| S54 | **★ Oracle 成本域的第四种消解范式 = 权重加权求和（多候选不取一）**：多条同 rank Sourcing Rule 并存时，官方公式 `Standard cost = (Buy cost × Buy allocation) + (Rolled-up cost from work definition × Make allocation) + (Transfer cost × Transfer allocation)`——**三条候选全部参与**；工单事务上另有 **`Cost Factor Allocation`**（官方示例：Pulp 二次产出 25% / Orange Juice 主产出 100%）；成本方法三种 = **Actual（按 receipt layer 逐层）/ Standard（当期标准）/ Perpetual Average（永续平均）**，同一批事务可挂不同 Cost Book 出多套结果；`Provisional completion` + **`Adjustment propagation`（允许完工产出反哺材料领用形成环，但传播 3 圈后强制停止；`Enforce Transaction Order` 防死锁）**；官方卷积算例 `SC_ABCDEF` 用 Labor-3 10 hours、Mach-01 5 hours，含 **10% markup 的转移成本** | Oracle《Roll Up Costs》《Example of Supply Chain Cost Rollup for Process Manufacturing》《Cost Accounting for Manufacturing Work Orders》《Using Supply Chain Cost Management》Supported Cost Methods | 【确定】 |
| S55 | **★ Oracle EAR（Environmental Accounting & Reporting）= 最干净的"量 × 率"标本**：**Emission Factor**"用于计算消耗/产生某 **Emission Source** 所产生的 **Emission Type** 数量的因子"（单位 **kg CO2-e / KWh** 或 **/ GJ**）；**Emission Source**（Purchased Electricity 等）/ **Emission Type**（CO2、CH4、N2O、HFCs、PFCs、SF6、NF3）/ **Emission Scope**（Direct = Scope 1 / Indirect = Scope 2 / 其余 = Scope 3）/ **Environmental Ledger**（结果落库）；官方算例：100,000 KWh × **0.9 kg CO2-e/KWh** = **90,000 kg CO2-e**；活动数据官方措辞为 **activity data**（示例 kL 燃油 × 能量密度，量纲换算写在活动数据组装里）；四种因子来源 = 物料直接监测（Scope 1 专用）/ 供应商特定 / 组织特定 / 政府因子（分"按地点"与"通用"两档）；`Emission Calculation API` 用**组织级预置公式（seeded formulas）**；数据入口 4 条 = **AP Invoice / Inventory Misc Transaction / Web ADI / Environmental Transaction Batches** | Oracle《Environmental Accounting and Reporting User's Guide》R12.1（Environmental Accounting Overview、Emission Calculations using Location Specific Factors、Environmental Accounting for Invoices） | 【确定】 |
| S56 | **★ 排放因子有 5 级 precedence 链，与 Oracle 自己定价域的 Precedence 同构**：`Item specific > Supplier specific > Organization specific > Government(location specific) > Government(universal)`，"应用内按上述顺序决定用哪个因子"；另 `Location Specific Emission Factor Selection` profile option 控制按地点选因子 → **证明"按 specificity 逐级覆盖 + 首个命中"是 Oracle 跨域复用的统一消解机制**，与平台 `MetaDefaultRule` + `default_by_priority` 同构 | Oracle《Environmental Accounting and Reporting User's Guide》（Environmental Accounting Overview / Setting Up Profile Options） | 【确定】 |
| S57 | **OFS Climate Change Analytics（银行碳）**：按 **IPCC GWP（100 年，AR4/AR5/AR6）** 计算各气体排放 → **串联的第二次"量 × 率"**（气体量 × GWP = CO2-e）；**预置 6 个排放因子数据库来源且以层级树（hierarchies）预置** = **UNFCC / DEFRA / EPA / GHG Protocol / PCAF / IFI**；**Scope × 活动类型二维矩阵**（Scope 1 = Fuels / Refrigerants / Owned Transportation；Scope 2 = Electricity / Heat and Steam / District Cooling；Scope 3 = 17 类） | Oracle《GHG Emissions and Classification》(OFS Financial Services Climate Change Analytics Cloud 25A) | 【确定】 |
| S58 | **EPM for Sustainability（★ Oracle 也没做通用引擎的反证）**：含预构建 KPI / 度量 / **碳计算器（Carbon Calculator）** / 输入模板 / 仪表板；碳计算器 = 用户选一组"控制因素"后生成范围状况、报告数据与输出度量；仪表板按 **Scope 1/2/3** 组织可下钻；**底层由 EPM（Planning）引擎驱动**；官方声明其为"**可配置的配置型 Planning 应用程序**"而非标准 Planning 模块 → **碳计算不在定价引擎内，而在 Planning 引擎内** | Oracle《EPM for Sustainability》模块文档（`docs.oracle.com/cloud/help/zh_CN/pbcs_common/EPBCA/esg_about.htm`） | 【确定】 |
| S59 | **★ Palantir Ontology 六元组与"它不是语义层"**：Ontology 是"组织的**运营层**"，位于 datasets / virtual tables / models 之上并映射到真实世界对应物（物理资产 → 概念），"在许多场景下是组织的**数字孪生**"，含**语义元素（objects, properties, links）**与**动力元素（actions, functions, dynamic security）**；**明确声明"Ontology 不是语义层"**，其设计目的是通过 **data / logic / action / security 四重集成**表达企业复杂的、互联的**决策**；六元组 = **Object types**（schema 定义，含 primary key / title key，由 backing datasource 列自动生成属性）/ **Link types**（1:1、1:n、n:n，遍历需后端加载链接）/ **Action types**（一组对象/属性/链接变更的定义，含提交时的副作用行为）/ **Functions**（服务端业务逻辑，**一等支持读属性、遍历链接、灵活编辑 Ontology**）/ **Interfaces**（"描述对象类型**及其能力**的抽象类型，提供**对象类型多态**"） | Palantir《Ontology · Overview》`docs/foundry/ontology/overview/`；《Object and link types》《Functions · Overview》 | 【确定】 |
| S60 | **★ Action Type 结构（与我们的"过程 + 结果 + 调整"高度同构）**："An Action is a **single transaction** that changes the properties of one or more objects, **based on a user-defined logic**"；`action type` = **参数定义**（可要求用户在标准化表单输入，含 object reference / object set）+ **Rules**（把参数转成 Ontology 编辑的逻辑）+ **Submission criteria** + **Validation**（"验证**授权员工**（如 HR 人员）可执行该 Action"）+ **Side effects**（"通知新旧 manager"）；**12 类规则**：Create object / Modify object(s) / Create or modify object(s) / Delete object(s) / Create link(s) / Delete link / **Function rule** / Create·Modify·Delete object(s) of interface / Create·Delete link(s) on object(s) of interface；**规则取值四种来源** = **From parameter**（默认自动建同名参数）/ **Object parameter property**（类型须匹配）/ **Static value**（仅存在于 Rules 部分、交互时不可改）/ **Current User / Time**；提交后"**携带用户编辑的最新对象数据 → object type 的 writeback dataset**"，且"**同一套 Action 逻辑与校验可跨所有前端应用复用**" | Palantir《Action types · Overview》《Action types · Rules》`docs/foundry/action-types/overview/`、`/rules/` | 【确定】 |
| S61 | **★ Palantir 把"配置化"与"代码化"当二选一**：**Function rule** = "引用一个 Ontology 编辑函数，其输入由 action 的参数派生。**存在此规则时，不得配置其他规则**，因为**函数代码本身已能处理其他规则能做的一切**" → 官方明确二选一，无"配置里嵌代码"；`Function action types` 为独立能力 | Palantir《Action types · Rules》（规则第 7 条 Function rule） | 【确定】 |
| S62 | **★ Palantir 无产品化定价引擎（定价为 use case，计算在 Dynamics 侧）**：化工行业用例 **"Drive revenue with integrated pricing"** 官方定位为 **use case**——Sales 在 **Microsoft Dynamics** 提报价请求（无上下文）→ **每 5 分钟经 Magritte REST 插件**同步 CRM 数据到 Foundry → Marketing 经理在 **Quiver 分析**中查看"**相似机会**（相同材料/客户/区域/量）的历史量价成本毛利"+"**前瞻成本估算**（基于未来材料价 + **BOM** 信息）"→ 人工给出价格建议 → **经 Webhook 写回 CRM**；**闭环反馈**（成交/丢单回灌 Foundry 优化未来决策）；零售用例官方措辞："Foundry **suggests** the best price… while **letting humans modify** the price"；成本侧 `Optimize COGS` / BOM 用例：整合 **7+ 套 ERP** 建价值链数字孪生、用 **out-of-the-box Bill of Material workflow** 优化 COGS，核心是 **granular COGS / profitability model**，官方措辞始终是 **model / workflow / optimization**，**不是 engine** | Palantir《Use case examples · Drive revenue with integrated pricing》《Optimizing production with ERP data across the supply chain》；`palantir.com/explore/retail/`；`palantir.com/explore/supply-chain-cogs/` | 【确定】 |
| S63 | **★ AIP Logic：可编程逻辑仍在 Action 这道"受控门"之后**："no-code environment for LLM-powered functions"，**输入**（primitive 或对象类型）+ **块**（**创建变量 / 获取对象属性 / 使用 LLM / 变换块（表达式转换）/ Apply Action（确定性调 Action，绕过 LLM）/ Execute（确定性调函数）**）+ **输出**，块可链式前馈、可嵌函数、**可单元测试**、可被 Automate 触发；**关键限制**："**必须**从 Action 调用 Logic 函数，Ontology 才会被编辑；**即使函数含 Apply Action 块，未经 Action 执行则不会写入**"；平台三件套 = **Apollo**（持续交付）/ **Foundry**（数据运营）/ **AIP**（生成式 AI），Ontology 由 **Language（建模语义对象与动力动作）+ Engine（可伸缩读写架构）+ Toolchain（OSDK）**组成 | Palantir《Logic · Getting started》（`Transform block` 明确"perform mathematical expressions"）、《Foundry platform summary for LLMs》 | 【确定】 |
| P4 | 定价依赖的通用主数据多缺失：币种仅枚举引用、无汇率/税/客户价格组/物料价格组；已有 UoM/换算/物料组/物料/伙伴/组织 | `meta/schemas` 枚举（glob + grep） | 【确定】 |
| P5 | **销售区域口径（v1.9 复证）**：平台**已有** `org_functions`（`org_id × function_type`，`UNIQUE(org_id, function_type)`，`is_primary`），`function_type` 白名单 **12 项**（`administrative` / `legal_entity` / `management_unit` / `procurement` / `accounting` / `profit_center` / `cost_center` / **`sales`** / `warehouse` / `manufacturing` / `inventory` / `storage`）——**含 `sales`（销售组织职能）**；`org.yaml` 另有 `org_type`（部门/团队/事业部/公司）、`org_scope`（内/外）、`parent_id` 自引用树；**但"分销渠道 / 产品组"两段无** → 原"待核"改判"**部分具备**" | `meta/services/org_function_service.py` L53-57（白名单）；`meta/migrations/v073__create_org_functions.py`；`meta/schemas/org.yaml` L106-165 / L389-415 | 【确定】 |

---

## 10. 变更记录

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v1.0 | 2026-10-05 | 首版：定价引擎专题研究。现状取证（无引擎 + 上位文档判定独立引擎）→ 六家头部对标矩阵 → 六件概念模型 → 与既有资产边界（五条划界）→ 差距分析（9 项）→ 渐进建设路径（P0–P5）→ 8 项待决策 → 证据表 | AI Assistant |
| v1.1 | 2026-10-05 | 落实评审意见：D7 **已拍板**（只做定价、元模型按通用确定设计，§8.2 给出 4 条可执行约束）；D2/D3 给出**专业建议**并新增 §8.1——按"**槽位内 exclusive / 槽位间 additive**"两粒度给默认值，D3 默认 Precedence、Best Price 须显式开启并定义度量 | AI Assistant |
| v1.2 | 2026-10-05 | 二期深化三问：新增 **§4.1 条件类型=配置对象**（六家对标 + 元模型字段）、**§4.2 主数据/配置对象四层全景**（含平台现状取证：币种仅枚举、无汇率/税/客户价格组）、**§4.3 计算基准**（层级/基准量/基准步骤三拆 + 行 vs 头 + 汇总方向 + 平台建议）；§1 加 3 条结论；§6.1 补 7 项依赖缺口；§7 P0–P2 挂依赖；§8 加 D9–D11；§9 加 S19–S23/P4 | AI Assistant |
| v1.3 | 2026-10-05 | 三期深挖（Oracle Fusion + Salesforce）：**§3.1.2 重写**（运行时对象链 + 三件可配置件 + 官方算例 + **cascading vs cumulative** + Pricing Basis 一等对象，并修正原稿"precedence vs best price 二选一"口径）；**§3.1.3 重写**（Pricing Procedure=ExpressionSet + 价格元素 + Context/Pricing Recipe/Sales Transaction Type + RCA/CPQ 双瀑布）；**§3.2 汇总表加详 + 3 行**（★基准一等对象 / ★过程内派生·汇总·分摊 / ★最低最高价）；§4.3⑥ base 拆四字段（加 `base_roll`）；新增 **§4.4 两引擎 13 维对照 + 六条直接启示**；**§5.2 分摊边界收窄**（过程内属定价、跨单据守恒归 allocation）+ 划界条款改写；§6.1 加 **#17/#18**（基准四字段 / 步骤 `element_type`）；§7 P2 补 `element_type`+`base_roll`、非目标行澄清；§8 加 **D12/D13**；§9 加 **S24–S29**。（注：本版 SF 元素计数"16 个 / 12+4"有误，已由 v1.4 纠正） | AI Assistant |
| v1.4 | 2026-10-05 | **二次检查修正版**（全篇通读 + 两处关键论据联网复证）：① **重核 SF 元素清单**——正确为 **15 个价格元素 + 5 个控制元素（共 20 个 Element）**，原稿"16 个 / 12+4"有误（§1(11)、§3.1.3 标题与表、§3.2、§9 S28 全稿同步，并补计数说明与 Contract Pricing 说明）；② **深挖证实 DDS 是定价过程内的标准 Element**（头级折扣跨行分摊 + 地板价 + 分摊规则决策表，支持等分/按行值比例），据此把 D13 与 §5.2 的判据从"**是否守恒 / 是否跨单据**"改为"**是否作为定价过程的一步**"（§1(11)、§3.1.3 借鉴点②、§4.3⑥、§4.4 启示 4、§5.2、§7、§8 D13、§8.2 共 8 处联动）；③ **厘清"基准"第四维**——新增 `base_roll`（是否滚动）与 `base_step`（基准步骤）**互斥**，`base_value` 统一改名 **`base_basis`**（§1(9)、§4.3 D 行/⑥ item5、§4.4 启示 3、§5.2）；④ §5.2 标题"五条边界"→**"六条边界"**（表实为 6 行）；⑤ §9 证据表**新增 S30–S32**（DDS 属过程内 Element / Running Net Price 是单一累加器且 `base_roll` 与 `base_step` 互斥 / Oracle 合同级+行级 cumulative 作用于 list price 的官方算例）并重排编号 | AI Assistant |
| v1.5 | 2026-10-05 | **四期深化**（用户新增两问：单据流里上游价格"复制 vs 重算"、基于实际执行数量计算或重新定价）：新增 **§4.5**——**维度一 传递策略**（SAP `KNPRS`/`TVCPF` 复制 vs 重算枚举、Oracle 三个 `Freeze*` 开关、SF Repricing Service）、**维度二 数量基准**（SAP `FKMGK` 开票数量指标、Oracle 21D/24C 按实际发货量调 extended amount、EBS `Price Line`）；给 **三种组合表**（①纯搬运 / ②按实际量重算金额 / ③完全重定价）与**元模型建议**（`freeze_policy` / `reprice_trigger` / `qty_basis`，并强调 `qty_basis` 须与 §4.3 `base_basis` 区分）；**红线：已开票/已过账行禁止隐式重定价**；§1 加结论 12（两维正交）；§6.1 加 **#19/#20**；§7 P4 行与"非目标"行联动；§8 **D8 细化**（三档 `price_mode` × 逐属性覆盖）并新增 **D14**（`qty_basis`）；§9 加 **S33–S37** | AI Assistant |
| v1.6 | 2026-10-05 | **五期深化**（用户新增一问：定价业务对象结构，与订单 / 订单行 / 单据对象的关系）：新增 **§4.6**——**两条对象链**（配置/主数据链 vs 单据运行时链）、三家宿主对标（SAP 条件行 `KONV`/`PRCD_COND` 随单据存 + 头级聚合号 `KNUMV` + `KHERK=D` 头条件；Oracle `Charge` 挂订单行 + `ChargeComponent` 明细；SF `PricingProcedureOutputMap` 映射回单据行）、**三个结构事实**（值落行不落头 / 头条件靠标记与分摊 / 结果分"结果行 + 步骤明细"两层）、**平台对象结构建议**（复用 `document` 型 BO + `composition 1:N`，落成 `pricing_result` + `pricing_step`，**不建独立定价单据**）；§1 加结论 13；§5.2 `doc_flow` 行补"只搬结果字段、不搬明细"；§6.1 加 **#21**；§7 P2 交付加结果对象；§8 加 **D15**（对象宿主）；§9 加 **S38–S40**。（另：**D8 / D14 / D15** 于 2026-10-05 经 PM **认可**，§8 已标 ✅ 已拍板）| AI Assistant |
| v1.7 | 2026-10-05 | **六期深化**（用户新增一问：事后 unplanned charge（如采购侧）、过程中的费用、分摊，是否已考虑）：① **先切三类费用**（过程内条件费用 / 事后计划外费用 / 过程执行费用），指出**分摊只覆盖了"过程内"的一半，事后费用与过程费用基本未覆盖**；② **三家对标**——SAP 计划外交付成本（MIRO 录入 `BEZNK`、按发票行分摊 or 独立 G/L、SPRO 配置点、**不走条件技术**走 OBYC `UPF` + BAdI `MRM_UDC_DISTRIBUTE`）、后续借项/贷项（**属 MM 发票校验**）与 SD 开票更正请求（订单类型 RK、成对贷借项、只结算差额）、追溯定价（`PRSDT`、`VA05 Mass Change`、`VF02 Update Pricing`）、返利（**条件更新 `KOUPD`** + 结算 + S/4 WCOCO + Delta Accrual）；Oracle **LCM 六种分摊基数** + 计入库存成本/COGS + **独立 acquisition cost adjustment** + Retroactive Price Adjustment；SF `PriceAdjustmentSchedule` 为预配置、**无 ad-hoc 追加费用标准机制**【未找到】、走 Repricing Service；③ **归纳四条规律**（不改原单价 / 分摊基数可配 / 去向可配 / 追溯须显式触发）+ 边界启发（**费用不一定走条件技术**）；④ **平台对象建议**——扩展 `pricing_result`（`origin`/`charge_source`/`source_document_*`/`target`/`allocation_basis`/`allocation_rule_id`）+ 新增 **`allocation_rule`** + **`pricing_adjustment`**，**不新建费用单据**；⑤ **§5.2 / §7 边界细化两档**，判据升级为"**是否有'可分摊到一个业务单据行'的价格/费用语义**"；⑥ 新增 **§4.7**、§1 加结论 14、§6.1 加 **#22–#24**、§7 加 **P4.5** 行并**显式声明采购侧范围**、§8 加 **D16**、§9 加 **S41–S46** | AI Assistant |
| v1.8 | 2026-10-05 | **七期深化**（用户新增一问：基于**质检结果 / 其他事实数据**重新计算，如**优质优价**、**大宗贸易**，是否已考虑）：① **答"没专门考虑"**——原稿只有"按实际数量重算"（§4.5），"按质量 / 计量 / 市场事实重算"整体缺失；② **事实源切三源**（质量 / 计量 / 市场），与 §4.7 事后费用**同族**（来源 ≠ 订单条件记录）；③ **三家对标**——SAP **变式定价 `VARCOND`**（`KONV-VARCOND`、条件表 A900、VA00；**`VACOND` 不存在**）、批次定价只到批次号、**CPE 暂定价 → 终价（两段式开票 + 差额 credit/debit memo）**、报价源 **MIC + DCS + Quotation 规则**、**F&A 计价期均价**、**按品位折算数量**（AIBM + 批次特定计量单位）、采购侧**"质检值直接改价"未找到**；Oracle **属性定价确定但"质检值 → 定价"未找到**、**EBS 有完整 Pricing Formulas / Fusion 无**、外部报价源未找到、GTM 无 provisional → final；SF **`AttributeBasedAdjustment`** + `PriceAdjustmentSchedule` 容器、**质量升贴水 / 暂定价结算未找到**、指数定价 = **`IndexRate` + `PriceRevisionPolicy`**；④ **四规律**（两条进入路径 / 头部普遍半成品 → 平台做成一等即增量 / 大宗 = 两段式差值结算 / 计价期是配置）；⑤ **平台对象建议**——字段目录加 **`source_type`**、新增 **`external_price_source` / `pricing_period`**、`pricing_result` 加 **`fact_snapshot`**、`qty_basis` 扩容、优质优价落 `quality_premium`、大宗落 `provisional_settlement`；⑥ 新增 **§4.8**、§1 加结论 15、§4.5 扩 `reprice_trigger`、§6.1 加 **#25–#27**、§7 加 **P6** 行与期货 / QMS 边界声明、§8 加 **D17**、§9 加 **S47–S51** | AI Assistant |
| v1.9 | 2026-10-05 | **二次检查修正版（把 v1.7 / v1.8 新增内容与全篇口径重新对齐 + 收口两处遗留待核）**：① **修正枚举漏项**——`pricing_adjustment.adjustment_type` 补 **`provisional_settlement`**（§4.8 用到但 §4.7D 表与 §6.1 #24 未收，已全稿对齐）；② **修正件号笔误**——§6.1 **#19/#20** 的"件⑦配套"改 **"件④配套"**（§4 只有六件，§4.5C 原文即"件④配套"）；③ **修正阶段口径张力**——§4.7A① 的"已设计"改为"**模型已设计**"，显式标注**头条件 / 组条件分摊按 D10 属 P3+**；④ **修正 D17 倾向笔误**（原"①蓝图按 ③"与选项①"不做"自相矛盾，改为"**蓝图按 ③ 设计、实施按 ② 起步**"）；⑤ **补齐联动**——§6.1 标题 / 引言覆盖 **§4.2–§4.8**、排序原则补 **#25–#27**、#20 补 `qty_basis` 扩容值、§4.4 启示 1 补 `quality_premium`、§9 P3 行号 L1435→**L1432**（与 §5.1 一致）；⑥ **收口遗留待核（两处）**——(a) 复证**金蝶"计算策略"属定价过程内**（公式化因子聚合层、可回放；仅旗舰版 / 星瀚），新增 §1 结论 16、§3.1.6 条目、§3.2 表行改写、§4.4 ④ 表行改写、§9 **S52**；(b) 复证**销售区域**口径——`org_functions.function_type` 已含 **`sales`**（销售组织职能，12 项白名单），**渠道 / 产品组两段无**，§4.2 表与 §6.1 #16 由"待核"改"**部分具备**"；⑦ **header 版本号同步为 v1.9** | AI Assistant |
| v2.0 | 2026-10-05 | **跨域二次研究版**（用户要求：结合通用性角度，对 Oracle 做二次研究）：**动机**——前七期都是从**定价域**向外看，本期在元模型改为"领域中立 + 三轴参数化"后，**反向验证**：拿 Oracle **自家另外两个域**的引擎逐字对撞（选 Oracle 因其是六家中唯一同时存在三套"量×率×多步"引擎的厂商，且同厂商内部比可排除"术语差异"噪音）。① **新增 §4.9 八期深化**——**A 成本域**（Cost Organization → Cost Book[primary/secondary/ledgerless] → Cost Scenario → Cost Element / Cost Component / Resource Rate / Overhead Rate / Sourcing Rule → **Roll up Costs** → Cost Accounting Distribution；官方卷积公式"总成本 = 固定 + 变动[单位资源成本 × 消耗数量]，单位成本 = 总成本 ÷ **scaled quantity**"；Actual / Standard / Perpetual Average 三种估值基础；`Provisional completion` + `Adjustment propagation` **3 环强制停止**；域特有逻辑=成本期间/截止日/差异分析/WIP/科目映射）；**B 碳域**（EAR 的 **Emission Factor × activity data = 排放量**，官方算例 100,000 KWh × 0.9 kg CO2-e/KWh = 90,000 kg CO2-e；**Emission Source / Emission Type / Emission Scope / Environmental Ledger**；**5 级 precedence 链：物料 > 供应商 > 组织 > 政府(地点) > 政府(通用)**；四种因子来源；四种事实数据入口；OFS 气候的 **GWP 二次乘数** + **6 个因子库层级（UNFCC/DEFRA/EPA/GHG Protocol/PCAF/IFI）** + Scope×活动二维矩阵；EPM 碳计算器**建在 Planning 引擎上**）；**C 逐轴检验**——三轴全部成立，`rate_source` 三值够用、`result_semantic` 保持单值（碳的 Scope/气体类型是**并列字段**非复合语义）；**D 三条未覆盖维度**——**D1 ★第四消解范式 `weighted`**（多候选不取一、全部按权重加权累加；Oracle 内部三处在用；建议 `condition_record.allocation_weight` 可空，与 `allocation_rule` 互为对偶）/ **D2 单位换算层**（换算是"单位声明"不是"公式"的一部分 → 本期只补 `scaled_quantity` 枚举）/ **D3 多账簿并行**（属编排层 → TBD-11）；**E 建议清单 R-1–R-6**；**F ★反证**——**Oracle 自己也没做通用引擎**（三套独立应用 + 三套结果结构，碳甚至建在 Planning 引擎上）→ 正面印证 D7 / N9 边界，同时点明平台"**一张 `pricing_result` + 一张 `pricing_step` 承载三域**"是相对 Oracle 的真实增量；**G 新增决策 D18–D20**；② **§1 加结论 17**；③ **§6.1 加 #28–#30**（权重分配 / `scaled_quantity` / `conversion`）+ 排序原则补 #28–#30；④ **§8 加 D18 / D19 / D20**（各给 2–3 选项与倾向）；⑤ **§9 加 S53–S58**（六条 Oracle 官方文档证据，全部【确定】）；⑥ **header 同步为 v2.0**。**注：本期结论已回写 Spec v1.3 的三轴判定，但 Spec 本身未改（R-1/R-2 待 PM 拍板后方落）** | AI Assistant |
| v2.1 | 2026-10-05 | **Palantir 研究版**（用户要求：针对 Palantir 研究下）：**动机**——前八期的六家（SAP / Oracle / SF / D365 / Odoo / 金蝶）都是"**业务套件 + 预置引擎**"路线，靠"加字段 / 加条件类型"扩域；**Palantir 是唯一不卖预置业务套件、只卖通用对象层（Ontology）的厂商**，因此是检验"对象模型通用性"的**最佳对照组**。① **新增 §4.10 九期深化**——**A Ontology 六元组**（Object Type / Property / Link Type / Interface / Action Type / Function）+ **官方定位**（"组织的**运营层**""**数字孪生**""含语义元素 objects/properties/links + 动力元素 actions/functions/dynamic security"）+ **明确声明"Ontology 不是语义层"**，其目的是 data/logic/action/security **四重集成**；**B Action Type 逐项对撞**（"一次**事务**，基于用户定义逻辑改变一个或多个对象属性"= 参数 + **12 类 Rules** + Submission criteria + **Validation**（"验证授权员工可执行"）+ **Side effects** + writeback dataset；**规则取值四来源** From parameter / Object parameter property / **Static value** / **Current User-Time**）；**C ★★ 第三条通用化路径**——路径①**元模型+参数化**（六家）/ 路径②**通用对象图+行为附着**（Palantir）/ 路径③**套件内建**（Odoo/金蝶）；**C2 明确"不预置业务域"**（只有 `use-case-examples`，无任何定价/成本/碳产品文档）；**C3 定价为 use case、计算在 Dynamics 侧**（Magritte REST 五分钟同步 → Quiver 看相似机会历史量价成本毛利 + 前瞻成本 → 人工建议价 → Webhook 写回；零售措辞"**建议**最优价、**让人可以**改价"；成本侧措辞始终 model/workflow/optimization）；**C4 AIP Logic**（输入 + 块[创建变量/取对象属性/**用 LLM**/变换块/**Apply Action**/**Execute**] + 输出，**必须从 Action 调用才写入 Ontology**）；**C5 ★最锋利结论**——"两条路径的分野不在能力，在**谁承担域特有逻辑**"；**D 三条落地观察**（D1 **`field_catalog` 多一层 `source_type` 是合理增量**、它缺是因为它没有"按计量结果重算"的诉求；D2 **Interface 能力多态**→ TBD-12；D3 **Validation 位**→ 补"改价必填原因"、完整矩阵 TBD-13）；**E 新增决策 D21 / D22**；② **§1 加结论 18**；③ **§6.1 加 #31（改价必填原因，P2）/ #32（结果能力接口，后置 TBD-12）** + 排序原则补 #31/#32；④ **§8 加 D21 / D22**（各给 3 个选项与倾向）；⑤ **§9 加 S59–S63**（五条 Palantir 官方文档证据，全部【确定】）；⑥ **header 同步为 v2.1**。**注：本期结论同样未改 Spec（D21/D22 待 PM 拍板后方落）** | AI Assistant |
