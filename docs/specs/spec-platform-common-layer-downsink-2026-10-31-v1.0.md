# Spec: 平台通用层下沉（Phase 1）

- 文档版本：v1.2
- 日期：2026-10-31
- 状态：已确认（里程碑 1 后端机制已落地，FR-001/FR-002/FR-003 验收达成）
- 适用范围：`meta/` 后端平台层、`src/` 前端通用层
- 关联文档：`docs/ARCHITECTURE_V3.md`、`docs/ARCHITECTURE_PRINCIPLES.md`、`docs/HANDOVER_PLATFORM_LAYER_ARCHITECTURE.md`

## 1. 背景与目标

### 1.1 背景

`ARCHITECTURE_V3.md` 已明确平台层只提供对象定义、权限、流转、数量账四种能力，业务规则应通过 YAML/对象配置填充，依赖必须单向向下。方向是正确的，但 2026-10-31 的代码核查显示：**平台层的“机制”存在多个入口，边界承诺多数只有声明、没有执行点**。这导致同一规则在不同层重复实现，平台层无法作为单一事实源。

核查基线（只读统计，非估算）：

| 维度 | 现状证据 | 结论 |
|---|---|---|
| 响应契约 | `jsonify(` 1266 处 / 63 文件；使用 `_response_contract` 仅 21 处 / 7 文件（约 1.7%）；`bo_api.py` 单文件 165 处且零导入契约 | 契约存在但未强制 |
| 事务边界 | API 层 `.commit()` 16 处 / 6 文件；service 层 26 处 / 8 文件；core 层 98 处 / 21 文件（含迁移与适配器，不全是违规）；`bo_framework` 自动包裹仅覆盖 9 个动作 | 事务归属不统一 |
| 唯一调度 | `enum_api.py`、`data_permission_api.py`、`schema_api.py`、`unified_permission_api.py`、`intent_api.py`、`filter_variant_api.py` 绕过 `bo_framework` 直接写库 | 存在真实旁路 |
| 审计写入 | 约 23 个写审计函数 / 6 个模块；底层 INSERT 点 2 个（`audit_service.log`、`audit_async_queue:215`）；4 处直调 `AuditLogger` | 入口多、落地单 |
| 鉴权 | `require_permission` 仅 35 处 / 6 文件，`bo_api` 为 0；service 内权限判断 21 处 / 7 文件；拦截器另有一套权限解析 | 三层职责重叠 |
| 查询参数 | 15 个文件手工解析 `page/page_size`；filters/排序有 5 套实现 | 无统一 QuerySpec |
| 前端路由 | `/detail/${...}` 字面量共 8 处 / 5 文件：`MetaListPage` 3、`useNavigation` 2、`detailRouteGuard` 1、`FkLinkField` 1、`ObjectDetailPage` 1 | 配置未覆盖全部路径 |
| 前端枚举 | 已存在 `src/services/enumService.js`（缓存 + TTL），但 `MetaListPage` 未接入，逐列直读 `enum_values/options` | 通用能力未复用 |
| 前端权限 | 至少 5 条判定路径：`useMetaList._checkPermission`、`actionPolicyService`、`AssociationSection` 2 处、`ExportDialog` 硬编码 `${t}:export` | 口径不一 |
| 平台边界 | `table_prefix` 仅声明与校验，无物理改写；`allowed_platform_modules` 有 3 个 app 声明、0 个消费点；应用 migrations 未执行；`requires.column_version` 仅登记 | 声明有、执行无 |

### 1.2 业务目标

- 每个横切机制只有一个入口：响应、事务、审计、鉴权、查询参数。
- 平台边界从“约定”变为“可执行门禁”。
- 迁移过程不改变现有对外成功响应结构，不做大爆炸式重写。
- 每一项都可用静态计数与测试验证，可回滚。

### 1.3 涉众目标

- 平台开发者：新增业务模块时不需要重复实现分页、权限、审计、事务。
- 业务开发者/应用插件作者：只写 YAML 与领域策略，不碰平台机制。
- PM/运维：能通过基线计数判断架构是否退化，而不是靠人工 review。
- 最终用户：行为不变，权限与审计结果一致。

## 2. 需求类型概览

| 类型 | 适用 | 证据来源 |
|---|---|---|
| 业务需求 | 是 | 平台层评审结论、V3 分层定义 |
| 涉众需求 | 是 | 开发者/PM/运维目标 |
| 解决方案需求 | 是 | 本 Spec 第 9 章 RFC |
| 功能需求 | 是 | FR-001 ~ FR-011 |
| 非功能需求 | 是 | NFR-001 ~ NFR-006 |
| 外部接口需求 | 是 | IF-001 ~ IF-003 |
| 过渡需求 | 是 | TR-001 ~ TR-003 |

## 3. 功能需求

### FR-001 响应契约统一

- **描述**：`meta/api/` 下所有 HTTP handler MUST 通过 `_response_contract` 的 `ok / ok_list / error_response` 返回；禁止在 handler 内直接 `jsonify` 业务结果。
- **验收标准**：
  - P0 模块（`bo_api`、`decorators`、`enum_api`、`manage_api`、`task_inbox_api`、`audit_api`）直接 `jsonify` 计数降为 0（契约模块自身除外）。
  - CI 记录 `jsonify(` 基线，之后不得增加；每个里程碑只允许下降。
  - 成功响应 payload 字段不变；错误响应统一为 `{success:false, error_code, message, details}`。
