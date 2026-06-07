# Spec: 对象日志详情页面（可复用模块）+ 全对象详情页适配

## 1. Background & Objectives

### 1.1 Background

当前项目中日志/变更历史功能存在三大问题：

1. **数据加载方式不统一**：4种不同的日志数据获取路径并存
   - `useDetail.loadAuditLogsData()` 使用 `boService.queryAssociations()`
   - `RolePermissionDetail` 使用 `boService.query('audit_log', { filters })`
   - `RoleDetailDrawer` 直接调用 `/audit-logs` API
   - `DynamicDetail` 依赖父组件传入 `change_history`

2. **日志展示组件功能不足**：
   - `AuditLog.vue` 仅支持简单列表展示，缺少分页、筛选、详情查看
   - `ChangeHistory.vue` 是空占位组件，从未实现

3. **YAML 配置与 UI 推导脱节**：
   - 仅 user/role/user_group 3个对象在 YAML 中配置了 `type: history` 的 tab
   - 其余 9 个对象（domain/sub_domain/service_module/business_object/relationship/product/version/enum_type/enum_value）完全没有 history tab
   - 但这 9 个对象中大部分已声明 `aspects: [audit_aspect]`，说明模型层已具备审计能力，只是 UI 层没有推导出来

4. **违反单一事实原则**：当前 history tab 需要逐对象在 `ui_view_config.detail.tabs` 中手动配置，与 YAML 单一事实原则矛盾。模型层已通过 `aspects: [audit_aspect]` 声明了审计能力，UI 层应自动推导。

### 1.2 Business Objectives

- 所有声明了 `audit_aspect` 的业务对象，详情页自动具备变更历史 Tab
- 日志数据加载方式统一为单一 Composable
- 日志展示组件支持分页、筛选、详情查看

### 1.3 User / Stakeholder Objectives

- **系统管理员**：在任意对象详情页查看该对象的完整变更历史
- **业务用户**：查看自己操作的变更记录，了解字段级变更细节
- **开发者**：新增业务对象时只需声明 `aspects: [audit_aspect]`，无需手动配置 history tab

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 统一日志查看体验，减少重复配置 |
| User/Stakeholder | Yes | 管理员/业务用户的日志查看需求 |
| Solution | Yes | 智能推导 history tab + 统一 Composable |
| Functional | Yes | 分页/筛选/详情查看/全对象适配 |
| Nonfunctional | Yes | 性能（分页加载）、一致性（统一数据源） |
| External Interface | Yes | 后端 $metadata 端点需返回 aspects 信息 |
| Transition | Yes | 现有手动配置的 history tab 需迁移为智能推导 |

## 3. Functional Requirements

### FR-001: 后端 $metadata 端点返回 aspects 信息

- **Description**: 后端 `GET /api/v2/bo/<object>/$metadata` 端点的响应中 MUST 包含对象的 `aspects` 数组，以便前端判断该对象是否具备审计能力。
- **Acceptance Criteria**:
  - `$metadata` 响应中包含 `aspects` 字段（如 `["audit_aspect", "hierarchy_aspect"]`）
  - 对于声明了 `aspects: [audit_aspect]` 的对象，返回值中包含 `"audit_aspect"`
  - 对于未声明 aspects 的对象，返回空数组或不含 `"audit_aspect"`
- **Priority**: Must
- **Type Mapping**: Solution / External Interface
- **Source**: 代码分析 -- 10个对象已声明 `aspects: [audit_aspect]` 但前端无法感知

### FR-002: 前端智能推导 history tab

- **Description**: 当对象的 `$metadata` 返回的 `aspects` 中包含 `"audit_aspect"` 时，前端 MUST 自动在详情页中添加"变更历史" Tab，无需在 YAML 的 `ui_view_config.detail.tabs` 中手动配置。
- **Acceptance Criteria**:
  - 声明了 `aspects: [audit_aspect]` 的对象，详情页自动出现"变更历史" Tab
  - 未声明 `audit_aspect` 的对象，详情页不出现"变更历史" Tab
  - 已在 YAML 中手动配置了 `type: history` tab 的对象（user/role/user_group），行为与智能推导一致，不重复显示
  - 智能推导的 history tab 排在所有手动配置的 tab 之后
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 用户要求"YAML 请确保单一事实，尽量是模型，UI 更多的是智能推导"

### FR-003: 统一日志数据加载 Composable

