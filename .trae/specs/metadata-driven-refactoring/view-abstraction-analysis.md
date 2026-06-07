# 架构数据管理 UI/Export 分析与 View 抽象建议

> 分析当前架构数据管理功能，识别可抽象为 Analytics View 或普通 View 的场景

---

## 一、当前功能概览

### 1.1 UI 功能清单

| 功能 | 组件 | 当前实现 | 数据来源 |
|------|------|----------|----------|
| 对象列表 | `DynamicView.vue` | 基于 `ui_view_config` 动态渲染 | Entity 直接查询 |
| 关系列表 | `DynamicView.vue` | 基于 `ui_view_config` 动态渲染 | relationship 表 |
| 树形筛选器 | `UnifiedScopePanel.vue` | 基于 `hierarchies.yaml` 构建 | 多表关联 |
| 关系统计 | `RelationFacet.vue` | 直接 API 调用 | `/business_object/{id}/relations` |
| 导出功能 | `ExportDialog.vue` | 直接 API 调用 | `/api/v1/export` |
| 详情面板 | `DynamicView.vue` | 基于 `ui_view_config.detail` | Entity 直接查询 |

### 1.2 当前架构问题

```
┌─────────────────────────────────────────────────────────────────────┐
│                        当前实现方式                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   前端组件                      后端 API                             │
│   ┌─────────────┐              ┌─────────────┐                      │
│   │DynamicView  │──────────────│ /api/v1/xxx │──► Entity 表         │
│   └─────────────┘              └─────────────┘                      │
│                                                                      │
│   ┌─────────────┐              ┌─────────────┐                      │
│   │RelationFacet│──────────────│ /relations  │──► 关联查询（代码）   │
│   └─────────────┘              └─────────────┘                      │
│                                                                      │
│   ┌─────────────┐              ┌─────────────┐                      │
│   │ExportDialog │──────────────│ /export     │──► 导出逻辑（代码）   │
│   └─────────────┘              └─────────────┘                      │
│                                                                      │
│   问题：                                                             │
│   1. 关联查询逻辑硬编码在代码中                                        │
│   2. 导出列定义分散在多处                                             │
│   3. 统计查询无法复用                                                 │
│   4. 缺少声明式的视图定义                                             │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、可抽象为 View 的场景分析

### 2.1 Analytics View 候选

#### 场景 1: 关系统计视图

**当前实现**:
```javascript
// RelationFacet.vue
const response = await fetch(`${API_BASE}/business_object/${props.objectId}/relations`)
// 后端代码中硬编码关联查询
```

**建议抽象为**:
```yaml
# schemas/views/bo_relation_stats.yaml

id: bo_relation_stats
name: 业务对象关系统计
object_type: view

analytics:
  data_category: cube
  query_enabled: true
  measures:
    - source_relation_count   # 作为源的关系数
    - target_relation_count   # 作为目标的关系数
    - total_relation_count    # 总关系数
  dimensions:
    - bo_id
    - bo_code
    - bo_name

view_config:
  sources:
    - object: business_object
      alias: bo
    - object: relationship
      alias: r_src
    - object: relationship
      alias: r_tgt
  
  joins:
    - type: left
      source: bo
      target: r_src
      condition: "bo.id = r_src.source_bo_id"
    - type: left
      source: bo
      target: r_tgt
      condition: "bo.id = r_tgt.target_bo_id"
  
  group_by:
    - bo.id
    - bo.code
    - bo.name
  
  aggregates:
    - field: source_relation_count
      function: COUNT
      source_field: "r_src.id"
    - field: target_relation_count
      function: COUNT
      source_field: "r_tgt.id"
    - field: total_relation_count
      function: COUNT
      source_field: "COALESCE(r_src.id, r_tgt.id)"

ui_view_config:
  list:
    columns:
      - key: bo_code
        title: 对象编码
      - key: bo_name
        title: 对象名称
      - key: source_relation_count
        title: 作为源
      - key: target_relation_count
        title: 作为目标
      - key: total_relation_count
        title: 总计
