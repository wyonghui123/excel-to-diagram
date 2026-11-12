# 变式物料化（Variant Item Materialization）Spec

> 版本 v1.2 · 2026-10-31 · 二次对标决策已落地（auto 改 `frozen` 触发、auto 产物 `active`、v167 provenance 迁移 + 唯一索引 + 权限点）
> 上游：`docs/specs/p2-master-data-pricing-variant/spec.md` §3.4（Phase 1 边界）
> 定位：把「配置实例（configuration）」固化为「可交易物料（items 新行）」，即 `items.config_materialize_policy` 的消费端 + `configurations.variant_item_id` 的写入端。
> 一句话：**物料化是主数据动作，不是订单动作**——`manual` 产物是 `draft`（须签发），`auto` 在配置冻结时产出 `active`。

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

### D1 触发时机 = manual 手动 / auto 冻结触发

- `manual`：用户在配置实例详情/列表点「物化为物料」，同步调用服务；产物 `draft`，须签发。
- `auto`：**配置冻结（`frozen`）时触发**——`ConfigurationGuardInterceptor.after_action` 检测到 `status` 更新为 `frozen` 后同步调用服务；产物直接 `active`（对齐 Oracle「生成即可用」，见 §11 / §12.1）。
- 不再挂在 `solve()`：`solve()` 同时被配置 UI 与**草稿订单展开**调用，售前试配不应产生主数据。
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

- `seq` = 该模型下**不重复的变式物料数** + 1（`SELECT COUNT(DISTINCT variant_item_id) FROM configurations WHERE model_item_id=? AND variant_item_id IS NOT NULL`），从 `0001` 起，左补零 4 位。
- **[2026-10-31 修正]** 原实现按 configuration 行计数；多个配置复用同一物料（D3）时会跳号（0001、0003…），已改 `COUNT(DISTINCT variant_item_id)`。
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
| `status` | `manual` → `draft`（走签发）；`auto` → `active`（冻结即承诺，直接可交易） |
| 其余（`purchase_uom`/`min_order_qty`/重量等） | 不继承，按 `items.yaml` 默认或空 |

### D6 事务与写入顺序

单事务（`BEGIN IMMEDIATE`，沿用 `data_source.transaction()`）：
1. 校验 D2；2. **事务内**按 `(variant_of_item_id, variant_config_hash)` 查重（命中即回写并返回）；3. `INSERT items`（含 provenance 两列）；4. `UPDATE configurations SET variant_item_id=?`；5. commit。
任一步失败 → rollback + raise。审计由 BO 层自动产生（`aspects: [audit_aspect]` 两者均有）。
查重必须与写入同事务：否则两个并发请求会同时查不到再各插一行（P0，见 §12.2 #1）。

### D7 不复制 BOM、不复制价格

- `item_structure` 不复制：configuration 已锚定 `structure_id`，复制会产生两份真源。
- `rate_record` 不复制：定价仍按模型/父物料维度；变式物料成为价格载体是 Phase 3 议题。

### D8 生命周期 = 按策略分化，且不绕过项 5 的不变量

- `manual`：产物 `draft`，必须经签发（`draft → active`）才能被单据行引用——「draft 不可引用」不变量的正向应用。
- `auto`：触发点已是 `frozen`（承诺点），产物直接 `active`；若仍为 `draft`，auto 只会制造待签发死物料（见 §12.2 #4）。
- 两者都不绕过不变量：`db` 里不会有被单据引用的 draft。

### D9 变更管理 = 新配置实例 → 新变式物料

`configuration` solved 后不可改（R10），改配置只能生成新实例 → 新 `config_hash` → 新物料；旧物料保留，需要时手工置 `inactive`（对齐 Oracle delink 语义，但不做自动替换动作）。

### D10 新增一次迁移（v167）承载溯源与唯一性

`items` 新增两列，作为幂等键的**真源**（不再靠 join `configurations` 反查）：

- `items.variant_of_item_id INTEGER REFERENCES items(id)`
- `items.variant_config_hash TEXT`（存物化时的 `config_hash`）

