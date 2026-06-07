# 业务关系管理与视图类型扩展 Spec

## Why

当前架构数据管理模块已实现基础的 CRUD 功能，但存在以下问题：

1. **业务关系维护入口缺失**：业务关系(relationship)是跨对象的关联，无法通过现有层级树导航访问
2. **业务对象详情缺少关联关系展示**：用户查看业务对象时无法看到其作为源/目标的关系
3. **筛选器配置未模型化**：筛选逻辑硬编码在前端，无法通过元数据配置
4. **视图类型不完整**：缺少 filter、relation 等视图类型配置

## What Changes

- **新增视图类型**：扩展 `ui_view_config` 支持 `filter` 和 `relation` 视图类型
- **业务对象详情增强**：在详情页展示关联关系（作为源/目标）
- **业务关系独立管理入口**：通过顶部 Tab 切换"层级数据"和"业务关系"
- **筛选器配置模型化**：通过 YAML 定义筛选器字段、默认值、顺序
- **关系分类筛选**：复用 `relationClassifier.js` 的分类逻辑

## Impact

- Affected specs: architecture-data-management, unified-meta-model-design
- Affected code:
  - `meta/schemas/relationship.yaml` - 关系元模型完善
  - `meta/schemas/business_object.yaml` - 业务对象元模型扩展
  - `meta/api/meta_api.py` - 视图配置 API 扩展
  - `meta/api/manage_api.py` - 关系查询 API
  - `src/views/ArchDataManageApp/index.vue` - 主框架 Tab 切换
  - `src/views/ArchDataManageApp/components/DynamicDetail.vue` - 关联关系展示
  - `src/views/ArchDataManageApp/components/DynamicFilter.vue` - 筛选器组件（新增）
  - `src/views/ArchDataManageApp/composables/useFilter.js` - 筛选逻辑（新增）

## ADDED Requirements

### Requirement: 视图配置扩展 - Filter 视图类型

系统 SHALL 在 `ui_view_config` 中支持 `filter` 视图类型配置：

```yaml
ui_view_config:
  filter:
    filters:
      - key: business_object
        title: 业务对象
        type: multi_select      # multi_select | checkbox_group | select | text
        source: business_object # 关联对象类型
        display_field: name     # 显示字段
        position: 1
        default: all            # all | none | specific values
      
      - key: category_type
        title: 分类维度
        type: checkbox_group
        options:
          - value: cross_domain
            label: 跨领域
          - value: same_domain
            label: 同领域
        position: 2
        default: all
```

#### Scenario: 筛选器配置解析
- **WHEN** API 返回包含 `filter` 配置的视图元数据
- **THEN** 前端根据配置动态渲染筛选器组件

#### Scenario: 默认值处理
- **WHEN** 筛选器配置 `default: all`
- **THEN** 该筛选项默认全选所有选项

### Requirement: 视图配置扩展 - Relation 视图类型

系统 SHALL 在 `ui_view_config.detail` 中支持 `relation_list` 分面类型：

```yaml
ui_view_config:
  detail:
    facets:
      - title: 关联关系
        type: relation_list
        source: relationship
        source_field: source_bo_id
        target_field: target_bo_id
        display_mode: split    # split | combined
        max_display: 5
        fields:
          source: [relation_code, target_bo_name]
          target: [relation_code, source_bo_name]
```

#### Scenario: 关联关系展示
- **WHEN** 用户查看业务对象详情
- **THEN** 详情页显示该对象作为源和目标的所有关系

#### Scenario: 关系列表跳转
- **WHEN** 用户点击关系列表中的"查看全部"
- **THEN** 跳转到业务关系页面并预填充筛选条件

### Requirement: 业务关系筛选器设计

系统 SHALL 提供按以下顺序的筛选器：

1. **业务对象** - 多选，选择后显示相关关系统计
2. **分类维度** - 复选框组，默认全选
3. **关系类型** - 复选框组，默认全选

筛选器布局：

```
┌─────────────────────────────────┐
│ 业务关系管理                    │
│ 版本: [供应链云平台 - v1.0 ▼]  │
├─────────────────────────────────┤
│ ── 业务对象 ──                  │
│  [搜索业务对象...]              │
│  ├ ☑ 供应商 (12)               │
│  ├ ☑ 采购订单 (8)              │
│  └ ☐ 仓库 (5)                  │
│  [全选] [清空]                  │
├─────────────────────────────────┤
│ ── 分类维度 ── (默认全选)       │
│  ├ ☑ 跨领域 (45)               │
│  ├ ☑ 同领域跨子领域 (67)        │
│  └ ☑ 同服务模块 (21)            │
├─────────────────────────────────┤
│ ── 关系类型 ── (默认全选)       │
│  ├ ☑ 调用 (CALLS) (45)         │
│  ├ ☑ 依赖 (DEPENDS_ON) (67)    │
│  └ ☑ 数据流 (DATA_FLOW) (23)   │
├─────────────────────────────────┤
│ 关系统计: 156                   │
│ [应用筛选] [重置]               │
└─────────────────────────────────┘
```

