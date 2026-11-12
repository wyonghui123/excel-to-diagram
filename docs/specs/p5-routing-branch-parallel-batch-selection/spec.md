# P5 实现规格：路线分支/并行、批次等级与批次选择策略

- 日期: 2026-11-03
- 状态: **待批准**（批准后才动代码）
- 上游依据:
  - `docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md` v0.8 §12（P5 字段级方案）/ §11.9（Oracle 二次复核 O1–O7）
  - 主 Spec `spec-unified-resource-model-2026-11-01-v1.0.md` v1.25 附 C.3
- 迁移号: **v199**（仓库实际最大前缀 `v198`，存在 `v198__engineering_change.py` / `v198__location_org.py` 两文件；研究稿“预计 v197”已过期）

## 1. 目标与范围

**做（仅三件事）**：

1. `work_definition_sequences` 扩 5 列 + `parallel` 枚举 + 分支/批量区间/优先级 + 图校验 `validate_sequence_graph` + 只读展开 `expand_sequences`。
2. `batches.grade_code` 物理列 + `(item_id, grade_code)` 索引（Oracle 一等批次属性，§11.9 O1）。
3. 新对象 `batch_selection_policy`（保存校验）+ `select_batches`（默认可用性谓词、逐层策略、审计留痕）。

**不做（已拍板，勿重复讨论）**：

- 不做 P4b 新增项 / 财务域（`cost_center` / `activity_type` / `activity_rate`）。
- 不建 `batch_characteristics` / `batch_type_attribute` / `characteristics_json`。
- 不建批次库存余额、批次成本、多父 genealogy、跨组织批次谱系/链接；`qty/uom` 不参与筛选；不做执行层批次分配（预留/拣货/单据行拆批）。
- 不建独立 `recipe` 头、`department`、`process_segment`、`control_key` 主数据。
- 不改 `batch_attribute_values`；不建 `selection_basis` 列；不建 grade master。
- 不 commit、不部署。

## 2. 已定决策与对研究稿的修正

| # | 决策 | 说明 |
|---|---|---|
| D1 | 迁移号 **v199** | 实际最大前缀 v198；不预占、不重排既有 v198 |
| D2 | 菜单 `batch-selection-policy-list` 的 `sort_order=**106**` | 研究稿写 104，但 104 已被 v196 `batch-management` 占用、105 已被 v198 `engineering_change` 占用 |
| D3 | `expand_sequences(definition_id, lot_qty)` 不内置 PV 选择 | 仓库无 P4a PV 选路实现；调用方先按 PV 解析到 `definition_id` 再展开，避免新增第二套选 PV 逻辑 |
| D4 | `grade_code` 排序用字典序，NULL 永远排最后 | 无 grade master；SQL `ORDER BY (col IS NULL) ASC, col ASC|DESC` |
| D5 | 无策略 / 全部策略 0 条 ⇒ `NoBatchMatchError` | 不静默取第一条（§12.9 Q3） |
| D6 | `rule_json` 解析错误立即抛错，不跳到下一条 | 避免静默错配（§12.6） |
| D7 | `allow_blocked=true` 放开 blocked + inspection，`closed` 永远排除 | §12.9 Q9 |
| D8 | `rule_hash = sha256(canonical(rule_json))[:16]` | 不新增 `rule_version` 列 |
| D9 | 告警而非阻断：`MULTIPLE_STD_SEQUENCE`（存量）与 `SEQUENCE_LOT_NOT_COVERED` | §12.2 G1/G12 修订口径 |
| D10 | 批次唯一性语义 = Oracle `No uniqueness control` | 键 `(item_id, org_id, batch_no)` 不变；Oracle `Across items`（跨组织唯一）属 P6，不在 P5 落库 |
| D11 | 跨组织同一批次不建单行记录 | Oracle 同样每组织一条 lot 记录；P5 不建 origin/谱系链接，差异记入 P6 backlog |
| D12 | 单据行不挂批次 | 与 Oracle 一致（销售订单行/调拨单行不含批次）；拆批属预留/拣货/发运执行层，P5 不做，禁止给 `transfer_order_line` 加 `batch_id` |
| D13 | `grade_code` 排序是业务扩展，非 Oracle 惯例 | Oracle 拣货规则按有效期(FEFO)/收货日期(FIFO)/批号排序，未见按等级；默认模板仍以 FEFO 为首选 |

