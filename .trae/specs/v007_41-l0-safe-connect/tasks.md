# V007.41 任务清单（执行版）

> **状态**：未启动
> **依赖**：V007.40 commit `7c71636` 已合并到 `release/pre-2026-06-29`
> **预计工作量**：2-3 工作日（不含部署）

## Task 1: 工厂核心代码

**文件**: `meta/core/safe_connect.py` (新建)
**行数预估**: ~150
**工作量**: 0.5 天

### 子任务

- [ ] 1.1 写模块 docstring + import
- [ ] 1.2 实现 `_bump_counter(name)` 内部 helper
- [ ] 1.3 实现 `safe_connect_for_read(db_path)` contextmanager
- [ ] 1.4 实现 `safe_connect_for_write(db_path, force_no_tx=False)` contextmanager
  - [ ] 1.4.1 集成 `sqlite_tx_state.get_tx_state` 探测
  - [ ] 1.4.2 NONE 状态 raise ConnectionRefusedError
  - [ ] 1.4.3 UNKNOWN 状态降级（log + metric + 放行）
  - [ ] 1.4.4 force_no_tx=True 绕过 + metric 标记
- [ ] 1.5 实现 `safe_connect(db_path, mode="auto")` 兼容函数
- [ ] 1.6 单元自测：模块可 import，三个 API 可调用

## Task 2: 配置化默认值

**文件**: `meta/core/sql_config.py` (修改)
**工作量**: 0.5 天

### 子任务

- [ ] 2.1 添加 `SafeConnectConfig` dataclass 到 `sql_config.py`
  ```python
  @dataclass
  class SafeConnectConfig:
      timeout: float = 30.0
      busy_timeout_ms: int = 30000
      check_same_thread: bool = False
      enforce_write_in_tx: bool = True
      tx_state_unknown_passthrough: bool = True
  ```
- [ ] 2.2 添加 `get_safe_connect_config()` 函数（返回单例或新实例）
- [ ] 2.3 添加 `BO_FRAMEWORK_TX_FORCE` 环境变量支持（V007.41 FR-002 逃生口）
- [ ] 2.4 更新 `tests/test_sql_config.py` 断言 SafeConnectConfig 字段
- [ ] 2.5 验证：导入无 error

## Task 3: metric 集成

**文件**: `meta/core/observability.py` (修改)
**工作量**: 0.25 天

### 子任务

- [ ] 3.1 在 OBS_COUNTERS 字典新增 4 项：
  ```python
  'safe_connect_read': 'v007_41_safe_connect_read_total',
  'safe_connect_write': 'v007_41_safe_connect_write_total',
  'safe_connect_write_no_tx': 'v007_41_safe_connect_write_no_tx_total',
  'safe_connect_tx_unknown': 'v007_41_safe_connect_tx_state_unknown_total',
  ```
- [ ] 3.2 验证：不破坏现有 V007.24 pool_init_count 等 metric

## Task 4: 单元测试

**文件**: `meta/tests/test_v007_41_safe_connect.py` (新建)
**工作量**: 0.5 天

### 子任务

- [ ] 4.1 `test_safe_connect_for_read_default_params`：验证 timeout/busy_timeout/check_same_thread
- [ ] 4.2 `test_safe_connect_for_read_contextmanager`：验证 with 退出自动 close
- [ ] 4.3 `test_safe_connect_for_write_in_tx`：模拟外层事务，写连接可用
- [ ] 4.4 `test_safe_connect_for_write_no_tx_raises`：无事务时 raise ConnectionRefusedError
- [ ] 4.5 `test_safe_connect_for_write_force_no_tx`：force_no_tx=True 不 raise
- [ ] 4.6 `test_safe_connect_for_write_tx_unknown_passthrough`：UNKNOWN 状态降级放行
- [ ] 4.7 `test_safe_connect_auto_mode`：兼容 mode="auto"
- [ ] 4.8 `test_metric_counters`：验证 4 个 metric 正确递增
- [ ] 4.9 `test_safe_connect_config_integration`：验证 SafeConnectConfig 生效
- [ ] 4.10 全部测试通过

## Task 5: 迁移本地 helper 持有者（Phase 2.1）

**工作量**: 0.5 天

### 子任务

- [ ] 5.1 `meta/core/intent_resolver.py`
  - [ ] 5.1.1 删除 `_safe_connect` 函数（line 44-58）
  - [ ] 5.1.2 替换 7 处调用 `_safe_connect(self._db_path)` → `safe_connect_for_read(self._db_path)`
  - [ ] 5.1.3 删除 `import sqlite3`（如果不再用）
- [ ] 5.2 `meta/services/subflow_template_store.py`
  - [ ] 5.2.1 删除 `_safe_connect` 函数
  - [ ] 5.2.2 替换 4 处调用
- [ ] 5.3 `meta/services/token_blacklist_service.py`
  - [ ] 5.3.1 删除 `_get_connection` 函数
  - [ ] 5.3.2 替换 3 处调用（`_cleanup_expired` / `add_to_blacklist` / `is_blacklisted`）
- [ ] 5.4 `meta/api/filter_variant_api.py`
  - [ ] 5.4.1 拆分 `_execute_query` 为 `_execute_read_query` + `_execute_write_query`
  - [ ] 5.4.2 内部 `sqlite3.connect(...)` → `safe_connect_for_read/write`

## Task 6: 迁移内联 sqlite3.connect（Phase 2.2）

**工作量**: 0.5 天

### 子任务

