# 规则模型（属性确定）Spec + RFC

> **版本**：v1.3 | **日期**：2026-10-03 | **状态**：已实施（一期 M1~M4 + 二期 M5/M6/M7 已落地）
> **关联文档**：
> - [2026-10-02-rule-model-research.md](./2026-10-02-rule-model-research.md)（v1.11，对标研究报告）
> - [2026-10-02-rule-model-implementation-plan.md](./2026-10-02-rule-model-implementation-plan.md)（实施计划 / Phase / 任务 / 里程碑）
> - 对象模型总纲（计划对象 vs 事实对象）§5.4 谁是事实

---

## 1. 背景与目标

**背景**：新建业务对象时，用户需按录入因子（订单类型 / 行类型 / 客户 / 物料等）自动确定其它属性、合同与字段。平台**已有规则框架**（`MetaRule` + `RuleEngine` + `DERIVATION` + `computation_service`），但缺「属性确定（defaulting）」语义，且规则读取散落在 9 处直接遍历 `meta_obj.rules`，后期若要求在线配规则，变更成本大。

**对标结论（研究报告 v1.9，共性 C1–C10）**，与本期最相关者：

- **C2** 保存前内存改写是主流时机
- **C3** 覆盖语义必须显式（仅空值才填 / System-User 开关）
- **C4** 顺序号 + 首个命中 + 必须定义 tie-break
- **C6** 展示用派生 ≠ 写入用默认
- **C8** 必须留命令式逃生门
- **C9** 可解释性 = 能回放
- **C10** 再判定必须显式规定「清空 or 保留」

**本期目标**

- **G1** 让「按因子自动带出属性值」成为一等公民，配置在 meta 规则里，不写代码
- **G2** 零新表、复用现有 `MetaRule`/`RuleEngine`，只扩语义 + 收口读取入口
- **G3** 可解释：每次自动带出都能回答「哪条规则、因何命中、值从哪来」
- **G4** 为后期「在线配置规则」预留零改造升级路径（`RuleProvider`）

**本期非目标**

- **N1** 拆分/分摊（1→N 守恒）、反向汇总（N→1）→ 二期
- **N2** dry-run 预演 → 二期（一期只做日志，但数据结构按可回放设计）。**二期 v1 已落地**（`ActionExecutor.dry_run_defaults` + `POST /api/v1/meta/<object_type>/defaults-preview`），范围为「守卫段以内」的 DEFAULT 规则链
- **N3** 规则版本化 + 生效期（**不承诺**「按当时规则复现历史单据」）
- **N4** 在线配置 UI

---

## 2. 需求类型总览

| 类型 | 编号段 | 说明 |
|---|---|---|
| 功能需求 FR | FR-001 … FR-012 | 本期必做 |
| 非功能需求 NFR | NFR-001 … NFR-006 | 质量属性 |
| 接口/集成需求 IF | IF-001 … IF-005 | 与现有代码的接缝 |
| 过渡/迁移需求 TR | TR-001 … TR-003 | 灰度与迁移 |
| 约束与假设 | §7 | |

---

## 3. 功能需求（FR）

**FR-001 规则容器**：在 `MetaObject.rules` 中用现有 `MetaRule` 承载属性确定规则，五要素齐备：触发（`triggers`）/ 因子（`condition` 引用的字段）/ 条件（`condition` 表达式）/ 动作（`target_fields` + 取值）/ 次序与覆盖（`priority` + 覆盖策略）。

**FR-002 触发时机**：默认 `BEFORE_SAVE`（对应 C2「保存前内存改写」）；`ON_CHANGE` 为可选（前端联动实时带出，见 TBD-5）。

**FR-003 因子与条件**：`condition` 走 `SafeExpressionEvaluator` 语法；因子字段以字段 id 直接引用；支持跨对象因子（`build_cross_object_locals` 已具备）。`condition` 为空即无条件命中。

**FR-004 取值来源（Source）**，对标 EBS Source 四类：
`constant` 常量 / `field` 同对象字段 / `cross_object` 跨对象取字段 / `expression` 表达式（函数白名单内）。