### 2.1 Oracle 二次复核（2026-11-03）

只影响口径，不改变 §3–§6 的实现。

| 流程 | Oracle 官方事实 | 与 P5 的对齐 | 结论 |
|---|---|---|---|
| 跨组织不同批次 | 批次主数据按 `item + inventory org + lot number` 建记录；Manage Lots 只显示当前组织；同物料同批号可跨组织并存（即使开启 Across Items） | `batches` 唯一键与 `select_batches(item_id, org_id)` 的组织隔离一致 | **Oracle 也如此**；P5 实现的是 `No uniqueness control` 语义 |
| 跨组织同一批次 | 组织间调拨保留批号与有效期；目标组织仍为独立批次记录；通过产品谱系/交易历史按批号跨组织追溯 | P5 无调拨执行、无 origin 链接、无谱系 | **口径修正**：不是“模型不成立”，而是“主数据层与 Oracle 一致，缺属性延续与追溯层”；P6 再评估 |
| 单据行批次拆分 | 销售订单拆行按仓库/替代料/交期，不按批次；批次在预留（低层预留到批号）、拣货确认（可录多批）、发运（Record Lots）层拆；调拨单行初始映射一条发运行 | 本地 `transfer_order_line` 不含批次，与 Oracle 单据行模型一致；本地无预留/拣货层 | **口径修正**：拆批是执行层能力，不是单据行字段；P5 “不做”成立，不得用给单据行加 `batch_id` 来“补齐” |

P6 backlog（本 Spec 不做）：

1. 跨组织批次链接/谱系（`origin_org_id` / `origin_batch_id`，或复用 `parent_batch_id`）。
2. 批次唯一性控制（Oracle `Across items` 语义）。
3. 执行层批次分配（单据行 × 批次 × 数量，对应 Oracle 预留/拣货）。
4. 等级排序模板的可配置化（当前 `GRADE_FIRST` 为业务扩展）。

不作为结论依据的疑点（待核实，勿写入实现）：

- EBS `Global Lot Attributes` 的跨组织属性同步范围（仅见帮助标题与二手资料）。
- Fusion 跨组织调拨是否自动建立谱系父子边（官方未明确）。
- Oracle 是否存在按等级拣货的内置规则（公开文档未见）。

## 3. 数据模型

### 3.1 `work_definition_sequences`（追加列，裸列无 FK）

| 列 | DDL | 可空 | 默认 | 语义 |
|---|---|---|---|---|
| `branch_operation_seq` | `INTEGER` | 是 | — | 分支工序号，引用同定义 `work_definition_operations.seq`，服务层校验 |
| `return_operation_seq` | `INTEGER` | 是 | — | 返回/汇合工序号；alternative 必填，parallel 可选 |
| `lot_min` | `REAL` | 是 | — | 适用批量下限，空 = 不限 |
| `lot_max` | `REAL` | 是 | — | 适用批量上限，空 = 无上限 |
| `priority` | `INTEGER NOT NULL DEFAULT 1` | 否 | 1 | 同 branch 多 alternative 的取用顺序（小者优先） |

枚举 `sequence_type` 追加 `parallel`（不新建枚举类型）。

索引：
- `uq_work_definition_sequence_branch_priority`：**部分唯一** `(definition_id, branch_operation_seq, priority) WHERE seq_type = 'alternative' AND branch_operation_seq IS NOT NULL`
- `idx_work_definition_sequence_branch`：`(definition_id, branch_operation_seq)`
- 保留既有 `uq_work_definition_sequence_no` / `idx_work_definition_sequence_type`

