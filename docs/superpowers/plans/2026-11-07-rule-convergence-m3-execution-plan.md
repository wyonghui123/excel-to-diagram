# 执行方案：规则化收敛 M3（权限层级 / 组织边界 / Provider facade / 统一 explain）

> 依据：[2026-11-07 规则化收敛 Spec](../specs/2026-11-07-rule-convergence-spec.md) v1.3 §3 FR-002 / FR-003 / FR-010 / FR-011
> 前置：[M1 执行方案](./2026-11-07-rule-convergence-m1-execution-plan.md)（层级映射已部分改 loader）、[M2 执行方案](./2026-11-07-rule-convergence-m2-execution-plan.md)
> 决议：TBD-4 保持现状（`sub_domain` 为授权叶子，`service_module` 不升第 5 锚点）
> 原则：先声明、后替换读取入口；对外错误码 / HTTP 状态 / 用户提示零变化；无 DDL、无数据迁移

---

## 1. 范围

### 1.1 本轮实施

| FR | 内容 | 目标载体 |
|---|---|---|
| FR-002 | 六张层级/维度映射收敛到 `hierarchies.yaml`，`hierarchy_loader` 唯一入口；`dimension_levels` 声明 `level_type / parent_level / scope_anchor / owner_field`；深度由 profile 决定 | `hierarchies.yaml` + `meta/core/hierarchy_loader.py` + 6 个消费者 |
| FR-003 | `REQUIRED_ORG_SCOPE_BOS`（43 项）改为「扫描 BO 推导候选 + 显式豁免 YAML（带理由）」 | `meta/schemas/org_scope_exemptions.yaml` + `meta/core/org_scope_validator.py` |
| FR-010 | `RuleProvider` 增加 DB 规则门面（doc_flow / permission_rule），业务调用方不再直连各域 store | `meta/core/rule_provider.py` + 5 处调用点 |
| FR-011 | 统一 explain / dry-run：默认值、权限拒绝、状态流转拒绝、审批命中 | 新增 `meta/core/rule_explainer.py` + `POST /api/v2/bo/<object_type>/rules/explain` |

### 1.2 明确不做

- 不改 `dimension_scope_engine` 的授权语义（仍只认 `scope_anchor=true` 的 4 层）。
- 不把 `org_scope` 求值器改成声明驱动（Phase 3 内容）。
- 不新增 `RuleType`；不新增 DDL；不改迁移脚本已有数据。
- 不改 `meta/api/unified_permission_api.py` / `meta/api/permission_rule_api.py` 对 DAO 的直接使用（属规则管理端，白名单）。
- 不引入规则在线热更新 / 多租户隔离。

---

## 2. 关键决议

| 编号 | 决议 | 理由 |
|---|---|---|
| D-M3-1 | `dimension_levels` 复用 `hierarchies.yaml` 的 `levels[]`，不新增文件；新增字段 `level_type / parent_level / owner_field`，保留 `kind / parent_object / scope_anchor` | 一份声明两套语义（展示层级 + 授权层级），避免第二次双写 |
| D-M3-2 | 深度由顶层 `dimension_profiles` 声明（`default: 4` / `full: 6`），loader 提供 `get_child_type_map(profile)` | FR-002「profile 只决定默认深度」；4/6 层不是二选一 |
| D-M3-3 | 非层级实体（relationship / annotation / org / user）放顶层 `extra_entity_tables`，不进 `levels[]` | 它们不是维度链成员；避免污染 `get_table_map()` 的 6 层契约 |
| D-M3-4 | 模块级常量名（`RESOURCE_TABLE_MAP` 等）保留，但值必须由 loader 推导；静态守卫只禁**字面量定义** | 这些名字被 `meta/api/*` 大量 import，删名会扩大改动面与回归风险 |
| D-M3-5 | FR-003 候选判定 = 「声明了 `org_scope`」∪「字段名匹配 `^org_id$|_org_id$`」；豁免只能进 YAML 且理由非空 | 实现 V6 原意（有组织字段/显式声明都必须处理），同时把「执行组织字段」显式豁免 |
| D-M3-6 | 取消「43 项期望 mode 逐项比对」；mode 合法性/字段存在性仍由 V1-V5 校验 | 期望 mode 也是硬编码清单的一部分；结构校验已能捕获漂移 |
| D-M3-7 | FR-010 门面方法放 `RuleProvider` 实例 + 模块级便捷函数；懒 import 各域 store | 避免循环依赖；调用方只改 import 行 |
| D-M3-8 | FR-011 统一响应信封固定 8 字段；四类场景各自适配，不改底层服务返回 | 对外接口一次定型，内部实现可替换 |
| D-M3-9 | explain 只读：default 走既有 `dry_run_defaults`；审批走 `DocumentApprovalService.resolve`；状态流转走 `get_state_machine`；权限走 `PermissionExplainer` | 满足「不落库、不改变数据」 |

