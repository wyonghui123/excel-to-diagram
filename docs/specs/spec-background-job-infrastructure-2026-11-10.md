# Spec：后台任务基础设施（job_definitions / job_triggers / task_runs）

> 状态：待评审（未实现）
> 日期：2026-11-10
> 前序研究：`d:\filework\fusion-task-research-2026-11-10.html` §4（目标架构与 P0–P4）
> 前序 spec：`docs/specs/task-two-generation-convergence/spec.md`（D6「账本统一」登记为缺口，本 spec 是其继任方案）
> 范围：**新建一套通用后台作业基础设施**，不改造 Gen1 队列、不复活 `task_executions`、不动 Gen2 `tasks` 业务状态机。

---

## 1. 结论先行

当前系统"能跑后台任务"，但没有**统一的任务基础设施**：

| 能力 | 现状 | 结论 |
|---|---|---|
| 作业定义 | 硬编码在 3 个进程内 Scheduler 的 `DEFAULT_JOBS` / 常量里 | 不可动态注册、不可查询、不可禁用单条 |
| 触发器 | 代码内 `time.sleep(interval)` 轮询 + 手写 cron 判断 | 无到期表、无"错过补偿"、无法统一观测 |
| 执行账本 | `task_executions`（Gen1，25642 行）与 `task_events`（Gen2，0 行）双轨且无桥接 | 无跨作业统一视图 |
| 并发隔离 | `ThreadPoolExecutor.submit()` fire-and-forget | 无 claim / lease / 超时回收 / 去重 |
| 重试与死信 | `async_audit_writer` 自带 3 次重试；`TaskScheduler` 有 dead letter；运维作业没有 | 三套语义，互相不可见 |

本 spec 定义四层对象与一个通用消费者：

```
job_definitions   作业定义（what：handler / 参数 schema / 超时 / 重试策略）
job_triggers      触发器（when：cron / interval / 手动 / 事件）
task_runs         执行账本（how it went：参数快照 / 状态 / attempt / 耗时 / 错误）
dispatcher        通用消费者（tick → 建 run → claim/lease → 投递 executor → 回收）
```

**首个接入的 executor 必须是"失败不影响业务"的作业**（审计重试 / DB 维护），不允许首批接入业务事务。

---

## 2. 现状证据

| 事实 | 证据 |
|---|---|
| `TaskScheduler` 仍启动，但只加载队列、不跑 cron | `meta/server.py:797-799`（`check_interval=60`）；类注释与 `start()` 明确 `queue-only, no cron loop`，`meta/core/task_scheduler.py` |
| 队列配置唯一源 = DB `task_queues` | `meta/server.py:801-803`；`meta/core/task_queue_manager.py:51-70`（`SELECT * FROM task_queues WHERE enabled=1`）|
| 队列执行是线程池直投，无持久化、无重试、无租约 | `meta/core/task_queue_manager.py:39`（`ThreadPoolExecutor(max_workers=...)`）、`:99-132`（`executor.submit(_execute)`）|
| cron 已与遗留调度器解耦，改由 3 个进程内 Scheduler 承担 | `meta/server.py:805-826`；`MaintenanceScheduler` / `PlatformScheduler` / `WorkflowScheduleScheduler`；总开关 `CRON_JOBS_ENABLED`（`meta/server.py:827-828`）|
| 进程内调度器为 `while + sleep(interval)` 轮询 | `meta/core/maintenance_scheduler.py:117,152,176` |
| 作业清单硬编码 | `meta/core/maintenance_scheduler.py:88-91`（`OPS_JOB_CODES` / `JOB_CODES`）|
| Gen2 `tasks` 已有 11 态状态机与 `type` / `executor_type` 双层类型 | `meta/core/task_schema.py:26`（`TASK_TABLE = "tasks"`）、`:38`（`TASK_STATUSES`）、`:44`（业务分类与 executor_type 正交）|
| `task_events` 为 append-only 事件账，但当前 0 行 | `meta/core/task_event_schema.py:43-47`（`TASK_EVENT_TABLE` / `WORKLOG_TABLE`）|
| 审计写入有自己的队列 + 重试 + 降级同步 | `meta/services/async_audit_writer.py:26-31`（`AUDIT_ASYNC_*` / `AUDIT_MAX_RETRIES`）、`:48`（`queue.Queue(maxsize=1000)`）|
| 迁移号已到 v245，新迁移从 **v246** 起 | `meta/migrations/v245__customer_invoice_fee_line_types.py` |