### 3.2 `batches`（追加列）

| 列 | DDL | 可空 | 语义 |
|---|---|---|---|
| `grade_code` | `VARCHAR(20)` | 是 | 质量等级；字典序排序；物理列不进 EAV（§11.9 O1） |

索引：`idx_batches_grade`：`(item_id, grade_code)`。

### 3.3 `batch_selection_policies`（新表）

| 字段 | 类型 | 可空 | 约束 |
|---|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | 否 | — |
| `code` | VARCHAR(40) | 否 | 全局唯一 `uq_batch_selection_policy_code` |
| `name` | VARCHAR(128) | 否 | 显示名 |
| `scope_type` | VARCHAR(20) | 否 | `item` / `item_group` / `org` |
| `scope_ref` | VARCHAR(60) | 否 | 业务编码：`items.code` / `item_groups.code` / `orgs.code`；保存时校验存在 |
| `rule_json` | TEXT | 否 | JSON DSL v1；保存时 parse + 白名单 |
| `priority` | INTEGER | 否 | `>= 1`，默认 1；同 `(scope_type, scope_ref)` 下 active 唯一 |
| `status` | VARCHAR(20) | 否 | `active` / `inactive`，默认 active |
| `description` | VARCHAR(255) | 是 | — |
| `created_by` / `updated_by` | VARCHAR(200) | 是 | 平台审计列 |
| `created_at` / `updated_at` | DATETIME | 是 | — |

表级 CHECK：`scope_type IN ('item','item_group','org')`、`status IN ('active','inactive')`、`priority >= 1`。

索引：
- `uq_batch_selection_policy_code(code)` 唯一
- `uq_batch_selection_policy_scope_priority`：**部分唯一** `(scope_type, scope_ref, priority) WHERE status = 'active'`
- `idx_batch_selection_policy_scope(scope_type, scope_ref)`

## 4. Schema YAML 变更

### 4.1 `meta/schemas/work_definition_sequence.yaml`

- 追加字段 `branch_operation_seq` / `return_operation_seq`（integer，nullable，UI `fieldGroup: 分支`）、`lot_min` / `lot_max`（number，nullable，`gte: 0`，UI `适用范围`）、`priority`（integer，`required: true`，`default: 1`，`numeric_range.gte: 1`，UI `适用范围`）。
- `seq_type.enum_values` 追加 `parallel`（label 并行，color info）。
- 索引追加上述 2 条（部分索引用 `type: partial` + `unique: true` + `condition`）。
- `ui_view_config.form.sections` 与 `detail.tabs[0].fields` 纳入新字段；list 增加 `branch_operation_seq` / `return_operation_seq` / `priority` 列。
- 顶部口径注释删除“P5 再扩”，改为“P5 已扩 parallel + branch/return”。

### 4.2 `meta/schemas/batches.yaml`

- 追加 `grade_code`（string(20)，nullable，`fieldGroup: 质量`，`fieldGroupPosition: 125`，注释引用 §11.9 O1）。
- 索引追加 `idx_batches_grade`：`[item_id, grade_code]`。

### 4.3 `meta/schemas/batch_selection_policy.yaml`（新建）

- 对象 `batch_selection_policy`，表 `batch_selection_policies`，`aspects: [audit_aspect]`，`display_name_field: name`。
- 字段全部按 §3.3 声明；`scope_type` / `status` 内联枚举 + `enum_type_id` 分别指向 `batch_selection_scope` / `batch_selection_policy_status`。
- `code` 标 `business_key: true`；`rule_json` 用 textarea。
- 索引 3 条（含部分唯一 `condition: "status = 'active'"`）。
- `ui_view_config` 含 list / form / detail 三态；`skip_auto_menu: false`（需独立菜单）。
- `category_config` 四动作权限：`batch_selection_policy:batch_selection_policy_{create|update|delete}` + read。