---

## 3. 交付物

| 编号 | 交付物 | 路径 |
|---|---|---|
| D1 | 层级声明扩展 | `meta/schemas/hierarchies.yaml` |
| D2 | loader 扩展 | `meta/core/hierarchy_loader.py` |
| D3 | 6 个消费者去字面量 | `permission_dimension_engine.py`、`management_dimension_engine.py`、`condition_permission_service.py`、`chain_owner_resolver.py`、`dimension_scope_engine.py`、`meta/core/value_help_providers.py` |
| D4 | 组织边界豁免声明 | 新增 `meta/schemas/org_scope_exemptions.yaml` |
| D5 | 组织边界推导 | `meta/core/org_scope_validator.py` |
| D6 | Provider facade | `meta/core/rule_provider.py` + 5 处调用点 |
| D7 | 统一 explain | 新增 `meta/core/rule_explainer.py` |
| D8 | explain HTTP 入口 | `meta/api/bo_api.py` |
| D9 | 静态守卫扩展 | `scripts/check_rule_convergence.py` |
| D10 | M3 等价性 / 回归测试 | 新增 `meta/tests/test_rule_convergence_m3.py` |
| D11 | 既有组织边界测试适配 | `meta/tests/test_org_scope_declarations.py` |
| D12 | 执行记录 | 本文件 §9 |

---

## 4. 详细设计

### 4.1 FR-002 层级 / 维度单一真源

#### 4.1.1 `hierarchies.yaml` 声明扩展

每个 `levels[]` 条目补齐（示例 level 3）：

```yaml
- level: 3
  object: sub_domain
  kind: entity                 # 兼容既有消费者
  level_type: entity           # 新增：entity | association
  parent_level: 2              # 新增：父层 level，根为 null
  owner_field: owner_id        # 新增：数据授权 owner 追溯列；association 为 null
  scope_anchor: true           # 既有：数据授权只认 true
  # ... 其余字段不变
```

- level 0 `parent_level: null`；level 6 relationship `level_type: association`、`owner_field: null`、`parent_level: 5`。
- 顶层新增：

```yaml
dimension_profiles:
  default: 4        # product → sub_domain
  full: 6           # product → business_object

extra_entity_tables:
  - {object: relationship, table_name: relationships}
  - {object: annotation,   table_name: annotations}
  - {object: org,          table_name: orgs, parent_field: parent_id, self_parent: true}
  - {object: user,         table_name: users}
```

#### 4.1.2 `hierarchy_loader.py` 扩展

新增：

```python
@dataclass(frozen=True)
class DimensionLevel:
    level: int
    object: str
    level_type: str                    # entity | association
    parent_level: Optional[int]
    parent_object: Optional[str]
    scope_anchor: bool
    owner_field: Optional[str]
    table_name: Optional[str]
    foreign_key_field: Optional[str]
    display_field: Optional[str]
    code_field: Optional[str]

def get_dimension_levels() -> List[DimensionLevel]
def get_dimension_profile_depth(profile: str = 'default') -> int
def get_child_type_map(profile: str = 'default') -> Dict[str, List[str]]
def get_extra_entity_map() -> Dict[str, Dict[str, Any]]
def get_extra_entity_table_map(*objects: str) -> Dict[str, str]
```

