# V007.41 实施计划

## 1. 总体策略

**目标**：从 V007.40 的"补丁式"修复升级到"工厂统一"架构

**原则**：
1. **零破坏性**：V007.40 已通过的 14 项验证必须仍然 100% 通过
2. **渐进式**：4 个 Phase，每个 Phase 单独 commit + 单独可回滚
3. **测试驱动**：每 Phase 都有对应的单元测试或验证脚本
4. **可降级**：force_no_tx 逃生口 + metric 监控 + 灰度部署

## 2. 4 个 Phase 时间表

```
Day 1: Phase 1 (工厂实现) + Phase 2 (17 处迁移)
Day 2: Phase 3 (写迁移到 V3)
Day 3: Phase 4 (验证 + 文档) + 部署
```

## 3. Phase 1: 工厂实现（Day 1 上午）

### 3.1 目标

- `meta/core/safe_connect.py` 模块可用
- `SafeConnectConfig` 配置生效
- 4 个 metric 注册
- 单元测试 100% 通过

### 3.2 提交清单

**Commit 1**: `fix(be): V007.41 T1-T4 - safe_connect factory + config + metric + unit tests`

包含：
- `meta/core/safe_connect.py` (新建)
- `meta/core/sql_config.py` (修改)
- `meta/core/observability.py` (修改)
- `meta/tests/test_v007_41_safe_connect.py` (新建)
- `meta/tests/test_sql_config.py` (修改)

### 3.3 验收

- [ ] `from meta.core.safe_connect import safe_connect_for_read, safe_connect_for_write, safe_connect` 可用
- [ ] `pytest meta/tests/test_v007_41_safe_connect.py` 100% 通过
- [ ] `pytest meta/tests/test_sql_config.py` 100% 通过
- [ ] V007.40 14 项验证仍 100% 通过

## 4. Phase 2: 17 处迁移（Day 1 下午）

### 4.1 目标

- V007.40 修复的 17 处全部改用 `safe_connect_for_read`
- V007.40 加的"三件套"代码整段删除
- `verify_v007_41.py` Test 1（唯一性检查）= 0 处

### 4.2 提交清单

**Commit 2**: `fix(be): V007.41 T5-T7 - migrate 17 L0 sites to safe_connect`

包含：
- `meta/core/intent_resolver.py` (修改)
- `meta/services/subflow_template_store.py` (修改)
- `meta/services/token_blacklist_service.py` (修改)
- `meta/api/filter_variant_api.py` (修改)
- `meta/core/runtime_dimension_resolver.py` (修改)
- `meta/core/dim_scope_overlap_detector.py` (修改)
- `meta/services/audit_export.py` (修改)
- `meta/core/sql_adapters.py` (修改)
- `meta/core/app_builder.py` (修改)

### 4.3 关键风险

**intent_resolver 7 处**：删除 `_safe_connect` 后，6 个业务方法 + 1 个 helper 都要改 import。逐一验证：

```python
# 修改前
conn = _safe_connect(self._db_path)

# 修改后
from meta.core.safe_connect import safe_connect_for_read
with safe_connect_for_read(self._db_path) as conn:
    cursor = conn.cursor()
    # ...
```

**filter_variant_api**：`_execute_query` 是被多个路由调用，拆分为 read/write 时不能影响 list 路由（只读）。

### 4.4 验收

- [ ] `grep -rn "sqlite3\.connect(" meta/{core,services,api,handlers}/` = 0 处
- [ ] `grep -rn "_safe_connect" meta/` = 0 处（除 safe_connect.py 内部）
- [ ] V007.40 14 项验证仍 100% 通过
- [ ] Phase 1 单元测试仍 100% 通过

## 5. Phase 3: 写迁移到 V3（Day 2）

### 5.1 目标

- 4 处 L0 写路径迁移到 `bo_framework.transaction()`
- `safe_connect_for_write` 在无事务时 raise
- silent partial commit 测试通过

### 5.2 提交清单

**Commit 3**: `fix(be): V007.41 T8-T9 - migrate L0 writes to bo_framework.transaction()`