## 5. 服务层

### 5.1 `meta/services/work_definition_sequence_service.py`（新建）

常量：`SEQ_STD='std'`、`SEQ_PARALLEL='parallel'`、`SEQ_ALTERNATIVE='alternative'`。异常 `WorkDefinitionSequenceError(message, field_name, rule)`。

`validate_sequence(payload, existing=None) -> List[str]`：
- 合并 old + patch，校验 `seq_no >= 1`、`priority >= 1`、`seq_type` 枚举、`lot_min >= 0`、`lot_max > lot_min`。
- 以候选行替换同 id 后构建完整序列集，执行 G1–G10；返回告警（G1 存量/G12）。

`validate_sequence_graph(definition_id) -> List[str]`：
- 只读加载并执行 G1–G12，返回告警列表，不抛硬错误（供巡检）。

规则（硬失败）：

| # | 规则码 | 判定 |
|---|---|---|
| G1 | `MULTIPLE_STD_SEQUENCE` | 写入时同定义已有另一条 std；存量巡检只告警 |
| G2 | `SEQUENCE_STD_HAS_BRANCH` | std 填 branch/return |
| G3 | `SEQUENCE_PARALLEL_BRANCH_REQUIRED` / `SEQUENCE_RETURN_NOT_AFTER_BRANCH` | parallel 缺 branch；return 填了但 ≤ branch |
| G4 | `SEQUENCE_ALTERNATIVE_BOUNDARY_REQUIRED` / `SEQUENCE_BOUNDARY_INVALID` | alternative 缺 branch/return；branch == return 或 return ≤ branch |
| G5 | `SEQUENCE_BRANCH_NOT_IN_STD` / `SEQUENCE_RETURN_NOT_IN_STD` | branch/return 不在 std 的 active 工序（`sequence_id IS NULL` 或指向本定义 std 行） |
| G6 | `SEQUENCE_BRANCH_PRIORITY_DUPLICATE` | 同 `(definition_id, branch)` 的 alternative `priority` 重复 |
| G7 | `SEQUENCE_LOT_MIN_NEGATIVE` / `SEQUENCE_LOT_RANGE_INVALID` | `lot_min < 0`；两者都填且 `lot_max <= lot_min` |
| G8 | `SEQUENCE_GRAPH_CYCLE` / `SEQUENCE_OPERATION_SEQ_DUPLICATE` / `SEQUENCE_OPERATION_CONFLICTS_BOUNDARY` | branch→return 连边 DFS 成环；序列内工序 seq 重复；工序 seq 等于本序列 branch/return |
| G9 | `SEQUENCE_BOUNDARY_OPERATION_NOT_STD` | 任何 branch/return 工序号被挂到非 std 序列 |
| G10 | `SEQUENCE_NO_OPERATION` | 非 std 序列 0 工序 |
| G12 | `SEQUENCE_LOT_NOT_COVERED` | 定义被 active PV 引用，且序列区间与所有 active PV 区间都不相交 ⇒ **告警** |

`validate_operation(payload, existing=None) -> None`：
- G11：工序 `seq` 变更且旧值被任何序列的 branch/return 引用 ⇒ `SEQUENCE_BOUNDARY_OPERATION_REFERENCED`。
- 若工序所属序列为非 std：`seq` 不得等于该序列 branch/return（同上 G8 规则）。

`expand_sequences(definition_id, lot_qty=None) -> Dict`：
- 纯函数返回 `{'operations': [...], 'decisions': [...]}`。
- `operations` 元素 `{seq, source: std|alternative|parallel, sequence_id, operation_seq}`。
- 标准工序按 seq 升序；到达 branch 工序时：
  - alternative：按 `lot_min/lot_max` 过滤（空=不限），`priority` 升序、`id` 升序取首条，替换 `(branch, return)` 区间；
  - parallel：同 branch 全部序列按 `seq_no` 升序并列输出；
  - 无替代命中：输出 `ROUTE_FALLBACK_STD` 决策，保留标准路径。