- `get_dimension_levels()`：读 `levels[]` **全部**条目（含 association），按 `level` 排序；缺失新字段时按兜底推导（`level_type=kind`、`parent_level=前一实体层`、`owner_field='owner_id'` for entity），并 `print` WARNING。
- `get_child_type_map(profile)`：
  - `depth = get_dimension_profile_depth(profile)`；
  - 对 `i < depth-1`，取 `levels[i+1].parent_level == levels[i].level` 的边 → `parent.object: [child.object]`；
  - 为每个被纳入的对象补空列表键；
  - 追加 `extra_entity_tables` 中 `self_parent: true` 的对象自环（`org: ['org']`）。
  - 实测期望：
    - `default` → `product:[version]`、`version:[domain]`、`domain:[sub_domain]`、`sub_domain:[]`（不含 service_module/business_object）。
    - `full` → 前 4 层同上 + `sub_domain:[service_module]`、`service_module:[business_object]`、`business_object:[]`，并按声明追加 `org:['org']`。
- `get_extra_entity_map()`：读 `extra_entity_tables`，返回 `{object: {...}}`；YAML 缺失返回 `{}`。
- `get_extra_entity_table_map(*objects)`：`{obj: table_name}`，`objects` 为空返回全部。
- `reload()` 清空新增缓存。

#### 4.1.3 消费者替换（只做「去字面量」，不改调用点语义）

| 文件 | 现状 | 改为 |
|---|---|---|
| `permission_dimension_engine.py` | `RESOURCE_TABLE_MAP.update({'relationship':..., 'annotation':...})`；`CHILD_TYPE_MAP` 字面量 | `update(get_extra_entity_table_map('relationship','annotation'))`；`CHILD_TYPE_MAP = get_child_type_map('default')` |
| `management_dimension_engine.py` | `CHILD_TYPE_MAP` 字面量 | `CHILD_TYPE_MAP = get_child_type_map('default')` |
| `condition_permission_service.py` | `RESOURCE_TABLE_MAP.update({'org','user'})`；`CHILD_TYPE_MAP` 6 层 + org 自环；`PARENT_FIELD_MAP.update({'org': 'parent_id'})` | `update(get_extra_entity_table_map('org','user'))`；`get_child_type_map('full')`；`PARENT_FIELD_MAP.update({k: v['parent_field'] for k, v in get_extra_entity_map().items() if v.get('parent_field')})` |
| `chain_owner_resolver.py` | 已派生 | 不变（保留为 loader 推导） |
| `dimension_scope_engine.py` | `VERSION_AWARE_BOS['relationship'] = 'relationships'` | `VERSION_AWARE_BOS.update(get_extra_entity_table_map('relationship'))` |
| `meta/core/value_help_providers.py` | 已派生 | 不变 |

### 4.2 FR-003 组织边界清单推导化

#### 4.2.1 候选与豁免

新增 `meta/schemas/org_scope_exemptions.yaml`：

```yaml
# 组织边界一致性校验豁免清单（Spec 24 V6）
# 仅用于「字段名像组织字段、但不是 owning org」的对象；理由必填。
exemptions:
  - object: purchase_order
    reason: "org_id 为法人执行组织，owning org 由 purchase_org_id 声明（Spec 24 §4.1）"
```

- 实施时先用一次性脚本列出全部「含 `org_id` / `*_org_id` 字段但未声明 `org_scope`」的 BO，逐个判定是否需要豁免并写理由；脚本不落盘。
- 豁免项必须在 `reason` 非空，否则校验报错。

#### 4.2.2 `org_scope_validator.py`

- 删除 `REQUIRED_ORG_SCOPE_BOS`。
- 新增错误码 `ORG_SCOPE_EXEMPTION_REASON_MISSING`。
- 新增：