- **落地状态（2026-10-31）**：已完成。P0 六个模块 `jsonify` 计数均为 0；全局计数 1263 → 750。
  无法无损映射到标准助手的既有结构（扁平列表、`_hint`/`_deprecated` 顶层标记、`error` 键、动态状态码）统一经 `_response_contract.json_response(payload, status)` 原样输出，
  该函数是唯一的"非标准 payload 出口"，新增代码不得使用；`error_response` 增加 `errors` 可选参数以保留历史错误结构。
- **优先级**：Must
- **类型映射**：解决方案/功能
- **来源**：代码核查第 3 条

### FR-002 事务边界统一

- **描述**：事务 MUST 由 `bo_framework` 或 `DataSource.transaction()` 统一管理；API 层禁止 `commit/rollback`；service 层仅允许跨聚合批量场景自行开启事务，且必须登记在允许清单。
- **验收标准**：
  - `meta/api/` 下 `.commit()` 计数为 0。
  - service 层自持事务只允许基线 `allowlists.service_commits` 登记的基础设施模块（当前 7 个：审计写入/哈希链/异步写入/重试 worker、权限缓存、令牌黑名单、子流程模板存储），清单之外为 0。
  - 现有回滚路径（异常、校验失败、权限拒绝）全部有测试覆盖。
- **落地状态（2026-10-31）**：已完成。`meta/api/` 16 处 `.commit()` → 0；请求路径上的 service 提交（`enum_type_crud`）改由 `DataSource.transaction()` 包裹；
  其余 23 处均为无请求事务上下文的进程级/基础设施模块，登记在基线白名单并附原因。
- **优先级**：Must
- **类型映射**：功能/非功能（一致性）
- **来源**：代码核查第 2、7 条

### FR-003 `bo_framework` 唯一调度入口

- **描述**：业务对象的 CRUD 与关联操作 MUST 经 `bo_framework`；确实需要绕过的端点（如 schema 管理、权限配置）必须登记为“平台基础设施端点”并说明原因。
- **验收标准**：
  - 当前 6 个绕过文件全部完成迁移或登记，未登记旁路为 0。
  - 路由级覆盖测试能列出每个端点的调度入口。
- **落地状态（2026-10-31）**：已完成登记。6 个文件全部登记为「平台基础设施端点」，写入基线 `allowlists.api_platform_infra` 并附原因：
  `enum_api`（枚举元数据）、`schema_api`（schema DDL）、`unified_permission_api`（权限规则配置）、
  `data_permission_api`（数据权限范围）、`intent_api`（意图定义）、`filter_variant_api`（过滤变体）。
  它们操作的是平台自身元数据/配置，不是业务对象 CRUD，因此不经过 BO 调度链；业务对象 CRUD 仍只走 `bo_framework`。
- **优先级**：Must
- **类型映射**：功能
- **来源**：代码核查第 7 条

### FR-004 审计入口收敛

- **描述**：审计写入 MUST 统一经 `AuditService.log`；异步队列的批量 INSERT 也必须通过同一服务接口，不允许模块直调底层 `AuditLogger` 或自行拼 SQL。
- **验收标准**：
  - 底层 INSERT 点保持 2 个且均归属 audit service/queue。
  - 4 处直调 `AuditLogger` 全部迁移。
  - 写入口从约 23 个收敛到 ≤6 个适配器（配置审计、数据审计、认证审计、流程审计等）。
- **落地状态（2026-10-31）**：已完成。`insert into audit_logs` 直写点保持 2 个（audit_service / 异步队列），
  基线 `audit_insert_outside` 锁定 0；`auth_api`、`user_api`、`user_reset_password` 三处直调 `AuditLogger`
  改为 `AuditService(resolve_audit_data_source(ds)).log(...)`，`_audit_helper.write_permission_config_audit`
  作为唯一保留的权限配置适配器。新增基线指标 `audit_logger_direct` 锁定 1（仅适配器）。
  写入口收敛为 5 个：`AuditService.log`（底层唯一）、`_audit_helper.write_permission_config_audit`（配置）、
  `AuditService.log_permission_decision`（权限决策）、`AuditLogger`（框架调度）、`AuditInterceptor`（自动拦截）。
  认证/用户相关 69 项测试通过（67 passed / 2 skipped）。
- **优先级**：Should
- **类型映射**：功能
- **来源**：代码核查第 1 条

### FR-005 鉴权统一

- **描述**：API 层只声明权限码；权限判定由 core 的 permission gate 统一执行；service 层只允许数据范围/行级过滤，不得再做角色/权限码判断。
- **验收标准**：
  - `bo_api` 端点权限声明覆盖率从 0 提升到 100%（写操作优先）。
  - 变更类端点 `require_permission` 或声明式权限覆盖 100%。
  - service 内角色/权限码判断 21 处收敛为 0；数据范围判断保留。
  - 拦截器与装饰器共用同一权限解析结果，禁止两套解析各查一次。