- 不做 PV 选择（D3）。

### 5.2 `meta/services/batch_selection_policy_service.py`（新建）

异常 `BatchSelectionPolicyError(message, field_name, rule)`。

`validate_policy(payload, existing=None) -> Dict`（返回规范化合并值，`rule_json` 重序列化为 canonical JSON）：
- `code ≤ 40` / `name ≤ 128` / `scope_ref ≤ 60` 必填。
- `scope_type ∈ {item, item_group, org}`；`scope_ref` 按层查 `items.code` / `item_groups.code` / `orgs.code`，不存在 ⇒ `BATCH_SELECTION_SCOPE_NOT_FOUND`。
- `priority >= 1`；同 `(scope_type, scope_ref, priority)` 的另一条 active（排除自身）⇒ `BATCH_SELECTION_PRIORITY_DUPLICATE`。
- `status ∈ {active, inactive}`。
- `rule_json`：
  - 必须是 JSON 对象；非法 ⇒ `BATCH_SELECTION_RULE_INVALID_JSON`。
  - 顶层白名单 `version / filters / sort / limit / allow_blocked`，未知键 ⇒ `BATCH_SELECTION_RULE_UNKNOWN_KEY`。
  - `version` 必填且 `== 1` ⇒ 否则 `BATCH_SELECTION_RULE_VERSION`。
  - 字段白名单：`batch_no / status / quality_status / qty / produced_at / expiry_date / potency_pct / grade_code / source / parent_batch_id / created_at`；其他（含 EAV 特性）⇒ `BATCH_SELECTION_EAV_FIELD_NOT_ALLOWED` / `BATCH_SELECTION_RULE_UNKNOWN_FIELD`。
  - 算子 `eq / ne / gt / gte / lt / lte / in / between / is_null / is_not_null`，未知 ⇒ `BATCH_SELECTION_RULE_UNKNOWN_OP`；类型校验失败 ⇒ `BATCH_SELECTION_RULE_VALUE_INVALID`。
  - `sort` 元素只允许 `field / dir`，`dir ∈ {asc, desc}`。
  - `limit` 为 1..500 整数，缺省 100。
  - `allow_blocked` 为 boolean，缺省 false。
- `RULE_TEMPLATES`：FEFO（`expiry_date asc`）、FIFO（`created_at asc`）、等级优先（`grade_code desc, expiry_date asc`），仅作常量与测试样例。
- `rule_hash(rule_json) -> str`：`sha256(json.dumps(parsed, sort_keys=True, separators=(',', ':'), ensure_ascii=False))[:16]`。

### 5.3 `meta/services/batch_selection_service.py`（新建）

异常：
- `InvalidSelectionRuleError`：已落库策略的 `rule_json` 解析/白名单错误（立即抛错，不跳到下一条）。
- `NoBatchMatchError(attempted_policy_codes, reason)`：无策略或无匹配。

`BatchSelectionResult`：`batch_ids / policy_id / rule_hash / evaluated_policies / default_predicate / allow_blocked`。

`select_batches(item_id, org_id, qty=None, uom=None, context=None, tenant_id=0, audit_service=None) -> BatchSelectionResult`：
1. 默认谓词：`quality_status = 'unrestricted' AND status != 'closed'`；`allow_blocked=true` ⇒ `status != 'closed'`（放开 blocked/inspection）。
2. 解析 `items.code` → `item_groups.code` → `orgs.code`；缺失层跳过。
3. 策略顺序 item → item_group → org；同层 `priority ASC, id ASC`，仅 `status='active'`。
4. 逐条执行：默认谓词 + `filters`，`sort` 每键 `(col IS NULL) ASC, col ASC|DESC`，`limit`。
5. 首条 ≥1 结果生效；0 条记录 `attempted_policy_codes` 继续。
6. 全部 0 条或无策略 ⇒ 写失败审计（`outcome='failed'` + `reason`）后抛 `NoBatchMatchError`。
7. 成功审计：`AuditService.log(object_type='batch_selection_policy', object_id=policy_id, action='select', outcome='success', extra_data={item_code, org_code, qty, uom, batch_ids, policy_code, priority, rule_hash, default_predicate, allow_blocked, attempted_policy_codes, context})`。
8. `qty/uom` 仅透传审计，不参与筛选。