```python
EXEMPTIONS_PATH = meta/schemas/org_scope_exemptions.yaml
def load_exemptions() -> Dict[str, str]          # object -> reason；reason 为空抛 OrgScopeDeclarationError
def org_columns(meta_obj) -> Set[str]            # id/db_column 匹配 ^org_id$|_org_id$
def candidate_org_scope_bos(registry) -> Set[str] # 声明 org_scope ∪ org_columns 非空
def required_org_scope_bos(registry) -> Set[str]  # candidates - exemptions
```

- `validate_registry` 的 V6 段改为：

```python
exemptions = load_exemptions()          # 理由为空直接产生错误
for bo_id in sorted(required_org_scope_bos(registry_obj)):
    obj = registry_obj.get(bo_id)
    if obj is None:
        continue
    if not (getattr(obj, 'org_scope', None) or {}):
        errors.append(OrgScopeDeclarationError(
            ORG_SCOPE_UNDECLARED, '有组织字段/显式登记但未声明 org_scope', bo_id))
```

- 移除「expected_mode 逐项比对」；`validate_object` 的 V1-V5 保持不变。
- 豁免生效但对象同时声明了 `org_scope` → 视为声明优先，不报错（豁免只影响「必须声明」判定）。

### 4.3 FR-010 统一 RuleProvider facade

`meta/core/rule_provider.py` 新增（懒 import，避免循环）：

```python
class RuleProvider:
    # 既有 YAML 方法不变 ...

    def get_doc_flow_rule(self, data_source, rule_id: str) -> Optional[Dict[str, Any]]:
        from meta.core.doc_flow_rule_store import get_rule
        return get_rule(data_source, rule_id)

    def upsert_doc_flow_rules(self, data_source, rules) -> int:
        from meta.core.doc_flow_rule_store import upsert_rules
        return upsert_rules(data_source, rules)

    def list_permission_rules(self, db_path=None, resource_type=None):
        from meta.core.permission_rule_v2_dao import PermissionRuleV2DAO
        from meta.core.db_path import get_meta_db_path
        return PermissionRuleV2DAO(db_path or get_meta_db_path()).list_all(resource_type)


def get_doc_flow_rule(data_source, rule_id): ...
def upsert_doc_flow_rules(data_source, rules): ...
def list_permission_rules(db_path=None, resource_type=None): ...
```

替换调用点（只改 import，调用行不变）：

| 文件 | 行 | 原 import |
|---|---|---|
| `meta/services/shipment_service.py` | 436 | `from meta.core.doc_flow_rule_store import get_rule` |
| `meta/core/doc_flow_batch_engine.py` | 186 | 同上 |
| `meta/core/doc_flow_reversal.py` | 299 | 同上 |
| `meta/core/doc_flow_attach.py` | 49 | 同上 |
| `meta/core/doc_flow_derive_engine.py` | 397 | 同上 |
| `meta/core/app_registry.py` | 888 | `from meta.core.doc_flow_rule_store import (...)` → 实施时确认用途；若为建表/种子，改用 `upsert_doc_flow_rules` 门面 |

- `meta/api/unified_permission_api.py` 保持直连 DAO（规则管理端白名单）。
- 迁移脚本 `v214/v215/v222` 不动。
- **覆盖边界**：审批规则（`approval_policies / approval_policy_conditions / approval_policy_steps`）
  的查询已封装在 `DocumentApprovalResolver.resolve`，业务调用方不直连表，故本轮不新增
  approval store 门面；`config_rule` 是 BO schema（`meta/schemas/config_rule.yaml`），
  不是 DB 规则表，不涉及 store 直连。两者均不违反「业务调用方不直连各域 store」。

### 4.4 FR-011 统一 explain / dry-run

#### 4.4.1 `meta/core/rule_explainer.py`（新增）

```python
SCENARIOS = ('default', 'permission', 'state_transition', 'approval')

def explain(object_type: str, scenario: str, *,
            data: dict | None = None,
            user_id: int | None = None,
            action_id: str = 'read',
            record_id=None,
            state_field: str = 'status',
            from_state=None, to_state=None,
            data_source=None) -> dict
```

统一信封：