- **落地状态（2026-10-31）**：已完成。新增 `meta/core/permission_gate.py` 作为唯一权限判定入口
  （`resolve_required_permission` 解析声明式权限码并回退 `object_type:suffix`，`evaluate_code` / `evaluate`
  统一通配判定，`declare_permission` 仅打元数据标记）；`PermissionInterceptor`、`meta/services/auth_middleware.py`
  （`require_permission` / `require_permission_any` / `require_permission_unified` / `is_admin`）、`meta/api/decorators.py`、
  `meta/api/manage_api.py` 全部委托 gate，删除各自实现。同时修复 `meta/api/decorators.require_permission`
  调用不存在方法（`PermissionSyncService.check_user_permission`）导致恒返 403 的缺陷。
  `bo_api` 19 个变更类端点全部加 `@declare_permission`（另 8 个权限配置端点用 `@require_permission`），
  service 层角色/权限码判断 21 → 0（`import_export_service` / `permission_service` / `function_value_help_resolve`
  改为 `is_admin` / `user_has_permission`）；数据范围判断保留。新增基线指标
  `bo_api_write_routes_undeclared` 与 `service_adhoc_permission_checks` 均锁定 0。
  权限相关 259 项测试通过（253 passed / 6 skipped，`test_auth_permission.py` 因 raw SQL 规范跳过）。
- **优先级**：Should（其中 `bo_api` 覆盖为 Must 子项）
- **类型映射**：功能/安全
- **来源**：代码核查第 4 条

### FR-006 查询参数标准化

- **描述**：新增 `meta/core/query_spec.py`，统一解析 `page/page_size/ordering/search/filters`；各 API 不得手工解析。
- **验收标准**：
  - 手工解析 `page/page_size` 的文件数从 15 降到 0。
  - filters/排序实现从 5 套收敛为 1 套。
  - 现有列表接口的分页、排序、过滤语义不变，并有契约测试。
- **落地状态（2026-10-31）**：已完成。新增 `meta/core/query_spec.py`（`parse_query_spec` / `QuerySpec`），统一解析
  `page/page_size/ordering/search/filters`，保留键唯一真源为 `unified_query_protocol.RESERVED_QUERY_KEYS`；
  过滤条件复用 `parse_url_filters`（原 `_parse_url_filters` 转正），不再有第二套实现。
  `meta/api/` 手工解析文件数 18 → 0（基线新增 `manual_pagination_files` 指标并锁定 0）；
  非法分页参数由 `server.create_app` 的 `QuerySpecError` errorhandler 统一返回 400。
  契约测试 `meta/tests/test_query_spec.py`（8 项）通过；受影响模块 305 项测试通过（143 + 37 + 125，含既有跳过项）。
- **优先级**：Should
- **类型映射**：功能
- **来源**：代码核查第 5 条

### FR-007 前端列表详情路由下沉

- **描述**：列表到详情的路由 MUST 由统一 resolver 解析，优先读 `metaConfig.list.detail_path`；FK 跨对象跳转、`useNavigation`、`detailRouteGuard`、`ObjectDetailPage` 的 fallback 也必须走 resolver。
- **验收标准**：
  - `src/` 下 `/detail/${...}` 字面量从 8 处 / 5 文件降到 0（resolver 内部除外）。
  - 已配置 `detail_path` 的对象行为不变。
  - 未配置对象使用 resolver 的默认规则，并有单测。
- **优先级**：Must
- **类型映射**：功能
- **来源**：前端核查第 1 条 + 基线扫描（8 处 / 5 文件）
- **落地状态（2026-10-31）**：已完成。新增 `src/router/detailPathResolver.js`（`resolveDetailBasePath` /
  `resolveDetailPath`），解析顺序为「显式 `detailPath` → `metaService.getViewConfigSync(objectType).data.list.detail_path`
  → 默认 `/detail/<objectType>`」，缓存缺失时安全回退。5 个手工拼接点全部改走 resolver：
  `useNavigation`（行 28 详情跳转、行 119 breadcrumb）、`FkLinkField.vue`（`targetRoute`）、
  `MetaListPage.vue`（FK 跨对象跳转、`navigateToDetailPage`、`navigateToDetailPageForCreate`）、
  `ObjectDetailPage.vue`（保存后跳转）、`detailRouteGuard.js`（breadcrumb）。已配置 `detail_path` 的对象
  仍传入原值，行为不变。`src/` 下手工 `/detail/` + id 拼接点 8 → 0，ratchet `detail_literal` 锁定 0。
  新增 `detailPathResolver.spec.js` 6 项单测（显式路径优先 / 配置路径 / 默认回退 / 缓存缺失 / id 拼接 / 空 id）；
  相关前端测试 122 项通过（6 个文件）。

### FR-008 前端枚举统一接入

- **描述**：`MetaListPage` MUST 通过 `src/services/enumService.js` 获取枚举/字典，不得逐列直读 `column.enum_values/options` 并自行加载。
- **验收标准**：
  - `MetaListPage` 对 `enumService` 的引用存在，直接枚举加载路径为 0。
  - 缓存 TTL 5 分钟、LRU 100 的既有策略保持。
  - 列表筛选与单元格展示使用同一份枚举数据。
