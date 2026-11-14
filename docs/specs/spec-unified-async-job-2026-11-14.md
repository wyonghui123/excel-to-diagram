# Spec: 统一异步任务体系（复用 task_runs / JobDispatcher / job_triggers）

> 版本：v1.4（2026-11-14）
> 关联：
> - `docs/specs/spec-background-job-infrastructure-2026-11-10.md`（v246 三表与状态机来源）
> - `docs/specs/spec-message-platform-change-event-2026-11-14.md`（v2.1，P1-d 已完成）
> 定位：**收敛，不新建体系**。把已有的 5 套调度设施 + 2 套任务账本收敛为「1 个执行账本 + 1 个触发源抽象 + 1 条通知路径」。
>
> v1.1 增量（本轮）：补齐「作业中心」的**管理面**——作业定义、参数驱动的手动运行、一次性定时、周期触发器管理、运行记录中心 UI。新增 FR-014~FR-020 / NFR-006~007 / IF-007~IF-012 / TR-005 / 第 11 章竞品参考 / 第 12 章实现契约。
> 现状基线（2026-11-14 核对）：`job_admin_api` 只有 runs 列表+详情+run-now+retry+cancel；`job_definitions`/`job_triggers` **无 CRUD 接口**；`due_triggers` 仅识别 `cron|interval`；前端**无 `/system/task-runs` 路由**（后端 `links.detail` 为死链）。
>
> v1.2 增量（本轮「元数据驱动 + 单一事实」复审）：① once 完成改用新增原子方法 `complete_once_trigger`（`advance_trigger` 传 `None` 必然失败）；② 参数校验复用既有 `job_params` 规则，不新增第二套实现；③ `progress` 由账本层 `_decode` 统一解析、投影层透传；④ 补 paused 的调度侧记账语义；⑤ 区分「once 自然完成软删除」与「DELETE 物理删除」；⑥ `concurrency_group` / `record_mode` / `timezone` 标为无消费方的只读字段；⑦ 一次性定时唯一路径（`run-now.scheduled_for` 收紧为 ±60s 容差）；⑧ 新增 §2.1 事实来源与优先级清单。
>
> v1.3 增量（本轮 SAP 对标复核）：① §11.1 增加 SAP S/4HANA Application Jobs / SM36-SM37、SAP BTP Job Scheduler 两行对照，§11.2/§11.3 补采纳与不采纳结论；② 确认 `job_triggers.event_name` 与 `timezone` 同属**无消费方列**，本期不支持事件触发（§2.1）；③ §10 为全部 TBD 补「建议」结论，其中 TBD-6 / TBD-9 / TBD-10 给出可直接拍板的方案。
>
> v1.4 增量（前端实现方案细化）：① §12.2 重写为「组件复用 + 参数元数据驱动」实现方案，结论是**不新增 job 专属 UI pattern 组件**；② 新增 3 个纯函数适配器（`jobParams.schemaToFields` / `jobRunStatus` / `jobService`）与 1 处通用组件微扩展（`MetaForm` 增加 `password` 类型）；③ IF-002 追加 `capabilities`、IF-011 追加 `meta{filters}`，UI 的能力位与筛选项一律由后端下发（§2.1 新增对应事实行）；④ §12.5 增加「无 job 专属组件」取证项。

## 1. 背景与目标

### 1.1 背景

v246 迁移已经建好 `job_definitions` / `job_triggers` / `task_runs` 三表，并播种 10 条作业定义，但触发器 `enabled=0`、`JOB_DISPATCH_ENABLED` 默认 `0`，处于「已建能力、未接线」状态。与此同时，系统里存在以下重复设施：

| 设施 | 现状 | 问题 |
|---|---|---|
| `TaskScheduler` | 空转 | 冗余 |
| `MaintenanceScheduler` | 8 个运维作业的 cron 循环 | 自实现 cron/统计，与 `job_triggers` 语义重复 |
| `PlatformScheduler` | `platform_tick` | 同上 |
| `WorkflowScheduleScheduler` | 工作流动态触发器 | 同上 |
| `ChangeEventWorker` | 事件轮询投递 | 职责清晰，保留 |
| 批量导入 `/import/async` | daemon 线程 + 内存字典 `_import_tasks` | 重启即丢、无法跨实例查询、逐行发事件造成通知风暴 |

用户诉求：**一次建好、四种模式共用**——前台同步、前台发起后异步、后台/排队、定时；任务完成后结果必须能取到。

### 1.2 业务目标

- BO-1：任何长耗时操作（导入、导出、重算、归档）都有统一的「发起 → 进度 → 结果 → 通知」闭环。
- BO-2：消除「进程重启后任务状态丢失」和无界通知风暴。
- BO-3：不再新增第 6 套调度/任务机制，现有设施只做归位。

### 1.3 涉众目标

- UO-1（业务用户）：点击后立刻有反馈，离开页面再回来仍能看到进度与结果。
- UO-2（管理员/运维）：一个入口查看全部作业执行记录、失败原因、重试与取消。
- UO-3（开发者）：接入新异步能力只需「定义一条 job + 实现一个 handler」，不用碰调度、不用碰通知。

## 2. 需求类型总览

| 类型 | 适用 | 依据 |
|---|---|---|
| 业务需求 | 是 | 第 1 章 |
| 用户/涉众需求 | 是 | 第 1.3 节 |
| 解决方案需求 | 是 | 第 9 章 RFC |
| 功能需求 | 是 | 第 3 章 FR-001 ~ FR-020 |
| 非功能需求 | 是 | 第 4 章 NFR-001 ~ NFR-007 |
| 外部接口需求 | 是 | 第 5 章 IF-001 ~ IF-012 |
| 过渡需求 | 是 | 第 6 章 TR-001 ~ TR-005 |

### 2.1 事实来源与优先级（单一事实清单）

> v1.2 复审结论：本体系只允许一个权威来源；凡可在运行期推导的值，一律**派生不落库**，禁止在 DB / 后端投影 / 前端各存一份。

| 事实 | 唯一来源 | 派生方式 / 禁止事项 |
|---|---|---|
| 作业可执行体 | 代码 `ExecutorRegistry` 白名单（按 `job_definitions.handler` 名匹配） | DB 只存 handler 名，不存模块/类路径；不在白名单 → `available=false`，**不写入 DB 状态列** |
| 作业运营参数 | `job_definitions` 行 | 前端 PATCH 只改白名单字段；`params_schema` / `handler` / `executor_type` 只读，禁止通过接口注册任意 handler |
| 触发计划 | `job_triggers.next_run_at`（epoch 秒，UTC） | once 与 cron/interval 共用该列，不新增 `schedule_type` / `run_at` 列；`timezone` 列仅展示（**当前不参与推算**，见下「时区语义」），落库始终 epoch |
| 触发/运行来源 | `task_runs.run_key` 前缀（`manual:` / `import:` / `<trigger_id>:<scheduled_for>`） | 派生优先级固定为：① `import:` → `import`；② `<digits>:<digits>` → 查 `job_triggers.trigger_type`（`cron|interval|once`）；③ trigger 已被物理删除 → `scheduled`（类型不可考，不猜测）；④ `manual:` → `manual`（UI 与 API 手动触发同义，**不设 `api` 值**）。DB 不新增 `source` 列，前端不做二次推导 |
| run 状态 | `job_run_store.RUN_STATUSES`（后端唯一字典） | 前端只做「状态 → 文案/颜色」映射，不得新增状态值；`TERMINAL_STATUSES` 用于终态停轮询 |
| 进度 | `task_runs.progress`（JSON） | 由 `JobRunStore._decode` 在 `get_run` / `list_runs` 统一解析为对象，投影层**透传**；前端不解析字符串；未写入为 `null`（表示不确定进度） |
| 最终结果 | `task_runs.result` / `error` / `duration_ms` | 只由 `finish()` 写终态；`progress` 不承担终态语义 |
| 参数生效链 | `default_params` ⊕ `trigger.params_override` ⊕ `request.params` | 唯一合并函数 `merge_job_params`；唯一校验函数 `sanitize_params`；**快照写入** `task_runs.params` 后，run 执行不再回读定义 |
| 尝试上限 | `task_runs.max_attempts`（创建时从定义快照） | 定义后续修改**不回溯**历史 run；`attempt` 只由账本递增 |
| 可供运行判定 | 派生：`available ∧ status=='active'` | `run-now` 的 409/400 判定统一走同一判定函数，避免前端与后端各写一套 |
| UI 能力位与筛选枚举（v1.4） | 后端投影 `capabilities`（IF-002）+ `meta.filters`（IF-011） | 前端只做「值 → 文案/颜色」映射；**禁止**前端硬编码状态集合、终态判断、按钮可用性推导 |

已接受限制（显式声明，不扩散）：

- `timeout_seconds` / `backoff_seconds` **未快照**到 run：定义修改后，历史 run 的「超时/退避口径」按当前定义解释。改写快照需 DDL，本期不做，记入 TBD-9。（`concurrency_group` 当前无消费方，见 FR-014 预留字段。）
- `last_run` / `next_run` 摘要 MUST 由**单次聚合查询**产出（`LEFT JOIN` 或子查询），禁止前端逐作业请求（N+1）。
- **校验时机（同规则、两处入口）**：手动运行在**入库前**校验（返回 `400 invalid_params`，不落 run）；触发器路径在**领取前**校验（已落 run 后置 `dead`）。两处 MUST 调用同一实现，不得各写一套规则。
- **空 schema 语义**：`params_schema` 为 NULL/空时，`sanitize_params` 会丢弃**所有键**（仅记 warning，不报错）。因此前端在无 schema 时不渲染参数表单；有 schema 时只渲染声明的 property，避免「提交了却没生效」的错觉。
- **时区语义（v1.2）**：`job_triggers.timezone` 列**当前无消费方**，`CronParser` 不接受时区参数，`next_run_at` 按**进程本地时区**推算；`Asia/Shanghai` 是部署约束而非字段保证。触发器表单因此只展示该列（只读），cron 预览与调度 MUST 同源（同一进程时区），不得前端自算。
- **事件触发未接线（v1.3）**：`job_triggers.event_name` 同样**无任何消费方**（`meta/core/job_*.py` 零引用，`due_triggers` 只认 `cron|interval|once`）。本期明确**不支持**事件驱动触发（对标 SAP SM62/SM64「after event」能力），触发器表单不得暴露该字段——否则会形成「看起来能配、实际不生效」的第二个触发事实源。

## 3. 功能需求

### FR-001: 唯一执行账本

- **描述**：系统所有「机器执行的后台/异步作业」MUST 在 `task_runs` 落账，不得再使用进程内字典或另建表记录执行状态。
- **验收标准**：
  - 任一异步作业发起后，`task_runs` 存在对应行，含 `run_key`、`job_id`、`status`、`params`、`scheduled_for`。
  - 进程重启后，未完成 run 仍可被查询到（`status` ∈ `pending/claimed/running`）。
  - 代码中不再新增 `_xxx_tasks: Dict` 类型的执行状态容器。