- [ ] 6.1 `meta/core/runtime_dimension_resolver.py` 3 处
- [ ] 6.2 `meta/core/dim_scope_overlap_detector.py` 2 处
- [ ] 6.3 `meta/services/audit_export.py` 1 处
- [ ] 6.4 `meta/core/sql_adapters.py` `fresh_connection()` 1 处
- [ ] 6.5 `meta/core/app_builder.py` 2 处（preflight + startup）

## Task 7: 清理 V007.40 残留（Phase 2.3）

**工作量**: 0.25 天

### 子任务

- [ ] 7.1 `git diff` 扫描所有生产代码
- [ ] 7.2 删除残留的 `timeout=30.0` / `check_same_thread=False` / `PRAGMA busy_timeout = 30000`（除 safe_connect.py 内部）
- [ ] 7.3 例外：`migrations/ scripts/ tests/conftest.py` 保留

## Task 8: 写迁移到 V3（Phase 3）

**工作量**: 1 天（最危险，需谨慎）

### 子任务

- [ ] 8.1 列出 `intent_resolver.grant/deny/revoke` 调用方
  ```bash
  cd D:\filework\release-prep-worktree
  grep -rn "intent_resolver\.\(grant\|deny\|revoke\)\|RoleIntentDAO.*grant\|RoleIntentDAO.*deny\|RoleIntentDAO.*revoke" \
    meta/ --include="*.py" --exclude-dir=migrations
  ```
- [ ] 8.2 调用方加 `bo_framework.transaction()` 包裹
- [ ] 8.3 `intent_resolver` 内部 `sqlite3.connect` → `safe_connect_for_write`
- [ ] 8.4 `subflow_template_store.delete/save` 同上迁移
- [ ] 8.5 `filter_variant_api` POST/PUT/DELETE 路由加 `bo_framework.transaction()`
- [ ] 8.6 `token_blacklist_service._cleanup_expired` 决策
  - 默认：保留 L0 + `force_no_tx=True`（cleanup 每次请求独立事务更轻量）
  - 如选 B：迁移到 `bo_framework.transaction()`

## Task 9: 写迁移测试（Phase 3.7）

**文件**: `meta/tests/test_v007_41_l0_write_in_tx.py` (新建)
**工作量**: 0.5 天

### 子任务

- [ ] 9.1 `test_intent_resolver_grant_in_tx_rollback`
  - 在事务中 grant → raise → 验证 role_intents 表无新行
- [ ] 9.2 `test_subflow_template_store_delete_in_tx_rollback`
  - 在事务中 delete → raise → 验证 subflow_templates 表无删除
- [ ] 9.3 `test_filter_variant_api_create_in_tx_rollback`
  - 在事务中 create_variant → raise → 验证 filter_variants 表无新行
- [ ] 9.4 `test_no_silent_partial_commit`
  - 综合：3 个表都不应该出现写入痕迹

## Task 10: verify_v007_41.py 集成验证（Phase 4.1）

**文件**: `verify_v007_41.py` (新建)
**工作量**: 0.5 天

### 子任务

- [ ] 10.1 Test 1-15 全部实现（参考 checklist.md 4.1）
- [ ] 10.2 验证：100% 通过

## Task 11: 文档同步

**工作量**: 0.25 天

### 子任务

- [ ] 11.1 复制 `spec.md` 到 `docs/SPEC_V007.41.md`
- [ ] 11.2 更新 `.trae/rules/core/checklist.md` 加 V007.41 检查项
- [ ] 11.3 更新 `meta/core/sql_connection_pool.py` docstring，引用 safe_connect

## 执行顺序

```
Task 1 ──→ Task 2 ──→ Task 3
              │           │
              └→ Task 4 ─┘  (测试驱动)
                            │
                            ▼
            Task 5 ──→ Task 6 ──→ Task 7
                              │
                              ▼
            Task 8 (Phase 3) ──→ Task 9
                              │
                              ▼
            Task 10 ──→ Task 11
                       │
                       ▼
                  Verification
```

## 提交规范

每 Task 或 Task 组一个 commit：

```
fix(be): V007.41 T1-T4 - safe_connect factory + config + metric + unit tests
fix(be): V007.41 T5-T7 - migrate 17 L0 sites to safe_connect
fix(be): V007.41 T8-T9 - migrate L0 writes to bo_framework.transaction()
fix(be): V007.41 T10-T11 - verify_v007_41.py + docs sync
```

## 风险评估

| 风险点 | 缓解 |
|---|---|
| Task 8 写迁移破坏现有业务 | 单独 commit + 灰度部署；保留 force_no_tx 逃生口 |
| Task 6 迁移时漏掉某些 sqlite3.connect | verify_v007_41.py Test 1 强制 0 处 |
| Task 5 删除 _safe_connect 后被其他文件 import | `grep -rn "_safe_connect" meta/` 全量扫描 |
| Python 3.9 vs 3.12 in_transaction 行为差异 | sqlite_tx_state.py 已处理 fallback |

## 验收门禁

- [ ] 所有 Task 子任务勾选
- [ ] 4 个 commit 合并到 `release/pre-2026-06-29`
- [ ] `verify_v007_41.py` 15/15 通过
- [ ] `verify_v007_40.py` 14/14 仍通过（零破坏性）
- [ ] `pytest meta/tests/test_v007_41_*.py` 100% 通过
- [ ] release-prep 服务器部署后 24h disk I/O error = 0 复发
- [ ] yonaa 生产部署后 1 周 disk I/O error = 0 复发