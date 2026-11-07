# 执行方案：规则化收敛 M2（状态机 / 审批注册表 / 单据流 / 加载期校验）

> 依据：[2026-11-07 规则化收敛 Spec](../specs/2026-11-07-rule-convergence-spec.md) v1.3 §3 FR-004 / FR-005 / FR-006 / FR-012
> 前置：[M1 执行方案](./2026-11-07-rule-convergence-m1-execution-plan.md)（已落地、未提交）
> 决议：TBD-4 保持现状（`sub_domain` 为授权叶子，`service_module` 不升第 5 锚点）
> 原则：先声明、后替换读取入口；对外错误码 / HTTP 状态 / 用户提示零变化

---

## 1. 范围

### 1.1 本轮实施

| FR | 内容 | 目标载体 |
|---|---|---|
| FR-004 | `sales_order_schedule` / `serial_number` 状态图声明化 | BO YAML `states:` + `rules: type=state_transition` |
| FR-005 | 审批对象注册表与金额优先级元数据化 | BO YAML `approval:` + `MetaObject.approval` |
| FR-006 | 单据流规则数据化收口 + 迁移静态守卫 | `doc_flow_rule` 校验器 + `scripts/check_rule_convergence.py` |
| FR-012 | 加载期一致性校验（状态机 / 审批 / 编号 / 单据流） | 新增 `rule_declaration_validator.py` + CI 测试 |

### 1.2 明确不做

- FR-002 / FR-003 / FR-010 / FR-011（M3）。
- 不新增 `RuleType`；状态图复用 `RuleType.STATE_TRANSITION`。
- 不改 `v214` / `v215` / `v222` 的规则数据与行为。
- 不改数据库结构（无 DDL）、不改对外错误码与 HTTP 状态。
- 不把 `serial_number` 的状态变更接入通用 RuleEngine（D11：只走服务白名单 + 事件账）。

---

## 2. 关键决议

| 编号 | 决议 | 理由 |
|---|---|---|
| D-M2-1 | 状态图声明为 BO YAML 的 `rules: type=state_transition`，复用现有 `MetaStateTransition`，不新增顶层块 | 与 `purchase_order_schedule.yaml`、`project.yaml` 已有范式一致；IF-001 要求复用 `state_transition` |
| D-M2-2 | 新增的 state_transition 规则全部声明 `ui_hints.hidden: true` | `bo_api.get_state_transitions` 只返回非 hidden 规则；隐藏后 `/state_transitions` 输出与改造前**逐字节等价**，避免前端凭空多出按钮 |
| D-M2-3 | 规则声明 `enabled: false`（不接 `before_update`） | `MetaStateTransition.__post_init__` 会把空 `triggers` 默认成 `before_update`；`enabled: false` 让 `get_rules_by_trigger` 过滤掉，`get_rules_by_type` 仍可读，既不接引擎也不改变既有写路径（尤其防止 `serial_number` 绕过 `serial_transactions`） |
| D-M2-4 | 声明缺失时 fail-open + WARNING，不保留旧常量副本 | NFR-002 可回滚；FR-012 在 CI 阶段以稳定错误码拦截漏声明，运行时不为一次读失败打死写入路径（沿用 M1 `_read_numbering` 口径） |
| D-M2-5 | 状态全集与终态来自 `states:` 目录（`category: terminal`），不由规则反推 | 「新增状态只改 YAML」；同时保证 `SCHEDULE_TERMINAL` 的专用提示语保持可判定 |
| D-M2-6 | 审批表名与金额优先级放 BO YAML `approval:`，审批策略本身仍在 DB | 表名/取值顺序是对象结构元数据（L1）；门限/审批人可配置（L2） |
| D-M2-7 | FR-012 校验以测试 + `check_rule_convergence.py` 在 CI 失败为准，不接入请求链路 | 满足「启动或 CI 阶段失败」的「或」；避免运行时行为变化 |

---

## 3. 交付物

