# Spec: 规则模型场景化与扩展属性接入（Sourcing / Extended Attributes）

> 本文是 [2026-11-07-rule-convergence-spec.md](./2026-11-07-rule-convergence-spec.md) §12（语义模型）与 §13（元数据驱动与单一事实源）的**细化补充**，不修改、不替代原文。
> 范围：①Sourcing 作为规则场景接入；②扩展属性（物料/组织/客商等）接入规则模型；③场景因子轴声明与 trace 输入快照契约；④分级路线图与验收标准。

## 1. 背景与目标

### 1.1 背景

规则收敛 Spec §13 已确立三条约束：每个语义只有一个 owner、一个读取入口，其余只能是投影/派生/缓存/快照；DB 层规则不新造枚举；元数据必须可闭合校验。当前实现存在三个缺口：

1. **Sourcing 能力完整但不在规则事实图内**：`sourcing_rules` 等四张表、五步解析、守卫、API 均已落地，但规则目录（`rule_catalog_service`）不聚合它，`rule_trace_service` 的 6 个场景不含它，`rule_key` 对它是空白。
2. **扩展属性无法被规则消费**：`attribute_definition / attribute_scope / <object>_attribute_values` 元模型完整，但 `RuleContext` 只装载行数据与 schema `relations`，没有值表读取通道；`attribute_promotion` 仅有 lint 文案约束。
3. **因子轴与轨迹契约是封闭常量**：`DIMENSION_FIELDS` 固定 4 维，无法表达 sourcing 的 item/目的组织/目的库位/用途/日期；trace 只快照 4 个维度，表达式实际读取的跨对象字段与扩展属性没有留痕，回放能力不完整。

### 1.2 业务目标

- 让「为什么选了这个来源/这条规则」在同一套规则中心里可查、可解释、可审计，而不是 sourcing 自成一套。
- 让租户扩展属性可以在规则条件中被引用，同时不破坏发布审计键、索引与多租户边界。
- 消除「特异性排序 / 身份 / 轨迹」三处双轨，避免后续规则域继续各造一套。

### 1.3 涉众目标

- 规则中心配置与审计人员：一处看到 sourcing 规则、同一 `rule_key`、同一轨迹形状。
- 供应链寻源配置人员：sourcing 规则仍按 BO 生命周期维护，不被迫迁移到配置发布流。
- 规则引擎/目录维护者：新增规则域只需登记场景 + adapter，不改枚举、不改全局因子轴。
- 前端规则中心：`sources`/`scenarios`/`factor_keys` 由后端派生下发，无需手写数组。

## 2. 需求类型总览

| 类型 | 适用 | 依据 |
|---|---|---|
| 业务需求 | 是 | §1.2：统一规则事实图、降低双轨维护成本 |
| 涉众需求 | 是 | §1.3：配置/审计/寻源/前端四类角色 |
| 解决方案需求 | 是 | 场景注册表 + AttributeProvider + trace inputs |
| 功能需求 | 是 | §3 FR-001 ~ FR-012 |
| 非功能需求 | 是 | §4 NFR-001 ~ NFR-005 |
| 外部接口需求 | 是 | §5 IF-001 ~ IF-005 |
| 迁移需求 | 是 | §6 TR-001 ~ TR-003 |

## 3. 功能需求

### FR-001: 场景注册表成为唯一声明源

- **Description**: 系统 MUST 提供 `meta/core/rule_scenarios.py` 作为场景/载体/因子轴/命中策略的唯一声明源；`rule_trace_service`、规则目录、视图元数据生成器 MUST 从该注册表派生，不得各自维护清单。
- **Acceptance Criteria**:
  - 注册表同时声明 `scenario`、`source`、`semantic_class`、`semantic_type`、`legacy_rule_type`、`hit_policy`、`factor_keys`、`instrumented`、`configurable`、`publishable`。
  - `view-config` 返回的 `trace.scenarios` 与 `sources` 与注册表逐字相等（顺序可归一）。
  - 启动期/测试期闭合校验：每个已登记 source 要么有 instrumented 场景，要么在 `NOT_INSTRUMENTED_SOURCES` 中显式声明。
- **Priority**: Must
- **Source**: §13.1 / F-13-12 现状；§1.2

### FR-002: Sourcing 登记为场景与载体