- **Description**: 创建 `useAuditLogs` composable，统一所有日志数据获取路径，替代当前4种不同方式。
- **Acceptance Criteria**:
  - `useAuditLogs(objectType, objectId)` 提供统一的日志加载接口
  - 支持分页参数（page, page_size）
  - 支持筛选参数（action 类型筛选）
  - `useDetail.loadAuditLogsData()` 内部改用统一接口，保持向后兼容
  - `ChangeHistory` 组件使用 `useAuditLogs` 自行加载数据
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 代码分析 -- 4种不同的日志加载方式

### FR-004: AuditLog 组件增强 -- 分页与筛选

- **Description**: 增强 `AuditLog.vue` 组件，支持分页和操作类型筛选。
- **Acceptance Criteria**:
  - 支持底部分页器（使用 `Pagination` 组件），当 `showPagination=true` 时显示
  - 支持操作类型筛选栏（创建/更新/删除/分配/撤销），当 `showFilter=true` 时显示
  - 筛选变更时触发 `filter-change` 事件
  - 分页变更时触发 `page-change` 事件
  - 保持现有功能（展开/收起、空状态、加载状态）不变
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: UI_COMPONENT_GUIDELINES.md 2.9 Pagination / 2.7 状态徽章

### FR-005: AuditLog 组件增强 -- 日志点击展开详情

- **Description**: 点击 AuditLog 中的日志条目时，MUST 展开该条目的完整变更内容或打开详情弹窗。
- **Acceptance Criteria**:
  - 点击日志条目触发 `log-click` 事件，传递该条日志数据
  - 日志条目 hover 时有视觉反馈（边框变色、背景高亮）
  - 支持通过 prop 控制点击行为：`clickMode = 'expand' | 'drawer'`
    - `expand`：在列表中展开详情区域
    - `drawer`：打开 AuditLogDetail Drawer
  - 默认 `clickMode = 'expand'`
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: UI_COMPONENT_GUIDELINES.md 2.6 表格交互

### FR-006: AuditLogDetail 日志详情弹窗

- **Description**: 新增 `AuditLogDetail.vue` 组件，以 Drawer 形式展示单条日志的完整变更内容。
- **Acceptance Criteria**:
  - 使用 `Drawer` 组件（遵循 UI_COMPONENT_GUIDELINES.md 2.10）
  - 展示：操作类型标签、操作时间、操作人、对象类型、对象ID
  - 展示变更字段表格：字段名 | 变更前值 | 变更后值（遵循 2.6 表格规范）
  - 变更前值使用删除线 + 红色，变更后值使用绿色加粗
  - 创建操作显示"创建记录"而非字段变更
  - 删除操作显示"删除记录"而非字段变更
  - 支持 `v-model:visible` 控制显隐
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: UI_COMPONENT_GUIDELINES.md 2.10 Drawer / 2.6 表格 / 2.7 状态徽章

### FR-007: ChangeHistory 组件重写

- **Description**: 重写当前空占位的 `ChangeHistory.vue`，基于 `useAuditLogs` composable 实现完整的变更历史展示。
- **Acceptance Criteria**:
  - 接收 `objectType` 和 `objectId` props，自行加载日志数据
  - 内部使用增强版 `AuditLog` 组件展示日志列表
  - 支持分页和筛选
  - 点击日志条目可展开详情或打开 AuditLogDetail
  - 空状态展示友好提示
  - 替换后 `EnumTypeDetail` 中的 ChangeHistory 引用自动生效
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 -- ChangeHistory.vue 当前为空占位

### FR-008: 清理 YAML 中冗余的 history tab 配置

- **Description**: 由于 FR-002 实现了智能推导，YAML 中手动配置的 `type: history` tab 成为冗余配置，MUST 清理以遵循单一事实原则。
- **Acceptance Criteria**:
  - 从 `user.yaml`、`role.yaml`、`user_group.yaml` 中移除 `type: history` 的 tab 配置
  - 从 `_template.yaml` 中移除 `type: history` 的 tab 配置
  - 清理后，这三个对象的详情页仍自动显示"变更历史" Tab（通过智能推导）
  - 清理后功能无回退
- **Priority**: Must
- **Type Mapping**: Transition / Solution
- **Source**: 用户要求"YAML 请确保单一事实"

### FR-009: 为未声明 audit_aspect 的对象补充声明