### 5.4 拦截器与注册（两条启动路径）

- 新建 `meta/core/interceptors/work_definition_sequence_guard_interceptor.py`（优先级 57）：
  - 对象 `work_definition_sequence`（create/update）→ `validate_sequence`；
  - 对象 `work_definition_operation`（create/update）→ `validate_operation`。
- 新建 `meta/core/interceptors/batch_selection_policy_guard_interceptor.py`（优先级 58）：
  - 对象 `batch_selection_policy`（create/update）→ `validate_policy`。
- 失败统一转 `ValidationFailedError(details=[{field_name, rule, message, i18n_key:'', params:{}}])`。
- 两处注册：`meta/core/app_builder.py`（约 L323 之后）与 `meta/server.py`（约 L581 之后），缺一静默失效。

## 6. 迁移 `meta/migrations/v199__routing_p5.py`

单笔包含：

1. `ALTER TABLE work_definition_sequences ADD COLUMN` × 5（幂等：PRAGMA 查列）。
2. `sequence_type` 枚举补 `parallel`（sort_order=3）。
3. 新枚举 `batch_selection_scope`（item/item_group/org）、`batch_selection_policy_status`（active/inactive）。
4. `CREATE TABLE IF NOT EXISTS batch_selection_policies` + 3 索引。
5. 权限 4 条 `batch_selection_policy:batch_selection_policy_{read|create|update|delete}`，授予 `admin` / `default`。
6. 菜单 `batch-selection-policy-list`「批次选择策略」挂 `master-data`，`sort_order=106`，路径 `/master-data/batch-selection-policy`。
7. `batches.grade_code VARCHAR(20)` + `idx_batches_grade(item_id, grade_code)`。
8. `verify`：5 列 + `priority` NOT NULL/DEFAULT 1、`grade_code`、4 索引、`sequence_type.parallel` + 2 新枚举全值、4 权限、1 菜单；`rollback` 反向：菜单/权限/授权 → 索引 → 表 → DROP COLUMN（枚举种子保留）；重复执行打印 `[SKIP]`。
9. 兜底：`work_definition_sequences` / `batches` 表不存在时打印 `[SKIP]` 并以退化模式继续（测试库可只建部分表），但 `verify` 对缺表判 FAIL。

## 7. 测试

### 7.1 新建 `meta/tests/test_work_definition_sequence_graph.py`

1. YAML：5 字段类型/可空/默认；`seq_type` 含 `parallel`；部分唯一索引 condition；UI 分组。
2. 迁移 v199：临时库 `migrate → verify → migrate → verify → rollback → verify 失败`；5 列与 2 索引真实存在。
3. 规则：G2/G3/G4（缺边界、return ≤ branch、branch == return）；G5（branch/return 不在 std）；G6（同 branch priority 重复）；G7；G8（成环、重复 seq、边界冲突）；G9；G10；G11。
4. 告警：存量多 std 只告警；G12 与 active PV 全不相交只告警。
5. `expand_sequences`：替代命中替换区间；无命中 `ROUTE_FALLBACK_STD`；并行并列输出；批量区间过滤。

### 7.2 新建 `meta/tests/test_batch_selection_policy.py`