| 编号 | 交付物 | 路径 |
|---|---|---|
| D1 | 状态机加载器 | 新增 `meta/core/state_machine_loader.py` |
| D2 | 计划行状态声明 | `meta/schemas/sales_order_schedule.yaml` |
| D3 | 序列号状态声明 | `meta/schemas/serial_number.yaml` |
| D4 | 守卫 / 服务改读声明 | `meta/services/sales_order_guard_service.py`、`meta/services/serial_number_service.py` |
| D5 | 审批元数据加载器 | 新增 `meta/core/approval_meta_loader.py` |
| D6 | 审批声明 | `meta/schemas/{purchase_order,transfer_order,requisition,service_request}.yaml` |
| D7 | 元模型扩展 `approval` | `meta/core/models.py`、`meta/core/yaml_loader.py` |
| D8 | 审批服务改读声明 | `meta/services/document_approval_service.py` |
| D9 | 加载期一致性校验器 | 新增 `meta/core/rule_declaration_validator.py` |
| D10 | 静态守卫扩展 | `scripts/check_rule_convergence.py` |
| D11 | M2 等价性测试 | 新增 `meta/tests/test_rule_convergence_m2.py` |
| D12 | 执行记录 | 本文件 §9 |

---

## 4. 详细设计

### 4.1 FR-004 状态机声明化

#### 4.1.1 YAML 声明形状

`sales_order_schedule.yaml` 新增 `states:` 与 `rules:`：

```yaml
# R-SCH-9 唯一真源（服务层只读声明，保留副作用与跨字段校验）
states:
  - {code: planned,   label: 计划中, category: initial,  seq: 1}
  - {code: confirmed, label: 已确认, seq: 2}
  - {code: completed, label: 已完成, category: terminal, seq: 3}
  - {code: cancelled, label: 已作废, category: terminal, seq: 4}

rules:
  - id: confirm_sales_order_schedule
    name: 确认计划行
    type: state_transition
    state_field: status
    from_states: [planned]
    to_state: confirmed
    enabled: false
    ui_hints: {hidden: true}

  - id: complete_sales_order_schedule
    name: 完成计划行
    type: state_transition
    state_field: status
    from_states: [confirmed]
    to_state: completed
    triggers: []
    ui_hints: {hidden: true}

  - id: cancel_sales_order_schedule
    name: 作废计划行
    type: state_transition
    state_field: status
    from_states: [planned, confirmed]
    to_state: cancelled
    triggers: []
    ui_hints: {hidden: true}
```

`serial_number.yaml` 新增 `states:`（`usage_status` 轴）与 7 条规则。规则顺序必须与旧 `TRANSITIONS` 的元组顺序一致：

| 顺序 | to_state | from_states |
|---|---|---|
| 1 | `in_stores` | `defined, returned, in_transit` |
| 2 | `issued` | `in_stores` |
| 3 | `in_transit` | `in_stores` |
| 4 | `shipped` | `in_stores, issued` |
| 5 | `consumed` | `issued` |
| 6 | `returned` | `issued` |
| 7 | `scrapped` | `defined, in_stores, in_transit, issued, shipped, consumed, returned` |

`states:`：`defined`（initial）、`in_stores`、`in_transit`、`issued`、`shipped`、`consumed`、`returned`、`scrapped`（terminal）。全部规则 `enabled: false` + `ui_hints.hidden: true`。

#### 4.1.2 `meta/core/state_machine_loader.py`（新增）

```python
@dataclass(frozen=True)
class StateMachine:
    object_type: str
    state_field: str
    states: Tuple[str, ...]                     # 有序：states 目录 seq，否则按规则出现序
    transitions: Dict[str, Tuple[str, ...]]     # from -> 有序 to 列表（含空元组）
    terminal: Tuple[str, ...]                   # states.category == 'terminal'；无目录时=无出边状态
    rules: Tuple[Any, ...]

def get_state_machine(object_type: str, state_field: str = 'status') -> Optional[StateMachine]
def reload() -> None
```

