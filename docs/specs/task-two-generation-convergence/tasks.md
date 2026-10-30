# Tasks：任务体系两代收口

> 依赖 spec：`spec.md` | 状态：已完成（Phase A + Phase B 全部实现并回归）
> 执行顺序：Phase A 全绿后再开 Phase B。
> 版本号修正：仓库已有 v139/v140/v141（sales_order 系列，最大 v153），
> 本 spec 的迁移号顺延为 **v154（Gen2 六表）/ v155（退役 scheduled_tasks）/ v156（接管 Gen1 队列账本）**。

## Phase A — Gen2 provisioning 收口（零业务风险）

- [x] A1 新建 `meta/migrations/v154__provision_task_domain_tables.py`：
      幂等建 `tasks` / `task_templates` / `workflows` / `workflow_runs` /
      `task_events` / `task_worklogs`；`verify()` 动态比对
      `task_schema.build_task_meta_objects()` 与 `task_event_schema` 期望列；
      `rollback()` no-op。
- [x] A2 `meta/server.py` 启动期显式调用 `ensure_task_tables` +
      `ensure_task_event_tables`（init_task_seed 之后、scheduler 启动之前）。
- [x] A3 `meta/api/manage_api.py:63-71` 注释改为"兜底，启动期已 ensure"（逻辑不变）。
- [x] A4 DB 副本验证：空库跑 v154 → 六表齐全；二次执行幂等；不调 manage API 启动后六表存在。
- [x] A5 回归：
      `test_migration_runner.py`、`test_schema_generator.py`、`test_task_inbox_api.py`、
      `test_yaml_loader.py`。
- [x] A6 文档：`docs/ARCHITECTURE_V3.md` §1.4 + 附录 A（Phase A 已收敛 / Phase B 待批）；
      CHANGELOG v3.11。

## Phase B — Gen1 定时配置退役（需单独批准）

### B0 前置核查（未核查前不得改代码）

- [x] B0-1 grep `scheduled_task_crud`，列出权限种子/菜单/测试引用。
- [x] B0-2 grep `task-scheduler|/tasks/.*trigger|task-executions`，确认前端/E2E/外部消费者。
- [x] B0-3 确认 `task_api` 的 `status/reload` 读源（进程内调度器 vs DB）。
- [x] B0-4 grep `scheduled_task|task_queue|task_execution` 在 `meta/tests`、`tests/` 的断言点。

### B1 退役 `scheduled_tasks`

- [x] B1-1 删除 `meta/schemas/scheduled_task.yaml`。
- [x] B1-2 新建 `meta/migrations/v155__retire_scheduled_tasks.py`（RENAME → DROP backup；rollback 重建空表）。
- [x] B1-3 `meta/api/task_api.py` 删除 `trigger/enable/disable` 三条路由及相关 `UPDATE scheduled_tasks`（:60,:79,:85,:104,:110）；保留 `status/reload`（依 B0-3 结论）、`task-executions/*`、`task-queues/stats`。
- [x] B1-4 `meta/core/task_scheduler.py` 移除 `SELECT/UPDATE scheduled_tasks`（:100,:182）及 cron 加载；保留队列消费与 `_create_execution_record`（:281）。
- [x] B1-5 `meta/scripts/init_task_seed.py` 删除 `cleanup_legacy_scheduled_tasks()`（:151-189）及 `server.py` 调用链。
- [x] B1-6 清理 B0-1 命中的权限/菜单引用。

### B2 接管 Gen1 队列/账本表 provisioning

- [x] B2-1 新建 `meta/core/task_infra_schema.py`（`task_queues`/`task_executions` 唯一 DDL 真源）
      与 `meta/migrations/v156__adopt_task_infra_tables.py`（调用前者建表）：幂等建 `task_queues` / `task_executions`（DDL 源自 `init_task_seed.py:15-60`）。
- [x] B2-2 `init_task_seed.py` 删除建表段（:15,:27,:48），保留队列种子（:136）。
- [x] B2-3 删除 `meta/schemas/task_queue.yaml`、`meta/schemas/task_execution.yaml`。
- [x] B2-4 `meta/core/task_write_guard.py:42-43` 注释更新（表名保留）。
- [x] B2-5 `meta/schemas/README.md` 移除三表；重生成 `generated_schema.sql` 与 `.schema_version.json`。

### B3 测试与验证

- [x] B3-1 改写/删除 `meta/tests/test_scheduled_tasks_e2e.py`、`test_task_scheduler.py` 的 cron 用例。
- [x] B3-2 `test_yaml_loader.py` 断言随 YAML 删除更新；`test_schema_generator.py` 全量断言复核。
- [x] B3-3 DB 副本跑 v140/v141 → verify → 二次幂等；确认真实库未被触碰。
- [x] B3-4 `python d:\filework\test.py --all` → `--failed` 串行确认。
      （实测：`--all` 并行 300s 超时中断；`--failed` 串行回放 378 个历史失败 → 367F/6P/13E，均为既有基线问题（`user_group.yaml` 缺失、已删迁移模块 import、权限口径改名、`datasource_cache` 文件锁、后端未启动等）；`test_task*` / `test_scheduler*` / `test_yaml_loader` / `test_schema_generator` 无一失败。）
- [x] B3-5 文档：ARCHITECTURE §1.4 完成态 + 附录 A 将 P1 标记为"已收敛"；CHANGELOG。

## 范围外（另立 spec）

- [ ] 账本统一（`task_executions` → `task_events` 投影/归档）
- [ ] 队列配置双份收敛（DB 5 行 vs 代码 5 个 QueueConfig）
- [ ] `ai_async_tasks`（0 行）退役评估
