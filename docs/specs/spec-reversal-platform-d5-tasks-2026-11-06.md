# D5 任务清单：调拨发货侧红冲

> 规格：`spec-reversal-platform-2026-11-06.md` §12 阶段 D5（方案已定稿）
> 语义：原地红冲发货事实（库存 REVERSAL + 红字补偿边），终态 `reversed`；
> 不新建反向调拨单；已收货只能走既有 `create_reversal()`。

## 实施顺序

| # | 状态 | 任务 | 文件 | 验收 |
|---|---|---|---|---|
| D5-1 | ✅ | 声明 `status.enum_values.reversed` + 顶层 `rules` + `doc_effect` | `meta/schemas/transfer_order.yaml` | YAML 加载无报错；V1-V6 校验通过 |
| D5-2 | ✅ | 新增 3 个原语并注册（14 → 17） | `meta/core/reversal_primitives.py` | 注册表含 `inventory_reverse_by_source` / `transfer_reverse_lines` / `recompute_transfer_fulfillment` |
| D5-3 | ✅ | `STATUS_REVERSED` + `TERMINAL_STATUSES` + `reverse_shipment()` + 错误映射 | `meta/services/transfer_order_service.py` | 守卫/幂等/错误码符合规格 |
| D5-4 | ✅ | BO 动作 handler | `meta/services/transfer_order_actions.py` | handler 可被动作框架调度 |
| D5-5 | ✅ | 动作注册与权限 | `meta/services/bo_action_registrations.py` | `transfer_order.reverse_shipment` 可见且受权限控制 |
| D5-6 | ✅ | 权限种子迁移 | `meta/migrations/v226__transfer_order_reverse.py` | 迁移幂等；`admin/default` 获授权 |
| D5-7 | ✅ | 新增回归 3 例 | `meta/tests/test_transfer_ship_reversal.py` | T1-T3 全绿 |
| D5-8 | ✅ | 回归与规格回填 | 既有测试 + 本规格 §8.1 / §12 | 目标套件全绿；§8.1 原语数 17、§12 D5 标 ✅ |

## 关键不变量

1. 仅 `status=released` 且总发货量 > 0 可红冲；总收货量 > 0 → `TO_RECEIVED_CANNOT_REVERSE`。
2. 已 `reversed` 再次调用：不执行编排、不开事务，返回 `idempotent=True`。
3. 失败全回滚（编排器自持事务，服务层不重复开事务）。
4. 库存反冲按来源单据枚举全部 `transfer_order:{id}:ship:{seq}` 事件键，
   镜像键为 `{原键}:reverse`；已红冲事件跳过。
5. 补偿边追加 `#rev:{doc_id}`，`quantity_sign='red'`、`status='active'`，指向原边。
6. 行 `qty_shipped=0`；履约派生重算为 `open`。

## 验证

```
python d:\filework\test.py --file meta/tests/test_transfer_ship_reversal.py,meta/tests/test_transfer_order_service.py,meta/tests/test_transfer_order_schema.py,meta/tests/test_transfer_order_guard.py,meta/tests/test_transfer_order_receipt_bridge.py,meta/tests/test_reversal_platform.py,meta/tests/test_reversal_orchestrator.py,meta/tests/test_yaml_loader.py
```

通过后再补跑：

```
python d:\filework\test.py --file meta/tests/test_transfer_shipment_doc_flow.py,meta/tests/test_reversal_primitives.py
```

## 不做

- 不新增 `reversed_at` / `reversal_reason` / `reversed_transfer_id` 列。
- 不改 `create_reversal()` 语义与既有反向草稿调拨单流程。
- 不处理部分发货批次的选择性红冲（整单发货事实红冲；部分批次走调拨发货单/反向调拨）。
- 不自行 git commit（等待用户指令）。
