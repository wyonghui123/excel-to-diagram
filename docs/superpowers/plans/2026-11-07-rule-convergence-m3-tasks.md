# M3 任务清单（规则化收敛）

> 方案：[2026-11-07-rule-convergence-m3-execution-plan.md](./2026-11-07-rule-convergence-m3-execution-plan.md)
> 规则：完成一项勾选一项；未勾选不得宣称完成。

- [x] M3-1 `hierarchies.yaml` 补 `level_type/parent_level/owner_field` + `dimension_profiles` + `extra_entity_tables`
- [x] M3-2 `meta/core/hierarchy_loader.py` 新增 `get_dimension_levels / get_dimension_profile_depth / get_child_type_map / get_extra_entity_map / get_extra_entity_table_map`
- [x] M3-3 6 个消费者去字面量（permission / management / condition / chain_owner / dimension_scope / value_help）
- [x] M3-4 扫描候选 BO，生成 `meta/schemas/org_scope_exemptions.yaml`（理由必填）
- [x] M3-5 `meta/core/org_scope_validator.py` 推导化，删除 `REQUIRED_ORG_SCOPE_BOS`
- [x] M3-6 `meta/tests/test_org_scope_declarations.py` 适配 + 负例
- [x] M3-7 `meta/core/rule_provider.py` 新增 DB 门面 + 替换 5 处调用点
- [x] M3-8 新增 `meta/core/rule_explainer.py`（default / permission / state_transition / approval）
- [x] M3-9 `meta/api/bo_api.py` 新增 `POST /api/v2/bo/<object_type>/rules/explain`
- [x] M3-10 扩展 `scripts/check_rule_convergence.py`
- [x] M3-11 新增 `meta/tests/test_rule_convergence_m3.py`（14 例）
- [x] M3-12 目标测试 + `--failed` 串行回归
