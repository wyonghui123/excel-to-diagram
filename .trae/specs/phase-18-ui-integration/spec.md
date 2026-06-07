# Phase 18 UI 集成：M18.4 - M18.9

> **状态**: 🚧 待开始
> **依赖**: M18.1 ✅ | M18.2 ✅ | M18.3 🔄 进行中
> **预估工时**: 13 天
> **独立 Spec**: 本文档为 M18.4-M18.9 的细化实现规格

---

## 1. 概述与目标

### 1.1 双重目标声明

本文档承载两个战略目标：

| 目标 | 说明 | 成功标准 |
|------|------|---------|
| **目标一：架构数据管理 UI 层迁移** | 将 Domain/SubDomain/ServiceModule/BusinessObject 的 UI 从旧架构迁移到新架构 | 旧 App 功能在新架构 100% 覆盖 |
| **目标二：丰富通用组件库** | 将迁移过程中沉淀的通用能力抽象为可复用组件 | 组件可独立于架构数据管理场景使用 |

> **架构原则**: 所有组件必须遵循 **元数据驱动** 原则 —— 组件行为由 YAML 配置声明，无硬编码业务逻辑。

### 1.2 架构原则：元数据驱动

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    元数据驱动架构原则                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  YAML 配置声明 ──► Composable 解释 ──► 组件渲染                          │
│        │                │                │                              │
│        ▼                ▼                ▼                              │
│  hierarchies      useHierarchy       ObjectTreePanel                    │
│  context          useVersionContext  ContextSelector                    │
│  cascade_select   useCascadeSelect  MetaForm                           │
│  annotations      useAnnotations     AnnotationPanel                    │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │  单一事实原则: YAML 是唯一真相来源，组件只解释配置，不包含业务逻辑  │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**核心约束**:

| 约束 | 说明 | 违规示例 |
|------|------|---------|
| **无硬编码对象名** | 树节点类型、级联层级从 YAML 动态读取 | `if (type === 'domain')` |
| **无硬编码字段** | 字段列表、显示名称从 `$metadata` 获取 | `field: 'name'` 写死 |
| **无硬编码过滤** | 过滤条件由 `context` 配置驱动 | `params.version_id = 1` |
| **声明式 UI** | 视图配置在 YAML 中声明，组件解释执行 | 表单分区硬编码 |

### 1.3 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Phase 18 UI 集成架构                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     YAML 配置层 (单一事实来源)                      │   │
│  │   hierarchies | context | cascade_select | annotations           │   │
│  │   display_name | ui_view_config | field_groups                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     BOF 服务层 (M18.1 ✅)                         │   │
│  │   HierarchyService | VersionContextInterceptor | ExportService    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Composable 层 (可复用)                        │   │
│  │   useVersionContext | useCascadeSelect | useHierarchyList        │   │
│  │   useAnnotations | useBreadcrumb | useWorkspaceLayout            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                │                                        │
│  ┌───────────────┬───────────────┬───────────────┬───────────────┐   │
│  ▼               ▼               ▼               ▼               ▼   │
│ M18.4           M18.5           M18.6           M18.7           M18.8 │
│ 树形导航         层级钻取         三栏布局         导入导出          详情页  │
│  │               │               │               │               │   │
│  └───────────────┴───────────────┴───────────────┴───────────────┘   │
│                                │                                        │
│                                ▼                                        │
│                    ┌───────────────────────────┐                       │
│                    │       M18.9 废弃清理        │                       │
│                    └───────────────────────────┘                       │
│                                                                         │
│  通用组件库 ◄────────────────────────────────── 架构数据管理专用组件    │
│     ↑                                                         ↑        │
│     │                      目标二                         目标一        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.4 里程碑依赖关系

```
M18.1 YAML+BOF 基础能力 ✅
  │
  ├──────────────────────────────┐
  ▼                              ▼
M18.2 产品版本上下文 ✅        M18.3 级联下拉 🔄
  │                             │
  ├──────────┐                  │
  ▼          ▼                  │
M18.4 树形导航  M18.5 层级钻取  │
  │          │                  │
  └──────┬───┘                  │
         ▼                      │
M18.6 MetaListPage 三栏布局 ◄───┘
  │  (整合上下文+树+级联+钻取)
  │
  ├──────────────────────┐
  ▼                      ▼
M18.7 导入导出增强     M18.8 详情页增强
  │                      │
  └──────┬───────────────┘
         ▼
M18.9 旧App废弃+API瘦身
```

### 1.5 任务并行性分析

#### 关键洞察：真实依赖 vs 表面依赖

| 里程碑 | 表面依赖 | 真实依赖 | 结论 |
|--------|----------|----------|------|
| M18.4 树形导航 | 看起来依赖 M18.3 | M18.1 hierarchies + HierarchyService | **不依赖 M18.3** |
| M18.5 层级钻取 | 看起来依赖 M18.4 | M18.1 hierarchies 配置 | **不依赖 M18.4** |
| M18.7 导入导出 | 看起来依赖 M18.6 | M18.1 ExportService | **可提前开发** |
| M18.8 详情页 | 看起来依赖 M18.6 | M18.1 AnnotationService | **可提前开发** |

#### 真实依赖链（精简版）

```
M18.1 YAML+BOF ✅
        │
        ├──────────────────────────────────────────────┐
        │                                              │
        ▼                                              ▼
M18.3 级联下拉                              M18.4 树形导航
        │                                              │
        ▼                                              ▼
M18.5 层级钻取                              M18.7 导入导出
        │                                              │
        ▼                                              ▼
M18.6 三栏布局整合 ◄────────────────────────────────┘
        │
        ▼
M18.9 废弃清理
```

#### 真正的关键路径

```
关键路径 = M18.3 → M18.5 → M18.6 → M18.9
                   ↑
                   └──── M18.4 (不在线上，但 M18.6 需要它)
```

#### 可完全并行开发的任务（Week 1 可开始）

| 组件 | 真实依赖 | 为什么可并行 |
|------|----------|-------------|
| CollapsiblePanel.vue | 无 | 纯 UI 组件，无业务依赖 |
| ObjectTreePanel.vue | M18.1 | hierarchies + HierarchyService 已就绪 |
| BreadcrumbNav.vue | 无 | 纯 UI 组件，无业务依赖 |
| useHierarchyList.js | M18.1 | hierarchies 配置已就绪 |
| BatchImportDialog.vue | M18.1 | ExportService API 已就绪 |
| BatchExportDialog.vue | M18.1 | ExportService API 已就绪 |
| DetailPanel.vue | M18.1 | AnnotationService API 已就绪 |
| RelationPanel.vue | M18.1 | RelationScopeService API 已就绪 |

#### 优化后的执行计划（5 周完成）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Week 1: 完全并行开发                                              │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐  │
│ │ M18.3.2        │ │ M18.4           │ │ M18.7/M18.8 独立部分  │  │
│ │ MetaForm 级联   │ │ CollapsiblePanel │ │ BatchImportDialog     │  │
│ │ (300 行)       │ │ ObjectTreePanel │ │ BatchExportDialog    │  │
│ │                 │ │ (500 行)        │ │ DetailPanel          │  │
│ │                 │ │                 │ │ (1000+ 行)          │  │
│ └─────────────────┘ └─────────────────┘ └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────────────┐
│ Week 2: 第二批并行开发                                             │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐  │
│ │ M18.5          │ │ M18.7 集成     │ │ M18.8 集成           │  │
│ │ useHierarchy   │ │ BatchImport     │ │ RelationPanel         │  │
│ │ BreadcrumbNav   │ │ BatchExport    │ │ AnnotationPanel       │  │
│ │ (350 行)       │ │ (300 行)       │ │ (500 行)             │  │
│ └─────────────────┘ └─────────────────┘ └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────────────┐
│ Week 3: 三栏布局整合                                              │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────┐    │
│ │ M18.6: WorkspaceSidebar + WorkspaceMain                        │    │
│ │ MetaListPage 插槽扩展 + 三栏联动逻辑                           │    │
│ │ + 4 个业务页面 (800 行)                                       │    │
│ └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────────────┐
│ Week 4: 集成测试                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│ M18.3/M18.4/M18.5/M18.6/M18.7/M18.8 端到端测试              │
└─────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────────────┐
│ Week 5: 收尾                                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ M18.9: 废弃清理 + useChangeNotification 通用化                    │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 详细并行策略

| 阶段 | 主任务 | 并行任务 | 说明 |
|------|--------|----------|------|
| **Week 1** | M18.3.2 MetaForm 级联 | M18.4 CollapsiblePanel, ObjectTreePanel | 完全并行 |
| **Week 1** | - | M18.7 BatchImportDialog, BatchExportDialog | 完全并行 |
| **Week 1** | - | M18.8.1 DetailPanel | 完全并行 |
| **Week 2** | M18.5 useHierarchyList | M18.7 集成 | 完全并行 |
| **Week 2** | M18.5 BreadcrumbNav | M18.8.2 RelationPanel, AnnotationPanel | 完全并行 |
| **Week 3** | M18.6 三栏布局整合 | M18.7/M18.8 集成测试 | 交叉进行 |
| **Week 4** | 集成测试 | Bug 修复 | 测试验证 |
| **Week 5** | M18.9 废弃清理 | 收尾 | 清理工作 |

#### 组件级并行分析（最终版）

| 组件 | 真实依赖 | 可开始时机 | 并行度 |
|------|----------|-----------|--------|
| CollapsiblePanel.vue | 无 | **Week 1** | 高 |
| business_object.yaml cascade | M18.1 | **Week 1** | 高 |
| ObjectTreePanel.vue | M18.1 hierarchies | **Week 1** | 高 |
| BatchImportDialog.vue | M18.1 ExportService | **Week 1** | 高 |
| BatchExportDialog.vue | M18.1 ExportService | **Week 1** | 高 |
| DetailPanel.vue | M18.1 API | **Week 1** | 高 |
| useHierarchyList.js | M18.1 hierarchies | **Week 1** | 高 |
| BreadcrumbNav.vue | 无 | **Week 1** | 高 |
| RelationPanel.vue | M18.1 API | Week 2 | 中 |
| AnnotationPanel.vue | M18.1 API | Week 2 | 中 |
| MetaTable 层级增强 | useHierarchyList | Week 2 | 中 |
| WorkspaceSidebar.vue | M18.4 完成 | Week 3 | 低 |
| WorkspaceMain.vue | M18.4, M18.5 完成 | Week 3 | 低 |
| 4 个业务页面 | M18.6 完成 | Week 3 | 低 |