并建**部分唯一索引** `ux_items_variant_identity ON items(variant_of_item_id, variant_config_hash) WHERE variant_of_item_id IS NOT NULL`（普通物料两列为 NULL，不参与唯一）。

迁移 `meta/migrations/v167__variant_item_provenance_and_permissions.py`：加列 → 从 `configurations.variant_item_id` 回填 → 重复检查（有重复即失败）+ 建索引 → 种权限 `configuration:configuration_materialize`。`downgrade()` 保留列与数据（只回滚索引/权限种子可选）。

> 原 v1.1 的「本期不新增迁移」已被本条取代：无 DB 级唯一约束时，并发重复只能靠应用层事务兜底（见 §12.2 #1/#7）。

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
- 权限：action 权限点 `configuration:configuration_materialize`（DB 码，双段式），由 v167 种入；端点 `POST /api/v2/configuration/materialize` 用 `@require_permission('configuration:configuration_materialize')`；无权限 → 403 `FORBIDDEN`。
- 不做批量物化、不做定时批处理（Phase 2）。

---

## 4. 测试计划

### 4.1 新增 `meta/tests/test_variant_item_materialize_service.py`

| # | 用例 | 断言 |
|---|---|---|
| 1 | 正常物化（manual） | 新增 1 行 items；`code='{model}-0001'`；`status='draft'`；`structure_role='none'`；`config_materialize_policy='off'`；`variant_of_item_id` / `variant_config_hash` 已写；`variant_item_id` 回写；`created=True` |
| 2 | 幂等复用 | 同 hash 第二个配置 → `created=False`，items 不新增，两个 configuration 都指向同一 item |
| 3 | policy=off | 抛 `MATERIALIZE_DISABLED`，items 与 configuration 均无变化 |
| 4 | 配置未 solved | draft/invalid → `CONFIG_NOT_SOLVED` |
| 5 | 模型不可交易 | 模型 draft/inactive → `MODEL_NOT_TRADABLE` |
| 6 | 无 config_hash | → `CONFIG_HASH_MISSING` |
| 7 | 序号递增 | 同模型第二个不同配置 → `-0002` |
| 8 | 联动不变量 | 新变式物料 `draft` 在 `sales_order_lines` 引用被 `value_filter` 拒绝；置 `active` 后放行 |
| 9 | 审计 | items 新增审计 1 条；configuration 更新审计 1 条 |
| 10 | 编码冲突 | 预置同 code 行 → 重试后成功或 `CODE_CONFLICT`（不静默覆盖） |
| 11 | auto + frozen | 冻结触发物化，产物 `status='active'` |
| 12 | auto + solved | 仅 solved 不触发（返回 `None`） |
| 13 | auto + 模型策略非 auto | 跳过不物化 |
| 14 | auto 失败 | 不抛给调用方（拦截器吞异常，回滚本次物化） |
| 15 | auto 同 hash 复用 | 冻结第二个同 hash 配置 → 不新增 items，复用同一物料 |

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

- [x] `python d:\filework\test.py --single meta/tests/test_variant_item_materialize_service.py` 全绿（17 passed）
- [x] `test_configuration_materialize_inert.py` 按 §6.3 改写后全绿（3 passed）
- [x] `test_sales_order_pricing_e2e.py` 4 passed、`test_configuration_price.py` 41 passed 无回归
- [x] v167 迁移在真实库副本上 migrate + verify 通过（provenance 2 列 / `ux_items_variant_identity` / 权限码）
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
| 物化后无人签发 → 死物料 | 数据垃圾 | `auto` 产物直接 `active`（§11.2），不再产生自动 draft；`manual` 产物仍需签发，列表过滤属遗留项（§12.2 #4） |
| config_hash 与选项变更 | 同配置不同 hash | solved 后不可改已保证 hash 稳定；跨实例差异是预期行为 |
| 与价格链耦合 | 变式物料无价格 | 本期不承诺价格，定价继续走模型维度 |

---

## 10. 分期

