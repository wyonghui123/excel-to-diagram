# Spec: 规则模型场景化与扩展属性接入（Sourcing / Extended Attributes）

> 本文是 [2026-11-07-rule-convergence-spec.md](./2026-11-07-rule-convergence-spec.md) §12（语义模型）与 §13（元数据驱动与单一事实源）的**细化补充**，不修改、不替代原文。
> 范围：①Sourcing 作为规则场景接入；②扩展属性（物料/组织/客商等）接入规则模型；③场景因子轴声明与 trace 输入快照契约；④分级路线图与验收标准；⑤单据流多 BO 节点与编排层的对齐结论（仅研究结论，不实施）。

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
| 功能需求 | 是 | §3 FR-001 ~ FR-013 |
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

### FR-013: 单据节点组只读派生

- **Description**: 系统 MUST 从 BO YAML `child_sections` + 现有 `doc_flow_rule` 派生单据节点组，并在规则目录与 `doc_flow` trace 中以只读增量字段暴露；MUST NOT 新增规则表字段、`RuleType`、API 路由或改变下推/边写入。
- **Acceptance Criteria**:
  - `sales_order` 组含 `sales_order/header`、`sales_order_line/line`、`sales_order_schedule/schedule`，父键均为 `order_id`。
  - `shipment` 组含 `shipment/header`、`shipment_line/line`，父键取 `delivery_id`（`hierarchy.parent_field` 优先于字段名推断）。
  - `sales_order_schedule → shipment_line` 归入 SO 组 `outbound` 与 shipment 组 `inbound`，`target_group=shipment`。
  - 父键无法解析时组标 `degraded=true` 并给原因，接口不报错。
  - 目录 `detail.node_group` 与 trace `detail.node_group` 为增量字段；`decision`、`reason`、`detail.rules` 与现有测试一致。
- **Priority**: Should
- **Source**: §9.3.9 / §9.3.10 / TBD-006

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
- **Measurement**: 新增测试文件至少覆盖 FR-001/002/003/005/006/007/008/010/013。
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
| FR-013 | 单据节点组只读派生 | Should | 让头/行/计划行在目录与 trace 可见，不改写入 |

- 里程碑：
  - M1（P0，契约先行）：FR-001/002（仅登记 NOT_INSTRUMENTED）/003/004/010，零行为变更。
  - M2（P1，接入）：FR-005/006/007/008/011，配套契约与单测。
  - M3（P2，治理）：FR-009/012，promotion 落表与影响面分析。
  - M4（只读增量）：FR-013，模块 + 目录/trace 增量字段 + 契约测试，不改表、不改枚举、不改写入。
- 范围说明：M1-M3 不含单据流多节点与编排层实现；M4 仅实现 TBD-006 的只读派生，TBD-007（头级/计划行级边）与 TBD-008（编排层）不在范围。

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


#### 9.3.9 单据流多 BO 节点与编排层（2026-11-09 补充）

**问题界定**：`doc_flow_rule` 的粒度是「单源 BO → 单目标 BO」的原子边，但业务上的"一次下推"通常生成一组 BO 节点。以 SO 为例，头/行/计划行是三个独立 BO：`sales_order`（头）、`sales_order_line`（行）、`sales_order_schedule`（计划行），由 YAML `child_sections` 挂接；下游交货同样是 `shipment`（头）+ `shipment_line`（行）。当前存量规则全部登记为行级 BO 对，规则只描述"哪条行生成哪条行"，头节点由服务自行创建，规则模型不感知。

| 业务动作 | 实际生成的节点集合 | 现有规则边 |
|---|---|---|
| SO → 交货 | `shipment` 头 + `shipment_line` 行 | `sales_order_schedule → shipment_line` |
| 调拨单 → 调拨发货 | `transfer_shipment` 头 + `transfer_shipment_line` 行 | `transfer_order_line → transfer_shipment_line` |
| 调拨单 → 收货 | `receipt` 头 + `receipt_line` 行 | `transfer_order_line → receipt_line` |
| 采购申请 → 采购订单 | `purchase_order` 头 + `purchase_order_line` 行 + `demand_allocation` 行 | `requisition_line → purchase_order_line` |

引擎侧只有两种形态：平铺行级边（`target_bo` 即行 BO）与两级模式（`target_line_bo + head_fk_field`，边写 `target_bo=头 BO / target_item=行 ID`）。两级模式仍以单个源 BO 为输入，`split_key` 只从源行读取字段，头字段只能来自分单键分组与运行时 `head_overrides`，没有持久化的头级字段映射；两种模式的边形态不一致，消费方需按 `target_line_bo` 分支处理。

**对标结论**：

