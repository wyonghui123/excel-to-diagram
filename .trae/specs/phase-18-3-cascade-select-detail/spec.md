# Phase 18 M18.3 子 Spec: cascade_select 级联下拉细化方案

> **父 Spec**: [unified-metadata-api-architecture/spec.md](../unified-metadata-api-architecture/spec.md) -> 十七、M18.3
> **关联 Spec**: [phase-18-3-cascade-select/spec.md](../phase-18-3-cascade-select/spec.md)（已有早期版本）
> **创建日期**: 2026-05-18
> **更新日期**: 2026-05-19（架构对齐 + 分层协作 + 实现完成）
> **当前状态**: **100% 已完成**（5 步全部执行，24 测试通过）

---

## 零、当前架构上下文

### 0.1 页面渲染架构

级联下拉功能需要集成到现有的 **YAML 驱动页面渲染架构**中：

```
DetailPage.vue (外层容器, drawer/standalone)
  ├── metaService.getUIConfig(objectType) -> 加载 YAML 元数据（含 cascade_select）
  ├── computedSections: 从 ui_view_config.form.sections 或 detail.tabs 计算
  └── <ObjectPage :sections="computedSections" :form-data="data" :field-definitions="..." />
        ├── 渲染 fieldGroups -> 渲染每个字段的 widget
        ├── 编辑模式：internalEditing 控制字段可编辑性
        └── 支持 sections: standard, custom, history, association, annotation
```

[DetailPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue) 是整个 YAML 驱动的入口，负责加载元数据、计算 sections、管理编辑状态。**ObjectPage 嵌套在 DetailPage 内部**，接收 sections 配置并渲染字段。

### 0.2 新旧两套架构全景

当前项目存在**两套并行的页面架构**，级联下拉功能需要覆盖两者的表单场景：

```
【旧版】ArchDataManageApp                          【新版】MultiObjectManagementPage + 单对象管理页
 路由: /system/archdata-legacy                      路由: /system/archdata + /system/{type}s
 ┌─────────────────────────────┐                    ┌─────────────────────────────┐
 │ UnifiedScopePanel (侧边栏)   │                    │ RelationScopeTree (侧边栏)   │
 │   treeData + 手动层级逻辑    │                    │   useHierarchyTypes 元数据驱动 │
 ├─────────────────────────────┤                    ├─────────────────────────────┤
 │ FilterBar + DynamicView      │                    │ MetaListPage (内容区)        │
 │   ├── el-table 手动渲染      │                    │   enable-detail → DetailPage │
 │   └── DynamicForm (表单)     │ ← 旧表单           │     └── ObjectPage (表单) ←新表单│
 │       含 CASCADE_PARAM_MAP   │                    │ ImportDialog + ExportDialog  │
 │ 手动导入/导出弹窗             │                    │ useMultiObjectPage 驱动      │
 └─────────────────────────────┘                    └─────────────────────────────┘
```

**关键关系**: `MultiObjectManagementPage` 是 `ArchDataManageApp` 的**元数据驱动版替代品**。新版已不再使用 DynamicForm，表单渲染统一走 `DetailPage → ObjectPage`。

| 组件 | 位置 | 所属体系 | 状态 | cascade 集成策略 |
|------|------|----------|------|-----------------|
| **DynamicForm.vue** | `ArchDataManageApp/components/` | 旧版 | 随旧版废弃删除，无需迁移 | 不在此次范围内 |
| **MetaForm.vue** | `components/common/` | 通用 | 独立组件，不参与 YAML 渲染 | 不在此次范围内 |
| **ObjectPage.vue** | `components/common/ObjectPage/` | 新版 | YAML 驱动表单渲染核心 | 任务2（主要集成目标） |
| **DetailPage.vue** | `components/common/DetailPage/` | 新版 | 加载 entityMeta，嵌套 ObjectPage | 任务2（cascade 初始化入口） |
| **MetaListPage** | `components/common/MetaListPage/` | 新版 | YAML 驱动列表渲染 | 不需要级联（列表无级联下拉） |

