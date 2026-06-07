# 枚举依赖关系通用化 Spec — UI 适配专项分析

> Edition: v4 — 新增 UI 适配细节、ValueHelp 影响分析、上层应用适配方案
>
> 关联文件：spec.md（概要）/ optimization-plan.md（后端方案）/ tasks.md（任务分解）

---

## 一、现有架构全景

### 1.1 枚举管理 UI 架构

```
菜单: /business-config  ──► GenericTabContainer
                              ├── Tab: "枚举类型" 
                              │    ├─ 列表: GenericObjectList(objectType='enum_type')
                              │    │          └─ MetaListPage (元数据驱动, YAML 配置列)
                              │    └─ 详情: ObjectDetailPage(objectType='enum_type')
                              │              └─ DetailPage (元数据驱动, YAML 配置 facets)
                              └── Tab: "枚举值" (由 enum_type 详情页子区域进入)
                                   └─ EnumValueList(objectType='enum_value')
                                         └─ MetaListPage

表单字段渲染 (MetaListPage/DetailPage 利用 Schema 自动生成):
  widget: input      → <a-input>
  widget: textarea   → <a-textarea> (当前 dimension_schema 用此)
  widget: select     → <a-select> (填充 YAML options/enum_values)
  widget: value_help → ValueHelpField (调用 /api/v2/value-help/...)
  widget: badge      → <a-tag> 彩色标签
```

### 1.2 当前 enum_type 详情页结构

```yaml
# enum_type.yaml:L150-168
detail:
  facets:
    - title: 基本信息      # id, name, category, mutability, description
    - title: 维度配置      # dimension_schema (widget: textarea — 裸 JSON!)
    - title: 系统信息      # created_at, updated_at
  child_sections:
    - child_object: enum_value  # 枚举值子列表 (MetaListPage)
```

**问题**：`dimension_schema` 裸 JSON 展示，无关联管理 UI。未来需要增加 "枚举依赖" 子区域。

### 1.3 现有 relationship 关系数据渲染路径

```
路径 A：ObjectPage 合并关系表（硬编码）
  ├─ YAML: business_object.yaml detail.facets[type=association].customFetcher=merged_bo_relationships
  ├─ 模板: ObjectPage.vue:L357-L367
  └─ 显示: <el-table-column prop="relation_code" /> ← 原始编码，无枚举解析

路径 B：关系表单字段（YAML 驱动）
  ├─ relationship.yaml L922-955: relation_type 字段
  ├─ widget: select + enum_type: relation_type
  ├─ value_help.source.type: enum + enum_type_id: relation_type
  ├─ 表单渲染: DetailPage → widget=select → <a-select> (从 YAML enum_values 读取)
  │           或 widget=value_help → ValueHelpField → /api/v2/value-help/enum/relation_type
  └─ 过滤器: RelationFilterSection.vue → EnumService.loadOptions('relation_type')

路径 C：导入导出
  └─ fieldExtractors.js:L153: 按字段名识别 relation_type
```

### 1.4 ValueHelp 系统现状

```
ValueHelp 链路:
  Frontend                     Backend
  ┌──────────────┐         ┌─────────────────────────┐
  │ ValueHelpField│ ─GET──►│ /api/v2/value-help/     │
  │ useValueHelp │         │   enum/{enum_type_id}   │
  │ boService.   │         │                          │
  │   searchVH() │         │ └─► EnumValueHelpProvider│
  └──────────────┘         │      ├─ enum_type_id     │
                            │      ├─ filter_by_       │
                            │      │   dimension       │  ← 当前: 基于 dimensions JSON
                            │      └─ value_filter     │     过滤 (dimensions__xxx)
                            └─────────────────────────┘
```

