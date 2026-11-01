# Tasks

- [x] Task 1: 新建 `meta/schemas/project_task.yaml`（字段 / 四态状态机 / 项目内唯一索引 / project 真外键）
- [x] Task 2: 新建 `meta/schemas/project_task_dependency.yaml`（FS/SS/FF/SF + lag / 三列唯一 / 双外键）
- [x] Task 3: `work_order.yaml` 的 `source_demand_type` 扩 `project_task`（G11）并同步文件头注释
- [x] Task 4: `work_order_service.py` 增 `project_task` 需求分支 + 同项目校验与回填
- [x] Task 5: 新建 `v179__project_task_p15.py`（建表 / 索引 / 权限 / 手工菜单 / 幂等 / 回滚）并在 `init_menu_permissions.py` 声明菜单
- [x] Task 6: `python -m meta.tools.sync_schema --generate` 同步 `generated_schema.sql`
- [x] Task 7: 新建 `meta/tests/test_project_p15.py`（AC-09 四点 + 迁移 + DDL 一致性），21 passed
  - [x] 单文件：`python scripts/agent_test.py --file .../test_project_p15.py --port 3014 -q`
- [x] Task 8: 更新 spec 变更记录（project v1.7 / milestone v0.7）
- [x] Task 9: 回归 4 个既有测试文件（35 / 25 / 15 / 17 全绿）
- [x] Task 10: 仅在 worktree 提交，不 merge

# Task Dependencies

- Task 2 依赖 Task 1
- Task 4 依赖 Task 1、Task 3
- Task 5 依赖 Task 1、Task 2
- Task 7 依赖 Task 1–6
- Task 9 依赖 Task 7
- Task 10 依赖 Task 8、Task 9