- **Description**: 系统 MUST 以 `source='sourcing'`（载体）、`scenario='sourcing'`（业务场景）、`semantic_class=decision`、`semantic_type=determination`、`legacy_rule_type='sourcing'`、`hit_policy='first'` 登记 sourcing，且 MUST NOT 新增 `RuleType` 枚举值。
- **Acceptance Criteria**:
  - 注册表出现 sourcing 条目；`RuleType` 枚举值集合不变。
  - 规则目录可列出 `sourcing_rules` 数据行，字段含 `rule_key`、名称、状态、作用域摘要、`links.edit`。
  - 目录条目标记 `configurable=false`、`publishable=false`，不提供统一发布动作。
- **Priority**: Must
- **Source**: §12.5 / §12.7；Sourcing P43 实现

### FR-003: Sourcing 唯一身份 rule_key

- **Description**: 系统 MUST 为每条 sourcing 规则生成唯一 `rule_key = sourcing:{rule_code}`，规则目录、trace、详情、发布审计、导出 MUST 使用同一函数产出，禁止拼接。
- **Acceptance Criteria**:
  - 四处 `rule_key` 逐字相等（契约测试）。
  - `rule_code` 变更（若允许）时旧键在 trace 中保留原值，不做追溯改写。
- **Priority**: Must
- **Source**: §13.2 身份单一；FR-001

### FR-004: 场景因子轴声明与兼容

- **Description**: 每个场景 MUST 在注册表声明自己的 `factor_keys`；全局 `DIMENSION_FIELDS` 降级为**并集投影**（只读兼容），新增代码 MUST 通过场景元数据读取因子轴。
- **Acceptance Criteria**:
  - 现有 6 个场景行为不变，其 `factor_keys` 并集等于原 4 维。
  - sourcing 声明 `factor_keys = (dest_org_id, item_id, usage, eval_date)`；`dest_location_id` 只作为可选匹配输入记录在 `inputs.fields`，不得进入因子轴（对齐 Fusion/SAP：寻源键为「组织 + 物料（+ 日期）」，库位不是寻源轴）。
  - `item_group_id` 由物料派生用于作用域匹配，记录为 `inputs.derived`，不作为独立因子。
  - 契约测试禁止在 `rule_scenarios.py` 与 `rule_keys.py` 之外新增因子轴字面量数组。
- **Priority**: Must
- **Source**: §13.1 / F-13-12；sourcing 作用域能力

### FR-005: Sourcing 轨迹适配器

- **Description**: 系统 MUST 提供 sourcing trace adapter，将 `sourcing_service` 现有 `explain`（assignment / line_filter / line_pick）映射到统一 trace 信封（`rule_key`、`stage`、`decision`、`kind`、`skip_reason`、`factors`），MUST NOT 在 trace 路径重新实现匹配算法。
- **Acceptance Criteria**:
  - 命中：返回命中规则 `rule_key` + 来源行 + 因子快照，`kind=hit`。
  - 无候选：返回 `kind=miss` + 淘汰原因分类（作用域不匹配/日期失效/资格不符/无可用来源）。
  - trace 求值结果与 `/sourcing/resolve` 同输入下不矛盾（同一规则、同一排序）。
- **Priority**: Must
- **Source**: §12.4 轨迹统一；sourcing `explain`

### FR-006: 扩展属性唯一读取入口 AttributeProvider

- **Description**: 系统 MUST 提供 `AttributeProvider.resolve(object_type, object_ids, codes)` 作为 `<object>_attribute_values` 的唯一读取入口；规则引擎、trace、目录、业务服务 MUST NOT 直接查询值表。
- **Acceptance Criteria**:
  - 代码检索无值表直查（除 AttributeProvider 与 AttributeValueService 实现内部）。
  - 返回结构含 `value`、`source`（value/default/missing）、`definition_id`、`definition_version`。
  - 多租户/应用作用域由 Provider 统一注入，调用方不拼租户条件。
- **Priority**: Must
- **Source**: §13.3 单入口；attribute_value_service

### FR-007: 扩展属性表达式命名空间

- **Description**: 规则表达式 MUST 支持 `attrs.<code>`（当前对象）与 `self.<relation>.attrs.<code>`（跨对象，如物料/客商/组织）；未定义或已停用的属性 MUST 解析为 `missing` 而非异常。
- **Acceptance Criteria**:
  - 单测覆盖：已定义有值、无值、定义停用、类型不匹配、跨对象取值。
  - 缺失/停用 → 表达式求值为 `None`，条件判定为不命中，trace 记录 `attribute_missing` / `attribute_inactive`，不抛异常。
  - 跨对象属性按 `relations` 声明的目标对象解析，禁止按字段名猜对象。
  - P1 范围：根对象 `attrs.<code>` + `item.attrs.<code>`；`party/org` 跨对象属性在 P2 完成性能与租户隔离评估后开放（对齐 Fusion/SAP：扩展属性不参与标准寻源键）。
