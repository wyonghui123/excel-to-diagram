# Spec: V007.41 L0 连接工厂统一 + L0 写迁移到 V3 事务

## 1. Background & Objectives

### 1.1 Background

V007.40 在第 4 次全面检查时发现：17 个文件复制了同一个 `timeout + check_same_thread + PRAGMA busy_timeout` 三件套的 L0 裸连接修复。这暴露了两个深层问题：

1. **架构债**：项目没有 L0 统一工厂。下次 V007.XX 想改 timeout/busy_timeout 默认值，必须再扫一遍代码 + 在 N 处复制。这是 V007.40 的"补丁式"修复遗留的问题。
2. **事务隐患**：V007.40 修复的 17 处中，至少 4 处是写路径（`intent_resolver.grant/deny/revoke`、`subflow_template_store.delete`、`filter_variant_api._execute_query` 的 INSERT/UPDATE/DELETE 分支、`token_blacklist_service._cleanup_expired/add_to_blacklist`）。这些写操作走 L0 直连，**不参与外层事务**。如果业务代码 `with bo_framework.transaction(): ... intent_resolver.grant(...) ...`，intent_resolver 内部已经直连 commit，外层回滚救不回——**silent partial commit**。

### 1.2 Business Objectives

- **统一 L0 入口**：所有 L0 裸连接必须走单一工厂，杜绝"在三件套的复制粘贴"
- **写迁移到 V3**：所有 L0 写路径必须在外层 `bo_framework.transaction()` 内，或迁移到 L2+ 的事务 API
- **可观测**：safe_connect 调用必须分类（read / write / pool-bypass）记 metric
- **可降级**：探测失败时不影响业务，warn + metric 即可
- **零破坏性**：V007.40 已通过的验证必须在 V007.41 仍然 100% 通过

### 1.3 User / Stakeholder Objectives

| 角色 | 收益 |
|---|---|
| **后端开发者** | 调 `safe_connect_for_read/write` 即可，不用关心 timeout / busy_timeout / 多线程兼容 |
| **运维 / SRE** | L0 写不再悄悄 commit，事务原子性可观察；disk I/O error 复发时可快速定位 |
| **AI Agent** | 多步 workflow（UnitOfWork + DeepInsert）的写操作保证原子性，回滚可追溯 |
| **SAP/集成专家** | 事务模型对齐 SAP LUW（Logical Unit of Work）：写 = LUW 内执行 |

### 1.4 与 V007.40 的关系

```
V007.34 (read retry)               ─┐
V007.38 (journal_mode idempotent)   ├─ 战术止血
V007.39 (TRUNCATE elimination)      ─┤
V007.40 (4th check, default fix)   ─┘
                                    │
                                    ▼
V007.41 (本 spec)                  ── 战略统一
```

V007.40 不回滚、不重做；V007.41 在 V007.40 基础上做架构重构。

### 1.5 与事务系统的关系

引用 `.trae/specs/transaction-system/spec.md` 已定义的层次：

```
V1 直调 ds.execute()                          ─ 本次: 保留（读）
V2 with ds.transaction()                       ─ 本次: 不动（L2 DataSource）
V3 with bo_framework.transaction()             ─ 本次: 写迁移目标
V4 UnitOfWork                                   ─ 不动
V5 DeepInsert/DeepMutation                      ─ 不动
```

本次**只动 L0**（V007.40 之前的修复点），V2/V3/V4/V5 不重构。

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 数据一致性（atomic write）是企业应用基础；silent partial commit 风险 |
| User/Stakeholder | Yes | 后端 / SRE / AI Agent 三类用户受益 |
| Solution | Yes | 重构 L0 抽象 + 写迁移策略 |
| Functional | Yes | safe_connect API、tx_state 守卫、metric、迁移工具 |
| Nonfunctional | Yes | 性能（<5% 开销）、可观测、可降级、零破坏性 |
| External Interface | No | 不暴露新 HTTP 接口 |
| Transition | Yes | V007.40 → V007.41 兼容迁移，旧 L0 仍可工作（带 warning） |

## 3. Functional Requirements

### FR-001: safe_connect 统一 L0 工厂