包含：
- `meta/core/intent_resolver.py` (写路径改用 safe_connect_for_write)
- `meta/services/subflow_template_store.py` (同上)
- `meta/api/filter_variant_api.py` (POST/PUT/DELETE 路由加事务)
- `meta/services/token_blacklist_service.py` (决策后)
- 调用方 `meta/handlers/*.py` / `meta/api/*.py` (加 bo_framework.transaction)
- `meta/tests/test_v007_41_l0_write_in_tx.py` (新建)

### 5.3 关键决策点

**3.6 token_blacklist_service._cleanup_expired**：

```python
# 决策 A: 保留 L0 + force_no_tx=True
# 理由: cleanup 每次请求都触发, 加事务层会显著增加 latency
#       cleanup 失败可容忍 (下次请求再清)
def _cleanup_expired(self):
    with safe_connect_for_write(self._db_path, force_no_tx=True) as conn:
        conn.execute('DELETE FROM token_blacklist WHERE expires_at < ?', (now,))
        conn.commit()

# 决策 B: 迁移到 bo_framework.transaction()
# 理由: 与 is_blacklisted 共用事务, 原子性更好
def _cleanup_expired(self):
    with bo_framework.transaction() as txn:
        with safe_connect_for_write(self._db_path) as conn:
            conn.execute('DELETE FROM token_blacklist WHERE expires_at < ?', (now,))
```

**默认推荐 A**：cleanup 是辅助操作，独立事务更轻量。失败下次重试。

### 5.4 调用方事务包裹模板

```python
# 修改前
def grant_intent_api():
    dao = RoleIntentDAO()
    success = dao.grant(role_id=1, bo_id='user', action_name='create')
    return jsonify({'success': success})

# 修改后
def grant_intent_api():
    from meta.core.bo_framework import bo_framework
    dao = RoleIntentDAO()
    with bo_framework.transaction() as txn:
        success = dao.grant(role_id=1, bo_id='user', action_name='create')
        if not success:
            raise RuntimeError("grant failed")
    return jsonify({'success': success})
```

### 5.5 验收

- [ ] `verify_v007_41.py` Test 12（safe_connect_for_write raise）通过
- [ ] `pytest meta/tests/test_v007_41_l0_write_in_tx.py` 100% 通过
- [ ] silent partial commit 测试：3 个表都不应该出现"事务回滚后仍写入"的痕迹
- [ ] V007.40 14 项验证仍 100% 通过
- [ ] Phase 1 + Phase 2 单元测试仍 100% 通过

## 6. Phase 4: 验证 + 文档（Day 3）

### 6.1 目标

- `verify_v007_41.py` 15 项 100% 通过
- `docs/SPEC_V007.41.md` 镜像同步
- `.trae/rules/core/checklist.md` 更新

### 6.2 提交清单

**Commit 4**: `fix(be): V007.41 T10-T11 - verify_v007_41.py + docs sync`

包含：
- `verify_v007_41.py` (新建)
- `docs/SPEC_V007.41.md` (新建)
- `.trae/rules/core/checklist.md` (修改)

### 6.3 验收

- [ ] `python verify_v007_41.py` 15/15 通过
- [ ] `python verify_v007_40.py` 14/14 仍通过
- [ ] 所有 4 个 commit 已合并到 `release/pre-2026-06-29`

## 7. 部署计划

### 7.1 release-prep 服务器（先）

1. 部署 Commit 4
2. 监控 24h
3. 验证指标：
   - `v007_41_safe_connect_read_total` 应持续增长（每分钟数百次）
   - `v007_41_safe_connect_write_no_tx_total` 应 = 0（如果 > 0 说明有写路径漏迁）
   - `v007_41_safe_connect_tx_state_unknown_total` 应 ≈ 0
   - disk I/O error 日志 = 0
4. 观察 24h 无问题 → 进入 yonaa

### 7.2 yonaa 生产（后）

1. 灰度 1 个实例（先关 1 个 Flask worker）
2. 监控 2h
3. 全量部署
4. 监控 1 周

## 8. 回滚策略

每个 Phase 单独可回滚：