- **Priority**: Must
- **Source**: §12 表达式不变量；attribute_scope

### FR-008: Trace 输入快照（factors + expression inputs）

- **Description**: trace MUST 记录本次求值实际读取的全部输入：场景因子、表达式引用的字段路径与值、扩展属性（code/值/来源/定义版本）；快照 MUST 由同一次求值过程采集，禁止事后重解析。
- **Acceptance Criteria**:
  - 响应新增 `inputs` 段（可选字段），旧客户端忽略后行为不变。
  - 同一输入重放得到同一结论；属性值变更后旧 trace 仍展示"当时值"。
  - 未引用的变量不进入快照（控制体积）。
- **Priority**: Must
- **Source**: §12.4 可解释/可回归；现有 trace 仅 4 维因子

### FR-009: 可用属性变量派生下发

- **Description**: 系统 MUST 按 `attribute_scopes(对象) + usage_class ∈ {descriptive, analytic} + status=active` 派生"规则可用属性变量"清单，并随视图元数据下发；YAML/前端 MUST NOT 手写该清单。
- **Acceptance Criteria**:
  - 新增属性定义后，无需改 YAML 即可出现在变量清单。
  - 停用定义后，清单移除且已有表达式按 FR-007 语义处理。
  - 清单项含 `code / label / data_type / scope_level`。
- **Priority**: Should
- **Source**: §13.4 视图元数据同源；attribute_lint_service

### FR-010: 扩展属性不得作为因子轴

- **Description**: 扩展属性 MUST NOT 进入 `factor_keys` 或发布审计键；只有经 `attribute_promotion` 提升为物理字段后，该物理字段才可作为因子轴。
- **Acceptance Criteria**:
  - 注册表校验：场景 `factor_keys` 与属性 code 命名空间不重叠。
  - 提交含扩展属性的因子声明时启动期报错并给出替代路径提示。
- **Priority**: Must
- **Source**: §13.3；usage_class=indexed/computed 必须提升

### FR-011: 属性变更的缓存失效

- **Description**: 属性值写入、定义停用/改类型、promotion 完成后 MUST 触发 AttributeProvider 对应缓存失效；跨进程场景以 TTL 兜底。
- **Acceptance Criteria**:
  - 值变更后下一次解析返回新值（同进程）。
  - 停用定义后下一次解析返回 `missing/inactive`。
  - 缓存键含 `app_id + object_type + ids + codes`。
- **Priority**: Should
- **Source**: §13.3 缓存不得成为第二事实源

### FR-012: Sourcing 发布策略显式化

- **Description**: Sourcing 规则 MUST 明确为「BO 生命周期（draft/active/inactive）」，不进入统一配置发布流；目录描述符 MUST 显式标注 `configurable=false`、`publishable=false`。
- **Acceptance Criteria**:
  - 规则中心详情页不出现"发布/回滚"动作。
  - 审计仍可查询规则状态变更历史（沿用 BO 审计）。
- **Priority**: Should
- **Source**: §13.2 生命周期单一归属；FR-002

## 4. 非功能需求

### NFR-001: 向后兼容

- **Description**: 现有 6 场景、4 维因子、无 `inputs` 的 trace 响应 MUST 保持兼容。
- **Measurement**: 现有规则/追踪相关测试全绿；旧响应字段不删除、不改语义。
- **Priority**: Must

### NFR-002: 性能

- **Description**: AttributeProvider 批量解析 MUST 避免 N+1：同一请求内相同 `(object_type, id, code)` 只解析一次；跨对象批量查询按对象集合合并。
- **Measurement**: 单规则求值新增查询次数 ≤ 1/属性对象类型；本机 P95 增量 ≤ 5ms（以基准脚本记录）。
- **Priority**: Must

### NFR-003: 可观测与可回放

- **Description**: trace MUST 能回答"读了什么、值来自值表还是默认、定义版本是多少"。
- **Measurement**: trace `inputs.attrs[]` 含 `path/code/value/source/definition_version`；回放测试通过。
- **Priority**: Must