```python
{
  'ok': bool,
  'scenario': str,
  'decision': str,        # applied|skipped|granted|denied|allowed|rejected|matched|not_matched
  'rule_id': str | None,
  'source': str,          # yaml | db | code
  'reason': str,
  'factors': dict,
  'elapsed_ms': float,
}
```

四类适配：

| scenario | 数据来源 | decision 映射 |
|---|---|---|
| `default` | `ActionExecutor.dry_run_defaults(meta_object, data)` | 命中且有值 → `applied`；`skip_reason` 非空 → `skipped` |
| `permission` | `get_permission_explainer().explain(user_id, object_type, action_id)` | `granted` / `denied`；`rule_id` 取 `unified_permission_rules` 命中项（无则 None） |
| `state_transition` | `get_state_machine(object_type, state_field)` | `allowed` / `rejected`；`rule_id` = 匹配 `from_states`/`to_state` 的声明规则 id |
| `approval` | `DocumentApprovalService(data_source).resolve(object_type, record_id)` | `matched` / `not_matched`；`rule_id` = 命中 policy 的标识 |

- 非法 `scenario` / 未注册对象 → 抛 `ValueError`（API 层转 400）。
- `elapsed_ms` 用 `time.perf_counter()` 计算并四舍五入 3 位。
- 全程只读：不调用任何 `upsert/update/insert`。

#### 4.4.2 HTTP 入口

在 `meta/api/bo_api.py`（`bo_bp` 前缀 `/api/v2/bo`）新增：

```python
@bo_bp.route('/<object_type>/rules/explain', methods=['POST'])
@login_required
def explain_rules(object_type):
    payload = request.get_json(silent=True) or {}
    scenario = payload.get('scenario')
    if scenario not in SCENARIOS or registry.get(object_type) is None:
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST',
                        'message': 'scenario 或 object_type 非法'}}), 400
    result = explain(object_type, scenario, data=payload.get('data'), ...)
    return jsonify({'success': True, 'data': result})
```

- 不新增权限码；沿用与同文件其他 v2 路由一致的 `@login_required`。

### 4.5 静态守卫扩展（FR-013 延续）

`scripts/check_rule_convergence.py`：

| 文件 | 新增禁止模式 |
|---|---|
| `meta/services/permission_dimension_engine.py` | `CHILD_TYPE_MAP = {` |
| `meta/services/management_dimension_engine.py` | `CHILD_TYPE_MAP = {` |
| `meta/services/condition_permission_service.py` | `CHILD_TYPE_MAP = {` |
| `meta/services/chain_owner_resolver.py` | 既有 |
| `meta/services/dimension_scope_engine.py` | 既有 + `VERSION_AWARE_BOS\[` 赋值字面量 |
| `meta/services/*.py`、`meta/core/doc_flow_*.py`（排除 `rule_provider.py`） | `from meta.core.doc_flow_rule_store import` |
| `meta/services/*.py` | `from meta.core.permission_rule_v2_dao import` |
| `meta/services/*.py`、`meta/core/*.py`（排除 loader/provider/engine） | `for \w+ in [\w\.]*\.rules\b` |

豁免白名单：`rule_provider.py`、`hierarchy_loader.py`、`rule_executor.py`、`permission_explainer.py`、`rule_explainer.py`。

---

## 5. 任务分解