**当前 `EnumValueHelpProvider` 的维度过滤**（[value_help_providers.py:L39-L43](file:///d:/filework/excel-to-diagram/meta/core/value_help_providers.py#L39-L43)）：

```python
if self.filter_by_dimension:
    mapping = self.filter_by_dimension.get("mapping", {})
    for dim_field in mapping:
        if dim_field in filters:
            combined_filters["dimensions__" + dim_field] = filters[dim_field]
```

它是基于 `enum_values.dimensions` JSON 字段做过滤的（如 `dimensions__direction = PUSH`）。而新方案中维度数据将迁移到 `enum_dependency_links` 表。

### 1.5 文件中 relation_code / relation_type 引用汇总

| 位置 | 使用方式 | 枚举解析 |
|------|---------|:---:|
| [ObjectPage.vue:L359](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPage.vue#L359) | `prop="relation_code"` | ❌ |
| [ObjectPage.vue:L452-L460](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPage.vue#L452-L460) | `getEnumLabel(fieldKey, val)` | ✅ (仅限有 options 的字段) |
| [RelationFilterSection.vue:L30-L56](file:///d:/filework/excel-to-diagram/src/components/common/RelationScopeTree/RelationFilterSection.vue#L30-L56) | `EnumService.loadOptions('relation_type')` | ✅ |
| [useMultiObjectPage.js:L361-L382](file:///d:/filework/excel-to-diagram/src/composables/useMultiObjectPage.js#L361-L382) | `relation_code__in` 过滤参数 | ❌ |
| [useRelationClassifier.js:L339](file:///d:/filework/excel-to-diagram/src/composables/useRelationClassifier.js#L339) | `r.relation_code` | ❌ |
| [archDataConverter.js:L133-L137](file:///d:/filework/excel-to-diagram/src/services/archDataConverter.js#L133-L137) | `rel.relation_code` + `rel.relation_type_name` | ❌ |
| [fieldExtractors.js:L153](file:///d:/filework/excel-to-diagram/src/utils/fieldExtractors.js#L153) | 按字段名匹配提取 | ❌ |
| [relationship.yaml:L970-L981](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L970-L981) | `relation_type_name` virtual 字段 | — |

---

## 二、UI 适配方案

### 2.1 enum_type 详情页：新增 "枚举依赖" 子区域

**目标**：在 `enum_type` 详情页中，在 "维度配置" (dimension_schema textarea) 之外，新增一个可交互的依赖管理区域。

```
enum_type 详情页改造:

改造前:
  ┌──────────────────┐
  │ 基本信息          │
  ├──────────────────┤
  │ 维度配置          │
  │  [dimension_schema│
  │    textarea]      │  ← 裸 JSON，不可交互
  ├──────────────────┤
  │ 枚举值 (子列表)   │
  ├──────────────────┤
  │ 系统信息          │
  └──────────────────┘

改造后:
  ┌──────────────────┐
  │ 基本信息          │
  ├──────────────────┤
  │ 维度配置           │
  │  [dimension_schema│  ← 保留但标记为 "(由依赖关系自动计算)"
  │    textarea 只读] │
  ├──────────────────┤
  │ 枚举依赖 (*新增*) │
  │  ┌─────────────┐ │
  │  │ 父值    │ 子类型 │ 操作   │ │  ← 可编辑的依赖表
  │  │GENERATES│dir    │[删除] │ │
  │  │UPDATES  │dir    │[删除] │ │
  │  │TRIGGERS │dir    │[删除] │ │
  │  │[+ 新增依赖]   │ │ │
  │  └─────────────┘ │
  ├──────────────────┤
  │ 枚举值 (子列表)   │
  ├──────────────────┤
  │ 系统信息          │
  └──────────────────┘
```

**实现方式**：在 `enum_type.yaml` 的 `child_sections` 中新增 `enum_dependency_link` 子对象区域，利用现有的 `MetaListPage` 组件渲染依赖列表，CRUD 操作由 YAML 声明驱动。

#### enum_type.yaml 改动

```yaml
# 在 child_sections 中新增 (位于 enum_value 之前)
child_sections:
  - child_object: enum_dependency_link       # 新增
    title: 枚举依赖
    display: expandable
    pageSize: 20
    useMetaList: true
    enableDetail: true
    enableAutoCrud: true                     # 允许增删
    fixedFilters:                            # 过滤器：只显示当前 enum_type 的依赖
      - field: parent_enum_type_id
        value: "{id}"                        # 动态替换为当前 enum_type.id
    rowMutability: fully_editable
  - child_object: enum_value                 # 保持不变
    ...
```

#### 新增 enum_dependency_link.yaml

```yaml
id: enum_dependency_link
name: 枚举依赖关系
table_name: enum_dependency_links
description: 枚举类型间的依赖关系（维度/级联/分类）

aspects: [audit_aspect]
import_export:
  import_enabled: true
  export_enabled: true

ui_view_config:
  list:
    pageSize: 20
    columns:
      - key: parent_enum_value
        title: 父枚举值
        width: 150
      - key: child_enum_type_id
        title: 子枚举类型
        width: 150
      - key: child_enum_value
        title: 子枚举值 (NULL=全部)
        width: 150
  detail:
    facets:
      - title: 基本信息
        type: fieldGroup
        fields:
          - parent_enum_type_id
          - parent_enum_value
          - child_enum_type_id
          - child_enum_value

fields:
  - id: parent_enum_type_id
    name: 父枚举类型
    type: string
    db_column: parent_enum_type_id
    required: true
    ui:
      widget: select
      enum_type: all_enums              # 特殊：指向所有枚举类型
      placeholder: 选择父枚举类型
  - id: parent_enum_value
    name: 父枚举值
    type: string
    db_column: parent_enum_value
    required: true
    ui:
      widget: select
      enum_type: dyn_parent_values      # 特殊：根据 parent_enum_type_id 动态加载
  - id: child_enum_type_id
    name: 子枚举类型
    type: string
    db_column: child_enum_type_id
    required: true
    ui:
      widget: select
      enum_type: all_enums
      placeholder: 选择子枚举类型
  - id: child_enum_value
    name: 子枚举值
    type: string
    db_column: child_enum_value
    description: 留空表示该子类型下的所有值都可用
    ui:
      widget: select
      placeholder: 留空=全部可用
      enum_type: dyn_child_values       # 特殊：根据 child_enum_type_id 动态加载

relations:
  - id: dep_to_parent_enum_type
    name: 父枚举类型
    type: reference
    target: enum_type
    foreign_key: parent_enum_type_id
  - id: dep_to_child_enum_type
    name: 子枚举类型
    type: reference
    target: enum_type
    foreign_key: child_enum_type_id
```

### 2.2 ValueHelp 系统适配

#### 影响分析

| ValueHelp 能力 | 当前基于 | 需要改为 |
|---------------|---------|---------|
| 枚举选项加载 | enum_values 表 (code + name) | **不变** |
| 维度过滤 | `dimensions__` JSON 查询 | **改为** `enum_dependency_links` JOIN 查询 |
| 绑定强度校验 | behavior.binding_strength | **不变** |

#### 改动方案：EnumValueHelpProvider 维度过滤适配

```python
# value_help_providers.py 改动

class EnumValueHelpProvider(ValueHelpProvider):
    def search(self, query, search_fields, filters, page, page_size, sort, user_context):
        combined_filters = dict(filters)
        combined_filters["enum_type_id"] = self.enum_type_id
        
        if self.filter_by_dimension:
            # 旧逻辑（保留向后兼容）
            mapping = self.filter_by_dimension.get("mapping", {})
            for dim_field in mapping:
                if dim_field in filters:
                    combined_filters["dimensions__" + dim_field] = filters[dim_field]
            
            # 新逻辑：从 enum_dependency_links 派生维度过滤
            if self.filter_by_dimension.get("use_dependency_links"):
                parent_value = filters.get("_parent_enum_value")
                if parent_value:
                    # 查询 enum_dependency_links 获取该值的子枚举类型
                    deps = self._get_dependencies(self.enum_type_id, parent_value)
                    for dep in deps:
                        # 传递依赖信息给前端
                        pass
```

**但更重要的是**：新 API `/api/v1/enum-dependencies/parent/{type_id}/{value}` 已经解决了 "前端需要知道选中 GENERATES 后该显示哪个维度选择器" 这个问题。ValueHelp 系统主要负责 "枚举值的下拉选项加载 + 搜索"，维度过滤是增强特性，本期可暂不涉及。

#### 本次不涉及 ValueHelp 改动

- 维度过滤 (`filter_by_dimension`) 已有机制保持不变
- 新 API `/api/v1/enum-dependencies/...` 独立于 ValueHelp 系统
- 未来需要维度联动过滤时，再统一接入 `enum_dependency_links`

### 2.3 关系表单 — 维度选择器集成

#### 当前关系表单入口

关系表单通过 `DetailPage` 渲染，字段由 `relationship.yaml` 的 `form.sections` 定义：

```
关系创建/编辑表单:
  ├─ relation_type (widget: select, enum_type: relation_type)
  ├─ source_bo_code (widget: value_help)
  ├─ target_bo_code (widget: value_help)
  └─ relation_desc (widget: textarea)
```

#### 改造后

```
关系创建/编辑表单:
  ├─ relation_type (widget: select, enum_type: relation_type)
  │   └─ 当选中 GENERATES/UPDATES/TRIGGERS 时
  │       └─ [动态追加] EnumDependencySelector
  │            └─ direction 下拉 (PUSH/PULL/BIDIRECTIONAL)
  └─ source_bo_code / target_bo_code / relation_desc (不变)
```

**实现方式**：
- `EnumDependencySelector.vue` 是一个独立组件，监听父组件的 `relation_type` v-model 值
- 调用 `EnumService.loadDependencyOptions('relation_type', selectedValue)`
- 返回值决定渲染哪个子选择器（方向/强度/空）
- 双向绑定维度值到 `relation_type_dimensions` 字段（关系表中存储维度 JSON）

```
EnumDependencySelector 组件接口:

Props:
  parentEnumTypeId  : string   // 'relation_type'
  parentEnumValue   : string   // 'GENERATES'
  modelValue        : object   // { direction: 'PUSH' }

Events:
  update:modelValue  →  { direction: 'PUSH' }
```

### 2.4 ObjectPage 合并关系表 — 枚举显示改造

#### 当前代码（硬编码）

```vue
<!-- ObjectPage.vue:L357-L367 -->
<el-table-column prop="relation_code" label="关系编码" width="200" />
```

#### 改造后

```vue
<el-table-column label="关系类型" width="120">
  <template #default="{ row }">
    <EnumFieldDisplay
      :value="row.relation_type"
      enum-type="relation_type"
      display-field="name"
    />
  </template>
</el-table-column>
```

同时 `business_object.yaml` 的 `associations.columns` 需要同步修改：

```yaml
# business_object.yaml associations.columns
columns:
  - id: relation_type         # 改: relation_code → relation_type
    label: 关系类型
  - id: source_bo_name
    label: 源对象
  - id: target_bo_name
    label: 目标对象
  - id: relation_desc
    label: 关系描述
```

### 2.5 EnumService 扩展

```javascript
// enumService.js 新增方法

/**
 * 加载枚举依赖选项（维度/级联等）
 * @param {string} enumTypeId - 父枚举类型ID
 * @param {string} enumValue - 父枚举值
 * @returns {Array<{enumTypeId, enumTypeName, values: Array<{code, name, nameEn}>}>}
 */
async loadDependencyOptions(enumTypeId, enumValue) {
  if (!enumTypeId || !enumValue) return []
  
  const cacheKey = `dep:${enumTypeId}:${enumValue}`
  const cached = this._cache.get(cacheKey)
  if (cached) return cached
  
  const response = await fetch(
    `${API_BASE}/api/v1/enum-dependencies/parent/${enumTypeId}/${enumValue}`
  )
  const data = await response.json()
  const deps = data?.data?.dependencies || []
  
  this._cache.set(cacheKey, deps, { ttl: 5 * 60 * 1000 })
  return deps
}
```

### 2.6 数据流入/流出路径汇总

```
                    ┌───────────────────────────────┐
                    │     enum_dependency_links     │
                    │  (权威数据源)                   │
                    └───────┬───────────────────────┘
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
  │ enum_type    │  │  API 层       │  │ ValueHelp 系统    │
  │ 详情页        │  │ /enum-dep/   │  │ (未来适配)        │
  │ (管理依赖)   │  │  parent/... │  │ filter_by_dim     │
  └──────────────┘  └──────┬───────┘  └──────────────────┘
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
  │ EnumService  │  │ EnumDep      │  │ ObjectPage.vue   │
  │ loadDepOpts()│  │ Selector.vue │  │ + EnumFieldDisplay│
  └──────────────┘  └──────────────┘  └──────────────────┘
```

### 2.7 各应用适配方案一览

| 应用/组件 | 当前行为 | 适配方案 | Phase |
|----------|---------|---------|:---:|
| **enum_type 详情页** | `dimension_schema` textarea 裸JSON | 新增 `enum_dependency_link` 子区域，可增删依赖 | 3-4 |
| **enum_value 列表** | 已有 `dimensions` textarea | 保留（向后兼容），权限标记只读 | 3 |
| **EnumValueHelpProvider** | `filter_by_dimension` 基于 JSON | 保留现有逻辑，未来增加 `enum_dependency_links` 路径 | 5 |
| **DetailPage 表单** | widget=select 加载 enum_values | **不变** — select 组件直接查 enum_values 表，不涉及依赖 | — |
| **ValueHelpField** | 调用 /api/v2/value-help/enum/xxx | **不变** — 本期不涉及维度过滤增强 | — |
| **EnumDependencySelector** | 不存在 | **新增组件**，集成到关系表单 | 4 |
| **EnumFieldDisplay** | 已创建但未使用 | 在 ObjectPage 中启用 | 4 |
| **ObjectPage 合并关系** | `prop="relation_code"` | 改用 `relation_type` + `EnumFieldDisplay` | 4 |
| **RelationFilterSection** | `EnumService.loadOptions('relation_type')` | **不变** — 过滤器已工作正常 | — |
| **useMultiObjectPage** | `relation_code__in` 过滤 | **不变** — 此为后端查询参数，非UI | — |
| **archDataConverter** | `rel.relation_code` | 增加 `rel.relation_type` 传递 | 4 |
| **fieldExtractors** | 提取 `relation_type` | **不变** — 已支持此字段名 | — |
| **导入导出** | Excel 含 relation_code 列 | 导出时增加 `relation_type_name` 列供人类阅读 | 4 |

---

## 三、实施时序

```
Phase 1: 数据模型 (models.py + enum_dependency_links 表 + migrate)
  │
Phase 2: 迁移脚本 (dimensions JSON → enum_dependency_links)
  │
Phase 3: API (GET /api/v1/enum-dependencies/parent/...)
  │         + enum_dependency_link.yaml (元模型定义)
  │         + enum_type.yaml 增加 child_section
  ├──────────────────────────────────────────────┐
  │                                              │
Phase 4a: 管理端 UI                         Phase 4b: 业务端 UI
  ├─ enum_type 详情页可管理依赖                ├─ EnumDependencySelector.vue
  ├─ enum_dependency_link CRUD               ├─ ObjectPage 枚举显示改造
  └─ dimension_schema 只读                    └─ EnumFieldDisplay 启用
  │                                              │
  └──────────────────────────────────────────────┘
                    │
              Phase 5: ValueHelp 适配（future，暂不实施）
                    └─ EnumValueHelpProvider 接入 dependency_links
```

## 四、文件变更总览

| 文件 | 类型 | Phase | 说明 |
|------|------|:---:|------|
| `meta/core/models.py` | 新增 | 1 | `Direction` 枚举类 |
| `meta/scripts/migrate_enums.py` | 修改 | 1-2 | 注册 Direction + 迁移脚本 |
| `meta/scripts/init_database.py` | 新增 | 1 | `create_enum_dependency_links_table()` |
| `meta/api/enum_api.py` | 新增 | 3 | 依赖查询 API endpoint |
| `meta/schemas/enum_dependency_link.yaml` | **新增** | 3 | 元模型定义（让 MetaListPage 可渲染） |
| `meta/schemas/enum_type.yaml` | 修改 | 3 | 新增 `enum_dependency_link` child_section |
| `meta/schemas/business_object.yaml` | 修改 | 4 | associations.columns: relation_code → relation_type |
| `src/services/enumService.js` | 新增 | 4 | `loadDependencyOptions()` |
| `src/components/common/EnumDependencySelector.vue` | **新增** | 4 | 依赖选择器组件 |
| `src/components/common/ObjectPage/ObjectPage.vue` | 修改 | 4 | relation_code → relation_type + EnumFieldDisplay |
| `src/services/archDataConverter.js` | 修改 | 4 | 透传 relation_type |
