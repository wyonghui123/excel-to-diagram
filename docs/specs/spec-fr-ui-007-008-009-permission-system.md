## 目录

1. [0. 抽取理由](#0-抽取理由)
2. [1. 背景与目标](#1-背景与目标)
3. [2. 现状深度分析](#2-现状深度分析)
4. [3. 目标架构](#3-目标架构)
5. [4. FR-UI-007：permissionService.js](#4-fr-ui-007：permissionservicejs)
6. [5. FR-UI-008：conditionExpressionService.js](#5-fr-ui-008：conditionexpressionservicejs)
7. [6. FR-UI-009：Vue 组件重构](#6-fr-ui-009：vue-组件重构)
8. [7. 实施计划](#7-实施计划)
9. [8. 风险与缓解](#8-风险与缓解)
10. [附录 A：条件表达式 DSL EBNF](#附录-a：条件表达式-dsl-ebnf)
11. [附录 B：操作符优先级](#附录-b：操作符优先级)

---
# Spec 子文档: PR 8-10 FR-UI-007/008/009 权限系统下沉

> **版本**: v1.0.0
> **日期**: 2026-06-06
> **状态**: 📋 Designed — 待实施
> **范围**: 从 [spec-ui-business-logic-downflow.md v2.0.2](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) 拆出**独立子 spec**
> **适用 PR**: PR 8-10（FR-UI-007/008/009）
> **父 spec**: [spec-ui-business-logic-downflow.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) §4 FR-UI-007/008/009

---

## 0. 抽取理由

父 spec v2.0.2 涵盖 15 个 FR，FR-UI-007/008/009 这 3 个 P1 项聚焦在**权限系统**的 service 层下沉。拆分理由：

1. **影响面广**：涉及 7 个 Vue 组件、23 个 API 端点、8 类重复业务逻辑
2. **逻辑闭环**：permissionService → conditionExpressionService → Vue 重构，形成完整依赖链
3. **与 Track A 无依赖**：可独立实施、独立验收
4. **重复代码严重**：权限级别标签、资源类型标签、条件表达式生成/解析等在 2-5 个组件中重复

---

## 1. 背景与目标

### 1.1 现状痛点

| 维度 | 现状 | 目标 |
|------|------|------|
| **fetch() 调用** | 7 个组件共 **30 处** | 0 处 |
| **重复业务逻辑** | 8 类重复（见 §1.2） | 0 类重复 |
| **可单测函数** | 0（全在 .vue 中） | ~30（全部在 service） |
| **权限级别标签** | 5 处定义，值不一致 | 1 处定义（permissionService） |
| **条件表达式 DSL** | 2 处重复实现 | 1 处（conditionExpressionService） |

### 1.2 重复业务逻辑清单

| # | 重复逻辑 | 重复组件数 | 行数估算 |
|---|---------|-----------|---------|
| 1 | `getHeaders()` 认证头构造 | 6 | 6×5=30 |
| 2 | 权限级别标签映射 `LEVEL_LABELS` / `getPermissionLevelLabel()` | 5 | 5×8=40 |
| 3 | 资源类型标签映射 `RESOURCE_LABELS` / `getResourceLabel()` | 4 | 4×10=40 |
| 4 | 条件表达式生成 `updateCondition()` | 2 | 2×30=60 |
| 5 | 条件表达式解析 `parseConditionToDimConfigs()` | 2 | 2×65=130 |
| 6 | 友好描述生成 `getFriendlyCondition()` / `generateSimpleFriendly()` | 2 | 2×60=120 |
| 7 | 维度加载 `loadDimensions()` | 3 | 3×12=36 |
| 8 | Value Help 加载 `loadValueHelp()` | 2 | 2×40=80 |

### 1.3 三个 FR 的目标分解

| FR | 目标 | 关键交付物 |
|----|------|----------|
| **FR-UI-007** | `permissionService.js` 创建 | 6 个 API 函数 + 4 个纯函数 + 15 单测 |
| **FR-UI-008** | `conditionExpressionService.js` 创建 | 6 个函数（含 DSL 解析器）+ 25 单测 |
| **FR-UI-009** | 7 个 Vue 组件重构 | 消除 30 处 fetch + 8 类重复逻辑 |

### 1.4 成功标准

| # | 衡量项 | 现状 | 目标 | 验收方式 |
|---|--------|------|------|---------|
| 1 | 权限相关 .vue 中 `fetch()` 调用 | 30 | **0** | `grep -rn "fetch(" src/views/SystemManagement/` |
| 2 | 权限相关 .vue 中 `getHeaders()` 定义 | 6 | **0** | grep |
| 3 | `LEVEL_LABELS` 定义数 | 5 | **1**（在 permissionService） | grep |
| 4 | `updateCondition()` 实现数 | 2 | **1**（在 conditionExpressionService） | grep |
| 5 | `parseConditionToDimConfigs()` 实现数 | 2 | **1**（在 conditionExpressionService） | grep |
| 6 | `RolePermissionCenter.vue` 行数减少 | - | ≥ 20% | `wc -l` |
| 7 | `ConditionRuleDialog.vue` 行数减少 | - | ≥ 30% | `wc -l` |
| 8 | 权限功能行为不变 | - | **100%** | E2E 测试 |

---

## 2. 现状深度分析

### 2.1 API 端点清单（23 个）

#### 角色管理

| API 端点 | 组件 | 方法 |
|----------|------|------|
| `/api/v1/roles` | DataPermissionConfig | GET |
| `/api/v1/roles/:id` | RolePermissionCenter | GET |
| `/api/v1/roles/:id/permission-rules` | RolePermissionCenter | GET, POST |
| `/api/v1/roles/:id/permission-rules/:ruleId` | RolePermissionCenter | PUT, PATCH, DELETE |
| `/api/v1/roles/:id/permission-rules/batch` | RolePermissionCenter | POST |
| `/api/v1/roles/:id/calculate-impact` | RolePermissionCenter | POST |
| `/api/v1/roles/:id/unified-permissions` | RoleDetailDrawer | GET |
| `/api/v1/roles/:id/menu-permissions` | RoleDetailDrawer | PUT |
| `/api/v1/roles/:id/dimension-scopes` | DimensionScopePanel | GET, POST |
| `/api/v1/roles/:id/derived-permissions` | DimensionScopePanel | GET |
| `/api/v1/roles/:id/overlaps` | ConditionRuleDialog | GET |

#### 条件规则

| API 端点 | 组件 | 方法 |
|----------|------|------|
| `/api/v1/permission-rules` | DataPermissionConfig, ConditionRuleDialog | GET, POST |
| `/api/v1/permission-rules/:id` | RoleDetailDrawer, DataPermissionConfig | DELETE |
| `/api/v1/permission-rules/preview` | ConditionRuleDialog | POST |
| `/api/v1/permission-rules/field-metadata` | ConditionRuleDialog | GET |
| `/api/v1/permission-rules/dimensions/:code/values` | ConditionRuleDialog | GET |

#### 维度管理

| API 端点 | 组件 | 方法 |
|----------|------|------|
| `/api/v1/management-dimensions` | RolePermissionCenter, ConditionRuleDialog, DimensionScopePanel | GET |
| `/api/v1/management-dimensions/:id/fields` | RolePermissionCenter | GET |
| `/api/v1/management-dimensions/:id/instances` | DimensionScopePanel | GET |

#### 其他

| API 端点 | 组件 | 方法 |
|----------|------|------|
| `/api/v1/meta/objects` | RoleDetailDrawer, AddPermissionDialog, UserPermissionSummary | GET |
| `/api/v1/users` | BatchDataPermDialog | GET |
| `/api/v1/users/batch-data-permissions` | BatchDataPermDialog | POST |
| `/api/v1/user-groups/:groupId/data-permissions` | AddPermissionDialog | POST |

### 2.2 组件级 fetch 分布

| 组件 | fetch 数 | 行数 | 核心业务函数 |
|------|---------|------|-------------|
| **RolePermissionCenter.vue** | 8 | ~600 | `getDimensionName`, `getPermissionLevelType/Label`, `loadPermissionRules`, `handleRuleSubmit`, `handleSave` |
| **ConditionRuleDialog.vue** | 8 | ~1100 | `updateCondition`, `getFriendlyCondition`, `generateSimpleFriendly`, `parseConditionToDimConfigs`, `sortedDimensions` |
| **RoleDetailDrawer.vue** | 5 | ~530 | `getPermLevelLabel`, `loadUnifiedPermissions`, `saveUnifiedPermissions` |
| **DimensionScopePanel.vue** | 5 | ~500 | `loadDimensions`, `loadDimensionScopes`, `saveDimensionScopes`, `autoDerive`, 级联逻辑 |
| **DataPermissionConfig.vue** | 3 | ~300 | `getResourceLabel`, `getPermLevelLabel` |
| **BatchDataPermDialog.vue** | 2 | ~140 | `searchUsers`, `submit` |
| **AddPermissionDialog.vue** | 3 | ~350 | `loadObjectTypes`, `loadResources`, `handleSubmit` |
| **UserPermissionSummary.vue** | 1 | ~160 | `getResourceLabel`（纯展示） |
| **总计** | **35** | **~3680** | — |

> 注：实际 `fetch()` 调用 30 处，另有 5 处通过 `apiV1()` 已封装。

### 2.3 条件表达式 DSL 现状

**生成方**（ConditionRuleDialog.vue `updateCondition()` L462-491）：

```
输入: dimConfigs = [{dim: 'domain_id', op: '=', value: 5}, {dim: 'status', op: 'IN', value: ['active', 'draft']}]
输出: "domain_id = 5 AND status IN ('active', 'draft')"
```

- 支持操作符：`=`, `!=`, `IN`, `NOT IN`, `LIKE`, `>`, `>=`, `<`, `<=`
- 多条件用 `AND` 连接
- 字符串值加引号，数值不加

**解析方**（ConditionRuleDialog.vue `parseConditionToDimConfigs()` L959-1024）：

- 解析 `field IN (v1, v2)` → `{dim, op: 'IN', value: [v1, v2]}`
- 解析 `field = value` / `field != value`
- 按 `AND` 分割多条件
- 无法匹配时回退到自定义条件模式

**重复实现**：ConditionRuleEditor.vue 中有几乎相同的 `updateCondition()` 和 `parseConditionToDimConfigs()`。

---

## 3. 目标架构

### 3.1 Service 层设计

```
┌─────────────────────────────────────────────────────────┐
│                    Vue 组件层                            │
│  RolePermissionCenter / ConditionRuleDialog / ...        │
│  职责：UI 事件绑定、对话框开关、loading/error 状态         │
└──────────────┬──────────────────────┬───────────────────┘
               │                      │
       ┌───────▼───────┐      ┌──────▼──────────┐
       │permissionService│      │conditionExpression│
       │                │      │Service            │
       │ API 函数 (6)   │      │ 纯函数 (6)        │
       │ 纯函数 (4)     │      │ - buildCondition  │
       │ - getLevelLabel│      │ - translate      │
       │ - getLevelType │      │ - parse          │
       │ - getResLabel  │      │ - sort/filter    │
       │ - getDimName   │      │ - validate       │
       └───────┬────────┘      └──────────────────┘
               │
       ┌───────▼────────┐
       │  httpClient     │
       │  apiV1.get/post │
       └────────────────┘
```

### 3.2 依赖关系

```
FR-UI-007 (permissionService) ← 依赖 FR-UI-001 (httpClient) ✅
FR-UI-008 (conditionExpressionService) ← 无外部依赖（纯函数）
FR-UI-009 (Vue 重构) ← 依赖 FR-UI-007 + FR-UI-008
```

---

## 4. FR-UI-007：permissionService.js

### 4.1 API 函数（6 个，调用 httpClient.apiV1）

```javascript
// src/services/permissionService.js

import { apiV1 } from '@/utils/httpClient'

/**
 * 加载角色列表
 * @param {object} [params] - 查询参数
 * @returns {Promise<ApiResponse>}
 */
export async function loadRoles(params = {}) {
  return apiV1.get('/roles', { params })
}

/**
 * 加载角色详情
 * @param {number} roleId
 * @returns {Promise<ApiResponse>}
 */
export async function loadRole(roleId) {
  return apiV1.get(`/roles/${roleId}`)
}

/**
 * 加载角色的权限规则
 * @param {number} roleId
 * @param {object} [params] - 查询参数
 * @returns {Promise<ApiResponse>}
 */
export async function loadPermissionRules(roleId, params = {}) {
  return apiV1.get(`/roles/${roleId}/permission-rules`, { params })
}

/**
 * 保存权限规则（新建 / 编辑 / 批量）
 * @param {number} roleId
 * @param {object} rule - 规则数据
 * @param {'create'|'update'|'batch'} mode
 * @returns {Promise<ApiResponse>}
 */
export async function savePermissionRules(roleId, rule, mode = 'create') {
  if (mode === 'batch') {
    return apiV1.post(`/roles/${roleId}/permission-rules/batch`, rule)
  }
  if (mode === 'update' && rule.id) {
    return apiV1.put(`/roles/${roleId}/permission-rules/${rule.id}`, rule)
  }
  return apiV1.post(`/roles/${roleId}/permission-rules`, rule)
}

/**
 * 删除权限规则
 * @param {number} roleId
 * @param {number} ruleId
 * @returns {Promise<ApiResponse>}
 */
export async function deletePermissionRule(roleId, ruleId) {
  return apiV1.delete(`/roles/${roleId}/permission-rules/${ruleId}`)
}

/**
 * 切换规则启用/禁用
 * @param {number} roleId
 * @param {number} ruleId
 * @param {boolean} enabled
 * @returns {Promise<ApiResponse>}
 */
export async function toggleRuleStatus(roleId, ruleId, enabled) {
  return apiV1.patch(`/roles/${roleId}/permission-rules/${ruleId}`, { enabled })
}

/**
 * 计算规则影响范围
 * @param {number} roleId
 * @param {object} rule
 * @returns {Promise<ApiResponse>}
 */
export async function calculateImpact(roleId, rule) {
  return apiV1.post(`/roles/${roleId}/calculate-impact`, rule)
}

/**
 * 加载管理维度列表
 * @param {object} [params] - 查询参数
 * @returns {Promise<ApiResponse>}
 */
export async function loadDimensions(params = {}) {
  return apiV1.get('/management-dimensions', { params })
}

/**
 * 加载维度字段
 * @param {number} dimensionId
 * @returns {Promise<ApiResponse>}
 */
export async function loadDimensionFields(dimensionId) {
  return apiV1.get(`/management-dimensions/${dimensionId}/fields`)
}

/**
 * 加载维度实例（Value Help）
 * @param {string} dimCode - 维度代码
 * @param {object} [params] - 查询参数（search, page, filter 等）
 * @returns {Promise<ApiResponse>}
 */
export async function loadDimensionValues(dimCode, params = {}) {
  return apiV1.get(`/permission-rules/dimensions/${dimCode}/values`, { params })
}

/**
 * 加载字段元数据
 * @param {string} resourceType
 * @returns {Promise<ApiResponse>}
 */
export async function loadFieldMetadata(resourceType) {
  return apiV1.get('/permission-rules/field-metadata', { params: { resource_type: resourceType } })
}

/**
 * 预览条件匹配
 * @param {object} previewData
 * @returns {Promise<ApiResponse>}
 */
export async function previewCondition(previewData) {
  return apiV1.post('/permission-rules/preview', previewData)
}

/**
 * 加载统一权限配置
 * @param {number} roleId
 * @returns {Promise<ApiResponse>}
 */
export async function loadUnifiedPermissions(roleId) {
  return apiV1.get(`/roles/${roleId}/unified-permissions`)
}

/**
 * 保存菜单权限
 * @param {number} roleId
 * @param {object} permissions
 * @returns {Promise<ApiResponse>}
 */
export async function saveMenuPermissions(roleId, permissions) {
  return apiV1.put(`/roles/${roleId}/menu-permissions`, permissions)
}

/**
 * 加载维度范围
 * @param {number} roleId
 * @returns {Promise<ApiResponse>}
 */
export async function loadDimensionScopes(roleId) {
  return apiV1.get(`/roles/${roleId}/dimension-scopes`)
}

/**
 * 保存维度范围
 * @param {number} roleId
 * @param {object} scopes
 * @returns {Promise<ApiResponse>}
 */
export async function saveDimensionScopes(roleId, scopes) {
  return apiV1.post(`/roles/${roleId}/dimension-scopes`, scopes)
}

/**
 * 自动推导权限
 * @param {number} roleId
 * @returns {Promise<ApiResponse>}
 */
export async function derivePermissions(roleId) {
  return apiV1.get(`/roles/${roleId}/derived-permissions`)
}

/**
 * 查询字段重叠警告
 * @param {number} roleId
 * @param {string} resourceType
 * @returns {Promise<ApiResponse>}
 */
export async function loadOverlapWarnings(roleId, resourceType) {
  return apiV1.get(`/roles/${roleId}/overlaps`, { params: { resource_type: resourceType } })
}

/**
 * 加载条件规则列表（无 roleId 前缀）
 * @param {object} [params] - 查询参数
 * @returns {Promise<ApiResponse>}
 */
export async function loadConditionRules(params = {}) {
  return apiV1.get('/permission-rules', params)
}

/**
 * 删除条件规则
 * @param {number} ruleId
 * @returns {Promise<ApiResponse>}
 */
export async function deleteConditionRule(ruleId) {
  return apiV1.delete(`/permission-rules/${ruleId}`)
}

/**
 * 保存条件规则
 * @param {object} rule
 * @returns {Promise<ApiResponse>}
 */
export async function saveConditionRule(rule) {
  return apiV1.post('/permission-rules', rule)
}

/**
 * 加载维度实例（分页，用于 DimensionScopePanel）
 * @param {number} dimensionId
 * @param {object} [params] - page, page_size, search, filter_*
 * @returns {Promise<ApiResponse>}
 */
export async function loadDimensionInstances(dimensionId, params = {}) {
  return apiV1.get(`/management-dimensions/${dimensionId}/instances`, { params })
}

/**
 * 批量设置数据权限
 * @param {object} data - { user_ids, resource_type, resource_id, permission_level, inherit_to_children }
 * @returns {Promise<ApiResponse>}
 */
export async function batchDataPermissions(data) {
  return apiV1.post('/users/batch-data-permissions', data)
}

/**
 * 为用户组添加数据权限
 * @param {number} groupId
 * @param {object} data
 * @returns {Promise<ApiResponse>}
 */
export async function addGroupDataPermission(groupId, data) {
  return apiV1.post(`/user-groups/${groupId}/data-permissions`, data)
}
```

### 4.2 纯函数（4 个，无 IO）

```javascript
/**
 * 权限级别 -> Tag 类型映射
 * @param {string} level - 'read'|'write'|'admin'|'manage'|'none'
 * @returns {'success'|'warning'|'danger'|'info'|''}
 */
export function getPermissionLevelType(level) {
  const map = {
    read: '',
    write: 'warning',
    admin: 'success',
    manage: 'success',
    none: 'info',
  }
  return map[level] || ''
}

/**
 * 权限级别 -> 中文标签
 * @param {string} level
 * @returns {string}
 */
export function getPermissionLevelLabel(level) {
  const map = {
    read: '只读',
    write: '可编辑',
    admin: '完全管理',
    manage: '管理',
    none: '无权限',
  }
  return map[level] || level
}

/**
 * 资源类型 -> 中文标签
 * @param {string} resourceType
 * @returns {string}
 */
export function getResourceLabel(resourceType) {
  const map = {
    domain: '领域',
    sub_domain: '子领域',
    service_module: '服务模块',
    business_object: '业务对象',
    product: '产品',
    version: '版本',
    relationship: '关系',
    annotation: '标注',
  }
  return map[resourceType] || resourceType
}

/**
 * 根据 resource_type 查找维度中文名
 * @param {Array} dimensions - 维度列表
 * @param {string} resourceType
 * @returns {string}
 */
export function getDimensionName(dimensions, resourceType) {
  const dim = dimensions.find(d => d.code === resourceType || d.resource_type === resourceType)
  return dim?.name || getResourceLabel(resourceType)
}
```

### 4.3 常量导出

```javascript
/**
 * 权限级别标签（统一来源，消除 5 处重复定义）
 */
export const PERMISSION_LEVELS = {
  none: { label: '无权限', type: 'info' },
  read: { label: '只读', type: '' },
  write: { label: '可编辑', type: 'warning' },
  admin: { label: '完全管理', type: 'success' },
  manage: { label: '管理', type: 'success' },
}

/**
 * 资源类型标签（统一来源，消除 4 处重复定义）
 */
export const RESOURCE_LABELS = {
  domain: '领域',
  sub_domain: '子领域',
  service_module: '服务模块',
  business_object: '业务对象',
  product: '产品',
  version: '版本',
  relationship: '关系',
  annotation: '标注',
}

/**
 * 维度父子映射
 */
export const DIMENSION_PARENT_MAP = {
  product: null,
  version: 'product',
  domain: 'version',
  sub_domain: 'domain',
}

/**
 * 维度层级
 */
export const DIMENSION_LEVEL_MAP = {
  product: 0,
  version: 1,
  domain: 2,
  sub_domain: 3,
}

/**
 * 隐藏维度列表
 */
export const HIDDEN_DIMENSIONS = [
  'domain_type', 'organization', 'department', 'employee',
  'created_by', 'created_at', 'owner_id',
]
```

### 4.4 单元测试矩阵（≥ 15 用例）

| # | 测试场景 | 函数 | 预期 |
|---|---------|------|------|
| 1 | `getPermissionLevelType('read')` | 纯函数 | `''` |
| 2 | `getPermissionLevelType('write')` | 纯函数 | `'warning'` |
| 3 | `getPermissionLevelType('admin')` | 纯函数 | `'success'` |
| 4 | `getPermissionLevelType('unknown')` | 纯函数 | `''` |
| 5 | `getPermissionLevelLabel('read')` | 纯函数 | `'只读'` |
| 6 | `getPermissionLevelLabel('admin')` | 纯函数 | `'完全管理'` |
| 7 | `getResourceLabel('domain')` | 纯函数 | `'领域'` |
| 8 | `getResourceLabel('unknown')` | 纯函数 | `'unknown'` |
| 9 | `getDimensionName([{code:'domain',name:'领域'}], 'domain')` | 纯函数 | `'领域'` |
| 10 | `getDimensionName([], 'domain')` | 纯函数 | `'领域'`（回退到 RESOURCE_LABELS） |
| 11 | `loadRoles()` | API 函数 | 调用 `apiV1.get('/roles')` |
| 12 | `savePermissionRules(1, {id:5}, 'update')` | API 函数 | 调用 `apiV1.put('/roles/1/permission-rules/5')` |
| 13 | `savePermissionRules(1, [{...}], 'batch')` | API 函数 | 调用 `apiV1.post('/roles/1/permission-rules/batch')` |
| 14 | `deletePermissionRule(1, 5)` | API 函数 | 调用 `apiV1.delete('/roles/1/permission-rules/5')` |
| 15 | `loadDimensionValues('domain', {search:'test'})` | API 函数 | 调用 `apiV1.get('/permission-rules/dimensions/domain/values')` |

---

## 5. FR-UI-008：conditionExpressionService.js

### 5.1 函数签名（6 个，全部纯函数）

```javascript
// src/services/conditionExpressionService.js

/**
 * @typedef {Object} DimConfig
 * @property {string} dim        // dimension code
 * @property {string} op         // 操作符：=, !=, IN, NOT IN, LIKE, >, <, >=, <=
 * @property {string|number|string[]} value
 *
 * @typedef {Object} ValueNameMap
 * @property {Object} [code]     // value code → display name
 *
 * @typedef {Object} Dimension
 * @property {string} code
 * @property {string} name
 * @property {string} [parent_dim]
 */

/**
 * 根据维度配置生成条件表达式
 *
 * 示例:
 *   buildConditionFromDimensions(
 *     [{dim:'domain_id', op:'=', value:5}, {dim:'status', op:'IN', value:['active','draft']}],
 *     [], {}, 'AND'
 *   )
 *   → "domain_id = 5 AND status IN ('active', 'draft')"
 *
 * @param {DimConfig[]} dimConfigs
 * @param {Dimension[]} dimensions - 维度元数据（用于字段名映射）
 * @param {ValueNameMap} valueNameMap - 值 ID→名称映射
 * @param {'AND'|'OR'|'CUSTOM'} mode
 * @returns {string} 条件表达式字符串
 */
export function buildConditionFromDimensions(dimConfigs, dimensions, valueNameMap, mode = 'AND')

/**
 * 将技术条件表达式翻译为用户友好的中文描述
 *
 * 示例:
 *   translateToFriendlyCondition(
 *     "domain_id = 5 AND status IN ('active', 'draft')",
 *     [{dim:'domain_id', op:'=', value:5}, {dim:'status', op:'IN', value:['active','draft']}],
 *     {5:'产品研发', active:'活跃', draft:'草稿'},
 *     [{code:'domain_id', name:'领域'}, {code:'status', name:'状态'}]
 *   )
 *   → "领域 = 产品研发 且 状态 为 活跃,草稿"
 *
 * @param {string} condition - 条件表达式
 * @param {DimConfig[]} dimConfigs
 * @param {ValueNameMap} valueNameMap
 * @param {Dimension[]} dimensions
 * @returns {string} 友好描述
 */
export function translateToFriendlyCondition(condition, dimConfigs, valueNameMap, dimensions)

/**
 * 按层级深度排序维度（父维度在前）
 * @param {Dimension[]} dimensions
 * @param {Function} getDepth - (dim) => number
 * @returns {Dimension[]} 排序后的维度列表
 */
export function sortDimensionsByHierarchy(dimensions, getDepth)

/**
 * 过滤隐藏维度
 * @param {Dimension[]} dimensions
 * @param {string[]} hiddenList - 隐藏维度代码列表
 * @returns {Dimension[]} 过滤后的维度列表
 */
export function filterHiddenDimensions(dimensions, hiddenList)

/**
 * 解析自定义条件文本
 * @param {string} text - 用户输入的条件文本
 * @returns {{ok: true, ast: object} | {ok: false, error: string}}
 */
export function parseCustomCondition(text)

/**
 * 校验条件表达式是否合法
 * @param {string} condition
 * @returns {boolean}
 */
export function isValidCondition(condition)
```

### 5.2 核心算法：buildConditionFromDimensions

```javascript
export function buildConditionFromDimensions(dimConfigs, dimensions, valueNameMap, mode = 'AND') {
  if (!dimConfigs || dimConfigs.length === 0) return ''
  if (mode === 'CUSTOM') return ''  // 自定义模式由用户手写

  const parts = dimConfigs
    .filter(dc => dc.value !== undefined && dc.value !== null && dc.value !== '')
    .map(dc => {
      const fieldName = dc.dim
      const op = dc.op.toUpperCase()

      if (op === 'IN' || op === 'NOT IN') {
        const vals = Array.isArray(dc.value) ? dc.value : [dc.value]
        const formatted = vals.map(v => typeof v === 'number' ? v : `'${v}'`)
        return `${fieldName} ${op} (${formatted.join(', ')})`
      }

      if (op === 'LIKE') {
        return `${fieldName} LIKE '%${dc.value}%'`
      }

      // =, !=, >, <, >=, <=
      const formatted = typeof dc.value === 'number' ? dc.value : `'${dc.value}'`
      return `${fieldName} ${op} ${formatted}`
    })

  return parts.join(` ${mode} `)
}
```

### 5.3 核心算法：translateToFriendlyCondition

```javascript
export function translateToFriendlyCondition(condition, dimConfigs, valueNameMap, dimensions) {
  if (!condition) return ''

  // 尝试用 dimConfigs 逐条翻译
  if (dimConfigs && dimConfigs.length > 0) {
    const parts = dimConfigs
      .filter(dc => dc.value !== undefined && dc.value !== null && dc.value !== '')
      .map(dc => {
        const dimMeta = dimensions.find(d => d.code === dc.dim)
        const dimLabel = dimMeta?.name || dc.dim

        const opLabel = {
          '=': '=', '!=': '≠', 'IN': '为', 'NOT IN': '不为',
          'LIKE': '包含', '>': '>', '<': '<', '>=': '≥', '<=': '≤',
        }[dc.op.toUpperCase()] || dc.op

        let valueLabel
        if (Array.isArray(dc.value)) {
          valueLabel = dc.value.map(v => valueNameMap[v] || v).join(',')
        } else {
          valueLabel = valueNameMap[dc.value] || dc.value
        }

        return `${dimLabel} ${opLabel} ${valueLabel}`
      })
    return parts.join(' 且 ')
  }

  // 后备：简单替换
  return generateSimpleFriendly(condition, dimensions, valueNameMap)
}

function generateSimpleFriendly(condition, dimensions, valueNameMap) {
  let result = condition
  // 替换字段名
  for (const dim of dimensions) {
    result = result.replace(new RegExp(`\\b${dim.code}\\b`, 'g'), dim.name)
  }
  // 替换操作符
  result = result.replace(/\bAND\b/g, '且')
  result = result.replace(/\bOR\b/g, '或')
  result = result.replace(/\bIN\b/g, '为')
  result = result.replace(/\bNOT IN\b/g, '不为')
  result = result.replace(/\bLIKE\b/g, '包含')
  // 替换值
  for (const [code, name] of Object.entries(valueNameMap)) {
    result = result.replace(new RegExp(`\\b${code}\\b`, 'g'), name)
  }
  return result
}
```

### 5.4 单元测试矩阵（≥ 25 用例）

| # | 测试场景 | 函数 | 输入 | 预期 |
|---|---------|------|------|------|
| 1 | 空配置 | build | `[]` | `''` |
| 2 | 单条件 = | build | `[{dim:'x', op:'=', value:5}]` | `'x = 5'` |
| 3 | 单条件 = 字符串 | build | `[{dim:'x', op:'=', value:'abc'}]` | `"x = 'abc'"` |
| 4 | 单条件 != | build | `[{dim:'x', op:'!=', value:1}]` | `'x != 1'` |
| 5 | IN 操作符 | build | `[{dim:'x', op:'IN', value:[1,2]}]` | `'x IN (1, 2)'` |
| 6 | IN 字符串 | build | `[{dim:'x', op:'IN', value:['a','b']}]` | `"x IN ('a', 'b')"` |
| 7 | NOT IN | build | `[{dim:'x', op:'NOT IN', value:[1]}]` | `'x NOT IN (1)'` |
| 8 | LIKE | build | `[{dim:'x', op:'LIKE', value:'test'}]` | `"x LIKE '%test%'"` |
| 9 | 多条件 AND | build | 2 个 dimConfigs | `'a = 1 AND b = 2'` |
| 10 | 多条件 OR | build | mode='OR' | `'a = 1 OR b = 2'` |
| 11 | CUSTOM 模式 | build | mode='CUSTOM' | `''` |
| 12 | 空值过滤 | build | `[{dim:'x', op:'=', value:''}]` | `''` |
| 13 | 简单翻译 | translate | `'domain_id = 5'` + dimConfigs | `'领域 = 产品研发'` |
| 14 | IN 翻译 | translate | IN 条件 | `'领域 为 产品研发,技术'` |
| 15 | 后备翻译 | translate | 无 dimConfigs | 简单替换 |
| 16 | 层级排序 | sort | 3 维度 | 父维度在前 |
| 17 | 隐藏过滤 | filter | 含 hidden | 排除 hidden |
| 18 | parseCustom 合法 | parse | `'x = 1'` | `{ok: true, ast:...}` |
| 19 | parseCustom 非法 | parse | `'@#$'` | `{ok: false, error:...}` |
| 20 | isValid 合法 | isValid | `'x = 1 AND y = 2'` | `true` |
| 21 | isValid 非法 | isValid | `''` | `false` |
| 22 | 比较操作符 > | build | `[{dim:'x', op:'>', value:10}]` | `'x > 10'` |
| 23 | 比较操作符 >= | build | `[{dim:'x', op:'>=', value:10}]` | `'x >= 10'` |
| 24 | 混合类型多条件 | build | 数值+字符串 | 正确格式化 |
| 25 | valueNameMap 替换 | translate | 含映射 | ID→名称 |

---

## 6. FR-UI-009：Vue 组件重构

### 6.1 重构策略

**逐组件渐进式重构**，每个组件的改动：
1. 删除 `getHeaders()` → 使用 httpClient（自动 credentials: 'include'）
2. 删除 `const API_BASE` → 已在 FR-UI-006 中完成
3. `fetch()` 调用 → `permissionService.*()`
4. 业务逻辑函数 → 委托给 `permissionService.*` 或 `conditionExpressionService.*`
5. 重复常量 → `import { PERMISSION_LEVELS, RESOURCE_LABELS } from '@/services/permissionService'`

### 6.2 逐组件重构清单

#### 6.2.1 RolePermissionCenter.vue（8 fetch → 0）

| 原代码 | 替换为 |
|--------|--------|
| `fetch(GET /roles/:id)` | `permissionService.loadRole(roleId)` |
| `fetch(GET /management-dimensions)` | `permissionService.loadDimensions()` |
| `fetch(GET /management-dimensions/:id/fields)` | `permissionService.loadDimensionFields(id)` |
| `fetch(GET /roles/:id/permission-rules)` | `permissionService.loadPermissionRules(roleId)` |
| `fetch(POST /roles/:id/calculate-impact)` | `permissionService.calculateImpact(roleId, rule)` |
| `fetch(POST/PUT /roles/:id/permission-rules)` | `permissionService.savePermissionRules(roleId, rule, mode)` |
| `fetch(DELETE /roles/:id/permission-rules/:id)` | `permissionService.deletePermissionRule(roleId, ruleId)` |
| `fetch(PATCH /roles/:id/permission-rules/:id)` | `permissionService.toggleRuleStatus(roleId, ruleId, enabled)` |
| `fetch(POST /roles/:id/permission-rules/batch)` | `permissionService.savePermissionRules(roleId, rules, 'batch')` |
| `getDimensionName()` | `permissionService.getDimensionName()` |
| `getPermissionLevelType()` | `permissionService.getPermissionLevelType()` |
| `getPermissionLevelLabel()` | `permissionService.getPermissionLevelLabel()` |
| `getHeaders()` | 删除（httpClient 自动处理） |

**预期行数减少**：~600 → ~480（-20%）

#### 6.2.2 ConditionRuleDialog.vue（8 fetch → 0）

| 原代码 | 替换为 |
|--------|--------|
| `fetch(GET /roles/:id/overlaps)` | `permissionService.loadOverlapWarnings(roleId, resourceType)` |
| `fetch(GET /management-dimensions)` | `permissionService.loadDimensions()` |
| `fetch(GET /permission-rules/dimensions/:code/values)` | `permissionService.loadDimensionValues(dimCode, params)` |
| `fetch(GET /permission-rules/field-metadata)` | `permissionService.loadFieldMetadata(resourceType)` |
| `fetch(POST /permission-rules/preview)` | `permissionService.previewCondition(data)` |
| `fetch(POST /permission-rules)` | `permissionService.saveConditionRule(rule)` |
| `updateCondition()` | `conditionExpressionService.buildConditionFromDimensions()` |
| `getFriendlyCondition()` | `conditionExpressionService.translateToFriendlyCondition()` |
| `generateSimpleFriendly()` | 删除（内化到 service） |
| `parseConditionToDimConfigs()` | `conditionExpressionService.parseCustomCondition()` |
| `sortedDimensions` computed | `conditionExpressionService.sortDimensionsByHierarchy()` + `filterHiddenDimensions()` |
| `HIDDEN_DIMENSIONS` 常量 | `import { HIDDEN_DIMENSIONS } from '@/services/permissionService'` |
| `getHeaders()` | 删除 |

**预期行数减少**：~1100 → ~770（-30%）

#### 6.2.3 RoleDetailDrawer.vue（5 fetch → 0）

| 原代码 | 替换为 |
|--------|--------|
| `fetch(GET /meta/objects)` | `permissionService.loadObjectTypes()` 或 `objectTypeService.init()` |
| `fetch(GET /roles/:id/unified-permissions)` | `permissionService.loadUnifiedPermissions(roleId)` |
| `fetch(GET /permission-rules?role_id=...)` | `permissionService.loadConditionRules({role_id})` |
| `fetch(DELETE /permission-rules/:id)` | `permissionService.deleteConditionRule(ruleId)` |
| `fetch(PUT /roles/:id/menu-permissions)` | `permissionService.saveMenuPermissions(roleId, data)` |
| `getPermLevelLabel()` | `permissionService.getPermissionLevelLabel()` |
| `LEVEL_LABELS` 常量 | `import { PERMISSION_LEVELS } from '@/services/permissionService'` |
| `FALLBACK_RESOURCE_TYPES` | `import { RESOURCE_LABELS } from '@/services/permissionService'` |

#### 6.2.4 DimensionScopePanel.vue（5 fetch → 0）

| 原代码 | 替换为 |
|--------|--------|
| `fetch(GET /management-dimensions)` | `permissionService.loadDimensions()` |
| `fetch(GET /roles/:id/dimension-scopes)` | `permissionService.loadDimensionScopes(roleId)` |
| `fetch(GET /management-dimensions/:id/instances)` | `permissionService.loadDimensionInstances(dimId, params)` |
| `fetch(GET /roles/:id/derived-permissions)` | `permissionService.derivePermissions(roleId)` |
| `fetch(POST /roles/:id/dimension-scopes)` | `permissionService.saveDimensionScopes(roleId, scopes)` |
| `DIMENSION_PARENT_MAP` | `import { DIMENSION_PARENT_MAP } from '@/services/permissionService'` |
| `DIMENSION_LEVEL_MAP` | `import { DIMENSION_LEVEL_MAP } from '@/services/permissionService'` |

#### 6.2.5 DataPermissionConfig.vue（3 fetch → 0）

| 原代码 | 替换为 |
|--------|--------|
| `fetch(GET /roles)` | `permissionService.loadRoles()` |
| `fetch(GET /permission-rules)` | `permissionService.loadConditionRules()` |
| `fetch(DELETE /permission-rules/:id)` | `permissionService.deleteConditionRule(ruleId)` |
| `getResourceLabel()` | `permissionService.getResourceLabel()` |
| `getPermLevelLabel()` | `permissionService.getPermissionLevelLabel()` |
| `RESOURCE_LABELS` / `LEVEL_LABELS` | `import { RESOURCE_LABELS, PERMISSION_LEVELS } from '@/services/permissionService'` |

#### 6.2.6 BatchDataPermDialog.vue（2 fetch → 0）

| 原代码 | 替换为 |
|--------|--------|
| `fetch(GET /users?keyword=...)` | `permissionService.searchUsers(keyword)` |
| `fetch(POST /users/batch-data-permissions)` | `permissionService.batchDataPermissions(data)` |
| `getHeaders()` | 删除 |

> 注：需新增 `searchUsers()` API 函数到 permissionService。

#### 6.2.7 AddPermissionDialog.vue（3 fetch → 0）

| 原代码 | 替换为 |
|--------|--------|
| `fetch(GET /meta/objects)` | `objectTypeService.init()` 或 `permissionService.loadObjectTypes()` |
| `fetch(GET /:resource_type?...)` | `permissionService.loadResources(resourceType, params)` |
| `fetch(POST /user-groups/:id/data-permissions)` | `permissionService.addGroupDataPermission(groupId, data)` |
| `FALLBACK_RESOURCE_TYPES` | `import { RESOURCE_LABELS } from '@/services/permissionService'` |
| `permissionLevels` 常量 | `import { PERMISSION_LEVELS } from '@/services/permissionService'` |

> 注：需新增 `loadResources()` 和 `loadObjectTypes()` API 函数到 permissionService。

#### 6.2.8 UserPermissionSummary.vue（1 fetch → 0）

| 原代码 | 替换为 |
|--------|--------|
| `fetch(GET /meta/objects)` | `objectTypeService.init()` |
| `getResourceLabel()` | `permissionService.getResourceLabel()` |
| `FALLBACK_LABELS` / `ACTION_LABELS` / `LEVEL_LABELS` | `import { RESOURCE_LABELS, PERMISSION_LEVELS } from '@/services/permissionService'` |

#### 6.2.9 ConditionRuleEditor.vue（可复用组件）

此组件是 ConditionRuleDialog 的可复用版本，有相同的 `updateCondition()` / `parseConditionToDimConfigs()` 重复实现。重构方式与 ConditionRuleDialog 一致。

| 原代码 | 替换为 |
|--------|--------|
| `updateCondition()` | `conditionExpressionService.buildConditionFromDimensions()` |
| `parseConditionToDimConfigs()` | `conditionExpressionService.parseCustomCondition()` |
| `generateFriendlyFromCustom()` | `conditionExpressionService.translateToFriendlyCondition()` |
| `loadValueHelp()` | `permissionService.loadDimensionValues()` |
| `loadFieldMetadata()` | `permissionService.loadFieldMetadata()` |
| `doPreview()` | `permissionService.previewCondition()` |

### 6.3 permissionService 需补充的 API 函数

基于 §6.2 分析，除了 §4.1 已列出的 22 个函数外，还需补充：

```javascript
/**
 * 搜索用户（用于批量授权）
 * @param {string} keyword
 * @param {object} [params]
 * @returns {Promise<ApiResponse>}
 */
export async function searchUsers(keyword, params = {}) {
  return apiV1.get('/users', { params: { keyword, page_size: 20, ...params } })
}

/**
 * 加载资源列表（分页）
 * @param {string} resourceType
 * @param {object} [params] - page, page_size, keyword
 * @returns {Promise<ApiResponse>}
 */
export async function loadResources(resourceType, params = {}) {
  return apiV1.get(`/${resourceType}`, params)
}

/**
 * 加载对象类型元数据
 * @returns {Promise<ApiResponse>}
 */
export async function loadObjectTypes() {
  return apiV1.get('/meta/objects')
}
```

---

## 7. 实施计划

### 7.1 PR 分解

| PR | 内容 | FR | 依赖 |
|----|------|----|----|
| **8a** | `permissionService.js` 创建（API 函数 + 纯函数 + 常量） | FR-UI-007 | FR-UI-001 ✅ |
| **8b** | `conditionExpressionService.js` 创建（6 个纯函数） | FR-UI-008 | 无 |
| **9a** | RolePermissionCenter.vue 重构 | FR-UI-009 | PR 8a |
| **9b** | ConditionRuleDialog.vue + ConditionRuleEditor.vue 重构 | FR-UI-009 | PR 8a + 8b |
| **9c** | RoleDetailDrawer + DimensionScopePanel + DataPermissionConfig 重构 | FR-UI-009 | PR 8a |
| **9d** | BatchDataPermDialog + AddPermissionDialog + UserPermissionSummary 重构 | FR-UI-009 | PR 8a |

### 7.2 执行顺序

```
PR 8a ─────────────────────────────┐
  permissionService.js              │
                                    ├──→ PR 9a ──→ PR 9c
PR 8b ─────────────────────────────┤
  conditionExpressionService.js     ├──→ PR 9b
                                    │
                                    └──→ PR 9d
```

**8a 和 8b 可并行**，9a-9d 依赖 8a/8b 完成后按序执行。

### 7.3 验收检查清单

- [ ] `grep -rn "fetch(" src/views/SystemManagement/` 为空
- [ ] `grep -rn "getHeaders" src/views/SystemManagement/` 为空
- [ ] `grep -rn "LEVEL_LABELS" src/views/SystemManagement/` 为空（统一从 permissionService 导入）
- [ ] `grep -rn "RESOURCE_LABELS" src/views/SystemManagement/` 为空
- [ ] `grep -rn "updateCondition" src/views/SystemManagement/ConditionRuleDialog.vue` 为空
- [ ] `grep -rn "parseConditionToDimConfigs" src/views/SystemManagement/ConditionRuleDialog.vue` 为空
- [ ] RolePermissionCenter.vue 行数减少 ≥ 20%
- [ ] ConditionRuleDialog.vue 行数减少 ≥ 30%
- [ ] Vite build 通过
- [ ] 权限管理页面功能正常（角色列表/权限规则CRUD/条件规则/维度范围）

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| httpClient.apiV1 行为与直接 fetch 不一致 | 低 | 高 | permissionService API 函数返回值格式与原 fetch 一致 |
| 条件表达式生成结果与原实现不一致 | 中 | 高 | 快照测试：重构前后对同一 dimConfigs 生成相同条件字符串 |
| ConditionRuleEditor.vue 是可复用组件，被其他页面引用 | 中 | 中 | 重构后保持 props 接口不变，仅内部委托 service |
| AddPermissionDialog.vue 混用 apiV1 和 API_BASE | 低 | 低 | 统一改为 permissionService 调用 |
| 维度级联逻辑复杂（DimensionScopePanel） | 中 | 中 | 级联逻辑保留在组件内，仅 API 调用下沉 |

---

## 附录 A：条件表达式 DSL EBNF

```
condition       = simple_condition { ("AND" | "OR") simple_condition }
simple_condition = field_name operator value
                 | field_name "IN" "(" value_list ")"
                 | field_name "NOT" "IN" "(" value_list ")"
                 | field_name "LIKE" string_value
operator        = "=" | "!=" | ">" | "<" | ">=" | "<="
field_name      = identifier
value           = string_value | numeric_value
string_value    = "'" char_sequence "'"
numeric_value   = [ "-" ] digit_sequence [ "." digit_sequence ]
value_list      = value { "," value }
identifier      = letter { letter | digit | "_" }
```

## 附录 B：操作符优先级

| 优先级 | 操作符 | 结合性 |
|--------|--------|--------|
| 1 (最高) | `NOT` | 右 |
| 2 | `=`, `!=`, `>`, `<`, `>=`, `<=`, `IN`, `NOT IN`, `LIKE` | 左 |
| 3 | `AND` | 左 |
| 4 (最低) | `OR` | 左 |

---

_本子 spec 是父 spec FR-UI-007/008/009 的完整实施蓝本，与 Track A（PR 4-7）无依赖，可并行实施。_
