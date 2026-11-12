# Spec：业务对象关系元模型（单一事实规范）

> 版本：v2.0（association aggregate 收口版）｜ 日期：2026-11-12 ｜ 基线：HEAD `0431188c`
> 性质：**治理规范 + 落地需求**（非研究报告）
> 输入：
> - 研究报告 `../../research/business-object-metamodel-research-2026-11-12.md`（六公理 A1-A6、九产品解剖、G1-G7）
> - `spec-bo-metadata-single-source-2026-11-11.md`（权限四平面、四条判定链路、判定口径）
> - `spec-doc-flow-single-fact-model-2026-11-05.md`（单一事实五判据、边表使用四问）
> - `spec-metadata-driven-backend-research.md`（七产品元数据可部署性对比）
> 定位：把「关系是一等公民」从研究结论收敛为**可 lint、可断言、不新增事实表、不新增并行承载位**的元模型约束。

---

## 0. 结论先行

### 0.1 v1.0 → v2.0 的核心修正

v1.0 把「关联（`relationship`）」当成**缺失**，试图为它新建三套承载位。二次核对 main（`0431188c`）后确认：**关联本身已是一个完整聚合根**，v1.0 的三条主张 100% 属于「重复建模」。

| v1.0 主张 | v2.0 修正 | 证据 |
|---|---|---|
| R-MM-01 新增顶层 `relation_kind:` + `carrier:` 对象 | 只在既有 `semantics` 段加一个 `kind` 枚举（缺省 `association`） | `meta/schemas/relationship.yaml` L13-16 资源身份、L54-56 删除策略、L57-65 权限 scope、L69-101 级联选择、L102-115 语义、L116-137 键模板、L146+ 分析模型 |
| R-MM-04 新增 `permission_rule.via_relation` + 新 PDP | 复用既有 `relationship.authorization.inherit_mode`，扩展既有 `check_association_visibility` | `meta/services/resource_inheritance_engine.py` L39 `RESOURCE_ASSOCIATION`、L315 `check_association_visibility`、L375 `_resolve_endpoint_product_id`（两端并集**已实现**） |
| R-MM-06 新增 `GET /bo/{t}/{id}/relations` | 扩展既有 `$associations/<name>` 加 `?kind=`，**不新增端点** | `meta/api/bo_api.py` L1449 / 1475 / 1495 / 1534 / 1602 / 1642 / 1704 共 7 个 `$associations` 路由 |
| R-MM-07 元模型版本包（新声明位） | 删除，能力并入既有 `/schema-version` | 避免第二套版本声明位 |
| R-MM-03 新建矩阵为「唯一判定源」 | 降为「覆盖度 + lint + 派生矩阵」，判定源仍是 `state_field_policies` / `field_policies` | `meta/core/models.py` L1238 / L1243；`meta/services/field_policy_engine.py` L60-133 |
| R-MM-05 泛化 `doc_profile` 新声明 | 降为「覆盖度 + lint」，复用既有对象 `document:` 段 | 14 个事实单据已有 `document:`；`document_profile_service.py` 已消费 |

### 0.2 五条需求（v1.0 的 7 条压缩而来）

1. **R-MM-01（P0）关联语义扩展**：`relationship.semantics.kind` 四枚举（`association` / `hierarchy` / `reference` / `master_detail` / `derived`）+ `$associations?kind=` 消费。
2. **R-MM-02（P0）动作元模型补全**：`_standard_actions.yaml` 从 6 字段扩到 6 组（`params` / `preconditions` / `effects` / `emits` / `audit` / `object_types`），全部可选、向后兼容。
3. **R-MM-03（P0）状态可写性覆盖度**：`state_field_policies` 覆盖 15 张事实单据 + 3~5 个高频对象补 `field_policies`（已补 5 个：`purchase_order` / `customer_invoice` / `sales_order` / `vendor_invoice` / `work_order`）。
4. **R-MM-04（P1）关系感知授权**：`relationship.authorization.inherit_mode`（`none` / `endpoint_union` / `explicit`），扩展既有 `check_association_visibility`，不新增权限表。
5. **R-MM-05（P1）正/逆/调整同构**：三边型（`red_ink` / `counter` / `compensate`）覆盖度 + 「原边 immutable」lint，不新增流程引擎。

### 0.3 三条硬约束

- **不新增事实表**：所有落点都在既有 YAML 声明内；唯一新增的生成物是 `meta/generated/state_field_matrix.yaml`（派生、可重建、不进声明扫描）。
- **不新增端点**：关系导航只扩展既有 `$associations`，不新建 `/relations`。
- **声明 → 运行必须可判定**：任何规范都要能被 `sync_schema --check` 或 `lint_metamodel` 判定；不能断言的规范视为未落地。

---

## 1. 判定口径与落地实况

### 1.1 判定口径（沿用 `spec-bo-metadata-single-source` §1）

| 判定 | 含义 | 处理 |
|---|---|---|
| 已覆盖 | 声明位存在，生成物/判定链路自动生效，有测试 | 引用，不重复要求 |
| 部分覆盖 | 声明位存在但未被消费，或仅部分链路消费 | 本 spec 要求「接线」 |
| 缺失 | 声明位不存在 | 本 spec 要求「新增字段/生成物」 |
| 空转 | 声明位存在但无任何读取方（死表/死字段） | 本 spec 要求「删除或接线」，二选一 |

