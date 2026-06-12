# -*- coding: utf-8 -*-
"""
条件型权限规则 API

提供权限规则的 CRUD、预览、管理维度、员工数据权限等端点
"""

from flask import Blueprint, request, jsonify, g
from meta.services.auth_middleware import login_required, require_permission
from meta.services.condition_permission_service import ConditionPermissionService
from meta.core.datasource import get_data_source
import os

permission_rule_bp = Blueprint('permission_rule', __name__, url_prefix='/api/v1/permission-rules')


def admin_required(f):
    from functools import wraps
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not hasattr(g, 'current_user') or not g.current_user:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401
        perms = g.current_user.get('permissions', [])
        if '*' not in perms and 'admin' not in perms:
            return jsonify({'success': False, 'message': 'Admin required'}), 403
        return f(*args, **kwargs)
    return decorated


_data_source = None

def _get_service():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return ConditionPermissionService(_data_source)


@permission_rule_bp.route('', methods=['GET'])
@login_required
@require_permission('user:read')
def list_rules():
    """获取权限规则列表"""
    try:
        service = _get_service()
        role_id = request.args.get('role_id', type=int)
        resource_type = request.args.get('resource_type')

        if role_id:
            rules = service.get_rules_by_role(role_id, resource_type)
        else:
            rules = service.get_all_rules(resource_type)

        return jsonify({'success': True, 'data': rules})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/<int:rule_id>', methods=['GET'])
