# Spec：后台任务基础设施（job_definitions / job_triggers / task_runs）

> 状态：P0-P2 已实装并接线（账本 / 触发器 / claim-lease-executor / handler 注册 / `bo_action` 桥接 / 参数校验 / 手动入口）；只读账本（横切）已上线；定义与触发器管理面、P4 治理待建（见 §10.1）
> 日期：2026-11-10（细化：实装对齐 / handler 安全边界 / 应用类作业桥接 / 调度接入）
> 前序研究：`d:\filework\fusion-task-research-2026-11-10.html` §4（目标架构与 P0–P4）；ESS 对标结论见 §16
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

### 1.1 落地快照（2026-11-10）

| 层 | 代码 | 状态 |
|---|---|---|
| 账本 | `meta/core/job_run_store.py` | 已实现，`test_job_run_store.py` 19 条 |
| 调度 | `meta/core/job_dispatcher.py` | 已实现，`test_job_dispatcher.py` 11 条；已接入 `meta/server.py`（`JOB_DISPATCH_ENABLED` 默认 0，灰度启动） |
| 执行 | `meta/core/job_executor_registry.py` + `meta/handlers/job_handlers.py` | 已实现，`test_job_executor_registry.py` 14 条；生产侧由 `build_default_job_registry()` 注册 5 个运维 handler + `bo_action`（`test_job_handlers.py` 8 条） |
| 参数校验 | `meta/core/job_params.py` | 已实现（§7.2 白名单 + `params_schema`），dispatcher claim 前执行，`test_job_params.py` 12 条 |
| 写接口 | `meta/api/job_admin_api.py` | 已实现 `run-now` / `retry` / `cancel`，权限 `job_admin`，`test_job_admin_api.py` 9 条 |
| 只读账本 UI | `meta/schemas/task_run.yaml` + `/system/task-runs` | 已实现（`generic_api_mode: read_only` + `task_run:read`），`test_generic_api_mode.py` 19 条；页面未真机验证 |
| 定义 / 触发器管理面 | — | **未实现**（无 CRUD API、无 UI，见 §10.1 第 6 项） |
| 应用类作业（巡检等） | `meta/handlers/job_handlers.py:make_bo_action_executor` | 桥接已实现（§7.3）；示例定义 `inspection_daily` 已播种但 `status=disabled`、触发器 `enabled=0` |

一句话：**骨架已通电**——handler 注册、调度灰度接入、参数校验、手动入口均已接线；剩余定义管理面（第 6 项）与 P4 治理（第 7 项）。

**首个接入的 executor 必须是"失败不影响业务"的作业**（审计重试 / DB 维护），不允许首批接入业务事务。应用类作业（巡检、报表刷新等）通过 §7.3 的 `bo_action` 桥接接入，仍以"只读 / 可重放 / 失败不阻断业务"为前提。

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
7. **白名单注册**：`job_definitions.handler` 只能是启动期 `registry.register()` 过的名字；禁止按字符串反射解析模块 / 函数（见 §7.2）。

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
  code               TEXT    NOT NULL UNIQUE,   -- 稳定标识，如 'db_analyze' / 'audit_failure_retry'
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
     ├── 人工取消 ──────────────────► cancelled（终态）
     ├── record_mode 过滤 / DRY_RUN ► skipped（终态）
     └── 并发组占用（P4）──────────► blocked（非终态，组释放后回 pending）
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
| `skipped` | `record_mode` 过滤 / `DRY_RUN`（终态）| 否 |
| `blocked` | 并发组被占用（**P4 预留，尚未实装**）；非终态，组释放后回 `pending` | 否（每 tick 复查）|

**对标 ESS**：ESS 把互斥冲突落 `Blocked`（非终态、自动恢复），而不是丢弃运行；本 spec 据此把 `skipped` 收窄为"本就不该记账的运行"（`DRY_RUN` / `record_mode`），并发占用改由 `blocked` 表达（§16.1）。

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

