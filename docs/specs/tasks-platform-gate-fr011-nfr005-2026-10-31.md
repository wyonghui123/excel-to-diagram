# Tasks: 平台边界门禁（FR-011）+ 回滚开关（NFR-005）

- 日期：2026-10-31
- 父 Spec：[spec-platform-common-layer-downsink-2026-10-31-v1.0.md](./spec-platform-common-layer-downsink-2026-10-31-v1.0.md)（FR-001~FR-010 已完成；本文件补齐 FR-011、NFR-005）
- 状态：已完成（2026-10-31，验证通过）
- 范围：仅 `meta/` 后端 + `apps/tms/app.yaml`；不改前端，不改成功响应结构

## 1. 决策（实施前必须落定）

### D1 FR-011 门禁方式：加载期静态扫描（AST）

- 不引入 import hook / sys.meta_path 补丁（会污染平台自身进程与测试）。
- 在 `register_apps()`（真正的启动加载点）对每个应用的 `app_dir` 下全部 `*.py` 做 AST 解析，收集 `import` / `from ... import ...`。
- 只拦「平台模块」：`meta` 或以 `meta.` 开头；相对 import（`from . import x`）跳过。
- 白名单匹配：精确匹配或前缀匹配（`meta.core.bo_framework` 允许 `meta.core.bo_framework.xxx`）。
- 同一 import 语句的多个候选名（如 `from meta.core import datasource` → `meta.core` 与 `meta.core.datasource`）只要**任一**命中白名单即通过。
- 违规抛 `AppManifestError`（信息含 app 名、相对文件名、模块名、已声明白名单），在 `register_apps` 内转成 `AppRegistrationError("平台模块 import 门禁失败: ...")` → 启动中止。
- 已知边界：静态扫描不覆盖 `importlib` / `__import__` 动态加载；在 docstring 中写明，不做运行时 hook。

### D2 tms 白名单补齐（保持「现有 3 个应用不受影响」）

实测 `apps/tms/blueprints/handlers/on_outbound_completed.py` 导入 `meta.core.action_executor`、`meta.core.models`，但 `app.yaml` 未声明 → 门禁开启后会误杀真实应用。
处理：`apps/tms/app.yaml` 的 `allowed_platform_modules` 增加这两项（只是把真实依赖写实，不改行为）。
另两个应用：`hello_world` 无 meta import；`warehouse` 仅 `meta.core.datasource`（已声明）。

### D3 三个开关的语义与默认值（`meta/core/platform_flags.py` 新建）

取值（大小写不敏感）：`strict`(1/true/on/strict/enforce) / `shadow`(shadow/log/warn/observe) / `off`(0/false/no/off/disabled/none)；未设置用默认；非法值记 warning 后回默认。

| 开关 | 默认 | 理由 |
|---|---|---|
| `PLATFORM_STRICT_CONTRACT` | `shadow` | 仍有 46 处 `json_response` 逃生口，先观察 |
| `PLATFORM_TX_GUARD` | `shadow` | 事务基线已达标，先观察；strict 未验证全量动作 |
| `PLATFORM_PERMISSION_GATE` | `strict` | 鉴权已是现行行为，默认 shadow 会 fail-open → 违反 NFR-001；开关用于回滚 |

每个开关独立读取 `os.environ`（调用时读取，便于测试与运行时切换）。

### D4 三个开关的接入点

