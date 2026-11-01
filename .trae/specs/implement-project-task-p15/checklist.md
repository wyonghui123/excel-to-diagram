# Checklist

- [x] `project_tasks` 声明 `project_id` required、`task_no` 项目内唯一、四态状态机可达 done / cancelled
- [x] `project_task_dependencies` 只允许 `FS / SS / FF / SF`，`lag_minutes` 为整数且允许负数
- [x] `work_order.source_demand_type` 枚举包含 `project_task`
- [x] `source_demand_type='project_task'` 时缺 `source_demand_id` 抛 `ST_SOURCE_DEMAND_REQUIRED`
- [x] 任务不存在抛 `ST_SOURCE_DEMAND_INVALID`
- [x] 工单与任务跨项目抛 `ST_PROJECT_MISMATCH`；缺省项目回填任务项目
- [x] 迁移 v179 可建表 / 建索引 / 建权限 / 建菜单，重复执行 `[SKIP]`，`verify` 通过，`rollback` 删表保留权限
- [x] `generated_schema.sql` 含两张新表与六条索引
- [x] `test_project_p15.py` 21 passed；P1 35 / P2b1 25 / production 15 / service 17 全绿
- [x] spec 变更记录 v1.7 / v0.7 落地，工时回聚视图标注「待 G7」
- [x] 改动仅在 worktree，未动主工作树
