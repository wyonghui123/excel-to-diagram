# -*- coding: utf-8 -*-
"""
M8 消费侧 API（QE-M8-2026-06-v2）

[M8 2026-06-06] 6 个 P0 消费侧能力端点：
- VP-1 ValueHelp (`GET /<entity>/valuehelp`)
- VP-2 Nested DSL (`POST /<entity>/query`)
- VP-3 Aggregate (`GET /<entity>/aggregate`)
- VP-4 Reverse Expand (`GET /<entity>/<id>/reverse/<assoc>`)
- VP-5 ETag / If-None-Match（middleware via app_builder）
- VP-6 Custom Order（m8_utils.parse_ordering）

不重复实现 v3 已有能力，作为 facade 入口包装。
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

# ============================================================
# Blueprint 集合
# ============================================================
valuehelp_bp = Blueprint('m8_valuehelp', __name__, url_prefix='/api/v1')
query_dsl_bp = Blueprint('m8_query_dsl', __name__, url_prefix='/api/v1')
aggregate_bp = Blueprint('m8_aggregate', __name__, url_prefix='/api/v1')
reverse_bp = Blueprint('m8_reverse', __name__, url_prefix='/api/v1')


# ============================================================
# VP-1 ValueHelp
# ============================================================
@valuehelp_bp.route('/<entity>/valuehelp', methods=['GET'])
def valuehelp(entity: str):
    """VP-1 值帮助 / 自动补全。

    Query params:
    - q / search: 搜索关键字
    - top / pageSize: top N (default=20, max=100)
    - display / display_fields: 展示字段（comma-separated）
    - locale: 国际化（v3.1 集成 M7.5）
    - order_by: 排序字段
    - filter[k__op]=v: 任意 v3 filter
    """
    from meta.core.m8_utils import parse_valuehelp_args
    from meta.core.unified_query_facade import get_query_facade
    from meta.core.unified_query_protocol import (
        UnifiedQueryRequest, FilterValue,
    )

    args = parse_valuehelp_args(request.args.to_dict(flat=True))
    q, top, display_fields, locale, ordering, extra_filters = (
        args['q'], args['top'], args['display_fields'],
        args['locale'], args['ordering'], args['extra_filters'],
    )

    # 默认 display 字段
    if not display_fields:
        try:
            from meta.core.models import registry
            meta = registry.get(entity)
            display_fields = (
                getattr(meta, 'value_help_fields', None)
                or getattr(meta, 'display_field', None)
                or ['name']
            )
            if isinstance(display_fields, str):
                display_fields = [display_fields]
        except Exception:
            display_fields = ['name']

    # 构造 filters
    filters: Dict[str, FilterValue] = {}
    # 1. q 关键字 → 多字段 OR ILIKE
    if q:
        # 用 like_q__ilike 简化处理（单字段时）
        # 多字段 OR：构造为一个组合条件
        for f in display_fields:
            filters[f'{f}__or_ilike'] = FilterValue(op='ilike', value=f'%{q}%')
    # 2. 额外 filter
    for field, value in extra_filters.items():
        if '__' in field:
            fname, op = field.rsplit('__', 1)
        else:
            fname, op = field, 'eq'
        filters[field] = FilterValue(op=op, value=value)

    # 排序
    if not ordering:
        ordering = display_fields[0] if display_fields else 'id'

    # 执行
    try:
        facade = get_query_facade()
        req = UnifiedQueryRequest(
            entity_type=entity,
            page_size=top,
            ordering=ordering,
            filters=filters,
        )
        result = facade.execute(req)
    except Exception as e:
        logger.error(f"[M8.VP-1] valuehelp failed: {e}", exc_info=True)
        return jsonify({'error': 'valuehelp_failed', 'message': str(e)}), 500

    return jsonify({
        'items': result.items,
        'total': result.total,
        'has_more': result.total > top,
        'display_fields': display_fields,
        'locale': locale,
        'q': q,
    })


# ============================================================
# VP-2 Nested DSL
# ============================================================
@query_dsl_bp.route('/<entity>/query', methods=['POST'])
def nested_query(entity: str):
    """VP-2 嵌套 WHERE DSL。

    Body:
    {
      "where": {...},
      "order_by": [{"col": "desc"}],
      "page": 1,
      "page_size": 20,
      "expand": ["user(id,name)", "tags(name)"]
    }
    """
    from meta.core.nested_where_dsl import NestedWhereParser, NestedWhereError
    from meta.core.unified_query_facade import get_query_facade
    from meta.core.unified_query_protocol import (
        UnifiedQueryRequest, FilterValue,
    )

    body = request.get_json(silent=True) or {}
    where = body.get('where') or {}
    order_by = body.get('order_by') or []
    page = int(body.get('page') or 1)
    page_size = int(body.get('page_size') or 20)
    expand = body.get('expand') or []

    # 1. 解析嵌套 WHERE
    parser = NestedWhereParser(base_alias='bo')
    try:
        where_sql, where_params, joins = parser.parse(where)
    except NestedWhereError as e:
        return jsonify({
            'error': e.code,
            'message': e.message,
            'detail': e.detail,
        }), 400

    # 2. 转化为 v3 FilterValue（简化版：扁平 AND 路径）
    # 嵌套 DSL → v3 Flat 的转化在 v3.1 子任务实现
    # 这里 M8 VP-2 阶段先支持：单层 AND / 简单条件
    filters: Dict[str, FilterValue] = {}
    if isinstance(where, dict):
        # 提取顶层简单条件
        for key, value in where.items():
            if key in ('and', 'or', 'not'):
                continue
            if '__' in key:
                fname, op = key.rsplit('__', 1)
            else:
                fname, op = key, 'eq'
            filters[key] = FilterValue(op=op, value=value)

    # 3. 排序
    ordering_str = ''
    if isinstance(order_by, list):
        parts = []
        for o in order_by:
            if isinstance(o, dict):
                for col, direction in o.items():
                    parts.append(
                        f'-{col}' if direction and str(direction).lower() == 'desc'
                        else col
                    )
            elif isinstance(o, str):
                parts.append(o)
        ordering_str = ','.join(parts)
    elif isinstance(order_by, str):
        ordering_str = order_by

    # 4. 执行
    try:
        facade = get_query_facade()
        req = UnifiedQueryRequest(
            entity_type=entity,
            page=page,
            page_size=page_size,
            ordering=ordering_str,
            filters=filters,
        )
        result = facade.execute(req)
    except Exception as e:
        logger.error(f"[M8.VP-2] query failed: {e}", exc_info=True)
        return jsonify({'error': 'query_failed', 'message': str(e)}), 500

    return jsonify({
        'items': result.items,
        'total': result.total,
        'page': page,
        'page_size': page_size,
        'where_sql': where_sql,
        'joins': joins,
        'complex_where': where,  # 返回原始复杂 where 供调试
    })


# ============================================================
# VP-3 Aggregate (REST GET)
# ============================================================
@aggregate_bp.route('/<entity>/aggregate', methods=['GET'])
def aggregate_rest(entity: str):
    """VP-3 REST 风格聚合。

    Query params:
    - group_by: 维度字段（comma-separated）
    - count / sum / avg / min / max: 聚合字段（可重复）
    - filter[k__op]=v: 任意 v3 filter
    - having[k__op]=v: 聚合后过滤（v3.1）
    """
    from meta.core.unified_query_protocol import FilterValue
    from meta.core.app_builder import get_query_service

    dimensions = [
        c.strip() for c in (request.args.get('group_by') or '').split(',')
        if c.strip()
    ]
    measures = []
    for agg in ('count', 'sum', 'avg', 'min', 'max'):
        for f in request.args.getlist(agg) or []:
            if f.strip():
                measures.append({'field': f.strip(), 'aggregation': agg})

    # 简单 v3 filter 收集
    filters: Dict[str, FilterValue] = {}
    for k, v in request.args.items():
        if k.startswith('filter[') and k.endswith(']'):
            field = k[len('filter['):-1]
            if '__' in field:
                fname, op = field.rsplit('__', 1)
            else:
                fname, op = field, 'eq'
            filters[field] = FilterValue(op=op, value=v)

    # 调用底层 service（已存在 _query_api.aggregate）
    try:
        from meta.api.query_api import _get_query_service
        from meta.services.query_service import AggregateRequest, AggregateMeasure
        service = _get_query_service()
        agg_request = AggregateRequest(
            object_type=entity,
            dimensions=dimensions,
            measures=[
                AggregateMeasure(
                    field=m['field'],
                    aggregation=m['aggregation'],
                )
                for m in measures
            ],
            filters=list(filters.items()),
        )
        result = service.aggregate(agg_request)
        return jsonify(_aggregate_to_dict(result))
    except Exception as e:
        logger.error(f"[M8.VP-3] aggregate failed: {e}", exc_info=True)
        return jsonify({'error': 'aggregate_failed', 'message': str(e)}), 500


def _aggregate_to_dict(result: Any) -> Dict:
    """把 AggregateResult 序列化为 dict（容错处理）。"""
    if result is None:
        return {'rows': [], 'total_groups': 0}
    if isinstance(result, dict):
        return result
    # 尝试访问属性
    out: Dict[str, Any] = {}
    if hasattr(result, 'rows'):
        out['rows'] = result.rows
    if hasattr(result, 'total_groups'):
        out['total_groups'] = result.total_groups
    if hasattr(result, 'dimensions'):
        out['dimensions'] = result.dimensions
    if hasattr(result, 'measures'):
        out['measures'] = [
            getattr(m, 'field', str(m)) for m in result.measures
        ]
    return out


# ============================================================
# VP-4 Reverse Expand
# ============================================================
@reverse_bp.route(
    '/<entity>/<int:parent_id>/reverse/<assoc>',
    methods=['GET'],
)
def reverse_expand(entity: str, parent_id: int, assoc: str):
    """VP-4 反向关联展开。

    URL: /api/v1/<entity>/<parent_id>/reverse/<assoc>
    e.g. /api/v1/customer/1/reverse/orders?status__eq=active
    """
    from meta.core.m8_utils import find_reverse_association
    from meta.core.unified_query_facade import get_query_facade
    from meta.core.unified_query_protocol import (
        UnifiedQueryRequest, FilterValue,
    )
    from meta.core.models import registry

    meta = registry.get(entity)
    if meta is None:
        return jsonify({
            'error': 'entity_not_found',
            'message': f'entity {entity} not registered',
        }), 404

    reverse_def = find_reverse_association(meta, assoc)
    if reverse_def is None:
        return jsonify({
            'error': 'association_not_found',
            'message': f'{entity} has no reverse association {assoc}',
        }), 404

    target_entity = reverse_def['target_entity']
    fk_field = reverse_def['source_key']

    # 构造 v3 filter：target.fk = parent_id
    filters: Dict[str, FilterValue] = {
        f'{fk_field}__eq': FilterValue(op='eq', value=parent_id),
    }

    # 用户的 filter
    for k, v in request.args.items():
        if k.startswith('filter[') and k.endswith(']'):
            field = k[len('filter['):-1]
            if '__' in field:
                fname, op = field.rsplit('__', 1)
            else:
                fname, op = field, 'eq'
            filters[field] = FilterValue(op=op, value=v)

    ordering = request.args.get('order_by', '-id')
    try:
        page_size = int(request.args.get('pageSize', 20))
    except (TypeError, ValueError):
        page_size = 20
    expand = request.args.get('expand', '')

    try:
        facade = get_query_facade()
        req = UnifiedQueryRequest(
            entity_type=target_entity,
            page_size=page_size,
            ordering=ordering,
            filters=filters,
            expand=expand,
        )
        result = facade.execute(req)
    except Exception as e:
        logger.error(f"[M8.VP-4] reverse expand failed: {e}", exc_info=True)
        return jsonify({'error': 'reverse_failed', 'message': str(e)}), 500

    return jsonify({
        'items': result.items,
        'total': result.total,
        'association': assoc,
        'target_entity': target_entity,
        'parent': {'id': parent_id, 'type': entity},
    })


# ============================================================
# 注册到 app_builder
# ============================================================
def register_m8_blueprints(app) -> None:
    """注册 M8 全部 4 个 blueprint。"""
    app.register_blueprint(valuehelp_bp)
    app.register_blueprint(query_dsl_bp)
    app.register_blueprint(aggregate_bp)
    app.register_blueprint(reverse_bp)
    logger.info('[M8] registered 4 blueprints: valuehelp, query_dsl, aggregate, reverse')