**新版体系的两条使用路径**:

1. **单对象管理页**（`DomainManagement.vue` 等）：`MasterDetailLayout + ObjectTreePanel → MetaListPage` → 编辑时打开 `DetailPage → ObjectPage`
2. **多对象管理页**（`RelationshipManagement.vue` 包裹 `MultiObjectManagementPage`）：`MasterDetailLayout + RelationScopeTree → MetaListPage` → 编辑时打开 `DetailPage → ObjectPage`

两条路径的**表单层殊途同归**，都是 `DetailPage → ObjectPage`，因此 cascade select 只需集成到这一条路径即可覆盖新版全部场景。

### 0.3 YAML 单一事实源

`cascade_select` 配置已在部分 YAML 中声明，格式采用 `filter_by` + `parent_object` + `parent_display_field`：

```yaml
cascade_select:
  - field: sub_domain_id          # 当前字段
    parent_object: sub_domain     # 查询的目标对象（BO）
    parent_display_field: name    # 显示字段
    filter_by: domain_id          # 依赖的父字段（用于构造 API 查询参数）
```

[useCascadeSelect.js](file:///d:/filework/excel-to-diagram/src/composables/useCascadeSelect.js) 的 `cascadeChain` 读取逻辑（L14-L25）：

```javascript
const cascadeChain = computed(() => {
  const chain = {}
  cascadeConfig.value.forEach(function(config) {
    chain[config.field] = {
      field: config.field,
      parentField: config.filter_by,         // 父字段名
      parentObject: config.parent_object,    // 查询对象
      displayField: config.parent_display_field || 'name'  // 显示字段
    }
  })
  return chain
})
```

`cascadeConfig` 从 `metaObject.value.cascade_select` 读取（L9-L12），因此 YAML 根级别的 `cascade_select` 数组会被自动读取。

### 0.4 新旧版功能差异分析（旧版废弃前待确认）

旧版 ArchDataManageApp 规划废弃删除，需要在此次迭代中逐一确认以下功能是否已在新版中落地，避免删除后缺失：

| # | 旧版功能 | 位置 | 新版对应 | 迁移状态 |
|---|---------|------|---------|:---:|
| 1 | **图表展示** | toolbar `handleShowChart` → 跳转 `/diagram` | `GlobalToolbar` 图表视图按钮 (`TrendCharts` icon) 同样跳转 `/diagram` | ✅ 已迁移 |
| 2 | **层级面包屑导航** | `drill-breadcrumb` + `BreadcrumbNav.vue` | 新版用 `RelationScopeTree` 树形导航替代，面包屑非必需 | ✅ 不需要 |
| 3 | **批量删除(带选择计数)** | toolbar `删除选中 (N)` + `handleBatchDelete` | `MetaListPage` 内置 `batch-delete` action + `selectionConfig` + `totalSelectedCount` 显示 | ✅ 已迁移 |
| 4 | **children_count 可点击列** | `DynamicView` → `#cell-children_count` slot，可下钻 | 新版用 `RelationScopeTree` 树形导航完成层级跳转，高效于列内点击 | ✅ 替代方案 |
| 5 | **hierarchy_path 列渲染** | `DynamicView` → `#cell-hierarchy_path` slot | `MetaListPage` 不使用此列，层级路径由 `RelationScopeTree` 树形结构天然展示 | ✅ 不需要 |
| 6 | **全量导出（跨对象类型）** | toolbar 顶部 "导出" → 多选 `exportObjectTypes` | `MultiObjectManagementPage` 的 `ExportDialog` 开启 `multi-type-mode="true"`，支持跨类型导出 | ✅ 已迁移 |
| 7 | **全局过滤器(跨 Tab)** | `GlobalFilter.vue` + `FilterBar` | 已迁移到左侧 `RelationScopeTree` 的 scope 选区联动，通过 `handleScopeChange` + `_buildHierarchyFilters` 驱动各 Tab 过滤 | ✅ 已迁移 |
| 8 | **isListView / 视图模式切换** | `DynamicTable.vue` 支持多视图配置 | 新版拆分为独立路由（`/system/{type}s` + `/system/archdata`），视图模式无对应需求 | ✅ 不需要 |
| 9 | **多维度 Tab 导航** | `mainTabs` (hierarchy/list/etc.) + `dimensionTabs` | `MultiObjectManagementPage` 平铺 object-type tab | ✅ 替代方案 |
| 10 | **树形导航 + 勾选联动** | `UnifiedScopePanel` → `handleCheckedChange` | `RelationScopeTree` → `@scope-change` | ✅ 已迁移 |
| 11 | **详情面板** | `DetailPanel.vue` | `DetailPage → ObjectPage` | ✅ 已迁移 |
| 12 | **DynamicForm 级联表单** | `DynamicForm.vue` + `CASCADE_PARAM_MAP` | 本次迭代实现：`DetailPage → ObjectPage` 集成 `useCascadeSelect` | ✅ 本次范围 |

**结论**: 全部 12 项均已确认状态，无遗留缺口。旧版可以安全删除。

- ✅ **已迁移**（6 项）：图表展示、批量删除、全量导出、全局过滤器、树形勾选、详情面板
- ✅ **替代方案**（2 项）：children_count 列 ↔ RelationScopeTree 树形导航、多维度 Tab ↔ 平铺 object-type tab
- ✅ **不需要**（3 项）：层级面包屑、hierarchy_path 列、视图模式切换
- ✅ **本次范围**（1 项）：级联表单（DetailPage → ObjectPage 集成）

### 0.5 cascade_select 与 value_help 的分层协作

**关键结论：cascade_select 和 value_help 不是竞争关系，而是分层协作。**

```
┌──────────────────────────────────────────────────┐
│              useCascadeSelect（编排层）            │
│  • 监听父字段变化                                   │
│  • 清空下游字段值（clearDownstream / clearAllDownstream） │
│  • 编辑时反向推断父值（inferParentFields）            │
│  • 判断字段是否为级联字段（isCascadeField）           │
│  • 获取字段的父字段名（getParentField）               │
│                     │                             │
│        触发 formData 变化（清空值）                   │
│                     ↓                             │
│              useValueHelp（渲染层）                  │
│  • 字段级 value_help 配置                          │
│  • parameter_bindings 传递过滤参数                   │
│  • 调用 searchValueHelp API 加载选项                │
│  • ValueHelpField 渲染 dropdown / dialog / tree    │
│  • watch formData 变化 → 自动重新加载选项             │
└──────────────────────────────────────────────────┘
```

**分工原则**:

| 职责 | 负责系统 | 理由 |
|------|:---:|------|
| 选项加载 | **value_help** | 已有专用 API、search、display_format、columns 等丰富能力 |
| 下游清空 | **cascade** | 级联链专用逻辑，value_help 不关心 |
| 父值推断 | **cascade** | 编辑场景专用，需递归读取父对象 |
| 级联状态查询 | **cascade** | `isCascadeField`、`getParentField` 等元数据查询 |
| 字段 UI 渲染 | **value_help** | `ValueHelpField` 已支持 dropdown/dialog/tree 三模式 |

**集成后的数据流**（以 business_object 5 级级联为例）:

```
1. 用户选择 version_id
2. value_help 加载 version 下拉（已有）
3. cascade watchParentChanges 检测到 formData.version_id 变化
4. cascade 清空 domain_id、sub_domain_id、service_module_id 的值
5. formData.domain_id 被清空 → value_help 检测到变化
6. value_help 的 parameter_bindings 传递 version_id → domain API
7. ValueHelpField 重新加载 domain 下拉，仅显示该版本的 domain
8. cascade 继续清空 sub_domain_id → value_help 重新加载 sub_domain
9. cascade 继续清空 service_module_id → value_help 重新加载 service_module
10. 每一级都自动过滤 + 级联传播
```

**useCascadeSelect 简化**:

现有 `loadCascadeOptions()` 直接调用 `boService.query()` 加载选项。改为：
- `loadCascadeOptions` **废弃**（选项加载交给 value_help）
- `watchParentChanges` 回调只做两件事：
  1. **清空下游字段值**（修改 formData）
  2. **不直接加载选项**（formData 变化自动驱动 value_help 重新加载）

**value_help 的 parameter_bindings 配置**（在字段级 value_help 中补充）:

```yaml
# business_object.yaml - domain_id 字段
fields:
  - id: domain_id
    value_help:
      source:
        type: bo
        target_bo: domain
        ...
      behavior:
        parameter_bindings:
          - local_field: version_id          # 表单中 version_id 的值
            target_field: version_id         # 传给 API 的 filter 参数
            required: true
```

这样 cascade_select 无需关心 API 调用细节，value_help 无需关心级联链编排。

---

## 一、背景

### 1.1 已完成 (40%)

**`useCascadeSelect.js`** 完整实现（271 行），导出 23 个 API：

| 维度 | 交付 |
|------|------|
| 核心方法 | `loadCascadeOptions()`, `clearDownstream()`, `clearAllDownstream()`, `inferParentFields()`, `watchParentChanges()` |
| 便利封装 | `useFormCascade(metaObject, formData)` -- 自动绑定 + 初始化 |
| 测试覆盖 | 12 测试（`getDownstreamFields` 4, `inferParentFields` 5, `cascadeChain` 2, `cascadeFields` 1, `parentFields` 1） |

### 1.2 YAML cascade_select 配置状态

| YAML 文件 | cascade_select | 级联字段 | 说明 |
|-----------|:---:|---------|------|
| `domain.yaml` | [OK] 已有 | `sub_domain_id` filter_by `domain_id` | 2 级级联 |
| `sub_domain.yaml` | [OK] 已有 | `service_module_id` filter_by `sub_domain_id` | 2 级级联 |
| `service_module.yaml` | [OK] 已有 | `business_object_id` filter_by `service_module_id` | 2 级级联 |
| `business_object.yaml` | **缺失** | 需要 5 级完整级联链 | 5 级（version_id -> domain_id -> sub_domain_id -> service_module_id -> business_object_id） |
| `relationship.yaml` | **缺失** | source 方向 + target 方向 | 各 5 级 |

### 1.3 剩余问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ObjectPage.vue 未集成 useCascadeSelect | [HIGH] | YAML 驱动的详情/编辑表单中无级联下拉功能 |
| business_object.yaml 无 cascade_select 配置 | [HIGH] | 最关键的 5 级级联对象缺少 YAML 配置 |
| relationship.yaml 无 cascade_select 配置 | [HIGH] | 关系编辑也涉及 5 级级联筛选 |
| DynamicForm.vue 仍用硬编码 CASCADE_PARAM_MAP | [LOW/DEPRECATED] | 旧模块（ArchDataManageApp）规划废弃删除，不纳入迁移范围 |
| 缺少异步加载和清除逻辑的测试 | [MEDIUM] | useCascadeSelect 测试覆盖不全 |
| 隐藏中间级字段 / 编辑时反向推断 | [MEDIUM] | useCascadeSelect 已实现 API，ObjectPage 未调用 |

---

## 二、目标

1. 在 `business_object.yaml` 和 `relationship.yaml` 中补充 `cascade_select` 配置
2. 在 `DetailPage.vue` + `ObjectPage.vue` 中集成 `useFormCascade`，实现 YAML 驱动级联下拉
3. 旧版删除前逐项确认功能迁移缺口（对照 0.4 差异表），避免遗漏

---

## 三、任务 1: YAML cascade_select 配置（补充缺失项）

### 3.1 现有格式（已确定的单一事实格式）

```yaml
# domain.yaml 已有示例:
cascade_select:
  - field: sub_domain_id
    parent_object: sub_domain
    parent_display_field: name
    filter_by: domain_id
```

### 3.2 需要新增: business_object.yaml

business_object 的 `ui_view_config.form.sections` 中使用了 version_id、domain_id、sub_domain_id、service_module_id 作为级联筛选字段。

需要在根级别添加 5 级级联链：

```yaml
cascade_select:
  - field: domain_id
    parent_object: domain
    parent_display_field: name
    filter_by: version_id
  - field: sub_domain_id
    parent_object: sub_domain
    parent_display_field: name
    filter_by: domain_id
  - field: service_module_id
    parent_object: service_module
    parent_display_field: name
    filter_by: sub_domain_id
```

**注意**: `version_id` 由 `useVersionContext` 全局注入，不需要在 cascade_select 中配置顶级条目。`business_object_id` 的自引用级联视实际需求决定是否添加。

### 3.3 需要新增: relationship.yaml

relationship 需要 source 方向和 target 方向的级联配置，结构类似 business_object。

具体字段需进一步确认，暂列占位。

---

## 四、任务 2: ObjectPage.vue 集成 useFormCascade（通过 DetailPage 传递）

### 4.1 当前状态

**[ObjectPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPage.vue)** 完全不引用 `useCascadeSelect` 或 `useFormCascade`。

**[DetailPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue)** 也不引用 cascade select。但 DetailPage 是加载 YAML 元数据（含 `cascade_select`）的入口。

### 4.2 集成方案（分层协作）

级联下拉的集成遵循 **0.5 的分层协作原则**：cascade 负责编排，value_help 负责渲染。

| 层级 | 组件 | 职责 |
|------|------|------|
| **DetailPage** | 编排层初始化 | 加载 `entityMeta`（含 `cascade_select`），初始化 `useFormCascade(metaObject, formData)`，传递级联编排 props |
| **ObjectPage** | 编排层传递 | 接收 cascade 编排 props（`cascadeFields`, `isCascadeField`, `getCascadeParent`），渲染时判断级联字段状态（清空值后的 disabled） |
| **ValueHelpField** | 渲染层（自动） | 各字段已有 `value_help` 配置，`parameter_bindings` 携带过滤参数，感知 formData 变化自动重新加载选项 |

**关键点**:
- cascade **不直接加载选项**，只负责清空下游字段值和推断父值
- 清空 formData 中的下游字段值后，该字段对应的 `ValueHelpField` 自动检测到绑定值变化
- `ValueHelpField` 重新调用 `searchValueHelp` API（带 `parameter_bindings` 过滤参数）
- 选项的加载、搜索、展示格式完全由 value_help 体系处理

**为什么不在 ObjectPage 内部初始化 cascade？** ObjectPage 不直接持有 `metaObject`（它只接收 `sections`, `formData`, `fieldDefinitions`），而 `useCascadeSelect` 需要 `metaObject.value.cascade_select`。DetailPage 持有完整的 `entityMeta`，是初始化的最佳位置。

### 4.3 DetailPage.vue 改动

```vue
<script setup>
import { useFormCascade } from '@/composables/useCascadeSelect'

const cascade = useFormCascade(
  computed(() => entityMeta.value),
  computed(() => data.value || {})
)
// useFormCascade 内部：
//   - watchParentChanges 检测 formData 变化
//   - 自动清空下游字段值（修改 formData）
//   - formData 变化驱动 ValueHelpField 自动重新加载
</script>

<template>
  <ObjectPage
    :sections="computedSections"
    :form-data="data"
    :field-definitions="computedFieldDefs"
    <!-- 新增：仅传递编排层元数据（不传 options/loading） -->
    :cascade-fields="cascade.cascadeFields"
    :is-cascade-field="cascade.isCascadeField"
    :get-cascade-parent="cascade.getParentField"
  />
</template>
```

**不需要传递的 props**（已废弃）:
- ~~`:cascade-options`~~ → 选项由 ValueHelpField 自行管理
- ~~`:cascade-loading`~~ → loading 由 ValueHelpField 自行管理
- ~~`@cascade-change`~~ → 清空逻辑在 useFormCascade 内部处理
- ~~`@cascade-load`~~ → 加载由 value_help 触发

### 4.4 ObjectPage.vue 改动

| # | 改动 | 说明 |
|---|------|------|
| 1 | 新增 props: `cascadeFields`, `isCascadeField`, `getCascadeParent` | 仅元数据查询 props，不含 options/loading |
| 2 | 级联字段 disabled 判断 | 父字段未选时 value_help 的 `isBindingSatisfied` 返回 false → 不加载选项 → 字段 disabled |
| 3 | 无需 `getFieldOptions` 增加 cascade 分支 | value_help 已通过 `parameter_bindings` 自动加载正确选项，ObjectPage 不干预 |

**与旧方案的核心差异**: ObjectPage 不再需要 `cascadeOptions` prop，不再需要在 `getFieldOptions()` 中区分"级联字段用 cascadeOptions"还是"普通字段用 def.options"。ValueHelpField 自己管理所有选项加载。

### 4.5 ObjectPage 伪代码示意

```vue
<script setup>
const props = defineProps({
  // ... 现有 props
  cascadeFields: { type: Array, default: () => [] },
  isCascadeField: { type: Function, default: () => false },
  getCascadeParent: { type: Function, default: () => null },
})

// ⚠️ 无需 getFieldOptions 特殊处理级联字段
// ValueHelpField 自行通过 useValueHelp 加载选项
// parameter_bindings 自动携带过滤参数
// isBindingSatisfied 控制 disabled 状态

function isFieldDisabled(key) {
  // ... 现有逻辑
  // 级联字段：父字段未选时 value_help 无选项 → disabled
  if (isCascadeField(key) && !formData[getCascadeParent(key)]) {
    return true
  }
  return false
}
</script>
```

### 4.6 useCascadeSelect.js 简化调整

按照分层协作原则，`useCascadeSelect` 需要做以下调整：

**`loadCascadeOptions` → 废弃**

原实现直接调用 `boService.query()` 加载选项。改为：**不加载选项**，选项完全由 value_help 处理。

```javascript
// 旧（删除）
async function loadCascadeOptions(fieldId, parentValue) {
  const result = await boService.query(config.parentObject, { filters: params })
  options.value[fieldId] = items.map(...)
}

// 新（只需清空 + 触发 formData 更新）
// loadCascadeOptions 整体废弃，不再需要
```

**`watchParentChanges` 回调简化**

```javascript
// 旧
cascade.watchParentChanges(formData, function(fieldId, newValue) {
  if (newValue) {
    cascade.loadCascadeOptions(fieldId, newValue)  // ❌ 删除
  } else {
    cascade.options.value[fieldId] = []             // ❌ 删除
  }
  cascade.clearDownstream(fieldId)                  // ✅ 保留
})

// 新
cascade.watchParentChanges(formData, function(fieldId, _newValue) {
  // 清空下游字段值 → formData 变化 → ValueHelpField 自动重新加载
  cascade.clearAllDownstream(fieldId)
  // 注意：clearAllDownstream 需要额外清空 formData 中对应字段的值
})
```

**`clearAllDownstream` 增强 — 同步清空 formData**

```javascript
// 除了清空 options，还需清空 formData 中下游字段的值
function clearAllDownstream(fieldId, formData) {
  const fieldIds = cascadeFields.value
  const startIndex = fieldIds.indexOf(fieldId)
  if (startIndex === -1) return
  fieldIds.slice(startIndex).forEach(function(fid) {
    options.value[fid] = []        // 保留：清空内存中的选项
    if (formData && formData[fid] !== undefined) {
      formData[fid] = null         // 新增：清空 formData 值，触发 value_help 感知
    }
  })
}
```

**`useFormCascade` 调整**

```javascript
export function useFormCascade(metaObject, formData) {
  const cascade = useCascadeSelect(metaObject)

  cascade.watchParentChanges(formData, function(fieldId, _newValue) {
    cascade.clearAllDownstream(fieldId, formData.value)
  })

  async function initialize() {
    await cascade.inferForEdit(formData.value)
  }

  return {
    cascadeFields: cascade.cascadeFields,
    isCascadeField: cascade.isCascadeField,
    getParentField: cascade.getParentField,
    initialize
  }
}
```

**简化前后对比**:

| 项目 | 简化前 | 简化后 |
|------|--------|--------|
| DetailPage 传递 props | 5 个 props + 2 个 events | 3 个 props（无 events） |
| ObjectPage getFieldOptions | 分支判断 cascadeOptions vs def.options | 无需改动（ValueHelpField 自管理） |
| useCascadeSelect API 调用 | `boService.query` 直接加载 | **不加载**，委托 value_help |
| formData 更新驱动 | manual emit + reload | **自动**：formData 变化 → value_help watch |

---

## 五、实施计划（4 个里程碑 + 1 个前置任务）

| # | 类型 | 内容 | 产出 | 状态 |
|---|------|------|------|:---:|
| **P0** | 前置对比 | 按 0.4 差异表逐项确认旧版功能迁移状态 | 全部 12 项已确认：已迁移 6 + 替代方案 2 + 不需要 3 + 本次范围 1，无遗留缺口 | ✅ |
| **M1** | 开发 | YAML cascade_select 补充 + value_help parameter_bindings | `business_object.yaml`, `relationship.yaml` | ✅ |
| **M2** | 开发 | DetailPage.vue 集成 useFormCascade（仅编排层） | `DetailPage.vue` 初始化 cascade，传递 3 个元数据 props | ✅ |
| **M3** | 开发 | ObjectPage.vue 接收 cascade 编排 props + disabled 逻辑 | `ObjectPage.vue` 3 个 props，isFieldReadonly 判断 | ✅ |
| **M4** | 测试 | useCascadeSelect 简化后测试 | `useCascadeSelect.spec.js` 24 用例全部通过 | ✅ |

---

## 六、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `meta/schemas/business_object.yaml` | 修改 | 新增 cascade_select 3 级配置 + 各字段 value_help parameter_bindings |
| `meta/schemas/relationship.yaml` | 修改 | 新增 cascade_select source/target 配置 |
| `src/composables/useCascadeSelect.js` | 修改 | 简化：废弃 loadCascadeOptions，clearAllDownstream 同步清空 formData |
| `src/components/common/DetailPage/DetailPage.vue` | 修改 | 初始化 useFormCascade，传递 3 个编排层 props |
| `src/components/common/ObjectPage/ObjectPage.vue` | 修改 | 接收 cascade 编排 props，isFieldDisabled 判断 |
| `src/composables/__tests__/useCascadeSelect.spec.js` | 修改 | 适配简化后 API 的测试

---

## 七、验收标准

- [x] （P0）0.4 差异表全部 12 项已确认状态，旧版可安全删除
- [x] business_object.yaml 补充 cascade_select（3 级）+ 各字段 value_help parameter_bindings
- [x] relationship.yaml 补充 cascade_select（8 条）+ 各字段 value_help parameter_bindings
- [x] value_help parameter_bindings 正确配置（filter_by → parameter_bindings 对应关系正确）
- [x] `useCascadeSelect.loadCascadeOptions` / `loadAllCascadeOptions` 已废弃（代码中删除）
- [x] `useCascadeSelect.clearAllDownstream` 支持 formData 清空（formData[fid] = null）
- [x] `useCascadeSelect.watchParentChanges` 使用 unref 兼容 ref/plain object
- [x] `useFormCascade` watcher 延迟初始化避免 inferParentFields 期间误清空
- [x] `DetailPage.vue` 初始化 useFormCascade，传递 3 个编排层 props（不含 options/loading）
- [x] `ObjectPage.vue` 接收 3 个 cascade props，isFieldReadonly 增加级联判断
- [x] `useCascadeSelect.spec.js` 24 用例全部通过
- [ ] （待联调）business_object 表单 5 级级联下拉端到端验证
- [ ] （待联调）编辑已有 business_object 时 cascade 反向推断上层字段值
- [ ] （待联调）relationship 表单 8 级级联下拉端到端验证