**关键判定**：Gen1 的 `task_queues` / `task_executions` / `TaskQueueManager` 解决的是"进程内并发执行"，不是"作业调度与可观测"。二者的边界应在 spec 中显式化，而不是继续在 `TaskScheduler` 上叠加职责。

---

## 3. 设计原则

1. **账本先行**：先有 `task_runs`（可查询、可回溯），再有调度与执行接管。
2. **单一消费者**：只有 dispatcher 推进 `job_triggers.next_run_at` 与 `task_runs.status`，业务代码只写定义与触发器。
3. **幂等优先**：任何一次 tick 重复执行都不得产生重复 run（`run_key` 唯一约束兜底）。
4. **失败隔离**：executor 抛错只影响该 run，不影响 dispatcher 线程与业务事务。
5. **不合并状态机**：`task_runs.status` 是"执行账本状态"，与 Gen2 `tasks.status`（业务生命周期）正交；`task_runs.task_id` 仅作可选桥接。
6. **默认关闭**：`JOB_DISPATCH_ENABLED=0` 为默认值，所有阶段可灰度、可一键停。

### 明确不做

| 不做 | 理由 |
|---|---|
| 复活或删除 `task_executions` | 25k 行历史仍有查询价值；删除属数据治理，独立执行 |
| 用 `task_events` 替代 `task_runs` | `task_events` 是领域事件（迁移/工时），语义不是执行尝试 |
| 引入 Temporal / Airflow / Celery | 单机 SQLite 部署，运维成本远大于收益 |
| 让 dispatcher 直接执行 Gen2 业务动作 | 业务动作仍走 `tasks` + `task_write_guard`；本 spec 只承载基础设施作业 |
| 首批接入业务事务（如盘点过账、发票记账） | 事务型作业需要与请求线程共享事务语义，不适合首批迁移 |

---

## 4. 数据模型

### 4.1 `job_definitions`（v246）

```sql
CREATE TABLE job_definitions (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  code               TEXT    NOT NULL UNIQUE,   -- 稳定标识，如 'db_analyze' / 'audit_retry'
  name               TEXT    NOT NULL,
  description        TEXT,
  executor_type      TEXT    NOT NULL DEFAULT 'python',  -- python | http | external
  handler            TEXT    NOT NULL,           -- ExecutorRegistry 中的 key
  params_schema      TEXT,                       -- JSON Schema（校验 + 前端渲染）
  default_params     TEXT,                       -- JSON
  timeout_seconds    INTEGER NOT NULL DEFAULT 300,
  max_attempts       INTEGER NOT NULL DEFAULT 3,
  backoff_seconds    INTEGER NOT NULL DEFAULT 60, -- 第 n 次重试等待 n * backoff
  concurrency_group  TEXT,                       -- P4：互斥组
  record_mode        TEXT    NOT NULL DEFAULT 'all', -- all | failure_only
  status             TEXT    NOT NULL DEFAULT 'active', -- active | disabled
  created_at         TEXT,
  updated_at         TEXT
);
```

- `record_mode='failure_only'`：高频心跳类作业（`platform_tick`，1 分钟一次）只落失败 run，避免账本膨胀。
- `status='disabled'` 是**定义级**开关，与 `job_triggers.enabled`（**触发器级**开关）分离。

### 4.2 `job_triggers`

