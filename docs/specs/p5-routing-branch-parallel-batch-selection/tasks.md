# P5 实施任务

> 规格: [spec.md](./spec.md)；批准后按序执行，每项完成即验证。不 commit。

## [x] T1 Schema：work_definition_sequence

- 文件: `meta/schemas/work_definition_sequence.yaml`
- 内容: 追加 `branch_operation_seq` / `return_operation_seq` / `lot_min` / `lot_max` / `priority`；`seq_type` 加 `parallel`；2 条索引（部分唯一 + branch）；UI 分组「分支 / 适用范围」与三态字段补全。
- 验收: `test_work_definition_sequence_schema.py` 翻新用例通过。

## [x] T2 Schema：batches + batch_selection_policy

- 文件: `meta/schemas/batches.yaml`（`grade_code` + `idx_batches_grade`）
- 文件: `meta/schemas/batch_selection_policy.yaml`（新对象：9 业务字段 + 审计列、3 索引、枚举、三态 UI、四权限）。
- 验收: `test_batches.py` YAML 用例 + `test_batch_selection_policy.py` 声明用例通过。

## [x] T3 WorkDefinitionSequenceService

- 文件: `meta/services/work_definition_sequence_service.py`
- 内容: `WorkDefinitionSequenceError`、`validate_sequence`（G1–G10）、`validate_sequence_graph`（G1–G12 告警）、`validate_operation`（G11）、`expand_sequences`（替代/并行/回退）。
- 验收: 图规则与展开用例全绿。

## [x] T4 批次选择服务

- 文件: `meta/services/batch_selection_policy_service.py`
  - `BatchSelectionPolicyError`、`validate_policy`、`rule_hash`、`RULE_TEMPLATES`。
- 文件: `meta/services/batch_selection_service.py`
  - `InvalidSelectionRuleError`、`NoBatchMatchError`、`BatchSelectionResult`、`select_batches`（默认谓词 / 三层解析 / 首条命中 / 审计成功与失败）。
- 验收: 策略保存与选择用例全绿。

## [x] T5 拦截器与双路径注册

- 新增 `meta/core/interceptors/work_definition_sequence_guard_interceptor.py`（P57）。
- 新增 `meta/core/interceptors/batch_selection_policy_guard_interceptor.py`（P58）。
- 修改 `meta/core/app_builder.py` 与 `meta/server.py` 各注册两个拦截器。
- 验收: 启动路径导入无错；非法保存被转 `ValidationFailedError`。

## [x] T6 迁移 v199

- 文件: `meta/migrations/v199__routing_p5.py`
- 内容: 5 列 + `grade_code` + `idx_batches_grade`；`sequence_type.parallel`；2 新枚举；`batch_selection_policies` 表 + 3 索引；4 权限与授权；菜单 `batch-selection-policy-list`（sort_order 106）。
- 接口: `migrate(db_path, skip_backup=False)` / `verify(db_path)` / `rollback(db_path)` / `downgrade = rollback`；幂等。
- 验收: `migrate → verify → 再 migrate → verify → rollback → verify 失败`。

## [x] T7 测试

- 新建 `meta/tests/test_work_definition_sequence_graph.py`（§7.1 全部项）。
- 新建 `meta/tests/test_batch_selection_policy.py`（§7.2 全部项）。
- 修改 `meta/tests/test_work_definition_sequence_schema.py`（翻转 2 个旧断言 + 索引）。
- 修改 `meta/tests/test_batches.py`（`grade_code` 字段 + 索引）。
- 验收: 4 个 `--single` 均通过。

## T8 回归与报告

- `python d:\filework\test.py --failed`（若有并发假失败，串行复跑确认）。
- 输出改动清单 + 测试结果；**不 commit**。
