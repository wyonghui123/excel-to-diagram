# V007.42 实施检查清单

> **完成状态**：未启动
> **使用方式**：每完成一项打勾并写明 commit hash。所有项完成后即可进入验证阶段。

## Commit 记录

- **P5** (____): mmap 修正 + Retry 升级 + I/O 限流
- **P6** (____): WAL 监控 + Import Fix + 长事务防护
- **P7** (____): 集成验证 + 文档

## 验收状态

- [ ] **FR-001** 连接池级 Retry 机制升级 (Decorrelated Jitter, 3 attempts, base=200ms, cap=2s, **总预算 ≥250ms**)
- [ ] **FR-002** 读连接池 I/O Health Guard (I/O 限流器, 60s/10次阈值, sleep 200ms 不拒绝)
- [ ] **FR-003** WAL Checkpoint 监控指标 (checkpoint_busy + reader_health)
- [ ] **FR-004** WAL 饥饿时主动释放读连接 (max_readers 缩容)
- [ ] **FR-005** 修复 ImportQueueHandler.get_all_tasks() (AttributeError)
- [ ] **FR-006** 长事务防护 (>30s WARNING, >120s ERROR)
- [ ] **FR-007** 全链路 Metric 集成 (10 个新 metric)
- [ ] **FR-008** mmap_size 可配置化 + 默认值 0 (P0 关键修改)
- [ ] **FR-009** max_readers 默认值 5→10 (D3 修正)
- [ ] **FR-010** async_audit_writer 裸连接统一
- [ ] **FR-011** SQLite 版本基线检查 (D2 新增: < 3.51.3 WARNING)
- [ ] **FR-012** 主动健康检查心跳 (D4 新增: PRAGMA quick_check)
- [ ] **NFR-001** Retry 性能开销 <1%/request
- [ ] **NFR-002** 零破坏性 (V007.41 验证仍通过)
- [ ] **NFR-003** 可降级 (限流/mmap 均有环境变量逃生口)
- [ ] **NFR-004** 向后兼容

## Phase 5: mmap 修正 + Retry 升级 + I/O 限流

- [ ] **5.1** 修改 `ConnectionConfig` 增加 `mmap_size: int = 0` 字段 (FR-008)
  - commit: ____

- [ ] **5.2** 修改 `_create_connection()` PRAGMA mmap_size 从硬编码改为读取 config (FR-008)
  - `PRAGMA mmap_size = 67108864` → `PRAGMA mmap_size = {config.mmap_size}`
  - 环境变量 `SQLITE_MMAP_SIZE` 可覆盖
  - commit: ____

- [ ] **5.3** 增加 I/O 限流器到 `SQLiteConnectionPool` (FR-002)
  - `_record_io_error()`: 记录 disk I/O error, 检查窗口阈值
  - `_check_io_rate_limit()`: 限流状态时 sleep 200ms
  - 环境变量 `SQLITE_IO_RATE_LIMIT_THRESHOLD` / `SQLITE_IO_RATE_LIMIT_WINDOW` / `SQLITE_IO_RATE_LIMIT_DISABLE`
  - commit: ____

- [ ] **5.4** 修改 `_execute_via_read_pool` retry 逻辑 (FR-001)
  - max_retries: 保持 3
  - base: 50ms → 200ms
  - cap: 2s
  - 退避算法: 固定指数 → Decorrelated Jitter
  - 每次重试前: reader() 重建坏连接 + 检查 I/O 限流
  - commit: ____

- [ ] **5.5** 修改 `_connect_pool` max_readers 默认值 20→10 (FR-009)
  - `kwargs.get("max_readers", 10)`
  - 环境变量 `SQLITE_MAX_READERS` 可覆盖
  - commit: ____

- [ ] **5.6** 新增 `test_v007_42_read_retry.py`
  - test_retry_3_attempts: 验证 3 次执行
  - test_decorrelated_jitter_base_200ms: 验证最小延迟 200ms
  - test_decorrelated_jitter_cap_2s: 验证最大延迟 2s
  - test_io_rate_limit_triggered: 限流触发后 sleep 200ms
  - test_io_rate_limit_disable: 环境变量禁用限流
  - test_mmap_size_default_zero: 默认 mmap_size=0
  - test_mmap_size_env_override: SQLITE_MMAP_SIZE 环境变量覆盖
  - commit: ____

- [ ] **5.7** 新增 metric 到 `observability.py` (FR-007 部分)
  - `read_retry_total`
  - `read_retry_success_total`
  - `io_rate_limit_triggered_total`
  - `reader_errored_total`
  - commit: ____

- [ ] **5.8** 新增 `meta/core/sqlite_version_guard.py` (FR-011)
  - 检测 `sqlite3.sqlite_version`，< 3.51.3 WARNING
  - 设 metric `sqlite_version_compliant`
  - 环境变量 `SQLITE_REQUIRE_MIN_VERSION` 可强制 raise
  - 在 `bo_framework.__init__` 启动时调用一次
  - commit: ____

- [ ] **5.9** 新增 `meta/core/db_heartbeat.py` (FR-012)
  - daemon 线程，每 30s `PRAGMA quick_check`
  - 失败: WARNING + 触发连接重建 + metric `heartbeat_check_failed_total`
  - 连续 3 次失败升级为 ERROR
  - 环境变量 `SQLITE_HEARTBEAT_INTERVAL` / `SQLITE_HEARTBEAT_DISABLE`
  - 集成到 `bo_framework.__init__`
  - 新增 `test_v007_42_heartbeat.py`
  - commit: ____

## Phase 6: WAL 监控 + Import Fix + 长事务防护

