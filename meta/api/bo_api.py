# -*- coding: utf-8 -*-
import logging
import os
from flask import Blueprint, request, jsonify, g

from meta.core.bo_framework import bo_framework
from meta.core.models import registry
from meta.services.auth_middleware import login_required, get_current_user
from meta.services.field_policy_engine import FieldPolicyEngine, PolicyContext, ObjectContext
from meta.services.view_config_service import view_config_service
from meta.services.computation_service import computation_service

logger = logging.getLogger(__name__)

bo_bp = Blueprint('bo_v2', __name__, url_prefix='/api/v2/bo')
meta_v2_bp = Blueprint('meta_v2', __name__, url_prefix='/api/v2/meta')


def _set_user_context():
    try:
        current_user = get_current_user()
        if current_user:
            bo_framework.set_user_context(
                user_id=current_user.get('user_id') or current_user.get('id'),
                user_name=current_user.get('username') or current_user.get('display_name'),
                ip_address=request.remote_addr,
            )
    except Exception:
        pass


def _get_bo():
    _set_user_context()
    return bo_framework


_data_source = None


# 关联查询保留参数（这些 key 不应该作为过滤条件透传）
_ASSOC_RESERVED_KEYS = {
    'page', 'page_size', 'pageSize', 'ordering', 'search', 'keyword',
    '_order_by', '_limit', '_offset',
}


def _extract_assoc_query_params(args):
    """从 request.args 中提取关联查询的过滤/排序/搜索参数。

    返回 (filters, ordering, search)：
    - filters: dict，key 为字段名（含 __in/__like/__gte/__lte/_start/_end 后缀），
               value 为标量或字符串
    - ordering: 字符串（可能为 '-field' 形式），空字符串表示未指定
    - search: 搜索关键词字符串
    """
    filters = {}
    ordering = ''
    search = ''

    ordering_raw = args.get('ordering') or args.get('_order_by') or ''
    if isinstance(ordering_raw, str):
        ordering = ordering_raw.strip()

    for raw in (args.get('search'), args.get('keyword')):
        if raw and not search:
            search = str(raw).strip()

    for key, value in args.items():
        if key in _ASSOC_RESERVED_KEYS:
            continue
        if key.startswith('filters[') or key == 'filters':
            # 形如 filters[name]=value 或 filters[name][in]=v — 不在 SQL 层解析
            continue
        if value is None or value == '':
            continue
        filters[key] = value

    return filters, ordering, search


def _get_data_source():
    global _data_source
    if _data_source is None:
        from meta.core.datasource import get_data_source
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


# ── CRUD ──

@bo_bp.route('/<object_type>', methods=['POST'])
@login_required
def create_bo(object_type):
    logger.info(f"[bo_api] create_bo START: object_type={object_type}")
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    try:
        result = bo.create(object_type, data)
        logger.info(f"[bo_api] result: success={result.success}, message={result.message}")
        status_code = 201 if result.success else (result.status_code or 400)

        if result.success and result.data and result.data.get('id'):
            try:
                from meta.services.data_permission_generator import DataPermissionGenerator
                from meta.api.user_api import get_current_user
                from meta.core.models import registry
                meta_obj = registry.get(object_type)
                if meta_obj:
                    user = get_current_user()
                    if user and user.get('user_id'):
                        ds = _get_data_source()
                        gen = DataPermissionGenerator(ds)
                        count = gen.generate_on_create(
                            meta_obj,
                            result.data['id'],
                            user['user_id']
                        )
                        if count > 0:
                            logger.info(f"[bo_api] auto_granted {count} data_permissions for user={user['user_id']} on {object_type}:{result.data['id']}")
            except Exception as e:
                logger.warning(f"[bo_api] auto_grant failed (non-fatal): {e}")

        return jsonify({'success': result.success, 'data': result.data, 'message': result.message}), status_code
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] create error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@meta_v2_bp.route('/schema-version', methods=['GET'])
def get_schema_version():
    import hashlib
    from datetime import datetime

    schema_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
    hasher = hashlib.md5()

    try:
        for filename in sorted(os.listdir(schema_dir)):
            if filename.endswith('.yaml') and not filename.startswith('_'):
                filepath = os.path.join(schema_dir, filename)
                with open(filepath, 'rb') as f:
                    hasher.update(f.read())
    except Exception as e:
        logger.warning(f"[schema-version] failed to hash schemas: {e}")
        hasher.update(str(datetime.now().date()).encode())

    return jsonify({
        'success': True,
        'data': {
            'schema_version': hasher.hexdigest()[:12],
            'timestamp': datetime.now().isoformat()
        }
    })


def _attach_change_history(record: dict, object_type: str, obj_id) -> None:
    """[FIX 2026-06-09] 为 v2 BO 读取响应附加 change_history (含子对象/关联操作)

    与 v1 manage_api.get_record 行为一致, 使用 include_children=True 以包含:
    - 子对象 (parent_object_type=object_type) 的 CRUD 日志
    - ASSOCIATE/DISSOCIATE/ASSIGN/REVOKE 关联操作日志
    """
    if not record:
        return
    try:
        from meta.services.audit_service import AuditService
        audit_service = AuditService(_get_data_source())
        record['change_history'] = audit_service.get_object_history(
            object_type, obj_id, include_children=True
        )
    except Exception as e:
        logger.debug(f"[bo_api] change_history attach failed for {object_type}/{obj_id}: {e}")
        record['change_history'] = []


@bo_bp.route('/<object_type>/<int:obj_id>', methods=['GET'])
@login_required
def read_bo(object_type, obj_id):
    bo = _get_bo()
    result = bo.read(object_type, obj_id)
    if result.success:
        _attach_change_history(result.data, object_type, obj_id)
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), 404


@bo_bp.route('/<object_type>/<path:obj_id>', methods=['GET'])
@login_required
def read_bo_by_string_id(object_type, obj_id):
    """支持字符串ID的读取路由"""
    bo = _get_bo()
    result = bo.read(object_type, obj_id)
    if result.success:
        _attach_change_history(result.data, object_type, obj_id)
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), 404


@bo_bp.route('/<object_type>', methods=['GET'])
@login_required
def query_bo(object_type):
    bo = _get_bo()
    request_filters = dict(request.args)
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', request.args.get('pageSize', 20)))
    ordering = request.args.get('ordering', '')

    # 移除分页和排序参数，只保留过滤参数
    clean_filters = {k: v for k, v in request_filters.items()
                     if k not in ('page', 'page_size', 'pageSize', 'ordering', '_limit', '_offset', '_order_by')}

    # 计算offset
    offset = (page - 1) * page_size

    # 构建查询参数，只传递过滤参数
    query_params = clean_filters.copy()
    if ordering:
        query_params['_order_by'] = ordering
    query_params['_limit'] = page_size
    query_params['_offset'] = offset

    logger.info(f"[query_bo] object_type={object_type}, page={page}, page_size={page_size}, ordering={ordering}, offset={offset}")
    logger.info(f"[query_bo] query_params={query_params}")

    # 直接使用crud_query action
    result = bo.execute(object_type, 'crud_query', query_params)
    
    logger.info(f"[query_bo] result.success={result.success}, result.data type={type(result.data)}, len={len(result.data) if hasattr(result.data, '__len__') else 'N/A'}")
    
    # 转换数据格式以匹配前端期望
    if result.success:
        raw_data = result.data
        
        # 从 ActionResult 获取 total
        total = getattr(result, 'total', None)
        if total is None:
            # 如果 result.total 不存在，使用 len(raw_data)
            total = len(raw_data) if isinstance(raw_data, list) else 0
        
        # 获取 filters 数组（从 view-config 中获取）
        filters = []
        try:
            config = view_config_service.get_or_build_view_config(object_type, None)
            if config and hasattr(config, 'list') and config.list:
                filters = config.list.filters if hasattr(config.list, 'filters') else []
        except Exception as e:
            logger.warning(f"[query_bo] Failed to get filters from view-config: {e}")
        
        # 检查是否是数组格式（来自 _do_list）
        if isinstance(raw_data, list):
            computation_service.compute_by_semantics(object_type, raw_data)
            # 返回 { items: [], total: 20, filters: [] } 格式
            return jsonify({
                'success': True,
                'data': {
                    'items': raw_data,
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'filters': filters
                },
                'message': result.message
            })
        else:
            # 已经是正确格式
            return jsonify({'success': True, 'data': result.data, 'message': result.message})
    else:
        logger.error(f"[query_bo] Error: {result.message}")
        status_code = result.status_code or 400
        return jsonify({'success': False, 'message': result.message}), status_code