- **优先级**：Must
- **类型映射**：解决方案 / 功能

### FR-002: 四种运行模式共用同一入口

- **描述**：系统 MUST 支持 M1 前台同步、M2 前台发起异步、M3 后台/排队、M4 定时四种模式，且 M2/M3/M4 共用 `POST /api/v2/jobs/{code}/run-now` 与同一账本。
- **验收标准**：
  - M1：耗时 < 阈值（默认 2s）的操作在请求内完成，不产生 `task_runs` 行（或按 `record_mode=failure_only` 仅失败记账）。
  - M2：接口返回 `202 + run_id`，请求线程不等待执行完成。
  - M3：服务端调用同一入口，`params` 中无 UI 上下文仍可执行。
  - M4：`job_triggers.enabled=1` 且 `next_run_at` 到期时，由 dispatcher 建 run 并执行。
  - 四种模式的 run 记录字段结构完全一致。
- **优先级**：Must
- **类型映射**：解决方案

### FR-003: 统一结果查询

- **描述**：系统 MUST 提供按 run 查询与列表查询，返回状态、进度、结果、错误、关联链接。
- **验收标准**：
  - `GET /api/v2/jobs/runs/{run_id}` 返回 `status / progress / result / error / duration_ms / created_at / links`。
  - `GET /api/v2/jobs/runs?job_code=&status=&page=` 支持分页与筛选。
  - 完成态（`succeeded/failed/cancelled/skipped/dead`）的 `result` 或 `error` 至少一个非空（`skipped` 除外）。
- **优先级**：Must

### FR-004: 进度上报

- **描述**：`task_runs` MUST 支持写入结构化进度，供前端展示。
- **验收标准**：
  - 新增单列 `progress TEXT`，内容为 JSON：`{current, total, percent, stage, message}`，允许部分字段缺省。
  - handler 可通过 `JobRunStore.update_progress(run_id, payload)` 更新，写入频率受节流限制（默认 ≥1s/次）。
  - 未提供进度的作业，`progress` 为 `NULL`，前端显示不确定进度。
- **优先级**：Must

### FR-005: 取消与重试

- **描述**：系统 MUST 支持对 run 的取消与重试，语义为协作式。
- **验收标准**：
  - `POST /api/v2/jobs/runs/{id}/cancel`：`pending` 直接置 `cancelled`；`claimed/running` 置取消标记，handler 在下个检查点退出并置 `cancelled`。
  - `POST /api/v2/jobs/runs/{id}/retry`：仅 `failed/dead/cancelled` 可重试，重试产生 `attempt+1` 且保留原 `run_key` 语义。
  - 取消后不再产生完成事件以外的通知。
- **优先级**：Must

### FR-006: 批量导入接入异步作业

- **描述**：`POST /import/async` MUST 改为创建 `import_cascade` 作业 run，执行体复用现有 `import_cascade` 逻辑。
- **验收标准**：
  - 接口返回 `202 + {import_id, run_id}`，两者一一对应。
  - 执行中每 N 行（默认 200）更新一次 `progress`。
  - 完成时 `result` 含 `{created, updated, failed, skipped, errors[], errors_truncated}`。
  - `errors[]` 的截断口径与现状一致：**每个对象类型最多 200 条**（`import_export_service` 现有上限），全局再设 2000 条硬上限；超限时 `errors_truncated=true`，并给出 `result_download_url` 供下载完整明细。
  - `result.errors` 的条目结构 MUST 与现状一致（`{object_type, row, field, message, ...}`），前端按 `object_type` 过滤展示不受影响。
  - 失败可重试，重试不重复写入已成功的行（依赖业务幂等键）。
- **优先级**：Must

### FR-007: 导入状态接口兼容

- **描述**：`GET /import/status/<import_id>` MUST 保持现有响应结构不变，内部数据源切换为 `task_runs`。
- **验收标准**：
  - 响应 JSON 字段名、层级与切换前完全一致。
  - 进程重启后该接口仍返回正确状态。
  - 兼容层可通过开关 `IMPORT_USE_JOB_LEDGER` 回退到旧实现。
- **优先级**：Must

### FR-008: 逐行事件抑制与汇总投递

- **描述**：批量导入产生的 `change_events` MUST 支持按批次聚合投递，事实行不删除。
- **验收标准**：
  - 导入期间写入的事件 `idempotency_key` 统一为 `job:<run_id>:<seq>`。
  - 开关 `change_notification.batch_summary=false`（默认）时行为与现状完全一致。
  - 开关为 `true` 时，同 `job:<run_id>:` 前缀的事件合并为 1 条投递，正文含成功/失败计数与失败样例。
  - `change_events` 表内事件条数不因聚合而减少。
- **优先级**：Should

### FR-009: 完成通知统一走事件出口

- **描述**：作业完成 MUST 通过写入 1 条 `change_event` 触发通知，不得直接调用 webhook/IM 发送。
- **验收标准**：
  - run 进入终态后，产生事件 `event_type=job_succeeded|job_failed`（或复用 `state_changed` 并带 `object_type=job_run`）。
  - 该事件经 `ChangeEventWorker` 投递到已配置通道，与现有通道限速/重试逻辑一致。
  - 站内收件箱可见该通知，并可深链到 `/system/task-runs?run=<id>`。
- **优先级**：Must

### FR-010: 定时与后台作业接入

- **描述**：`MaintenanceScheduler` / `PlatformScheduler` 的作业 MUST 能通过 `job_triggers` 到期触发，执行体复用同一 handler 注册表。
- **验收标准**：
  - 打开某条触发器（`enabled=1`）后，到点产生 run 并执行。
  - `JOB_DISPATCH_DRY_RUN=1` 时只记账不执行，可用于与旧调度做次数比对。
  - 关闭该触发器后，旧调度路径行为不变。
- **优先级**：Should

### FR-011: 任务中心只读视图

- **描述**：`/system/task-runs` MUST 展示进度、状态投影、耗时、错误摘要，并提供取消/重试入口。
- **验收标准**：
  - 列表新增 `progress` 列（百分比 + 阶段），`status` 按 6 个投影状态显示。
  - 详情抽屉展示 `params/result/error` 与关联对象深链。
  - 取消/重试按钮的可见性由 run 状态决定。
- **v1.1 关系**：FR-011 为最小只读要求（Could）；页面级完整能力（筛选、深链、轮询纪律、来源列）以 **FR-016（Must）** 为准，二者不冲突。
- **优先级**：Could

### FR-012: 调度设施收敛

- **描述**：`MaintenanceScheduler` / `PlatformScheduler` MUST 降级为触发源，`TaskScheduler` MUST 移除。
- **验收标准**：
  - `TaskScheduler` 无任何调用点且文件删除。
  - 两个调度器保留启动/停止接口，但执行逻辑委托 dispatcher；开关 `SCHEDULER_MODE=legacy|dispatcher`。
  - `WorkflowScheduleScheduler` 本期只做「触发器行维护」，执行仍走 legacy（延后至 P5）。
- **优先级**：Could

### FR-013: 导入对话框交互兼容

- **描述**：现有「校验 → 导入中 → 结果」三步对话框交互 MUST 保持不变，仅新增可恢复能力。
- **验收标准**：
  - 默认路径不变：提交后仍在对话框内展示进度条，完成自动进入结果步（第 4 步），不跳转任务中心。
  - 校验报错（第 2 步预览）继续走同步 `/import/preview`，不经过任务账本。
  - 「导入中」步骤也允许最小化为右下角浮卡（现状仅第 1/3 步可最小化）。
  - 浮卡恢复、页面刷新、服务重启后，前端可通过 `run_id` 重新拉取 `GET /api/v2/jobs/runs/{id}` 恢复进度与结果。
  - 进入终态后 MUST 停止轮询；轮询失败不得无限重试（现状 404 会每秒重试且不终止）。
- **优先级**：Should

### FR-014: 作业定义管理（只读 + 有限编辑）

- **描述**：作业定义 MUST 保持「代码注册表 + DB 行」双源，前端只允许编辑**运营参数**，不允许通过接口注册任意 handler。
- **可编辑字段**：`name` / `description` / `timeout_seconds` / `max_attempts` / `backoff_seconds` / `status(active|paused)` / `default_params`（须过 `params_schema` 校验）。这三项时序参数的实际消费点已核对：`timeout_seconds` 在执行时读取、`backoff_seconds` 在重试时读取（均不回读历史快照，见 TBD-9）、`max_attempts` 在创建 run 时快照。
- **只读字段**：`code` / `executor_type` / `handler` / `params_schema`。新增作业只能改代码 + 迁移播种。
- **预留字段（只读，v1.2）**：`concurrency_group` / `record_mode` 当前**均无消费方**（全库仅定义与读写，无并发闸门、无记账开关逻辑），M5 只展示不编辑——避免给用户「可限流 / 可关闭记账」的假象。是否启用 enforcement 记入 TBD-7。
- **验收标准**：
  - `PATCH /api/v2/jobs/{code}` 只接受上述可编辑字段，出现未知或只读字段 → `400 invalid_field`。
  - 修改后**不重启**即可在下一次 dispatcher tick 生效（每次 tick 重新读 `job_definitions`）。
  - `status=paused` 时 `run-now` 返回 `409 job_paused`；已有 `pending` run 不被暂停自动取消。
  - `handler` 不在 `ExecutorRegistry.names()` 白名单 → 投影 `available=false`，`run-now` 返回 `409 job_unavailable`（**判定只写在投影/接口一处**，前端不重复推导「哪些作业能跑」）。
  - paused 的**调度侧**语义（与代码事实对齐）：到期触发器仍会建 run，随后由 `_dispatch_pending` 置 `skipped(job_inactive)` 记账、**不执行**。即 paused 期间会产生一条 `skipped` 历史行，属于有意留痕，不是重复执行。

### FR-015: 参数驱动的手动运行

- **描述**：手动运行 MUST 按 `params_schema` 校验并支持前端表单渲染，替代当前「只能提交原始 JSON」。
- **校验唯一性（v1.2）**：MUST 复用 `job_params` 的既有校验规则（白名单丢弃 + `required`/`type`/`const`/`enum` + 16KB + 禁止键），**禁止新增第二套规则**；结构化 `details[{field,message}]` 与既有字符串 `error` 由同一内部实现产出，HTTP 层负责映射为 `400 invalid_params`。
- **`params_schema` 扩展约定**（向后兼容，纯 JSON Schema 仍可用）：
  - 每个 property 可带 `x-ui`：`{ label, help, placeholder, component: select|textarea|switch|json|number, enum_labels: {value: label}, secret: true, readonly: true }`。
  - 无 `x-ui` 时前端按 `type` 退化：`string→input`、`boolean→switch`、`integer/number→number`、`object/array→json`、带 `enum→select`。
