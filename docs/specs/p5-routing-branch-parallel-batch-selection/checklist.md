# P5 验收清单

> 对应 [spec.md](./spec.md) / [tasks.md](./tasks.md)。每项以测试或直读代码为证据。

## Schema

- [x] work_definition_sequence 声明 branch_operation_seq / return_operation_seq / lot_min / lot_max / priority，seq_type 含 std/parallel/alternative
- [x] work_definition_sequence 部分唯一索引 uq_work_definition_sequence_branch_priority + idx_work_definition_sequence_branch 已建
- [x] batches.grade_code（nullable、max_length 20）+ idx_batches_grade 已声明并建表
- [x] batch_selection_policy 对象：9 业务字段 + 审计列、3 索引（含 active 部分唯一）、3 值枚举、三态 UI、四权限

## 服务

- [x] WorkDefinitionSequenceService：G1–G12 图校验（写入硬失败 / 只读巡检告警）
- [x] validate_operation 覆盖 G11（被引用工序改号 / 工序压边界）
- [x] expand_sequences：std 基线、alternative 区间替换、parallel 并列、无 lot 回退
- [x] BatchSelectionPolicyService：scope 存在性、active priority 唯一、rule_json v1 白名单、模板、rule_hash
- [x] BatchSelectionService：item → item_group → org、同层 priority 升序、首条命中、无策略/全 0 抛错
- [x] 默认谓词 quality_status='unrestricted' AND status!='closed'；allow_blocked 放开 blocked/inspection 但仍排除 closed
- [x] 审计成功/失败载荷含 policy_code、rule_hash、batch_ids、attempted_policy_codes

## 拦截器与迁移

- [x] P57 / P58 两个拦截器已实现，并在 app_builder.py 与 server.py 双路径注册
- [x] v199 迁移：6 列、表、索引、枚举种子、权限与授权、菜单（sort_order 106）
- [x] v199 幂等（重复 migrate 打印 SKIP）与 rollback 可回退
- [x] 无破坏性改动：batch_attribute_values 未改；未建 selection_basis；未引入库存/成本/genealogy

## 测试

- [x] test_work_definition_sequence_graph.py 全绿
- [x] test_batch_selection_policy.py 全绿
- [x] test_work_definition_sequence_schema.py 全绿
- [x] test_batches.py 全绿
- [ ] 全量回归无新增失败
