# 元模型驱动的过滤系统 Spec

> **创建日期**: 2026-05-07
> **相关Spec**: metadata-driven-refactoring, p0-meta-model-core-enhancement
> **参考**: SAP One Domain Model, Salesforce System Dictionary, ServiceNow Dictionary

---

## 一、Why

### 问题背景

当前系统中存在以下问题：

1. **过滤字段硬编码** - 前端代码中直接写死 `created_by`、`updated_at` 等字段名，不符合元模型驱动原则
2. **全局与局部过滤混淆** - 没有明确区分全局过滤（作用于所有列表）和局部过滤（仅作用于特定视图）
3. **扩展性差** - 新增过滤字段需要修改前后端代码，无法通过配置实现
4. **类型不安全** - 过滤参数没有类型检查，容易出错
5. **缺乏持久化** - 过滤条件无法保存和共享

### 目标

构建一个**元模型驱动的过滤系统**，参考SAP、Salesforce、ServiceNow等头部产品的最佳实践：

- ✅ 全局过滤（作用于所有对象列表）
- ✅ 局部过滤（作用于特定视图或子列表）
- ✅ 从元模型定义自动生成过滤组件
- ✅ 类型安全的过滤参数传递
- ✅ 过滤条件持久化和共享
- ✅ 过滤逻辑组合（AND/OR）

---

## 二、行业最佳实践参考

### 2.1 SAP One Domain Model

**核心设计**：
- **CDS View注解系统** - 使用 `@Consumption.filter` 定义可过滤字段
- **UI.SelectionFields** - 定义UI层面的过滤字段
- **自动推断** - 根据字段类型自动推断过滤组件
- **作用域管理** - 支持全局过滤和局部过滤

**示例**：
```abap
@UI.selectionField: [ { position: 10 } ]
Created_at,

@Consumption.filter: { selectionType: #INTERVAL }
Created_by,
```

### 2.2 Salesforce List View

**核心设计**：
- **System Dictionary** - 定义所有字段元数据
- **动态过滤** - 过滤字段从字段定义中动态获取
- **过滤逻辑** - 支持复杂逻辑组合（AND/OR）
- **持久化** - 支持过滤条件保存和共享

**示例**：
```xml
<ListView>
  <filterScope>Mine</filterScope>
  <filters>
    <field>CREATED_DATE</field>
    <operation>equals</operation>
    <value>THIS_WEEK</value>
  </filters>
</ListView>
```

### 2.3 ServiceNow System Dictionary

**核心设计**：
- **sys_dictionary表** - 存储所有字段定义
- **动态生成** - 过滤组件从元数据动态生成
- **引用限定符** - 支持字段关联过滤
- **类型推断** - 根据字段类型自动推断过滤方式

**示例**：
```xml
<dictionary>
  <element name="created_on" type="glide_date_time">
    <attributes>
      <attribute name="filterable">true</attribute>
      <attribute name="filter_type">date_range</attribute>
    </attributes>
  </element>
</dictionary>
```

### 2.4 共同特点总结

| 特性 | SAP | Salesforce | ServiceNow | 我们的方案 |
|------|-----|-----------|-----------|----------|
| **元数据驱动** | ✅ CDS注解 | ✅ Dictionary | ✅ Dictionary | ✅ YAML定义 |
| **声明式配置** | ✅ 注解 | ✅ XML | ✅ XML | ✅ YAML |
| **自动推断** | ✅ 字段类型 | ✅ 字段类型 | ✅ 字段类型 | ✅ 字段类型 |
| **作用域管理** | ✅ Global/Local | ✅ Scope | ✅ View | ✅ Scope |
| **持久化** | ✅ Variant | ✅ List View | ✅ Filter | ✅ Variant |
| **逻辑组合** | ✅ AND/OR | ✅ AND/OR | ✅ AND/OR | ✅ AND/OR |

---

## 三、What Changes

### 核心概念

#### 1. **过滤字段定义层级**

