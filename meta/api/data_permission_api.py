# -*- coding: utf-8 -*-
"""
数据权限管理API
"""

from flask import Blueprint, request, jsonify, g
from meta.services.auth_middleware import login_required, is_admin
from meta.services.data_permission_service import DataPermissionService
from meta.core.datasource import get_data_source
import os

data_perm_bp = Blueprint('data_permission', __name__, url_prefix='/api/v1/data-permissions')

_data_source = None
_data_perm_service = None


def init_data_perm_services(data_source=None):
    global _data_source, _data_perm_service
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    _data_perm_service = DataPermissionService(_data_source)


def _get_data_perm_service():
    if _data_perm_service is None:
        init_data_perm_services()
    return _data_perm_service


@data_perm_bp.route('', methods=['GET'])
@login_required
def list_data_permissions():
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    user_id = request.args.get('user_id', type=int)
    resource_type = request.args.get('resource_type', '').strip()

    if user_id:
        perms = _get_data_perm_service().get_user_data_permissions(user_id)
    else:
        cursor = _data_source.execute(
            "SELECT dp.*, u.username FROM data_permissions dp LEFT JOIN users u ON dp.user_id = u.id ORDER BY dp.user_id, dp.resource_type"
        )
        columns = [desc[0] for desc in cursor.description]
        perms = [dict(zip(columns, row)) for row in cursor.fetchall()]

    if resource_type:
        perms = [p for p in perms if p.get('resource_type') == resource_type]

    for perm in perms:
        perm['resource_name'] = _get_resource_name(
            perm.get('resource_type'), perm.get('resource_id')
        )

    return jsonify({'success': True, 'data': perms})


@data_perm_bp.route('', methods=['POST'])
@login_required
def add_data_permission():
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    resource_type = data.get('resource_type', '').strip()
    resource_id = data.get('resource_id')
    permission_level = data.get('permission_level', 'read')
    inherit_to_children = data.get('inherit_to_children', True)

    if not user_id or not resource_type or resource_id is None:
        return jsonify({'success': False, 'message': 'user_id, resource_type, resource_id 不能为空'}), 400

    valid_levels = ['read', 'write', 'admin']
    if permission_level not in valid_levels:
        return jsonify({'success': False, 'message': f'permission_level 必须是: {", ".join(valid_levels)}'}), 400

    valid_types = ['domain', 'sub_domain', 'service_module', 'business_object']
    if resource_type not in valid_types:
        return jsonify({'success': False, 'message': f'resource_type 必须是: {", ".join(valid_types)}'}), 400

    cursor = _data_source.execute("SELECT id FROM users WHERE id = ?", [user_id])
    if not cursor.fetchone():
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    perm_id = _get_data_perm_service().add_data_permission(
        user_id, resource_type, resource_id, permission_level, inherit_to_children
    )
    _data_source.commit()

    if perm_id is None:
        return jsonify({'success': False, 'message': '添加数据权限失败'}), 400

    return jsonify({
        'success': True,
        'data': {'id': perm_id},
        'message': '数据权限添加成功',
    }), 201


@data_perm_bp.route('/<int:perm_id>', methods=['DELETE'])
@login_required
def delete_data_permission(perm_id):
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    success = _get_data_perm_service().remove_data_permission(perm_id)
    _data_source.commit()

    if not success:
        return jsonify({'success': False, 'message': '删除数据权限失败'}), 400

    return jsonify({'success': True, 'message': '数据权限删除成功'})


@data_perm_bp.route('/batch', methods=['POST'])
@login_required
def batch_add_data_permissions():
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    permissions = data.get('permissions', [])

    if not user_id or not permissions:
        return jsonify({'success': False, 'message': 'user_id 和 permissions 不能为空'}), 400

    results = []
    for perm in permissions:
        resource_type = perm.get('resource_type', '').strip()
        resource_id = perm.get('resource_id')
        permission_level = perm.get('permission_level', 'read')
        inherit_to_children = perm.get('inherit_to_children', True)

        perm_id = _get_data_perm_service().add_data_permission(
            user_id, resource_type, resource_id, permission_level, inherit_to_children
        )
        results.append({
            'resource_type': resource_type,
            'resource_id': resource_id,
            'success': perm_id is not None,
            'id': perm_id,
        })

    _data_source.commit()

    return jsonify({
        'success': True,
        'data': results,
        'message': f'批量添加完成，成功 {sum(1 for r in results if r["success"])} 条',
    })


@data_perm_bp.route('/effective', methods=['GET'])
@login_required
def get_effective_permissions():
    if not is_admin():
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            from meta.services.auth_middleware import get_current_user
            current = get_current_user()
            user_id = current.get('user_id') if current else None
    else:
        user_id = request.args.get('user_id', type=int)

    if not user_id:
        return jsonify({'success': False, 'message': 'user_id 不能为空'}), 400

    resource_type = request.args.get('resource_type', 'business_object').strip()
    allowed_ids = _get_data_perm_service().get_allowed_resource_ids(user_id, resource_type)

    return jsonify({
        'success': True,
        'data': {
            'user_id': user_id,
            'resource_type': resource_type,
            'allowed_ids': allowed_ids,
            'count': len(allowed_ids),
        },
    })


def _get_resource_name(resource_type, resource_id):
    if not resource_type or resource_id is None:
        return None
    from meta.core.models import registry
    meta_obj = registry.get(resource_type)
    if not meta_obj:
        return None
    try:
        table = meta_obj.table_name
        cursor = _data_source.execute(f"SELECT name FROM {table} WHERE id = ?", [resource_id])
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception:
        return None


@data_perm_bp.route('/self', methods=['GET'])
@login_required
def get_self_data_permissions():
    """获取当前用户的数据权限（自身操作，无需权限）"""
    user_id = g.current_user['user_id']
    perms = _get_data_perm_service().get_user_data_permissions(user_id)

    for perm in perms:
        perm['resource_name'] = _get_resource_name(
            perm.get('resource_type'), perm.get('resource_id')
        )

    return jsonify({'success': True, 'data': perms})