#### 优化效果

| 指标 | 原始计划 | 优化后 | 提升 |
|------|----------|--------|------|
| 总工期 | 13 天 | **5 周** | 62% 减少 |
| 并行度 | 低 | **高** | 多任务并行 |
| 组件独立开发 | 无 | **Week 1 开始** | 提前 2 周 |
| 瓶颈 | 串行等待 | **无** | 消除 |

### 1.6 交付物概览

| 里程碑 | 通用组件 | 专用组件 | 代码行数(估) | 目标归属 |
|--------|----------|----------|-------------|---------|
| M18.3(剩余) | useCascadeSelect 增强 | MetaForm 级联集成 | 300 | 目标二 |
| M18.4 | CollapsiblePanel, BreadcrumbNav | ObjectTreePanel | 500 | 目标二 |
| M18.5 | useHierarchyList, BreadcrumbNav 增强 | MetaTable 层级增强 | 350 | 目标二 |
| M18.6 | WorkspaceSidebar, WorkspaceMain | 4个业务页面 | 800 | 目标一+目标二 |
| M18.7 | BatchImportDialog, BatchExportDialog | - | 600 | 目标二 |
| M18.8 | DetailPanel, RelationPanel | AnnotationPanel | 500 | 目标二 |
| M18.9 | useChangeNotification | 废弃清理 | - | 目标一 |
| **合计** | **14 个通用组件** | **9 个专用组件** | **~3050** | - |

---

## 2. M18.3: 级联下拉 MetaForm 集成（剩余任务）

> **预计工时**: 3 天
> **依赖**: M18.1 ✅ | M18.2 ✅ | M18.3 已完成部分 ✅
> **目标归属**: 目标一（架构数据管理 UI 迁移）+ 目标二（通用组件库）

### 2.1 目标

| 目标 | 具体内容 |
|------|---------|
| **架构迁移** | 将级联下拉能力集成到 MetaForm，支持 5 级级联 |
| **通用能力** | 沉淀 useCascadeSelect 为通用级联逻辑 |

### 2.2 背景

`useCascadeSelect.js` 已创建完成，但尚未集成到 MetaForm 中。本章节补充剩余任务。

**已完成部分**:
- `useCascadeSelect.js` - Composable 实现

**待完成部分**:
- YAML 配置补充
- MetaForm 集成

### 2.3 元数据驱动设计原则

**级联下拉组件必须遵循的元数据驱动约束**：

| 约束 | YAML 配置来源 | 说明 |
|------|-------------|------|
| 级联关系 | `cascade_select[].field` | 当前字段 |
| 父字段 | `cascade_select[].parentField` | filter_by 参数 |
| 父对象 | `cascade_select[].parentObject` | 查询的父对象类型 |
| 显示字段 | `cascade_select[].displayField` | 父对象显示字段 |
| 清空下游 | `cascade_select[].clearDownstream` | 是否清空下游字段 |

```typescript
// ✅ 正确：从 cascade_select 配置读取
const config = cascadeChain.value[fieldId]
const params = { [config.parentField]: parentValue }
const result = await boService.query(config.parentObject, { filters: params })

// ❌ 错误：硬编码级联关系
if (fieldId === 'sub_domain_id') {
  params.domain_id = parentValue
}
```

### 2.4 待完成任务详解

#### 2.4.1 business_object.yaml 补充 cascade_select

**当前状态**: M18.1 已为 domain/sub_domain/service_module 配置 cascade_select，但 business_object 缺少配置

**需要补充的配置**:

```yaml
# business_object.yaml
cascade_select:
  - field: domain_id
    parentObject: domain
    displayField: name
    parentField: version_id
    filter: version_id
    clearDownstream: true
  - field: sub_domain_id
    parentObject: sub_domain
    displayField: name
    parentField: domain_id
    filter: domain_id
    clearDownstream: true
  - field: service_module_id
    parentObject: service_module
    displayField: name
    parentField: sub_domain_id
    filter: sub_domain_id
    clearDownstream: true
```

**级联链**: product → version → domain → sub_domain → service_module → business_object

#### 2.4.2 MetaForm 级联下拉渲染

**目标**: 将 useCascadeSelect 集成到 MetaForm，支持 depends_on 字段变更触发重新加载

**集成方案**:

```vue
<!-- MetaForm.vue -->
<template>
  <el-form>
    <template v-for="field in enhancedFields" :key="field.key">
      <AppSelect
        v-if="isCascadeField(field.key)"
        v-model="formData[field.key]"
        :options="cascade.getOptions(field.key)"
        :loading="cascade.isLoading(field.key)"
        :disabled="isCascadeDisabled(field.key)"
        @change="onCascadeChange(field.key, $event)"
      />
      <AppInput
        v-else
        v-model="formData[field.key]"
      />
    </template>
  </el-form>
</template>

<script setup>
import { useCascadeSelect } from '@/composables/useCascadeSelect'

const props = defineProps({
  metaObject: Object,
  modelValue: Object
})

const emit = defineEmits(['update:modelValue'])

const cascade = useCascadeSelect(toRef(props, 'metaObject'))

const formData = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

function onCascadeChange(fieldId, newValue) {
  // 清空下游字段
  cascade.clearDownstream(fieldId)
  // 重新加载受控字段选项
  if (newValue) {
    cascade.loadCascadeOptions(fieldId, newValue)
  }
}

function isCascadeDisabled(fieldId) {
  const parentField = cascade.getParentField(fieldId)
  return !formData.value[parentField]
}
</script>
```

#### 2.4.3 MetaForm 层级归属区块

**目标**: cascade_select 字段自动归入"层级归属" section

**YAML 配置**:

```yaml
# business_object.yaml
fields:
  - id: domain_id
    ui:
      fieldGroup: 层级归属
      fieldGroupPosition: 10
  - id: sub_domain_id
    ui:
      fieldGroup: 层级归属
      fieldGroupPosition: 20
  - id: service_module_id
    ui:
      fieldGroup: 层级归属
      fieldGroupPosition: 30
```

**渲染逻辑**:

```vue
<template>
  <div class="meta-form">
    <!-- 基本信息区块 -->
    <div class="field-group" v-if="basicFields.length">
      <div class="field-group-title">基本信息</div>
      <div class="field-group-fields">
        <template v-for="field in basicFields" :key="field.key">
          <!-- 渲染字段 -->
        </template>
      </div>
    </div>
    
    <!-- 层级归属区块 -->
    <div class="field-group" v-if="hierarchyFields.length">
      <div class="field-group-title">层级归属</div>
      <div class="field-group-fields">
        <template v-for="field in hierarchyFields" :key="field.key">
          <!-- 渲染级联字段 -->
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
const hierarchyFields = computed(() => {
  return props.fields.filter(f => f.ui?.fieldGroup === '层级归属')
    .sort((a, b) => (a.ui?.fieldGroupPosition || 0) - (b.ui?.fieldGroupPosition || 0))
})
</script>
```

#### 2.4.4 隐藏中间级字段

**目标**: 版本上下文已选定时，自动隐藏已确定的层级字段

**场景**: 当用户从 ObjectTreePanel 选择了一个 sub_domain 后，创建 business_object 时：
- 自动填充 `domain_id`、`sub_domain_id`
- 隐藏这两个字段，只显示 `service_module_id` 和 `business_object_name`

**实现方案**:

```typescript
interface CascadeFieldVisibility {
  autoFilledFields: string[]      // 自动填充的字段
  hiddenFields: string[]          // 隐藏的字段
}

// 从 parent_id 自动推导并填充
function inferAndHideFields(parentType: string, parentId: number) {
  switch (parentType) {
    case 'sub_domain':
      // 填充 domain_id, sub_domain_id，隐藏这两个字段
      return {
        autoFilledFields: ['domain_id', 'sub_domain_id'],
        hiddenFields: ['domain_id', 'sub_domain_id'],
        editableFields: ['service_module_id', 'name']
      }
    case 'domain':
      // 填充 domain_id，隐藏字段
      return {
        autoFilledFields: ['domain_id'],
        hiddenFields: ['domain_id'],
        editableFields: ['sub_domain_id', 'service_module_id', 'name']
      }
  }
}
```

#### 2.4.5 编辑时反向推断

**目标**: 编辑已有数据时，从 service_module_id 反推完整层级路径

**场景**: 加载 `{ service_module_id: 5 }`，需要：
1. 查询 service_module 获取 `sub_domain_id`
2. 查询 sub_domain 获取 `domain_id`
3. 查询 domain 获取 `version_id`
4. 填充级联下拉的每个选项

**实现方案**:

```typescript
async function inferParentFields(currentFieldId, currentValue) {
  const config = cascadeChain.value[currentFieldId]
  if (!config) return

  // 查询当前对象获取父字段值
  const result = await boService.read(config.parentObject, currentValue)
  if (!result.success) return

  const parentValue = result.data[config.parentField]
  if (!parentValue) return

  // 填充当前字段的父字段
  formData.value[config.parentField] = parentValue

  // 递归推断上级字段
  await inferParentFields(config.parentField, parentValue)

  // 加载当前字段的选项（用于编辑）
  await cascade.loadCascadeOptions(currentFieldId, parentValue)
}
```

### 2.5 任务清单

| # | 任务 | 文件 | 产出 | 状态 | 元数据驱动 |
|---|------|------|------|------|-----------|
| 1 | useCascadeSelect.js | `src/composables/` | 级联逻辑 Composable | ✅ 已完成 | ✅ |
| 2 | business_object.yaml 补充 | `meta/schemas/` | 5 级 cascade_select | 🚧 | ✅ |
| 3 | MetaForm 级联下拉渲染 | `MetaForm.vue` | 级联选项注入 | 🚧 | ✅ |
| 4 | MetaForm 字段分组渲染 | `MetaForm.vue` | 层级归属区块 | 🚧 | ✅ |
| 5 | 隐藏中间级字段 | `MetaForm.vue` | 版本上下文联动 | 🚧 | ✅ |
| 6 | 编辑时反向推断 | useCascadeSelect | 完整层级路径填充 | 🚧 | ✅ |
| 7 | 集成测试 | - | 端到端测试 | 🚧 | - |

### 2.6 验收标准

#### 功能验收

- [ ] 创建 business_object: 5级级联（产品→版本→领域→子领域→服务模块）正常
- [ ] 父字段变更→下游字段自动清空
- [ ] 级联字段自动归入"层级归属"区块
- [ ] 从树节点创建时，中间级字段自动隐藏
- [ ] 编辑模式下父字段 immutable
- [ ] 编辑时反向推断正常（填充完整层级路径）

