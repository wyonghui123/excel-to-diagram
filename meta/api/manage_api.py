from flask import Blueprint, request, jsonify, g
from meta.services.manage_service import ManageService, CreateRequest, UpdateRequest, DeleteRequest
from meta.services.query_service import QueryService, SearchRequest, QueryCondition
from meta.services.audit_service import AuditService, AuditQuery
from meta.services.hierarchy_filter_service import HierarchyFilterService
from meta.services.cascade_service import get_type_order, HierarchyConfigLoader
from meta.services.auth_middleware import login_required, get_current_user, is_admin
from meta.services.data_permission_filter import DataPermissionFilter
from meta.core.datasource import get_data_source
from meta.core.models import registry
from meta.core.enrichment_engine import init_enrichment_engine, enrich_record, enrich_records
from meta.api.special_routes_api import _compute_category, list_relationships
import os
import logging

logger = logging.getLogger(__name__)

manage_bp = Blueprint('manage', __name__, url_prefix='/api/v1')

_data_source = None
_manage_service = None
_query_service = None
_audit_service = None
_hierarchy_filter_service = None
_data_perm_filter = None
AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'true').lower() in ('true', '1', 'yes')


def init_services(data_source=None):
    global _data_source, _manage_service, _query_service, _audit_service, _hierarchy_filter_service, _data_perm_filter
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    _manage_service = ManageService(_data_source)
    _query_service = QueryService(_data_source)
    _audit_service = AuditService(_data_source)
    _hierarchy_filter_service = HierarchyFilterService(_query_service, _data_source)
    _data_perm_filter = DataPermissionFilter(_data_source)
    
    from meta.core.redundancy_registry import redundancy_registry
    redundancy_registry.build_from_registry()
    init_enrichment_engine(_data_source)

    try:
        from meta.core.schema_generator import sync_schema_from_meta
        from meta.core.models import registry as meta_registry, FieldStorage
        meta_objects = [meta_registry.get(ot) for ot in meta_registry.list_types()]
        meta_objects = [obj for obj in meta_objects if obj is not None]
        sync_schema_from_meta(_data_source, meta_objects)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Schema sync skipped: %s", str(e))

    _ensure_default_permissions(_data_source)

    from meta.api.special_routes_api import init_special_services
    from meta.api.annotation_routes_api import init_annotation_services
    from meta.api.audit_management_api import init_audit_mgmt_services
    init_special_services(
        data_source=_data_source,
        hierarchy_filter_service=_hierarchy_filter_service,
        data_perm_filter=_data_perm_filter,
    )
    init_annotation_services(data_source=_data_source, manage_service=_manage_service)
    init_audit_mgmt_services(audit_service=_audit_service)


def _get_manage_service():
    if _manage_service is None:
        init_services()
    return _manage_service


def _get_query_service():
    if _query_service is None:
        init_services()
    return _query_service


def _get_audit_service():
    if _audit_service is None:
        init_services()
    return _audit_service


def _get_hierarchy_filter_service():
    if _hierarchy_filter_service is None:
        init_services()
    return _hierarchy_filter_service


def _set_audit_user():
    from urllib.parse import unquote
    service = _get_manage_service()

    current_user = getattr(g, 'current_user', None)

    if not current_user:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.replace('Bearer ', '')
            try:
                from meta.services.token_service import TokenService
                current_user = TokenService.verify_token(token)
            except Exception:
                pass

    current_user = current_user or {}
    user_id = current_user.get('user_id') or request.headers.get('X-User-Id')

    user_name_raw = (current_user.get('display_name')
                     or current_user.get('username')
                     or request.headers.get('X-User-Name', '')
                     or os.environ.get('AUDIT_DEFAULT_USER', ''))
    try:
        user_name = unquote(user_name_raw) if user_name_raw else ''
    except Exception:
        user_name = user_name_raw

    if not user_name:
        user_name = 'system'

    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) or request.headers.get('X-IP-Address', '')
    user_agent = request.headers.get('User-Agent', '')
    service.set_audit_user(user_id, user_name, ip_address, user_agent)

    agent_id = getattr(g, 'agent_id', None) or request.headers.get('X-Agent-Id')
    agent_session_id = getattr(g, 'agent_session_id', None) or request.headers.get('X-Agent-Session-Id')
    tool_call_id = getattr(g, 'tool_call_id', None) or request.headers.get('X-Tool-Call-Id')
    agent_reasoning = getattr(g, 'agent_reasoning', None) or request.headers.get('X-Agent-Reasoning')
    if any([agent_id, agent_session_id, tool_call_id]):
        service.set_agent_context(agent_id, agent_session_id, tool_call_id, agent_reasoning)


def _api_error(message, error_code='INTERNAL_ERROR', status_code=400, detail=None):
    response = {
        'success': False,
        'error_code': error_code,
        'message': message
    }
    if detail and os.environ.get('FLASK_DEBUG') == '1':
        response['detail'] = detail
    return jsonify(response), status_code


def _api_success(data=None, message='Success', **kwargs):
    response = {
        'success': True,
        'message': message
    }
    if data is not None:
        response['data'] = data
    response.update(kwargs)
    return jsonify(response)


def _get_page_params():
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('pageSize', request.args.get('page_size', 20, type=int), type=int)
    keyword = request.args.get('keyword', '')
    order_by = request.args.get('order_by', '') or request.args.get('sort_by', '')
    sort_order = request.args.get('sort_order', request.args.get('order', 'desc'))

    if order_by and sort_order:
        order_by = f"{order_by} {sort_order}"
    return page, page_size, keyword, order_by


def _auth_required(f):
    return login_required(f)


def _get_permission_code(object_type: str, action: str):
    meta_obj = registry.get(object_type)
    if meta_obj is None or meta_obj.authorization is None or meta_obj.authorization.get('check') is not True:
        return None
    return meta_obj.authorization.get('permissions', {}).get(action)


