# Spec：规则化收敛（Rule Convergence）

> 文档编号: 待定 | 状态: 执行基线 v1.3 | 日期: 2026-11-07（v1.1：TBD 决议；v1.2：官方文档二次确认；v1.3：TBD-4 关闭，进入 M1 执行）
> 主题: 把仍硬编码在 Python 中的业务规则，按「元模型 / 配置 / 代码」三层归属收敛到规则模型
> 前置: [2026-10-02 规则模型 Spec](./2026-10-02-rule-model-spec.md)、[24 · 业务对象组织边界](../spec_权限体系升级/24_org_scope_business_object_phase2.md)
> 关联: `meta/core/rule_executor.py`、`meta/core/rule_provider.py`、`meta/core/hierarchy_loader.py`

---

## 1. 背景与目标

### 1.1 背景

平台已具备规则模型骨架：`RuleType` 8 类（validation / constraint / computation / state_transition / permission / trigger / derivation / default）、`RuleProvider` 统一读取、`RuleEngine` 执行、DEFAULT 的 first-match / `FILL_IF_EMPTY` / dry-run / 可回放日志均已落地。

但当前规则存在形式是**三层载体并存**：

| 层 | 载体 | 现状 |
|---|---|---|
| L1 元模型 | BO YAML（`rules` / `doc_effect` / `org_scope` / `state_transition` / `computed` / `state_field_policies`） | 覆盖部分域，缺编号、审批、层级等 |
| L2 配置 | DB 规则表（doc_flow / approval_rule / config_rule / number_sequence / data_permission_rules） | 有表，但对象注册与绑定关系仍写在代码 |
| L3 代码 | Python 常量字典 + guard service | 约 50 处层级映射 + 多域状态图/规则号写死 |

典型证据：

- 层级/维度映射在 `permission_dimension_engine.py`、`management_dimension_engine.py`、`condition_permission_service.py`、`chain_owner_resolver.py`、`dimension_scope_engine.py`、`value_help_providers.py` 重复 6+ 份；规则模型 Spec §7A.6 已登记「5 种值形状、约 50 处」。
- `sales_order_guard_service.SCHEDULE_TRANSITIONS`、`serial_number_service.TRANSITIONS` 用 Python 字典表达状态图，而 `RuleType.STATE_TRANSITION` 已存在却未接入。
- `document_number_service.NUMBERING` 把「对象 → 编号列 / 日期列 / 序列表」写死在代码里，新增单据需要改 Python。
- `document_approval_service.APPROVAL_TABLES`、`_AMOUNT_FIELDS` 把审批对象与金额优先级写死。
- `org_scope_validator.REQUIRED_ORG_SCOPE_BOS` 用 43 项硬编码清单做一致性校验。
- `field_policy_engine.SYSTEM_FIELDS` 用常量判断系统字段。

### 1.2 业务目标

1. **单一真源**：同一业务语义只有一处声明，消除多份映射漂移。
2. **可配置**：租户可调的策略（审批阈值、单据流、组织范围）不发版即可变更。
3. **可解释**：任何拒绝/默认/流转都能给出规则来源与原因。
4. **可回归**：每次收敛都可证明「行为等价」，不引入隐性变更。

### 1.3 涉众目标

| 涉众 | 目标 |
|---|---|
| 产品/实施 | 新流程、新编号、新审批不需要研发改代码 |
| 研发 | 新增 BO/维度只改声明；减少重复常量维护 |
| 运维/审计 | 能回答「为什么这条数据被拒绝/被默认成这个值」 |

---

## 2. 需求类型总览

| 类型 | 适用 | 证据来源 |
|---|---|---|
| 业务需求 | 是 | 平台化与多产品交付需要降低发版耦合 |
| 用户/涉众需求 | 是 | 实施配置化、研发减负、审计可解释 |
| 解决方案需求 | 是 | 三层归属 + 统一 Provider + Explain |
| 功能需求 | 是 | §3 FR-001 ~ FR-013 |
| 非功能需求 | 是 | §4 NFR-001 ~ NFR-006 |
| 外部接口需求 | 是 | §5 IF-001 ~ IF-005 |
| 过渡需求 | 是 | §6 TR-001 ~ TR-004 |

---

