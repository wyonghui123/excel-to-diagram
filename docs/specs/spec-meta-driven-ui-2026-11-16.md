# Spec：元数据驱动 UI 的收敛落地（v1.1 文法 + 地基 + 对象迁移）

- 状态：待评审（Draft）
- 日期：2026-11-16
- 关联：`docs/specs/plan-integration-p1p2-2026-11-16.md`（S8-2/S8-3/S8-5 已落地）
- 对标依据：Salesforce（Dynamic Forms / 决策指南）、ServiceNow（`sys_ui_*`）、SAP Fiori Elements（annotations + extension）、Odoo（`ir.ui.view` 继承）、Oracle Fusion（Page/Application Composer）、Power Apps（model-driven form/view）

---

## 1. 背景与结论

集成三页已收敛为「YAML 声明 + 通用组件」，与头部产品同构。但审计后确认：

| # | 事实 | 影响 |
|---|---|---|
| F1 | 仅 3 个对象声明 `list.data_source` + `list.actions` + `menu.route` | 其余对象无法被通用组件驱动 |
| F2 | `audit_log` 已有 YAML，前端却在 [auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) 重复声明列/筛选/枚举 | 同一事实两处维护，必然漂移 |
| F3 | `ui-meta` 已下发 `field_policies`（`readable/writable/roles`），但前端未消费 | 权限/可见性仍散落在页面 `v-if` |
| F4 | 无 `ui_view_config` 校验；`lint_metamodel.py` 只覆盖 relations/actions/permissions/doc-flow | 配错只有在运行时才暴露 |

对标结论（用于约束设计，不是复述）：

1. 声明式覆盖「列表 / 表单 / 动作 / 菜单」是头部默认，**只读运维列表一律声明式**（ServiceNow `sys_audit` + list view；Salesforce Setup Audit Trail）。
2. 复杂页保留手写，但**手写点必须是明确的 extension point**（Fiori fragment / Odoo inherit / Power Apps Custom Page），而不是复制整页。
3. 差异通过**继承/变体**表达，不是复制（Odoo `inherit_id` + xpath）。
4. 元数据必须是**可校验、可回显、可版本化**的第一类对象（SAP 明确警告注解与模型不同步会报错）。

---

## 2. 目标 / 非目标

### 目标
- G1 给出 YAML v1.1 文法：对象级**变体（variants）**、条件可见性、字段只读、动作可见性。
- G2 后端 `ui-meta` 输出可诊断（`warnings` / `explain=1` 来源行号），并新增 `--ui-config` 校验。
- G3 前端通用组件消费条件与字段策略，未知声明**告警不静默**。
- G4 按序收敛 `audit_log` → `task_run` → `handling_unit`（列表）→ `print_template`（列表）。
- G5 用户级列表个性化（列序/列宽/每页条数/筛选）本地持久化，元数据变更自动失效。

### 非目标（明确不做，避免渲染器膨胀）
- ❌ 前端表达式语言 / 脚本钩子（条件文法封闭、可静态校验）。
- ❌ 跨对象视图继承（当前真实需求是同对象多视图，用 `variants` 足够）。
- ❌ 元数据入库（YAML 仍是唯一真源）+ 可视化 Builder。
- ❌ 通用渲染器承载审批流、字段 diff、向导（`engineering_change` / `rule_center` 继续手写）。
- ❌ 用户个性化同步到后端（先本地）。

---

## 3. 现状基线（契约事实）