def _check_permission(object_type: str, action: str):
    perm_code = _get_permission_code(object_type, action)
    if perm_code is None:
        return True
    if not AUTH_ENABLED:
        return True
    user = get_current_user()
    if not user:
        return False
    user_permissions = user.get('permissions', [])
    if '*' in user_permissions:
        return True
    if perm_code in user_permissions:
        return True
    return False


def _apply_scope_filter(object_type: str, conditions):
    if not AUTH_ENABLED:
        return conditions
    meta_obj = registry.get(object_type)
    if meta_obj is None or meta_obj.authorization is None:
        return conditions
    scope_expr = meta_obj.authorization.get('scope')
    if not scope_expr:
        return conditions
    try:
        user = get_current_user()
    except RuntimeError:
        return conditions
    if not user or is_admin(user):
        return conditions

    # [FIX v3.18.1 2026-06-09] 优先应用 role_dimension_scope 派生条件
    #   与 DataPermissionInterceptor._apply_dimension_scope_filter 保持一致
    #   TEST60 配 version=[1,2,11,12] 时, 对 VERSION_AWARE_BOS (service_module/business_object/relationship)
    #   应使用 version_id IN (...) 而非 owner_id = $user.id
    user_id = user.get('user_id')
    try:
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        engine = DimensionScopeEngine(_data_source)
        # 查 user 的 role_ids
        cur = _data_source.execute(
            """SELECT DISTINCT gr.role_id
               FROM group_roles gr
               JOIN user_group_members ugm ON gr.group_id = ugm.group_id
               WHERE ugm.user_id = ?""",
            [user_id]
        )
        role_ids = [row[0] for row in cur.fetchall()]
        # 查 role 是否有 dimension scope
        if role_ids:
            placeholders = ','.join('?' * len(role_ids))
            cnt_cur = _data_source.execute(
                f"SELECT COUNT(*) FROM role_dimension_scopes WHERE role_id IN ({placeholders})",
                role_ids,
            )
            has_scope = cnt_cur.fetchone()[0] > 0
            if has_scope:
                # 收集所有 role 的条件 (跨 role OR, role 内 AND)
                from meta.services.query_service import QueryCondition
                or_group = []
                for rid in role_ids:
                    conds = engine.derive_data_conditions(rid)
                    expr = conds.get(object_type)
                    if not expr:
                        continue
                    # 解析表达式 (单段或 AND 复合)
                    import re
                    parts = re.split(r'\s+AND\s+', expr, flags=re.IGNORECASE)
                    for part in parts:
                        part = part.strip()
                        m_in = re.match(r'^(\w+)\s+IN\s*\(([^)]+)\)\s*$', part, re.IGNORECASE)
                        m_eq = re.match(r'^(\w+)\s*=\s*(\d+)\s*$', part)
                        if m_in:
                            field = m_in.group(1)
                            values = [int(x.strip()) for x in m_in.group(2).split(',') if x.strip()]
                            or_group.append(QueryCondition(field=field, operator='in', values=values, combine_mode='or'))
                        elif m_eq:
                            field = m_eq.group(1)
                            value = int(m_eq.group(2))
                            or_group.append(QueryCondition(field=field, operator='eq', value=value, combine_mode='or'))
                if or_group:
                    # [FIX v3.18.1] OR 关系: dim scope OR owner
                    # QueryService or_where 已修复, IN 算子能传 values list
                    conditions.extend(or_group)
                    # 加 owner 始终可见 (OR 关系)
                    conditions.append(QueryCondition(
                        field='owner_id', operator='eq', value=user_id, combine_mode='or'
                    ))
                    return conditions
    except Exception as e:
        logger.warning(f"[_apply_scope_filter v3.18.1] dimension scope check failed: {e}")

    allowed_ids = _data_perm_filter.perm_service.get_allowed_resource_ids(user.get('user_id'), object_type)
    if allowed_ids:
        return conditions

    from meta.services.query_service import QueryCondition
    resolved = scope_expr
    resolved = resolved.replace('$user.id', str(user.get('user_id', '')))
    resolved = resolved.replace('$user.username', str(user.get('username', '')))
    
    try:
        parsed = _parse_scope_expression(resolved)
        for cond_item in parsed:
            if isinstance(cond_item, list):
                or_group = cond_item
                for c in or_group:
                    c['combine_mode'] = 'or'
                    conditions.append(QueryCondition(
                        field=c['field'], operator=c['operator'], value=c['value'],
                        combine_mode='or'
                    ))
            else:
                conditions.append(QueryCondition(
                    field=cond_item['field'], operator=cond_item['operator'],
                    value=cond_item['value']
                ))
    except Exception:
        parts = resolved.split('=', 1)
        if len(parts) == 2:
            field = parts[0].strip()
            value = parts[1].strip()
            conditions.append(QueryCondition(field=field, operator='eq', value=value))
    
    return conditions


def _parse_scope_expression(expr: str):
    import re
    
    or_parts = re.split(r'\s+OR\s+', expr, flags=re.IGNORECASE)
    if len(or_parts) > 1:
        or_group = []
        for part in or_parts:
            or_group.append(_parse_simple_condition(part.strip()))
        return [or_group]
    
    return [_parse_simple_condition(expr.strip())]


def _parse_simple_condition(expr: str):
    expr = expr.strip()
    for op_char, op_name in [('!=', 'ne'), ('>=', 'ge'), ('<=', 'le'), ('>', 'gt'), ('<', 'lt'), ('=', 'eq')]:
        if op_char in expr:
            parts = expr.split(op_char, 1)
            field = parts[0].strip()
            value = parts[1].strip()
            if (value.startswith("'") and value.endswith("'")) or \
               (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]
            return {'field': field, 'operator': op_name, 'value': value}
    return {'field': expr, 'operator': 'eq', 'value': True}


