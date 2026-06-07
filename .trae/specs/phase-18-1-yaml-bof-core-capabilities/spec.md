# Spec: Phase 18.1 — YAML Schema 补全 + BOF 核心能力建设

## 1. 背景与目标

### 1.1 背景

产品版本管理（Product/Version）和架构数据管理（Domain/SubDomain/ServiceModule/BusinessObject）是系统中覆盖面最广的 6 个核心对象。当前这 6 个对象存在**双轨并存**问题：

- **旧架构**: 前端通过 `ArchDataManageApp`（46 文件）和 `ProductVersionApp`（8 文件）调用 `/api/v1/manage/*`，后端使用 `manage_api.py` + `ManageService` + `QueryService`。
- **新架构**: 统一 YAML → BOFramework → v2 API → MetaListPage，但 6 个对象尚未完全迁移。

经过深度分析，发现这不仅是"适配迁移"，更需要在三层（YAML/BOF/API）补齐 **6 项核心能力**，否则迁移后功能将严重回退。

### 1.2 业务目标

- 将 6 个对象的 YAML Schema 补全为**完整驱动能力**的配置
- 在 BOF 层建设 GAP-1~GAP-6 所需的核心服务
- 新增 5 个 v2 API 端点，使前端可完全脱离 `/api/v1/manage/*`

### 1.3 用户/涉众目标

- **前端开发者**: 调用 v2 API 即可获取所有数据（树形、上下文、备注、批量导入导出），无需直接写 SQL
- **架构管理员**: 通过 YAML 配置即可声明层级、上下文、级联选择，无需改代码
- **系统管理员**: 6 个对象的 CRUD、导入导出、数据权限全部走 v2 统一链路

## 2. 需求类型概览

| 类型 | 适用 | 证据 |
|------|------|------|
| 业务需求 | 是 | 双轨并存导致维护成本高、功能回退风险 |
| 用户/涉众需求 | 是 | 前端需要 v2 API 支持树形/上下文/级联/备注/批量导入导出 |
| 解决方案需求 | 是 | YAML 声明能力 + BOF 服务能力 + API 暴露能力 |
| 功能需求 | 是 | 6 个 GAP 的具体功能定义 |
| 非功能需求 | 是 | 性能（树构建避免 N+1）、兼容性（v1 共存） |
| 外部接口需求 | 是 | 5 个新 v2 API 端点 |
| 过渡需求 | 是 | v1/v2 共存期、Deprecation 标记 |

## 3. 功能需求

### FR-001: YAML Schema 补全 — 字段属性标准化

- **描述**: 6 个对象的 YAML Schema 存在大量不一致和缺失，必须标准化后才能驱动统一架构
- **验收标准**:
  - [ ] 所有 `code` 字段添加 `required: true`、`immutable: true`、`pattern: "^[A-Z][A-Z0-9_]*$"`
  - [ ] 所有 `name` 字段添加 `required: true`、`data_category: text`
  - [ ] `product.code` 补齐 `immutable: true` 和 `pattern` 校验
  - [ ] `product.is_active` 补齐 `ui.widget: switch`
  - [ ] `version.code` 补齐 `immutable: true` 和 `pattern` 校验
  - [ ] `domain/sub_domain/service_module` 补齐 `description` 字段（与 product/version/business_object 对齐）
  - [ ] `business_object.description` 类型从 `string` 改为 `text`（与 product/version 对齐）
  - [ ] 所有对象 `id` 字段统一添加 `ui.visible: false / editable: false`
  - [ ] 修复 `business_object` 索引引用不存在的 `is_deleted` 字段
  - [ ] 修复所有 `pageSize` 重复定义问题
  - [ ] `product/version` 补齐 `import_export` 配置
  - [ ] `product/version` 补齐 `owner_id` 字段（与 domain 及以下对齐）
  - [ ] `domain/sub_domain/service_module` 补齐 `description` 字段（与 product/version/business_object 对齐）
  - [ ] 所有对象补齐 `display_name_field` 声明
  - [ ] 所有对象补齐 `filter` 视图配置
  - [ ] 所有对象补齐 `authorization` 配置
  - [ ] 所有对象补齐 `change_notification` 配置
  - [ ] 所有 virtual 字段补齐 `redundancy` 声明（Type-C 解析冗余）
  - [ ] 所有 `resolve_from_field` 路径补齐
- **优先级**: Must
- **来源**: YAML Schema 逐文件分析

### FR-002: YAML Schema 补全 — `hierarchies` 配置块

- **描述**: 为 domain/sub_domain/service_module/business_object 添加 `hierarchies` 配置块，声明 4 层树形结构
- **验收标准**:
  - [ ] `domain.yaml` 新增 `hierarchies` 配置，声明 arch_tree（4 层: domain→sub_domain→service_module→business_object）
  - [ ] `hierarchies` 包含 `levels` 定义，每层声明 `object_type`、`parent_field`、`children_field`
  - [ ] `hierarchies` 包含 `root_filter` 声明（按 version_id 过滤树根）
  - [ ] YAML 解析器 `parse_hierarchies()` 正确解析新配置
  - [ ] `$metadata` 端点返回 `hierarchies` 配置
