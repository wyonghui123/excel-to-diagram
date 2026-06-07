# -*- coding: utf-8 -*-
"""
用户管理API - 基于BOFramework重构版本

使用元数据驱动的BOFramework实现统一的CRUD操作和审计日志。
"""

import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from meta.services.auth_middleware import login_required, require_permission, get_current_user, is_admin
from meta.services.permission_service import PermissionService
from meta.services.auth_provider import _hash_password_pbdkdf2
from meta.services.data_permission_service import DataPermissionService
from meta.services.user_group_service import UserGroupService
from meta.services.audit_interceptor import AuditInterceptor as SvcAuditInterceptor
from meta.core.bo_framework import BOFramework
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.interceptors.context_interceptor import ContextInterceptor
from meta.core.datasource import get_data_source
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__, url_prefix='/api/v1/users')

_data_source = None
_bo_framework = None
_perm_service = None
_data_perm_service = None
_user_group_service = None
_svc_audit_interceptor = None


def init_user_services(data_source=None):
    """初始化用户服务"""
    global _data_source, _perm_service, _data_perm_service, _user_group_service, _svc_audit_interceptor
    
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)
    
    _perm_service = PermissionService(_data_source)
    _data_perm_service = DataPermissionService(_data_source)
    _user_group_service = UserGroupService(_data_source)
    _svc_audit_interceptor = SvcAuditInterceptor(_data_source)


def _get_bo_framework():
    """获取全局 BOFramework 实例（在server.py中初始化）"""
    from meta.core.bo_framework import bo_framework
    return bo_framework


def _get_perm_service():
    """获取权限服务实例"""
    if _perm_service is None:
        init_user_services()
    return _perm_service


def _get_data_perm_service():
    """获取数据权限服务实例"""
    if _data_perm_service is None:
        init_user_services()
    return _data_perm_service


def _get_user_group_service():
    """获取用户组服务实例"""
    if _user_group_service is None:
        init_user_services()
    return _user_group_service


def _get_svc_audit_interceptor():
    """获取审计日志拦截器实例"""
    if _svc_audit_interceptor is None:
        init_user_services()
    return _svc_audit_interceptor


def _set_user_context():
    """设置用户上下文"""
    current_user = get_current_user()
    bo = _get_bo_framework()
    bo.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get('display_name', current_user.get('username', 'unknown')),
        ip_address=request.remote_addr,
    )