#### Scenario: 筛选器联动
- **WHEN** 用户选择业务对象"供应商"
- **THEN** 分类维度和关系类型的统计数字更新为该对象相关的关系数量

#### Scenario: 筛选结果
- **WHEN** 用户点击"应用筛选"
- **THEN** 列表仅显示符合所有筛选条件的关系

### Requirement: 主框架 Tab 切换

系统 SHALL 在架构数据管理主界面提供顶部 Tab 切换：

```
┌─────────────────────────────────────────────────────────────────────┐
│ Header                                                                │
├─────────────────────────────────────────────────────────────────────┤
│  [层级数据]  [业务关系]    ← 顶部主 Tab                              │
├──────────────┬──────────────────────────────────────────────────────┤
│              │                                                      │
│  左侧导航    │  右侧内容区                                          │
│  (根据Tab变化)│  (列表/详情/表单)                                   │
└──────────────┴──────────────────────────────────────────────────────┘
```

#### Scenario: 层级数据 Tab
- **WHEN** 用户选择"层级数据" Tab
- **THEN** 左侧显示层级树导航，右侧显示选中对象类型的列表

#### Scenario: 业务关系 Tab
- **WHEN** 用户选择"业务关系" Tab
- **THEN** 左侧显示筛选器，右侧显示关系列表

### Requirement: 业务对象详情关联关系展示

系统 SHALL 在业务对象详情页显示关联关系区块：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 业务对象详情                                                         │
├─────────────────────────────────────────────────────────────────────┤
│  ...基本信息...                                                      │
│                                                                     │
│  关联关系 (15)                                      [查看全部 ▼]    │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ 作为源的关系 (8)                    作为目标的关系 (7)           ││
│  ├────────────────────────────┬────────────────────────────────────┤│
│  │ CALLS → 采购订单           │ DEPENDS_ON ← 采购申请              ││
│  │ CALLS → 采购合同           │ DATA_FLOW ← 供应商评估             ││
│  │ ...                        │ ...                                ││
│  └────────────────────────────┴────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

#### Scenario: 关联关系加载
- **WHEN** 用户打开业务对象详情页
- **THEN** 系统自动加载该对象作为源和目标的关系列表

#### Scenario: 关系数量显示
- **WHEN** 关联关系区块显示
- **THEN** 显示作为源和目标的关系数量统计

### Requirement: 关系分类计算

系统 SHALL 复用 `relationClassifier.js` 的分类逻辑，为每条关系计算分类：

- **跨领域**：源和目标业务对象属于不同领域
- **同领域跨子领域**：同领域，不同子领域
- **同子领域跨服务模块**：同子领域，不同服务模块
- **同服务模块**：同一服务模块

#### Scenario: 关系分类计算
- **WHEN** 关系数据加载
- **THEN** 系统根据源和目标业务对象的层级归属计算分类

### Requirement: 关系列表视图

系统 SHALL 为业务关系提供列表视图，显示以下列：

| 列名 | 字段 | 说明 |
|-----|------|------|
| 源业务对象 | source_bo_name | 源业务对象名称 |
| 目标业务对象 | target_bo_name | 目标业务对象名称 |
| 关系类型 | relation_code | CALLS/DEPENDS_ON/DATA_FLOW |
| 分类维度 | category_label | 跨领域/同领域等 |
| 描述 | relation_desc | 关系描述 |
| 创建时间 | created_at | 创建时间 |

#### Scenario: 关系列表渲染
- **WHEN** 用户进入业务关系页面
- **THEN** 显示关系列表，支持排序和分页

#### Scenario: 关系编辑
- **WHEN** 用户点击关系的"编辑"按钮
- **THEN** 打开关系编辑表单

## MODIFIED Requirements

### Requirement: relationship.yaml 元模型完善

`relationship.yaml` SHALL 扩展以下配置：