- **优先级**: Must
- **来源**: GAP-1 层级树形导航

### FR-003: YAML Schema 补全 — `context` 配置块

- **描述**: 为 domain/sub_domain/service_module/business_object 添加 `context` 配置块，声明版本上下文
- **验收标准**:
  - [ ] `domain.yaml` 新增 `context` 配置，声明 `scope_field: version_id`、`cascade_to: [sub_domain, service_module, business_object]`
  - [ ] `context` 包含 `parent_context` 声明（version 的 filter_field 为 product_id）
  - [ ] YAML 解析器 `parse_context()` 正确解析新配置
  - [ ] `$metadata` 端点返回 `context` 配置
- **优先级**: Must
- **来源**: GAP-2 产品版本上下文

### FR-004: YAML Schema 补全 — `cascade_select` 配置块

- **描述**: 为所有 6 个对象添加 `cascade_select` 配置块，声明级联下拉关系
- **验收标准**:
  - [ ] `domain.yaml` 新增 `cascade_select`：product_id→version_id→domain_id
  - [ ] `sub_domain.yaml` 新增 `cascade_select`：product_id→version_id→domain_id→sub_domain_id
  - [ ] `service_module.yaml` 新增 `cascade_select`：product_id→version_id→domain_id→sub_domain_id→service_module_id
  - [ ] `business_object.yaml` 新增 `cascade_select`：5 级完整链路 product_id→version_id→domain_id→sub_domain_id→service_module_id
  - [ ] 每个 cascade_select 条目包含 `field`、`controls`、`filter`、`clear_downstream`
  - [ ] YAML 解析器 `parse_cascade_select()` 正确解析新配置
  - [ ] `$metadata` 端点返回 `cascade_select` 配置
- **优先级**: Must
- **来源**: F-5 级联下拉

### FR-005: YAML Schema — scope_rules 引用机制验证

- **描述**: relationship 对象的 `scope_rules` 已在 `hierarchies.yaml` 中定义（4 种 hierarchy_scopes），relationship.yaml 通过 `scope_rules_ref: hierarchies.hierarchy_scopes` 引用。本项确保引用机制正确工作，无需新增配置块
- **验收标准**:
  - [ ] `relationship.yaml` 的 `scope_rules_ref` 引用路径正确解析
  - [ ] `virtual_field_transform.py` 的 `load_scope_rules_from_ref()` 正确加载 4 种分类规则
  - [ ] `generate_scope_sql_from_rules()` 正确生成 SQL CASE 表达式
  - [ ] `cascade_service.compute_scope()` 正确计算分类（当前为硬编码 if/elif，通用化延后到 GAP-3）
  - [ ] `$metadata` 端点返回 `scope_rules` 配置（含 4 种分类定义）
- **优先级**: Should
- **来源**: GAP-3 关系范围可视化（本阶段仅验证引用机制，通用化延后）

### FR-006: YAML Schema — annotations 配置同步

- **描述**: 备注分类已通过 `enum_values` 表实现 extensible（`enum_type_id = 'annotation_category'`），无需额外自定义机制。YAML `annotations.categories` 配置作为初始化种子，确保与 `enum_values` 表同步
- **验收标准**:
  - [ ] 4 个对象新增 `annotations` 配置，`enabled: true`
  - [ ] `categories` 列表与 `enum_values` 表中 `annotation_category` 类型保持一致
  - [ ] YAML 解析器正确解析 `annotations` 配置
  - [ ] `$metadata` 端点返回 `annotations` 配置（含当前分类列表）
  - [ ] 运行时分类从 `enum_values` 表动态获取（已实现，无需改动）
- **优先级**: Should
- **来源**: GAP-4 备注系统

### FR-007: BOF — HierarchyService.build_tree()

- **描述**: 后端拼装 4 层树形结构，避免前端 N+1 请求
- **验收标准**:
  - [ ] 新建 `meta/services/hierarchy_tree_service.py`
  - [ ] `build_tree(version_id, object_types=None) -> List[TreeNode]` 一次性返回完整树
  - [ ] 树节点结构: `{id, name, object_type, children: [], child_count, ...}`
  - [ ] 内部使用并行查询（4 个对象各一次查询），前端拼装
  - [ ] 性能: version_id 下 1000 个节点 < 500ms
  - [ ] 支持部分加载: `object_types=['domain', 'sub_domain']` 只构建前 2 层
- **优先级**: Must
- **来源**: GAP-1，替代 `archDataStore.fetchFilteredTreeData()` 的 4 次并行请求 + 前端拼装

### FR-008: BOF — 版本上下文过滤拦截器

