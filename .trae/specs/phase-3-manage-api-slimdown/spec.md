# Phase 3: manage_api.py 瘦身与 API 统一迁移

## 1. 概述

### 1.1 问题陈述

`manage_api.py` 当前包含 **1948 行**代码、**29 个路由**，运行在 `/api/v1` 前缀下。随着 BOFramework（`bo_api.py`, `/api/v2/bo`）的成熟，manage_api.py 成为遗留瓶颈：

- 18 处 `print()` 调试语句残留
- 2 个已弃用函数体仍在文件中
- 850 行标准 CRUD 路由在 v2 API 已有等价实现
- 1100 行特殊业务路由（关系查询、注解、审计管理、元数据、分析）散落在单一文件中
- 前端约 **80+ 处仍引用 `/api/v1/`** 端点

### 1.2 目标

| 指标 | 当前 | 目标 |
|------|------|------|
| manage_api.py 行数 | 1948 | ≤500 |
| 调试语句 | 18 处 | 0 处 |
| 弃用函数 | 2 个 | 0 个 |
| 标准 CRUD 路由 | 仍在服务 | 返回 410 Gone |
| 特殊路由 | 散落单文件 | 拆分至 4 个独立 Blueprint |
| 前端 v1 API 残留 | ~80 处 | 分类处理（迁移或确认保留） |

### 1.3 引用关系

