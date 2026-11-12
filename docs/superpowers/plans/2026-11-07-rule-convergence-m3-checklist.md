# M3 验收清单（规则化收敛）

> 方案：[2026-11-07-rule-convergence-m3-execution-plan.md](./2026-11-07-rule-convergence-m3-execution-plan.md)
> 规则：每条必须有可复现证据（命令输出 / 文件行号），不得仅凭「已实现」。

## 一、FR-002 层级 / 维度单一真源

- [x] `hierarchies.yaml` 每层声明 `level_type / parent_level / owner_field`，level 6 为 association
- [x] `dimension_profiles.default == 4`、`full == 6`
- [x] `get_child_type_map('default')` 与旧 permission 引擎字面量逐项相等
- [x] `get_child_type_map('full', include_extra=True)` 与旧 condition 服务字面量逐项相等（含 `org:['org']`）
- [x] `get_scope_chain() == ['product','version','domain','sub_domain']`
- [x] 6 个消费者源码中无 `CHILD_TYPE_MAP = {` 等字面量
- [x] 追加收敛：`value_help_providers` / `runtime_dimension_resolver` / `bo_yaml_cache` / `data_permission_service` / `audit_derived_fields` / `permission_dimension_api` 均改为 loader 派生
- [x] 未知 profile 抛 `ValueError`（`get_dimension_profile_depth('nope')`）
- [x] `python scripts/check_rule_convergence.py` exit 0

## 二、FR-003 组织边界推导化

- [x] `REQUIRED_ORG_SCOPE_BOS` 已删除（grep 0 命中）
- [x] `org_scope_exemptions.yaml` 每条有非空 `reason`
- [x] 新构造含 `org_id` 未声明 BO → `ORG_SCOPE_UNDECLARED`
- [x] 空理由豁免 → `ORG_SCOPE_EXEMPTION_REASON_MISSING`
- [x] 带理由豁免后不报错

## 三、FR-010 Provider facade

- [x] `meta/services/*.py` 无 `from meta.core.doc_flow_rule_store import`
- [x] `meta/core/doc_flow_*.py` 无直连 store（`rule_provider.py` 除外）
- [x] `meta/services/*.py` 无 `from meta.core.permission_rule_v2_dao import`
- [x] 单据流目标测试全绿

## 四、FR-011 统一 explain

- [x] `explain()` 四场景均返回 `ok/scenario/decision/rule_id/source/reason/factors/elapsed_ms`
- [x] `POST /api/v2/bo/<object_type>/rules/explain` 非法入参返回 400
- [x] 调用前后业务表行数不变（只读）
- [x] 权限拒绝 / 状态流转拒绝原因可从接口获得

## 五、回归

- [x] `python d:\filework\test.py --file meta/tests/test_rule_convergence_m3.py` 全绿（19 例）
- [x] `python d:\filework\test.py --file meta/tests/test_org_scope_declarations.py` 全绿
- [x] `python d:\filework\test.py --file meta/tests/test_doc_flow.py` 全绿
- [x] `python d:\filework\test.py --file meta/tests/test_document_approval.py` 全绿（25 例）
- [x] `python d:\filework\test.py --failed` rerun 150 项，均为历史遗留，无新增失败
- [x] 未执行 git commit（等待用户授权）
