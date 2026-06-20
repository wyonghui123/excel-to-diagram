from flask import Blueprint, request, jsonify
from meta.services.cascade_service import get_type_order
from meta.core.models import registry
from meta.core.datasource import get_data_source
from meta.services.auth_middleware import login_required
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

annotation_bp = Blueprint('annotation', __name__, url_prefix='/api/v1')

_data_source = None
_manage_service = None


def init_annotation_services(data_source=None, manage_service=None):
    global _data_source, _manage_service
    _data_source = data_source or get_data_source()
    _manage_service = manage_service


def _get_annotation_category_labels():
    global _data_source
    try:
        if _data_source is None:
            init_annotation_services()
        ds = _data_source
        sql = "SELECT code, name FROM enum_values WHERE enum_type_id = 'annotation_category' AND is_active = 1"
        cursor = ds.execute(sql)
        rows = cursor.fetchall()
        if rows:
            return {row[0]: row[1] for row in rows}
    except Exception:
        pass

    annotation_meta = registry.get('annotation')
    if annotation_meta:
        for f in annotation_meta.fields:
            if f.id == 'category' and hasattr(f, 'ui') and f.ui and f.ui.options:
                return {opt.get('value', ''): opt.get('label', opt.get('value', ''))
                        for opt in f.ui.options if opt.get('value')}
    return {
        'important': '[SYMBOL] 重要',
        'warning': '[WARNING] 警告',
        'info': 'ℹ️ 信息',
        'tip': '[DECORATIVE] 提示',
    }


def _get_valid_annotation_categories():
    global _data_source
    try:
        if _data_source is None:
            init_annotation_services()
        ds = _data_source
        sql = "SELECT code FROM enum_values WHERE enum_type_id = 'annotation_category' AND is_active = 1"
        cursor = ds.execute(sql)
        rows = cursor.fetchall()
        if rows:
            return [row[0] for row in rows]
    except Exception:
        pass

    annotation_meta = registry.get('annotation')
    if annotation_meta:
        for f in annotation_meta.fields:
            if f.id == 'category' and hasattr(f, 'ui') and f.ui and f.ui.options:
                return [opt.get('value', '') for opt in f.ui.options if opt.get('value')]

    return ['important', 'warning', 'info', 'tip']




@annotation_bp.route('/annotations/by-target', methods=['GET'])
def list_annotations_by_target():
    if _data_source is None:
        init_annotation_services()
    ds = _data_source

    target_type = request.args.get('target_type')
    target_id = request.args.get('target_id', type=int)

    if not target_type or not target_id:
        return jsonify({
            'success': False,
            'message': '目标类型和目标 ID 不能为空',
        }), 400

    valid_target_types = get_type_order() + ['relationship']
    if target_type not in valid_target_types:
        return jsonify({
            'success': False,
            'message': f'Invalid target_type. Must be one of: {", ".join(valid_target_types)}',
        }), 400

    sql = """
        SELECT * FROM annotations
        WHERE target_type = ? AND target_id = ?
        ORDER BY created_at DESC
    """
    cursor = ds.execute(sql, (target_type, target_id))
    columns = [desc[0] for desc in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]

    category_labels = _get_annotation_category_labels()

    for item in data:
        item['category_label'] = category_labels.get(item.get('category'), item.get('category', ''))

    return jsonify({
        'success': True,
        'data': data,
        'total': len(data),
    })


@annotation_bp.route('/annotations/<int:annotation_id>', methods=['GET'])
@login_required
def get_annotation(annotation_id):
    if _data_source is None:
        init_annotation_services()
    ds = _data_source

    sql = "SELECT * FROM annotations WHERE id = ?"
    cursor = ds.execute(sql, (annotation_id,))
    row = cursor.fetchone()

    if not row:
        return jsonify({
            'success': False,
            'message': '标注不存在',
        }), 404

    columns = [desc[0] for desc in cursor.description]
    data = dict(zip(columns, row))

    category_labels = _get_annotation_category_labels()
    data['category_label'] = category_labels.get(data.get('category'), data.get('category', ''))

    return jsonify({
        'success': True,
        'data': data,
    })