| 项 | 实装 |
|---|---|
| 常驻循环 | `JobDispatcher.start()` → 单 daemon 线程 `job-dispatcher`，`Event.wait(tick_interval)`，默认 `5s`；`stop()` 置位并 `join(5s)` |
| 执行载体 | 未传 `executor_pool` 时**在 tick 线程内同步执行**（`_execute_run`）；传入池才 `pool.submit`。当前无池 → 调度与执行同线程 |
| 租约 | `lease = max(60s, timeout_seconds + 30s)`，覆盖整个执行窗口，避免同进程 watchdog 误回收长作业 |
| 总开关 | `JOB_DISPATCH_ENABLED`（默认 `0`），构造函数可显式覆盖 |
| 影子模式 | `JOB_DISPATCH_DRY_RUN=1`：只建 run + 推进触发器 + 落 `skipped(dry_run)`，不 claim、不执行 |
| 批量 | `batch=50`（到期触发器、pending run 各一批） |
| 停机 | `stop()`；与后端进程同生命周期（接入见 6.6） |

### 6.6 启动接入（待完成）

```python
# meta/server.py：进程内 Scheduler 之后、同一 CREON_JOBS_ENABLED 区段
if job_dispatch_enabled():
    _job_dispatcher = JobDispatcher(
        JobRunStore(data_source),
        registry=build_default_job_registry(),   # 白名单，见 §7.2
    )
    _job_dispatcher.start()
```

约束：

1. **只以进程内 daemon 线程启动**。不得 `Start-Process python ...` 另起常驻进程——按项目铁律 L11，长驻服务必须走 `scripts/launch_detached.ps1`（WMI 脱离 job object），否则终端调用会被后代进程拖死数十分钟。
2. 未注册任何 handler 时 `start()` 仍会跑，但所有 run 都会以 `未注册的 handler` 失败。因此接入顺序必须是：**先 `build_default_job_registry()`，再打开开关**。
3. `JOB_DISPATCH_ENABLED=0` 时 `start()` 返回 `False`，不建线程、零开销。
4. 接入后 `tick` 单次耗时应 < 1s（`due=0` 场景）；超过 1s 视为 SQLite 锁竞争，按 §12 R1 处理。

---

## 7. Executor 插件接口（已实装）

实现文件：`meta/core/job_executor_registry.py`。原计划的 `meta/core/job_executor.py` 未创建；`JobExecutor(Protocol)` 改为鸭子类型 + `FunctionExecutor` 适配，注册表同时支持"普通函数"与"执行体对象"两种形态。

### 7.1 实际接口

```python
# meta/core/job_executor_registry.py

@dataclass
class JobContext:                 # dispatcher 构造，executor 只读
    run_id: int
    job_code: str
    params: dict
    attempt: int
    deadline_monotonic: float     # time.monotonic() + timeout
    cancel_event: threading.Event

@dataclass
class JobResult:                  # data → run.result；error → run.error
    success: bool
    data: dict = None
    error: str = None

class FunctionExecutor:           # 普通函数 → executor 形状
    def __init__(self, name, func, supports_cancel=True): ...
    def run(self, ctx): ...

class ExecutorRegistry:
    def register(self, executor_or_name, func=None, *, supports_cancel=True): ...
    def unregister(self, name) -> bool: ...
    def get(self, name): ...
    def names(self) -> list: ...
    def execute(self, name, ctx, timeout=None) -> JobResult: ...   # 永不抛异常
```

`execute()` 行为契约（`test_job_executor_registry.py` 已覆盖）：

1. **未注册** name → `JobResult(False, error='未注册的 handler: <name>')`，不抛异常。
2. **抛错**（含 `BaseException`）→ `JobResult(False, error='<类型>: <消息>')`。
3. **超时** → 只 `ctx.cancel_event.set()` 并立即返回 `JobResult(False, error='timeout after X.XXXs')`；**不强杀线程**（daemon 线程自生自灭）。
4. **返回值归一**：`JobResult` 原样；`None` → 成功空结果；`dict` → 成功且落 `result`；其他类型（str / int / bool…）→ **失败**（防静默成功）。
5. **执行前已取消** → 直接 `JobResult(False, error='cancelled')`。
6. 注册表**不加锁**：注册只在启动期发生、运行期只读。

能力边界：

