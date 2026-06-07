# 运行态视图配置引擎 Spec

## Why

当前前端组件（DetailPanel、EditForm、index.vue）中的字段定义、列表列、表单字段均为硬编码，与 YAML Schema 无关联。新增对象类型需要同时修改 4 处代码（YAML + 3 个 Vue 组件），维护成本高且容易不一致。

同时，在 AI Agent 背景下，Agent 需要理解业务对象的语义、可用操作、参数定义，当前架构无法提供这些信息。借鉴 Palantir Foundry 的 Ontology 架构，元数据应成为 Human UI 和 AI Agent 的共同数据源。

## What Changes

- **扩展 YAML Schema**：新增 `ui` 注解段（字段级 UI 定义）和 `views` 配置段（视图级配置）
- **新增 ViewConfigService**：后端服务，基于 Schema 自动生成视图配置
- **新增 View Config API**：`GET /api/v1/meta/{object_type}/view-config`
- **新增 Agent Context API**：`GET /api/v1/agent/context/{object_type}`、`GET /api/v1/agent/tools`
- **新增前端动态渲染组件**：DynamicTable、DynamicDetail、DynamicForm
- **新增 useViewConfig composable**：前端配置加载与缓存
- **重构现有组件**：使用动态配置替代硬编码

## Impact

- Affected specs: 元模型核心定义、前端组件架构
- Affected code:
  - `meta/core/models.py` - 新增 UIAnnotation、ViewConfig 等数据类
  - `meta/core/yaml_loader.py` - 解析 ui 段和 views 段
  - `meta/services/view_config_service.py` - 新增视图配置服务
  - `meta/api/meta_api.py` - 新增视图配置 API
  - `meta/api/agent_api.py` - 新增 Agent API
  - `meta/schemas/*.yaml` - 所有 schema 文件添加 ui 注解
  - `src/composables/useViewConfig.js` - 新增配置加载
  - `src/components/DynamicTable.vue` - 新增动态表格
  - `src/components/DynamicDetail.vue` - 新增动态详情
  - `src/components/DynamicForm.vue` - 新增动态表单
  - `src/views/ArchDataManageApp/index.vue` - 重构使用动态组件

## ADDED Requirements

### Requirement: UI 注解定义

系统 SHALL 在 MetaField 中提供 `ui` 注解段，定义字段级 UI 属性：

```python
@dataclass
class UIAnnotation:
    lineItem: Optional[Dict] = None      # 列表视图列配置 {position, importance, width}
    fieldGroup: Optional[str] = None     # 详情/表单分组标识
    fieldGroupPosition: int = 100        # 分组内位置
    widget: str = "input"                # 表单控件类型
    visible: bool = True                 # 是否在 UI 中显示
    editable: bool = True                # 是否可编辑
    width: str = "auto"                  # 列表列宽度
```

#### Scenario: 列表显示字段
- **WHEN** 字段配置 `ui.lineItem: { position: 10, importance: high }`
- **THEN** 该字段在列表视图中显示，位置为第 10 列

#### Scenario: 详情分组字段
- **WHEN** 字段配置 `ui.fieldGroup: basic, ui.fieldGroupPosition: 10`
- **THEN** 该字段在详情页"基本信息"分组中显示，位置为第 10 个

#### Scenario: 隐藏字段
- **WHEN** 字段配置 `ui.visible: false`
- **THEN** 该字段不在任何 UI 中显示（如 id, created_at）

### Requirement: 视图配置定义

系统 SHALL 在 MetaObject 中提供 `views` 配置段，定义视图级配置：

