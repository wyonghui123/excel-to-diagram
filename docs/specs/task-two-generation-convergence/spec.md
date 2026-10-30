# Spec：任务体系两代并存分析与收口方案

> 状态：已完成（已实现并回归；改动未提交 git）
> 日期：2026-10-30
> 关联：`docs/ARCHITECTURE_V3.md` §1.4 / 附录 A P1「任务体系两代并行未收敛」
> 依赖 spec：`docs/specs/spec-task-scheduler.md`（第一代原始设计，2026-05-23）
> 相关已完成 spec：`docs/superpowers/specs/2026-10-14-workflow-schedule-and-platform-ops-jobs.md`

***

## 1. 结论先行

两代**不是同一功能的版本迭代**，而是两个层次，且各自都处于"半迁移"状态：

| 层次   | 第一代（Gen1）                                                                    | 第二代（Gen2）                                                  |
| ---- | ---------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 真实定位 | **作业执行基础设施**（队列 + 执行账本 + cron 容器）                                            | **任务/编排领域模型**（任务、模板、工作流、运行、事件、工时）                          |
| 是否活着 | 队列与账本**仍在生产运行**（`action_dispatcher.py:103`、`bo_framework.py:684` 仍在 enqueue） | 领域层已接管前端与 API，但**六表全空**、无业务数据                              |
| 元模型  | YAML（3 个文件）+ `init_task_seed` 裸 DDL（**建表双份**）                                | 代码 MetaObject（`task_schema.py`）+ 运行时懒建表（**不在元模型体系内**）      |
| 定时配置 | 已实质废弃：`scheduled_tasks` **0 行**，每次启动被清理，cron 已内嵌代码                           | `workflow_schedule_scheduler` 从 `workflows` 定义表读取 schedule |

因此收口动作不是"二选一退役"，而是三件事：

1. **Gen1 的定时配置层（`scheduled_tasks`）已死**：应正式退役（删 YAML、删空表、删 DB 路由），但**队列/账本作为基础设施保留**。
2. **Gen2 的 provisioning 游离在三个真源之外**：应补 migration 并把建表挪到启动期，消除"首次 manage API 请求才建表"的隐式依赖。
3. **账本双轨（`task_executions`** **在写、`task_events`** **为空）**：本次**不改**，登记为独立缺口（属编排域重构，见 §7 范围外）。

***

## 2. 现状证据

### 2.1 建表路径（三轨并存）

| 轨                          | 表                                                                                            | 机制                                                                           | 证据                                                                                |
| -------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| ① YAML 元模型                 | `scheduled_tasks` / `task_queues` / `task_executions` / `ai_async_tasks`                     | `register_from_directory()` 全量注册 → `generate_create_table()`                 | `meta/schemas/scheduled_task.yaml:6,8`、`task_queue.yaml:6`、`task_execution.yaml`  |
| ② 裸 DDL 种子脚本               | 同上三表                                                                                         | `CREATE TABLE IF NOT EXISTS`（每次启动）                                           | `meta/scripts/init_task_seed.py:15,27,48`                                         |
| ③ 代码 MetaObject + 运行时 sync | `tasks` / `task_templates` / `workflows` / `workflow_runs` / `task_events` / `task_worklogs` | `ensure_task_tables()` → `sync_schema_from_meta()` + `register_table_name()` | `meta/core/task_schema.py:38-47,359,369-388`；`meta/core/task_event_schema.py:204` |

**关键事实**：轨③**唯一调用点**是 `meta/api/manage_api.py:63-64,70-71`，位于 `init_services()`（`manage_api.py:32`），由 `_get_manage_service()` 首次请求懒触发。`meta/server.py:153` 只从 `migration_runner` 导入了 `init_change_notification_tables`，**启动期不执行任何** **`meta/migrations/*`**（唯一批量入口是 `run_all_migrations()`，`meta/core/migration_runner.py:1148`）。

后果：全新部署且从未调用 manage API 时，Gen2 六表不存在 → `task_inbox_api`、`task_tick.platform_tick`、`workflow_api` 全部不可用。

### 2.2 调度真相

