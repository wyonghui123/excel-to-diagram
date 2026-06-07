# Virtual Field Query Engine Spec

## Why

当前虚拟字段（如 `category_label`）无法在数据库层面进行排序和过滤，只能通过内存处理，存在以下问题：
1. 大数据量时性能差
2. 分页排序结果不准确（只能对当前页排序）
3. 无法支持虚拟字段作为过滤条件

参考 SAP SADL 的 `sort.transformedBy` 和 `filter.transformedBy` 机制，构建虚拟字段查询引擎。

## What Changes

### Phase 1: Sort Transformation
- 扩展 `SemanticAnnotation` 添加 `sort_transform` 属性
- 扩展 `SemanticAnnotation` 添加 `filter_transform` 属性
- 实现 `VirtualFieldTransformEngine` 处理排序/过滤转换
- 修改 `QueryBuilder` 支持虚拟字段排序转换
- 修改 `query_service.py` 集成转换引擎

### Phase 2: Analytics Query Engine
- 新增 `AnalyticsQueryBuilder` 支持维度/度量查询
- 支持虚拟字段作为分组维度
- 支持聚合函数（COUNT, SUM, AVG, MIN, MAX）
- 生成优化的 SQL 查询

## Impact

- Affected specs: 元模型驱动架构、查询服务
- Affected code:
  - `meta/core/models.py` - SemanticAnnotation 扩展
  - `meta/core/yaml_loader.py` - 解析新属性
  - `meta/core/query_builder.py` - 排序转换支持
  - `meta/services/query_service.py` - 集成转换引擎
  - `meta/schemas/*.yaml` - 元数据声明

---

## ADDED Requirements

### Requirement: Sort Transformation

系统应支持虚拟字段的排序转换，将虚拟字段排序转换为数据库可执行的 SQL 表达式。

#### Scenario: 虚拟字段通过映射字段排序
- **GIVEN** 字段定义了 `sort_transform.by` 属性映射到真实字段
- **WHEN** 用户按虚拟字段排序
- **THEN** 系统将排序转换为映射字段的数据库排序

#### Scenario: 虚拟字段通过 SQL 表达式排序
- **GIVEN** 字段定义了 `sort_transform.sql_expr` 属性
- **WHEN** 用户按虚拟字段排序
- **THEN** 系统将 SQL 表达式注入到 ORDER BY 子句

#### Scenario: 虚拟字段无转换配置
- **GIVEN** 字段未定义 `sort_transform` 属性
- **WHEN** 用户按虚拟字段排序
- **THEN** 系统回退到内存排序（当前实现）

### Requirement: Filter Transformation

系统应支持虚拟字段的过滤转换，将虚拟字段过滤条件转换为数据库可执行的 SQL 条件。

#### Scenario: 虚拟字段通过 SQL 表达式过滤
- **GIVEN** 字段定义了 `filter_transform.sql_expr` 属性
- **WHEN** 用户按虚拟字段过滤
- **THEN** 系统将 SQL 表达式注入到 WHERE 子句

### Requirement: Analytics Query Builder

系统应提供分析查询构建器，支持虚拟字段作为维度进行分组和聚合。

#### Scenario: 虚拟字段作为分组维度
- **GIVEN** 用户需要按虚拟字段分组统计
- **WHEN** 使用 AnalyticsQueryBuilder 指定虚拟字段为维度
- **THEN** 系统生成包含 CASE WHEN 表达式的 GROUP BY 查询

#### Scenario: 聚合查询
- **GIVEN** 用户需要对数据进行聚合统计
- **WHEN** 使用 AnalyticsQueryBuilder 指定度量和聚合函数
- **THEN** 系统生成正确的聚合查询 SQL

---

## Technical Design

### 1. 元数据扩展