- **验收标准**：
  - `POST /api/v2/jobs/{code}/run-now` 的 `params` 不符合 schema（缺必填 / 类型错 / enum 越界）→ `400 invalid_params` + `errors: [{field, message}]`。
  - 前端「立即运行」弹窗按 schema 生成表单；`secret: true` 的字段前端不回显历史值。
  - 无 `params_schema` 的作业，允许空参数直接运行，不弹表单。

### FR-016: 运行记录中心（前端 `/system/task-runs`）

- **描述**：MUST 新增运行记录页，修复 `links.detail` 死链，成为 UO-2「一个入口看全部执行」的落地页。
- **列表**：列 `run_id` / `job_name(job_code)` / `status` / 进度 / `attempt` / **来源**（`manual|import|cron|interval|once|scheduled`，后端派生）/ 耗时 / `created_at`；筛选 `job_code`、`status`、时间范围；分页沿用 `page/page_size`。
- **详情抽屉**：基础信息、进度条、`params`（只读 JSON，`secret` 字段脱敏）、`result`（成功/失败/跳过计数 + 错误表 + 复制/下载）、`error`（首行摘要 + 可展开堆栈）、时间线（created → claimed → started → finished → next_retry_at）、操作按钮（重试 / 取消，可见性由状态决定）。
- **深链**：`/system/task-runs?run=123` 打开页面即自动打开该 run 抽屉（FR-009 通知深链依赖此）。
- **验收标准**：
  - 存在 `running/pending/claimed/retrying` 行时自动轮询（3s）；全部进入终态即停止。
  - 页面不可见（`document.hidden`）或路由离开时停止轮询；同时最多 1 个轮询器。
  - 操作返回 409 时以可读文案提示（如「该执行已完成，不能取消」），不弹原始 JSON。
  - 刷新后保留筛选条件（query 同步）。

### FR-017: 一次性定时（定时跑一次）

- **描述**：MUST 支持「在指定时刻运行一次」，复用 `job_triggers` 表，**不新增列**：`trigger_type='once'` + `next_run_at` 即计划时刻。
- **语义**：
  - 到期 → dispatcher 以 `run_key='<trigger_id>:<scheduled_for>'` 建 run（幂等）→ 同 tick 内置 `enabled=0, next_run_at=NULL, last_run_at=now`。
  - **完成动作 MUST 用专用原子方法 `complete_once_trigger(trigger_id, expected_next_run_at, now)`**：单条 `UPDATE job_triggers SET enabled=0, next_run_at=NULL, last_run_at=? WHERE id=? AND next_run_at=?`，以受影响行数判定幂等。**禁止复用 `advance_trigger(..., None)`**——该方法的写后回读校验要求 `next_run_at is not None`，传 `None` 必然返回 `False`，会导致 once 永远无法收尾。
  - **自然完成 ≠ 管理员删除**：自然完成 = 软删除（`enabled=0`，行保留，可追溯「谁在什么时候排过什么」）；管理员 `DELETE` = 物理删除（历史 run 靠 `task_runs.trigger_id` 原值仍可追溯）。两者 MUST 走不同实现，不得共用一个「删除」语义。
  - 未到期取消 = `enabled=0`，行保留。
  - 服务停机错过时刻：本轮默认**恢复后立即补跑一次**（不丢任务）；补跑窗口策略见 TBD-6。
  - **paused 与 once 的交互（v1.2 显式声明）**：dispatcher 到期处理**不按 `job.status` 过滤**，paused 作业的 once 到点仍会建 run 并被 `complete_once_trigger` 消费，随后置 `skipped(job_inactive)`。即「暂停期间到点的一次性计划会作废（留痕 skipped）」。若要保留，应在暂停前删除或改期该触发器；是否改为「paused 时暂不消费 once」记入 TBD-10。
  - **与 `run-now.scheduled_for` 的边界（v1.2）**：远期一次性定时**只能**走 once 触发器；`run-now` 的 `scheduled_for` 仅允许 ±60s 时钟容差，超出即 `400 invalid_schedule`。这样「一次性定时」在系统内只有一个事实源（`job_triggers`），可被列表/取消/改期。
- **验收标准**：
  - 同一 trigger 连续多个 tick / 多实例并发时，只产生 1 个 run（`run_key` 唯一约束 + `complete_once_trigger` 以旧 `next_run_at` 乐观匹配、受影响行数判定）。
  - 触发后列表状态显示「已完成（一次性）」，不可再触发；重新启用需显式设置新的 `run_at`。
  - 进程重启后未到期的一次性任务仍按时触发（`next_run_at` 持久化）。
  - 时区：**`job_triggers.timezone` 当前不被 dispatcher 消费**，`next_run_at` 按**服务器本地时区**解释 cron；`Asia/Shanghai` 是部署前提，不是本表字段的运行时保证。前端展示与提交统一用带偏移的 `ISO8601`，落库仍为 epoch。

### FR-018: 周期触发器管理

- **描述**：MUST 提供 `cron` / `interval` 触发器的增删改查与启停，替代「只能改 DB」。
- **校验**：`cron` 5 段表达式用 `CronParser` 校验并回显「下次 5 次运行时间」；`interval_seconds >= 60`。**预览 MUST 由后端用与 dispatcher 相同的 `CronParser` 计算**（同一进程时区），前端只展示结果、不得自算；`timezone` 为只读展示列（当前不参与推算，见 §2.1）。
- **参数校验（v1.2）**：保存触发器时，`merge_job_params(job, params_override)` 的结果 MUST 过 `sanitize_params`；缺 `required` / 类型错 → `400 invalid_params`。**禁止把「参数不完整」的触发器落库**——否则每次到期只会产生 `dead` 记账行，问题被推迟到运行期才暴露。
- **验收标准**：
  - 新建/修改后立即重算 `next_run_at`，打开 `enabled=1` 即进入调度；修改 cron 不清空 `last_run_at`。
  - 列表展示 `next_run_at` / `last_run_at` / 上次 run 状态（成功/失败徽标）。
  - 「立即运行」不影响 `next_run_at`（`run_key=manual:<uuid>`）。
  - 删除触发器不删除其历史 run（`task_runs.trigger_id` 保留，列表来源显示「定时(已删除)」——触发器行已物理删除时类型不可考，不显示 `cron`）。

### FR-019: 调度器状态可见

- **描述**：MUST 暴露 dispatcher 运行态，避免用户把「调度器未启用」误判为功能故障。
- **验收标准**：
  - `GET /api/v2/jobs/dispatcher/status` 返回 `{enabled, dry_run, running, last_tick_at, last_summary{recorded,duplicates,advanced,promoted,errors}, backlog}`。
  - 前端作业中心顶部横幅：`enabled=false` 时显示「调度器未启用（JOB_DISPATCH_ENABLED=0），定时任务不会自动运行，仅可手动执行」。
  - 状态读取不触发 tick（纯只读）。

### FR-020: 权限与审计

- **描述**：作业管理面 MUST 全部受 `job_admin` 权限保护，写操作留审计。
- **验收标准**：
  - 本章所有 `/api/v2/jobs*` 接口 `@require_permission('job_admin')`；前端路由 `requiresAdmin: true`。
  - 定义修改、触发器增删改、run-now / retry / cancel 各写 1 条审计（`resource_type=job_run|job_trigger`，含 before/after 差异，`params.secret` 脱敏）。
  - 未授权访问返回 403，且前端菜单不显示。

## 4. 非功能需求

### NFR-001: 零破坏兼容

- **描述**：所有改动 MUST 在开关关闭时保持现网行为逐字一致。
- **度量**：关闭开关后，`/import/status` 响应 diff 为空；既有回归用例全绿。
- **优先级**：Must

### NFR-002: 可观测性

- **描述**：每次 run 的状态迁移与终态 MUST 可查询、可告警。
- **度量**：`/ops/health` 可读到 dispatcher 存活与积压数；连续失败触发 `scheduler_job_failed` 告警（已有）。
- **优先级**：Must

### NFR-003: 性能

- **描述**：异步发起接口 MUST NOT 等待执行；进度写入 MUST NOT 成为写放大源。
- **度量**：`POST /run-now` P95 < 100ms；单 run 进度写入 ≤ 1 次/秒。
- **优先级**: Must

### NFR-004: 可测试性

- **描述**：账本、触发器、聚合投递 MUST 可用纯单测覆盖，不依赖真实 HTTP/IM。
- **度量**：`python d:\filework\test.py --single meta/tests/test_job_*.py` 可在无外部依赖下通过。
- **优先级**：Must

### NFR-005: 幂等与一致性

- **描述**：同一排期/同一请求 MUST NOT 产生重复 run 或重复投递。
- **度量**：`run_key` 唯一约束生效；`INSERT OR IGNORE` 下重复创建返回既有 run id；聚合投递对同一批次只投递一次。
- **优先级**：Must

### NFR-006: 定义侧安全边界

- **描述**：作业定义面 MUST NOT 成为任意代码执行入口。
- **度量**：不存在「通过 API 注册/切换 handler」的通道；`handler` 不在 `ExecutorRegistry` 白名单的定义一律 `unavailable`；`params` 中的 `x-ui.secret` 字段在列表、详情、审计、日志中均脱敏。

### NFR-007: 前端轮询纪律

- **描述**：所有作业相关轮询 MUST 有终止条件，禁止无界重试。
- **度量**：
  - 终态（`succeeded/failed/cancelled/skipped/dead`）后立即停止；页面隐藏或路由离开立即停止。
  - 单页最多 1 个轮询器；连续失败按 2s→4s→8s 退避，累计 3 次后停止并展示「状态获取失败，点击重试」。
  - 导入对话框与运行中心的轮询互不复用、互不干扰（各自独立 token）。

## 5. 外部接口需求

### IF-001: 发起作业

- **类型**：API
- **入口**：`POST /api/v2/jobs/{code}/run-now`（v1.2：`params` 依 schema 校验；`scheduled_for` 仅作**时钟容差**用途，允许区间 `[now-60s, now+60s]`，超出 → `400 invalid_schedule`）
- **请求**：`{ "params": {...}, "async": true, "scheduled_for": 1763000000, "task_id": null }`
- **响应**：`202 { "success": true, "data": { "run_id": 123, "status": "pending" } }`
- **单一事实（v1.2）**：**未来时点的一次性执行只有一条路径**——`POST /api/v2/jobs/{code}/triggers`（`trigger_type='once'` + `run_at`），它进入 `job_triggers` 可被查看/取消/改期。`run-now` MUST NOT 接受远期 `scheduled_for` 造「影子定时」（否则同一语义出现两个事实源，且用户无法在触发器列表里管理它）。
- **错误处理**：未知 `code` → 404 `job_not_found`；作业 `paused` → 409 `job_paused`；`available=false` → 409 `job_unavailable`；参数不合法 → 400 `invalid_params`（附 `errors[{field,message}]`）；`scheduled_for` 超容差 → 400 `invalid_schedule`；账本写入失败 → 500 `run_create_failed`。