| 项                 | 现状                                                                                                                                                     | 证据                                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `scheduled_tasks` | **0 行**；启动时按 `maintenance_scheduler.JOB_CODES` 反复删除残留 cron 行                                                                                           | `meta/scripts/init_task_seed.py:151-189`（`DELETE ... WHERE code IN (...)` at :183）；`meta/core/maintenance_scheduler.py:14,28,55` |
| 真 cron            | 已内嵌代码：8 条运维作业 + `platform_tick` 每分钟 + workflow schedule                                                                                                | `maintenance_scheduler.py:55`；`platform_scheduler.py:44`；`workflow_schedule_scheduler.py:77,136,144`                             |
| `task_queues`     | **5 行**（DB）**+** 5 个 `QueueConfig`（代码）→ 双份配置                                                                                                           | `init_task_seed.py:136`；`server.py:670-682`                                                                                      |
| `task_executions` | **25642 行**，由 `task_scheduler` 持续写入                                                                                                                    | `task_scheduler.py:281`                                                                                                          |
| `TaskScheduler`   | 仍启动，仍消费队列（基础设施用途），但不再有 cron 作业可加载                                                                                                                      | `server.py:665,767-770`；`task_scheduler.py:100`（读空表）                                                                             |
| 门控不对称             | `task_api_bp`/`task_inbox_bp`/`task_decision_bp`/`workflow_bp` 受 `is_module_enabled('tasks')` 门控；`scheduler_bp` **无条件**；`TaskScheduler` 本体不受门控（有意，见注释） | `server.py:988-1005`；`platform_modules.py:30-33`                                                                                 |

### 2.3 API / 前端

* Gen1 API（`task_api_bp`）：`/api/v2/task-scheduler/status|reload`、`/tasks/<code>/trigger|enable|disable`、`/task-executions/<id>/retry|cancel`、`/task-queues/stats`（`meta/api/task_api.py:40,50,60,79,104,128,157,175`）。其中 `enable/disable` 直接 `UPDATE scheduled_tasks`（`:85,:110`），`retry/cancel` 读写 `task_executions`（`:135,:145,:165`）。

* Gen2 API：`meta/api/task_inbox_api.py`（`/api/v1/tasks`、`/task-inbox`、`/platform/tick`、`/events`、`/claim`）、`workflow_api.py`（`/api/v2/workflows/schedules`、`/scheduler/status`）、`task_decision_api.py`。

* 前端已收敛：`src/router/modules/system.js:44-50` 注释明确 4 条遗留路由已下线，`TaskCenter.vue` 读 `/api/v1/tasks`；`taskService.js:126-148` 走 Gen2 + workflow schedules。

* 写权限：`task_write_guard.py:33`（Gen2 四表）与 `:43`（Gen1 三表）**同时**视为 task-owned。

### 2.4 物理库实测（`meta/architecture.db` 只读）

`scheduled_tasks=0`、`task_queues=5`、`task_executions=25642`、`tasks=0`、`task_templates=0`、`workflows=0`、`workflow_runs=0`、`task_events=0`、`task_worklogs=0`、`ai_async_tasks=0`。
`generated_schema.sql` 只含 Gen1 表；`meta/migrations/` 中无 Gen2 四表 DDL（grep 无匹配）。

***

## 3. 结构性问题判定

| ID     | 问题                                                                                     | 性质                  | 严重度            |
| ------ | -------------------------------------------------------------------------------------- | ------------------- | -------------- |
| **P1** | 建表三轨并存：YAML、种子裸 DDL、代码懒建表；Gen2 不进 `meta/schemas`、不进 `generated_schema.sql`、无 migration | 真源分裂（与权限双轨同构）       | 高（全新部署不可用）     |
| **P2** | `scheduled_tasks` 空表 + DB 路由仍可 `enable/disable` 写它 + 启动反复清理                            | 僵尸 API 面（DB 写入无消费者） | 中              |
| **P3** | 账本双轨：`task_executions` 持续写 25642 行，`task_events` 0 行，无桥接                               | 领域模型断层              | 中（本次不改）        |
| **P4** | 队列配置双份（DB 5 行 + 代码 5 个 QueueConfig）                                                    | 配置真源分裂              | 低（代码为准，DB 仅统计） |
| **P5** | 门控不对称（`scheduler_bp` 无条件；`TaskScheduler` 豁免）                                           | 有意设计，缺文档            | 低（登记而非修复）      |

***

## 4. 目标架构（决策）

**分层不变，边界显式化：**

```
Gen1 = Infra Execution Layer（保留）
  task_queues（队列定义，代码为真源，DB 仅供统计/兼容）
  task_executions（作业执行账本，历史 25642 行保留）
  TaskScheduler（消费队列；不再承载 cron）
  ✗ scheduled_tasks（退役）

Gen2 = Task/Orchestration Domain（目标形态）
  tasks / task_templates / workflows / workflow_runs / task_events / task_worklogs
  provisioning 真源 = meta/migrations（唯一）
  启动期显式 ensure（幂等兜底列补齐）
```

