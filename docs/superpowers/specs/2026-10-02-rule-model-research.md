# 规则模型研究：创建业务对象时的属性确定与自动带出

> **版本**：v1.9 | **日期**：2026-10-02 | **状态**：研究报告（待评审）
>
> **关联文档**：
> - [对象模型总纲：计划与事实](2026-09-30-object-model-guideline-plan-vs-fact.md)（本文的上位理论：§5 关联在边上、§5.4 一个对象放几个量、§9 新建 BO 五问）
> - [单据流 Copy Control 深度研究](2026-09-29-doc-flow-copy-control-research.md)（**姊妹篇**：那篇讲"**跨对象**源单→目标单的映射与拆合"；本篇讲"**单对象内**因子→属性的确定"，两者是不同的规则资产，勿混）
> - [派生的数量语义](2026-09-08-doc-flow-quantity-semantics.md)（DOC_FLOW 边表/规则表定义）
> - [Palantir Ontology 三层架构研究](2026-10-01-palantir-ontology-three-layer-research.md)（机制原语平台坐标；本文 §5 是其"动力学层"的规则细节）
> - [Oracle Fusion 履行编排引擎研究](2026-09-30-oracle-fusion-fulfillment-orchestration-engine-research.md)（Fusion 侧 §3.4 绑定=指派规则的出处）
>
> **本文回答**：当用户**新建一个业务对象**、只填了少数字段（订单类型 / 行类型 / 客户 / 物料）时，系统凭什么把**其余属性/合同/字段**自动带出来？这套"因子 → 规则 → 结果"的机制，SAP / Oracle / Palantir / Salesforce 各怎么做？共性骨架是什么？**我们平台该长成什么样、落在哪几个既有接缝上？**
>
> **核实说明**：本篇头部产品结论均来自官方文档/官方帮助页原文（SAP Help / Oracle Docs / Palantir Docs / Salesforce Help / Microsoft Learn / Odoo Docs / 金蝶官方社区），标注 **【确定】/【基本确定】/【存疑】**；二手评价一律【存疑】且不进入结论。

---

## 1. 先把"规则"切干净：平台有三类规则资产，本文只谈第三类

"规则"在平台上是个被过度使用的词。动手前必须切开，否则会造出第四套重复机制：

| # | 规则资产 | 作用域 | 方向 | 已有落点 | 形态 |
|---|---|---|---|---|---|
| 一 | **单据派生规则** | **跨对象**（源单 → 目标单） | 推（下推/上拉） | `doc_flow_rule` + derive 引擎 | 边 + 数量池 |
| 二 | **条件权限规则** | 单对象字段 | 判定（能看/能改/必填） | `condition_permission_service` / `field_policy_engine` | 条件 → 布尔 |
| 三 | **属性确定规则** ★本文 | **单对象内**（因子 → 其它属性） | 带出（默认填充） | **容器已有**（`MetaRule` + `RuleEngine` + `meta_obj.rules`），**缺 `default` 语义** | 条件 → 值 |

> **口径修正（v1.10，2026-10-03，实施后回填）**：原表第 3 行写「**尚无专门资产**」不准确。核实后：平台**已有**规则容器与执行骨架——`MetaRule` 基类（`models.py` L141-170）、`RuleType` 七值枚举（`models_enums.py` L94-101）、`RuleEngine`（`rule_executor.py` L1039 起）、`MetaObject.rules` 与 `MetaObject.get_rules_by_type/get_computations/...` 访问器、`SafeExpressionEvaluator` AST 白名单。**真正缺的只是 `default`（属性确定）这一种语义**：现有 `priority` 是「全局排序 + 全部执行」，而属性确定需要「分组（按目标字段）+ 首个命中即停」。因此本专题的工作量是**扩展已有引擎**，而非新建引擎——这与 §8.2 结论一致，仅「尚无专门资产」的措辞需正名。

> **一句话分界**：
> - 一类解决"**这条单变成哪几条单、多少量**"（对象之间）；
> - 二类解决"**你能看见/改动这个字段吗**"（权限，不产生值）；
> - **三类解决"你没填的这个字段，系统替你填成什么"（对象之内）**。

**本文只谈第三类。** 但第三类与第一类、第二类共享同一套"条件表达式"基础设施（见 §8）。

**本专题首要场景**（用户原话复述）：建单时录入 订单类型、行类型、客户、物料 → 系统自动确定**其它属性**、确定**合同**、确定 **xxx** → 填入表头或明细字段 → **有时用户可进一步变更**。

---

## 2. 规则解剖：五要素

把所有头部产品的"属性确定"机制拆到底，都是同一副骨架，但有**五个必须显式回答的问题**，缺一不可：

| 要素 | 问题 | 典型取值 |
|---|---|---|
| **① 触发 When** | 什么时候算？ | 创建时 / 字段变化时（onchange）/ 保存前 / 保存后 / 批处理 |
| **② 因子 Factor** | 依据哪些已录入值？ | 订单类型、行类型、客户、物料、日期、组织、用户 |
| **③ 条件 If** | 因子的什么取值组合命中？ | 相等 / 区间 / 属于集合 / 表达式 / AND-OR 分组 |
| **④ 动作 Then** | 命中后把什么设成什么？ | 常量 / 字段对字段 / 查表带出 / 公式 / 调用函数 |
| **⑤ 次序 & 覆盖 Order** | 多条命中怎么办？已有的值动不动？ | 顺序号·首个命中 / 取最优；仅空值才填 / 强制覆盖 |

> **本报告的对比矩阵就是这五要素。** 后文每家的机制，都按"它怎么回答①–⑤"来读。

**三个贯穿全篇的关键区分**（先记住，后面反复出现）：

1. **保存前内存改写 vs 保存后落库**：保存前改写（Salesforce before-save flow / Odoo onchange / SAP 替代）**零 DML、可被用户覆盖、不产生审计痕迹**；保存后落库则相反。
2. **客户端带出 vs 服务端强制**：客户端带出是"贴心预填"，用户能改；服务端强制是"规则即事实"，用户改不了（或改了要理由）。
3. **展示用派生 vs 写入用默认**：读时算出来的（公式、derived property）**只用于显示**，**不能反过来当默认值来源**——Palantir 官方只把 derived property 声明为 **read-only、不能被 function / action 编辑**【确定】，**据此它在机制上无法充当默认源**【基本确定】（官方页**无**“不可用于 defaulting”字样，原稿此处属过度断言，v1.7 修正）；我们的读时填充引擎同理。

---

## 3. SAP：条件技术（Condition Technique）——把"确定"抽象成一台通用机器

SAP 是这套机制的祖师爷，也是抽象最彻底的一家。它把"根据若干因子确定一个结果"统一抽象为 **条件技术**，同一台机器驱动五种业务确定过程。

### 3.1 条件技术五构件【确定】

| 构件 | 英文 | 回答的问题 | 形态 |
|---|---|---|---|
| **条件表** | Condition Table | 用哪些因子做键 | 字段组合（如 客户+物料+订单类型） |
| **存取顺序** | Access Sequence | 按什么优先次序去查条件表 | 有序的条件表列表 |
| **条件类型** | Condition Type | 查出来的是什么 | 一个语义槽位（如"客户折扣"） |
| **条件记录** | Condition Record | 具体取值 | 数据行（键 + 值 + 有效期） |
| **确定过程** | Procedure | 用哪些条件类型、什么次序 | 条件类型的有序清单 |

> **精髓**：**"键从哪来"（存取顺序）与"值是什么"（条件记录）与"用哪些键"（条件表）三者解耦**。换一套因子组合不用改取数逻辑，只加一张条件表就行。这是它能一次抽象、五处复用的原因。

### 3.2 同一台机器驱动五类确定过程【确定】

| 确定过程 | 事务码 | 因子（典型） | 带出的结果 |
|---|---|---|---|
| **定价** Pricing | V/08 | 客户+物料+订单类型+数量 | 价格、折扣、附加费 |
| **合作伙伴** Partner | VOPAN | 客户 + 单据类型 + 账户组 | 售达方/送达方/付款方/开票方 |
| **批次** Batch | COB1/OPL8 | 物料+工厂+特性+批次属性 | 用哪个批次 |
| **输出** Output | NACE | 单据类型+合作伙伴 | 打印/EDI 消息 |
| **文本** Text | VOTXN | 单据类型+语言+对象 | 标准文本 |

**对本专题的启示**：**"确定合同""确定 xxx"在 SAP 里都是同一台条件技术机器的产物，只是过程不同。** 我们不需要为"定合同"造一套、为"定价"再造一套——应该是一套确定引擎 + 多张规则表（见 §8）。

### 3.3 存取顺序的两条取数语义：独占 vs 累加【确定】

- **独占型（exclusive，默认）**：**命中的第一条就返回，停止**（first-hit-wins）。→ 这是"确定唯一值"的语义。
- **累加型（additive）**：**继续向下把所有命中累加**。→ 只用于定价这类"多项叠加"。

**Requirements routine（需求例程）**：每个存取顺序的一级可挂一个布尔例程，用来**否决**本条（如"该客户不参与此折扣"）。

> 本专题（属性确定）几乎全是 **exclusive（首个命中）**；additive 是定价专属。这个区分很重要——决定了我们规则表的默认取数语义。

### 3.4 复制控制（跨对象）——见姊妹篇，本文不展开

SAP 的 Copy Control（VTAA/VTLA/VTFL、Data Transfer Routine、Copying Requirement、VOFM 例程）解决的是"**源单 → 目标单**"的映射与拆合，属于本文 §1 的**第一类**规则，已在 [Copy Control 研究](2026-09-29-doc-flow-copy-control-research.md) 详述。此处只记一条与本文的交界：

> **Copy Control 是"对象之间"的确定；条件技术是"对象之内"的确定。** SAP 把两者做成了**两套**机制（VOFM / 条件技术），并没有合并。**这印证了我们也不该把属性确定塞进 `doc_flow_rule`**（§8.1）。

### 3.5 变式配置（LO-VC）的五类对象依赖——最强的一处"因子组合定值"【确定】

可配置物料（KMAT）+ 特性 + 类（200/300）的 Variant Configuration，是 SAP 里表达"**因子之间相互约束、互推出值**"最完整的机制。它把规则叫**对象依赖（Object Dependencies）**，共五类：

| 类型 | 作用 | 类比 |
|---|---|---|
| **前提条件** Precondition | 某特性是否允许填 | 门禁 |
| **选择条件** Selection Condition | 哪些值可被选 | 候选过滤 |
| **动作** Action | **某特性值变化 → 自动推出另一特性值** | ★**正是本文要的"带出"** |
| **约束** Constraint | 多特性之间的取值组合约束 | 联合校验 |
| **过程** Procedure | 计算/覆盖逻辑（命令式） | 公式 |

**配置参数文件（Configuration Profile）** 决定这五类依赖何时触发（保存/配置时）。

> **直接可借用的一条**：**"Action = 由其它值自动派生特性值"**——这就是"输入因子，带出其它属性"在头部产品里最纯粹的形式。它的粒度是**字段级**，触发是**值变化时**，结果**可被后续依赖继续消费**（级联）。

**变式表（Variant Table）**：把"因子组合 → 结果"做成一张可维护的表——**等价于我们的"确定规则表"**（条件表 + 条件记录）。

### 3.6 FI 校验与替代（Validation & Substitution）——"保存前内存改写"的教科书【确定】

- **校验**：GGB0 定义 / OBBH 激活；**替代**：GGB1 定义 / OBBH 激活（OB28 用于特定场景）。
- **三级 callup point**：抬头 / 行项目 / 完全凭证。
- **替代结构**：**前提条件（布尔）→ 替换值**；替换值三种来源：**常量 / 字段对字段 / EXIT 例程**。
- **执行时机**：**替代在凭证保存前执行**（内存改写，随后落库）。
- **优先级**：`OKB9 默认 > GGB1 替代 > 手工输入`（同一字段三者都可能给值时，按此序）。
- **GB01** 控制**哪些字段允许被替代**（不给改的字段锁死）。

> **两处极重要的先例**：
> 1. **"替代 = 保存前内存改写"** → 对标 Salesforce before-save flow、Odoo onchange。**这是"带出"最该采用的时机**——用户看到的值是带出后的，但历史/审计上它仍是一次正常写入。
> 2. **优先级三档 `默认 < 替代 < 手工`**（数值上 OKB9 优先，但语义上"手工输入最高"）→ 直接回答本文要素⑤的**覆盖语义**：**系统算的可以被用户覆盖，用户改了就认用户的**。这正是用户原话"**有时用户可以进一步变更**"的行业标准答案。

### 3.7 SAP 小结

