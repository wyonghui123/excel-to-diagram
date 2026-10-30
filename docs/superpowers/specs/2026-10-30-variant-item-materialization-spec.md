# 变式物料化（Variant Item Materialization）Spec

> 版本 v1.0 · 2026-10-30 · 状态：待评审（decision-complete）
> 上游：`docs/specs/p2-master-data-pricing-variant/spec.md` §3.4（Phase 1 边界）
> 定位：把「配置实例（configuration）」固化为「可交易物料（items 新行）」，即 `items.config_materialize_policy` 的消费端 + `configurations.variant_item_id` 的写入端。
> 一句话：**物料化是主数据动作，不是订单动作**——它产出的是 `draft` 物料，必须走签发才能被单据引用。

---

## 0. 现状（实测，2026-10-30）

| 项 | 事实 | 证据 |
|---|---|---|
| 声明已落 | `items.config_materialize_policy`：必填、默认 `off`、枚举 `off/manual/auto` | `meta/schemas/items.yaml:325-342` |
| 接收列已落 | `configurations.variant_item_id`：可空、真外键 → `item`、关系 `configuration_to_variant_item` N:1 | `meta/schemas/configuration.yaml:281-336` |
| 迁移已落 | v117「只留位置不取值」 | `meta/migrations/v117__configuration_price_and_materialize_fields.py` |
| 消费者 | **无**（`meta/services` 无 `config_materialize_policy` 读取） | 静态扫描 0 命中 |
| 写入点 | **无**（`variant_item_id` 无任何赋值语句） | 静态扫描 0 命中 |
| 现状固化 | 3 个断言（默认 off / manual 链路不写 / 无写入点） | `meta/tests/test_configuration_materialize_inert.py`（3 passed） |

本 spec 落地后，上述「无消费者/无写入点」两条断言**必然失效**，需按 §6.3 改写该测试（不是删掉）。

---

## 1. Oracle 对标（公开手册，2026-10-30 检索）

研究产品：Oracle EBS「Configure to Order（CTO）」、Oracle Fusion Cloud SCM「Configurator / Configured Item」；横向对照 SAP 变式配置。

### 1.1 关键做法

| 维度 | Oracle 做法 | 依据 |
|---|---|---|
| 触发时机 | EBS 在订单推进到「Create Configuration Item」活动时生成（booking/排程后 workflow 或 AutoCreate 批处理）；Fusion 在订单提交时 item generation | EBS OM Implementation Manual · CTO |
| 唯一性/复用 | 按「选项组合集合」匹配可复用已有配置物料；Fusion 物料属性 `Match Configuration`（No / One time / Standard / User-defined），EBS 有 `BOM: Match to Existing Configurations` | 同上 + Fusion Item Manufacturing Attributes |
| 编码 | 「模型号 + 序号/流水」，分隔符可配（EBS `Numbering Method`: Append with sequence → `CN97444*1236-Laptop`；Fusion Sequence：`CTO_474000-100`） | EBS CTO Setup / Fusion Set Up Numbers for Configuration Models |
| 生命周期 | 生成即普通可用物料，无审批；收尾靠「Deactivate Configuration Items」程序停用 | EBS CTO Setup |
| BOM/工艺 | 物化时生成**新的** config BOM + routing，由 model BOM 与选中的 option class 展开（不是复制行） | EBS CTO Process Guide |
| 价格/成本 | 配置物料既是库存/成本载体也是价格载体；配置层价格 = 选项价汇总（`BOM: CTO Perform Cost Rollup`） | EBS CTO Setup |
| 变更 | 已 booking 默认禁改；改配置 = 旧配置物料 **delink** + 重新物化 | EBS CTO Order Changes |
| 溯源 | 配置物料上记录 `Base Model`、`ConfigItemNumber`、`ConfiguratorPath`、`ConfigRevisionNumber` | Fusion Item Manufacturing Attributes |