```
┌─────────────────────────────────────────────────────────┐
│  元模型层 (Meta Model Layer)                            │
│  - 字段语义定义 (semantics.filterable)                  │
│  - 过滤类型推断 (filter_type: date/user/enum/text)     │
│  - 过滤配置 (filter_label, filter_options)             │
│  - 过滤作用域 (filter_scope: global/local/both)       │
│  - 过滤默认值 (filter_default)                         │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  视图层 (View Layer)                                    │
│  - 全局过滤配置 (global_filters)                        │
│  - 局部过滤配置 (local_filters)                         │
│  - 过滤变体管理 (filter_variants)                       │
│  - 过滤逻辑组合 (filter_logic)                          │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  组件层 (Component Layer)                               │
│  - 动态渲染过滤组件                                     │
│  - 自动类型转换和验证                                   │
│  - 过滤条件状态管理                                     │
│  - 过滤变体保存和加载                                   │
└─────────────────────────────────────────────────────────┘
```

#### 2. **全局过滤 vs 局部过滤**

| 特性 | 全局过滤 (Global Filters) | 局部过滤 (Local Filters) |
|------|-------------------------|------------------------|
| **作用范围** | 所有对象列表 | 特定视图或子列表 |
| **显示位置** | 顶部工具栏 | 视图内部或侧边栏 |
| **生命周期** | 跨页面持久化 | 仅当前视图有效 |
| **示例** | 创建时间、创建人 | 对象详情页的关系过滤 |
| **存储方式** | URL参数或全局状态 | 组件内部状态 |
| **持久化** | 支持保存为变体 | 不支持持久化 |
| **共享** | 支持共享给其他用户 | 不支持共享 |

#### 3. **适用场景**

**全局过滤适用场景**：
- ✅ 架构数据管理的主列表（领域、子领域、服务模块、业务对象）
- ✅ 关系列表
- ✅ 标注列表
- ❌ 对象树（左侧导航树）
- ❌ 关系树

**局部过滤适用场景**：
- ✅ 对象详情页中的关系子列表
- ✅ 业务对象详情页的标注列表
- ✅ 版本对比视图的差异列表
- ✅ 导出对话框中的数据预览列表

---

## 四、Impact

### 受影响的Spec
- `metadata-driven-refactoring` - 需要扩展元模型定义
- `p0-meta-model-core-enhancement` - 需要添加过滤语义
- `unified-meta-model-design` - 需要统一过滤字段定义

### 受影响的代码

**前端**：
- `src/views/ArchDataManageApp/index.vue` - 全局过滤UI
- `src/components/common/DynamicView.vue` - 过滤参数传递
- `src/composables/useGlobalFilters.js` - 新增：全局过滤状态管理
- `src/composables/useLocalFilters.js` - 新增：局部过滤状态管理
- `src/components/common/FilterVariantManager.vue` - 新增：过滤变体管理

**后端**：
- `meta/core/models.py` - 元模型字段定义扩展
- `meta/services/query_service.py` - 过滤条件构建
- `meta/api/query_api.py` - 过滤参数解析

**元模型定义**：
- `meta/schemas/domain.yaml` - 添加过滤语义
- `meta/schemas/sub_domain.yaml` - 添加过滤语义
- `meta/schemas/service_module.yaml` - 添加过滤语义
- `meta/schemas/business_object.yaml` - 添加过滤语义

---

## 四、ADDED Requirements

### Requirement: 元模型过滤字段定义

系统**应当**在元模型中定义字段的过滤语义。

#### Scenario: 日期范围过滤
- **GIVEN** 元模型字段 `created_at` 定义了 `semantics.filterable: true` 和 `filter_type: date`
- **WHEN** 前端渲染全局过滤组件
- **THEN** 自动生成日期范围选择器（起止日期）

#### Scenario: 用户过滤
- **GIVEN** 元模型字段 `created_by` 定义了 `semantics.filterable: true` 和 `filter_type: user`
- **WHEN** 前端渲染全局过滤组件
- **THEN** 自动生成用户输入框（支持模糊匹配）