@login_required
@require_permission('user:read')
def get_rule(rule_id):
    """获取单条权限规则"""
    try:
        service = _get_service()
        rule = service.get_rule(rule_id)
        if rule:
            return jsonify({'success': True, 'data': rule})
        return jsonify({'success': False, 'message': 'Rule not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('', methods=['POST'])
@login_required
@require_permission('user:update')
def create_rule():
    """创建权限规则"""
    try:
        service = _get_service()
        data = request.get_json()

        required = ['role_id', 'resource_type', 'condition']
        for field in required:
            if field not in data:
                return jsonify({'success': False, 'message': f'{field} is required'}), 400

        data['created_by'] = g.current_user.get('user_id') if hasattr(g, 'current_user') and g.current_user else None

        rule_id = service.create_rule(data)
        if rule_id:
            # [FIX 2026-06-12] 权限规则审计日志: 关联到角色对象
            from meta.api._audit_helper import write_permission_config_audit
            write_permission_config_audit(
                action='CREATE',
                object_type='permission_rule',
                object_id=rule_id,
                data={
                    'role_id': data.get('role_id'),
                    'resource_type': data.get('resource_type'),
                    'permission_level': data.get('permission_level', 'read'),
                },
                parent_object_type='role',
                parent_object_id=data.get('role_id'),
            )
            return jsonify({'success': True, 'data': {'id': rule_id}})
        return jsonify({'success': False, 'message': 'Failed to create rule'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/<int:rule_id>', methods=['PUT'])
@login_required
@require_permission('user:update')
def update_rule(rule_id):
    """更新权限规则"""
    try:
        service = _get_service()
        data = request.get_json()
        success = service.update_rule(rule_id, data)
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Failed to update rule'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/<int:rule_id>', methods=['DELETE'])
@login_required
@require_permission('user:update')
def delete_rule(rule_id):
    """删除权限规则"""
    try:
        service = _get_service()
        success = service.delete_rule(rule_id)
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Failed to delete rule'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/preview', methods=['POST'])
@login_required
@require_permission('user:read')
def preview_matching():
    """预览条件匹配的资源"""
    try:
        service = _get_service()
        data = request.get_json()
        condition = data.get('condition', '')
        resource_type = data.get('resource_type', '')

        if not condition or not resource_type:
            return jsonify({'success': False, 'message': 'condition and resource_type are required'}), 400

        result = service.preview_matching_resources(condition, resource_type)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/check', methods=['POST'])
@login_required
def check_permission():
    """检查当前用户权限"""
    try:
        service = _get_service()
        data = request.get_json()
        resource_type = data.get('resource_type', '')
        resource_id = data.get('resource_id')
        action = data.get('action', 'read')

        if not resource_type or resource_id is None:
            return jsonify({'success': False, 'message': 'resource_type and resource_id are required'}), 400

        user_id = g.current_user.get('user_id') if hasattr(g, 'current_user') and g.current_user else None
        if not user_id:
            return jsonify({'success': False, 'message': 'Not authenticated'}), 401

        result = service.check_permission(user_id, resource_type, resource_id, action)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/field-metadata', methods=['GET'])
@login_required
@require_permission('user:read')
def get_field_metadata():
    """获取资源类型的字段元数据（用于自定义条件字段Value Help）"""
    try:
        service = _get_service()
        resource_type = request.args.get('resource_type')

        if not resource_type:
            return jsonify({'success': False, 'message': 'resource_type is required'}), 400

        fields = service.get_resource_field_metadata(resource_type)
        return jsonify({'success': True, 'data': fields})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/employee-scopes', methods=['GET'])
@login_required
@require_permission('user:read')
def get_employee_scopes():
    """获取员工数据权限范围列表"""
    try:
        service = _get_service()
        scopes = service.get_employee_data_scopes()
        return jsonify({'success': True, 'data': scopes})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/reference-check', methods=['POST'])
@login_required
@admin_required
def check_resource_references():
    """检查资源被哪些权限规则引用 [仅管理员]"""
    try:
        service = _get_service()
        data = request.get_json()
        resource_type = data.get('resource_type', '')
        resource_id = data.get('resource_id')

        if not resource_type or resource_id is None:
            return jsonify({'success': False, 'message': 'resource_type and resource_id are required'}), 400

        affected = service.check_rule_references_resource(resource_type, resource_id)
        return jsonify({'success': True, 'data': {'affected_rules': affected, 'count': len(affected)}})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ========== FR-004 / v1.4 对齐：ConditionRuleDialog UI 依赖的兼容端点 ==========
# 历史: ConditionRuleDialog 调 /permission-rules/dimensions/<code>/values,
# 真实端点是 /management-dimensions/<id>/instances.
# 在 permission-rule 命名空间下提供同义转发, 避免前端耦合 management-dimension 端点.

@permission_rule_bp.route('/dimensions/<string:dimension_code>/values', methods=['GET'])
@login_required
@require_permission('user:read')
def list_dimension_values_for_rule(dimension_code):
    """
    列出某管理维度的可选值（Value Help），供条件规则 UI 选值用。

    Query:
        search / page / page_size / filter_<field>=<value> (级联过滤, 复数 IN)

    Returns:
        { success, data: [{id, code, name, parent_name}, ...] }
    """
    try:
        # 复用 management_dimension_api 的引擎, 保持单一事实
        from meta.api.management_dimension_api import (
            _data_source,
            _PARENT_INFO_MAP,
            _get_engine,
        )
        from meta.services.management_dimension_engine import (
            CODE_FIELD_MAP,
            DISPLAY_FIELD_MAP,
            RESOURCE_TABLE_MAP,
        )
        engine = _get_engine()

        search = request.args.get('search', '').strip()
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 50, type=int)
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 200:
            page_size = 50
        offset = (page - 1) * page_size

        table_name = RESOURCE_TABLE_MAP.get(dimension_code)
        if not table_name:
            return jsonify({'success': False, 'message': f'Unknown dimension: {dimension_code}'}), 400

        display_field = DISPLAY_FIELD_MAP.get(dimension_code, 'name')
        code_field = CODE_FIELD_MAP.get(dimension_code, 'code')
        parent_info = _PARENT_INFO_MAP.get(dimension_code)

        # 探测实际列
        try:
            cursor = _data_source.execute(f'PRAGMA table_info({table_name})')
            columns = [r[1] for r in cursor.fetchall()]
        except Exception:
            columns = []
        if display_field not in columns:
            display_field = 'name' if 'name' in columns else (code_field if code_field in columns else 'id')
        if code_field not in columns:
            code_field = 'id'

        where_clause = ''
        params = []
        seen_filter_keys = set()
        if search:
            where_clause = f'WHERE (main.{display_field} LIKE ? OR main.{code_field} LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])

        for key in request.args:
            if key.startswith('filter_') and key not in seen_filter_keys:
                field_name = key[7:]
                if field_name not in columns:
                    continue
                values = [v for v in request.args.getlist(key) if v]
                if not values:
                    continue
                seen_filter_keys.add(key)
                if len(values) == 1:
                    if where_clause:
                        where_clause += f' AND main.{field_name} = ?'
                    else:
                        where_clause = f'WHERE main.{field_name} = ?'
                    params.append(values[0])
                else:
                    placeholders = ','.join(['?' for _ in values])
                    if where_clause:
                        where_clause += f' AND main.{field_name} IN ({placeholders})'
                    else:
                        where_clause = f'WHERE main.{field_name} IN ({placeholders})'
                    params.extend(values)

        select_fields = f'main.id, main.{code_field}, main.{display_field}'
        from_clause = f'FROM {table_name} main'
        if parent_info:
            parent_type, parent_table, parent_fk, parent_display = parent_info
            select_fields += f', parent.{parent_display} AS parent_name'
            from_clause += f' LEFT JOIN {parent_table} parent ON main.{parent_fk} = parent.id'

        sql = f'SELECT {select_fields} {from_clause} {where_clause} ORDER BY main.{display_field} LIMIT ? OFFSET ?'
        params.extend([page_size, offset])
        cursor = _data_source.execute(sql, params)

        items = []
        for row in cursor.fetchall():
            item = {
                'id': row[0],
                'code': str(row[1]) if row[1] else '',
                'display_name': str(row[2]) if row[2] is not None else '',
            }
            if parent_info:
                item['path'] = str(row[3]) if row[3] is not None else ''
            items.append(item)

        return jsonify({'success': True, 'data': items})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@permission_rule_bp.route('/dimensions', methods=['GET'])
@login_required
@require_permission('user:read')
def list_dimensions_for_rule():
    """
    列出 ConditionRuleDialog 可见的管理维度（兼容历史端点）。

    ConditionRuleDialog 历史调 /permission-rules/dimensions,
    真实端点是 /management-dimensions. 这里转发, 保持前端不动。
    """
    try:
        from meta.api.management_dimension_api import _get_engine
        engine = _get_engine()
        dimensions = engine.get_available_dimensions()
        result = []
        for dim in dimensions:
            dim_id = dim.get('id')
            result.append({
                'id': dim_id,
                'code': dim_id,
                'name': dim.get('name', ''),
                'description': dim.get('description', ''),
                'field': f'{dim_id}_id' if dim_id else None,
                'relation_object': dim_id,
                'cascade_parent': _guess_cascade_parent(dim_id),
                'resource_types': _dim_resource_types(dim_id),
            })
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def _guess_cascade_parent(dim_id):
    """粗略级联父维度（与 management_dimension.yaml 顺序保持一致）。"""
    cascade = {
        'sub_domain': 'domain',
        'service_module': 'sub_domain',
        'business_object': 'service_module',
    }
    return cascade.get(dim_id)


def _dim_resource_types(dim_id):
    """管理维度可作用的资源类型（与 ConditionRuleDialog 的 resourceTypeOptions 对齐）。"""
    return ['domain', 'sub_domain', 'service_module', 'business_object']