- **描述**: 当请求带有 `version_id` 上下文时，自动为 domain/sub_domain/service_module/business_object 的查询追加 `version_id` 过滤条件
- **验收标准**:
  - [ ] 新建 `meta/core/interceptors/context_filter_interceptor.py`
  - [ ] 优先级: 25（在 QueryInterceptor 之前）
  - [ ] `before_action()`: 对 query 动作，若对象有 `context` 配置且请求含 `version_id`，自动追加 `version_id = X` 条件
  - [ ] 不影响无 `context` 配置的对象（如 product/version）
  - [ ] 注册到 BOFramework 默认拦截器链
- **优先级**: Must
- **来源**: GAP-2，替代 `archDataStore` 中手动传递 `version_id` 参数

### FR-009: BOF — RelationScopeService.classify()

- **描述**: 后端计算关系的分类和内外范围
- **验收标准**:
  - [ ] 新建 `meta/services/relation_scope_service.py`
  - [ ] `classify(version_id, scope_object_ids=None) -> Dict[category, List[relation]]`
  - [ ] 分类基于 `scope_rules` 配置: cross_domain / same_domain_cross_subdomain / same_subdomain_cross_module / same_module
  - [ ] 支持 `scope_mode`: involved（OR 语义）/ internal（AND 语义）
  - [ ] 性能: 1000 条关系 < 200ms
- **优先级**: Should
- **来源**: GAP-3，替代 `manage_api.list_relationships()` 中的 6 表 JOIN + 分类计算

### FR-010: BOF — 通用 Annotation CRUD

- **描述**: 独立于业务对象的备注服务
- **验收标准**:
  - [ ] `meta/services/annotation_service.py` 已存在，验证其 CRUD 能力
  - [ ] `list_by_target(target_type, target_id)` — 按 target 查询备注
  - [ ] `create(target_type, target_id, category, content)` — 创建备注
  - [ ] `update(annotation_id, category, content)` — 更新备注
  - [ ] `delete(annotation_id)` — 删除备注
  - [ ] 支持 4 种分类: note/warning/question/issue
- **优先级**: Should
- **来源**: GAP-4，替代 `useApi.listAnnotationsByTarget/createAnnotation/updateAnnotation/deleteAnnotation`

### FR-011: BOF — ExportService.export_multi()

- **描述**: 多对象批量导出，支持级联导出
- **验收标准**:
  - [ ] 扩展 `meta/services/import_export_service.py`
  - [ ] `export_multi(object_types, version_id, options) -> BytesIO`
  - [ ] 支持级联导出: domain + sub_domain + service_module + business_object + relationship
  - [ ] 导出选项: `include_hierarchy_path`、`include_hierarchy_ids`、`include_operation_mode`、`protect_sheet`、`include_readonly`
  - [ ] 输出多 Sheet Excel，每个对象类型一个 Sheet
  - [ ] 性能: 1000 条记录 < 3s
- **优先级**: Must
- **来源**: GAP-5，替代 `useApi.exportData()` 和 `ExportDialog.vue` 的级联导出

### FR-012: BOF — ImportService.import_multi_async()

- **描述**: 多对象异步导入，支持预览和进度查询
- **验收标准**:
  - [ ] 扩展 `meta/services/import_export_service.py`
  - [ ] `import_multi_async(file, conflict_strategy, context) -> task_id`
  - [ ] `get_import_status(task_id) -> {status, progress, results}`
  - [ ] 支持多 Sheet Excel（5 种对象类型同时导入）
  - [ ] 支持冲突策略: upsert / skip
  - [ ] 支持预览: `preview_import(file) -> {sheets: [{name, row_count, errors}]}`
  - [ ] 异步执行: 后台线程处理，前端轮询进度
  - [ ] 结果统计: 按对象类型分列 {created, updated, deleted, skipped, failed}
- **优先级**: Must
- **来源**: GAP-5，替代 `useApi.importDataAsync()` + `getImportStatus()`

### FR-013: API — GET /api/v2/bo/hierarchy/tree

- **描述**: 一次性返回完整 4 层树结构
- **验收标准**:
  - [ ] 路由: `GET /api/v2/bo/hierarchy/tree?version_id=X&object_types=domain,sub_domain,...`
  - [ ] 参数: `version_id`（必填）、`object_types`（可选，逗号分隔）
  - [ ] 响应: `{success: true, data: [TreeNode, ...]}`
  - [ ] TreeNode: `{id, name, code, object_type, child_count, children: [TreeNode, ...]}`
  - [ ] 认证: 需要登录
  - [ ] 数据权限: 仅返回有权限的节点
- **优先级**: Must
- **来源**: GAP-1

### FR-014: API — GET/POST/PUT/DELETE /api/v2/annotations

- **描述**: 通用备注 CRUD 端点
- **验收标准**:
  - [ ] `GET /api/v2/annotations?target_type=X&target_id=Y` — 查询备注
  - [ ] `POST /api/v2/annotations` — 创建备注 `{target_type, target_id, category, content}`
  - [ ] `PUT /api/v2/annotations/<id>` — 更新备注
  - [ ] `DELETE /api/v2/annotations/<id>` — 删除备注
  - [ ] 认证: 需要登录
- **优先级**: Should
- **来源**: GAP-4

