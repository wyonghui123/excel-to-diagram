# 执行方案：规则化收敛 M1（编号 / 系统字段 / 层级映射 / 等价性守卫）

> 依据：[2026-11-07 规则化收敛 Spec](../specs/2026-11-07-rule-convergence-spec.md) v1.3
> 决议：TBD-1 仅 M1；TBD-4 保持现状（`sub_domain` 为授权叶子，`service_module` 不升锚点）
> 原则：先迁移载体，再验证等价；M1 不改变任何对外行为与错误码

---

## 1. 范围

### 1.1 本轮实施

| FR | 内容 | 目标载体 |
|---|---|---|
| FR-007 | 单据编号绑定声明化 | 各 BO YAML `numbering:` |
| FR-008 | 系统字段清单声明化 | `shared_properties.yaml#system_fields` |
| FR-009 | 层级映射（表名 / 父子字段 / 显示列）声明化 | `hierarchies.yaml#hierarchies[].levels[]` |
| FR-013 | 等价性回归 + 静态守卫 | 新增测试 + 守卫脚本 |

### 1.2 明确不做

- FR-001 ~ FR-006、FR-010 ~ FR-012（M2 / M3）。
- `dimension_levels` 的代码落地：TBD-4 已确认保持现状，仅保留 Spec 中的目标模型，不在 M1 改权限行为。
- 任何数据库迁移：M1 全部为声明与读取路径改造，无 DDL。
- 错误码、HTTP 状态、放行/拒绝结论的变化。

---

## 2. 交付物

| 编号 | 交付物 | 路径 |
|---|---|---|
| D1 | 元模型支持 `numbering` | `meta/core/models.py`、`meta/core/yaml_loader.py` |
| D2 | 5 个单据的编号声明 | `meta/schemas/{sales_order,purchase_order,receipt,transfer_order,transfer_shipment}.yaml` |
| D3 | 取号服务改为读声明 | `meta/services/document_number_service.py`、`meta/api/bo_api.py` |
| D4 | 系统字段声明与加载 | `meta/schemas/shared_properties.yaml`、`meta/core/system_field_loader.py` |
| D5 | 层级显示列声明与加载 | `meta/schemas/hierarchies.yaml`、`meta/core/hierarchy_loader.py` |
| D6 | 六处重复映射收敛 | 见 §4.3 |
| D7 | 等价性测试 | `meta/tests/test_rule_convergence_m1.py` |
| D8 | 静态守卫 | `scripts/check_rule_convergence.py` |
| D9 | 执行记录 | 本文件 §9 |

---

## 3. 任务分解

| WBS | 任务 | 依赖 | 预估改动面 | 验收 |
|---|---|---|---|---|
| M1-1 | 元模型扩展 `numbering` | 无 | 2 文件 | 加载 sales_order 后 `obj.numbering` 非空 |
| M1-2 | 编号声明迁移与读取改造 | M1-1 | 5 YAML + 2 py | 5 个对象取号结果与改造前一致 |
| M1-3 | 系统字段声明与加载 | 无 | 2 文件 | `SYSTEM_FIELDS` 无硬编码，行为一致 |
| M1-4 | 层级显示列声明与加载 | 无 | 2 文件 | 6 个映射消费者全部读 loader |
| M1-5 | 六处重复映射收敛 | M1-4 | 6 py | 映射结果与改造前逐项一致 |
| M1-6 | 等价性测试 | M1-2/3/5 | 1 新测试 | 全部通过 |
| M1-7 | 静态守卫 | M1-2/3/5 | 1 新脚本 + 1 测试 | 命中旧常量即失败 |
| M1-8 | 全量回归 | 全部 | 无 | 目标测试 + `--failed` 串行确认 |

---

## 4. 详细设计

### 4.1 M1-1 / M1-2：编号声明化（FR-007）

**声明形状（BO YAML 顶层）**

```yaml
numbering:
  no_field: order_no
  date_field: order_date
  type_table: type_definitions
  # 二选一：type_table 绑定，或 scope_bo + fallback_sequence_code
  scope_bo: sales_order
  fallback_sequence_code: SO
  gapless: false
```