```

**收益**:
- 统计逻辑声明式定义，易于维护
- 可复用于导出、报表等场景
- 支持多维度聚合（按领域、按类型等）

---

#### 场景 2: 领域关系统计视图

**当前实现**: 前端 `useRelationScopeTree.js` 中计算

**建议抽象为**:
```yaml
# schemas/views/domain_relation_stats.yaml

id: domain_relation_stats
name: 领域关系统计
object_type: view

analytics:
  data_category: cube
  measures:
    - internal_relation_count   # 内部关系
    - external_relation_count   # 外部关系
    - total_relation_count
  dimensions:
    - domain_id
    - domain_name
    - relation_code

view_config:
  sources:
    - object: relationship
      alias: r
    - object: business_object
      alias: src_bo
    - object: business_object
      alias: tgt_bo
    - object: domain
      alias: src_d
    - object: domain
      alias: tgt_d
  
  joins:
    - type: left
      source: r
      target: src_bo
      condition: "r.source_bo_id = src_bo.id"
    - type: left
      source: r
      target: tgt_bo
      condition: "r.target_bo_id = tgt_bo.id"
    - type: left
      source: src_bo
      target: src_d
      condition: "src_bo.domain_id = src_d.id"
    - type: left
      source: tgt_bo
      target: tgt_d
      condition: "tgt_bo.domain_id = tgt_d.id"
  
  group_by:
    - src_d.id
    - src_d.name
    - r.relation_code
  
  aggregates:
    - field: internal_relation_count
      function: COUNT
      source_field: "CASE WHEN src_d.id = tgt_d.id THEN r.id END"
    - field: external_relation_count
      function: COUNT
      source_field: "CASE WHEN src_d.id != tgt_d.id THEN r.id END"
    - field: total_relation_count
      function: COUNT
      source_field: "r.id"
```

---

#### 场景 3: 关系类型分布视图

**建议抽象为**:
```yaml
# schemas/views/relation_type_distribution.yaml

id: relation_type_distribution
name: 关系类型分布
object_type: view

analytics:
  data_category: cube
  measures:
    - relation_count
  dimensions:
    - relation_code
    - domain_id
    - scope_category  # cross_domain / same_domain / same_module

view_config:
  sources:
    - object: relationship
      alias: r
    - object: business_object
      alias: src_bo
    - object: business_object
      alias: tgt_bo
  
  joins:
    - type: left
      source: r
      target: src_bo
      condition: "r.source_bo_id = src_bo.id"
    - type: left
      source: r
      target: tgt_bo
      condition: "r.target_bo_id = tgt_bo.id"
  
  group_by:
    - r.relation_code
    - src_bo.domain_id
    - "CASE 
        WHEN src_bo.domain_id != tgt_bo.domain_id THEN 'cross_domain'
        WHEN src_bo.sub_domain_id != tgt_bo.sub_domain_id THEN 'same_domain_cross_subdomain'
        WHEN src_bo.service_module_id != tgt_bo.service_module_id THEN 'same_subdomain_cross_module'
        ELSE 'same_module'
      END AS scope_category"
  
  aggregates:
    - field: relation_count
      function: COUNT
      source_field: "r.id"
```

---

### 2.2 普通 View 候选

#### 场景 4: 业务对象详情视图

**当前实现**: Entity 直接查询 + 前端拼接

**建议抽象为**:
```yaml
# schemas/views/business_object_detail.yaml

id: business_object_detail
name: 业务对象详情视图
object_type: view

view_config:
  sources:
    - object: business_object
      alias: bo
    - object: service_module
      alias: sm
    - object: sub_domain
      alias: sd
    - object: domain
      alias: d
    - object: version
      alias: v
  
  joins:
    - type: left
      source: bo
      target: sm
      condition: "bo.service_module_id = sm.id"
    - type: left
      source: sm
      target: sd
      condition: "sm.sub_domain_id = sd.id"
    - type: left
      source: sd
      target: d
      condition: "sd.domain_id = d.id"
    - type: left
      source: bo
      target: v
      condition: "bo.version_id = v.id"