1. executor **不得**自行 sleep 重试；重试由 dispatcher 按 `job_definitions.max_attempts` / `backoff_seconds` 决定。
2. executor 应响应 `cancel_event`（每 1s 至少检查一次）；不支持取消的执行体注册时传 `supports_cancel=False`。
3. executor 的异常由注册表统一转失败，**不得吞掉后返回成功**。
4. 参数进入 executor 前必须已脱敏（§12 R6）。

### 7.2 handler 白名单与参数校验（安全边界，必做）

`handler` 是定义表里的字符串，`params` 来自触发器或 API。**二者组合等于"任意函数调用"**，是本设计最大的攻击面，必须在接入生产前锁死：

| 约束 | 落地方式 |
|---|---|
| 白名单 | 只有启动期注册过的 name 可执行；未注册一律 `failed`（已实现） |
| 禁止反射 | 不得 `importlib.import_module` / `getattr(module, func)` 按 `handler` 解析；`handler` 不支持 `module:func` 形式 |
| 参数形状 | `params_schema`（JSON Schema）在下发前校验；无 schema 的定义必须显式存 `{"type":"object","additionalProperties":false}` |
| 键白名单 | 只透传 `params_schema.properties` 中声明的键；`params_override` 中多出的键丢弃并记 warn |
| 禁止字段 | 含 `handler` / `module` / `class` 或以 `__` 开头的键 → 直接拒绝 |
| 体积 | `params` 序列化后 > 16KB → 拒绝，避免账本写入放大 |

校验位置：dispatcher 的 `_execute_run` 之前，**不放进 executor**——executor 保持"只执行、不校验"，便于单测替换与复用。

### 7.3 `bo_action` handler 桥接（应用类作业）

目标：让"巡检"这类应用作业通过 schedule 一个 job 去调用某个 BO action，复用 `task_runs` 的账本 / 租约 / 重试，而不新增执行通道。

**单个内置 handler，不做一 action 一 handler**：

```python
params = {
  "action_id":   "inspection.run",   # 必填，bo_action_registry 的 canonical id
  "payload":     {"scope": "all"},   # 必填，object
  "permissions": ["*"],              # 可选，默认 ['*']（system 身份）
}
```

实现要点：

1. `action_id` 必须 `bo_action_registry.has(action_id)`，否则 `JobResult(False, error='未知 action_id: ...')`。
2. 直接调 `bo_action_registry.call(action_id, payload, context)`（**不走 HTTP 层**），`context = {'permissions': params['permissions'], 'user_id': None, 'source': 'job'}`；返回的 `{'success','data','message'}` 映射为 `JobResult`（`success=False` 时 `error=message`）。
3. 权限：固定 `system` 身份，默认 `['*']`；**禁止**把终端用户会话或 token 塞进 `params`（账本对所有有 `task_run:read` 的人可见，等于泄露）。
4. 超时：使用 dispatcher 传入的 `deadline_monotonic`；`bo_action_registry.call` 内部已有 action 级超时，桥接不再叠加。
5. 取消：registry 调用是同步的，**不支持中途取消**；桥接层只在**调用前**检查 `cancel_event`。即"取消 = 不再开始新的 action 调用"，UI 必须如实标注（见 §13 Q8）。
6. 幂等：同一 `(trigger_id, scheduled_for)` 由 `run_key` 唯一约束保证只调一次；action 自身幂等性由 `BusinessActionMeta.idempotent` 声明，桥接层不重复调用。
7. `record_mode`：巡检类默认 `all`（留证据链）；心跳类仍 `failure_only`。

> 为什么不复用 `meta/core/bo_action_executor.py` 的 `BOActionExecutor`：它绑定 Gen2 `tasks` 的 `task_id` 与三态（`completed` / `needs_review` / `awaiting_async`），与 `task_runs` 的"一次尝试"语义不同。桥接**只调 registry**，三态仍由 Gen2 任务域维护。

### 7.4 首个应用类作业示例：巡检

定义播种行（建议随 P3 一起，`status='disabled'` 待灰度）：