- 读取顺序：`meta.core.models.registry.get(object_type)` → 取 `get_rule_provider().get_rules_by_type(obj, RuleType.STATE_TRANSITION)` 且 `rule.state_field == state_field`；registry 未命中时直读 `meta/schemas/<object_type>.yaml`，对 `rules` 中 `type == 'state_transition'` 的条目调用 `yaml_loader.parse_state_transition`。
- `states` 目录同样 registry 优先、YAML 兜底（复用 `MetaObject.states`）。
- `transitions`：遍历规则，按规则出现顺序把 `to_state` 追加到每个 `from_states`；为 `states` 中每个状态补齐空元组键。**不排序**，保证与旧字典逐项相等。
- 无任何声明 → 返回 `None`（调用方 fail-open，D-M2-4）。
- 进程内缓存 + `reload()`。

#### 4.1.3 守卫 / 服务替换

`sales_order_guard_service.py`：

- 删除模块常量 `SCHEDULE_STATUSES`、`SCHEDULE_TERMINAL`、`SCHEDULE_TRANSITIONS`（L248-L254）。
- `validate_schedule_write` 内 R-SCH-9 段（L1678-L1696）改为：

```python
machine = get_state_machine(SCHEDULE_OBJECT)
if machine is None:
    logger.warning('[sales_order_guard] sales_order_schedule 未声明状态机，跳过 R-SCH-9')
elif not _is_blank(new_status) and str(new_status) not in machine.states:
    raise ... f'计划行状态 {new_status} 不属于 {"/".join(machine.states)}'
elif not is_create and not _is_blank(new_status):
    ...
    if str(old_status) in machine.terminal: 同原文案
    allowed = machine.transitions.get(str(old_status), ()) 同原文案
```

错误码 `SCHEDULE_STATUS_INVALID`、字段 `status`、两条提示文案逐字保持。

`serial_number_service.py`：

- 删除模块常量 `TRANSITIONS`（L84-L96）；`USAGE_STATUSES` 改为声明派生（模块加载时 `get_state_machine('serial_number', 'usage_status')`，取 `.states`，缺失时为空元组）。
- `change_status`（L683）改用 `machine.transitions.get(current, ())`。
- 退货回库分支（L868）同样改用机器映射；`SERIAL_STATUS_TRANSITION_INVALID` 与文案不变。
- `OUTBOUND_ALLOWED` / `LINE_TABLE_BY_DOC` 等非状态图常量保留（属于服务规则，不在 FR-004 范围）。

### 4.2 FR-005 审批注册表与金额优先级元数据化

#### 4.2.1 元模型与声明

`MetaObject` 新增 `approval: Dict[str, Any] = field(default_factory=dict)`；`yaml_loader.build_meta_object` 新增 `approval=data.get("approval") or {}`。

四个 BO 增加：

```yaml
approval:
  table: purchase_orders          # 各对象对应表
  amount_fields: [gross_amount, net_amount, total_amount, amount]
```

| 对象 | table |
|---|---|
| `purchase_order` | `purchase_orders` |
| `transfer_order` | `transfer_orders` |
| `requisition` | `requisitions` |
| `service_request` | `service_requests` |

#### 4.2.2 `meta/core/approval_meta_loader.py`（新增）

```python
DEFAULT_AMOUNT_FIELDS = ('gross_amount', 'net_amount', 'total_amount', 'amount')

def get_approval_meta(object_type: str) -> Dict[str, Any]
# -> {'table': str, 'amount_fields': Tuple[str, ...]}
# registry 优先、YAML 兜底；amount_fields 缺失时回落 DEFAULT_AMOUNT_FIELDS（唯一默认，不再逐对象复制）
def reload() -> None
```

#### 4.2.3 服务替换

`document_approval_service.py`：

- 删除 `APPROVAL_TABLES`（L31-L36）与 `_AMOUNT_FIELDS`（L39）。
- `resolve`：`meta = get_approval_meta(object_type)`；`table = meta['table']`；表为空 → 沿用 `reason='invalid_object'`。
- `_amount_of` 增加 `amount_fields` 参数（默认取 loader 默认值），调用处传 `meta['amount_fields']`；取值优先级与旧顺序一致。

### 4.3 FR-006 单据流规则数据化收口

- `v214` / `v215` / `v222` 保持不动；新增 `check_rule_convergence.py` 守卫，扫描 `meta/migrations/*.py` 并禁止：
  - `if rule_id` / `elif rule_id` / `rule_id ==` 等按规则分支；
  - `from meta.services` / `from meta.core.doc_flow` / `import meta.core.doc_flow` 等运行时依赖。