**代码改动**

1. `meta/core/models.py`：在 `org_scope` 之后新增 `numbering: Dict[str, Any] = field(default_factory=dict)`。
2. `meta/core/yaml_loader.py`：`build_meta_object` 中新增 `numbering=data.get("numbering") or {}`。
3. `meta/services/document_number_service.py`：
   - 删除模块级 `NUMBERING` 字典；
   - 新增 `_config(object_type)`：从 `meta.core.models.registry.get(object_type)` 读取 `numbering`；缺失时抛既有 `DocumentNumberError`（文案与错误码保持）；
   - `allocate_for` / `validate_external_number` 改调 `_config`；
   - 新增 `get_numbering_map()` 供报告接口使用，返回 `{object_type: config}`，只收录声明了 `numbering` 的对象。
4. `meta/api/bo_api.py`：`L2842` 改为导入 `get_numbering_map`；`L2884-L2890` 改为遍历 `get_numbering_map().items()`。
5. 5 个 YAML 按现有常量逐字段迁移，`on_exhaust` 不进声明（仍由 `number_sequences` 行决定）。

**等价性判据**

- 5 个对象分别调用 `allocate_for`，返回的编号、`field_name`、`rule`、异常类型与改造前一致。
- `_resolve_sequence_id` 的 `type_table` / `scope_bo` / `fallback_sequence_code` 三条分支命中结果一致。
- `validate_external_number` 的四类错误码（`NUMBER_FORMAT_INVALID` / `NUMBER_SEQUENCE_UNSUPPORTED` / `NUMBER_SEQUENCE_UNAVAILABLE` / 既有重复码）不变。

### 4.2 M1-3：系统字段声明化（FR-008）

**声明形状（`meta/schemas/shared_properties.yaml`）**

```yaml
system_fields:
  - id
  - _id
  - tenant_id
  - created_at
  - updated_at
  - created_by
  - updated_by
  - created_date
  - updated_date
  - created_user
  - updated_user
  - is_system
  - system_flag
  - readonly
```

**代码改动**

1. 新增 `meta/core/system_field_loader.py`：读取 `meta/schemas/shared_properties.yaml` 的 `system_fields`，返回 `frozenset`，带进程内缓存与 `reload()`。
2. `meta/services/field_policy_engine.py`：删除 `SYSTEM_FIELDS` 类常量，`_is_system_field` 改调 loader。
3. 读不到声明时回落到现有 14 项并打 WARNING（fail-open，不阻断启动）。

**等价性判据**

- `_is_system_field` 对现有 14 项与 14 项以外样本（如 `order_no`）的结果不变。
- `test_field_policy.py` / `test_field_policy_interceptor.py` 全绿。

### 4.3 M1-4 / M1-5：层级映射声明化（FR-009）

**声明扩展（`hierarchies.yaml#hierarchies[biz_hierarchy].levels[]`）**

每个 level 新增：

```yaml
display_field: name              # 该层自身的名称列
parent_display_field: name       # 父层名称列；缺省=父 level 的 display_field
```

按现有物理列填：`product.name`、`version.name`、`domain.domain_name`、`sub_domain.sub_domain_name`、`service_module.name`、`business_object.name`。

**加载器扩展（`meta/core/hierarchy_loader.py`）**

- `get_table_map()` 保持现有签名；
- 新增 `get_display_field_map() -> Dict[str, str]`；
- 新增 `get_parent_info_map() -> Dict[str, Tuple[str, str, str, str]]`，返回 `(parent_object, parent_table, parent_fk, parent_display_field)`；
- 三层缓存与现有 loader 一致，提供 `reload()`。

**消费者替换（6 处）**