```json
{
  "code": "inspection_daily",
  "name": "每日巡检",
  "executor_type": "python",
  "handler": "bo_action",
  "params_schema": {
    "type": "object",
    "required": ["action_id", "payload"],
    "properties": {
      "action_id": {"const": "inspection.run"},
      "payload":   {"type": "object"}
    }
  },
  "default_params": {"action_id": "inspection.run", "payload": {"scope": "all"}},
  "timeout_seconds": 900,
  "max_attempts": 2,
  "backoff_seconds": 300,
  "record_mode": "all",
  "status": "disabled"
}
```

触发器：`trigger_type='cron'`、`cron_expr='0 2 * * *'`、`timezone='Asia/Shanghai'`、`enabled=0`。

验收路径：

1. `POST /api/v2/jobs/inspection_daily/run-now` → 生成 `manual:<uuid>` run；
2. 执行 → `succeeded`，`result` 内含巡检 action 的 `data`；
3. 重复 tick 同一 cron 边界 → 不产生第二条 run（`run_key` 兜底）；
4. 把 action 改为抛错 → run 进 `retrying`，第 2 次失败后 `dead`。

> 前置依赖：巡检本身必须已注册为 BO action（`inspection.run`）。本 spec 只提供调度与桥接，不实现巡检业务逻辑。

### 7.5 首批接入范围

| 优先级 | handler | 类型 | 说明 |
|---|---|---|---|
| 1 | `db_analyze` / `db_vacuum` / `db_integrity_check` / `db_checkpoint` | 运维 | 纯函数、幂等、失败无业务影响 |
| 2 | `audit_failure_retry` | 运维 | 自带重试语义，可验证 retry/dead 路径 |
| 3 | `bo_action` | 应用 | 巡检等只读 / 可重放作业；**首个业务侧接入点** |
| 暂缓 | `platform_tick` / `workflow_schedule` / `import_queue_processor` | — | 依赖其他子系统，或高频需 `failure_only` |

`async_audit_writer` 的进程内队列**本期不改**，待账本稳定后再评估是否收敛为 executor。

---

## 8. API

### 8.1 已实现（只读账本）

| 方法 | 路径 | 说明 | 权限 / 响应 |
|---|---|---|---|
| GET | `/api/v2/bo/task_run` | 账本列表（分页 / 排序 / 过滤由通用 BO 列表提供）| `task_run:read`；无权限 → 403 `GENERIC_API_FORBIDDEN` |
| GET | `/api/v2/bo/task_run/<id>` | 单条详情 | 同上 |
| GET | `/api/v1/task_run/...` | 旧版通用 BO 读路由 | 同上 |
| POST / PUT / DELETE | `/api/v2/bo/task_run...` | 写路径一律拒绝 | 404 `GENERIC_API_READ_ONLY` |
| POST / PUT / DELETE | `/api/v1/task_run/...` | 同上 | 404 `GENERIC_API_READ_ONLY` |

实现依据：

- `meta/schemas/task_run.yaml` 声明 `generic_api_mode: read_only`（`full` / `read_only` / `disabled` 三档，见 `meta/core/models.py::generic_api_mode_of`）。
- 写口子在 `meta/api/bo_api.py` / `meta/api/manage_api.py` 的 `before_request` 拦截，且仅对 `registry.get(object_type)` 命中的对象生效（避免误伤 `/api/v2/bo/architecture/...`）。
- 读权限由 `meta/services/auth_middleware.py::check_generic_read_permission` 判定：`before_request` 阶段 `g.current_user` 尚未写入（`login_required` 是视图装饰器），因此回落到自行验 token；未登录 / 坏 token 返回 `None`，交给 `login_required` 统一 401。
- **只读 ≠ 免鉴权**：`task_runs` 含 `params` / `result` / `error`，只读档位只解决"不能写"，不解决"谁能读"，因此必须有对象级 `task_run:read`。

界面：`/system/task-runs`（`object_list` → `GenericObjectList` → `MetaListPage`），菜单由 `meta/scripts/init_task_menus.py` 播种，`required_permissions=['*']`。

### 8.2 待实现（写接口与专用查询）