- **优先级**：Must
- **类型映射**：功能
- **来源**：前端核查第 3 条
- **落地状态（2026-10-31）**：已完成。`MetaListPage.vue` 引入 `EnumService`，新增
  `columnEnumOptions` / `getColumnEnumValues(column)` / `loadColumnEnums()`：列带 `enum_type` 时按 key 去重、
  异步走 `EnumService.loadOptions(enum_type, { cache: true, throwError: false })`，加载失败静默回退，
  不阻塞渲染。`isBadgeColumn` / `getBadgeTagType` / `getBadgeDisplayValue` 统一改读 `getColumnEnumValues`，
  `columns` 变化（watch）与 `onMounted` 触发加载。无 `enum_type` 的列回退 YAML `enum_values`，
  唯一直读点收敛在 `getColumnEnumValues` 兜底内。筛选侧 `TableHeaderFilter` 原本即走
  `EnumService.loadOptions`，因此筛选与单元格展示共用同一份缓存（TTL 5 分钟 / LRU 100），策略未改。
  测试方面同步修正 `MetaListPage.responsive.spec.js`：新增 `beforeAll`（独立 60s 超时）预热组件模块，
  避免首个用例把整条依赖图约 5–10s 的首次编译计入 5s 用例预算而超时；该文件 14 项全部通过。

### FR-009 前端权限判定单一入口

- **描述**：按钮/操作显隐 MUST 通过统一 `can(action, context)` 判定；禁止页面、组件各自调用 `authStore.hasPermission` 或硬编码权限码。
- **验收标准**：
  - 统一判定入口 1 个，5 条现有路径全部收敛。
  - `ExportDialog` 的 `${t}:export` 硬编码移除，改由 context 提供。
  - 权限码缺失时行为有明确默认值并记录 debug 日志。
- **优先级**：Must
- **类型映射**：功能/安全
- **来源**：前端核查第 4 条
- **落地状态（2026-10-31）**：已完成。在 `src/services/permissionService.js` 新增统一入口
  `can(action, context = {})`，判定顺序为「显式 `context.permission`（字符串或数组，`mode: 'any' | 'all'`）
  → `objectType + action` 派生 `<objectType>:<action>` → 无权限码放行并记 debug 日志」；`authStore` 由调用方注入
  （未注入或为 `null` 时降级放行并记 debug 日志），避免 `permissionService` 静态 import `authStore` 形成循环依赖。
  `action` 原样使用、不做别名归一（`read` 不会隐式变成 `view`）。6 处直调全部收敛：
  `router/index.js`（路由守卫 `requiredPermissions`）、`useMultiObjectPage.js`（`canImport` / `canExport`）、
  `useMetaList.js`（`_checkPermission`，并移除注释中的直调写法）、`useVersionContext.js`（product / version 读取）、
  `ExportDialog.vue`（`availableMultiTypes`，`${t}:export` 硬编码改为 `can('export', { objectType: t, authStore })`）、
  `AssociationSection.vue`（两处 toolbar actions）。
  ratchet `direct_permission_calls` 12 → 0，基线已 `--update` 锁定 0。`permissionService.spec.js` 新增 8 项
  `can` 单测（无权限码 / 无 store 降级 / objectType 派生 / 不做别名归一 / 显式优先 / 数组 any / `mode=all` / 空数组回退）全部通过。

### FR-010 导出配置契约化

- **描述**：`MetaListPage` 的 `exportOptions` prop 目前是死配置（全仓 0 处传入）。MUST 二选一：删除该 prop，或由 `metaConfig`/YAML 明确驱动。
- **验收标准**：
  - 不存在“声明但无调用方”的导出配置。
  - 导出字段来源可追溯到 YAML `listConfig.exportOptions.includeFields`。
- **优先级**：Could
- **类型映射**：功能/清理
- **来源**：前端核查第 2、5 条
- **落地状态（2026-10-31）**：已完成（选「删除该 prop」分支）。删除 `MetaListPage.vue` 中
  `ExportDialog` 的 `:export-options="exportOptions"` 绑定，并移除 props 里 `exportOptions`
  （`{ type: Object, default: () => ({ includeFilters: true }) }`）声明；`ExportDialog` 自身 `exportOptions`
  默认 `{}` 且 `includeFilters = props.exportOptions?.includeFilters !== false`，故实际行为等价（包含筛选条件仍默认开启，
  `showExportOptions` 本就未传入、默认 `false`）。导出字段来源已可追溯到 YAML：
  `useMetaList.js` 读取 `listConfig.exportOptions.includeFields` 组装 `exportFields`，非死配置。

### FR-011 平台边界门禁

- **描述**：`allowed_platform_modules` MUST 在应用加载期被执行：应用导入未授权平台模块时启动失败并给出明确错误；应用 migrations 与 `requires.column_version` 的执行语义在本阶段只登记、不实现。
- **验收标准**：
  - 违规 import 的应用在启动期失败，错误信息包含模块名与 app 名。
  - 现有 3 个声明 `allowed_platform_modules` 的应用不受影响。
  - `table_prefix` 物理改写不在本 Spec 范围，另立 Spec（TBD-1）。
- **优先级**：Should
- **类型映射**：功能/平台治理
- **来源**：代码核查第 6 条
- **落地状态（2026-10-31）**：已完成（加载期静态 AST 门禁，不引入运行时 import hook）。
  - `meta/core/app_loader.py` 新增 `_iter_platform_imports()` / `is_platform_module_allowed()` /
    `validate_platform_imports()`：扫描 `app_dir/**/*.py`，只拦 `meta` / `meta.*`，白名单精确或前缀
    （`entry + "."`）匹配，同一 import 语句的多个候选名任一命中即通过；违规错误含 app 名、
    `相对路径:行号`、模块名与已申明白名单。
  - `meta/core/app_registry.py` 在 `register_apps()` 的 `_verify_dependencies()` 之后调用
    `_verify_platform_imports()`，违规转 `AppRegistrationError("平台模块 import 门禁失败: ...")`
    ⇒ 启动中止。
  - `apps/tms/app.yaml` 补齐真实依赖 `meta.core.action_executor`、`meta.core.models`
    （此前未声明，门禁开启会误杀）；`hello_world` / `warehouse` / `tms` 三个应用与
    `register_apps` 回归全部通过。
  - 已知边界：静态扫描不覆盖 `importlib` / `__import__` 动态加载（在 docstring 写明）；
    `requires.column_version` 与 migrations 执行语义按本 Spec 仍只登记、不实现。

