# 规则模型研究（二）：消费侧的模型、分层归属与基础能力

> **版本**：v2.1 | **日期**：2026-10-03 | **状态**：研究稿（P2~P5 已实施，见 §8.9；**规则顺序已收口为唯一口径**，见 §4.4；**G3/G1 已修**，见 §4.4；编排专题见关联文档）
> **关联文档**：
> - [2026-10-02-rule-model-research.md](./2026-10-02-rule-model-research.md)（v1.11，规则内容/生产侧对标）
> - [2026-10-02-rule-model-spec.md](./2026-10-02-rule-model-spec.md)（v1.3，Spec + RFC）
> - [2026-10-02-rule-model-implementation-plan.md](./2026-10-02-rule-model-implementation-plan.md)（v1.6）
> - [2026-10-03-rule-orchestration-ordering-and-propagation.md](./2026-10-03-rule-orchestration-ordering-and-propagation.md)（v1.6，**编排专题**：顺序/链式传播/跨对象级联 + 8 家对标 + 收口方案 + P0 实测 + G9/G10/G11 已修 + D7 tie-break 已统一 + P1 顺序唯一入口已落地 + G3/G1 已修 + **二次检查完成，P2~P6 待办见 §4.1**）
> - [analysis-head-product-model-comparison.md](../../specs/analysis-head-product-model-comparison.md)（"模型要素"术语出处）
>
> **本文与前文的分工**：前文（v1.11）研究的是**规则的"内容"**——五要素、各产品怎么配一条确定规则（生产侧）。本文研究**规则的"消费"**——规则在运行时由谁读、谁执行、作用于哪一层（消费侧），并回答分层归属问题。

---

## 0. 本文回答什么（用户原话映射）

| # | 用户原话 | 本文位置 | 结论先行 |
|---|---|---|---|
| 1 | "在规则的消费侧、使用侧，它的这个模型跟一些基础能力" | §2 | 消费侧 = 「BO 声明 → EO 实例 → 基础设施引擎」三段链路；共享内核只有条件求值一条 |
| 2 | "Determination 跟 validation 应该是属于 BO 层面，EO 对象层面，基础设施里头的" | §3 | **方向正确但不完整**：不是三选一的一层，而是**三段式并存**（声明在 BO、作用于 EO、机器在基础设施） |
| 3 | "模型要素 这个应该是跟规则是不是也有关系？" | §1、§4 | **有关系但不是一回事**：模型要素 = 框架预置的**能力槽位**；规则 = 填进槽位的**声明数据** |
| 4 | "其他的头部产品它的一些模型跟架构" | §5 | 头部产品一致采用「**槽位 + 数据 + 引擎**」三段式；分"代码声明式"与"配置数据式"两流派 |

**意外发现（§4）**：平台的 Validation 要素在运行时存在 **4 条互不相同的消费路径**；其中 YAML `validations:` 声明通道**未被任何运行时代码消费**（代码级核实）。

---

## 1. 术语先切干净：模型要素 / 规则 / 基础能力

这三个词当前被混用，是造成"该属于哪一层"争论的根源。按「**位置 / 内容 / 机器**」三轴切开：

| 轴 | 术语 | 定义 | 平台对应物 | 是"规则"吗 |
|---|---|---|---|---|
| **位置** | **模型要素**（meta-model element / 能力槽位） | 框架预置的、可被填充的**类型槽位** | `RuleType` 枚举的 8 个值 | 否，是"槽位类型" |
| **内容** | **规则**（rule data / 声明实例） | 填进槽位的**可配置数据** | `MetaObject.rules` 里的 `MetaRule` 实例（YAML`rules:`段） | 是，本体 |
| **机器** | **基础能力**（infrastructure） | 与具体规则无关的**通用执行机器** | `RuleEngine` / 6 个 Executor / 表达式求值 / 依赖图 | 否，是"引擎" |

### 1.1 模型要素再分两类（回答"模型要素跟规则有没有关系"）

`analysis-head-product-model-comparison.md` 把 Node / Action / Determination / Validation / Association / Query / Status Schema 统称"模型要素"。它们与规则的关系**并不相同**：

| 子类 | 要素 | 与规则的关系 | 平台载体 |
|---|---|---|---|
| **结构型要素** | Node/Object、Attribute/Field、Association、Value Set、Query、Status Schema | **无关**：定义的是"结构"，由 schema 声明填充，不是规则数据 | `MetaObject` / `MetaField` / `MetaRelation` / `enum_values` / `MetaQuery` / `MetaStateTransition.state_field` |
| **规则型要素** | **Determination、Validation**、Action、Trigger | **有关**：定义的是"行为槽位"，由**规则数据或代码**填充 | `RuleType`（DEFAULT/DERIVATION/VALIDATION/CONSTRAINT/TRIGGER…） |