### 1.2 落地实况（基线 `0431188c` 取证）

| 能力 | 声明位 | 声明数 | 消费方 | 判定 |
|---|---|---|---|---|
| 关联资源身份 | `relationship.resource`（L13-16） | 1 类 | `resource_inheritance_engine.py` L39 / L315 | **已覆盖** |
| 关联权限 scope | `relationship.authorization`（L57-65） | 1 类 | 同上 + `bo_api.py` L836-865 角色来源 | **已覆盖** |
| 关联级联选择 | `relationship.cascade_select`（L69-101） | 8 组 | 表单级联 | **已覆盖** |
| 关联键模板 | `relationship.key_template`（L116-137） | 1 | 取号服务 | **已覆盖** |
| 关联分析模型 | `relationship.analytical_model`（L146+） | 1 | 分析服务 | **已覆盖** |
| 关联语义分类 | `relationship.semantics.category`（L106） | 1 | **无 kind 消费** | **缺 kind** |
| 单据文档画像 | 对象 `document:` 段 | 14/14 事实单据 | `document_profile_service.py` | **已覆盖** |
| 状态 × 字段只读 | `state_field_policies` | 2/15（`purchase_order.yaml` L71、`customer_invoice.yaml` L801） | `FieldPolicyEngine` | **部分覆盖** |
| 角色 × 字段策略 | `field_policies` | 5 个对象已声明 | `FieldPolicyEngine._load_role_policies`（L60-79） | **已接线（5/15 事实单据）** |
| 动作元模型 | `_standard_actions.yaml` | 25 × 6 字段 | `rules.action_ref` | **部分覆盖** |
| 单据流规则 | `doc_flow_rule` + `doc_flow_edges` | 已有 | `reversal_orchestrator.py`（7 步） | **已覆盖** |

**净缺口只有 3 个**：① `semantics.kind` 缺失；② `field_policies` 仅 5 个高频对象已声明（其余单据仍空转）；③ 动作元模型缺 5 组字段。其余 v1.0 主张均为「已有承载，勿重建」。

---

## 2. 收敛框架：三个聚合根，各管一段

| 聚合根 | 声明真源 | 运行时承载 | 职责边界 | v1.0 误判 |
|---|---|---|---|---|
| **A 关联聚合** | `relationship.yaml`（身份/审计/删除/权限 scope/级联/键模板/分析模型/语义） | `relationships` 表 + `check_association_visibility` + 7 个 `$associations` 路由 | 对象↔对象关系的定义、授权、遍历 | 误判「承载位缺失」→ 要新建 kind / carrier / 端点 |
| **B 对象聚合** | `<object>.yaml`（`states` / `state_field_policies` / `field_policies` / `document`） | `FieldPolicyEngine` + `document_profile_service` | 字段级可写/可见/必填 + 文档画像 | 误判「无单一来源」→ 要新建矩阵文件当唯一源 |
| **C 单据流聚合** | `doc_flow_rule` + `doc_flow_edges` + 对象 `document:` | `reversal_orchestrator` + `doc_flow_reversal` | 正向 / 逆向 / 调整 | 已实现，只需 lint 守边 |

**收口原则**：新能力优先落在对应聚合根**内部**（加一个键/枚举），不跨根新建。v1.0「迭代多了」的根因就是把同一个能力在三个根里各写一遍。

---

## 3. R-MM-01 关联语义扩展（A1/A2/A3，P0）

### 3.1 问题陈述

`relationship.semantics` 只有 `category: relationship`（L106），无法区分「树形上下级 / 引用 / 主从 / 一般关联」。后果：前端无法按语义渲染（树 vs 列表）、权限无法按语义决定继承强度、单据边与普通关联共用同一 `relation_code` 空间。

### 3.2 声明位（扩展既有 `semantics`，**不新增顶层键**）

```yaml
semantics:
  meaning: 业务对象之间的关联关系   # 既有 L103
  category: relationship             # 既有 L106
  kind: association                  # 新增；五枚举，缺省 association
```

| kind | 语义 | 结构约束 | 运行时行为 |
|---|---|---|---|
| `association`（默认） | 一般关联 | 无 | 两端 product 并集可见（现有行为） |
| `hierarchy` | 树形上下级 | `source_bo_id == target_bo_id` 且 `key_template.enabled=true` | 允许 parent/children 导航 |
| `reference` | 引用/查阅 | 目标只读 | 不级联状态 |
| `master_detail` | 主从强依赖 | 主子删除/状态联动 | 必须在 `deletability` 显式声明条件（L54-56 默认 `'true'` 不适用于主从） |
| `derived` | 派生（视图/计算） | `analytical_model.enabled=true`（L146） | 只读，不可写 |

### 3.3 消费侧（原 R-MM-06 并入）

**不新增 `/relations` 端点**。在既有 7 个 `$associations` 路由（`bo_api.py` L1449-1704）上增加查询参数：

