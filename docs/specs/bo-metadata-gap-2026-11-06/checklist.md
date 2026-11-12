# Checklist — 元数据平台缺口补全（S7 阶段）

> 本轮范围：T8.1 / T8.2 / T8.3（过账强制快照）/ T8.5 / T8.4（默认推导）。
> 暂缓：会计期间（D7）、修订族谱（D8）、元数据快照回滚（D9/T8.6）、14 单据全量启用 revision_policy（T8.3-b）。

- [x] `MetaDocumentProfile` 已落地，存量对象 `document_profile is None`（未声明 = 零影响）
- [x] `document:` 段解析与 fail-fast 校验（`[S7]` 前缀）：number_field / business_date_field / state_field / posting_state / reversal_profile
- [x] 跨对象校验 `validate_document_profiles()`：line_object 存在、line_parent_field / line_sequence_field 属于子对象、aspect 提供的 document_type_field / snapshot_fields 在切面合并后校验
- [x] `document_profile_service.py` 提供 `get_profile` / `require_profile` / `is_posting_state` / `enters_posting_state`
- [x] `purchase_order.yaml` 试点声明可加载（含 document_type_aspect 提供的 document_type_id）
- [x] 其余 13 个事实单据 YAML 已补 `document:` 声明，全量 schema 加载无 `[S7]` 报错
- [x] `field_policies:` 有 YAML 入口（`MetaObject.field_policies`）
- [x] 修复 `when_expr` 恒 False 缺陷（补 `safe_evaluate` import）
- [x] 角色规则求值顺序：系统字段 → 角色规则（未命中视为无意见）→ 状态矩阵 → 字段级默认
- [x] 3 处 `PolicyContext` 已传 `user_context`（bo_api 2 处 + field_policy_validation 1 处）
- [x] 是否传入 `user_context` 对存量行为无影响（无上下文 = 无意见）
- [x] `revision_service.record(forced=True)` 可在未启用 `revision_policy` 的对象上写整单快照
- [x] `action_executor` 在「跨入 posting_state」时写一条无差异 revision
- [x] 未进入 posting_state / 未声明 document_profile 时不额外产生 revision
- [x] 只读接口 `GET /api/v2/bo/<object>/<id>/revisions/<n>` 提供快照 + 字段差异；列表接口复用既有 IF-001
- [x] `derive_default_state_policy()` / `derive_deletability()` 仅在未显式声明时兜底
- [x] 新增测试全绿：`test_document_profile.py`(13) / `test_field_policy_role.py`(7) / `test_document_invariants.py`(6) / `test_document_revision_posting.py`(5)
- [x] 回归全绿：`test_field_policy.py` / `test_state_field_matrix.py` / `test_yaml_loader.py` / `test_revision_*.py`（合计 248 passed）
- [x] `tasks.md` 已同步勾选与偏差说明