#### Scenario: 枚举过滤
- **GIVEN** 元模型字段 `status` 定义了 `semantics.filterable: true` 和 `filter_type: enum`
- **WHEN** 前端渲染全局过滤组件
- **THEN** 自动生成下拉选择框（选项从 `filter_options` 获取）

---

### Requirement: 全局过滤状态管理

系统**应当**提供全局过滤状态管理功能。

#### Scenario: 全局过滤持久化
- **GIVEN** 用户在架构数据管理页面设置了全局过滤条件
- **WHEN** 用户切换到不同的对象类型（如从领域切换到子领域）
- **THEN** 全局过滤条件保持不变并继续生效

#### Scenario: 全局过滤清除
- **GIVEN** 用户设置了全局过滤条件
- **WHEN** 用户点击"清除过滤"按钮
- **THEN** 所有全局过滤条件被重置，列表恢复显示全部数据

---

### Requirement: 局部过滤作用域隔离

系统**应当**确保局部过滤仅作用于特定视图。

#### Scenario: 局部过滤不影响全局
- **GIVEN** 用户在对象详情页的关系列表中设置了局部过滤
- **WHEN** 用户返回主列表页面
- **THEN** 主列表不受局部过滤影响

#### Scenario: 多个局部过滤独立
- **GIVEN** 用户在业务对象A的详情页设置了关系过滤
- **WHEN** 用户切换到业务对象B的详情页
- **THEN** 业务对象B的关系列表使用独立的过滤条件

---

### Requirement: 过滤参数自动构建

系统**应当**根据元模型定义自动构建过滤参数。

#### Scenario: 日期范围过滤参数
- **GIVEN** 用户选择了创建时间范围 `2024-01-01` 到 `2024-12-31`
- **WHEN** 前端发送查询请求
- **THEN** 自动生成 `created_time_from=2024-01-01&created_time_to=2024-12-31` 参数

#### Scenario: 用户模糊匹配参数
- **GIVEN** 用户输入创建人 "张三"
- **WHEN** 前端发送查询请求
- **THEN** 自动生成 `created_by=张三` 参数，后端使用 `LIKE '%张三%'` 查询

---

### Requirement: 过滤变体管理

系统**应当**支持过滤条件的保存、加载和共享。

#### Scenario: 保存过滤变体
- **GIVEN** 用户设置了复杂的全局过滤条件
- **WHEN** 用户点击"保存为变体"按钮并输入名称
- **THEN** 过滤条件被保存到数据库，可以在下次使用时快速加载

#### Scenario: 加载过滤变体
- **GIVEN** 用户之前保存了过滤变体"本周创建的数据"
- **WHEN** 用户从变体列表中选择该变体
- **THEN** 过滤条件自动应用，列表显示符合条件的数据

#### Scenario: 共享过滤变体
- **GIVEN** 用户保存了过滤变体
- **WHEN** 用户将变体设置为"共享"并选择共享对象
- **THEN** 其他用户可以在自己的变体列表中看到并使用该变体

---

### Requirement: 过滤逻辑组合

系统**应当**支持复杂的过滤逻辑组合。

#### Scenario: AND逻辑组合
- **GIVEN** 用户设置了两个过滤条件：创建时间范围和创建人
- **WHEN** 用户选择"AND"逻辑
- **THEN** 列表显示同时满足两个条件的数据

#### Scenario: OR逻辑组合
- **GIVEN** 用户设置了两个过滤条件：状态为"启用"或状态为"待审核"
- **WHEN** 用户选择"OR"逻辑
- **THEN** 列表显示满足任一条件的数据

#### Scenario: 复杂逻辑组合
- **GIVEN** 用户需要设置复杂过滤条件：(创建时间在本周 AND 创建人为张三) OR (状态为紧急)
- **WHEN** 用户使用高级过滤编辑器
- **THEN** 系统正确解析并应用复杂逻辑

---

## 五、MODIFIED Requirements

