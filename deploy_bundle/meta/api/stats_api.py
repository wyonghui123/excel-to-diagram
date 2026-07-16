from flask import Blueprint, jsonify, request, g
from meta.core.datasource import get_data_source
from meta.services.auth_middleware import get_current_user
import json
from datetime import datetime, timedelta

stats_bp = Blueprint('stats', __name__, url_prefix='/api/v1')

_data_source = None
_analytical_engine = None
_aggregate_manager = None


def _get_data_source():
    global _data_source
    if _data_source is None:
        import os
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def _get_analytical_engine():
    global _analytical_engine
    if _analytical_engine is None:
        from meta.core.analytical_engine import AnalyticalEngine
        _analytical_engine = AnalyticalEngine(_get_data_source())
    return _analytical_engine


def _get_aggregate_manager():
    global _aggregate_manager
    if _aggregate_manager is None:
        from meta.core.aggregate_manager import AggregateManager
        _aggregate_manager = AggregateManager(_get_data_source())
        _aggregate_manager.register_all()
    return _aggregate_manager


def _safe_count(ds, table, where_clause='', params=None):
    try:
        sql = f"SELECT COUNT(*) FROM {table}"
        if where_clause:
            sql += f" WHERE {where_clause}"
        cursor = ds.execute(sql, params or [])
        return cursor.fetchone()[0]
    except Exception:
        return 0


def _compute_trend(ds, table, date_field='created_at'):
    week_start = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
    month_start = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
    try:
        cursor = ds.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {date_field} >= ?", [week_start]
        )
        week_count = cursor.fetchone()[0]
    except Exception:
        week_count = 0
    try:
        cursor = ds.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {date_field} >= ?", [month_start]
        )
        month_count = cursor.fetchone()[0]
    except Exception:
        month_count = 0
    return {'week': week_count, 'month': month_count}


def _get_user_domain_scopes(ds, user):
    if not user or '*' in (user.permissions if hasattr(user, 'permissions') else []):
        return None
    roles = getattr(user, 'roles', []) or []
    if 'admin' in roles:
        return None
    try:
        user_id = getattr(user, 'user_id', None)
        if user_id is None:
            return None
        cursor = ds.execute(
            """SELECT rds.dimension_values
               FROM role_dimension_scopes rds
               JOIN group_roles gr ON rds.role_id = gr.role_id
               JOIN user_group_members ugm ON gr.group_id = ugm.group_id
               WHERE ugm.user_id = ? AND rds.dimension_code = 'domain'""",
            [user_id]
        )
        all_domain_ids = set()
        for row in cursor.fetchall():
            try:
                vals = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                all_domain_ids.update(vals if isinstance(vals, list) else [])
            except (json.JSONDecodeError, TypeError):
                pass
        if not all_domain_ids:
            return None
        cursor = ds.execute(
            f"SELECT name FROM domains WHERE id IN ({','.join(['?'] * len(all_domain_ids))})",
            list(all_domain_ids)
        )
        labels = [row[0] for row in cursor.fetchall()]
        return {
            'domain_ids': list(all_domain_ids),
            'labels': labels
        }
    except Exception:
        return None


def _compute_scoped_stats(ds, domain_ids):
    try:
        placeholders = ','.join(['?'] * len(domain_ids))
        params = list(domain_ids)

        scoped_domains = _safe_count(
            ds, 'domains',
            f'id IN ({placeholders})', params
        )

        scoped_bo = _safe_count(
            ds, 'business_objects bo',
            f"""bo.service_module_id IN (
                SELECT sm.id FROM service_modules sm
                JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                WHERE sd.domain_id IN ({placeholders})
            )""", params
        )

        scoped_rel = _safe_count(
            ds, 'relationships r',
            f"""r.source_business_object_id IN (
                SELECT bo.id FROM business_objects bo
                JOIN service_modules sm ON bo.service_module_id = sm.id
                JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                WHERE sd.domain_id IN ({placeholders})
            )""", params
        )

        return {
            'domains': scoped_domains,
            'business_objects': scoped_bo,
            'relationships': scoped_rel
        }
    except Exception:
        return None