**FR-005 次序与 tie-break（C4）**：按 `priority` 升序（数字小先）；逐条判定，**同一目标字段首个命中即停止**（first-match wins）；同 `priority` 必须有确定 tie-break（`rule.id` 字典序），禁止不确定顺序（对标 EBS 同序按字母序）。

> 现有 `RuleEngine._compute_by_priority` 是「全局排序 + 全部执行」，**DEFAULT 需新增专用分支** `default_by_priority`（分组 + 首个命中），不得复用 COMPUTATION 语义。

> **口径细化（实施后回填，2026-10-03）**：上述「首个命中即停止」在实施中细化为 —— **首个「条件命中**且实际写入成功**」的规则获胜**（`first rule that produces a value wins`，对标 EBS defaulting sequence），而非「首个条件为真即停」。理由：若首条规则条件为真、但因 `FILL_IF_EMPTY` 判定目标非空而被挡下就停止，会**反直觉地压死后续 `OVERRIDE` 规则**（组内更"敢写"的规则反而永远不生效）。故获胜判据 = `hit=True 且 value is not None`；其后的同组规则一律记 `skip_reason = "not_first_match"` 并跳过。分组维度实测为 `target_field`（不是 `scope`）；组内排序 `(priority, rule.id)` 全局稳定。
>
> **组内无获胜规则时**：进入再判定（FR-007），见其边界说明。

> **隔离护栏（E2E 实测补充，2026-10-03）**：`RuleEngine.execute_rules` 在按 trigger 取规则后**必须排除 `RuleType.DEFAULT`**。原因：DEFAULT 默认 `triggers=[BEFORE_SAVE]`，若不排除会被 `BEFORE_SAVE` 的 `execute_rules` **二次执行**，而该路径语义为「全局排序 + 全部执行」且 `change_source` 缺省 `both` —— 会误触发 `apply_on='system'` 的规则并覆盖 `apply_defaults` 已算出的值（E2E 实测：`price_list` 由 `PL_ZOR` 被改写为 `PL_SYS`，且日志与落库值不一致）。DEFAULT 只能经 `default_by_priority` / `apply_defaults` 执行。

**FR-006 覆盖语义（C3）**：每条规则显式声明覆盖策略：

- `FILL_IF_EMPTY`（默认）：目标字段为空才填（对标 D365 `Set Default Value`、Fusion 控件 `Is Blank`）
- `OVERRIDE`：无条件覆盖

另附来源开关 `apply_on = USER_INPUT | SYSTEM | BOTH`（对标 EBS System vs User Changes）。

**FR-007 再判定语义（C10）**：因子变化触发重判时，显式二选一：

- `RECOMPUTE_CLEAR`：重判；解析不出新值则清空原自动值
- `RECOMPUTE_KEEP`（默认）：重判；解析不出新值则**保留旧值**（对标 EBS 官方 “the old value would be retained instead of clearing”）

只清理由规则产生的值；用户手工输入值不被清理（需记录来源标记）。

> **一期边界（实施后回填，2026-10-03）**：实现为 `RuleEngine._apply_recompute` + `RuleContext.auto_filled_fields`（内存集合）。**一期明确限制：来源标记不跨请求持久化**（对应 TBD-3），故再判定仅对「**同一请求内的多次重判**」生效；跨请求（保存 → 后改因子 → 再保存）时 `auto_filled_fields` 为空，`RECOMPUTE_CLEAR` 不会清空历史自动值。`apply_defaults(...)` 已预留 `previously_auto_filled` 形参，二期接入持久化标记后即可生效，**调用方无需改动**。默认 `recompute="keep"`（对标 EBS 「未算出新值则保留旧值」），仅显式 `clear` 才清空。

**FR-008 展示派生 ≠ 写入默认（C6）**：读时计算不落库走 `enrichment_engine` / `computed`；落库走本 Spec 的 DEFAULT。同一字段不得混用，以 `computed` / `storage` 显式区分。