```
GET /api/v2/bo/{object_type}/{id}/$associations/<name>?kind=hierarchy&depth=1&direction=out
```

- `kind` 省略 = 不过滤（向后兼容）
- `depth` 上限 2；`depth>1` 时做环检测，同一 `(type,id,code)` 只出现一次
- 返回结构不变，`kind` 只做过滤，不改响应 schema

### 3.4 硬规则

- **R1**：`kind` 缺省 `association`，存量 0 迁移、0 行为变化。
- **R2**：`kind: master_detail` 必须同时声明 `deletability.condition`，否则 lint 失败。
- **R3**：`kind: derived` 必须 `analytical_model.enabled=true`，否则 lint 失败。
- **R4**：`kind` 只影响渲染与继承强度；**不进 DDL、不新增表、不新增端点、不改 `relationships` 表结构**。

### 3.5 验收断言

| # | 断言 | 命令/证据 |
|---|---|---|
| A-01-1 | `kind` 不产生 DDL 差异 | `python meta/tools/sync_schema.py --check --against db` 返回 0 |
| A-01-2 | 五枚举逐项校验，`master_detail` 无 `deletability` 即失败 | `python meta/tools/lint_metamodel.py --relations` 退出码 0 |
| A-01-3 | `?kind=` 过滤结果 == 手工按 `semantics.kind` 过滤结果 | 同一夹具下集合相等 |
| A-01-4 | 省略 `kind` 时 7 个路由响应与改造前一致 | 回归 0 失败 |

---

## 4. R-MM-02 动作元模型补全（A4，P0）

### 4.1 问题陈述

`_standard_actions.yaml` 每条动作只有 `id / name / action_type / instance_scope / method / description` 6 字段。动作的**参数、前置条件、副作用、事件、审计要求**全部散落在 Python service 与前端，无法被状态矩阵、权限、审计复用，也无法断言「声明 = 实现」。

### 4.2 声明位（扩展 `_standard_actions.yaml`，字段全部可选、向后兼容）

```yaml
standard_actions:
  - id: post
    name: 过账
    action_type: business
    instance_scope: instance
    method: POST
    object_types: [vendor_invoice, sales_invoice]   # 新增：动作适用对象（缺省=全部）

    params:                                          # 新增
      - {name: posting_date, type: date, required: true, default: today, source: user}

    preconditions:                                   # 新增（声明式，禁止内联脚本）
      status_in: [draft, rejected]
      role_any: [admin, editor]                      # 必须是真实 permission_sets.code，见 §4.3 R8
      relation_exists: {code: invoice_line, min: 1}
      expr: "amount_total > 0"                       # OCL-lite，仅字段比较与布尔组合

    effects:                                         # 新增（枚举化）
      - {type: transition, field: status, from: draft, to: posted}
      - {type: set, field: posted_at, value: now}
      - {type: create, object: journal_entry}
      - {type: link, relation_code: invoice_to_je, direction: forward}
      - {type: notify, target: owner}

    emits: [invoice.posted]                          # 新增：领域事件名
    audit: {record: true, reason_required: false, fields: [status, posted_at]}   # 新增
    permission: {code: invoice.post, level: write}   # 已有能力，显式化
```

### 4.3 硬规则

- **R5**：`effects` / `preconditions` 只允许**声明式枚举**，不允许任意脚本；实现仍在 Python service，YAML 不产生第二个执行体。
- **R6**：`emits` 的事件名进入事件注册表，未注册即 lint 失败（防「声明了没人听」）。
- **R7**：`audit.record=true` 的动作必须落到 `audit_log` 的 `action` 字段，且 `audit.fields` ⊆ 实际变更字段。
- **R8**：`preconditions.role_any` 只能使用**库中真实存在的角色**。角色来源 = `bo_api.py` L836-865 `_current_user_roles()` → `permission_sets.code`；当前 seed 仅 `admin` / `editor` / `viewer`（`meta/scripts/init_auth.py` L155-159）。引用不存在的 code 会导致条件永不命中，lint 必须报错。
- **R9**：已由 `rules.action_ref` 引用的动作，其 `preconditions.status_in` 必须覆盖该对象 `status` 枚举的全部合法来源态；不覆盖即 lint 警告并列出。

### 4.4 验收断言

| # | 断言 |
|---|---|
| A-02-1 | 25 个存量动作 100% 通过结构校验；新增字段缺省时行为不变（回归 0 失败） |
| A-02-2 | `lint_metamodel --actions` 退出码 0，输出「声明-实现签名差异: 0」 |
| A-02-3 | 任一动作可通过既有元数据端点读取完整声明（前端「动作详情」不再硬编码） |
| A-02-4 | `test_action_metamodel.py` 断言 `post` 的 `effects[0].to` 与对象 `status` 枚举一致、`emits` 已注册、`role_any` 全部存在于 `permission_sets` |

---

## 5. R-MM-03 状态可写性覆盖度（A4/A5，P0）

### 5.1 问题陈述与修正