- 新增 `validate_doc_flow_rules(rules, registry)`（见 §4.4），对迁移基线规则做结构校验；`verify()` 已由既有测试覆盖。

### 4.4 FR-012 加载期一致性校验

新增 `meta/core/rule_declaration_validator.py`：

| 校验器 | 错误码 | 判定 |
|---|---|---|
| `validate_state_machines(registry)` | `STATE_FIELD_MISSING` | `state_field` 不在对象字段（`id` / `db_column`） |
| | `STATE_UNDECLARED` | `from_states` / `to_state` 不在 `states` 目录 |
| | `STATE_TERMINAL_OUTGOING` | `category=terminal` 的状态出现在 `from_states` |
| | `STATE_ORPHAN` | 非 initial 状态入度 0 |
| `validate_approval(registry)` | `APPROVAL_TABLE_UNKNOWN` | `approval.table` 为空或不在表清单 |
| | `APPROVAL_AMOUNT_FIELD_MISSING` | `amount_fields` 中字段不在对象字段 |
| `validate_numbering(registry)` | `NUMBERING_FIELD_MISSING` | `no_field` / `date_field` 不在对象字段 |
| `validate_doc_flow_rules(rules, registry)` | `DOC_FLOW_SOURCE_UNKNOWN` / `DOC_FLOW_TARGET_UNKNOWN` | source/target BO 未注册 |
| | `DOC_FLOW_QTY_FIELD_MISSING` | `source_qty_field` 不在源 BO 字段 |
| | `DOC_FLOW_DUPLICATE` | `rule_id` 重复 |

统一返回 `List[DeclarationError]`（`code / object_type / message`），由 `test_rule_convergence_m2.py` 与 `scripts/check_rule_convergence.py` 断言为空。

### 4.5 静态守卫扩展（FR-013 延续）

`scripts/check_rule_convergence.py` 增加 M2 命中模式（仅限三个文件）：

| 文件 | 禁止模式 |
|---|---|
| `meta/services/sales_order_guard_service.py` | `SCHEDULE_TRANSITIONS = {` / `SCHEDULE_TERMINAL = (` |
| `meta/services/serial_number_service.py` | `^TRANSITIONS = {` |
| `meta/services/document_approval_service.py` | `APPROVAL_TABLES = {` / `_AMOUNT_FIELDS = (` |

新增迁移守卫（`meta/migrations/*.py`）：`rule_id ==` / `if rule_id` / `from meta.services` / `from meta.core.doc_flow` / `import meta.core.doc_flow`。

---

## 5. 任务分解

| WBS | 任务 | 依赖 | 改动面 | 验收 |
|---|---|---|---|---|
| M2-1 | 新增 `state_machine_loader.py` | 无 | 1 新文件 | 单测：两对象机器与基线逐项相等 |
| M2-2 | 两个 YAML 增加 `states` + 规则 | M2-1 | 2 YAML | 加载成功；规则 id 唯一；`hidden` 生效 |
| M2-3 | 计划行守卫改读声明 | M2-1/2 | 1 py | `test_sales_order_schedule_guard.py` 全绿 |
| M2-4 | 序列号服务改读声明 | M2-1/2 | 1 py | `test_serial_number_service.py` 全绿 |
| M2-5 | 元模型 + 审批加载器 + 4 YAML | 无 | 4 文件 + 4 YAML | 4 对象 `approval` 非空 |
| M2-6 | 审批服务改读声明 | M2-5 | 1 py | `test_document_approval.py` 全绿 |
| M2-7 | 加载期校验器 | M2-1/5 | 1 新文件 | 正例为空、负例命中错误码 |
| M2-8 | 静态守卫扩展 | M2-3/4/6 | 1 py | 命中旧常量即 exit 1 |
| M2-9 | M2 等价性测试 | 全部 | 1 新测试 | 全绿 |
| M2-10 | 回归验证 | 全部 | 无 | 目标测试 + `--failed` 无新增失败 |

---

## 6. 测试矩阵

