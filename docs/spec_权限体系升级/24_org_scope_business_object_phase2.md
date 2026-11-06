# 24 · 业务对象组织边界（Phase 2 细化规格）

> 文档编号: 24 | 状态: 草案 v1.0 | 更新: 2026-11-06
> 主题: 把 [23 · 主组织与组织数据权限](./23_primary_org_data_permission.md) §5 Phase 2
>       「业务对象组织边界」细化为可实施规格；对齐 Oracle Fusion 的
>       **owning organization + Data Role 组织范围 + 组织层级继承** 模型。
> 前置: 23（主组织锚点与组织页受控）/ 17（组织树）/ 13（权限总纲）/ 16（角色→权限集）
> 关联: [dimension_object_mapping.yaml](../../meta/schemas/dimension_object_mapping.yaml)
>       / [permission_set_dimension_scopes.yaml](../../meta/schemas/permission_set_dimension_scopes.yaml)
>       / [org_function_service.py](../../meta/services/org_function_service.py)
>       / [dimension_scope_engine.py](../../meta/services/dimension_scope_engine.py)

---

## 0. TL;DR

1. 每个业务对象（BO）必须声明**唯一的 owning org**（归属组织），不再"多个组织字段并列、以谁为准不明"。
2. 用户可见组织集 = **权限集组织范围（含子树）∪ 主组织 − 排除项**；不是"有主组织就自动全有"，也不是"无配置就放行"。
3. 读过滤、写校验、参照（F7）三处共用**同一个求值器**，避免"列表看不到、详情能改、参照能选"。
4. BO 的组织声明是**单一真源**，`dimension_object_mapping` 不再手工双写；声明与绑定不一致时一致性测试失败。
5. 阶段拆分：**2a 只读过滤 → 2b 写校验 → 2c 组织职能校验**，每步可独立回滚。

## 1. 范围与非目标

### 1.1 范围内

* BO 层 owning org 的元模型声明与登记清单（§3、§4）。
* 可见组织集求值器（§5.1）。
* 读、写、参照三类判定（§5.2-§5.4）。
* 组织职能约束（owning org 必须具备对应 `function_type`）。
* 主数据共享的显式声明（§4.4）。
* 迁移、灰度开关、测试与验收（§7-§8）。

### 1.2 非目标

* `users.primary_org_id` 主组织字段本身（23 §4.3，Phase 1 交付）。
* 组织管理页自身的行级受控（23 §4.5，Phase 1 交付）。
* 运行时"切换当前组织"上下文（23 Phase 3）。
* 组织树的物化闭包（23 D7：实时递归展开）。
* 数据权限 UI 改版（仅要求既有 UI 能表达"组织维度范围"，已有能力）。

## 2. 概念模型

### 2.1 owning org 与执行组织

| 概念 | 定义 | 判定用途 |
|---|---|---|
| **owning org（归属组织）** | 业务对象"属于谁"的唯一组织；Fusion 中 PO 属于 Procurement BU、收货/发运/库存属于 Inventory Org | **数据权限唯一判据** |
| **执行组织（secondary org）** | 参与业务但不决定归属的组织，如收货单的 `purchase_org_id`、法人 `org_id` | 仅用于业务流程、默认值、报表，**不参与权限判定** |
| **来源 / 目标组织** | 双端单据（调拨）的 from / to | 读：任一端可见；写：两端均需可见（§5.3） |

**核心规则**：一个 BO 有且仅有一个 owning org 声明（或一个 dual 双端声明）。多组织字段并存时，必须在元模型中指定"以谁为准"，未指定即 `ORG_SCOPE_AMBIGUOUS`。

### 2.2 组织职能约束

owning org 必须在该组织上具备对应职能（`org_functions.function_type`，`status='active'`）：

| owning 类型 | 必需职能 |
|---|---|
| 采购单据（purchase_order、requisition） | `procurement` |
| 库存单据（receipt、shipment、transfer、inventory_*、serial_number） | `inventory`（调出端允许 `storage`） |
| 销售单据（sales_order） | `sales` |
| 制造单据（未来的 production_order） | `manufacturing` |
| 法人主体（party_internal） | `legal_entity` |

未具备对应职能 → `ORG_FUNCTION_MISSING`，建单/改单拒绝。**该规则只在 2c 阶段开启**，避免历史脏数据一次性阻塞。

