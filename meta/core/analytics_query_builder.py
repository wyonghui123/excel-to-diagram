"""分析查询构建器

支持虚拟字段作为维度的分组聚合查询。
参考 SAP SADL 的分析查询能力设计。

核心功能：
1. 支持物理字段和虚拟字段作为维度
2. 支持多种聚合函数（COUNT, SUM, AVG, MIN, MAX）
3. 自动处理虚拟字段的 SQL 表达式转换
4. 生成优化的 GROUP BY 查询

示例：
    builder = AnalyticsQueryBuilder(ds, meta_obj)
    result = builder \
        .dimension('category_label') \
        .dimension('relation_code') \
        .measure('id', 'COUNT', 'count') \
        .filter('relation_code', 'eq', 'CALLS') \
        .execute()
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DimensionSpec:
    """维度规格"""
    field_id: str
    alias: Optional[str] = None
    sql_expr: Optional[str] = None
    is_virtual: bool = False


@dataclass
class MeasureSpec:
    """度量规格"""
    field_id: str
    aggregation: str  # COUNT, SUM, AVG, MIN, MAX
    alias: Optional[str] = None


@dataclass
class AnalyticsQuerySpec:
    """分析查询规格"""
    table_name: str
    dimensions: List[DimensionSpec] = field(default_factory=list)
    measures: List[MeasureSpec] = field(default_factory=list)
    filters: List[Tuple[str, str, Any]] = field(default_factory=list)
    joins: List[str] = field(default_factory=list)
    order_by: List[Tuple[str, str]] = field(default_factory=list)
    limit: int = 0


class AnalyticsQueryBuilder:
    """分析查询构建器
    
    支持虚拟字段作为维度的分组聚合查询。
    
    示例:
        builder = AnalyticsQueryBuilder(ds, meta_obj)
        result = builder \
            .dimension('category_label') \
            .measure('id', 'COUNT', 'count') \
            .execute()
    """
    
    VALID_AGGREGATIONS = ('COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COUNT_DISTINCT')
    
    def __init__(self, data_source, meta_object):
        self.ds = data_source
        self.meta_object = meta_object
        self._spec = AnalyticsQuerySpec(table_name=meta_object.table_name)
        self._join_tables = set()
        self._field_map = {f.id: f for f in meta_object.fields} if meta_object else {}
    
    def dimension(self, field_id: str, alias: Optional[str] = None) -> "AnalyticsQueryBuilder":
        """添加维度字段
        
        支持物理字段和虚拟字段。虚拟字段会自动转换为其 SQL 表达式。
        
        Args:
            field_id: 字段ID
            alias: 别名（可选）
            
        Returns:
            self（支持链式调用）
        """
        field = self._field_map.get(field_id)
        
        if not field:
            logger.warning(f"[AnalyticsBuilder] Field '{field_id}' not found")
            return self
        
        from meta.core.models import FieldStorage
        storage = getattr(field, 'storage', None)
        is_virtual = storage == FieldStorage.VIRTUAL
        
        sql_expr = None
        if is_virtual:
            semantics = getattr(field, 'semantics', None)
            if semantics:
                filter_transform = getattr(semantics, 'filter_transform', None)
                if filter_transform and 'sql_expr' in filter_transform:
                    sql_expr = filter_transform['sql_expr'].strip()
                    self._add_required_joins_for_virtual_field(field_id)
        
        dim = DimensionSpec(
            field_id=field_id,
            alias=alias or field_id,
            sql_expr=sql_expr,
            is_virtual=is_virtual
        )
        self._spec.dimensions.append(dim)
        
        return self
    
    def measure(self, field_id: str, aggregation: str, alias: Optional[str] = None) -> "AnalyticsQueryBuilder":
        """添加度量字段
        
        Args:
            field_id: 字段ID
            aggregation: 聚合函数（COUNT, SUM, AVG, MIN, MAX, COUNT_DISTINCT）
            alias: 别名（可选）
            
        Returns:
            self（支持链式调用）
        """
        aggregation = aggregation.upper()
        if aggregation not in self.VALID_AGGREGATIONS:
            logger.warning(f"[AnalyticsBuilder] Invalid aggregation: {aggregation}")
            return self
        
        measure = MeasureSpec(
            field_id=field_id,
            aggregation=aggregation,
            alias=alias or f"{aggregation.lower()}_{field_id}"
        )
        self._spec.measures.append(measure)
        
        return self
    
    def filter(self, field_id: str, operator: str, value: Any) -> "AnalyticsQueryBuilder":
        """添加过滤条件
        
        Args:
            field_id: 字段ID
            operator: 操作符（eq, ne, gt, lt, gte, lte, like, in）
            value: 过滤值
            
        Returns:
            self（支持链式调用）
        """
        self._spec.filters.append((field_id, operator, value))
        return self
    
    def order_by(self, field: str, direction: str = "asc") -> "AnalyticsQueryBuilder":
        """添加排序
        
        Args:
            field: 字段名或别名
            direction: 排序方向（asc/desc）
            
        Returns:
            self（支持链式调用）
        """
        self._spec.order_by.append((field, direction.lower()))
        return self
    
    def limit(self, limit: int) -> "AnalyticsQueryBuilder":
        """限制返回数量
        
        Args:
            limit: 最大返回数量
            
        Returns:
            self（支持链式调用）
        """
        self._spec.limit = limit
        return self
    
    def _add_required_joins_for_virtual_field(self, field_id: str):
        """为虚拟字段添加必要的 JOIN 表"""
        if field_id in ('category_label', 'category_type'):
            self._join_tables.add('business_objects_source')
            self._join_tables.add('business_objects_target')
            self._join_tables.add('service_modules_source')
            self._join_tables.add('service_modules_target')
            self._join_tables.add('sub_domains_source')
            self._join_tables.add('sub_domains_target')
    
    def _build_join_clause(self) -> str:
        """构建 JOIN 子句"""
        joins = []
        
        if 'business_objects_source' in self._join_tables:
            joins.append("LEFT JOIN business_objects bo1 ON r.source_bo_id = bo1.id")
        if 'business_objects_target' in self._join_tables:
            joins.append("LEFT JOIN business_objects bo2 ON r.target_bo_id = bo2.id")
        if 'service_modules_source' in self._join_tables:
            joins.append("LEFT JOIN service_modules sm1 ON bo1.service_module_id = sm1.id")
        if 'service_modules_target' in self._join_tables:
            joins.append("LEFT JOIN service_modules sm2 ON bo2.service_module_id = sm2.id")
        if 'sub_domains_source' in self._join_tables:
            joins.append("LEFT JOIN sub_domains sd1 ON sm1.sub_domain_id = sd1.id")
        if 'sub_domains_target' in self._join_tables:
            joins.append("LEFT JOIN sub_domains sd2 ON sm2.sub_domain_id = sd2.id")
        
        return " ".join(joins)
    
    def build_sql(self) -> Tuple[str, List[Any]]:
        """构建分析查询 SQL
        
        Returns:
            (sql, params) 元组
        """
        if not self._spec.dimensions and not self._spec.measures:
            raise ValueError("At least one dimension or measure is required")
        
        select_parts = []
        group_by_parts = []
        params = []
        
        for dim in self._spec.dimensions:
            if dim.sql_expr:
                select_parts.append(f"({dim.sql_expr}) AS {dim.alias}")
                group_by_parts.append(f"({dim.sql_expr})")
            else:
                col = self._get_db_column(dim.field_id)
                select_parts.append(f"{col} AS {dim.alias}")
                group_by_parts.append(col)
        
        for measure in self._spec.measures:
            col = self._get_db_column(measure.field_id)
            if measure.aggregation == 'COUNT_DISTINCT':
                select_parts.append(f"COUNT(DISTINCT {col}) AS {measure.alias}")
            else:
                select_parts.append(f"{measure.aggregation}({col}) AS {measure.alias}")
        
        sql = f"SELECT {', '.join(select_parts)} FROM {self._spec.table_name} r"
        
        join_clause = self._build_join_clause()
        if join_clause:
            sql += f" {join_clause}"
        
        if self._spec.filters:
            where_parts = []
            for field_id, operator, value in self._spec.filters:
                col = self._get_db_column(field_id)
                sql_op = self._map_operator(operator)
                
                if operator in ('in', 'not_in'):
                    if not isinstance(value, (list, tuple)):
                        value = [value]
                    placeholders = ', '.join(['?' for _ in value])
                    where_parts.append(f"{col} {sql_op} ({placeholders})")
                    params.extend(value)
                elif value is None:
                    if operator == 'eq':
                        where_parts.append(f"{col} IS NULL")
                    elif operator == 'ne':
                        where_parts.append(f"{col} IS NOT NULL")
                else:
                    where_parts.append(f"{col} {sql_op} ?")
                    params.append(value)
            
            if where_parts:
                sql += f" WHERE {' AND '.join(where_parts)}"
        
        if group_by_parts:
            sql += f" GROUP BY {', '.join(group_by_parts)}"
        
        if self._spec.order_by:
            order_parts = [f"{f} {d.upper()}" for f, d in self._spec.order_by]
            sql += f" ORDER BY {', '.join(order_parts)}"
        
        if self._spec.limit > 0:
            sql += f" LIMIT {self._spec.limit}"
        
        return sql, params
    
    def execute(self) -> List[Dict[str, Any]]:
        """执行分析查询
        
        Returns:
            查询结果列表
        """
        sql, params = self.build_sql()
        logger.info(f"[AnalyticsBuilder] Executing: {sql}")
        logger.debug(f"[AnalyticsBuilder] Params: {params}")
        
        cursor = self.ds.execute(sql, tuple(params))
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        logger.info(f"[AnalyticsBuilder] Returned {len(results)} rows")
        return results
    
    def _get_db_column(self, field_id: str) -> str:
        """获取字段的数据库列名"""
        field = self._field_map.get(field_id)
        if field:
            db_column = getattr(field, 'db_column', None)
            if db_column:
                return db_column
        return field_id
    
    def _map_operator(self, operator: str) -> str:
        """映射操作符到 SQL"""
        operator_map = {
            'eq': '=',
            'ne': '!=',
            'gt': '>',
            'lt': '<',
            'gte': '>=',
            'lte': '<=',
            'like': 'LIKE',
            'in': 'IN',
            'not_in': 'NOT IN',
        }
        return operator_map.get(operator.lower(), '=')