def _apply_data_permission_filter(object_type, conditions):
    if not AUTH_ENABLED:
        return conditions
    user = get_current_user()
    if not user:
        return conditions
    if is_admin(user):
        return conditions
    return _data_perm_filter.apply_filter(object_type, user.get('user_id'), conditions)


@manage_bp.route('/<object_type>', methods=['POST'])
@_auth_required
def create_record(object_type):
    if not _check_permission(object_type, "create"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "create")}', 'code': 'FORBIDDEN'}), 403
    _set_audit_user()
    data = request.get_json(silent=True) or {}
    
    ARCH_TYPES = set(HierarchyConfigLoader.get_type_order())
    
    if object_type in ARCH_TYPES and AUTH_ENABLED:
        user = get_current_user()
        if user:
            data['owner_id'] = user.get('user_id')
    
    if object_type == 'version' and data.get('is_current'):
        product_id = data.get('product_id')
        if product_id:
            existing = _data_source.execute(
                "SELECT id FROM versions WHERE product_id = ? AND is_current = 1",
                (product_id,)
            ).fetchone()
            if existing:
                return jsonify({
                    'success': False,
                    'message': '每个产品只能有一个当前版本，请先将其他版本设为非当前版本',
                }), 400
    
    skip_validation = data.pop('_skip_validation', False)
    skip_audit = data.pop('_skip_audit', False)
    req = CreateRequest(
        object_type=object_type,
        data=data,
        skip_validation=skip_validation,
        skip_audit=skip_audit,
    )
    result = _get_manage_service().create(req)
    
    if result.success and object_type in ARCH_TYPES and AUTH_ENABLED:
        user = get_current_user()
        if user and result.data and result.data.get('id'):
            from meta.services.data_permission_service import DataPermissionService
            ds = _get_data_source() if _data_source else get_data_source("sqlite", database=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db'))
            perm_service = DataPermissionService(ds)
            perm_service.add_data_permission(
                user_id=user.get('user_id'),
                resource_type=object_type,
                resource_id=result.data['id'],
                permission_level='admin',
                inherit_to_children=True
            )
    
    return jsonify({
        'success': result.success,
        'data': result.data,
        'message': result.message,
    }), 201 if result.success else 400


@manage_bp.route('/<object_type>/deep', methods=['POST'])
@_auth_required
def deep_insert(object_type):
    """Deep Insert - 一次请求创建/更新父对象和子对象
    
    请求体格式：
    {
        "parent": { ... 父对象数据（含 id 则更新） ... },
        "children": {
            "sub_domain": [ ... 子对象列表（含 id 则更新） ... ],
            "another_child_type": [ ... ]
        },
        "options": {
            "transaction_mode": "all_or_nothing",  // 或 "independent"
        }
    }
    
    或简化格式：
    {
        ... 父对象数据 ...,
        "_children": {
            "sub_domain": [ ... ]
        }
    }
    """
    if not _check_permission(object_type, "create"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "create")}', 'code': 'FORBIDDEN'}), 403
    
    _set_audit_user()
    body = request.get_json(silent=True) or {}
    
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404
    
    from meta.core.deep_insert_engine import DeepInsertEngine
    engine = DeepInsertEngine()
    result = engine.execute(object_type, body, _get_data_source())
    
    if result.success:
        return jsonify({
            'success': True,
            'data': result.data,
            'message': result.message,
        }), 201
    else:
        status_code = 400
        if result.data and result.data.get('rolled_back'):
            status_code = 409
        return jsonify({
            'success': False,
            'message': result.message,
            'error_code': 'TRANSACTION_ROLLBACK' if (result.data and result.data.get('rolled_back')) else 'DEEP_INSERT_FAILED',
            'data': result.data,
            'errors': result.errors,
        }), status_code


@manage_bp.route('/<object_type>/<id>', methods=['GET'])
@_auth_required
def get_record(object_type, id):
    if not _check_permission(object_type, "read"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "read")}', 'code': 'FORBIDDEN'}), 403
    conditions = [
        QueryCondition(field='id', operator='eq', value=int(id) if str(id).isdigit() else id)
    ]
    conditions = _apply_scope_filter(object_type, conditions)
    search_req = SearchRequest(
        object_type=object_type,
        conditions=conditions,
        page=1,
        page_size=1,
    )
    result = _get_query_service().search(search_req)
    if result.data:
        record = result.data[0]
        record['type'] = object_type
        record = enrich_record(object_type, record)

        # 填充 FK display names（与 _do_list 保持一致）
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        from meta.core.datasource import get_data_source
        pi = PersistenceInterceptor()
        meta_obj = registry.get(object_type)
        if meta_obj:
            ds = get_data_source()
            record = pi._enrich_fk_display_names(meta_obj, record, ds)

        record['can_delete'] = _get_manage_service().check_can_delete(object_type, record)
        try:
            audit_service = _get_audit_service()
            change_history = audit_service.get_object_history(
                object_type, record.get('id'), include_children=True
            )
            record['change_history'] = change_history
        except Exception as e:
            record['change_history'] = []
        return jsonify({'success': True, 'data': record})
    return jsonify({'success': False, 'data': None, 'message': 'Not found'}), 404


def _batch_load_names(table, ids, ds):
    if not ids:
        return {}
    id_list = list(set(i for i in ids if i is not None))
    if not id_list:
        return {}
    placeholders = ','.join(['?'] * len(id_list))
    sql = f"SELECT id, name FROM {table} WHERE id IN ({placeholders})"
    cursor = ds.execute(sql, tuple(id_list))
    return {row[0]: row[1] for row in cursor.fetchall()}


def _batch_get_single_records(table, ids, ds):
    if not ids:
        return {}
    id_list = list(set(i for i in ids if i is not None))
    if not id_list:
        return {}
    placeholders = ','.join(['?'] * len(id_list))
    sql = f"SELECT * FROM {table} WHERE id IN ({placeholders})"
    cursor = ds.execute(sql, tuple(id_list))
    columns = [desc[0] for desc in cursor.description]
    return {row[0]: dict(zip(columns, row)) for row in cursor.fetchall()}