`GET /api/v1/meta/<object_type>/ui-meta`（[meta_api.py:583](file:///d:/filework/excel-to-diagram/meta/api/meta_api.py#L583)）当前输出：

| 键 | 来源 | 说明 |
|---|---|---|
| `schema_version` | [view_config_service.py:522](file:///d:/filework/excel-to-diagram/meta/services/view_config_service.py#L515-L525) | schema 目录 hash，可作前端缓存失效键 |
| `list.columns/actions/data_source/stats` | [`_list_block`](file:///d:/filework/excel-to-diagram/meta/api/meta_api.py#L470-L483) | `data_source`/`stats` 未声明时为 `null` |
| `form/detail/filters` | `_form_block/_detail_block/_filters_block` | 表单字段与详情分区 |
| `field_policies` | [`_policies_block`](file:///d:/filework/excel-to-diagram/meta/api/meta_api.py#L567-L580) | 仅输出非默认：`{readable,writable,roles}` |
| `partial` | 聚合端点 | 单块构建失败降级 |

YAML 侧模型：[UIListViewConfig / UIListViewColumn](file:///d:/filework/excel-to-diagram/meta/core/models_ui_config.py#L9-L73)（已含 `data_source`、`stats`、`detail_mode`）。
前端消费：[metaResourceService.js](file:///d:/filework/excel-to-diagram/src/services/metaResourceService.js) + [MetaResourcePage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaResourcePage.vue)。

---

## 4. 详细设计

### 4.1 YAML v1.1 文法（增量，全部可选）

```yaml
ui_view_config:
  version: 2                      # 文法版本；缺省按 1 处理（= 当前行为）
  menu: {...}                     # 不变；variants 不允许覆盖 menu
  list:                           # 基础视图（不变）
    data_source: {...}
    actions: [...]
    columns: [...]
  variants:                       # 新增：同对象多视图（Odoo inherit 的轻量等价物）
    docs:
      title: 单据列表
      list:
        columns:
          - field: doc_no
          - field: status
            visible_when: {field: status, in: [draft, submitted]}
        actions:
          - id: export
            label: 导出
            position: toolbar
            roles: [admin, planner]
            http: {method: get, url: /api/v2/handling-unit/docs/export}
```

**合并语义（patch）**：逐层深合并；数组按稳定键合并（`columns→field`、`actions→id`、`form.fields→id`、`filters→key`），同名项覆盖，`_remove: true` 删除。

**条件文法（封闭）**，只允许以下形式之一：

```yaml
visible_when: {field: status, in: [failed, skipped]}
readonly_when: {field: source, equals: manual}
visible_when: {field: secret_ref, not_empty: true}
```

- 只允许单层条件对象，不嵌套、不允许 `and/or`（多条件请拆列/拆动作）。
- `field` 必须存在于该对象 schema（lint 校验）。
- 运行时遇到未知形式：**按“可见/可编辑”降级 + `console.warn` 一次**（理由：后端仍鉴权，隐藏导致空白页更难诊断）。

**作用位置**：
| 位置 | 支持键 |
|---|---|
| `list.columns[]` | `visible_when`、`roles` |
| `list.actions[]` | `visible_when`、`roles`（已有 `enabled_when`、`confirm`、`success_message`） |
| `form.fields[]` / 字段 schema | `readonly_when`、`visible_when`、`roles`（与 `permission` 合并，后端 `field_policies` 优先） |

**视图选择**：`GET /ui-meta?view=docs`；前端由 `route.meta.integrationResource.view` 或 `?view=` 传入；未声明 `variants` 时行为完全不变。

### 4.2 后端改动

| 文件 | 改动 | 兼容性 |
|---|---|---|
| [meta_api.py](file:///d:/filework/excel-to-diagram/meta/api/meta_api.py#L470-L483) `_list_block` | 列/动作透传 `visible_when/roles`；接受 `view` 参数选变体 | 未声明则输出不变 |
| `_action_to_dict` | 白名单增加 `visible_when`、`roles` | 纯增量 |
| `_policies_block` | 合并字段级 `visible_when/readonly_when`（YAML）与 `permission` | 输出结构保持 `{readable,writable,roles}` + 新增可选键 |
| `get_ui_meta` | 顶层新增 `meta: {warnings: [], effective_view, schema_version}`；`?explain=1` 时附 `sources: [{file, key, line}]` | 新增键，旧消费方无感 |
| `view_config_service` | 实现 `variants` 合并 + 环检测；合并结果参与 `schema_version` 指纹 | 无 variants 时结果不变 |

**错误分级**（关键决策）：
- 构建期（lint / doctor / CI）：结构错误**硬失败**（非零退出）。
- 运行期：结构错误**降级**——跳过该条动作/列，写入 `meta.warnings`，页面仍可用（不能因一个对象配错白屏）。

### 4.3 校验：`lint_metamodel.py --ui-config`

| 规则 | 内容 |
|---|---|
| R-UI-01 | `version` ∈ {1,2}；v2 才允许 `variants` |
| R-UI-02 | `data_source.url` 以 `/api/` 开头；`method` ∈ GET/POST；`items_path/total_path` 必填 |
| R-UI-03 | `params_map` 值域 ⊆ `{page,pageSize,sort,order,keyword}`；禁止反向 |
| R-UI-04 | `actions[].id` 唯一；`position` ∈ `{row,toolbar}`；有 `http.url`；`dialog` ∈ `{none,form}` |
| R-UI-05 | 占位符只允许 `{row.<field>}`、`{id}`，且 `<field>` 存在于 schema |
| R-UI-06 | `columns[].field` ∈ schema 字段；`filterable: true` 的列必须声明 `filter_type` |
| R-UI-07 | `variants` 键合法、合并后仍满足以上规则；无自引用 |
| R-UI-08 | 条件文法合法（4.1），`field` 存在；`roles` 为字符串数组 |

接入：`python meta/tools/lint_metamodel.py --ui-config`（并纳入 `--all`）。

### 4.4 前端改动

**服务层** [metaResourceService.js](file:///d:/filework/excel-to-diagram/src/services/metaResourceService.js) 新增（纯函数，可单测）：
- `evalCondition(cond, row)` → boolean
- `isVisible(decl, row)` / `isActionVisible(decl, row)` / `isFieldReadonly(decl, row, policies)`
- `mergeFieldPolicies(uiMeta.field_policies, localDecl)`（后端优先）

**组件接线**：
| 组件 | 改动 |
|---|---|
| [MetaListPage](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue) | 列渲染前过滤 `visible_when=false`；动作列按 `visible_when` 隐藏（不是置灰） |
| [MetaResourcePage](file:///d:/filework/excel-to-diagram/src/components/common/MetaResourcePage.vue) | `customActions` 与 `variants` 解析；未知 action/字段 → `warnOnce` |
| [MetaForm.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaForm.vue) | `field.readonly` 与 `readonly_when` 合并；`roles` 命中失败则只读（不隐藏） |

**规则**：`roles` 仅做展示层过滤，**不替代后端鉴权**；页面不得再为同一字段写 `v-if`。

### 4.5 用户级列表个性化

- 存储：`localStorage['meta-ui:list:<object_type>:<schema_version>']`
- 内容：`{columnOrder: [], hidden: [], width: {}, pageSize, filters: {}}`
- 失效：`schema_version`（schema 目录 hash）变化 → 整条丢弃，避免列错位。
- 范围：仅 `MetaListPage` 内生效；不做后端同步（非目标）。

### 4.6 调试可观测性

- `ui-meta` 顶层 `meta.warnings[]`：`{code, where, message}`（如 `UNKNOWN_CONDITION`、`UNKNOWN_FIELD`）。
- `?explain=1`：返回 `meta.sources[]`（`file:line`），供排查“这份列到底从哪个 YAML 来的”。
- 前端对同一 warning 只 `console.warn` 一次（按 `object_type+code` 去重）。

---

## 5. 对象收敛清单

### 5.1 `audit_log`（P0，风险最低）

- **现状**：`AuditLogManagement.vue` 用 `MetaListPage` + 本地 [auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js)（列/筛选/枚举/`baseUrl: /api/v1/audit`）。
- **YAML 增量**（写进 `meta/schemas/audit_log.yaml`）：
  ```yaml
  ui_view_config:
    list:
      data_source:
        url: /api/v1/audit/logs
        method: get
        items_path: data.data      # 端点为 {data:[...], total}；经 httpClient 解包后为 data.data
        total_path: data.total
        params_map: {page: page, page_size: pageSize, object_type: object_type, action: action}
      actions:
        - id: export
          label: 导出
          position: toolbar
          http: {method: get, url: /api/v1/audit/logs/export}
        - id: detail
          label: 详情
          position: row
          http: {method: get, url: '/api/v1/audit/logs/{row.id}'}
      columns: [...]      # 从 auditLogMeta.js 迁移，枚举/颜色改由 YAML options 下发
  ```
- **页面改造**：删除 `auditLogMeta.js`；`AuditLogManagement.vue` 改为通用壳（保留自定义详情抽屉，作为唯一合法差异）；`SystemAdmin/index.vue` 已走通用页，二者共用同一份 YAML。
- **实现前置动作**：用 `grep` 复核 `/api/v1/audit/logs` 的返回结构后再回填 `items_path/total_path`（勿凭猜测）。
- **验收**：表头/筛选/枚举与迁移前逐项一致；导出与详情抽屉可用；`auditLogMeta.spec.js` 删除或改测 YAML 下发。

### 5.2 `task_run`（P1，M2 落地口径见 §4.9）

- 端点：`GET /api/v2/jobs/runs`；动作 `POST /api/v2/jobs/runs/{run_id}/retry`、`/cancel`。
- `enabled_when` 取后端 `capabilities` 同源值：cancel `in: [pending, claimed, running]`、retry `in: [failed, dead, cancelled]`（`timeout/queued` 不是本对象状态，原文作废）。
- 列保持页面级：`job`（job_name+job_code 复合）与 `progress` 不是 schema 字段，纳入 YAML 会触发 R-UI-06。
- 页面 `TaskRuns.vue` 消费 `data_source` + `actions`，保留轮询 / URL 同步 / 日志抽屉。

### 5.3 `handling_unit` / `print_template`（P2，**已修正：本里程碑不收敛**）

> 事实复核后本节原文作废，决策见 §4.9.3。

- `handling_unit`：`HandlingUnitDocs.vue` / `HandlingUnitSeal.vue` 实为「联接行查询页 + 扫码封箱工作台」，不是 `handling_unit` 对象列表 ⇒ 不适用 `variants`。
- `print_template`：唯一数据入口 `/api/print/templates` 走 `apiRoot` 命名空间，现有 `resolveRequest` 只认 `/api/v1`、`/api/v2`；且列表列含复合/派生（`template`、`scope`）⇒ 需先补命名空间与 computed 列，本里程碑保持手写。

### 5.4 明确不动

| 对象/页面 | 原因（对标依据） |
|---|---|
| `engineering_change`（List/Detail/Diff 三页） | 审批流 + 字段 diff + 多步动作，属“工作流产物”，头部用 Flow/Screen Flow 承载 |
| `RuleCenterPage` + `ApprovalPolicyPanel` | 复合工作台（多对象 + 树 + 矩阵），属 Custom Page 场景 |
| `PermissionSetCenter` / `RolePermissionCenter` | 树形授权矩阵，交互非 CRUD |
| `PlatformOpsJobs` / `JobSchedules` | 无对应 YAML，纯运维面 |
| `HandlingUnitDocs` / `HandlingUnitSeal` | 联接行查询 / 扫码封箱工作台，非对象列表；需联接聚合 + 状态机 + 专用权限（§4.9.3 复核关闭） |
| `PrintPlatform`（模板/绑定/命中试算 3 Tab） | 复合/派生列 + 专用版式编辑器 + 级联选项 + `/api/print` 管理台；收敛需扩渲染器，违反非目标（§4.9.3 复核关闭） |

---

### 4.7 M0 实施契约（decision-complete）

> 本节是 M0 的唯一执行口径。与上文冲突时以本节为准，并同步收窄 §4.1。

#### 4.7.1 决策修订（避免回归）

| # | 修订 | 理由 |
|---|---|---|
| D1 | 字段级 `visible_when` **保持 legacy 字符串表达式**（`UIAnnotation.visible_when: Optional[str]`），M0 不把它改成条件对象；表单条件只新增 `readonly_when`（dict）+ `roles` | 该字段已被详情页/表单按表达式字符串消费，改类型必然回归 |
| D2 | `roles` 未注入当前用户角色上下文时**不隐藏**（默认放行） | 前端拿不到角色时误隐藏会造成“页面空白”，后端仍鉴权 |
| D3 | 列级 `visible_when` 以 `row=null` 求值，false 即隐藏该列；现有 YAML 均未声明 ⇒ 行为不变 | 与 §4.4「列渲染前过滤」一致，且可静态校验 |
| D4 | YAML 加载器**不新增抛错路径**：variants / 条件结构错误由 `lint --ui-config` 硬失败，`ui-meta` 运行期降级 + `meta.warnings` | 配错不能白屏（§4.2 错误分级） |
| D5 | `explain=1` 的 `line` 为 YAML 文本扫描的**近似行号**（首个匹配行），仅用于定位文件 | 现有 registry 未持久化字段级行号，避免为此改造加载链 |

#### 4.7.2 数据模型（`meta/core/models_ui_config.py` / `models_annotations.py`）

- `UIListViewColumn` 新增：`visible_when: Dict[str, Any] = field(default_factory=dict)`、`roles: List[str] = field(default_factory=list)`。
- `UIViewConfig` 新增：`version: int = 1`、`variants: Dict[str, Dict[str, Any]] = field(default_factory=dict)`（原样保留 patch，不在加载期求值）。
- `UIAnnotation` 新增：`readonly_when: Optional[Dict[str, Any]] = None`、`roles: List[str] = field(default_factory=list)`。

#### 4.7.3 YAML 加载（`meta/core/yaml_loader.py`）

- `parse_ui_list_view_column`：读取可选 `visible_when`（dict，原样）/ `roles`（字符串数组，过滤非字符串项），写入列模型。
- `parse_ui_annotation`：读取可选 `readonly_when`（仅接受 dict，否则置 `None`，不抛错）/ `roles`（字符串数组）。
- `parse_ui_view_config`：读取 `version`（`int`，缺省 1；非法值回落 1）；读取 `variants`（必须是 dict，否则忽略并 `logger.warning`；每项非 dict 的条目丢弃）。其余键透传不变。
- `_parse_resource_list_actions`：`dict(item)` 已透传 `visible_when/roles`，**不新增校验抛错**（D4）。

#### 4.7.4 变体合并（新文件 `meta/core/ui_config/variant_merge.py`）

纯函数、无 registry 依赖，供 service 与 lint 共用：

- `merge_patch(base: dict, patch: dict, *, where: str = "") -> tuple[dict, list[str]]`
  - 逐层深合并；dict 递归；标量覆盖；`None` 覆盖。
  - 数组按稳定键合并：`columns→field|key`、`actions→id|key`、`filters→key`、`detail.sections→key`、`form.sections→key`、`form.fields→id|key`；同键覆盖，新键追加，`_remove: true` 删除。
  - patch 中出现 `variants` → 忽略并返回 warning `NESTED_VARIANTS`（禁止自引用/嵌套）。
- `apply_variant(base_config: UIViewConfig, patch: dict) -> tuple[UIViewConfig, list[str]]`
  - `dataclasses.asdict(base_config)` → `merge_patch` → `parse_ui_view_config`（函数内延迟 import 避免环）。
  - `version` 固定为 `base.version`，`variants` 置空（变体不携带变体）。

#### 4.7.5 服务层（`meta/services/view_config_service.py`）

- `get_view_config(object_type, view_name)`：
  - 现有命名视图（`ui_view_configs`）优先，保持原语义；
  - 若 `view_name` 命中 `base_config.variants`：`apply_variant`，缓存 `object_type:view_name`；失败时回退 base + `logger.warning`（运行期降级）。
- `get_available_views(object_type)`：在 `["default", *ui_view_configs.keys()]` 后追加 `variants` 键（去重）。
- `get_or_build_view_config`：签名不变；变体合并后的 config 继续走 `_merge_default_actions` / `_enrich_columns_with_field_meta`；`schema_version` 计算逻辑不变（fallback 指纹天然包含合并结果）。

#### 4.7.6 ui-meta 端点（`meta/api/meta_api.py`）

- `get_ui_meta`：
  - `view = request.args.get('view') or None`；`explain = request.args.get('explain') == '1'`。
  - `config = view_config_service.get_or_build_view_config(object_type, view)`。
  - `warnings: list[dict]` 贯穿各 block builder；结构 `{code, where, message}`。
  - `view` 不在 `get_available_views` → 记 `UNKNOWN_VIEW`，`effective_view = 'default'`。
  - 顶层新增 `meta: {warnings, effective_view, schema_version}`；`explain` 时 `meta.sources = _ui_view_sources(object_type, view)`。
- `_list_column_dict(col, field_map, warnings)`：仅当非空时下发 `visible_when` / `roles`；校验失败 → 跳过该键 + warning（`UNKNOWN_CONDITION` / `UNKNOWN_FIELD`）。
- `_action_to_dict(action, field_map, warnings)`：dict 形态校验 `visible_when/roles`，非法则删除该键 + warning；字符串形态不变。
- `_form_block`：字段项仅当非空时追加 `readonly_when`、`roles`；`visible_when` 仍输出 legacy 字符串。
- `_policies_block`：条目纳入条件扩为「permission 非默认 **或** `ui.readonly_when` **或** `ui.roles`」；输出结构保留 `{readable,writable,roles}`，新增可选 `readonly_when`；`roles` = permission.roles ∪ ui.roles（去重保序）。
- `_ui_view_sources(object_type, view=None)`（新私有函数）：在 `get_yaml_schema_dir()` 下扫描含 `^id:\s*<object_type>$` 的 YAML，返回 `[{file, key, line}]`，key ∈ `ui_view_config` / `list.columns` / `list.actions` / `variants.<view>`；未命中项省略。仅解释用，失败返回 `[]` 不抛错。

#### 4.7.7 lint（`meta/tools/lint_metamodel.py`）

新增 `lint_ui_config() -> tuple[list, int]`，扫描 `SCHEMAS_DIR.glob("*.yaml")`（跳过 `_` 前缀共享文件），实现 R-UI-01..08：

| 规则 | 判定 |
|---|---|
| R-UI-01 | `version ∈ {1,2}`；声明 `variants` 且 `version < 2` → 违规 |
| R-UI-02 | `list.data_source`：`url` 以 `/api/` 开头；`method ∈ {get,post}`；`items_path`/`total_path` 非空点路径 |
| R-UI-03 | `params_map` 值 ⊆ `UI_PARAMS_ALLOWED`（lint 顶部常量；当前 = `page/pageSize/page_size/sort/order/keyword/object_type/ordering`，末两项为 S8 既有资源页在用参数，按真实新增需求扩展） |
| R-UI-04 | `list.actions[]` 身份键 = `id`（v1 兼容 `action`/`key`）；同一视图内唯一；`position ∈ {row,toolbar}`；`http.url` 必填；`dialog ∈ {none,form}` |
| R-UI-05 | URL 占位符仅 `{row.<field>}` / `{id}`，`<field>` ∈ schema 字段 |
| R-UI-06 | `columns[].field`（v1 兼容 `key`）∈ schema 字段（`computed: true` / 声明 `value_help` / 有 `data_source` 时豁免）；显式 `filterable: true` 必须声明 `filter_type`。**列字段存在性与 filter_type 仅对 `version >= 2` 硬校验**（v1 语义冻结，避免误伤存量声明） |
| R-UI-07 | 变体名 `^[a-z][a-z0-9_]*$` 且 ≠ `default`；patch 为 dict；禁止嵌套 `variants`；合并结果重跑 R-UI-02..06 |
| R-UI-08 | 条件仅 `{field, in|equals|not_empty}` 单层；`in` 非空数组；`not_empty` 布尔；`field` ∈ schema；`roles` 为非空字符串数组；`readonly_when` 仅用于 form 字段 |

CLI：新增 `--ui-config`，并纳入 `--all` 与无参默认全跑；输出格式沿用 `[ui-config] <文件> :: <键> — <原因>`；存在违规退出码 1。
零违规基线 = 当前 3 个资源页（integration_connection / notification_delivery / import_staging_rows）；若既有声明触发违规，只做**行为等价**修正（如补显式 `filter_type`），不得改变运行时行为。

#### 4.7.8 前端

`src/services/metaResourceService.js`（新增纯函数，均可单测）：

- `evalCondition(cond, row)`：封闭文法；未知形式返回 `true`（降级可见/可编辑）。
- `isVisible(decl, row)` / `isActionVisible(decl, row)`：`visible_when` 为 false → false；`roles` 命中规则见 D2（未注入角色上下文一律放行）。
- `isFieldReadonly(decl, row, policies)`：`policies[key].writable === false` → true；`decl.readonly` → true；`evalCondition(decl.readonly_when, row)` → true。
- `mergeFieldPolicies(uiPolicies, localDecl)`：后端字段策略优先，返回合并结果供表单使用。
- `setCurrentRoles(roles)` + `warnOnce(objectType, code, message)`（按 `objectType+code` 去重 `console.warn`）。
- `toFormControls(fields, { editing, keyField, model, policies })`：`disabled` 改为 `isFieldReadonly(...)` 的结果；不破坏现有签名默认值。

组件接线：

| 文件 | 改动 |
|---|---|
| `src/services/metaTransformService.js` | `transformColumns` 透传 `visible_when` / `roles`；`transformActions` 透传 `visible_when` / `roles` / `enabled_when` / `http` / `dialog` / `refresh` / `success_message` |
| `src/composables/useMetaList.js` | `_loadMetaConfig` 调用 `metaService.getUiMeta(obj, { view: config.viewName })`；`_transformMetaToComponentFormat` 后对 `columns` 过滤 `isVisible(col, null)`；`getRowActions(row)` 结果过滤 `isActionVisible(action, row)`；toolbar 过滤 `isVisible(action, null)` |
| `src/services/metaService.js` | `getUiMeta(objectType, { force, view })`：缓存键 `${objectType}:${view || 'default'}`；`view` 存在时 URL 追加 `?view=<encoded>`；无 `view` 时请求与缓存行为与现状完全一致 |
| `src/components/common/MetaListPage/MetaListPage.vue` | 新增 `viewName` prop → 传入 `useMetaList`；无 prop 时不改变任何行为 |
| `src/components/common/MetaResourcePage.vue` | 新增 `view` prop（可由 `route.meta.integrationResource.view` 传入）→ `MetaListPage :view-name`；行动作改 `rowActionsFor(row)` 过滤 `isActionVisible`；`onToolbarAction` 未命中时 `warnOnce(...'UNKNOWN_ACTION')`；`formFields` 传入 `model` 与 `uiMeta.field_policies` |
| `src/components/common/MetaForm.vue` | 仅消费 `toFormControls` 已算好的 `disabled`，不新增条件逻辑 |

#### 4.7.9 测试与验收（L1 唯一入口）

| 项 | 命令 / 判据 |
|---|---|
| 后端既有 | `python d:\filework\test.py --file meta/tests/api/test_ui_meta_data_source.py --force` 全绿 |
| 新增后端 | `test_ui_meta_variants.py`（合并/未知 view/effective_view）、`test_ui_meta_conditions.py`（条件透传、非法条件降级 warning、explain sources）、`test_lint_ui_config.py`（R-UI-01..08 各 1 正 1 反） |
| lint | `python meta/tools/lint_metamodel.py --ui-config` 退出码 0；`--all` 不新增违规 |
| 前端单测 | `metaResourceService.conditions.spec.js`：`evalCondition` 四形态、`isVisible` roles 放行/命中、`isFieldReadonly` 后端优先 |
| 静态 | `npx eslint src/services/metaResourceService.js src/services/metaTransformService.js src/services/metaService.js src/composables/useMetaList.js src/components/common/MetaResourcePage.vue src/components/common/MetaListPage/MetaListPage.vue` |
| 构建 | `npx vite build` 通过 |
| 冒烟 | Playwright 打开集成三页：列数/筛选/枚举/动作与改动前逐项一致（仅允许新增不可见键），无 console error |

#### 4.7.10 交付边界

- 不 commit；不迁移 `audit_log/task_run/handling_unit/print_template`（M1/M2）；不做个性化（M3）。
- 回滚：删除新增可选键的消费即恢复（YAML 无声明时输出与现状逐字节等价，`schema_version` 之外无新增必需键）。

### 4.8 M1 实施契约：`audit_log` 收敛（decision-complete）

> 本节取代 §5.1 的实现细节；与 §5.1 冲突时以本节为准。M0 已完成并验证。

#### 4.8.1 复核事实（2026-11-16 实测）

| # | 事实 | 结论 |
|---|---|---|
| A1 | `auditLogMeta.js` 生产代码零引用（仅 `src/views/SystemManagement/meta/__tests__/auditLogMeta.spec.js` 引用） | 可直接删除，无需页面改造配合 |
| A2 | `AuditLogManagement.vue` 用 `MetaListPage`（非 `MetaResourcePage`），列/筛选已由 YAML `ui-meta` 驱动 | 只差 `data_source` / `actions` 的声明与消费 |
| A3 | `GET /api/v1/audit/logs` 返回 `{success, data:[...], total, page, page_size}`；SELECT 不含 `log_category/log_level` | `items_path: data`、`total_path: total`；现有这两列是死列，必须删 |
| A4 | `buildFetcher / runAction / resolveActionUrl` 硬编码 `apiV2`，`/api/v1/...` 会被拼成 `/api/v2/api/v1/...` | 必须先加命名空间路由 |
| A5 | `httpClient` 成功分支只透传 `body.data`，`body.total` 丢失 | 需透传顶层 `total`，否则分页 total 退化为本页条数 |
| A6 | `useMetaList.loadList` 只在显式 `options.fetcher` 时使用声明式 fetcher | 需在无 fetcher 时消费 `list.data_source` |
| A7 | R-UI-06 要求列字段 ∈ schema；`business_key` 是服务端计算字段，不在 schema | **不声明** `business_key` 列（其展示已由 `object_id` 自定义 cell 内联） |
| A8 | MetaListPage 对 `action.key === 'export'` 走内建 `handleBatchExport()`（前端 CSV），不读 `http` | 导出保持无 `http` 声明，页面不改 |
| A9 | MetaListPage 对 `action.key === 'detail'` 在 `enableDetail` 为真时打开**内建**抽屉，否则 emit `detail` | 保留默认值，页面行点击打开自定义抽屉 |
| A10 | `audit_log` 非 persistent，`/api/v2/bo/audit_log/actions/evaluate` 不可用 → `useMetaList` 行级动作 **fail-closed 全部隐藏**（实测运行实例确认） | **不声明**行级 `detail` 动作；详情仍由行点击触发 |

#### 4.8.2 决策

- **D5** `data_source` 消费点放在 `useMetaList.loadList`：无显式 `options.fetcher` 且 `meta.list.data_source` 存在时使用 `buildFetcher`；`MetaResourcePage` 显式 fetcher 优先，行为不变。
- **D6** 新增并导出纯函数 `resolveRequest(url, paramsMap)`：`/api/v1/*` → `apiV1` + 去前缀；`/api/v2/*` → `apiV2` + 去前缀；其他 → `apiV2` + 原路径。`buildFetcher / runAction / resolveActionUrl` 统一走它。
- **D7** 排序桥接：`params_map` 同时声明后端键 `sort_field` 与 `sort_direction` 时，把前端 `ordering`（`-field` / `field`）拆成二者并删除 `ordering`；未声明时原样透传（现有三页零影响）。
- **D8** `httpClient` 成功分支：`body.total !== undefined` 时补 `result.total`；`buildFetcher` 在 `total_path` 取不到时回退 `result.total`。
- **D9** 列集合 = 现有 YAML 列 − `log_category` − `log_level`；不新增 `business_key`（A7）；不声明行级 `detail` 动作（A10）。
- **D10** 删除 `auditLogMeta.js` + `auditLogMeta.spec.js`；以 Python 测试断言 YAML 下发替代。
- **D11** `lint_metamodel.py` 白名单追加 `action / user_name / created_at_start / created_at_end / sort_field / sort_direction`，仍为白名单硬校验。

#### 4.8.3 精确改动

`meta/schemas/audit_log.yaml`（`ui_view_config` 内）：

```yaml
ui_view_config:
  version: 2
  list:
    # title / description / defaultSort / pageSize / selectable 保持不变
    data_source:
      url: /api/v1/audit/logs
      method: get
      items_path: data
      total_path: total
      params_map:
        page: page
        page_size: pageSize
        action: action
        object_type: object_type
        user_name: user_name
        start_date: created_at_start
        end_date: created_at_end
        sort_field: sort_field
        sort_direction: sort_direction
    actions:
      - id: export        # 保持现状：无 http，走内建前端 CSV
        label: 导出
        icon: download
        type: default
        position: toolbar
    # 不声明行级 detail（A10：actions/evaluate 不可用，行级动作 fail-closed）
```

- 删除 `columns` 中 `log_category`、`log_level` 两项；其余列（含 `trace_id`）原样保留。
- `detail` 块保持不变（页面使用自定义抽屉，不消费该块）。

前端改动：

| 文件 | 改动 |
|---|---|
| `src/services/metaResourceService.js` | 新增导出 `resolveRequest`；`buildFetcher` 用 `resolveRequest` + `applyOrderingBridge`（D7）+ `total` 回退（D8）；`resolveActionUrl`/`runAction` 用 `resolveRequest` |
| `src/utils/httpClient.js` | 成功分支：`if (body.total !== undefined) result.total = body.total` |
| `src/composables/useMetaList.js` | `loadList`：`const fetcher = config.fetcher || (metaConfig.value?.list?.data_source ? buildFetcher(metaConfig.value.list.data_source) : null)`，随后 `fetcher ? fetcher(...) : boService.query(...)` |
| `src/views/SystemManagement/AuditLogManagement.vue` | 不改（A9/A10：行点击自定义抽屉保持现状） |

删除：`src/views/SystemManagement/meta/auditLogMeta.js`、`src/views/SystemManagement/meta/__tests__/auditLogMeta.spec.js`。

新增测试：

- `meta/tests/api/test_ui_meta_audit_log.py`：ui-meta 下发 `data_source`（url/items_path/total_path/params_map）、`actions` id 集合 = `{export, detail}`、columns 不含 `log_category/log_level`、`meta.effective_view == 'default'`。
- `src/services/__tests__/metaResourceService.dataSource.spec.js`：`resolveRequest` 三形态、`applyOrderingBridge` 命中/未命中、total 回退（mock apiV1/apiV2）。

#### 4.8.4 验证（L1 唯一入口）

| 项 | 命令 / 判据 |
|---|---|
| 新增后端 | `python d:\filework\test.py --file meta/tests/api/test_ui_meta_audit_log.py --force` |
| 既有后端 | `python d:\filework\test.py --file meta/tests/api/test_ui_meta_data_source.py --force` |
| lint | `python meta/tools/lint_metamodel.py --ui-config` 退出码 0 |
| 前端单测 | `npx vitest run src/services/__tests__/metaResourceService.dataSource.spec.js src/services/__tests__/metaResourceService.conditions.spec.js` |
| 静态 | `npx eslint` 仅本次改动文件 |
| 构建 | `npx vite build` 通过 |
| 冒烟 | Playwright 审计页：表头 = 日志ID/操作时间/操作人/操作类型/对象类型/对象ID/变更字段/旧值/新值/IP地址/链路ID，无 log_category/log_level；列表有数据（走 v1 data_source）；行点击打开自定义详情抽屉（标题「审计日志详情」）；`error_toasts = 0` |

#### 4.8.5 回滚

- 删除 `audit_log.yaml` 的 `data_source` 块 → `useMetaList` 回退 `boService.query`（D5 分支不触发），前端其余改动对无声明对象零影响。
- `resolveRequest` / `total` 透传 / 白名单追加均为纯增量，可单独回滚。
- 删除的两个前端文件可由 git 恢复；不涉及数据迁移。

### 4.9 M2 实施契约：`task_run` 收敛（decision-complete）

#### 4.9.1 事实复核（2026-11-16 实测）

| 事实 | 证据 |
|---|---|
| `GET /api/v2/jobs/runs` 返回 `{success, data:{items,total,page,page_size,has_more,meta.filters}}`；`httpClient` 已把 `body.data` 提到 `result.data` ⇒ `items_path: items` / `total_path: total` | [job_admin_api.py](file:///d:/filework/excel-to-diagram/meta/api/job_admin_api.py#L782-L801)、[httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js#L474-L498) |
| 能力位与 `enabled_when` 同源：`can_cancel` = `pending/claimed/running`；`can_retry` = `failed/dead/cancelled` | [job_admin_api.py](file:///d:/filework/excel-to-diagram/meta/api/job_admin_api.py#L201-L209) |
| `_action_to_dict` 原样拷贝 YAML 动作 dict ⇒ `enabled_when/http/success_message/refresh` 均会下发 | [meta_api.py](file:///d:/filework/excel-to-diagram/meta/api/meta_api.py#L421-L442)、[meta_api.py](file:///d:/filework/excel-to-diagram/meta/api/meta_api.py#L535-L548) |
| `useMetaList.loadList` 的 fetcher 参数为 `{page, pageSize, ...params}`，经 `params_map` 反查后发请求 | [useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js#L511-L531) |
| `buildFetcher` 只回 `{items,total}`，丢弃响应 `meta.filters` ⇒ 页面会丢动态筛选选项 | [metaResourceService.js](file:///d:/filework/excel-to-diagram/src/services/metaResourceService.js#L104-L138) |
| `HandlingUnitDocs/Seal` 查询/封箱工作台，数据是 `document_hu_links` 联接行，字段不在 `handling_unit` schema | [HandlingUnitDocs.vue](file:///d:/filework/excel-to-diagram/src/views/HandlingUnitDocs.vue#L186-L263)、[HandlingUnitSeal.vue](file:///d:/filework/excel-to-diagram/src/views/HandlingUnitSeal.vue#L133-L236) |
| `print_template` 数据入口 `/api/print/templates`（`apiRoot`），YAML 仅 `skip_auto_menu`，列含派生 `scope`/复合 `template` | [printService.js](file:///d:/filework/excel-to-diagram/src/services/printService.js#L19-L34)、[print_template.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/print_template.yaml#L157-L159) |

#### 4.9.2 决策

| # | 决策 | 理由 |
|---|---|---|
| M2-D1 | `task_run` 只收敛 `data_source` + `actions`；列 / 筛选 / 轮询 / URL 同步 / 详情抽屉保留页面实现 | 复合列与动态筛选选项无法满足 R-UI-06；避免行为回归 |
| M2-D2 | 动作由「`capabilities` 显隐」改为「YAML `enabled_when` 置灰」；后端 409 兜底 | 与 spec §4.1 动作文法一致；E2E 判据即「重试置灰」 |
| M2-D3 | `buildFetcher` 返回值新增 `meta`（透传响应 `data.meta`），纯增量 | 页面需要 `meta.filters` 维持动态筛选选项 |
| M2-D4 | `ui-meta` 拉取失败或对象未声明 `data_source` 时，页面回退 `jobService.fetchRuns` 并 `console.warn` 一次 | 运行期降级，页面不白屏（与 §4.2 错误分级一致） |
| M2-D5 | `handling_unit` 两页与 `print_template` 列表本里程碑不动（§4.9.3） | spec 原假设与代码事实不符；强行收敛会引入新渲染器 = 非目标 |

#### 4.9.3 范围修正

> 2026-11-16 复核结论：两项**正式关闭，不再列为候选**，按显式 extension point 保留手写（对标 Odoo `inherit_id` / Fiori fragment）。证据见本节末。

- `handling_unit`：不做 `variants.docs/seal`。两页分别是「单据↔容器联接行查询」和「扫码封箱工作台」，无 `handling_unit` 对象列表；`variants` 只 patch 对象视图，无法表达联接行聚合与扫码队列。归入 §5.4「明确不动」。
  - 实体列表本身**已经是声明式**（`meta/schemas/handling_unit.yaml` 的 `ui_view_config` 含 9 列/搜索/CRUD 动作，无 `skip_auto_menu`，走 `GenericObjectList`），无需二次迁移。
  - `HandlingUnitDocs.vue` 的数据源是 `document_hu_link_view`（`boService.query`），行是 link 视图行；`HandlingUnitSeal.vue` 走 `/api/v1/handling-units/scan|seal|batch-seal` 专用端点与 `handling_unit:seal/unseal` 权限，属状态机工作台。
- `print_template`：不做列表收敛。复核确认 5 个硬缺口：① 命名空间（2026-11-16 已补 `apiRoot` 分支，见 §4.11）；② `template/paper/scope/status` 为复合/派生列，YAML 列文法未声明 computed 形态（R-UI-06 要求字段 ∈ schema）；③ 编辑态是 HTML/CSS/纸张/边距/作用域专用编辑器；④ 筛选选项由 `/api/print/printable` 级联；⑤ 行级动作链含 validate/publish/fork-default 与专用编辑抽屉。
  - 即使只收敛「列表读」，也必须先扩 ②；扩完仍需保留行内 slot，YAML 只承载一半事实，维护成本高于收益。
  - `PrintPlatform.vue` 为 3 Tab 管理台（模板/绑定/命中试算），归入 §5.4「明确不动」。

#### 4.9.4 精确改动

**A. `meta/schemas/task_run.yaml`**（`ui_view_config.list` 内追加，保留现有 `columns/selection/searchFields/defaultSort`）

```yaml
    data_source:
      url: /api/v2/jobs/runs
      method: get
      items_path: items
      total_path: total
      params_map:
        page: page
        page_size: page_size
        job_code: job_code
        status: status
        source: source
        from: from
        to: to
    actions:
      - id: cancel
        label: 取消
        position: row
        http:
          method: post
          url: /api/v2/jobs/runs/{row.id}/cancel
        enabled_when: {field: status, in: [pending, claimed, running]}
        success_message: 已提交取消
        refresh: true
      - id: retry
        label: 重试
        position: row
        http:
          method: post
          url: /api/v2/jobs/runs/{row.id}/retry
        enabled_when: {field: status, in: [failed, dead, cancelled]}
        success_message: 已提交重试
        refresh: true
```

> 注：`run_id` 是响应别名，不在 `task_run` schema；R-UI-05 只接受 schema 字段，故占位符写 `{row.id}`，页面在 `executeRowAction` 内把 `run_id → id` 归一后再调 `runAction`。

**B. `meta/tools/lint_metamodel.py`**：`UI_PARAMS_ALLOWED` 追加 `job_code`、`status`、`source`、`from`、`to`。R-UI-03 仍硬校验，其他规则不改。

**C. `src/services/metaResourceService.js`**：`buildFetcher` 返回 `data` 内**仅当响应含 `result.data.meta` 时**附加 `meta` 键（不改 `items/total` 语义，无 `meta` 时返回结构与现状逐键一致）。

**D. `src/services/__tests__/metaResourceService.dataSource.spec.js`**：新增用例「响应含 meta 时透传 / 不含时无 `meta` 键」，既有断言不动。

**E. `src/views/TaskCenter/TaskRuns.vue`**

1. 移除 `fetchRuns/retryRun/cancelRun` 的硬编码调用与 `onCancel/onRetry/readableError/runAction` 本地实现（保留 `fetchRuns` 仅作降级）。
2. 新增：`uiMeta`、`rowActions`（`list.actions` 且 `position==='row'`）、`dataFetcher`（`buildFetcher(uiMeta.list.data_source, () => buildRequestParams())`）。
3. `loadRuns`：有 `dataFetcher` 用之，否则回退 `fetchRuns(buildRequestParams())`；`filtersMeta` 改从 `data.meta?.filters` 取（无则不覆盖）。
4. `#cell-actions` 插槽：按 `rowActions` 渲染（cancel → retry → 详情），`:disabled="!isActionEnabled(action, row)"`，点击 `@click.stop` 调 `executeRowAction`。
5. `executeRowAction(action,row)`：先把 `run_id → id` 归一（`{...row, id: row.run_id}`），再 `runAction(action,{row})` → 失败 `error(message)`；成功 `success(result.message)` → `loadRuns({silent:true})` → 抽屉打开则同步 `loadDetail(silent)` → `ensurePolling()`。
6. 不变：`FilterBar`、动态筛选选项、3s 静默轮询、`QUERY_KEYS`/`syncQuery`、`?run=` 深链、`Drawer` 详情与日志区、`MetaTable` 列定义。

**F. `meta/tests/api/test_ui_meta_task_run.py`**（新建）：`GET /api/v1/meta/task_run/ui-meta` 断言 `list.data_source`（url/items_path/total_path/params_map 键）、`list.actions`（顺序 cancel→retry、http.url、enabled_when.in 集合）。

#### 4.9.5 验证（L1 唯一入口）

1. `python d:\filework\test.py --file meta/tests/api/test_ui_meta_task_run.py --force`
2. `python d:\filework\test.py --file meta/tests/api/test_ui_meta_data_source.py --force`
3. `python meta/tools/lint_metamodel.py --ui-config`
4. `npx vitest run src/services/__tests__/metaResourceService.dataSource.spec.js`
5. `npx eslint src/views/TaskCenter/TaskRuns.vue src/services/metaResourceService.js`
6. `npx vite build`
7. 手工冒烟 `/system/task-runs`：列表/筛选/分页；cancel/retry 置灰与提交；详情抽屉；`?run=<id>` 深链；有活跃 run 时 3s 轮询。

判据：以上 1–6 全绿；冒烟项与改动前一致，唯一预期差异是动作按钮由「隐藏」变「置灰」。

#### 4.9.6 回滚

- 删除 YAML `data_source`/`actions` → 页面走 `fetchRuns` 降级路径且不渲染行级动作（代码保留降级分支）。
- `buildFetcher` 的 `meta` 为新增键，回滚无副作用。
- 不涉及后端端点、数据库与既有页面。

---

### 4.10 M3 实施契约：列表个性化（decision-complete）

> 范围只回填 §4.5。§4.6 的 `warnings` / `explain=1` 已在 M0 落地（后端 `?explain=1` + 前端 `warnOnce`），M3 不扩后端、不改 YAML。

#### 4.10.1 决策

| # | 决策 | 理由 |
|---|---|---|
| M3-D1 | 存储键 `meta-ui:list:<object_type>:<schema_version>`；值 `{columnOrder: string[], hidden: string[], width: Record<string, number>, pageSize: number\|null, filters: {panel: object, header: object}}` | `schema_version` 是 schema 目录 hash，天然作为失效键 |
| M3-D2 | 仅 `displayMode==='page'` 生效；`embedded` / `dialog` 复用同一 object_type，读写会互相污染，故直接跳过 | 个性化属于"用户看整页列表"的偏好；嵌入/弹窗由宿主页面决定列 |
| M3-D3 | 读取时机：`metaConfig.schema_version` 可用后一次性加载；若恢复值影响查询（pageSize / filters），补一次 `loadList()` | 首次渲染前拿不到版本号；仅"确有存量偏好"时才多一次请求 |
| M3-D4 | 列序：`columnOrder` 已知列前置，未知列丢弃，新增列按元数据顺序追加末尾；隐藏列与元数据 `visible`/`visible_when` 过滤取交集 | 元数据变更后不出现空白/错位列 |
| M3-D5 | 列宽：`el-table` 的 `header-dragend` 写回实际渲染宽度；渲染时优先用保存值（不再叠加排序/筛选图标补偿） | 避免每次拖拽把补偿值重复累加 |
| M3-D6 | 筛选持久化 `filterValues`（面板）与 `headerFilterValues`（表头），不含 `keyword` | keyword 属临时搜索，且页面可能已用 URL 同步 |
| M3-D7 | 不做列设置以外的 UI 改造；新增一个「列设置」popover（勾选显示 + 上下移序 + 恢复默认） | 没有入口时列序/隐藏无法被用户改变，功能等同空转 |
| M3-D8 | 仓储异常（隐私模式 / 配额 / 非法 JSON）一律静默降级为默认值，不写 console.error | 个性化失败不得影响列表可用性 |

#### 4.10.2 精确改动

**A. 新文件 `src/composables/useListPreferences.js`**

导出：

| 名称 | 说明 |
|---|---|
| `buildStorageKey(objectType, schemaVersion)` | `meta-ui:list:<type>:<version>` |
| `createDefaultPreferences()` | `{columnOrder:[],hidden:[],width:{},pageSize:null,filters:{panel:{},header:{}}}` |
| `normalizePreferences(raw)` | 清洗：去重字符串数组、丢弃非正数宽度、pageSize 仅接受 1–200 整数、filters 仅保留普通对象 |
| `applyColumnOrder(columns, columnOrder)` | 纯函数，未知列丢弃、新增列追加末尾；空 order 原样返回 |
| `filterHiddenColumns(columns, hidden)` | 纯函数 |
| `resolvePageSize(saved, allowed, fallback)` | 不在 `allowed` 内回退默认 |
| `useListPreferences({objectType, schemaVersion, enabled, storage})` | 返回 `{prefs, storageKey, load, patch, setColumnOrder, setHidden, setWidth, setPageSize, setFilters, reset}` |

**B. `src/components/common/MetaListPage/MetaListPage.vue`**

1. `preferredColumns = applyColumnOrder(filterHiddenColumns(visibleColumns, prefs.hidden), prefs.columnOrder)`；`tableColumns`、`cardPrimaryColumn`、`cardColumns`、`hasBusinessKeyColumn` 改用它。
2. `getColumnWidth` 优先返回 `prefs.width[prop]`。
3. `<el-table @header-dragend="onHeaderDragEnd">` → `setWidth(prop, Math.round(newWidth))`。
4. `watch(storageKey)`：`load()` 后同步 `pagination.pageSize` / `filterValues` / `headerFilterValues`，有变化则 `loadList()`。
5. `watch(pagination.pageSize)` 与 `watch([filterValues, headerFilterValues], deep)` → 持久化。
6. 工具栏右侧（`isPageMode && !hideToolbar`）新增「列设置」`el-popover`：复选显示/隐藏、上下移序、恢复默认。

**C. 新增 `src/composables/__tests__/useListPreferences.spec.js`**

覆盖：键格式 / 非法值清洗 / 列序（未知列丢弃、新增列末尾）/ 隐藏过滤 / pageSize 白名单回退 / 存取往返 / 非法 JSON → null / `schema_version` 变化不串号。

#### 4.10.3 明确不做

- 不写后端、不跨设备同步、不写 URL。
- 不给 `embedded` / `dialog` 做偏好隔离（直接不启用）。
- 不持久化 `keyword`、排序、页码（页码每次回到第 1 页是既有行为）。

#### 4.10.4 验证

1. `npx vitest run src/composables/__tests__/useListPreferences.spec.js`
2. `npx eslint src/composables/useListPreferences.js src/components/common/MetaListPage/MetaListPage.vue src/composables/__tests__/useListPreferences.spec.js`
3. `npx vite build`
4. 冒烟（FE 3006）：任一对象列表 → 列设置隐藏/移序 → 拖列宽 → 改每页条数 → 刷新，均保持；篡改 localStorage 中 `schema_version` 段 → 偏好失效回默认；审计页（embedded）不出现「列设置」。

#### 4.10.5 回滚

- 删除 `useListPreferences.js` 与 MetaListPage 中的接线即可；`localStorage` 残留键无副作用（不被读取）。
- 不影响后端、YAML 与其他页面。

---

### 4.11 命名空间扩展：任意 `/api/*` 走 apiRoot（2026-11-16）

- 背景：`resolveRequest` 原先只识别 `/api/v1`、`/api/v2`，其余一律按 v2 处理；`/api/print/templates` 会被拼成 `/api/v2/api/print/templates`。这是 `print_template` 声明式化的前置缺口①。
- 改动：`src/services/metaResourceService.js` 增加 `API_ROOT_PREFIX = '/api/'` 分支，**保留完整路径**并选用 `apiRoot` 命名空间；v1/v2 分支顺序不变，裸路径回退行为不变。
- 边界：仅解决寻址，不解决复合/派生列（缺口②）与专用编辑器（缺口③-⑤），因此 M2.5 仍不立项。
- 验证：`metaResourceService.dataSource.spec.js` 新增 `/api/print/templates`、`/api/integrations/feeds` 两断言；既有 v1/v2/裸路径断言不变。

---

## 6. 兼容与回滚

- 所有新增键可选；`data_source` 缺省仍为 `null` → 旧 fetcher 路径不变。
- `version: 2` 才启用 `variants`；v1 语义冻结。
- 回滚粒度：单对象 YAML 回滚（git）即可恢复，无需前端发版。
- 运行期降级确保“一个对象配错不白屏”。

---

## 7. 测试计划

| 层 | 内容 | 入口 |
|---|---|---|
| 后端单测 | `test_ui_meta_data_source.py` 扩展：variants 合并、条件透传、warnings、explain | `python d:\filework\test.py --file meta/tests/api/test_ui_meta_data_source.py --force` |
| 新增后端测试 | `test_ui_meta_variants.py`、`test_ui_meta_conditions.py`、`test_lint_ui_config.py` | 同上 |
| 前端单测 | `metaResourceService` 纯函数（条件/合并/策略优先级） | 现有 vitest 流程 |
| E2E | 集成三页回归 + `audit_log` 页（列可见性/导出/详情）+ `task_run`（重试置灰） | PlaywrightCLI，FE 3006 / BE 3010 |
| 静态 | `lint_metamodel.py --ui-config`、`eslint`、`vite build` | — |

---

## 8. 里程碑

| 阶段 | 范围 | 验收 |
|---|---|---|
| **M0 地基** | 4.1 文法 + 4.2 后端 + 4.3 lint + 4.4 前端条件消费（不改任何页面） | 集成三页行为零变化；lint 通过；新增单测绿 |
| **M1 audit_log** | 5.1 | 页面功能与迁移前一致；`auditLogMeta.js` 删除 |
| **M2 task_run** | 5.2（范围修正见 §4.9.3：`handling_unit` / `print_template` 不动，列 M2.5 候选） | task_run 的 `data_source`/`actions` 声明式；轮询/深链/抽屉保留；动作「隐藏→置灰」为唯一预期差异 |
| **M3 个性化 + explain** | 4.5 + 4.10（explain 已由 M0 覆盖，不扩范围） | 列序/隐藏/列宽/每页条数/筛选刷新后保留；`schema_version` 变更自动失效；embedded/dialog 不启用 |

---

## 9. 风险

| 风险 | 对策 |
|---|---|
| 元数据漂移（YAML ≠ 实际字段） | lint R-UI-06 + 启动校验；`explain=1` 定位来源 |
| 渲染器膨胀成“半个框架” | 条件文法封闭；`variants` 只做 patch，不引入表达式 |
| 权限误读（前端隐藏当鉴权） | 明确 `roles` 仅展示层；后端策略为准 |
| 缓存脏（个性化错位） | key 含 `schema_version`，变更即失效 |
| 调试成本 | `meta.warnings` + 来源行号 + 未知项告警 |

---

## 10. 验收 Checklist

- [x] `ui-meta` 新增键不破坏现有三页（回归 E2E 全绿）
- [x] `lint_metamodel.py --ui-config` 覆盖 R-UI-01..08 并有测试
- [x] `audit_log` 列表/筛选/枚举/导出/详情全部由 YAML 驱动，`auditLogMeta.js` 已删
- [x] 未知条件/字段/动作在浏览器控制台有一次性 warning，页面不白屏
- [x] `variants` 切换（`?view=`）生效，未声明对象行为不变
- [x] 个性化在 `schema_version` 变更后自动失效
- [x] 文档回填：plan 文档追加 M0–M3 落地记录