### NFR-004: 多租户与安全

- **Description**: 属性值解析 MUST 在 Provider 内强制应用/租户作用域，禁止跨租户读取。
- **Measurement**: 单测覆盖跨租户访问返回 missing；代码审查无绕过路径。
- **Priority**: Must

### NFR-005: 可测试性

- **Description**: 新增能力 MUST 提供单元 + 契约测试，统一使用 `python d:\filework\test.py --root d:\filework\doc-flow-worktree --file ...` 执行。
- **Measurement**: 新增测试文件至少覆盖 FR-001/002/003/005/006/007/008/010。
- **Priority**: Must

## 5. 外部接口需求

### IF-001: 规则目录查询（现有 rule_center API）

- **Type**: API
- **Endpoint / Entry**: 现有规则目录查询路由（`meta/api/rule_center_api.py`），不新增路由。
- **Request/Response**: 条目新增/补齐 `rule_key`、`source`、`scenario`、`semantic_class`、`configurable`、`publishable`、`links.edit`。
- **Error Handling**: sourcing 表不可用时返回空列表并标记 `degraded=true`，不 500。
- **Source**: FR-001/002/003

### IF-002: 规则追踪查询（现有 trace API）

- **Type**: API
- **Endpoint / Entry**: 现有规则追踪路由，响应新增可选 `inputs`。
- **Request/Response**: `inputs.factors`、`inputs.fields[]`、`inputs.attrs[]`、`inputs.relations[]`。
- **Error Handling**: 场景未注册 → `skip` + `reason=scenario_not_registered`；adapter 异常 → 该场景 `skip`，不阻断其他场景。
- **Source**: FR-005/008

### IF-003: AttributeProvider 内部契约

- **Type**: 内部 Python 接口
- **Entry**: `meta/core/attribute_provider.py`
- **Contract**:
  - `resolve(object_type, object_ids, codes) -> {object_id: {code: {value, source, definition_id, definition_version}}}`
  - `available_variables(bo_id) -> [{code, label, data_type, scope_level}]`
  - `invalidate(object_type, object_ids=None, codes=None) -> None`
- **Error Handling**: 未注册对象类型/无值表 → 全量 `missing`；定义停用 → `missing` + `reason=inactive`。
- **Source**: FR-006/007/009/011

### IF-004: 视图元数据下发

- **Type**: API（现有 view-config）
- **Entry**: 现有视图元数据接口
- **Request/Response**: `trace.scenarios`、`trace.sources`、`trace.factor_keys`（按场景）由注册表派生；`attribute_variables` 按对象下发。
- **Error Handling**: 派生失败时保留上一版静态快照并告警，不返回空数组掩盖问题。
- **Source**: FR-001/004/009

### IF-005: Sourcing 解析接口（复用）

- **Type**: API
- **Entry**: 现有 `/api/v1/sourcing/resolve`、`/rules/<id>/validate`
- **Request/Response**: 不改请求；响应 `explain` 由 trace adapter 消费，不复制逻辑。
- **Error Handling**: 沿用现有错误码。
- **Source**: FR-005

## 6. 迁移需求

### TR-001: 旧 trace 兼容

- **Description**: 历史调用方可能按固定字段渲染 trace。
- **Strategy**: `inputs` 为新增可选字段；响应版本不做破坏性升级；前端按存在性渲染。
- **Rollback Plan**: 关闭快照采集开关即回到旧结构（字段缺失）。
- **Source**: FR-008

### TR-002: Sourcing 登记灰度

- **Description**: adapter 上线前，sourcing 已在目录/视图中可见但不参与推导。
- **Strategy**: 先以 `NOT_INSTRUMENTED_SOURCES` 登记 `sourcing`（与 state_machine/numbering 同款），adapter 与契约测试通过后移出该集合。
- **Rollback Plan**: 将 `instrumented=false` 回退，目录标记只读来源，不影响 sourcing 业务。
- **Source**: FR-001/002/005

### TR-003: 属性变量清单灰度

- **Description**: 变量清单从手工走向派生期间可能出现差异。
- **Strategy**: 派生结果与现有前端清单做一次差异审计；差异项人工确认后再切换。
- **Rollback Plan**: 保留静态清单兜底开关一个迭代，之后删除。
- **Source**: FR-009

## 7. 约束与假设

### 7.1 技术约束