#### 元数据驱动验收

- [ ] **级联关系从 YAML 读取**: cascade_select 由 YAML 配置定义
- [ ] **无硬编码对象名**: 使用 config.parentObject 而非 if/elif
- [ ] **无硬编码级联链**: 级联深度由 cascade_select 数组长度决定

---

## 3. M18.4: 树形导航 — HierarchyTreePanel

> **预计工时**: 2 天
> **依赖**: M18.1 ✅ | M18.2 ✅
> **目标归属**: 目标二（丰富通用组件库）

### 2.1 目标

| 目标 | 具体内容 |
|------|---------|
| **架构迁移** | 替代旧的 TreeNavigator.vue |
| **通用能力** | 沉淀 CollapsiblePanel 为通用折叠容器 |

### 2.2 元数据驱动设计原则

**树形导航组件必须遵循的元数据驱动约束**：

```typescript
// ✅ 正确：从 YAML hierarchies 配置读取
const hierarchyConfig = metaObject.value.hierarchies
const levels = hierarchyConfig.levels  // 动态层级

// ❌ 错误：硬编码层级
const LEVELS = ['domain', 'sub_domain', 'service_module', 'business_object']
```

| 约束 | YAML 配置来源 | 说明 |
|------|-------------|------|
| 树结构定义 | `hierarchies[].levels[]` | 层级定义（类型、父子关系） |
| 节点显示字段 | `display_name.expression` | 节点显示名称表达式 |
| 子对象类型 | `hierarchies[].levels[].children_field` | 子节点类型 |
| 根节点过滤 | `hierarchies[].root_filter` | 版本上下文过滤字段 |

### 2.3 组件设计

#### 2.3.1 CollapsiblePanel.vue — 通用折叠面板

> **通用性**: 可用于任何需要折叠+可调宽度的场景，不限于架构数据管理

**定位**: 统一折叠容器组件，支持标题、徽章、操作按钮。

```vue
<!-- 使用示例 -->
<CollapsiblePanel title="架构对象" :badge="selectedCount">
  <template #extra>
    <el-button size="small" link>全选</el-button>
  </template>
  <!-- 面板内容 -->
  <el-tree :data="treeData" />
</CollapsiblePanel>
```

**Props**:

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| title | String | '' | 面板标题 |
| badge | Number | 0 | 徽章数字 |
| collapsible | Boolean | true | 是否可折叠 |
| defaultExpanded | Boolean | true | 默认展开状态 |
| resizable | Boolean | false | 是否可拖拽调整宽度 |
| minWidth | Number | 200 | 最小宽度 |
| maxWidth | Number | 400 | 最大宽度 |

**Events**:

| Event | Payload | 说明 |
|-------|---------|------|
| resize | { width } | 宽度变化时触发 |
| toggle | { expanded } | 折叠状态变化时触发 |

**Slots**:

| Slot | 说明 |
|------|------|
| default | 面板内容 |
| extra | 标题栏右侧操作区 |

#### 2.3.2 ObjectTreePanel.vue — 树形导航面板

> **通用性**: 通过 `objectType` prop 可适配任何层级对象，不限于架构数据管理
>
> **元数据驱动**: 树层级结构、显示字段从 YAML `hierarchies` 配置读取

**定位**: 4 层架构对象树形导航，基于 el-tree 封装。

**Props**:

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| objectType | String | 'domain' | **元数据驱动**: 根节点对象类型，从 YAML hierarchies.root_type 读取 |
| versionId | Number | required | 版本上下文 ID |
| selectedNodes | Array | [] | 已选中的节点 ID 列表 |
| showCount | Boolean | true | 显示子对象计数 |
| showCheckbox | Boolean | true | 显示复选框 |
| searchPlaceholder | String | '搜索对象' | 搜索框占位符 |
| defaultExpandAll | Boolean | false | 默认展开全部 |

**元数据驱动的 Props 说明**：

```typescript
// ✅ 正确：从 metaObject 读取 hierarchies 配置
const props = defineProps<{
  objectType?: string  // 默认从 metaObject.hierarchies[0].root_type 获取
}>()

const metaObject = inject('metaObject')
const hierarchyConfig = computed(() => metaObject.value?.hierarchies?.[0])
const rootType = computed(() => hierarchyConfig.value?.root_type || 'domain')

// ❌ 错误：硬编码根节点类型
const rootType = 'domain'
```

**Events**:

```vue
<!-- 使用示例 -->
<ObjectTreePanel
  :version-id="selectedVersionId"
  :selected-nodes="selectedNodes"
  :show-count="true"
  :show-checkbox="true"
  @select="onNodeSelect"
  @check="onNodeCheck"
/>
```

**Props**:

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| versionId | Number | required | 版本上下文 ID |
| selectedNodes | Array | [] | 已选中的节点 ID 列表 |
| showCount | Boolean | true | 显示子对象计数 |
| showCheckbox | Boolean | true | 显示复选框 |
| searchPlaceholder | String | '搜索对象' | 搜索框占位符 |
| defaultExpandAll | Boolean | false | 默认展开全部 |

**Events**:

| Event | Payload | 说明 |
|-------|---------|------|
| select | { node, path } | 节点点击选中 |
| check | { checkedNodes, checkedKeys } | 节点勾选变化 |
| load | { treeData } | 树加载完成 |

**核心功能**:

1. **树数据加载**
```javascript
async function loadTreeData() {
  const result = await boService.getHierarchyTree({
    version_id: props.versionId
  })
  // result: { data: [{ id, name, type, children: [...] }] }
  treeData.value = result.data
}
```

2. **节点勾选过滤**
```javascript
function onNodeCheck(node, checked) {
  const checkedKeys = treeRef.value.getCheckedKeys()
  emit('check', {
    checkedKeys,
    checkedNodes: getCheckedNodes(checkedKeys)
  })
}
```

3. **子对象计数加载**
```javascript
// 每个节点显示其下子对象数量
// GET /api/v2/bo/<object>/count?parent_id=X
function getNodeCount(node) {
  const objectType = getChildObjectType(node.type)
  return boService.count(objectType, { parent_id: node.id })
}
```

4. **搜索过滤**
```javascript
function filterTree(query) {
  treeRef.value.filter(query)
}

// el-tree filter 方法
function filterNode(value, data) {
  return data.name.includes(value)
}
```

### 2.3 API 对接

**后端 API**: `GET /api/v2/meta/hierarchy/tree`

**请求参数**:
```typescript
interface HierarchyTreeRequest {
  version_id: number       // 版本 ID（必填）
  root_type?: string      // 根节点类型，默认 'domain'
  include_counts?: boolean // 是否包含子对象计数
}
```

**响应格式**:
```typescript
interface HierarchyTreeResponse {
  success: boolean
  data: TreeNode[]
}

interface TreeNode {
  id: number
  name: string
  type: 'domain' | 'sub_domain' | 'service_module' | 'business_object'
  children?: TreeNode[]
  children_count?: number  // 子对象计数
  disabled?: boolean       // 是否禁用（无子对象时）
}
```

### 2.4 任务清单

| # | 任务 | 文件 | 产出 | 状态 | 元数据驱动 |
|---|------|------|------|------|-----------|
| 1 | CollapsiblePanel.vue | `src/components/common/CollapsiblePanel/` | 通用折叠容器 | 🚧 | N/A |
| 2 | ObjectTreePanel.vue | `src/components/business/ObjectTreePanel/` | 4层树形导航 | 🚧 | ✅ |
| 3 | 树节点展开/收起 | ObjectTreePanel | el-tree 渲染 | 🚧 | ✅ |
| 4 | 节点勾选过滤 | ObjectTreePanel | 勾选→过滤列表 | 🚧 | ✅ |
| 5 | 全选/清空按钮 | ObjectTreePanel | 树顶部操作 | 🚧 | - |
| 6 | 树节点搜索 | ObjectTreePanel | filterNode | 🚧 | ✅ |
| 7 | 节点计数 | ObjectTreePanel + API | 每个节点显示数量 | 🚧 | ✅ |

### 2.5 验收标准

#### 功能验收

- [ ] 4层树正确展示 domain→sub_domain→service_module→business_object
- [ ] 树节点展开/收起正常
- [ ] 勾选节点→右侧列表正确过滤
- [ ] 版本上下文变更→树自动重新加载
- [ ] 节点计数正确显示
- [ ] 搜索过滤正常工作

#### 元数据驱动验收

> 验证组件是否真正遵循元数据驱动原则

- [ ] **层级结构从 YAML 读取**: 树层级由 `hierarchies.levels` 定义，非硬编码
- [ ] **节点显示名从 YAML 读取**: 显示字段由 `display_name.expression` 决定
- [ ] **子对象类型从 YAML 读取**: children_field 由 `hierarchies[].levels[].children_field` 决定
- [ ] **无 if/elif 判断对象类型**: 组件代码中不存在 `if (type === 'domain')` 类判断

### 2.6 重构收益

| 对比项 | 旧 (TreeNavNode) | 新 (ObjectTreePanel) | 减少 |
|--------|-----------------|---------------------|------|
| 代码行数 | ~200 行 | ~150 行 | 25% |
| 复用性 | 低 | 高（通用树组件） | - |
| 可测试性 | 低 | 高 | - |

---

## 4. M18.5: 层级钻取 — useHierarchyList + 表格增强

> **预计工时**: 2 天
> **依赖**: M18.1 ✅ | M18.4 🔄
> **目标归属**: 目标二（丰富通用组件库）

### 4.1 目标

| 目标 | 具体内容 |
|------|---------|
| **架构迁移** | 层级路径列、子对象计数列、钻入操作 |
| **通用能力** | 沉淀 useHierarchyList、BreadcrumbNav 为通用组件 |

### 4.2 元数据驱动设计原则

**层级钻取组件必须遵循的元数据驱动约束**：

| 约束 | YAML 配置来源 | 说明 |
|------|-------------|------|
| 层级路径定义 | `hierarchies.levels[]` | 从 levels 动态构建路径 |
| 路径分隔符 | `hierarchies.path_separator` 或默认 '>' | 可配置的路径分隔符 |
| 钻取方向 | `hierarchies.levels[].drill_direction` | 钻入/钻出方向 |
| 对象类型映射 | `hierarchies.levels[].object_type` | 类型到显示名称的映射 |