### 2.3 与 Oracle Fusion 的映射

| Fusion | 本平台 | 状态 |
|---|---|---|
| Legal Entity | `org_functions.function_type='legal_entity'` | 已有 |
| Business Unit | `management_unit` 职能 + 单据的采购/销售组织字段 | 已有职能，未确立为统一锚点 |
| Inventory Organization | `inventory` 职能 + `inventory_org_id` / `org_id` | 已有 |
| Organization Hierarchy | `orgs.parent_id` + `filter_through_hierarchy: true` | 已有 |
| Data Role → Organization Security | 权限集 + `permission_set_dimension_scopes('org')` | 已有载体，未接 BO |
| Default Business Unit | `users.primary_org_id` | Phase 1 补 |
| Reference Data Set (RDS) | §4.4 `reference_data_scope` | 本规格补 |

> 差异说明：Fusion 的权限来源是 Data Role 的组织范围，主组织只是默认上下文。本规格保持同一语义——主组织**加入**可见集，但不替代权限集范围；唯一例外是兼容期（§7.2）。

## 3. 元模型

### 3.1 BO 声明块 `org_scope`

在 BO YAML 顶层新增（与 `rules` / `doc_effect` 同级）：

```yaml
org_scope:
  mode: direct                 # direct | chain | dual | global
  field: inventory_org_id      # direct/dual 必填；owning org 字段
  function: inventory          # 2c 阶段校验；可空
  write_check: true            # 是否参与写校验
  enforce: enforce             # enforce | compat | off（默认继承全局开关）
```

**模式语义**

| mode | 含义 | 过滤形态 |
|---|---|---|
| `direct` | 本表有 owning org 列 | `<field> IN (:visible)` |
| `chain` | 经外键跳到宿主对象 | `EXISTS (SELECT 1 FROM host h WHERE h.id = t.<fk> AND h.<field> IN (:visible))` |
| `dual` | 双端组织（from / to） | `(<from> IN (:visible) OR <to> IN (:visible))` |
| `global` | 显式全局共享（主数据） | 不注入 |

**校验规则（元数据加载期）**

| 编号 | 规则 | 失败错误 |
|---|---|---|
| V1 | `mode ∈ {direct, chain, dual, global}` | `ORG_SCOPE_UNDECLARED` |
| V2 | `direct`/`dual` 的 `field` 必须存在于本 BO 字段 | `ORG_SCOPE_FIELD_MISSING` |
| V3 | `chain` 必须声明 `via`（外键字段）与 `host`（宿主 BO） | `ORG_SCOPE_CHAIN_INVALID` |
| V4 | `dual` 必须同时声明 `from_field` / `to_field` | `ORG_SCOPE_DUAL_INCOMPLETE` |
| V5 | 同一 BO 不得同时声明两个 org_scope | `ORG_SCOPE_AMBIGUOUS` |
| V6 | 有组织字段但未声明 `org_scope` 的 BO | `ORG_SCOPE_UNDECLARED`（一致性测试失败，不阻塞启动） |

### 3.2 单一真源

* `org_scope` 声明是唯一真源。
* `DimensionObjectMappingLoader.get_bindings_for_bo` 增加合成路径：优先读 BO 声明，`dimension_object_mapping.yaml` 中 org 的 `applies_to` 仅保留 `party_internal` 作为历史兼容并标注 `deprecated`。
* 一致性测试：声明集合与映射表集合不一致 → 失败（防止手工双写漂移）。

### 3.3 明细行

明细行（`receipt_line`、`shipment_line`、`purchase_order_line`、`purchase_order_schedule`）不单独声明 org，统一 `mode: chain` 到主单：

```yaml
org_scope:
  mode: chain
  via: receipt_id
  host: receipt
  field: inventory_org_id
```

要求：所有列表/详情/导出查询必须 join 主单；未 join 的查询由测试拦截（§8 AC-07）。

## 4. BO 登记清单

### 4.1 A 类：直接归属（direct）