### FR-015: API — POST /api/v2/bo/export/batch

- **描述**: 多对象批量导出端点
- **验收标准**:
  - [ ] 路由: `POST /api/v2/bo/export/batch`
  - [ ] Body: `{object_types: [...], version_id, options: {include_hierarchy_path, include_hierarchy_ids, ...}}`
  - [ ] 响应: Excel 文件下载（Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet）
  - [ ] 认证: 需要登录
- **优先级**: Must
- **来源**: GAP-5

### FR-016: API — POST /api/v2/bo/import/batch + GET /api/v2/bo/import/status/<task_id>

- **描述**: 多对象异步导入端点
- **验收标准**:
  - [ ] `POST /api/v2/bo/import/batch` — 上传文件（FormData），返回 `{task_id}`
  - [ ] `POST /api/v2/bo/import/preview` — 预览导入文件，返回 Sheet 列表+行数+校验错误
  - [ ] `GET /api/v2/bo/import/status/<task_id>` — 查询导入进度
  - [ ] 响应: `{status: pending/processing/completed/failed, progress: 0-100, current_type, results: {...}}`
  - [ ] 认证: 需要登录
- **优先级**: Must
- **来源**: GAP-5

### FR-017: API — GET /api/v2/bo/relationship/scope-tree

- **描述**: 返回分类后的关系范围树
- **验收标准**:
  - [ ] 路由: `GET /api/v2/bo/relationship/scope-tree?version_id=X&scope_mode=involved`
  - [ ] 参数: `version_id`（必填）、`scope_mode`（involved/internal）、`domain_id`/`sub_domain_id`/`service_module_id`（可选范围过滤）
  - [ ] 响应: `{success: true, data: {categories: [{name, relations: [...]}], scope_tree: [...]}}`
  - [ ] 认证: 需要登录
- **优先级**: Should
- **来源**: GAP-3

### FR-018: $metadata 端点扩展

- **描述**: 确保 `$metadata` 端点返回所有新增配置块
- **验收标准**:
  - [ ] `GET /api/v2/meta/<object_type>/ui-config` 返回 `hierarchies`、`context`、`cascade_select`、`annotations`
  - [ ] `GET /api/v2/meta/<object_type>/schema` 返回 `scope_rules`（仅 relationship）
  - [ ] 所有新增配置块在 `$metadata` 响应中有独立节点
- **优先级**: Must
- **来源**: 前端需要 $metadata 驱动 UI

## 4. 非功能需求

### NFR-001: 性能 — 树构建

- **描述**: `HierarchyService.build_tree()` 在 1000 个节点时 < 500ms
- **测量**: 后端计时，version_id 下 4 个对象并行查询
- **优先级**: Must

### NFR-002: 性能 — 批量导出

- **描述**: `ExportService.export_multi()` 在 1000 条记录时 < 3s
- **测量**: 后端计时，5 个对象类型各 200 条
- **优先级**: Must

### NFR-003: 兼容性 — v1/v2 共存

- **描述**: 新增 v2 端点不影响现有 v1 端点功能
- **测量**: v1 端点回归测试全部通过
- **优先级**: Must

### NFR-004: 数据权限

- **描述**: 所有新端点必须集成数据权限过滤
- **测量**: 非管理员用户只能看到有权限的数据
- **优先级**: Must

## 5. 外部接口需求

### IF-001: GET /api/v2/bo/hierarchy/tree

- **类型**: API
- **端点**: `GET /api/v2/bo/hierarchy/tree`
- **请求参数**: `version_id`（必填）、`object_types`（可选）
- **响应**: `{success: true, data: [TreeNode]}`
- **错误处理**: 401 未认证、403 无权限、400 缺少 version_id

### IF-002: Annotations CRUD

- **类型**: API
- **端点**: `GET/POST/PUT/DELETE /api/v2/annotations`
- **请求/响应**: 标准 CRUD 格式
- **错误处理**: 401 未认证、403 无权限、404 注解不存在

### IF-003: Batch Export

- **类型**: API
- **端点**: `POST /api/v2/bo/export/batch`
- **请求**: `{object_types, version_id, options}`
- **响应**: Excel 文件流
- **错误处理**: 401 未认证、403 无权限、400 参数错误

### IF-004: Batch Import

- **类型**: API
- **端点**: `POST /api/v2/bo/import/batch` + `GET /api/v2/bo/import/status/<task_id>`
- **请求**: FormData（file + conflict_strategy + context）
- **响应**: `{task_id}` / `{status, progress, results}`
- **错误处理**: 401 未认证、403 无权限、400 文件格式错误

### IF-005: Relationship Scope Tree

- **类型**: API
- **端点**: `GET /api/v2/bo/relationship/scope-tree`
- **请求参数**: `version_id`、`scope_mode`、`domain_id`/`sub_domain_id`/`service_module_id`
- **响应**: `{success: true, data: {categories, scope_tree}}`
- **错误处理**: 401 未认证、403 无权限、400 缺少 version_id