- **Description**: 提供 `meta/core/safe_connect.py` 模块，封装所有 L0 裸连接创建逻辑
- **Acceptance Criteria**:
  - 模块导出 3 个公共 API：
    - `safe_connect_for_read(db_path: str) -> ContextManager[sqlite3.Connection]`：只读直连，可独立调用
    - `safe_connect_for_write(db_path: str) -> ContextManager[sqlite3.Connection]`：写直连，**必须**在外层 `bo_framework.transaction()` 内
    - `safe_connect(db_path: str, *, mode: str = "auto") -> sqlite3.Connection`：兼容旧调用（自动判断 read/write）
  - 所有连接默认参数：`timeout=30.0`、`check_same_thread=False`、`PRAGMA busy_timeout=30000`、`row_factory=sqlite3.Row`
  - 不参与 pool（L1），与 `sql_connection_pool` 完全解耦
- **Priority**: Must
- **Type Mapping**: Solution/Functional
- **Source**: V007.40 重复修复分析 + 调研 `.trae/rules/core/checklist.md`

### FR-002: 写路径强制 V3 事务

- **Description**: `safe_connect_for_write()` 检测到当前无外层事务时，raise `ConnectionRefusedError`
- **Acceptance Criteria**:
  - 用 `meta/core/sqlite_tx_state.py:get_tx_state()` 探测 SQLite 真实事务状态
  - 状态为 `NONE` 时 raise `ConnectionRefusedError("L0 write must be inside bo_framework.transaction()")`
  - 状态为 `WRITE/READ` 时正常返回连接
  - 状态为 `UNKNOWN` 时降级：log warning + 放行 + metric +1
  - 提供 `BO_FRAMEWORK_TX_FORCE=True` 环境变量可临时关闭强制（紧急逃生口，metric 标记）
- **Priority**: Must
- **Type Mapping**: Solution/Functional/Nonfunctional
- **Source**: silent partial commit 风险分析

### FR-003: 4 处 L0 写迁移到 V3

- **Description**: V007.40 修复的 4 处 L0 写路径必须迁移到外层 `bo_framework.transaction()` 包裹
- **Acceptance Criteria**:
  - `intent_resolver.grant/deny/revoke` → 调用方（API 层）必须用 `with bo_framework.transaction() as txn:` 包裹
  - `subflow_template_store.delete/save` → 同上
  - `filter_variant_api._execute_query` (INSERT/UPDATE/DELETE) → 重构为 `safe_connect_for_write` + 调用方 `bo_framework.transaction()`
  - `token_blacklist_service._cleanup_expired/add_to_blacklist` → 评估保留 L0（每次请求触发 cleanup 频率高）+ 调用方事务，或迁移
  - 迁移后 `verify_v007_41.py` 自动检测这 4 处调用方是否在外层事务中
  - 保留"非事务上下文也能调"的能力（admin 单写场景），但通过 `safe_connect(db_path, mode="write_force_no_tx=True")` 显式声明
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: V007.40 留下的 4 处写路径

### FR-004: V007.40 17 处迁移到新工厂

- **Description**: V007.40 在 17 处复制粘贴的三件套，全部改为 `from meta.core.safe_connect import safe_connect_for_read`
- **Acceptance Criteria**:
  - 删除 `intent_resolver._safe_connect` / `subflow_template_store._safe_connect` 本地 helper
  - 删除 `token_blacklist_service._get_connection` / `filter_variant_api._execute_query` 中的 `sqlite3.connect(...)` 调用
  - 删除 `runtime_dimension_resolver` / `dim_scope_overlap_detector` / `audit_export` / `sql_adapters.fresh_connection` / `app_builder` 中的 `sqlite3.connect(...)` 调用
  - 全部改为 `from meta.core.safe_connect import safe_connect_for_read` + context manager
  - V007.40 在这些文件中加的 `timeout=30.0` / `check_same_thread=False` / `PRAGMA busy_timeout = 30000` 三件套代码**整段删除**（工厂已封装）
- **Priority**: Must
- **Type Mapping**: Solution
- **Source**: V007.40 commit 7c71636 修复清单

### FR-005: 唯一性检查

