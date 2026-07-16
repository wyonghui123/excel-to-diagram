# V007.42 任务清单（执行版）

> **状态**：未启动
> **依赖**：V007.41 commit `3838a5b` 已合并到 `release/pre-2026-06-29`
> **预计工作量**：2-3 工作日（不含部署）

## Task 1: mmap_size 配置化 (FR-008, P0 关键)

**文件**: `meta/core/sql_connection_pool.py` (修改)
**工作量**: 0.5 天

### 子任务

- [ ] 1.1 `ConnectionConfig` 新增 `mmap_size: int = 0` 字段
- [ ] 1.2 `_create_connection()` 中 `PRAGMA mmap_size = 67108864` 改为 `PRAGMA mmap_size = {config.mmap_size}`
- [ ] 1.3 新增 `SQLITE_MMAP_SIZE` 环境变量覆盖: `config.mmap_size = int(os.environ.get('SQLITE_MMAP_SIZE', str(config.mmap_size)))`
- [ ] 1.4 日志记录 mmap_size 配置值: `logger.info("[V007.42] mmap_size=%d", config.mmap_size)`
- [ ] 1.5 更新 `verify_v007_41.py` 中 PRAGMA mmap_size 断言（从 67108864 改为 0）
- [ ] 1.6 验证: `python -c "from meta.core.sql_connection_pool import ConnectionConfig; c=ConnectionConfig(); assert c.mmap_size==0"`

## Task 2: I/O 限流器 (FR-002)

**文件**: `meta/core/sql_connection_pool.py` (修改)
**工作量**: 0.5 天

### 子任务

- [ ] 2.1 `SQLiteConnectionPool.__init__` 新增限流器字段:
  ```python
  self._io_error_count = 0
  self._io_error_window_start = time.time()
  self._io_rate_limit_active = False
  self._io_error_lock = threading.Lock()
  ```
- [ ] 2.2 实现 `_record_io_error()` 方法:
  - 滑动窗口 (60s) + 阈值 (10 次) + 激活限流
  - 环境变量: `SQLITE_IO_RATE_LIMIT_THRESHOLD`, `SQLITE_IO_RATE_LIMIT_WINDOW`
  - 激活时记 WARNING 日志 + metric `io_rate_limit_triggered_total`
- [ ] 2.3 实现 `_check_io_rate_limit()` 方法:
  - 限流状态时 `time.sleep(0.2)` (减速不拒绝)
  - 逃生口: `SQLITE_IO_RATE_LIMIT_DISABLE` 环境变量
- [ ] 2.4 在 `_execute_via_read_pool` 捕获 disk I/O error 时调用 `_record_io_error()`
- [ ] 2.5 在 `_execute_via_read_pool` 执行前调用 `_check_io_rate_limit()`
- [ ] 2.6 验证: 限流器字段初始化正确

## Task 3: Retry 升级 (FR-001)

**文件**: `meta/core/sql_adapters.py` (修改)
**工作量**: 0.5 天

### 子任务

- [ ] 3.1 替换固定指数退避为 Decorrelated Jitter:
  ```python
  # 旧: delay = 0.05 * (2 ** attempt) + random.uniform(0, 0.02)
  # 新: delay = min(2.0, random.uniform(0.2, prev_sleep * 3))
  ```
- [ ] 3.2 确认 max_retries = 3 (不改为 5)
- [ ] 3.3 确认 base = 200ms (从 50ms 提升)
- [ ] 3.4 确认 cap = 2s
- [ ] 3.5 每次重试前: reader() 重建坏连接 (已有 mark_error) + I/O 限流检查
- [ ] 3.6 重试日志增加 attempt 编号 + 实际 sleep 时间
- [ ] 3.7 环境变量 `SQLITE_READ_RETRY_MAX` / `SQLITE_READ_RETRY_BASE_MS` 可覆盖
- [ ] 3.8 验证: retry 逻辑不破坏现有读查询

## Task 4: max_readers 调整 (FR-009)

**文件**: `meta/core/sql_connection_pool.py` + `meta/core/sql_adapters.py` (修改)
**工作量**: 0.25 天

### 子任务

