# Schema → 测试覆盖矩阵报告

**生成时间**: 2026-07-17 14:44:41  
**Schema 总数**: 42

## 摘要

| 覆盖度 | 数量 | 占比 |
|---|---|---|
| 完全覆盖 (3 维) | 22 | 52% |
| 部分覆盖 (1-2 维) | 18 | 42% |
| 无覆盖 (0 维) | 2 | 4% |

## [!!!] 无测试覆盖的 schema

这些 schema 在所有 test_*.py 文件中均未出现, 意味着修改 yaml 不会触发任何测试失败。

| schema | table | yaml 文件 |
|---|---|---|
| `ai_async_task` | `ai_async_tasks` | `ai_async_task.yaml` |
| `new_object` | `new_objects` | `_template.yaml` |

## 部分覆盖的 schema

| schema | id 命中 | table 命中 | class 命中 | sample files |
|---|---|---|---|---|
| `audit_aspect` | 4 | 0 | 0 | test_yaml_driven_constraints.py, test_aspect_resolution.py |
| `change_subscription` | 2 | 2 | 0 | test_cascade_interceptor_detailed.py, test_deletion_service.py |
| `dimension_object_mapping` | 1 | 0 | 1 | test_dimension_scope_and_visibility_v105.py |
| `employee_data_scope` | 0 | 1 | 0 | test_condition_permission_service.py |
| `filter_variant` | 0 | 4 | 3 | test_cascade_interceptor_detailed.py, test_browser_e2e.py |
| `group_data_permission` | 0 | 9 | 0 | test_cascade_interceptor_detailed.py, test_association_multi_hop.py |
| `hierarchies` | 11 | 0 | 0 | test_p0_other_domains.py, test_cascade_bug_v013.py |
| `hierarchy_aspect` | 1 | 0 | 0 | test_aspect_resolution.py |
| `menu_permission` | 1 | 0 | 2 | test_cleanup_integrity.py, test_menu_permission_api.py |
| `naming_aspect` | 2 | 0 | 0 | test_aspect_resolution.py, test_version_cascade_delete.py |
| `owner_aspect` | 1 | 0 | 0 | test_aspect_resolution.py |
| `permission_bundle` | 2 | 0 | 2 | test_permission_services.py, test_permission_bundle_api.py |
| `role_permission` | 0 | 18 | 2 | test_cascade_interceptor_detailed.py, test_aggregate_manager.py |
| `scheduled_task` | 0 | 2 | 2 | test_scheduled_tasks_comprehensive.py, test_scheduled_tasks_e2e.py |
| `task_execution` | 0 | 2 | 0 | test_scheduled_tasks_e2e.py, test_task_scheduler.py |
| `task_queue` | 0 | 2 | 1 | test_scheduled_tasks_e2e.py, test_task_scheduler.py |
| `test_objects` | 6 | 6 | 0 | test_p1_custom_domains.py, test_hierarchy_bo.py |
| `test_table` | 8 | 8 | 0 | test_p1_custom_domains.py, test_audit_interceptor_comprehensive.py |

## 完全覆盖的 schema

| schema | 测试文件数 | 引用次数 |
|---|---|---|
| `user` | 209 | 1596 |
| `domain` | 153 | 1455 |
| `role` | 121 | 529 |
| `version` | 114 | 667 |
| `business_object` | 111 | 620 |
| `product` | 111 | 817 |
| `permission` | 105 | 180 |
| `sub_domain` | 91 | 456 |
| `service_module` | 76 | 524 |
| `relationship` | 64 | 466 |
| `user_group` | 60 | 307 |
| `audit_log` | 59 | 239 |
| `user_group_member` | 35 | 2 |
| `annotation` | 27 | 317 |
| `enum_type` | 23 | 97 |
| `enum_value` | 23 | 79 |
| `data_permission` | 17 | 14 |
| `menu` | 17 | 59 |
| `change_event` | 11 | 40 |
| `role_data_permission` | 11 | 9 |
| `permission_rule` | 8 | 12 |
| `role_dimension_scope` | 7 | 5 |

## 维度说明

**id 命中**: schema_id (e.g. `user`) 出现在测试文件中 (字符串字面量或路径)  
**table 命中**: table_name (e.g. `users`) 出现在测试文件中  
**class 命中**: 测试类名 `Test{SchemaIdCamel}` 出现

## 改进建议

- **P0**: 为无覆盖 schema 至少补 1 个 schema-id 级测试, 防止静默回归
- **P1**: 部分覆盖 schema 补齐缺失维度, 提升 schema-id ↔ test 关联性
- **P2**: 长期监控, 集成到 CI, 新增 schema 必须有至少 1 个 schema-id 级测试