v1.0 主张「新建 `state_field_matrix.yaml` 作为唯一可写性判定源」。核对后确认**判定源已经存在**：`state_field_policies`（`meta/core/models.py` L1238）+ `field_policies`（L1243），由 `FieldPolicyEngine` 按固定顺序求值（`is_field_editable`：系统字段 → **角色策略** → 状态矩阵 → immutable → `ui.editable` → 运行时注册策略 → mutability → 默认 True）。

真正的缺口是**覆盖率**：`state_field_policies` 仅 2/15 张事实单据，`field_policies` **0** 声明 → 角色维完全空转。

### 5.2 目标（可验收）

| 项 | 现状 | 目标 |
|---|---|---|
| `state_field_policies` 覆盖 | 2/15（`purchase_order` L71、`customer_invoice` L801） | 15/15 事实单据 |
| `field_policies` 声明数 | 5 个高频对象（本轮已补） | ≥ 3~5 个高频对象（已达成） |
| 角色名合法性 | 无校验 | lint 校验 `when` 中角色 ⊆ `permission_sets.code` |
| 派生矩阵 | 无 | `meta/generated/state_field_matrix.yaml`（仅用于覆盖度 diff 与前端版本失效，**不作判定源**） |

**本轮执行清单（3~5 个高频对象）**：`purchase_order` / `customer_invoice` / `sales_order` / `vendor_invoice` / `work_order`（存在的先做）。声明口径见 §5.3。

### 5.3 声明口径（`field_policies` 权威语法）

来自 `meta/services/field_policy_engine.py` L95-133 与 `meta/tests/test_field_policy_role.py`：

```yaml
field_policies:
  exchange_rate:
    editable:
      - when: "'viewer' in user.roles"
        value: false
  gross_amount:
    required:
      - when: "'editor' in user.roles"
        value: true
  cost_price:
    visible:
      - when: "'viewer' in user.roles"
        value: false
```

- 三键：`editable`（缺省 True）/ `visible`（缺省 True）/ `required`（缺省 False）
- 规则元素：`{when, value}`，`when` 由 `safe_evaluate` 求值，可引用 `user.roles`
- **角色名只能是 `admin` / `editor` / `viewer`**（`init_auth.py` L155-159）；测试里的 `auditor` / `clerk` / `external` 是夹具，库中不存在，照抄会永不命中
- 已知实现瑕疵：`visible` 也被解析为 `EditablePolicy`（`_parse_policy_kind(..., True)`），但 `_role_policy` 只读 `.determination`，语义可用；本 spec 只备注不扩大改动

### 5.4 硬规则

- **R10**：判定源唯一 = `state_field_policies` + `field_policies`（由 `FieldPolicyEngine` 求值）；矩阵文件是**派生物**，不得手工编辑，文件头写 `generated ... do not edit`。
- **R11**：派生矩阵必须幂等（连续两次生成字节一致），覆盖「过渡态」（如 `cancelling` / `reversing`），过渡态默认 `writable_fields: []`。
- **R12**：写入被拒绝时返回 `400` + `field_not_writable_in_state`，不得静默忽略。
- **R13**：`field_policies.when` 中引用的角色必须存在于 `permission_sets.code`，否则 lint 失败。
- **R14**：`meta/generated/` **不存在时由生成工具 `mkdir -p` 创建**；该目录不在 `meta/schemas/` 扫描路径内，不会污染 YAML 加载。

### 5.5 验收断言

| # | 断言 |
|---|---|
| A-03-1 | 15 张事实单据全部有 `state_field_policies` 条目（或 lint 显式列出未覆盖清单） |
| A-03-2 | `python d:\filework\test.py --file meta/tests/test_field_policy_role.py` 通过；角色命中 → 只读/必填，未命中 → 回退状态矩阵 |
| A-03-3 | `grep -c '^field_policies:' meta/schemas/*.yaml` 命中数 ≥ 3（当前 5） |
| A-03-4 | 构造夹具：对 `posted` 状态的 `amount_total` 发起 PUT → 400 且错误码 `field_not_writable_in_state` |
| A-03-5 | 连续两次生成矩阵字节一致（幂等） |

---

## 6. R-MM-04 关系感知授权（A5，P1）

### 6.1 问题陈述与修正

v1.0 要在 `permission_rule` 上新增 `via_relation` + 新 PDP。核对后确认：**关联聚合已有授权执行体**——`resource_inheritance_engine.py` L39 `RESOURCE_ASSOCIATION = 'association'`（不继承、取两端并集）、L315 `check_association_visibility`、L375 `_resolve_endpoint_product_id`。缺的只是「按语义选择继承强度」的开关，而不是新权限表。

### 6.2 声明位（扩展既有 `relationship.authorization`，L57-65）

```yaml
authorization:
  check: true
  scope: version_id IN (...)          # 既有 L59-60
  auto_owner: false                   # 既有
  auto_permission: admin              # 既有
  inherit_to_children: false          # 既有
  inherit_mode: endpoint_union        # 新增：none | endpoint_union | explicit（缺省 endpoint_union，保持现有行为）
  allow_transfer: false
  transfer_keep_permissions: false
```