- MUST NOT 新增 `RuleType` 枚举值（§12.7）。
- MUST NOT 把扩展属性值 JOIN 进业务行或写入 `RuleContext.data`。
- MUST NOT 新增 `org_attribute_values` 或把组织加入 `attribute_scope` 定义维度。
- 规则求值算法属 L3，场景适配器只做映射，不复制匹配/排序逻辑。
- 测试唯一入口 `python d:\filework\test.py`；所有命令遵守 workspace 铁律。

### 7.2 业务约束

- 扩展属性只做条件变量，不做因子/审计键（FR-010）。
- Sourcing 沿用 BO 生命周期，不迁入统一发布流（FR-012）。

### 7.3 假设

- 假设 sourcing `explain` 已稳定包含 `assignment/line_filter/line_pick` 三段及淘汰原因 — 来源：代码核对，待 P1 实现时再次验证（TBD-004）。
- 假设 `attribute_scopes` 的由具体到通用优先级已由值服务实现，Provider 复用 — 来源：现有实现，已验证。
- 假设 `item/party/batch` 值表已存在，`org` 无值表 — 来源：schema/迁移检索，已验证。

## 8. 优先级与里程碑

| ID | 需求 | 优先级 | 理由 |
|---|---|---|---|
| FR-001 | 场景注册表 | Must | 后续全部工作的单一声明基础 |
| FR-002 | Sourcing 登记 | Must | 目录/追踪可见性的前提 |
| FR-003 | 唯一 rule_key | Must | 身份双轨是本轮核心缺口 |
| FR-004 | 因子轴声明 | Must | 解除 4 维封闭，兼容旧行为 |
| FR-005 | Sourcing 轨迹 | Must | "为什么命中"可解释 |
| FR-006 | AttributeProvider | Must | 扩展属性唯一读取入口 |
| FR-007 | attrs 表达式 | Must | 扩展属性可用性的用户可见部分 |
| FR-008 | trace inputs 快照 | Must | 回放/审计成立的前提 |
| FR-009 | 可变变量清单 | Should | 降低前端/YAML 漂移 |
| FR-010 | 禁止属性作因子 | Must | 防止索引/审计键被污染 |
| FR-011 | 缓存失效 | Should | 正确性 + 性能平衡 |
| FR-012 | Sourcing 发布策略 | Should | 避免第二套发布流 |

- 里程碑：
  - M1（P0，契约先行）：FR-001/002（仅登记 NOT_INSTRUMENTED）/003/004/010，零行为变更。
  - M2（P1，接入）：FR-005/006/007/008/011，配套契约与单测。
  - M3（P2，治理）：FR-009/012，promotion 落表与影响面分析。

## 9. 变更 / 设计方案（RFC）

### 9.1 As-Is 分析

- **现状架构**：
  - 场景与载体清单分散在 `rule_trace_service.TRACE_SCENARIOS`、`rule_keys.SOURCES/NOT_INSTRUMENTED_SOURCES`、`rule_center_view.yaml` 三处，靠契约测试约束。
  - 因子轴为 `DIMENSION_FIELDS` 四维常量，被推导、试算、控制参数、视图元数据共用。
  - 规则表达式通过 `CrossObjectResolver` 读取行数据与 `relations`，无扩展属性通道。
  - trace 仅记录四维因子，不记录表达式实际读取的字段。
  - sourcing 有独立 resolver 与 `explain`，但无目录、无 `rule_key`、无 trace。
- **现有问题**：
  - 身份双轨（`sourcing_rules.id/code` vs `rule_key`）。
  - 特异性排序双实现（控制参数 vs sourcing），"不回退到更粗规则"仅在一处实现。
  - 轨迹双契约（`explain[]` vs trace 信封）。
  - 扩展属性值表可被任意代码直查，形成第二读取入口的风险。
  - 属性提升（promotion）只有约束文案，没有实现，导致"需要参与计算"的属性事实上无法进入规则。
- **相关代码路径**：
  - `meta/core/rule_keys.py`、`meta/core/rule_trace_service.py`、`meta/core/rule_executor.py`
  - `meta/core/cross_object_resolver.py`、`meta/services/sourcing_service.py`
  - `meta/services/attribute_value_service.py`、`meta/services/attribute_lint_service.py`
  - `meta/services/rule_catalog_service.py`、`meta/schemas/rule_center_view.yaml`

### 9.2 Target State