### Requirement: 元模型字段语义扩展

**原需求**: 元模型字段支持 `display_name`、`required` 等基本语义

**修改后**: 元模型字段**应当**支持以下过滤相关语义（参考SAP CDS注解）：

```yaml
fields:
  - id: created_at
    name: 创建时间
    type: datetime
    semantics:
      display_name: 创建时间
      filterable: true              # @Consumption.filter
      filter_type: date             # selectionType: #INTERVAL
      filter_label: 创建时间        # @EndUserText.label
      filter_placeholder: 选择日期范围
      filter_default: null          # defaultValue
      filter_scope: global          # scope: #GLOBAL
      filter_mandatory: false       # @Consumption.filter.mandatory

  - id: created_by
    name: 创建人
    type: string
    semantics:
      display_name: 创建人
      filterable: true
      filter_type: user
      filter_label: 创建人
      filter_placeholder: 输入用户名
      filter_scope: global
      filter_operator: like         # 默认操作符

  - id: status
    name: 状态
    type: string
    semantics:
      display_name: 状态
      filterable: true
      filter_type: enum
      filter_label: 状态
      filter_options:               # valueList
        - value: active
          label: 启用
        - value: inactive
          label: 禁用
      filter_scope: local           # 仅局部过滤
      filter_default: active
```

**对比SAP CDS注解**：

| 我们的YAML | SAP CDS注解 | 说明 |
|-----------|------------|------|
| `filterable: true` | `@Consumption.filter` | 是否可过滤 |
| `filter_type: date` | `selectionType: #INTERVAL` | 过滤类型 |
| `filter_label` | `@EndUserText.label` | 显示标签 |
| `filter_scope: global` | `scope: #GLOBAL` | 作用域 |
| `filter_mandatory` | `@Consumption.filter.mandatory` | 是否必填 |
| `filter_options` | `valueList` | 枚举值列表 |

---

## 六、REMOVED Requirements

无移除的需求。

---

## 七、技术方案

### 7.1 元模型定义扩展

**参考SAP CDS View注解系统**：

```python
# meta/core/models.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal

@dataclass
class FilterOption:
    """过滤选项（枚举值）"""
    value: str
    label: str

@dataclass
class FieldSemantics:
    """字段语义定义"""
    display_name: Optional[str] = None
    filterable: bool = False                    # @Consumption.filter
    filter_type: Literal['date', 'user', 'enum', 'text', 'foreign_key'] = 'text'
    filter_label: Optional[str] = None          # @EndUserText.label
    filter_placeholder: Optional[str] = None
    filter_default: Optional[str] = None
    filter_scope: Literal['global', 'local', 'both'] = 'both'
    filter_options: List[FilterOption] = field(default_factory=list)
    filter_mandatory: bool = False              # @Consumption.filter.mandatory
    filter_operator: str = 'eq'                 # 默认操作符
```

### 7.2 前端实现

#### 全局过滤状态管理 (`useGlobalFilters.js`)

**参考SAP Fiori Elements SmartFilterBar**：

```javascript
import { ref, computed } from 'vue'
import { registry } from '@/meta/registry'

export function useGlobalFilters(objectType) {
  // 从元模型获取可过滤字段（类似SAP的UI.SelectionFields）
  const filterableFields = computed(() => {
    const metaObj = registry.get(objectType)
    if (!metaObj) return []
    
    return metaObj.fields
      .filter(f => f.semantics?.filterable && f.semantics?.filter_scope !== 'local')
      .map(f => ({
        id: f.id,
        label: f.semantics.filter_label || f.semantics.display_name || f.name,
        type: f.semantics.filter_type || 'text',
        options: f.semantics.filter_options || [],
        placeholder: f.semantics.filter_placeholder || '',
        mandatory: f.semantics.filter_mandatory || false,
        default: f.semantics.filter_default
      }))
  })
  
  // 全局过滤状态（持久化到URL或localStorage）
  const globalFilters = ref({})
  
  // 过滤变体管理（类似SAP的Variant Management）
  const filterVariants = ref([])
  
  // 应用过滤
  function applyFilters() {
    // 触发列表刷新
  }
  
  // 清除过滤
  function clearFilters() {
    globalFilters.value = {}
    applyFilters()
  }
  
  // 保存过滤变体
  function saveVariant(name, isShared = false) {
    // 保存到数据库
  }
  
  // 加载过滤变体
  function loadVariant(variantId) {
    // 从数据库加载
  }
  
  return {
    filterableFields,
    globalFilters,
    filterVariants,
    applyFilters,
    clearFilters,
    saveVariant,
    loadVariant
  }
}
```