## 6. 过渡需求

### TR-001: v1/v2 共存期

- **描述**: 新增 v2 端点后，v1 端点继续正常工作
- **策略**: v2 端点使用独立 Blueprint，不修改 v1 代码
- **回滚方案**: 删除 v2 端点路由注册即可回滚
- **来源**: 系统运行中不能中断 v1 服务

### TR-002: YAML 配置向后兼容

- **描述**: 新增 `hierarchies`/`context`/`cascade_select`/`scope_rules`/`annotations` 配置块不能破坏现有 YAML 解析
- **策略**: 所有新配置块为可选（Optional），缺失时使用默认值
- **回滚方案**: 删除新配置块即可恢复原状
- **来源**: 现有 6 个 YAML 文件必须继续正常工作

## 7. 约束与假设

### 7.1 技术约束

- Python 后端（Flask），SQLite 数据库
- YAML 解析使用 `meta/core/yaml_loader.py` 现有框架
- BOFramework 拦截器体系必须遵守现有优先级规则
- v2 API 使用 `bo_bp` Blueprint（前缀 `/api/v2/bo`）
- 异步导入使用 Python threading（非 Celery），与现有 `importDataAsync` 一致

### 7.2 业务约束

- 本 Phase 仅覆盖后端（YAML + BOF + API），不涉及前端 UI 改动
- 前端 UI 迁移在 M18.2-M18.9 中完成
- Phase 12（Value Help）由另一个智能体并行跟进，本 Phase 不涉及

### 7.3 假设

- 6 个对象的数据库表结构不变（仅 YAML 配置变更）
- 现有 `annotation_service.py` 的 CRUD 能力可复用
- 现有 `import_export_service.py` 的单对象导入导出可扩展为多对象
- `HierarchyFilterService` 和 `HierarchyPathService` 可复用
- `CascadeService` 的级联策略可复用

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-001 | YAML 字段标准化 | Must | 所有后续工作的基础 |
| FR-002 | YAML hierarchies | Must | GAP-1 前置 |
| FR-003 | YAML context | Must | GAP-2 前置 |
| FR-004 | YAML cascade_select | Must | F-5 前置 |
| FR-005 | YAML scope_rules | Should | GAP-3 前置，可延后 |
| FR-006 | YAML annotations | Should | GAP-4 前置，可延后 |
| FR-007 | HierarchyService | Must | GAP-1 核心 |
| FR-008 | 版本上下文拦截器 | Must | GAP-2 核心 |
| FR-009 | RelationScopeService | Should | GAP-3 核心，可延后 |
| FR-010 | Annotation CRUD | Should | GAP-4 核心，可延后 |
| FR-011 | ExportService.export_multi | Must | GAP-5 核心 |
| FR-012 | ImportService.import_multi_async | Must | GAP-5 核心 |
| FR-013 | API hierarchy/tree | Must | FR-007 的 API 暴露 |
| FR-014 | API annotations | Should | FR-010 的 API 暴露 |
| FR-015 | API export/batch | Must | FR-011 的 API 暴露 |
| FR-016 | API import/batch | Must | FR-012 的 API 暴露 |
| FR-017 | API scope-tree | Should | FR-009 的 API 暴露 |
| FR-018 | $metadata 扩展 | Must | 前端驱动必需 |

### 建议里程碑

- **M18.1-A (Day 1-2)**: FR-001 + FR-002 + FR-003 + FR-004（YAML 补全）
- **M18.1-B (Day 2-3)**: FR-007 + FR-008 + FR-018（核心 BOF 服务 + $metadata）
- **M18.1-C (Day 3-4)**: FR-011 + FR-012 + FR-013 + FR-015 + FR-016（批量导入导出 + API）
- **M18.1-D (Day 4)**: FR-005 + FR-006 + FR-009 + FR-010 + FR-014 + FR-017（可延后的 GAP-3/4）

## 9. 变更/设计提案（RFC）

### 9.1 现状分析

**当前架构**:

```
前端 (ArchDataManageApp/ProductVersionApp)
  │
  ├── useApi.js → /api/v1/manage/* (manage_api.py)
  │     ├── list(objectType, params)
  │     ├── create/update/delete
  │     ├── listAnnotationsByTarget / createAnnotation / ...
  │     ├── exportData / importData / importDataAsync
  │     └── downloadFullTemplate / downloadImportTemplate
  │
  └── archDataStore.js
        ├── fetchFilteredTreeData() → 4 次并行 API 请求 + 前端拼装树
        ├── fetchProducts/fetchVersions
        └── CRUD 委托 useApi

后端 (manage_api.py)
  ├── 通用 CRUD: /<object_type> GET/POST/PUT/DELETE
  ├── 深度创建: /<object_type>/deep POST
  ├── 批量操作: /<object_type>/batch-create/update/delete
  ├── 关系列表: /relationships (6 表 JOIN + 分类计算)
  ├── 元数据: /meta/objects, /meta/hierarchies, /meta/hierarchies/config
  ├── 导入导出: /import, /export, /import/async, /import/status
  └── 备注系统: /annotations/by-target, /annotations CRUD
```

