from flask import Blueprint, request, jsonify
import os
from meta.services.query_service import (
    QueryService, QueryCondition, SearchRequest,
    AggregateMeasure, AggregateRequest, AggregateResult
)
from meta.core.datasource import get_data_source

query_bp = Blueprint('query', __name__, url_prefix='/api/v1/query')

_query_service = None


def _get_query_service():
    global _query_service
    if _query_service is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        ds = get_data_source('sqlite', database=db_path)
        _query_service = QueryService(ds)
    return _query_service


@query_bp.route('/search', methods=['POST'])
def search():
    body = request.get_json(silent=True) or {}
    service = _get_query_service()

    conditions = []
    for c in body.get('conditions', []):
        conditions.append(QueryCondition(
            field=c.get('field', ''),
            operator=c.get('operator', 'eq'),
            value=c.get('value'),
            values=c.get('values', []),
        ))

    search_request = SearchRequest(
        object_type=body.get('object_type', ''),
        conditions=conditions,
        keyword=body.get('keyword', ''),
        hierarchy_path=body.get('hierarchy_path', ''),
        order_by=body.get('order_by', ''),
        page=body.get('page', 1),
        page_size=body.get('page_size', 20),
        include_relations=body.get('include_relations', False),
        filter_params=body.get('filter_params', {}),
        filter_scope=body.get('filter_scope', 'global'),
    )

    result = service.search(search_request)

    return jsonify({
        'success': True,
        'data': result.data,
        'total': result.total,
        'page': result.page,
        'page_size': result.page_size,
        'total_pages': result.total_pages,
    })


@query_bp.route('/full-text', methods=['GET'])
def full_text_search():
    keyword = request.args.get('keyword', '')
    types_str = request.args.get('types', '')
    limit = request.args.get('limit', 50, type=int)

    object_types = [t.strip() for t in types_str.split(',') if t.strip()] if types_str else None

    service = _get_query_service()
    data = service.full_text_search(keyword, object_types, limit)

    return jsonify({
        'success': True,
        'data': data,
        'keyword': keyword,
    })


@query_bp.route('/hierarchy/<path:path>', methods=['GET'])
def hierarchy_query(path):
    include_children = request.args.get('include_children', 'false').lower() == 'true'

    service = _get_query_service()
    data = service.query_by_hierarchy_path(path, include_children)

    return jsonify({
        'success': True,
        'data': data,
        'path': path,
    })


@query_bp.route('/suggest/<object_type>/<field>', methods=['GET'])
def suggest(object_type, field):
    prefix = request.args.get('prefix', '')
    limit = request.args.get('limit', 10, type=int)

    service = _get_query_service()
    data = service.suggest(object_type, field, prefix, limit)

    return jsonify({
        'success': True,
        'data': data,
        'object_type': object_type,
        'field': field,
    })


@query_bp.route('/aggregate', methods=['POST'])
def aggregate():
    body = request.get_json(silent=True) or {}
    service = _get_query_service()

    measures = []
    for m in body.get('measures', []):
        measures.append(AggregateMeasure(
            field=m.get('field', ''),
            aggregation=m.get('aggregation', 'count'),
        ))

    agg_request = AggregateRequest(
        object_type=body.get('object_type', ''),
        measures=measures,
        dimensions=body.get('dimensions', []),
        filters=body.get('filters', []),
    )

    result = service.aggregate(agg_request)

    return jsonify({
        'success': result.success,
        'data': result.data,
        'total': result.total,
        'message': result.message,
    })
