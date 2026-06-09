# -*- coding: utf-8 -*-
import logging
import re
from typing import Dict, Any

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext, ActionResult
from meta.core.action_executor import ActionRegistry
from meta.core.association_engine import AssociationEngine
from meta.core.enrich_utils import enrich_fk_display_names as _shared_enrich_fk, enrich_association_counts as _shared_enrich_counts
from meta.core.models import FieldStorage
# [FIX 2026-06-04] Reuse the Element Plus sortable column index suffix stripper
# from sql_adapters. Frontend (el-table) sends ordering like "-updated_at:1"
# where ":1" is the column index, not part of the field name.
from meta.core.sql_adapters import _SORTABLE_INDEX_SUFFIX

# [DECORATIVE] v3.18: trace_id 支持
try:
    from meta.core.trace_id import TraceId
    _trace_id_available = True
except ImportError:
    _trace_id_available = False

logger = logging.getLogger(__name__)


class PersistenceInterceptor(Interceptor):
    """
    持久化拦截器

    负责实际的数据持久化操作，复用现有的 ActionExecutor。
    关联操作委托给 AssociationEngine。
    """

    @property
    def priority(self) -> int:
        return 95

    def __init__(self):
        self._registry = None
        self._association_engine = AssociationEngine()

    def _get_registry(self, context: ActionContext) -> ActionRegistry:
        if self._registry is None:
            self._registry = ActionRegistry(context.data_source)
        return self._registry

    def before_action(self, context: ActionContext) -> None:
        pass
    
    def should_execute(self, context: ActionContext) -> bool:
        """PersistenceInterceptor应该执行所有CRUD操作"""
        return True
    
    def after_action(self, context: ActionContext) -> None:
        logger.debug(f"[PersistenceInterceptor] after_action: action={context.action}")
        
        if not (context.is_crud_action or context.action in (
            'associate', 'dissociate', 'query_associations',
            'batch_query_associations',
            'assign', 'unassign', 'batch_assign', 'batch_unassign',
            'count',
            'query', 'list', 'read'
        )):
            return

        registry = self._get_registry(context)

        # [DECORATIVE] v3.18: trace_id 注入到 context
        if _trace_id_available:
            trace_id = TraceId.get()
            if trace_id and hasattr(context, 'trace_id'):
                context.trace_id = trace_id

        try:
            if context.is_create_action:
                result = self._do_create(context, registry)
            elif context.is_read_action:
                result = self._do_read(context, registry)
            elif context.is_update_action:
                result = self._do_update(context, registry)
            elif context.is_delete_action:
                result = self._do_delete(context, registry)
            elif context.action in ('crud_list', 'crud_query', 'query', 'list'):
                result = self._do_list(context, registry)
            elif context.action == 'associate':
                result = self._association_engine.associate(context)
            elif context.action == 'dissociate':
                result = self._association_engine.dissociate(context)
            elif context.action == 'query_associations':
                result = self._association_engine.query_associations(context)
            elif context.action == 'batch_query_associations':
                result = self._association_engine.batch_query_associations(context)
            elif context.action == 'assign':
                result = self._association_engine.assign(context)
            elif context.action == 'unassign':
                result = self._association_engine.unassign(context)
            elif context.action == 'batch_assign':
                result = self._association_engine.batch_assign(context)
            elif context.action == 'batch_unassign':
                result = self._association_engine.batch_unassign(context)
            elif context.action == 'count':
                result = self._association_engine.count(context)
            else:
                result = ActionResult(success=True, message="No persistence action needed")

            context.result = result

        except Exception as e:
            logger.error(f"[PersistenceInterceptor] Error: {e}", exc_info=True)
            context.result = ActionResult(success=False, message=str(e), errors=[str(e)])
            raise

    def _do_create(self, context: ActionContext, registry: ActionRegistry) -> ActionResult:
        meta_object = context.meta_object
        data = context.params

        result = registry.create(meta_object, data)

        if result.success:
            if result.data and 'id' in result.data:
                context.params['id'] = result.data['id']

            return ActionResult(
                success=True,
                data=result.data,
                message=result.message or '创建成功',
            )
        else:
            errors = getattr(result, 'errors', []) or [result.error] if getattr(result, 'error', '') else []
            return ActionResult(
                success=False,
                message=result.message or '创建失败',
                errors=errors,
            )

    def _do_read(self, context: ActionContext, registry: ActionRegistry) -> ActionResult:
        meta_object = context.meta_object
        object_id = context.object_id

        result = registry.read(meta_object, object_id)

        if result.success:
            # 注入 FK display names（与 _do_list 保持一致）
            try:
                if result.data:
                    result.data = self._enrich_fk_display_names(meta_object, result.data, registry.ds)
            except Exception as e:
                logger.warning(f"[_do_read] _enrich_fk_display_names failed: {e}")
            return ActionResult(
                success=True,
                data=result.data,
                message=result.message or '查询成功',
            )
        else:
            return ActionResult(
                success=False,
                message=result.message or '记录不存在',
            )

    def _do_update(self, context: ActionContext, registry: ActionRegistry) -> ActionResult:
        meta_object = context.meta_object
        object_id = context.object_id
        data = context.params

        # [NEW 2026-06-07] 过滤 immutable 字段 (业务主键不可改)
        # schema 中 semantics.immutable=true 的字段在 update 时被静默忽略
        data = self._filter_immutable_fields(meta_object, data)

        result = registry.update(meta_object, object_id, data)

        if result.success:
            return ActionResult(
                success=True,
                data=result.data,
                message=result.message or '更新成功',
            )
        else:
            return ActionResult(
                success=False,
                message=result.message or '更新失败',
            )

    def _do_delete(self, context: ActionContext, registry: ActionRegistry) -> ActionResult:
        meta_object = context.meta_object
        object_id = context.object_id

        result = registry.delete(meta_object, object_id)

        if result.success:
            return ActionResult(
                success=True,
                data=result.data,
                message=result.message or '删除成功',
            )
        else:
            return ActionResult(
                success=False,
                message=result.message or '删除失败',
            )

    def _filter_immutable_fields(self, meta_object, data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤 schema 中声明 immutable=true 的字段, 防止业务主键被修改

        业务规则: role.code, user.username 等 semantics.immutable=true 的字段
        在 update 操作中应被忽略 (schema 是单一事实源)。
        """
        if not data or not meta_object:
            return data
        try:
            fields = getattr(meta_object, 'fields', None) or []
            immutable_ids = set()
            for f in fields:
                sem = getattr(f, 'semantics', None) or {}
                if isinstance(sem, dict) and sem.get('immutable'):
                    fid = getattr(f, 'id', None) or getattr(f, 'name', None)
                    if fid:
                        immutable_ids.add(fid)
            if not immutable_ids:
                return data
            filtered = {k: v for k, v in data.items() if k not in immutable_ids}
            removed = set(data.keys()) - set(filtered.keys())
            if removed:
                logger.info(f"[PersistenceInterceptor] Filtered immutable fields: {removed}")
            return filtered
        except Exception as e:
            logger.warning(f"[PersistenceInterceptor] _filter_immutable_fields failed: {e}")
            return data

    def _build_scope_conditions(self, context: ActionContext):
        """
        Convert query_conditions from data_permission_interceptor
        into SQL condition strings and parameters.

        Supports:
          - Simple: { 'field': 'visibility', 'operator': 'eq', 'value': 'public' }
          - OR group: { 'type': 'or', 'conditions': [{...}, {...}] }
        """
        from meta.core.action_context import ActionContext as _AC
        query_conditions = context.extra.get('query_conditions', []) if hasattr(context, 'extra') else []
        if not query_conditions:
            return [], []

        OP_MAP = {
            'eq': '=', 'neq': '!=', 'gt': '>', 'lt': '<',
            'gte': '>=', 'lte': '<=', 'like': 'LIKE',
            'in': 'IN', 'nin': 'NOT IN',  # [FIX v1.0.2] 支持 in/nin 操作符
        }

        conditions = []
        params = []

        for cond in query_conditions:
            if cond.get('type') == 'or':
                or_parts = []
                for c in cond.get('conditions', []):
                    field = c.get('field', '')
                    op = c.get('operator', 'eq')
                    value = c.get('value')
                    if op == 'in_subquery':
                        or_parts.append(f"{field} IN ({value})")
                    elif op in ('in', 'nin'):
                        # [FIX v1.0.2] 列表值用 IN (...) 展开
                        values = c.get('values', value if isinstance(value, list) else [value])
                        placeholders = ','.join('?' * len(values))
                        or_parts.append(f"{field} {OP_MAP[op]} ({placeholders})")
                        params.extend(values)
                    else:
                        sql_op = OP_MAP.get(op, '=')
                        or_parts.append(f"{field} {sql_op} ?")
                        params.append(value)
                if or_parts:
                    conditions.append("(" + " OR ".join(or_parts) + ")")
            else:
                field = cond.get('field', '')
                op = cond.get('operator', 'eq')
                value = cond.get('value')
                if op == 'in_subquery':
                    conditions.append(f"{field} IN ({value})")
                elif op in ('in', 'nin'):
                    # [FIX v1.0.2] 列表值用 IN (...) 展开
                    values = cond.get('values', value if isinstance(value, list) else [value])
                    placeholders = ','.join('?' * len(values))
                    conditions.append(f"{field} {OP_MAP[op]} ({placeholders})")
                    params.extend(values)
                else:
                    sql_op = OP_MAP.get(op, '=')
                    conditions.append(f"{field} {sql_op} ?")
                    params.append(value)

        return conditions, params

    def _build_ctf_exists(self, meta_object, ctf_config, param_values):
        association = ctf_config.get('association', {})
        target_table = association.get('target_table')
        target_alias = association.get('target_alias', 't')
        on_conditions = association.get('on_conditions', [])
        where_conditions = association.get('where_conditions', [])
        main_table = meta_object.table_name

        def _resolve_field(field_str):
            if (field_str.startswith("'") and field_str.endswith("'")) or \
               (field_str.startswith('"') and field_str.endswith('"')):
                return None, field_str[1:-1]
            if '.' in field_str:
                prefix, col = field_str.rsplit('.', 1)
                if prefix == target_alias:
                    return f"{target_alias}.{col}", None
                elif prefix != main_table:
                    return f"{main_table}.{col}", None
                return f"{prefix}.{col}", None
            return f"{main_table}.{field_str}", None

        on_parts = []
        on_params = []

        for cond in on_conditions:
            left = str(cond.get('left_field', ''))
            right = str(cond.get('right_field', ''))
            operator = cond.get('operator', 'eq')
            sql_op = '=' if operator == 'eq' else operator

            left_resolved, left_literal = _resolve_field(left)
            right_resolved, right_literal = _resolve_field(right)

            if left_literal is not None and right_literal is not None:
                on_parts.append(f"? {sql_op} ?")
                on_params.extend([left_literal, right_literal])
            elif left_literal is not None:
                on_parts.append(f"? {sql_op} {right_resolved}")
                on_params.append(left_literal)
            elif right_literal is not None:
                on_parts.append(f"{left_resolved} {sql_op} ?")
                on_params.append(right_literal)
            else:
                on_parts.append(f"{left_resolved} {sql_op} {right_resolved}")

        where_parts = []
        where_params = []
        for cond in where_conditions:
            field = str(cond.get('field', ''))
            operator = cond.get('operator', 'eq')
            col = field.rsplit('.', 1)[-1] if '.' in field else field
            alias = field.rsplit('.', 1)[0] if '.' in field else target_alias

            if operator == 'in':
                placeholders = ', '.join(['?' for _ in param_values])
                where_parts.append(f"{alias}.{col} IN ({placeholders})")
                where_params.extend(param_values)
            elif operator == 'like':
                where_parts.append(f"{alias}.{col} LIKE ?")
                where_params.append(f'%{param_values[0]}%')
            else:
                where_parts.append(f"{alias}.{col} = ?")
                where_params.append(param_values[0])

        on_clause = ' AND '.join(on_parts)
        where_clause = ' AND '.join(where_parts)

        exists_sql = f"EXISTS (SELECT 1 FROM {target_table} {target_alias} WHERE {on_clause} AND {where_clause})"
        all_params = on_params + where_params
        return exists_sql, all_params

    def _do_list(self, context: ActionContext, registry: ActionRegistry) -> ActionResult:
        meta_object = context.meta_object
        params = context.params

        order_by = params.get("_order_by")
        # [FIX 2026-06-04] 去掉 Element Plus 可排序列索引后缀 ":N"（如 "-updated_at:1"）
        # 必须在任何下游处理（_resolve_virtual_sort / 字段查找 / SELECT 增强）之前剥离，
        # 否则 ":1" 会被当成字段名的一部分传递下去。
        if order_by:
            order_by = _SORTABLE_INDEX_SUFFIX.sub('', order_by)
        logger.info(f"[_do_list] order_by={order_by}, params keys={list(params.keys())}")
        limit = params.get("_limit")
        offset = params.get("_offset")

        page = params.get("page")
        page_size = params.get("page_size")
        if page is not None and page_size is not None:
            try:
                offset = (int(page) - 1) * int(page_size)
                limit = int(page_size)
            except (ValueError, TypeError):
                pass

        try:
            safe_limit = min(int(limit or 20), 500)
            safe_offset = max(int(offset or 0), 0)
        except (ValueError, TypeError):
            safe_limit = 20
            safe_offset = 0

        search_keyword = params.get("search") or params.get("keyword")

        analytical_model = getattr(meta_object, 'analytical_model', None)
        cross_table_filters = analytical_model.get('cross_table_filters', []) if analytical_model else []

        ctf_param_map = {}
        for ctf in cross_table_filters:
            for wc in ctf.get('association', {}).get('where_conditions', []):
                ctf_param_map[wc.get('parameter', '')] = ctf

        filters = {}
        special_params = ["_order_by", "_limit", "_offset", "page", "page_size", "search", "keyword", "filters", "ordering"]
        ctf_exists_clauses = []
        ctf_exists_params = []
        # computed *_count 字段的过滤子句（使用子查询，不能走普通 _build_conditions）
        computed_conditions = []
        computed_params = []
        # [FIX 2026-06-09] semantic 派生字段过滤 (category_label/category_type)：
        # 不在 DB 中，需要 LEFT JOIN 业务对象/服务模块/子领域/领域层级表，
        # 再用 CASE WHEN 表达式对比 source/target 的层级关系生成可比较的值。
        semantic_join_clauses = []

        nested_filters = params.get("filters")
        if isinstance(nested_filters, dict):
            for key, value in nested_filters.items():
                params[key] = value

        ordering = params.get("ordering")
        if ordering and not order_by:
            order_by = ordering
        
        default_updated_at_sort = False
        if not order_by:
            updated_at_field = meta_object.get_field('updated_at') if meta_object else None
            if updated_at_field:
                order_by = '-updated_at'
                default_updated_at_sort = True
                logger.info(f"[_do_list] No order specified, defaulting to updated_at desc")

        for key, value in params.items():
            if key not in special_params:
                # [FIX] computed *_count 字段过滤（如 member_count >= 3）：
                # DB 中该列为 NULL，排序/过滤都不能直接用 db_column，
                # 必须用子查询通过关联表 COUNT。
                computed_clause, computed_filter_params = self._try_build_computed_filter(
                    meta_object, key, value
                )
                if computed_clause is not None:
                    computed_conditions.append(computed_clause)
                    computed_params.extend(computed_filter_params)
                    continue
                # [FIX 2026-06-09] semantic 派生字段过滤 (category_label/category_type)：
                # 与 computed_*_count 不同，这里返回 (joins, where_clause, params)
                # - joins 会被收集到 semantic_join_clauses 用于 SQL FROM 后插入
                # - where_clause 是 CASE WHEN ... = ? 的可比较表达式
                sem_joins, sem_where, sem_params = self._try_build_semantic_filter(
                    meta_object, key, value
                )
                if sem_where is not None:
                    semantic_join_clauses.extend(sem_joins)
                    computed_conditions.append(sem_where)
                    computed_params.extend(sem_params)
                    continue
                if key.endswith('__in'):
                    field_name = key[:-4]
                    field = meta_object.get_field(field_name)
                    if field:
                        field_storage = getattr(field, 'storage', None)
                        if field_storage == FieldStorage.VIRTUAL:
                            logger.warning(f"[_do_list] Ignoring filter for virtual field: {field_name}")
                        else:
                            values = [v.strip() for v in value.split(',') if v.strip()]
                            if values:
                                filters[f"{field.db_column} IN"] = values
                    elif field_name in ctf_param_map:
                        values = [v.strip() for v in str(value).split(',') if v.strip()]
                        if values:
                            ctf = ctf_param_map[field_name]
                            exists_sql, exists_params = self._build_ctf_exists(meta_object, ctf, values)
                            ctf_exists_clauses.append(exists_sql)
                            ctf_exists_params.extend(exists_params)
                    else:
                        logger.warning(f"[_do_list] Unknown filter field: {field_name}")

                elif key.endswith('__like'):
                    field_name = key[:-6]
                    field = meta_object.get_field(field_name)
                    if field:
                        field_storage = getattr(field, 'storage', None)
                        if field_storage == FieldStorage.VIRTUAL:
                            logger.warning(f"[_do_list] Ignoring filter for virtual field: {field_name}")
                        else:
                            filters[f"{field.db_column} LIKE"] = f"%{value}%"
                    elif field_name in ctf_param_map:
                        values = [str(value).strip()]
                        if values and values[0]:
                            ctf = ctf_param_map[field_name]
                            exists_sql, exists_params = self._build_ctf_exists(meta_object, ctf, values)
                            ctf_exists_clauses.append(exists_sql)
                            ctf_exists_params.extend(exists_params)
                    else:
                        logger.warning(f"[_do_list] Unknown filter field: {field_name}")

                elif key.endswith('_start'):
                    base_field = key[:-6]
                    field = meta_object.get_field(base_field)
                    if field:
                        field_storage = getattr(field, 'storage', None)
                        if field_storage == FieldStorage.VIRTUAL:
                            logger.warning(f"[_do_list] Ignoring filter for virtual field: {base_field}")
                        else:
                            filters[f"{field.db_column} >="] = value
                    else:
                        filters[f"{base_field} >="] = value

                elif key.endswith('_end'):
                    base_field = key[:-4]
                    field = meta_object.get_field(base_field)
                    if field:
                        field_storage = getattr(field, 'storage', None)
                        if field_storage == FieldStorage.VIRTUAL:
                            logger.warning(f"[_do_list] Ignoring filter for virtual field: {base_field}")
                        else:
                            filters[f"{field.db_column} <="] = value
                    else:
                        filters[f"{base_field} <="] = value

                elif key == 'exclude_ids' and value:
                    values = []
                    for v in str(value).split(','):
                        v = v.strip()
                        if v:
                            try:
                                values.append(int(v))
                            except (ValueError, TypeError):
                                logger.warning(f"[_do_list] Skipping non-integer exclude_ids value: {v}")
                    if values:
                        filters["id__notin"] = values

                else:
                    field = meta_object.get_field(key)
                    if field:
                        field_storage = getattr(field, 'storage', None)
                        if field_storage == FieldStorage.VIRTUAL:
                            logger.warning(f"[_do_list] Ignoring filter for virtual field: {key}")
                        else:
                            filter_value = value
                            field_type = getattr(field, 'field_type', None)
                            if field_type and hasattr(field_type, 'value'):
                                type_value = field_type.value
                                if type_value == 'boolean' and isinstance(filter_value, str):
                                    if filter_value.lower() in ('true', '1'):
                                        filter_value = 1
                                    elif filter_value.lower() in ('false', '0'):
                                        filter_value = 0
                            filters[field.db_column] = filter_value
                    else:
                        logger.warning(f"[_do_list] Ignoring unknown filter field: {key}")

        scope_conditions, scope_params = self._build_scope_conditions(context)

        search_or_conditions = []
        search_or_params = []

        if search_keyword and str(search_keyword).strip():
            search_keyword = str(search_keyword).strip()

            if hasattr(meta_object, 'fields') and meta_object.fields:
                for f in meta_object.fields:
                    field_name = getattr(f, 'name', getattr(f, 'key', ''))
                    db_column = getattr(f, 'db_column', field_name)

                    field_type = getattr(f, 'field_type', None)
                    if field_type is not None:
                        type_value = field_type.value if hasattr(field_type, 'value') else str(field_type)
                    else:
                        continue

                    is_text_type = type_value in ('string', 'text', 'varchar', 'email')
                    is_hidden = getattr(f, 'hidden_filter', False)
                    field_storage = getattr(f, 'storage', None)
                    is_virtual = field_storage == FieldStorage.VIRTUAL

                    if is_text_type and not is_hidden and db_column and not is_virtual:
                        search_or_conditions.append(f"{db_column} LIKE ?")
                        search_or_params.append(f"%{search_keyword}%")

        try:
            virtual_sort = self._resolve_virtual_sort(meta_object, order_by)

            if search_or_conditions:
                # [FIX 2026-06-08] 传 table_prefix 消除 JOIN 后的列名歧义
                # (例：relationship JOIN business_objects 后 `version_id` 两表都有)
                and_conditions, and_params = registry.ds._build_conditions(filters, meta_object.table_name) if filters else ([], [])

                all_where_clauses = []
                all_params = []

                if and_conditions:
                    all_where_clauses.append("(" + " AND ".join(and_conditions) + ")")
                    all_params.extend(and_params)

                if scope_conditions:
                    all_where_clauses.append("(" + " AND ".join(scope_conditions) + ")")
                    all_params.extend(scope_params)

                or_clause = "(" + " OR ".join(search_or_conditions) + ")"
                all_where_clauses.append(or_clause)
                all_params.extend(search_or_params)

                if ctf_exists_clauses:
                    all_where_clauses.extend(ctf_exists_clauses)
                    all_params.extend(ctf_exists_params)

                if computed_conditions:
                    all_where_clauses.append("(" + " AND ".join(computed_conditions) + ")")
                    all_params.extend(computed_params)

                where_sql = ""
                if all_where_clauses:
                    where_sql = "WHERE " + " AND ".join(all_where_clauses)

                # [FIX 2026-06-09] semantic JOIN 子句 (category_label/category_type filter)
                semantic_join_sql = " ".join(semantic_join_clauses) if semantic_join_clauses else ""

                count_sql = f"SELECT COUNT(*) as count FROM {meta_object.table_name} {semantic_join_sql} {where_sql}"
                rows, columns = self._execute_for_list(registry, count_sql, all_params, bool(computed_conditions))
                total_row = rows[0] if rows else None
                total = (total_row['count'] if isinstance(total_row, dict) else total_row[0]) if total_row else 0

                if virtual_sort:
                    join_clause, sort_expr = virtual_sort
                    sql = f"SELECT {meta_object.table_name}.* FROM {meta_object.table_name} {semantic_join_sql} {join_clause} {where_sql} ORDER BY {sort_expr} LIMIT ? OFFSET ?"
                elif order_by:
                    field = meta_object.get_field(order_by.lstrip('-'))
                    if field:
                        # [FIX] computed *_count 字段（如 member_count）DB 列为 NULL，
                        # 排序需用子查询通过关联表 COUNT
                        computed_sort = self._build_computed_count_sort_clause(
                            meta_object, order_by.lstrip('-'), order_by.startswith('-')
                        )
                        if computed_sort:
                            sql = f"SELECT * FROM {meta_object.table_name} {semantic_join_sql} {where_sql} ORDER BY {computed_sort} LIMIT ? OFFSET ?"
                        else:
                            db_column = getattr(field, 'db_column', order_by.lstrip('-'))
                            direction = 'DESC' if order_by.startswith('-') else 'ASC'
                            sql = f"SELECT * FROM {meta_object.table_name} {semantic_join_sql} {where_sql} ORDER BY {db_column} {direction} LIMIT ? OFFSET ?"
                    else:
                        sql = f"SELECT * FROM {meta_object.table_name} {semantic_join_sql} {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
                else:
                    sql = f"SELECT * FROM {meta_object.table_name} {semantic_join_sql} {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
                all_params.extend([safe_limit, safe_offset])
                rows, columns = self._execute_for_list(registry, sql, all_params, bool(computed_conditions))

                items = []
                for row in rows:
                    if isinstance(row, dict):
                        items.append(dict(row))
                    else:
                        items.append(dict(zip(columns, row)))

                records = items

            else:
                # [FIX 2026-06-08] 传 table_prefix 消除 JOIN 后的列名歧义
                and_conditions, and_params = registry.ds._build_conditions(filters, meta_object.table_name) if filters else ([], [])

                all_where_clauses = []
                all_params = []

                if and_conditions:
                    all_where_clauses.append("(" + " AND ".join(and_conditions) + ")")
                    all_params.extend(and_params)

                if scope_conditions:
                    all_where_clauses.append("(" + " AND ".join(scope_conditions) + ")")
                    all_params.extend(scope_params)

                if ctf_exists_clauses:
                    all_where_clauses.extend(ctf_exists_clauses)
                    all_params.extend(ctf_exists_params)

                if computed_conditions:
                    all_where_clauses.append("(" + " AND ".join(computed_conditions) + ")")
                    all_params.extend(computed_params)

                where_sql = ""
                if all_where_clauses:
                    where_sql = "WHERE " + " AND ".join(all_where_clauses)

                # [FIX 2026-06-09] semantic JOIN 子句 (category_label/category_type filter)
                semantic_join_sql = " ".join(semantic_join_clauses) if semantic_join_clauses else ""

                # computed *_count 过滤依赖相关子查询，必须用新连接绕过读池
                # 才能读到最新的 user_group_members 数据（读池连接可能持有过期 WAL 快照）
                use_fresh = bool(computed_conditions)

                if virtual_sort:
                    join_clause, sort_expr = virtual_sort
                    count_sql = f"SELECT COUNT(*) as count FROM {meta_object.table_name} {semantic_join_sql} {join_clause} {where_sql}"
                    rows, columns = self._execute_for_list(registry, count_sql, all_params, use_fresh)
                    total_row = rows[0] if rows else None
                    total = (total_row['count'] if isinstance(total_row, dict) else total_row[0]) if total_row else 0

                    sql = f"SELECT {meta_object.table_name}.* FROM {meta_object.table_name} {semantic_join_sql} {join_clause} {where_sql} ORDER BY {sort_expr} LIMIT ? OFFSET ?"
                    all_params.extend([safe_limit, safe_offset])
                    rows, columns = self._execute_for_list(registry, sql, all_params, use_fresh)
                    items = []
                    for row in rows:
                        if isinstance(row, dict):
                            items.append(dict(row))
                        else:
                            items.append(dict(zip(columns, row)))
                    records = items
                else:
                    count_sql = f"SELECT COUNT(*) as count FROM {meta_object.table_name} {semantic_join_sql} {where_sql}"
                    rows, columns = self._execute_for_list(registry, count_sql, all_params, use_fresh)
                    total_row = rows[0] if rows else None
                    total = (total_row['count'] if isinstance(total_row, dict) else total_row[0]) if total_row else 0

                    base_columns = f"SELECT {meta_object.table_name}.*"
                    # [FIX 2026-06-04] 增强 SELECT 时只包含实际存在物理列的虚拟字段。
                    # audit_aspect 声明的 updated_at/created_by/updated_by 是 storage=virtual
                    # 且 materialization.strategy=virtual（无物理列），若直接加进 SELECT
                    # 会触发 "no such column: updated_at" 错误。
                    # 这些"真正虚拟"的字段会在后续 _enrich_audit_virtual_fields 步骤中
                    # 从 audit_logs 计算填充。
                    available_columns_for_select = None
                    try:
                        available_columns_for_select = registry.ds._get_table_columns(meta_object.table_name)
                    except Exception:
                        available_columns_for_select = None
                    for field in meta_object.fields:
                        if getattr(field, 'storage', None) == FieldStorage.VIRTUAL and getattr(field, 'db_column', None):
                            if available_columns_for_select and field.db_column not in available_columns_for_select:
                                continue
                            base_columns += f", {field.db_column} as {field.id}"

                    sql = f"{base_columns} FROM {meta_object.table_name} {semantic_join_sql} {where_sql}"
                    if order_by:

                        order_clause = []
                        order_by_fields = []
                        # [FIX 2026-06-04] 排序时校验字段是否实际存在；
                        # 顶部已剥离 ":N" 后缀，这里再补一道物理列存在性校验。
                        available_columns_for_order = available_columns_for_select
                        for part in order_by.split(','):
                            part = part.strip()
                            if not part:
                                continue
                            is_desc = part.startswith('-')
                            field_name = part.lstrip('-')
                            field = meta_object.get_field(field_name)
                            # [FIX] computed *_count 字段（如 member_count）即使标记为 virtual
                            # （DB 无列），排序也需用子查询通过关联表 COUNT。
                            # 必须在 VIRTUAL 跳过判断之前处理。
                            computed_sort = self._build_computed_count_sort_clause(meta_object, field_name, is_desc)
                            if computed_sort:
                                order_clause.append(computed_sort)
                                order_by_fields.append(field_name)
                                continue
                            if field and getattr(field, 'storage', None) == FieldStorage.VIRTUAL:
                                # 虚拟字段无物理列，留给 _sort_by_virtual_fields 内存排序
                                continue
                            # [FIX 2026-06-04] 跳过表中不存在的字段（防御性兜底）
                            if available_columns_for_order and field_name not in available_columns_for_order:
                                logger.warning(
                                    f"[_do_list] Skipping ORDER BY for non-existent column: {field_name} "
                                    f"on {meta_object.table_name}"
                                )
                                continue
                            db_column = getattr(field, 'db_column', field_name) if field else field_name
                            order_clause.append(f"{db_column} {'DESC' if is_desc else 'ASC'}")
                            order_by_fields.append(field_name)
                        if order_clause:
                            sql += " ORDER BY " + ", ".join(order_clause)
                        else:
                            sql += " ORDER BY id DESC"
                    else:
                        sql += " ORDER BY id DESC"
                    sql += f" LIMIT ? OFFSET ?"
                    all_params.extend([safe_limit, safe_offset])
                    rows, columns = self._execute_for_list(registry, sql, all_params, use_fresh)
                    items = []
                    for row in rows:
                        if isinstance(row, dict):
                            items.append(dict(row))
                        else:
                            items.append(dict(zip(columns, row)))
                    records = items

            records = self._enrich_audit_virtual_fields(meta_object, records, registry.ds)
            records = self._enrich_association_counts(meta_object, records, registry.ds)
            records = self._enrich_fk_display_names(meta_object, records, registry.ds)

            # [FIX 2026-06-08] 只有当 SQL 层未排序虚拟字段时才做内存排序
            # virtual_sort 非 None 表示 SQL 已通过 JOIN + ORDER BY 排序，无需再内存排序
            if order_by and not virtual_sort:
                records = self._sort_by_virtual_fields(meta_object, records, order_by)

            return ActionResult(success=True, data=records, total=total)
        except Exception as e:
            logger.error(f"[_do_list] Error: {e}")
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _execute_for_list(self, registry, sql, params, use_fresh):
        """执行列表查询的 SQL 并取回结果。

        use_fresh=True 时通过全新 sqlite3 连接执行（绕过读池），
        适用于依赖相关子查询（如 computed *_count 过滤/排序）的 SQL，
        因为读池连接可能持有过期的 WAL 快照导致子查询看不到最新数据。

        返回 (rows, columns)，其中 rows 是 Row/字典 列表，columns 是列名列表。
        之所以返回数据而不是游标，是因为 fresh_connection 是 contextmanager，
        连接在 with 块退出时即被关闭，游标无法跨闭包使用。
        """
        if use_fresh:
            with registry.ds.fresh_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, tuple(params))
                else:
                    cursor.execute(sql)
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                return rows, columns
        if params:
            cursor = registry.ds.execute(sql, tuple(params))
        else:
            cursor = registry.ds.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return rows, columns

    def _build_computed_count_sort_clause(self, meta_object, field_name, is_desc):
        """为 computed 的 *_count 字段构造子查询排序子句

        computed 字段（如 member_count）虽然有 db_column，
        但 DB 中该列未被维护（始终为 NULL），无法直接 ORDER BY。
        通过 many_to_many 关联的 through 表生成 COUNT 子查询进行排序。

        兼容 meta_object.associations 为 dict（{name: AssociationDefinition}）
        或 list（[AssociationDefinition | str]）两种形态。

        Returns:
            str: 完整排序子句（如 "(SELECT COUNT(*) FROM through WHERE ...) DESC"），
                 不匹配时返回 None。
        """
        field = meta_object.get_field(field_name)
        if not field or not getattr(field, 'computed', False):
            return None
        if not field_name.endswith('_count'):
            return None

        base_name = field_name[:-6]  # member_count -> member
        table_name = meta_object.table_name

        associations = getattr(meta_object, 'associations', None)
        if not associations:
            return None
        if isinstance(associations, dict):
            assoc_items = list(associations.values())
        else:
            assoc_items = list(associations)

        # [FIX 2026-06-09] child_count 字段 (computation.type=count_children)
        # 计算子对象数量；先按 computation.child_object 与 assoc.target_entity 匹配
        field_computation = getattr(field, 'computation', None) or {}
        field_child_object = (
            field_computation.get('child_object')
            or field_computation.get('target_object')
            or ''
        )

        for assoc in assoc_items:
            if isinstance(assoc, str):
                # 兼容历史格式：list of names
                assoc_name = assoc
                assoc_type = 'many_to_many'
                through = None
                source_key = None
                foreign_key_field = None
                target_table = None
                target_entity = ''
            else:
                assoc_name = getattr(assoc, 'name', '')
                assoc_type = getattr(assoc, 'type', '')
                through = getattr(assoc, 'through', None)
                source_key = getattr(assoc, 'source_key', None)
                # [FIX] merged_one_to_many / one_to_many / composition 等
                # 虚拟/父子关联通过外键字段统计；composition 的 FK 通常放在
                # source_key 里（如 product.yaml 的 source_key: product_id），
                # 这里把 source_key 作为 foreign_key_field 的兜底。
                foreign_key_field = (
                    getattr(assoc, 'foreign_key_field', None)
                    or source_key
                )
                # [FIX] 实际表名通常是 assoc_name 复数 (如 relationships)；
                # target_entity/target_type 在 YAML 中是单数 (relationship)，DB 表是复数。
                # 优先级: 显式 target_table > assoc_name 复数 (本表通常命名为 relationships)
                # > target_entity 复数 > target_entity 单数
                target_entity = getattr(assoc, 'target_entity', None) or ''
                _pluralized = (
                    assoc_name if assoc_name.endswith('s')
                    else assoc_name + 's'
                )
                target_table = (
                    getattr(assoc, 'target_table', None)
                    or _pluralized
                    or (target_entity + 's' if target_entity and not target_entity.endswith('s') else target_entity)
                    or target_entity
                )

            # [FIX] 支持 many_to_many (走 through/source_key)
            #       和 merged_one_to_many / one_to_many / composition (走 foreign_key_field/source_key)
            many_to_many_matched = False
            if assoc_type == 'many_to_many' and through and source_key:
                many_to_many_matched = True
            elif assoc_type in ('merged_one_to_many', 'one_to_many', 'virtual_one_to_many', 'composition', 'parent_child') and foreign_key_field and target_table:
                pass  # 走外键路径
            else:
                continue
            # 匹配：relation_count <-> relationships / relationship / relations / relation
            # 支持关系名去除常见后缀（ship / ies / es / s）后与 base_name 比较，
            # 这样 relation_count 也能匹配 relationships / relationships_for_xxx
            assoc_singular = re.sub(r'(ship$|ies$|es$|s$)', '', assoc_name)
            name_matched = (
                assoc_name == base_name
                or assoc_name == base_name + 's'
                or assoc_singular == base_name
                or assoc_name == base_name + 'ship'
                or assoc_name == base_name + 'ship' + 's'
            )
            # [FIX 2026-06-09] child_count 这种通用字段不会按关联名匹配
            # (例如 product.child_count 的 base_name='child' 跟 assoc_name='version'
            # 完全对不上)，所以额外允许通过 computation.child_object 命中
            # assoc.target_entity/target_type，命中后强制走外键子查询。
            child_object_matched = bool(
                field_child_object
                and target_entity
                and field_child_object == target_entity
            )
            matched = name_matched or child_object_matched
            if not matched:
                continue

            direction = 'DESC' if is_desc else 'ASC'
            if many_to_many_matched:
                return (
                    f"(SELECT COUNT(*) FROM {through} "
                    f"WHERE {through}.{source_key} = {table_name}.id) {direction}"
                )
            else:
                # [FIX] merged_one_to_many: 业务对象的关系数量通常按双向计算
                # (source_bo_id = id OR target_bo_id = id) 才能与 Python 端
                # computation_service.compute_by_semantics 计算的 relation_count 一致。
                target_key = getattr(assoc, 'target_key', None) or ''
                if target_key and target_key != foreign_key_field:
                    return (
                        f"(SELECT COUNT(*) FROM {target_table} "
                        f"WHERE {target_table}.{foreign_key_field} = {table_name}.id "
                        f"OR {target_table}.{target_key} = {table_name}.id) {direction}"
                    )
                return (
                    f"(SELECT COUNT(*) FROM {target_table} "
                    f"WHERE {target_table}.{foreign_key_field} = {table_name}.id) {direction}"
                )

        return None

    def _try_build_computed_filter(self, meta_object, key, value):
        """检测 (key, value) 是否是 computed *_count 字段的过滤，若是返回子查询条件子句

        支持的操作符（按 key 后缀解析）：
        - __in:     IN (?, ?, ...)
        - __notin:  NOT IN (?, ?, ...)
        - __like:   LIKE ?
        - _start:   >= ?
        - _end:     <= ?
        - 精确匹配: = ?

        [FIX] URL 参数始终是字符串。如果字段是 integer 类型，SQLite 在比较
        TEXT 占位符与 INTEGER 子查询结果时行为不稳定（type affinity），
        会导致过滤失效。这里按字段类型把字符串转成 int/float。

        Returns:
            (sql_clause, [params]) 或 (None, None)
        """
        if key.endswith('__in'):
            field_name = key[:-4]
            operator = 'IN'
            if isinstance(value, str):
                values = [v.strip() for v in value.split(',') if v.strip()]
            else:
                values = list(value) if hasattr(value, '__iter__') else [value]
        elif key.endswith('__notin'):
            field_name = key[:-7]
            operator = 'NOT IN'
            if isinstance(value, str):
                values = [v.strip() for v in value.split(',') if v.strip()]
            else:
                values = list(value) if hasattr(value, '__iter__') else [value]
        elif key.endswith('__like'):
            field_name = key[:-6]
            operator = 'LIKE'
            values = [f"%{value}%"]
        elif key.endswith('__gte'):
            field_name = key[:-5]
            operator = '>='
            values = [value]
        elif key.endswith('__lte'):
            field_name = key[:-5]
            operator = '<='
            values = [value]
        elif key.endswith('__gt'):
            field_name = key[:-4]
            operator = '>'
            values = [value]
        elif key.endswith('__lt'):
            field_name = key[:-4]
            operator = '<'
            values = [value]
        elif key.endswith('_start'):
            field_name = key[:-6]
            operator = '>='
            values = [value]
        elif key.endswith('_end'):
            field_name = key[:-4]
            operator = '<='
            values = [value]
        else:
            field_name = key
            operator = '='
            values = [value]

        field = meta_object.get_field(field_name)
        if not field or not getattr(field, 'computed', False):
            return None, None
        if not field_name.endswith('_count'):
            return None, None

        # [FIX] 按字段类型转换参数值，避免 SQLite type affinity 问题
        field_type_attr = getattr(field, 'field_type', None)
        is_integer = (
            field_type_attr is not None
            and (str(field_type_attr).endswith('INTEGER') or str(field_type_attr).endswith('INT')
                 or str(field_type_attr) in ('integer', 'int', 'bigint', 'smallint'))
        )
        if is_integer and operator not in ('LIKE',):
            def _coerce(v):
                if isinstance(v, str):
                    try:
                        return int(v)
                    except (ValueError, TypeError):
                        return v
                return v
            values = [_coerce(v) for v in values]

        base_name = field_name[:-6]
        table_name = meta_object.table_name

        associations = getattr(meta_object, 'associations', None)
        if not associations:
            return None, None
        if isinstance(associations, dict):
            assoc_items = list(associations.values())
        else:
            assoc_items = list(associations)

        # [FIX 2026-06-09] 把 field_child_object 提取到外层 scope，
        # 让 assoc 循环和后面的 relations 循环都能复用。
        field_computation = getattr(field, 'computation', None) or {}
        field_child_object = (
            field_computation.get('child_object')
            or field_computation.get('target_object')
            or ''
        )

        for assoc in assoc_items:
            if isinstance(assoc, str):
                assoc_name = assoc
                assoc_type = 'many_to_many'
                through = None
                source_key = None
                foreign_key_field = None
                target_table = None
                target_entity = ''
            else:
                assoc_name = getattr(assoc, 'name', '')
                assoc_type = getattr(assoc, 'type', '')
                through = getattr(assoc, 'through', None)
                source_key = getattr(assoc, 'source_key', None)
                # [FIX 2026-06-09] composition/parent_child 的 FK 通常在
                # source_key 里（如 product.yaml 的 source_key: product_id），
                # 把 source_key 作为 foreign_key_field 的兜底（与 sort 路径对称）。
                foreign_key_field = (
                    getattr(assoc, 'foreign_key_field', None)
                    or source_key
                )
                target_entity = getattr(assoc, 'target_entity', None) or ''
                _pluralized = (
                    assoc_name if assoc_name.endswith('s')
                    else assoc_name + 's'
                )
                target_table = (
                    getattr(assoc, 'target_table', None)
                    or _pluralized
                    or (target_entity + 's' if target_entity and not target_entity.endswith('s') else target_entity)
                    or target_entity
                )

            # [FIX 2026-06-09] 支持 many_to_many (走 through/source_key)
            #       和 merged_one_to_many / one_to_many / composition / parent_child (走外键)
            many_to_many_matched = False
            if assoc_type == 'many_to_many' and through and source_key:
                many_to_many_matched = True
            elif assoc_type in ('merged_one_to_many', 'one_to_many', 'virtual_one_to_many', 'composition', 'parent_child') and foreign_key_field and target_table:
                pass  # 走外键路径
            else:
                continue
            # 匹配：relation_count <-> relationships / relationship / relations / relation
            assoc_singular = re.sub(r'(ship$|ies$|es$|s$)', '', assoc_name)
            name_matched = (
                assoc_name == base_name
                or assoc_name == base_name + 's'
                or assoc_singular == base_name
                or assoc_name == base_name + 'ship'
                or assoc_name == base_name + 'ship' + 's'
            )
            # [FIX 2026-06-09] child_count 这种通用字段不会按关联名匹配
            # (例如 product.child_count 的 base_name='child' 跟 assoc_name='version'
            # 完全对不上)，所以额外允许通过 computation.child_object 命中
            # assoc.target_entity/target_type（与 sort 路径对称）。
            # 注意 field_child_object 已在函数顶部提取，避免重复计算
            child_object_matched = bool(
                field_child_object
                and target_entity
                and field_child_object == target_entity
            )
            matched = name_matched or child_object_matched
            if not matched:
                continue

            if many_to_many_matched:
                subquery = f"(SELECT COUNT(*) FROM {through} WHERE {through}.{source_key} = {table_name}.id)"
            else:
                # [FIX] 双向 COUNT (source FK = id OR target FK = id) 与 Python 端 relation_count 一致
                _target_key = getattr(assoc, 'target_key', None) or ''
                if _target_key and _target_key != foreign_key_field:
                    subquery = (
                        f"(SELECT COUNT(*) FROM {target_table} "
                        f"WHERE {target_table}.{foreign_key_field} = {table_name}.id "
                        f"OR {target_table}.{_target_key} = {table_name}.id)"
                    )
                else:
                    subquery = f"(SELECT COUNT(*) FROM {target_table} WHERE {target_table}.{foreign_key_field} = {table_name}.id)"
            if operator in ('IN', 'NOT IN'):
                if not values:
                    return None, None
                placeholders = ', '.join(['?'] * len(values))
                return f"{subquery} {operator} ({placeholders})", list(values)
            else:
                return f"{subquery} {operator} ?", list(values)

        # [FIX 2026-06-09] G1 兜底: meta_object.relations (MetaRelation 类型) 路径
        # YAML 的 relations: 段被解析为 MetaRelation 而非 AssociationDefinition，
        # 字段名也不同 (target_object/source_field/relation_type)；
        # 这里用同样的匹配逻辑再扫一遍。
        relations = getattr(meta_object, 'relations', None) or []
        for rel in relations:
            rel_name = getattr(rel, 'name', '')
            # MetaRelation.relation_type 是枚举，需要取 .value
            rel_type_attr = getattr(rel, 'relation_type', None)
            rel_type_value = getattr(rel_type_attr, 'value', rel_type_attr) or ''
            rel_type_str = str(rel_type_value).lower() if rel_type_value else ''
            # 映射：composition/parent_child 在 MetaRelation 里通常叫 PARENT_CHILD/COMPOSITION
            if rel_type_str in ('composition', 'parent_child'):
                rel_target_entity = getattr(rel, 'target_object', '') or ''
                rel_source_field = getattr(rel, 'source_field', '') or ''
                # [FIX 2026-06-09] source_field 缺失时按命名约定回退:
                # sub_domains 上指向 domain 的列就是 domain_id
                if not rel_source_field and rel_target_entity:
                    inferred_fk = f"{meta_object.id}_id"
                    rel_source_field = inferred_fk
                rel_target_table = (
                    rel_target_entity + 's'
                    if rel_target_entity and not rel_target_entity.endswith('s')
                    else rel_target_entity
                )
                # 匹配 (与 association 同一逻辑)
                rel_singular = re.sub(r'(ship$|ies$|es$|s$)', '', rel_name)
                rel_name_matched = (
                    rel_name == base_name
                    or rel_name == base_name + 's'
                    or rel_singular == base_name
                )
                rel_child_object_matched = bool(
                    field_child_object
                    and rel_target_entity
                    and field_child_object == rel_target_entity
                )
                if not (rel_name_matched or rel_child_object_matched):
                    continue
                if not rel_source_field or not rel_target_table:
                    continue
                subquery = (
                    f"(SELECT COUNT(*) FROM {rel_target_table} "
                    f"WHERE {rel_target_table}.{rel_source_field} = {table_name}.id)"
                )
                if operator in ('IN', 'NOT IN'):
                    if not values:
                        return None, None
                    placeholders = ', '.join(['?'] * len(values))
                    return f"{subquery} {operator} ({placeholders})", list(values)
                return f"{subquery} {operator} ?", list(values)

        # [FIX 2026-06-09] G4: count_relations descendants 兜底
        # 关联列表里没有名字对应的 association 时 (例如 domain.relation_count
        # 没有 relationships 关联)，尝试通过 computation.type=count_relations +
        # scope=descendants 直接生成层级子查询。
        return self._try_build_count_relations_filter(
            meta_object, field_name, base_name, operator, values
        )

    def _try_build_count_relations_filter(self, meta_object, field_name, base_name, operator, values):
        """[FIX 2026-06-09] G4: count_relations descendants SQL 子查询兜底

        适用场景: domain / sub_domain / service_module 的 relation_count 过滤。
        这些对象没有名为 'relationships' 的 association，无法走标准 _try_build_computed_filter。
        但 computation.type=count_relations + scope=descendants 提供了层级路径。
        这里的硬编码层级与领域模型一致：

          domain.id → sub_domains.domain_id → service_modules.sub_domain_id
                   → business_objects.service_module_id → relationships.source/target_bo_id
        """
        if field_name != 'relation_count' or base_name != 'relation':
            return None, None

        field = meta_object.get_field(field_name)
        if not field:
            return None, None

        field_computation = getattr(field, 'computation', None) or {}
        if field_computation.get('type') != 'count_relations':
            return None, None

        scope = field_computation.get('scope', 'self')
        if scope != 'descendants':
            # scope=self 仅作用于当前对象对应的 BO 集合 (如 business_object)，
            # 它有 relationships 关联，已在主路径覆盖；此处不重复实现。
            return None, None

        table_name = meta_object.table_name
        object_type = meta_object.id

        # 按对象类型生成层级子查询
        if object_type == 'domain':
            descendant_match = (
                "EXISTS (SELECT 1 FROM business_objects bo "
                "JOIN service_modules sm ON bo.service_module_id = sm.id "
                "JOIN sub_domains sd ON sm.sub_domain_id = sd.id "
                "WHERE sd.domain_id = domains.id "
                "AND (r.source_bo_id = bo.id OR r.target_bo_id = bo.id))"
            )
        elif object_type == 'sub_domain':
            descendant_match = (
                "EXISTS (SELECT 1 FROM business_objects bo "
                "JOIN service_modules sm ON bo.service_module_id = sm.id "
                "WHERE sm.sub_domain_id = sub_domains.id "
                "AND (r.source_bo_id = bo.id OR r.target_bo_id = bo.id))"
            )
        elif object_type == 'service_module':
            descendant_match = (
                "EXISTS (SELECT 1 FROM business_objects bo "
                "WHERE bo.service_module_id = service_modules.id "
                "AND (r.source_bo_id = bo.id OR r.target_bo_id = bo.id))"
            )
        else:
            return None, None

        subquery = (
            f"(SELECT COUNT(DISTINCT r.id) FROM relationships r "
            f"WHERE {descendant_match})"
        )

        if operator in ('IN', 'NOT IN'):
            if not values:
                return None, None
            placeholders = ', '.join(['?'] * len(values))
            return f"{subquery} {operator} ({placeholders})", list(values)
        return f"{subquery} {operator} ?", list(values)

    def _try_build_semantic_filter(self, meta_object, key, value):
        """[FIX 2026-06-09] semantic 派生字段过滤 (category_label/category_type)

        这些字段不在 DB 中存储，而是通过业务对象/服务模块/子领域/领域
        层级关系实时计算 (见 ComputationFieldHandler._compute_category_*)。
        为支持 SQL 过滤，这里：
          1. 拼出 LEFT JOIN 串把层级表拉进来
          2. 拼出 CASE WHEN 表达式，把层级匹配结果映射成可比较的中文/英文标签
          3. 把这个表达式以 = ? 的形式追加到 WHERE

        Returns:
            (joins: List[str], where_clause: Optional[str], params: List[Any])
            - joins: LEFT JOIN 子句列表
            - where_clause: "CASE WHEN ... END = ?" 子句 (None 表示不匹配)
            - params: 参数列表

        目前支持:
          - relationship.category_label  (中文标签: 同业务对象/同服务模块/同子领域/同领域/跨领域)
          - relationship.category_type   (英文枚举: same_bo/same_module/same_subdomain/same_domain/cross_domain)
        """
        if value is None:
            return [], None, []

        # 解析 key 后缀（仅支持精确匹配 = 和 __in）
        operator = '='
        if key.endswith('__in'):
            field_name = key[:-4]
            operator = 'IN'
            values = [v.strip() for v in str(value).split(',') if v.strip()]
        else:
            field_name = key
            values = [value]

        if not values:
            return [], None, []

        # 只处理白名单字段，避免任意字段都走 JOIN
        if field_name not in ('category_label', 'category_type'):
            return [], None, []

        # 必须作用于 relationship 表（其它对象无 source_bo_id/target_bo_id 语义）
        if meta_object.id != 'relationship':
            logger.warning(f"[_try_build_semantic_filter] category_label/category_type filter only supported on relationship, got {meta_object.id}")
            return [], None, []

        # JOIN 串：业务对象 ×2 + 服务模块 ×2 + 子领域 ×2 + 领域 ×2
        # 用 LEFT JOIN 避免因层级缺失数据导致整行消失（与 analytics_query_builder 一致）
        joins = [
            "LEFT JOIN business_objects _cat_bo1 ON relationships.source_bo_id = _cat_bo1.id",
            "LEFT JOIN business_objects _cat_bo2 ON relationships.target_bo_id = _cat_bo2.id",
            "LEFT JOIN service_modules _cat_sm1 ON _cat_bo1.service_module_id = _cat_sm1.id",
            "LEFT JOIN service_modules _cat_sm2 ON _cat_bo2.service_module_id = _cat_sm2.id",
            "LEFT JOIN sub_domains _cat_sd1 ON _cat_sm1.sub_domain_id = _cat_sd1.id",
            "LEFT JOIN sub_domains _cat_sd2 ON _cat_sm2.sub_domain_id = _cat_sd2.id",
            "LEFT JOIN domains _cat_d1 ON _cat_sd1.domain_id = _cat_d1.id",
            "LEFT JOIN domains _cat_d2 ON _cat_sd2.domain_id = _cat_d2.id",
        ]

        # CASE WHEN 表达式:
        # 中文 (category_label): 同业务对象 > 同服务模块 > 同子领域 > 同领域 > 跨领域
        # 英文 (category_type):  same_bo > same_module > same_subdomain > same_domain > cross_domain
        # 用 COALESCE(..., -1) != COALESCE(..., -1) 处理 LEFT JOIN 产生的 NULL
        if field_name == 'category_label':
            case_expr = (
                "CASE "
                "WHEN relationships.source_bo_id = relationships.target_bo_id THEN '同业务对象' "
                "WHEN COALESCE(_cat_sm1.id, -1) = COALESCE(_cat_sm2.id, -1) THEN '同服务模块' "
                "WHEN COALESCE(_cat_sd1.id, -1) = COALESCE(_cat_sd2.id, -1) THEN '同子领域' "
                "WHEN COALESCE(_cat_d1.id, -1) = COALESCE(_cat_d2.id, -1) THEN '同领域' "
                "ELSE '跨领域' "
                "END"
            )
        else:  # category_type
            case_expr = (
                "CASE "
                "WHEN relationships.source_bo_id = relationships.target_bo_id THEN 'same_bo' "
                "WHEN COALESCE(_cat_sm1.id, -1) = COALESCE(_cat_sm2.id, -1) THEN 'same_module' "
                "WHEN COALESCE(_cat_sd1.id, -1) = COALESCE(_cat_sd2.id, -1) THEN 'same_subdomain' "
                "WHEN COALESCE(_cat_d1.id, -1) = COALESCE(_cat_d2.id, -1) THEN 'same_domain' "
                "ELSE 'cross_domain' "
                "END"
            )

        if operator == 'IN':
            placeholders = ', '.join(['?'] * len(values))
            return joins, f"({case_expr}) IN ({placeholders})", list(values)
        return joins, f"({case_expr}) = ?", [values[0]]

    def _resolve_virtual_sort(self, meta_object, order_by):
        if not order_by:
            return None

        from meta.core.models import registry as meta_registry

        parts = order_by.strip().split()
        field_name = parts[0].lstrip('-')
        direction = 'DESC' if parts[0].startswith('-') or (len(parts) > 1 and parts[1].upper() == 'DESC') else 'ASC'

        field = meta_object.get_field(field_name)
        if not field:
            return None

        storage = getattr(field, 'storage', None)
        if storage != FieldStorage.VIRTUAL:
            return None

        from meta.core.redundancy_registry import redundancy_registry
        red_def = redundancy_registry.get_redundancy(meta_object.id, field_name)
        
        # [FIX 2026-06-08] audit 派生字段排序支持
        # 如果 red_def 为空，检查是否是 audit 派生字段（derive_from_object='audit_logs'）
        if not red_def or not red_def.join_path:
            derive_from = getattr(field, 'derive_from_object', None)
            if derive_from == 'audit_logs':
                from meta.services.query.virtual_sort import _build_audit_derived_order_join
                result = _build_audit_derived_order_join(
                    meta_object.table_name,
                    meta_object.id,  # object_type for audit query
                    field_name,
                    direction
                )
                if result:
                    # _build_audit_derived_order_join 返回三元组 (join_clause, order_alias, sort_dir)
                    # 需要转为二元组 (join_clause, sort_expr) 以匹配 _resolve_virtual_sort 的返回格式
                    join_sql, order_alias, sort_dir = result
                    # [FIX 2026-06-08] COALESCE 回退到 created_at：
                    # COALESCE 包装已在 _build_audit_derived_order_join() 中完成
                    sort_expr = f"{order_alias} {sort_dir}"
                    logger.info(f"[VirtualSort] Built audit-derived JOIN sort for {meta_object.id}.{field_name}: {join_sql}, order_by: {sort_expr}")
                    return join_sql, sort_expr
            return None

        table_name = meta_object.table_name
        alias_counter = 0
        join_parts = []
        last_alias = table_name
        target_field = None

        for step in red_def.join_path:
            alias_counter += 1
            join_alias = f"_vsj{alias_counter}"
            to_field = step.to_field if step.to_field else 'id'
            join_sql = f"LEFT JOIN {step.table} AS {join_alias} ON {last_alias}.{step.from_field} = {join_alias}.{to_field}"
            join_parts.append(join_sql)
            last_alias = join_alias
            target_field = step.select

        if not target_field:
            return None

        join_clause = " ".join(join_parts)
        sort_expr = f"{last_alias}.{target_field} {direction}"

        logger.info(f"[VirtualSort] Built JOIN sort: {join_clause}, order_by: {sort_expr}")
        return join_clause, sort_expr

    def _enrich_audit_virtual_fields(self, meta_object, records, data_source):
        """SSOT: 从 audit_logs 批量计算 virtual 字段（updated_at 等）

        遵循单一事实原则：virtual 字段不在业务表中物理存储，
        查询时通过 audit_logs 的 created_at_epoch (Unix毫秒) 实时计算。

        更新时间逻辑：
        1. 只查询 UPDATE 操作的审计日志时间
        2. 如果没有 UPDATE 日志，则使用记录本身的 created_at（创建时间）

        测试环境下优雅处理 audit_logs 表缺失的情况。

        v1.4 重构：委托给共享 helper `meta.core.audit_derived_fields`
        """

        if not records:
            return records

        virtual_fields = []
        for f in meta_object.fields:
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
            ds=data_source,
            object_type=meta_object.id,
            records=records,
            field_ids=field_ids,
        )

    def _sort_by_virtual_fields(self, meta_object, records, order_by):
        """对 VIRTUAL 字段执行内存排序，补充 SQL 层无法排序的虚拟字段
        
        SSOT virtual 字段（如 updated_at）在 enrichment 之后才有值，
        无法在 SQL 层 ORDER BY。此方法在内存中对当前页做排序。
        """

        if not records or not order_by:
            return records

        parts = order_by.strip().split(',')
        sort_keys = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            is_desc = part.startswith('-')
            field_name = part.lstrip('-')
            field = meta_object.get_field(field_name)
            if not field:
                continue
            storage = getattr(field, 'storage', None)
            if storage != FieldStorage.VIRTUAL:
                continue
            sort_keys.append((field_name, is_desc))

        if not sort_keys:
            return records

        def sort_key(record):
            values = []
            for fname, _desc in sort_keys:
                val = record.get(fname)
                if val is None:
                    val = ''
                values.append(val)
            return tuple(values)

        for fname, is_desc in reversed(sort_keys):
            records.sort(key=lambda r, fn=fname: (r.get(fn) or ''), reverse=is_desc)

        return records

    def _enrich_association_counts(self, meta_object, records, data_source):
        # 委托给共享模块（与 association_engine._query_reference 共用）
        return _shared_enrich_counts(meta_object, records, data_source)

    def _enrich_fk_display_names(self, meta_object, records_or_record, data_source):
        # 委托给共享模块（与 association_engine._query_reference 共用）
        return _shared_enrich_fk(meta_object, records_or_record, data_source)
