# M2 任务清单（规则化收敛）

> 方案：[2026-11-07-rule-convergence-m2-execution-plan.md](./2026-11-07-rule-convergence-m2-execution-plan.md)
> 规则：完成一项勾选一项；未勾选不得宣称完成。

- [x] M2-1 新增 `meta/core/state_machine_loader.py`
- [x] M2-2 `sales_order_schedule.yaml` / `serial_number.yaml` 增加 `states` + `state_transition` 规则
- [x] M2-3 `sales_order_guard_service.py` 改读声明（R-SCH-9）
- [x] M2-4 `serial_number_service.py` 改读声明（usage_status）
- [x] M2-5 `MetaObject.approval` + `approval_meta_loader.py` + 4 个 BO YAML `approval`
- [x] M2-6 `document_approval_service.py` 改读声明
- [x] M2-7 新增 `meta/core/rule_declaration_validator.py`
- [x] M2-8 扩展 `scripts/check_rule_convergence.py`（M2 常量 + 迁移守卫）
- [x] M2-9 新增 `meta/tests/test_rule_convergence_m2.py`
- [x] M2-10 目标测试 + `--failed` 串行回归