@user_bp.route('', methods=['GET'])
@login_required
def list_users():
    """列出用户（带权限过滤）"""
    current_user = get_current_user()
    user_id = current_user.get('user_id')
    
    has_all_permission = is_admin()
    has_group_permission = _get_perm_service().has_permission(user_id, 'user:manage:group')
    
    if not has_all_permission and not has_group_permission:
        return jsonify({'success': False, 'message': '需要用户管理权限'}), 403

    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    keyword = request.args.get('keyword', '').strip()
    group_id = request.args.get('group_id', type=int)

    conditions = []
    params = []

    if keyword:
        conditions.append("(username LIKE ? OR display_name LIKE ? OR email LIKE ?)")
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw])

    if group_id:
        conditions.append("id IN (SELECT user_id FROM user_group_members WHERE group_id = ?)")
        params.append(group_id)

    if not has_all_permission and has_group_permission:
        manageable_user_ids = _get_user_group_service().get_manageable_users(user_id, has_all_permission=False)
        if not manageable_user_ids:
            return jsonify({
                'success': True,
                'data': [],
                'total': 0,
                'page': page,
                'page_size': page_size,
            })
        placeholders = ','.join(['?' for _ in manageable_user_ids])
        conditions.append(f"id IN ({placeholders})")
        params.extend(manageable_user_ids)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    count_sql = f"SELECT COUNT(*) FROM users WHERE {where_clause}"
    cursor = _data_source.execute(count_sql, tuple(params))
    total = cursor.fetchone()[0]

    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT id, username, email, display_name, status, sso_provider, last_login_at, created_at
        FROM users WHERE {where_clause}
        ORDER BY id
        LIMIT ? OFFSET ?
    """
    cursor = _data_source.execute(data_sql, tuple(params + [page_size, offset]))
    columns = [desc[0] for desc in cursor.description]
    users = [dict(zip(columns, row)) for row in cursor.fetchall()]

    for u in users:
        u['roles'] = _get_perm_service().get_user_roles(u['id'])

    return jsonify({
        'success': True,
        'data': users,
        'total': total,
        'page': page,
        'page_size': page_size,
    })


@user_bp.route('', methods=['POST'])
@login_required
def create_user():
    """创建用户"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    email = data.get('email', '').strip()
    display_name = data.get('display_name', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码长度不能少于6位'}), 400

    cursor = _data_source.execute("SELECT id FROM users WHERE username = ?", [username])
    if cursor.fetchone():
        return jsonify({'success': False, 'message': '用户名已存在'}), 400

    password_hash = _hash_password_pbdkdf2(password)

    _set_user_context()
    bo = _get_bo_framework()
    
    with bo.transaction():
        result = bo.create('user', {
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'display_name': display_name or username,
            'status': 'active',
        })
        
        if not result.success:
            return jsonify({'success': False, 'message': result.message}), 400
        
        user_id = result.data['id']

        role_ids = data.get('role_ids', [])
        for role_id in role_ids:
            _get_perm_service().assign_role(user_id, role_id)

    return jsonify({
        'success': True,
        'data': {'id': user_id, 'username': username},
        'message': '用户创建成功',
    }), 201


@user_bp.route('/me', methods=['GET'])
@login_required
def get_current_user_profile():
    """获取当前用户个人信息"""
    current = get_current_user()
    user_id = current.get('user_id')

    _set_user_context()
    bo = _get_bo_framework()
    
    result = bo.read('user', user_id)
    
    if not result.success:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    user = result.data
    user['roles'] = _get_perm_service().get_user_roles(user_id)

    return jsonify({'success': True, 'data': user})


@user_bp.route('/me', methods=['PUT'])
@login_required
def update_current_user_profile():
    """更新当前用户个人信息及偏好设置"""
    current = get_current_user()
    user_id = current.get('user_id')
    data = request.get_json(silent=True) or {}

    profile_fields = ['display_name', 'email']
    preference_fields = ['locale', 'timezone', 'date_style', 'time_style', 'hour_cycle']
    allowed_fields = profile_fields + preference_fields
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        return jsonify({'success': False, 'message': '没有可更新的字段'}), 400

    _set_user_context()
    bo = _get_bo_framework()
    
    result = bo.update('user', user_id, update_data)
    
    if not result.success:
        return jsonify({'success': False, 'message': result.message}), 400

    return jsonify({'success': True, 'message': '个人信息更新成功'})


@user_bp.route('/<int:user_id>', methods=['GET'])
@login_required
def get_user(user_id):
    """获取用户详情"""
    try:
        if not is_admin() and get_current_user().get('user_id') != user_id:
            return jsonify({'success': False, 'message': '无权查看'}), 403

        _set_user_context()
        bo = _get_bo_framework()
        
        result = bo.read('user', user_id)
        
        if not result.success:
            return jsonify({'success': False, 'message': '用户不存在'}), 404

        user = result.data
        user['roles'] = _get_perm_service().get_user_roles(user_id)
        user['permissions'] = _get_perm_service().get_user_permissions(user_id)
        user['groups'] = _get_user_group_service().get_user_groups(user_id)
        user['data_permissions'] = _get_data_perm_service().get_all_user_data_permissions_with_groups(user_id)

        return jsonify({'success': True, 'data': user})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'获取用户详情失败: {str(e)}'}), 500


