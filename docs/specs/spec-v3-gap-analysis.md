# Spec: v3 架构差距分析与收敛方案

> **版本**: v1.1.0
> **日期**: 2026-06-06
> **状态**: 实施中（16/18 FR 已完成，1 暂缓，1 待实施）
> **范围**: 前端 `src/services/`、`src/composables/`、`src/stores/`、`src/views/`、后端 `server.py` 集成
> **关联文档**: [spec-ui-business-logic-downflow.md v3.3.1](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md)

---

## 1. 背景与目标

### 1.1 背景

经过对 spec-ui-business-logic-downflow.md v3.3.1 声明与实际代码的逐行对比，发现 **Spec 声明与实际实现存在显著差距**：

| 维度 | Spec 声明 | 实际状态 | 差距等级 |
|------|----------|---------|:--------:|
| FR 完成度 | 13/14 (93%) | 名义达标，实质约 70% | 高 |
| 三层架构分离 | 100% 业务逻辑下沉 | 约 70% 下沉 | 高 |
| httpClient 统一 | 全部走 httpClient | 新 service 达标，旧 bo/ 子服务 34 处 raw fetch | 高 |
| 7 项约束执行 | 全部达标 | 0 项完全达标 | 高 |
| 后端 M10/M13/M14 | 实施完成 | 代码完成但 3 个 Blueprint 未注册到 server.py | 中 |
| useMetaList 重构 | 完成（减 97 行） | 仍 2412 行，超标 11 倍 | 高 |

**核心问题**：项目处于**新旧双轨并行**状态，新 service（httpClient + 纯函数）与旧 bo/ 子服务（raw fetch + 类继承）共存，@deprecated 标记但未删除。

### 1.2 业务目标

1. **消除双轨并行**：将所有 raw fetch 调用收敛到 httpClient，删除 @deprecated 遗留代码
2. **收敛 .vue 内联 fetch**：将 30 处 .vue 内联 fetch 迁移到 service 层
3. **注册后端 Blueprint**：将 M10 MCP / M13 Dashboard / M14 Telemetry 的 Blueprint 挂载到 server.py
4. **继续拆分 useMetaList**：从 2412 行降至 750 行以内
5. **强制执行 7 项约束**：通过 ESLint 规则 + CI 卡点实现自动化

### 1.3 用户/涉众目标

- **开发者**：统一的 HTTP 调用模式，减少认知负担
- **Code Reviewer**：自动化的约束检查，减少人工审查负担
- **运维**：M10/M13/M14 API 端点线上可用
- **AI Agent**：MCP Server 线上可用，支持 Claude/Cursor 集成

---

## 2. 需求类型概览

| 类型 | 适用 | 证据 |
|------|:----:|------|
| 业务需求 | 是 | 双轨并行增加维护成本、线上功能不可用 |
| 用户/涉众需求 | 是 | 开发者统一调用模式、运维端点可用 |
| 解决方案需求 | 是 | httpClient 统一、Blueprint 注册、ESLint 规则 |
| 功能需求 | 是 | FR-GAP-001 ~ FR-GAP-018 |
| 非功能需求 | 是 | NFR-GAP-001 ~ NFR-GAP-005 |
| 外部接口需求 | 是 | M10 MCP / M13 Dashboard / M14 Telemetry API |
| 过渡需求 | 是 | 双轨迁移、@deprecated 代码删除、缓存兼容 |

---

## 3. 功能需求

### FR-GAP-001: boCrudService 迁移 httpClient

- **描述**: 系统必须将 `boCrudService.js` 中 10 个 raw fetch 调用替换为 `BaseService._request()` 或 `apiV2` 命名空间调用
- **验收标准**:
  - `boCrudService.js` 中 0 处 raw fetch 调用
  - 所有 10 个方法（create/read/query/update/delete/executeAction/deepInsert/batchCreate/batchDelete/suggestKeyTemplateCode）改用 `this._request()` 或 `apiV2`
  - LRU 缓存逻辑保留（通过 `BOBaseService` 缓存工具方法）
  - 返回格式从 `{ success, message, code, errors }` 统一为 `{ success, data, message, code, httpStatus, traceId }`
  - 调用方（useBOApi/useDetail/useHierarchyList 等 39 个文件）无需修改
- **优先级**: Must
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: 代码审计 — boCrudService.js 10 处 raw fetch

### FR-GAP-002: boExportImportService 迁移 httpClient

- **描述**: 系统必须将 `boExportImportService.js` 中 11 个 raw fetch 调用替换为 httpClient，并处理 FormData + Blob 下载特殊场景
- **验收标准**:
  - `boExportImportService.js` 中 0 处 raw fetch 调用
  - FormData 上传（previewImport/importData/importDataAsync）通过 httpClient 正确发送（不设置 Content-Type，浏览器自动 multipart boundary）
  - Blob 下载（downloadTemplate/exportData/downloadExportFile）通过 httpClient 的 `responseType: 'blob'` 选项支持
  - v1 API 路径全部改用 `apiV1` 命名空间