- **Description**: 检查所有业务对象的 YAML，确保需要审计能力的对象都声明了 `aspects: [audit_aspect]`。
- **Acceptance Criteria**:
  - 以下对象 MUST 声明 `aspects: [audit_aspect]`（如果尚未声明）：
    - user（已有，通过 user.yaml 验证）
    - role（已有）
    - user_group（已有）
    - domain（已有）
    - sub_domain（已有）
    - service_module（已有）
    - business_object（已有）
    - relationship（已有）
    - product（已有）
    - version（已有）
    - enum_type（已有）
    - enum_value（已有）
    - annotation（已有）
  - audit_log 自身不需要 audit_aspect（自身即日志）
  - 确认所有需要审计的对象都已声明
- **Priority**: Must
- **Type Mapping**: Solution
- **Source**: 代码分析 -- aspects.yaml + 各对象 YAML

### FR-010: DetailPage 集成分页和详情弹窗

- **Description**: `DetailPage.vue` 中 history tab 的渲染 MUST 传入分页参数，并集成 AuditLogDetail 弹窗。
- **Acceptance Criteria**:
  - 传入 `:total`、`:show-pagination`、`:current-page`、`:page-size` 参数
  - 监听 `@page-change` 和 `@log-click` 事件
  - 集成 `AuditLogDetail` Drawer 组件
  - `useDetail.js` 增加 `auditLogsTotal` 和 `auditLogsPage` 状态
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 -- DetailPage.vue 当前仅传入 logs + loading

### FR-011: 统一 RoleDetailDrawer 和 RolePermissionDetail 中的日志实现

- **Description**: 将 `RoleDetailDrawer` 和 `RolePermissionDetail` 中独立的日志加载和展示逻辑，统一为使用增强版 AuditLog + AuditLogDetail。
- **Acceptance Criteria**:
  - `RoleDetailDrawer` 使用 `AuditLog` 组件替代自行实现的日志 Tab
  - `RolePermissionDetail` 使用 `AuditLog` 组件替代手动集成的日志 Tab
  - 两处均支持分页和详情查看
  - 数据加载改用 `useAuditLogs` 或 `useDetail.loadAuditLogsData()`
- **Priority**: Should
- **Type Mapping**: Transition / Functional
- **Source**: 代码分析 -- 4种不同的日志加载方式

## 4. Nonfunctional Requirements

### NFR-001: 性能 -- 分页加载

- **Description**: 日志数据 MUST 支持分页加载，避免一次性加载大量日志导致页面卡顿。
- **Measurement**: 默认每页 20 条，翻页响应时间 < 500ms
- **Priority**: Must
- **Source**: 当前 `loadAuditLogsData` 一次加载 50 条无分页

### NFR-002: 一致性 -- 统一数据源

- **Description**: 所有日志数据加载 MUST 通过统一的 `useAuditLogs` composable 或 `useDetail.loadAuditLogsData()`，禁止直接调用 `/audit-logs` API。
- **Measurement**: 代码审查无直接调用 `/audit-logs` 的前端代码
- **Priority**: Must
- **Source**: 代码分析 -- 4种不同的日志加载方式

### NFR-003: 设计规范遵循

- **Description**: 所有新增/增强组件 MUST 遵循 UI_COMPONENT_GUIDELINES.md 和 YonDesign 设计规范。
- **Measurement**: 
  - 颜色使用 CSS 变量（`var(--color-*)`），无硬编码
  - 间距使用 CSS 变量（`var(--spacing-*)`）
  - 字体使用 CSS 变量（`var(--font-*)`）
  - 组件使用规范组件（Drawer/Pagination/状态徽章）
- **Priority**: Must
- **Source**: UI_COMPONENT_GUIDELINES.md

### NFR-004: 向后兼容

- **Description**: 智能推导 history tab MUST 与现有手动配置的 history tab 兼容，不产生重复 Tab。
- **Measurement**: user/role/user_group 详情页仍只显示一个"变更历史" Tab
- **Priority**: Must
- **Source**: 过渡需求

## 5. External Interface Requirements

### IF-001: $metadata 端点增强

- **Type**: API
- **Endpoint**: `GET /api/v2/bo/<object>/$metadata`
- **Request/Response**: 响应 JSON 中新增 `aspects` 字段：
  ```json
  {
    "id": "domain",
    "name": "领域",
    "aspects": ["hierarchy_aspect", "audit_aspect", "owner_aspect", "naming_aspect"],
    "fields": [...],
    "ui_view_config": {...}
  }
  ```
- **Error Handling**: 如果对象未声明 aspects，返回空数组 `"aspects": []`
- **Source**: FR-001