| 阶段 | 内容 | 前置 |
|---|---|---|
| Phase 1（已完成） | manual 物化 + 幂等 + 编码 + 审计 + UI 动作 | 无 |
| Phase 2（已完成，见 §11） | auto：配置 `frozen` 后由拦截器同步触发物化；产物直接 `active`（不再产生待签发 draft） | 无 |
| Phase 3 | 变式物料作为价格/成本载体（rate_record 复制或继承、成本汇总） | Phase 1 稳定运行 |

---

## 11. Phase 2 落地记录（2026-10-30）

### 11.1 实现方式

| 项 | 落地 |
|---|---|
| 触发点 | `ConfigurationGuardInterceptor.after_action`：`configuration` 的 `crud_update` 且 `params.status == 'frozen'` 时调用（`meta/core/interceptors/configuration_guard_interceptor.py`） |
| 判定 | 调用 `VariantItemMaterializeService.materialize_on_freeze(configuration_id)`：重读配置，仅 `status='frozen'` 且模型 `config_materialize_policy='auto'` 才物化 |
| 失败处理 | 全异常吞掉（`MaterializeError` → warning 日志，其它 → `logger.exception`），**不回滚配置冻结、不抛给更新请求** |
| 响应 | 不再向 `solve()` 追加 `variant_item_id`（§12.2 #3 已修）；物化结果只在审计/日志可见 |
| 幂等 | 复用 `(variant_of_item_id, variant_config_hash)`：应用层事务内查重 + DB 部分唯一索引双保险 |
| 生命周期 | `auto` 产物 `status='active'`（见 D8）；`manual` 仍为 `draft` |

不采用事件驱动（outbox + dispatcher + `app.yaml` 订阅契约）：`after_action` 同步调用即可满足「冻结后物化」，且失败不影响主流程；幂等键与唯一索引已保证重试安全。

### 11.2 产品决策（已拍板）

**auto 直接产出 `active`**：触发点已收窄到 `frozen`（承诺点），此时物料应立即可交易（对齐 Oracle / Fusion「生成即可用」）。因此不再有「待签发 draft 死物料」的自动产物；`manual` 保留 `draft`，作为人工确认闸门。

配套要求：`auto` 失败只记录日志属可接受（配置冻结必须成功）；可观测性见 §12.2 #5 遗留项。

### 11.3 测试

`meta/tests/test_variant_item_materialize_service.py` 新增 5 条 auto 用例（freeze 触发 active / 仅 solved 不触发 / 非 auto 跳过 / 失败不抛 / 同 hash 复用），文件合计 17 passed；`test_configuration_materialize_inert.py` 3 passed、`test_item_structure_config.py` 63 passed 无回归。v167 迁移在真实库副本上 migrate + verify 均 PASS。

---

## 12. 二次对标与审视（2026-10-31）

### 12.1 头部产品横向对照（配置记在哪 / 物料何时生成 / 生成后是否即可用）

| 产品 | 配置记录 | 变式物料生成时机 | 生成后可用 | 成本/价格载体 |
|---|---|---|---|---|
| Oracle EBS CTO | 订单行 | booking 后 `Create Configuration Item` | 是 | 是（成本 rollup） |
| Oracle Fusion | 订单行 | 订单提交时 item generation；`Match Configuration` 复用 | 是 | 是 |
| SAP VC / AVC | KMAT + 订单/计划行配置 | 默认不建物料；material variant 另立（手动/可配置自动） | 是 | 是（标准成本） |
| D365 | 销售/报价/采购/生产/项目行，每配置一个 configuration ID | 按需 `Create item` | 是（released product） | 是 |
| Odoo | 产品模板 + 属性组合 | Instant / **Dynamic（加入销售订单时）** / Never | 是 | 是 |
| Salesforce CPQ / Revenue Cloud | 报价行（QuoteLineItem → Product2/PricebookEntry） | **不生成物料主数据** | 不适用 | 由 ERP 承担 |

结论：没有头部产品在「售前求解」阶段自动建物料主数据；我们的 `auto` 触发点比所有对标产品都早。

### 12.2 偏离项与处置