| WBS | 任务 | 依赖 | 改动面 | 验收 |
|---|---|---|---|---|
| M3-1 | `hierarchies.yaml` 补 `level_type/parent_level/owner_field` + `dimension_profiles` + `extra_entity_tables` | 无 | 1 文件 | YAML 可加载，既有 6 层映射不变 |
| M3-2 | `hierarchy_loader.py` 新增 5 个 API + 缓存 + reload | M3-1 | 1 文件 | 单元测试取到 default/full 两套 child map |
| M3-3 | 6 个消费者去字面量 | M3-2 | 6 文件 | 静态守卫命中数 0；旧测试全绿 |
| M3-4 | 扫描候选 BO，生成 `org_scope_exemptions.yaml` | 无 | 1 新文件 | 每个豁免有非空理由 |
| M3-5 | `org_scope_validator.py` 推导化 + 删 43 项清单 | M3-4 | 1 文件 | `ORG_SCOPE_UNDECLARED` 仍可被新 BO 触发 |
| M3-6 | `test_org_scope_declarations.py` 适配 + 新增负例 | M3-5 | 1 文件 | 全绿 |
| M3-7 | `rule_provider.py` 新增 DB 门面 + 5 处调用点替换 | 无 | 6 文件 | doc_flow 测试全绿 |
| M3-8 | 新增 `rule_explainer.py` | M2 loader、M3-7 | 1 新文件 | 四场景信封字段齐全 |
| M3-9 | `bo_api.py` 新增 explain 路由 | M3-8 | 1 文件 | 200/400 符合契约 |
| M3-10 | 扩展静态守卫 | M3-3/5/7 | 1 文件 | exit 0 |
| M3-11 | 新增 `test_rule_convergence_m3.py` | 全部 | 1 新文件 | 全绿 |
| M3-12 | 目标回归 + `--failed` 串行 | 全部 | 无 | 无新增失败 |

---

## 6. 测试矩阵

| 层 | 命令 | 通过标准 |
|---|---|---|
| 新用例 | `python d:\filework\test.py --file meta/tests/test_rule_convergence_m3.py` | 全绿 |
| 组织边界 | `python d:\filework\test.py --file meta/tests/test_org_scope_declarations.py` | 全绿 |
| 权限维度 | `python d:\filework\test.py --file meta/tests/test_dimension_scope_engine.py` | 全绿 |
| 权限引擎 | `python d:\filework\test.py --file meta/tests/test_permission_dimension_api.py` | 全绿 |
| 管理维度 | `python d:\filework\test.py --file meta/tests/test_management_dimension_api.py` | 全绿 |
| 单据流 | `python d:\filework\test.py --file meta/tests/test_doc_flow.py` | 全绿 |
| 单据流回归 | `python d:\filework\test.py --file meta/tests/test_doc_flow_stage2_edges.py` | 全绿 |
| 发货 | `python d:\filework\test.py --file meta/tests/test_shipment_issue_doc_flow.py` | 全绿 |
| 审批 | `python d:\filework\test.py --file meta/tests/test_document_approval.py` | 全绿 |
| 守卫 | `python scripts/check_rule_convergence.py` | exit 0 |
| 全量回归 | `python d:\filework\test.py --failed` | 无新增失败（仅历史遗留） |

`test_rule_convergence_m3.py` 用例清单：

1. `test_table_parent_display_code_equivalent`：6 层 × 4 类映射与基线快照逐项相等。
2. `test_child_type_map_default_profile`：default = 4 层，`sub_domain == []`。
3. `test_child_type_map_full_profile`：full 含 `sub_domain→service_module→business_object` + `org:['org']`。
4. `test_scope_chain_is_four_layers`：`get_scope_chain() == ['product','version','domain','sub_domain']`。
5. `test_dimension_levels_declared`：每层 `level_type/parent_level/scope_anchor/owner_field` 非缺失；`scope_anchor` 只在 entity 层。
6. `test_child_type_is_derived_not_literal`：源码扫描三个服务文件无 `CHILD_TYPE_MAP = {`。
7. `test_org_scope_candidate_detection`：构造含 `org_id` 的假 BO 未声明 → `ORG_SCOPE_UNDECLARED`。
8. `test_org_scope_exemption_requires_reason`：空理由 → `ORG_SCOPE_EXEMPTION_REASON_MISSING`。
9. `test_org_scope_exemption_suppresses`：带理由豁免后不报错。
10. `test_rule_provider_doc_flow_facade`：门面与直连 store 返回同一条规则。
11. `test_explain_envelope_all_scenarios`：四场景均返回 8 字段，`elapsed_ms >= 0`。
12. `test_explain_is_read_only`：调用前后业务表行数不变。
13. `test_static_guard_passes`：`run_checks() == []`。