| 文件 | 替换内容 |
|---|---|
| `meta/core/value_help_providers.py` | `_PARENT_INFO_MAP` 改为 `get_parent_info_map()` |
| `meta/services/permission_dimension_engine.py` | `RESOURCE_TABLE_MAP` / `PARENT_FIELD_MAP` / `DISPLAY_FIELD_MAP` / `CODE_FIELD_MAP` / `MANAGEMENT_DIMENSION_CHAIN` 改读 loader |
| `meta/services/dimension_scope_engine.py` | `HIERARCHY_CHAIN` / `EXTENDED_CHAIN_*` / `LEAF_CHAIN_FIELD` 改读 loader |
| `meta/services/management_dimension_engine.py` | 重复的 table / parent 映射改读 loader |
| `meta/services/condition_permission_service.py` | 重复映射改读 loader |
| `meta/services/chain_owner_resolver.py` | 重复映射改读 loader |

**约束**

- `hierarchies.yaml` 的 `dimensions[]` 仍保留，作为「展示维度」清单；`levels[]` 作为「映射 SSOT」。
- 任何一处 loader 缺失时沿用当前常量并打 WARNING，避免启动期硬失败；守卫测试负责在 CI 报出未收敛项。

**等价性判据**

- 6 处消费者对 `product/version/domain/sub_domain/service_module/business_object` 的 `table / parent / display / code` 结果与改造前逐项一致。
- `test_dimension_scope_engine.py`、`test_permission_dimension_api.py`、`test_management_dimension_api.py`、`test_hierarchy_*` 全绿。

### 4.4 M1-6：等价性测试

新增 `meta/tests/test_rule_convergence_m1.py`：

1. **编号**：5 个对象 config 与基线快照一致；三类绑定分支各 1 例；错误码快照。
2. **系统字段**：14 项命中 + 3 项非命中。
3. **层级映射**：6 层 × 4 类映射（table / parent / display / code）快照。
4. **缺失声明**：对象无 `numbering` 时错误码不变；`system_fields` 缺失时回落 14 项。
5. **加载期**：`hierarchies.yaml` 每层必须有 `display_field`，否则失败并指出层名。

### 4.5 M1-7：静态守卫

新增 `scripts/check_rule_convergence.py`：

- 扫描 `meta/services/*.py`、`meta/core/*.py`，命中以下模式即退出码 1：
  - `NUMBERING = {`
  - `SYSTEM_FIELDS = {`
  - `RESOURCE_TABLE_MAP = {` / `PARENT_FIELD_MAP = {` / `DISPLAY_FIELD_MAP = {` / `CODE_FIELD_MAP = {` / `HIERARCHY_CHAIN = [`
- 允许白名单：`hierarchy_loader.py`（缓存实现）、本脚本自身。
- 同时作为 `meta/tests/test_rule_convergence_m1.py` 的一个用例执行，保证 `test.py` 能跑到。

---

## 5. 测试矩阵

| 层 | 命令 | 通过标准 |
|---|---|---|
| 单模块 | `python d:\filework\test.py --file meta/tests/test_document_number_service.py` | 全绿 |
| 单模块 | `python d:\filework\test.py --file meta/tests/test_external_document_number.py` | 全绿 |
| 单模块 | `python d:\filework\test.py --file meta/tests/test_field_policy.py` | 全绿 |
| 单模块 | `python d:\filework\test.py --file meta/tests/test_dimension_scope_engine.py` | 全绿 |
| 新用例 | `python d:\filework\test.py --file meta/tests/test_rule_convergence_m1.py` | 全绿 |
| 回归 | `python d:\filework\test.py --failed` | 无新增失败 |
| 守卫 | `python scripts/check_rule_convergence.py` | exit 0 |

---

## 6. 风险与回滚

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| registry 未加载时取号失败 | 中 | 高 | `_config` 对未加载场景回落到迁移前的只读快照，并打 WARNING；M1 结束删除回落 |
| YAML 漏迁某对象 | 低 | 中 | 等价性测试覆盖 5 个对象；缺失即失败 |
| 6 处映射替换出现列名偏差 | 中 | 高 | 先加 loader，再逐文件替换；每文件单独跑对应测试 |
| 守卫误报 | 低 | 低 | 白名单 + 只匹配精确赋值模式 |
| 报告接口字段变化 | 低 | 低 | `get_numbering_map()` 保持 `no_field/date_field/type_table/fallback_sequence_code` 四字段 |

**回滚**：M1 全部为读取路径改造，回滚 = 还原本方案涉及的提交；无数据迁移、无 DDL、无开关。