1. YAML / 表结构 / 3 索引（含部分唯一条件）/ 3 值枚举 / `priority >= 1`。
2. 保存校验：scope_ref 不存在；同 scope 同 priority 两条 active 冲突；inactive 可复用；非法 JSON / 未知键 / EAV 字段 / 未知算子 / `limit=0` / `version != 1`；3 模板可通过。
3. 选择：item > item_group > org；同层 priority；首条命中即停；首条 0 条落到下条；全部 0 条 / 无策略 ⇒ `NoBatchMatchError`。
4. 审计载荷含 `batch_ids / policy_code / priority / rule_hash / default_predicate / allow_blocked`；失败含 `outcome='failed'`。
5. 默认谓词排除 blocked / inspection / closed；`allow_blocked=true` 放开 blocked+inspection，closed 仍排除。
6. `qty/uom` 不影响结果集合。
7. `grade_code` 升/降序且 NULL 最后。

### 7.3 翻转既有测试

- `meta/tests/test_work_definition_sequence_schema.py`：`test_seq_type_only_std_and_alternative` → 断言 3 值含 parallel；`test_no_p5_fields` → 断言 5 列存在；索引断言补 2 条。
- `meta/tests/test_batches.py`：字段集补 `grade_code`（nullable）；索引补 `idx_batches_grade`。
- `test_batch_attribute_values.py` / `test_production_version_schema.py` 保持绿。

## 8. 验收与验证

```
python d:\filework\test.py --single meta/tests/test_work_definition_sequence_graph.py
python d:\filework\test.py --single meta/tests/test_batch_selection_policy.py
python d:\filework\test.py --single meta/tests/test_work_definition_sequence_schema.py
python d:\filework\test.py --single meta/tests/test_batches.py
python d:\filework\test.py --failed
```

- 迁移另跑：`python -m meta.migrations.v199__routing_p5 --verify`（真实库只读校验，不改数据）。
- 全部通过后输出改动清单与测试结果；**不 commit**。

## 9. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 既有 alternative 行无 branch/priority 默认 1，同 branch 部分唯一索引不冲突 | 部分索引 `WHERE branch IS NOT NULL` 排除存量 |
| 旧 `sequence_type` 枚举无 parallel | 迁移补值；YAML 内联枚举同步 |
| 策略 `rule_json` 从 EAV 迁入物理列 | 白名单拒绝 EAV 字段，文档标注“不得替代质量判定” |
| 菜单排序冲突 | 使用 106（104/105 已占用） |
| 回滚丢策略数据 | rollback 先删表（数据不可恢复）；生产只允许在功能未启用时回滚 |
| 跨组织同一物理批无追溯链接 | P5 仅做主数据；谱系/链接列入 P6，不承诺跨组织血缘 |

## 附 A：Oracle 复核来源（2026-11-03）

官方文档（Fusion SCM 26C/26D）：

- [批次唯一性控制](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/famml/considerations-for-selecting-lot-number-uniqueness-control.html)
- [批次管理（Manage Lots 按组织）](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/famml/lot-management.html)
- [组织间调拨](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/famml/interorganization-transfers.html)
- [调拨保留有效期](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/famml/does-a-lot-retain-its-expiration-date-during-interorganization.html)
- [预留（可到批号粒度）](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/famml/reservations.html)
- [拣货确认可录多批](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/famml/overview-of-pick-slip-confirmation.html)
- [发运 Record Lots](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/famlo/how-can-i-record-more-than-one-lot.html)
- [销售订单拆行（仓库/日期/替代料）](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/fauom/fulfillment-line-splits.html)
- [调拨单行映射一条发运行](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/famlo/how-transfer-orders-and-shipping-integration-is-processed.html)
- [产品谱系](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/faumf/overview-of-tracing-product-genealogy.html)

数据字典（二手，用于确认键与列）：

- [Fusion INV_LOT_NUMBERS](https://summit-bi.com/resources/fusion-reference/tables/inv_lot_numbers)
- [EBS MTL_LOT_NUMBERS](https://summit-bi.com/resources/ebs-reference/tables/mtl_lot_numbers)
