# 元数据驱动架构重构方案

> 基于 SAP One Model 和 Analytics Query View 最佳实践
> 
> **创建日期**: 2026-04-25

---

## 一、背景与目标

### 1.1 问题背景

在之前的开发中，遇到了以下数据不一致问题：

1. **前端树选择数量与列表显示不匹配** - 选择领域后，关系树显示的数量与关系列表不一致
2. **层级过滤逻辑分散** - 前端 `hierarchyFilterBuilder.js` 和后端 `hierarchy_filter_service.py` 各自独立实现
3. **硬编码的层级链** - `domain → sub_domain → service_module → business_object` 散落在多处代码中
4. **导出过滤条件不一致** - 导出时未能正确应用前端选择的过滤条件

### 1.2 SAP One Model 核心理念

SAP S/4HANA 的 **CDS View + Analytics Query** 架构提供了成熟的解决方案：

```
┌─────────────────────────────────────────────────────────────┐
│                    元数据层 (Metadata Layer)                 │
│  CDS View 定义：字段、关联、注解、聚合规则                      │
│  @Analytics.dataCategory: #CUBE / #DIMENSION               │
│  @ObjectModel.readOnly, @mandatory, @immutable             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 单一数据源
┌─────────────────────────────────────────────────────────────┐
│                    服务层 (Service Layer)                    │
│  SADL 框架：自动生成 OData Service                           │
│  统一的查询、过滤、分页逻辑                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ 统一 API
┌─────────────────────────────────────────────────────────────┐
│                    展现层 (Presentation Layer)               │
│  Fiori Elements：自动生成 UI 组件                            │
│  列表、表单、过滤器从元数据动态生成                            │
└─────────────────────────────────────────────────────────────┘
```

**核心原则**：
1. **元数据即代码** - 所有业务语义在元数据中定义
2. **单一数据源** - 前后端统一消费同一份元数据
3. **声明式开发** - 描述"是什么"而非"怎么做"
4. **Code-to-Data** - 计算下推到数据库层

### 1.3 目标