```python
@dataclass
class ListViewConfig:
    columns: List[str] = field(default_factory=list)  # 显式指定列（可选）
    defaultSort: str = ""                              # 默认排序字段
    filters: List[str] = field(default_factory=list)   # 筛选字段
    pageSize: int = 20                                 # 分页大小

@dataclass
class DetailFacet:
    title: str                                         # 分区标题
    type: str = "fieldGroup"                           # 分区类型
    qualifier: str = ""                                # 关联的 fieldGroup
    fields: List[str] = field(default_factory=list)   # 显式指定字段

@dataclass
class DetailViewConfig:
    facets: List[DetailFacet] = field(default_factory=list)
    showChangeHistory: bool = True
    showRelations: bool = True

@dataclass
class FormSection:
    title: str
    fields: List[str] = field(default_factory=list)

@dataclass
class FormViewConfig:
    sections: List[FormSection] = field(default_factory=list)
    layout: str = "vertical"

@dataclass
class ViewConfig:
    list: ListViewConfig = field(default_factory=ListViewConfig)
    detail: DetailViewConfig = field(default_factory=DetailViewConfig)
    form: FormViewConfig = field(default_factory=FormViewConfig)
```

#### Scenario: 列表默认配置
- **WHEN** 未显式配置 `views.list.columns`
- **THEN** 自动使用所有 `ui.lineItem` 字段作为列表列

#### Scenario: 详情分区配置
- **WHEN** 配置 `views.detail.facets: [{title: "基本信息", qualifier: "basic"}]`
- **THEN** 详情页显示"基本信息"分区，包含所有 `ui.fieldGroup: basic` 的字段

### Requirement: 视图配置服务

系统 SHALL 提供 ViewConfigService，基于 YAML Schema 自动生成视图配置：

```python
class ViewConfigService:
    def get_view_config(self, object_type: str) -> Dict[str, Any]:
        """获取完整视图配置"""
        
    def get_list_view_config(self, object_type: str) -> Dict[str, Any]:
        """获取列表视图配置"""
        
    def get_detail_view_config(self, object_type: str) -> Dict[str, Any]:
        """获取详情视图配置"""
        
    def get_form_view_config(self, object_type: str) -> Dict[str, Any]:
        """获取表单视图配置"""
        
    def invalidate_cache(self, object_type: str = None):
        """清除缓存"""
```

#### Scenario: 自动生成列表配置
- **WHEN** 调用 `get_list_view_config("domain")`
- **THEN** 返回基于 `ui.lineItem` 自动生成的列配置

#### Scenario: 缓存机制
- **WHEN** 首次请求某对象类型的配置
- **THEN** 解析 YAML 并缓存结果
- **AND** 后续请求直接返回缓存

#### Scenario: 缓存失效
- **WHEN** YAML 文件被修改
- **THEN** 自动清除相关缓存

### Requirement: 视图配置 API

系统 SHALL 提供视图配置 API：

```
GET /api/v1/meta/{object_type}/view-config
Response: {
  "success": true,
  "data": {
    "objectType": "domain",
    "objectName": "领域",
    "listView": { "columns": [...], "defaultSort": "name" },
    "detailView": { "facets": [...] },
    "formView": { "sections": [...] },
    "fieldDefinitions": { "name": {...}, "code": {...} }
  }
}
```

#### Scenario: 获取视图配置
- **WHEN** 前端请求 `GET /api/v1/meta/domain/view-config`
- **THEN** 返回 domain 对象的完整视图配置

#### Scenario: 未知对象类型
- **WHEN** 请求不存在的对象类型
- **THEN** 返回 404 错误

### Requirement: Agent Context API

系统 SHALL 提供 Agent 上下文 API，支持 AI Agent 理解业务对象：

```
GET /api/v1/agent/tools
Response: {
  "success": true,
  "data": [
    {
      "name": "create_domain",
      "description": "创建领域对象",
      "parameters": { "type": "object", "properties": {...} }
    }
  ]
}

GET /api/v1/agent/context/{object_type}
Response: {
  "success": true,
  "data": {
    "objectType": "domain",
    "objectName": "领域",
    "description": "...",
    "fields": [...],
    "relations": [...],
    "actions": [...],
    "validations": [...]
  }
}
```