ui_view_config:
  list:
    columns:
      - key: code
        title: 编码
      - key: name
        title: 名称
      - key: service_module_name
        title: 服务模块
      - key: sub_domain_name
        title: 子领域
      - key: domain_name
        title: 领域
      - key: version_name
        title: 版本
```

**收益**:
- 一次查询获取所有关联信息
- 减少前端多次 API 调用
- 导出时直接使用视图定义

---

#### 场景 5: 关系详情视图

**当前实现**: Entity 直接查询

**建议抽象为**:
```yaml
# schemas/views/relationship_detail.yaml

id: relationship_detail
name: 关系详情视图
object_type: view

view_config:
  sources:
    - object: relationship
      alias: r
    - object: business_object
      alias: src_bo
    - object: business_object
      alias: tgt_bo
    - object: service_module
      alias: src_sm
    - object: service_module
      alias: tgt_sm
    - object: sub_domain
      alias: src_sd
    - object: sub_domain
      alias: tgt_sd
    - object: domain
      alias: src_d
    - object: domain
      alias: tgt_d
  
  joins:
    # 源端关联
    - type: left
      source: r
      target: src_bo
      condition: "r.source_bo_id = src_bo.id"
    - type: left
      source: src_bo
      target: src_sm
      condition: "src_bo.service_module_id = src_sm.id"
    - type: left
      source: src_sm
      target: src_sd
      condition: "src_sm.sub_domain_id = src_sd.id"
    - type: left
      source: src_sd
      target: src_d
      condition: "src_sd.domain_id = src_d.id"
    # 目标端关联
    - type: left
      source: r
      target: tgt_bo
      condition: "r.target_bo_id = tgt_bo.id"
    - type: left
      source: tgt_bo
      target: tgt_sm
      condition: "tgt_bo.service_module_id = tgt_sm.id"
    - type: left
      source: tgt_sm
      target: tgt_sd
      condition: "tgt_sm.sub_domain_id = tgt_sd.id"
    - type: left
      source: tgt_sd
      target: tgt_d
      condition: "tgt_sd.domain_id = tgt_d.id"

ui_view_config:
  list:
    columns:
      - key: source_code
        title: 源编码
      - key: source_bo_name
        title: 源对象
      - key: source_domain_name
        title: 源领域
      - key: relation_code
        title: 关系类型
      - key: target_code
        title: 目标编码
      - key: target_bo_name
        title: 目标对象
      - key: target_domain_name
        title: 目标领域
      - key: category_label
        title: 关系范围
```

---

### 2.3 Export View 候选

#### 场景 6: 导出配置视图

**当前实现**: 导出选项硬编码在 `ExportDialog.vue` 中

**建议抽象为**:
```yaml
# schemas/export_configs/relationship_export.yaml

id: relationship_export
name: 关系导出配置
target_object: relationship

export_config:
  # 导出列定义
  columns:
    - field: source_code
      title: 源编码
      width: 120
      style: business_key
      
    - field: source_bo_name
      title: 源对象
      width: 150
      
    - field: source_domain_name
      title: 源领域
      width: 100
      
    - field: relation_code
      title: 关系类型
      width: 100
      
    - field: target_code
      title: 目标编码
      width: 120
      style: business_key
      
    - field: target_bo_name
      title: 目标对象
      width: 150
      
    - field: target_domain_name
      title: 目标领域
      width: 100
      
    - field: relation_desc
      title: 描述
      width: 200
  
  # 导出选项
  options:
    include_hierarchy_path: true
    include_hierarchy_ids: true
    include_operation_mode: true
    protect_sheet: false
    include_readonly: true
  
  # 样式配置
  styles:
    business_key:
      background: "#E6F7FF"
      font:
        bold: true
    readonly:
      background: "#F5F5F5"
    parent_key:
      background: "#FFF7E6"