## 4. 非功能需求

### NFR-001 行为兼容

- **描述**：除错误响应统一外，现有成功响应 JSON 结构与字段名不得变化。
- **度量**：迁移模块的契约测试对比迁移前后响应快照，差异为 0。
- **优先级**：Must

### NFR-002 性能

- **描述**：统一入口带来的额外开销可控；权限判定不得新增每请求数据库查询。
- **度量**：p95 额外延迟 ≤5ms；权限解析命中缓存；压测对比基线。
- **优先级**：Must

### NFR-003 可观测

- **描述**：审计记录必须包含 `trace_id`、用户、动作、对象、before/after（可用时）。
- **度量**：抽样审计记录字段完整率 100%。
- **优先级**：Should

### NFR-004 可测试

- **描述**：每个统一入口必须有单元测试与至少一条集成测试；测试只经 `python d:\filework\test.py`。
- **度量**：新增测试全部纳入 `test.py`，禁止直接 pytest。
- **优先级**：Must

### NFR-005 可回滚

- **描述**：统一入口通过环境变量开关控制严格模式，默认先 shadow 后强制。
- **度量**：`PLATFORM_STRICT_CONTRACT`、`PLATFORM_TX_GUARD`、`PLATFORM_PERMISSION_GATE` 可独立关闭。
- **优先级**：Must
- **落地状态（2026-10-31）**：已完成。新增 `meta/core/platform_flags.py`：三态
  `strict` / `shadow` / `off`，三个开关各自读取环境变量（调用时读取，非法值记 warning 后回默认），互不影响。
  - 接入点：`meta/api/_response_contract.py`（`json_response()` 与 `ok(list)`）、
    `meta/core/bo_framework.py`（`_check_write_tx_scope()`）、`meta/core/permission_gate.py`
    （`_apply_gate_mode()` 覆盖 `evaluate()` / `evaluate_code()`）。
  - **默认值偏离本需求原文「默认先 shadow 后强制」**：`PLATFORM_STRICT_CONTRACT` = shadow、
    `PLATFORM_TX_GUARD` = shadow，但 `PLATFORM_PERMISSION_GATE` = strict。理由：鉴权已是现行行为，
    默认 shadow 会在本应拒绝时放行（fail-open），违反 NFR-001 行为兼容；该开关的用途是回滚，
    仅在显式设为 `shadow` / `off` 时才放行。
  - 验证：`meta/tests/test_platform_boundary.py` 23 项全部通过（经 `python d:\filework\test.py`）。

### NFR-006 架构基线与门禁

- **描述**：建立可提交的架构基线文件，CI 对 `jsonify`、`commit`、权限判断、`/detail/` 字面量等计数做 ratchet。
- **度量**：基线文件纳入版本管理；计数上涨即失败。
- **优先级**：Must

## 5. 外部接口需求

### IF-001 HTTP 响应契约

- **类型**：API
- **入口**：`meta/api/` 全部路由
- **成功响应**：保持现有 payload；列表继续返回既有分页字段。
- **错误响应**：`{success:false, error_code, message, details?}`；HTTP 状态码沿用现有映射。
- **错误处理**：契约层统一捕获未预期异常，记录 trace_id 并返回 500，不泄露堆栈。
- **来源**：FR-001

### IF-002 前端配置契约

- **类型**：UI/配置
- **入口**：`metaConfig.list.detail_path`、`permission.can(action, context)`
- **交互**：列表行点击/FK 跳转读取 `detail_path`；按钮显隐读取 `can()` 结果。
- **错误处理**：配置缺失时使用默认路由与默认拒绝，并记录 debug 日志。
- **来源**：FR-007、FR-009

### IF-003 审计日志结构

- **类型**：系统集成/数据
- **入口**：`AuditService.log`
- **字段**：`trace_id`、`user_id`、`action`、`object_type`、`object_id`、`before`、`after`、`source`、`created_at`
- **错误处理**：审计失败不得阻断主事务；异步队列失败进入重试与告警。
- **来源**：FR-004

## 6. 过渡需求

### TR-001 架构基线 ratchet

- **描述**：新增 `docs/governance/arch-baseline-2026-10-31.json` 与 `scripts/check_architecture.py`，记录并校验计数。
- **策略**：先落基线（只读），再逐模块下降；CI 只允许计数下降。
- **回滚**：删除基线检查或降低阈值，不影响运行时。
- **来源**：NFR-006

### TR-002 模块级渐进迁移

- **描述**：按 P0 模块列表逐个迁移，每个模块独立提交、独立回滚。
- **策略**：契约测试先行的“双跑”模式；新旧返回并比，差异为 0 后再切换。
- **回滚**：按模块 git revert；环境开关可关闭严格模式。
- **来源**：FR-001 ~ FR-009

### TR-003 无数据库结构变更

- **描述**：本 Spec 不引入表结构变更，不需要迁移版本号。
- **策略**：`table_prefix` 物理改写另立 Spec；本阶段只做代码与配置。
- **回滚**：无 DB 回滚需求。
- **来源**：FR-011、TBD-1