- [ ] 4.1 `ConnectionConfig.max_readers` 默认值 20 → 10
- [ ] 4.2 `sql_adapters.py _connect_pool` 中 `kwargs.get("max_readers", 20)` → `kwargs.get("max_readers", 10)`
- [ ] 4.3 环境变量 `SQLITE_MAX_READERS` 可覆盖
- [ ] 4.4 验证: 连接池初始化时 max_readers=10

## Task 5: Retry + mmap 单元测试

**文件**: `meta/tests/test_v007_42_read_retry.py` (新建)
**工作量**: 0.5 天

### 子任务

- [ ] 5.1 `test_retry_3_attempts`: mock 连接, 验证 3 次执行后 raise
- [ ] 5.2 `test_decorrelated_jitter_base_200ms`: 验证最小 sleep ≥ 200ms
- [ ] 5.3 `test_decorrelated_jitter_cap_2s`: 验证 sleep ≤ 2000ms
- [ ] 5.4 `test_io_rate_limit_triggered`: 模拟 10 次 I/O error, 验证限流激活
- [ ] 5.5 `test_io_rate_limit_disable`: 设置环境变量, 验证不限流
- [ ] 5.6 `test_mmap_size_default_zero`: 验证 ConnectionConfig.mmap_size=0
- [ ] 5.7 `test_mmap_size_env_override`: 设置 SQLITE_MMAP_SIZE, 验证覆盖
- [ ] 5.8 `test_max_readers_default_10`: 验证默认 max_readers=10
- [ ] 5.9 全部测试通过

## Task 6: WAL 监控指标 (FR-003)

**文件**: `meta/core/sql_connection_pool.py` (修改)
**工作量**: 0.5 天

### 子任务

- [ ] 6.1 `health_check()` 输出增加 `checkpoint_busy` 字段:
  - 执行 `PRAGMA wal_checkpoint(PASSIVE)` 获取 busy 值
  - checkpoint_busy > 0 持续 > 300s 记 WARNING
- [ ] 6.2 `health_check()` 输出增加 `reader_health` 字段:
  - 统计读连接池中 healthy/errored 连接数
  - `{healthy: N, errored: M}` 格式
- [ ] 6.3 新增 metric `wal_checkpoint_busy_total` + `reader_errored_total`
- [ ] 6.4 验证: health_check 返回新增字段

## Task 7: WAL 饥饿缩容 (FR-004)

**文件**: `meta/core/sql_connection_pool.py` (修改)
**工作量**: 0.5 天

### 子任务

- [ ] 7.1 `force_passive_checkpoint()` 失败后检查 `checkpoint_starvation_seconds`
- [ ] 7.2 starvation > 60s: 临时将 max_readers 从当前值降到 5
- [ ] 7.3 释放后重试 PASSIVE checkpoint
- [ ] 7.4 checkpoint 成功后 30s 恢复 max_readers 到原值
- [ ] 7.5 新增 metric `pool_shrink_total` + `pool_expand_total`
- [ ] 7.6 验证: 缩放操作记 INFO 日志

## Task 8: Import Fix (FR-005)

**文件**: `meta/services/async_import_service.py` (修改)
**工作量**: 0.25 天

### 子任务

- [ ] 8.1 新增 `get_all_tasks() -> Dict[str, Dict]`:
  ```python
  def get_all_tasks(self) -> Dict[str, Dict]:
      with self._task_lock:
          return {
              task_id: {
                  'id': task.id,
                  'status': task.status.value,
                  'created_at': task.created_at.isoformat(),
                  'error': task.error,
              }
              for task_id, task in self._tasks.items()
          }
  ```
- [ ] 8.2 验证: `ImportQueueHandler.execute()` 不再 raise AttributeError

## Task 9: 长事务检测 (FR-006)

**文件**: `meta/core/bo_framework.py` (修改)
**工作量**: 0.25 天

### 子任务

- [ ] 9.1 `TransactionContext.__enter__` 记录 `self._start_time = time.time()`
- [ ] 9.2 `TransactionContext.__exit__` 计算 `duration = time.time() - self._start_time`
- [ ] 9.3 duration > 30s: `logger.warning("[V007.42] long transaction: %.1fs, txn=%s", duration, self.tran)`
- [ ] 9.4 duration > 120s: `logger.error(...)` + metric `long_transaction_total`
- [ ] 9.5 不强制 rollback (仅告警)
- [ ] 9.6 验证: TransactionContext 有 _start_time 字段