```sql
CREATE TABLE job_triggers (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id            INTEGER NOT NULL,
  trigger_type      TEXT    NOT NULL DEFAULT 'cron', -- cron | interval | manual | event
  cron_expr         TEXT,
  interval_seconds  INTEGER,
  event_name        TEXT,
  params_override   TEXT,                            -- JSON，覆盖 default_params
  timezone          TEXT    NOT NULL DEFAULT 'Asia/Shanghai',
  enabled           INTEGER NOT NULL DEFAULT 1,
  next_run_at       REAL,                            -- UTC epoch 秒；NULL = 尚未排期
  last_run_at       REAL,
  created_at        TEXT,
  updated_at        TEXT
);

CREATE INDEX ix_job_triggers_due ON job_triggers(enabled, next_run_at);
```

- cron 解析复用 `meta/core/cron_parser.py`（`CronParser`），不引入新依赖。
- `trigger_type='manual'` 的触发器 `next_run_at` 恒为 NULL，不参与扫描；手动运行由 API 直接建 run。
- `event_type` 的一期实现：仅建表 + 存储，dispatcher 不消费（P4 再开）。

### 4.3 `task_runs`

```sql
CREATE TABLE task_runs (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  run_key          TEXT    NOT NULL UNIQUE,  -- '<trigger_id>:<scheduled_for>' 或 'manual:<uuid>'
  job_id           INTEGER NOT NULL,
  trigger_id       INTEGER,                  -- manual run 可为 NULL
  task_id          INTEGER,                  -- 可选：桥接 Gen2 tasks
  status           TEXT    NOT NULL,         -- 见 §5
  params           TEXT,                     -- 参数快照（脱敏后）
  attempt          INTEGER NOT NULL DEFAULT 1,
  max_attempts     INTEGER NOT NULL DEFAULT 3,
  scheduled_for    REAL    NOT NULL,         -- 计划执行时刻（UTC epoch 秒）
  claimed_at       REAL,
  started_at       REAL,
  finished_at      REAL,
  lease_until      REAL,                     -- 租约到期（UTC epoch 秒）
  worker_id        TEXT,                     -- '<hostname>:<pid>:<thread>'
  duration_ms      INTEGER,
  result           TEXT,
  error            TEXT,
  next_retry_at    REAL,
  created_at       TEXT,
  updated_at       TEXT
);

CREATE INDEX ix_task_runs_status_lease ON task_runs(status, lease_until);
CREATE INDEX ix_task_runs_job_time     ON task_runs(job_id, created_at);
```

**为什么不复用 `task_executions`**：该表列固定为 Gen1 队列语义（`queue` / `priority` / `handler`），缺 `run_key` / `lease_until` / `attempt` / `next_retry_at`；在其上加列会让一张 25k 行的历史表承担两套语义。

---

## 5. 状态机（`task_runs.status`）

```
                 ┌────────── 人工 retry ──────────┐
                 ▼                                │
  pending ──claim──► claimed ──start──► running ──┴─► succeeded（终态）
     │                  │                  │
     │                  │ 租约过期           │ 抛错 / 超时
     │                  ▼                  ▼
     │              retrying ◄────────── failed
     │                  │                  │ attempt >= max_attempts
     │                  │ next_retry_at 到期 ▼
     └──────────────────┘                dead（终态）
     │
     └── 人工取消 / 并发组占用 ──► cancelled / skipped（终态）
```

| 状态 | 含义 | 可被 dispatcher 领取 |
|---|---|---|
| `pending` | 已创建、未领取 | 是 |
| `claimed` | 已被某 worker 领取，尚未开始 | 否（租约过期可回收）|
| `running` | 执行中 | 否（租约过期可回收）|
| `succeeded` | 成功（终态）| 否 |
| `failed` | 本次尝试失败，等待重试 | 否 |
| `retrying` | 等待 `next_retry_at` 到期 | 到期后转 `pending` |
| `dead` | 重试耗尽或不可重试错误（终态）| 否 |
| `cancelled` | 人工取消（终态）| 否 |
| `skipped` | 并发组占用 / `record_mode` 过滤（终态）| 否 |

**与 Gen2 11 态的关系**：不映射、不复制。`task_runs.task_id` 非空时，可在任务详情页以"执行记录"子列表展示，但状态并列展示、互不驱动。