| 要素 | SAP 的回答 |
|---|---|
| ① 触发 | 保存前（替代）；值变化时（VC Action）；批量（确定过程） |
| ② 因子 | 条件表字段组合 / 特性 |
| ③ 条件 | 存取顺序 + requirements routine（布尔否决） |
| ④ 动作 | 条件记录取值 / 字段对字段 / 常量 / EXIT / 公式 |
| ⑤ 次序 | **条件类型次序 + 存取顺序次序 + 首个命中**；覆盖 = `默认 < 替代 < 手工` |

**一句话**：SAP 把"确定"做成**一台可配置机器 + 数据化的条件记录**（exclusive / additive 两种取数语义），而不是写死的代码。

---

## 4. Oracle：两代产品、两套哲学

Oracle 在这个问题上**横跨两代产品、给出两套答案**：**EBS** 是"**独立的确定引擎 + 规则数据化**"（Defaulting Rules 自成一套）；**Fusion** 则把"确定"**并入转换与编排**——没有一个与 Transformation Rules 并列的独立 "Defaulting Rules" 模块，规则藏在 **Pretransformation Defaulting Rules + 编排指派 + Groovy 扩展**里。本节按五要素逐层拆解。

### 4.1 EBS 默认规则（Defaulting Rules）——"顺序号 + 源属性"模型【确定】

默认规则挂在**实体 × 属性**上（如"订单行的仓库"），每个属性一组有序规则：

| 要素 | EBS 记法 |
|---|---|
| **Condition** | 什么条件下适用 |
| **Source** | 值从哪来：常量 / 其它属性 / 系统变量 / 配置文件 / **PL/SQL（Defaulting Framework）** |
| **Defaulting Sequence** | **顺序号**；**同序号按字母序**（tie-break） |
| **Dependencies** | **依赖仅限同一实体**；源属性变动 → 触发**再默认** |
| **头部 → 行** | **可配置级联**（profile `OM: Sales Order Form: Cascade Header Changes to Line` = Automatic / Askme / Manual） |

**★ 三处口径修正（v1.8）**：

1. **"种子顺序号从 50 起"【未找到】** —— 官方只证实"**同序号按字母序**"，未给种子起点；原稿的"50"应删。
2. **Source 的"SQL 语句"【不准确】** —— Order Management 用的是 **PL/SQL Defaulting Framework**；裸 SQL 作为源属 **Purchasing**（PO）体系的默认规则，**不应混入 OM**。
3. **"源属性变必先清空再默认"【有例外】** —— 官方原文：
   > "if re-defaulting did not come up with a default ... the old value would be retained instead of clearing"
   即 **再默认若未算出新值，则保留旧值而非清空**。→ **"先清空"是愿望不是铁律**；正因官方自己都有例外，"再判定到底清空还是保留"**必须由我们显式规定**。

> **可借用的两条**：
> 1. **"顺序号 + 首个命中 + 明确 tie-break"** 是默认确定的通用范式（与 SAP exclusive 同构）。
> 2. **再判定（re-defaulting）必须显式规定"清空 or 保留"** —— 否则残值串联（C10）。

### 4.2 EBS 处理约束（Processing Constraints）——"能不能改"而非"填什么"【确定】

四元组 **Entity + Operation + Attribute + Action**；**Group Number 支持 AND / OR 分组**，Scope = ANY / ALL。

官方明列的动作（**修正 v1.8**——原稿的 "Not Allowed / Generate Version / Require History" 属**过度提炼**，官方实际列出的是）：

| Action | 含义 |
|---|---|
| **Require Reason** | 允许改，但**必须填变更原因** |
| **Trigger Audit Trail / Versioning** | 改**要留痕 / 生成版本** |
| **Raise Integration Event** | 改**要发集成事件** |

**关键**：**System Changes vs User Changes 两个开关**——分别控制"**系统再默认能否覆盖用户已录入的值**"。

**★ 删除**：原稿"**一次变更只有一个约束生效**"【未找到】—— 官方页无此表述，**不足以作为结论**（v1.8 移除）。

> **这是要素⑤"覆盖语义"的第二个标准答案**：**把"系统能不能改用户的值"显式做成开关**；并给出"**可改但要理由 / 要留痕 / 要发事件**"这条**受控变更**路线 —— 对应"用户可进一步变更"的**受控版本**。

### 4.3 Fusion OM：Pretransformation Defaulting Rules（预处理默认规则）——最接近本专题的现代实现【确定】

**★ 标题与口径修正（v1.8）**：原稿写"Fusion 默认值**即** Transformation Rules"，**不准确**。官方**有独立的默认值机制**：

- 页面名 **Manage Pretransformation Defaulting Rules**（"Pretransformation **Defaulting** Rules"）；
- 判断"目标为空"的**界面控件名是 `Is Blank`**（原稿写的 "`target attribute is blank`" 系**改写**，非官方控件名）；
- **Fusion OM 没有**与 Transformation Rules 并列的独立 "Defaulting Rules" 模块 —— 默认值主要由 **Pretransformation（Defaulting）Rules + Order Management Extensions（Groovy）** 承担。

其机制：

- **两阶段**：**Pretransformation（预转换）** / **Posttransformation（后转换）**，对应不同时机。
- **声明式构造**：Visual Information Builder，**If / AND / OR → THEN > DO > New Action**。
- **★ 覆盖语义**：条件里**显式加 `Is Blank`**，才**不覆盖用户已录入的值** —— **"仅空值才填"是规则里的一行条件，不是引擎的隐含默认**。
- **生命周期**：**Effective Date / Active / Publish**；复杂逻辑退化为 Groovy（命令式逃生门）。

> **对本平台最重要的一条**：`Is Blank` 说明 —— **"是否覆盖"是规则自身的属性**，应写在规则里**可读可审**，而不是藏在引擎里当黑盒。我们若做确定规则表，**"覆盖策略"必须是一列显式数据**（§8.3 `overwrite`）。

### 4.4 Fusion 编排进程指派规则（Orchestration Process Assignment Rules）——规则本体不版本化【确定】

`Manage Orchestration Process Assignment Rules`，**If / Else-If / Otherwise** 三段式。

官方原文（关键）：

> "You don't need to specify a version or effective date for an assignment rule **because the orchestration process controls them**."

**含义**：**规则本体不版本化——版本与生效期由被指派的实体（编排流程）承担。** 这是"**版本分层**"（规则轻、被引用物重）的先例（C7）。

### 4.5 Advanced Pricing：Qualifier + Modifier + 取优【确定】

- **Qualifier**（资格，如订单类型/客户群）/ **Modifier**（修饰，如折扣）/ **Price List**（价目）。
- **Context 属性 + Precedence**：多上下文同时命中时按优先级。
- **Event Phase 的 Incompatibility Resolve Code**：冲突时二选一——**Precedence（按优先级）vs Best Price（取最优）**。
- **可解释性**：**Pricing Engine Request Viewer** 能把一次定价计算的取数过程完整回放。

> 两条借用点：**① 冲突消解要显式选范式**（首个命中 vs 取最优，二选一，不要混）；**② 可解释性要做成"能回放这次为什么带出这个值"**（C9）。

### 4.6 校验：Fusion 的两层（声明式 + 扩展式）【确定·v1.8 新增】

| 层 | 机制 | 形态 |
|---|---|---|
| **声明式** | **Processing Constraints**（OM）—— 按 实体 / 操作 / 属性 阻断非法变更 | **阻断型** |
| **扩展式** | **Application Composer** 的 **Object Functions / Triggers / Validators** | 可 **Error / Warning** 两级 |

→ 与 §10.2 的"**布尔·阻断**"一格对应；也印证 C8：**声明式挡住大头，边角走扩展**。

### 4.7 计算：Fusion 的路径（无独立"Processor"）【确定·v1.8 新增】

- **定价侧**：**Pricing Formulas / Groovy 脚本**（`Amount = Qty × Price` 之类写在公式里）。
- **对象侧**：**Application Composer 的 Formula 字段**。
- **口径提醒**：官方**没有**"计算处理器（Processor）"这类页面表述 —— 不应把它写成 Fusion 的一个独立引擎。

→ 对应 §8.9 的 `compute`：**确定与计算分立**（本文共识），Fusion 也是分立实现。

### 4.8 集合确定：Fusion 的现状（部分缺口）【基本确定·v1.8 新增】

| 过程 | Fusion 的承载 |
|---|---|
| **审批人** | **Approval Management**（审批体系，非"属性确定"） |
| **批次** | **Wave Plan / Pick Slip Grouping**（分组规则） |
| **伙伴 / 输出** | **未找到**与默认规则并列的"规则化确定"机制【未找到】 |

→ 说明**"集合确定"在头部产品里也常散落在各业务模块**，未必统一成一个规则引擎 —— 与 §10.3"最大缺口"的判断一致。

### 4.9 Oracle 五要素小结（EBS vs Fusion）

| 要素 | EBS | Fusion |
|---|---|---|
| ① 触发 | 创建 / 字段变化（**可配置级联**） | Pre / Post transformation |
| ② 因子 | Condition + 实体属性 | If 里的属性 |
| ③ 条件 | Condition | If / AND / OR（**含 `Is Blank`**） |
| ④ 动作 | Source（常量 / 属性 / 系统变量 / 配置 / PL/SQL） | THEN > DO |
| ⑤ 次序·覆盖 | **顺序号 + 首个命中 + 同序字母序**；**System vs User 开关**；依赖仅同实体 | 规则内**显式写覆盖条件**（`Is Blank`）；规则本体不版本化 |

### 4.10 Oracle 结论

> **Oracle 给了"独立确定引擎"（EBS）与"确定并入流程"（Fusion）两个答案。** EBS 的 `Defaulting Rules` 是本文最接近的对照物：**实体×属性 + 有序规则 + 有效源 + 依赖 + 覆盖开关**，几乎就是 §8.3 草案表的原型。Fusion 则把"是否覆盖"降为规则里的一行 `Is Blank` —— 两种做法都指向同一条纪律：**覆盖策略必须是显式的、可读可审的**。

对我们：
1. **借 EBS 的"实体×属性 → 有序规则集"**：这正是我们规则表的**分组粒度**（`scope` = 目标属性阶梯）。
2. **借 EBS 的"System vs User Changes 开关"**：对应 `overwrite` 的两态（`blank_only` / `always`）。
3. **借 Fusion 的 `Is Blank`**：**覆盖条件可以写成规则里的一行条件**（我们更彻底 —— 做成列 `overwrite`）。
4. **警告（再判定例外）**：EBS 官方自己都会"没算出新值时保留旧值" —— 我们必须**显式规定**再判定的清空 / 保留，不能默认"先清空"。
5. **不引 Fusion 的版本分层为默认**：编排指派"规则本体不版本化"是**特例**（版本由被指派实体承担），我们是"规则本体带 `status`"（§8.3）。

---

## 5. Palantir：Ontology 层**没有**通用声明式规则引擎

这是本次研究一个**反直觉但重要**的结论：Palantir 的 Ontology **不提供“属性确定引擎”** —— 它把这层让给了 **Action 参数默认值 + Function 代码**。本节按五要素（触发 / 因子 / 条件 / 动作 / 次序·覆盖）**系统拆解**它的全部机制。

### 5.1 语义层：对象与属性**不带任何规则**【确定】

- 属性元数据只有：ID / Display name / Description / RID / Status / API name / Keys（title key、primary key）/ Base type / Value formatting / Conditional formatting / **Type classes** / Render hints / **Visibility**（prominent / normal / hidden）。
- **没有“属性级默认值”**：默认值**只出现在两处** —— ① Action 参数默认值；② Foundry Rules 输出字段的 permitted / default values。
- **必填**：官方 “**The primary key of the object type is a required property which has to be filled.**”；一般必填校验落在 Action 提交时的 **submission criteria**。

> **含义**：Palantir 把“**值从哪来**”完全移出对象定义，交给**动作**。对象只是“数据形状”，不是“取值规则”。这与 SAP 把规则烧进条件表 / 过程，是两种世界观。

### 5.2 动力学层①：Action Types —— 声明式确定（本文核心对照）【确定】

**(a) 参数默认值**（Palantir 版的“带出”）
- 可为**静态值**，也可为**另一个对象参数的属性值**；
- 官方：**“Only object reference parameters that are placed above the parameter in the input list are available to be used as a default value.”**（**只能引用排在上方的参数 → 顺序敏感**）
- 官方：**“Local default values (for example, Workshop variables) always take precedence over global default values.”**（**局部优先全局**）
- 支持 **type classes** 预填（如 UUID、当前用户 ID）。

**(b) Rules：四种赋值来源**

| 来源 | 含义 |
|---|---|
| From parameter | 取另一个参数的值 |
| Object parameter property | 取对象参数的属性值 |
| Static value | 常量 |
| Current User / Time | 系统变量 |