**FR-009 命令式逃生门（C8）**：保留 `RuleEngine.register_custom_validator` / `register_trigger_handler` 与 `MetaField.computation`；DEFAULT 只做声明式确定，复杂逻辑走代码，规则内可用 `custom` 引用。

**FR-010 可解释性 = 日志（C9，一期方案）**：保存时对每条参与判定的 DEFAULT 规则记一条日志：
`rule_id` / `seq`（排序后序号）/ `target_field` / `是否命中` / `未命中原因`（条件为假 / 被更小 seq 的同目标规则抢先）/ `带出的值` / `取值来源` / `覆盖判定结果`（`FILL_IF_EMPTY` 因目标非空而跳过）/ `耗时ms`。
日志结构按**可回放**设计（含因子值快照），二期 dry-run 复用同一份数据结构，零浪费。

> **实现口径（实施后回填，2026-10-03）**：日志载体为 `DefaultLogEntry`（`rule_executor.py`），字段落成为 `rule_id / rule_name / target_field / seq / priority / hit / skip_reason / value / source_type / overwritten / factor_snapshot / elapsed_ms`，带 `to_dict()`。**不并入 `RuleExecutionReport`**（T-13 口径调整）：`apply_defaults(...)` 直接**返回** `(data, logs)` 二元组，由 `ActionExecutor._log_default_rules` 逐条 `logging.info` 输出 —— 避免改动既有校验报告的语义与消费方。`skip_reason` 枚举实测为 `condition_false / target_not_empty / apply_on_mismatch / not_first_match / no_value`（`DefaultExecutor.SKIP_REASONS`）。

**FR-011 统一读取入口 `RuleProvider`**：新增 `meta/core/rule_provider.py`：

```python
class RuleProvider:
    def get_rules(self, meta_object) -> List[MetaRule]          # 原样返回（保序、不过滤）
    def get_enabled_rules(self, meta_object) -> List[MetaRule]  # 仅 enabled=True，保序
    def get_rules_by_type(self, meta_object, rule_type) -> List[MetaRule]
    def get_default_rules(self, meta_object) -> List[MetaRule]  # 仅属性确定类（T-06，P2 交付）
```

> **口径澄清（实施后回填）**：`get_rules` **原样返回**（保序、含未启用规则），与历史 `meta_obj.rules` 遍历行为严格等价——**禁止**在此加排序/过滤，否则会改变既有 9 处调用点行为。过滤能力另由 `get_enabled_rules` / `get_rules_by_type` 承担。`get_default_rules` 依赖 `RuleType.DEFAULT`，故推迟至 T-06（P2）交付。

将现散落 **9 处**直接遍历改为经 Provider（清单见实施计划 §2.3）；一期实现为**直读 `meta_obj.rules`（行为不变）**，委托 `MetaObject` 现有访问器；后期上线在线配置只需替换 Provider 实现（文件/DB/缓存），**调用方零改动**。

**FR-012 边界登记**：显式声明拆分/分摊（1→N，含守恒 `Σ行 = 头`）与反向汇总（N→1）**不属于**属性确定，不纳入本期语义；反向汇总能力平台**已具备**（`computation_service.count_children` + SUM/AVG/MAX/MIN），仅在文档口径上正名。

> **实施后回填（2026-10-03，边界不变）**：拆分/分摊已于**二期 M7** 落地，但以「**独立服务 + BO Action**」形式交付（`AllocationService` + `allocation.apply` / `allocation.split`），**仍未引入 `RuleType.ALLOCATION`、未改 `RULE_TYPE_MAP`** —— 本条的「不属于属性确定」边界**保持不变**（YAML 声明化 T-26 后置）。反向汇总的「**按父分组取值聚合**」已于 **M6** 落地；仍缺的是「**子行增删改 → 父行重算**」的自动触发。

---

## 4. 非功能需求（NFR）