| BO | owning org 字段 | 职能 | 备注 |
|---|---|---|---|
| purchase_order | `purchase_org_id` | procurement | `org_id`（法人）降级为执行组织 |
| receipt | `inventory_org_id` | inventory | `purchase_org_id`、`org_id` 不参与判定 |
| sales_order | `sales_org_id` | sales | `org_id` 为法人 |
| inventory_transaction | `org_id` | inventory | — |
| inventory_balance | `org_id` | inventory | — |
| inventory_adjustment | `org_id` | inventory | — |
| inventory_count | `org_id` | inventory | — |
| inventory_reservation | `org_id` | inventory | — |
| serial_number | `org_id` | inventory | — |
| party_internal | `org_id` | legal_entity | 已登记，保持 |
| project / location / batches / employee / shift / resource* | `org_id` | — | 主数据，2a 即可 |

### 4.2 B 类：派生成（chain）

| BO | via | host | host 字段 |
|---|---|---|---|
| receipt_line | `receipt_id` | receipt | `inventory_org_id` |
| purchase_order_line | `order_id` | purchase_order | `purchase_org_id` |
| purchase_order_schedule | `order_id` | purchase_order | `purchase_org_id` |
| shipment | `ship_from_location_id` | location | `org_id` |
| shipment_line | `shipment_id` | shipment | 派生链（shipment → location.org_id） |
| sales_order_line | `order_id` | sales_order | `sales_org_id` |

> `shipment` 当前**没有组织列**，2a 用 chain 派生；若性能不达标，2b 再补冗余 `org_id` 并回填（见 Q2）。

### 4.3 C 类：双端（dual）

| BO | from | to | 读策略 | 写策略 |
|---|---|---|---|---|
| transfer_order | `from_org_id` | `to_org_id` | 任一端可见 | 两端均可见（推荐，见 Q1） |

### 4.4 D 类：全局共享（global，RDS 等价）

| BO | 声明 | 理由 |
|---|---|---|
| items / item_group / item_structure / item_uom_conversion / item_xref | `mode: global` | 集团级主数据 |
| party / party_archive（外部往来方） | `mode: global` | 供应商/客户档案跨组织共享 |
| control_parameter_value / pricing_determination | `mode: global` | 配置类 |

**强制要求**：`global` 必须显式声明，不允许"没有组织字段 = 自动全局"。未声明且无组织字段的 BO → 一致性测试失败（V6）。

### 4.5 E 类：待定（开放问题）

| BO | 问题 |
|---|---|
| work_order（服务工单） | 无 org 字段；按 `project_id` / `coverage_id` 派生，或补 `org_id`（Q3） |
| purchase_order_schedule | 已归 chain，但"计划行是否允许跨组织"待业务确认 |

## 5. 判定算法

### 5.1 可见组织集

```text
visible(user) =
    ⋃ { expand_subtree(v) | (dimension_code='org', scope_mode='include', v ∈ values(PSS(user))) }
  ∪ { users.primary_org_id }                                    # Phase 1 字段；为空则跳过
  − ⋃ { expand_subtree(v) | scope_mode='exclude' }

expand_subtree(v) = 递归 CTE：v 及其全部后代（orgs.parent_id，防环，最大深度 10）
is_admin(user)   → visible = ALL（显式豁免，非"无配置放行"）
```

**约束**

* `values(PSS)` 取用户全部权限集的并集（用户→角色/组织→权限集）。
* 无任何 org 范围且无主组织：
  * `enforce` → 空集，查询注入 `1=0`（默认拒绝）；
  * `compat` → 不过滤（仅灰度期）；
  * `off` → 不过滤。
* 结果按 `(user_id, 组织树版本)` 缓存，树变更时失效（23 R-04）。

### 5.2 读过滤

| mode | 注入条件 |
|---|---|
| direct | `<field> IN (:visible)` |
| chain | `EXISTS (SELECT 1 FROM <host> h WHERE h.id = t.<via> AND h.<field> IN (:visible))` |
| dual | `(t.<from> IN (:visible) OR t.<to> IN (:visible))` |
| global | 不注入 |

注入点沿用 `data_permission_interceptor`，扩展为 `crud_query + crud_detail + crud_export`（当前仅 `crud_query`）。

### 5.3 写校验

| 操作 | 校验 |
|---|---|
| create | 提交的 owning org ∈ visible；dual 要求两端均 ∈ visible |
| update | ① 原记录 owning org ∈ visible；② 新 owning org ∈ visible（禁止把单据"搬"到不可见组织） |
| delete / cancel / reverse | 原记录 owning org ∈ visible |
| 2c 追加 | owning org 具备对应 `function_type` |