| 方法 | 路径 | 说明 | 门控 |
|---|---|---|---|
| GET | `/api/v2/jobs/definitions` | 定义列表 | `task_run:read` |
| GET | `/api/v2/jobs/triggers` | 触发器列表（含 `next_run_at`）| `task_run:read` |
| GET | `/api/v2/jobs/runs?job_code=&status=&limit=` | 账本分页（比通用 BO 多 `job_code` 过滤）| `task_run:read` |
| GET | `/api/v2/jobs/runs/<id>` | 单条详情（含 `result` / `error`）| `task_run:read` |
| POST | `/api/v2/jobs/runs/<id>/retry` | 人工重试（`dead`/`failed` → `pending`，`attempt+1`）| `job_admin` |
| POST | `/api/v2/jobs/runs/<id>/cancel` | 人工取消（置 `cancel_event`；进行中的 action 不中断，见 §7.3）| `job_admin` |
| POST | `/api/v2/jobs/<code>/run-now` | 手动运行（`run_key='manual:<uuid>'`）| `job_admin` |
| POST / PUT / DELETE | `/api/v2/jobs/definitions[/<id>]` | 定义 CRUD（`handler` 必须在白名单内）| `job_admin` |
| POST / PUT / DELETE | `/api/v2/jobs/triggers[/<id>]` | 触发器 CRUD（`next_run_at` 由服务端计算）| `job_admin` |

- **不定义 `task_run:write`**：账本 schema 是 `read_only`，本就不生成写动作；所有写口子收敛到新增功能权限 `job_admin`（暂只授管理员），避免借通用 BO 写路径绕过状态机。
- 写接口**不得**直接改 `status` / `attempt` / `run_key` / `worker_id`：迁移只能通过 `JobRunStore` 的方法完成。
- 响应字段 `snake_case`，与 `task_inbox_api` 一致。
- run 详情的 `params` 默认只回键名摘要，`?include_params=1` 才返回脱敏值（§12 R6）。
- 沿用 `scheduler_bp` 的"状态类接口无条件、写接口门控"惯例；既有差异已在 `task-two-generation-convergence/spec.md` §2.2 登记。

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

**实现状态（2026-11-10）**

| 阶段 | 代码 | 测试 | 生产接线 |
|---|---|---|---|
| P0 账本 | `meta/core/job_run_store.py` + v246 三表 | `test_job_run_store.py` 19 条 | 表已建 |
| P1 触发器 | `meta/core/job_dispatcher.py`（建 run / 推进 / `DRY_RUN`）| `test_job_dispatcher.py` 11 条 | 已接入 `meta/server.py`（`JOB_DISPATCH_ENABLED` 默认 0） |
| P2 claim/lease/执行 | 同上 + `meta/core/job_executor_registry.py` + `meta/handlers/job_handlers.py` | `test_job_executor_registry.py` 14 条 + `test_job_handlers.py` 8 条 | 已注册 5 个运维 handler + `bo_action`；`executor_pool` 未传 → tick 线程内联执行 |
| 横切：参数校验 | `meta/core/job_params.py`（§7.2）| `test_job_params.py` 12 条 | dispatcher claim 前执行；v247 为 v246 播种定义补空 schema |
| 横切：写接口 | `meta/api/job_admin_api.py`（`run-now` / `retry` / `cancel`）| `test_job_admin_api.py` 9 条 | 蓝图已注册；权限 `job_admin` |
| 横切：只读账本 | `task_run.yaml`、`generic_api_mode`、`/system/task-runs`、`task_run:read` | `test_generic_api_mode.py` 19 条 | 菜单已播种；页面未真机验证 |

### 10.1 待建清单（按依赖顺序）

