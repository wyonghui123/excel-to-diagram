# -*- coding: utf-8 -*-
"""
Query Builder - 灵活的查询构建器

支持：
- 链式调用构建查询
- 多种操作符（=, !=, >, <, LIKE, IN, BETWEEN 等）
- 分页、排序
- 聚合函数
- 与元模型查询模板结合
"""

from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
import logging
logger = logging.getLogger(__name__)

from meta.core.models import (
    MetaObject, MetaField, MetaQuery, MetaQueryFilter, MetaQuerySort,
    QueryOperator, FieldType
)
from meta.core.datasource import DataSource


@dataclass
class QueryCondition:
    """查询条件"""
    field: str
    operator: QueryOperator
    value: Any = None
    values: List[Any] = field(default_factory=list)


@dataclass
class QuerySpec:
    """查询规格"""
    table_name: str
    conditions: List[QueryCondition] = field(default_factory=list)
    or_conditions: List[List[QueryCondition]] = field(default_factory=list)
    sorts: List[Tuple[str, str]] = field(default_factory=list)
    sort_expressions: List[str] = field(default_factory=list)
    limit: int = 0
    offset: int = 0
    fields: List[str] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    aggregates: Dict[str, str] = field(default_factory=dict)
    distinct: bool = False
    exists_conditions: List[Tuple[str, List[Any]]] = field(default_factory=list)  # EXISTS 子查询条件 (SQL, params)
    raw_conditions: List[Tuple[str, List[Any]]] = field(default_factory=list)  # 原始 SQL 条件 (SQL, params)


