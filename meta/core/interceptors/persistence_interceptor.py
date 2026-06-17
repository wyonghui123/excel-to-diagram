# -*- coding: utf-8 -*-
import logging
import re
from typing import Dict, Any

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext, ActionResult
from meta.core.action_executor import ActionRegistry
from meta.core.association_engine import AssociationEngine
from meta.core.enrichment_engine import EnrichmentEngine
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
        # [SPR-04 T-S03-02] suffix operator dispatch table
        # [FIX v3.18 2026-06-10] 改用方法名字符串 + getattr 模式：
        #   原实现存的是 bound method (self._build_in_filter)，调用方很容易误传 self
        #   (e.g. `builder(self, ...)`)，导致 "takes 8 args but 9 given"。
        #   改用 method name 字典 + getattr 显式 self 边界：getattr(self, name)(args...)
        #   表达 "这是 self 的方法，调用方不要再传 self"，根除 arity 误传。
        self._SUFFIX_BUILDER_METHODS = {
            '__in':   '_build_in_filter',
            '__like': '_build_like_filter',
            '_start': '_build_start_filter',
            '_end':   '_build_end_filter',
        }

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
            # [R0-2 2026-06-11] ComputationNotSupportedError 必须冒泡到 Flask errorhandler
            # 让其返回 422 + 统一错误格式. 不要被通用 except 吞掉转 400.
            from meta.core.computed_field_query import ComputationNotSupportedError
            if isinstance(e, ComputationNotSupportedError):
                logger.warning(f"[PersistenceInterceptor] {e}")
                raise  # 让 Flask errorhandler 接管 (bo_api.py 422 handler)
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
                    result.data = EnrichmentEngine.for_data_source(registry.ds).enrich_fk_display_names(meta_object, result.data)
            except Exception as e:
                logger.warning(f"[_do_read] enrich_fk_display_names failed: {e}")
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

        [FIX v1.0.9 2026-06-10] 支持 dict 和 SemanticAnnotation 两种形式:
        - yaml 解析后: semantics=SemanticAnnotation(immutable=True)
        - 测试 mock 或 嵌套字段: semantics={'immutable': True}
        """
        if not data or not meta_object:
            return data
        try:
            fields = getattr(meta_object, 'fields', None) or []
            immutable_ids = set()
            for f in fields:
                sem = getattr(f, 'semantics', None)
                if sem is None:
                    continue
                # [FIX v1.0.9] 同时支持 dict 和对象
                is_immutable = False
                if isinstance(sem, dict):
                    is_immutable = bool(sem.get('immutable'))
                else:
                    is_immutable = bool(getattr(sem, 'immutable', False))
                if is_immutable:
                    fid = getattr(f, 'id', None) or getattr(f, 'name', None)
                    if fid:
                        immutable_ids.add(fid)
            if not immutable_ids:
                return data
            filtered = {k: v for k, v in data.items() if k not in immutable_ids}
            removed = set(data.keys()) - set(filtered.keys())
            if removed:
                logger.info(
                    f"[PersistenceInterceptor] Filtered immutable fields: {removed} "
                    f"(immutable_ids: {immutable_ids})"
                )
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
          - [FIX v1.0.6 2026-06-10] 嵌套 OR group: 内层 OR group 会被递归处理
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

        def _render_cond(cond_obj) -> tuple:
            """递归渲染单条件 (dict → SQL片段, params)

            如果 cond 是 dict 且 type='or', 递归处理内嵌 conditions。
            """
            if not isinstance(cond_obj, dict):
                return '', []

            # [FIX v1.0.6] 嵌套 OR group 递归处理
            if cond_obj.get('type') == 'or':
                sub_parts = []
                sub_params = []
                for sub_c in cond_obj.get('conditions', []):
                    sql, p = _render_cond(sub_c)
                    if sql:
                        sub_parts.append(sql)
                        sub_params.extend(p)
                if sub_parts:
                    return "(" + " OR ".join(sub_parts) + ")", sub_params
                return '', []

            # [FIX v1.0.7 2026-06-10] AND group 支持 (用于 dim AND visibility 嵌套)
            if cond_obj.get('type') == 'and':
                sub_parts = []
                sub_params = []
                for sub_c in cond_obj.get('conditions', []):
                    sql, p = _render_cond(sub_c)
                    if sql:
                        sub_parts.append(sql)
                        sub_params.extend(p)
                if sub_parts:
                    return "(" + " AND ".join(sub_parts) + ")", sub_params
                return '', []

            field = cond_obj.get('field', '')
            op = cond_obj.get('operator', 'eq')
            value = cond_obj.get('value')
            if op == 'in_subquery':
                return f"{field} IN ({value})", []
            elif op in ('in', 'nin'):
                # [FIX v1.0.2] 列表值用 IN (...) 展开
                values = cond_obj.get('values', value if isinstance(value, list) else [value])
                placeholders = ','.join('?' * len(values))
                return f"{field} {OP_MAP[op]} ({placeholders})", list(values)
            else:
                sql_op = OP_MAP.get(op, '=')
                return f"{field} {sql_op} ?", [value]

        conditions = []
        params = []

        for cond in query_conditions:
            sql, p = _render_cond(cond)
            if sql:
                conditions.append(sql)
                params.extend(p)

        return conditions, params

    # ---- [SPR-04 T-S03-02] suffix filter builders (dispatch table) ----

    def _build_in_filter(self, meta_object, key, value, ctf_param_map, filters, ctf_exists_clauses, ctf_exists_params):
        """处理 __in 后缀: `field__in=a,b,c` → `field IN (?, ?, ?)`"""
        field_name = key[:-4]
        # [V1.2.5 2026-06-17] 先检查 cross_table_filters (chain filter):
        # 字段是 virtual 时 (source_domain_id 等), 不应直接走 DB 字段 IN, 应走 EXISTS chain.
        # 即使字段是物理的, 如果 yaml 显式声明了 ctf, 也优先用 ctf (覆盖默认行为).
        if field_name in ctf_param_map:
            values = [v.strip() for v in str(value).split(',') if v.strip()]
            if values:
                ctf = ctf_param_map[field_name]
                exists_sql, exists_params = self._build_ctf_exists(meta_object, ctf, values)
                ctf_exists_clauses.append(exists_sql)
                ctf_exists_params.extend(exists_params)
            return
        field = meta_object.get_field(field_name)
        if field:
            if getattr(field, 'storage', None) == FieldStorage.VIRTUAL:
                logger.warning(f"[_do_list] Ignoring filter for virtual field: {field_name}")
                return
            values = [v.strip() for v in str(value).split(',') if v.strip()]
            if values:
                filters[f"{field.db_column} IN"] = values
        else:
            logger.warning(f"[_do_list] Unknown filter field: {field_name}")

    def _build_like_filter(self, meta_object, key, value, ctf_param_map, filters, ctf_exists_clauses, ctf_exists_params):
        """处理 __like 后缀: `field__like=foo` → `field LIKE '%foo%'`"""
        field_name = key[:-6]
        # [V1.2.5 2026-06-17] 先 ctf 后 field: 同 _build_in_filter
        if field_name in ctf_param_map:
            values = [str(value).strip()]
            if values and values[0]:
                ctf = ctf_param_map[field_name]
                exists_sql, exists_params = self._build_ctf_exists(meta_object, ctf, values)
                ctf_exists_clauses.append(exists_sql)
                ctf_exists_params.extend(exists_params)
            return
        field = meta_object.get_field(field_name)
        if field:
            if getattr(field, 'storage', None) == FieldStorage.VIRTUAL:
                logger.warning(f"[_do_list] Ignoring filter for virtual field: {field_name}")
                return
            filters[f"{field.db_column} LIKE"] = f"%{value}%"
        else:
            logger.warning(f"[_do_list] Unknown filter field: {field_name}")

    def _build_start_filter(self, meta_object, key, value, ctf_param_map, filters, ctf_exists_clauses, ctf_exists_params):
        """处理 _start 后缀: `field_start=X` → `field >= X` (date range start)"""
        base_field = key[:-6]
        field = meta_object.get_field(base_field)
        if field:
            if getattr(field, 'storage', None) == FieldStorage.VIRTUAL:
                logger.warning(f"[_do_list] Ignoring filter for virtual field: {base_field}")
                return
            filters[f"{field.db_column} >="] = value
        else:
            filters[f"{base_field} >="] = value

    def _build_end_filter(self, meta_object, key, value, ctf_param_map, filters, ctf_exists_clauses, ctf_exists_params):
        """处理 _end 后缀: `field_end=X` → `field <= X` (date range end)"""
        base_field = key[:-4]
        field = meta_object.get_field(base_field)
        if field:
            if getattr(field, 'storage', None) == FieldStorage.VIRTUAL:
                logger.warning(f"[_do_list] Ignoring filter for virtual field: {base_field}")
                return
            filters[f"{field.db_column} <="] = value
        else:
            filters[f"{base_field} <="] = value

    def _build_where_sql(
        self,
        filters: Dict[str, Any],
        scope_conditions, scope_params,
        ctf_exists_clauses, ctf_exists_params,
        computed_conditions, computed_params,
        search_or_conditions, search_or_params,
        registry, meta_object,
    ):
        """[SPR-04 T-S03-01] 组合 WHERE 子句 (search/no-search 两个分支共用).

        接受 5 类过滤条件 + 各自 params, 合并为一个 WHERE 字符串和参数列表.
        顺序: 普通 AND → scope AND → search OR → ctf EXISTS → computed AND.

        Returns:
            (where_sql, all_params): where_sql 是空字符串或 'WHERE ...'
        """
        and_conditions, and_params = (
            registry.ds._build_conditions(filters, meta_object.table_name)
            if filters else ([], [])
        )

        all_where_clauses = []
        all_params = []

        if and_conditions:
            all_where_clauses.append("(" + " AND ".join(and_conditions) + ")")
            all_params.extend(and_params)
        if scope_conditions:
            all_where_clauses.append("(" + " AND ".join(scope_conditions) + ")")
            all_params.extend(scope_params)
        if search_or_conditions:
            all_where_clauses.append("(" + " OR ".join(search_or_conditions) + ")")
            all_params.extend(search_or_params)
        if ctf_exists_clauses:
            all_where_clauses.extend(ctf_exists_clauses)
            all_params.extend(ctf_exists_params)
        if computed_conditions:
            all_where_clauses.append("(" + " AND ".join(computed_conditions) + ")")
            all_params.extend(computed_params)

        where_sql = "WHERE " + " AND ".join(all_where_clauses) if all_where_clauses else ""
        return where_sql, all_params

    def _build_order_by_clause(self, meta_object, order_by: str, available_columns):
        """[SPR-04 T-S03-03] 解析多列 order_by 字符串 → SQL 排序子句.

        支持:
        - 单/多列 (逗号分隔)
        - DESC (- 前缀)
        - computed *_count 字段 (走 _build_computed_count_sort_clause 子查询)
        - VIRTUAL 字段 (留 _sort_by_virtual_fields 内存排序, 跳过)
        - 不存在的列 (跳过 + warning)

        Returns:
            (order_clause_sql, order_by_fields): SQL 是 "col1 DESC, col2 ASC" 或 None
        """
        if not order_by:
            return None, []
        order_clause = []
        order_by_fields = []
        for part in order_by.split(','):
            part = part.strip()
            if not part:
                continue
            is_desc = part.startswith('-')
            field_name = part.lstrip('-')
            field = meta_object.get_field(field_name)
            # computed *_count 字段 (DB 无列), 排序需用子查询
            computed_sort = self._build_computed_count_sort_clause(meta_object, field_name, is_desc)
            if computed_sort:
                order_clause.append(computed_sort)
                order_by_fields.append(field_name)
                continue
            if field and getattr(field, 'storage', None) == FieldStorage.VIRTUAL:
                # 虚拟字段无物理列, 留给 _sort_by_virtual_fields 内存排序
                continue
            # 跳过表中不存在的字段 (防御性兜底)
            if available_columns and field_name not in available_columns:
                logger.warning(
                    f"[_do_list] Skipping ORDER BY for non-existent column: {field_name} "
                    f"on {meta_object.table_name}"
                )
                continue
            db_column = getattr(field, 'db_column', field_name) if field else field_name
            order_clause.append(f"{db_column} {'DESC' if is_desc else 'ASC'}")
            order_by_fields.append(field_name)
        return (", ".join(order_clause) if order_clause else None), order_by_fields

    def _post_process_records(self, meta_object, records, registry, order_by, virtual_sort):
        """[SPR-04 T-S03-05] 列表结果后处理: enrich 虚拟字段 + 内存排序.

        步骤:
        1. 填充 audit 虚拟字段 (created_by/updated_by 等)
        2. 委托 EnrichmentEngine 算关联计数 + FK display names
        3. [R0-4 2026-06-11] relationship 专用: ensure_hierarchy_ids + compute_by_semantics
           修一个长期 P0 — 走 crud_query 路径的 relationship 列表,
           category_label/category_type 不被 enrichment, 排序/过滤静默失效
        4. 若 SQL 层未排虚拟字段, 做内存排序

        Returns:
            records: 后处理后的列表
        """
        records = self._enrich_audit_virtual_fields(meta_object, records, registry.ds)
        # [SPR-01 S-01] 委托给 EnrichmentEngine（删除 v1 兼容 shim）
        engine = EnrichmentEngine.for_data_source(registry.ds)
        records = engine.enrich_association_counts(meta_object, records)
        records = engine.enrich_fk_display_names(meta_object, records)

        # [R0-4 2026-06-11] relationship 列表必须 enrichment hierarchy_scope
        # 与 v2 专用 _query_relationship_with_scope (bo_api.py:391-397) 对齐
        if meta_object.id == 'relationship':
            from meta.services.query.computed_utils import ensure_hierarchy_ids_for_relationships
            from meta.services.computation_service import computation_service
            ensure_hierarchy_ids_for_relationships(registry.ds, records)
            computation_service.compute_by_semantics('relationship', records, registry.ds)

        # [FIX 2026-06-08] 只有当 SQL 层未排序虚拟字段时才做内存排序
        # virtual_sort 非 None 表示 SQL 已通过 JOIN + ORDER BY 排序，无需再内存排序
        if order_by and not virtual_sort:
            records = self._sort_by_virtual_fields(meta_object, records, order_by)
        return records

    def _build_select_columns(self, meta_object, registry):
        """[SPR-04 T-S03-04] 生成 SELECT 列子句, 包含物理虚拟列.

        Returns:
            (select_sql, available_columns): select_sql 是 'SELECT table.*, col1 as id1, ...'
        """
        base_columns = f"SELECT {meta_object.table_name}.*"
        # [FIX 2026-06-04] 增强 SELECT 时只包含实际存在物理列的虚拟字段。
        # audit_aspect 声明的 updated_at/created_by/updated_by 是 storage=virtual
        # 且 materialization.strategy=virtual（无物理列），若直接加进 SELECT
        # 会触发 "no such column: updated_at" 错误。
        # 这些"真正虚拟"的字段会在后续 _enrich_audit_virtual_fields 步骤中
        # 从 audit_logs 计算填充。
        available_columns = None
        try:
            available_columns = registry.ds._get_table_columns(meta_object.table_name)
        except Exception:
            available_columns = None
        for field in meta_object.fields:
            if getattr(field, 'storage', None) == FieldStorage.VIRTUAL and getattr(field, 'db_column', None):
                if available_columns and field.db_column not in available_columns:
                    continue
                base_columns += f", {field.db_column} as {field.id}"
        return base_columns, available_columns

    def _build_ctf_exists(self, meta_object, ctf_config, param_values):
        association = ctf_config.get('association', {})
        target_table = association.get('target_table')
        target_alias = association.get('target_alias', 't')
        on_conditions = association.get('on_conditions', [])
        where_conditions = association.get('where_conditions', [])
        # [V1.2.5 2026-06-17] chain filter 支持: from_join 自定义 JOIN 链
        # 默认 JOIN 只有 target_table, 加 from_join 后支持多表 JOIN
        # 例 (源域过滤): FROM business_objects bo_src JOIN service_modules sm_src ON ... JOIN sub_domains sd_src ON ...
        from_join = association.get('from_join', '').strip()
        main_table = meta_object.table_name

        def _resolve_field(field_str):
            if (field_str.startswith("'") and field_str.endswith("'")) or \
               (field_str.startswith('"') and field_str.endswith('"')):
                return None, field_str[1:-1]
            if '.' in field_str:
                prefix, col = field_str.rsplit('.', 1)
                if prefix == target_alias:
                    return f"{target_alias}.{col}", None
                # [V1.2.5 2026-06-17] 修复: from_join 引入了额外别名 (bo_src, sm_src, sd_src 等)
                # 这些别名既不是 target_alias 也不是 main_table, 但在 SQL 中有效.
                # 之前会错误重写成 main_table.col, 导致 SQL 字段名错乱.
                # 现在: 既不是 target_alias 也不是 main_table 时, 保留原 prefix.
                #
                # 兼容: 主表 'r' 别名 (约定见 relationship.yaml analytical_model.fact.alias),
                # 主 SQL FROM relationships (无别名), 所以 'r.' 必须替换为 main_table.
                # 否则 SQL 'no such column: r.source_bo_id'.
                if prefix == 'r':
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

        # [V1.2.5 2026-06-17] 拼接 EXISTS SQL:
        # 默认: EXISTS (SELECT 1 FROM {target_table} {target_alias} WHERE ...)
        # chain: EXISTS (SELECT 1 FROM business_objects bo_src JOIN ... WHERE ...)
        if from_join:
            # 自定义 FROM JOIN 链, 不需要额外 FROM target_table
            from_clause = from_join
        else:
            from_clause = f"FROM {target_table} {target_alias}"

        exists_sql = f"EXISTS (SELECT 1 {from_clause} WHERE {on_clause} AND {where_clause})"
        all_params = on_params + where_params
        return exists_sql, all_params

    def _resolve_pagination(self, params: dict, order_by: str, meta_object):
        """[SPR-04 T-S03-01b] 解析 limit/offset/page/safe_limit, 返回 (safe_limit, safe_offset, order_by).

        顺序: ordering → _order_by (含 ":N" 剥离) → 默认 -updated_at.
        """
        # 优先级: ordering > _order_by > 默认 -updated_at
        ordering = params.get("ordering")
        if ordering and not order_by:
            order_by = ordering

        if not order_by and meta_object:
            updated_at_field = meta_object.get_field('updated_at')
            if updated_at_field:
                order_by = '-updated_at'
                logger.info(f"[_do_list] No order specified, defaulting to updated_at desc")

        # 解析 limit/offset
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

        return safe_limit, safe_offset, order_by

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

        # [SPR-04 T-S03-01b] 解析 limit/offset/page/safe_limit
        safe_limit, safe_offset, order_by = self._resolve_pagination(params, order_by, meta_object)

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
                # [SPR-04 T-S03-02] 4 重 suffix operator 改 dispatch table
                # [FIX v3.18 2026-06-10] 用 method name + getattr 替代 bound method dispatch，
                # 防止调用方误传 self (历史 bug: 28/29 反复出现就是因为 `builder(self, ...)` 多传 self)。
                handled = False
                for suffix, method_name in self._SUFFIX_BUILDER_METHODS.items():
                    if key.endswith(suffix):
                        getattr(self, method_name)(
                            meta_object, key, value,
                            ctf_param_map, filters, ctf_exists_clauses, ctf_exists_params
                        )
                        handled = True
                        break
                if handled:
                    continue

                if key == 'exclude_ids' and value:
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

            # [FIX 2026-06-17 v3] 搜索范围控制：
            # 1. 如果 schema 显式声明了 list.searchFields，则**严格只搜这些字段**（避免误匹配审计字段）
            # 2. 否则回退到遍历所有 text 字段，但**排除 audit 字段**（created_by/updated_by/created_at/updated_at）
            #
            # 历史背景：之前不加审计字段排除，搜索"TEST"会返回所有 updated_by='TEST888' 的数据
            # (如 "采购合同"、"采购执行" 等正常数据)，用户看到不该出现的结果。
            list_search_fields = []
            ui_view_config = getattr(meta_object, 'ui_view_config', None)
            if ui_view_config:
                list_cfg = getattr(ui_view_config, 'list', None)
                if list_cfg:
                    list_search_fields = getattr(list_cfg, 'searchFields', []) or []

            def _is_audit_field(f):
                """判断字段是否属于审计字段（created_by/updated_by/created_at/updated_at）"""
                # 方式1：通过 semantics.source_of_truth 识别
                sem = getattr(f, 'semantics', None)
                if sem is not None:
                    if isinstance(sem, dict):
                        if sem.get('source_of_truth') == 'audit_logs':
                            return True
                    else:
                        if getattr(sem, 'source_of_truth', None) == 'audit_logs':
                            return True
                # 方式2：通过 field id 兜底识别（兼容未声明 semantics 的情况）
                field_id = getattr(f, 'id', None) or getattr(f, 'name', None)
                if field_id in ('created_at', 'updated_at', 'created_by', 'updated_by'):
                    return True
                return False

            if list_search_fields:
                # 模式 1: schema 显式声明了 searchFields，严格按声明搜
                if hasattr(meta_object, 'fields') and meta_object.fields:
                    for f in meta_object.fields:
                        field_id = getattr(f, 'id', getattr(f, 'key', ''))
                        if field_id not in list_search_fields:
                            continue

                        db_column = getattr(f, 'db_column', field_id)
                        field_type = getattr(f, 'field_type', None)
                        if field_type is None:
                            continue
                        type_value = field_type.value if hasattr(field_type, 'value') else str(field_type)
                        is_text_type = type_value in ('string', 'text', 'varchar', 'email')
                        is_hidden = getattr(f, 'hidden_filter', False)
                        field_storage = getattr(f, 'storage', None)
                        is_virtual = field_storage == FieldStorage.VIRTUAL

                        if not is_text_type or is_hidden or not db_column:
                            continue

                        if is_virtual:
                            # 虚拟字段：暂时不通过 LIKE 搜（除非是已知的 source_bo_/target_bo_ 链）
                            # 由下方的 virtual 字段 EXISTS 处理
                            continue

                        search_or_conditions.append(f"{db_column} LIKE ?")
                        search_or_params.append(f"%{search_keyword}%")
            else:
                # 模式 2: 未声明 searchFields，回退遍历所有 text 字段，但排除 audit
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

                        # [FIX 2026-06-17 v3] 排除 audit 字段（避免误匹配 updated_by='TEST888' 等）
                        if _is_audit_field(f):
                            continue

                        if is_text_type and not is_hidden and db_column and not is_virtual:
                            search_or_conditions.append(f"{db_column} LIKE ?")
                            search_or_params.append(f"%{search_keyword}%")

            # [V1.2.5 2026-06-17] toolbar 搜索支持 virtual 字段 (redundancy 链)
            # 用户在 toolbar 输入 "采购订单" 时, 后端不仅搜关系表物理字段,
            # 还要搜 source_bo_name/target_bo_name 这类由冗余链 JOIN 出来的 virtual 字段.
            # 通过 EXISTS 子查询实现:
            #   source_bo_name='xxx' → EXISTS (SELECT 1 FROM business_objects WHERE id = r.source_bo_id AND name LIKE '%xxx%')

            # 收集需要通过 EXISTS 搜的 virtual 字段
            search_virtual_fields = []
            if hasattr(meta_object, 'fields') and meta_object.fields:
                for f in meta_object.fields:
                    field_id = getattr(f, 'id', getattr(f, 'key', ''))
                    # 仅当 searchFields 显式声明该字段时，才纳入 virtual 搜索
                    if list_search_fields and field_id not in list_search_fields:
                        continue
                    is_virtual = getattr(f, 'storage', None) == FieldStorage.VIRTUAL
                    is_text_type = False
                    ft = getattr(f, 'field_type', None)
                    if ft is not None:
                        type_value = ft.value if hasattr(ft, 'value') else str(ft)
                        is_text_type = type_value in ('string', 'text', 'varchar', 'email')
                    if is_virtual and is_text_type:
                        search_virtual_fields.append(field_id)

            for vfield_id in search_virtual_fields:
                # 根据 field_id 推断 JOIN 路径
                # source_bo_name / source_bo_code → 通过 source_bo_id → business_objects.name/code
                # target_bo_name / target_bo_code → 通过 target_bo_id → business_objects.name/code
                if vfield_id.startswith('source_bo_') or vfield_id == 'source_bo_name':
                    bo_col = vfield_id.replace('source_bo_', '')  # 'name' / 'code'
                    exists_sql = (
                        f"EXISTS (SELECT 1 FROM business_objects bo "
                        f"WHERE bo.id = {meta_object.table_name}.source_bo_id "
                        f"AND bo.{bo_col} LIKE ?)"
                    )
                    search_or_conditions.append(exists_sql)
                    search_or_params.append(f"%{search_keyword}%")
                elif vfield_id.startswith('target_bo_') or vfield_id == 'target_bo_name':
                    bo_col = vfield_id.replace('target_bo_', '')
                    exists_sql = (
                        f"EXISTS (SELECT 1 FROM business_objects bo "
                        f"WHERE bo.id = {meta_object.table_name}.target_bo_id "
                        f"AND bo.{bo_col} LIKE ?)"
                    )
                    search_or_conditions.append(exists_sql)
                    search_or_params.append(f"%{search_keyword}%")

        try:
            virtual_sort = self._resolve_virtual_sort(meta_object, order_by)

            if search_or_conditions:
                # [SPR-04 T-S03-01] where_sql 组合委托给 _build_where_sql
                where_sql, all_params = self._build_where_sql(
                    filters,
                    scope_conditions, scope_params,
                    ctf_exists_clauses, ctf_exists_params,
                    computed_conditions, computed_params,
                    search_or_conditions, search_or_params,
                    registry, meta_object,
                )

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
                # [SPR-04 T-S03-01] where_sql 组合委托给 _build_where_sql (空 search_or_conditions)
                where_sql, all_params = self._build_where_sql(
                    filters,
                    scope_conditions, scope_params,
                    ctf_exists_clauses, ctf_exists_params,
                    computed_conditions, computed_params,
                    [], [],  # 无 search_or_conditions
                    registry, meta_object,
                )

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

                    base_columns, available_columns_for_select = self._build_select_columns(meta_object, registry)

                    sql = f"{base_columns} FROM {meta_object.table_name} {semantic_join_sql} {where_sql}"
                    if order_by:
                        # [SPR-04 T-S03-03] order_by 解析委托给 _build_order_by_clause
                        order_clause_sql, _ = self._build_order_by_clause(
                            meta_object, order_by, available_columns_for_select
                        )
                        if order_clause_sql:
                            sql += " ORDER BY " + order_clause_sql
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

            # [SPR-04 T-S03-05] 后处理委托给 _post_process_records
            records = self._post_process_records(
                meta_object, records, registry, order_by, virtual_sort
            )

            return ActionResult(success=True, data=records, total=total)
        except Exception as e:
            logger.error("[_do_list] Error: %s, object_type=%s", e,
                         meta_object.id if meta_object else '?')
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
        """[R0-3 2026-06-11] SSOT 委托给 ComputedFieldQuery.

        历史: [SPR-02] 委托给公共模块 + 保留 count_children / count_relations 特殊路径.
        现在: 全部走 ComputedFieldQuery (fail-fast + 次级稳定键 + validate_table_name).
        """
        try:
            field = meta_object.get_field(field_name)
        except Exception:
            return None
        if not field or not getattr(field, 'computed', False):
            return None
        if not field_name.endswith('_count'):
            return None

        from meta.core.computed_field_query import ComputedFieldQuery, ComputationNotSupportedError
        try:
            cfq = ComputedFieldQuery(meta_object, field)
            return cfq.build_order_clause(is_desc=is_desc)
        except ComputationNotSupportedError:
            # [R0-2] 不再 silent fallback, 让 caller 决定 (向上抛 422)
            raise

    def _try_build_computed_filter(self, meta_object, key, value):
        """[R0-3 2026-06-11] SSOT 委托给 ComputedFieldQuery.

        历史: [SPR-02] 委托给公共模块 + 保留 relations / count_relations 兜底.
        现在: count_relations / count_children 走 ComputedFieldQuery,
              m2m / composition 等其他 type 走 _computed_count_clause (保留).
        """
        from meta.core._computed_count_clause import (
            parse_operator, normalize_values, coerce_for_field_type,
            find_count_assoc, build_count_subquery, apply_count_clause,
        )

        if not meta_object or not key:
            return None, None

        field_name, operator = parse_operator(key)
        try:
            field = meta_object.get_field(field_name)
        except Exception:
            return None, None
        if not field or not getattr(field, 'computed', False):
            return None, None
        if not field_name.endswith('_count'):
            return None, None

        field_computation = getattr(field, 'computation', None) or {}
        comp_type = field_computation.get('type', '')

        # [R0-3] count_relations / count_children 走 SSOT
        if comp_type in ('count_relations', 'count_children'):
            from meta.core.computed_field_query import ComputedFieldQuery, ComputationNotSupportedError
            try:
                cfq = ComputedFieldQuery(meta_object, field)
                clause, params = cfq.build_filter_clause(operator, value)
                if clause is not None:
                    return clause, params
            except ComputationNotSupportedError:
                # [R0-2] 不再 silent fallback, 向上抛 422
                raise
            return None, None

        # [保留历史] m2m / composition / parent_child 等其他 type 走 _computed_count_clause
        values = normalize_values(value, operator)
        values = coerce_for_field_type(field, operator, values)
        base_name = field_name[:-6]
        table_name = meta_object.table_name
        field_child_object = (
            field_computation.get('child_object')
            or field_computation.get('target_object')
            or ''
        )

        # 主路径：公共模块 (m2m / one_to_many / composition / parent_child / merged / virtual)
        assoc_info = find_count_assoc(meta_object, base_name, field_computation)
        if assoc_info is not None:
            subquery = build_count_subquery(
                meta_object, base_name, target_alias='', assoc_info=assoc_info,
            )
            if subquery is not None:
                clause, params = apply_count_clause(subquery, operator, values)
                if clause:
                    return clause, params

        # [FIX 2026-06-09] G1 兜底: meta_object.relations (MetaRelation 类型) 路径
        rel_clause, rel_params = self._try_build_relations_filter(
            meta_object, base_name, operator, values,
            table_name=table_name, field_child_object=field_child_object,
        )
        if rel_clause is not None:
            return rel_clause, rel_params

        # [FIX 2026-06-09] G4: count_relations descendants 兜底
        return self._try_build_count_relations_filter(
            meta_object, field_name, base_name, operator, values
        )

    def _try_build_relations_filter(
        self, meta_object, base_name, operator, values,
        table_name: str = '', field_child_object: str = '',
    ):
        """[SPR-02] G1 兜底：meta_object.relations (MetaRelation) 路径。"""
        from meta.core._computed_count_clause import apply_count_clause

        if not table_name:
            table_name = meta_object.table_name
        relations = getattr(meta_object, 'relations', None) or []
        for rel in relations:
            rel_name = getattr(rel, 'name', '')
            rel_type_attr = getattr(rel, 'relation_type', None)
            rel_type_value = getattr(rel_type_attr, 'value', rel_type_attr) or ''
            rel_type_str = str(rel_type_value).lower() if rel_type_value else ''
            if rel_type_str not in ('composition', 'parent_child'):
                continue
            rel_target_entity = getattr(rel, 'target_object', '') or ''
            rel_source_field = getattr(rel, 'source_field', '') or ''
            if not rel_source_field and rel_target_entity:
                inferred_fk = f"{meta_object.id}_id"
                rel_source_field = inferred_fk
            rel_target_table = (
                rel_target_entity + 's'
                if rel_target_entity and not rel_target_entity.endswith('s')
                else rel_target_entity
            )
            rel_singular = re.sub(r'(ship$|ies$|es$|s$)', '', rel_name)
            rel_name_matched = (
                rel_name == base_name
                or rel_name == base_name + 's'
                or rel_singular == base_name
            )
            rel_child_object_matched = bool(
                field_child_object and rel_target_entity
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
            return apply_count_clause(subquery, operator, values)
        return None, None

    def _try_build_count_relations_filter(self, meta_object, field_name, base_name, operator, values):
        """[FIX 2026-06-09] G4: count_relations descendants SQL 子查询兜底

        适用场景: domain / sub_domain / service_module 的 relation_count 过滤。
        这些对象没有名为 'relationships' 的 association，无法走标准 _try_build_computed_filter。
        但 computation.type=count_relations + scope=descendants 提供了层级路径。

        [SPR-06 T-S08-03] descendant_match 由 _descendant_subquery.build_descendant_exists_sql
        数据驱动生成, 替代原 67 行 3 分支硬编码.
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

        object_type = meta_object.id
        # [SPR-06] 数据驱动 descendant_match 替代硬编码 if/elif 链
        from meta.core._descendant_subquery import build_descendant_exists_sql
        descendant_match = build_descendant_exists_sql(object_type, target_alias=meta_object.table_name)
        if descendant_match is None:
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

        # 收集需要排序的 VIRTUAL 字段 (field_name, is_desc)
        sort_keys = []
        for part in order_by.strip().split(','):
            part = part.strip()
            if not part:
                continue
            is_desc = part.startswith('-')
            field_name = part.lstrip('-')
            field = meta_object.get_field(field_name)
            if not field or getattr(field, 'storage', None) != FieldStorage.VIRTUAL:
                continue
            sort_keys.append((field_name, is_desc))

        if not sort_keys:
            return records

        # [SPR-07 T-S06-01] 倒序 stable sort: 次要 key 先排, 主要 key 后排
        for fname, is_desc in reversed(sort_keys):
            records.sort(key=lambda r, fn=fname: (r.get(fn) or ''), reverse=is_desc)
        return records

    # [SPR-01 S-01] 删 _enrich_association_counts / _enrich_fk_display_names wrapper
    # 调用方已改用 EnrichmentEngine.for_data_source(registry.ds) 直接获取实例