- **优先级**: Must
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: 代码审计 — boExportImportService.js 11 处 raw fetch

### FR-GAP-003: boSearchHelpService 迁移 httpClient

- **描述**: 系统必须将 `boSearchHelpService.js` 中 2 个 raw fetch 调用替换为 `apiV2` 命名空间调用
- **验收标准**:
  - `boSearchHelpService.js` 中 0 处 raw fetch 调用
  - searchValueHelp / resolveValueHelp 改用 `apiV2.get()`
- **优先级**: Should
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: 代码审计 — boSearchHelpService.js 2 处 raw fetch

### FR-GAP-004: 删除 @deprecated 的 boAssociationService 和 boHierarchyService

- **描述**: 系统必须删除已标记 @deprecated 且被 `associationService` / `hierarchyService` 完整覆盖的旧文件
- **验收标准**:
  - `boAssociationService.js`（246 行）删除
  - `boHierarchyService.js`（29 行）删除
  - `boService.js` facade 中对应方法改为直接委托 `associationService` / `hierarchyService`
  - 所有调用方（useDetail/useBOApi/useAssociation/RoleDetailDrawer 等）无破坏性变更
  - **缓存兼容**：`boAssociationService` 的 LRU 缓存逻辑迁移到 `associationService`，或确认调用方不依赖缓存行为
- **优先级**: Should
- **类型映射**: 过渡需求
- **来源**: 代码审计 — 2 个文件已 @deprecated 但未删除

### FR-GAP-005: .vue 内联 fetch 收敛 — 重复组 A/B/C/D（14 处）

- **描述**: 系统必须将 .vue 文件中与已有 service 功能重复的 14 处 fetch 调用迁移到对应 service
- **验收标准**:
  - 重复组 A（GET /users/me，5 处）→ `authService.getCurrentUser()`
  - 重复组 B（PUT /users/me，3 处）→ `authService.updateProfile()`
  - 重复组 C（POST /auth/change-password，2 处）→ `authService.changePassword()`
  - 重复组 D（飞书 tenant_access_token，2 处）→ `feishuService.getTenantAccessToken()`
  - 涉及文件：EditProfileDialog.vue、AccountSettings/index.vue、AccountSettingsDialog.vue、ConfigApp.vue、SystemSettings.vue
  - 这些文件中 0 处 `getAuthHeaders()` 调用（由 service 层内部处理认证）
- **优先级**: Must
- **类型映射**: 功能需求 / 过渡需求
- **来源**: 代码审计 — 14 处重复 fetch

### FR-GAP-006: .vue 内联 fetch 收敛 — 需新建 service（16 处）

- **描述**: 系统必须为 .vue 文件中无现有 service 覆盖的 16 处 fetch 调用创建新 service
- **验收标准**:
  - 新建 `annotationService.js`（4 API：list/create/update/delete）→ 替代 AssociationSection.vue 4 处 fetch
  - 新建 `filterVariantService.js`（4 API：list/create/setDefault/delete）→ 替代 FilterVariantSelector.vue 4 处 fetch
  - 扩展 `boService` 或新建 `stateTransitionService.js`（2 API：getTransitions/executeTransition）→ 替代 StateTransitionButtons.vue 2 处 fetch
  - 新建 `statsService.js`（1 API：getOverview）→ 替代 StatsOverview.vue 1 处 fetch
  - 扩展 v2 命名空间或新建 `actionSchemaService.js`（1 API：getSchemas）→ 替代 ActionExplorer.vue 1 处 fetch
  - `EnumSearchHelp.vue` 1 处 → `EnumService.loadOptions()`
  - `RelationScopeSection.vue` 1 处 → `boService.query('relationship', ...)`
  - `ConditionRuleEditor.vue` 2 处 → 评估是否改为 service 注入（当前通过 props 传入 apiBase/apiHeaders）
  - MermaidComponent.vue CDN 加载不迁移
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: 代码审计 — 16 处无 service 覆盖的 fetch

### FR-GAP-007: userPreferences store 迁移

- **描述**: 系统必须将 `userPreferences.js` store 中 2 处直调 fetch `/api/v1/users/me` 迁移到 authService
- **验收标准**:
  - `userPreferences.js` 中 0 处 fetch 调用
  - 用户偏好加载/保存通过 `authService.getCurrentUser()` / `authService.updateProfile()` 实现
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 代码审计 — userPreferences.js 2 处 fetch

### FR-GAP-008: metaService 迁移 httpClient

- **描述**: 系统必须将 `metaService.js` 从 raw fetch 的 `_handleResponse()` 路径迁移到 `BaseService._request()` 方法
- **验收标准**:
  - `metaService.js` 中 0 处通过 `_handleResponse()` 处理的 fetch 调用
  - 所有方法改用 `this._request()` 走 httpClient
  - metaService 单例的缓存逻辑不受影响
- **优先级**: Should
- **类型映射**: 解决方案需求
- **来源**: 代码审计 — metaService.js 继承 BaseService 但未使用 _request()