- **Description**: 全项目代码（生产代码 + 测试代码，但排除 migrations / scripts / dev / 测试 conftest）不允许出现 `sqlite3.connect(` 直接调用
- **Acceptance Criteria**:
  - `verify_v007_41.py` 扫描 `meta/{core,services,api,handlers}/`，匹配 `sqlite3\.connect\(` 应该为 0 处
  - 例外白名单：`migrations/`、`scripts/`、`dev/`、`tests/conftest.py`、`tests/shared/base.py`、`scripts/check_file_encoding.py`
  - 例外白名单需在 `verify_v007_41.py` 中显式列出，附理由注释
- **Priority**: Must
- **Type Mapping**: Nonfunctional
- **Source**: 架构债根治目标

### FR-006: metric 集成

- **Description**: safe_connect 调用必须记入 `meta/core/observability.py` 的 OBS_COUNTERS
- **Acceptance Criteria**:
  - 新增 4 个 metric：
    - `v007_41_safe_connect_read_total`：只读调用计数
    - `v007_41_safe_connect_write_total`：写调用计数
    - `v007_41_safe_connect_write_no_tx_total`：写调用但无外层事务计数（应=0，告警源）
    - `v007_41_safe_connect_tx_state_unknown_total`：探测失败计数（应≈0）
  - metric 通过 `OBS_COUNTERS` 字典暴露（与 V007.24 pool_init_count 一致风格）
- **Priority**: Should
- **Type Mapping**: Nonfunctional
- **Source**: 可观测性需求

### FR-007: 配置化默认值

- **Description**: safe_connect 的 timeout / busy_timeout 默认值从配置读取，便于未来调整
- **Acceptance Criteria**:
  - 在 `meta/core/sql_config.py` 新增 `SafeConnectConfig` dataclass：
    ```python
    @dataclass
    class SafeConnectConfig:
        timeout: float = 30.0
        busy_timeout_ms: int = 30000
        check_same_thread: bool = False
        enforce_write_in_tx: bool = True  # False = 关闭 FR-002 强制
        tx_state_unknown_passthrough: bool = True  # True = 降级放行
    ```
  - `safe_connect_for_read/write` 默认从 `get_safe_connect_config()` 读取
  - 现有 `sql_connection_pool.py` 的 `db_timeout=30.0` 不变（共用同一默认值）
- **Priority**: Should
- **Type Mapping**: Solution
- **Source**: 配置化原则（与 V007.40 CheckpointConfig 一致风格）

### FR-008: 降级逃生口

- **Description**: 紧急场景下可绕过强制规则，metric 标记
- **Acceptance Criteria**:
  - 提供 `safe_connect(db_path, mode="write_force_no_tx")` 兼容模式
  - 该模式绕过 `enforce_write_in_tx` 检查，但 metric `v007_41_safe_connect_write_no_tx_total` +1
  - 文档明确：仅 admin / 一次性脚本可用，业务热路径禁用
- **Priority**: Should
- **Type Mapping**: Solution/Functional
- **Source**: 紧急情况兼容性

## 4. Non-Functional Requirements

### NFR-001: 性能开销 <5%

- 每次 safe_connect 比直接 `sqlite3.connect()` 慢应 <1ms（仅多 1 次函数调用 + 1 次 tx_state 探测 + 1 次 metric 写）
- 启用 `enforce_write_in_tx` 时，写路径探测 <2ms
- `verify_v007_41.py` 包含 benchmark：连续 1000 次 safe_connect_for_read，总耗时 < 1000ms

### NFR-002: 零破坏性

- V007.40 已通过的 14 项验证在 V007.41 必须仍然 100% 通过
- 已部署服务（release-prep）升级 V007.41 后不需要重启 DB / 重写数据
- 不引入新的依赖包

### NFR-003: 可降级

- tx_state 探测失败时不影响业务（warn + metric +1）
- 缺 metric 模块时降级为 log 计数
- 模块导入失败时（Python 3.9 vs 3.12 in_transaction 差异）走 legacy 探测路径

### NFR-004: 可观测

- 所有 safe_connect 调用记 metric
- 探测守卫触发时记 log（WARNING 级别，含 caller 文件:行号）
- 提供 `meta/core/diagnostics/safe_connect_stats.py` 工具读 metric 快照