---

## 6. Dispatcher

### 6.1 单次 tick（幂等）

```python
def tick(now: float = None) -> None:
    now = now or utc_epoch()
    with write_tx():                                   # 一个短事务
        due = q("SELECT * FROM job_triggers "
                "WHERE enabled=1 AND trigger_type IN ('cron','interval') "
                "AND next_run_at IS NOT NULL AND next_run_at <= ? "
                "ORDER BY next_run_at LIMIT ?", [now, TICK_BATCH])
        for t in due:
            run_key = f"{t.id}:{int(t.next_run_at)}"
            insert_ignore_run(run_key, t, scheduled_for=t.next_run_at)
            advance(t, now)                            # 乐观推进，见 6.3

    for run in q("SELECT * FROM task_runs WHERE status='pending' "
                 "AND scheduled_for <= ? ORDER BY scheduled_for LIMIT ?",
                 [now, EXEC_BATCH]):
        claim_and_submit(run)
```

顺序要求：**先建 run，再推进触发器**，二者同一事务；`run_key` 唯一约束保证崩溃重放不产生重复 run。

### 6.2 claim / lease（SQLite 条件 UPDATE）

```sql
-- 1) 领取：只有状态仍为 pending 才能成功
UPDATE task_runs
   SET status = 'claimed',
       worker_id = ?,
       claimed_at = ?,
       lease_until = ?,
       updated_at = ?
 WHERE id = ? AND status = 'pending';

-- 2) 确认领取成功（避免依赖 rowcount 的平台差异）
SELECT changes();                     -- 或 SELECT status FROM task_runs WHERE id = ?

-- 3) 开始执行
UPDATE task_runs
   SET status = 'running', started_at = ?, updated_at = ?
 WHERE id = ? AND status = 'claimed' AND worker_id = ?;

-- 4) 执行中续租（长作业，每 LEASE_RENEW_INTERVAL 一次）
UPDATE task_runs
   SET lease_until = ?
 WHERE id = ? AND status = 'running' AND worker_id = ?;
```

约束：
- 所有写必须走 `data_source.execute` 的**写路径**（`meta/core/datasource.py:280`），不得用只读连接。
- 项目已有多连接下 `lastrowid` 不可靠的经验（`meta/core/task_scheduler.py` 中 `_create_execution_record` 注释），因此**不依赖 `RETURNING`**：以 `changes()` 或回读状态判定。
- 退避策略复用 `_retry_db_write` 同款语义（指数 + jitter），但不直接引用该私有函数，在 `job_run_store` 内独立实现，避免跨模块耦合。

### 6.3 触发器推进（乐观并发）

```sql
UPDATE job_triggers
   SET next_run_at = ?,                      -- cron: 下一次；interval: now + interval
       last_run_at = ?,
       updated_at  = ?
 WHERE id = ? AND next_run_at = ?;           -- 期望值 = 本次读到的旧值
```

`changes() = 0` 说明另一个 tick / 另一个进程已推进，**不重复建 run**（该 run 已由上一步 `INSERT OR IGNORE` 保证唯一）。

### 6.4 租约回收（watchdog）

```sql
-- running 过期 → 重试或死信，由 store 层判定 attempt
UPDATE task_runs
   SET status = 'retrying',
       attempt = attempt + 1,
       next_retry_at = ?,
       error = 'lease expired',
       worker_id = NULL,
       updated_at = ?
 WHERE status IN ('claimed','running') AND lease_until < ?;
```

回收同样是幂等的：再次执行时这些行已不在 `claimed/running`，不会重复自增。

### 6.5 线程模型与开关