**执行时机**：`before_action`，与现有功能权限校验同一拦截器链。写校验失败不落库。

### 5.4 参照（F7）

组织选择器 / 组织参照接口统一：`orgs` 查询注入 visible，并按 `function_type` 过滤（如采购单据只列 `procurement` 职能组织）。这解决"列表看不到、参照能选"的越权路径。

### 5.5 与委托管理的收敛

* 委托管理员（`OrgAdminScopeService`）的范围 = 其绑定组织子树，与本文求值器**同一份展开逻辑**，只输入不同（委托规则 vs 权限集范围）。
* 两条载体（`permission_set_dimension_scopes` 与 `data_permission_rules(resource_type='org')`）在 Phase 2 内**不合并**，但必须共用 `expand_subtree`，且求值器输出带来源标记，便于排障（23 G4 的收敛留 Phase 3）。

## 6. 错误码

| 错误码 | 触发 | 用户提示 |
|---|---|---|
| `ORG_SCOPE_DENIED` | 读/写/删目标组织不在可见集 | 无权访问该组织的数据 |
| `ORG_SCOPE_UNDECLARED` | BO 未声明 org_scope | 系统配置错误：对象未声明组织归属（内部错误，不暴露细节） |
| `ORG_SCOPE_AMBIGUOUS` | 同 BO 多声明 / 多字段未指定 owning | 同上 |
| `ORG_SCOPE_FIELD_MISSING` | 声明字段不存在 | 同上 |
| `ORG_SCOPE_CHAIN_INVALID` | chain 声明不完整 | 同上 |
| `ORG_FUNCTION_MISSING` | owning org 缺职能 | 组织 X 未启用「库存/采购/销售」职能 |

## 7. 迁移与灰度

### 7.1 迁移（v228）

1. `users.primary_org_id INTEGER NULL`（Phase 1 若已交付则跳过）。
2. 索引：`idx_users_primary_org`。
3. 回填：`receipt_line` / `purchase_order_line` 不补列（走 chain）；`shipment` 不补列（走 chain）。
4. 开关种子：`control_parameter_defs.org_scope_enforce`，值 `off`，取值 `off | compat | enforce`。

### 7.2 三态开关

| 状态 | 读 | 写 | 用途 |
|---|---|---|---|
| `off` | 不过滤 | 不校验 | 默认；元模型可先上线 |
| `compat` | 不过滤，但记录"本应过滤"的命中日志 | 不校验 | 灰度观测，评估影响面 |
| `enforce` | 注入过滤，空集 `1=0` | 校验，拒绝越权 | 目标态 |

### 7.3 上线顺序

```
2a 只读          compat 观测 7 天 → enforce
2b 写校验        enforce 读稳定后开启
2c 职能校验      历史组织先补齐 functions
```

回滚：`org_scope_enforce` 降至 `compat`/`off`；不改数据、不删列。

## 8. 验收标准

| 编号 | 场景 | 期望 |
|---|---|---|
| AC-ORG-01 | 用户仅属组织 A，查询采购订单 | 只见 A 的 PO；B 的 PO 不可见 |
| AC-ORG-02 | 用户属父组织 P | 可见 P 及全部后代组织的数据 |
| AC-ORG-03 | 无组织范围 + enforce | 返回 0 行，不报 500 |
| AC-ORG-04 | 用户可见 A，提交 B 组织的 PO | 拒绝 `ORG_SCOPE_DENIED` |
| AC-ORG-05 | 用户把 A 的 PO 改到 B 组织 | 拒绝（原记录与新组织双向校验） |
| AC-ORG-06 | 调拨单 from=A / to=B，用户仅见 A | 可见；创建 B 为目标的单据需双端可见 |
| AC-ORG-07 | receipt_line 查询未 join receipts | 测试失败（静态扫描 + 集成用例） |
| AC-ORG-08 | 组织参照接口 | 只返回可见且职能匹配的组织 |
| AC-ORG-09 | 声明 `global` 的 items | 所有组织可见 |
| AC-ORG-10 | 有 org 字段但未声明 org_scope | 一致性测试失败 |

## 9. 任务拆分