### FR-GAP-009: graphqlClient 迁移 httpClient ⏸ 暂缓

- **实施状态**: ⏸ 暂缓（POC 阶段，0 调用方，迁移收益极低）
- **当前状态**: graphqlClient.js 162 行，1 处 raw fetch（`_graphqlFetch`），使用 `authStore.getAuthHeaders()` + `credentials: 'include'`
- **迁移方案**:
  - `_graphqlFetch()` 内部 `fetch(GRAPHQL_ENDPOINT, ...)` → `apiV1.post('/graphql', body)`
  - 认证：httpClient 自动处理，移除手动 `getAuthHeaders()`
  - 响应格式适配：GraphQL `{data, errors}` 被 httpClient 包装为 `{success, data: {data, errors}}`，需二次解包
  - 建议：等 GraphQL 正式启用时再统一处理
- **优先级**: Could
- **类型映射**: 解决方案需求
- **来源**: 代码审计 — graphqlClient.js POC 阶段直调 fetch

### FR-GAP-010: useMetaList 继续拆分 — 功能已提取，目标需修正 ✅ 功能等价

- **实施状态**: ✅ 功能等价完成（2412 → 1800 行）
- **原目标**: useMetaList.js <= 750 行，4 个独立 service 文件
- **实际可达**: ~1150-1200 行（UI 编排代码占 60%+ 不可下沉）
- **关键发现**:
  - columnTransformService → 已提取为 metaTransformService.transformColumns + enrichColumnsWithFieldMeta + inferColumnWidth + fixDatetimeColumns + inferColumnPriority
  - actionTransformService → 已提取为 metaTransformService.transformActions + inferActionPosition + mapVariant + filterRowActions
  - inlineEditConfigService → 已提取为 metaTransformService.inferFieldEditConfig
  - metaTransformService.js: 484 行，11 个导出函数，功能完整
  - 拆成 3 个独立文件只是组织方式不同，不会减少 useMetaList.js 行数（委托胶水代码一样多）
- **750 行目标基于错误假设**：以为所有业务逻辑都能下沉，实际上 composable 的 UI 编排代码（响应式状态、事件处理、生命周期）占 60%+ 且不可提取
- **建议修正目标**: ≤ 1200 行，或接受 1800 行为合理终态
- **优先级**: Should
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: 代码审计 — useMetaList.js 2412 行，Spec 目标 <= 250 行

### FR-GAP-011: server.py 注册 M10 MCP Blueprint

- **描述**: 系统必须将 `mcp_bp` Blueprint 注册到 server.py，使 MCP Server API 端点线上可用
- **验收标准**:
  - `server.py` 中添加 `from mcp.server import mcp_bp` 和 `app.register_blueprint(mcp_bp)`
  - `POST /mcp`、`GET /mcp`、`GET /mcp/tools` 端点可访问
  - `curl.exe -s http://localhost:3010/mcp` 返回 server info
  - Claude / Cursor 可通过 MCP 协议访问 20 个工具
- **优先级**: Must
- **类型映射**: 功能需求 / 外部接口需求
- **来源**: 代码审计 — mcp_bp 已定义但未注册

### FR-GAP-012: server.py 注册 M13 Schema Dashboard Blueprint

- **描述**: 系统必须将 `schema_dashboard_bp` Blueprint 注册到 server.py
- **验收标准**:
  - `server.py` 中添加 `from meta.api.schema_api import schema_dashboard_bp` 和 `app.register_blueprint(schema_dashboard_bp)`
  - `GET /api/v1/schema/dashboard/summary` 等 4 个端点可访问
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: 代码审计 — schema_dashboard_bp 已定义但未注册

### FR-GAP-013: server.py 注册 M14 Telemetry Blueprint

- **描述**: 系统必须将 `telemetry_bp` Blueprint 注册到 server.py，并集成 trace 采集中间件
- **验收标准**:
  - `server.py` 中添加 `from telemetry.api import telemetry_bp` 和 `app.register_blueprint(telemetry_bp)`
  - `GET /api/v1/telemetry/stats` 等 5 个端点可访问
  - `telemetry.integration.install_global_tracer(interceptors)` 在拦截器注册后调用
  - before_request / after_request 钩子中集成 trace 上下文注入
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: 代码审计 — telemetry_bp 已定义但未注册

### FR-GAP-014: httpClient 支持 FormData 和 Blob 下载

- **描述**: httpClient 必须支持 FormData 上传（不设置 Content-Type）和 Blob 响应下载
- **验收标准**:
  - `apiV1.post(url, formData)` 当 body 为 FormData 实例时，不设置 Content-Type header
  - `apiV1.get(url, { responseType: 'blob' })` 返回 Blob 对象而非 JSON
  - 新增 `apiV1.download(url, filename)` 便捷方法，自动触发浏览器下载
- **优先级**: Must（FR-GAP-002 前置）
- **类型映射**: 解决方案需求
- **来源**: 代码审计 — boExportImportService 需要 FormData + Blob