### 7.3 后端实现

#### 过滤条件构建服务 (`filter_service.py`)

**参考SAP SADL框架**：

```python
from meta.core.models import MetaObject, registry
from typing import List, Dict, Literal

@dataclass
class QueryCondition:
    """查询条件"""
    field: str
    operator: Literal['eq', 'ne', 'gt', 'lt', 'ge', 'le', 'like', 'in']
    value: any
    logic: Literal['AND', 'OR'] = 'AND'

def build_filters_from_meta(
    meta_obj: MetaObject, 
    params: dict, 
    scope: str = 'global'
) -> List[QueryCondition]:
    """
    从元模型定义和请求参数构建过滤条件
    类似SAP SADL的自动过滤构建
    """
    conditions = []
    
    for field in meta_obj.fields:
        if not hasattr(field, 'semantics') or not field.semantics:
            continue
        
        semantics = field.semantics
        
        # 检查是否可过滤（@Consumption.filter）
        if not getattr(semantics, 'filterable', False):
            continue
        
        # 检查作用域
        filter_scope = getattr(semantics, 'filter_scope', 'both')
        if scope == 'global' and filter_scope == 'local':
            continue
        if scope == 'local' and filter_scope == 'global':
            continue
        
        # 根据过滤类型构建条件（selectionType）
        filter_type = getattr(semantics, 'filter_type', 'text')
        
        if filter_type == 'date':
            # 日期范围过滤（#INTERVAL）
            from_key = f"{field.id}_from"
            to_key = f"{field.id}_to"
            
            if from_key in params and params[from_key]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='ge',
                    value=params[from_key]
                ))
            
            if to_key in params and params[to_key]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='le',
                    value=params[to_key]
                ))
        
        elif filter_type == 'user':
            # 用户模糊匹配
            if field.id in params and params[field.id]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='like',
                    value=f"%{params[field.id]}%"
                ))
        
        elif filter_type == 'enum':
            # 枚举精确匹配
            if field.id in params and params[field.id]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='eq',
                    value=params[field.id]
                ))
    
    return conditions
```

---

## 八、实施计划

### Phase 1: 元模型定义扩展（1天）
- 扩展元模型字段语义定义（参考SAP CDS注解）
- 为现有字段添加过滤配置
- 编写元模型验证测试

### Phase 2: 前端过滤组件（2天）
- 实现 `useGlobalFilters` 和 `useLocalFilters`
- 创建动态过滤组件（参考SAP SmartFilterBar）
- 实现过滤变体管理

### Phase 3: 后端过滤服务（1天）
- 实现 `filter_service.py`（参考SAP SADL）
- 集成到 `query_service.py`
- 编写过滤条件构建测试

### Phase 4: 局部过滤应用（1天）
- 为对象详情页添加局部过滤
- 为关系子列表添加局部过滤
- 测试作用域隔离

### Phase 5: 过滤变体和逻辑组合（2天）
- 实现过滤变体保存和加载
- 实现过滤逻辑组合（AND/OR）
- 实现高级过滤编辑器

---

## 九、验收标准

### 功能验收
- [ ] 全局过滤在所有对象列表中生效
- [ ] 局部过滤仅在特定视图中生效
- [ ] 过滤条件可以正确清除
- [ ] 过滤参数正确传递到后端
- [ ] 过滤变体可以保存、加载和共享
- [ ] 过滤逻辑组合正确工作