- **目标架构**：
  1. `meta/core/rule_scenarios.py` 成为场景/载体/因子轴/命中策略的唯一声明源。
  2. Sourcing 以 `source + scenario + legacy_rule_type` 登记，目录通过只读 adapter 聚合，trace 通过映射 adapter 归一。
  3. `AttributeProvider` 成为扩展属性唯一读取入口；表达式新增 `attrs` 命名空间；trace 记录实际读取的输入。
  4. 因子轴由场景声明，全局常量退化为并集投影。
- **关键变化**：
  - 新增：`rule_scenarios.py`、`attribute_provider.py`、sourcing catalog adapter、sourcing trace adapter、inputs 采集器。
  - 修改：`rule_trace_service`（场景分发 + inputs）、`rule_executor`（attrs locals + 采集）、`cross_object_resolver`（related.attrs）、view-config 生成器、`rule_catalog_service`。
  - 不动：`RuleType` 枚举、四维兼容行为、sourcing 匹配算法。

### 9.3 详细设计

#### 9.3.1 场景注册表（唯一声明）

模块 `meta/core/rule_scenarios.py`，仅依赖标准库，避免循环引用：

| 字段 | 说明 |
|---|---|
| `scenario` | 场景标识（如 `default` / `doc_flow` / `sourcing`） |
| `source` | 载体（`bo_yaml` / `doc_flow` / `sourcing` …） |
| `semantic_class` | `constraint` / `decision` / `action` / `projection`（§12） |
| `semantic_type` | `validation` / `determination` / `computation` … |
| `legacy_rule_type` | 兼容旧 `rule_type` 词（如 `doc_flow`、`sourcing`） |
| `hit_policy` | `all` / `first` / `best` |
| `factor_keys` | 本场景因子轴元组 |
| `instrumented` | 是否已接入 trace 求值 |
| `configurable` / `publishable` | 目录能力声明 |
| `stage_map` | 场景内部阶段 → 统一 stage |

派生：`SOURCES`、`NOT_INSTRUMENTED_SOURCES`、`SCENARIO_FACTOR_KEYS`、`TRACE_SCENARIO_HANDLERS`。`rule_keys.DIMENSION_FIELDS` 改为 `union(factor_keys)` 的只读投影，并加注释标注"仅供旧代码兼容"。

#### 9.3.2 Sourcing 身份与目录

- `rule_key = f"sourcing:{rule_code}"`，由 `rule_keys` 的键生成器唯一产出。
- 目录 adapter：读取 `sourcing_rules`（含状态、作用域摘要），输出统一条目；`links.edit` 指向 sourcing BO 页面；`configurable=false`、`publishable=false`。
- 载体不可用（表缺失/迁移未跑）时返回空列表 + `degraded=true`。

#### 9.3.3 Sourcing trace 适配器

输入：BO 行（如采购行）→ 取 `item_id / org / location / usage / eval_date`。

输出映射：

| sourcing explain 阶段 | 统一 stage | decision/kind |
|---|---|---|
| assignment（规则作用域匹配） | `scope` | matched / skipped(scope_mismatch) |
| line_filter（有效性/日期/资格） | `filter` | matched / skipped(inactive/date/qualification) |
| line_pick（排序取源） | `select` | hit / miss(no_candidate) |

- 因子快照 = 解析实际输入（FR-008）。
- 不复制排序算法；排序结果以 sourcing resolver 返回为准，adapter 只做形状映射。

#### 9.3.4 AttributeProvider

- 位置：`meta/core/attribute_provider.py`。
- 复用 `AttributeValueService.for_object()` 建立对象类型 → 值表映射；不新增表。
- 解析顺序：Provider 缓存 → 值表（按 scope 优先级）→ 默认值 → `missing`。
- 缓存：请求级 memo（必选）+ 进程级 TTL LRU（可选）；键 `(app_id, object_type, ids, codes)`。
- 失效钩子：属性值写入/定义变更/promotion 完成时调用 `invalidate`；跨进程 TTL 兜底。
- 可用变量：`available_variables(bo_id)` 由 `attribute_scope + usage_class∈{descriptive,analytic} + active` 派生，过滤 `indexed/computed`。

#### 9.3.5 表达式与快照

- `RuleContext` 增加：
  - `attrs` 代理（当前对象）。
  - 输入采集器 `_accessed`：记录 `fields[path]=value`、`attrs[]{path,code,value,source,definition_version}`、`relations[]`。