## 3. 功能需求

### FR-001 规则载体分层判定准则

- **描述**：系统 MUST 为每类业务逻辑定义唯一归属层：L1 元模型（结构/语义/默认/校验/状态图/组织边界）、L2 配置（租户可调策略）、L3 代码（算法/安全/集成）；并形成归属矩阵。
- **验收标准**：
  - 产出「逻辑类型 → 归属层 → 载体 → 读取入口」矩阵，覆盖本次盘点 10 类候选。
  - 新增逻辑的评审清单包含「是否可声明」检查项。
  - 安全边界（认证白名单、表达式白名单、审计哈希链、事务锁、SQL/CTE）明确列入 L3，不得配置化。
- **优先级**：Must
- **类型映射**：解决方案需求
- **来源**：本次规则模型审查

### FR-002 层级/维度单一真源

- **描述**：系统 MUST 将 `RESOURCE_TABLE_MAP` / `PARENT_FIELD_MAP` / `DISPLAY_FIELD_MAP` / `CODE_FIELD_MAP` / `CHILD_TYPE_MAP` / `HIERARCHY_CHAIN` 等映射收敛为单一声明源，`hierarchy_loader` 作为唯一读取入口。
- **验收标准**：
  - `permission_dimension_engine`、`management_dimension_engine`、`condition_permission_service`、`chain_owner_resolver`、`dimension_scope_engine`、`value_help_providers` 不再各自定义同名映射。
  - 运行时映射值与旧常量逐项相等（等价性测试）。
  - 层级深度不写死：`dimension_levels` 声明 `level_type / parent_level / scope_anchor / owner_field`，`profile` 只决定默认深度（默认 4 层，完整 6 层）。
  - 数据授权只认 `scope_anchor=true` 的层级；展示层级不授予数据访问权。
  - 新增层级/维度只改声明，不改 Python。
- **优先级**：Must
- **类型映射**：解决方案需求
- **来源**：规则模型 Spec §7A.6；本次审查 P0-1

### FR-003 组织边界清单推导化

- **描述**：系统 MUST 以「扫描全部 BO 推导候选 + 显式豁免清单」替代 `REQUIRED_ORG_SCOPE_BOS` 硬编码清单；豁免项进入 YAML 并带理由。
- **验收标准**：
  - 新增 BO 未声明 `org_scope` 时，一致性测试仍能报 `ORG_SCOPE_UNDECLARED`。
  - 豁免项只能通过声明文件添加，且必须填写理由。
  - Python 中不存在 43 项对象清单。
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：本次审查 P0-2

### FR-004 状态机声明化

- **描述**：系统 MUST 先将 `sales_order_schedule` 与 `serial_number` 的状态图迁移到 BO YAML `state_transition`；guard service 仅保留副作用与跨字段复杂校验。
- **验收标准**：
  - 新旧状态图逐项等价（合法流转集合、终态、不可回退）。
  - 非法流转的错误码与用户提示保持不变。
  - 新增状态/流转只改 YAML。
  - 错误响应继续携带规则号（如 `R-SCH-9`）。
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：`sales_order_guard_service.py:251`、`serial_number_service.py:84`

### FR-005 审批注册表与金额优先级元数据化

- **描述**：系统 MUST 将 `APPROVAL_TABLES`（审批对象→表）与 `_AMOUNT_FIELDS`（金额取值优先级）改为元数据/规则表驱动。
- **验收标准**：
  - 新增审批对象零代码改动。
  - 金额字段优先级可配置，默认顺序与旧实现一致。
  - 审批规则读取统一经 RuleProvider facade（见 FR-010）。
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：`document_approval_service.py:31-39`、`v178__approval_rule_model.py`

### FR-006 单据流规则数据化

- **描述**：系统 MUST 将单据流业务规则作为数据/种子维护，迁移脚本只负责建表与基线数据，不得继续把新增业务流写进 Python 迁移。
- **验收标准**：
  - 新增一条单据流不需要发版（通过配置数据完成）。
  - `v214` / `v215` / `v222` 已承载的规则行为保持不变。
  - CI 增加静态守卫，禁止在迁移文件中新增业务流分支。
- **优先级**：Should
- **类型映射**：过渡需求 + 功能需求
- **来源**：`meta/migrations/v214/v215/v222`、`doc_flow_rule_store.py`