- **前置 Spec**: [unified-metadata-api-architecture/spec.md](file:///d:/filework/excel-to-diagram/.trae/specs/unified-metadata-api-architecture/spec.md) — 本 Phase 3 属于此前置 Spec 中的 Phase 3
- **前置 Spec**: [platform-architecture-gap-roadmap/spec.md](file:///d:/filework/excel-to-diagram/.trae/specs/platform-architecture-gap-roadmap/spec.md) — 架构缺失要素路线图，Phase 19+ 之后的工作

---

## 2. 前端 v1 API 引用审计报告

### 2.1 审计结论

> **前端并非完全迁移到 v2 API**。13 个标准 CRUD 页面已使用 MetaListPage + boService（正确模式），但仍有 **~80 处 `/api/v1/` 引用**分布在权限管理、账户设置、枚举查询、元数据查询、关系查询、导入导出等模块。

### 2.2 已迁移（v2 API 正确模式）的页面 — 13 个

这些页面使用 MetaListPage → boService → `/api/v2/bo`，**标准 CRUD 路由可以安全废弃**：

| 页面 | 对象类型 |
|------|---------|
| UserManagement.vue | user |
| RoleManagement.vue | role |
| UserGroupManagement.vue | user_group |
| ProductManagement.vue | product |
| VersionManagement.vue | version |
| EnumValueManagement.vue | enum_value |
| DomainManagement.vue | domain |
| SubDomainManagement.vue | sub_domain |
| ServiceModuleManagement.vue | service_module |
| BusinessObjectManagement.vue | business_object |
| AuditLogManagement.vue | audit_log |
| GenericObjectList.vue | 任意 object_type |
| EnumValueList.vue | enum_value |

### 2.3 v1 API 残留引用 — 按模块分类

#### 2.3.1 权限管理组件（阻止迁移的最大障碍）

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [RoleDetailDrawer.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/RoleDetailDrawer.vue) | `/api/v1/roles/*`, `/api/v1/permission-rules/*`, `/api/v1/meta/objects` | 6+ | 🔄 权限规则非 v2 CRUD |
| [RolePermissionCenter.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/RolePermissionCenter.vue) | `/api/v1/roles/*`, `/api/v1/management-dimensions` | 7+ | 🔄 权限分配非 v2 CRUD |
| [ConditionRuleDialog.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/ConditionRuleDialog.vue) | `/api/v1/permission-rules/*` | 6+ | 🔄 条件规则非 v2 CRUD |
| [DataPermissionConfig.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/DataPermissionConfig.vue) | `/api/v1/roles`, `/api/v1/permission-rules/*` | 3+ | 🔄 数据权限配置 |
| [DimensionScopePanel.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/DimensionScopePanel.vue) | `/api/v1/management-dimensions` | 5+ | 🔄 维度非 v2 CRUD |
| [AddPermissionDialog.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/AddPermissionDialog.vue) | `/api/v1/meta/objects`, `/api/v1/user-groups/*/data-permissions` | 3+ | 🔄 |
| [BatchDataPermDialog.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/BatchDataPermDialog.vue) | `/api/v1/users`, `/api/v1/users/batch-data-permissions` | 2 | 🔄 |

**分析**: 这些组件调用的是权限规则、管理维度、数据权限分配等特殊业务 API，**不是标准对象 CRUD**。当前 v2 API 未提供这些端点。需要保留 manage_api.py 中对应路由。

#### 2.3.2 账户设置

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [AccountSettings/index.vue](file:///d:/filework/excel-to-diagram/src/views/AccountSettings/index.vue) | `/api/v1/users/me`, `/api/v1/auth/change-password` | 3 | ❌ v2 无此路由 |
| [AccountSettingsDialog.vue](file:///d:/filework/excel-to-diagram/src/components/AccountSettingsDialog.vue) | `/api/v1/users/me`, `/api/v1/auth/change-password` | 3 | ❌ v2 无此路由 |

**分析**: `/users/me` 和 `/auth/change-password` 不属于 manage_api.py 管理范围（属于 auth 模块），不阻止 manage_api 瘦身。

#### 2.3.3 枚举查询

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [enumService.js](file:///d:/filework/excel-to-diagram/src/services/enumService.js) | `/api/v1/enums/*`, `/api/v1/enum-types/*` | 3 | 🔄 v2 通过 `/api/v2/bo/enum_value?filters=...` 可替代，但需改造查询参数 |
| [EnumSearchHelp.vue](file:///d:/filework/excel-to-diagram/src/components/common/EnumSearchHelp.vue) | `/api/v1/enum-types/{type}/values` | 1 | 🔄 同上 |
| [AnnotationList.vue](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/components/AnnotationList.vue) | `/api/v1/enum-types/annotation_category/values` | 1 | 🔄 同上 |
| [DynamicDetail.vue](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/components/DynamicDetail.vue) | `/api/v1/enum-types/relation_type/values` | 1 | 🔄 同上 |

**分析**: 枚举查询可通过 v2 `/api/v2/bo/enum_value?filters=...` 替代，但需要后端添加枚举值列表查询优化（当前 v2 query 不支持按 enum_type_id 高效过滤）。**不改 enum 查询就阻止 manage_api.py 完全删除此路由。**

#### 2.3.4 元数据查询

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [objectTypeService.js](file:///d:/filework/excel-to-diagram/src/services/objectTypeService.js) | `/api/v1/meta/objects` | 1 | ❌ v2 无此路由 |
| [hierarchyFilterBuilder.js](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/utils/hierarchyFilterBuilder.js) | `/api/v1/meta/hierarchies/config` | 1 | ❌ v2 无此路由 |
| [ArchDataManageApp/index.vue](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/index.vue) | `/api/v1/meta/objects` | 1 | ❌ v2 无此路由 |
| [DynamicDetail.vue](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/components/DynamicDetail.vue) | `/api/v1/meta/objects` | 1 | ❌ v2 无此路由 |
| [useViewConfig.js](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/composables/useViewConfig.js) | `/api/v1/meta/domain/view-config` | 1 | ❌ v2 无此路由 |
| [useI18n.js](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/composables/useI18n.js) | `/api/v1/meta/i18n` | 1 | ❌ v2 无此路由 |

**分析**: 元数据查询端点（`/meta/objects`, `/meta/hierarchies/config`, `/meta/i18n`）是系统自省 API，并非标准对象 CRUD。v2 API 目前无这些端点，需要保留。其中 `/meta/objects` 有 **4 处调用**。

#### 2.3.5 关系查询

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [RelationScopeSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/RelationScopeTree/RelationScopeSection.vue) | `/api/v1/relationships` | 1 | ❌ v2 无此复杂 JOIN 查询 |

#### 2.3.6 导入导出

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [useImportExportApi.js](file:///d:/filework/excel-to-diagram/src/composables/useImportExportApi.js) | `/api/v1/import`, `/api/v1/export`, `/api/v1/import/async`, `/api/v1/import/template`, `/api/v1/import-export/config` | 8+ | ❌ v2 无批量导入导出端点 |

#### 2.3.7 审计管理

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) | `/api/v1/users?size=1000` | 1 | 🔄 可替换为 v2 query |
| [auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) | `/api/v1/audit` | 1 | ❌ v2 无审计管理端点 |

#### 2.3.8 产品/版本元数据配置

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [entityMeta.js](file:///d:/filework/excel-to-diagram/src/views/ProductVersionApp/meta/entityMeta.js) | `apiBase: '/api/v1/product'`, `apiBase: '/api/v1/version'` | 2 | ✅ 可替换为 v2 |

#### 2.3.9 死代码（已确认可安全删除）

| 文件 | v1端点 | 说明 |
|------|--------|------|
| [EnumTypeCreate.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/EnumTypeCreate.vue) | `/api/v1/enum-types` | 🗑️ 死代码，无任何组件导航到此路由。enum_type 创建已由 MetaListPage enable-auto-crud → DetailPage Drawer 替代 |
| [EnumValueManagement.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/EnumValueManagement.vue) | — | 🗑️ 死代码，无任何组件导航到此路由。enum_value 作为 child_of enum_type，通过 DetailPage association tab 渲染 |
| [EnumValueFormDialog.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/EnumValueFormDialog.vue) | `/api/v1/bo/enum_value/*` | 🗑️ 死代码，仅 EnumValueManagement.vue 使用。EnumValueList.vue 已用 MetaListPage enable-auto-crud |

#### 2.3.10 其他残留

| 文件 | v1端点 | 调用数 | v2可替代? |
|------|--------|--------|----------|
| [UserPermissionSummary.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/UserPermissionSummary.vue) | `/api/v1/meta/objects` | 1 | ❌ v2 无此路由 |
| [useChangeNotification.js](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/composables/useChangeNotification.js) | `/api/v1/notifications/ws` (WS) | 1 | ❌ WebSocket，非 REST |

---

## 3. 功能需求

### FR-001: 清理调试语句和弃用代码

**优先级**: P0（即刻执行，零风险）

**描述**: 删除 manage_api.py 中所有 `print()` 调试语句、无意义 `logger.info()` 调用、以及已弃用的空函数体。

**清单**:
- 第 204 行：`print(f"[ScopeFilter] User has data permissions...")`
- 第 220-232 行：5 处 `print(f"[DataPermFilter]...")`
- 第 507, 510, 524, 539 行：4 处 `print(f"[DEBUG] list_records...")`
- 第 784, 806 行：2 处 `logger.info(f"[DELETE]...")`
- 第 886, 992, 998 行：3 处 `print(f"[RelationshipPerm]...")`
- 第 468-477 行：`_enrich_relationship_data()` — 弃用函数，删除函数体
- 第 480-489 行：`_enrich_record_with_names()` — 弃用函数，删除函数体

**验收标准**:
- [ ] 18 处调试语句全部清理
- [ ] 2 个弃用函数全部删除
- [ ] 文件行数从 1948 减至 ~1850

### FR-002: 废弃标准 CRUD 路由并添加 410 重定向

**优先级**: P0

**描述**: 已确认 13 个前端页面全部使用 MetaListPage + boService → v2 API，manage_api.py 中的标准 CRUD 路由可以安全废弃。

**待废弃路由**:
- `POST /<object_type>` — 创建对象
- `GET /<object_type>/<id>` — 读取对象
- `GET /<object_type>` — 列表查询
- `PUT /<object_type>/<id>` — 更新对象
- `DELETE /<object_type>/<id>` — 删除对象
- `POST /<object_type>/deep` — 深度插入
- `POST /<object_type>/batch-create` — 批量创建
- `POST /<object_type>/batch-update` — 批量更新
- `POST /<object_type>/batch-delete` — 批量删除
- `GET /<object_type>/<id>/actions` — 获取操作列表
- `POST /<object_type>/<id>/actions/<action_id>` — 执行操作

**废弃策略**: 非立即删除，而是返回 `410 Gone` + 迁移提示，提供 90 天过渡期。

```python
# 每个废弃路由替换为:
@manage_bp.route('/<object_type>', methods=['POST'])
def create_record(object_type):
    return jsonify({
        'error': 'API Moved',
        'message': f'POST /api/v1/{object_type} has moved to POST /api/v2/bo/{object_type}',
        'migrated_at': '2026-05-15',
        'sunset_at': '2026-08-15'
    }), 410
```

**验收标准**:
- [ ] 11 个标准 CRUD 路由全部返回 410 Gone
- [ ] 响应体包含迁移提示和新端点路径
- [ ] 现有前端 13 个页面功能不受影响（已使用 v2 API）

### FR-003: 前端死代码清理 + 低风险文件切换到 v2 API

**优先级**: P0

经过深入审计，发现 EnumTypeCreate.vue 和 EnumValueManagement.vue + EnumValueFormDialog.vue 已被标准 MetaListPage + DetailPage 模式替代，属于死代码。

#### FR-003a: 删除已替代的旧页面（死代码清理）

| 文件 | 废弃原因 | 替代方案 |
|------|---------|---------|
| [EnumTypeCreate.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/EnumTypeCreate.vue) | 无任何组件导航到 `/business-config/enums/create` | MetaListPage enable-auto-crud → DetailPage Drawer |
| [EnumValueManagement.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/EnumValueManagement.vue) | 无任何组件导航到 `/business-config/enums/:id/values` | enum_value 作为 child_of enum_type，通过 DetailPage association tab 渲染 |
| [EnumValueFormDialog.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/EnumValueFormDialog.vue) | 仅 EnumValueManagement.vue 使用 | EnumValueList.vue 已用 MetaListPage enable-auto-crud |

**清理操作**:
1. 删除 `EnumTypeCreate.vue` 文件
2. 删除 `EnumValueManagement.vue` 文件
3. 删除 `EnumValueFormDialog.vue` 文件
4. 删除对应测试文件：`EnumTypeCreate.spec.js`, `EnumValueManagement.spec.js`
5. 从 router 删除 `/business-config/enums/create` 和 `/business-config/enums/:id/values` 路由

#### FR-003b: 低风险文件切换到 v2 API

| 文件 | 当前 v1 端点 | 替换为 v2 端点 | 风险 |
|------|------------|-------------|------|
| [entityMeta.js](file:///d:/filework/excel-to-diagram/src/views/ProductVersionApp/meta/entityMeta.js) | `apiBase: '/api/v1/product'` | `apiBase: '/api/v2/bo/product'` | 低 |
| [entityMeta.js](file:///d:/filework/excel-to-diagram/src/views/ProductVersionApp/meta/entityMeta.js) | `apiBase: '/api/v1/version'` | `apiBase: '/api/v2/bo/version'` | 低 |
| [auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) | `apiUrl: '/api/v1/users?size=1000'` | `/api/v2/bo/user?page_size=1000` | 低 |

**验收标准**:
- [ ] 3 个死代码文件 + 2 个测试文件被删除
- [ ] 2 个旧路由从 router 移除
- [ ] 3 处 v1 API 引用替换为 v2
- [ ] 功能测试通过，无回退

### FR-004: 拆分特殊业务路由到独立 Blueprint

**优先级**: P0

将 manage_api.py 中 1100 行特殊业务路由拆分为 4 个独立文件：

```
meta/api/
├── manage_api.py               (目标 ≤500行，保留辅助函数 + 410重定向)
├── special_routes_api.py        (新增，关系查询 + 分析查询)
├── annotation_routes_api.py     (新增，注解 CRUD)
├── audit_management_api.py      (新增，审计管理)
└── meta_utility_routes_api.py   (新增，元数据自省)
```

#### FR-004a: special_routes_api.py

**路由**:
- `GET/POST /api/v1/relationships` — 复杂关系查询（6表 JOIN）
- `GET /api/v1/business_object/<id>/relations` — 关系详情 + Enrichment
- `POST /api/v1/analytics/<object_type>` — 分析聚合查询

**迁移代码量**: ~650 行

#### FR-004b: annotation_routes_api.py

**路由**:
- `GET /api/v1/annotations/by-target` — 注解按目标查询
- `GET /api/v1/annotations/<id>` — 获取注解详情
- `POST /api/v1/annotations` — 创建注解
- `PUT /api/v1/annotations/<id>` — 更新注解
- `DELETE /api/v1/annotations/<id>` — 删除注解
- `GET /api/v1/annotations/category-stats` — 注解分类统计

**迁移代码量**: ~190 行

#### FR-004c: audit_management_api.py

**路由**:
- `GET /api/v1/audit/failed` — 失败审计日志
- `POST /api/v1/audit/failed/<id>/retry` — 审计重试
- `GET /api/v1/audit/stats` — 审计统计

**迁移代码量**: ~60 行

#### FR-004d: meta_utility_routes_api.py

**路由**:
- `GET /api/v1/meta/objects` — 元对象列表 + 层级信息
- `GET /api/v1/meta/hierarchies` — 层级配置查询
- `GET /api/v1/meta/hierarchies/<id>/levels` — 层级级别查询
- `GET /api/v1/meta/hierarchies/config` — 层级配置详情
- `GET /api/v1/meta/objects/<object_type>/field_controls` — 字段控制配置

**迁移代码量**: ~180 行

**验收标准**:
- [ ] 4 个新 Blueprint 文件创建完成
- [ ] 所有路由功能测试通过
- [ ] server.py 注册新 Blueprint
- [ ] manage_api.py 中对应代码被删除或注释

### FR-005: manage_api.py 最终清理

**优先级**: P0

在 FR-001 ~ FR-004 完成后：

1. 保留在 manage_api.py 的代码：
   - `init_services()` — 服务初始化（简化版）
   - 工具函数：`_apply_scope_filter()`, `_apply_data_permission_filter()`, `_set_audit_user()`, `_api_error()`, `_api_success()`
   - 部分权限管理路由（role/permission-rule/management-dimension 相关，这些目前无法迁移到 v2）
   - 枚举查询特殊路由（`/enums/*`, `/enum-types/*` — 待前端 enumService 迁移后移除）
   - 410 Gone 重定向路由

2. 目标行数：≤500 行

**验收标准**:
- [ ] manage_api.py 行数 ≤500
- [ ] 所有保留路由功能正常
- [ ] 4 个新 Blueprint 文件功能正常
- [ ] 现有测试全部通过

---

## 4. 非功能需求

### NFR-001: 调试语句清理
所有 `print()` 语句必须删除。有业务意义的日志保留但改用 `logger.debug()`。

### NFR-002: 路由废弃过渡期
标准 CRUD 路由废弃后提供 90 天过渡期（返回 410 + 提示），90 天后可彻底删除代码。

### NFR-003: 向后兼容
拆分后的特殊路由保持完全一致的URL路径和请求/响应格式，前端零改动即可运行。

---

## 5. 外部接口

### IF-001: 标准 CRUD 路由废弃后的 410 响应格式

```json
{
  "error": "API Moved",
  "message": "POST /api/v1/{object_type} has moved to POST /api/v2/bo/{object_type}",
  "migrated_at": "2026-05-15",
  "sunset_at": "2026-08-15"
}
```

### IF-002: 新 Blueprint 注册（server.py）

```python
from meta.api.special_routes_api import special_bp
from meta.api.annotation_routes_api import annotation_bp
from meta.api.audit_management_api import audit_mgmt_bp
from meta.api.meta_utility_routes_api import meta_util_bp

app.register_blueprint(special_bp)
app.register_blueprint(annotation_bp)
app.register_blueprint(audit_mgmt_bp)
app.register_blueprint(meta_util_bp)
```

---

## 6. 实施计划

### 6.1 里程碑

| 里程碑 | 内容 | 工时 | 依赖 |
|--------|------|------|------|
| M1 | FR-001: 清理调试语句和弃用函数 | 0.5天 | 无 |
| M2 | FR-002: 废弃标准 CRUD 路由 + 410 重定向 | 0.5天 | M1 |
| M3 | FR-003a: 删除死代码（3个Vue + 2个测试 + 2个路由） | 0.5天 | M2 |
| M4 | FR-003b: 前端低风险文件切换到 v2 | 0.5天 | M3 |
| M5 | FR-004a: 拆分 relationship + analytics 路由 | 2天 | M2 |
| M6 | FR-004b: 拆分 annotation 路由 | 1天 | M2 |
| M7 | FR-004c: 拆分 audit 管理路由 | 0.5天 | M2 |
| M8 | FR-004d: 拆分 meta_utility 路由 | 0.5天 | M2 |
| M9 | FR-005: manage_api.py 最终清理 | 0.5天 | M4-M8 |
| M10 | 回归测试 + 文档更新 | 0.5天 | M9 |

**总计: 7 天**

### 6.2 后续计划（本 Phase 范围外）

以下前端残留引用在本次 Phase 3 中暂不处理，记录为后续工作：

| 模块 | 残留数量 | 优先级 | 建议 Phase |
|------|---------|--------|-----------|
| 权限管理组件（7个文件） | ~30 处 | P1 | Phase 3.1 |
| 账户设置（2个文件） | 6 处 | P1 | Phase 3.2 |
| 枚举查询（4个文件） | 6 处 | P1 | Phase 3.3 |
| 元数据查询（6个文件） | 5 处 | P1 | Phase 3.4 |
| 导入导出（1个文件） | 8 处 | P1 | Phase 3.5 |
| 审计元数据配置 | 1 处 | P2 | Phase 3.6 |
| WebSocket 通知 | 1 处 | P2 | Phase 3.7 |

---

## 7. 风险矩阵

| 风险 | 严重度 | 概率 | 缓解措施 |
|------|--------|------|---------|
| 前端有隐含的 v1 CRUD 调用未被审计发现 | 高 | 低 | M2 后 monitor 410 响应日志，发现异常立即回滚 |
| 特殊路由拆分时引入 Bug | 中 | 中 | 每个 Blueprint 独立测试后再合并 |
| 权限管理路由迁移复杂度超标 | 中 | 高 | 本 Phase 不动权限路由，保留在 manage_api.py |
| 枚举查询前端迁移需改造 enumService.js | 中 | 中 | 本 Phase 不动，记录为 Phase 3.3 后续 |
| `version.is_current` 唯一性校验丢失 | 高 | 低 | 该逻辑已在 ConstraintEngine 补充，确认后移除硬编码 |

---

## 8. 优先级

| FR | 优先级 | 理由 |
|----|--------|------|
| FR-001 | Must | 代码卫生，零风险 |
| FR-002 | Must | 核心目标，已确认前端就绪 |
| FR-003a | Must | 死代码清理，零风险 |
| FR-003b | Must | 低风险立即迁移 |
| FR-004 | Must | 核心目标，代码结构优化 |
| FR-005 | Must | 最终目标 |

---

## 9. TBD 列表

| ID | 待定事项 | 决策建议 |
|----|---------|---------|
| TBD-1 | `version.is_current` 唯一性校验是否已在 ConstraintEngine 实现？ | 需要确认后端代码 |
| TBD-2 | 权限管理路由（role/permission-rule/management-dimension）后续是否迁移到 v2 权限专用 API？ | 建议 Phase 3.1 后创建独立的 permission_api.py |
| TBD-3 | `/meta/objects` 等元数据端点是否应该合并到 v2 `/api/v2/meta` 前缀？ | 建议后续统一到 `/api/v2/meta/` |
| TBD-4 | 410 过渡期结束后（2026-08-15），是否需要保留路由还是彻底删除？ | 建议 90 天后彻底删除 |