### FR-GAP-015: ESLint 规则强制执行 C1-C3 约束

- **描述**: 系统必须通过 ESLint 自定义规则强制执行 Spec 7 项约束中的 C1-C3
- **验收标准**:
  - C1: composable 内禁止 >20 行的纯函数业务逻辑 → ESLint `max-lines-per-function` + 自定义规则检测纯函数块
  - C2: Pinia store 内禁止 `fetch()` → ESLint `no-restricted-globals` 限定 fetch 只能在 `services/`
  - C3: .vue 文件内禁止 `fetch()` → 同 C2
  - CI 流水线中 `npm run lint` 失败时阻止合并
- **优先级**: Should
- **类型映射**: 解决方案需求 / 非功能需求
- **来源**: Spec C1-C3 约束无强制执行机制

### FR-GAP-016: vitest isolate:true 改造

- **描述**: 系统必须将 vitest.config.js 的 `isolate: false` 改为 `isolate: true`，根治跨 spec mock 链断裂
- **验收标准**:
  - `vitest.config.js` 中 `isolate: true`
  - 全量测试通过率 >= 95%（当前 73 失败中约 30 处由 isolate:false 导致）
  - 测试执行时间增加 <= 30%
- **优先级**: Could
- **类型映射**: 非功能需求
- **来源**: 代码审计 — vitest isolate:false 导致跨 spec 污染

### FR-GAP-017: app_builder.py 同步 Blueprint 注册

- **描述**: 系统必须将 `app_builder.py` 中缺失的 7 个 Blueprint 注册补齐
- **验收标准**:
  - `app_builder.py` 注册列表与 `server.py` 一致
  - 缺失的 7 个 Blueprint（overlap_bp / permission_bp / intent_bp / bo_action_bp / db_admin_bp / graphql_bp / task_api_bp）全部注册
- **优先级**: Could
- **类型映射**: 功能需求
- **来源**: 代码审计 — app_builder.py 与 server.py 不同步

### FR-GAP-018: associationService 补充缓存层

- **描述**: 系统必须在 `associationService.js` 中补充 LRU 缓存，替代 `boAssociationService` 的缓存能力
- **验收标准**:
  - `associationService.js` 支持 `queryV2()` / `countV2()` 结果缓存
  - 缓存 key 格式与 `boAssociationService` 兼容
  - 写操作（assign/unassign/associate/dissociate）自动清除相关缓存
  - 缓存 TTL = 5 分钟（与 BaseService 一致）
- **优先级**: Should（FR-GAP-004 前置）
- **类型映射**: 解决方案需求
- **来源**: 代码审计 — boAssociationService 有 LRU 缓存，associationService 无

---

## 4. 非功能需求

### NFR-GAP-001: 性能

- httpClient 迁移后，API 调用延迟不增加（httpClient 已有连接复用和请求拦截器）
- associationService 补充缓存后，关联查询性能不退化
- vitest isolate:true 后，测试执行时间增加 <= 30%

### NFR-GAP-002: 可测试性

- 每个新 service 必须有单元测试（覆盖率 >= 90%）
- httpClient FormData/Blob 支持必须有集成测试
- Blueprint 注册后必须有 curl 级别的冒烟测试

### NFR-GAP-003: 兼容性

- `boService.js` facade 的 30+ 方法签名不变
- 返回格式从旧格式 `{ success, message, code, errors }` 到新格式 `{ success, data, message, code, httpStatus, traceId }` 的迁移必须向后兼容
- 调用方如果依赖 `result.errors` 字段，需提供兼容层

### NFR-GAP-004: 可观测性

- httpClient 迁移后，所有请求自动携带 traceId
- M14 Telemetry 注册后，拦截器执行自动产生 trace 数据
- M10 MCP 注册后，AI Agent 请求自动应用 RLS

### NFR-GAP-005: 回滚安全

- 每个 FR-GAP 独立可回滚
- Blueprint 注册可注释掉即回滚
- @deprecated 文件删除前需确认所有调用方已迁移

---

## 5. 外部接口需求

### IF-GAP-001: M10 MCP Server API

- **类型**: API
- **端点**:
  - `POST /mcp` — JSON-RPC 2.0 请求
  - `GET /mcp` — Server info
  - `GET /mcp/tools` — 工具列表
- **请求/响应**: JSON-RPC 2.0 格式，protocolVersion `2024-11-05`
- **错误处理**: JSON-RPC 错误码 (-32700/-32600/-32601/-32602)
- **来源**: mcp/server.py

### IF-GAP-002: M13 Schema Dashboard API

- **类型**: API
- **端点**:
  - `GET /api/v1/schema/dashboard/summary`
  - `GET /api/v1/schema/dashboard/entities`
  - `GET /api/v1/schema/dashboard/diff-history`
  - `GET /api/v1/schema/dashboard/sync-status`
- **来源**: meta/api/schema_api.py

### IF-GAP-003: M14 Telemetry API