| 层 | 命令 | 通过标准 |
|---|---|---|
| 新用例 | `python d:\filework\test.py --file meta/tests/test_rule_convergence_m2.py` | 全绿 |
| 计划行 | `python d:\filework\test.py --file meta/tests/test_sales_order_schedule_guard.py` | 全绿 |
| 序列号 | `python d:\filework\test.py --file meta/tests/test_serial_number_service.py` | 全绿 |
| 审批 | `python d:\filework\test.py --file meta/tests/test_document_approval.py` | 全绿 |
| 单据流 | `--file meta/tests/test_doc_flow.py`、`test_doc_flow_stage2_edges.py`、`test_doc_flow_stage3_reversal.py`、`test_shipment_issue_doc_flow.py`、`test_shipment_return_doc_flow.py` | 全绿 |
| 状态目录 | `--file meta/tests/test_lifecycle_rule_coverage.py`、`test_state_field_matrix.py` | 全绿 |
| 守卫 | `python scripts/check_rule_convergence.py` | exit 0 |
| 回归 | `python d:\filework\test.py --failed` | 无新增失败 |

### 6.1 等价性测试清单（`test_rule_convergence_m2.py`）

1. `test_schedule_machine_matches_legacy`：`states == ('planned','confirmed','completed','cancelled')`，`transitions == {'planned': ('confirmed','cancelled'), 'confirmed': ('completed','cancelled'), 'completed': (), 'cancelled': ()}`，`terminal == ('completed','cancelled')`。
2. `test_serial_machine_matches_legacy`：8 状态 + 7 条边逐项等于旧 `TRANSITIONS`（含元组顺序）。
3. `test_schedule_terminal_cannot_move` + 既有 `test_sales_order_schedule_guard.py`：终态 / 非法跳转 / 未知状态的文案、`field_name`、`rule` 零变化。
4. `test_serial_states_equal_service_constant` + 既有 `test_serial_number_service.py`：非法跳转与 scrapped 终态文案、规则号零变化。
5. `test_approval_meta_matches_legacy`：4 对象 table 与金额优先级等于旧常量。
6. `test_approval_amount_priority`：四字段依次取值 + 全空返回 0.0。
7. `test_state_machine_validator_negative`：未声明状态 / 终态出边 / 孤儿状态 / 字段缺失各 1 例。
8. `test_approval_validator_negative`：表为空、金额字段不存在各 1 例。
9. `test_numbering_validator_negative`：`no_field` / `date_field` 不存在各 1 例。
10. `test_doc_flow_baseline_unchanged`：`v214.RULE` + `v215.RULES` + `v222` 规则集合与基线快照一致。
11. `test_static_guard_passes`：调用守卫脚本返回 0。

---

## 7. 风险与回滚

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 规则加入后 `/state_transitions` 多出按钮 | 中 | 中 | 全部 `ui_hints.hidden: true`；用例断言输出仍为空 |
| 通用 RuleEngine 抢跑改状态 | 中 | 高 | `triggers: []`，不注册自动触发（D-M2-3） |
| `app_registry` 由规则推导状态字段 | 低 | 中 | 回归 `test_app_registry*` / 启动加载；`state_field` 与实际业务字段一致 |
| 规则顺序导致 `transitions` 元组顺序漂移 | 中 | 中 | 用例逐项比对元组；YAML 顺序固化在 §4.1.1 |
| registry 未加载时守卫读不到声明 | 中 | 中 | loader 直读同名 schema 兜底；仍失败则 fail-open + WARNING |
| 审批表名与 BO 实际表不一致 | 低 | 中 | FR-012 `APPROVAL_TABLE_UNKNOWN` 在 CI 拦截 |
| 迁移守卫误伤历史迁移 | 低 | 低 | 仅匹配分支/依赖导入模式，`v214/v215/v222` 均为纯数据 |

**回滚**：删除 YAML 声明 + 还原三个服务文件即可回到旧常量路径；无 DDL、无数据迁移、无对外契约变更。

---

## 8. 完成定义（DoD）