### IF-002: 查询单次执行

- **类型**：API（新增）
- **入口**：`GET /api/v2/jobs/runs/{run_id}`
- **响应**：`{ "success": true, "data": { "run_id": 123, "job_code": "import_cascade", "status": "running", "progress": {...}, "result": null, "error": null, "duration_ms": null, "capabilities": { "is_terminal": false, "can_cancel": true, "can_retry": false, "can_run": true }, "links": { "detail": "/system/task-runs?run=123" } } }`
- **说明**：`progress` 为**对象或 `null`**（由 `JobRunStore._decode` 在 `get_run` / `list_runs` 内统一解析，投影层直接透传，禁止二次序列化）。
- **能力位（v1.4）**：`capabilities.is_terminal = status ∈ TERMINAL_STATUSES`；`can_cancel = status ∈ pending|claimed|running`；`can_retry = status ∈ failed|dead|cancelled`；`can_run = job.available ∧ job.status=='active'`。四者 MUST 由后端用 `RUN_STATUSES` / `TERMINAL_STATUSES` 派生，前端**禁止**自行推导终态或按钮可用性（否则形成第二份状态事实）。
- **错误处理**：不存在 → 404 `run_not_found`。

### IF-003: 查询执行列表

- **类型**：API
- **入口**：`GET /api/v2/jobs/runs?job_code=&status=&page=1&page_size=20`
- **说明**：与 `task_run` 通用只读 API 并存；本接口返回投影状态与 `job_code` 名称，供前端任务中心使用。**v1.1 扩展**（`trigger_type/source/from/to` 与新增投影字段）见 IF-011，不传新参数时行为不变。

### IF-004: 取消 / 重试

- **类型**：API（已存在）
- **入口**：`POST /api/v2/jobs/runs/{id}/cancel`、`POST /api/v2/jobs/runs/{id}/retry`
- **错误处理**：状态不允许 → 409 `invalid_state_transition`。

### IF-005: 导入接口兼容

- **类型**：API
- **入口**：`POST /import/async`、`GET /import/status/<import_id>`
- **说明**：`/import/async` 增加返回 `run_id`；`/import/status` 响应结构不变，数据源切 `task_runs`。
- **错误处理**：`import_id` 不存在 → 404，与现行为一致。

### IF-006: 进度推送（可选）

- **类型**：API
- **入口**：`GET /api/v2/jobs/runs/{run_id}/stream`（SSE）
- **说明**：P4 可选实现；未实现前前端使用 2s 轮询。

### IF-007: 作业定义列表与详情

- **类型**：API（v1.1 新增）
- **入口**：`GET /api/v2/jobs`、`GET /api/v2/jobs/{code}`
- **响应**：`{ success, data: { items: [...] } }`，单项字段：
  `code / name / description / executor_type / handler / params_schema / default_params / timeout_seconds / max_attempts / backoff_seconds / concurrency_group / record_mode / status / available / last_run{run_id,status,finished_at} / next_run{trigger_id,trigger_type,next_run_at,enabled} / trigger_count`
- **说明**：`available=false` 表示 `handler` 不在当前进程 `ExecutorRegistry` 白名单（定义可见但不可运行）。`params_schema` 原样回传（含 `x-ui`），由前端渲染表单。
- **错误处理**：`{code}` 不存在 → 404 `job_not_found`；账本未初始化 → 503。

### IF-008: 作业定义编辑

- **类型**：API（v1.1 新增）
- **入口**：`PATCH /api/v2/jobs/{code}`
- **请求**：仅接受 FR-014 可编辑字段的**子集**，例：`{ "name": "...", "max_attempts": 2, "status": "paused", "default_params": {...} }`
- **响应**：`200 { success, data: <IF-007 单项> }`
- **校验**：未知字段或只读字段（`code/executor_type/handler/params_schema`）→ 400 `invalid_field`（`errors[{field,message}]`）；`timeout_seconds>0`、`max_attempts>=1`、`backoff_seconds>=0`；`status ∈ active|paused`；`default_params` 须过 `params_schema` → 否则 400 `invalid_params`。`record_mode` / `concurrency_group` 不接受写入（见 FR-014 预留字段）。
- **副作用**：写 `updated_at`，进程内定义缓存（如有）失效；不重启即生效。

### IF-009: 触发器管理（cron / interval / once）

- **类型**：API（v1.1 新增）
- **入口**：
  - `GET /api/v2/jobs/{code}/triggers`（列表，含 `next_runs_preview[5]`、`last_run{run_id,status}`）
  - `POST /api/v2/jobs/{code}/triggers`（新建）
  - `PATCH /api/v2/jobs/triggers/{trigger_id}`（修改 / 启停）
  - `DELETE /api/v2/jobs/triggers/{trigger_id}`（删除；历史 run 保留）
- **请求**：
  - cron：`{ "trigger_type": "cron", "cron_expr": "0 2 * * *", "timezone": "Asia/Shanghai", "enabled": true, "params_override": {...} }`
  - interval：`{ "trigger_type": "interval", "interval_seconds": 3600, ... }`
  - once：`{ "trigger_type": "once", "run_at": "2026-11-15T09:30:00+08:00", ... }` → 落库为 `next_run_at=<epoch>`，**不新增列**
- **响应**：`201/200 { success, data: <trigger 投影> }`，投影字段 `trigger_id / job_code / trigger_type / cron_expr / interval_seconds / timezone / enabled / next_run_at / last_run_at / next_runs_preview / last_run`
- **校验**：cron 用 `CronParser` 校验（非法 → 400 `invalid_cron_expr`）；`interval_seconds>=60`（否则 400 `invalid_interval`）；`run_at` 必须为未来时间（允许 60s 容差，早于 `now-60s` → 400 `run_at_in_past`）；`timezone` 仅存储与展示（**当前不参与推算**，见 §2.1），固定 `Asia/Shanghai`；`merge_job_params(job, params_override)` 须过 `sanitize_params`（否则 400 `invalid_params`，不让不完整参数落库）。
- **语义**：新建/修改后立即重算 `next_run_at`；`enabled=false` 保留行不调度；`DELETE` 为**物理删除**触发器行（`task_runs.trigger_id` 保留原值，列表来源显示「定时(已删除)」）。
- **删除语义区分（v1.2）**：once 自然完成由 dispatcher 调 `complete_once_trigger` 置 `enabled=0`（**软删除、行保留**）；只有显式 `DELETE` 才物理删除。前端「已完成的 once」不再出现在可调度列表，但仍在历史查询中可追溯。

### IF-010: 调度器状态

- **类型**：API（v1.1 新增，只读）
- **入口**：`GET /api/v2/jobs/dispatcher/status`
- **响应**：`{ success, data: { enabled, dry_run, running, last_tick_at, last_summary: {recorded,duplicates,advanced,promoted,errors}, backlog: {pending,due_triggers} } }`
- **说明**：只读快照，**不触发 tick**；`enabled=false` 供前端顶部横幅提示（FR-019）。

### IF-011: 运行记录列表扩展筛选

- **类型**：API（在 IF-003 上扩展，向后兼容）
- **入口**：`GET /api/v2/jobs/runs?job_code=&status=&trigger_type=&source=&from=&to=&page=&page_size=`
- **新增参数**：`trigger_type ∈ cron|interval|once`（按 `job_triggers.trigger_type` 联表判定，触发器已删除的行不匹配任何值）；`source ∈ manual|import|cron|interval|once|scheduled`（后端按 §2.1 前缀规则派生，**不设 `api`**）；`from/to` 为 `created_at` 的 ISO8601 或 epoch 秒。
- **响应**：沿用 IF-003 结构，单项**追加** `source / trigger_type / trigger_id / params_excerpt（脱敏后前 200 字）/ capabilities`；顶层**追加** `meta.filters = { statuses:[...], sources:[...], job_codes:[{code,name}] }`（`statuses` 来自 `RUN_STATUSES`、`sources` 来自 §2.1 前缀派生枚举，均为**值集合**，前端只负责文案/颜色映射）。
- **兼容**：不传新参数时行为与现状完全一致。

### IF-012: 运行详情扩展

- **类型**：API（在 IF-002 上扩展，向后兼容）
- **入口**：`GET /api/v2/jobs/runs/{run_id}`
- **追加字段**：`source / trigger_type / trigger_id / scheduled_for / next_retry_at / max_attempts / worker_id（脱敏为机位短标识）/ timeline[]`（`created → claimed → started → finished/next_retry` 事件数组）。
- **说明**：`params` 中 `x-ui.secret=true` 的键在响应中替换为 `"***"`；`result` 保持原样（可能较大，前端按需折叠）。
- **派生规则（v1.2）**：`timeline` MUST 由 run 行自身时间列（`created_at / claimed_at / started_at / finished_at / next_retry_at`）派生，**不新增事件表**；触发器被物理删除后 `trigger_type` 为 `null`、`source='scheduled'`，不猜测原类型。

## 6. 过渡需求

### TR-001: `task_runs.progress` 新增列

- **描述**：`task_runs` 增加可空 `progress TEXT`。
- **策略**：幂等迁移（`PRAGMA table_info` 判存在后 `ALTER TABLE ADD COLUMN`）；`task_run.yaml` 同步补字段（`type: json`）。
- **回滚**：列可空、无读方时零影响；回滚只需停止读写该列。

### TR-002: 导入双写 → 单写

- **描述**：`/import/async` 从内存字典迁移到账本。
- **策略**：P0 双写（内存 + 账本），P1 读侧切账本、保留内存写一版，P1+1 删除内存字典。开关 `IMPORT_USE_JOB_LEDGER`。
- **回滚**：开关置 0 回到内存实现；旧接口结构未变，前端无感。

### TR-003: 调度灰度收敛

- **描述**：`MaintenanceScheduler` / `PlatformScheduler` 执行权移交 dispatcher。
- **策略**：先 `JOB_DISPATCH_DRY_RUN=1` 跑 24h，比对「旧调度实际执行次数」与「dry-run 记账次数」一致率 100% 后打开 `SCHEDULER_MODE=dispatcher`。`WorkflowScheduleScheduler` 不在本期范围。
- **回滚**：`SCHEDULER_MODE=legacy`（默认），`JOB_DISPATCH_ENABLED=0`。

### TR-004: 历史数据

- **描述**：存量 `task_runs` 行 `progress` 为 `NULL`，无需回填。
- **策略**：不做数据迁移；`_import_tasks` 中的存量内存任务不迁移（重启即失效，可接受）。