- **类型**: API
- **端点**:
  - `GET /api/v1/telemetry/stats`
  - `GET /api/v1/telemetry/traces`
  - `GET /api/v1/telemetry/traces/slow`
  - `GET /api/v1/telemetry/traces/<trace_id>`
  - `POST /api/v1/telemetry/configure`
- **来源**: telemetry/api.py

---

## 6. 过渡需求

### TR-GAP-001: boService facade 返回格式兼容

- **描述**: `boCrudService` 迁移 httpClient 后，返回格式从旧格式变为新格式，需确保调用方兼容
- **策略**: 在 `boService.js` facade 层做格式适配，旧字段 `errors` 映射到新字段 `data.errors`
- **回滚方案**: 恢复 `boCrudService.js` 的 raw fetch 调用

### TR-GAP-002: boAssociationService 缓存迁移

- **描述**: 删除 `boAssociationService` 前，需将 LRU 缓存逻辑迁移到 `associationService`
- **策略**: 在 `associationService.js` 中引入与 `BOBaseService` 相同的 LRU 缓存机制
- **回滚方案**: 保留 `boAssociationService` 文件

### TR-GAP-003: .vue fetch 迁移分批执行

- **描述**: 30 处 .vue 内联 fetch 需分批迁移，避免大爆炸式修改
- **策略**: 按重复组优先级分 3 批：P0（authService 已覆盖，14 处）→ P1（需新建 service，8 处）→ P2（评估/低优先级，8 处）
- **回滚方案**: 每批独立，单批回滚不影响其他

---

## 7. 约束与假设

### 7.1 技术约束

- httpClient 当前不支持 FormData body 和 Blob 响应，需先完成 FR-GAP-014
- `boCrudService` 是被 39 个文件导入的核心服务，迁移必须零破坏
- vitest `isolate: true` 会增加测试时间约 30%
- `app_builder.py` 与 `server.py` 需保持同步

### 7.2 业务约束

- M10 MCP Server 的 RLS 集成依赖 M11 RLS 拦截器（已就绪）
- M14 Telemetry 的 trace 采集中间件需在 `before_request`/`after_request` 钩子中集成
- `associationService` 缓存缺失可能导致关联查询性能退化

### 7.3 假设

- httpClient 的 `_request()` 方法已支持 `credentials: 'include'`（已确认）
- `BaseService._request()` 返回格式与 httpClient 一致（已确认）
- M10/M13/M14 的 Blueprint 代码已测试通过，仅需注册（已确认）
- 调用方不依赖 `boCrudService` 返回格式中的 `errors` 字段（需验证）

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|:------:|------|
| FR-GAP-014 | httpClient FormData/Blob 支持 | Must | FR-GAP-002 前置 |
| FR-GAP-001 | boCrudService 迁移 httpClient | Must | 最大 raw fetch 残留区（10 处） |
| FR-GAP-002 | boExportImportService 迁移 httpClient | Must | 第二大 raw fetch 残留区（11 处） |
| FR-GAP-005 | .vue 重复组 A/B/C/D 迁移 | Must | authService 已覆盖，14 处直接替换 |
| FR-GAP-007 | userPreferences store 迁移 | Must | 唯一含 fetch 的 store |
| FR-GAP-011 | server.py 注册 M10 MCP | Must | AI 时代入场券 |
| FR-GAP-018 | associationService 补充缓存 | Should | FR-GAP-004 前置 |
| FR-GAP-003 | boSearchHelpService 迁移 | Should | 2 处 raw fetch |
| FR-GAP-004 | 删除 @deprecated 文件 | Should | 消除双轨并行 |
| FR-GAP-006 | .vue 需新建 service（16 处） | Should | 收敛 .vue fetch |
| FR-GAP-008 | metaService 迁移 httpClient | Should | 消除 _handleResponse 路径 |
| FR-GAP-010 | useMetaList 继续拆分 | Should | 2412 行超标 |
| FR-GAP-012 | server.py 注册 M13 Dashboard | Should | Schema 治理可视化 |
| FR-GAP-013 | server.py 注册 M14 Telemetry | Should | 可观测性 |
| FR-GAP-015 | ESLint 规则 C1-C3 | Should | 约束自动化 |
| FR-GAP-009 | graphqlClient 迁移 httpClient | Could | POC 阶段 |
| FR-GAP-016 | vitest isolate:true | Could | 基础设施改造 |
| FR-GAP-017 | app_builder.py 同步 | Could | 代码一致性 |

### 里程碑建议

- **Milestone 1（P0 收敛，1 周）**: FR-GAP-014 + FR-GAP-001 + FR-GAP-002 + FR-GAP-005 + FR-GAP-007 + FR-GAP-011
- **Milestone 2（P1 消除双轨，1 周）**: FR-GAP-018 + FR-GAP-003 + FR-GAP-004 + FR-GAP-006 + FR-GAP-008
- **Milestone 3（P2 增强，1 周）**: FR-GAP-010 + FR-GAP-012 + FR-GAP-013 + FR-GAP-015
- **Milestone 4（P3 基础设施，0.5 周）**: FR-GAP-009 + FR-GAP-016 + FR-GAP-017