### FR-007 编号绑定 YAML 化

- **描述**：系统 MUST 将 `NUMBERING`（对象→编号列/日期列/序列/作用域）迁入 BO YAML `numbering` 声明；`document_number_service` 只读取声明。
- **验收标准**：
  - 5 个现有单据取号结果逐项相等（前缀、日期分段、序列来源）。
  - 新增单据只改 YAML，不改 Python。
  - 加载期校验 `no_field` / `date_field` 必须存在于 BO 字段。
- **优先级**：Must（低风险优先）
- **类型映射**：功能需求
- **来源**：`document_number_service.py:13-40`

### FR-008 系统字段策略推导

- **描述**：系统 MUST 用 `MetaField.system` 或 `field_policy` 元数据替代 `field_policy_engine.SYSTEM_FIELDS` 常量。
- **验收标准**：
  - 现有系统字段行为（隐藏/只读/必填）不变。
  - 新增系统字段不需要修改引擎代码。
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：`field_policy_engine.py:82-96`

### FR-009 业务映射常量配置化

- **描述**：系统 SHOULD 将以下映射改为 `control_parameter` 或 YAML `mappings`：税率/税务处理取值、付款条件基准日期字段、预留需求数量来源、承诺策略、采购申请行类型映射。
- **验收标准**：
  - 映射变更不需要发版。
  - 默认值与旧常量逐项相等。
  - 加载期校验 key 合法、无重复、无未知枚举。
- **优先级**：Could
- **类型映射**：功能需求
- **来源**：`tax_guard_service.py:31-34`、`payment_term_schedule_service.py:148`、`inventory_reservation_service.py:78`、`commitment_policies.py:26`、`requisition_po_conversion.py:32`

### FR-010 统一 RuleProvider facade

- **描述**：系统 MUST 扩展规则读取入口，使 YAML 规则与 DB 规则（doc_flow / approval / config_rule）对调用方透明。
- **验收标准**：
  - 业务调用方不直接 import 各域 store。
  - 新增规则载体时调用方零改动。
  - 静态守卫禁止在业务代码中直接遍历 `meta_obj.rules`（豁免清单除外）。
- **优先级**：Should
- **类型映射**：解决方案需求
- **来源**：`rule_provider.py`、`doc_flow_rule_store.py`、`permission_rule_v2_dao.py`

### FR-011 统一 explain / dry-run

- **描述**：系统 SHOULD 提供统一规则解释接口，至少覆盖：默认值（已有）、权限拒绝、状态流转拒绝、审批命中。
- **验收标准**：
  - 返回 `rule_id` / 来源载体 / 命中或拒绝原因 / 因子快照 / 耗时。
  - 解释过程不落库、不改变数据。
  - 权限与状态流转的拒绝原因可从接口获得，而不是只能查日志。
- **优先级**：Should
- **类型映射**：外部接口需求
- **来源**：DEFAULT dry-run 已落地；权限/状态机缺失

### FR-012 加载期一致性校验

- **描述**：系统 MUST 为每个规则域提供加载期校验器（仿 `org_scope_validator` V1-V6）。
- **验收标准**：
  - 编号：字段存在、序列存在、日期字段类型合法。
  - 状态机：无孤儿状态、无不可达状态、终态不可出边（除显式声明）。
  - 审批：对象/表存在、金额字段存在。
  - 映射：key 合法、无重复、无未知枚举。
  - 非法声明在启动或 CI 阶段失败，错误码稳定。
- **优先级**：Must
- **类型映射**：非功能/功能
- **来源**：`org_scope_validator.py` 已验证的模式

### FR-013 静态守卫与等价性回归

- **描述**：系统 MUST 为每次收敛提供「新旧逐项相等」的等价性测试，并增加静态守卫防止回潮。
- **验收标准**：
  - 每个迁移项都有等价性用例（运行时值 vs 旧常量），不能只依赖「测试通过」。
  - 静态守卫能拦截：新增扁平映射、重复常量、迁移中写业务流分支。
  - 统一通过 `python d:\filework\test.py` 执行。
- **优先级**：Must
- **类型映射**：非功能需求
- **来源**：规则模型 Spec §7A.6 的验证方法

