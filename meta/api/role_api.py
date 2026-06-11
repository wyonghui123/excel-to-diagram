# -*- coding: utf-8 -*-
"""
角色权限管理API - 基于BOFramework重构版本

使用元数据驱动的BOFramework实现统一的CRUD操作和审计日志。
"""

from flask import Blueprint, request, jsonify
from meta.services.auth_middleware import login_required, require_permission, is_admin, get_current_user
from meta.services.permission_service import PermissionService
from meta.services.condition_permission_service import ConditionPermissionService
from meta.services.association_service import AssociationService
from meta.core.bo_framework import BOFramework
from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
from meta.core.interceptors.audit_interceptor import AuditInterceptor
from meta.core.interceptors.context_interceptor import ContextInterceptor
from meta.core.datasource import get_data_source
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
import os

role_bp = Blueprint('role', __name__, url_prefix='/api/v1/roles')

_data_source = None
_bo_framework = None
_perm_service = None
_condition_perm_service = None
_association_service = None


def init_role_services(data_source=None):
    """初始化角色服务"""
    global _data_source, _perm_service, _condition_perm_service, _association_service
    
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)
    
    _perm_service = PermissionService(_data_source)
    _condition_perm_service = ConditionPermissionService(_data_source)
    _association_service = AssociationService(_data_source)


def _get_bo_framework():
    """获取全局 BOFramework 实例（在server.py中初始化）"""
    from meta.core.bo_framework import bo_framework
    return bo_framework


def _get_perm_service():
    """获取权限服务实例"""
    if _perm_service is None:
        init_role_services()
    return _perm_service


def _get_condition_perm_service():
    """获取条件权限服务实例"""
    if _condition_perm_service is None:
        init_role_services()
    return _condition_perm_service


def _get_association_service():
    """获取关联服务实例"""
    if _association_service is None:
        init_role_services()
    return _association_service


def _set_user_context():
    """设置用户上下文"""
    current_user = get_current_user()
    bo = _get_bo_framework()
    bo.set_user_context(
        user_id=current_user.get('user_id') if current_user else None,
        user_name=current_user.get('display_name', current_user.get('username', 'unknown')) if current_user else 'unknown',
    )


def _get_latest_change_time(object_type: str, object_id: int) -> str:
    """
    从审计日志获取对象最新的变更时间
    
    单一事实原则：
    - 优先返回最新的 UPDATE/DELETE 时间
    - 如果没有变更记录，返回 CREATE 时间（创建即变更）
    
    Args:
        object_type: 对象类型，如 'role', 'user'
        object_id: 对象ID
        
    Returns:
        ISO 格式的时间字符串，如果不存在则返回 None
    """
    cursor = _data_source.execute("""
        SELECT created_at FROM audit_logs 
        WHERE object_type = ? AND object_id = ?
        ORDER BY 
            CASE action 
                WHEN 'UPDATE' THEN 1 
                WHEN 'DELETE' THEN 2 
                WHEN 'CREATE' THEN 3 
            END ASC,
            created_at DESC
        LIMIT 1
    """, [object_type, object_id])
    row = cursor.fetchone()
    return row[0] if row else None


@role_bp.route('', methods=['GET'])
@login_required
def list_roles():
    """获取角色列表
    
    注意：变更时间从审计日志计算，不存储在对象表中（单一事实原则）
    """
    # [FIX 2026-06-08] 非管理员不能访问角色列表（避免 OperationalError 500）
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403
    roles = _get_perm_service().get_all_roles()

    # [FR-006] 批量获取权限和更新时间, 避免 N+1 查询
    if roles:
        role_ids = [r['id'] for r in roles]
        placeholders = ','.join(['?'] * len(role_ids))

        # 批量获取角色权限
        # [V1 修复 2026-06-10] permissions 表没有 is_system 列, 移除避免 500
        cursor = _data_source.execute(
            f"SELECT rp.role_id, p.id, p.code, p.name, p.description "
            f"FROM permissions p JOIN role_permissions rp ON p.id = rp.permission_id "
            f"WHERE rp.role_id IN ({placeholders})",
            role_ids
        )
        perm_map = {}
        for row in cursor.fetchall():
            rid = row[0]
            if rid not in perm_map:
                perm_map[rid] = []
            perm_map[rid].append({
                'id': row[1], 'code': row[2], 'name': row[3],
                'description': row[4]
            })

        # 批量获取 updated_at (参照 _enrich_updated_at 模式)
        cursor = _data_source.execute(
            f"SELECT object_id, MAX(created_at) as max_update_at "
            f"FROM audit_logs WHERE object_type = 'role' "
            f"AND object_id IN ({placeholders}) AND action = 'UPDATE' "
            f"GROUP BY object_id",
            role_ids
        )
        updated_map = dict(cursor.fetchall())

        for role in roles:
            role['permissions'] = perm_map.get(role['id'], [])
            role['updated_at'] = updated_map.get(role['id'])
    else:
        for role in roles:
            role['permissions'] = []
            role['updated_at'] = None

    return jsonify({'success': True, 'data': roles})