```typescript
// ✅ 正确：从 hierarchies 构建路径
const buildPath = (currentType, currentId) => {
  const levels = hierarchyConfig.value.levels
  const path = []
  let level = levels.find(l => l.object_type === currentType)
  while (level) {
    path.unshift({ type: level.object_type, id: currentId })
    const parentLevel = levels[levels.indexOf(level) - 1]
    if (!parentLevel) break
    level = parentLevel
  }
  return path
}

// ❌ 错误：硬编码层级顺序
const LEVEL_ORDER = ['domain', 'sub_domain', 'service_module']
```

### 3.3 组件设计

#### 3.3.1 useHierarchyList.js — 层级钻取状态管理

> **通用性**: 可用于任何需要面包屑钻取的场景，不限于架构数据管理
>
> **元数据驱动**: 路径构建逻辑基于 YAML hierarchies 配置

**定位**: 管理面包屑导航和钻取状态。

```javascript
// 使用示例
const hierarchy = useHierarchyList({
  objectType: 'domain',
  versionId: computed(() => selectedVersionId.value)
})

// 钻取到子对象
hierarchy.drillIn(targetType, parentId)

// 点击面包屑回退
hierarchy.goTo(index)

// 当前钻取路径
console.log(hierarchy.path.value)
// [{ type: 'domain', id: 1, name: '财务领域' },
//  { type: 'sub_domain', id: 5, name: '总账' }]
```

**API**:

```typescript
interface UseHierarchyListOptions {
  objectType: string           // 当前对象类型
  versionId: Ref<number>       // 版本上下文
  onPathChange?: (path) => void // 路径变化回调
}

interface UseHierarchyListReturn {
  path: Ref<HierarchyNode[]>   // 钻取路径
  currentType: Ref<string>     // 当前对象类型
  parentId: Ref<number|null>    // 父对象 ID
  isDrilling: Ref<boolean>     // 是否正在钻取
  
  drillIn(targetType: string, parentId: number): void
  drillOut(index: number): void
  reset(): void
}

interface HierarchyNode {
  type: string                 // domain | sub_domain | service_module | business_object
  id: number
  name: string
}
```

#### 3.2.2 BreadcrumbNav.vue — 面包屑导航

**定位**: 显示当前钻取路径，支持点击回退。

```vue
<!-- 使用示例 -->
<BreadcrumbNav
  :path="hierarchy.path.value"
  :show-icon="true"
  @navigate="hierarchy.goTo"
/>
```

**Props**:

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| path | Array | [] | 钻取路径 |
| separator | String | '/' | 分隔符 |
| showIcon | Boolean | true | 显示对象类型图标 |
| maxItems | Number | 4 | 最大显示项数 |

**Events**:

| Event | Payload | 说明 |
|-------|---------|------|
| navigate | index | 点击回退到指定层级 |

#### 3.2.3 MetaTable 层级增强

**定位**: 在 MetaTable 中添加层级路径列和子对象计数列。

**新增列类型**:

```typescript
// 层级路径列
interface HierarchyPathColumn {
  type: 'hierarchy_path'
  levels: string[]              // 路径层级 ['domain', 'sub_domain']
  separator?: string            // 分隔符，默认 ' > '
}

// 子对象计数列
interface ChildCountColumn {
  type: 'child_count'
  childObjectType: string       // 子对象类型
  countField?: string           // 计数字段名
  drillable?: boolean          // 是否可点击钻入
}
```

**渲染示例**:

```
| 名称       | 层级路径                        | 子对象     | 操作 |
|------------|--------------------------------|-----------|------|
| 财务领域    | 财务管理 > 总账                 | 5 个子领域  | 编辑 |
| 总账       | 财务管理 > 总账                 | 12 个对象   | 编辑 |
```

### 4.4 钻取流程

```
用户点击 "5 个子领域" 计数列
    │
    ▼
┌─────────────────────────────────────┐
│ 1. 触发 drillIn                     │
│    hierarchy.drillIn('sub_domain', 1) │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 2. 更新钻取状态                     │
│    path: [{ type: 'domain', id: 1 }]│
│    currentType: 'sub_domain'         │
│    parentId: 1                      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 3. 刷新 MetaTable                   │
│    MetaTable 重新加载 sub_domain    │
│    自动带上 parent_id=1 过滤        │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 4. 更新面包屑                       │
│    面包屑显示: 财务管理 > 总账       │
└─────────────────────────────────────┘
```

### 4.5 API 对接

**获取子对象计数**:

```typescript
// GET /api/v2/bo/<object>/count
interface CountRequest {
  parent_id: number
  version_id?: number
}

interface CountResponse {
  success: boolean
  data: {
    count: number
  }
}
```

### 4.6 任务清单

| # | 任务 | 文件 | 产出 | 状态 | 元数据驱动 |
|---|------|------|------|------|-----------|
| 1 | useHierarchyList.js | `src/composables/useHierarchyList.js` | 钻取状态管理 | 🚧 | ✅ |
| 2 | BreadcrumbNav.vue | `src/components/common/BreadcrumbNav/` | 面包屑组件 | 🚧 | N/A |
| 3 | MetaTable 层级路径列 | `MetaTable.vue` | 路径列渲染 | 🚧 | ✅ |
| 4 | MetaTable 子对象计数列 | `MetaTable.vue` | 计数列+钻入 | 🚧 | ✅ |
| 5 | 钻取联动逻辑 | MetaTable + useHierarchyList | 钻取触发刷新 | 🚧 | ✅ |

### 4.7 验收标准

#### 功能验收

- [ ] domain 列表显示子对象计数列
- [ ] 点击计数列→钻入子对象列表（带 parent_id 过滤）
- [ ] 面包屑正确显示钻取路径
- [ ] 点击面包屑任意层级→正确回退
- [ ] 层级路径列正确显示完整路径

#### 元数据驱动验收

- [ ] **路径构建从 YAML 读取**: 路径由 `hierarchies.levels` 动态构建，非硬编码
- [ ] **分隔符从 YAML 读取**: 分隔符可由 `hierarchies.path_separator` 配置
- [ ] **钻取方向从 YAML 读取**: 方向由 `hierarchies.levels[].drill_direction` 决定

---

## 5. M18.6: MetaListPage 三栏布局整合

> **预计工时**: 3 天
> **依赖**: M18.2 ✅ | M18.3 🔄 | M18.4 🔄 | M18.5 🔄
> **目标归属**: 目标一（架构数据管理 UI 迁移）+ 目标二（通用组件库）

### 4.1 目标

| 目标 | 具体内容 |
|------|---------|
| **架构迁移** | 整合 M18.2-M18.5 的所有能力到 MetaListPage |
| **通用能力** | 沉淀 WorkspaceSidebar、WorkspaceMain 为通用布局组件 |

### 4.2 三栏布局架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [产品 ▾] [版本 ▾]                    [新建] [更多操作 ▾]                │
├───────────────┬─────────────────────────────────────────────────────────┤
│               │                                                         │
│  🔍 搜索...   │ 面包屑: 财务管理 > 总账                                │
│               ├─────────────────────────────────────────────────────────┤
│  ▼ 全部 (12)  │ ┌─────────────────────────────────────────────────────┐│
│    ▼ 财务     │ │ 名称       │ 层级路径           │ 子对象   │ 操作    ││
│      总账     │ │ 凭证       │ 财务管理 > 总账    │ 8 个对象  │ 编辑    ││
│      账簿     │ │ 账簿       │ 财务管理 > 总账    │ 3 个对象  │ 编辑    ││
│    ▼ 资金     │ │ 报表       │ 财务管理 > 总账    │ 5 个对象  │ 编辑    ││
│      收款     │ └─────────────────────────────────────────────────────┘│
│      付款     │                                                         │
│               │                        < 1 2 3 ... 10 >                │
│  [全选] [清空]│                                                         │
│               │                                                         │
└───────────────┴─────────────────────────────────────────────────────────┘
        ↑                     ↑                           ↑
   ObjectTreePanel      BreadcrumbNav               MetaTable
     (M18.4)              (M18.5)                    (M18.5)
```

### 4.3 元数据驱动设计原则

**三栏布局组件必须遵循的元数据驱动约束**：

| 约束 | YAML 配置来源 | 说明 |
|------|-------------|------|
| 上下文字段 | `context.scope_field` | 版本上下文过滤字段 |
| 上下文级联 | `context.cascade_to` | 上下文影响的子对象 |
| 侧边栏显示 | `ui_view_config.sidebar.visible` | 是否显示侧边栏 |
| 面包屑显示 | `ui_view_config.breadcrumb.visible` | 是否显示面包屑 |

### 4.4 组件设计

#### 4.2.1 WorkspaceSidebar.vue — 侧边栏容器

**定位**: 三栏布局的左侧容器，整合 ObjectTreePanel。

```vue
<!-- 使用示例 -->
<WorkspaceSidebar
  :width="sidebarWidth"
  :resizable="true"
  @resize="onSidebarResize"
>
  <template #header>
    <div class="sidebar-header">
      <el-input v-model="searchQuery" placeholder="搜索对象" />
      <el-button link @click="onSelectAll">全选</el-button>
      <el-button link @click="onClearAll">清空</el-button>
    </div>
  </template>
  
  <ObjectTreePanel
    :version-id="selectedVersionId"
    :selected-nodes="selectedNodes"
    @select="onNodeSelect"
    @check="onNodeCheck"
  />
</WorkspaceSidebar>
```

**Props**:

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| width | Number | 280 | 侧边栏宽度 |
| resizable | Boolean | true | 是否可拖拽 |
| minWidth | Number | 200 | 最小宽度 |
| maxWidth | Number | 400 | 最大宽度 |
| collapsible | Boolean | true | 是否可折叠 |

**Events**:

| Event | Payload | 说明 |
|-------|---------|------|
| resize | { width } | 宽度变化 |
| collapse | { collapsed } | 折叠状态变化 |

#### 4.2.2 WorkspaceMain.vue — 主内容区

**定位**: 三栏布局的右侧容器，包含面包屑和 MetaTable。

```vue
<!-- 使用示例 -->
<WorkspaceMain>
  <template #toolbar>
    <el-button type="primary" @click="onCreate">
      <el-icon><Plus /></el-icon> 新建
    </el-button>
  </template>
  
  <template #breadcrumb>
    <BreadcrumbNav :path="hierarchy.path.value" @navigate="onBreadcrumbClick" />
  </template>
  
  <MetaTable
    :object-type="currentObjectType"
    :initial-filters="currentFilters"
    @drill-in="onDrillIn"
  />