### 4.1 决策清单

| 决策                                                | 选择                                                | 理由                                                                             |
| ------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------ |
| D1 Gen1 队列/账本                                     | **保留**，不迁 Gen2                                    | `action_dispatcher.py:103`、`bo_framework.py:684` 仍在使用；迁移成本 > 收益                |
| D2 `scheduled_tasks`                              | **退役**（YAML + 表 + DB 写路由）                         | 0 行、启动即清理、cron 已在代码；表无任何生产者                                                    |
| D3 Gen2 provisioning                              | **migration v139 为唯一真源** + `server.py` 启动期 ensure | 不引入元模型 YAML（Gen2 明确"非业务 BO、不进 registry"，`task_schema.py:369-388` 注释），同时消除懒触发依赖 |
| D4 Gen1 表 provisioning                            | **migration v141 接管**，`init_task_seed` 删建表段       | 消除轨①②双份 DDL 漂移；队列种子数据保留                                                        |
| D5 Gen1 `task_queue.yaml` / `task_execution.yaml` | **删除**（表与运行时保留）                                   | 表已由迁移接管；YAML 仅剩建表副作用，且菜单早已下线（`init_task_menus.py:9-10`）                        |
| D6 账本统一（`task_executions` → `task_events`）        | **本次不做**，登记缺口                                     | 属编排域重构，需独立 spec；避免一次批次过大                                                       |
| D7 `task_write_guard` Gen1 表名                     | **保留**                                            | 表仍存在且属 task-owned；仅更新注释                                                        |

> **重要**：D3 与 D5 后，`generated_schema.sql` 将不再包含 Gen1 三表与 `ai_async_tasks`（若一并退役）。这是预期结果，不是回归；需同步 `meta/schemas/README.md` 与文档。

***

## 5. 变更清单（Phase A：Gen2 provisioning 收口）

> Phase A 零业务风险，建议先批准执行。Phase B（Gen1 YAML 退役）单列，见 §6。

| #  | 文件                                                             | 变更                                                                                                                                                                                                                                                                                                              |
| -- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1 | **新增** `meta/migrations/v139__provision_task_domain_tables.py` | 幂等 `CREATE TABLE IF NOT EXISTS` 六表（`tasks`/`task_templates`/`workflows`/`workflow_runs`/`task_events`/`task_worklogs`）；`verify()` 比对 `task_schema.build_task_meta_objects()` 与 `task_event_schema` 的列集合（只读导入，不复制 DDL 语义）；`rollback()` = no-op（provisioning 迁移不回滚建表）；`migrate(db_path, skip_backup=False)->bool` |
| A2 | `meta/server.py`                                               | 启动期显式调用 `ensure_task_tables(_data_source)` 与 `ensure_task_event_tables(_data_source)`（位置：`init_task_seed_data` 之后、scheduler 启动之前）；保留 `manage_api` 懒调用（幂等）                                                                                                                                                       |
| A3 | `meta/api/manage_api.py:63-71`                                 | 注释更新为"兜底（启动期已 ensure）"，逻辑不变                                                                                                                                                                                                                                                                                     |
| A4 | `docs/ARCHITECTURE_V3.md` §1.4 / 附录 A                          | 更新为"分层判定 + Phase A 已收敛 / Phase B 待批"；CHANGELOG 增 v3.11 行                                                                                                                                                                                                                                                        |

**验收**：全新空 DB 不调 manage API，启动后六表存在且列齐全；`migrations` 记录含 v139；重复启动幂等。

***

## 6. 变更清单（Phase B：Gen1 定时配置退役，需单独批准）

