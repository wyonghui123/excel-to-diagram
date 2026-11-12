# 逆向平台 D1 任务清单（平台骨架，不接管任何单据）

- 父规格：`docs/specs/spec-reversal-platform-2026-11-06.md` §7 / §8 / §12-D1 / §14
- 状态：**待批准**
- 范围：纯新增 + 一处元数据透传；**不修改** `shipment_service` / `receipt_service` / `inventory_adjustment_service` 行为；
  **不加任何 `doc_effect` 段**（无单据被接管）。
- 验证唯一入口：`python d:\filework\test.py --single <path>`；禁止 pytest。

---

## 已核实的事实（决定实现形态）

| 事实 | 证据 | 对 D1 的约束 |
|---|---|---|
| `MetaObject` 不保留 `doc_effect` | [models.py](../meta/core/models.py#L1014-L1110)、[yaml_loader.py](../meta/core/yaml_loader.py#L2494-L2534) | 必须先加字段并透传，否则 Orchestrator 无法解析声明 |
| `meta/core/reversal_orchestrator.py` 已存在 | 旧边级分派器：`resolve_mode` / `reverse_document` / `reverse_document_edges`，被 [receipt_service.py L1172](../meta/services/receipt_service.py#L1172) 引用 | 新 API **追加**到同模块，旧函数与导入路径零改动 |
| 旧测试锁定旧 API | [test_reversal_orchestrator.py](../meta/tests/test_reversal_orchestrator.py) | 新用例写 `meta/tests/test_reversal_platform.py` |
| `ds.transaction()` 嵌套透传 | [datasource.py L357-L389](../meta/core/datasource.py#L357-L389) | Orchestrator 自持事务，嵌套时不重复 begin/commit，外层统一回滚 |
| 8 个原语均有现成实现 | 见下表 | 原语只转调，不复制业务逻辑（R6） |

### 原语 → 既有实现映射

| primitive | 转调 | 幂等/缺失判定 |
|---|---|---|
| `inventory_reverse_by_event` | `InventoryPostingService(ds).reverse_by_source(event_key, source, transaction_date=now)` | 无分录 → `missing`；建单前查原分录存在 |
| `inventory_reverse_by_txn` | `InventoryPostingService(ds).reverse(txn_ids, source, transaction_date=now)` | `reversal_of_transaction_id` 已存在 → existing |
| `serial_reverse_by_txn` | `SerialNumberService(ds).reverse_serial_event(txn_id)` | 序列号 schema 未建 / 无事件 → `missing` |
| `hu_rewind_by_txn` | `HandlingUnitService(ds).reverse_document(doc_type, doc_id)` | HU schema 未建 / 无事件 → `missing` |
| `reservation_release_by_demand` | `InventoryReservationService(ds).unfulfill_by_demand(bo, id, qty, reason=...)` | 无需求行 → `missing` |
| `edge_compensate_by_source` | `doc_flow_attach.reverse_edges_by_source(ds, rule_id, source_bo, source_id, ref_id=ref, derived_by=...)` | 边表缺失 / 无 active 边 → `missing`（不抛错） |
| `recompute_schedule_delivered` | 与 `shipment_service._refresh_schedule_delivery` 同 SQL 口径的重算函数（本阶段写入原语模块，**不改 shipment 服务**） | 纯重算，恒非 missing |
| `recompute_fulfillment` | `SalesOrderFulfillmentService(ds).recompute_order(order_id)` | 缺 order_id → `missing` |

> `inventory` 面输出 `txn_ids` = **原分录 id**（下游 serial/hu 面依据原事务定位），
> `reversal_txn_ids` = 新生成的 REVERSAL 分录 id；不在 faces 间传递新分录。

---

## 任务

### T-1 元数据透传 `doc_effect`

- 文件：`meta/core/models.py` — `MetaObject` 增加 `doc_effect: Dict[str, Any] = field(default_factory=dict)`。
- 文件：`meta/core/yaml_loader.py` — `parse_meta_object` 构造对象时传 `doc_effect=data.get("doc_effect", {})`。
- 约束：不参与 DDL、不参与 UI 配置、不影响既有对象（默认空字典）。

### T-2 新增 `meta/core/reversal_primitives.py`

公共类型：

```python
@dataclass
class ReversalContext:
    ds: Any
    schema_id: str
    doc_id: Any
    doc: Dict[str, Any]              # 当前单据行
    ref: str                         # 业务权威锚
    now: str
    reason: str
    executed: Dict[str, FaceResult]  # 已完成面的输出
    posting: Dict[str, Any]
    reversal: Dict[str, Any]

@dataclass
class FaceResult:
    data: Dict[str, Any] = field(default_factory=dict)
    missing: bool = False
```

- `PRIMITIVES: Dict[str, Callable[[Any, dict, ReversalContext], FaceResult]]`（8 个，id 与规格 §8.1 一致）。
- `get_primitive(name)`：未注册 → `KeyError`。
- `resolve_args(args, ctx)`：占位符解析
  - 整串单占位符保留原类型（列表不转字符串）：`"{inventory.txn_ids}"` → `list`
  - 其余为字符串插值；命名空间 = 单据行字段 / `posting.*` / `reversal.*` / `<face_id>.*` / `now` / `reason` / `doc_id`
  - 未解析 → `UnresolvedPlaceholder`（供 validator 与 orchestrator 共用）
- `eval_enabled_when(expr, ctx)`：仅支持 `==` / `!=` / `and`，操作数为命名空间变量或字面量；语法非法 → `ValueError`。

### T-3 新增 `meta/core/doc_effect_validator.py`

- `class DocEffectDeclError(Exception)`：`code` / `message` / `path`。
- `validate(doc_effect, *, schema=None, status_values=None) -> None` 实现 V1-V6：
  | 编号 | 校验 | 错误码 |
  |---|---|---|
  | V1 | `reversal.to_state` ∈ status 枚举 | `DECL_INVALID_TO_STATE` |
  | V2 | `reversal.from_states` == 同 `to_state` 的 `state_transition` rule 的 `from_states` | `DECL_STATE_MISMATCH` |
  | V3 | `faces[].primitive` ∈ `PRIMITIVES` | `DECL_UNKNOWN_PRIMITIVE` |
  | V4 | 存在 `edge_compensate_*` 面时 `ref_field` 必填 | `DECL_REF_FIELD_REQUIRED` |
  | V5 | `args` 占位符前缀可解析（schema 字段 / posting / reversal / 前序 face id / now / reason / doc_id） | `DECL_UNRESOLVED_PLACEHOLDER` |
  | V6 | `faces[].id` 唯一 | `DECL_DUPLICATE_FACE` |
- `validate_schema(schema_id)`：从 `meta.core.models.registry` 取 `MetaObject`，读 `doc_effect`；无声明直接返回（不报错）。
- `validate_all()`：遍历 registry，返回 `{schema_id: [code...]}`，供测试期使用；不在启动期阻塞。

### T-4 扩展 `meta/core/reversal_orchestrator.py`（追加，不删旧）

新增公共 API（与旧 `resolve_mode` 等并存，旧函数顶部加「legacy」注释）：

```python
class ReversalError(Exception):
    def __init__(self, code: str, message: str, field: str = '', rule: str = '')

@dataclass
class ReversalOutcome:
    doc_id: Any
    to_state: str
    replay: bool = False
    faces: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    projections: Dict[str, Dict[str, Any]] = field(default_factory=dict)

def execute(ds, *, schema_id, doc_id, reason='', ref=None, user_info=None) -> ReversalOutcome
def supports(schema_id: str) -> bool
```

执行序严格按 §8.3：

1. `resolve`：`schema = registry.get(schema_id)`；`doc_effect` 缺失 → `REVERSAL_NOT_DECLARED`；声明非法 → `REVERSAL_DECL_INVALID`（包装 `DocEffectDeclError`）。
2. `guard`：`SELECT * FROM <table_name> WHERE id=?`；不存在 → `REVERSAL_STATE_INVALID`；
   状态 ∈ `idempotent_states`（默认 `[to_state]`）→ `ReversalOutcome(replay=True)`，**不开事务**；
   状态 ∉ `from_states` → `REVERSAL_STATE_INVALID`；
   `ref_field` 有值且 `ref` 为空 → `REVERSal_REF_MISSING`（实现用规范拼写 `REVERSAL_REF_MISSING`）。
3. `txn`：`with ds.transaction():`。
4. `faces`：按 `order` 排序（`inverted` = 声明序反向，默认；`declared` = 原序）；逐个检查 `enabled_when`，解析 args，调用原语；
   原语异常 → 包装 `REVERSAL_FAILED`（保留 code/message）；`on_missing='strict'` 且 `result.missing` → `REVERSAL_FACT_MISSING`。
5. `project`：faces 全部完成后按声明序执行（不参与倒序，V7）。
6. `state`：`UPDATE <table> SET status=?, <write_audit_fields> WHERE id=? AND status=?`（条件更新，命中 0 行 → `REVERSAL_STATE_INVALID`，触发回滚）。
7. `commit`：退出上下文即提交；事务外不做写。

`supports(schema_id)`：`registry.get(schema_id)` 存在且 `doc_effect.reversal` 非空。

### T-5 新增测试 `meta/tests/test_reversal_platform.py`（T1-T10）

用 fake schema + 记录型原语（不依赖真实业务表），覆盖：

| 用例 | 断言 |
|---|---|
| T1 最小合法声明 | `execute` 返回 `to_state`；faces 全部被调用 |
| T2 倒序 / declared | 调用日志顺序 = 声明序反向 / 原序 |
| T3 幂等 | `replay=True`；原语调用次数 = 0；不进入事务 |
| T4 状态守卫 | `REVERSAL_STATE_INVALID` |
| T5 原语失败回滚 | 第 1 面无残留（用临时表验证），抛 `REVERSAL_FAILED` |
| T6 业务锚 | `REVERSAL_REF_MISSING` |
| T7 `on_missing` | strict → `REVERSAL_FACT_MISSING`；skip → 正常完成 |
| T8 投影 | 投影在 faces 后执行，值等于事实聚合 |
| T9 未声明 | `REVERSAL_NOT_DECLARED` |
| T10 声明校验 | `DECL_STATE_MISMATCH`（validator 直接断言） |

实现方式：测试内用 `monkeypatch` 注入临时 `MetaObject` 到 `meta.core.models.registry`（或临时构造 schema 对象传给内部 `_resolve`），原语通过 `PRIMITIVES` 的副本替换为记录型函数，避免触碰真实业务代码。

### T-6 验证

1. `python d:\filework\test.py --single meta/tests/test_reversal_platform.py`
2. `python d:\filework\test.py --single meta/tests/test_reversal_orchestrator.py`（旧 API 零回归）
3. `python d:\filework\test.py --single meta/tests/test_reversal_profiles.py`
4. 不 commit；结果交用户确认后再进入 D2。

---

## 明确不做（D1 边界）

- 不给任何 schema 加 `doc_effect` 段。
- 不改 `shipment_service.reverse()` / `receipt_service.reverse()` / `inventory_adjustment_service.reverse()`。
- 不删旧 `reversal_profiles` / 旧 Orchestrator 函数（D7 收口时清理）。
- 不新增数据库表、不新增迁移。
- 不改前端。