| 维度 | SAP SD | Oracle Fusion OM | 本平台现状 |
|---|---|---|---|
| 表达粒度 | 单据类型对（`VTAA/VTLA/VTFA/VTFL/VTAF/VTFF`）+ Header / Item / Schedule 三级配置 | 销售订单头行 + 履行行 + 每条订单行一个编排流程实例 | 行级 BO 对原子边 |
| 复制内容 | copying requirements + data transfer routines（VOFM）+ switches | assignment rules → process definition → task/service | `field_map / copied_fields / check_hook / map_hook / create_hook` |
| 单据流记录 | `VBFA` 单独记录 item 级前驱后继与数量（`VBELV/POSNV → VBELN/POSNN`、`RFMNG`） | `DOO_DOCUMENT_REFERENCES` 记录 doc / line / subline 多粒度引用 | `doc_flow_edges` + `consumed_qty`，只到行级 |
| 拆分/合并 | delivery split（ship-to / shipping point / route / date） | fulfillment line split（`SPLIT_FROM_FLINE_ID`、split priority、shipment set） | `split_key` 建头，无运行时血缘 |
| 变更处理 | 单据流更新 + completion rule（部分引用/已完成） | processing constraints → `Change Pending` → 补偿（Undo/Redo/Update/Cancel/None） | 无编排层，红冲另立 |
| 规则与流程关系 | copy control 只管创建时复制，单据流由 `VBFA` 独立记录 | 规则（assignment）与流程（orchestration）分离 | 规则与下推服务耦合 |

**结论**：

1. 多 BO 不是"规则对象粒度"问题，而是三层职责问题。`doc_flow_rule` SHOULD 保持"单源 BO → 单目标 BO"的原子边，不扩展为 `sources[] / targets[]`；节点组合、执行顺序、流程状态不属于规则表。此原则与 §9.3.8 一致：规则保持原子，扩展能力由独立层承载。
2. L1 单据节点层（node group）：声明"一次下推生成哪些节点、各节点的头/行/计划行角色与父子外键"。优先只读派生：由 BO YAML `child_sections` + 现有 `doc_flow_rule` 推导，不新增表、不改枚举；目录与 trace 以节点组为展示单位。派生结果需闭合校验（每个节点组内至少一条边、外键可解析）。
3. L2 边规则层：保留行级边；头级字段映射与计划行级边在出现第二个真实需求时再补。头级映射优先复用 `head_fk_field` 与运行时 `head_overrides`，不足时再评估持久化 `head_field_map`；不新增 `RuleType`。
4. L3 编排层（远期，TBD-008）：Fusion 的编排单元是履行行而非单据头，包含流程模板、任务/服务、等待与提前期、错误处理、变更补偿。本平台当前无跨系统履约与补偿需求，不复制该模型；若立项，作为独立运行时与 `doc_flow` 并列，不塞进规则表。
5. 可观测性：`rule_trace_service` 的 doc_flow 场景目前只按 `source_bo == object_type` 匹配，SO 头 trace 看不到子 BO 的声明；`rule_catalog_service` 的 doc_flow 条目也只有平铺规则。建议在只读层补 `nodes[]`（节点组）与 `edges[]`，trace 信封形状不变。

**明确不做**：

- 不把 `doc_flow_rule` 改成多对象规则；
- 不引入 BPMN / 通用工作流引擎表达单据流；
- 不在本轮实现编排层（assignment rules、process instance、task status、compensation）。

**代码依据**：`doc_flow_rule_store.py`（列契约）、`doc_flow_batch_engine.py`（两级模式与 `split_key` 读取源行）、`doc_flow_derive_engine.py`（两级边形态）、`shipment_service.py` / `transfer_shipment_service.py` / `receipt_service.py` / `requisition_po_conversion.py`（头 + 行 + 逐行 attach）、`rule_trace_service.py` / `rule_catalog_service.py`（doc_flow 只按源 BO 平铺）。

#### 9.3.10 单据节点组只读派生（M4 实现设计）

**目标**：让目录与 trace 能回答"这张单据由哪些节点组成、它的上下游边属于哪些单据"，不改规则表、不新增 `RuleType`、不改变下推与边写入。

**单一事实约束**：本方案不新增事实表。父子关系只来自 YAML 元数据（`child_sections` / `hierarchy` / `ui.relation`），边只来自 `doc_flow_rule`；节点组是二者的只读投影（join），不落库、不缓存、不参与写入，也不引入第二份 BO 清单。

**新增模块**：`meta/core/doc_flow_node_groups.py`（纯读、无副作用）。

**输入**：
- `registry.get_all()` 的 `MetaObject`：`ui_view_config.child_sections`、`hierarchy.parent_field`、字段 `ui.relation`。
- `rule_provider.list_doc_flow_rules(data_source)` 的规则列表。

**派生算法**（确定性，按顺序执行）：
1. 候选头 BO：`child_sections` 非空，且头或其子 BO 出现在任一 `doc_flow_rule` 的 `source_bo/target_bo` 中。
2. 节点角色：优先读 `child_sections[].role` 显式声明；未声明时头 = `header`，子 BO 以 `_schedule` 结尾 = `schedule`，其余 = `line`（命名回落只作兼容，不写回元数据）。
3. 子节点父键：优先 `child.hierarchy.parent_field`；否则取 `child.fields` 中 `ui.relation == header_bo` 的字段；否则取子表中实际存在的 `<header_bo>_id` 字段；全部失败则节点组 `degraded=true`，原因 `parent_fk_unresolved`。
4. 组归属：若子 BO 自身也是候选头（如 `project → sales_order`），不放入 `nodes`，放入 `subflows`，避免同一 BO 同时以"行"和"头"身份重复出现；一个 BO 只能出现在一个 `nodes` 中，冲突时记 `ambiguous`。
5. 边归组：`source_bo` 属于组内节点 → `outbound`；`target_bo` 属于组内节点 → `inbound`；对端不在任何组时保留 BO 名、`target_group`/`source_group` 为空。边只取 `status='active'`。
6. 已知边界：`demand_allocation` 等无 `child_sections` 的多态表不进入节点组，单列 `unmodeled_bo`；需要时由 TBD-007 补声明。