## 7. 约束与假设

### 7.1 技术约束

- Python 3.11 + Flask + Waitress + SQLite；前端 Vue 3 + TS + Element Plus + Pinia。
- 禁止绕过 `test.py` 直接 pytest；测试入口唯一。
- 禁止直读写 `meta/architecture.db`；DB 操作走既有服务/事务。
- 平台层不得 import `apps/`；依赖方向只允许向下。

### 7.2 业务约束

- 不改变现有对外成功响应结构，避免前端与外部调用方返工。
- 权限收紧必须有 shadow 期，避免误锁用户。
- 不在本阶段实现应用 migrations 与 `table_prefix` 物理改写。

### 7.3 假设

- 假设 1：`jsonify` 的 1266 处中，多数可按模块机械迁移到契约函数 —— 来源：代码抽查（待逐模块确认）。
- 假设 2：`enumService` 的缓存策略可满足列表页枚举需求 —— 来源：现有实现。
- 假设 3：前端 `useMetaList` 的 5 条权限路径可收敛到单一 evaluator —— 来源：代码核查（待补单测）。
- 假设 4：平台基础设施端点（schema/permission 管理）允许登记旁路 —— 来源：架构评审结论（待确认，见 TBD-3）。

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|---|---|---|---|
| FR-001 | 响应契约统一 | Must | 1.7% 落地率，外部契约风险最高 |
| FR-002 | 事务边界统一 | Must | API/service 双路径提交，数据一致性风险 |
| FR-003 | bo_framework 唯一调度 | Must | 6 个真实旁路，平台机制被绕过 |
| FR-007 | 前端详情路由下沉 | Must | 两处硬编码绕过配置 |
| FR-008 | 前端枚举统一 | Must | 已有服务未复用，列表/详情口径不一 |
| FR-009 | 前端权限单一入口 | Must | 5 条路径，含硬编码权限码 |
| FR-004 | 审计入口收敛 | Should | 入口多但底层已单一，先收敛再升级 |
| FR-005 | 鉴权统一 | Should | 拦截器已兜底，`bo_api` 覆盖为 Must 子项 |
| FR-006 | 查询参数标准化 | Should | 15 文件手工解析，收益明确但影响面广 |
| FR-011 | 平台边界门禁 | Should | 声明有、执行无，先做 import 门禁 |
| FR-010 | 导出配置契约化 | Could | 死配置，清理即可 |

- 里程碑 1（后端机制）：FR-001、FR-002、FR-003 + 基线工具。
- 里程碑 2（权限与审计）：FR-004、FR-005、FR-006。
- 里程碑 3（前端通用层）：FR-007、FR-008、FR-009、FR-010。
- 里程碑 4（平台治理）：FR-011；`table_prefix` 另立 Spec。

## 9. 变更/设计方案（RFC）

### 9.1 As-Is 分析

- **当前架构**：`api/` → `services/` → `core/`；`bo_framework` 提供 CRUD、事务、拦截器链；`MetaListPage + useMetaList` 提供前端列表通用能力。
- **核心问题**：
  1. 机制多入口：响应、事务、审计、鉴权、查询参数均存在 2 套以上实现。
  2. 边界无执行：`table_prefix`、`allowed_platform_modules`、app migrations 只有声明。
  3. 通用层未命名：`core` 同时承担内核与工具箱，缺少显式“通用能力层”边界。
  4. 前端通用层只覆盖列表，详情路由、枚举、权限仍分散。
- **相关代码路径**：
  - `meta/api/_response_contract.py`、`meta/api/_audit_helper.py`、`meta/api/decorators.py`
  - `meta/core/bo_framework.py`、`meta/core/interceptors/`、`meta/core/query_builder.py`
  - `meta/services/audit_interceptor.py`、`meta/services/audit_service.py`
  - `src/components/common/MetaListPage/MetaListPage.vue`、`src/composables/useMetaList/`
  - `src/services/enumService.js`、`src/services/permissionService.js`

### 9.2 目标状态

- **显式通用能力层**：在 `core` 下按能力划分，不新增第四层目录，但明确“内核 / 通用能力 / 基础设施”三类归属：
  - 内核：`bo_framework`、`query_builder`、拦截器编排、事务。
  - 通用能力：响应契约、QuerySpec、权限 gate、审计服务、枚举服务接口。
  - 基础设施：迁移、适配器、异步队列。
- **关键变化**：
  1. `_response_contract` 成为唯一响应出口。
  2. `bo_framework` 成为唯一业务调度与事务入口；旁路登记制。
  3. `AuditService.log` 成为唯一审计写入口。
  4. permission gate 统一解析一次，API 只声明权限码。
  5. 前端三件事下沉：routeResolver、enumService、permission.can。

### 9.3 详细设计

