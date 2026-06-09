## 目录

1. [一、实现方案总览](#一-实现方案总览)
2. [二、详细实现方案](#二-详细实现方案)
3. [三、测试策略](#三-测试策略)
4. [四、完整 Checklist](#四-完整-checklist)
5. [五、风险与缓解](#五-风险与缓解)
6. [六、时间估算](#六-时间估算)
7. [七、验收标准](#七-验收标准)

---
# Association 统一模型实现方案与 Checklist

> **版本**: v1.0
> **日期**: 2026-05-14
> **目的**: 详细实现方案和 Checklist

---

## 一、实现方案总览

### 1.1 核心改动概述

| 模块 | 改动类型 | 说明 |
|------|---------|------|
| **models.py** | 新增字段 | 添加 `cardinality`、`hierarchy`、`foreign_key_field` 到 AssociationDefinition |
| **yaml_loader.py** | 新增逻辑 | 添加推导函数 `derive_parent_object()`、`derive_foreign_key_field()` 等 |
| **cascade_service.py** | 修改逻辑 | HierarchyConfigLoader 支持从 Association 推导 |
| **拦截器** | 修改调用 | 使用新的推导方法替代硬编码 |

### 1.2 实现优先级

```
P0: 核心推导逻辑（必须先完成）
    ├── models.py 新增字段
    ├── yaml_loader.py 新增推导
    └── cascade_service.py 修改 HierarchyConfigLoader

P1: 拦截器改造
    ├── HierarchyValidationInterceptor
    └── CascadeInterceptor

P2: YAML 配置改造
    └── 实体文件添加 associations

P3: 前端组件改造
    └── TypeScript 使用新元数据
```

---

## 二、详细实现方案

### 2.1 models.py 改动

**文件**：`meta/core/models.py`

#### 2.1.1 新增字段到 AssociationDefinition

**当前代码**（行 59-67）：

```python
@dataclass
class AssociationDefinition:
    """关联关系定义"""
    name: str
    type: str
    through: Optional[str] = None
    source_key: str = ""
    target_entity: str = ""
    target_key: str = ""
    actions: Dict[str, AssociationActionDef] = field(default_factory=dict)
```

**改动后**：

```python
@dataclass
class AssociationDefinition:
    """关联关系定义"""
    name: str
    type: str  # 'association' | 'composition'
    through: Optional[str] = None
    source_key: str = ""
    target_entity: str = ""
    target_key: str = ""
    actions: Dict[str, AssociationActionDef] = field(default_factory=dict)
    
    # ── 新增：基数 ──
    cardinality: str = "many_to_many"  # 'many_to_one' | 'one_to_many' | 'many_to_many'
    
    # ── 新增：层级标识 ──
    hierarchy: bool = False  # 是否参与层级计算
    
    # ── 新增：外键字段 ──
    foreign_key_field: Optional[str] = None  # 显式指定外键字段
    
    # ── 新增：级联删除 ──
    cascade_delete: bool = False  # 删除父对象时是否级联删除
```

#### 2.1.2 Checklist

- [ ] 在 `AssociationDefinition` 中添加 `cardinality` 字段
- [ ] 在 `AssociationDefinition` 中添加 `hierarchy` 字段
- [ ] 在 `AssociationDefinition` 中添加 `foreign_key_field` 字段
- [ ] 在 `AssociationDefinition` 中添加 `cascade_delete` 字段
- [ ] 添加字段验证逻辑（cardinality 枚举值校验）

---

### 2.2 yaml_loader.py 改动

**文件**：`meta/core/yaml_loader.py`

#### 2.2.1 新增导入

**当前代码**（行 49-67）：

```python
@dataclass
class AssociationDefinition:
    """关联关系定义"""
    name: str
    type: str
    ...
```

**改动**：无需改动，AssociationDefinition 已存在

#### 2.2.2 新增推导函数

**新增位置**：在 `parse_associations()` 方法后添加

```python
def derive_parent_object(self, associations: List[Dict]) -> Optional[str]:
    """从 Association 配置推导 parent_object
    
    规则：
    1. 查找 cardinality='many_to_one' 且 type='composition' 的 Association
    2. 其 target_entity 即为 parent_object
    """
    for assoc in associations:
        if (assoc.get('cardinality') == 'many_to_one' and 
            assoc.get('type') == 'composition'):
            return assoc.get('target_entity')
    return None


def derive_foreign_key_field(self, associations: List[Dict]) -> Optional[str]:
    """从 Association 配置推导 foreign_key_field
    
    规则：
    1. 查找 cardinality='many_to_one' 且 type='composition' 的 Association
    2. 优先使用显式配置的 foreign_key_field
    3. 否则自动推导：target_entity + "_id"
    """
    for assoc in associations:
        if (assoc.get('cardinality') == 'many_to_one' and 
            assoc.get('type') == 'composition'):
            # 显式配置优先
            if assoc.get('foreign_key_field'):
                return assoc['foreign_key_field']
            # 自动推导
            return f"{assoc['target_entity']}_id"
    return None


def derive_hierarchy_fields(self, associations: List[Dict]) -> Dict[str, Optional[str]]:
    """从 Association 配置推导 path_field 和 depth_field
    
    规则：
    1. 存在 cardinality='one_to_many' 且 hierarchy=True 的 Association 时
    2. 自动生成 path_field='hierarchy_path' 和 depth_field='hierarchy_depth'
    """
    has_hierarchy = any(
        a.get('cardinality') == 'one_to_many' and a.get('hierarchy', False)
        for a in associations
    )
    
    return {
        'path_field': 'hierarchy_path' if has_hierarchy else None,
        'depth_field': 'hierarchy_depth' if has_hierarchy else None
    }


def build_hierarchy_chain(self, entity_name: str, registry: Dict) -> List[str]:
    """构建单个对象的层级链
    
    规则：
    1. 从当前对象出发
    2. 向上追溯 cardinality='many_to_one' 且 hierarchy=True 的 Association
    3. 构建完整的层级链
    """
    chain = [entity_name]
    current = entity_name
    
    max_depth = 10  # 防止循环引用
    depth = 0
    
    while depth < max_depth:
        entity = registry.get(current)
        if not entity or not entity.associations:
            break
        
        parent_assoc = next((
            a for a in entity.associations
            if a.get('cardinality') == 'many_to_one' and a.get('hierarchy', False)
        ), None)
        
        if not parent_assoc:
            break
        
        current = parent_assoc.get('target_entity')
        chain.insert(0, current)
        depth += 1
    
    return chain
```

#### 2.2.3 修改 parse_entity 方法

**新增位置**：在解析完 associations 后添加推导逻辑

```python
def parse_entity(self, entity_yaml: Dict) -> MetaObject:
    # ... 现有代码 ...
    
    # 解析 associations（现有代码）
    associations = entity_yaml.get('associations', [])
    parsed_associations = [self.parse_association(a) for a in associations]
    
    # ── 新增：推导层级属性 ──
    
    # 推导 parent_object
    derived_parent_object = self.derive_parent_object(parsed_associations)
    if not entity_yaml.get('parent_object'):
        entity.parent_object = derived_parent_object
    
    # 推导 foreign_key_field（存储到 hierarchy 配置中）
    derived_foreign_key = self.derive_foreign_key_field(parsed_associations)
    if not entity_yaml.get('hierarchy', {}).get('foreign_key_field'):
        if entity.hierarchy is None:
            entity.hierarchy = {}
        entity.hierarchy['foreign_key_field'] = derived_foreign_key
    
    # 推导 path_field 和 depth_field
    hierarchy_fields = self.derive_hierarchy_fields(parsed_associations)
    if entity.hierarchy is None:
        entity.hierarchy = {}
    entity.hierarchy['path_field'] = hierarchy_fields['path_field']
    entity.hierarchy['depth_field'] = hierarchy_fields['depth_field']
    
    # 推导完成后，输出警告（如果显式配置与推导不一致）
    if entity_yaml.get('parent_object') and derived_parent_object:
        if entity_yaml['parent_object'] != derived_parent_object:
            logger.warning(
                f"[YAML Loader] parent_object conflict for {entity.name}: "
                f"explicit={entity_yaml['parent_object']}, "
                f"derived={derived_parent_object}"
            )
    
    # ... 后续代码 ...
```

#### 2.2.4 Checklist

- [ ] 新增 `derive_parent_object()` 方法
- [ ] 新增 `derive_foreign_key_field()` 方法
- [ ] 新增 `derive_hierarchy_fields()` 方法
- [ ] 新增 `build_hierarchy_chain()` 方法
- [ ] 修改 `parse_entity()` 方法，添加推导逻辑
- [ ] 添加冲突警告日志
- [ ] 添加单元测试

---

### 2.3 cascade_service.py 改动

**文件**：`meta/services/cascade_service.py`

#### 2.3.1 修改 HierarchyConfigLoader

**当前代码**（行 58-60）：

```python
@classmethod
def get_parent_object(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> Optional[str]:
    level = cls.get_level_by_object(object_type, hierarchy_id)
    return level.get('parent_object') if level else None
```

**改动后**：

```python
@classmethod
def get_parent_object(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> Optional[str]:
    """获取父对象类型
    
    优先级：
    1. 优先从 hierarchies.yaml 获取（向后兼容）
    2. 如果不存在，则从 Registry 中获取实体，从 Association 推导
    """
    # 优先从 hierarchies.yaml 获取
    level = cls.get_level_by_object(object_type, hierarchy_id)
    if level and level.get('parent_object'):
        return level.get('parent_object')
    
    # 从 Registry 推导
    from meta.core.models import registry
    entity = registry.get(object_type)
    if entity and entity.associations:
        for assoc in entity.associations:
            if (assoc.get('cardinality') == 'many_to_one' and 
                assoc.get('type') == 'composition'):
                return assoc.get('target_entity')
    
    return None


@classmethod
def get_foreign_key(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> Optional[str]:
    """获取外键字段
    
    优先级：
    1. 优先从 hierarchies.yaml 获取
    2. 如果不存在，则从 Registry 中获取实体，从 Association 推导
    """
    # 优先从 hierarchies.yaml 获取
    level = cls.get_level_by_object(object_type, hierarchy_id)
    if level and level.get('foreign_key_field'):
        return level.get('foreign_key_field')
    
    # 从 Registry 推导
    from meta.core.models import registry
    entity = registry.get(object_type)
    
    # 尝试从 hierarchy 配置获取
    if entity and entity.hierarchy and entity.hierarchy.get('foreign_key_field'):
        return entity.hierarchy.get('foreign_key_field')
    
    # 从 Association 推导
    if entity and entity.associations:
        for assoc in entity.associations:
            if (assoc.get('cardinality') == 'many_to_one' and 
                assoc.get('type') == 'composition'):
                # 显式配置优先
                if assoc.get('foreign_key_field'):
                    return assoc['foreign_key_field']
                # 自动推导
                return f"{assoc['target_entity']}_id"
    
    return None


@classmethod
def get_child_types(cls, object_type: str, hierarchy_id: str = 'biz_hierarchy') -> List[str]:
    """获取所有子对象类型
    
    优先级：
    1. 优先从 hierarchies.yaml 获取
    2. 如果不存在，则从 Registry 中获取实体，从 Association 推导
    """
    # 优先从 hierarchies.yaml 获取
    children = []
    levels = cls.get_levels(hierarchy_id)
    for level in levels:
        if level.get('parent_object') == object_type:
            children.append(level.get('object'))
    
    if children:
        return children
    
    # 从 Registry 推导
    from meta.core.models import registry
    entity = registry.get(object_type)
    if entity and entity.associations:
        for assoc in entity.associations:
            if (assoc.get('cardinality') == 'one_to_many' and 
                assoc.get('type') == 'composition'):
                children.append(assoc.get('target_entity'))
    
    return children


@classmethod
def get_cascade_strategy(cls, parent_type: str, child_type: str) -> CascadeStrategy:
    """获取级联策略
    
    优先级：
    1. 优先从 hierarchies.yaml 获取
    2. 如果不存在，则从 Registry 中获取子实体，从 Association 推导
    """
    # 优先从 hierarchies.yaml 获取
    child_level = cls.get_level_by_object(child_type)
    if child_level:
        delete_behavior = child_level.get('delete_behavior', {})
        policy = delete_behavior.get('policy', 'RESTRICT').upper()
        try:
            return CascadeStrategy[policy]
        except KeyError:
            return CascadeStrategy.RESTRICT
    
    # 从 Registry 推导
    from meta.core.models import registry
    entity = registry.get(child_type)
    if entity and entity.associations:
        for assoc in entity.associations:
            if (assoc.get('target_entity') == parent_type and 
                assoc.get('type') == 'composition'):
                # composition 默认 CASCADE
                if assoc.get('cascade_delete', False):
                    return CascadeStrategy.CASCADE
                return CascadeStrategy.RESTRICT
    
    return CascadeStrategy.RESTRICT
```

#### 2.3.2 Checklist

- [ ] 修改 `get_parent_object()` 支持从 Association 推导
- [ ] 修改 `get_foreign_key()` 支持从 Association 推导
- [ ] 修改 `get_child_types()` 支持从 Association 推导
- [ ] 修改 `get_cascade_strategy()` 支持从 Association 推导
- [ ] 添加向后兼容逻辑
- [ ] 添加单元测试

---

### 2.4 拦截器改动

#### 2.4.1 HierarchyValidationInterceptor

**文件**：`meta/core/interceptors/hierarchy_validation_interceptor.py`

**当前代码**（伪代码）：

```python
class HierarchyValidationInterceptor:
    def _validate_update(self, operation):
        object_type = operation.entity_type
        # 硬编码获取 parent_object
        parent_object = HierarchyConfigLoader.get_parent_object(object_type)
        parent_field = HierarchyConfigLoader.get_foreign_key(object_type)
        
        if parent_field and parent_field in operation.changes:
            raise ValidationError(...)
```

**改动后**：

```python
class HierarchyValidationInterceptor:
    def _validate_update(self, operation):
        object_type = operation.entity_type
        
        # 使用新的 HierarchyConfigLoader 方法（自动推导）
        parent_field = HierarchyConfigLoader.get_foreign_key(object_type)
        
        if parent_field and parent_field in operation.changes:
            raise ValidationError(
                f"Cannot change {parent_field}: parent object is immutable"
            )
```

**改动点**：
- 无需改动，因为 `HierarchyConfigLoader` 已经支持自动推导

#### 2.4.2 CascadeInterceptor

**文件**：`meta/core/interceptors/cascade_interceptor.py`

**当前代码**（伪代码）：

```python
class CascadeInterceptor:
    def _cascade_delete_children(self, operation):
        object_type = operation.entity_type
        
        # 硬编码获取 child_types
        children = HierarchyConfigLoader.get_child_types(object_type)
        
        for child_type in children:
            # 执行级联删除
            ...
```

**改动后**：

```python
class CascadeInterceptor:
    def _cascade_delete_children(self, operation):
        object_type = operation.entity_type
        
        # 使用新的 HierarchyConfigLoader 方法（自动推导）
        children = HierarchyConfigLoader.get_child_types(object_type)
        
        for child_type in children:
            # 获取级联策略
            strategy = HierarchyConfigLoader.get_cascade_strategy(object_type, child_type)
            
            if strategy == CascadeStrategy.CASCADE:
                # 执行级联删除
                self._delete_children(object_type, child_type)
            elif strategy == CascadeStrategy.SET_NULL:
                # 执行 SET NULL
                self._set_null_children(object_type, child_type)
            elif strategy == CascadeStrategy.RESTRICT:
                # 检查是否存在子对象
                if self._has_children(object_type, child_type):
                    raise ValidationError(...)
```

**改动点**：
- 无需改动，因为 `HierarchyConfigLoader` 已经支持自动推导

#### 2.4.3 Checklist

- [ ] 验证 HierarchyValidationInterceptor 使用新的 HierarchyConfigLoader
- [ ] 验证 CascadeInterceptor 使用新的 HierarchyConfigLoader
- [ ] 添加集成测试

---

### 2.5 YAML 配置改动

#### 2.5.1 domain.yaml 示例

**当前配置**：

```yaml
name: domain
label: 领域
parent_object: version
hierarchy:
  enabled: true
  hierarchy_id: biz_hierarchy
  level: 2
  parent_field: version_id
  path_field: hierarchy_path
  depth_field: hierarchy_depth
```

**改动后**（新版）：

```yaml
name: domain
label: 领域
aspects:
  - audit_aspect

associations:
  # 父子层级关系
  - name: parent
    label: 父版本
    target_entity: version
    type: composition
    cardinality: many_to_one
    hierarchy: true
    # foreign_key_field 可选，自动推导为 version_id
    
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

# 兼容旧配置（可选，逐步废弃）
# parent_object: version
# hierarchy:
#   enabled: true
#   path_field: hierarchy_path
#   depth_field: hierarchy_depth
```

#### 2.5.2 Checklist

- [ ] 修改 `meta/schemas/domain.yaml`
- [ ] 修改 `meta/schemas/sub_domain.yaml`
- [ ] 修改 `meta/schemas/service_module.yaml`
- [ ] 修改 `meta/schemas/business_object.yaml`
- [ ] 修改 `meta/schemas/version.yaml`
- [ ] 修改 `meta/schemas/product.yaml`
- [ ] 添加向后兼容注释

---

### 2.6 前端 TypeScript 改动

#### 2.6.1 useHierarchyTypes.js

**当前逻辑**：从 API 获取 hierarchies.yaml

**改动方向**：
- 优先从实体元数据获取 associations
- 如果不存在，则回退到 hierarchies.yaml

```javascript
export function useHierarchyTypes() {
  // 获取类型信息
  function getParentType(type) {
    const entity = metaStore.getEntity(type)
    
    // 从 associations 推导
    if (entity?.associations) {
      const parentAssoc = entity.associations.find(a => 
        a.cardinality === 'many_to_one' && a.type === 'composition'
      )
      if (parentAssoc) {
        return parentAssoc.target_entity
      }
    }
    
    // 回退到旧逻辑
    return HIERARCHY_CONFIG[type]?.parent
  }
  
  function getChildType(type) {
    const entity = metaStore.getEntity(type)
    
    // 从 associations 推导
    if (entity?.associations) {
      const childAssoc = entity.associations.find(a => 
        a.cardinality === 'one_to_many' && a.type === 'composition'
      )
      if (childAssoc) {
        return childAssoc.target_entity
      }
    }
    
    // 回退到旧逻辑
    return HIERARCHY_CONFIG[type]?.child
  }
  
  // ...
}
```

#### 2.6.2 Checklist

- [ ] 修改 `useHierarchyTypes.js` 支持从 associations 推导
- [ ] 修改 `useHierarchyList.js` 使用新的推导
- [ ] 修改 `useCascadeSelect.js` 使用新的推导

---

## 三、测试策略

### 3.1 单元测试

#### 3.1.1 yaml_loader 测试

```python
# test_yaml_loader_derivation.py

class TestAssociationDerivation:
    def test_derive_parent_object(self):
        """测试 parent_object 推导"""
        associations = [
            {'name': 'parent', 'type': 'composition', 'cardinality': 'many_to_one', 'target_entity': 'version'},
            {'name': 'sub_domains', 'type': 'composition', 'cardinality': 'one_to_many', 'target_entity': 'sub_domain'}
        ]
        
        loader = YAMLLoader()
        result = loader.derive_parent_object(associations)
        
        assert result == 'version'
    
    def test_derive_foreign_key_field_explicit(self):
        """测试显式 foreign_key_field"""
        associations = [
            {'name': 'parent', 'type': 'composition', 'cardinality': 'many_to_one', 
             'target_entity': 'version', 'foreign_key_field': 'parent_version_id'}
        ]
        
        loader = YAMLLoader()
        result = loader.derive_foreign_key_field(associations)
        
        assert result == 'parent_version_id'
    
    def test_derive_foreign_key_field_auto(self):
        """测试自动推导 foreign_key_field"""
        associations = [
            {'name': 'parent', 'type': 'composition', 'cardinality': 'many_to_one', 
             'target_entity': 'version'}
        ]
        
        loader = YAMLLoader()
        result = loader.derive_foreign_key_field(associations)
        
        assert result == 'version_id'
    
    def test_derive_hierarchy_fields(self):
        """测试 hierarchy_fields 推导"""
        associations = [
            {'name': 'sub_domains', 'type': 'composition', 'cardinality': 'one_to_many', 
             'target_entity': 'sub_domain', 'hierarchy': True}
        ]
        
        loader = YAMLLoader()
        result = loader.derive_hierarchy_fields(associations)
        
        assert result['path_field'] == 'hierarchy_path'
        assert result['depth_field'] == 'hierarchy_depth'
    
    def test_no_hierarchy_derivation(self):
        """测试无层级时推导"""
        associations = [
            {'name': 'roles', 'type': 'association', 'cardinality': 'many_to_many', 
             'target_entity': 'role'}
        ]
        
        loader = YAMLLoader()
        result = loader.derive_hierarchy_fields(associations)
        
        assert result['path_field'] is None
        assert result['depth_field'] is None
```

#### 3.1.2 Checklist

- [ ] 添加 yaml_loader 推导测试
- [ ] 添加 HierarchyConfigLoader 推导测试
- [ ] 添加冲突警告测试

---

## 四、完整 Checklist

### P0: 核心逻辑

| 编号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 1 | 添加 AssociationDefinition 字段 | models.py | ☐ |
| 2 | 新增 derive_parent_object() | yaml_loader.py | ☐ |
| 3 | 新增 derive_foreign_key_field() | yaml_loader.py | ☐ |
| 4 | 新增 derive_hierarchy_fields() | yaml_loader.py | ☐ |
| 5 | 修改 parse_entity() 添加推导 | yaml_loader.py | ☐ |
| 6 | 修改 get_parent_object() | cascade_service.py | ☐ |
| 7 | 修改 get_foreign_key() | cascade_service.py | ☐ |
| 8 | 修改 get_child_types() | cascade_service.py | ☐ |
| 9 | 修改 get_cascade_strategy() | cascade_service.py | ☐ |

### P1: 拦截器改造

| 编号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 10 | 验证 HierarchyValidationInterceptor | hierarchy_validation_interceptor.py | ☐ |
| 11 | 验证 CascadeInterceptor | cascade_interceptor.py | ☐ |

### P2: YAML 配置改造

| 编号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 12 | domain.yaml | meta/schemas/ | ☐ |
| 13 | sub_domain.yaml | meta/schemas/ | ☐ |
| 14 | service_module.yaml | meta/schemas/ | ☐ |
| 15 | business_object.yaml | meta/schemas/ | ☐ |
| 16 | version.yaml | meta/schemas/ | ☐ |
| 17 | product.yaml | meta/schemas/ | ☐ |

### P3: 前端改造

| 编号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 18 | useHierarchyTypes.js | src/composables/ | ☐ |
| 19 | useHierarchyList.js | src/composables/ | ☐ |
| 20 | useCascadeSelect.js | src/composables/ | ☐ |

### P4: 测试

| 编号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 21 | yaml_loader 单元测试 | meta/tests/ | ☐ |
| 22 | HierarchyConfigLoader 单元测试 | meta/tests/ | ☐ |
| 23 | 冲突警告测试 | meta/tests/ | ☐ |
| 24 | 集成测试 | meta/tests/ | ☐ |

---

## 五、风险与缓解

### 5.1 风险列表

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 旧配置不兼容 | 中 | 保持向后兼容，显式配置优先 |
| 循环引用 | 高 | 添加最大深度限制（10层） |
| 配置冲突 | 低 | 输出警告但不阻断 |
| 性能影响 | 低 | 添加缓存机制 |

### 5.2 回滚计划

1. **保留旧配置**：不删除 hierarchies.yaml
2. **显式优先**：显式配置覆盖推导值
3. **灰度发布**：先在小范围试点

---

## 六、时间估算

| 模块 | 任务数 | 估算时间 |
|------|--------|---------|
| P0: 核心逻辑 | 9 | 2 天 |
| P1: 拦截器改造 | 2 | 0.5 天 |
| P2: YAML 配置 | 6 | 1 天 |
| P3: 前端改造 | 3 | 1 天 |
| P4: 测试 | 4 | 1 天 |
| **总计** | **24** | **5.5 天** |

---

## 七、验收标准

### 7.1 功能验收

- [ ] 新的 Association 配置能正确推导 parent_object
- [ ] 新的 Association 配置能正确推导 foreign_key_field
- [ ] 新的 Association 配置能正确推导 path_field 和 depth_field
- [ ] 旧配置仍然正常工作（向后兼容）
- [ ] 冲突时输出警告

### 7.2 集成验收

- [ ] HierarchyService 正常工作
- [ ] CascadeService 正常工作
- [ ] 拦截器正常工作

### 7.3 性能验收

- [ ] 推导逻辑性能无明显影响
- [ ] 无循环引用问题

---

**实现完成**
