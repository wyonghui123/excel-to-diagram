from typing import List, Dict, Any, Optional
import logging

from meta.core.query_builder import QueryBuilder
from meta.core.models import MetaObject, registry, QueryOperator, FieldStorage
from meta.core.datasource import DataSource
from meta.core.table_name_validator import validate_table_name
from meta.services.filter_service import filter_service
from meta.core.sql_utils import add_table_alias_to_where
from meta.services.query_models import (
    QueryCondition, SearchRequest, SearchResult,
    AggregateMeasure, AggregateRequest, AggregateResult,
    AnalyticsFieldInfo,
)
from meta.services.query.hierarchy_utils import (
    resolve_object_id_by_depth,
    get_name_field,
    get_child_object_id,
    get_parent_field,
    get_ancestor_parent_field,
    apply_hierarchy_filter,
    apply_path_name_filters,
)
from meta.services.query.virtual_sort import (
    build_virtual_field_order_join,
    execute_virtual_field_query,
)
from meta.services.query.computed_utils import (
    sort_by_virtual_fields,
    ensure_hierarchy_ids_for_relationships,
)
from meta.services.query.filter_utils import (
    parse_filter_value,
    build_computed_where_clause,
    build_virtual_field_filter_exists,
    build_exists_subquery,
)

logger = logging.getLogger(__name__)


def discover_analytics_fields(meta_obj: MetaObject) -> List[AnalyticsFieldInfo]:
    result = []
    for f in meta_obj.fields:
        analytics = f.semantics.analytics if hasattr(f.semantics, 'analytics') else {}
        if not analytics:
            continue
        category = analytics.get("category", "")
        if not category:
            continue
        result.append(AnalyticsFieldInfo(
            field_id=f.id,
            category=category,
            aggregation=analytics.get("aggregation", ""),
            dimension_type=analytics.get("type", ""),
            display_name=analytics.get("display_name", f.name or f.id),
            hidden=analytics.get("hidden", False),
            default_filter=analytics.get("default_filter"),
        ))
    return result