官方：**“The order of rules affects the final object edit.”** → **后写覆盖先写**（**顺序即语义**）。

**(c) Override blocks（if / then）** —— 动态改**约束 / 可见 / 必填 / 默认值**
- 条件**只能引用层级在其上方的参数**；
- 官方：**“if more than one is true, only the first one will be executed.”** → **首个命中即停**（与 SAP exclusive / EBS 首个命中同构）。

**(d) Submission criteria（提交条件）= 校验**
- 位于 Security & Submission Criteria；条件基于**当前用户或参数**；**全部满足才可提交**，否则弹 failure message **阻断**。
- **“只校验不提交”**存在：Apply Action v2 `options.mode` = `VALIDATE_ONLY | VALIDATE_AND_EXECUTE`；v1 有 `/validate` 端点返回 `VALID` / `INVALID`。

**(e) 参数级控制**：官方 **“Each parameter can be individually configured as to whether they are exposed in the Form or not, or whether they can be changed by the user or not.”** → **是否上表单、是否允许用户改，是参数级开关**。

**(f) 声明式与命令式互斥**：**Function rule 不能与其它规则并用**，须走 `@OntologyEditFunction`。

### 5.3 动力学层②：Functions —— 命令式逃生门【确定】

- v1：`@OntologyEditFunction` + `@Edits`；v2：`createEditBatch()` + `Edits`，返回 `OntologyEdit[]`；另有 Python SDK。
- **只有被配置为 function-backed Action 的 Function 才真正落库**。
- **Staged writes [Beta]**（原名 Ontology transactions）：**原子提交 / 回滚 / read-after-write**，可嵌套。
- 官方明说函数能**读多对象算值并写回**：“**compute a value based on some business logic that reads data from several objects, then write that value into an object property.**”

### 5.4 计算的三处落点（对标 §8.9 的 `compute`）【确定】

| 落点 | 何时算 | 落库 | 典型 |
|---|---|---|---|
| **Pipeline transform**（pre-computed） | 写时 | ✅ | `fullName = firstName + " " + lastName` |
| **Derived property [Beta]** | **读时** | ❌ 只读 | 沿 link 聚合（Count / Avg / Sum / Min / Max / Cardinality / Collect list·set，**≤3 跳**） |
| **Function-backed Action** | 写时 | ✅ | 读多对象算复杂值再写回 |

**★ 重要修正**：derived property 的官方限制**只有** —— **read-only、不能被 function / action 编辑**；不能标 required（非空）、不能作 primary key、不能有 type constraints、不能挂 rule set bindings / base formatters；OSv1 对象不能同查；不能用于文本搜索；仅 **scheduled monitoring** 下可作 Automate 条件。

→ **官方页面并未出现“不能用于 defaulting”或“只用于展示 / 过滤 / 排序 / 聚合”字样**【未找到】；“**不可当默认源**”是**由 read-only 反推的结论**【基本确定】。（原稿 v1.0–v1.6 写作“官方明说”，**属过度断言**，v1.7 修正。）

> 与我们 **`enrichment_engine`（读时 JOIN 填充）** 同构：读时派生**只服务显示**；且它**连 required 都不能标**，更不可能充当写侧默认。

### 5.5 Foundry Rules（原 Taurus）：另一条独立产品线【基本确定】

- 官方：**“Foundry Rules (previously known as Taurus) enables users to actively manage complex business logic in Foundry with a point-and-click, low-code interface.”**
- 面向 **dataset 的行**：“**a rule is a set of conditions that ... specify particular rows of data in a dataset.**”
- 组件：**Rule Editor**（表单由创建规则的 Action 参数自动生成；本质是“接受 Foundry Action 的 widget”）、**Proposal Reviewer**（提案审批）、只读 **Rule Viewer**。
- 执行：**批处理 / 按计划**（“these two datasets can be placed on a schedule”）；输出为 **output dataset 的行·列**（告警 / 分类 / cohorting）；输出字段可配 **required** 与 **permitted / default values**（“Default values will automatically be assigned when a new rule is created.”）。
- **修正**：原稿写的组件名 `TaurusRuleRunner` **未在官方页面找到**【未找到】 —— 官方口径是“规则执行 = pipeline”，并非独立 Runner 组件。

> **定位**：Foundry Rules **不是对象级属性确定**，而是“**对数据集批量打标 / 分类 / 告警**”的规则产品线。它与 Action 参数默认值是**两条互不相干的线**。

### 5.6 邻域：AIP Logic 与 Automate（划界，非本模型）【确定】

- **AIP Logic**：官方 “a no-code development environment for building, testing, and releasing functions powered by LLMs” —— **LLM / 自然语言驱动，非声明式**；产物是 Function，可被 Action / Automate 调用，也可 “make edits to the Ontology”。
- **Automate**：官方 “define conditions and effects. Conditions are checked continuously, and effects are executed automatically when the specified conditions were met.”；**Object Monitors 已被 Automate 取代**。
- → 二者是“**条件 → 动作**”的**流程自动化**，**不是属性确定**，印证 §10.5 的邻域划界条款。

### 5.7 可解释性：Action Log + Test run【确定】

- **Action Log**：与 Action type 一一对应，记录 Action RID、type 版本、时间、用户、被编辑对象主键、可选参数值。
- **Test run**：返回**逐步执行日志**（submission criteria → 参数校验 → edits 计算），**且不落库** —— 即“**干跑回放**”。

> 这条**补强了** §7 C9：可解释性**不止 Oracle**。Palantir 的 Test run 是**声明式引擎之外**的另一条回放路径；代价是它回放的是“**动作**”，不是“**规则表命中了哪一行**”。

### 5.8 Palantir 五要素小结

| 要素 | Palantir 的回答 |
|---|---|
| ① 触发 | **提交时**（Action 执行）；override / 参数校验在**填写过程中**动态生效 |
| ② 因子 | Action 参数（含对象引用参数）；**引用方向受“只能向上”约束** |
| ③ 条件 | Rules 四种来源映射；Override block 的 `if`；Submission criteria |
| ④ 动作 | 静态值 / 从参数 / 对象属性 / 当前用户·时间 / Function |
| ⑤ 次序·覆盖 | **后写覆盖先写** + override **首个命中** + 参数级“是否允许用户改”；**无独立规则表 → 无集中式规则审计** |

### 5.9 Palantir 结论

> **Ontology 层没有通用声明式规则引擎。** 属性自动判定由三处拼出：**① Action 参数默认值（声明式）+ ② submission criteria / override（校验·收窄）+ ③ Function 代码（命令式）**。这与 SAP / Oracle 的“独立确定引擎”是两条路 —— **Palantir 用“动作即规则”消解了规则引擎。**

对我们：
1. **别为规则而规则** —— 若某确定逻辑只在单点使用、无复用与审计要求，塞进 hook 即可（C8 逃生门）。
2. 但代价要看清：**没有独立规则资产，就没有规则级的统一审计面** —— Action Log 记的是“动作与结果”，不是“哪条规则为什么命中”。
3. 可借两点：**参数级“是否允许用户改”开关**（对应我们的 `overwrite`）；**Test run 干跑回放**（对应我们的可解释性目标）。
4. 须警惕：Palantir 的**顺序即语义**（只能向上引用、后写覆盖）是**隐式**的 —— 我们应显式化（`seq` + `scope` + `is_fallback`，§8.8）。

---

## 6. Salesforce 系统拆解 与 声明式规则 DSL 广度坐标

§5 的 Palantir 是"**没有规则引擎**"的极端；Salesforce 是另一个极端 —— **一台声明式引擎（Flow）+ 一张显式的执行次序表（Order of Execution）**。它对本专题的价值在于：**"带出"的时机、覆盖、次序三件事，都被产品写成了白纸黑字**。

### 6.1 两种时机：before-save vs after-save【确定】

| 时机 | 官方名 | 语义 |
|---|---|---|
| **before-save** | **Fast Field Updates** | 在同一条记录的**保存事务内、写库之前**执行；直接改写 **`$Record` 内存值** |
| **after-save** | **Actions and Related Records** | 保存**之后**执行；走 **DML**（可跨对象），可递归 |

官方原文（before-save 的关键性质）：

> "they don't consume additional DML operations or re-trigger the save order of execution."

**含义**：**before-save 零额外 DML、不重入保存执行顺序** —— 这正是要素①"保存前内存改写"的**教科书样本**（C2）；也正因如此：

- **不跨对象**（要跨对象必须 after-save）；
- **不触发**其它保存期逻辑（无递归）。

### 6.2 覆盖语义：before-save 直接写 `$Record`【基本确定】

- before-save flow 直接赋值 `$Record.Field = ...` → **用户已录入的值会被覆盖**；
- 要保留用户输入，必须**自己判空**（`ISBLANK(...)`）再赋值 —— 即 **"仅空值才填"由用户手写实现，不是引擎默认**。
- **★ 未找到**：**字段默认值 vs Flow 默认值的先后顺序**【未找到】—— 官方未给出明确次序，**不作为结论**。

> 对照 Fusion 的 `Is Blank`：**两家都把"别覆盖用户值"交给规则/公式自己表达** —— 再次印证 C3：**覆盖语义必须显式**。

### 6.3 次序：Flow Trigger Explorer 显式排 Trigger Order【确定】

- **多条 before-save flow 的执行顺序不保证**；
- 官方提供 **Flow Trigger Explorer** 让用户**显式指定 Trigger Order**；
- **★ 修正**：该顺序**不是字母序**（原稿隐含的"按名排序"不成立）。

> 与 SAP 存取顺序 / EBS 顺序号同构：**"谁先判"必须显式**；不定义 = 结果不确定（§8.8 ⑥ tie-break）。

### 6.4 站位：Order of Execution 里的步骤号【确定】

Salesforce 把"一条记录保存"的全过程写成**编号步骤**，本专题相关的几步：

| 步 | 内容 |
|---|---|
| **3** | **before-save flows**（Fast Field Updates） |
| **4** | **before triggers**（Apex，命令式） |
| **5** | **自定义校验规则（Validation Rules）** |
| **6** | **duplicate rules** |
| **7** | **保存到数据库** |
| **8** | **after triggers** |
| **14** | **after-save flows** |
| **16** | **roll-up summary 字段** |

**读法**：**确定/带出（3）→ 校验（5）→ 落库（7）→ 计算汇总（16）** —— 五要素里的"触发"与"次序"，Salesforce **给了一张产品级的完整站位图**。

### 6.5 校验：Validation Rules（第 5 步·阻断）【确定】

- 时机：**第 5 步**、**落库前**；不通过则**阻断**整条保存；
- 结果类型 = **布尔·阻断** —— 正对 §10.2 的"校验 validation"一格。

### 6.6 计算：Formula Field（只读·读时算·不落库）【确定】

- **只读**：用户改不了，**也不能被其它规则写**；
- **读时计算**（run-time），**不落库**；
- 因此**不能反过来充当默认值来源**（与 Palantir derived property 同一性质，C6）。

→ 对应 §8.9 的 `compute`：**确定（before-save）与计算（Formula Field）分立**。

### 6.7 字段默认值 与 Dynamic Forms【确定】

- **字段默认值**：字段定义上的静态默认（"带出"的最弱形态）；
- **Dynamic Forms**：**Lightning App Builder 组件级**的声明式能力，控**可见 / 必填** —— 与本平台 `field_policy_engine`（可见/必填策略）同族，**结果不是"值"**。

### 6.8 邻域：审批 / 编排 / Apex（划界）【确定】

| 族 | 归属 | 口径 |
|---|---|---|
| **Approval Process** | 审批体系 | 管"谁批"，非取值 |
| **Flow Orchestration** | 流程 · 任务编排 | 管"步骤序列" |
| **Apex Trigger** | **命令式逃生门** | 官方：**"the order of trigger execution isn't guaranteed"** |

→ 三者均**非"因子 → 值"**，属 §10.5 邻域，**不并入规则表**（Apex 对应 C8 逃生门）。

### 6.9 Salesforce 五要素小结

| 要素 | Salesforce 的回答 |
|---|---|
| ① 触发 | **before-save（零 DML / 不重入）** vs **after-save（走 DML / 可递归）** |
| ② 因子 | 当前记录字段；after-save 才可取关联记录 |
| ③ 条件 | Decision 元素（布尔 / 公式条件） |
| ④ 动作 | Assignment / Get·Create·Update·Delete Records / Loop |
| ⑤ 次序·覆盖 | **Trigger Order 显式排序**（非字母序）；**覆盖须自己判空**（`ISBLANK`）；落在 **Order of Execution 第 3 步** |