### 元模型驱动验收
- [ ] 过滤字段从元模型定义中获取
- [ ] 新增过滤字段无需修改代码
- [ ] 过滤类型自动推断正确
- [ ] 符合SAP CDS注解规范

### 性能验收
- [ ] 过滤条件构建时间 < 50ms
- [ ] 前端渲染过滤组件时间 < 100ms

---

## 十、风险与缓解

### 风险1: 过滤字段过多导致UI拥挤
**缓解措施**:
- 支持过滤字段折叠/展开（参考SAP Fiori）
- 支持自定义显示的过滤字段
- 使用标签页分组过滤字段

### 风险2: 全局过滤与局部过滤冲突
**缓解措施**:
- 明确作用域定义
- 提供过滤条件预览
- 支持过滤条件合并策略配置

### 风险3: 后端查询性能下降
**缓解措施**:
- 为常用过滤字段添加索引
- 使用查询缓存
- 限制过滤条件数量

---

## 十一、参考资料

- SAP S/4HANA CDS View Annotations
- SAP Fiori Elements SmartFilterBar
- SAP Variant Management
- Salesforce System Dictionary
- ServiceNow sys_dictionary
- 用友BIP 元模型驱动架构
- `metadata-driven-refactoring` spec
      filter_placeholder: 输入用户名
      filter_scope: global

  - id: status
    name: 状态
    type: string
    semantics:
      display_name: 状态
      filterable: true
      filter_type: enum
      filter_label: 状态
      filter_options:               # 枚举选项
        - value: active
          label: 启用
        - value: inactive
          label: 禁用
      filter_scope: local           # 仅局部过滤
```

---

## 六、REMOVED Requirements

无移除的需求。

---

## 七、技术方案

### 7.1 前端实现

#### 全局过滤状态管理 (`useGlobalFilters.js`)

```javascript
import { ref, computed } from 'vue'
import { registry } from '@/meta/registry'

export function useGlobalFilters(objectType) {
  // 从元模型获取可过滤字段
  const filterableFields = computed(() => {
    const metaObj = registry.get(objectType)
    if (!metaObj) return []
    
    return metaObj.fields
      .filter(f => f.semantics?.filterable && f.semantics?.filter_scope !== 'local')
      .map(f => ({
        id: f.id,
        label: f.semantics.filter_label || f.semantics.display_name || f.name,
        type: f.semantics.filter_type || 'text',
        options: f.semantics.filter_options || [],
        placeholder: f.semantics.filter_placeholder || ''
      }))
  })
  
  // 全局过滤状态（持久化到URL或localStorage）
  const globalFilters = ref({})
  
  // 应用过滤
  function applyFilters() {
    // 触发列表刷新
  }
  
  // 清除过滤
  function clearFilters() {
    globalFilters.value = {}
    applyFilters()
  }
  
  return {
    filterableFields,
    globalFilters,
    applyFilters,
    clearFilters
  }
}
```

#### 局部过滤状态管理 (`useLocalFilters.js`)

```javascript
import { ref, computed } from 'vue'
import { registry } from '@/meta/registry'

export function useLocalFilters(objectType, viewId) {
  // 从元模型获取可过滤字段（包括局部过滤字段）
  const filterableFields = computed(() => {
    const metaObj = registry.get(objectType)
    if (!metaObj) return []
    
    return metaObj.fields
      .filter(f => f.semantics?.filterable && f.semantics?.filter_scope !== 'global')
      .map(f => ({
        id: f.id,
        label: f.semantics.filter_label || f.semantics.display_name || f.name,
        type: f.semantics.filter_type || 'text',
        options: f.semantics.filter_options || [],
        placeholder: f.semantics.filter_placeholder || ''
      }))
  })
  
  // 局部过滤状态（仅组件内部）
  const localFilters = ref({})
  
  return {
    filterableFields,
    localFilters
  }
}
```

### 7.2 后端实现

#### 过滤条件构建服务 (`filter_service.py`)

```python
from meta.core.models import MetaObject, registry