## Task 10: async_audit_writer 统一 (FR-010)

**文件**: `meta/services/async_audit_writer.py` (修改)
**工作量**: 0.25 天

### 子任务

- [ ] 10.1 替换 `sqlite3.connect(...)` → `from meta.core.safe_connect import safe_connect_for_write`
- [ ] 10.2 使用 `with safe_connect_for_write(db_path, force_no_tx=True) as conn:`
- [ ] 10.3 确保有 PRAGMA busy_timeout (safe_connect_for_write 已封装)
- [ ] 10.4 确保无 mmap_size (safe_connect_for_write 默认 0)
- [ ] 10.5 验证: `grep "sqlite3.connect" meta/services/async_audit_writer.py` = 0

## Task 11: Metric 集成 (FR-007)

**文件**: `meta/core/observability.py` (修改)
**工作量**: 0.25 天

### 子任务

- [ ] 11.1 新增 10 个 metric 到 OBS_COUNTERS:
  - `read_retry_total`
  - `read_retry_success_total`
  - `io_rate_limit_triggered_total`
  - `wal_checkpoint_busy_total`
  - `reader_errored_total`
  - `long_transaction_total`
  - `pool_shrink_total`
  - `pool_expand_total`
  - `sqlite_version_compliant` (FR-011)
  - `heartbeat_check_failed_total` (FR-012)
- [ ] 11.2 验证: 不破坏现有 metric

## Task 12: SQLite 版本守卫 (FR-011)

**文件**: `meta/core/sqlite_version_guard.py` (新建)
**工作量**: 0.25 天

### 子任务

- [ ] 12.1 创建模块，导出 `check_sqlite_version()` 函数
- [ ] 12.2 检测 `sqlite3.sqlite_version`，< 3.51.3 记 WARNING
- [ ] 12.3 设 metric `sqlite_version_compliant` (0/1)
- [ ] 12.4 环境变量 `SQLITE_REQUIRE_MIN_VERSION` 可强制 raise
- [ ] 12.5 在 `bo_framework.__init__` 启动时调用一次
- [ ] 12.6 验证: WARNING 日志格式正确

## Task 13: 后台心跳线程 (FR-012)

**文件**: `meta/core/db_heartbeat.py` (新建)
**工作量**: 0.5 天

### 子任务

- [ ] 13.1 创建 `DBHeartbeat` 类，含 start/stop 方法
- [ ] 13.2 daemon 线程，每 30s 调用 `PRAGMA quick_check`
- [ ] 13.3 失败时: WARNING 日志 + 触发连接重建 + metric
- [ ] 13.4 连续 3 次失败升级为 ERROR
- [ ] 13.5 环境变量 `SQLITE_HEARTBEAT_INTERVAL` / `SQLITE_HEARTBEAT_DISABLE`
- [ ] 13.6 集成到 `bo_framework.__init__` (与 V007.16 连接池绑定)
- [ ] 13.7 新增 `test_v007_42_heartbeat.py` 单元测试
- [ ] 13.8 验证: 心跳线程正常启停

## Task 14: 集成验证 (Phase 7)

**文件**: `verify_v007_42.py` (新建)
**工作量**: 0.5 天

### 子任务

- [ ] 14.1 实现 17 项验证 (参考 checklist.md)
  - Test 1-15: 原 FR-001~010 验证项
  - Test 16: sqlite_version_guard 检测 < 3.51.3 WARNING (FR-011)
  - Test 17: db_heartbeat 模块存在 + 线程可启停 (FR-012)
- [ ] 14.2 验证: 100% 通过
- [ ] 14.3 验证: `python verify_v007_41.py` 仍 100% 通过
- [ ] 14.4 复制 spec 到 `docs/SPEC_V007.42.md`

## Task 15: WAL + Import 单元测试

**文件**: `meta/tests/test_v007_42_wal_monitor.py` + `meta/tests/test_v007_42_import_fix.py` (新建)
**工作量**: 0.5 天