## 5. Module Design

### 5.1 新增模块

| 文件 | 职责 | 行数预估 |
|---|---|---|
| `meta/core/safe_connect.py` | 统一 L0 工厂 + tx_state 守卫 | ~150 |
| `meta/tests/test_v007_41_safe_connect.py` | 单元测试 | ~250 |
| `verify_v007_41.py` | 集成验证（与 verify_v007_40 互补） | ~200 |
| `docs/SPEC_V007.41.md` | 本 spec 镜像（便于历史归档） | 复制 |

### 5.2 修改模块

| 文件 | 修改内容 |
|---|---|
| `meta/core/intent_resolver.py` | 删 `_safe_connect`，改 `from meta.core.safe_connect import safe_connect_for_read` |
| `meta/services/subflow_template_store.py` | 删 `_safe_connect`，改 `safe_connect_for_read` |
| `meta/services/token_blacklist_service.py` | 删 `_get_connection`，改 `safe_connect_for_read`，评估 write 路径事务化 |
| `meta/api/filter_variant_api.py` | 删 `_execute_query` 中的 `sqlite3.connect(...)`，按 read/write 拆分 |
| `meta/core/runtime_dimension_resolver.py` | 3 处 `sqlite3.connect(...)` → `safe_connect_for_read` |
| `meta/core/dim_scope_overlap_detector.py` | 2 处 → `safe_connect_for_read` |
| `meta/services/audit_export.py` | `with sqlite3.connect(...)` → `with safe_connect_for_read(...)` |
| `meta/core/sql_adapters.py` | `fresh_connection()` → `safe_connect_for_read` |
| `meta/core/app_builder.py` | 2 处 `sqlite3.connect(...)` → `safe_connect_for_read` |
| `meta/core/sql_config.py` | 新增 `SafeConnectConfig` |
| `meta/core/observability.py` | 新增 4 个 metric |
| `meta/handlers/*.py` 等业务调用方 | intent_resolver.grant/deny/revoke 调用方包 `bo_framework.transaction()` |

### 5.3 safe_connect.py 核心代码骨架