@bo_bp.route('/<object_type>/deep', methods=['POST'])
@login_required
def deep_insert_bo(object_type):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    try:
        result = bo.deep_insert(object_type, data)
        if result.success:
            return jsonify({'success': True, 'data': result.data, 'message': result.message}), 201
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)
    except Exception as e:
        logger.error(f"[bo_api] deep_insert error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@bo_bp.route('/<object_type>/<int:obj_id>', methods=['PUT'])
@login_required
def update_bo(object_type, obj_id):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    result = bo.update(object_type, obj_id, data)
    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<path:obj_id>', methods=['PUT'])
@login_required
def update_bo_by_string_id(object_type, obj_id):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    result = bo.update(object_type, obj_id, data)
    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>', methods=['DELETE'])
@login_required
def delete_bo(object_type, obj_id):
    bo = _get_bo()
    result = bo.delete(object_type, obj_id)
    if result.success:
        return jsonify({'success': True, 'message': result.message})
    if hasattr(result, 'error') and result.error == 'NOT_FOUND':
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), 404
    if '不存在' in result.message or 'NOT_FOUND' in result.message:
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), 404
    return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<path:obj_id>', methods=['DELETE'])
@login_required
def delete_bo_by_string_id(object_type, obj_id):
    bo = _get_bo()
    result = bo.delete(object_type, obj_id)
    if result.success:
        return jsonify({'success': True, 'message': result.message})
    if hasattr(result, 'error') and result.error == 'NOT_FOUND':
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), 404
    if '不存在' in result.message or 'NOT_FOUND' in result.message:
        return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), 404
    return jsonify({'success': False, 'message': result.message, 'errors': result.errors}), (result.status_code or 400)


# ── Action ──

@bo_bp.route('/<object_type>/<int:obj_id>/actions/<action_id>', methods=['POST'])
@login_required
def execute_action(object_type, obj_id, action_id):
    bo = _get_bo()
    params = request.get_json(silent=True) or {}
    params['id'] = obj_id
    result = bo.execute_action(object_type, action_id, params)
    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


# ── Association ──

