# 规则编排专题：顺序、链式传播与跨对象级联

> **版本**：v1.6 | **日期**：2026-10-03 | **状态**：研究稿 + 方案（P0/P0.5 已执行；G9/G10/G11 已修；D7 tie-break 已统一；P1 顺序唯一入口已落地；G3/G1 已修；**二次检查完成，P2~P6 及加固项已登记待办，见 §4.1**）
> **关联文档**：
> - [2026-10-03-rule-model-consumption-and-layering.md](./2026-10-03-rule-model-consumption-and-layering.md)（v2.1，消费侧模型与分层归属；本专题是其延伸）
> - [2026-10-02-rule-model-research.md](./2026-10-02-rule-model-research.md)（规则内容/生产侧）
> - [2026-10-02-rule-model-spec.md](./2026-10-02-rule-model-spec.md)（Spec + RFC）
>
> **本文回答**：用户追问——"determination 有顺序吗？A 变导致 B 变、B 再导致 C 变，这个编排执行逻辑是否已考虑？"
> **结论先行**：机制**已建成但接线不全**——拓扑链只挂在 `compute()` 一个入口，跨对象级联未接线，`depends_on` 是死字段。头部产品在这一点上的共性做法可作为我们的收口依据。

---

## 1. 我方现状（代码级取证）

### 1.1 真实执行序列（以 update 为例）

```
一次 update 的真实序列（action_executor.py#L1960-L2008）
 ├─ execute_rules(BEFORE_UPDATE) → 平铺 sorted(priority)
 ├─ apply_defaults(BEFORE_SAVE)  → DEFAULT 专用链（分组 + 首个命中获胜）
 ├─ execute_rules(BEFORE_SAVE)   → 平铺 sorted(priority)   ← 校验在这里跑
 ├─ compute(...)                 → 拓扑链                  ← ★ 唯一走编排的入口
 ├─ ── 写库 ──
 └─ execute_rules(AFTER_SAVE)    → 平铺 sorted(priority)
```

### 1.2 已有的编排机制（可复用，不必重造）