| 编号 | 任务 | 依赖 |
|---|---|---|
| T1 | 元模型：`org_scope` 声明解析 + V1-V6 校验 + 一致性测试 | — |
| T2 | 求值器：`OrgScopeService.visible_org_ids(user)`（子树展开、缓存、三态） | T1 |
| T3 | 读注入：interceptor 支持 direct/chain/dual，扩展 detail/export | T2 |
| T4 | 写校验：create/update/delete 目标组织校验与错误码 | T2 |
| T5 | BO 登记：A/B/C/D 类声明落到 35 个 schema | T1 |
| T6 | 参照收敛：组织选择器按 visible + function 过滤 | T2 |
| T7 | 职能校验（2c）+ 错误码 | T5 |
| T8 | 迁移 v228、开关种子、灰度日志、回归 | T2 |

**并行建议**：T1 与 T2 可并行；T5 依赖 T1；T3/T4/T6 依赖 T2。

### 9.1 实施记录（2026-11-06）

| 任务 | 落点 | 状态 |
|---|---|---|
| T1 | [org_scope_validator.py](../../meta/core/org_scope_validator.py)：V1-V5 单对象校验 + V6 §4 登记清单；`MetaObject.org_scope` 解析 | ✅ |
| T2 | [org_scope_service.py](../../meta/services/org_scope_service.py)：`visible_org_ids`（include/exclude 子树、主组织、管理员豁免、进程缓存）、三态开关 | ✅ |
| T3 | [org_scope_interceptor.py](../../meta/core/interceptors/org_scope_interceptor.py)：direct/chain/dual 读条件注入（crud_query / crud_read / query / list） | ✅ |
| T4 | 同拦截器：create/update/delete 双向写校验，`ORG_SCOPE_DENIED` | ✅ |
| T5 | §4 A/B/C/D 类共 40 个 BO 声明（含嵌套 chain：shipment_line → shipment → location） | ✅ |
| T6 | 组织参照：`value_help_providers` 对 `target_bo=org` 注入 visible（+ `org_function_type` 职能过滤） | ✅ |
| T7 | 同拦截器 2c：owning org 职能校验，`ORG_FUNCTION_MISSING` | ✅ |
| T8 | [v228__org_scope_phase2.py](../../meta/migrations/v228__org_scope_phase2.py)：`users.primary_org_id` + 索引 + `org_scope_enforce=off` | ✅ |

测试：[test_org_scope_declarations.py](../../meta/tests/test_org_scope_declarations.py)（31 项：声明校验 / 求值器 / 读条件 / 写判定 / 拦截器接线）。
默认 `off`，线上行为不变；灰度按 §7.3 切 `compat` → `enforce`。

## 10. 开放决策

| 编号 | 问题 | 推荐 |
|---|---|---|
| Q1 | 调拨单双端可见策略 | 读任一端、写两端（防止单侧越权创建） |
| Q2 | shipment 是否补 `org_id` 冗余列 | 先用 chain；查询性能不达标再补列回填 |
| Q3 | 服务工单 work_order 归属 | 按 `project.org_id` 派生；无项目则需补 `org_id` |
| Q4 | items/供应商全局共享是否可接受 | 接受，但必须显式 `mode: global`；后续引入共享范围再扩 |
| Q5 | 无组织用户策略 | 沿用 23 Q2：enforce 拒绝 + 白名单 |
| Q6 | `compat` 观测期长度 | 7 天或覆盖一个完整月结周期 |

---

## 附：与 23 号文档的关系

| 23 号内容 | 本文处理 |
|---|---|
| §4.1 三层模型 | 沿用（身份锚点 → 组织范围 → 资源判定） |
| §4.2 M1-M5 元模型 | 本文 §3 细化 M5（org_scope 声明） |
| §4.4 可见集求值 | 本文 §5.1 落为公式 + 缓存策略 |
| §5 Phase 2 | 本文主体；拆为 2a/2b/2c |
| §5 Phase 3「一次配置三处生效」 | **本文提前到 2b（§5.4 参照收敛）**：参照越权与列表过滤同源，且复用同一求值器，增量成本低；若不接受可回退为 Phase 3 |
| §7 AC | 本文 §8 补 BO 层 10 条 |
| Q2/Q3 | 本文 Q5/Q6 继承 |