| inherit_mode | 语义 | 求值 |
|---|---|---|
| `endpoint_union`（默认） | 两端 product 并集（**现有行为**） | `_resolve_endpoint_product_id` 并集 |
| `none` | 只看本端，不取并集 | 仅 source 端 product |
| `explicit` | 由 `permission_rule.condition` 显式声明路径/深度 | 复用既有条件表达式，**不加新字段** |

### 6.3 硬规则

- **R15**：**不新建权限表、不新增第八处声明位**。`explicit` 复用既有 `permission_rule.condition`，二者组合求值。
- **R16**：`inherit_mode=explicit` 时必须有对应 `permission_rule` 行引用同一 `relation_code`；否则 lint 失败。
- **R17**：求值顺序固定：`is_denied` 优先 → 直接规则 → 关系继承 → 默认拒绝；`max_depth ≤ 2`。
- **R18**：四条既有判定链路（L1 Gate / L2 YAML RLS / L3 ActionPermissionInterceptor / L4 未接线 PDP）中，**P1 只接线到一处 PDP**；其余链路对 `inherit_mode` 显式忽略并把 `decided_by` 写入 trace，避免四份不同答案。
- **R19**：`inherit_mode` 缺省 `endpoint_union`，存量关系 0 迁移、0 行为变化（回归必须为 0 失败）。

### 6.4 验收断言

| # | 断言 |
|---|---|
| A-04-1 | 同一夹具在 L1/L2/L3 入口得到**相同** allow/deny，trace 中 `decided_by` 唯一 |
| A-04-2 | `inherit_mode` 缺省时所有既有用例结果不变（回归 0 失败） |
| A-04-3 | `explicit` + `max_depth=2` 用例通过；`max_depth=3` 被拒绝并返回明确错误 |
| A-04-4 | `lint_metamodel --permissions` 校验 `explicit` 行全部有对应 `relation_code` 声明 |

---

## 7. R-MM-05 正向 / 逆向 / 调整同构（A3/A6，P1）

### 7.1 结论复用（研究报告 §5）

> 正向 = 动作 + 状态迁移 + 关系边生成；逆向 = 追加一条反向边（红冲 / 反向单 / 补偿），**不修改原边**；调整 = 差额或新版本边。关键不是「三套流程」，而是一套关系元模型 + 一组动作类型 + 一张状态矩阵 + 一组参数。

**修正**：v1.0 要新建 `doc_profile` 声明段。核对后确认对象已有 `document:` 段（14/14 事实单据）+ `doc_flow_rule` / `doc_flow_edges` + `reversal_orchestrator.py`（7 步）+ `doc_flow_reversal.py`（三边型 `red_ink` / `counter` / `compensate`）。因此本条只剩**覆盖度与 lint**，不新增声明位。

### 7.2 硬规则（沿用，措辞收敛）

- **R20**：三类型由同一套 `doc_flow_rule` + `doc_flow_edges` + `reversal_orchestrator` 驱动；**禁止为第二类单据新增 Python 分支**。判据：新增单据类型后 `reversal_orchestrator.py` 的 diff 为 0。
- **R21**：逆向/调整**只能追加边**，原边 `immutable`；任何 UPDATE 原单数量/状态的动作视为违规，lint 报错。
- **R22**：数量归属唯一——数量只在边上（`doc_flow_edges`），状态只在头/项；同一字段不得两处写。
- **R23**：`status` 唯一真源为单据表 `status` 列（v256 已加 CHECK）；**不引入 BPMN 引擎**，长事务仅由 `change_request` 审批承载。

### 7.3 验收断言

| # | 断言 |
|---|---|
| A-05-1 | 选第二类单据仅用 YAML 声明即可完成「正向 → 红冲 → 调整」，`reversal_orchestrator.py` 无改动 |
| A-05-2 | 冲销后原单行 `updated_at` 不变（用 `audit_log` 断言） |
| A-05-3 | 三边型各自 1 个端到端用例通过（红冲 / 反向单 / 补偿） |

---

## 8. 需求清单与路线

| ID | 需求 | 公理 | 优先级 | 落点（全部为既有承载） | 关键断言 |
|---|---|---|---|---|---|
| R-MM-01 | 关联语义扩展 | A1/A2/A3 | P0 | `relationship.semantics.kind` + `$associations?kind=` | A-01-1..4 |
| R-MM-02 | 动作元模型补全 | A4 | P0 | `_standard_actions.yaml` +5 组字段 | A-02-1..4 |
| R-MM-03 | 状态可写性覆盖度 | A4/A5 | P0 | `state_field_policies`（2→15）+ `field_policies`（0→3~5） | A-03-1..5 |
| R-MM-04 | 关系感知授权 | A5 | P1 | `relationship.authorization.inherit_mode` + 扩展 `check_association_visibility` | A-04-1..4 |
| R-MM-05 | 正/逆/调整同构 | A3/A6 | P1 | `doc_flow_*` + `document:` 覆盖度 lint | A-05-1..3 |

### 8.1 路线

| 阶段 | 内容 | 前置 |
|---|---|---|
| P0 | R-MM-01 / 02 / 03 + `lint_metamodel --relations --actions --field-policies` | 无（纯元模型 + 声明，不动运行时判定链路） |
| P0.5 | §12 R24-R27：受控枚举 + 别名归一 + `bo_category` 派生 + 生成 `bo_capability_matrix.yaml` | P0 完成（能力维度前置，零 YAML 改动） |
| P1 | R-MM-04 / 05（04 依赖 01 的 `kind` 标注完成） | P0 完成；P0.5 与之并行 |

