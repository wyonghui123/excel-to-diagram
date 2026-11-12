# M2 验收检查表（规则化收敛）

> 方案：[2026-11-07-rule-convergence-m2-execution-plan.md](./2026-11-07-rule-convergence-m2-execution-plan.md)
> 每项通过后勾选，并记录命令与结果。

- [x] C1 计划行状态机与旧 `SCHEDULE_TRANSITIONS` / `SCHEDULE_TERMINAL` / `SCHEDULE_STATUSES` 逐项相等
  - `test_rule_convergence_m2.py::test_schedule_machine_matches_legacy` 通过
- [x] C2 序列号状态机与旧 `TRANSITIONS` 逐项相等（含元组顺序）
  - `test_serial_machine_matches_legacy` / `test_serial_states_equal_service_constant` 通过
- [x] C3 计划行守卫错误码 / 提示文案 / `field_name` 零变化
  - `test_sales_order_schedule_guard.py` 全绿
- [x] C4 序列号 `change_status` 错误码 / 提示文案零变化
  - `test_serial_number_service.py` 全绿
- [x] C5 4 个审批对象 table 与金额优先级等于旧常量
  - `test_approval_meta_matches_legacy` / `test_approval_amount_priority` 通过
- [x] C6 非法流转与审批拒绝的对外错误码 / HTTP 状态零变化
  - `test_document_approval.py` 全绿；服务仅替换取值来源
- [x] C7 `/state_transitions` 输出零变化（规则全部 `ui_hints.hidden: true`）
  - `test_state_machines_are_hidden_and_not_triggered` 通过；`bo_api` 仅返回非 hidden
- [x] C8 FR-012 校验器正例为空、负例命中稳定错误码
  - 4 个 `*_negative` 用例通过
- [x] C9 `scripts/check_rule_convergence.py` exit 0
  - 已执行，exit 0
- [x] C10 `test.py --failed` 无新增失败
  - 161 项历史遗留失败（write_scope / vendor_account / permission 等），
    M2 涉及的 8 个测试文件全部全绿