---

## 9. 变更/设计提案（RFC）

### 9.1 As-Is 分析

**当前架构**：双轨并行

```
新架构（FR-UI-xxx 系列）          旧架构（BaseService 继承体系）
+-- httpClient.js (统一)          +-- raw fetch (散落 34 处)
+-- 纯函数优先                     +-- 类继承模式 (BaseService)
+-- 注入式依赖                     +-- this._handleResponse (旧模式)
+-- apiV1/apiV2 命名空间           +-- fetch(url, {headers: getHeaders()})
+-- @deprecated 标记旧方法         +-- 无统一错误处理
+-- 0 处 .vue fetch (目标)         +-- 30 处 .vue 内联 fetch
```

**当前问题**：
1. bo/ 子服务 34 处 raw fetch 是最大残留区
2. .vue 文件 30 处内联 fetch 违反 C3 约束
3. 3 个后端 Blueprint 未注册，线上不可用
4. useMetaList 2412 行超标 11 倍
5. 7 项约束无强制执行机制

**相关代码路径**：
- [boCrudService.js](file:///d:/filework/excel-to-diagram/src/services/bo/boCrudService.js) — ✅ 已迁移到 httpClient
- [boExportImportService.js](file:///d:/filework/excel-to-diagram/src/services/bo/boExportImportService.js) — ✅ 已迁移到 httpClient
- ~~boAssociationService.js~~ — ✅ 已删除，委托到 associationService
- ~~boHierarchyService.js~~ — ✅ 已删除，委托到 hierarchyService
- [boSearchHelpService.js](file:///d:/filework/excel-to-diagram/src/services/bo/boSearchHelpService.js) — ✅ 已迁移到 httpClient
- [metaService.js](file:///d:/filework/excel-to-diagram/src/services/metaService.js) — ✅ 已迁移到 httpClient
- [associationService.js](file:///d:/filework/excel-to-diagram/src/services/associationService.js) — ✅ 已补充 LRU 缓存
- [annotationService.js](file:///d:/filework/excel-to-diagram/src/services/annotationService.js) — 🆕 新建
- [filterVariantService.js](file:///d:/filework/excel-to-diagram/src/services/filterVariantService.js) — 🆕 新建
- [authService.js](file:///d:/filework/excel-to-diagram/src/services/authService.js) — ✅ 新增 v1 REST 端点
- [httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js) — ✅ FormData/Blob/errors/error_code 支持
- [server.py](file:///d:/filework/excel-to-diagram/meta/server.py) — ✅ M10/M13/M14 Blueprint 已注册
- [useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js) — ⏳ 2412 行，待拆分

### 9.2 Target State

**目标架构**：单一统一架构

```
Service Layer (httpClient 统一)
+-- 所有 API 调用走 httpClient (apiV1/apiV2)
+-- 纯函数优先，副作用函数显式命名
+-- 注入式依赖
+-- LRU 缓存层
+-- 统一错误处理 { success, data, message, code, httpStatus, traceId }

Composable Layer (精简)
+-- useMetaList <= 750 行
+-- 0 处内联 fetch
+-- 0 处 getAuthHeaders()
+-- 所有业务逻辑委托 service

Page Layer (纯编排)
+-- 0 处 fetch()
+-- 0 处 getAuthHeaders()
+-- 仅组合 composable 与 service

Backend (全功能在线)
+-- M9 GraphQL: 已注册
+-- M10 MCP: 已注册
+-- M11 RLS: 已集成
+-- M13 Dashboard: 已注册
+-- M14 Telemetry: 已注册 + trace 采集
```

### 9.3 详细设计

#### 9.3.1 httpClient FormData/Blob 扩展

```javascript
// src/utils/httpClient.js 新增

// FormData 支持：当 body 是 FormData 实例时，不设置 Content-Type
async function request(method, url, options = {}) {
  const { body, headers: customHeaders, responseType, ...rest } = options

  const headers = { ...customHeaders }
  // [KEY] FormData 场景：浏览器自动设置 Content-Type (multipart/form-data + boundary)
  if (body instanceof FormData) {
    delete headers['Content-Type']
    delete headers['content-type']
  }

  const response = await fetch(url, {
    method,
    headers,
    body,
    credentials: 'include',
    signal: options.signal,
    ...rest,
  })

  // Blob 下载支持
  if (responseType === 'blob') {
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return response.blob()
  }

  // ... 原有 JSON 处理逻辑
}

// 便捷下载方法
function createNamespace(basePath) {
  return {
    // ... 原有 get/post/put/delete/patch
    download: async (path, filename, options = {}) => {
      const blob = await request('GET', `${basePath}${path}`, {
        ...options,
        responseType: 'blob',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    },
  }
}
```

#### 9.3.2 boCrudService 迁移策略

**就地重构**（不新建 service，因为 boService facade 已是公共 API）：

```javascript
// src/services/bo/boCrudService.js — 迁移前
async create(objectType, data) {
  const response = await fetch(`${API_BASE_V2}/bo/${objectType}`, {
    method: 'POST',
    headers: getHeaders(this._getAuthStore()),
    body: JSON.stringify(data),
    credentials: 'include',
  })
  return this._handleResponse(response)
}

// 迁移后
async create(objectType, data) {
  return this._request('POST', `/api/v2/bo/${objectType}`, { body: data })
}
```

**关键变更**：
- `fetch()` + `getHeaders()` → `this._request()`
- `JSON.stringify(data)` → `_request()` 内部处理
- `_handleResponse(response)` → `_request()` 内部处理
- 返回格式从 `{ success, message, code, errors }` → `{ success, data, message, code, httpStatus, traceId }`
- **缓存逻辑保留**：`_clearCache()` / `_getCached()` / `_setCache()` 不变

**返回格式兼容层**（在 boService.js facade 中）：

```javascript
// src/services/boService.js — 格式适配
function _adaptResult(result) {
  // 新格式 -> 旧格式兼容
  if (result && result.httpStatus !== undefined) {
    return {
      success: result.success,
      data: result.data,
      message: result.message,
      code: result.code,
      errors: result.data?.errors,
      traceId: result.traceId,
    }
  }
  return result
}
```

#### 9.3.3 .vue fetch 迁移示例

```javascript
// AccountSettingsDialog.vue — 迁移前
const response = await fetch('/api/v1/users/me', {
  headers: authStore.getAuthHeaders(),
  credentials: 'include',
})
const data = await response.json()

// 迁移后
import { authService } from '@/services/authService'
const result = await authService.getCurrentUser()
const data = result.data
```

#### 9.3.4 server.py Blueprint 注册

```python
# meta/server.py — 在 Blueprint 注册区域（约 L614 之后）添加

# M10 MCP Server
from mcp.server import mcp_bp
app.register_blueprint(mcp_bp)

# M13 Schema Dashboard
from meta.api.schema_api import schema_dashboard_bp
app.register_blueprint(schema_dashboard_bp)

# M14 Telemetry
from telemetry.api import telemetry_bp
app.register_blueprint(telemetry_bp)

# M14 Telemetry trace 采集中间件
from telemetry.integration import install_global_tracer
install_global_tracer(bo_framework._interceptors)
```

#### 9.3.5 useMetaList 拆分策略

**新增 4 个 service**：

| Service | 提取函数 | 行数 | useMetaList 委托 |
|---------|---------|------|-----------------|
| columnTransformService | _transformColumns / _inferColumnPriority / _inferColumnWidth / _fixDatetimeColumns / _enrichColumnsWithFieldMeta | ~290 | ~10 行 |
| actionTransformService | _transformActions / _inferActionPosition / _mapVariant / _checkPermission + 行操作过滤 | ~120 | ~10 行 |
| metaTransformService | _transformMetaToComponentFormat 中的纯逻辑部分 | ~100 | ~50 行 |
| inlineEditConfigService | _parseInlineEditConfig / getFieldEditConfig | ~55 | ~5 行 |

**合并到已有 service**：
- `_addExportFilterParam` + `_getDefaultOrdering` → `filterService.js`（~75 行）
- `handleError` / `_getNestedValue` / `formatDate` / `truncateText` / `getStatusTagType` → `formatUtils.js`（~45 行）

**预期效果**：useMetaList 从 2412 行降至约 749 行（-69%）。

#### 9.3.6 associationService 缓存补充

```javascript
// src/services/associationService.js — 新增缓存层
import { apiV2 } from '@/utils/httpClient'

const _cache = new Map()
const CACHE_TTL = 5 * 60 * 1000 // 5 分钟

function _getCacheKey(objectType, id, associationName, params) {
  return `${objectType}:${id}:${associationName}:${JSON.stringify(params || {})}`
}

function _getCached(key) {
  const entry = _cache.get(key)
  if (entry && Date.now() - entry.time < CACHE_TTL) return entry.data
  _cache.delete(key)
  return undefined
}

function _setCache(key, data) {
  _cache.set(key, { data, time: Date.now() })
}

function _clearCache(objectType, id) {
  for (const key of _cache.keys()) {
    if (key.startsWith(`${objectType}:${id}:`)) _cache.delete(key)
  }
}

// 查询方法使用缓存
async function queryV2(objectType, id, associationName, params) {
  const key = _getCacheKey(objectType, id, associationName, params)
  const cached = _getCached(key)
  if (cached) return { success: true, data: cached }

  const result = await apiV2.get(`/bo/${objectType}/${id}/\$associations/${associationName}`, { params })
  if (result.success) _setCache(key, result.data)
  return result
}

// 写方法清除缓存
async function assignV2(objectType, id, associationName, data) {
  const result = await apiV2.post(`/bo/${objectType}/${id}/\$associations/${associationName}/assign`, data)
  _clearCache(objectType, id)
  return result
}
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|:----:|
| **A: boCrudService 就地重构** | 改动最小，facade 不变 | 仍依赖 BaseService 继承体系 | **选定** |
| B: 新建 boCrudServiceV2 | 干净架构，纯函数 | 需改 39 个调用方 | 拒绝 |
| C: 直接删除 bo/ 子目录，全部用 apiV2 | 最干净 | 改动巨大，风险高 | 拒绝 |
| **A: useMetaList 拆 4 个 service** | 渐进式，可独立回滚 | 仍遗留 mixed 函数 | **选定** |
| B: useMetaList 完全重写 | 最干净 | 风险极高，35+ 列表页面 | 拒绝 |
| **A: vitest isolate:true** | 根治跨 spec 污染 | 慢 30% | **选定**（Milestone 4） |
| B: 保持 isolate:false + 逐 spec 修 mock | 不增加测试时间 | 无法根治 | 拒绝 |

### 9.5 实施与迁移计划

**实施顺序**（按依赖关系）：

1. FR-GAP-014（httpClient FormData/Blob 支持）— 前置
2. FR-GAP-001（boCrudService 迁移）— 最大收益
3. FR-GAP-002（boExportImportService 迁移）— 第二大收益
4. FR-GAP-005（.vue 重复组 A/B/C/D）— 14 处直接替换
5. FR-GAP-007（userPreferences store）— 唯一 store fetch
6. FR-GAP-011（M10 MCP Blueprint 注册）— 1 行代码
7. FR-GAP-018（associationService 缓存）— FR-GAP-004 前置
8. FR-GAP-003（boSearchHelpService 迁移）— 2 处
9. FR-GAP-004（删除 @deprecated 文件）— 消除双轨
10. FR-GAP-006（.vue 需新建 service）— 16 处
11. FR-GAP-008（metaService 迁移）— 消除 _handleResponse
12. FR-GAP-010（useMetaList 拆分）— 最大重构
13. FR-GAP-012（M13 Dashboard 注册）— 1 行代码
14. FR-GAP-013（M14 Telemetry 注册）— 1 行代码 + 中间件
15. FR-GAP-015（ESLint 规则）— 自动化
16. FR-GAP-009（graphqlClient 迁移）— POC
17. FR-GAP-016（vitest isolate:true）— 基础设施
18. FR-GAP-017（app_builder.py 同步）— 一致性

**风险缓解**：

| 风险 | 缓解策略 |
|------|---------|
| boCrudService 迁移破坏 39 个调用方 | 格式适配层 + 全量测试 |
| associationService 缺缓存导致性能退化 | 先补缓存（FR-GAP-018）再删旧文件（FR-GAP-004） |
| httpClient FormData/Blob 不兼容 | 先完成 FR-GAP-014 并测试 |
| useMetaList 拆分破坏 35+ 列表页面 | 接口契约守卫 + Phase B 183 PASS 回归 |
| M10 MCP 注册后 RLS 未生效 | M11 RLS 拦截器已就绪，MCP rls_integration.py 已实现 |

**测试策略**：
- 单元测试：每个新 service / 迁移后的方法
- 集成测试：boService facade 返回格式兼容性
- E2E 测试：`python d:\filework\test.py --failed` 回归
- 冒烟测试：M10/M13/M14 Blueprint 注册后 curl 验证

**回滚方案**：
- 每个 FR-GAP 独立 git commit
- boCrudService 迁移回滚：恢复 raw fetch 调用
- Blueprint 注册回滚：注释掉 register_blueprint 行
- @deprecated 文件删除回滚：git revert

---

## 10. TBD 列表

| ID | 项 | 缺失信息 | 下一步 |
|----|---|---------|--------|
| TBD-1 | boCrudService 返回格式中 `errors` 字段是否有调用方依赖 | 需 grep 搜索 `result.errors` / `.errors` 在调用方中的使用 | 代码搜索 |
| TBD-2 | ConditionRuleEditor.vue 的 props apiBase/apiHeaders 设计是否保留 | 通用组件 vs service 注入的权衡 | 评估 |
| TBD-3 | httpClient 是否已支持 `responseType: 'blob'` | 需读 httpClient.js 确认 | 代码验证 |
| TBD-4 | M14 Telemetry 的 `install_global_tracer` 是否需在 server.py 中显式调用 | 需确认 telemetry 集成方式 | 代码验证 |
| TBD-5 | useMetaList 拆分后，`_transformMetaToComponentFormat` 的 mixed 部分如何处理 | 需设计响应式状态与纯逻辑的分离策略 | 详细设计 |
| TBD-6 | vitest isolate:true 后测试时间增加是否可接受 | 需实际测量 | 实验验证 |
| TBD-7 | app_builder.py 是否仍在使用 | 需确认是否有其他入口依赖 | 代码搜索 |

---

*Spec + RFC 包含 10 个章节，最后一节为 "TBD 列表"，内容完整。*