### 子任务

- [ ] 15.1 `test_v007_42_wal_monitor.py`:
  - `test_health_check_checkpoint_busy`
  - `test_health_check_reader_health`
  - `test_checkpoint_starvation_triggers_shrink`
  - `test_checkpoint_recovery_expands_pool`
- [ ] 15.2 `test_v007_42_import_fix.py`:
  - `test_get_all_tasks_empty`
  - `test_get_all_tasks_one`
  - `test_get_all_tasks_multiple`
  - `test_import_queue_handler_no_error`
- [ ] 15.3 全部测试通过

## 执行顺序

```
Task 1 (mmap) ──→ Task 2 (限流器) ──→ Task 3 (retry)
                                            │
                    Task 4 (max_readers) ────┤
                    Task 12 (版本守卫) ──────┤  (FR-011 新增)
                    Task 13 (心跳) ──────────┤  (FR-012 新增)
                                            │
                    Task 5 (测试 P5) ────────┤
                                            ▼
                    Task 6 (WAL监控) ──→ Task 7 (WAL缩容)
                                            │
                    Task 8 (Import) ─────────┤
                    Task 9 (长事务) ─────────┤
                    Task 10 (审计) ──────────┤
                    Task 11 (metric) ────────┤
                                            │
                    Task 15 (测试 P6) ───────┤
                                            ▼
                    Task 14 (verify P7)
```

## 提交规范

3 个 commit：

```
fix(be): V007.42 P5 - mmap fix + retry upgrade + I/O rate limiter

[V007.42] Phase 5: mmap 修正 + Retry 升级 + I/O 限流
- sql_connection_pool.py: ConnectionConfig.mmap_size=0, I/O 限流器, max_readers=10
- sql_adapters.py: Decorrelated Jitter (base=200ms, cap=2s, max=3)
- test_v007_42_read_retry.py: 单元测试
- observability.py: 4 个新 metric
```

```
fix(be): V007.42 P6 - WAL monitor + import fix + long-tx guard + audit unify

[V007.42] Phase 6: WAL 监控 + Import Fix + 长事务防护 + 审计统一
- sql_connection_pool.py: health_check 增强 + 动态缩容
- async_import_service.py: get_all_tasks()
- bo_framework.py: TransactionContext 长事务检测
- async_audit_writer.py: 裸连接统一
- test_v007_42_wal_monitor.py + test_v007_42_import_fix.py
- observability.py: 4 个新 metric
```

```
fix(be): V007.42 P7 - verify + docs

[V007.42] Phase 7: 集成验证 + 文档
- verify_v007_42.py: 15 项验证
- docs/SPEC_V007.42.md: spec 镜像
```

## 风险评估

| 风险点 | 缓解 |
|---|---|
| mmap_size=0 导致读性能下降 | `cache_size=-2000` 仍提供页缓存; `SQLITE_MMAP_SIZE` 环境变量可恢复 |
| I/O 限流器误触发 | 60s/10次阈值; 限流只 sleep 不拒绝; `SQLITE_IO_RATE_LIMIT_DISABLE` 逃生口 |
| max_readers 10 不够用 | Flask 8-16 worker 下 10 足够; `SQLITE_MAX_READERS` 可调高 |
| async_audit_writer 迁移失败 | 审计写入异步队列, 失败可容忍; force_no_tx=True 保留 |
| verify_v007_41.py PRAGMA 断言失败 | 需更新 mmap_size 断言从 67108864→0 |

## 验收门禁

- [ ] 所有 Task 子任务勾选
- [ ] 3 个 commit 合并到 `release/pre-2026-06-29`
- [ ] `verify_v007_42.py` 17/17 通过
- [ ] `verify_v007_41.py` 仍通过（零破坏性）
- [ ] `pytest meta/tests/test_v007_42_*.py` 100% 通过
- [ ] release-prep 服务器部署后 24h disk I/O error 频率下降 ≥80%
- [ ] yonaa 生产部署后 1 周 disk I/O error = 0 复发
- [ ] **新增**: SQLite 版本 < 3.51.3 触发 WARNING (FR-011) - 不阻断启动
- [ ] **新增**: 后台心跳线程成功启停 (FR-012)