| 组件 | 位置 | 职责 | 依赖 |
|---|---|---|---|
| ResponseContract | `meta/api/_response_contract.py`（保留） | 成功/错误/列表/分页统一序列化 | 无 |
| QuerySpec | `meta/core/query_spec.py`（新增） | 解析分页/排序/搜索/过滤，输出稳定结构 | 无 |
| PermissionGate | `meta/core/permission_gate.py`（新增编排层） | 合并装饰器声明、动作权限、数据权限，单次解析 | 既有 3 个拦截器 |
| AuditService | `meta/services/audit_service.py`（保留并收口） | 唯一审计写入口；异步队列委托 | DB/queue |
| TransactionOwner | `meta/core/bo_framework.py`（强化） | 统一开启/提交/回滚；API 禁止提交 | DataSource |
| ArchBaseline | `scripts/check_architecture.py`（新增） | 统计并 ratchet 关键计数 | CI |
| RouteResolver | `src/services/routeResolver.js`（新增） | `detail_path` + 默认规则 + FK 跳转 | metaConfig |
| EnumService | `src/services/enumService.js`（复用） | 枚举缓存与加载 | API |
| PermissionEvaluator | `src/services/permissionService.js`（扩展 `can`） | 统一按钮/操作判定 | authStore |

**主要流程（写操作）**：

1. API handler 解析请求 → 调用 `bo_framework.run_action`。
2. `bo_framework` 开启事务 → PermissionGate 单次判定（声明码 + 动作 + 数据范围）。
3. 业务执行 → AuditService 记录 before/after（异步队列）。
4. 统一提交；异常统一回滚 → ResponseContract 输出。

**错误处理**：

- 权限拒绝：403 + `error_code=PERMISSION_DENIED`，不泄露对象细节。
- 校验失败：422 + 字段级 details。
- 未预期异常：500 + trace_id，审计记录失败原因。

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A 大爆炸重写全部 API | 一次到位 | 风险高、无法逐模块回滚 | 否决 |
| B 基线 ratchet + 模块渐进迁移 | 可回滚、可度量、兼容现有行为 | 周期长、需要双跑测试 | **采用** |
| C 只写规范不落地 | 成本最低 | 计数继续上涨，问题不解决 | 否决 |

### 9.5 实施与迁移计划

- **实施顺序**：
  1. 落架构基线与检查脚本（只读，不改变行为）。
  2. 后端里程碑 1：响应契约 + 事务边界 + 6 个旁路迁移/登记。
  3. 后端里程碑 2：审计收口 + 权限 gate + QuerySpec。
  4. 前端里程碑 3：routeResolver、enumService 接入、permission.can。
  5. 里程碑 4：`allowed_platform_modules` import 门禁。
- **风险与缓解**：
  - 响应结构变化 → 契约快照测试 + 成功 payload 不变 + 开关回退。
  - 事务 guard 误伤长事务 → 允许清单 + shadow 模式。
  - 权限收紧误锁 → 先 shadow 比对，再强制。
  - 前端枚举缓存不一致 → 统一 TTL + 失效钩子。
- **测试策略**：
  - 单元：`test_response_contract.py`、`test_transaction_boundary.py`、`test_audit_single_writer.py`、`test_permission_gate.py`、`test_query_spec.py`。
  - 集成：API 契约快照、审计记录字段、权限 403/200 路径。
  - 前端：routeResolver、enumService 缓存、permission.can 的 Vitest。
  - E2E：列表 → 详情跳转、权限按钮显隐、导出。
- **回滚方案**：
  - 代码按模块 revert。
  - 运行时开关 `PLATFORM_STRICT_CONTRACT`、`PLATFORM_TX_GUARD`、`PLATFORM_PERMISSION_GATE` 关闭严格模式。
  - 本阶段无 DB 变更，无数据回滚。

## 10. TBD 清单与决议

| ID | 事项 | 决议 | 触发/后续 |
|---|---|---|---|
| TBD-1 | `table_prefix` 物理改写 | **推迟物理改写**（与 v1.27 决策一致），升级为运行时门禁：同一 DB 被 ≥2 个 app 共享时告警 | 触发条件：多应用共享 DB、表名冲突、按应用隔离审计；触发后另立 Spec |
| TBD-2 | 响应契约迁移范围 | **Tier 1/2/3 + ratchet**：Tier 1 为 8 个核心 CRUD 文件；Tier 3 冻结并登记；基线 1266 只降不升。**落地状态（2026-10-31）**：已完成主体迁移，全局 750 → **371（≤400 已达成）**；Tier 1 六个模块清零，剩余 2 个文件 18 处为非标准结构已冻结；Tier 2 两批 26 个文件迁移完成；基线同步下调，详见 §10.1 | Tier 1 清零后全局目标 ≤400；文件流响应先分类再迁移 |
| TBD-3 | 权限双保险 | **两层保留、单次判定**：装饰器声明权限码并快速失败，core gate 单次解析，service 只做数据范围 | 验收：单请求权限解析次数 = 1；403 结构统一 |
| TBD-4 | 审计异步队列直 INSERT | **允许批量 INSERT，仅限审计模块内部**；业务调用方统一走 `AuditService.log` | CI 检查：审计模块外 `INSERT INTO audit_logs` = 0 |
| TBD-5 | 前端权限 evaluator 归属 | **`permissionService` 提供纯函数 `can(action, context, permissions)`**；`useMetaList` 只编排 | 组件层统一调用 `can()`；禁止页面直调 `authStore.hasPermission` |
| TBD-6 | 应用 migrations / `column_version` | **本阶段不实现，登记 P2**；先定义 schema hash 契约，再定执行语义 | 触发条件：首个自带 schema 的应用上线或应用升级需数据迁移 |

### 10.1 TBD-2 执行清单（2026-10-31 实测）

计数口径：`meta/api/*.py`（不含 `_response_contract.py`）中 `jsonify(` 出现次数，由 `scripts/check_architecture.py` 统计。