class QueryBuilder:
    """
    查询构建器
    
    支持链式调用构建复杂查询。
    
    示例:
        results = QueryBuilder(ds, product) \
            .where('name', 'like', '%供应链%') \
            .where('is_active', '=', True) \
            .order_by('created_at', 'desc') \
            .page(1, 20) \
            .execute()
    """
    
    def __init__(self, data_source: DataSource, meta_object: MetaObject):
        self.ds = data_source
        self.meta_object = meta_object
        self._spec = QuerySpec(table_name=meta_object.table_name)
        self._field_map = {f.id: f for f in meta_object.fields}
    
    def where(self, field: str, operator: Union[str, QueryOperator], 
              value: Any = None) -> "QueryBuilder":
        """
        添加查询条件
        
        Args:
            field: 字段名
            operator: 操作符 (eq, ne, gt, ge, lt, le, like, in, between 等)
            value: 值
            
        Returns:
            self (支持链式调用)
        """
        if isinstance(operator, str):
            operator = QueryOperator(operator.lower())
        
        condition = QueryCondition(
            field=self._get_db_column(field),
            operator=operator,
            value=self._convert_value(field, value)
        )
        self._spec.conditions.append(condition)
        return self
    
    def where_eq(self, field: str, value: Any) -> "QueryBuilder":
        """等于条件"""
        return self.where(field, QueryOperator.EQ, value)
    
    def where_ne(self, field: str, value: Any) -> "QueryBuilder":
        """不等于条件"""
        return self.where(field, QueryOperator.NE, value)
    
    def where_gt(self, field: str, value: Any) -> "QueryBuilder":
        """大于条件"""
        return self.where(field, QueryOperator.GT, value)
    
    def where_ge(self, field: str, value: Any) -> "QueryBuilder":
        """大于等于条件"""
        return self.where(field, QueryOperator.GE, value)
    
    def where_lt(self, field: str, value: Any) -> "QueryBuilder":
        """小于条件"""
        return self.where(field, QueryOperator.LT, value)
    
    def where_le(self, field: str, value: Any) -> "QueryBuilder":
        """小于等于条件"""
        return self.where(field, QueryOperator.LE, value)
    
    def where_like(self, field: str, pattern: str) -> "QueryBuilder":
        """LIKE 模糊查询"""
        return self.where(field, QueryOperator.LIKE, pattern)
    
    def where_ilike(self, field: str, pattern: str) -> "QueryBuilder":
        """不区分大小写的 LIKE"""
        return self.where(field, QueryOperator.ILIKE, pattern)
    
    def where_in(self, field: str, values: List[Any]) -> "QueryBuilder":
        """IN 多值查询"""
        condition = QueryCondition(
            field=self._get_db_column(field),
            operator=QueryOperator.IN,
            values=[self._convert_value(field, v) for v in values]
        )
        self._spec.conditions.append(condition)
        return self
    
    def where_not_in(self, field: str, values: List[Any]) -> "QueryBuilder":
        """NOT IN 查询"""
        condition = QueryCondition(
            field=self._get_db_column(field),
            operator=QueryOperator.NOT_IN,
            values=[self._convert_value(field, v) for v in values]
        )
        self._spec.conditions.append(condition)
        return self
    
    def where_between(self, field: str, start: Any, end: Any) -> "QueryBuilder":
        """BETWEEN 范围查询"""
        condition = QueryCondition(
            field=self._get_db_column(field),
            operator=QueryOperator.BETWEEN,
            values=[
                self._convert_value(field, start),
                self._convert_value(field, end)
            ]
        )
        self._spec.conditions.append(condition)
        return self
    
    def where_null(self, field: str) -> "QueryBuilder":
        """IS NULL 查询"""
        return self.where(field, QueryOperator.IS_NULL)
    
    def where_not_null(self, field: str) -> "QueryBuilder":
        """IS NOT NULL 查询"""
        return self.where(field, QueryOperator.IS_NOT_NULL)
    
    def or_where(self, conditions: List[Tuple[str, Union[str, QueryOperator], Any]]) -> "QueryBuilder":
        """
        添加 OR 条件组

        Args:
            conditions: 条件列表 [(field, operator, value), ...]
                         或 [(field, operator, [v1, v2, ...])] (IN/NOT_IN 用 list)

        Returns:
            self
        """
        or_group = []
        for field, operator, value in conditions:
            if isinstance(operator, str):
                operator = QueryOperator(operator.lower())
            # [FIX v3.18.1] IN/NOT_IN 算子应使用 values list 而非单个 value
            if operator in (QueryOperator.IN, QueryOperator.NOT_IN, QueryOperator.BETWEEN):
                values = value if isinstance(value, list) else [value]
                or_group.append(QueryCondition(
                    field=self._get_db_column(field),
                    operator=operator,
                    values=[self._convert_value(field, v) for v in values]
                ))
            else:
                or_group.append(QueryCondition(
                    field=self._get_db_column(field),
                    operator=operator,
                    value=self._convert_value(field, value)
                ))
        self._spec.or_conditions.append(or_group)
        return self
    
    def where_exists(self, subquery: str, params: List[Any] = None) -> "QueryBuilder":
        """
        添加 EXISTS 子查询条件（跨表关联过滤）
        
        参考 SAP CDS Association + Path Expression 风格：
        - 支持通过 EXISTS 子查询实现跨表过滤
        - 例如：按备注类型过滤业务对象
        
        Args:
            subquery: EXISTS 子查询 SQL（不含 EXISTS 关键字）
            params: 参数列表
            
        Returns:
            self
            
        示例:
            builder.where_exists('''
                SELECT 1 FROM annotations a
                WHERE a.target_id = bo.id
                AND a.target_type = 'business_object'
                AND a.category IN (?, ?)
            ''', ['important', 'warning'])
        """
        self._spec.exists_conditions.append((subquery, params or []))
        logger.info(f"[QueryBuilder] Added EXISTS condition: {subquery[:100]}... with params: {params}")
        return self

    def where_cursor(self, field: str, value: Any, direction: str = 'after') -> "QueryBuilder":
        """[M4 2026-06-05] cursor-based pagination 条件。

        direction='after'  → WHERE field > value（下一页）
        direction='before' → WHERE field < value（上一页）

        配套 usage: 配合 builder.page(1, page_size + 1) 多取一条判断 has_next
        """
        op = QueryOperator.GT if direction == 'after' else QueryOperator.LT
        self._spec.conditions.append(QueryCondition(
            field=self._get_db_column(field),
            operator=op,
            value=value,
        ))
        logger.info(f"[QueryBuilder] Added cursor: {field} {op} {value!r} (direction={direction})")
        return self

    def where_raw(self, raw_sql: str, params: List[Any] = None) -> "QueryBuilder":
        """
        添加原始 SQL 条件
        
        用于需要直接编写 SQL 的特殊场景：
        - 复杂子查询
        - 数据库特定函数
        - 临时性过滤条件
        
        Args:
            raw_sql: 原始 SQL 条件表达式
            params: 参数列表
            
        Returns:
            self
            
        示例:
            builder.where_raw("EXISTS (SELECT 1 FROM annotations WHERE ...)")
        """
        self._spec.raw_conditions.append((raw_sql, params or []))
        logger.info(f"[QueryBuilder] Added raw condition: {raw_sql[:100]}...")
        return self
    
    def order_by(self, field: str, direction: str = "asc") -> "QueryBuilder":
        """
        添加排序
        
        支持虚拟字段排序转换：
        - 如果字段有 sort_transform.by 配置，映射到真实字段
        - 如果字段有 sort_transform.sql_expr 配置，使用 SQL 表达式
        
        Args:
            field: 字段名
            direction: 排序方向 (asc / desc)
            
        Returns:
            self
        """
        from meta.core.virtual_field_transform import get_transform_engine
        from meta.core.models import FieldStorage
        
        direction = direction.lower()
        
        field_meta = self.meta_object.get_field(field) if self.meta_object else None
        if field_meta:
            storage = getattr(field_meta, 'storage', None)
            if storage == FieldStorage.VIRTUAL:
                engine = get_transform_engine()
                result = engine.transform_sort(self.meta_object, field, direction)
                
                if result:
                    sort_expr, is_expression = result
                    if is_expression:
                        self._spec.sort_expressions.append(sort_expr)
                        logger.info(f"[QueryBuilder] Virtual field '{field}' sort transformed to expression: {sort_expr}")
                    else:
                        self._spec.sorts.append((self._get_db_column(sort_expr), direction))
                        logger.info(f"[QueryBuilder] Virtual field '{field}' sort mapped to field: {sort_expr}")
                    return self
                else:
                    logger.info(f"[QueryBuilder] Virtual field '{field}' has no sort_transform, using memory sort")
                    return self
        
        self._spec.sorts.append((self._get_db_column(field), direction))
        return self
    
    def order_by_expr(self, expr: str) -> "QueryBuilder":
        """
        添加 SQL 表达式排序
        
        Args:
            expr: SQL 排序表达式（如 "CASE WHEN a=b THEN 1 ELSE 2 END ASC"）
            
        Returns:
            self
        """
        self._spec.sort_expressions.append(expr)
        return self
    
    def limit(self, limit: int) -> "QueryBuilder":
        """限制返回数量"""
        self._spec.limit = limit
        return self
    
    def offset(self, offset: int) -> "QueryBuilder":
        """设置偏移量"""
        self._spec.offset = offset
        return self
    
    def page(self, page: int, page_size: int = 20) -> "QueryBuilder":
        """
        分页
        
        Args:
            page: 页码（从1开始）
            page_size: 每页数量
            
        Returns:
            self
        """
        self._spec.offset = (page - 1) * page_size
        self._spec.limit = page_size
        return self
    
    def select(self, *fields: str) -> "QueryBuilder":
        """指定返回字段"""
        self._spec.fields = [self._get_db_column(f) for f in fields]
        return self
    
    def distinct(self) -> "QueryBuilder":
        """去重"""
        self._spec.distinct = True
        return self
    
    def group_by(self, *fields: str) -> "QueryBuilder":
        """分组"""
        self._spec.group_by = [self._get_db_column(f) for f in fields]
        return self
    
    def aggregate(self, func: str, field: str, alias: str = "") -> "QueryBuilder":
        """
        添加聚合函数
        
        Args:
            func: 聚合函数 (count, sum, avg, max, min)
            field: 字段名
            alias: 别名
            
        Returns:
            self
        """
        col = self._get_db_column(field)
        alias = alias or "{0}_{1}".format(func, field)
        self._spec.aggregates[alias] = "{0}({1})".format(func.lower(), col)
        return self
    
    def count(self, field: str = "*", alias: str = "count") -> "QueryBuilder":
        """COUNT 聚合"""
        col = self._get_db_column(field) if field != "*" else "*"
        self._spec.aggregates[alias] = "COUNT({0})".format(col)
        return self
    
    def sum(self, field: str, alias: str = "") -> "QueryBuilder":
        """SUM 聚合"""
        return self.aggregate("sum", field, alias)
    
    def avg(self, field: str, alias: str = "") -> "QueryBuilder":
        """AVG 聚合"""
        return self.aggregate("avg", field, alias)
    
    def max(self, field: str, alias: str = "") -> "QueryBuilder":
        """MAX 聚合"""
        return self.aggregate("max", field, alias)
    
    def min(self, field: str, alias: str = "") -> "QueryBuilder":
        """MIN 聚合"""
        return self.aggregate("min", field, alias)
    
    def from_query(self, query: MetaQuery, params: Optional[Dict[str, Any]] = None) -> "QueryBuilder":
        """
        从元模型查询模板构建
        
        Args:
            query: 元模型查询定义
            params: 参数值
            
        Returns:
            self
        """
        params = params or {}
        
        for f in query.filters:
            value = params.get(f.param, f.value) if f.param else f.value
            if f.operator == QueryOperator.IN:
                self.where_in(f.field, value if isinstance(value, list) else [value])
            elif f.operator == QueryOperator.BETWEEN:
                if isinstance(value, list) and len(value) == 2:
                    self.where_between(f.field, value[0], value[1])
            else:
                self.where(f.field, f.operator, value)
        
        for s in query.sorts:
            self.order_by(s.field, s.direction)
        
        if query.limit > 0:
            self.limit(query.limit)
        if query.offset > 0:
            self.offset(query.offset)
        if query.fields:
            self.select(*query.fields)
        if query.group_by:
            self.group_by(*query.group_by)
        if query.aggregates:
            self._spec.aggregates.update(query.aggregates)
        
        return self
    
    def build_sql(self) -> Tuple[str, List[Any]]:
        """
        构建 SQL 语句

        Returns:
            (sql, params) 元组
        """
        import logging
        _qlog = logging.getLogger('meta.core.query_builder')
        parts = []
        params = []
        
        if self._spec.aggregates:
            select_cols = list(self._spec.aggregates.values())
            if self._spec.fields:
                select_cols.extend(self._spec.fields)
            parts.append("SELECT {0}".format(", ".join(select_cols)))
        elif self._spec.fields:
            select_clause = "SELECT DISTINCT" if self._spec.distinct else "SELECT"
            parts.append("{0} {1}".format(select_clause, ", ".join(self._spec.fields)))
        else:
            select_clause = "SELECT DISTINCT *" if self._spec.distinct else "SELECT *"
            parts.append(select_clause)
        
        # 使用 analytical_model 中的 alias（如果有），否则使用默认的 'bo'
        alias = 'bo'
        if hasattr(self.meta_object, 'analytical_model') and self.meta_object.analytical_model:
            fact_config = self.meta_object.analytical_model.get('fact', {})
            alias = fact_config.get('alias', 'bo')
        
        parts.append("FROM {0} AS {1}".format(self._spec.table_name, alias))
        
        where_parts = []
        
        for cond in self._spec.conditions:
            w, p = self._build_condition(cond)
            where_parts.append(w)
            params.extend(p)
        
        for or_group in self._spec.or_conditions:
            or_parts = []
            for cond in or_group:
                w, p = self._build_condition(cond)
                or_parts.append(w)
                params.extend(p)
            where_parts.append("({0})".format(" OR ".join(or_parts)))
        
        # 添加 EXISTS 子查询条件（跨表关联过滤）
        for exists_item in self._spec.exists_conditions:
            if isinstance(exists_item, tuple):
                exists_sql, exists_params = exists_item
                where_parts.append(f"EXISTS ({exists_sql})")
                params.extend(exists_params)
            else:
                where_parts.append(f"EXISTS ({exists_item})")
        
        # 添加原始 SQL 条件
        for raw_item in self._spec.raw_conditions:
            if isinstance(raw_item, tuple):
                raw_sql, raw_params = raw_item
                where_parts.append(raw_sql)
                params.extend(raw_params)
            else:
                where_parts.append(raw_item)
        
        if where_parts:
            parts.append("WHERE {0}".format(" AND ".join(where_parts)))
        
        if self._spec.group_by:
            parts.append("GROUP BY {0}".format(", ".join(self._spec.group_by)))
        
        all_sorts = []
        all_sorts.extend(["{0} {1}".format(f, d.upper()) for f, d in self._spec.sorts])
        all_sorts.extend(self._spec.sort_expressions)
        
        if all_sorts:
            parts.append("ORDER BY {0}".format(", ".join(all_sorts)))
        
        if self._spec.limit > 0:
            parts.append("LIMIT {0}".format(self._spec.limit))
        if self._spec.offset > 0:
            parts.append("OFFSET {0}".format(self._spec.offset))
        
        sql = " ".join(parts)
        return sql, params
    
    def _build_condition(self, cond: QueryCondition) -> Tuple[str, List[Any]]:
        """构建单个条件"""
        params = []
        
        if cond.operator == QueryOperator.EQ:
            params.append(cond.value)
            return "{0} = ?".format(cond.field), params
        elif cond.operator == QueryOperator.NE:
            params.append(cond.value)
            return "{0} != ?".format(cond.field), params
        elif cond.operator == QueryOperator.GT:
            params.append(cond.value)
            return "{0} > ?".format(cond.field), params
        elif cond.operator == QueryOperator.GE:
            params.append(cond.value)
            return "{0} >= ?".format(cond.field), params
        elif cond.operator == QueryOperator.LT:
            params.append(cond.value)
            return "{0} < ?".format(cond.field), params
        elif cond.operator == QueryOperator.LE:
            params.append(cond.value)
            return "{0} <= ?".format(cond.field), params
        elif cond.operator == QueryOperator.LIKE:
            params.append(cond.value)
            return "{0} LIKE ?".format(cond.field), params
        elif cond.operator == QueryOperator.ILIKE:
            params.append(cond.value)
            return "LOWER({0}) LIKE LOWER(?)".format(cond.field), params
        elif cond.operator == QueryOperator.IN:
            if not cond.values:
                return "1=0", params
            placeholders = ", ".join(["?"] * len(cond.values))
            params.extend(cond.values)
            return "{0} IN ({1})".format(cond.field, placeholders), params
        elif cond.operator == QueryOperator.NOT_IN:
            if not cond.values:
                return "1=1", params
            placeholders = ", ".join(["?"] * len(cond.values))
            params.extend(cond.values)
            return "{0} NOT IN ({1})".format(cond.field, placeholders), params
        elif cond.operator == QueryOperator.IS_NULL:
            return "{0} IS NULL".format(cond.field), params
        elif cond.operator == QueryOperator.IS_NOT_NULL:
            return "{0} IS NOT NULL".format(cond.field), params
        elif cond.operator == QueryOperator.BETWEEN:
            params.extend(cond.values)
            return "{0} BETWEEN ? AND ?".format(cond.field), params
        
        return "", params
    
    def build(self) -> str:
        """
        构建 SQL 语句（不执行）
        
        用于调试和测试场景，返回完整的 SQL 语句。
        
        Returns:
            SQL 语句字符串
        """
        sql, params = self.build_sql()
        if params:
            param_str = ", ".join(repr(p) for p in params)
            return f"{sql} -- params: [{param_str}]"
        return sql
    
    def execute(self) -> List[Dict[str, Any]]:
        """
        执行查询
        
        Returns:
            查询结果列表
        """
        sql, params = self.build_sql()
        cursor = self.ds.execute(sql, tuple(params) if params else None)
        rows = cursor.fetchall()
        
        if rows:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return []
    
    def first(self) -> Optional[Dict[str, Any]]:
        """返回第一条记录"""
        self._spec.limit = 1
        results = self.execute()
        return results[0] if results else None
    
    def count_all(self) -> int:
        """返回符合条件的记录总数"""
        sql, params = self.build_sql()
        
        count_sql = "SELECT COUNT(*) FROM ({0}) AS _count_query".format(sql)
        cursor = self.ds.execute(count_sql, tuple(params) if params else None)
        row = cursor.fetchone()
        return row[0] if row else 0
    
    def exists(self) -> bool:
        """检查是否存在符合条件的记录"""
        return self.count_all() > 0
    
    def paginate(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """
        分页查询
        
        Args:
            page: 页码（从1开始）
            page_size: 每页数量
            
        Returns:
            {
                "data": [...],
                "total": 100,
                "page": 1,
                "page_size": 20,
                "total_pages": 5
            }
        """
        total = self.count_all()
        self.page(page, page_size)
        data = self.execute()
        
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        
        return {
            "data": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    
    def _get_db_column(self, field: str) -> str:
        """获取数据库列名"""
        if field in self._field_map:
            return self._field_map[field].db_column
        return field
    
    def _convert_value(self, field: str, value: Any) -> Any:
        """类型转换"""
        if value is None:
            return None
        
        meta_field = self._field_map.get(field)
        if not meta_field:
            return value
        
        try:
            if meta_field.field_type == FieldType.INTEGER:
                return int(value)
            elif meta_field.field_type == FieldType.FLOAT:
                return float(value)
            elif meta_field.field_type == FieldType.BOOLEAN:
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
        except (ValueError, TypeError):
            pass
        
        return value


def query(data_source: DataSource, meta_object: MetaObject) -> QueryBuilder:
    """
    创建 QueryBuilder 的便捷函数
    
    Args:
        data_source: 数据源
        meta_object: 元模型对象
        
    Returns:
        QueryBuilder 实例
    """
    return QueryBuilder(data_source, meta_object)
