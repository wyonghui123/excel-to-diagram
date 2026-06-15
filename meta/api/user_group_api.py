# -*- coding: utf-8 -*-
"""
用户组 API - 基于BOFramework重构版本

使用元数据驱动的BOFramework实现统一的CRUD操作和审计日志。
"""

from flask import Blueprint, request, jsonify, g
from meta.services.auth_middleware import login_required, require_permission, is_admin, get_current_user
from meta.services.user_group_service import UserGroupService
from meta.services.data_permission_service import DataPermissionService
from meta.core.bo_framework import BOFramework
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.interceptors.context_interceptor import ContextInterceptor
from meta.core.datasource import get_data_source
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir, registry
import os

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or not is_admin(user):
            return jsonify({'success': False, 'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated

user_group_bp = Blueprint('user_group', __name__, url_prefix='/api/v1')

_data_source = None
_bo_framework = None
_group_service = None
_perm_service = None


def init_user_group_services(data_source=None):
    """初始化用户组服务"""
    global _data_source, _group_service, _perm_service
    
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)
    
    _group_service = UserGroupService(_data_source)
    _perm_service = DataPermissionService(_data_source)


def _get_bo_framework():
    """获取全局 BOFramework 实例（在server.py中初始化）"""
    from meta.core.bo_framework import bo_framework
    return bo_framework


def _get_group_service():
    """获取用户组服务实例"""
    if _group_service is None:
        init_user_group_services()
    return _group_service


def _get_perm_service():
    """获取数据权限服务实例"""
    if _perm_service is None:
        init_user_group_services()
    return _perm_service


def _set_user_context():
    """设置用户上下文"""
    current_user = get_current_user()
    bo = _get_bo_framework()
    bo.set_user_context(
        user_id=current_user.get('user_id') if current_user else None,
        user_name=current_user.get('display_name', current_user.get('username', 'unknown')) if current_user else 'unknown',
    )


# v1.4 P8 Sunset (2026-06-05): 已移除 4 个主表 CRUD 端点
#   - GET /user-groups: 改用 v2/bo/user_group 端点
#   - POST /user-groups: 改用 v2/bo/user_group 端点
#   - GET /user-groups/<id>: 改用 v2/bo/user_group/<id> 端点
#   - PUT /user-groups/<id>: 改用 v2/bo/user_group/<id> 端点
#   - DELETE /user-groups/<id>: 改用 v2/bo/user_group/<id> DELETE 端点
#
# 保留的 v1 业务关系端点（业务路径）：
#   - /user-groups/<id>/members
#   - /user-groups/<id>/data-permissions
#   - /user-groups/<id>/roles
#   - /user-groups/<id>/logs
#   - /system/migrate-group-permissions-to-roles

# 保留 v1/user-groups/<id> 业务关系端点
# （移到下面以维持模块化结构）


@user_group_bp.route('/user-groups/<int:group_id>/members', methods=['GET'])
@login_required
@require_permission('user:read')
def get_group_members(group_id):
    """
    [已废弃] 获取用户组成员
    请使用 v2 API: GET /api/v2/bo/user_group/{group_id}/associations/members
    """
    import warnings
    warnings.warn(
        "此API已废弃，请使用 GET /api/v2/bo/user_group/{id}/associations/members",
        DeprecationWarning,
        stacklevel=2
    )
    try:
        service = _get_group_service()
        members = service.get_group_members(group_id)
        return jsonify({'success': True, 'data': members, '_deprecated': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/members', methods=['POST'])
@login_required
@require_permission('user:update')
def add_group_member(group_id):
    """
    [已废弃] 添加成员到用户组
    请使用 v2 API: POST /api/v2/bo/user_group/{group_id}/associations/members
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        user_id = data.get('user_id')
        is_manager = data.get('is_manager', False)

        if user_id:
            user_ids = [user_id]

        if not user_ids:
            return jsonify({'success': False, 'message': 'user_id is required'}), 400

        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()
        
        logger.info(f"[add_group_member] BOFramework instance: {bo}")
        logger.info(f"[add_group_member] Interceptors: {bo._interceptors}")
        
        added_count = 0
        for uid in user_ids:
            logger.info(f"[add_group_member] Calling bo.associate for user {uid}")
            result = bo.associate(
                src_type='user_group',
                src_id=group_id,
                tgt_type='user',
                tgt_id=uid,
                association_name='members'
            )
            
            logger.info(f"[add_group_member] Result: success={result.success}, message={result.message}")
            
            if result.success:
                added_count += 1

        return jsonify({'success': True, 'data': {'added_count': added_count}})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/members', methods=['PUT'])
@login_required
@require_permission('user:update')
def set_group_members(group_id):
    """增量更新用户组成员（只记录新增的成员）"""
    try:
        data = request.get_json()
        new_user_ids = set(data.get('user_ids', []))
        
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()

        with _data_source.transaction():
            cursor = _data_source.execute(
                "SELECT user_id FROM user_group_members WHERE group_id = ?",
                [group_id]
            )
            rows = cursor.fetchall()
            existing_user_ids = set(row[0] for row in rows)

            users_to_add = new_user_ids - existing_user_ids
            users_to_remove = existing_user_ids - new_user_ids

            removed_count = 0
            for uid in users_to_remove:
                result = bo.dissociate(
                    src_type='user_group',
                    src_id=group_id,
                    tgt_type='user',
                    tgt_id=uid,
                    association_name='members'
                )
                if result.success:
                    removed_count += 1

            added_count = 0
            for uid in users_to_add:
                result = bo.associate(
                    src_type='user_group',
                    src_id=group_id,
                    tgt_type='user',
                    tgt_id=uid,
                    association_name='members'
                )
                if result.success:
                    added_count += 1

        return jsonify({
            'success': True,
            'data': {
                'added_count': added_count,
                'removed_count': removed_count
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
@require_permission('user:update')
def remove_group_member(group_id, user_id):
    """从用户组移除成员"""
    try:
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()
        
        result = bo.dissociate(
            src_type='user_group',
            src_id=group_id,
            tgt_type='user',
            tgt_id=user_id,
            association_name='members'
        )
        
        if result.success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': result.message}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/data-permissions', methods=['GET'])
@login_required
@require_permission('user:read')
def get_group_data_permissions(group_id):
    """[已废弃] 获取用户组数据权限 - 建议通过角色关联获取权限"""
    import warnings
    warnings.warn(
        "直接用户组数据权限已废弃，请使用 /user-groups/{id}/roles 接口通过角色管理权限",
        DeprecationWarning, stacklevel=2
    )
    try:
        service = _get_perm_service()
        perms = service.get_group_data_permissions(group_id)
        return jsonify({'success': True, 'data': perms, '_deprecated': True,
                        '_hint': '建议使用 /user-groups/{id}/roles 接口通过角色间接分配数据权限'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/data-permissions', methods=['POST'])
@login_required
@require_permission('user:update')
def add_group_data_permission(group_id):
    """[已废弃] 为用户组添加数据权限 - 建议创建角色并关联到用户组"""
    import warnings
    warnings.warn(
        "直接用户组数据权限已废弃，请先创建角色配置数据权限，再将角色关联到用户组",
        DeprecationWarning, stacklevel=2
    )
    try:
        service = _get_perm_service()
        data = request.get_json()
        resource_type = data.get('resource_type')
        resource_id = data.get('resource_id')
        permission_level = data.get('permission_level', 'read')
        inherit_to_children = data.get('inherit_to_children', True)

        if not resource_type or not resource_id:
            return jsonify({'success': False, 'message': 'resource_type and resource_id are required'}), 400

        perm_id = service.add_group_data_permission(group_id, resource_type, resource_id, permission_level, inherit_to_children)
        if perm_id:
            return jsonify({'success': True, 'data': {'id': perm_id}, '_deprecated': True})
        return jsonify({'success': False, 'message': 'Failed to add permission'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/data-permissions/<int:perm_id>', methods=['DELETE'])
@login_required
@require_permission('user:update')
def remove_group_data_permission(group_id, perm_id):
    """[已废弃] 删除用户组数据权限"""
    import warnings
    warnings.warn("直接用户组数据权限已废弃", DeprecationWarning, stacklevel=2)
    try:
        service = _get_perm_service()
        success = service.remove_group_data_permission(perm_id)
        if success:
            return jsonify({'success': True, '_deprecated': True})
        return jsonify({'success': False, 'message': 'Failed to delete permission'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/roles', methods=['GET'])
@login_required
@require_permission('user:read')
def get_group_roles(group_id):
    """
    [已废弃] 获取用户组关联的角色列表
    请使用 v2 API: GET /api/v2/bo/user_group/{group_id}/associations/roles
    """
    import warnings
    warnings.warn(
        "此API已废弃，请使用 GET /api/v2/bo/user_group/{id}/associations/roles",
        DeprecationWarning,
        stacklevel=2
    )
    try:
        service = _get_group_service()
        roles = service.get_group_roles(group_id)
        return jsonify({'success': True, 'data': roles, '_deprecated': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/roles', methods=['PUT'])
@login_required
@require_permission('user:update')
def set_group_roles(group_id):
    """批量设置用户组角色（增量更新）"""
    try:
        data = request.get_json()
        new_role_ids = set(data.get('role_ids', []))
        
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()

        with _data_source.transaction():
            cursor = _data_source.execute(
                "SELECT role_id FROM group_roles WHERE group_id = ?",
                [group_id]
            )
            rows = cursor.fetchall()
            existing_role_ids = set(row[0] for row in rows)

            roles_to_add = new_role_ids - existing_role_ids
            roles_to_remove = existing_role_ids - new_role_ids

            removed_count = 0
            for rid in roles_to_remove:
                result = bo.dissociate(
                    src_type='user_group',
                    src_id=group_id,
                    tgt_type='role',
                    tgt_id=rid,
                    association_name='roles'
                )
                if result.success:
                    removed_count += 1

            added_count = 0
            for rid in roles_to_add:
                result = bo.associate(
                    src_type='user_group',
                    src_id=group_id,
                    tgt_type='role',
                    tgt_id=rid,
                    association_name='roles'
                )
                if result.success:
                    added_count += 1

        return jsonify({
            'success': True,
            'data': {
                'added_count': added_count,
                'removed_count': removed_count
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/roles/<int:role_id>', methods=['POST'])
@login_required
@require_permission('user:update')
def add_group_role(group_id, role_id):
    """为用户组添加单个角色"""
    try:
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()
        
        result = bo.associate(
            src_type='user_group',
            src_id=group_id,
            tgt_type='role',
            tgt_id=role_id,
            association_name='roles'
        )
        
        if result.success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': result.message}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/roles/<int:role_id>', methods=['DELETE'])
@login_required
@require_permission('user:update')
def remove_group_role(group_id, role_id):
    """从用户组移除角色"""
    try:
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()
        
        result = bo.dissociate(
            src_type='user_group',
            src_id=group_id,
            tgt_type='role',
            tgt_id=role_id,
            association_name='roles'
        )
        
        if result.success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': result.message}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/roles/available', methods=['GET'])
@login_required
@require_permission('user:read')
def get_available_roles_for_group(group_id):
    """获取可分配给该用户组的角色列表（未关联的）"""
    try:
        service = _get_group_service()
        roles = service.get_roles_not_in_group(group_id)
        return jsonify({'success': True, 'data': roles})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/system/migrate-group-permissions-to-roles', methods=['POST'])
@login_required
@admin_required
def migrate_group_permissions():
    """将旧的用户组直接数据权限迁移到基于角色的模型 [仅管理员]"""
    try:
        service = _get_group_service()
        migrated_count = service.migrate_group_data_permissions_to_roles()
        return jsonify({
            'success': True,
            'data': {'migrated_group_count': migrated_count},
            'message': f'成功迁移 {migrated_count} 个用户组的直接数据权限到对应角色'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_group_bp.route('/user-groups/<int:group_id>/logs', methods=['GET'])
@login_required
def get_user_group_logs(group_id):
    """获取指定用户组的操作日志"""
    try:
        cursor = _data_source.execute("SELECT id, name FROM user_groups WHERE id = ?", [group_id])
        group = cursor.fetchone()
        if not group:
            return jsonify({'success': False, 'message': '用户组不存在'}), 404

        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)

        offset = (page - 1) * page_size

        cursor = _data_source.execute("""
            SELECT * FROM audit_logs
            WHERE object_type = 'user_group' AND object_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, [group_id, page_size, offset])

        columns = [desc[0] for desc in cursor.description]
        logs = []
        for row in cursor.fetchall():
            logs.append(dict(zip(columns, row)))

        cursor = _data_source.execute(
            "SELECT COUNT(*) as total FROM audit_logs WHERE object_type = 'user_group' AND object_id = ?",
            [group_id]
        )
        total = cursor.fetchone()[0]

        return jsonify({
            'success': True,
            'data': logs,
            'total': total,
            'page': page,
            'page_size': page_size
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