**数据结构**（键顺序稳定，便于契约测试）：

```json
{
  "group_id": "sales_order",
  "header_bo": "sales_order",
  "nodes": [
    {"bo": "sales_order", "role": "header", "parent_fk": ""},
    {"bo": "sales_order_line", "role": "line", "parent_fk": "order_id"},
    {"bo": "sales_order_schedule", "role": "schedule", "parent_fk": "order_id"}
  ],
  "subflows": [],
  "outbound": [
    {"rule_id": "so_schedule_to_shipment_line", "source_bo": "sales_order_schedule",
     "target_bo": "shipment_line", "target_group": "shipment"}
  ],
  "inbound": [],
  "degraded": false,
  "reasons": [],
  "unmodeled_bo": []
}
```

**集成点**：
- `rule_catalog_service._doc_flow_descriptors`：每次调用只计算一次节点组，附加到每条 doc_flow 描述符的 `detail.node_group`；现有 `rule_key/factors/detail` 键不变。
- `rule_trace_service._doc_flow`：按 `object_type` 找到所属组（头或子节点），在 `detail.node_group` 附加 `group_id / node_role / nodes / outbound / inbound / degraded`；`decision`、`reason`、`detail.rules` 保持原逻辑，旧断言不受影响。
- 不新增 API 路由；目录外层不加 `groups` 汇总，避免前端契约变更。
- P0 只提供 API 增量字段；界面展示必须在 `rule_center_view.yaml` 声明 section/widget，前端不得写死节点组（`WIDGETS` 仍为封闭枚举，新增图形化 widget 属独立变更）。

**错误与性能**：
- 单个 BO 派生失败只降级该组，写日志并置 `degraded`，不向 API 抛 500。
- P0 不引入跨请求缓存（`child_sections` 与规则规模小）；若 trace 出现热点，再按规则 `updated_at` 做进程级缓存。

#### 9.3.11 TBD-007 细化：头级 / 计划行级边（2026-11-09）

**现状核查**（worktree DB + 代码）：
- `doc_flow_rule` 现有 8 条 active 规则全部为平铺行级边，`target_line_bo` 全为空；两级模式（`target_line_bo + head_fk_field`）只存在于引擎与测试，无生产规则。
- 真实单据头由业务服务创建（`shipment_service` / `transfer_shipment_service` / 收货 / 采购服务），头字段多为业务快照（地址、承运商、库位、日期），不是规则字段复制。
- 通用入口 `DocFlowService.derive` 在 `mode=create` 时 `head_overrides=None`，两级建头只能得到「split_key 自动映射 + 常量覆盖」；required 头字段若不在 split_key，通用建单无法满足。

**需求分拆**：三个问题不能混为一谈。

| 子问题 | 现状 | 建议 |
|---|---|---|
| 头级边（头 → 头） | 无；边只到行 / 计划行 | **不新增**。头级关系由 M4 节点组 + 行级边 rollup 只读派生；写入头级边会形成第二事实源 |
| 计划行级边 | 已可表达（`sales_order_schedule → shipment_line`） | **不新增角色列**。`schedule` 角色由 YAML 派生（M4）；如需展示标签，放 catalog 只读字段 `source_role` |
| 头字段映射 | 依赖 split_key + head_overrides（运行时） | **两阶段**：P0 明确契约；触发后新增 `head_field_map` |

**P0（现在，零 DDL）**：
1. 规则目录增加只读 `detail.header_contract`：`mode`（`flat` / `rule_headed` / `service_headed`）、`split_key`、`required_missing`（目标头 YAML required 字段减去 split_key）、`service_owned_fields`（头快照 / 业务服务写入字段，仅提示）。
2. 建单契约冻结：`rule_headed` 规则的头字段来源顺序 = `head_overrides`（运行时）> split_key 自动映射；required 字段未覆盖时，目录标记 `degraded=true` 并给 `header_field_uncovered`，不阻断既有服务建单。
3. 计划行边继续用 BO 名表达，节点组负责角色解释；trace 的 `detail.node_group.node_role` 已可区分 `schedule`。

**P1（触发条件满足后，新增 1 列）**：
- 触发条件（任一）：① 出现第二条需要规则建头的 BO 对，且头必填字段不在 split_key；② 通用界面开始创建真实单据（非 demo）；③ 同一 split_key 混入「只复制、不分组」的字段，拆单粒度被污染。
- 设计：`doc_flow_rule.head_field_map TEXT NOT NULL DEFAULT '{}'`，JSON `{target_field_id: source_field_id}`；常量仍走运行时 `head_overrides`，不落规则（避免主数据快照进规则）。
- 解析顺序：`head_overrides` > `head_field_map` > split_key 自动映射；attach 模式（`head_overrides.id`）忽略 `head_field_map`，不改既有头。
- 取值口径：按组内首行取值（与现有 split_key 建头一致）；组内多行该字段值不同时首行胜出，并在结果 `head_field_conflicts[]` 记录，不静默。
- 校验：保存规则时校验源字段存在、目标头字段存在、类型兼容；失败 `HEAD_FIELD_MAP_INVALID`。`field_map` 仍只作用于行级复制。
- 迁移：幂等加列（沿用 `_ADDED_COLUMNS` 模式），`app.yaml` upsert 声明列，无回填。
- 不采用：`create_hook`（Python 钩子，破坏元数据驱动，仅在跨系统复杂快照时单独立项）；把 `head_field_map` 塞进 `field_map` 命名空间（语义重载，消费方需二次解析）。