**关键问题**:
1. 树构建是前端拼装（4 次 N+1 请求），无后端统一服务
2. 版本上下文是前端手动传递 `version_id`，无后端拦截器
3. 关系分类是 manage_api.py 内联 SQL（6 表 JOIN），无独立服务
4. 备注系统已有独立服务但走 v1 端点
5. 批量导入导出仅支持单对象，无多对象联合能力

### 9.2 目标状态

```
前端 (未来 MetaListPage)
  │
  └── boService.js → /api/v2/bo/* (bo_api.py)
        ├── 标准 CRUD: /<object_type> GET/POST/PUT/DELETE
        ├── 树构建: /hierarchy/tree?version_id=X
        ├── 上下文过滤: 自动（ContextFilterInterceptor）
        ├── 备注: /annotations CRUD
        ├── 批量导出: /export/batch
        ├── 批量导入: /import/batch + /import/status/<id>
        └── 关系范围: /relationship/scope-tree
```

### 9.3 详细设计

#### 9.3.1 YAML 新增配置块解析

**文件**: `meta/core/yaml_loader.py`

新增 4 个解析函数:

```python
def parse_hierarchies(config: Dict) -> Optional[List[Dict]]:
    """解析 hierarchies 配置块"""
    # 输入: {hierarchies: [{name, type, levels: [{object_type, parent_field, children_field}], root_filter}]}
    # 输出: List[HierarchyConfig]

def parse_context(config: Dict) -> Optional[Dict]:
    """解析 context 配置块"""
    # 输入: {context: {scope_field, cascade_to, parent_context: {object_type, filter_field}}}
    # 输出: ContextConfig

def parse_cascade_select(config: Dict) -> Optional[List[Dict]]:
    """解析 cascade_select 配置块"""
    # 输入: {cascade_select: [{field, controls, filter, clear_downstream}]}
    # 输出: List[CascadeSelectConfig]

def parse_annotations_config(config: Dict) -> Optional[Dict]:
    """解析 annotations 配置块"""
    # 输入: {annotations: {enabled, categories: [{code, name}]}}
    # 输出: AnnotationsConfig
```

**集成点**: 在 `parse_object()` 中调用这 4 个函数，将结果存入 `MetaObject` 的新字段。

**MetaObject 新增字段**:

```python
class MetaObject:
    # ... 现有字段 ...
    hierarchies: Optional[List[Dict]] = None      # FR-002
    context: Optional[Dict] = None                 # FR-003
    cascade_select: Optional[List[Dict]] = None    # FR-004
    annotations_config: Optional[Dict] = None      # FR-006
```

#### 9.3.2 HierarchyTreeService

**文件**: `meta/services/hierarchy_tree_service.py`（新建）

```python
class HierarchyTreeService:
    def __init__(self, data_source):
        self.data_source = data_source

    def build_tree(self, version_id: int, object_types: List[str] = None) -> List[Dict]:
        """
        构建 4 层树形结构
        
        算法:
        1. 从 domain.yaml 的 hierarchies 配置获取层级定义
        2. 并行查询 4 个对象: domain, sub_domain, service_module, business_object
           每个 query 带 version_id 过滤
        3. 前端拼装树: domain → sub_domain → service_module → business_object
        4. 每个节点计算 child_count
        
        性能优化:
        - 4 次查询（非 N+1），与 archDataStore.fetchFilteredTreeData() 策略一致
        - 使用 QueryService.search() 复用现有查询引擎
        - 数据权限自动生效（QueryInterceptor 已集成）
        """
```

**与现有代码的关系**:
- 复用 `QueryService.search()` 执行查询
- 复用 `HierarchyFilterService` 解析层级条件
- 替代 `archDataStore.fetchFilteredTreeData()` 的 4 次并行请求逻辑

#### 9.3.3 ContextFilterInterceptor

**文件**: `meta/core/interceptors/context_filter_interceptor.py`（新建）

```python
class ContextFilterInterceptor(Interceptor):
    """
    版本上下文过滤拦截器
    
    当请求带有 version_id 参数且对象有 context 配置时，
    自动追加 version_id 过滤条件到查询中。
    """
    name = "context_filter"
    priority = 25  # 在 QueryInterceptor(50) 之前

    def before_action(self, context: ActionContext):
        if context.action != 'query':
            return
        
        meta_obj = context.meta_object
        if not meta_obj.context:
            return
        
        version_id = context.params.get('version_id')
        if not version_id:
            return
        
        scope_field = meta_obj.context['scope_field']
        # 追加 version_id 条件到 filter_params
        context.params.setdefault('filter_params', {})
        context.params['filter_params'][scope_field] = version_id

    def after_action(self, context: ActionContext):
        pass
```

**与现有代码的关系**:
- 复用 `Interceptor` 基类
- 注册到 `BOFramework` 默认拦截器链
- 替代前端手动传递 `version_id` 的逻辑