def enrich_dimension_names(
    meta_obj: MetaObject,
    data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not data:
        return data

    analytics_fields = discover_analytics_fields(meta_obj)
    fk_dimensions = {}
    for af in analytics_fields:
        if af.category == "dimension" and af.dimension_type == "foreign_key":
            fk_dimensions[af.field_id] = af

    if not fk_dimensions:
        return data

    dim_values = {}
    for dim_field, af in fk_dimensions.items():
        values = set()
        for row in data:
            v = row.get(dim_field)
            if v is not None:
                values.add(v)
        if values:
            dim_values[dim_field] = values

    for dim_field, values in dim_values.items():
        target_field = meta_obj.get_field(dim_field)
        if not target_field:
            continue
        ui = target_field.ui if hasattr(target_field, 'ui') else None
        if not ui:
            continue
        relation_object = ui.relation if hasattr(ui, 'relation') else ""
        display_field = ui.display_field if hasattr(ui, 'display_field') else ""
        if not relation_object or not display_field:
            continue

        target_obj = registry.get(relation_object)
        if not target_obj:
            continue

        try:
            from meta.core.datasource import DataSource
            ds = None
            for row in data:
                break

            target_builder = QueryBuilder(
                _get_data_source(),
                target_obj,
            )
            target_builder.where_in("id", list(values))
            target_builder.select("id", display_field)
            target_rows = target_builder.execute()

            id_to_name = {}
            for tr in target_rows:
                id_to_name[tr.get("id")] = tr.get(display_field, "")

            name_field = "{0}_name".format(dim_field.replace("_id", ""))
            for row in data:
                dim_val = row.get(dim_field)
                if dim_val is not None and dim_val in id_to_name:
                    row[name_field] = id_to_name[dim_val]
        except Exception:
            pass

    return data


_data_source_instance = None


def _get_data_source():
    global _data_source_instance
    if _data_source_instance is None:
        try:
            from meta.core.bo_framework import bo_framework
            ds = getattr(bo_framework, '_data_source', None)
            if ds is not None:
                _data_source_instance = ds
            else:
                from meta.core.datasource import get_data_source
                import os
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
                _data_source_instance = get_data_source('sqlite', database=db_path)
        except Exception:
            pass
    return _data_source_instance


_OPERATOR_MAP = {
    "eq": QueryOperator.EQ,
    "ne": QueryOperator.NE,
    "gt": QueryOperator.GT,
    "ge": QueryOperator.GE,
    "lt": QueryOperator.LT,
    "le": QueryOperator.LE,
    "like": QueryOperator.LIKE,
    "ilike": QueryOperator.ILIKE,
    "in": QueryOperator.IN,
    "not_in": QueryOperator.NOT_IN,
    "is_null": QueryOperator.IS_NULL,
    "is_not_null": QueryOperator.IS_NOT_NULL,
    "between": QueryOperator.BETWEEN,
}

_METHOD_MAP = {
    QueryOperator.EQ: "where_eq",
    QueryOperator.NE: "where_ne",
    QueryOperator.GT: "where_gt",
    QueryOperator.GE: "where_ge",
    QueryOperator.LT: "where_lt",
    QueryOperator.LE: "where_le",
    QueryOperator.LIKE: "where_like",
    QueryOperator.ILIKE: "where_ilike",
    QueryOperator.IN: "where_in",
    QueryOperator.NOT_IN: "where_not_in",
    QueryOperator.IS_NULL: "where_null",
    QueryOperator.IS_NOT_NULL: "where_not_null",
    QueryOperator.BETWEEN: "where_between",
}


def _resolve_operator(op) -> QueryOperator:
    if isinstance(op, QueryOperator):
        return op
    return _OPERATOR_MAP.get(op.lower(), QueryOperator.EQ)


class QueryService:

    def __init__(self, data_source: DataSource):
        self.ds = data_source

    def _build_virtual_field_order_join(
        self, 
        meta_obj: MetaObject, 
        sort_field: str, 
        sort_direction: str
    ) -> Optional[str]:
        return build_virtual_field_order_join(meta_obj, sort_field, sort_direction)


    def search(self, request: SearchRequest) -> SearchResult:
        meta_obj = registry.get(request.object_type)
        logger.info(f"[QueryService.search] object_type={request.object_type}, order_by={request.order_by}")
        if not meta_obj:
            return SearchResult(
                page=request.page,
                page_size=request.page_size,
            )

        builder = QueryBuilder(self.ds, meta_obj)

        # 应用元模型驱动的过滤条件
        if request.filter_params:
            self._apply_meta_driven_filters(builder, meta_obj, request.filter_params, request.filter_scope)

        # [M3 2026-06-05] 应用 UnifiedQueryFacade 注入的子查询条件
        # 用于 computed *_count 字段过滤 / 关联查询过滤
        # 项格式:
        #   ('__raw__', (sql, params))  - 直接拼到 WHERE（适用于 (subquery) op value）
        #   ('__raw__', sql)             - 同上，无参数
        #   (sql, params)                - EXISTS 子查询（适用于关联过滤）
        #   sql                          - EXISTS 子查询，无参数
        for exists_item in (request.exists_conditions or []):
            if isinstance(exists_item, tuple) and len(exists_item) == 2:
                marker, payload = exists_item
                if marker == '__raw__':
                    if isinstance(payload, tuple):
                        builder.where_raw(payload[0], payload[1])
                    else:
                        builder.where_raw(payload)
                else:
                    # 原生 EXISTS 项
                    builder.where_exists(marker, payload)
            elif isinstance(exists_item, str):
                builder.where_exists(exists_item)

        # [M4 2026-06-05] 应用 cursor-based pagination 条件
        if request.cursor and meta_obj:
            from meta.core.unified_query_facade import _decode_cursor
            try:
                decoded = _decode_cursor(request.cursor)
                if decoded and request.cursor_field in decoded:
                    builder.where_cursor(
                        request.cursor_field,
                        decoded[request.cursor_field],
                        request.cursor_direction,
                    )
                    # 多取一条判断 has_next（不影响 count / total）
                    builder.page(1, request.page_size + 1)
                    request._cursor_active = True
            except Exception as e:
                logger.warning(f"[QueryService.M4] invalid cursor, ignored: {e}")

        # 分离 OR 条件和 AND 条件
        or_conditions = [c for c in request.conditions if c.combine_mode == 'or']
        and_conditions = [c for c in request.conditions if c.combine_mode != 'or']

        # 先应用 AND 条件
        for cond in and_conditions:
            op = _resolve_operator(cond.operator)
            method_name = _METHOD_MAP.get(op)
            if method_name and hasattr(builder, method_name):
                method = getattr(builder, method_name)
                if op == QueryOperator.IS_NULL or op == QueryOperator.IS_NOT_NULL:
                    method(cond.field)
                elif op == QueryOperator.IN or op == QueryOperator.NOT_IN:
                    method(cond.field, cond.values if cond.values else [cond.value])
                elif op == QueryOperator.BETWEEN:
                    vals = cond.values if len(cond.values) >= 2 else [cond.value, cond.value]
                    method(cond.field, vals[0], vals[1])
                else:
                    method(cond.field, cond.value)

        # 应用 OR 条件组
        if or_conditions:
            or_group = []
            for cond in or_conditions:
                op = _resolve_operator(cond.operator)
                # [FIX v3.18.1] IN/NOT_IN 算子必须传 values list
                if op in (QueryOperator.IN, QueryOperator.NOT_IN):
                    payload = cond.values if cond.values else [cond.value]
                else:
                    payload = cond.value
                or_group.append((cond.field, op, payload))
            if or_group:
                builder.or_where(or_group)

        self._apply_data_permission(builder, meta_obj, request.object_type)
        
        self._apply_soft_delete_filter(builder, meta_obj, request.include_deleted, request.deleted_only)

        if request.keyword:
            # 优先使用 request.search_fields（来自 value_help 的 search_fields 参数）
            # 如果没有指定，则使用默认搜索字段（display_name/name/code/description/remark/notes）
            search_fields = []
            if hasattr(request, 'search_fields') and request.search_fields:
                # 验证字段是否存在于 meta_obj 中
                valid_field_ids = {f.id for f in meta_obj.fields}
                search_fields = [f for f in request.search_fields if f in valid_field_ids]

            if not search_fields:
                # 回退到默认搜索字段
                for f in meta_obj.fields:
                    render_hints = f.ui.render_hints if f.ui and f.ui.render_hints else None
                    is_searchable = render_hints.searchable if render_hints else True

                    if f.field_type.value in ("string", "text") and is_searchable:
                        if f.semantics.display_name or f.id in ("name", "code", "description", "remark", "notes"):
                            search_fields.append(f.id)

            if search_fields:
                or_conditions = [
                    (f, QueryOperator.ILIKE, "%{0}%".format(request.keyword))
                    for f in search_fields
                ]
                builder.or_where(or_conditions)

        if request.hierarchy_path:
            self._apply_hierarchy_filter(builder, meta_obj, request.hierarchy_path)

        order_clause = request.get_order_by_clause()
        virtual_join_info = None
        memory_sort_field = None
        memory_sort_direction = None
        memory_sort_computed_by = None
        memory_sort_formula = None
        default_updated_at_sort = False
        
        if not order_clause:
            updated_at_field = meta_obj.get_field('updated_at') if meta_obj else None
            if updated_at_field:
                order_clause = 'updated_at desc'
                default_updated_at_sort = True
                logger.info(f"[VirtualSort] No order specified, defaulting to updated_at desc")

        logger.info(f"[VirtualSort] search called: object_type={request.object_type}, order_clause={order_clause}, page={request.page}, page_size={request.page_size}")

        if order_clause:
            parts = order_clause.strip().split()
            raw_field = parts[0]
            order_field = raw_field.lstrip('-')
            direction = 'desc' if raw_field.startswith('-') else (parts[1] if len(parts) > 1 else 'asc')
            
            logger.info(f"[VirtualSort] order_field={order_field}, direction={direction}")
            
            virtual_join_info = self._build_virtual_field_order_join(
                meta_obj, order_field, direction
            )

            logger.info(f"[VirtualSort] virtual_join_info={virtual_join_info}")
            
            if virtual_join_info:
                join_clause, order_alias, sort_dir = virtual_join_info
                data, total = self._execute_virtual_field_query(
                    builder, join_clause, order_alias, sort_dir,
                    request.page, request.page_size, meta_obj
                )
                total_pages = (total + request.page_size - 1) // request.page_size if request.page_size > 0 else 0

                aggregations = {}
                if data:
                    aggregations["count"] = len(data)

                if request.include_relations and data:
                    data = self._enrich_with_relations(meta_obj, data)

                # [FIX 2026-06-08] 计算 list 中配置的 computed 字段（如 child_count）
                # 早期 return 路径必须也调用，否则 child_count 永远是 None
                if data:
                    data = self._enrich_audit_virtual_fields(meta_obj, data)
                    try:
                        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
                        pi = PersistenceInterceptor()
                        data = pi._enrich_fk_display_names(meta_obj, data, self.ds)
                    except Exception as e:
                        logger.warning(f"[QueryService.search] _enrich_fk_display_names failed: {e}")
                    data = self._compute_list_computed_fields(meta_obj, data)

                return SearchResult(
                    data=data,
                    total=total,
                    page=request.page,
                    page_size=request.page_size,
                    total_pages=total_pages,
                    aggregations=aggregations,
                )
            else:
                field = meta_obj.get_field(order_field) if meta_obj else None
                is_physical = True
                computation = None
                if field:
                    storage = getattr(field, 'storage', None)
                    if storage == FieldStorage.VIRTUAL:
                        is_physical = False
                    raw_computation = getattr(field, 'computation', None)
                    computation = raw_computation if isinstance(raw_computation, dict) and raw_computation.get('type') else None
                    logger.info(f"[VirtualSort] Field '{order_field}': storage={storage}, raw_computation={raw_computation}, computation={computation}")
                    if not computation:
                        ui_view_config = getattr(meta_obj, 'ui_view_config', None) if meta_obj else None
                        if ui_view_config:
                            list_view = getattr(ui_view_config, 'list', None)
                            logger.info(f"[VirtualSort] UI list_view: {list_view}")
                            if list_view:
                                for col in list_view.columns:
                                    col_computation = getattr(col, 'computation', None)
                                    logger.info(f"[VirtualSort] Column '{col.key}': computation={col_computation}")
                                    if col.key == order_field and isinstance(col_computation, dict) and col_computation.get('type'):
                                        computation = col_computation
                                        break
                
                if is_physical:
                    builder.order_by(order_field, direction)
                elif computation and computation.get('type') == 'count_relations':
                    logger.info(f"[VirtualSort] Field '{order_field}' has count_relations computation, using DB sort")
                    logger.info(f"[VirtualSort] Computation details: {computation}")
                    data, total = self._execute_computed_field_query(
                        builder, order_field, direction,
                        computation, request.page, request.page_size, meta_obj
                    )
                    total_pages = (total + request.page_size - 1) // request.page_size if request.page_size > 0 else 0
                    aggregations = {}
                    if data:
                        aggregations["count"] = len(data)
                    if request.include_relations and data:
                        data = self._enrich_with_relations(meta_obj, data)
                    # [FIX 2026-06-08] 计算 list 中配置的 computed 字段
                    if data:
                        data = self._enrich_audit_virtual_fields(meta_obj, data)
                        try:
                            from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
                            pi = PersistenceInterceptor()
                            data = pi._enrich_fk_display_names(meta_obj, data, self.ds)
                        except Exception as e:
                            logger.warning(f"[QueryService.search] _enrich_fk_display_names failed: {e}")
                        data = self._compute_list_computed_fields(meta_obj, data)
                    return SearchResult(
                        data=data,
                        total=total,
                        page=request.page,
                        page_size=request.page_size,
                        total_pages=total_pages,
                        aggregations=aggregations,
                    )
                else:
                    logger.info(f"[VirtualSort] Field '{order_field}' is not physical and has no DB-sortable computation, will sort in memory")
                    
                    semantics = getattr(field, 'semantics', None) if field else None
                    computed_by = getattr(semantics, 'computed_by', None) if semantics else None
                    
                    formula = computation.get('formula') if computation else None
                    
                    if computed_by:
                        logger.info(f"[VirtualSort] Field '{order_field}' has computed_by='{computed_by}', will sort in memory")
                        memory_sort_field = order_field
                        memory_sort_direction = direction
                        memory_sort_computed_by = computed_by
                    elif formula:
                        logger.info(f"[VirtualSort] Field '{order_field}' has formula, will sort in memory")
                        memory_sort_field = order_field
                        memory_sort_direction = direction
                        memory_sort_computed_by = 'formula'
                        memory_sort_formula = formula
                    else:
                        logger.info(f"[VirtualSort] Field '{order_field}' is virtual without computed_by, using default memory sort")
                        memory_sort_field = order_field
                        memory_sort_direction = direction
                        memory_sort_computed_by = 'default'

        # [FR-007] 虚拟字段排序: 先排序再分页, 修复跨页排序不一致 Bug
        if memory_sort_field:
            # 内存排序路径: 先查全部数据, 排序后再分页
            data = builder.execute()
            total = len(data) if request.skip_count else builder.count_all()
            total_pages = (total + request.page_size - 1) // request.page_size if request.page_size > 0 else 0
        else:
            builder.page(request.page, request.page_size)
            data = builder.execute()
            if request.skip_count:
                total = -1
                total_pages = -1
            else:
                total = builder.count_all()
                total_pages = (total + request.page_size - 1) // request.page_size if request.page_size > 0 else 0

        aggregations = {}
        if data:
            aggregations["count"] = len(data)

        if request.include_relations and data:
            data = self._enrich_with_relations(meta_obj, data)

        data = self._enrich_audit_virtual_fields(meta_obj, data)

        # 注入 FK display names（与 _do_list 保持一致）
        try:
            from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
            pi = PersistenceInterceptor()
            data = pi._enrich_fk_display_names(meta_obj, data, self.ds)
        except Exception as e:
            logger.warning(f"[QueryService.search] _enrich_fk_display_names failed: {e}")

        if data:
            data = self._compute_list_computed_fields(meta_obj, data)

        if order_clause:
            data = self._sort_by_virtual_fields(meta_obj, data, order_clause)
        
        if memory_sort_field and memory_sort_computed_by:
            data = self._sort_by_computed_field(data, memory_sort_field, memory_sort_direction, memory_sort_computed_by, meta_obj, memory_sort_formula)

        # [FR-007] 内存排序后 Python 分页
        if memory_sort_field and data:
            start = (request.page - 1) * request.page_size
            data = data[start:start + request.page_size]

        return SearchResult(
            data=data,
            total=total,
            page=request.page,
            page_size=request.page_size,
            total_pages=total_pages,
            aggregations=aggregations,
        )

    def _enrich_audit_virtual_fields(self, meta_obj, records):
        """SSOT: 从 audit_logs 批量计算 virtual updated_at

        v1.4 重构：委托给共享 helper `meta.core.audit_derived_fields`

        更新时间逻辑：
        1. 只查询 UPDATE 操作的审计日志时间
        2. 如果没有 UPDATE 日志，则使用记录本身的 created_at（创建时间）
        """
        if not records:
            return records

        virtual_fields = []
        for f in meta_obj.fields:
            storage = getattr(f, 'storage', None)
            deriv_obj = getattr(f, 'derive_from_object', '')
            if storage == FieldStorage.VIRTUAL and deriv_obj == 'audit_logs':
                virtual_fields.append(f)

        if not virtual_fields:
            return records

        # v1.4 抽取：委托给 SSOT helper
        from meta.core.audit_derived_fields import enrich_audit_virtual_fields
        field_ids = [vf.id for vf in virtual_fields]
        return enrich_audit_virtual_fields(
            ds=self.ds,
            object_type=meta_obj.id,
            records=records,
            field_ids=field_ids,
        )

    def _compute_list_computed_fields(self, meta_obj, data):
        """计算列表视图中的计算字段（用于排序和过滤）

        [FR-005] 使用 computation_service.collect_computed_columns SSOT，
        与 import_export_service._compute_list_computed_fields_for_export 统一。
        """
        try:
            from meta.services.computation_service import computation_service

            computed_cols = computation_service.collect_computed_columns(meta_obj)

            if computed_cols:
                computation_service.compute_batch(self.ds, meta_obj.id, data, computed_cols)

        except Exception as e:
            logger.warning(f"[ComputedFields] Failed to compute fields: {e}")

        return data

    def _sort_by_virtual_fields(self, meta_obj, records, order_by):
        return sort_by_virtual_fields(meta_obj, records, order_by)

    def _sort_by_computed_field(
        self,
        data: List[Dict[str, Any]],
        order_field: str,
        direction: str,
        computed_by: str,
        meta_obj: MetaObject,
        formula: str = None
    ) -> List[Dict[str, Any]]:
        """对计算型虚拟字段进行内存排序
        
        Args:
            data: 查询结果数据
            order_field: 排序字段
            direction: 排序方向 (asc/desc)
            computed_by: 计算函数标识
            meta_obj: 元对象
            formula: 公式表达式（当 computed_by='formula' 时使用）
            
        Returns:
            排序后的数据
        """
        if not data:
            return data
        
        logger.info(f"[ComputedSort] Sorting {len(data)} records by {order_field} ({direction}) using computed_by={computed_by}")
        
        if computed_by == 'hierarchy_scope':
            from meta.services.cascade_service import HierarchyConfigLoader

            self._ensure_hierarchy_ids_for_relationships(data)

            for item in data:
                if order_field not in item or item.get(order_field) is None:
                    name, _, _ = HierarchyConfigLoader.compute_scope(item)
                    if not name:
                        name = '同服务模块'
                    item[order_field] = name
        
        elif computed_by == 'formula' and formula:
            from meta.core.rule_executor import ExpressionEvaluator, RuleContext
            
            for item in data:
                if order_field not in item or item.get(order_field) is None:
                    context = RuleContext(meta_obj, item)
                    value = ExpressionEvaluator.evaluate(formula, context)
                    item[order_field] = value
        
        elif computed_by == 'default':
            pass
        
        reverse = direction.lower() == 'desc'
        
        def sort_key(item):
            val = item.get(order_field, '')
            if val is None:
                return ''
            return str(val)
        
        sorted_data = sorted(data, key=sort_key, reverse=reverse)
        logger.info(f"[ComputedSort] Sorted {len(sorted_data)} records")
        
        return sorted_data
    
    def _ensure_hierarchy_ids_for_relationships(self, data: List[Dict[str, Any]]):
        return ensure_hierarchy_ids_for_relationships(self.ds, data)

    def _execute_computed_field_query(
        self,
        builder: QueryBuilder,
        order_field: str,
        direction: str,
        computation: dict,
        page: int,
        page_size: int,
        meta_obj: MetaObject = None,
    ) -> tuple:
        import re
        from meta.core.enrichment_engine import enrich_records, get_enrichment_engine
        
        logger.info(f"[ComputedSort] _execute_computed_field_query: field={order_field}, dir={direction}, computation={computation}")
        
        table_name = validate_table_name(meta_obj.table_name) if meta_obj else builder._spec.table_name
        comp_type = computation.get('type')
        
        base_sql, params = builder.build_sql()
        base_sql = re.sub(r'\s+ORDER\s+BY\s+\S+\s+(?:ASC|DESC)', '', base_sql, flags=re.IGNORECASE)

        object_type = meta_obj.id if meta_obj else ''
        scope = computation.get('scope', 'self')
        
        if comp_type == 'count_relations':
            rel_table = 'relationships'
            if scope == 'self' and object_type == 'business_object':
                count_subquery = (
                    f"(SELECT COUNT(*) FROM {rel_table} "
                    f"WHERE {rel_table}.source_bo_id = {table_name}.id "
                    f"OR {rel_table}.target_bo_id = {table_name}.id) "
                    f"AS _sort_val"
                )
            elif scope == 'self' and object_type == 'user_group':
                count_subquery = (
                    f"(SELECT COUNT(*) FROM user_group_members "
                    f"WHERE user_group_members.group_id = {table_name}.id) "
                    f"AS _sort_val"
                )
            elif scope == 'descendants':
                if object_type == 'domain':
                    count_subquery = (
                        f"(SELECT COUNT(DISTINCT r.id) FROM relationships r "
                        f"WHERE r.source_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                        f"JOIN sub_domains sd ON sm.sub_domain_id = sd.id "
                        f"WHERE sd.domain_id = {table_name}.id) "
                        f"OR r.target_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                        f"JOIN sub_domains sd ON sm.sub_domain_id = sd.id "
                        f"WHERE sd.domain_id = {table_name}.id)) "
                        f"AS _sort_val"
                    )
                elif object_type == 'sub_domain':
                    count_subquery = (
                        f"(SELECT COUNT(DISTINCT r.id) FROM relationships r "
                        f"WHERE r.source_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                        f"WHERE sm.sub_domain_id = {table_name}.id) "
                        f"OR r.target_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                        f"WHERE sm.sub_domain_id = {table_name}.id)) "
                        f"AS _sort_val"
                    )
                elif object_type == 'service_module':
                    count_subquery = (
                        f"(SELECT COUNT(DISTINCT r.id) FROM relationships r "
                        f"WHERE r.source_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"WHERE bo.service_module_id = {table_name}.id) "
                        f"OR r.target_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"WHERE bo.service_module_id = {table_name}.id)) "
                        f"AS _sort_val"
                    )
                else:
                    logger.warning(f"[ComputedSort] Unknown object_type for descendants scope: {object_type}")
                    return builder.execute(), builder.count_all()
            else:
                logger.warning(f"[ComputedSort] Unsupported count_relations scope/object: scope={scope}, object_type={object_type}")
                return builder.execute(), builder.count_all()
        else:
            logger.warning(f"[ComputedSort] Unknown computation type: {comp_type}")
            return builder.execute(), builder.count_all()
        
        if "WHERE" in base_sql.upper():
            parts = base_sql.split("WHERE", 1)
            where_clause = add_table_alias_to_where(parts[1], table_name)
            where_clause_for_count = where_clause
        else:
            where_clause = None
            where_clause_for_count = None
        
        count_sql = f"SELECT COUNT(*) as cnt FROM {table_name}"
        if where_clause_for_count:
            count_sql = f"{count_sql} WHERE {where_clause_for_count}"
        
        try:
            count_result = self.ds.query(count_sql, params)
            total = count_result[0].get('cnt', 0) if count_result else 0
        except Exception as e:
            logger.warning(f"[ComputedSort] Count query failed: {e}")
            total = 0
        
        subquery_alias = "_csq"
        subquery_select = f"SELECT {table_name}.*, {count_subquery} FROM {table_name}"
        if where_clause:
            subquery_select = f"SELECT {table_name}.*, {count_subquery} FROM {table_name} WHERE {where_clause}"
        
        sql_final = (
            f"SELECT {subquery_alias}.* FROM ({subquery_select}) AS {subquery_alias} "
            f"ORDER BY {subquery_alias}._sort_val {direction}"
        )
        
        offset = (page - 1) * page_size if page > 0 and page_size > 0 else 0
        if page_size > 0:
            sql_final = f"{sql_final} LIMIT {page_size} OFFSET {offset}"
        
        logger.info(f"[ComputedSort] Final SQL: {sql_final}")
        
        try:
            raw_data = self.ds.query(sql_final, params)
            logger.info(f"[ComputedSort] Query returned {len(raw_data)} rows")
        except Exception as e:
            logger.warning(f"[ComputedSort] Query failed: {e}, falling back to standard query")
            return builder.execute(), builder.count_all()
        
        if meta_obj and raw_data:
            main_table_fields = set()
            for f in meta_obj.fields:
                if hasattr(f, 'db_column') and f.db_column:
                    main_table_fields.add(f.db_column)
                else:
                    main_table_fields.add(f.id)
            main_table_fields.update(['id', 'created_at', 'created_by', 'updated_by', 'is_deleted'])
            
            data = []
            seen_ids = set()
            for row in raw_data:
                row_id = row.get('id')
                if row_id in seen_ids:
                    continue
                seen_ids.add(row_id)
                clean_row = {k: v for k, v in row.items() if k in main_table_fields}
                data.append(clean_row)
            
            if meta_obj:
                data = enrich_records(meta_obj.id, data)
                from meta.services.computation_service import computation_service
                ui_computed_columns = []
                if hasattr(meta_obj, 'ui_view_config') and meta_obj.ui_view_config:
                    list_config = getattr(meta_obj.ui_view_config, 'list', None)
                    if list_config and hasattr(list_config, 'columns'):
                        ui_computed_columns = [
                            {'key': col.key, 'computation': getattr(col, 'computation', None)}
                            for col in list_config.columns
                            if getattr(col, 'computed', False) and getattr(col, 'computation', None)
                        ]
                rule_computed = computation_service.get_computed_columns_from_rules(meta_obj.id)
                computed_cols = computation_service.merge_computed_columns(ui_computed_columns, rule_computed)
                if computed_cols:
                    computation_service.compute_batch(self.ds, meta_obj.id, data, computed_cols)
                logger.info(f"[ComputedSort] After enrich+compute, first row {order_field}: {data[0].get(order_field) if data else 'N/A'}")
        else:
            data = raw_data
        
        return data, total

    def _execute_virtual_field_query(
        self,
        builder: QueryBuilder,
        join_clause: str,
        order_alias: str,
        sort_dir: str,
        page: int,
        page_size: int,
        meta_obj: MetaObject = None,
    ) -> tuple:
        return execute_virtual_field_query(
            self.ds, builder, join_clause, order_alias, sort_dir,
            page, page_size, meta_obj, add_table_alias_to_where
        )


    def full_text_search(
        self,
        keyword: str,
        object_types: Optional[List[str]] = None,
        limit: int = 50,
    ) -> Dict[str, List[Dict[str, Any]]]:
        results: Dict[str, List[Dict[str, Any]]] = {}
        pattern = "%{0}%".format(keyword)

        target_types = object_types if object_types else registry.list_objects()

        for object_id in target_types:
            meta_obj = registry.get(object_id)
            if not meta_obj:
                continue

            search_fields = []
            for f in meta_obj.fields:
                if f.id in ("name", "code"):
                    search_fields.append(f.id)

            if not search_fields:
                continue

            builder = QueryBuilder(self.ds, meta_obj)
            or_conditions = [
                (f, QueryOperator.ILIKE, pattern)
                for f in search_fields
            ]
            builder.or_where(or_conditions)
            builder.limit(limit)

            rows = builder.execute()
            if rows:
                results[object_id] = rows

        return results

    def query_by_hierarchy_path(
        self,
        path: str,
        include_children: bool = False,
    ) -> List[Dict[str, Any]]:
        segments = [s.strip() for s in path.strip().split("/") if s.strip()]
        if not segments:
            return []

        depth = len(segments) - 1
        target_object_id = self._resolve_object_id_by_depth(depth)
        if not target_object_id:
            return []

        meta_obj = registry.get(target_object_id)
        if not meta_obj:
            return []

        builder = QueryBuilder(self.ds, meta_obj)

        self._apply_path_name_filters(builder, segments)

        results = builder.execute()

        if include_children:
            child_object_id = self._get_child_object_id(target_object_id)
            if child_object_id:
                child_obj = registry.get(child_object_id)
                if child_obj:
                    parent_ids = [r.get("id") for r in results if r.get("id") is not None]
                    if parent_ids:
                        child_builder = QueryBuilder(self.ds, child_obj)
                        parent_field = self._get_parent_field(child_obj, target_object_id)
                        if parent_field:
                            child_builder.where_in(parent_field, parent_ids)
                            children = child_builder.execute()
                            results.extend(children)

        return results

    def suggest(
        self,
        object_type: str,
        field: str,
        prefix: str,
        limit: int = 10,
    ) -> List[str]:
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return []

        builder = QueryBuilder(self.ds, meta_obj)
        builder.where_ilike(field, "{0}%".format(prefix))
        builder.select(field)
        builder.limit(limit)

        rows = builder.execute()
        return list(dict.fromkeys(r.get(field, "") for r in rows if r.get(field)))

    def _apply_meta_driven_filters(
        self,
        builder: QueryBuilder,
        meta_obj: MetaObject,
        filter_params: Dict[str, str],
        filter_scope: str = 'global'
    ) -> None:
        """
        应用元模型驱动的过滤条件
        
        Args:
            builder: 查询构建器
            meta_obj: 元模型对象
            filter_params: 过滤参数（来自前端）
            filter_scope: 过滤作用域（'global' 或 'local'）
        """
        try:
            from meta.core.redundancy_registry import redundancy_registry

            normalized_params = dict(filter_params)
            suffix_map = {}
            for key in list(filter_params.keys()):
                if key.endswith('__in'):
                    base_key = key[:-4]
                    suffix_map[base_key] = ('in', filter_params[key])
                    if base_key not in normalized_params:
                        normalized_params[base_key] = filter_params[key]
                elif key.endswith('__like'):
                    base_key = key[:-6]
                    suffix_map[base_key] = ('like', filter_params[key])
                    if base_key not in normalized_params:
                        normalized_params[base_key] = filter_params[key]
                elif key.endswith('__gte'):
                    base_key = key[:-5]
                    suffix_map[base_key] = ('>=', filter_params[key])
                    if base_key not in normalized_params:
                        normalized_params[base_key] = filter_params[key]
                elif key.endswith('__lte'):
                    base_key = key[:-5]
                    suffix_map[base_key] = ('<=', filter_params[key])
                    if base_key not in normalized_params:
                        normalized_params[base_key] = filter_params[key]
                elif key.endswith('__gt'):
                    base_key = key[:-4]
                    suffix_map[base_key] = ('>', filter_params[key])
                    if base_key not in normalized_params:
                        normalized_params[base_key] = filter_params[key]
                elif key.endswith('__lt'):
                    base_key = key[:-4]
                    suffix_map[base_key] = ('<', filter_params[key])
                    if base_key not in normalized_params:
                        normalized_params[base_key] = filter_params[key]
            
            logger.debug(
                "_apply_meta_driven_filters: object=%s filter_scope=%s",
                meta_obj.id, filter_scope
            )
            
            virtual_field_filters = []
            computed_field_filters = []
            
            meta_dict = {
                'fields': []
            }
            
            for f in meta_obj.fields:
                storage = getattr(f, 'storage', None)
                is_virtual = storage == FieldStorage.VIRTUAL
                computation = getattr(f, 'computation', None)
                is_computed = computation is not None
                
                in_filter_params = f.id in normalized_params
                semantics_filterable = getattr(f.semantics, 'filterable', None) if f.semantics else None
                if semantics_filterable is None and in_filter_params:
                    semantics_filterable = True

                field_type = f.field_type.value if hasattr(f, 'field_type') else 'string'
                
                default_filter_type = getattr(f.semantics, 'filter_type', None) if f.semantics else None
                if default_filter_type is None:
                    default_filter_type = 'enum' if field_type == 'boolean' else 'text'
                
                if f.id in suffix_map:
                    op_suffix = suffix_map[f.id][0]
                    if op_suffix == 'in':
                        default_filter_type = 'multi-select'
                    elif op_suffix == 'like':
                        default_filter_type = 'text'
                        if f.semantics and hasattr(f.semantics, 'filter_operator'):
                            pass
                        else:
                            semantics_filterable = True
                
                field_info = {
                    'id': f.id,
                    'name': f.name,
                    'db_column': getattr(f, 'db_column', f.id),
                    'type': field_type,
                    'semantics': {
                        'filterable': semantics_filterable if semantics_filterable is not None else False,
                        'filter_type': default_filter_type,
                        'filter_scope': getattr(f.semantics, 'filter_scope', 'both') if f.semantics else 'both',
                        'filter_operator': getattr(f.semantics, 'filter_operator', 'eq') if f.semantics else 'eq',
                    },
                    'is_virtual': is_virtual,
                    'is_computed': is_computed,
                }
                meta_dict['fields'].append(field_info)
                
                if f.id in normalized_params:
                    filter_value = filter_params[f.id]
                    if field_type == 'boolean' and isinstance(filter_value, str):
                        if filter_value.lower() in ('true', '1'):
                            filter_params[f.id] = 1
                            filter_value = 1
                        elif filter_value.lower() in ('false', '0'):
                            filter_params[f.id] = 0
                            filter_value = 0
                    if filter_value is not None and filter_value != '' and filter_value != []:
                        if is_computed:
                            computed_field_filters.append({
                                'field_id': f.id,
                                'value': filter_value,
                                'computation': computation,
                            })
                            logger.info(f"[ComputedFieldFilter] Computed field '{f.id}' with computation type '{computation.get('type')}', will use subquery filter")
                        elif is_virtual:
                            red_def = redundancy_registry.get_redundancy(meta_obj.id, f.id)
                            if red_def and red_def.join_path:
                                virtual_field_filters.append({
                                    'field_id': f.id,
                                    'value': filter_value,
                                    'red_def': red_def,
                                })
                                logger.info(f"[VirtualFieldFilter] Virtual field '{f.id}' has redundancy join_path, will use EXISTS filter")
            
            conditions = filter_service.build_filters_from_meta(
                meta_dict,
                normalized_params,
                filter_scope
            )
            
            for f_id, (op_suffix, raw_value) in suffix_map.items():
                if op_suffix == 'in' and raw_value:
                    field = meta_obj.get_field(f_id) if meta_obj else None
                    if field:
                        db_col = getattr(field, 'db_column', f_id)
                        values = [v.strip() for v in str(raw_value).split(',') if v.strip()]
                        int_values = []
                        for v in values:
                            try:
                                int_values.append(int(v))
                            except ValueError:
                                int_values.append(v)
                        if int_values:
                            builder.where_in(db_col, int_values)
                            logger.info(f"[SuffixFilter] Applied IN filter for {f_id}: {int_values}")
                elif op_suffix in ('>=', '<=', '>', '<', 'like') and raw_value:
                    # __gte/__lte/__gt/__lt/__like 后缀：dispatch 到对应 where_* 方法
                    field = meta_obj.get_field(f_id) if meta_obj else None
                    if field:
                        op = _resolve_operator(op_suffix)
                        method_name = _METHOD_MAP.get(op)
                        if method_name and hasattr(builder, method_name):
                            db_col = getattr(field, 'db_column', f_id)
                            method = getattr(builder, method_name)
                            method(db_col, raw_value)
                            logger.info(f"[SuffixFilter] Applied {op_suffix} filter for {f_id}: {raw_value}")
            
            for cond in conditions:
                field = meta_obj.get_field(cond.field) if meta_obj else None
                if field:
                    storage = getattr(field, 'storage', None)
                    computation = getattr(field, 'computation', None)
                    if storage == FieldStorage.VIRTUAL:
                        if computation:
                            logger.info(f"[ComputedFieldFilter] Skipping computed field '{cond.field}' in standard filter, will use subquery")
                        else:
                            logger.info(f"[VirtualFieldFilter] Skipping virtual field '{cond.field}' in standard filter, will use EXISTS")
                        continue
                
                op = _resolve_operator(cond.operator)
                method_name = _METHOD_MAP.get(op)
                
                if method_name and hasattr(builder, method_name):
                    method = getattr(builder, method_name)
                    method(cond.field, cond.value)
            
            logger.info(f"[MetaFilter] Applied {len(conditions)} filter conditions for {meta_obj.id}")
            
            for cf_filter in computed_field_filters:
                filter_result = self._apply_computed_field_filter(
                    builder, meta_obj, cf_filter['field_id'], cf_filter['value'], cf_filter['computation']
                )
                if filter_result:
                    logger.info(f"[ComputedFieldFilter] Applied subquery filter for computed field '{cf_filter['field_id']}'")
            
            for vf_filter in virtual_field_filters:
                exists_sql, exists_params = self._build_virtual_field_filter_exists(
                    meta_obj, vf_filter['field_id'], vf_filter['value'], vf_filter['red_def']
                )
                if exists_sql:
                    if hasattr(builder, 'where_exists'):
                        builder.where_exists(exists_sql, exists_params)
                        logger.info(f"[VirtualFieldFilter] Applied EXISTS filter for virtual field '{vf_filter['field_id']}'")
            
            logger.info(f"[CrossTableFilter] Checking for cross-table filters with params: {filter_params}")
            self._apply_cross_table_filters(builder, meta_obj, filter_params)
        
        except Exception as e:
            logger.error(f"[MetaFilter] Failed to apply meta-driven filters: {e}")
    
    def _apply_computed_field_filter(
        self,
        builder: QueryBuilder,
        meta_obj: MetaObject,
        field_id: str,
        filter_value: Any,
        computation: dict
    ) -> bool:
        """
        为计算字段应用过滤条件
        
        支持的计算类型:
        - count_relations: 关系数量统计
        - count_children: 子节点数量统计
        
        支持的过滤格式:
        - 数字值: 10 (等于)
        - 比较表达式: ">10", ">=5", "<20", "<=15", "!=0"
        - 范围值: "5-20" (5到20之间)
        
        Args:
            builder: 查询构建器
            meta_obj: 元模型对象
            field_id: 计算字段ID
            filter_value: 过滤值
            computation: 计算配置
            
        Returns:
            是否成功应用过滤
        """
        try:
            import re
            
            comp_type = computation.get('type')
            scope = computation.get('scope', 'self')
            table_name = validate_table_name(meta_obj.table_name)
            object_type = meta_obj.id
            
            logger.info(f"[ComputedFieldFilter] Processing: field={field_id}, value={filter_value}, comp_type={comp_type}, scope={scope}")
            
            op, value = self._parse_filter_value(filter_value)
            if op is None or value is None:
                logger.warning(f"[ComputedFieldFilter] Failed to parse filter value: {filter_value}")
                return False
            
            logger.info(f"[ComputedFieldFilter] Parsed: op={op}, value={value}")
            
            if comp_type == 'count_relations':
                return self._apply_count_relations_filter(
                    builder, table_name, object_type, scope, op, value
                )
            elif comp_type == 'count_children':
                return self._apply_count_children_filter(
                    builder, table_name, object_type, op, value
                )
            else:
                logger.warning(f"[ComputedFieldFilter] Unsupported computation type: {comp_type}")
                return False
                
        except Exception as e:
            logger.error(f"[ComputedFieldFilter] Failed to apply computed field filter: {e}")
            return False
    
    def _parse_filter_value(self, filter_value):
        return parse_filter_value(filter_value)


    def _apply_count_relations_filter(
        self,
        builder: QueryBuilder,
        table_name: str,
        object_type: str,
        scope: str,
        op: str,
        value: Any
    ) -> bool:
        """
        应用关系数量过滤
        
        Args:
            builder: 查询构建器
            table_name: 表名
            object_type: 对象类型
            scope: 作用域 (self/descendants)
            op: 操作符
            value: 过滤值
            
        Returns:
            是否成功应用
        """
        try:
            rel_table = 'relationships'
            
            if scope == 'self' and object_type == 'business_object':
                count_expr = (
                    f"(SELECT COUNT(*) FROM {rel_table} "
                    f"WHERE {rel_table}.source_bo_id = {table_name}.id "
                    f"OR {rel_table}.target_bo_id = {table_name}.id)"
                )
            elif scope == 'descendants':
                if object_type == 'domain':
                    count_expr = (
                        f"(SELECT COUNT(DISTINCT r.id) FROM relationships r "
                        f"WHERE r.source_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                        f"JOIN sub_domains sd ON sm.sub_domain_id = sd.id "
                        f"WHERE sd.domain_id = {table_name}.id) "
                        f"OR r.target_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                        f"JOIN sub_domains sd ON sm.sub_domain_id = sd.id "
                        f"WHERE sd.domain_id = {table_name}.id))"
                    )
                elif object_type == 'sub_domain':
                    count_expr = (
                        f"(SELECT COUNT(DISTINCT r.id) FROM relationships r "
                        f"WHERE r.source_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                        f"WHERE sm.sub_domain_id = {table_name}.id) "
                        f"OR r.target_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                        f"WHERE sm.sub_domain_id = {table_name}.id))"
                    )
                elif object_type == 'service_module':
                    count_expr = (
                        f"(SELECT COUNT(DISTINCT r.id) FROM relationships r "
                        f"WHERE r.source_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"WHERE bo.service_module_id = {table_name}.id) "
                        f"OR r.target_bo_id IN ("
                        f"SELECT bo.id FROM business_objects bo "
                        f"WHERE bo.service_module_id = {table_name}.id))"
                    )
                else:
                    logger.warning(f"[ComputedFieldFilter] Unknown object_type for descendants scope: {object_type}")
                    return False
            else:
                logger.warning(f"[ComputedFieldFilter] Unsupported count_relations scope/object: scope={scope}, object_type={object_type}")
                return False
            
            where_clause = self._build_computed_where_clause(count_expr, op, value)
            if where_clause:
                builder.where_raw(where_clause)
                logger.info(f"[ComputedFieldFilter] Applied count_relations filter: {where_clause}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[ComputedFieldFilter] Failed to apply count_relations filter: {e}")
            return False
    
    def _apply_count_children_filter(
        self,
        builder: QueryBuilder,
        table_name: str,
        object_type: str,
        op: str,
        value: Any
    ) -> bool:
        """
        应用子节点数量过滤
        
        Args:
            builder: 查询构建器
            table_name: 表名
            object_type: 对象类型
            op: 操作符
            value: 过滤值
            
        Returns:
            是否成功应用
        """
        try:
            if object_type == 'service_module':
                count_expr = (
                    f"(SELECT COUNT(*) FROM business_objects bo "
                    f"WHERE bo.service_module_id = {table_name}.id)"
                )
            elif object_type == 'sub_domain':
                count_expr = (
                    f"(SELECT COUNT(*) FROM service_modules sm "
                    f"WHERE sm.sub_domain_id = {table_name}.id)"
                )
            elif object_type == 'domain':
                count_expr = (
                    f"(SELECT COUNT(*) FROM sub_domains sd "
                    f"WHERE sd.domain_id = {table_name}.id)"
                )
            else:
                logger.warning(f"[ComputedFieldFilter] Unknown object_type for count_children: {object_type}")
                return False
            
            where_clause = self._build_computed_where_clause(count_expr, op, value)
            if where_clause:
                builder.where_raw(where_clause)
                logger.info(f"[ComputedFieldFilter] Applied count_children filter: {where_clause}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[ComputedFieldFilter] Failed to apply count_children filter: {e}")
            return False
    
    def _build_computed_where_clause(self, count_expr: str, op: str, value) -> Optional[str]:
        return build_computed_where_clause(count_expr, op, value)


    def _build_virtual_field_filter_exists(
        self, meta_obj, field_id, filter_value, red_def
    ):
        return build_virtual_field_filter_exists(meta_obj, field_id, filter_value, red_def)


    def _apply_cross_table_filters(
        self,
        builder: QueryBuilder,
        meta_obj: MetaObject,
        filter_params: Dict[str, str]
    ) -> None:
        """
        应用跨表关联过滤（SAP CDS Association + Path Expression 风格）
        
        支持通过 EXISTS 子查询实现跨表过滤，例如：
        - 按备注类型过滤业务对象
        - 按备注内容搜索业务对象
        
        Args:
            builder: 查询构建器
            meta_obj: 元模型对象
            filter_params: 过滤参数（来自前端）
        """
        try:
            # 获取跨表过滤配置
            analytical_model = getattr(meta_obj, 'analytical_model', None)
            if not analytical_model:
                return
            
            cross_table_filters = analytical_model.get('cross_table_filters', [])
            if not cross_table_filters:
                return
            
            logger.info(f"[CrossTableFilter] Checking {len(cross_table_filters)} cross-table filters for {meta_obj.id}")
            
            for ctf in cross_table_filters:
                ctf_id = ctf.get('id')
                association = ctf.get('association', {})
                where_conditions = association.get('where_conditions', [])
                
                if not where_conditions:
                    continue
                
                # 检查是否有对应的过滤参数（且值不为空）
                has_filter = False
                filter_values = {}
                
                for wc in where_conditions:
                    param_name = wc.get('parameter')
                    if param_name and param_name in filter_params:
                        param_value = filter_params[param_name]
                        # 跳过空值，让过滤不生效
                        if param_value is None or param_value == '' or param_value == []:
                            continue
                        has_filter = True
                        filter_values[param_name] = param_value
                
                if not has_filter:
                    continue
                
                logger.info(f"[CrossTableFilter] Applying cross-table filter: {ctf_id} with values: {filter_values}")
                
                # 构建 EXISTS 子查询
                exists_sql, exists_params = self._build_exists_subquery(
                    meta_obj,
                    association,
                    filter_values
                )
                
                if exists_sql:
                    # 使用 QueryBuilder 的 where_exists 方法
                    if hasattr(builder, 'where_exists'):
                        builder.where_exists(exists_sql, exists_params)
                        logger.info(f"[CrossTableFilter] Applied EXISTS filter: {exists_sql[:100]}... with params: {exists_params}")
                    else:
                        # 如果 QueryBuilder 不支持 where_exists，使用 where_raw
                        if hasattr(builder, 'where_raw'):
                            builder.where_raw(f"EXISTS ({exists_sql})", exists_params)
                            logger.info(f"[CrossTableFilter] Applied raw EXISTS filter")
            
        except Exception as e:
            logger.error(f"[CrossTableFilter] Failed to apply cross-table filters: {e}")
    
    def _build_exists_subquery(self, meta_obj, association, filter_values):
        return build_exists_subquery(meta_obj, association, filter_values)


    def _apply_data_permission(
        self,
        builder: QueryBuilder,
        meta_obj: MetaObject,
        object_type: str,
    ) -> None:
        try:
            from meta.services.auth_middleware import get_current_user, is_admin
            from meta.services.data_permission_filter import DataPermissionFilter

            user = get_current_user()
            if not user or is_admin(user):
                return

            user_id = user.get('user_id')
            if not user_id:
                return

            perm_filter = DataPermissionFilter(self.ds)
            
            allowed_ids = perm_filter.perm_service.get_allowed_resource_ids(user_id, object_type)
            
            if allowed_ids is None:
                return

            if not allowed_ids:
                # [FIX v3.18.1 2026-06-09] 无 data_permissions 旧表配置 → 允许所有
                #   之前错误地加 id = -1 拒绝 filter
                #   与 DataPermissionFilter.apply_filter (data_permission_filter.py:33) 行为一致
                #   这样 dimension scope 用户 (无 data_perms 配置) 不会被误拒
                logger.info(f"[DataPerm] No data permissions for {object_type}, allowing all (rely on dimension scope)")
                return

            if len(allowed_ids) == 1:
                builder.where('id', QueryOperator.EQ, allowed_ids[0])
            else:
                builder.where_in('id', allowed_ids)
            
            logger.info(f"[DataPerm] Applied filter for {object_type}: {len(allowed_ids)} IDs")
        except Exception as e:
            logger.warning(f"[DataPerm] Failed to apply data permission: {e}")

    def _apply_soft_delete_filter(
        self,
        builder: QueryBuilder,
        meta_obj: MetaObject,
        include_deleted: bool = False,
        deleted_only: bool = False,
    ) -> None:
        if not include_deleted:
            return
        soft_delete_field = None
        for f in meta_obj.fields:
            semantics = getattr(f, 'semantics', {})
            if isinstance(semantics, dict) and semantics.get('meaning') == 'soft_delete':
                soft_delete_field = f.id
                break
            elif hasattr(f, 'meaning') and f.meaning == 'soft_delete':
                soft_delete_field = f.id
                break
        if soft_delete_field:
            if deleted_only:
                builder.where(soft_delete_field, QueryOperator.IS_NOT_NULL)
            else:
                builder.where_null(soft_delete_field)

    def _apply_hierarchy_filter(
        self,
        builder: QueryBuilder,
        meta_obj: MetaObject,
        hierarchy_path: str,
    ) -> None:
        return apply_hierarchy_filter(self.ds, builder, meta_obj, hierarchy_path)

    def _apply_path_name_filters(
        self,
        builder: QueryBuilder,
        segments: List[str],
    ) -> None:
        return apply_path_name_filters(self.ds, builder, segments)


    def _resolve_object_id_by_depth(self, depth: int) -> Optional[str]:
        return resolve_object_id_by_depth(depth)

    def _get_name_field(self, meta_obj: MetaObject) -> Optional[str]:
        return get_name_field(meta_obj)

    def _get_child_object_id(self, object_id: str) -> Optional[str]:
        return get_child_object_id(object_id)

    def _get_parent_field(self, child_obj: MetaObject, parent_object_id: str) -> Optional[str]:
        return get_parent_field(child_obj, parent_object_id)

    def _get_ancestor_parent_field(self, meta_obj: MetaObject, ancestor_id: str) -> Optional[str]:
        return get_ancestor_parent_field(meta_obj, ancestor_id)

    def _enrich_with_relations(
        self,
        meta_obj: MetaObject,
        data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not data:
            return data

        for rel in meta_obj.relations:
            target_obj = registry.get(rel.target_object)
            if not target_obj:
                continue

            target_field = rel.target_field if rel.target_field and rel.target_field != "id" else "id"
            source_field = rel.source_field if rel.source_field else "id"

            source_values = list(set(
                row.get(source_field) for row in data
                if row.get(source_field) is not None
            ))
            if not source_values:
                for row in data:
                    row["_rel_{0}".format(rel.id)] = []
                continue

            try:
                rel_builder = QueryBuilder(self.ds, target_obj)
                rel_builder.where_in(target_field, source_values)
                all_related = rel_builder.execute()

                related_map: Dict[Any, List[Dict]] = {}
                for rel_row in all_related:
                    key = rel_row.get(target_field)
                    if key is None:
                        continue
                    if key not in related_map:
                        related_map[key] = []
                    related_map[key].append(rel_row)

                for row in data:
                    source_val = row.get(source_field)
                    row["_rel_{0}".format(rel.id)] = \
                        related_map.get(source_val, []) if source_val is not None else []
            except Exception:
                logger.error("Failed to enrich relations for %s rel=%s", meta_obj.id, rel.id)
                for row in data:
                    row["_rel_{0}".format(rel.id)] = []

        return data

    def aggregate(self, request: AggregateRequest) -> AggregateResult:
        meta_obj = registry.get(request.object_type)
        if not meta_obj:
            return AggregateResult(
                success=False,
                data=[],
                total=0,
                message="Object type not found: {0}".format(request.object_type),
            )

        if not request.measures:
            return AggregateResult(
                success=False,
                data=[],
                total=0,
                message="At least one measure is required",
            )

        builder = QueryBuilder(self.ds, meta_obj)

        for f in request.filters:
            self._apply_filter(builder, f)

        for dim in request.dimensions:
            builder.select(dim)

        for measure in request.measures:
            agg_func = measure.aggregation.lower()
            if agg_func == "sum":
                builder.sum(measure.field, "{0}_{1}".format(agg_func, measure.field))
            elif agg_func == "avg":
                builder.avg(measure.field, "{0}_{1}".format(agg_func, measure.field))
            elif agg_func == "max":
                builder.max(measure.field, "{0}_{1}".format(agg_func, measure.field))
            elif agg_func == "min":
                builder.min(measure.field, "{0}_{1}".format(agg_func, measure.field))
            elif agg_func == "count":
                builder.count(measure.field, "{0}_{1}".format(agg_func, measure.field))
            else:
                return AggregateResult(
                    success=False,
                    data=[],
                    total=0,
                    message="Unsupported aggregation function: {0}".format(measure.aggregation),
                )

        if request.dimensions:
            builder.group_by(*request.dimensions)

        try:
            data = builder.execute()
            if request.dimensions:
                data = enrich_dimension_names(meta_obj, data)
            return AggregateResult(
                success=True,
                data=data,
                total=len(data),
                message="",
            )
        except Exception as e:
            logger.error("Aggregate query failed: %s", str(e))
            return AggregateResult(
                success=False,
                data=[],
                total=0,
                message="Query failed: {0}".format(str(e)),
            )

    def _apply_filter(self, builder: QueryBuilder, f: Dict) -> None:
        op = f.get('operator', 'eq').lower()
        field = f.get('field', '')
        value = f.get('value')
        values = f.get('values', [])

        if op == 'eq':
            builder.where_eq(field, value)
        elif op == 'ne':
            builder.where_ne(field, value)
        elif op == 'gt':
            builder.where_gt(field, value)
        elif op == 'ge':
            builder.where_ge(field, value)
        elif op == 'lt':
            builder.where_lt(field, value)
        elif op == 'le':
            builder.where_le(field, value)
        elif op == 'like':
            builder.where_like(field, value)
        elif op == 'ilike':
            builder.where_ilike(field, value)
        elif op == 'in':
            builder.where_in(field, values if values else [value])
        elif op == 'not_in':
            builder.where_not_in(field, values if values else [value])
        elif op == 'is_null':
            builder.where_null(field)
        elif op == 'is_not_null':
            builder.where_not_null(field)
        elif op == 'between':
            if len(values) >= 2:
                builder.where_between(field, values[0], values[1])