| 项 | 设计 |
|---|---|
| dispatcher 线程 | 单线程 `while + Event.wait(tick_interval)`，默认 `tick_interval=5s` |
| 执行载体 | 复用 `TaskQueueManager` 的 `ThreadPoolExecutor`（按 `executor_type` 选队列），**不新建线程池** |
| 总开关 | `JOB_DISPATCH_ENABLED`（默认 `0`）|
| 影子模式 | `JOB_DISPATCH_DRY_RUN=1`：只建 run 与推进触发器，不 claim、不执行；run 直接落 `skipped` 便于比对 |
| 停机 | 与 `TaskScheduler.stop()` 同生命周期，`server.py` 统一收尾 |

---

## 7. Executor 插件接口

```python
# meta/core/job_executor.py

@dataclass
class JobContext:
    run_id: int
    job_code: str
    params: dict
    attempt: int
    deadline_monotonic: float
    cancel_event: threading.Event

@dataclass
class JobResult:
    success: bool
    data: dict | None = None
    error: str | None = None

class JobExecutor(Protocol):
    name: str
    supports_cancel: bool          # False 时，取消仅标记 cancel_requested
    def run(self, ctx: JobContext) -> JobResult: ...

class ExecutorRegistry:
    def register(self, executor: JobExecutor) -> None: ...
    def get(self, name: str) -> JobExecutor | None: ...
```

要求：
1. executor 内部**不得**自行 sleep 重试；重试由 dispatcher 依据 `job_definitions.max_attempts` / `backoff_seconds` 决定。
2. executor 必须响应 `cancel_event`（每 1s 至少检查一次）；HTTP executor 通过 `requests` 超时实现。
3. executor 抛出的异常由 dispatcher 统一转成 `failed` + `error`，不得吞掉。
4. 参数进入 executor 前必须已脱敏（§10 风险 R6）。

**首个接入**：`audit_retry`（包装现有 `AuditRetryWorker` 的单轮重试）。理由：它本身"失败不影响业务 + 自带重试语义"，状态映射最直接，且可立即验证 retry/dead 路径。`async_audit_writer` 的进程内队列**本期不改**，P2 再评估是否收敛为 executor。

---

## 8. API

| 方法 | 路径 | 说明 | 门控 |
|---|---|---|---|
| GET | `/api/v2/jobs/definitions` | 定义列表 | 无（只读）|
| GET | `/api/v2/jobs/triggers` | 触发器列表（含 `next_run_at`）| 无 |
| GET | `/api/v2/jobs/runs?job_code=&status=&limit=` | 账本分页 | 无 |
| GET | `/api/v2/jobs/runs/<id>` | 单条详情（含 `result` / `error`）| 无 |
| POST | `/api/v2/jobs/runs/<id>/retry` | 人工重试（`dead`/`failed` → `pending`，`attempt+1`）| `is_module_enabled('tasks')` |
| POST | `/api/v2/jobs/runs/<id>/cancel` | 人工取消（置 `cancel_event`）| 同上 |
| POST | `/api/v2/jobs/<code>/run-now` | 手动运行（建 `manual:<uuid>` run）| 同上 |

- 沿用现有 `scheduler_bp` 的"状态类接口无条件、写接口门控"惯例（`meta/server.py:988-1005` 的既有差异在 `task-two-generation-convergence/spec.md` §2.2 已登记）。
- 响应字段使用 `snake_case`，与 `task_inbox_api` 一致。
- 单条 run 的 `params` 默认不返回（仅返回字段名）；`?include_params=1` 才返回脱敏后的值。

---

## 9. 迁移与播种（v246）

文件：`meta/migrations/v246__background_job_infrastructure.py`

> 结构沿用 v245 的模块级 `_do_*` 函数风格，但**入口必须是 `def migrate(db_path, skip_backup=True)`**——`migration_runner.run_migration` 只调用 `migrate`，不调用 `upgrade`；`upgrade = migrate` 仅作别名。