---

## 4. 非功能需求

### NFR-001 行为等价

- **描述**：除显式声明的语义变更外，收敛前后运行时输出、错误码、排序、默认值必须一致。
- **度量**：每个迁移项提供逐项比对用例；差异数为 0。
- **优先级**：Must

### NFR-002 可灰度、可回滚

- **描述**：每个域支持独立开关；回滚不依赖数据回滚。
- **度量**：关闭声明即回到旧代码路径；单域回滚不影响其他域。
- **优先级**：Must

### NFR-003 性能

- **描述**：元数据在加载期解析并缓存，运行期不得重复解析 YAML；读路径不得新增 N+1 查询。
- **度量**：与基线相比，列表/详情 P95 延迟增幅 ≤ 5%；加载时间增幅 ≤ 10%。
- **优先级**：Must

### NFR-004 可解释

- **描述**：规则命中/拒绝必须能给出规则 ID、载体、原因。
- **度量**：FR-011 接口覆盖四类场景；日志可回放。
- **优先级**：Should

### NFR-005 安全边界不配置化

- **描述**：认证白名单、表达式白名单、审计哈希字段、事务/锁、SQL 生成保持代码实现。
- **度量**：代码评审清单 + 静态守卫白名单。
- **优先级**：Must

### NFR-006 可测试

- **描述**：每个新声明块必须有正例、负例、加载期校验用例。
- **度量**：新增声明块的测试覆盖率 ≥ 80%；负例覆盖主要错误码。
- **优先级**：Must

---

## 5. 外部接口需求

### IF-001 元模型声明接口

- **类型**：元模型加载
- **入口**：BO YAML 顶层新增/复用 `numbering`、`approval`，复用 `state_transition`、`org_scope`
- **交互**：`yaml_loader` 解析 → `MetaObject` 字段 → 加载期校验器
- **错误处理**：非法声明返回稳定错误码，启动/CI 失败
- **来源**：FR-004/005/007

### IF-002 规则读取 facade

- **类型**：内部 API
- **入口**：`RuleProvider.get_rules / get_enabled_rules / get_rules_by_type`
- **交互**：屏蔽 YAML 与 DB 载体差异
- **错误处理**：载体不可用时降级并告警
- **来源**：FR-010

### IF-003 规则解释接口

- **类型**：HTTP API
- **入口**：`POST /api/v2/bo/<object_type>/rules/explain`
- **请求/响应**：请求含动作/字段/因子快照；响应含 `rule_id`、载体、命中、原因、值、耗时
- **错误处理**：不落库；对象/动作非法返回 400
- **来源**：FR-011

### IF-004 管理端配置界面（二期）

- **类型**：UI
- **入口**：规则管理页
- **交互**：查看/编辑 L2 规则，查看 L1 只读
- **错误处理**：冲突与非法值即时校验
- **来源**：平台化目标

### IF-005 迁移与校验命令

- **类型**：CLI / 测试入口
- **入口**：迁移脚本 `migrate / verify / rollback`；测试 `python d:\filework\test.py`
- **交互**：幂等；支持 dry-run
- **错误处理**：失败回滚事务
- **来源**：FR-012/013

---

## 6. 过渡需求

### TR-001 分波次切换

- **描述**：按 M1（低风险）→ M2（流程）→ M3（权限层级）分波次，每波独立验收。
- **策略**：每波先只读双跑，再切换读取入口。
- **回滚**：单域开关关闭即回旧路径。

### TR-002 影子读取与双跑

- **描述**：切换前同时计算旧常量与声明结果，差异写告警日志。
- **策略**：至少运行一个回归周期，差异为 0 后切换。
- **回滚**：停止影子读取即可。

### TR-003 兼容期

- **描述**：旧常量保留一个版本作为 fallback，声明缺失时回退并告警。
- **策略**：fallback 只读、不写；下个版本删除。
- **回滚**：恢复旧读取入口。

### TR-004 数据不变

- **描述**：本次收敛不修改业务数据、不删列、不改索引。
- **策略**：只改读取与校验路径。
- **回滚**：无需数据回滚。

---

## 7. 约束与假设

### 7.1 技术约束