**验收**：
- 两级规则 + `head_field_map` 建头：映射字段来自首行；attach 模式不改头；缺字段报 `HEAD_FIELD_MAP_INVALID`；多行冲突进 `head_field_conflicts`。
- 头级 trace：不产生头级边，`doc_flow_edges` 行数不变；节点组 `outbound` 仍按规则列出。
- 计划行：`so_schedule_to_shipment_line` 的 catalog `source_role=schedule`，边与下推行为不变。

#### 9.3.12 TBD-008 细化：编排层（orchestration）

**对标要点**（Fusion / SAP）：
- Fusion：编排单元是**履行行**（fulfillment line），每条订单行一个 orchestration process 实例；流程定义由任务 / 服务 + 依赖组成；assignment rules 选流程；变更走 processing constraints → `Change Pending` → 补偿动作 `Undo/Redo/Update/Cancel/None`；拆分行用 `SPLIT_FROM_FLINE_ID` 保留血缘。
- SAP：copy control 只管**创建时复制**，运行期单据流由 `VBFA` 独立记录；没有等价的编排 / 补偿运行时。
- 结论：编排不是 copy control 的扩展，而是**独立的履约运行时**；平台已用 Gen2 任务 / 工作流域建成该运行时（见下），因此不塞进规则表、也不另造一套。

**已有底座（2026-09-07 任务模型设计 + 2026-10-30 两代收口）**：