---

## 7. 风险与回滚

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| `levels[]` 新增字段被其他严格 YAML 校验拒绝 | 低 | 中 | 先跑 `test.py --file meta/tests/test_hierarchy_config.py`；loader 对缺失字段兜底 |
| org 候选扫描命中大量「执行组织」字段 | 中 | 中 | 一次性脚本先出清单；逐条写入豁免 YAML 并给理由 |
| 豁免清单漏项导致启动/CI 失败 | 中 | 低 | V6 只在测试/CI 生效，不阻塞请求链路 |
| facade 懒 import 引入循环依赖 | 低 | 高 | 只在函数体内 import；`rule_provider.py` 不 import 服务模块 |
| explain 副作用 | 低 | 高 | 只调用只读方法；测试断言行数不变 |
| 静态守卫误报 | 低 | 低 | 精确正则 + 白名单 |

**回滚**：全部为读取路径与声明改造，回滚 = 还原本方案涉及文件；无 DDL、无数据迁移、无开关。

---

## 8. 完成定义（DoD）

- [x] 6 个消费者不再以字面量定义 `RESOURCE_TABLE_MAP / PARENT_FIELD_MAP / DISPLAY_FIELD_MAP / CODE_FIELD_MAP / CHILD_TYPE_MAP / HIERARCHY_CHAIN`。
- [x] 二次扫描追加收敛：`value_help_providers / runtime_dimension_resolver / bo_yaml_cache / data_permission_service / audit_derived_fields / permission_dimension_api`。
- [x] `value_help_providers.HIERARCHY_DIMS` 改为 loader 派生，并纳入静态守卫。
- [x] `dimension_levels` 声明含 `level_type / parent_level / scope_anchor / owner_field`；深度由 `dimension_profiles` 决定。
- [x] 未知 profile 抛 `ValueError`（不静默回退 default）。
- [x] 授权链仍为 4 层，`scope_anchor` 是唯一授权判据。
- [x] Python 中不存在 43 项 `REQUIRED_ORG_SCOPE_BOS`；新 BO 漏声明仍报 `ORG_SCOPE_UNDECLARED`。
- [x] 业务调用方不再直接 import `doc_flow_rule_store` / `permission_rule_v2_dao`。
- [x] 业务代码不再直接访问 `meta_obj.rules`（`computation_service` 已改 `RuleProvider`）。
- [x] explain 覆盖四类场景，返回 8 字段，且不落库。
- [x] `scripts/check_rule_convergence.py` exit 0。
- [x] 目标测试全绿；`test.py --failed` 无新增失败。
- [x] 不提交 git（等用户授权）。

---

## 9. 执行记录

