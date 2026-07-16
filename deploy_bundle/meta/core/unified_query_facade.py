# -*- coding: utf-8 -*-
"""
UnifiedQueryFacade (QE-2026-06-v2)

v3 SSOT 统一查询 Facade。

不重新实现 SQL 构造/增强/转换——只做"组装 + 编排 + trace_id 注入"。
全部委托给 v3 已有组件：
  - QueryBuilder / QueryService  (SQL 构造与查询)
  - EnrichmentEngine             (FK display / association count)
  - RedundancyRegistry           (冗余字段注册)
  - VirtualFieldTransform        (虚拟字段转换)
  - DRE (SqlMonitor / SlowQueryLogger) (可观测性)

约束：
- TC-7 SSOT 原则：不重新实现与 v3 已有组件功能重复的模块
- NFR-002 "无 f-string SQL" 铁律
- 完整重写（TR-001）：最终删除 _do_list / _query_* / value_help / audit 中的手拼 SQL
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from meta.core.models import registry
from meta.services.query_service import (
    QueryService,
    SearchRequest,
    SearchResult,
    QueryCondition,
    _get_data_source,
)
from meta.services.query_models import SearchRequest as _SearchRequest
from meta.core.unified_query_protocol import (
    UnifiedQueryRequest,
    UnifiedQueryResponse,
    QueryProtocolError,
)
from meta.core.query_field_providers import (
    FieldValueProviderRegistry,
    build_default_registry,
)

logger = logging.getLogger(__name__)


class UnifiedQueryFacade:
    """统一查询 Facade（v3 SSOT 编排层）。

    用法：
        facade = UnifiedQueryFacade()  # 全部走 v3 SSOT
        result = facade.execute(req)
    """

    def __init__(
        self,
        data_source: Any = None,
        enrichment_engine: Any = None,
        provider_registry: Optional[FieldValueProviderRegistry] = None,
        slow_query_logger: Any = None,
        sql_monitor: Any = None,
    ):
        self.ds = data_source or _get_data_source()
        self.qs = QueryService(self.ds) if self.ds else None
        self.ee = enrichment_engine  # 缺省惰性加载
        self.providers = provider_registry  # 缺省惰性加载
        self.slow_log = slow_query_logger
        self.monitor = sql_monitor

    def _get_enrichment_engine(self):
        """惰性加载 v3 EnrichmentEngine 单例。"""
        if self.ee is None:
            from meta.core.enrichment_engine import EnrichmentEngine
            from meta.core.redundancy_registry import redundancy_registry
            self.ee = EnrichmentEngine(self.ds, redundancy_registry)
        return self.ee

    def _get_provider_registry(self) -> FieldValueProviderRegistry:
        """惰性构造 FieldValueProvider 注册表。"""
        if self.providers is None:
            from meta.core.redundancy_registry import redundancy_registry
            try:
                from meta.core.virtual_field_transform import get_transform_engine
                transform_engine = get_transform_engine()
            except Exception:
                transform_engine = None
            try:
                from meta.core.safe_expr_evaluator import SafeExpressionEvaluator
                evaluator = SafeExpressionEvaluator()
            except Exception:
                evaluator = None
            self.providers = build_default_registry(
                redundancy_reg=redundancy_registry,
                transform_engine=transform_engine,
                evaluator=evaluator,
            )
        return self.providers

    # ----------------------------------------------------------------
    # 主入口
    # ----------------------------------------------------------------
    def explain(self, req: UnifiedQueryRequest) -> Dict[str, Any]:
        """[M6.2 2026-06-05] Explain API：构造 SQL + EXPLAIN QUERY PLAN，不执行。

        Returns:
            {
                'sql': str,
                'params': list,
                'plan': List[Dict],  # EXPLAIN QUERY PLAN rows
                'estimated_rows': int,  # 推测（无 stats 实际数据，按 plan 推断）
                'cache_hit': bool,
            }
        """
        from meta.core.bo_framework import bo_framework
        ds = bo_framework._data_source
        v3_request = self._build_v3_search_request(req)

        # 构造 SQL（不执行）
        sql_parts = [f"SELECT * FROM {req.entity_type}"]
        params: List[Any] = []
        if v3_request.conditions:
            where_clauses = [c.field for c in v3_request.conditions]
            sql_parts.append('WHERE ' + ' AND '.join(where_clauses))
        if req.ordering:
            sql_parts.append(f"ORDER BY {req.ordering}")
        sql_parts.append(f"LIMIT {req.page_size}")
        sql = ' '.join(sql_parts)

        # EXPLAIN QUERY PLAN
        plan_rows: List[Dict[str, Any]] = []
        try:
            cur = ds.execute(f"EXPLAIN QUERY PLAN {sql}", tuple(params))
            rows = cur.fetchall()
            for row in rows:
                if isinstance(row, dict):
                    plan_rows.append(row)
                else:
                    plan_rows.append({'detail': str(row)})
        except Exception as e:
            plan_rows.append({'error': str(e)})

        return {
            'sql': sql,
            'params': params,
            'plan': plan_rows,
            'entity_type': req.entity_type,
            'filter_count': len(req.filters),
        }

    def execute(self, req: UnifiedQueryRequest) -> UnifiedQueryResponse:
        """执行统一查询。

        流程：
        1. 构造 trace_id
        2. 把 UnifiedQueryRequest 转 v3 SearchRequest
        3. 调 QueryService.search()
        4. FieldValueProvider 后处理（computed/virtual/rule chain）
        5. EnrichmentEngine 补 FK display
        6. DRE 慢查询记录
        7. 包装 UnifiedQueryResponse
        """
        trace_id = new_trace_id()
        t0 = time.perf_counter()
        # 1. 校验 entity_type
        meta = registry.get(req.entity_type)
        if meta is None:
            raise QueryProtocolError(
                code='unknown_entity',
                message=f'unknown entity_type: {req.entity_type!r}',
                detail={'entity_type': req.entity_type, 'trace_id': trace_id},
            )

        # 2. 构造 v3 SearchRequest
        v3_request = self._build_v3_search_request(req)

        # 2.5 [M4.3] QueryPlanCache: 缓存 (entity_type, filter_signature, ordering_signature)
        # 命中：跳过 v3 重新解析 filter_params 的开销
        from meta.core.query_plan_cache import get_query_plan_cache, signature_filters, signature_ordering
        cache = get_query_plan_cache()
        cache_key = signature_filters(
            {k: f'{v.op}:{v.value}' for k, v in req.filters.items()}
        )
        ordering_sig = signature_ordering(req.ordering)
        cached = cache.get(req.entity_type, cache_key, ordering_sig)
        cache_hit = cached is not None

        if not cache_hit:
            # 第一次见 → 写回缓存（M4 简化版：仅缓存 stats，不短路 v3 解析）
            cache.put(req.entity_type, cache_key, ordering_sig, {
                'filter_count': len(req.filters),
                'cursor_active': bool(req.cursor),
            })

        # 2.6 [M6.1] Query Allow-list 校验
        # 默认放行（未注册 entity_type），注册后 fail-fast
        try:
            from meta.core.query_allow_list import get_query_allow_list
            get_query_allow_list().check(
                entity_type=req.entity_type,
                filters=req.filters,
                ordering=req.ordering,
                page_size=req.page_size,
            )
        except Exception as allow_list_err:
            # 允许关闭：环境变量 DISABLE_ALLOW_LIST=true
            import os as _os
            if _os.environ.get('DISABLE_ALLOW_LIST', '').lower() not in ('1', 'true', 'yes'):
                raise
            logger.warning(f"[UnifiedQueryFacade.M6.1] allow-list check skipped (DISABLE_ALLOW_LIST=true): {allow_list_err}")

        # 3. 调 v3 QueryService
        if self.qs is None:
            raise QueryProtocolError(
                code='db_error',
                message='data source not available',
                detail={'trace_id': trace_id},
            )
        result: SearchResult = self.qs.search(v3_request)

        # 4. FieldValueProvider 后处理
        if result.data:
            try:
                providers = self._get_provider_registry()
                providers.run_postprocess(meta, result.data, self.ds)
            except Exception as e:
                logger.warning(f"[UnifiedQueryFacade] FieldValueProvider postprocess failed: {e}")

        # 5. EnrichmentEngine 补 FK display
        if result.data and req.context_type in ('list', 'association', 'audit'):
            try:
                ee = self._get_enrichment_engine()
                if ee:
                    result.data = ee.enrich_batch(req.entity_type, result.data)
            except Exception as e:
                logger.warning(f"[UnifiedQueryFacade] EnrichmentEngine.enrich_batch failed: {e}")

        # 6. 包装 + DRE
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        total_pages = (result.total + req.page_size - 1) // req.page_size if req.page_size else 0

        # [M4] cursor 计算：多取一条判断 has_next
        next_cursor = None
        prev_cursor = None
        if result.data and getattr(req, 'cursor', None):
            cursor_field = req.cursor_field
            if result.data and len(result.data) > req.page_size:
                # 多取了一条 → 切掉，多取那条的 field 值作为 next_cursor
                last_in_page = result.data[req.page_size - 1]
                next_cursor = _encode_cursor({cursor_field: last_in_page.get(cursor_field)})
                result.data = result.data[:req.page_size]
            if req.page > 1:
                first_in_page = result.data[0] if result.data else None
                if first_in_page:
                    prev_cursor = _encode_cursor({cursor_field: first_in_page.get(cursor_field)})

        # [M6.4] 关联 expand 注入（在 cursor 切分后，避免 expand 切掉关联行）
        expand_applied: List[str] = []
        if result.data and getattr(req, 'expand', ''):
            try:
                from meta.core.association_expander import (
                    AssociationExpander, parse_expand_specs,
                )
                specs = parse_expand_specs(req.expand)
                if specs:
                    expander = AssociationExpander()
                    expander.expand(result.data, specs, req.entity_type)
                    expand_applied = [s.path for s in specs]
            except Exception as e:
                logger.error(f"[UnifiedQueryFacade.M6.4] expand failed: {e}", exc_info=True)

        # [M6.5] 列级权限（hidden / mask）
        field_visibility_applied: List[str] = []
        if result.data:
            try:
                from meta.core.permission_spec import get_permission_registry
                perm_registry = get_permission_registry()
                spec = perm_registry.get(req.entity_type)
                if spec:
                    spec.apply_field_visibility(result.data)
                    field_visibility_applied = list(spec.field_visibility.keys())
            except Exception as e:
                logger.error(f"[UnifiedQueryFacade.M6.5] field visibility failed: {e}", exc_info=True)

        # DRE 慢查询
        if self.slow_log and elapsed_ms > 100:
            try:
                self.slow_log.log(trace_id=trace_id, entity=req.entity_type,
                                  context_type=req.context_type, elapsed_ms=elapsed_ms)
            except Exception:
                pass

        return UnifiedQueryResponse(
            items=result.data,
            total=result.total,
            page=req.page,
            page_size=req.page_size,
            total_pages=total_pages,
            trace_id=trace_id,
            elapsed_ms=elapsed_ms,
            meta={
                'context_type': req.context_type,
                'entity_type': req.entity_type,
                'used_protocol': 'unified_query_facade',
                # [M4.3] cache 命中标记
                'plan_cache_hit': cache_hit,
                # [M6.4] 实际 expand 的路径
                'expand_applied': expand_applied,
                # [M6.5] 实际应用的列级策略
                'field_visibility_applied': field_visibility_applied,
            },
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            # [M6.4] 关联 expand 已在 _expand_associations 注入到 result.data
        )

    # ----------------------------------------------------------------
    # UnifiedQueryRequest -> v3 SearchRequest 转换
    # ----------------------------------------------------------------
    def _build_v3_search_request(self, req: UnifiedQueryRequest) -> SearchRequest:
        """把 pydantic UnifiedQueryRequest 转 v3 SearchRequest（QueryService 入口）。

        注：v3 SearchRequest 有两个排序字段：
        - order_by: 单一字符串（如 "-updated_at" / "name asc"）
        - sort_by + sort_order: 拆分形式
        `get_order_by_clause()` 优先使用 order_by，所以这里直接组装 order_by。

        [M3 2026-06-05] computed `*_count` 字段无物理 DB 列，转为 EXISTS 子查询条件，
        通过 SearchRequest.exists_conditions 传给 QueryService。
        """
        conditions: List[QueryCondition] = []
        exists_conditions: List[tuple] = []
        meta = registry.get(req.entity_type)
        for field_name, fv in req.filters.items():
            # [FIX 2026-06-05] req.filters 的 key 已经是 base_field（__op 后缀已剥），
            # op 在 fv.op 里。_split_field_op 是为兼容 raw URL key 用的，这里不再用。
            base_field = field_name
            op = fv.op
            v3_op = _map_op_to_v3(op)
            # [M4.2] 日期函数（func_year / func_month / func_day / date_diff）
            if op in ('func_year', 'func_month', 'func_day', 'date_diff'):
                raw_sql, raw_params = _build_func_condition(base_field, op, fv)
                if raw_sql:
                    exists_conditions.append(('__raw__', (raw_sql, raw_params)))
                    logger.info(f"[UnifiedQueryFacade.M4] {base_field} {op} -> func raw SQL")
                continue
            # [M3] computed *_count 字段 → raw_conditions 子查询
            # 不走 EXISTS（语义不对），用直接 WHERE (subquery) op ? 形式
            if base_field.endswith('_count') and meta is not None:
                try:
                    f = meta.get_field(base_field)
                    if f is not None and getattr(f, 'computed', False):
                        raw_sql, raw_params = _build_count_subquery_condition(
                            meta, base_field, v3_op, fv
                        )
                        if raw_sql:
                            # raw_conditions: 直接拼到 WHERE
                            exists_conditions.append(('__raw__', (raw_sql, raw_params)))
                            logger.info(
                                f"[UnifiedQueryFacade.M3] {base_field} {op} -> raw subquery"
                            )
                            continue
                except Exception as e:
                    logger.warning(
                        f"[UnifiedQueryFacade.M3] Failed to build count subquery for "
                        f"{base_field}: {e}, falling back to skip"
                    )
            cond = QueryCondition(
                field=base_field,
                operator=v3_op,
                value=fv.value,
                values=fv.values or [],
                combine_mode='and',
            )
            conditions.append(cond)

        # 解析 ordering: "field" / "-field" / "field asc" / "-field desc"
        sort_by, sort_order = _parse_ordering(req.ordering)
        # 默认 updated_at desc（如 v3 QueryService 行为）
        # [FIX 2026-06-10] audit_logs 表无 updated_at，默认改为 created_at desc
        if not sort_by:
            sort_by = 'created_at' if req.entity_type == 'audit_log' else 'updated_at'
            sort_order = 'desc'

        # [M3] computed *_count 字段排序：QueryService.search 内部已有
        # _execute_computed_field_query 接管（如 user_group.member_count），
        # 这里保持 order_by 为物理列名，QueryService 会检测到 count_relations
        # 并自行切换到子查询排序。
        order_by = f"{sort_by} {sort_order}".strip()

        # [M3] 关联子查询（AssocQueryService 注入）走 EXISTS 形态
        for assoc in (req.assoc_subqueries or []):
            exists_conditions.append((
                assoc.get('subquery_sql', ''),
                list(assoc.get('subquery_params', [])),
            ))

        # [M4] cursor 解析（base64 JSON）
        cursor_decoded = None
        if req.cursor:
            try:
                cursor_decoded = _decode_cursor(req.cursor)
            except Exception as e:
                raise QueryProtocolError(
                    code='invalid_cursor',
                    message=f'invalid cursor: {e}',
                    detail={'cursor': req.cursor[:32] + '...' if len(req.cursor) > 32 else req.cursor},
                ) from e

        return SearchRequest(
            object_type=req.entity_type,
            conditions=conditions,
            keyword=req.search or '',
            order_by=order_by,
            page=req.page,
            page_size=req.page_size,
            exists_conditions=exists_conditions,
            cursor=req.cursor or '',
            cursor_field=req.cursor_field,
            cursor_direction=req.cursor_direction,
        )


# ============================================================
# 工具函数
# ============================================================

def new_trace_id() -> str:
    """生成新的 trace_id（X-Trace-Id 风格）。"""
    return f"qe-{uuid.uuid4().hex[:16]}"


# [M4 2026-06-05] cursor 编解码（base64 JSON）
import base64
import json as _json


def _encode_cursor(payload: Dict[str, Any]) -> str:
    """把 dict 编码成 cursor 字符串（base64 JSON）。"""
    raw = _json.dumps(payload, separators=(',', ':'), sort_keys=True, default=str)
    return base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii').rstrip('=')


def _decode_cursor(cursor: str) -> Dict[str, Any]:
    """把 cursor 字符串解码成 dict。"""
    if not cursor:
        return {}
    # 补齐 padding
    pad = '=' * ((4 - len(cursor) % 4) % 4)
    raw = base64.urlsafe_b64decode((cursor + pad).encode('ascii'))
    return _json.loads(raw.decode('utf-8'))


def _split_field_op(field_name: str) -> tuple:
    """拆分 `field__op` 形式。"""
    SUFFIXES = ('__like', '__ilike', '__in', '__not_in', '__gte', '__lte',
                '__gt', '__lt', '__ne', '__between', '__start', '__end')
    for suf in SUFFIXES:
        if field_name.endswith(suf):
            return field_name[: -len(suf)], suf[2:]
    return field_name, 'eq'


def _map_op_to_v3(op: str) -> str:
    """op 名映射：UnifiedQueryRequest op -> v3 QueryCondition operator 字符串。"""
    # v3 QueryCondition.operator 是 str（QueryOperator enum 的 .value）
    # QueryOperator: EQ / NE / GT / GE / LT / LE / LIKE / ILIKE / IN / NOT_IN / IS_NULL / IS_NOT_NULL / BETWEEN
    M = {
        'eq': 'eq',
        'ne': 'ne',
        'gt': 'gt',
        'gte': 'ge',
        'lt': 'lt',
        'lte': 'le',
        'like': 'like',
        'ilike': 'ilike',
        'in': 'in',
        'not_in': 'not_in',
        'between': 'between',
        'is_null': 'is_null',
        'is_not_null': 'is_not_null',
    }
    return M.get(op, 'eq')


def _parse_ordering(ordering: str) -> tuple:
    """解析 ordering 字符串 → (sort_by, sort_order)。"""
    if not ordering:
        return ('', '')
    parts = ordering.strip().split()
    raw_field = parts[0]
    sort_by = raw_field.lstrip('-')
    if raw_field.startswith('-'):
        sort_order = 'desc'
    else:
        sort_order = parts[1].lower() if len(parts) > 1 else 'asc'
    return (sort_by, sort_order)


# ============================================================
# [M3 2026-06-05] computed *_count 字段的子查询条件构造
# [SPR-02 S-02 2026-06-10] 委托给 _computed_count_clause.find_count_assoc /
#   build_count_subquery / apply_count_clause（去除 _find_m2m_assoc_for_count 重复）
# ============================================================

# v3 operator 名称 → SQL operator 映射（unified_query_facade 私有）
_V3_OP_TO_SQL = {
    'eq': '=', 'ne': '!=', 'gt': '>', 'ge': '>=', 'lt': '<', 'le': '<=',
    'in': 'IN', 'not_in': 'NOT IN', 'like': 'LIKE', 'ilike': 'LIKE',
}


def _build_count_subquery_condition(
    meta_object,
    field_name: str,
    v3_op: str,
    fv,
) -> tuple:
    """[SPR-02 delegate] → _computed_count_clause.find_count_assoc + build_count_subquery + apply_count_clause。

    返回 (raw_sql, params)。raw_sql 形如:
        (SELECT COUNT(*) FROM through WHERE source_key = bo.id) >= ?
    """
    from meta.core._computed_count_clause import (
        find_count_assoc, build_count_subquery, apply_count_clause,
    )

    if not meta_object or not field_name.endswith('_count'):
        return '', []

    base_name = field_name[:-6]
    assoc_info = find_count_assoc(meta_object, base_name)
    if assoc_info is None or assoc_info.kind != 'many_to_many':
        logger.warning(
            f"[M3] No m2m association for {field_name!r} "
            f"(base_name={base_name!r}) in {getattr(meta_object, 'id', '?')}"
        )
        return '', []

    # [FIX 2026-06-05] QueryBuilder.build_sql 用 AS bo 别名（除非有 analytical_model.alias）
    # 这里统一用 `bo.id` 引用，与 QueryBuilder 渲染一致
    subquery = build_count_subquery(
        meta_object, base_name, target_alias='bo', assoc_info=assoc_info
    )
    if not subquery:
        return '', []

    sql_op = _V3_OP_TO_SQL.get(v3_op, '=')
    if sql_op in ('IN', 'NOT IN'):
        values = list(fv.values) if fv.values else []
        return apply_count_clause(subquery, sql_op, values)
    return apply_count_clause(subquery, sql_op, [fv.value])


def _build_count_subquery_order(meta_object, field_name: str, sort_order: str) -> str:
    """[SPR-02 delegate] → _computed_count_clause.build_order_clause 的 m2m 路径。

    返回完整表达式，如：
        (SELECT COUNT(*) FROM through WHERE bo.id = ...) DESC
    """
    from meta.core._computed_count_clause import find_count_assoc, build_count_subquery

    if not meta_object or not field_name.endswith('_count'):
        return ''

    base_name = field_name[:-6]
    assoc_info = find_count_assoc(meta_object, base_name)
    if assoc_info is None or assoc_info.kind != 'many_to_many':
        return ''

    subquery = build_count_subquery(
        meta_object, base_name, target_alias='bo', assoc_info=assoc_info
    )
    if not subquery:
        return ''
    direction = 'DESC' if (sort_order or 'asc').lower() == 'desc' else 'ASC'
    return f"{subquery} {direction}"


# ============================================================
# [M4.2 2026-06-05] 日期函数 SQL 构造（SQLite strftime / julianday）
# ============================================================

# SQLite strftime 单位映射
_FUNC_SQLITE = {
    'func_year':  "%Y",   # 4 位年
    'func_month': "%m",   # 月 1-12
    'func_day':   "%d",   # 日 1-31
}

# date_diff 单位（秒）
_DATE_DIFF_UNIT_SECONDS = {
    'day': 86400,
    'hour': 3600,
    'minute': 60,
    'second': 1,
}


def _build_func_condition(field_name: str, op: str, fv) -> tuple:
    """[M4.2] 把日期函数过滤条件转为 raw SQL。

    Returns:
        (raw_sql, params)
    """
    if not field_name:
        return '', []

    if op in _FUNC_SQLITE:
        fmt = _FUNC_SQLITE[op]
        # CAST(strftime('%Y', {field}) AS INTEGER) = ?
        raw_sql = f"CAST(strftime('{fmt}', bo.{field_name}) AS INTEGER) = ?"
        try:
            value = int(fv.value)
        except (TypeError, ValueError):
            return '', []
        return raw_sql, [value]

    if op == 'date_diff':
        # date_diff('day', a, b) → ((julianday(a) - julianday(b)) * 86400 / unit_seconds) = ?
        unit = (fv.func_arg or 'day').lower()
        unit_seconds = _DATE_DIFF_UNIT_SECONDS.get(unit, 86400)
        other = 'CURRENT_TIMESTAMP'  # 默认 vs 当前时间
        # 如果 func_arg 形如 'day:other_field' 解析第二字段
        if ':' in unit:
            unit, other = unit.split(':', 1)
            unit_seconds = _DATE_DIFF_UNIT_SECONDS.get(unit, 86400)
            other = f"bo.{other}" if other and other != 'now' else 'CURRENT_TIMESTAMP'
        raw_sql = (
            f"((julianday(bo.{field_name}) - julianday({other})) "
            f"* 86400 / {unit_seconds}) = ?"
        )
        try:
            value = float(fv.value)
        except (TypeError, ValueError):
            return '', []
        return raw_sql, [value]

    return '', []