### TR-005: 一次性触发器（once）零列变更上线

- **描述**：`job_triggers.trigger_type` 扩展枚举值 `once`，**不新增列**；一次性计划复用 `next_run_at` 作为计划时刻。
- **策略**：
  1. `JobRunStore.due_triggers` 的 `trigger_type IN ('cron','interval')` 追加 `'once'`；
  2. `JobRunStore` 新增 `complete_once_trigger(trigger_id, expected_next_run_at, now)`：单条 `UPDATE job_triggers SET enabled=0, next_run_at=NULL, last_run_at=? WHERE id=? AND next_run_at=?`，以受影响行数判定是否首次完成。**不得复用 `advance_trigger(..., None)`**：该方法末尾「写后回读」校验要求 `next_run_at is not None`，传 `None` 恒返回 `False`，once 将无法收尾。
  3. `JobDispatcher._process_trigger` 对 `once`：建 run 后同 tick 内调 `complete_once_trigger`，成功即 `summary['advanced'] += 1`（**不新增摘要键**，也不进入 cron 的 `errors` 计数）；
  4. `_next_run_at` 对 `once` 不再参与（分支提前返回），避免以 `None` 落入「无法推算下次时间」告警路径；
  5. 前端仅在 `trigger_type` 下拉增加「仅一次」。
- **幂等**：`run_key='<trigger_id>:<int(scheduled_for)>'` 唯一约束 + `complete_once_trigger` 以旧 `next_run_at` 乐观匹配，多实例/多 tick 只产生 1 个 run。
- **回滚**：代码回滚后 `once` 行因 `enabled` 已被置 0 不再被旧版本消费；未到期行只需 `enabled=0` 即可停用，无 DDL 回滚。

## 7. 约束与假设

### 7.1 技术约束

- 不新建业务表；只允许 `task_runs` 加 1 个可空列。
- 所有 DDL 必须幂等，且 `change_events_archive` 自愈逻辑（按源表派生列）继续成立。
- 不修改 `manage_service` 的审计语义（`skip_audit=True` 行为保持）。
- SQLite 单写模型：进度写入需节流，避免与业务事务争锁。
- 测试唯一入口 `python d:\filework\test.py`，禁止直接 pytest。

### 7.2 业务约束

- 导入的用户可见行为不得回退：成功/失败行数、错误提示、导出失败明细能力保持。
- 通知数量默认不变化（聚合开关默认关闭）。

### 7.3 假设

- 假设 A1：`JobDispatcher` + `JobRunStore` 的 claim/lease/retry 语义满足本期需求（已读代码确认）——来源：已验证。
- 假设 A2：`job_admin_api` 的 run-now / retry / cancel 可直接复用，不改变鉴权模型——来源：已验证。
- 假设 A3：导入服务 `import_cascade` 可在无请求上下文的线程中执行——来源：`/import/async` 现用 daemon 线程，已验证同构可行。

## 8. 优先级与里程碑

| ID | 需求 | 优先级 | 理由 |
|---|---|---|---|
| FR-001 | 唯一执行账本 | Must | 简化前提 |
| FR-002 | 四模式统一入口 | Must | 用户核心诉求 |
| FR-003 | 统一结果查询 | Must | 完成后可取结果 |
| FR-004 | 进度上报 | Must | 前台可感知 |
| FR-005 | 取消/重试 | Must | 长任务必备 |
| FR-006 | 导入接账本 | Must | 首个真实消费方 |
| FR-007 | 导入接口兼容 | Must | 零破坏 |
| FR-009 | 完成走事件出口 | Must | 单一通知路径 |
| FR-008 | 事件聚合投递 | Should | 治理通知风暴 |
| FR-010 | 定时接入 | Should | 收敛验证 |
| FR-011 | 任务中心视图 | Could | 体验增强 |
| FR-012 | 调度收敛 | Could | 技术债清理 |
| FR-013 | 导入对话框兼容 | Should | 现状交互不回退 |
| FR-014 | 作业定义管理 | Must | 管理面基础（可编辑运营参数） |
| FR-015 | 参数驱动手动运行 | Must | 替代裸 JSON，降低误用 |
| FR-016 | 运行记录中心 | Must | 修复 `links.detail` 死链，UO-2 落地 |
| FR-017 | 一次性定时 | Must | 用户明确诉求「定时跑一次」 |
| FR-018 | 周期触发器管理 | Should | 替代「只能改 DB」 |
| FR-019 | 调度器状态可见 | Should | 消除「功能坏了」误判 |
| FR-020 | 权限与审计 | Must | 管理面写操作合规 |

- 里程碑：
  - M1（P0+P1）：FR-001/002/003/004/006/007 + `progress` 迁移 + 导入切账本（双写过渡）。
  - M2（P2）：FR-009/FR-008 + 汇总事件开关。
  - M3（P3）：FR-010/FR-012 + 调度 dry-run 比对后切换。
  - M4（P4）：FR-011 任务中心完整视图 + 可选 SSE。
  - **M5（P5，v1.1 新增，作业中心管理面）**：
    - M5.1 后端最小闭环：FR-017（once）+ TR-005 + FR-014/IF-007/IF-008（定义列表/编辑）+ FR-019/IF-010（调度器状态）+ FR-015（`params_schema` 校验与 `x-ui` 透传）。
    - M5.2 运行记录中心：FR-016（`/system/task-runs` 路由 + 列表 + 详情抽屉 + 深链 `?run=` + 轮询纪律 NFR-007）+ IF-011/IF-012 扩展字段。前端组件复用方案与「不新增 job 专属组件」结论见 **§12.2**。
    - M5.3 调度管理页：FR-018 + IF-009（触发器 CRUD、cron 预览、once 表单、启停、立即运行）。复用矩阵见 **§12.2.1**。
    - M5.4 审计与权限收口：FR-020 + NFR-006（secret 脱敏、只读字段保护、全部端点 `job_admin`）。

### 8.1 依赖关系（M5 内部）

| 顺序 | 依赖原因 |
|---|---|
| M5.1 → M5.2 | 运行记录需 `source/trigger_type` 字段先由后端派生 |
| M5.1 → M5.3 | 触发器 CRUD 依赖 `once` 枚举与 `params_override` 校验 |
| M5.2 可并行 M5.3 | 两页互不依赖，仅共用 `jobService.js` 与服务端错误码 |
| M5.4 最后 | 审计/脱敏需覆盖前三个里程碑新增的全部写端点 |

## 9. 变更与设计提案（RFC）

### 9.1 现状分析（As-Is）

- 当前架构：三套 cron 循环各自持有作业表；`task_runs` 与 `JobDispatcher` 已建但默认关闭；导入用 daemon 线程 + 内存字典。
- 主要问题：
  1. 执行状态多源（内存字典 / 调度器内部统计 / `task_runs` 半启用）。
  2. 导入重启丢状态、无法跨进程查询。
  3. 逐行 `change_event` 造成投递风暴。
  4. 新增长任务没有统一接入方式，只能复制粘贴 daemon 线程。