1. **消除数据不一致** - 前后端使用统一的过滤逻辑
2. **提高可维护性** - 层级关系集中配置，易于修改
3. **支持扩展** - 为未来的分析查询、聚合视图奠定基础
4. **对齐 SAP 最佳实践** - 借鉴成熟的元数据驱动架构

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    YAML 元模型定义                           │
│  ├── schemas/hierarchies.yaml    # 层级结构定义              │
│  ├── schemas/business_object.yaml # 业务对象定义             │
│  ├── schemas/relationship.yaml   # 关系定义                  │
│  └── schemas/*.yaml              # 其他对象定义              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ YAML Loader
┌─────────────────────────────────────────────────────────────┐
│                    Python 元模型注册表                        │
│  meta/core/models.py                                         │
│  ├── MetaRegistry (单例)                                     │
│  ├── MetaObject (对象定义)                                   │
│  ├── MetaField (字段定义)                                    │
│  ├── MetaRelation (关联定义)                                 │
│  └── SemanticAnnotation (语义注解)                           │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  过滤服务          │ │  导入导出服务      │ │  视图配置服务      │
│  hierarchy_filter │ │  import_export    │ │  view_config      │
│  _service.py      │ │  _service.py      │ │  _service.py      │
└───────────────────┘ └───────────────────┘ └───────────────────┘
            │                 │                 │
            └─────────────────┼─────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    REST API 层                               │
│  /api/v1/meta/hierarchies      # 获取层级配置                │
│  /api/v1/meta/objects/{type}   # 获取对象元数据              │
│  /api/v1/relationships         # 关系查询（支持层级过滤）      │
│  /api/v1/export                # 导出（支持层级过滤）         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    前端消费层                                 │
│  ├── stores/archDataStore.js    # 状态管理                   │
│  ├── composables/useRelationScopeTree.js  # 关系树           │
│  └── components/               # UI 组件                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 元数据流向

```
┌──────────────────────────────────────────────────────────────────┐
│                      hierarchies.yaml                            │
│  hierarchies:                                                    │
│    - id: biz_hierarchy                                          │
│      levels:                                                     │
│        - object: domain                                          │
│          parent_object: version                                  │
│          foreign_key_field: version_id                           │
│        - object: sub_domain                                      │
│          parent_object: domain                                   │
│          foreign_key_field: domain_id                            │
│        ...                                                       │
└──────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  后端过滤服务      │ │  前端树构建        │ │  导出服务          │
│                   │ │                   │ │                   │
│  build_child_chain│ │  buildTreeFrom    │ │  _resolve_hierarchy│
│  (domain→bo)      │ │  HierarchiesYaml  │ │  _filters         │
│                   │ │                   │ │                   │
│  输入: domain_id  │ │  输入: version_id │ │  输入: domain_id   │
│  输出: [bo_ids]   │ │  输出: 树结构      │ │  输出: 过滤条件    │
└───────────────────┘ └───────────────────┘ └───────────────────┘
```

---

## 三、详细设计

### 3.1 Phase 1: 统一层级过滤服务（已完成部分）

#### 3.1.1 已完成

| 项目 | 状态 | 说明 |
|------|------|------|
| `hierarchies.yaml` 定义 | ✅ 完成 | 层级结构、维度、API映射已定义 |
| `config_driven_hierarchy_filter.py` | ✅ 完成 | 配置驱动的过滤服务 |
| `hierarchy_filter_service.py` 重构 | ✅ 完成 | 使用配置驱动方式 |
| 前端 `useRelationScopeTree.js` | ✅ 完成 | 支持多粒度过滤 |
| 后端 `manage_api.py` | ✅ 完成 | 支持 business_object_id 过滤 |

#### 3.1.2 待完成

| 项目 | 优先级 | 工作量 | 说明 |
|------|--------|--------|------|
| TD-1: 移除硬编码层级链 | P1 | 0.5天 | 确保所有代码都从 `hierarchies.yaml` 读取 |
| TD-2: 前端过滤条件构建统一 | P1 | 0.5天 | 前端只传节点ID，后端负责转换 |
| TD-4: 关系过滤语义统一 | P2 | 1天 | 添加 `scope_mode` 参数 |

### 3.2 Phase 2: 元数据 API 增强

#### 3.2.1 新增 API 端点

```python
# meta/api/meta_api.py

@meta_bp.route('/hierarchies', methods=['GET'])
def get_hierarchies():
    """
    获取层级结构配置
    
    返回:
    {
        "hierarchies": [...],
        "dimensions": [...],
        "hierarchy_scopes": [...]
    }
    """
    pass

@meta_bp.route('/hierarchies/<hierarchy_id>/levels', methods=['GET'])
def get_hierarchy_levels(hierarchy_id):
    """
    获取指定层级的级别定义
    
    用于前端动态构建树形选择器
    """
    pass

@meta_bp.route('/objects/<object_type>/analytics_config', methods=['GET'])
def get_analytics_config(object_type):
    """
    获取对象的分析配置（借鉴 SAP @Analytics 注解）
    
    返回:
    {
        "data_category": "cube" | "dimension",
        "measures": ["relation_count", ...],
        "dimensions": ["domain_id", "sub_domain_id", ...],
        "default_aggregations": {...}
    }
    """
    pass
```

#### 3.2.2 前端消费元数据 API

```javascript
// stores/archDataStore.js

async fetchHierarchyConfig() {
  const response = await fetch('/api/v1/meta/hierarchies')
  const data = await response.json()
  this.hierarchyConfig = data.hierarchies[0] // biz_hierarchy
  this.dimensions = data.dimensions
  this.hierarchyScopes = data.hierarchy_scopes
}

// 根据元数据动态构建树
buildTreeFromConfig() {
  const levels = this.hierarchyConfig.levels
  // 按层级定义递归构建树
}
```

### 3.3 Phase 2.5: 字段控制属性统一（关键补充）

#### 3.3.1 背景

项目中已实现完整的字段控制属性，借鉴 SAP One Model 的 `@ObjectModel` 注解体系。这些属性对**导入导出**和**表单编辑**有直接影响。

#### 3.3.2 字段控制属性定义

| 属性 | SAP 对应 | 说明 | 新建时 | 编辑时 |
|------|----------|------|--------|--------|
| `business_key` | `@ObjectModel.businessKey` | 业务唯一标识 | 必填+唯一 | 只读 |
| `parent_key` | 层级外键 | 父对象关联键 | 必填 | **可编辑**（允许移动层级） |
| `immutable` | `@Core.Immutable` | 创建后不可变 | 必填+可编辑 | 只读 |
| `readonly_always` | `readOnly: true` | 始终只读 | 只读 | 只读 |
| `mandatory` | `@mandatory` | 业务必填 | 必填 | 必填 |
| `ui.editable` | `@UI.editable` | UI 可编辑控制 | 按设置 | 按设置 |

#### 3.3.3 字段可编辑性判断逻辑

**后端实现** ([import_export_service.py:1689-1728](file:///d:/filework/excel-to-diagram/meta/services/import_export_service.py#L1689-L1728))：

```python
def _is_field_editable(self, field, mode: str = 'edit') -> bool:
    """判断字段是否可编辑（用于导入导出）
    
    参考 SAP CDS View 字段控制逻辑：
    1. 系统字段：始终只读
    2. readonly_always 字段：始终只读（新建+编辑）
    3. virtual 字段：始终只读（除非有 ui.relation，作为搜索帮助）
    4. immutable 字段：编辑时只读
    5. parent_key 字段：可编辑（SAP One Model 允许移动层级）
    6. ui.editable=false：始终只读
    """
    readonly_field_ids = {'id', 'created_at', 'updated_at', 'created_by', 'updated_by'}
    
    if field.id in readonly_field_ids:
        return False
    
    # readonly_always 始终只读
    if getattr(field.semantics, 'readonly_always', False):
        return False
    
    # virtual 字段：如果是计算字段则只读，如果是外键/搜索帮助则可编辑
    if field.storage.value == 'virtual' or getattr(field.semantics, 'virtual', False):
        if hasattr(field, 'ui') and hasattr(field.ui, 'relation') and field.ui.relation:
            pass  # 可编辑
        else:
            return False  # 计算字段，只读
    
    if mode == 'edit':
        if getattr(field.semantics, 'immutable', False):
            return False
        # parent_key 字段可编辑（SAP One Model 允许移动层级）
    
    if hasattr(field, 'ui') and hasattr(field.ui, 'editable') and field.ui.editable is False:
        return False
    
    return True
```

**前端实现** ([DynamicForm.vue:276-326](file:///d:/filework/excel-to-diagram/src/views/ArchDataManageApp/components/DynamicForm.vue#L276-L326))：

```javascript
function isFieldEditable(fieldId) {
  const field = getField(fieldId)
  if (!field) return false
  
  const semantics = field.semantics || {}
  
  // 系统字段始终只读
  const readonlyFieldIds = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']
  if (readonlyFieldIds.includes(fieldId)) {
    return false
  }
  
  // ui.editable 显式设置为 false 时只读
  if (field.ui?.editable === false) {
    return false
  }
  
  // readonly_always 字段：始终只读
  if (semantics.readonly_always) {
    return false
  }
  
  // immutable 字段：编辑时只读
  if (semantics.immutable && props.mode === 'edit') {
    return false
  }
  
  // parent_key 字段：可编辑（SAP One Model 允许移动层级）
  
  // virtual 字段的处理...
  
  return true
}
```

#### 3.3.4 导入导出中的字段控制

**Excel 列样式标记**：

| 列类型 | 背景色 | 说明 |
|--------|--------|------|
| `business_key` | 浅蓝色 | 业务键，新建必填，编辑只读 |
| `parent_key` | 浅黄色 | 父对象键，新建必填，**编辑可改** |
| `editable` | 白色 | 普通可编辑字段 |
| `readonly` | 灰色 | 只读字段 |

**导入验证规则**：

1. `business_key` 字段必填且唯一
2. `parent_key` 对应的父对象必须存在
3. `immutable` 字段编辑时不能修改
4. `mandatory` 字段必填

#### 3.3.5 YAML 配置示例

```yaml
# schemas/business_object.yaml

fields:
  - id: code
    name: 编码
    type: string
    semantics:
      business_key: true      # 业务键
      immutable: true         # 创建后不可变
      pattern: "^[A-Z][A-Z0-9_]*$"
      
  - id: service_module_id
    name: 服务模块
    type: integer
    semantics:
      parent_key: true        # 父对象键
      mandatory: true         # 业务必填
      # 注意：parent_key 可编辑，允许移动层级
    ui:
      widget: select
      relation: service_module
      
  - id: version_id
    name: 版本
    type: integer
    semantics:
      readonly_always: true   # 始终只读
      context_field: true     # 上下文字段
      
  - id: name
    name: 名称
    type: string
    semantics:
      mandatory: true
    ui:
      editable: true          # 可编辑
```

#### 3.3.6 待改进项

| 项目 | 当前状态 | 改进方向 |
|------|----------|----------|
| 前后端一致性 | ✅ 已统一 | 保持同步 |
| 导入时 parent_key 验证 | ✅ 已实现 | 增强错误提示 |
| context_field 处理 | ⚠️ 部分实现 | 完善导入时自动填充 |
| 字段控制 API | ❌ 未实现 | 提供前端查询接口 |

---

### 3.4 Phase 3: Analytics Query 支持

#### 3.4.1 扩展 ViewConfig

```python
# meta/core/models.py

@dataclass
class AnalyticsConfig:
    """分析配置（借鉴 SAP @Analytics 注解）"""
    data_category: str = ""           # cube | dimension
    query_enabled: bool = False       # 是否作为分析查询
    default_aggregation: str = ""     # SUM | COUNT | AVG | MAX | MIN
    measures: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)

@dataclass
class ViewConfig:
    """视图配置"""
    sources: List[ViewSource] = field(default_factory=list)
    joins: List[ViewJoin] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    aggregates: List[ViewAggregate] = field(default_factory=list)
    # 新增
    analytics: Optional[AnalyticsConfig] = None
```

#### 3.3.2 YAML 定义示例

```yaml
# schemas/relationship_analytics.yaml

id: relationship_analytics
name: 关系分析视图
object_type: view

analytics:
  data_category: cube
  query_enabled: true
  measures:
    - relation_count
  dimensions:
    - domain_id
    - sub_domain_id
    - service_module_id
    - relation_code

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
    - src_bo.domain_id
    - src_bo.sub_domain_id
    - r.relation_code
  
  aggregates:
    - field: relation_count
      function: COUNT
      source_field: r.id
```

### 3.4 Phase 4: Aspects 机制（P0.1）

#### 3.4.1 设计

借鉴 SAP CDS 的 aspect 机制，支持字段组合复用：

```yaml
# schemas/aspects.yaml

aspects:
  - id: cuid
    name: 创建信息
    fields:
      - id: created_at
        type: datetime
        semantics:
          readonly_always: true
      - id: created_by
        type: string
        semantics:
          readonly_always: true
  
  - id: managed
    name: 管理信息
    aspects: [cuid]  # 继承
    fields:
      - id: updated_at
        type: datetime
        semantics:
          readonly_always: true
      - id: updated_by
        type: string
        semantics:
          readonly_always: true

# 使用
# schemas/business_object.yaml

id: business_object
name: 业务对象
aspects: [managed]  # 自动继承 created_at, created_by, updated_at, updated_by
fields:
  - id: code
    ...
```

#### 3.4.2 实现

```python
# meta/core/yaml_loader.py

def apply_aspects(obj_def: Dict, all_aspects: Dict) -> Dict:
    """将 aspect 字段合并到对象定义中"""
    if 'aspects' not in obj_def:
        return obj_def
    
    merged_fields = []
    aspect_names = obj_def['aspects']
    
    for aspect_name in aspect_names:
        aspect = all_aspects.get(aspect_name)
        if aspect:
            # 递归处理嵌套 aspects
            aspect = apply_aspects(aspect, all_aspects)
            merged_fields.extend(aspect.get('fields', []))
    
    # 对象自身字段追加在后面
    merged_fields.extend(obj_def.get('fields', []))
    obj_def['fields'] = merged_fields
    
    return obj_def
```

### 3.5 Phase 5: 关系类型增强（P0.2）

#### 3.5.1 扩展关系类型

```python
# meta/core/models.py

class RelationType(Enum):
    PARENT_CHILD = "parent_child"    # 父子关系
    REFERENCE = "reference"          # 引用关系（弱依赖）
    COMPOSITION = "composition"      # 组合关系（强依赖，级联删除）
    AGGREGATION = "aggregation"      # 聚合关系（弱依赖，独立生命周期）
    MANY_TO_MANY = "many_to_many"    # 多对多关系
```

#### 3.5.2 删除行为策略

```yaml
# hierarchies.yaml

hierarchies:
  - id: biz_hierarchy
    levels:
      - object: service_module
        relation_type: composition  # 强依赖
        delete_behavior:
          policy: CASCADE           # 删除服务模块时级联删除业务对象
          
      - object: sub_domain
        relation_type: aggregation  # 弱依赖
        delete_behavior:
          policy: RESTRICT           # 有服务模块时不允许删除
```

---

## 四、实施计划

### 4.1 优先级矩阵

| 阶段 | 项目 | 优先级 | 工作量 | 依赖 | 价值 |
|------|------|--------|--------|------|------|
| P1 | TD-1: 移除硬编码层级链 | 高 | 0.5天 | 无 | 消除技术债务 |
| P1 | TD-2: 前端过滤条件统一 | 高 | 0.5天 | 无 | 解决数据不一致 |
| P1 | 元数据 API 增强 | 高 | 1天 | TD-1 | 支持前端动态消费 |
| P2 | TD-4: 关系过滤语义统一 | 中 | 1天 | 无 | 语义清晰 |
| P2 | AnalyticsConfig 扩展 | 中 | 2天 | P1 | 支持分析查询 |
| P3 | Aspects 机制 | 低 | 2天 | 无 | 减少重复定义 |
| P3 | 关系类型增强 | 低 | 1.5天 | 无 | 更精细的关系控制 |

### 4.2 里程碑

```
Week 1:
├── Day 1-2: TD-1 + TD-2 完成
├── Day 3: 元数据 API 增强
└── Day 4-5: 测试验证

Week 2:
├── Day 1-2: TD-4 关系过滤语义统一
├── Day 3-5: AnalyticsConfig 扩展
└── Day 5: 集成测试

Week 3+ (可选):
├── Aspects 机制
└── 关系类型增强
```

### 4.3 验收标准

1. **数据一致性**
   - [ ] 关系树选择数量与列表显示一致
   - [ ] 导出数据与前端选择一致
   - [ ] 多粒度过滤正确工作

2. **代码质量**
   - [ ] 无硬编码层级链
   - [ ] 前后端过滤逻辑统一
   - [ ] 单元测试覆盖率 > 80%

3. **可扩展性**
   - [ ] 新增层级只需修改 `hierarchies.yaml`
   - [ ] 前端可动态获取元数据配置
   - [ ] 支持分析查询配置

---

## 五、层次简化原则（关键）

### 5.1 SAP VDM 最佳实践

SAP 的 VDM 采用**三层架构**，不应过度叠加：

```
Layer 0: Entities (实体) - 物理存储
    ↓
Layer 1: Basic Views (基础视图) - Entity + 常用关联
    ↓
Layer 2: Consumption Views (消费视图) - 按需创建
```

### 5.2 层次过多的风险

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| 性能下降 | 每层 JOIN 累积 | 限制最多 2-3 层 |
| 维护困难 | 依赖链长 | 合并常用关联到基础视图 |
| 缓存失效 | 底层变更影响大 | 减少中间层 |
| 理解成本 | 数据流复杂 | 保持简单架构 |

### 5.3 推荐架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    推荐的简化架构                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Layer 2: Consumption Views (按需)                                  │
│   - relationship_detail_view (关系详情)                              │
│   - bo_relation_stats_view (关系统计)                                │
│                                                                      │
│   Layer 1: Basic Views (基础视图)                                    │
│   - business_object_with_hierarchy (带层级的业务对象)                │
│   - relationship_with_context (带上下文的关系)                       │
│                                                                      │
│   Layer 0: Entities (实体)                                           │
│   - domain, sub_domain, service_module, business_object, relationship│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.4 设计原则

1. **不要过度抽象** - 每个 View 都应有明确的消费场景
2. **合并关联到基础视图** - 避免多层 JOIN
3. **Analytics View 独立存在** - 直接基于 Entity 构建
4. **按需创建消费视图** - 不要为了"复用"而创建

---

## 六、测试要求

### 6.1 单元测试覆盖

| 模块 | 测试文件 | 覆盖要求 |
|------|----------|----------|
| `config_driven_hierarchy_filter.py` | `test_config_driven_hierarchy_filter.py` | > 80% |
| `hierarchy_filter_service.py` | `test_hierarchy_filter_service.py` | > 80% |
| 元数据 API | `test_meta_api.py` | > 80% |
| 字段控制逻辑 | `test_field_controls.py` | > 80% |

### 6.2 集成测试场景

| 场景 | 测试内容 |
|------|----------|
| 层级过滤一致性 | 前端树选择与后端列表过滤结果一致 |
| 多粒度过滤 | businessObject > serviceModule > subDomain > domain 优先级 |
| 导出过滤 | 导出数据与前端选择一致 |
| 字段控制 | business_key/parent_key/immutable 行为正确 |

### 6.3 测试命令

```bash
# 运行所有测试
pytest meta/tests/ -v

# 运行覆盖率
pytest meta/tests/ --cov=meta/services --cov-report=term-missing

# 运行特定测试
pytest meta/tests/test_config_driven_hierarchy_filter.py -v
```

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 重构影响现有功能 | 高 | 增量重构，保持向后兼容 |
| 前端改造工作量大 | 中 | 分阶段实施，优先后端 API |
| 性能下降 | 中 | 添加缓存机制，监控查询性能 |
| 团队学习成本 | 低 | 提供文档和示例 |

---

## 六、参考资料

- [SAP CDS View Documentation](https://help.sap.com/docs/ABAP_PLATFORM_NEW/abap-cds/abap-cds-documentation)
- [SAP Analytics Query](https://community.sap.com/t5/technology-blogs-by-sap/sap-fiori-elements-for-odata-building-analytical-list-page/ba-p/13335765)
- [Palantir Foundry Ontology](https://www.palantir.com/docs/foundry/ontology/)
- `.trae/backlog/filter-export-improvements.md`
- `.trae/specs/unified-meta-model-design/spec.md`