> 未证实项（不进设计依据）：EBS profile `CZ: Auto Create Configuration Item` 在公开手册检索不到；SAP「变式生成规则」细节未逐条证实。

### 1.2 与本平台的三个架构差异（决定了不能照抄）

| 差异 | Oracle 前提 | 本平台事实 | 结论 |
|---|---|---|---|
| BOM 归属 | BOM 挂在物料上 → 必须为配置物料生成 BOM | `item_structure` 是**独立结构版本**，`configuration.structure_id` 已锚定冻结版本 | **不复制 BOM**：订单/生产按 configuration 展开即可 |
| 生命周期 | 生成即可用 | 已有不变量「draft 不可被单据引用」（ARCHITECTURE_V3 §0.4.5 #4） | 新物料 `status='draft'`，**必须走签发**才可交易 |
| 唯一性 | 选项组合集合匹配（可跨单复用） | `config_hash` 已是「规范化拼接 + sha256」，且 solved/frozen 才有值、solved 后不可改 | **直接用 config_hash** 做幂等键，不新建匹配逻辑 |

---

## 2. 决策（decision-complete）

### D1 触发时机 = 只做 manual

- `manual`：用户在配置实例详情/列表点「物化为物料」，同步调用服务。
- `auto`：Phase 1 只留 hook 注释位；**Phase 2 已落地**（见 §11）。实现方式为「求解提交后同步调用」，不引入事件/订阅者；产物仍为 `draft`，**不自动签发**（D8 不变量不变）。
- 明确不做「下单即物化」：订单行只持 `config_id`，下单不应产生主数据。

### D2 前置条件（任一不满足则抛 `MaterializeRejected(code)`，不静默）

| # | 条件 | code |
|---|---|---|
| 1 | `configuration` 存在 | `CONFIG_NOT_FOUND` |
| 2 | `configuration.status ∈ {solved, frozen}` | `CONFIG_NOT_SOLVED` |
| 3 | `configuration.config_hash` 非空 | `CONFIG_HASH_MISSING` |
| 4 | `model_item_id` 对应物料存在 | `MODEL_NOT_FOUND` |
| 5 | 模型物料 `status ∈ {active, frozen}` | `MODEL_NOT_TRADABLE` |
| 6 | 模型物料 `config_materialize_policy ∈ {manual, auto}` | `MATERIALIZE_DISABLED`（`off` 时明确报错，替代现在的静默无效） |

### D3 幂等键 = `(model_item_id, config_hash)`

- 命中已有变式物料（任一 configuration 的 `variant_item_id` 指向它）→ **复用**：把当前 configuration 的 `variant_item_id` 也指向该物料，返回 `created=False`。
- 语义：同一「模型 + 选项组合」只生成一次物料，多个配置实例可共享同一物料（对齐 Oracle `Match Configuration`）。
- 不做「配置指纹 → 物料」新映射表：`configurations.variant_item_id` 本身即映射。

### D4 编码规则 = `{model_code}-{seq:04d}`

- `seq` = 该模型下已物化变式物料数 + 1（`SELECT COUNT(*) FROM configurations WHERE model_item_id=? AND variant_item_id IS NOT NULL`），从 `0001` 起，左补零 4 位。
- 例：模型 `LAPTOP-X1` → `LAPTOP-X1-0001`。
- 满足 `items.code` 约束（`pattern ^[A-Za-z0-9][A-Za-z0-9_\-]*$`、`max_length 40`）；拼接后超 40 字符 → 抛 `ITEM_CODE_TOO_LONG`，提示缩短模型编码，**不截断**。
- 并发重号：交给 `items.code` 唯一约束兜底，捕获唯一冲突后**重算序号并重试 1 次**，仍冲突则 `CODE_CONFLICT`。不新增序号表。

### D5 新物料字段（继承 + 强制）