- **NFR-001 性能**：单对象 DEFAULT 规则 ≤ 50 条时，保存链路判定增量 ≤ 50ms（不含跨对象取数）；跨对象取数须批量/缓存。
- **NFR-002 安全**：条件与表达式一律走 `SafeExpressionEvaluator` AST 白名单，禁止 `eval`。
- **NFR-003 可观测**：日志经现有 `logging` 输出（一期不建表）。
- **NFR-004 兼容**：Provider 一期透传，`meta_obj.rules` 既有读取行为零变化，存量测试全绿。
- **NFR-005 可测试**：每条 FR 有对应单测；提供 Provider 的 stub 实现供测试注入。
- **NFR-006 最小改动**：不新增表；新增文件 ≤ 3（`rule_provider.py` + 测试 + 可选执行器片段），优先在 `rule_executor.py` 内扩展。

---

## 5. 接口/集成需求（IF）

- **IF-001** `RuleProvider` 接口（见 FR-011）。
- **IF-002** `RuleEngine` 新增 `default_by_priority(meta_object, data, context)`；或新增 `DefaultExecutor` 注册进 `RuleExecutor`。
- **IF-003 执行链落点**：`action_executor.py` create/update 链路中，在 `compute(...)` 之后调用 DEFAULT 分支（现 `compute` 调用位于 L1528-1573、L1868-1908）。
- **IF-004 日志接口**：`RuleExecutionReport` 新增 `logs: List[DefaultLogEntry]`（新增键，不破坏现有 `to_dict` 字段）。
- **IF-005 与静态默认的关系**：`MetaField.default`（静态默认）优先级最低，在 DEFAULT 规则全未命中后才生效。

---

## 6. 过渡/迁移需求（TR）

- **TR-001** 存量对象无 DEFAULT 规则时，行为完全不变（天然灰度）。
- **TR-002** 9 处读取点切 Provider 分两步：① 引入 Provider 并透传（行为不变）→ ② 逐点替换。
- **TR-003** 后期上线在线配置时，Provider 实现切换 + 规则热加载；历史单据「读当前规则」还是「快照」另立 TBD-4（本期不做）。

---

## 7. 约束与假设

- **假设**规则规模小（每对象 ≤ 50 条），不值得引入索引/编译缓存。
- **假设**一期无在线配置需求，规则随元数据定义发布。
- **约束**不新增表；不改动 9 处读取点的对外行为。
- **约束**本期不支持「按当时规则复现历史单据」（需规则版本 + 生效期或因子快照，仅 SAP 靠 KONV 逐行落库做到）。
- **边界**拆分/分摊（二期）；反向汇总（已具备，仅口径正名）。

---

## 8. 优先级与里程碑

| 优先级 | 需求 |
|---|---|
| **P0** | FR-001 / 003 / 004 / 005 / 006 / 011（容器、条件、取值、次序、覆盖、读取入口） |
| **P1** | FR-002 / 007 / 009 / 010（触发、再判定、逃生门、日志） |
| **P2** | FR-008 / 012（展示区分、边界登记） |

- **M1** 语义与入口打通（P0）
- **M2** 可解释与再判定（P1）
- **M3** 文档收口 + 研究报告口径修正（P2）
- **二期** 拆分/分摊、dry-run、在线配置、规则版本化
  - **dry-run（M5）已落地 v1**：`dry_run_defaults` 复用同一条 `apply_defaults`（同排序 / 同首个命中 / 同覆盖语义 / 同 `change_source`），在浅拷贝上求值、零写库、零审计、不就地改写入参；返回 `{data, auto_filled_fields, logs}`。端点 `POST /api/v1/meta/<object_type>/defaults-preview`。
  - **汇总补强（M6）已落地**：按父外键分组的取值聚合（`_aggregate_field_by_parent` + `GROUP BY` 批量），复用既有 `comp_type`（不新增），未声明 `target_object` 时保持整表聚合。
  - **拆分/分摊（M7）已落地**：1→N 守恒（Σ子行 = 父行）—— `AllocationService`（最大余数法 + 回读守恒 + 事务回滚）+ 2 个 BO Action（`allocation.apply` / `allocation.split`）；`RuleType.ALLOCATION` + YAML 声明化后置。
  - **二期其余仍在队列**：集合确定、定价、在线配置 UI、规则版本化。
  - **注**：原计划「紧接着补校验」**已撤销** —— 代码级核实校验已具备（`MetaValidation` + `ValidationExecutor` + 保存链路可阻断），详见研究报告 §10.6 #6 [v1.11]。