- `build_cross_object_locals` 返回的代理支持 `.attrs` 次级命名空间（跨对象）。
- trace 响应新增 `inputs`，由 `rule_trace_service` 透传采集结果；`SCENARIO_FACTOR_KEYS` 决定 `inputs.factors`。
- 缺失/停用语义：求值返回 `None`；比较不命中；`skip_reason` 记录 `attribute_missing` / `attribute_inactive`；不抛异常。

#### 9.3.6 数据模型

- P0/P1 **不新增表**：sourcing 复用现有四表；扩展属性复用定义/范围/值表。
- P2 才引入 `attribute_promotion` 表（字段：`id、object_type、attribute_code、target_table、target_column、sync_mode、status`）与同步服务。
- trace 为按需计算，不落库；快照随响应返回。

#### 9.3.7 主要流程

1. 规则目录：请求 → 注册表取 sources/scenarios → 各 adapter 汇总 → 统一条目（含 rule_key/能力标记）。
2. 规则求值：表达式读取 `self/attrs/relations` → 采集器记录输入 → 返回结果。
3. 规则追踪：按场景分发 handler → 现有 resolver 求值 → 采集输入 → 统一信封 + `inputs`。
4. 视图元数据：注册表派生 scenarios/sources/factor_keys；属性变量按对象派生。

#### 9.3.8 与 Fusion / SAP 的对齐结论（2026-11-09）

对齐原则：**寻源键取交集、扩展能力取超集、解释能力自建契约**。

| 能力 | Oracle Fusion | SAP | 本平台现状 | 结论 |
|---|---|---|---|---|
| 寻源键 | 组织 + 物料/品类（Item-Organization 级），含有效期 | 物料 + 工厂（+ 有效期） | `item_id + dest_org_id + usage + date` | 键已对齐；`usage` 是本地增强，保留 |
| 库位是否寻源轴 | 否（目的地库位属单据明细） | 否（工厂级寻源） | 现为可选输入 | **不作因子轴**，只记录 `inputs.fields` |
| 有效期 | 规则/分配均有生效区间 | 来源清单记录逐条有效期 | 规则/分配/来源行均有有效期 | 已对齐 |
| 资格过滤 | ASL（批准供应商清单） | 来源清单 blocked / MRP 标识 | mode policy + 行 blocked/fixed | 已对齐，保持分层 |
| 优先级/分摊 | rank + allocation %（合计 100） | 配额 + 配额比率 / 固定源 | specificity_rank + seq + rank；`allocation_pct` 仅计划提示 | 分摊是**声明缺口**：如需拆量，另建配额对象，不复用 `allocation_pct` |
| 扩展属性参与寻源 | 标准键不变，DFF/EFF 用于扩展与报表 | 标准逻辑不开放，需 BAdI/增强 | 无通道 | 规则仅可作**条件变量**，不可作因子（FR-010） |
| 可解释性 | 以日志/计划工作台为主 | 有限追踪（MRP 来源/配额比率） | 已有三段 `explain` | 本平台领先，**冻结自有契约**而非向下对齐 |

由此确认四项 TBD：

- **TBD-001（因子轴）**：sourcing `factor_keys = (dest_org_id, item_id, usage, eval_date)`。`dest_location_id` 保留为可选匹配输入；`item_group_id` 为派生值；供应商/来源类型/供应方式是**输出**，不进入因子。
- **TBD-002（跨对象属性）**：P1 只支持根对象与 `item.attrs`；`party/org` 属 P2。理由：Fusion/SAP 均不允许扩展属性进入标准寻源键；物料值表已存在、租户语义最清晰，先验证性能与失效链路。
- **TBD-003（promotion 同步）**：采用**一次性切换（cutover）**而非长期双写。状态机 `pending → column_created → backfilled → verified → active`；切换后物理列成为唯一 owner，值表标记 `promoted` 只读。回填期如需可编辑，允许同事务 write-through，但 Provider 在 `verified` 前仍读值表；切换后停止镜像。每日一致性校验 + 差异告警。
- **TBD-004（explain 稳定性）**：不向 Fusion/SAP 看齐，直接冻结本平台契约为 `explain_version=1`：固定三段 `scope / filter / select`，原因码枚举 `scope_mismatch / not_effective / inactive / usage_mismatch / mode_conflict / not_qualified / blocked / no_candidate / other`；未知原因归 `other` 并保留 `raw_reason`；仅允许增量扩展。
- **残留 TBD**：拆量/配额能力（TBD-005）——Fusion 的 allocation % 与 SAP 的配额比率都属"多源分摊"，与 `allocation_pct`（计划提示）语义不同，需单独立项，不在本轮范围。