</WorkspaceMain>
```

#### 4.2.3 MetaListPage 插槽扩展

**新增插槽**:

| 插槽名 | 说明 | 使用场景 |
|--------|------|---------|
| #context-bar | 顶部上下文选择器 | VersionContextSelector |
| #sidebar | 左侧树形导航 | ObjectTreePanel |
| #toolbar-extra | 工具栏额外按钮 | 导入/导出按钮 |
| #breadcrumb | 面包屑导航 | BreadcrumbNav |

**使用示例**:

```vue
<MetaListPage
  object-type="domain"
  :enable-auto-crud="true"
  :enable-detail="true"
>
  <template #context-bar>
    <VersionContextSelector @change="onContextChange" />
  </template>
  
  <template #sidebar>
    <ObjectTreePanel
      v-if="showSidebar"
      :version-id="selectedVersionId"
      @select="onNodeSelect"
    />
  </template>
  
  <template #breadcrumb>
    <BreadcrumbNav :path="hierarchy.path.value" @navigate="hierarchy.goTo" />
  </template>
</MetaListPage>
```

### 4.3 三栏联动逻辑

#### 4.3.1 上下文 → 树+列表刷新

```javascript
watch(selectedVersionId, async (newVersionId) => {
  // 1. 重新加载树数据
  await treePanel.loadTreeData(newVersionId)
  
  // 2. 重新加载列表（带上 version_id 过滤）
  metaTable.loadData({ version_id: newVersionId })
})
```

#### 4.3.2 树节点 → 列表过滤

```javascript
function onNodeSelect(node) {
  // 1. 更新当前对象类型
  currentObjectType.value = node.type
  
  // 2. 更新过滤条件
  currentFilters.value = {
    ...currentFilters.value,
    parent_id: node.id
  }
  
  // 3. 刷新列表
  metaTable.loadData(currentFilters.value)
  
  // 4. 更新钻取路径
  hierarchy.drillIn(node.type, node.id)
}
```

#### 4.3.3 列表钻入 → 树同步

```javascript
function onDrillIn(childType, parentId) {
  // 1. 获取父节点信息
  const parentNode = await treePanel.getNodeById(parentId)
  
  // 2. 展开树到该节点
  treePanel.expandTo(parentNode)
  
  // 3. 触发节点选择
  treePanel.selectNode(parentId)
}
```

### 4.4 新建页面

| 页面 | 文件 | 说明 |
|------|------|------|
| DomainManagement.vue | `src/views/system/DomainManagement.vue` | 领域管理页面 |
| SubDomainManagement.vue | `src/views/system/SubDomainManagement.vue` | 子领域管理页面 |
| ServiceModuleManagement.vue | `src/views/system/ServiceModuleManagement.vue` | 服务模块管理页面 |
| BusinessObjectManagement.vue | `src/views/system/BusinessObjectManagement.vue` | 业务对象管理页面 |

**页面模板**:

```vue
<!-- DomainManagement.vue -->
<template>
  <div class="management-page">
    <MetaListPage
      object-type="domain"
      :enable-auto-crud="true"
      :enable-detail="true"
    >
      <template #context-bar>
        <VersionContextSelector @change="onVersionChange" />
      </template>
      
      <template #sidebar>
        <ObjectTreePanel
          :version-id="selectedVersionId"
          @select="onNodeSelect"
        />
      </template>
      
      <template #breadcrumb>
        <BreadcrumbNav :path="hierarchy.path.value" @navigate="hierarchy.goTo" />
      </template>
    </MetaListPage>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import MetaListPage from '@/components/bo/MetaListPage.vue'
import VersionContextSelector from '@/components/business/VersionContextSelector.vue'
import ObjectTreePanel from '@/components/business/ObjectTreePanel.vue'
import BreadcrumbNav from '@/components/common/BreadcrumbNav.vue'
import { useVersionContext } from '@/composables/useVersionContext'
import { useHierarchyList } from '@/composables/useHierarchyList'

const { selectedVersionId, onContextChange } = useVersionContext()

const currentObjectType = ref('domain')
const hierarchy = useHierarchyList({
  objectType: 'domain',
  versionId: selectedVersionId
})

function onNodeSelect(node) {
  currentObjectType.value = node.type
  hierarchy.drillIn(node.type, node.id)
}

function onVersionChange(context) {
  onContextChange(context)
  hierarchy.reset()
}
</script>
```

### 4.5 路由配置

```javascript
// router/index.js
{
  path: '/system',
  children: [
    {
      path: 'domains',
      name: 'DomainManagement',
      component: () => import('@/views/system/DomainManagement.vue'),
      meta: { title: '领域管理', icon: 'Folder' }
    },
    {
      path: 'sub-domains',
      name: 'SubDomainManagement',
      component: () => import('@/views/system/SubDomainManagement.vue'),
      meta: { title: '子领域管理', icon: 'FolderOpened' }
    },
    {
      path: 'service-modules',
      name: 'ServiceModuleManagement',
      component: () => import('@/views/system/ServiceModuleManagement.vue'),
      meta: { title: '服务模块管理', icon: 'Connection' }
    },
    {
      path: 'business-objects',
      name: 'BusinessObjectManagement',
      component: () => import('@/views/system/BusinessObjectManagement.vue'),
      meta: { title: '业务对象管理', icon: 'Box' }
    }
  ]
}
```

### 4.6 任务清单

| # | 任务 | 文件 | 产出 | 状态 | 目标归属 |
|---|------|------|------|------|---------|
| 1 | WorkspaceSidebar.vue | `src/components/business/WorkspaceSidebar/` | 侧边栏容器 | 🚧 | 目标二 |
| 2 | WorkspaceMain.vue | `src/components/business/WorkspaceMain/` | 主内容区 | 🚧 | 目标二 |
| 3 | MetaListPage 插槽扩展 | `MetaListPage.vue` | context-bar/sidebar 插槽 | 🚧 | 目标二 |
| 4 | 三栏布局 CSS | `workspace-layout.scss` | 三区域布局样式 | 🚧 | 目标二 |
| 5 | 三栏联动逻辑 | `useWorkspaceLayout.js` | 上下文→树→列表联动 | 🚧 | 目标二 |
| 6 | DomainManagement.vue | `src/views/system/` | 领域管理页面 | 🚧 | 目标一 |
| 7 | SubDomainManagement.vue | `src/views/system/` | 子领域管理页面 | 🚧 | 目标一 |
| 8 | ServiceModuleManagement.vue | `src/views/system/` | 服务模块管理页面 | 🚧 | 目标一 |
| 9 | BusinessObjectManagement.vue | `src/views/system/` | 业务对象管理页面 | 🚧 | 目标一 |
| 10 | 路由注册 | `router/index.js` | /system/* 路由 | 🚧 | 目标一 |
| 11 | 导航菜单更新 | `LayoutSidebar.vue` | 菜单入口 | 🚧 | 目标一 |

### 4.7 验收标准

#### 功能验收

- [ ] 三栏布局正确渲染（上下文栏+树+列表）
- [ ] 上下文变更→树+列表联动刷新
- [ ] 树节点点击→列表过滤
- [ ] 级联下拉在 MetaForm 中正常工作
- [ ] 层级钻取在 MetaTable 中正常工作
- [ ] 4个新页面完整可用
- [ ] 路由正确注册
- [ ] 导航菜单正确显示

#### 元数据驱动验收

- [ ] **上下文字段从 YAML 读取**: scope_field 由 `context.scope_field` 决定
- [ ] **上下文级联从 YAML 读取**: cascade_to 由 `context.cascade_to` 决定
- [ ] **侧边栏显示从 YAML 读取**: visible 由 `ui_view_config.sidebar.visible` 决定
- [ ] **面包屑显示从 YAML 读取**: visible 由 `ui_view_config.breadcrumb.visible` 决定

### 4.8 重构收益

| 对比项 | 旧 (UnifiedScopePanel + DynamicView) | 新 (WorkspaceSidebar + WorkspaceMain) | 减少 |
|--------|-------------------------------------|--------------------------------------|------|
| 代码行数 | ~1250 行 | ~300 行 | 76% |
| 组件数 | 10+ | 2 | 80% |
| 可复用性 | 低 | 高（通用布局组件） | - |

---

## 6. M18.7: 导入导出增强

> **预计工时**: 2 天
> **依赖**: M18.1 ✅ | M18.6 🔄
> **目标归属**: 目标二（丰富通用组件库）

### 5.1 目标

| 目标 | 具体内容 |
|------|---------|
| **架构迁移** | 替代旧的 ImportDialog + ExportDialog |
| **通用能力** | 沉淀 BatchImportDialog、BatchExportDialog 为通用组件 |

### 5.2 元数据驱动设计原则

**导入导出组件必须遵循的元数据驱动约束**：

| 约束 | YAML 配置来源 | 说明 |
|------|-------------|------|
| 导入对象类型 | `import_export.import_enabled` | 启用导入的对象 |
| 导出对象类型 | `import_export.export_enabled` | 启用导出的对象 |
| 级联导出 | `import_export.cascade_export` | 是否支持级联导出 |
| 层级路径列 | `import_export.include_hierarchy_path` | 是否包含层级路径列 |

### 5.3 BatchImportDialog.vue — 批量导入对话框

**定位**: 支持多对象导入、预览、冲突策略选择。

**功能流程**:

```
┌─────────────────────────────────────────────────────────────┐
│ 批量导入                                              [X]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  步骤:  ○ 文件上传  ● 预览确认  ○ 导入完成                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │     📁 点击或拖拽文件到此处上传                      │   │
│  │                                                     │   │
│  │     支持 .xlsx 格式                                  │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  版本: [v2.0 财务版本 ▾]                                    │
│                                                             │
│                              [取消]  [下一步]                │
└─────────────────────────────────────────────────────────────┘
```

**Props**:

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| visible | Boolean | false | 对话框显示状态 |
| versionId | Number | required | 版本上下文 ID |
| objectTypes | Array | ['domain', 'sub_domain', 'service_module', 'business_object'] | 支持的对象类型 |

**Events**:

| Event | Payload | 说明 |
|-------|---------|------|
| success | { imported, failed } | 导入完成 |
| error | { message } | 导入失败 |

**步骤说明**:

1. **文件上传**
   - 支持拖拽上传
   - 支持点击上传
   - 验证文件格式 (.xlsx)
   - 解析 Sheet 列表

2. **预览确认**
   - 显示每个 Sheet 的行数
   - 显示数据校验结果
   - 冲突策略选择（upsert / skip / overwrite）

3. **导入完成**
   - 显示导入结果统计
   - 显示错误明细

### 5.3 BatchExportDialog.vue — 批量导出对话框

**定位**: 支持单对象/级联导出、专业选项配置。

**功能流程**:

```
┌─────────────────────────────────────────────────────────────┐
│ 导出                                                [X]     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  导出模式:                                                   │
│  ○ 单对象导出    ● 级联导出（含子对象）                       │
│                                                             │
│  对象选择:                                                   │
│  ☑ 领域 (domains)                                           │
│  ☑ 子领域 (sub_domains)    ← 级联自领域                      │
│  ☑ 服务模块 (service_modules) ← 级联自子领域                  │
│  ☑ 业务对象 (business_objects) ← 级联自服务模块              │
│                                                             │
│  导出选项:                                                   │
│  ☑ 包含层级路径列                                            │
│  ☑ 包含层级编码/名称列                                       │
│  ☐ 保护工作表                                                │
│  ☐ 标记只读字段                                              │
│                                                             │
│  导出范围:                                                   │
│  版本: [v2.0 财务版本 ▾]                                     │
│                                                             │
│                              [取消]            [导出]          │
└─────────────────────────────────────────────────────────────┘
```

**Props**:

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| visible | Boolean | false | 对话框显示状态 |
| versionId | Number | required | 版本上下文 ID |
| currentObjectType | String | required | 当前对象类型 |
| cascadeLevels | Number | 0 | 级联层级深度 |

**导出选项接口**:

```typescript
interface ExportOptions {
  object_types: string[]           // 导出的对象类型
  cascade: boolean                  // 是否级联导出
  cascade_levels: number            // 级联深度
  include_hierarchy_path: boolean   // 包含层级路径
  include_hierarchy_ids: boolean    // 包含层级编码/名称
  protect_sheet: boolean           // 保护工作表
  mark_readonly: boolean            // 标记只读字段
  version_id: number               // 版本 ID
}
```

### 5.4 API 对接

**导入 API**:
```typescript
// POST /api/v2/bo/import/batch
interface BatchImportRequest {
  file: File
  version_id: number
  object_types: string[]
  conflict_strategy: 'upsert' | 'skip' | 'overwrite'
}

