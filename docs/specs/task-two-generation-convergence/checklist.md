# Checklist：任务体系两代收口

> 验证方式：代码/文档静态核对 + DB 副本执行 + 受影响测试回归。

- [x] Gen2 六表 provisioning 迁移化：`meta/migrations/v154__provision_task_domain_tables.py` 存在，`verify()` 按 `task_schema` / `task_event_schema` 期望列比对；DB 副本空库跑后六表列数 workflows=14 / task_templates=27 / workflow_runs=16 / tasks=40 / task_events=16 / task_worklogs=16。
- [x] 启动期兜底：`meta/server.py` 在 seed 之后、scheduler 之前调用 `ensure_task_tables` + `ensure_task_event_tables`（失败仅告警）；`manage_api.py` 注释改为「兜底」。
- [x] `scheduled_tasks` 物理退役：`meta/migrations/v155__retire_scheduled_tasks.py` 以 RENAME→DROP backup 执行（DB 副本实测 0 rows），`verify()` 表与 backup 均不存在即 PASS；`rollback` 重建空表。
- [x] `meta/schemas/scheduled_task.yaml` / `task_queue.yaml` / `task_execution.yaml` 均已删除；`yaml_loader` 不再注册三表。
- [x] `meta/api/task_api.py` 仅保留 `status/reload`、`task-executions/*/retry|cancel`、`task-queues/stats`；`trigger/enable/disable` 返回 404（`test_scheduler_api.py` 10 passed）。
- [x] `meta/core/task_scheduler.py` 不再加载 `scheduled_tasks`、不再起调度线程；`start()` 仅加载队列并置 `_running=True`；`_execute_task` 保留账本写入。
- [x] `meta/scripts/init_task_seed.py` 无裸 DDL、无 `cleanup_legacy_scheduled_tasks`；建表唯一真源为 `meta/core/task_infra_schema.py`（`task_queues` 8 列 / `task_executions` 19 列）。
- [x] `meta/migrations/v156__adopt_task_infra_tables.py` 幂等接管两表（`CREATE TABLE IF NOT EXISTS` + 列校验 verify；rollback no-op 保留运行账本）。
- [x] `generated_schema.sql` 与 `.schema_version.json` 重新生成，无 `scheduled_tasks` / `task_queues` / `task_executions` 的 CREATE TABLE；`.schema_version.json` objects=124。
- [x] `test_task_scheduler.py`(13 passed/2 skipped)、`test_task_tick.py`(11 passed)、`test_scheduler_api.py`(10 passed)、`test_task_api.py`(5 passed)、`test_platform_scheduler.py`(13 passed)、`test_maintenance_scheduler.py`(10 passed)、`test_yaml_loader.py`(46 passed)、`test_schema_generator.py`(7 passed) 全部通过。
- [x] 真实库未触碰：`meta/architecture.db` SHA256 前后一致；迁移/幂等验证全部在副本（`_tmp_task_two_gen/arch_copy*.db`）上完成。
- [x] 文档：`docs/ARCHITECTURE_V3.md` §1.4 改为「两代分层共存（v154/v155/v156 收口后）」、附录 A P1 标记「已收敛」、CHANGELOG 追加 v3.11；`meta/schemas/README.md` 同步。