@user_bp.route('/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    """更新用户"""
    current_user = get_current_user()
    operator_id = current_user.get('user_id')
    
    has_all_permission = is_admin()
    has_group_permission = _get_perm_service().has_permission(operator_id, 'user:manage:group')
    
    is_self = operator_id == user_id
    
    if not has_all_permission and not has_group_permission and not is_self:
        return jsonify({'success': False, 'message': '无权修改'}), 403
    
    if not has_all_permission and not is_self:
        if not _get_user_group_service().can_manage_user(operator_id, user_id, has_all_permission=False):
            return jsonify({'success': False, 'message': '无权修改该用户'}), 403

    data = request.get_json(silent=True) or {}

    update_data = {}
    for field in ['email', 'display_name', 'status']:
        if field in data:
            update_data[field] = data[field]

    _set_user_context()
    bo = _get_bo_framework()
    
    if update_data or ((has_all_permission or has_group_permission) and 'role_ids' in data):
        with bo.transaction():
            if update_data:
                result = bo.update('user', user_id, update_data)
                
                if not result.success:
                    return jsonify({'success': False, 'message': result.message}), 400

            if (has_all_permission or has_group_permission) and 'role_ids' in data:
                if not has_all_permission:
                    if not _get_user_group_service().can_manage_user(operator_id, user_id, has_all_permission=False):
                        return jsonify({'success': False, 'message': '无权修改该用户角色'}), 403
                
                current_roles = {r['id'] for r in _get_perm_service().get_user_roles(user_id)}
                new_roles = set(data['role_ids'])

                added_roles = new_roles - current_roles
                removed_roles = current_roles - new_roles

                for role_id in added_roles:
                    if not _get_data_perm_service().can_assign_role(operator_id, role_id):
                        return jsonify({'success': False, 'message': '无权分配该角色，可能导致权限提升'}), 403
                    _get_perm_service().assign_role(user_id, role_id)
                    _get_svc_audit_interceptor().log_associate(
                        object_type='user',
                        object_id=user_id,
                        tgt_type='role',
                        tgt_id=role_id,
                        association_name='roles',
                        user_id=str(operator_id) if operator_id else None,
                        user_name=operator_name,
                    )
                for role_id in removed_roles:
                    _get_perm_service().remove_role(user_id, role_id)
                    _get_svc_audit_interceptor().log_dissociate(
                        object_type='user',
                        object_id=user_id,
                        tgt_type='role',
                        tgt_id=role_id,
                        association_name='roles',
                        user_id=str(operator_id) if operator_id else None,
                        user_name=operator_name,
                    )

    return jsonify({'success': True, 'message': '用户更新成功'})


@user_bp.route('/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    """删除用户"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403
    
    _set_user_context()
    bo = _get_bo_framework()
    
    result = bo.delete('user', user_id)
    
    if not result.success:
        if '不存在' in result.message:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        return jsonify({'success': False, 'message': result.message}), 400

    return jsonify({'success': True, 'message': '用户删除成功'})


@user_bp.route('/batch-delete', methods=['POST'])
@login_required
def batch_delete_users():
    """批量删除用户"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403
    
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'success': False, 'message': '请选择要删除的记录'}), 400
    
    _set_user_context()
    bo = _get_bo_framework()
    
    try:
        deleted_count = 0
        errors = []
        
        for user_id in ids:
            result = bo.delete('user', user_id)
            if result.success:
                deleted_count += 1
            else:
                errors.append(f'ID {user_id}: {result.message}')
        
        if deleted_count > 0:
            return jsonify({
                'success': True,
                'data': {'count': deleted_count},
                'message': f'成功删除 {deleted_count} 条记录' + (f'，失败 {len(errors)} 条' if errors else ''),
                'errors': errors if errors else None
            })
        else:
            return jsonify({
                'success': False,
                'message': '删除失败',
                'errors': errors
            }), 400
    except Exception as e:
        logger.error(f'批量删除用户失败: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500


@user_bp.route('/<int:user_id>/reset-password', methods=['POST'])
@login_required
def reset_password(user_id):
    """重置密码"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password', '')

    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码长度不能少于6位'}), 400

    cursor = _data_source.execute(
        "SELECT username FROM users WHERE id = ?", [user_id]
    )
    row = cursor.fetchone()
    if not row:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    password_hash = _hash_password_pbdkdf2(new_password)

    _set_user_context()
    with _data_source.transaction():
        _data_source.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
            [password_hash, user_id]
        )

    current_user = get_current_user()
    operator_name = current_user.get('display_name', current_user.get('username', 'unknown'))
    operator_id = current_user.get('user_id')

    ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in ip_addr:
        ip_addr = ip_addr.split(',')[0].strip()

    _data_source.execute(
        """INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name,
           field_name, new_data, ip_address, created_at, log_category, log_level)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'security', 'INFO')""",
        ['user', user_id, 'RESET_PASSWORD', operator_id, operator_name,
         'password_hash', f'reset by {operator_name}', ip_addr]
    )

    return jsonify({'success': True, 'message': '密码重置成功，用户下次登录需修改密码'})


@user_bp.route('/batch-data-permissions', methods=['POST'])
@login_required
def batch_add_user_data_permissions():
    """批量添加用户数据权限"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        resource_type = data.get('resource_type')
        resource_id = data.get('resource_id')
        permission_level = data.get('permission_level', 'read')
        inherit_to_children = data.get('inherit_to_children', True)

        if not user_ids or not resource_type or not resource_id:
            return jsonify({'success': False, 'message': 'user_ids, resource_type, resource_id are required'}), 400

        result = _get_data_perm_service().add_batch_user_data_permissions(
            user_ids, resource_type, resource_id, permission_level, inherit_to_children
        )

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@user_bp.route('/self', methods=['GET'])
@login_required
def get_current_user_detail():
    """获取当前用户详情"""
    user_id = g.current_user['user_id']
    
    _set_user_context()
    bo = _get_bo_framework()
    
    result = bo.read('user', user_id)
    
    if not result.success:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    user = result.data
    user['roles'] = _get_perm_service().get_user_roles(user_id)
    user['permissions'] = _get_perm_service().get_user_permissions(user_id)

    return jsonify({'success': True, 'data': user})


@user_bp.route('/self', methods=['PUT'])
@login_required
def update_user_self():
    """更新当前用户个人信息及偏好设置（备用路由）"""
    current = get_current_user()
    user_id = current.get('user_id')
    data = request.get_json(silent=True) or {}

    profile_fields = ['display_name', 'email']
    preference_fields = ['locale', 'timezone', 'date_style', 'time_style', 'hour_cycle']
    allowed_fields = profile_fields + preference_fields
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        return jsonify({'success': False, 'message': '没有可更新的字段'}), 400

    _set_user_context()
    bo = _get_bo_framework()

    result = bo.update('user', user_id, update_data)

    if not result.success:
        return jsonify({'success': False, 'message': result.message}), 400

    return jsonify({'success': True, 'message': '个人信息更新成功'})


@user_bp.route('/<int:user_id>/menus', methods=['GET'])
@login_required
def get_user_menus(user_id):
    """获取指定用户的菜单权限"""
    try:
        ds = _data_source
        
        cursor = ds.execute("SELECT id, username FROM users WHERE id = ?", [user_id])
        user = cursor.fetchone()
        if not user:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        cursor = ds.execute("""
            SELECT DISTINCT mp.menu_code, mp.menu_name, mp.menu_path, mp.icon
            FROM menu_permissions mp
            JOIN role_menu_permissions rmp ON mp.menu_code = rmp.menu_code
            JOIN group_roles gr ON rmp.role_id = gr.role_id
            JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
            AND mp.is_active = 1
            ORDER BY mp.sort_order
        """, [user_id])
        
        columns = [desc[0] for desc in cursor.description]
        menus = []
        for row in cursor.fetchall():
            menu = dict(zip(columns, row))
            menu['assigned'] = True
            menus.append(menu)
        
        return jsonify({
            'success': True,
            'data': menus
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@user_bp.route('/<int:user_id>/logs', methods=['GET'])
@login_required
def get_user_logs(user_id):
    """获取指定用户的操作日志"""
    try:
        ds = _data_source
        
        cursor = ds.execute("SELECT id, username FROM users WHERE id = ?", [user_id])
        user = cursor.fetchone()
        if not user:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        
        offset = (page - 1) * page_size
        
        cursor = ds.execute("""
            SELECT * FROM audit_logs
            WHERE object_type = 'user' AND object_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, [user_id, page_size, offset])
        
        columns = [desc[0] for desc in cursor.description]
        logs = []
        for row in cursor.fetchall():
            logs.append(dict(zip(columns, row)))
        
        cursor = ds.execute(
            "SELECT COUNT(*) as total FROM audit_logs WHERE object_type = 'user' AND object_id = ?",
            [user_id]
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