### 6.10 其余三家横向坐标（D365 / Odoo / 金蝶）

补三家主流声明式规则工具，与 Salesforce 并列成"规则 DSL 长什么样"的横向坐标：

| 产品 | 机制 | 触发 | 覆盖语义 | 备注 |
|---|---|---|---|---|
| **Dynamics 365** | **Business Rules** | **Scope 决定时机**：Entity=客户端+服务端；All forms=仅客户端；Specific form | 动作含**设置默认值 / 设置·清除列值 / 校验 / 必填级别 / 显示隐藏 / 启用禁用 / 建议**；**表单保存事件不应用业务规则**，服务端在 **before** 阶段 | 边界：业务规则 → 低代码插件（pre/post-operation）→ 实时工作流 → Power Automate → C# 插件 |
| **Odoo** | `compute` + `inverse` + `@api.depends`；**`@api.onchange`** | onchange = **UI 默认带出**（伪记录、保存前生效、不持久化） | `store=True` 才落库；**有 `inverse` 才可写**；`related` 字段、`default`/`_default_xxx`/`default_get` | **Automated Actions（base_automation）** 做声明式，触发器含 **On create and edit / Values Updated / On UI change** |
| **金蝶云·星空** | **BOTP 单据转换** + **值更新事件** | 转换（跨对象）；**值更新事件 = 基础资料带出（onchange 式）** | 字段映射取值方式：**源单字段 / 计算公式 / 按条件取值 / 常量** | 原厂规则不可改，须**扩展（差量叠加覆盖）或继承（同步上游）**做版本治理；**运行时可见 / 默认选用此规则 / 规则启用条件 / 启用** |

### 6.11 这份坐标给的共性

- **before-save / onchange 是主流"带出"时机**（C2）；
- **"先判空再赋值"是主流覆盖语义**（C3）；
- **Scope / 触发点决定客户端还是服务端**；
- **"谁先执行"必须显式**：Flow Trigger Order / Odoo `depends` 顺序 / 金蝶规则集顺序 —— **不定义 = 不确定**（§8.8 ⑥）。

---

## 7. 跨产品共性规律（本文结论）

七家产品（SAP / Oracle / Palantir / Salesforce / D365 / Odoo / 金蝶）拆完，规律高度收敛：

| # | 规律 | 各方证据 |
|---|---|---|
| **C1** | **骨架统一为 `触发 + 条件 + 动作`**（When / If / Then），本专题再加**因子**与**次序·覆盖**共五要素 | 全部七家 |
| **C2** | **保存前内存改写是"带出"的主流时机**：零 DML、可被用户覆盖、不产生常规审计 | SAP 替代、Salesforce before-save、Odoo onchange、金蝶值更新 |
| **C3** | **覆盖语义必须显式**，只有两种正统做法：**① 仅空值才填**（Salesforce 判空 `ISBLANK`、Fusion `Is Blank`）；**② System/User 开关**（EBS Processing Constraints） | Salesforce / Fusion / EBS |
| **C4** | **确定次序 = 顺序号 + 首个命中**（exclusive）为主流，且**必须定义 tie-break**；**取最优（Best Price）是定价专属**，不要混用 | SAP 存取顺序、EBS Defaulting Sequence（**同序按字母序**）、Oracle Pricing |
| **C5** | **范围收窄是"带出"的孪生需求**：因子不仅定值，还应收窄候选集 | Palantir 动态参数约束、D365 显示/必填动态化 |
| **C6** | **展示用派生 ≠ 写入用默认**：读时算的不能当默认源 | Palantir derived properties（官方声明 **read-only、不可被 action / function 编辑**【确定】→ **机制上无法当默认源**【基本确定】）；本平台 enrichment 同构 |
| **C7** | **规则本体 vs 被引用物分层做版本**：规则轻、被指派的实体重 | Fusion 编排指派规则（规则本体不版本化） |
| **C8** | **必须留命令式逃生门**：声明式覆盖 80%，剩余走函数/例程 | SAP EXIT/VOFM、Fusion Groovy、Palantir Function、D365 插件 |
| **C9** | **可解释性 = 能回放“为什么带出这个值”** | Oracle Pricing Engine Request Viewer（定价最完整）；**Palantir Action Log + Test run（干跑逐步日志、不落库）** |
| **C10** | **再判定必须显式规定"清空 or 保留"** —— 主流是"先清空重算"，但**官方自己就有例外**：EBS 再默认**未算出新值时保留旧值** | EBS Defaulting Dependencies（官方原文 "the old value would be retained instead of clearing"） |

---

## 8. 对本平台的接缝与建议

### 8.1 资产定位：**不要塞进 `doc_flow_rule`，也不要塞进权限规则**

| | 一类 `doc_flow_rule` | 二类 权限规则 | **三类 属性确定（新）** |
|---|---|---|---|
| 范围 | 跨对象 | 单对象字段 | **单对象内** |
| 是否产生"数量" | 是（数量池/幂等键） | 否 | **否** |
| 语义 | 派生边 | 判定布尔 | **条件 → 值** |
| 违反后果 | 账算错 | 越权 | **字段填错** |

**SAP 用两套机制（VOFM vs 条件技术）分开这两件事，我们也应分开**（§3.4）。同理也不并入条件权限——**权限规则产出布尔，不产出值**。

### 8.2 落点：平台**已经有**两块可以直接复用的接缝【代码级确认】