### IF-002: 审计日志查询接口

- **Type**: API（已有，无需变更）
- **Endpoint**: `GET /api/v2/bo/<object>/<id>/$associations/audit_logs`
- **Request/Response**: 已支持 page/page_size 参数
- **Source**: 现有 boService.queryAssociations 接口

## 6. Transition Requirements

### TR-001: YAML history tab 配置迁移

- **Description**: 从 user.yaml/role.yaml/user_group.yaml/_template.yaml 中移除手动配置的 `type: history` tab，改由智能推导生成。
- **Strategy**: 先实现智能推导（FR-002），验证功能无回退后，再清理 YAML 配置（FR-008）
- **Rollback Plan**: 如果智能推导出现问题，恢复 YAML 中的 history tab 配置即可
- **Source**: FR-002 + FR-008

### TR-002: 独立日志实现迁移

- **Description**: 将 RoleDetailDrawer 和 RolePermissionDetail 中的独立日志实现迁移为统一组件。
- **Strategy**: 逐个替换，每次替换后验证功能
- **Rollback Plan**: Git revert 对应文件
- **Source**: FR-011

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 前端框架：Vue 3 + Composition API
- UI 组件库：Element Plus + YonDesign 主题
- 元数据驱动：YAML 是单一事实源
- 后端 API：v2 bo_api.py 统一入口

### 7.2 Business Constraints

- 日志数据是只读的，不支持修改/删除
- audit_log 自身不需要 history tab（自身即日志对象）

### 7.3 Assumptions

- 所有声明了 `audit_aspect` 的对象，后端都会正确记录审计日志 -- Source: Verified（audit_interceptor.py 已实现）
- `boService.queryAssociations(objectType, id, 'audit_logs')` 接口已支持分页参数 -- Source: Verified
- `$metadata` 端点当前未返回 `aspects` 字段，需要增强 -- Source: Assumed（需验证）

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|------------|----------|--------|
| FR-001 | $metadata 返回 aspects | Must | 智能推导的前置条件 |
| FR-002 | 智能推导 history tab | Must | 核心价值：单一事实原则 |
| FR-003 | useAuditLogs Composable | Must | 数据层统一 |
| FR-004 | AuditLog 分页筛选 | Must | 基础功能增强 |
| FR-005 | AuditLog 点击展开 | Should | 交互增强 |
| FR-006 | AuditLogDetail 弹窗 | Should | 详情查看 |
| FR-007 | ChangeHistory 重写 | Must | 替换空占位 |
| FR-008 | YAML 冗余配置清理 | Must | 单一事实原则 |
| FR-009 | 补充 audit_aspect 声明 | Must | 确保覆盖完整 |
| FR-010 | DetailPage 集成 | Must | 前端集成 |
| FR-011 | 独立实现统一 | Should | 代码一致性 |

### Suggested Milestones

- **M-LOG-1**: 后端增强 + Composable + AuditLog 增强（FR-001/003/004）
- **M-LOG-2**: 智能推导 + YAML 清理 + DetailPage 集成（FR-002/008/009/010）
- **M-LOG-3**: AuditLogDetail + ChangeHistory + 独立实现统一（FR-005/006/007/011）

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**:
  - 日志数据加载：4种不同方式（useDetail/boService.query/直接API/父组件传入）
  - 日志展示：AuditLog.vue（简单列表）+ ChangeHistory.vue（空占位）
  - history tab 配置：仅在 user/role/user_group 的 YAML 中手动配置
  - aspects 机制：10个对象已声明 `aspects: [audit_aspect]`，但前端无法感知

- **Current Issues**:
  1. 违反单一事实原则：模型层已声明审计能力，UI 层需重复配置
  2. 数据加载不统一：4种方式并存
  3. 组件功能不足：无分页/筛选/详情
  4. ChangeHistory 空占位：从未实现

- **Relevant Code Paths**:
  - `src/composables/useDetail.js` -- loadAuditLogsData()
  - `src/components/common/AuditLog/AuditLog.vue` -- 日志展示组件
  - `src/components/common/DetailPage/DetailPage.vue` -- 详情页 Drawer
  - `src/views/SystemManagement/ChangeHistory.vue` -- 空占位
  - `meta/schemas/aspects.yaml` -- aspect 定义
  - `meta/schemas/*.yaml` -- 各对象 YAML（aspects 声明）
  - `meta/core/yaml_loader.py` -- YAML 解析（parse_aspects_yaml）

### 9.2 Target State