- 相关代码路径：
  - [job_run_store.py](file:///d:/filework/excel-to-diagram/meta/core/job_run_store.py)
  - [job_dispatcher.py](file:///d:/filework/excel-to-diagram/meta/core/job_dispatcher.py)
  - [job_admin_api.py](file:///d:/filework/excel-to-diagram/meta/api/job_admin_api.py)
  - [server.py](file:///d:/filework/excel-to-diagram/meta/server.py)（`JOB_DISPATCH_ENABLED` 接线）
  - [export_import_api.py](file:///d:/filework/excel-to-diagram/meta/api/export_import_api.py)（`/import/async`、`/import/status`）
  - [import_handlers.py](file:///d:/filework/excel-to-diagram/meta/handlers/import_handlers.py)
  - [maintenance_scheduler.py](file:///d:/filework/excel-to-diagram/meta/core/maintenance_scheduler.py)

### 9.2 目标态

```
[触发层] job_triggers  (cron | interval | once | manual | event | on_demand)
              │ 写
[执行层] task_runs ──── JobDispatcher(tick/claim/lease/retry/reclaim)
              │ 终态
[通知层] change_events ── ChangeEventWorker ── webhook / im / inbox
              │ 弱引用
[人工层] tasks (人工待办，独立账本)
```

- 关键变更：
  1. `task_runs` 成为唯一执行账本，新增 `progress`。
  2. 导入改为账本驱动，`/import/status` 仅换数据源。
  3. 作业完成写事件，通知链路不新增通道。
  4. 旧调度器降级为触发源，`TaskScheduler` 删除。

### 9.3 详细设计

**模块职责**

| 模块 | 职责 | 改动 |
|---|---|---|
| `JobRunStore` | 账本读写 | 新增 `update_progress(run_id, payload)`、`update_result(run_id, result)` |
| `JobDispatcher` | 到期触发 / claim / 执行 / 回收 | 复用；执行期注入取消信号 |
| `JobContext` | handler 上下文 | 新增 `run_id`、`should_cancel()`、`report_progress()` |
| `meta/handlers/import_handlers.py` | 导入作业执行体 | 由「统计内存任务」改为「执行 `import_cascade` + 进度上报」|
| `export_import_api` | 导入接口 | `/import/async` 建 run；`/import/status` 读账本 |
| `job_admin_api` | 作业管理 | 新增 `GET /runs/{id}`、`GET /runs`；v1.1 追加定义列表/编辑、触发器 CRUD、dispatcher status、runs 扩展筛选与详情 timeline |
| `job_params` | 参数合并与校验（唯一实现） | `merge_job_params` 合并；`sanitize_params` 保持 `(clean, error)` 二元组；v1.2 仅抽内部 `_validate` 以提供结构化 `details`，不新增第二套规则；secret 键脱敏 |
| `notification` | 汇总投递 | dispatcher 按 `idempotency_key` 前缀聚合 |

**数据模型**

- `task_runs` 新增：`progress TEXT NULL`（JSON）。
- `job_triggers` **无列变更**：`trigger_type` 语义扩展 `once`，计划时刻复用 `next_run_at`（TR-005）。
- `change_events` 不新增列：批次标识复用 `idempotency_key = job:<run_id>:<seq>`。
- 无其他表结构变更。

**API 设计**：见第 5 章 IF-001 ~ IF-012（v1.1 新增 IF-007 ~ IF-012）。

**主流程（导入 M2）**

1. `POST /import/async` 校验文件与对象 → `JobRunStore.create_run('import_cascade', params={file, object_type, mode})` → 返回 `202 {import_id, run_id}`。
2. `JobDispatcher.tick()` 领 run → `start()` → 调 handler。
3. handler 分批执行，每 200 行 `report_progress`；每行 `manage_service.create(skip_audit=True)` 携带批次键。
4. 完成：`finish(success, result)` → 写 1 条 `job_succeeded|job_failed` 事件。
5. `ChangeEventWorker` 投递；聚合开关开启时同批次只投 1 条。
6. 前端 2s 轮询 `GET /api/v2/jobs/runs/{run_id}`，终态展示结果与失败明细下载。

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. 复用 `task_runs` + `JobDispatcher`（本方案） | 零新表、已具备租约/重试/幂等 | 需收敛旧调度器，有迁移工作量 | 选定 |
| B. 新建独立作业表/队列 | 概念清爽 | 第 6 套机制，与 v246 重复 | 否决 |
| C. 引入 Celery/RQ 等外部队列 | 生态成熟 | 新增 Redis/Worker 运维，SQLite 单机场景过重 | 否决 |
| D. 仅扩展内存字典（现状延长） | 改动最小 | 重启丢状态，无法收敛 | 否决 |
| 事件聚合：新增 `source_job_run_id` 列 | 语义直白 | 又一次 schema 变更 | 否决，复用 `idempotency_key` |
| 进度：3 个数值列 | 易索引 | 结构僵化 | 否决，用 1 列 JSON |

### 9.5 实施与迁移计划

**实施顺序**

1. P0：`progress` 幂等迁移 + `task_run.yaml` 补字段 + `JobRunStore.update_progress`。
2. P0：`/import/async` 双写账本；`/import/status` 优先读账本（开关 `IMPORT_USE_JOB_LEDGER`）。
3. P1：`import_handlers` 真正执行 `import_cascade` 并上报进度；`JobContext` 增加取消/进度能力。
4. P1：新增 `GET /api/v2/jobs/runs/{id}` 与列表接口；前端 step2 允许最小化、按 `run_id` 恢复、终态停止轮询（默认交互不变）。
5. P2：作业完成事件 + 聚合投递开关。
6. P3：`JOB_DISPATCH_DRY_RUN=1` 比对 24h → `SCHEDULER_MODE=dispatcher` → 删除 `TaskScheduler`。
7. P4：任务中心进度/取消/重试 UI。
8. P5（v1.1）：M5.1 后端 once + 定义/触发器/状态接口与 params 校验 → M5.2 运行记录中心 → M5.3 调度管理页 → M5.4 审计与脱敏收口（顺序与依赖见 §8.1）。

**风险与缓解**

| 风险 | 缓解 |
|---|---|
| SQLite 进度写与业务写争锁 | 进度 1s 节流 + 单条 UPDATE |
| 调度切换导致漏跑/重跑 | dry-run 24h 次数比对 + 触发器 `enabled` 逐条打开 |
| 导入重试重复写入 | 依赖业务幂等键；重试只重跑失败批次 |
| 聚合投递被误认为"事件丢失" | 开关默认关闭；文档明确"事实不删，仅改投递粒度" |
| 归档表与新列不一致 | 归档表自愈已按源表派生列，新增 `progress` 自动覆盖 |
| 一次性任务重复执行 | `run_key` 唯一约束 + `complete_once_trigger` 以旧 `next_run_at` 乐观匹配；并发 tick 单测 |
| 触发器官改导致漏跑/错跑 | cron 保存前用 `CronParser` 校验并预览未来 5 次；改后立即重算 `next_run_at` |
| 管理面误操作（暂停/删除） | `paused` 期间调度到点仍记账 `skipped(job_inactive)`、不执行；`run-now` 返回 409；不取消存量 run；删除触发器不删历史 run |

**测试策略**

- 单元：`test_job_run_store`（progress/result/取消）、`test_job_dispatcher`（claim/lease/retry/dry-run）。
- 集成：`test_import_async_ledger`（双写一致、重启可查）、`test_job_completion_event`（终态→事件→投递）。
- 兼容：`test_import_status_contract`（响应结构 diff 为空）、`test_import_errors_cap`（每类型 200 / 全局 2000 / `errors_truncated`）。
- 回归：`test_change_event_worker`、`test_message_center_inbox`、`test_archive_change_events`。
- M5 新增：`test_job_triggers_crud`（once 触发后 `enabled=0` 且只产生 1 run / cron 非法 400 / DELETE 保留历史 run）、`test_job_definitions_patch`（只读字段 400 / paused 时 run-now 409）、`test_job_params_validate`（缺必填、类型、enum、secret 脱敏）；前端 vitest 覆盖 `jobService` 与运行中心「终态停止轮询」。 
- 统一入口：`python d:\filework\test.py --single <path>`。

**回滚计划**

- 全部通过开关降级：`IMPORT_USE_JOB_LEDGER=0`、`change_notification.batch_summary=false`、`SCHEDULER_MODE=legacy`、`JOB_DISPATCH_ENABLED=0`。
- 代码回滚不涉及数据回滚（`progress` 列可空、`task_runs` 仅新增行）。

## 10. TBD 列表

| ID | 事项 | 缺失信息 | 下一步 |
|---|---|---|---|
| TBD-1 | 同步/异步判定阈值 | 默认 2s 是否合适，是否按作业类型配置 | 实现 P0 时用常量 + 作业定义覆盖，观察后再定 → **v1.3 建议：维持「常量 2s + 定义级覆盖」，M5 不改**，上线 2 周按实测 P95 再定 |
| TBD-2 | ~~失败行明细存储位置~~ | 已定：`result.errors` 保持「每类型 200 条 + 全局 2000 条」，超限 `errors_truncated=true` + `result_download_url` | 已关闭（2026-11-14） |
| TBD-3 | 聚合投递的默认开关状态 | 是否在 P2 上线时对内部用户默认开启 | 待产品确认 → **v1.3 建议：默认 `false`（现状）**，仅对内部账号灰度开启，稳定 1 周后再评估全局开启 |
| TBD-4 | SSE 是否本期实现 | 轮询 2s 是否满足体验 | P4 前评估；**M5 不实现 SSE**，运行中心用 3s 轮询 + 终态停止（NFR-007），不阻塞 M5 |
| TBD-5 | `WorkflowScheduleScheduler` 收敛时点 | 动态触发器是否已有足够使用量 | 放到 P5，另行评估 |
| TBD-6 | 一次性任务「错过时刻」的补跑窗口 | 停机跨越 `next_run_at` 时是否无条件补跑 | 默认恢复后补跑一次；是否引入 `misfire_grace_seconds`（建议 24h，超窗记 `skipped`）在 M5.1 前定 → **v1.3 建议：采纳 `misfire_grace_seconds=86400`**（env 可覆盖）。规则：仅 `job.status='active'` 参与补跑；`now - scheduled_for > grace` 记 `skipped(misfire)`；paused 一律 `skipped(job_inactive)` 不补（与 TBD-10 一致）。实现成本 = `_process_trigger` 一处判断，M5.1 落地 |
| TBD-7 | 预留字段 enforcement（`record_mode` / `concurrency_group`）与 run 保留期 | 两者当前无消费方 | M5 只展示只读；是否实现「按 mode 记账」「按组限并发」与留存期策略在 M5.3 前确认 → **v1.3 建议：M5 仅只读展示，不实装 enforcement**；保留期 **90 天**，由 `job_runs_retention` 作业定义自身执行（不照搬 JSS 的 15 天，太短）；若 M5.3 前仍无消费方需求，则从表单移除、列保留 |
| TBD-8 | 运行中心与旧 `/system/platform-ops-jobs` 关系 | 是否合并菜单 | M5.2 前与产品确认；建议旧页保留只读，新页为唯一入口 → **v1.3 建议：按此执行**（旧页 `maintenance_scheduler` 与 `task_runs` 无共享事实，硬合并会造成第二账本） |
| TBD-9 | `timeout_seconds` / `backoff_seconds` 未快照到 run | 定义修改后历史 run 的超时/退避口径漂移 | 本期接受「按当前定义解释」；如需精确口径，后续迁移在 `task_runs` 增加 `timeout_snapshot` 列（需评审）→ **v1.3 建议：接受不快照，不加列**。依据：SAP BTP JSS 的超时同样是调度侧策略（默认 30min、可配至 7 天），不随单次 run 固化；如需审计，仅在 run 日志记录「本次实际生效 timeout」 |
| TBD-10 | paused 状态下 once 触发器是否消费 | 当前到点仍消费并记 `skipped`，计划作废 | 本期按现状（暂停即放弃该次）；若要「恢复后补跑」，需 dispatcher 在 `_process_trigger` 前检查 `job.status`，M5.1 前定 → **v1.3 建议：维持「暂停即放弃」**（消费 + `skipped(job_inactive)`）。理由：与 cron 行为一致（暂停期间计划照常流逝、不积压），避免 dispatcher 新增分支与「静默积压」；代价是 UI 必须在暂停确认框显式提示「待执行的一次性计划将作废」 |

## 11. 竞品参考（2026-11 调研）与取舍

> 调研目的：确认「定义 / 手动运行 / 运行详情 / 周期 / 一次性」这五件事在成熟产品中的**界面与语义惯例**，避免自造概念。
> 结论先行：**语义上采纳「周期调度」与「一次性延迟」分离**（Temporal 的 Schedule vs Start Delay、Red Hat 的 "Does not repeat"），**存储上复用同一张触发器表**（EventBridge 的统一 schedule API），**交互上采纳 Hangfire 的双层视图**（定义列表看 next/last run + 运行列表看每次执行）。

### 11.1 横向对比

| 产品 | 定义方式 | 手动运行 | 运行记录详情 | 周期 | 一次性 | 借鉴点 |
|---|---|---|---|---|---|---|
| **Hangfire** | 代码注册（C# API/特性），Dashboard 只读 + 有限操作 | Dashboard「Trigger now」触发一次，不改周期 | `/jobs` 按 Succeeded/Failed/Processing/Delayed 分组；可 Requeue | Cron（5/6 段）| Delayed Job = 延迟到某时刻执行一次 | 定义列表展示 next/last run + Trigger now；失败自动重试递增延迟 |
| **Temporal** | 代码定义 Workflow（多语言 SDK）| Client/CLI/UI 手动触发 | Schedule 详情：frequency、start/end、recent runs、**upcoming runs** | Schedule（cron/calendar/interval）| **Start Delay**（`start_delay`），与 Schedule 互斥 | 周期与一次性**概念分离**；「未来 N 次」预览 |
| **GitHub Actions** | YAML（代码即定义，UI 不可新建）| `workflow_dispatch` + `inputs` 表单 | run 页 jobs 侧栏 + 每 job 日志；Re-run all / Re-run failed | `schedule` cron（UTC）| 无原生定时一次（只能立即 dispatch）| inputs 驱动表单；失败只重跑失败 job（本期只到 run 级）|
| **Kubernetes** | CronJob（周期）与 Job（一次性）**两个资源** | `kubectl create job --from=cronjob/x` | Job/Pod conditions、events、日志 | CronJob（5 段 + 时区）| 独立 Job 资源 | 官方明确「CronJob 创建的 Job 必须幂等」→ 我们用 `run_key` |
| **AWS EventBridge Scheduler** | 统一 schedule API：`at` / `rate` / `cron` | 无「立即执行」，需改 schedule 或直调目标 | 指标/日志为主，无执行列表 | `rate` / `cron` + `EndDate` | `at(...)` 一次性 + `ActionAfterCompletion=DELETE` | 一次性完成后**自动删除**；我们改为 `enabled=0` 软删除保留历史 |
| **Airflow** | Python DAG（代码即定义）| Trigger DAG with config（JSON `conf`）| DAG Runs 列表 → Grid/Graph → Task 实例日志与重试 | `schedule_interval`（cron/timedelta）| 手动 trigger 一次（无原生一次性计划）| `conf` = 我们的 `params`；列表与详情分层；失败原因优先 |
| **Red Hat Automation Orchestrator** | 可视表单 + Workflow | 运行 workflow | Workflow 运行详情（节点级）| 可视 schedule（Frequency 下拉）| Frequency 选 **"Does not repeat"** | 一次性作为周期下拉的一个选项，认知成本最低 |
| **SAP S/4HANA Application Jobs / SM36-SM37** | SM36：作业名 + 步骤（ABAP 程序/变式）+ 开始条件；Fiori「Schedule Application Jobs」表单，可存 Job Template | 「Start Immediately」是开始条件里的显式选项 | SM37 作业总览 + 作业日志（spool）；状态 Scheduled / Released / Ready / Active / Finished / Canceled | 开始条件：立即、指定日期时间、周期（按日/周/月）、**前置作业后、事件后（SM62/SM64）** | 与周期**同一个「开始条件」字段**，选「立即 / 指定日期时间」即一次性 | ①「定义（含参数变式）」与「调度（开始条件）」两层分离；② 一次性与周期同在开始条件，不造新概念；③ 运行详情以**作业日志**为主体 |
| **SAP BTP Job Scheduler** | REST `POST /scheduler/jobs`（`action` 端点 + 参数 + `active`） | 手动触发 / `"time": "now"` | run log（调度器下发 `x-sap-job-run-id`，应用完成后回写）；保留 15 天；SCHEDULED → RUNNING（TRIGGERED / ACK_RECVD / ACK_NOT_RECVD）→ COMPLETED（SUCCESS / ERROR / REQUEST_ERROR / UNKNOWN） | 7 段 SAP cron / `repeatInterval` / `repeatAt` | ISO-8601 日期时间，**执行后自动 deactivate** | ① 一次性执行后自动停用（= 我们 `enabled=0` 保留行）；② 异步必须「立即 202 + 事后回写 run log」（= 我们 `task_runs` 账本）；③ 错过计划时刻**尽快补跑**（支撑 TBD-6 的 misfire grace）；④ 超时是调度侧策略（默认 30min、可配至 7 天），不随单次 run 快照（支撑 TBD-9）|

### 11.2 采纳清单（映射到 FR）

- **定义列表双层视图**（Hangfire）：定义页展示 `last_run` / `next_run` 摘要 + 「立即运行」→ FR-014 / FR-018 / IF-007。
- **周期与一次性分离**（Temporal / Red Hat）：`trigger_type ∈ cron|interval|once`，UI 用同一个「频率」下拉表达 → FR-017 / FR-018 / IF-009。
- **未来 N 次预览**（Temporal upcoming runs）：`next_runs_preview[5]` → IF-009。
- **一次性完成后自动收尾**（EventBridge `ActionAfterCompletion=DELETE`）：改写为 `enabled=0` 软删除，保留追溯 → FR-017 / TR-005。
- **表单驱动手动运行**（GitHub Actions `workflow_dispatch.inputs` / Airflow `conf`）：`params_schema` + `x-ui` 生成表单，提交前校验 → FR-015。
- **运行列表 → 详情抽屉**（Hangfire `/jobs`、Airflow DAG Runs）：`/system/task-runs` 列表 + 抽屉 + 深链 → FR-016。
- **幂等要求**（Kubernetes CronJob 官方限制）：`run_key='<trigger_id>:<scheduled_for>'` → FR-017。
- **失败原因优先**（Airflow）：详情抽屉 `error` 首行摘要置顶，堆栈折叠 → FR-016。
- **一次性与周期同属「触发计划」**（SAP SM36 开始条件 / JSS schedule）：`job_triggers` 一行一计划，靠 `trigger_type` 区分，不为一次性建第二张表 → FR-017 / IF-009。
- **定义 / 调度两层分离 + 参数变式**（SAP SM36 变式、Application Jobs Job Template）：`job_definitions.default_params` 即「默认变式」，触发器 `params_override` 即「本次调度变式」→ FR-014 / FR-015 / FR-018。
- **一项计划执行完即停用、行保留**（JSS one-time auto-deactivate）：与 EventBridge 结论一致，落为 `enabled=0` + 保留 run 历史 → FR-017 / TR-005。
- **错过即补跑 + 运行日志保留期**（JSS「到期未触发则尽快补跑」、run log 保留 15 天）：作为 TBD-6 misfire grace 与 TBD-7 保留期的外部依据 → §10。

### 11.3 明确不采纳

1. **DAG / Workflow 编排**（Airflow、Temporal Workflow）：本期所有作业均为单一执行体；引入依赖图需新表 + 新引擎，违反「收敛不新建体系」。
2. **代码即定义的上传通道**（YAML/DAG 上传）：可执行任意代码，安全边界不可控；定义仍由迁移播种 + 代码注册表决定（NFR-006）。
3. **handler 动态加载 / 插件市场**：同上，白名单外一律 `unavailable`。
4. **job/task 级部分重跑**（GitHub Actions "Re-run failed jobs"）：当前账本粒度为 run，拆分需子 run 表；M5 只做 run 级 `retry`（FR-005）。
5. **一次性触发器物理删除**（EventBridge DELETE）：会丢历史；我们保留行。
6. **多时区 / RRULE / 复杂日历**（Temporal Calendar、Hangfire RRULE 讨论）：本期仅 cron 5 段 + interval + once，时区固定 `Asia/Shanghai`。
7. **依赖可视化 / 甘特图**（Airflow Graph 视图）：不在管理面 MVP 范围。
8. **事件驱动触发**（SAP SM62/SM64、SM36「after event」）：`job_triggers.event_name` 保留列但 dispatcher 不消费，本期不支持；事件触发统一走 `change_events` + `ChangeEventWorker`，不再造第三套机制。
9. **作业优先级 / 作业类 A/B/C**（SAP SM36 job class）：单进程 dispatcher + SQLite，无多应用服务器负载均衡场景；并发限流需求记 TBD-7。

**来源**：

- [Hangfire RecurringJob.Trigger](https://api.hangfire.io/html/M_Hangfire_RecurringJob_Trigger.htm)
- [Temporal: How to choose between a Schedule, a Cron Job, and Start Delay](https://docs.temporal.io/evaluate/features/schedules)
- [Temporal TypeScript SDK: Start Delay](https://docs.temporal.io/develop/typescript/schedules)
- [GitHub Blog: Save time with partial re-runs in GitHub Actions](https://github.blog/news-insights/product-news/save-time-partial-re-runs-github-actions/)
- [Kubernetes: CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [AWS: Deleting a schedule in EventBridge Scheduler（ActionAfterCompletion）](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-schedule-delete.html?language=en_US)
- [AWS Blog: Automatically delete schedules upon completion](https://aws.amazon.com/blogs/compute/automatically-delete-schedules-upon-completion-with-amazon-eventbridge-scheduler/)
- [Airflow: DAG Runs — Passing Parameters when triggering DAGs](https://airflow.apache.org/docs/apache-airflow/2.8.1/core-concepts/dag-run.html)
- [Red Hat: Schedule a workflow with a visual schedule（Does not repeat）](https://docs.redhat.com/de/documentation/automation_orchestrator/2026.8/develop-schedule_a_workflow_with_a_visual_schedule)
- [BMC: SM36 and SM37 at Enterprise Scale](https://www.bmc.com/blogs/sm36-sm37-enterprise-limits/)（SM36 定义步骤/变式/开始条件，SM37 监视）
- [Fioneer Docs: Application Jobs（Fiori 调度步骤：Start Immediately / 指定时间戳 / 参数 / 存模板）](https://fsdm.docs.fioneer.com/latest/en/4-ABAPCloud/30-FioriApps/Admin/Applic_Job_Templ)
- [SAP BTP Job Scheduling Service — 计划类型、生命周期、一次性自动停用、run log 与超时约束（社区 skill 摘要，2025-11 校验）](https://www.skillmd.ai/skills/sap-btp-job-scheduling/SKILL.md)
- [SAP Help Portal: Job Scheduler](https://help.sap.com/docs/job-scheduler)

## 12. 作业中心实现契约摘要（M5）

> 供实现期只读本摘要，避免反复通读全文（L2 规则）。

### 12.1 后端改动点

| 文件 | 改动 |
|---|---|
| [job_run_store.py](file:///d:/filework/excel-to-diagram/meta/core/job_run_store.py) | ① `due_triggers` SQL 的 `IN ('cron','interval')` 追加 `'once'`；② 新增 `complete_once_trigger(trigger_id, expected_next_run_at, now)`（单条 `UPDATE ... WHERE next_run_at=?`，受影响行数判定）；③ 新增触发器方法 `list_triggers(job_id)` / `trigger_by_id` / `create_trigger` / `update_trigger` / `delete_trigger` / `last_run_by_trigger`；④ `list_runs` 增加可选 `trigger_type` / `from_ts` / `to_ts`（默认行为不变）|
| [job_dispatcher.py](file:///d:/filework/excel-to-diagram/meta/core/job_dispatcher.py) | `_process_trigger` 增加 `once` 分支：建 run → `complete_once_trigger(...)` → `summary['advanced'] += 1`，**提前返回**（不进 `_next_run_at` 与 `errors`）；**禁止 `advance_trigger(expected, None)`**（回读校验要求非 None） |
| [job_params.py](file:///d:/filework/excel-to-diagram/meta/core/job_params.py) | **不新增校验规则**：把现有规则抽成唯一内部实现 `_validate(params, schema) -> (clean, error, details)`；`sanitize_params` 保持 `(clean, error)` 二元组签名不变（既有调用点零改动），API 层用新增 `sanitize_params_detailed`（同一实现，仅多返回 `details[{field,message}]`）；新增 `redact_secrets(schema, params)`（只做脱敏，不做校验） |
| [job_admin_api.py](file:///d:/filework/excel-to-diagram/meta/api/job_admin_api.py) | 新增 IF-007/008/009/010 共 8 个端点；`_project_run` 追加 `source/trigger_type/trigger_id/timeline/params(脱敏)/capabilities`；`job_runs_list` 追加 `meta.filters`；`progress` 保持透传 `_decode` 后的对象（禁止二次 `json.dumps`）；run-now 增加 `paused→409`、`invalid_params→400`、`scheduled_for` 语义 |
| [server.py](file:///d:/filework/excel-to-diagram/meta/server.py) | 向 `job_admin_api` 注入 dispatcher 引用（供 IF-010 状态快照）；`ExecutorRegistry.names()` 供 `available` 判定 |

### 12.2 前端实现方案（组件复用 + 参数元数据驱动）

> **结论：不新增任何 job 专属 UI pattern 组件。** 现有 `src/components/common/` 已覆盖列表、筛选、表单、抽屉、确认、分页、时间选择全部需求；作业中心的差异只在「字段配置」与「值 → 文案/颜色映射」，属于页面内数据配置，不构成独立 pattern。
> 判定口径：只有当某交互在 ≥2 个非 job 场景也需要、且无法由现有组件配置表达时，才允许下沉为通用组件。本轮检查后**无此情况**。

#### 12.2.1 组件复用矩阵（零新增 `.vue`）

| 需求 | 复用组件 | 配置方式 |
|---|---|---|
| 页面骨架 / 标题 / 面包屑 | `PageShell` | props 直传 |
| 列表（运行记录 / 定义 / 触发器） | `MetaTable` | `columns` 配置：`status` 列 + `statusMap`（值→文案/色调）、`time` 列、`ellipsis` 列；`#cell-<key>` 插槽渲染进度条 / 结果摘要；`actions` 传 `position:'row'` 的取消/重试/立即运行 |
| 顶部筛选（状态 / 来源 / 作业 / 时间范围） | `FilterBar` | `fields` **由 IF-011 `meta.filters` 生成**（禁止前端写死枚举） |
| 分页 | `MetaTable` 内置 `pagination`（或独立 `Pagination`） | 受控 `page/size`，与 query 同步 |
| 详情（参数 / 进度 / 结果 / 错误 / 时间线） | `Drawer` + `AppTabs` + `DetailSection` | run 详情抽屉；`AppTabs` 分「概览 / 参数 / 结果 / 时间线」 |
| 运行前参数录入 | `MetaForm` | `fields` 由 `params_schema` 转换（见 12.2.2），`layout='vertical'` |
| 一次性定时时间 | `DateTimePicker` | `MetaForm` 的 `field.slot` 挂载；提交前转 epoch 秒（UTC） |
| 触发器编辑（cron / interval / once） | `MetaDialog` + `MetaForm` | `trigger_type` 切换驱动 `fieldVisibility` / `fieldDependencies`（仅显示对应字段） |
| 危险操作确认（取消 / 删除触发器 / 暂停作业） | `ConfirmDialog` | 文案按 `capabilities` 与 `status` 生成 |
| 空态 / 错误 / 降级横幅 | `EmptyState` / `AppAlert` | dispatcher `enabled=false` 或 `503` 时展示只读横幅 |
| 按钮 | `AppButton` | 可用性**只读** `capabilities`，不在前端推导 |

新增页面（仅 2 个 `.vue`，均不进入 `components/common/`）：

| 文件 | 改动 |
|---|---|
| [system.js](file:///d:/filework/excel-to-diagram/src/router/modules/system.js) | 新增 `/system/task-runs`（`TaskRuns.vue`）与 `/system/job-schedules`（`JobSchedules.vue`），均 `requiresAdmin: true` |
| `src/views/TaskCenter/TaskRuns.vue`（新建） | `PageShell` + `FilterBar` + `MetaTable` + `Drawer`；`?run=` 深链（打开抽屉）；3s 轮询且 `capabilities.is_terminal=true` 即停（NFR-007） |
| `src/views/SystemManagement/JobSchedules.vue`（新建） | 定义列表（PATCH 运营参数 / 立即运行 / paused 徽标）+ 触发器管理（cron 预览 / interval / once / 启停 / 删除）+ dispatcher 横幅；表单全走 `MetaForm` |

#### 12.2.2 三个纯函数适配器（无 UI、可单测）

| 模块（新建） | 职责 | 关键约束 |
|---|---|---|
| `src/utils/jobParams.js` | `schemaToFields(schema) -> MetaForm.fields[]`；`buildDefaults(schema) -> params`；`toEpochSeconds(localValue)` | 映射：`string→text`、`integer/number→number`、`boolean→switch`、`enum→select(options)`、`const→text(disabled)`、`required→required`、`default→初始值`；键名命中 `token/password/secret/key` → `password`；`schema` 为空/NULL → 返回 `[]`（不渲染表单，见 §2.1「空 schema 语义」）；**不实现任何校验规则**（校验唯一来源是后端 `sanitize_params`） |
| `src/utils/jobRunStatus.js` | `statusLabel` / `statusTone` / `sourceLabel` / `triggerTypeLabel` | 输入值集合**只来自后端下发**（`meta.filters` / run 行）；命中未知值返回原值 + `default` 色调，**不猜测、不新增状态** |
| `src/services/jobService.js` | `fetchJobs / patchJob / fetchTriggers / createTrigger / updateTrigger / deleteTrigger / fetchDispatcherStatus / fetchRuns / fetchRun / runNow / retryRun / cancelRun` | 照 `schedulerService.js` 模式 `import { apiV2 } from '@/utils/httpClient'`；路径参数一律 `encodeURIComponent`；不在 service 层做业务判断 |

#### 12.2.3 唯一一处通用组件微扩展

| 文件 | 改动 | 理由 |
|---|---|---|
| [MetaForm.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaForm.vue) | `type='password'` 分支（`el-input`/原生 `input` + `show-password`），约 6 行 | 作业参数存在 secret（token/password/key）；这是**通用表单能力缺口**，不是 job 专属逻辑。禁止为 job 新建 `JobParamForm.vue` |

#### 12.2.4 明确不做（反模式清单）

- [X] 新建 `components/job/`、`JobTable.vue`、`JobRunCard.vue`、`JobParamForm.vue` 等 job 命名组件。
- [X] 前端维护状态数组 / 终态数组 / 按钮可用性函数（第二份事实，见 §2.1）。
- [X] 前端解析 `progress` 字符串或 `params` JSON（后端已 `_decode`）。
- [X] 前端自算 cron 下次运行时间（与调度进程时区不同源）。
- [X] 改写 `PlatformOpsJobs.vue` / `TaskCenter.vue` 的原生 `<table>`（只读保留，FR-020 / TBD-8）。

#### 12.2.5 落地顺序

1. **M5.2-a**：`jobService.js` + `jobRunStatus.js` + `jobParams.js`（纯函数，先写单测）。
2. **M5.2-b**：`MetaForm` 增加 `password` 类型 + 单测。
3. **M5.2-c**：`TaskRuns.vue`（列表 → 筛选 → 深链 → 详情 → 取消/重试 → 轮询纪律）。
4. **M5.2-d**：`JobSchedules.vue`（定义列表/立即运行 → 触发器 CRUD → dispatcher 横幅）。
5. **M5.2-e**：`system.js` 注册两条路由（最后接线路由，避免半成品入口）。

### 12.3 字段契约（后端投影 → 前端）

- **run**：`run_id / job_code / job_name / status / attempt / progress / result / error / duration_ms / created_at / started_at / finished_at / source / trigger_type / trigger_id / params / timeline[{at,status}] / capabilities{is_terminal,can_cancel,can_retry,can_run} / links.detail`
  - `progress` MUST 为**对象或 `null`**（投影层解析后下发），禁止下发 JSON 字符串；`params` 中 `x-ui.secret=true` 的键为 `"***"`。
  - `capabilities` MUST 由后端按 §IF-002 四条规则派生；前端**禁止**再判定终态与按钮可用性。
- **list 顶层**：`runs[] / total / page / size / meta.filters{statuses[],sources[],job_codes[{code,name}]}`（`meta.filters` 供 `FilterBar` 生成枚举，前端不硬编码）。
- **trigger**：`trigger_id / job_code / trigger_type / cron_expr / interval_seconds / timezone / enabled / next_run_at / last_run_at / next_runs_preview[] / last_run{run_id,status}`
- **dispatcher**：`enabled / dry_run / running / last_tick_at / last_summary{recorded,duplicates,advanced,promoted,errors} / backlog{pending,due_triggers}`
- **不变契约**：`/import/status` 响应结构与导入对话框三步交互（含第 2 步校验报错展示、浮卡最小化/恢复）**不得改动**（FR-013）。

### 12.4 错误码

| code | HTTP | 场景 |
|---|---|---|
| `job_not_found` / `run_not_found` | 404 | 定义、触发器或 run 不存在 |
| `job_paused` | 409 | `status=paused` 时 run-now |
| `job_unavailable` | 409 | `handler` 不在 `ExecutorRegistry` 白名单 |
| `invalid_field` | 400 | PATCH 含未知或只读字段 |
| `invalid_params` | 400 | `params` 未过 schema（附 `errors[{field,message}]`）|
| `invalid_cron_expr` / `invalid_interval` / `run_at_in_past` | 400 | 触发器参数校验 |
| `invalid_state_transition` | 409 | retry/cancel 状态不允许 |
| `run_create_failed` | 500 | 账本写入失败（run-now）|
| `invalid_schedule` | 400 | run-now 的 `scheduled_for` 超出 ±60s 容差（远期一次性应走 once 触发器） |
| `store_unavailable` | 503 | 账本/dispatcher 未注入 |

### 12.5 验收取证

- 后端：`python d:\filework\test.py --single <新增测试文件>`；重点用例见 §9.5「测试策略 · M5 新增」。
- 前端：`npx vitest run <相关 spec>`；页面手验 `/system/task-runs` 与 `/system/job-schedules`（含 `?run=` 深链、终态停轮询）。
- **无 job 专属组件（v1.4 取证）**：`src/components/common/` 下 MUST NOT 出现 job 命名或作业专用的 `.vue`；`src/components/` 下不得新增 `job/` 目录。取证方式：
  - `Glob src/components/common/*.vue` 与 `src/components/job/**` 结果比对（后者应为空）；
  - `Grep "status ===|TERMINAL|canCancel|canRetry" src/views/TaskCenter/TaskRuns.vue src/views/SystemManagement/JobSchedules.vue` 应为**零命中**（能力位只读后端 `capabilities`）；
  - `Grep "RUN_STATUSES|'pending'|'succeeded'" src/utils/jobRunStatus.js src/utils/jobParams.js` 仅允许出现在「文案映射表」中，不得参与判定逻辑。
- 接口：`curl.exe` + dev-login cookie 验证 400/409/503 分支，禁止用 `curl` 别名（L2）。