```

---

## 三、重构建议

### 3.1 目标架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        目标架构                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    YAML View 定义                            │   │
│   │  schemas/views/                                              │   │
│   │  ├── bo_relation_stats.yaml      # Analytics View            │   │
│   │  ├── domain_relation_stats.yaml  # Analytics View            │   │
│   │  ├── business_object_detail.yaml # 普通 View                 │   │
│   │  └── relationship_detail.yaml    # 普通 View                 │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    View Registry                             │   │
│   │  meta/core/view_registry.py                                  │   │
│   │  - 加载 View 定义                                            │   │
│   │  - 缓存 View 配置                                            │   │
│   │  - 提供 View 查询 API                                        │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│            ┌─────────────────┼─────────────────┐                    │
│            ▼                 ▼                 ▼                    │
│   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐            │
│   │ Query Service │ │ Export Service│ │ UI Service    │            │
│   │               │ │               │ │               │            │
│   │ 执行 View 查询 │ │ 基于 View 导出 │ │ 返回 View 配置│            │
│   └───────────────┘ └───────────────┘ └───────────────┘            │
│            │                 │                 │                    │
│            └─────────────────┼─────────────────┘                    │
│                              ▼                                       │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    前端组件                                   │   │
│   │  DynamicView.vue     - 基于 View 配置渲染                    │   │
│   │  RelationFacet.vue   - 使用 Analytics View                   │   │
│   │  ExportDialog.vue    - 使用 Export View                      │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 实施优先级

| 优先级 | 场景 | 类型 | 收益 | 工作量 |
|--------|------|------|------|--------|
| **P1** | 关系详情视图 | 普通 View | 导出/列表复用 | 1天 |
| **P1** | 业务对象详情视图 | 普通 View | 导出/列表复用 | 1天 |
| **P2** | 关系统计视图 | Analytics View | 统计复用 | 2天 |
| **P2** | 领域关系统计视图 | Analytics View | 树形筛选器优化 | 2天 |
| **P3** | 导出配置视图 | Export View | 导出标准化 | 1天 |
| **P3** | 关系类型分布视图 | Analytics View | 报表支持 | 1天 |

### 3.3 API 设计

```python
# 新增 API 端点

# 1. 查询 View 数据
GET /api/v1/views/{view_id}?filters=...&group_by=...

# 2. 获取 View 配置
GET /api/v1/views/{view_id}/config

# 3. 基于 View 导出
POST /api/v1/views/{view_id}/export

# 4. 获取 Analytics 数据
GET /api/v1/analytics/{view_id}?measures=...&dimensions=...
```

---

## 四、总结

### 4.1 当前状态

| 功能 | 是否使用 View | 说明 |
|------|--------------|------|
| 对象列表 | ⚠️ 部分 | 使用 `ui_view_config`，但无数据层 View |
| 关系列表 | ⚠️ 部分 | 同上 |
| 关系统计 | ❌ 否 | 直接 API 调用，逻辑硬编码 |
| 导出 | ❌ 否 | 导出逻辑在代码中 |
| 树形筛选 | ⚠️ 部分 | 使用 `hierarchies.yaml`，但统计在代码中 |

### 4.2 改进方向

1. **数据层 View** - 将关联查询抽象为 View 定义
2. **Analytics View** - 将统计查询抽象为 Analytics View
3. **Export View** - 将导出配置抽象为 View 定义
4. **前端统一消费** - 前端通过 View API 获取数据和配置

### 4.3 预期收益

1. **代码简化** - 关联查询逻辑从代码移到配置
2. **复用性提高** - 同一 View 可用于列表、导出、报表
3. **维护性提升** - 修改查询只需改配置文件
4. **性能优化** - View 可缓存，减少重复查询