- **Proposed Architecture**:

```
YAML 层（模型声明）:
  aspects: [audit_aspect]  -->  单一事实：声明审计能力

后端层（信息传递）:
  $metadata 端点  -->  返回 aspects: ["audit_aspect"]

前端层（智能推导）:
  useDetail.loadUIConfig()  -->  检测 aspects 包含 audit_aspect
  -->  自动追加 { id: 'history', label: '变更历史', type: 'history' } tab
  -->  无需 YAML 中手动配置

组件层（统一展示）:
  useAuditLogs  -->  统一日志数据加载
  AuditLog (增强版)  -->  分页 + 筛选 + 点击展开
  AuditLogDetail  -->  日志详情 Drawer
  ChangeHistory  -->  自包含组件（ObjectPage 场景）
```

- **Key Changes**:
  1. 后端 $metadata 返回 aspects 数组
  2. 前端 useDetail 根据 aspects 智能推导 history tab
  3. 创建 useAuditLogs composable 统一数据加载
  4. 增强 AuditLog 组件（分页/筛选/点击展开）
  5. 新增 AuditLogDetail 组件（日志详情 Drawer）
  6. 重写 ChangeHistory 组件
  7. 清理 YAML 中冗余的 history tab 配置

### 9.3 Detailed Design

#### 9.3.1 后端 $metadata 端点增强

**文件**: `meta/services/view_config_service.py` 或 `meta/api/bo_api.py`

在 `$metadata` 响应中增加 `aspects` 字段：

```python
# view_config_service.py 或 bo_api.py 中的 metadata 端点
def get_metadata(object_type):
    meta_obj = yaml_loader.load(object_type)
    # ... 现有逻辑 ...
    
    return {
        'id': meta_obj.id,
        'name': meta_obj.name,
        'aspects': meta_obj.aspects or [],  # 新增
        'fields': [...],
        'ui_view_config': {...}
    }
```

#### 9.3.2 前端智能推导 history tab

**文件**: `src/composables/useDetail.js`

在 `loadUIConfig()` 中，检测 aspects 并自动追加 history tab：

```javascript
async function loadUIConfig() {
  const result = await metaService.getUIConfig(objectType)
  
  if (result.success) {
    uiConfig.value = result.data
    
    const uiViewConfig = result.data?.ui_view_config
    const aspects = result.data?.aspects || []
    
    if (uiViewConfig) {
      detailConfig.value = uiViewConfig.detail || null
      
      if (detailConfig.value?.tabs) {
        tabs.value = detailConfig.value.tabs.map(tab => ({
          id: tab.id,
          label: tab.label,
          type: tab.type || 'fields',
          fields: tab.fields || null,
          association: tab.association || null,
          widget: tab.widget || null,
          actions: tab.actions || []
        }))
      }
      
      // 智能推导：如果 aspects 包含 audit_aspect 且无手动配置的 history tab
      const hasManualHistoryTab = tabs.value.some(t => t.type === 'history')
      const hasAuditAspect = aspects.includes('audit_aspect')
      
      if (hasAuditAspect && !hasManualHistoryTab) {
        tabs.value.push({
          id: 'history',
          label: '变更历史',
          type: 'history'
        })
      }
    } else {
      // 无 detail 配置但有 audit_aspect：创建基础 tabs + history
      const aspects = result.data?.aspects || []
      if (aspects.includes('audit_aspect')) {
        tabs.value = [
          { id: 'basic', label: '基本信息', type: 'fields' },
          { id: 'history', label: '变更历史', type: 'history' }
        ]
      }
    }
  }
  
  return result
}
```

**关键设计决策**：

- 智能推导的 history tab 排在手动配置的 tab 之后
- 如果已有手动配置的 `type: history` tab，不重复添加（向后兼容）
- 如果对象完全没有 detail 配置但有 audit_aspect，自动创建基础 tabs + history

#### 9.3.3 useAuditLogs Composable

**文件**: `src/composables/useAuditLogs.js`

