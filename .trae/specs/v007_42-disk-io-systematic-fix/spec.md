# Spec: V007.42 Disk I/O 系统性修复 — Retry + I/O 限流 + WAL 监控 + mmap 修正 + Import Fix

## 1. Background & Objectives

### 1.1 Background

V007.41 部署到 yonaa 后，disk I/O error 仍在持续。85 行错误 trace 深度分析揭示：

```
时间分布: 11:30:03 ~ 11:34:29 (4 分钟窗口内 86% 集中在 12 秒内)
并发特征: 11:34:17 单秒 42 次错误, 5 个并发 req_id 同时触发
对象类型: 100% 只读路径, 全部是 relationship 查询 + enrichment
SQLite 环境: Python 3.14.3 + SQLite 3.50.4 (低于 WAL-reset race 修复版本 3.51.3)
SQLite IOERR 实测 retry span: 156~193ms (之前误判为 11ms)
磁盘类型: WAL/SHM 文件正常 (< 0.5MB), checkpoint 状态健康
恢复行为: mark_bad + rebuild 循环, 但无 backpressure/debounce
```

### 1.2 根因分析 (二次确认)

经过代码逐行审阅 + 行业最佳实践研究 + 现场诊断，确认 4 层叠加根因：

| # | 根因 | 证据 | 行业参考 |
|---|------|------|---------|
| R1 | **连接池级 retry 机制缺陷** | `_execute_via_read_pool` 仅 3 次 attempt、backoff 50-100ms 太短、无 Decorrelated Jitter、6 并发 retry 11ms 内全部失败 | AWS 2015 Jitter Paper; SQLite 官方建议 retry 间隔 ≥ 200ms |
| R2 | **WAL checkpoint 饥饿** | PASSIVE 模式在有活跃读者时不截断 WAL；20 个读连接持 mmap 视图阻止 WAL 回收 → WAL 膨胀 → mmap 失效 → disk I/O | SQLite WAL mode doc §3; PRAGMA wal_checkpoint 文档 |
| R3 | **ImportQueueHandler.get_all_tasks() 缺失** | `import_handlers.py:16` 调 `service.get_all_tasks()` 但 `AsyncImportService` 无此方法 → `AttributeError` 每 30s 一次 → 持续错误日志噪音 + 潜在连接泄漏 | 代码审阅确认 |
| R4 | **无全局 I/O 错误感知** | 6 个线程独立 retry，无法感知其他线程已失败 → thundering herd → I/O 子系统过载 | Circuit Breaker pattern (Netflix Hystrix) |

### 1.6 现场诊断关键发现 (第三次研究)

经 3 个并行研究 agent (文献综述 + 现场诊断 + 堆栈完整分析) 补充，发现 4 项关键遗漏：

| # | 新发现 | 数据来源 | 对 V007.42 spec 的影响 |
|---|--------|---------|----------------------|
| D1 | **实测 retry 时间 156~193ms**，原 spec 假设 11ms 严重低估 | 堆栈分析: 3 次 retry 总耗时 span 数据 | FR-001 retry 预算应 ≥ 250ms |
| D2 | **SQLite 版本 3.50.4 < 3.51.3** (存在 WAL-reset race 修复版本) | 现场诊断: `Python 3.14.3 + SQLite 3.50.4` | 新增 FR-011: SQLite 版本基线检查 |
| D3 | **当前 max_readers 实际为 5**（非 spec 假设的 20），但仍是固定值未根据 I/O 抖动动态调整 | 现场诊断: `sql_config.py PoolConfig.max_readers=5` | FR-009 需修正: 5 → 10, 加动态调整机制 |
| D4 | **缺少主动健康检查层**（PRAGMA quick_check 心跳），完全依赖被动 retry | 堆栈分析: 无任何 quick_check 日志 | 新增 FR-012: 主动心跳 + quick_check |

### 1.7 业界真实事故对照

