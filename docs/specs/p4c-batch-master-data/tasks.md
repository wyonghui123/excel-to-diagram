# P4c 批次主数据实施任务

> 规格: [spec.md](./spec.md)；批准后按序执行，每项完成即验证。

## T1 Schema 声明（batches）

- 文件: `meta/schemas/batches.yaml`
- 内容: 对象 `batch`，表 `batches`；13 个业务/审计字段；3 组内联枚举；7 条索引（含唯一 `(item_id, org_id, batch_no)`）；4 条关系（item / org / uom / parent 自引用）；`deletion_policy.mode=restrict`；`ui_view_config.skip_auto_menu=true` + list/form/detail 三态。
- 验收: `python d:\filework\test.py --single meta/tests/test_batches.py` 中 YAML 用例通过。

## T2 Schema 声明（batch_attribute_values）

- 文件: `meta/schemas/batch_attribute_values.yaml`
- 内容: 严格照 `_attribute_value_template.yaml`；`parent_object: batch`；唯一 `(tenant_id, batch_id, attribute_id, seq)`；`(attribute_id)` 与 `(tenant_id, batch_id)` 索引；两条真外键 relation。
- 验收: 模板对齐用例通过。

## T3 BatchService

- 文件: `meta/services/batch_service.py`
- 内容: `BatchError`；`BatchService.validate_batch`（16 条规则码，见 spec §3.1）；`validate_required_attributes`（按 `item_group_code` 解析 `scope_ref='batch'` 必填项）。
- 验收: 服务单测全绿。

## T4 BatchAttributeValueService

- 文件: `meta/services/batch_attribute_value_service.py`
- 内容: 子类 `AttributeValueService`，仅覆写 `VALUE_TABLE` / `OWNER_FIELD`。
- 验收: 五值列、互斥、active、租户、seq 用例通过。

## T5 守卫拦截器

- 新增 `meta/core/interceptors/batch_guard_interceptor.py`（P56）。
- 修改 `meta/server.py` 与 `meta/core/app_builder.py` 注册（两处必须同时改）。
- 修改 `meta/core/interceptors/attribute_guard_interceptor.py`：`GUARDED_OBJECTS` 加 `batch_attribute_value`，分支调用新服务。
- 验收: interceptor 用例 + 启动路径不报 ImportError。

## T6 `attribute_scope.yaml` 语义注释

- 文件: `meta/schemas/attribute_scope.yaml`
- 内容: 补 `item_group` 在批次场景下的语义扩展说明（仅注释）。
- 验收: diff 仅注释行。

## T7 迁移 v196

- 文件: `meta/migrations/v196__batch_foundation.py`
- 内容: 建 2 表（含 FK/CHECK）+ 10 条索引 + 3 组枚举 + 8 条权限与授权 + 菜单 `batch-management`；`verify` / `rollback` / 幂等。
- 验收: 迁移用例（migrate→verify→重跑→rollback）通过。

## T8 测试

- `meta/tests/test_batches.py`：YAML / 迁移 / 唯一约束 / BatchService 全规则。
- `meta/tests/test_batch_attribute_values.py`：YAML / 值服务 / 守卫拦截器。
- 验收: 两个 `--single` 均通过。

## T9 回归与报告

- `python d:\filework\test.py --failed`（若有失败串行复跑）。
- 输出改动清单 + 测试结果；**不 commit**。