// GET /api/v2/bo/import/status/<task_id>
interface ImportStatusResponse {
  success: boolean
  data: {
    status: 'pending' | 'processing' | 'completed' | 'failed'
    progress: number               // 0-100
    current_object?: string        // 当前处理的对象类型
    result?: {
      total: number
      success: number
      failed: number
      errors: Array<{ row: number, message: string }>
    }
  }
}
```

**导出 API**:
```typescript
// POST /api/v2/bo/export/batch
interface BatchExportRequest {
  options: ExportOptions
}

// Response: 文件流 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
```

### 5.5 任务清单

| # | 任务 | 文件 | 产出 | 状态 |
|---|------|------|------|------|
| 1 | BatchImportDialog.vue | `src/components/business/BatchImportDialog/` | 批量导入对话框 | 🚧 |
| 2 | 导入文件上传 | BatchImportDialog | 拖拽+点击上传 | 🚧 |
| 3 | 导入预览 | BatchImportDialog | Sheet列表+校验 | 🚧 |
| 4 | 异步导入+进度条 | BatchImportDialog | 轮询+百分比 | 🚧 |
| 5 | 导入结果统计 | BatchImportDialog | 按类型分列统计 | 🚧 |
| 6 | BatchExportDialog.vue | `src/components/business/BatchExportDialog/` | 批量导出对话框 | 🚧 |
| 7 | 导出选项配置 | BatchExportDialog | 级联+专业选项 | 🚧 |
| 8 | MetaListPage 集成 | `MetaListPage.vue` | 导入/导出按钮 | 🚧 |

### 5.6 验收标准

#### 功能验收

- [ ] 多对象导入：5种对象类型同时导入
- [ ] 导入预览：Sheet 列表+行数+校验错误
- [ ] 异步导入：进度条+当前处理对象类型
- [ ] 级联导出：domain+其下所有子对象
- [ ] 导出选项：层级路径列、保护工作表、只读标记

#### 元数据驱动验收

- [ ] **导入启用从 YAML 读取**: import_enabled 由 `import_export.import_enabled` 决定
- [ ] **导出启用从 YAML 读取**: export_enabled 由 `import_export.export_enabled` 决定
- [ ] **级联导出从 YAML 读取**: cascade_export 由 `import_export.cascade_export` 决定

---

## 7. M18.8: 详情页增强

> **预计工时**: 2 天
> **依赖**: M18.1 ✅ | M18.6 🔄
> **目标归属**: 目标二（丰富通用组件库）

### 6.1 目标

| 目标 | 具体内容 |
|------|---------|
| **架构迁移** | 关联嵌入式展示、备注面板、变更历史 |
| **通用能力** | 复用现有组件（DetailPage、AssociationPanel、AuditLog、AnnotationList） |

### 6.2 设计原则

**核心原则**：
- **元数据驱动**：所有展示逻辑通过 YAML 配置声明
- **组件复用**：复用现有组件，避免重复建设
- **单一事实来源**：YAML 是唯一的配置源
- **智能推导**：根据 aspects 自动启用相关能力

**参考模型**：采用 **SAP CDS 风格的关联模型**

```
Association（关联）
├── 普通关联 (association) — 可独立存在
└── 组成关系 (composition) — 生命周期绑定
```

**SAP 引用**：
> *"In CDS models, compositions are a special kind of association that represent a parent-child hierarchical relationship, in which the child is a part of the parent and cannot exist without it."*

### 6.3 关联类型体系

#### 6.3.1 类型定义

| 类型 | 说明 | 示例 | 生命周期 |
|------|------|------|----------|
| `association` | 普通关联 | 用户-角色 | 可独立存在 |
| `composition` | 组成关系 | 领域-子领域、对象-备注 | 随主对象 |

#### 6.3.2 配置结构

```yaml
associations:
  # 普通关联 — 默认 Tab 展示
  - name: related_objects
    label: 关联对象
    target_entity: business_object
    type: association
    display:
      mode: tab

  # 组成关系 — 默认嵌入式展示
  - name: sub_domains
    label: 子领域
    target_entity: sub_domain
    type: composition
    display:
      mode: embedded
      collapsed: true

  # 备注 — 作为 composition 类型
  - name: annotations
    label: 备注
    target_entity: annotation
    type: composition
    config:
      categories_from_enum: annotation_category
      default_category: note
    display:
      mode: embedded
      collapsed: true
```

#### 6.3.3 配置字段说明

| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `name` | string | 关联名称（唯一标识） | - |
| `label` | string | 显示标签 | - |
| `target_entity` | string | 目标实体 | - |
| `type` | enum | `association` \| `composition` | `association` |
| `display.mode` | enum | `tab` \| `embedded` | `tab` |
| `display.collapsed` | boolean | 默认折叠状态 | `false` |
| `config` | object | 特定类型配置 | - |

### 6.4 详情页布局

#### 6.4.1 页面结构

```
┌─────────────────────────────────────────────────────────────┐
│ DetailPage.vue                                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 基本信息字段                                          │  │
│  │ - 字段1: 值1                                        │  │
│  │ - 字段2: 值2                                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ [折叠] 子领域 (3)           [展开]                  │  │
│  │ ┌─────────────────────────────────────────────────┐│  │
│  │ │ AssociationPanel (embedded, composition)          ││  │
│  │ └─────────────────────────────────────────────────┘│  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ [折叠] 备注 (5)               [展开]                │  │
│  │ ┌─────────────────────────────────────────────────┐│  │
│  │ │ AnnotationList (embedded, composition)            ││  │
│  │ └─────────────────────────────────────────────────┘│  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ [关联对象] [变更历史] [附件]                        │  │
│  │─────────────────────────────────────────────────────│  │
│  │                                                     │  │
│  │ AssociationPanel (tab mode)                          │  │
│  │                                                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 6.4.2 渲染逻辑

```
associations 配置
    │
    ├── mode: embedded
    │   └── 渲染在基本信息下方（按配置顺序）
    │
    └── mode: tab
        └── 合并到 "关联" Tab（统一展示）

aspects 配置
    │
    └── audit_aspect
        └── 添加 "变更历史" Tab
```

### 6.5 审计日志（Audit Log）

#### 6.5.1 设计决策

审计日志作为**系统能力**独立处理：

| 特点 | 说明 |
|------|------|
| 系统内置 | 不是用户配置的关联，是框架自动提供的 |
| 只读特性 | 用户不能编辑历史记录 |
| 固定展示 | 头部企业（SAP、Salesforce）都使用 Tab，无嵌入模式 |

#### 6.5.2 配置方式

```yaml
# 方式1: 通过 aspects 自动启用
aspects:
  - audit_aspect

# 方式2: 显式配置（可选）
ui_view_config:
  detail:
    showAuditLog: true
```

#### 6.5.3 智能推导规则

| 条件 | 结果 |
|------|------|
| 实体有 `audit_aspect` | 自动添加变更历史 Tab |
| 无 `audit_aspect` | 不显示变更历史 |

### 6.6 完整依赖分析

> Association 是基础模型，影响多个组件和模块。需要全面分析依赖关系。
>
> **参考文档**：
> - `phase-9-common-capability-model/spec.md` - Association 操作模式定义
> - `phase-12-value-help-architecture/spec.md` - ValueHelp 与 Association 协作关系
> - `object-audit-log-detail-page/spec.md` - 智能推导机制
> - `meta-model-deletion-association/spec.md` - 管理维度关联

#### 6.6.1 受影响的组件

| 组件 | 位置 | 影响说明 | 当前状态 |
|------|------|----------|----------|
| **ObjectPage.vue** | `src/components/common/ObjectPage/` | 详情页容器，支持 YAML 驱动 sections | ✅ 已有 |
| **DetailPage.vue** | `src/components/common/DetailPage/` | 侧滑详情面板 | ✅ 已有 |
| **MetaForm.vue** | `src/components/common/MetaForm/` | 表单，关联字段输入 | ✅ 已有 |
| **MetaTable.vue** | `src/components/common/MetaTable/` | 列表，关联列展示 | ✅ 已有 |
| **FilterBar.vue** | `src/components/common/FilterBar/` | 筛选器，关联过滤 | ✅ 已有 |
| **AssociationPanel.vue** | `src/components/common/AssociationPanel/` | 通用关联面板 | ✅ 已有 |
| **ValueHelpField.vue** | `src/components/common/ValueHelpField/` | 值帮助组件 | ✅ 已有 |
| **SearchHelpDialog.vue** | `src/components/common/SearchHelpDialog/` | 搜索帮助对话框 | ✅ 已有 |
| **AuditLog.vue** | `src/components/common/AuditLog/` | 审计日志组件 | ✅ 已有 |
| **AuditLogDetail.vue** | `src/components/common/AuditLog/` | 日志详情弹窗 | ✅ 已有 |