#### Scenario: 获取所有工具
- **WHEN** Agent 请求 `GET /api/v1/agent/tools`
- **THEN** 返回所有对象类型的 CRUD 操作作为 Tool Schema

#### Scenario: 获取对象上下文
- **WHEN** Agent 请求 `GET /api/v1/agent/context/domain`
- **THEN** 返回 domain 对象的完整语义信息

### Requirement: Action Types 自动转 Tool Schema

系统 SHALL 将 YAML Schema 中的 actions 自动转换为 LLM Tool Schema：

```python
class MetaAction:
    def to_tool_schema(self) -> Dict[str, Any]:
        """将 Action 转换为 OpenAI Function Calling 格式"""
        return {
            "name": self.id,
            "description": f"{self.name}: {self.description}",
            "parameters": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
```

#### Scenario: CRUD 操作转 Tool
- **WHEN** 对象有 `crud_create` action
- **THEN** 自动生成 `create_{object_type}` Tool Schema

#### Scenario: 自定义操作转 Tool
- **WHEN** 对象有自定义 action
- **THEN** 根据 action 参数定义生成 Tool Schema

### Requirement: 前端动态渲染组件

系统 SHALL 提供动态渲染组件，基于视图配置渲染 UI：

#### DynamicTable
```vue
<DynamicTable 
  :config="viewConfig.listView" 
  :data="tableData"
  :selectable="true"
  @row-click="handleRowClick"
  @edit="handleEdit"
  @delete="handleDelete"
/>
```

#### DynamicDetail
```vue
<DynamicDetail 
  :config="viewConfig.detailView"
  :data="recordData"
  @back="handleBack"
  @edit="handleEdit"
  @delete="handleDelete"
/>
```

#### DynamicForm
```vue
<DynamicForm 
  :config="viewConfig.formView"
  :data="formData"
  :mode="'create'"
  @save="handleSave"
  @cancel="handleCancel"
/>
```

#### Scenario: 动态表格渲染
- **WHEN** DynamicTable 接收 listView 配置
- **THEN** 根据 columns 配置动态渲染表格列

#### Scenario: 动态详情渲染
- **WHEN** DynamicDetail 接收 detailView 配置
- **THEN** 根据 facets 配置动态渲染详情分区

#### Scenario: 动态表单渲染
- **WHEN** DynamicForm 接收 formView 配置
- **THEN** 根据 sections 配置动态渲染表单字段

### Requirement: 前端配置缓存

系统 SHALL 在前端提供配置缓存机制：

```javascript
export function useViewConfig(objectType) {
  const cache = new Map()
  
  async function loadConfig() {
    if (cache.has(objectType)) {
      return cache.get(objectType)
    }
    const config = await api.get(`/meta/${objectType}/view-config`)
    cache.set(objectType, config)
    return config
  }
  
  return { config, loading, error, reload }
}
```

#### Scenario: 配置缓存
- **WHEN** 首次加载某对象类型的配置
- **THEN** 缓存到内存
- **AND** 后续请求直接返回缓存

#### Scenario: 配置刷新
- **WHEN** 调用 `reload()`
- **THEN** 清除缓存并重新加载

## MODIFIED Requirements

### Requirement: MetaField 扩展

`MetaField` SHALL 新增 `ui` 属性：

```python
@dataclass
class MetaField:
    # ... existing fields ...
    ui: UIAnnotation = field(default_factory=UIAnnotation)
```

### Requirement: MetaObject 扩展

`MetaObject` SHALL 新增 `view_config` 属性：

```python
@dataclass
class MetaObject:
    # ... existing fields ...
    view_config: ViewConfig = field(default_factory=ViewConfig)
```

### Requirement: MetaAction 扩展

`MetaAction` SHALL 新增 `to_tool_schema()` 方法：

```python
@dataclass
class MetaAction:
    # ... existing fields ...
    parameters: List[ActionParameter] = field(default_factory=list)
    
    def to_tool_schema(self) -> Dict[str, Any]:
        """转换为 LLM Tool Schema"""
```