```python
# meta/core/safe_connect.py
"""V007.41 safe_connect - 统一 L0 裸连接工厂

[V007.41 BUG-FIX] 背景:
  - V007.40 在 17 个文件复制 timeout + check_same_thread + busy_timeout 三件套
  - V007.41 集中到本模块, 强制全项目唯一入口
  - 写连接强制走 bo_framework.transaction(), 根治 silent partial commit

用法:
    # 只读 (V1)
    from meta.core.safe_connect import safe_connect_for_read
    with safe_connect_for_read(db_path) as conn:
        cursor = conn.execute("SELECT ...")

    # 写 (V3, 必须在外层事务内)
    from meta.core.safe_connect import safe_connect_for_write
    with bo_framework.transaction() as txn:
        with safe_connect_for_write(db_path) as conn:
            cursor = conn.execute("INSERT ...")
            # 自动 commit 由外层 txn 负责, 不要 conn.commit()!
"""
from __future__ import annotations
import sqlite3
import logging
import os
from contextlib import contextmanager
from typing import Optional

from meta.core.sqlite_tx_state import get_tx_state, TxState
from meta.core.sql_config import get_safe_connect_config
from meta.core.observability import OBS_COUNTERS

logger = logging.getLogger(__name__)


def _bump_counter(name: str) -> None:
    """递增 OBS_COUNTERS 中对应 metric, 失败降级 log"""
    try:
        counter = OBS_COUNTERS.get(name)
        if counter and hasattr(counter, 'inc'):
            counter.inc()
    except Exception as e:
        logger.debug(f"safe_connect metric bump failed (degraded): {e}")


@contextmanager
def safe_connect_for_read(db_path: str):
    """[V007.41] L0 只读裸连接工厂

    等价于:
        conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.row_factory = sqlite3.Row
    """
    _bump_counter('v007_41_safe_connect_read_total')
    cfg = get_safe_connect_config()
    conn = sqlite3.connect(
        db_path,
        timeout=cfg.timeout,
        check_same_thread=cfg.check_same_thread,
    )
    conn.execute(f"PRAGMA busy_timeout = {cfg.busy_timeout_ms}")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


@contextmanager
def safe_connect_for_write(db_path: str, *, force_no_tx: bool = False):
    """[V007.41] L0 写裸连接工厂, 强制 V3 事务上下文

    背景: L0 写不参与外层事务 = silent partial commit 风险.
    修法: 用 sqlite_tx_state 探测外层事务状态, NONE 时 raise.

    Args:
        db_path: 数据库路径
        force_no_tx: True = 绕过检查 (admin/一次性脚本专用, metric 标记)

    Raises:
        ConnectionRefusedError: 无外层事务且 force_no_tx=False
    """
    _bump_counter('v007_41_safe_connect_write_total')
    cfg = get_safe_connect_config()

    # 探测外层事务
    if cfg.enforce_write_in_tx and not force_no_tx:
        # 用一个临时只读连接探测 (不创建新事务, 不影响业务)
        with safe_connect_for_read(db_path) as probe_conn:
            state = get_tx_state(probe_conn)
        if state == TxState.NONE:
            _bump_counter('v007_41_safe_connect_write_no_tx_total')
            raise ConnectionRefusedError(
                f"[V007.41] safe_connect_for_write requires outer transaction. "
                f"Use 'with bo_framework.transaction() as txn:' or call from within "
                f"ds.transaction()/UnitOfWork. If this is an admin one-shot, pass "
                f"force_no_tx=True."
            )
        elif state == TxState.UNKNOWN:
            _bump_counter('v007_41_safe_connect_tx_state_unknown_total')
            logger.warning("[V007.41] tx_state probe UNKNOWN, write proceeding (degraded)")

    if force_no_tx:
        _bump_counter('v007_41_safe_connect_write_no_tx_total')
        logger.warning("[V007.41] force_no_tx=True, write bypassing tx enforcement")

    conn = sqlite3.connect(
        db_path,
        timeout=cfg.timeout,
        check_same_thread=cfg.check_same_thread,
    )
    conn.execute(f"PRAGMA busy_timeout = {cfg.busy_timeout_ms}")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


@contextmanager
def safe_connect(db_path: str, *, mode: str = "auto"):
    """[V007.41] 兼容旧调用, 自动判断 read/write

    Args:
        mode: "auto" | "read" | "write" | "write_force_no_tx"

    Note: "auto" 通过 PRAGMA journal_mode 判断 (WAL = read mostly), 不推荐.
    """
    if mode == "read":
        with safe_connect_for_read(db_path) as conn:
            yield conn
    elif mode == "write":
        with safe_connect_for_write(db_path) as conn:
            yield conn
    elif mode == "write_force_no_tx":
        with safe_connect_for_write(db_path, force_no_tx=True) as conn:
            yield conn
    else:  # auto
        # 简单启发式: 连接到 :memory: 时认为是 read, 否则默认 read (保守)
        # 业务调用应明确指定 mode
        logger.debug("[V007.41] safe_connect mode=auto, defaulting to read")
        with safe_connect_for_read(db_path) as conn:
            yield conn
```

## 6. Migration Plan

### Phase 1: 工厂实现（1 个 commit）

| Task | Owner | 验收 |
|---|---|---|
| 1.1 新增 `meta/core/safe_connect.py`（FR-001） | dev-agent | 单元测试通过 |
| 1.2 新增 `SafeConnectConfig` 到 `sql_config.py`（FR-007） | dev-agent | 默认值与 V007.40 一致 |
| 1.3 新增 4 个 metric 到 `observability.py`（FR-006） | dev-agent | 不破坏现有 metric |
| 1.4 新增 `meta/tests/test_v007_41_safe_connect.py` | dev-agent | 100% 覆盖 read/write/降级/逃生口 |

### Phase 2: 现有 17 处迁移（1 个 commit）

| Task | Owner | 验收 |
|---|---|---|
| 2.1 迁移 4 个本地 helper 持有者（intent_resolver / subflow_template_store / token_blacklist / filter_variant_api） | dev-agent | `verify_v007_41.py` 通过 |
| 2.2 迁移 13 个内联 sqlite3.connect（runtime_dimension_resolver / dim_scope_overlap_detector / audit_export / sql_adapters.fresh_connection / app_builder） | dev-agent | 同上 |
| 2.3 V007.40 加的 `timeout=30.0` / `PRAGMA busy_timeout = 30000` / `check_same_thread=False` 整段删除 | dev-agent | git diff 确认删除 |