| Phase | 回滚命令 | 影响范围 |
|---|---|---|
| Phase 1 | `git revert <commit 1>` | safe_connect 模块不存在，依赖方 ImportError → 必须 Phase 2 一起回滚 |
| Phase 2 | `git revert <commit 2>` | 17 处改回原 V007.40 写法，无功能影响 |
| Phase 3 | `git revert <commit 3>` | 写路径回到 L0 直连，silent partial commit 风险恢复，但 V007.40 14 项验证仍过 |
| Phase 4 | `git revert <commit 4>` | 仅文档，无功能影响 |

**应急逃生口**（不需回滚代码）：
- 设置 `BO_FRAMEWORK_TX_FORCE=False` 环境变量 → safe_connect_for_write 不 raise
- 设置 `BO_FRAMEWORK_TX_FORCE=true` 且 `enforce_write_in_tx=False` → 关闭守卫但保留 metric

## 9. 关键代码变更预览

### 9.1 safe_connect.py 完整骨架

```python
# meta/core/safe_connect.py
"""V007.41 safe_connect - 统一 L0 裸连接工厂..."""
from __future__ import annotations
import sqlite3
import logging
from contextlib import contextmanager

from meta.core.sqlite_tx_state import get_tx_state, TxState
from meta.core.sql_config import get_safe_connect_config
from meta.core.observability import OBS_COUNTERS

logger = logging.getLogger(__name__)


def _bump_counter(name: str) -> None:
    try:
        c = OBS_COUNTERS.get(name)
        if c and hasattr(c, 'inc'):
            c.inc()
    except Exception as e:
        logger.debug(f"safe_connect metric bump failed: {e}")


@contextmanager
def safe_connect_for_read(db_path: str):
    """[V007.41] L0 只读裸连接工厂"""
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
    """[V007.41] L0 写裸连接工厂, 强制 V3 事务上下文"""
    _bump_counter('v007_41_safe_connect_write_total')
    cfg = get_safe_connect_config()
    if cfg.enforce_write_in_tx and not force_no_tx:
        with safe_connect_for_read(db_path) as probe_conn:
            state = get_tx_state(probe_conn)
        if state == TxState.NONE:
            _bump_counter('v007_41_safe_connect_write_no_tx_total')
            raise ConnectionRefusedError(
                "[V007.41] safe_connect_for_write requires outer transaction. "
                "Use 'with bo_framework.transaction() as txn:' or call from "
                "ds.transaction()/UnitOfWork. If this is an admin one-shot, "
                "pass force_no_tx=True."
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
    """[V007.41] 兼容旧调用"""
    if mode == "read":
        with safe_connect_for_read(db_path) as conn:
            yield conn
    elif mode == "write":
        with safe_connect_for_write(db_path) as conn:
            yield conn
    elif mode == "write_force_no_tx":
        with safe_connect_for_write(db_path, force_no_tx=True) as conn:
            yield conn
    else:
        logger.debug("[V007.41] safe_connect mode=auto, defaulting to read")
        with safe_connect_for_read(db_path) as conn:
            yield conn
```

### 9.2 intent_resolver.py 改造示例

```python
# 修改前 (V007.40)
def _safe_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def grant(self, role_id, bo_id, action_name, parameters=None, source='manual'):
    conn = _safe_connect(self._db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO role_intents ...", ...)
    conn.commit()
    conn.close()

# 修改后 (V007.41)
from meta.core.safe_connect import safe_connect_for_read

def grant(self, role_id, bo_id, action_name, parameters=None, source='manual'):
    """授予 Intent 权限
    
    [V007.41] 调用方必须在外层事务中:
        with bo_framework.transaction() as txn:
            dao.grant(role_id=..., bo_id=..., action_name=...)
    """
    with safe_connect_for_read(self._db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO role_intents ...", ...)
        # 外层事务负责 commit, 这里不要 conn.commit()!
```

## 10. 总结

V007.41 是 V007.40 的**架构升级**：
- 17 处分散修复 → 1 个统一工厂
- L0 直连写 → L0 + V3 事务
- 补丁式 → 可观测、可降级、可演进

预计 3 个工作日完成，零破坏性，独立可回滚。