| 能力 | 位置 | 说明 |
|---|---|---|
| 依赖图构建 | [rule_chain.py#L196-L238](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L196-L238) | 节点 = 规则；边由「字段数据流」推断 |
| 建边规则 | [rule_chain.py#L299-L334](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L299-L334) | `target_field ↔ source_fields`，另加 computation→validation/state 边 |
| 环检测 | [rule_chain.py#L336-L372](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L336-L372) | DFS 三色；**有环则抛 ValueError** |
| 拓扑排序 | [rule_chain.py#L374-L423](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L374-L423) | 类型权重（COMPUTATION 10 < DERIVATION 15 < CONSTRAINT 20 < VALIDATION 30 < STATE 40 < TRIGGER 50）+ priority tie-break |
| 增量取规则 | [rule_chain.py#L458-L482](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L458-L482) | `changed_fields` → 规则 → 下游闭包 |
| 传播循环 | [rule_chain.py#L484-L545](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L484-L545) | `while ... and depth < MAX_PROPAGATION_DEPTH(100)`；值真变 → 下游入队 |
| 平铺执行 | [rule_executor.py#L1283-L1300](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1283-L1300) | `sorted(rules, key=priority)`，首个 ERROR 即 break |
| 链入口 | [rule_executor.py#L1341-L1380](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1341-L1380) | `compute()`；异常时**降级回 priority 顺序** |

### 1.3 十一项结构性缺口

| # | 缺口 | 证据 | 严重度 |
|---|---|---|---|
| G1 | `MetaRule.depends_on` 是**死字段** | 声明于 [models.py#L164](file:///d:/filework/excel-to-diagram/meta/core/models.py#L164)（注释"依赖的其他规则"），全仓 `.depends_on` 读取 **0 处** → 依赖纯靠隐式推断 | 中 → **✅ 已修（v1.5）** |
| G2 | **两套顺序并存**：拓扑链只在 `compute()` 生效，其余入口平铺 priority | [rule_executor.py#L1291](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1291) vs [#L1341](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1341) | **高 → ✅ 已修（P1，v1.4）** |
| G3 | `compute()` **丢弃链的校验结论**：只取 `data`/`changes`，不读 `success`/`errors` | [rule_executor.py#L1365-L1373](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1365-L1373) | **高 → ✅ 已修（v1.5）** |
| G4 | 环检测在运行期**静默降级**为 priority 顺序，仅 `logger.warning` | [rule_executor.py#L1374-L1376](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1374-L1376) | **高** |
| G5 | **跨对象链零接线**：`CrossObjectRuleChainExecutor` 全仓无生产调用 | [cross_object_chain.py#L116](file:///d:/filework/excel-to-diagram/meta/core/cross_object_chain.py#L116) | **高** |
| G6 | 聚合派生**只 SELECT 不回写**目标对象 → A→B→C 断链 | [rule_executor.py#L1095-L1145](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1095-L1145) | **高** |
| G7 | 链内 DERIVATION 是 **stub**（只产出 `status: 'pending'` 描述，不落库） | [rule_chain.py#L776-L847](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L776-L847) | 中 |
| G8 | 求值内核**分裂**：优先第三方 `simple_eval.EvalWithCompoundTypes`，缺失才回落 `safe_evaluate` | [rule_chain.py#L881-L899](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L881-L899) vs SSOT §2.5 认定的唯一内核 | 中 |
| **G9** | **环检测对状态机大规模误报**：`STATE_TRANSITION` 的 `source_fields` 与 `target_fields` 同为 `state_field`，导致同一状态字段上的两条规则**必然互相成环**（不区分 `from_states` 是否互斥） | `_create_node` [rule_chain.py#L251-L259](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L251-L259) + `_build_edges` [#L303-L313](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L303-L313) | **高（P0 实证）→ ✅ 已修（v1.2）** |
| **G10** | `topological_sort` 遇环**静默返回不完整序列**（Kahn 算法丢弃所有入度非零节点），不抛错、不告警 | [rule_chain.py#L386-L423](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L386-L423) | 中（P0 实证）→ ✅ 已修（v1.2） |
| **G11** | **链内状态迁移缺 gating**：`_execute_state_transition` 无条件按 `from_states` 写入 `to_state`，且 `triggered_rules` 会把同字段的互斥兄弟拉进传播循环 → 同一批次内**互斥兄弟互相覆盖**，请求的状态被静默回滚（flat 侧 `StateTransitionExecutor` 的 Case 0/1/1.5/2 gating 在链内**不存在**） | [rule_chain.py#L651-L691](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L651-L691) vs [rule_executor.py#L904-L956](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L904-L956) | **高（P0 复测实证，当前不可达）→ ✅ 已修（v1.3）** |

**"空转"事实**：全仓 `*.yaml` 中 `type: computation` / `derivation` / `trigger` 的**规则声明为 0**（[version.yaml#L538](file:///d:/filework/excel-to-diagram/meta/schemas/version.yaml#L538) 的 `type: trigger` 是 action effect，非规则）。现有 `rules:` 段几乎全是 `state_transition`（[version.yaml#L592](file:///d:/filework/excel-to-diagram/meta/schemas/version.yaml#L592)、[product.yaml#L539](file:///d:/filework/excel-to-diagram/meta/schemas/product.yaml#L539) 各 2 条），加本轮迁入的 1 条 `validation`（relationship）。→ **机器造好了，几乎没有规则喂给它跑**，这是 G2~G7 长期未被发现的原因。

### 1.4 P0 实测结果（已执行，只读）

审计脚本：[.trae/scripts/audit_rule_orchestration.py](file:///d:/filework/excel-to-diagram/.trae/scripts/audit_rule_orchestration.py)
命令：`python .trae/scripts/audit_rule_orchestration.py`

**覆盖面**：51 个对象（`meta/schemas` + `apps/{hello_world,tms,warehouse}/schemas`），**其中有规则的仅 8 个**；**未建图规则 0 个**（所有规则的 `rule_type` 都有对应节点，链对它们不"隐形"）。

**Q1 环扫描 → 7 个对象报环，且全部是状态机误报（G9 实证）**

| 对象 | 报出的环路径（原样） | 真实语义 |
|---|---|---|
| product | `activate_product → deactivate_product → activate_product` | `is_active` 上的一对互斥迁移 |
| version | `set_current_version → unset_current_version → set_current_version` | `is_current` 上的互斥对 |
| user | `lock_user → freeze_user → lock_user` | 状态字段上的互斥对 |
| permission_set | `enable_permission_set → disable_permission_set → enable_permission_set` | 同上 |
| change_subscription | `enable_subscription → disable_subscription → enable_subscription` | 同上 |
| change_event | `fail_event → deliver_event → fail_event` | 同上 |
| audit_log | `mark_written → mark_failed → mark_written` | 同上 |

> **这 7 条都不是真环**：状态字段在一次保存里只可能取一个值，`should_execute` 又要求 `current_state in rule.from_states`，两条互斥规则**不可能同时命中**。报环纯属"`state_field` 既是 source 又是 target"的建图副作用。

**Q2 两套顺序差异 → 8 处，但实质是同一个病根**

- 上述 **7 个对象**（audit_log / change_event / change_subscription / permission_set / product / user / version，全部是 `before_update`）在拓扑侧返回 **`topo: []`**——不是"顺序不同"，而是 **Kahn 算法把成环节点全部丢弃，拓扑序列为空**（G10 实证）。
- 唯一"健康"的对象是 **relationship**：`before_save` 上 flat == topo == `[source_not_equal_target]`，但该规则**同时出现在平铺与链两条路径** → **真实重复覆盖 1 处**（幂等，当前无功能危害）。

**结论（对方案的影响）**：

1. **原 P2"环=加载期硬失败"若直接上，会拒掉 8 个有规则对象中的 7 个** —— 即直接搞挂平台。必须先修 G9 的建图口径，硬门禁才有意义。
2. **拓扑链当前只在 1 个对象（relationship）上可用**，且在它身上重复执行 1 条校验。其余 7 个对象每次 `compute()` 都走 [静默降级分支](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1374-L1376)。
3. 因此 **P2 的正确顺序是：先修 G9（建图口径）+ G10（拓扑排序必须报错），再谈硬门禁**。

### 1.5 G9 / G10 修复实施与复测（v1.2）

**改动**（2 处，均在 `meta/core/rule_chain.py`）：

| 缺口 | 口径 | 改法 |
|---|---|---|
| **G9** | 采纳 D6 建议：**状态迁移之间不成边** | `_build_edges` 通用建边循环内加一道判定——当 `node` 与目标节点**同为 `STATE_TRANSITION`** 时 `continue`。保留 `computation → state_transition` 的 `CONDITION_DEPENDENCY` 边（那是真依赖：先算出状态值，再做迁移准入） |
| **G10** | 拓扑排序遇环**必须报错** | `topological_sort` 末尾校验 `len(result) != len(graph.nodes)` → 抛 `ValueError` 并列出无法定序的规则 id（原实现静默丢弃成环节点） |

**复测（同一脚本，修后重跑）**：

| 指标 | 修前 | 修后 |
|---|---|---|
| 报环对象 | 7 | **0** |
| 拓扑排序报错 | —（静默返回 `[]`） | **0** |
| 拓扑序列为空的对象 | 7 | **0** |
| 顺序差异 | 8 处 | 8 处，但**性质已变**：全部是「同层平局 tie-break 口径」差异（见下） |
| 真实重复覆盖 | 1（relationship / before_save） | **1（未变）** |

**运行时验证（只读探针）**：

1. `ImplicitRuleChainExecutor(product)` 修复前抛 `ValueError`（误报环），修复后正常构造，`get_execution_order()` = `['activate_product', 'deactivate_product']`。
2. `RuleEngine.compute(product, data={'is_active': True}, original_data={'is_active': False})` 返回 `is_active=True`（**未被链改写**）→ 确认 G9 修复**对存量行为中性**：`compute()` 现走链路径，但链只执行 `before_save` 触发的规则，而 schema 里的状态迁移全是 `before_update`，故实际不执行任何规则，与旧的"降级执行 COMPUTATION"等价（这些对象本就无 COMPUTATION 规则）。
3. 相关单测回归：`test_rule_chain`(5) / `test_rule_engine` / `test_rule_provider_unit` / `test_rule_validations_migration` / `test_derivation` 全部通过。

**修后仍存的 8 处顺序差异 = 平局 tie-break 口径不一致（新增 D7）**

- `flat`（`execute_rules`）用 `sorted(key=priority)`，**稳定排序** → 同优先级的相对次序 = **YAML 声明顺序**。
- `topo`（`topological_sort`）用 `(类型权重, priority, rule.id)` 元组排序 → 同优先级时退化为 **rule.id 字典序**。

实测对照（同层同优先级下）：

| 对象 | flat（声明序） | topo（id 序） |
|---|---|---|
| user | `[activate_user, deactivate_user, lock_user, unlock_user, freeze_user, unfreeze_user]` | `[activate_user, deactivate_user, freeze_user, lock_user, unfreeze_user, unlock_user]` |
| change_event | `[process_event, deliver_event, fail_event, retry_event]` | `[deliver_event, fail_event, process_event, retry_event]` |
| audit_log | `[mark_written, mark_failed, retry_write]` | `[mark_failed, mark_written, retry_write]` |
| product / version / relationship | 与 topo 一致 | 与 flat 一致 |

> 这些差异**当前无语义危害**——同一状态字段上的迁移互斥，任一时刻只有一条命中；但 **P1 顺序收口时必须先统一 tie-break 口径**（建议：同优先级取「声明顺序」，与 flat 对齐，避免"收口即改序"）。

**⚠️ P1 的关键前置：G11（新发现，已实证）**

修 G9 之后链对 7 个对象**变得可用**，于是暴露出一条此前被"环误报"掩盖的隐患：**链内 `_execute_state_transition` 没有 flat 侧的 gating**。实测（只读探针，构造 `trigger=BEFORE_UPDATE`）：

```
execute(product, data={'is_active': True}, original_data={'is_active': False}, trigger=BEFORE_UPDATE)
→ 执行序 ['activate_product', 'deactivate_product']
→ 最终 is_active = False      ← 请求的 True 被静默回滚
```

原因：同一批次内 `activate_product` 写入 `True`，随后 `deactivate_product` 读**实时值** `True ∈ from_states=[true]` 便把它写回 `False`；且 `triggered_rules` 还会把互斥兄弟再次拉进传播循环。

**当前不可达**（`compute()` 只以 `BEFORE_SAVE` 调链，而 schema 里状态迁移全是 `before_update`），所以**本次修复不改变任何存量行为**。但这意味着：

> **P1「`execute_rules_ordered` 成为唯一入口」之前，必须先修 G11**，否则顺序收口的第一步就会让 `before_update` 的状态迁移走进无 gating 的链实现，**用户点击"激活"会被静默回滚为"停用"**。

### 1.6 D7 / G11 修复实施与复测（v1.3）

**改动（2 处代码 + 1 处审计脚本口径修正）**

| 项 | 口径 | 改法 |
|---|---|---|
| **D7** | tie-break 统一为**声明顺序**（用户已拍板） | `RuleNode` 新增 `declaration_index`（`analyze` 按 `get_rules` 的保序枚举赋值）；`topological_sort` 排序键由 `(类型权重, priority, rule.id)` 改为 `(类型权重, priority, declaration_index)` |
| **G11** | 链内状态迁移**补齐 flat 侧 gating** | ① `RuleNode.should_execute` 取消 STATE_TRANSITION 的「live 值 ∈ from_states」预筛——该预筛与 flat 准入模型不同，会挡掉显式 action 却放过 form 回提交；② `_execute_state_transition` 内按 flat 的 Case 0/1/1.5/2/3 + `condition` 逐条判定；③ `triggered_rules` 排除同 `state_field` 的互斥兄弟（新增 `_is_sibling_state_transition`） |
| 审计脚本 | 「顺序差异」计数口径修正 | 原先把「两路都会跑（overlap）」也计入差异，致 D7 后计数虚高；现拆为「顺序差异」与「两路重叠」两项独立上报 |

**复测（同一脚本）**

| 指标 | 修前 | 修后 |
|---|---|---|
| 报环对象 | 0 | 0 |
| 拓扑排序报错 | 0 | 0 |
| **顺序差异** | 8 处 | **0 处** |
| 两路重叠（P1 收口后需消除） | 8 处 | 8 处（未变） |
| 真实重复覆盖 | 1（relationship / before_save） | 1（未变） |

**G11 行为对照（只读探针，product / `before_update`）**

| 用例 | chain（修前） | chain（修后） | flat |
|---|---|---|---|
| 显式 activate（data=True, orig=False） | **False（被静默回滚）** | **True** | True |
| 显式 deactivate（data=False, orig=True） | False | False | False |
| form 回提交当前值（True/True） | True | True | True |
| data 中无 state 字段 | None | None | None |

→ 修后链与 flat **四种情形全部一致**。单测回归：`test_rule_chain`(5) / `test_rule_engine`(9) / `test_rule_provider_unit`(9) / `test_rule_validations_migration`(4) / `test_derivation`(6) 全绿。

**⚠️ P1 落地分级（本轮实测新增的阻塞项）**

P1 不是「换入口」而是**语义变更**。直接切唯一入口会引入下列回归，须先逐项处置（并先跑影子模式，见 D2）：

1. 链内 `TRIGGER` 是 stub（只产出 `executed=True`，**不分发 handler**）；flat `TriggerExecutor` 会真正调用已注册的 `_handlers`。
2. 链内 `DERIVATION` 是 stub（只产出 `status: pending`，**不写库**）；flat `DerivationExecutor` 会真正聚合并写回（即 G6 的修法）。
3. 链内状态迁移**不写 `{state_field}_entered_at`**（flat 会写）。
4. **执行集合不同**：flat 跑「该 trigger 下全部规则」；链先按 `changed_fields` 求「受影响规则集」再按 trigger 过滤 → 跨字段校验会被漏跑。
5. 返回类型不同：`RuleChainResult` vs `RuleExecutionReport`（后者承载 `success`/`errors` 的阻断语义）。
6. 链有**传播循环**（同规则可被多轮触发）；flat 是单趟按 priority 跑完即止。
7. `_filter_by_trigger` **只作用于初始集合**，传播出来的规则未再按 trigger 过滤。

> **⚠️ 上述 7 项仅在「把链 executor 当作唯一执行体」时才成立** —— 见 §1.7 的落地方式（链**只用来取顺序**，执行体仍是 flat 执行器），故本批实现下**全部失效**。

### 1.7 P1 顺序唯一入口实施与复测（v1.4，用户拍板「直接切」）

**落地方式**：不新造入口、不改任何调用点，把排序**做进既有唯一入口**
[`RuleEngine.execute_rules`](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1264-L1300)
（`action_executor.py` 的 BEFORE_UPDATE / BEFORE_SAVE / AFTER_SAVE 共 4 处调用 + `compute()` 全走这里），
新增私有方法 `_order_rules_by_dependency`：

- 图内规则：按 `RuleDependencyAnalyzer.topological_sort` 的次序（依赖在前）；
- 图外规则（分析器未建档的类型，如 `PERMISSION`）：保持原 `priority` 稳定序，追加在末尾；
- 分析器报环（`ValueError`）时**回退**到原 `priority` 顺序并 `logger.warning`，避免一次保存因某个与本次触发无关的环而整体失败。

**关键点：执行体不变**。仍复用既有的 flat 各类型执行器（`ValidationExecutor` / `ComputationExecutor` /
`StateTransitionExecutor` / `TriggerExecutor` / `DerivationExecutor`），
**只改「顺序」**；因此 `RuleExecutionReport` 语义（首个 ERROR 即 break）、`{state_field}_entered_at`
写入、触发器真分发 handler、派生真写库等**全部维持原样**。

**§1.6 的 7 项阻塞在本实现下的状态**

| §1.6 阻塞 | 本实现下的状态 |
|---|---|
| 1 链内 TRIGGER 是 stub（不分发 handler） | **失效**——仍由 flat `TriggerExecutor` 执行 |
| 2 链内 DERIVATION 是 stub（不写库） | **失效**——仍由 flat `DerivationExecutor` 执行 |
| 3 链不写 `{state_field}_entered_at` | **失效**——`StateTransitionExecutor` 照旧写 |
| 4 执行集合差异（跨字段校验被漏跑） | **失效**——flat 跑该 trigger 下**全部**规则，不按 `changed_fields` 求子集 |
| 5 返回类型不同（`RuleChainResult` vs `RuleExecutionReport`） | **失效**——调用方仍拿 `RuleExecutionReport` |
| 6 链有传播循环（多轮） | **失效**——单趟执行，无多轮传播 |
| 7 `_filter_by_trigger` 只作用初始集合 | **失效**——trigger 过滤仍是 `get_rules_by_trigger`，行为未变 |

**审计复测（[audit_rule_orchestration.py](file:///d:/filework/excel-to-diagram/.trae/scripts/audit_rule_orchestration.py)）**：
环 0 / 拓扑报错 0 / **顺序差异 0** / 未建图规则 0 —— 对存量 8 个有规则对象，新口径与旧 flat priority 顺序**完全一致**（行为中性）。

**新增回归测试**：
[`test_rule_engine.py::test_rule_engine_cross_field_validation_order`](file:///d:/filework/excel-to-diagram/meta/tests/test_rule_engine.py#L500-L560)
—— 只改 `price`，依赖序保证 `calc_total` 先于 `total_consistent` 执行；校验的 `priority` 故意设为更小（10 < 100），
若仍按 priority 平铺则校验先跑、读到过期 `total` 而失败。该用例通过 → **证明顺序确由依赖决定**。

**本批未做（留后续）**：G3（`compute()` 丢弃链的校验 `success`/`errors`）、G1（`depends_on` 仍是死字段）、
`compute()` 与 `execute_rules(BEFORE_SAVE)` 对 `relationship / before_save` 仍会重复执行一次（属既有行为，非本次引入）。

**旁证（既有失败，与本改动无关）**：`tests/test_rule_engine_layer.py` 3 个用例（`test_business_key_validation` /
`test_unique_constraint` / `test_error_severity_stops_operation`）在**改动前后同样失败**，根因是测试数据
`version_id=1` 在库中无对应行 → `FOREIGN KEY constraint failed`；已用"临时回退排序口径"的对照实验确认。

**规则相关单测复测**：`test_rule_chain`(5) / `test_rule_engine`(10，含新增) / `test_rule_provider_unit`(9) /
`test_rule_validations_migration`(4) / `test_derivation`(6) 全绿。

### 1.8 G3 与 G1 的修复（v1.5）

**G3（`compute()` 丢弃链的校验结论）——用「移除冗余引擎」根治，而不是「把结论上抛」**

排查发现关键事实：链内 [`_execute_validation`](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L779-L810) 以 **`condition` 当判定**；
而平铺 [`ValidationExecutor`](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L624-L659) 以 **`action` 当判定**、`condition` 仅作"是否适用"的门。
真实 YAML 校验（如 `relationship/source_not_equal_target`）以 `rule:` → `action` 表达判定、`condition` 为空。因此：

- 链内校验结论**本身就不可信**（空 `condition` 恒真 → 从不报错；`condition` 被误当判定 → 误报）；
- 若按原方案「把链结论上抛」，反而会**误阻断**合法保存。

故正确解法是**让 `compute()` 不再运行第二个引擎**：

- [`compute()`](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1372-L1395) 移除 `ImplicitRuleChainExecutor` 调用，只执行**计算规则**；顺序复用 `_order_rules_by_dependency`（与 `execute_rules` 同一口径）。
- 随之删除已无用途的 `use_chain` / `changed_fields` 形参（全仓无调用方使用）。
- **校验仍由 `execute_rules(BEFORE_SAVE)` 按 `action` 口径统一执行并阻断**，职责不再重叠。
- 副产品：生产路径上「同一 trigger 被平铺与链各跑一次」的**重复执行被消除**；审计中的「两路重叠 / 真实重复覆盖」自此成为设计探针（仅当链被重新接回执行路径时需重估，脚本已就地注解）。
- 回归：[test_rule_engine.py::test_compute_only_computes_and_ignores_validation](file:///d:/filework/excel-to-diagram/meta/tests/test_rule_engine.py#L563-L619)。

**G1（`depends_on` 死字段）**：取「甲」（启用显式依赖边、且优先于推断边），实施细节见 §3.3。

**复测**：`test_rule_chain`(6，含新增) / `test_rule_engine`(11，含新增) / `test_rule_provider_unit`(9) /
`test_rule_validations_migration`(4) / `test_derivation`(6) 全绿；审计复测**环 0 / 拓扑报错 0 / 顺序差异 0 / 未建图规则 0**
（存量行为中性）。`tests/test_rule_engine_layer.py` 仍是同一批既有 `FOREIGN KEY` 数据失败（3 个），与本批无关。

---

## 2. 头部产品对标（四维）

### 2.1 对标矩阵

| 产品 | ① 顺序表达 | ② 链式传播 | ③ 环/无限递归防护 | ④ 跨对象 / 事务边界 |
|---|---|---|---|---|
| **SAP** | 定价过程按**步骤号**顺序；条件类型经**访问顺序**（最具体→最一般）取值 | 步骤间以小计（subtotal）传递；更新模块 `IN UPDATE TASK` + `COMMIT WORK` 统一执行 | 未确证 | **V1 同步**（失败整体回滚）/ **V2 异步**（失败不回滚、仅留日志，SM13 查看） |
| **Oracle Fusion OM** | 编排流程定义的 **step 列表**，step 带 **dependencies**、分支、退出条件 | 按 step 自动推进（schedule→reserve→ship→invoice） | 未确证 | **compensation 补偿**（有 delta 时 hold 当前任务、重跑受影响 step）；savepoint 回滚；耗时活动 **deferred 到 background engine** |
| **Salesforce** | 官方 **Order of Execution**（硬编码序号流水线） | 同事务内按序号推进；workflow 字段更新会**再触发一次** before/after update | **递归保存时跳过步骤 9–17**（官方）；实践用静态变量作 guard | **单次 save 同一事务**，末端统一提交；跨对象更新同事务级联 |
| **Dataverse / D365** | **插件管道阶段**（PreValidation 10 / PreOperation 20 / PostOperation 40）+ **Execution Order** 数字升序 | 同步插件在管道内顺序执行并级联 | **`depth` 属性**判定递归深度；可抛"infinite loop"取消执行 | PreValidation 在主事务外；Pre/PostOperation 在扩展事务内；**异步插件在事务外** |
| **ServiceNow** | Business Rules 的 **`order` 字段**（100/200…）+ When 分类（before/after/async/display） | after 规则更新关联记录，**同步**传播；async 后台并发 | 未确证（社区指出 after 中 `current.update()` 会重触发，可能无限循环） | before/after 同步；**async 提交后由调度器运行**；before 可 `setAbortAction` 阻止落库 |
| **Pega** | **Rule Resolution** 算法（Apply-to 类 + 规则集栈 + 类继承 + circumstances），首个匹配获胜 | **Forward chaining（前向链）**：解析 Declare Expression/OnChange，**计算依赖顺序后执行**；Report Definition 走反向链 | 未确证（可见约束：前向链**仅跟踪主页面**属性） | 声明式网络在同一流程内**同步**传播；无异步/补偿（未确证） |
| **Camunda / DMN** | **DRG/DRD** 用 `required decision` 表达依赖决定求值顺序；表内用 **hit policy** 解决冲突 | 被依赖 decision **自动递归先算**，同步 | 图结构应无环；环检测官方行为未确证 | 纯求值，无事务/补偿语义 |
| **Drools** | **Agenda** 排序，默认 **Salience + LIFO**；另有 activation-group / agenda-group / ruleflow-group | **Rete 前向推理 + 真值维护（TMS）**：`insertLogical()` 条件不成立时**自动 retract** | **`no-loop`**（阻自身后果重激活）、**`lock-on-active`**（组激活期内更强制） | stateful session 保留事实；逻辑插入提供自动撤销语义 |

**来源**（均为子代理实际抓取/搜索所得；官方域名检索受限处已标"未确证"）：
- Salesforce：[Triggers and Order of Execution](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_triggers_order_of_execution.htm)、[Record-Triggered Automation](https://architect.salesforce.com/docs/architect/decision-guides/guide/record-triggered)
- Dataverse：[Register a plug-in](https://learn.microsoft.com/fil-ph/power-apps/developer/data-platform/register-plug-in)、[Plug-in execution context](https://learn.microsoft.com/en-ca/training/modules/extend-plug-ins/execution/)、[Troubleshoot plug-ins](https://learn.microsoft.com/en-us/troubleshoot/power-platform/dataverse/plug-in-execution/dataverse-plug-ins-errors)
- ServiceNow：[Scripts and engines execution order](https://www.servicenow.com/docs/r/australia/build-workflows/approvals/execution-order-scripts-engines.html)
- Oracle：[Orchestration Process Steps](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25c/faiom/guidelines-for-setting-up-orchestration-process-steps.html)、[Managing Change（compensation）](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faiom/overview-of-managing-change-that-occurs-during-order-fulfillment.html)、[Workflow Engine APIs（savepoint/deferred）](https://docs.oracle.com/cd/E26401_01/doc.122/e22009/T341351T341380.htm)
- Pega：[Rule resolution](https://academy.pega.com/it/topic/rule-resolution/v1/in/2866/5227)、[Forward chaining（SA-5374）](https://community.pega.com/support/support-articles/declare-rule-execution-very-slow-use-case)
- Camunda/DMN：[DMN in Modeler](https://docs.camunda.io/docs/8.6/components/modeler/dmn/)、[Decision requirements graph](https://docs.camunda.io/docs/8.6/components/modeler/dmn/decision-requirements-graph/)、[Choosing the DMN hit policy](https://docs.camunda.io/docs/8.6/components/best-practices/modeling/choosing-the-dmn-hit-policy/)、[OMG DMN](https://www.omg.org/spec/DMN)
- Drools：[Rule Language Reference](https://docs.drools.org/latest/drools-docs/drools/language-reference/index.html)、[Rule engine（agenda/TMS）](https://docs.drools.org/8.42.0.Final/drools-docs/drools/rule-engine/index.html)
- SAP：社区来源（非官方域）——[数据更新触发机制](https://cloud.tencent.com/developer/article/1745507)、[update processing V1/V2](https://www.sapewmhelp.com/?question=sap-update-processing)

### 2.2 五条共性规律（本专题的立论依据）

| # | 规律 | 依据 |
|---|---|---|
| **A** | **顺序必须显式且唯一**——八家都有明确的顺序表达，**没有一家把顺序留在两套并存机制里** | 管道阶段 / order 字段 / DRG 依赖 / 算法解析 / 序号，各有一种但只有一种 |
| **B** | **链式传播默认同步，重副作用默认异步** | Salesforce/Dataverse 同事务管道、ServiceNow before/after、Pega 前向链、Drools Rete、Oracle step 推进均同步；而 SAP V2、Oracle deferred、ServiceNow async、Dataverse 异步插件一律把重副作用外移 |
| **C** | **环防护至少要有一种硬手段**，且**层次不同** | Drools 同规则自触发抑制、Dataverse 递归深度计数、Salesforce 递归时跳过批次 |
| **D** | **显式依赖图与显式序号可以并存**：图定偏序、序号只做平局决策 | DMN 用 `required decision` 图 + hit policy；Oracle 用 dependencies + step 次；Drools 用 Rete 图 + salience |
| **E** | **跨对象后果必须明确事务归属**：要么同事务回滚，要么异步 + 补偿/幂等，**不允许含糊** | Oracle compensation、SAP V1/V2 二分、ServiceNow async |

> **对照我方**：G2 违反 A（两套顺序）；G3/G4 违反 C 的精神（有环却静默降级、链内失败被吞）；G5/G6 违反 E（跨对象后果既不同事务也无异步通道）；G1 是 D 的反面（有图能力但放弃了显式依赖边）。

---

## 3. 我方合理方案：一套顺序、两个通道、三种硬约束

### 3.1 总纲

```
         ┌───────────────── 一套顺序（SSOT）─────────────────┐
         │  RuleEngine.execute_rules_ordered()  ← 唯一入口    │
         │  内部 = ImplicitRuleChainExecutor                  │
         │  排序键 = 类型权重 → priority（降级为 tie-break）   │
         └───────────────────────┬───────────────────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
   ②a 同步通道（同一事务）              ②b 异步通道（提交后）
      字段↔字段、同对象、                通知、外部调用、
      「必须一致」的跨对象回写            重聚合、可延迟副作用
              │                                     │
      ③硬约束：环=加载期失败 / 深度=可配上限+报错 / 轨迹=落审计
```

### 3.2 三条设计决定

**决定一：顺序收口（治 G2/G3）**
- 新增 `RuleEngine.execute_rules_ordered(meta_object, trigger, context)`，内部统一走 `ImplicitRuleChainExecutor`。
- 现有 `execute_rules()` 改为其**薄封装**（或删除），杜绝"同一 trigger 被平铺跑一次、又被链跑一次"的重复执行（当前 validation 就存在此重复）。
- `priority` 语义**从"全局顺序"降级为"拓扑同层平局决策"**——这与 DMN hit policy / Drools salience / Dataverse Execution Order 的定位一致，也是把两套顺序收敛成一套的最小改动。
- `compute()` 的返回值必须带上 `success` / `errors`（治 G3），链内校验失败要能阻断。

**决定二：环与深度改为硬约束（治 G4）**
- 环检测从"运行期 warning + 降级"上移到 **schema 加载期/启动期报错**（对标"图应无环"）。存量若确有环，走两步：先 **dry-run 扫描**列出全部环（只报告不阻断），再逐个处置，避免一刀切导致启动失败。
- `MAX_PROPAGATION_DEPTH` 从常量改为**可配（per-object）+ 超限报错**，取代当前"静默截断"。
- 终止条件从"`changed_fields` 数量不增即 break"改为**按「规则 + 字段值」记账检测振荡**（当前逻辑在值抖动但字段集合不增时会误判收敛）。

**决定三：跨对象分两步接线（治 G5/G6）**
- **第一步（同事务，低风险）**：让 `DerivationExecutor` 聚合结果**真正回写目标对象**（当前只 SELECT）。回写后目标对象自身的规则自然接力 → 这才是真正的 A→B→C。
- **第二步（异步，高风险）**：再启用 `CrossObjectRuleChainExecutor`，并明确事务归属——同事务回滚 vs 异步 + 幂等键（对标规律 E）。第二步必须排在"异步通道"落地之后。

### 3.3 `depends_on` 的处置（治 G1，**已取「甲」并实施 · v1.5**）

| 选项 | 做法 | 理由 | 风险 |
|---|---|---|---|
| **甲（推荐）** | **启用**：`_build_edges` 在数据流边之外，追加 `depends_on` 声明的显式边 | DMN/Oracle 都用显式依赖（规律 D）；数据流推断在"表达式动态拼字段名"时会**漏边**，显式声明是确定性更强的补丁 | 两套依赖来源可能冲突（需定义优先级：显式边优先） |
| 乙 | **删除** `depends_on` 字段 | 少一个概念，避免两套依赖冲突 | 放弃显式依赖能力，漏边问题无解 |

**实施（甲）**：

1. **建边**：[rule_chain.py `_build_edges`](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L309-L337) 先收集显式边（`dep_id → rule.id`，边类型 `EdgeType.EXPLICIT_DEPENDENCY`），并记录其**反向对**；随后所有推断边统一走 `_add_inferred()`，若与显式边反向冲突则**丢弃** → 「显式边优先于推断边」落地，且显式声明可消除互相引用造成的**假环**。
2. **装载**：[yaml_loader.parse_rule](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1583-L1612) 在类型分派后统一注入 `rule.depends_on = data.get("depends_on", [])`，避免逐个 `parse_*` 重复。
3. **回归**：[test_rule_chain.py::test_explicit_dependency_edges](file:///d:/filework/excel-to-diagram/meta/tests/test_rule_chain.py#L296-L380) 覆盖两件事——显式依赖改变同类型规则的先后；显式边压制反向推断边、消除假环。
4. **存量影响为零**：当前所有 YAML 规则均未声明 `depends_on`（审计「顺序差异 0 / 未建图 0」在实施后不变）。

### 3.4 分阶段落地

| 阶段 | 内容 | 前置 | 风险 |
|---|---|---|---|
| **P0** | **影子模式**：同时按"新拓扑顺序"与"旧平铺顺序"计算，**只记录差异不改变行为**；并 dry-run 扫描全量 schema 的环 | 无 | 无（只读） |
| **P0.5** | ✅ **已做（v1.2）**：G9（状态迁移之间不成边）+ G10（拓扑排序遇环报错）；复测环 0、拓扑报错 0；运行时探针确认对存量行为中性 | 无 | 无（缺陷修复，行为中性已实证） |
| **P1** | 顺序收口：顺序改由拓扑序**唯一决定**（落在既有唯一入口 `execute_rules`，**不动调用点**）；`priority` 降级为 tie-break；`compute()` 不再吞校验结论 | ✅ **已落地（v1.4，用户拍板「直接切」）**：D7 tie-break 统一（顺序差异 8→0）+ G11 已修；实现方式为「链只取顺序、执行体仍用 flat 执行器」→ §1.6 的 7 项阻塞**全部失效**（见 §1.7）；审计复测顺序差异 0、新增跨字段校验回归用例通过。**`compute()` 吞校验结论（G3）已于 v1.5 修复，见 §1.8** | **高**（已从"语义变更"降为"仅改顺序"，行为中性已实证） |
| **P2** | 环=加载期硬失败；深度可配 + 超限报错；振荡检测（**G9/G10 已修，硬门禁现在可以安全上**；注意 G11 的"互斥兄弟互相覆盖"要在 P1 前解决，否则振荡检测会先撞上它） | P1 | 中 |
| **P3** | 执行轨迹可解释：保留 `execution_order`/`changes` 并落审计 | 无（可并行） | 低 |
| **P4** | 跨对象第一步：聚合派生回写目标对象 | P1 | 中 |
| **P5** | 异步通道：`execution_mode: sync\|async`（复用已有 `MetaTrigger.async_exec`）+ 幂等键 + outbox | P1 | 中高 |
| **P6** | 跨对象第二步：启用 `CrossObjectRuleChainExecutor`，明确事务边界；处置 `depends_on`（甲/乙） | P4 + P5 | 高 |

> **G11 建议**（P1 前置，属"治 G2/G3"的组成部分，与顺序收口同批实施）：把 flat 侧 `StateTransitionExecutor` 的 gating（Case 0 字段未变 / Case 1 已是目标态 / Case 1.5 用户未改状态 / Case 2 已被别的规则改走）下沉为**共享判定**，让 `_execute_state_transition` 复用；并在 `triggered_rules` 中**排除同字段的互斥兄弟**（它们不是下游，是替代项）。

### 3.5 明确不做（划边界，避免过度设计）

- **不引入** 完整 Saga/补偿框架（Oracle compensation 级别的能力）——当前无跨系统长事务需求，异步通道 + 幂等键足够。
- **不引入** Rete/真值维护（Drools TMS）——我们的规则规模（当前 YAML 规则声明近乎为 0）远未到需要增量匹配网络的程度。
- **不改** 现有"类型权重"次序（COMPUTATION → DERIVATION → CONSTRAINT → VALIDATION → STATE → TRIGGER），只把它确立为唯一顺序来源。
- **不把** 求值内核统一问题（G8）混进本专题——它是独立的一致性议题，另行登记。

---

## 4. 待决策清单

| # | 决策点 | 建议 |
|---|---|---|
| D1 | `depends_on` 启用还是删除？ | ✅ **已决并实施（v1.5）**：取**「甲」启用**（`EdgeType.EXPLICIT_DEPENDENCY`，显式边优先于推断边，反向冲突的推断边丢弃），装载侧在 `yaml_loader.parse_rule` 统一注入。见 §3.3 |
| D2 | P1 顺序收口是否先跑影子模式？ | ✅ **已决并实施（v1.4）**：用户拍板**直接切换、不跑影子模式**。落地为原子改动——「链只用来取顺序、执行体仍是 flat 执行器」，使 P0 影子模式要防的 7 项阻塞**全部不存在**；审计复测顺序差异 0（行为中性）。见 §1.7 |
| D3 | 环在存量 schema 中是否真实存在？ | ✅ **已结**：7 个报环**全部是状态机误报（G9）**，存量**无真环**；G9/G10 已修（v1.2） |
| D4 | 异步通道的幂等键口径 | 建议 `对象 + 记录 id + 规则 id + 输入快照 hash` |
| D5 | 跨对象第一步（回写）是否同事务？ | 建议**同事务**（可回滚），第二步再评估异步 |
| D6 | **G9 修正口径**：状态机互斥对如何建图？ | ✅ **已决并实施（v1.2）**：**排除 STATE_TRANSITION 之间的边**（互斥选择 ≠ 数据依赖）；`computation → state_transition` 的真依赖保留 |
| D7 | **同层平局 tie-break 口径统一为哪个？**（P1 前置） | ✅ **已决并实施（v1.3）**：用户拍板**改为「声明顺序」**（`(类型权重, priority, declaration_index)`）。复测：顺序差异 8 处 → **0 处** |
| D8 | **G11 何时修？**（P1 前置，不放 P2） | ✅ **已决并实施（v1.3）**：用户拍板**与 P1 同批**。gating 按 flat 的 Case 0/1/1.5/2/3 在链内补齐 + `triggered_rules` 排除同 `state_field` 互斥兄弟；四种情形探针实测链与 flat 一致 |

### 4.1 待办登记（未排期 · backlog）

> **用户确认（2026-10-03）**：P2~P6 均为**可选 / 可延后**——彼此不阻塞、当前无触发场景（存量 0 环、无 `permission` 规则、跨对象链未接线），登记为待办即可，**不在本批实施**。
> 下表 B8~B12 为本批「二次检查」发现项；均为**当前不可达 / 无影响**的加固项，不阻塞提交。

| # | 待办 | 来源 | 当前影响 |
|---|---|---|---|
| B1 | **P2**：环 = 加载期硬失败；传播深度可配 + 超限报错；振荡检测 | §3.4 | 无（存量 0 环） |
| B2 | **P3**：执行轨迹（`execution_order` / `changes`）落审计 | §3.4 | 无 |
| B3 | **P4**：聚合派生回写目标对象（A→B→C 打通） | §3.4 | 无（当前派生仅 SELECT） |
| B4 | **P5**：异步通道 `execution_mode: sync\|async` + 幂等键 + outbox | §3.4 | 无 |
| B5 | **P6**：启用 `CrossObjectRuleChainExecutor` + 明确事务边界 | §3.4 | 无 |
| B6 | **G4**：报环时仍静默降级（仅 `logger.warning`），应与 P2 的硬门禁一并收口 | §1.3 | 无（0 环） |
| B7 | **G5/G6/G7/G8**：跨对象链零接线 / 聚合不回写 / 派生 stub / 求值内核分裂（G8） | §1.3 | 无 |
| B8 | **二次检查①**：拓扑回退粒度是「全量」——对象内**任意**一处环会把本次触发的**全部**规则降级为 priority 序（[rule_executor.py#L1342-L1349](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1342-L1349)）。建议改为按连通分量 / 仅成环节点粒度回退 | 二次检查 | 无（存量 0 环）；宜随 B1 一并解决 |
| B9 | **二次检查②**：图外规则被无条件追加末尾；若它 `depends_on` 一个**不入图**的类型（`permission` / `default`），依赖方向会反（[rule_executor.py#L1351-L1355](file:///d:/filework/excel-to-diagram/meta/core/rule_executor.py#L1351-L1355) + [rule_chain.py#L319-L326](file:///d:/filework/excel-to-diagram/meta/core/rule_chain.py#L319-L326)） | 二次检查 | 无（当前无 `permission` 规则） |
| B10 | **二次检查③**：`_order_rules_by_dependency` 仅捕 `ValueError`——非环类异常（属性缺失等）会冒泡打断保存，与「避免整次保存失败」的注释相悖。建议收敛为明确环异常 + 其余异常记日志后回退 | 二次检查 | 无（当前不可达） |
| B11 | **二次检查④**：`DeprecatedSchemaSectionError` 会穿透 `load_yaml_directory` **中止整目录加载**，与其余解析错误「跳过单文件」行为不一致 | 二次检查 | 无（已无残留段） |
| B12 | **二次检查⑤**：`parse_aspects_yaml` 仍产出已被 `_resolve_aspects` 删除的 `"validations"` 键（死代码残留） | 二次检查 | 无 |

> **二次检查未发现「严重」级问题。** 另：`relationship.yaml` 迁移时删除的 4 条旧校验（`relation_type_in_enum` 等）按 §8.7 的 D/S 分类为**有意删除**（顶层 `validations:` 运行时本就不消费，`MetaObject.validations` 已无读取点），非缺陷。

---

## 5. 变更记录

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v1.0 | 2026-10-03 | 首版：固化我方编排现状（8 项缺口 + 执行序列图 + 空转事实）；8 家头部产品四维对标矩阵（每项附来源，未确证处如实标注）；提炼 5 条共性规律；给出"一套顺序、两个通道、三种硬约束"方案 + 6 阶段落地 + 明确不做边界 + 5 项待决策 | AI Assistant |
| v1.1 | 2026-10-03 | **P0 已执行（只读）**：新建审计脚本 [audit_rule_orchestration.py](file:///d:/filework/excel-to-diagram/.trae/scripts/audit_rule_orchestration.py) 并跑通（51 对象 / 8 有规则 / 7 报环 / 8 顺序差异 / 1 重复覆盖）。新增 **G9**（`STATE_TRANSITION` 的 source/target 同为 `state_field` → 互斥迁移必然成环，环检测大规模误报）、**G10**（Kahn 遇环静默返回不完整序列）；新增 §1.4 实测结果。**方案影响**：原 P2"环=加载期硬失败"直上会拒掉 8 个有规则对象中的 7 个（即搞挂平台），故 P2 前置"先修 G9+G10"；§3.4 P2 行、§4 新增 D6（G9 修正口径） | AI Assistant |
| v1.2 | 2026-10-03 | **G9 / G10 已修并复测**（`meta/core/rule_chain.py` 2 处）：G9 按 D6 口径在 `_build_edges` 中"状态迁移之间不成边"；G10 在 `topological_sort` 末尾校验并抛 `ValueError`。复测：**环 7→0、拓扑报错 0、空序列 7→0**；运行时探针确认 `ImplicitRuleChainExecutor(product)` 不再抛错、`compute()` 对存量行为中性；5 个规则相关测试文件全绿。新增 §1.5（实施 + 复测 + 运行时验证）。**新增发现 G11**（链内 `_execute_state_transition` 缺 gating，互斥兄弟互相覆盖 → 请求状态被静默回滚；`before_update` 探针实证 `is_active` 由 True 被改回 False；当前因 `compute()` 只走 `before_save` 而不可达，但 **P1 收口前必须先修**）。**新增 D7**（tie-break 口径统一）、**D8**（G11 修期）；§3.4 增 P0.5 行、P1/P2 前置更新 | AI Assistant |
| v1.3 | 2026-10-03 | **D7 + G11 已修并复测**（用户拍板：tie-break 取声明顺序；G11 与 P1 同批）。D7：`RuleNode.declaration_index` + `topological_sort` 排序键改用声明索引 → **顺序差异 8 处 → 0 处**。G11：`should_execute` 取消 STATE_TRANSITION 的 live 预筛、`_execute_state_transition` 补齐 flat 的 Case 0/1/1.5/2/3 gating、`triggered_rules` 排除同 `state_field` 互斥兄弟 → 四情形探针链与 flat 全一致。审计脚本「顺序差异」计数口径拆出 overlap。新增 §1.6（实施 + 复测 + **P1 的 7 项阻塞**：触发器/派生 stub、`entered_at`、执行集合差异、返回类型、传播循环、trigger 过滤）；D7/D8 标记已决；P1 行改为"语义变更，需先处置阻塞并跑影子模式" | AI Assistant |
| v1.4 | 2026-10-03 | **P1 顺序唯一入口已落地并复测**（用户拍板「直接切」，不跑影子模式）。落地方式：**排序做进既有唯一入口** `RuleEngine.execute_rules`（新增 `_order_rules_by_dependency`，不动任何调用点）——图内规则按 `topological_sort` 次序、图外规则按 priority 追加末尾、报环回退 priority 并告警；**执行体仍是 flat 各类型执行器**（只改顺序）。因此 §1.6 的 7 项阻塞**全部失效**（它们只在"链 executor 成为唯一执行体"时成立）。审计复测：环 0 / 拓扑报错 0 / **顺序差异 0** / 未建图规则 0（对存量 8 个有规则对象行为中性）。新增回归用例 `test_rule_engine_cross_field_validation_order`（只改 `price`，依赖序保证先算后校；校验 priority 故意更小以证伪"仍按 priority"）。规则相关 5 个测试文件全绿；`test_rule_engine_layer.py` 的 3 个失败经对照实验确认为既有 `FOREIGN KEY` 数据问题、与本改动无关。新增 §1.7；D2 标记已决；P1 行改为"已落地" | AI Assistant |
| v1.5 | 2026-10-03 | **G3 + G1 已修并复测**。G3：`compute()` 不再运行 `ImplicitRuleChainExecutor`（删除 `use_chain`/`changed_fields` 形参，全仓确认 3 个调用方均未使用），只保留「计算」且顺序与 `execute_rules` 统一为依赖拓扑序；根治理由是链内校验以 `condition` 当判定、平铺 `ValidationExecutor` 以 `action` 当判定，**上抛链结论会误阻断合法保存**（见 §1.8 根因说明）。G1：`yaml_loader.parse_rule` 统一注入 `depends_on`（此前全仓 0 处读写）；`rule_chain._build_edges` 新增 `EdgeType.EXPLICIT_DEPENDENCY` 显式边且**显式优先于推断**（反向冲突的推断边丢弃）。新增回归 `test_compute_only_computes_and_ignores_validation`、`test_explicit_dependency_edges`；`test_rule_chain`(6) / `test_rule_engine`(11) / `test_rule_provider_unit`(9) / `test_rule_validations_migration`(4) / `test_derivation`(6) 全绿；审计脚本复测顺序差异仍为 0。审计脚本「两路重复执行」指标标注为**设计探针**（生产路径已无重复）。新增 §1.8；G1/G3 标记已修 | AI Assistant |
| v1.6 | 2026-10-03 | **二次检查完成 + 待办登记**。独立复核本批全部未提交改动（rule_executor / rule_chain / yaml_loader / models / validator / 2 个测试 + 审计脚本 + 校验迁移）：**无「严重」级问题**；提出 3 项加固项与 2 项一致性提示，均已登记 §4.1（B8~B12，均为当前不可达/无影响）。用户确认 **P2~P6 为可选/可延后**（互不阻塞、当前无触发场景），一并登记 B1~B7。**提交范围**：仅规则模型相关文件；`tools/*`+`scripts/*`+`*.service`+`meta/migrations/*` 的批量路径改动（`/opt/miniconda3-py39/bin/python` → `/usr/local/bin/python3`）与 `docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md`（多产品平台 v1.29.8）经核实**与本批无关，排除**。新增 §4.1 | AI Assistant |