- 复用现有 `RuleType` 8 类，不新增规则类型（状态图用 `STATE_TRANSITION`）。
- 元数据在加载期完成解析与校验，运行期零 YAML 解析。
- 数据库为 SQLite，规则表变更走迁移；禁止直读写 `meta/architecture.db`。
- 测试唯一入口为 `python d:\filework\test.py`。

### 7.2 业务约束

- 安全边界不配置化。
- 不改变现有 API 契约与前端路由。
- 不在本轮引入规则在线热更新与多租户隔离。

### 7.3 假设

- 假设 1：现有常量即为当前正确行为（已由测试与线上行为验证）——来源：已验证。
- 假设 2（已定，TBD-4）：4 层与 6 层不是二选一。层级深度由 `dimension_levels` 声明，默认 profile=4；授权只认 `scope_anchor` 层级。已确认保持现状：`sub_domain` 为授权叶子，`service_module` 不升锚点。
- 假设 3（已定，TBD-2/TBD-3）：状态主图与编号绑定放 L1；租户可配的仅限原因/子状态/门槛与编号区间参数。

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|---|---|---|---|
| FR-001 | 分层判定准则 | Must | 后续所有工作的判据 |
| FR-002 | 层级/维度 SSOT | Must | 重复最多、漂移风险最高 |
| FR-003 | 组织清单推导化 | Should | 影响面小，但防止新增 BO 漏配 |
| FR-004 | 状态机声明化 | Must | 规则类型已具备，收益直接 |
| FR-005 | 审批注册表元数据化 | Should | 减少发版耦合 |
| FR-006 | 单据流数据化 | Should | 已有 store，只差约束 |
| FR-007 | 编号 YAML 化 | Must | 低风险、可作试点 |
| FR-008 | 系统字段推导 | Should | 减少引擎分支 |
| FR-009 | 业务映射配置化 | Could | 收益分散，后置 |
| FR-010 | 统一 Provider | Should | 平台化关键接缝 |
| FR-011 | 统一 explain | Should | 排障与可解释 |
| FR-012 | 加载期校验 | Must | 防止声明漂移 |
| FR-013 | 等价性回归与守卫 | Must | 保证不回归 |

**里程碑**

- M1（低风险试点）：FR-007、FR-008、FR-009、FR-013
- M2（流程域）：FR-004、FR-005、FR-006、FR-012
- M3（权限/平台域）：FR-002、FR-003、FR-010、FR-011

---

## 9. 变更/设计方案（RFC）

### 9.1 现状分析（As-Is）

| # | 位置 | 硬编码内容 | 目标载体 | 难度 | 风险 |
|---|---|---|---|---|---|
| 1 | `permission_dimension_engine.py:45-100` 等 6 处 | 对象→表/父外键/显示列/子类型 | L1 层级声明 | 高 | 高（权限语义） |
| 2 | `org_scope_validator.py:21` | 43 项组织边界清单 | L1 豁免声明 + 推导 | 低 | 低 |
| 3 | `field_policy_engine.py:82-96` | `SYSTEM_FIELDS` | L1 字段元数据 | 低 | 低 |
| 4 | `sales_order_guard_service.py:251`、`serial_number_service.py:84` | 状态图 + 规则号 | L1 `state_transition` | 中 | 中 |
| 5 | `document_approval_service.py:31-39` | 审批对象表、金额优先级 | L1/L2 审批规则 | 中 | 中 |
| 6 | `v214/v215/v222` 迁移 | 单据流业务分支 | L2 doc_flow 数据 | 中 | 中 |
| 7 | `document_number_service.py:13-40` | 编号绑定 | L1 `numbering` | 低 | 低 |
| 8 | `tax_guard_service.py:31` 等 5 处 | 业务映射常量 | L2 参数/映射 | 低 | 低 |
| 9 | `rule_provider.py` + 各域 store | 读取入口分散 | 统一 facade | 中 | 中 |
| 10 | DEFAULT 之外无 explain | 只能查日志 | 统一 explain | 中 | 低 |

### 9.2 目标态（Target）

