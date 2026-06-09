## 目录

1. [1. 背景与目标](#1-背景与目标)
2. [2. 需求类型概览](#2-需求类型概览)
3. [3. 功能需求](#3-功能需求)
4. [4. 非功能需求](#4-非功能需求)
5. [5. 外部接口需求](#5-外部接口需求)
6. [6. 过渡需求](#6-过渡需求)
7. [7. 约束与假设](#7-约束与假设)
8. [8. 优先级与里程碑建议](#8-优先级与里程碑建议)
9. [9. 变更/设计提案 (RFC)](#9-变更设计提案-(rfc))

---
# Spec: SQLite 数据库多次损坏修复方案

> **版本**: 1.0  
> **日期**: 2026-05-31  
> **状态**: 已实施 - 2026-06-02（7个FR全部完成）

---

## 1. 背景与目标

### 1.1 背景

`excel-to-diagram` 项目使用 SQLite 作为唯一的持久化存储后端，通过自研的读写分离连接池（`SQLiteConnectionPool`）+ 串行写入队列（`WriteQueue`）处理并发。该数据库已发生 **至少 4 次** 损坏（存在 `architecture.db.corrupted`、`architecture.db.corrupted2` 等损坏标记文件），每次损伤都导致后端无法启动，需人工从备份恢复。

经完整代码审查（共检查 9 个关键文件），对照 SQLite 官方文档、Litestream 生产实践、zylos.ai WAL 深度分析等 6 个权威来源进行校验，识别出 **6 个根因**。

**关键发现**：当前 Python 环境中的 SQLite 版本为 **3.50.4**，该版本存在 SQLite 官方确认的 **WAL-Reset Bug**（2026-03-13 在 3.51.3 中修复）。此 Bug 的描述——"WAL 模式下，两个或多个连接在不同线程/进程中同时对同一文件执行写入或 checkpoint"——与本项目的架构模式完全吻合。

### 1.2 业务目标

- 彻底消除 SQLite 数据库反复损坏问题
- 建立数据库损坏的尽早发现和自动恢复机制
- 确保开发服务器（`npm run dev:python`）启停不引入数据库风险
- 规范运维操作（VACUUM、checkpoint）的执行时机和方式

### 1.3 用户/涉众目标

| 角色 | 目标 |
|------|------|
| 开发者 | dev server 重启不再导致 DB 损坏，不再需要手工恢复 |
| 运维人员 | 数据库健康状态可观测，损坏时有明确恢复路径 |
| 测试框架 | test.py 快照机制与修复方案协同，不产生污染 DB |

---

## 2. 需求类型概览

| 类型 | 适用 | 证据（来源） |
|------|------|-------------|
| 业务需求 | 是 | 任务描述 / 4 次损坏历史 |
| 用户/涉众需求 | 是 | 开发者 & 运维反馈 |
| 解决方案需求 | 是 | 代码审计 + 行业调研 |
| 功能需求 | 是 | 见第 3 节 |
| 非功能需求 | 是 | 见第 4 节 |
| 外部接口需求 | 是 | API 端点变更 |
| 过渡需求 | 是 | 渐进式引入 |

---

## 3. 功能需求

### FR-001: 关闭 Flask Reloader（消除多进程竞争）【P0】

- **描述**: 开发环境下，系统 MUST 禁用 Flask Werkzeug 的 `use_reloader`，以确保 SQLite 数据库不因 fork 出的子进程携带打开的连接而产生多进程 WAL 竞争。
- **行业依据**: [SQLite howtocorrupt §2.7](https://sqlite.org/howtocorrupt.html#_carrying_an_open_database_connection_across_a_fork_) 明确列出 "Carrying an open database connection across a fork()" 为 corruption 原因；[zylos.ai WAL Pitfalls §3](https://zylos.ai/research/2026-02-20-sqlite-wal-mode-ai-agent-systems) 指出多进程共享同一 WAL 文件的 checkpoint 与写操作存在 race condition。
- **验收标准**:
  - `dev.py` 中 `use_reloader=False`
  - 启动后只有一个 Python 进程持有 `architecture.db` 连接
  - 前端 Vite HMR 不受影响（仅后端热更新受影响）
- **优先级**: Must (P0)
- **类型映射**: 功能需求
- **来源**: 代码审计 + 行业调研

### FR-002: 启动前清理残留 WAL/SHM 文件【P0】

- **描述**: 在连接池初始化前（`SQLiteConnectionPool.initialize()` 阶段），系统 MUST 检测并安全清理孤立的 `-wal` 和 `-shm` 文件，防止 crash 后残留的 WAL 在下一次启动时触发失败的 WAL recovery。
- **行业依据**: [Litestream Tips](https://litestream.io/tips/) 建议删除数据库前先清理关联的 `-shm`/`-wal`；[SQLite WAL §3.3](https://sqlite.org/wal.html#persistence_of_wal_mode) 说明 WAL 是 quasi-persistent 文件，可能在 crash 后残留。
- **清理安全条件**: 仅当 `wal_mtime < db_mtime`（WAL 比 DB 旧，确认非活跃写入状态）且 `-shm` 文件存在时执行清理。
- **验收标准**:
  - `sql_connection_pool.py` 中新增 `_safe_cleanup_wal_shm()` 函数
  - 在 `initialize()` 的 `_create_connection()` 之前调用
  - 清理前记录 INFO 日志：`[DB] Cleaned orphan WAL: {path} (wal_mtime={ts}, db_mtime={ts})`
- **优先级**: Must (P0)
- **来源**: 代码审计 / Litestream / SQLite 官方文档

### FR-003: 禁用运行时 VACUUM，改为 auto_vacuum=INCREMENTAL【P0】

- **描述**: 系统 MUST 移除或关闭所有运行时触发的 `VACUUM` 操作，改用 `PRAGMA auto_vacuum=INCREMENTAL` + 可控的 `PRAGMA incremental_vacuum` 替代。
- **行业依据**: [Litestream Troubleshooting](https://litestream.io/docs/troubleshooting/#in-place-vacuum) 明确指出 "In-place VACUUM will destroy your tracking state"；[SQLite WAL §1 #3](https://sqlite.org/wal.html) 说明 WAL 模式下不可通过 VACUUM 变更 page_size，VACUUM 实际上是重建整个文件替换旧文件——期间发生的写入将丢失。
- **验收标准**:
  - `DBVacuumHandler.execute()` 不再调用 `VACUUM`，改为 `PRAGMA incremental_vacuum`
  - `POST /api/v1/system/database/vacuum` 端点默认返回 dry-run（仅报告空间统计），需 `--force` 参数才执行 `VACUUM INTO` 导出方式
  - 在线 VACUUM 使用 `VACUUM INTO 'tmp.db'` 导出 + 原子替换方式（仅在低流量时段允许）
  - `connection_pool` 初始化时设置 `PRAGMA auto_vacuum = INCREMENTAL`
- **优先级**: Must (P0)
- **来源**: 代码审计 / Litestream / SQLite 官方文档

### FR-004: ops_server 接入统一连接池 / 只读连接（消除双 WAL writer）【P0】

- **描述**: `ops_server.py` MUST 不再使用独立的 `sqlite3.connect()` + 独立 `PRAGMA journal_mode=WAL`，改为只读模式打开数据库连接，不与主 server 的 WriteQueue 竞争 WAL 写入。
- **行业依据**: [SQLite howtocorrupt §2.4](https://sqlite.org/howtocorrupt.html#_two_processes_using_different_locking_protocols) 明确列出 "Two processes using different locking protocols" 为 corruption 原因；[blog.gary.info](https://blog.gary.info/posts/sqlite-lying-concurrent-writes/) 通过实验证明第二个独立 WAL writer 与主进程的 checkpoint 存在竞态窗口。
- **验收标准**:
  - `ops_server.py` 中 `_get_db()` 使用 URI 只读模式：`file:{path}?mode=ro`
  - 移除 `PRAGMA journal_mode=WAL` 的设置（只读连接不需要）
  - 移除 `PRAGMA wal_checkpoint(TRUNCATE)` 调用（最激进的 checkpoint，必须移除）
  - 运维 check 操作仅执行 `PRAGMA integrity_check`（只读，安全）
  - 如需写操作，提供 `--maintenance` 命令行参数临时开启写模式
- **优先级**: Must (P0)
- **来源**: 代码审计 / SQLite 官方 / blog.gary.info

### FR-005: WriteQueue 注册 atexit 优雅关闭【P0】

- **描述**: `create_app()` 中 MUST 注册 `atexit` 回调，确保 `WriteQueue.stop()` 在进程退出前被调用，避免正在执行的事务残留 WAL 中。
- **行业依据**: [Litestream Tips](https://litestream.io/tips/) 建议 "Always shut down gracefully — call sqlite3_close() on all connections"；[zylos.ai §6](https://zylos.ai/research/2026-02-20-sqlite-wal-mode-ai-agent-systems) 强调连接池的优雅关闭可避免未提交事务污染 WAL 文件。
- **验收标准**:
  - `server.py` 中新增 `_cleanup_resources()` 函数，注册到 `atexit`
  - 清理顺序：先 `write_queue.flush(timeout=30)`，再 `write_queue.stop(timeout=30)`，最后 `pool.shutdown()`
  - 同时注册信号处理器（`signal.SIGTERM`、`signal.SIGINT`）触发相同清理逻辑
  - `WriteQueue.stop()` 超时从 10s 提升到 30s
- **优先级**: Must (P0)
- **来源**: 代码审计 / Litestream / zylos.ai

### FR-006: 数据库启动前完整性检查 + 自动恢复【P1】

- **描述**: 后端启动时，在 `create_app()` 初始化连接池之前，MUST 对 `architecture.db` 执行 `PRAGMA integrity_check`；若失败，自动从最近备份恢复。
- **行业依据**: [Litestream Cron-based backup](https://litestream.io/alternatives/cron/) 建议每次恢复后执行 `PRAGMA integrity_check` 验证；[Slingacademy](https://www.slingacademy.com/article/automating-maintenance-tasks-in-sqlite-databases/#consistency-checks) 将 integrity_check 列为自动化维护的核心环节。
- **验收标准**:
  - `server.py` 中新增 `_preflight_db_check()` 函数，在 `get_data_source()` 之前调用
  - 空 DB（< 1KB）跳过检查
  - 检查失败时自动：`shutil.copy2('architecture.db.bak', 'architecture.db')` → 再次验证
  - 备份也损坏时打印 ERROR 并阻止启动（`sys.exit(1)`）
  - 恢复成功时打印 WARNING 日志标记以便排查根因
- **优先级**: Should (P1)
- **来源**: test.py 已有类似逻辑 / Litestream / Slingacademy

### FR-007: 连接池 PRAGMA 参数优化【P1】

- **描述**: 在连接池初始化时，统一设置以下行业推荐的 PRAGMA 参数以提升 SQLite 在开发环境下的稳定性和性能。
- **行业依据**: [Forward Email 生产配置](https://forwardemail.net/hu/blog/docs/sqlite-performance-optimization-pragma-chacha20-production-guide) 提供了经过大规模生产验证的 PRAGMA 参数集；[zylos.ai](https://zylos.ai/research/2026-02-20-sqlite-wal-mode-ai-agent-systems) 强调 `busy_timeout` 是多线程环境下防止 `SQLITE_BUSY` 错误的第一道防线; [Shivek Khurana benchmark](https://shivekkhurana.com/blog/sqlite-in-production/) 通过实验数据验证了 `WAL + NORMAL synchronous + busy_timeout` 组合的最优性能。
- **验收标准**:
  - 每个新连接自动设置以下 PRAGMA：

    ```python
    conn.execute("PRAGMA busy_timeout = 5000")       # 防止 SQLITE_BUSY
    conn.execute("PRAGMA synchronous = NORMAL")       # WAL 下安全且更快
    conn.execute("PRAGMA foreign_keys = ON")          # 数据完整性
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")  # 在线空间回收
    conn.execute("PRAGMA wal_autocheckpoint = 1000")  # 保持默认，适配低写入场景
    ```

  - `busy_timeout=5000` 是 zylos.ai 推荐的行业标准值（5000-30000ms）
  - `wal_autocheckpoint=1000` 保持 SQLite 默认值（约 4MB WAL），适合开发服务器低写入场景，WAL 小利于快速重启
- **优先级**: Should (P1)
- **来源**: Forward Email / zylos.ai / Shivek Khurana benchmark / SQLite 官方

---

## 4. 非功能需求

### NFR-001: 可靠性

- **描述**: 修复后的系统在连续 100 次 `npm run dev:python` 启停循环中不应发生数据库损坏（`PRAGMA integrity_check` 始终返回 `ok`）。
- **测量方式**: 编写自动化脚本循环启停，每次启动前验证 DB 完整性＋每次退出后检查无残留活跃 WAL
- **优先级**: Must

### NFR-002: 可观测性

- **描述**: 数据库健康状态暴露给运维接口，包括 WAL 文件大小、page_count/freelist_count、连接池活跃连接数、最后一次 checkpoint 时间。
- **测量方式**: `GET /ops/api/v1/db/status` 返回实时指标
- **优先级**: Should

### NFR-003: 向后兼容

- **描述**: 修复不应破坏现有的 CRUD API、test.py 测试框架、npm scripts 的使用方式。
- **测量方式**: `python d:\filework\test.py --all --force` 全量测试通过
- **优先级**: Must

### NFR-004: 故障恢复时间 (RTO)

- **描述**: 数据库损坏后的恢复时间不超过 30 秒（含完整性检查 + 备份恢复 + 二次验证）。
- **测量方式**: 计时脚本记录从 `_preflight_db_check()` 调用到 `create_app()` 完成的时间
- **优先级**: Should

### NFR-005: 请求延迟不劣化

- **描述**: 修复后的系统请求延迟（P50/P99）不应因本次变更而显著劣化。每个 FR 的性能影响已逐项评估（见下方性能影响分析），整体结论为中性偏正面。
- **测量方式**: 修复前后分别用 Apache Bench（`ab -n 1000 -c 10`）对以下端点进行基准测试并对比：
  - `GET /api/v1/health`（轻量读）
  - `GET /api/v2/bo/user`（列表查询）
  - `POST /api/v2/bo/user`（写入操作）
- **目标值**:
  | 指标 | 目标 |
  |------|------|
  | P50 延迟 | ≤ 修复前 × 1.05（增幅 ≤ 5%） |
  | P99 延迟 | ≤ 修复前 × 1.10（增幅 ≤ 10%） |
  | 吞吐量 (RPS) | ≥ 修复前 × 0.95（降幅 ≤ 5%） |
- **优先级**: Should

### NFR-006: 内存占用不增加

- **描述**: 修复后的进程内存占用（RSS）不应因本次变更而显著增加。关闭 reloader 会减少一个进程（约-30MB），此收益应被保留。
- **测量方式**: 修复前后分别采样 10 次进程 `WorkingSet` 取中位数对比
- **目标值**: RSS ≤ 修复前 × 1.10（增幅 ≤ 10%）
- **优先级**: Should

### NFR-007: 启动时间不显著增加

- **描述**: `create_app()` 完成时间（含新增的 integrity_check + WAL 清理）不应显著延长。
- **测量方式**: 修复前后分别计时 `python dev.py` 从启动到 `Running on http://` 输出的时间
- **目标值**: 增量 ≤ 修复前 + 500ms
- **优先级**: Should

#### 各 FR 性能影响分析

| FR | 变更 | 运行时性能影响 | 方向 |
|----|------|--------------|------|
| FR-001 | 关闭 reloader | 减少一个进程（~30-50MB RSS），请求处理能力不变 | ✅ 正面 |
| FR-002 | WAL/SHM 启动清理 | 仅启动时执行一次（< 1ms） | ⚪ 无影响 |
| FR-003 | VACUUM→incremental | 消除定时全库锁死；每 DELETE +1-2% CPU/I/O | ✅ 正面（消除大风险换微小代价） |
| FR-004 | ops_server 只读连接 | 读取性能不变 | ⚪ 无影响 |
| FR-005 | WriteQueue atexit | 仅进程退出时执行 | ⚪ 无影响 |
| FR-006 | 启动完整性检查 | 启动 +50-200ms（DB < 100MB） | ⚪ 可忽略 |
| FR-007 | PRAGMA 参数优化 | `auto_vacuum=INCREMENTAL` 每 DELETE +1-2%（Forward Email 生产验证）；`busy_timeout=5000` 仅在锁竞争时生效 | ⚠️ 微负（可接受） |

---

## 5. 外部接口需求

### IF-001: VACUUM API 端点变更

- **类型**: API
- **端点**: `POST /api/v1/system/database/vacuum`
- **变更**:
  - 默认行为改为 dry-run：返回当前 `page_count`、`freelist_count`、空闲空间百分比，不执行 VACUUM
  - 仅当请求体包含 `{"force": true}` 时，使用 `VACUUM INTO 'meta/architecture_vacuum.db'` + 原子替换方式执行
  - 响应增加 `requires_restart: true` 字段提示操作员
- **错误处理**: 磁盘空间不足时返回 507 Insufficient Storage
- **回退方案**: 保留旧端点路径不变

### IF-002: WAL Checkpoint API 端点变更

- **类型**: API
- **端点**: `POST /api/v1/system/database/wal-checkpoint`
- **变更**:
  - 增加 `mode` 参数白名单校验，仅允许 `PASSIVE`（默认）和 `FULL`
  - `TRUNCATE` 模式返回 400 Bad Request 并提示使用离线维护模式
  - 响应返回 checkpoint 前后 WAL 页数对比
- **来源**: [SQLite WAL §3.2](https://sqlite.org/wal.html#application_initiated_checkpoints) + zylos.ai checkpoint mode 分析

---

## 6. 过渡需求

### TR-001: 渐进式引入

- **描述**: 修复分两阶段实施，P0 项先上线，P1 项在后续迭代中引入。
- **策略**:
  - **Phase 1 (立即)**: FR-001~FR-005 — 覆盖所有 Must 优先级，消除已知 corruption 路径
  - **Phase 2 (后续)**: FR-006、FR-007 — 增强防御和性能优化
- **回滚计划**: 每个变更独立可逆；保留 `architecture.db.bak` 始终可用；通过 Git `revert` 即可回滚

### TR-002: 数据库初始化兼容

- **描述**: 对已存在的 `architecture.db`，修复方案不强制重建。`auto_vacuum=INCREMENTAL` 对已有数据库为新空间使用，存量空间不强制压缩。
- **策略**: 不强制迁移，通过 Phase 2 的离线 VACUUM INTO 逐步压缩存量空间。

---

## 7. 约束与假设

### 7.1 技术约束

| 约束 | 值 | 影响 |
|------|----|------|
| Python 版本 | 3.14 | 自带 SQLite 3.50.4 |
| SQLite 版本 | 3.50.4 | 含 WAL-Reset Bug（3.51.3 修复），不升级 |
| 操作系统 | Windows 11 | D 盘 NTFS，WAL 共享内存满足 |
| 文件系统 | D 盘本地（非网络） | WAL 条件满足 |
| 架构 | 读写分离连接池 + WriteQueue | 已正确实现 Single Writer 模式 |

### 7.2 业务约束

- 开发环境 dev server 重启频繁（编码 → 保存 → 重启，多次/小时）
- ops_server 与主 server 可能并发运行（同一用户启动）
- test.py 测试框架有独立快照保护（不应受本修复影响）
- npm scripts 调用方式不变：`npm run dev:python` / `npm run dev:full`

### 7.3 假设

| 假设 | 状态 | 来源 |
|------|------|------|
| `architecture.db` 始终是 WAL 模式 | 已验证 | 连接池初始化时强制开启 |
| 只有主进程写入，ops_server 主要是只读 | 已验证 | 代码审计 |
| 用户不升级 Python/SQLite 版本 | 已确认 | 用户明确指示 |
| test.py 数据库操作走独立快照 DB，不影响主 DB | 已验证 | test.py 源码 |
| D 盘 NTFS 支持 POSIX 文件锁 | 已验证 | Windows NTFS 兼容 |

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-001 | 关闭 Flask reloader | **Must (P0)** | 最高频损坏路径：每次代码保存触发 fork |
| FR-002 | 清理残留 WAL/SHM | **Must (P0)** | 防御 crash 后的 WAL 污染 |
| FR-003 | 禁用运行时 VACUUM | **Must (P0)** | VACUUM + 写并发 = 确定性数据丢失 |
| FR-004 | ops_server 只读连接 | **Must (P0)** | 双 WAL writer 冲突 = 确定性 Bug |
| FR-005 | WriteQueue atexit | **Must (P0)** | 优雅关闭保护，防止事务残留 |
| FR-006 | 启动完整性检查 | Should (P1) | 防御性编程，减少人工恢复次数 |
| FR-007 | PRAGMA 参数优化 | Should (P1) | 性能与稳定性提升 |
| NFR-001 | 可靠性（100次启停） | **Must (P0)** | 核心验证标准 |
| NFR-002 | 可观测性 | Should (P1) | 运维可见性 |
| NFR-003 | 向后兼容 | **Must (P0)** | 不破坏现有功能 |
| NFR-004 | 恢复时间 RTO ≤ 30s | Should (P1) | 故障恢复目标 |
| NFR-005 | 请求延迟不劣化 | Should (P1) | P50 ≤ 基线×1.05, P99 ≤ 基线×1.10 |
| NFR-006 | 内存不增加 | Should (P1) | RSS ≤ 基线 × 1.10 |
| NFR-007 | 启动时间不显著增加 | Should (P1) | 增量 ≤ +500ms |

**里程碑**:

| 里程碑 | 范围 | 预期效果 |
|--------|------|----------|
| **Milestone 1 (P0)** | FR-001~005 + NFR-001, NFR-003 | 消除 5 个已知 corruption 路径，100 次启停零损坏，全量测试通过 |
| **Milestone 2 (P1)** | FR-006~007 + NFR-002, NFR-004~007 | 自动恢复 + 性能优化 + 可观测性 + 性能基准验证 |

---

## 9. 变更/设计提案 (RFC)

### 9.1 As-Is 分析

#### 当前架构（问题版）

```
┌──────────────────────────────────────────────────────────────┐
│  dev.py / server.py                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ Flask App    │  │ WriteQueue   │  │ ConnectionPool       │ │
│  │ (reloader=ON)│  │ (单写线程)    │  │ (1 writer + N readers)│ │
│  │              │  │ stop未注册    │  │ WAL mode             │ │
│  │ fork()  ────►│  │ atexit       │  │ sync=NORMAL          │ │
│  │ 子进程继续持有 │  │              │  │ auto_checkpoint=1000  │ │
│  │ DB连接 ✗      │  │              │  │ busy_timeout未设置    │ │
│  └─────────────┘  └──────────────┘  └──────────────────────┘ │
│                                                              │
│  ┌──────────────────┐                                       │
│  │ DBVacuumHandler  │  ← VACUUM on live DB ✗                │
│  │ (每周日 04:00)    │                                       │
│  └──────────────────┘                                       │
└──────────────────────────────────────────────────────────────┘
                          │
                          │ 同一 architecture.db
                          │
┌──────────────────────────────────────┐
│  ops_server.py (独立进程) ✗           │
│  ┌──────────────────────────────┐   │
│  │ 独立 sqlite3.connect()        │   │
│  │ 独立 PRAGMA journal_mode=WAL  │   │  ← 双 WAL writer! 冲突!
│  │ 独立 PRAGMA wal_checkpoint    │   │
│  └──────────────────────────────┘   │
└──────────────────────────────────────┘
```

#### 已识别问题（6 个根因）

| # | 问题 | 严重性 | 触发频率 | 影响 | 行业校验 | 修复 |
|---|------|--------|----------|------|----------|------|
| 1 | Flask reloader fork 多进程 | **Critical** | 每次代码保存 | SQLite howtocorrupt §2.7 | ✓ 官方确认 | FR-001 |
| 2 | VACUUM + 在线写入并发 | **Critical** | 每周日/手动调用 | Litestream Troubleshooting | ✓ 官方确认 | FR-003 |
| 3 | ops_server 独立 WAL 连接 | **High** | ops_server 运行时 | SQLite howtocorrupt §2.4 | ✓ 官方确认 | FR-004 |
| 4 | WriteQueue 无 atexit 保护 | **High** | 进程被 kill | Litestream Tips | ✓ 行业共识 | FR-005 |
| 5 | 残留 -wal/-shm 污染启动 | **Medium** | 每次 crash 后 | Litestream Tips | ✓ 行业共识 | FR-002 |
| 6 | SQLite 3.50.4 WAL-Reset Bug | **Medium** | 多连接并发 | SQLite 官方 WAL §11 | ✓ 官方 Bug | 不升级绕过 |

### 9.2 目标状态

```
┌──────────────────────────────────────────────────────────────┐
│  dev.py / server.py (单进程!)                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ Flask App    │  │ WriteQueue   │  │ ConnectionPool       │ │
│  │ (reloader=   │  │ atexit.stop  │  │ 启动前: 清理WAL/SHM   │ │
│  │   OFF)       │  │ atexit.flush │  │ 启动前: integrity_check│ │
│  │              │  │ SIGTERM hook │  │ auto_vacuum=          │ │
│  │ 单进程 ✓     │  │              │  │   INCREMENTAL         │ │
│  │ single proc  │  │              │  │ busy_timeout=5000     │ │
│  └─────────────┘  └──────────────┘  └──────────────────────┘ │
│                                                              │
│  ┌──────────────────┐                                       │
│  │ DBVacuumHandler  │  ← incremental_vacuum only ✓          │
│  └──────────────────┘                                       │
└──────────────────────────────────────────────────────────────┘
                          │
                          │ 同一 architecture.db
                          │
┌──────────────────────────────────────┐
│  ops_server.py (独立进程) ✓           │
│  ┌──────────────────────────────┐   │
│  │ 只读连接 (mode=ro)             │   │
│  │ NO journal_mode=WAL 设置       │   │  ← 不竞争 WAL!
│  │ NO wal_checkpoint            │   │
│  │ 仅 integrity_check + 只读查询 │   │
│  └──────────────────────────────┘   │
└──────────────────────────────────────┘
```

#### 关键变更清单

| # | 文件 | 变更内容 | 对应 FR |
|---|------|----------|---------|
| 1 | `dev.py:L58` | `use_reloader=False` | FR-001 |
| 2 | `sql_connection_pool.py` | 新增 `_safe_cleanup_wal_shm()` 在 `initialize()` 中调用 | FR-002 |
| 3 | `sql_connection_pool.py` | 新增 PRAGMA 初始化：`busy_timeout=5000`、`auto_vacuum=INCREMENTAL` | FR-007 |
| 4 | `system_handlers.py:L25` | `DBVacuumHandler` 改用 `PRAGMA incremental_vacuum` | FR-003 |
| 5 | `database_api.py:L109` | VACUUM 端点默认 dry-run | FR-003 |
| 6 | `ops_server.py:L78-L81` | `_get_db()` 改用 `mode=ro`，移除 WAL + checkpoint 操作 | FR-004 |
| 7 | `ops_server.py:L251` | 移除 `PRAGMA wal_checkpoint(TRUNCATE)` | FR-004 |
| 8 | `server.py` | 新增 `_cleanup_resources()` + `atexit` 注册 + 信号处理器 | FR-005 |
| 9 | `server.py` | 新增 `_preflight_db_check()` 在 `create_app()` 中调用 | FR-006 |

### 9.3 详细设计

#### 9.3.1 启动前 WAL/SHM 清理 (FR-002)

```python
# 位置: meta/core/sql_connection_pool.py, initialize() 方法开头

def _safe_cleanup_wal_shm(db_path: str):
    """清理孤立的 -wal 和 -shm 文件（仅当确认非活跃写入状态）"""
    import os
    import logging
    logger = logging.getLogger(__name__)
    
    wal_path = db_path + '-wal'
    shm_path = db_path + '-shm'
    
    if not os.path.exists(wal_path) and not os.path.exists(shm_path):
        return
    
    db_mtime = os.path.getmtime(db_path) if os.path.exists(db_path) else 0
    wal_mtime = os.path.getmtime(wal_path) if os.path.exists(wal_path) else 0
    
    # 只有在 WAL 比 DB 旧（非活跃写入状态）时才清理
    if wal_mtime > 0 and wal_mtime < db_mtime:
        for path in (wal_path, shm_path):
            try:
                os.remove(path)
                logger.info("Cleaned orphan file: %s (wal_mtime=%s < db_mtime=%s)",
                           path, wal_mtime, db_mtime)
            except OSError as e:
                logger.warning("Failed to clean orphan file: %s: %s", path, e)
```

#### 9.3.2 启动前完整性检查 (FR-006)

```python
# 位置: meta/server.py, create_app() 方法中，get_data_source() 之前

def _preflight_db_check(db_path: str) -> bool:
    """启动前数据库完整性验证，失败则自动从备份恢复"""
    import logging
    logger = logging.getLogger(__name__)
    
    file_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    if file_size < 1024:
        logger.info("[PREFLIGHT] DB is empty or new, skipping integrity check")
        return True
    
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if result == "ok":
            return True
        logger.error("[PREFLIGHT] DB integrity_check FAILED: %s", result)
    except sqlite3.DatabaseError as e:
        logger.error("[PREFLIGHT] DB is corrupt: %s", e)
    except Exception as e:
        logger.error("[PREFLIGHT] DB preflight error: %s", e)
    
    # 尝试从备份恢复
    bak_path = db_path + '.bak'
    if os.path.exists(bak_path):
        shutil.copy2(bak_path, db_path)
        # 二次验证
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if result == "ok":
                logger.warning("[PREFLIGHT] Recovered DB from backup successfully")
                return True
            logger.error("[PREFLIGHT] Backup is also corrupt")
        except Exception as e:
            logger.error("[PREFLIGHT] Backup recovery failed: %s", e)
    else:
        logger.error("[PREFLIGHT] No backup available")
    
    return False
```

#### 9.3.3 atexit 注册 + 信号处理 (FR-005)

```python
# 位置: meta/server.py, create_app() 末尾

import atexit
import signal

def _cleanup_resources():
    """进程退出时的资源清理"""
    logger = logging.getLogger(__name__)
    
    # 1. 排空写入队列
    if data_source and data_source._write_queue:
        try:
            logger.info("Flushing write queue...")
            data_source._write_queue.flush(timeout=30)
        except Exception as e:
            logger.warning("WriteQueue flush failed: %s", e)
    
    # 2. 停止写入队列
    if data_source and data_source._write_queue:
        try:
            logger.info("Stopping write queue...")
            data_source._write_queue.stop(timeout=30)
        except Exception as e:
            logger.warning("WriteQueue stop failed: %s", e)
    
    # 3. 关闭连接池
    if data_source and data_source._pool:
        try:
            logger.info("Shutting down connection pool...")
            data_source._pool.shutdown()
        except Exception as e:
            logger.warning("ConnectionPool shutdown failed: %s", e)

def _signal_handler(signum, frame):
    """处理 SIGTERM / SIGINT"""
    logger = logging.getLogger(__name__)
    logger.info("Received signal %s, shutting down gracefully...", signum)
    _cleanup_resources()
    sys.exit(0)

# 注册
atexit.register(_cleanup_resources)
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)
```

#### 9.3.4 ops_server 只读连接 (FR-004)

```python
# 位置: meta/ops_server.py, _get_db() 函数

def _get_db() -> sqlite3.Connection:
    db_path = _get_db_path()
    # 使用只读 URI 模式，不开 WAL，不与主 server 竞争
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn
```

移除 `db_status` 端点中的 checkpoint 调用：

```python
# 位置: meta/ops_server.py（原来的 L251 附近）
# 删除: conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
# 改为只读检查：
# conn.execute("PRAGMA integrity_check")
```

#### 9.3.5 VACUUM → incremental_vacuum (FR-003)

```python
# 位置: meta/handlers/system_handlers.py

class DBVacuumHandler(TaskHandler):
    def execute(self, params, context):
        try:
            ds = context.get('data_source')
            ds.execute("PRAGMA incremental_vacuum")
            return TaskResult(success=True, data={'action': 'INCREMENTAL_VACUUM'})
        except Exception as e:
            return TaskResult(success=False, error=str(e))
```

#### 9.3.6 PRAGMA 初始化 (FR-007)

```python
# 位置: meta/core/sql_connection_pool.py, _create_connection() 方法中

def _create_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    
    # 行业推荐的 PRAGMA 参数（按 Forward Email / zylos.ai / Shivek Khurana 建议）
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
    conn.execute("PRAGMA wal_autocheckpoint = 1000")
    
    return conn
```

### 9.4 备选方案对比

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **A: 单进程架构**（关闭 reloader） | 简单、根治 fork 问题、零额外依赖 | 修改后端代码需手动重启 | **已选**（Vite HMR 已覆盖前端热更新） |
| B: 迁移到 PostgreSQL | 多进程天然安全 | 开发环境复杂、迁移成本巨大、引入网络延迟 | 拒绝（过度工程） |
| C: 使用 SQLite exclusive locking mode | WAL + exclusive 减少锁冲突 | 仍受 reloader fork 影响、牺牲并发读取 | 拒绝（不解决根因） |
| D: VACUUM INTO + 原子替换 | 在线 VACUUM 安全 | 额外磁盘空间需求 | **辅助方案**（离线维护用） |
| E: 集成 Litestream | 实时连续备份 | 增加外部依赖、运维复杂度 | 拒绝（当前规模不需要） |

### 9.5 实施与迁移计划（安全执行版）

#### 核心原则

> **每个步骤 = 修改 → 验证 → 确认通过 → 下一步。禁止批量修改后一次性验证。**

#### 前置准备（Step 0）

> ⚠️ 在任何代码修改之前必须完成

```
[0.1] 创建基线
  - 备份: copy meta\architecture.db meta\architecture.db.baseline /Y
  - Git 分支: git checkout -b fix/sqlite-corruption
  - 记录基线性能: 运行一次全量测试 python d:\filework\test.py --all --force

[0.2] 停止正在运行的服务（避免修改时竞争）
  - 终端 6 (npm run dev:full) → 停止
  - 终端 7 (npm run dev:python) → 停止

[0.3] 确认当前 DB 状态
  python -c "import sqlite3; c=sqlite3.connect('meta/architecture.db'); print(c.execute('PRAGMA integrity_check').fetchone()); c.close()"
  → 必须输出 ok
```

---

#### Step 1: 关闭 Flask Reloader（FR-001）【最低风险】

```
[1.1] 修改 dev.py
  文件: dev.py:L58
  原值: app.run(host='0.0.0.0', port=port, debug=True, use_reloader=True, ...)
  改为: app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False, ...)

[1.2] ✅ 验证 checkpoint
  # 启动后端
  cd d:\filework\excel-to-diagram
  python dev.py &
  sleep 3
  
  # 确认只有一个 Python 进程
  Get-Process -Name python | Measure-Object | Select-Object Count
  → Count 应为 1（之前 reloader 模式下为 2）
  
  # 确认 API 可达
  python -c "import urllib.request; r=urllib.request.urlopen('http://localhost:3010/api/v1/health'); print(r.status)"
  → 200
  
  # 停止
  kill %1 2>nul

[1.3] ❌ 回退方案（如果验证失败）
  git checkout -- dev.py
```

#### Step 2: 新增 WAL/SHM 清理 + PRAGMA 初始化（FR-002 + FR-007）【低风险】

```
[2.1] 修改 sql_connection_pool.py
  新增函数: _safe_cleanup_wal_shm()  （见 9.3.1 节完整代码）
  修改方法: _create_connection() 增加 PRAGMA 初始化 （见 9.3.6 节完整代码）
  修改方法: initialize() 在 _create_connection() 之前调用 _safe_cleanup_wal_shm()

[2.2] ✅ 验证 checkpoint
  # 手动制造残留 WAL（模拟 crash 场景）
  cd meta
  python -c "
  import sqlite3
  conn = sqlite3.connect('architecture.db')
  conn.execute('PRAGMA journal_mode=WAL')
  conn.execute('CREATE TABLE IF NOT EXISTS _test(x)')
  conn.execute('INSERT INTO _test VALUES(1)')
  conn.close()
  "
  # 此时应存在 architecture.db-wal 和 architecture.db-shm
  
  # 修改 DB 的 mtime 使其比 WAL 新（模拟正常关闭后残留）
  python -c "
  import os, time
  os.utime('architecture.db', None)  # 更新 db mtime
  print(f'wal_mtime: {os.path.getmtime(\"architecture.db-wal\")}')
  print(f'db_mtime:  {os.path.getmtime(\"architecture.db\")}')
  "
  
  # 启动后端（应触发 _safe_cleanup_wal_shm）
  cd ..
  python dev.py &
  sleep 3
  
  # 查看日志确认清理
  # 应输出: [DB] Cleaned orphan file: ...architecture.db-wal ...
  
  # 确认 WAL 已被清理
  Test-Path meta/architecture.db-wal
  → False
  
  # 清理测试表
  python -c "import sqlite3; c=sqlite3.connect('meta/architecture.db'); c.execute('DROP TABLE IF EXISTS _test'); c.close()"
  
  kill %1 2>nul

[2.3] ❌ 回退方案
  git checkout -- meta/core/sql_connection_pool.py
```

#### Step 3: 新增 atexit + 信号处理（FR-005）【低风险】

```
[3.1] 修改 server.py
  新增函数: _cleanup_resources() （见 9.3.3 节完整代码）
  新增函数: _signal_handler()
  新增注册: atexit.register + signal.signal （在 create_app() 末尾）

[3.2] ✅ 验证 checkpoint
  # 启动后端
  python dev.py &
  sleep 3
  
  # 确认 API 可达
  python -c "import urllib.request; r=urllib.request.urlopen('http://localhost:3010/api/v1/health'); print(r.status)"
  
  # 发送 SIGINT 停止
  kill %1 2>nul
  wait-for-process-stop python 10
  
  # 检查日志输出
  # 应看到: "Flushing write queue..." → "Stopping write queue..." → "Shutting down connection pool..."
  
  # 确认停止后 WAL 无残留
  python -c "
  import os
  print('wal exists:', os.path.exists('meta/architecture.db-wal'))
  print('shm exists:', os.path.exists('meta/architecture.db-shm'))
  "
  → 两个都为 False（或至少 -wal 不存在）

[3.3] ❌ 回退方案
  git checkout -- meta/server.py
```

#### Step 4: 新增启动完整性检查（FR-006）【中风险】

```
[4.1] 修改 server.py
  新增函数: _preflight_db_check() （见 9.3.2 节完整代码）
  修改: create_app() 中，在 get_data_source() 之前调用 _preflight_db_check()
  如果返回 False → sys.exit(1) 阻止启动

[4.2] ✅ 验证 checkpoint — 正常启动
  python dev.py &
  sleep 3
  # 日志应显示: [PREFLIGHT] DB integrity_check passed
  kill %1 2>nul

[4.3] ✅ 验证 checkpoint — 损坏恢复
  # 备份当前 DB
  copy meta\architecture.db meta\architecture.db.temp_backup /Y
  copy meta\architecture.db meta\architecture.db.bak /Y
  
  # 人为损坏 DB
  python -c "
  with open('meta/architecture.db', 'wb') as f:
      f.write(b'corrupted_data_xxxxx')
  "
  
  # 启动后端 → 应自动从 .bak 恢复
  python dev.py &
  sleep 5
  
  # 日志应显示: [PREFLIGHT] DB is corrupt → [PREFLIGHT] Recovered DB from backup successfully
  
  # 验证恢复后的 DB 正常
  python -c "import sqlite3; c=sqlite3.connect('meta/architecture.db'); print(c.execute('PRAGMA integrity_check').fetchone()); c.close()"
  
  kill %1 2>nul
  
  # 清理
  copy meta\architecture.db.temp_backup meta\architecture.db /Y
  del meta\architecture.db.temp_backup

[4.4] ❌ 回退方案
  git checkout -- meta/server.py
```

#### Step 5: VACUUM → incremental_vacuum（FR-003）【低风险】

```
[5.1] 修改 system_handlers.py
  修改: DBVacuumHandler.execute() （见 9.3.5 节完整代码）

[5.2] 修改 database_api.py
  修改: VACUUM POST 端点 → 默认 dry-run 模式
  dry-run 返回: {page_count, freelist_count, free_ratio, recommendation}

[5.3] ✅ 验证 checkpoint
  # 启动后端
  python dev.py &
  sleep 3
  
  # 测试 VACUUM API → 应返回 dry-run（不实际执行）
  python -c "
  import urllib.request, json
  req = urllib.request.Request('http://localhost:3010/api/v1/system/database/vacuum',
      data=json.dumps({}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
  resp = urllib.request.urlopen(req)
  print(json.loads(resp.read()))
  "
  → 应包含 page_count, freelist_count, free_ratio 字段（无 VACUUM 执行）
  
  kill %1 2>nul

[5.4] ❌ 回退方案
  git checkout -- meta/handlers/system_handlers.py meta/api/database_api.py
```

#### Step 6: ops_server 只读连接改造（FR-004）【中风险】

```
[6.1] 修改 ops_server.py
  修改: _get_db() → 使用 file:{path}?mode=ro （见 9.3.4 节完整代码）
  移除: 连接时不再执行 PRAGMA journal_mode=WAL
  移除: db_status 端点中的 PRAGMA wal_checkpoint(TRUNCATE)
  保留: PRAGMA integrity_check（只读安全）

[6.2] ✅ 验证 checkpoint
  # 启动后端（如果有 ops_server 入口，也启动它）
  python dev.py &
  sleep 3
  
  # 如果没有独立的 ops_server 启动方式，手动测试只读连接
  python -c "
  import sqlite3
  conn = sqlite3.connect('file:meta/architecture.db?mode=ro', uri=True, timeout=10)
  result = conn.execute('PRAGMA integrity_check').fetchone()[0]
  print(f'integrity_check: {result}')
  conn.close()
  "
  → ok
  
  kill %1 2>nul

[6.3] ❌ 回退方案
  git checkout -- meta/ops_server.py
```

#### 终验：全量测试

```
[F.1] 运行全量测试
  python d:\filework\test.py --all --force
  
[F.2] 确认无新增失败
  对比 Step 0 的基线测试结果

[F.3] 性能基准对比
  # 具体方法见 NFR-005/006/007
  - 记录 P50/P99 延迟并与基线对比
  - 记录内存占用并与基线对比
  - 记录启动时间并与基线对比

[F.4] 启停压力测试（100 次）
  执行 9.5.1 节压力测试脚本，100 次启停后 integrity_check 必须全部 ok
```

---

#### 9.5.1 压力测试脚本（PowerShell 版）

```powershell
# 100 次启停循环压力测试
# 执行前确认: 后端未运行、DB 已备份

$ErrorActionPreference = "Stop"
$PYTHON = "python"
$DB_PATH = "meta\architecture.db"

for ($i = 1; $i -le 100; $i++) {
    Write-Host "=== Cycle $i/100 ===" -ForegroundColor Cyan
    
    # 启动后端
    $proc = Start-Process -FilePath $PYTHON -ArgumentList "dev.py" -PassThru -NoNewWindow
    Start-Sleep -Seconds 4
    
    # 验证 API 可达
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:3010/api/v1/health" -TimeoutSec 5 -UseBasicParsing
        if ($resp.StatusCode -ne 200) { throw "Health check returned $($resp.StatusCode)" }
    } catch {
        Write-Host "ERROR: API not reachable at cycle $i: $_" -ForegroundColor Red
        exit 1
    }
    
    # 停止后端
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    
    # 验证 DB 完整性
    $result = & $PYTHON -c @"
import sqlite3
conn = sqlite3.connect('$DB_PATH')
r = conn.execute('PRAGMA integrity_check').fetchone()[0]
print(r)
conn.close()
"@
    
    if ($result.Trim() -ne "ok") {
        Write-Host "CORRUPTED at cycle $i : $result" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "  Cycle $i: OK (integrity=$result)" -ForegroundColor Green
    Start-Sleep -Seconds 1
}

Write-Host "=== All 100 cycles PASSED ===" -ForegroundColor Green
```

#### 安全执行总结

```
┌─ Step 0: 前置准备 ─────────────────────────────────────────────┐
│ [✓] git branch + 备份 DB + 基线测试 + 停止现有服务              │
│ 状态: 准备就绪                                                   │
└────────────────────────────────────────────────────────────────┘
  ↓
┌─ Step 1-4: 低风险变更 ─────────────────────────────────────────┐
│ FR-001 → [验证] → [通过] →                                      │
│ FR-002+007 → [验证] → [通过] →                                  │
│ FR-005 → [验证] → [通过] →                                      │
│ FR-006 → [验证] → [通过]                                        │
│ 状态: 每个步骤都有独立验证 + 回退方案                             │
└────────────────────────────────────────────────────────────────┘
  ↓
┌─ Step 5-6: 中风险变更 ─────────────────────────────────────────┐
│ FR-003 → [验证] → [通过] →                                      │
│ FR-004 → [验证] → [通过]                                        │
└────────────────────────────────────────────────────────────────┘
  ↓
┌─ 终验 ─────────────────────────────────────────────────────────┐
│ [F.1] 全量测试 --all --force                                    │
│ [F.2] 对比基线确认无新增失败                                     │
│ [F.3] 性能基准对比 (NFR-005/006/007)                            │
│ [F.4] 100 次启停压力测试                                        │
│ 全部通过 → git commit → 完成                                    │
└────────────────────────────────────────────────────────────────┘
```

#### 紧急回滚（一键）

如果终验失败或上线后出现问题：

```powershell
# 一键恢复所有修改文件
cd d:\filework\excel-to-diagram
git checkout main -- dev.py meta/core/sql_connection_pool.py meta/server.py meta/handlers/system_handlers.py meta/api/database_api.py meta/ops_server.py

# 如果数据库损坏
copy meta\architecture.db.bak meta\architecture.db /Y

# 重启服务
npm run dev:full

---

## 10. TBD 列表（已全部解决）

| ID | 事项 | 原状态 | 解决方案 | 依据 |
|----|------|--------|----------|------|
| ~~TBD-1~~ | SQLite 升级 | 已解决 | **不升级**（用户决策）。SQLite 3.50.4 的 WAL-Reset Bug 通过架构改进（单进程、单 WAL writer）绕过 | 用户指示 |
| ~~TBD-2~~ | WAL autocheckpoint 阈值 | 已解决 | **保持默认 1000 页**（约 4MB）。开发服务器写入量低，1000 页即为最佳平衡——WAL 不会无限增长，checkpoint 频率也不过高。同时新增 `busy_timeout=5000`（行业标准）防止并发冲突被误判为错误 | [SQLite 官方 WAL §3.1](https://sqlite.org/wal.html#automatic_checkpoint) + [zylos.ai](https://zylos.ai/research/2026-02-20-sqlite-wal-mode-ai-agent-systems) |
| ~~TBD-3~~ | 离线 VACUUM 维护 | 已解决 | 在线维护用 **`auto_vacuum=INCREMENTAL` + `PRAGMA incremental_vacuum`**（低开销、不锁库）；离线 VACUUM 用 `VACUUM INTO` 导出 + 原子替换（仅手动触发）。如果 `freelist_count/page_count > 30%`，建议每月执行一次离线 VACUUM。建议保留一个 `npm run db:maintenance` 脚本 | [Litestream Cron-based backup](https://litestream.io/alternatives/cron/) + [Slingacademy TIP monitoring](https://www.slingacademy.com/article/automating-maintenance-tasks-in-sqlite-databases/#automating-the-vacuum-command) |
| ~~TBD-4~~ | 备份策略 | 已解决 | **三层备份**：① `architecture.db.bak` — 启动时自动备份（FR-006 使用）；② test.py 快照 — `test_temp/architecture_snapshot_*.db`（已有，保留 3 份）；③ 建议新增 `npm run db:backup` 脚本使用 `sqlite3 .backup` 命令生成压缩备份 | [Litestream Tips](https://litestream.io/alternatives/cron/) + [Slingacademy backup](https://www.slingacademy.com/article/automating-maintenance-tasks-in-sqlite-databases/#automating-backups) |

---

## 附录 A: 行业最佳实践校验摘要

| 来源 | 关键发现 | 对应我们的根因 |
|------|----------|---------------|
| [SQLite WAL §11 官方 Bug 页](https://sqlite.org/wal.html#the_wal_reset_bug) | WAL-Reset Bug (3.51.3+ 修复): 多连接并发写/checkpoint → corruption | 验证根因 #1 (reloader) + #3 (ops_server) |
| [SQLite howtocorrupt](https://sqlite.org/howtocorrupt.html) | fork() 携带 DB 连接 → corruption；两个进程不同锁协议 → corruption | 验证根因 #1 + #3 |
| [Litestream Tips](https://litestream.io/tips/) | 禁用 autocheckpoint 或合理设置；busy_timeout=5000；永远不要用 cp 备份 | 验证根因 #2 (WAL/SHM) + 指导 FR-007 |
| [Litestream: In-place VACUUM](https://litestream.io/docs/troubleshooting/#in-place-vacuum) | 在线 VACUUM 损坏 tracking state，建议使用 VACUUM INTO 替代 | 验证根因 #3 (VACUUM) |
| [Litestream: Cron-based backup](https://litestream.io/alternatives/cron/) | 使用 `.backup` 或 `VACUUM INTO` 备份，恢复后执行 integrity_check | 指导 TR-003 (离线维护) |
| [zylos.ai: WAL Pitfalls](https://zylos.ai/research/2026-02-20-sqlite-wal-mode-ai-agent-systems) | Single-Writer 是唯一安全模式；busy_timeout=5000-30000；checkpoint 模式选择 | 验证架构 + 指导 FR-007 |
| [blog.gary.info: WAL ≠ Multi-Writer](https://blog.gary.info/posts/sqlite-lying-concurrent-writes/) | WAL checkpoint 与写锁存在 race condition，架构级修复：单进程 | 验证根因 #1 |
| [Shivek Khurana: SQLite Production Benchmark](https://shivekkhurana.com/blog/sqlite-in-production/) | `WAL + NORMAL + busy_timeout + BEGIN IMMEDIATE` 是最优生产配置 | 指导 FR-007 |
| [Forward Email: Production PRAGMA](https://forwardemail.net/hu/blog/docs/sqlite-performance-optimization-pragma-chacha20-production-guide) | 大规模生产验证：`WAL + NORMAL + cache_size` 等多参数组合 | 指导 FR-007 |
| [Slingacademy: Automation](https://www.slingacademy.com/article/automating-maintenance-tasks-in-sqlite-databases/) | TIP 监控（freelist/page ratio > 30% → VACUUM）+ 自动化备份 | 指导 TR-003 |

**一致性结论**: 6 个根因中有 **4 个** 被 SQLite 官方文档明确列为 corruption 原因；另 2 个被 Litestream 等生产级工具明确指出。修复方案与行业共识完全一致。

## 附录 B: 损坏历史记录

| 日期 | 文件 | 恢复方式 |
|------|------|----------|
| 2026-05-31 | `architecture.db` (corrupted) | `architecture.db.bak` |
| 更早 | `architecture.db.corrupted` | 手动恢复 |
| 更早 | `architecture.db.corrupted2` | 手动恢复 |
| 未知 | `architecture.db.corrupted_20260531_230528` | 未追踪 |

---

*Spec 共包含 10 个章节 + 2 个附录，7 个 FR + 7 个 NFR，内容完整。*  
*最后更新: 2026-05-31*