@role_bp.route('', methods=['POST'])
@login_required
def create_role():
    """创建角色"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    data = request.get_json(silent=True) or {}
    code = data.get('code', '').strip()
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()

    if not code or not name:
        return jsonify({'success': False, 'message': '角色编码和名称不能为空'}), 400

    cursor = _data_source.execute("SELECT id FROM roles WHERE code = ?", [code])
    if cursor.fetchone():
        return jsonify({'success': False, 'message': '角色编码已存在'}), 400

    _set_user_context()
    bo = _get_bo_framework()
    
    result = bo.create('role', {
        'code': code,
        'name': name,
        'description': description,
        'is_system': False,
    })
    
    if not result.success:
        return jsonify({'success': False, 'message': result.message}), 400

    return jsonify({
        'success': True,
        'data': result.data,
        'message': '角色创建成功',
    }), 201


@role_bp.route('/<int:role_id>', methods=['GET'])
@login_required
def get_role(role_id):
    """获取指定角色的详细信息
    
    注意：变更时间从审计日志计算，不存储在对象表中（单一事实原则）
    """
    _set_user_context()
    bo = _get_bo_framework()
    
    result = bo.read('role', role_id)
    
    if not result.success:
        return jsonify({'success': False, 'message': '角色不存在'}), 404
    
    role = result.data
    role['updated_at'] = _get_latest_change_time('role', role_id)
    
    return jsonify({'success': True, 'data': role})


@role_bp.route('/<int:role_id>/users', methods=['POST'])
@login_required
def assign_role_to_users(role_id):
    """分配角色给用户（通过用户组路径）"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    try:
        cursor = _data_source.execute("SELECT id, name FROM roles WHERE id = ?", [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        data = request.get_json(silent=True) or {}
        user_ids = data.get('user_ids', [])

        if not user_ids:
            return jsonify({'success': False, 'message': '用户ID列表不能为空'}), 400

        current_user = get_current_user()
        operator_id = current_user.get('user_id', 0) if current_user else 0
        operator_name = current_user.get('username', 'system') if current_user else 'system'

        results = []
        for user_id in user_ids:
            success = _get_perm_service().assign_role(user_id, role_id)
            results.append({'user_id': user_id, 'success': success})

        success_count = sum(1 for r in results if r.get('success'))
        failed_count = len(results) - success_count

        if success_count == len(results):
            return jsonify({
                'success': True,
                'message': f'成功分配 {success_count} 个用户到角色',
                'data': {'assigned': success_count, 'failed': failed_count}
            })
        elif success_count > 0:
            return jsonify({
                'success': False,
                'message': f'部分分配失败: 成功 {success_count} 个，失败 {failed_count} 个',
                'data': {'assigned': success_count, 'failed': failed_count, 'details': results}
            }), 207
        else:
            return jsonify({'success': False, 'message': '所有分配操作均失败', 'data': results}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@role_bp.route('/<int:role_id>/users/<int:user_id>', methods=['DELETE'])
@login_required
def remove_user_from_role(role_id, user_id):
    """从角色移除用户（通过用户组路径）"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    try:
        cursor = _data_source.execute("SELECT id, name FROM roles WHERE id = ?", [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        success = _get_perm_service().remove_role(user_id, role_id)

        if success:
            return jsonify({
                'success': True,
                'message': f'已从角色移除用户 {user_id}',
                'data': {'success': True}
            })
        else:
            return jsonify({'success': False, 'message': '移除失败'}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@role_bp.route('/<int:role_id>', methods=['PUT'])
@login_required
def update_role(role_id):
    """更新角色"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    cursor = _data_source.execute("SELECT is_system FROM roles WHERE id = ?", [role_id])
    row = cursor.fetchone()
    if not row:
        return jsonify({'success': False, 'message': '角色不存在'}), 404

    if row[0]:
        return jsonify({'success': False, 'message': '系统角色不可修改'}), 400

    data = request.get_json(silent=True) or {}

    update_data = {}
    for field in ['name', 'description']:
        if field in data:
            update_data[field] = data[field]

    if not update_data:
        return jsonify({'success': False, 'message': '没有可更新的字段'}), 400

    _set_user_context()
    bo = _get_bo_framework()
    
    result = bo.update('role', role_id, update_data)
    
    if not result.success:
        return jsonify({'success': False, 'message': result.message}), 400

    return jsonify({'success': True, 'message': '角色更新成功'})


@role_bp.route('/<int:role_id>', methods=['DELETE'])
@login_required
def delete_role(role_id):
    """删除角色"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    cursor = _data_source.execute("SELECT is_system FROM roles WHERE id = ?", [role_id])
    row = cursor.fetchone()
    if not row:
        return jsonify({'success': False, 'message': '角色不存在'}), 404

    if row[0]:
        return jsonify({'success': False, 'message': '系统角色不可删除'}), 400

    _set_user_context()
    bo = _get_bo_framework()
    
    result = bo.delete('role', role_id)
    
    if not result.success:
        return jsonify({'success': False, 'message': result.message}), 400

    return jsonify({'success': True, 'message': '角色删除成功'})


@role_bp.route('/<int:role_id>/permissions', methods=['PUT'])
@login_required
def set_role_permissions(role_id):
    """设置角色权限"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    data = request.get_json(silent=True) or {}
    permission_ids = data.get('permission_ids', [])

    with _data_source.transaction():
        success = _get_perm_service().set_role_permissions(role_id, permission_ids)

    if not success:
        return jsonify({'success': False, 'message': '权限配置失败'}), 400

    return jsonify({'success': True, 'message': '权限配置成功'})


@role_bp.route('/<int:role_id>/permissions', methods=['GET'])
@login_required
def get_role_permissions(role_id):
    """获取指定角色的功能权限"""
    try:
        cursor = _data_source.execute("SELECT id, name FROM roles WHERE id = ?", [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        permissions = _get_perm_service().get_role_permissions(role_id)
        return jsonify({'success': True, 'data': permissions})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@role_bp.route('/<int:role_id>/menus', methods=['GET'])
@login_required
def get_role_menus(role_id):
    """获取指定角色的菜单权限"""
    try:
        cursor = _data_source.execute("SELECT id, name FROM roles WHERE id = ?", [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        cursor = _data_source.execute("""
            SELECT menu_code, created_at FROM role_menu_permissions
            WHERE role_id = ?
            ORDER BY created_at DESC
        """, [role_id])

        menu_permissions = []
        for row in cursor.fetchall():
            menu_permissions.append({
                'role_id': role_id,
                'menu_code': row[0],
                'created_at': row[1]
            })

        return jsonify({'success': True, 'data': menu_permissions})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@role_bp.route('/<int:role_id>/data-permissions', methods=['GET'])
@login_required
def get_role_data_permissions(role_id):
    """获取指定角色的数据权限规则"""
    try:
        cursor = _data_source.execute("SELECT id, name FROM roles WHERE id = ?", [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        rules = _get_condition_perm_service().get_rules_by_role(role_id)

        return jsonify({'success': True, 'data': rules})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@role_bp.route('/<int:role_id>/data-permissions', methods=['POST'])
@login_required
def add_role_data_permission(role_id):
    """为角色添加数据权限规则"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403

    try:
        cursor = _data_source.execute("SELECT id, name, is_system FROM roles WHERE id = ?", [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        if role[2]:
            return jsonify({'success': False, 'message': '系统角色不可修改'}), 400

        data = request.get_json(silent=True) or {}

        required_fields = ['resource_type', 'condition']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'缺少必填字段: {field}'}), 400

        current_user = get_current_user()
        user_id = current_user.get('id') if current_user else None

        with _data_source.transaction():
            cursor = _data_source.execute("""
                INSERT INTO permission_rules (role_id, resource_type, condition, permission_level,
                                           is_denied, inherit_to_children, propagate_to_parents,
                                           analysis_mode, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                role_id,
                data.get('resource_type'),
                data.get('condition'),
                data.get('permission_level', 'read'),
                1 if data.get('is_denied') else 0,
                1 if data.get('inherit_to_children', True) else 0,
                1 if data.get('propagate_to_parents', True) else 0,
                data.get('analysis_mode'),
                user_id
            ])

        return jsonify({
            'success': True,
            'message': '数据权限规则添加成功',
            'data': {'id': cursor.lastrowid}
        }), 201

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@role_bp.route('/permissions', methods=['GET'])
@login_required
def list_permissions():
    """v1.4 P8 Sunset: 已迁移到 v2/bo/permission"""
    return jsonify({
        'error': 'API Gone',
        'message': 'GET /api/v1/roles/permissions has been sunset; use GET /api/v2/bo/permission',
        'sunset_at': '2026-06-05',
        'migrated_to': '/api/v2/bo/permission'
    }), 410


@role_bp.route('/<int:role_id>/logs', methods=['GET'])
@login_required
def get_role_logs(role_id):
    """获取指定角色的操作日志"""
    try:
        cursor = _data_source.execute("SELECT id, name FROM roles WHERE id = ?", [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)

        offset = (page - 1) * page_size

        cursor = _data_source.execute("""
            SELECT * FROM audit_logs
            WHERE object_type = 'role' AND object_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, [role_id, page_size, offset])

        columns = [desc[0] for desc in cursor.description]
        logs = []
        for row in cursor.fetchall():
            logs.append(dict(zip(columns, row)))

        cursor = _data_source.execute(
            "SELECT COUNT(*) as total FROM audit_logs WHERE object_type = 'role' AND object_id = ?",
            [role_id]
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