| 字段 | 取值 |
|---|---|
| `code` | D4 |
| `name` | `{model.name} / {配置摘要}`，摘要 = 前 3 条 `configuration_value`（按字段名排序）的显示值拼接，超 60 字截断 |
| `item_type` / `item_group_id` / `base_uom` / `sales_uom` / `tax_classification_id` | 继承模型（模型必有） |
| `structure_role` | 强制 `none`（变式物料是标准件，不再是 model，**防递归物化**） |
| `config_materialize_policy` | 强制 `off`（同上） |
| `config_match_policy` | 强制 `no`（变式物料不参与配置匹配） |
| `status` | 强制 `draft`（走签发） |
| 其余（`purchase_uom`/`min_order_qty`/重量等） | 不继承，按 `items.yaml` 默认或空 |

### D6 事务与写入顺序

单事务（沿用 `ConfigurationMatchService` 的连接获取方式，见 §5 T0-1）：
1. 校验 D2；2. `INSERT items`（走元模型 BO 写入路径，自动写审计）；3. `UPDATE configurations SET variant_item_id=?`；4. commit。
任一步失败 → rollback + raise。审计由 BO 层自动产生（`aspects: [audit_aspect]` 两者均有）。

### D7 不复制 BOM、不复制价格

- `item_structure` 不复制：configuration 已锚定 `structure_id`，复制会产生两份真源。
- `rate_record` 不复制：定价仍按模型/父物料维度；变式物料成为价格载体是 Phase 3 议题。

### D8 生命周期 = `draft`，且不绕过项 5 的不变量

物化成功 ≠ 可下单。新物料必须经签发（`draft → active`）才能被单据行引用；这正是「draft 不可引用」不变量的正向应用。生产者也因此拿不到「半成品主数据」。

### D9 变更管理 = 新配置实例 → 新变式物料

`configuration` solved 后不可改（R10），改配置只能生成新实例 → 新 `config_hash` → 新物料；旧物料保留，需要时手工置 `inactive`（对齐 Oracle delink 语义，但不做自动替换动作）。

### D10 不新增数据库迁移

溯源双向可达：`configuration → variant_item_id`，`items ← configurations.model_item_id` join 即可回答「这是哪个模型的第几个变式」。**本期不新增列、不新增表**（v160 保留）。

---

## 3. 接口与 UI

```python
# meta/services/variant_item_materialize_service.py
class MaterializeError(Exception): code: str
class VariantItemMaterializeService:
    def __init__(self, data_source): ...          # 与 ConfigurationMatchService 同一种注入
    def materialize(self, configuration_id: int) -> dict
        # -> {"item_id": int, "item_code": str, "created": bool}
```

- UI：`configuration` 的 `actions` 段新增 `materialize`（custom，`visible_when: status in [solved, frozen]`，`confirm: true`），成功后 toast 展示 `item_code` + 跳转链接。自动菜单仍关闭（`skip_auto_menu: true` 不动）。
- 权限：新增 action 权限点 `configuration:materialize`，授予配置管理角色；无权限 → 403。
- 不做批量物化、不做定时批处理（Phase 2）。

---

## 4. 测试计划

### 4.1 新增 `meta/tests/test_variant_item_materialize_service.py`

| # | 用例 | 断言 |
|---|---|---|
| 1 | 正常物化 | 新增 1 行 items；`code='{model}-0001'`；`status='draft'`；`structure_role='none'`；`config_materialize_policy='off'`；`variant_item_id` 回写；`created=True` |
| 2 | 幂等复用 | 同 hash 第二个配置 → `created=False`，items 不新增，两个 configuration 都指向同一 item |
| 3 | policy=off | 抛 `MATERIALIZE_DISABLED`，items 与 configuration 均无变化 |
| 4 | 配置未 solved | draft/invalid → `CONFIG_NOT_SOLVED` |
| 5 | 模型不可交易 | 模型 draft/inactive → `MODEL_NOT_TRADABLE` |
| 6 | 无 config_hash | → `CONFIG_HASH_MISSING` |
| 7 | 序号递增 | 同模型第二个不同配置 → `-0002` |
| 8 | 联动不变量 | 新变式物料 `draft` 在 `sales_order_lines` 引用被 `value_filter` 拒绝；置 `active` 后放行 |
| 9 | 审计 | items 新增审计 1 条；configuration 更新审计 1 条 |
| 10 | 编码冲突 | 预置同 code 行 → 重试后成功或 `CODE_CONFLICT`（不静默覆盖） |