| 接缝 | 现有能力 | 与本文的关系 |
|---|---|---|
| [field_policy_engine.py](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py#L40-L75) | **`PolicyRule(when_expr, value, default)` + `determination: List[PolicyRule]` + `default`，首个命中语义**（[evaluate 逻辑](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py#L249-L259)） | **已有"条件 → 值"的完整骨架！**只是当前用途是 visible/editable/required。**属性确定可以复用同一 `PolicyRule` 形态，新增一类 determination（value 型）** |
| [persistence_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L27-L37)（priority=95） | **写前拦截**，可在落库前改写数据；已 import `AssociationEngine` / `EnrichmentEngine` | ~~**"保存前内存改写"的天然落点**（对标 C2）~~ **（口径修正，v1.10）** 非本文落点，见下方修正说明 |
| [condition_parser.py](file:///d:/filework/excel-to-diagram/meta/core/condition_parser.py) | `when_expr` 表达式解析 | 三类规则共享的条件基础设施 |
| [enrichment_engine.py](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L1-L24) | **读时填充**（JOIN 虚拟冗余字段，注释自称对标 SAP CDS / Salesforce Formula / Palantir derived property） | **这是"展示"，不是"默认"**——正因如此，**属性确定必须另做写入侧**（C6） |
| [action_executor.py](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L868-L872) | `ActionType.CRUD / BATCH / BUSINESS` + [`register_handler`](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L2937) | **命令式逃生门**（对标 C8）与批量再判定入口，同时是属性确定的**实际调用点** |
| [rule_executor.py](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1039) | `RuleEngine` + `MetaObject.rules` + `SafeExpressionEvaluator` | **属性确定的真实落点**（见下方修正说明） |

> **重要**：`field_policy_engine` 的 `PolicyRule` 形态、`persistence_interceptor` 的写前时机**都已存在**。所以本专题**不是"从零造引擎"**，而是**"把已有的条件-值能力，从权限语义扩展到取值语义"**——改动面远小于直觉。

> **落点口径修正（v1.10，2026-10-03，实施后回填）**：本文原判「`persistence_interceptor`（priority=95）是"保存前内存改写"的天然落点」**未采纳**。实施时核实：属性确定需要**五要素齐备**（触发/因子/条件/动作/次序·覆盖）与**分组+首个命中**语义，而 `persistence_interceptor` 只是拦截器管线中的一个时机点，不承载规则模型与求值器。实际落点为 **`RuleEngine`（`rule_executor.py`）新增 `DefaultExecutor` + `RuleEngine.default_by_priority`，由 `action_executor` 在 `BEFORE_SAVE` 校验之前调用**（`_do_create` / `_do_update` 两处）。`persistence_interceptor` 保持原职责不变。

### 8.3 建议的规则资产形态（草案，待专项设计）

对照 §2 五要素与 §7 十条共性，一张**确定规则表**最少需要这些列（与 `doc_flow_rule` 同风格：`app.yaml` 声明 = 能力，`status` = 运行态）：

| 列 | 对应要素 | 取值示例 | 共性依据 |
|---|---|---|---|
| `rule_id` | — | `order_contract_def` | — |
| `kind` | **语义类型** | `default`（确定，可改）/ `compute`（计算，只读） | 两类语义不可混（§8.9） |
| `target_bo` / `target_field` | 结果落点 | `sales_order` / `contract_id` | 表头 vs 明细（用户原话"表头或明细"） |
| `scope` | **分组** | `contract_def` / `pricing_term` | **优先级只在同组内有效**（§8.8） |
| `factors` | ② 因子 | `["order_type","line_type","customer","material","material.materialgroup"]` | 条件表（SAP）；**支持点路径**（主数据属性作为因子，见 §8.7） |
| `factor_freeze` | ② 因子·冻结 | `[]` / `["material.materialgroup"]` | **需审计回放的因子才落行快照**；默认不落（§8.7） |
| `depends_on` | 计算依赖 | `["quantity","price","customer_type"]`（仅 `kind=compute`；**须含条件因子**） | **依赖图 / 重算触发**（§8.9 ⑦） |
| `when_expr` | ③ 条件 | `order_type='OR' AND customer.group='KA'` | 复用 `condition_parser` |
| `value_source` | ④ 动作 | `constant` / `field` / `lookup` / `expr` / `hook` | EBS Source 五种 |
| `value_payload` | ④ 动作 | 具体值 / 源字段名 / 查表键 | — |
| `seq` | ⑤ 次序 | **组内** 10 / 20 / 30（**首个命中即停**） | C4；**组内有序**（§8.8） |
| `is_fallback` | ⑤ 兜底 | `true` = else 行（建议 `seq=999`） | **阶梯无兜底 = 有空洞**（§8.8） |
| **`overwrite`** | ⑤ 覆盖 | `blank_only` / `always` / `never` | **C3，必做显式列** |
| `status` | 运行态 | `active` / `deprecated` | 复用 `doc_flow_rule` 的"停新不禁旧" |
| `readonly_after` | 覆盖控制 | 带出后是否锁死 | SAP GB01 / EBS 处理约束（Require Reason 等） |

> **平台实现口径（v1.10，2026-10-03，实施后回填）**：本表的「`scope`（组）+ `seq`（组内序）」落到平台时，映射为 **`MetaDefaultRule` 的**分组键 `target_field` + 组内序 `priority`**（升序；**同 `priority` 以 `rule.id` 字典序 tie-break**）。注意与既有语义的差异：`RuleEngine` 现有的 `priority` 是「**全局排序 + 全部执行**」（`_compute_by_priority`，服务于 COMPUTATION 等）；**DEFAULT 不复用它**，而走专用分支 `RuleEngine.default_by_priority`（**按 `target_field` 分组 + 组内首个「命中且实际写入成功」获胜**，其后同组规则记 `not_first_match` 跳过）。两套语义**并存但隔离**，互不影响 —— 又一次印证 §8.6「概念通用 ≠ 引擎合并」。

**三条落地纪律**（直接来自共性）：
1. **覆盖策略必须是数据列，不是引擎黑盒**（Fusion `Is Blank` 教训，C3）。
2. **再判定须显式规定"清空 or 保留"**——默认"因子变了先清空重算"，但要写明**清空例外**（EBS 官方：未算出新值则保留旧值，C10）。
3. **留 hook 逃生门**——`value_source=hook` 走 `ActionType.BUSINESS`（C8）。

### 8.4 与对象模型总纲的接缝

- **§5.4 一个对象放几个量**：**确定带出的是"属性值"，不是"量"**。带出一个合同号、一个行类型，不触及"第二个量"的判定；但若规则想"按客户带出一个默认数量"，则该量须过 [总纲 §5.4](file:///d:/filework/docs/superpowers/specs/2026-09-30-object-model-guideline-plan-vs-fact.md) 三问——**"是不是上游计划量的活拷贝"**，是则**不加**。
- **§5 关联在边上**：确定规则**只写属性字段，不写边**。凡涉及"这条单派生出哪条单"的，一律归 `doc_flow_rule`（一类），**不准用确定规则偷偷建关联**。
- **§1 计划/事实**：带出只改变**当前对象的字段**，不改时态归属。用户后续变更 = 计划类对象的正常可变性。

### 8.5 与用户原话场景的逐句映射

| 用户原话 | 机制回答 |
|---|---|
| "根据录入的元素，如订单类型、行类型、客户、物料" | ② 因子 = `factors` 条件表 |
| "自动确定其他的属性" | ④ 动作（常量/字段/查表） |
| "确定合同" | ④ 动作（`lookup` 查合同表，条件命中） |
| "确定 xxx" | 同一台引擎，不同 `target_field`（SAP 五类确定过程同机） |
| "填入单据表头，或者明细的字段" | `target_bo` + `target_field`，头/行两套（EBS **可配置级联** 头→行） |
| **"有的时候用户可以进一步变更"** | ⑤ **`overwrite=blank_only`**（C3）——**系统只在空值时带出，用户填了就不覆盖** |

### 8.6 架构边界条款：**共享条件内核，不合并求值器**

> 回应一个易被误判的问题：**权限条件配置是不是"通用规则模型"？**
> **结论：一半对**——它是"**条件求值**"这一半的通用内核 + "**判定型**"的结果；而属性确定要的是"**取值型**"结果。**概念通用 ≠ 引擎合并。**

平台现存**四处**"条件 → 结果"资产，**条件内核同构、结果类型不同**：

| 资产 | 因子空间 | 条件内核 | **结果类型** | 取数语义 | 触发时机 |
|---|---|---|---|---|---|
| `doc_flow_rule`（一类） | 源单字段 | 条件表 / 池 | **边 + 数量** | Σ 池校验 | 派生时 |
| [condition_permission_service](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L343-L393)（二类） | **用户主体（角色）** + 资源字段 | ConditionRuleBuilder + [`_expand_condition_anchors`](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L283-L315)（bizkey 动态锚定 / instance 快照） | **布尔**（allow/deny，`_check_denied_rules` 先判 → **deny 优先**） | 多规则**合并** | 每次**读/写**访问（高频） |
| [field_policy_engine](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py#L40-L75)（二类·字段策略） | 用户主体 + 行数据 | `PolicyRule(when_expr, value, default)` | **布尔**（visible / editable / required） | **首个命中** + default | 访问评估 |
| **属性确定规则（三类·新）** | **纯业务字段**（无"谁"） | 复用上两者 | **值**（合同号 / 行类型） | **首个命中** | 仅创建/更新**保存前**（低频） |

**可共享的内核（三处，应抽为公共层）**：

1. 条件表达式解析 —— [condition_parser.py](file:///d:/filework/excel-to-diagram/meta/core/condition_parser.py)
2. 条件行编辑 UI —— ConditionRuleBuilder（field / operator / value）
3. 动态锚定语义 —— bizkey 动态锚定 vs instance 快照

**不可合并的三条硬理由**：

| # | 理由 |
|---|---|
| 1 | **结果类型不同**：布尔判定 vs 取值 —— 两种求值器，**输出域不同**，不能互相替代 |
| 2 | **性能画像相反**：权限是**读时高频**，属性确定是**写时低频**；硬合并会让写路径背上读路径的开销 |
| 3 | **因子空间多一维**：权限 / 字段策略带"**谁**（用户主体）"，属性确定不带 |

**条款**：属性确定规则应 **复用条件内核 + 新增一个"取值"求值器**（首个命中 + `overwrite` 覆盖策略）——**既不重写条件表达式，也不把权限引擎"升级"成通用引擎**。

**行业佐证**：SAP 把"条件技术"作为**理念**共享，但定价/合作伙伴/批次各是**独立过程**；Salesforce 共享条件构建器 UI，但 Flow / 校验规则结果类型各异（§3.2、§6）。

### 8.7 因子取值：**路径解析 vs 行内快照**

> 回应："因子可能包括**主因子的属性**（如 `material.materialgroup`）——**是否必须把它 copy 到单据行**（单据行上必须要有这个属性）？"
>
> **结论：不必须。** 需把两个**正交**问题拆开 —— **① 取值路径**（值从哪来）与 **② 冻结需求**（要不要在行上留快照）。

**① 取值路径三型**：

| 型 | 说明 | 平台先例 |
|---|---|---|
| **本地字段** | 行上已有（`order_type`） | — |
| **点路径解析** | `material.materialgroup`，求值时沿 join_path 取主数据 | [enrichment_engine](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L1-L24)（读时 JOIN 填充，对标 SAP CDS / Salesforce Formula / Palantir derived property） |
| **锚点解析** | 维度业务键 → ID，求值时解析 | 权限规则 [`_resolve_anchor_ids`](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L174-L186)（**资源行上并不存该维度**） |

**关键证据（代码级）**：权限规则**已经在做"跨实体因子求值时解析、不落行"**——[`_expand_condition_anchors`](file:///d:/filework/excel-to-diagram/meta/services/condition_permission_service.py#L271-L315) 把 `anchor in ('bizkey…')` 展开为 `anchor in (id…)`，而**资源行上没有这个维度列**。故本平台的既有形态是 **规则存"因子声明"，求值时现算**，而非把因子拷进行。

**② 何时必须落库（行内快照）—— 三种情形**：

| # | 情形 | 为什么 |
|---|---|---|
| 1 | **要事后回放"当时为什么带出该值"**（审计/举证，C9） | **主数据会漂移**：物料今天 G1、明年改 G2；join 重算得**不同答案**，回放失真 |
| 2 | **要监听因子变化并重算**（EBS Dependencies，C10） | 因子不在场，无"变化"可监听 |
| 3 | **前端需即时带出、且客户端拿不到该属性** | 要么随主数据记录取回，要么落行 |

**③ 一条易漏的区分：落"结果"必落库，落"因子"看需求**

- **确定的产物（`contract_id`）→ 必须落库**（无选择）
- **因子（`material.materialgroup`）→ 不必须落库**：**结果本身已是快照** —— 合同号存下即"当时按 G1 定成 C1"已固化；因子只在**要重新演绎**（回放/重算）时才需要

**④ 平台特有硬约束：多应用库路由**

平台 `APP_DB_ROUTING=1`（[persistence_interceptor](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L58-L68)）。**若主数据与单据行不在同一库**，写时"一次 SQL join"不可得 → 只能**服务调用取回**或**落行携带**；此时落库由"可选"变为"工程更省事"。

**⑤ 决策表**：

| 场景 | 因子取值 | 因子落库 | 结果落库 |
|---|---|---|---|
| 仅建单时算一次、不要求回放 | 点路径 / 锚点解析 | ❌ | ✅ |
| 要审计回放 / 举证 | 解析 | **✅ 快照**（`factor_freeze`） | ✅ |
| 因子变更要触发重算 | 解析 | ✅（或记变更日志） | ✅ |
| 前端即时带出、客户端无该属性 | 随主数据带 | ⚠️ 或随记录取回 | ✅ |
| 因子跨应用库 | 服务调用 | ⚠️ 倾向落库 | ✅ |

**⑥ 与总纲同向**：本条与 [总纲 §5.4](file:///d:/filework/docs/superpowers/specs/2026-09-30-object-model-guideline-plan-vs-fact.md) 的"**上游活拷贝 ❌ 不加 —— 要显示就 join 上游**"完全一致。`material.materialgroup` 属同类 —— **它是主数据的活拷贝，不是本单据的断言**：默认不落行，解析取值即可。

**一句话**：**不必须 copy 到单据行** —— 默认"**因子路径解析 + 只落结果**"；仅在"**要回放 / 要监听变化 / 前端拿不到 / 跨库**"时，才把**因子**（而非结果）快照落地。

### 8.8 多条规则行的优先级与阶梯求值

> 回应："规则需要**多条规则行的优先级** —— `if 物料组 in xx and 行类型 = xxx then… elseif 物料组 in xx then…`"
>
> **要点：规则集不是平表，而是"按目标分组的、有序的、首个命中的阶梯"。**

**① 先分组，再排序** —— 优先级**只在同一确定目标内**有效

- 分组键 = (`target_bo`, `target_field`, 场景) → 落为 `scope` 列
- **跨组规则互不干扰**：定"合同"的规则与定"付款条件"的规则各是一个**独立阶梯**
- 先例：SAP 用**过程（Procedure）**把条件类型排序；Oracle 编排指派用 **If / Else-If / Otherwise**

**② 阶梯语义 = 互斥，首个命中即停**

- `if / elseif / else` 是**互斥**的：命中第一条即停，**后面的不再看**
- 同构：SAP **exclusive** 条件记录；**Fusion 编排指派 If / Else-If / Otherwise**、**Palantir Override blocks "only the first one will be executed"**、**Salesforce Flow Trigger Order**（均"首个命中即停"，只是次序载体不同）
- **平台已有**：[field_policy_engine](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py#L40-L75) 的 `determination: List[PolicyRule]` + 首个命中

**③ 排序两种范式（必须显式二选一）**

| 范式 | 机制 | 先例 | 风险 |
|---|---|---|---|
| **显式顺序号** | `seq` 小者先判 | SAP access sequence、EBS defaulting sequence（**同序按字母序**）、金蝶规则集顺序 | 需人工维护顺序 |
| **特异性自动排** | 匹配因子越多越优先 | SAP 条件表"最具体 → 最一般" | **"猜不到为什么"**；连 Oracle Fusion 都**明文要求用户自己排成 most specific → least specific** |

**建议**：**以显式 `seq` 为主**（可控、可解释），附加"**特异性倒置检查**"作辅助告警（见 ④）。

**④ 用户例子正解：更具体的必须排前面**

```
seq 10  if 物料组 in {G1,G2} and 行类型 = 'TA'  → ...
seq 20  if 物料组 in {G1,G2}                   → ...   ← 更一般，必须靠后
```

- `物料组 + 行类型` 比 `物料组` **更具体** → 必须在前
- 若用户漏排 → 引擎应**检测"更一般的规则排在更具体之前"并告警**（不是静默按 seq 执行）
- 集合匹配（`in {…}`）计为**一个因子的匹配**，参与特异性比较

**⑤ 必配 else 兜底** —— **阶梯无兜底 = 有空洞**（某些因子组合永远无值）

| 产品 | 兜底机制 |
|---|---|
| EBS | 末位顺序号兜底行（seq 最大者） |
| Oracle Fusion | `Otherwise` 分支 |
| Palantir | 全局参数默认值 |
| **平台** | `PolicyRule.default` + `is_fallback` 列 |

**⑥ tie-break 必须确定**（同 `seq` 怎么办）

- EBS：同序号按**字母序**；SAP：access 号码
- **不定义 tie-break = 结果不确定 = 不可解释** → 平台须明文规定（建议：同 `seq` 按 `rule_id` 字典序）

**⑦ 优先级 vs 覆盖：正交，勿混**

| 列 | 决定 | 语义 |
|---|---|---|
| `seq` | **哪条规则赢** | 选规则（互斥、首个命中） |
| `overwrite` | **赢了之后写不写** | 用户已填值时是否覆盖 |

**高优先级的规则也完全可以 `blank_only`**（不覆盖用户值）——**两者独立**。

**⑧ 跨阶梯有依赖顺序**（非平级）

- 若"先据物料定合同 → 再据合同定付款条件" → 是**两个阶梯**，且**阶梯之间有依赖序**
- 对标 EBS **Hierarchical Defaulting**（Header → Line 级联）
- 落地：声明阶梯的**求值次序**，或由依赖关系**拓扑排序**；**禁止把依赖关系藏进 seq 数字里**

**⑨ 变更影响**：调整某条 `seq` 会**改变历史行为** → 需变更审计；若要求"按当时规则复现"，则阶梯需**生效期/版本**（对标 EBS 处理约束的版本控制）

**一句话**：`seq` 定胜负、`overwrite` 定覆盖、`else` 定兜底、tie-break 定确定性、`scope` 定范围、阶梯间次序定依赖。

### 8.9 计算规则：对象内的属性派生（与"确定"并列的第四类）

> 回应："规则是否包括**对象内属性的计算规则** —— `金额 = 数量 × 单价`，而**单价是其它规则确定的**？"
>
> **是同一规则模型家族，但是与"确定"并列的第二种子类** —— §1 按**平台现有资产**切成三类；本节说的是：第三类（属性确定，尚缺）在语义上**还必须再分两支**：`default`（确定）与 `compute`（计算）。

**① 两支的语义差异（不可混）**

| 轴 | **确定 default** | **计算 compute** |
|---|---|---|
| 触发 | 创建/更新时带一次 | **依赖字段一变就重算**（实时 / 写时） |
| 可覆盖 | 用户**可改** | **只读**（改了没意义，重算又冲掉） |
| 真值 | 外部 / 规则 | **本对象其它字段的纯函数** |
| 落库 | 落（是产物） | **默认可不落**（读时算） |
| 依赖 | 因子（§8.7） | **必须声明 `depends_on`** |

**② 七家全部把两者分开 —— 无一例外（这不是风格，是共识）**

| 产品 | 确定 / 默认带出 | 计算 / 派生 |
|---|---|---|
| SAP | 条件技术的 **access step** | 过程里的 **calculation step**（基值 / 公式、VOFM 公式） |
| Oracle EBS | Defaulting Rules | Pricing 的 **formula** / 视图 |
| Oracle Fusion | **Pretransformation Defaulting Rules** | 引擎内建公式（`Amount = Qty × Price`）/ Pricing Formulas |
| **Palantir** | Action 参数默认值 | **三处并列**：pipeline transform（写时落库）/ derived property（读时只读）/ Function-backed Action（写回） |
| Salesforce | before-save Flow | **Formula Field**（只读、读取时算） |
| Odoo | `@api.onchange` | **computed field**（`compute` + `@api.depends` + `store`；**有 `inverse` 才可写**） |
| D365 | Business Rule"设置默认值" | **Calculated Column**（只读、服务端算） |

> **合并的代价**：会造出"**用户改了金额，但单价一变又被冲掉**"这种无法回答的状态。

**③ 用户的例子是一条依赖链（DAG）**

```
规则A（kind=default）: 条件 → 单价           ← 外部带出，可改
          ↓  depends_on
规则B（kind=compute）: 单价 × 数量 → 金额     ← 纯函数，只读
```

- **执行顺序**：先确定（出单价）→ 再计算（出金额）—— 正是 §8.8 ⑧ 的"跨阶梯依赖次序"
- 依赖须**自动成图**（对标 Odoo `@api.depends` / Salesforce Formula 自动依赖 / Palantir derived 链）；**手工维护依赖必然漏**

**④ 落库决策沿用 §8.7 同一判据**

- **不落库**（读时算）：永远自洽，但**历史值随单价改而漂移** → 审计失真
- **落库（快照）**：冻结当时金额；代价是单价/数量变时**必须触发重算**
- **判断**：**金额是"本单据的断言"（当时的钱）→ 通常要落库**；单价若按 §8.7 解析而来，则"是否冻结"用**同一判据**

**⑤ 平台接缝**

- `value_source=expr` 已在 §8.3 —— **计算规则是它的显式化**，但**必须补 `depends_on`**，否则依赖变化时无法重算
- **读时算**走 [enrichment_engine](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L1-L24)（虚拟字段）路子；**写时算**走 [persistence_interceptor](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L58-L68)（保存前内存改写）
- **建议**：同一张规则表 + 一列 `kind = default | compute` **显式区分**——**不新增第四张表，但语义不含糊**

**⑥ 两支都支持条件 —— 条件是"共享的阶梯"，不是 `default` 专有**

条件可放在**两个位置**，各有先例：

| 位置 | 形态 | 先例 | 特点 |
|---|---|---|---|
| **A. 规则层条件**（阶梯） | 多条 `kind=compute` + `seq` + `is_fallback` | SAP 定价过程（access 选条件记录 → calc routine 算）、**Fusion Transformation Rules（`If / Then` 本身就是条件化计算）** | **可解释**（"命中 seq 10"）、可分别启停 / 改期 |
| **B. 公式内条件** | `金额 = IF(客户类型='大客户', 数量×单价×0.9, 数量×单价)` | Salesforce **Formula Field** 的 `IF()`、D365 **Calculated Column** | 自包含，一条规则 |

**建议**：**两者都支持，但优先 A** —— 可解释、可审计；B 只用于"公式内的小分支"。

> **关键**：`when_expr` / `scope` / `seq` / `is_fallback` **对两支都适用**（§8.8 的阶梯是共享的）。两支的差异**仅两处**：`overwrite`（compute 无意义——只读，改了会被重算冲掉）与 `depends_on`（compute 必需）。

**⑦ `depends_on` 必须包含"条件因子"** —— 这是最容易漏的一条

条件一变可能就**换到另一条公式**，所以依赖闭包 = **公式操作数 ∪ 条件因子**：

```
kind=compute, seq=10: if 客户类型='大客户' → 金额 = 数量 × 单价 × 0.9
```

依赖**不是** `{数量, 单价}`，而是 **`{数量, 单价, 客户类型}`** —— 否则"**改了客户类型，金额却不重算**"这个 bug 必现。

> **对照**：位置 B（公式内条件）天然含条件依赖（同一个表达式）；位置 A（规则层条件）需引擎**自动把条件因子并入依赖闭包**。

**一句话**：**确定是"条件 → 值（可改）"，计算是"条件 + 依赖 → 值（只读）"**；**条件与阶梯两支共享**，靠 `depends_on`（含条件因子）串成链，落库判据沿用 §8.7。

### 8.10 拆分/分摊 与 反向汇总：结果基数不是"一个值"的两类

> 回应："**从表头到明细行的拆分分摊，以及反向汇总，这算规则模型覆盖吗？**"
>
> **结论：都不算第三类覆盖。** 本文第三类的求值器输出**恰好一个值**；这两件事**结果基数不是 1** —— 拆分是 **1 → N**，汇总是 **N → 1**。它们属"同族但**另一台求值器**"（§8.6"概念通用 ≠ 引擎合并"的再一例）。

**① 拆分 / 分摊（1 → N）—— 比"集合确定"多一条硬约束：守恒**

| 轴 | 属性确定（本文第三类） | 拆分 / 分摊 |
|---|---|---|
| 结果基数 | 1 | **N**（多行） |
| 整体约束 | 无 | **守恒**：`Σ行 = 头` |
| 求值器 | 首个命中 → 一个值 | **分配算法**（等分 / 按比例 / 按明细金额 / 按数量…） |
| 失败模式 | 值带错 | **对不平（Σ ≠ 源）** |

**★ 关键**：**守恒是本文五要素（触发 / 因子 / 条件 / 动作 / 次序·覆盖）描述不了的第六条** —— 它是**跨结果行的整体约束**，不是单条规则的条件。所以**不能**靠多写几条 `default` 规则拼出来（各算各的，加总不保证相等）。

**归属**：它更近的亲属是**一类 `doc_flow_rule`**（§1）—— 那里的 **数量池 + 幂等键**正是"拆多行且总量受控"的语义（姊妹篇 Copy Control）。因此：

- 拆的是**数量 / 清单** → 优先看一类资产能否覆盖（`field_map` 一对一头/行映射 + 池校验）；
- 拆的是**金额 / 费用分摊** → 与**定价**（§10.4）并列成独立族（**分配基数 + 舍入尾差**是它的专属难题）。

**② 反向汇总（N → 1）—— 平台「**计数类已具备**」，缺「**按父分组的取值聚合**」**

> **落点口径修正（v1.10，2026-10-03，实施后回填）**：原文称本项「即 §10.6 第 10 项**缺口**」「属**最低成本补齐项之一**」，**过强**。经代码级核实（`meta/services/computation_service.py`），平台 N→1 聚合**已具备一部分**：
> - ✅ **计数类 rollup 已有**：`count_children`（按外键统计**子记录数**，且有 `GROUP BY` 批量版 `_batch_count_children`，代码注释自述"1 个 SQL 替代 N+1"）、`count_relations`（关系计数）；
> - ✅ **表级 / 过滤级聚合已有**：`SUM / AVG / MAX / MIN`（`AGGREGATION_TYPES`，`_aggregate_field` 支持 `filters` + `WHERE`）；
> - ❌ **仍缺**：**按父记录分组的取值聚合**（`_aggregate_field` 是**整表 / 条件过滤**聚合，**不带父键分组**，故不能算"每个父一行"的 rollup）+ **子行增 / 删 / 改触发重算**的依赖机制。
>
> 准确表述：**计数与全局聚合已具备；按父分组的取值 rollup 与重算触发仍缺** —— 补齐成本仍低（可复用 `count_children` 的分组模板 + `depends_on` 骨架），但**不再是"从零补"**。

- **与 `compute` 的本质差别**：`compute` 是"**本对象其它字段**的纯函数"（§8.9 ①）；rollup 是"**其它记录**字段的聚合" → 依赖对象不是**字段**而是**子集合**，且子行**增 / 删 / 改**都要触发重算。
- **先例**：Salesforce **roll-up summary**（正是 §6.4 执行顺序的**第 16 步**）、Palantir derived property 沿 link 聚合（≤3 跳）、SAP 汇总结构。
- **共性设施**：与 `compute` **分表但可共用依赖图** —— `depends_on` 从"字段依赖"扩展为"**子集合依赖**"（父量依赖 `children(qty)`）。
- **成本**：**部分已在**（计数 / 全局聚合，见上口径修正）；剩余"按父分组的取值聚合 + 重算触发"仍属**较低成本**补齐项。

**③ 真正的接缝在总纲 §5.4，不在本文**

两类都撞同一堵墙 —— **"一个对象放几个量"**：

```
头量 = 用户填 / 规则确定   →  行量是「拆分结果」（派生）   ← 拆分
行量 = 逐行录入的事实      →  头量是「汇总」（派生）       ← 汇总
```

**两头不能都是事实**：否则 `Σ行 ≠ 头` 时无法判定谁对。这正是 C6「展示用派生 ≠ 写入用默认」的**同构问题** —— **同一维度的两个粒度，必须切一刀定谁是事实、谁是派生**（[总纲 §5.4](file:///d:/filework/docs/superpowers/specs/2026-09-30-object-model-guideline-plan-vs-fact.md)）。

**④ 判定表**

| 问题 | 方向 | 归属 | 本文覆盖？ | 建议落点 |
|---|---|---|---|---|
| 表头 → 行拆分 / 分摊 | **1 → N** | §10.3 集合确定的**带守恒变体** | ❌ | 数量维度归一类 `doc_flow_rule`（数量池）；金额分摊独立成族 |
| 反向汇总 rollup | **N → 1** | §10.6 第 10 项 | 🔵 **计数类已具备**（`count_children` / `count_relations`）；按父分组的取值聚合缺 | 单列「汇总族」，与 `compute` 共用依赖图 |

**一句话**：**拆分（1→N，带守恒）与汇总（N→1，带子集合依赖）都不是"条件 → 一个值"** —— 前者归一类池资产 / 金额分摊族，后者归汇总族；但**两者都必须先回答总纲 §5.4 的"谁是事实"**。

---

## 9. 证据表（官方来源）

| # | 结论 | 来源 | 确定度 |
|---|---|---|---|
| E1 | 条件技术五构件；exclusive vs additive；requirements routine | SAP Help – Condition Technique / Access Sequences | 【确定】 |
| E2 | 五类确定过程（定价/合作伙伴/批次/输出/文本） | SAP Help – Pricing / Partner Determination (VOPAN) / Batch Determination (COB1) / Output (NACE) | 【确定】 |
| E3 | LO-VC 五类对象依赖（前提/选择/**动作**/约束/过程） | SAP Help – Object Dependencies in Variant Configuration | 【确定】 |
| E4 | FI 校验与替代 GGB0/GGB1、三级 callup、保存前执行、`默认<替代<手工`、GB01 | SAP Help – Validation and Substitution (GGB0/GGB1/OB28/GB01) | 【确定】 |
| E5 | Copy Control 与本文分属两套机制 | 见 [Copy Control 研究](2026-09-29-doc-flow-copy-control-research.md)（VTAA/VTLA/VTFL、VOFM） | 【确定】 |
| O1 | EBS 默认规则：实体×属性 + Condition + Source（**PL/SQL Defaulting Framework**）+ Defaulting Sequence（**同序按字母序**）、依赖仅同实体、头→行**可配置级联**（profile `OM: Sales Order Form: Cascade Header Changes to Line`）；**"种子 50"未找到**、**Source 含裸 SQL 不准确**、**"源变必先清空"有例外**（原文 "the old value would be retained instead of clearing"） | Oracle EBS Order Management User Guide – Defaulting Rules | 【确定】（三处修正见 §4.1） |
| O2 | EBS 处理约束：Group Number、Scope ANY/ALL、**Require Reason / Trigger Audit Trail·Versioning / Raise Integration Event**、System vs User Changes；**"五种 Action"与"一次一个约束生效"未找到**（v1.8 删除） | Oracle EBS – Processing Constraints | 【确定】（两处删除见 §4.2） |
| O3 | Fusion 默认值 = **Manage Pretransformation Defaulting Rules**（官方页名）、判断空值控件名 **`Is Blank`**、Pre/Post、Effective Date/Active/Publish、Groovy 逃生门；**"默认值即 Transformation Rules"不准确** | Oracle Fusion Cloud SCM – Pretransformation Defaulting Rules / Transformation Rules | 【确定】（口径修正见 §4.3） |
| O4 | 编排指派规则本体不版本化（"orchestration process controls them"） | Oracle Fusion – Manage Orchestration Process Assignment Rules | 【确定】 |
| O5 | Advanced Pricing：Qualifier/Modifier、Context Precedence、Precedence vs Best Price、Request Viewer | Oracle Advanced Pricing User Guide | 【确定】 |
| O6 | Fusion 校验两层：Processing Constraints（阻断）+ Application Composer Object Functions / Triggers / Validators（Error/Warning） | Oracle Fusion – Processing Constraints / Application Composer | 【确定】 |
| O7 | Fusion 计算路径：Pricing Formulas / Groovy、Application Composer **Formula 字段**；**无"计算 Processor"官方表述** | Oracle Fusion – Pricing Formulas / Application Composer | 【确定】 |
| O8 | Fusion 集合确定散落在业务模块：审批人 = Approval Management、批次 = Wave Plan / Pick Slip Grouping；**伙伴 / 输出未找到规则化确定机制** | Oracle Fusion – Approval Management / Wave Planning | 【基本确定】 |
| P1 | Derived properties [Beta]：**读时算、只读、不可被 function / action 编辑**；≤3 跳聚合；不能标 required（非空）/ 不得作 primary key / 无 type constraints / 无 rule set bindings；OSv1 不能同查；**官方页无“不可用于 defaulting”字样**（该限制系由只读反推） | Palantir Docs – Derived properties [Beta] | 【确定】（defaulting 限制：【基本确定】） |
| P2 | Action 参数默认值：静态 / 对象属性、**局部默认优先全局**、**只能引用排在上方的对象参数**；Rules 四种来源、**顺序敏感（后写覆盖先写）** | Palantir Docs – Action types（Parameters / Rules） | 【确定】 |
| P3 | **Function rule 与其它规则互斥**；Function-backed Action 才落库（`@OntologyEditFunction` + `@Edits`；v2 `createEditBatch`）；Staged writes 原子提交 / read-after-write | Palantir Docs – Function-backed actions / Staged writes | 【确定】 |
| P4 | Submission criteria（提交条件：全部满足才可提交，否则 failure message 阻断）；**VALIDATE_ONLY / VALIDATE_AND_EXECUTE**；v1 `/validate` 端点 | Palantir Docs – Submission criteria / Apply Action API | 【确定】 |
| P5 | Foundry Rules（原 Taurus）：低代码、面向 **dataset 行**、**batch / scheduled**、输出 dataset 的 permitted / default values 与 required 列；Rule Editor / Proposal Reviewer / Rule Viewer；**组件名 “TaurusRuleRunner” 未找到** | Palantir Docs – Foundry Rules（overview / rule-logic / permitted-and-default-output-values） | 【基本确定】 |
| P6 | **Override blocks**（if / then）：动态改约束·可见·必填·默认值；**只能引用上方参数**；**多条命中仅第一条执行** | Palantir Docs – Parameters override | 【确定】 |
| P7 | **参数级开关**：是否暴露在 Form、是否允许用户修改 | Palantir Docs – Parameters overview | 【确定】 |
| P8 | 计算的**三处落点**：pipeline transform（写时）/ derived property（读时）/ Function-backed Action（写回）；**属性元数据无属性级默认值** | Palantir Docs – Structural guidance / Property metadata | 【确定】 |
| P9 | **AIP Logic**（LLM 驱动函数、非声明式）；**Automate**（conditions→effects 持续检查；Object Monitors 已被取代） | Palantir Docs – AIP Logic / Automate | 【确定】 |
| P10 | **Action Log**（RID / type 版本 / 用户 / 对象 / 参数）+ **Test run**（干跑逐步日志、不落库） | Palantir Docs – Action log / Test run | 【确定】 |
| S1 | Salesforce **before-save = Fast Field Updates**：保存事务内改写 `$Record`、**零额外 DML、不重入保存执行顺序**（原文 "they don't consume additional DML operations or re-trigger the save order of execution."）；**不跨对象** | Salesforce Help / 官方博客 – Record-Triggered Flow（Fast Field Updates） | 【确定】 |
| S2 | after-save = **Actions and Related Records**：走 **DML**、可跨对象、可递归 | Salesforce Help – Record-Triggered Flow | 【确定】 |
| S3 | 覆盖语义：before-save 直接写 `$Record`，**用户值会被覆盖**，要保留须**自己判空**（`ISBLANK`）；**字段默认值 vs Flow 默认值先后顺序未找到** | Salesforce Help – Record-Triggered Flow（Apex 于 Order of Execution 步骤号见 S4） | 【基本确定】（先后顺序：【未找到】） |
| S4 | **Flow Trigger Explorer 显式排 Trigger Order**（**非字母序**）；**多条 before-save flow 顺序不保证** | Salesforce Help – Flow Trigger Explorer | 【确定】 |
| S5 | **Order of Execution 步骤号**：3 before-save flows / 4 before triggers / 5 校验规则 / 6 duplicate rules / 7 落库 / 8 after triggers / 14 after-save flows / 16 roll-up summary | Salesforce Developer Docs – Apex Developer Guide, Order of Execution | 【确定】 |
| S6 | **Validation Rules 第 5 步阻断**；**Formula Field 只读、读时算、不落库、不可作默认源**；字段默认值 + **Dynamic Forms**（组件级可见/必填）；Apex trigger 顺序不保证（"the order of trigger execution isn't guaranteed"） | Salesforce Help / Developer Docs – Validation Rules / Formula Fields / Dynamic Forms | 【确定】 |
| S7 | D365 Business Rules：Scope 决定时机、动作集、表单保存不应用、服务端 before | Microsoft Learn – Create a business rule | 【确定】 |
| S8 | Odoo：compute+inverse+depends、onchange 伪记录、Automated Actions 触发器 | Odoo Docs – Computed fields / Onchange / Automated Actions | 【确定】 |
| S9 | 金蝶 BOTP 转换规则 + 值更新事件（基础资料带出）、扩展/继承做版本治理 | 金蝶云·星空 官方社区 – 单据转换管理 / 值更新事件 | 【基本确定】 |

---

## 10. 规则模型全景图：我们覆盖到哪、边界在哪

> 问：**"还有其他类型的规则吗？我们覆盖得全吗？"**
>
> **答：不全。** 本文只覆盖"**给一组因子 → 产出一个属性值**"这一类。同族还有**三类结果类型**未覆盖；邻域还有**四个体系**须显式划界。

### 10.1 四层作用域

| 层 | 规则族 | 归属 |
|---|---|---|
| **L1 对象内 · 字段级** | 默认确定 / 计算 / 校验 / 变更约束 / 可见性 | 本文 + 已有资产 |
| **L2 对象间 · 单据级** | 复制转换 / **集合确定（伙伴·审批人·批次·输出）** / **定价** / 寻源分配 / 汇总 | 一类资产 + **多数缺口** |
| **L3 流程 · 事件级** | 触发自动化 / 审批流 / 通知 / SLA | **邻域**（任务·编排体系） |
| **L4 安全 · 主体级** | 条件权限 / 行级数据范围 | 二类资产 |

### 10.2 同族的多种结果类型 —— 一台条件引擎驱动多类过程

这正是 **SAP 条件技术的本质**：同一台机器（条件表 + 存取顺序 + 过程）驱动**定价 / 输出 / 文本 / 伙伴 / 批次 / 物料确定**等**至少五六类**过程【确定】。

| 结果类型 | 规则族 | 平台现状 | 判定 |
|---|---|---|---|
| **值 · 可改** | 默认确定 | ✅ 本文 §8.3 | — |
| **值 · 只读** | 计算 compute | ✅ 本文 §8.9 | 依赖图未落 |
| **布尔 · 可见性** | 字段策略 | 🔵 已有（`field_policy_engine`） | — |
| **布尔 · 阻断** | **校验 validation** | ✅ **已有**（`MetaValidation` + `ValidationExecutor` + 保存链路可阻断） | **同族，共用条件内核**（先例：Palantir submission criteria、**Oracle EBS/Fusion Processing Constraints**、**Salesforce Validation Rules（第 5 步）**、D365 Business Rule 校验、SAP GGB0 校验）；"跨对象"形态未核实 |
| **集合 · 多值** | **伙伴 / 审批人 / 批次 / 输出确定** | ❌ | **同族，结果是"一组"** |
| **一组 · 带守恒** | **拆分 / 分摊（头 → 行，1→N）** | ❌ | **比集合多一条"`Σ行 = 头`"整体约束**（§8.10 ①） |
| **值 · 聚合** | **汇总 rollup（N→1）** | 🔵 **计数类已具备**（`count_children` / `count_relations`） | **依赖是"子集合"而非字段**；缺**按父分组的取值聚合**（§8.10 ②） |
| **金额 · 多层** | **定价 Pricing** | ❌ | **同族里最复杂，宜独立引擎** |

### 10.3 集合确定：最大的缺口（结果不是"一个值"）

| 过程 | 结果 | 特殊约束（SAP 先例【确定】） |
|---|---|---|
| **伙伴确定** | 一组参与方角色 | Sequence 优先级；Mandatory / Unique / Not Modifiable |
| **审批策略**（Release Strategy） | 审批层级 / 审批人组 | 由特征值命中 → 定层级 |
| **批次确定** | 候选批次（排序） | 条件表 + 排序规则 + 策略类型 |
| **输出 / 消息确定** | 要发哪些消息、给谁 | 可能多条 |
| **寻源 / 分配** | 分给哪个组织 / 仓库 / 供应商 | — |
| **拆分 / 分摊**（头 → 行，见 §8.10） | **一组行**（等分 / 按比例 / 按明细） | **★ `Σ行 = 头`（守恒）**；舍入尾差处理 —— 比上表多一条**跨行整体约束** |

**共性**：结果**不止一个**，且常带**排序 + 必填/唯一**约束 —— 与属性确定**共享条件内核**，但**求值器与落库形态不同**（一值是列；一组是子集合 / 边）。**拆分 / 分摊是本节里最硬的一格**：它多了"**守恒**"这条五要素描述不了的约束（§8.10 ①）。

> **注意**：`doc_flow_rule` 的 `field_map` 已能做"一对一头/行映射"，但**做不了一对多的伙伴行**——这类要**子集合**（或边），**不能塞进主表的列**。

### 10.4 定价：同族里最复杂的一类（建议独立引擎）

**为什么单列** —— 结果虽是金额，语义远超"一条规则给一个数"：

- **多层累加**：基价 + 折扣 + 附加费 + 税 + 运费 → 层层叠加
- **互斥 vs 累加**：SAP `exclusive` / `additive` 条件记录
- **冲突取优**：`Precedence`（先命中）vs `Best Price`（取最优）—— 两套合并哲学
- **值类型多样**：百分比 / 定额 / 数量 / 公式

**结论**：定价**不该**用"属性确定规则表"凑合 —— 它是**独立引擎**（对标 SAP 定价过程、Oracle Pricing Engine）。

### 10.5 邻域：属别的体系（须显式划界，勿塞进规则表）

| 族 | 归属体系 | 为什么不属本规则模型 |
|---|---|---|
| 触发 / 自动化（Flow） | 任务 · 编排 | 是"**事件 → 动作序列**"，非"因子 → 值" |
| 审批流 | 任务 · 状态机 | 管"谁批、批几次"；规则最多产出"要不要批" |
| 状态机转移准入 | 状态机资产 | 管"状态能不能变"，是**图上的边约束** |
| SLA / 时效 | 计划 · 任务 | "承诺日期怎么算"归业务域（§5.5 纪律） |
| 行级数据范围 | 权限体系 | 带"**谁**"的维度（§8.6） |

> **划界条款**：**规则表只回答"给一组因子，产出什么"，不回答"接下来发生什么"** —— 后者一律走任务 / 编排体系。

### 10.6 覆盖清单

| # | 规则族 | 状态 |
|---|---|---|
| 1 | 属性确定 `default` | ✅ 本文 §8.3 / §8.7 / §8.8 |
| 2 | 计算 `compute` | ✅ 本文 §8.9 |
| 3 | 字段策略（可见 / 可改 / 必填） | 🔵 已有资产 |
| 4 | 条件权限 | 🔵 已有资产 |
| 5 | 单据复制转换 | 🔵 一类资产（姊妹篇） |
| 6 | **校验 validation** | ✅ **已有**（`models.py` L173-183 `MetaValidation`（`severity` / `validation_mode`）；`rule_executor.py` L621-716 `ValidationExecutor`；`action_executor.py` L792-859 保存前 `MetadataDrivenValidator` → `ActionResult.fail("VALIDATION_FAILED")` 可**阻断保存**）。**口径修正 [v1.11]**：原文判「❌ 缺口（同族，成本最低）」，经代码级核实为**已具备**；仅"跨对象校验"形态未核实 |
| 7 | **变更准入约束**（何时允许改 / 须理由 / 须留痕） | ❌ 缺口（半只脚：`readonly_after`） |
| 8 | **集合确定**（伙伴 / 审批人 / 批次 / 输出 / **拆分·分摊**） | ❌ **缺口（同族·最大；拆分/分摊带守恒，见 §8.10）** |
| 9 | **定价** | ❌ 缺口（同族·宜独立引擎） |
| 10 | **汇总 rollup**（跨记录聚合 N→1，见 §8.10） | 🔵 **部分具备**：计数 `count_children` / `count_relations` + 表级 `SUM·AVG·MAX·MIN` 已有；**缺**按父分组的取值聚合 + 子行增删改重算 |
| 11 | 编号 / 文本 / 输出模板 | ❌ 缺口（较轻） |
| 12 | 流程触发 / 审批 / 状态机 / SLA | ⬜ 邻域（另立，不混） |

### 10.7 下一步优先级（建议）

1. **先做 `default` + `compute`**（本文已设计）—— 对应用户原话场景
2. ~~紧接着补校验~~ **校验已具备，无需立项**（`MetaValidation` + `ValidationExecutor` + 保存链路阻断，见 §10.2 / §10.6 第 6 项；口径修正 [v1.11]）
3. **汇总 rollup 补齐剩余**（计数已具备；补「按父分组的取值聚合 + 子行增删改重算」，与 `compute` 共用依赖图，成本低，§8.10 ②）
4. **再评估集合确定**（伙伴 / 审批人 / **拆分·分摊**）—— 若"确定合同"要带出**参与方**，或要**表头拆行**，则**现在就需要**；拆分/分摊注意**守恒**（§8.10 ①）
5. **定价单独立项**（勿混入规则表）
6. **邻域四项显式划界**（写进规则表的使用约束）

**一句话**：本文覆盖的是"**条件 → 单个属性值**"；同族中**校验（布尔·阻断）已具备**（`MetaValidation` + `ValidationExecutor` + 保存链路阻断）、**汇总（N→1）计数类已具备、取值聚合待补**；**仍未覆盖**的是"**集合（伙伴/审批人/批次/输出/拆分·分摊）**"与"**金额·多层（定价）**" —— **集合可共用条件 / 依赖基础设施，定价宜独立**；流程 / 审批 / 状态机 / SLA 是**邻域**，须显式划界、不混。

---

## 11. 结论

1. **先切干净三类规则**：跨对象派生（`doc_flow_rule`）/ 条件权限 / **单对象属性确定（本文）**。SAP 用两套机制分开前两者与第三者，我们也应分开（§1、§3.4、§8.1）。
2. **五要素是通用骨架**：触发 / 因子 / 条件 / 动作 / 次序·覆盖。七家产品全部收敛在此（§2、§7）。
3. **两处必须显式、不能藏**：**覆盖策略**（`blank_only` 等，Fusion `Is Blank` / Salesforce `ISBLANK` 的教训）与**确定次序**（顺序号 + 首个命中 + tie-break，SAP/EBS 同构）。用户原话"有时可进一步变更" = `blank_only`（§7 C3/C4、§8.3）。
4. **平台不是从零造**：`field_policy_engine` 的 `PolicyRule(when_expr, value, default)` + 首个命中**已经是骨架**，`persistence_interceptor` 的写前时机**已存在**，`condition_parser` 是共享条件基础。要做的是**把条件-值能力从"权限语义"扩到"取值语义"**（§8.2）。
5. **守住三条边界**：读时填充（`enrichment_engine`）只能展示、不许当默认源（C6）；确定规则只写属性、不写边（总纲 §5）；带出"数量"须过总纲 §5.4 三问。
6. **必留逃生门与可解释性**：声明式覆盖 80%，剩余走 `ActionType.BUSINESS` hook（C8）；并应提供"这次为什么带出这个值"的回放（对标 Oracle Pricing Request Viewer，C9）。
7. **共享条件内核、不合并求值器**（§8.6）：权限条件配置只是"**条件求值**"的通用内核 + **判定型**结果；属性确定要的是**取值型**结果。两者**共享条件解析/UI/锚定**，但**不共用求值器**（结果类型、触发时机、因子空间三重不同）。**概念通用 ≠ 引擎合并**。
8. **覆盖不全，须按全景图补齐**（§10）：本文只覆盖"条件 → **单个属性值**"；同族还有 **校验（布尔·阻断）**、**集合确定（伙伴/审批人/批次/输出）**、**拆分·分摊（1→N，带守恒）**、**反向汇总（N→1，带子集合依赖；计数类已具备，取值聚合待补）**、**定价（金额·多层）** 五类未覆盖 —— 前三类与汇总可**共用条件内核 / 依赖图**，**定价宜独立引擎**；流程 / 审批 / 状态机 / SLA 属**邻域**，须显式划界、不混入规则表。**拆分与汇总还须先回答总纲 §5.4"谁是事实"**（§8.10 ③）。

---

## 12. 变更记录

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v1.0 | 2026-10-02 | 首版：规则模型专题（属性确定与自动带出）。三类规则资产切分；五要素解剖；SAP 条件技术/五类确定过程/VC 五类依赖/FI 替代；Oracle 默认规则/处理约束/Transformation Rules/编排指派/Pricing；Palantir "无声明式规则引擎"结论；四家声明式 DSL 坐标；十条共性规律；平台接缝（field_policy_engine / persistence_interceptor / enrichment_engine）与规则表草案；证据表 | AI Assistant |
| v1.1 | 2026-10-02 | 增补 **§8.6 架构边界条款：共享条件内核，不合并求值器**（回应"权限条件配置是否通用规则模型"）：平台四处"条件→结果"资产的因子空间/结果类型/取数语义/触发时机对照；三处可共享内核；三条不可合并理由；§10 增结论 7 | AI Assistant |
| v1.2 | 2026-10-02 | 增补 **§8.7 因子取值：路径解析 vs 行内快照**（回应"主因子属性如 `material.materialgroup` 是否必须 copy 到单据行"）：拆开取值路径 vs 冻结需求两个正交问题；三型取值路径（本地/点路径/锚点）+ 代码级先例；必须落库的三情形；"落结果必落库、落因子看需求"；多应用库路由硬约束；决策表。并 **§8.3 增 `factors` 支持点路径 + 新增 `factor_freeze` 列** | AI Assistant |
| v1.3 | 2026-10-02 | 增补 **§8.8 多条规则行的优先级与阶梯求值**（回应"多条规则行的 if/elseif 优先级"）：先分组再排序；阶梯=互斥首个命中；显式 `seq` vs 特异性自动排两范式；更具体的须排前 + 特异性倒置告警；必配 else 兜底；tie-break 必须确定；优先级 vs 覆盖正交；跨阶梯依赖次序；变更影响。并 **§8.3 新增 `scope` / `is_fallback` 列，`seq` 明确为组内序** | AI Assistant |
| v1.4 | 2026-10-02 | 增补 **§8.9 计算规则：对象内属性派生**（回应"`金额 = 数量 × 单价` 是否算规则"）：确定(default) vs 计算(compute) 两支语义对照；七家产品"确定/计算"分立证据；依赖链 DAG 与执行顺序；落库决策沿用 §8.7；平台接缝（`value_source=expr` + `depends_on`）。并 **§8.3 新增 `kind` / `depends_on` 列** | AI Assistant |
| v1.5 | 2026-10-02 | §8.9 增补 **⑥ compute 亦支持条件**（两位置：A 规则层阶梯 / B 公式内 IF；`when_expr`/`scope`/`seq`/`is_fallback` 两支共享，仅 `overwrite`/`depends_on` 有别）与 **⑦ `depends_on` 必须含条件因子**（否则"改条件不重算"bug 必现）。并 **§8.3 `depends_on` 示例补条件因子** | AI Assistant |
| v1.6 | 2026-10-02 | 新增 **§10 规则模型全景图：我们覆盖到哪、边界在哪**（回应"还有哪些规则类型、覆盖全不全"）：四层作用域；同族多种结果类型（值·可改/值·只读/布尔·可见/布尔·阻断/集合·多值/金额·多层）；集合确定（伙伴/审批人/批次/输出）为最大缺口；定价宜独立引擎；邻域四族划界条款；覆盖清单 12 项；下一步优先级。**§11 结论增结论 8**；原 §10 结论→§11、§11 变更记录→§12 | AI Assistant |
| v1.7 | 2026-10-02 | **Palantir 专项系统化重写 §5（回应"继续系统地分析 Palantir"）**：改为按层拆解 —— §5.1 语义层（对象/属性**无任何规则**、无属性级默认值）、§5.2 Action Types（参数默认值 / Rules 四种来源 / **Override 首个命中** / Submission criteria 校验 / 参数级开关 / **声明式与命令式互斥**）、§5.3 Functions、**§5.4 计算三落点（pipeline / derived property / function 写回）**、§5.5 Foundry Rules（原 Taurus，**修正 `TaurusRuleRunner` 为未找到**）、§5.6 邻域（AIP Logic / Automate）、§5.7 可解释性（Action Log + Test run）、§5.8 五要素小结、§5.9 结论。**并修正承重断言**：derived property 官方页**无**"不可用于 defaulting / 只用于展示·过滤·排序"字样（原 §2 区分 3、§7 C6、§8.9、证据表 P1 一并降级为【基本确定/未找到】）；补强 §7 C9（Palantir Test run 为另一条回放路径）；证据表新增 P6–P10；§10.2 校验行补先例 | AI Assistant |
| v1.9 | 2026-10-02 | 新增 **§8.10 拆分/分摊 与 反向汇总：结果基数不是"一个值"的两类**（回应"表头→明细行拆分分摊、反向汇总算规则模型覆盖么"）：判定**都不算第三类覆盖**（第三类输出恰好一个值）；**拆分/分摊 = 1→N 且多一条五要素描述不了的"守恒"约束**（`Σ行 = 头`，所以不能靠多条 `default` 拼），归属一类 `doc_flow_rule`（数量池）或金额分摊族；**反向汇总 = N→1**，与 `compute` 的区别是**依赖"子集合"而非字段**，可与其共用依赖图、成本最低；两者真正的接缝在**总纲 §5.4"谁是事实"**（两头不能都是事实）。**同步更新**：§10.2 增两行（一组·带守恒 / 值·聚合）、§10.3 增拆分·分摊行 + 守恒说明、§10.6 第 8/10 项、§10.7 优先级、§11 结论 8（缺口由三类改五类） | AI Assistant |
| v1.10 | 2026-10-03 | **实施后回填的 4 处口径修正**（均经代码级核实）：① **§1 表格第 3 行** —— `meta/rules` 容器**已存在**（`MetaRule` + `RuleEngine` + `meta_obj.rules`），缺的是 `default` 语义，非"尚无专门资产"；② **§8.2 落点表** —— 删除"`persistence_interceptor` 为落点"的判断，实际落点为 `RuleEngine` 新增 `DefaultExecutor` + `default_by_priority`，由 `action_executor` 在 `BEFORE_SAVE` 前调用；③ **§8.10 ② + §10.2 + §10.6 #10 + §10.7 #3 + §11 结论 8** —— "反向汇总"由「❌ 缺口 / 最低成本补齐项」修正为「**计数类已具备**（`count_children` / `count_relations` + `GROUP BY` 批量版）、表级 `SUM·AVG·MAX·MIN` 已有；**仍缺**按父分组的取值聚合 + 子行增删改重算」（原判**过强**）；④ **§8.3 新增平台实现口径块** —— `scope`+`seq` 映射为 `MetaDefaultRule.target_field` 分组 + 组内 `priority`，与既有 `priority`「全局排序 + 全部执行」为**两套并存但隔离**的语义 | AI Assistant |
| v1.11 | 2026-10-03 | **二期开工前的现状核查，再修正一处过强断言**：**校验 validation 判为「❌ 缺口（同族，成本最低）」有误 —— 平台已具备**（`meta/core/models.py` L173-183 `MetaValidation`（`severity` / `validation_mode`）；`rule_executor.py` L621-716 `ValidationExecutor`；`action_executor.py` L792-859 保存前 `MetadataDrivenValidator` → `ActionResult.fail("VALIDATION_FAILED")` 可**阻断保存**）。同步修正 **§10.2 判定表**、**§10.6 第 6 项**、**§10.7 优先级第 2 条**（改为"已具备，无需立项"）、**§10.7 一句话**。附：定价经全仓 grep（`pricing` / `price_list` / `discount` / `unit_price`）**零业务命中**（仅命中我方测试文件）→ **确实缺**；前端 `.vue` 中无规则配置界面（仅 `PermissionConfigPanel.vue` 命中）→ **在线配置 UI 确实缺** | AI Assistant |