- [ ] **6.1** 修改 `health_check()` 增加 checkpoint_busy + reader_health (FR-003)
  - `PRAGMA wal_checkpoint(PASSIVE)` 返回 busy 字段
  - 读连接健康统计: {healthy: N, errored: M}
  - checkpoint_busy > 0 持续 > 300s 记 WARNING
  - commit: ____

- [ ] **6.2** 修改 `force_passive_checkpoint()` 失败后动态缩容 max_readers (FR-004)
  - checkpoint_starvation_seconds > 60s: max_readers 临时降到 5
  - checkpoint 成功后 30s 恢复原值
  - commit: ____

- [ ] **6.3** 新增 `async_import_service.get_all_tasks()` (FR-005)
  - 返回 `Dict[str, Dict]` 包含 id/status/created_at/error
  - ImportQueueHandler.execute() 不再 AttributeError
  - commit: ____

- [ ] **6.4** 修改 `TransactionContext` 增加长事务检测 (FR-006)
  - `__enter__` 记录 `self._start_time = time.time()`
  - `__exit__` 检查持续时间: >30s WARNING, >120s ERROR + metric
  - commit: ____

- [ ] **6.5** 修改 `async_audit_writer.py` 裸连接统一 (FR-010)
  - 替换 `sqlite3.connect(...)` → `safe_connect_for_write(..., force_no_tx=True)`
  - commit: ____

- [ ] **6.6** 新增 `test_v007_42_wal_monitor.py`
  - test_health_check_checkpoint_busy: 返回 checkpoint_busy 字段
  - test_health_check_reader_health: 返回 reader_health 统计
  - test_checkpoint_starvation_triggers_shrink: 饥饿触发缩容
  - test_checkpoint_recovery_expands_pool: 恢复后扩容
  - commit: ____

- [ ] **6.7** 新增 `test_v007_42_import_fix.py`
  - test_get_all_tasks_empty: 空 tasks
  - test_get_all_tasks_one: 1 条 task
  - test_get_all_tasks_multiple: 多条 tasks
  - test_import_queue_handler_no_error: 不再 AttributeError
  - commit: ____

- [ ] **6.8** 新增 WAL + 长事务 metric (FR-007 剩余)
  - `wal_checkpoint_busy_total`
  - `long_transaction_total`
  - `pool_shrink_total`
  - `pool_expand_total`
  - commit: ____

## Phase 7: 集成验证 + 文档

- [ ] **7.1** 新增 `verify_v007_42.py` ≥17 项验证
  - Test 1: ConnectionConfig.mmap_size 默认 = 0
  - Test 2: _create_connection PRAGMA mmap_size 读取 config
  - Test 3: SQLITE_MMAP_SIZE 环境变量覆盖
  - Test 4: max_readers 默认 = 10
  - Test 5: _execute_via_read_pool max_retries = 3
  - Test 6: Decorrelated Jitter base=200ms, cap=2s
  - Test 7: I/O 限流器存在且可触发
  - Test 8: SQLITE_IO_RATE_LIMIT_DISABLE 逃生口
  - Test 9: health_check 返回 checkpoint_busy
  - Test 10: health_check 返回 reader_health
  - Test 11: AsyncImportService.get_all_tasks() 存在
  - Test 12: TransactionContext 长事务检测 (有 _start_time 字段)
  - Test 13: async_audit_writer 不含裸 sqlite3.connect
  - Test 14: observability 含 10 个新 metric (含 sqlite_version_compliant + heartbeat_check_failed_total)
  - Test 15: verify_v007_41.py 仍 100% 通过
  - Test 16: sqlite_version_guard 检测 < 3.51.3 触发 WARNING (FR-011)
  - Test 17: db_heartbeat 模块存在 + 线程可启停 (FR-012)
  - commit: ____

- [ ] **7.2** verify_v007_41.py 仍 100% 通过
  - commit: ____

- [ ] **7.3** 复制 spec 到 `docs/SPEC_V007.42.md`
  - commit: ____

## 验证阶段

- [ ] **V.1** 单元测试 100% 通过
  - `pytest meta/tests/test_v007_42_read_retry.py`
  - `pytest meta/tests/test_v007_42_wal_monitor.py`
  - `pytest meta/tests/test_v007_42_import_fix.py`
  - 结果: ____

- [ ] **V.2** 集成验证 100% 通过
  - `python verify_v007_42.py`
  - `python verify_v007_41.py` (回归)
  - 结果: ____

- [ ] **V.3** 部署到 release-prep 服务器
  - 监控 24h: disk I/O error 频率变化 + mmap_size=0 读性能
  - 结果: ____

- [ ] **V.4** 部署到 yonaa 生产
  - 灰度 → 全量
  - 监控 1 周: disk I/O error = 0 复发
  - 结果: ____

## 提交规范

每个 Phase 单独 commit，commit message 格式：

```
fix(be): V007.42 P5 - mmap fix + retry upgrade + I/O rate limiter

[V007.42] Phase 5: mmap 修正 + Retry 升级 + I/O 限流
- sql_connection_pool.py: ConnectionConfig.mmap_size=0, I/O 限流器
- sql_adapters.py: Decorrelated Jitter (base=200ms, cap=2s)
- test_v007_42_read_retry.py: 单元测试
- observability.py: 4 个新 metric
```

```
fix(be): V007.42 P6 - WAL monitor + import fix + long-tx guard

[V007.42] Phase 6: WAL 监控 + Import Fix + 长事务防护
- sql_connection_pool.py: health_check 增强 + 动态缩容
- async_import_service.py: get_all_tasks()
- bo_framework.py: TransactionContext 长事务检测
- async_audit_writer.py: 裸连接统一
```

```
fix(be): V007.42 P7 - verify + docs

[V007.42] Phase 7: 集成验证 + 文档
- verify_v007_42.py: 15 项验证
- docs/SPEC_V007.42.md: spec 镜像
```