> **一句话**：**模型要素是"容器位"，规则是"装进去的东西"**。所以"模型要素跟规则有关系"——但只对**规则型要素**成立；结构型要素不装规则。
> 平台证据：`MetaAction` 是**独立结构类**（[models.py#L609](file:///d:/filework/excel-to-diagram/meta/core/models.py#L609)），**不继承 `MetaRule`**；而 Determination（`MetaDerivation`）/ Validation（`MetaValidation`）**继承 `MetaRule`**（[models.py#L173-L187](file:///d:/filework/excel-to-diagram/meta/core/models.py#L173-L187)、[#L357-L378](file:///d:/filework/excel-to-diagram/meta/core/models.py#L357-L378)）——平台自己就把"要素"分成了"结构型（非规则）"与"规则型（是规则）"两类。

### 1.2 平台现状：一个基类承载 8 个规则型要素

`MetaRule`（[models.py#L141-L170](file:///d:/filework/excel-to-diagram/meta/core/models.py#L141-L170)）是**唯一基类**，8 个子类型即 8 个"要素槽位"：

```
MetaRule (基类, models.py L141)
├── MetaValidation      VALIDATION        L173
├── MetaConstraint      CONSTRAINT        L190
├── MetaComputation     COMPUTATION       L206
├── MetaDefaultRule     DEFAULT           L224   ← 一期新增
├── MetaStateTransition STATE_TRANSITION  L292
├── MetaTrigger         TRIGGER           L320
└── MetaDerivation      DERIVATION        L357
（RuleType 枚举见 models_enums.py L94-L104；PERMISSION 在枚举中但无对应类）
```

---

## 2. 消费侧全景：一次保存的规则消费链（代码级）

### 2.1 三个坐标（对应 §0 的"三层"）

| 层 | 坐标 | 代码证据 |
|---|---|---|
| **BO 声明层** | 规则从**元数据**读入 | YAML `rules:` → `parse_rule` 分发 → `MetaObject(rules=...)`（[yaml_loader.py#L2031](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L2031)、[#L2086](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L2086)） |
| **EO 实例层** | 规则作用于**当前这条记录** | `RuleContext(meta_object, data, original_data)`，持有 `data` / `original_data` / `changed_fields` / `auto_filled_fields`（[rule_executor.py#L139-L157](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L139-L157)） |
| **基础设施层** | **执行机器** | `RuleEngine` 持有 6 个 Executor（[rule_executor.py#L1254-L1262](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1254-L1262)） |

### 2.2 取规则 → 分发 → 落结果

```
action_executor.create/update
  └─ rule_engine.apply_defaults(...)        属性确定（专用链，L1625 / L1972）
  └─ rule_engine.execute_rules(trigger)     按 trigger 取规则（L1264）
        ├─ meta_object.get_rules_by_trigger(trigger)      ← BO 声明层读取（models.py L1080）
        ├─ 过滤掉 DEFAULT（显式排除，L1289）              ← 设计纪律，见 §4.3
        ├─ sorted(rules, key=priority)                    ← 基础设施层排序
        └─ for rule: self._execute_rule(rule, context)    ← 分发（L1302）
  └─ 写库
```

**读取入口已收口**：9 处直读 `meta_obj.rules` 已改为经 `RuleProvider`（[rule_provider.py](file:///d:/filework/excel-to-diagram/meta/core/rule_provider.py)）；`get_rules` 原样返回（保序不过滤），过滤能力由 `get_enabled_rules` / `get_rules_by_type` / `get_default_rules` 承担。这是"BO 声明层"的**唯一读取门面**，也是后期切"在线配置规则"的零改造升级点。

### 2.3 分发矩阵：rule_type → 执行器

| rule_type | 执行器 | 位置 | 产出 |
|---|---|---|---|
| VALIDATION | `ValidationExecutor` | [L621-L659](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L621-L659) | 布尔·阻断（`severity`） |
| CONSTRAINT | `ValidationExecutor`（**共用**，见分发 L1312） | 同上 | 布尔·阻断 |
| COMPUTATION | `ComputationExecutor` | [L662-L716](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L662-L716) | 写回 `target_field` |
| DEFAULT | `DefaultExecutor` | [L719-L867](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L719-L867) | 写回（**不走通用链**，见 §4.3） |
| STATE_TRANSITION | `StateTransitionExecutor` | [L870-L988](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L870-L988) | 状态迁移准入 |
| TRIGGER | `TriggerExecutor` | [L991-L1046](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L991-L1046) | 副作用/handler |
| DERIVATION | `DerivationExecutor` | [L1049-L1244](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1049-L1244) | 跨对象派生/聚合 |

分发逻辑集中在 `RuleEngine._execute_rule`（[L1302-L1324](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1302-L1324)），通过 `rule.rule_type` 分支。

### 2.4 执行时机（EO 生命周期）

| 时机 | action_executor 调用点 |
|---|---|
| BEFORE_CREATE | L1612 |
| **apply_defaults（DEFAULT，先于 BEFORE_SAVE）** | **L1625 / L1972** |
| BEFORE_SAVE | L1632（create）/ L1978（update） |
| compute（COMPUTATION，优先走依赖拓扑链） | L1642 / L1989 |
| AFTER_CREATE / AFTER_SAVE | L1662 / L1666（create）、L2004 / L2008（update） |
| BEFORE_DELETE / AFTER_DELETE | L2210 / L2309 |

### 2.5 共享内核只有一条

**结论**：被 7 类规则共用、且与规则内容无关的通用能力，实际只有 **`SafeExpressionEvaluator`**（AST 白名单，禁止 `eval`/`import`，内嵌于 [rule_executor.py#L188-L464](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L188-L464)）。
`condition_parser` / `condition_converter` **未**被 `rule_executor` 导入——即"条件解析"与"条件求值"在平台里是**两条未打通的路径**（前文 §8.6 判"共享条件内核"，此处需收窄口径：**当前实际共享的只有求值内核，解析层尚未统一**）。

---

## 3. Determination 与 Validation 的分层归属

### 3.1 判定框架：不是"三选一"，而是"三段式"

用户提出三个候选层（BO / EO / 基础设施）。代码级核实表明：**同一要素在三层各有落点**，问"属于哪一层"本身就设错了题型。正确问法是"**在这三层分别是什么**"。

| 层 | Determination 在这层是什么 | Validation 在这层是什么 |
|---|---|---|
| **BO 声明层** | `MetaDerivation` / `MetaDefaultRule` 是 `MetaObject.rules` 的成员（声明载体） | `MetaValidation` / `MetaConstraint` 是 `MetaObject.rules` 的成员；**另有 `MetaObject.validations` 容器**（见 §4.1） |
| **EO 实例层** | 改写 `RuleContext.data`（写字段值）；`auto_filled_fields` 记录自动值 | 读 `RuleContext.data` + `original_data`，产出 `RuleResult(success=False)` 阻断保存 |
| **基础设施层** | `DerivationExecutor` / `DefaultExecutor` + `default_by_priority`；跨对象取数/聚合 | `ValidationExecutor` + `MetadataDrivenValidator` + 拦截器链（`ConstraintEngine`…） |

### 3.2 Determination 的落点（写入型）

- **BO**：`MetaDerivation`（[L357](file:///d:/filework/excel-to-diagram/meta/core/models.py#L357)）/ `MetaDefaultRule`（[L224](file:///d:/filework/excel-to-diagram/meta/core/models.py#L224)）——都是 `MetaRule`，住在 `MetaObject.rules`。
- **EO**：写 `context.data[field]`；DEFAULT 额外登记 `context.auto_filled_fields`（[L153](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L153)）以支持再判定只清"自动值"。
- **基础设施**：`DerivationExecutor`（跨对象/聚合）与 `DefaultExecutor` + `RuleEngine.default_by_priority`（分组 + 首个命中）。注意 **DEFAULT 用独立求值器**，与 COMPUTATION 的"全局排序 + 全部执行"语义**并存但隔离**（前文 §8.6 的"概念通用 ≠ 引擎合并"在代码里得到了字面印证）。

### 3.3 Validation 的落点（判定型）——平台里有 **4 条消费路径**

这是本次研究最重要的发现：**"Validation 要素"在平台里不是一个层，而是一个伞形概念，横跨 4 条互不相同的消费路径**：

| # | 路径 | 声明位置 | 执行者 | 层归属 | 阻断能力 |
|---|---|---|---|---|---|
| 1 | **规则型校验** | YAML `rules:` 里 `type: validation/constraint` → `MetaValidation`/`MetaConstraint` | `RuleEngine.execute_rules` → `ValidationExecutor` | BO 声明 + 基础设施 | 可阻断（`severity=ERROR`，L1297） |
| 2 | **字段属性校验** | `MetaField.required/unique/enum_values/pattern/max_length` | `MetadataDrivenValidator` [L30-L42](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py#L30-L42) | **纯基础设施**（由字段属性驱动，无规则数据） | 可阻断（`VALIDATION_FAILED`） |
| 3 | **拦截器链校验** | `MetaField.semantics` / `constraints` | `FieldPolicyInterceptor`(p=40) / `ConstraintValidationInterceptor`(p=42) → `ConstraintEngine` / `HierarchyValidationInterceptor`(p=45) | **纯基础设施** | 可阻断（拦截器链） |
| 4 | **旧 `validations:` 段** | YAML `validations:` → `parse_validation` → `MetaObject.validations` | **无消费者**（见 §4.1） | BO 声明（孤儿） | 无 |

> 路径 2、3 是**同一件事的两种表达**：`required` 既可由 `MetaField.required` 走 `MetadataDrivenValidator`，也可由字段语义走 `FieldPolicyInterceptor` —— 两套并行、互不知情。

### 3.4 对用户判断的回应

| 用户判断 | 核实结论 |
|---|---|
| "属于 BO 层面" | **对**——Determination/Validation 的**声明**住在 `MetaObject.rules`（BO 元数据）；原第 2 条声明通道 `MetaObject.validations` 已于 P3 移除（§8.9） |
| "属于 EO 对象层面" | **对**——两者都经 `RuleContext` 作用于**当前实例**（`data` / `original_data` / `changed_fields`）；执行时机挂在 EO 生命周期（BEFORE_SAVE 等） |
| "属于基础设施里头" | **对**——执行机器（7 个 Executor + 求值内核 + 拦截器链）与规则内容无关，可被任意对象复用；Validation 的路径 2/3 **甚至完全不含"规则数据"**，是纯基础设施 |
| **综合** | **判断方向正确，但三者不是互斥选项**：Determination/Validation 是"**贯穿 BO 声明 → EO 实例 → 基础设施三段**的模型要素"。若只能选一个词，**"对象基础设施的能力"最贴切**——因为它们是为**所有对象**预置的能力，而非某条业务规则的内容。 |

### 3.5 专题：唯一性校验的归属（内置结构约束）

> 用户追问："唯一性校验算不算一个规则？若是，它是规则模型里的一个小覆盖。"
> 结论：**唯一性不是"规则数据"，而是"结构型内置约束"；它在 `CONSTRAINT` 槽位下用"专用分支"覆盖了"通用表达式"语义，故确实可视为规则模型里的一个"小覆盖"。**

#### 3.5.1 代码取证：唯一性有 4 个载体，无一走 `rules:`

| # | 载体 | 声明位置 | 执行者 | 是否需要表达式求值器 | 是否"规则数据" |
|---|---|---|---|---|---|
| 1 | `MetaField.unique`（单字段） | 字段属性 | `MetadataDrivenValidator._check_unique`（`SELECT COUNT(*)`） | 否 | 否（结构型） |
| 2 | `indexes: type: unique`（复合） | 索引结构 | `_check_unique_indexes`（应用层；跳过"纯 bk"索引，保留 `(version_id, code)` 复合） | 否 | 否（结构型） |
| 3 | `semantics.business_key` 复合唯一 | 字段语义（含 `meaning` 文本） | `_check_business_key_composite`（自动补 `version_id`；从"产品内唯一"推 `product_id` scope） | 否 | 否（结构+语义型） |
| 4 | `MetaConstraint(constraint_type='unique')` | `rules: type: constraint` | `ValidationExecutor` | **是** | 槽位存在，但**实际零使用** |

证据：
- `MetaConstraint.constraint_type: unique / foreign_key / check / exclusion` — [models.py#L191-L198](file:///d:/filework/excel-to-diagram/meta/core/models.py#L191-L198)
- `_check_unique` — [metadata_driven_validator.py#L143-L164](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py#L143-L164)
- `_check_unique_indexes`（"单字段 bk 跳过、复合 bk+scope 参与"在 L494-509） — [metadata_driven_validator.py#L465-L509](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py#L465-L509)
- `_check_business_key_composite`（"产品内唯一"→ scope FK 映射 L411-420） — [metadata_driven_validator.py#L378-L420](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py#L378-L420)
- 全仓 `meta/schemas/*.yaml`：`type: constraint` = **0**；`type: unique` 全部出现在 `indexes:` 块，共 **8 处**（version 483、sub_domain 703、service_module 771、`role_effective_intents` 76、relationship 1686、enum_value 460、domain 568、business_object 1014）。
- 本轮删除的 `enum_value.unique_code_per_type`、`relationship.code_unique_within_version` 的**真实载体是 #2**：`enum_value.yaml` L457-462 `uidx_enum_values_type_code`、`relationship.yaml` L1682-1688 `uidx_relationships_version_code` → 删掉的是**重复声明**，唯一性能力未丢。

#### 3.5.2 回答"算不算一个规则"

按 §1 三轴切分：
- **不是"规则"（规则数据）**：唯一性由**字段 / 索引结构**声明，不写进 `rules:`，也不经 `RuleEngine`。
- **但占用"规则型要素"的一个槽位**：`RuleType.CONSTRAINT`（`MetaConstraint.constraint_type='unique'`）。这是"**槽位预置、实现为空**"——所以被删掉的 `validations: type: unique/constraint` 是往**空槽位**里写数据（且无消费者）。

#### 3.5.3 "小覆盖"的精确含义

通用规则的语义 = **"条件表达式 → `SafeExpressionEvaluator` 判定"**（AST 白名单，禁 `eval`/`import`，即**无 IO**）。唯一性天然**无法用表达式表达**（本质是"存在性 / 聚合查询"），因此它必须**绕开通用求值内核**，改由基础设施层的**专用分支**（查库）承担。这正是用户所说的"**里头的小覆盖**"：

> **同一个 `CONSTRAINT` 槽位下，required / unique / pattern / max_length / enum_values / fk_existence / business_key 这一族，用"专用分支"覆盖了"通用表达式"语义。**

这一族的共同特征：
1. **声明在结构**（字段属性 / 索引 / 语义），不在 `rules:`；
2. **执行在基础设施的专用校验器**（`MetadataDrivenValidator` 的 8 个硬编码分支），**不经过** `RuleEngine`；
3. **是预置的、不可配的规则实例**——即"规则引擎本可表达的能力，被硬编码成了结构约定"。

建议在 §1 分类中为这一族补正式子类：**结构型约束（built-in structural constraint）**，作为"规则型要素"与"结构型要素"的**交叉带**；避免未来再把 UNIQUE 误写成 `validations:` 或 `rules:`。

#### 3.5.4 两个后续判断（待决策）

| # | 问题 | 建议 |
|---|---|---|
| 1 | 要不要在 `rules:` 提供"真正的 UNIQUE 规则"（`type: constraint` + 查库能力）？ | **不提供**。会与索引结构重复（正是本轮踩的坑），且需给表达式内核开放 DB 权限（安全面）。若确需统一入口，应做成"`rules:` **引用** structural index id"，而非重写 UNIQUE 表达式。 |
| 2 | 派生目录 `.trae/specs/_business_rules/*.yaml` 出现**死引用** | 该目录由派生脚本从 schema 生成（原 771 条，供 `BusinessRuleAssertor.js` 消费）。本轮删除 `validations:` 后 **24 处 `source: ...:validations[...]` 失效**（enum_value 4、business_object 2、enum_type 4、annotation 4、version 3、relationship 2、domain/product/service_module/sub_domain/test_objects 各 1）。**✅ 已用「定向剔除」消除（非重跑生成器）**，明细见 §9 v1.5。 |

---

## 4. 消费侧的结构性问题（代码级发现）

> 本节是研究过程中的**实测发现**，不是推测。均为只读核实所得，供后续决策。

### 4.1 ✅ YAML `validations:` 声明通道在运行时**未被消费**（历史发现，P2/P3 已收口）

**证据链**：

1. YAML 有两个平行声明段：`validations:` 与 `rules:`，分别解析为 `MetaObject.validations` 与 `MetaObject.rules`（[yaml_loader.py#L2029-L2031](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L2029-L2031)、[#L2085-L2086](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L2085-L2086)），**两者不合并**。
2. `MetaObject.get_validations()` **只遍历 `self.rules`**（[models.py#L1084-L1086](file:///d:/filework/excel-to-diagram/meta/core/models.py#L1084-L1086)），**看不到 `self.validations`**。
3. 全仓 grep `\.validations\b` / `validations\s*=` / `get_validations(`：除 `yaml_loader`（加载）、`rule_chain`（同名但属 `RuleResult.validations`，无关）、cache `invalidations` 外，**无任何运行时代码读取 `MetaObject.validations`**。
4. `metadata_validator.py`（启动期校验）也只扫字段/派生（[L210-L215](file:///d:/filework/excel-to-diagram/meta/core/metadata_validator.py#L210-L215)），不读 `validations`。
5. **活样本**：平台自身的 `meta/schemas/business_object.yaml` 就用了 `validations:` 段（[#L1031-L1043](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L1031-L1043)），声明了 `version_id_required`、`code_format` 两条校验——**按当前消费链，它们不会被执行**。

**影响**：凡是把校验写在 YAML `validations:` 段的对象，其校验**静默失效**（对应 `MetaField.validations`，同样恒为空：`parse_field` 写死 `validations=[]`，[yaml_loader.py#L1346](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1346)）。

**待决策 → 已在 §8 定案并实施（P2/P3/P4 完成，见 §8.9）**：
- 度量结果：11 处使用**全部在 `meta/schemas/`**，`apps/` **零使用**；多数与字段属性**重复**，少数为**真缺口**（跨字段）。
- 定案：**三分法逐条处置**（D 删除 / M 迁字段属性 / G 迁入 `rules:`），随后删除该通道——原「全部并入 `rules:`」被数据否决（会产生重复执行）。详见 §8.2。
- **执行结果**：11 个 YAML 清空 `validations:`（25 条删除、1 条迁入 `rules:`、`enum_type.id_required` 改由字段属性承载）；`MetaObject.validations` 容器与 `get_validations()` 已移除；加载器对残留顶层 `validations:` 段**直接报错**。故本节的代码行号引用为**收口前的历史证据**。

### 4.2 校验三路并行（声明式校验缺少单一 SSOT）

如 §3.3 表：路径 1（规则型）/ 2（字段属性型）/ 3（拦截器型）**互不感知**，同一业务约束可能被表达两次（如 `required` 与 `semantics.mandatory`）。消费侧没有"这次为什么被拦"的统一解释入口。

**待决策**：是否需要一份"**校验统一视图**"（只读汇总三路，供 UI 与解释用），而非强行合并三套引擎——与 §8.6"共享内核、不合并求值器"的既有结论一致。

### 4.3 ✅ DEFAULT 被显式排除出通用链（已有设计纪律，记录备查）

`RuleEngine.execute_rules` 主动过滤 `RuleType.DEFAULT`（[L1289-L1290](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1289-L1290)），并附实测原因注释（E2E 曾把 `price_list` 从 `PL_ZOR` 误改为 `PL_SYS`）。这是"同一要素可有**多条消费路径**、但必须**显式互斥**"的正面样本——消费侧纪律已落地，无须改动。

### 4.4 编排（顺序 / 传播）存在**两套并存的顺序**（新增发现，详见编排专题）→ **P1 已收口**

承接 §2.4 的执行时机表，进一步核实"规则之间的顺序"：

- **拓扑链只挂在 `compute()` 一个入口**（[rule_executor.py#L1341](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1341)），其余入口（BEFORE_UPDATE / BEFORE_SAVE / AFTER_SAVE）走 [平铺 `sorted(priority)`](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1283-L1300)。→ **同一 trigger 可能被跑两次**，且校验的先后实际由 priority 决定、不由数据流拓扑决定。**（已收口，见本节末条）**
- `compute()` 曾**丢弃链的 `success`/`errors`**（[L1365-L1373](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1365-L1373)）→ 链内校验失败**被静默吞掉**。**✅ 已修（v2.1）**：`compute()` 不再运行链（删除 `use_chain`/`changed_fields` 形参），只做计算且顺序与 `execute_rules` 统一；校验职责唯一归 `execute_rules(BEFORE_SAVE)`。之所以不采用"上抛链结论"，是因为链内校验以 `condition` 当判定、平铺 `ValidationExecutor` 以 `action` 当判定，上抛会**误阻断合法保存**。
- 有环时**静默降级**为 priority 顺序，仅 `logger.warning`（[L1374-L1376](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1374-L1376)）。
- **跨对象链零接线**：`CrossObjectRuleChainExecutor` 全仓无生产调用；聚合派生[只 SELECT 不回写](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1095-L1145) → A→B→C 断链。
- `MetaRule.depends_on`（[models.py#L164](file:///d:/filework/excel-to-diagram/meta/core/models.py#L164)）曾为**死字段**（全仓无读取，依赖纯靠字段数据流隐式推断）。**✅ 已修（v2.1）**：装载侧在 `yaml_loader.parse_rule` 统一注入；建边侧新增 `EdgeType.EXPLICIT_DEPENDENCY` 显式边且**显式优先于推断**（反向冲突的推断边丢弃），可消除互相引用造成的假环。存量 YAML 未声明 `depends_on`，影响为零。
- **P0 只读实测（2026-10-03）**：51 个对象中有规则的仅 **8** 个；**7 个被报环但全是状态机误报**（`STATE_TRANSITION` 的 source/target 同为 `state_field`），拓扑链当前只在 **1** 个对象（relationship）上真正可用 → 说明"两套顺序"的危害尚未爆发，仅因**规则声明近乎为空**。
- **G9/G10 已修（v1.2）**：`rule_chain.py` 中①状态迁移之间不再成边（互斥选择 ≠ 数据依赖）、②`topological_sort` 遇环抛 `ValueError`（不再静默丢弃成环节点）。复测：**报环 7→0**、拓扑报错 0；运行时探针确认对存量行为中性。**但暴露新缺口 G11**：链内 `_execute_state_transition` 缺 flat 侧 gating，互斥兄弟会互相覆盖（`before_update` 下实测"激活"被静默改回"停用"）；当前不可达，**P1 顺序收口前必须先修**。

- **P1 顺序已收口（v2.0）**：顺序改由**依赖拓扑序唯一决定**——排序做进既有唯一入口 [`RuleEngine.execute_rules`](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1264-L1300)（新增 `_order_rules_by_dependency`，**不动任何调用点**）：图内规则按 `topological_sort` 次序、图外规则按 priority 追加末尾、报环回退 priority 并告警。**执行体不变**（仍是 flat 各类型执行器），故 `RuleExecutionReport` 阻断语义、`{state_field}_entered_at` 写入、触发器真分发 handler、派生真写库**全部维持原样**；审计复测对存量 8 个有规则对象**顺序差异 0**（行为中性）。「两套顺序」（G2）至此消除。**G3/G1 已于 v2.1 修复**：G3 → `compute()` 不再运行链、只做计算（校验唯一归 `execute_rules(BEFORE_SAVE)`）；G1 → `depends_on` 显式依赖已启用且优先于推断边。新增回归 `test_compute_only_computes_and_ignores_validation`、`test_explicit_dependency_edges`，规则相关 5 个测试文件全绿。

> 完整代码取证、8 家头部产品四维对标、5 条共性规律、6 阶段收口方案与 P0 实测明细，见 **[2026-10-03-rule-orchestration-ordering-and-propagation.md](./2026-10-03-rule-orchestration-ordering-and-propagation.md)**。

---

## 5. 头部产品的模型与架构（分层对标）

> 检索与官方文档核对结果。每产品的每个结论附官方来源；`【确证】`=官方文档/权威一手，`【推断】`=交叉印证。

### 5.1 分层归属对照表

| 产品 | 要素槽位（BO/元模型层） | 规则数据（可配置层） | 执行机器（引擎层） | 关键证据 |
|---|---|---|---|---|
| **SAP BOPF** | Node 的 **Node Elements** 内建 Determinations / Validations / Actions | Determin. 的 trigger node/field/time 可配；Action Validation 可定顺序 | Save Transaction 的 Check-Before-Save；BO 运行时框架 | 【确证】[BOPF Validations](https://abap-blog.ru/wp-content/uploads/2020/04/07-BOPF-Validations.pdf)：Determination 属 Node 模型要素 |
| **SAP RAP** | `define behavior for <CDS entity>` 内的 `determination` / `validation` / `precheck` **关键字槽位** | 触发条件写在声明里：`on modify { field X }` / `on save { create; field X }` | Behavior Pool 的 handler（`FOR DETERMINE` / `FOR VALIDATE`） | 【确证】[SAP PRESS RAP ToC](https://www.sap-press.com/abap-restful-application-programming-model_6161/toc/5589)：3.13 Internal Business Logic |
| **SAP 条件技术** | 无"槽位"概念，跨应用**引擎** | 条件表 + 条件记录 + 存取顺序（数据） | 同一台确定引擎驱动定价/输出/账户/批次/物料 | 【推断】[SAP 条件技术官方文档](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/7b24a64d9d0941bda1afa753263d9e39/d69fbe532789b44ce10000000a174cb4.html)（引用链；页面未抓取） |
| **Oracle EBS** | 属性级 defaulting rule 槽位（逐属性定义 source + 优先级） | Attribute Defaulting Rules（配置数据） | 订单默认引擎 | 【确证】[EBS Defaulting Rules](https://docs.oracle.com/cd/E18727-01/doc.121/e13408/T335476T459403.htm) |
| **Oracle Fusion** | Processing Constraints 挂在 entity（Header/Line）+ action 上 | 引用独立的 **Validation Rule Set**（配置数据） | 约束求值引擎 | 【确证】[Fusion 24B Processing Constraints](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/24b/faiom/processing-constraints.html)｜[EBS 12.1](https://docs.oracle.com/cd/E18727_01/doc.121/e13406/T373258T377247.htm) |
| **Salesforce** | Validation Rule 定义在 **object** 上（槽位=object 级的规则记录） | 规则记录（可配置数据） | **Order of Execution 固定第 5 步**（before-save flow=3 → before trigger=4 → **custom validation=5** → duplicate=6 → save=7） | 【确证】[Apex Order of Execution](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_triggers_order_of_execution.htm) |
| **ServiceNow** | Business Rule 落在**表级**（`sys_script.table` 必填） | 规则记录（`when` 可配） | 4 时机：`before`（校验/默认值）/ `after` / `async` / `display` | 【确证】[BusinessRule SDK API](https://servicenow.github.io/sdk/4.13.0/api/businessrule-api) |
| **Odoo** | 分散三处：`default=`（字段参数）/ `@api.constrains`（模型方法）/ `_sql_constraints`（模型属性） | 代码内声明（非配置数据） | ORM 触发 `@api.depends` 依赖图重算；DB 执行 SQL 约束 | 【确证】[Odoo ORM API](https://www.odoo.com/documentation/17.0/developer/reference/backend/orm.html)｜[Constraints](https://www.odoo.com/documentation/17.0/developer/tutorials/server_framework_101/10_constraints.html) |
| **Palantir Foundry** | **Object Type 不带规则**；可编辑性经 **Action Type** 生效 | Submission Criteria（旧称 validations）为 Action 级条件数据 | `/actions/{id}/validate` 由引擎统一求值参数约束 + 提交标准 | 【确证】[Submission criteria](https://www.palantir.com/docs/foundry/action-types/submission-criteria/)｜[Validate Action API](https://www.palantir.com/docs/foundry/api/ontology-resources/actions/validate-action) |

### 5.2 两个流派

| 流派 | 代表 | 特征 | 平台更像谁 |
|---|---|---|---|
| **代码声明式（槽位=语言/定义关键字）** | SAP BOPF、SAP RAP、Odoo | 规则以 BDEF 关键字 / 装饰器 / 字段参数形式存在，**不落为配置记录**；改动要动代码/发布 | 平台**部分像**：YAML `rules:` 是声明文件，随元数据发布（前文 §7 假设"一期无在线配置"） |
| **配置数据式（槽位=可配置记录）** | Salesforce、ServiceNow、Palantir、Oracle | 规则是**运行时可编辑的记录**，挂在 object/table/action 上，UI 可配 | 平台**正朝这里走**：`RuleProvider` 已为"规则从文件变记录"预留零改造升级点 |

### 5.3 共性结论（对第 3 节的印证）

1. **三段式是共识**：所有 8 个产品都区分「**要素槽位**（BO 层）/ **规则数据**（配置层）/ **执行机器**（引擎层）」。**没有一个产品把 Determination/Validation 当作"单层"概念**——这直接印证 §3.1"三选一设错了题型"。
2. **槽位住 BO、时机属 EO**：SAP BOPF 的 Determination 是 Node 要素、Salesforce 的 Validation 定义在 object，但两者都**在记录保存时**（EO 生命周期）执行。与平台"声明在 `MetaObject.rules`、执行在 `RuleContext`"结构同构。
3. **Validation 与 Determination 分属不同机器**：SAP 只有"确定"走条件技术引擎，"校验"走 BO/检查框架（不共用）；Odoo 的 `depends`（计算/派生）与 `constrains`（校验）是两个装饰器；平台亦是两套 Executor。**前文 §8.6"共享条件内核、不合并不求值器"在头部产品里普遍成立。**
4. **唯一的例外**：Palantir Object Type 明确**不带**规则，规则全挂 Action Type —— 可作为"要素挂哪层"的一个反例参照（**规则可以挂在"动作"而非"对象"上**），平台目前是"挂对象（rules）+ 动作（BO Action handler）"混合，方向不冲突。

---

## 6. 对本平台的启示

### 6.1 现状对齐（无需改动，仅确认）

| 平台实现 | 与头部产品对照 | 判定 |
|---|---|---|
| 规则声明在 `MetaObject.rules`（BO 层） | BOPF Node Elements / Salesforce object | ✅ 同构 |
| 执行作用于 `RuleContext.data`（EO 层） | BOPF Check-Before-Save / Salesforce Order of Execution | ✅ 同构 |
| 7 Executor + 求值内核（基础设施层） | 各产品独立引擎 | ✅ 同构 |
| Determination 与 Validation 用不同 Executor | SAP 确定/校验分机、Odoo depends/constrains | ✅ 同构 |
| `RuleProvider` 统一读取门面 | 无直接对标，是平台自研收口 | ✅ 有前瞻性 |

### 6.2 待决策项（登记，不在本轮实施）

| # | 事项 | 依据 | 建议优先级 |
|---|---|---|---|
| TBD-A | YAML `validations:` 段未被消费（§4.1） | 代码级核实 + §8.1 度量：11 处全在 `meta/schemas/`、`apps/` 零使用、多数与字段属性重复 | ✅ **已完成**（§8.2 三分法 → P2/P3/P4 收口，见 §8.9） |
| TBD-B | 校验三路并行，缺统一解释视图（§4.2） | §3.3 四路径 | P2 |
| TBD-C | `condition_parser` 属意图/权限子系统，非规则引擎（§2.5） | 实测 [effective_intent_checker.py#L30](file:///d:/filework/excel-to-diagram/meta/core/effective_intent_checker.py#L30) / [intent_scope_adapter.py#L35](file:///d:/filework/excel-to-diagram/meta/core/intent_scope_adapter.py#L35) 引用；与规则引擎**不应合并**（印证 §8.6） | **P3**（纯文档口径修正） |
| TBD-D | `RuleType.PERMISSION` 枚举存在但无 Executor（§1.2） | 分发矩阵 §2.3 无该分支 | P3（清理或补实现） |

### 6.3 与前文的口径修正

- 前文 §8.6 判"三类规则**共享条件内核**"——**需收窄**：当前代码层面共享的只有 **`SafeExpressionEvaluator`（求值内核）**；`condition_parser`（解析层）**未被 `rule_executor` 导入**，解析路径尚未统一（§2.5）。
- 前文 §10.6 判"校验 validation ✅ 已有"——**成立，但需补注**：平台实际有 **4 条**校验消费路径，其中 YAML `validations:` 一条**静默失效**（§3.3 / §4.1）。

---

## 7. 证据表

| # | 结论 | 证据（代码/文档） |
|---|---|---|
| E1 | `MetaRule` 为唯一基类，8 个 rule_type | [models.py#L141-L170](file:///d:/filework/excel-to-diagram/meta/core/models.py#L141-L170)、[models_enums.py#L94-L104](file:///d:/filework/excel-to-diagram/meta/core/models_enums.py#L94-L104) |
| E2 | `MetaAction` 不继承 `MetaRule`（结构型 ≠ 规则型） | [models.py#L609](file:///d:/filework/excel-to-diagram/meta/core/models.py#L609) |
| E3 | `RuleEngine` 持 6 Executor | [rule_executor.py#L1254-L1262](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1254-L1262) |
| E4 | 分发按 `rule_type` | [rule_executor.py#L1302-L1324](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1302-L1324) |
| E5 | DEFAULT 显式排除出通用链 | [rule_executor.py#L1284-L1290](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1284-L1290) |
| E6 | `RuleContext` 持实例数据 + 自动值集合 | [rule_executor.py#L139-L157](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L139-L157) |
| E7 | `validations:` 与 `rules:` 平行解析、不合并（**收口前**；P3 已移除 `validations` 解析） | [yaml_loader.py#L2029-L2031](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L2029-L2031)、[#L2085-L2086](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L2085-L2086) |
| E8 | `get_validations()` 只遍历 `self.rules`（**收口前**；P3 已移除该方法） | [models.py#L1084-L1086](file:///d:/filework/excel-to-diagram/meta/core/models.py#L1084-L1086) |
| E9 | 全仓无运行时读取 `MetaObject.validations` | grep `\.validations\b` / `get_validations(`（仅定义处命中） |
| E10 | 活样本：`business_object.yaml` 用 `validations:` 声明校验（**收口前**；P2 已删除该段） | [business_object.yaml#L1031-L1043](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L1031-L1043) |
| E11 | `parse_field` 写死 `validations=[]` | [yaml_loader.py#L1346](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1346) |
| E12 | 字段属性校验走 `MetadataDrivenValidator` | [metadata_driven_validator.py#L30-L42](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py#L30-L42) |
| E13 | `ConstraintEngine` 支撑拦截器链校验 | [constraint_engine.py#L21-L31](file:///d:/filework/excel-to-diagram/meta/core/constraint_engine.py#L21-L31) |
| E14 | `RuleProvider` 统一读取入口 | [rule_provider.py](file:///d:/filework/excel-to-diagram/meta/core/rule_provider.py) |
| E15 | 请求级生命周期调用点 | [action_executor.py#L1612-L2008](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L1612-L2008) |
| E16–E23 | 头部产品分层归属（8 个产品） | 见 §5.1 各行 URL |

---

## 8. 执行方案（细化）

> **前置说明**：本节修正 §4.1 的初步倾向。Step 0 度量（只读）后，原「**方案 A：全部并入 `rules:`**」**被数据否决**，见 §8.2。

### 8.1 Step 0 度量结果（已完成，只读）

| 项 | 结果 | 依据 |
|---|---|---|
| 使用 `validations:` 的对象 | **11 个，全部在 `meta/schemas/`**（平台自身对象） | grep `^validations:` 全仓 |
| 业务应用（`apps/*/schemas/`）使用数 | **0**（warehouse / tms / hello_world 均无） | Glob + grep |
| 条目形态 | 绝大多数为「X 必填」式（`X is not None` / `!= ''`）；少数为格式/跨字段 | 逐文件摘录 |
| `rules: type: validation` 全仓使用数 | **0**（`rules:` 仅用于 `state_transition`） | grep `type: validation/constraint` |
| `parse_validation` / `MetaObject.validations` 测试覆盖 | **0** | grep `meta/tests` |

**抽查证据（两类代表）**：

| 对象 | 孤儿校验 | 字段属性等价物 | 判定 |
|---|---|---|---|
| `business_object` | `version_id_required` | `version_id.required: true`（[L534-L538](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L534-L538)） | **重复** |
| `business_object` | `code_format: ^[A-Z][A-Z0-9_]*$` | `code.semantics.pattern`（**同一正则**，[L752-L762](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L752-L762)） | **重复** |
| `relationship` | `version_id_required` | `version_id.required: true`（[L450-L454](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L450-L454)） | **重复** |
| `relationship` | `source_not_equal_target`（cross_field：`source_bo_id != target_bo_id`） | **无** | **真缺口** |

> `semantics.pattern` 确由 `MetadataDrivenValidator._check_pattern` 消费（[metadata_driven_validator.py#L164-L179](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py#L164-L179)），故 `code_format` 实际已生效。

**结论**：`validations:` 通道是**混合体** —— 多数是「已被字段属性兜住的重复」，少数是「真没生效的约束」。

### 8.2 方案修正：三分法逐条处置（替代原「全部并入」）

**否决原方案 A 的理由**：把 11 个文件的条目无差别并入 `rules:`，会让 **D 类重复条目被二次执行**（字段属性路径已生效），并产生大面积行为变更 —— 「修 bug」变成「引入重复 + 变更」。数据不支持一刀切。

**修正为三分法**：

| 类 | 定义 | 处置 | 目标载体 |
|---|---|---|---|
| **D 重复** | 条目语义已由字段属性强制（`required` / `semantics.pattern` / `max_length` / `enum_values` / `unique`） | **删除**，不迁移 | 无（字段属性即 SSOT） |
| **M 可字段化** | 可表达为字段属性但尚未声明 | **迁到字段属性** | `MetaField.required` / `semantics.pattern` 等 |
| **G 真缺口** | 无字段属性等价物（**跨字段 / 对象级**，如 `source_bo_id != target_bo_id`） | **迁入 `rules:`**（`type: validation`） | `MetaObject.rules` |

**处置后收口**（已实施）：删除 `validations:` 声明段与 `MetaObject.validations` 容器，加载器不再解析该段（顶层残留段**直接报错** `DeprecatedSchemaSectionError`，防回流）。

### 8.3 阶段与任务

| Phase | 任务 | 触及 | 产出 | 验收 |
|---|---|---|---|---|
| **P0** | 影响面度量 | 只读 | §8.1 表 | ✅ 已完成 |
| **P1** | 逐条分类清单（11 文件全部条目 → D/M/G + 目标） | 只读产出清单 | §8.7 处置表 | ✅ 已完成（28 条，D21/S4/M0/G3） |
| **P2** | YAML 处置：D 删 / M 迁字段 / G 迁 rules | 11 个 `meta/schemas/*.yaml` | YAML 变更 | ✅ 已完成：25 条删除 + `relationship.source_not_equal_target` 迁入 `rules:`；11 文件 `validations:` 段清空 |
| **P3** | 代码收口：删通道 + 删容器 + 加载器护栏 | [yaml_loader.py](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py)、[models.py](file:///d:/filework/excel-to-diagram/meta/core/models.py)、[metadata_driven_validator.py](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py) | 代码变更 | ✅ 已完成：`MetaObject.validations`/`get_validations` 移除；残留顶层 `validations:` 段报 `DeprecatedSchemaSectionError`；`_skip_field` 对 `business_key` 的 id 不再跳过 |
| **P4** | 测试 | `meta/tests/test_rule_validations_migration.py` | 单测 | ✅ 已完成（4 passed）：① G 类保存链路真阻断；② 字段属性 id 路径不回归；③ 残留 `validations:` 段被拒；④ 容器已移除 |
| **P5** | 文档回填 | 本文 §4.1/§6.2 + Spec/Plan | 口径更新 | ✅ 已完成：§4.1/§6.2/§8.2/§8.3/§8.9 与本日志同步；Spec/Plan 未涉及该段，无需改动 |

### 8.4 关键实现口径（避坑）

1. **G 类必须进 `rules:`，不能只改访问器**：运行时取规则走 [`get_rules_by_trigger`](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1283) → 只遍历 `self.rules`（[models.py#L1080-L1082](file:///d:/filework/excel-to-diagram/meta/core/models.py#L1080-L1082)）。只让 `get_validations()` 读另一个容器**无效**。
2. **M 类不要迁进 `rules:`**：字段属性路径（`MetadataDrivenValidator`）已生效，迁入会产生双份执行。
3. **`rules: type: validation` 是首次启用**：全仓 YAML 目前**零使用**该类型（`rules:` 仅用于 `state_transition`），且 `ValidationExecutor` 无测试。**P4 必须先补一条能证明「阻断生效」的测试**，再迁 G 类。
4. **不确定顺序要拍板**：若某对象同时有 `rules:` 与 G 类迁移项，`priority` 都为 100，需给稳定 tie-break（建议沿用 DEFAULT 的 `rule.id` 字典序先例）。

### 8.5 风险与回滚

| 风险 | 说明 | 缓解 |
|---|---|---|
| G 类迁移后**突然开始阻断** | 原本失效的约束一旦生效，可能挡住历史/异常数据 | 先枚举 G 类影响面（预计极少）；按 TR 灰度：先加日志/告警，确认后再转阻断 |
| `ValidationExecutor` 路径未经验证 | 首次使用 + 零测试 | P4 先补测试（§8.4 口径 3） |
| D 类误删 | 若某条实为 G 类被误判为 D | P1 清单逐条留证（字段属性行号）；判不准的一律归 G |
| 误伤业务应用 | 实测 `apps/` 零使用，风险极低 | 已在 §8.1 证实 |

**回滚**：YAML 与代码改动可整体 revert；P3 的「拒绝残留段」可先用 **warning** 灰度、确认后再转 error。

### 8.6 验证方式

- **单测**：`python d:\filework\test.py --file meta/tests/<新增测试文件>`
- **回归**：schema 加载相关既有测试 + 保存链路测试
- **手工**：取 G 类对象（`relationship`），构造 `source_bo_id == target_bo_id` 的保存请求，断言被阻断

### 8.7 P1 逐条分类清单（已完成，只读产出）

11 个文件共 **28 条**孤儿校验，全部逐条落判：

| 判定 | 条数 | 处置 |
|---|---|---|
| **D 重复**（已被字段属性/索引强制） | 21 | 删，不迁移 |
| **S 陈旧**（与现行字段设计矛盾，P1 新增类） | 4 | 删，不迁移 |
| **M 可字段化** | 0 | — |
| **G 真缺口**（无字段属性等价物） | 3 | 迁入 `rules: type: validation` |

> **P1 新增发现**：原三分法只有「重复 → 删」，但实测存在一类**既没被强制、又不该强制**的条目 —— 它们与字段现行设计**直接矛盾**（字段已显式改成 `required: false`、已标注"历史字段"、已把 `value_help.validation` 关掉），或含**测试残留**（硬编码枚举里混入 `TEST`）。若按 G 迁入 `rules:`，会**凭空开始阻断合法写入**。故新增 **S 类**，与 D 类同为"删除"，但删除理由不同。

#### 8.7.1 全量清单

| # | 文件 | 条目 | 类型 | 判定 | 依据 |
|---|---|---|---|---|---|
| 1 | annotation | `target_type_required` | field | **D** | `target_type.required: true`（[L160](file:///d:/filework/excel-to-diagram/meta/schemas/annotation.yaml#L160)） |
| 2 | annotation | `target_id_required` | field | **D** | `target_id.required: true`（[L203](file:///d:/filework/excel-to-diagram/meta/schemas/annotation.yaml#L203)） |
| 3 | annotation | `category_required` | field | **D** | `category.required: true`（[L219](file:///d:/filework/excel-to-diagram/meta/schemas/annotation.yaml#L219)）+ `semantics.mandatory: true`（L225） |
| 4 | annotation | `category_valid` | field | **S** | 硬编码列表 `[... 'tip', 'TEST']` 含测试残留；SSOT 实为 `annotation_category` 枚举（`ui.enum_type` + `value_help` strict，[L235-L239](file:///d:/filework/excel-to-diagram/meta/schemas/annotation.yaml#L235-L239)）。迁 rules 会误挡合法分类 |
| 5 | enum_type | `id_required` | field | **G** | 字段已声明 `required: true`（[L224](file:///d:/filework/excel-to-diagram/meta/schemas/enum_type.yaml#L224)），但 [`_skip_field`](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py#L84-L91) 对 `field.id == 'id'` **无条件跳过** → 字段属性路径实际失效 |
| 6 | enum_type | `name_required` | field | **D** | `name.required: true`（[L253](file:///d:/filework/excel-to-diagram/meta/schemas/enum_type.yaml#L253)） |
| 7 | enum_type | `category_required` | field | **D** | `category.required: true`（[L275](file:///d:/filework/excel-to-diagram/meta/schemas/enum_type.yaml#L275)）+ `enum_values`（L283） |
| 8 | enum_type | `mutability_required` | field | **D** | `mutability.required: true`（[L312](file:///d:/filework/excel-to-diagram/meta/schemas/enum_type.yaml#L312)）+ `enum_values`（L320） |
| 9 | enum_value | `enum_type_id_required` | field | **D** | `enum_type_id.required: true`（[L212](file:///d:/filework/excel-to-diagram/meta/schemas/enum_value.yaml#L212)） |
| 10 | enum_value | `code_required` | field | **D** | `code.required: true`（[L241](file:///d:/filework/excel-to-diagram/meta/schemas/enum_value.yaml#L241)） |
| 11 | enum_value | `name_required` | field | **D** | `name.required: true`（[L265](file:///d:/filework/excel-to-diagram/meta/schemas/enum_value.yaml#L265)） |
| 12 | enum_value | `unique_code_per_type` | constraint | **D** | `indexes.uidx_enum_values_type_code` unique on `(enum_type_id, code)`（[L457-L461](file:///d:/filework/excel-to-diagram/meta/schemas/enum_value.yaml#L457-L461)）→ 由 `_check_unique_indexes` 消费 |
| 13 | business_object | `version_id_required` | field | **D** | `version_id.required: true`（[L534-L538](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L534-L538)） |
| 14 | business_object | `code_format` | field | **D** | `code.semantics.pattern: ^[A-Z][A-Z0-9_]*$`（**同一正则**，[L752-L762](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L752-L762)）。注：severity 冲突（此处 `warning` vs 字段路径 error 级） |
| 15 | domain | `version_id_required` | field | **D** | `version_id.required: true`（[L361-L365](file:///d:/filework/excel-to-diagram/meta/schemas/domain.yaml#L361-L365)） |
| 16 | product | `name_required` | field | **D** | `name.required: true`（[L326-L330](file:///d:/filework/excel-to-diagram/meta/schemas/product.yaml#L326-L330)） |
| 17 | relationship | `version_id_required` | field | **D** | `version_id.required: true`（[L450-L454](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L450-L454)） |
| 18 | relationship | `source_not_equal_target` | cross_field | **G** | 对象级跨字段，无字段属性等价物；字段仅声明 `required: true`（[L862-L866](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L862-L866)、[L919-L923](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L919-L923)） |
| 19 | relationship | `code_unique_within_version` | unique | **D** | `indexes.uidx_relationships_version_code` unique on `(version_id, code)`（[L1682-L1688](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L1682-L1688)） |
| 20 | relationship | `relation_type_in_enum` | field | **S** | 字段 `required` 已被显式改为 `false` 并留 FIX 注释（[L1068-L1071](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L1068-L1071)："业务方反馈…允许留空"）；`value_help` strict 绑定 DB 枚举；规则硬编码 4 值（`GENERATES/UPDATES/TRIGGERS/REFERENCES`）与 DB 枚举不一致 |
| 21 | relationship | `relation_direction_in_enum` | field | **S** | 字段 `value_help.behavior.validation: false`（[L1124](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L1124)）已显式关闭校验；规则自身也允许 `None`；硬编码 3 值陈旧 |
| 22 | relationship | `relation_code_required` | field | **S** | `relation_code` 已标注"历史字段"、`default: ''`、`hidden_in_form: true`、**无** `required: true`（[L1044-L1059](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L1044-L1059)）→ 规则与现行设计直接矛盾 |
| 23 | sub_domain | `version_id_required` | field | **D** | `version_id.required: true`（[L400-L404](file:///d:/filework/excel-to-diagram/meta/schemas/sub_domain.yaml#L400-L404)） |
| 24 | service_module | `version_id_required` | field | **D** | `version_id.required: true`（[L422-L426](file:///d:/filework/excel-to-diagram/meta/schemas/service_module.yaml#L422-L426)） |
| 25 | test_objects | `name_required` | field | **D** | `name.required: true`（[L52-L56](file:///d:/filework/excel-to-diagram/meta/schemas/test_objects.yaml#L52-L56)） |
| 26 | version | `name_required` | field | **D** | `name.required: true`（[L316-L320](file:///d:/filework/excel-to-diagram/meta/schemas/version.yaml#L316-L320)） |
| 27 | version | `product_id_required` | field | **D** | `product_id.required: true`（[L278-L282](file:///d:/filework/excel-to-diagram/meta/schemas/version.yaml#L278-L282)） |
| 28 | version | `only_one_current_per_product` | business | **G** | 对象级业务规则（命令式代码块，含 `data_source.query`），无字段属性等价物；字段 `is_current` 仅 `default: false`（[L367-L372](file:///d:/filework/excel-to-diagram/meta/schemas/version.yaml#L367-L372)） |

#### 8.7.2 结论要点

1. **D 类 21 条占 75%** —— 印证 §8.1 判断："该通道绝大多数是重复"，删掉无行为影响。
2. **G 类只有 3 条**，且形态集中：
   - `enum_type.id_required` —— 根因是 `_skip_field` 跳过 `id`，**P2 需拍板修法**：走 `rules:`（迁移）还是修 `_skip_field`（让 `business_key: true` 的 id 不被跳过）。
   - `relationship.source_not_equal_target` —— 跨字段，**最值钱的真缺口**，P4 用它做"阻断生效"证明。
   - `version.only_one_current_per_product` —— 对象级 + 需查库，**注意**：`ValidationExecutor` 只做表达式求值（`SafeExpressionEvaluator` 无 DB 访问），该规则原文是命令式代码块（`if is_current: existing = data_source.query(...)`），**不能直接搬进 `rules:` 的 `condition`**。候选处置：改用 `CONSTRAINT`+子查询表达式（若求值器支持），或转 `MetaAction`/`MetaComputation`，或在 P2 单列一项待评估。
3. **S 类 4 条**（新增类）—— 全部集中在 `annotation` 与 `relationship`，特征是"字段设计已前进、孤儿规则停在原地"。**建议直接删除**，不迁移、不改字段。
4. **M 类为 0** —— 说明不存在"能字段化但没声明"的中间态；字段属性已经覆盖到位。

### 8.8 P2 待拍板的三个点

| # | 待定 | 建议 |
|---|---|---|
| 1 | **S 类是否确认新增并入"删除"** | 建议确认。否则 4 条会被误迁入 `rules:` 而**凭空阻断合法写入** |
| 2 | `enum_type.id_required` 修法 | 建议**修 `_skip_field`**（`business_key: true` 的 id 不跳过），保持"字段属性即 SSOT"，不新增规则 |
| 3 | `version.only_one_current_per_product` 落点 | 建议**先不迁**，P2 单列评估（求值器无 DB 能力，硬迁会失效）；避免"迁了等于没迁" |

### 8.9 P2~P4 执行结果（已落地）

**拍板采纳**：三点建议全部采纳。S 类确认并入"删除"；`enum_type.id_required` 改由字段属性承载（修 `_skip_field`）；`version.only_one_current_per_product` 暂不迁移（求值器无 DB 访问能力，硬迁会失效），保留为本节待评估项。

**P2（YAML）**：11 个 `meta/schemas/*.yaml` 顶层 `validations:` 段全部清空——**25 条删除**（D 21 + S 4）、**1 条迁移**（`relationship.source_not_equal_target` → `rules:` 内 `type: validation` / `scope: cross_field` / `severity: error` / `priority: 100`）、**`enum_type.id_required` 不新增规则**（由 `id.required: true` + `_skip_field` 修复承载）、**`version.only_one_current_per_product` 删除并单列**。

**P3（代码）**：
- [models.py](file:///d:/filework/excel-to-diagram/meta/core/models.py)：移除 `MetaObject.validations` 容器与 `get_validations()`。
- [yaml_loader.py](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py)：移除 `parse_meta_object` 的 `validations` 解析与 aspect 段合并；新增 `DeprecatedSchemaSectionError`，**顶层 `validations:` 段在加载期直接报错**（`load_yaml_file` 对该异常不吞，向 `load_yaml_directory` 传播）。
- [metadata_driven_validator.py](file:///d:/filework/excel-to-diagram/meta/core/metadata_driven_validator.py)：`_skip_field` 改为「`id` 且非 `business_key` 才跳过」，使 `enum_type.id` 的 `required`/`pattern`/`unique` 生效（全仓影响面：仅 `enum_type`，其余 `id` 字段均无 `business_key`）。

**P4（测试）**：新增 [test_rule_validations_migration.py](file:///d:/filework/excel-to-diagram/meta/tests/test_rule_validations_migration.py)，**4 passed**：
1. `relationship.source_not_equal_target` 在 `BEFORE_SAVE` 真阻断（相等即失败、不等即通过）——首次验证 `rules: type: validation` 生效；
2. `enum_type.id`（business_key）不被 `_skip_field` 跳过，普通 `id` 保持跳过；
3. 残留顶层 `validations:` 段抛 `DeprecatedSchemaSectionError`；
4. `MetaObject` 不再持有 `validations` 字段 / `get_validations`。

**回归**：`load_yaml_directory(meta/schemas)` 正常加载 **50 个对象**，无 schema 被护栏误拒；`relationship.rules` 含 `source_not_equal_target`（`validation`, trigger `before_save`）。`test_rule_engine.py` **9 passed**。`test_metadata_completeness.py::test_no_duplicate_action_ids` **失败与本轮无关**（源为 `_audit_materialization.yaml` 等非对象 yaml 的空 id + 空 action id，属既有问题）。

**遗留（§8.8 第 3 点）**：`version.only_one_current_per_product` 需"每产品仅一个当前版本"的对象级+查库约束，当前 `ValidationExecutor` 表达式求值器无 DB 访问，无法直接承载；候选落点为 `MetaAction` handler（如 `clear_other_current_versions` 已有同类实现）或专用校验器，待后续单列评估。

**派生目录收尾（§3.5.4 #2）**：`.trae/specs/_business_rules/` 因删除 `validations:` 产生的 **24 处死引用已定向剔除**（`:validations[` 与 `_index.json` 的 `-VAL-` 均归零，`total_rules` 771→747）；e2e `enum-management.spec.js` 改指有效 id `BR-enum_type-FLD-REQ-name`。**未重跑生成器**：两个脚本均无 `rules:` / `validations:` 抽取器，重跑会缩水且改不对（详见 §9 v1.5）。

---

## 9. 变更记录

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v1.0 | 2026-10-03 | 首版：消费侧模型（BO 声明 → EO 实例 → 基础设施三段）；模型要素 vs 规则三轴切分；Determination/Validation 分层归属判定（三段式，非三选一）；**发现并记录 `validations:` 声明通道运行时未被消费**；校验 4 条消费路径；8 家头部产品分层对标（附官方 URL）；4 项待决策登记（TBD-A~D）；前文 §8.6 / §10.6 口径修正 | AI Assistant |
| v1.1 | 2026-10-03 | 新增 §8 执行方案（细化）：Step 0 只读度量（11 处 `validations:` 全在 `meta/schemas/`、`apps/` 零使用、`rules: type: validation` 零使用、相关测试零覆盖）；**原「全部并入 `rules:`」被数据否决**，改为三分法（D 删 / M 迁字段属性 / G 迁 `rules:`）；P0~P5 阶段任务表 + 4 条避坑口径 + 风险回滚 + 验证方式；同步更新 §4.1 定案指针、§6.2 TBD-A/TBD-C 口径（TBD-C 降级为 P3 纯文档修正） | AI Assistant |
| v1.2 | 2026-10-03 | **P1 完成**：新增 §8.7 全量清单（11 文件 28 条 → D21 / S4 / M0 / G3，逐条附字段属性行号依据）+ §8.8 P2 待拍板 3 点。**P1 新增发现 S 类**（陈旧/与现行字段设计矛盾，如 `relationship.relation_type` 已改 `required: false`、`relation_code` 已标历史字段）—— 此类若按 G 迁移会凭空阻断合法写入，建议与 D 类同为删除 | AI Assistant |
| v1.3 | 2026-10-03 | **P2/P3/P4/P5 完成**（§8.8 三点建议全采纳）：11 个 schema 清空 `validations:`（25 删 + 1 迁 `rules:`）；移除 `MetaObject.validations`/`get_validations`；加载器对残留顶层 `validations:` 段报 `DeprecatedSchemaSectionError`；`_skip_field` 对 `business_key` 的 `id` 不再跳过；新增 `test_rule_validations_migration.py`（4 passed）。新增 §8.9 执行结果；§4.1/§6.2/§7/§8.2/§8.3 口径同步为"已收口" | AI Assistant |
| v1.4 | 2026-10-03 | **新增 §3.5 专题：唯一性校验的归属**（代码取证 4 个载体 + "内置结构约束"定位 + "小覆盖"含义 + 2 项待决策）。结论：唯一性是**结构型内置约束**，占用 `CONSTRAINT` 槽位但零实现；其 `validations: type: unique/constraint` 声明为"错位数据"，删除正确且唯一性能力未丢（真实载体为 `unique:` / `indexes: type: unique` / `business_key`）。同时发现派生目录 `.trae/specs/_business_rules/*.yaml` 有 **24 处死引用**（指向已删的 `validations[...]`），待重跑 `discover_business_rules_v4.py` | AI Assistant |
| v1.5 | 2026-10-03 | **§3.5.4 待决策 #2 已结**：派生目录 24 处死引用**已消除**。① 采用**定向剔除**（临时脚本只删 `source: ...:validations[...]` 条目），**未重跑生成器**——实测 `discover_business_rules.py`（unversioned）会把 771 条缩水到 84 条（丢弃 field_constraint/relation/import_export/aspect 混合内容），`discover_business_rules_v4.py` 只产出 `_composite/`，两者都**无 `rules:` / `validations:` 抽取器**，重跑会把 24 处"改错"而非"改对"。② 结果：`:validations[` 归零、`_index.json` 的 `-VAL-` 归零、`total_rules` 771→747（objects=40，逐对象求和自洽）。③ e2e `enum-management.spec.js` L47 由失效的 `BR-enum_type-VAL-name_required` 改指有效 id `BR-enum_type-FLD-REQ-name`。④ **遗留缺口**：unversioned 生成器无 `rules:` 抽取器 → 本轮 G 类迁移规则 `relationship.source_not_equal_target` **未进入**派生目录（`BusinessRuleAssertor` 无法覆盖），是否补抽取器待决策。 | AI Assistant |
| v1.6 | 2026-10-03 | **新增 §4.4 编排（顺序/传播）两套顺序并存**（代码取证：拓扑链仅挂 `compute()`、链内校验被吞、有环静默降级、跨对象链零接线、聚合只 SELECT 不回写、`depends_on` 死字段）；**关联文档新增编排专题** [2026-10-03-rule-orchestration-ordering-and-propagation.md](./2026-10-03-rule-orchestration-ordering-and-propagation.md)（8 家头部产品四维对标 + 5 条共性规律 + "一套顺序、两个通道、三种硬约束"方案 + 6 阶段 + 5 项待决策） | AI Assistant |
| v1.7 | 2026-10-03 | **编排专题 P0 实测回填**：§4.4 增补 P0 只读实测结论（51 对象 / 有规则仅 8 个 / 7 个报环全是状态机误报 / 拓扑链仅 1 个对象可用）；编排专题同步升 v1.1（新增 G9、G10 与 §1.4 实测） | AI Assistant |
| v1.8 | 2026-10-03 | **编排专题 G9/G10 已修**：§4.4 增补修复与复测结论（报环 7→0、拓扑报错 0、行为中性已实证）+ 新缺口 G11（链内状态迁移缺 gating）；编排专题同步升 v1.2 | AI Assistant |
| v1.9 | 2026-10-03 | **编排专题 D7 + G11 已修**：D7 统一同层 tie-break 为**声明顺序**（顺序差异 8→0）；G11 在链内补齐 flat 侧状态迁移 gating 并排除同 `state_field` 互斥兄弟（四情形探针链与 flat 一致）。**P1 不能直接切唯一入口**——§1.6 列出 7 项阻塞（链内 TRIGGER/DERIVATION 为 stub、不写 `entered_at`、执行集合差异、返回类型不同、传播循环、trigger 过滤只作用于初始集合），须先跑影子模式再收口；编排专题同步升 v1.3 | AI Assistant |
| v2.0 | 2026-10-03 | **P1 顺序唯一入口已落地**（用户拍板「直接切」）：顺序改由依赖拓扑序**唯一决定**，排序做进既有唯一入口 `RuleEngine.execute_rules`（新增 `_order_rules_by_dependency`，不动调用点），**执行体仍是 flat 各类型执行器**（只改顺序）→ 编排专题 §1.6 的 7 项阻塞（只在"链 executor 成为唯一执行体"时成立）**全部失效**。审计复测：环 0 / 拓扑报错 0 / **顺序差异 0** / 未建图规则 0（对存量 8 个有规则对象行为中性）。新增跨字段校验回归用例 `test_rule_engine_cross_field_validation_order`；规则相关 5 个测试文件全绿。§4.4 增补收口结论（「两套顺序」G2 消除；G3/G1 留后续）；编排专题同步升 v1.4 | AI Assistant |
| v2.1 | 2026-10-03 | **§4.4 遗留的 G3/G1 已修**。G3：`compute()` 不再运行 `ImplicitRuleChainExecutor`（删除 `use_chain`/`changed_fields` 形参），只做计算且顺序与 `execute_rules` 统一——链内校验以 `condition` 当判定、平铺 `ValidationExecutor` 以 `action` 当判定，**上抛链结论会误阻断合法保存**，故根治方向是"让第二个引擎不再跑"而非"上抛其结论"；`compute()` 顺带不再重复执行校验。G1：`depends_on` 显式依赖启用（`yaml_loader.parse_rule` 统一注入；`EdgeType.EXPLICIT_DEPENDENCY` 显式边优先于推断边，反向冲突的推断边丢弃）。新增回归 `test_compute_only_computes_and_ignores_validation`、`test_explicit_dependency_edges`；`test_rule_chain`(6) / `test_rule_engine`(11) / `test_rule_provider_unit`(9) / `test_rule_validations_migration`(4) / `test_derivation`(6) 全绿；审计复测顺序差异仍为 0。§4.4 三条 bullet 口径同步为"已修"；编排专题同步升 v1.5 | AI Assistant |