def build_filters_from_meta(meta_obj: MetaObject, params: dict, scope: str = 'global') -> List[QueryCondition]:
    """从元模型定义和请求参数构建过滤条件"""
    conditions = []
    
    for field in meta_obj.fields:
        if not hasattr(field, 'semantics') or not field.semantics:
            continue
        
        semantics = field.semantics
        
        # 检查是否可过滤
        if not getattr(semantics, 'filterable', False):
            continue
        
        # 检查作用域
        filter_scope = getattr(semantics, 'filter_scope', 'both')
        if scope == 'global' and filter_scope == 'local':
            continue
        if scope == 'local' and filter_scope == 'global':
            continue
        
        # 根据过滤类型构建条件
        filter_type = getattr(semantics, 'filter_type', 'text')
        
        if filter_type == 'date':
            # 日期范围过滤
            from_key = f"{field.id}_from"
            to_key = f"{field.id}_to"
            
            if from_key in params and params[from_key]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='>=',
                    value=params[from_key]
                ))
            
            if to_key in params and params[to_key]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='<=',
                    value=params[to_key]
                ))
        
        elif filter_type == 'user':
            # 用户模糊匹配
            if field.id in params and params[field.id]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='like',
                    value=f"%{params[field.id]}%"
                ))
        
        elif filter_type == 'enum':
            # 枚举精确匹配
            if field.id in params and params[field.id]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='eq',
                    value=params[field.id]
                ))
        
        elif filter_type == 'foreign_key':
            # 外键关联过滤
            if field.id in params and params[field.id]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='eq',
                    value=params[field.id]
                ))
        
        else:
            # 文本模糊匹配
            if field.id in params and params[field.id]:
                conditions.append(QueryCondition(
                    field=field.db_column,
                    operator='like',
                    value=f"%{params[field.id]}%"
                ))
    
    return conditions
```

---

## 八、实施计划

### Phase 1: 元模型定义扩展（1天）
- 扩展元模型字段语义定义
- 为现有字段添加过滤配置
- 编写元模型验证测试

### Phase 2: 前端过滤组件（2天）
- 实现 `useGlobalFilters` 和 `useLocalFilters`
- 创建动态过滤组件
- 集成到架构数据管理页面

### Phase 3: 后端过滤服务（1天）
- 实现 `filter_service.py`
- 集成到 `query_service.py`
- 编写过滤条件构建测试

### Phase 4: 局部过滤应用（1天）
- 为对象详情页添加局部过滤
- 为关系子列表添加局部过滤
- 测试作用域隔离

---

## 九、验收标准

### 功能验收
- [ ] 全局过滤在所有对象列表中生效
- [ ] 局部过滤仅在特定视图中生效
- [ ] 过滤条件可以正确清除
- [ ] 过滤参数正确传递到后端

### 元模型驱动验收
- [ ] 过滤字段从元模型定义中获取
- [ ] 新增过滤字段无需修改代码
- [ ] 过滤类型自动推断正确

### 性能验收
- [ ] 过滤条件构建时间 < 50ms
- [ ] 前端渲染过滤组件时间 < 100ms

---

## 十、风险与缓解

### 风险1: 过滤字段过多导致UI拥挤
**缓解措施**:
- 支持过滤字段折叠/展开
- 支持自定义显示的过滤字段
- 使用标签页分组过滤字段

### 风险2: 全局过滤与局部过滤冲突
**缓解措施**:
- 明确作用域定义
- 提供过滤条件预览
- 支持过滤条件合并策略配置

### 风险3: 后端查询性能下降
**缓解措施**:
- 为常用过滤字段添加索引
- 使用查询缓存
- 限制过滤条件数量

---

## 十一、参考资料

- SAP S/4HANA CDS View Annotations
- SAP Fiori Elements Filter Bar
- 用友BIP 元模型驱动架构
- `metadata-driven-refactoring` spec