1. `PLATFORM_STRICT_CONTRACT` → [meta/api/_response_contract.py](file:///d:/filework/excel-to-diagram/meta/api/_response_contract.py)
   - `json_response()`（唯一非标准 payload 出口）：`strict` 抛 `ResponseContractViolation`；`shadow` 记 debug；`off` 放行。
   - `ok()`：`strict` 下 data 为 list/tuple 抛 `ResponseContractViolation`（列表应走 `ok_list`）。
   - 默认 shadow ⇒ 现有行为零变化。
2. `PLATFORM_TX_GUARD` → [meta/core/bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py)
   - 新增 `TransactionBoundaryError` + `_check_write_tx_scope(object_type, action, data_source)`。
   - 调用点：`execute()` 算出 `_should_wrap` 后，若 `action in _AUTO_TXN_ACTIONS` 且未包裹（典型场景 = `DISABLE_AUTO_TRANSACTION=1` 或数据源无 `in_transaction`），执行守卫；`in_transaction=True`（调用方已开事务）不拦。
   - `strict` 抛错、`shadow` 记 warning、`off` 不动作。
3. `PLATFORM_PERMISSION_GATE` → [meta/core/permission_gate.py](file:///d:/filework/excel-to-diagram/meta/core/permission_gate.py)
   - 新增 `_apply_gate_mode(allowed, required, source)`；接入 `evaluate_code()` 与 `evaluate()`。
   - `strict`（默认）保持现行为；`shadow` / `off` 在「本应拒绝」时放行并记 warning（回滚用，显式开启才生效）。

## 2. 变更清单（逐文件）

| # | 文件 | 变更 |
|---|---|---|
| [x] T1 | `meta/core/platform_flags.py`（新建） | `STRICT/SHADOW/OFF`、`parse_mode`、`contract_mode()`、`tx_guard_mode()`、`permission_gate_mode()`、三个 env 常量 |
| [x] T2 | `meta/core/app_loader.py` | 新增 `_iter_platform_imports(py_file)`（AST，按 import 语句返回候选全名 + 行号）、`is_platform_module_allowed(module, whitelist)`、`validate_platform_imports(manifest)` |
| [x] T3 | `meta/core/app_registry.py` | import `AppManifestError`；新增 `_verify_platform_imports(manifests)`；在 `_verify_dependencies()` 之后调用 |
| [x] T4 | `apps/tms/app.yaml` | 白名单 + `meta.core.action_executor`、`meta.core.models` |
| [x] T5 | `meta/api/_response_contract.py` | `ResponseContractViolation` + `_contract_guard(...)`；接入 `json_response()`、`ok()` |
| [x] T6 | `meta/core/bo_framework.py` | `TransactionBoundaryError` + `_check_write_tx_scope(...)` + `execute()` 调用 |
| [x] T7 | `meta/core/permission_gate.py` | `_apply_gate_mode(...)` + 接入 `evaluate_code()` / `evaluate()` |
| [x] T8 | `meta/tests/test_platform_boundary.py`（新建） | FR-011 + NFR-005 单测（见 §3） |
| [x] T9 | 父 Spec | 回写 FR-011「落地状态（2026-10-31）」与 NFR-005 实现说明（含 D3 默认值偏离 spec 原文「默认先 shadow」的理由） |

## 3. 测试（T8，全部经 test.py）

`meta/tests/test_platform_boundary.py`：

- `TestImportGate`
  - 白名单精确匹配通过；前缀子模块通过；`from meta.core import datasource` 在只声明子模块时通过
  - 未声明时 `import meta.core.bo_framework` 抛 `AppManifestError`，断言信息含 app 名 + 模块名
  - 真实 `apps/` 全部应用 `validate_platform_imports` 通过（验收「3 个声明应用不受影响」）
  - `register_apps(..., apps_root=<tmp>)` 对违规应用抛 `AppRegistrationError`（启动中止）
- `TestPlatformFlags`：三开关默认值；strict/shadow/off 解析；非法值回默认；独立（设置一个不影响另两个）
- `TestContractGuard`：默认 shadow 放行；`strict` 下 `json_response` / `ok(list)` 抛 `ResponseContractViolation`；`off` 放行
- `TestTxGuard`：默认 shadow 不抛；`strict` + 未开事务抛 `TransactionBoundaryError`；`in_transaction=True` 不拦；`off` 不拦
- `TestPermissionGate`：默认 strict 拒绝无权限；shadow 放行并 `decision.allowed=True`；off 放行；有权限时与模式无关恒 True

## 4. 验证步骤（按序）

1. `python d:\filework\test.py --file meta/tests/test_platform_boundary.py`
2. `python d:\filework\test.py --file meta/tests/test_app_loader.py,meta/tests/test_app_registry.py,meta/tests/test_app_dependency.py,meta/tests/test_doc_flow.py,meta/tests/test_app_table_name_collision_probe.py`（应用加载/注册回归）
3. `python d:\filework\test.py --file meta/tests/test_auth_permission.py,meta/tests/test_require_permission_decorator.py,meta/tests/test_v2_api_permissions.py`（权限 gate 回归）
4. `python scripts/check_architecture.py`（11 项计数不得上涨）
5. 回写父 Spec（T9）

## 5. 不做 / 不在本批

- 不引入运行时 import hook；不实现 `requires.column_version` 执行语义；不启用 `table_prefix` 物理改写（父 Spec 已排除）。
- 不把三个开关写进 `.env` / 前端配置面板（只用环境变量）。
- 不 git commit（等用户明确指令）。