---

## 7. 提交策略

1. `feat(meta): support numbering declaration on BO yaml`（M1-1 + M1-2 + 测试）
2. `refactor(meta): declare system fields in shared properties`（M1-3 + 测试）
3. `refactor(meta): drive hierarchy maps from hierarchies.yaml`（M1-4 + M1-5 + 测试）
4. `test(meta): add rule convergence equivalence and static guard`（M1-6 + M1-7）

每个提交单独可回滚；不合并为一个大提交。

---

## 8. 完成定义（DoD）

- [x] 5 个单据 `numbering` 全部来自 YAML，`NUMBERING` 字典删除。
- [x] `SYSTEM_FIELDS` 字典删除，系统字段来自 `shared_properties.yaml`。
- [x] 6 处层级映射消费者不再各自维护常量。
- [x] 等价性测试与静态守卫全部通过。
- [x] `python d:\filework\test.py --failed` 无新增失败（--failed 集合为历史遗留失败，本次改动相关模块全绿）。
- [x] 错误码、HTTP 状态、编号结果零变化。

---

## 9. 执行记录

| 日期 | WBS | 状态 | 备注 |
|---|---|---|---|
| 2026-11-07 | 方案编制 | 完成 | 本文件 |
| 2026-11-07 | M1-1 | 完成 | `MetaObject.numbering` + `yaml_loader.build_meta_object` |
| 2026-11-07 | M1-2 | 完成 | 5 个 BO YAML 增加 `numbering`；`document_number_service` 改为 `_read_numbering()`（registry 优先，YAML 兜底）；`get_numbering_map()` 替换 `bo_api` 的 `NUMBERING` |
| 2026-11-07 | M1-3 | 完成 | `shared_properties.yaml#system_fields` + 新增 `meta/core/system_field_loader.py`；`FieldPolicyEngine._is_system_field` 改读 loader |
| 2026-11-07 | M1-4 | 完成 | `hierarchies.yaml` levels 增加 `display_field / code_field / parent_display_field / scope_anchor`；loader 增加 4 个读取入口 + `reload()` |
| 2026-11-07 | M1-5 | 完成 | 6 处消费者（permission / management / condition / chain_owner / dimension_scope / value_help）改由 loader 驱动 |
| 2026-11-07 | M1-6 | 完成 | 新增 `meta/tests/test_rule_convergence_m1.py`（11 例全绿） |
| 2026-11-07 | M1-7 | 完成 | 新增 `scripts/check_rule_convergence.py`，`exit 0` |
| 2026-11-07 | M1-8 | 完成 | 目标模块：numbering / field_policy / dimension_scope / hierarchy 全绿；YAML 约束仅 1 条与本次无关的历史违规（factor_catalog） |
| 2026-11-07 | 提交 | 待办 | 按 §7 拆分 4 个提交（等待用户授权 git commit） |

### 9.1 执行偏差说明

1. **TBD-4 保持不变**：`scope_anchor: true` 只标在 product / version / domain / sub_domain 四层；
   `get_scope_chain()` 返回 4 层，`service_module` / `business_object` 仍走 `EXTENDED_CHAIN_*` 派生。
2. **展示列取值**：`domain` / `sub_domain` 的 `display_field` 沿用现有 SQL 逻辑列名
   `domain_name` / `sub_domain_name`（非物理列 `name`），以保持 `permission_dimension_api`
   与 `management_dimension_api` 的对外输出零变化。
3. **静态守卫范围**：只针对 M1 涉及的 7 个文件 + 精确字面量模式，避免误伤
   `change_notification_service` 等 M1 范围外的同名常量。
4. **registry 未加载的调用路径**：`_read_numbering()` 直读同名 schema 文件，
   不引入第二份常量副本。
5. **额外收敛 2 处**：`permission_dimension_api.py` / `management_dimension_api.py`
   的 `_PARENT_INFO_MAP` 字面量与 loader 输出逐项相同，一并改为 `get_parent_info_map()`
   （原方案只列了 6 处服务/核心消费者，实际重复共 8 处）。