def _get_single_record(table_name, record_id):
    if _data_source is None:
        init_services()
    ds = _data_source
    if not ds:
        return None
    try:
        sql = f"SELECT * FROM {table_name} WHERE id = ?"
        cursor = ds.execute(sql, (record_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
    except Exception as e:
        logger.warning("Failed to get record from %s id=%s: %s", table_name, record_id, str(e))
    return None


@manage_bp.route('/<object_type>', methods=['GET'])
@_auth_required
def list_records(object_type):
    if not _check_permission(object_type, "read"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "read")}', 'code': 'FORBIDDEN'}), 403
    if object_type == 'relationship':
        return list_relationships()

    page, page_size, keyword, order_by = _get_page_params()

    from flask import request
    args_dict = {}
    for key in request.args.keys():
        args_dict[key] = request.args.getlist(key)
    conditions = _get_hierarchy_filter_service().resolve_conditions(object_type, args_dict)
    
    conditions = _apply_scope_filter(object_type, conditions)

    # 提取 filter_params（用于跨表过滤等高级过滤）
    reserved_params = {'page', 'page_size', 'keyword', 'order_by', 'orderBy', 'sort_by', 'sort_order'}
    filter_params = {}
    for key, values in args_dict.items():
        if key not in reserved_params:
            if len(values) == 1:
                filter_params[key] = values[0]
            else:
                filter_params[key] = values
    from meta.services.hierarchy_filter_service import _normalize_object_type
    normalized_type = _normalize_object_type(object_type)

    search_req = SearchRequest(
        object_type=normalized_type,
        conditions=conditions,
        keyword=keyword,
        order_by=order_by,
        page=page,
        page_size=page_size,
        filter_params=filter_params,  # 添加 filter_params 支持跨表过滤
    )
    result = _get_query_service().search(search_req)
    for i, item in enumerate(result.data):
        item['type'] = object_type
    result.data = enrich_records(normalized_type, result.data)

    from meta.services.computation_service import computation_service
    computation_service.compute_by_semantics(normalized_type, result.data, _data_source)
    from meta.core.models import registry as meta_registry, FieldStorage
    meta_obj = meta_registry.get(normalized_type)
    if meta_obj:
        list_config = None
        if hasattr(meta_obj, 'ui_view_config') and meta_obj.ui_view_config:
            list_config = getattr(meta_obj.ui_view_config, 'list', None)
        
        ui_computed_columns = []
        if list_config and hasattr(list_config, 'columns'):
            ui_computed_columns = [
                {'key': col.key, 'computation': getattr(col, 'computation', None)}
                for col in list_config.columns
                if getattr(col, 'computed', False) and getattr(col, 'computation', None)
            ]
        
        field_computed_columns = []
        for field in meta_obj.fields:
            storage = getattr(field, 'storage', None)
            computation = getattr(field, 'computation', None)
            if storage == FieldStorage.VIRTUAL and computation:
                if computation.get('formula') or computation.get('type'):
                    field_computed_columns.append({
                        'key': field.id,
                        'computation': computation
                    })
        
        rule_computed_columns = computation_service.get_computed_columns_from_rules(normalized_type)
        computed_columns = computation_service.merge_computed_columns(
            ui_computed_columns, 
            computation_service.merge_computed_columns(field_computed_columns, rule_computed_columns)
        )

        if computed_columns:
            computation_service.compute_batch(_data_source, object_type, result.data, computed_columns)

    if meta_obj and meta_obj.deletability:
        for item in result.data:
            item['can_delete'] = _get_manage_service().check_can_delete(normalized_type, item)

    return jsonify({
        'success': True,
        'data': result.data,
        'total': result.total,
        'page': result.page,
        'page_size': result.page_size,
    })


@manage_bp.route('/<object_type>/list', methods=['POST'])
@_auth_required
def list_records_post(object_type):
    """POST 方式的列表查询，用于参数过多导致 URL 过长的情况"""
    if not _check_permission(object_type, "read"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "read")}', 'code': 'FORBIDDEN'}), 403
    if object_type == 'relationship':
        return list_relationships()

    data = request.get_json() or {}
    page = data.get('page', 1)
    page_size = data.get('pageSize', data.get('page_size', 20))
    keyword = (data.get('keyword') or '').strip()
    order_by = data.get('order_by', data.get('orderBy', '-created_at'))
    filter_params = data.get('filter_params', {})
    filter_scope = data.get('filter_scope', 'global')
    
    # 将非保留参数也添加到 filter_params（支持跨表过滤）
    reserved_keys = ('page', 'pageSize', 'page_size', 'keyword', 'order_by', 'orderBy', 'sort_by', 'sort_order', 'filter_params', 'filter_scope')
    args_dict = {}
    for key, value in data.items():
        if key not in reserved_keys:
            if isinstance(value, list):
                args_dict[key] = value
            else:
                args_dict[key] = [value]
            # 也添加到 filter_params 用于跨表过滤
            if key not in filter_params:
                filter_params[key] = value if not isinstance(value, list) else value[0] if value else None
    
    sort_by = data.get('sort_by')
    sort_order = data.get('sort_order', 'desc')
    if sort_by:
        order_by = f"{'-' if sort_order == 'desc' else ''}{sort_by}"

    conditions = _get_hierarchy_filter_service().resolve_conditions(object_type, args_dict)
    conditions = _apply_scope_filter(object_type, conditions)

    from meta.services.hierarchy_filter_service import _normalize_object_type
    normalized_type = _normalize_object_type(object_type)

    search_req = SearchRequest(
        object_type=normalized_type,
        conditions=conditions,
        keyword=keyword,
        order_by=order_by,
        page=page,
        page_size=page_size,
        filter_params=filter_params,
        filter_scope=filter_scope,
    )
    result = _get_query_service().search(search_req)
    for i, item in enumerate(result.data):
        item['type'] = object_type
    result.data = enrich_records(normalized_type, result.data)

    from meta.services.computation_service import computation_service
    computation_service.compute_by_semantics(normalized_type, result.data, _data_source)

    from meta.core.models import registry as meta_registry, FieldStorage
    meta_obj = meta_registry.get(normalized_type)
    if meta_obj:
        list_config = None
        if hasattr(meta_obj, 'ui_view_config') and meta_obj.ui_view_config:
            list_config = getattr(meta_obj.ui_view_config, 'list', None)

        ui_computed_columns = []
        if list_config and hasattr(list_config, 'columns'):
            ui_computed_columns = [
                {'key': col.key, 'computation': getattr(col, 'computation', None)}
                for col in list_config.columns
                if getattr(col, 'computed', False) and getattr(col, 'computation', None)
            ]

        field_computed_columns = []
        for field in meta_obj.fields:
            storage = getattr(field, 'storage', None)
            computation_attr = getattr(field, 'computation', None)
            if storage == FieldStorage.VIRTUAL and computation_attr:
                if computation_attr.get('formula') or computation_attr.get('type'):
                    field_computed_columns.append({
                        'key': field.id,
                        'computation': computation_attr
                    })

        rule_computed_columns = computation_service.get_computed_columns_from_rules(normalized_type)
        computed_columns = computation_service.merge_computed_columns(
            ui_computed_columns,
            computation_service.merge_computed_columns(field_computed_columns, rule_computed_columns)
        )

        if computed_columns:
            computation_service.compute_batch(_data_source, object_type, result.data, computed_columns)

    if meta_obj and meta_obj.deletability:
        for item in result.data:
            item['can_delete'] = _get_manage_service().check_can_delete(normalized_type, item)

    return jsonify({
        'success': True,
        'data': result.data,
        'total': result.total,
        'page': result.page,
        'page_size': result.page_size,
    })