---

## 9. 风险与不做清单

| # | 风险 | 对策 |
|---|---|---|
| 1 | `inherit_mode` 演变为「第八处权限声明位」 | R15：只复用既有 `authorization` + `condition`，不新建表、不加并行判定链 |
| 2 | 关系继承求值递归爆炸 | `max_depth ≤ 2` + 环检测 + 结果缓存按 `(user, object, relation_code)` |
| 3 | 动作声明与 Python 实现漂移 | `lint_metamodel --actions` 比对签名/事件/审计字段，差异即失败 |
| 4 | `field_policies` 角色名写错（永不命中） | R13：lint 校验 `when` 中角色 ⊆ `permission_sets.code`；本轮只用 `admin`/`editor`/`viewer` |
| 5 | 派生矩阵与前端缓存不一致 | 矩阵带 `version`（内容哈希），前端按版本失效；矩阵不作判定源 |
| 6 | 261 表逐表补声明成本高 | 先脚本推断（有 `states` 的对象自动生成骨架），人工只复核高风险对象 |

**不做（明确排除）**：

- 不引入 BPMN / 流程引擎作为第四处状态真源。
- 不建通用 EAV / 关系超表；不把所有 FK 都改写成关系行。
- 不为元模型新增事实表（唯一新增为 `meta/generated/` 派生矩阵，可重建）。
- 不在 P0 阶段改运行时判定链路（只加声明与 lint）。
- 不新增 `/relations` 端点、不新增 `permission_rule` 声明位、不新增 `doc_profile` 声明段。

---

## 10. 与既有 spec 的边界

| 既有文档 | 关系 |
|---|---|
| `spec-bo-metadata-single-source-2026-11-11.md` | R-MM-04 是其「权限四平面」的关系面补充；判定口径直接复用 |
| `spec-doc-flow-single-fact-model-2026-11-05.md` | R-MM-05 是其五判据在通用关系上的推广；边表四问直接复用 |
| `spec-reversal-platform-2026-11-06.md` | `reversal_orchestrator` / 三边型为该 spec 已交付能力，本 spec 只要求 lint 守边 |
| `spec-metadata-driven-backend-research.md` | 提供 Palantir / Dataverse / ServiceNow 的元数据可部署性证据 |
| `../../research/business-object-metamodel-research-2026-11-12.md` | 理论来源（A1-A6、九产品解剖），本 spec 为其工程收敛 |

---

## 11. 术语

| 术语 | 定义 |
|---|---|
| 声明位 | 某个事实在元模型中唯一的权威定义位置（YAML 字段/枚举） |
| 生成物 | 由声明位确定性推导出的产物（DDL、派生矩阵），可重建、不手工编辑 |
| 聚合根 | 一组内聚声明 + 运行时承载的整体；本 spec 收敛为关联 / 对象 / 单据流三类 |
| 状态可写性 | 某状态下某字段是否允许写入，由 `FieldPolicyEngine` 按固定顺序求值 |
| 过渡态 | 不在主状态枚举语义内的中间态（如 `cancelling` / `reversing`），默认不可写 |

---

## 12. 类型驱动能力：archetype × capability profile × 关联类型

> 本节是 2026-11-12 九产品二次复核后的新增结论，也是 R-MM 系列的**上游前提**：
> 先确定「能力挂在哪个元模型层」，再谈关系 / 动作 / 状态可写性各自的声明位。

### 12.1 头部产品结论

| 产品 | 能力承载方式 | 关键取证 | 对我方的含义 |
|---|---|---|---|
| D365 F&O | Table Group（Main / Transaction / Worksheet / Parameter / Reference） | 组只驱动生命周期与处理顺序，**不生成字段、不建关联**；Header↔Line 需人工建 1:N | 粗分类不足，不能只靠「单据 / 主数据」二分推导能力 |
| Salesforce | Master-Detail vs Lookup | Master-Detail ⇒ 级联删除 + Owner 继承父 + Detail 侧 Owner 不可用 + 禁共享规则 + 隐含必填 + 可 Rollup；Lookup 侧 `deleteConstraint` 三选 SetNull / Restrict / Cascade | 能力挂在**关系**上，最接近我方 L2 |
| NetSuite | Transaction 类型 | 自动获得内部不间断编号（不可覆盖）、过账、作废、冲销、审批 | 「内部编号不可覆盖」须由生成器保证，不能交给用户模板 |
| Odoo | `Model` / `TransientModel` / `AbstractModel` | `_inherits` 自动建外键，但**字段委派查找是运行时隐式** | 反面样本：隐式委派导致「写的层与读的层不一致」 |
| Dataverse | Table type + Ownership | Standard / Activity / Elastic / Virtual；Ownership = User-or-team / Organization / Filtered，**创建后不可改** | 类型与归属是**不可变**的建模期决策 |
| ServiceNow | Table `extends` / `augments` | 继承字段与逻辑，但 **ACL 不随 extends 自动继承** | 权限不因类型继承而自动获得（对应 A5） |
| SAP RAP | BDEF：managed / unmanaged / draft-enabled / abstract | managed = 框架代管锁 / 编号 / 权限 / 草稿 / DB 保存；**编译期绑定** | 「受管 / 非受管」二选一 + 编译期展开，正是本项目要的形状 |
| 金蝶苍穹 BOS | 单据 / 基础资料（含树形）/ 动态表单 + 编码规则 | 编码规则中「流水号必含」 | 编号能力的下限（有流水号）可硬约束 |
| 用友 YonBuilder | 勾选式能力集（审批、业务流、交易类型、自动编码、档案状态、主组织） | **未勾选则不生成** | 最接近 capability profile：opt-in、显式、可 lint |

