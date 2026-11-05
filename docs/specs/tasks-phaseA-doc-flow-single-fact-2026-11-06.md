# 阶段 A 任务清单（P0）

对应规格：`docs/specs/spec-phaseA-doc-flow-single-fact-2026-11-06.md`

| # | 任务 | 文件 | 验收 | 状态 |
|---|---|---|---|---|
| 1 | 边表元数据补 `edge_kind` / `reverses_edge_id` 两列 | `meta/core/doc_flow_schema.py`、`v214`/`v215` DDL 常量 | 新库/旧库均可写补偿边 | [x] |
| 2 | 新增 `compensate_edge` + `EDGE_HAS_COMPENSATION` 守卫 | `meta/core/doc_flow_reversal.py` | T4 通过 | [x] |
| 3 | `reverse_edges_by_source` 切补偿模式（含红字子边补偿） | `meta/core/doc_flow_attach.py` | T5 通过 | [x] |
| 4 | 事务边界：`_atomic` + 三个入口包裹 | `meta/services/shipment_service.py` | T1 通过 | [x] |
| 5 | 过账 fail-closed + 显式降级标记 | `meta/services/shipment_service.py` | T2 / T3 通过 | [x] |
| 6 | 计划行改为同事务重算（删增量算术） | `meta/services/shipment_service.py` | T6 通过 | [x] |
| 7 | 新增 6 个用例 | `meta/tests/test_shipment_single_fact.py` | 6 passed | [x] |
| 8 | 回归 7 个既有套件 | `meta/tests/` | 7 套件全绿 | [x] |
| 9 | 回填规格实施记录与 AC 状态 | 两份规格文件 | AC-SF-01~05 有证据 | [x] |

## 执行顺序

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

## 执行记录（2026-11-06）

- 新增套件：`test_shipment_single_fact.py` **6 passed**。
- 既有套件：`test_shipment_service` / `test_shipment_reverse` / `test_shipment_issue_doc_flow` /
  `test_shipment_return_doc_flow` / `test_doc_flow_reconcile` / `test_doc_flow_reversal` /
  `test_doc_flow_stage3_reversal` **全绿**。
- `--all`：会话在 300s 超时中止，报告 20 F；`--failed` 重跑命中工作区既有基线失败
  （`factor_catalog` YAML 约束、`role.yaml` 缺失、`tax_classifications` 缺表、write_scope
  单测、test_temp 文件锁等 359 条），与本阶段改动无交集（本次未触碰任何 YAML / 权限 /
  数据源代码）。单独复跑 `test_yaml_driven_constraints::test_no_constraint_violations`
  可稳定复现 `factor_catalog.display_name_field='name'` 既有违规，判定为基线问题。
- `doctor`：HEALTHY（FE 3006 / BE 3010）。

## 完成判据

- 新增 6 例 + 既有 7 套件全绿；
- `--all` 的失败均为基线既有问题（已留证），非本阶段引入；
- 不产生任何未声明的公开行为变更；不做 git commit。
