# 规格：单据头 → 行追溯（方案 B）+ aggregate_root 聚合根派生

- 文档版本：v1.0（已实施 P0）
- 日期：2026-11-12
- 状态：**P0 已实现并自测通过**（P1/P2/P3 未开始）
- 上游依据：
  - `docs/specs/spec-doc-flow-end-to-end-2026-11-05.md`（边表 = 唯一转单事实层）
  - `docs/specs/spec-vendor-invoice-object-model-2026-11-11.md` §21.7 / §21.9（v254 三条规则只落行级）
  - 代码契约核验：`meta/api/doc_flow_api.py`、`meta/services/doc_flow_service.py`、`src/services/docFlowService.js`、`meta/core/models.py`、`meta/services/query/hierarchy_utils.py`
- 术语：
  - 「单头」= `business_document` 类对象（如 `vendor_invoice`）；「行」= `business_document_line` 类对象（如 `vendor_invoice_line`）。
  - 「聚合根（aggregate root）」= 单据聚合的可追溯起点：沿 `parent_object` 上溯到最顶层单据头。**与已有 `root_object` 语义无关**（见 §3.1）。

---

## 0. 结论摘要

1. **问题确证**：v254 的三条规则 `target_bo` 全为 `vendor_invoice_line`，[doc_flow_service.py](file:///d:/filework/excel-to-diagram/meta/services/doc_flow_service.py#L404-L430) 的 `list_edges()` 只做等值过滤、不做头→行展开，因此头级详情页用 `target_id = <头id>` 查不到任何边，上下游表格恒为空。
2. **修复方向**：新增单端点 `GET /api/v2/doc-flow/trace`，由服务层把「头 id」解析为「行 id 集合」后再查边，一次返回上游 + 下游 + 展开信息。**保留 `/edges` 原契约不动**。
3. **模型缺口确证**：`MetaObject` 无 `aggregate_root` 字段；`parent_object` 同时承担三种语义（单据聚合、主数据从属、架构层级），且 `semantics.category` 无法可靠区分（`document_hu_link` 是 `business_document_line` 却无父；`customer_sales_org` 是 `core_entity` 却有父）。因此**不新增 `bo_root` 字段**，而是新增**派生访问器** `get_aggregate_root()` / `get_aggregate_children()` / `get_aggregate_parent_field()`，零 schema 改动。
4. **命名**：不叫 `root`（已被 `permission_dimension_api` 的 `root_object: 'product'` 与 `audit_operation_api` 的 `root_object: f"{object_type}#{object_id}"` 占用），统一叫 `aggregate_root`。
5. **分期**：P0 = 访问器 + trace 端点（本 spec 主体，可独立交付）；P1 = schema 一致性 lint；P2 = 写侧门控（单独 spec）；P3 = `doc_flow_rule` 去重（单独 spec）。

---

## 1. 问题证据（本次二次核验结果）

| # | 事实 | 证据位置 | 影响 |
|---|---|---|---|
| E1 | `_edges_view()` 仅在 `source_bo+source_id` 或 `target_bo+target_id` 之间二选一，无头→行展开 | [doc_flow_api.py](file:///d:/filework/excel-to-diagram/meta/api/doc_flow_api.py#L104-L116) | 头级查询必然空集 |
| E2 | `list_edges()` 只 `SELECT ... WHERE target_bo = ? AND target_id = ?`，无聚合、无 `status` 过滤 | [doc_flow_service.py](file:///d:/filework/excel-to-diagram/meta/services/doc_flow_service.py#L404-L430) | 需服务层新增解析与聚合，不能靠前端拼 |
| E3 | `_EDGE_COLUMNS` 已含 `quantity_sign`、`status`、`rule_id`、`target_item`、`pool`、`edge_kind`、`reverses_edge_id` | [doc_flow_service.py](file:///d:/filework/excel-to-diagram/meta/services/doc_flow_service.py#L41-L46) | 「正数减红字」与「排除撤销边」无需改表 |
| E4 | `_rule_view()` 已暴露 `target_line_bo` / `head_fk_field` | [doc_flow_service.py](file:///d:/filework/excel-to-diagram/meta/services/doc_flow_service.py#L83-L105) | 规则层重复声明头-行关系，是 §3 的佐证，也是 P3 去重对象 |
| E5 | 响应统一为 `{success, data, message}` / `{success, data, message: null, code}` | [doc_flow_api.py](file:///d:/filework/excel-to-diagram/meta/api/doc_flow_api.py#L33-L47) | 新端点必须沿用 |
| E6 | 视图体与装饰器分离，`_xxx_view()` 为无装饰器纯函数 | [doc_flow_api.py](file:///d:/filework/excel-to-diagram/meta/api/doc_flow_api.py#L50-L116) | 新端点必须沿用（便于直接单测） |
| E7 | `/edges` 只有 `@login_required`，**无对象级读权限校验** | [doc_flow_api.py](file:///d:/filework/excel-to-diagram/meta/api/doc_flow_api.py#L140-L143) | 本次一并加固（§4.6） |
| E8 | `vendor_invoice_line`：`parent_object: vendor_invoice`、`hierarchy.parent_field: invoice_id`，无 `authorization`，`generic_api_mode` 取默认 `full` | [vendor_invoice_line.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/vendor_invoice_line.yaml#L22-L63) | 行可绕过单头被写（P2 缺口，本 spec 不修，只登记） |
| E9 | 迁移最大编号 = v259 | `meta/migrations/` | 若需迁移，编号从 **v260** 起；本 spec P0 **不需要迁移** |

---

## 2. 目标与非目标

### 2.1 目标

| # | 目标 |
|---|---|
| G1 | 单据头详情页可查到「头级上下游」，不再因边落在行级而为空 |
| G2 | 一次请求返回上下游，前端不再发 2 次 `/edges` 并自行拼装 |
| G3 | 「头 → 行」解析规则**只在一处实现**，`TraceGraphService` 二期可直接复用 |
| G4 | 聚合口径明确：同一对端单据的多个行合并成一行，数量按 `Σ正数 − Σ红字` |
| G5 | 查询走既有索引，不引入全表扫描 |
| G6 | 新增 `aggregate_root` 派生访问器，消除「头-行关系散落 6 处」的读侧漂移 |

### 2.2 非目标

- **不新增 `bo_root` / `aggregate_root` schema 字段**（零 YAML 改动，见 §3.1）。
- **不改 `/edges` 的请求/响应契约**（只加权限校验，见 §4.6）。
- **不做写侧门控**（行写解析根权限 / 根状态锁行）→ P2 单独 spec。
- **不做多级聚合**（头 → 行 → 子行）→ 首期只展开一跳，见 §6 待确认 Q1。
- **不改 `quantity_sign` / `doc_flow_edges` 表结构**。
- **不替换 `v_demand_trace_graph`**：计划层追溯仍走该视图，本 spec 只统一「头→行」这一段。

---

## 3. aggregate_root：概念定位与 P0 派生访问器

### 3.1 为什么不是 `bo_root` 字段

三条反对证据：

| # | 证据 | 结论 |
|---|---|---|
| R1 | `permission_dimension_api` 已有 `root_object: 'product'`（架构根）；`audit_operation_api` 已有 `root_object: f"{object_type}#{object_id}"`（审计级联根） | 「root」在本仓已有两种不兼容语义，新增 `bo_root` 会造成第三种，术语通胀 |
| R2 | `parent_object` 已同时承担三种语义：单据聚合（`vendor_invoice_line → vendor_invoice`）、主数据从属（`customer_sales_org → customer_account`、`item_* → item`）、架构层级（`business_object → service_module`、`domain → version`） | 再存一个 `bo_root` 会与 `parent_object` 形成**第四个**冗余声明，而非消解 |
| R3 | `semantics.category` 不能作为判据：`document_hu_link` 是 `business_document_line` 但**无** `parent_object`；`demand_trace_link` / `document_serial_link` 同类；`customer_sales_org` 是 `core_entity` 却**有**父 | 静态分类无法推导聚合根，必须**按对象链动态判定** |

因此：`aggregate_root` 作为**读时派生的语义概念**存在，不落库、不进 YAML。

### 3.2 判定规则（`get_aggregate_root`）

在 [models.py](file:///d:/filework/excel-to-diagram/meta/core/models.py#L1398-L1406) 的 `get_hierarchy_ancestors()` 基础上增加**边界停止条件**（现有实现无边界，会一路穿到架构链）：

```
输入：obj（MetaObject）
输出：MetaObject | None（聚合根）；obj 自身已是根时返回 obj

1. 若 obj.aggregate_root 显式存在（当前无此字段，留扩展位）→ 以显式值为准
2. cur = obj；visited = {cur.id}
3. loop:
     parent_id = cur.parent_object
     if not parent_id: return cur if cur 是单据类 else None
     if parent_id in visited: return None            # 环保护
     parent = registry.get(parent_id)
     if parent is None: return cur if cur 是单据类 else None
     if 跨域(parent): return None                   # 进入架构链，不是聚合
     visited.add(parent_id)
     if is_document_head(parent): return parent      # 命中单据头，停
     cur = parent
```

其中：

- `跨域(parent)` = `parent.category in ('meta_object', 'system_entity')` 或 `parent.semantics.category in ('architecture', 'platform')` → 说明已离开业务单据域。
- `is_document_head(o)` = `o.parent_object == ''` 且 `o.semantics.category == 'business_document'`。
- **无父的 `business_document_line`**（如 `document_hu_link`、`demand_trace_link`）→ 返回 `None`（明确「不参与单据聚合」），不得报错。

### 3.3 三个访问器（P0）

| 方法 | 签名 | 行为 |
|---|---|---|
| `get_aggregate_root()` | `(self) -> Optional[MetaObject]` | 按 §3.2 返回聚合根；自身是根返回自身 |
| `get_aggregate_children()` | `(self) -> List[MetaObject]` | 返回 `parent_object == self.id` **且** 自身是单据头 的**全部**子对象列表；替换 [hierarchy_utils.py](file:///d:/filework/excel-to-diagram/meta/services/query/hierarchy_utils.py) 中 `get_child_object_id()` 只返回第一个的行为（该函数保留不动，新增不替换） |
| `get_aggregate_parent_field()` | `(self) -> str` | 取 `hierarchy.parent_field`；缺省时回落 `{parent_object}_id`；两者皆无返回 `""` |

`get_aggregate_children()` 必须**稳定排序**（按 `registry` 注册顺序，即 id 字典序），保证 trace 结果可复现。

### 3.4 单测要求（P0 必须覆盖）

| 用例 | 断言 |
|---|---|
| `vendor_invoice_line` | root == `vendor_invoice`；parent_field == `invoice_id` |
| `vendor_invoice` 自身 | root == 自身；children 含 `vendor_invoice_line` |
| `customer_sales_org` | root == `None`（`customer_account` 非单据头） |
| `document_hu_link` | root == `None`（无父的行级对象） |
| `business_object` | root == `None`（进入架构链即停） |
| 环（人为造 A→B→A） | 返回 `None`，不抛异常、不死循环 |
| 多头下多子对象 | children 返回全部，不丢第二个 |

落位：`meta/tests/test_doc_flow_trace.py`（已新建，12 用例全绿），用 `registry` 的测试桩对象构造，不依赖真实 DB；另含 1 个真实 schema 用例（`vendor_invoice_line` → `vendor_invoice`）。

---

## 4. 方案 B：头 → 行追溯

### 4.1 端点契约

```
GET /api/v2/doc-flow/trace?bo=<对象ID>&id=<单据ID>
```

- 参数：`bo` 必填（对象标识，如 `vendor_invoice`）；`id` 必填（单据头或行 id）。
- 语义：**`id` 可以是头 id，也可以是行 id**，服务层自动向上归一（行 → 其所属头），避免前端判断。
- 权限：`@login_required` + 对象级读权限（§4.6）。
- 路由注册：`@doc_flow_bp.route('/trace', methods=['GET'])`，视图体 `_trace_view()` 为无装饰器纯函数（E6）。

响应（成功）：

```json
{
  "success": true,
  "message": "",
  "data": {
    "object": "vendor_invoice",
    "root_object": "vendor_invoice",
    "root_id": "VI-0001",
    "upstream":   { "items": [ /* 聚合后的边 */ ], "total": 2 },
    "downstream": { "items": [ /* 聚合后的边 */ ], "total": 1 },
    "expanded": true,
    "line_scope": { "object": "vendor_invoice_line", "count": 3, "ids": ["...", "..."] },
    "truncated": false
  }
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `object` | str | 请求的 `bo` 回显 |
| `root_object` / `root_id` | str | 归一后的聚合根；无根时为 `""` |
| `upstream` / `downstream` | object | 与 `/edges` **同形**的 `{items, total}`，便于前端复用渲染 |
| `expanded` | bool | `true` = 发生了头→行展开（请求的是头且存在行）；`false` = 直接按 id 命中 |
| `line_scope` | object | 本次展开的行使集合；仅 `expanded == true` 时有意义 |
| `truncated` | bool | 行使数量超上限（默认 500）时为 `true`，`line_scope.ids` 只含前 N 个 |

失败沿用 `_fail(code, message, status)`。

### 4.2 scope resolver（唯一实现点）

新增函数（置于 `meta/services/query/hierarchy_utils.py` 或 `doc_flow_service.py` 私有方法，**只能有一处**）：

```
resolve_line_scope(bo: str, id: str) -> LineScope
  LineScope = {object, ids: List[str], head_id: str, head_object: str, expanded: bool}
```

逻辑：

1. `obj = registry.get(bo)`；不存在 → `DOC_FLOW_BO_NOT_FOUND`(404)。
2. `root = obj.get_aggregate_root()`：
   - `root is None` 且 `obj` 不是单据头 → 退化为「直接用 `bo + id` 查边」（`expanded = false`，`ids = [id]`）。
   - `root` 存在且 `root.id == bo` → 视为头：`children = obj.get_aggregate_children()`。
     - `children` 为空 → `ids = [id]`，`expanded = false`（无边可展开，不是错误）。
     - `children` 非空 → 逐个子对象取 `fk = child.get_aggregate_parent_field()`；`fk` 为空则该子对象跳过并记 `warning`（不打断）；
       SQL 取 `SELECT CAST(id AS TEXT) FROM <child.table_name> WHERE <fk_col> = ?` 得到行 id 集合；`expanded = true`。
3. `obj` 是行（`root.id != bo`）→ 先查自身 `fk` 反查头 id，归一到头后执行步骤 2；`root_id` 记录头 id。
4. `ids` 去重、排序、截断到 `_MAX_TRACE_LINES = 500`；超出置 `truncated = true`。

**关键约束**：resolver **不读 `doc_flow_rule`**，只读 `parent_object` + `hierarchy.parent_field`（§3.3）。规则层声明仅作为 P3 一致性 lint 的校验对象，不作为运行时依赖。

### 4.3 聚合键与数量

`upstream` / `downstream` 的 `items` 由边记录聚合而来，聚合键：

```
(对端 bo, 对端 id, 对端 item, rule_id)
```

- 对端：查上游时对端 = `source_bo/source_id/source_item`；查下游时对端 = `target_bo/target_id/target_item`。
- `quantity` = `Σ(quantity_sign = 'normal' 的数量) − Σ(quantity_sign = 'red' 的数量)`，取绝对值后按符号汇总，最后 `round(..., 6)`。
  - `quantity_sign` 是**字符串枚举** `normal` / `red`（见 [doc_flow_schema.py](file:///d:/filework/excel-to-diagram/meta/core/doc_flow_schema.py#L69-L70)），不是 `+1/-1`；空值按 `normal` 兜底。
- `status`：**只取 `status = 'active'`**（撤销边 `status = 'reversed'` 不计入数量，但计入 `raw_count`）。
- 输出项字段（在 `_EDGE_COLUMNS` 基础上裁剪、增加聚合信息）：

```json
{
  "peer_bo": "purchase_order_line",
  "peer_id": "PO-0007",
  "peer_item": "10",
  "rule_id": "vendor_invoice_from_po",
  "quantity": 12.0,
  "unit": "EA",
  "edge_ids": ["e-1", "e-2"],
  "edge_count": 2,
  "raw_count": 3,
  "first_derived_at": "2026-11-10T08:12:00",
  "last_derived_at": "2026-11-11T09:30:00"
}
```

- `edge_ids` 供下钻（前端点击可展开明细）；`raw_count` 含撤销边，`edge_count` 仅 active。
- **数量为 0 的聚合项不隐藏**（可能正负完全冲销），但加 `"balanced": true`，供前端灰显。

### 4.4 SQL 与索引

共享一条边查询（`_EDGE_COLUMNS` 已有全部所需列）：

```sql
-- 下游：边落在 target 侧
SELECT <_EDGE_COLUMNS>
  FROM doc_flow_edges
 WHERE target_bo = ?
   AND target_id IN (SELECT CAST(id AS TEXT) FROM <child_table> WHERE <fk_col> = ?)
 ORDER BY derived_at, id;

-- 上游：边落在 source 侧
SELECT <_EDGE_COLUMNS>
  FROM doc_flow_edges
 WHERE source_bo = ?
   AND source_id IN (SELECT CAST(id AS TEXT) FROM <child_table> WHERE <fk_col> = ?)
 ORDER BY derived_at, id;
```

- **文本 id 口径**：子查询 `CAST(id AS TEXT)`，与 [list_sources()](file:///d:/filework/excel-to-diagram/meta/services/doc_flow_service.py#L150-L215) 的 `CAST(s.<id_col> AS TEXT)` 一致（E2 反查）。
- **索引**：命中 `idx_doc_flow_target(target_bo, target_id, status)` 与 `idx_doc_flow_source(source_bo, source_id, status)`（v231 已建）；无需新增索引。
- 子查询用 `IN (SELECT ...)` 而非 `JOIN`：`doc_flow_edges` 无外键，`JOIN` 会在多行时放大结果集。
- 边数上限保护：单次查询 `LIMIT _MAX_EDGES (1000)`，超出置 `truncated = true`。

### 4.5 前端改造

| 文件 | 改动 |
|---|---|
| [docFlowService.js](file:///d:/filework/excel-to-diagram/src/services/docFlowService.js#L24-L27) | 新增 `export async function traceDocuments(params)` → `apiV2.get('/doc-flow/trace', { params })`，`return resp.data`，与既有 4 个函数同风格 |
| [DocFlowTracePanel.vue](file:///d:/filework/excel-to-diagram/src/components/business/DocFlow/DocFlowTracePanel.vue) | 由「`listEdges` 两次（源侧 / 目标侧）」改为「`traceDocuments` 一次」；读 `data.upstream.items` / `data.downstream.items`（`items` 兼容上一轮已修）；`expanded === true` 时在面板标题旁显示「含 N 行」；`truncated === true` 时显示截断提示 |

**不改**：`DetailPage.vue` 的 `docFlowMatched` 判定、`/edges` 调用（其它页面仍在用）。

### 4.6 `/edges` 兼容与权限加固

- `/edges` 请求参数、响应结构、错误码**全部不变**（回归风险最低）。
- 加固：在 `_edges_view()` 内，对 `source_bo` / `target_bo` 校验调用者对该对象的读权限；无权限 → `DOC_FLOW_FORBIDDEN`(403)。
  - **复用现成工具，不新增权限设施**：[auth_middleware.py](file:///d:/filework/excel-to-diagram/meta/services/auth_middleware.py#L167-L181) 已有 `check_generic_read_permission(object_type)`，语义为「`None` = 放行，否则返回 `allowed=False` 的 `PermissionDecision`」，按 canonical `<object_type>:read` 或 YAML `authorization.permissions.read` 判定，管理员 `*` 放行。
  - `/trace` 同样校验 `bo` 与 `root_object`（两者都非空时各查一次）。
- **顺序**：先加权限校验（可单独提交、可单独回归），再做 `/trace`（避免一次提交混合两件事）。

### 4.7 新增错误码

| code | status | 触发 |
|---|---|---|
| `DOC_FLOW_TRACE_ARGS_REQUIRED` | 400 | 缺 `bo` 或 `id` |
| `DOC_FLOW_BO_NOT_FOUND` | 404 | `registry.get(bo)` 为空 |
| `DOC_FLOW_FORBIDDEN` | 403 | 对象读权限不足（`/edges` 与 `/trace` 共用） |

沿用既有码：`DOC_FLOW_RULE_NOT_FOUND`(404)、`DOC_FLOW_RULE_INVALID`(409)。**不新增**码给「无行可展开」——那不是错误，返回 `expanded: false` 即可。

---

## 5. 分期

| 期 | 内容 | 是否本 spec |
|---|---|---|
| **P0** | `get_aggregate_root()` / `get_aggregate_children()` / `get_aggregate_parent_field()`；`resolve_line_scope()`；`/trace` 端点；前端单次调用；`/edges` 权限加固 | 是（本 spec 全部实现范围） |
| **P1** | schema 一致性 lint：`org_scope.chain.host/via`、`deletion_policy.cascade`、`child_sections`、`doc_flow_rule.target_line_bo/head_fk_field` 必须与 `parent_object` + `hierarchy.parent_field` 一致，不一致即 CI 报错 | 否（另立） |
| **P2** | 写侧门控：行写解析根权限 + 根状态锁行（`vendor_invoice_line` 无 `authorization`、`generic_api_mode=full` 的缺口） | 否（高风险，单独 spec） |
| **P3** | `doc_flow_rule` 去重：`target_line_bo` / `head_fk_field` 改为由模型派生，规则表只保留业务语义字段 | 否（依赖 P1 落地） |

---

## 6. 待确认口径（默认值已定，评审时请确认）

| # | 问题 | 本 spec 默认 |
|---|---|---|
| Q1 | 是否支持多级聚合（头 → 行 → 子行）？ | **首期只展开一跳**。理由：v254 三条规则均为一跳；多级需先确认子行的 `parent_object` 是否稳定（`document_hu_link` 等无父行会污染链路）。 |
| Q2 | 写侧是否「根状态锁行」（头 `draft` 才允许写行）？ | **本 spec 不做**，登记到 P2。当前行为不变，避免与既有业务写路径冲突。 |
| Q3 | `line_scope.ids` 上限 500 / 边上限 1000 是否合适？ | 暂定，可在压测后调。超限只置 `truncated`，不报错。 |
| Q4 | 聚合项数量为 0（正负完全冲销）是否保留？ | **保留**并标 `balanced: true`。 |

---

## 7. 验收标准

| # | 用例 | 期望 |
|---|---|---|
| AC-01 | `vendor_invoice` 头（有 3 行、行上有 v254 边）调 `/trace` | `expanded == true`，`line_scope.count == 3`，`upstream.items` / `downstream.items` 非空 |
| AC-02 | 同上，用行 id 调 `/trace` | 归一到头，返回与 AC-01 **完全相同**的 `upstream/downstream` |
| AC-03 | 无行的 `vendor_invoice` 头 | `expanded == false`，`items` 为空数组，HTTP 200（不是 4xx） |
| AC-04 | `document_hu_link` 一类无父行对象 | 不报错，退化为按 `bo + id` 直查 |
| AC-05 | 同一对端单据 2 行各 5 与 7，另有 1 条红字 -2 | `quantity == 10.0`，`edge_count == 3`，`raw_count == 3` |
| AC-06 | 一条边 `status = 'reversed'` | 不计入 `quantity`，计入 `raw_count` |
| AC-07 | 正负完全冲销 | 项保留，`quantity == 0`，`balanced == true` |
| AC-08 | 超过 500 行 | `truncated == true`，`line_scope.ids` 长度 == 500，HTTP 200 |
| AC-09 | 无读权限的对象 | `/edges` 与 `/trace` 均返回 403 `DOC_FLOW_FORBIDDEN` |
| AC-10 | `/edges` 原 4 种调用方式 | 响应结构与改造前**逐字段一致**（回归） |
| AC-11 | 缺 `bo` 或 `id` | 400 `DOC_FLOW_TRACE_ARGS_REQUIRED` |
| AC-12 | `bo` 不存在 | 404 `DOC_FLOW_BO_NOT_FOUND` |
| AC-13 | 前端面板 | 打开头级详情页，1 次 `/trace` 请求（Network 面板可见），两张表均有数据 |
| AC-14 | `aggregate_root` 单测 | §3.4 七个用例全绿 |

---

## 8. 测试与验证入口

- 后端单测：
  ```
  python d:\filework\test.py --single meta/tests/test_doc_flow_trace.py::test_line_resolves_to_head
  python d:\filework\test.py --single meta/tests/test_doc_flow_trace.py::test_trace_expands_head_to_lines
  python d:\filework\test.py --single meta/tests/test_doc_flow_api.py::test_trace_view_passes_args
  ```
  （禁止 `pytest` / `python -m pytest`；`--single` 只接受 `path::func`，不带类名。）
- API 冒烟（认证为 httpOnly cookie，需 `requests.Session()` + dev-login）：
  ```
  curl.exe -s "http://localhost:3011/api/v2/doc-flow/trace?bo=vendor_invoice&id=VI-0001"
  ```
  （禁 PowerShell `curl` 别名。）
- 前端静态校验：`npx vue-tsc --noEmit`（或项目既有 lint 脚本）。
- 收尾：`python d:\filework\test.py --failed` 串行确认。

---

## 9. 变更清单

| 类型 | 文件 | 说明 |
|---|---|---|
| 改 | `meta/core/models.py` | 新增 3 个 `aggregate_root` 派生访问器（§3.3），不改 `get_hierarchy_ancestors()` 既有行为 |
| 改 | `meta/services/doc_flow_service.py` | 新增 `resolve_line_scope()`（或放 `hierarchy_utils.py`）+ `trace_records()` + 聚合函数；`list_edges()` 不动 |
| 改 | `meta/api/doc_flow_api.py` | 新增 `_trace_view()` + `/trace` 路由；`_edges_view()` 加 `check_generic_read_permission` 校验 |
| 不进 | `meta/services/auth_middleware.py` | 无需改动：`check_generic_read_permission`（L167）已满足要求，直接复用 |
| 改 | `src/services/docFlowService.js` | 新增 `traceDocuments(params)` |
| 改 | `src/components/business/DocFlow/DocFlowTracePanel.vue` | 两次 `/edges` → 一次 `/trace` |
| 新 | `meta/tests/test_doc_flow_trace.py` | §3.4 七个聚合根用例 + 5 个 `/trace` 服务用例 |
| 改 | `meta/tests/test_doc_flow_api.py` | AC-01~AC-12 覆盖（含 `/trace` 参数校验、路由清单） |
| 迁移 | 无 | P0 不改表、不加索引、不写数据；如后续需要，编号从 **v260** 起 |

---

## 10. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 头→行展开后单次返回边过多 | `LIMIT 1000` + `truncated` 标记；`line_scope` 上限 500 |
| `hierarchy.parent_field` 缺失导致解析错列 | `get_aggregate_parent_field()` 回落 `{parent}_id`；仍为空则跳过该子对象并记日志，不中断 |
| 权限加固误伤既有页面 | 先单独提交权限校验，用 AC-10 回归；有权限用户行为不变 |
| 前端改造影响其他用 `/edges` 的页面 | `/edges` 契约完全不动，仅 `DocFlowTracePanel` 切换数据源 |
| 回滚 | 前端回退到两次 `listEdges` 即可（后端新增端点保持存在、无副作用）；后端回退只需删除 `/trace` 路由与新增函数，未改表故无数据回滚 |