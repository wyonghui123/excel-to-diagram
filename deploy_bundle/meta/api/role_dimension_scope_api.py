# -*- coding: utf-8 -*-
"""
角色维度范围API

提供角色维度范围声明的 CRUD 和推导预览
"""

from flask import Blueprint, request, jsonify
import os

from meta.core.datasource import get_data_source
from meta.api.user_api import login_required
from meta.services.auth_middleware import is_admin, get_current_user
from meta.services.dimension_scope_engine import get_dimension_scope_engine
from meta.api._audit_helper import write_permission_config_audit
from functools import wraps
import json

role_dim_bp = Blueprint('role_dim', __name__, url_prefix='/api/v1/roles')

_data_source = None


def _ds():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or not is_admin(user):
            return jsonify({"success": False, "message": "\u9700\u8981\u7ba1\u7406\u5458\u6743\u9650"}), 403
        return f(*args, **kwargs)
    return decorated


@role_dim_bp.route('/<int:role_id>/dimension-scopes', methods=['GET'])
@login_required
def get_dimension_scopes(role_id):
    try:
        ds = _ds()
        cursor = ds.execute(
            "SELECT id, role_id, dimension_code, dimension_values, inherit_children, scope_mode FROM role_dimension_scopes WHERE role_id = ?", [role_id]
        )
        cols = [d[0] for d in (cursor.description or [])]
        rows = []
        for row in cursor.fetchall():
            item = dict(zip(cols, row))
            dimension_code = item.get('dimension_code')
            raw_values = item.get('dimension_values', '[]')
            dimension_values = json.loads(raw_values or '[]')
            
            # 查询维度对象的名称
            if dimension_code and dimension_values:
                # 维度 code 对应的表名（product -> products, version -> versions 等）
                table_name = f"{dimension_code}s" if not dimension_code.endswith('s') else f"{dimension_code}"
                
                # 尝试查询名称（先查 name 字段，再查 code 字段）
                try:
                    value_list = ','.join(['?' for _ in dimension_values])
                    query = f"SELECT id, COALESCE(name, code, '') as name, code FROM {table_name} WHERE id IN ({value_list})"
                    name_cursor = ds.execute(query, dimension_values)
                    inner_cols = [d[0] for d in (name_cursor.description or [])]
                    name_map = {}
                    for inner_row in name_cursor.fetchall():
                        row_dict = dict(zip(inner_cols, inner_row))
                        name_map[str(row_dict.get('id'))] = {'id': row_dict.get('id'), 'name': row_dict.get('name', ''), 'code': row_dict.get('code') or ''}
                    
                    # 构建完整对象列表
                    dimension_values_with_names = []
                    for vid in dimension_values:
                        vid_str = str(vid)
                        if vid_str in name_map:
                            dimension_values_with_names.append(name_map[vid_str])
                        else:
                            dimension_values_with_names.append({'id': vid, 'name': str(vid), 'code': ''})
                    
                    item['dimension_values'] = dimension_values_with_names
                except Exception as table_error:
                    # 表不存在或查询失败，回退到简单对象
                    item['dimension_values'] = [{'id': vid, 'name': str(vid), 'code': ''} for vid in dimension_values]
            else:
                item['dimension_values'] = []
            
            rows.append(item)
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@role_dim_bp.route('/<int:role_id>/dimension-scopes', methods=['POST'])
@admin_required
def save_dimension_scopes(role_id):
    try:
        data = request.get_json()
        # [FIX 2026-06-15] 空 list 是合法操作 (用户清空维度范围), 不应 400
        # 之前用 `if not data` 把空 list 当 400, 导致"移除 dim value 后保存"必失败
        if data is None:
            return jsonify({'success': False, 'error': '请求体为空'}), 400
        if not isinstance(data, list):
            return jsonify({'success': False, 'error': '请求体必须为 list'}), 400
        ds = _ds()
        with ds.transaction():
            ds.execute("DELETE FROM role_dimension_scopes WHERE role_id = ?", [role_id])
            for item in data:
                ds.execute(
                    "INSERT INTO role_dimension_scopes "
                    "(role_id, dimension_code, dimension_values, inherit_children, scope_mode) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        role_id,
                        item.get('dimension_code'),
                        json.dumps(item.get('dimension_values', [])),
                        1 if item.get('inherit_children', True) else 0,
                        item.get('scope_mode', 'include'),
                    ]
                )
        # [FIX 2026-06-12] 角色权限操作审计日志: 关联到角色对象
        # 之前这个 endpoint 没写 audit, 导致用户改管理维度后审计日志 tab 看不到记录
        write_permission_config_audit(
            action='UPDATE',
            object_type='role_dimension_scope',
            object_id=role_id,
            data={'scopes_count': len(data) if isinstance(data, list) else 0,
                  'dimension_codes': [item.get('dimension_code') for item in data] if isinstance(data, list) else []},
            parent_object_type='role',
            parent_object_id=role_id,
        )
        return jsonify({'success': True, 'message': '\u7ef4\u5ea6\u8303\u56f4\u5df2\u4fdd\u5b58'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@role_dim_bp.route('/<int:role_id>/derived-permissions', methods=['GET'])
@login_required
def get_derived_permissions(role_id):
    try:
        engine = get_dimension_scope_engine(_ds())
        result = engine.auto_sync_all(role_id)
        # [FIX 2026-06-12] 自动推导完成后也写 audit (跟手动 save 一致, 让操作日志完整)
        write_permission_config_audit(
            action='UPDATE',
            object_type='role_dimension_scope',
            object_id=role_id,
            data={'auto_derived': True,
                  'recommended_menus': len(result.get('recommended_menus', [])) if isinstance(result, dict) else 0,
                  'derived_permissions': len(result.get('derived_permissions', [])) if isinstance(result, dict) else 0},
            parent_object_type='role',
            parent_object_id=role_id,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