内容：
1. 建 `job_definitions` / `job_triggers` / `task_runs` 三表 + 三个索引（`ix_job_triggers_due` / `ix_task_runs_status_lease` / `ix_task_runs_job_time`，均 `IF NOT EXISTS`）。
2. 播种 **10 条** `job_definitions`（8 个运维作业：`db_analyze` / `db_vacuum` / `db_integrity_check` / `db_checkpoint` / `audit_failure_retry` / `audit_log_cleanup` / `audit_log_archive` / `import_queue_processor`；加 `platform_tick` 与 `workflow_schedule` 占位），全部 `status='active'`，但**不播种 enable 的触发器**。
   > 注：审计重试作业的实际 code 是 `audit_failure_retry`（不是 `audit_retry`）；`workflow_schedule` 无静态 cron，触发器行 `cron_expr=NULL`，等待 P2 从工作流定义动态派生。
3. 播种 **10 条** `job_triggers`，`enabled=0`、`next_run_at=NULL`——供 P1 影子比对时手工打开。
4. 不写任何历史数据迁移（`task_executions` 保持原样）。
5. 幂等：所有 DDL 用 `IF NOT EXISTS`；播种用「先查存在再插入」（按 `code` / `(job_id, trigger_type)` 跳过，重复执行打印 `[SKIP]`）。

回滚策略：迁移只新增表，`downgrade` 不提供；不符预期时以 `JOB_DISPATCH_ENABLED=0` 停用，不 DROP 表。

---

## 10. 分阶段落地

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 账本** | v246 三表 + `job_run_store`（create/claim/start/finish/retry/dead/reclaim）+ 单测；在 `audit_failure_retry` 执行点旁路 `record()` | 全新库跑迁移后三表存在；`test_job_run_store.py` 全绿；业务行为零变化 |
| **P1 触发器统一** | 播种定义/触发器；dispatcher 以 `DRY_RUN=1` 运行；比对"应到期"与三个进程内 Scheduler 实际执行次数 | 连续 24h：`dry-run run 数` 与 `Scheduler 执行次数` 差异 ≤ 1（允许首个 tick 边界）；不产生 `pending` 堆积 |
| **P2 claim/lease + 执行** | 打开 `JOB_DISPATCH_ENABLED`，仅 `audit_failure_retry` 与 `db_analyze` 实际执行；其余定义保持 `enabled=0` | 双 worker 并发压测：同一 run 仅一个成功 claim；进程被 kill 后 2×lease 内回收为 `retrying` |
| **P3 重试与死信** | 按定义执行 backoff；`dead` 可查询 + 运维告警；人工 retry/cancel API | 注入失败 executor：attempt 达上限落 `dead`；重试间隔符合 `backoff_seconds`；cancel 在 1s 内生效 |
| **P4 治理** | `concurrency_group` 互斥、优先级、`record_mode` 过滤、event 触发器 | 同组两个触发器同时到期只产生一个 `running`，另一个 `skipped`；`failure_only` 作业成功时不落账本 |

**实现状态**：P0 已完成（v246 + `job_run_store.py`，19 条测试）；P1 代码已就绪（`meta/core/job_dispatcher.py`，10 条测试）；P2 代码已就绪（`meta/core/job_executor_registry.py` + dispatcher 的 claim/lease/执行/回收路径，14 条测试；未传 `executor_pool` 时在 tick 线程内联执行）。三阶段均由 `JOB_DISPATCH_ENABLED` / `JOB_DISPATCH_DRY_RUN` 控制，默认关闭，**尚未接入 `server.py`**——接入、首批作业（`audit_failure_retry` / `db_analyze`）打开 `enabled` 与 24h 影子观测属运维动作，需先确认三个进程内 Scheduler 的 tick 间隔。

**阶段硬门禁**：进入下一阶段前，上一阶段验收标准必须连续通过，且 `python d:\filework\test.py --failed` 无新增失败。

---

## 11. 测试计划

新增测试（`meta/tests/`）：

| 文件 | 覆盖 |
|---|---|
| `test_job_run_store.py` | 状态迁移矩阵、`run_key` 幂等、`attempt` 上限入 `dead`、租约回收、人工 retry/cancel |
| `test_job_dispatcher.py` | 假时钟下"一个 due trigger 只建一个 run"、并发 claim 唯一成功、`DRY_RUN` 不执行、触发器乐观推进不重复 |
| `test_job_executor_registry.py` | 注册/查找、异常转 `failed`、超时转 `failed`、`cancel_event` 生效 |