| # | 偏离 | 证据 | 级别 | 处置 |
|---|---|---|---|---|
| 1 | 事务外查重 → 并发可产生重复变式物料 | 原 `materialize()` 在事务外 `_find_variant_item`，`_create_variant` 才开事务 | P0 | **已修**：查重移入 `BEGIN IMMEDIATE` 事务（datasource / WriteQueue 均为 IMMEDIATE） |
| 2 | 序号按 configuration 计数 → 复用后跳号 | `_next_sequence` 原为 `COUNT(*)` | P1 | **已修**：`COUNT(DISTINCT variant_item_id)` |
| 3 | auto 挂在 `solve()` → 售前试配 / 草稿订单展开即物化 | `solve()` 被 `sales_order_expand_service._solve()` 调用 | P1 | **已修**：改到 `frozen` 由拦截器触发，`solve()` 不再物化 |
| 4 | draft 必须签发 + 列表过滤未实现 → 死物料 | `src/` 无 `variant_item` 过滤 | P1 | **部分已修**：auto 产物直出 `active`，不再制造自动 draft；**列表过滤仍遗留**（仅 manual 产物受影响） |
| 5 | auto 失败仅 warning，不可观测 | `materialize_on_freeze` 全吞异常 | P1 | 遗留：落失败标记或在配置列表暴露「auto 未物化」 |
| 6 | 权限点缺失（§3 要求，实现仅 `login_required`） | `meta/api/configuration_api.py` | P1 | **已修**：`require_permission('configuration:configuration_materialize')` + v167 种入权限 |
| 7 | 无 provenance / 无唯一索引 | `items` 原无 variant 列；`configurations` 无 `(model, hash)` 唯一 | P2 | **已修**：v167 加 `variant_of_item_id` / `variant_config_hash` + 部分唯一索引 |
| 8 | 无价格/成本载体 | 无 `rate_record` | P2 | Phase 3 |
| 9 | 删除保护未业务化 | `items.deletion_policy.restrict_on` 不含 `configurations` | P2 | 补 restrict + 友好错误 |
| 10 | 命名摘要按 `attribute_code` 排序 | `_variant_summary` | P2 | 改用 `seq` + 属性名 |

### 12.3 决策落地与剩余动作

**已落地（v1.2 变更集）**

1. auto 触发点从 `solve()` 改为 `frozen`（拦截器 `after_action`）。
2. auto 产物直接 `active`；`manual` 保持 `draft`（D8）。
3. v167 迁移：`items.variant_of_item_id` / `variant_config_hash` + 部分唯一索引 + 权限种子。
4. 端点权限点 `configuration:configuration_materialize`（DB 双层码）。
5. P0 并发查重入事务；D4 序号 `COUNT(DISTINCT)`。

**剩余（不阻塞本期）**

1. **可观测性（P1）**：auto 失败落标记或在配置列表暴露「auto 未物化」。
2. **列表过滤（P1）**：`src/` 默认过滤 manual 产出的 draft 变式物料 / 待签发队列。
3. **删除保护（P2）**：`items.deletion_policy.restrict_on` 补 `configurations`，给业务化错误。
4. **命名摘要（P2）**：`_variant_summary` 改用 `seq` + 属性名排序。
5. **Phase 3 前** `config_materialize_policy` 保持默认 `off`（无价格载体的主数据不自动产生）。

---

## 附录：参考来源

- [Oracle EBS · Order Management CTO 流程与配置项创建](https://docs.oracle.com/cd/E18727-01/doc.121/e13406/T373258T374217.htm)
- [Oracle EBS · CTO Setup（编号方法 / 停用程序 / 成本汇总）](https://docs.oracle.com/cd/E26401_01/doc.122/e48832/T426454T426679.htm)
- [Oracle EBS · CTO Order Changes（配置变更与 delink）](https://docs.oracle.com/cd/E18727-01/doc.121/e13692/T426454T426903.htm)
- [Oracle Fusion · Set Up Numbers for Configuration Models](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25d/faiom/set-up-numbers-for-configuration-models.html)
- [Oracle Fusion · Item Manufacturing Attributes（Match Configuration）](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/fapim/item-manufacturing-attributes.html)
- [Oracle Fusion · Manage CTO Changes Without Canceling Supply](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25d/faims/manage-configure-to-order-changes-without-canceling-supply.html)