#### 6.6.2 受影响的 Composables

| Composable | 位置 | 影响说明 | 当前状态 |
|------------|------|----------|----------|
| **useValueHelp** | `src/composables/useValueHelp.js` | 值帮助逻辑，关联选择器 | ✅ 已有 |
| **useDetail** | `src/composables/useDetail.js` | 详情页状态管理 | ✅ 已有 |
| **useAssociation** | `src/composables/useAssociation.js` | 关联操作（CRUD） | ✅ 已有 |
| **useAuditLogs** | `src/composables/useAuditLogs.js` | 审计日志加载 | ✅ 已有 |

#### 6.6.3 受影响的 YAML 配置

| 配置项 | 位置 | 影响说明 | 当前状态 |
|--------|------|----------|----------|
| `relations` | 各实体 YAML | 业务对象之间的关系定义 | ✅ 已有 |
| `parent_object` | 各实体 YAML | 父对象声明 | ✅ 已有 |
| `associations` | 各实体 YAML | 关联配置（新方案） | 🆕 需新增 |
| `value_help` | 各实体 YAML | 值帮助配置 | ✅ 已有 |
| `aspects` | 各实体 YAML | 切面声明 | ✅ 已有 |
| `ui_view_config.detail` | 各实体 YAML | 详情页视图配置 | ✅ 已有 |
| `ui_view_config.list` | 各实体 YAML | 列表视图配置 | ✅ 已有 |
| `ui_view_config.filter` | 各实体 YAML | 筛选器配置（含跨表过滤） | ✅ 已有 |

#### 6.6.4 Association 操作类型体系（Phase 9）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  Association 操作类型（Phase 9 定义）                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Assignment Operations (分配操作)                                      │
│     ├── assign:      分配单个关联                                       │
│     ├── unassign:    取消分配单个关联                                   │
│     ├── batch_assign: 批量分配关联                                     │
│     └── batch_unassign: 批量取消分配                                    │
│                                                                         │
│  2. Query Operations (查询操作)                                        │
│     ├── list:        列出所有关联                                       │
│     ├── count:       统计关联数量                                       │
│     └── search:     搜索关联                                           │
│                                                                         │
│  3. Navigation Operations (导航操作)                                    │
│     ├── retrieve:    获取关联对象完整信息                                 │
│     └── navigate:   导航到关联对象详情页                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**API 设计**：

| 操作 | HTTP方法 | 端点 | 说明 |
|------|---------|------|------|
| 分配 | POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/assign` | 分配单个关联 |
| 取消分配 | POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/unassign` | 取消单个关联 |
| 批量分配 | POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_assign` | 批量分配 |
| 批量取消 | POST | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_unassign` | 批量取消 |
| 查询列表 | GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}` | 查询关联列表 |
| 统计数量 | GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/count` | 统计关联数量 |
| 获取详情 | GET | `/api/v2/bo/{entity}/{id}/$associations/{assoc}/{target_id}` | 获取关联对象详情 |

#### 6.6.5 ValueHelp 与 Association 的协作关系（Phase 12）

**核心洞察**：ValueHelp 和 Association 是协作关系而非互斥关系（SAP 模式）

| 维度 | Association | ValueHelp |
|------|-------------|-----------|
| **定义** | 关系语义（谁和谁关联、基数、生命周期） | 字段级选择行为（如何选择、搜索、展示、验证） |
| **SAP 对标** | `association [1..1] to I_Customer` | `@Consumption.valueHelpDefinition` |
| **数据层** | 定义 JOIN 路径、导航属性 | 定义 F4 帮助的数据源和搜索行为 |
| **UI 层** | 详情页的关联面板（AssociationPanel） | 表单字段的值选择器（ValueHelpField） |
| **操作** | assign / unassign / 导航到详情 | select / search / validate |

**协作规则**：
1. **字段级选择**（如选择客户、选择上级组织）→ `ValueHelpField`（source 从 Association 推导）
2. **关联对象管理**（如为角色分配用户、为用户组添加成员）→ `AssociationPanel` + Association API
3. **自动推导**：当字段有 Association 且 `cardinality = 1` 时，自动推导 `value_help.source.type = bo, target_bo = association.target_bo`

#### 6.6.6 智能推导机制（Object Audit Log Detail Page）

**核心原则**：YAML 是单一事实来源，UI 层应自动推导

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      智能推导机制                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  YAML 层（模型声明）:                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ aspects: [audit_aspect]  -->  单一事实：声明审计能力           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  后端层（信息传递）:                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ $metadata 端点  -->  返回 aspects: ["audit_aspect"]             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  前端层（智能推导）:                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ useDetail.loadUIConfig()  -->  检测 aspects 包含 audit_aspect   │   │
│  │   -->  自动追加 { id: 'history', label: '变更历史', type: 'history' } │   │
│  │   -->  无需 YAML 中手动配置                                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**推导规则**：

| 条件 | 结果 |
|------|------|
| `aspects` 包含 `audit_aspect` | 自动添加变更历史 Tab |
| `aspects` 包含 `hierarchy_aspect` | 自动启用层级导航 |
| 字段有 `association` 且 `cardinality = 1` | 自动推导 ValueHelp source |

#### 6.6.7 现有关联类型体系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        现有关联类型体系                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  relations:                                                             │
│  ├── parent_child — 父子关系（层级）                                    │
│  │   ├── version → domain                                              │
│  │   ├── domain → sub_domain                                           │
│  │   └── sub_domain → service_module                                   │
│  │                                                                   │
│  ├── composition — 组成关系                                            │
│  │   └── domain → sub_domain（composition: true）                    │
│  │                                                                   │
│  └── reference — 引用关系                                              │
│      ├── business_object → relationship（作为源）                      │
│      └── business_object → relationship（作为目标）                    │
│                                                                         │
│  parent_object:                                                         │
│  ├── version.parent_object = product                                   │
│  ├── domain.parent_object = version                                   │
│  ├── sub_domain.parent_object = domain                                 │
│  ├── service_module.parent_object = sub_domain                          │
│  └── business_object.parent_object = service_module                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 6.6.8 Association 与其他模块的关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Association 依赖关系图                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     YAML 配置层                                   │   │
│  │  associations | relations | parent_object | aspects | value_help │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Composable 层                                 │   │
│  │  useValueHelp | useDetail | useAssociation | useAuditLogs        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                    │                    │                │               │
│         ┌─────────┴────────┐  ┌──────┴──────┐  ┌────┴────┐         │
│         ▼                  ▼  ▼             ▼  ▼         ▼         │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐  ┌────────┐  ┌──────┐│
│  │ MetaForm   │  │ MetaTable  │  │FilterBar │  │DetailPage│ │ObjectPage││
│  │ (值帮助)  │  │ (关联列)  │  │(跨表过滤)│  │(关联展示)│  │(关联)  ││
│  └────────────┘  └────────────┘  └──────────┘  └────────┘  └──────┘│
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     BOF 服务层                                    │   │
│  │  ValueHelpService | RelationService | AssociationService | AuditService│   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 6.6.9 ObjectPage 与 DetailPage 的关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ObjectPage vs DetailPage                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ObjectPage.vue (Full Page)          DetailPage.vue (Slide Panel)      │
│  ┌────────────────────────────┐     ┌────────────────────────────┐     │
│  │ Header (Sticky)            │     │ Header                     │     │
│  │ - Back + Breadcrumb        │     │ - Title + Actions          │     │
│  │ - Status + Actions         │     │                            │     │
│  ├────────────────────────────┤     ├────────────────────────────┤     │
│  │ Content (Scrollable)       │     │ Content                    │     │
│  │ - Sections (Tab/Toggle)   │     │ - Basic Info              │     │
│  │ - FieldGroups             │     │ - Associations (Embedded)  │     │
│  │ - Custom Slots            │     │ - Tabs (Association/History)│     │
│  └────────────────────────────┘     └────────────────────────────┘     │
│                                                                         │
│  使用场景:                        使用场景:                              │
│  - 独立详情页                    - 列表页内快速查看                       │
│  - 需要完整导航                  - 弹窗式编辑                            │
│                                                                         │
│  共同点: 两者都使用相同的 Association 渲染逻辑                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.7 组件改造

#### 6.7.1 DetailPage.vue 增强

**新增 Props**：

```typescript
interface DetailPageProps {
  // 现有...
  embeddedAssociations?: AssociationConfig[]
  tabAssociations?: AssociationConfig[]
}
```

**渲染逻辑**：

```vue
<template>
  <div class="detail-page">
    <!-- 基本信息 -->
    <BasicInfo :fields="fields" />

    <!-- 嵌入式关联（composition 默认嵌入） -->
    <template v-for="assoc in embeddedAssociations" :key="assoc.name">
      <AssociationSection
        :config="assoc"
        :collapsed="assoc.display.collapsed"
      >
        <AssociationPanel :config="assoc" mode="embedded" />
      </AssociationSection>
    </template>

    <!-- Tab 区域 -->
    <AppTabs v-model="activeTab" :tabs="tabs">
      <template v-for="assoc in tabAssociations" :key="assoc.name">
        <TabPane :label="assoc.label" :name="assoc.name">
          <AssociationPanel :config="assoc" mode="tab" />
        </TabPane>
      </template>
    </AppTabs>
  </div>
</template>
```

#### 6.7.2 智能分类逻辑

```typescript
function classifyAssociations(associations: AssociationConfig[]) {
  const embedded: AssociationConfig[] = []
  const tab: AssociationConfig[] = []

  for (const assoc of associations) {
    // composition 默认嵌入
    if (assoc.type === 'composition' && assoc.display.mode !== 'tab') {
      embedded.push(assoc)
    } else {
      tab.push(assoc)
    }
  }

  return { embedded, tab }
}
```

### 6.8 配置示例

#### 6.8.1 完整配置示例