1. ✅ `build_default_job_registry()`（§7.5 优先级 1-2）：`meta/handlers/job_handlers.py`，注册 5 个运维 handler。
2. ✅ `bo_action` 桥接 handler（§7.3）：`make_bo_action_executor()`，是应用类作业能力的唯一入口。
3. ✅ §7.2 白名单 + `params_schema` 校验：`meta/core/job_params.py`，已与第 1、2 项同批上线。
4. ✅ dispatcher 接入 `meta/server.py`（§6.6）：`JOB_DISPATCH_ENABLED` 默认 0，灰度启动。
5. ✅ 写接口：`run-now`（最短闭环验收）+ `retry` / `cancel`（§8.2），见 `meta/api/job_admin_api.py`。
6. ⬜ 定义 / 触发器管理面：API → 脚本播种 → UI（UI 可延后，先用 SQL / 脚本）。
7. ⬜ **P4 治理补强（对标 ESS，§16）**：`blocked` 非终态 + 并发组释放回 `pending`（不再落 `skipped`）；`job_definitions.required_permissions`（按定义授权 run-now）；`task_runs` 输出件与 `dead` 告警。Job Set / DAG 依赖、Work Assignment 资源域**明确不做**。

**阶段硬门禁**：进入下一阶段前，上一阶段验收标准必须连续通过，且 `python d:\filework\test.py --failed` 无新增失败；打开 `JOB_DISPATCH_ENABLED` 前必须完成第 1-3 项。

---

## 11. 测试计划

新增测试（`meta/tests/`）：

| 文件 | 覆盖 |
|---|---|
| `test_job_run_store.py` | 状态迁移矩阵、`run_key` 幂等、`attempt` 上限入 `dead`、租约回收、人工 retry/cancel |
| `test_job_dispatcher.py` | 假时钟下"一个 due trigger 只建一个 run"、并发 claim 唯一成功、`DRY_RUN` 不执行、触发器乐观推进不重复 |
| `test_job_executor_registry.py` | 注册/查找、异常转 `failed`、超时转 `failed`、`cancel_event` 生效 |
| `test_generic_api_mode.py` | `generic_api_mode` 三档归一、方法矩阵、`task_run.yaml` 只读声明、read_only 读权限 403 / 管理员放行、写路径仍 404 |

运行命令：

```powershell
python d:\filework\test.py --single meta/tests/test_job_run_store.py
python d:\filework\test.py --single meta/tests/test_job_dispatcher.py
python d:\filework\test.py --single meta/tests/test_job_executor_registry.py
python d:\filework\test.py --single meta/tests/test_generic_api_mode.py
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
| R9 | `handler` + `params` 组合构成任意函数调用（RCE 面）| 白名单注册 + 禁反射解析 + `params_schema` 校验 + 键白名单 + 禁止字段（§7.2） |
| R10 | 调度器另起进程会拖死终端（项目铁律 L11）| 只作为后端进程内 daemon 线程；禁止 `Start-Process python ...`；长驻服务一律 `scripts/launch_detached.ps1` |
| R11 | 只读账本被当成免鉴权（`params` / `result` / `error` 泄露）| `generic_api_mode: read_only` + 对象级 `task_run:read` + 写路径 404；**菜单隐藏不作为安全边界**（§8.1） |
| R12 | 开了调度但没注册 handler → 全量 run 以"未注册的 handler"失败刷屏 | 接入顺序硬约束：先注册再开开关（§6.6）；开启前先用 `DRY_RUN` 预演 |
| R13 | tick 长时间停摆（服务停机数小时）后集中补跑，导致瞬时堆积 | `next_run_at` 推进以"当前时刻之后的下一次"为准，**只补最近一次**，不追补全部遗漏（§13 Q11）；运维作业自身须幂等 |

---

## 13. 开放问题（需批准）

| ID | 问题 | 建议默认 |
|---|---|---|
| Q1 | 成功 run 保留期 | 30 天，环境变量可调；`dead` 永久保留至人工清理 |
| Q2 | `platform_tick` 是否纳入触发器 | 纳入，但 `record_mode='failure_only'` |
| Q3 | 取消语义强度 | Python executor 协作式取消；HTTP executor 仅标记 `cancel_requested`，不强制中断 |
| Q4 | 是否支持跨进程 / 跨机 worker | 本期只支持单进程多线程；lease 字段为未来多进程预留 |
| Q5 | 是否允许业务代码直接提交 run | P4 前不允许；`async_import_service` 等维持现状 |
| Q6 | `bo_action` 作业的权限主体 | 固定 `system`（`permissions=['*']`）；若需最小权限，后续在 `job_definitions` 增加 `run_as_permissions`，本期不做 |
| Q7 | 巡检失败是否阻断后续批次 | 不阻断；失败入 `retrying` → `dead`，由 `/system/task-runs` 人工 retry |
| Q8 | 取消对进行中 `bo_action` 的效力 | 仅"不再开始新调用"，不中断已开始的 action；UI 必须明示（§7.3） |
| Q9 | 定义 / 触发器是否允许业务方自助编辑 | 本期只授 `job_admin`（管理员）；自助编辑需先有 handler 白名单审计 + 变更日志 |
| Q10 | 权限是否按 ESS 拆三层（提交 / 监控 / 管理） | 本期不拆：读 = `task_run:read`，写 = `job_admin`；P4 视使用情况再拆 `job_submit` / `job_monitor`，并按 `job_definitions.required_permissions` 授权 run-now |
| Q11 | 错过多次 cron 的补偿策略 | 只补最近一次（ESS 按计划时间逐次补跑，本部署不采纳，避免停机后集中爆发）|

---

## 14. 范围外

1. `task_executions` 历史数据归档 / 删除。
2. `task_events` 与 `task_runs` 的桥接写入（保持双轨，直至 Gen2 编排域重构）。
3. `async_audit_writer` 进程内队列的收敛（P2 评估，不在本 spec 承诺）。
4. 跨机 worker 与分布式锁。
5. 前端任务中心改造：本期只有账本只读页（`/system/task-runs`）；定义 / 触发器管理 UI 不在范围。
6. 巡检等应用作业的业务实现（`inspection.run` action 本身）；本 spec 只提供调度与桥接。

---

## 15. 验证命令

```powershell
# 迁移可执行 + 幂等（重复跑不报错）
python d:\filework\test.py --single meta/tests/test_migration_runner.py

