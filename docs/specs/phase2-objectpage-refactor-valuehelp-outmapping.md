## 目录

1. [1. 概述](#1-概述)
2. [2. 头部产品参考](#2-头部产品参考)
3. [3. 现状分析](#3-现状分析)
4. [4. 数据模型](#4-数据模型)
5. [5. 组件架构](#5-组件架构)
6. [6. API 设计](#6-api-设计)
7. [7. 前端实现](#7-前端实现)
8. [8. 后端实现](#8-后端实现)
9. [9. 实施计划](#9-实施计划)
10. [10. 测试用例](#10-测试用例)
11. [附录 A：文件变更清单](#附录-a：文件变更清单)
12. [附录 B：YAML 配置示例](#附录-b：yaml-配置示例)
13. [附录 C：风险与缓解](#附录-c：风险与缓解)

---
# Spec: Phase 2 — ObjectPage 组件重构 + ValueHelp In/Out Mapping + Association 通用能力

> **版本**: v2.0
> **日期**: 2026-05-26
> **状态**: 设计中
> **前置依赖**: Phase 1（ObjectPage YAML 驱动渲染 + ValueHelp 三层架构）已就绪
> **影响范围**: 前端组件 7 个文件 + 后端模型 2 个文件 + YAML Schema

---

## 1. 概述

### 1.1 背景

当前 `ObjectPage.vue` 已承担过多职责，代码量约 2430 行（含模板 584 行 + 脚本 1287 行 + 样式 560 行），包含以下功能模块：

| 职责 | 代码行范围 | 复杂度 |
|------|-----------|--------|
| Header 渲染（标题/状态/StateTransitionButtons/操作按钮） | L9-L77 | 中 |
| 5 种 Section 类型渲染（standard/custom/association/annotation/history） | L94-L506 | 高 |
| 字段渲染 + ValueHelpField 自动切换 | L136-L186, L436-L501 | 高 |
| autoLoadMeta 机制（从后端加载字段元数据） | L813-L881 | 中 |
| 语义驱动 Actions（30+ actionKey→semantic 映射） | L899-L1023 | 中 |
| Annotation CRUD（表单状态、API 调用、分类加载） | L1131-L1282 | 高 |
| AuditLog 集成 | L1029-L1071 | 低 |
| 合并关系数据加载（两个并行请求 + 去重） | L1074-L1099 | 中 |
| Association Section 嵌入 MetaListPage | L189-L243, L329-L405 | 高 |
| CascadeField 支持 | L1734-L1741 | 低 |

**核心问题**：

1. **单文件过大**：2430 行超出 Vue 组件可维护性阈值（建议 < 500 行）
2. **职责耦合**：Annotation CRUD、AuditLog、Association 逻辑全部内联，修改一处需理解全部
3. **模板重复**：standard section 的字段渲染逻辑在 `main_content` 虚拟 Tab 和普通 Tab 中各出现一次（L136-L186 与 L459-L497 几乎完全相同）
4. **测试困难**：无法单独测试 Annotation CRUD 或 AuditLog 逻辑
5. **annotation section 是特例处理**：annotation 本质上是多态关联 + 生命周期绑定 + 自定义表单的组合，不应作为独立 section 类型

同时，ValueHelp 的 In/Out Mapping 能力缺失：

- **当前状态**：`ValueHelpParameterBinding`（L483-L487）仅支持 **In Mapping**（`local_field → target_field`），即从表单字段向 ValueHelp 搜索请求传参
- **缺失能力**：**Out Mapping** — 用户选择 ValueHelp 项后，自动将结果中的其他字段值回填到表单
- **SAP 对标**：SAP 的 `@ObjectModel.resultElement` 和 `@Consumption.valueHelpDefinition` 原生支持 Out Mapping

### 1.2 目标

**ObjectPage 重构**：

1. 将 ObjectPage.vue 拆分为 7 个职责单一的子组件
2. **移除 annotation section 特例**，统一到 association section
3. 消除模板重复（字段渲染逻辑统一到 ObjectPageField）
4. 每个子组件可独立测试
5. 保持 100% 向后兼容（props/emits/slots 不变）

**ValueHelp Out Mapping**：

1. 后端新增 `ValueHelpOutMapping` 数据类
2. YAML Schema 支持 `out_mappings` 配置
3. 前端 ValueHelpField 选择后自动回填 out_mapping 字段
4. 与现有 `parameter_bindings`（In Mapping）对称设计

**Association 通用能力**：

1. 多态关联过滤：任何 `target_type: polymorphic` 的关联都支持 `filters.target_type` + `filters.target_id`
2. 生命周期绑定：任何 `cascade_delete: true` 的关联都支持 `lifecycle: bound` 语义
3. 自定义表单：任何关联都可以配置 `form.mode: custom` + `form.component`

### 1.3 涉众目标

| 涉众 | 目标 |
|------|------|
| 前端开发者 | ObjectPage 子组件可独立开发和测试，降低认知负载 |
| 架构师 | 组件职责清晰，符合单一职责原则；annotation 不再是特例 |
| 产品经理 | ValueHelp Out Mapping 提升数据录入效率，减少手动填写 |
| 终端用户 | 选择一个值后自动填充关联字段，减少重复输入 |

---

## 2. 头部产品参考

### 2.1 SAP S/4HANA — ValueHelp Out Mapping

SAP CDS View 中通过 `@Consumption.valueHelpDefinition` 和 `@ObjectModel.resultElement` 实现 Out Mapping：

```abap
@Consumption.valueHelpDefinition: {
  entity: { name: 'I_Domain', element: 'DomainID' }
}
DomainID;

@ObjectModel.resultElement: 'DomainName'
DomainName;  // 自动从 ValueHelp 结果回填
```

**SAP 模式**：选择 DomainID 后，DomainName 自动从 ValueHelp 结果中填充。

### 2.2 Salesforce — Lookup Field Auto-Population

Salesforce Lookup 字段选择后，关联对象的 Name 字段自动显示在 `Name` 列：

- 选择 `Account` Lookup → 自动显示 `Account.Name`
- 通过 `relatedTo` + `displayField` 配置

### 2.3 ServiceNow — Reference Field Auto-Population

ServiceNow Reference 字段选择后，可通过 `ref_auto_completer` 配置自动填充关联字段：

- `ref_ac_columns_search`：搜索哪些列
- `ref_ac_columns`：选择后显示哪些列
- 支持通过 `glideform` API 的 `onChange` 脚本实现 Out Mapping

### 2.4 组件拆分参考

| 产品 | 详情页架构 | 特点 |
|------|-----------|------|
| **SAP Fiori** | ObjectPage → HeaderFacet + Section + FieldGroup | 每种 Section 类型独立组件 |
| **Salesforce Lightning** | RecordPage → Header + Detail + RelatedList | RelatedList 独立组件 |
| **ServiceNow** | FormPage → Header + Section + RelatedList | 每种 Section 类型独立组件 |

**共同模式**：Header / Section / Field 三层拆分，每种 Section 类型独立组件。

### 2.5 多态关联参考

| 产品 | 多态关联实现 | 特点 |
|------|------------|------|
| **SAP** | Generic Reference + `@ObjectModel.type.key` | 通用引用字段 + 类型键 |
| **Salesforce** | Polymorphic Lookup | `WhatId` / `WhoId` 可指向任意对象 |
| **ServiceNow** | Reference + `reference_qualifier` | 引用字段 + 动态过滤条件 |

---

## 3. 现状分析

### 3.1 ObjectPage.vue 当前结构

```
ObjectPage.vue (2430 行)
├── <template> (L1-L584)
│   ├── header 区域 (L9-L77)
│   │   ├── 返回按钮 + 面包屑
│   │   ├── 状态徽章
│   │   ├── StateTransitionButtons
│   │   ├── YAML-Driven 操作按钮
│   │   └── actions slot
│   ├── content 区域 (L82-L530)
│   │   ├── headerContent slot
│   │   ├── YAML-Driven 模式 (L94-L506)
│   │   │   ├── Tab 导航栏
│   │   │   ├── main_content 虚拟 Tab
│   │   │   │   ├── standard section (字段组渲染) ← 重复 A
│   │   │   │   ├── association section
│   │   │   │   ├── annotation section ← 特例处理
│   │   │   │   └── history section
│   │   │   ├── custom section
│   │   │   ├── history section (独立 Tab)
│   │   │   ├── association section (独立 Tab)
│   │   │   ├── annotation section (独立 Tab) ← 特例处理
│   │   │   └── standard section (独立 Tab) ← 重复 B
│   │   └── Legacy Slot 模式 (L510-L530)
│   ├── AuditLogDetail Drawer
│   ├── AssignmentDialog
│   └── Annotation Form Dialog ← 特例处理
├── <script setup> (L587-L1871)
│   ├── Props 定义 (L605-L763)
│   ├── autoLoadMeta 机制 (L769-L881)
│   ├── Actions 语义映射 (L890-L1023)
│   ├── AuditLog 集成 (L1029-L1071)
│   ├── 合并关系加载 (L1074-L1099)
│   ├── Annotation CRUD (L1131-L1282) ← 特例处理
│   ├── Association 工具函数 (L1284-L1391)
│   ├── Tab 管理 (L1394-L1613)
│   ├── Visibility Engine (L1615-L1627)
│   ├── FieldGroup 折叠 (L1629-L1657)
│   ├── 字段元数据工具 (L1670-L1847)
│   └── 动态组件解析 (L1849-L1861)
└── <style scoped> (L1873-L2433)
```

### 3.2 annotation section 特例分析

**当前实现**：annotation 作为独立的 section 类型，有专用的处理逻辑：

```javascript
// 专用 fetcher
function getAnnotationFetcher(section) {
  return async (queryParams) => {
    const url = `${API_BASE}/annotations?target_type=${props.objectType}&target_id=${props.objectId}&...`
    // ...
  }
}

// 专用 action handler
async function handleAnnotationAction(event, section) { ... }

// 专用表单状态
const annotationFormVisible = ref(false)
const annotationFormData = ref({ category: '', content: '' })
const annotationEditingId = ref(null)
```

**本质分析**：annotation 不是特例，而是三种通用能力的组合：

| 能力 | annotation 的应用 | 通用性 |
|------|------------------|--------|
| **多态关联过滤** | `target_type` + `target_id` 过滤 | 任何 `target_type: polymorphic` 的关联都需要 |
| **生命周期绑定** | `cascade_delete: true` | 任何 composition/parent_child 关系都有 |
| **自定义表单** | category select + content textarea | MetaListPage 通过 `emit('create')` 支持任意自定义表单 |

**annotation.yaml 的关联定义**：

```yaml
associations:
  - name: target
    target_type: polymorphic           # 多态关联
    type: many_to_one
    polymorphic_type_field: target_type
    polymorphic_id_field: target_id
    cascade_delete: true               # 生命周期绑定
```

**结论**：annotation section 可以完全统一到 association section，通过配置驱动。

### 3.3 MetaListPage 的扩展点

MetaListPage 已支持三种创建/编辑模式：

```javascript
// MetaListPage.vue L1061-L1076
if (action.key === 'create') {
  if (hasDetailPageRoute()) {
    navigateToDetailPageForCreate()           // 路径 1：导航到详情页
  } else if (enableDetailPage.value && !hasCustomDialog('create')) {
    openCreateDrawer()                        // 路径 2：内置 Drawer
  } else {
    emit('create', payload)                   // 路径 3：外部处理 ← 扩展点！
  }
}
```

**annotation section 正是利用了这个扩展点**：

```vue
<MetaListPage
  :enable-auto-crud="false"              ← 禁用内置 CRUD
  @action="handleAnnotationAction"       ← 接管 action 处理
/>
```

### 3.4 ValueHelp 当前数据模型

```python
# meta/core/models.py

@dataclass
class ValueHelpParameterBinding:          # L483-L487
    local_field: str = ""                 # 表单字段名
    target_field: str = ""                # ValueHelp 请求参数名
    required: bool = False
    constant: str = ""

@dataclass
class ValueHelpBehavior:                  # L509-L518
    binding_strength: str = "strict"
    validation: bool = True
    search_fields: List[str] = field(default_factory=list)
    min_search_length: int = 0
    debounce_ms: int = 300
    multiple: bool = False
    parameter_bindings: List[ValueHelpParameterBinding] = field(default_factory=list)
    enabled_condition: str = ""
    # ❌ 无 out_mappings 字段
```

### 3.5 ValueHelp 前端当前流程

```
用户点击 ValueHelpField
  → useValueHelp.loadOptions(search, filters)
    → boService.searchValueHelp(sourceType, sourceId, params)
      → GET /api/v2/value-help/{sourceType}/{sourceId}
        → Provider.search() → 返回 [{value, display, code, extra}]
  → 用户选择一项
    → ValueHelpField.emit('update:modelValue', val)
    → ValueHelpField.emit('update:displayValue', display)
    → ❌ 仅更新 value 和 displayValue，不回填其他字段
```

### 3.6 BoValueHelpProvider 返回结构

```python
# meta/core/value_help_providers.py — BoValueHelpProvider.search()

def search(self, query, ...):
    # 返回格式
    {
        "data": [
            {
                "value": 1,           # source.value_field (默认 id)
                "display": "产品A",    # source.display_field (默认 name)
                "code": "PRD001",     # source.code_field (默认 code)
                "extra": {            # 其他字段
                    "status": "active",
                    "domain_name": "技术域",
                    ...
                }
            }
        ],
        "total": 100
    }
```

**关键发现**：`extra` 字段已包含 ValueHelp 结果的所有额外字段，但前端未利用。

---

## 4. 数据模型

### 4.1 新增 ValueHelpOutMapping

```python
# meta/core/models.py — 新增

@dataclass
class ValueHelpOutMapping:
    """值帮助输出映射（借鉴 SAP @ObjectModel.resultElement）
    
    用户选择 ValueHelp 项后，将结果中的指定字段值回填到表单字段。
    与 ValueHelpParameterBinding（In Mapping）对称设计。
    """
    value_help_field: str = ""    # ValueHelp 结果中的字段名
    local_field: str = ""         # 表单/实体中的字段名
```

### 4.2 修改 ValueHelpBehavior

```python
# meta/core/models.py — 修改

@dataclass
class ValueHelpBehavior:
    binding_strength: str = "strict"
    validation: bool = True
    search_fields: List[str] = field(default_factory=list)
    min_search_length: int = 0
    debounce_ms: int = 300
    multiple: bool = False
    parameter_bindings: List[ValueHelpParameterBinding] = field(default_factory=list)
    out_mappings: List[ValueHelpOutMapping] = field(default_factory=list)  # 新增
    enabled_condition: str = ""
```

### 4.3 新增 AssociationSectionConfig

```python
# meta/core/models.py — 新增

@dataclass
class AssociationSectionConfig:
    """关联 Section 配置（统一 annotation 和其他关联）"""
    
    # 基础配置
    association: str = ""                    # 关联名称（如 'target' / 'relationships'）
    target_bo: str = ""                      # 目标 BO（可从 association 元数据推导）
    
    # 多态关联过滤
    polymorphic_filter: bool = False         # 是否启用多态过滤
    polymorphic_type_field: str = ""         # 类型字段名（如 'target_type'）
    polymorphic_id_field: str = ""           # ID 字段名（如 'target_id'）
    
    # 生命周期绑定
    lifecycle: str = "independent"           # independent | bound
    # bound = cascade_delete + 随父对象查询 + 禁止独立删除
    
    # 自定义表单
    form_mode: str = "standard"              # standard | custom
    form_component: str = ""                 # 自定义表单组件名（form_mode=custom 时）
    form_fields: List[Dict[str, Any]] = field(default_factory=list)  # 声明式表单字段
```

### 4.4 YAML Schema 格式

#### 4.4.1 ValueHelp Out Mapping

```yaml
# 示例：business_object 的 domain_id 字段
fields:
  - id: domain_id
    name: 所属领域
    type: integer
    value_help:
      source:
        type: bo
        target_bo: domain
        value_field: id
        display_field: name
        code_field: code
      behavior:
        binding_strength: strict
        search_fields: [name, code]
        parameter_bindings:
          - local_field: version_id
            target_field: version_id
            required: true
        out_mappings:                          # 新增
          - value_help_field: name
            local_field: domain_name
          - value_help_field: code
            local_field: domain_code
      presentation:
        result_type: dropdown
        display_mode: flat
```

#### 4.4.2 Association Section（统一 annotation）

```yaml
# 当前 annotation section（特例）
sections:
  - key: annotations
    type: annotation            # 特殊类型
    title: 备注信息

# 统一后（纯配置）
sections:
  - key: annotations
    type: association
    association: target         # annotation.yaml 中定义的关联名
    title: 备注信息
    # 多态关联过滤（通用能力，从 association 元数据自动推导）
    polymorphic_filter: true    # 或省略，自动从 association.target_type=polymorphic 推导
    # 生命周期绑定（通用能力，从 association.cascade_delete 自动推导）
    lifecycle: bound            # 或省略，自动从 cascade_delete=true 推导
    # 自定义表单（通用能力）
    form:
      mode: custom
      component: AnnotationForm
      # 或声明式定义
      fields:
        - name: category
          widget: select
          options: enum:annotation_category
        - name: content
          widget: textarea
          rows: 4
```

### 4.5 In/Out Mapping 对称关系

```
┌─────────────────────────────────────────────────────────────┐
│                    ValueHelp In/Out Mapping                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  In Mapping (parameter_bindings)                            │
│  ┌──────────┐    搜索请求参数    ┌──────────────┐           │
│  │ 表单字段  │ ─────────────────→ │ ValueHelp API │           │
│  │ local_field │  target_field   │  查询参数     │           │
│  └──────────┘                    └──────────────┘           │
│                                         │                   │
│                                         ▼                   │
│  Out Mapping (out_mappings)            结果                  │
│  ┌──────────┐    自动回填       ┌──────────────┐           │
│  │ 表单字段  │ ←─────────────── │ ValueHelp 结果 │           │
│  │ local_field │  value_help_field │  extra 字段  │           │
│  └──────────┘                    └──────────────┘           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| 维度 | In Mapping (`parameter_bindings`) | Out Mapping (`out_mappings`) |
|------|----------------------------------|------------------------------|
| 方向 | 表单 → ValueHelp 请求 | ValueHelp 结果 → 表单 |
| 触发时机 | 打开/搜索 ValueHelp 时 | 选择 ValueHelp 项时 |
| 源字段 | `local_field`（表单字段名） | `value_help_field`（结果字段名） |
| 目标字段 | `target_field`（API 参数名） | `local_field`（表单字段名） |
| 数据类型 | 任意（传参） | 任意（回填） |
| 必填支持 | `required: true` | 不需要（可选回填） |

---

## 5. 组件架构

### 5.1 重构后的组件树

```
ObjectPageShell (~300 行)                     ← 新增：骨架组件
├── ObjectPageHeader (~150 行)                ← 新增：Header 组件
│   ├── 返回按钮 + 面包屑
│   ├── 状态徽章
│   ├── StateTransitionButtons
│   └── 操作按钮（YAML-Driven）
├── ObjectPageContent (~200 行)               ← 新增：内容容器 + Tab 导航
│   ├── Tab 导航栏
│   └── Section 渲染分发
│       ├── FieldGroupSection (~200 行)       ← 新增：标准字段组
│       │   └── ObjectPageField (~150 行)     ← 新增：字段渲染单元
│       │       ├── FkLinkField（只读模式）
│       │       ├── el-tag（枚举只读模式）
│       │       ├── ValueHelpField（编辑模式 + Out Mapping）
│       │       └── 动态 Widget（编辑模式）
│       ├── AssociationSection (~350 行)      ← 新增：关联对象（统一 annotation）
│       │   ├── many_to_many（AssignDialog + MetaListPage）
│       │   ├── merged_bo_relationships（独立表格）
│       │   ├── one_to_many/composition（MetaListPage）
│       │   └── 自定义表单支持（form.mode=custom）
│       └── HistorySection (~80 行)           ← 新增：审计日志
│           └── AuditLog + AuditLogDetail
└── AssignmentDialog（已有，保持不变）
```

**关键变化**：
- **移除 AnnotationSection 独立组件**
- **AssociationSection 承担所有关联渲染**，包括 annotation
- **AnnotationForm.vue 作为独立表单组件**，通过 `form.component` 引用

### 5.2 各组件职责与文件路径

| 组件 | 文件路径 | 行数估算 | 职责 |
|------|---------|---------|------|
| ObjectPageShell | `src/components/common/ObjectPage/ObjectPageShell.vue` | ~300 | 骨架布局、props 定义、autoLoadMeta、子组件编排 |
| ObjectPageHeader | `src/components/common/ObjectPage/ObjectPageHeader.vue` | ~150 | Header 渲染、状态徽章、操作按钮、StateTransitionButtons |
| ObjectPageContent | `src/components/common/ObjectPage/ObjectPageContent.vue` | ~200 | Tab 导航、Section 分发、Visibility Engine |
| FieldGroupSection | `src/components/common/ObjectPage/FieldGroupSection.vue` | ~200 | FieldGroup 渲染、折叠控制、Grid 布局 |
| ObjectPageField | `src/components/common/ObjectPage/ObjectPageField.vue` | ~150 | 单字段渲染、ValueHelpField 集成、Out Mapping |
| AssociationSection | `src/components/common/ObjectPage/AssociationSection.vue` | ~350 | 关联对象列表、多态过滤、生命周期绑定、自定义表单 |
| HistorySection | `src/components/common/ObjectPage/HistorySection.vue` | ~80 | AuditLog 集成、分页、筛选 |
| AnnotationForm | `src/components/common/ObjectPage/AnnotationForm.vue` | ~100 | 备注表单（独立组件，通过 form.component 引用） |

### 5.3 AssociationSection 组件设计（统一 annotation）

```vue
<!-- AssociationSection.vue — 关联对象 Section（统一 annotation） -->
<template>
  <div class="op-association-section">
    <!-- many_to_many / reverse_many_to_many -->
    <template v-if="isManyToMany">
      <div class="op-assoc-toolbar">
        <el-button
          v-if="!section.readonly && section.actions?.includes('assign')"
          type="primary"
          size="small"
          @click="$emit('open-assign', section)"
        >
          + 添加
        </el-button>
      </div>
      <MetaListPage
        :ref="el => metaListRef = el"
        :object-type="targetType"
        display-mode="embedded"
        :columns-override="associationColumns"
        :options="manyToManyOptions"
        :row-actions-override="section.readonly ? [] : unassignRowActions"
        :enable-detail="false"
        :enable-auto-crud="false"
        row-key="id"
        @action="$emit('embedded-action', { action: $event, section })"
      />
    </template>

    <!-- merged_bo_relationships -->
    <div v-else-if="section.customFetcher === 'merged_bo_relationships'" class="op-merged-relations">
      <el-table :data="mergedData" v-loading="mergedLoading" size="small" max-height="400">
        <el-table-column label="关系类型" width="120">
          <template #default="{ row }">{{ row.relation_type_name || row.relation_type }}</template>
        </el-table-column>
        <el-table-column label="方向" width="80">
          <template #default="{ row }">{{ row.relation_direction || '-' }}</template>
        </el-table-column>
        <el-table-column prop="source_bo_name" label="源对象" min-width="180" />
        <el-table-column prop="target_bo_name" label="目标对象" min-width="180" />
        <el-table-column prop="relation_desc" label="关系描述" min-width="150" />
      </el-table>
      <div class="op-empty-state" v-if="!mergedLoading && mergedData.length === 0">
        <AppIcon name="link" size="lg" />
        <p>暂无关系数据</p>
      </div>
    </div>

    <!-- one_to_many / composition / parent_child / polymorphic -->
    <template v-else>
      <!-- 工具栏：创建按钮 -->
      <div v-if="showCreateToolbar" class="op-assoc-toolbar">
        <el-button
          v-if="formMode === 'custom'"
          type="primary"
          size="small"
          @click="openCustomForm"
        >
          {{ section.createLabel || '+ 添加' }}
        </el-button>
        <el-button
          v-else-if="!section.readonly && enableAutoCrud"
          type="primary"
          size="small"
          @click="handleStandardCreate"
        >
          {{ section.createLabel || '+ 新建' }}
        </el-button>
      </div>

      <MetaListPage
        v-if="targetType && parentObjectType && parentObjectId"
        :ref="el => metaListRef = el"
        :object-type="targetType"
        :options="oneToManyOptions"
        :initial-filters="effectiveFilters"
        :enable-detail="section.enableDetail !== undefined ? section.enableDetail : true"
        :enable-auto-crud="formMode === 'standard' && (section.enableAutoCrud !== undefined ? section.enableAutoCrud : !section.readonly)"
        :row-mutability="section.rowMutability || (section.readonly ? 'locked' : 'fully_editable')"
        :external-editing="editing"
        :row-actions-override="rowActions"
        @request-edit="$emit('request-edit')"
        @create="handleCreate"
        @edit="handleEdit"
        @action="handleAction"
      />
    </template>

    <!-- 空状态 -->
    <div v-if="showEmptyState" class="op-empty-state">
      <AppIcon name="link" size="lg" />
      <p>{{ emptyStateMessage }}</p>
    </div>

    <!-- 自定义表单 Dialog -->
    <component
      v-if="formComponent && formDialogVisible"
      :is="formComponent"
      v-model:visible="formDialogVisible"
      :editing-id="formEditingId"
      :parent-object-type="parentObjectType"
      :parent-object-id="parentObjectId"
      :initial-data="formInitialData"
      @success="handleFormSuccess"
      @cancel="formDialogVisible = false"
    />
  </div>
</template>

<script setup>
import { computed, ref, shallowRef } from 'vue'
import MetaListPage from '../MetaListPage/MetaListPage.vue'
import AnnotationForm from './AnnotationForm.vue'

const props = defineProps({
  section: { type: Object, required: true },
  objectType: { type: String, default: null },
  objectId: { type: [String, Number], default: null },
  editing: { type: Boolean, default: false },
  uiConfig: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['request-edit', 'open-assign', 'refresh'])

// ────────────────────────────────────────────
// 多态关联过滤（通用能力）
// ────────────────────────────────────────────
const associationMeta = computed(() => {
  const assocName = props.section.association || props.section.assocName
  return props.uiConfig?.associations?.find(a => a.name === assocName) || {}
})

const isPolymorphic = computed(() => {
  if (props.section.polymorphic_filter !== undefined) {
    return props.section.polymorphic_filter
  }
  return associationMeta.value.target_type === 'polymorphic'
})

const polymorphicFilters = computed(() => {
  if (!isPolymorphic.value) return {}
  const typeField = associationMeta.value.polymorphic_type_field || 'target_type'
  const idField = associationMeta.value.polymorphic_id_field || 'target_id'
  return {
    [typeField]: props.objectType,
    [idField]: props.objectId,
  }
})

// ────────────────────────────────────────────
// 生命周期绑定（通用能力）
// ────────────────────────────────────────────
const lifecycle = computed(() => {
  if (props.section.lifecycle !== undefined) {
    return props.section.lifecycle
  }
  return associationMeta.value.cascade_delete ? 'bound' : 'independent'
})

// ────────────────────────────────────────────
// 自定义表单（通用能力）
// ────────────────────────────────────────────
const formMode = computed(() => {
  return props.section.form?.mode || 'standard'
})

const formComponent = shallowRef(null)
const formDialogVisible = ref(false)
const formEditingId = ref(null)
const formInitialData = ref({})

function resolveFormComponent() {
  if (formMode.value !== 'custom') return null
  const componentName = props.section.form?.component
  if (componentName === 'AnnotationForm') return AnnotationForm
  // 动态导入其他自定义表单
  return null
}

function openCustomForm(row = null) {
  formComponent.value = resolveFormComponent()
  formEditingId.value = row?.id || null
  formInitialData.value = row || {}
  formDialogVisible.value = true
}

function handleCreate(payload) {
  if (formMode.value === 'custom') {
    openCustomForm()
  } else {
    // 标准 MetaListPage 处理
    emit('request-edit', { action: 'create', section: props.section })
  }
}

function handleEdit(payload) {
  if (formMode.value === 'custom') {
    openCustomForm(payload.row)
  } else {
    // 标准 MetaListPage 处理
    emit('request-edit', { action: 'edit', section: props.section, row: payload.row })
  }
}

function handleFormSuccess(result) {
  formDialogVisible.value = false
  emit('refresh')
  metaListRef.value?.refresh?.()
}

// ────────────────────────────────────────────
// 统一的 fetcher
// ────────────────────────────────────────────
function getAssociationFetcher() {
  return async (params) => {
    const filters = {
      ...params,
      ...polymorphicFilters.value,  // 多态过滤
      ...props.section.filters,      // 额外静态过滤
    }
    return boService.queryAssociations(
      props.objectType,
      props.objectId,
      props.section.association,
      filters
    )
  }
}

// ────────────────────────────────────────────
// 行操作（统一 edit/delete）
// ────────────────────────────────────────────
const rowActions = computed(() => {
  if (props.section.readonly) return []
  const actions = []
  if (formMode.value === 'custom') {
    actions.push({ key: 'edit', label: '编辑', type: 'primary' })
  }
  if (lifecycle.value === 'bound') {
    actions.push({ key: 'delete', label: '删除', type: 'danger' })
  } else {
    actions.push({ key: 'unassign', label: '移除', type: 'warning' })
  }
  return actions
})

async function handleAction(event) {
  const { action, row } = event
  if (action.key === 'edit') {
    openCustomForm(row)
  } else if (action.key === 'delete') {
    await handleDelete(row)
  } else if (action.key === 'unassign') {
    await handleUnassign(row)
  }
}
</script>
```

### 5.4 AnnotationForm 组件设计

```vue
<!-- AnnotationForm.vue — 独立备注表单组件 -->
<template>
  <el-dialog
    :model-value="visible"
    :title="editingId ? '编辑备注' : '添加备注'"
    width="480px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form label-position="top">
      <el-form-item label="分类">
        <el-select v-model="formData.category" style="width: 100%">
          <el-option
            v-for="cat in categories"
            :key="cat.code"
            :value="cat.code"
            :label="cat.name || cat.label || cat.code"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="内容">
        <el-input
          v-model="formData.content"
          type="textarea"
          :rows="4"
          placeholder="请输入备注内容..."
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="saving" @click="handleSave">
        {{ saving ? '保存中...' : '保存' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import boService from '@/services/boService'

const props = defineProps({
  visible: { type: Boolean, default: false },
  editingId: { type: [String, Number], default: null },
  parentObjectType: { type: String, required: true },
  parentObjectId: { type: [String, Number], required: true },
  initialData: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:visible', 'success', 'cancel'])

const formData = ref({ category: '', content: '' })
const categories = ref([])
const saving = ref(false)

watch(() => props.visible, (val) => {
  if (val) {
    if (props.editingId) {
      formData.value = { ...props.initialData }
    } else {
      formData.value = { category: '', content: '' }
    }
  }
})

onMounted(async () => {
  // 加载分类选项
  const result = await boService.query('enum_value', { enum_type_id: 'annotation_category' })
  if (result.success) {
    categories.value = result.data?.data || result.data || []
  }
})

async function handleSave() {
  if (!formData.value.content?.trim()) {
    ElMessage.warning('请输入备注内容')
    return
  }

  saving.value = true
  try {
    const isEdit = !!props.editingId
    const url = isEdit
      ? `/api/v1/annotations/${props.editingId}`
      : '/api/v1/annotations'
    const body = isEdit
      ? { category: formData.value.category, content: formData.value.content }
      : {
          target_type: props.parentObjectType,
          target_id: props.parentObjectId,
          category: formData.value.category,
          content: formData.value.content,
        }

    const response = await fetch(url, {
      method: isEdit ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('auth_token')}` },
      body: JSON.stringify(body),
    })
    const result = await response.json()

    if (result.success) {
      ElMessage.success(isEdit ? '备注已更新' : '备注已添加')
      emit('success', result.data)
    } else {
      ElMessage.error(result.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>
```

### 5.5 ObjectPageShell 组件设计

```vue
<!-- ObjectPageShell.vue — 骨架组件 -->
<template>
  <div class="object-page" :class="`object-page--${size}`">
    <ObjectPageHeader
      :title="title"
      :subtitle="subtitle"
      :status="status"
      :status-type="statusType"
      :breadcrumbs="breadcrumbs"
      :show-back-button="showBackButton"
      :actions="processedActions"
      :visible-actions="visibleActions"
      :editing="internalEditing"
      :saving="saving"
      :object-type="objectType"
      :object-id="objectId"
      :show-state-transitions="showStateTransitions"
      @back="$emit('back')"
      @navigate="$emit('navigate', $event)"
      @action="handleObjectPageAction"
      @update:editing="$emit('update:editing', $event)"
    >
      <template #breadcrumb><slot name="breadcrumb" /></template>
      <template #actions><slot name="actions" /></template>
    </ObjectPageHeader>

    <ObjectPageContent
      :sections="sections"
      :form-data="formData"
      :field-definitions="effectiveFieldDefs"
      :editing="internalEditing"
      :object-type="objectType"
      :object-id="objectId"
      :card-size="cardSize"
      :value-help-field-keys="valueHelpFieldKeys"
      :enum-field-keys="enumFieldKeys"
      :ui-config="uiConfig"
      :cascade-fields="cascadeFields"
      :is-cascade-field="isCascadeField"
      :get-cascade-parent="getCascadeParent"
      :tabs="tabs"
      :active-tab="activeTab"
      @tab-change="onTabChange"
      @field-update="$emit('field-update', $event)"
      @update:editing="$emit('update:editing', $event)"
      @refresh="$emit('refresh')"
    >
      <template #headerContent><slot name="headerContent" /></template>
      <template #info><slot name="info" /></template>
      <template v-for="(_, name) in $slots" #[name]="slotData">
        <slot :name="name" v-bind="slotData || {}" />
      </template>
    </ObjectPageContent>

    <AssignmentDialog
      v-if="assignDialogState"
      :model-value="assignDialogState.visible"
      :object-type="objectType"
      :object-id="objectId"
      :association-name="assignDialogState.assocName"
      :config="assignDialogState.config"
      :exclude-ids="assignDialogState.excludeIds"
      @success="handleAssignSuccess"
      @update:model-value="(val) => { if (!val) assignDialogState = null }"
    />
  </div>
</template>
```

### 5.6 ObjectPageField 组件设计

```vue
<!-- ObjectPageField.vue — 字段渲染单元 -->
<template>
  <div class="op-field">
    <label>
      {{ fieldLabel }}
      <span v-if="required" class="op-required">*</span>
    </label>

    <!-- 只读模式 -->
    <template v-if="!editing">
      <FkLinkField
        v-if="isFk"
        :value="formData[fieldKey]"
        :display-value="displayValue"
        :target-object-type="fkTargetType"
      />
      <el-tag
        v-else-if="isEnum && formData[fieldKey] != null && formData[fieldKey] !== ''"
        :type="enumColor"
        size="small"
      >
        {{ enumLabel }}
      </el-tag>
      <span v-else class="op-field-value">{{ formattedValue }}</span>
    </template>

    <!-- 编辑模式 -->
    <ValueHelpField
      v-else-if="isValueHelp"
      :model-value="formData[fieldKey]"
      :value-help-config="valueHelpConfig"
      :form-values="formData"
      :disabled="readonly"
      @update:model-value="handleValueUpdate"
      @out-mapping="handleOutMapping"
    />
    <component
      v-else
      :is="widget"
      v-model="formData[fieldKey]"
      v-bind="fieldProps"
      :disabled="readonly"
      :placeholder="placeholder"
    />
  </div>
</template>
```

### 5.7 HistorySection 组件设计

```vue
<!-- HistorySection.vue — 审计日志包装组件 -->
<template>
  <div class="op-audit-log-section">
    <AuditLog
      v-if="objectType && hasRealObjectId"
      :logs="logs"
      :loading="loading"
      :total="total"
      :show-pagination="true"
      :current-page="currentPage"
      :page-size="20"
      :show-filter="true"
      :click-mode="'expand'"
      :object-type="objectType"
      :object-id="objectId"
      @page-change="handlePageChange"
      @filter-change="handleFilterChange"
      @log-click="handleLogClick"
    />
    <div v-else class="op-empty-state">
      <AppIcon name="warning" size="lg" />
      <p>缺少 objectType 或 objectId 属性，无法加载变更历史。</p>
    </div>
    <AuditLogDetail
      v-model:visible="detailVisible"
      :log="selectedLog"
    />
  </div>
</template>
```

---

## 6. API 设计

### 6.1 ValueHelp Out Mapping — 后端变更

**无需新增 API 端点**。Out Mapping 的数据来自现有的 ValueHelp search/resolve 结果中的 `extra` 字段。

**变更点**：

1. `ValueHelpBehavior` 新增 `out_mappings` 字段（数据模型变更）
2. `yaml_loader.py` 解析 `out_mappings` 配置
3. `getUIConfig` API 返回的 `value_help.behavior` 中包含 `out_mappings`

### 6.2 getUIConfig API 返回格式变更

```json
{
  "success": true,
  "data": {
    "fields": [
      {
        "id": "domain_id",
        "name": "所属领域",
        "type": "integer",
        "value_help": {
          "source": {
            "type": "bo",
            "target_bo": "domain",
            "value_field": "id",
            "display_field": "name",
            "code_field": "code"
          },
          "behavior": {
            "binding_strength": "strict",
            "search_fields": ["name", "code"],
            "parameter_bindings": [
              {
                "local_field": "version_id",
                "target_field": "version_id",
                "required": true
              }
            ],
            "out_mappings": [
              {
                "value_help_field": "name",
                "local_field": "domain_name"
              },
              {
                "value_help_field": "code",
                "local_field": "domain_code"
              }
            ]
          },
          "presentation": {
            "result_type": "dropdown"
          }
        }
      }
    ]
  }
}
```

### 6.3 Association Section 配置返回

```json
{
  "success": true,
  "data": {
    "sections": [
      {
        "key": "annotations",
        "type": "association",
        "association": "target",
        "title": "备注信息",
        "polymorphic_filter": true,
        "lifecycle": "bound",
        "form": {
          "mode": "custom",
          "component": "AnnotationForm"
        }
      }
    ],
    "associations": [
      {
        "name": "target",
        "target_type": "polymorphic",
        "polymorphic_type_field": "target_type",
        "polymorphic_id_field": "target_id",
        "cascade_delete": true
      }
    ]
  }
}
```

---

## 7. 前端实现

### 7.1 useValueHelp.js 变更

```javascript
// src/composables/useValueHelp.js — 新增 out mapping 支持

export function useValueHelp(valueHelpConfig, options = {}) {
  // ... 现有代码 ...

  const outMappings = computed(() => {
    return valueHelpConfig?.behavior?.out_mappings || []
  })

  function applyOutMappings(selectedItem, formValues) {
    if (!outMappings.value.length || !selectedItem) return {}

    const updates = {}
    const sourceData = {
      value: selectedItem.value,
      display: selectedItem.display,
      code: selectedItem.code,
      ...(selectedItem.extra || {})
    }

    for (const mapping of outMappings.value) {
      const sourceValue = sourceData[mapping.value_help_field]
      if (sourceValue !== undefined) {
        updates[mapping.local_field] = sourceValue
      }
    }

    return updates
  }

  return {
    // ... 现有返回值 ...
    outMappings,
    applyOutMappings,
  }
}
```

### 7.2 ValueHelpField.vue 变更

```vue
<!-- ValueHelpField.vue — 新增 out-mapping 事件 -->

<script setup>
// ... 现有代码 ...

const {
  optionsList,
  loading,
  displayValue,
  loadOptions,
  loadOptionsDebounced,
  resolveDisplay,
  validateInput,
  getFilterParams,
  isBindingSatisfied,
  outMappings,          // 新增
  applyOutMappings,     // 新增
} = useValueHelp(props.valueHelpConfig)

const emit = defineEmits([
  'update:modelValue',
  'update:displayValue',
  'change',
  'out-mapping',        // 新增
])

function handleSelectChange(val) {
  emit('update:modelValue', val)
  if (Array.isArray(val)) {
    const displays = optionsList.value
      .filter(opt => val.includes(opt.value))
      .map(opt => opt.display)
    emit('update:displayValue', displays.join(', '))
  } else {
    const opt = optionsList.value.find(o => o.value === val)
    emit('update:displayValue', opt?.display || '')

    // 新增：Out Mapping 回填
    if (opt && outMappings.value.length > 0) {
      const updates = applyOutMappings(opt, props.formValues)
      if (Object.keys(updates).length > 0) {
        emit('out-mapping', updates)
      }
    }
  }
  emit('change', val)
}
</script>
```

### 7.3 向后兼容策略

**ObjectPage.vue 保持作为入口组件**，内部委托给 ObjectPageShell：

```vue
<!-- ObjectPage.vue — 向后兼容入口 -->
<template>
  <ObjectPageShell v-bind="$attrs">
    <template v-for="(_, name) in $slots" #[name]="slotData">
      <slot :name="name" v-bind="slotData || {}" />
    </template>
  </ObjectPageShell>
</template>

<script setup>
import ObjectPageShell from './ObjectPageShell.vue'
</script>
```

这样所有现有的 `import ObjectPage` 和 `<ObjectPage>` 使用无需任何修改。

---

## 8. 后端实现

### 8.1 models.py 变更

```python
# meta/core/models.py

@dataclass
class ValueHelpOutMapping:
    """值帮助输出映射"""
    value_help_field: str = ""
    local_field: str = ""


@dataclass
class ValueHelpBehavior:
    binding_strength: str = "strict"
    validation: bool = True
    search_fields: List[str] = field(default_factory=list)
    min_search_length: int = 0
    debounce_ms: int = 300
    multiple: bool = False
    parameter_bindings: List[ValueHelpParameterBinding] = field(default_factory=list)
    out_mappings: List[ValueHelpOutMapping] = field(default_factory=list)  # 新增
    enabled_condition: str = ""
```

### 8.2 yaml_loader.py 变更

```python
# meta/core/yaml_loader.py — 解析 out_mappings

def _parse_value_help_behavior(behavior_dict):
    if not behavior_dict:
        return ValueHelpBehavior()

    parameter_bindings = []
    for pb in behavior_dict.get('parameter_bindings', []):
        parameter_bindings.append(ValueHelpParameterBinding(
            local_field=pb.get('local_field', ''),
            target_field=pb.get('target_field', ''),
            required=pb.get('required', False),
            constant=pb.get('constant', ''),
        ))

    out_mappings = []  # 新增
    for om in behavior_dict.get('out_mappings', []):
        out_mappings.append(ValueHelpOutMapping(
            value_help_field=om.get('value_help_field', ''),
            local_field=om.get('local_field', ''),
        ))

    return ValueHelpBehavior(
        binding_strength=behavior_dict.get('binding_strength', 'strict'),
        validation=behavior_dict.get('validation', True),
        search_fields=behavior_dict.get('search_fields', []),
        min_search_length=behavior_dict.get('min_search_length', 0),
        debounce_ms=behavior_dict.get('debounce_ms', 300),
        multiple=behavior_dict.get('multiple', False),
        parameter_bindings=parameter_bindings,
        out_mappings=out_mappings,  # 新增
        enabled_condition=behavior_dict.get('enabled_condition', ''),
    )
```

---

## 9. 实施计划

### 9.1 里程碑

| 里程碑 | 内容 | 预计工时 | 依赖 |
|--------|------|---------|------|
| M1 | 后端 ValueHelpOutMapping 模型 + YAML 解析 + API 序列化 | 2h | 无 |
| M2 | 前端 useValueHelp Out Mapping 支持 | 2h | M1 |
| M3 | ValueHelpField Out Mapping 事件 | 2h | M2 |
| M4 | ObjectPageField 组件提取 | 3h | 无 |
| M5 | HistorySection 组件提取 | 1h | 无 |
| M6 | AssociationSection 组件提取（含多态过滤、生命周期绑定、自定义表单） | 4h | 无 |
| M7 | AnnotationForm 组件提取 | 2h | 无 |
| M8 | FieldGroupSection 组件提取 | 2h | M4 |
| M9 | ObjectPageHeader 组件提取 | 2h | 无 |
| M10 | ObjectPageContent 组件提取 | 2h | M8, M5, M6, M9 |
| M11 | ObjectPageShell 组装 + 向后兼容 | 2h | M10 |
| M12 | 集成测试 + 回归验证 | 3h | M3, M11, M7 |

### 9.2 实施顺序

```
阶段 A: ValueHelp Out Mapping（M1 → M2 → M3）
  ↓
阶段 B: ObjectPage 组件提取（M4 → M5/M6/M7 并行 → M8 → M9 → M10 → M11）
  ↓
阶段 C: 集成验证（M12）
```

### 9.3 阶段 B 详细任务

| # | 任务 | 文件 | 类型 | 说明 |
|---|------|------|------|------|
| B1 | 提取 ObjectPageField | `src/components/common/ObjectPage/ObjectPageField.vue` | 新增 | 从 ObjectPage.vue L144-L181 提取 |
| B2 | 提取 HistorySection | `src/components/common/ObjectPage/HistorySection.vue` | 新增 | 从 ObjectPage.vue L1029-L1071 + L533-L537 提取 |
| B3 | 提取 AssociationSection | `src/components/common/ObjectPage/AssociationSection.vue` | 新增 | 统一处理所有关联，包括 annotation |
| B4 | 提取 AnnotationForm | `src/components/common/ObjectPage/AnnotationForm.vue` | 新增 | 从 ObjectPage.vue L1131-L1282 + L551-L583 提取 |
| B5 | 提取 FieldGroupSection | `src/components/common/ObjectPage/FieldGroupSection.vue` | 新增 | 从 ObjectPage.vue L437-L501 提取，使用 ObjectPageField |
| B6 | 提取 ObjectPageHeader | `src/components/common/ObjectPage/ObjectPageHeader.vue` | 新增 | 从 ObjectPage.vue L9-L77 + L890-L1023 提取 |
| B7 | 提取 ObjectPageContent | `src/components/common/ObjectPage/ObjectPageContent.vue` | 新增 | 从 ObjectPage.vue L82-L530 提取，编排子组件 |
| B8 | 新增 ObjectPageShell | `src/components/common/ObjectPage/ObjectPageShell.vue` | 新增 | 骨架组件，整合 Header + Content + Dialog |
| B9 | 改造 ObjectPage.vue 为兼容入口 | `src/components/common/ObjectPage/ObjectPage.vue` | 修改 | 委托给 ObjectPageShell |
| B10 | 更新 index.js 导出 | `src/components/common/ObjectPage/index.js` | 修改 | 新增子组件导出 |

### 9.4 阶段 C 验证清单

| # | 验证项 | 方法 |
|---|--------|------|
| C1 | ObjectPage 向后兼容 | 现有 DetailPage / ObjectPageWithChildren 无需修改 |
| C2 | ValueHelp Out Mapping 功能 | 选择 domain_id 后 domain_name/domain_code 自动回填 |
| C3 | annotation section 统一 | annotation 作为 association section 正常渲染 |
| C4 | AnnotationForm 自定义表单 | 添加/编辑/删除备注正常工作 |
| C5 | AuditLog Section | 审计日志分页/筛选/详情正常 |
| C6 | Association Section | many_to_many / one_to_many / merged 关系正常 |
| C7 | StateTransitionButtons | 状态转换按钮正常 |
| C8 | autoLoadMeta | 字段元数据自动加载正常 |
| C9 | CascadeField | 级联字段联动正常 |
| C10 | Legacy Slot 模式 | 旧版 slot 模式正常 |

---

## 10. 测试用例

### 10.1 后端单元测试

```python
# meta/tests/test_value_help_out_mapping.py

def test_value_help_out_mapping_dataclass():
    """测试 ValueHelpOutMapping 数据类"""
    om = ValueHelpOutMapping(value_help_field="name", local_field="domain_name")
    assert om.value_help_field == "name"
    assert om.local_field == "domain_name"


def test_value_help_behavior_with_out_mappings():
    """测试 ValueHelpBehavior 包含 out_mappings"""
    behavior = ValueHelpBehavior(
        binding_strength="strict",
        out_mappings=[
            ValueHelpOutMapping(value_help_field="name", local_field="domain_name"),
            ValueHelpOutMapping(value_help_field="code", local_field="domain_code"),
        ]
    )
    assert len(behavior.out_mappings) == 2
    assert behavior.out_mappings[0].value_help_field == "name"
    assert behavior.out_mappings[1].local_field == "domain_code"
```

### 10.2 前端单元测试

```javascript
// src/composables/__tests__/useValueHelp.outMapping.spec.js

describe('useValueHelp - Out Mapping', () => {
  it('applyOutMappings 应从 extra 中提取字段值', () => {
    const config = {
      source: { type: 'bo', target_bo: 'domain' },
      behavior: {
        out_mappings: [
          { value_help_field: 'name', local_field: 'domain_name' },
          { value_help_field: 'code', local_field: 'domain_code' },
        ]
      }
    }
    const { applyOutMappings } = useValueHelp(config)

    const selectedItem = {
      value: 1,
      display: '技术域',
      code: 'TECH',
      extra: { name: '技术域', code: 'TECH', status: 'active' }
    }

    const updates = applyOutMappings(selectedItem, {})
    expect(updates).toEqual({
      domain_name: '技术域',
      domain_code: 'TECH',
    })
  })
})
```

### 10.3 AssociationSection 集成测试

```javascript
// src/components/common/ObjectPage/__tests__/AssociationSection.spec.js

describe('AssociationSection - 统一关联渲染', () => {
  it('应正确处理多态关联过滤', () => {
    const wrapper = mount(AssociationSection, {
      props: {
        section: {
          key: 'annotations',
          type: 'association',
          association: 'target',
        },
        objectType: 'business_object',
        objectId: 1,
        uiConfig: {
          associations: [{
            name: 'target',
            target_type: 'polymorphic',
            polymorphic_type_field: 'target_type',
            polymorphic_id_field: 'target_id',
          }]
        },
      }
    })
    // 验证 polymorphicFilters
    expect(wrapper.vm.polymorphicFilters).toEqual({
      target_type: 'business_object',
      target_id: 1,
    })
  })

  it('应正确处理自定义表单', async () => {
    const wrapper = mount(AssociationSection, {
      props: {
        section: {
          key: 'annotations',
          type: 'association',
          association: 'target',
          form: { mode: 'custom', component: 'AnnotationForm' },
        },
        objectType: 'business_object',
        objectId: 1,
        uiConfig: { associations: [{ name: 'target' }] },
      }
    })
    expect(wrapper.vm.formMode).toBe('custom')
    // 点击创建按钮应打开自定义表单
    await wrapper.find('.op-assoc-toolbar button').trigger('click')
    expect(wrapper.vm.formDialogVisible).toBe(true)
  })
})
```

---

## 附录 A：文件变更清单

| 文件 | 类型 | 变更说明 |
|------|------|---------|
| `meta/core/models.py` | 修改 | 新增 ValueHelpOutMapping，ValueHelpBehavior 新增 out_mappings |
| `meta/core/yaml_loader.py` | 修改 | _parse_value_help_behavior 解析 out_mappings |
| `meta/api/bo_api.py` | 修改 | _serialize_value_help_behavior 序列化 out_mappings |
| `src/composables/useValueHelp.js` | 修改 | 新增 outMappings computed + applyOutMappings function |
| `src/components/common/ValueHelpField.vue` | 修改 | 新增 out-mapping 事件，选择时触发 |
| `src/components/common/ObjectPage/ObjectPageField.vue` | 新增 | 字段渲染单元组件 |
| `src/components/common/ObjectPage/FieldGroupSection.vue` | 新增 | 标准字段组 Section |
| `src/components/common/ObjectPage/AssociationSection.vue` | 新增 | 关联对象 Section（统一 annotation） |
| `src/components/common/ObjectPage/AnnotationForm.vue` | 新增 | 备注表单组件（独立，通过 form.component 引用） |
| `src/components/common/ObjectPage/HistorySection.vue` | 新增 | 审计日志 Section |
| `src/components/common/ObjectPage/ObjectPageHeader.vue` | 新增 | Header 组件 |
| `src/components/common/ObjectPage/ObjectPageContent.vue` | 新增 | 内容容器 + Tab 导航 |
| `src/components/common/ObjectPage/ObjectPageShell.vue` | 新增 | 骨架组件 |
| `src/components/common/ObjectPage/ObjectPage.vue` | 修改 | 改为委托给 ObjectPageShell |
| `src/components/common/ObjectPage/index.js` | 修改 | 新增子组件导出 |

## 附录 B：YAML 配置示例

### B.1 annotation section 统一配置

```yaml
# ui_view_config.detail.sections
sections:
  - key: annotations
    type: association              # 统一为 association
    association: target            # annotation.yaml 中定义的关联名
    title: 备注信息
    # 以下配置可省略，自动从 association 元数据推导
    # polymorphic_filter: true     # 从 target_type=polymorphic 推导
    # lifecycle: bound             # 从 cascade_delete=true 推导
    form:
      mode: custom
      component: AnnotationForm
```

### B.2 ValueHelp Out Mapping 配置

```yaml
fields:
  - id: domain_id
    name: 所属领域
    type: integer
    value_help:
      source:
        type: bo
        target_bo: domain
        value_field: id
        display_field: name
        code_field: code
      behavior:
        out_mappings:
          - value_help_field: name
            local_field: domain_name
          - value_help_field: code
            local_field: domain_code
```

## 附录 C：风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 组件拆分导致 props 传递层级过深 | 中 | 中 | 使用 provide/inject 传递共享状态 |
| annotation section 统一后兼容性问题 | 高 | 低 | ObjectPage.vue 保持向后兼容入口 |
| Out Mapping 回填触发不必要的 watch 副作用 | 中 | 低 | 使用 nextTick + formRenderKey 控制 |
| extra 字段不包含 out_mapping 所需字段 | 中 | 低 | applyOutMappings 忽略 undefined 字段 |

---

> **最后更新**: 2026-05-26
> **版本变更**: v1.0 → v2.0（移除 AnnotationSection 独立组件，统一到 AssociationSection）