> 里程碑的详细拆解（任务清单 + 验收标准）见 [实施计划](./2026-10-02-rule-model-implementation-plan.md)。

---

## 9. 变更设计方案（RFC）

### 9.1 As-Is

- `MetaRule` / `MetaComputation` / `MetaDerivation` 已存在；`RuleEngine.compute` = 全局排序 + **全部执行**；`DERIVATION` 走 `DerivationExecutor`（聚合/转换/过滤/富化，跨对象）。
- 规则读取散落 **9 处**直接遍历 `meta_obj.rules`。
- **无 DEFAULT 语义**：无「仅空值填」、无「首个命中」、无覆盖开关、无再判定清空/保留策略、无执行日志。
- `MetaField.default` 仅静态默认值。

### 9.2 Target

- 新增 `RuleType.DEFAULT` + `MetaDefaultRule`（**已定：方案 A**，见 9.4）。
- `RuleProvider` 统一读取（9 处收口）。
- `RuleEngine` 新增 `default_by_priority`（分组 + 首个命中）。
- 执行日志（可回放结构）。

### 9.3 详细设计

- **载体**：`MetaDefaultRule(MetaRule)`，字段：`overwrite` / `apply_on` / `on_recompute` / `source_type` / `source_ref` / `priority`；默认 `triggers = [BEFORE_SAVE]`。
- **取值来源映射**：`constant` 直接赋值；`field` → `context.get_field_value`；`cross_object` → `build_cross_object_locals`；`expression` → `SafeExpressionEvaluator`。
- **排序**：`priority` asc，其次 `rule.id` asc。
- **覆盖**：目标值空判定（`None`/`""`）；`OVERRIDE` 直接 `set_field_value`。
- **来源标记**：`RuleContext` 增 `auto_filled: Dict[field, rule_id]`，供 FR-007 只清自动值。
- **集成点**：`action_executor.py` create/update。

> **字段名回填（实施后回填，2026-10-03）**：实际字段名为 **`source_type` / `source_value` / `apply_mode`（`fill_if_empty`|`override`）/ `apply_on`（`user_input`|`system`|`both`）/ `recompute`（`keep`|`clear`）** —— 与本节草案名 `overwrite` / `on_recompute` / `source_ref` 有意不同：`apply_mode` 比 `overwrite` 更中性（默认 `fill_if_empty` 并非"覆盖"），`recompute` 独立成字段以对齐 C10「清空 or 保留」。其它落点差异：来源标记落为 `RuleContext.auto_filled_fields`（`set`，非 `Dict[field, rule_id]`）；集成点为 `action_executor._do_create` / `_do_update`，在 `BEFORE_SAVE` **校验之前**调用 `apply_defaults`；`MetaDefaultRule.target_field` 为只读属性（取 `target_fields[0]`），即分组键。

### 9.4 备选方案（TBD-1 已定：A）

| 方案 | 做法 | 优点 | 代价 |
|---|---|---|---|
| **A（已采纳）** | 新增 `RuleType.DEFAULT` | 语义显式、可解释性最好 | 枚举新增；已核查爆炸半径 = 5 个 Python 点，前端零改动 |
| B | 复用 `DERIVATION` + `custom` | 零枚举改动、最小 | 语义藏在 `custom`，可发现性差 |
| C | 新增 `MetaDefaultRule` 子类（不改枚举） | 结构正 | 枚举与类语义不一致，理解成本高 |

### 9.5 实施与迁移步骤

1. 新增 `meta/core/rule_provider.py`（直读实现 + 单测）
2. 9 处读取点改走 Provider（透传，行为不变）
3. 新增 `RuleType.DEFAULT` + `MetaDefaultRule`（含 `yaml_loader` 映射）
4. `RuleEngine` 新增 `default_by_priority` + `DefaultLogEntry`
5. `action_executor` 集成
6. 日志输出
7. 修正研究报告 4 处口径（§1 / §8.2 落点 / §8.10 汇总 / §8.3 补 `priority`）