## REMOVED Requirements

无移除的需求。现有硬编码组件将保留作为 fallback，逐步迁移。

## YAML 示例

### 完整 Schema 示例（domain.yaml）

```yaml
id: domain
name: 领域
table_name: domains
description: 业务领域定义

fields:
  - id: id
    name: ID
    type: integer
    ui:
      visible: false

  - id: name
    name: 名称
    type: string
    required: true
    semantics:
      display_name: true
      business_key: true
    ui:
      lineItem: { position: 10, importance: high }
      fieldGroup: basic
      fieldGroupPosition: 10
      widget: input
      required: true

  - id: code
    name: 编码
    type: string
    semantics:
      business_key: true
    ui:
      lineItem: { position: 20 }
      fieldGroup: basic
      fieldGroupPosition: 20

  - id: version_id
    name: 版本
    type: integer
    ui:
      lineItem: false
      fieldGroup: hierarchy
      fieldGroupPosition: 10
      widget: select
      relation: version

  - id: created_at
    name: 创建时间
    type: datetime
    ui:
      visible: false

  - id: updated_at
    name: 更新时间
    type: datetime
    ui:
      visible: false

views:
  list:
    defaultSort: name
    filters: [version_id]
    pageSize: 20
  detail:
    facets:
      - title: 基本信息
        type: fieldGroup
        qualifier: basic
      - title: 层级归属
        type: fieldGroup
        qualifier: hierarchy
    showChangeHistory: true
  form:
    sections:
      - title: 基本信息
        fields: [name, code]
      - title: 层级归属
        fields: [version_id]

actions:
  - id: crud_create
    name: 创建领域
    type: create
    parameters:
      - id: name
        name: 名称
        type: string
        required: true
      - id: code
        name: 编码
        type: string
      - id: version_id
        name: 版本ID
        type: integer
        required: true

  - id: crud_update
    name: 更新领域
    type: update
    parameters:
      - id: id
        name: ID
        type: integer
        required: true
      - id: name
        name: 名称
        type: string
      - id: code
        name: 编码
        type: string

  - id: crud_delete
    name: 删除领域
    type: delete
    parameters:
      - id: id
        name: ID
        type: integer
        required: true
```

## 架构对比

### 与 Palantir Foundry 对标

| Palantir 概念 | 本设计对应 | 说明 |
|--------------|-----------|------|
| Object Types | MetaObject + fields | 业务实体定义 |
| Link Types | relations | 对象间关系 |
| Action Types | actions + to_tool_schema() | 操作定义，自动转 Tool Schema |
| Functions | functions | 计算函数 |
| Ontology Engine | ViewConfigService + QueryService | 运行时引擎 |
| Agent Tools | Agent API + Tool Schema | AI Agent 接口 |

### 与 SAP S/4HANA 对标

| SAP CDS 概念 | 本设计对应 | 说明 |
|-------------|-----------|------|
| @UI.lineItem | ui.lineItem | 列表列定义 |
| @UI.fieldGroup | ui.fieldGroup | 表单字段分组 |
| @UI.selectionField | views.list.filters | 筛选字段 |
| @UI.facet | views.detail.facets | 详情分区 |
| CDS View + Annotation | YAML Schema + ui/views | 统一定义 |

## 迁移策略

### 阶段一：后端基础设施
1. 扩展 models.py（UIAnnotation、ViewConfig 等）
2. 扩展 yaml_loader.py（解析 ui、views 段）
3. 新增 view_config_service.py
4. 新增 meta_api.py

### 阶段二：Schema 扩展
1. 为所有 YAML Schema 添加 ui 注解
2. 为所有 YAML Schema 添加 views 配置
3. 测试配置生成正确性

### 阶段三：前端动态组件
1. 新增 useViewConfig.js
2. 新增 DynamicTable.vue
3. 新增 DynamicDetail.vue
4. 新增 DynamicForm.vue