**结论**：九产品无一采用「运行时按类型隐式获得能力」，全部是 **建模期显式选择 → 落盘声明 → 编译 / 装载期展开 → 运行期只执行展开结果**，且带「选择后不可静默变更」约束。

### 12.2 三层承载位模型与我方落点

| 层 | 承载什么 | 能力清单 | 我方落点 | 现状 |
|---|---|---|---|---|
| **L1 Archetype**（对象类型） | 结构能力 | 审计 / 编号 / 状态机 / 过账 / 软删 / 版本 | `semantics.category`（受控枚举）→ 派生 `bo_category` + `bo_capability_matrix.yaml` | 枚举未受控（14 值自由字符串）；`bo_category` 仅 6 文件显式声明**且装载期被忽略** |
| **L2 Association kind**（关系类型） | 关系能力 | 级联 / 必填 / 共享继承 / 汇总 / 可见性 | `relationship.semantics.kind`（R-MM-01，5 枚举） | 未声明，零覆盖 |
| **L3 Field type**（字段类型） | 字段能力 | 值帮助 / 枚举保护 / 审计跟踪 | `field.type` + `semantics.sensitive` + `field_policies`（R-MM-03） | `field_policies` 0→3~5；`state_field_policies` 2/15 |

**A3（单一承载位）在能力维度上的投影**：同一能力只能挂**一层**。级联删除只能由 L2 关系声明，L1 不得再声明「该对象所有下游都级联」；审计只能由 L1 声明，L3 不再逐字段声明「是否审计」，L3 只声明敏感度与可写性。

### 12.3 现状取证（2026-11-12 实测）

`meta/schemas/` 下 **150 个 YAML** 声明了顶层 `semantics.category`，共 **14 个取值**：

| 取值 | 数量 | 取值 | 数量 |
|---|---|---|---|
| `core_entity` | 60 | `relationship` | 2 |
| `system_entity` | 29 | `meta_object` | 2 |
| `business_document_line` | 24 | `test` | 2 |
| `business_document` | 18 | `auxiliary` | 1 |
| `transactional` | 5 | `business_config` | 1 |
| `business_object` | 3 | `configuration` | 1 |
| `master_data` | 1 | `security_entity` | 1 |

**同义分裂**（必须归一）：`transactional` vs `business_document`；`configuration` vs `business_config`；`master_data` vs `core_entity`（部分 `core_entity` 实为主数据）。

**其它取证**：

- `parse_meta_object` **未读取** `bo_category` / `bo_sub_category`，两键虽在 `_KNOWN_OBJECT_KEYS` 白名单内，但声明的 6 个文件的值在装载后被 dataclass 默认值 `MASTER_DATA` 覆盖 → **显式覆盖当前是失效的**（P0.5 一并接线）。
- `BoCategoryConfig` 模板在 `__post_init__` 回填，唯一运行时消费点只有序列化输出（`bo_framework.py` L489）→ **模板链路是死代码**，是「6 套维度仅 2 套生效」的证据之一。
- `semantics.category` 在装载期**无任何枚举校验**（Grep 无匹配）→ 拼错静默通过。

**对原 P0 计划的修正**：原计划为「5 值枚举（document / document_line / master_data / config / analytical）强制重命名」。实测为 **14 值 / 150 文件**，强制重命名需改 150 个 YAML 且丢失 `system_entity` / `meta_object` / `relationship` / `test` / `security_entity` 语义，违背「不改 200+ YAML」的初衷。**改为：保留既有 14 值作为受控枚举 + 别名归一 + 显式映射派生，零 YAML 改动。**

### 12.4 声明与派生规则

**R24 受控枚举**：`semantics.category` 取值必须 ∈ `ObjectSemanticsCategory`（14 既有值）。装载期未知取值 → 告警并入 lint 失败清单，不再静默通过。

**R25 别名归一**：同义写法在读取时归一，不要求改 YAML。别名表与枚举同模块维护，同属单一事实。

**R26 派生优先级**（`bo_category` 求值顺序，前者覆盖后者）：

1. YAML 显式 `bo_category`（人工覆盖，矩阵标 `source: override`）
2. `ARCHETYPE_TO_BO_CATEGORY[semantics.category]`（矩阵标 `source: template`）
3. dataclass 默认 `MASTER_DATA`（矩阵标 `source: absent`，计入覆盖率缺口）