运行命令：

```powershell
python d:\filework\test.py --single meta/tests/test_job_run_store.py
python d:\filework\test.py --single meta/tests/test_job_dispatcher.py
python d:\filework\test.py --single meta/tests/test_job_executor_registry.py
python scripts/lint_tests.py
```

测试数据用内存 SQLite + 迁移里的 `_do_*` 常量建表，**不读写 `meta/architecture.db`**（沿用 `meta/tests/inventory_adjustment_doubles.py` 的做法：直接复用迁移函数，避免 DDL 漂移）。

---

## 12. 风险与对策

| ID | 风险 | 对策 |
|---|---|---|
| R1 | SQLite 单写者 → tick 与业务写竞争 | tick 事务只做"读到期 + INSERT OR IGNORE + 推进"，不含执行；执行在事务外 |
| R2 | `execute()` 返回值平台差异，误判 claim 成功 | 以 `SELECT changes()` / 回读 `status` 判定，不依赖 cursor 类型 |
| R3 | 时钟回拨 / NTP 跳变导致重复或漏跑 | 统一 UTC epoch 秒；`run_key` 唯一约束兜底；`next_run_at` 推进用"旧值乐观匹配" |
| R4 | 高频道作业（`platform_tick` 60s）账本膨胀 | 默认 `record_mode='failure_only'`；成功 run 保留 30 天（`JOB_RUN_RETENTION_DAYS`），清理本身注册为作业 |
| R5 | 影子模式双跑造成副作用翻倍 | `DRY_RUN` 只建 run 不执行；P2 只对已确认幂等的作业开启真实执行 |
| R6 | run 的 `params` 落库泄露敏感字段 | 入账前过脱敏（与审计日志同一规则）；详情 API 默认不回传 `params` |
| R7 | 与 Gen2 `tasks` 职责混淆 | `task_runs` 仅基础设施作业；业务任务继续走 `tasks` + `task_write_guard`；`task_id` 只读桥接 |
| R8 | dispatcher 崩溃导致 `claimed` 悬挂 | lease TTL（默认 60s）+ watchdog 回收；回收本身幂等 |

---

## 13. 开放问题（需批准）

| ID | 问题 | 建议默认 |
|---|---|---|
| Q1 | 成功 run 保留期 | 30 天，环境变量可调；`dead` 永久保留至人工清理 |
| Q2 | `platform_tick` 是否纳入触发器 | 纳入，但 `record_mode='failure_only'` |
| Q3 | 取消语义强度 | Python executor 协作式取消；HTTP executor 仅标记 `cancel_requested`，不强制中断 |
| Q4 | 是否支持跨进程 / 跨机 worker | 本期只支持单进程多线程；lease 字段为未来多进程预留 |
| Q5 | 是否允许业务代码直接提交 run | P4 前不允许；`async_import_service` 等维持现状 |

---

## 14. 范围外

1. `task_executions` 历史数据归档 / 删除。
2. `task_events` 与 `task_runs` 的桥接写入（保持双轨，直至 Gen2 编排域重构）。
3. `async_audit_writer` 进程内队列的收敛（P2 评估，不在本 spec 承诺）。
4. 跨机 worker 与分布式锁。
5. 前端任务中心改造（本期只提供 API）。

---

## 15. 验证命令

```powershell
# 迁移可执行 + 幂等（重复跑不报错）
python d:\filework\test.py --single meta/tests/test_migration_runner.py

# 新增测试
python d:\filework\test.py --single meta/tests/test_job_run_store.py
python d:\filework\test.py --single meta/tests/test_job_dispatcher.py
python d:\filework\test.py --single meta/tests/test_job_executor_registry.py

# 回归（相邻域）
python d:\filework\test.py --single meta/tests/test_task_scheduler.py
python d:\filework\test.py --single meta/tests/test_task_inbox_api.py

# 测试规范自查
python scripts/lint_tests.py
```