```yaml
# relationship.yaml
- id: category_label
  storage: virtual
  semantics:
    computed_by: hierarchy_scope
    sort_transform:
      by: category_type                    # 方案A: 映射到已有字段
      # 或
      sql_expr: |                          # 方案B: SQL 表达式
        CASE 
          WHEN source_domain_id != target_domain_id THEN 1
          WHEN source_sub_domain_id != target_sub_domain_id THEN 2
          WHEN source_service_module_id != target_service_module_id THEN 3
          ELSE 4
        END
    filter_transform:
      sql_expr: |                          # 过滤转换
        CASE 
          WHEN source_domain_id != target_domain_id THEN '跨领域'
          WHEN source_sub_domain_id != target_sub_domain_id THEN '同领域跨子领域'
          WHEN source_service_module_id != target_service_module_id THEN '同子领域跨服务模块'
          ELSE '同服务模块'
        END
```

### 2. SemanticAnnotation 扩展

```python
@dataclass
class SemanticAnnotation:
    # ... 现有字段 ...
    computed_by: str = ""
    
    # 新增
    sort_transform: Dict[str, Any] = field(default_factory=dict)
    filter_transform: Dict[str, Any] = field(default_factory=dict)
```

### 3. VirtualFieldTransformEngine

```python
class VirtualFieldTransformEngine:
    """虚拟字段转换引擎
    
    参考 SAP SADL 的 IF_SADL_EXIT_SORT_TRANSFORM 机制
    """
    
    def transform_sort(self, meta_obj: MetaObject, field_id: str, direction: str) -> Optional[str]:
        """将虚拟字段排序转换为 SQL ORDER BY 表达式"""
        
    def transform_filter(self, meta_obj: MetaObject, field_id: str, operator: str, value: Any) -> Optional[str]:
        """将虚拟字段过滤转换为 SQL WHERE 条件"""
```

### 4. QueryBuilder 集成

```python
class QueryBuilder:
    def order_by(self, field: str, direction: str = "asc") -> "QueryBuilder":
        field_meta = self.meta_object.get_field(field)
        
        if field_meta.storage == FieldStorage.VIRTUAL:
            transform = self._transform_engine.transform_sort(
                self.meta_object, field, direction
            )
            if transform:
                # 使用转换后的 SQL 表达式
                self._spec.sort_expressions.append(transform)
                return self
        
        # 原有逻辑
        self._spec.sorts.append((field, direction))
        return self
```

### 5. AnalyticsQueryBuilder

```python
class AnalyticsQueryBuilder:
    """分析查询构建器
    
    支持虚拟字段作为维度的分组聚合查询
    """
    
    def dimension(self, field: str, alias: str = None) -> "AnalyticsQueryBuilder":
        """添加维度字段"""
        
    def measure(self, field: str, aggregation: str, alias: str = None) -> "AnalyticsQueryBuilder":
        """添加度量字段"""
        
    def build(self) -> str:
        """生成分析查询 SQL"""
```

---

## SQLite 兼容性

所有功能基于 SQLite 3.50.4 验证：

| 功能 | SQLite 支持 | 使用场景 |
|------|-------------|----------|
| CASE WHEN | ✅ | 排序/过滤转换表达式 |
| ORDER BY 表达式 | ✅ | 虚拟字段排序 |
| GROUP BY 表达式 | ✅ | 虚拟字段分组 |
| 窗口函数 | ✅ | 高级分析查询 |
| CTE (WITH) | ✅ | 复杂查询优化 |

---

## Performance Considerations

### 索引要求

虚拟字段排序/过滤依赖 JOIN 字段索引：

```sql
CREATE INDEX idx_bo_service_module ON business_objects(service_module_id);
CREATE INDEX idx_sm_sub_domain ON service_modules(sub_domain_id);
CREATE INDEX idx_sd_domain ON sub_domains(domain_id);
```

### 查询优化

1. **Sort Transform 优先于内存排序**
2. **Filter Transform 下推到数据库**
3. **大数据量使用分页 + 索引**