```javascript
export function useAuditLogs(objectType, objectId, options = {}) {
  const { pageSize = 20, autoLoad = true } = options

  const logs = ref([])
  const total = ref(0)
  const loading = ref(false)
  const currentPage = ref(1)
  const filters = ref({})

  async function loadLogs(params = {}) {
    if (!objectType || !objectId) return { success: false }
    
    loading.value = true
    const result = await boService.queryAssociations(
      objectType, objectId, 'audit_logs', {
        page: params.page || currentPage.value,
        page_size: params.pageSize || pageSize,
        ...filters.value,
        ...params.filters
      }
    )
    
    if (result.success) {
      logs.value = result.data?.items || []
      total.value = result.data?.total || 0
    }
    
    loading.value = false
    return result
  }

  function setFilters(newFilters) {
    filters.value = { ...newFilters }
    currentPage.value = 1
    return loadLogs()
  }

  function setPage(page) {
    currentPage.value = page
    return loadLogs({ page })
  }

  if (autoLoad && objectType && objectId) {
    onMounted(() => loadLogs())
  }

  return {
    logs, total, loading, currentPage, filters,
    loadLogs, setFilters, setPage
  }
}
```

#### 9.3.4 AuditLog 组件增强

**文件**: `src/components/common/AuditLog/AuditLog.vue`

新增 Props：

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| total | Number | 0 | 日志总数 |
| showFilter | Boolean | true | 是否显示筛选栏 |
| showPagination | Boolean | false | 是否显示分页器 |
| currentPage | Number | 1 | 当前页码 |
| pageSize | Number | 20 | 每页条数 |
| clickMode | String | 'expand' | 点击模式：expand/drawer |

新增 Events：

| Event | Payload | Description |
|-------|---------|-------------|
| page-change | page: Number | 分页变更 |
| filter-change | filters: Object | 筛选变更 |
| log-click | log: Object | 日志条目点击 |

#### 9.3.5 AuditLogDetail 组件

**文件**: `src/components/common/AuditLogDetail/AuditLogDetail.vue`

基于 Drawer 组件，展示单条日志的完整变更内容。

Props：

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| visible | Boolean | false | 是否显示（v-model） |
| log | Object | null | 日志数据 |

#### 9.3.6 ChangeHistory 重写

**文件**: `src/views/SystemManagement/ChangeHistory.vue`

基于 `useAuditLogs` 的自包含组件，接收 `objectType` 和 `objectId` props。

#### 9.3.7 YAML 清理

从以下文件中移除 `type: history` 的 tab 配置：

- `meta/schemas/user.yaml` -- 移除 history tab
- `meta/schemas/role.yaml` -- 移除 history tab
- `meta/schemas/user_group.yaml` -- 移除 history tab
- `meta/schemas/_template.yaml` -- 移除 history tab

清理后，这些对象的详情页通过智能推导自动显示"变更历史" Tab。

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A: 智能推导（基于 aspects） | 遵循单一事实原则，零配置 | 需要后端增强 $metadata | Selected |
| B: 逐对象配置 history tab | 简单直接，无后端改动 | 违反单一事实原则，9个对象需手动配置 | Rejected |
| C: 全局默认开启 history tab | 最简单 | audit_log 等不需要 history 的对象也会出现 | Rejected |

### 9.5 Implementation & Migration Plan

- **Implementation Order**:
  1. M-LOG-1: 后端 $metadata 返回 aspects + useAuditLogs Composable + AuditLog 增强
  2. M-LOG-2: 智能推导 history tab + YAML 清理 + DetailPage 集成
  3. M-LOG-3: AuditLogDetail + ChangeHistory 重写 + 独立实现统一

- **Risk Mitigation**:
  - 智能推导与手动配置冲突 --> 先检测已有 history tab，不重复添加（FR-002）
  - $metadata 端点改动影响范围大 --> 仅新增字段，不修改现有字段
  - YAML 清理导致功能回退 --> 先实现智能推导并验证，再清理 YAML

- **Testing Strategy**:
  - Unit tests: useAuditLogs composable 的加载/分页/筛选逻辑
  - Integration tests: $metadata 端点返回 aspects 字段
  - E2E tests: 每个对象的详情页是否自动显示 history tab
  - Visual tests: AuditLog/AuditLogDetail 组件的渲染效果

- **Rollback Plan**:
  - 如果智能推导出现问题，恢复 YAML 中的 history tab 配置
  - 如果 $metadata 端点改动导致问题，前端可 fallback 到不使用 aspects 推导

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|-------------------|-----------|
| TBD-1 | $metadata 端点当前是否已返回 aspects | 需验证实际 API 响应 | 运行后端验证 |
| TBD-2 | boService.queryAssociations 是否支持 action 筛选参数 | 需验证后端接口 | 查看 bo_api.py |
| TBD-3 | facets 布局的对象如何兼容 tabs 推导 | domain 等对象使用 facets 而非 tabs | 设计时确定转换规则 |