```text
L1 元模型（随产品版本，Git 管理）
  BO YAML: rules / computed / validation / state_transition / org_scope / numbering / approval
  层级声明: dimension_levels（level_type / parent_level / scope_anchor / owner_field）
        ↓ 加载期解析 + 校验（V1-Vn）
L2 配置（租户可改，DB 规则表）
  data_permission_rules / doc_flow_rules / approval_rules / config_rules / number_sequence / control_parameter
        ↓
RuleProvider（唯一读取入口，屏蔽载体差异）
        ↓
RuleEngine（8 类型执行）+ Domain Services（只保留算法/副作用）
        ↓
ExplainService（默认/权限/状态/审批统一解释）
```

### 9.3 详细设计

**模块职责**

| 模块 | 职责 |
|---|---|
| `yaml_loader` | 解析新声明块，构造 `MetaObject` 字段 |
| 各域 validator | 加载期校验，稳定错误码 |
| `RuleProvider` | 统一取规则（YAML + DB） |
| `RuleEngine` | 执行 default/validation/computation |
| 域服务 | 只保留副作用、跨对象算法、复杂校验 |
| `ExplainService` | 统一解释与 dry-run |

**数据模型**

- `dimension_levels`（L1，独立声明文件）：`{level_type, parent_level, scope_anchor, owner_field, profile}`；`profile=4` 为当前行为，`profile=full` 含 `service_module / business_object`。
- `MetaObject.numbering: Dict`：`{field, date_field, sequence_code, scope_bo, fallback_sequence_code, gapless}`。
- `MetaObject.approval: Dict`：`{enabled, table, amount_fields, rule_set}`。
- 复用 `MetaObject.state_transitions`、`MetaObject.org_scope`、`MetaObject.rules`。
- L2 规则表沿用现有表，不新增重复表。

**主流程**

1. 加载：YAML → MetaObject → 各域 validator → 缓存。
2. 读取：调用方 → RuleProvider → 规则列表。
3. 执行：RuleEngine / 域服务。
4. 解释：ExplainService 读取同一 Provider 与因子快照，输出原因。

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A 全部 YAML | 单一真源、版本可追溯 | 租户不可改、发版耦合 | 否 |
| B 全部 DB | 租户可配 | 结构语义不可版本化、测试困难 | 否 |
| C 分层归属（本方案） | 各取所长 | 需要判定准则与 Provider | **选中** |
| D 维持现状 | 零成本 | 漂移持续、发版耦合 | 否 |

### 9.5 实施与迁移计划

**本轮范围**：仅 M1（TBD-1 决议）；M2、M3 以独立变更单推进。

**实施顺序**

1. M1：FR-007 编号 → FR-008 系统字段 → FR-009 映射 → FR-013 守卫。
2. M2：FR-004 状态机试点 → FR-005 审批 → FR-006 单据流 → FR-012 校验。
3. M3：FR-002 层级 SSOT（影子双跑）→ FR-003 组织清单 → FR-010 Provider → FR-011 Explain。

**风险与缓解**

| 风险 | 缓解 |
|---|---|
| 层级 SSOT 改变权限语义 | 只读双跑 + 逐项等价 + 独立开关 |
| 状态机迁移改变错误码 | 错误码与文案回归用例 |
| 编号迁移导致重复/跳号 | 事务外取号约束不变 + 取号结果比对 |
| 规则载体分散回潮 | 静态守卫 + 评审清单 |

**测试策略**

- 单元：validator 正/负例、Provider 载体透明、映射等价。
- 集成：列表/详情/保存/流转/审批链路。
- E2E：权限可见性、状态流转拒绝、编号生成。
- 全部经 `python d:\filework\test.py`。

**回滚方案**

- 每域独立开关；关闭即回旧代码路径。
- 旧常量保留一个版本作为 fallback。
- 不涉及数据回滚。

---

## 10. TBD 决议

> 决议日期：2026-11-07。对标依据：Oracle Fusion、SAP S/4HANA / Solution Manager、Workday、ServiceNow CSDM、Microsoft Dynamics 365、NetSuite、LeanIX 的公开产品机制。

### 10.1 决议表