### 4.2 回归

- `test_configuration_materialize_inert.py` 按 §6.3 改写。
- `test_configuration_price.py`、`test_sales_order_pricing_e2e.py` 必须保持通过。

### 4.3 运行入口（铁律）

```
python d:\filework\test.py --single meta/tests/test_variant_item_materialize_service.py
python d:\filework\test.py --single meta/tests/test_configuration_materialize_inert.py
python d:\filework\test.py --single meta/tests/test_sales_order_pricing_e2e.py
```

---

## 5. 实施前需确认（T0，实现第一件事就是这三条）

1. **连接/事务**：`ConfigurationMatchService` 如何拿连接（`db_path` / `data_source`），物化服务复用同一方式；确认是否已有跨对象事务工具。
2. **BO 写入路径**：`items` 新增与 `configuration` 更新是走 facade/BO API（自动审计）还是裸 SQL（需手写审计）；选前者，除非无事务能力。
3. **actions YAML 结构**：现有 `configuration.yaml` 是否已有 `actions` 段与 custom action 范例可照抄（若无，参考其他对象 yaml 的 action 定义）。

---

## 6. 落地清单

### 6.1 新增
- `meta/services/variant_item_materialize_service.py`
- `meta/tests/test_variant_item_materialize_service.py`

### 6.2 修改
- `meta/schemas/configuration.yaml`：加 `materialize` action + 权限点
- `meta/schemas/items.yaml`：`config_materialize_policy` 描述去掉「只留位置」，改为指向本 spec
- `docs/ARCHITECTURE_V3.md`：§4.1 / §5.6 `[计划]` → `[事实]`；附录 A.1 两行「存在但未接线 / 缺失」→「已实现」
- `docs/specs/p2-master-data-pricing-variant/spec.md` §3.4：标注已另立本 spec

### 6.3 改写（不是删除）`test_configuration_materialize_inert.py`

| 原断言 | 处理 |
|---|---|
| 默认值 `off` | 保留 |
| `manual` 链路人肉解算不写 `variant_item_id` | 保留，但改为「**未调用物化服务的解算**不写」 |
| 源码无写入点 | 删除，替换为「`off` 时调用物化服务被拒且不写」 |

---

## 7. 验收标准

- [x] `python d:\filework\test.py --single meta/tests/test_variant_item_materialize_service.py` 全绿（11 passed）
- [x] `test_configuration_materialize_inert.py` 按 §6.3 改写后全绿（3 passed）
- [x] `test_sales_order_pricing_e2e.py` 4 passed、`test_configuration_price.py` 41 passed 无回归
- [x] `config_materialize_policy='off'` 时调用物化 → 明确错误码（`MATERIALIZE_DISABLED`，不再静默）
- [x] 物化产出物料 `status='draft'`，在订单行引用被拒；签发（`active`）后可引用
- [x] 同 `(model, config_hash)` 两次调用只产生 1 行 items（第二次 `created=False` 复用）
- [x] 架构文档 §4.1/§5.6/附录 A.1 与实际行为一致（无 `[缺口]` 残留）

---

## 8. 明确不做（本期 out of scope）

- 事件订阅（auto 已改为同步后置钩子实现，见 §11）、批量/定时物化
- 复制 BOM/工艺、复制价格记录、成本汇总
- 配置物料变更（重新物化/替换/自动停用）
- 配置物料命名中的选项摘要本地化文案
- 跨模型共享物料、按组织分库物化

---