### 9.6 测试

- **单测**：Provider 透传一致性（9 处调用点回归）；`priority` + 首个命中；tie-break；`FILL_IF_EMPTY` vs `OVERRIDE`；`apply_on`；再判定 `CLEAR`/`KEEP`；日志字段完整性；危险表达式被 `SafeExpressionEvaluator` 拒绝。
- **集成**：经 `action_executor` 保存对象，验证落库值与日志；存量测试全绿（按项目铁律用 `python d:\filework\test.py`，禁止直接 pytest）。
- **E2E**：本期无 UI 变更，不强制；若纳入 `ON_CHANGE` 前端联动则补 E2E。

### 9.7 回滚

- Provider 透传可回退为直读（单点开关）。
- DEFAULT 规则经 `enabled=false` 或删除即失效，不影响存量数据。
- **无 schema 变更 → 无数据迁移回滚**。

---

## 10. TBD 清单

| 编号 | 待定项 | 状态 |
|---|---|---|
| **TBD-1** | 载体选型：A / B / C | **已定：A（新增 `RuleType.DEFAULT`）** |
| TBD-2 | 日志是否落库（一期仅 logging，二期如需查询再评） | 待定 |
| TBD-3 | 「自动值」来源标记是否需持久化隐藏字段，或仅内存 + 日志 | 待定 |
| TBD-4 | 在线配置形态（文件/DB）+ 历史单据复现策略 | 待定（二期） |
| TBD-5 | `ON_CHANGE` 前端联动是否纳入一期 | 待定 |
| TBD-6 | 因子值快照是否入日志（影响日志体积） | 待定（本期按「仅 condition 引用字段」入日志） |

---

## CHANGELOG

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-02 | v1.0 | 初版：由 spec-rfc 流程产出，含 10 节（Background → TBD List）；TBD-1 定为方案 A |
| 2026-10-03 | v1.1 | **实施后回填 5 处口径**（代码级核实，不改需求边界）：① FR-005 增「首个命中」细化 —— 获胜判据为「**条件命中且实际写入成功**」（首个能产出值的规则），分组维度实测 `target_field`；② FR-007 增一期边界 —— 来源标记 `auto_filled_fields` **不跨请求持久化**（TBD-3），`RECOMPUTE_CLEAR` 仅对同一请求内多次重判生效，`previously_auto_filled` 形参已预留；③ FR-010 增实现口径 —— 日志载体 `DefaultLogEntry`，**不并入 `RuleExecutionReport`**（T-13），经 `apply_defaults` 返回值 + `_log_default_rules` 输出，`skip_reason` 五枚举实测值；④ §9.3 增字段名回填 —— 实为 `source_value` / `apply_mode` / `recompute`（草案名 `overwrite` / `on_recompute` / `source_ref`）及来源标记为 `set`；⑤ FR-011 前次已回填（`get_rules` 原样返回） |
| 2026-10-03 | v1.2 | **二期开工（N2 部分落地）**：§8 二期行拆分 —— dry-run 已落地 v1（`dry_run_defaults` + `POST /api/v1/meta/<object_type>/defaults-preview`，浅拷贝 / 零写库 / 零审计），其余（拆分·分摊、集合确定、汇总补强、定价、在线配置、规则版本化）仍在队列；N2 同步标注「范围为守卫段以内的 DEFAULT 规则链」；撤销「紧接着补校验」（已核实具备）。实现细节见实施计划 M5 |
| 2026-10-03 | v1.3 | **二期·汇总补强(M6) + 拆分/分摊(M7) 落地回填**：§8 二期行新增 M6（按父分组取值聚合）/M7（1→N 守恒 + 2 个 BO Action）已落地说明，并从「仍在队列」移除这两项；FR-012 追加实施回填 —— 拆分/分摊**仍以独立服务 + BO Action 交付、未引入 `RuleType.ALLOCATION`、边界不变**，反向汇总的「按父分组取值聚合」M6 已落地、仍缺「子行增删改 → 父行重算」。实现细节见实施计划 M6 / M7 |