| ID | 事项 | 决议 | 判定依据 | 状态 |
|---|---|---|---|---|
| TBD-1 | 本轮实施范围 | 仅 M1（编号 / 系统字段 / 映射 / 等价性守卫）；M2、M3 另立变更单 | 载体迁移与语义变化必须解耦，否则回归不可定位；Oracle Sandbox 亦按对象分批发布 | 已定 |
| TBD-2 | 状态机载体 | L1 声明主状态图与终态；L2 只允许原因码 / 子状态 / 动作门槛，不得新增主状态 | Dynamics `statecode` 固定 + `statuscode` 可配；SAP 系统状态固定 + 用户状态附加 | 已定 |
| TBD-3 | 编号载体 | L1 声明绑定（field / scope_bo / date_field / sequence_code / gapless）；L2 只配前缀、补零、区间、重置策略、起始值 | SAP SNRO 号码范围对象由产品定义、区间由客户维护；D365 编号序列按法人 | 已定 |
| TBD-4 | 层级口径 | 4 层与 6 层并存：`dimension_levels` 声明层级类型与深度，`scope_anchor` 单独标记可授权层级；默认 profile=4 | Workday Functional Area / Domain / Business Process 三轴分离；ServiceNow CSDM 按关注点分层；SAP SolMan 组织单元 / 主数据 / 业务流程三正交 | 已定：保持现状，`sub_domain` 仍为授权叶子，`service_module` 不升第 5 锚点 |
| TBD-5 | 等价性边界 | 错误码、HTTP 状态、放行/拒绝结论冻结；日志与文案可改，但 i18n key 稳定 | Oracle / SAP 均为 message class + message number 稳定、文本可翻译 | 已定 |
| TBD-6 | 审批注册表 | 结构放 L1（对象→表、金额字段优先级、开关、默认规则集）；策略放 L2（条件、步骤、金额段、审批人、生效期）；L2 不存表名 | Oracle BPM 策略为租户配置，对象可审批性与金额字段为产品元数据 | 已定 |
| TBD-7 | Explain 范围 | 一期覆盖 permission / state / validation；approval 与 derivation 二期 | 三类是写入拒绝与不可见的主因，且数据已在拦截器/状态机/校验器内；审批解释依赖 L2 快照 | 已定 |

### 10.2 TBD-4 头部产品研究

**结论：4 层 vs 6 层是伪命题；真正要定的是「层级类型」「深度」「授权锚点」三件事。**

> 现状依据：`meta/schemas/hierarchies.yaml` 已记录 2026-06-03 由 6 层裁剪为 4 层，
> 理由为「层级过深，授权到子领域已足够精确」。这正说明 6 层仍有展示价值，只是不适合做授权粒度。

| 产品 | 机制 | 对我们的启示 |
|---|---|---|
| Workday | Functional Area（导航分组）→ Domain（安全集合）→ Business Process Type；一个 Domain 可属于多个 Functional Area | 导航层级与安全范围是两套坐标，不能共用一棵树做授权 |
| ServiceNow CSDM | 4 层（Ideation / Design / Build / Service Delivery）7 个域，按关注点分层，实体跨层多对多 | 层级是关注点分层，不是固定元数；深度随模型演进 |
| SAP Solution Manager | Business Blueprint 将组织单元、主数据、业务流程分三类管理 | 组织、对象、流程是正交维度，不应压成一条链 |
| Oracle Fusion | 以产品族 / 功能范围 / 任务组织功能；数据授权另由 Data Role + 组织层级决定 | 展示深度可到 6 层，授权锚点另立 |
| LeanIX / EA 工具 | 能力地图深度可变，实践建议每层 5-10 项、优先广度 | 固定深度会逼迫模型裁剪，最终产生「假层级」 |

**落地模型**

```yaml
dimension_levels:
  - level_type: product          # 层级语义类型
    parent_level: null
    scope_anchor: true           # 可作数据授权锚点
    owner_field: product_id
  - level_type: version
    parent_level: product
    scope_anchor: true
    owner_field: version_id
  - level_type: domain
    parent_level: version
    scope_anchor: true
    owner_field: domain_id
  - level_type: sub_domain
    parent_level: domain
    scope_anchor: true           # 当前 4 层 profile 的叶子
    owner_field: sub_domain_id
  - level_type: service_module
    parent_level: sub_domain
    scope_anchor: false          # 展示层级，不授权
    owner_field: service_module_id
  - level_type: business_object
    parent_level: service_module
    scope_anchor: false
    owner_field: business_object_id
```