# 新增测试
python d:\filework\test.py --single meta/tests/test_job_run_store.py
python d:\filework\test.py --single meta/tests/test_job_dispatcher.py
python d:\filework\test.py --single meta/tests/test_job_executor_registry.py
python d:\filework\test.py --single meta/tests/test_generic_api_mode.py

# 回归（相邻域）
python d:\filework\test.py --single meta/tests/test_task_scheduler.py
python d:\filework\test.py --single meta/tests/test_task_inbox_api.py

# 只读账本接口（服务已启动）：有 task_run:read → 200；无权限 → 403
curl.exe -s -o NUL -w "%{http_code}" -b cookies.txt http://localhost:3011/api/v2/bo/task_run
# 写路径必须 404（GENERIC_API_READ_ONLY）
curl.exe -s -X POST -b cookies.txt http://localhost:3011/api/v2/bo/task_run

# 测试规范自查
python scripts/lint_tests.py
```

---

## 16. 对标 Oracle Fusion ESS（采纳 / 调整 / 不做）

> 研究底稿：`d:\filework\fusion-task-research-2026-11-10.html`（ESS 五对象模型、生命周期、三入口、三层治理、横向对比）。
> ESS 是商业 ERP 跨 Pillar 的批处理底座，目标是「可控 / 可审计 / 可治理」；本 spec 目标是「单机 SQLite 上把账本 + 调度 + 执行接通」。
> 因此本节只做**语义对齐**，不复制其体量。

### 16.1 对照表

| ESS 能力 | ESS 语义 | 本 spec 现状 | 取舍 |
|---|---|---|---|
| Job Definition | 作业包 + 作业名 + 参数定义；Oracle 预置由 Oracle 维护，自定义由客户维护 | `job_definitions`（种子 + 管理员维护）| 采纳「定义不承载状态」；维持 Q9 只授 `job_admin` |
| Job Set | 多作业串行 / 依赖，官方建议单集 ≤ 20 | 无 | **不做**（P4+）：单机用「A 成功后 run-now B」足够，DAG 会显著扩大状态机 |
| Schedule | 一次性 / 重复 cron / 触发式 | `job_triggers`（cron / interval / manual / event 预留）| 已对齐 |
| Process 实例 | 每次提交生成实例，参数快照 + 状态 + 日志 | `task_runs`（`run_key` 幂等 + `params` 快照）| 已对齐；**不引入父子层级** |
| Incompatibility | 冲突时后到者 **Blocked**，自动恢复 | 并发组占用落 `skipped`（终态）| **调整**：新增 `blocked` 非终态（P4），`skipped` 收窄为 `DRY_RUN` / `record_mode` |
| Work Assignment | 线程池资源域，关键作业预留 | 共享 `TaskQueueManager` 池 | **不做**：单机线程数固定，`concurrency_group` 已覆盖互斥需求 |
| Hold | 提交时挂起，等人工放行 | `job_triggers.enabled=0` / 定义 `status='disabled'` | 采纳等价物，**不新增状态** |
| Paused | 给自动触发的进程让路 | 无 | **不做**（无抢占场景）|
| Cancel / Cancelling | 请求取消 → 尽力停止 | 协作式 `cancel`，只有终态 `cancelled` | 采纳；不新增 `cancelling` 中间态（Q8）|
| Error Auto-Retry / Retrying | 按计划自动重跑，次数由作业配置决定，用尽后 Error | `failed` → `retrying`（`backoff_seconds`）→ `dead` | 已对齐；术语映射：`retrying` ≈ Auto-Retry，`dead` ≈ Manual Recovery |
| Error Manual Recovery | 需管理员介入重新提交 | `job_admin` 调 `retry`（`attempt+1`）| 已对齐 |
| Expired | 未运行且计划已结束，可重新提交 | 不建 run | **不采纳**：不产生「应跑未跑」的残留记录 |
| Warning | 终态但需人工关注 | `succeeded` 无警告含义 | **调整**：不新增状态，允许 `result` 内带 `warning` 标志（P4）|
| 中断自动续跑 | 进程中断后从中断处继续 | 租约过期回收 → `retrying`（整次重跑）| **不采纳断点续跑**：只保证不悬挂，重跑正确性由 handler 幂等承担 |
| 按 job definition 的提交权限 + ESSMonitor / ESSOperator / `ESS_REQUEST_HISTORY` | 提交与监控分权 | `task_run:read`（看）+ `job_admin`（改）| **暂不拆**（Q10）；`required_permissions` 列入 P4 |
| Submit / Cancel / Hold / Resume / Resubmit / View Log / View Output | 管理面七动作 | `run-now` / `retry` / `cancel`；无输出件 | Hold/Resume 已由触发器开关覆盖；输出件列入 P4 |
| 两层监控（自带页面 + 日志外流）| 自带页面偏人工，生产接 OCI Logging Analytics | 只读账本页 + `dead` 告警 | 采纳「账本 + 告警」，**不做**外流（复用现有日志 / 审计体系）|

### 16.2 三条结构性结论

1. **四层分离成立，骨架不改。** ESS 用 5 个对象表达「定义 / 调度 / 账本 / 载体」，我们用 3 张表 + 1 个 dispatcher；差异只在 Job Set 与 Work Assignment，属于 P4+ 的编排与资源治理，不影响当前骨架。
2. **必须尊重「状态是开放集合」。** 本次最实质的修正就是 `blocked`：它**非终态**，必须由 dispatcher 每 tick 复查并在组释放后回 `pending`，不能像 `skipped` 一样终态化。
3. **ESS 的能力边界是「治理」，不是「执行」。** 它不替作业解决幂等与事务语义；我们同样把幂等责任留在 handler（§7.4 的 `run_key` + action 幂等），不在 dispatcher 内做业务级去重。

### 16.3 本次回灌的修订点

| 位置 | 修订 |
|---|---|
| §5 状态机 | 新增 `blocked`（P4 预留，非终态）；`skipped` 职责收窄 |
| §10.1 | 新增第 7 项 P4 治理补强（`blocked` 回收、`required_permissions`、输出件与 `dead` 告警）|
| §12 | 新增 R13（tick 长停摆后的补跑策略）|
| §13 | 新增 Q10（权限是否拆分）、Q11（错过补偿策略）|

> 本次只改文档：未改代码、未提交；§1.1 的实装状态不变（`blocked` 等仍为 P4 预留）。