### 9.4 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. 新增 `RuleType.SOURCING` | 直观 | 枚举继续承担语义+来源+场景三重含义，违反 §12.7 | 拒绝 |
| B. 把 sourcing 塞进 control_parameter | 复用现有解析 | 因子/命中策略/候选语义不同，会造成假统一 | 拒绝 |
| C. 场景注册表 + 只读 adapter（本方案） | 正交、可闭合校验、增量上线 | 需要新增注册表与两个 adapter | 选中 |
| D. 扩展属性直接 JOIN 进业务行 | 实现快 | 产生第二事实与陈旧副本，破坏 SSOT | 拒绝 |
| E. 只用 promotion，不做 Provider | 改动最小 | 未提升的属性无法进规则，且 promotion 尚未实现 | 作为兜底，不作为唯一路径 |
| F. 独立 AttributeProvider + attrs 命名空间（本方案） | 单入口、可快照、可失效 | 需处理缓存与跨对象 N+1 | 选中 |

### 9.5 实施与迁移计划

- **实施顺序**：
  1. P0：新增 `rule_scenarios.py`；登记 sourcing（NOT_INSTRUMENTED）；全局因子轴改并集投影；view-config 改为派生；契约测试。
  2. P1：sourcing catalog adapter → trace adapter；AttributeProvider；`attrs` 表达式；inputs 采集与响应；缓存失效。
  3. P2：`attribute_promotion` 落表与同步；影响面分析（定义变更 → 受影响规则）；变量清单切换收尾。
- **风险与缓解**：
  - 视图元数据派生导致快照漂移 → 契约测试逐字比对；失败保留上一版快照并告警。
  - 跨对象属性 N+1 → Provider 批量化 + 请求级 memo；基准脚本纳入验收。
  - 旧 trace 无 inputs → 字段可选；回放器按存在性降级。
  - sourcing explain 结构变化 → adapter 隔离；契约测试锁定三段 stage。
  - 属性类型变更导致历史快照误读 → 快照带 `definition_version`。
- **测试策略**：
  - 单元：`test_rule_scenarios_registry.py`（闭合校验/并集）、`test_attribute_provider.py`（missing/inactive/类型/租户/失效）、`test_rule_trace_inputs_snapshot.py`（采集/回放）。
  - 集成：`test_rule_trace_sourcing.py`（命中/未命中/无候选）、`test_rule_center_view_contract.py`（sources/scenarios 派生一致）。
  - 回归：`test_doc_flow_reconcile.py`、`test_doc_flow_transfer_doc_rules.py`、`test_demand_trace_graph.py` 保持全绿。
- **回滚方案**：
  - P0：注册表为纯新增，回滚即移除 sourcing 条目，行为回到 6 场景。
  - P1：`instrumented=false` 关闭 sourcing 场景；`attrs` 命名空间可通过开关关闭（表达式解析不到即按 missing 处理）。
  - P2：promotion 表与同步服务独立，停用不影响现有规则。

## 10. TBD 列表

| ID | 事项 | 结论 / 缺失信息 | 下一步 |
|---|---|---|---|
| TBD-001 | Sourcing 因子轴最终集合 | **已确认**：`(dest_org_id, item_id, usage, eval_date)`；库位与物料组不作因子（见 §9.3.8） | 关闭，写入契约测试 |
| TBD-002 | 跨对象 `attrs` 范围 | **已确认**：P1 根对象 + `item`；`party/org` 留 P2 评估 | 关闭，P2 立项时复评 |
| TBD-003 | `attribute_promotion` 同步方式 | **已确认**：一次性 cutover + 回填期可选 write-through，不做长期双写（见 §9.3.8） | 关闭，P2 按状态机实现 |
| TBD-004 | sourcing `explain` 稳定性 | **已确认**：冻结 `explain_version=1` + 固定阶段与原因码枚举 | 关闭，随 P1 adapter 落契约测试 |
| TBD-005 | 多源分摊 / 配额能力 | 未决：Fusion allocation % 与 SAP 配额比率语义，不同于 `allocation_pct` 计划提示 | 单独立项，本轮不实现 |