**执行结果：1266 → 750 → 371**（Tier 1 剩余 + Tier 2 共 26 个文件迁移），全局 ≤400 目标已达成；基线文件同步下调为 371。

**Tier 1（8 个核心 CRUD 文件）**

| 文件 | 迁移前 | 迁移后 | 状态 |
|---|---|---|---|
| `meta/api/bo_api.py` | 0 | 0 | ✅ |
| `meta/api/manage_api.py` | 0 | 0 | ✅ |
| `meta/api/audit_api.py` | 0 | 0 | ✅ |
| `meta/api/task_inbox_api.py` | 0 | 0 | ✅ |
| `meta/api/enum_api.py` | 0 | 0 | ✅ |
| `meta/api/decorators.py` | 0 | 0 | ✅ |
| `meta/api/bo_action_api.py` | 8 | 8 | 冻结（6 处 `make_response(jsonify(...))`/变量 payload + 2 处变量 `success`；改 helper 会变结构） |
| `meta/api/association_api.py` | 14 | 10 | 迁移 4 处；其余 payload 为变量或带额外顶层字段，冻结 |

**Tier 2（12 个高计数文件）**

| 文件 | 迁移前 | 迁移后 |
|---|---|---|
| `meta/api/notification_api.py` | 42 | 3 |
| `meta/api/export_import_api.py` | 38 | 11 |
| `meta/api/permission_rule_api.py` | 37 | 7 |
| `meta/api/unified_permission_api.py` | 37 | 2 |
| `meta/api/stats_api.py` | 36 | 8 |
| `meta/api/permission_dimension_api.py` | 35 | 3 |
| `meta/api/meta_api.py` | 30 | 23 |
| `meta/api/schema_api.py` | 29 | 13 |
| `meta/api/menu_permission_api.py` | 25 | 15 |
| `meta/api/permission_bundle_api.py` | 25 | 17 |
| `meta/api/database_api.py` | 22 | 22（全部无 `success` 包装，冻结） |
| `meta/api/value_help_api.py` | 20 | 14 |

**第二批（为达成 ≤400 追加的 15 个文件）**

| 文件 | 迁移前 → 迁移后 | 文件 | 迁移前 → 迁移后 |
|---|---|---|---|
| `data_permission_api.py` | 18 → 3 | `owner_transfer_api.py` | 13 → 1 |
| `intent_api.py` | 18 → 14 | `permission_sync_api.py` | 13 → 5 |
| `filter_variant_api.py` | 14 → 1 | `permission_set_menu_api.py` | 12 → 5 |
| `auth_api.py` | 16 → 4 | `m8_api.py` | 11 → 11（冻结） |
| `annotation_routes_api.py` | 16 → 4 | `user_group_api.py` | 10 → 10（冻结） |
| `object_identity_api.py` | 15 → 0 | `key_template_api.py` | 10 → 2 |
| `permission_set_dimension_scope_api.py` | 14 → 3 | | |
| `permission_audit_api.py` | 14 → 7 | | |
| `db_admin_api.py` | 14 → 1 | | |

**冻结原因（剩余的合法 `jsonify`，不得新增）**

1. payload 本身是扁平列表（非 `items/total/page/page_size` 四键，`ok_list` 会改变结构）。
2. 含 `error` 键的错误体（`error_response` 无对应字段，映射会丢 `error`）。
3. 额外顶层字段（`_deprecated`、`has_more`、`where_sql`、`warnings`、`skipped_types` 等）。
4. payload 是变量或 `make_response(jsonify(...))` 链（如设置 cookie 的登录/登出）。
5. `success` 由运行时变量决定（如 `result.success`）。
6. 无 `success` 包装的历史结构（`database_api.py` 的 `{"data": ...}` / `{"error": ...}`）。

**Tier 3（冻结登记，不迁移；不得新增）**

`_response_contract.py`（契约自身）、`_problem_details.py`、`_messages.py`、`_deprecation.py`、`API_TEMPLATE.py`、`meta/graphql/__init__.py`、`meta/ops_server.py`、`meta/server.py`、`meta/core/app_builder.py`、`meta/core/auth_helpers.py`、`meta/core/interceptors/*`。

**迁移规则（结构不变优先）**

1. `{'success': True, 'data': X}` → `ok(X)`；带 `message` → `ok(X, message=M)`。
2. `{'success': True, 'message': M}` → `ok_message(M)`。
3. `{'success': False, 'message': M}` → `error_response(M, status=S)`。
4. `{'success': False, 'message': M, 'code': C}` → `error_response(M, code=C, status=S)`（新增 `error_code` 为契约允许的附加字段）。
5. 无法无损映射的结构 → **保持原 `jsonify` 不动**（不使用 `json_response` 兜底）。
6. 状态码通过返回值元组或 `status=` 原样保留；不得改变控制流。

**验证（2026-10-31）**

- `python scripts/check_architecture.py`：`jsonify_total=371`，其余 9 项计数不变，ratchet PASS。
- `python d:\filework\test.py --file ...`（覆盖 25 个迁移文件的 API 测试）：两批共 331 passed；失败项均为**预先存在**的 v1 端点 410 下线断言（`@v1_deprecated` / legacy 注册表）与 `PermissionRuleV2DAO` 列缺失（`role_id`/`permission_set_id`），与本次响应迁移无关。
- 所有改动文件 `python -m compileall` 通过。