| #  | 文件                                                                                                                      | 变更                                                                                                                                                        |
| -- | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1 | **删除** `meta/schemas/scheduled_task.yaml`                                                                               | 同时删除其权限声明 `scheduled_task_crud`（yaml:202-223）；需检查权限种子/菜单引用                                                                                                |
| B2 | **新增** `meta/migrations/v140__retire_scheduled_tasks.py`                                                                | 空表按仓库约定 `RENAME → DROP backup`（0 行，先 rename 再 drop）；`rollback()` 重建空表                                                                                     |
| B3 | `meta/api/task_api.py`                                                                                                  | 删除 `trigger/enable/disable`（依赖 `scheduled_tasks`，:60,:79,:85,:104,:110）；保留 `status/reload`（如确认读进程内调度器，见 B3 前置核查）与 `task-executions/*`、`task-queues/stats` |
| B4 | `meta/core/task_scheduler.py`                                                                                           | 移除 `SELECT/UPDATE scheduled_tasks`（:100,:182）及对应加载循环；保留队列消费与 `_create_execution_record`（:281）                                                             |
| B5 | `meta/scripts/init_task_seed.py`                                                                                        | 删除 `cleanup_legacy_scheduled_tasks()`（:151-189）及 `server.py:180` 后的调用链；保留队列种子（:136）                                                                       |
| B6 | **删除** `meta/schemas/task_queue.yaml` / `task_execution.yaml`；**新增** `meta/migrations/v141__adopt_task_infra_tables.py` | 幂等接管两表 DDL（DDL 从 `init_task_seed.py:15-60` 迁入）；删除种子脚本中的建表段                                                                                                |
| B7 | `meta/core/task_write_guard.py:42-43`                                                                                   | 注释改为"Gen1 表仍存在（迁移接管）"                                                                                                                                     |
| B8 | `meta/schemas/README.md` + `generated_schema.sql` + `.schema_version.json`                                              | 移除三表条目；`python -m meta.tools.sync_schema --generate` 重生成                                                                                                  |
| B9 | 测试                                                                                                                      | 删除/改写 `test_scheduled_tasks_e2e.py`、`test_task_scheduler.py` 中 cron 用例；`test_yaml_loader.py` 断言随 YAML 删除更新；检查 `test_schema_generator.py` 对全量表的断言          |

**B3 前置核查（必须先行）**：确认 `status/reload` 是否只读进程内调度器；确认无 E2E/外部消费者调用 `trigger/enable/disable`（grep `task-scheduler|/tasks/.*trigger`）。

***

## 7. 范围外（登记缺口，另立 spec）

1. **账本统一**：`task_executions`(25642) 与 `task_events`(0) 的投影/归档策略。
2. **队列配置双份**（P4）：DB `task_queues` 5 行与代码 `QueueConfig` 的收敛。
3. **门控文档化**（P5）：`TaskScheduler` 基础设施豁免写进 ARCHITECTURE §1.4。

***

## 8. 验证方案

```powershell
# 单元/回归（唯一合法入口）
python d:\filework\test.py --single meta/tests/test_migration_runner.py
python d:\filework\test.py --single meta/tests/test_yaml_loader.py
python d:\filework\test.py --single meta/tests/test_task_scheduler.py
python d:\filework\test.py --single meta/tests/test_schema_generator.py
python d:\filework\test.py --single meta/tests/test_task_inbox_api.py

# Phase A 空库验收（DB 副本，不碰真实库）
# 1) 复制空库 → 跑 v139 → 检查六表 + schema_migrations
# 2) 二次执行 → 幂等
# 3) 启动仅初始化（不调 manage API）→ 六表存在

# 全量
python d:\filework\test.py --all
python d:\filework\test.py --failed   # 并行假失败必须串行确认
```

**禁止**：直接 `pytest`；直接对 `meta/architecture.db` 执行迁移（一律副本验证，真实库由部署流程执行）。

***

## 9. 风险与缓解

| 风险                                     | 影响         | 缓解                                                   |
| -------------------------------------- | ---------- | ---------------------------------------------------- |
| R1 `generated_schema.sql` 有消费者/测试断言全量表 | Phase B 回归 | 先 grep 消费者；`test_schema_generator` 先行跑               |
| R2 migration 与 `task_schema.py` 列定义漂移  | 建表列不一致     | v139 `verify()` 动态比对列集合；`ensure_task_tables` 作为列补齐兜底 |
| R3 `task_api` 有外部消费者                   | 404        | B3 前置 grep + 保留 4 条非 `scheduled_tasks` 路由            |
| R4 权限种子引用 `scheduled_task_crud`        | 孤儿权限       | B1 前置 grep `scheduled_task_crud`，同步清理                |
| R5 启动期 ensure 拖慢启动                     | 秒级         | `sync_schema_from_meta` 表存在即跳过；实测 < 1s               |

***

## 10. 需批准的决策点

1. 是否接受 **D1（Gen1 队列/账本保留，不并入 Gen2）**？
2. Phase A（v139 + 启动期 ensure）是否立即执行？
3. Phase B 是否同批执行，还是先 Phase A 观察一轮？
4. `ai_async_tasks`（0 行，YAML 存在）是否随 Gen1 一并退役？（默认：本次不动，单列）
5. `task_executions` 历史 25642 行：保留原表继续写（默认）还是立即归档只读？

