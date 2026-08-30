# -*- coding: utf-8 -*-
"""
组织 API - 基于BOFramework重构版本

使用元数据驱动的BOFramework实现统一的CRUD操作和审计日志。
"""

from flask import Blueprint, request, jsonify, g
from meta.api._deprecation import v1_deprecated
from meta.services.auth_middleware import login_required, require_permission, is_admin, get_current_user
from meta.services.org_service import OrgService
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
            return jsonify({'success': False, 'message': '您没有执行此操作的权限，需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated

org_bp = Blueprint('org', __name__, url_prefix='/api/v1')

_data_source = None
_bo_framework = None
_group_service = None
_perm_service = None


def init_org_services(data_source=None):
    """初始化组织服务"""
    global _data_source, _group_service, _perm_service
    
    if data_source:
        _data_source = data_source
    elif _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)
    
    _group_service = OrgService(_data_source)
    _perm_service = DataPermissionService(_data_source)


def _get_bo_framework():
    """获取全局 BOFramework 实例（在server.py中初始化）"""
    from meta.core.bo_framework import bo_framework
    return bo_framework


def _get_group_service():
    """获取组织服务实例"""
    if _group_service is None:
        init_org_services()
    return _group_service


def _get_perm_service():
    """获取数据权限服务实例"""
    if _perm_service is None:
        init_org_services()
    return _perm_service


def _set_user_context():
    """设置用户上下文"""
    current_user = get_current_user()
    bo = _get_bo_framework()
    bo.set_user_context(
        user_id=current_user.get('user_id') if current_user else None,
        user_name=current_user.get('display_name', current_user.get('username', 'unknown')) if current_user else 'unknown',
    )


def _bump_org_subtree_users(org_id: int) -> None:
    """组织（含子孙）全部成员权限变更后失效令牌，强制重新鉴权拉取最新权限

    [最小范围] 组织挂/摘权限集会影响该组织自身 + 全部子孙组织的成员，
    必须对所有受影响用户 token bump，否则已登录用户要等 token 过期才生效。
    """
    try:
        _get_group_service()  # 确保 _data_source 已初始化
        from meta.services.token_version_service import token_version_service
        user_ids = OrgService(_data_source).get_org_subtree_user_ids(org_id)
        if user_ids:
            token_version_service.bump(user_ids)
    except Exception:
        pass


# v1.4 P8 Sunset (2026-06-05): 已移除 4 个主表 CRUD 端点
#   - GET /orgs: 改用 v2/bo/user_group 端点
#   - POST /orgs: 改用 v2/bo/user_group 端点
#   - GET /orgs/<id>: 改用 v2/bo/user_group/<id> 端点
#   - PUT /orgs/<id>: 改用 v2/bo/user_group/<id> 端点
#   - DELETE /orgs/<id>: 改用 v2/bo/user_group/<id> DELETE 端点
#
# 保留的 v1 业务关系端点（业务路径）：
#   - /orgs/<id>/members
#   - /orgs/<id>/data-permissions
#   - /orgs/<id>/roles
#   - /orgs/<id>/logs
#   - /system/migrate-group-permissions-to-roles

# 保留 v1/orgs/<id> 业务关系端点
# （移到下面以维持模块化结构）


@org_bp.route('/orgs/<int:org_id>/members', methods=['GET'])
@login_required
@require_permission('user:read')
@v1_deprecated(migrated_to='/api/v2/bo/user_group/<org_id>/associations/members')
def get_group_members(org_id):
    """
    [已废弃] 获取组织成员
    请使用 v2 API: GET /api/v2/bo/user_group/{org_id}/associations/members
    """
    try:
        service = _get_group_service()
        members = service.get_group_members(org_id)
        return jsonify({'success': True, 'data': members})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/members', methods=['POST'])
@login_required
@require_permission('user:update')
@v1_deprecated(migrated_to='/api/v2/bo/user_group/<org_id>/associations/members')
def add_group_member(org_id):
    """
    [已废弃] 添加成员到组织
    请使用 v2 API: POST /api/v2/bo/user_group/{org_id}/associations/members
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
                src_id=org_id,
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


@org_bp.route('/orgs/<int:org_id>/members', methods=['PUT'])
@login_required
@require_permission('user:update')
def set_group_members(org_id):
    """增量更新组织成员（只记录新增的成员）"""
    try:
        data = request.get_json()
        new_user_ids = set(data.get('user_ids', []))
        
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()

        with _data_source.transaction():
            cursor = _data_source.execute(
                "SELECT user_id FROM org_members WHERE org_id = ?",
                [org_id]
            )
            rows = cursor.fetchall()
            existing_user_ids = set(row[0] for row in rows)

            users_to_add = new_user_ids - existing_user_ids
            users_to_remove = existing_user_ids - new_user_ids

            removed_count = 0
            for uid in users_to_remove:
                result = bo.dissociate(
                    src_type='user_group',
                    src_id=org_id,
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
                    src_id=org_id,
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


@org_bp.route('/orgs/<int:org_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
@require_permission('user:update')
def remove_group_member(org_id, user_id):
    """从组织移除成员"""
    try:
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()
        
        result = bo.dissociate(
            src_type='user_group',
            src_id=org_id,
            tgt_type='user',
            tgt_id=user_id,
            association_name='members'
        )
        
        if result.success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': result.message}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/data-permissions', methods=['GET'])
@login_required
@require_permission('user:read')
@v1_deprecated(migrated_to='/api/v2/bo/user_group/<org_id>/associations/roles')
def get_org_data_permissions(org_id):
    """[已废弃] 获取组织数据权限 - 建议通过角色关联获取权限"""
    try:
        service = _get_perm_service()
        perms = service.get_org_data_permissions(org_id)
        return jsonify({'success': True, 'data': perms,
                        '_hint': '建议使用 /orgs/{id}/roles 接口通过角色间接分配数据权限'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/data-permissions', methods=['POST'])
@login_required
@require_permission('user:update')
@v1_deprecated(migrated_to='/api/v2/bo/org/<org_id>/associations/permission_sets')
def add_group_data_permission(org_id):
    """[已废弃] 为组织添加数据权限 - 建议创建角色并关联到组织"""
    try:
        service = _get_perm_service()
        data = request.get_json()
        resource_type = data.get('resource_type')
        resource_id = data.get('resource_id')
        permission_level = data.get('permission_level', 'read')
        inherit_to_children = data.get('inherit_to_children', True)

        if not resource_type or not resource_id:
            return jsonify({'success': False, 'message': '资源类型和资源 ID 不能为空'}), 400

        perm_id = service.add_group_data_permission(org_id, resource_type, resource_id, permission_level, inherit_to_children)
        if perm_id:
            return jsonify({'success': True, 'data': {'id': perm_id}})
        return jsonify({'success': False, 'message': 'Failed to add permission'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/data-permissions/<int:perm_id>', methods=['DELETE'])
@login_required
@require_permission('user:update')
@v1_deprecated(migrated_to='/api/v2/bo/org/<org_id>/associations/permission_sets')
def remove_group_data_permission(org_id, perm_id):
    """[已废弃] 删除组织数据权限"""
    try:
        service = _get_perm_service()
        success = service.remove_group_data_permission(perm_id)
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Failed to delete permission'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/roles', methods=['GET'])
@login_required
@require_permission('user:read')
@v1_deprecated(migrated_to='/api/v2/bo/org/<org_id>/associations/permission_sets')
def get_org_permission_sets(org_id):
    """
    [已废弃] 获取组织关联的权限集列表
    请使用 v2 API: GET /api/v2/bo/org/{org_id}/associations/permission_sets
    """
    try:
        service = _get_group_service()
        roles = service.get_org_permission_sets(org_id)
        return jsonify({'success': True, 'data': roles})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/roles', methods=['PUT'])
@login_required
@require_permission('user:update')
def set_org_permission_sets(org_id):
    """批量设置组织角色（增量更新）"""
    try:
        data = request.get_json()
        new_permission_set_ids = set(data.get('permission_set_ids', []))

        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()

        with _data_source.transaction():
            cursor = _data_source.execute(
                "SELECT permission_set_id FROM org_permission_sets WHERE org_id = ?",
                [org_id]
            )
            rows = cursor.fetchall()
            existing_permission_set_ids = set(row[0] for row in rows)

            permission_sets_to_add = new_permission_set_ids - existing_permission_set_ids
            permission_sets_to_remove = existing_permission_set_ids - new_permission_set_ids

            removed_count = 0
            for pid in permission_sets_to_remove:
                result = bo.dissociate(
                    src_type='org',
                    src_id=org_id,
                    tgt_type='permission_set',
                    tgt_id=pid,
                    association_name='permission_sets'
                )
                if result.success:
                    removed_count += 1

            added_count = 0
            for pid in permission_sets_to_add:
                result = bo.associate(
                    src_type='org',
                    src_id=org_id,
                    tgt_type='permission_set',
                    tgt_id=pid,
                    association_name='permission_sets'
                )
                if result.success:
                    added_count += 1

        # [最小范围] 挂/摘权限集影响 org 子树全部成员，失效令牌强制刷新
        _bump_org_subtree_users(org_id)

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


@org_bp.route('/orgs/<int:org_id>/roles/<int:permission_set_id>', methods=['POST'])
@login_required
@require_permission('user:update')
def add_group_role(org_id, permission_set_id):
    """为组织添加单个权限集"""
    try:
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()

        result = bo.associate(
            src_type='org',
            src_id=org_id,
            tgt_type='permission_set',
            tgt_id=permission_set_id,
            association_name='permission_sets'
        )

        if result.success:
            _bump_org_subtree_users(org_id)
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': result.message}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/roles/<int:permission_set_id>', methods=['DELETE'])
@login_required
@require_permission('user:update')
def remove_group_role(org_id, permission_set_id):
    """从组织移除权限集"""
    try:
        current_user = get_current_user()
        _set_user_context()
        bo = _get_bo_framework()

        result = bo.dissociate(
            src_type='org',
            src_id=org_id,
            tgt_type='permission_set',
            tgt_id=permission_set_id,
            association_name='permission_sets'
        )

        if result.success:
            _bump_org_subtree_users(org_id)
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': result.message}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/roles/available', methods=['GET'])
@login_required
@require_permission('user:read')
def get_available_roles_for_group(org_id):
    """获取可分配给该组织的角色列表（未关联的）"""
    try:
        service = _get_group_service()
        roles = service.get_roles_not_in_group(org_id)
        return jsonify({'success': True, 'data': roles})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/system/migrate-group-permissions-to-roles', methods=['POST'])
@login_required
@admin_required
def migrate_group_permissions():
    """将旧的组织直接数据权限迁移到基于角色的模型 [仅管理员]"""
    try:
        service = _get_group_service()
        migrated_count = service.migrate_org_data_permissions_to_roles()
        return jsonify({
            'success': True,
            'data': {'migrated_group_count': migrated_count},
            'message': f'成功迁移 {migrated_count} 个组织的直接数据权限到对应角色'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@org_bp.route('/orgs/<int:org_id>/logs', methods=['GET'])
@login_required
def get_user_group_logs(org_id):
    """获取指定组织的操作日志"""
    try:
        cursor = _data_source.execute("SELECT id, name FROM orgs WHERE id = ?", [org_id])
        group = cursor.fetchone()
        if not group:
            return jsonify({'success': False, 'message': '组织不存在'}), 404

        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)

        offset = (page - 1) * page_size

        cursor = _data_source.execute("""
            SELECT * FROM audit_logs
            WHERE object_type = 'user_group' AND object_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, [org_id, page_size, offset])

        columns = [desc[0] for desc in cursor.description]
        logs = []
        for row in cursor.fetchall():
            logs.append(dict(zip(columns, row)))

        cursor = _data_source.execute(
            "SELECT COUNT(*) as total FROM audit_logs WHERE object_type = 'user_group' AND object_id = ?",
            [org_id]
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