def _set_audit_user_for_annotation():
    from flask import g, request
    from urllib.parse import unquote
    import os

    service = _manage_service
    if not service:
        return

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


@annotation_bp.route('/annotations', methods=['POST'])
@login_required
def create_annotation():
    from meta.services.manage_service import CreateRequest

    _set_audit_user_for_annotation()
    data = request.get_json(silent=True) or {}

    if not data.get('target_type') or not data.get('target_id'):
        return jsonify({
            'success': False,
            'message': '目标类型和目标 ID 不能为空',
        }), 400

    if isinstance(data.get('target_id'), str) and not str(data.get('target_id')).isdigit():
        return jsonify({
            'success': False,
            'message': '目标 ID 必须为有效数字',
        }), 400

    if not data.get('category'):
        data['category'] = 'info'

    if not data.get('content'):
        return jsonify({
            'success': False,
            'message': '内容不能为空',
        }), 400

    valid_target_types = get_type_order() + ['relationship']
    if data.get('target_type') not in valid_target_types:
        return jsonify({
            'success': False,
            'message': f'Invalid target_type. Must be one of: {", ".join(valid_target_types)}',
        }), 400

    valid_categories = _get_valid_annotation_categories()
    if data.get('category') not in valid_categories:
        return jsonify({
            'success': False,
            'message': f'Invalid category. Must be one of: {", ".join(valid_categories)}',
        }), 400

    data['created_at'] = datetime.now().isoformat()

    req = CreateRequest(
        object_type='annotation',
        data=data,
        skip_validation=True,
        skip_audit=False,
    )
    result = _manage_service.create(req)

    return jsonify({
        'success': result.success,
        'data': result.data,
        'message': result.message,
    }), 201 if result.success else 400


@annotation_bp.route('/annotations/<int:annotation_id>', methods=['PUT'])
def update_annotation(annotation_id):
    from meta.services.manage_service import UpdateRequest

    _set_audit_user_for_annotation()
    data = request.get_json(silent=True) or {}

    if data.get('category'):
        valid_categories = _get_valid_annotation_categories()
        if data['category'] not in valid_categories:
            return jsonify({
                'success': False,
                'message': f'Invalid category. Must be one of: {", ".join(valid_categories)}',
            }), 400

    req = UpdateRequest(
        object_type='annotation',
        id=annotation_id,
        data=data,
        skip_validation=True,
        skip_audit=False,
    )
    result = _manage_service.update(req)

    return jsonify({
        'success': result.success,
        'data': result.data,
        'message': result.message,
    }), 200 if result.success else 400


@annotation_bp.route('/annotations/<int:annotation_id>', methods=['DELETE'])
@login_required
def delete_annotation(annotation_id):
    from meta.services.manage_service import DeleteRequest

    _set_audit_user_for_annotation()

    req = DeleteRequest(
        object_type='annotation',
        id=annotation_id,
        force=True,
        cascade=False,
    )
    result = _manage_service.delete(req)

    return jsonify({
        'success': result.success,
        'message': result.message,
    }), 200 if result.success else 400


@annotation_bp.route('/annotations/category-stats', methods=['GET'])
@login_required
def get_annotation_category_stats():
    if _data_source is None:
        init_annotation_services()
    ds = _data_source

    target_type = request.args.get('target_type', 'business_object')
    is_active = request.args.get('is_active', '')

    try:
        active_categories = None
        if is_active.lower() == 'true':
            cursor = ds.execute(
                "SELECT code FROM enum_values WHERE enum_type_id = 'annotation_category' AND is_active = 1"
            )
            active_categories = [row[0] for row in cursor.fetchall()]

        sql = """
            SELECT category, COUNT(*) as count
            FROM annotations
            WHERE target_type = ?
            GROUP BY category
        """
        cursor = ds.execute(sql, (target_type,))
        rows = cursor.fetchall()

        stats = {}
        for row in rows:
            category = row[0]
            if active_categories is not None and category not in active_categories:
                continue
            stats[category] = row[1]

        return jsonify({
            'success': True,
            'data': stats,
        })
    except Exception as e:
        logger.error(f"获取备注分类统计失败: {e}")
        return jsonify({
            'success': True,
            'data': {},
        })