> 映射表是**单一事实**：只存在于代码常量，不复制到 150 个 YAML。派生结果只写 `meta/generated/bo_capability_matrix.yaml`。

**R27 生成物约束**：`meta/generated/bo_capability_matrix.yaml` 由生成工具创建（目录不存在则创建），**不在** `meta/schemas/` 扫描路径内，不参与 `load_yaml_directory`；带内容哈希 `version`，可重建、不手工编辑；**不作任何判定源**。

矩阵形状（archetype × capability 展开）：

```yaml
version: <对 枚举 + 映射 + 覆盖 取 sha256 前 12 位>
generated_at: "2026-11-12T00:00:00Z"
archetypes:
  business_document:
    bo_category: TRANSACTIONAL
    capabilities:
      audit:         {enabled: true,  source: template}
      numbering:     {enabled: true,  source: template}
      state_machine: {enabled: true,  source: template}
      posting:       {enabled: false, source: template, disabled: 未声明 doc_effect}
      soft_delete:   {enabled: false, source: template}
      revision:      {enabled: false, source: template}
    objects: [purchase_order, sales_order]
```

### 12.5 硬规则

| ID | 规则 | 断言 |
|---|---|---|
| R24 | `semantics.category` ∈ 受控枚举；未知取值装载期告警 | A-12-1 |
| R25 | 别名归一在读取层完成，YAML 零改动 | A-12-2 |
| R26 | `bo_category` 派生优先级固定为 显式 > 映射 > 默认；矩阵须标 `source` | A-12-3 |
| R27 | 矩阵为生成物：可重建、内容哈希版本、不作判定源 | A-12-4 |
| R28 | 同一能力只能挂一层（A3 在能力维度的投影）；跨层重复声明 → lint 失败 | A-12-5 |

### 12.6 该抄 / 不该抄

**该抄**

- 用友勾选式 opt-in：能力显式打开，未声明即不存在（对应 R26 的 `absent` / `disabled`）。
- SAP managed / unmanaged 编译期二选一：派生在装载期一次算完，运行期不重算（对应 R27）。
- Salesforce 关系类型驱动能力：L2 承载关系能力（对应 R-MM-01 的 `kind`）。
- Dataverse 不可变 ownership：`semantics.category` 属建模期决策，改类型须走显式覆盖。
- ServiceNow 权限不随继承自动获得：L1 继承不产生权限（A5 三平面）。
- NetSuite 内部编号不可覆盖：编号开启后用户模板不得覆盖流水号。

**不该抄**

- D365「一个表只能进一个组」的粗分类：我方按能力逐项 opt-in，不用单值粗分类。
- Salesforce「关系类型决定 Owner 继承」的强耦合：会绕过 `OwnerChainInterceptor`，Owner 继承仍由既有链决定。
- Odoo `_inherits` 字段委派查找：运行时隐式，与「装载期展开」直接冲突。

### 12.7 路线

| 阶段 | 内容 | 前置 |
|---|---|---|
| P0.5 | R24-R27：受控枚举 + 别名归一 + `ARCHETYPE_TO_BO_CATEGORY` 派生 + 生成 `bo_capability_matrix.yaml` | P0（不改运行时判定链路；零 YAML 改动） |
| P1.5 | R28 跨层重复声明 lint + 覆盖率缺口清单（哪些对象缺哪项能力） | P0.5 |
| P2 | 能力开关反向驱动运行时（如 `numbering.enabled=false` 时不注册 KeyTemplate 拦截器） | P1.5 + 运行时链路改造评估 |

---

## 附录 A v1.0 → v2.0 删改明细

1. **删 R-MM-07**（元模型版本包）：能力并入既有 `/schema-version`，不新增 `metamodel_packages.json` 声明位。
2. **R-MM-01 降级**：`relation_kind` + `carrier` 两个顶层键 → `semantics.kind` 一个枚举键；原 R1-R4 四条硬规则压缩为 R1-R4 四条（改判据，不再要求「carrier 唯一」）。
3. **R-MM-04 降级**：`permission_rule.via_relation` + `inherit_mode` 两个新字段 → `relationship.authorization.inherit_mode` 一个字段；原「唯一 PDP」保留为 R18，但明确只接线一处。
4. **R-MM-06 并入 R-MM-01**：不新增 `/relations`，改为 `$associations?kind=`；原 R22-R25 四条压缩为 §3.3 三条参数约束。
5. **R-MM-03 降级**：矩阵从「唯一判定源」改为「派生物」；新增覆盖率目标（2→15、0→3~5）。
6. **R-MM-05 降级**：`doc_profile` 新声明段 → 覆盖度 + lint；R18-R21 保留语义，重编号为 R20-R23。
7. **修正路径**：`meta/generated/` 目录不存在 → 明确由生成工具创建、且不在 `meta/schemas/` 扫描路径内。
8. **修正基线**：`5cf6fc5b` → `0431188c`（s7 已合并）。
9. **新增角色真实性约束**：R8（动作 `role_any`）与 R13（`field_policies.when`）均限定 `permission_sets.code`，当前仅 `admin` / `editor` / `viewer`。