### 阶段四：集成迁移
1. 重构 index.vue 使用动态组件
2. 保留旧组件作为 fallback
3. 端到端测试

### 阶段五：Agent API
1. 新增 agent_api.py
2. 实现 Action.to_tool_schema()
3. Agent 集成测试

## 架构动态性设计

### 核心设计理念

本架构的核心目标是**元数据与渲染层解耦**，实现以下动态性：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        运行态元数据架构                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    YAML Schema (单一数据源)                          │   │
│   │                                                                     │   │
│   │  fields + ui + views + actions + validations                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    元数据服务层                                      │   │
│   │                                                                     │   │
│   │  ViewConfigService + AgentContextService + I18nService              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                    ┌───────────────┼───────────────┐                        │
│                    ▼               ▼               ▼                        │
│   ┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────┐          │
│   │   Human UI 渲染      │ │  AI Agent 接口   │ │  未来扩展        │          │
│   │                     │ │                 │ │                 │          │
│   │  Vue DynamicTable   │ │  Tool Schema    │ │  React 组件      │          │
│   │  Vue DynamicDetail  │ │  Context API    │ │  移动端 UI       │          │
│   │  Vue DynamicForm    │ │  Natural Lang   │ │  语音交互        │          │
│   │                     │ │                 │ │  ...            │          │
│   │  可替换为任意框架     │ │  动态生成 UI    │ │                 │          │
│   └─────────────────────┘ └─────────────────┘ └─────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 动态性支持

| 动态性维度 | 实现方式 | 说明 |
|-----------|---------|------|
| **前端框架可替换** | 元数据 → JSON API → 任意前端框架 | Vue → React → 移动端 → 桌面端 |
| **Agent 动态生成 UI** | 元数据 → Tool Schema → Agent 生成 UI | Agent 可基于上下文动态构建界面 |
| **多视图配置** | 同一对象多套 views 配置 | 不同角色/场景看到不同视图 |
| **多语言支持** | i18n key + I18nService | UI 标题支持多语言 |
| **权限控制** | 字段级权限注解（预留） | 控制字段可见性/可编辑性 |

### 前端框架无关性

```javascript
// Vue 实现
<DynamicTable :config="viewConfig.listView" :data="tableData" />

// React 实现（未来）
<DynamicTable config={viewConfig.listView} data={tableData} />

// 移动端实现（未来）
<MobileList config={viewConfig.listView} data={tableData} />

// Agent 生成的 UI（未来）
// Agent 基于 viewConfig 动态生成自然语言描述或 Markdown 表格
```

### Agent 动态 UI 生成示例

```python
# Agent 可基于元数据动态生成 UI 描述
def generate_ui_description(view_config, data):
    """Agent 生成 UI 的自然语言描述"""
    columns = view_config['listView']['columns']
    description = f"列表包含以下字段：{', '.join([c['title'] for c in columns])}"
    return description

# 或生成 Markdown 表格
def generate_markdown_table(view_config, data):
    columns = [c['key'] for c in view_config['listView']['columns']]
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for row in data:
        rows.append("| " + " | ".join([str(row.get(c, "")) for c in columns]) + " |")
    return "\n".join([header, separator] + rows)
```

## TBD List

| ID | Item | 决策 | 说明 |
|----|------|------|------|
| TBD-1 | 权限控制 | ✅ 需要 | 字段级权限控制，先预留接口，后续实现 |
| TBD-2 | 多视图支持 | ✅ 需要 | 同一对象支持多套视图配置（按角色/场景） |
| TBD-3 | 自定义组件 | ❌ 不需要 | 使用标准动态组件即可 |
| TBD-4 | 国际化 | ✅ 需要 | 架构上支持多语言，UI 标题使用 i18n key |
| TBD-5 | AI Agent | ✅ 需要 | 先预留接口，后续实现完整 Agent 集成 |

Spec contains 10 sections, last section is "TBD List", content is complete.