@stats_bp.route('/stats/overview', methods=['GET'])
def get_stats_overview():
    try:
        ds = _get_data_source()

        result = {
            'products': _safe_count(ds, 'products'),
            'versions': _safe_count(ds, 'versions'),
            'domains': _safe_count(ds, 'domains'),
            'business_objects': _safe_count(ds, 'business_objects'),
            'relationships': _safe_count(ds, 'relationships'),
        }

        trends = {
            'products': _compute_trend(ds, 'products'),
            'versions': _compute_trend(ds, 'versions'),
            'domains': _compute_trend(ds, 'domains'),
            'business_objects': _compute_trend(ds, 'business_objects'),
            'relationships': _compute_trend(ds, 'relationships'),
        }

        user = get_current_user()
        domain_scopes = _get_user_domain_scopes(ds, user) if user else None
        scoped = None
        if domain_scopes and domain_scopes.get('domain_ids'):
            scoped_stats = _compute_scoped_stats(ds, domain_scopes['domain_ids'])
            if scoped_stats:
                scoped = {
                    'domains': scoped_stats['domains'],
                    'business_objects': scoped_stats['business_objects'],
                    'relationships': scoped_stats['relationships'],
                    'dimension_labels': domain_scopes.get('labels', [])
                }

        return jsonify({
            'success': True,
            'data': result,
            'trends': trends,
            'scoped': scoped
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/aggregates', methods=['GET'])
def list_aggregates():
    try:
        manager = _get_aggregate_manager()

        return jsonify({
            'success': True,
            'data': manager.get_registered_aggregates()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/aggregates/<aggregate_id>/query', methods=['POST'])
def query_aggregate(aggregate_id):
    try:
        manager = _get_aggregate_manager()

        body = request.get_json() or {}

        results = manager.query(
            aggregate_id,
            filters=body.get('filters'),
            order_by=body.get('order_by'),
            limit=body.get('limit')
        )

        return jsonify({
            'success': True,
            'data': results,
            'meta': {
                'aggregate_id': aggregate_id,
                'row_count': len(results),
                'freshness': manager.get_freshness(aggregate_id),
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/aggregates/<aggregate_id>/refresh', methods=['POST'])
def refresh_aggregate(aggregate_id):
    try:
        manager = _get_aggregate_manager()

        row_count = manager.refresh(aggregate_id, force=True)

        return jsonify({
            'success': True,
            'data': {
                'aggregate_id': aggregate_id,
                'row_count': row_count,
                'freshness': manager.get_freshness(aggregate_id),
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/aggregates/freshness', methods=['GET'])
def get_all_freshness():
    try:
        manager = _get_aggregate_manager()

        return jsonify({
            'success': True,
            'data': manager.get_all_freshness()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/olap/<object_type>', methods=['POST'])
def execute_olap_query(object_type):
    try:
        engine = _get_analytical_engine()

        model = engine.get_analytical_model(object_type)
        if not model or not model.enabled:
            return jsonify({
                'success': False,
                'message': f'对象类型 {object_type} 未启用分析模型'
            }), 404

        body = request.get_json() or {}

        dimensions = body.get('dimensions', [])
        measures = body.get('measures', [])
        filters = body.get('filters')
        order_by = body.get('order_by')
        limit = body.get('limit')
        use_cache = body.get('use_cache', True)

        if not dimensions:
            return jsonify({
                'success': False,
                'message': '至少需要指定一个维度'
            }), 400

        if not measures:
            return jsonify({
                'success': False,
                'message': '至少需要指定一个度量'
            }), 400

        results = engine.execute_olap_query(
            object_type, dimensions, measures, filters, order_by, limit,
            use_cache=use_cache
        )

        return jsonify({
            'success': True,
            'data': results,
            'meta': {
                'object_type': object_type,
                'dimensions': dimensions,
                'measures': measures,
                'row_count': len(results),
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/olap/<object_type>/drill-down', methods=['POST'])
def drill_down_query(object_type):
    try:
        engine = _get_analytical_engine()

        model = engine.get_analytical_model(object_type)
        if not model or not model.enabled:
            return jsonify({
                'success': False,
                'message': f'对象类型 {object_type} 未启用分析模型'
            }), 404

        body = request.get_json() or {}

        current_dimensions = body.get('current_dimensions', [])
        drill_dimension = body.get('drill_dimension', '')
        measures = body.get('measures', [])
        filters = body.get('filters')

        if not drill_dimension:
            return jsonify({
                'success': False,
                'message': '需要指定下钻维度'
            }), 400

        results = engine.drill_down(
            object_type, current_dimensions, drill_dimension, measures, filters
        )

        nav = engine.get_hierarchy_navigation(
            object_type, current_dimensions + [drill_dimension]
        )

        return jsonify({
            'success': True,
            'data': results,
            'meta': {
                'object_type': object_type,
                'dimensions': current_dimensions + [drill_dimension],
                'measures': measures,
                'drill_dimension': drill_dimension,
                'row_count': len(results),
                'navigation': {
                    'drill_down_options': nav.drill_down_options,
                    'roll_up_options': nav.roll_up_options,
                    'hierarchy_path': nav.hierarchy_path,
                },
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/olap/<object_type>/roll-up', methods=['POST'])
def roll_up_query(object_type):
    try:
        engine = _get_analytical_engine()

        model = engine.get_analytical_model(object_type)
        if not model or not model.enabled:
            return jsonify({
                'success': False,
                'message': f'对象类型 {object_type} 未启用分析模型'
            }), 404

        body = request.get_json() or {}

        current_dimensions = body.get('current_dimensions', [])
        roll_to_dimensions = body.get('roll_to_dimensions', [])
        measures = body.get('measures', [])
        filters = body.get('filters')

        if not roll_to_dimensions:
            return jsonify({
                'success': False,
                'message': '需要指定上卷目标维度'
            }), 400

        results = engine.roll_up(
            object_type, current_dimensions, roll_to_dimensions, measures, filters
        )

        nav = engine.get_hierarchy_navigation(object_type, roll_to_dimensions)

        return jsonify({
            'success': True,
            'data': results,
            'meta': {
                'object_type': object_type,
                'dimensions': roll_to_dimensions,
                'measures': measures,
                'row_count': len(results),
                'navigation': {
                    'drill_down_options': nav.drill_down_options,
                    'roll_up_options': nav.roll_up_options,
                    'hierarchy_path': nav.hierarchy_path,
                },
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/model/<object_type>', methods=['GET'])
def get_analytical_model_info(object_type):
    try:
        engine = _get_analytical_engine()

        model = engine.get_analytical_model(object_type)
        if not model or not model.enabled:
            return jsonify({
                'success': False,
                'message': f'对象类型 {object_type} 未启用分析模型'
            }), 404

        return jsonify({
            'success': True,
            'data': engine.get_analytical_summary(object_type)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/model/<object_type>/navigation', methods=['POST'])
def get_hierarchy_navigation(object_type):
    try:
        engine = _get_analytical_engine()

        model = engine.get_analytical_model(object_type)
        if not model or not model.enabled:
            return jsonify({
                'success': False,
                'message': f'对象类型 {object_type} 未启用分析模型'
            }), 404

        body = request.get_json() or {}
        current_dimensions = body.get('current_dimensions', [])

        nav = engine.get_hierarchy_navigation(object_type, current_dimensions)

        return jsonify({
            'success': True,
            'data': {
                'object_type': nav.object_type,
                'current_dimensions': nav.current_dimensions,
                'drill_down_options': nav.drill_down_options,
                'roll_up_options': nav.roll_up_options,
                'hierarchy_path': nav.hierarchy_path,
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/model/<object_type>/dimensions/<dimension_id>/members', methods=['GET'])
def get_dimension_members(object_type, dimension_id):
    try:
        engine = _get_analytical_engine()

        model = engine.get_analytical_model(object_type)
        if not model or not model.enabled:
            return jsonify({
                'success': False,
                'message': f'对象类型 {object_type} 未启用分析模型'
            }), 404

        filters = {}
        for key, value in request.args.items():
            if key.startswith('filter_'):
                filter_key = key[7:]
                try:
                    filters[filter_key] = int(value)
                except (ValueError, TypeError):
                    filters[filter_key] = value

        search = request.args.get('search')
        try:
            limit = int(request.args.get('limit', 100))
        except (ValueError, TypeError):
            limit = 100

        members = engine.get_dimension_members(
            object_type, dimension_id,
            filters=filters if filters else None,
            search=search,
            limit=limit
        )

        return jsonify({
            'success': True,
            'data': [
                {
                    'value': m.value,
                    'display_name': m.display_name,
                    'count': m.count,
                }
                for m in members
            ],
            'meta': {
                'object_type': object_type,
                'dimension_id': dimension_id,
                'member_count': len(members),
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/cache', methods=['GET'])
def get_cache_stats():
    try:
        engine = _get_analytical_engine()

        return jsonify({
            'success': True,
            'data': engine.get_cache_stats()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@stats_bp.route('/stats/cache/invalidate', methods=['POST'])
def invalidate_cache():
    try:
        engine = _get_analytical_engine()

        body = request.get_json() or {}
        object_type = body.get('object_type', '')

        engine.invalidate_cache(object_type)

        return jsonify({
            'success': True,
            'data': {
                'invalidated': object_type or 'all',
                'cache_stats': engine.get_cache_stats(),
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