## 9. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 物料爆炸（每配置一物料） | 主数据膨胀 | 只 manual 触发 + 幂等键复用 + 后续可选 inactive 策略 |
| 序号在并发下重号 | 编码冲突 | 唯一约束 + 重算重试 1 次 + 明确错误码 |
| 物化后无人签发 → 死物料 | 数据垃圾 | 列表默认过滤 `draft` 变式物料；文档写明必须签发 |
| config_hash 与选项变更 | 同配置不同 hash | solved 后不可改已保证 hash 稳定；跨实例差异是预期行为 |
| 与价格链耦合 | 变式物料无价格 | 本期不承诺价格，定价继续走模型维度 |

---

## 10. 分期

| 阶段 | 内容 | 前置 |
|---|---|---|
| Phase 1（已完成） | manual 物化 + 幂等 + 编码 + 审计 + UI 动作 | 无 |
| Phase 2（已完成，见 §11） | auto：solved 后同步触发物化；**不做自动签发**（draft 保留，签发走 `activate`） | 无 |
| Phase 3 | 变式物料作为价格/成本载体（rate_record 复制或继承、成本汇总） | Phase 1 稳定运行 |

---

## 11. Phase 2 落地记录（2026-10-30）

### 11.1 实现方式

| 项 | 落地 |
|---|---|
| 触发点 | `ItemStructureConfigService.solve()` 写入事务 **提交之后**（`meta/services/item_structure_config_service.py`） |
| 判定 | 调用 `VariantItemMaterializeService.materialize_on_solve(configuration_id)`，内部读模型 `config_materialize_policy`，仅 `auto` 才物化 |
| 失败处理 | 全异常吞掉（`MaterializeError` → warning 日志，其它 → `logger.exception`），**不回滚、不抛给求解** |
| 响应 | auto 成功时 `solve()` 返回值追加 `variant_item_id`；失败/跳过不追加，字段集合不变 |
| 幂等 | 复用 Phase 1 的 `(model_item_id, config_hash)` 幂等键，重试安全 |

不采用事件驱动（outbox + dispatcher + `app.yaml` 订阅契约）：solve 需要内聚返回、避免引入线程/死信/契约校验的运维面；幂等键已保证同步重试等价。

### 11.2 产品决策（保守默认，可改）

**auto 只物化，不自动签发**：产物 `status='draft'`，仍需 `items.yaml` 的 `activate` 动作签发后才可被单据行引用（D8 不变量）。副作用是 auto 实例会产生待签发 draft，需人工（或后续批量签发）清理，否则等于 D8 风险表里的「死物料」。

若要改为「auto 直接签发为 active」，需同时补：签发审计、失败回滚语义、死物料率监控——属独立变更，不在本期。

### 11.3 测试

`meta/tests/test_variant_item_materialize_service.py` 新增 4 条 auto 用例（策略命中物化 / 非 auto 跳过 / 失败不抛 / 同 hash 复用），文件合计 15 passed；`test_configuration_materialize_inert.py` 3 passed、`test_item_structure_config.py` 63 passed 无回归。

---

## 附录：参考来源

- [Oracle EBS · Order Management CTO 流程与配置项创建](https://docs.oracle.com/cd/E18727-01/doc.121/e13406/T373258T374217.htm)
- [Oracle EBS · CTO Setup（编号方法 / 停用程序 / 成本汇总）](https://docs.oracle.com/cd/E26401_01/doc.122/e48832/T426454T426679.htm)
- [Oracle EBS · CTO Order Changes（配置变更与 delink）](https://docs.oracle.com/cd/E18727-01/doc.121/e13692/T426454T426903.htm)
- [Oracle Fusion · Set Up Numbers for Configuration Models](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25d/faiom/set-up-numbers-for-configuration-models.html)
- [Oracle Fusion · Item Manufacturing Attributes（Match Configuration）](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/fapim/item-manufacturing-attributes.html)
- [Oracle Fusion · Manage CTO Changes Without Canceling Supply](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25d/faims/manage-configure-to-order-changes-without-canceling-supply.html)