### Phase 3: 写迁移到 V3（1 个 commit，谨慎）

| Task | Owner | 验收 |
|---|---|---|
| 3.1 列出 `intent_resolver.grant/deny/revoke` 所有调用方 | dev-agent | grep 结果 |
| 3.2 调用方加 `with bo_framework.transaction() as txn:` 包裹 | dev-agent | 调用方测试 |
| 3.3 `intent_resolver` 内部 `sqlite3.connect(...)` → `safe_connect_for_write` | dev-agent | 测试 |
| 3.4 同上对 `subflow_template_store.delete/save` | dev-agent | 测试 |
| 3.5 `filter_variant_api` 拆分 `_execute_query` 为 read / write 两个版本 | dev-agent | 测试 |
| 3.6 `token_blacklist_service._cleanup_expired` 评估：每次请求触发 cleanup + 独立事务 | dev-agent | 决策：保留 L0 + force_no_tx 或迁移 |
| 3.7 新增 `test_v007_41_l0_write_in_tx.py`，覆盖 4 处写迁移后外层回滚确实回滚 | dev-agent | 测试 |

### Phase 4: 唯一性检查 + 文档（1 个 commit）

| Task | Owner | 验收 |
|---|---|---|
| 4.1 新增 `verify_v007_41.py`，14 项验证 | dev-agent | 100% pass |
| 4.2 复制本 spec 到 `docs/SPEC_V007.41.md`（历史归档） | dev-agent | 文件存在 |
| 4.3 更新 `.trae/rules/core/checklist.md` 加 V007.41 检查项 | dev-agent | 规则同步 |

## 7. Risk Assessment

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Phase 3 写迁移破坏现有业务 | 中 | 高 | 单元测试 + 集成测试 + 灰度部署；保留 force_no_tx 逃生口 |
| safe_connect 引入性能瓶颈 | 低 | 中 | NFR-001 benchmark；contextmanager 开销可忽略 |
| tx_state 探测失败导致误判 | 低 | 中 | NFR-003 降级放行 + metric |
| Python 3.9 vs 3.12 in_transaction 行为差异 | 低 | 中 | sqlite_tx_state.py 已处理 fallback (try BEGIN IMMEDIATE) |
| V007.40 修复的 14 项验证在 V007.41 失败 | 低 | 高 | NFR-002 强制零破坏；Phase 4 必跑 verify_v007_40.py |

## 8. Acceptance Criteria

- [ ] FR-001~008 全部实现
- [ ] NFR-001~004 全部满足
- [ ] verify_v007_40.py 14/14 仍通过
- [ ] verify_v007_41.py 新增 ≥14 项 100% 通过
- [ ] test_v007_41_safe_connect.py 单元测试 100% 覆盖
- [ ] test_v007_41_l0_write_in_tx.py 验证 4 处写迁移后 silent partial commit 消失
- [ ] docs/SPEC_V007.41.md 镜像同步
- [ ] 单测 + 集成测试 + 部署后监控 1 周 disk I/O error 0 复发

## 9. Out of Scope

- L1 (WriteQueue + checkpoint) 重构 → V007.42+ 候选
- L2 (SQLDataSource) 抽象改造 → 不动
- PostgreSQL 迁移 → docs/SPEC_PG_MIGRATION.md 独立 spec
- 监控 / 告警系统建设 → 运维 agent 负责
- 业务层事务（V4 UnitOfWork / V5 DeepInsert）改造 → 不动

## 10. References

- V007.40 commit 7c71636 (本 spec 起点)
- `.trae/specs/transaction-system/spec.md` (事务层次定义)
- `meta/core/sqlite_tx_state.py` (tx_state 探测基础)
- `meta/core/sql_config.py` (配置化模式参考)
- `meta/core/observability.py` (metric 风格参考)
- `meta/core/sql_connection_pool.py` (V007.40 修复点, 不动)
- `meta/core/sql_write_queue.py` (V007.40 修复点, 不动)