| 日期 | 项 | 结果 |
|---|---|---|
| 2026-11-07 | M3-1 / M3-2 | `hierarchies.yaml` 补齐 `level_type / parent_level / owner_field`、`dimension_profiles`、`extra_entity_tables`；loader 新增 6 个 API |
| 2026-11-07 | M3-3 | 6 个消费者全部改为 loader 派生；静态守卫 0 命中 |
| 2026-11-07 | M3-4 / M3-5 / M3-6 | 扫描出 18 个非 owning-org 候选，写入 `org_scope_exemptions.yaml`（理由必填）；删除 `REQUIRED_ORG_SCOPE_BOS`；候选推导 + 豁免负例测试通过 |
| 2026-11-07 | M3-7 | `RuleProvider` 新增 5 个 DB 门面方法；5 处生产调用点改门面；`app_registry` 作为启动注册白名单保留 |
| 2026-11-07 | M3-8 / M3-9 | 新增 `rule_explainer.py`（四场景、8 字段信封）与 `POST /api/v2/bo/<object_type>/rules/explain` |
| 2026-11-07 | M3-10 | 静态守卫扩展：CHILD_TYPE_MAP 字面量、store 直连、元对象规则遍历 |
| 2026-11-07 | M3-11 | `test_rule_convergence_m3.py` 14 例通过 |
| 2026-11-07 | M3-12 | 目标回归全绿；`--failed` rerun 150 项均为历史遗留，新增/修改模块无新增失败 |
| 2026-11-07 | M3-13（遗漏反查） | `value_help_providers.HIERARCHY_DIMS` 改 loader 派生并入守卫；`computation_service` 去掉 `meta_obj.rules` 直接访问；`.rules` 守卫拓宽到 `if/for/while/return` 形式；`dimension_profiles` 加缓存且未知 profile 抛 `ValueError` |
| 2026-11-07 | M3-14（二次扫描） | 追加收敛：`runtime_dimension_resolver`（链/父字段/表名）、`bo_yaml_cache._PARENT_MAP/_TOP_BOS`、`data_permission_service._get_parent_resource`、`permission_dimension_api`（relevant_chain/CHAIN_FALLBACK/VALID_DIMS）、`audit_derived_fields` 层级表名兜底；守卫新增 5 个文件规则 |
| 2026-11-07 | FR-010 边界确认 | approval 规则由 `DocumentApprovalResolver` 封装（无独立 store）；`config_rule` 为 BO schema，本轮无需新增门面 |
| 2026-11-07 | M3-15（回归复核） | 逐项核对派生值与旧字面量等价：授权链 4 层、父字段 5 项、表名 6 项、`VALID_DIMS` 6 项、`HIERARCHY_DIMS` 5 项；`profile` 调用方仅 `default/full`，抛错改动无外部影响；补 `runtime_dimension_resolver` 缺失的 `safe_connect_for_read` 导入（HEAD 既有缺陷，非本次引入） |
| 2026-11-07 | M3-15 验证 | guard exit 0；M3 19、M1 11、org 35、permission_v101 36、hierarchy_filter 25、dimension_scope 7、value_help 9 全绿；`runtime_resolver_v101` 2 项仍因基线 DB 缺 `bo_id` 列失败（历史遗留，与本次改动无关） |
| 2026-11-07 | M3-16（失败用例收尾） | 定位 `test_runtime_resolver_v101` T2/T3 根因：断言依赖真实库 `permission_set_dimension_scopes` 的 ps=1803 / user=1223 运行数据，该数据当前库已不存在（探测确认 0 行），属数据依赖而非代码缺陷。改为自播种临时库（`make_dim_scope_engine_ds` 暴露 `db_path`，复用 `seed_v101_upward_expansion`），并修正 helper WAL 与 `safe_connect_for_read` `journal_mode=DELETE` 冲突；T2/T3 转绿（2 passed, 1 skipped），T1 保留 skip 并改为准确理由（`product.yaml` 仅声明 product 绑定，向上展开路径在该 BO 不可达） |
| 2026-11-07 | M3-17（遗留用例迁移） | `tests/unit/test_runtime_dimension_resolver.py` 21 项从 v070 前模型迁移到 `permission_sets` 体系：新增 `make_runtime_resolver_ds()` 自播种临时库（org_members / org_permission_sets / permission_set_dimension_scopes 含 bo_id），`_get_user_roles` → `_get_user_permission_sets`；同时校正 3 项随 YAML 演进的断言（business_object.domain_id 已 stored + db_column → 冗余字段优先；无冗余场景改用 mock schema）。21 passed |

**关键实测值**

- `get_table_map()`：6 层与旧常量逐项相等。
- `get_child_type_map('default')` = `{product:[version], version:[domain], domain:[sub_domain], sub_domain:[]}`（与旧 permission 引擎一致）。
- `get_child_type_map('full', include_extra=True)` = 旧 condition 服务 7 项（含 `org:['org']`，不含 relationship）。
- `get_scope_chain()` = `['product','version','domain','sub_domain']`。
- `required_org_scope_bos()` = 43 项；豁免 18 项。
- `get_dimension_profiles()` = `{'default': 4, 'full': 6}`；未知 profile 抛 `ValueError`。
- `python scripts/check_rule_convergence.py` → exit 0。

**未提交**：全部改动等待用户授权后 commit。