**两条不变量**

1. `scope_anchor=true` 的层级集合必须能覆盖所有业务表的归属字段；不能覆盖时，加载期报 `DIMENSION_ANCHOR_UNCOVERED`。
2. 任一深度的对象向上解析归属时，只能命中最近的一个 `scope_anchor`；跨锚点解析报 `DIMENSION_ANCHOR_AMBIGUOUS`。

**已确认（2026-11-07）：保持现状，不做行为变化**

- `product / version / domain / sub_domain` 四个 `scope_anchor=true` 不变；
- `sub_domain` 仍为授权叶子；
- `service_module / business_object` 仍为 `scope_anchor=false`，只做展示与归属解析；
- 默认 `profile=4`，现有权限行为零变化。

### 10.3 关联修正

- FR-002 验收标准改为「深度可声明 + 锚点分离」。
- §7.3 假设 2、3 更新为已定结论。
- §9.5 明确本轮只实施 M1。

### 10.4 二次确认（官方文档级）

对 §10.1 的每条决议做了第二轮核实，优先采用产品官方文档而非二手文章。

| ID | 核实到的产品事实 | 对 Spec 的影响 | 结论 |
|---|---|---|---|
| TBD-1 | Oracle Fusion 的自定义在 Sandbox 内完成，验证后 Publish 合并回主线 | 变更应以「可验证的发布单元」推进，而非一次性全量 | 维持 M1 |
| TBD-2 | Microsoft：`statecode` 的状态选项不能新增，只能改标签；`statuscode`（Status Reason）可按状态增删 | 比原决议更严格：L1 主状态值冻结，L2 只能扩原因码 | 维持并收紧 |
| TBD-3 | Oracle Document Sequence 分 Automatic / Gapless / Manual，可设初始值并按单据类别分配；Gapless 会阻止删除已编号单据 | `gapless` 不能只理解为「不跳号」，还要加删除约束 | 微调（新增约束） |
| TBD-4 | ServiceNow CSDM 明确四层用于 separation of concerns；Workday 一个 Domain 可属于多个 Functional Area | 层级是关注点切分，且允许非树形引用；授权锚点与展示层级必须分离 | 维持并补「允许多对多引用」 |
| TBD-5 | SAP 消息由 message class + message number 定位，长文本可独立维护（SE91） | 错误码/消息号稳定、文案可翻译，与原决议一致 | 维持 |
| TBD-6 | Oracle AME 以规则引擎按金额区间等条件路由审批，配置而非编码 | 审批策略属租户配置层，与原决议一致 | 维持 |
| TBD-7 | SAP SU53 只能在报错后立即查看「最后一次失败的授权检查」，缓冲区易失 | Explain 必须同步记录当次失败因子，不能事后从日志重建 | 微调（新增约束） |

### 10.5 二次确认带来的微调

1. **TBD-2 收紧**：`state_transition.states[].code` 为主状态主键，加载期禁止租户新增/删除；租户只能维护 `label` 与 `reason_codes`。
2. **TBD-3 增约束**：`gapless: true` 时，已编号单据禁止物理删除；作废必须保留号码并置 `voided`，否则报 `NUMBER_SEQUENCE_GAP_FORBIDDEN`。
3. **TBD-7 增约束**：Explain 的 `factors[]` 必须在同一次请求内生成并随响应返回（含 `rule_id`、`level`、期望值/实际值）；禁止依赖日志回捞。
4. **TBD-4 补边界**：`dimension_levels` 的展示层级（`scope_anchor=false`）允许一个对象被多个父级引用；授权层级仍要求唯一归属，避免权限歧义。

### 10.6 研究来源

- Microsoft Learn：Define custom state model transitions（statecode 不可新增状态值）
- SAP：User Status Profile（系统状态不可改，用户状态附加）
- Oracle：Document Sequences（Automatic / Gapless / Manual，初始值，Gapless 阻止删除）
- Oracle：AME（Approval Management Engine）规则化审批
- SAP：SU53 授权检查
- SAP：SE91 消息维护
- ServiceNow：CSDM 5 White Paper（四层 separation of concerns）
- Workday：Configurable Security Framework（Functional Area / Domain）
- Oracle：Sandbox Publish