```yaml
ui_view_config:
  list:
    columns:
      - key: source_bo_name
        title: 源业务对象
        width: 150
        position: 1
      - key: target_bo_name
        title: 目标业务对象
        width: 150
        position: 2
      - key: relation_code
        title: 关系类型
        width: 120
        position: 3
      - key: category_label
        title: 分类维度
        width: 150
        position: 4
      - key: relation_desc
        title: 描述
        width: 200
        position: 5
    defaultSort: created_at
    pageSize: 20

  detail:
    facets:
      - title: 基本信息
        type: fieldGroup
        fields:
          - source_bo_name
          - target_bo_name
          - relation_code
          - relation_desc
      - title: 分类信息
        type: fieldGroup
        fields:
          - category_type
          - scope_type

  form:
    sections:
      - title: 基本信息
        fields:
          - version_id
          - source_bo_id
          - relation_code
          - target_bo_id
          - relation_desc

  filter:
    filters:
      - key: business_object
        title: 业务对象
        type: multi_select
        source: business_object
        display_field: name
        position: 1
        default: all
      
      - key: category_type
        title: 分类维度
        type: checkbox_group
        options:
          - value: cross_domain
            label: 跨领域
          - value: same_domain_cross_subdomain
            label: 同领域跨子领域
          - value: same_subdomain_cross_module
            label: 同子领域跨服务模块
          - value: same_module
            label: 同服务模块
        position: 2
        default: all
      
      - key: relation_code
        title: 关系类型
        type: checkbox_group
        options:
          - value: CALLS
            label: 调用
          - value: DEPENDS_ON
            label: 依赖
          - value: DATA_FLOW
            label: 数据流
          - value: INCLUDE
            label: 包含
        position: 3
        default: all
      
      - key: version_id
        title: 版本
        type: select
        source: version
        display_field: name
        position: 0
        required: true
```

### Requirement: business_object.yaml 元模型扩展

`business_object.yaml` SHALL 在 `ui_view_config.detail` 中添加关联关系分面：

```yaml
ui_view_config:
  detail:
    facets:
      - title: 基本信息
        type: fieldGroup
        fields:
          - code
          - name
          - bo_type
          - description
      
      - title: 关联关系
        type: relation_list
        source: relationship
        source_field: source_bo_id
        target_field: target_bo_id
        display_mode: split
        max_display: 5
        fields:
          source: [relation_code, target_bo_name]
          target: [relation_code, source_bo_name]
        position: 3
      
      - title: 归属信息
        type: fieldGroup
        fields:
          - version_name
          - domain_name
          - sub_domain_name
          - service_module_name
```

## REMOVED Requirements

无移除的需求。所有现有功能保持向后兼容。

## ADDED Requirements (补充)

### Requirement: 层级对象关系数量统计列

系统 SHALL 在领域、子领域、服务模块、业务对象的列表中显示关系数量统计列：

| 对象类型 | 统计列名 | 统计逻辑 |
|---------|---------|---------|
| 领域 (domain) | relation_count | 该领域下所有业务对象参与的关系总数 |
| 子领域 (sub_domain) | relation_count | 该子领域下所有业务对象参与的关系总数 |
| 服务模块 (service_module) | relation_count | 该服务模块下所有业务对象参与的关系总数 |
| 业务对象 (business_object) | relation_count | 该业务对象作为源或目标的关系总数 |

#### 统计规则定义

```yaml
# 在各对象的 ui_view_config.list.columns 中添加
- key: relation_count
  title: 关系数量
  width: 100
  position: 90
  computed: true           # 标记为计算字段
  computation:
    type: count_relations  # 统计规则类型
    scope: descendants     # descendants=包含下级 | self=仅自身
```

#### Scenario: 领域关系数量统计
- **WHEN** 用户查看领域列表
- **THEN** 每个领域显示其下所有业务对象参与的关系总数

#### Scenario: 业务对象关系数量统计
- **WHEN** 用户查看业务对象列表
- **THEN** 每个业务对象显示其作为源或目标的关系总数

#### Scenario: 关系数量点击跳转
- **WHEN** 用户点击关系数量
- **THEN** 跳转到业务关系页面并预填充筛选条件

### Requirement: 统计规则计算服务

系统 SHALL 提供统计规则计算服务，支持在查询时动态计算统计字段：

```python
@dataclass
class ComputationRule:
    type: str              # count_relations | count_children | aggregate
    scope: str             # descendants | self | related
    relation_type: str = None  # 可选，筛选特定关系类型
```

#### Scenario: 统计字段计算
- **WHEN** 列表查询包含 computed 字段
- **THEN** 系统根据 computation 规则计算字段值

#### Scenario: 统计字段缓存
- **WHEN** 关系数据变更
- **THEN** 相关的统计字段缓存失效

## API 设计

### 关系列表 API

```
GET /api/v1/relationships
Parameters:
  - version_id: int              # 必填，版本ID
  - business_objects: int[]      # 业务对象ID数组
  - category_types: string[]     # 分类类型数组
  - relation_codes: string[]     # 关系类型数组
  - page: int
  - pageSize: int

Response:
  data: Relationship[]
  total: int
  stats: {
    total: int
    by_category: { [key]: int }
    by_type: { [key]: int }
  }
```

### 业务对象关联关系 API

```
GET /api/v1/business_object/{id}/relations
Parameters:
  - display_mode: 'all' | 'source_only' | 'target_only'
  - category_types: string[]
  - relation_codes: string[]

Response:
  source_relations: Relation[]
  target_relations: Relation[]
  stats: {
    total: int
    by_category: { [key]: int }
    by_type: { [key]: int }
  }
```

### 筛选器配置 API

```
GET /api/v1/meta/{object_type}/filter-config
Response:
  filters: FilterDefinition[]
```