- [x] `SCHEDULE_TRANSITIONS` / `SCHEDULE_TERMINAL` / `TRANSITIONS` / `APPROVAL_TABLES` / `_AMOUNT_FIELDS` 全部删除。
- [x] 两个状态图与四个审批对象的结果与旧常量逐项相等。
- [x] 非法流转的错误码、文案、HTTP 状态零变化；`/state_transitions` 输出零变化。
- [x] 新增状态 / 新审批对象只改 YAML。
- [x] FR-012 四类校验器正例为空、负例命中稳定错误码。
- [x] 静态守卫 exit 0；目标测试全绿；`--failed` 无新增失败。

---

## 9. 执行记录

| 日期 | WBS | 状态 | 备注 |
|---|---|---|---|
| 2026-11-07 | 方案编制 | 完成 | 本文件 |
| 2026-11-07 | M2-1 | 完成 | 新增 `meta/core/state_machine_loader.py`（registry 优先 / YAML 兜底 / 缓存 / reload） |
| 2026-11-07 | M2-2 | 完成 | `sales_order_schedule.yaml` 3 条规则 + `serial_number.yaml` 7 条规则，全部 `enabled: false` + `hidden: true` |
| 2026-11-07 | M2-3 | 完成 | `SCHEDULE_STATUSES/TERMINAL/TRANSITIONS` 删除，R-SCH-9 改读声明，文案与错误码不变 |
| 2026-11-07 | M2-4 | 完成 | `TRANSITIONS` 删除，`change_status` / 退货回库改读声明 |
| 2026-11-07 | M2-5 | 完成 | `MetaObject.approval` + `approval_meta_loader.py` + 4 个 BO YAML |
| 2026-11-07 | M2-6 | 完成 | `APPROVAL_TABLES` / `_AMOUNT_FIELDS` 删除，`_amount_of` 接收声明的优先级 |
| 2026-11-07 | M2-7 | 完成 | 新增 `meta/core/rule_declaration_validator.py`（状态机 / 审批 / 编号 / 单据流） |
| 2026-11-07 | M2-8 | 完成 | 守卫新增 M2 常量模式 + 迁移脚本 `rule_id` 分支 / `meta.core.doc_flow` 依赖 |
| 2026-11-07 | M2-9 | 完成 | 新增 `meta/tests/test_rule_convergence_m2.py`（15 例全绿） |
| 2026-11-07 | M2-10 | 完成 | 计划行 / 序列号 / 审批 / 单据流 / 生命周期 / 状态目录 / app_registry 全绿；`--failed` 仅历史遗留失败 |
| 2026-11-07 | 提交 | 待办 | 等待用户授权 git commit（含 M1 未提交改动） |

### 9.1 执行偏差说明

1. **D-M2-3 落地为 `enabled: false`**：`MetaStateTransition.__post_init__` 会把空 `triggers`
   默认成 `before_update`，无法用 `triggers: []` 表达「不接引擎」。`enabled: false`
   使 `get_rules_by_trigger` 不返回该规则，`get_rules_by_type` 仍可读，符合决议目的。
2. **不使用 `STATE_DUPLICATE_EDGE`**：`purchase_order.yaml` 已存在同一 `(from, to)` 的
   多条规则（不同 action 落同一状态），属合法数据；Spec FR-012 验收也未要求查重。
3. **`USAGE_STATUSES` 保留为常量元组**：拦截器直接 `from ... import USAGE_STATUSES`；
   改为声明派生会引入导入期耦合。等价性由 `test_serial_states_equal_service_constant`
   断言其与 `machine.states` 完全一致。
4. **迁移守卫范围收窄**：历史迁移中有 5 处合法的 `from meta.services`（数据回填），
   因此只禁止 `rule_id` 分支与 `meta.core.doc_flow` 运行时依赖。
5. **`approval.amount_fields` 按对象声明**：`transfer_order` / `requisition` /
   `service_request` 无金额字段，显式声明 `[]`（金额恒 0.0，与旧 `_amount_of` 一致）；
   `purchase_order` 声明四字段优先级。
6. **`NUMBERING_TABLE_UNKNOWN` 未实现**：`type_table: type_definitions` 不是已注册 BO
   的 `table_name`，静态校验会误报；编号只校验 `no_field` / `date_field` 字段存在。