| 层 | 已有对象 / 模块 | 已覆盖能力 |
|---|---|---|
| 定义层 | `workflows` + [workflow_definition.py](file:///d:/filework/doc-flow-worktree/meta/core/workflow_definition.py#L1-L18) + `workflow_store.publish_workflow()` | 版本化定义、发布期校验；**主干 + 单亲分支块（明确非通用 DAG，对齐 Oracle 最小充分集）** |
| 实例层 | `workflow_runs` + [workflow_engine.py](file:///d:/filework/doc-flow-worktree/meta/core/workflow_engine.py#L1-L25) | `start_run` 定义快照 / 任务克隆、`advance_run` 依赖求值、`run_progress` 进度派生（Run 无状态列） |
| 执行层 | `tasks` + `task_state_machine` + `task_event_schema` | 11 态、`executor_type`（human / agent / system / cron / webhook）、retry / timeout / SLA、`doc_ref` / `line_refs`、幂等 |
| 补偿 | `workflow_engine.compensate_task()` | 新建补偿任务 + `bo_action` 声明，对齐 Oracle `REFERENCE_STEP_INSTANCE_ID`；业务红字执行委托 [doc_flow_reversal.py](file:///d:/filework/doc-flow-worktree/meta/core/doc_flow_reversal.py)（E6 三档冲销） |
| 触发 | `workflow_trigger`（manual / schedule / event / api）+ `workflow_schedule_scheduler` | 事件、定时、手动、API 四种起 Run 方式 |
| 边界铁律 | [任务模型设计 §17.1–§17.3](file:///d:/filework/docs/superpowers/specs/2026-09-07-task-model-design.md#L1166-L1207) | 单据流不进任务域；边只经 BO Action 创建；不删边；边表不知道任务引擎存在 |

Gen2 六表（`tasks` / `task_templates` / `workflows` / `workflow_runs` / `task_events` / `task_worklogs`）已由 [两代收口 spec](file:///d:/filework/doc-flow-worktree/docs/specs/task-two-generation-convergence/spec.md#L88-L99) 定为 Task/Orchestration Domain 的目标形态，并有 `test_workflow_engine.py` / `test_workflow_definition.py` / `test_workflow_trigger.py` 覆盖。

**结论修正**：TBD-008 不是「新建 L3 运行时」，而是**复用 Gen2 任务 / 编排域，只补接缝**。原方案中的 `process_definition / process_instance / process_step / process_event` 与既有 `workflows / workflow_runs / tasks / task_events` 语义重复，撤回。

**接缝清单**（按需实施，不新增表）：
1. **`create_document` executor**：在现有 `executor_type` 体系增加 `bo_action`（或 `system` + `config.action_id=derive`），内部调用 `derive_batch`；幂等键 `(run_id, node_id)`；遵守决策-生效协议（任务库与业务库不同库，不能同事务）。
2. **outputs → inputs 注入**：`workflow_engine` 已显式标注未实现；补 edge 模板 `{{node.outputs.field}}`，只做 DAG 内数据流，不碰任务状态。
3. **补偿适配**：`compensate_task()` 的 `bo_action` 落到 E6 三档冲销；不复制数量语义，不新建补偿表。
4. **事件触发接线**：`doc_flow.created` / `bo.status_changed` → `workflow_trigger(kind=event)` 起 Run；一期按目标单头建实例，二期如需按履行行用 `tasks.line_refs` 关联。
5. **trace 分工**：编排状态查 `workflow_runs` / `tasks` / `task_events`；`doc_flow` trace 不混入流程状态。

**何时启动接线**（满足任一，且业务方确认）：
1. 需要对接外部履约系统（WMS / TMS / OMS）并等待回调；
2. 需要异步任务、重试、超时、死信；
3. 出现数量冲销无法覆盖的补偿（状态回退、外部取消、部分重放）；
4. 需要按履行行跟踪多步骤状态与拆单血缘；
5. 出现跨单据的审批 / 履约状态机。

启动顺序：先接 1 + 3 + 4（创建、补偿、触发），再按需做 2（数据流）。

**方案对比**：

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| 规则表加流程状态 | 单表简单 | 规则与运行态混存、版本与幂等难治理 | 拒绝 |
| 通用 BPMN 引擎 | 表达力强 | 语义溢出、运维成本高 | 拒绝 |
| 新建独立 L3 运行时（原建议） | 与规则分层 | 与 Gen2 四表重复，等于重造已建成的任务域 | **撤回** |
| 复用 Gen2 + 补接缝（本建议） | 单一事实源、已有测试与状态机、增量接线 | 需补 executor / outputs / 补偿适配 | **选中** |

#### 9.3.13 五接缝实现步骤（M5 预案，按需启用）

**总原则**：不新增编排表；全部落在既有 Gen2 任务/工作流域 + `doc_flow`。实施顺序 **S1 → S3 → S4 → S2 → S5**（S1/S3 可并行；S2 依赖 S1 的 outputs；S4 依赖 S1 的 action）。

##### S1 `create_document` executor

**目标**：Workflow 节点可创建单据，幂等、可重试、可观测。

**现状**：
- [bo_action_executor.py](file:///d:/filework/doc-flow-worktree/meta/core/bo_action_executor.py#L279-L289) 已支持 `system` 任务：参数取 `task.inputs`，调用 `registry.call(action_id, inputs, context)`，context 带 `run_as/task_id/workflow_run_id/trace_id`；幂等键 `{run_id}:{task_id}:{attempt}`。
- 尚无 `doc_flow.*` BO Action；`start_run` 创建任务时 `inputs` 置 NULL（[workflow_engine.py](file:///d:/filework/doc-flow-worktree/meta/core/workflow_engine.py#L208-L238)）。

**步骤**：
1. **服务单例下沉**：把 `init_doc_flow_service()` / `_require_service()` 从 [doc_flow_api.py](file:///d:/filework/doc-flow-worktree/meta/api/doc_flow_api.py#L26-L41) 移到 `meta/services/doc_flow_service.py`（模块级 `init/get`）；API 与 action handler 共用，避免 service 反向 import API；同步更新 `meta/tests/test_doc_flow_api.py` 的导入。
2. **新增 `meta/services/doc_flow_action.py`**：
   - `doc_flow_derive_handler(params, context)`：取 `context['run_as']` 作 `derived_by`；调用 [DocFlowService.derive()](file:///d:/filework/doc-flow-worktree/meta/services/doc_flow_service.py#L229-L310) 或批量 [derive_batch()](file:///d:/filework/doc-flow-worktree/meta/core/doc_flow_batch_engine.py#L161)。
   - 入参：`rule_id`、`sources`（源单 id 列表）、`target`（`{mode, id?, data?}`）、`head_overrides`。
   - 返回：`{success, data: {created, target_ids, edge_ids}, message}`；`data` 会被 `_extract_outputs` 写入 `task.outputs`，供 S2/S3/S5 使用。
3. **注册 Action**：在 [bo_action_registrations.py](file:///d:/filework/doc-flow-worktree/meta/services/bo_action_registrations.py) 注册 `doc_flow.derive`，`idempotent=True`、`operation_type='action'`、`category='doc_flow'`、`permission_required=None`（系统任务走内部调用），并给 `input_schema`。
4. **节点契约**：`executor_type='system'`、`executor_config={"action_id":"doc_flow.derive"}`、输入模板放 `meta.inputs_template`（S2）；`publish_workflow()` 新增发布期校验：`action_id` 必须已注册，否则 `ACTION_NOT_REGISTERED`。
5. **幂等**：执行器按 `(run_id, task_id, attempt)` 去重；handler 内再由规则 `derive_key` 去重（重复调用返回 replay，不新建行）。
6. **失败归位**：业务异常返回 `{"success": False, "message": ...}` → 执行器归 `failed`，按 `retry_policy` 重试；不吞异常、不静默成功。

**测试**：`meta/tests/test_doc_flow_action_executor.py` — 成功建单并产出 `edge_ids`；同参数重放不新增；无规则报错归 failed；`trace_id` 从 context 透传。

##### S2 outputs → inputs 注入

**目标**：上游节点 outputs 能按模板注入下游 `task.inputs`，不引入表达式引擎。

**现状**：`start_run` 已把 `node.meta` 存入 `task.meta`（[workflow_store.py](file:///d:/filework/doc-flow-worktree/meta/core/workflow_store.py#L39-L44) 的 `NODE_CONTENT_FIELDS` 含 `meta`）；`advance_run()` 只改状态，不写 `inputs`（[workflow_engine.py](file:///d:/filework/doc-flow-worktree/meta/core/workflow_engine.py#L285-L320)）；outputs 已落 `task.outputs`。

**步骤**：
1. **模板语法**：节点 `meta.inputs_template`（JSON 对象），值支持整值占位 `{{run.inputs.<path>}}`、`{{<node_id>.outputs.<path>}}`；只支持点路径，不支持运算/函数。
2. **发布期校验**：`workflow_definition.validate_definition()` 增加引用校验——`<node_id>` 必须是直接上游（`incoming_edges`），路径非空；失败 `INPUT_TEMPLATE_INVALID`。
3. **注入点**：`advance_run()` 提升 `pending → ready` 的同一事务内：
   - 用已加载的 `tasks` 建 `outputs_by_task_id`；
   - 解析 `task.meta.inputs_template`；
   - 解析失败：不提升，保持 `pending`，在返回值新增 `blocked_reasons[task_id] = "INPUT_TEMPLATE_UNRESOLVED:<path>"`；
   - 解析成功：`UPDATE tasks SET inputs=?`，与状态更新同事务。
4. **首节点**：`start_run(inputs=payload)` 已存 Run inputs；首节点模板直接引用 `run.inputs`（事件触发场景由 S4 填充）。
5. **类型与幂等**：单占位保持原类型（list/dict），嵌入字符串则 `str()`；重复 `advance_run()` 只对 `pending` 生效，天然幂等。

**测试**：`meta/tests/test_workflow_inputs_injection.py` — 正常注入、缺路径阻塞、非直接上游发布失败、`run.inputs`、重复 advance 幂等。

##### S3 补偿适配

**目标**：`compensate_task()` 的 `bo_action` 真正执行 E6 冲销，而不是重放原 Action。

**现状**：`compensate_task()` 复制原任务的 `executor_type/executor_config/workflow_node_id`（[workflow_engine.py](file:///d:/filework/doc-flow-worktree/meta/core/workflow_engine.py#L458-L485)），`bo_action` 只写入 `meta`，`BOActionExecutor` 不读取 → system 补偿任务会再次执行 `doc_flow.derive`，造成重复建单。

**步骤**：
1. **改写补偿执行配置**：当 `bo_action` 非空且原 `executor_type ∈ {system, cron}` 时，补偿任务 `executor_config` 覆写为 `{"action_id": "doc_flow.reverse", "params": {...}}`；`meta.bo_action` 保留审计，不删除。
2. **扩展 `compensate_task()` 入参**（向后兼容）：新增可选 `ref_id`、`params`；`mode` 从 `bo_action` 映射：
   - `cancel` → A 档 `reverse_edge()`（[doc_flow_reversal.py](file:///d:/filework/doc-flow-worktree/meta/core/doc_flow_reversal.py#L108)）；
   - `partial` → B 档 `red_ink_edge()`（同文件 L226）；
   - `update` → C 档 `counter_edge()`（同文件 L313）；
   - `compensate` → 追加补偿 `compensate_edge()`（同文件 L391）；
   - `none` → 直接返回 `success + skipped`，只留审计。
3. **新增 handler**：`doc_flow_reverse_handler(params, context)` 调上述函数；`ref_id` 对 B/C 档必填（`REF_ID_REQUIRED`），A 档用补偿任务 id 作 `reversed_by`。
4. **注册 `doc_flow.reverse`**：与 S1 同文件注册，`idempotent=True`；B/C 档幂等由 `derive_key='rev:<edge>:<ref_id>'` 保证。
5. **幂等边界（对齐引擎原设计）**：不在 `compensate_task()` 做「同一任务只能补偿一次」的硬拦截（其 docstring 明确：业务幂等由 E6 红字单锚保证）。改为：`partial/update/compensate` 创建补偿任务时必须传 `ref_id`，否则 `WorkflowEngineError("REF_ID_REQUIRED")`；`cancel` 由 `reverse_edge()` 对同一 edge 的 replay 保证幂等；重复调用产生的新任务在 outputs 中标记 `replay=true`。
6. **边界**：补偿写业务库走 Action，任务状态在任务库，两库不同事务；失败按 `retry_policy` 重试，不硬编码回滚。

**测试**：`meta/tests/test_doc_flow_compensation_adapter.py` — A/B/C 三档、`ref_id` 缺失、重复补偿不重复建边、失败归位、`none` 不执行。

##### S4 事件触发接线

**目标**：`doc_flow.created` / `bo.status_changed` 能按 `trigger_expr` 唤起 Workflow Run。

**现状**：`start_runs_for_event()` 已存在，payload 直接成为 `run.inputs`，`doc_ref` 从 payload 字段取（[workflow_trigger.py](file:///d:/filework/doc-flow-worktree/meta/core/workflow_trigger.py#L260-L307)）；但 [event_outbox.enqueue_event()](file:///d:/filework/doc-flow-worktree/meta/core/event_outbox.py#L321-L373) 只服务有 app.yaml 的应用，平台 BO（sales / shipment）`get_app_id_for_bo()` 返回 None（[app_registry.py](file:///d:/filework/doc-flow-worktree/meta/core/app_registry.py#L125-L127)），因此当前不会发事件。

**步骤（MVP 先同步，后补持久化）**：
1. **事件契约**：`doc_flow.created`，payload `{rule_id, source_bo, source_id, target_bo, target_id, target_line_bo, row_count, trace_id}`；`trigger_expr` 的 `doc_ref` 取 `target_id`。
2. **MVP 触发**：`DocFlowService.derive()` 业务事务提交成功后，调用 `start_runs_for_event(platform_ds, event_name='doc_flow.created', payload=..., app_id='')`；异常只记录日志 + 指标，不影响业务成功。
3. **去重**：`workflow_runs` 增加 nullable `idempotency_key` + 唯一索引（幂等加列 + 迁移号 +1）；键 = `doc_flow.created:{trace_id}`；`start_runs_for_event()` 落 Run 前查/插，重复直接返回已有 Run。
4. **持久化升级**（触发：需要 at-least-once / 跨进程重试）：注册平台 core publisher contract，`enqueue_event()` 与业务写同事务；新增 core outbox consumer 调 `start_runs_for_event()`；删除 MVP 的同步调用。
5. **Workflow 定义**：`trigger_kind='event'`、`trigger_expr={"event":"doc_flow.created","when":"target_bo == 'shipment'","doc_ref":"target_id"}`；启动期由 `assert_trigger()` 校验，未知事件拒绝发布。

**测试**：`meta/tests/test_doc_flow_event_trigger.py` — 事件命中/不命中、payload→`run.inputs`、`doc_ref`、幂等键重复不起第二个 Run、触发异常不阻断 derive。

##### S5 trace 分工与关联

**目标**：两域各查各的，又能精确关联；不破坏 `doc_flow_edges` 17 列定稿。

**现状**：`doc_flow` trace 已含 `rules/edges/node_group`；任务域有 `tasks.trace_id` / `task_events`；`doc_flow_edges` 无 `trace_id` 列，`doc_flow_batch_engine` 也没有 trace 参数。

**步骤**：
1. **不改边表**：不给 `doc_flow_edges` 加 `trace_id`（17 列定稿；且 `derive_key` 是幂等键，掺 trace 会破坏重放）。
2. **用 outputs 关联**：S1 handler 的 `data.edge_ids` 写入 `task.outputs`；任务同时有 `doc_ref`（目标单 id）与 `trace_id`。查询链路 = `tasks.doc_ref/trace_id → task.outputs.edge_ids → doc_flow_edges`。
3. **trace 服务不动**：`rule_trace_service` 的 `doc_flow` 信封保持原口径，不混入 Run/Task 状态；编排状态查 `workflow_runs` / `tasks` / `task_events`。
4. **补偿链路**：S3 handler 返回 `reversed_edge_ids/created_edge_ids`，同样写 `task.outputs`，保持同一关联方式。
5. **测试**：`meta/tests/test_trace_division.py` — `doc_flow` 信封无 workflow 字段；`task.outputs.edge_ids` 与边表一致；按 `doc_ref` 可反查任务。

##### 实施顺序与验收

| 阶段 | 接缝 | 验收用例 |
|---|---|---|
| M5-1 | S1 + S3 | SO → shipment 模板 Workflow：建单成功；取消补偿只冲销一次，不重复建单 |
| M5-2 | S4 | `doc_flow.created` 命中 workflow 定义，Run 的 `inputs/doc_ref` 正确；重复事件不重复起 Run |
| M5-3 | S2 | 上游 `outputs.target_ids` 注入下游 `inputs`；缺路径保持 pending 并可观测 |
| M5-4 | S5 | 两域 trace 独立；`task.outputs.edge_ids` 可反查边，`doc_flow` 信封零变化 |

**回滚**：S1/S3 为新增 Action；S4 为新增事件与 nullable 列；S2/S5 为模板与只读关联。停用对应 Workflow 定义即可关闭编排，不影响现有 `doc_flow_rule` / `derive` API / 边表。

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. 新增 `RuleType.SOURCING` | 直观 | 枚举继续承担语义+来源+场景三重含义，违反 §12.7 | 拒绝 |
| B. 把 sourcing 塞进 control_parameter | 复用现有解析 | 因子/命中策略/候选语义不同，会造成假统一 | 拒绝 |
| C. 场景注册表 + 只读 adapter（本方案） | 正交、可闭合校验、增量上线 | 需要新增注册表与两个 adapter | 选中 |
| D. 扩展属性直接 JOIN 进业务行 | 实现快 | 产生第二事实与陈旧副本，破坏 SSOT | 拒绝 |
| E. 只用 promotion，不做 Provider | 改动最小 | 未提升的属性无法进规则，且 promotion 尚未实现 | 作为兜底，不作为唯一路径 |
| F. 独立 AttributeProvider + attrs 命名空间（本方案） | 单入口、可快照、可失效 | 需处理缓存与跨对象 N+1 | 选中 |
| G. 把 `doc_flow_rule` 扩展为多对象规则（`sources[]/targets[]`） | 一条配置表达整条链 | 规则表被迫承担节点顺序、条件与流程状态，版本与闭包难校验 | 拒绝（见 §9.3.9） |
| H. 原子边 + 节点组只读派生（本方案） | 改动小、可闭合、目录/trace 同源 | 节点组是派生视图，需闭合校验 | 选中（只读层） |
| I. 引入通用编排引擎（Fusion 式 process/task/compensation） | 表达力最强 | 当前无跨系统履约与补偿需求，成本与语义溢出 | 暂不立项（TBD-008） |

### 9.5 实施与迁移计划

- **实施顺序**：
  1. P0：新增 `rule_scenarios.py`；登记 sourcing（NOT_INSTRUMENTED）；全局因子轴改并集投影；view-config 改为派生；契约测试。
  2. P1：sourcing catalog adapter → trace adapter；AttributeProvider；`attrs` 表达式；inputs 采集与响应；缓存失效。
  3. P2：`attribute_promotion` 落表与同步；影响面分析（定义变更 → 受影响规则）；变量清单切换收尾。
  4. M4（只读增量）：`doc_flow_node_groups.py` → 目录 `detail.node_group` → trace `detail.node_group` → 契约/回归测试；不改表、不改枚举、不改写入。
- **风险与缓解**：
  - 视图元数据派生导致快照漂移 → 契约测试逐字比对；失败保留上一版快照并告警。
  - 跨对象属性 N+1 → Provider 批量化 + 请求级 memo；基准脚本纳入验收。
  - 旧 trace 无 inputs → 字段可选；回放器按存在性降级。
  - sourcing explain 结构变化 → adapter 隔离；契约测试锁定三段 stage。
  - 属性类型变更导致历史快照误读 → 快照带 `definition_version`。
  - 节点组把非单据 BO（如 `project → sales_order`）误判为行 → 候选头 + `subflows` 规则；契约测试锁定 `sales_order` 只以头身份出现。
  - 父键推断错误（`shipment_line.delivery_id`）→ 优先 `hierarchy.parent_field`，字段名推断只作兜底；组级降级不阻塞接口。
- **测试策略**：
  - 单元：`test_rule_scenarios_registry.py`（闭合校验/并集）、`test_attribute_provider.py`（missing/inactive/类型/租户/失效）、`test_rule_trace_inputs_snapshot.py`（采集/回放）。
  - 集成：`test_rule_trace_sourcing.py`（命中/未命中/无候选）、`test_rule_center_view_contract.py`（sources/scenarios 派生一致）。
  - 节点组：`test_doc_flow_node_groups.py`（SO/shipment 组、父键优先级、边归组、降级、`subflows`）。
  - 集成：`test_rule_catalog_doc_flow_nodes.py`、`test_rule_trace_doc_flow_nodes.py`（增量字段 + 旧字段不变）。
  - 回归：`test_doc_flow_reconcile.py`、`test_doc_flow_transfer_doc_rules.py`、`test_demand_trace_graph.py` 保持全绿。
- **回滚方案**：
  - P0：注册表为纯新增，回滚即移除 sourcing 条目，行为回到 6 场景。
  - P1：`instrumented=false` 关闭 sourcing 场景；`attrs` 命名空间可通过开关关闭（表达式解析不到即按 missing 处理）。
  - P2：promotion 表与同步服务独立，停用不影响现有规则。
  - M4：纯读附加字段，回滚即移除 `detail.node_group` 注入，目录/trace 恢复原响应；无数据迁移。

## 10. TBD 列表

| ID | 事项 | 结论 / 缺失信息 | 下一步 |
|---|---|---|---|
| TBD-001 | Sourcing 因子轴最终集合 | **已确认**：`(dest_org_id, item_id, usage, eval_date)`；库位与物料组不作因子（见 §9.3.8） | 关闭，写入契约测试 |
| TBD-002 | 跨对象 `attrs` 范围 | **已确认**：P1 根对象 + `item`；`party/org` 留 P2 评估 | 关闭，P2 立项时复评 |
| TBD-003 | `attribute_promotion` 同步方式 | **已确认**：一次性 cutover + 回填期可选 write-through，不做长期双写（见 §9.3.8） | 关闭，P2 按状态机实现 |
| TBD-004 | sourcing `explain` 稳定性 | **已确认**：冻结 `explain_version=1` + 固定阶段与原因码枚举 | 关闭，随 P1 adapter 落契约测试 |
| TBD-005 | 多源分摊 / 配额能力 | 未决：Fusion allocation % 与 SAP 配额比率语义，不同于 `allocation_pct` 计划提示 | 单独立项，本轮不实现 |
| TBD-006 | 单据节点组（node group）的声明归属 | **M4 已定**：只读派生（§9.3.10）；长期归属（YAML 显式声明 / 独立元数据表）仍未决 | 先落 M4；出现第二个消费方或持久化需求时再定归属 |
| TBD-007 | 头级 / 计划行级边规则表达 | **已定（阶段化）**：不新增头级边 / 角色列；P0 复用 `head_overrides` + `split_key`（零 DDL），P1 触发后新增 `head_field_map`（§9.3.11） | P0 随下一次 doc_flow 变更落 catalog 只读 `header_contract` 与校验；P1 需第二个真实需求 |
| TBD-008 | 编排层（orchestration）是否立项 | **已定：复用 Gen2 任务 / 工作流域**（`workflows` / `workflow_runs` / `tasks` / `task_events`），不新建编排层；按需补 `create_document` executor / outputs 注入 / 补偿适配（§9.3.12） | 满足触发条件后接线，不写入规则表、不新增 `process_*` 表 |