@bo_bp.route('/<object_type>/<int:obj_id>/associations/<association_name>', methods=['POST'])
@login_required
def associate_bo(object_type, obj_id, association_name):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    target_id = data.get('target_id') or data.get('tgt_id')
    target_type = data.get('target_type') or data.get('tgt_type')
    metadata = data.get('metadata', {})

    if not target_id:
        return jsonify({'success': False, 'message': 'target_id is required'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    result = bo.associate(
        src_type=object_type,
        src_id=obj_id,
        tgt_type=target_type,
        tgt_id=target_id,
        association_name=association_name,
        metadata=metadata,
    )

    if result.success:
        return jsonify({'success': True, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/associations/<association_name>', methods=['DELETE'])
@login_required
def dissociate_bo(object_type, obj_id, association_name):
    bo = _get_bo()
    target_id = request.args.get('target_id')
    target_type = request.args.get('target_type')

    if not target_id:
        data = request.get_json(silent=True) or {}
        target_id = data.get('target_id') or data.get('tgt_id')
        target_type = target_type or data.get('target_type') or data.get('tgt_type')

    if not target_id:
        return jsonify({'success': False, 'message': 'target_id is required (via query param or JSON body)'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    result = bo.dissociate(
        src_type=object_type,
        src_id=obj_id,
        tgt_type=target_type,
        tgt_id=int(target_id),
        association_name=association_name,
    )

    if result.success:
        return jsonify({'success': True, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/associations/<association_name>', methods=['GET'])
@login_required
def query_associations_bo(object_type, obj_id, association_name):
    bo = _get_bo()
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', request.args.get('pageSize', 50)))

    filters, ordering, search = _extract_assoc_query_params(request.args)

    result = bo.query_associations(
        src_type=object_type,
        src_id=obj_id,
        association_name=association_name,
        page=page,
        page_size=page_size,
        search=search,
        filters=filters,
        ordering=ordering,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data})
    logger.error(f"[bo_api] query_associations failed: type={object_type}, id={obj_id}, assoc={association_name}, message={result.message}")
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


# ── Association v2 ($associations 路由) ──

@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>', methods=['GET'])
@login_required
def query_associations_v2(object_type, obj_id, association_name):
    """查询关联列表 - v2 API"""
    bo = _get_bo()
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', request.args.get('pageSize', 50)))

    filters, ordering, search = _extract_assoc_query_params(request.args)

    result = bo.query_associations(
        src_type=object_type,
        src_id=obj_id,
        association_name=association_name,
        page=page,
        page_size=page_size,
        search=search,
        filters=filters,
        ordering=ordering,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/count', methods=['GET'])
@login_required
def count_associations_v2(object_type, obj_id, association_name):
    """统计关联数量 - v2 API"""
    bo = _get_bo()
    result = bo.count_associations(
        src_type=object_type,
        src_id=obj_id,
        association_name=association_name,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/assign', methods=['POST'])
@login_required
def assign_association_v2(object_type, obj_id, association_name):
    """分配单个关联 - v2 API (返回 204)"""
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    target_id = data.get('target_id') or data.get('tgt_id')
    target_type = data.get('target_type') or data.get('tgt_type')
    metadata = data.get('metadata', {})

    if not target_id:
        return jsonify({'success': False, 'message': 'target_id is required'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    result = bo.assign_association(
        src_type=object_type,
        src_id=obj_id,
        tgt_type=target_type,
        tgt_id=target_id,
        association_name=association_name,
        metadata=metadata,
    )

    if result.success:
        return '', 204
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/unassign', methods=['POST'])
@login_required
def unassign_association_v2(object_type, obj_id, association_name):
    """取消分配单个关联 - v2 API (返回 204)"""
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    association_record_id = data.get('association_record_id')
    target_id = data.get('target_id') or data.get('tgt_id')
    target_type = data.get('target_type') or data.get('tgt_type')

    if not target_id and not association_record_id:
        return jsonify({'success': False, 'message': 'target_id or association_record_id is required'}), 400

    if association_record_id:
        from meta.core.yaml_loader import get_meta_object
        meta_obj = get_meta_object(object_type)
        if meta_obj and meta_obj.associations:
            assoc_def = meta_obj.associations.get(association_name)
            if assoc_def and hasattr(assoc_def, 'through') and assoc_def.through:
                ds = bo._data_source
                sql = f"SELECT * FROM {assoc_def.through} WHERE id = ?"
                logger.info(f"[unassign] Looking up record: {sql} with params: [{association_record_id}]")
                cursor = ds.execute(sql, [int(association_record_id)])
                row = cursor.fetchone()
                if not row:
                    return jsonify({'success': False, 'message': 'Association record not found'}), 404
                columns = [desc[0] for desc in cursor.description]
                record = dict(zip(columns, row))
                src_key = assoc_def.source_key if hasattr(assoc_def, 'source_key') else 'source_id'
                tgt_key = assoc_def.target_key if hasattr(assoc_def, 'target_key') else 'target_id'
                target_id = record.get(tgt_key)
                if not target_id:
                    return jsonify({'success': False, 'message': 'Cannot resolve target_id from association record'}), 400
                if not target_type:
                    target_type = getattr(assoc_def, 'target_entity', None) or getattr(assoc_def, 'target_object', None)
            else:
                return jsonify({'success': False, 'message': 'Association does not use through table'}), 400
        else:
            return jsonify({'success': False, 'message': 'Cannot resolve association definition'}), 400
    else:
        target_id = int(target_id) if target_id else None

    if not target_id:
        return jsonify({'success': False, 'message': 'target_id is required'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    result = bo.unassign_association(
        src_type=object_type,
        src_id=obj_id,
        tgt_type=target_type,
        tgt_id=target_id,
        association_name=association_name,
    )

    if result.success:
        return '', 204
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/batch_assign', methods=['POST'])
@login_required
def batch_assign_associations_v2(object_type, obj_id, association_name):
    """批量分配关联 - v2 API"""
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    target_ids = data.get('target_ids', [])
    target_type = data.get('target_type') or data.get('tgt_type')
    metadata = data.get('metadata', {})

    if not target_ids:
        return jsonify({'success': False, 'message': 'target_ids is required'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    result = bo.batch_assign_associations(
        src_type=object_type,
        src_id=obj_id,
        tgt_type=target_type,
        target_ids=target_ids,
        association_name=association_name,
        metadata=metadata,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/$associations/<association_name>/batch_unassign', methods=['POST'])
@login_required
def batch_unassign_associations_v2(object_type, obj_id, association_name):
    """批量取消分配关联 - v2 API"""
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    target_ids = data.get('target_ids', [])
    target_type = data.get('target_type') or data.get('tgt_type')
    association_record_ids = data.get('association_record_ids', [])

    if association_record_ids:
        from meta.core.yaml_loader import get_meta_object
        meta_obj = get_meta_object(object_type)
        if meta_obj and meta_obj.associations:
            assoc_def = meta_obj.associations.get(association_name)
            if assoc_def and hasattr(assoc_def, 'through') and assoc_def.through:
                ds = bo._data_source
                tgt_key = assoc_def.target_key if hasattr(assoc_def, 'target_key') else 'target_id'
                placeholders = ','.join(['?' for _ in association_record_ids])
                sql = f"SELECT id, {tgt_key} FROM {assoc_def.through} WHERE id IN ({placeholders})"
                cursor = ds.execute(sql, [int(rid) for rid in association_record_ids])
                rows = cursor.fetchall()
                resolved_ids = [row[1] for row in rows if row[1] is not None]
                if not resolved_ids:
                    return jsonify({'success': False, 'message': 'No valid target IDs found'}), 400
                target_ids = list(set(resolved_ids + target_ids))
                if not target_type:
                    target_type = assoc_def.target_entity
            else:
                return jsonify({'success': False, 'message': 'Association does not use through table'}), 400
        else:
            return jsonify({'success': False, 'message': 'Cannot resolve association definition'}), 400

    if not target_ids:
        return jsonify({'success': False, 'message': 'target_ids or association_record_ids is required'}), 400

    if not target_type:
        target_type = _infer_target_type(object_type, association_name)

    result = bo.batch_unassign_associations(
        src_type=object_type,
        src_id=obj_id,
        tgt_type=target_type,
        target_ids=target_ids,
        association_name=association_name,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/$associations/<association_name>/batch-query', methods=['POST'])
@login_required
def batch_query_associations(object_type, association_name):
    bo = _get_bo()
    data = request.get_json(silent=True) or {}
    source_ids = data.get('source_ids', [])
    page = data.get('page', 1)
    page_size = data.get('page_size', data.get('pageSize', 20))
    search = data.get('search', '')

    if not source_ids:
        return jsonify({'success': True, 'data': {'items': [], 'total': 0, 'counts': {}}})

    result = bo.batch_query_associations(
        src_type=object_type,
        source_ids=source_ids,
        association_name=association_name,
        page=page,
        page_size=page_size,
        search=search,
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'message': result.message}), (result.status_code or 400)


@bo_bp.route('/<object_type>/<int:obj_id>/retrieve', methods=['GET'])
@login_required
def retrieve_with_associations(object_type, obj_id):
    """深度获取对象及其关联 - v2 API"""
    bo = _get_bo()

    associations_param = request.args.get('associations', '')
    associations = [a.strip() for a in associations_param.split(',') if a.strip()] if associations_param else None
    depth = int(request.args.get('depth', 1))

    if depth > 2:
        return jsonify({'success': False, 'message': '深度限制为2，防止循环引用'}), 400

    result = bo.retrieve_with_associations(
        object_type=object_type,
        obj_id=obj_id,
        associations=associations,
        depth=depth
    )

    if result.success:
        return jsonify({'success': True, 'data': result.data, 'message': result.message})
    return jsonify({'success': False, 'message': result.message}), 404


@bo_bp.route('/<object_type>/batch-delete', methods=['POST'])
@login_required
def batch_delete_bo(object_type):
    """批量删除记录"""
    from meta.services.manage_service import ManageService
    
    body = request.get_json(silent=True) or {}
    ids = body.get('ids', [])
    force = body.get('force', False)
    
    if not ids:
        return jsonify({'success': False, 'message': '请提供要删除的记录ID'}), 400
    
    try:
        bo = _get_bo()
        manage_service = ManageService(bo._data_source)
        
        # 设置审计用户
        current_user = getattr(g, 'current_user', None) or {}
        user_id = current_user.get('user_id') or request.headers.get('X-User-Id')
        user_name = current_user.get('display_name') or current_user.get('username') or request.headers.get('X-User-Name', '')
        user_ip = request.headers.get('X-Forwarded-For', request.remote_addr) or ''
        user_ua = request.headers.get('User-Agent', '')
        manage_service.set_audit_user(user_id, user_name, user_ip, user_ua)
        
        result = manage_service.batch_delete(object_type, ids, force)

        return jsonify({
            'success': result.failed_count == 0,
            'success_count': result.success_count,
            'failed_count': result.failed_count,
            'results': [r.to_dict() if hasattr(r, 'to_dict') else {'success': r.success, 'data': r.data, 'message': r.message, 'error': r.error} for r in result.results],
            'errors': result.errors,
        }), 200 if result.failed_count == 0 else 207
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] batch-delete error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [FIX GAP-008 2026-06-07] v2 端点补齐 — 8 个原仅 v1 存在的端点迁移到 v2
# v1 端点 (manage_api) 已被 sunset_at=2026-06-05, v2 路径未实现 → 测试报 500
# 解决: 在 v2 重新注册 8 个路由, 委托给 v1 handler (共享业务逻辑)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 延迟导入避免循环依赖
def _v1_handlers():
    """延迟导入 v1 handler 函数 (避免 manage_api 导入 bo_api 形成循环)"""
    from meta.api.manage_api import (
        list_records_post as _list_records_post,
        batch_create as _batch_create,
        batch_update as _batch_update,
        list_actions as _list_actions,
        recover_from_log as _recover_from_log,
        list_deleted_objects as _list_deleted_objects,
        get_state_history as _get_state_history,
        get_stage_metrics as _get_stage_metrics,
    )
    return {
        'list_records_post': _list_records_post,
        'batch_create': _batch_create,
        'batch_update': _batch_update,
        'list_actions': _list_actions,
        'recover_from_log': _recover_from_log,
        'list_deleted_objects': _list_deleted_objects,
        'get_state_history': _get_state_history,
        'get_stage_metrics': _get_stage_metrics,
    }


@bo_bp.route('/<object_type>/list', methods=['POST'])
@login_required
def v2_list_records_post(object_type):
    """POST 列表查询 (URL 过长场景) — 委托给 v1 manage_api"""
    return _v1_handlers()['list_records_post'](object_type)


@bo_bp.route('/<object_type>/batch-create', methods=['POST'])
@login_required
def v2_batch_create(object_type):
    """批量创建 — 委托给 v1 manage_api"""
    return _v1_handlers()['batch_create'](object_type)


@bo_bp.route('/<object_type>/batch-update', methods=['POST'])
@login_required
def v2_batch_update(object_type):
    """批量更新 — 委托给 v1 manage_api"""
    return _v1_handlers()['batch_update'](object_type)


@bo_bp.route('/<object_type>/<int:obj_id>/actions', methods=['GET'])
@login_required
def v2_list_actions(object_type, obj_id):
    """获取可执行 Action 列表 — 委托给 v1 manage_api"""
    return _v1_handlers()['list_actions'](object_type, obj_id)


@bo_bp.route('/<object_type>/<int:obj_id>/actions', methods=['GET'])
@login_required
def v2_list_actions_string(object_type, obj_id):
    """[path variant] 字符串 id 兼容 — 委托给 v1 manage_api"""
    return _v1_handlers()['list_actions'](object_type, obj_id)


@bo_bp.route('/<object_type>/<int:obj_id>/recover', methods=['POST'])
@login_required
def v2_recover_from_log(object_type, obj_id):
    """从 audit_log 恢复已删除 — 委托给 v1 manage_api"""
    return _v1_handlers()['recover_from_log'](object_type, obj_id)


@bo_bp.route('/<object_type>/deleted', methods=['GET'])
@login_required
def v2_list_deleted_objects(object_type):
    """查询已删除对象 — 委托给 v1 manage_api"""
    return _v1_handlers()['list_deleted_objects'](object_type)


@bo_bp.route('/<object_type>/<int:obj_id>/state_history', methods=['GET'])
@login_required
def v2_get_state_history(object_type, obj_id):
    """状态转换历史 — 委托给 v1 manage_api"""
    return _v1_handlers()['get_state_history'](object_type, obj_id)


@bo_bp.route('/<object_type>/<int:obj_id>/stage_metrics', methods=['GET'])
@login_required
def v2_get_stage_metrics(object_type, obj_id):
    """状态停留统计 — 委托给 v1 manage_api"""
    return _v1_handlers()['get_stage_metrics'](object_type, obj_id)


# ── Architecture Preview ──

@bo_bp.route('/architecture/preview', methods=['GET'])
@login_required
def get_architecture_preview():
    """架构预览聚合 API - 一次返回完整树结构数据"""
    try:
        bo = _get_bo()
        version_id = request.args.get('version_id', type=int)
        domain_ids = request.args.get('domain_ids', '')
        sub_domain_ids = request.args.get('sub_domain_ids', '')
        service_module_ids = request.args.get('service_module_ids', '')
        business_object_ids = request.args.get('business_object_ids', '')

        # 构建版本过滤条件
        version_filter = {'version_id': version_id} if version_id else {}

        # 查询各层级数据（大 page_size 获取全量）
        domain_result = bo.query('domain', version_filter.copy(), page_size=5000)
        sub_domain_result = bo.query('sub_domain', version_filter.copy(), page_size=5000)
        module_result = bo.query('service_module', version_filter.copy(), page_size=5000)
        bo_result = bo.query('business_object', version_filter.copy(), page_size=5000)
        rel_result = bo.query('relationship', version_filter.copy(), page_size=10000)

        # 提取数据
        domains = domain_result.data if domain_result.success else []
        sub_domains = sub_domain_result.data if sub_domain_result.success else []
        modules = module_result.data if module_result.success else []
        business_objects = bo_result.data if bo_result.success else []
        relationships = rel_result.data if rel_result.success else []

        # 解析过滤 ID 列表
        domain_id_list = [int(x) for x in domain_ids.split(',') if x.strip()]
        sub_domain_id_list = [int(x) for x in sub_domain_ids.split(',') if x.strip()]
        module_id_list = [int(x) for x in service_module_ids.split(',') if x.strip()]
        bo_id_list = [int(x) for x in business_object_ids.split(',') if x.strip()]

        # 按 ID 过滤
        if domain_id_list:
            domains = [d for d in domains if d.get('id') in domain_id_list]
        if sub_domain_id_list:
            sub_domains = [d for d in sub_domains if d.get('id') in sub_domain_id_list]
        if module_id_list:
            modules = [m for m in modules if m.get('id') in module_id_list]
        if bo_id_list:
            business_objects = [b for b in business_objects if b.get('id') in bo_id_list]

        # 计算 center_scope（中心范围的 BO code 列表）
        center_scope = []
        if bo_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('id') in bo_id_list]
        elif module_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('service_module_id') in module_id_list]
        elif sub_domain_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('sub_domain_id') in sub_domain_id_list]
        elif domain_id_list:
            center_scope = [b.get('code', '') for b in business_objects if b.get('domain_id') in domain_id_list]

        # ── Relation Classification（scope_type + category_type 下沉到后端）──
        # 构建 BO id → {domain_id, sub_domain_id, service_module_id} 映射
        bo_id_map = {}
        for b in business_objects:
            bo_id_map[b.get('id')] = {
                'domain_id': b.get('domain_id'),
                'sub_domain_id': b.get('sub_domain_id'),
                'service_module_id': b.get('service_module_id'),
            }

        # 确定哪些 BO 在范围内
        center_scope_set = set(center_scope)
        bo_code_map = {b.get('code'): b.get('id') for b in business_objects if b.get('code')}

        # 对每条 relationship 附加 scope_type 和 category_type
        for rel in relationships:
            src_code = rel.get('source_code') or rel.get('sourceCode')
            tgt_code = rel.get('target_code') or rel.get('targetCode')

            # 自环关系
            if src_code and tgt_code and src_code == tgt_code:
                rel['scope_type'] = 'external'
                rel['category_type'] = 'cross-domain'
                continue

            # 获取源和目标 BO 的层级信息
            src_bo_id = bo_code_map.get(src_code)
            tgt_bo_id = bo_code_map.get(tgt_code)
            src_info = bo_id_map.get(src_bo_id, {}) if src_bo_id else {}
            tgt_info = bo_id_map.get(tgt_bo_id, {}) if tgt_bo_id else {}

            # 计算 scope_type
            src_in_scope = src_code in center_scope_set if center_scope_set else True
            tgt_in_scope = tgt_code in center_scope_set if center_scope_set else True

            if src_in_scope and tgt_in_scope:
                scope_type = 'internal'
            elif src_in_scope or tgt_in_scope:
                scope_type = 'cross-boundary'
            else:
                scope_type = 'external'

            # 计算 category_type
            src_domain_id = src_info.get('domain_id')
            tgt_domain_id = tgt_info.get('domain_id')
            src_sub_domain_id = src_info.get('sub_domain_id')
            tgt_sub_domain_id = tgt_info.get('sub_domain_id')
            src_module_id = src_info.get('service_module_id')
            tgt_module_id = tgt_info.get('service_module_id')

            if src_domain_id and tgt_domain_id and src_domain_id != tgt_domain_id:
                category_type = 'cross-domain'
            elif src_sub_domain_id and tgt_sub_domain_id and src_sub_domain_id != tgt_sub_domain_id:
                category_type = 'same-domain-cross-subdomain'
            elif src_module_id and tgt_module_id and src_module_id != tgt_module_id:
                category_type = 'same-subdomain-cross-module'
            else:
                category_type = 'same-module'

            # 修正：外部关系但分类为同模块时，提升到更高级别
            if scope_type != 'internal' and category_type == 'same-module':
                if src_sub_domain_id and tgt_sub_domain_id and src_sub_domain_id != tgt_sub_domain_id:
                    category_type = 'same-domain-cross-subdomain'
                elif src_domain_id and tgt_domain_id and src_domain_id != tgt_domain_id:
                    category_type = 'cross-domain'

            rel['scope_type'] = scope_type
            rel['category_type'] = category_type

        return jsonify({
            'success': True,
            'data': {
                'domains': domains,
                'sub_domains': sub_domains,
                'service_modules': modules,
                'business_objects': business_objects,
                'relationships': relationships,
                'center_scope': center_scope
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] architecture preview error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@bo_bp.route('/<object_type>/<int:obj_id>/state_transitions', methods=['GET'])
@login_required
def get_state_transitions(object_type, obj_id):
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404

    bo = _get_bo()
    result = bo.read(object_type, obj_id)
    if not result or not result.success:
        return jsonify({'success': False, 'message': 'Record not found'}), 404

    record = result.data if hasattr(result, 'data') else result

    state_transitions = []
    for rule in meta_obj.rules:
        if not hasattr(rule, 'state_field'):
            continue
        if not hasattr(rule, 'from_states') or not hasattr(rule, 'to_state'):
            continue

        current_state = record.get(rule.state_field) if isinstance(record, dict) else getattr(record, rule.state_field, None)
        is_available = current_state in rule.from_states

        ui_hints = getattr(rule, 'ui_hints', None)

        transition_info = {
            'id': rule.id,
            'name': rule.name,
            'stateField': rule.state_field,
            'fromStates': list(rule.from_states),
            'toState': rule.to_state,
            'currentState': current_state,
            'available': is_available,
            'label': ui_hints.label if ui_hints else rule.name,
            'icon': ui_hints.icon if ui_hints else '',
            'confirmMessage': ui_hints.confirm_message if ui_hints else '',
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


@bo_bp.route('/<object_type>/<path:obj_id>/state_transitions', methods=['GET'])
@login_required
def get_state_transitions_by_string_id(object_type, obj_id):
    """支持字符串ID的状态转换路由"""
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404

    bo = _get_bo()
    result = bo.read(object_type, obj_id)
    if not result or not result.success:
        return jsonify({'success': False, 'message': 'Record not found'}), 404

    record = result.data if hasattr(result, 'data') else result

    state_transitions = []
    for rule in meta_obj.rules:
        if not hasattr(rule, 'state_field'):
            continue
        if not hasattr(rule, 'from_states') or not hasattr(rule, 'to_state'):
            continue

        current_state = record.get(rule.state_field) if isinstance(record, dict) else getattr(record, rule.state_field, None)
        is_available = current_state in rule.from_states

        ui_hints = getattr(rule, 'ui_hints', None)

        transition_info = {
            'id': rule.id,
            'name': rule.name,
            'stateField': rule.state_field,
            'fromStates': list(rule.from_states),
            'toState': rule.to_state,
            'currentState': current_state,
            'available': is_available,
            'label': ui_hints.label if ui_hints else rule.name,
            'icon': ui_hints.icon if ui_hints else '',
            'confirmMessage': ui_hints.confirm_message if ui_hints else '',
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


# ── Meta / UI Config ──

@meta_v2_bp.route('/<object_type>/ui-config', methods=['GET'])
@login_required
def get_ui_config(object_type):
    try:
        bo = _get_bo()
        config = bo.get_ui_config(object_type)
        if config:
            json_safe_config = _make_json_safe(config)
            return jsonify({'success': True, 'data': json_safe_config})
        return jsonify({'success': False, 'message': f'Unknown object type: {object_type}'}), 404
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] ui-config error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


def _make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_json_safe(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    elif hasattr(obj, '__dict__'):
        return _make_json_safe(obj.__dict__)
    else:
        return str(obj)


@meta_v2_bp.route('/<object_type>/schema', methods=['GET'])
@login_required
def get_object_schema(object_type):
    try:
        bo = _get_bo()
        schema = bo.get_schema(object_type)
        if not schema:
            return jsonify({'success': False, 'message': f'Unknown object type: {object_type}'}), 404

        meta_obj = registry.get(object_type)
        if meta_obj:
            actions = getattr(meta_obj, 'actions', None)
            if actions:
                action_list = []
                if isinstance(actions, dict):
                    for name, action in actions.items():
                        a = _to_json_dict(action)
                        a['name'] = name
                        action_list.append(a)
                elif isinstance(actions, list):
                    for action in actions:
                        a = _to_json_dict(action)
                        action_list.append(a)
                schema['actions'] = action_list

            if hasattr(meta_obj, 'hierarchy') and meta_obj.hierarchy:
                schema['hierarchy'] = meta_obj.hierarchy

            if hasattr(meta_obj, 'context') and meta_obj.context:
                schema['context'] = meta_obj.context

            if hasattr(meta_obj, 'cascade_select') and meta_obj.cascade_select:
                schema['cascade_select'] = meta_obj.cascade_select

            if object_type == 'relationship':
                scope_rules = _load_scope_rules()
                if scope_rules:
                    schema['scope_rules'] = scope_rules

            if object_type in ['domain', 'sub_domain', 'service_module', 'business_object']:
                annotation_categories = _load_annotation_categories()
                if annotation_categories:
                    schema['annotations'] = {
                        'enabled': True,
                        'categories': annotation_categories
                    }

        return jsonify({'success': True, 'data': schema})
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] schema error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@meta_v2_bp.route('/<object_type>/full', methods=['GET'])
@login_required
def get_meta_full(object_type):
    """元数据合并 API - 一次返回 ui_config + schema + field_policies"""
    try:
        bo = _get_bo()

        # 获取 ui_config
        ui_config = bo.get_ui_config(object_type)

        # 获取 schema
        schema = bo.get_schema(object_type)

        # 获取 field_policies
        meta_obj = registry.get(object_type)
        field_policies = {}
        if meta_obj:
            context = request.args.get('context', 'read')
            mutability = request.args.get('mutability')
            engine = FieldPolicyEngine(meta_object=meta_obj)
            object_context = ObjectContext(mutability=mutability, object_type=object_type)
            policy_context = PolicyContext(object_context=object_context, action=context)
            for f in meta_obj.fields:
                field_policies[f.id] = {
                    'editable': engine.is_field_editable(f.id, policy_context),
                    'visible': engine.is_field_visible(f.id, policy_context),
                    'required': engine.is_field_required(f.id, policy_context),
                }

        return jsonify({
            'success': True,
            'data': {
                'ui_config': _make_json_safe(ui_config) if ui_config else {},
                'schema': schema,
                'field_policies': field_policies,
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] meta-full error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] [NEW] v1.2 / FR-2.4: 全量 OpenAPI 端点（Action + BO CRUD + Meta）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@meta_v2_bp.route('/_openapi.json', methods=['GET'])
def get_full_openapi():
    """
    [DECORATIVE] [NEW] v1.2 / FR-2.4: 全量 OpenAPI 规范（Action + BO CRUD + Meta）

    与 bo_action_api._openapi.json（Action-only）共存。
    复用 _generate_action_openapi + _generate_bo_crud_paths + _generate_bo_schema。
    """
    try:
        from flask import request as _req
        from meta.api.bo_action_api import _generate_action_openapi
        from meta.core.models import registry

        base_url = _req.host_url.rstrip('/')

        # 1. Action OpenAPI（从 bo_action_api 复用）
        action_spec = _generate_action_openapi(base_url)

        # 2. BO CRUD paths（防御性检查 registry.all()）
        meta_objects = list(registry.all()) if hasattr(registry, 'all') else []
        bo_paths = _generate_bo_crud_paths(meta_objects)

        # 3. BO schemas
        bo_schemas = {
            obj.id: _generate_bo_schema(obj)
            for obj in meta_objects
            if getattr(obj, 'table_name', None)
        }

        # 4. 合并
        spec = action_spec.copy()
        spec['paths'].update(bo_paths)
        spec['components']['schemas'].update(bo_schemas)
        spec['info']['title'] = 'Excel-to-Diagram Full API'
        spec['info']['version'] = 'v2.0'
        spec['info']['description'] = '全量 OpenAPI 规范（Action + BO CRUD + Meta）'

        return jsonify(spec)
    except Exception as e:
        import traceback
        return jsonify({
            'error': type(e).__name__,
            'message': str(e),
            'traceback': traceback.format_exc(),
        }), 500


@meta_v2_bp.route('/<object_type>/field-policies', methods=['GET'])
@login_required
def get_field_policies(object_type):
    """获取字段策略评估结果"""
    try:
        context = request.args.get('context', 'read')
        mutability = request.args.get('mutability', None)

        meta_obj = registry.get(object_type)
        if not meta_obj:
            return jsonify({'success': False, 'message': f'Object type {object_type} not found'}), 404

        engine = FieldPolicyEngine(meta_object=meta_obj)

        object_context = ObjectContext(mutability=mutability, object_type=object_type)
        policy_context = PolicyContext(object_context=object_context, action=context)

        field_ids = [f.id for f in meta_obj.fields]
        editable_fields = engine.get_editable_fields(field_ids, policy_context)
        readonly_fields = engine.get_readonly_fields(field_ids, policy_context)

        # [DECORATIVE] [NEW] v1.2 / FR-4.5a: 提取 conditional_required 规则（从 field.constraints）
        # 供前端 useFieldPolicy.requiredMap 消费
        policies = {}
        for field_id in field_ids:
            field_def = None
            for f in meta_obj.fields:
                if f.id == field_id:
                    field_def = f
                    break
            conditional_required = []
            if field_def:
                constraints = getattr(field_def, 'constraints', None)
                if isinstance(constraints, list):
                    for c in constraints:
                        if isinstance(c, dict) and c.get('type') == 'conditional_required':
                            conditional_required.append({
                                'condition': c.get('condition', ''),
                                'message': c.get('message', ''),
                                'severity': c.get('severity', 'error'),
                            })
                elif isinstance(constraints, dict) and constraints.get('type') == 'conditional_required':
                    conditional_required.append({
                        'condition': constraints.get('condition', ''),
                        'message': constraints.get('message', ''),
                        'severity': constraints.get('severity', 'error'),
                    })
            policies[field_id] = {
                'editable': field_id in editable_fields,
                'visible': engine.is_field_visible(field_id, policy_context),
                'required': engine.is_field_required(field_id, policy_context),
                'conditional_required': conditional_required,  # [DECORATIVE] FR-4.5a
            }

        return jsonify({
            'success': True,
            'data': policies
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] field-policies error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


def _load_scope_rules():
    """加载 scope_rules 配置"""
    try:
        from meta.core.virtual_field_transform import load_scope_rules_from_ref
        rules = load_scope_rules_from_ref()
        if rules:
            return [
                {
                    'id': r.get('id'),
                    'name': r.get('name'),
                    'description': r.get('description', ''),
                    'rule': r.get('rule', ''),
                    'color': r.get('color', '#999999')
                }
                for r in rules
            ]
    except Exception as e:
        logger.warning(f"[bo_api] Failed to load scope_rules: {e}")
    return None


def _load_annotation_categories():
    """加载备注分类配置"""
    try:
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        ds = get_data_source("sqlite", database=db_path)
        cursor = ds.execute(
            "SELECT code, name, name_en FROM enum_values WHERE enum_type_id = 'annotation_category' AND is_active = 1 ORDER BY sort_order"
        )
        rows = cursor.fetchall()
        return [
            {'code': r[0], 'name': r[1], 'name_en': r[2] if len(r) > 2 else r[1]}
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"[bo_api] Failed to load annotation categories: {e}")
    return None


@meta_v2_bp.route('/<object_type>/view-config', methods=['GET'])
@meta_v2_bp.route('/<object_type>/view-config/<view_name>', methods=['GET'])
@login_required
def get_view_config(object_type, view_name='default'):
    try:
        from meta.services.view_config_service import view_config_service
        from meta.api.meta_api import _dataclass_to_dict
        
        # 先获取原始配置
        original_config = view_config_service.get_view_config(object_type, view_name)
        logger.info(f"[bo_api] original_config: {original_config}")
        logger.info(f"[bo_api] original_config.list: {original_config.list if original_config else 'None'}")
        logger.info(f"[bo_api] original_config.list.actions: {original_config.list.actions if original_config and original_config.list else 'None'}")
        
        config = view_config_service.get_or_build_view_config(object_type, view_name)
        
        if not config:
            return jsonify({'success': False, 'message': f'View config not found for: {object_type}'}), 404
        
        logger.info(f"[bo_api] config.list.actions: {config.list.actions}")
        logger.info(f"[bo_api] config.list.actions length: {len(config.list.actions)}")
        
        data = _dataclass_to_dict(config)

        bo = _get_bo()
        ui_config = bo.get_ui_config(object_type)
        if ui_config.get('fields'):
            data['fields'] = ui_config['fields']
        # [FIX 2026-06-09] 合并 associations 元数据。
        # 原因：role.yaml 的 assigned_groups.readonly: true 需要传到前端
        #       DetailPage.vue 用 tab.readonly || assocDef?.readonly 判定，
        #       若不合并 associations → assocDef 找不到 → readonly 永远 false
        #       → AssociationSection.vue 仍显示"移除"按钮。
        if ui_config.get('associations'):
            data['associations'] = ui_config['associations']

        logger.info(f"[bo_api] data['list']['actions']: {data['list']['actions']}")
        logger.info(f"[bo_api] data['list']['actions'] length: {len(data['list']['actions'])}")
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] view-config error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@meta_v2_bp.route('/<object_type>/views', methods=['GET'])
@login_required
def list_view_configs(object_type):
    try:
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return jsonify({'success': False, 'message': f'Unknown object type: {object_type}'}), 404

        views = [{'name': 'default', 'label': '默认视图'}]

        view_configs = getattr(meta_obj, 'view_configs', None)
        if view_configs and isinstance(view_configs, dict):
            for name, config in view_configs.items():
                views.append({
                    'name': name,
                    'label': config.get('label', name)
                })

        ui_view_config = getattr(meta_obj, 'ui_view_config', None)
        if ui_view_config and isinstance(ui_view_config, dict):
            configured_views = ui_view_config.get('views', {})
            for name, config in configured_views.items():
                if not any(v['name'] == name for v in views):
                    views.append({
                        'name': name,
                        'label': config.get('label', name)
                    })

        return jsonify({'success': True, 'data': {'views': views}})
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] list views error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


def _to_json_dict(obj) -> dict:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, '__dict__'):
        result = {}
        for k, v in obj.__dict__.items():
            if hasattr(v, '__dict__') and not isinstance(v, (str, int, float, bool, list, dict)):
                result[k] = str(v)
            elif isinstance(v, (list, dict, str, int, float, bool)) or v is None:
                result[k] = v
            else:
                result[k] = str(v)
        return result
    return {'value': str(obj)}


@meta_v2_bp.route('/hierarchy/tree', methods=['GET'])
@login_required
def get_hierarchy_tree():
    """
    获取层级树

    Query params:
        - object_type: 起始对象类型（可选，默认从顶层开始）
        - parent_id: 父节点ID（可选，用于构建子树）
        - version_id: 版本ID（可选，用于版本上下文过滤）
        - levels: 包含的层级列表（可选，逗号分隔）

    Returns:
        {
            "success": true,
            "data": {
                "tree": [...]
            }
        }
    """
    try:
        from meta.services.hierarchy_service import HierarchyService

        object_type = request.args.get('object_type')
        parent_id = request.args.get('parent_id', type=int)
        version_id = request.args.get('version_id', type=int)
        levels_str = request.args.get('levels')
        include_relation_counts = request.args.get('include_counts', 'true').lower() == 'true'

        levels = None
        if levels_str:
            levels = [l.strip() for l in levels_str.split(',') if l.strip()]

        svc = HierarchyService()
        tree = svc.build_tree(
            object_type=object_type,
            parent_id=parent_id,
            version_id=version_id,
            levels=levels,
            include_relation_counts=include_relation_counts
        )

        return jsonify({
            'success': True,
            'data': {
                'tree': tree,
                'levels': svc.get_levels()
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] hierarchy tree error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@meta_v2_bp.route('/hierarchy/levels', methods=['GET'])
@login_required
def get_hierarchy_levels():
    """获取层级定义列表"""
    try:
        from meta.services.hierarchy_service import HierarchyService
        svc = HierarchyService()
        levels = svc.get_levels()
        return jsonify({
            'success': True,
            'data': {'levels': levels}
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def _infer_target_type(src_type: str, association_name: str) -> str:
    from meta.core.metadata_resolver import MetadataResolver
    return MetadataResolver.get_association_target(src_type, association_name)


# ── Role Unified Permissions (v2) ──

role_v2_bp = Blueprint('role_v2', __name__, url_prefix='/api/v2/roles')


@role_v2_bp.route('/<int:role_id>/unified-permissions', methods=['GET'])
@login_required
def get_role_unified_permissions(role_id):
    """获取角色的统一权限（菜单权限矩阵）

    权限计算公式: effective = (auto_menu ∪ manual_include) - manual_exclude
    - auto_menu: 已分配菜单的 required_permissions 自动派生
    - manual_include: role_permissions 中 granted=1 的记录
    - manual_exclude: role_permissions 中 granted=0 的记录
    """
    try:
        from meta.core.datasource import get_data_source
        from meta.services.menu_permission_service import MenuPermissionService

        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        ds = get_data_source("sqlite", database=db_path)
        menu_service = MenuPermissionService(ds)

        # 获取角色已分配的菜单
        cursor = ds.execute("""
            SELECT rmp.menu_code, m.menu_name, m.menu_path, m.icon, m.sort_order
            FROM role_menu_permissions rmp
            JOIN menus m ON rmp.menu_code = m.menu_code
            WHERE rmp.role_id = ?
            ORDER BY m.sort_order, m.menu_name
        """, [role_id])

        assigned_menus = {}
        for row in cursor.fetchall():
            menu_code = row[0]
            assigned_menus[menu_code] = {
                'menu_code': menu_code,
                'display_name': row[1],
                'menu_path': row[2],
                'icon': row[3],
                'assigned': True,
                'required_permissions': []
            }

        # 查询角色的手动权限覆盖（include/exclude）
        cursor = ds.execute("""
            SELECT rp.permission_id, rp.granted, p.code
            FROM role_permissions rp
            JOIN permissions p ON rp.permission_id = p.id
            WHERE rp.role_id = ?
        """, [role_id])
        manual_overrides = {}  # {perm_code: {'granted': bool, 'source': str}}
        for row in cursor.fetchall():
            manual_overrides[row[2]] = {
                'granted': bool(row[1]),
                'source': 'include' if bool(row[1]) else 'exclude'
            }

        # 获取所有菜单（[单一事实源] 与 LandingPage 末端节点一致）
        cursor = ds.execute("""
            SELECT menu_code, menu_name, menu_path, icon, sort_order,
                   required_permissions, required_any_permission, data_permission_hint
            FROM menus
            WHERE is_active = 1 AND show_in_sidebar = 1
              AND menu_code != 'dashboard'
              AND menu_code NOT IN (
                SELECT DISTINCT parent_menu FROM menus
                WHERE parent_menu IS NOT NULL AND parent_menu != ''
                  AND is_active = 1 AND show_in_sidebar = 1
              )
              AND menu_path IS NOT NULL AND menu_path != ''
              AND (parent_menu IS NULL OR parent_menu = ''
                   OR parent_menu NOT IN (
                     SELECT menu_code FROM menus
                     WHERE page_type = 'multi_object_hub' AND is_active = 1
                   ))
            ORDER BY sort_order, menu_name
        """)

        # 动作分组配置
        ACTION_GROUPS = {
            'view':   {'label': '查看', 'actions': ['read', 'list']},
            'edit':   {'label': '编辑', 'actions': ['read', 'list', 'create', 'update']},
            'manage': {'label': '管理', 'actions': ['read', 'list', 'create', 'update', 'delete']},
        }
        # 独立动作列表
        STANDALONE_ACTIONS = ['export', 'import', 'assign', 'unassign',
                              'associate', 'dissociate', 'grant', 'revoke']

        # 动作标签映射
        action_labels = {
            'read': '查看', 'create': '创建', 'update': '编辑',
            'delete': '删除', 'list': '列表', 'manage': '管理',
            'export': '导出', 'import': '导入', 'assign': '分配',
            'unassign': '取消分配', 'associate': '关联', 'dissociate': '取消关联',
            'grant': '授权', 'revoke': '撤销',
        }

        menus = []
        for row in cursor.fetchall():
            menu_code = row[0]
            required_perm_codes = []
            if row[5]:  # required_permissions
                try:
                    import json
                    required_perm_codes = json.loads(row[5]) if isinstance(row[5], str) else row[5]
                except:
                    pass

            # 转换为前端期望的格式: [{code, label, granted, source}]
            is_assigned = menu_code in assigned_menus
            required_perms = []
            for perm_code in required_perm_codes:
                # 解析权限代码: "domain:read" -> domain, read
                parts = perm_code.split(':')
                resource = parts[0] if len(parts) > 0 else perm_code
                action = parts[1] if len(parts) > 1 else 'read'

                # 计算权限状态
                if perm_code in manual_overrides:
                    override = manual_overrides[perm_code]
                    granted = override['granted']
                    source = override['source']
                elif is_assigned:
                    granted = True
                    source = 'auto'
                else:
                    granted = False
                    source = ''

                # 生成友好的标签
                label = f'{resource.title()} - {action_labels.get(action, action)}'

                required_perms.append({
                    'code': perm_code,
                    'label': label,
                    'granted': granted,
                    'source': source
                })



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

            # 按 BO 分组推导动作分组状态
            # 收集每个 resource 的权限状态
            resource_perms = {}  # {resource: {action: {granted, source}}}
            for perm_code in required_perm_codes:
                parts = perm_code.split(':')
                resource = parts[0] if len(parts) > 0 else perm_code
                action = parts[1] if len(parts) > 1 else 'read'
                if resource not in resource_perms:
                    resource_perms[resource] = {}
                # 获取该权限的计算结果
                for p in required_perms:
                    if p['code'] == perm_code:
                        resource_perms[resource][action] = {
                            'granted': p['granted'],
                            'source': p['source']
                        }
                        break

            # 推导动作分组状态
            bo_permission_groups = []
            for resource, actions_map in resource_perms.items():
                groups = {}
                for group_key, group_def in ACTION_GROUPS.items():
                    group_actions = group_def['actions']
                    # 检查该 BO 是否有这些动作的权限
                    available_actions = [a for a in group_actions if a in actions_map]
                    if not available_actions:
                        continue  # 该 BO 没有此分组的动作

                    # 分组 granted = 所有可用动作都 granted
                    group_granted = all(
                        actions_map[a]['granted'] for a in available_actions
                    )

                    # 分组 source 推导
                    sources = set(
                        actions_map[a]['source'] for a in available_actions
                    )
                    if 'exclude' in sources:
                        group_source = 'exclude'
                    elif 'include' in sources:
                        group_source = 'include'
                    elif 'auto' in sources:
                        group_source = 'auto'
                    else:
                        group_source = ''

                    groups[group_key] = {
                        'granted': group_granted,
                        'source': group_source
                    }

                # 独立动作
                standalone_perms = []
                for action_key in STANDALONE_ACTIONS:
                    if action_key in actions_map:
                        standalone_perms.append({
                            'action': action_key,
                            'label': action_labels.get(action_key, action_key),
                            'granted': actions_map[action_key]['granted'],
                            'source': actions_map[action_key]['source']
                        })

                bo_permission_groups.append({
                    'bo_id': resource,
                    'bo_name': resource.title(),
                    'groups': groups,
                    'standalone': standalone_perms
                })

            data_hint = None
            if row[7]:  # data_permission_hint
                try:
                    import json
                    data_hint = json.loads(row[7]) if isinstance(row[7], str) else row[7]
                except:
                    pass

            menus.append({
                'menu_code': menu_code,
                'display_name': row[1],
                'menu_path': row[2],
                'icon': row[3],
                'assigned': is_assigned,
                'required_permissions': required_perms,
                'bo_permission_groups': bo_permission_groups,
                'has_data_scope': bool(row[6]),
                'data_permission_hint': data_hint
            })

        # 获取角色信息
        cursor = ds.execute("SELECT id, code, name FROM roles WHERE id = ?", [role_id])
        role_row = cursor.fetchone()
        role_info = None
        if role_row:
            role_info = {'id': role_row[0], 'code': role_row[1], 'name': role_row[2]}

        return jsonify({
            'success': True,
            'data': {
                'role': role_info,
                'menus': menus,
                'total_count': len(menus),
                'assigned_count': len(assigned_menus)
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] unified-permissions error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@role_v2_bp.route('/<int:role_id>/menu-permissions', methods=['PUT'])
@login_required
def update_role_menu_permissions(role_id):
    """更新角色的菜单权限和功能权限

    请求体:
    {
        "menu_codes": ["architecture_data", "system_management"],
        "permissions": [
            {"code": "domain:update", "granted": false},   // exclude
            {"code": "product:create", "granted": true}     // include
        ]
    }

    采用全量替换策略：DELETE 该角色所有 role_permissions 记录，再 INSERT 请求中的手动权限。
    """
    try:
        from meta.core.datasource import get_data_source

        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        ds = get_data_source("sqlite", database=db_path)

        # 获取角色信息
        cursor = ds.execute("SELECT is_system FROM roles WHERE id = ?", [role_id])
        role_row = cursor.fetchone()
        if not role_row:
            return jsonify({'success': False, 'message': '角色不存在'}), 404
        if role_row[0]:
            return jsonify({'success': False, 'message': '系统角色不可修改'}), 400

        data = request.get_json(silent=True) or {}
        menu_codes = data.get('menu_codes', [])
        permissions = data.get('permissions', [])

        with ds.transaction():
            # 1. 保存菜单分配
            ds.execute("DELETE FROM role_menu_permissions WHERE role_id = ?", [role_id])
            for menu_code in menu_codes:
                ds.execute(
                    "INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)",
                    [role_id, menu_code]
                )

            # 2. 全量替换手动权限 include/exclude
            ds.execute("DELETE FROM role_permissions WHERE role_id = ?", [role_id])
            for perm in permissions:
                perm_code = perm.get('code', '')
                granted = perm.get('granted', True)
                cursor = ds.execute("SELECT id FROM permissions WHERE code = ?", [perm_code])
                perm_row = cursor.fetchone()
                if perm_row:
                    ds.execute("""
                        INSERT INTO role_permissions (role_id, permission_id, granted, created_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """, [role_id, perm_row[0], 1 if granted else 0])

        return jsonify({
            'success': True,
            'message': f'已更新 {len(menu_codes)} 个菜单权限和 {len(permissions)} 个功能权限'
        })
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] update-menu-permissions error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── Permission Rules (v2) ──

permission_rule_v2_bp = Blueprint('permission_rule_v2', __name__, url_prefix='/api/v2/permission-rules')


@permission_rule_v2_bp.route('', methods=['GET'])
@login_required
def list_permission_rules_v2():
    """获取权限规则列表"""
    try:
        from meta.services.condition_permission_service import ConditionPermissionService
        from meta.core.bo_framework import bo_framework
        
        service = ConditionPermissionService(bo_framework._data_source)
        
        role_id = request.args.get('role_id', type=int)
        
        if role_id:
            rules = service.get_rules_by_role(role_id)
        else:
            rules = service.get_all_rules()
        
        return jsonify({'success': True, 'data': rules})
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] list-permission-rules-v2 error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_v2_bp.route('', methods=['POST'])
@login_required
def create_permission_rule_v2():
    """创建权限规则"""
    try:
        from meta.services.condition_permission_service import ConditionPermissionService
        from meta.core.bo_framework import bo_framework
        
        service = ConditionPermissionService(bo_framework._data_source)
        
        data = request.get_json(silent=True) or {}
        
        required_fields = ['role_id', 'resource_type', 'condition']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} 是必填字段'}), 400
        
        # 获取当前用户
        current_user = getattr(g, 'current_user', None) or {}
        user_id = current_user.get('user_id')
        
        rule_data = {
            'role_id': data.get('role_id'),
            'resource_type': data.get('resource_type'),
            'condition': data.get('condition'),
            'permission_level': data.get('permission_level', 'read'),
            'is_denied': data.get('is_denied', False),
            'inherit_to_children': data.get('inherit_to_children', True),
            'propagate_to_parents': data.get('propagate_to_parents', True),
            'created_by': user_id
        }
        
        rule_id = service.create_rule(rule_data)
        
        return jsonify({
            'success': True,
            'data': {'id': rule_id},
            'message': '权限规则创建成功'
        }), 201
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] create-permission-rule-v2 error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_v2_bp.route('/<int:rule_id>', methods=['PUT'])
@login_required
def update_permission_rule_v2(rule_id):
    """更新权限规则"""
    try:
        from meta.services.condition_permission_service import ConditionPermissionService
        from meta.core.bo_framework import bo_framework
        
        service = ConditionPermissionService(bo_framework._data_source)
        
        data = request.get_json(silent=True) or {}
        
        success = service.update_rule(rule_id, data)
        
        if success:
            return jsonify({'success': True, 'message': '权限规则更新成功'})
        return jsonify({'success': False, 'message': '更新失败'}), 400
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] update-permission-rule-v2 error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_v2_bp.route('/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_permission_rule_v2(rule_id):
    """删除权限规则"""
    try:
        from meta.services.condition_permission_service import ConditionPermissionService
        from meta.core.bo_framework import bo_framework
        
        service = ConditionPermissionService(bo_framework._data_source)
        
        success = service.delete_rule(rule_id)
        
        if success:
            return jsonify({'success': True, 'message': '权限规则删除成功'})
        return jsonify({'success': False, 'message': '删除失败'}), 400
    except Exception as e:
        import traceback
        logger.error(f"[bo_api] delete-permission-rule-v2 error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] [NEW] v1.2 / FR-2.2 / FR-2.3: OpenAPI 工具函数（被 FR-2.4 全量端点调用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_TYPE_MAP = {
    'string': 'string', 'text': 'string', 'integer': 'integer',
    'float': 'number', 'boolean': 'boolean', 'date': 'string',
    'datetime': 'string', 'json': 'object',
}


def _map_field_type(field_type) -> str:
    """将内部字段类型映射为 OpenAPI/JSON Schema 类型（兼容 enum 和 str）"""
    # 兼容 FieldType enum（.value / .name）和 str
    if hasattr(field_type, 'value'):
        field_type = field_type.value
    return _TYPE_MAP.get(str(field_type), 'string')


def _generate_bo_schema(meta_object) -> dict:
    """
    [DECORATIVE] [NEW] v1.2 / FR-2.3: 将 MetaObject 转换为 OpenAPI components/schemas 子对象

    防御: 用 getattr(field, 'xxx', None) 处理字段可能缺失的属性
    """
    properties = {}
    required = []
    for field in meta_object.fields:
        # MetaField 用 .field_type（FieldType enum），不是 .type
        field_type = getattr(field, 'field_type', None) or getattr(field, 'type', None)
        prop = {"type": _map_field_type(field_type)}
        if getattr(field, 'description', None):
            prop["description"] = field.description
        if getattr(field, 'enum_values', None):
            # [DECORATIVE] [NEW] v1.2 / bug #4 fix: 兼容 enum_values 元素可能是 str 或 dict
            enum_list = []
            for v in field.enum_values:
                if isinstance(v, dict):
                    enum_list.append(v.get('value'))
                else:
                    enum_list.append(v)  # 兼容 str / int
            if enum_list:
                prop["enum"] = enum_list
        # ui 可能是 dict 或 UIAnnotation 对象
        ui = getattr(field, 'ui', None)
        if isinstance(ui, dict):
            relation = ui.get('relation')
            display_field = ui.get('display_field')
        else:
            relation = getattr(ui, 'relation', None) if ui else None
            display_field = getattr(ui, 'display_field', None) if ui else None
        if relation:
            prop["x-relation"] = relation
            prop["x-display-field"] = display_field
        properties[field.id] = prop
        if field.required:
            required.append(field.id)
    return {
        "type": "object",
        "properties": properties,
        "required": required or None,
    }


def _generate_bo_crud_paths(meta_objects) -> dict:
    """
    [DECORATIVE] [NEW] v1.2 / FR-2.2: 为每个 BO 类型生成 7 个标准 CRUD 端点的 OpenAPI path 描述

    端点:
    - GET    /api/v2/bo/{type}            列表
    - POST   /api/v2/bo/{type}            创建
    - GET    /api/v2/bo/{type}/{id}       详情
    - PUT    /api/v2/bo/{type}/{id}       更新
    - DELETE /api/v2/bo/{type}/{id}       删除
    - POST   /api/v2/bo/{type}/deep       深度插入
    - POST   /api/v2/bo/{type}/batch-delete  批量删除
    """
    paths = {}
    for obj in meta_objects:
        if not getattr(obj, 'table_name', None):
            continue
        type_name = obj.id
        base = f'/api/v2/bo/{type_name}'
        type_tag = f'BO/{type_name}'

        paths[base] = {
            'get': {
                'operationId': f'bo_{type_name}_list',
                'summary': f'查询 {getattr(obj, "display_name", None) or type_name} 列表',
                'tags': [type_tag],
                'parameters': [
                    {'name': 'page', 'in': 'query', 'schema': {'type': 'integer', 'default': 1}},
                    {'name': 'page_size', 'in': 'query', 'schema': {'type': 'integer', 'default': 20}},
                    {'name': 'order_by', 'in': 'query', 'schema': {'type': 'string'}},
                    {'name': 'search', 'in': 'query', 'schema': {'type': 'string'}},
                ],
                'responses': {
                    '200': {'description': '列表数据', 'content': {'application/json': {'schema': {'type': 'object', 'properties': {'items': {'type': 'array'}, 'total': {'type': 'integer'}}}}}}
                },
            },
            'post': {
                'operationId': f'bo_{type_name}_create',
                'summary': f'创建 {getattr(obj, "display_name", None) or type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {
                        'application/json': {
                            'schema': {'$ref': f'#/components/schemas/{type_name}'}
                        }
                    }
                },
                'responses': {
                    '201': {'description': '已创建'},
                    '400': {'description': '参数错误'},
                },
            },
        }
        paths[f'{base}/{{id}}'] = {
            'get': {
                'operationId': f'bo_{type_name}_get',
                'summary': f'获取 {type_name} 详情',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'responses': {
                    '200': {'description': '详情数据', 'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}},
                    '404': {'description': '未找到'},
                },
            },
            'put': {
                'operationId': f'bo_{type_name}_update',
                'summary': f'更新 {type_name}',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'requestBody': {
                    'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}
                },
                'responses': {
                    '200': {'description': '已更新'},
                    '400': {'description': '参数错误'},
                    '404': {'description': '未找到'},
                },
            },
            'delete': {
                'operationId': f'bo_{type_name}_delete',
                'summary': f'删除 {type_name}',
                'tags': [type_tag],
                'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'responses': {
                    '204': {'description': '已删除'},
                    '404': {'description': '未找到'},
                },
            },
        }
        paths[f'{base}/deep'] = {
            'post': {
                'operationId': f'bo_{type_name}_deep_create',
                'summary': f'深度插入 {type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {'application/json': {'schema': {'$ref': f'#/components/schemas/{type_name}'}}}
                },
                'responses': {
                    '201': {'description': '已深度插入'},
                },
            }
        }
        paths[f'{base}/batch-delete'] = {
            'post': {
                'operationId': f'bo_{type_name}_batch_delete',
                'summary': f'批量删除 {type_name}',
                'tags': [type_tag],
                'requestBody': {
                    'content': {'application/json': {'schema': {
                        'type': 'object',
                        'properties': {'ids': {'type': 'array', 'items': {'type': 'string'}}}
                    }}}
                },
                'responses': {
                    '200': {'description': '已批量删除'},
                },
            }
        }
    return paths