@manage_bp.route('/<object_type>/<id>', methods=['PUT'])
@_auth_required
def update_record(object_type, id):
    if not _check_permission(object_type, "update"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "update")}', 'code': 'FORBIDDEN'}), 403
    _set_audit_user()
    data = request.get_json(silent=True) or {}
    
    if object_type == 'version' and data.get('is_current'):
        product_id = data.get('product_id')
        if product_id:
            existing = _data_source.execute(
                "SELECT id FROM versions WHERE product_id = ? AND is_current = 1 AND id != ?",
                (product_id, id)
            ).fetchone()
            if existing:
                return jsonify({
                    'success': False,
                    'message': '每个产品只能有一个当前版本，请先将其他版本设为非当前版本',
                }), 400
    
    from meta.services.hierarchy_validation_service import validate_update
    meta_obj = registry.get(object_type)
    if meta_obj:
        table_name = meta_obj.table_name
        original_data = _data_source.find_by_id(table_name, id)
        if original_data:
            validation_result = validate_update(object_type, original_data, data, _data_source)
            if not validation_result.valid:
                return jsonify({
                    'success': False,
                    'message': validation_result.message,
                    'error_code': validation_result.error_code,
                    'details': validation_result.details,
                }), 400
    
    skip_validation = data.pop('_skip_validation', False)
    skip_audit = data.pop('_skip_audit', False)
    req = UpdateRequest(
        object_type=object_type,
        id=id,
        data=data,
        skip_validation=skip_validation,
        skip_audit=skip_audit,
    )
    result = _get_manage_service().update(req)
    return jsonify({
        'success': result.success,
        'data': result.data,
        'message': result.message,
    }), 200 if result.success else 400


@manage_bp.route('/<object_type>/<id>', methods=['DELETE'])
@_auth_required
def delete_record(object_type, id):
    if not _check_permission(object_type, "delete"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "delete")}', 'code': 'FORBIDDEN'}), 403
    _set_audit_user()
    force = request.args.get('force', 'false').lower() in ('true', '1', 'yes')
    cascade = request.args.get('cascade', 'false').lower() in ('true', '1', 'yes')
    
    if not force:
        from meta.services.hierarchy_validation_service import validate_delete
        validation_result = validate_delete(object_type, id, _data_source)
        if not validation_result.valid:
            return jsonify({
                'success': False,
                'message': validation_result.message,
                'error_code': validation_result.error_code,
                'details': validation_result.details,
            }), 400
    
    delete_annotations_by_target(object_type, id)
    
    req = DeleteRequest(
        object_type=object_type,
        id=id,
        force=force,
        cascade=cascade,
    )
    result = _get_manage_service().delete(req)
    return jsonify({
        'success': result.success,
        'message': result.message,
    }), 200 if result.success else 400