#### 9.3.4 ExportService.export_multi()

**文件**: `meta/services/import_export_service.py`（扩展）

```python
def export_multi(self, object_types: List[str], version_id: int, 
                 options: Dict = None) -> BytesIO:
    """
    多对象批量导出
    
    算法:
    1. 按 object_types 顺序，对每个类型调用 QueryService.search()
       带 version_id 过滤
    2. 对每个类型调用 enrich_records() 填充冗余字段
    3. 若 options.include_hierarchy_path，调用 HierarchyPathService 批量获取路径
    4. 写入多 Sheet Excel
    5. 若 options.protect_sheet，保护工作表
    6. 若 options.include_readonly，标记只读字段（灰色背景）
    """
```

#### 9.3.5 ImportService.import_multi_async()

**文件**: `meta/services/import_export_service.py`（扩展）

```python
def import_multi_async(self, file, conflict_strategy: str = 'upsert',
                       context: Dict = None) -> str:
    """
    多对象异步导入
    
    算法:
    1. 保存上传文件到临时目录
    2. 生成 task_id
    3. 启动后台线程执行导入
    4. 返回 task_id
    
    后台线程:
    1. 读取 Excel，获取 Sheet 列表
    2. 按 Sheet 顺序（domain → sub_domain → service_module → business_object → relationship）
       逐 Sheet 导入
    3. 每完成一个 Sheet，更新进度
    4. 全部完成后，汇总结果
    """

def preview_import(self, file) -> Dict:
    """
    导入预览
    返回: {sheets: [{name, row_count, columns, errors: [{row, column, message}]}]}
    """

def get_import_status(self, task_id: str) -> Dict:
    """
    查询导入进度
    返回: {status, progress, current_type, results: {object_type: {created, updated, ...}}}
    """
```

#### 9.3.6 RelationScopeService

**文件**: `meta/services/relation_scope_service.py`（新建）

```python
class RelationScopeService:
    def classify(self, version_id: int, scope_object_ids: Dict = None,
                 scope_mode: str = 'involved') -> Dict:
        """
        关系分类
        
        算法（复用 manage_api.list_relationships 的分类逻辑）:
        1. 查询 version_id 下的所有 relationship
        2. JOIN business_objects + service_modules + sub_domains + domains
        3. 根据 scope_rules 配置计算分类
        4. 根据 scope_mode 过滤范围
        """
```

#### 9.3.7 v2 API 端点

**文件**: `meta/api/bo_api.py`（扩展）

新增 5 个端点注册到 `bo_bp`:

