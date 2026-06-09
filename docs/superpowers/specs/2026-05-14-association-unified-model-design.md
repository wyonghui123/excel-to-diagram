## 目录

1. [一、背景与问题](#一-背景与问题)
2. [二、完整依赖分析](#二-完整依赖分析)
3. [三、设计原则](#三-设计原则)
4. [四、Association 类型体系](#四-association-类型体系)
5. [五、智能推导规则](#五-智能推导规则)
6. [六、不依赖 Association 推导的配置](#六-不依赖-association-推导的配置)
7. [七、YAML 配置示例](#七-yaml-配置示例)
8. [八、向后兼容](#八-向后兼容)
9. [九、详细实现方案](#九-详细实现方案)
10. [十、API 端点](#十-api-端点)
11. [十一、验收标准](#十一-验收标准)
12. [十二、影响范围清单](#十二-影响范围清单)
13. [十三、后续工作](#十三-后续工作)
14. [十四、变更记录](#十四-变更记录)

---
# Association 统一模型设计规范

> **版本**: v3.0
> **日期**: 2026-05-14
> **目的**: 通过 Association 单一事实来源统一 parent_object、hierarchy、path_field 等层级相关配置

---

## 一、背景与问题

### 1.1 头部企业研究

#### SAP S/4HANA CDS

> *"In CDS, a hierarchy node entity can be modeled by a CDS view or a CDS entity, and the **parent relation can be modeled by a CDS association**."*

SAP 明确指出 **parent-child hierarchy 是通过 Association 建模的**。

**SAP 关系模型**：

| CDS 概念 | 说明 |
|---------|------|
| Association | 定义关系的基础 |
| Composition | 强整体-部分关系（子依赖父生命周期） |
| Parent-Child Hierarchy | 通过 Composition 的基数推导 |

#### Salesforce Object Model

| 关系类型 | 说明 | 与 Association 的关系 |
|----------|------|---------------------|
| **Lookup** | 松散关联，可独立存在 | → `association` |
| **Master-Detail** | 紧耦合，子依赖父 | → `composition` |
| **Hierarchical** | 自引用（如用户汇报线） | → `self-reference composition` |

#### 结论

头部企业（SAP、Salesforce）的共同点：

1. **Association 是基础抽象**：所有关系类型统一用 Association 表示
2. **Parent-Child 通过 Association 推导**：通过基数和类型推导层级
3. **Composition 是特殊类型**：表示强生命周期依赖

### 1.2 现有设计的问题

当前设计中，层级关系和关联关系分散在多处配置：

```yaml
# domain.yaml（现状）
name: domain
parent_object: version          # 父子关系声明
hierarchy:
  enabled: true
  path_field: hierarchy_path    # 路径字段
  depth_field: hierarchy_depth # 深度字段
  parent_field: version_id      # 外键字段

# hierarchies.yaml（独立配置）
hierarchies:
  - id: biz_hierarchy
    levels:
      - object: domain
        parent_object: version
        foreign_key_field: version_id
        delete_behavior:
          policy: RESTRICT

# relationship.yaml（使用 scope_rules）
fields:
  - id: relation_scope
    semantics:
      computed_by: hierarchy_scope
      scope_rules_ref: hierarchies.hierarchy_scopes
```

**问题**：

| 问题 | 说明 |
|------|------|
| 配置冗余 | `parent_object`、`foreign_key_field` 在多处重复声明 |
| 不一致风险 | hierarchies.yaml 和实体 YAML 可能不一致 |
| 维护困难 | 修改层级结构需要改多处 |
| 语义混乱 | `parent_object`、`associations`、`hierarchies` 关系不清 |

### 1.3 设计目标

| 目标 | 说明 |
|------|------|
| **单一事实来源** | 所有关系通过 `associations[]` 配置 |
| **智能推导** | 自动计算 `parent_object`、`path_field`、`depth_field`、`foreign_key_field` |
| **消除冗余** | 逐步废弃 `hierarchies.yaml` |
| **配置简洁** | 只需声明自己的关联 |

---

## 二、完整依赖分析

### 2.1 核心配置文件依赖

| 文件 | 位置 | 关键配置 | 状态 |
|------|------|---------|------|
| `hierarchies.yaml` | `meta/schemas/` | 层级定义、scope_rules、dimensions | 权威配置源 |
| `domain.yaml` | `meta/schemas/` | parent_object、hierarchy | 需改造 |
| `business_object.yaml` | `meta/schemas/` | parent_object、hierarchy | 需改造 |
| `sub_domain.yaml` | `meta/schemas/` | parent_object、hierarchy | 需改造 |
| `service_module.yaml` | `meta/schemas/` | parent_object、hierarchy | 需改造 |
| `version.yaml` | `meta/schemas/` | parent_object、hierarchy、context | 需改造 |
| `relationship.yaml` | `meta/schemas/` | scope_rules_ref | 保持独立 |

### 2.2 后端 Python 服务依赖

| 服务 | 文件 | 功能 | 需改造 |
|------|------|------|--------|
| **HierarchyService** | `meta/services/hierarchy_service.py` | 层级树构建 | ✅ |
| **CascadeService** | `meta/services/cascade_service.py` | 级联策略 | ✅ |
| **HierarchyFilterService** | `meta/services/hierarchy_filter_service.py` | 层级过滤 | ✅ |
| **HierarchyConfigLoader** | `meta/services/cascade_service.py` | 层级配置加载 | ✅ |
| **HierarchyValidationInterceptor** | `meta/core/interceptors/hierarchy_validation_interceptor.py` | 层级校验 | ✅ |
| **CascadeInterceptor** | `meta/core/interceptors/cascade_interceptor.py` | 级联拦截 | ✅ |
| **yaml_loader** | `meta/core/yaml_loader.py` | 配置解析 | ✅ |
| **models** | `meta/core/models.py` | 元数据模型 | ✅ |

### 2.3 前端组件依赖

| 组件 | 文件 | 功能 | 需改造 |
|------|------|------|--------|
| **useHierarchyTypes** | `src/composables/useHierarchyTypes.js` | 层级类型管理 | ⚠️ |
| **useHierarchyList** | `src/composables/useHierarchyList.js` | 层级列表管理 | ⚠️ |
| **useCascadeSelect** | `src/composables/useCascadeSelect.js` | 级联选择 | ⚠️ |
| **useDetail** | `src/composables/useDetail.js` | 详情页状态 | ✅ (已完成) |
| **DetailPage** | `src/components/common/DetailPage/DetailPage.vue` | 详情页 | ✅ (已完成) |

### 2.4 拦截器依赖

```
┌─────────────────────────────────────────────────────────────┐
│                    Interceptors 依赖链                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CRUD Operations (BOFramework)                             │
│       │                                                     │
│       ├── HierarchyValidationInterceptor                   │
│       │    └── 校验 parent_object 不可变                   │
│       │                                                     │
│       └── CascadeInterceptor                               │
│            ├── cascade_delete_children                     │
│            ├── cleanup_annotations                         │
│            └── cleanup_association_tables                  │
│                                                             │
│  依赖:                                                     │
│  ├── HierarchyConfigLoader                                 │
│  ├── CascadeService                                       │
│  └── yaml_loader                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.5 配置加载依赖

```
┌─────────────────────────────────────────────────────────────┐
│                    配置加载依赖链                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  hierarchies.yaml (权威配置)                                │
│       │                                                     │
│       ├──→ HierarchyConfigLoader                           │
│       │    └── get_hierarchy()                            │
│       │    └── get_delete_behavior()                      │
│       │    └── get_parent_object()                        │
│       │    └── get_hierarchy_scopes()                    │
│       │                                                     │
│       └──→ yaml_loader.py                                 │
│            ├── parse_hierarchy()                          │
│            ├── parse_associations()                       │
│            └── parse_scope_rules()                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、设计原则

### 3.1 核心原则

1. **YAML 是单一事实来源**：所有配置从 YAML 声明，无硬编码
2. **Association 是统一抽象**：父子关系、业务关联、系统关联统一用 Association 表示
3. **智能推导**：从 Association 配置自动计算派生属性
4. **向后兼容**：支持新旧配置共存，逐步迁移
5. **独立配置分离**：无法从 Association 推导的配置保持独立

### 3.2 UML 关系映射

```
Association（关联）
│
├── Composition（组成关系）
│   ├── cardinality: many_to_one → parent_object
│   ├── cardinality: many_to_one → foreign_key_field
│   └── cardinality: one_to_many → children
│
├── Aggregation（聚合关系）
│   └── 无生命周期依赖
│
└── 普通 Association
    └── 业务关联
```

---

## 四、Association 类型体系

### 4.1 类型定义

| 类型 | 说明 | 示例 | 生命周期 |
|------|------|------|----------|
| `association` | 普通关联 | 用户-角色 | 可独立存在 |
| `composition` | 组成关系 | 领域-子领域、父子 | 随主对象 |

### 4.2 基数定义

| 基数 | 说明 | 推导 |
|------|------|------|
| `many_to_one` | 多对一（子→父） | 自动推导 `parent_object`、`foreign_key_field` |
| `one_to_many` | 一对多（父→子） | 参与层级构建 |
| `many_to_many` | 多对多 | 普通关联 |

### 4.3 层级标识

```yaml
associations:
  - name: parent
    target_entity: version
    type: composition
    cardinality: many_to_one
    foreign_key_field: version_id  # 新增：自动推导外键
    hierarchy: true  # 参与层级计算
    
  - name: children
    target_entity: sub_domain
    type: composition
    cardinality: one_to_many
    hierarchy: true
```

---

## 五、智能推导规则

### 5.1 从 Association 可推导的配置

| 配置 | 推导来源 | 说明 |
|------|---------|------|
| `parent_object` | `cardinality: many_to_one` | 自动推导父对象 |
| `foreign_key_field` | `cardinality: many_to_one` | 自动推导外键字段名 |
| `path_field` | `cardinality: one_to_many` + `hierarchy: true` | 存在子对象时自动生成 |
| `depth_field` | `cardinality: one_to_many` + `hierarchy: true` | 存在子对象时自动生成 |
| `delete_behavior` | `type: composition` | composition 默认 CASCADE |

### 5.2 parent_object 推导

```python
def derive_parent_object(associations):
    parent = next((a for a in associations
        if a.cardinality == 'many_to_one'
        and a.type == 'composition'), None)
    return parent.target_entity if parent else None
```

### 5.3 foreign_key_field 推导

```python
def derive_foreign_key_field(associations):
    parent = next((a for a in associations
        if a.cardinality == 'many_to_one'
        and a.type == 'composition'), None)
    
    if parent:
        # 优先使用显式配置
        if parent.get('foreign_key_field'):
            return parent['foreign_key_field']
        # 自动推导：target_entity + "_id"
        return f"{parent['target_entity']}_id"
    
    return None
```

### 5.4 path_field / depth_field 推导

```python
def derive_hierarchy_fields(associations):
    has_hierarchy = any(a for a in associations
        if a.cardinality == 'one_to_many'
        and getattr(a, 'hierarchy', False))
    
    return {
        'path_field': 'hierarchy_path' if has_hierarchy else None,
        'depth_field': 'hierarchy_depth' if has_hierarchy else None
    }
```

### 5.5 层级链构建

```python
def build_hierarchy_chain(entities):
    chains = []
    
    for entity in entities:
        chain = []
        current = entity
        
        while current:
            chain.unshift(current.name)
            parent_assoc = next((a for a in current.associations
                if a.cardinality == 'many_to_one' and a.hierarchy), None)
            current = parent_assoc.target_entity if parent_assoc else None
        
        chains.append(chain)
    
    return sorted(chains, key=lambda x: len(x))
```

---

## 六、不依赖 Association 推导的配置

### 6.1 独立配置分类

| 配置类型 | 说明 | 示例 | 推导来源 |
|---------|------|------|----------|
| **scope_rules** | 层级范围规则 | `source.domain_id != target.domain_id` | 业务语义 |
| **dimensions** | 维度定义 | `domain`、`sub_domain` | 视图展示 |
| **context** | 版本上下文 | `field: version_id` | 运行时环境 |
| **cascade_select** | 级联下拉 | 下级对象选择逻辑 | UI 交互 |
| **computed_by** | 计算方式 | `hierarchy_scope` | 业务逻辑 |

### 6.2 scope_rules 详细说明

**定义位置**：`hierarchies.yaml` (hierarchy_scopes)

**使用位置**：`relationship.yaml` (scope_rules_ref)

```yaml
# hierarchies.yaml（保持独立）
hierarchy_scopes:
  - id: cross_domain
    name: 跨领域
    rule: source.domain_id != target.domain_id
    color: "#F44336"
```

```yaml
# relationship.yaml（引用）
fields:
  - id: relation_scope
    semantics:
      computed_by: hierarchy_scope
      scope_rules_ref: hierarchies.hierarchy_scopes
```

### 6.3 dimensions 详细说明

**定义位置**：`hierarchies.yaml` (dimensions)

```yaml
dimensions:
  - id: domain
    name: 领域
    object: domain
    hierarchy: biz_hierarchy
    filter_param: id
    ancestor_param: null
    
  - id: sub_domain
    name: 子领域
    object: sub_domain
    hierarchy: biz_hierarchy
    filter_param: domain_id
    ancestor_param: id
```

---

## 七、YAML 配置示例

### 7.1 完整配置（新版）

```yaml
# domain.yaml
name: domain
label: 领域
aspects:
  - audit_aspect

associations:
  # 父子层级关系（可推导 parent_object、foreign_key_field）
  - name: parent
    label: 父版本
    target_entity: version
    type: composition
    cardinality: many_to_one
    foreign_key_field: version_id  # 可选，自动推导
    hierarchy: true
    
  - name: sub_domains
    label: 子领域
    target_entity: sub_domain
    type: composition
    cardinality: one_to_many
    hierarchy: true
    display:
      mode: embedded
      collapsed: true

  # 业务关联
  - name: related_domains
    label: 关联领域
    target_entity: domain
    type: association
    cardinality: many_to_many
    display:
      mode: tab

  # 系统关联
  - name: annotations
    label: 备注
    target_entity: annotation
    type: composition
    display:
      mode: embedded

# 独立配置（不依赖 Association 推导）
scope_rules_ref: hierarchies.hierarchy_scopes
dimensions:
  - id: domain
    object: domain
    filter_param: id
```

### 7.2 自动推导结果

```yaml
# 自动推导（无需手动配置）
derived:
  parent_object: version          # from many_to_one
  foreign_key_field: version_id   # from many_to_one
  path_field: hierarchy_path      # from one_to_many
  depth_field: hierarchy_depth    # from one_to_many
  hierarchy_chain:
    - product
    - version
    - domain
    - sub_domain
    - service_module
    - business_object
```

### 7.3 配置分类总结

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        YAML 配置分类                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Association 可推导的配置（通过 cardinality/type/hierarchy）              │
│  ├── parent_object ← many_to_one                                       │
│  ├── foreign_key_field ← many_to_one                                   │
│  ├── path_field ← one_to_many + hierarchy: true                        │
│  ├── depth_field ← one_to_many + hierarchy: true                       │
│  └── delete_behavior ← composition                                     │
│                                                                         │
│  独立配置（不依赖 Association 推导）                                    │
│  ├── scope_rules ← scope_rules_ref                                      │
│  ├── dimensions ← 视图展示需求                                          │
│  ├── context ← 版本系统                                                │
│  ├── cascade_select ← UI 交互                                          │
│  └── computed_by ← 业务逻辑                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 八、向后兼容

### 8.1 兼容策略

| 场景 | 处理方式 |
|------|----------|
| 显式 `parent_object` | 优先使用，兼容旧配置 |
| 显式 `foreign_key_field` | 优先使用，兼容旧配置 |
| hierarchies.yaml 存在 | 合并推导结果 |
| 冲突检测 | 警告但不阻断 |
| scope_rules | 保持独立配置 |

### 8.2 迁移策略

```
Phase 1: 添加推导逻辑（向后兼容）
    ↓
Phase 2: 清理冗余配置（警告）
    ↓
Phase 3: 废弃旧配置（可配置）
```

### 8.3 配置合并

```python
def merge_config(config, derived):
    # 显式配置优先
    if config.get('parent_object'):
        if derived.get('parent_object') and config['parent_object'] != derived['parent_object']:
            logger.warning(f"parent_object conflict: {config['parent_object']} vs {derived['parent_object']}")
        return config['parent_object']
    
    return derived.get('parent_object')
```

---

## 九、详细实现方案

### 9.1 YAML Loader 改动

**文件**：`meta/core/yaml_loader.py`

```python
class AssociationParser:
    def parse(self, entity_yaml):
        associations = entity_yaml.get('associations', [])
        
        # 1. 解析 Association 配置
        parsed = [self.parse_association(a) for a in associations]
        
        # 2. 推导 parent_object
        entity.parent_object = self.derive_parent_object(parsed)
        
        # 3. 推导 foreign_key_field
        entity.foreign_key_field = self.derive_foreign_key_field(parsed)
        
        # 4. 推导 hierarchy_fields
        hierarchy_fields = self.derive_hierarchy_fields(parsed)
        entity.path_field = hierarchy_fields['path_field']
        entity.depth_field = hierarchy_fields['depth_field']
        
        # 5. 构建层级链
        entity.hierarchy_chain = self.build_hierarchy_chain(parsed)
        
        # 6. 处理独立配置（不推导）
        entity.scope_rules = self.parse_scope_rules(entity_yaml)
        entity.dimensions = self.parse_dimensions(entity_yaml)
        
        return entity
    
    def derive_parent_object(self, associations):
        parent = next((a for a in associations
            if a.cardinality == 'many_to_one'
            and a.type == 'composition'), None)
        return parent.target_entity if parent else None
    
    def derive_foreign_key_field(self, associations):
        parent = next((a for a in associations
            if a.cardinality == 'many_to_one'
            and a.type == 'composition'), None)
        
        if parent:
            if parent.get('foreign_key_field'):
                return parent['foreign_key_field']
            return f"{parent['target_entity']}_id"
        
        return None
    
    def derive_hierarchy_fields(self, associations):
        has_hierarchy = any(a for a in associations
            if a.cardinality == 'one_to_many'
            and getattr(a, 'hierarchy', False))
        
        return {
            'path_field': 'hierarchy_path' if has_hierarchy else None,
            'depth_field': 'hierarchy_depth' if has_hierarchy else None
        }
```

### 9.2 HierarchyConfigLoader 改动

**文件**：`meta/services/cascade_service.py`

```python
class HierarchyConfigLoader:
    def __init__(self):
        self._associations_cache = {}
    
    def get_parent_object(self, object_type):
        """从 Association 推导 parent_object"""
        entity = registry.get(object_type)
        
        if entity.parent_object and entity._config.get('parent_object'):
            # 显式配置优先
            return entity.parent_object
        
        # 从 associations 推导
        parent_assocs = [a for a in entity.associations
            if a.cardinality == 'many_to_one' and a.type == 'composition']
        
        if parent_assocs:
            return parent_assocs[0].target_entity
        
        return None
    
    def get_foreign_key_field(self, object_type):
        """从 Association 推导 foreign_key_field"""
        entity = registry.get(object_type)
        
        if entity._config.get('foreign_key_field'):
            return entity._config['foreign_key_field']
        
        # 从 associations 推导
        parent_assocs = [a for a in entity.associations
            if a.cardinality == 'many_to_one' and a.type == 'composition']
        
        if parent_assocs:
            parent = parent_assocs[0]
            return parent.get('foreign_key_field') or f"{parent['target_entity']}_id"
        
        return None
    
    def get_child_types(self, object_type):
        """获取所有子对象类型"""
        entity = registry.get(object_type)
        
        # 从 associations 推导
        child_assocs = [a for a in entity.associations
            if a.cardinality == 'one_to_many']
        
        return [a.target_entity for a in child_assocs]
```

### 9.3 拦截器改动

#### 9.3.1 HierarchyValidationInterceptor

**文件**：`meta/core/interceptors/hierarchy_validation_interceptor.py`

```python
class HierarchyValidationInterceptor:
    def _validate_update(self, operation):
        object_type = operation.entity_type
        
        # 从 Association 推导 parent_object
        parent_object = HierarchyConfigLoader().get_parent_object(object_type)
        
        if parent_object:
            parent_field = HierarchyConfigLoader().get_foreign_key_field(object_type)
            
            if parent_field in operation.changes:
                raise ValidationError(
                    f"Cannot change {parent_field}: parent object is immutable"
                )
```

#### 9.3.2 CascadeInterceptor

**文件**：`meta/core/interceptors/cascade_interceptor.py`

```python
class CascadeInterceptor:
    def _cascade_delete_children(self, operation):
        object_type = operation.entity_type
        
        # 从 Association 推导 child_types
        child_types = HierarchyConfigLoader().get_child_types(object_type)
        
        for child_type in child_types:
            child_assoc = next((a for a in operation.entity.associations
                if a.target_entity == child_type and a.type == 'composition'), None)
            
            if child_assoc and getattr(child_assoc, 'cascade_delete', False):
                # 执行级联删除
                self._delete_composition_children(operation, child_type)
```

---

## 十、API 端点

### 10.1 层级查询 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/meta/hierarchy/tree` | GET | 获取层级树（保持不变） |
| `/api/v2/meta/hierarchy/path/{type}/{id}` | GET | 获取路径（保持不变） |
| `/api/v2/bo/{type}/{id}/hierarchy` | GET | 新增：获取完整层级信息 |

### 10.2 响应格式

```json
{
  "success": true,
  "data": {
    "current": {
      "type": "domain",
      "id": 1,
      "name": "销售领域"
    },
    "path": [
      { "type": "product", "id": 1, "name": "ERP产品" },
      { "type": "version", "id": 1, "name": "V2.0" },
      { "type": "domain", "id": 1, "name": "销售领域" }
    ],
    "children": [
      { "type": "sub_domain", "id": 1, "name": "CRM子域" },
      { "type": "sub_domain", "id": 2, "name": "SRM子域" }
    ],
    "derived": {
      "parent_object": "version",
      "foreign_key_field": "version_id",
      "path_field": "hierarchy_path",
      "depth_field": "hierarchy_depth"
    },
    "independent": {
      "scope_rules": ["cross_domain", "same_domain_cross_subdomain"],
      "dimensions": ["domain", "sub_domain", "service_module"]
    }
  }
}
```

---

## 十一、验收标准

### 11.1 功能验收

| 编号 | 标准 | 验证方式 |
|------|------|----------|
| 1 | Association 可配置 `cardinality: many_to_one` | YAML 配置 |
| 2 | `parent_object` 自动从 many_to_one 推导 | 单元测试 |
| 3 | `foreign_key_field` 自动从 many_to_one 推导 | 单元测试 |
| 4 | `path_field` / `depth_field` 从 one_to_many 推导 | 单元测试 |
| 5 | 层级链正确构建 | 集成测试 |
| 6 | 向后兼容旧配置 | 回归测试 |

### 11.2 服务验收

| 编号 | 标准 | 验证方式 |
|------|------|----------|
| 1 | HierarchyConfigLoader 支持从 Association 推导 | 单元测试 |
| 2 | HierarchyService 正常工作 | 集成测试 |
| 3 | CascadeService 正常工作 | 集成测试 |
| 4 | HierarchyValidationInterceptor 正常工作 | 集成测试 |
| 5 | CascadeInterceptor 正常工作 | 集成测试 |

### 11.3 独立配置验收

| 编号 | 标准 | 说明 |
|------|------|------|
| 1 | scope_rules 保持独立配置 | 不从 Association 推导 |
| 2 | dimensions 保持独立配置 | 不从 Association 推导 |
| 3 | context 保持独立配置 | 不从 Association 推导 |
| 4 | 冲突时输出警告 | 日志警告 |

### 11.4 向后兼容验收

| 编号 | 标准 |
|------|------|
| 1 | hierarchies.yaml 存在时兼容处理 |
| 2 | 显式 parent_object 优先使用 |
| 3 | 显式 foreign_key_field 优先使用 |
| 4 | 逐步废弃旧配置 |

---

## 十二、影响范围清单

### 12.1 需要改造的文件

#### YAML 配置（6个）

- [ ] `meta/schemas/domain.yaml` - 添加 associations
- [ ] `meta/schemas/business_object.yaml` - 添加 associations
- [ ] `meta/schemas/sub_domain.yaml` - 添加 associations
- [ ] `meta/schemas/service_module.yaml` - 添加 associations
- [ ] `meta/schemas/version.yaml` - 添加 associations
- [ ] `meta/schemas/hierarchies.yaml` - 保持（独立配置）

#### Python 服务（8个）

- [ ] `meta/core/yaml_loader.py` - 添加推导逻辑
- [ ] `meta/core/models.py` - 添加 Association 模型
- [ ] `meta/services/cascade_service.py` - 修改 HierarchyConfigLoader
- [ ] `meta/services/hierarchy_service.py` - 使用新的推导
- [ ] `meta/services/hierarchy_filter_service.py` - 使用新的推导
- [ ] `meta/core/interceptors/hierarchy_validation_interceptor.py` - 使用新的推导
- [ ] `meta/core/interceptors/cascade_interceptor.py` - 使用新的推导

#### TypeScript 组件（3个）

- [ ] `src/composables/useHierarchyTypes.js` - 使用新的元数据
- [ ] `src/composables/useHierarchyList.js` - 使用新的元数据
- [ ] `src/composables/useCascadeSelect.js` - 使用新的元数据

#### 测试文件（4个）

- [ ] `meta/tests/test_hierarchy_validation.py` - 添加推导测试
- [ ] `meta/tests/test_hierarchy_path.py` - 添加推导测试
- [ ] `meta/tests/test_hierarchy_filter_service.py` - 更新测试
- [ ] `meta/tests/test_cascade_service.py` - 更新测试

### 12.2 改造工作量估算

| 模块 | 文件数 | 复杂度 | 说明 |
|------|--------|--------|------|
| YAML 配置 | 6 | 低 | 添加 associations 声明 |
| Python 服务 | 8 | 高 | 核心推导逻辑 |
| TypeScript | 3 | 中 | 使用新元数据 |
| 测试 | 4 | 中 | 添加推导测试 |
| **总计** | **21** | - | - |

---

## 十三、后续工作

| 编号 | 工作 | 说明 | 优先级 |
|------|------|------|--------|
| 1 | YAML Loader 改造 | 实现智能推导逻辑 | P0 |
| 2 | HierarchyConfigLoader 改造 | 支持从 Association 构建 | P0 |
| 3 | 拦截器改造 | 使用新的推导 | P0 |
| 4 | YAML 配置改造 | 实体文件添加 associations | P1 |
| 5 | 单元测试 | 推导逻辑测试 | P1 |
| 6 | 集成测试 | 完整流程测试 | P1 |
| 7 | 前端组件改造 | TypeScript 使用新元数据 | P2 |
| 8 | 文档更新 | 移除 hierarchies.yaml 依赖 | P2 |

---

## 十四、变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-05-14 | v1.0 | 初始版本 |
| 2026-05-14 | v2.0 | 补充 SAP/Salesforce 头部产品研究；增加独立配置分类 |
| 2026-05-14 | v3.0 | 完整依赖分析；详细实现方案；影响范围清单 |

---

**设计完成，待实现**