@manage_bp.route('/<object_type>/<id>/recover', methods=['POST'])
@_auth_required
def recover_from_log(object_type, id):
    """从 audit_log 恢复已删除的记录"""
    if not _check_permission(object_type, "update"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "update")}', 'code': 'FORBIDDEN'}), 403
    
    _set_audit_user()
    
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404
    
    try:
        object_id = int(id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid id'}), 400
    
    existing = _data_source.find_by_id(meta_obj.table_name, object_id)
    if existing:
        return jsonify({'success': False, 'message': '记录已存在，无需恢复'}), 400
    
    old_data = None
    try:
        cursor = _data_source.execute(
            "SELECT old_data FROM change_event WHERE object_type = ? AND object_id = ? AND event_type = 'delete' ORDER BY created_at DESC LIMIT 1",
            [object_type, object_id]
        )
        row = cursor.fetchone()
        if row:
            raw = row[0] if not isinstance(row, dict) else row.get('old_data')
            if isinstance(raw, str):
                import json
                old_data = json.loads(raw)
            else:
                old_data = raw
    except Exception as e:
        logger.warning(f"[Recover] Failed to query change_event: {e}")
    
    if not old_data:
        try:
            cursor = _data_source.execute(
                "SELECT extra_data FROM audit_log WHERE object_type = ? AND object_id = ? AND action = 'DELETE' ORDER BY created_at DESC LIMIT 1",
                [object_type, object_id]
            )
            row = cursor.fetchone()
            if row:
                raw = row[0] if not isinstance(row, dict) else row.get('extra_data')
                if isinstance(raw, str):
                    import json
                    extra = json.loads(raw)
                    old_data = extra.get('old_data') if isinstance(extra, dict) else None
                elif isinstance(raw, dict):
                    old_data = raw.get('old_data')
        except Exception as e:
            logger.warning(f"[Recover] Failed to query audit_log: {e}")
    
    if not old_data:
        return jsonify({'success': False, 'message': '未找到删除记录，可能已被审计日志清理'}), 404
    
    clean_data = {k: v for k, v in old_data.items() if k != 'id'}
    clean_data['id'] = object_id
    
    try:
        _data_source.insert(meta_obj.table_name, clean_data)
    except Exception as e:
        return jsonify({'success': False, 'message': f'恢复失败: {str(e)}'}), 500
    
    return jsonify({
        'success': True,
        'message': f'已从审计日志恢复 {object_type}#{object_id}',
        'data': clean_data,
    })


@manage_bp.route('/<object_type>/deleted', methods=['GET'])
@_auth_required
def list_deleted_objects(object_type):
    """从 audit_log 查询已删除对象列表"""
    if not _check_permission(object_type, "read"):
        return jsonify({'error': f'需要权限: {_get_permission_code(object_type, "read")}', 'code': 'FORBIDDEN'}), 403
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    deleted_by = request.args.get('deleted_by')
    deleted_after = request.args.get('deleted_after')
    deleted_before = request.args.get('deleted_before')
    
    conditions = ["object_type = ?", "action = 'DELETE'"]
    params = [object_type]
    
    if deleted_by:
        conditions.append("user_id = ?")
        params.append(int(deleted_by))
    if deleted_after:
        conditions.append("created_at >= ?")
        params.append(deleted_after)
    if deleted_before:
        conditions.append("created_at <= ?")
        params.append(deleted_before)
    
    where = " AND ".join(conditions)
    
    from datetime import datetime
    
    try:
        cursor = _data_source.execute(
            f"SELECT COUNT(DISTINCT object_id) as cnt FROM audit_log WHERE {where}",
            params
        )
        row = cursor.fetchone()
        total = row[0] if isinstance(row, tuple) else row['cnt']
    except Exception:
        total = 0
    
    offset = (page - 1) * per_page
    items = []
    try:
        cursor = _data_source.execute(
            f"""SELECT object_id, MAX(created_at) as deleted_at, 
                      MAX(user_id) as user_id
               FROM audit_log
               WHERE {where}
               GROUP BY object_id
               ORDER BY deleted_at DESC
               LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        )
        rows = cursor.fetchall()
        for row in rows:
            if isinstance(row, dict):
                oid = row['object_id']
                deleted_at = row['deleted_at']
                deleted_by_id = row['user_id']
            else:
                oid = row[0]
                deleted_at = row[1]
                deleted_by_id = row[2]
            
            deleted_by_name = ""
            if deleted_by_id:
                try:
                    user_record = _data_source.find_by_id('users', int(deleted_by_id))
                    if user_record:
                        deleted_by_name = user_record.get('name', user_record.get('username', ''))
                except Exception:
                    pass
            
            items.append({
                'object_id': oid,
                'object_type': object_type,
                'deleted_at': str(deleted_at) if deleted_at else '',
                'deleted_by': deleted_by_id,
                'deleted_by_name': deleted_by_name,
                'recoverable': True,
            })
    except Exception as e:
        logger.warning(f"[Deleted] Failed to query: {e}")
    
    return jsonify({
        'success': True,
        'data': {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
        }
    })


@manage_bp.route('/<object_type>/batch-create', methods=['POST'])
@_auth_required
def batch_create(object_type):
    _set_audit_user()
    body = request.get_json(silent=True) or {}
    data_list = body.get('data_list', [])
    skip_validation = body.get('skip_validation', False)
    result = _get_manage_service().batch_create(object_type, data_list, skip_validation)
    return jsonify({
        'success': result.failed_count == 0,
        'success_count': result.success_count,
        'failed_count': result.failed_count,
        'results': [r.to_dict() if hasattr(r, 'to_dict') else {'success': r.success, 'data': r.data, 'message': r.message, 'error': r.error} for r in result.results],
        'errors': result.errors,
    }), 200 if result.failed_count == 0 else 207


@manage_bp.route('/<object_type>/batch-update', methods=['POST'])
@_auth_required
def batch_update(object_type):
    _set_audit_user()
    body = request.get_json(silent=True) or {}
    updates = body.get('updates', [])
    skip_validation = body.get('skip_validation', False)
    result = _get_manage_service().batch_update(object_type, updates, skip_validation)
    return jsonify({
        'success': result.failed_count == 0,
        'success_count': result.success_count,
        'failed_count': result.failed_count,
        'results': [r.to_dict() if hasattr(r, 'to_dict') else {'success': r.success, 'data': r.data, 'message': r.message, 'error': r.error} for r in result.results],
        'errors': result.errors,
    }), 200 if result.failed_count == 0 else 207


@manage_bp.route('/<object_type>/batch-delete', methods=['POST'])
@_auth_required
def batch_delete(object_type):
    _set_audit_user()
    body = request.get_json(silent=True) or {}
    ids = body.get('ids', [])
    force = body.get('force', False)
    result = _get_manage_service().batch_delete(object_type, ids, force)
    return jsonify({
        'success': result.failed_count == 0,
        'success_count': result.success_count,
        'failed_count': result.failed_count,
        'results': [r.to_dict() if hasattr(r, 'to_dict') else {'success': r.success, 'data': r.data, 'message': r.message, 'error': r.error} for r in result.results],
        'errors': result.errors,
    }), 200 if result.failed_count == 0 else 207
def _ensure_default_permissions(ds):
    DEFAULT_PERMISSIONS = [
        ('product', '产品'),
        ('version', '版本'),
        ('domain', '领域'),
        ('sub_domain', '子领域'),
        ('service_module', '服务模块'),
        ('business_object', '业务对象'),
        ('relationship', '关系'),
        ('annotation', '备注'),
    ]
    ACTIONS = ['create', 'read', 'update', 'delete', 'export']
    
    existing = set()
    cursor = ds.execute("SELECT code FROM permissions")
    for row in cursor.fetchall():
        existing.add(row[0])
    
    count = 0
    for resource_type, label in DEFAULT_PERMISSIONS:
        for action in ACTIONS:
            code = f"{resource_type}:{action}"
            if code not in existing:
                name = f"{label}{action}"
                ds.execute(
                    "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) VALUES (?, ?, ?, ?)",
                    [code, name, resource_type, action]
                )
                count += 1
    
    if count > 0:
        logger.info("[Init] Seeded %d default permissions", count)
def delete_annotations_by_target(target_type, target_id):
    """删除关联对象的所有备注（级联删除）"""
    if _data_source is None:
        init_services()
    ds = _data_source
    
    sql = "DELETE FROM annotations WHERE target_type = ? AND target_id = ?"
    with ds.transaction():
        ds.execute(sql, (target_type, target_id))
@manage_bp.route('/<object_type>/<id>/actions', methods=['GET'])
@_auth_required
def list_actions(object_type, id):
    """获取对象可执行的 Action 列表"""
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404

    record = None
    try:
        record = _data_source.find_by_id(meta_obj.table_name, id)
    except Exception:
        pass

    if not record:
        return jsonify({'success': False, 'message': 'Record not found'}), 404

    from meta.core.condition_evaluator import ConditionEvaluator
    evaluator = ConditionEvaluator()

    actions = []
    for action in meta_obj.actions:
        action_info = {
            'id': action.id,
            'name': action.name,
            'type': action.action_type.value,
            'method': action.method,
            'path': action.path,
            'description': action.description,
            'available': True,
        }

        if action.behavior and action.behavior.precondition:
            context = {"self": record, "parameters": {}}
            can_execute = evaluator.evaluate(
                action.behavior.precondition.condition,
                context=context,
            )
            action_info['available'] = can_execute
            if not can_execute:
                action_info['unavailable_reason'] = action.behavior.precondition.message

        actions.append(action_info)

    can_delete = _get_manage_service().check_can_delete(object_type, record)

    return jsonify({
        'success': True,
        'data': {
            'actions': actions,
            'can_delete': can_delete,
        },
    })


@manage_bp.route('/<object_type>/<id>/actions/<action_id>', methods=['POST'])
@_auth_required
def execute_action(object_type, id, action_id):
    """执行自定义 Action"""
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404

    action = meta_obj.get_action(action_id)
    if not action:
        return jsonify({'success': False, 'message': f'Action not found: {action_id}'}), 404

    _set_audit_user()
    body = request.get_json(silent=True) or {}
    params = dict(body)
    params['id'] = int(id) if str(id).isdigit() else id

    result = _get_manage_service().executor.execute(meta_obj, action_id, params)

    return jsonify({
        'success': result.success,
        'data': result.data,
        'message': result.message,
        'error': result.error,
    }), 200 if result.success else 400






@manage_bp.route('/<object_type>/<id>/state_transitions', methods=['GET'])
@_auth_required
def get_state_transitions(object_type, id):
    """获取当前可用的状态转换规则"""
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404
    
    try:
        object_id = int(id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid id'}), 400
    
    record = _data_source.find_by_id(meta_obj.table_name, object_id)
    if not record:
        return jsonify({'success': False, 'message': 'Record not found'}), 404
    
    state_transitions = []
    for rule in meta_obj.rules:
        if not hasattr(rule, 'state_field'):
            continue
        if not hasattr(rule, 'from_states') or not hasattr(rule, 'to_state'):
            continue
        
        current_state = record.get(rule.state_field)
        is_available = current_state in rule.from_states
        
        ui_hints = getattr(rule, 'ui_hints', None)
        
        transition_info = {
            'id': rule.id,
            'name': rule.name,
            'state_field': rule.state_field,
            'from_states': list(rule.from_states),
            'to_state': rule.to_state,
            'current_state': current_state,
            'available': is_available,
            'label': ui_hints.label if ui_hints else rule.name,
            'icon': ui_hints.icon if ui_hints else '',
            'confirm_message': ui_hints.confirm_message if ui_hints else '',
            'highlight': ui_hints.highlight if ui_hints else False,
            'hidden': ui_hints.hidden if ui_hints else False,
        }
        
        if rule.condition:
            transition_info['condition'] = rule.condition
        
        if not transition_info['hidden']:
            state_transitions.append(transition_info)
    
    return jsonify({
        'success': True,
        'data': state_transitions,
    })


@manage_bp.route('/<object_type>/<id>/state_history', methods=['GET'])
@_auth_required
def get_state_history(object_type, id):
    """获取状态转换历史（基于 audit_log）"""
    from datetime import datetime
    
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404
    
    field = request.args.get('field', 'status')
    
    try:
        object_id = int(id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid id'}), 400
    
    sql = """
        SELECT id, old_value, new_value, user_name, created_at, action
        FROM audit_logs
        WHERE object_type = ? AND object_id = ? AND field_name = ?
        ORDER BY created_at ASC
    """
    
    cursor = _data_source.execute(sql, (object_type, object_id, field))
    logs = cursor.fetchall()
    
    field_meta = None
    for f in meta_obj.fields:
        if f.id == field:
            field_meta = f
            break
    
    enum_values = {}
    if field_meta and field_meta.enum_values:
        for ev in field_meta.enum_values:
            enum_values[ev.get('value')] = ev
    
    result = []
    for i, log in enumerate(logs):
        record = {
            'id': log[0],
            'from_state': log[1],
            'to_state': log[2],
            'operator_name': log[3],
            'created_at': log[4],
            'action': log[5],
        }
        
        from_ev = enum_values.get(log[1], {})
        to_ev = enum_values.get(log[2], {})
        record['from_state_label'] = from_ev.get('label', log[1])
        record['to_state_label'] = to_ev.get('label', log[2])
        record['from_state_color'] = from_ev.get('color')
        record['to_state_color'] = to_ev.get('color')
        record['from_state_icon'] = from_ev.get('icon')
        record['to_state_icon'] = to_ev.get('icon')
        
        if i > 0:
            prev_created_at = logs[i - 1][4]
            try:
                if isinstance(prev_created_at, str):
                    prev_dt = datetime.strptime(prev_created_at, '%Y-%m-%d %H:%M:%S')
                else:
                    prev_dt = prev_created_at
                if isinstance(log[4], str):
                    curr_dt = datetime.strptime(log[4], '%Y-%m-%d %H:%M:%S')
                else:
                    curr_dt = log[4]
                duration_seconds = (curr_dt - prev_dt).total_seconds()
                record['duration_in_prev_state'] = round(duration_seconds / 86400, 2)
            except Exception:
                pass
        
        result.append(record)
    
    return jsonify({'success': True, 'data': result})


@manage_bp.route('/<object_type>/<id>/stage_metrics', methods=['GET'])
@_auth_required
def get_stage_metrics(object_type, id):
    """获取状态停留统计（基于 audit_log）"""
    from datetime import datetime
    
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404
    
    field = request.args.get('field', 'status')
    
    try:
        object_id = int(id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid id'}), 400
    
    record = _data_source.find_by_id(meta_obj.table_name, object_id)
    if not record:
        return jsonify({'success': False, 'message': 'Record not found'}), 404
    
    current_state = record.get(field)
    # [FIX 2026-06-09] 不再从 record.get(f'{field}_entered_at') 读, 改为从 audit_logs 派生
    # 原因: status_entered_at DB 字段已删除 (冗余且被 state_transition 规则反复覆盖),
    # 单一事实源改为 audit_logs 表 (最近一次 field 变化时间)
    sql_entered_at = """
        SELECT created_at FROM audit_logs
        WHERE object_type = ? AND object_id = ? AND field_name = ? AND action = 'UPDATE'
        ORDER BY created_at DESC LIMIT 1
    """
    cursor_entered = _data_source.execute(sql_entered_at, (object_type, object_id, field))
    row_entered = cursor_entered.fetchone()
    current_state_entered_at = row_entered[0] if row_entered else None
    
    field_meta = None
    for f in meta_obj.fields:
        if f.id == field:
            field_meta = f
            break
    
    enum_values = {}
    if field_meta and field_meta.enum_values:
        for ev in field_meta.enum_values:
            enum_values[ev.get('value')] = ev
    
    current_ev = enum_values.get(current_state, {})
    current_state_label = current_ev.get('label', current_state)
    
    current_duration_days = 0
    if current_state_entered_at:
        try:
            if isinstance(current_state_entered_at, str):
                entered_dt = datetime.strptime(current_state_entered_at, '%Y-%m-%d %H:%M:%S')
            else:
                entered_dt = current_state_entered_at
            current_duration_days = round((datetime.now() - entered_dt).total_seconds() / 86400, 2)
        except Exception:
            pass
    
    sql = """
        SELECT old_value, new_value, created_at
        FROM audit_logs
        WHERE object_type = ? AND object_id = ? AND field_name = ?
        ORDER BY created_at ASC
    """
    
    cursor = _data_source.execute(sql, (object_type, object_id, field))
    logs = cursor.fetchall()
    
    stage_breakdown = {}
    total_days = 0
    
    for i, log in enumerate(logs):
        from_state = log[0]
        to_state = log[1]
        created_at = log[2]
        
        if i > 0:
            prev_created_at = logs[i - 1][2]
            try:
                if isinstance(prev_created_at, str):
                    prev_dt = datetime.strptime(prev_created_at, '%Y-%m-%d %H:%M:%S')
                else:
                    prev_dt = prev_created_at
                if isinstance(created_at, str):
                    curr_dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                else:
                    curr_dt = created_at
                duration = round((curr_dt - prev_dt).total_seconds() / 86400, 2)
                
                if from_state:
                    if from_state not in stage_breakdown:
                        ev = enum_values.get(from_state, {})
                        stage_breakdown[from_state] = {
                            'state': from_state,
                            'label': ev.get('label', from_state),
                            'duration_days': 0,
                        }
                    stage_breakdown[from_state]['duration_days'] += duration
                    total_days += duration
            except Exception:
                pass
    
    total_days += current_duration_days
    if current_state:
        if current_state not in stage_breakdown:
            ev = enum_values.get(current_state, {})
            stage_breakdown[current_state] = {
                'state': current_state,
                'label': ev.get('label', current_state),
                'duration_days': 0,
            }
        stage_breakdown[current_state]['duration_days'] += current_duration_days
    
    stage_list = list(stage_breakdown.values())
    for stage in stage_list:
        if total_days > 0:
            stage['percentage'] = round(stage['duration_days'] / total_days * 100, 1)
        else:
            stage['percentage'] = 0
    
    return jsonify({
        'success': True,
        'data': {
            'current_state': current_state,
            'current_state_label': current_state_label,
            'current_state_entered_at': str(current_state_entered_at) if current_state_entered_at else None,
            'current_state_duration_days': current_duration_days,
            'total_lifecycle_days': round(total_days, 2),
            'stage_breakdown': stage_list,
        },
    })