| 案例 | 环境 | 错误码 | 与 yonaa 共性 | V007.42 对策 |
|------|------|--------|------------|------------|
| [OSMC Vero V (2026-06)](https://discourse.osmc.tv/t/recurring-sqlite-errors-causing-application-corruption-on-vero-v/112621) | eMMC + WAL | IOERR_SHORT_READ | WAL 被 truncate → header 读取失败 | 禁用 mmap + 监控 WAL 大小 |
| [RHEL 8.10 SQLite 3.46 + WAL](https://www.sqlite.org/forum/forumpost/f78c41cfdc) | 多线程 + 在线 backup | IOERR_SHORT_READ 522 | 与 yonaa 高度类似 | 避免外部工具触碰 WAL/SHM |
| [Django mmap WAL race (2026-04)](https://blog.bythewood.me/posts/optimizing-sqlite-for-django-in-production/) | mmap + 多进程 | database disk image malformed | mmap 把 race 放大为 corruption | **升级 SQLite ≥ 3.51.3** |
| [Scott Perry on macOS mmap (2024-10)](https://sqlite.org/forum/forumpost/3ce1ee76242cfb29) | mmap 区域 | IOERR_MMAP + SIGBUS | Richard Hipp: "never use mmap" | **禁用 mmap_size=0** |

### 1.3 行业最佳实践二次确认

| 实践 | 本项目适用性 | 确认方式 |
|------|-------------|---------|
| **SQLite busy_timeout (PRAGMA)** | 已在用 (30s)，对 SQLITE_BUSY 有效但对 SQLITE_IOERR 无效 | SQLite 文档: busy_timeout 只处理 SQLITE_BUSY |
| **SQLite busy_handler (C API)** | Python sqlite3 模块不暴露此 API | Python 3.12 sqlite3 源码确认 |
| **Connection pre-ping** | 已部分实现 (`PooledConnection.is_valid()` 执行 `SELECT 1`)，但 retry loop 不使用 | 代码审阅 sql_connection_pool.py:92-124 |
| **Decorrelated Jitter** | 适用: 消除并发 retry 的同步性 | AWS 2015 "Exponential Backoff And Jitter" paper |
| **Circuit Breaker** | 适用: 防止 retry storm 保护 I/O 子系统 | Netflix Hystrix; resilience4j 文档 |
| **WAL 监控指标** | 适用: 检测 checkpoint 饥饿的唯一直接手段 | SQLite PRAGMA wal_checkpoint 返回 (busy, log, checkpointed) |
| **SQLITE_FCNTL_WIN32_AV_RETRY** | 不适用: 仅 Windows C API，yonaa 是 Linux | SQLite VFS 源码 |
| **tenacity 库** | 不引入: 增加外部依赖；retry 逻辑有 SQLite 特殊性 (连接 invalidation)，通用库不覆盖 | 架构原则: 不引入新依赖 (NFR-002) |
| **BEGIN IMMEDIATE** | 已在 WriteQueue 使用；读路径保持 DEFERRED (默认) | WriteQueue._do_begin line 299 已确认 |

### 1.4 与前序版本的关系

```
V007.34 (read retry 基础)              ─┐
V007.38 (journal_mode/auto_vacuum 幂等) ├─ 战术止血
V007.39 (TRUNCATE → PASSIVE)            ─┤
V007.40 (4th check, 默认值修复)          ├─ 战术止血
V007.41 (L0 safe_connect 统一)          ─┘
                                         │
                                         ▼
V007.42 (本 spec)                       ── 系统性修复
```

V007.41 不回滚；V007.42 在 V007.41 基础上叠加 3 个 commit (P5/P6/P7)。

### 1.5 Business Objectives

- **消除 disk I/O error 雪崩**: 通过 I/O 限流 + Decorrelated Jitter 防止 retry storm
- **根治 mmap 导致的 disk I/O**: 禁用 mmap_size (设为 0)，消除 SQLite 官方文档指出的不可恢复 I/O error
- **根治 WAL checkpoint 饥饿**: 监控 WAL 大小，在饥饿时主动释放读连接
- **修复 ImportQueueHandler bug**: 消除每 30s 的 AttributeError 噪音
- **可观测**: WAL/I/O 限流/Retry 全链路 metric
- **零破坏性**: V007.41 已通过的验证必须在 V007.42 仍然 100% 通过

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 生产环境 disk I/O error 导致查询失败，影响用户体验 |
| User/Stakeholder | Yes | SRE 需要可观测性；后端开发需要稳定的 SQLite 层 |
| Solution | Yes | 连接池级 retry + I/O 限流 + WAL 监控 + mmap 修正 |
| Functional | Yes | 新 API: `get_all_tasks()`, WAL metric, I/O 限流状态 |
| Nonfunctional | Yes | Retry 开销 <1%/req; I/O 限流恢复 < 60s |
| External Interface | No | 不暴露新 HTTP 接口 |
| Transition | Yes | V007.41 → V007.42 兼容叠加 |

## 3. Functional Requirements

### FR-001: 连接池级 Retry 机制升级

- **Description**: 升级 `_execute_via_read_pool` 的 retry 逻辑
- **Acceptance Criteria**:
  - 最大重试次数: 保持 3 (SQLITE_IOERR 是 hard error, 更多重试无效; SQLite 官方 + AWS Jitter paper 均不建议超过 3-5 次; CB OPEN 时不再重试直接快速失败)
  - 基础退避: 50ms → 200ms (SQLite 官方建议最小 200ms 间隔)
  - 退避算法: 固定指数 → **Decorrelated Jitter**
    ```python
    # AWS 2015 paper 推荐 (Full Jitter 变体)
    delay = min(cap, random.uniform(base, previous_sleep * 3))
    # cap=2s, base=0.2s, previous_sleep=上次实际 sleep 时间
    ```
  - 每次重试前: (a) 让 reader() 重建坏连接 (已有 mark_error 机制), (b) 如果 CB OPEN 则直接 raise 不重试
  - 重试日志增加 trace_id (已有) + attempt 编号 + 实际 sleep 时间
  - 环境变量 `SQLITE_READ_RETRY_MAX` / `SQLITE_READ_RETRY_BASE_MS` 可覆盖
  - [二次确认修正] AWS paper 推荐 Full Jitter 而非 Decorrelated Jitter 用于数据库场景; 但 Decorrelated Jitter 更适合多客户端竞争 (本项目的 6 并发读场景), 保留 Decorrelated
- **Priority**: Must
- **Source**: R1 (连接池级 retry 机制缺陷) + AWS 2015 Jitter Paper

### FR-002: 读连接池 I/O Health Guard (Circuit Breaker 变体)

- **Description**: 在读连接池层实现 I/O Health Guard，防止 retry storm (thundering herd)

- **设计依据 (二次确认修正)**:

  **[重要] 二次确认后决定: 不实施完整 Circuit Breaker, 改为增强现有连接级熔断 + 全局 I/O 计数器**

  原因:
  1. SQLite 官方明确指出 SQLITE_IOERR 是 hard error, 不是暂时性锁争用
  2. 传统 Circuit Breaker (Netflix Hystrix) 适用于远程服务, 对嵌入式数据库不合适
  3. **现有连接级熔断已足够**: `consecutive_errors >= 3` 时 `reader()` 自动重建坏连接
  4. CB Open 状态会**完全阻止所有读操作**, 对用户体验是灾难性 — 宁可重试后失败, 不要直接拒绝
  5. CB Open → Half-Open → Closed 恢复时瞬间涌入, 可能造成比原始问题更严重的 I/O 压力

  **替代方案: 全局 I/O 错误计数器 + 限流**
  - 新增 `SQLiteConnectionPool._global_io_error_count` (原子计数器)
  - 新增 `SQLiteConnectionPool._global_io_error_window_start` (滑动窗口起始时间)
  - 60 秒内累计 > 10 次 disk I/O error → 限流: 新读请求 sleep 200ms 后再执行 (不拒绝, 只是减速)
  - 限流状态持续到窗口重置 (60s)
  - 这比 CB 更温和: 不阻断请求, 只是减缓并发度, 给 I/O 子系统喘息时间

- **Acceptance Criteria**:
  - `SQLiteConnectionPool` 新增 `_global_io_error_count` + `_global_io_error_window_start` 字段
  - `_execute_via_read_pool` 捕获 disk I/O error 时, 递增全局计数器
  - 全局计数器超过阈值时, 新读请求 sleep 200ms (限流, 不拒绝)
  - 计数器每 60s 重置
  - 环境变量 `SQLITE_IO_RATE_LIMIT_THRESHOLD` / `SQLITE_IO_RATE_LIMIT_WINDOW` 可覆盖
  - 逃生口: `SQLITE_IO_RATE_LIMIT_DISABLE=1` 关闭限流
  - 状态变更记 WARNING 日志 + metric
- **Priority**: Must
- **Source**: R4 (无全局 I/O 错误感知) + Netflix Hystrix pattern

### FR-003: WAL Checkpoint 监控指标

- **Description**: 在连接池中暴露 WAL 大小和 checkpoint 成功率指标
- **二次确认修正**: 精简 — 只加 `checkpoint_busy` 字段 + 读连接健康汇总, 不加 TRUNCATE
- **Acceptance Criteria**:
  - `health_check()` 输出增加:
    - `checkpoint_busy`: `PRAGMA wal_checkpoint(PASSIVE)` 返回的 busy 字段 (>0 表示有读连接持有 WAL 锁)
    - `reader_health`: `{healthy: N, errored: M}` 统计读连接健康状态
  - `checkpoint_busy > 0` 持续 > 300s 记 WARNING (checkpoint 饥饿信号)
  - 新增 metric: `wal_checkpoint_busy_total`, `reader_errored_total`
- **Priority**: Must
- **Source**: R2 (WAL checkpoint 饥饿) + SQLite PRAGMA wal_checkpoint 返回值

### FR-004: WAL 饥饿时主动释放读连接

- **Description**: 当检测到 WAL 饥饿 (checkpoint 连续失败) 时，主动缩小读连接池
- **Acceptance Criteria**:
  - 在 `force_passive_checkpoint()` 失败后，检查 `checkpoint_starvation_seconds`
  - 如果 > 60s: 临时将 `max_readers` 从 20 降到 5 (释放 15 个读连接的 mmap 持有)
  - 释放后重试 PASSIVE checkpoint
  - checkpoint 成功后 30s 恢复 `max_readers` 到原值
  - 缩放操作记 INFO 日志 + metric
- **Priority**: Should
- **Source**: R2 (WAL checkpoint 饥饿) + SQLite WAL mode 文档

### FR-005: 修复 ImportQueueHandler.get_all_tasks()

- **Description**: `AsyncImportService` 新增 `get_all_tasks()` 方法
- **Acceptance Criteria**:
  - 新增 `AsyncImportService.get_all_tasks() -> Dict[str, Dict]`:
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
  - `ImportQueueHandler.execute()` 正常工作，不再 raise AttributeError
  - 单元测试覆盖 `get_all_tasks()` 返回空/1 条/多条
- **Priority**: Must
- **Source**: R3 (ImportQueueHandler.get_all_tasks() 缺失)

### FR-006: 长事务防护

- **Description**: 检测并告警超长事务 (可能阻止 WAL checkpoint)
- **Acceptance Criteria**:
  - `TransactionContext.__enter__` 记录开始时间
  - `TransactionContext.__exit__` 检查事务持续时间
  - 持续 > 30s: WARNING 日志 (含 transaction_id + 持续时间)
  - 持续 > 120s: ERROR 日志 + metric `long_transaction_total`
  - 不强制 rollback (风险太大)，仅告警
- **Priority**: Should
- **Source**: R2 (长事务阻止 WAL 截断) + 生产日志分析

### FR-007: 全链路 Metric 集成

- **Description**: V007.42 新增的所有 metric 汇入 `observability.py`
- **二次确认修正**: 精简 metric 列表, 移除 CB 相关 metric (不实施完整 CB)
- **Acceptance Criteria**:
  - 新增 metric:
    - `read_retry_total`: 读重试总次数
    - `read_retry_success_total`: 重试成功次数
    - `io_rate_limit_triggered_total`: I/O 限流触发次数
    - `wal_checkpoint_busy_total`: checkpoint 忙检测次数
    - `reader_errored_total`: 读连接错误计数
    - `long_transaction_total`: 超长事务检测次数
    - `pool_shrink_total`: 读连接池缩容次数
    - `pool_expand_total`: 读连接池恢复次数
  - 所有 metric 通过 `OBS_COUNTERS` 字典暴露 (与 V007.41 风格一致)
- **Priority**: Should
- **Source**: 可观测性需求

### FR-008: mmap_size 可配置化 + 默认值调整 (P0 关键修改)

- **Description**: 将 mmap_size 从硬编码 64MB 改为可配置, 默认值改为 0 (禁用 mmap)

- **设计依据 (二次确认新增)**:
  这可能是**根治 disk I/O error 的最高 ROI 修改**:
  1. V007.35 引入 mmap_size=256MB 后, 注释明确记录 "写操作让整个 mmap 视图失效, 触发 20 个读连接全部 mark_error → 雪崩"
  2. V007.38 降到 64MB 后仍持续出问题
  3. SQLite 官方文档: "An I/O error on a memory-mapped file cannot be caught and dealt with by SQLite. Instead, the I/O error causes a signal which, if not caught by the application, results in a program crash."
  4. 如果生产环境使用 NFS 或 overlayfs (容器), mmap + WAL 是 SQLite 官方明确不支持的组合
  5. `mmap_size=0` + `cache_size=-2000` 仍提供 2MB 页缓存, 读性能影响有限 (~10-20% 下降)
  6. `db_health_monitor.py` 用裸 `sqlite3.connect` (无 mmap) 能正常读取, 佐证问题出在 mmap 连接

- **Acceptance Criteria**:
  - `ConnectionConfig` 新增 `mmap_size: int = 0` 字段 (默认 0 = 禁用)
  - `_create_connection()` 中 `PRAGMA mmap_size` 从硬编码 67108864 改为读取 config
  - 环境变量 `SQLITE_MMAP_SIZE` 可覆盖 (如需恢复 mmap: `SQLITE_MMAP_SIZE=67108864`)
  - 修改后 verify_v007_41.py PRAGMA mmap_size 断言需更新
  - 日志记录 mmap_size 配置值 (便于生产诊断)
- **Priority**: Must
- **Source**: V007.35→38 mmap 问题历史 + SQLite 官方 mmap 文档 + 研究二次确认

### FR-009: max_readers 默认值调整

- **Description**: 将 max_readers 从 20 降到 10, 与 Flask 实际并发度匹配

- **设计依据 (二次确认新增)**:
  1. Flask + Waitress 通常 8-16 个 worker thread
  2. 20 个线程本地连接 = 20 个 mmap 映射 (如果 mmap_size > 0)
  3. 任何 mmap 失效影响 20 个连接; 降到 10 减少一半影响面
  4. 减少空闲连接数 = 减少连接重建时的 PRAGMA 执行开销

- **Acceptance Criteria**:
  - `ConnectionConfig.max_readers` 默认值从 20 改为 10
  - `sql_adapters.py _connect_pool` 中 `kwargs.get("max_readers", 20)` 改为 `kwargs.get("max_readers", 10)`
  - 环境变量 `SQLITE_MAX_READERS` 可覆盖
- **Priority**: Should
- **Source**: Flask 并发度分析 + 研究二次确认

### FR-010: async_audit_writer 裸连接统一

- **Description**: `async_audit_writer.py:116` 用裸 `sqlite3.connect` 无 mmap_size/cache_size, 与连接池配置不一致

- **Acceptance Criteria**:
  - 改用 `safe_connect_for_write` (V007.41 已建立) + `force_no_tx=True` (审计写入是独立事务)
  - 或改用连接池的 `pool.writer()` (审计写入已经是异步队列, 走写路径更合理)
  - 确保审计写入有 PRAGMA busy_timeout + mmap_size (统一配置)
- **Priority**: Should
- **Source**: 研究二次确认 — 生产审计写入路径配置不一致

### FR-011: SQLite 版本基线检查 (D2 新增)

- **Description**: 检测并记录 SQLite 版本，低于 3.51.3 时发出 WARNING (WAL-reset race 风险)
- **设计依据**:
  - yonaa 当前 `Python 3.14.3 + SQLite 3.50.4`，低于 WAL-reset race 修复版本
  - SQLite 3.51.3 (2026-03-13 发布) 修复了多进程写场景下 WAL-reset race
  - mmap 会把 WAL race 放大为结构性 corruption (Django 案例)
- **Acceptance Criteria**:
  - 应用启动时检测 `sqlite3.sqlite_version`
  - < 3.51.3 时记 WARNING 日志: `[V007.42] SQLite 3.50.4 < 3.51.3, WAL-reset race risk`
  - 新增 metric `sqlite_version_compliant: 0/1`
  - 不阻断启动 (环境升级可能不在控制范围内)
  - 提供 `SQLITE_REQUIRE_MIN_VERSION` 环境变量可强制 raise
- **Priority**: Should
- **Source**: 现场诊断 (D2) + SQLite 论坛 Django 案例 + SQLite Forum 3.51.3 changelog

### FR-012: 主动健康检查心跳 (D4 新增)

- **Description**: 后台线程每 30s 执行 `PRAGMA quick_check`，失败时主动告警 + 重建连接
- **设计依据**:
  - 当前完全依赖被动 retry (V007.16 mark_bad + V007.34 retry)
  - 缺主动预防层，无法在用户请求触发前发现问题
  - 堆栈分析中无任何 quick_check 日志佐证
- **Acceptance Criteria**:
  - 新增 `meta/core/db_heartbeat.py` 模块
  - 后台 daemon 线程，每 30s 调用 `PRAGMA quick_check` (单连接)
  - 失败时: WARNING 日志 + 触发连接重建 + metric `heartbeat_check_failed_total`
  - 连续 3 次失败触发 WARNING 升级为 ERROR
  - 环境变量 `SQLITE_HEARTBEAT_INTERVAL` / `SQLITE_HEARTBEAT_DISABLE` 可调
- **Priority**: Should
- **Source**: 现场诊断 (D4) + 主动监控原则

## 4. Non-Functional Requirements

### NFR-001: Retry 性能开销 <1%/request

- 正常请求 (无 disk I/O): I/O 限流检查 < 0.1ms (1 个 bool 比较)
- 重试场景: 3 次 attempt 总耗时 < 5s (Decorrelated Jitter cap=2s)
- `health_check()` 调用: < 5ms (1 次 PRAGMA + 统计)

### NFR-002: 零破坏性

- V007.41 已通过的验证在 V007.42 必须仍然 100% 通过
- 不引入新的外部依赖包
- I/O 限流默认启用，但 `SQLITE_IO_RATE_LIMIT_DISABLE=1` 可立即关闭
- mmap_size=0 默认启用，但 `SQLITE_MMAP_SIZE=67108864` 可恢复原值

### NFR-003: 可降级

- I/O 限流器探测失败时不影响业务 (降级为不限制流)
- WAL stats 获取失败时降级为空 dict + log
- metric 写入失败时降级为 log (与 V007.41 safe_connect 一致)

### NFR-004: 向后兼容

- `SQLiteConnectionPool` 新增方法不破坏现有调用方
- `AsyncImportService.get_all_tasks()` 是新增方法，不影响现有 API
- `_execute_via_read_pool` 内部逻辑变更，外部签名不变

## 5. Module Design

### 5.1 新增模块

| 文件 | 职责 | 行数预估 |
|---|---|---|
| `meta/tests/test_v007_42_read_retry.py` | Retry 升级 + Decorrelated Jitter 测试 | ~120 |
| `meta/tests/test_v007_42_wal_monitor.py` | WAL 监控 + 读连接健康测试 | ~100 |
| `meta/tests/test_v007_42_import_fix.py` | Import fix 测试 | ~80 |
| `meta/tests/test_v007_42_heartbeat.py` | 心跳线程 + 版本守卫测试 | ~80 |
| `meta/core/sqlite_version_guard.py` | SQLite 版本基线检查 (FR-011) | ~60 |
| `meta/core/db_heartbeat.py` | 后台心跳线程 (FR-012) | ~100 |
| `verify_v007_42.py` | 集成验证 (≥17 项) | ~280 |

### 5.2 修改模块

| 文件 | 修改内容 |
|---|---|
| `meta/core/sql_adapters.py` | `_execute_via_read_pool` retry 升级: Decorrelated Jitter + I/O 限流 |
| `meta/core/sql_connection_pool.py` | `ConnectionConfig` 增加 mmap_size + max_readers 调整 + health_check 增强 + I/O 限流 |
| `meta/services/async_import_service.py` | 新增 `get_all_tasks()` 方法 |
| `meta/core/bo_framework.py` | `TransactionContext` 增加长事务检测 |
| `meta/services/async_audit_writer.py` | 裸连接统一到 safe_connect_for_write |
| `meta/core/observability.py` | 新增 10 个 metric (原 8 + sqlite_version_compliant + heartbeat_check_failed_total) |
| **新增** `meta/core/sqlite_version_guard.py` | SQLite 版本基线检查 (FR-011) |
| **新增** `meta/core/db_heartbeat.py` | 后台心跳线程 + quick_check (FR-012) |
| **新增** `meta/tests/test_v007_42_heartbeat.py` | 心跳单元测试 (FR-012) |

### 5.3 I/O 限流器设计 (替代完整 Circuit Breaker)

```python
# 在 sql_connection_pool.py SQLiteConnectionPool 中
import threading

class SQLiteConnectionPool:
    def __init__(self, ...):
        ...
        # [V007.42] I/O 限流: 防止 thundering herd
        self._io_error_count = 0
        self._io_error_window_start = time.time()
        self._io_rate_limit_active = False
        self._io_error_lock = threading.Lock()

    def _record_io_error(self):
        """记录一次 disk I/O error, 检查是否需要限流"""
        with self._io_error_lock:
            now = time.time()
            window = float(os.environ.get('SQLITE_IO_RATE_LIMIT_WINDOW', '60'))
            if now - self._io_error_window_start > window:
                self._io_error_count = 0
                self._io_error_window_start = now
                self._io_rate_limit_active = False
            self._io_error_count += 1
            threshold = int(os.environ.get('SQLITE_IO_RATE_LIMIT_THRESHOLD', '10'))
            if self._io_error_count >= threshold and not self._io_rate_limit_active:
                self._io_rate_limit_active = True
                logger.warning(
                    "[V007.42] I/O rate limit activated: %d errors in %.0fs window",
                    self._io_error_count, now - self._io_error_window_start
                )

    def _check_io_rate_limit(self):
        """检查是否需要限流, 如果需要则 sleep 200ms"""
        if os.environ.get('SQLITE_IO_RATE_LIMIT_DISABLE', '').lower() in ('1', 'true'):
            return
        if self._io_rate_limit_active:
            time.sleep(0.2)  # 减速, 不拒绝
```

### 5.4 Decorrelated Jitter 算法

```python
# 在 sql_adapters.py _execute_via_read_pool 中
import random

_RETRY_CAP = 2.0       # 最大延迟 2s
_RETRY_BASE = 0.2      # 基础延迟 200ms
_MAX_RETRIES = 3       # SQLITE_IOERR 是 hard error, >3 次无效

def _decorrelated_jitter_sleep(previous_sleep: float) -> float:
    """AWS 2015: sleep = min(cap, random(base, sleep * 3))"""
    delay = min(_RETRY_CAP, random.uniform(_RETRY_BASE, previous_sleep * 3))
    time.sleep(delay)
    return delay
```

## 6. Migration Plan

### Phase 5: mmap 修正 + Retry 升级 + I/O 限流 (1 commit)

| Task | Owner | 验收 |
|---|---|---|
| 5.1 修改 `sql_connection_pool.py:ConnectionConfig` 增加 `mmap_size` 字段 (FR-008) | dev-agent | 默认值 0，`_create_connection` 读取 config |
| 5.2 修改 `sql_connection_pool.py` `_create_connection` PRAGMA mmap_size 可配置 (FR-008) | dev-agent | `PRAGMA mmap_size = {config.mmap_size}` |
| 5.3 修改 `sql_connection_pool.py` 增加 I/O 限流器 (FR-002) | dev-agent | `_record_io_error` + `_check_io_rate_limit` |
| 5.4 修改 `sql_adapters.py:_execute_via_read_pool` retry 升级 (FR-001) | dev-agent | 3 attempts + Decorrelated Jitter + I/O 限流 |
| 5.5 修改 `sql_adapters.py` `_connect_pool` max_readers 默认值 20→10 (FR-009) | dev-agent | `kwargs.get("max_readers", 10)` |
| 5.6 新增 `test_v007_42_read_retry.py` | dev-agent | 3 attempts + jitter + 限流 + mmap=0 |
| 5.7 新增 metric 到 `observability.py` (FR-007 部分) | dev-agent | read_retry_total 等 |
| **5.8** 新增 `meta/core/sqlite_version_guard.py` (FR-011) | dev-agent | 启动检测 + WARNING + metric |
| **5.9** 新增 `meta/core/db_heartbeat.py` (FR-012) | dev-agent | 后台心跳线程 + quick_check |

### Phase 6: WAL 监控 + Import Fix + 长事务防护 (1 commit)

| Task | Owner | 验收 |
|---|---|---|
| 6.1 修改 `sql_connection_pool.py` health_check 增强 (FR-003) | dev-agent | checkpoint_busy + reader_health |
| 6.2 修改 `sql_connection_pool.py` 动态 max_readers (FR-004) | dev-agent | 饥饿时缩容 |
| 6.3 修改 `async_import_service.py` 新增 `get_all_tasks()` (FR-005) | dev-agent | ImportQueueHandler 不再 AttributeError |
| 6.4 修改 `bo_framework.py:TransactionContext` 增加长事务检测 (FR-006) | dev-agent | >30s WARNING, >120s ERROR |
| 6.5 修改 `async_audit_writer.py` 裸连接统一 (FR-010) | dev-agent | 使用 safe_connect_for_write |
| 6.6 新增 `test_v007_42_wal_monitor.py` | dev-agent | WAL 指标测试 |
| 6.7 新增 `test_v007_42_import_fix.py` | dev-agent | get_all_tasks() 测试 |
| 6.8 新增 WAL + 长事务 metric (FR-007 剩余) | dev-agent | wal_checkpoint_busy_total 等 |

### Phase 7: 集成验证 + 文档 (1 commit)

| Task | Owner | 验收 |
|---|---|---|
| 7.1 新增 `verify_v007_42.py` | dev-agent | ≥15 项验证 100% 通过 |
| 7.2 verify_v007_41.py 仍 100% 通过 | dev-agent | 零破坏性 |
| 7.3 复制本 spec 到 `docs/SPEC_V007.42.md` | dev-agent | 文件存在 |
| 7.4 生产环境 mmap_size=0 观察 | PM/SRE | 部署后 disk I/O error 频率变化 |

## 7. Risk Assessment

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| mmap_size=0 导致读性能下降 | 中 | 中 | `cache_size=-2000` 仍提供 2MB 页缓存; 预估降 10-20%; `SQLITE_MMAP_SIZE` 环境变量可立即恢复 |
| I/O 限流器误触发 (短暂波动触发限流) | 低 | 低 | 10 次/60s 阈值较高; 限流只是 sleep 200ms 不拒绝; `SQLITE_IO_RATE_LIMIT_DISABLE=1` 逃生口 |
| WAL 缩容影响并发读性能 | 低 | 中 | 仅在饥饿时缩容; 缩容后 30s 恢复; 缩容操作 INFO 日志 |
| Decorrelated Jitter 导致 retry 时间不可预测 | 低 | 低 | cap=2s 保底; 日志记录每次 sleep 时间 |
| TransactionContext 长事务检测影响性能 | 极低 | 极低 | 仅在 __exit__ 时做 1 次 time.time() 比较 |
| max_readers 10 不够用 (高并发场景) | 低 | 中 | Flask 8-16 worker 下 10 足够; `SQLITE_MAX_READERS` 环境变量可调高 |
| async_audit_writer 迁移到 safe_connect 风格变更 | 低 | 低 | 审计写入是异步队列, 失败可容忍; 保留 force_no_tx=True |

## 8. Acceptance Criteria

- [ ] FR-001~012 全部实现
- [ ] NFR-001~004 全部满足
- [ ] verify_v007_41.py 仍 100% 通过
- [ ] verify_v007_42.py ≥15 项 100% 通过
- [ ] test_v007_42_read_retry.py 验证 3 attempts + Decorrelated Jitter
- [ ] test_v007_42_import_fix.py 验证 get_all_tasks() 返回正确
- [ ] test_v007_42_wal_monitor.py 验证 health_check 返回 checkpoint_busy + reader_health
- [ ] `ConnectionConfig.mmap_size` 默认 = 0, `_create_connection` 读取 config
- [ ] I/O 限流器: 60s 窗口 10 次触发限流, 不拒绝只减速
- [ ] `async_import_service.get_all_tasks()` 返回正确, ImportQueueHandler 不再 AttributeError
- [ ] `TransactionContext` 长事务 >30s WARNING, >120s ERROR
- [ ] `async_audit_writer` 使用 safe_connect_for_write 而非裸 sqlite3.connect
- [ ] **FR-011**: 应用启动时检测 SQLite 版本，< 3.51.3 触发 WARNING + metric
- [ ] **FR-012**: 后台心跳每 30s `PRAGMA quick_check`，失败触发连接重建
- [ ] **D1 修正**: 3 次 retry 总预算 ≥ 250ms（实测 156~193ms）
- [ ] **D3 修正**: max_readers 默认 10 (原 5 → 10)
- [ ] docs/SPEC_V007.42.md 镜像同步
- [ ] 部署后监控: disk I/O error 频率下降 ≥80%

## 9. Out of Scope

- PostgreSQL 迁移 → 独立 spec
- L1 WriteQueue 重构 → V007.43+ 候选 (当前 PASSIVE + force_passive_checkpoint 已基本够用)
- L2 SQLDataSource 抽象改造 → 不动
- 监控/告警系统建设 → 运维 agent 负责
- mmap_size 进一步调优 → 需要更多生产数据
- SQLite VFS 自定义 (SQLITE_FCNTL_WIN32_AV_RETRY 等) → 需要 C 扩展
- SQLite 版本升级 (3.50.4 → 3.51.3+) → 运维/基础设施 agent 负责 (FR-011 仅检测告警, 不升级)
- NFS / overlayfs 存储迁移 → 基础设施层面, 不在本 spec 范围
- SQLITE_IOERR 子码区分处理 (Python sqlite3 绑定层限制) → V007.43+ 候选

## 10. References

### SQLite 官方文档
- Result and Error Codes: https://www.sqlite.org/rescode.html
- Extended Result Codes (IOERR_* 子码全表): https://www.sqlite.org/c3ref/c_abort_rollback.html
- WAL mode: https://www.sqlite.org/wal.html
- PRAGMA wal_checkpoint: https://www.sqlite.org/pragma.html#pragma_wal_checkpoint
- Memory-Mapped I/O: https://www.sqlite.org/mmap.html
- How To Corrupt An SQLite Database File: https://www.sqlite.org/howtocorrupt.html
- File Locking And Concurrency: https://www.sqlite.org/lockingv3.html

### SQLite Forum 真实案例
- [RHEL 8.10 SQLite 3.46 + WAL IOERR_SHORT_READ](https://www.sqlite.org/forum/forumpost/f78c41cfdc)
- [WAL checkpoint fsync 失败分析](https://www.sqlite.org/forum/forumpost/59681c40ce)
- [Scott Perry: mmap 在 macOS 崩溃 1000+ 次](https://sqlite.org/forum/forumpost/3ce1ee76242cfb29)
- [76GB 数据库 .recover 恢复](https://www.sqlite.org/forum/forumpost/6084da204166b238)

### 业界最佳实践
- AWS 2015 "Exponential Backoff And Jitter": https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Python sqlite3 文档: https://docs.python.org/3/library/sqlite3.html
- [Django + SQLite mmap WAL race 案例](https://blog.bythewood.me/posts/optimizing-sqlite-for-django-in-production/)
- Netflix Hystrix Circuit Breaker: https://github.com/Netflix/Hystrix/wiki/How-it-Works

### 项目内部文档
- V007.41 spec: `.trae/specs/v007_41-l0-safe-connect/spec.md`
- V007.41 HANDOFF: `docs/HANDOFF_V007_41_DISK_IO_STILL.md`
- yonaa disk I/O error log: `D:\filework\yonaa_disk_io_full.txt`
- sql_config.py: `meta/core/sql_config.py`
- 现场诊断报告: `D:\filework\diagnostic_report_20260708.md`