```yaml
# domain.yaml
name: domain
label: 领域
aspects:
  - audit_aspect

fields:
  - name: name
    label: 名称
    type: string
    required: true

associations:
  - name: sub_domains
    label: 子领域
    target_entity: sub_domain
    type: composition
    display:
      mode: embedded
      collapsed: true

  - name: annotations
    label: 备注
    target_entity: annotation
    type: composition
    config:
      categories_from_enum: annotation_category
    display:
      mode: embedded
      collapsed: true

  - name: related_domains
    label: 关联领域
    target_entity: domain
    type: association
    display:
      mode: tab

ui_view_config:
  detail:
    tabs:
      - id: basic
        label: 基本信息
        type: fields
      - id: associations
        label: 关联对象
        type: associations
      - id: history
        label: 变更历史
        type: history
        # audit_aspect 启用时自动添加
```

#### 6.8.2 最小配置示例

```yaml
# 最小配置：只需要声明 associations
name: domain
label: 领域

associations:
  - name: sub_domains
    target_entity: sub_domain
    type: composition
    # display.mode 默认 tab，composition 可省略

  - name: annotations
    target_entity: annotation
    type: composition
```

### 6.9 组件复用清单

| 组件 | 位置 | 状态 | 说明 |
|------|------|------|------|
| DetailPage.vue | src/components/common/ | ✅ 已有 | 详情页容器 |
| useDetail.js | src/composables/ | ✅ 已有 | 详情页状态管理 |
| AssociationPanel.vue | src/components/common/ | ✅ 已有 | 通用关联面板 |
| AuditLog.vue | src/components/common/ | ✅ 已有 | 审计日志组件 |
| AnnotationList.vue | src/views/ArchDataManageApp/ | ✅ 已有 | 备注列表组件 |

### 6.10 任务清单

| # | 任务 | 文件 | 产出 | 状态 | 说明 |
|---|------|------|------|------|------|
| 1 | DetailPage 嵌入式关联增强 | `DetailPage.vue` | embeddedAssociations 渲染 | 🚧 | 复用现有组件 |
| 2 | AssociationPanel 嵌入模式 | `AssociationPanel.vue` | embedded mode 支持 | 🚧 | 复用现有组件 |
| 3 | AnnotationList 作为 Association | YAML 配置 | type: composition | 🚧 | 注解也是一种关联 |
| 4 | 智能分类逻辑 | `useDetail.js` | embedded/tab 自动分类 | 🚧 | composition 默认 embedded |
| 5 | AuditLog 集成 | `DetailPage.vue` | 变更历史 Tab | ✅ | audit_aspect 自动启用 |
| 6 | **层级路径导航（TODO）** | - | 后续增强 | 🟡 | 后续支持 parent object 链接 |

### 6.10 验收标准

#### 功能验收

| 编号 | 标准 | 验证方式 |
|------|------|----------|
| 1 | Association 可配置 `mode: tab \| embedded` | YAML 配置 |
| 2 | `type: composition` 默认 `mode: embedded` | 渲染验证 |
| 3 | Embedded 关联渲染在基本信息下方 | UI 验证 |
| 4 | Tab 关联合并到 "关联" Tab | UI 验证 |
| 5 | `audit_aspect` 自动启用变更历史 Tab | YAML 配置 |
| 6 | Annotation 作为 `type: composition` | YAML 配置 |
| 7 | `collapsed` 配置生效 | UI 验证 |

#### 元数据驱动验收

| 编号 | 标准 |
|------|------|
| 1 | 所有展示逻辑通过 YAML 配置声明 |
| 2 | 无硬编码关联类型 |
| 3 | 复用现有组件，无重复建设 |

#### 非功能验收

| 编号 | 标准 |
|------|------|
| 1 | 复用现有组件（DetailPage、AssociationPanel、AuditLog、AnnotationList） |
| 2 | 无需修改组件代码即可配置新关联 |

### 6.12 后续增强（TODO）

| 编号 | 功能 | 说明 |
|------|------|------|
| 1 | 层级路径导航 | 点击路径节点跳转到父对象详情 |

---

## 8. M18.9: 旧 App 废弃 + manage_api.py 瘦身

> **预计工时**: 2 天
> **依赖**: M18.6 ✅ | M18.7 ✅ | M18.8 ✅
> **目标归属**: 目标一（架构数据管理 UI 迁移）

### 7.1 目标

| 目标 | 具体内容 |
|------|---------|
| **架构迁移** | 旧 App 废弃、manage_api.py 标记废弃、useChangeNotification 通用化 |

### 7.2 废弃计划

#### 7.2.1 旧 App 路由迁移

| 旧路由 | 新路由 | 过渡期 |
|--------|--------|--------|
| `/arch-data` | `/system/domains` | 2 周 |
| `/product-version` | `/system/products` | 2 周 |

```javascript
// router/index.js
{
  path: '/legacy',
  component: Layout,
  children: [
    {
      path: 'arch-data',
      component: () => import('@/views/legacy/ArchDataManageApp/index.vue'),
      meta: { deprecated: true, removeAt: '2026-07-01' }
    }
  ]
}
```

#### 7.2.2 导航菜单更新

```javascript
// 隐藏旧菜单入口
const menuItems = [
  // ...
  {
    path: '/legacy/arch-data',
    title: '架构数据管理（旧）',
    visible: false,  // 隐藏
    meta: { deprecated: true }
  }
]
```

#### 7.2.3 manage_api.py 废弃标记

```python
# manage_api.py
@api.route('/<object_type>', methods=['GET', 'POST'])
@deprecated("""
    [DEPRECATED] /api/v1/manage/<object> 将在 v3.0 移除。
    请使用 /api/v2/bo/<object> 替代。
    废弃时间: 2026-05-01
    移除时间: 2026-07-01
""")
def manage_crud(object_type):
    # ...
```

### 7.3 前端调用清理

**全局搜索**: 检查前端是否有直接调用 `/api/v1/manage/*` 的代码。

```bash
# 搜索命令
grep -rn "/api/v1/manage" src/ --include="*.vue" --include="*.js"
```

**常见调用场景**:

| 场景 | 替换方案 |
|------|---------|
| archDataStore.fetchList | boService.query |
| archDataStore.fetchById | boService.read |
| archDataStore.create | boService.create |
| archDataStore.update | boService.update |
| archDataStore.delete | boService.delete |

### 7.4 旧文件清理清单

| 目录 | 文件数 | 说明 |
|------|--------|------|
| `src/views/arch-data-manage/` | 25+ | 旧架构数据管理页面 |
| `src/views/product-version/` | 8+ | 旧产品版本页面 |
| `src/stores/archDataStore.js` | 1 | 旧状态管理 |
| `src/api/manageApi.js` | 1 | 旧 API 调用 |

### 7.5 useChangeNotification 通用化

**现状**: `useChangeNotification` 在 ArchDataManageApp 内部使用。

**目标**: 提升到 `src/composables/` 供所有页面使用。

```javascript
// src/composables/useChangeNotification.js
export function useChangeNotification(options = {}) {
  const {
    objectTypes = [],
    onCreated,
    onUpdated,
    onDeleted
  } = options
  
  // WebSocket 连接管理
  // 订阅/取消订阅
  // 自动刷新逻辑
  
  return {
    subscribe,
    unsubscribe,
    isConnected
  }
}
```

### 7.6 任务清单

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 1 | 旧 App 路由添加 /legacy 前缀 | 保留 2 周过渡期 | 🚧 |
| 2 | 旧 App 导航入口隐藏 | 从菜单中移除 | 🚧 |
| 3 | manage_api.py 添加 Deprecation Warning | 通用路由标记废弃 | 🚧 |
| 4 | 确认无遗留 /api/v1/manage/* 调用 | 前端全局搜索 | 🚧 |
| 5 | 过渡期后删除旧文件 | 54+ 文件 | 🚧 |
| 6 | useChangeNotification 通用化 | 提升到 src/composables/ | 🚧 |

### 7.7 验收标准

- [ ] 新架构功能完整，无功能回退
- [ ] 旧 App /legacy 路由在过渡期内可用
- [ ] 无前端直接调用 /api/v1/manage/*
- [ ] manage_api.py 通用路由标记 Deprecated
- [ ] 过渡期结束后旧文件全部删除

---

## 8. 技术风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| ArchDataManageApp 的 RelationScopeTree / AnnotationList 等组件有隐藏依赖未发现 | 功能回退 | 中 | 在过渡期保留旧 App 的 `/legacy` 路由，充分测试 |
| 旧 App 的 useApi.js 有复杂查询逻辑（多表 join、聚合）在 v2 框架下无法直接实现 | CRUD 不完整 | 中 | 逐一验证每个 API 调用的查询逻辑，必要时扩展 BO Framework |
| ProductVersionApp 的树形+表格混合交互在新架构下用户体验下降 | UX 退化 | 低 | 使用 useTreeNavigation composable 复现树形交互 |
| manage_api.py 通用路由有其他未迁移对象依赖 | 不可删除 | 高 | 不删除通用路由，仅标记废弃；等待所有对象迁移完毕再清理 |
| 过渡期间新旧两套路由并存导致数据不一致 | 数据冲突 | 低 | 新旧路由读写同一数据库，不存在一致性问题 |

---

## 9. 实施计划

### 9.1 时间线

| 周 | 里程碑 | 任务 |
|----|--------|------|
| Week 1 | M18.4 树形导航 | CollapsiblePanel + ObjectTreePanel |
| Week 2 | M18.5 层级钻取 | useHierarchyList + MetaTable 增强 |
| Week 3 | M18.6 三栏布局 (1/2) | WorkspaceSidebar + WorkspaceMain |
| Week 4 | M18.6 三栏布局 (2/2) | 4 个新页面 + 路由 |
| Week 5 | M18.7 导入导出 | BatchImportDialog + BatchExportDialog |
| Week 6 | M18.8 详情页 | DetailPanel + RelationPanel + AnnotationPanel |
| Week 7 | M18.9 废弃清理 | 路由迁移 + 文件清理 |

### 9.2 测试策略

| 阶段 | 测试内容 |
|------|---------|
| 单元测试 | Composable、组件独立功能 |
| 集成测试 | 三栏联动、API 对接 |
| E2E 测试 | 完整用户流程（创建→编辑→导入→导出） |
| 回归测试 | 与旧 App 功能对比 |

---

## 10. 变更记录

| 日期 | 变更内容 | 操作人 |
|------|---------|--------|
| 2026-05-14 | 创建 Phase 18 M18.4-M18.9 细化规格 | AI |
| 2026-05-14 | M18.8 详情页增强细化：采用 SAP CDS 风格关联模型，统一 association/composition 类型，支持嵌入式展示；增加 ObjectPage 影响分析和 ValueHelp 与 Association 关系分析；引用 Phase 9/12/Object Audit Log spec，完善 Association 操作类型体系和智能推导机制 | AI |