```python
# FR-013: 树构建
@bo_bp.route('/hierarchy/tree', methods=['GET'])
def get_hierarchy_tree():
    version_id = request.args.get('version_id', type=int)
    object_types = request.args.get('object_types', '').split(',') if request.args.get('object_types') else None
    tree = hierarchy_tree_service.build_tree(version_id, object_types)
    return jsonify({'success': True, 'data': tree})

# FR-014: 备注 CRUD (新 Blueprint)
annotations_v2_bp = Blueprint('annotations_v2', __name__, url_prefix='/api/v2/annotations')

@annotations_v2_bp.route('', methods=['GET'])
def list_annotations():
    target_type = request.args.get('target_type')
    target_id = request.args.get('target_id', type=int)
    annotations = annotation_service.list_by_target(target_type, target_id)
    return jsonify({'success': True, 'data': annotations})

# FR-015: 批量导出
@bo_bp.route('/export/batch', methods=['POST'])
def export_batch():
    data = request.get_json()
    excel_bytes = export_service.export_multi(
        object_types=data['object_types'],
        version_id=data['version_id'],
        options=data.get('options', {})
    )
    return send_file(excel_bytes, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# FR-016: 批量导入
@bo_bp.route('/import/batch', methods=['POST'])
def import_batch():
    file = request.files['file']
    conflict_strategy = request.form.get('conflict_strategy', 'upsert')
    context = json.loads(request.form.get('context', '{}'))
    task_id = import_service.import_multi_async(file, conflict_strategy, context)
    return jsonify({'success': True, 'task_id': task_id})

@bo_bp.route('/import/status/<task_id>', methods=['GET'])
def get_import_status(task_id):
    status = import_service.get_import_status(task_id)
    return jsonify({'success': True, 'data': status})

# FR-017: 关系范围树
@bo_bp.route('/relationship/scope-tree', methods=['GET'])
def get_relationship_scope_tree():
    version_id = request.args.get('version_id', type=int)
    scope_mode = request.args.get('scope_mode', 'involved')
    result = relation_scope_service.classify(version_id, scope_mode=scope_mode)
    return jsonify({'success': True, 'data': result})
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A: 后端拼装树 | 一次请求、前端简单 | 后端复杂度增加 | **选择** — 与 archDataStore 策略一致 |
| B: 前端拼装树 | 后端简单 | N+1 请求、前端复杂 | 拒绝 — 性能差 |
| C: GraphQL | 灵活查询 | 架构变更太大 | 拒绝 — 不符合现有架构 |

### 9.5 实施与迁移计划

**实施顺序**:

1. FR-001: YAML 字段标准化（修改 6 个 YAML 文件）
2. FR-002/003/004: YAML 新增配置块（hierarchies/context/cascade_select）
3. yaml_loader.py 新增 4 个解析函数
4. models.py MetaObject 新增 4 个字段
5. FR-018: $metadata 端点扩展
6. FR-007: HierarchyTreeService
7. FR-008: ContextFilterInterceptor
8. FR-013: API hierarchy/tree
9. FR-011: ExportService.export_multi()
10. FR-012: ImportService.import_multi_async()
11. FR-015/016: API export/batch + import/batch
12. FR-005/006/009/010/014/017: 可延后的 GAP-3/4

**风险缓解**:

| 风险 | 缓解策略 |
|------|---------|
| YAML 新增配置块破坏现有解析 | 所有新配置块为 Optional，缺失时默认 None |
| ContextFilterInterceptor 影响无 context 的对象 | should_execute() 检查 meta_obj.context |
| 异步导入线程安全 | 使用 threading.Lock 保护 task_status 字典 |
| v2 API 与 v1 行为不一致 | 对同一数据执行 v1/v2 对比测试 |

**测试策略**:

- **单元测试**: yaml_loader 新增解析函数、HierarchyTreeService.build_tree()、ContextFilterInterceptor.before_action()、ExportService.export_multi()、ImportService 各方法
- **集成测试**: 6 个对象的 v2 CRUD 完整链路、$metadata 返回新配置块、hierarchy/tree 返回正确树结构、export/batch 生成正确 Excel、import/batch 异步导入完整流程
- **回归测试**: v1 端点全部通过、现有 YAML 解析不受影响

**回滚方案**:

1. 删除 v2 新增路由注册（5 个端点）
2. 删除新增 Service 文件（hierarchy_tree_service.py、relation_scope_service.py）
3. 删除新增 Interceptor（context_filter_interceptor.py）
4. 从 YAML 中移除新增配置块（hierarchies/context/cascade_select/annotations）
5. 从 MetaObject 中移除新增字段

## 10. TBD 列表

| ID | 项目 | 决策 | 依据 |
|----|------|------|------|
| TBD-1 | `scope_rules` 模型方案 | **YAML 声明 + ref 引用 + 双引擎（SQL/Python）** — 已实现核心机制，本阶段仅验证引用正确性 | hierarchies.yaml 已定义 4 种 hierarchy_scopes，relationship.yaml 通过 scope_rules_ref 引用 |
| TBD-2 | 异步导入线程池 | **单线程** — 数据导入当前为同步单线程，异步方案为单 worker 线程串行处理各 Sheet | SQLite 库级写锁不适合多线程并发写；审计日志的 ThreadPoolExecutor 仅用于审计写入，不用于数据导入 |
| TBD-3 | `product/version` 是否需要 `owner_id` | **需要** — 与 domain 及以下对齐 | 用户确认 |
| TBD-4 | `domain/sub_domain/service_module` 是否需要 `description` | **需要** — 与 product/version/business_object 对齐 | 用户确认 |
| TBD-5 | 备注分类是否支持自定义 | **已支持** — 通过 `enum_values` 表（`enum_type_id='annotation_category'`）动态管理，YAML categories 作为初始化种子 | `_get_annotation_category_labels()` 直接查 enum_values 表，天然 extensible |
| TBD-6 | scope_rules Python 引擎通用化 | **延后到 GAP-3** — `cascade_service._evaluate_scope_rule()` 当前为硬编码 if/elif，通用规则解释器随 GAP-3 一起实现 | 本阶段仅验证引用机制，通用化非 Must |
| TBD-7 | scope_rules SQL 查询通用化 | **延后到 GAP-3** — `meta_api._get_category_pair_sqls()` 当前为 4 段硬编码 SQL，动态生成随 GAP-3 一起实现 | 本阶段仅验证引用机制，通用化非 Must |

Spec + RFC contain 10 sections, last section is "TBD List", content is complete.

---

## Spec + RFC 确认请求

我已完成上述 Spec 和 RFC。请确认以下内容：

### 1. 授权

- [ ] 您是否接受此 Spec + RFC？
- [ ] 您是否授权立即开始开发？

### 2. TBD 项目澄清

- TBD-1: `scope_rules` 的分类条件是否需要支持自定义表达式？还是固定 4 种分类即可？
- TBD-2: 异步导入的线程池大小？单线程还是多线程？
- TBD-3: `product/version` 是否需要添加 `owner_id` 字段？
- TBD-4: `domain/sub_domain/service_module` 是否需要添加 `description` 字段？
- TBD-5: 备注分类是否需要支持自定义？还是固定 4 种？

### 3. 补充信息

如果您觉得 Spec 或 RFC 中有任何信息不完整或需要补充，请在"补充信息"中提供。

💡 如果您觉得当前问题不足以澄清需求，欢迎在"补充信息"中提供任何相关信息。
